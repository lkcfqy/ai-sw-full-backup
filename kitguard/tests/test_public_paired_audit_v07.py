"""Synthetic CPU contracts for the independent audit; no public predictions read."""
import copy
import json
import shutil
import types
from pathlib import Path

import pytest
from PIL import Image

from scripts.v07 import audit_public_paired as a


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def fixture_case(i=1):
    return {"id": f"c{i}", "source_id": f"s{i}", "source_sha256": f"{i:064x}",
            "source_decoded_rgb_sha256": f"{i+51:064x}", "subgroup": "synthetic",
            "supported_positive_classes": ["bolt", "nut"],
            "ground_truth": {"bolt": 1, "nut": 0, "washer": 0, "bracket": 0}}


def fixture_row(case=None, *, uncertain=False, wrong=False, error=None):
    case = case or fixture_case()
    observation = {"observed": case["ground_truth"] | ({"bracket": 1} if wrong else {}),
                   "issues": ["unclear"] if uncertain else [],
                   "action": {"kind": "recapture" if uncertain else "none", "message": "synthetic"}}
    return {"case_id": case["id"], "observation": observation, "error": error,
            "counts_exact": not wrong and not error, "actionable_counts": not uncertain and not error,
            "mode": a.MODES[0], "loaded_before": True, "latency_ms": 1000}


def test_incomplete_status_is_rejected_before_predictions_file_is_opened(tmp_path):
    write(tmp_path / "run.json", {"status": "running"})
    with pytest.raises(a.AuditError, match="predictions intentionally unread"):
        a.audit(tmp_path)
    assert not (tmp_path / "predictions.jsonl").exists()


def test_completed_must_mean_all_153_attempts(tmp_path):
    write(tmp_path / "run.json", {"status": "completed", "planned_attempts": 153, "completed_attempts": 152})
    with pytest.raises(a.AuditError, match="153"):
        a.completed_metadata(tmp_path)


def test_order_validation_rejects_reordered_duplicate_or_unplanned_rows():
    cases = [fixture_case(i) for i in range(1, 52)]
    schedule = a.planned_schedule(cases)
    freeze = {"cases": 51, "attempts": 153, "modes": list(a.MODES), "schedule": schedule}
    assert len(a.validate_ledger(freeze, {"cases": cases}, schedule)) == 51
    changed = copy.deepcopy(schedule)
    changed[0], changed[1] = changed[1], changed[0]
    with pytest.raises(a.AuditError, match="reordered"):
        a.validate_ledger(freeze, {"cases": cases}, changed)
    changed[0] = changed[1]
    with pytest.raises(a.AuditError, match="duplicate"):
        a.validate_ledger(freeze, {"cases": cases}, changed)


def test_cwue_and_nonvisual_uncertainty_are_independently_recomputed():
    case = fixture_case()
    assert a.derive_outcome(fixture_row(), case["ground_truth"]) == "C"
    assert a.derive_outcome(fixture_row(wrong=True), case["ground_truth"]) == "W"
    assert a.derive_outcome(fixture_row(uncertain=True), case["ground_truth"]) == "U"
    row = fixture_row(error="runtime failed")
    row["counts_exact"] = row["actionable_counts"] = False
    assert a.derive_outcome(row, case["ground_truth"]) == "E"
    row["counts_exact"] = True
    with pytest.raises(a.AuditError, match="scoring flags"):
        a.derive_outcome(row, case["ground_truth"])


def test_false_ready_uses_all_255_orders_and_supported_domain_separately():
    case = fixture_case()
    row = fixture_row(wrong=True)
    panels = a.independent_panels(case, row)
    assert len(list(a.order_panel(a.PARTS))) == 255
    assert panels["all_four"]["mismatched_orders"] == 254
    assert panels["all_four"]["any_false_ready"] is True
    assert panels["source_supported"]["any_false_ready"] is False
    assert a.independent_panels(case, fixture_row(uncertain=True))["all_four"]["any_false_ready"] is False
    failed = a.independent_panels(case, fixture_row(error="failed"))["all_four"]
    assert failed["risk_measured"] is False and failed["any_false_ready"] is False


def test_safe_artifact_rejects_escape_and_symlink(tmp_path):
    with pytest.raises(a.AuditError, match="escapes"):
        a.inside(tmp_path, "../outside")
    (tmp_path / "real").write_text("data")
    (tmp_path / "link").symlink_to(tmp_path / "real")
    with pytest.raises(a.AuditError, match="symlinks"):
        a.inside(tmp_path, "link")


def cpu_fixture(tmp_path, mode=a.MODES[0], *, malformed=False, malformed_call=None, identity_id="p001", no_return_call=None):
    """Record one synthetic observer execution through the real CPU preparation."""
    from kitguard import schemas, vision
    from scripts import probe_selective_identity as probe

    tmp_path.mkdir(parents=True, exist_ok=True)
    frozen = types.SimpleNamespace(schemas=schemas, vision=vision, probe=probe)
    image = tmp_path / "normalized.jpg"
    Image.new("RGB", (80, 72), (220, 215, 200)).save(image)
    case_dir = tmp_path / "case"
    engine = probe.SelectiveIdentityVision() if mode == a.MODES[2] else vision.LocalVision(observation_mode=mode, image_max_side=1536)
    engine.artifact_dir = case_dir
    # One clear nut enables identity in guarded and the one-direction candidate.
    inventory = {"objects": [{"part": "nut", "center": [.5, .5]}], "uncertain_parts": [], "issues": [],
                 "action": {"kind": "none", "message": "fixture inventory"}}
    identity = {"objects": [{"id": identity_id, "part": "nut", "status": "independent_object",
                             "opening": "through_hole", "issue": ""}]}

    def fake_generate(self, system, prompt, images, schema, *, max_tokens=450):
        calls = self._observation_attempt.setdefault("generation_calls", [])
        call_dir = self.artifact_dir / f"call-{len(calls)+1:02d}"
        call_dir.mkdir(parents=True)
        saved = []
        for i, source in enumerate(images, 1):
            target = call_dir / f"image-{i:02d}{Path(source).suffix}"
            shutil.copyfile(source, target)
            saved.append({"path": str(target.relative_to(case_dir)), "sha256": a.sha(target)})
        raw = "not-json" if malformed or len(calls)+1 == malformed_call else json.dumps(inventory if schema.__name__ == "SpatialInventory" else identity)
        runtime = {"seconds": 0., "prompt_tokens": 10, "generation_tokens": 10,
                   "mlx_reported_peak_memory_gb": .01, "finish_reason": "stop"}
        record = {"schema": schema.__name__, "system": system, "prompt": prompt,
                  "max_tokens": max_tokens, "temperature": 0., "images": saved,
                  "status": "parsed", "raw_text": raw, "runtime": runtime}
        self._last_inference = copy.deepcopy(runtime)
        calls.append(record)
        if len(calls) == no_return_call:
            record.update(status="failed", raw_text=None, runtime=None, error="RuntimeError: simulated backend loss")
            self._last_inference = None
            write(call_dir / "generation.json", record)
            raise vision.ModelUnavailableError("Experimental inference failed: RuntimeError")
        try:
            parsed = vision._parse_json(raw, schema)
            record["parsed"] = parsed.model_dump()
            return parsed
        except vision.ModelOutputError as exc:
            record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            raise
        finally:
            write(call_dir / "generation.json", record)

    engine._generate = types.MethodType(fake_generate, engine)
    error, observation = None, None
    try:
        observation = engine._observe(image, {})
    except (vision.ModelOutputError, vision.ModelUnavailableError, ValueError) as exc:
        error = f"{type(exc).__name__}: {exc}"
    row = {"mode": mode, "observation": observation, "error": error, "latency_ms": 1000,
           "observation_diagnostics": copy.deepcopy(engine._observation_attempt),
           "runtime": copy.deepcopy(engine._last_inference) if not error else None}
    return engine, image, case_dir, row, frozen


@pytest.mark.parametrize("mode,expected_calls,expected_crops", [(a.MODES[0], 1, 0), (a.MODES[1], 3, 1), (a.MODES[2], 2, 1)])
def test_all_three_frozen_observation_paths_replay_exact_inputs_and_raw_outputs(tmp_path, mode, expected_calls, expected_crops):
    engine, normalized, directory, row, frozen = cpu_fixture(tmp_path, mode)
    totals, failures = a.replay_observation(engine, normalized, directory, row, frozen)
    assert totals["calls"] == expected_calls
    assert totals["reconstructed_identity_crops"] == expected_crops
    assert failures == []


def test_raw_parse_failure_is_preserved_and_reproduced(tmp_path):
    engine, normalized, directory, row, frozen = cpu_fixture(tmp_path, malformed=True)
    totals, failures = a.replay_observation(engine, normalized, directory, row, frozen)
    assert totals["failed"] == 1 and totals["raw_text_returns"] == 1 and not failures


def test_changed_image_rejected_even_when_receipt_hash_is_also_rewritten(tmp_path):
    engine, normalized, directory, row, frozen = cpu_fixture(tmp_path)
    call = row["observation_diagnostics"]["generation_calls"][0]
    image = directory / call["images"][0]["path"]
    Image.new("RGB", (80, 72), "black").save(image)
    call["images"][0]["sha256"] = a.sha(image)
    write(directory / "call-01/generation.json", call)
    with pytest.raises(a.AuditError, match="re-prepared pixels"):
        a.replay_observation(engine, normalized, directory, row, frozen)


def test_changed_parsed_object_does_not_override_retained_raw_text(tmp_path):
    engine, normalized, directory, row, frozen = cpu_fixture(tmp_path)
    call = row["observation_diagnostics"]["generation_calls"][0]
    call["parsed"]["objects"][0]["part"] = "bolt"
    write(directory / "call-01/generation.json", call)
    with pytest.raises(a.AuditError, match="Reparsed raw text"):
        a.replay_observation(engine, normalized, directory, row, frozen)


def test_final_observation_cannot_be_changed_independently_of_raw_call(tmp_path):
    engine, normalized, directory, row, frozen = cpu_fixture(tmp_path)
    row["observation"]["action"]["message"] = "manually changed receipt"
    with pytest.raises(a.AuditError, match="final observation"):
        a.replay_observation(engine, normalized, directory, row, frozen)


@pytest.mark.parametrize("mode,call_count", [(a.MODES[1], 3), (a.MODES[2], 2)])
def test_valid_identity_json_with_wrong_target_id_preserves_parsed_calls(tmp_path, mode, call_count):
    engine, normalized, directory, row, frozen = cpu_fixture(tmp_path, mode, identity_id="p999")
    assert row["error"].startswith("ValueError:")
    calls = row["observation_diagnostics"]["generation_calls"]
    assert len(calls) == call_count and all(c["status"] == "parsed" for c in calls)
    totals, failures = a.replay_observation(engine, normalized, directory, row, frozen)
    assert totals["parsed"] == call_count and not failures


def test_second_call_parse_failure_keeps_first_inventory_and_identity_diagnostics(tmp_path):
    engine, normalized, directory, row, frozen = cpu_fixture(tmp_path, a.MODES[2], malformed_call=2)
    totals, failures = a.replay_observation(engine, normalized, directory, row, frozen)
    assert totals["parsed"] == 1 and totals["failed"] == 1 and not failures


def test_failed_identity_metadata_tampering_is_rejected(tmp_path):
    engine, normalized, directory, row, frozen = cpu_fixture(tmp_path, a.MODES[2], identity_id="p999")
    row["observation_diagnostics"]["experimental_identity"]["targets"][0]["center"] = [.1, .2]
    with pytest.raises(a.AuditError, match="identity/observation diagnostics"):
        a.replay_observation(engine, normalized, directory, row, frozen)


def test_persisted_candidate_base_wall_timer_is_checked_not_cpu_replayed(tmp_path):
    engine, normalized, directory, row, frozen = cpu_fixture(tmp_path, a.MODES[2])
    row["latency_ms"] = 20_000
    row["observation_diagnostics"]["single_direction_base"]["latency_ms"] = 14_645
    row = json.loads(json.dumps(row))  # Use the persisted JSON receipt boundary.
    totals, failures = a.replay_observation(engine, normalized, directory, row, frozen)
    assert totals["parsed"] == 2 and not failures
    assert row["observation_diagnostics"]["single_direction_base"]["latency_ms"] == 14_645


@pytest.mark.parametrize("elapsed", [-1, True, 1002])
def test_candidate_base_timer_rejects_invalid_or_outside_attempt_values(tmp_path, elapsed):
    engine, normalized, directory, row, frozen = cpu_fixture(tmp_path, a.MODES[2])
    row["observation_diagnostics"]["single_direction_base"]["latency_ms"] = elapsed
    with pytest.raises(a.AuditError, match="base timer"):
        a.replay_observation(engine, normalized, directory, row, frozen)


def test_candidate_base_timer_cannot_be_shorter_than_generation(tmp_path):
    _, _, _, row, _ = cpu_fixture(tmp_path, a.MODES[2])
    row["observation_diagnostics"]["single_direction_base"]["latency_ms"] = 5
    row["observation_diagnostics"]["generation_calls"][0]["runtime"]["seconds"] = .100
    with pytest.raises(a.AuditError, match="shorter than"):
        a.comparable_diagnostics(row["observation_diagnostics"], row, recorded=True)


def test_nested_base_observation_and_other_timing_fields_still_compare_exactly(tmp_path):
    engine, normalized, directory, row, frozen = cpu_fixture(tmp_path, a.MODES[2])
    row["observation_diagnostics"]["single_direction_base"]["observed"]["bolt"] = 3
    with pytest.raises(a.AuditError, match="diagnostics differ"):
        a.replay_observation(engine, normalized, directory, row, frozen)
    _, _, _, row, _ = cpu_fixture(tmp_path / "other", a.MODES[2])
    row["observation_diagnostics"]["unregistered_timer"] = {"latency_ms": 100}
    comparable = a.comparable_diagnostics(row["observation_diagnostics"], row, recorded=True)
    assert comparable["unregistered_timer"]["latency_ms"] == 100


def test_runtime_failure_with_no_raw_return_remains_an_explicit_unreplayable_failure(tmp_path):
    engine, normalized, directory, row, frozen = cpu_fixture(tmp_path, a.MODES[2], no_return_call=2)
    totals, failures = a.replay_observation(engine, normalized, directory, row, frozen)
    assert totals["parsed"] == 1 and totals["failed"] == 1 and totals["raw_text_returns"] == 1
    assert failures == [{"call": 2, "error": "RuntimeError: simulated backend loss", "status": "retained_runtime_failure_no_raw_return"}]


def test_independent_summary_keeps_failures_and_not_attempted_in_each_planned_denominator():
    cases = [fixture_case(i) for i in range(1, 4)]
    rows = []
    for mode in a.MODES:
        for i, case in enumerate(cases):
            if mode == a.MODES[2] and i == 2:
                continue
            row = fixture_row(case, uncertain=mode == a.MODES[1] and i == 1,
                              wrong=mode == a.MODES[2] and i == 1,
                              error="backend lost" if mode == a.MODES[1] and i == 2 else None)
            row["mode"] = mode
            rows.append(row)
    freeze = {"predeclared_acceptance": {"guarded_execution_failures": 0, "guarded_wrong_actionable": 0,
              "guarded_any_false_ready": 0, "guarded_correct_actionable_min_rate": .9,
              "guarded_coverage_loss_max_images": 3, "guarded_median_max_ms": 60000},
              "selective_identity_further_validation_gate": {"median_at_most_guarded_fraction": .8}}
    result = a.summarize_independently({c["id"]: c for c in cases}, rows, freeze)
    guard = result["modes"][a.MODES[1]]["all"]
    candidate = result["modes"][a.MODES[2]]["all"]
    assert guard["outcomes"] == {"C": 1, "W": 0, "U": 1, "E": 1, "N": 0}
    assert candidate["outcomes"] == {"C": 1, "W": 1, "U": 0, "E": 0, "N": 1}
    assert guard["correct_actionable_rate"] == candidate["correct_actionable_rate"] == 1/3
    assert guard["false_ready_denominator"] == candidate["false_ready_denominator"] == 3
    assert guard["unmeasured_risk_images"] == candidate["unmeasured_risk_images"] == 1
    assert result["selective_identity_further_validation_gate"]["eligible_for_further_validation"] is False
