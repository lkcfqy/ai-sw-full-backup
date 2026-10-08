"""Pure-Python detection/count metrics for the two-class public-data experiment.

Detection uses class-aware, score-ordered greedy one-to-one matching at IoU
>= 0.5. These are fixed-threshold precision/recall/F1, not COCO mAP. Counts
ignore localization deliberately, so correct counts can coexist with zero TP.
All input images remain in count denominators, including empty predictions.
"""

from __future__ import annotations

import math
import statistics

LABELS = (1, 2)
DEFAULT_THRESHOLDS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)


def _number(value, name, *, minimum=None, maximum=None):
    try:
        finite = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError(f"{name} must be a finite number")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be <= {maximum}")
    return value


def _validate_objects(objects, name, *, predictions=False):
    if not isinstance(objects, list):
        raise TypeError(f"{name} must be a list")
    for index, item in enumerate(objects):
        where = f"{name}[{index}]"
        if not isinstance(item, dict):
            raise TypeError(f"{where} must be an object")
        label = item.get("label")
        if type(label) is not int or label not in LABELS:
            raise ValueError(f"{where}.label must be integer 1 or 2")
        box = item.get("box")
        if not isinstance(box, (list, tuple)) or len(box) != 4:
            raise ValueError(f"{where}.box must contain four xyxy coordinates")
        for coordinate in box:
            _number(coordinate, f"{where}.box coordinate")
        width, height = box[2] - box[0], box[3] - box[1]
        area = width * height
        _number(area, f"{where}.box area")
        if width <= 0 or height <= 0 or area <= 0:
            raise ValueError(f"{where}.box must have finite positive area")
        if predictions:
            _number(item.get("score"), f"{where}.score", minimum=0, maximum=1)


def _validate(records):
    if not isinstance(records, list):
        raise TypeError("records must be a list")
    seen = set()
    for index, record in enumerate(records):
        where = f"records[{index}]"
        if not isinstance(record, dict):
            raise TypeError(f"{where} must be an object")
        image_id = record.get("image_id")
        if type(image_id) is not int or image_id in seen:
            raise ValueError(f"{where}.image_id must be a unique integer")
        seen.add(image_id)
        _validate_objects(record.get("ground_truth"), f"{where}.ground_truth")
        _validate_objects(record.get("predictions"), f"{where}.predictions", predictions=True)
        _number(record.get("inference_seconds"), f"{where}.inference_seconds", minimum=0)


def _iou(first, second):
    intersection = max(0, min(first[2], second[2]) - max(first[0], second[0])) * max(
        0, min(first[3], second[3]) - max(first[1], second[1])
    )
    area_first = (first[2] - first[0]) * (first[3] - first[1])
    area_second = (second[2] - second[0]) * (second[3] - second[1])
    # Divide before adding to avoid overflowing a union of individually finite areas.
    scale = max(area_first, area_second)
    return (intersection / scale) / (
        area_first / scale + area_second / scale - intersection / scale
    )


def _detection_metrics(tp, fp, fn):
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0,
    }


def evaluate(records, threshold):
    """Score all records; per-class mappings use integer keys 1 and 2.

    A prediction is retained when score >= threshold. Equal scores retain input
    order; equal-IoU matches use ground-truth input order. Undefined detection
    ratios are 0.0. An empty dataset has None for count rates/MAEs and latency.
    Inputs are validated before score filtering and are never mutated.
    """
    _number(threshold, "threshold", minimum=0, maximum=1)
    _validate(records)
    totals = {label: {"tp": 0, "fp": 0, "fn": 0} for label in LABELS}
    count_errors = {label: 0 for label in LABELS}
    exact_count_images = total_count_error = 0
    for record in records:
        predictions = [item for item in record["predictions"] if item["score"] >= threshold]
        errors = []
        ground_truth = record["ground_truth"]
        for label in LABELS:
            truth = [item for item in ground_truth if item["label"] == label]
            proposed = sorted(
                (item for item in predictions if item["label"] == label),
                key=lambda item: item["score"], reverse=True,
            )
            unmatched = set(range(len(truth)))
            matched = 0
            for prediction in proposed:
                best_index, best_iou = None, -1.0
                for index in sorted(unmatched):
                    overlap = _iou(prediction["box"], truth[index]["box"])
                    if overlap > best_iou:
                        best_index, best_iou = index, overlap
                if best_index is not None and best_iou >= 0.5:
                    unmatched.remove(best_index)
                    matched += 1
            totals[label]["tp"] += matched
            totals[label]["fp"] += len(proposed) - matched
            totals[label]["fn"] += len(truth) - matched
            error = abs(len(proposed) - len(truth))
            count_errors[label] += error
            errors.append(error)
        exact_count_images += not any(errors)
        total_count_error += abs(len(predictions) - len(ground_truth))
    images = len(records)
    per_class = {label: _detection_metrics(**totals[label]) for label in LABELS}
    return {
        **_detection_metrics(**{key: sum(totals[label][key] for label in LABELS)
                               for key in ("tp", "fp", "fn")}),
        "per_class": per_class,
        "images": images,
        "exact_count_images": exact_count_images,
        "exact_count_accuracy": exact_count_images / images if images else None,
        "count_mae_per_class": {
            label: count_errors[label] / images if images else None for label in LABELS
        },
        "mean_absolute_total_count_error": total_count_error / images if images else None,
        "latency_median_seconds": statistics.median(
            record["inference_seconds"] for record in records
        ) if images else None,
    }


def select_threshold(records, thresholds=DEFAULT_THRESHOLDS):
    """Select using validation records only; callers must enforce split isolation.

    Rank by exact-count accuracy, lower mean class count MAE, detection F1,
    then higher threshold. Return {threshold, metrics, sweep}; sweep retains
    the supplied threshold order. Never invoke this function on the test set.
    """
    _validate(records)
    if not records:
        raise ValueError("threshold selection requires nonempty validation records")
    if not isinstance(thresholds, (list, tuple)) or not thresholds:
        raise ValueError("thresholds must be a nonempty list or tuple")
    for threshold in thresholds:
        _number(threshold, "threshold", minimum=0, maximum=1)
    if len(set(thresholds)) != len(thresholds):
        raise ValueError("thresholds must be unique")
    sweep = [{"threshold": threshold, "metrics": evaluate(records, threshold)}
             for threshold in thresholds]

    def rank(row):
        metrics = row["metrics"]
        return (
            metrics["exact_count_accuracy"],
            -sum(metrics["count_mae_per_class"].values()) / len(LABELS),
            metrics["f1"],
            row["threshold"],
        )

    best = max(sweep, key=rank)
    return {"threshold": best["threshold"], "metrics": best["metrics"], "sweep": sweep}
