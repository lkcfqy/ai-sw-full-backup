"""Tampering counterexamples for the independent verifier; no app scoring imports."""

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.verify_study_export import InvalidExport, parse_json, read_json, verify_payload

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "test-results/browser/field-study-v04/engineering-study-export.json"


@pytest.fixture
def exported():
    return read_json(EXAMPLE)


def assign(payload, path, value):
    cursor = payload
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value


def test_actual_browser_engineering_export_passes_independent_logic(exported):
    result = verify_payload(exported)
    assert result["status"] == "verified_internal_consistency", result
    assert result["checked_trials"] == 9
    assert result["recomputed_methods"]["manual"]["correct"] == 3
    assert result["recomputed_methods"]["kitguard"]["returned_checks"]["wrong_clear"] == 1
    assert result["physical_authenticity_verified"] is False
    assert result["photo_bytes_verified"] is False
    assert result["signature_verified"] is False


@pytest.mark.parametrize("path,value", [
    (["schema_version"], True),
    (["schema_version"], 2),
    (["study", "status"], "frozen"),
    (["study", "planned_cases"], 5),
    (["study", "protocol_sha256"], "a" * 64),
    (["study", "cases", 0, "truth", "bolt"], 1),
    (["study", "cases", 0, "truth", "bolt"], True),
    (["study", "cases", 0, "truth_nonce"], "f" * 64),
    (["study", "cases", 0, "photo_sha256"], "b" * 64),
    (["study", "cases", 0, "reference_ids"], {"bolt": "arbitrary"}),
    (["study", "cases", 0, "trials", "manual", "method"], "kitguard"),
    (["study", "cases", 0, "trials", "manual", "elapsed_ms"], True),
    (["study", "cases", 0, "trials", "manual", "elapsed_ms"], -1),
    (["study", "cases", 0, "trials", "manual", "elapsed_ms"], None),
    (["study", "cases", 0, "trials", "manual", "status"], "running"),
    (["study", "cases", 0, "trials", "manual", "status"], "interrupted"),
    (["study", "cases", 0, "trials", "kitguard", "started_at"], "2000-01-01T00:00:00+00:00"),
    (["study", "cases", 0, "trials", "kitguard", "started_at"], "2026-09-26T14:42:35"),
    (["study", "cases", 0, "trials", "kitguard", "order_id"], "another-order"),
    (["study", "cases", 0, "trials", "kitguard", "check", "photo_id"], "another-photo"),
    (["study", "cases", 0, "trials", "kitguard", "evidence", "checks"], []),
    (["study", "cases", 0, "trials", "kitguard", "evidence", "events"], []),
    (["study", "report", "methods", "kitguard", "correct"], True),
    (["study", "report", "methods", "kitguard", "not_started"], 0),
    (["study", "report", "methods", "kitguard", "failed"], 0),
    (["study", "report", "methods", "kitguard", "returned_checks", "wrong_clear"], 0),
    (["study", "report", "methods", "kitguard", "returned_checks", "false_ready"], 0),
    (["study", "report", "methods", "kitguard", "terminal_elapsed_ms", "n"], 3),
    (["study", "report", "paired_completed_cases"], 4),
    (["study", "source_kind"], "self_reported_physical"),
])
def test_tampered_export_is_rejected(exported, path, value):
    assign(exported, path, value)
    result = verify_payload(exported)
    assert result["status"] == "invalid", path
    assert result["errors"]


def test_removed_case_cannot_disappear_from_planned_denominator(exported):
    exported["study"]["cases"].pop()
    assert verify_payload(exported)["status"] == "invalid"


def test_returned_wrong_check_survives_failed_status_and_cannot_be_zeroed(exported):
    study = exported["study"]
    trial = study["cases"][1]["trials"]["kitguard"]
    assert trial["check"]["observed"] != study["cases"][1]["truth"]
    trial.update(status="failed", check=None, note="Synthetic post-return abandonment variant")
    for event in study["events"]:
        if event["kind"] == "trial_finished" and event["payload"]["trial_id"] == trial["id"]:
            event["payload"]["status"] = "failed"
    # Written directly as this fixture's expected arithmetic, never using either scorer.
    metrics = study["report"]["methods"]["kitguard"]
    metrics.update(completed=2, wrong=0, failed=2)
    metrics["false_ready"]["numerator"] = 0
    remaining = [c["trials"]["kitguard"]["elapsed_ms"] for c in study["cases"]
                 if c["trials"]["kitguard"] and c["trials"]["kitguard"]["status"] == "completed"]
    assert len(remaining) == 2
    metrics["completed_elapsed_ms"] = {"n": 2, "median": sum(remaining) / 2, "max": max(remaining)}
    study["report"]["paired_completed_cases"] = 2
    result = verify_payload(exported)
    assert result["status"] == "verified_internal_consistency", result
    assert result["recomputed_methods"]["kitguard"]["returned_checks"]["wrong_clear"] == 1
    metrics["returned_checks"]["wrong_clear"] = 0
    assert verify_payload(exported)["status"] == "invalid"


def test_duplicate_or_nonfinite_json_is_rejected():
    for raw in ('{"schema_version":1,"schema_version":2}', '{"n":NaN}', '{"n":Infinity}'):
        with pytest.raises(InvalidExport):
            parse_json(raw)


@pytest.mark.parametrize("malformed", [None, [], {}, {"schema_version": 1}, {"schema_version": 1, "kind": "invalid"}])
def test_malformed_payload_returns_invalid_receipt_instead_of_crashing(malformed):
    assert verify_payload(malformed)["status"] == "invalid"


def test_cli_receipt_exit_code_and_read_only_behavior(exported, tmp_path):
    original = EXAMPLE.read_bytes()
    receipt_path = tmp_path / "receipt.json"
    command = [sys.executable, str(ROOT / "scripts/verify_study_export.py"), str(EXAMPLE), "--output", str(receipt_path)]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(receipt_path.read_text())["status"] == "verified_internal_consistency"
    assert EXAMPLE.read_bytes() == original
    assert subprocess.run(command, capture_output=True, check=False).returncode == 2
    invalid = deepcopy(exported)
    invalid["study"]["report"]["methods"]["kitguard"]["wrong"] = 0
    bad_path = tmp_path / "tampered.json"
    bad_path.write_text(json.dumps(invalid))
    bad = subprocess.run([sys.executable, str(ROOT / "scripts/verify_study_export.py"), str(bad_path)],
                         capture_output=True, text=True, check=False)
    assert bad.returncode == 1
    assert json.loads(bad.stdout)["status"] == "invalid"
