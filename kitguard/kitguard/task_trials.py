"""Exploratory full-task trials. Real actions and identities remain human declarations.

This recorder is separate from fixed-state FieldStudies. It never runs inference,
changes historical studies, generates ground truth, or turns a test backend into AI.
"""
from __future__ import annotations

import copy
import hashlib
import json
import secrets
import statistics
import time
from contextlib import contextmanager
from pathlib import Path

from . import __version__
from .photo_documents import is_digital_only
from .public_demo_catalog import CATALOG
from .regions import family_tokens, stored_bytes, verify_photo_lineage
from .schemas import PARTS
from .store import StateError, now, uid
from .store import event as order_event

METHODS = ("manual", "rules", "kitguard")
SCENARIOS = ("normal", "revision", "missing")
IDENTITY_KEYS = ("repo_id", "revision", "observer_protocol_sha256", "observation_mode", "image_max_side")
PROTOCOL = {
    "name": "full_task_exploratory_v1", "scales": {"pilot9": 9, "study27": 27},
    "participants": 3, "methods": METHODS, "scenarios": SCENARIOS,
    "allocation": "m=(participant+position+block)%3; s=(participant+2*position+block)%3",
    "timing": "Server monotonic start before BOM reveal to participant submission; no pause; audit separate",
    "truth": "Host physically counts twice before start and after submission; host differs from participant",
    "scope": "Four visible coarse classes, 1-12 target pieces; no SKU or industrial release claim",
    "analysis": "Exploratory descriptive full denominator; no causal or statistical-significance claims",
    "revision": "First observation, then structured changed BOM is revealed and must be applied",
    "conditions": "All receive the same tray/reference access; manual counts, rules computes differences, KitGuard actual model",
}
LIMITATIONS = [
    "小样本探索性试用，不证明因果提效或统计显著 / 소규모 탐색 시험이며 인과 효과·통계적 유의성을 입증하지 않습니다.",
    "人物、同意、实物来源与独立计数均为人员声明，哈希和代号不能认证 / 신원·동의·실물 출처·독립 계수는 사람의 진술입니다.",
    "主持人与参与者令牌仅减少意外泄漏；本地工单API并非隔离实验室 / 토큰은 우발적 유출을 줄이며 인증된 맹검은 아닙니다.",
    "同一人会学习，匹配任务不是完全相同任务；不得把9或27任务当作9或27独立用户 / 반복 학습과 변형 과제가 있으며 사용자는 3명입니다.",
    "照片哈希可识别登记的精确来源，不能识别所有未登记裁剪、重压缩或新摆放真实性 / 등록되지 않은 변환·실제 촬영은 인증하지 못합니다.",
    "计时包括任务揭示后的拍照、上传、推理、调整及补拍；公共场地布置与主持人复核另列 / 시작 이후 촬영·업로드·추론·조정 포함, 사전 배치·사후 검수 제외.",
    "订单变更使用同一已结构化指令，不能推断自然语言改版准备成本 / 동일한 구조화 변경을 사용하며 자연어 준비 비용은 평가하지 않습니다.",
]
ROOT = Path(__file__).resolve().parents[1]


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()


def counts(value):
    if not isinstance(value, dict) or set(value) != set(PARTS) or any(type(v) is not int or not 0 <= v <= 100 for v in value.values()):
        raise StateError("四类数量须为0–100整数 / 네 종류의 수량은 0–100 정수입니다", 422)
    return value


def duration(values):
    values = [v for v in values if type(v) is int and v >= 0]
    return {"n": len(values), "median_ms": statistics.median(values) if values else None,
            "max_ms": max(values) if values else None}


def allocation(participants, scale):
    tasks = []
    for p, participant in enumerate(participants):
        for block in range(1 if scale == "pilot9" else 3):
            for position in range(3):
                method = METHODS[(p + position + block) % 3]
                scenario = SCENARIOS[(p + 2 * position + block) % 3]
                # Quantity variants must not track method: each method receives
                # every participant/block variant equally, with fresh layouts.
                variant = (p + block) % 3
                values = [2, 2, 1, 1]
                values = values[variant:] + values[:variant]
                target = dict(zip(PARTS, values))
                change_part = next(part for part in PARTS if target[part] == 2)
                initial_bom = copy.deepcopy(target)
                physical = copy.deepcopy(target)
                if scenario == "revision":
                    initial_bom[change_part] -= 1
                    physical = copy.deepcopy(initial_bom)
                if scenario == "missing":
                    physical[change_part] -= 1
                tasks.append({"id": f"P{p+1}-T{block*3+position+1:02d}", "participant_code": participant,
                              "sequence": block*3+position+1, "block": block+1, "method": method,
                              "scenario": scenario, "variant": variant+1, "initial_bom": initial_bom,
                              "target_bom": target, "planned_initial_counts": physical,
                              "status": "not_started", "setup": None, "order_id": None,
                              "started_at": None, "submitted_at": None, "elapsed_ms": None,
                              "current_bom": None, "change_revealed_at": None, "observations": [],
                              "events": [], "submission": None, "review": None, "evidence": None})
    return tasks


def public_inventory():
    """Read registered manifests only, never traverse/decode a user's image folder."""
    hashes = {row["source_sha256"] for row in CATALOG}
    coverage = [{"manifest": "kitguard/public_demo_catalog.py", "raw_hash_records": len(CATALOG),
                 "manifest_sha256": sha((ROOT / "kitguard/public_demo_catalog.py").read_bytes())}]
    sources = (
        ("datasets/manifests/mvtec_screws/manifest.json", "images"),
        ("datasets/manifests/mvtec_loco_screw_bag/manifest.json", "images"),
        ("datasets/raw/ino-10-190/SOURCE_MANIFEST.json", "files"),
        ("datasets/manifests/v0.3/CANONICAL_NEW_SOURCE_BENCHMARK_V1.json", "cases"),
        ("datasets/manifests/v0.4/ino_l_bracket_external_v1/manifest.json", "cases"),
        ("datasets/manifests/v0.4/ino_two_bracket_diagnostic_v1/manifest.json", "cases"),
        ("datasets/manifests/v0.4/ino_l_bracket_full_multi_v1/manifest.json", "cases"),
    )
    for relative, key in sources:
        path = ROOT / relative
        entry = {"manifest": relative, "raw_hash_records": 0}
        if path.is_file():
            raw = path.read_bytes()
            data = json.loads(raw)
            records = data[key]
            if key == "files":
                records = [r for r in records if Path(r["local_path"]).suffix.lower() in {".png", ".jpg", ".jpeg"}]
            for row in records:
                digest = row.get("sha256")
                if not isinstance(digest, str) or len(digest) != 64:
                    raise StateError("公开来源清单损坏 / 공개 출처 목록 오류")
                hashes.add(digest)
            entry.update(raw_hash_records=len(records), manifest_sha256=sha(raw))
        else:
            entry["gap"] = "missing manifest; this source is not covered"
        coverage.append(entry)
    return hashes, {"sources": coverage, "unique_raw_hashes": len(hashes), "normalized_pixel_records": 0,
                    "scope": "Registered raw hashes and known main-order normalized/source-family links only; no perceptual matching"}


def report(batch):
    result = {"protocol": PROTOCOL["name"], "scale": batch["scale"], "participants": 3,
              "source_kind": batch.get("source_kind", "self_reported_physical"),
              "physical_verified": False, "participant_identity_verified": False,
              "planned_tasks": len(batch["tasks"]), "methods": {}, "limitations": LIMITATIONS}
    for method in METHODS:
        tasks = [t for t in batch["tasks"] if t["method"] == method]
        summary = {"planned": len(tasks), "correct": 0, "wrong": 0, "unreviewed": 0,
                   "failed": 0, "abandoned": 0, "interrupted": 0, "not_started": 0, "takeovers": 0}
        for task in tasks:
            if task["status"] == "completed":
                key = "unreviewed" if task["review"] is None else ("correct" if task["review"]["matches_target"] else "wrong")
            elif task["status"] == "running":
                key = "unreviewed"
            else:
                key = task["status"]
            summary[key] += 1
            summary["takeovers"] += bool((task.get("submission") or {}).get("takeover"))
        summary["correct_fraction_full_planned"] = summary["correct"] / len(tasks)
        summary["terminal_time"] = duration([t["elapsed_ms"] for t in tasks if t["status"] not in {"not_started", "running"}])
        summary["completed_time"] = duration([t["elapsed_ms"] for t in tasks if t["status"] == "completed"])
        summary["correct_time"] = duration([t["elapsed_ms"] for t in tasks if t["status"] == "completed" and t["review"] and t["review"]["matches_target"]])
        summary["host_review_time"] = duration([(t.get("review") or {}).get("review_elapsed_ms") for t in tasks])
        summary["model_latency"] = duration([c.get("latency_ms") for t in tasks for c in (t.get("evidence") or {}).get("checks", [])])
        summary["returned_checks"] = sum(len((t.get("evidence") or {}).get("checks", [])) for t in tasks)
        summary["inference_failures"] = sum(e["kind"] == "inspection_failed" for t in tasks for e in (t.get("evidence") or {}).get("events", []))
        summary["per_scenario"] = {s: [{"task_id": t["id"], "participant_code": t["participant_code"],
                                      "status": t["status"], "elapsed_ms": t["elapsed_ms"],
                                      "matches_target": (t.get("review") or {}).get("matches_target")}
                                     for t in tasks if t["scenario"] == s] for s in SCENARIOS}
        result["methods"][method] = summary
    return result


class TaskTrials:
    def __init__(self, store, runtime_provider):
        self.store, self.runtime_provider = store, runtime_provider
        self.process_nonce = secrets.token_hex(16)
        with store.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS task_trial_batches (id TEXT PRIMARY KEY, body TEXT NOT NULL)")

    def runtime(self):
        value = self.runtime_provider()
        return {"app_version": __version__, **{key: value.get(key) for key in IDENTITY_KEYS}}

    @staticmethod
    def _put(db, batch):
        db.execute("INSERT OR REPLACE INTO task_trial_batches VALUES (?,?)", (batch["id"], canonical(batch)))

    @staticmethod
    def _get(db, batch_id):
        row = db.execute("SELECT body FROM task_trial_batches WHERE id=?", (batch_id,)).fetchone()
        if row is None:
            raise StateError("找不到试用批次 / 시험 배치를 찾을 수 없습니다", 404)
        return json.loads(row["body"])

    @contextmanager
    def transaction(self, batch_id):
        db = self.store.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            batch = self._get(db, batch_id)
            yield db, batch
            self._put(db, batch)
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def role(batch, token):
        digest = sha(token or "")
        if secrets.compare_digest(digest, batch["_host_token_sha256"]):
            return "host"
        for participant, expected in batch["_participant_tokens_sha256"].items():
            if secrets.compare_digest(digest, expected):
                return participant
        raise StateError("入口令牌无效 / 접근 토큰이 유효하지 않습니다", 403)

    @classmethod
    def host(cls, batch, token):
        if cls.role(batch, token) != "host":
            raise StateError("需要主持人入口 / 진행자 접근이 필요합니다", 403)

    @staticmethod
    def task(batch, task_id):
        task = next((t for t in batch["tasks"] if t["id"] == task_id), None)
        if task is None:
            raise StateError("找不到任务 / 과제를 찾을 수 없습니다", 404)
        return task

    @classmethod
    def participant(cls, batch, task, token):
        if cls.role(batch, token) != task["participant_code"]:
            raise StateError("请使用该参与者的入口 / 해당 참여자 입구를 사용하세요", 403)

    @staticmethod
    def event(task, kind, payload=None):
        task["events"].append({"kind": kind, "created_at": now(), "payload": payload or {}})

    def view(self, batch, role):
        value = copy.deepcopy(batch)
        value.pop("_host_token_sha256")
        value.pop("_participant_tokens_sha256")
        value["role"] = role
        for task in value["tasks"]:
            for key in list(task):
                if key.startswith("_"):
                    task.pop(key)
            if role != "host":
                for key in ("planned_initial_counts", "setup", "review", "evidence", "target_bom"):
                    task.pop(key, None)
                if task["status"] == "not_started":
                    task.pop("initial_bom", None)
                    task.pop("current_bom", None)
                task["prepared"] = bool(self.task(batch, task["id"])["setup"])
        if role != "host":
            value["tasks"] = [t for t in value["tasks"] if t["participant_code"] == role]
            value.pop("source_declaration", None)
        value["report"] = report(batch) if batch["status"] == "closed" and role == "host" else None
        return value

    def get(self, batch_id, token):
        with self.store.connect() as db:
            batch = self._get(db, batch_id)
        return self.view(batch, self.role(batch, token))

    def create(self, body):
        participants = body["participant_codes"]
        if len(participants) != 3 or len(set(participants)) != 3 or body["host_code"] in participants or "host" in participants:
            raise StateError("需要3个不同参与者代号，主持人须另一个人 / 참여자 3명과 별도 진행자 필요", 422)
        token = secrets.token_urlsafe(32)
        participant_tokens = {p: secrets.token_urlsafe(32) for p in participants}
        batch = {**body, "id": uid("tasks"), "status": "draft", "created_at": now(), "frozen_at": None,
                 "physical_verified": False, "participant_identity_verified": False,
                 "closed_at": None, "protocol": PROTOCOL, "limitations": LIMITATIONS,
                 "tasks": allocation(participants, body["scale"]), "runtime_identity": None,
                 "_host_token_sha256": sha(token),
                 "_participant_tokens_sha256": {p: sha(t) for p, t in participant_tokens.items()}}
        with self.store.connect() as db:
            self._put(db, batch)
        return {"batch": self.view(batch, "host"), "host_token": token, "participant_tokens": participant_tokens}

    def freeze(self, batch_id, token):
        with self.transaction(batch_id) as (_, batch):
            self.host(batch, token)
            if batch["status"] != "draft":
                raise StateError("只能冻结一次 / 한 번만 동결할 수 있습니다")
            _, coverage = public_inventory()
            batch.update(status="frozen", frozen_at=now(), runtime_identity=self.runtime(),
                         public_source_coverage=coverage, recorder_sha256=sha(Path(__file__).read_bytes()),
                         protocol_sha256=sha(canonical(PROTOCOL)), allocation_sha256=sha(canonical(allocation(batch["participant_codes"], batch["scale"]))))
        return self.get(batch_id, token)

    def setup(self, batch_id, task_id, token, body):
        with self.transaction(batch_id) as (_, batch):
            self.host(batch, token)
            task = self.task(batch, task_id)
            if batch["status"] not in {"draft", "frozen"} or task["status"] != "not_started" or task["setup"]:
                raise StateError("布置记录已锁定 / 배치 기록이 잠겼습니다")
            first, second = counts(body["counts"]), counts(body["counts_repeat"])
            if first != second or first != task["planned_initial_counts"]:
                raise StateError("两次实际计数须一致且符合预定布置；请调整实物 / 두 실물 계수가 계획 배치와 일치해야 합니다", 422)
            if not body["independent_confirmed"]:
                raise StateError("需要本人实物核对声明 / 직접 실물 확인 선언이 필요합니다", 422)
            task["setup"] = {**body, "host_code": batch["host_code"], "recorded_at": now()}
            task["setup_sha256"] = sha(canonical(task["setup"]))
            self.event(task, "host_setup_locked", {"setup_sha256": task["setup_sha256"]})
        return self.get(batch_id, token)

    def unchanged(self, batch):
        _, coverage = public_inventory()
        if (batch["runtime_identity"] != self.runtime() or batch["recorder_sha256"] != sha(Path(__file__).read_bytes())
                or batch["public_source_coverage"] != coverage):
            raise StateError("冻结后模型、记录器或公开来源清单变化；保留此批并另建批次 / 동결 후 구성이 변경되었습니다")

    def _new_order(self, db, batch, task):
        stamp = now()
        order = {"id": uid("ord"), "title": f'Trial {batch["id"][-6:]} {task["id"]}',
                 "requirements": copy.deepcopy(task["initial_bom"]), "revision": 1, "status": "pending",
                 "created_at": stamp, "updated_at": stamp, "latest_check": None, "checks": [], "photos": [],
                 "references": {}, "reference_history": [], "events": [], "completions": [], "evidence_epoch": 0,
                 "active_inspection": None, "revisions": [{"revision": 1, "requirements": copy.deepcopy(task["initial_bom"]),
                 "instruction": "试用初始订单 / 시험 최초 주문", "created_at": stamp}]}
        order_event(order, "order_created", "完整任务试用开始 / 전체 과제 시험 시작", {"batch_id": batch["id"], "task_id": task["id"]})
        self.store._put(db, order)
        return order

    def start(self, batch_id, task_id, token, body):
        with self.transaction(batch_id) as (db, batch):
            task = self.task(batch, task_id)
            self.participant(batch, task, token)
            if batch["status"] != "frozen" or task["status"] != "not_started" or not task["setup"]:
                raise StateError("需冻结分配并由主持人完成布置；任务只能开始一次 / 동결·배치 확인 후 한 번만 시작")
            if any(t["status"] == "running" for t in batch["tasks"]):
                raise StateError("已有进行中的任务 / 진행 중인 과제가 있습니다")
            if any(t["participant_code"] == task["participant_code"] and t["sequence"] < task["sequence"]
                   and t["status"] == "not_started" for t in batch["tasks"]):
                raise StateError("请按冻结顺序执行 / 동결한 순서대로 실행하세요")
            self.unchanged(batch)
            task.update(status="running", started_at=now(), _monotonic_started=time.monotonic(),
                        _process_nonce=self.process_nonce, current_bom=copy.deepcopy(task["initial_bom"]),
                        start_declarations=body)
            if task["method"] == "kitguard":
                task["order_id"] = self._new_order(db, batch, task)["id"]
            self.event(task, "started_and_bom_revealed")
        return self.get(batch_id, token)

    @staticmethod
    def running(batch, task):
        if batch["status"] != "frozen" or task["status"] != "running":
            raise StateError("任务未运行或已提交 / 과제가 실행 중이 아니거나 이미 제출됨")

    def observe(self, batch_id, task_id, token, body):
        with self.transaction(batch_id) as (_, batch):
            task = self.task(batch, task_id)
            self.participant(batch, task, token)
            self.running(batch, task)
            if task["method"] == "kitguard":
                raise StateError("KitGuard只能关联实际工单观察 / KitGuard는 실제 주문 관찰만 사용", 422)
            observation = {"counts": counts(body["counts"]), "at": now(), "bom": copy.deepcopy(task["current_bom"])}
            if task["method"] == "rules":
                observation["difference"] = {p: body["counts"][p] - task["current_bom"][p] for p in PARTS}
                observation["matches"] = body["counts"] == task["current_bom"]
            task["observations"].append(observation)
            self.event(task, "human_count_recorded", {"observation_index": len(task["observations"])-1})
        return self.get(batch_id, token)

    def reveal_change(self, batch_id, task_id, token):
        with self.transaction(batch_id) as (db, batch):
            task = self.task(batch, task_id)
            self.participant(batch, task, token)
            self.running(batch, task)
            if task["scenario"] != "revision" or task["change_revealed_at"]:
                raise StateError("此任务没有待揭示变更 / 공개할 변경이 없습니다")
            if task["method"] == "kitguard":
                order = self.store._get(db, task["order_id"])
                if order.get("active_inspection") or not order["checks"]:
                    raise StateError("先完成初始订单的实际检查，再揭示变更 / 최초 주문의 실제 검사 후 변경 공개")
                if order["revision"] != 1 or order["requirements"] != task["initial_bom"]:
                    raise StateError("初始订单已经被另外修改 / 최초 주문이 외부에서 변경됨")
            elif not task["observations"]:
                raise StateError("先记录初始订单的人工观察 / 먼저 최초 주문의 수동 관찰 기록")
            task["change_revealed_at"] = now()
            task["current_bom"] = copy.deepcopy(task["target_bom"])
            self.event(task, "changed_bom_revealed", {"requirements": task["current_bom"]})
        return self.get(batch_id, token)

    def log_action(self, batch_id, task_id, token, body):
        with self.transaction(batch_id) as (_, batch):
            task = self.task(batch, task_id)
            self.participant(batch, task, token)
            self.running(batch, task)
            self.event(task, "participant_declared_action", body)
        return self.get(batch_id, token)

    def capture(self, db, task):
        if not task["order_id"]:
            return {"events": [], "checks": [], "photos": [], "note": "No AI path for manual/rules"}
        order = self.store._get(db, task["order_id"])
        return {**copy.deepcopy(order), "captured_at": now()}

    def verify_ai(self, db, batch, task, order):
        if is_digital_only(order) or not order["photos"] or not order["checks"]:
            if "document_source" in order:
                raise StateError("자료 사진 주문은 실물 시험이 아닙니다 / 资料照片工单不能作为实物试验")
            raise StateError("需要真实工单照片和实际模型检查；公开演示不合格 / 실물 주문 사진·모델 검사 필요")
        self.store._nonpublic_family(db, order, order["photos"][-1])
        public, _ = public_inventory()
        all_family = set()
        for photo in order["photos"]:
            stored_bytes(self.store, photo, db)
            verify_photo_lineage(self.store, order, photo, db)
            all_family |= family_tokens(photo)
        if all_family & public:
            raise StateError("登记公开来源不能作为新实物试用 / 등록된 공개 사진은 새 실물 시험이 아닙니다")
        for row in db.execute("SELECT body FROM orders"):
            other = json.loads(row["body"])
            if other["id"] != order["id"] and any(family_tokens(photo) & all_family for photo in other["photos"]):
                raise StateError("照片与其他工单重叠，不能算新任务 / 다른 주문과 사진이 중복됩니다")
        for reference in order["references"].values():
            stored_bytes(self.store, reference, db)
        for check in order["checks"]:
            if check.get("backend") != "mlx" or any(check.get("runtime_identity", {}).get(k) != batch["runtime_identity"].get(k) for k in IDENTITY_KEYS):
                raise StateError("工程替身或不同模型不能冒充真实AI记录 / 테스트 대역·다른 모델은 실제 AI 기록이 아닙니다")
            photo = next((p for p in order["photos"] if p["id"] == check.get("photo_id")), None)
            if not photo or check.get("photo_sha256") != photo["sha256"]:
                raise StateError("检查与照片绑定无效 / 검사 사진 연결 오류")
        if any(batch["runtime_identity"].get(k) is None for k in IDENTITY_KEYS):
            raise StateError("模型身份不完整 / 모델 식별 정보 불완전")
        if task["scenario"] == "revision":
            if len(order["revisions"]) != 2 or order["revisions"][-1]["requirements"] != task["target_bom"]:
                raise StateError("请按已揭示要求在主工单批准一次改版 / 공개 요구대로 한 번 변경 승인")
        elif order["revision"] != 1:
            raise StateError("非变更场景不允许修改需求 / 변경 없는 과제의 요구 수정 불가")
        check = order.get("latest_check")
        if (order["requirements"] != task["target_bom"] or order["status"] != "completed" or not order["completions"]
                or not check or not check.get("valid") or check["decision"] != "ready"
                or check["revision"] != order["revision"] or check["photo_id"] != order["photos"][-1]["id"]
                or check["evidence_epoch"] != order["evidence_epoch"]
                or order["completions"][-1]["check_id"] != check["id"]):
            raise StateError("请完成主工单当前版本核验与人工确认；不能完成则记录失败 / 최신 주문 검사·수동 확인 완료 필요")

    def submit(self, batch_id, task_id, token, body):
        submitted_at, submitted_monotonic = now(), time.monotonic()
        with self.transaction(batch_id) as (db, batch):
            task = self.task(batch, task_id)
            self.participant(batch, task, token)
            self.running(batch, task)
            if task.get("_process_nonce") != self.process_nonce:
                raise StateError("此前进程的计时不能继续；请恢复中断记录 / 이전 프로세스 계시를 계속할 수 없습니다")
            order = self.store._get(db, task["order_id"]) if task["order_id"] else None
            if order and order.get("active_inspection"):
                raise StateError("模型请求仍在运行，请等待返回后提交 / 모델 요청 종료 후 제출하세요")
            if body["outcome"] == "completed":
                self.unchanged(batch)
                if task["scenario"] == "revision" and not task["change_revealed_at"]:
                    raise StateError("还未执行订单变更 / 주문 변경을 아직 실행하지 않음")
                if task["method"] == "kitguard":
                    self.verify_ai(db, batch, task, order)
                elif not task["observations"] or task["observations"][-1]["bom"] != task["target_bom"]:
                    raise StateError("先记录最终需求下的实际计数 / 최종 요구에 대한 실제 계수 기록 필요")
            elif not body.get("note", "").strip():
                raise StateError("请保留失败或放弃原因 / 실패·포기 사유 필요", 422)
            task["evidence"] = self.capture(db, task)
            task["ai_completion_evidence_validated"] = task["method"] == "kitguard" and body["outcome"] == "completed"
            task["ai_evidence_note"] = ("Passed registered-source/model/order checks; physical source still a declaration"
                                        if task["ai_completion_evidence_validated"] else
                                        "No validated AI completion claimed; raw failures/checks retained for inspection")
            task["evidence_sha256"] = sha(canonical(task["evidence"]))
            task.update(status=body["outcome"], submitted_at=submitted_at, submission=body,
                        elapsed_ms=max(0, round((submitted_monotonic-task["_monotonic_started"])*1000)))
            self.event(task, "participant_submitted", {"outcome": task["status"], "elapsed_ms": task["elapsed_ms"]})
        return self.get(batch_id, token)

    def begin_review(self, batch_id, task_id, token):
        with self.transaction(batch_id) as (_, batch):
            self.host(batch, token)
            task = self.task(batch, task_id)
            if batch["status"] != "frozen" or task["status"] in {"not_started", "running"} or task["review"]:
                raise StateError("参与者提交后由主持人核对一次 / 참여자 제출 후 진행자가 한 번 검수")
            if task.get("_review_started"):
                raise StateError("复核已经开始 / 검수가 이미 시작됨")
            task.update(_review_started=time.monotonic(), _review_nonce=self.process_nonce, review_started_at=now())
        return self.get(batch_id, token)

    def review(self, batch_id, task_id, token, body):
        with self.transaction(batch_id) as (_, batch):
            self.host(batch, token)
            task = self.task(batch, task_id)
            if batch["status"] != "frozen" or task["status"] in {"not_started", "running"} or task["review"] or not task.get("review_started_at"):
                raise StateError("先开始独立复核；已提交复核不能覆盖 / 독립 검수 시작 후 한 번 제출")
            first, second = counts(body["counts"]), counts(body["counts_repeat"])
            if first != second:
                raise StateError("两次数量不一致，请重新实物核对 / 두 계수가 다릅니다", 422)
            if body["reviewer_code"] != batch["host_code"] or body["reviewer_code"] == task["participant_code"]:
                raise StateError("须由预登记主持人核对，不能参与者自证 / 등록 진행자의 독립 검수 필요", 422)
            elapsed = max(0, round((time.monotonic()-task["_review_started"])*1000)) if task.get("_review_nonce") == self.process_nonce else None
            task["review"] = {**body, "recorded_at": now(), "review_elapsed_ms": elapsed,
                              "matches_target": first == task["target_bom"],
                              "counts_match_participant": first == task["observations"][-1]["counts"] if task["observations"] else None}
            self.event(task, "host_review_locked", {"review_sha256": sha(canonical(task["review"]))})
        return self.get(batch_id, token)

    def close(self, batch_id, token):
        with self.transaction(batch_id) as (_, batch):
            self.host(batch, token)
            if batch["status"] == "closed" or any(t["status"] == "running" for t in batch["tasks"]):
                raise StateError("请先提交正在运行的任务；关闭后不能重开 / 실행 과제 제출 후 닫기")
            batch.update(status="closed", closed_at=now())
        return self.get(batch_id, token)

    def recover_interrupted(self):
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for row in db.execute("SELECT body FROM task_trial_batches").fetchall():
                batch = json.loads(row["body"])
                for task in batch["tasks"]:
                    if task["status"] == "running":
                        task.update(status="interrupted", submitted_at=now(), elapsed_ms=None,
                                    submission={"outcome": "interrupted", "takeover": False, "note": "Server restarted; elapsed unknown"})
                        task["evidence"] = self.capture(db, task)
                        task["evidence_sha256"] = sha(canonical(task["evidence"]))
                        self.event(task, "server_interrupted")
                self._put(db, batch)

    def export(self, batch_id, token):
        with self.store.connect() as db:
            batch = self._get(db, batch_id)
            self.host(batch, token)
            if batch["status"] != "closed":
                raise StateError("关闭批次后才能导出 / 배치를 닫은 후 내보내기")
            for task in batch["tasks"]:
                evidence = task.get("evidence")
                if evidence is not None:
                    if sha(canonical(evidence)) != task["evidence_sha256"]:
                        raise StateError("提交快照已改变 / 제출 스냅샷 변경됨")
                    for photo in evidence.get("photos", []):
                        stored_bytes(self.store, photo, db)
            value = self.view(batch, "host")
        return {"schema_version": 1, "kind": "kitguard_full_task_exploratory", "batch": value,
                "payload_sha256": sha(canonical(value)), "hash_note": "Integrity checksum, not a signature or source/person certification"}
