"""CPU engineering checks for worker ownership and local-file integrity, not model accuracy."""

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from conftest import REQUIREMENTS, FakeAnalyzer
from fastapi.testclient import TestClient
from PIL import Image

from kitguard.app import create_app
from kitguard.runtime import DataDirectoryLease, InferenceGate
from kitguard.spatial import SpatialInventory
from kitguard.vision import LocalVision


def setup(client, image_bytes, requirements=REQUIREMENTS):
    order = client.post("/api/orders", json={"title": "CPU runtime fixture", "requirements": requirements}).json()["order"]
    photo = client.post(f"/api/orders/{order['id']}/photos", data={"expected_revision": 1},
        files={"photo": ("fixture.png", image_bytes(), "image/png")}).json()["photo"]
    return order, photo


def inspect(client, order, photo):
    return client.post(f"/api/orders/{order['id']}/inspect", json={"photo_id": photo["id"], "expected_revision": 1})


def wait_idle(app):
    deadline = time.monotonic() + 2
    while app.state.inference_gate.status()["busy"] and time.monotonic() < deadline:
        time.sleep(.005)
    assert not app.state.inference_gate.status()["busy"]


class QueuedCPUObserver(LocalVision):
    """Use the actual single model-thread dispatcher; replace only CPU observation."""

    def __init__(self):
        super().__init__(observation_mode="spatial_inventory")
        self.release = threading.Event()
        self.executed = []

    def status(self):
        return {"available": True, "loaded": False, "observation_mode": "spatial_inventory"}

    def _observe(self, image_path, references, context=None):
        self.executed.append(threading.current_thread().name)
        if not self.release.wait(5):
            raise RuntimeError("CPU fixture release timeout")
        return FakeAnalyzer.observation(REQUIREMENTS)


def test_timeout_retries_do_not_enter_real_model_dispatch_queue(tmp_path, image_bytes):
    engine = QueuedCPUObserver()
    app = create_app(data_dir=tmp_path, analyzer=engine, inference_timeout=.04)
    with TestClient(app) as client:
        order, photo = setup(client, image_bytes)
        try:
            assert inspect(client, order, photo).status_code == 504
            before = app.state.store.get(order["id"])
            assert [inspect(client, order, photo).status_code for _ in range(3)] == [503] * 3
            assert app.state.store.get(order["id"]) == before
            assert len(engine.executed) == 1
            health = client.get("/api/health").json()["inference"]
            assert health == {"busy": True, "request_waiting": False, "queue_capacity": 0}
        finally:
            engine.release.set()
            wait_idle(app)
        assert len(engine.executed) == 1
        assert app.state.store.get(order["id"])["checks"] == []
        assert inspect(client, order, photo).status_code == 200
        assert len(engine.executed) == 2
        assert all(name.startswith("kitguard-mlx") for name in engine.executed)


@pytest.mark.parametrize("first", ["inspect", "proposal"])
def test_inspection_and_proposal_share_admission_across_orders(tmp_path, analyzer, image_bytes, first):
    app = create_app(data_dir=tmp_path, analyzer=analyzer, inference_timeout=.04)
    with TestClient(app) as client:
        one, photo = setup(client, image_bytes)
        other, other_photo = setup(client, image_bytes)
        analyzer.release.clear()
        analyzer.proposal_release.clear()
        try:
            if first == "inspect":
                initial = inspect(client, one, photo)
            else:
                initial = client.post(f"/api/orders/{one['id']}/propose-revision", json={
                    "instruction": "bolt 3", "expected_revision": 1})
            assert initial.status_code == 504
            before = app.state.store.get(other["id"])
            assert inspect(client, other, other_photo).status_code == 503
            assert client.post(f"/api/orders/{other['id']}/propose-revision", json={
                "instruction": "bolt 3", "expected_revision": 1}).status_code == 503
            assert app.state.store.get(other["id"]) == before
        finally:
            analyzer.release.set()
            analyzer.proposal_release.set()
            wait_idle(app)


def test_cancelled_request_retains_worker_slot_until_thread_finishes(tmp_path, analyzer, image_bytes):
    app = create_app(data_dir=tmp_path, analyzer=analyzer)
    with TestClient(app) as client:
        order, photo = setup(client, image_bytes)
        analyzer.release.clear()
        async def scenario():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as other:
                task = asyncio.create_task(other.post(f"/api/orders/{order['id']}/inspect", json={
                    "photo_id": photo["id"], "expected_revision": 1}))
                assert await asyncio.to_thread(analyzer.started.wait, 2)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                assert app.state.inference_gate.status()["busy"]
                response = await other.post(f"/api/orders/{order['id']}/inspect", json={
                    "photo_id": photo["id"], "expected_revision": 1})
                assert response.status_code == 503
                analyzer.release.set()
                await asyncio.to_thread(wait_idle, app)
        try:
            asyncio.run(scenario())
        finally:
            analyzer.release.set()
            wait_idle(app)
        assert len(analyzer.calls) == 1
        assert app.state.store.get(order["id"])["checks"] == []


def test_second_live_instance_is_rejected_before_recovery(tmp_path, analyzer, image_bytes):
    app = create_app(data_dir=tmp_path, analyzer=analyzer)
    with TestClient(app) as first:
        order, photo = setup(first, image_bytes)
        analyzer.release.clear()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(inspect, first, order, photo)
            try:
                assert analyzer.started.wait(2)
                before = app.state.store.get(order["id"])
                with (
                    pytest.raises(RuntimeError, match="另一个 KitGuard"),
                    TestClient(create_app(data_dir=tmp_path, analyzer=analyzer)),
                ):
                    pytest.fail("Second live data-directory owner must not start")
                assert app.state.store.get(order["id"]) == before
            finally:
                analyzer.release.set()
            assert future.result(2).status_code == 200


def test_data_lease_rejects_other_process_and_releases_cleanly(tmp_path):
    script = """import json,sys
from pathlib import Path
from kitguard.runtime import DataDirectoryLease
try:
 lease = DataDirectoryLease(Path(sys.argv[1])).acquire()
 lease.close()
 print(json.dumps({'acquired': True}))
except RuntimeError:
 print(json.dumps({'acquired': False}))
"""
    def child():
        result = subprocess.run([sys.executable, "-c", script, str(tmp_path)],
            env={**os.environ, "KITGUARD_DATA_DIR": str(tmp_path / "child-unused")},
            capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    lease = DataDirectoryLease(tmp_path).acquire()
    try:
        assert child() == {"acquired": False}
    finally:
        lease.close()
    assert child() == {"acquired": True}


def test_shutdown_retains_data_lease_until_expired_worker_really_finishes(tmp_path):
    lease = DataDirectoryLease(tmp_path).acquire()
    gate = InferenceGate()
    release = threading.Event()
    started = threading.Event()
    def work():
        started.set()
        assert release.wait(3)
    async def scenario():
        with gate.reserve() as slot, pytest.raises(TimeoutError):
            await slot.run(work, timeout=.04)
        assert started.is_set()
        gate.close_when_idle(lease.close)
        with pytest.raises(RuntimeError, match="另一个 KitGuard"):
            DataDirectoryLease(tmp_path).acquire()
        release.set()
        deadline = time.monotonic() + 2
        while lease.file is not None and time.monotonic() < deadline:
            await asyncio.sleep(.005)
        assert lease.file is None
        renewed = DataDirectoryLease(tmp_path).acquire()
        renewed.close()
    try:
        asyncio.run(scenario())
    finally:
        release.set()
        lease.close()


def test_crashed_owner_does_not_leave_a_permanent_stale_lock(tmp_path):
    script = """import sys,time
from pathlib import Path
from kitguard.runtime import DataDirectoryLease
lease = DataDirectoryLease(Path(sys.argv[1])).acquire()
print('locked', flush=True)
time.sleep(30)
"""
    process = subprocess.Popen([sys.executable, "-c", script, str(tmp_path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline().strip() == "locked"
        with pytest.raises(RuntimeError, match="另一个 KitGuard"):
            DataDirectoryLease(tmp_path).acquire()
    finally:
        process.terminate()
        process.communicate(timeout=2)
    renewed = DataDirectoryLease(tmp_path).acquire()
    renewed.close()


def test_rejected_invalid_request_releases_unused_reservation(client, order, upload):
    response = inspect(client, order, {"id": "not-current-photo"})
    assert response.status_code == 409
    assert not client.app.state.inference_gate.status()["busy"]
    assert inspect(client, order, upload(order).json()["photo"]).status_code == 200


@pytest.mark.parametrize("target", ["photo", "reference"])
@pytest.mark.parametrize("when", ["before", "during", "completion"])
def test_changed_evidence_file_cannot_commit_or_complete(tmp_path, analyzer, image_bytes, target, when):
    app = create_app(data_dir=tmp_path, analyzer=analyzer)
    with TestClient(app) as client:
        order, photo = setup(client, image_bytes)
        evidence = photo
        if target == "reference":
            evidence = client.post(f"/api/orders/{order['id']}/references/bolt", data={"expected_revision": 1},
                files={"photo": ("reference.png", image_bytes(1), "image/png")}).json()["photo"]
        path = app.state.store.photo_path(evidence["id"])
        def change():
            Image.new("RGB", (160, 96), (1, 90, 150)).save(path, format="JPEG", quality=95)
            assert hashlib.sha256(path.read_bytes()).hexdigest() != evidence["sha256"]
        if when == "before":
            change()
            assert inspect(client, order, photo).status_code == 409
            assert analyzer.calls == []
        elif when == "during":
            analyzer.release.clear()
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(inspect, client, order, photo)
                try:
                    assert analyzer.started.wait(2)
                    change()
                finally:
                    analyzer.release.set()
                assert future.result(2).status_code == 409
        else:
            check = inspect(client, order, photo).json()["check"]
            change()
            response = client.post(f"/api/orders/{order['id']}/complete", json={
                "expected_revision": 1, "check_id": check["id"], "confirmed": True,
                "idempotency_key": "changed-file"})
            assert response.status_code == 409
        saved = app.state.store.get(order["id"])
        assert saved["completions"] == []
        if when != "completion":
            assert saved["checks"] == []
        assert not app.state.inference_gate.status()["busy"]


def test_guarded_non_ring_path_rejects_changed_file_without_generating(tmp_path, image_bytes):
    engine = LocalVision(observation_mode="spatial_guarded")
    calls = []
    def generate(*args, **kwargs):
        calls.append(True)
        return SpatialInventory.model_validate({"objects": [{"part": "bolt", "center": [.5, .5]}],
            "uncertain_parts": [], "issues": [], "action": {"kind": "none", "message": "CPU fixture"}})
    engine._generate = generate
    engine.status = lambda: {"available": True, "loaded": False, "observation_mode": "spatial_guarded"}
    app = create_app(data_dir=tmp_path, analyzer=engine)
    with TestClient(app) as client:
        order, photo = setup(client, image_bytes, {"bolt": 1, "nut": 0, "washer": 0, "bracket": 0})
        Image.new("RGB", (160, 96), "blue").save(app.state.store.photo_path(photo["id"]), format="JPEG")
        assert inspect(client, order, photo).status_code == 409
        assert calls == []
