"""CPU safety contracts for list-derived counts, not image-recognition measurements."""

from copy import deepcopy

import pytest
from PIL import Image
from pydantic import ValidationError

from kitguard.schemas import Observation
from kitguard.spatial import SpatialInventory, count_inventory
from kitguard.vision import LocalVision

PAYLOAD = {
    "objects": [
        {"part": "bolt", "center": [0.2, 0.4]},
        {"part": "nut", "center": [0.5, 0.7]},
        {"part": "nut", "center": [0.7, 0.4]},
    ],
    "uncertain_parts": [],
    "issues": [],
    "action": {"kind": "none", "message": "CPU fixture"},
}


def test_counts_come_from_every_list_entry_without_clamping_or_inventing_absent_parts():
    payload = deepcopy(PAYLOAD)
    payload["objects"].extend({"part": "nut", "center": [0.1 * n, 0.2]} for n in (1, 2))
    result, evidence = count_inventory(SpatialInventory.model_validate(payload), "TEST FIXTURE")
    assert result["observed"] == {"bolt": 1, "nut": 4, "washer": 0, "bracket": 0}
    assert evidence["listed_counts"]["nut"] == 4


def test_explicit_uncertainty_cannot_be_replaced_by_partial_list_count():
    payload = deepcopy(PAYLOAD)
    payload["uncertain_parts"] = ["nut"]
    result, evidence = count_inventory(SpatialInventory.model_validate(payload), "TEST FIXTURE")
    assert result["observed"]["nut"] is None
    assert result["observed"]["bolt"] == 1
    assert result["action"]["kind"] == "recapture"
    assert evidence["listed_counts"]["nut"] == 2


@pytest.mark.parametrize(
    "changed",
    [{"issues": ["Unlocalized issue"]}, {"action": {"kind": "recapture", "message": "Cannot complete list"}}],
)
def test_unlocalized_obstacle_makes_all_counts_unknown(changed):
    result, _ = count_inventory(SpatialInventory.model_validate({**PAYLOAD, **changed}), "TEST FIXTURE")
    assert all(value is None for value in result["observed"].values())
    assert result["action"]["kind"] == "recapture"


@pytest.mark.parametrize(
    "point", [[float("nan"), 0.2], [0.1, float("inf")], [-0.01, 0.5], [0.5, 1.01], [0.5], [0.5, 0.5, 0.5]]
)
def test_invalid_coordinates_reject_the_whole_response(point):
    payload = deepcopy(PAYLOAD)
    payload["objects"][0]["center"] = point
    with pytest.raises(ValidationError):
        SpatialInventory.model_validate(payload)


@pytest.mark.parametrize("extra", [{"counts": {"nut": 99}}, {"required": 2}, {"ready": True}])
def test_model_cannot_supply_totals_targets_or_readiness(extra):
    with pytest.raises(ValidationError):
        SpatialInventory.model_validate({**PAYLOAD, **extra})


def test_object_budget_overflow_is_not_truncated_to_an_acceptable_count():
    payload = deepcopy(PAYLOAD)
    payload["objects"] *= 7
    with pytest.raises(ValidationError):
        SpatialInventory.model_validate(payload)


def test_duplicate_uncertainty_entries_are_rejected():
    with pytest.raises(ValidationError):
        SpatialInventory.model_validate({**PAYLOAD, "uncertain_parts": ["nut", "nut"]})


def test_live_adapter_spatial_prompt_is_independent_of_target_and_retains_points(tmp_path, monkeypatch):
    path = tmp_path / "cpu.png"
    Image.new("RGB", (100, 80), "gray").save(path)
    engine = LocalVision(observation_mode="spatial_inventory", image_max_side=1536)
    prompts = []

    def generate(system, prompt, images, schema, *, max_tokens):
        prompts.append((system, prompt, len(images), max_tokens))
        return SpatialInventory.model_validate(PAYLOAD)

    monkeypatch.setattr(engine, "_generate", generate)
    first = engine.observe(path, {"bolt": 1, "nut": 2, "washer": 0, "bracket": 0}, {})
    second = engine.observe(path, {"bolt": 3, "nut": 0, "washer": 3, "bracket": 2}, {})
    assert prompts[0] == prompts[1]
    assert prompts[0][3] == 900
    assert first["observed"] == second["observed"] == {"bolt": 1, "nut": 2, "washer": 0, "bracket": 0}
    assert first["object_evidence"]["objects"] == PAYLOAD["objects"]
    Observation.model_validate(first)
    context = {"previous_action_kind": "recapture", "uncertain_parts": ["washer"], "region": None}
    engine.observe_with_context(path, {"bolt": 1, "nut": 2, "washer": 0, "bracket": 0}, {}, context)
    engine.observe_with_context(path, {"bolt": 3, "nut": 0, "washer": 3, "bracket": 2}, {}, context)
    assert prompts[2] == prompts[3]


def test_saved_object_evidence_cannot_contradict_observed_counts():
    result, _ = count_inventory(SpatialInventory.model_validate(PAYLOAD), "TEST FIXTURE")
    result["object_evidence"] = {
        "protocol": "spatial_inventory_v1",
        "coordinate_frame": "normalized_original",
        "objects": PAYLOAD["objects"],
        "uncertain_parts": [],
    }
    result["observed"]["nut"] = 1
    with pytest.raises(ValidationError):
        Observation.model_validate(result)


def test_object_list_and_actual_count_step_persist_through_api(client, analyzer, image_bytes):
    requirements = {"bolt": 1, "nut": 2, "washer": 0, "bracket": 0}
    order = client.post(
        "/api/orders", json={"title": "Spatial CPU fixture", "requirements": requirements}
    ).json()["order"]
    photo = client.post(
        f"/api/orders/{order['id']}/photos",
        data={"expected_revision": 1},
        files={"photo": ("fixture.png", image_bytes(), "image/png")},
    ).json()["photo"]
    result, _ = count_inventory(SpatialInventory.model_validate(PAYLOAD), "TEST FIXTURE")
    result["backend"] = "test"
    result["object_evidence"] = {
        "protocol": "spatial_inventory_v1",
        "coordinate_frame": "normalized_original",
        "objects": PAYLOAD["objects"],
        "uncertain_parts": [],
    }
    analyzer.result = result
    response = client.post(
        f"/api/orders/{order['id']}/inspect", json={"photo_id": photo["id"], "expected_revision": 1}
    )
    assert response.status_code == 200
    check = response.json()["check"]
    assert check["object_evidence"] == result["object_evidence"]
    step = next(step for step in check["tool_trace"] if step["step"] == "derive_counts_from_object_list")
    assert step["listed_objects"] == 3
    saved = client.get(f"/api/orders/{order['id']}").json()["order"]
    assert saved["latest_check"]["object_evidence"] == result["object_evidence"]
