import copy

import pytest

from scripts.v08 import audit_three_class_shadow as a


def base():
    return {"observed": {"bolt": 1, "nut": 1, "washer": 1, "bracket": 0}, "issues": [],
            "action": {"kind": "none"}, "object_evidence": {"uncertain_parts": [], "objects": []}}


def test_threshold_inclusive_and_cross_class_overlaps_do_not_suppress():
    raw = {"labels": [2, 3], "scores": [.5, .5], "boxes": [[1, 1, 5, 5], [1, 1, 5, 5]]}
    r = a.detector(raw, .5, [10, 10])
    assert r["counts"] == {"bolt": 0, "nut": 1, "washer": 1}
    assert r["cross_class_overlaps"] == [{"indices": [0, 1], "iou": 1.0, "both_retained": True}]
    assert a.detector(raw, .6, [10, 10])["counts"] == {"bolt": 0, "nut": 0, "washer": 0}


def test_equal_or_smaller_counts_do_not_repair_or_veto():
    b = base()
    r, triggers = a.fusion(b, {"counts": {"bolt": 99, "nut": 0, "washer": 1}, "predictions": []})
    assert r == b and triggers == []


def test_known_exceeded_makes_both_unknown_and_preserves_evidence():
    b = base()
    original = copy.deepcopy(b)
    r, triggers = a.fusion(b, {"counts": {"nut": 2, "washer": 0}, "predictions": []})
    assert b == original
    assert r["observed"] == {"bolt": 1, "nut": None, "washer": None, "bracket": 0}
    assert len(triggers) == 1 and r["object_evidence"] == b["object_evidence"]
    assert r["action"] == b["action"] and a.outcome(r, original["observed"]) == "U"


@pytest.mark.parametrize("value,uncertain", [(None, []), (True, []), (1, ["nut"])])
def test_unknown_or_boolean_is_not_known_count(value, uncertain):
    b = base()
    b["observed"]["nut"] = value
    b["object_evidence"]["uncertain_parts"] = uncertain
    r, triggers = a.fusion(b, {"counts": {"nut": 50, "washer": 1}, "predictions": []})
    assert r == b and not triggers


def test_all_four_false_ready_can_exist_when_narrow_panel_is_zero():
    case = {"ground_truth": {"bolt": 1, "nut": 1, "washer": 0, "bracket": 0},
            "supported_positive_classes": ["bolt", "nut"]}
    r = a.risk(case, base())
    assert r["all_four"]["any_false_ready"] is True
    assert r["source_supported"]["any_false_ready"] is False
    b = base()
    b["issues"] = ["uncertain"]
    assert a.risk(case, b)["all_four"]["any_false_ready"] is False
