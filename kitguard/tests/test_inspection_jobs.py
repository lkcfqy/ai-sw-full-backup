"""Request recovery tests with injected CPU observers, not recognition accuracy."""

import asyncio
import time

import httpx
import pytest
from conftest import REQUIREMENTS
from fastapi.testclient import TestClient

from kitguard.app import create_app
from kitguard.inspection_jobs import InspectionJobs, JobRequest
from kitguard.runtime import DataDirectoryLease, InferenceGate
from kitguard.store import StateError, Store


def setup(client, image_bytes):
    order = client.post("/api/orders", json={"title": "Job fixture", "requirements": REQUIREMENTS}).json()["order"]
    photo = client.post(f"/api/orders/{order['id']}/photos", data={"expected_revision": 1},
                        files={"photo": ("test.png", image_bytes(), "image/png")}).json()["photo"]
    return order, {"photo_id": photo["id"], "expected_revision": 1, "request_key": "same-request-001"}


def start(client, order, request):
    return client.post(f"/api/orders/{order['id']}/inspection-jobs", json=request)


def wait_job(client, job_id):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        result = client.get(f"/api/inspection-jobs/{job_id}").json()
        if result["job"]["status"] != "running":
            return result
        time.sleep(.005)
    raise AssertionError("CPU job did not finish")


def test_response_loss_replay_and_resume_only_one_observation(tmp_path, analyzer, image_bytes):
    app = create_app(data_dir=tmp_path, analyzer=analyzer)
    with TestClient(app) as client:
        order, request = setup(client, image_bytes)
        analyzer.release.clear()
        try:
            response = start(client, order, request)
            assert response.status_code == 202
            job = response.json()["job"]
            assert analyzer.started.wait(2)
            recovered = start(client, order, request).json()
            assert recovered["replayed"] and recovered["job"]["id"] == job["id"]
            assert client.get(f"/api/orders/{order['id']}/inspection-jobs").json()["jobs"][0]["id"] == job["id"]
            assert len(analyzer.calls) == 1
            assert start(client, order, {**request, "request_key": "fresh-request-002"}).status_code == 503
            assert start(client, order, {**request, "expected_revision": 2}).status_code == 409
        finally:
            analyzer.release.set()
        result = wait_job(client, job["id"])
        assert result["job"]["status"] == "succeeded"
        assert result["job"]["check_id"] == result["order"]["latest_check"]["id"]
        assert result["order"]["latest_check"]["backend"] == "test"
        assert len(analyzer.calls) == 1
        assert start(client, order, request).json()["job"]["status"] == "succeeded"


def test_async_timeout_keeps_busy_slot_and_does_not_accept_late_result(tmp_path, analyzer, image_bytes):
    app = create_app(data_dir=tmp_path, analyzer=analyzer, inference_timeout=.03)
    with TestClient(app) as client:
        order, request = setup(client, image_bytes)
        analyzer.release.clear()
        try:
            job = start(client, order, request).json()["job"]
            result = wait_job(client, job["id"])
            assert result["job"]["status"] == "failed"
            assert result["job"]["error"]["status_code"] == 504
            assert result["order"]["checks"] == []
            assert client.get("/api/health").json()["inference"]["busy"]
            assert start(client, order, {**request, "request_key": "new-request-001"}).status_code == 503
        finally:
            analyzer.release.set()
            assert analyzer.finished.wait(2)
        assert wait_job(client, job["id"])["job"]["status"] == "failed"
        assert client.get(f"/api/orders/{order['id']}").json()["order"]["checks"] == []


def test_async_result_rejects_revision_changed_during_inference(tmp_path, analyzer, image_bytes):
    app = create_app(data_dir=tmp_path, analyzer=analyzer)
    with TestClient(app) as client:
        order, request = setup(client, image_bytes)
        analyzer.release.clear()
        try:
            job = start(client, order, request).json()["job"]
            assert analyzer.started.wait(2)
            revised = client.post(f"/api/orders/{order['id']}/revise", json={
                "expected_revision": 1, "requirements": {**REQUIREMENTS, "bolt": 3}, "instruction": "test"})
            assert revised.status_code == 200
        finally:
            analyzer.release.set()
        result = wait_job(client, job["id"])
        assert result["job"]["status"] == "failed"
        assert result["job"]["error"]["status_code"] == 409
        assert result["order"]["revision"] == 2
        assert result["order"]["checks"] == []


def test_restart_marks_stored_running_job_interrupted_without_replaying(tmp_path, analyzer, image_bytes):
    app = create_app(data_dir=tmp_path, analyzer=analyzer)
    with TestClient(app) as client:
        order, request = setup(client, image_bytes)
        job = start(client, order, request).json()["job"]
        wait_job(client, job["id"])
        saved = app.state.inspection_jobs.get(job["id"])
        saved.update(status="running", check_id=None, finished_at=None)
        app.state.inspection_jobs._save(saved)
    another = create_app(data_dir=tmp_path, analyzer=analyzer)
    with TestClient(another) as client:
        result = client.get(f"/api/inspection-jobs/{job['id']}").json()
        assert result["job"]["status"] == "interrupted"
        assert start(client, order, request).json()["replayed"] is True
        assert len(analyzer.calls) == 1


def test_missing_photo_does_not_leave_gate_reserved(tmp_path, analyzer):
    app = create_app(data_dir=tmp_path, analyzer=analyzer)
    with TestClient(app) as client:
        order = client.post("/api/orders", json={"title": "empty", "requirements": REQUIREMENTS}).json()["order"]
        assert start(client, order, {"photo_id": "missing", "expected_revision": 1,
                                   "request_key": "request-missing"}).status_code == 409
        assert not app.state.inference_gate.status()["busy"]
        assert app.state.inspection_jobs.list(order["id"]) == []


def standalone_jobs(tmp_path):
    """State-only fixture: the injected runner never decodes or observes pixels."""
    store, gate = Store(tmp_path), InferenceGate()
    order = store.create("SYNTHETIC JOB STATE ONLY", REQUIREMENTS)
    photo = {"id": "synthetic-photo", "sha256": "a" * 64, "revision": 1}
    order = store.add_photo(order["id"], photo, tmp_path / "unused.jpg", expected=1)
    return InspectionJobs(store, gate), order, JobRequest(
        photo_id=photo["id"], expected_revision=1, request_key="standalone-request-001")


def test_cancel_before_first_step_persists_interruption_and_releases_unused_slot(tmp_path):
    jobs, order, request = standalone_jobs(tmp_path)
    async def runner(*_):
        pytest.fail("Pre-start cancellation must never execute the runner")
    jobs.runner = runner
    async def scenario():
        job = jobs.start(order["id"], request)["job"]
        await jobs.close()
        saved = jobs.get(job["id"])
        assert saved["status"] == "interrupted" and saved["finished_at"]
        assert not jobs.gate.status()["busy"]
        assert not jobs.store.get(order["id"])["active_inspection"]
        assert jobs.store.get(order["id"])["checks"] == []
        assert not jobs.tasks
        replay = jobs.start(order["id"], request)
        assert replay["replayed"] and replay["job"] == saved
    asyncio.run(scenario())


def test_shutdown_rejects_new_admission_even_after_old_slot_is_released(tmp_path):
    jobs, order, request = standalone_jobs(tmp_path)
    async def runner(*_):
        await asyncio.Event().wait()
    jobs.runner = runner
    async def scenario():
        jobs.start(order["id"], request)
        await asyncio.sleep(0)
        closing = asyncio.create_task(jobs.close())
        while jobs.gate.status()["busy"]:
            await asyncio.sleep(0)
        # Cancellation has released its reservation; close may still be
        # awaiting completion callbacks for its original task snapshot.
        with pytest.raises(StateError) as rejected:
            jobs.start(order["id"], request.model_copy(update={"request_key": "escaped-shutdown"}))
        assert rejected.value.code == 503
        await closing
        assert len(jobs.list(order["id"])) == 1
        assert jobs.list(order["id"])[0]["status"] == "interrupted"
        assert not jobs.tasks and not jobs.store.get(order["id"])["active_inspection"]
        with pytest.raises(StateError):
            jobs.start(order["id"], request.model_copy(update={"request_key": "after-close-key"}))
    asyncio.run(scenario())


def test_cancel_running_model_preserves_lease_until_worker_finishes_without_late_commit(tmp_path):
    import threading

    jobs, order, request = standalone_jobs(tmp_path)
    release, started = threading.Event(), threading.Event()
    lease = DataDirectoryLease(tmp_path).acquire()
    def worker():
        started.set()
        assert release.wait(3)
        return {"check": {"id": "must-not-be-saved"}}
    async def runner(_order, _body, _token, _snapshot, slot):
        return await slot.run(worker, timeout=2)
    jobs.runner = runner
    async def scenario():
        job = jobs.start(order["id"], request)["job"]
        assert await asyncio.to_thread(started.wait, 2)
        await jobs.close()
        assert jobs.get(job["id"])["status"] == "interrupted"
        assert jobs.gate.status() == {"busy": True, "request_waiting": False, "queue_capacity": 0}
        jobs.gate.close_when_idle(lease.close)
        with pytest.raises(RuntimeError, match="另一个 KitGuard"):
            DataDirectoryLease(tmp_path).acquire()
        release.set()
        deadline = time.monotonic() + 2
        while lease.file is not None and time.monotonic() < deadline:
            await asyncio.sleep(.005)
        assert lease.file is None
        assert jobs.get(job["id"])["status"] == "interrupted"
        assert jobs.get(job["id"])["check_id"] is None
        assert jobs.store.get(order["id"])["checks"] == []
        assert not jobs.store.get(order["id"])["active_inspection"]
    try:
        asyncio.run(scenario())
    finally:
        release.set()
        lease.close()


@pytest.mark.parametrize("failure", [StateError("Fixture stale state", 409), RuntimeError("Private trace/path")])
def test_runner_failure_always_clears_active_token_and_stores_safe_failure(tmp_path, failure):
    jobs, order, request = standalone_jobs(tmp_path)
    async def runner(*_):
        raise failure
    jobs.runner = runner
    async def scenario():
        job = jobs.start(order["id"], request)["job"]
        await asyncio.gather(*jobs.tasks)
        saved = jobs.get(job["id"])
        assert saved["status"] == "failed"
        assert saved["error"]["status_code"] == (409 if isinstance(failure, StateError) else 503)
        assert "Private trace/path" not in str(saved)
        assert not jobs.store.get(order["id"])["active_inspection"]
        assert not jobs.gate.status()["busy"]
        await jobs.close()
    asyncio.run(scenario())


def test_actual_lost_http_response_replays_accepted_job_instead_of_observing_twice(tmp_path, analyzer, image_bytes):
    app = create_app(data_dir=tmp_path, analyzer=analyzer)
    class DropFirstAcceptedResponse(httpx.AsyncBaseTransport):
        def __init__(self):
            self.delegate = httpx.ASGITransport(app=app)
            self.dropped = False
        async def handle_async_request(self, request):
            response = await self.delegate.handle_async_request(request)
            if request.method == "POST" and request.url.path.endswith("/inspection-jobs") and not self.dropped:
                self.dropped = True
                assert response.status_code == 202
                await response.aclose()
                raise httpx.ReadError("Injected connection loss after server accepted the job")
            return response
        async def aclose(self):
            await self.delegate.aclose()
    async def scenario(order, request):
        async with httpx.AsyncClient(transport=DropFirstAcceptedResponse(), base_url="http://testserver") as client:
            endpoint = f"/api/orders/{order['id']}/inspection-jobs"
            with pytest.raises(httpx.ReadError):
                await client.post(endpoint, json=request)
            assert await asyncio.to_thread(analyzer.started.wait, 2)
            responses = await asyncio.gather(*(client.post(endpoint, json=request) for _ in range(5)))
            assert all(response.status_code == 202 and response.json()["replayed"] for response in responses)
            job_ids = {response.json()["job"]["id"] for response in responses}
            assert len(job_ids) == 1 and len(analyzer.calls) == 1
            analyzer.release.set()
            await asyncio.gather(*app.state.inspection_jobs.tasks)
            saved = app.state.inspection_jobs.get(job_ids.pop())
            assert saved["status"] == "succeeded"
            assert app.state.store.get(order["id"])["latest_check"]["id"] == saved["check_id"]
    with TestClient(app) as client:
        order, request = setup(client, image_bytes)
        analyzer.release.clear()
        try:
            asyncio.run(scenario(order, request))
        finally:
            analyzer.release.set()


def test_stale_terminal_replay_after_order_reopen_never_reexecutes(tmp_path, analyzer, image_bytes):
    app = create_app(data_dir=tmp_path, analyzer=analyzer)
    with TestClient(app) as client:
        order, request = setup(client, image_bytes)
        job = start(client, order, request).json()["job"]
        result = wait_job(client, job["id"])
        check = result["order"]["latest_check"]
        assert client.post(f"/api/orders/{order['id']}/complete", json={
            "check_id": check["id"], "expected_revision": 1, "confirmed": True,
            "idempotency_key": "fixture-complete-key"}).status_code == 200
        fresh = client.post(f"/api/orders/{order['id']}/reopen", json={
            "expected_revision": 1, "reason": "Fixture fresh round", "confirmed": True,
            "idempotency_key": "fixture-reopen-key"}).json()["order"]
        replay = start(client, order, request)
        assert replay.status_code == 202 and replay.json()["replayed"] is True
        assert replay.json()["job"]["id"] == job["id"]
        assert app.state.store.get(order["id"]) == fresh
        assert fresh["revision"] == 2 and fresh["status"] == "pending"
        assert len(analyzer.calls) == 1
