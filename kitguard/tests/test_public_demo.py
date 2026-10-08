"""Isolated synthetic source files test demo provenance, not recognition accuracy."""

import hashlib

import pytest
from fastapi.testclient import TestClient

from kitguard.app import create_app


@pytest.fixture
def demo_client(tmp_path, monkeypatch, analyzer, image_bytes):
    import kitguard.app as module

    source = tmp_path / "public-dataset"
    source.mkdir()
    raw = image_bytes(17)
    (source / "fixture.png").write_bytes(raw)
    spec = {
        "sample_id": "engineering", "title": "SYNTHETIC PUBLIC DEMO FIXTURE",
        "requirements": {"bolt": 1, "nut": 1, "washer": 0, "bracket": 0},
        "image": "fixture.png", "source_case_id": "engineering-only", "derived_view": False,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "source_url": "https://example.invalid/test-only", "license": "SYNTHETIC TEST ONLY",
        "source_note": "No model accuracy claim",
    }
    monkeypatch.setattr(module, "PUBLIC_DEMOS", [spec])
    app = create_app(tmp_path / "app-data", analyzer=analyzer, demo_dataset_root=source)
    with TestClient(app) as client:
        yield client, source


def test_gallery_and_preview_are_read_only_and_never_run_model(demo_client, analyzer):
    client, _ = demo_client
    samples = client.get("/api/public-demos").json()["samples"]
    assert samples[0]["available"]
    assert client.get("/api/public-demos/engineering/photo").status_code == 200
    assert client.get("/api/orders").json()["orders"] == []
    assert analyzer.calls == []


@pytest.mark.parametrize("changed", ["missing", "corrupt"])
def test_missing_or_changed_public_pixels_never_create_order(demo_client, changed):
    client, source = demo_client
    if changed == "missing":
        (source / "fixture.png").unlink()
    else:
        (source / "fixture.png").write_bytes(b"SYNTHETIC CORRUPTION")
    assert not client.get("/api/public-demos").json()["samples"][0]["available"]
    assert client.post("/api/public-demos/engineering/orders").status_code in {404, 409}
    assert client.get("/api/orders").json()["orders"] == []


def test_unknown_demo_cannot_select_arbitrary_file(demo_client):
    client, _ = demo_client
    assert client.post("/api/public-demos/not-listed/orders").status_code == 404
    assert client.get("/api/orders").json()["orders"] == []


def test_demo_creates_real_photo_record_without_observation_or_completion(demo_client, analyzer):
    client, _ = demo_client
    result = client.post("/api/public-demos/engineering/orders")
    assert result.status_code == 201
    order, photo = result.json()["order"], result.json()["photo"]
    assert order["demo_source"]["kind"] == "public_photo_demo"
    assert order["demo_source"]["physical_completion_allowed"] is False
    assert order["checks"] == order["completions"] == []
    assert len(order["photos"]) == 1 and photo["revision"] == 1
    assert analyzer.calls == []
    # Even a later matching result does not authorize a physical completion for public images.
    check = client.post(f"/api/orders/{order['id']}/inspect", json={
        "photo_id": photo["id"], "expected_revision": 1,
    }).json()["check"]
    assert check["decision"] == "ready"
    denied = client.post(f"/api/orders/{order['id']}/complete", json={
        "check_id": check["id"], "expected_revision": 1, "confirmed": True,
        "idempotency_key": "public-demo-test-0001",
    })
    assert denied.status_code == 409
    saved = client.get(f"/api/orders/{order['id']}").json()["order"]
    assert saved["completions"] == []
    assert saved["status"] != "completed"


def test_demo_provenance_survives_revision(demo_client):
    client, _ = demo_client
    order = client.post("/api/public-demos/engineering/orders").json()["order"]
    changed = client.post(f"/api/orders/{order['id']}/revise", json={
        "expected_revision": 1, "requirements": {**order["requirements"], "bolt": 2},
        "instruction": "CPU fixture modification",
    }).json()["order"]
    assert changed["demo_source"] == order["demo_source"]


@pytest.mark.parametrize('endpoint', ['photo', 'orders'])
def test_verified_public_bytes_are_used_even_if_file_changes_after_read(demo_client, monkeypatch, endpoint):
    from pathlib import Path

    client, source = demo_client
    target = source / 'fixture.png'
    original = target.read_bytes()
    actual_read = Path.read_bytes
    reads = []

    def replace_after_read(path):
        content = actual_read(path)
        if path == target:
            reads.append(path)
            path.write_bytes(b'changed after validation read')
        return content

    monkeypatch.setattr(Path, 'read_bytes', replace_after_read)
    if endpoint == 'photo':
        response = client.get('/api/public-demos/engineering/photo')
        assert response.status_code == 200
        assert response.content == original
    else:
        response = client.post('/api/public-demos/engineering/orders')
        assert response.status_code == 201
        payload = response.json()
        assert payload['photo']['source_sha256'] == hashlib.sha256(original).hexdigest()
        assert payload['order']['demo_source']['source_sha256'] == payload['photo']['source_sha256']
    assert len(reads) == 1
