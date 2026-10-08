"""Synthetic state tests. Annotation quality and real users are never inferred."""

import hashlib
import json
from copy import deepcopy
from io import BytesIO
from zipfile import ZipFile

import pytest
from test_public_review import inspect, replay, request, review, revise, summary
from test_public_review import public as public  # noqa: PLC0414 -- pytest fixture re-export

from kitguard.digital_resolution import current_resolution


def body(client, order, **changes):
    return {**summary(client, order)["resolution"]["request"], "operator_code": "ENGINEERING-TEST",
            "purpose": "engineering_rehearsal", "assessment": "counted",
            "points": [{"part": "bolt", "x": 200, "y": 200}, {"part": "nut", "x": 700, "y": 700}],
            "note": "Synthetic point declarations, not visual validation.",
            "confirmed_scope": True, "confirmed_digital_only": True,
            "idempotency_key": "synthetic-resolution-key", **changes}


def resolve(client, order, payload):
    return client.post(f"/api/orders/{order['id']}/digital-resolution", json=payload)


@pytest.mark.parametrize("decision", ["ready", "correct", "recapture", "manual"])
def test_point_counts_recheck_without_rewriting_ai_or_physical_state(public, decision):
    client, _, analyzer, _ = public
    order = inspect(public, decision=decision)
    before = deepcopy(order)
    r = resolve(client, order, body(client, order))
    assert r.status_code == 200, r.text
    value = r.json()
    assert value["resolution"]["outcome"] == "matched"
    assert value["resolution"]["reviewed_counts"] == order["requirements"]
    assert value["order"]["latest_check"] == before["latest_check"]
    assert value["order"]["checks"] == before["checks"]
    assert value["order"]["status"] == before["status"]
    assert value["order"]["completions"] == value["order"]["manual_reviews"] == []
    assert len(analyzer.calls) == 1
    assert not value["resolution"]["physical_completion"]
    assert not value["resolution"]["user_validation"]
    assert not value["resolution"]["annotation_verified_by_system"]
    assert value["summary"]["resolution"]["current"]["id"] == value["resolution"]["id"]


@pytest.mark.parametrize("points,outcome", [([], "mismatch"), ([{"part": "washer", "x": 10, "y": 20}], "mismatch")])
def test_mismatch_is_derived_not_claimed(public, points, outcome):
    client = public[0]; order = inspect(public)
    value = resolve(client, order, body(client, order, points=points)).json()["resolution"]
    assert value["outcome"] == outcome
    assert value["difference"]["nut"] == -1


def test_more_evidence_is_a_distinct_outcome_without_invented_counts(public):
    client = public[0]; order = inspect(public)
    payload = body(client, order, assessment="needs_more_evidence", points=[], note="Need a sharper source photo")
    value = resolve(client, order, payload).json()["resolution"]
    assert value["outcome"] == "needs_more_evidence"
    assert value["reviewed_counts"] is value["difference"] is None


@pytest.mark.parametrize("changes", [
    {"confirmed_scope": 1}, {"confirmed_digital_only": "true"}, {"note": " "},
    {"points": [{"part": "nut", "x": True, "y": 1}]},
    {"points": [{"part": "nut", "x": 1001, "y": 1}]},
    {"points": [{"part": "nut", "x": 1, "y": 1}, {"part": "bolt", "x": 1, "y": 1}]},
    {"assessment": "needs_more_evidence"}, {"outcome": "matched"},
])
def test_invalid_declarations_rejected(public, changes):
    client = public[0]; order = inspect(public)
    assert resolve(client, order, body(client, order, **changes)).status_code == 422
    assert not summary(client, order)["resolution"]["history"]


@pytest.mark.parametrize("change", ["opinion", "decision", "revision", "region", "reference", "runtime"])
def test_stale_request_cannot_close_changed_evidence(public, change):
    client, _, _analyzer, identity = public
    order = inspect(public)
    payload = body(client, order)
    if change == "opinion":
        assert review(client, order, request(client, order, conclusion="disputed")).status_code == 200
    elif change == "decision":
        assert resolve(client, order, {**payload, "idempotency_key": "another-resolution"}).status_code == 200
    elif change == "revision":
        revise(client, order)
    elif change in {"region", "reference"}:
        store = client.app.state.store
        with store.transaction(order["id"]) as (_, saved):
            saved["evidence_epoch"] += 1
    else:
        identity["revision"] = "different-runtime"
    assert resolve(client, order, payload).status_code == 409


def test_new_opinion_invalidates_then_explicit_redecision_preserves_old_history(public):
    client = public[0]; order = inspect(public)
    assert review(client, order, request(client, order, conclusion="disputed")).status_code == 200
    first = resolve(client, order, body(client, order)).json()["resolution"]
    assert summary(client, order)["resolution"]["current"]["id"] == first["id"]
    assert review(client, order, request(client, order, conclusion="needs_more_evidence",
                                      idempotency_key="new-opinion-key")).status_code == 200
    assert summary(client, order)["resolution"]["current"] is None
    second = resolve(client, order, body(client, order, assessment="needs_more_evidence", points=[],
                                        idempotency_key="new-decision-key")).json()["resolution"]
    s = summary(client, order)
    assert len(s["resolution"]["history"]) == 2 and len(s["reviews"]) == 2
    assert s["resolution"]["current"]["id"] == second["id"]
    assert s["resolution"]["history"][0]["receipt"]["id"] == first["id"]


def test_revise_and_reinspect_does_not_restore_old_signoff(public):
    client = public[0]; order = inspect(public)
    resolve(client, order, body(client, order))
    order = revise(client, order)
    assert summary(client, order)["resolution"]["current"] is None
    assert replay(client, order).status_code == 200
    inspect(public)
    assert summary(client, order)["resolution"]["current"] is None


def test_idempotent_retry_and_conflicting_payload(public):
    client = public[0]; order = inspect(public); payload = body(client, order)
    first = resolve(client, order, payload).json()
    second = resolve(client, order, payload).json()
    assert second["resolution"]["replayed"]
    assert first["resolution"]["id"] == second["resolution"]["id"]
    assert len(second["order"]["digital_resolutions"]) == 1
    assert resolve(client, order, {**payload, "note": "Different body"}).status_code == 409


def test_export_binds_annotation_check_and_opinions(public):
    client = public[0]; order = inspect(public)
    result = resolve(client, order, body(client, order)).json()
    response = client.get(f"/api/orders/{order['id']}/evidence.zip")
    assert response.status_code == 200
    with ZipFile(BytesIO(response.content)) as z:
        payload = json.loads(z.read("evidence.json"))
        assert payload["order"]["digital_resolutions"] == result["order"]["digital_resolutions"]
        assert current_resolution(payload["order"])["id"] == result["resolution"]["id"]
        viewer = z.read("OPEN_ME.html").decode()
        assert "照片资料审核结论" in viewer and "review-dot" in viewer
        assert "<script" not in viewer
        for member in json.loads(z.read("SHA256.json")):
            assert hashlib.sha256(z.read(member["path"])).hexdigest() == member["sha256"]


def test_test_backend_is_not_accepted_as_real_review(public):
    client = public[0]; order = inspect(public, backend="test")
    assert summary(client, order)["resolution"]["request"] is None
