"""Engineering-only CPU fixtures for the offline detector probe, not accuracy evidence."""

import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "scripts/probe_owl_detector.py"
SPEC = importlib.util.spec_from_file_location("owl_probe", PATH)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def box(index, part="nut", score=0.8, xyxy=None):
    return {"raw_index": index, "part": part, "score": score, "box_xyxy": xyxy or [0, 0, 10, 10]}


def test_nms_does_not_merge_classes_or_fit_counts():
    kept, suppressed = probe.nms([box(1), box(0), box(2, "washer"), box(3, xyxy=[20, 0, 30, 10])], 0.5)
    assert [item["raw_index"] for item in kept] == [0, 2, 3]
    assert suppressed[0]["raw_index"] == 1
    assert suppressed[0]["suppressed_by_raw_index"] == 0


def test_nms_threshold_boundary_is_strict():
    kept, suppressed = probe.nms([box(0, xyxy=[0, 0, 10, 10]), box(1, xyxy=[0, 0, 5, 10])], 0.5)
    assert len(kept) == 2
    assert suppressed == []


def test_localization_is_class_aware_and_one_to_one():
    truth = [{"annotation_id": 9, "part": "nut", "box_xyxy": [0, 0, 10, 10]}]
    result = probe.match_boxes([box(0, "washer", 0.99), box(1, "nut", 0.9), box(2, "nut", 0.8)], truth)
    assert (result["tp"], result["fp"], result["fn"]) == (1, 2, 0)
    assert result["matches"][0]["raw_index"] == 1


def test_author_box_translation_and_resize_are_applied():
    case = {
        "id": "a",
        "crop_xyxy": [100, 50, 200, 150],
        "included_annotation_ids": [1],
        "ground_truth": {"bolt": 0, "nut": 1, "washer": 0, "bracket": 0},
    }
    view = {
        "id": "a",
        "crop_xyxy": case["crop_xyxy"],
        "all_source_annotations": [
            {
                "id": 1,
                "category_id": 9,
                "conservative_aabb_xyxy": [120, 80, 160, 120],
                "bbox_row_col_width_height_phi": [100, 140, 40, 40, 0],
            }
        ],
    }
    assert probe.author_boxes(case, view, (200, 100))[0]["box_xyxy"] == [40, 30, 120, 70]
    case["ground_truth"]["nut"] = 2
    with pytest.raises(ValueError, match="count truth"):
        probe.author_boxes(case, view, (200, 100))


def test_failure_and_unfinished_cases_remain_in_exact_denominator():
    counts = {"bolt": 0, "nut": 1, "washer": 0, "bracket": 0}
    good = {
        "dataset": "loco",
        "error": None,
        "counts": counts,
        "ground_truth": counts,
        "counts_exact": True,
        "latency_ms": 10,
    }
    error = {"dataset": "loco", "error": {"type": "RuntimeError"}, "counts_exact": False}
    planned = [{"dataset": "loco"}] * 3
    result = probe.summarize([good, error], planned)["loco"]
    assert result["exact_count_images"] == 1
    assert result["exact_count_denominator"] == 3
    assert result["errors"] == 1
    assert result["absolute_error_denominator_successful"] == 1


def test_empty_detection_is_not_perfect_localization():
    truth = [{"annotation_id": 1, "part": "nut", "box_xyxy": [0, 0, 1, 1]}]
    result = probe.match_boxes([], truth)
    assert (result["tp"], result["fp"], result["fn"]) == (0, 0, 1)
