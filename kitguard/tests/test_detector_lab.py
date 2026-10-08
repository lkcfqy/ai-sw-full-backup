"""Isolated lab API fixtures. No trained model is loaded or executed."""

import hashlib
import io
import json
import subprocess
import threading
import time
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from kitguard.detector_lab import MAX_UPLOAD, _CpuPredictor, _DetectorLab, create_detector_lab_router


def photo_bytes(*, size=(64, 48), format="PNG", exif=None):
    stream = io.BytesIO()
    image = Image.new("RGB", size, (120, 80, 30))
    image.save(stream, format=format, **({"exif": exif} if exif else {}))
    return stream.getvalue()


class Predictor:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.release.set()
        self.finished = threading.Event()
        self.calls = []
        self.error = None
        self.mutate = None

    def __call__(self, checkpoint, image):
        self.calls.append((checkpoint, image))
        self.started.set()
        try:
            if not self.release.wait(5):
                raise RuntimeError("Test predictor timed out")
            if self.error:
                raise self.error
            with Image.open(image) as decoded:
                size = list(decoded.size)
            result = {"checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
                      "source_sha256": hashlib.sha256(image.read_bytes()).hexdigest(), "image_size": size,
                      "device": "cpu", "inference_seconds": 0.125, "threshold": 0.5,
                      "predictions": [{"label": 1, "bbox_xyxy": [1, 2, 20, 22], "score": 0.8},
                                      {"label": 2, "bbox_xyxy": [22, 4, 40, 20], "score": 0.5},
                                      {"label": 1, "bbox_xyxy": [25, 5, 45, 30], "score": 0.49}],
                      "counts": {"bolt": 999, "washer": 0}, "decision": "ready"}
            if self.mutate:
                self.mutate(result)
            return result
        finally:
            self.finished.set()


@contextmanager
def lab_client(tmp_path, predictor=None, *, checkpoint=True):
    checkpoint_path = tmp_path / "fixture.pt"
    if checkpoint and not checkpoint_path.exists():
        checkpoint_path.write_bytes(b"synthetic checkpoint, never torch.load")
    app = FastAPI()
    app.include_router(create_detector_lab_router(
        tmp_path / "lab", checkpoint_path if checkpoint else None, predictor=predictor))
    with TestClient(app) as client:
        try:
            yield client
        finally:
            if predictor is not None:
                predictor.release.set()
                if predictor.calls:
                    predictor.finished.wait(5)
                    # The predictor's return precedes the final durable job write.
                    deadline = time.monotonic() + 5
                    while client.get("/api/detector-lab/status").json()["busy"]:
                        if time.monotonic() > deadline:
                            pytest.fail("Lab worker did not drain")
                        time.sleep(0.005)


def submit(client, raw=None, **kwargs):
    return client.post("/api/detector-lab/jobs",
                       files={"photo": ("fixture.png", raw if raw is not None else photo_bytes(), "image/png")},
                       **kwargs)


def completed(client, identifier):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        result = client.get(f"/api/detector-lab/jobs/{identifier}")
        assert result.status_code == 200
        job = result.json()["job"]
        if job["status"] not in {"queued", "running"}:
            return job
        time.sleep(0.005)
    pytest.fail("Lab job did not finish")


def test_disabled_lab_does_not_start_subprocess(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("Disabled lab started predictor"))
    with lab_client(tmp_path, checkpoint=False) as client:
        status = client.get("/api/detector-lab/status").json()
        assert not status["enabled"] and not status["available"]
        assert submit(client).status_code == 503
    assert not list((tmp_path / "lab").glob("*/job.json"))


def test_completed_job_recomputes_counts_preserves_unknown_and_has_no_decision(tmp_path):
    predictor = Predictor()
    raw = photo_bytes()
    with lab_client(tmp_path, predictor) as client:
        response = submit(client, raw)
        assert response.status_code == 202
        initial = response.json()["job"]
        assert initial["status"] == "queued" and initial["error"] is None
        job = completed(client, initial["id"])
        assert job["status"] == "completed"
        assert job["result"]["counts"] == {"bolt": 1, "nut": 1, "washer": None, "bracket": None}
        assert job["decision"] is None and job["result"]["decision"] is None
        assert job["result"]["threshold"] == 0.5
        assert len(job["result"]["predictions"]) == 3
        assert job["model"]["backend"] == "injected_predictor"
        assert job["image"]["source_sha256"] == hashlib.sha256(raw).hexdigest()
        response = client.get(job["image"]["url"])
        assert hashlib.sha256(response.content).hexdigest() == job["image"]["sha256"]
        assert response.headers["content-type"] == "image/png"
        stored = tmp_path / "lab" / job["id"]
        assert json.loads((stored / "job.json").read_text()) == job
        assert (stored / "model-result.json").is_file()
    assert len(predictor.calls) == 1


def test_exif_orientation_is_applied_and_private_metadata_removed(tmp_path):
    exif = Image.Exif()
    exif[274] = 6
    exif[270] = "PRIVATE TEST DESCRIPTION"
    raw = photo_bytes(format="JPEG", exif=exif)
    with lab_client(tmp_path, Predictor()) as client:
        job = completed(client, submit(client, raw).json()["job"]["id"])
        assert (job["image"]["width"], job["image"]["height"]) == (48, 64)
        with Image.open(io.BytesIO(client.get(job["image"]["url"]).content)) as image:
            assert image.mode == "RGB" and not image.getexif() and "exif" not in image.info


def test_busy_job_rejected_without_parallel_predictor_or_extra_record(tmp_path):
    predictor = Predictor()
    predictor.release.clear()
    with lab_client(tmp_path, predictor) as client:
        first = submit(client).json()["job"]
        assert predictor.started.wait(2)
        assert client.get("/api/detector-lab/status").json()["busy"]
        assert submit(client).status_code == 503
        assert len(list((tmp_path / "lab").glob("*/job.json"))) == 1
        predictor.release.set()
        assert completed(client, first["id"])["status"] == "completed"


@pytest.mark.parametrize("raw,code", [(b"not an image", 422), (photo_bytes(size=(16, 40)), 422),
                                     (photo_bytes(format="GIF"), 422), (b"x" * (MAX_UPLOAD + 1), 413)])
def test_invalid_upload_never_reaches_predictor(tmp_path, raw, code):
    predictor = Predictor()
    with lab_client(tmp_path, predictor) as client:
        assert submit(client, raw).status_code == code
        assert not client.get("/api/detector-lab/status").json()["busy"]
        assert not predictor.calls
        assert not list((tmp_path / "lab").glob("*/job.json"))


def test_request_cannot_change_checkpoint_threshold_or_order(tmp_path):
    predictor = Predictor()
    with lab_client(tmp_path, predictor) as client:
        for key in ("checkpoint", "threshold", "order_id"):
            assert submit(client, data={key: "untrusted"}).status_code == 422
        assert not predictor.calls
        assert client.get("/api/detector-lab/jobs/not-an-id").status_code == 404


@pytest.mark.parametrize("error,code", [(RuntimeError("private /Users/secret/file"), "inference_failed"),
                                      (subprocess.TimeoutExpired(["private command"], 90), "timeout")])
def test_failed_jobs_are_durable_without_exception_text_or_local_paths(tmp_path, error, code):
    predictor = Predictor()
    predictor.error = error
    with lab_client(tmp_path, predictor) as client:
        job = completed(client, submit(client).json()["job"]["id"])
        assert job["status"] == "failed" and job["result"] is None
        assert job["error"]["code"] == code
        assert "private" not in json.dumps(job) and "/Users/" not in json.dumps(job)
        assert json.loads((tmp_path / "lab" / job["id"] / "job.json").read_text()) == job


@pytest.mark.parametrize("field,value", [("checkpoint_sha256", "wrong"), ("source_sha256", "wrong"),
                                        ("device", "mps"), ("threshold", float("nan")),
                                        ("image_size", [1, 1])])
def test_invalid_result_identity_or_numbers_cannot_complete(tmp_path, field, value):
    predictor = Predictor()
    predictor.mutate = lambda result: result.update({field: value})
    with lab_client(tmp_path, predictor) as client:
        job = completed(client, submit(client).json()["job"]["id"])
        assert job["status"] == "failed" and job["result"] is None


def test_checkpoint_or_photo_change_is_detected(tmp_path):
    predictor = Predictor()
    predictor.release.clear()
    with lab_client(tmp_path, predictor) as client:
        initial = submit(client).json()["job"]
        assert predictor.started.wait(2)
        (tmp_path / "fixture.pt").write_bytes(b"changed checkpoint")
        predictor.release.set()
        assert completed(client, initial["id"])["status"] == "failed"
        image = tmp_path / "lab" / initial["id"] / "image.png"
        image.write_bytes(b"changed image")
        assert client.get(initial["image"]["url"]).status_code == 409


def test_startup_recovers_interrupted_jobs_without_rerunning(tmp_path):
    directory = tmp_path / "lab" / ("a" * 32)
    directory.mkdir(parents=True)
    (directory / "job.json").write_text(json.dumps({"id": "a" * 32, "status": "running", "error": None}))
    predictor = Predictor()
    with lab_client(tmp_path, predictor) as client:
        job = client.get(f"/api/detector-lab/jobs/{'a' * 32}").json()["job"]
        assert job["status"] == "interrupted" and job["error"]["code"] == "interrupted"
        assert not predictor.calls


def test_frozen_summary_threshold_is_checked_without_loading_checkpoint(tmp_path):
    checkpoint = tmp_path / "fixture.pt"
    checkpoint.write_bytes(b"synthetic checkpoint")
    (tmp_path / "training_summary.json").write_text(json.dumps({
        "best_checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
        "best_epoch": 10, "threshold": 0.8,
    }))
    with lab_client(tmp_path, Predictor()) as client:
        status = client.get("/api/detector-lab/status").json()
        assert status["checkpoint_epoch"] == 10 and status["threshold"] == 0.8
        job = completed(client, submit(client).json()["job"]["id"])
        assert job["status"] == "failed"


def test_cpu_subprocess_uses_packaged_module_and_fixed_deadline(tmp_path, monkeypatch):
    image = tmp_path / "image.png"
    image.write_bytes(photo_bytes())

    def fake_run(command, **kwargs):
        assert command[1:4] == ["-m", "kitguard.detector_worker", "--checkpoint"]
        assert "--device" not in command and "--threshold" not in command
        assert kwargs["timeout"] == 90
        assert kwargs["env"]["CUDA_VISIBLE_DEVICES"] == ""
        assert kwargs["capture_output"] is True
        (tmp_path / "worker-result.json").write_text('{"synthetic":true}')
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert _CpuPredictor()(tmp_path / "fixture.pt", image) == {"synthetic": True}


def test_packaged_worker_count_contract_matches_original_cli():
    from kitguard.detector_worker import summarize_predictions
    from scripts.predict_public_detector import summarize_predictions as original

    inputs = ([1, 2, 1], [[0, 0, 10, 10], [20, 1, 30, 20], [40, 5, 50, 20]],
              [0.9, 0.5, 0.49], 0.5, (64, 48))
    assert summarize_predictions(*inputs) == original(*inputs)


def test_packaged_worker_constructs_matching_frozen_bn_without_downloading(monkeypatch):
    torch = pytest.importorskip("torch")
    pytest.importorskip("torchvision")
    from torchvision.ops.misc import FrozenBatchNorm2d

    from kitguard.detector_worker import ARCHITECTURE, build_model

    def reject_download(*args, **kwargs):
        pytest.fail("CPU worker must never download pretrained weights")

    monkeypatch.setattr("torchvision.models._api.load_state_dict_from_url", reject_download)
    # CPU parameter initialization only; no checkpoint load or forward pass.
    model = build_model({"model": ARCHITECTURE, "classes": {1: "bolt", 2: "nut"},
                         "min_size": 640, "max_size": 960})
    assert not any(isinstance(module, torch.nn.BatchNorm2d) for module in model.modules())
    assert any(isinstance(module, FrozenBatchNorm2d) for module in model.modules())
    assert model.roi_heads.box_predictor.cls_score.out_features == 3
    assert model.transform.min_size == (640,) and model.transform.max_size == 960


def test_second_lab_instance_does_not_fail_main_app_startup(tmp_path):
    predictor = Predictor()
    with lab_client(tmp_path, predictor) as first:
        assert first.get("/api/detector-lab/status").json()["available"]
        with lab_client(tmp_path, Predictor()) as second:
            status = second.get("/api/detector-lab/status").json()
            assert not status["available"] and not status["accepting"]
            assert submit(second).status_code == 503
        assert first.get("/api/detector-lab/status").json()["available"]


@pytest.mark.parametrize("prediction", [
    {"label": 3, "bbox_xyxy": [0, 0, 10, 10], "score": 0.9},
    {"label": 1, "bbox_xyxy": [0, 0, 100, 10], "score": 0.9},
    {"label": 1, "bbox_xyxy": [0, 0, 0, 10], "score": 0.9},
    {"label": 1, "bbox_xyxy": [0, 0, 10, 10], "score": float("nan")},
])
def test_invalid_prediction_boxes_scores_or_classes_fail_closed(tmp_path, prediction):
    predictor = Predictor()
    predictor.mutate = lambda result: result.update(predictions=[prediction])
    with lab_client(tmp_path, predictor) as client:
        job = completed(client, submit(client).json()["job"]["id"])
        assert job["status"] == "failed" and job["result"] is None


def test_shutdown_retains_storage_lease_until_worker_has_finished_writing(tmp_path):
    checkpoint = tmp_path / "fixture.pt"
    checkpoint.write_bytes(b"synthetic checkpoint")
    predictor = Predictor()
    predictor.release.clear()
    lab = _DetectorLab(tmp_path / "lab", checkpoint, predictor)
    other = _DetectorLab(tmp_path / "lab", checkpoint, Predictor())
    lab.start()
    try:
        job = lab.create(photo_bytes())
        assert predictor.started.wait(2)
        lab.close()
        other.start()
        assert not other.status()["accepting"]
        predictor.release.set()
        assert predictor.finished.wait(2)
        deadline = time.monotonic() + 5
        while lab.status()["busy"]:
            assert time.monotonic() < deadline, "worker did not release storage"
            time.sleep(0.005)
        assert lab.get(job["id"])["status"] == "completed"
        fresh = _DetectorLab(tmp_path / "lab", checkpoint, Predictor())
        fresh.start()
        try:
            assert fresh.status()["accepting"]
        finally:
            fresh.close()
    finally:
        predictor.release.set()
        lab.close()
        other.close()
