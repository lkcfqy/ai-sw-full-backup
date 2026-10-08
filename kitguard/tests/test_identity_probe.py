"""CPU engineering contracts for the unselected identity probe, not accuracy evidence."""

from __future__ import annotations

import copy
import json
import sys
import threading
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from kitguard.consensus import compare_inventories
from kitguard.schemas import Observation
from kitguard.spatial import SpatialInventory, count_inventory
from kitguard.vision import _prepare_image
from scripts import probe_identity_verification as probe


def base_observation(objects=None, *, uncertain=False):
    objects = (
        objects
        if objects is not None
        else [
            {"part": "bolt", "center": [0.2, 0.4]},
            {"part": "nut", "center": [0.7, 0.8]},
            {"part": "washer", "center": [0.5, 0.5]},
        ]
    )
    payload = {
        "objects": objects,
        "uncertain_parts": ["nut"] if uncertain else [],
        "issues": ["CPU obstruction"] if uncertain else [],
        "action": {"kind": "recapture" if uncertain else "none", "message": "CPU only"},
    }
    inv = SpatialInventory.model_validate(payload)
    base, _, agree, clear = compare_inventories(inv, inv, "CPU engineering fixture")
    counted, _ = count_inventory(inv, "CPU engineering fixture")
    passes = [
        {
            "transform": transform,
            "input_sha256": "a" * 64,
            "observed": counted["observed"],
            "issues": counted["issues"],
            "action": counted["action"],
            "objects": objects,
            "uncertain_parts": list(payload["uncertain_parts"]),
        }
        for transform in ("original", "rotate_90_ccw")
    ]
    base["verification"] = {
        "mode": "spatial_consensus",
        "same_model_correlated_calls": True,
        "counts_agree": agree,
        "clear_agreement": clear,
        "passes": passes,
    }
    Observation.model_validate(base)
    return base


def reply(targets, **changes):
    return probe.IdentityResponse.model_validate(
        {
            "objects": [
                {
                    "id": target["id"],
                    "part": target["original_part"],
                    "status": "independent_object",
                    "issue": "",
                    **changes,
                }
                for target in targets
            ]
        }
    )


def case_fixture():
    return {
        "id": probe.SCREWS_IDS[0],
        "image": "engineering.png",
        "sha256": "b" * 64,
        "source_id": "synthetic:identity-cpu",
        "split": "development",
        "ground_truth": {"bolt": 1, "nut": 1, "washer": 1, "bracket": 0},
    }


def row_fixture(tmp_path, base=None):
    source = tmp_path / "normalized.jpg"
    Image.new("RGB", (240, 160), "gray").save(source)
    prepared = tmp_path / "prepared.png"
    _prepare_image(source, prepared, 1536)
    base = base or base_observation()
    base["verification"]["passes"][0]["input_sha256"] = probe.file_sha256(prepared)
    return source, {
        "observation": base,
        "error": None,
        "latency_ms": 700,
        "model_input_sha256": probe.file_sha256(source),
    }


class CPUVision:
    image_max_side = 1536
    last_generated_text = None
    _last_inference = None

    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def status(self):
        return {"loaded": bool(self.calls), "load_seconds": 0.01, "last_inference": self._last_inference}

    def _generate(self, system, prompt, images, schema, *, max_tokens):
        self.calls.append(
            {
                "system": system,
                "prompt": prompt,
                "images": images,
                "schema": schema,
                "max_tokens": max_tokens,
                "thread": threading.current_thread().name,
            }
        )
        self._last_inference = {"seconds": 0.001}
        if self.error:
            raise self.error
        return self.response


def test_selects_only_original_frame_nut_washer_without_category_in_id():
    targets = probe.select_targets(base_observation())
    assert [t["id"] for t in targets] == ["p002", "p003"]
    assert [t["original_part"] for t in targets] == ["nut", "washer"]
    assert probe.select_targets(base_observation(uncertain=True)) == []


@pytest.mark.parametrize("mutation", ["missing", "extra", "duplicate"])
def test_requires_complete_unique_ids(mutation):
    targets = probe.select_targets(base_observation())
    data = reply(targets).model_dump()
    if mutation == "missing":
        data["objects"].pop()
    elif mutation == "extra":
        data["objects"].append({**data["objects"][0], "id": "p020"})
    else:
        data["objects"].append(data["objects"][0])
    with pytest.raises(ValueError):
        probe.validate_response(probe.IdentityResponse.model_validate(data), targets)


@pytest.mark.parametrize(
    "field,value", [("part", "screw"), ("status", "confirmed"), ("id", "nut-001"), ("issue", 123)]
)
def test_schema_is_strict_and_bounded(field, value):
    data = {"objects": [{"id": "p001", "part": "nut", "status": "independent_object", "issue": ""}]}
    data["objects"][0][field] = value
    with pytest.raises(ValidationError):
        probe.IdentityResponse.model_validate(data)


def test_matching_independent_objects_do_not_change_counts_or_base():
    base = base_observation()
    saved = copy.deepcopy(base)
    targets = probe.select_targets(base)
    response = reply(targets)
    response.objects.reverse()  # Response order is not the identity key.
    filtered, guard = probe.apply_guard(base, targets, response)
    assert filtered["observed"] == base["observed"]
    assert base == saved and "verification" not in filtered
    assert guard["status"] == "confirmed_candidates"
    assert filtered["object_evidence"] == base["object_evidence"]


@pytest.mark.parametrize(
    "part,status,issue,blocked",
    [
        ("washer", "independent_object", "", {"nut", "washer"}),
        ("bolt", "attached_feature", "head attached to shaft", {"nut", "bolt"}),
        ("unknown", "uncertain", "hole unresolved", {"nut"}),
        ("nut", "no_object", "reflection", {"nut"}),
        ("nut", "attached_feature", "attached", {"nut"}),
        ("nut", "uncertain", "", {"nut"}),
        ("nut", "independent_object", "threaded hole not visible", {"nut"}),
    ],
)
def test_conflicts_null_original_and_known_new_class_without_recount(part, status, issue, blocked):
    base = base_observation()
    targets = probe.select_targets(base)
    response = reply(targets)
    response.objects[0] = probe.IdentityItem(id="p002", part=part, status=status, issue=issue)
    filtered, guard = probe.apply_guard(base, targets, response)
    assert {p for p, count in filtered["observed"].items() if count is None} == blocked
    assert set(filtered["object_evidence"]["uncertain_parts"]) == blocked
    assert filtered["object_evidence"]["objects"] == base["object_evidence"]["objects"]
    assert filtered["action"]["kind"] == "recapture" and filtered["issues"]
    assert not guard["integer_counts_reassigned"]
    Observation.model_validate(filtered)


@pytest.mark.parametrize(
    "size,point",
    [
        ((32, 32), [0.0, 0.0]),
        ((32, 80), [1.0, 1.0]),
        ((100, 1000), [0.5, 0.5]),
        ((2048, 1536), [1.0, 0.0]),
        ((2048, 1536), [0.5, 0.5]),
    ],
)
def test_crops_stay_inside_image_and_have_at_least_32_pixels(size, point):
    left, top, right, bottom = probe.crop_bounds(size, point)
    assert 0 <= left < right <= size[0] and 0 <= top < bottom <= size[1]
    assert right - left >= 32 and bottom - top >= 32
    assert left <= point[0] * (size[0] - 1) < right
    assert top <= point[1] * (size[1] - 1) < bottom
    if point == [0.5, 0.5] and min(size) > 134:
        assert abs((right - left) - 0.24 * min(size)) <= 2


@pytest.mark.parametrize(
    "center", [[True, 0.5], [float("nan"), 0.5], [float("inf"), 0.5], [-0.1, 0.5], [0.1, 1.1]]
)
def test_invalid_coordinates_fail_closed(center):
    with pytest.raises(ValueError):
        probe.crop_bounds((300, 200), center)


def test_raw_and_resized_crops_have_separate_provenance_and_actual_positions(tmp_path):
    source = tmp_path / "source.jpg"
    Image.new("RGB", (100, 80), "white").save(source)
    target = {"id": "p001", "original_part": "nut", "center": [1.0, 0.0]}
    crops = probe.save_crops(source, [target], tmp_path)
    crop = crops[0]
    assert max(crop["crop_size"]) == 512
    assert crop["crop_source_size"] == [32, 32]
    assert crop["target_center_crop"] == [1.0, 0.0]
    assert crop["pixel_crop_sha256"] == probe.file_sha256(Path(crop["pixel_crop_file"]))
    assert crop["crop_sha256"] == probe.file_sha256(Path(crop["crop_file"]))
    assert crop["pixel_crop_sha256"] != crop["crop_sha256"]
    assert not crop["interpolation_creates_information"]


def test_prompt_only_contains_ids_and_coordinates_not_labels_truth_or_bom():
    crops = [
        {
            "id": "p002",
            "center": [0.7, 0.8],
            "target_center_crop": [0.5, 0.5],
            "original_part": "SECRET_LABEL",
            "ground_truth": "SECRET_TRUTH",
            "requirements": "SECRET_BOM",
            "crop_file": "SECRET_FILENAME",
        }
    ]
    prompt = probe.build_prompt(crops)
    assert "SECRET_" not in prompt
    assert all(word not in prompt for word in ("nut", "washer", "ground_truth", "requirements"))
    assert set(json.loads(prompt.split("Points:\n", 1)[1])[0]) == {
        "id",
        "image",
        "center_in_full_image",
        "center_in_crop",
    }
    assert "split/spring lock washers" in probe.SYSTEM_PROMPT
    assert "round or knurled" in probe.SYSTEM_PROMPT
    assert "Nearby objects alone do not" in probe.SYSTEM_PROMPT


def test_guard_cannot_be_called_to_recover_unclear_or_omit_candidates():
    base = base_observation()
    targets = probe.select_targets(base)
    with pytest.raises(ValueError, match="exactly"):
        probe.apply_guard(base, targets[:1], reply(targets[:1]))
    with pytest.raises(ValueError, match="exactly"):
        probe.apply_guard(base_observation(uncertain=True), targets, reply(targets))


def test_calls_once_on_worker_with_full_and_all_crops_preserving_base(tmp_path):
    source, base = row_fixture(tmp_path)
    targets = probe.select_targets(base["observation"])
    engine = CPUVision(reply(targets))
    row = probe.run_case(engine, case_fixture(), base, source, tmp_path, 1, 1800)
    assert row["error"] is None
    assert len(engine.calls) == 1 and len(engine.calls[0]["images"]) == 3
    assert engine.calls[0]["thread"].startswith("kitguard-mlx")
    assert engine.calls[0]["max_tokens"] == 1800
    assert row["base_observation"] == base["observation"]
    assert "verification" not in row["observation"]
    assert row["base_latency_ms"] == 700
    assert row["latency_ms"] == 700 + row["identity_elapsed_ms"]
    assert row["identity_call_wall_ms"] is not None and row["identity_cold_load_seconds"] == 0.01
    assert row["identity_inference_seconds"] == 0.001
    assert row["counts_exact"] and row["actionable_counts"]
    assert all(probe.file_sha256(tmp_path / item["file"]) == item["sha256"] for item in row["inputs"])


@pytest.mark.parametrize("kind", ["unclear", "base_error", "no_candidates"])
def test_ineligible_rows_never_call_model_or_restore_clear(tmp_path, kind):
    if kind == "no_candidates":
        base = base_observation([{"part": "bolt", "center": [0.5, 0.5]}])
    else:
        base = base_observation(uncertain=kind == "unclear")
    source, original = row_fixture(tmp_path, base)
    if kind == "base_error":
        original["error"] = "RecordedModelFailure"
        original["observation"] = None
    engine = CPUVision(error=AssertionError("Must not execute"))
    row = probe.run_case(engine, case_fixture(), original, source, tmp_path, 1, 1800)
    assert not engine.calls and not row["model_called"]
    if kind != "no_candidates":
        assert not row["actionable_counts"]
    assert row["experimental_identity_guard"]["status"].startswith("skipped_")


@pytest.mark.parametrize("failure", [RuntimeError("CPU execution failure"), ValueError("CPU malformed IDs")])
def test_model_errors_never_fall_back_to_clear_base_and_remain_denominator(tmp_path, failure):
    source, base = row_fixture(tmp_path)
    row = probe.run_case(CPUVision(error=failure), case_fixture(), base, source, tmp_path, 1, 1800)
    assert row["error"] and row["observation"] is None and row["base_observation"]
    assert row["experimental_identity_guard"]["status"] == "execution_error"
    assert not row["actionable_counts"]
    summary = probe.comparison_summary([row], [case_fixture()], [base])
    assert summary["filtered"]["images"] == 1 and summary["filtered"]["errors"]["numerator"] == 1
    assert summary["correct_actionable_blocked"] == 1


def test_incomplete_model_ids_are_execution_error_not_pass(tmp_path):
    source, base = row_fixture(tmp_path)
    response = reply(probe.select_targets(base["observation"])[:1])
    row = probe.run_case(CPUVision(response), case_fixture(), base, source, tmp_path, 1, 1800)
    assert row["error"] and row["observation"] is None


def test_changed_full_input_hash_prevents_model_call(tmp_path):
    source, base = row_fixture(tmp_path)
    base["observation"]["verification"]["passes"][0]["input_sha256"] = "d" * 64
    engine = CPUVision()
    row = probe.run_case(engine, case_fixture(), base, source, tmp_path, 1, 1800)
    assert row["error"] and "differs" in row["error"] and not engine.calls


def create_source_run(tmp_path):
    directory = tmp_path / "base"
    directory.mkdir()
    (directory / "normalized_inputs").mkdir()
    rows, cases = [], []
    for i, identifier in enumerate(probe.SCREWS_IDS, 1):
        case = {**case_fixture(), "id": identifier, "source_id": f"engineering:{i}"}
        path = directory / "normalized_inputs" / f"{i:03d}.jpg"
        Image.new("RGB", (64, 48), (i, 50, 100)).save(path)
        cases.append(case)
        rows.append(
            {
                **case,
                "case_id": identifier,
                "latency_ms": 0,
                "input_pipeline": "app-upload",
                "model_input_sha256": probe.file_sha256(path),
                "observation": None,
                "error": "CPU fixture error",
            }
        )
    manifest = directory / "manifest.json"
    manifest.write_text(
        probe.json_text({"cases": cases + [{"id": "DO_NOT_OPEN", "split": "holdout", "image": "/NO_FILE"}]})
    )
    metadata = {
        "split": "development",
        "status": "completed",
        "source_changed_during_run": False,
        "input_pipeline": "app-upload",
        "model_before": {
            **probe.PROFILES[probe.PROFILE],
            "observation_mode": "spatial_consensus",
            "image_max_side": 1536,
        },
        "case_ids": list(probe.SCREWS_IDS),
        "expected_cases": 12,
        "completed_cases": 12,
        "manifest_sha256": probe.file_sha256(manifest),
    }
    (directory / "run.json").write_text(probe.json_text(metadata))
    (directory / "predictions.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return directory


def test_loader_validates_development_pixels_and_ignores_holdout_images(tmp_path):
    directory = create_source_run(tmp_path)
    _metadata, rows, cases, paths = probe.load_source_run(directory)
    assert len(rows) == len(cases) == len(paths) == 12
    assert all(case["split"] == "development" for case in cases)


@pytest.mark.parametrize(
    "key,value",
    [
        ("split", "holdout"),
        ("status", "running"),
        ("source_changed_during_run", True),
        ("completed_cases", 11),
    ],
)
def test_loader_rejects_nonfixed_or_noncompleted_inputs(tmp_path, key, value):
    directory = create_source_run(tmp_path)
    file = directory / "run.json"
    metadata = json.loads(file.read_text())
    metadata[key] = value
    file.write_text(probe.json_text(metadata))
    with pytest.raises(ValueError):
        probe.load_source_run(directory)


def test_loader_rejects_changed_normalized_pixels(tmp_path):
    directory = create_source_run(tmp_path)
    (directory / "normalized_inputs/001.jpg").write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        probe.load_source_run(directory)


def test_validate_only_never_constructs_model_or_creates_output(tmp_path, monkeypatch):
    directory = create_source_run(tmp_path)
    output = tmp_path / "must-not-exist"
    monkeypatch.setattr(
        sys, "argv", ["probe", "--run", str(directory), "--output", str(output), "--validate-only"]
    )
    monkeypatch.setattr(probe, "RecordingVision", lambda *a, **kw: pytest.fail("Model constructed"))
    assert probe.main() == 0 and not output.exists()


def test_existing_output_rejected_before_source_read(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["probe", "--run", "nonexistent", "--output", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        probe.main()
    assert exc.value.code == 2


@pytest.mark.parametrize("text", ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'])
def test_strict_json_rejects_duplicates_and_nonfinite(text):
    with pytest.raises(ValueError):
        probe.strict_loads(text)
