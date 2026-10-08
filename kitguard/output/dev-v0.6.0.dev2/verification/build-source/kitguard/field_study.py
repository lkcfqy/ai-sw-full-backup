"""Prospective, locally recorded comparison trials; no inference or invented field results."""

from __future__ import annotations

import copy
import hashlib
import html
import json
import secrets
import statistics
import time
from contextlib import contextmanager
from pathlib import Path

from . import __version__
from .feedback import reference_ids
from .regions import family_tokens, inspection_scope, known_family_hashes, verify_photo_lineage
from .store import StateError, now, uid

METHODS = ("manual", "kitguard")
IDENTITY_KEYS = ("repo_id", "revision", "observer_protocol_sha256", "observation_mode", "image_max_side")
PROTOCOL = {
    "name": "fixed_state_manual_then_kitguard_v1",
    "max_cases": 48,
    "methods": METHODS,
    "truth_policy": "Two matching entries and an operator declaration, sealed before either method starts",
    "timing": "Server monotonic start-to-terminal after photo/setup; not full physical work time",
    "missing": "Every planned slot remains in each method denominator",
    "repeat": "One start per method; all inspection attempts and returned checks retained",
    "inspection_scope_policy": "operator_region_v1",
}
LIMITATIONS = [
    "출처·독립 계수는 작업자의 선언입니다 / 来源与独立计数是操作者声明，软件不能证明现场真实性。",
    "정답 잠금은 블라인드 실험이 아닙니다 / 真值先锁定不等于盲测；同一浏览器没有人员隔离。",
    "수동 후 AI 순서에는 학습 효과가 있습니다 / 固定先人工后AI可能产生学习效应，不能据此宣称因果效率提升。",
    "준비·촬영 이후의 시간입니다 / 计时从准备和拍照之后开始，包含等待与操作，不是完整实物作业时间。",
    "한 사례는 고정된 물체 상태입니다 / 每个案例只对应一个固定实物状态；补件后须新登记真值，不计连续补件成功率。",
    "공개 사진·공학 테스트는 현장 결과가 아닙니다 / 公开回放和工程替身不是现场效果；三种来源分别记录。",
    "중단·미실행도 분모에 포함합니다 / 失败、放弃、中断及未开始都保留；已返回的错误不会被放弃状态隐藏。",
    "해시는 서명이 아닙니다 / 散列用于核对内容，不是签名、人员身份或实物真实性证明。",
]


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha(value):
    return hashlib.sha256(value).hexdigest()


def commitment(truth, nonce):
    return sha(canonical({"truth": truth, "nonce": nonce}).encode())


def durations(values):
    values = [v for v in values if isinstance(v, int) and v >= 0]
    return {"n": len(values), "median": statistics.median(values) if values else None,
            "max": max(values) if values else None}


def classify(check, truth):
    observed = check.get("observed", {})
    if check.get("decision") not in {"ready", "correct"} or any(v is None for v in observed.values()):
        return "uncertain"
    return "correct" if observed == truth else "wrong"


def compute_report(study):
    """Always use planned denominators, including unregistered slots."""
    result = {"scope": PROTOCOL["name"], "source_kind": study["source_kind"],
              "planned_cases": study["planned_cases"], "registered_cases": len(study["cases"]),
              "methods": {}, "paired_completed_cases": 0, "limitations": LIMITATIONS}
    for method in METHODS:
        metrics = {k: 0 for k in ("started", "completed", "correct", "wrong", "uncertain",
                                 "failed", "abandoned", "interrupted", "not_started")}
        metrics["planned"] = study["planned_cases"]
        metrics["not_started"] = study["planned_cases"] - len(study["cases"])
        terminal, completed = [], []
        false_ready = 0
        mismatch_n = sum(c["truth"] != c["requirements"] for c in study["cases"])
        returned = {"total": 0, "scorable": 0, "wrong_clear": 0, "false_ready": 0,
                    "uncertain": 0, "multiple_attempt_trials": 0, "ineligible_backend_or_identity": 0}
        for case in study["cases"]:
            trial = case["trials"][method]
            if not trial:
                metrics["not_started"] += 1
                continue
            metrics["started"] += 1
            terminal.append(trial.get("elapsed_ms"))
            if trial["status"] == "completed":
                metrics["completed"] += 1
                completed.append(trial.get("elapsed_ms"))
                if method == "manual":
                    category = "correct" if trial["manual_counts"] == case["truth"] else "wrong"
                else:
                    category = classify(trial["check"], case["truth"])
                    false_ready += trial["check"]["decision"] == "ready" and case["truth"] != case["requirements"]
                metrics[category] += 1
            else:
                metrics[trial["status"]] += 1
            evidence = trial.get("evidence", {})
            returned["multiple_attempt_trials"] += sum(
                e["kind"] == "inspection_started" for e in evidence.get("events", [])
            ) > 1
            for check in evidence.get("checks", []):
                returned["total"] += 1
                if study["source_kind"] != "engineering_fixture" and (
                    check.get("backend") != "mlx" or any(
                        check.get("runtime_identity", {}).get(k) != study["runtime_identity"].get(k)
                        for k in IDENTITY_KEYS
                    )
                ):
                    returned["ineligible_backend_or_identity"] += 1
                    continue
                if not (
                    check.get("photo_sha256") == case["photo_sha256"]
                    and check.get("revision") == case["revision"]
                    and check.get("requirements_snapshot") == case["requirements"]
                ):
                    continue
                returned["scorable"] += 1
                category = classify(check, case["truth"])
                returned["wrong_clear"] += category == "wrong"
                returned["uncertain"] += category == "uncertain"
                returned["false_ready"] += check["decision"] == "ready" and case["truth"] != case["requirements"]
        metrics.update({
            "correct_fraction": metrics["correct"] / metrics["planned"] if metrics["started"] else None,
            "terminal_elapsed_ms": durations(terminal), "completed_elapsed_ms": durations(completed),
            "false_ready": {"numerator": false_ready, "denominator": mismatch_n} if method == "kitguard" else None,
            "returned_checks": returned,
        })
        assert sum(metrics[k] for k in ("correct", "wrong", "uncertain", "failed", "abandoned",
                                       "interrupted", "not_started")) == metrics["planned"]
        result["methods"][method] = metrics
    result["paired_completed_cases"] = sum(
        all(c["trials"][m] and c["trials"][m]["status"] == "completed" for m in METHODS)
        for c in study["cases"]
    )
    return result


class FieldStudies:
    def __init__(self, store, runtime_provider):
        self.store = store
        self.runtime_provider = runtime_provider
        self.process_nonce = secrets.token_hex(16)
        with store.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS field_studies (id TEXT PRIMARY KEY, body TEXT NOT NULL)")

    def runtime(self):
        status = self.runtime_provider()
        return {"app_version": __version__, **{k: status.get(k) for k in IDENTITY_KEYS}}

    @staticmethod
    def _put(db, study):
        db.execute("INSERT OR REPLACE INTO field_studies VALUES (?,?)", (study["id"], canonical(study)))

    @staticmethod
    def _get(db, study_id):
        row = db.execute("SELECT body FROM field_studies WHERE id=?", (study_id,)).fetchone()
        if row is None:
            raise StateError("검증 배치를 찾을 수 없습니다 / 找不到验证批次", 404)
        return json.loads(row["body"])

    @contextmanager
    def transaction(self, study_id):
        db = self.store.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            study = self._get(db, study_id)
            yield db, study
            self._put(db, study)
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def event(study, kind, payload=None):
        study["events"].append({"kind": kind, "created_at": now(), "payload": payload or {}})

    @staticmethod
    def view(study):
        value = copy.deepcopy(study)
        reveal = value["status"] == "closed"
        for case in value["cases"]:
            if not reveal:
                case.pop("truth")
                case.pop("truth_nonce")
            for trial in case["trials"].values():
                if trial:
                    trial.pop("_monotonic_started", None)
                    trial.pop("_process_nonce", None)
        value["report"] = compute_report(study) if reveal else None
        return value

    def get(self, study_id):
        with self.store.connect() as db:
            return self.view(self._get(db, study_id))

    def list(self):
        with self.store.connect() as db:
            studies = [json.loads(r["body"]) for r in db.execute("SELECT body FROM field_studies")]
        return [self.view(s) for s in sorted(studies, key=lambda x: x["created_at"], reverse=True)]

    def create(self, body):
        study = {**body, "id": uid("study"), "created_at": now(), "status": "draft", "cases": [],
                 "frozen_at": None, "closed_at": None, "protocol_sha256": None, "runtime_identity": None,
                 "events": [], "protocol": PROTOCOL, "limitations": LIMITATIONS}
        self.event(study, "created")
        with self.store.connect() as db:
            self._put(db, study)
        return self.view(study)

    def verify_photo(self, db, photo):
        row = db.execute("SELECT path FROM photos WHERE id=?", (photo["id"],)).fetchone()
        if row is None:
            raise StateError("사진 기록이 없습니다 / 照片记录缺失")
        path = Path(row["path"])
        if not path.is_absolute():
            path = self.store.photos_dir / path
        if not path.resolve().is_relative_to(self.store.photos_dir.resolve()) or not path.is_file():
            raise StateError("사진 파일이 없습니다 / 照片文件缺失")
        if sha(path.read_bytes()) != photo["sha256"]:
            raise StateError("사진 바이트가 바뀌었습니다 / 照片文件内容已改变")

    def binding(self, db, order):
        if not order["photos"] or order["photos"][-1]["revision"] != order["revision"]:
            raise StateError("현재 버전의 사진이 필요합니다 / 需要当前版本的照片")
        photo = order["photos"][-1]
        self.verify_photo(db, photo)
        verify_photo_lineage(self.store, order, photo, db)
        for pic in order["references"].values():
            self.verify_photo(db, pic)
        scope = inspection_scope(order, photo)
        return {"order_id": order["id"], "revision": order["revision"], "photo_id": photo["id"],
                "photo_sha256": photo["sha256"], "requirements": copy.deepcopy(order["requirements"]),
                "evidence_epoch": order["evidence_epoch"], "reference_ids": reference_ids(order),
                "reference_sha256": {p: v["sha256"] for p, v in order["references"].items()},
                "inspection_scope": scope, "source_family_sha256": scope["source_family_sha256"]}

    def verify_binding(self, db, case, *, scope_required=False):
        order = self.store._get(db, case["order_id"])
        binding = self.binding(db, order)
        if scope_required and "inspection_scope" not in case:
            raise StateError("등록 검사 범위 기록이 없습니다 / 缺少登记检查范围记录")
        legacy = "inspection_scope" not in case and order["photos"][-1].get("kind", "root_photo") == "root_photo"
        if any(case.get(k) != v for k, v in binding.items()
               if not (legacy and k in {"inspection_scope", "source_family_sha256"})):
            raise StateError("등록 후 주문·사진·기준이 바뀌었습니다 / 登记后订单、照片或参考已改变")
        return order

    @staticmethod
    def untouched(order):
        if order.get("active_inspection") or order["checks"] or any(
            e["kind"] == "inspection_started" for e in order["events"]
        ):
            raise StateError("이미 AI 검증을 시도한 주문입니다 / 此订单已经尝试过AI核验，请使用新工单和未核验照片")

    @staticmethod
    def external_exposures(db, case):
        exposed = []
        family = known_family_hashes(db, case)
        for row in db.execute("SELECT body FROM orders"):
            saved = json.loads(row["body"])
            if saved["id"] == case["order_id"]:
                continue
            if any(family_tokens(p) & family for p in saved["photos"]) and any(
                e["kind"] == "inspection_started" for e in saved["events"]
            ):
                exposed.append({"order_id": saved["id"], "events": saved["events"], "checks": saved["checks"]})
        return exposed

    def verify_no_external_exposure(self, db, study, case):
        if study["source_kind"] != "self_reported_physical":
            return
        family = known_family_hashes(db, case)
        for row in db.execute("SELECT body FROM orders"):
            saved = json.loads(row["body"])
            if saved.get("demo_source") and any(family_tokens(p) & family for p in saved["photos"]):
                raise StateError("이미 알려진 공개 사진입니다 / 此照片已知来自公开图库，换工单不能改为现场来源")
        if self.external_exposures(db, case):
            raise StateError("다른 주문에서 동일 사진이 AI에 노출되었습니다 / 同一照片已在另一工单尝试AI核验，不能作前瞻性现场对照")

    def add_case(self, study_id, body):
        with self.transaction(study_id) as (db, study):
            if study["status"] != "draft" or len(study["cases"]) >= study["planned_cases"]:
                raise StateError("등록이 잠겼거나 예정 사례 수에 도달했습니다 / 登记已锁定或已达预定数量")
            order = self.store._get(db, body["order_id"])
            self.untouched(order)
            bound = self.binding(db, order)
            self.verify_no_external_exposure(db, study, bound)
            if bound["revision"] != body["expected_revision"] or bound["photo_id"] != body["photo_id"]:
                raise StateError("최신 주문·사진으로 등록하세요 / 请按最新订单和照片登记")
            if order.get("demo_source") and study["source_kind"] != "public_replay":
                raise StateError("공개 데모는 공개 재생으로만 등록할 수 있습니다 / 公开图库工单只能登记为公开回放")
            family = known_family_hashes(db, bound)
            if any(c["order_id"] == order["id"] or bool(family_tokens(c) & family)
                   for c in study["cases"]):
                raise StateError("중복 주문·사진은 새 사례가 아닙니다 / 重复订单或照片不能算新案例")
            if study["source_kind"] == "self_reported_physical":
                for row in db.execute("SELECT body FROM orders"):
                    saved = json.loads(row["body"])
                    if any(family_tokens(p) & family for p in saved["photos"]) and any(
                        e["kind"] == "inspection_started" for e in saved["events"]
                    ):
                        raise StateError("동일 사진의 이전 AI 노출이 있습니다 / 这张照片已有AI观察记录，不能作为新现场验证")
                for row in db.execute("SELECT body FROM field_studies"):
                    if any(family_tokens(c) & family for c in json.loads(row["body"])["cases"]):
                        raise StateError("이미 등록된 사진입니다 / 该照片已有验证登记，不能作为新案例")
            nonce = secrets.token_hex(32)
            case = {"id": uid("case"), "label": body["label"], "source_note": body["source_note"],
                    "registered_at": now(), **bound, "truth": body["truth"], "truth_nonce": nonce,
                    "truth_commitment": commitment(body["truth"], nonce), "confirmed_independent": True,
                    "demo_source": copy.deepcopy(order.get("demo_source")),
                    "trials": {m: None for m in METHODS}}
            study["cases"].append(case)
            self.event(study, "case_registered", {"case_id": case["id"], "truth_commitment": case["truth_commitment"]})
        return self.get(study_id)

    def freeze(self, study_id):
        with self.transaction(study_id) as (db, study):
            if study["status"] != "draft" or len(study["cases"]) != study["planned_cases"]:
                raise StateError("예정된 모든 사례를 먼저 등록하세요 / 请先登记全部预定案例；已冻结批次不能重冻")
            for case in study["cases"]:
                self.untouched(self.verify_binding(db, case, scope_required=bool(study["protocol"].get("inspection_scope_policy"))))
                self.verify_no_external_exposure(db, study, case)
            study["status"], study["frozen_at"] = "frozen", now()
            study["runtime_identity"] = self.runtime()
            study["protocol_sha256"] = sha(canonical(PROTOCOL).encode())
            study["recorder_source_sha256"] = sha(Path(__file__).read_bytes())
            self.event(study, "frozen")
        return self.get(study_id)

    @staticmethod
    def case(study, case_id):
        for case in study["cases"]:
            if case["id"] == case_id:
                return case
        raise StateError("사례를 찾을 수 없습니다 / 找不到案例", 404)

    def start(self, study_id, case_id, method):
        with self.transaction(study_id) as (db, study):
            if study["status"] != "frozen":
                raise StateError("동결된 배치에서 시작하세요 / 请先冻结批次")
            if study["runtime_identity"] != self.runtime() or study["recorder_source_sha256"] != sha(Path(__file__).read_bytes()):
                raise StateError("동결 이후 실행 구성이 바뀌었습니다 / 冻结后运行配置或记录器已改变")
            case = self.case(study, case_id)
            if case["trials"][method] or any(
                t and t["status"] == "running" for c in study["cases"] for t in c["trials"].values()
            ):
                raise StateError("이미 시작했거나 다른 시행이 진행 중입니다 / 此方法已开始过，或另有进行中的试次")
            if method == "kitguard" and not case["trials"]["manual"]:
                raise StateError("수동 시행을 먼저 종료하세요 / 请先结束人工环节")
            order = self.verify_binding(db, case, scope_required=bool(study["protocol"].get("inspection_scope_policy")))
            self.untouched(order)
            self.verify_no_external_exposure(db, study, case)
            trial = {"id": uid("trial"), "method": method, "status": "running", "started_at": now(),
                     "finished_at": None, "elapsed_ms": None, "note": "", "manual_counts": None, "check": None,
                     "order_id": case["order_id"], "photo_id": case["photo_id"], "revision": case["revision"],
                     "_monotonic_started": time.monotonic(), "_process_nonce": self.process_nonce,
                     "event_index": len(order["events"]), "check_index": len(order["checks"]),
                     "evidence": {"events": [], "checks": []}}
            case["trials"][method] = trial
            self.event(study, "trial_started", {"case_id": case_id, "trial_id": trial["id"], "method": method})
        value = self.get(study_id)
        return {"study": value, "trial": self.case(value, case_id)["trials"][method]}

    def capture(self, db, case, trial):
        order = self.store._get(db, case["order_id"])
        return {"events": copy.deepcopy(order["events"][trial["event_index"]:]),
                "checks": copy.deepcopy(order["checks"][trial["check_index"]:]),
                "other_order_exposures": self.external_exposures(db, case),
                "order_revision_at_capture": order["revision"], "captured_at": now()}

    def terminate(self, db, case, trial, outcome, note):
        if self.store._get(db, case["order_id"]).get("active_inspection"):
            raise StateError("AI 요청이 아직 진행 중입니다. 응답 후 기록하세요 / AI请求仍在进行，请等待返回后记录，避免遗漏结果")
        trial["evidence"] = self.capture(db, case, trial)
        same_process = trial["_process_nonce"] == self.process_nonce
        trial["status"] = outcome if same_process else "interrupted"
        trial["elapsed_ms"] = max(0, round((time.monotonic() - trial["_monotonic_started"]) * 1000)) if same_process else None
        trial["finished_at"], trial["note"] = now(), note

    def finish(self, study_id, trial_id, body):
        with self.transaction(study_id) as (db, study):
            if study["status"] != "frozen":
                raise StateError("시행을 종료할 수 없는 배치입니다 / 此批次不能结束试次")
            pairs = [(c, t) for c in study["cases"] for t in c["trials"].values() if t and t["id"] == trial_id]
            if not pairs:
                raise StateError("시행을 찾을 수 없습니다 / 找不到试次", 404)
            case, trial = pairs[0]
            if trial["status"] != "running" or trial["_process_nonce"] != self.process_nonce:
                raise StateError("이미 종료되었거나 이전 프로세스의 시행입니다 / 已结束或属于此前进程的试次")
            if body["outcome"] == "completed":
                order = self.verify_binding(db, case, scope_required=bool(study["protocol"].get("inspection_scope_policy")))
                self.verify_no_external_exposure(db, study, case)
                if (study["runtime_identity"] != self.runtime()
                        or study["recorder_source_sha256"] != sha(Path(__file__).read_bytes())):
                    raise StateError("실행 구성·기록기가 바뀌었습니다 / 运行配置或记录器源码已改变")
                if trial["method"] == "manual":
                    self.untouched(order)
                    if body.get("manual_counts") is None or body.get("check_id") is not None:
                        raise StateError("수동 계수만 입력하세요 / 人工环节只能提交人工计数", 422)
                    trial["manual_counts"] = body["manual_counts"]
                else:
                    if body.get("manual_counts") is not None or not body.get("check_id"):
                        raise StateError("실제 검증 ID가 필요합니다 / AI环节需要实际核验ID，不能上传预测", 422)
                    check = order.get("latest_check")
                    evidence = self.capture(db, case, trial)
                    starts = [e for e in evidence["events"] if e["kind"] == "inspection_started"]
                    if not (check and check["id"] == body["check_id"] and check["valid"]
                            and not order["active_inspection"] and len(starts) == 1 and len(evidence["checks"]) == 1
                            and check["photo_sha256"] == case["photo_sha256"]
                            and check["photo_id"] == case["photo_id"] and check["revision"] == case["revision"]
                            and check["evidence_epoch"] == case["evidence_epoch"]
                            and check["reference_ids"] == case["reference_ids"]
                            and check.get("inspection_scope") == case.get("inspection_scope")
                            and check["requirements_snapshot"] == case["requirements"]):
                        raise StateError("시작 이후 한 번의 실제 검증만 연결하세요 / 只能关联开始后唯一一次、同版本同照片的有效核验")
                    if any(check.get("runtime_identity", {}).get(k) != study["runtime_identity"].get(k) for k in IDENTITY_KEYS):
                        raise StateError("검증 모델 구성이 일치하지 않습니다 / 核验模型配置不一致")
                    if study["source_kind"] != "engineering_fixture" and check.get("backend") != "mlx":
                        raise StateError("테스트 대역은 현장·공개 모델 결과가 아닙니다 / 工程替身不能冒充现场或公开图的模型结果")
                    trial["check"] = copy.deepcopy(check)
            elif body.get("manual_counts") is not None or body.get("check_id") is not None or not body.get("note", "").strip():
                raise StateError("실패·중단 사유만 기록하세요 / 失败或放弃请只填写原因，不提交替代结果", 422)
            self.terminate(db, case, trial, body["outcome"], body.get("note", ""))
            self.event(study, "trial_finished", {"trial_id": trial_id, "status": trial["status"]})
        return self.get(study_id)

    def close(self, study_id):
        with self.transaction(study_id) as (db, study):
            if study["status"] == "closed":
                raise StateError("이미 닫힌 배치입니다 / 此批次已经关闭")
            for case in study["cases"]:
                for trial in case["trials"].values():
                    if trial and trial["status"] == "running":
                        self.terminate(db, case, trial, "abandoned", "배치 종료 / 批次关闭，试次放弃")
            study["status"], study["closed_at"] = "closed", now()
            self.event(study, "closed")
        return self.get(study_id)

    def recover_interrupted(self):
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for row in db.execute("SELECT body FROM field_studies").fetchall():
                study = json.loads(row["body"])
                for case in study["cases"]:
                    for trial in case["trials"].values():
                        if trial and trial["status"] == "running":
                            trial["evidence"] = self.capture(db, case, trial)
                            trial.update({"status": "interrupted", "elapsed_ms": None, "finished_at": now(),
                                          "note": "서버 재시작; 경과 시간 미상 / 服务重启，耗时未知"})
                            self.event(study, "trial_interrupted", {"trial_id": trial["id"]})
                self._put(db, study)

    def export(self, study_id):
        result = self.get(study_id)
        if result["status"] != "closed":
            raise StateError("배치를 닫은 뒤 정답과 보고서를 내보내세요 / 关闭批次后才能导出真值与报告")
        with self.store.connect() as db:
            for case in result["cases"]:
                if result["protocol"].get("inspection_scope_policy") and "inspection_scope" not in case:
                    raise StateError("등록 검사 범위 기록이 없습니다 / 缺少登记检查范围记录")
                order = self.store._get(db, case["order_id"])
                photo = next((p for p in order["photos"] if p["id"] == case["photo_id"]), None)
                if photo is None or photo["sha256"] != case["photo_sha256"]:
                    raise StateError("등록 사진 연결이 바뀌었습니다 / 登记照片绑定已改变")
                verify_photo_lineage(self.store, order, photo, db)
                if case.get("inspection_scope") is not None and inspection_scope(order, photo) != case["inspection_scope"]:
                    raise StateError("등록 검사 범위가 바뀌었습니다 / 登记检查范围已改变")
        return {"schema_version": 1, "kind": "kitguard_fixed_state_study", "study": result}


def render_report(payload):
    study = payload["study"]
    escape = lambda value: html.escape(str(value))
    rows = []
    for method, m in study["report"]["methods"].items():
        rows.append("<tr>" + "".join(f"<td>{escape(v)}</td>" for v in [
            method, m["planned"], m["correct"], m["wrong"], m["uncertain"], m["failed"],
            m["abandoned"], m["interrupted"], m["not_started"], m["terminal_elapsed_ms"]["median"],
            m["returned_checks"]["wrong_clear"], m["returned_checks"]["false_ready"],
        ]) + "</tr>")
    cases = []
    for case in study["cases"]:
        details = "".join(f"<li>{escape(m)}: {escape(canonical(case['trials'][m]))}</li>" for m in METHODS)
        cases.append(f"<article><h2>{escape(case['label'])}</h2><p>Truth / 실제 수량 / 真值: {escape(canonical(case['truth']))}</p>"
                     f"<p>Photo SHA256: {escape(case['photo_sha256'])}</p><ul>{details}</ul></article>")
    limits = "".join(f"<li>{escape(s)}</li>" for s in LIMITATIONS)
    return f"""<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>KitGuard · {escape(study['title'])}</title><style>body{{font-family:system-ui,sans-serif;max-width:1150px;margin:32px auto;padding:0 18px;color:#193e37;background:#f7f8f5;line-height:1.65}}table{{border-collapse:collapse;width:100%;background:white}}td,th{{padding:10px;border:1px solid #ccd8d3;text-align:left}}.scroll{{overflow:auto}}article{{background:white;padding:18px;margin-top:20px;border:1px solid #ccd8d3;border-radius:12px}}li,p,h1,h2,code{{overflow-wrap:anywhere}}h1{{font-size:32px}}</style>
<h1>{escape(study['title'])}</h1><p>고정 상태 검증 기록 / 固定状态验证记录 · {escape(study['source_kind'])}</p>
<p>Anonymous participant: {escape(study['participant_code'])} · Closed: {escape(study['closed_at'])}</p>
<p>등록 / 已登记 {len(study['cases'])} / 예정 / 预定 {study['planned_cases']} · 계획 분모 유지 / 保留预定分母</p>
<div class="scroll"><table><thead><tr><th>Method</th><th>Planned</th><th>Correct</th><th>Wrong</th><th>Uncertain</th><th>Failed</th><th>Abandoned</th><th>Interrupted</th><th>Not started</th><th>Terminal median ms</th><th>All returned wrong</th><th>All returned false ready</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<p>计时包含所有已知终态，重启耗时未知不作0；全部返回错误单列，放弃不删除已返回证据。导出的完整JSON保留计时样本数、失败和所有绑定记录。</p><ul>{limits}</ul>{''.join(cases)}
<p>Protocol SHA256: {escape(study['protocol_sha256'])}</p><p>Runtime: {escape(canonical(study['runtime_identity']))}</p></html>"""
