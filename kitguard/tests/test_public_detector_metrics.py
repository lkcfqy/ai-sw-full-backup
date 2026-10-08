"""Synthetic metric arithmetic checks; no model inference or accuracy evidence."""

import copy
import math

import pytest

from scripts.public_detector_metrics import evaluate, select_threshold


def obj(label=1, box=(0, 0, 10, 10), score=None):
    result = {"label": label, "box": list(box)}
    if score is not None:
        result["score"] = score
    return result


def record(truth, predictions, image_id=1, seconds=0.5):
    return {"image_id": image_id, "ground_truth": truth, "predictions": predictions,
            "inference_seconds": seconds}


def test_duplicate_prediction_matches_truth_only_once():
    result = evaluate([record([obj()], [obj(score=0.9), obj(score=0.8)])], 0.5)
    assert (result["tp"], result["fp"], result["fn"]) == (1, 1, 0)
    assert result["precision"] == 0.5
    assert result["recall"] == 1
    assert result["f1"] == pytest.approx(2 / 3)
    assert result["count_mae_per_class"] == {1: 1.0, 2: 0.0}


def test_wrong_class_has_false_positive_and_false_negative_despite_same_total():
    result = evaluate([record([obj()], [obj(label=2, score=1)])], 0.5)
    assert (result["tp"], result["fp"], result["fn"]) == (0, 1, 1)
    assert result["per_class"][1]["fn"] == 1
    assert result["per_class"][2]["fp"] == 1
    assert result["exact_count_accuracy"] == 0
    assert result["count_mae_per_class"] == {1: 1.0, 2: 1.0}
    assert result["mean_absolute_total_count_error"] == 0


def test_correct_counts_do_not_imply_correct_localization():
    result = evaluate([record([obj()], [obj(box=(20, 20, 30, 30), score=0.9)])], 0.5)
    assert (result["tp"], result["fp"], result["fn"]) == (0, 1, 1)
    assert result["exact_count_images"] == 1
    assert result["exact_count_accuracy"] == 1
    assert result["count_mae_per_class"] == {1: 0.0, 2: 0.0}


def test_matching_is_score_ordered_greedy_not_global_maximum():
    # The higher-score prediction overlaps both GTs and takes GT1; the lower
    # prediction can match only GT1. Greedy therefore finds one TP, not two.
    rows = [record([obj(), obj(box=(3, 0, 13, 10))],
                   [obj(box=(0, 0, 7, 10), score=0.7),
                    obj(box=(1, 0, 11, 10), score=0.9)])]
    before = copy.deepcopy(rows)
    result = evaluate(rows, 0.5)
    assert (result["tp"], result["fp"], result["fn"]) == (1, 1, 1)
    assert rows == before


def test_iou_and_score_thresholds_are_inclusive():
    result = evaluate([record([obj()], [obj(box=(0, 0, 5, 10), score=0.5)])], 0.5)
    assert (result["tp"], result["fp"], result["fn"]) == (1, 0, 0)


def test_empty_predictions_and_empty_truth_stay_in_image_denominator():
    rows = [record([obj(), obj(label=2)], [], 1, 1), record([], [], 2, 3)]
    result = evaluate(rows, 0.5)
    assert result["images"] == 2
    assert result["exact_count_images"] == 1
    assert result["exact_count_accuracy"] == 0.5
    assert result["count_mae_per_class"] == {1: 0.5, 2: 0.5}
    assert result["mean_absolute_total_count_error"] == 1
    assert result["latency_median_seconds"] == 2
    assert (result["tp"], result["fp"], result["fn"]) == (0, 0, 2)
    assert result["precision"] == result["recall"] == result["f1"] == 0


def test_selection_removes_low_score_duplicate_then_prefers_higher_tied_threshold():
    rows = [record([obj()], [obj(score=0.85), obj(score=0.25)])]
    result = select_threshold(rows)
    assert result["threshold"] == 0.8
    assert result["metrics"]["exact_count_accuracy"] == 1
    assert len(result["sweep"]) == 9
    assert result["sweep"][0]["metrics"]["exact_count_accuracy"] == 0


def test_selection_breaks_equal_accuracy_by_class_mae_before_f1():
    rows = [record([obj(), obj(box=(20, 0, 30, 10))],
                   [obj(box=(40, 0, 50, 10), score=0.9), obj(score=0.4),
                    obj(box=(20, 0, 30, 10), score=0.4),
                    obj(box=(60, 0, 70, 10), score=0.4)])]
    result = select_threshold(rows, [0.3, 0.5])
    # Neither count is exact. The higher threshold reduces absolute count
    # error from two to one, despite throwing away both correctly placed boxes.
    assert result["threshold"] == 0.5
    assert result["metrics"]["exact_count_accuracy"] == 0
    assert result["metrics"]["count_mae_per_class"] == {1: 1.0, 2: 0.0}
    assert result["metrics"]["f1"] == 0
    assert result["sweep"][0]["metrics"]["f1"] > 0


def test_selection_breaks_equal_count_metrics_by_detection_f1():
    rows = [record([obj()], [obj(score=0.9), obj(box=(20, 0, 30, 10), score=0.4)], 1),
            record([obj()], [obj(box=(20, 0, 30, 10), score=0.4)], 2)]
    result = select_threshold(rows, [0.3, 0.5])
    # Both thresholds have one exact-count image and a total class-count error
    # of one. Removing the misplaced low-score boxes improves detection F1.
    assert result["threshold"] == 0.5
    assert result["metrics"]["f1"] == pytest.approx(2 / 3)


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf, True, "0.5", -0.1, 1.1])
def test_invalid_score_or_threshold_rejected_even_below_filter(invalid):
    with pytest.raises(ValueError):
        evaluate([record([obj()], [obj(score=invalid)])], 1)
    with pytest.raises(ValueError):
        evaluate([], invalid)


@pytest.mark.parametrize("box", [[0, 0, 0, 10], [10, 0, 0, 10], [0, 0, 10],
                                 [0, 0, math.inf, 10], [0, False, 10, 10],
                                 [0, 0, 1e308, 1e308]])
def test_invalid_boxes_rejected(box):
    with pytest.raises(ValueError):
        evaluate([record([obj(box=box)], [])], 0.5)


@pytest.mark.parametrize("label", [0, 3, True, 1.0, "1"])
def test_invalid_labels_rejected(label):
    with pytest.raises(ValueError):
        evaluate([record([obj(label=label)], [])], 0.5)


@pytest.mark.parametrize("seconds", [-1, math.nan, math.inf, True, None])
def test_invalid_latency_rejected(seconds):
    with pytest.raises(ValueError):
        evaluate([record([], [], seconds=seconds)], 0.5)


def test_duplicate_images_and_empty_threshold_selection_rejected():
    with pytest.raises(ValueError):
        evaluate([record([], []), record([], [])], 0.5)
    with pytest.raises(ValueError):
        select_threshold([])
    with pytest.raises(ValueError):
        select_threshold([record([], [])], [])
    with pytest.raises(ValueError):
        select_threshold([record([], [])], [0.5, 0.5])
    result = evaluate([], 0.5)
    assert result["images"] == 0
    assert result["exact_count_accuracy"] is None
    assert result["count_mae_per_class"] == {1: None, 2: None}
    assert result["latency_median_seconds"] is None
