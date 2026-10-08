"""Read-only digital opinions bound to one saved check; never a new AI decision.

Without runtime_identity this compares only the saved snapshot. Supplying runtime
metadata also requires it to match the check; neither mode reads image bytes or
authenticates a reviewer. File verification remains the review/export route's job.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter

from .photo_documents import digital_source, is_digital_only, verify_document_source
from .regions import inspection_scope, resolve_root
from .store import StateError

IDENTITY_KEYS = ("label", "repo_id", "revision", "observer_protocol_sha256", "observation_mode", "image_max_side")
CONCLUSIONS = ("acknowledged", "needs_more_evidence", "disputed", "inconclusive")
_SNAPSHOT = object()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _sha(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _reviews(order):
    value = order.get("public_reviews")
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def current_digital_check(order, *, runtime_identity=_SNAPSHOT):
    """Return the metadata-bound check, or None; no database/file/runtime calls."""
    try:
        if (not is_digital_only(order) or order.get("active_inspection")
                or order.get("status") in {"completed", "manual_reviewed"}
                or type(order.get("revision")) is not int or order["revision"] < 1
                or type(order.get("evidence_epoch")) is not int or order["evidence_epoch"] < 0):
            return None
        source = digital_source(order)
        photo, check = order["photos"][-1], order["latest_check"]
        if not isinstance(source, dict) or not isinstance(check, dict):
            return None
        root = resolve_root(order, photo)
        if "document_source" in order:
            verify_document_source(order, root)
        elif (source.get("kind") != "public_photo_demo" or source.get("physical_completion_allowed") is not False
              or not source.get("sample_id") or not _sha(source.get("source_sha256"))
              or source["source_sha256"] != root.get("source_sha256")):
            return None
        identity = check.get("runtime_identity")
        if (check.get("valid") is not True or check.get("backend") != "mlx"
                or not isinstance(identity, dict) or any(identity.get(key) is None for key in IDENTITY_KEYS)
                or not _sha(identity.get("observer_protocol_sha256"))
                or not _sha(photo.get("sha256")) or not check.get("id")
                or type(check.get("revision")) is not int or type(photo.get("revision")) is not int
                or type(check.get("evidence_epoch")) is not int
                or check.get("revision") != order["revision"] or photo.get("revision") != order["revision"]
                or check.get("photo_id") != photo["id"] or check.get("photo_sha256") != photo["sha256"]
                or check.get("evidence_epoch") != order["evidence_epoch"]
                or check.get("requirements_snapshot") != order["requirements"]
                or check.get("inspection_scope") != inspection_scope(order, photo)
                or check.get("reference_ids") != {part: ref["id"] for part, ref in order["references"].items()}):
            return None
        if runtime_identity is not _SNAPSHOT and (
                not isinstance(runtime_identity, dict)
                or {key: runtime_identity.get(key) for key in IDENTITY_KEYS} != identity):
            return None
        return check
    except (KeyError, TypeError, ValueError, IndexError, StateError):
        return None


def current_review_ids(order, check):
    """A later acknowledgement cannot supersede a bound disagreement."""
    if check is None:
        return []
    source = digital_source(order)
    check_hash, identity_hash = digest(check), digest(check["runtime_identity"])
    expected_scope = "photo_document_digital_review" if "document_source" in order else "public_photo_digital_review"
    current = []
    ids = Counter(r.get("id") for r in _reviews(order) if isinstance(r.get("id"), str))
    for receipt in _reviews(order):
        if not isinstance(receipt, dict):
            continue
        if (isinstance(receipt.get("id"), str) and receipt["id"] and ids[receipt["id"]] == 1
                and receipt.get("conclusion") in CONCLUSIONS
                and receipt.get("scope") == expected_scope and receipt.get("order_id") == order.get("id")
                and receipt.get("physical_completion") is False and receipt.get("user_validation") is False
                and type(receipt.get("revision")) is int and type(receipt.get("evidence_epoch")) is int
                and receipt.get("revision") == order["revision"] and receipt.get("evidence_epoch") == order["evidence_epoch"]
                and receipt.get("photo_id") == check["photo_id"] and receipt.get("photo_sha256") == check["photo_sha256"]
                and receipt.get("check_id") == check["id"] and receipt.get("check_sha256") == check_hash
                and receipt.get("runtime_identity_sha256") == identity_hash
                and receipt.get("runtime_identity") == check["runtime_identity"]
                and receipt.get("inspection_scope") == check["inspection_scope"]
                and receipt.get("requirements_snapshot") == order["requirements"]
                and receipt.get("source") == source and receipt.get("check_snapshot") == check
                and receipt.get("ai_decision") == check.get("decision")):
            current.append(receipt["id"])
    return current


def derive_digital_review_feedback(order, *, runtime_identity=_SNAPSHOT):
    """Pure view data only: nothing is written to order, check or receipt."""
    check = current_digital_check(order, runtime_identity=runtime_identity)
    current = current_review_ids(order, check)
    counts = dict.fromkeys(CONCLUSIONS, 0)
    pending, seen = [], set()
    for receipt in _reviews(order):
        if isinstance(receipt, dict) and receipt.get("id") in current and receipt["id"] not in seen:
            seen.add(receipt["id"])
            counts[receipt["conclusion"]] += 1
            if receipt["conclusion"] != "acknowledged":
                pending.append(receipt["id"])
    status = ("not_applicable" if check is None else "needs_clarification" if pending
              else "recorded" if current else "none")
    return {"schema_version": 1, "status": status, "current_count": len(current), "pending_count": len(pending),
            "counts": counts, "pending_review_ids": pending, "current_review_ids": current,
            "check_id": check["id"] if check else None,
            "binding_scope": "saved_snapshot" if runtime_identity is _SNAPSHOT else "live_runtime_metadata"}
