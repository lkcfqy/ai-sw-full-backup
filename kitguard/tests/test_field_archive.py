"""Photographic byte provenance for local study exports; only engineering fixtures."""

import hashlib
import io
import json
from zipfile import ZipFile

from test_field_study_flow import prepared


def test_closed_archive_has_every_actual_photo_and_safe_offline_links(client, order, upload, image_bytes):
    reference = client.post(f'/api/orders/{order["id"]}/references/nut',
                            data={"expected_revision": 1},
                            files={"photo": ("fixture.png", image_bytes(6), "image/png")})
    assert reference.status_code == 201, reference.text
    order = reference.json()["order"]
    study, photo = prepared(client, order, upload)
    assert client.get(f'/api/studies/{study["id"]}/evidence.zip').status_code == 409
    client.post(f'/api/studies/{study["id"]}/close', json={"confirmed": True})
    response = client.get(f'/api/studies/{study["id"]}/evidence.zip')
    assert response.status_code == 200
    with ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.testzip() is None
        manifest = json.loads(archive.read("MANIFEST.json"))
        assert manifest["source_kind"] == "engineering_fixture"
        assert {b["role"] for b in manifest["photo_bindings"]} == {"target", "reference:nut"}
        assert set(archive.namelist()) == {"MANIFEST.json"} | {f["path"] for f in manifest["files"]}
        for entry in manifest["files"]:
            raw = archive.read(entry["path"])
            assert len(raw) == entry["bytes"]
            assert hashlib.sha256(raw).hexdigest() == entry["sha256"]
        bound = next(b for b in manifest["photo_bindings"] if b["role"] == "target")
        assert archive.read(bound["archive_path"]) == client.app.state.store.photo_path(photo["id"]).read_bytes()
        for name in ("OPEN_ME.html", "PHOTOS.html", "REPORT.html"):
            rendered = archive.read(name).decode()
            assert '<script' not in rendered and 'src="http' not in rendered
        assert "engineering_fixture" in archive.read("OPEN_ME.html").decode()
        assert json.loads(archive.read("STUDY.json"))["study"]["report"]["methods"]["kitguard"]["not_started"] == 1
    assert list((client.app.state.store.directory / "exports").glob("study-*.zip")) == []


def test_archive_refuses_changed_photo_after_study_closes(client, order, upload):
    study, photo = prepared(client, order, upload)
    client.post(f'/api/studies/{study["id"]}/close', json={"confirmed": True})
    client.app.state.store.photo_path(photo["id"]).write_bytes(b"not the bound pixels")
    response = client.get(f'/api/studies/{study["id"]}/evidence.zip')
    assert response.status_code == 409
    assert not (client.app.state.store.directory / "exports").exists()
