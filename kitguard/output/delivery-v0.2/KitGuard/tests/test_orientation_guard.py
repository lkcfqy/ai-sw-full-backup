"""CPU fixtures verify guard behavior, not photographic recognition accuracy."""

from copy import deepcopy

import pytest
from PIL import Image

from kitguard.schemas import Observation
from kitguard.vision import LocalVision, ModelOutputError, _Observation

COUNTS = {"bolt": 2, "nut": 2, "washer": 2, "bracket": 0}
CLEAR = {
    "observed": COUNTS,
    "issues": [],
    "action": {"kind": "none", "message": "test fixture", "region": None},
}


def adapter(tmp_path, monkeypatch, outputs):
    photo = tmp_path / "fixture.png"
    image = Image.new("RGB", (80, 48), "black")
    image.paste("white", (0, 0, 20, 10))
    image.save(photo)
    vision = LocalVision(observation_mode="dual_orientation")
    calls = []

    def generate(system, prompt, images, schema):
        with Image.open(images[0]) as supplied:
            calls.append({"prompt": prompt, "size": supplied.size})
        output = outputs[len(calls) - 1]
        if isinstance(output, Exception):
            raise output
        vision._last_inference = {"seconds": 0.1}
        return _Observation.model_validate(output)

    monkeypatch.setattr(vision, "_generate", generate)
    return vision, photo, calls


def test_agreement_retains_two_actual_observations_and_separate_inputs(tmp_path, monkeypatch):
    vision, photo, calls = adapter(tmp_path, monkeypatch, [CLEAR, CLEAR])
    result = Observation.model_validate(vision.observe(photo, {**COUNTS, "bolt": 3}, {}))
    assert result.observed.model_dump() == COUNTS
    assert result.verification.clear_agreement
    assert [c["size"] for c in calls] == [(80, 48), (48, 80)]
    passes = result.verification.passes
    assert passes[0].input_sha256 != passes[1].input_sha256
    assert all('"bolt":' not in c["prompt"] for c in calls)
    assert len(vision.status()["last_inference"]["passes"]) == 2


@pytest.mark.parametrize("second_count", [3, None])
def test_disagreement_or_unknown_cannot_become_ready(tmp_path, monkeypatch, second_count):
    second = deepcopy(CLEAR)
    second["observed"]["nut"] = second_count
    if second_count is None:
        second["action"]["kind"] = "recapture"
    vision, photo, _ = adapter(tmp_path, monkeypatch, [CLEAR, second])
    result = vision.observe(photo, COUNTS, {})
    assert result["observed"]["nut"] is None
    assert result["action"]["kind"] == "recapture"
    assert not result["verification"]["clear_agreement"]


@pytest.mark.parametrize("kind", ["separate", "recapture", "manual"])
def test_matching_counts_do_not_erase_observation_obstacles(tmp_path, monkeypatch, kind):
    second = deepcopy(CLEAR)
    second["action"]["kind"] = kind
    vision, photo, _ = adapter(tmp_path, monkeypatch, [CLEAR, second])
    result = vision.observe(photo, COUNTS, {})
    assert result["verification"]["counts_agree"]
    assert not result["verification"]["clear_agreement"]
    assert result["issues"]
    assert result["action"]["kind"] == ("manual" if kind == "manual" else "recapture")


def test_failed_second_observation_does_not_fall_back_to_first(tmp_path, monkeypatch):
    vision, photo, _ = adapter(tmp_path, monkeypatch, [CLEAR, ModelOutputError("fixture failure")])
    with pytest.raises(ModelOutputError) as caught:
        vision.observe(photo, COUNTS, {})
    diagnostic = caught.value.observation_diagnostics
    assert diagnostic["status"] == "failed"
    assert len(diagnostic["passes"]) == 1
    assert diagnostic["passes"][0]["observation"] == CLEAR


def test_rotated_context_omits_old_region_and_previous_counts(tmp_path, monkeypatch):
    vision, photo, calls = adapter(tmp_path, monkeypatch, [CLEAR, CLEAR])
    context = {
        "previous_action_kind": "recapture",
        "uncertain_parts": ["nut"],
        "region": [0.2, 0.3, 0.8, 0.9],
    }
    vision.observe_with_context(photo, COUNTS, {}, context)
    assert '"region"' in calls[0]["prompt"]
    assert "region" not in calls[1]["prompt"]
    assert "nut" in calls[1]["prompt"]


def test_failed_pass_diagnostics_are_saved_without_creating_a_valid_check(client, analyzer, image_bytes):
    order = client.post(
        "/api/orders", json={"title": "CPU failure trace fixture", "requirements": COUNTS}
    ).json()["order"]
    photo = client.post(
        f"/api/orders/{order['id']}/photos",
        data={"expected_revision": 1},
        files={"photo": ("fixture.png", image_bytes(), "image/png")},
    ).json()["photo"]
    error = ModelOutputError("Second pass fixture failure")
    error.observation_diagnostics = {
        "status": "failed",
        "mode": "dual_orientation",
        "passes": [{"transform": "original", "observation": CLEAR}],
    }
    analyzer.error = error
    response = client.post(
        f"/api/orders/{order['id']}/inspect", json={"photo_id": photo["id"], "expected_revision": 1}
    )
    assert response.status_code == 503
    saved = client.get(f"/api/orders/{order['id']}").json()["order"]
    assert saved["latest_check"] is None
    assert saved["status"] != "ready"
    event = [e for e in saved["events"] if e["kind"] == "inspection_failed"][-1]
    assert event["payload"]["observation_diagnostics"] == error.observation_diagnostics
