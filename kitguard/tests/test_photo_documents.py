"""Synthetic CPU contracts: no actual model, people, public data or field evidence."""

import hashlib
import json
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from kitguard.app import create_app
from kitguard.photo_documents import DocumentSource, digest, is_digital_only
from kitguard.store import StateError

COUNTS = {"bolt": 1, "nut": 1, "washer": 0, "bracket": 0}
IDENTITY = {"label": "SYNTHETIC CONTRACT ONLY", "repo_id": "synthetic/document-test",
            "revision": "synthetic-v1", "observer_protocol_sha256": "a" * 64,
            "observation_mode": "single", "image_max_side": 512}


@pytest.fixture
def client(tmp_path, analyzer, monkeypatch):
    # Router captures the provider at application creation, matching production.
    monkeypatch.setattr(analyzer, "status", lambda: {"available": True, "loaded": False, **IDENTITY})
    app = create_app(tmp_path / "data", analyzer=analyzer)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def metadata(**changes):
    return {"title": "Synthetic photo document", "requirements": COUNTS,
            "source_note": "Synthetic own-file declaration, not authenticated provenance",
            "source_url": "https://example.invalid/source", "license_note": "Synthetic unverified note",
            "confirmed_digital_only": True, **changes}


def create(client, raw, body=None, **extra_form):
    return client.post("/api/photo-documents", data={"metadata": json.dumps(body or metadata()), **extra_form},
                       files={"photo": ("fixture.png", raw, "image/png")})


def get(client, order):
    return client.get(f"/api/orders/{order['id']}").json()["order"]


def summary(client, order):
    result = client.get(f"/api/orders/{order['id']}/public-review-summary")
    assert result.status_code == 200, result.text
    return result.json()


def inspect(client, order, analyzer, monkeypatch, backend="mlx"):
    # Production-shaped metadata fixture; FakeAnalyzer remains the actual backend.
    monkeypatch.setattr(analyzer, "status", lambda: {"available": True, "loaded": False, **IDENTITY})
    analyzer.result = analyzer.observation(order["requirements"])
    analyzer.result["backend"] = backend
    result = client.post(f"/api/orders/{order['id']}/inspect", json={
        "expected_revision": order["revision"], "photo_id": order["photos"][-1]["id"]})
    assert result.status_code == 200, result.text
    return result.json()["order"]


def register_study(client, order):
    study = client.post("/api/studies", json={"title": "Synthetic study, no humans",
        "source_kind": "self_reported_physical", "planned_cases": 1,
        "participant_code": "fixture", "note": "Synthetic security contract only"}).json()["study"]
    return client.post(f"/api/studies/{study['id']}/cases", json={"label": "synthetic",
        "order_id": order["id"], "expected_revision": order["revision"],
        "photo_id": order["photos"][-1]["id"], "truth": COUNTS, "truth_repeat": COUNTS,
        "confirmed_independent": True, "source_note": "Not an actual field claim"})


def manual(client, order):
    return client.post(f"/api/orders/{order['id']}/manual-review", json={
        "expected_revision": order["revision"], "expected_evidence_epoch": order["evidence_epoch"],
        "photo_id": order["photos"][-1]["id"], "check_id": (order.get("latest_check") or {}).get("id"),
        "actual_counts": COUNTS, "operator_code": "synthetic", "reason": "Contract, no actual person",
        "confirmed_physical": True, "confirmed_current_bom": True, "idempotency_key": "synthetic-manual"})


def inventory(store):
    with store.connect() as db:
        return (db.execute("SELECT count(*) FROM orders").fetchone()[0],
                db.execute("SELECT count(*) FROM photos").fetchone()[0],
                tuple(sorted(p.name for p in store.photos_dir.iterdir())))


def test_atomic_registration_and_bound_declaration(client, image_bytes, analyzer):
    raw = image_bytes(12, exif=True)
    result = create(client, raw)
    assert result.status_code == 201, result.text
    order, photo = result.json()["order"], result.json()["photo"]
    source = order["document_source"]
    assert DocumentSource.model_validate(source).model_dump() == source
    assert source["verification"] == "user_declared_unverified" and source["physical_completion_allowed"] is False
    assert is_digital_only(order) and "demo_source" not in order
    assert source["source_sha256"] == hashlib.sha256(raw).hexdigest()
    stored = client.get(photo["url"]).content
    assert source["storage_sha256"] == hashlib.sha256(stored).hexdigest() == photo["sha256"]
    assert source["original_root_photo_id"] == photo["id"]
    assert photo["document_source"] == source and photo["physical_capture"] is False
    assert source["statement_sha256"] == digest({k: metadata()[k] for k in ("source_note", "source_url", "license_note")})
    assert inventory(client.app.state.store)[:2] == (1, 1)
    assert not analyzer.calls and order["latest_check"] is None
    assert summary(client, order)["scope"] == "photo_document_digital_review"
    assert not summary(client, order)["can_review"]


@pytest.mark.parametrize("change", [
    {"source_note": " "}, {"source_url": "javascript:alert(1)"}, {"source_url": "file:///private/x"},
    {"source_url": "https://user:secret@example.invalid/x"}, {"source_url": "https://example.invalid:bad/x"},
    {"source_url": "https://example.invalid/\npath"}, {"source_url": "//example.invalid"},
    {"confirmed_digital_only": 1}, {"confirmed_digital_only": False},
    {"kind": "public_photo_demo"}, {"demo_source": {"sample_id": "bag-revision"}},
    {"document_source": {}}, {"physical_completion_allowed": True},
    {"requirements": {**COUNTS, "nut": 4}}, {"title": " "},
])
def test_invalid_metadata_cannot_leave_partial_order(client, image_bytes, change):
    before = inventory(client.app.state.store)
    result = create(client, image_bytes(), metadata(**change))
    assert result.status_code == 422, result.text
    assert inventory(client.app.state.store) == before


def test_optional_declarations_and_no_remote_fetch(client, image_bytes, monkeypatch):
    import socket

    def forbidden(*args, **kwargs):
        pytest.fail("No network source retrieval is permitted")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    for url in (None, "", "https://127.0.0.1:9/not-fetched"):
        result = create(client, image_bytes(), metadata(source_url=url, license_note=None))
        assert result.status_code == 201, result.text
        assert result.json()["order"]["document_source"]["source_url"] == (url or None)


def test_bad_photo_and_extra_form_leave_no_registration(client, image_bytes):
    assert create(client, b"not an image").status_code == 422
    assert create(client, image_bytes(), catalog_initial="true").status_code == 422
    assert inventory(client.app.state.store) == (0, 0, ())


def test_database_failure_rolls_back_photo_order_and_file(client, image_bytes):
    store = client.app.state.store
    with store.connect() as db:
        db.execute("CREATE TRIGGER fixture_fail BEFORE INSERT ON orders "
                   "BEGIN SELECT RAISE(ABORT, 'Synthetic failure after photo row insert'); END")
    assert create(client, image_bytes()).status_code == 500
    assert inventory(store) == (0, 0, ())


def test_existing_photo_is_not_deleted_on_creation_collision(client, image_bytes, monkeypatch):
    import kitguard.app as app_module

    store = client.app.state.store
    path = store.photos_dir / "img_collision.jpg"
    path.write_bytes(b"preexisting sentinel")
    monkeypatch.setattr(app_module, "uid", lambda prefix: "img_collision")
    assert create(client, image_bytes()).status_code == 500
    assert path.read_bytes() == b"preexisting sentinel"
    assert inventory(store)[:2] == (0, 0)


def test_order_uid_collision_preserves_original_and_rolls_back_new_photo(client, image_bytes, monkeypatch):
    import kitguard.store as store_module

    original = client.post("/api/orders", json={"title": "Existing unrelated order", "requirements": COUNTS}).json()["order"]
    original = client.post(f"/api/orders/{original['id']}/photos", data={"expected_revision": 1},
                          files={"photo": ("existing.png", image_bytes(4), "image/png")}).json()["order"]
    store = client.app.state.store
    before = inventory(store)
    with store.connect() as db:
        before_body = db.execute("SELECT body FROM orders WHERE id=?", (original["id"],)).fetchone()["body"]
    original_bytes = client.get(original["photos"][-1]["url"]).content
    original_uid = store_module.uid
    monkeypatch.setattr(store_module, "uid", lambda prefix: original["id"] if prefix == "ord" else original_uid(prefix))
    response = create(client, image_bytes(8))
    assert response.status_code == 500, response.text
    viewed = get(client, original)
    assert viewed.pop("digital_review_feedback")["status"] == "not_applicable"
    assert viewed == original
    with store.connect() as db:
        assert db.execute("SELECT body FROM orders WHERE id=?", (original["id"],)).fetchone()["body"] == before_body
    assert client.get(original["photos"][-1]["url"]).content == original_bytes
    assert inventory(store) == before


def test_private_document_errors_do_not_claim_public_catalog(client, image_bytes):
    document = create(client, image_bytes(6)).json()["order"]
    store = client.app.state.store
    with store.connect() as db, pytest.raises(StateError) as caught:
        store._nonpublic_family(db, document, document["photos"][-1])
    assert "资料" in str(caught.value) and "公开" not in str(caught.value)
    result = client.post(f"/api/orders/{document['id']}/complete", json={"expected_revision": 1,
        "check_id": "synthetic-no-check", "confirmed": True, "idempotency_key": "document-wording-complete"})
    assert result.status_code == 409
    assert "资料" in result.json()["detail"] and "公开" not in result.json()["detail"]
    with store.connect() as db, pytest.raises(StateError) as caught:
        client.app.state.task_trials.verify_ai(db, {}, {}, document)
    assert "资料" in str(caught.value) and "公开" not in str(caught.value)
    copied = client.post("/api/orders", json={"title": "Private document copy", "requirements": COUNTS}).json()["order"]
    copied = client.post(f"/api/orders/{copied['id']}/photos", data={"expected_revision": 1},
                         files={"photo": ("copy.png", image_bytes(6), "image/png")}).json()["order"]
    with store.connect() as db, pytest.raises(StateError) as caught:
        store._nonpublic_family(db, copied, copied["photos"][-1])
    assert "资料" in str(caught.value) and "公开" not in str(caught.value)
    result = register_study(client, copied)
    assert result.status_code == 409
    assert "资料" in result.json()["detail"] and "公开" not in result.json()["detail"]


def test_root_locked_references_allowed_and_ordinary_source_injection_rejected(client, image_bytes):
    order = create(client, image_bytes()).json()["order"]
    initial_source = deepcopy(order["document_source"])
    before = inventory(client.app.state.store)
    result = client.post(f"/api/orders/{order['id']}/photos", data={"expected_revision": 1},
                         files={"photo": ("different.png", image_bytes(1), "image/png")})
    assert result.status_code == 409 and inventory(client.app.state.store) == before
    ref = client.post(f"/api/orders/{order['id']}/references/nut", data={"expected_revision": 1},
                      files={"photo": ("reference.png", image_bytes(3), "image/png")})
    assert ref.status_code == 201
    assert ref.json()["order"]["document_source"] == initial_source
    for key in ("demo_source", "document_source"):
        response = client.post("/api/orders", json={"title": "forged", "requirements": COUNTS, key: initial_source})
        assert response.status_code == 422


def test_review_revision_and_same_image_replay_require_new_observation(client, image_bytes, analyzer, monkeypatch):
    order = create(client, image_bytes()).json()["order"]
    order = inspect(client, order, analyzer, monkeypatch)
    current = summary(client, order)
    assert current["can_review"], current["review_blockers"]
    body = {**current["review_request"], "operator_code": "ENGINEERING-FIXTURE", "conclusion": "disputed",
            "note": "Synthetic software contract; no real user feedback", "confirmed_digital_only": True,
            "idempotency_key": "synthetic-document-review"}
    result = client.post(f"/api/orders/{order['id']}/public-review", json=body)
    assert result.status_code == 200, result.text
    receipt = result.json()["review"]
    assert receipt["physical_completion"] is False and receipt["user_validation"] is False
    assert receipt["scope"] == "photo_document_digital_review"
    assert receipt["source"] == order["document_source"]
    source = deepcopy(order["document_source"])
    old = order["latest_check"]["id"]
    order = client.post(f"/api/orders/{order['id']}/revise", json={"expected_revision": 1,
        "requirements": {**COUNTS, "bolt": 2}, "instruction": "Synthetic actual order change"}).json()["order"]
    assert not summary(client, order)["can_review"]
    assert not summary(client, order)["reviews"][0]["current"]
    assert client.post(f"/api/orders/{order['id']}/public-review", json={**body, "idempotency_key": "stale-review-key"}).status_code == 409
    replay = client.post(f"/api/orders/{order['id']}/public-replay", json={
        **summary(client, order)["replay_request"], "confirmed_no_physical_capture": True,
        "idempotency_key": "synthetic-document-replay"})
    assert replay.status_code == 200, replay.text
    order = replay.json()["order"]
    assert order["document_source"] == source and len(analyzer.calls) == 1
    assert replay.json()["photo"]["capture_kind"] == "photo_document_replay"
    assert replay.json()["photo"]["sha256"] == source["storage_sha256"]
    assert not summary(client, order)["can_review"]
    order = inspect(client, order, analyzer, monkeypatch)
    assert summary(client, order)["can_review"] and len(analyzer.calls) == 2
    assert order["latest_check"]["id"] != old
    exported = client.get(f"/api/orders/{order['id']}/export").json()["order"]
    assert exported["document_source"] == source and exported["public_reviews"][0]["id"] == receipt["id"]


def test_test_backend_cannot_be_digital_review_evidence(client, image_bytes, analyzer, monkeypatch):
    order = inspect(client, create(client, image_bytes()).json()["order"], analyzer, monkeypatch, backend="test")
    assert summary(client, order)["can_review"] is False
    assert not get(client, order).get("public_reviews")


@pytest.mark.parametrize("field,value", [("source_note", "silently changed"), ("source_sha256", "f" * 64),
                                       ("storage_sha256", "f" * 64), ("physical_completion_allowed", 0),
                                       ("kind", "public_photo_demo")])
def test_changed_source_rejected_by_lineage_before_inspection(client, image_bytes, analyzer, field, value):
    order = create(client, image_bytes()).json()["order"]
    with client.app.state.store.transaction(order["id"]) as (_, saved):
        saved["document_source"][field] = value
    assert client.get(f"/api/orders/{order['id']}/public-review-summary").status_code == 409
    result = client.post(f"/api/orders/{order['id']}/inspect", json={"expected_revision": 1,
        "photo_id": order["photos"][-1]["id"]})
    assert result.status_code == 409 and not analyzer.calls


@pytest.mark.parametrize("copy_kind", ["direct", "raw", "normalized", "region"])
def test_digital_document_and_known_copies_cannot_be_physical(client, image_bytes, analyzer, monkeypatch, copy_kind):
    raw = image_bytes(9)
    original = create(client, raw).json()["order"]
    if copy_kind == "region":
        p = original["photos"][-1]
        original = client.post(f"/api/orders/{original['id']}/inspection-region", json={
            "expected_revision": 1, "expected_photo_id": p["id"], "expected_evidence_epoch": original["evidence_epoch"],
            "root_photo_id": p["id"], "mode": "region", "region_xyxy": [10, 10, 400, 300],
            "confirmed_all_items_inside": True}).json()["order"]
    order = original
    if copy_kind != "direct":
        content = raw if copy_kind == "raw" else client.get(original["photos"][-1]["url"]).content
        order = client.post("/api/orders", json={"title": "Synthetic ordinary copy", "requirements": COUNTS}).json()["order"]
        order = client.post(f"/api/orders/{order['id']}/photos", data={"expected_revision": 1},
                           files={"photo": ("copy.png", content, "image/png")}).json()["order"]
    assert register_study(client, order).status_code == 409
    assert manual(client, order).status_code == 409
    order = inspect(client, order, analyzer, monkeypatch)
    assert client.post(f"/api/orders/{order['id']}/complete", json={"expected_revision": 1,
        "check_id": order["latest_check"]["id"], "confirmed": True,
        "idempotency_key": "blocked-digital-complete"}).status_code == 409
    assert manual(client, order).status_code == 409
    store = client.app.state.store
    with store.connect() as db, pytest.raises(StateError):
        # Direct bounded recorder boundary, before any task state or real study exists.
        client.app.state.task_trials.verify_ai(db, {}, {}, order)
    after = get(client, order)
    assert not after["completions"] and not after["manual_reviews"]


def test_document_and_ordinary_upload_produce_identical_model_inputs(client, image_bytes, analyzer):
    raw = image_bytes(8)
    document = create(client, raw).json()["order"]
    ordinary = client.post("/api/orders", json={"title": "Synthetic input comparison", "requirements": COUNTS}).json()["order"]
    ordinary = client.post(f"/api/orders/{ordinary['id']}/photos", data={"expected_revision": 1},
        files={"photo": ("fixture.png", raw, "image/png")}).json()["order"]
    observations = []
    for order in (document, ordinary):
        result = client.post(f"/api/orders/{order['id']}/inspect", json={
            "expected_revision": 1, "photo_id": order["photos"][-1]["id"]})
        assert result.status_code == 200, result.text
        observations.append(result.json()["check"]["observed"])
    calls = analyzer.calls
    assert len(calls) == 2 and calls[0]["requirements"] == calls[1]["requirements"] == COUNTS
    assert calls[0]["references"] == calls[1]["references"] == {}
    assert calls[0]["image_path"].read_bytes() == calls[1]["image_path"].read_bytes()
    assert observations[0] == observations[1]
