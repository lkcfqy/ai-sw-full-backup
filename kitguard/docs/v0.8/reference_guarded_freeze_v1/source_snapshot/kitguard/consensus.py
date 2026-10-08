"""Target-blind comparison of correlated spatial observations; never a vote."""

from .spatial import PARTS, SpatialInventory, count_inventory


def compare_inventories(first: SpatialInventory, second: SpatialInventory, model_label: str):
    """Keep a count only when both complete observations agree on that category.

    The rotated pass is the same model on the same scene, not new evidence.
    A disagreement is left unknown rather than repaired using the order target.
    Centers guide recapture only; their geometry is not treated as ground truth.
    """
    observations = [count_inventory(item, model_label)[0] for item in (first, second)]
    unknown = [
        part
        for part in PARTS
        if observations[0]["observed"][part] is None
        or observations[1]["observed"][part] is None
        or observations[0]["observed"][part] != observations[1]["observed"][part]
    ]
    obstacle = bool(unknown or any(o["issues"] or o["action"]["kind"] != "none" for o in observations))
    # A global obstacle with no localized class must never preserve actionable counts.
    if obstacle and not unknown:
        unknown = list(PARTS)
    points = [item.center for item in first.objects if item.part in unknown]
    points += [[1 - item.center[1], item.center[0]] for item in second.objects if item.part in unknown]
    region = None
    if points and len(unknown) < len(PARTS):
        # Approximate location of predicted conflicting categories, not verified boxes.
        margin = 0.08
        region = [
            max(0.0, min(p[0] for p in points) - margin),
            max(0.0, min(p[1] for p in points) - margin),
            min(1.0, max(p[0] for p in points) + margin),
            min(1.0, max(p[1] for p in points) + margin),
        ]
    guidance = {
        "bolt": "볼트/螺栓: 머리와 나사산을 모두 보이게 분리 / 分开放置，露出完整头部与杆部",
        "nut": "너트/螺母: 구멍이 보이게 분리 / 分开放置，让孔口可见",
        "washer": "와셔/垫圈: 겹치지 않게 펼치기 / 平铺，避免重叠",
        "bracket": "브래킷/角码: 두 면이 보이게 분리 / 分开放置，让两面可见",
    }
    result = {
        "observed": {p: None if p in unknown else observations[0]["observed"][p] for p in PARTS},
        "issues": ["두 방향의 물체 목록이 불일치하거나 불명확하여 해당 종류를 미확인으로 남겼습니다."]
        if obstacle else [],
        "action": {
            "kind": "recapture" if obstacle else "none",
            "message": (
                " · ".join(guidance[p] for p in unknown)
                + " → 전체 재촬영 / 重新拍摄整套。영역은 추정 위치 / 区域仅为估计位置。"
                if obstacle else "동일 모델의 두 방향 물체 목록을 대조했습니다. 일치는 정확성을 보장하지 않습니다."
            ),
            "region": region,
        },
        "model_label": model_label,
        "backend": "mlx",
        "object_evidence": {
            "protocol": "spatial_inventory_v1",
            "coordinate_frame": "normalized_original",
            "objects": [o.model_dump() for o in first.objects],
            "uncertain_parts": unknown,
        },
    }
    return result, observations, not unknown, not obstacle
