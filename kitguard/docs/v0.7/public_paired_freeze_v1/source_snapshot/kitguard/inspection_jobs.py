"""Durable, idempotent inspection requests; browser disconnects do not stop work."""

import asyncio
import hashlib
import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import Field

from .schemas import Inspection
from .store import StateError, now, uid

log = logging.getLogger(__name__)


class JobRequest(Inspection):
    request_key: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")


class InspectionJobs:
    def __init__(self, store, gate):
        self.store, self.gate = store, gate
        self.tasks = set()
        self.runner = None
        self._closing = False
        with store.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS inspection_jobs (
                id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL,
                digest TEXT NOT NULL, order_id TEXT NOT NULL, body TEXT NOT NULL
            )""")

    def _save(self, job):
        with self.store.connect() as db:
            db.execute("UPDATE inspection_jobs SET body=? WHERE id=?",
                       (json.dumps(job, ensure_ascii=False), job["id"]))

    def get(self, job_id):
        with self.store.connect() as db:
            row = db.execute("SELECT body FROM inspection_jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise StateError("검사 작업을 찾을 수 없습니다 / 找不到核验任务", 404)
        return json.loads(row["body"])

    def list(self, order_id):
        self.store.get(order_id)
        with self.store.connect() as db:
            rows = db.execute("SELECT body FROM inspection_jobs WHERE order_id=? ORDER BY rowid DESC LIMIT 10",
                              (order_id,)).fetchall()
        return [json.loads(row["body"]) for row in rows]

    def recover_interrupted(self):
        self._closing = False
        with self.store.connect() as db:
            rows = db.execute("SELECT body FROM inspection_jobs").fetchall()
        for row in rows:
            job = json.loads(row["body"])
            if job["status"] == "running":
                job.update(status="interrupted", finished_at=now(),
                           error={"status_code": 503, "message": "서비스가 재시작되었습니다. 새 요청으로 다시 확인하세요 / 服务已重启，请重新核验"})
                self._save(job)

    async def close(self):
        # Stop admission before yielding to cancellation. Otherwise a request
        # could reserve the slot released by a cancelled task while close() is
        # still awaiting its original task snapshot, and escape shutdown.
        self._closing = True
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def start(self, order_id, body):
        request = body.model_dump()
        digest = hashlib.sha256(json.dumps({"order_id": order_id, **request}, sort_keys=True).encode()).hexdigest()
        # No await occurs before the task is scheduled. Concurrent HTTP requests
        # on the one local event loop cannot insert the same key twice.
        with self.store.connect() as db:
            previous = db.execute("SELECT digest, body FROM inspection_jobs WHERE request_key=?",
                                  (body.request_key,)).fetchone()
        if previous:
            if previous["digest"] != digest:
                raise StateError("요청 키를 다른 사진·버전에 재사용할 수 없습니다 / 请求键不能用于不同照片或版本")
            return {"job": json.loads(previous["body"]), "replayed": True}
        if self._closing:
            raise StateError("서비스가 종료 중입니다 / 服务正在停止，请重新连接后再核验", 503)
        slot = self.gate.reserve()
        token = None
        try:
            token, snapshot = self.store.begin_inspection(order_id, body.photo_id, body.expected_revision)
            job = {"id": uid("job"), "request_key": body.request_key, "order_id": order_id,
                   "revision": body.expected_revision, "photo_id": body.photo_id,
                   "photo_sha256": snapshot["photos"][-1]["sha256"],
                   "evidence_epoch": snapshot["evidence_epoch"], "inspection_token": token,
                   "status": "running", "created_at": now(), "finished_at": None,
                   "check_id": None, "error": None}
            with self.store.connect() as db:
                db.execute("INSERT INTO inspection_jobs VALUES (?,?,?,?,?)",
                           (job["id"], body.request_key, digest, order_id, json.dumps(job, ensure_ascii=False)))
            task = asyncio.create_task(self._run(job, body, token, snapshot, slot))
            self.tasks.add(task)
            task.add_done_callback(lambda completed: self._done(completed, job, token, slot))
        except BaseException:
            slot.__exit__(None, None, None)
            if token is not None:
                self.store.fail_inspection(order_id, token, "검사 작업 시작 실패 / 核验任务启动失败")
            raise
        return {"job": job, "replayed": False}

    def _done(self, task, job, token, slot):
        self.tasks.discard(task)
        if not task.cancelled():
            task.exception()
        if job["status"] == "running":
            # Cancellation before the coroutine's first step must also release
            # an unused reservation and persist an interrupted record.
            slot.__exit__(None, None, None)
            self.store.fail_inspection(job["order_id"], token, "서비스 종료 / 服务停止")
            job.update(status="interrupted", finished_at=now(),
                       error={"status_code": 503, "message": "서비스 종료로 검사 미완료 / 服务停止，核验未完成"})
            self._save(job)

    async def _run(self, job, body, token, snapshot, slot):
        try:
            with slot:
                result = await self.runner(job["order_id"], body, token, snapshot, slot)
            job.update(status="succeeded", check_id=result["check"]["id"])
        except asyncio.CancelledError:
            self.store.fail_inspection(job["order_id"], token, "서비스 종료 / 服务停止")
            job.update(status="interrupted", error={"status_code": 503, "message": "서비스 종료로 검사 미완료 / 服务停止，核验未完成"})
        except (HTTPException, StateError) as exc:
            # The runner normally clears the token itself; retain the same
            # invariant if an alternate runner raises before doing that.
            self.store.fail_inspection(job["order_id"], token, "검사 작업 미완료 / 核验任务未完成")
            job.update(status="failed", error={"status_code": getattr(exc, "status_code", getattr(exc, "code", 503)),
                                               "message": str(getattr(exc, "detail", exc))})
        except Exception:
            log.exception("Inspection job failed")
            self.store.fail_inspection(job["order_id"], token, "검사 작업 실패 / 核验任务失败")
            job.update(status="failed", error={"status_code": 503, "message": "검사 작업 실패 / 核验任务失败"})
        finally:
            job["finished_at"] = now()
            self._save(job)


def create_inspection_jobs_router(jobs):
    router = APIRouter()

    @router.post("/api/orders/{order_id}/inspection-jobs", status_code=202)
    async def start(order_id: str, body: JobRequest):
        return jobs.start(order_id, body)

    @router.get("/api/orders/{order_id}/inspection-jobs")
    async def recent(order_id: str):
        return {"jobs": jobs.list(order_id)}

    @router.get("/api/inspection-jobs/{job_id}")
    async def get(job_id: str):
        job = jobs.get(job_id)
        return {"job": job, "order": jobs.store.get(job["order_id"])}

    return router
