"""Synthetic CPU contracts for v0.8 reference provenance; never call a real model."""

import copy
import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from test_guarded_review import cpu_engine, fixture_png, inspect, make_order

from kitguard.app import create_app
from kitguard.schemas import Observation


def trace_engine(**kwargs):
    engine, calls = cpu_engine(**kwargs)
    status = engine.status
    engine.status = lambda: {
        **status(), "observer_protocol_sha256": engine.protocol_sha256,
        "reference_evidence_protocol": "reference_inputs_v1",
    }
    return engine, calls


def upload_reference(client, order_id, part, payload):
    response = client.post(
        f"/api/orders/{order_id}/references/{part}", data={"expected_revision": 1},
        files={"photo": ("SYNTHETIC_REFERENCE.png", payload, "image/png")},
    )
    assert response.status_code == 201, response.text
    return response.json()["photo"]


def test_actual_reference_png_order_and_stages_are_recorded_without_counting_them(tmp_path):
    target = tmp_path / "SYNTHETIC_TARGET.png"
    target.write_bytes(fixture_png())
    references = {}
    for part, size, color in (("washer", (64, 120), "red"), ("nut", (800, 600), "green")):
        path = tmp_path / f"SYNTHETIC_{part}.png"
        Image.new("RGB", size, color).save(path)
        references[part] = path
    engine, calls = trace_engine()
    result = engine.observe(target, {"bolt": 0, "nut": 0, "washer": 1, "bracket": 0}, references)
    evidence = Observation.model_validate(result).reference_evidence
    assert result["observed"] == {"bolt": 0, "nut": 0, "washer": 1, "bracket": 0}
    assert [image.part for image in evidence.images] == ["nut", "washer"]
    assert [image.image_index for image in evidence.images] == [2, 3]
    assert [image.prepared_size for image in evidence.images] == [[512, 384], [64, 120]]
    assert [image.stored_sha256 for image in evidence.images] == [
        hashlib.sha256(references[p].read_bytes()).hexdigest() for p in ("nut", "washer")
    ]
    assert [image.prepared_sha256 for image in evidence.images] == calls[0]["hashes"][1:]
    assert calls[0]["hashes"][1:] == calls[1]["hashes"][1:]
    assert not set(calls[2]["hashes"]) & set(calls[0]["hashes"][1:])
    assert [stage.model_dump() for stage in evidence.stages] == [
        {"stage": "original", "reference_image_indices": [2, 3], "status": "completed"},
        {"stage": "rotate_90_ccw", "reference_image_indices": [2, 3], "status": "completed"},
        {"stage": "identity", "reference_image_indices": [], "status": "completed"},
    ]
    assert evidence.guarded_identity_uses_references is False
    assert evidence.prepared_bytes_retained is False
    assert evidence.observer_protocol_sha256 == engine.protocol_sha256
    assert result["reference_evidence"] == engine.status()["last_observation_attempt"]["reference_evidence"]


def test_api_binds_reference_snapshot_and_preserves_it_after_replacement(tmp_path, image_bytes):
    engine, calls = trace_engine()
    with TestClient(create_app(data_dir=tmp_path, analyzer=engine)) as client:
        order_id, target = make_order(client)
        nut = upload_reference(client, order_id, "nut", image_bytes(1))
        washer = upload_reference(client, order_id, "washer", image_bytes(2))
        result = inspect(client, order_id, target)
        assert result.status_code == 200, result.text
        check = result.json()["check"]
        saved = copy.deepcopy(check["reference_evidence"])
        for item, reference in zip(saved["images"], (nut, washer), strict=True):
            assert item["photo_id"] == reference["id"]
            assert item["stored_sha256"] == reference["sha256"]
            assert item["upload_source_sha256"] == reference["source_sha256"]
            assert item["prepared_sha256"] == calls[0]["hashes"][item["image_index"] - 1]
        replacement = upload_reference(client, order_id, "nut", image_bytes(3))
        current = client.get(f"/api/orders/{order_id}").json()["order"]
        assert current["references"]["nut"]["id"] == replacement["id"]
        assert current["latest_check"]["valid"] is False
        assert current["latest_check"]["reference_evidence"] == saved
        assert current["checks"][-1]["reference_evidence"] == saved
        assert current["evidence_epoch"] > check["evidence_epoch"]


@pytest.mark.parametrize("mutation", [
    "source_sha", "missing_part", "wrong_protocol", "missing_evidence", "missing_stages",
    "wrong_mode", "false_skip", "failed_original", "out_of_order",
])
def test_api_rejects_unbound_reference_metadata(tmp_path, image_bytes, mutation):
    def mutate(observation):
        if mutation == "missing_evidence":
            observation.pop("reference_evidence")
        elif mutation == "source_sha":
            observation["reference_evidence"]["images"][0]["stored_sha256"] = "0" * 64
        elif mutation == "wrong_protocol":
            observation["reference_evidence"]["observer_protocol_sha256"] = "0" * 64
        elif mutation == "missing_stages":
            observation["reference_evidence"]["stages"] = []
        elif mutation == "wrong_mode":
            observation["reference_evidence"]["observation_mode"] = "single"
        elif mutation == "false_skip":
            observation["reference_evidence"]["stages"][-1]["status"] = "skipped_no_candidates"
        elif mutation == "failed_original":
            observation["reference_evidence"]["stages"][0]["status"] = "failed"
        elif mutation == "out_of_order":
            observation["reference_evidence"]["stages"].reverse()
        else:
            observation["reference_evidence"]["images"] = []
            for stage in observation["reference_evidence"]["stages"]:
                stage["reference_image_indices"] = []

    engine, _ = trace_engine(final_mutator=mutate)
    with TestClient(create_app(data_dir=tmp_path, analyzer=engine)) as client:
        order_id, target = make_order(client)
        upload_reference(client, order_id, "nut", image_bytes(1))
        response = inspect(client, order_id, target)
        assert response.status_code == 503
        current = client.get(f"/api/orders/{order_id}").json()["order"]
        assert current["latest_check"] is None
        assert current["status"] != "ready"


def test_failed_identity_retains_reference_inputs_and_stage_outcome(tmp_path, image_bytes):
    engine, calls = trace_engine(third_failure=True)
    with TestClient(create_app(data_dir=tmp_path, analyzer=engine)) as client:
        order_id, target = make_order(client)
        reference = upload_reference(client, order_id, "nut", image_bytes(1))
        assert inspect(client, order_id, target).status_code == 503
        current = client.get(f"/api/orders/{order_id}").json()["order"]
        event = next(e for e in current["events"] if e["kind"] == "inspection_failed")
        evidence = event["payload"]["observation_diagnostics"]["reference_evidence"]
        assert evidence["images"][0]["stored_sha256"] == reference["sha256"]
        assert evidence["images"][0]["prepared_sha256"] == calls[0]["hashes"][1]
        assert [s["status"] for s in evidence["stages"]] == ["completed", "completed", "failed"]
        assert evidence["stages"][-1]["reference_image_indices"] == []
        assert current["latest_check"] is None


@pytest.mark.parametrize("reason", ["skipped_no_candidates", "skipped_base_unclear"])
def test_identity_skips_are_explicit_and_never_claim_reference_or_identity_use(tmp_path, reason):
    target = tmp_path / "SYNTHETIC_TARGET.png"
    target.write_bytes(fixture_png())
    engine, calls = trace_engine()
    original_generate = engine._generate

    def generate(*args, **kwargs):
        inventory = original_generate(*args, **kwargs)
        if reason == "skipped_no_candidates" or len(calls) == 2:
            inventory.objects[0].part = "bolt"
        return inventory

    engine._generate = generate
    result = engine.observe(target, {"bolt": 1, "nut": 0, "washer": 0, "bracket": 0}, {})
    parsed = Observation.model_validate(result)
    assert parsed.identity_verification is None
    assert parsed.reference_evidence.images == []
    assert parsed.reference_evidence.stages[-1].model_dump() == {
        "stage": "identity", "reference_image_indices": [], "status": reason,
    }
    assert len(calls) == 2


def test_legacy_checks_are_not_backfilled(client, inspected, image_bytes):
    order = inspected["order"]
    before = inspected["check"]
    assert "reference_evidence" not in before
    upload_reference(client, order["id"], "nut", image_bytes(8))
    current = client.get(f"/api/orders/{order['id']}").json()["order"]
    assert "reference_evidence" not in current["latest_check"]
    assert all("reference_evidence" not in c for c in current["checks"])
    assert "reference_evidence" not in json.dumps(before)
