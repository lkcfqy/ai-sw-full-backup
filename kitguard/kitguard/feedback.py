"""Evidence feedback is derived from stored observations, never imagined actions."""

import re

from .regions import source_family
from .schemas import LABELS, PARTS


def reference_ids(order):
    return {part: photo["id"] for part, photo in order.get("references", {}).items()}


def previous_check(order):
    if not order.get("checks"):
        return None
    check = order["checks"][-1]
    if check["revision"] != order["revision"] or check.get("reference_ids") != reference_ids(order):
        return None
    return check


def _photo_content_hashes(order):
    """Use stored JPEG hashes, falling back to check snapshots for legacy photos.

    Missing/invalid hashes stay unknown: photo IDs retain their old identity
    semantics. Source-upload hashes are not substitutes for normalized content.
    This does not establish that different bytes describe a different real scene.
    """
    hashes = {}
    for collection, id_key, hash_key in (
        (order.get("photos", []), "id", "sha256"),
        (order.get("checks", []), "photo_id", "photo_sha256"),
    ):
        for item in collection:
            photo_id = item.get(id_key)
            digest = source_family(item) if id_key == "id" else item.get("source_family_sha256", item.get(hash_key))
            if (
                isinstance(photo_id, str)
                and photo_id
                and isinstance(digest, str)
                and re.fullmatch(r"[0-9a-fA-F]{64}", digest)
            ):
                hashes.setdefault(photo_id, digest.lower())
    # A direct re-upload of bytes already stored by this order is a known alias.
    # Do not infer relationships merely from a shared unknown source-upload hash.
    photos = order.get("photos", [])
    by_stored_hash = {photo.get("sha256"): photo.get("id") for photo in photos if photo.get("sha256")}
    for _ in photos:
        changed = False
        for photo in photos:
            previous_id = by_stored_hash.get(photo.get("source_sha256"))
            if previous_id in hashes and photo.get("id") in hashes and hashes[photo["id"]] != hashes[previous_id]:
                hashes[photo["id"]] = hashes[previous_id]
                changed = True
        if not changed:
            break
    return hashes


def _content_identity(photo_id, hashes):
    return ("sha256", hashes[photo_id]) if photo_id in hashes else ("photo_id", photo_id)


def _is_content_retry(order, photo_id):
    """A previously checked image in this scope is a retry, even after another image.

    A revision/reference boundary ends the search. Legacy unknown hashes fall
    back to photo IDs; unrelated missing hashes never collapse into one identity.
    """
    references = reference_ids(order)
    hashes = _photo_content_hashes(order)
    identity = _content_identity(photo_id, hashes)
    for check in reversed(order.get("checks", [])):
        if check.get("revision") != order["revision"] or check.get("reference_ids") != references:
            break
        previous_id = check.get("photo_id")
        if (
            isinstance(previous_id, str)
            and previous_id
            and _content_identity(previous_id, hashes) == identity
        ):
            return True
    return False


def observation_context(order):
    """Return attention cues only: no target counts, old counts, or add/remove text."""
    previous = previous_check(order)
    latest_photo = order.get("photos", [])[-1] if order.get("photos") else None
    if not previous or not latest_photo or _is_content_retry(order, latest_photo["id"]):
        return None
    uncertain = [part for part in PARTS if previous["observed"][part] is None]
    kind = previous["action"]["kind"]
    if not uncertain and kind not in {"separate", "recapture", "manual"}:
        return None
    return {
        "previous_action_kind": kind if kind in {"separate", "recapture", "manual"} else "recapture",
        "uncertain_parts": uncertain,
        "region": None if previous.get("inspection_scope", {}).get("mode") == "region"
        or latest_photo.get("scope_mode") == "region" else previous["action"].get("region"),
    }


def prior_unclear_evidence_count(order, current_photo_id):
    """Count distinct earlier image content in the current unclear segment.

    A revision/reference change, a clear ready/correct result, or a legacy record
    without reference identity ends the segment. Unknown legacy scope must not
    consume the new scope's budget. Re-running or re-uploading identical normalized
    content is another model attempt, not additional evidence. Unknown legacy
    hashes fall back to photo IDs, not a shared unknown-content identity. This
    neither rejects retries nor authenticates a physical scene.
    """
    references = reference_ids(order)
    hashes = _photo_content_hashes(order)
    current_identity = _content_identity(current_photo_id, hashes)
    identities = set()
    views = {p["id"] for p in order.get("photos", []) if p.get("kind") == "inspection_region_view"}
    for check in reversed(order.get("checks", [])):
        if (
            check.get("revision") != order["revision"]
            or check.get("reference_ids") != references
        ):
            break
        if check.get("decision") not in {"recapture", "manual"}:
            if check.get("photo_id") in views:
                continue  # Reframing the same photo does not reset the recapture budget.
            break
        photo_id = check.get("photo_id")
        if not isinstance(photo_id, str) or not photo_id:
            break  # Legacy records without evidence identity are not countable.
        identity = _content_identity(photo_id, hashes)
        if identity != current_identity:
            identities.add(identity)
    return len(identities)


def evidence_feedback(order, current):
    previous = previous_check(order)
    if previous is not None and previous["photo_id"] != current["photo_id"]:
        hashes = _photo_content_hashes(order)
        if _content_identity(previous["photo_id"], hashes) == _content_identity(current["photo_id"], hashes):
            photos = {p["id"]: p for p in order.get("photos", [])}
            before_photo, after_photo = photos.get(previous["photo_id"], {}), photos.get(current["photo_id"], {})
            if before_photo.get("region_xyxy") != after_photo.get("region_xyxy"):
                return {
                    "previous_check_id": previous["id"], "previous_photo_id": previous["photo_id"],
                    "previous_action_kind": previous["action"]["kind"], "outcome": "inspection_scope_changed",
                    "message": "같은 사진의 검사 범위가 바뀌었습니다. 현재 영역에만 적용됩니다 / 同一照片的检查范围已改变，结果仅适用于当前区域，不能算新拍摄补证",
                    "resolved_uncertainties": [], "remaining_uncertainties": [], "remaining_mismatches": [],
                    "observed_changes": [], "physical_action_verified": False, "new_physical_evidence": False,
                }
    if previous is None or _is_content_retry(order, current["photo_id"]):
        return None
    before, after = previous["observed"], current["observed"]
    resolved = [part for part in PARTS if before[part] is None and after[part] is not None]
    uncertain = [part for part in PARTS if after[part] is None]
    differences = [
        part for part in PARTS if after[part] is not None and after[part] != order["requirements"][part]
    ]
    if current["decision"] == "ready":
        outcome = "current_requirements_match"
        message = "새 사진의 수량이 현재 요구사항과 일치합니다. 실물 확인은 작업자가 완료하세요 / 新照片观察数量与当前需求相符，仍须操作者核对实物"
    elif current["decision"] == "correct" and resolved:
        outcome = "evidence_improved_quantity_mismatch"
        names = ", ".join(f"{LABELS[part][0]}/{LABELS[part][1]}" for part in resolved)
        message = f"{names}: 이전 불명확한 수량을 관찰했습니다. 수량 차이는 아직 남아 있습니다 / 原不明确数量现可观察，但仍有配料差异"
    elif current["decision"] in {"recapture", "manual"}:
        outcome = "evidence_still_unclear"
        message = "새 사진에도 확인되지 않은 증거가 남아 있습니다 / 新照片仍未解决全部观察问题"
    else:
        outcome = "quantity_mismatch_remains"
        message = "새 관찰에서도 수량 차이가 남아 있습니다. 현재 차이를 확인하세요 / 新观察仍有数量差异，请按当前差异调整"
    return {
        "previous_check_id": previous["id"],
        "previous_photo_id": previous["photo_id"],
        "previous_action_kind": previous["action"]["kind"],
        "outcome": outcome,
        "message": message,
        "resolved_uncertainties": resolved,
        "remaining_uncertainties": uncertain,
        "remaining_mismatches": differences,
        "observed_changes": [
            {"part": part, "before": before[part], "after": after[part]}
            for part in PARTS
            if before[part] != after[part]
        ],
        "physical_action_verified": False,
    }
