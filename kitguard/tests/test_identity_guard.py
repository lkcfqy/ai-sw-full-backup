"""CPU-only candidate guard contracts and fixed development replay; no holdout reads."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from kitguard import identity

ROOT = Path(__file__).resolve().parents[1]
DEVELOPMENT_RUN = ROOT / "evaluation-runs/v03_screws_identity_geometry_v2"
BASE_INPUTS = ROOT / "evaluation-runs/v03_screws_development_v1/normalized_inputs"


def base_input():
    objects = [
        {"part": "bolt", "center": [0.2, 0.4]},
        {"part": "nut", "center": [0.7, 0.8]},
        {"part": "washer", "center": [0.5, 0.5]},
    ]
    counts = {"bolt": 1, "nut": 1, "washer": 1, "bracket": 0}
    action = {"kind": "none", "message": "SYNTHETIC CPU FIXTURE", "region": None}
    return {
        "observed": dict(counts),
        "issues": [],
        "action": copy.deepcopy(action),
        "object_evidence": {
            "protocol": "spatial_inventory_v1",
            "coordinate_frame": "normalized_original",
            "objects": copy.deepcopy(objects),
            "uncertain_parts": [],
        },
        "verification": {
            "mode": "spatial_consensus",
            "same_model_correlated_calls": True,
            "counts_agree": True,
            "clear_agreement": True,
            "passes": [
                {
                    "transform": transform,
                    "input_sha256": "a" * 64,
                    "observed": dict(counts),
                    "issues": [],
                    "action": copy.deepcopy(action),
                    "objects": copy.deepcopy(objects),
                    "uncertain_parts": [],
                }
                for transform in ("original", "rotate_90_ccw")
            ],
        },
    }


def response(targets):
    return {
        "objects": [
            {
                "id": t["id"],
                "part": t["original_part"],
                "status": "independent_object",
                "opening": "through_hole",
                "issue": "",
            }
            for t in targets
        ]
    }


def obstacle_base():
    base = base_input()
    second = base["verification"]["passes"][1]
    second["objects"] = [o for o in second["objects"] if o["part"] != "washer"]
    second["observed"]["washer"] = 0
    base["verification"].update(counts_agree=False, clear_agreement=False)
    base["observed"]["washer"] = None
    base["object_evidence"]["uncertain_parts"] = ["washer"]
    base["issues"] = ["SYNTHETIC directional disagreement"]
    base["action"]["kind"] = "recapture"
    return base


def test_candidate_has_no_runtime_or_schema_import_and_never_loads_model():
    command = "from kitguard import identity; import sys; assert 'kitguard.vision' not in sys.modules; assert 'kitguard.schemas' not in sys.modules; assert not any(k == 'mlx' or k.startswith('mlx.') for k in sys.modules)"
    subprocess.run([sys.executable, "-c", command], cwd=ROOT, check=True, capture_output=True, text=True)


def test_original_list_indices_are_preserved_without_label_ids_or_base_metadata():
    base = base_input()
    original = copy.deepcopy(base)
    targets = identity.select_targets(base)
    assert targets == [
        {"id": "p002", "object_index": 2, "original_part": "nut", "center": [0.7, 0.8]},
        {"id": "p003", "object_index": 3, "original_part": "washer", "center": [0.5, 0.5]},
    ]
    decision = identity.apply_decision(base, targets, response(targets))
    assert decision["blocked_categories"] == []
    assert all(t["accepted"] for t in decision["targets"])
    assert base == original and "verification" in base
    assert set(decision) == {"blocked_categories", "targets"}


@pytest.mark.parametrize("fault", ["partial_targets", "reordered_targets", "unclear_base", "moved_point"])
def test_guard_cannot_skip_reorder_move_candidates_or_recover_unclear(fault):
    base = base_input()
    targets = identity.select_targets(base)
    if fault == "partial_targets":
        targets = targets[:1]
    elif fault == "reordered_targets":
        targets.reverse()
    elif fault == "unclear_base":
        base = obstacle_base()
    else:
        targets[0]["center"] = [0.1, 0.1]
    with pytest.raises(ValueError, match="exactly"):
        identity.apply_decision(base, targets, response(targets))
    assert identity.select_targets(obstacle_base()) == []


@pytest.mark.parametrize(
    "part,status,opening,issue,blocked",
    [
        ("washer", "independent_object", "through_hole", "", ["nut", "washer"]),
        ("bolt", "attached_feature", "closed_recess", "attached head", ["bolt", "nut"]),
        ("unknown", "uncertain", "uncertain", "unclear hole", ["nut"]),
        ("nut", "no_object", "not_applicable", "reflection", ["nut"]),
        ("nut", "uncertain", "through_hole", "", ["nut"]),
        ("nut", "independent_object", "through_hole", "threading not visible", ["nut"]),
        # Frozen v2 does not impose the washer-only through-hole rule on nuts.
        ("nut", "independent_object", "uncertain", "", []),
    ],
)
def test_conflicts_block_original_and_known_conflicting_category_only(part, status, opening, issue, blocked):
    base = base_input()
    targets = identity.select_targets(base)
    reply = response(targets)
    before = copy.deepcopy(base)
    reply["objects"][0].update(part=part, status=status, opening=opening, issue=issue)
    result = identity.apply_decision(base, targets, reply)
    assert result["blocked_categories"] == blocked
    assert base == before
    assert result["targets"][0]["blocked_categories"] == blocked
    assert result["targets"][1]["accepted"]


@pytest.mark.parametrize("opening", ["closed_recess", "uncertain", "not_applicable"])
def test_washer_requires_visible_through_hole(opening):
    base = base_input()
    targets = identity.select_targets(base)
    reply = response(targets)
    reply["objects"][1]["opening"] = opening
    assert identity.apply_decision(base, targets, reply)["blocked_categories"] == ["washer"]


def test_response_order_is_not_identity_and_whitespace_issue_matches_frozen_policy():
    base = base_input()
    targets = identity.select_targets(base)
    reply = response(targets)
    reply["objects"][0]["issue"] = " \n "
    reply["objects"].reverse()
    result = identity.apply_decision(base, targets, reply)
    assert not result["blocked_categories"]
    assert [t["id"] for t in result["targets"]] == ["p002", "p003"]


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "extra",
        "duplicate",
        "too_many",
        "extra_key",
        "string_issue",
        "missing_opening",
        "bad_id",
        "constructed_mutation",
    ],
)
def test_response_payload_is_strict_bounded_and_exactly_covers_targets(fault):
    targets = identity.select_targets(base_input())
    reply = response(targets)
    if fault == "missing":
        reply["objects"].pop()
    elif fault == "extra":
        reply["objects"].append({**reply["objects"][0], "id": "p020"})
    elif fault == "duplicate":
        reply["objects"].append(reply["objects"][0])
    elif fault == "too_many":
        reply["objects"] = [{**reply["objects"][0], "id": f"p{i:03d}"} for i in range(21)]
    elif fault == "extra_key":
        reply["objects"][0]["count"] = 1
    elif fault == "string_issue":
        reply["objects"][0]["issue"] = False
    elif fault == "missing_opening":
        reply["objects"][0].pop("opening")
    elif fault == "bad_id":
        reply["objects"][0]["id"] = "../../escape"
    else:
        reply = identity.IdentityResponse.model_validate(reply)
        reply.objects[0].issue = 123
    with pytest.raises(ValueError):
        identity.validate_response(reply, targets)


@pytest.mark.parametrize(
    "fault",
    [
        "extra_bom",
        "extra_object",
        "many_objects",
        "bool_center",
        "nan_center",
        "wrong_count",
        "forged_clear",
        "rotated_first",
        "string_flag",
        "duplicate_uncertainty",
        "bad_source_hash",
    ],
)
def test_base_and_saved_spatial_evidence_are_strict(fault):
    base = base_input()
    if fault == "extra_bom":
        base["requirements"] = {"nut": 1}
    elif fault == "extra_object":
        base["verification"]["passes"][0]["objects"][0]["label"] = "bolt"
    elif fault == "many_objects":
        base["verification"]["passes"][0]["objects"] *= 8
    elif fault == "bool_center":
        base["verification"]["passes"][0]["objects"][0]["center"] = [True, 0.5]
    elif fault == "nan_center":
        base["verification"]["passes"][0]["objects"][0]["center"] = [float("nan"), 0.5]
    elif fault == "wrong_count":
        base["observed"]["nut"] = 2
    elif fault == "forged_clear":
        base["verification"]["clear_agreement"] = False
    elif fault == "rotated_first":
        base["verification"]["passes"].reverse()
    elif fault == "string_flag":
        base["verification"]["counts_agree"] = "true"
    elif fault == "duplicate_uncertainty":
        base["object_evidence"]["uncertain_parts"] = ["nut", "nut"]
    else:
        base["verification"]["passes"][0]["input_sha256"] = "invalid"
    with pytest.raises(ValueError):
        identity.select_targets(base)


@pytest.mark.parametrize(
    "size,center",
    [
        ((31, 50), [0.5, 0.5]),
        ((True, 50), [0.5, 0.5]),
        ((64, 64), [False, 0.5]),
        ((64, 64), [float("nan"), 0.5]),
        ((64, 64), [float("inf"), 0.5]),
        ((64, 64), [-0.1, 0.5]),
        ((64, 64), [0.5]),
        ((64, 64, 64), [0.5, 0.5]),
    ],
)
def test_crop_bounds_reject_malformed_or_nonfinite_input(size, center):
    with pytest.raises(ValueError):
        identity.crop_bounds(size, center)


def test_edge_crop_preserves_pixels_hashes_and_projected_position(tmp_path):
    source = tmp_path / "source.jpg"
    Image.new("RGB", (80, 64), "gray").save(source)
    target = {"id": "p001", "object_index": 1, "original_part": "nut", "center": [1.0, 0.0]}
    crop = identity.save_crops(source, [target], tmp_path)[0]
    assert crop["rect_source_px"] == [48, 0, 80, 32]
    assert crop["target_center_crop"] == [1.0, 0.0]
    assert crop["crop_source_size"] == [32, 32] and crop["crop_size"] == [512, 512]
    assert crop["source_sha256"] == identity.file_sha256(source)
    with Image.open(source) as image, Image.open(crop["pixel_crop_file"]) as pixel_crop:
        assert image.convert("RGB").crop(tuple(crop["rect_source_px"])).tobytes() == pixel_crop.tobytes()
    assert crop["pixel_crop_sha256"] == identity.file_sha256(Path(crop["pixel_crop_file"]))
    assert crop["crop_sha256"] == identity.file_sha256(Path(crop["crop_file"]))
    assert not crop["interpolation_creates_information"]


def test_target_payload_cannot_write_arbitrary_paths_or_exceed_limit(tmp_path):
    source = tmp_path / "source.png"
    Image.new("RGB", (64, 64), "gray").save(source)
    target = identity.select_targets(base_input())[0]
    for mutation in (
        {"id": "../outside"},
        {"object_index": 1},
        {"original_part": "bolt"},
        {"extra": "forbidden"},
    ):
        with pytest.raises(ValueError):
            identity.save_crops(source, [{**target, **mutation}], tmp_path)
    with pytest.raises(ValueError):
        identity.save_crops(source, [target] * 21, tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["source.png"]


def test_prompt_has_no_original_labels_bom_filenames_hashes_or_quantity_fields(tmp_path):
    source = tmp_path / "SECRET_BOM_TARGET_QUANTITIES.png"
    Image.new("RGB", (96, 80), "gray").save(source)
    crops = identity.save_crops(source, identity.select_targets(base_input()), tmp_path)
    prompt = identity.build_prompt(crops)
    assert all(
        word not in prompt
        for word in (
            "SECRET",
            "nut",
            "washer",
            "original_part",
            "requirements",
            "ground_truth",
            "sha256",
            "object_index",
        )
    )
    points = json.loads(prompt.split("Points:\n", 1)[1])
    assert all(set(p) == {"id", "image", "center_in_full_image", "center_in_crop"} for p in points)
    assert [p["image"] for p in points] == [2, 3]
    crops[0]["requirements"] = {"nut": 3}
    with pytest.raises(ValueError):
        identity.build_prompt(crops)


def test_crop_metadata_rejects_forged_projection_and_unsafe_bool(tmp_path):
    source = tmp_path / "input.png"
    Image.new("RGB", (64, 64), "gray").save(source)
    crop = identity.save_crops(source, identity.select_targets(base_input())[:1], tmp_path)[0]
    for change in (
        {"target_center_crop": [0.0, 0.0]},
        {"crop_size": [511, 511]},
        {"source_sha256": "x"},
        {"interpolation_creates_information": 0},
    ):
        with pytest.raises(ValidationError):
            identity.CropMetadata.model_validate({**crop, **change})


@pytest.mark.skipif(
    not (DEVELOPMENT_RUN / "predictions.jsonl").is_file(),
    reason="Saved development replay artifacts are not distributed in every source checkout",
)
def test_frozen_screws_v2_development_prompt_schema_decisions_and_crop_bytes(tmp_path):
    # These are the explicit 12 development rows. Do not open a benchmark manifest or holdout path.
    metadata = json.loads((DEVELOPMENT_RUN / "run.json").read_text())
    assert metadata["split"] == "development" and metadata["status"] == "completed"
    assert metadata["expected_cases"] == metadata["completed_cases"] == 12
    protocol = json.loads((DEVELOPMENT_RUN / "protocol.json").read_text())
    assert identity.SYSTEM_PROMPT == protocol["system"]
    assert identity.IdentityResponse.model_json_schema() == protocol["schema"]
    rows = [json.loads(line) for line in (DEVELOPMENT_RUN / "predictions.jsonl").read_text().splitlines()]
    assert len(rows) == 12 and [r["case_id"] for r in rows] == metadata["case_ids"]
    if (ROOT / "SOURCE_MANIFEST.json").is_file() and not (BASE_INPUTS / "001.jpg").is_file():
        pytest.skip("Source-only distribution excludes photographs and crops; restore development inputs")
    crops_compared = 0
    for index, row in enumerate(rows, 1):
        assert row["split"] == "development"
        source = BASE_INPUTS / f"{index:03d}.jpg"
        assert identity.file_sha256(source) == row["normalized_input_sha256"]
        targets = identity.select_targets(row["base_observation"])
        if not row["model_called"]:
            assert not targets
            continue
        before = copy.deepcopy(row["base_observation"])
        decision = identity.apply_decision(before, targets, row["identity_response"])
        assert before == row["base_observation"]
        assert all(decision[key] == row["experimental_identity_guard"][key] for key in decision)
        output = tmp_path / f"{index:03d}"
        output.mkdir()
        crops = identity.save_crops(source, targets, output)
        assert identity.build_prompt(crops) == row["prompt"]
        assert len(crops) == len(row["crops"])
        for actual, saved in zip(crops, row["crops"], strict=True):
            assert {k: v for k, v in actual.items() if k not in ("crop_file", "pixel_crop_file")} == {
                k: v for k, v in saved.items() if k not in ("crop_file", "pixel_crop_file")
            }
            for key in ("crop_file", "pixel_crop_file"):
                assert Path(actual[key]).read_bytes() == (DEVELOPMENT_RUN / saved[key]).read_bytes()
            crops_compared += 1
    assert crops_compared == 18
