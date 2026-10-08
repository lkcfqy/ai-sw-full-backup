"""Independent audit regressions; synthetic arrays only, no detector or MLX."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "scripts/v08/audit_heterogeneous_veto.py"
SPEC = importlib.util.spec_from_file_location("independent_v08_audit", SOURCE)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


@pytest.fixture
def sample():
    observed = {"bolt": 1, "nut": 0, "washer": 1, "bracket": 0}
    objects = [{"part": "bolt", "center": [.1, .1]}, {"part": "washer", "center": [.5, .5]}]
    original = {"objects": objects, "observed": observed, "uncertain_parts": [], "transform": "original"}
    base = {"observed": observed, "issues": [], "action": {"kind": "none", "message": "clear", "region": None},
            "latency_ms": 20000, "object_evidence": {"objects": objects, "coordinate_frame": "normalized_original"},
            "verification": {"passes": [original]}, "identity_verification": {"historical": "do not rewrite"}}
    raw = {"labels": [2], "boxes": [[50., 40., 60., 50.]], "scores": [.5]}
    predictions, counts = audit.validate_raw(raw, [101, 81])
    fused, points, excluded, matches = audit.reconstruct_overlay(base, original, [101, 81], predictions)
    detector = {"predictions": predictions, "counts": counts, "checkpoint_sha256": audit.CHECKPOINT_SHA,
                "checkpoint_epoch": 10, "device": "cpu", "threshold": .5, "input_sha256": "input",
                "image_size": [101, 81], "unsupported_classes": ["washer", "bracket"], "decision": None,
                "architecture": "fasterrcnn_mobilenet_v3_large_320_fpn",
                "coordinate_frame": "normalized_input absolute pixel xyxy", "threshold_comparison": "score >= threshold",
                "model_return_filter": "torchvision score floor .05, NMS .5, maximum100 detections"}
    row = {"base_observation": copy.deepcopy(base), "fused_observation": fused, "detector": detector,
           "raw_detector_output": raw, "detector_call_started": True, "detector_call_completed": True,
           "washer_points": points, "excluded_points": excluded, "veto_matches": matches, "veto_applied": True,
           "fused_observation_scope": "experimental overlay, not a revalidated production Observation",
           "status": "ok", "error": None, "binding": {"normalized_input": {"sha256": "input"}},
           "timing": {"cpu_detector_seconds": .1, "fusion_seconds": .01, "added_seconds": .11,
                      "case_wall_seconds": .3, "baseline_guarded_reused_latency_ms": 20000,
                      "full_end_to_end_measured": False}}
    return row, {"observation": base, "latency_ms": 20000}, original


def test_boundary_inclusion_uses_width_minus_one_and_preserves_evidence(sample):
    row, base, original = sample
    audit.verify_case(row, base, original, [101, 81])
    assert row["washer_points"][0]["point_xy"] == [50., 40.]
    assert row["fused_observation"]["observed"] == {"bolt": 1, "nut": None, "washer": None, "bracket": 0}
    assert row["fused_observation"]["identity_verification"] == base["observation"]["identity_verification"]
    assert "latency_ms" not in row["fused_observation"]
    assert base["observation"]["observed"]["nut"] == 0


def test_below_threshold_does_not_veto(sample):
    _, base, original = sample
    raw = {"labels": [2], "boxes": [[50., 40., 60., 50.]], "scores": [.49999]}
    predictions, _ = audit.validate_raw(raw, [101, 81])
    fused, points, excluded, matches = audit.reconstruct_overlay(base["observation"], original, [101, 81], predictions)
    assert not matches and points and not excluded
    expected = copy.deepcopy(base["observation"])
    expected.pop("latency_ms")
    assert fused == expected


@pytest.mark.parametrize("mutation", ["uncertain", "unknown_count", "count_mismatch"])
def test_unclear_original_washer_is_excluded(sample, mutation):
    row, base, original = sample
    original = copy.deepcopy(original)
    if mutation == "uncertain":
        original["uncertain_parts"] = ["washer"]
    else:
        original["observed"]["washer"] = None if mutation == "unknown_count" else 2
    fused, points, excluded, matches = audit.reconstruct_overlay(base["observation"], original, [101, 81], row["detector"]["predictions"])
    assert not points and not matches and len(excluded) == 1
    assert excluded[0]["reason"] == "original_washer_category_unclear"
    assert fused["observed"] == base["observation"]["observed"]


def test_manual_action_and_old_issues_not_downgraded(sample):
    row, base, original = sample
    base["observation"]["action"]["kind"] = "manual"
    base["observation"]["issues"] = ["prior uncertainty"]
    fused, _, _, _ = audit.reconstruct_overlay(base["observation"], original, [101, 81], row["detector"]["predictions"])
    assert fused["action"]["kind"] == "manual" and fused["issues"][0] == "prior uncertainty"


@pytest.mark.parametrize("mutation", ["count_repair", "identity_rewrite", "point_shift", "false_no_match", "label_rewrite", "historical_time"])
def test_tampered_success_receipts_rejected(sample, mutation):
    row, base, original = sample
    if mutation == "count_repair":
        row["fused_observation"]["observed"]["nut"] = 1
    elif mutation == "identity_rewrite":
        row["fused_observation"]["identity_verification"] = {}
    elif mutation == "point_shift":
        row["washer_points"][0]["point_xy"][0] += 1
    elif mutation == "false_no_match":
        row["veto_matches"] = []
    elif mutation == "label_rewrite":
        row["detector"]["predictions"][0]["class_name"] = "washer"
    else:
        row["timing"]["full_end_to_end_measured"] = True
    with pytest.raises(ValueError):
        audit.verify_case(row, base, original, [101, 81])


def test_runtime_failure_is_E_not_baseline_fallback(sample):
    row, base, original = sample
    row.update(status="failed", error="RuntimeError: no model result", raw_detector_output=None, detector=None,
               detector_call_completed=False, fused_observation=None, washer_points=[], excluded_points=[],
               veto_matches=[], veto_applied=False)
    row["timing"].update(fusion_seconds=None, added_seconds=None)
    assert audit.verify_case(row, base, original, [101, 81])["failure_replay"] == "runtime_failure_not_reexecuted"
    assert audit.classify(None, base["observation"]["observed"], row["error"]) == "E"
    row["fused_observation"] = base["observation"]
    with pytest.raises(ValueError, match="without G fallback"):
        audit.verify_case(row, base, original, [101, 81])


def test_invalid_raw_failure_preserved_and_reconstructed(sample):
    row, base, original = sample
    row.update(status="failed", error="ValueError: Predicted box outside image", detector=None,
               fused_observation=None, washer_points=[], excluded_points=[], veto_matches=[], veto_applied=False)
    row["timing"].update(fusion_seconds=None, added_seconds=None)
    row["raw_detector_output"]["boxes"][0][2] = 200
    receipt = audit.verify_case(row, base, original, [101, 81])
    assert receipt["failure_replay"] == "raw_validation_failed"
    assert "outside image" in receipt["raw_validation_error"]


def test_no_raw_without_completed_call(sample):
    row, base, original = sample
    row["detector_call_completed"] = False
    with pytest.raises(ValueError, match="without completed call"):
        audit.verify_case(row, base, original, [101, 81])


@pytest.mark.parametrize("field,value", [("scores", [float("nan")]), ("labels", [True]), ("boxes", [[0, 0, 101, 82]])])
def test_invalid_raw_arrays_rejected(field, value):
    raw = {"labels": [2], "boxes": [[0, 0, 1, 1]], "scores": [.5]}
    raw[field] = value
    with pytest.raises(ValueError):
        audit.validate_raw(raw, [101, 81])


@pytest.mark.parametrize("match_field,reason", [("source_sha256", "original_file_sha256"),
                                              ("source_decoded_rgb_sha256", "original_decoded_rgb_sha256"),
                                              ("original_filename", "original_filename")])
def test_exposure_matches_original_family_even_when_view_changed(match_field, reason):
    case = {"source_image": "raw/image.png", "source_sha256": "source", "source_decoded_rgb_sha256": "pixels",
            "sha256": "derived-new"}
    stage = {"original_filename": "other.png", "source_sha256": "other", "source_decoded_rgb_sha256": "other"}
    stage[match_field] = "image.png" if match_field == "original_filename" else case[match_field]
    assert audit.exposure_matches(case, [stage])[0]["reasons"] == [reason]


def test_derived_view_hash_does_not_hide_or_create_original_match():
    case = {"source_id": "domain:original.png", "source_sha256": "raw", "source_decoded_rgb_sha256": "pixels", "sha256": "crop"}
    stage = {"original_filename": "other.png", "source_sha256": "crop", "source_decoded_rgb_sha256": "other"}
    assert audit.exposure_matches(case, [stage]) == []


def test_incomplete_run_refused_before_prediction_read(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "run.json").write_text(json.dumps({"status": "running"}))
    with pytest.raises(ValueError, match="predictions intentionally unread"):
        audit.audit_run(tmp_path, run, tmp_path / "missing-freeze.json")


def test_all_four_panel_does_not_hide_washer_error_with_narrow_scope(sample):
    _, base, _ = sample
    case = {"ground_truth": {"bolt": 1, "nut": 1, "washer": 0, "bracket": 0},
            "supported_positive_classes": ["bolt", "nut"]}
    panel = audit.panels(case, base["observation"])
    assert panel["all_four"]["any_false_ready"] is True
    assert panel["source_supported"]["any_false_ready"] is False
    assert panel["all_four"]["mismatched_orders"] == 254


def test_import_never_loads_models():
    import ast
    tree = ast.parse(SOURCE.read_text())
    modules = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    modules += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    assert not any(m and m.startswith(("torch", "mlx", "kitguard")) for m in modules)


def test_original_pixel_hash_includes_size_and_mode_namespace():
    import hashlib

    from PIL import Image

    a = Image.new("RGB", (2, 3), (0, 0, 0))
    b = Image.new("RGB", (3, 2), (0, 0, 0))
    assert a.tobytes() == b.tobytes()
    assert audit.source_pixel_sha(a) == hashlib.sha256(b"(2, 3)|RGB|" + a.tobytes()).hexdigest()
    assert audit.source_pixel_sha(a) != audit.source_pixel_sha(b)
