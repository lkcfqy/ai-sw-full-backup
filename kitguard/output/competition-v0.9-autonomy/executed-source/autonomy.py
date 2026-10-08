"""A bounded public-photo agent mission using the ordinary durable inference path.

The planner is an explicit state machine, not generated hidden reasoning. It never
uses author truth, confirms a human review, changes a BOM from model output, or
completes a physical order. Planned R2 is a disclosed simulated incoming change.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import html
import json
import logging
import re
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import Field
from starlette.background import BackgroundTask

from . import __version__
from .digital_review_state import IDENTITY_KEYS, current_digital_check, digest
from .field_api import Confirm, Input
from .inspection_jobs import JobRequest
from .public_review import PublicReviews
from .regions import verify_photo_lineage
from .store import StateError, now, uid

log = logging.getLogger(__name__)
CASES = (
    {"id": "quantity", "sample_id": "mixed-screws",
     "bom": {"bolt": 2, "nut": 0, "washer": 0, "bracket": 0}, "revision_bom": None},
    {"id": "identity", "sample_id": "small-part",
     "bom": {"bolt": 2, "nut": 1, "washer": 0, "bracket": 0}, "revision_bom": None},
    {"id": "revision", "sample_id": "bag-revision",
     "bom": {"bolt": 3, "nut": 2, "washer": 2, "bracket": 0},
     "revision_bom": {"bolt": 2, "nut": 2, "washer": 2, "bracket": 0}},
)
PROTOCOL = {
    "name": "public_photo_autonomous_mission_v1", "cases": CASES,
    "goal": "Produce current-version machine findings and an inspectable digital evidence package.",
    "plan": ["verify_source_and_create_order", "run_local_vision", "route_from_saved_check",
             "if_planned_change_invalidate_replay_and_run_again", "package_machine_evidence"],
    "revision_policy": "R2 is fixed before execution, never inferred or silently approved from an AI count.",
    "uncertainty_policy": "Stop that case at needs_more_evidence; do not repeatedly infer the same pixels to force agreement.",
    "timing": "Server monotonic for the entire mission, includes preparation and all model waits; restart is unknown.",
    "scope": "Known public development photos; engineering execution, not a new accuracy or human benefit study.",
}
LIMITATIONS = [
    "This is automatic engineering execution on previously exposed public development photos; human participants = 0.",
    "The rule planner routes real model findings. It does not certify correctness, independently review the image, or repair a scene.",
    "Same-photo R2 replay is declared simulation, not a new capture. No physical completion or user-efficiency claim.",
    "An archived finding describes its saved snapshot. A later order, photo, check or runtime change makes it historical.",
]
TERMINAL = {"completed", "failed", "cancelled", "interrupted"}


def route_check(check):
    """Route from the saved check's decision; never from a case's expected answer."""
    decision = check["decision"]
    if decision == "ready":
        return {"finding": "quantities_match", "next_action": "package_findings",
                "reason": "All four visible coarse-category counts match this BOM; digital evidence only."}
    if decision == "correct":
        return {"finding": "quantity_difference", "next_action": "list_differences",
                "reason": "The stored count comparison has a nonzero difference; preserve the BOM and list the differences."}
    if decision in {"recapture", "manual"}:
        return {"finding": "needs_more_evidence", "next_action": "request_more_evidence",
                "reason": "The stored observation is uncertain or requires review; these same pixels cannot resolve it by assertion."}
    raise StateError("알 수 없는 검사 분기 / 无法识别核验分支")


class Start(Input):
    scenario: Literal["all", "quantity", "identity", "revision"] = "all"
    request_key: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")


class AutonomousMissions:
    def __init__(self, store, runtime, gate, jobs, prepare, catalog):
        self.store, self.runtime, self.gate, self.jobs, self.prepare = store, runtime, gate, jobs, prepare
        self.reviews = PublicReviews(store, runtime, catalog)
        self.tasks, self.live = {}, {}
        self.closing = False

    def _exists(self, db):
        return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='autonomous_missions'").fetchone()

    def _save(self, run):
        with self.store.connect() as db:
            db.execute("UPDATE autonomous_missions SET body=? WHERE id=?",
                       (json.dumps(run, ensure_ascii=False, allow_nan=False), run["id"]))

    def _read(self, run_id):
        with self.store.connect() as db:
            row = db.execute("SELECT body FROM autonomous_missions WHERE id=?", (run_id,)).fetchone() if self._exists(db) else None
        if row is None:
            raise StateError("자율 과제를 찾을 수 없습니다 / 找不到自主任务", 404)
        return json.loads(row["body"])

    def list(self):
        with self.store.connect() as db:
            rows = db.execute("SELECT body FROM autonomous_missions ORDER BY rowid DESC LIMIT 20").fetchall() if self._exists(db) else []
        return [{k: r[k] for k in ("id", "status", "scenario", "created_at", "finished_at", "elapsed_ms")}
                for r in (json.loads(row["body"]) for row in rows)]

    def get(self, run_id):
        run = self._read(run_id)
        for case in run["cases"]:
            case["live_binding"] = self.audit(case)
        return run

    def audit(self, case):
        if not case.get("snapshot"):
            return {"status": "not_recorded", "reason": None}
        try:
            saved = case["snapshot"]["latest_check"]
            current = self.store.get(case["order_id"])
            check = self.reviews._current_check(current)
            if digest(check) != digest(saved):
                raise StateError("핵심 검사가 변경되었습니다 / 已有新的核验结果")
            return {"status": "current", "reason": None}
        except (StateError, OSError) as exc:
            return {"status": "historical", "reason": str(exc)}

    def start(self, body):
        key, request_hash = body.request_key, digest({"scenario": body.scenario})
        with self.store.connect() as db:
            if self._exists(db):
                old = db.execute("SELECT digest, body FROM autonomous_missions WHERE request_key=?", (key,)).fetchone()
                if old:
                    if old["digest"] != request_hash:
                        raise StateError("요청 키를 다른 계획에 재사용할 수 없습니다 / 请求键不能用于不同计划")
                    return {"run": self.get(json.loads(old["body"])["id"]), "replayed": True}
        runtime = self.runtime()
        if (self.closing or not runtime.get("available") or self.gate.status()["busy"]):
            raise StateError("모델이 준비되지 않았거나 처리 중입니다 / 模型尚未就绪或正在处理，请稍后重试", 503)
        if (any(runtime.get(k) is None for k in IDENTITY_KEYS)
                or re.fullmatch(r"[a-f0-9]{64}", str(runtime.get("observer_protocol_sha256"))) is None):
            raise StateError("실제 모델 식별 정보가 필요합니다 / 需要完整的实际模型身份", 503)
        selected = [copy.deepcopy(c) for c in CASES if body.scenario in {"all", c["id"]}]
        run = {"schema_version": 1, "id": uid("mission"), "version": __version__,
               "scenario": body.scenario, "status": "running", "created_at": now(), "finished_at": None,
               "elapsed_ms": None, "cancel_requested": False, "purpose": "engineering_rehearsal",
               "human_participants": 0, "physical_completions": 0,
               "runtime_identity": {k: runtime.get(k) for k in IDENTITY_KEYS},
               "protocol": copy.deepcopy(PROTOCOL), "protocol_sha256": digest(PROTOCOL),
               "planned_cases": len(selected), "planned_checks": sum(2 if c["revision_bom"] else 1 for c in selected),
               "cases": [{**c, "status": "not_started", "order_id": None, "finding": None,
                          "steps": [], "checks": [], "snapshot": None, "error": None} for c in selected],
               "limitations": LIMITATIONS, "error": None}
        # Optional feature: no table is added to untouched historical databases.
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE IF NOT EXISTS autonomous_missions (id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL, digest TEXT NOT NULL, body TEXT NOT NULL)")
            active = [json.loads(row["body"]) for row in db.execute("SELECT body FROM autonomous_missions")]
            if any(r["status"] == "running" for r in active):
                raise StateError("자율 과제가 진행 중입니다 / 已有自主任务正在运行")
            db.execute("INSERT INTO autonomous_missions VALUES (?,?,?,?)", (run["id"], key, request_hash, json.dumps(run, ensure_ascii=False)))
        self.live[run["id"]] = run
        task = asyncio.create_task(self._execute(run))
        self.tasks[run["id"]] = task
        task.add_done_callback(lambda done: self._done(run, done))
        return {"run": copy.deepcopy(run), "replayed": False}

    def _done(self, run, task):
        self.tasks.pop(run["id"], None)
        self.live.pop(run["id"], None)
        if not task.cancelled():
            task.exception()
        if run["status"] == "running":
            self._interrupt(run)

    def _interrupt(self, run):
        run.update(status="interrupted", elapsed_ms=None, finished_at=now(),
                   error="서비스가 중단되었습니다 / 服务停止；保留已执行步骤，整次耗时未知")
        for case in run["cases"]:
            if case["status"] == "running":
                case["status"] = "interrupted"
                for step in case["steps"]:
                    if step["status"] == "running":
                        step.update(status="interrupted", finished_at=now())
        self._save(run)

    def recover_interrupted(self):
        self.closing = False
        for row in self.list():
            if row["status"] == "running":
                self._interrupt(self._read(row["id"]))

    async def close(self):
        self.closing = True
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def cancel(self, run_id):
        run = self.live.get(run_id)
        if run is not None and run["status"] == "running":
            run["cancel_requested"] = True
            self._save(run)
        return self.get(run_id)

    def _step(self, run, case, tool, reason, binding=None):
        step = {"index": len(case["steps"]) + 1, "tool": tool, "reason": reason,
                "status": "running", "started_at": now(), "finished_at": None,
                "binding": binding, "result": None}
        case["steps"].append(step)
        self._save(run)
        return step

    def _finish_step(self, run, step, result):
        step.update(status="completed", finished_at=now(), result=result)
        self._save(run)

    def _guard(self, run):
        if run["cancel_requested"]:
            raise asyncio.CancelledError
        self._guard_identity(run)

    async def _observe(self, run, case, order):
        self._guard(run)
        photo = order["photos"][-1]
        step = self._step(run, case, "local_vision", "A fresh check is required for this exact version and photograph.",
                          {"order_id": order["id"], "revision": order["revision"], "photo_id": photo["id"],
                           "photo_sha256": photo["sha256"], "evidence_epoch": order["evidence_epoch"]})
        started = self.jobs.start(order["id"], JobRequest(photo_id=photo["id"], expected_revision=order["revision"],
                                  request_key=f'{run["id"]}_{case["id"]}_R{order["revision"]}'))
        step["job_id"] = started["job"]["id"]
        self._save(run)
        while True:
            job = self.jobs.get(step["job_id"])
            if job["status"] != "running":
                break
            # Cancel stops follow-on tools; the actual model thread keeps its gate
            # until it returns. Browser closure never cancels this coroutine.
            await asyncio.sleep(0.15)
        if job["status"] != "succeeded":
            raise StateError(str(job.get("error") or job["status"]), 503)
        self._guard_identity(run)
        current = self.store.get(order["id"])
        check = self.reviews._current_check(current)
        if (check["id"] != job["check_id"] or check["revision"] != order["revision"]
                or check["photo_id"] != photo["id"] or current["requirements"] != order["requirements"]):
            raise StateError("실행 중 증거가 변경되었습니다 / 执行期间订单或证据改变")
        case["checks"].append(copy.deepcopy(check))
        self._finish_step(run, step, {"check_id": check["id"], "decision": check["decision"],
                                    "latency_ms": check["latency_ms"], "check_sha256": digest(check)})
        routing = route_check(check)
        branch = self._step(run, case, routing["next_action"], routing["reason"], {"check_id": check["id"]})
        self._finish_step(run, branch, {"finding": routing["finding"], "differences": check["differences"],
                                      "uncertain_action": check["action"] if routing["finding"] == "needs_more_evidence" else None})
        case["finding"], case["snapshot"] = routing["finding"], copy.deepcopy(current)
        self._save(run)
        self._guard(run)
        return current

    def _guard_identity(self, run):
        runtime = self.runtime()
        if {k: runtime.get(k) for k in IDENTITY_KEYS} != run["runtime_identity"]:
            raise StateError("모델 구성이 변경되었습니다 / 执行期间模型身份或观察协议改变")

    async def _execute(self, run):
        started = time.monotonic()
        case, step = None, None
        try:
            for case in run["cases"]:
                self._guard(run)
                case["status"] = "running"
                step = self._step(run, case, "prepare_public_photo", "Use the frozen public source and predeclared BOM, not a cached prediction.")
                prepared = await self.prepare(case, run["id"])
                order = prepared["order"]
                case["order_id"] = order["id"]
                self._finish_step(run, step, {"order_id": order["id"], "photo_id": prepared["photo"]["id"],
                                            "source": order["demo_source"]})
                current = await self._observe(run, case, order)
                if case["revision_bom"]:
                    self._guard(run)
                    # The plan, not the model, authorizes this simulated incoming change.
                    step = self._step(run, case, "apply_planned_revision", "Apply the predeclared simulated R2 and prove the old check is no longer current.",
                                      {"expected_revision": current["revision"], "previous_check_id": current["latest_check"]["id"]})
                    current = self.store.revise(current["id"], case["revision_bom"],
                                                "AUTONOMOUS MISSION: predeclared simulated R2; not an AI-derived BOM correction", 1)
                    if current_digital_check(current, runtime_identity=self.runtime()) is not None or current["latest_check"]["valid"]:
                        raise StateError("이전 검사가 아직 유효합니다 / 改版后旧核验未失效")
                    case["stale_check_rejected"] = True
                    self._finish_step(run, step, {"revision": current["revision"], "old_check_valid": False})
                    step = self._step(run, case, "replay_verified_photo", "Same pixels, declared no new physical capture; the new revision requires new inference.")
                    result = self.reviews.replay(current["id"], {"expected_revision": current["revision"],
                        "expected_photo_id": current["photos"][-1]["id"], "expected_evidence_epoch": current["evidence_epoch"],
                        "confirmed_no_physical_capture": True, "idempotency_key": run["id"] + ":R2"})
                    self._finish_step(run, step, {"replay_id": result["replay"]["id"], "photo_id": result["photo"]["id"], "physical_capture": False})
                    await self._observe(run, case, result["order"])
                case["status"] = "completed"
                self._save(run)
            run["status"] = "completed"
        except asyncio.CancelledError:
            if self.closing:
                self._interrupt(run)
                return
            run["status"] = "cancelled"
            if case is not None and case["status"] == "running":
                case["status"] = "cancelled"
        except Exception as exc:
            log.exception("Autonomous mission failed")
            run.update(status="failed", error=str(exc))
            if case is not None and case["status"] == "running":
                case.update(status="failed", error=str(exc))
                for entry in case["steps"]:
                    if entry["status"] == "running":
                        entry.update(status="failed", finished_at=now(), result={"error": str(exc)})
        run.update(finished_at=now(), elapsed_ms=round((time.monotonic() - started) * 1000))
        self._save(run)

    def archive(self, run_id):
        run = self.get(run_id)
        if run["status"] not in TERMINAL:
            raise StateError("과제 종료 후 내보내세요 / 任务结束后才能导出")
        payload = {"exported_at": now(), "binding_scope": "saved_mission_snapshots_with_live_audit_at_export", "run": run}
        files = {"mission.json": (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode()}
        for case in run["cases"]:
            order = case.get("snapshot")
            if order is None:
                continue
            for photo in order["photos"]:
                if re.fullmatch(r"[A-Za-z0-9_-]{1,100}", photo["id"]) is None:
                    raise StateError("사진 식별자가 올바르지 않습니다 / 照片标识无效")
                verify_photo_lineage(self.store, order, photo)
                raw = self.store.photo_path(photo["id"]).read_bytes()
                if hashlib.sha256(raw).hexdigest() != photo["sha256"]:
                    raise StateError("사진 무결성 실패 / 照片完整性校验失败")
                files[f'photos/{photo["id"]}.jpg'] = raw
        files["index.html"] = render_archive(run).encode()
        files["SHA256.json"] = (json.dumps({"schema_version": 1, "files": [{"path": k, "bytes": len(v),
                                    "sha256": hashlib.sha256(v).hexdigest()} for k, v in files.items()]}, indent=2) + "\n").encode()
        with tempfile.NamedTemporaryFile(prefix="kitguard-mission-", suffix=".zip", delete=False) as file:
            path = Path(file.name)
        try:
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                for name, value in files.items():
                    z.writestr(name, value)
            return path
        except BaseException:
            path.unlink(missing_ok=True)
            raise


def render_archive(run):
    esc = html.escape
    cards = []
    for case in run["cases"]:
        order = case.get("snapshot")
        photo = order["photos"][-1] if order else None
        check = order["latest_check"] if order else None
        rows = "".join(f'<tr><th>{p}</th><td>{order["requirements"][p]}</td><td>{check["observed"][p] if check["observed"][p] is not None else "?"}</td></tr>'
                       for p in ("bolt", "nut", "washer", "bracket")) if check else ""
        steps = "".join(f'<li><b>{esc(s["tool"])}</b> · {esc(s["status"])}<p>{esc(s["reason"])}</p><pre>{esc(json.dumps(s["result"], ensure_ascii=False, indent=2))}</pre></li>' for s in case["steps"])
        cards.append(f'<section><h2>{esc(case["id"])} · {esc(case["status"])} · {esc(case["finding"] or "—")}</h2>'
                     f'<p>Binding at export: {esc(case["live_binding"]["status"])}</p>'
                     + (f'<img src="photos/{esc(photo["id"])}.jpg" alt="{esc(case["id"])}"><p>R{order["revision"]} · {esc(check["id"])} · {check["latency_ms"]}ms</p><table><tr><th>Part</th><th>BOM</th><th>AI</th></tr>{rows}</table>' if check else "")
                     + f'<ol>{steps}</ol></section>')
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>KitGuard autonomous mission</title><style>body{max-width:980px;margin:40px auto;padding:0 22px;background:#f6f8f6;color:#173b35;font:16px system-ui}section{background:white;padding:24px;margin:24px 0;border:1px solid #dae4de;border-radius:16px}img{max-width:100%;max-height:340px}table{border-collapse:collapse}th,td{padding:8px 24px;border-bottom:1px solid #ddd}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}li{margin:18px 0}a{color:#12654d}</style>' + f'<h1>KitGuard · Autonomous mission</h1><p>{esc(run["id"])} · {esc(run["status"])} · {run["elapsed_ms"]}ms</p><p>{run["planned_cases"]} planned cases · {run["planned_checks"]} planned checks · 0 humans · 0 physical completions</p><p>工程执行 / 엔지니어링 실행. Known development photos; no new accuracy or human benefit claim.</p><p><a href="mission.json">Full snapshots and tool results</a> · <a href="SHA256.json">File checksums</a></p>' + "".join(cards) + "<ul>" + "".join(f'<li>{esc(s)}</li>' for s in run["limitations"]) + "</ul></html>"


def create_autonomy_router(missions):
    router = APIRouter(prefix="/api/autonomous-missions")

    @router.get("")
    async def listing():
        return {"runs": missions.list(), "protocol": PROTOCOL}

    @router.post("", status_code=202)
    async def start(body: Start):
        return missions.start(body)

    @router.get("/{run_id}")
    async def get(run_id: str):
        return {"run": missions.get(run_id)}

    @router.post("/{run_id}/cancel")
    async def cancel(run_id: str, body: Confirm):
        return {"run": missions.cancel(run_id)}

    @router.get("/{run_id}/evidence.zip")
    async def evidence(run_id: str):
        path = await asyncio.to_thread(missions.archive, run_id)
        return FileResponse(path, media_type="application/zip", filename=f"kitguard-{run_id}-evidence.zip",
                            background=BackgroundTask(path.unlink, missing_ok=True))

    return router
