"""Evidence feedback is derived from stored observations, never imagined actions."""

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


def observation_context(order):
    """Return attention cues only: no target counts, old counts, or add/remove text."""
    previous = previous_check(order)
    latest_photo = order.get("photos", [])[-1] if order.get("photos") else None
    if not previous or not latest_photo or previous["photo_id"] == latest_photo["id"]:
        return None
    uncertain = [part for part in PARTS if previous["observed"][part] is None]
    kind = previous["action"]["kind"]
    if not uncertain and kind not in {"separate", "recapture", "manual"}:
        return None
    return {
        "previous_action_kind": kind if kind in {"separate", "recapture", "manual"} else "recapture",
        "uncertain_parts": uncertain,
        "region": previous["action"].get("region"),
    }


def prior_unclear_evidence_count(order, current_photo_id):
    """Count distinct earlier photos in the current consecutive unclear segment.

    A revision/reference change, a clear ready/correct result, or a legacy record
    without reference identity ends the segment. Unknown legacy scope must not
    consume the new scope's budget. Re-running one stored photo is another model
    attempt, not additional evidence; this does not authenticate a physical scene
    or reject separately uploaded files with duplicate content.
    """
    references = reference_ids(order)
    photo_ids = set()
    for check in reversed(order.get("checks", [])):
        if (
            check.get("revision") != order["revision"]
            or check.get("reference_ids") != references
            or check.get("decision") not in {"recapture", "manual"}
        ):
            break
        photo_id = check.get("photo_id")
        if not isinstance(photo_id, str) or not photo_id:
            break  # Legacy records without evidence identity are not countable.
        if photo_id != current_photo_id:
            photo_ids.add(photo_id)
    return len(photo_ids)


def evidence_feedback(order, current):
    previous = previous_check(order)
    if previous is None or previous["photo_id"] == current["photo_id"]:
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
