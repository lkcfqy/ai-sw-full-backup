"""Synthetic binding/readonly contracts, not model or human validation evidence."""

from copy import deepcopy

import pytest

from kitguard.digital_review_state import derive_digital_review_feedback, digest
from kitguard.evidence import render_viewer
from kitguard.photo_documents import bind_source
from kitguard.regions import inspection_scope


def order_fixture(*, document=False):
    photo = {"id": "synthetic-photo", "revision": 1, "kind": "root_photo", "sha256": "a"*64,
             "source_sha256": "b"*64, "width": 640, "height": 480, "created_at": "synthetic-time"}
    source = {"kind": "public_photo_demo", "sample_id": "SYNTHETIC", "source_sha256": "b"*64,
              "physical_completion_allowed": False}
    order = {"id": "synthetic-order", "title": "SYNTHETIC ENGINEERING ONLY", "revision": 1,
             "evidence_epoch": 2, "requirements": {"bolt": 2, "nut": 2, "washer": 2, "bracket": 0},
             "photos": [photo], "references": {}, "status": "ready", "active_inspection": None,
             "demo_source": source, "public_reviews": [], "completions": [], "manual_reviews": []}
    if document:
        source = bind_source({"source_note": "SYNTHETIC, NOT AUTHENTICATED", "source_url": None, "license_note": None}, photo, "synthetic-time")
        order.pop("demo_source")
        order["document_source"] = source
        photo["document_source"] = deepcopy(source)
    check = {"id": "synthetic-check", "revision": 1, "photo_id": photo["id"], "photo_sha256": photo["sha256"],
             "valid": True, "backend": "mlx", "evidence_epoch": 2, "requirements_snapshot": deepcopy(order["requirements"]),
             "inspection_scope": inspection_scope(order, photo), "reference_ids": {}, "decision": "ready",
             "runtime_identity": {"label": "SYNTHETIC METADATA ONLY", "repo_id": "synthetic/repo", "revision": "fake-commit",
                                  "observer_protocol_sha256": "c"*64, "observation_mode": "synthetic", "image_max_side": 512}}
    order["latest_check"] = check
    order["checks"] = [deepcopy(check)]
    return order


def add_review(order, conclusion="disputed", identifier=None):
    check = order["latest_check"]
    receipt = {"id": identifier or f"review-{len(order['public_reviews'])}", "order_id": order["id"],
               "scope": "photo_document_digital_review" if "document_source" in order else "public_photo_digital_review",
               "revision": order["revision"], "evidence_epoch": order["evidence_epoch"], "photo_id": check["photo_id"],
               "photo_sha256": check["photo_sha256"], "check_id": check["id"], "check_sha256": digest(check),
               "runtime_identity_sha256": digest(check["runtime_identity"]), "runtime_identity": deepcopy(check["runtime_identity"]),
               "inspection_scope": deepcopy(check["inspection_scope"]), "requirements_snapshot": deepcopy(order["requirements"]),
               "source": deepcopy(order.get("document_source", order.get("demo_source"))), "check_snapshot": deepcopy(check),
               "ai_decision": check["decision"], "conclusion": conclusion, "physical_completion": False,
               "user_validation": False, "operator_code": "SYNTHETIC", "note": "<script>synthetic</script>"}
    order["public_reviews"].append(receipt)
    return receipt


@pytest.mark.parametrize("document", [False, True])
@pytest.mark.parametrize("negative", ["disputed", "needs_more_evidence", "inconclusive"])
def test_later_acknowledgement_never_clears_pending_opinion(document, negative):
    order = order_fixture(document=document)
    pending = add_review(order, negative)
    add_review(order, "acknowledged")
    before = deepcopy(order)
    result = derive_digital_review_feedback(order, runtime_identity=order["latest_check"]["runtime_identity"])
    assert result["status"] == "needs_clarification"
    assert result["current_count"] == 2 and result["pending_count"] == 1
    assert result["pending_review_ids"] == [pending["id"]]
    assert result["counts"]["acknowledged"] == result["counts"][negative] == 1
    assert result["binding_scope"] == "live_runtime_metadata"
    assert order == before


def test_none_recorded_and_not_applicable_are_different():
    order = order_fixture()
    assert derive_digital_review_feedback(order)["status"] == "none"
    add_review(order, "acknowledged")
    assert derive_digital_review_feedback(order)["status"] == "recorded"
    order.pop("demo_source")
    assert derive_digital_review_feedback(order)["status"] == "not_applicable"
    assert derive_digital_review_feedback(order)["current_count"] == 0


@pytest.mark.parametrize("field", ["revision", "evidence_epoch", "photo_id", "photo_sha256", "check_id", "check_sha256",
                                  "runtime_identity_sha256", "runtime_identity", "source", "inspection_scope", "requirements_snapshot",
                                  "check_snapshot", "order_id", "scope", "ai_decision", "physical_completion", "user_validation"])
def test_every_receipt_binding_is_required(field):
    order = order_fixture()
    add_review(order)[field] = "tampered"
    result = derive_digital_review_feedback(order)
    assert result["status"] == "none" and result["current_count"] == result["pending_count"] == 0


@pytest.mark.parametrize("change", ["revision", "epoch", "new_photo", "photo_sha", "invalid", "test_backend", "scope", "references", "requirements", "active", "source", "runtime_missing"])
def test_stale_check_never_makes_history_current(change):
    order = order_fixture()
    add_review(order)
    if change == "revision": order["revision"] += 1
    elif change == "epoch": order["evidence_epoch"] += 1
    elif change == "new_photo": order["photos"].append({**order["photos"][-1], "id": "new-photo"})
    elif change == "photo_sha": order["photos"][-1]["sha256"] = "d"*64
    elif change == "invalid": order["latest_check"]["valid"] = False
    elif change == "test_backend": order["latest_check"]["backend"] = "test"
    elif change == "scope": order["latest_check"]["inspection_scope"] = {}
    elif change == "references": order["references"] = {"nut": {"id": "new-ref"}}
    elif change == "requirements": order["requirements"]["nut"] = 1
    elif change == "active": order["active_inspection"] = {"id": "job"}
    elif change == "source": order["demo_source"]["physical_completion_allowed"] = True
    else: order["latest_check"]["runtime_identity"] = {}
    feedback = derive_digital_review_feedback(order)
    assert feedback["status"] == "not_applicable" and feedback["check_id"] is None
    assert feedback["pending_review_ids"] == []


@pytest.mark.parametrize("runtime", [None, {}, {"observer_protocol_sha256": "changed"}])
def test_live_unknown_or_changed_runtime_is_not_snapshot_fallback(runtime):
    order = order_fixture()
    add_review(order)
    assert derive_digital_review_feedback(order, runtime_identity=runtime)["status"] == "not_applicable"
    snapshot = derive_digital_review_feedback(order)
    assert snapshot["status"] == "needs_clarification" and snapshot["binding_scope"] == "saved_snapshot"


def test_duplicate_id_and_malformed_receipt_fail_closed_without_mutation():
    order = order_fixture()
    first = add_review(order)
    order["public_reviews"].extend([dict(first, conclusion="acknowledged"), None, {"id": []}])
    before = deepcopy(order)
    assert derive_digital_review_feedback(order)["status"] == "none"
    assert order == before


@pytest.mark.parametrize("value", [None, 42, "legacy", {}, [None, 42, {}, {"id": []}]])
def test_malformed_review_collection_is_readable_history_not_an_exception(value):
    order = order_fixture()
    order["public_reviews"] = value
    before = deepcopy(order)
    assert derive_digital_review_feedback(order)["status"] == "none"
    render_viewer({"order": order, "photos": []})
    assert order == before


def test_boolean_revision_is_not_an_integer_binding():
    order = order_fixture()
    receipt = add_review(order)
    receipt["revision"] = True
    assert derive_digital_review_feedback(order)["status"] == "none"
    order["revision"] = True
    assert derive_digital_review_feedback(order)["status"] == "not_applicable"


def test_offline_first_screen_and_history_use_same_saved_binding_and_escape():
    order = order_fixture(document=True)
    add_review(order)
    add_review(order, "acknowledged")
    payload = {"order": order, "photos": []}
    before = deepcopy(payload)
    html = render_viewer(payload)
    assert "data-feedback-status='needs_clarification'" in html
    assert "待澄清意见" in html and "AI 保存判断（未改写）" in html
    assert "href='#digital-review-history'" in html and "id='digital-review-history'" in html
    assert "仅对照导出时保存的绑定" in html and "后续认可不会清除先前异议" in html
    assert "&lt;script&gt;synthetic&lt;/script&gt;" in html and "<script>synthetic</script>" not in html
    assert payload == before
    order["latest_check"]["valid"] = False
    html = render_viewer(payload)
    assert "不适用于当前核验 · 不代表已解决" in html
    assert "对应导出时当前核验" not in html
