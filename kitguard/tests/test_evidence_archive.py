"""Portable archive checks with explicit engineering fixtures, never model accuracy."""

import hashlib
import io
import json
import zipfile

from kitguard.evidence import render_viewer


def upload(client, order, raw, path="photos"):
    response = client.post(
        f"/api/orders/{order['id']}/{path}",
        files={"photo": ("fixture.png", raw, "image/png")},
        data={"expected_revision": order["revision"]},
    )
    assert response.status_code == 201
    return response.json()["photo"]


def test_archive_contains_old_references_and_only_its_order(client, order, image_bytes):
    old = upload(client, order, image_bytes(1), "references/nut")
    new = upload(client, order, image_bytes(2), "references/nut")
    photo = upload(client, order, image_bytes(3))
    other = client.post(
        "/api/orders", json={"title": "PRIVATE OTHER ORDER", "requirements": order["requirements"]}
    ).json()["order"]
    secret = upload(client, other, image_bytes(4))
    response = client.get(f"/api/orders/{order['id']}/evidence.zip")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        assert {f"photos/{p['id']}.jpg" for p in (old, new, photo)} <= set(names)
        assert f"photos/{secret['id']}.jpg" not in names
        assert not any("sqlite" in name or name.startswith("/") or ".." in name for name in names)
        payload = json.loads(archive.read("evidence.json"))
        assert payload["order"]["id"] == order["id"]
        assert len(payload["order"]["reference_history"]) == 2
        assert b"PRIVATE OTHER ORDER" not in archive.read("evidence.json")
        for record in json.loads(archive.read("SHA256.json")):
            content = archive.read(record["path"])
            assert hashlib.sha256(content).hexdigest() == record["sha256"]
            assert len(content) == record["bytes"]
        viewer = archive.read("OPEN_ME.html").decode()
        assert "src='photos/" in viewer
        assert "fetch(" not in viewer and "<script" not in viewer


def test_archive_refuses_corrupted_photo(client, order, image_bytes):
    photo = upload(client, order, image_bytes())
    client.app.state.store.photo_path(photo["id"]).write_bytes(b"CORRUPTED TEST COPY")
    result = client.get(f"/api/orders/{order['id']}/evidence.zip")
    assert result.status_code == 409


def test_viewer_escapes_untrusted_title_and_observation_text():
    html = render_viewer(
        {
            "order": {"title": "<script>alert(1)</script>", "revision": 1, "status": "pending", "checks": []},
            "photos": [],
            "exported_at": "now",
        }
    )
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html
