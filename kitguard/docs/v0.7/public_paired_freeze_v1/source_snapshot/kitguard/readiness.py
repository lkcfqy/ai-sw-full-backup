"""Read-only operational checks: no backend import, model load or inference."""

from __future__ import annotations

import ast
import asyncio
import importlib.metadata
import importlib.util
import inspect
import json
import os
import platform
import sqlite3
import sys
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import Response

from . import __version__

MODES = ("main", "detector", "all")
DEFAULT_EXPECTED_IDENTITY = {
    "repo_id": "mlx-community/Qwen3.6-27B-4bit",
    "revision": "c000ac2c2057d94be3fa931000c31723aac53282",
    "observation_mode": "spatial_guarded", "image_max_side": 1536,
    "observer_protocol_sha256": "0f6d5a514d4e7b093e486ae585040e9506670a4a7e725f7471333ec103e75403",
}
IDENTITY_SOURCE = "test-results/browser/inspection-region-real-v05/public-replay.json runtime_identity"
V1_CHECKPOINT_SHA256 = "2022c203a3b3b36dd146534c8bcfc538739cf8bf643066fc14a5b9611ebeb62c"
REQUIRED_ASSETS = (
    "index.html", "app.js", "styles.css", "audit.js", "spatial.js", "camera.js", "favicon.svg",
    "demo.html", "demo.js", "demo.css", "study.html", "study.js", "study.css", "region.js", "region.css",
    "detector.html", "detector.js", "detector.css", "readiness.html", "readiness.js", "readiness.css",
    "workflow.js", "workflow.css", "trials.html", "trials.js", "trials.css",
    "public-review.js", "public-review.css",
)
LIMITATIONS = {
    "ko": "파일·설정·의존성 존재와 서버 상태를 확인합니다. 모델 로드·추론은 하지 않습니다. "
          "전체 가중치 해시, 실제 쓰기 성공, 카메라 권한, 정확도, 현장 성능은 확인하지 않습니다.",
    "zh": "检查文件、配置、依赖是否存在及服务状态；不加载模型、不推理。"
          "未验证全量权重散列、实际写入成功、相机权限、准确率或现场效果。",
}


def bilingual(ko, zh):
    return {"ko": ko, "zh": zh}


def installed_version(package):
    """Read the current package file, so a stale server cannot approve its own old version."""
    try:
        tree = ast.parse((Path(package) / "__init__.py").read_text(encoding="utf-8"))
        for node in tree.body:
            if (isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets)
                    and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
                return node.value.value
    except (OSError, SyntaxError, UnicodeError):
        pass
    return None


def dependency_inventory(names):
    """Check installation presence without importing torch/MLX or initializing a device."""
    records = {}
    distributions = {"PIL": "pillow", "mlx_vlm": "mlx-vlm", "multipart": "python-multipart"}
    for name in names:
        try:
            present = importlib.util.find_spec(name) is not None
        except (ImportError, ValueError, AttributeError):
            present = False
        try:
            version = importlib.metadata.version(distributions.get(name, name)) if present else None
        except importlib.metadata.PackageNotFoundError:
            version = None
        records[name] = {"present": present, "version": version, "import_verified": False}
    return records


def directory_permissions(directory):
    """Access bits only; never create a probe file or claim a successful write."""
    directory = Path(directory).expanduser().resolve()
    ancestor = directory
    while not ancestor.exists() and ancestor != ancestor.parent:
        ancestor = ancestor.parent
    return {"path": str(directory), "exists": directory.exists(), "checked_directory": str(ancestor),
            "permission_allows_write": ancestor.is_dir() and os.access(ancestor, os.W_OK | os.X_OK),
            "write_probe_performed": False}


def database_integrity(path):
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        return {"exists": False, "ok": None, "detail": "database_missing"}
    connection = None
    try:
        connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)
        deadline = time.monotonic() + 3
        connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        connection.execute("PRAGMA query_only=ON")
        passed = connection.execute("PRAGMA quick_check").fetchall() == [("ok",)]
        return {"exists": True, "ok": passed, "detail": "ok" if passed else "quick_check_failed"}
    except sqlite3.Error as exc:
        return {"exists": True, "ok": False, "detail": type(exc).__name__}
    finally:
        if connection is not None:
            connection.close()


def build_readiness_report(*, package, data_dir, health=None, detector=None, mode="main",
                           database_path=None, expected_identity=None, dependencies=None,
                           expected_version=None, server_error=None):
    if mode not in MODES:
        raise ValueError("mode must be main, detector or all")
    package, data_dir = Path(package), Path(data_dir)
    expected_version = expected_version or installed_version(package)
    health = health if isinstance(health, Mapping) else {}
    detector = detector if isinstance(detector, Mapping) else {}
    identity = dict(DEFAULT_EXPECTED_IDENTITY if expected_identity is None else expected_identity)
    checks = []

    def add(name, scope, passed, label, message, action=None, *, required=True, detail=None):
        state = "pass" if passed is True else "fail" if required else "info" if passed is None else "warn"
        checks.append({"check": name, "scope": scope, "passed": passed, "state": state,
                       "required": required, "label": label, "message": message,
                       "action": action, "detail": detail})

    restart = bilingual("이 프로젝트의 서버를 다시 시작하고 포트를 확인하세요.",
                        "请重启本项目的服务，并检查端口。")
    add("python", "common", (3, 11) <= sys.version_info[:2] < (3, 14),
        bilingual("Python 버전", "Python 版本"), bilingual(platform.python_version(), platform.python_version()),
        bilingual("Python 3.11–3.13 환경을 사용하세요.", "请使用 Python 3.11–3.13 环境。"))
    add("running_application_version", "common", bool(expected_version)
        and health.get("version") == expected_version,
        bilingual("실행 중인 앱 버전", "正在运行的应用版本"),
        bilingual(f"실행 {health.get('version') or '미확인'} / 기대 {expected_version}",
                  f"实际 {health.get('version') or '未确认'} / 预期 {expected_version}"), restart,
        detail={"running": health.get("version"), "expected": expected_version, "error": server_error})
    missing = [name for name in REQUIRED_ASSETS if not (package / "static" / name).is_file()]
    add("static_assets", "common", not missing, bilingual("화면 파일", "页面资源"),
        bilingual("필수 화면 파일 존재 여부입니다.", "检查全部所需页面资源是否存在。"),
        bilingual("현재 버전의 전체 패키지를 다시 설치하세요.", "请重新安装当前版本的完整程序包。"),
        detail={"checked": list(REQUIRED_ASSETS), "missing": missing})
    permission = directory_permissions(data_dir)
    add("data_directory_permissions", "common", permission["permission_allows_write"],
        bilingual("저장 폴더 권한", "数据目录权限"),
        bilingual("권한만 확인합니다. 시험 파일을 쓰지 않습니다.", "仅检查权限，不写入测试文件。"),
        bilingual("KITGUARD_DATA_DIR을 쓰기 가능한 폴더로 지정하세요.",
                  "请将 KITGUARD_DATA_DIR 指向有写入权限的目录。"), detail=permission)
    names = ["fastapi", "uvicorn", "PIL", "pydantic", "multipart"]
    if mode in {"main", "all"}:
        names += ["mlx", "mlx_vlm"]
    if mode in {"detector", "all"}:
        names += ["torch", "torchvision"]
    inventory = dependency_inventory(names) if dependencies is None else dependencies
    for scope, selected in (("common", names[:5]), ("main", ["mlx", "mlx_vlm"]),
                            ("detector", ["torch", "torchvision"])):
        if scope != "common" and mode not in {scope, "all"}:
            continue
        details = {name: inventory.get(name, {"present": False, "version": None}) for name in selected}
        add(f"{scope}_dependencies", scope, all(item.get("present") is True for item in details.values()),
            bilingual("의존성 파일", "依赖文件"),
            bilingual("설치 여부 확인입니다. 실제 import·모델 로드는 수행하지 않습니다.",
                      "仅确认安装文件存在，未实际导入后端或加载模型。"),
            bilingual("이 실행 환경에 필요한 의존성을 설치하세요.", "请在运行服务的环境中安装所需依赖。"),
            detail=details)

    if mode in {"main", "all"}:
        model = health.get("model") if isinstance(health.get("model"), Mapping) else {}
        gate = health.get("inference") if isinstance(health.get("inference"), Mapping) else {}
        add("main_model_files", "main", model.get("available") is True,
            bilingual("주 모델 파일", "主模型文件"),
            bilingual("모델 상태가 보고한 파일 존재·크기입니다. 전체 해시 검증은 아닙니다.",
                      "依据模型状态检查文件存在和大小，未核验全量权重散列。"),
            bilingual("고정 모델 파일과 KITGUARD_MODEL_PATH를 확인하세요.",
                      "请检查冻结模型文件及 KITGUARD_MODEL_PATH。"),
            detail={key: model.get(key) for key in ("available", "path", "error")})
        for key in ("repo_id", "revision", "observation_mode", "image_max_side", "observer_protocol_sha256"):
            expected = identity.get(key)
            add(f"main_{key}", "main", model.get(key) == expected if expected is not None else None,
                bilingual(f"고정 설정 · {key}", f"冻结配置 · {key}"),
                bilingual("실행 중인 상태를 고정된 기대값과 비교합니다.", "比较运行状态与冻结期望值。"),
                bilingual("scripts/run.sh로 실행하고 변경한 프로토콜은 별도로 검증하세요.",
                          "请用 scripts/run.sh 启动；协议变更须单独验证。"), required=expected is not None,
                detail={"expected": expected, "actual": model.get(key)})
        loaded = model.get("loaded") is True
        add("main_model_loaded", "main", loaded, bilingual("주 모델 메모리 로드", "主模型内存加载"),
            bilingual("이미 로드되었습니다." if loaded else "미로드 상태입니다. 첫 추론에 추가 시간이 듭니다.",
                      "模型已加载。" if loaded else "模型尚未加载，首次推理还需加载时间。"), required=False)
        add("main_runtime_error", "main", not model.get("error"),
            bilingual("주 모델 오류 상태", "主模型错误状态"),
            bilingual("상태에 오류가 기록돼 있는지 확인합니다.", "检查模型状态是否报告错误。"), restart,
            detail={"error_reported": bool(model.get("error"))})
        add("main_inference_idle", "main", gate.get("busy") is False,
            bilingual("주 모델 사용 상태", "主模型占用状态"),
            bilingual("현재 추론 점유 상태를 확인합니다.", "检查当前推理占用状态。"),
            bilingual("진행 중인 작업이 끝난 뒤 다시 확인하세요.", "请等待当前任务结束后重新检查。"),
            detail=dict(gate))
        database = database_integrity(database_path or data_dir / "kitguard.sqlite3")
        add("local_database_integrity", "main", database["ok"] is True,
            bilingual("주문 데이터베이스", "工单数据库"),
            bilingual("읽기 전용 SQLite quick_check 결과입니다.", "SQLite 只读 quick_check 结果。"),
            bilingual("서버·데이터 폴더를 확인하세요. 오류 시 원본을 보존하고 백업을 점검하세요.",
                      "请检查服务和数据目录；若损坏，保留原件并检查备份。"), detail=database)

    if mode in {"detector", "all"}:
        launch = bilingual("bash scripts/run_detector_lab.sh를 실행하고 8767 포트를 확인하세요.",
                           "请运行 bash scripts/run_detector_lab.sh，并检查 8767 端口。")
        add("detector_enabled", "detector", detector.get("enabled") is True,
            bilingual("검출 실험 설정", "检测实验配置"),
            bilingual("주 작업대와 별도의 선택 기능입니다.", "这是独立于主工作台的可选功能。"), launch)
        add("detector_files", "detector", detector.get("available") is True,
            bilingual("검출 파일·저장소", "检测文件与存储"),
            bilingual("서비스가 보고한 파일·저장소 상태입니다. 모델 로드 검증은 아닙니다.",
                      "依据服务报告检查文件和存储状态，未验证模型可加载。"), launch,
            detail={"available": detector.get("available"), "error": detector.get("error")})
        add("detector_frozen_model", "detector",
            detector.get("checkpoint_sha256") == V1_CHECKPOINT_SHA256 and detector.get("threshold") == 0.5,
            bilingual("기본 v1 모델", "默认 v1 模型"),
            bilingual("고정 v1 체크포인트와 기준 0.5를 확인합니다.", "检查冻结 v1 checkpoint 和阈值 0.5。"),
            bilingual("v1 best.pt와 같은 폴더의 training_summary.json을 사용하세요.",
                      "请使用 v1 best.pt 及同目录 training_summary.json。"),
            detail={"expected_sha256": V1_CHECKPOINT_SHA256,
                    "reported_sha256": detector.get("checkpoint_sha256"), "threshold": detector.get("threshold")})
        add("detector_backend", "detector", detector.get("backend") == "cpu_subprocess",
            bilingual("검출 실행 방식", "检测运行方式"),
            bilingual("실제 CPU subprocess 구성인지 확인합니다.", "检查是否配置真实 CPU 子进程后端。"), launch)
        add("detector_inference_idle", "detector",
            detector.get("busy") is False and detector.get("accepting") is True,
            bilingual("검출 작업 접수", "检测任务接收"),
            bilingual("점유와 작업 접수 상태를 확인합니다.", "检查占用与接收任务状态。"),
            bilingual("작업 종료 후 다시 확인하거나 저장소 오류를 해결하세요.", "等待任务结束后重查，或修复存储错误。"),
            detail={"busy": detector.get("busy"), "accepting": detector.get("accepting")})
        add("detector_model_loaded", "detector", None, bilingual("검출 모델 로드", "检测模型加载"),
            bilingual("가중치를 로드하지 않습니다. 실제 추론 성공은 별도 확인이 필요합니다.",
                      "本检查不加载权重，实际推理成功仍需单独验证。"), required=False)

    scopes = {}
    for scope in ("main", "detector"):
        selected = mode in {scope, "all"}
        required = [c for c in checks if c["scope"] in {"common", scope} and c["required"]]
        scopes[scope] = {"checked": selected,
                         "ready": all(c["passed"] is True for c in required) if selected else None}
    return {"schema": "kitguard.readiness.v1", "checked_at": datetime.now(UTC).isoformat(),
            "version": health.get("version"), "expected_version": expected_version, "mode": mode,
            "ready": all(c["passed"] is True for c in checks if c["required"]), "scopes": scopes,
            "checks": checks, "expected_main_identity": identity,
            "identity_source": IDENTITY_SOURCE if expected_identity is None else "caller_supplied_expectation",
            "verification_level": "read_only_preflight_without_model_load_or_inference",
            "limitations": LIMITATIONS, "scope": LIMITATIONS["zh"]}


async def _snapshot(provider):
    if provider is None:
        return {}
    try:
        if isinstance(provider, Mapping):
            return dict(provider)
        value = await provider() if inspect.iscoroutinefunction(provider) else await asyncio.to_thread(provider)
        if inspect.isawaitable(value):
            value = await value
        return value if isinstance(value, Mapping) else {"error": "InvalidStatus"}
    except Exception as exc:  # noqa: BLE001 - optional backend failure must still yield a report
        return {"error": type(exc).__name__}


def create_readiness_router(*, store, engine, inference_gate, package, detector_status=None,
                            expected_identity=None):
    """GET /api/readiness. Providers expose status only, never model execution."""
    router = APIRouter(prefix="/api/readiness")

    @router.get("")
    async def readiness(mode: Literal["main", "detector", "all"] = "main", download: bool = False):
        model = await _snapshot(engine.status) if mode in {"main", "all"} else {}
        gate = await _snapshot(inference_gate.status) if mode in {"main", "all"} else {}
        detector = await _snapshot(detector_status) if mode in {"detector", "all"} else {}
        report = await asyncio.to_thread(
            build_readiness_report, package=package, data_dir=store.directory,
            database_path=store.path, health={"version": __version__, "model": model, "inference": gate},
            detector=detector, mode=mode, expected_identity=expected_identity,
        )
        if download:
            stamp = datetime.fromisoformat(report["checked_at"]).strftime("%Y%m%dT%H%M%S%fZ")
            content = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
            return Response(content, media_type="application/json", headers={
                "Content-Disposition": f'attachment; filename="kitguard-readiness-{mode}-{stamp}.json"',
                "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
            })
        return report

    return router
