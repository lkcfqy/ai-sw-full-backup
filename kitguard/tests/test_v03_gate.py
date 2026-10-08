"""Synthetic CPU engineering fixtures; not photograph/model accuracy evidence."""

import hashlib
import json
import subprocess
import sys

import pytest

from kitguard.app import decide
from kitguard.evaluation import file_sha256, score_case
from kitguard.schemas import Observation, Requirements
from scripts.evaluate_v03_gate import (
    PROJECT,
    SCORER_FILES,
    bom_panel,
    compare,
    evaluate_rows,
    evaluate_run,
    first_pass_observation,
    metrics,
    panel_result,
    rescore,
    strict_json,
)


def case(index=0, subgroup="normal_constant_222", truth=None):
    return {
        "id": f"engineering-{index}",
        "source_id": f"engineering-source-{index}",
        "image": f"engineering-{index}.png",
        "sha256": hashlib.sha256(str(index).encode()).hexdigest(),
        "split": "development",
        "subgroup": subgroup,
        "ground_truth": truth or {"bolt": 1, "nut": 1, "washer": 0, "bracket": 0},
    }


def observation(counts=None, *, issue=False, unknown=False):
    counts = dict(counts or {"bolt": 1, "nut": 1, "washer": 0, "bracket": 0})
    if unknown:
        counts["nut"] = None
    return {
        "observed": counts,
        "issues": ["Synthetic visibility obstacle"] if issue or unknown else [],
        "action": {"kind": "recapture" if issue or unknown else "none", "message": "Engineering fixture"},
    }


def raw(case_data, value=None, error=None, latency=1000):
    inventory = {
        "objects": [{"part": "bolt", "center": [0.2, 0.2]}, {"part": "nut", "center": [0.5, 0.5]}],
        "uncertain_parts": [],
        "issues": [],
        "action": {"kind": "none", "message": "Synthetic fixture"},
    }
    return {
        **case_data,
        "case_id": case_data["id"],
        "latency_ms": latency,
        "observation": value if value is not None else observation(),
        "error": error,
        "input_pipeline": "app-upload",
        "counts_exact": True,
        "actionable_counts": True,
        "observation_diagnostics": {"passes": [{"transform": "original", "inventory": inventory}]},
    }


@pytest.mark.parametrize(
    "value",
    [
        observation(),
        observation({"bolt": 2, "nut": 1, "washer": 0, "bracket": 0}),
        observation({"bolt": 4, "nut": 0, "washer": 0, "bracket": 0}),
        observation({"bolt": 0, "nut": 0, "washer": 0, "bracket": 0}),
        observation(issue=True),
        observation(unknown=True),
    ],
)
def test_panel_shortcut_matches_real_decide_for_every_legal_bom(value):
    panel = bom_panel()
    assert len(panel) == 255
    truth = case()["ground_truth"]
    row = score_case(case(), value, 1)
    ready = []
    for requirements in panel:
        Requirements.model_validate(requirements)
        result = decide(
            {"id": "engineering", "revision": 1, "requirements": requirements, "checks": []},
            Observation.model_validate(value),
            "fixture",
            1,
        )
        if result["decision"] == "ready":
            ready.append(requirements)
    compressed = panel_result(row)
    assert compressed["any_false_ready"] == any(bom != truth for bom in ready)
    assert compressed["ready_requirements"] == (ready[0] if ready else None)
    assert len(ready) <= 1


def test_schema_recompute_ignores_saved_success_flags_and_retains_errors():
    c = case()
    invalid = raw(c, {"observed": {"bolt": True}})
    candidate, baseline = rescore(c, invalid)
    assert candidate["classification"] == "E"
    assert not candidate["panel"]["any_false_ready"]
    assert baseline["classification"] == "C"
    candidate, baseline = rescore(c, raw(c, error="ThirdPassFailed"))
    assert candidate["classification"] == "E" and baseline["classification"] == "C"


def test_known_exact_with_issue_is_abstention_not_correct_actionable():
    candidate, _ = rescore(case(), raw(case(), observation(issue=True)))
    assert candidate["counts_exact"]
    assert candidate["classification"] == "U"
    result = metrics([candidate], latency=True)
    assert result["C"] == 0 and result["U"] == 1
    assert result["wrong_given_actionable"]["rate"] is None


def test_missing_original_diagnostic_never_substitutes_final_observation():
    data = raw(case())
    data["observation_diagnostics"]["passes"][0]["transform"] = "rotate_90_ccw"
    value, error = first_pass_observation(data)
    assert value is None and error.startswith("UnavailableFirstPass")
    _, baseline = rescore(case(), data)
    assert baseline["classification"] == "E"


def test_nominal_perturbation_and_255_panel_denominators_are_separate():
    c1 = case(1, "quantity_anomaly", {"bolt": 2, "nut": 1, "washer": 0, "bracket": 0})
    c1["nominal_requirements"] = {"bolt": 1, "nut": 1, "washer": 0, "bracket": 0}
    c2 = case(2, "screws_author_safe_crop")
    rows = [rescore(c1, raw(c1))[0], rescore(c2, raw(c2))[0]]
    result = metrics(rows, latency=True)
    assert result["nominal_anomaly_false_ready"] == {"numerator": 1, "denominator": 1, "rate": 1}
    assert result["fixed_perturbation_false_ready"]["denominator"] == 2
    assert result["fixed_perturbation_false_ready"]["numerator"] == 0
    assert result["panel_any_false_ready"] == {"numerator": 1, "denominator": 2, "rate": 0.5}


def test_zero_errors_both_does_not_demonstrate_benefit_and_no_latency_claim():
    candidate, baseline = rescore(case(), raw(case()))
    comparison = compare([candidate], [baseline])
    assert not comparison["demonstrated_error_blocking_benefit"]
    assert metrics([baseline], latency=False)["latency_ms"] is None
    assert baseline["latency_ms"] is None


def test_benefit_requires_real_baseline_wrong_and_no_new_wrong():
    c = case()
    right, _ = rescore(c, raw(c))
    wrong, _ = rescore(c, raw(c, observation({"bolt": 2, "nut": 1, "washer": 0, "bracket": 0})))
    abstain, _ = rescore(c, raw(c, observation(unknown=True)))
    reduced = compare([abstain, right], [wrong, right])
    assert reduced["demonstrated_error_blocking_benefit"]
    assert reduced["blocked_baseline_wrong"] == 1
    # Net fewer errors cannot conceal a new error on a different image.
    introduced = compare([abstain, abstain, wrong], [wrong, wrong, right])
    assert introduced["candidate_wrong"] < introduced["baseline_wrong"]
    assert introduced["introduced_wrong"] == 1
    assert not introduced["demonstrated_error_blocking_benefit"]


def test_gate_does_not_pool_groups_or_drop_slow_error():
    c1, c2 = case(1, "loco"), case(2, "screws")
    config = {
        "groups": {
            k: {"images": 1, "correct_actionable_min": 1, "subgroups": [k]} for k in ("loco", "screws")
        },
        "median_latency_ms_max": 60000,
    }
    report = evaluate_rows([c1, c2], [raw(c1), raw(c2, error="Timeout", latency=90000)], config)
    assert report["groups"]["loco"]["passed"]
    assert not report["groups"]["screws"]["passed"] and not report["stage_passed"]
    assert report["candidate"]["images"] == 2 and report["candidate"]["E"] == 1
    assert report["groups"]["screws"]["candidate"]["latency_ms"]["median"] == 90000


@pytest.fixture
def saved_run(tmp_path):
    run = tmp_path / "synthetic-run"
    run.mkdir()
    (run / "source_snapshot").mkdir()
    (run / "normalized_inputs").mkdir()
    c = case()
    manifest = {"schema_version": 1, "cases": [c]}
    (run / "manifest.json").write_text(json.dumps(manifest))
    fake_input = run / "normalized_inputs/001.jpg"
    fake_input.write_bytes(b"Engineering bytes; no image or model inference")
    snapshot = run / "source_snapshot/spatial.py"
    snapshot.write_bytes((PROJECT / "kitguard/spatial.py").read_bytes())
    config = {
        "manifest_sha256": file_sha256(run / "manifest.json"),
        "case_ids": [c["id"]],
        "groups": {"synthetic": {"images": 1, "correct_actionable_min": 1, "subgroups": [c["subgroup"]]}},
        "median_latency_ms_max": 60000,
    }
    model = {"observation_mode": "spatial_guarded", "revision": "engineering-fixture"}
    protocol = {
        "created_at": "2026-09-26T00:00:00+00:00",
        "stages": {"development": config},
        "required_model_status": model,
        "method_source_hashes": {"spatial.py": file_sha256(snapshot)},
        "scoring_source_hashes": {n: file_sha256(PROJECT / "kitguard" / n) for n in SCORER_FILES},
        "limitations": ["Synthetic engineering fixture only"],
    }
    protocol_path = tmp_path / "synthetic-protocol.json"
    protocol_path.write_text(json.dumps(protocol))
    meta = {
        "status": "completed",
        "expected_cases": 1,
        "completed_cases": 1,
        "case_ids": [c["id"]],
        "manifest_sha256": config["manifest_sha256"],
        "split": "development",
        "input_pipeline": "app-upload",
        "model_before": model,
        "model_after": model,
        "source_changed_during_run": False,
        "source_hashes": protocol["method_source_hashes"],
        "source_hashes_after": protocol["method_source_hashes"],
    }
    (run / "run.json").write_text(json.dumps(meta))
    row = raw(c)
    row["model_input_sha256"] = file_sha256(fake_input)
    (run / "predictions.jsonl").write_text(json.dumps(row) + "\n")
    return run, protocol_path


def test_complete_integrity_verified_run_recomputes_and_never_deploys_development(saved_run):
    run, protocol = saved_run
    result = evaluate_run(run, "development", protocol)
    assert result["stage_passed"] and result["complete"]
    assert result["candidate"]["C"] == 1
    assert result["default_adoption_eligible"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        "incomplete",
        "source_changed",
        "snapshot",
        "input",
        "row_duplicate",
        "row_truth",
        "row_order",
        "model",
        "manifest",
        "scorer",
    ],
)
def test_provenance_failure_cannot_create_passing_report(saved_run, mutation):
    run, protocol = saved_run
    meta = json.loads((run / "run.json").read_text())
    row = json.loads((run / "predictions.jsonl").read_text())
    if mutation == "incomplete":
        meta["status"] = "running"
    elif mutation == "source_changed":
        meta["source_changed_during_run"] = True
    elif mutation == "snapshot":
        (run / "source_snapshot/spatial.py").write_text("changed")
    elif mutation == "input":
        (run / "normalized_inputs/001.jpg").write_bytes(b"changed")
    elif mutation == "row_duplicate":
        (run / "predictions.jsonl").write_text((json.dumps(row) + "\n") * 2)
    elif mutation == "row_truth":
        row["ground_truth"]["nut"] = 0
    elif mutation == "row_order":
        row["case_id"] = "wrong"
    elif mutation == "model":
        meta["model_after"] = {**meta["model_after"], "revision": "other"}
    elif mutation == "manifest":
        (run / "manifest.json").write_text((run / "manifest.json").read_text() + " ")
    elif mutation == "scorer":
        data = json.loads(protocol.read_text())
        data["scoring_source_hashes"]["evaluation.py"] = "0" * 64
        protocol.write_text(json.dumps(data))
    (run / "run.json").write_text(json.dumps(meta))
    if mutation != "row_duplicate":
        (run / "predictions.jsonl").write_text(json.dumps(row) + "\n")
    with pytest.raises(ValueError):
        evaluate_run(run, "development", protocol)


@pytest.mark.parametrize("payload", ['{"a":1,"a":2}', '{"x":NaN}', '{"x":Infinity}'])
def test_ambiguous_json_rejected(payload):
    with pytest.raises(ValueError):
        strict_json(payload)


def test_cli_refuses_output_overwrite_without_mutating(saved_run, tmp_path):
    run, protocol = saved_run
    output = tmp_path / "existing.json"
    output.write_text("preserve")
    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT / "scripts/evaluate_v03_gate.py"),
            "--run",
            str(run),
            "--stage",
            "development",
            "--protocol",
            str(protocol),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0 and output.read_text() == "preserve"
