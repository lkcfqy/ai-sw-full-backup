"""Scope provenance and budget regressions using CPU-only synthetic API fixtures."""

import io
import json
from copy import deepcopy
from zipfile import ZipFile

from conftest import REQUIREMENTS, FakeAnalyzer

from kitguard.feedback import _photo_content_hashes


def saved(client, order):
    return client.app.state.store.get(order["id"])


def region(client, order, rectangle):
    current = saved(client, order)
    photo = current["photos"][-1]
    return client.post(f"/api/orders/{order['id']}/inspection-region", json={
        "expected_revision": current["revision"], "expected_photo_id": photo["id"],
        "expected_evidence_epoch": current["evidence_epoch"],
        "root_photo_id": photo.get("root_photo_id", photo["id"]),
        "mode": "region" if rectangle is not None else "whole_image",
        "region_xyxy": rectangle, "confirmed_all_items_inside": True,
    })


def inspect(client, order):
    current = saved(client, order)
    result = client.post(f"/api/orders/{order['id']}/inspect", json={
        "expected_revision": current["revision"], "photo_id": current["photos"][-1]["id"],
    })
    assert result.status_code == 200, result.text
    return result.json()["check"]


def register(client, order):
    result = client.post("/api/studies", json={"title": "Synthetic region regression", "source_kind": "engineering_fixture",
                         "planned_cases": 1, "participant_code": "v05-cpu", "note": "CPU fixtures only"})
    study = result.json()["study"]
    current = saved(client, order)
    response = client.post(f"/api/studies/{study['id']}/cases", json={
        "label": "Declared synthetic scope", "order_id": order["id"], "expected_revision": current["revision"],
        "photo_id": current["photos"][-1]["id"], "truth": REQUIREMENTS, "truth_repeat": REQUIREMENTS,
        "confirmed_independent": True, "source_note": "No real material or human study",
    })
    assert response.status_code == 201, response.text
    return response.json()["study"]


def test_clear_crop_does_not_reset_same_root_recapture_budget(client, order, upload, analyzer):
    uncertain = {**REQUIREMENTS, "nut": None}
    analyzer.result = FakeAnalyzer.observation(uncertain, action="recapture", issues=["Synthetic nut uncertainty"])
    decisions = []
    for variant in (1, 2, 3):
        upload(order, seed=variant)
        decisions.append(inspect(client, order)["decision"])
    assert decisions == ["recapture", "recapture", "manual"]
    assert region(client, order, [0, 0, 320, 320]).status_code == 200
    analyzer.result = FakeAnalyzer.observation(REQUIREMENTS)
    assert inspect(client, order)["decision"] == "ready"
    assert region(client, order, None).status_code == 200
    analyzer.result = FakeAnalyzer.observation(uncertain, action="recapture", issues=["Synthetic nut uncertainty"])
    check = inspect(client, order)
    assert check["decision"] == "manual"
    assert check["evidence_feedback"]["outcome"] == "inspection_scope_changed"
    assert check["evidence_feedback"]["observed_changes"] == []


def test_same_order_exact_stored_jpeg_upload_joins_known_family_without_guessing_other_sources():
    records = {"photos": [
        {"id": "original", "sha256": "a" * 64, "source_sha256": "f" * 64},
        {"id": "crop", "sha256": "b" * 64, "source_family_sha256": "a" * 64},
        {"id": "reuploaded", "sha256": "c" * 64, "source_sha256": "b" * 64},
        {"id": "unknown1", "sha256": "d" * 64, "source_sha256": "9" * 64},
        {"id": "unknown2", "sha256": "e" * 64, "source_sha256": "9" * 64},
    ]}
    identities = _photo_content_hashes(records)
    assert identities["original"] == identities["crop"] == identities["reuploaded"]
    assert identities["unknown1"] != identities["unknown2"]


def test_closed_field_keeps_historical_region_after_workbench_reselection(client, order, upload):
    root = upload(order).json()["photo"]
    first = region(client, order, [20, 30, 320, 330]).json()["photo"]
    study = register(client, order)
    case = study["cases"][0]
    assert client.post(f"/api/studies/{study['id']}/close", json={"confirmed": True}).status_code == 200
    second = region(client, order, [40, 60, 340, 360]).json()["photo"]
    assert first["id"] != second["id"]
    response = client.get(f"/api/studies/{study['id']}/evidence.zip")
    assert response.status_code == 200, response.text[:200]
    with ZipFile(io.BytesIO(response.content)) as archive:
        manifest = json.loads(archive.read("MANIFEST.json"))
        study_json = json.loads(archive.read("STUDY.json"))
        assert study_json["study"]["cases"][0]["inspection_scope"] == case["inspection_scope"]
        binding = {item["role"]: item for item in manifest["photo_bindings"]}
        assert binding["target"]["photo_id"] == first["id"]
        assert binding["root"]["photo_id"] == root["id"]
        assert "<rect" in archive.read("PHOTOS.html").decode()


def test_scope_policy_cannot_be_downgraded_by_deleting_case_scope(client, order, upload):
    upload(order)
    study = register(client, order)
    recorder = client.app.state.studies
    with recorder.transaction(study["id"]) as (_, record):
        assert record["protocol"]["inspection_scope_policy"] == "operator_region_v1"
        del record["cases"][0]["inspection_scope"]
    assert client.post(f"/api/studies/{study['id']}/freeze", json={"confirmed": True}).status_code == 409
    assert client.post(f"/api/studies/{study['id']}/close", json={"confirmed": True}).status_code == 200
    assert client.get(f"/api/studies/{study['id']}/export").status_code == 409


def test_legacy_root_record_keeps_whole_image_bytes_and_accepts_region(client, order, upload):
    photo = upload(order).json()["photo"]
    store = client.app.state.store
    original = store.photo_path(photo["id"]).read_bytes()
    with store.transaction(order["id"]) as (_, record):
        for key in ("kind", "scope_mode", "root_photo_id", "root_photo_sha256", "source_family_sha256"):
            record["photos"][-1].pop(key)
    full = region(client, order, None)
    assert full.status_code == 200 and full.json()["changed"] is False
    assert store.photo_path(photo["id"]).read_bytes() == original
    selected = region(client, order, [0, 0, 200, 200])
    assert selected.status_code == 200
    assert selected.json()["photo"]["root_photo_sha256"] == photo["sha256"]


def test_completion_rejects_check_scope_mismatch_even_when_photo_bytes_are_valid(client, order, upload):
    upload(order)
    region(client, order, [0, 0, 300, 300])
    check = inspect(client, order)
    with client.app.state.store.transaction(order["id"]) as (_, record):
        forged = deepcopy(record["latest_check"])
        forged["inspection_scope"]["region_xyxy"] = [10, 10, 310, 310]
        record["latest_check"] = forged
    result = client.post(f"/api/orders/{order['id']}/complete", json={
        "check_id": check["id"], "expected_revision": 1, "confirmed": True, "idempotency_key": "v05-scope-mismatch",
    })
    assert result.status_code == 409
