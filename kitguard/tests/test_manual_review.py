"""Isolated state-machine fixtures, never physical or model-accuracy evidence."""

import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from io import BytesIO
from zipfile import ZipFile

import pytest
from conftest import REQUIREMENTS

from kitguard.manual_review import create_manual_review_router
from kitguard.store import StateError, Store


@pytest.fixture(autouse=True)
def manual_routes(client):
    # Also works while the main app integrates this independently owned router.
    path = "/api/orders/{order_id}/manual-review"
    if not any(getattr(route, "path", None) == path for route in client.app.routes):
        client.app.include_router(create_manual_review_router(client.app.state.store, lambda order: None))


def stored_body(client, order):
    with client.app.state.store.connect() as db:
        return db.execute("SELECT body FROM orders WHERE id=?", (order["id"],)).fetchone()["body"]


def current(client, order):
    """Compare persisted state separately from the GET-only feedback projection."""
    before = stored_body(client, order)
    result = client.get(f"/api/orders/{order['id']}")
    assert result.status_code == 200, result.text
    viewed = result.json()["order"]
    feedback = viewed.pop("digital_review_feedback")
    assert feedback["schema_version"] == 1
    assert feedback["status"] == "not_applicable"  # these are physical/manual-state fixtures
    assert "digital_review_feedback" not in json.loads(before)
    assert viewed == json.loads(before)
    assert stored_body(client, order) == before  # GET must not write even the same logical order again
    return viewed


def body(order, **changes):
    check = order.get("latest_check")
    current_check = check if check and check.get("valid") and check.get("evidence_epoch") == order["evidence_epoch"] else None
    return {
        "expected_revision": order["revision"], "expected_evidence_epoch": order["evidence_epoch"],
        "photo_id": order["photos"][-1]["id"], "check_id": current_check["id"] if current_check else None,
        "actual_counts": dict(REQUIREMENTS), "operator_code": "fixture-operator",
        "reason": "Synthetic contract test, not a physical verification",
        "confirmed_physical": True, "confirmed_current_bom": True,
        "idempotency_key": "manual-review-test", **changes,
    }


def review(client, order, request=None, *, concurrent=False, **changes):
    before = stored_body(client, order)
    result = client.post(f"/api/orders/{order['id']}/manual-review", json=request or body(order, **changes))
    if result.status_code >= 400 and not concurrent:
        assert stored_body(client, order) == before
    return result


def reopen_body(order, **changes):
    return {"expected_revision": order["revision"], "reason": "Synthetic explicit reopening",
            "confirmed": True, "idempotency_key": "reopen-test-key", **changes}


def reopen(client, order, request=None, **changes):
    before = stored_body(client, order)
    result = client.post(f"/api/orders/{order['id']}/reopen", json=request or reopen_body(order, **changes))
    if result.status_code >= 400:
        assert stored_body(client, order) == before
    return result


@pytest.mark.parametrize("matches", [True, False])
def test_offline_archive_exposes_human_outcome_without_claiming_ai_success(client, order, upload, matches):
    order = upload(order).json()["order"]
    reason = "Fixture <script>alert('never')</script>"
    actual = dict(REQUIREMENTS) if matches else {**REQUIREMENTS, "bolt": 0}
    result = review(client, order, actual_counts=actual, reason=reason)
    assert result.status_code == 200
    response = client.get(f"/api/orders/{order['id']}/evidence.zip")
    assert response.status_code == 200
    with ZipFile(BytesIO(response.content)) as archive:
        viewer = archive.read("OPEN_ME.html").decode()
        data = json.loads(archive.read("evidence.json"))
    assert "人工实物复核记录" in viewer and "不计为 AI 核验成功" in viewer
    assert ("수량 일치 / 数量相符" if matches else "미해결 / 未解决") in viewer
    assert "&lt;script&gt;" in viewer and "<script>" not in viewer
    assert data["order"]["checks"] == [] and data["order"]["completions"] == []
    assert data["order"]["manual_reviews"][0]["actual_counts"] == actual


@pytest.mark.parametrize("matches", [True, False])
def test_manual_record_derives_outcome_without_an_ai_check(client, order, upload, matches, analyzer):
    order = upload(order).json()["order"]
    counts = dict(REQUIREMENTS) if matches else {**REQUIREMENTS, "washer": 0}
    response = review(client, order, actual_counts=counts)
    assert response.status_code == 200, response.text
    saved, receipt = response.json()["order"], response.json()["manual_review"]
    assert saved["status"] == "manual_reviewed"
    assert saved["requirements"] == REQUIREMENTS
    assert saved["checks"] == saved["completions"] == []
    assert saved["latest_check"] is None and analyzer.calls == []
    assert receipt["matches_requirements"] is matches
    assert receipt["outcome"] == ("matched" if matches else "unresolved")
    assert receipt["actual_counts"] == counts and receipt["requirements_snapshot"] == REQUIREMENTS
    assert receipt["photo_id"] == order["photos"][-1]["id"]
    assert receipt["photo_sha256"] == order["photos"][-1]["sha256"]
    assert receipt["evidence_epoch"] == order["evidence_epoch"] and receipt["revision"] == 1
    assert receipt["check_id"] is None and not receipt["ai_completion"] and not receipt["industrial_release"]
    assert receipt["source_kind"] == "operator_declared_physical"
    assert len(saved["manual_reviews"]) == 1 and receipt["replayed"] is False
    assert saved["events"][-1]["kind"] == "manual_review_recorded"


@pytest.mark.parametrize("decision,action", [("manual", "manual"), ("recapture", "recapture"), ("correct", "none")])
def test_manual_preserves_nonready_ai_check(client, order, upload, analyzer, decision, action):
    order = upload(order).json()["order"]
    # Simulate persisted production metadata, without loading or running any model.
    counts = {**REQUIREMENTS, "bolt": 1}
    analyzer.result = analyzer.observation(counts, action=action, issues=["Synthetic fixture"] if action != "none" else [])
    analyzer.result["backend"] = "mlx"
    response = client.post(f"/api/orders/{order['id']}/inspect", json={
        "expected_revision": 1, "photo_id": order["photos"][-1]["id"],
    })
    assert response.status_code == 200, response.text
    order = response.json()["order"]
    before = deepcopy(order["latest_check"])
    assert before["decision"] == decision
    result = review(client, order)
    assert result.status_code == 200, result.text
    assert result.json()["order"]["latest_check"] == before
    receipt = result.json()["manual_review"]
    assert receipt["check_id"] == before["id"] and receipt["check_decision"] == decision
    assert result.json()["order"]["completions"] == []


@pytest.mark.parametrize("change", [
    {"confirmed_physical": 1}, {"confirmed_current_bom": "true"}, {"confirmed_physical": False},
    {"reason": "   "}, {"operator_code": ""}, {"expected_revision": True},
    {"expected_evidence_epoch": "1"}, {"actual_counts": {**REQUIREMENTS, "bolt": True}},
    {"actual_counts": {**REQUIREMENTS, "bolt": 1.0}},
    {"actual_counts": {**REQUIREMENTS, "bolt": -1}},
    {"actual_counts": {**REQUIREMENTS, "bolt": 101}},
    {"actual_counts": {"bolt": 2, "nut": 2, "washer": 2}}, {"unknown": "field"},
])
def test_manual_requires_explicit_complete_strict_input(client, order, upload, change):
    order = upload(order).json()["order"]
    result = review(client, order, **change)
    assert result.status_code == 422, result.text
    assert current(client, order) == order


@pytest.mark.parametrize("change", [
    {"expected_revision": 2}, {"expected_evidence_epoch": 0},
    {"photo_id": "old-photo"}, {"check_id": "old-check"},
])
def test_stale_manual_binding_is_rejected(client, order, upload, change):
    order = upload(order).json()["order"]
    result = review(client, order, **change)
    assert result.status_code == 409, result.text
    assert current(client, order) == order


@pytest.mark.parametrize("kind", ["photo", "reference", "revision"])
def test_evidence_mutation_rejects_previous_manual_confirmation(client, order, upload, image_bytes, kind):
    order = upload(order).json()["order"]
    request = body(order)
    if kind == "photo":
        changed = upload(order, seed=2)
    elif kind == "reference":
        changed = client.post(f"/api/orders/{order['id']}/references/bolt", files={
            "photo": ("reference.png", image_bytes(3), "image/png")}, data={"expected_revision": 1})
    else:
        changed = client.post(f"/api/orders/{order['id']}/revise", json={
            "expected_revision": 1, "requirements": {**REQUIREMENTS, "bolt": 1}, "instruction": "fixture"})
    assert changed.status_code in {200, 201}, changed.text
    assert review(client, order, request).status_code == 409
    assert current(client, order) == changed.json()["order"]


@pytest.mark.parametrize("target", ["photo", "reference"])
def test_changed_evidence_bytes_cannot_be_manually_finalized(client, order, upload, image_bytes, target):
    order = upload(order).json()["order"]
    if target == "reference":
        result = client.post(f"/api/orders/{order['id']}/references/bolt", files={
            "photo": ("reference.png", image_bytes(9), "image/png")}, data={"expected_revision": 1})
        order = result.json()["order"]
        photo = order["references"]["bolt"]
    else:
        photo = order["photos"][-1]
    client.app.state.store.photo_path(photo["id"]).write_bytes(b"Tampered fixture")
    assert review(client, order).status_code == 409
    assert current(client, order) == order


def test_manual_binds_all_current_reference_hashes(client, order, upload, image_bytes):
    order = upload(order).json()["order"]
    result = client.post(f"/api/orders/{order['id']}/references/bolt", files={
        "photo": ("reference.png", image_bytes(9), "image/png")}, data={"expected_revision": 1})
    order = result.json()["order"]
    receipt = review(client, order).json()["manual_review"]
    assert receipt["reference_ids"] == {"bolt": order["references"]["bolt"]["id"]}
    assert receipt["reference_sha256"] == {"bolt": order["references"]["bolt"]["sha256"]}


@pytest.mark.parametrize("source", ["public", "test", "copied_test", "known_public"])
def test_known_public_and_test_evidence_cannot_become_physical_terminal(client, order, upload, inspected, source, monkeypatch):
    # inspected is an unrelated order except in the direct test case; its bytes
    # remain a known test-observation family even after exact re-upload.
    if source == "test":
        order = inspected["order"]
    else:
        order = client.post("/api/orders", json={"title": "Provenance fixture", "requirements": REQUIREMENTS}).json()["order"]
        order = upload(order, seed=0 if source == "copied_test" else 3).json()["order"]
        if source == "public":
            with client.app.state.store.transaction(order["id"]) as (_, saved):
                saved["demo_source"] = {"kind": "public_photo_demo"}
            order = current(client, order)
        elif source == "known_public":
            import kitguard.public_demo_catalog as catalog
            monkeypatch.setattr(catalog, "CATALOG", [{"source_sha256": order["photos"][-1]["source_sha256"]}])
    result = review(client, order)
    assert result.status_code == 409, result.text
    assert current(client, order) == order


@pytest.mark.parametrize("terminal", ["completed", "manual_reviewed"])
def test_terminal_record_protects_all_evidence_until_explicit_transition(client, order, upload, image_bytes, terminal):
    order = upload(order).json()["order"]
    if terminal == "completed":
        check = client.post(f"/api/orders/{order['id']}/inspect", json={
            "photo_id": order["photos"][-1]["id"], "expected_revision": 1}).json()["check"]
        result = client.post(f"/api/orders/{order['id']}/complete", json={
            "check_id": check["id"], "expected_revision": 1, "confirmed": True,
            "idempotency_key": "fixture-completion"})
    else:
        result = review(client, order)
    assert result.status_code == 200, result.text
    order = result.json()["order"]
    before_body = stored_body(client, order)
    before_files = set(client.app.state.store.photos_dir.iterdir())
    assert upload(order, seed=5).status_code == 409
    assert client.post(f"/api/orders/{order['id']}/references/bolt", files={
        "photo": ("reference.png", image_bytes(6), "image/png")}, data={"expected_revision": 1}).status_code == 409
    assert client.post(f"/api/orders/{order['id']}/inspect", json={
        "photo_id": order["photos"][-1]["id"], "expected_revision": 1}).status_code == 409
    assert client.post(f"/api/orders/{order['id']}/inspection-region", json={
        "expected_photo_id": order["photos"][-1]["id"], "root_photo_id": order["photos"][-1]["id"],
        "expected_revision": 1, "expected_evidence_epoch": order["evidence_epoch"],
        "mode": "region", "region_xyxy": [0, 0, 320, 240], "confirmed_all_items_inside": True}).status_code == 409
    assert current(client, order) == order
    assert stored_body(client, order) == before_body
    assert set(client.app.state.store.photos_dir.iterdir()) == before_files
    changed = reopen(client, order)
    assert changed.status_code == 200, changed.text
    fresh = changed.json()["order"]
    assert fresh["status"] == "pending" and fresh["revision"] == 2
    assert fresh["requirements"] == order["requirements"]
    assert fresh["photos"] == order["photos"]
    assert fresh["completions"] == order["completions"] and fresh["manual_reviews"] == order["manual_reviews"]
    assert fresh["evidence_epoch"] == order["evidence_epoch"] + 1
    assert client.post(f"/api/orders/{order['id']}/inspect", json={
        "photo_id": order["photos"][-1]["id"], "expected_revision": 2}).status_code == 409
    assert review(client, fresh, idempotency_key="fresh-review-key").status_code == 409
    assert upload(fresh, seed=7).status_code == 201


def test_bom_revision_from_manual_terminal_preserves_prior_receipt(client, order, upload):
    order = upload(order).json()["order"]
    reviewed = review(client, order).json()["order"]
    result = client.post(f"/api/orders/{order['id']}/revise", json={"expected_revision": 1,
        "requirements": {**REQUIREMENTS, "bolt": 1}, "instruction": "New fixture BOM"})
    assert result.status_code == 200, result.text
    assert result.json()["order"]["manual_reviews"] == reviewed["manual_reviews"]
    assert result.json()["order"]["revision"] == 2 and result.json()["order"]["status"] == "pending"


def test_review_and_reopen_replays_are_idempotent_and_cannot_restore_old_state(client, order, upload):
    order = upload(order).json()["order"]
    request = body(order)
    first = review(client, order, request).json()
    reopened = reopen(client, first["order"]).json()
    replay = review(client, order, request)
    assert replay.status_code == 200, replay.text
    assert replay.json()["manual_review"]["id"] == first["manual_review"]["id"]
    assert replay.json()["manual_review"]["replayed"] is True
    assert replay.json()["order"] == reopened["order"]
    reopened_again = reopen(client, first["order"])
    assert reopened_again.status_code == 200, reopened_again.text
    assert reopened_again.json()["reopening"]["id"] == reopened["reopening"]["id"]
    assert reopened_again.json()["reopening"]["replayed"] is True
    assert reopened_again.json()["order"] == reopened["order"]
    assert review(client, order, {**request, "reason": "changed"}).status_code == 409
    assert reopen(client, first["order"], idempotency_key=request["idempotency_key"]).status_code == 409


@pytest.mark.parametrize("operation", ["manual_review", "reopen"])
def test_concurrent_duplicate_requests_commit_once(client, order, upload, operation):
    order = upload(order).json()["order"]
    if operation == "reopen":
        order = review(client, order).json()["order"]
        send = reopen
    else:
        send = review
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: send(client, order), range(2)))
    assert [r.status_code for r in results] == [200, 200]
    key = "manual_review" if operation == "manual_review" else "reopening"
    receipts = [r.json()[key] for r in results]
    assert receipts[0]["id"] == receipts[1]["id"]
    assert sorted(r["replayed"] for r in receipts) == [False, True]
    saved = current(client, order)
    assert len(saved["manual_reviews" if operation == "manual_review" else "reopenings"]) == 1


def test_manual_and_upload_race_cannot_bind_stale_evidence(client, order, upload):
    order = upload(order).json()["order"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        # A concurrent successful upload may change the DB while review rejects;
        # the winner/loser invariants below, rather than byte immutability, apply.
        a = pool.submit(review, client, order, concurrent=True)
        b = pool.submit(upload, order, 11)
        reviewed, uploaded = a.result(), b.result()
    assert sorted([reviewed.status_code, uploaded.status_code]) in ([200, 409], [201, 409])
    saved = current(client, order)
    if reviewed.status_code == 200:
        assert saved["status"] == "manual_reviewed"
        assert saved["photos"][-1]["id"] == saved["manual_reviews"][0]["photo_id"]
    else:
        assert saved["status"] == "pending" and saved["manual_reviews"] == []


def test_active_inspection_blocks_manual_then_failure_allows_current_photo(client, order, upload):
    order = upload(order).json()["order"]
    store = client.app.state.store
    token, _ = store.begin_inspection(order["id"], order["photos"][-1]["id"], 1)
    assert review(client, order).status_code == 409
    store.fail_inspection(order["id"], token, "Synthetic execution failure before any observation")
    failed = current(client, order)
    assert failed["status"] == "needs_action"
    assert review(client, failed).status_code == 200


def test_unclosed_field_study_keeps_registered_order_untouched(client, order, upload):
    from test_field_study_flow import prepared

    study, _ = prepared(client, order, upload)
    order = current(client, order)
    assert review(client, order).status_code == 409
    assert current(client, order) == order
    assert client.post(f"/api/studies/{study['id']}/close", json={"confirmed": True}).status_code == 200
    assert review(client, order).status_code == 200


@pytest.mark.parametrize("changes,code", [
    ({"expected_revision": 2}, 409), ({"confirmed": 1}, 422), ({"confirmed": False}, 422),
    ({"reason": " "}, 422), ({"unknown": True}, 422),
])
def test_reopen_requires_current_revision_and_explicit_reason(client, order, upload, changes, code):
    order = upload(order).json()["order"]
    order = review(client, order).json()["order"]
    assert reopen(client, order, **changes).status_code == code
    assert current(client, order) == order


def test_pending_order_cannot_be_reopened(client, order):
    assert reopen(client, order).status_code == 409
    assert current(client, order) == order


def test_legacy_order_and_database_are_migrated_without_history_loss(client, order, upload):
    order = upload(order).json()["order"]
    original = client.app.state.store
    with original.transaction(order["id"]) as (_, saved):
        del saved["manual_reviews"]
        del saved["reopenings"]
    with original.connect() as db:
        db.execute("DROP TABLE human_operations")
    store = Store(original.directory)
    reviewed = store.manual_review(order["id"], body(order))
    reopened = store.reopen(order["id"], reopen_body(reviewed["order"]))
    assert len(reopened["order"]["manual_reviews"]) == len(reopened["order"]["reopenings"]) == 1
    assert reopened["order"]["events"][:len(order["events"])] == order["events"]


def test_injected_evidence_verifier_failure_rolls_back_receipt(client, order, upload):
    order = upload(order).json()["order"]
    before_body = stored_body(client, order)
    def reject(snapshot):
        assert snapshot["id"] == order["id"]
        raise StateError("Synthetic verification failure")
    with pytest.raises(StateError):
        client.app.state.store.manual_review(order["id"], body(order), reject)
    assert stored_body(client, order) == before_body
    assert current(client, order) == order
    assert review(client, order).status_code == 200
