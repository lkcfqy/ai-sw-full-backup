"""API test fixtures only; synthetic images are NOT competition evaluation data."""

from __future__ import annotations

from copy import deepcopy
from io import BytesIO
from threading import Event

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

PARTS = ("bolt", "nut", "washer", "bracket")
REQUIREMENTS = {"bolt": 2, "nut": 2, "washer": 2, "bracket": 1}


class FakeAnalyzer:
    """Deterministic injected test double, never a product inference fallback."""

    def __init__(self):
        self.available = True
        self.result = None
        self.error = None
        self.proposal = None
        self.calls = []
        self.started = Event()
        self.finished = Event()
        self.release = Event()
        self.release.set()
        self.proposal_started = Event()
        self.proposal_finished = Event()
        self.proposal_release = Event()
        self.proposal_release.set()

    def status(self):
        return {
            "available": self.available,
            "loaded": self.available,
            "label": "SYNTHETIC TEST FIXTURE ONLY",
            "path": None,
            "error": None if self.available else "Test model unavailable",
        }

    def observe(self, image_path, requirements, references):
        self.calls.append(
            {"image_path": image_path, "requirements": deepcopy(requirements), "references": references}
        )
        self.started.set()
        try:
            if not self.release.wait(timeout=10):
                raise RuntimeError("Test observer was not released")
            if not self.available:
                raise RuntimeError("Test model unavailable")
            if self.error is not None:
                raise self.error
            if self.result is not None:
                return deepcopy(self.result)
            return self.observation(requirements)
        finally:
            self.finished.set()

    def propose_revision(self, instruction, requirements):
        self.proposal_started.set()
        try:
            if not self.proposal_release.wait(timeout=10):
                raise RuntimeError("Test proposer was not released")
            if self.error is not None:
                raise self.error
            return deepcopy(self.proposal or {"requirements": requirements, "explanation": "TEST ONLY"})
        finally:
            self.proposal_finished.set()

    @staticmethod
    def observation(observed, *, action="none", issues=None):
        return {
            "observed": deepcopy(observed),
            "issues": issues or [],
            "action": {"kind": action, "message": "Test observer output", "region": None},
            "model_label": "SYNTHETIC TEST FIXTURE ONLY",
            "backend": "test",
            "latency_ms": 1,
        }


@pytest.fixture
def analyzer():
    return FakeAnalyzer()


@pytest.fixture
def client(tmp_path, analyzer):
    from kitguard.app import create_app

    app = create_app(data_dir=tmp_path / "data", analyzer=analyzer)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def image_bytes():
    def make(seed=0, *, format="PNG", exif=False):
        image = Image.new("RGB", (640, 480), (220, 220, 220))
        draw = ImageDraw.Draw(image)
        draw.rectangle((20 + seed * 3, 20, 150 + seed * 3, 160), fill=(40, 80, 120))
        draw.text((20, 210), f"SYNTHETIC API TEST FIXTURE {seed}", fill="black")
        output = BytesIO()
        kwargs = {}
        if exif:
            metadata = Image.Exif()
            metadata[271] = "PRIVATE TEST CAMERA"
            metadata[270] = "TEST METADATA MUST BE REMOVED"
            kwargs["exif"] = metadata
        image.save(output, format=format, **kwargs)
        return output.getvalue()

    return make


@pytest.fixture
def order(client):
    response = client.post("/api/orders", json={"title": "Synthetic test order", "requirements": REQUIREMENTS})
    assert response.status_code == 201, response.text
    return response.json()["order"]


@pytest.fixture
def upload(client, image_bytes):
    def send(order, seed=0, *, payload=None, name="test.png", mime="image/png"):
        return client.post(
            f"/api/orders/{order['id']}/photos",
            data={"expected_revision": order["revision"]},
            files={"photo": (name, image_bytes(seed) if payload is None else payload, mime)},
        )

    return send


@pytest.fixture
def inspected(client, order, upload):
    posted = upload(order)
    assert posted.status_code == 201, posted.text
    photo = posted.json()["photo"]
    response = client.post(
        f"/api/orders/{order['id']}/inspect",
        json={"photo_id": photo["id"], "expected_revision": order["revision"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["order"]["status"] == "ready", response.text
    return response.json()
