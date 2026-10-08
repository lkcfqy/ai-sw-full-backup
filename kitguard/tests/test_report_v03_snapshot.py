"""Read-only report reconciliation and isolated refresh eligibility checks; no model/images."""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
import shutil
import statistics
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    refresh = importlib.import_module("scripts.refresh_v03_report_snapshot")
finally:
    sys.path.pop(0)
REPORT = ROOT / "reports/self-evaluation/src/data.json"
FIXED_RUNS = {
    "v03_consensus_development_v1",
    "v03_screws_development_v1",
    "v03_screws_identity_probe_v1",
    "v03_screws_identity_geometry_v2",
    "v03_loco_identity_geometry_v2",
    "v03_owl_development_v1",
    "v03_grounding_dino_development_v1",
    "v03_guarded_integrated_development_v1",
}


def read_json(path):
    return json.loads(path.read_text())


def predictions(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


@pytest.mark.skipif(not REPORT.exists(), reason="Local reviewed report is not in this checkout")
def test_existing_completed_cohorts_reconcile_to_independent_raw_observation_counts():
    snapshot = read_json(REPORT)
    query = snapshot["queries"]["v03_runs"]
    selected = [row for row in query["rows"] if row["run"] in FIXED_RUNS]
    has_integrated = any(row["run"] == "v03_guarded_integrated_development_v1" for row in selected)
    assert len(selected) == (11 if has_integrated else 9)
    for row in selected:
        directory = ROOT / "evaluation-runs" / row["run"]
        run = read_json(directory / "run.json")
        assert run["status"] == "completed"
        values = [
            r
            for r in predictions(directory / "predictions.jsonl")
            if ("LOCO" if "loco" in r["source_id"] else "Screws") == row["cohort"]
        ]
        assert row["stage"] == "development"
        assert (
            len(values)
            == row["images"]
            == len({r["case_id"] for r in values})
            == len({r["source_id"] for r in values})
        )
        exact = wrong = abstained = errors = 0
        for r in values:
            error = bool(r.get("error"))
            errors += error
            if row["kind"] == "detector":
                # Grounding DINO unmapped boxes prevent full-vector exactness.
                exact += int(not error and r.get("counts") == r["ground_truth"] and not r.get("unmapped"))
                continue
            observed = r.get("observation") or {}
            counts = observed.get("observed", {})
            actionable = (
                not error
                and set(counts) == {"bolt", "nut", "washer", "bracket"}
                and all(type(n) is int for n in counts.values())
                and not observed.get("issues")
                and observed.get("action", {}).get("kind") == "none"
            )
            exact += int(actionable and counts == r["ground_truth"])
            wrong += int(actionable and counts != r["ground_truth"])
            abstained += int(not actionable and not error)
        assert row["correct"] == exact and row["errors"] == errors
        if row["kind"] == "detector":
            assert row["actionable"] is row["wrong"] is row["abstained"] is None
            assert "不含模型加载" in row["timingNote"]
        else:
            assert (row["wrong"], row["abstained"], row["actionable"]) == (wrong, abstained, exact + wrong)
            assert exact + wrong + abstained + errors == row["images"]
        if row["kind"] == "replay":
            assert "非端到端" in row["timingNote"] and "历史" in row["timingNote"]
        assert row["medianMs"] == statistics.median(r["latency_ms"] for r in values)
        for filename in ("run.json", "predictions.jsonl"):
            relative = str((directory / filename).relative_to(ROOT))
            assert relative in query["source"]["files"]
            assert (
                query["source"]["fileHashes"][relative]
                == hashlib.sha256((directory / filename).read_bytes()).hexdigest()
            )
    # Weak/rejected alternatives stay visible instead of only the selected v2.
    assert {
        "v03_screws_identity_probe_v1",
        "v03_owl_development_v1",
        "v03_grounding_dino_development_v1",
    } <= {r["run"] for r in selected}


def isolate_refresh(tmp_path, monkeypatch, name):
    original = ROOT / "evaluation-runs" / name
    if not (original / "run.json").exists():
        pytest.skip("Fixed development source is not bundled")
    run = read_json(original / "run.json")
    rows = predictions(original / "predictions.jsonl")
    assert run["status"] == "completed"
    assert all(r.get("split", "development") == "development" for r in rows)
    directory = tmp_path / "evaluation-runs" / name
    directory.mkdir(parents=True)
    # Only JSON/text records, never images or model inputs; preserve originals.
    for file in original.glob("*.json"):
        (directory / file.name).write_bytes(file.read_bytes())
    if (original / "source_snapshot").is_dir():
        shutil.copytree(original / "source_snapshot", directory / "source_snapshot")
    target = tmp_path / "data.json"
    target.write_text(
        json.dumps({"queries": {"engineering_checks": {"rows": [{}], "source": {"files": ["none"]}}}})
    )
    monkeypatch.setattr(refresh, "ROOT", tmp_path)
    monkeypatch.setattr(refresh, "TARGET", target)
    def staged_history(*, write=True):
        assert write is False
        return read_json(target)

    monkeypatch.setattr(refresh, "refresh_history", staged_history)
    return directory, target, run, rows


def write_run(directory, run, rows):
    (directory / "run.json").write_text(json.dumps(run))
    (directory / "predictions.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_running_integrated_record_never_publishes_partial_score(tmp_path, monkeypatch):
    directory, target, run, rows = isolate_refresh(tmp_path, monkeypatch, "v03_screws_identity_geometry_v2")
    run["status"] = "running"
    run["completed_cases"] = 1
    write_run(directory, run, rows[:1])
    refresh.main()
    assert read_json(target)["queries"]["v03_runs"]["rows"] == []


@pytest.mark.parametrize("name", ["v03_screws_identity_geometry_v2", "v03_grounding_dino_development_v1"])
def test_complete_unchanged_saved_development_run_can_be_promoted(tmp_path, monkeypatch, name):
    directory, target, run, rows = isolate_refresh(tmp_path, monkeypatch, name)
    write_run(directory, run, rows)
    refresh.main()
    displayed = read_json(target)["queries"]["v03_runs"]["rows"]
    assert sum(row["images"] for row in displayed) == len(rows)


@pytest.mark.parametrize(
    "fault",
    ["missing_finish", "missing_source_audit", "wrong_completed_count", "duplicate_case", "changed_input"],
)
def test_incomplete_or_ambiguous_completed_model_run_is_not_promoted(tmp_path, monkeypatch, fault):
    directory, target, run, rows = isolate_refresh(tmp_path, monkeypatch, "v03_screws_identity_geometry_v2")
    if fault == "missing_finish":
        run.pop("finished_at")
    elif fault == "missing_source_audit":
        run.pop("source_changed_during_run")
    elif fault == "wrong_completed_count":
        run["completed_cases"] -= 1
    elif fault == "duplicate_case":
        rows[1] = copy.deepcopy(rows[0])
    else:
        run["source_inputs_changed_during_run"] = True
    write_run(directory, run, rows)
    original = target.read_bytes()
    with pytest.raises((ValueError, AssertionError)):
        refresh.main()
    assert target.read_bytes() == original


@pytest.mark.parametrize(
    "fault",
    ["truncated_rows", "changed_script", "duplicate_case", "summary_denominator", "summary_numerator"],
)
def test_detector_completion_and_denominators_are_checked_before_promotion(tmp_path, monkeypatch, fault):
    directory, target, run, rows = isolate_refresh(tmp_path, monkeypatch, "v03_grounding_dino_development_v1")
    if fault == "truncated_rows":
        rows = rows[:1]
    elif fault == "changed_script":
        run["script_changed_during_run"] = True
    elif fault == "duplicate_case":
        rows[1] = copy.deepcopy(rows[0])
    elif fault == "summary_denominator":
        run["summary"]["loco"]["exact_count_denominator"] = 1
    else:
        run["summary"]["loco"]["exact_count_images"] = 16
    write_run(directory, run, rows)
    original = target.read_bytes()
    with pytest.raises((ValueError, AssertionError)):
        refresh.main()
    assert target.read_bytes() == original
