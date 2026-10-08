"""Engineering fixtures for the recorder, not physical or model accuracy data."""

import copy
import json

import pytest

from kitguard.field_study import commitment


def prepared(client, order, upload, *, truth=None, cases=1):
    photo = upload(order).json()["photo"]
    response = client.post("/api/studies", json={
        "title": "ENGINEERING ONLY", "source_kind": "engineering_fixture", "planned_cases": cases,
        "participant_code": "synthetic-001", "note": "No physical validation or real inference",
    })
    assert response.status_code == 201
    study = response.json()["study"]
    truth = truth or order["requirements"]
    added = client.post(f'/api/studies/{study["id"]}/cases', json={
        "label": "SYNTHETIC", "order_id": order["id"], "expected_revision": 1, "photo_id": photo["id"],
        "truth": truth, "truth_repeat": truth, "confirmed_independent": True,
        "source_note": "Generated engineering pixels with injected test double",
    })
    assert added.status_code == 201, added.text
    return added.json()["study"], photo


def freeze(client, study):
    result = client.post(f'/api/studies/{study["id"]}/freeze', json={"confirmed": True})
    assert result.status_code == 200, result.text
    return result.json()["study"]


def start(client, study, method):
    result = client.post(f'/api/studies/{study["id"]}/cases/{study["cases"][0]["id"]}/start', json={"method": method})
    assert result.status_code == 200, result.text
    return result.json()["trial"]


def finish(client, study, trial, **body):
    return client.post(f'/api/studies/{study["id"]}/trials/{trial["id"]}/finish', json=body)


def test_complete_paired_flow_seals_truth_and_scores_actual_check(client, order, upload, analyzer):
    truth = {**order["requirements"], "bolt": 1}
    study, photo = prepared(client, order, upload, truth=truth)
    frozen = freeze(client, study)
    assert frozen["runtime_identity"] and frozen["protocol_sha256"]
    assert "truth" not in frozen["cases"][0] and frozen["report"] is None
    manual = start(client, study, "manual")
    saved = finish(client, study, manual, outcome="completed", manual_counts=truth)
    assert saved.status_code == 200
    ai = start(client, study, "kitguard")
    checked = client.post(f'/api/orders/{order["id"]}/inspect', json={"photo_id": photo["id"], "expected_revision": 1})
    assert checked.status_code == 200
    check = checked.json()["check"]
    # The injected engine returns requested quantities, producing a false ready against the independent truth.
    assert check["decision"] == "ready"
    assert finish(client, study, ai, outcome="completed", check_id=check["id"]).status_code == 200
    assert len(analyzer.calls) == 1
    assert analyzer.calls[0]["requirements"] == order["requirements"]
    closed = client.post(f'/api/studies/{study["id"]}/close', json={"confirmed": True}).json()["study"]
    case = closed["cases"][0]
    assert commitment(case["truth"], case["truth_nonce"]) == case["truth_commitment"]
    report = closed["report"]
    assert report["paired_completed_cases"] == 1
    assert report["methods"]["manual"]["correct"] == 1
    metrics = report["methods"]["kitguard"]
    assert metrics["correct"] == 0 and metrics["wrong"] == 1
    assert metrics["false_ready"] == {"numerator": 1, "denominator": 1}
    assert metrics["returned_checks"]["wrong_clear"] == metrics["returned_checks"]["false_ready"] == 1
    assert metrics["terminal_elapsed_ms"]["n"] == 1
    assert client.get(f'/api/studies/{study["id"]}/export').json()["study"] == closed
    assert "self_reported_physical" not in client.get(f'/api/studies/{study["id"]}/report.html').text
    assert finish(client, study, ai, outcome="completed", check_id=check["id"]).status_code == 409


def test_no_truth_reveal_through_list_start_or_export_before_close(client, order, upload):
    study, _ = prepared(client, order, upload)
    freeze(client, study)
    trial = start(client, study, "manual")
    for value in [client.get("/api/studies").json(), client.get(f'/api/studies/{study["id"]}').json(), trial]:
        text = json.dumps(value)
        assert '"truth":' not in text and '"truth_nonce":' not in text and '"_monotonic_started":' not in text
    for path in ["export", "report.html"]:
        assert client.get(f'/api/studies/{study["id"]}/{path}').status_code == 409


def test_manual_is_required_before_ai_and_no_double_start(client, order, upload):
    study, _ = prepared(client, order, upload)
    freeze(client, study)
    endpoint = f'/api/studies/{study["id"]}/cases/{study["cases"][0]["id"]}/start'
    assert client.post(endpoint, json={"method": "kitguard"}).status_code == 409
    manual = start(client, study, "manual")
    assert client.post(endpoint, json={"method": "manual"}).status_code == 409
    assert client.post(endpoint, json={"method": "kitguard"}).status_code == 409
    assert finish(client, study, manual, outcome="abandoned", note="Synthetic operator stopped").status_code == 200
    assert client.post(endpoint, json={"method": "manual"}).status_code == 409
    start(client, study, "kitguard")


def test_closed_draft_keeps_missing_cases_and_cannot_restart(client, order, upload):
    study, _ = prepared(client, order, upload, cases=3)
    assert client.post(f'/api/studies/{study["id"]}/freeze', json={"confirmed": True}).status_code == 409
    closed = client.post(f'/api/studies/{study["id"]}/close', json={"confirmed": True}).json()["study"]
    assert closed["frozen_at"] is None
    for method in closed["report"]["methods"].values():
        assert method["planned"] == method["not_started"] == 3
        assert method["correct_fraction"] is None
    assert client.post(f'/api/studies/{study["id"]}/close', json={"confirmed": True}).status_code == 409


@pytest.mark.parametrize("change", [{"confirmed": 1}, {"confirmed": "true"}, {"confirmed": False}, {"confirmed": True, "extra": 1}])
def test_confirm_must_be_explicit_strict_true(client, order, upload, change):
    study, _ = prepared(client, order, upload)
    assert client.post(f'/api/studies/{study["id"]}/freeze', json=change).status_code == 422


@pytest.mark.parametrize("mutation", ["mismatch", "bool_count", "extra_count", "false_confirmation"])
def test_independent_truth_input_must_match_and_be_strict(client, order, upload, mutation):
    photo = upload(order).json()["photo"]
    study = client.post("/api/studies", json={"title": "TEST", "planned_cases": 1,
                        "participant_code": "test", "source_kind": "engineering_fixture"}).json()["study"]
    body = {"label": "TEST", "order_id": order["id"], "expected_revision": 1, "photo_id": photo["id"],
            "truth": copy.deepcopy(order["requirements"]), "truth_repeat": copy.deepcopy(order["requirements"]),
            "confirmed_independent": True, "source_note": "ENGINEERING"}
    if mutation == "mismatch":
        body["truth_repeat"]["bolt"] += 1
    elif mutation == "bool_count":
        body["truth"]["bolt"] = True
    elif mutation == "extra_count":
        body["truth"]["other"] = 1
    else:
        body["confirmed_independent"] = 1
    assert client.post(f'/api/studies/{study["id"]}/cases', json=body).status_code == 422


def test_runtime_change_after_freeze_prevents_start(client, order, upload, analyzer):
    study, _ = prepared(client, order, upload)
    freeze(client, study)
    original = analyzer.status
    analyzer.status = lambda: {**original(), "revision": "DIFFERENT"}
    # FieldStudies captured the bound status method at app construction, so mutate that provider explicitly.
    client.app.state.studies.runtime_provider = analyzer.status
    response = client.post(f'/api/studies/{study["id"]}/cases/{study["cases"][0]["id"]}/start', json={"method": "manual"})
    assert response.status_code == 409


def test_close_running_trial_keeps_actual_returned_error(client, order, upload):
    truth = {**order["requirements"], "bolt": 1}
    study, photo = prepared(client, order, upload, truth=truth)
    freeze(client, study)
    manual = start(client, study, "manual")
    finish(client, study, manual, outcome="completed", manual_counts=truth)
    start(client, study, "kitguard")
    client.post(f'/api/orders/{order["id"]}/inspect', json={"photo_id": photo["id"], "expected_revision": 1})
    closed = client.post(f'/api/studies/{study["id"]}/close', json={"confirmed": True}).json()["study"]
    metrics = closed["report"]["methods"]["kitguard"]
    assert metrics["abandoned"] == 1 and metrics["wrong"] == 0
    assert metrics["returned_checks"]["wrong_clear"] == metrics["returned_checks"]["false_ready"] == 1
    assert metrics["terminal_elapsed_ms"]["n"] == 1
