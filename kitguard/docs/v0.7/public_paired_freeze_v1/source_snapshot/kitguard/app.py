"""Local HTTP interface; all completion decisions go through the transactional store."""

import asyncio
import hashlib
import io
import json
import logging
import math
import os
import time
import warnings
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, ImageStat, UnidentifiedImageError
from pydantic import ValidationError
from starlette.background import BackgroundTask
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .detector_lab import create_detector_lab_router
from .evidence import build_evidence_archive
from .feedback import evidence_feedback, observation_context, prior_unclear_evidence_count, reference_ids
from .field_api import study_router
from .field_study import FieldStudies
from .inspection_jobs import InspectionJobs, create_inspection_jobs_router
from .manual_review import create_manual_review_router
from .public_demo_catalog import CATALOG as PUBLIC_DEMOS
from .public_review import create_public_review_router
from .readiness import create_readiness_router
from .regions import InspectionRegion, inspection_scope, verify_photo_lineage
from .runtime import DataDirectoryLease, InferenceGate
from .schemas import (
    LABELS,
    PARTS,
    Completion,
    Inspection,
    NewOrder,
    Observation,
    Proposal,
    Requirements,
    Revision,
)
from .store import StateError, Store, expect_revision, now, uid
from .task_trial_api import task_trial_router
from .task_trials import TaskTrials

PACKAGE = Path(__file__).resolve().parent
MAX_UPLOAD = 12 * 1024 * 1024
log = logging.getLogger("kitguard")


class LazyVision:
    def __init__(self):
        self.instance = None

    def get(self):
        if self.instance is None:
            from .vision import LocalVision

            self.instance = LocalVision()
        return self.instance

    def status(self):
        try:
            return self.get().status()
        except (ImportError, OSError):
            return {
                "available": False,
                "loaded": False,
                "label": "Qwen3.6-27B · MLX 4-bit",
                "path": str(Path.home() / "Downloads/AI-Models/Qwen3.6-27B-4bit"),
                "error": "모델 환경을 준비 중입니다 / 模型环境尚未就绪",
            }

    def observe(self, *args, **kwargs):
        return self.get().observe(*args, **kwargs)

    def observe_with_context(self, *args, **kwargs):
        return self.get().observe_with_context(*args, **kwargs)

    def propose_revision(self, *args, **kwargs):
        return self.get().propose_revision(*args, **kwargs)


def decide(snapshot, observation, photo_id, elapsed):
    observed = observation.observed.model_dump()
    differences = [
        {
            "part": part,
            "required": snapshot["requirements"][part],
            "observed": observed[part],
            "delta": None if observed[part] is None else observed[part] - snapshot["requirements"][part],
        }
        for part in PARTS
    ]
    action = observation.action.model_dump()
    issues = observation.issues[:]
    uncertain = any(v is None for v in observed.values()) or bool(issues) or action["kind"] != "none"
    if action["kind"] == "manual":
        decision = "manual"
    elif uncertain:
        # Two additional distinct photos per consecutive unclear episode, scoped to
        # the current revision and references. Same-photo retries do not spend it.
        previous_count = prior_unclear_evidence_count(snapshot, photo_id)
        decision = "manual" if previous_count >= 2 else "recapture"
        if decision == "manual":
            action = {
                "kind": "manual",
                "message": "두 번의 보완 후에도 불명확합니다. 직접 확인하세요 / 两轮补证后仍不明确，请人工核对",
                "region": action["region"],
            }
        elif action["kind"] == "none":
            action = {
                "kind": "separate",
                "message": "겹친 부품을 번호 칸에 하나씩 분리하고 전체를 다시 촬영하세요 / 请将零件分开放到编号格，每格一件后重新拍摄全图",
                "region": None,
            }
    elif any(d["delta"] != 0 for d in differences):
        decision = "correct"
        changes = []
        for d in differences:
            if d["delta"]:
                ko, zh = LABELS[d["part"]]
                changes.append(
                    f"{ko}/{zh} {'추가/补充' if d['delta'] < 0 else '제거/取出'} {abs(d['delta'])}"
                )
        action = {
            "kind": "add_remove",
            "message": " · ".join(changes) + " → 다시 촬영 / 然后重新拍摄",
            "region": None,
        }
    else:
        decision = "ready"
        action = {
            "kind": "none",
            "message": "수량이 일치합니다. 실물을 확인한 뒤 완료하세요 / 数量相符，请核对实物后确认完成",
            "region": None,
        }
    check = {
        "id": uid("chk"),
        "order_id": snapshot["id"],
        "revision": snapshot["revision"],
        "photo_id": photo_id,
        "decision": decision,
        "observed": observed,
        "differences": differences,
        "issues": issues,
        "action": action,
        "model_label": observation.model_label,
        "backend": observation.backend,
        "latency_ms": elapsed,
        "created_at": now(),
        "valid": False,
    }
    check["requirements_snapshot"] = dict(snapshot["requirements"])
    current_photo = next((p for p in snapshot.get("photos", []) if p["id"] == photo_id), None)
    if current_photo is not None:
        check["inspection_scope"] = inspection_scope(snapshot, current_photo)
        check["source_family_sha256"] = check["inspection_scope"]["source_family_sha256"]
        if check["inspection_scope"]["mode"] == "region" and decision == "ready":
            check["action"]["message"] = "영역 안 수량이 일치합니다. 영역 밖은 검사하지 않았습니다. 실물을 확인하세요 / 选区内数量与要求一致，框外未核验，请核对实物"
    if observation.verification is not None:
        check["observation_verification"] = observation.verification.model_dump()
    if observation.identity_verification is not None:
        check["identity_verification"] = observation.identity_verification.model_dump()
    if observation.object_evidence is not None:
        check["object_evidence"] = observation.object_evidence.model_dump()
    check["reference_ids"] = reference_ids(snapshot)
    check["evidence_feedback"] = evidence_feedback(snapshot, check)
    check["tool_trace"] = [
        {
            "step": "observe_image",
            "status": "completed",
            "model": observation.model_label,
            "latency_ms": elapsed,
        },
        {"step": "compare_current_requirements", "status": "completed", "revision": snapshot["revision"]},
        {
            "step": "review_previous_evidence",
            "status": "completed" if check["evidence_feedback"] else "not_applicable",
        },
        {
            "step": "choose_next_action",
            "status": "completed",
            "decision": decision,
            "action_kind": action["kind"],
        },
    ]
    if observation.verification is not None:
        check["tool_trace"].insert(
            1,
            {
                "step": "compare_orientation_observations",
                "status": "completed",
                "clear_agreement": observation.verification.clear_agreement,
                "same_model_correlated_calls": True,
            },
        )
    if observation.identity_verification is not None:
        check["tool_trace"].insert(2, {
            "step": "verify_local_identity", "status": "completed",
            "blocked_categories": observation.identity_verification.blocked_categories,
            "same_model_correlated_calls": True,
        })
    if observation.object_evidence is not None:
        check["tool_trace"].insert(
            1,
            {
                "step": "derive_counts_from_object_list",
                "status": "completed",
                "listed_objects": len(observation.object_evidence.objects),
                "uncertain_parts": observation.object_evidence.uncertain_parts,
            },
        )
    return check


def create_app(data_dir: Path | None = None, analyzer=None, inference_timeout: float | None = None,
               demo_dataset_root: Path | None = None, detector_checkpoint: Path | None = None,
               detector_predictor=None):
    directory = Path(data_dir or os.environ.get("KITGUARD_DATA_DIR", str(PACKAGE.parent / "data")))
    store = Store(directory)
    demo_root = Path(demo_dataset_root or os.environ.get("KITGUARD_DATASET_DIR", PACKAGE.parent / "datasets")).resolve()
    engine = analyzer if analyzer is not None else LazyVision()
    studies = FieldStudies(store, engine.status)
    task_trials = TaskTrials(store, engine.status)
    timeout = float(
        inference_timeout
        if inference_timeout is not None
        else os.environ.get("KITGUARD_INFERENCE_TIMEOUT_SECONDS", "300")
    )
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Inference timeout must be a finite positive number")
    inference_gate = InferenceGate()
    inspection_jobs = InspectionJobs(store, inference_gate)

    @asynccontextmanager
    async def lifespan(_app):
        lease = DataDirectoryLease(directory).acquire()
        try:
            inference_gate.open()
            store.recover_interrupted()
            studies.recover_interrupted()
            task_trials.recover_interrupted()
            inspection_jobs.recover_interrupted()
            yield
        finally:
            await inspection_jobs.close()
            # A timed-out model thread may outlive the HTTP server. Keep data
            # ownership until it finishes; another instance must not recover it.
            inference_gate.close_when_idle(lease.close)

    app = FastAPI(title="KitGuard", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.store, app.state.analyzer = store, engine
    app.state.studies = studies
    app.state.task_trials = task_trials
    app.include_router(study_router(studies))
    app.include_router(task_trial_router(task_trials))
    app.include_router(create_public_review_router(store, engine.status, catalog=PUBLIC_DEMOS))
    detector_path = detector_checkpoint or os.environ.get("KITGUARD_DETECTOR_CHECKPOINT")
    detector_router = create_detector_lab_router(
        directory / "detector-lab", Path(detector_path) if detector_path else None,
        predictor=detector_predictor,
    )
    app.include_router(detector_router)
    detector_status = next(route.endpoint for route in detector_router.routes
                           if route.path == "/api/detector-lab/status")
    app.include_router(create_readiness_router(store=store, engine=engine,
        inference_gate=inference_gate, package=PACKAGE, detector_status=detector_status))
    app.state.inference_gate = inference_gate
    app.state.inspection_jobs = inspection_jobs
    app.include_router(create_inspection_jobs_router(inspection_jobs))

    @app.exception_handler(RequestValidationError)
    async def invalid_input(_request, exc):
        # Non-standard JSON NaN/Infinity may reach validation; never echo those
        # non-finite values into Starlette's strict JSON error serializer.
        errors = [{"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
                  for error in exc.errors()]
        return JSONResponse({"detail": errors}, status_code=422)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver", "[::1]"])

    @app.middleware("http")
    async def local_browser_boundary(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method not in ("GET", "HEAD", "OPTIONS") and origin:
            parsed = urlparse(origin)
            if parsed.netloc != request.headers.get("host") or parsed.scheme not in ("http", "https"):
                return JSONResponse(
                    {"detail": "로컬 앱 화면에서 요청하세요 / 请从本地应用界面操作"}, status_code=403
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; connect-src 'self'; media-src 'self' blob:; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        elif request.url.path == "/" or request.url.path.startswith("/static/"):
            # Revalidate local UI assets after upgrades instead of heuristic stale caching.
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.exception_handler(StateError)
    async def state_error(_request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=exc.code)

    @app.get("/api/health")
    async def health():
        return {"ok": True, "model": engine.status(), "version": __version__,
                "inference": inference_gate.status()}

    @app.get("/api/catalog")
    async def catalog():
        return {
            "parts": [{"id": p, "label_ko": LABELS[p][0], "label_zh": LABELS[p][1]} for p in PARTS],
            "limits": {"per_part": 3, "total": 12},
        }

    @app.get("/api/orders")
    async def orders():
        return {"orders": store.list()}

    @app.post("/api/orders", status_code=201)
    async def new_order(body: NewOrder):
        return {"order": store.create(body.title, body.requirements.model_dump())}

    @app.get("/api/orders/{order_id}")
    async def get_order(order_id: str):
        return {"order": store.get(order_id)}

    @app.post("/api/orders/{order_id}/revise")
    async def revise(order_id: str, body: Revision):
        return {
            "order": store.revise(
                order_id, body.requirements.model_dump(), body.instruction, body.expected_revision
            )
        }

    @app.post("/api/orders/{order_id}/propose-revision")
    async def propose(order_id: str, body: Proposal):
        snapshot = store.get(order_id)
        expect_revision(snapshot, body.expected_revision)
        try:
            with inference_gate.reserve() as slot:
                result = await slot.run(
                    engine.propose_revision, body.instruction, snapshot["requirements"], timeout=timeout
                )
            req = Requirements.model_validate(result["requirements"])
            explanation = result.get("explanation", "수정안을 확인하세요 / 请确认修改提案")
            if not isinstance(explanation, str) or len(explanation) > 3000:
                raise ValueError("invalid explanation")
        except StateError:
            raise
        except TimeoutError:
            raise HTTPException(
                504,
                "모델 응답 시간이 초과되었습니다. 수량을 직접 편집할 수 있습니다 / 模型响应超时，可直接编辑数量",
            )
        except (ValueError, ValidationError, KeyError, TypeError):
            raise HTTPException(
                422, "수정 지시를 명확히 하거나 수량을 직접 편집하세요 / 变更意图不明确，请说明或直接编辑数量"
            )
        except Exception:
            log.exception("Revision proposal unavailable")
            raise HTTPException(
                503,
                "로컬 모델을 사용할 수 없습니다. 수량을 직접 편집할 수 있습니다 / 本地模型不可用，可直接编辑数量",
            )
        expect_revision(store.get(order_id), snapshot["revision"])
        return {
            "proposal": {
                "requirements": req.model_dump(),
                "explanation": explanation,
                "base_revision": snapshot["revision"],
            }
        }

    async def receive_photo(order_id, upload, expected=None, part=None):
        # Validate state before writing and then again atomically when inserting metadata.
        current = store.get(order_id)
        if expected is not None:
            expect_revision(current, expected)
        raw = await upload.read(MAX_UPLOAD + 1)
        await upload.close()
        if len(raw) > MAX_UPLOAD:
            raise HTTPException(413, "사진은 12MB 이하여야 합니다 / 照片须小于12MB")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                im = Image.open(io.BytesIO(raw))
                if im.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValueError("format")
                if getattr(im, "n_frames", 1) != 1:
                    raise ValueError("multiple frames")
                if min(im.size) < 32 or max(im.size) > 8192 or im.width * im.height > 16_000_000:
                    raise ValueError("dimensions")
                im.load()
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
                # Re-encoding prevents executable uploads and strips EXIF/location metadata.
                normalized = io.BytesIO()
                im.save(normalized, format="JPEG", quality=95)
                content = normalized.getvalue()
                brightness = ImageStat.Stat(im.convert("L")).mean[0]
        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ):
            raise HTTPException(
                422,
                "단일 프레임 JPEG/PNG/WebP 사진(32px 이상, 1600만 화소 이하)을 사용하세요 / 请使用单帧JPEG、PNG或WebP照片，至少32像素且不超过1600万像素",
            )
        photo_id = uid("img")
        path = store.photos_dir / f"{photo_id}.jpg"
        path.write_bytes(content)
        warning = "노출을 조정하세요 / 请调整曝光" if brightness < 20 or brightness > 245 else None
        photo = {
            "id": photo_id,
            "url": f"/api/photos/{photo_id}",
            "sha256": hashlib.sha256(content).hexdigest(),
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            "revision": current["revision"],
            "created_at": now(),
            "width": im.width,
            "height": im.height,
            "quality": {"warning": warning},
        }
        if not part:
            photo.update({"kind": "root_photo", "scope_mode": "whole_image", "root_photo_id": photo_id,
                          "root_photo_sha256": photo["sha256"], "source_family_sha256": photo["sha256"]})
        try:
            order = store.add_photo(order_id, photo, path, expected, part)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return {"order": order, "photo": photo}

    @app.post("/api/orders/{order_id}/photos", status_code=201)
    async def upload_photo(
        order_id: str, photo: Annotated[UploadFile, File()], expected_revision: Annotated[int, Form()]
    ):
        return await receive_photo(order_id, photo, expected_revision)

    @app.post("/api/orders/{order_id}/references/{part}", status_code=201)
    async def upload_reference(
        order_id: str, part: str, photo: Annotated[UploadFile, File()],
        expected_revision: Annotated[int | None, Form()] = None,
    ):
        if part not in PARTS:
            raise HTTPException(422, "알 수 없는 부품 / 未知零件类型")
        return await receive_photo(order_id, photo, expected_revision, part=part)

    def demo_source(sample_id):
        spec = next((d for d in PUBLIC_DEMOS if d["sample_id"] == sample_id), None)
        if spec is None:
            raise HTTPException(404, "공개 예시를 찾을 수 없습니다 / 找不到公开样例")
        path = (demo_root / spec["image"]).resolve()
        if not path.is_relative_to(demo_root) or not path.is_file():
            raise HTTPException(404, "공개 원본이 준비되지 않았습니다 / 本机尚未准备此公开数据")
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != spec["source_sha256"]:
            raise HTTPException(409, "공개 원본의 해시가 다릅니다 / 公开源图校验失败")
        return spec, content

    @app.get("/api/public-demos")
    async def public_demos():
        demos = []
        for spec in PUBLIC_DEMOS:
            try:
                demo_source(spec["sample_id"])
                available = True
            except HTTPException:
                available = False
            demos.append({**{k: v for k, v in spec.items() if k != "image"}, "available": available})
        return {"samples": demos}

    @app.get("/api/public-demos/{sample_id}/photo")
    async def public_demo_photo(sample_id: str):
        _, content = demo_source(sample_id)
        return Response(content, media_type="image/png")

    @app.post("/api/public-demos/{sample_id}/orders", status_code=201)
    async def public_demo_order(sample_id: str):
        spec, content = demo_source(sample_id)
        provenance = {k: v for k, v in spec.items() if k not in {"image", "requirements", "title"}}
        provenance["kind"] = "public_photo_demo"
        provenance["physical_completion_allowed"] = False
        order = store.create("[PUBLIC DEMO] " + spec["title"],
                             Requirements.model_validate(spec["requirements"]).model_dump(), demo_source=provenance)
        # Same validated upload pipeline; no model invocation or cached observation.
        return await receive_photo(order["id"], UploadFile(file=io.BytesIO(content), filename=sample_id + ".png"), 1)

    @app.get("/api/photos/{photo_id}")
    async def photo_file(photo_id: str):
        return FileResponse(store.photo_path(photo_id), media_type="image/jpeg")

    @app.post("/api/orders/{order_id}/inspection-region")
    async def select_inspection_region(order_id: str, body: InspectionRegion):
        return store.select_region(order_id, body.model_dump())

    @app.post("/api/orders/{order_id}/inspect")
    async def inspect(order_id: str, body: Inspection):
        # Reserve before invalidating an existing check. Busy requests do not
        # mutate evidence or enqueue work that could expire before it starts.
        with inference_gate.reserve() as slot:
            token, snapshot = store.begin_inspection(order_id, body.photo_id, body.expected_revision)
            return await inspect_reserved(order_id, body, token, snapshot, slot)

    def verify_evidence_files(snapshot):
        photographs = ([snapshot["photos"][-1]] if snapshot["photos"] else [])
        if photographs:
            verify_photo_lineage(store, snapshot, photographs[0])
        photographs += list(snapshot["references"].values())
        for photograph in photographs:
            path = store.photo_path(photograph["id"])
            if hashlib.sha256(path.read_bytes()).hexdigest() != photograph.get("sha256"):
                raise StateError("사진 무결성 확인 실패 · 다시 업로드하세요 / 照片完整性校验失败，请重新上传")

    async def inspect_reserved(order_id, body, token, snapshot, slot):
        started = time.perf_counter()
        try:
            verify_evidence_files(snapshot)
            image_path = store.photo_path(body.photo_id)
            refs = {part: store.photo_path(pic["id"]) for part, pic in snapshot["references"].items()}
            context = observation_context(snapshot)
            contextual_observer = getattr(engine, "observe_with_context", None)
            if context is not None and callable(contextual_observer):
                result = await slot.run(
                    contextual_observer, image_path, snapshot["requirements"], refs, context, timeout=timeout
                )
            else:
                result = await slot.run(engine.observe, image_path, snapshot["requirements"], refs, timeout=timeout)
            verify_evidence_files(snapshot)
            observation = Observation.model_validate(result)
            runtime = engine.status()
            review = observation.identity_verification
            if review is not None and review.source_sha256 != snapshot["photos"][-1]["sha256"]:
                raise ValueError("Identity evidence is not bound to the current uploaded photograph")
            if runtime.get("observation_mode") == "spatial_guarded":
                verification = observation.verification
                if verification is None or verification.mode != "spatial_consensus":
                    raise ValueError("Guarded observation requires both spatial passes")
                candidates = any(o.part in {"nut", "washer"} for o in verification.passes[0].objects)
                if verification.clear_agreement and candidates and review is None:
                    raise ValueError("Guarded clear ring candidates require identity verification")
            check = decide(
                snapshot, observation, body.photo_id, round((time.perf_counter() - started) * 1000)
            )
            check["photo_sha256"] = snapshot["photos"][-1]["sha256"]
            check["observation_context"] = context
            check["runtime_identity"] = {
                key: runtime.get(key)
                for key in (
                    "label",
                    "repo_id",
                    "revision",
                    "observer_protocol_sha256",
                    "observation_mode",
                    "image_max_side",
                )
            }
            order = store.finish_inspection(order_id, token, snapshot, check)
        except StateError as exc:
            store.fail_inspection(order_id, token, str(exc))
            raise
        except asyncio.CancelledError:
            store.fail_inspection(order_id, token, "요청 중단 / 请求中断")
            raise
        except TimeoutError:
            store.fail_inspection(order_id, token, "모델 응답 시간 초과 / 模型响应超时")
            raise HTTPException(
                504,
                "관찰 시간이 초과되어 완료하지 않았습니다. 모델이 계속 처리 중일 수 있으니 잠시 후 다시 시도하세요 / 观察超时，未记为完成；模型可能仍在处理，请稍后重试",
            )
        except Exception as exc:
            store.fail_inspection(
                order_id,
                token,
                "모델 응답을 검증할 수 없습니다 / 无法取得有效模型观察",
                diagnostics=getattr(exc, "observation_diagnostics", None),
            )
            log.exception("Inspection failed")
            raise HTTPException(
                503,
                "관찰에 실패하여 완료 처리하지 않았습니다. 모델 상태를 확인하고 재시도하세요 / 观察失败，未记为完成；请检查模型状态后重试",
            )
        return {"order": order, "check": order["latest_check"]}

    inspection_jobs.runner = inspect_reserved
    app.include_router(create_manual_review_router(store, verify_evidence_files))

    @app.post("/api/orders/{order_id}/complete")
    async def complete(order_id: str, body: Completion):
        current = store.get(order_id)
        if current["status"] in {"ready", "completed", "manual_reviewed"}:
            verify_evidence_files(current)
        return store.complete(order_id, body.model_dump())

    @app.get("/api/orders/{order_id}/export")
    async def export(order_id: str):
        order = store.get(order_id)
        for photograph in order["photos"]:
            verify_photo_lineage(store, order, photograph)
        data = {
            "schema_version": 1,
            "exported_at": now(),
            "order": order,
            "limitations": [
                "Desktop prototype; no industrial performance claim.",
                "Photo hashes provide traceability, not proof of scene authenticity.",
                "Printed names, model observations and completion are not industrial safety certification.",
            ],
        }
        return Response(
            json.dumps(data, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="kitguard-{order["id"]}.json"'},
        )

    @app.get("/api/orders/{order_id}/evidence.zip")
    async def evidence_zip(order_id: str):
        path = await asyncio.to_thread(build_evidence_archive, store, order_id)
        return FileResponse(
            path,
            media_type="application/zip",
            filename=f"kitguard-{order_id}-evidence.zip",
            background=BackgroundTask(path.unlink, missing_ok=True),
        )

    @app.get("/api/templates/tray.svg")
    async def tray():
        cells = []
        for i in range(12):
            x, y = 15 + (i % 4) * 68, 35 + (i // 4) * 54
            cells.append(
                f'<rect x="{x}" y="{y}" width="64" height="50" rx="3" fill="white" stroke="#53676f" stroke-width="0.5"/>'
                f'<text x="{x + 4}" y="{y + 8}" font-size="4" fill="#53676f">{i + 1:02}</text>'
            )
        svg = '<svg xmlns="http://www.w3.org/2000/svg" width="297mm" height="210mm" viewBox="0 0 297 210"><rect width="297" height="210" fill="white"/>'
        svg += '<text x="15" y="18" font-family="sans-serif" font-size="7" fill="#152b35">KitGuard / Evidence tray</text>'
        svg += '<text x="15" y="26" font-family="sans-serif" font-size="3.5">One item per slot. Keep the entire tray visible. Do not infer hidden items.</text>'
        return Response(
            svg + "".join(cells) + "</svg>",
            media_type="image/svg+xml",
            headers={"Content-Disposition": 'attachment; filename="kitguard-tray-A4.svg"'},
        )

    @app.get("/")
    async def index():
        return FileResponse(PACKAGE / "static/index.html")

    app.mount("/static", StaticFiles(directory=PACKAGE / "static"), name="static")
    return app


app = create_app()
