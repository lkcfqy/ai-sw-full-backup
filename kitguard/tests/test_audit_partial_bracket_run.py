"""Independent CPU audit of synthetic runs; these are not model accuracy tests."""

import importlib.util
import json
from pathlib import Path

import pytest
from test_partial_bracket_benchmark import cpu_engine, execute, runner
from test_partial_bracket_benchmark import plan as plan  # noqa: PLC0414 -- pytest fixture re-export

PATH = Path(__file__).resolve().parents[1] / "scripts/audit_partial_bracket_run.py"
spec = importlib.util.spec_from_file_location("partial_auditor", PATH)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


@pytest.fixture
def completed(plan, monkeypatch):
    manifest = runner.read_json(plan["manifest"])
    for case in manifest["cases"]:
        count = case["ground_truth"]["bracket"]
        label = plan["dataset"] / (case["id"] + ".txt")
        label.write_text("0 0.5 0.5 0.5 0.6\n" if count == 1 else "0 0.25 0.5 0.35 0.6\n0 0.75 0.5 0.35 0.6\n")
        case.update(source_image=case["image"], source_image_sha256=case["sha256"],
                    annotation=label.name, annotation_sha256=runner.file_sha256(label),
                    roi_xyxy=[0, 0, 96, 64], view_kind="full_image", author_class_id=0)
    runner.write_json(plan["manifest"], manifest)
    freeze = runner.read_json(plan["freeze"])
    freeze["manifest_sha256"] = runner.file_sha256(plan["manifest"])
    runner.write_json(plan["freeze"], freeze)
    engine, _ = cpu_engine(monkeypatch)
    execute(plan, engine)
    return plan


def run_audit(plan):
    return audit.audit_run(plan["output"], plan["dataset"], plan["manifest"], plan["freeze"])


def test_complete_cpu_run_independently_reconstructed_and_scored(completed):
    report = run_audit(completed)
    assert report["passed"], report["failures"]
    assert report["independent_summary"]["outcomes"] == {"C_b": 2, "W_b": 1, "U_b": 0, "E": 0}
    assert report["independent_summary"]["constant_one_baseline"]["correct"] == 2
    assert report["checks"] > 200
    assert all(record["png_files_verified"] == 2 for record in report["input_reconstruction"])
    assert "run_partial_bracket_benchmark" not in PATH.read_text().split("from ")[0]  # No runner import.


@pytest.mark.parametrize("target", ["predictions", "summary", "snapshot", "normalized", "prepared", "generation_input"])
def test_detects_tampering_with_independent_evidence(completed, target):
    root = completed["output"]
    if target == "predictions":
        path = root / "predictions.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[0]["outcome"] = "W_b"
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    elif target == "summary":
        path = root / "run.json"
        metadata = audit.load(path)
        metadata["summary"]["constant_one_baseline"]["correct"] = 3
        runner.write_json(path, metadata)
    elif target == "snapshot":
        path = root / "source_snapshot/kitguard/vision.py"
        path.write_text(path.read_text() + "\n# CPU tamper fixture\n")
    elif target == "normalized":
        path = root / "normalized_inputs/001.jpg"
        path.write_bytes(path.read_bytes() + b"changed")
    elif target == "prepared":
        path = root / "case_artifacts/001/inspection.png"
        path.write_bytes(path.read_bytes() + b"changed")
    elif target == "generation_input":
        path = root / "case_artifacts/001/artifacts.json"
        record = audit.load(path)
        record["calls"][0]["images"][0]["sha256"] = "0" * 64
        runner.write_json(path, record)
    report = run_audit(completed)
    assert not report["passed"] and report["failures"]


def test_refuses_a_still_running_experiment(completed):
    path = completed["output"] / "run.json"
    metadata = audit.load(path)
    metadata["status"] = "running"
    runner.write_json(path, metadata)
    with pytest.raises(ValueError, match="still active"):
        run_audit(completed)


def test_partial_ground_truth_clarity_has_no_unlabeled_correctness_claim():
    inventory = {"objects": [{"part": "bracket"}], "uncertain_parts": ["nut"], "issues": ["nut unclear"],
                 "action": {"kind": "recapture"}}
    assert audit.inventory_counts(inventory) == {"bolt": 0, "nut": None, "washer": 0, "bracket": 1}
    assert audit.outcome(1, 1) == "C_b" and audit.outcome(None, 1) == "U_b"
    with pytest.raises(ValueError):
        audit.outcome(True, 1)
