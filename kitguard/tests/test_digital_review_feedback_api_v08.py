"""Isolated synthetic API contracts: no actual model or human review evidence."""

import hashlib
import json
from copy import deepcopy
from io import BytesIO
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def digital(tmp_path, monkeypatch, analyzer, image_bytes):
    # Test process MUST set KITGUARD_DATA_DIR before importing app.
    import os
    assert os.environ.get("KITGUARD_DATA_DIR") and "test-results" in os.environ["KITGUARD_DATA_DIR"]
    from kitguard.app import create_app

    identity = {"label": "SYNTHETIC ONLY", "repo_id": "synthetic/test", "revision": "synthetic-sha",
                "observer_protocol_sha256": "e"*64, "observation_mode": "single", "image_max_side": 512}
    monkeypatch.setattr(analyzer, "status", lambda: {"available": True, **identity})
    app = create_app(tmp_path/"data", analyzer=analyzer)
    requirements = {"bolt": 2, "nut": 2, "washer": 2, "bracket": 0}
    with TestClient(app) as client:
        response = client.post("/api/photo-documents", data={"metadata": json.dumps({
            "title": "SYNTHETIC DIGITAL FEEDBACK", "requirements": requirements,
            "source_note": "Synthetic API fixture; no real source/human/model", "confirmed_digital_only": True})},
            files={"photo": ("synthetic.png", image_bytes(), "image/png")})
        assert response.status_code == 201, response.text
        order = response.json()["order"]
        analyzer.result = {**analyzer.observation(requirements), "backend": "mlx"}
        checked = client.post(f"/api/orders/{order['id']}/inspect", json={
            "expected_revision": 1, "photo_id": order["photos"][-1]["id"]})
        assert checked.status_code == 200, checked.text
        yield client, app.state.store, checked.json()["order"], identity, analyzer


def submit(client, order, conclusion, index):
    base = f"/api/orders/{order['id']}"
    summary = client.get(base+"/public-review-summary").json()
    result = client.post(base+"/public-review", json={**summary["review_request"], "operator_code": "ENGINEERING_FIXTURE",
        "conclusion": conclusion, "note": "Synthetic state contract; 0 human participants.", "confirmed_digital_only": True,
        "idempotency_key": f"synthetic-feedback-{index}"})
    assert result.status_code == 200, result.text
    return result.json()


def stored_rows(store):
    with store.connect() as db:
        return [tuple(row) for row in db.execute("SELECT id,body FROM orders ORDER BY id")]


def test_get_list_summary_and_offline_preserve_ai_and_sqlite_body(digital):
    client, store, order, _, analyzer = digital
    base = f"/api/orders/{order['id']}"
    original_check = deepcopy(order["latest_check"])
    pending = submit(client, order, "disputed", 1)["review"]["id"]
    submit(client, order, "acknowledged", 2)
    before, calls = stored_rows(store), len(analyzer.calls)
    detail = client.get(base).json()["order"]
    listed = client.get("/api/orders").json()["orders"][0]
    summary = client.get(base+"/public-review-summary").json()
    feedback = detail["digital_review_feedback"]
    assert feedback == listed["digital_review_feedback"] == summary["feedback"]
    assert feedback["status"] == "needs_clarification" and feedback["pending_review_ids"] == [pending]
    assert all(r["current"] for r in summary["reviews"])
    assert detail["latest_check"] == original_check and detail["status"] == "ready"
    assert "digital_review_feedback" not in store.get(order["id"])
    export = client.get(base+"/evidence.zip")
    assert export.status_code == 200
    with ZipFile(BytesIO(export.content)) as archive:
        html = archive.read("OPEN_ME.html").decode()
        raw = json.loads(archive.read("evidence.json"))
        assert "data-feedback-status='needs_clarification'" in html
        assert raw["order"]["latest_check"] == original_check
        for record in json.loads(archive.read("SHA256.json")):
            assert hashlib.sha256(archive.read(record["path"])).hexdigest() == record["sha256"]
    assert stored_rows(store) == before and len(analyzer.calls) == calls


def test_runtime_change_and_revision_make_history_not_resolved(digital):
    client, store, order, identity, analyzer = digital
    submit(client, order, "needs_more_evidence", 1)
    base = f"/api/orders/{order['id']}"
    before = stored_rows(store)
    identity["observer_protocol_sha256"] = "f"*64
    detail = client.get(base).json()["order"]
    summary = client.get(base+"/public-review-summary").json()
    assert detail["digital_review_feedback"] == summary["feedback"]
    assert summary["feedback"]["status"] == "not_applicable"
    assert not any(r["current"] for r in summary["reviews"])
    # Offline is explicitly the stored snapshot and does not query current runtime.
    with ZipFile(BytesIO(client.get(base+"/evidence.zip").content)) as archive:
        assert "data-feedback-status='needs_clarification'" in archive.read("OPEN_ME.html").decode()
    assert stored_rows(store) == before
    result = client.post(base+"/revise", json={"expected_revision": 1,
        "requirements": {"bolt": 3, "nut": 2, "washer": 2, "bracket": 0}, "instruction": "SYNTHETIC revision"})
    assert result.status_code == 200
    detail = client.get(base).json()["order"]
    assert detail["digital_review_feedback"]["status"] == "not_applicable"
    assert len(detail["public_reviews"]) == 1 and len(analyzer.calls) == 1


def test_new_check_does_not_silently_clear_historical_disagreement(digital):
    client, _, order, _, _ = digital
    first = submit(client, order, "disputed", 1)["review"]
    base = f"/api/orders/{order['id']}"
    result = client.post(base+"/inspect", json={"expected_revision": 1, "photo_id": order["photos"][-1]["id"]})
    assert result.status_code == 200
    summary = client.get(base+"/public-review-summary").json()
    assert summary["feedback"]["status"] == "none" and not summary["reviews"][0]["current"]
    assert summary["reviews"][0]["receipt"]["id"] == first["id"]
    with ZipFile(BytesIO(client.get(base+"/evidence.zip").content)) as archive:
        assert "不适用于当前核验 · 不代表已解决" in archive.read("OPEN_ME.html").decode()


def test_get_status_failure_does_not_hide_orders_or_claim_no_pending(digital, monkeypatch):
    client, store, order, _, analyzer = digital
    submit(client, order, "disputed", 1)
    before = stored_rows(store)
    calls = []
    def unavailable_status():
        calls.append(True)
        raise RuntimeError("SYNTHETIC status metadata unavailable")
    monkeypatch.setattr(analyzer, "status", unavailable_status)
    detail = client.get(f"/api/orders/{order['id']}")
    assert detail.status_code == 200
    assert detail.json()["order"]["digital_review_feedback"]["status"] == "not_applicable"
    assert len(calls) == 1
    listed = client.get("/api/orders")
    assert listed.status_code == 200 and len(calls) == 2
    assert stored_rows(store) == before


def test_no_review_orders_do_not_query_runtime_status(digital, monkeypatch):
    client, _, order, _, analyzer = digital
    def forbidden_status():
        raise AssertionError("No opinion needs live runtime binding")
    monkeypatch.setattr(analyzer, "status", forbidden_status)
    value = client.get(f"/api/orders/{order['id']}").json()["order"]["digital_review_feedback"]
    assert value["status"] == "none" and value["binding_scope"] == "saved_snapshot"
    ordinary = client.post("/api/orders", json={"title": "SYNTHETIC ORDINARY", "requirements": order["requirements"]}).json()["order"]
    assert client.get(f"/api/orders/{ordinary['id']}").json()["order"]["digital_review_feedback"]["status"] == "not_applicable"
    assert client.get("/api/orders").status_code == 200
