"""Public-photo replay and human digital review, separate from physical completion.

No inference is performed here. Replay copies verified photograph bytes; inspection
must subsequently use the normal inference endpoint. A review records what a human
thought of a current model result, including disagreement and unresolved evidence.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from .public_demo_catalog import CATALOG
from .regions import inspection_scope, stored_bytes, verify_photo_lineage
from .store import StateError, event, expect_revision, invalidate, now, reject_active_study, uid

SCOPE = "public_photo_digital_review"
IDENTITY_KEYS = ("label", "repo_id", "revision", "observer_protocol_sha256", "observation_mode", "image_max_side")
LIMITATIONS = [
    "Public photographs and their selected views are recorded input, not a live physical scene.",
    "Replaying the same pixels after a revision is not a new capture, repair, or physical completion.",
    "Digital review is a human opinion about a model result, not model correctness or user-study evidence.",
    "Operator codes are self-declared labels, not authenticated identities; checksums are not signatures.",
]


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


class PublicReplayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_revision: StrictInt = Field(ge=1)
    expected_photo_id: str = Field(min_length=1, max_length=80)
    expected_evidence_epoch: StrictInt = Field(ge=0)
    confirmed_no_physical_capture: Literal[True]
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")

    @field_validator("confirmed_no_physical_capture", mode="before")
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError("새 실물 촬영이 아님을 확인하세요 / 请明确确认这不是新拍摄实物")
        return value


class PublicReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_revision: StrictInt = Field(ge=1)
    expected_evidence_epoch: StrictInt = Field(ge=0)
    photo_id: str = Field(min_length=1, max_length=80)
    check_id: str = Field(min_length=1, max_length=80)
    check_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    runtime_identity_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    operator_code: str = Field(min_length=1, max_length=80)
    conclusion: Literal["acknowledged", "needs_more_evidence", "disputed", "inconclusive"]
    note: str = Field(min_length=1, max_length=2000)
    confirmed_digital_only: Literal[True]
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")

    @field_validator("confirmed_digital_only", mode="before")
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError("디지털 검토임을 확인하세요 / 请明确确认仅为数字审查")
        return value


class PublicReviews:
    def __init__(self, store, runtime, catalog=None):
        self.store, self.runtime = store, runtime
        self.catalog = CATALOG if catalog is None else catalog

    def _source(self, order, db=None):
        source = order.get("demo_source") or {}
        spec = next((item for item in self.catalog if item["sample_id"] == source.get("sample_id")), None)
        if (not spec or source.get("kind") != "public_photo_demo"
                or source.get("physical_completion_allowed") is not False
                or any(source.get(k) != spec.get(k) for k in
                       ("source_sha256", "source_case_id", "source_url", "license", "derived_view"))):
            raise StateError("등록된 공개 사진 주문만 검토할 수 있습니다 / 仅可审查来源已登记的公开照片订单")
        if not order.get("photos"):
            raise StateError("공개 사진이 없습니다 / 尚无公开照片")
        photo = order["photos"][-1]
        root, raw = verify_photo_lineage(self.store, order, photo, db)
        if root.get("source_sha256") != spec["source_sha256"]:
            raise StateError("현재 사진은 등록된 공개 원본과 다릅니다 / 当前照片不属于已登记公开来源")
        return photo, root, raw

    @staticmethod
    def _idle(order):
        if order.get("active_inspection"):
            raise StateError("진행 중인 검증을 기다리세요 / 请等待正在进行的核验结束")
        if order["status"] in {"completed", "manual_reviewed"}:
            raise StateError("실물 종료 주문을 공개 검토로 바꿀 수 없습니다 / 实物完工订单不能改为公开数字审查")

    def _current_check(self, order, db=None):
        photo, _, _ = self._source(order, db)
        self._idle(order)
        check = order.get("latest_check")
        if (not check or not check.get("valid") or check["revision"] != order["revision"]
                or photo["revision"] != order["revision"] or check["photo_id"] != photo["id"]
                or check.get("evidence_epoch") != order["evidence_epoch"]
                or check.get("photo_sha256") != photo["sha256"]
                or check.get("requirements_snapshot") != order["requirements"]
                or check.get("inspection_scope") != inspection_scope(order, photo)
                or check.get("reference_ids") != {part: ref["id"] for part, ref in order["references"].items()}):
            raise StateError("현재 버전·사진의 유효한 AI 검증이 필요합니다 / 需要当前版本、照片与范围的有效AI核验")
        if check.get("backend") != "mlx":
            raise StateError("테스트 대역은 공개 AI 검토 증거가 아닙니다 / 工程替身不能作为公开数据AI审查证据")
        runtime = self.runtime()
        identity = {key: runtime.get(key) for key in IDENTITY_KEYS}
        if (any(identity[k] is None for k in IDENTITY_KEYS)
                or identity != check.get("runtime_identity")):
            raise StateError("모델 구성이 달라졌습니다. 다시 검증하세요 / 模型身份或观察协议已改变，请重新核验")
        for reference in order["references"].values():
            stored_bytes(self.store, reference, db)
        return check

    def _replayable(self, order, db=None):
        photo, root, raw = self._source(order, db)
        self._idle(order)
        if photo["revision"] == order["revision"]:
            raise StateError("현재 버전 사진입니다. 바로 AI 검증을 실행하세요 / 照片已对应当前版本，请直接运行AI核验")
        if len(order["photos"]) + len(order["reference_history"]) + (1 if root["id"] == photo["id"] else 2) > 300:
            raise StateError("주문 사진 한도에 도달했습니다 / 已达到订单照片数量上限")
        return photo, root, raw

    @staticmethod
    def _bound(order, body, photo_key):
        expect_revision(order, body["expected_revision"])
        if (order["evidence_epoch"] != body["expected_evidence_epoch"] or not order["photos"]
                or order["photos"][-1]["id"] != body[photo_key]):
            raise StateError("사진·증거 버전이 바뀌었습니다 / 照片或证据版本已变化，请刷新")

    def summary(self, order_id):
        order = self.store.get(order_id)
        self._source(order)
        check, blockers, replay_blockers = None, [], []
        try:
            check = self._current_check(order)
        except StateError as exc:
            blockers.append(str(exc))
        try:
            self._replayable(order)
        except StateError as exc:
            replay_blockers.append(str(exc))
        with self.store.connect() as db:
            try:
                reject_active_study(db, order)
            except StateError as exc:
                blockers.append(str(exc))
                replay_blockers.append(str(exc))
        photo = order["photos"][-1]
        reviews = [{"receipt": receipt, "current": bool(check and
                    receipt["check_sha256"] == digest(check) and receipt["revision"] == order["revision"]
                    and receipt["evidence_epoch"] == order["evidence_epoch"])}
                   for receipt in order.get("public_reviews", [])]
        review_request = None if blockers else {
            "expected_revision": order["revision"], "expected_evidence_epoch": order["evidence_epoch"],
            "photo_id": photo["id"], "check_id": check["id"], "check_sha256": digest(check),
            "runtime_identity_sha256": digest(check["runtime_identity"]),
        }
        return {
            "schema_version": 1, "scope": SCOPE, "order_id": order_id, "revision": order["revision"],
            "evidence_epoch": order["evidence_epoch"], "source": order["demo_source"],
            "physical_completion_allowed": False, "can_review": not blockers, "review_blockers": blockers,
            "can_replay": not replay_blockers, "replay_blockers": replay_blockers,
            "review_request": review_request,
            "replay_request": {"expected_revision": order["revision"], "expected_photo_id": photo["id"],
                               "expected_evidence_epoch": order["evidence_epoch"]},
            "current_review": next((r["receipt"] for r in reversed(reviews) if r["current"]), None),
            "reviews": reviews, "check": None if check is None else {
                **check, "check_sha256": digest(check),
                "runtime_identity_sha256": digest(check["runtime_identity"])},
            "inspection_scope": inspection_scope(order, photo), "limitations": LIMITATIONS,
        }

    def review(self, order_id, request):
        request = PublicReviewRequest.model_validate(request).model_dump()
        with self.store.transaction(order_id) as (db, order):
            receipt, request_digest = self.store._human_replay(db, order_id, "public_review", request)
            replayed = receipt is not None
            if receipt is None:
                self._bound(order, request, "photo_id")
                reject_active_study(db, order)
                check = self._current_check(order, db)
                if (request["check_id"] != check["id"] or request["check_sha256"] != digest(check)
                        or request["runtime_identity_sha256"] != digest(check["runtime_identity"])):
                    raise StateError("AI 검증 내용이 바뀌었습니다 / AI核验内容或模型身份已变化，请刷新")
                receipt = {
                    "id": uid("digital"), "scope": SCOPE, "order_id": order_id, "created_at": now(),
                    "revision": order["revision"], "evidence_epoch": order["evidence_epoch"],
                    "photo_id": check["photo_id"], "photo_sha256": check["photo_sha256"],
                    "check_id": check["id"], "check_sha256": digest(check),
                    "runtime_identity_sha256": digest(check["runtime_identity"]),
                    "runtime_identity": copy.deepcopy(check["runtime_identity"]),
                    "inspection_scope": copy.deepcopy(check["inspection_scope"]),
                    "source": copy.deepcopy(order["demo_source"]),
                    "requirements_snapshot": copy.deepcopy(order["requirements"]),
                    "ai_decision": check["decision"], "check_snapshot": copy.deepcopy(check),
                    "operator_code": request["operator_code"], "conclusion": request["conclusion"],
                    "note": request["note"], "physical_completion": False, "user_validation": False,
                    "limitations": LIMITATIONS,
                }
                order.setdefault("public_reviews", []).append(receipt)
                self.store._save_human_operation(db, order_id, "public_review", request, request_digest, receipt)
                event(order, "public_digital_review_recorded", "공개 사진 디지털 검토 / 已记录公开照片数字审查", {
                    "review_id": receipt["id"], "check_id": check["id"], "ai_decision": check["decision"],
                    "conclusion": request["conclusion"], "physical_completion": False})
        return {"order": self.store.get(order_id), "review": {**receipt, "replayed": replayed},
                "summary": self.summary(order_id)}

    def replay(self, order_id, request):
        request = PublicReplayRequest.model_validate(request).model_dump()
        written, committed = [], False
        try:
            with self.store.transaction(order_id) as (db, order):
                receipt, request_digest = self.store._human_replay(db, order_id, "public_replay", request)
                replayed = receipt is not None
                if receipt is None:
                    self._bound(order, request, "expected_photo_id")
                    reject_active_study(db, order)
                    old, root, raw = self._replayable(order, db)
                    new_root_id, stamp = uid("img"), now()
                    copies = [(root, raw)]
                    if old["id"] != root["id"]:
                        copies.append((old, stored_bytes(self.store, old, db)))
                    new_photos = []
                    for original, content in copies:
                        photo_id = new_root_id if original["id"] == root["id"] else uid("img")
                        photo = {**copy.deepcopy(original), "id": photo_id, "url": f"/api/photos/{photo_id}",
                                 "root_photo_id": new_root_id, "revision": order["revision"], "created_at": stamp,
                                 "replay_of_photo_id": original["id"], "physical_capture": False,
                                 "capture_kind": "public_photo_replay"}
                        if photo.get("kind") == "inspection_region_view":
                            photo["root_created_at"] = stamp
                        path = self.store.photos_dir / f"{photo_id}.jpg"
                        with path.open("xb") as stream:
                            written.append(path)
                            stream.write(content)
                        db.execute("INSERT INTO photos VALUES (?,?)", (photo_id, path.name))
                        order["photos"].append(photo)
                        new_photos.append(photo)
                    # Verify the old lineage again before committing, as file writes are not transactional.
                    verify_photo_lineage(self.store, order, old, db)
                    verify_photo_lineage(self.store, order, new_photos[-1], db)
                    invalidate(order)
                    receipt = {
                        "id": uid("replay"), "scope": SCOPE, "order_id": order_id, "created_at": stamp,
                        "revision": order["revision"], "evidence_epoch": order["evidence_epoch"],
                        "previous_photo_id": old["id"], "photo_id": new_photos[-1]["id"],
                        "created_photo_ids": [photo["id"] for photo in new_photos],
                        "inspection_scope": inspection_scope(order, new_photos[-1]),
                        "source": copy.deepcopy(order["demo_source"]), "physical_capture": False,
                        "requires_new_inference": True,
                    }
                    order.setdefault("public_replays", []).append(receipt)
                    self.store._save_human_operation(db, order_id, "public_replay", request, request_digest, receipt)
                    event(order, "public_photo_replayed", "공개 사진 재사용 · 새 AI 검증 필요 / 复用公开照片，需重新运行AI", receipt)
            committed = True
        finally:
            if not committed:
                for path in written:
                    path.unlink(missing_ok=True)
        order = self.store.get(order_id)
        return {"order": order, "photo": next(p for p in order["photos"] if p["id"] == receipt["photo_id"]),
                "replay": {**receipt, "replayed": replayed}}


def create_public_review_router(store, runtime, catalog=None):
    reviews = PublicReviews(store, runtime, catalog)
    router = APIRouter(prefix="/api/orders")

    @router.get("/{order_id}/public-review-summary")
    def summary(order_id: str):
        return reviews.summary(order_id)

    @router.post("/{order_id}/public-replay")
    def replay(order_id: str, body: PublicReplayRequest):
        return reviews.replay(order_id, body.model_dump())

    @router.post("/{order_id}/public-review")
    def review(order_id: str, body: PublicReviewRequest):
        return reviews.review(order_id, body.model_dump())

    return router
