"""Content-identity regression with synthetic photos and an injected observer.

These are engineering fixtures, not real-world recognition or physical-action
evidence. HTTP tests use the real upload normalization, API and SQLite store.
"""

from copy import deepcopy
from io import BytesIO

import pytest
from conftest import REQUIREMENTS, FakeAnalyzer
from PIL import Image, PngImagePlugin

from kitguard.feedback import evidence_feedback, observation_context, prior_unclear_evidence_count


class ContextObserver(FakeAnalyzer):
    def __init__(self):
        super().__init__()
        self.contexts = []

    def observe_with_context(self, image_path, requirements, references, context):
        self.contexts.append(deepcopy(context))
        return self.observe(image_path, requirements, references)


@pytest.fixture
def analyzer():
    return ContextObserver()


def inspect_upload(client, upload, order, analyzer, *, seed=0, payload=None, clear=False):
    counts = dict(order["requirements"])
    if not clear:
        counts["washer"] = None
    analyzer.result = analyzer.observation(counts, action="none" if clear else "recapture")
    posted = upload(order, seed=seed, payload=payload)
    assert posted.status_code == 201, posted.text
    photo = posted.json()["photo"]
    result = client.post(
        f"/api/orders/{order['id']}/inspect",
        json={"photo_id": photo["id"], "expected_revision": order["revision"]},
    )
    assert result.status_code == 200, result.text
    return photo, result.json()


def assert_no_new_evidence(check):
    assert check["observation_context"] is None
    assert check["evidence_feedback"] is None
    trace = {item["step"]: item for item in check["tool_trace"]}
    assert trace["review_previous_evidence"]["status"] == "not_applicable"


def test_identical_content_reupload_can_retry_without_claiming_evidence_improvement(
    client, upload, order, analyzer
):
    old_photo, first = inspect_upload(client, upload, order, analyzer)
    new_photo, second = inspect_upload(client, upload, order, analyzer, clear=True)
    assert old_photo["id"] != new_photo["id"]
    assert old_photo["sha256"] == new_photo["sha256"]
    assert first["check"]["observed"]["washer"] is None
    assert second["check"]["decision"] == "ready"
    assert_no_new_evidence(second["check"])
    assert analyzer.contexts == []
    assert len(analyzer.calls) == 2  # Retry remains an actual observer call.
    assert second["order"]["checks"][0]["valid"] is False
    assert second["order"]["completions"] == []


def test_different_original_bytes_with_identical_normalized_pixels_are_one_evidence(
    client, upload, order, analyzer, image_bytes
):
    original = image_bytes()
    with Image.open(BytesIO(original)) as source:
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("fixture_note", "Synthetic metadata change, not a new photograph")
        stream = BytesIO()
        source.save(stream, format="PNG", pnginfo=metadata)
    changed_metadata = stream.getvalue()
    assert original != changed_metadata
    first, _ = inspect_upload(client, upload, order, analyzer, payload=original)
    second, result = inspect_upload(client, upload, order, analyzer, payload=changed_metadata, clear=True)
    assert first["source_sha256"] != second["source_sha256"]
    assert first["sha256"] == second["sha256"]
    assert_no_new_evidence(result["check"])
    assert analyzer.contexts == []


def test_duplicate_uploads_do_not_exhaust_budget_and_distinct_content_still_does(
    client, upload, order, analyzer
):
    decisions = []
    for seed in [0, 0, 0, 1, 1, 2]:
        _, result = inspect_upload(client, upload, order, analyzer, seed=seed)
        decisions.append(result["check"]["decision"])
        if seed in {0, 1} and len(result["order"]["checks"]) in {2, 3, 5}:
            assert_no_new_evidence(result["check"])
    assert decisions == ["recapture", "recapture", "recapture", "recapture", "recapture", "manual"]
    assert len(analyzer.contexts) == 2  # Only new content B and C get follow-up attention.
    assert result["order"]["status"] == "needs_action"
    assert result["order"]["completions"] == []


def test_returning_to_older_content_is_not_new_evidence_after_an_intervening_photo(
    client, upload, order, analyzer
):
    inspect_upload(client, upload, order, analyzer, seed=0)
    inspect_upload(client, upload, order, analyzer, seed=1)
    _, returned = inspect_upload(client, upload, order, analyzer, seed=0)
    assert returned["check"]["decision"] == "recapture"
    assert_no_new_evidence(returned["check"])
    assert len(analyzer.contexts) == 1
    _, third_content = inspect_upload(client, upload, order, analyzer, seed=2)
    assert third_content["check"]["decision"] == "manual"


@pytest.mark.parametrize("change", ["revision", "reference"])
def test_content_identity_does_not_inherit_budget_or_feedback_across_scope_changes(
    client, upload, order, analyzer, image_bytes, change
):
    for seed in range(3):
        _, before = inspect_upload(client, upload, order, analyzer, seed=seed)
    assert before["check"]["decision"] == "manual"
    if change == "revision":
        changed = client.post(
            f"/api/orders/{order['id']}/revise",
            json={
                "requirements": {**REQUIREMENTS, "bolt": 1},
                "expected_revision": 1,
                "instruction": "Synthetic revision boundary",
            },
        )
        assert changed.status_code == 200, changed.text
    else:
        changed = client.post(
            f"/api/orders/{order['id']}/references/washer",
            files={"photo": ("synthetic-reference.png", image_bytes(9), "image/png")},
        )
        assert changed.status_code == 201, changed.text
    current = changed.json()["order"]
    analyzer.contexts.clear()
    _, fresh_scope = inspect_upload(client, upload, current, analyzer, seed=0)
    assert fresh_scope["check"]["decision"] == "recapture"
    assert_no_new_evidence(fresh_scope["check"])
    assert prior_unclear_evidence_count(fresh_scope["order"], fresh_scope["check"]["photo_id"]) == 0
    assert analyzer.contexts == []
    _, another = inspect_upload(client, upload, current, analyzer, seed=1)
    assert another["check"]["decision"] == "recapture"
    assert len(analyzer.contexts) == 1


def legacy_order():
    return {
        "revision": 1,
        "references": {},
        "requirements": dict(REQUIREMENTS),
        "photos": [{"id": "old"}, {"id": "new"}],
        "checks": [
            {
                "id": "prior-check",
                "photo_id": "old",
                "revision": 1,
                "reference_ids": {},
                "decision": "recapture",
                "observed": {**REQUIREMENTS, "washer": None},
                "action": {"kind": "recapture", "region": None},
            }
        ],
    }


def current_clear():
    return {"photo_id": "new", "observed": dict(REQUIREMENTS), "decision": "ready"}


@pytest.mark.parametrize("invalid_hash", [None, "", "a" * 63, "z" * 64, 7])
def test_legacy_missing_or_invalid_hashes_keep_photo_id_semantics(invalid_hash):
    order = legacy_order()
    for photo in order["photos"]:
        photo["sha256"] = invalid_hash
        photo["source_sha256"] = "f" * 64  # Raw hashes must not replace normalized hashes.
    assert prior_unclear_evidence_count(order, "new") == 1
    assert observation_context(order)["uncertain_parts"] == ["washer"]
    feedback = evidence_feedback(order, current_clear())
    assert feedback["resolved_uncertainties"] == ["washer"]
    assert feedback["physical_action_verified"] is False
    # Same ID remains a retry even when no valid content digest exists.
    order["photos"][-1]["id"] = "old"
    assert prior_unclear_evidence_count(order, "old") == 0
    assert observation_context(order) is None
    assert evidence_feedback(order, {**current_clear(), "photo_id": "old"}) is None


def test_legacy_check_normalized_hash_can_supply_missing_photo_hash():
    order = legacy_order()
    order["checks"][0]["photo_sha256"] = "a" * 64
    order["photos"][-1]["sha256"] = "A" * 64
    assert prior_unclear_evidence_count(order, "new") == 0
    assert observation_context(order) is None
    assert evidence_feedback(order, current_clear()) is None


def test_saved_photo_hash_takes_precedence_over_conflicting_check_snapshot():
    order = legacy_order()
    order["photos"][0]["sha256"] = "a" * 64
    order["photos"][1]["sha256"] = "a" * 64
    order["checks"][0]["photo_sha256"] = "b" * 64
    assert observation_context(order) is None
    assert evidence_feedback(order, current_clear()) is None
    assert prior_unclear_evidence_count(order, "new") == 0


def test_distinct_normalized_hashes_do_not_merge_even_with_same_source_hash():
    order = legacy_order()
    for photo, digest in zip(order["photos"], ["a" * 64, "b" * 64], strict=True):
        photo.update(sha256=digest, source_sha256="f" * 64)
    assert prior_unclear_evidence_count(order, "new") == 1
    assert observation_context(order)["uncertain_parts"] == ["washer"]
    assert evidence_feedback(order, current_clear())["resolved_uncertainties"] == ["washer"]


def test_legacy_same_photo_hash_fallback_deduplicates_repeated_historical_ids():
    order = legacy_order()
    first = order["checks"][0]
    order["checks"] = [
        first,
        {**deepcopy(first), "photo_sha256": "a" * 64},
        {**deepcopy(first), "photo_id": "old-copy", "photo_sha256": "a" * 64},
    ]
    order["photos"][-1]["sha256"] = "b" * 64
    assert prior_unclear_evidence_count(order, "new") == 1


@pytest.mark.parametrize("decision", ["ready", "correct"])
def test_clear_result_still_resets_the_content_budget(decision):
    order = legacy_order()
    first = order["checks"][0]
    order["checks"] = [
        first,
        {**deepcopy(first), "photo_id": "old-other"},
        {**deepcopy(first), "photo_id": "clear", "decision": decision},
        {**deepcopy(first), "photo_id": "recent", "photo_sha256": "a" * 64},
        {**deepcopy(first), "photo_id": "recent-copy", "photo_sha256": "a" * 64},
    ]
    order["photos"][-1]["sha256"] = "b" * 64
    assert prior_unclear_evidence_count(order, "new") == 1
