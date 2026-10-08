"""SQLite transactions preserve the relationship between evidence and order revisions."""

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path


def now():
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def uid(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


class StateError(Exception):
    def __init__(self, message, code=409):
        super().__init__(message)
        self.code = code


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def event(order, kind, message, payload=None):
    order["events"].append(
        {"id": uid("evt"), "kind": kind, "message": message, "created_at": now(), "payload": payload or {}}
    )
    order["updated_at"] = now()


def invalidate(order):
    order["evidence_epoch"] += 1
    order["status"] = "pending"
    if order.get("latest_check"):
        order["latest_check"]["valid"] = False
    for check in order["checks"]:
        check["valid"] = False


def expect_revision(order, revision):
    if order["revision"] != revision:
        raise StateError("주문 버전이 변경되었습니다. 새로 확인하세요 / 订单已改版，请按当前版本重新核验")


class Store:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "kitguard.sqlite3"
        self.photos_dir = self.directory / "photos"
        self.photos_dir.mkdir(exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS orders (id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS photos (id TEXT PRIMARY KEY, path TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS completions (
                    key TEXT PRIMARY KEY, order_id TEXT NOT NULL, digest TEXT NOT NULL, body TEXT NOT NULL
                );
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15, factory=ClosingConnection)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=15000")
        return db

    @staticmethod
    def _get(db, order_id):
        row = db.execute("SELECT body FROM orders WHERE id=?", (order_id,)).fetchone()
        if row is None:
            raise StateError("주문을 찾을 수 없습니다 / 找不到订单", 404)
        return json.loads(row["body"])

    @staticmethod
    def _put(db, order):
        db.execute(
            "INSERT OR REPLACE INTO orders VALUES (?,?)", (order["id"], json.dumps(order, ensure_ascii=False))
        )

    @contextmanager
    def transaction(self, order_id):
        db = self.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            order = self._get(db, order_id)
            yield db, order
            self._put(db, order)
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def get(self, order_id):
        with self.connect() as db:
            return self._get(db, order_id)

    def list(self):
        with self.connect() as db:
            rows = db.execute("SELECT body FROM orders").fetchall()
        orders = [json.loads(r["body"]) for r in rows]
        return sorted(orders, key=lambda x: x["updated_at"], reverse=True)

    def create(self, title, requirements):
        stamp = now()
        order = {
            "id": uid("ord"),
            "title": title,
            "requirements": requirements,
            "revision": 1,
            "status": "pending",
            "created_at": stamp,
            "updated_at": stamp,
            "latest_check": None,
            "checks": [],
            "photos": [],
            "references": {},
            "reference_history": [],
            "events": [],
            "completions": [],
            "evidence_epoch": 0,
            "active_inspection": None,
            "revisions": [
                {
                    "revision": 1,
                    "requirements": requirements,
                    "instruction": "최초 주문 / 初始订单",
                    "created_at": stamp,
                }
            ],
        }
        event(order, "order_created", "주문 생성 / 已创建订单")
        with self.connect() as db:
            self._put(db, order)
        return order

    def revise(self, order_id, requirements, instruction, expected):
        with self.transaction(order_id) as (_, order):
            expect_revision(order, expected)
            if requirements == order["requirements"]:
                raise StateError("변경된 수량이 없습니다 / 数量未改变", 422)
            order["revision"] += 1
            order["requirements"] = requirements
            invalidate(order)
            order["revisions"].append(
                {
                    "revision": order["revision"],
                    "requirements": requirements,
                    "instruction": instruction,
                    "created_at": now(),
                }
            )
            event(
                order,
                "revision_approved",
                "주문 변경 승인 · 이전 검증 무효 / 已确认改版，旧核验失效",
                {"revision": order["revision"], "requirements": requirements, "instruction": instruction},
            )
        return self.get(order_id)

    def add_photo(self, order_id, photo, path, expected=None, part=None):
        with self.transaction(order_id) as (db, order):
            if expected is not None:
                expect_revision(order, expected)
            if len(order["photos"]) + len(order["reference_history"]) >= 300:
                raise StateError("주문당 사진 한도(300)에 도달했습니다 / 此订单照片已达300张上限", 422)
            photo["revision"] = order["revision"]
            db.execute("INSERT INTO photos VALUES (?,?)", (photo["id"], Path(path).name))
            if part:
                order["references"][part] = photo
                order["reference_history"].append({"part": part, "photo": photo})
                kind, msg = "reference_updated", "기준 사진 변경 · 재검증 필요 / 参考图更新，需重新核验"
            else:
                order["photos"].append(photo)
                kind, msg = "photo_uploaded", "새 실물 사진 등록 / 已上传实物照片"
            invalidate(order)
            event(order, kind, msg, {"photo_id": photo["id"], "part": part})
        return self.get(order_id)

    def photo_path(self, photo_id):
        with self.connect() as db:
            row = db.execute("SELECT path FROM photos WHERE id=?", (photo_id,)).fetchone()
        if row is None:
            raise StateError("사진을 찾을 수 없습니다 / 找不到照片", 404)
        path = Path(row["path"])
        if not path.is_absolute():
            path = self.photos_dir / path
        if not path.is_file() or not path.resolve().is_relative_to(self.photos_dir.resolve()):
            raise StateError("사진 파일을 찾을 수 없습니다 / 照片文件缺失", 404)
        return path

    def begin_inspection(self, order_id, photo_id, revision):
        with self.transaction(order_id) as (_, order):
            expect_revision(order, revision)
            if order.get("active_inspection"):
                raise StateError("이미 검증 중입니다 / 该订单正在核验")
            if not order["photos"] or order["photos"][-1]["id"] != photo_id:
                raise StateError("최신 사진으로 검증하세요 / 请使用最新照片核验")
            if order["photos"][-1]["revision"] != revision:
                raise StateError("변경된 주문의 실물을 다시 촬영하세요 / 请为当前订单版本重新拍摄")
            token = uid("run")
            order["active_inspection"] = token
            order["status"] = "pending"
            if order.get("latest_check"):
                order["latest_check"]["valid"] = False
            for check in order["checks"]:
                check["valid"] = False
            event(order, "inspection_started", "실물 관찰 시작 / 开始观察实物", {"photo_id": photo_id})
            snapshot = json.loads(json.dumps(order))
        return token, snapshot

    def fail_inspection(self, order_id, token, reason, diagnostics=None):
        with self.transaction(order_id) as (_, order):
            if order.get("active_inspection") == token:
                order["active_inspection"] = None
                if order["status"] != "completed":
                    order["status"] = "needs_action"
                payload = {"reason": reason[:800]}
                if isinstance(diagnostics, dict):
                    payload["observation_diagnostics"] = diagnostics
                event(order, "inspection_failed", "검증 미완료 / 核验未完成", payload)

    def finish_inspection(self, order_id, token, snapshot, check):
        with self.transaction(order_id) as (_, order):
            expect_revision(order, snapshot["revision"])
            if (
                order["evidence_epoch"] != snapshot["evidence_epoch"]
                or order.get("active_inspection") != token
                or order["photos"][-1]["id"] != check["photo_id"]
            ):
                raise StateError(
                    "검증 중 사진·기준이 변경되었습니다. 재검증하세요 / 核验期间证据已变化，请重试"
                )
            order["active_inspection"] = None
            check["evidence_epoch"] = order["evidence_epoch"]
            check["valid"] = True
            check.setdefault("tool_trace", []).append(
                {
                    "step": "commit_current_evidence",
                    "status": "completed",
                    "revision": order["revision"],
                    "evidence_epoch": order["evidence_epoch"],
                }
            )
            order["checks"].append(check)
            order["latest_check"] = check
            order["status"] = "ready" if check["decision"] == "ready" else "needs_action"
            event(
                order,
                "inspection_completed",
                check["action"]["message"],
                {"check_id": check["id"], "decision": check["decision"], "revision": check["revision"]},
            )
        return self.get(order_id)

    def complete(self, order_id, request):
        canonical = json.dumps({"order_id": order_id, **request}, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        key = request["idempotency_key"]
        with self.transaction(order_id) as (db, order):
            previous = db.execute("SELECT * FROM completions WHERE key=?", (key,)).fetchone()
            if previous:
                if previous["order_id"] != order_id or previous["digest"] != digest:
                    raise StateError("중복 요청 키가 다른 작업에 사용되었습니다 / 幂等键已被其他请求使用")
                receipt = json.loads(previous["body"])
                replayed = True
            else:
                expect_revision(order, request["expected_revision"])
                check = order.get("latest_check")
                if (
                    not request["confirmed"]
                    or order["status"] != "ready"
                    or not check
                    or check["id"] != request["check_id"]
                    or not check["valid"]
                    or check["decision"] != "ready"
                    or check["revision"] != order["revision"]
                    or check["evidence_epoch"] != order["evidence_epoch"]
                    or check["photo_id"] != order["photos"][-1]["id"]
                    or order.get("active_inspection")
                ):
                    raise StateError(
                        "현재 버전의 유효한 검증과 작업자 확인이 필요합니다 / 需要当前版本的有效核验及操作者确认"
                    )
                receipt = {
                    "id": uid("done"),
                    "order_id": order_id,
                    "revision": order["revision"],
                    "check_id": check["id"],
                    "photo_id": check["photo_id"],
                    "created_at": now(),
                }
                db.execute(
                    "INSERT INTO completions VALUES (?,?,?,?)", (key, order_id, digest, json.dumps(receipt))
                )
                order["completions"].append(receipt)
                order["status"] = "completed"
                event(order, "order_completed", "작업자 확인 후 완료 저장 / 操作者确认后已记录完成", receipt)
                replayed = False
        # A separate read verifies the committed state; replay never overwrites a newer revision.
        return {"order": self.get(order_id), "completion": {**receipt, "replayed": replayed}}

    def recover_interrupted(self):
        for saved in self.list():
            if saved.get("active_inspection"):
                self.fail_inspection(
                    saved["id"], saved["active_inspection"], "애플리케이션 재시작 / 应用重启"
                )
