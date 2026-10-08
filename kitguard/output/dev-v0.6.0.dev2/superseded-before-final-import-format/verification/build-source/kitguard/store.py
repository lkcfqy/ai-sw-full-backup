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


TERMINAL_STATUSES = {"completed", "manual_reviewed"}


def require_open_order(order):
    if order["status"] in TERMINAL_STATUSES:
        raise StateError("종료된 주문입니다. 먼저 재처리하거나 주문을 개정하세요 / 已结束订单须先明确重开或改版")


def reject_active_study(db, order):
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='field_studies'").fetchone():
        for row in db.execute("SELECT body FROM field_studies"):
            study = json.loads(row["body"])
            if study["status"] != "closed" and any(c["order_id"] == order["id"] for c in study["cases"]):
                raise StateError("등록된 검증 사례입니다. 배치를 먼저 종료하세요 / 此订单已登记验证案例，请先关闭验证批次")


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
                CREATE TABLE IF NOT EXISTS human_operations (
                    key TEXT PRIMARY KEY, order_id TEXT NOT NULL, kind TEXT NOT NULL,
                    digest TEXT NOT NULL, body TEXT NOT NULL
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

    def create(self, title, requirements, *, demo_source=None):
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
            "manual_reviews": [],
            "reopenings": [],
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
        if demo_source is not None:
            order["demo_source"] = json.loads(json.dumps(demo_source))
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
            require_open_order(order)
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

    def select_region(self, order_id, body):
        from .regions import (
            InspectionRegion,
            check_region_change,
            derive_photo,
            stored_bytes,
            validate_rectangle,
            verify_photo_lineage,
        )

        body = InspectionRegion.model_validate(body).model_dump()
        path, committed = None, False
        try:
            with self.transaction(order_id) as (db, order):
                require_open_order(order)
                current, root = check_region_change(db, order, body)
                _, raw = verify_photo_lineage(self, order, current, db)
                validate_rectangle(body["mode"], body["region_xyxy"], root["width"], root["height"])
                if current.get("scope_mode", "whole_image") == body["mode"] and current.get("region_xyxy") == body["region_xyxy"]:
                    return {"order": order, "photo": current, "changed": False}
                if len(order["photos"]) + len(order["reference_history"]) >= 300:
                    raise StateError("주문당 사진 한도(300)에 도달했습니다 / 此订单照片已达300张上限", 422)
                photo, content = derive_photo(order, root, raw, body)
                path = self.photos_dir / (photo["id"] + ".jpg")
                with path.open("xb") as stream:
                    stream.write(content)
                # File mutation outside SQLite cannot substitute the root during derivation.
                stored_bytes(self, root, db)
                check_region_change(db, order, body)
                db.execute("INSERT INTO photos VALUES (?,?)", (photo["id"], path.name))
                order["photos"].append(photo)
                invalidate(order)
                event(order, "inspection_region_selected", "검사 범위 변경 · 재검증 필요 / 检查范围已改变，需重新核验", {
                    "previous_photo_id": current["id"], "photo_id": photo["id"], "root_photo_id": root["id"],
                    "root_photo_sha256": root["sha256"], "region_xyxy": photo["region_xyxy"],
                    "scope_mode": photo["scope_mode"], "scope_declaration": photo["scope_declaration"],
                    "scope_confirmed_at": photo["scope_confirmed_at"], "physical_capture": False,
                })
            committed = True
            return {"order": self.get(order_id), "photo": photo, "changed": True}
        finally:
            if path is not None and not committed:
                path.unlink(missing_ok=True)

    def begin_inspection(self, order_id, photo_id, revision):
        with self.transaction(order_id) as (_, order):
            require_open_order(order)
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
                if order["status"] not in TERMINAL_STATUSES:
                    order["status"] = "needs_action"
                payload = {"reason": reason[:800]}
                if isinstance(diagnostics, dict):
                    payload["observation_diagnostics"] = diagnostics
                event(order, "inspection_failed", "검증 미완료 / 核验未完成", payload)

    def finish_inspection(self, order_id, token, snapshot, check):
        with self.transaction(order_id) as (db, order):
            expect_revision(order, snapshot["revision"])
            if (
                order["evidence_epoch"] != snapshot["evidence_epoch"]
                or order.get("active_inspection") != token
                or order["photos"][-1]["id"] != check["photo_id"]
            ):
                raise StateError(
                    "검증 중 사진·기준이 변경되었습니다. 재검증하세요 / 核验期间证据已变化，请重试"
                )
            from .regions import inspection_scope, verify_photo_lineage

            verify_photo_lineage(self, order, order["photos"][-1], db)
            if inspection_scope(order, order["photos"][-1]) != inspection_scope(snapshot, snapshot["photos"][-1]):
                raise StateError("검증 중 검사 범위가 바뀌었습니다 / 核验期间检查范围已改变")
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
            if order.get("demo_source"):
                raise StateError("공개 사진 데모는 실물 완료를 기록할 수 없습니다 / 公开照片演示不能记录实物完工")
            if order["photos"]:
                from .regions import verify_photo_lineage

                verify_photo_lineage(self, order, order["photos"][-1], db)
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
                from .regions import inspection_scope

                if (check.get("photo_sha256", order["photos"][-1]["sha256"]) != order["photos"][-1]["sha256"]
                        or (check.get("inspection_scope") is not None
                            and check["inspection_scope"] != inspection_scope(order, order["photos"][-1]))):
                    raise StateError("검사 범위 바인딩이 바뀌었습니다 / 核验范围绑定已改变")
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

    @staticmethod
    def _human_replay(db, order_id, kind, request):
        canonical = json.dumps({"order_id": order_id, "kind": kind, **request},
                               sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        previous = db.execute("SELECT * FROM human_operations WHERE key=?", (request["idempotency_key"],)).fetchone()
        if previous:
            if previous["order_id"] != order_id or previous["kind"] != kind or previous["digest"] != digest:
                raise StateError("요청 키가 다른 작업에 사용되었습니다 / 幂等键已用于不同请求")
            return json.loads(previous["body"]), digest
        return None, digest

    @staticmethod
    def _save_human_operation(db, order_id, kind, request, digest, receipt):
        db.execute("INSERT INTO human_operations VALUES (?,?,?,?,?)", (
            request["idempotency_key"], order_id, kind, digest, json.dumps(receipt, ensure_ascii=False)))

    @staticmethod
    def _manual_source(db, order, photo):
        from .public_demo_catalog import CATALOG
        from .regions import family_tokens, known_family_hashes

        if order.get("demo_source") or photo.get("demo_source"):
            raise StateError("공개 사진은 실물 수동 확인으로 기록할 수 없습니다 / 公开照片不能记录为实物人工复核")
        family = known_family_hashes(db, photo)
        if family & {entry["source_sha256"] for entry in CATALOG}:
            raise StateError("알려진 공개 사진입니다 / 此照片已知来自公开图库")
        for row in db.execute("SELECT body FROM orders"):
            saved = json.loads(row["body"])
            related_photos = {p["id"] for p in saved.get("photos", []) if family_tokens(p) & family}
            if not related_photos:
                continue
            if saved.get("demo_source"):
                raise StateError("공개 사진의 동일 출처입니다 / 相同照片来源已标记为公开演示")
            if any(c.get("backend") == "test" and c.get("photo_id") in related_photos for c in saved.get("checks", [])):
                raise StateError("테스트 관찰 사진은 실물 확인이 아닙니다 / 工程替身观察不能升级为实物人工复核")

    def manual_review(self, order_id, request, verify_evidence_files=None):
        from .regions import inspection_scope, stored_bytes, verify_photo_lineage
        from .schemas import ManualReviewRequest

        request = ManualReviewRequest.model_validate(request).model_dump()
        with self.transaction(order_id) as (db, order):
            receipt, digest = self._human_replay(db, order_id, "manual_review", request)
            replayed = receipt is not None
            if receipt is None:
                require_open_order(order)
                expect_revision(order, request["expected_revision"])
                reject_active_study(db, order)
                if order.get("active_inspection"):
                    raise StateError("검증이 끝난 뒤 확인하세요 / 请等待核验结束后再人工复核")
                photos = order.get("photos", [])
                if (order["evidence_epoch"] != request["expected_evidence_epoch"] or not photos
                        or photos[-1]["id"] != request["photo_id"] or photos[-1]["revision"] != order["revision"]):
                    raise StateError("현재 사진과 증거 버전을 확인하세요 / 照片或证据版本已变化，请刷新后重新核对")
                photo = photos[-1]
                check = order.get("latest_check")
                current_check = check if (check and check.get("valid") and check["revision"] == order["revision"]
                                           and check["photo_id"] == photo["id"]
                                           and check.get("evidence_epoch") == order["evidence_epoch"]) else None
                if request["check_id"] != (current_check["id"] if current_check else None):
                    raise StateError("AI 검증 결과가 바뀌었습니다 / AI核验记录已变化，请重新核对")
                self._manual_source(db, order, photo)
                verify_photo_lineage(self, order, photo, db)
                for reference in order["references"].values():
                    stored_bytes(self, reference, db)
                if verify_evidence_files is not None:
                    verify_evidence_files(order)
                matches = request["actual_counts"] == order["requirements"]
                receipt = {
                    "id": uid("manual"), "order_id": order_id, "revision": order["revision"],
                    "photo_id": photo["id"], "photo_sha256": photo["sha256"],
                    "evidence_epoch": order["evidence_epoch"], "inspection_scope": inspection_scope(order, photo),
                    "check_id": current_check["id"] if current_check else None,
                    "check_decision": current_check["decision"] if current_check else None,
                    "check_backend": current_check.get("backend") if current_check else None,
                    "previous_check_id": check["id"] if check else None,
                    "reference_ids": {part: ref["id"] for part, ref in order["references"].items()},
                    "reference_sha256": {part: ref["sha256"] for part, ref in order["references"].items()},
                    "requirements_snapshot": order["requirements"].copy(), "actual_counts": request["actual_counts"],
                    "operator_code": request["operator_code"], "reason": request["reason"],
                    "confirmed_physical": True, "confirmed_current_bom": True,
                    "matches_requirements": matches, "outcome": "matched" if matches else "unresolved",
                    "source_kind": "operator_declared_physical", "ai_completion": False,
                    "industrial_release": False, "created_at": now(),
                    "limitation": "人工声明与计数，不证明实物真实性或工业放行；不是AI核验成功。",
                }
                self._save_human_operation(db, order_id, "manual_review", request, digest, receipt)
                order.setdefault("manual_reviews", []).append(receipt)
                order["status"] = "manual_reviewed"
                event(order, "manual_review_recorded", "수동 확인 기록 / 已记录人工复核（非AI完成）", receipt)
        return {"order": self.get(order_id), "manual_review": {**receipt, "replayed": replayed}}

    def reopen(self, order_id, request):
        from .schemas import ReopenRequest

        request = ReopenRequest.model_validate(request).model_dump()
        with self.transaction(order_id) as (db, order):
            receipt, digest = self._human_replay(db, order_id, "reopen", request)
            replayed = receipt is not None
            if receipt is None:
                expect_revision(order, request["expected_revision"])
                reject_active_study(db, order)
                if order["status"] not in TERMINAL_STATUSES or order.get("active_inspection"):
                    raise StateError("종료된 주문만 명시적으로 재처리할 수 있습니다 / 仅已结束且无运行中核验的订单可重开")
                old_status, old_revision = order["status"], order["revision"]
                order["revision"] += 1
                invalidate(order)
                receipt = {"id": uid("reopen"), "order_id": order_id, "from_revision": old_revision,
                           "to_revision": order["revision"], "previous_status": old_status,
                           "reason": request["reason"], "confirmed": True, "created_at": now(),
                           "requirements_snapshot": order["requirements"].copy()}
                self._save_human_operation(db, order_id, "reopen", request, digest, receipt)
                order.setdefault("reopenings", []).append(receipt)
                order["revisions"].append({"revision": order["revision"],
                                           "requirements": order["requirements"].copy(),
                                           "instruction": request["reason"], "created_at": receipt["created_at"],
                                           "kind": "reopen", "reopening_id": receipt["id"]})
                event(order, "order_reopened", "재처리 시작 · 새 사진 필요 / 已重开，须为新版本重新拍照", receipt)
        return {"order": self.get(order_id), "reopening": {**receipt, "replayed": replayed}}
