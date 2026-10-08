"""Synthetic contract tests only. No people or real inference are measured here."""
import copy
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from kitguard.digital_task_trials import CASES, PROTOCOL, allocation


@pytest.fixture
def digital_client(tmp_path, image_bytes, analyzer, monkeypatch):
    from kitguard import app as app_module
    from kitguard import digital_task_trials as module
    from kitguard.app import create_app
    from kitguard.public_demo_catalog import CATALOG

    catalog = copy.deepcopy(CATALOG)
    root = tmp_path / "synthetic-public-photos"
    for index, row in enumerate(catalog):
        content = image_bytes(index)
        path = root / row["image"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        row["source_sha256"] = hashlib.sha256(content).hexdigest()
    monkeypatch.setattr(app_module, "PUBLIC_DEMOS", catalog)
    monkeypatch.setattr(module, "CATALOG", catalog)
    with TestClient(create_app(data_dir=tmp_path / "data", analyzer=analyzer, demo_dataset_root=root),
                    raise_server_exceptions=False) as client:
        yield client


def create(client, index=0, purpose="engineering_rehearsal"):
    response = client.post("/api/digital-task-trials", json={"participant_code": "SYNTHETIC-NO-HUMAN",
            "purpose": purpose, "allocation_index": index, "consent_confirmed": purpose == "self_reported_human"})
    assert response.status_code == 201, response.text
    result = response.json()
    return result["batch"], {"X-Digital-Trial-Token": result["token"]}


def action(client, batch, headers, task, name, body=None, expected=200):
    response = client.post(f'/api/digital-task-trials/{batch["id"]}/tasks/{task["id"]}/{name}',
                           headers=headers, json={"confirmed": True} if body is None else body)
    assert response.status_code == expected, response.text
    return response.json().get("batch") if expected == 200 else response


def final_answer(task, revision=None):
    case = next(c for c in CASES if c["key"] == task["case_key"])
    bom = case["changed_bom"] or case["initial_bom"]
    return {"counts": case["truth"], "revision": revision or (2 if case["changed_bom"] else 1),
            "conclusion": "matched" if bom == case["truth"] else "mismatch"}


def inspect(client, task):
    binding = task["binding"]
    response = client.post(f'/api/orders/{task["order_id"]}/inspect', json={
        "photo_id": binding["photo_id"], "expected_revision": binding["revision"]})
    assert response.status_code == 200, response.text
    return response.json()["check"]


def test_allocation_is_counterbalanced_and_six_tasks_per_person():
    for index in range(6):
        tasks = allocation("SYNTHETIC", index)
        assert len(tasks) == 6
        assert tasks[0]["method"] == ("manual" if index % 2 == 0 else "kitguard")
        assert len({(t["method"], t["case_key"]) for t in tasks}) == 6
        assert tasks[0]["case_key"] == CASES[index % 3]["key"]


def test_fixed_author_labels_match_prior_protocol():
    from pathlib import Path
    source = json.loads((Path(__file__).parents[1] / "docs/v0.3/OWL_DEVELOPMENT_PROTOCOL.json").read_text())
    labels = {}

    def visit(value):
        if isinstance(value, dict):
            if "ground_truth" in value:
                labels[value["id"]] = value["ground_truth"]
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(source)
    from kitguard.public_demo_catalog import CATALOG
    for case in CASES:
        spec = next(s for s in CATALOG if s["sample_id"] == case["sample_id"])
        assert case["truth"] == labels[spec["source_case_id"]]


@pytest.mark.parametrize("field,value", [("consent_confirmed", True), ("consent_confirmed", 1),
                                         ("allocation_index", "0"), ("participant_code", "real name"),
                                         ("physical_completion", True)])
def test_strict_creation_cannot_promote_rehearsal(digital_client, field, value):
    body = {"participant_code": "SYNTHETIC", "purpose": "engineering_rehearsal",
            "allocation_index": 0, "consent_confirmed": False, field: value}
    assert digital_client.post("/api/digital-task-trials", json=body).status_code == 422


def test_truth_hidden_access_required_and_planned_denominator(digital_client):
    batch, headers = create(digital_client)
    assert all(set(case) == {"key"} for case in batch["protocol"]["cases"])
    assert batch["report"] is None
    assert all("_case" not in task for task in batch["tasks"]) and "_token_sha256" not in batch
    assert digital_client.get(f'/api/digital-task-trials/{batch["id"]}', headers={
        "X-Digital-Trial-Token": "wrong-token" * 4}).status_code == 403
    assert digital_client.get(f'/api/digital-task-trials/{batch["id"]}/export', headers=headers).status_code == 409
    closed = digital_client.post(f'/api/digital-task-trials/{batch["id"]}/close', headers=headers,
                                 json={"confirmed": True}).json()["batch"]
    assert closed["report"]["methods"]["manual"]["not_started"] == 3
    assert closed["report"]["methods"]["kitguard"]["not_started"] == 3
    assert closed["report"]["completed_self_reported_humans"] == 0
    assert closed["report"]["human_effect_estimate"] is None
    assert closed["protocol"] == json.loads(json.dumps(PROTOCOL))


def test_start_order_one_active_task_and_restart_unknown_duration(digital_client):
    batch, headers = create(digital_client)
    action(digital_client, batch, headers, batch["tasks"][1], "start", expected=409)
    batch = action(digital_client, batch, headers, batch["tasks"][0], "start")
    task = batch["tasks"][0]
    assert task["binding"] and task["started_at"] and task["elapsed_ms"] is None
    action(digital_client, batch, headers, task, "start", expected=409)
    action(digital_client, batch, headers, batch["tasks"][1], "start", expected=409)
    other, other_headers = create(digital_client, 1)
    action(digital_client, other, other_headers, other["tasks"][0], "start", expected=409)
    recorder = digital_client.app.state.digital_trials
    recorder.recover_interrupted()
    reopened = digital_client.get(f'/api/digital-task-trials/{batch["id"]}', headers=headers).json()["batch"]
    assert reopened["tasks"][0]["status"] == "interrupted"
    assert reopened["tasks"][0]["elapsed_ms"] is None


def test_manual_submission_help_and_elapsed_use_server_clock(digital_client, monkeypatch):
    batch, headers = create(digital_client)
    import kitguard.digital_task_trials as module
    clock = [100.0]
    monkeypatch.setattr(module, "monotonic", lambda: clock[0])
    batch = action(digital_client, batch, headers, batch["tasks"][0], "start")
    task = batch["tasks"][0]
    action(digital_client, batch, headers, task, "help")
    clock[0] = 112.25
    batch = action(digital_client, batch, headers, task, "finish", {
        "outcome": "completed", "answer": final_answer(task), "note": ""})
    task = batch["tasks"][0]
    assert task["elapsed_ms"] == 12250 and task["help_opens"] == 1
    action(digital_client, batch, headers, task, "finish", {"outcome": "abandoned", "note": "late"}, expected=409)


def test_manual_ai_contamination_retained_as_ineligible(digital_client):
    batch, headers = create(digital_client)
    batch = action(digital_client, batch, headers, batch["tasks"][0], "start")
    task = batch["tasks"][0]
    inspect(digital_client, task)
    action(digital_client, batch, headers, task, "finish", {"outcome": "completed", "answer": final_answer(task)})
    closed = digital_client.post(f'/api/digital-task-trials/{batch["id"]}/close', headers=headers,
                                 json={"confirmed": True}).json()["batch"]
    assert closed["report"]["methods"]["manual"]["correct"] == 0
    assert closed["report"]["methods"]["manual"]["ineligible"] == 1
    assert len(closed["tasks"][0]["evidence"]["checks"]) == 1


def test_ai_requires_current_check_and_test_backend_not_human(digital_client):
    batch, headers = create(digital_client, 1, "self_reported_human")
    batch = action(digital_client, batch, headers, batch["tasks"][0], "start")
    task = batch["tasks"][0]
    body = {"outcome": "completed", "answer": final_answer(task)}
    action(digital_client, batch, headers, task, "finish", body, expected=409)
    inspect(digital_client, task)
    action(digital_client, batch, headers, task, "finish", body, expected=409)
    action(digital_client, batch, headers, task, "finish", {"outcome": "failed", "note": "Synthetic backend excluded"})


def test_revision_records_first_answer_expires_r1_and_requires_r2(digital_client):
    batch, headers = create(digital_client, 5)  # AI first; rotation starts with revision.
    batch = action(digital_client, batch, headers, batch["tasks"][0], "start")
    task = batch["tasks"][0]
    action(digital_client, batch, headers, task, "reveal-change", expected=409)
    first_check = inspect(digital_client, task)
    action(digital_client, batch, headers, task, "first-answer", {
        "counts": CASES[2]["truth"], "revision": 1, "conclusion": "mismatch"})
    batch = action(digital_client, batch, headers, task, "reveal-change")
    changed = batch["tasks"][0]
    assert changed["binding"]["revision"] == 2
    assert changed["binding"]["photo_sha256"] == task["binding"]["photo_sha256"]
    assert changed["binding"]["photo_id"] != task["binding"]["photo_id"]
    snapshot = digital_client.app.state.store.get(task["order_id"])
    assert snapshot["checks"][0]["id"] == first_check["id"] and not snapshot["checks"][0]["valid"]
    action(digital_client, batch, headers, changed, "finish", {
        "outcome": "completed", "answer": final_answer(changed)}, expected=409)
    inspect(digital_client, changed)
    action(digital_client, batch, headers, changed, "finish", {
        "outcome": "completed", "answer": final_answer(changed, revision=1)})
    closed = digital_client.post(f'/api/digital-task-trials/{batch["id"]}/close', headers=headers,
                                 json={"confirmed": True}).json()["batch"]
    assert closed["report"]["methods"]["kitguard"]["version_errors"] == 1
    assert len(closed["tasks"][0]["evidence"]["checks"]) == 2
    assert closed["tasks"][0]["first_answer"]["check"]["valid"]  # original snapshot preserved
    assert closed["report"]["completed_self_reported_humans"] == 0


def test_external_bom_change_cannot_be_scored_as_assigned_task(digital_client):
    batch, headers = create(digital_client)
    batch = action(digital_client, batch, headers, batch["tasks"][0], "start")
    task = batch["tasks"][0]
    digital_client.app.state.store.revise(task["order_id"], CASES[0]["truth"], "External mutation fixture", 1)
    action(digital_client, batch, headers, task, "finish", {
        "outcome": "completed", "answer": final_answer(task)}, expected=409)
    action(digital_client, batch, headers, task, "finish", {"outcome": "abandoned", "note": "External mutation retained"})


def test_preparation_failure_is_retained_without_active_timer(digital_client, monkeypatch):
    import kitguard.app as module
    monkeypatch.setattr(module, "PUBLIC_DEMOS", [])
    batch, headers = create(digital_client)
    action(digital_client, batch, headers, batch["tasks"][0], "start", expected=404)
    result = digital_client.get(f'/api/digital-task-trials/{batch["id"]}', headers=headers).json()["batch"]
    assert result["tasks"][0]["status"] == "failed"


def test_public_task_never_allows_physical_completion(digital_client):
    batch, headers = create(digital_client)
    batch = action(digital_client, batch, headers, batch["tasks"][0], "start")
    task = batch["tasks"][0]
    assert digital_client.app.state.store.get(task["order_id"])["demo_source"]["physical_completion_allowed"] is False


@pytest.mark.parametrize("answer", [{"counts": None, "revision": 1, "conclusion": "matched"},
                                   {"counts": CASES[0]["truth"], "revision": "1", "conclusion": "mismatch"}])
def test_answer_validation(digital_client, answer):
    batch, headers = create(digital_client)
    batch = action(digital_client, batch, headers, batch["tasks"][0], "start")
    action(digital_client, batch, headers, batch["tasks"][0], "finish", {
        "outcome": "completed", "answer": answer}, expected=422)
