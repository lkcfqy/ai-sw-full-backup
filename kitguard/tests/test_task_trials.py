"""Synthetic engineering tests only; these are not users, field results, or inference evidence."""
import copy
import json
from collections import Counter
from types import SimpleNamespace

import pytest

from kitguard.task_trial_api import task_trial_router
from kitguard.task_trials import METHODS, SCENARIOS, TaskTrials, allocation

IDENTITY = {"repo_id": "SYNTHETIC-unit-fixture", "revision": "fixture-revision",
            "observer_protocol_sha256": "f"*64, "observation_mode": "unit-fixture", "image_max_side": 1200}


@pytest.fixture
def trials(client):
    recorder = getattr(client.app.state, "task_trials", None)
    if recorder is None:
        recorder = TaskTrials(client.app.state.store, lambda: IDENTITY)
        client.app.state.task_trials = recorder
        client.app.include_router(task_trial_router(recorder))
    recorder.runtime_provider = lambda: copy.deepcopy(IDENTITY)
    return recorder


def create(client, scale="pilot9"):
    r = client.post("/api/task-trials", json={"title": "SYNTHETIC ENGINEERING ONLY", "scale": scale,
                    "source_kind": "engineering_fixture",
                    "participant_codes": ["fixture-A", "fixture-B", "fixture-C"], "host_code": "fixture-host",
                    "capture_session": "NO-REAL-PEOPLE", "source_declaration": "Generated fixtures, no physical validation",
                    "consent_confirmed": False, "real_source_confirmed": False})
    assert r.status_code == 201, r.text
    return r.json()


def call(client, batch, token, action, body=None, task=None):
    path = f'/api/task-trials/{batch["id"]}' + (f'/tasks/{task["id"]}' if task else "") + (f"/{action}" if action else "")
    headers = {"X-Trial-Token": token}
    return client.get(path, headers=headers) if body is None else client.post(path, headers=headers, json=body)


def setup(client, access, task):
    response = call(client, access["batch"], access["host_token"], "setup", {
        "counts": task["planned_initial_counts"], "counts_repeat": task["planned_initial_counts"],
        "independent_confirmed": True, "note": "Synthetic fixture setup, not a person"}, task)
    assert response.status_code == 200, response.text


def frozen(client, trials, scale="pilot9"):
    access = create(client, scale)
    r = call(client, access["batch"], access["host_token"], "freeze", {"confirmed": True})
    assert r.status_code == 200, r.text
    access["batch"] = r.json()["batch"]
    return access


def begin(client, access, task):
    setup(client, access, task)
    r = call(client, access["batch"], access["participant_tokens"][task["participant_code"]], "start", {
        "consent_confirmed": True, "fresh_setup_confirmed": True}, task)
    assert r.status_code == 200, r.text
    return next(t for t in r.json()["batch"]["tasks"] if t["id"] == task["id"])


def participant_call(client, access, task, action, body):
    return call(client, access["batch"], access["participant_tokens"][task["participant_code"]], action, body, task)


def submit(client, access, task, outcome="completed", note=""):
    return participant_call(client, access, task, "submit", {"outcome": outcome, "takeover": False, "note": note})


def review(client, access, task, truth):
    start = call(client, access["batch"], access["host_token"], "review-start", {"confirmed": True}, task)
    assert start.status_code == 200, start.text
    result = call(client, access["batch"], access["host_token"], "review", {"counts": truth, "counts_repeat": truth,
                  "reviewer_code": "fixture-host", "independent_confirmed": True,
                  "unchanged_since_submission_confirmed": True, "note": "No physical claim"}, task)
    assert result.status_code == 200, result.text
    return result.json()["batch"]


@pytest.mark.parametrize("scale,total", [("pilot9", 9), ("study27", 27)])
def test_allocation_balances_methods_scenarios_and_participants(scale, total):
    tasks = allocation(["A", "B", "C"], scale)
    assert len(tasks) == total and len({t["id"] for t in tasks}) == total
    assert Counter(t["method"] for t in tasks) == {m: total//3 for m in METHODS}
    assert Counter((t["method"], t["scenario"]) for t in tasks) == {(m, s): total//9 for m in METHODS for s in SCENARIOS}
    assert len({tuple(sorted(Counter(t["variant"] for t in tasks if t["method"] == m).items())) for m in METHODS}) == 1
    for participant in ["A", "B", "C"]:
        selected = [t for t in tasks if t["participant_code"] == participant]
        assert Counter(t["method"] for t in selected) == {m: total//9 for m in METHODS}
        assert Counter(t["scenario"] for t in selected) == {s: total//9 for s in SCENARIOS}
        if scale == "study27":
            assert Counter((t["method"], t["scenario"]) for t in selected) == {(m, s): 1 for m in METHODS for s in SCENARIOS}


def test_participant_access_hides_truth_and_future_bom_no_precreated_orders(client, trials):
    access = frozen(client, trials)
    view = call(client, access["batch"], access["participant_tokens"]["fixture-A"], "").json()["batch"]
    assert len(view["tasks"]) == 3
    for forbidden in ('"planned_initial_counts":', '"initial_bom":', '"target_bom":', '"setup":', '"_host_token_sha256":'):
        assert forbidden not in json.dumps(view)
    assert client.app.state.store.list() == []
    assert call(client, access["batch"], "invalid-token-long-enough", "").status_code == 403
    assert call(client, access["batch"], access["participant_tokens"]["fixture-A"], "freeze", {"confirmed": True}).status_code == 403
    task = access["batch"]["tasks"][0]
    setup(client, access, task)
    assert call(client, access["batch"], access["host_token"], "start", {"consent_confirmed": True,"fresh_setup_confirmed": True}, task).status_code == 403
    assert call(client, access["batch"], access["participant_tokens"]["fixture-B"], "start", {"consent_confirmed": True,"fresh_setup_confirmed": True}, task).status_code == 403


@pytest.mark.parametrize("field,value", [("consent_confirmed", 1), ("consent_confirmed", "true"), ("real_source_confirmed", False)])
def test_explicit_consent_and_sources_are_required(client, trials, field, value):
    body = {"title": "Fixture", "scale": "pilot9", "participant_codes": ["A", "B", "C"], "host_code": "H",
            "capture_session": "fixture", "source_declaration": "fixture", "consent_confirmed": True, "real_source_confirmed": True}
    body[field] = value
    assert client.post("/api/task-trials", json=body).status_code == 422


def test_reserved_host_participant_code_cannot_escalate_role(client, trials):
    body = {"title": "Role collision fixture", "scale": "pilot9", "participant_codes": ["host", "B", "C"],
            "host_code": "H", "capture_session": "fixture", "source_declaration": "synthetic fixture",
            "consent_confirmed": True, "real_source_confirmed": True}
    assert client.post("/api/task-trials", json=body).status_code == 422


def test_engineering_source_is_explicit_and_never_physical_verification(client, trials):
    access = create(client)
    assert access["batch"]["source_kind"] == "engineering_fixture"
    assert access["batch"]["real_source_confirmed"] is False
    assert access["batch"]["physical_verified"] is access["batch"]["participant_identity_verified"] is False


def test_setup_rejects_bool_counts_and_mismatched_second_pass(client, trials):
    access = frozen(client, trials)
    task = access["batch"]["tasks"][0]
    body = {"counts": copy.deepcopy(task["planned_initial_counts"]), "counts_repeat": task["planned_initial_counts"],
            "independent_confirmed": True}
    body["counts"]["bolt"] = True
    assert call(client, access["batch"], access["host_token"], "setup", body, task).status_code == 422
    body["counts"]["bolt"] = 99
    assert call(client, access["batch"], access["host_token"], "setup", body, task).status_code == 422


def test_server_timer_stops_at_submission_audit_time_separate(client, trials, monkeypatch):
    import kitguard.task_trials as module
    clock = [100.0]
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    access = frozen(client, trials)
    task = access["batch"]["tasks"][0]
    begin(client, access, task)
    clock[0] = 130.0
    assert participant_call(client, access, task, "observe", {"counts": task["target_bom"]}).status_code == 200
    clock[0] = 160.0
    assert submit(client, access, task).status_code == 200
    clock[0] = 200.0
    assert call(client, access["batch"], access["host_token"], "review-start", {"confirmed": True}, task).status_code == 200
    clock[0] = 230.0
    r = call(client, access["batch"], access["host_token"], "review", {"counts": task["target_bom"],
             "counts_repeat": task["target_bom"], "reviewer_code": "fixture-host", "independent_confirmed": True,
             "unchanged_since_submission_confirmed": True}, task)
    saved = r.json()["batch"]["tasks"][0]
    assert saved["elapsed_ms"] == 60000 and saved["review"]["review_elapsed_ms"] == 30000
    assert submit(client, access, task).status_code == 409
    assert client.app.state.store.list() == []  # Manual never pretends to call the AI path.


def test_rules_differences_current_revision_and_no_silent_change(client, trials):
    access = frozen(client, trials)
    task = access["batch"]["tasks"][3]  # Participant B first: rules, revision.
    assert (task["method"], task["scenario"]) == ("rules", "revision")
    begin(client, access, task)
    assert participant_call(client, access, task, "reveal-change", {"confirmed": True}).status_code == 409
    observed = participant_call(client, access, task, "observe", {"counts": task["initial_bom"]})
    assert observed.json()["batch"]["tasks"][0]["observations"][-1]["matches"]
    assert submit(client, access, task).status_code == 409
    assert participant_call(client, access, task, "reveal-change", {"confirmed": True}).status_code == 200
    assert submit(client, access, task).status_code == 409
    observed = participant_call(client, access, task, "observe", {"counts": task["initial_bom"]}).json()
    assert not observed["batch"]["tasks"][0]["observations"][-1]["matches"]
    assert sum(observed["batch"]["tasks"][0]["observations"][-1]["difference"].values()) == -1
    # A participant can mistakenly claim completion. Independent review must record the error.
    assert submit(client, access, task).status_code == 200
    review(client, access, task, task["initial_bom"])
    closed = call(client, access["batch"], access["host_token"], "close", {"confirmed": True}).json()["batch"]
    assert closed["report"]["methods"]["rules"]["wrong"] == 1


def test_not_started_failed_unreviewed_are_all_in_final_denominator(client, trials):
    access = frozen(client, trials)
    manual, rules, ai = (access["batch"]["tasks"][i] for i in (0, 3, 6))
    begin(client, access, manual)
    participant_call(client, access, manual, "observe", {"counts": manual["target_bom"]})
    assert submit(client, access, manual).status_code == 200
    begin(client, access, rules)
    assert submit(client, access, rules, "failed", "Synthetic inability to finish").status_code == 200
    begin(client, access, ai)
    assert submit(client, access, ai, "abandoned", "Synthetic withdrawal").status_code == 200
    closed = call(client, access["batch"], access["host_token"], "close", {"confirmed": True}).json()["batch"]
    report = closed["report"]["methods"]
    assert report["manual"]["unreviewed"] == report["rules"]["failed"] == report["kitguard"]["abandoned"] == 1
    for value in report.values():
        assert value["planned"] == sum(value[k] for k in ["correct", "wrong", "unreviewed", "failed", "abandoned", "interrupted", "not_started"]) == 3
        assert value["not_started"] == 2
    payload = call(client, access["batch"], access["host_token"], "export").json()
    assert payload["kind"] == "kitguard_full_task_exploratory" and len(payload["batch"]["tasks"]) == 9
    assert '"_host_token_sha256"' not in json.dumps(payload)
    assert call(client, access["batch"], access["participant_tokens"]["fixture-A"], "export").status_code == 403


def test_cannot_skip_order_restart_or_overlap_active_tasks(client, trials):
    access = frozen(client, trials)
    first, second, other = (access["batch"]["tasks"][i] for i in (0, 1, 3))
    setup(client, access, second)
    r = participant_call(client, access, second, "start", {"consent_confirmed": True,"fresh_setup_confirmed": True})
    assert r.status_code == 409
    begin(client, access, first)
    setup(client, access, other)
    assert participant_call(client, access, other, "start", {"consent_confirmed": True,"fresh_setup_confirmed": True}).status_code == 409
    assert call(client, access["batch"], access["host_token"], "close", {"confirmed": True}).status_code == 409
    assert submit(client, access, first, "failed").status_code == 422
    assert submit(client, access, first, "failed", "fixture failure").status_code == 200
    assert participant_call(client, access, first, "start", {"consent_confirmed": True,"fresh_setup_confirmed": True}).status_code == 409


def test_restart_preserves_partial_actions_and_unknown_time(client, trials):
    access = frozen(client, trials)
    task = access["batch"]["tasks"][0]
    begin(client, access, task)
    participant_call(client, access, task, "actions", {"kind": "moved_parts", "note": "Fixture, no real action"})
    replacement = TaskTrials(trials.store, lambda: IDENTITY)
    replacement.recover_interrupted()
    saved = replacement.get(access["batch"]["id"], access["host_token"])["tasks"][0]
    assert saved["status"] == "interrupted" and saved["elapsed_ms"] is None
    assert any(e["kind"] == "participant_declared_action" for e in saved["events"])
    assert submit(client, access, task).status_code == 409


def test_runtime_drift_blocks_start_but_allows_honest_failure(client, trials):
    access = frozen(client, trials)
    task = access["batch"]["tasks"][0]
    begin(client, access, task)
    trials.runtime_provider = lambda: {**IDENTITY, "revision": "changed"}
    participant_call(client, access, task, "observe", {"counts": task["target_bom"]})
    assert submit(client, access, task).status_code == 409
    assert submit(client, access, task, "failed", "Configuration changed").status_code == 200


def test_double_counts_locked_and_participant_cannot_review_own_work(client, trials):
    access = frozen(client, trials)
    task = access["batch"]["tasks"][0]
    bad = {**task["planned_initial_counts"], "bolt": 99}
    body = {"counts": bad, "counts_repeat": bad, "independent_confirmed": True}
    assert call(client, access["batch"], access["host_token"], "setup", body, task).status_code == 422
    begin(client, access, task)
    assert call(client, access["batch"], access["host_token"], "setup", body, task).status_code == 409
    submit(client, access, task, "failed", "fixture")
    assert participant_call(client, access, task, "review-start", {"confirmed": True}).status_code == 403
    call(client, access["batch"], access["host_token"], "review-start", {"confirmed": True}, task)
    body.update(reviewer_code=task["participant_code"], unchanged_since_submission_confirmed=True)
    assert call(client, access["batch"], access["host_token"], "review", body, task).status_code == 422


def ai_fixture(client, trials, upload):
    access = frozen(client, trials)
    task = access["batch"]["tasks"][6]  # first C: KitGuard missing.
    started = begin(client, access, task)
    order = trials.store.get(started["order_id"])
    photo = upload(order).json()["photo"]
    checked = client.post(f'/api/orders/{order["id"]}/inspect', json={"photo_id": photo["id"], "expected_revision": 1})
    assert checked.status_code == 200, checked.text
    check = checked.json()["check"]
    complete = client.post(f'/api/orders/{order["id"]}/complete', json={"check_id": check["id"], "expected_revision": 1,
                            "confirmed": True, "idempotency_key": "fixture-completion"})
    assert complete.status_code == 200, complete.text
    return access, task, order, photo


def test_ai_test_backend_rejected_but_failed_trial_keeps_actual_checks(client, trials, upload):
    access, task, _order, _ = ai_fixture(client, trials, upload)
    assert submit(client, access, task).status_code == 409
    assert submit(client, access, task, "failed", "Injected test backend; not field AI").status_code == 200
    saved = trials.get(access["batch"]["id"], access["host_token"])["tasks"][6]
    assert saved["evidence"]["checks"][0]["backend"] == "test"
    assert saved["evidence"]["completions"] and saved["status"] == "failed"


def synthetic_real_schema(trials, order):
    """Schema fixture only. This never constitutes actual MLX/field validation."""
    with trials.store.transaction(order["id"]) as (_, saved):
        for check in saved["checks"]:
            check.update(backend="mlx", runtime_identity=copy.deepcopy(IDENTITY))
        saved["latest_check"].update(backend="mlx", runtime_identity=copy.deepcopy(IDENTITY))


def test_ai_complete_uses_server_order_snapshot_and_export_detects_file_change(client, trials, upload):
    access, task, order, photo = ai_fixture(client, trials, upload)
    synthetic_real_schema(trials, order)
    assert submit(client, access, task).status_code == 200
    review(client, access, task, task["target_bom"])
    call(client, access["batch"], access["host_token"], "close", {"confirmed": True})
    exported = call(client, access["batch"], access["host_token"], "export")
    assert exported.status_code == 200, exported.text
    saved = exported.json()["batch"]["tasks"][6]
    assert saved["evidence"]["id"] == order["id"] and saved["evidence"]["photos"][0]["id"] == photo["id"]
    trials.store.photo_path(photo["id"]).write_bytes(b"CHANGED FIXTURE")
    assert call(client, access["batch"], access["host_token"], "export").status_code == 409


@pytest.mark.parametrize("kind", ["public_source", "demo", "duplicate", "incomplete"])
def test_ai_rejects_public_demo_duplicate_or_missing_completion(client, trials, upload, kind):
    from kitguard.public_demo_catalog import CATALOG
    access, task, order, photo = ai_fixture(client, trials, upload)
    synthetic_real_schema(trials, order)
    if kind == "duplicate":
        other = trials.store.create("other synthetic", order["requirements"])
        with trials.store.transaction(other["id"]) as (_, saved):
            saved["photos"].append(copy.deepcopy(photo))
    else:
        with trials.store.transaction(order["id"]) as (_, saved):
            if kind == "public_source":
                saved["photos"][0]["source_sha256"] = CATALOG[1]["source_sha256"]
            elif kind == "demo":
                saved["demo_source"] = {"synthetic": "public"}
            else:
                saved["completions"] = []
    assert submit(client, access, task).status_code == 409


def test_host_can_close_unstarted_plan_preserving_all_slots(client, trials):
    access = create(client, "study27")
    result = call(client, access["batch"], access["host_token"], "close", {"confirmed": True})
    assert result.status_code == 200
    assert all(m["not_started"] == m["planned"] == 9 for m in result.json()["batch"]["report"]["methods"].values())


def test_native_export_attachment_requires_closed_host_and_preserves_payload(client, trials):
    access = create(client)
    path = f'/api/task-trials/{access["batch"]["id"]}/export-download'
    assert client.post(path, data={"token": access["host_token"]}).status_code == 409
    call(client, access["batch"], access["host_token"], "close", {"confirmed": True})
    result = client.post(path, data={"token": access["host_token"]}, headers={"Origin": "http://testserver"})
    assert result.status_code == 200, result.text
    assert result.headers["content-disposition"].endswith('-full-task.json"')
    assert result.headers["cache-control"] == "no-store"
    assert result.headers["pragma"] == "no-cache" and result.headers["x-content-type-options"] == "nosniff"
    assert result.json() == call(client, access["batch"], access["host_token"], "export").json()
    assert access["host_token"] not in result.text
    assert not result.request.url.query
    assert client.post(path, data={"token": access["participant_tokens"]["fixture-A"]}).status_code == 403
    assert client.post(path, data={"token": "invalid-token-long-enough"}).status_code == 403
    assert client.get(path).status_code == 405
    assert client.post(path).status_code == 422
    assert client.post(path, data={"token": access["host_token"], "extra": "not allowed"}).status_code == 422


def test_private_access_attachment_checks_all_keys_without_server_file_or_db_write(client, trials):
    from urllib.parse import parse_qs, urlparse
    access = create(client)
    batch_id = access["batch"]["id"]
    with trials.store.connect() as db:
        before = trials._get(db, batch_id)
    files_before = {p.relative_to(trials.store.directory) for p in trials.store.directory.rglob("*") if p.is_file()}
    path = f"/api/task-trials/{batch_id}/access-download"
    result = client.post(path, data={"token": access["host_token"],
                         "participant_tokens": json.dumps(access["participant_tokens"])},
                         headers={"Origin": "http://testserver"})
    assert result.status_code == 200, result.text
    assert result.headers["content-disposition"].endswith('-PRIVATE-access.json"')
    assert result.headers["cache-control"] == "no-store" and result.headers["pragma"] == "no-cache"
    saved = result.json()
    assert parse_qs(urlparse(saved["host"]).fragment) == {"batch": [batch_id], "token": [access["host_token"]]}
    for participant, link in saved["participants"].items():
        parsed = urlparse(link)
        assert parsed.netloc == "testserver" and parsed.path == "/static/trials.html" and not parsed.query
        assert parse_qs(parsed.fragment)["token"] == [access["participant_tokens"][participant]]
    with trials.store.connect() as db:
        assert trials._get(db, batch_id) == before
    assert {p.relative_to(trials.store.directory) for p in trials.store.directory.rglob("*") if p.is_file()} == files_before
    assert not result.request.url.query


@pytest.mark.parametrize("mutation,status", [("participant_host", 403), ("invalid_host", 403),
                                             ("missing_participant", 422), ("swapped_tokens", 403),
                                             ("invalid_token", 403), ("not_json", 422), ("extra_field", 422)])
def test_private_attachment_cannot_reissue_or_mix_credentials(client, trials, mutation, status):
    access = create(client)
    participant_tokens = copy.deepcopy(access["participant_tokens"])
    token = access["host_token"]
    if mutation == "participant_host":
        token = participant_tokens["fixture-A"]
    elif mutation == "invalid_host":
        token = "invalid-host-token-long-enough"
    elif mutation == "missing_participant":
        participant_tokens.pop("fixture-C")
    elif mutation == "swapped_tokens":
        participant_tokens["fixture-A"], participant_tokens["fixture-B"] = participant_tokens["fixture-B"], participant_tokens["fixture-A"]
    elif mutation == "invalid_token":
        participant_tokens["fixture-C"] = "invalid-participant-token-long-enough"
    body = {"token": token, "participant_tokens": "not-json" if mutation == "not_json" else json.dumps(participant_tokens)}
    if mutation == "extra_field":
        body["redirect"] = "https://example.invalid"
    result = client.post(f'/api/task-trials/{access["batch"]["id"]}/access-download', data=body)
    assert result.status_code == status, result.text
    assert "content-disposition" not in result.headers
    assert access["host_token"] not in result.text


@pytest.mark.parametrize("action", ["access-download", "export-download"])
@pytest.mark.parametrize("origin", ["https://unrelated.invalid", "null"])
def test_attachment_form_downloads_keep_existing_same_origin_boundary(client, trials, action, origin):
    access = create(client)
    body = {"token": access["host_token"]}
    if action == "access-download":
        body["participant_tokens"] = json.dumps(access["participant_tokens"])
    result = client.post(f'/api/task-trials/{access["batch"]["id"]}/{action}', data=body,
                         headers={"Origin": origin})
    assert result.status_code == 403
    assert "content-disposition" not in result.headers and access["host_token"] not in result.text


def test_invalid_download_forms_never_reflect_credential_body(client, trials):
    from urllib.parse import urlencode
    access = create(client)
    path = f'/api/task-trials/{access["batch"]["id"]}/access-download'
    missing = client.post(path, data={"token": access["host_token"]})
    assert missing.status_code == 422 and access["host_token"] not in missing.text
    duplicate = client.post(path, content=urlencode([("token", access["host_token"]), ("token", access["host_token"]),
                            ("participant_tokens", json.dumps(access["participant_tokens"]))]),
                            headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert duplicate.status_code == 422 and access["host_token"] not in duplicate.text
