"""Independent audit contracts, with tiny synthetic predictions only."""
import json

import pytest

from scripts.v08 import audit_grouped_detector_training as a


def case(key, source="foda", group="g", label=3):
    return {"id": key, "source": source, "group_id": group, "source_sha256": key,
            "image_size": [100, 100], "ground_truth": [{"label": label, "box": [10, 10, 20, 20], "annotation_id": 1}]}


def raw(record, predictions):
    return {"status": "ok", "id": record["id"], "ground_truth": record["ground_truth"],
            "image_sha256": record["source_sha256"], "predictions": predictions}


def pred(label=3, score=.5, box=None):
    return {"label": label, "score": score, "box": box or [10, 10, 20, 20]}


def test_raw_threshold_boundary_and_duplicate_box_false_positive():
    record = case("a")
    result = a.case_metric(record, raw(record, [pred(score=.5), pred(score=.4)]), .5)
    assert result["exact_count"] and result["per_class"]["washer"]["tp"] == 1
    result = a.case_metric(record, raw(record, [pred(score=.5), pred(score=.5)]), .5)
    assert result["matches"][0]["prediction_index"] == 0
    assert result["false_positive_indices"] == [1]
    assert not result["exact_count"]


def test_wrong_class_and_wrong_position_retain_distinct_errors():
    record = case("a")
    result = a.case_metric(record, raw(record, [pred(label=2)]), .5)
    assert result["per_class"]["nut"]["fp"] == result["per_class"]["washer"]["fn"] == 1
    result = a.case_metric(record, raw(record, [pred(box=[30, 30, 40, 40])]), .5)
    assert result["exact_count"]
    assert result["per_class"]["washer"]["tp"] == 0


def test_group_macro_is_independent_of_frame_count():
    records = [case("s", "screws"), case("one", group="one")]
    records += [case(str(i), group="many") for i in range(9)]
    raws = [raw(r, [] if r["group_id"] == "many" else [pred()]) for r in records]
    metric = a.recompute(records, raws, .5)
    assert metric["balanced_exact_count_accuracy"] == .75
    assert metric["foda"]["exact_count_accuracy"] == .1
    assert metric["balanced_class_count_mae"] == pytest.approx(1 / 12)


@pytest.mark.parametrize("actual,expected", [({"tp": True}, {"tp": 1}), ({"tp": 2}, {"tp": 1}),
                                            ({"x": .5}, {"x": .5001}), ({"x": .5, "y": 0}, {"x": .5})])
def test_summary_tampering_is_not_accepted(actual, expected):
    with pytest.raises(ValueError):
        a.same(actual, expected)


@pytest.mark.parametrize("mutation", ["missing", "failed", "input", "truth"])
def test_validation_cannot_omit_failures_or_replace_input_and_truth(mutation):
    records = [case("s", "screws"), case("f")]
    values = [raw(r, [pred()]) for r in records]
    if mutation == "missing":
        values.pop()
    elif mutation == "failed":
        values[0]["status"] = "failed"
    elif mutation == "input":
        values[0]["image_sha256"] = "other"
    else:
        values[0]["ground_truth"] = []
    with pytest.raises(ValueError):
        a.recompute(records, values, .5)


def test_incomplete_run_is_rejected_before_any_runtime_or_model_import(tmp_path):
    for name, content in (("run.json", {"status": "running", "epochs_completed": 11}),
                          ("protocol.json", {}), ("preflight.json", {})):
        (tmp_path / name).write_text(json.dumps(content))
    with pytest.raises(ValueError, match="complete twelve"):
        a.audit(tmp_path, inspect_checkpoints=True)
