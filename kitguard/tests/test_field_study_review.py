"""Independent adversarial collection-protocol checks; synthetic fixtures, no GPU."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

import pytest
from conftest import REQUIREMENTS


def _study(client, *, planned=1, title="Independent protocol review", source="engineering_fixture"):
    response = client.post("/api/studies", json={
        "title": title, "source_kind": source, "planned_cases": planned,
        "participant_code": "review_operator", "note": "Synthetic engineering fixture only",
    })
    assert response.status_code == 201, response.text
    return response.json()["study"]


def _register(client, study, order, photo, *, truth=None, label="Synthetic fixed state"):
    counts = deepcopy(REQUIREMENTS if truth is None else truth)
    response = client.post(f"/api/studies/{study['id']}/cases", json={
        "label": label, "order_id": order["id"], "expected_revision": order["revision"],
        "photo_id": photo["id"], "truth": counts, "truth_repeat": counts,
        "confirmed_independent": True, "source_note": "Synthetic fixture, no physical study",
    })
    assert response.status_code == 201, response.text
    return response.json()["study"]


def _freeze(client, study):
    response = client.post(f"/api/studies/{study['id']}/freeze", json={"confirmed": True})
    assert response.status_code == 200, response.text
    return response.json()["study"]


def _start(client, study, method):
    return client.post(f"/api/studies/{study['id']}/cases/{study['cases'][0]['id']}/start",
                       json={"method": method})


def _finish(client, study, trial, **payload):
    return client.post(f"/api/studies/{study['id']}/trials/{trial['id']}/finish", json=payload)


def _inspect(client, order, photo):
    return client.post(f"/api/orders/{order['id']}/inspect",
                       json={"photo_id": photo["id"], "expected_revision": order["revision"]})


def _prepared(client, order, upload, *, truth=None):
    uploaded = upload(order)
    assert uploaded.status_code == 201, uploaded.text
    photo = uploaded.json()["photo"]
    study = _register(client, _study(client), order, photo, truth=truth)
    return study, photo


def _finish_manual(client, study):
    started = _start(client, study, "manual")
    assert started.status_code == 200, started.text
    response = _finish(client, study, started.json()["trial"],
                       outcome="completed", manual_counts=REQUIREMENTS)
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("stage", ["before_freeze", "before_manual", "before_kitguard"])
def test_inspecting_in_other_workbench_cannot_bypass_ordered_collection(client, order, upload, stage):
    study, photo = _prepared(client, order, upload)
    if stage != "before_freeze":
        study = _freeze(client, study)
    if stage == "before_kitguard":
        _finish_manual(client, study)
    response = _inspect(client, order, photo)
    assert response.status_code == 200, response.text
    if stage == "before_freeze":
        blocked = client.post(f"/api/studies/{study['id']}/freeze", json={"confirmed": True})
    else:
        blocked = _start(client, study, "manual" if stage == "before_manual" else "kitguard")
    assert blocked.status_code == 409, blocked.text


def test_failed_early_attempt_is_exposure_even_without_a_saved_check(client, order, upload, analyzer):
    study, photo = _prepared(client, order, upload)
    analyzer.error = RuntimeError("Intentional review fixture inference failure")
    assert _inspect(client, order, photo).status_code >= 400
    frozen = client.post(f"/api/studies/{study['id']}/freeze", json={"confirmed": True})
    assert frozen.status_code == 409, frozen.text


def test_manual_completion_rejects_results_seen_after_timer_started(client, order, upload):
    study, photo = _prepared(client, order, upload)
    study = _freeze(client, study)
    started = _start(client, study, "manual")
    assert started.status_code == 200, started.text
    trial = started.json()["trial"]
    assert _inspect(client, order, photo).status_code == 200
    rejected = _finish(client, study, trial, outcome="completed", manual_counts=REQUIREMENTS)
    assert rejected.status_code == 409, rejected.text
    failed = _finish(client, study, trial, outcome="failed", note="Prior AI output contaminated manual trial")
    assert failed.status_code == 200, failed.text


@pytest.mark.parametrize("mutation", ["photo", "revision", "reference"])
def test_binding_changes_after_freeze_block_start(client, order, upload, image_bytes, mutation):
    study, _ = _prepared(client, order, upload)
    study = _freeze(client, study)
    if mutation == "photo":
        changed = upload(order, seed=7)
    elif mutation == "revision":
        changed_counts = {**REQUIREMENTS, "bolt": 1}
        changed = client.post(f"/api/orders/{order['id']}/revise", json={
            "requirements": changed_counts, "instruction": "Synthetic revision",
            "expected_revision": order["revision"],
        })
    else:
        changed = client.post(f"/api/orders/{order['id']}/references/bolt",
                             data={"expected_revision": order["revision"]},
                             files={"photo": ("reference.png", image_bytes(9), "image/png")})
    assert changed.status_code in (200, 201), changed.text
    started = _start(client, study, "manual")
    assert started.status_code == 409, started.text


def test_ai_result_cannot_be_borrowed_from_another_order(client, order, upload):
    study, _ = _prepared(client, order, upload)
    study = _freeze(client, study)
    _finish_manual(client, study)
    started = _start(client, study, "kitguard")
    assert started.status_code == 200, started.text
    other = client.post("/api/orders", json={"title": "Other fixture", "requirements": REQUIREMENTS})
    assert other.status_code == 201, other.text
    other_order = other.json()["order"]
    posted = upload(other_order, seed=8)
    assert posted.status_code == 201, posted.text
    checked = _inspect(client, other_order, posted.json()["photo"])
    assert checked.status_code == 200, checked.text
    rejected = _finish(client, study, started.json()["trial"], outcome="completed",
                       check_id=checked.json()["order"]["latest_check"]["id"])
    assert rejected.status_code == 409, rejected.text


def test_second_attempt_cannot_be_selected_as_if_it_were_first(client, order, upload, analyzer):
    study, photo = _prepared(client, order, upload)
    study = _freeze(client, study)
    _finish_manual(client, study)
    started = _start(client, study, "kitguard")
    assert started.status_code == 200, started.text
    analyzer.error = RuntimeError("First attempted inference intentionally failed")
    assert _inspect(client, order, photo).status_code >= 400
    analyzer.error = None
    successful = _inspect(client, order, photo)
    assert successful.status_code == 200, successful.text
    rejected = _finish(client, study, started.json()["trial"], outcome="completed",
                       check_id=successful.json()["order"]["latest_check"]["id"])
    assert rejected.status_code == 409, rejected.text


def test_close_unpopulated_study_retains_all_planned_slots(client):
    study = _study(client, planned=3)
    closed = client.post(f"/api/studies/{study['id']}/close", json={"confirmed": True})
    assert closed.status_code == 200, closed.text
    report = closed.json()["study"]["report"]
    assert report["registered_cases"] == 0
    for metrics in report["methods"].values():
        assert metrics["planned"] == 3
        assert metrics["started"] == 0
        assert metrics["not_started"] == 3
        assert metrics["correct_fraction"] is None


def test_truth_not_returned_before_close_and_report_escapes_untrusted_title(client, order, upload):
    attack = '</script><script>alert("review-fixture")</script>'
    photo = upload(order).json()["photo"]
    study = _register(client, _study(client, title=attack), order, photo)
    study = _freeze(client, study)
    case = study["cases"][0]
    assert "truth" not in case
    assert "truth_nonce" not in case
    assert study["report"] is None
    assert client.get(f"/api/studies/{study['id']}/export").status_code == 409
    assert client.get(f"/api/studies/{study['id']}/report.html").status_code == 409
    closed = client.post(f"/api/studies/{study['id']}/close", json={"confirmed": True})
    assert closed.status_code == 200, closed.text
    assert closed.json()["study"]["cases"][0]["truth"] == REQUIREMENTS
    exported = client.get(f"/api/studies/{study['id']}/report.html")
    assert exported.status_code == 200, exported.text
    assert attack not in exported.text
    assert "&lt;script&gt;" in exported.text


@pytest.mark.parametrize("outcome", ["failed", "abandoned", "close"])
def test_returned_wrong_ready_survives_every_noncompleted_terminal_path(client, order, upload, outcome):
    truth = {**REQUIREMENTS, "bolt": 1}
    study, photo = _prepared(client, order, upload, truth=truth)
    study = _freeze(client, study)
    _finish_manual(client, study)
    started = _start(client, study, "kitguard")
    assert started.status_code == 200, started.text
    checked = _inspect(client, order, photo)
    assert checked.status_code == 200, checked.text
    assert checked.json()["order"]["latest_check"]["decision"] == "ready"
    if outcome != "close":
        terminal = _finish(client, study, started.json()["trial"], outcome=outcome,
                           note="Operator declined a returned wrong result; preserve evidence")
        assert terminal.status_code == 200, terminal.text
    closed = client.post(f"/api/studies/{study['id']}/close", json={"confirmed": True})
    assert closed.status_code == 200, closed.text
    metrics = closed.json()["study"]["report"]["methods"]["kitguard"]
    assert metrics["started"] == 1
    assert metrics["returned_checks"]["total"] == 1
    assert metrics["returned_checks"]["scorable"] == 1
    assert metrics["returned_checks"]["wrong_clear"] == 1
    assert metrics["returned_checks"]["false_ready"] == 1
    trial = closed.json()["study"]["cases"][0]["trials"]["kitguard"]
    assert len(trial["evidence"]["checks"]) == 1


def test_restart_preserves_wrong_return_and_uses_unknown_elapsed(client, order, upload, analyzer):
    from kitguard.field_study import FieldStudies

    truth = {**REQUIREMENTS, "bolt": 1}
    study, photo = _prepared(client, order, upload, truth=truth)
    study = _freeze(client, study)
    _finish_manual(client, study)
    started = _start(client, study, "kitguard")
    assert started.status_code == 200, started.text
    assert _inspect(client, order, photo).status_code == 200
    replacement_process = FieldStudies(client.app.state.store, analyzer.status)
    replacement_process.recover_interrupted()
    refused = _finish(client, study, started.json()["trial"], outcome="failed", note="Old process request")
    assert refused.status_code == 409, refused.text
    closed = client.post(f"/api/studies/{study['id']}/close", json={"confirmed": True})
    assert closed.status_code == 200, closed.text
    record = closed.json()["study"]
    trial = record["cases"][0]["trials"]["kitguard"]
    assert trial["status"] == "interrupted"
    assert trial["elapsed_ms"] is None
    assert "_process_nonce" not in trial
    assert "_monotonic_started" not in trial
    metrics = record["report"]["methods"]["kitguard"]
    assert metrics["interrupted"] == 1
    assert metrics["terminal_elapsed_ms"]["n"] == 0
    assert metrics["returned_checks"]["wrong_clear"] == 1


def test_rejected_test_backend_stays_unscorable_when_operator_selects_failed(client, order, upload):
    photo = upload(order).json()["photo"]
    truth = {**REQUIREMENTS, "bolt": 1}
    study = _register(client, _study(client, source="self_reported_physical"), order, photo, truth=truth)
    study = _freeze(client, study)
    _finish_manual(client, study)
    started = _start(client, study, "kitguard")
    assert started.status_code == 200, started.text
    checked = _inspect(client, order, photo)
    assert checked.status_code == 200, checked.text
    rejected = _finish(client, study, started.json()["trial"], outcome="completed",
                       check_id=checked.json()["order"]["latest_check"]["id"])
    assert rejected.status_code == 409, rejected.text
    failed = _finish(client, study, started.json()["trial"], outcome="failed", note="Test backend was rejected")
    assert failed.status_code == 200, failed.text
    closed = client.post(f"/api/studies/{study['id']}/close", json={"confirmed": True})
    assert closed.status_code == 200, closed.text
    metrics = closed.json()["study"]["report"]["methods"]["kitguard"]
    assert metrics["failed"] == 1
    assert metrics["returned_checks"]["total"] == 1
    assert metrics["returned_checks"]["scorable"] == 0
    assert metrics["returned_checks"]["wrong_clear"] == 0
    assert metrics["returned_checks"]["false_ready"] == 0


@pytest.mark.parametrize("stage", ["before_freeze", "before_manual", "before_kitguard"])
def test_same_photo_in_another_order_cannot_create_hidden_early_exposure(client, order, upload, stage):
    photo = upload(order).json()["photo"]
    study = _register(client, _study(client, source="self_reported_physical"), order, photo)
    if stage != "before_freeze":
        study = _freeze(client, study)
    if stage == "before_kitguard":
        _finish_manual(client, study)
    other_response = client.post("/api/orders", json={"title": "Copy of same photo", "requirements": REQUIREMENTS})
    assert other_response.status_code == 201, other_response.text
    other = other_response.json()["order"]
    other_photo = upload(other).json()["photo"]
    assert other_photo["sha256"] == photo["sha256"]
    assert _inspect(client, other, other_photo).status_code == 200
    if stage == "before_freeze":
        blocked = client.post(f"/api/studies/{study['id']}/freeze", json={"confirmed": True})
    else:
        blocked = _start(client, study, "manual" if stage == "before_manual" else "kitguard")
    assert blocked.status_code == 409, blocked.text


def test_sealed_truth_never_replaces_requirements_in_inference(client, order, upload, analyzer):
    truth = {"bolt": 0, "nut": 0, "washer": 0, "bracket": 0}
    study, photo = _prepared(client, order, upload, truth=truth)
    study = _freeze(client, study)
    _finish_manual(client, study)
    started = _start(client, study, "kitguard")
    assert started.status_code == 200, started.text
    assert _inspect(client, order, photo).status_code == 200
    assert len(analyzer.calls) == 1
    assert analyzer.calls[0]["requirements"] == REQUIREMENTS
    assert "truth" not in analyzer.calls[0]
    assert "ground_truth" not in analyzer.calls[0]


def test_manual_trial_cannot_finish_after_same_photo_was_inferred_elsewhere(client, order, upload):
    photo = upload(order).json()["photo"]
    study = _register(client, _study(client, source="self_reported_physical"), order, photo)
    study = _freeze(client, study)
    started = _start(client, study, "manual")
    assert started.status_code == 200, started.text
    other = client.post("/api/orders", json={"title": "Parallel answer source", "requirements": REQUIREMENTS}).json()["order"]
    other_photo = upload(other).json()["photo"]
    assert other_photo["sha256"] == photo["sha256"]
    assert _inspect(client, other, other_photo).status_code == 200
    rejected = _finish(client, study, started.json()["trial"], outcome="completed", manual_counts=REQUIREMENTS)
    assert rejected.status_code == 409, rejected.text


def test_changed_photo_file_bytes_are_rejected_even_with_same_database_id(client, order, upload):
    study, photo = _prepared(client, order, upload)
    path = client.app.state.store.photo_path(photo["id"])
    path.write_bytes(path.read_bytes() + b"synthetic-integrity-tamper")
    blocked = client.post(f"/api/studies/{study['id']}/freeze", json={"confirmed": True})
    assert blocked.status_code == 409, blocked.text


@pytest.mark.parametrize("terminal_action", ["failed", "abandoned", "close"])
def test_active_inference_cannot_be_closed_before_its_wrong_result_is_retained(
    client, order, upload, analyzer, terminal_action
):
    study, photo = _prepared(client, order, upload, truth={**REQUIREMENTS, "bolt": 1})
    study = _freeze(client, study)
    _finish_manual(client, study)
    started = _start(client, study, "kitguard")
    assert started.status_code == 200, started.text
    analyzer.release.clear()
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(_inspect, client, order, photo)
        try:
            assert analyzer.started.wait(timeout=3), "Fixture observer did not begin"
            if terminal_action == "close":
                blocked = client.post(f"/api/studies/{study['id']}/close", json={"confirmed": True})
            else:
                blocked = _finish(client, study, started.json()["trial"], outcome=terminal_action,
                                  note="Attempt to discard while a real check is still pending")
        finally:
            analyzer.release.set()
        checked = pending.result(timeout=3)
    assert checked.status_code == 200, checked.text
    assert checked.json()["order"]["latest_check"]["decision"] == "ready"
    assert blocked.status_code == 409, blocked.text
    closed = client.post(f"/api/studies/{study['id']}/close", json={"confirmed": True})
    assert closed.status_code == 200, closed.text
    metrics = closed.json()["study"]["report"]["methods"]["kitguard"]
    assert metrics["returned_checks"]["wrong_clear"] == 1
    assert metrics["returned_checks"]["false_ready"] == 1


def test_recorder_source_change_during_running_trial_blocks_successful_finish(client, order, upload, monkeypatch):
    from kitguard import field_study

    study, _ = _prepared(client, order, upload)
    study = _freeze(client, study)
    started = _start(client, study, "manual")
    assert started.status_code == 200, started.text
    source_bytes = Path(field_study.__file__).read_bytes()
    original_sha = field_study.sha
    monkeypatch.setattr(field_study, "sha", lambda value: "f" * 64 if value == source_bytes else original_sha(value))
    rejected = _finish(client, study, started.json()["trial"], outcome="completed", manual_counts=REQUIREMENTS)
    assert rejected.status_code == 409, rejected.text
    failed = _finish(client, study, started.json()["trial"], outcome="failed", note="Recorder source changed")
    assert failed.status_code == 200, failed.text


def test_known_public_photo_does_not_become_physical_when_reuploaded(client, order, upload):
    store = client.app.state.store
    public_order = client.app.state.store.create(
        "SYNTHETIC public provenance fixture", REQUIREMENTS,
    )
    public_photo = upload(public_order).json()["photo"]
    # Seed an already-registered legacy public source. Ordinary uploads to public
    # catalog orders are now rejected before writing, so fixture construction
    # must not depend on the removed upload path.
    with store.transaction(public_order["id"]) as (_, stored):
        stored["demo_source"] = {"kind": "public_photo_demo", "physical_completion_allowed": False}
    public_order = store.get(public_order["id"])
    assert upload(public_order).status_code == 409
    assert store.get(public_order["id"]) == public_order
    ordinary_photo = upload(order).json()["photo"]
    assert ordinary_photo["sha256"] == public_photo["sha256"]
    study = _study(client, source="self_reported_physical")
    rejected = client.post(f"/api/studies/{study['id']}/cases", json={
        "label": "Reuploaded known public pixels", "order_id": order["id"],
        "expected_revision": order["revision"], "photo_id": ordinary_photo["id"],
        "truth": REQUIREMENTS, "truth_repeat": REQUIREMENTS,
        "confirmed_independent": True, "source_note": "Synthetic public provenance review",
    })
    assert rejected.status_code == 409, rejected.text
