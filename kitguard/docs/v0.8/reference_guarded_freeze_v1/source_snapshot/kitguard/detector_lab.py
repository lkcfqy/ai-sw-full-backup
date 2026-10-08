"""Optional, isolated bolt/nut photo experiments; never reads or changes orders.

Importing this module never imports torch or loads weights. A configured real
predictor runs in a CPU-only subprocess with a 90-second deadline. The router
owns its lifespan and exclusive storage lease. Shutdown stops admission; an
in-flight worker retains its lease until it actually exits, avoiding late writes
into a subsequently opened instance. Interrupted jobs are recovered on startup.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import io
import json
import math
import os
import re
import subprocess
import sys
import threading
import time
import uuid
import warnings
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from PIL import Image, ImageOps, UnidentifiedImageError

from .runtime import DataDirectoryLease

MAX_UPLOAD = 12 * 1024 * 1024
MAX_PIXELS = 16_000_000
CLASSES = {1: "bolt", 2: "nut"}
UNSUPPORTED = ["washer", "bracket"]
PREFIX = "/api/detector-lab"
MODEL_LABEL = "Faster R-CNN · MobileNetV3 · bolt/nut · CPU"
NOTE = (
    "실험용 볼트·너트 탐지이며 출고 판단이 아닙니다 / 实验性螺栓、螺母检测，不作出库判断。"
    "와셔·브래킷은 미지원입니다 / 垫圈、角码为未知，不是零。"
)


def _now():
    return datetime.now(UTC).isoformat()


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path, payload):
    content = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _normalize_photo(raw):
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "사진은 12MB 이하여야 합니다 / 照片须小于12MB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in {"JPEG", "PNG", "WEBP"} or getattr(image, "n_frames", 1) != 1:
                    raise ValueError("Unsupported image")
                if min(image.size) < 32 or max(image.size) > 8192 or image.width * image.height > MAX_PIXELS:
                    raise ValueError("Unsupported dimensions")
                image.load()
                oriented = ImageOps.exif_transpose(image).convert("RGB")
                oriented.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
                # A fresh image prevents PNG from retaining inherited EXIF/text.
                clean = Image.new("RGB", oriented.size)
                clean.paste(oriented)
                content = io.BytesIO()
                clean.save(content, format="PNG")
                return content.getvalue(), clean.size
    except (UnidentifiedImageError, OSError, ValueError,
            Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise HTTPException(
            422, "단일 JPEG/PNG/WebP 사진을 사용하세요 / 请使用单帧JPEG、PNG或WebP照片，"
            "边长32至8192像素且不超过1600万像素",
        ) from exc


def _finite(value, *, low=0, high=None):
    try:
        valid = type(value) in (int, float) and math.isfinite(value) and value >= low
    except OverflowError:
        valid = False
    if not valid or (high is not None and value > high):
        raise ValueError("Invalid finite numeric output")
    return value


def _validated_result(raw, job):
    """Validate model evidence and recompute counts; never trust supplied decisions."""
    if not isinstance(raw, dict):
        raise TypeError("Predictor output must be an object")
    image = job["image"]
    if (raw.get("checkpoint_sha256") != job["model"]["checkpoint_sha256"]
            or raw.get("source_sha256") != image["sha256"]
            or raw.get("image_size") != [image["width"], image["height"]]
            or raw.get("device") != "cpu"):
        raise ValueError("Predictor identity or image mismatch")
    threshold = _finite(raw.get("threshold"), high=1)
    expected = job["model"].get("threshold")
    if expected is not None and threshold != expected:
        raise ValueError("Frozen threshold mismatch")
    seconds = _finite(raw.get("inference_seconds"))
    predictions = raw.get("predictions")
    if not isinstance(predictions, list) or len(predictions) > 100:
        raise ValueError("Invalid prediction list")
    counts = {"bolt": 0, "nut": 0, "washer": None, "bracket": None}
    validated = []
    for prediction in predictions:
        if not isinstance(prediction, dict):
            raise TypeError("Prediction must be an object")
        label, box = prediction.get("label"), prediction.get("bbox_xyxy")
        if type(label) is not int or label not in CLASSES:
            raise ValueError("Unsupported predicted label")
        score = _finite(prediction.get("score"), high=1)
        if not isinstance(box, list) or len(box) != 4:
            raise ValueError("Invalid predicted box")
        for coordinate in box:
            _finite(coordinate)
        if not 0 <= box[0] < box[2] <= image["width"] or not 0 <= box[1] < box[3] <= image["height"]:
            raise ValueError("Predicted box outside normalized image")
        retained = score >= threshold
        counts[CLASSES[label]] += int(retained)
        validated.append({"label": label, "class_name": CLASSES[label], "bbox_xyxy": box,
                          "score": score, "retained_at_frozen_threshold": retained})
    return {
        "predictions": validated, "counts": counts, "threshold": threshold,
        "threshold_comparison": "score >= threshold", "unsupported_classes": UNSUPPORTED[:],
        "decision": None, "device": "cpu", "inference_seconds": seconds,
        "latency_scope": "model inference only; excludes process/model startup and image preparation",
        "coordinate_frame": "absolute pixel xyxy in normalized RGB PNG; x right, y down",
        "note": NOTE,
    }


class _CpuPredictor:
    def __init__(self):
        self.worker = Path(__file__).with_name("detector_worker.py")

    def __call__(self, checkpoint_path, image_path):
        output = image_path.parent / "worker-result.json"
        environment = dict(os.environ)
        environment["CUDA_VISIBLE_DEVICES"] = ""
        package_parent = str(Path(__file__).resolve().parents[1])
        environment["PYTHONPATH"] = os.pathsep.join(
            [package_parent, *([environment["PYTHONPATH"]] if environment.get("PYTHONPATH") else [])]
        )
        completed = subprocess.run(
            [sys.executable, "-m", "kitguard.detector_worker", "--checkpoint", str(checkpoint_path),
             "--image", str(image_path), "--output", str(output)],
            env=environment, timeout=90, capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError("CPU predictor failed")
        if not output.is_file() or output.stat().st_size > 1_000_000:
            raise ValueError("CPU predictor output missing or oversized")
        return json.loads(output.read_text())


class _DetectorLab:
    def __init__(self, storage_dir, checkpoint_path, predictor):
        self.directory = Path(storage_dir).expanduser().resolve()
        self.checkpoint = Path(checkpoint_path).expanduser().resolve() if checkpoint_path else None
        if predictor is not None and self.checkpoint is None:
            raise ValueError("An injected predictor requires a fixed checkpoint path")
        self.predictor = predictor if predictor is not None else _CpuPredictor()
        self.injected = predictor is not None
        self.identity = {"model_label": MODEL_LABEL, "device": "cpu", "checkpoint_sha256": None,
                         "checkpoint_epoch": None, "threshold": None,
                         "backend": "injected_predictor" if self.injected else "cpu_subprocess"}
        if self.checkpoint and self.checkpoint.is_file():
            try:
                self.identity["checkpoint_sha256"] = _sha(self.checkpoint)
            except OSError:
                # A broken optional checkpoint must not stop the production app.
                pass
            summary = self.checkpoint.parent / "training_summary.json"
            if summary.is_file():
                try:
                    metadata = json.loads(summary.read_text())
                    if metadata.get("best_checkpoint_sha256") == self.identity["checkpoint_sha256"]:
                        epoch = metadata.get("best_epoch")
                        self.identity["checkpoint_epoch"] = epoch if type(epoch) is int and epoch > 0 else None
                        self.identity["threshold"] = _finite(metadata["threshold"], high=1)
                except (OSError, ValueError, TypeError, KeyError):
                    self.identity["threshold"] = None
        self.lock = threading.RLock()
        self.active = None
        self.closing = True
        self.executor = None
        self.lease = None
        self.startup_error = None

    def start(self):
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            self.lease = DataDirectoryLease(self.directory).acquire()
            for path in self.directory.glob("*/job.json"):
                if (not re.fullmatch(r"[a-f0-9]{32}", path.parent.name) or path.is_symlink()
                        or path.parent.is_symlink()
                        or not path.resolve().is_relative_to(self.directory)):
                    continue
                try:
                    job = json.loads(path.read_text())
                except (OSError, ValueError):
                    # Preserve malformed historical files without disabling the app.
                    continue
                if not isinstance(job, dict):
                    continue
                if job.get("status") in {"queued", "running"}:
                    job.update(status="interrupted", finished_at=_now(), error={
                        "code": "interrupted", "message": "작업이 중단되었습니다 / 上次任务中断，请手动重试"})
                    _atomic_json(path, job)
            self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kitguard-detector-lab")
            self.closing = False
        except (OSError, ValueError, RuntimeError):
            if self.lease:
                self.lease.close()
                self.lease = None
            self.startup_error = "实验存储不可用 / 실험 저장소를 사용할 수 없습니다"

    def close(self):
        with self.lock:
            self.closing = True
            if self.executor:
                self.executor.shutdown(wait=False)
            if self.active is None and self.lease:
                self.lease.close()

    def status(self):
        with self.lock:
            available = bool(self.checkpoint and self.identity["checkpoint_sha256"]
                             and self.checkpoint.is_file()
                             and not self.startup_error
                             and (self.injected or self.predictor.worker.is_file()))
            return {"enabled": self.checkpoint is not None, "available": available,
                    "busy": self.active is not None, "accepting": available and not self.closing,
                    "active_job_id": self.active, "queue_capacity": 0,
                    "max_upload_bytes": MAX_UPLOAD, **copy.deepcopy(self.identity),
                    "error": self.startup_error,
                    "unsupported_classes": UNSUPPORTED[:], "decision": None, "note": NOTE}

    def _path(self, job_id, filename):
        if not re.fullmatch(r"[a-f0-9]{32}", job_id):
            raise HTTPException(404, "작업이 없습니다 / 未找到任务")
        path = self.directory / job_id / filename
        if path.is_symlink() or path.parent.is_symlink() or not path.resolve().is_relative_to(self.directory):
            raise HTTPException(404, "작업이 없습니다 / 未找到任务")
        return path

    def get(self, job_id):
        path = self._path(job_id, "job.json")
        try:
            return json.loads(path.read_text())
        except FileNotFoundError as exc:
            raise HTTPException(404, "작업이 없습니다 / 未找到任务") from exc
        except (ValueError, OSError) as exc:
            raise HTTPException(409, "기록을 읽을 수 없습니다 / 记录无法读取") from exc

    def image(self, job_id):
        job = self.get(job_id)
        try:
            raw = self._path(job_id, "image.png").read_bytes()
        except OSError as exc:
            raise HTTPException(409, "사진을 읽을 수 없습니다 / 图片无法读取") from exc
        if hashlib.sha256(raw).hexdigest() != job["image"]["sha256"]:
            raise HTTPException(409, "사진이 변경되었습니다 / 图片内容已变更")
        return raw

    def _release(self):
        with self.lock:
            self.active = None
            if self.closing and self.lease:
                self.lease.close()

    def create(self, raw):
        with self.lock:
            status = self.status()
            if not status["accepting"]:
                raise HTTPException(503, "탐지 실험을 사용할 수 없습니다 / 检测实验尚未启用或环境不可用")
            if self.active is not None:
                raise HTTPException(503, "이전 작업이 진행 중입니다 / 前一个检测任务仍在运行")
            job_id = uuid.uuid4().hex
            self.active = job_id
        try:
            content, (width, height) = _normalize_photo(raw)
            job_dir = self.directory / job_id
            job_dir.mkdir()
            (job_dir / "image.png").write_bytes(content)
            job = {
                "id": job_id, "status": "queued", "created_at": _now(), "started_at": None,
                "finished_at": None, "error": None, "result": None, "model": copy.deepcopy(self.identity),
                "image": {"url": f"{PREFIX}/jobs/{job_id}/image", "width": width, "height": height,
                          "source_sha256": hashlib.sha256(raw).hexdigest(),
                          "sha256": hashlib.sha256(content).hexdigest(), "format": "PNG", "mode": "RGB",
                          "normalization": "EXIF-oriented RGB; max side 2048px; metadata stripped"},
                "decision": None, "note": NOTE,
            }
            _atomic_json(job_dir / "job.json", job)
            with self.lock:
                if self.closing:
                    raise RuntimeError("Lab is shutting down")
                self.executor.submit(self._run, copy.deepcopy(job))
            return job
        except BaseException:
            self._release()
            raise

    def _run(self, job):
        path = self._path(job["id"], "job.json")
        started = time.perf_counter()
        try:
            job.update(status="running", started_at=_now())
            _atomic_json(path, job)
            image_path = self._path(job["id"], "image.png")
            if (_sha(self.checkpoint) != job["model"]["checkpoint_sha256"]
                    or _sha(image_path) != job["image"]["sha256"]):
                raise ValueError("Frozen input changed")
            raw = self.predictor(self.checkpoint, image_path)
            if (_sha(self.checkpoint) != job["model"]["checkpoint_sha256"]
                    or _sha(image_path) != job["image"]["sha256"]):
                raise ValueError("Frozen input changed during prediction")
            result = _validated_result(raw, job)
            _atomic_json(path.parent / "model-result.json", raw)
            job.update(status="completed", result=result)
        except Exception as exc:  # noqa: BLE001 - isolate arbitrary predictor failures from the app
            code = "timeout" if isinstance(exc, subprocess.TimeoutExpired) else "inference_failed"
            job.update(status="failed", result=None, error={
                "code": code, "exception_type": type(exc).__name__,
                "message": "탐지에 실패했습니다. 다시 시도하세요 / 检测失败，请检查实验环境后手动重试",
            })
        finally:
            job.update(finished_at=_now(), elapsed_seconds=time.perf_counter() - started)
            try:
                _atomic_json(path, job)
            finally:
                self._release()


def create_detector_lab_router(storage_dir, checkpoint_path=None, predictor=None):
    """Return a self-managed router; None checkpoint keeps the lab disabled.

    A test predictor is callable(checkpoint_path, normalized_image_path) and
    returns the existing single-photo prediction JSON contract. Injection is
    visibly recorded as an injected backend, never as real model validation.
    """
    lab = _DetectorLab(storage_dir, checkpoint_path, predictor)

    @asynccontextmanager
    async def lifespan(_app):
        lab.start()
        try:
            yield
        finally:
            lab.close()

    router = APIRouter(prefix=PREFIX, lifespan=lifespan)

    @router.get("/status")
    async def status():
        return lab.status()

    @router.post("/jobs", status_code=202)
    async def create_job(request: Request, photo: Annotated[UploadFile, File()]):
        try:
            form = await request.form()
            if set(form.keys()) != {"photo"} or len(form.getlist("photo")) != 1:
                raise HTTPException(422, "사진 한 장만 제출하세요 / 仅接收一张照片，不接收模型或阈值参数")
            raw = await photo.read(MAX_UPLOAD + 1)
        finally:
            await photo.close()
        return {"job": await asyncio.to_thread(lab.create, raw)}

    @router.get("/jobs/{job_id}")
    async def get_job(job_id: str):
        return {"job": await asyncio.to_thread(lab.get, job_id)}

    @router.get("/jobs/{job_id}/download")
    async def download_job(job_id: str):
        job = await asyncio.to_thread(lab.get, job_id)
        content = json.dumps(job, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        return Response(content, media_type="application/json", headers={
            "Content-Disposition": f'attachment; filename="kitguard-detection-{job_id}.json"',
            "Cache-Control": "no-store",
        })

    @router.get("/jobs/{job_id}/image")
    async def get_image(job_id: str):
        raw = await asyncio.to_thread(lab.image, job_id)
        return Response(raw, media_type="image/png", headers={"Cache-Control": "no-store",
                                                               "X-Content-Type-Options": "nosniff"})

    return router
