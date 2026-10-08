"""Main-app integration guards using injected model output, never real accuracy."""
import hashlib
import time

from fastapi.testclient import TestClient
from PIL import Image

from kitguard.app import create_app


def test_preview_page_and_disabled_api_are_available_in_main_app(client):
    status = client.get("/api/detector-lab/status")
    assert status.status_code == 200
    assert status.json()["enabled"] is False
    assert status.json()["available"] is False
    for asset in ("detector.html", "detector.js", "detector.css"):
        response = client.get(f"/static/{asset}")
        assert response.status_code == 200
        assert "default-src 'self'" in response.headers["content-security-policy"]


def test_detector_job_does_not_change_an_order(tmp_path, analyzer, image_bytes):
    checkpoint = tmp_path / "fixture.pt"
    checkpoint.write_bytes(b"not real model weights")

    def predictor(checkpoint_path, image_path):
        with Image.open(image_path) as image:
            size = list(image.size)
        return {
            "checkpoint_sha256": hashlib.sha256(checkpoint_path.read_bytes()).hexdigest(),
            "source_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
            "image_size": size, "device": "cpu", "threshold": 0.4, "inference_seconds": 0.001,
            "predictions": [{"label": 1, "bbox_xyxy": [1, 1, 20, 20], "score": 0.9}],
            "counts": {"bolt": 99, "nut": 99, "washer": 99, "bracket": 99},
            "decision": "ready",  # Must never propagate an injected release decision.
        }

    app = create_app(data_dir=tmp_path / "data", analyzer=analyzer,
                     detector_checkpoint=checkpoint, detector_predictor=predictor)
    with TestClient(app) as client:
        response = client.post("/api/orders", json={"title": "Unchanged order", "requirements":
                               {"bolt": 2, "nut": 1, "washer": 1, "bracket": 0}})
        assert response.status_code == 201
        before = client.get("/api/orders").json()
        response = client.post("/api/detector-lab/jobs", files={"photo": ("fixture.png", image_bytes(), "image/png")})
        assert response.status_code == 202
        job_id = response.json()["job"]["id"]
        deadline = time.monotonic() + 5
        while True:
            job = client.get(f"/api/detector-lab/jobs/{job_id}").json()["job"]
            if job["status"] in {"completed", "failed"}:
                break
            assert time.monotonic() < deadline
            time.sleep(0.01)
        assert job["status"] == "completed"
        assert job["result"]["counts"] == {"bolt": 1, "nut": 0, "washer": None, "bracket": None}
        assert job["decision"] is None and job["result"]["decision"] is None
        exported = client.get(f"/api/detector-lab/jobs/{job_id}/download")
        assert exported.status_code == 200 and exported.json() == job
        assert exported.headers["content-disposition"].startswith("attachment;")
        assert client.get("/api/orders").json() == before
        assert not analyzer.calls
