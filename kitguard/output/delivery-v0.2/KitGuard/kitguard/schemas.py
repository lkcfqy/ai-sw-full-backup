"""Explicit constraints for both human input and model observations."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from .spatial import InventoryObject

PARTS = ("bolt", "nut", "washer", "bracket")
LABELS = {
    "bolt": ("볼트", "螺栓"),
    "nut": ("너트", "螺母"),
    "washer": ("와셔", "垫圈"),
    "bracket": ("브래킷", "角码"),
}


class Requirements(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bolt: StrictInt = Field(ge=0, le=3)
    nut: StrictInt = Field(ge=0, le=3)
    washer: StrictInt = Field(ge=0, le=3)
    bracket: StrictInt = Field(ge=0, le=3)

    @model_validator(mode="after")
    def total(self):
        if not 1 <= sum(self.model_dump().values()) <= 12:
            raise ValueError("전체 수량은 1~12개여야 합니다 / 总数须为1–12件")
        return self


class NewOrder(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    requirements: Requirements

    @field_validator("title")
    @classmethod
    def clean_title(cls, value):
        if not value.strip():
            raise ValueError("주문 이름을 입력하세요 / 请填写订单名称")
        return value.strip()


class Revision(BaseModel):
    requirements: Requirements
    instruction: str = Field(default="수량 수정 / 修改数量", max_length=1500)
    expected_revision: StrictInt = Field(ge=1)


class Proposal(BaseModel):
    instruction: str = Field(min_length=1, max_length=500)
    expected_revision: StrictInt = Field(ge=1)


class Inspection(BaseModel):
    photo_id: str = Field(min_length=1, max_length=80)
    expected_revision: StrictInt = Field(ge=1)


class Completion(BaseModel):
    check_id: str = Field(min_length=1, max_length=80)
    expected_revision: StrictInt = Field(ge=1)
    confirmed: Literal[True]
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")

    @field_validator("confirmed", mode="before")
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError("본인 확인이 필요합니다 / 必须由操作者明确确认")
        return value


class ObservedCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bolt: StrictInt | None = Field(ge=0, le=100)
    nut: StrictInt | None = Field(ge=0, le=100)
    washer: StrictInt | None = Field(ge=0, le=100)
    bracket: StrictInt | None = Field(ge=0, le=100)


class SuggestedAction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    kind: Literal["none", "separate", "recapture", "manual"]
    message: str = Field(max_length=2000)
    region: list[float] | None = None

    @field_validator("region")
    @classmethod
    def box(cls, value):
        if value is None:
            return value
        if len(value) != 4 or not all(0 <= n <= 1 for n in value):
            raise ValueError("region must be a normalized box")
        if value[0] >= value[2] or value[1] >= value[3]:
            raise ValueError("region must have a positive area")
        return value


class ObservationPass(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transform: Literal["original", "rotate_90_ccw"]
    input_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    observed: ObservedCounts
    issues: list[str] = Field(max_length=6)
    action: SuggestedAction


class ObservationVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["dual_orientation"]
    same_model_correlated_calls: Literal[True]
    counts_agree: bool
    clear_agreement: bool
    passes: list[ObservationPass] = Field(min_length=2, max_length=2)


class ObjectEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol: Literal["spatial_inventory_v1"]
    coordinate_frame: Literal["normalized_original"]
    objects: list[InventoryObject] = Field(max_length=20)
    uncertain_parts: list[Literal["bolt", "nut", "washer", "bracket"]] = Field(max_length=4)


class Observation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    observed: ObservedCounts
    issues: list[str] = Field(max_length=20)
    action: SuggestedAction
    model_label: str = Field(default="Local VLM", max_length=160)
    backend: Literal["mlx", "test"] = "mlx"
    latency_ms: int = Field(default=0, ge=0)
    verification: ObservationVerification | None = None
    object_evidence: ObjectEvidence | None = None

    @model_validator(mode="after")
    def list_matches_counts(self):
        if self.object_evidence is not None:
            for part in PARTS:
                value = getattr(self.observed, part)
                listed = sum(item.part == part for item in self.object_evidence.objects)
                if part in self.object_evidence.uncertain_parts and value is not None:
                    raise ValueError("Uncertain object evidence must remain unknown")
                if value is not None and value != listed:
                    raise ValueError("Observed counts must match the saved object list")
        return self

    @field_validator("issues")
    @classmethod
    def lengths(cls, items):
        if any(len(v) > 2000 for v in items):
            raise ValueError("model issue too long")
        return items
