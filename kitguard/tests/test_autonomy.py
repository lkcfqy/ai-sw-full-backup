"""Injected synthetic observers verify orchestration, never image accuracy or people."""
import copy
import hashlib
import io
import json
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from kitguard.autonomy import CASES, PROTOCOL, route_check


@pytest.fixture
def mission_setup(tmp_path, image_bytes, analyzer, monkeypatch):
    from kitguard import app as module
    from kitguard.app import create_app
    from kitguard.public_demo_catalog import CATALOG

    catalog = copy.deepcopy(CATALOG)
    root = tmp_path / "synthetic-sources"
    for index, spec in enumerate(catalog):
        path = root / spec["image"]
        path.parent.mkdir(parents=True, exist_ok=True)
        content = image_bytes(index)
        path.write_bytes(content)
        spec["source_sha256"] = hashlib.sha256(content).hexdigest()
    monkeypatch.setattr(module, "PUBLIC_DEMOS", catalog)
    original_status, original_observe = analyzer.status, analyzer.observe
    identity = {"repo_id": "SYNTHETIC-NOT-A-REAL-MODEL", "revision": "synthetic",
                "observer_protocol_sha256": "a" * 64, "observation_mode": "single_pass", "image_max_side": 1536}
    analyzer.status = lambda: {**original_status(), **identity}

    def observe(*args):
        result = original_observe(*args)
        result["backend"] = "mlx"  # Deliberate injected fixture; not a runtime fallback.
        return result
    analyzer.observe = observe
    app = create_app(data_dir=tmp_path / "data", analyzer=analyzer, demo_dataset_root=root)
    return app, analyzer, root, catalog, identity


@pytest.fixture
def mission_client(mission_setup):
    app, analyzer, root, catalog, identity = mission_setup
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, analyzer, root, catalog, identity


def start(client, scenario="all", key="synthetic-mission-01", status=202):
    response = client.post("/api/autonomous-missions", json={"scenario": scenario, "request_key": key})
    assert response.status_code == status, response.text
    return response.json().get("run")


def wait(client, run_id):
    for _ in range(150):
        response = client.get(f"/api/autonomous-missions/{run_id}")
        assert response.status_code == 200, response.text
        run = response.json()["run"]
        if run["status"] != "running":
            return run
        time.sleep(.015)
    pytest.fail("Synthetic mission did not finish")


@pytest.mark.parametrize("decision,expected", [("ready", "quantities_match"), ("correct", "quantity_difference"),
                            ("recapture", "needs_more_evidence"), ("manual", "needs_more_evidence")])
def test_branch_is_driven_by_check_decision(decision, expected):
    assert route_check({"decision": decision})["finding"] == expected


def test_unknown_decision_is_never_promoted():
    with pytest.raises(Exception, match="核验分支"):
        route_check({"decision": "unexpected"})


def test_protocol_has_no_author_truth_and_fixed_declared_revision():
    assert "truth" not in json.dumps(PROTOCOL).lower()
    revision = next(c for c in CASES if c["id"] == "revision")
    assert revision["bom"]["bolt"] == 3 and revision["revision_bom"]["bolt"] == 2


def test_all_cases_are_autonomous_four_real_path_jobs_no_human_claim(mission_client):
    client, analyzer, *_ = mission_client
    run = wait(client, start(client)["id"])
    assert run["status"] == "completed"
    assert len(analyzer.calls) == run["planned_checks"] == 4
    assert run["planned_cases"] == 3
    assert run["human_participants"] == run["physical_completions"] == 0
    assert run["purpose"] == "engineering_rehearsal" and run["elapsed_ms"] > 0
    for case in run["cases"]:
        assert case["status"] == "completed" and case["live_binding"]["status"] == "current"
        assert case["snapshot"].get("public_reviews", []) == []
        assert case["snapshot"].get("digital_resolutions", []) == []
        assert case["snapshot"]["status"] != "completed"
    revision = run["cases"][2]
    assert revision["stale_check_rejected"] is True
    r1, r2 = revision["checks"]
    assert r1["revision"] == 1 and r2["revision"] == 2 and r1["id"] != r2["id"]
    assert r1["photo_id"] != r2["photo_id"] and r1["photo_sha256"] == r2["photo_sha256"]
    order = client.get(f'/api/orders/{revision["order_id"]}').json()["order"]
    assert order["checks"][0]["valid"] is False
    assert order["requirements"]["bolt"] == 2


def test_dynamic_difference_routes_without_rewriting_bom(mission_client):
    client, analyzer, *_ = mission_client
    analyzer.result = analyzer.observation({"bolt": 3, "nut": 0, "washer": 0, "bracket": 0})
    run = wait(client, start(client, "quantity")["id"])
    case = run["cases"][0]
    assert case["finding"] == "quantity_difference"
    assert case["snapshot"]["requirements"]["bolt"] == 2
    assert case["steps"][-1]["tool"] == "list_differences"
    assert len(analyzer.calls) == 1


def test_uncertainty_is_preserved_without_same_pixel_retry(mission_client):
    client, analyzer, *_ = mission_client
    analyzer.result = analyzer.observation({"bolt": 2, "nut": None, "washer": None, "bracket": 0}, action="recapture")
    run = wait(client, start(client, "identity")["id"])
    case = run["cases"][0]
    assert run["status"] == "completed"  # Execution finished, not asserted correct.
    assert case["finding"] == "needs_more_evidence" and case["checks"][0]["observed"]["nut"] is None
    assert case["steps"][-1]["tool"] == "request_more_evidence" and len(analyzer.calls) == 1


def test_idempotency_conflict_and_completed_replay(mission_client):
    client, analyzer, *_ = mission_client
    run = wait(client, start(client, "quantity")["id"])
    replay = start(client, "quantity")
    assert replay["id"] == run["id"] and len(analyzer.calls) == 1
    start(client, "identity", status=409)
    assert len(analyzer.calls) == 1


@pytest.mark.parametrize("body", [{"scenario": "all", "request_key": "good-key", "human_participants": 6},
    {"scenario": "all", "request_key": "good-key", "bom": {"bolt": 3}},
    {"scenario": "unknown", "request_key": "good-key"}, {"scenario": "all", "request_key": "short"}])
def test_external_requests_cannot_inject_truth_bom_or_people(mission_client, body):
    client, analyzer, *_ = mission_client
    response = client.post("/api/autonomous-missions", json=body)
    assert response.status_code == 422 and not analyzer.calls


def test_model_not_ready_does_not_create_orders_or_optional_table(mission_client):
    client, analyzer, *_ = mission_client
    analyzer.available = False
    start(client, status=503)
    assert client.get('/api/orders').json()["orders"] == []
    with client.app.state.store.connect() as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE name='autonomous_missions'").fetchone() is None


def test_failure_retains_full_planned_denominator_and_no_false_success(mission_client):
    client, analyzer, *_ = mission_client
    analyzer.error = RuntimeError("synthetic failure")
    run = wait(client, start(client)["id"])
    assert run["status"] == "failed" and run["planned_checks"] == 4 and run["planned_cases"] == 3
    assert [c["status"] for c in run["cases"]] == ["failed", "not_started", "not_started"]
    assert not run["cases"][0]["checks"] and run["cases"][0]["finding"] is None
    assert run["cases"][0]["steps"][-1]["status"] == "failed"
    response = client.get(f'/api/autonomous-missions/{run["id"]}/evidence.zip')
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        saved = json.loads(z.read("mission.json"))["run"]["cases"][0]
        assert saved["snapshot"] is None and saved["prepared_snapshot"]["photos"]
        assert len([n for n in z.namelist() if n.startswith("photos/")]) == 1
        assert b"No completed model finding" in z.read("index.html")


def test_tampered_public_source_is_not_sent_to_model(mission_client):
    client, analyzer, root, catalog, *_ = mission_client
    path = root / next(s for s in catalog if s["sample_id"] == "mixed-screws")["image"]
    path.write_bytes(b"bad source")
    run = wait(client, start(client)["id"])
    assert run["status"] == "failed" and len(analyzer.calls) == 0


def test_non_mlx_observation_cannot_be_promoted_to_mission_evidence(mission_client):
    client, analyzer, *_ = mission_client
    fake = analyzer.observe

    def wrong_backend(*args):
        result = fake(*args)
        result["backend"] = "test"
        return result
    analyzer.observe = wrong_backend
    run = wait(client, start(client, "quantity")["id"])
    assert run["status"] == "failed" and not run["cases"][0]["checks"]


def test_cancel_waits_for_inflight_result_and_skips_next_tools(mission_client):
    client, analyzer, *_ = mission_client
    analyzer.release.clear()
    try:
        run = start(client)
        assert analyzer.started.wait(2)
        start(client, "all", "another-mission-key", status=503)
        result = client.post(f'/api/autonomous-missions/{run["id"]}/cancel', json={"confirmed": True})
        assert result.json()["run"]["status"] == "running" and result.json()["run"]["cancel_requested"]
        assert client.get('/api/health').json()["inference"]["busy"]
    finally:
        analyzer.release.set()
    final = wait(client, run["id"])
    assert final["status"] == "cancelled" and len(analyzer.calls) == 1
    assert final["cases"][1]["status"] == "not_started" and len(final["cases"][0]["checks"]) == 1


def test_shutdown_is_interrupted_unknown_time_and_not_auto_resumed(mission_setup):
    app, analyzer, *_ = mission_setup
    analyzer.release.clear()
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            run = start(client)
            assert analyzer.started.wait(2)
        final = app.state.autonomous_missions.get(run["id"])
        assert final["status"] == "interrupted" and final["elapsed_ms"] is None
    finally:
        analyzer.release.set()
        assert analyzer.finished.wait(2)
    with TestClient(app) as client:
        before = len(analyzer.calls)
        assert client.get(f'/api/autonomous-missions/{run["id"]}').json()["run"]["status"] == "interrupted"
        assert start(client)["id"] == run["id"] and len(analyzer.calls) == before


def test_archive_has_saved_snapshots_hashes_photos_and_later_version_audit(mission_client):
    client, *_ = mission_client
    run = wait(client, start(client, "quantity")["id"])
    case = run["cases"][0]
    body = {"expected_revision": 1, "requirements": {"bolt": 1, "nut": 0, "washer": 0, "bracket": 0}, "instruction": "synthetic later change"}
    revised = client.post(f'/api/orders/{case["order_id"]}/revise', json=body)
    assert revised.status_code == 200, revised.text
    response = client.get(f'/api/autonomous-missions/{run["id"]}/evidence.zip')
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        manifest = json.loads(z.read('SHA256.json'))
        for row in manifest['files']:
            raw = z.read(row['path'])
            assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256']
        data = json.loads(z.read('mission.json'))["run"]
        saved = data['cases'][0]
        assert saved['snapshot']['revision'] == 1 and saved['live_binding']['status'] == 'historical'
        assert saved['snapshot']['requirements']['bolt'] == 2
        assert b'0 humans' in z.read('index.html')


def test_image_tampering_prevents_evidence_export(mission_client):
    client, *_ = mission_client
    run = wait(client, start(client, "quantity")["id"])
    photo = run['cases'][0]['snapshot']['photos'][-1]
    client.app.state.store.photo_path(photo['id']).write_bytes(b'tampered')
    assert client.get(f'/api/autonomous-missions/{run["id"]}/evidence.zip').status_code == 409


def document(client, image_bytes):
    body = {"title": "Synthetic operator goal", "requirements": dict(CASES[0]["bom"]),
            "source_note": "Synthetic declared input; no actual operator study", "confirmed_digital_only": True}
    response = client.post("/api/photo-documents", data={"metadata": json.dumps(body)},
                           files={"photo": ("fixture.png", image_bytes(6), "image/png")})
    assert response.status_code == 201, response.text
    return response.json()["order"]


def order_request(order, key="synthetic-bound-goal-01"):
    return {"scenario": "order", "request_key": key, "order_id": order["id"],
            "expected_revision": order["revision"], "expected_evidence_epoch": order["evidence_epoch"],
            "expected_photo_id": order["photos"][-1]["id"]}


def test_own_document_goal_runs_one_fresh_check_preserves_bom_and_declared_source(mission_client, image_bytes):
    client, analyzer, *_ = mission_client
    order = document(client, image_bytes)
    response = client.post("/api/autonomous-missions", json=order_request(order))
    assert response.status_code == 202, response.text
    run = wait(client, response.json()["run"]["id"])
    case = run["cases"][0]
    assert run["status"] == "completed" and run["planned_checks"] == len(analyzer.calls) == 1
    assert case["order_id"] == order["id"] and case["snapshot"]["requirements"] == order["requirements"]
    assert case["snapshot"]["document_source"] == order["document_source"]
    assert case["snapshot"]["revision"] == 1 and run["purpose"] == "machine_assistance"
    assert case["steps"][0]["tool"] == "verify_bound_order" and case["live_binding"]["status"] == "current"
    assert run["human_participants"] == run["physical_completions"] == 0
    assert len(client.get('/api/orders').json()["orders"]) == 1
    assert client.post('/api/autonomous-missions', json=order_request(order)).json()["replayed"] is True
    assert len(analyzer.calls) == 1


@pytest.mark.parametrize("field,value", [("expected_revision", 2), ("expected_evidence_epoch", 99),
                                      ("expected_photo_id", "stale_photo")])
def test_stale_goal_binding_rejected_before_any_model_call(mission_client, image_bytes, field, value):
    client, analyzer, *_ = mission_client
    body = order_request(document(client, image_bytes)); body[field] = value
    assert client.post('/api/autonomous-missions', json=body).status_code == 409
    assert not analyzer.calls and not client.get('/api/autonomous-missions').json()["runs"]


def test_physical_order_cannot_become_digital_agent_goal(mission_client, image_bytes):
    client, analyzer, *_ = mission_client
    order = client.post('/api/orders', json={"title": "Synthetic physical", "requirements": CASES[0]["bom"]}).json()["order"]
    body = {**order_request({**order, "photos": [{"id": "physical-photo"}]}), "expected_evidence_epoch": 0}
    assert client.post('/api/autonomous-missions', json=body).status_code == 409
    assert not analyzer.calls


def test_accepted_goal_changed_before_worker_fails_without_inference(mission_client, image_bytes):
    client, analyzer, *_ = mission_client
    order = document(client, image_bytes)
    missions = client.app.state.autonomous_missions
    original = missions._execute

    async def change_then_execute(run):
        missions.store.revise(order["id"], {"bolt": 1, "nut": 0, "washer": 0, "bracket": 0}, "synthetic concurrent edit", 1)
        await original(run)
    missions._execute = change_then_execute
    response = client.post('/api/autonomous-missions', json=order_request(order))
    run = wait(client, response.json()["run"]["id"])
    assert run["status"] == "failed" and not analyzer.calls and run["planned_checks"] == 1
    assert run["cases"][0]["snapshot"] is None


@pytest.mark.parametrize("body", [{"scenario": "order", "request_key": "bound-goal"},
    {"scenario": "all", "request_key": "bound-goal", "order_id": "ord_something"},
    {"scenario": "order", "request_key": "bound-goal", "order_id": "ord_something",
     "expected_revision": True, "expected_evidence_epoch": 0, "expected_photo_id": "photo"}])
def test_goal_schema_cannot_omit_binding_or_override_demonstration(mission_client, body):
    client, analyzer, *_ = mission_client
    assert client.post('/api/autonomous-missions', json=body).status_code == 422 and not analyzer.calls


def test_runtime_change_makes_saved_findings_historical(mission_client):
    client, _analyzer, _root, _catalog, identity = mission_client
    run = wait(client, start(client, "quantity")["id"])
    identity["image_max_side"] = 1024
    after = client.get(f'/api/autonomous-missions/{run["id"]}').json()['run']
    assert after['cases'][0]['live_binding']['status'] == 'historical'
    assert after['runtime_identity']['image_max_side'] == 1536


def test_running_export_and_false_cancel_are_rejected(mission_client):
    client, analyzer, *_ = mission_client
    analyzer.release.clear()
    try:
        run = start(client, "quantity")
        assert analyzer.started.wait(2)
        assert client.get(f'/api/autonomous-missions/{run["id"]}/evidence.zip').status_code == 409
        assert client.post(f'/api/autonomous-missions/{run["id"]}/cancel', json={"confirmed": 1}).status_code == 422
    finally:
        analyzer.release.set()
    wait(client, run['id'])
