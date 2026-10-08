"""Explicit constraints for both human input and model observations."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from .identity import CropMetadata, IdentityResponse, apply_decision
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
    model_config = ConfigDict(extra="forbid")
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


class ManualCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bolt: StrictInt = Field(ge=0, le=100)
    nut: StrictInt = Field(ge=0, le=100)
    washer: StrictInt = Field(ge=0, le=100)
    bracket: StrictInt = Field(ge=0, le=100)


class ManualReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_revision: StrictInt = Field(ge=1)
    expected_evidence_epoch: StrictInt = Field(ge=0)
    photo_id: str = Field(min_length=1, max_length=80)
    check_id: str | None = Field(default=None, min_length=1, max_length=80)
    actual_counts: ManualCounts
    operator_code: str = Field(min_length=1, max_length=40)
    reason: str = Field(min_length=1, max_length=1000)
    confirmed_physical: Literal[True]
    confirmed_current_bom: Literal[True]
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")

    @field_validator("confirmed_physical", "confirmed_current_bom", mode="before")
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError("실물과 현재 BOM을 직접 확인하세요 / 必须明确确认已独立核对实物和当前BOM")
        return value


class ReopenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_revision: StrictInt = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)
    confirmed: Literal[True]
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")

    @field_validator("confirmed", mode="before")
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError("재처리를 명시적으로 확인하세요 / 必须明确确认重新处理")
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


class SpatialObservationPass(ObservationPass):
    objects: list[InventoryObject] = Field(max_length=20)
    uncertain_parts: list[Literal["bolt", "nut", "washer", "bracket"]] = Field(max_length=4)

    @model_validator(mode="after")
    def list_and_uncertainty_match(self):
        if len(set(self.uncertain_parts)) != len(self.uncertain_parts):
            raise ValueError("Duplicate uncertain categories")
        for part in PARTS:
            count = getattr(self.observed, part)
            if (count is None) != (part in self.uncertain_parts):
                raise ValueError("Each unknown pass count must have its own uncertainty marker")
            if count is not None and count != sum(o.part == part for o in self.objects):
                raise ValueError("Pass count must match its saved spatial list")
        if self.uncertain_parts:
            if self.action.kind != "recapture" or not self.issues:
                raise ValueError("Uncertain spatial pass must retain its recapture obstacle")
        elif self.action.kind != "none" or self.issues:
            raise ValueError("Unlocalized spatial obstacles must mark counts unknown")
        return self


class SpatialVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["spatial_consensus"]
    same_model_correlated_calls: Literal[True]
    counts_agree: bool
    clear_agreement: bool
    passes: list[SpatialObservationPass] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def derived_agreement(self):
        if [p.transform for p in self.passes] != ["original", "rotate_90_ccw"]:
            raise ValueError("Spatial passes must retain the original and rotated frames in order")
        a, b = self.passes
        known_equal = all(
            getattr(a.observed, part) is not None
            and getattr(a.observed, part) == getattr(b.observed, part)
            for part in PARTS
        )
        clear = known_equal and not (a.issues or b.issues) and a.action.kind == b.action.kind == "none"
        if self.counts_agree != known_equal or self.clear_agreement != clear:
            raise ValueError("Spatial agreement flags must be derived from both saved passes")
        return self


class ObjectEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol: Literal["spatial_inventory_v1"]
    coordinate_frame: Literal["normalized_original"]
    objects: list[InventoryObject] = Field(max_length=20)
    uncertain_parts: list[Literal["bolt", "nut", "washer", "bracket"]] = Field(max_length=4)


class IdentityVerification(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    protocol: Literal["identity_geometry_v2"]
    same_model_correlated_calls: Literal[True]
    response: IdentityResponse
    blocked_categories: list[Literal["bolt", "nut", "washer", "bracket"]] = Field(max_length=4)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    full_input_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    # The metadata is reproduced by the geometry module; never used as truth or a count source.
    crops: list[CropMetadata] = Field(min_length=1, max_length=20)


class ReferenceImageEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    part: Literal["bolt", "nut", "washer", "bracket"]
    stored_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    prepared_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    prepared_size: list[StrictInt] = Field(min_length=2, max_length=2)
    image_index: StrictInt = Field(ge=2, le=5)
    # The API binds these to the inspection snapshot; the observer does not know photo IDs.
    photo_id: str | None = Field(default=None, min_length=1, max_length=80)
    upload_source_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @field_validator("prepared_size")
    @classmethod
    def bounded_size(cls, value):
        if not all(1 <= n <= 512 for n in value):
            raise ValueError("Reference inputs must retain their actual bounded dimensions")
        return value


class ReferenceStageEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    stage: Literal["original", "rotate_90_ccw", "identity"]
    reference_image_indices: list[StrictInt] = Field(max_length=4)
    status: Literal["attempted", "completed", "failed", "skipped_base_unclear", "skipped_no_candidates"]


class ReferenceEvidence(BaseModel):
    """Host-generated evidence only; this schema is never sent to the model."""

    model_config = ConfigDict(extra="forbid", strict=True)
    protocol: Literal["reference_inputs_v1"]
    observer_protocol_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    observation_mode: Literal["single", "dual_orientation", "spatial_inventory", "spatial_consensus", "spatial_guarded"]
    preprocessing: Literal["exif_transpose_rgb_thumbnail_lanczos_png_v1"]
    pillow_version: str = Field(min_length=1, max_length=50)
    max_side: Literal[512]
    prepared_bytes_retained: Literal[False]
    guarded_identity_uses_references: Literal[False]
    images: list[ReferenceImageEvidence] = Field(max_length=4)
    stages: list[ReferenceStageEvidence] = Field(max_length=3)

    @model_validator(mode="after")
    def ordered_inputs(self):
        if [image.part for image in self.images] != [p for p in PARTS if p in {i.part for i in self.images}]:
            raise ValueError("Reference categories must be unique and in model input order")
        indices = [image.image_index for image in self.images]
        if indices != list(range(2, len(self.images) + 2)):
            raise ValueError("Reference image indices must follow target image 1")
        names = [stage.stage for stage in self.stages]
        if len(set(names)) != len(names):
            raise ValueError("Reference stage records must be unique")
        for stage in self.stages:
            expected = [] if stage.stage == "identity" else indices
            if stage.reference_image_indices != expected:
                raise ValueError("Reference stage inputs differ from their declared roles")
            if stage.status.startswith("skipped_") and stage.stage != "identity":
                raise ValueError("Only the conditional identity stage may be skipped")
        return self


class Observation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    observed: ObservedCounts
    issues: list[str] = Field(max_length=20)
    action: SuggestedAction
    model_label: str = Field(default="Local VLM", max_length=160)
    backend: Literal["mlx", "test"] = "mlx"
    latency_ms: int = Field(default=0, ge=0)
    verification: ObservationVerification | SpatialVerification | None = None
    object_evidence: ObjectEvidence | None = None
    identity_verification: IdentityVerification | None = None
    reference_evidence: ReferenceEvidence | None = None

    @model_validator(mode="after")
    def successful_reference_stages(self):
        evidence = self.reference_evidence
        if evidence is None:
            return self
        mode = evidence.observation_mode
        expected = ["original"]
        if mode in {"dual_orientation", "spatial_consensus", "spatial_guarded"}:
            expected.append("rotate_90_ccw")
        if mode == "spatial_guarded":
            expected.append("identity")
        if [stage.stage for stage in evidence.stages] != expected:
            raise ValueError("Successful observations must retain every stage in actual call order")
        if any(stage.status != "completed" for stage in evidence.stages if stage.stage != "identity"):
            raise ValueError("Successful observations cannot have unfinished reference observation stages")
        if mode == "dual_orientation" and not isinstance(self.verification, ObservationVerification):
            raise ValueError("Reference mode must match the saved dual observation")
        if mode in {"spatial_consensus", "spatial_guarded"} and not isinstance(self.verification, SpatialVerification):
            raise ValueError("Reference mode must match the saved spatial observations")
        if mode in {"single", "spatial_inventory"} and self.verification is not None:
            raise ValueError("Single-pass reference evidence cannot describe multiple observations")
        if mode != "spatial_guarded" and self.identity_verification is not None:
            raise ValueError("Identity verification requires a guarded reference stage record")
        if mode == "spatial_guarded":
            if not self.verification.clear_agreement:
                status = "skipped_base_unclear"
            elif any(item.part in {"nut", "washer"} for item in self.verification.passes[0].objects):
                status = "completed"
            else:
                status = "skipped_no_candidates"
            if evidence.stages[-1].status != status or (self.identity_verification is not None) != (status == "completed"):
                raise ValueError("Reference identity stage must match its actual verification or skip reason")
        return self

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
        if isinstance(self.verification, SpatialVerification):
            first, second = self.verification.passes
            expected = {
                part: getattr(first.observed, part)
                if getattr(first.observed, part) == getattr(second.observed, part)
                else None
                for part in PARTS
            }
            if self.identity_verification is not None:
                from .identity import select_targets

                review = self.identity_verification
                if not self.verification.clear_agreement:
                    raise ValueError("Identity guard cannot restore an unclear base observation")
                base = {
                    "observed": expected, "issues": [],
                    "action": {"kind": "none", "message": "Validated base", "region": None},
                    "verification": self.verification.model_dump(),
                    "object_evidence": {"protocol": "spatial_inventory_v1",
                        "coordinate_frame": "normalized_original",
                        "objects": [o.model_dump() for o in first.objects], "uncertain_parts": []},
                }
                targets = select_targets(base)
                decision = apply_decision(base, targets, review.response)
                if review.blocked_categories != decision["blocked_categories"]:
                    raise ValueError("Identity blocked categories must be derived from saved responses")
                if review.full_input_sha256 != first.input_sha256:
                    raise ValueError("Identity full image must match the original pass")
                if [c.id for c in review.crops] != [t["id"] for t in targets]:
                    raise ValueError("Identity crop records must cover the selected targets in order")
                for crop, target in zip(review.crops, targets, strict=True):
                    if any(getattr(crop, key) != target[key] for key in target):
                        raise ValueError("Crop target must match the saved original object")
                    if crop.source_sha256 != review.source_sha256:
                        raise ValueError("Each crop must derive from the same saved upload")
                for part in review.blocked_categories:
                    expected[part] = None
                if review.blocked_categories and (not self.issues or self.action.kind == "none"):
                    raise ValueError("Unconfirmed identity requires a visible recapture obstacle")
            if self.observed.model_dump() != expected:
                raise ValueError("Final spatial counts must be derived from the two saved passes")
            if self.object_evidence is None or self.object_evidence.objects != first.objects:
                raise ValueError("Final spatial evidence must preserve the original-frame list")
            unknown = {p for p in PARTS if expected[p] is None}
            if set(self.object_evidence.uncertain_parts) != unknown:
                raise ValueError("Final spatial evidence must retain every unresolved category")
            if not self.verification.clear_agreement and (not self.issues or self.action.kind == "none"):
                raise ValueError("A conflicting spatial observation cannot become a clear result")
        elif self.identity_verification is not None:
            raise ValueError("Identity review requires both spatial observation passes")
        return self

    @field_validator("issues")
    @classmethod
    def lengths(cls, items):
        if any(len(v) > 2000 for v in items):
            raise ValueError("model issue too long")
        return items
