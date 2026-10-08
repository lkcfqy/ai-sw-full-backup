"""Check evaluation denominators and avoid reporting refusals as successes."""

import json

import pytest

from kitguard.evaluation import order_tasks, read_manifest, score_case, summarize, wilson_interval


def case():
    return {
        "id": "engineering-case",
        "source_id": "source-1",
        "image": "image.png",
        "sha256": "a" * 64,
        "split": "development",
        "ground_truth": {"bolt": 2, "nut": 1, "washer": 0, "bracket": 0},
    }


def observation(counts, *, uncertain=False):
    return {
        "observed": counts,
        "issues": ["Cannot see all parts"] if uncertain else [],
        "action": {
            "kind": "recapture" if uncertain else "none",
            "message": "Engineering fixture",
            "region": None,
        },
        "backend": "test",
    }


def test_refusal_and_failure_remain_in_denominators():
    item = case()
    rows = [
        score_case(item, observation(item["ground_truth"]), 1000),
        score_case(item, observation({p: None for p in item["ground_truth"]}, uncertain=True), 2000),
        score_case(item, None, 3000, "model failed"),
    ]
    summary = summarize(rows)
    assert summary["images"] == 3
    assert summary["count_exact"]["numerator"] == 1
    assert summary["count_exact"]["denominator"] == 3
    assert summary["errors"]["numerator"] == 1
    assert summary["matched_order_ready"]["rate"] == 1 / 3
    assert summary["mismatched_order_false_ready"]["rate"] == 0
    assert summary["latency_ms"]["median"] == 2000


def test_wrong_count_can_be_a_false_ready_on_the_mismatched_order():
    item = case()
    wrong = dict(item["ground_truth"], bolt=3)
    row = score_case(item, observation(wrong), 1000)
    assert row["counts_exact"] is False
    assert row["actionable_counts"] is True
    assert row["tasks"][1]["false_ready"] is True
    assert summarize([row])["wrong_actionable_count"]["rate"] == 1


def test_exact_but_uncertain_observation_does_not_claim_readiness():
    item = case()
    row = score_case(item, observation(item["ground_truth"], uncertain=True), 1000)
    assert row["counts_exact"] is True
    assert row["actionable_counts"] is False
    assert not any(task["correct_ready"] for task in row["tasks"])


def test_out_of_scope_truth_does_not_create_false_matched_task():
    assert order_tasks({"bolt": 4, "nut": 1, "washer": 0, "bracket": 0}) == []
    assert order_tasks({"bolt": 0, "nut": 0, "washer": 0, "bracket": 0}) == []
    tasks = order_tasks({"bolt": 3, "nut": 3, "washer": 3, "bracket": 3})
    assert len(tasks) == 2
    assert sum(tasks[1]["requirements"].values()) == 11


def test_empty_summary_is_unknown_not_zero_accuracy():
    summary = summarize([])
    assert summary["count_exact"]["rate"] is None
    assert summary["count_exact"]["wilson_95"] is None
    assert wilson_interval(0, 10)[1] > 0.27  # Zero observed failures does not prove zero risk.


def test_manifest_rejects_cross_split_same_original(tmp_path):
    first = case()
    second = dict(first, id="second", split="holdout", sha256="b" * 64)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"schema_version": 1, "cases": [first, second]}))
    with pytest.raises(ValueError, match="leaks"):
        read_manifest(path)
