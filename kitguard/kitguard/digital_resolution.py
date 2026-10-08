"""Point-supported photo review decisions, distinct from AI and physical release."""

from __future__ import annotations

import copy
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from .digital_review_state import current_digital_check, current_review_ids, digest
from .photo_documents import digital_source
from .schemas import PARTS


class ReviewPoint(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    part: Literal["bolt", "nut", "washer", "bracket"]
    x: StrictInt = Field(ge=0, le=1000)
    y: StrictInt = Field(ge=0, le=1000)


class DigitalResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_revision: StrictInt = Field(ge=1)
    expected_evidence_epoch: StrictInt = Field(ge=0)
    photo_id: str = Field(min_length=1, max_length=80)
    check_id: str = Field(min_length=1, max_length=80)
    check_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    runtime_identity_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    review_set_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    previous_resolution_id: str | None = Field(default=None, max_length=80)
    operator_code: str = Field(min_length=1, max_length=80)
    purpose: Literal["personal_review", "engineering_rehearsal"]
    assessment: Literal["counted", "needs_more_evidence"]
    points: list[ReviewPoint] = Field(max_length=100)
    note: str = Field(min_length=1, max_length=2000)
    confirmed_scope: Literal[True]
    confirmed_digital_only: Literal[True]
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")

    @field_validator("confirmed_scope", "confirmed_digital_only", mode="before")
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError("검토 범위와 디지털 자료임을 확인하세요 / 请明确确认复核范围及数字资料用途")
        return value

    @model_validator(mode="after")
    def distinct_points(self):
        positions = [(point.x, point.y) for point in self.points]
        if len(set(positions)) != len(positions):
            raise ValueError("같은 위치를 중복 표시할 수 없습니다 / 不可在同一点重复计数")
        if self.assessment == "needs_more_evidence" and self.points:
            raise ValueError("자료 요청에는 확정 수량을 기록하지 않습니다 / 补资料结论不能同时提交确定计数")
        return self


def review_set(order, check):
    ids = current_review_ids(order, check)
    return [copy.deepcopy(r) for r in order.get("public_reviews", []) if r.get("id") in ids]


def resolution_binding(order, check):
    return {"expected_revision": order["revision"], "expected_evidence_epoch": order["evidence_epoch"],
            "photo_id": check["photo_id"], "check_id": check["id"], "check_sha256": digest(check),
            "runtime_identity_sha256": digest(check["runtime_identity"]),
            "review_set_sha256": digest(review_set(order, check)),
            "previous_resolution_id": order.get("digital_resolutions", [{}])[-1].get("id")
            if order.get("digital_resolutions") else None}


def assessment_result(assessment, points, requirements):
    if assessment == "needs_more_evidence":
        return {"outcome": "needs_more_evidence", "reviewed_counts": None, "difference": None}
    counts = {part: sum(point["part"] == part for point in points) for part in PARTS}
    difference = {part: counts[part] - requirements[part] for part in PARTS}
    return {"outcome": "matched" if not any(difference.values()) else "mismatch",
            "reviewed_counts": counts, "difference": difference}


def current_resolution(order, *, check=None):
    """A saved decision expires after any evidence, opinion, or decision change."""
    check = current_digital_check(order) if check is None else check
    records = order.get("digital_resolutions")
    if check is None or not isinstance(records, list) or not records:
        return None
    r = records[-1]
    if not isinstance(r, dict):
        return None
    binding = resolution_binding(order, check)
    try:
        if (r.get("schema_version") != 1 or r.get("scope") != "photo_digital_resolution"
                or r.get("order_id") != order["id"] or r.get("physical_completion") is not False
                or r.get("user_validation") is not False or r.get("check_snapshot") != check
                or r.get("requirements_snapshot") != order["requirements"]
                or r.get("source") != digital_source(order)
                or r.get("photo_sha256") != check["photo_sha256"]
                or r.get("inspection_scope") != check["inspection_scope"]
                or r.get("review_snapshot") != review_set(order, check)
                or any(r.get(key) != value for key, value in binding.items()
                       if key != "previous_resolution_id")
                or not r.get("id") or r.get("purpose") not in {"personal_review", "engineering_rehearsal"}):
            return None
        request = DigitalResolutionRequest.model_validate(r["request_snapshot"]).model_dump()
        if any(r.get(key) != request[key] for key in ("assessment", "points", "operator_code", "purpose", "note")):
            return None
        result = assessment_result(r["assessment"], r["points"], order["requirements"])
        return r if all(r.get(key) == value for key, value in result.items()) else None
    except (KeyError, TypeError, ValueError):
        return None


def resolution_summary(order, check):
    current = current_resolution(order, check=check) if check is not None else None
    return {"current": current,
            "request": resolution_binding(order, check) if check is not None else None,
            "history": [{"receipt": r, "current": bool(current and r.get("id") == current["id"])}
                        for r in order.get("digital_resolutions", [])]}
