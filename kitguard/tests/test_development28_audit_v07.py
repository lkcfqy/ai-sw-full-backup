"""Audit contracts fail closed on partial, mutated or incompletely recorded runs."""
import copy
import json

import pytest

from scripts.v07.analyze_development28 import (
    admission,
    audit,
    outcome,
    require_complete,
    sha,
    timing,
    verify_calls,
)


def complete_metadata():
    return {"status": "completed", "split": "development", "expected_cases": 28, "completed_cases": 28,
            "case_ids": [f"c{i}" for i in range(28)], "source_changed_during_run": False,
            "source_hashes": {"observer.py": "a" * 64}, "source_hashes_after": {"observer.py": "a" * 64}}


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "reordered", "changed_source"])
def test_completed_run_requires_entire_unchanged_ordered_denominator(mutation):
    metadata = complete_metadata()
    predictions = [{"case_id": case} for case in metadata["case_ids"]]
    if mutation == "missing":
        predictions.pop()
    elif mutation == "duplicate":
        predictions[-1] = predictions[0]
    elif mutation == "reordered":
        predictions.reverse()
    else:
        metadata["source_hashes_after"]["observer.py"] = "b" * 64
    with pytest.raises(ValueError):
        require_complete(metadata, predictions)


def test_partial_predictions_are_not_even_opened(tmp_path):
    (tmp_path / "run.json").write_text('{"status":"running"}')
    (tmp_path / "predictions.jsonl").write_text("invalid JSON that must stay unread")
    with pytest.raises(ValueError, match="partial predictions are intentionally unread"):
        audit(tmp_path)


def test_fast_candidate_does_not_pass_development_gate_with_errors_or_lost_coverage():
    historical = {"C": 24, "W": 0, "U": 4, "E": 0}
    assert admission(historical, historical)["admit_to_new_51_three_method_comparison"] is True
    for candidate in ({"C": 27, "W": 1, "U": 0, "E": 0},
                      {"C": 27, "W": 0, "U": 0, "E": 1},
                      {"C": 23, "W": 0, "U": 5, "E": 0}):
        result = admission(candidate, historical)
        assert result["admit_to_new_51_three_method_comparison"] is False
        assert result["timing_used_for_admission"] is False
        assert result["automatic_default_change"] is False


def test_saved_success_flags_are_recomputed_from_observation():
    counts = {"bolt": 1, "nut": 0, "washer": 0, "bracket": 0}
    row = {"error": None, "ground_truth": counts, "counts_exact": True, "actionable_counts": True,
           "observation": {"observed": counts, "issues": [], "action": {"kind": "none", "message": "fixture", "region": None}, "backend": "test"}}
    assert outcome(row) == "C"
    row["observation"]["action"]["kind"] = "recapture"
    with pytest.raises(ValueError, match="Saved score"):
        outcome(row)


def raw_fixture(directory):
    call_dir = directory / "call-01"
    call_dir.mkdir()
    image = call_dir / "image-01.png"
    image.write_bytes(b"engineering input bytes")
    inventory = {"objects": [{"part": "bolt", "center": [.5, .5]}], "uncertain_parts": [],
                 "issues": [], "action": {"kind": "none", "message": "fixture"}}
    record = {"schema": "SpatialInventory", "max_tokens": 900, "temperature": 0, "status": "parsed",
              "raw_text": json.dumps(inventory), "parsed": inventory,
              "images": [{"path": "call-01/image-01.png", "sha256": sha(image)}]}
    (call_dir / "generation.json").write_text(json.dumps(record))
    row = {"error": None, "observation_diagnostics": {"generation_calls": [copy.deepcopy(record)],
           "passes": [{"transform": "original", "input_sha256": sha(image)}],
           "experimental_identity": {"model_called": False}}}
    return row, record, image


def test_raw_outputs_and_actual_input_bytes_are_both_checked(tmp_path):
    row, _, image = raw_fixture(tmp_path)
    counts, images = verify_calls(tmp_path, row)
    assert counts["generation_boundaries"] == counts["raw_text_returns"] == counts["parsed"] == 1
    assert images == 1
    image.write_bytes(b"mutated actual input")
    with pytest.raises(ValueError, match="input image hash"):
        verify_calls(tmp_path, row)


def test_raw_text_is_reparsed_instead_of_trusting_saved_parsed_payload(tmp_path):
    row, record, _ = raw_fixture(tmp_path)
    record["raw_text"] = record["raw_text"].replace('"bolt"', '"nut"')
    (tmp_path / "call-01/generation.json").write_text(json.dumps(record))
    row["observation_diagnostics"]["generation_calls"] = [record]
    with pytest.raises(ValueError, match="Reparsed raw"):
        verify_calls(tmp_path, row)


def test_latency_quantiles_and_total_retain_all_attempts():
    result = timing([{"latency_ms": value} for value in range(1, 29)])
    assert result == {"measured": 28, "p50_ms": 14.5, "p90_ms": 26, "total_ms": 406, "maximum_ms": 28}
