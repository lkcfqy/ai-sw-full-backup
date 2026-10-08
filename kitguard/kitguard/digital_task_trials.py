"""Prospective public-photo task comparison, separate from physical field trials.

Author labels score a participant's final answer. They never enter model input.
The recorder does not perform inference and cannot certify a human identity.
"""
import copy
import hashlib
import json
import secrets
import statistics
from contextlib import contextmanager
from pathlib import Path
from time import monotonic
from typing import Annotated, Literal

from fastapi import APIRouter, Header
from fastapi.responses import Response
from pydantic import Field, StrictBool, StrictInt, model_validator

from . import __version__
from .field_api import Confirm, Counts, Input
from .public_demo_catalog import CATALOG
from .public_review import PublicReviews
from .regions import inspection_scope, verify_photo_lineage
from .store import StateError, now, uid

IDENTITY_KEYS = ("repo_id", "revision", "observer_protocol_sha256", "observation_mode", "image_max_side")
METHODS = ("manual", "kitguard")
CASES = (
    {"key": "quantity", "sample_id": "mixed-screws", "initial_bom": {"bolt": 2, "nut": 0, "washer": 0, "bracket": 0},
     "truth": {"bolt": 3, "nut": 0, "washer": 0, "bracket": 0}, "changed_bom": None},
    {"key": "identity", "sample_id": "small-part", "initial_bom": {"bolt": 2, "nut": 1, "washer": 0, "bracket": 0},
     "truth": {"bolt": 2, "nut": 1, "washer": 0, "bracket": 0}, "changed_bom": None},
    {"key": "revision", "sample_id": "bag-revision", "initial_bom": {"bolt": 3, "nut": 2, "washer": 2, "bracket": 0},
     "truth": {"bolt": 2, "nut": 2, "washer": 2, "bracket": 0},
     "changed_bom": {"bolt": 2, "nut": 2, "washer": 2, "bracket": 0}},
)
PROTOCOL = {
    "name": "public_photo_digital_tasks_v1", "tasks_per_participant": 6,
    "cases": CASES, "methods": METHODS,
    "allocation": "AB: manual then kitguard; BA: kitguard then manual; rotate cases by participant index modulo 3",
    "timing": "Server monotonic before image/BOM reveal through final submission; no pause; includes inference and review",
    "truth": "Frozen author-derived development labels from docs/v0.3/OWL_DEVELOPMENT_PROTOCOL.json; not official task labels",
    "revision": "Record an initial answer, reveal R2, invalidate R1 and explicitly replay the same photo; AI needs a fresh R2 check",
    "analysis": "Descriptive paired digital-task comparison; preserve all six planned tasks, failures and missing tasks",
    "physical_completion": False,
}
LIMITATIONS = [
    "仅比较公开照片的数字审查，不能证明实物作业、现场收益或新图准确率 / 공개 사진의 디지털 검토 비교이며 현장·새 이미지 성능을 입증하지 않습니다.",
    "照片已用于开发；同一人会重复看到照片。交替顺序减少顺序偏差，但不能消除学习效应 / 개발 사진 반복 노출이며 교차 순서가 학습 효과를 없애지 못합니다.",
    "参与者身份、同意及未求助其他工具均为本人声明；本地API不是隔离盲测 / 신원·동의·외부 도구 미사용은 자기 진술이며 인증된 맹검이 아닙니다.",
    "同一匿名编号的六个任务只算一个参与者。工程演练永远不计入真人结果 / 6개 과제는 1명이며 엔지니어링 리허설은 사람 결과에 포함되지 않습니다.",
    "耗时包含模型加载、等待及复核，关闭浏览器不暂停；服务重启的时间记为未知 / 모델 로드·대기·검토 포함, 브라우저 종료는 일시 정지가 아니며 서버 재시작 시간은 미확정입니다.",
    "帮助次数指本页帮助按钮使用次数；小样本不证明因果效果或统计显著 / 도움 횟수는 페이지 도움 버튼 사용 횟수이며 인과 효과·통계 유의성을 입증하지 않습니다.",
]
ACTIVE = {"preparing", "running", "changing"}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()


def allocation(code, index):
    rows = []
    for method in METHODS[::1 if index % 2 == 0 else -1]:
        for position in range(3):
            case = CASES[(position + index) % 3]
            rows.append({"id": f"T{len(rows)+1:02d}", "participant_code": code, "method": method,
                         "case_key": case["key"], "sample_id": case["sample_id"], "_case": copy.deepcopy(case),
                         "status": "not_started", "started_at": None, "finished_at": None, "elapsed_ms": None,
                         "order_id": None, "binding": None, "first_answer": None, "change_revealed_at": None,
                         "answer": None, "help_opens": 0, "evidence": None, "note": ""})
    return rows


def case_for(task):
    return task.get("_case") or next(c for c in CASES if c["key"] == task["case_key"])


def summarize(batch):
    result = {"planned_tasks": 6, "registered_participants": 1,
              "completed_self_reported_humans": int(batch["purpose"] == "self_reported_human" and
                                                      all(t["status"] == "completed" and t["evidence"]["protocol_eligible"]
                                                          for t in batch["tasks"])),
              "human_identity_verified": False, "physical_completion": False, "methods": {}, "pairs": [],
              "limitations": LIMITATIONS}
    for method in METHODS:
        rows = [t for t in batch["tasks"] if t["method"] == method]
        times = [t["elapsed_ms"] for t in rows if t["status"] == "completed" and t["elapsed_ms"] is not None]
        result["methods"][method] = {"planned": 3, "completed": 0, "correct": 0, "wrong": 0,
                                      "uncertain": 0, "failed": 0, "abandoned": 0, "interrupted": 0,
                                      "not_started": 0, "ineligible": 0, "version_errors": 0,
                                      "help_opens": sum(t["help_opens"] for t in rows),
                                      "completed_time_n": len(times),
                                      "completed_median_ms": statistics.median(times) if times else None}
        metric = result["methods"][method]
        for task in rows:
            metric[task["status"]] += 1
            if task["status"] != "completed":
                continue
            answer = task["answer"]
            case = case_for(task)
            bom = case["changed_bom"] or case["initial_bom"]
            expected_revision = 2 if case["changed_bom"] else 1
            expected_conclusion = "matched" if case["truth"] == bom else "mismatch"
            valid = task["evidence"]["protocol_eligible"]
            metric["ineligible"] += not valid
            metric["version_errors"] += answer["revision"] != expected_revision
            key = ("uncertain" if answer["conclusion"] == "needs_more_evidence" else "correct"
                   if valid and answer["counts"] == case["truth"] and answer["revision"] == expected_revision
                   and answer["conclusion"] == expected_conclusion else "wrong")
            metric[key] += 1
        metric["correct_fraction_full_planned"] = metric["correct"] / 3
    for case in batch["protocol"]["cases"]:
        pair = [next(t for t in batch["tasks"] if t["case_key"] == case["key"] and t["method"] == m)
                for m in METHODS]
        paired = all(t["status"] == "completed" and t["evidence"]["protocol_eligible"] and
                     t["elapsed_ms"] is not None for t in pair)
        result["pairs"].append({"case_key": case["key"], "both_completed_eligible": paired,
                                "kitguard_minus_manual_ms": pair[1]["elapsed_ms"] - pair[0]["elapsed_ms"]
                                if paired else None})
    # An automated rehearsal must never become a headline human-effect estimate.
    result["human_effect_estimate"] = None
    result["interpretation"] = "Descriptive participant task results only; no general improvement estimate"
    return result


class DigitalTaskTrials:
    def __init__(self, store, runtime_provider):
        self.store, self.runtime_provider = store, runtime_provider
        self.process_nonce = secrets.token_hex(16)
        # Keep frozen observer replay databases byte/schema compatible until
        # this separate recorder is explicitly used.

    def runtime(self):
        runtime = self.runtime_provider()
        return {k: runtime.get(k) for k in IDENTITY_KEYS}

    @staticmethod
    def _put(db, batch):
        db.execute("INSERT OR REPLACE INTO digital_task_batches VALUES (?,?)", (batch["id"], canonical(batch)))

    @staticmethod
    def _get(db, batch_id):
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='digital_task_batches'").fetchone():
            raise StateError("找不到数字试用 / 디지털 시험을 찾을 수 없습니다", 404)
        row = db.execute("SELECT body FROM digital_task_batches WHERE id=?", (batch_id,)).fetchone()
        if row is None:
            raise StateError("找不到数字试用 / 디지털 시험을 찾을 수 없습니다", 404)
        return json.loads(row["body"])

    @contextmanager
    def transaction(self, batch_id, token):
        db = self.store.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            batch = self._get(db, batch_id)
            if not secrets.compare_digest(sha(token), batch["_token_sha256"]):
                raise StateError("试用入口无效 / 시험 접근 토큰 오류", 403)
            yield db, batch
            self._put(db, batch)
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def task(batch, task_id, statuses):
        if batch["status"] != "open":
            raise StateError("试用已关闭 / 시험이 종료되었습니다")
        task = next((t for t in batch["tasks"] if t["id"] == task_id), None)
        if task is None or task["status"] not in statuses:
            raise StateError("任务状态已改变 / 과제 상태가 변경되었습니다")
        return task

    @staticmethod
    def view(batch):
        value = copy.deepcopy(batch)
        value.pop("_token_sha256")
        if value["status"] != "closed":
            value["protocol"]["cases"] = [{"key": c["key"]} for c in value["protocol"]["cases"]]
        for task in value["tasks"]:
            task.pop("_case", None)
            task.pop("_monotonic_started", None)
            task.pop("_process_nonce", None)
            task.pop("_preparation_nonce", None)
            if task["status"] == "not_started":
                task.pop("sample_id")
            if value["status"] != "closed":
                task.pop("evidence")
        value["report"] = summarize(batch) if value["status"] == "closed" else None
        return value

    def get(self, batch_id, token):
        with self.transaction(batch_id, token) as (_, batch):
            return self.view(batch)

    def create(self, body):
        token = secrets.token_urlsafe(32)
        batch = {**body, "id": uid("digital_trial"), "created_at": now(), "closed_at": None,
                 "status": "open", "app_version": __version__, "protocol": copy.deepcopy(PROTOCOL),
                 "protocol_sha256": sha(canonical(PROTOCOL)), "recorder_source_sha256": sha(Path(__file__).read_bytes()),
                 "runtime_identity": self.runtime(), "_token_sha256": sha(token),
                 "source_catalog": copy.deepcopy(CATALOG), "limitations": LIMITATIONS,
                 "tasks": allocation(body["participant_code"], body["allocation_index"])}
        with self.store.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS digital_task_batches (id TEXT PRIMARY KEY, body TEXT NOT NULL)")
            self._put(db, batch)
        return {"batch": self.view(batch), "token": token}

    def start(self, batch_id, task_id, token):
        with self.transaction(batch_id, token) as (db, batch):
            task = self.task(batch, task_id, {"not_started"})
            pending = next(t for t in batch["tasks"] if t["status"] == "not_started")
            if pending["id"] != task_id:
                raise StateError("请按预定顺序执行 / 예정 순서로 실행하세요")
            for row in db.execute("SELECT body FROM digital_task_batches"):
                if any(t["status"] in ACTIVE for t in json.loads(row["body"])["tasks"]):
                    raise StateError("本机还有进行中的数字任务 / 이 기기에 진행 중인 디지털 과제가 있습니다")
            task.update(status="preparing", started_at=now(), _monotonic_started=monotonic(),
                        _process_nonce=self.process_nonce, _preparation_nonce=secrets.token_hex(16))
            return copy.deepcopy(task)

    def attach(self, batch_id, task_id, token, prepared):
        with self.transaction(batch_id, token) as (_, batch):
            task = self.task(batch, task_id, {"preparing", "changing"})
            order = prepared["order"]
            photo = order["photos"][-1]
            if task["status"] == "changing" and order["id"] != task["order_id"]:
                raise StateError("改版工单不一致 / 변경 주문 불일치")
            task.update(status="running", order_id=order["id"], binding={
                "revision": order["revision"], "photo_id": photo["id"], "photo_sha256": photo["sha256"],
                "evidence_epoch": order["evidence_epoch"], "requirements": order["requirements"],
                "photo_url": photo["url"]})
        return self.get(batch_id, token)

    def bound_order(self, db, batch, task, *, require_check=False):
        order = self.store._get(db, task["order_id"])
        binding = task["binding"]
        photo = order["photos"][-1]
        spec = next(s for s in CATALOG if s["sample_id"] == task["sample_id"])
        root, _ = verify_photo_lineage(self.store, order, photo, db)
        if (order["revision"] != binding["revision"] or order["requirements"] != binding["requirements"]
                or photo["id"] != binding["photo_id"] or photo["sha256"] != binding["photo_sha256"]
                or order["evidence_epoch"] != binding["evidence_epoch"] or order["references"]
                or root["source_sha256"] != spec["source_sha256"]
                or inspection_scope(order, photo)["mode"] != "whole_image"):
            raise StateError("试用照片、范围或工单在外部改变 / 시험 사진·범위·주문이 외부에서 변경되었습니다")
        if order["active_inspection"]:
            raise StateError("请等核验结束，等待计入用时 / 검사가 끝날 때까지 기다리세요; 대기도 시간에 포함됩니다")
        if require_check:
            check = order.get("latest_check")
            if (not check or not check.get("valid") or check["photo_id"] != photo["id"]
                    or check.get("photo_sha256") != photo["sha256"] or check["revision"] != order["revision"]
                    or check.get("evidence_epoch") != order["evidence_epoch"]
                    or check.get("requirements_snapshot") != order["requirements"]
                    or check.get("inspection_scope") != inspection_scope(order, photo)):
                raise StateError("请先执行当前版本的AI核验 / 먼저 현재 버전의 AI 검사를 실행하세요")
            if batch["purpose"] == "self_reported_human" and not self.eligible_check(check, batch):
                raise StateError("真人对照需要冻结身份的本机MLX模型，测试替身不能计入 / 사람 비교에는 고정된 로컬 MLX 모델이 필요합니다")
        return order

    def eligible_check(self, check, batch):
        identity = {k: check.get("runtime_identity", {}).get(k) for k in IDENTITY_KEYS}
        return (check.get("backend") == "mlx" and all(v is not None for v in identity.values())
                and identity == batch["runtime_identity"] == self.runtime())

    def first_answer(self, batch_id, task_id, token, answer):
        with self.transaction(batch_id, token) as (db, batch):
            task = self.task(batch, task_id, {"running"})
            if task["case_key"] != "revision" or task["first_answer"] is not None:
                raise StateError("此任务不需要首轮回答，或已经记录 / 첫 응답이 필요하지 않거나 이미 기록되었습니다")
            order = self.bound_order(db, batch, task, require_check=task["method"] == "kitguard")
            task["first_answer"] = {**answer, "recorded_at": now(), "check": copy.deepcopy(order.get("latest_check"))}
        return self.get(batch_id, token)

    def reveal_change(self, batch_id, task_id, token):
        with self.transaction(batch_id, token) as (db, batch):
            task = self.task(batch, task_id, {"running"})
            if not task["first_answer"] or task["change_revealed_at"]:
                raise StateError("先记录首轮回答；改版只揭示一次 / 먼저 첫 응답을 기록하세요; 변경은 한 번만 공개됩니다")
            self.bound_order(db, batch, task)
            task.update(status="changing", change_revealed_at=now())
            order_id = task["order_id"]
            target = case_for(task)["changed_bom"]
        order = self.store.revise(order_id, target, "Fixed public-photo digital-task R2 requirement change", 1)
        photo = order["photos"][-1]
        prepared = PublicReviews(self.store, self.runtime_provider, catalog=CATALOG).replay(order_id, {
            "expected_revision": 2, "expected_photo_id": photo["id"],
            "expected_evidence_epoch": order["evidence_epoch"], "confirmed_no_physical_capture": True,
            "idempotency_key": f"{batch_id}-{task_id}-R2"})
        return self.attach(batch_id, task_id, token, prepared)

    def help(self, batch_id, task_id, token):
        with self.transaction(batch_id, token) as (_, batch):
            self.task(batch, task_id, {"running"})["help_opens"] += 1
        return self.get(batch_id, token)

    def finish(self, batch_id, task_id, token, body):
        with self.transaction(batch_id, token) as (db, batch):
            task = self.task(batch, task_id, ACTIVE)
            order = self.store._get(db, task["order_id"]) if task["order_id"] else None
            if order and order.get("active_inspection"):
                raise StateError("核验仍在运行，不能提前停止计时 / 검사가 진행 중이므로 시간을 먼저 멈출 수 없습니다")
            eligible = False
            if body["outcome"] == "completed":
                if task["status"] != "running" or (task["case_key"] == "revision" and not task["change_revealed_at"]):
                    raise StateError("请完成任务改版步骤 / 과제의 변경 단계를 완료하세요")
                order = self.bound_order(db, batch, task, require_check=task["method"] == "kitguard")
                eligible = (not order["checks"] and not any(e["kind"] == "inspection_started" for e in order["events"])) \
                    if task["method"] == "manual" else self.eligible_check(order["latest_check"], batch)
                task["answer"] = body["answer"]
            task.update(status=body["outcome"], finished_at=now(),
                        elapsed_ms=round((monotonic() - task["_monotonic_started"]) * 1000)
                        if task.get("_process_nonce") == self.process_nonce else None,
                        note=body["note"], evidence={"protocol_eligible": bool(eligible),
                            "checks": copy.deepcopy(order["checks"]) if order else [],
                            "order_events": copy.deepcopy(order["events"]) if order else [],
                            "binding": copy.deepcopy(task["binding"])})
        return self.get(batch_id, token)

    def close(self, batch_id, token):
        with self.transaction(batch_id, token) as (_, batch):
            if batch["status"] != "open" or any(t["status"] in ACTIVE for t in batch["tasks"]):
                raise StateError("先结束当前任务再关闭；关闭后不能重开 / 현재 과제를 종료한 후 닫으세요; 다시 열 수 없습니다")
            batch.update(status="closed", closed_at=now())
        return self.get(batch_id, token)

    def recover_interrupted(self):
        with self.store.connect() as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='digital_task_batches'").fetchone():
                return
            for row in db.execute("SELECT body FROM digital_task_batches").fetchall():
                batch = json.loads(row["body"])
                changed = False
                for task in batch["tasks"]:
                    if task["status"] in ACTIVE:
                        task.update(status="interrupted", finished_at=now(), elapsed_ms=None,
                                    note="Server restarted; elapsed time is unknown")
                        changed = True
                if changed:
                    self._put(db, batch)


Code = Annotated[str, Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")]


class Create(Input):
    participant_code: Code
    purpose: Literal["self_reported_human", "engineering_rehearsal"]
    allocation_index: StrictInt = Field(ge=0, le=99)
    consent_confirmed: StrictBool

    @model_validator(mode="after")
    def declared_source(self):
        if self.consent_confirmed != (self.purpose == "self_reported_human"):
            raise ValueError("真人需自愿同意；工程演练不得声明真人同意 / 사람은 자발적 동의, 리허설은 사람 동의를 선언하지 않습니다")
        return self


class Answer(Input):
    counts: Counts | None
    revision: StrictInt = Field(ge=1, le=2)
    conclusion: Literal["matched", "mismatch", "needs_more_evidence"]

    @model_validator(mode="after")
    def definite_counts(self):
        if self.conclusion != "needs_more_evidence" and self.counts is None:
            raise ValueError("明确结论需要四类数量 / 명확한 결론에는 네 종류 수량이 필요합니다")
        return self


class Finish(Input):
    outcome: Literal["completed", "failed", "abandoned"]
    answer: Answer | None = None
    note: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def terminal_answer(self):
        if (self.outcome == "completed") != (self.answer is not None):
            raise ValueError("仅完成任务提供回答 / 완료 과제에만 응답을 제공하세요")
        if self.outcome != "completed" and not self.note:
            raise ValueError("失败或放弃请写原因 / 실패·포기 사유를 입력하세요")
        return self


def digital_task_router(trials, prepare):
    router = APIRouter(prefix="/api/digital-task-trials")
    Token = Annotated[str, Header(alias="X-Digital-Trial-Token", min_length=16, max_length=200)]

    @router.post("", status_code=201)
    def create(body: Create):
        return trials.create(body.model_dump())

    @router.get("/{batch_id}")
    def get(batch_id: str, token: Token):
        return {"batch": trials.get(batch_id, token)}

    @router.post("/{batch_id}/tasks/{task_id}/start")
    async def start(batch_id: str, task_id: str, body: Confirm, token: Token):
        task = trials.start(batch_id, task_id, token)
        try:
            prepared = await prepare(task, batch_id)
            return {"batch": trials.attach(batch_id, task_id, token, prepared)}
        except BaseException:
            trials.finish(batch_id, task_id, token, {"outcome": "failed", "answer": None,
                                                  "note": "Public-photo preparation failed; retained in denominator"})
            raise

    @router.post("/{batch_id}/tasks/{task_id}/first-answer")
    def first(batch_id: str, task_id: str, body: Answer, token: Token):
        return {"batch": trials.first_answer(batch_id, task_id, token, body.model_dump())}

    @router.post("/{batch_id}/tasks/{task_id}/reveal-change")
    def change(batch_id: str, task_id: str, body: Confirm, token: Token):
        return {"batch": trials.reveal_change(batch_id, task_id, token)}

    @router.post("/{batch_id}/tasks/{task_id}/help")
    def help_open(batch_id: str, task_id: str, body: Confirm, token: Token):
        return {"batch": trials.help(batch_id, task_id, token)}

    @router.post("/{batch_id}/tasks/{task_id}/finish")
    def finish(batch_id: str, task_id: str, body: Finish, token: Token):
        return {"batch": trials.finish(batch_id, task_id, token, body.model_dump())}

    @router.post("/{batch_id}/close")
    def close(batch_id: str, body: Confirm, token: Token):
        return {"batch": trials.close(batch_id, token)}

    @router.get("/{batch_id}/export")
    def export(batch_id: str, token: Token):
        batch = trials.get(batch_id, token)
        if batch["status"] != "closed":
            raise StateError("关闭后才能导出结果 / 종료 후 결과를 내보내세요")
        return Response(json.dumps(batch, ensure_ascii=False, indent=2), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="kitguard-{batch_id}-digital-tasks.json"',
                                 "Cache-Control": "no-store"})
    return router
