"""Synthetic state/permission contracts only; no model accuracy or real review evidence."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from io import BytesIO
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from kitguard.app import create_app
from kitguard.public_review import PublicReviews, create_public_review_router
from kitguard.store import StateError


@pytest.fixture
def public(tmp_path, monkeypatch, analyzer, image_bytes):
    import kitguard.app as app_module
    import kitguard.public_demo_catalog as catalog_module
    import kitguard.public_review as review_module

    dataset = tmp_path / "fixture-dataset"
    dataset.mkdir()
    raw = image_bytes(17)
    (dataset / "synthetic.png").write_bytes(raw)
    spec = {"sample_id": "synthetic", "title": "SYNTHETIC API FIXTURE ONLY",
            "requirements": {"bolt": 1, "nut": 1, "washer": 0, "bracket": 0}, "image": "synthetic.png",
            "source_case_id": "synthetic-only", "source_sha256": hashlib.sha256(raw).hexdigest(),
            "source_url": "https://example.invalid/synthetic", "license": "SYNTHETIC TEST ONLY",
            "source_note": "Contract fixture, not public evaluation evidence", "derived_view": False}
    monkeypatch.setattr(app_module, "PUBLIC_DEMOS", [spec])
    monkeypatch.setattr(catalog_module, "CATALOG", [spec])
    monkeypatch.setattr(review_module, "CATALOG", [spec])
    identity = {"label": "SYNTHETIC MODEL IDENTITY FIXTURE", "repo_id": "synthetic/test-only",
                "revision": "synthetic-revision", "observer_protocol_sha256": "b" * 64,
                "observation_mode": "single", "image_max_side": 512}
    monkeypatch.setattr(analyzer, "status", lambda: {"available": True, "loaded": True, **identity})
    app = create_app(tmp_path / "data", analyzer=analyzer, demo_dataset_root=dataset)
    if not any(getattr(route, "path", None) == "/api/orders/{order_id}/public-review" for route in app.routes):
        app.include_router(create_public_review_router(app.state.store, analyzer.status))
    with TestClient(app) as client:
        order = client.post("/api/public-demos/synthetic/orders").json()["order"]
        yield client, order, analyzer, identity


def read(client, order):
    return client.get(f"/api/orders/{order['id']}").json()["order"]


def summary(client, order):
    response = client.get(f"/api/orders/{order['id']}/public-review-summary")
    assert response.status_code == 200, response.text
    return response.json()


def inspect(public, *, decision="ready", backend="mlx"):
    client, old, analyzer, _ = public
    order = read(client, old)
    counts = dict(order["requirements"])
    if decision == "correct":
        counts["bolt"] = 0
    analyzer.result = analyzer.observation(counts, action=decision if decision in {"manual", "recapture"} else "none",
                                          issues=["Synthetic uncertainty"] if decision in {"manual", "recapture"} else [])
    # Persisted-production-metadata fixture; no MLX model is loaded or invoked.
    analyzer.result["backend"] = backend
    response = client.post(f"/api/orders/{order['id']}/inspect", json={
        "expected_revision": order["revision"], "photo_id": order["photos"][-1]["id"]})
    assert response.status_code == 200, response.text
    return response.json()["order"]


def request(client, order, **changes):
    return {**summary(client, order)["review_request"], "operator_code": "synthetic-reviewer",
            "conclusion": "acknowledged", "note": "Synthetic API contract; no actual user feedback.",
            "confirmed_digital_only": True, "idempotency_key": "synthetic-review-key", **changes}


def review(client, order, body):
    return client.post(f"/api/orders/{order['id']}/public-review", json=body)


def revise(client, order):
    counts = dict(order["requirements"])
    counts["bolt"] = 2 if counts["bolt"] != 2 else 3
    response = client.post(f"/api/orders/{order['id']}/revise", json={
        "expected_revision": order["revision"], "requirements": counts, "instruction": "SYNTHETIC revision"})
    assert response.status_code == 200, response.text
    return response.json()["order"]


def replay_request(client, order, **changes):
    return {**summary(client, order)["replay_request"], "confirmed_no_physical_capture": True,
            "idempotency_key": "synthetic-replay-key", **changes}


def replay(client, order, body=None):
    return client.post(f"/api/orders/{order['id']}/public-replay", json=body or replay_request(client, order))


@pytest.mark.parametrize("decision", ["ready", "correct", "recapture", "manual"])
@pytest.mark.parametrize("conclusion", ["acknowledged", "needs_more_evidence", "disputed", "inconclusive"])
def test_review_records_any_human_opinion_without_overwriting_ai_or_physical_state(public, decision, conclusion):
    client, _, analyzer, _ = public
    order = inspect(public, decision=decision)
    before = deepcopy(order)
    calls = len(analyzer.calls)
    result = review(client, order, request(client, order, conclusion=conclusion))
    assert result.status_code == 200, result.text
    result = result.json()
    saved, receipt = result["order"], result["review"]
    assert saved["status"] == before["status"]
    assert saved["checks"] == before["checks"] and saved["latest_check"] == before["latest_check"]
    assert saved["completions"] == saved["manual_reviews"] == []
    assert receipt["ai_decision"] == decision and receipt["conclusion"] == conclusion
    assert not receipt["physical_completion"] and not receipt["user_validation"]
    assert receipt["check_snapshot"] == order["latest_check"]
    assert receipt["source"] == order["demo_source"]
    assert result["summary"]["current_review"]["id"] == receipt["id"]
    assert len(analyzer.calls) == calls


def test_missing_or_test_model_check_cannot_become_digital_review_evidence(public):
    client, order, _, _ = public
    assert not summary(client, order)["can_review"]
    order = inspect(public, backend="test")
    assert not summary(client, order)["can_review"]
    check = order["latest_check"]
    payload = {"expected_revision": 1, "expected_evidence_epoch": order["evidence_epoch"],
               "photo_id": check["photo_id"], "check_id": check["id"], "check_sha256": "a" * 64,
               "runtime_identity_sha256": "a" * 64, "operator_code": "fixture", "conclusion": "acknowledged",
               "note": "Synthetic rejection", "confirmed_digital_only": True, "idempotency_key": "fake-check-key"}
    assert review(client, order, payload).status_code == 409
    assert read(client, order).get("public_reviews", []) == []


@pytest.mark.parametrize("field,value", [
    ("expected_revision", 2), ("expected_evidence_epoch", 999), ("photo_id", "other_photo"),
    ("check_id", "other_check"), ("check_sha256", "a" * 64), ("runtime_identity_sha256", "a" * 64)])
def test_stale_review_bindings_are_rejected(public, field, value):
    client, _, _, _ = public
    order = inspect(public)
    response = review(client, order, request(client, order, **{field: value}))
    assert response.status_code == 409, response.text
    assert read(client, order).get("public_reviews", []) == []


@pytest.mark.parametrize("field,value", [
    ("confirmed_digital_only", False), ("confirmed_digital_only", 1), ("confirmed_digital_only", "true"),
    ("expected_revision", True), ("expected_evidence_epoch", "1"), ("operator_code", "  "),
    ("note", "  "), ("conclusion", "completed"), ("extra_success", True)])
def test_review_requires_explicit_strict_inputs(public, field, value):
    client, _, _, _ = public
    order = inspect(public)
    assert review(client, order, request(client, order, **{field: value})).status_code == 422


def test_review_idempotency_survives_revision_without_making_history_current(public):
    client, _, _, _ = public
    order = inspect(public)
    body = request(client, order)
    first = review(client, order, body).json()["review"]
    assert review(client, order, body).json()["review"]["replayed"]
    assert review(client, order, {**body, "note": "different"}).status_code == 409
    changed = revise(client, order)
    result = review(client, changed, body)
    assert result.status_code == 200, result.text
    result = result.json()
    assert result["review"]["id"] == first["id"] and result["review"]["replayed"]
    assert result["order"]["revision"] == 2 and len(result["order"]["public_reviews"]) == 1
    assert result["summary"]["current_review"] is None
    assert not result["summary"]["reviews"][0]["current"]


@pytest.mark.parametrize("changed", ["runtime", "new_inspection", "reference", "check_content", "active"])
def test_changed_evidence_or_model_invalidates_review_currentness(public, image_bytes, changed):
    client, _, _, identity = public
    order = inspect(public)
    body = request(client, order)
    assert review(client, order, body).status_code == 200
    if changed == "runtime":
        identity["observer_protocol_sha256"] = "c" * 64
    elif changed == "new_inspection":
        inspect(public)
    elif changed == "reference":
        assert client.post(f"/api/orders/{order['id']}/references/bolt", data={"expected_revision": 1},
                           files={"photo": ("fixture.png", image_bytes(8), "image/png")}).status_code == 201
    else:
        with client.app.state.store.transaction(order["id"]) as (_, saved):
            if changed == "active":
                saved["active_inspection"] = "synthetic-active"
            else:
                saved["latest_check"]["action"]["message"] = "synthetic changed check"
    assert summary(client, order)["current_review"] is None
    assert review(client, order, {**body, "idempotency_key": "changed-review-key"}).status_code == 409


@pytest.mark.parametrize("scope", ["whole_image", "region"])
def test_replay_preserves_source_scope_and_pixels_requires_fresh_inference(public, scope):
    client, order, analyzer, _ = public
    if scope == "region":
        root = order["photos"][-1]
        response = client.post(f"/api/orders/{order['id']}/inspection-region", json={
            "expected_revision": 1, "expected_photo_id": root["id"],
            "expected_evidence_epoch": order["evidence_epoch"], "root_photo_id": root["id"],
            "mode": "region", "region_xyxy": [20, 20, 400, 300], "confirmed_all_items_inside": True})
        assert response.status_code == 200, response.text
    order = inspect(public)
    old_photo = order["photos"][-1]
    old_scope = summary(client, order)["inspection_scope"]
    changed = revise(client, order)
    payload = replay_request(client, changed)
    calls = len(analyzer.calls)
    result = replay(client, changed, payload)
    assert result.status_code == 200, result.text
    result = result.json()
    saved, photo, receipt = result["order"], result["photo"], result["replay"]
    assert len(analyzer.calls) == calls
    assert saved["status"] == "pending" and not saved["latest_check"]["valid"]
    assert saved["evidence_epoch"] == changed["evidence_epoch"] + 1
    assert photo["sha256"] == old_photo["sha256"] and photo["revision"] == 2
    assert photo["replay_of_photo_id"] == old_photo["id"] and not photo["physical_capture"]
    assert client.get(photo["url"]).content == client.get(old_photo["url"]).content
    new_scope = receipt["inspection_scope"]
    for key in ["mode", "view_sha256", "root_photo_sha256", "source_family_sha256", "region_xyxy", "root_source_sha256"]:
        assert new_scope[key] == old_scope[key]
    assert receipt["requires_new_inference"] and not receipt["physical_capture"]
    assert not summary(client, saved)["can_review"]
    assert replay(client, changed, payload).json()["replay"]["replayed"]
    assert len(read(client, order)["photos"]) == len(saved["photos"])
    refreshed = inspect(public)
    assert refreshed["latest_check"]["photo_id"] == photo["id"]
    assert len(analyzer.calls) == calls + 1
    assert summary(client, refreshed)["can_review"]


def test_same_revision_replay_is_rejected_without_duplicate_photos(public):
    client, order, analyzer, _ = public
    assert replay(client, order).status_code == 409
    assert len(read(client, order)["photos"]) == 1 and analyzer.calls == []


@pytest.mark.parametrize("field,value,status", [
    ("expected_revision", 9, 409), ("expected_photo_id", "old_photo", 409),
    ("expected_evidence_epoch", 999, 409), ("confirmed_no_physical_capture", 1, 422),
    ("confirmed_no_physical_capture", False, 422), ("physical_capture", True, 422)])
def test_replay_stale_or_nonexplicit_inputs_do_not_mutate(public, field, value, status):
    client, order, _, _ = public
    changed = revise(client, order)
    with client.app.state.store.connect() as db:
        before_body = db.execute("SELECT body FROM orders WHERE id=?", (order["id"],)).fetchone()["body"]
    result = replay(client, changed, replay_request(client, changed, **{field: value}))
    assert result.status_code == status
    fetched = read(client, order)
    assert fetched.pop("digital_review_feedback")["status"] == "not_applicable"
    assert fetched == changed
    with client.app.state.store.connect() as db:
        after_body = db.execute("SELECT body FROM orders WHERE id=?", (order["id"],)).fetchone()["body"]
    assert after_body == before_body  # includes raw check and receipt content


@pytest.mark.parametrize("change", ["nonpublic", "catalog_hash", "url", "source_pixels", "file"])
def test_nonpublic_or_tampered_source_is_rejected(public, image_bytes, change):
    client, _, _, _ = public
    order = inspect(public)
    body = request(client, order)
    store = client.app.state.store
    if change == "source_pixels":
        # Normal uploads now reject before mutation. Exercise corrupted persisted lineage directly.
        with store.transaction(order["id"]) as (_, saved):
            saved["photos"][-1]["source_sha256"] = hashlib.sha256(image_bytes(9)).hexdigest()
    elif change == "file":
        store.photo_path(order["photos"][-1]["id"]).write_bytes(b"synthetic corruption")
    else:
        with store.transaction(order["id"]) as (_, saved):
            if change == "nonpublic":
                saved.pop("demo_source")
            elif change == "url":
                saved["demo_source"]["source_url"] = "https://example.invalid/forged"
            else:
                saved["demo_source"]["source_sha256"] = "e" * 64
    assert review(client, order, body).status_code == 409
    changed = revise(client, read(client, order))
    replay_body = {"expected_revision": changed["revision"], "expected_photo_id": changed["photos"][-1]["id"],
                   "expected_evidence_epoch": changed["evidence_epoch"], "confirmed_no_physical_capture": True,
                   "idempotency_key": "reject-source-replay"}
    assert replay(client, changed, replay_body).status_code == 409


def photo_storage_snapshot(store):
    with store.connect() as db:
        rows = [tuple(row) for row in db.execute("SELECT id, path FROM photos ORDER BY id")]
    files = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in store.photos_dir.iterdir()}
    return rows, files


@pytest.mark.parametrize("payload", ["same_source", "other_source", "invalid"])
def test_public_normal_photo_upload_rejected_without_changing_any_evidence(public, image_bytes, payload):
    client, _, _, _ = public
    order = inspect(public)
    result = review(client, order, request(client, order, conclusion="needs_more_evidence"))
    assert result.status_code == 200
    before = read(client, order)
    store = client.app.state.store
    storage = photo_storage_snapshot(store)
    raw = b"not an image" if payload == "invalid" else image_bytes(17 if payload == "same_source" else 9)
    response = client.post(f"/api/orders/{order['id']}/photos",
                           data={"expected_revision": 1, "catalog_initial": "true"},
                           files={"photo": ("new.png", raw, "image/png")})
    assert response.status_code == 409, response.text
    assert "공개 예시" in response.json()["detail"]
    assert read(client, order) == before  # Includes revision, photos, checks, reviews, epoch, events, status.
    assert photo_storage_snapshot(store) == storage
    assert summary(client, order)["can_review"] is True


def test_public_store_guard_cleans_api_file_when_precheck_is_bypassed(public, image_bytes, monkeypatch):
    import kitguard.app as app_module

    client, _, _, _ = public
    order = inspect(public)
    store = client.app.state.store
    before, storage = read(client, order), photo_storage_snapshot(store)
    monkeypatch.setattr(app_module, "require_photo_upload", lambda *args, **kwargs: None)
    response = client.post(f"/api/orders/{order['id']}/photos", data={"expected_revision": 1},
                           files={"photo": ("other.png", image_bytes(9), "image/png")})
    assert response.status_code == 409
    assert read(client, order) == before
    assert photo_storage_snapshot(store) == storage


def test_public_store_initial_registration_cannot_replace_existing_root(public):
    client, order, _, _ = public
    store = client.app.state.store
    before, storage = read(client, order), photo_storage_snapshot(store)
    with pytest.raises(StateError):
        store.add_photo(order["id"], {**order["photos"][0], "id": "forbidden"},
                        store.photos_dir / "forbidden.jpg", expected=1, catalog_initial=True)
    assert read(client, order) == before
    assert photo_storage_snapshot(store) == storage


def test_public_reference_upload_remains_supported_and_requires_recheck(public, image_bytes):
    client, _, _, _ = public
    order = inspect(public)
    response = client.post(f"/api/orders/{order['id']}/references/bolt", data={"expected_revision": 1},
                           files={"photo": ("reference.png", image_bytes(9), "image/png")})
    assert response.status_code == 201, response.text
    updated = response.json()["order"]
    assert updated["photos"] == order["photos"]
    assert updated["references"]["bolt"]["id"] == response.json()["photo"]["id"]
    assert not updated["latest_check"]["valid"]
    assert summary(client, updated)["can_review"] is False


def test_cross_origin_and_nonpublic_orders_cannot_use_public_endpoints(public):
    client, order, _, _ = public
    response = client.post(f"/api/orders/{order['id']}/public-replay", json=replay_request(client, order),
                           headers={"Origin": "https://example.invalid"})
    assert response.status_code == 403
    other = client.post("/api/orders", json={"title": "ordinary fixture", "requirements": order["requirements"]}).json()["order"]
    assert client.get(f"/api/orders/{other['id']}/public-review-summary").status_code == 409


def test_concurrent_retries_commit_one_review_and_cannot_reuse_key_for_replay(public):
    client, _, _, _ = public
    order = inspect(public)
    body = request(client, order)
    service = PublicReviews(client.app.state.store, client.app.state.analyzer.status)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: service.review(order["id"], body), range(4)))
    assert len({result["review"]["id"] for result in results}) == 1
    assert len(read(client, order)["public_reviews"]) == 1
    changed = revise(client, order)
    assert replay(client, changed, replay_request(client, changed,
                                                idempotency_key=body["idempotency_key"])).status_code == 409


def test_public_review_is_exported_but_cannot_enable_physical_completion(public):
    client, _, _, _ = public
    order = inspect(public)
    receipt = review(client, order, request(client, order)).json()["review"]
    exported = client.get(f"/api/orders/{order['id']}/export").json()["order"]
    assert exported["public_reviews"][0]["id"] == receipt["id"]
    response = client.get(f"/api/orders/{order['id']}/evidence.zip")
    assert response.status_code == 200
    with ZipFile(BytesIO(response.content)) as archive:
        evidence = json.loads(archive.read("evidence.json"))
        assert evidence["order"]["public_reviews"][0]["id"] == receipt["id"]
    assert client.post(f"/api/orders/{order['id']}/complete", json={
        "expected_revision": 1, "check_id": order["latest_check"]["id"], "confirmed": True,
        "idempotency_key": "public-cannot-complete"}).status_code == 409
    assert read(client, order)["completions"] == []


def test_registered_active_study_blocks_writes_and_summary_affordances(public):
    client, _, _, _ = public
    order = inspect(public)
    body = request(client, order)
    with client.app.state.store.connect() as db:
        db.execute("INSERT INTO field_studies VALUES (?,?)", ("synthetic-study", json.dumps({
            "status": "frozen", "cases": [{"order_id": order["id"]}]})))
    state = summary(client, order)
    assert not state["can_review"] and state["review_request"] is None
    assert review(client, order, body).status_code == 409
    order = revise(client, order)
    assert not summary(client, order)["can_replay"]
    assert replay(client, order).status_code == 409
    assert read(client, order).get("public_reviews", []) == []


@pytest.mark.parametrize("kind", ["active", "terminal", "limit"])
def test_replay_rejects_busy_terminal_and_full_orders(public, kind):
    client, order, _, _ = public
    order = revise(client, order)
    body = replay_request(client, order)
    store = client.app.state.store
    with store.transaction(order["id"]) as (_, saved):
        if kind == "active":
            saved["active_inspection"] = "synthetic-inflight"
        elif kind == "terminal":
            saved["status"] = "manual_reviewed"
        else:
            saved["reference_history"] = [{"synthetic": True}] * 299
    before = store.get(order["id"])
    assert replay(client, order, body).status_code == 409
    assert store.get(order["id"]) == before


def test_interrupted_replay_file_write_rolls_back_files_and_database(public, monkeypatch):
    from pathlib import Path

    client, order, _, _ = public
    order = revise(client, order)
    body = replay_request(client, order)
    store = client.app.state.store
    files_before = set(store.photos_dir.iterdir())
    original_put = store._put

    def failing_put(db, saved):
        if saved.get("public_replays"):
            raise RuntimeError("Synthetic database write failure after copied file")
        return original_put(db, saved)

    monkeypatch.setattr(store, "_put", failing_put)
    with pytest.raises(RuntimeError, match="Synthetic database"):
        PublicReviews(store, client.app.state.analyzer.status).replay(order["id"], body)
    assert store.get(order["id"]) == order
    assert set(Path(store.photos_dir).iterdir()) == files_before


def test_replay_idempotency_is_atomic_for_simultaneous_requests(public):
    client, order, _, _ = public
    order = revise(client, order)
    body = replay_request(client, order)
    service = PublicReviews(client.app.state.store, client.app.state.analyzer.status)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: service.replay(order["id"], body), range(4)))
    assert len({result["replay"]["id"] for result in results}) == 1
    saved = read(client, order)
    assert len(saved["photos"]) == 2 and len(saved["public_replays"]) == 1


def test_offline_viewer_displays_replay_even_without_any_human_review(public):
    client, order, _, _ = public
    order = revise(client, order)
    assert replay(client, order).status_code == 200
    response = client.get(f"/api/orders/{order['id']}/evidence.zip")
    assert response.status_code == 200
    with ZipFile(BytesIO(response.content)) as archive:
        viewer = archive.read("OPEN_ME.html").decode()
        assert "同一公开照片回放" in viewer
        assert "不代表重新拍摄或实物发生变化" in viewer
        evidence = json.loads(archive.read("evidence.json"))
        assert len(evidence["order"]["public_replays"]) == 1
        assert not evidence["order"].get("public_reviews")


def test_offline_review_escapes_opinions_and_exposes_currentness(public):
    client, _, _, _ = public
    order = inspect(public)
    assert review(client, order, request(client, order, note="<script>not an actual review</script>")).status_code == 200
    response = client.get(f"/api/orders/{order['id']}/evidence.zip")
    with ZipFile(BytesIO(response.content)) as archive:
        viewer = archive.read("OPEN_ME.html").decode()
        assert "对应导出时当前核验" in viewer
        assert "&lt;script&gt;not an actual review&lt;/script&gt;" in viewer
        assert "<script>not an actual review</script>" not in viewer
        assert "不计为 AI 准确率、实物完工、出库或用户试验成绩" in viewer
    revise(client, order)
    response = client.get(f"/api/orders/{order['id']}/evidence.zip")
    with ZipFile(BytesIO(response.content)) as archive:
        viewer = archive.read("OPEN_ME.html").decode()
        assert "历史记录 · 不适用于当前核验" in viewer
        assert "对应导出时当前核验" not in viewer


@pytest.mark.parametrize("source", ["raw", "raw_without_demo_order", "normalized_copy", "region_copy", "region_in_order"])
def test_regular_order_cannot_complete_registered_public_source_families(public, source):
    client, demo_order, analyzer, _ = public
    store = client.app.state.store
    if source in {"region_copy", "region_in_order"}:
        root = demo_order["photos"][-1]
        result = client.post(f"/api/orders/{demo_order['id']}/inspection-region", json={
            "expected_revision": 1, "expected_photo_id": root["id"],
            "expected_evidence_epoch": demo_order["evidence_epoch"], "root_photo_id": root["id"],
            "mode": "region", "region_xyxy": [20, 20, 400, 300], "confirmed_all_items_inside": True})
        assert result.status_code == 200
        demo_order = result.json()["order"]
    if source in {"raw", "raw_without_demo_order", "region_in_order"}:
        content = client.get("/api/public-demos/synthetic/photo").content
    else:
        content = client.get(demo_order["photos"][-1]["url"]).content
    if source == "raw_without_demo_order":
        # This case exercises the catalog raw hash, without a previously tagged public order.
        with store.connect() as db:
            db.execute("DELETE FROM orders WHERE id=?", (demo_order["id"],))
    order = client.post("/api/orders", json={
        "title": "SYNTHETIC ordinary upload source guard", "requirements": demo_order["requirements"]}).json()["order"]
    order = client.post(f"/api/orders/{order['id']}/photos", data={"expected_revision": 1},
                        files={"photo": ("copy.png", content, "image/png")}).json()["order"]
    if source == "region_in_order":
        root = order["photos"][-1]
        order = client.post(f"/api/orders/{order['id']}/inspection-region", json={
            "expected_revision": 1, "expected_photo_id": root["id"],
            "expected_evidence_epoch": order["evidence_epoch"], "root_photo_id": root["id"],
            "mode": "region", "region_xyxy": [20, 20, 400, 300],
            "confirmed_all_items_inside": True}).json()["order"]
    assert "demo_source" not in order
    analyzer.result = analyzer.observation(order["requirements"])
    analyzer.result["backend"] = "mlx"  # Synthetic persisted metadata; no actual model/physical event.
    checked = client.post(f"/api/orders/{order['id']}/inspect", json={
        "expected_revision": 1, "photo_id": order["photos"][-1]["id"]})
    assert checked.status_code == 200, checked.text
    order = checked.json()["order"]
    assert order["status"] == "ready"
    response = client.post(f"/api/orders/{order['id']}/complete", json={
        "expected_revision": 1, "check_id": order["latest_check"]["id"], "confirmed": True,
        "idempotency_key": "known-public-copy-cannot-complete"})
    assert response.status_code == 409, response.text
    assert "公开" in response.json()["detail"]
    assert read(client, order)["completions"] == []


def test_unregistered_synthetic_upload_retains_existing_completion_contract(client, inspected):
    order = inspected["order"]
    assert order["latest_check"]["backend"] == "test"
    response = client.post(f"/api/orders/{order['id']}/complete", json={
        "expected_revision": 1, "check_id": order["latest_check"]["id"], "confirmed": True,
        "idempotency_key": "synthetic-existing-complete-contract"})
    assert response.status_code == 200, response.text
