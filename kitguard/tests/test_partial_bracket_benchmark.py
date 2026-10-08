"""CPU-only protocol/runner tests. Synthetic images do not establish model accuracy."""

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from kitguard.spatial import SpatialInventory
from kitguard.vision import LocalVision

RUNNER = Path(__file__).resolve().parents[1] / "scripts" / "run_partial_bracket_benchmark.py"
spec = importlib.util.spec_from_file_location("partial_bracket_runner", RUNNER)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@pytest.fixture
def plan(tmp_path):
    dataset = tmp_path / "datasets"
    dataset.mkdir()
    cases = []
    for index, truth in enumerate((1, 2, 1), start=1):
        image = dataset / f"{index}.png"
        Image.new("RGB", (96, 64), (index * 30, 0, 0)).save(image)
        cases.append({
            "id": f"case-{index}", "source_id": f"A/{index}", "author_group": "A",
            "image": image.name, "sha256": runner.file_sha256(image),
            "view_kind": "full_image" if index == 1 else "author_box_roi",
            "ground_truth": {"bracket": truth}, "unlabeled_categories": list(runner.UNLABELED),
        })
    manifest = tmp_path / "manifest.json"
    runner.write_json(manifest, {"schema_version": 1, "label_scope": runner.LABEL_SCOPE, "cases": cases})
    freeze = tmp_path / "freeze.json"
    runner.write_json(freeze, {
        "schema_version": 1, "protocol": runner.PROTOCOL,
        "frozen_at": "2026-09-26T00:00:00+00:00",
        "manifest_sha256": runner.file_sha256(manifest), "runner_sha256": runner.file_sha256(RUNNER),
        "method_source_hashes": runner.source_hashes(),
        "model": {"profile": runner.MODEL_PROFILE, "revision": runner.MODEL_REVISION},
        "observation_mode": "spatial_guarded", "image_max_side": 1536,
        "input_pipeline": "app-upload", "label_scope": runner.LABEL_SCOPE,
        "case_ids": [case["id"] for case in cases], "expected_cases": len(cases),
        "fixed_observer_requirements": dict(runner.FIXED_REQUIREMENTS),
    })
    return {"dataset": dataset, "manifest": manifest, "freeze": freeze, "cases": cases,
            "output": tmp_path / "result"}


def cpu_engine(monkeypatch, responses=None):
    engine = LocalVision(observation_mode="spatial_guarded", image_max_side=1536)
    calls = []
    responses = iter(responses) if responses else None

    def generate(system, prompt, images, schema, *, max_tokens):
        calls.append({"system": system, "prompt": prompt, "images": list(images)})
        response = next(responses) if responses else {"objects": [{"part": "bracket", "center": [.5, .5]}],
                    "uncertain_parts": [], "issues": [], "action": {"kind": "none", "message": "CPU fixture"}}
        if isinstance(response, Exception):
            raise response
        return schema.model_validate(response)

    monkeypatch.setattr(engine, "_generate", generate)
    return engine, calls


def execute(plan, engine, normalizer=runner.app_upload_bytes):
    return runner.execute_run(plan["manifest"], plan["dataset"], plan["output"], plan["freeze"],
                              engine_factory=lambda: engine, normalizer=normalizer)


def predictions(plan):
    return [json.loads(line) for line in (plan["output"] / "predictions.jsonl").read_text().splitlines()]


def test_actual_upload_capture_partial_scores_and_truth_blindness(plan, monkeypatch):
    engine, calls = cpu_engine(monkeypatch)
    requirements = []
    actual_observe = engine.observe

    def observe(path, supplied, references):
        requirements.append(copy.deepcopy(supplied))
        assert references == {}
        return actual_observe(path, supplied, references)

    monkeypatch.setattr(engine, "observe", observe)
    metadata = execute(plan, engine)
    rows = predictions(plan)
    assert metadata["status"] == "completed" and metadata["valid_frozen_run"]
    assert metadata["summary"]["outcomes"] == {"C_b": 2, "W_b": 1, "U_b": 0, "E": 0}
    assert metadata["summary"]["constant_one_baseline"]["correct"] == 2
    assert metadata["summary"]["by_view_kind"]["author_box_roi"]["cases"] == 2
    assert requirements == [runner.FIXED_REQUIREMENTS] * 3
    assert len({(call["system"], call["prompt"]) for call in calls}) == 1
    for row, case in zip(rows, plan["cases"], strict=True):
        assert row["ground_truth"] == case["ground_truth"] and set(row["ground_truth"]) == {"bracket"}
        assert "tasks" not in row and "counts_exact" not in row and "ready" not in row
        assert row["first_pass_bracket"] == 1 and row["app_clear"] is True
        assert row["source_sha256_before"] == row["source_sha256_after"] == case["sha256"]
        normalized = plan["output"] / row["normalized_input"]
        assert normalized.read_bytes().startswith(b"\xff\xd8")
        assert runner.file_sha256(normalized) == row["model_input_sha256"] == row["model_input_sha256_after"]
        artifacts = json.loads((plan["output"] / row["case_artifacts"] / "artifacts.json").read_text())
        assert {item["file"] for item in artifacts["files"]} == {"inspection.png", "inspection-rotated.png"}
        for item in artifacts["files"]:
            assert runner.file_sha256(plan["output"] / row["case_artifacts"] / item["file"]) == item["sha256"]
        assert len(artifacts["calls"]) == 2
        assert all(call["status"] == "completed" for call in artifacts["calls"])
    assert (plan["output"] / "observation_schema.json").is_file()
    assert (plan["output"] / "source_snapshot/scripts" / RUNNER.name).is_file()
    for relative, digest in runner.source_hashes().items():
        assert runner.file_sha256(plan["output"] / "source_snapshot" / relative) == digest


@pytest.mark.parametrize("mutator", [
    lambda c: c[0]["ground_truth"].update(bolt=0),
    lambda c: c[0]["ground_truth"].update(bracket=True),
    lambda c: c[0]["ground_truth"].update(bracket=0),
    lambda c: c[0].update(unlabeled_categories=[]),
    lambda c: c[1].update(source_id=c[0]["source_id"]),
    lambda c: c[1].update(id=c[0]["id"]),
    lambda c: c[0].update(sha256="bad"),
    lambda c: c[0].update(sha256="0" * 64),
    lambda c: c[0].update(image="../manifest.json"),
    lambda c: c[0].update(image="/etc/passwd"),
])
def test_rejects_invalid_partial_plan(plan, mutator):
    manifest = runner.read_json(plan["manifest"])
    mutator(manifest["cases"])
    with pytest.raises(ValueError):
        runner.validate_manifest(manifest, plan["dataset"])


def test_rejects_symlink_escape(plan, tmp_path):
    link = plan["dataset"] / "outside.png"
    link.symlink_to(plan["manifest"])
    case = {**plan["cases"][0], "image": link.name, "sha256": runner.file_sha256(link)}
    with pytest.raises(ValueError, match="escapes"):
        runner.checked_image(case, plan["dataset"])


@pytest.mark.parametrize("key,value", [
    ("runner_sha256", "0" * 64), ("manifest_sha256", "0" * 64),
    ("method_source_hashes", {}), ("case_ids", []), ("expected_cases", 2),
    ("input_pipeline", "original"), ("observation_mode", "single"), ("image_max_side", 1024),
    ("fixed_observer_requirements", {"bracket": 1}), ("model", {"profile": "other"}),
])
def test_freeze_checks_full_method_and_plan(plan, key, value):
    freeze = runner.read_json(plan["freeze"])
    freeze[key] = value
    runner.write_json(plan["freeze"], freeze)
    with pytest.raises(ValueError, match=f"Freeze mismatch: {key}"):
        runner.validate_configuration(plan["manifest"], plan["dataset"], plan["freeze"])


def test_validation_cli_does_not_import_any_model_or_application(plan):
    # -S removes site packages: this fails if even pydantic/Pillow/model/app is imported.
    command = [sys.executable, "-S", str(RUNNER), "--manifest", str(plan["manifest"]),
               "--dataset-root", str(plan["dataset"]), "--freeze", str(plan["freeze"]),
               "--output", str(plan["output"]), "--validate-only"]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "validated_without_model_import"
    assert not plan["output"].exists()
    result = subprocess.run(command[:-1], capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert "Select exactly one" in result.stderr


def test_startup_failure_preserves_every_planned_case_without_retry(plan):
    starts = []

    def unavailable():
        starts.append(1)
        raise RuntimeError("CPU simulated unavailable model")

    metadata = runner.execute_run(plan["manifest"], plan["dataset"], plan["output"], plan["freeze"],
                                  engine_factory=unavailable)
    assert starts == [1]
    assert metadata["summary"]["outcomes"] == {"C_b": 0, "W_b": 0, "U_b": 0, "E": 3}
    assert metadata["completed_cases"] == 3
    assert [r["id"] for r in predictions(plan)] == [c["id"] for c in plan["cases"]]
    assert all(r["app_clear"] is None and r["first_pass_outcome"] is None for r in predictions(plan))


def test_rotation_failure_keeps_original_pass_but_is_error(plan, monkeypatch):
    inventory = {"objects": [{"part": "bracket", "center": [.5, .5]}], "uncertain_parts": [],
                 "issues": [], "action": {"kind": "none", "message": "CPU fixture"}}
    engine, calls = cpu_engine(monkeypatch, [inventory, RuntimeError("second pass failed")] * 3)
    metadata = execute(plan, engine)
    rows = predictions(plan)
    assert len(calls) == 6 and metadata["summary"]["outcomes"]["E"] == 3
    assert [row["first_pass_outcome"] for row in rows] == ["C_b", "W_b", "C_b"]
    assert all(row["first_pass_bracket"] == 1 and row["outcome"] == "E" for row in rows)
    assert metadata["summary"]["paired_first_final"]["transitions"]["C_b->E"] == 2
    assert all(row["observation_diagnostics"]["passes"][0]["transform"] == "original" for row in rows)


def test_source_change_during_observation_is_error(plan, monkeypatch):
    engine, _ = cpu_engine(monkeypatch)
    original = engine.observe
    counter = iter(plan["cases"])

    def mutate(path, supplied, references):
        result = original(path, supplied, references)
        (plan["dataset"] / next(counter)["image"]).write_bytes(b"changed source")
        return result

    monkeypatch.setattr(engine, "observe", mutate)
    metadata = execute(plan, engine)
    assert metadata["summary"]["outcomes"]["E"] == 3
    assert metadata["input_changed_during_run"] and not metadata["valid_frozen_run"]
    assert all("InputIntegrityError" in row["error"] for row in predictions(plan))


def test_fresh_output_only(plan, monkeypatch):
    plan["output"].mkdir()
    (plan["output"] / "previous.txt").write_text("retain me")
    engine, _ = cpu_engine(monkeypatch)
    with pytest.raises(FileExistsError):
        execute(plan, engine)
    assert (plan["output"] / "previous.txt").read_text() == "retain me"


def test_unknown_bracket_is_not_execution_error_and_other_unknowns_only_affect_clarity():
    base = {"observed": {"bolt": None, "nut": 0, "washer": 0, "bracket": 1},
            "issues": ["bolt unclear"], "action": {"kind": "recapture"},
            "verification": {"passes": [{"observed": {"bracket": 1}}]}}
    row = runner.score_partial({"ground_truth": {"bracket": 1}}, base, None)
    assert row["outcome"] == "C_b" and row["app_clear"] is False
    base["observed"]["bracket"] = None
    row = runner.score_partial({"ground_truth": {"bracket": 1}}, base, None)
    assert row["outcome"] == "U_b" and row["first_pass_outcome"] == "C_b"


def test_invalid_observation_is_error_for_each_case(plan, monkeypatch):
    engine, _ = cpu_engine(monkeypatch)
    monkeypatch.setattr(engine, "observe", lambda *args: {"observed": {"bracket": 1}})
    metadata = execute(plan, engine)
    assert metadata["summary"]["outcomes"]["E"] == 3
    assert all("ValidationError" in row["error"] for row in predictions(plan))


def test_invalid_non_json_output_still_persists_all_errors(plan, monkeypatch):
    engine, _ = cpu_engine(monkeypatch)
    monkeypatch.setattr(engine, "observe", lambda *args: {
        "observed": {"bracket": float("nan")}, "invalid_object": object(),
    })
    metadata = execute(plan, engine)
    rows = predictions(plan)
    assert metadata["summary"]["outcomes"]["E"] == 3
    assert len(rows) == metadata["recorded_cases"] == 3
    assert rows[0]["observation"]["observed"]["bracket"] == {"non_json_float": "nan"}
    assert rows[0]["observation"]["invalid_object"]["non_json_type"] == "object"


def test_interrupt_keeps_fixed_denominator_with_explicit_unexecuted_rows(plan, monkeypatch):
    engine, _ = cpu_engine(monkeypatch)
    original = engine.observe
    calls = []

    def interrupt_second(*args):
        calls.append(1)
        if len(calls) == 2:
            raise KeyboardInterrupt
        return original(*args)

    monkeypatch.setattr(engine, "observe", interrupt_second)
    with pytest.raises(KeyboardInterrupt):
        execute(plan, engine)
    metadata = runner.read_json(plan["output"] / "run.json")
    rows = predictions(plan)
    assert metadata["status"] == "interrupted" and not metadata["valid_frozen_run"]
    assert metadata["summary"]["planned_cases"] == metadata["expected_cases"] == 3
    assert metadata["summary"]["outcomes"] == {"C_b": 1, "W_b": 0, "U_b": 0, "E": 2}
    assert metadata["summary"]["author_bracket_count_agreement_fraction"] == 1 / 3
    assert metadata["completed_cases"] == 1 and metadata["recorded_cases"] == 3
    assert metadata["summary"]["pipeline_latency_n"] == 1
    assert metadata["summary"]["median_pipeline_latency_ms"] == rows[0]["elapsed_ms"]
    assert all(row["execution_status"] == "not_executed_or_not_recorded" for row in rows[1:])
    assert all(row["elapsed_ms"] is None for row in rows[1:])


def test_source_hash_change_invalidates_freeze_even_with_correct_predictions(plan, monkeypatch):
    engine, _ = cpu_engine(monkeypatch)
    original = engine.observe
    hashes = runner.source_hashes()

    def change_fingerprint(*args):
        result = original(*args)
        monkeypatch.setattr(runner, "source_hashes", lambda: {**hashes, "kitguard/vision.py": "0" * 64})
        return result

    monkeypatch.setattr(engine, "observe", change_fingerprint)
    metadata = execute(plan, engine)
    assert metadata["source_changed_during_run"] and not metadata["valid_frozen_run"]


def test_capture_retains_identity_pixel_crop_even_when_generation_fails(tmp_path):
    class Stub:
        def _generate(self, *args, **kwargs):
            raise RuntimeError("CPU failure")

    engine = Stub()
    capture = runner.GenerationCapture(engine)
    capture.start(tmp_path / "saved")
    prepared = tmp_path / "temporary"
    prepared.mkdir()
    for name in ("inspection.png", "identity-crop-1.png", "identity-pixels-1.png"):
        Image.new("RGB", (30, 30)).save(prepared / name)
    with pytest.raises(RuntimeError):
        engine._generate("system", "prompt", [str(prepared / "inspection.png"),
                         str(prepared / "identity-crop-1.png")], SpatialInventory, max_tokens=1800)
    data = runner.read_json(tmp_path / "saved" / "artifacts.json")
    assert len(data["files"]) == 3 and data["calls"][0]["status"] == "error"
