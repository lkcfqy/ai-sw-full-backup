"""Correlated-pass guard contracts; synthetic fixtures do not measure accuracy."""

from copy import deepcopy

import pytest
from PIL import Image

from kitguard.consensus import compare_inventories
from kitguard.schemas import Observation
from kitguard.spatial import SpatialInventory
from kitguard.vision import LocalVision, ModelOutputError

COUNTS = {"bolt": 1, "nut": 1, "washer": 0, "bracket": 0}
PAYLOAD = {
    "objects": [{"part": "bolt", "center": [0.2, 0.4]}, {"part": "nut", "center": [0.7, 0.8]}],
    "uncertain_parts": [], "issues": [], "action": {"kind": "none", "message": "CPU fixture"},
}


def inventory(changes=None):
    return SpatialInventory.model_validate({**deepcopy(PAYLOAD), **(changes or {})})


def test_disagreement_abstains_without_changing_other_counts_or_deduplicating():
    second = inventory({"objects": [*PAYLOAD["objects"], PAYLOAD["objects"][0]]})
    result, _, agree, clear = compare_inventories(inventory(), second, "CPU")
    assert result["observed"] == {**COUNTS, "bolt": None}
    assert not agree and not clear
    assert result["object_evidence"]["objects"] == PAYLOAD["objects"]
    assert result["object_evidence"]["uncertain_parts"] == ["bolt"]
    assert result["action"]["kind"] == "recapture"
    assert "头部与杆部" in result["action"]["message"]
    # Rotated center .2,.4 maps back to .6,.2; both views bound the guide.
    assert result["action"]["region"] == pytest.approx([.12, .12, .68, .48])
    Observation.model_validate(result)


@pytest.mark.parametrize("changed", [{"issues": ["global blur"]}, {"uncertain_parts": ["nut"]}])
def test_known_matching_list_never_erases_uncertainty(changed):
    result, _, _, clear = compare_inventories(inventory(), inventory(changed), "CPU")
    assert not clear and result["observed"]["nut"] is None
    assert result["action"]["kind"] == "recapture"
    if "issues" in changed:
        assert all(v is None for v in result["observed"].values())
        assert result["action"]["region"] is None


def test_adapter_blinds_both_passes_rotates_pixels_and_saves_both_lists(tmp_path, monkeypatch):
    photo = tmp_path / "cpu.png"
    im = Image.new("RGB", (80, 48), "black")
    im.paste("white", (0, 0, 20, 10))
    im.save(photo)
    engine = LocalVision(observation_mode="spatial_consensus")
    calls = []

    def generate(system, prompt, images, schema, *, max_tokens):
        with Image.open(images[0]) as supplied:
            size = supplied.size
        calls.append((system, prompt, size, max_tokens))
        engine._last_inference = {"seconds": .1}
        return inventory()

    monkeypatch.setattr(engine, "_generate", generate)
    first = Observation.model_validate(engine.observe(photo, COUNTS, {}))
    second = engine.observe(photo, {"bolt": 3, "nut": 0, "washer": 3, "bracket": 1}, {})
    assert calls[:2] == calls[2:]
    assert calls[0][:2] == calls[1][:2]  # Neither first list nor BOM enters second prompt.
    assert [c[2] for c in calls[:2]] == [(80, 48), (48, 80)]
    assert all(c[3] == 900 for c in calls)
    assert first.observed.model_dump() == second["observed"] == COUNTS
    assert first.verification.mode == "spatial_consensus"
    assert first.verification.same_model_correlated_calls
    assert first.verification.clear_agreement
    passes = first.verification.passes
    assert passes[0].input_sha256 != passes[1].input_sha256
    assert len(passes[1].objects) == 2
    assert len(engine.status()["last_observation_attempt"]["passes"]) == 2


def test_second_failure_has_no_first_pass_fallback(tmp_path, monkeypatch):
    path = tmp_path / "cpu.png"
    Image.new("RGB", (80, 48), "gray").save(path)
    engine = LocalVision(observation_mode="spatial_consensus")
    calls = []

    def generate(*args, **kwargs):
        calls.append(None)
        if len(calls) == 2:
            raise ModelOutputError("CPU second pass failure")
        return inventory()

    monkeypatch.setattr(engine, "_generate", generate)
    with pytest.raises(ModelOutputError) as exc:
        engine.observe(path, COUNTS, {})
    assert exc.value.observation_diagnostics["status"] == "failed"
    assert len(exc.value.observation_diagnostics["passes"]) == 1


def test_reference_capture_rejects_old_revision_atomically(client, image_bytes):
    order = client.post("/api/orders", json={"title": "CPU capture", "requirements": COUNTS}).json()["order"]
    changed = client.post(f"/api/orders/{order['id']}/revise", json={
        "requirements": {**COUNTS, "bolt": 2}, "instruction": "CPU", "expected_revision": 1,
    })
    assert changed.status_code == 200
    stale = client.post(f"/api/orders/{order['id']}/references/bolt", data={"expected_revision": 1},
                        files={"photo": ("cpu.png", image_bytes(), "image/png")})
    assert stale.status_code == 409
    assert client.get(f"/api/orders/{order['id']}").json()["order"]["references"] == {}
    valid = client.post(f"/api/orders/{order['id']}/references/bolt", data={"expected_revision": 2},
                        files={"photo": ("cpu.png", image_bytes(), "image/png")})
    assert valid.status_code == 201
    assert valid.json()["photo"]["revision"] == 2
