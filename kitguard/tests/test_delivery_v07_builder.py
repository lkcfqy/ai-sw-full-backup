"""Synthetic delivery evidence bindings; no public predictions, model or media work."""

import copy
import json

import pytest

from scripts.v07 import build_delivery as b


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n")


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    root = tmp_path
    modes = b.EVALUATION_MODES
    manifest = root / "run/manifest.json"
    save(manifest, {"description": "Synthetic binding fixture; no real observations"})
    predictions = root / "run/predictions.jsonl"
    predictions.write_text('{"synthetic": true}\n')
    auditor = root / "scripts/v07/audit_public_paired.py"
    auditor.parent.mkdir(parents=True)
    auditor.write_text("# synthetic source identity only; not executed\n")
    identities = {m: {"label": "synthetic", "repo_id": "fixture/model", "revision": "fixture",
                     "observer_protocol_sha256": "0" * 64, "observer_source_hashes": {},
                     "observation_mode": m, "image_max_side": 1536, "path": "/synthetic/model"} for m in modes}
    freeze = {"schema": "kitguard.v07.public-paired.freeze.v1", "modes": list(modes), "cases": 51,
              "attempts": 153, "manifest_sha256": b.sha(manifest), "model_identity": identities}
    freeze_path = root / "freeze/freeze.json"
    save(freeze_path, freeze)
    freeze_sha = b.sha(freeze_path)
    monkeypatch.setattr(b, "EVALUATION_FREEZE_SHA", freeze_sha)
    (root / "run/freeze.json").write_bytes(freeze_path.read_bytes())
    save(root / "run/run.json", {"status": "completed", "planned_attempts": 153, "completed_attempts": 153,
                                "source_changed": False, "isolated_python": True, "freeze_sha256": freeze_sha})
    # A failed engineering gate is legitimate evidence, not a reason to hide results.
    groups = {m: {"all": {"planned": 51, "outcomes": {"C": 48, "W": 1, "U": 2, "E": 0, "N": 0}}} for m in modes}
    comparisons = {m: {"predeclared_gates": {"zero_wrong_actionable": False},
                       "engineering_acceptance_passed": False, "descriptive_safety_advantage_observed": False} for m in modes[1:]}
    followup = {"checks": {"zero_wrong_actionable": False}, "eligible_for_further_validation": False,
                "automatic_promotion": False}
    scores = {"schema": "kitguard.v07.public-paired.analysis.v1", "modes": groups,
              "comparisons_vs_inventory": comparisons, "selective_identity_further_validation_gate": followup,
              "default_change_authorized_by_this_report": False}
    save(root / "run/analysis.json", scores)
    audit = {"schema": "kitguard.v07.public-paired.independent-audit.v1", "status": "passed",
             "source_changed": False, "model_loaded_or_called": False, "planned_photos": 51,
             "planned_attempts": 153, "completed_attempts": 153, "default_change_authorized": False,
             "independent_results": {k: copy.deepcopy(scores[k]) for k in
                                     ("modes", "comparisons_vs_inventory", "selective_identity_further_validation_gate")},
             "model_identity": identities, "raw_evidence_by_mode": {m: {} for m in modes},
             "evidence_sha256": {"freeze": freeze_sha, "manifest": b.sha(manifest),
                                 "predictions": b.sha(predictions), "auditor": b.sha(auditor)},
             "artifacts_sha256": {p.name: b.sha(p) for p in (root / "run").iterdir()}}
    save(root / "audit.json", audit)
    return root, {"evaluation_run": "run/run.json", "evaluation_analysis": "run/analysis.json",
                  "evaluation_freeze": "freeze/freeze.json", "evaluation_audit": "audit.json"}


def test_complete_bound_evidence_retains_failed_engineering_gate(evidence):
    root, checks = evidence
    verified = b.evaluation_evidence(checks, root)
    assert verified["evaluation_attempts"] == 153
    assert verified["evaluation_modes"] == list(b.EVALUATION_MODES)
    assert verified["evaluation_independent_audit_status"] == "passed"
    for row in verified["evaluation_evidence"].values():
        assert b.sha(root / row["path"]) == row["sha256"]


def test_incomplete_run_is_rejected_before_other_evidence_is_read(tmp_path):
    save(tmp_path / "run.json", {"status": "running", "completed_attempts": 73})
    checks = dict.fromkeys(("evaluation_analysis", "evaluation_freeze", "evaluation_audit"), "not-created.json")
    checks["evaluation_run"] = "run.json"
    with pytest.raises(ValueError, match="not finished"):
        b.evaluation_evidence(checks, tmp_path)


@pytest.mark.parametrize("artifact", ["run/run.json", "run/analysis.json", "run/freeze.json", "freeze/freeze.json",
                                     "run/manifest.json", "run/predictions.jsonl", "scripts/v07/audit_public_paired.py"])
def test_changed_actual_bytes_cannot_reuse_passed_audit(evidence, artifact):
    root, checks = evidence
    with (root / artifact).open("a") as handle:
        handle.write(" \n")  # Keeps JSON semantics, changes the actual evidence identity.
    with pytest.raises(ValueError):
        b.evaluation_evidence(checks, root)


@pytest.mark.parametrize("mutation", ["missing_audit", "old_audit_schema", "failed_audit", "partial_audit",
                                    "missing_mode", "extra_mode", "negative_outcome", "missing_attempt",
                                    "independent_disagreement", "wrong_model_identity"])
def test_wrong_version_incomplete_or_mismatched_evidence_is_rejected(evidence, mutation):
    root, checks = evidence
    scores = b.read(root / "run/analysis.json")
    audit = b.read(root / "audit.json")
    if mutation == "missing_audit":
        checks.pop("evaluation_audit")
    elif mutation == "old_audit_schema":
        audit["schema"] = "kitguard.v06.public-paired.independent-audit.v1"
    elif mutation == "failed_audit":
        audit["status"] = "pending"
    elif mutation == "partial_audit":
        audit["completed_attempts"] = 152
    elif mutation == "missing_mode":
        scores["modes"].pop(b.EVALUATION_MODES[-1])
    elif mutation == "extra_mode":
        scores["modes"]["another_method"] = copy.deepcopy(scores["modes"][b.EVALUATION_MODES[0]])
    elif mutation in {"negative_outcome", "missing_attempt"}:
        outcomes = scores["modes"][b.EVALUATION_MODES[0]]["all"]["outcomes"]
        outcomes.update(C=52, W=-1, U=0) if mutation == "negative_outcome" else outcomes.update(C=47, N=1)
    elif mutation == "independent_disagreement":
        audit["independent_results"]["modes"][b.EVALUATION_MODES[0]]["all"]["outcomes"].update(C=49, W=0)
    elif mutation == "wrong_model_identity":
        audit["model_identity"][b.EVALUATION_MODES[0]]["revision"] = "another-model-version"
    save(root / "run/analysis.json", scores)
    audit["artifacts_sha256"]["analysis.json"] = b.sha(root / "run/analysis.json")
    save(root / "audit.json", audit)
    with pytest.raises(ValueError):
        b.evaluation_evidence(checks, root)
