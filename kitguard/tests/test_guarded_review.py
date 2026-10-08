"""Independent guarded-contract CPU fixtures; never load MLX or claim photo accuracy."""

import copy
import hashlib
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from kitguard.app import create_app
from kitguard.identity import IdentityResponse
from kitguard.schemas import Observation
from kitguard.spatial import SpatialInventory
from kitguard.vision import LocalVision, ModelOutputError


def fixture_png():
    stream = io.BytesIO()
    # Synthetic engineering pixels, not physical-object truth.
    Image.new("RGB", (160, 96), (218, 205, 184)).save(stream, format="PNG")
    return stream.getvalue()


def cpu_engine(*, final_mutator=None, third_failure=False):
    engine = LocalVision(observation_mode="spatial_guarded", image_max_side=1536)
    calls = []

    def generate(system, prompt, images, schema, *, max_tokens):
        calls.append(
            {
                "system": system,
                "prompt": prompt,
                "hashes": [hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in images],
                "tokens": max_tokens,
            }
        )
        index = (len(calls) - 1) % 3
        if index == 2 and third_failure:
            # Failure before this call sets any inference runtime: must not borrow pass two.
            raise ModelOutputError("Synthetic invalid third response")
        engine._last_inference = {"seconds": 0.001, "fixture": True}
        if index < 2:
            return SpatialInventory.model_validate(
                {
                    "objects": [{"part": "washer", "center": [0.4, 0.5] if index == 0 else [0.5, 0.6]}],
                    "uncertain_parts": [],
                    "issues": [],
                    "action": {"kind": "none", "message": "Synthetic engineering fixture"},
                }
            )
        return IdentityResponse.model_validate(
            {
                "objects": [
                    {
                        "id": "p001",
                        "part": "washer",
                        "status": "independent_object",
                        "opening": "through_hole",
                        "issue": "",
                    }
                ]
            }
        )

    engine._generate = generate
    engine.status = lambda: {
        "available": True,
        "loaded": False,
        "label": "CPU engineering fixture, no real inference",
        "observation_mode": "spatial_guarded",
        "last_observation_attempt": copy.deepcopy(getattr(engine, "_observation_attempt", None)),
    }
    original_observe = engine.observe
    if final_mutator:

        def observe(*args, **kwargs):
            value = original_observe(*args, **kwargs)
            final_mutator(value)
            return value

        engine.observe = observe
    return engine, calls


def make_order(client):
    order = client.post(
        "/api/orders",
        json={
            "title": "CPU SYNTHETIC guard test",
            "requirements": {"bolt": 0, "nut": 0, "washer": 1, "bracket": 0},
        },
    ).json()
    if "order" in order:
        order = order["order"]
    uploaded = client.post(
        f"/api/orders/{order['id']}/photos",
        data={"expected_revision": 1},
        files={"photo": ("SYNTHETIC_ENGINEERING.png", fixture_png(), "image/png")},
    )
    assert uploaded.status_code == 201
    return order["id"], uploaded.json()["photo"]


def inspect(client, order_id, photo):
    return client.post(
        f"/api/orders/{order_id}/inspect", json={"photo_id": photo["id"], "expected_revision": 1}
    )


def test_guarded_success_saves_all_three_stages_and_current_photo_binding(tmp_path):
    engine, calls = cpu_engine()
    with TestClient(create_app(data_dir=tmp_path, analyzer=engine)) as client:
        order_id, photo = make_order(client)
        result = inspect(client, order_id, photo)
        assert result.status_code == 200, result.text
        check = result.json()["check"]
        assert check["decision"] == "ready"
        assert len(calls) == 3
        assert [item["tokens"] for item in calls] == [900, 900, 1800]
        assert check["identity_verification"]["source_sha256"] == photo["sha256"]
        assert check["identity_verification"]["full_input_sha256"] == calls[0]["hashes"][0]
        assert check["identity_verification"]["crops"][0]["crop_sha256"] == calls[2]["hashes"][1]
        assert len(check["observation_verification"]["passes"]) == 2
        assert any(step["step"] == "verify_local_identity" for step in check["tool_trace"])


@pytest.mark.parametrize("mutation", ["missing_guard", "wrong_upload_source"])
def test_guarded_api_rejects_missing_required_guard_or_wrong_upload_binding(tmp_path, mutation):
    def mutate(value):
        if mutation == "missing_guard":
            value.pop("identity_verification")
        else:
            value["identity_verification"]["source_sha256"] = "0" * 64
            for crop in value["identity_verification"]["crops"]:
                crop["source_sha256"] = "0" * 64
        # Demonstrates why observation-internal consistency alone is insufficient.
        Observation.model_validate(value)

    engine, _ = cpu_engine(final_mutator=mutate)
    with TestClient(create_app(data_dir=tmp_path, analyzer=engine)) as client:
        order_id, photo = make_order(client)
        result = inspect(client, order_id, photo)
        assert result.status_code == 503
        current = client.get(f"/api/orders/{order_id}").json()
        if "order" in current:
            current = current["order"]
        assert current["latest_check"] is None
        assert current["status"] != "ready"


def test_failed_third_call_never_commits_and_retains_attempt_inputs(tmp_path):
    engine, calls = cpu_engine(third_failure=True)
    with TestClient(create_app(data_dir=tmp_path, analyzer=engine)) as client:
        order_id, photo = make_order(client)
        result = inspect(client, order_id, photo)
        assert result.status_code == 503
        current = client.get(f"/api/orders/{order_id}").json()
        if "order" in current:
            current = current["order"]
        assert current["latest_check"] is None
        assert current["status"] != "ready"
        diagnostics = engine.status()["last_observation_attempt"]
        assert diagnostics["status"] == "failed"
        assert len(diagnostics["passes"]) == 2
        assert len(calls) == 3
        identity = diagnostics["identity"]
        assert identity["full_input_sha256"] == calls[2]["hashes"][0]
        assert identity["crops"][0]["crop_sha256"] == calls[2]["hashes"][1]
        assert identity["source_sha256"] == photo["sha256"]
        assert identity["prompt"] == calls[2]["prompt"]
        assert identity["status"] == "failed"
        assert identity["runtime"] == {}
        saved_event = next(e for e in current["events"] if e["kind"] == "inspection_failed")
        assert saved_event["payload"]["observation_diagnostics"]["identity"] == identity
        assert current.get("active_inspection") is None


@pytest.mark.parametrize("with_context", [False, True])
def test_guarded_queries_do_not_change_with_order_targets(tmp_path, with_context):
    source = tmp_path / "SYNTHETIC_ENGINEERING.png"
    source.write_bytes(fixture_png())
    reference = tmp_path / "SYNTHETIC_REFERENCE.png"
    Image.new("RGB", (64, 64), (20, 140, 20)).save(reference)
    engine, calls = cpu_engine()
    context = {
        "previous_action_kind": "recapture",
        "uncertain_parts": ["nut"],
        "region": [0.1, 0.2, 0.3, 0.4],
    }
    for requirements in (
        {"bolt": 0, "nut": 0, "washer": 1, "bracket": 0},
        {"bolt": 3, "nut": 2, "washer": 0, "bracket": 1},
    ):
        result = (
            engine.observe_with_context(source, requirements, {"nut": reference}, context)
            if with_context
            else engine.observe(source, requirements, {"nut": reference})
        )
        Observation.model_validate(result)
    assert calls[:3] == calls[3:]
    assert "reference for nut; do NOT count it" in calls[0]["prompt"]
    assert calls[0]["hashes"][1] == calls[1]["hashes"][1]
    assert calls[2]["hashes"][1] != calls[0]["hashes"][1]
    assert "reference for nut" not in calls[2]["prompt"]
