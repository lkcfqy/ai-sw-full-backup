"""CPU-only experimental-contract checks; none are model accuracy evidence."""

import copy
import json
import threading
from types import SimpleNamespace

import pytest
from PIL import Image

from kitguard.schemas import Observation
from scripts.probe_selective_identity import MODE, SelectiveIdentityVision


def inventory(parts=("bolt", "nut", "washer"), unclear=False):
    return {"objects": [{"part": p, "center": [.2 + i * .2, .5]} for i, p in enumerate(parts)],
            "uncertain_parts": ["nut"] if unclear else [],
            "issues": ["unclear"] if unclear else [],
            "action": {"kind": "recapture" if unclear else "none", "message": "fixture"}}


def identity():
    return {"objects": [
        {"id": "p002", "part": "nut", "status": "independent_object", "opening": "through_hole", "issue": ""},
        {"id": "p003", "part": "washer", "status": "independent_object", "opening": "through_hole", "issue": ""},
    ]}


def observer(tmp_path, outputs):
    image = tmp_path / "source.png"
    Image.new("RGB", (256, 192), "white").save(image)
    vision = SelectiveIdentityVision()
    vision.artifact_dir = tmp_path / "case"
    threads, messages = [], []
    returned = iter(outputs)

    def generate(*args, **kwargs):
        threads.append(threading.current_thread().name)
        value = next(returned)
        text = value if isinstance(value, str) else json.dumps(value)
        return SimpleNamespace(text=text, prompt_tokens=10, generation_tokens=10,
                               peak_memory=0.0, finish_reason="stop")

    def template(_processor, _config, prompt, **kwargs):
        messages.append(prompt)
        return "formatted"

    runtime = {"processor": object(), "model": object(), "config": {},
               "generate": generate, "template": template, "grammar": lambda *args: object()}
    vision._load = lambda: runtime
    return vision, image, threads, messages


def run(vision, image):
    return vision.observe(image, {"bolt": 3, "nut": 2, "washer": 1, "bracket": 0}, {})


def test_single_pass_identity_uses_real_worker_and_independent_status(tmp_path):
    vision, image, threads, messages = observer(tmp_path, [inventory(), identity()])
    result = run(vision, image)
    Observation.model_validate(result)
    assert result["observed"] == {"bolt": 1, "nut": 1, "washer": 1, "bracket": 0}
    assert "verification" not in result and "identity_verification" not in result
    assert len(threads) == 2 and all(t.startswith("kitguard-mlx") for t in threads)
    status = vision.status()
    assert status["observation_mode"] == MODE and status["production_selected"] is False
    attempt = status["last_observation_attempt"]
    assert len(attempt["passes"]) == 1 and attempt["passes"][0]["transform"] == "original"
    assert attempt["experimental_identity"]["status"] == "confirmed_candidates"
    assert len(attempt["generation_calls"]) == 2
    assert (vision.artifact_dir / "call-02/generation.json").is_file()
    assert '"requirements"' not in json.dumps(messages)


@pytest.mark.parametrize("base,status", [
    (inventory(("bolt",)), "skipped_no_candidates"),
    (inventory(unclear=True), "skipped_base_unclear"),
])
def test_only_clear_candidate_lists_get_identity_call(tmp_path, base, status):
    vision, image, threads, _ = observer(tmp_path, [base])
    result = run(vision, image)
    Observation.model_validate(result)
    assert len(threads) == 1
    assert vision.status()["last_observation_attempt"]["experimental_identity"]["status"] == status


def test_reclassification_never_repairs_counts(tmp_path):
    response = identity()
    response["objects"][1].update(part="bolt", opening="closed_recess")
    vision, image, _, _ = observer(tmp_path, [inventory(), response])
    result = run(vision, image)
    Observation.model_validate(result)
    assert result["observed"] == {"bolt": None, "nut": 1, "washer": None, "bracket": 0}
    assert result["action"]["kind"] == "recapture"
    assert result["object_evidence"]["objects"][2]["part"] == "washer"


@pytest.mark.parametrize("kind", ["missing", "wrong_id", "duplicate", "bad_json"])
def test_invalid_identity_is_fail_closed_and_raw_output_survives(tmp_path, kind):
    response = identity()
    if kind == "missing":
        response["objects"].pop()
    elif kind == "wrong_id":
        response["objects"][1]["id"] = "p019"
    elif kind == "duplicate":
        response["objects"][1]["id"] = "p002"
    else:
        response = '{"objects": invalid'
    vision, image, threads, _ = observer(tmp_path, [inventory(), response])
    with pytest.raises(Exception) as caught:
        run(vision, image)
    assert len(threads) == 2
    attempt = caught.value.observation_diagnostics
    assert attempt["status"] == "failed"
    assert attempt["experimental_identity"]["status"] == "failed"
    saved = json.loads((vision.artifact_dir / "call-02/generation.json").read_text())
    assert saved["raw_text"] == (response if isinstance(response, str) else json.dumps(response))
    assert attempt["single_direction_base"]["observed"]["washer"] == 1


def test_malformed_first_pass_preserves_raw_text(tmp_path):
    vision, image, threads, _ = observer(tmp_path, ['{"objects": not-json'])
    with pytest.raises(Exception) as caught:
        run(vision, image)
    assert len(threads) == 1
    assert caught.value.observation_diagnostics["status"] == "failed"
    saved = json.loads((vision.artifact_dir / "call-01/generation.json").read_text())
    assert saved["raw_text"] == '{"objects": not-json' and saved["status"] == "failed"


def test_other_uncertainty_is_not_cleared_by_identity(tmp_path):
    base = copy.deepcopy(inventory())
    base.update(uncertain_parts=["bolt"], issues=["part hidden"])
    base["action"]["kind"] = "recapture"
    vision, image, threads, _ = observer(tmp_path, [base])
    result = run(vision, image)
    assert result["observed"]["bolt"] is None and len(threads) == 1
