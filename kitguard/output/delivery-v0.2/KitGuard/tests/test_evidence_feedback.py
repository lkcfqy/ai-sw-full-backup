"""Feedback/state integration using synthetic fixtures, not real vision evaluation.

The HTTP calls use the real app and store. Only image observation is a test double;
no result here establishes that a person changed a real physical kit.
"""

import json
from copy import deepcopy

import pytest
from conftest import REQUIREMENTS, FakeAnalyzer
from pydantic import ValidationError


class ContextRecordingAnalyzer(FakeAnalyzer):
    def __init__(self):
        super().__init__()
        self.contexts = []

    def observe_with_context(self, image_path, requirements, references, context):
        self.contexts.append(deepcopy(context))
        return self.observe(image_path, requirements, references)


@pytest.fixture
def analyzer():
    # Overrides the shared fixture for this module; the shared real TestClient uses it.
    return ContextRecordingAnalyzer()


def observe_new_photo(client, upload, order, analyzer, counts, *, seed=0, action="none", issues=None):
    analyzer.result = analyzer.observation(counts, action=action, issues=issues)
    posted = upload(order, seed=seed)
    assert posted.status_code == 201, posted.text
    photo = posted.json()["photo"]
    response = client.post(
        f"/api/orders/{order['id']}/inspect",
        json={"photo_id": photo["id"], "expected_revision": order["revision"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


def trace_by_step(check):
    return {step["step"]: step for step in check["tool_trace"]}


def test_cleared_uncertainty_can_improve_evidence_without_resolving_shortage(client, upload, order, analyzer):
    first = observe_new_photo(
        client,
        upload,
        order,
        analyzer,
        {**REQUIREMENTS, "washer": None},
        action="separate",
        issues=["Overlap"],
    )
    second = observe_new_photo(client, upload, order, analyzer, {**REQUIREMENTS, "washer": 1}, seed=1)
    check = second["check"]
    feedback = check["evidence_feedback"]
    assert check["decision"] == "correct"
    assert second["order"]["status"] == "needs_action"
    assert feedback["outcome"] == "evidence_improved_quantity_mismatch"
    assert feedback["previous_check_id"] == first["check"]["id"]
    assert feedback["previous_photo_id"] == first["check"]["photo_id"]
    assert feedback["resolved_uncertainties"] == ["washer"]
    assert feedback["remaining_uncertainties"] == []
    assert feedback["remaining_mismatches"] == ["washer"]
    assert feedback["physical_action_verified"] is False
    assert check["action"]["kind"] == "add_remove"
    assert next(item for item in check["differences"] if item["part"] == "washer")["delta"] == -1
    assert trace_by_step(check)["choose_next_action"]["decision"] == "correct"
    assert second["order"]["completions"] == []


def test_unchanged_uncertainty_is_not_claimed_resolved(client, upload, order, analyzer):
    counts = {**REQUIREMENTS, "washer": None}
    observe_new_photo(client, upload, order, analyzer, counts, action="separate", issues=["Overlap"])
    second = observe_new_photo(
        client, upload, order, analyzer, counts, seed=1, action="recapture", issues=["Blur"]
    )
    feedback = second["check"]["evidence_feedback"]
    assert second["check"]["decision"] == "recapture"
    assert feedback["outcome"] == "evidence_still_unclear"
    assert feedback["resolved_uncertainties"] == []
    assert feedback["remaining_uncertainties"] == ["washer"]
    assert feedback["physical_action_verified"] is False
    assert second["order"]["status"] != "ready"


def test_adding_wrong_class_preserves_shortage_and_reports_new_excess(client, upload, order, analyzer):
    first = observe_new_photo(client, upload, order, analyzer, {**REQUIREMENTS, "washer": 1})
    assert first["check"]["action"]["kind"] == "add_remove"
    second = observe_new_photo(
        client, upload, order, analyzer, {**REQUIREMENTS, "washer": 1, "nut": 3}, seed=1
    )
    check = second["check"]
    assert check["decision"] == "correct"
    assert check["evidence_feedback"]["outcome"] == "quantity_mismatch_remains"
    assert set(check["evidence_feedback"]["remaining_mismatches"]) == {"nut", "washer"}
    assert check["evidence_feedback"]["observed_changes"] == [{"part": "nut", "before": 2, "after": 3}]
    deltas = {item["part"]: item["delta"] for item in check["differences"]}
    assert deltas["nut"] == 1 and deltas["washer"] == -1
    # Server add/remove instructions and old counts never become visual attention cues.
    assert analyzer.contexts == []


def test_new_ambiguity_cannot_be_filled_from_an_old_clear_count(client, upload, order, analyzer):
    first = observe_new_photo(client, upload, order, analyzer, REQUIREMENTS)
    assert first["check"]["decision"] == "ready"
    second = observe_new_photo(
        client, upload, order, analyzer, {**REQUIREMENTS, "bolt": None}, seed=1, action="recapture"
    )
    assert second["check"]["observed"]["bolt"] is None
    assert second["check"]["decision"] == "recapture"
    assert second["check"]["evidence_feedback"]["remaining_uncertainties"] == ["bolt"]
    assert second["order"]["status"] == "needs_action"


@pytest.mark.parametrize("change", ["revision", "reference"])
def test_revision_or_reference_change_isolates_old_context_and_feedback(
    client, upload, order, analyzer, image_bytes, change
):
    observe_new_photo(
        client,
        upload,
        order,
        analyzer,
        {**REQUIREMENTS, "washer": None},
        action="separate",
        issues=["Overlap"],
    )
    if change == "revision":
        changed = client.post(
            f"/api/orders/{order['id']}/revise",
            json={
                "expected_revision": 1,
                "requirements": {**REQUIREMENTS, "bolt": 1},
                "instruction": "Test revision",
            },
        )
        assert changed.status_code == 200, changed.text
    else:
        changed = client.post(
            f"/api/orders/{order['id']}/references/washer",
            files={"photo": ("synthetic-reference.png", image_bytes(3), "image/png")},
        )
        assert changed.status_code == 201, changed.text
    current = changed.json()["order"]
    second = observe_new_photo(client, upload, current, analyzer, current["requirements"], seed=1)
    assert analyzer.contexts == []
    assert second["check"]["evidence_feedback"] is None
    assert trace_by_step(second["check"])["review_previous_evidence"]["status"] == "not_applicable"
    assert second["check"]["requirements_snapshot"] == current["requirements"]
    assert second["check"]["reference_ids"] == {
        part: pic["id"] for part, pic in current["references"].items()
    }


def test_attention_context_excludes_targets_counts_and_untrusted_instruction_text(
    client, upload, order, analyzer
):
    analyzer.result = analyzer.observation({**REQUIREMENTS, "washer": None}, action="separate")
    secret = "PRIOR_COUNT=2 TARGET=3 ADD_REMOVE_SENTINEL add one washer"
    analyzer.result["action"].update(message=secret, region=[0.1, 0.2, 0.7, 0.8])
    analyzer.result["issues"] = [secret]
    photo = upload(order).json()["photo"]
    first = client.post(
        f"/api/orders/{order['id']}/inspect",
        json={"photo_id": photo["id"], "expected_revision": 1},
    )
    assert first.status_code == 200, first.text
    observe_new_photo(client, upload, order, analyzer, REQUIREMENTS, seed=1)
    assert analyzer.contexts == [
        {
            "previous_action_kind": "separate",
            "uncertain_parts": ["washer"],
            "region": [0.1, 0.2, 0.7, 0.8],
        }
    ]
    assert secret not in json.dumps(analyzer.contexts)
    assert set(analyzer.contexts[0]) == {"previous_action_kind", "uncertain_parts", "region"}


def test_same_photo_reinspection_does_not_claim_new_evidence_feedback(client, upload, order, analyzer):
    first = observe_new_photo(
        client, upload, order, analyzer, {**REQUIREMENTS, "washer": None}, action="recapture"
    )
    analyzer.result = analyzer.observation(REQUIREMENTS)
    second = client.post(
        f"/api/orders/{order['id']}/inspect",
        json={"photo_id": first["check"]["photo_id"], "expected_revision": 1},
    )
    assert second.status_code == 200, second.text
    check = second.json()["check"]
    assert analyzer.contexts == []
    assert check["evidence_feedback"] is None
    assert trace_by_step(check)["review_previous_evidence"]["status"] == "not_applicable"


def test_trace_uses_executed_branch_and_drops_model_injected_success(client, upload, order, analyzer):
    analyzer.result = analyzer.observation({**REQUIREMENTS, "washer": None}, action="recapture")
    analyzer.result.update(
        decision="ready",
        tool_trace=[{"step": "fabricated_order_complete", "status": "completed"}],
        evidence_feedback={"outcome": "made_up_success", "physical_action_verified": True},
    )
    photo = upload(order).json()["photo"]
    response = client.post(
        f"/api/orders/{order['id']}/inspect", json={"photo_id": photo["id"], "expected_revision": 1}
    )
    assert response.status_code == 200, response.text
    data = response.json()
    check = data["check"]
    trace = trace_by_step(check)
    assert check["backend"] == "test"
    assert check["decision"] == "recapture"
    assert check["evidence_feedback"] is None
    assert "fabricated_order_complete" not in trace
    assert trace["choose_next_action"]["decision"] == "recapture"
    assert trace["commit_current_evidence"]["status"] == "completed"
    assert trace["commit_current_evidence"]["evidence_epoch"] == data["order"]["evidence_epoch"]
    assert data["order"]["status"] == "needs_action"
    assert data["order"]["completions"] == []
    exported = client.get(f"/api/orders/{order['id']}/export").json()["order"]
    assert exported["latest_check"]["tool_trace"] == check["tool_trace"]


def test_observer_failure_leaves_no_successful_check_or_commit_trace(client, upload, order, analyzer):
    analyzer.error = RuntimeError("Synthetic inference failure")
    photo = upload(order).json()["photo"]
    response = client.post(
        f"/api/orders/{order['id']}/inspect", json={"photo_id": photo["id"], "expected_revision": 1}
    )
    assert response.status_code == 503
    current = client.get(f"/api/orders/{order['id']}").json()["order"]
    assert current["checks"] == []
    assert current["latest_check"] is None
    assert current["completions"] == []
    assert any(event["kind"] == "inspection_failed" for event in current["events"])
    assert not any(event["kind"] == "inspection_completed" for event in current["events"])


@pytest.mark.parametrize(
    "forbidden", ["requirements", "prior_counts", "target", "differences", "previous_action_message"]
)
def test_real_adapter_rejects_context_fields_that_could_leak_counts(tmp_path, forbidden):
    from kitguard.vision import LocalVision

    engine = LocalVision(tmp_path / "intentionally-absent-model", observation_mode="single")
    context = {
        "previous_action_kind": "separate",
        "uncertain_parts": ["washer"],
        "region": None,
        forbidden: "secret",
    }
    with pytest.raises(ValidationError):
        engine.observe_with_context(tmp_path / "not-used.png", REQUIREMENTS, {}, context)


def test_real_adapter_prompt_is_identical_for_different_order_targets(tmp_path, image_bytes, monkeypatch):
    from kitguard.vision import LocalVision, _Observation

    engine = LocalVision(tmp_path / "intentionally-absent-model", observation_mode="single")
    image_path = tmp_path / "SYNTHETIC_ONLY.png"
    image_path.write_bytes(image_bytes())
    captured = []

    def capture_generate(system, prompt, images, schema):
        captured.append((system, prompt))
        return _Observation.model_validate(
            {
                "observed": {"bolt": None, "nut": None, "washer": None, "bracket": None},
                "issues": ["Synthetic engineering test only"],
                "action": {"kind": "manual", "message": "Test fixture only", "region": None},
            }
        )

    monkeypatch.setattr(engine, "_generate", capture_generate)
    context = {"previous_action_kind": "separate", "uncertain_parts": ["washer"], "region": None}
    engine.observe_with_context(image_path, REQUIREMENTS, {}, context)
    engine.observe_with_context(image_path, {"bolt": 0, "nut": 0, "washer": 0, "bracket": 1}, {}, context)
    assert len(captured) == 2
    assert captured[0] == captured[1]
    assert json.dumps(context, ensure_ascii=False) in captured[0][1]
    assert json.dumps(REQUIREMENTS) not in captured[0][1]


def test_same_photo_retries_do_not_spend_new_evidence_budget(client, upload, order, analyzer):
    counts = {**REQUIREMENTS, "washer": None}
    first = observe_new_photo(client, upload, order, analyzer, counts, action="recapture")
    for _ in range(3):
        retry = client.post(
            f"/api/orders/{order['id']}/inspect",
            json={"photo_id": first["check"]["photo_id"], "expected_revision": 1},
        )
        assert retry.status_code == 200, retry.text
        assert retry.json()["check"]["decision"] == "recapture"
        assert retry.json()["check"]["evidence_feedback"] is None
    assert analyzer.contexts == []
    second = observe_new_photo(client, upload, order, analyzer, counts, seed=1, action="recapture")
    assert second["check"]["decision"] == "recapture"
    retry = client.post(
        f"/api/orders/{order['id']}/inspect",
        json={"photo_id": second["check"]["photo_id"], "expected_revision": 1},
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["check"]["decision"] == "recapture"
    assert len(analyzer.contexts) == 1  # Only the actual second photo received a follow-up cue.
    third = observe_new_photo(client, upload, order, analyzer, counts, seed=2, action="recapture")
    assert third["check"]["decision"] == "manual"


@pytest.mark.parametrize("clear_decision", ["ready", "correct"])
def test_clear_decision_resets_consecutive_unclear_evidence_budget(
    client, upload, order, analyzer, clear_decision
):
    unclear = {**REQUIREMENTS, "washer": None}
    for seed in range(3):
        before = observe_new_photo(client, upload, order, analyzer, unclear, seed=seed, action="recapture")
    assert before["check"]["decision"] == "manual"
    clear = REQUIREMENTS if clear_decision == "ready" else {**REQUIREMENTS, "washer": 1}
    resolved = observe_new_photo(client, upload, order, analyzer, clear, seed=3)
    assert resolved["check"]["decision"] == clear_decision
    decisions = []
    for seed in range(4, 7):
        later = observe_new_photo(client, upload, order, analyzer, unclear, seed=seed, action="recapture")
        decisions.append(later["check"]["decision"])
    assert decisions == ["recapture", "recapture", "manual"]


@pytest.mark.parametrize("scope_change", ["reference", "revision"])
def test_new_scope_does_not_inherit_exhausted_followup_budget(
    client, upload, order, analyzer, image_bytes, scope_change
):
    unclear = {**REQUIREMENTS, "washer": None}
    for seed in range(3):
        old = observe_new_photo(client, upload, order, analyzer, unclear, seed=seed, action="recapture")
    assert old["check"]["decision"] == "manual"
    if scope_change == "reference":
        changed = client.post(
            f"/api/orders/{order['id']}/references/washer",
            files={"photo": ("new-synthetic-reference.png", image_bytes(9), "image/png")},
        )
        assert changed.status_code == 201, changed.text
    else:
        changed = client.post(
            f"/api/orders/{order['id']}/revise",
            json={
                "expected_revision": 1,
                "requirements": {**REQUIREMENTS, "bolt": 1},
                "instruction": "Synthetic scope change",
            },
        )
        assert changed.status_code == 200, changed.text
    current = changed.json()["order"]
    analyzer.contexts.clear()
    decisions = []
    for seed in range(3, 6):
        new = observe_new_photo(
            client,
            upload,
            current,
            analyzer,
            {**current["requirements"], "washer": None},
            seed=seed,
            action="recapture",
        )
        decisions.append(new["check"]["decision"])
        if seed == 3:
            assert analyzer.contexts == []
            assert new["check"]["evidence_feedback"] is None
    assert decisions == ["recapture", "recapture", "manual"]


def test_legacy_unknown_reference_scope_is_a_budget_boundary():
    from kitguard.feedback import observation_context, prior_unclear_evidence_count

    legacy = {"id": "legacy", "revision": 1, "decision": "recapture", "photo_id": "old-photo"}
    order = {"revision": 1, "references": {}, "checks": [legacy], "photos": [{"id": "new-photo"}]}
    assert prior_unclear_evidence_count(order, "new-photo") == 0
    assert observation_context(order) is None
    # A known new record after the legacy boundary can be counted, but not records before it.
    earlier = {**legacy, "photo_id": "earlier-known", "reference_ids": {}}
    later = {**legacy, "photo_id": "later-known", "reference_ids": {}}
    order["checks"] = [earlier, legacy, later]
    assert prior_unclear_evidence_count(order, "new-photo") == 1


def test_unknown_legacy_photo_identity_does_not_consume_budget():
    from kitguard.feedback import prior_unclear_evidence_count

    order = {
        "revision": 1,
        "references": {},
        "checks": [{"revision": 1, "decision": "recapture", "reference_ids": {}}],
    }
    assert prior_unclear_evidence_count(order, "new-photo") == 0


def test_budget_stops_at_reference_boundary_instead_of_reusing_older_matching_scope():
    from kitguard.feedback import prior_unclear_evidence_count

    def check(photo_id, reference_id):
        return {
            "revision": 1,
            "decision": "recapture",
            "photo_id": photo_id,
            "reference_ids": {"washer": reference_id},
        }

    order = {
        "revision": 1,
        "references": {"washer": {"id": "current-ref"}},
        "checks": [
            check("old-current", "current-ref"),
            check("other", "other-ref"),
            check("new-current", "current-ref"),
        ],
    }
    assert prior_unclear_evidence_count(order, "next-photo") == 1
