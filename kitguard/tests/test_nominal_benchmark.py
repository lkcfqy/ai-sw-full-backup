"""A constant-count shortcut must fail on author-labeled quantity anomalies."""

from test_evaluation import case, observation

from kitguard.evaluation import score_case, summarize


def test_constant_nominal_guess_exposes_all_variable_count_anomalies():
    nominal = {"bolt": 2, "nut": 2, "washer": 2, "bracket": 0}
    normal = {**case(), "ground_truth": nominal, "nominal_requirements": nominal, "subgroup": "normal"}
    anomaly = {
        **normal,
        "id": "anomaly",
        "source_id": "source-2",
        "sha256": "b" * 64,
        "ground_truth": {**nominal, "washer": 3},
        "subgroup": "quantity",
    }
    rows = [score_case(c, observation(nominal), 1000) for c in [normal, anomaly]]
    summary = summarize(rows)
    assert summary["images"] == 2
    assert summary["count_exact"]["rate"] == 0.5
    assert summary["nominal_order"]["matching_images_ready"]["rate"] == 1
    assert summary["nominal_order"]["quantity_anomalies_false_ready"]["rate"] == 1
    assert summary["nominal_order"]["constant_nominal_baseline"]["count_exact"]["rate"] == 0.5
    assert summary["subgroups"]["quantity"]["count_exact"]["rate"] == 0
    assert summary["subgroups"]["normal"]["count_exact"]["rate"] == 1


def test_correct_anomaly_count_produces_correct_adjustment_for_nominal_order():
    c = {
        **case(),
        "nominal_requirements": {"bolt": 2, "nut": 2, "washer": 0, "bracket": 0},
        "subgroup": "quantity",
    }
    summary = summarize([score_case(c, observation(c["ground_truth"]), 1000)])
    assert summary["nominal_order"]["quantity_anomalies_correct_adjustment"]["rate"] == 1
    assert summary["nominal_order"]["quantity_anomalies_false_ready"]["rate"] == 0


def test_nominal_refusal_is_not_a_success_and_stays_in_denominator():
    c = {**case(), "nominal_requirements": {"bolt": 2, "nut": 2, "washer": 0, "bracket": 0}}
    summary = summarize([score_case(c, None, 1000, "failure")])
    assert summary["nominal_order"]["quantity_anomalies_correct_adjustment"]["rate"] == 0
    assert summary["nominal_order"]["quantity_anomalies_false_ready"]["denominator"] == 1


def test_nominal_order_does_not_make_out_of_scope_truth_a_supported_matching_order():
    c = {
        **case(),
        "ground_truth": {"bolt": 4, "nut": 0, "washer": 0, "bracket": 0},
        "nominal_requirements": {"bolt": 2, "nut": 0, "washer": 0, "bracket": 0},
    }
    row = score_case(c, observation(c["ground_truth"]), 1000)
    summary = summarize([row])
    assert not row["in_product_scope"]
    assert [t["kind"] for t in row["tasks"]] == ["nominal"]
    assert summary["order_eligible_images"] == 0
    assert summary["order_out_of_scope_images"] == 1
    assert summary["nominal_order_eligible_images"] == 1
    assert summary["matched_order_ready"]["denominator"] == 0
