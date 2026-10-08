"""Independent CPU review of consensus contracts, not a model accuracy test."""

import hashlib
import json
from copy import deepcopy

import pytest
from conftest import FakeAnalyzer
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from kitguard.app import create_app
from kitguard.consensus import compare_inventories
from kitguard.schemas import Observation
from kitguard.spatial import SpatialInventory
from kitguard.vision import LocalVision, ModelOutputError

COUNTS = {"bolt": 1, "nut": 1, "washer": 0, "bracket": 0}
PAYLOAD = {
    "objects": [{"part": "bolt", "center": [0.2, 0.4]}, {"part": "nut", "center": [0.7, 0.8]}],
    "uncertain_parts": [],
    "issues": [],
    "action": {"kind": "none", "message": "CPU fixture only"},
}


def make_record(second_payload=None):
    first = SpatialInventory.model_validate(deepcopy(PAYLOAD))
    second = SpatialInventory.model_validate(deepcopy(second_payload or PAYLOAD))
    result, observations, agree, clear = compare_inventories(first, second, "CPU test observer")
    result["verification"] = {
        "mode": "spatial_consensus",
        "same_model_correlated_calls": True,
        "counts_agree": agree,
        "clear_agreement": clear,
        "passes": [
            {
                "transform": transform,
                "input_sha256": digit * 64,
                "observed": observation["observed"],
                "issues": observation["issues"],
                "action": observation["action"],
                "objects": [obj.model_dump() for obj in inventory.objects],
                "uncertain_parts": [p for p, n in observation["observed"].items() if n is None],
            }
            for transform, digit, observation, inventory in zip(
                ["original", "rotate_90_ccw"],
                ["a", "b"],
                observations,
                [first, second],
                strict=True,
            )
        ],
    }
    return result


def forged_clear_record():
    second = {
        **deepcopy(PAYLOAD),
        "objects": [*deepcopy(PAYLOAD["objects"]), deepcopy(PAYLOAD["objects"][0])],
    }
    record = make_record(second)
    record["observed"] = dict(COUNTS)
    record["issues"] = []
    record["action"] = {"kind": "none", "message": "Forged clear CPU fixture", "region": None}
    record["object_evidence"]["uncertain_parts"] = []
    record["verification"].update(counts_agree=True, clear_agreement=True)
    return record


def test_schema_rejects_clear_result_with_disagreeing_consensus_passes():
    with pytest.raises(ValidationError):
        Observation.model_validate(forged_clear_record())


@pytest.mark.parametrize(
    "mutation", ["count_list", "uncertain_count", "duplicate_transform", "swap_transform"]
)
def test_schema_rejects_internally_inconsistent_pass_records(mutation):
    record = make_record()
    first, second = record["verification"]["passes"]
    if mutation == "count_list":
        second["objects"] = []
    elif mutation == "uncertain_count":
        second["uncertain_parts"] = ["bolt"]
    elif mutation == "duplicate_transform":
        second["transform"] = "original"
    else:
        first["transform"], second["transform"] = second["transform"], first["transform"]
    with pytest.raises(ValidationError):
        Observation.model_validate(record)


def test_schema_does_not_let_top_level_clear_hide_a_global_pass_obstacle():
    record = make_record({**deepcopy(PAYLOAD), "issues": ["CPU global blur"]})
    record["observed"] = dict(COUNTS)
    record["issues"] = []
    record["action"] = {"kind": "none", "message": "Forged clear", "region": None}
    record["object_evidence"]["uncertain_parts"] = []
    record["verification"].update(counts_agree=True, clear_agreement=True)
    with pytest.raises(ValidationError):
        Observation.model_validate(record)


def test_inconsistent_adapter_consensus_cannot_create_ready_api_result(client, order, upload, analyzer):
    # Server validation must independently reject a contradictory adapter record.
    analyzer.result = forged_clear_record()
    photo = upload(order).json()["photo"]
    response = client.post(
        f"/api/orders/{order['id']}/inspect",
        json={"photo_id": photo["id"], "expected_revision": 1},
    )
    assert response.status_code == 503
    saved = client.get(f"/api/orders/{order['id']}").json()["order"]
    assert saved["checks"] == [] and saved["latest_check"] is None
    assert saved["status"] == "needs_action" and saved["completions"] == []


def test_consensus_both_prompts_and_reference_pixels_are_target_blind_with_context(tmp_path, monkeypatch):
    target = tmp_path / "target.png"
    reference = tmp_path / "reference.png"
    image = Image.new("RGB", (80, 48), "black")
    image.paste("white", (0, 0, 20, 10))
    image.save(target)
    Image.new("RGB", (42, 32), "red").save(reference)
    engine = LocalVision(observation_mode="spatial_consensus")
    calls = []

    def generate(system, prompt, images, schema, *, max_tokens):
        pixels = []
        for path in images:
            with Image.open(path) as item:
                pixels.append(item.copy())
        calls.append({"system": system, "prompt": prompt, "pixels": pixels, "tokens": max_tokens})
        engine._last_inference = {"seconds": 0.1}
        return SpatialInventory.model_validate(deepcopy(PAYLOAD))

    monkeypatch.setattr(engine, "_generate", generate)
    context = {
        "previous_action_kind": "recapture",
        "uncertain_parts": ["nut"],
        "region": [0.1, 0.2, 0.3, 0.4],
    }
    for counts in (COUNTS, {"bolt": 3, "nut": 0, "washer": 3, "bracket": 1}):
        Observation.model_validate(engine.observe_with_context(target, counts, {"nut": reference}, context))
    assert len(calls) == 4
    assert len({(c["system"], c["prompt"]) for c in calls}) == 1
    assert all(c["tokens"] == 900 and len(c["pixels"]) == 2 for c in calls)
    assert (
        calls[0]["pixels"][0].transpose(Image.Transpose.ROTATE_90).tobytes()
        == calls[1]["pixels"][0].tobytes()
    )
    assert all(c["pixels"][1].tobytes() == calls[0]["pixels"][1].tobytes() for c in calls)
    assert "reference for nut; do NOT count it" in calls[0]["prompt"]
    assert 'Previously uncertain categories: ["nut"]' in calls[0]["prompt"]
    assert "region" not in calls[0]["prompt"] and "0.1" not in calls[0]["prompt"]
    assert json.dumps(COUNTS) not in calls[0]["prompt"]


@pytest.mark.parametrize("error_type", [ModelOutputError, RuntimeError])
def test_second_pass_failure_keeps_current_first_pass_trace_but_no_api_success(
    tmp_path, image_bytes, monkeypatch, error_type
):
    engine = LocalVision(observation_mode="spatial_consensus")
    calls = []

    def generate(*args, **kwargs):
        calls.append(None)
        if len(calls) == 2:
            raise error_type("CPU only second-pass failure")
        engine._last_inference = {"seconds": 0.1}
        return SpatialInventory.model_validate(deepcopy(PAYLOAD))

    monkeypatch.setattr(engine, "_generate", generate)
    with TestClient(
        create_app(data_dir=tmp_path / "data", analyzer=engine), raise_server_exceptions=False
    ) as client:
        order = client.post(
            "/api/orders", json={"title": "CPU consensus failure", "requirements": COUNTS}
        ).json()["order"]
        photo = client.post(
            f"/api/orders/{order['id']}/photos",
            data={"expected_revision": 1},
            files={"photo": ("synthetic.png", image_bytes(), "image/png")},
        ).json()["photo"]
        response = client.post(
            f"/api/orders/{order['id']}/inspect",
            json={"photo_id": photo["id"], "expected_revision": 1},
        )
        assert response.status_code == 503
        saved = client.get(f"/api/orders/{order['id']}").json()["order"]
        assert saved["checks"] == [] and saved["latest_check"] is None
        assert saved["status"] == "needs_action" and saved["completions"] == []
        event = next(e for e in saved["events"] if e["kind"] == "inspection_failed")
        diagnostics = event["payload"]["observation_diagnostics"]
        assert diagnostics["source_sha256"] == photo["sha256"]
        assert diagnostics["status"] == "failed" and diagnostics["error_type"] == error_type.__name__
        assert len(diagnostics["passes"]) == 1
        assert diagnostics["passes"][0]["transform"] == "original"
        assert diagnostics["passes"][0]["inventory"] == PAYLOAD


def test_benchmark_preobservation_failure_never_reuses_previous_case_diagnostics(
    tmp_path, image_bytes, monkeypatch
):
    import scripts.run_benchmark as runner

    dataset = tmp_path / "images"
    dataset.mkdir()
    cases = []
    for i in range(2):
        path = dataset / f"synthetic-{i}.png"
        path.write_bytes(image_bytes(i))
        cases.append(
            {
                "id": f"cpu-{i}",
                "source_id": f"cpu-source-{i}",
                "image": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "split": "development",
                "ground_truth": COUNTS,
            }
        )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": 1, "cases": cases}))
    output = tmp_path / "run"

    class Observer:
        def __init__(self, *args, **kwargs):
            self.attempt = None

        def status(self):
            return {
                "available": True,
                "last_observation_attempt": self.attempt,
                "last_inference": {"seconds": 0.1},
            }

        def observe(self, path, *args):
            self.attempt = {
                "status": "completed",
                "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "passes": [{"marker": "only-first-case"}],
            }
            return FakeAnalyzer.observation(COUNTS)

    def upload(path):
        if path.name == "synthetic-1.png":
            raise ValueError("CPU upload failure before observer")
        return path.read_bytes()

    monkeypatch.setattr(runner, "LocalVision", Observer)
    monkeypatch.setattr(runner, "app_upload_bytes", upload)
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_benchmark.py",
            "--manifest",
            str(manifest),
            "--dataset-root",
            str(dataset),
            "--output",
            str(output),
            "--split",
            "development",
            "--input-pipeline",
            "app-upload",
            "--observation-mode",
            "spatial_consensus",
        ],
    )
    runner.main()
    rows = [json.loads(line) for line in (output / "predictions.jsonl").read_text().splitlines()]
    assert rows[0]["observation_diagnostics"]["passes"] == [{"marker": "only-first-case"}]
    assert "CPU upload failure before observer" in rows[1]["error"]
    assert rows[1]["error_diagnostics"] is None
    assert rows[1]["observation_diagnostics"] is None
    run = json.loads((output / "run.json").read_text())
    assert run["summary"]["errors"]["numerator"] == 1
    assert run["summary"]["images"] == 2
