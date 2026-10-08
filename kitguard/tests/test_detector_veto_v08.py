"""Synthetic contracts only. No detector/MLX model loads or inference."""
import copy
from contextlib import nullcontext

import pytest
from PIL import Image

from scripts.v08.probe_detector_veto import (
    CHECKPOINT_SHA,
    VETO_ISSUE,
    analyze,
    bind_thumbnail,
    fuse,
    outcome,
    recorded_detector_call,
    sha,
    validate_exposure,
    washer_points,
    write_new,
)


def sample():
    base = {"observed": {"bolt": 2, "nut": 0, "washer": 1, "bracket": 0}, "issues": [],
            "action": {"kind": "none", "message": "", "region": None}, "latency_ms": 21000,
            "object_evidence": {"objects": [{"part": "washer", "center": [.5, .5]}]},
            "verification": {"historical": True}}
    objects = [{"part": "washer", "center": [.5, .5]}]
    detector = {"input_sha256": "imagehash", "image_size": [101, 81],
                "checkpoint_sha256": CHECKPOINT_SHA, "threshold": .5,
                "predictions": [{"label": 2, "class_name": "nut", "bbox_xyxy": [50, 40, 60, 50],
                                 "score": .5, "retained_at_frozen_threshold": True}]}
    binding = {"normalized_input": {"sha256": "imagehash"}, "lineage": {"detector_image_size": [101, 81]}}
    original = {"observed": {"washer": 1}, "uncertain_parts": []}
    return base, objects, detector, binding, original


def test_boundary_threshold_veto_is_unknown_not_count_repair_and_preserves_raw_evidence():
    args = sample()
    untouched = copy.deepcopy(args)
    fused, points, excluded, matches = fuse(*args)
    assert args == untouched
    assert fused["observed"] == {"bolt": 2, "nut": None, "washer": None, "bracket": 0}
    assert fused["action"]["kind"] == "recapture" and fused["issues"] == [VETO_ISSUE]
    assert "latency_ms" not in fused
    assert fused["object_evidence"] == args[0]["object_evidence"]
    assert fused["verification"] == args[0]["verification"]
    assert points[0]["point_xy"] == [50, 40] and len(matches) == 1 and not excluded
    assert outcome(fused, {"bolt": 2, "nut": 1, "washer": 0, "bracket": 0}) == "U"


@pytest.mark.parametrize("change", ["below_threshold", "bolt_box", "point_outside", "no_boxes"])
def test_no_veto_keeps_entire_baseline_except_historical_latency(change):
    args = sample()
    prediction = args[2]["predictions"][0]
    if change == "below_threshold":
        prediction.update(score=.499999, retained_at_frozen_threshold=False)
    elif change == "bolt_box":
        prediction.update(label=1, class_name="bolt")
    elif change == "point_outside":
        prediction["bbox_xyxy"] = [50.0001, 40, 60, 50]
    else:
        args[2]["predictions"] = []
    fused, _, _, matches = fuse(*args)
    expected = copy.deepcopy(args[0])
    expected.pop("latency_ms")
    assert fused == expected and not matches


def test_existing_manual_unknown_is_never_upgraded_or_counted_as_correction():
    args = sample()
    args[0]["action"] = {"kind": "manual", "message": "retain", "region": None}
    args[0]["issues"] = ["existing"]
    args[0]["observed"]["nut"] = None
    fused, _, _, matches = fuse(*args)
    assert matches and fused["action"] == args[0]["action"]
    assert fused["issues"] == ["existing", VETO_ISSUE]
    assert outcome(fused, args[0]["observed"]) == "U"


@pytest.mark.parametrize("original", [{"observed": {"washer": None}, "uncertain_parts": ["washer"]},
                                      {"observed": {"washer": 2}, "uncertain_parts": []},
                                      {"observed": {"washer": True}, "uncertain_parts": []}])
def test_unclear_original_washer_points_are_saved_as_excluded(original):
    args = list(sample())
    args[4] = original
    _, points, excluded, matches = fuse(*args)
    assert not points and not matches and len(excluded) == 1
    assert excluded[0]["reason"] == "original_washer_category_unclear"


@pytest.mark.parametrize("field,value", [("input_sha256", "another"), ("image_size", [100, 81]),
                                         ("threshold", .6), ("checkpoint_sha256", "another")])
def test_detector_binding_mismatch_is_error_not_baseline_fallback(field, value):
    args = sample()
    args[2][field] = value
    with pytest.raises(ValueError):
        fuse(*args)


@pytest.mark.parametrize("field,value", [("score", float("nan")), ("score", float("inf")),
                                         ("bbox_xyxy", [-1, 0, 20, 20]),
                                         ("bbox_xyxy", [50, 40, 50, 60]),
                                         ("bbox_xyxy", [0, 0, 102, 80]), ("class_name", "washer"),
                                         ("retained_at_frozen_threshold", False)])
def test_invalid_raw_detector_results_are_rejected_even_before_filtering(field, value):
    args = sample()
    args[2]["predictions"][0][field] = value
    with pytest.raises(ValueError):
        fuse(*args)


def test_multiple_pairs_are_retained_but_counts_are_not_multiplied():
    args = sample()
    args[2]["predictions"].append(copy.deepcopy(args[2]["predictions"][0]))
    fused, _, _, matches = fuse(*args)
    assert len(matches) == 2 and fused["issues"] == [VETO_ISSUE]


def test_point_mapping_uses_width_minus_one_and_rejects_invalid_centers():
    assert washer_points([{"part": "washer", "center": [1, 0]}], [10, 8])[0]["point_xy"] == [9, 0]
    for bad in ([1.001, .5], [float("nan"), .5], [True, .5]):
        with pytest.raises(ValueError):
            washer_points([{"part": "washer", "center": bad}], [10, 8])


def test_thumbnail_lineage_binds_resize_bytes_pixels_and_dimensions(tmp_path):
    normalized, vlm = tmp_path / "original.jpg", tmp_path / "vlm.png"
    Image.new("RGB", (1600, 1100), (14, 22, 73)).save(normalized)
    with Image.open(normalized) as image:
        rgb = image.convert("RGB")
        rgb.thumbnail((1536, 1536), Image.Resampling.LANCZOS)
        rgb.save(vlm)
    lineage = bind_thumbnail(normalized, vlm, sha(normalized), sha(vlm))
    assert lineage["detector_image_size"] == [1600, 1100]
    assert lineage["vlm_image_size"] == [1536, 1056]
    with pytest.raises(ValueError, match="hash"):
        bind_thumbnail(normalized, vlm, "wrong", sha(vlm))
    Image.new("RGB", (1536, 1056), "blue").save(vlm)
    with pytest.raises(ValueError, match="lineage"):
        bind_thumbnail(normalized, vlm, sha(normalized), sha(vlm))


def test_model_failure_has_started_but_not_completed_and_retains_elapsed():
    record = {"detector_call_started": False, "detector_call_completed": False, "timing": {}}

    def fails(_):
        raise RuntimeError("record me")

    with pytest.raises(RuntimeError, match="record me"):
        recorded_detector_call(fails, object(), nullcontext, record)
    assert record["detector_call_started"] is True and record["detector_call_completed"] is False
    assert record["timing"]["cpu_detector_seconds"] >= 0


def test_full51_summary_keeps_negative_control_denominator_and_failure_risk():
    cases, rows = [], []
    for i in range(51):
        truth = {"bolt": 2, "nut": 2, "washer": 2, "bracket": 0}
        base = {"observed": truth, "issues": [], "action": {"kind": "none"}}
        cases.append({"id": str(i), "ground_truth": truth, "supported_positive_classes": list(truth),
                      "subgroup": "loco_normal_222" if i < 16 else "screws_author_safe_crop"})
        row = {"case_id": str(i), "base_observation": base, "fused_observation": copy.deepcopy(base),
               "error": None, "veto_applied": False,
               "timing": dict.fromkeys(("cpu_detector_seconds", "fusion_seconds", "added_seconds", "case_wall_seconds"), .1)}
        if i == 0:
            row.update(fused_observation=None, error="input hash mismatch")
        if i in (14, 15):
            row["base_observation"] = copy.deepcopy(base)
            row["base_observation"]["observed"]["nut"] = None
            row["fused_observation"] = copy.deepcopy(row["base_observation"])
        if i == 1:
            row["fused_observation"]["observed"]["nut"] = None
            row["fused_observation"]["observed"]["washer"] = None
            row["veto_applied"] = True
        rows.append(row)
    result = analyze(cases, rows)
    assert result["outcomes"] == {"C": 47, "W": 0, "U": 3, "E": 1, "N": 0}
    assert result["unmeasured_risk_images"] == 1
    assert result["loco_true_washer_negative_controls"]["previously_C_denominator"] == 14
    assert result["loco_true_washer_negative_controls"]["previously_C_to_U"] == 1
    assert result["loco_true_washer_negative_controls"]["errors"] == 1
    assert result["source_groups"]["loco_normal_222"]["planned"] == 16
    assert result["further_validation"]["descriptive_conditions_met"] is False
    with pytest.raises(ValueError, match="Full51"):
        analyze(cases[:-1], rows[:-1])


def test_exposure_requires_matching_sources_stages_scope_and_file_hashes(tmp_path):
    path = tmp_path / "evidence.txt"
    path.write_text("bound")
    cases = [{"id": str(i), "source_id": f"source{i}", "source_sha256": f"hash{i}"} for i in range(51)]
    exposure = {"schema": "kitguard.v08.heterogeneous-veto.exposure.v1", "status": "checked",
                "planned_cases": 51, "checkpoint_sha256": CHECKPOINT_SHA, "threshold": .5, "best_epoch": 10,
                "overlap_counts": {"train": 0, "val": 0, "test": 0}, "independent_holdout": False,
                "model_loaded_or_called": False, "files_sha256": {"evidence.txt": sha(path)},
                "cases": [{"case_id": c["id"], "source_id": c["source_id"], "source_sha256": c["source_sha256"],
                           "already_exposed_in_v07": True, "v1_stage_matches": {"train": [], "val": [], "test": []}}
                          for c in cases]}
    validate_exposure(tmp_path, exposure, cases)
    for field, bad in (("status", "pending"), ("independent_holdout", True),
                       ("overlap_counts", {"train": 1, "val": 0, "test": 0}),
                       ("checkpoint_sha256", "another"), ("cases", exposure["cases"][:-1])):
        changed = copy.deepcopy(exposure)
        changed[field] = bad
        with pytest.raises(ValueError):
            validate_exposure(tmp_path, changed, cases)
    path.write_text("changed")
    with pytest.raises(ValueError, match="Hash"):
        validate_exposure(tmp_path, exposure, cases)


def test_evidence_write_refuses_existing_output(tmp_path):
    path = tmp_path / "result.json"
    write_new(path, {"one": 1})
    with pytest.raises(FileExistsError):
        write_new(path, {"one": 2})
