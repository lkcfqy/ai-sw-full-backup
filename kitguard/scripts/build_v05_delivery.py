"""Build a fresh, portable v0.5 scope/provenance delivery, with explicit pending gates.

Preview is the default. --final requires actual final tests, a verified source ZIP,
bound real MLX receipts and both independently checked engineering exports.
This builder never invokes a model or writes to a prior delivery directory.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import importlib.util
import json
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote
from zipfile import ZipFile

_SPEC = importlib.util.spec_from_file_location("delivery_v04_utils", Path(__file__).with_name("build_v04_delivery.py"))
_UTILS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_UTILS)
junit, read_json, sha, validated_file = _UTILS.junit, _UTILS.read_json, _UTILS.sha, _UTILS.validated_file

ROOT = Path(__file__).resolve().parents[1]
REAL = "test-results/browser/inspection-region-real-v05"
UI = "test-results/browser/inspection-region-v05"
DEFAULTS = {
    "final_evaluation": ("최종 자체 평가 / 最终自检评估", "docs/v0.5/FINAL_EVALUATION.md"),
    "demo_runbook": ("시연 순서 / 演示流程", "docs/v0.5/DEMO_RUNBOOK_KO_ZH.md"),
    "real_integration_result": ("실제 연결 결과와 한계 / 真实连接结果与边界", "docs/v0.5/REAL_MODEL_INTEGRATION_RESULT.md"),
    "wheel": ("설치 wheel / 安装 wheel", "output/wheels-v0.5-final/kitguard-0.5.0-py3-none-any.whl"),
    "region_design": ("검사 범위와 한계 / 检查范围设计与边界", "docs/v0.5/INSPECTION_REGION_DESIGN.md"),
    "backend_implementation": ("범위·원본 추적 구현 / 范围与原图追溯实现", "docs/v0.5/REGION_BACKEND_IMPLEMENTATION.md"),
    "independent_review": ("독립 반례 검토 / 独立对抗审查", "docs/v0.5/INSPECTION_REGION_INDEPENDENT_REVIEW.md"),
    "independent_region_tests": ("독립 영역 테스트 / 独立区域测试", "test-results/inspection-region-independent-review.xml"),
    "backend_tests": ("백엔드 단계 회귀 / 后台阶段回归", "test-results/v05-backend-final.xml"),
    "ui_qa": ("키보드·터치·모바일 검사 / 键盘、触控与手机验收", "docs/v0.5/INSPECTION_REGION_UI_QA.md"),
    "ui_api": ("Chrome 실제 API 공학 검사 / Chrome 实际 API 工程验收", f"{UI}/result.json"),
    "ui_visual": ("최종 화면 읽기 검사 / 最终界面只读检查", f"{UI}/visual-final-result.json"),
    "ui_scroll": ("휴대폰 선언 스크롤 / 手机确认声明滚动检查", f"{UI}/footer-visual-result.json"),
    "ui_freeze": ("화면 소스 동결 / 界面源码冻结", f"{UI}/SOURCE_FREEZE.json"),
    "ui_shutdown": ("공학 서버 종료 / 工程服务停止", f"{UI}/shutdown.json"),
    "method_preservation": ("기존 관찰 방법 SHA / 既有观察方法 SHA 保持", "test-results/v05-method-preservation.json"),
    "engineering_api_export": ("세 범위 공학 API 기록 / 三种范围工程 API 记录", "test-results/v05-api-scope-fixture/engineering-study-export.json"),
    "engineering_api_verification": ("공학 API 독립 재계산 / 工程 API 独立复算", "test-results/audit/v05-api-scope-independent-verification.json"),
    "engineering_api_zip": ("세 범위 공학 증거 ZIP / 三种范围工程证据包", "test-results/v05-api-scope-fixture/engineering-study-evidence.zip"),
    "engineering_ui_export": ("브라우저 공학 연구 기록 / 浏览器工程研究记录", f"{UI}/engineering-study-export.json"),
    "engineering_ui_verification": ("브라우저 기록 독립 재계산 / 浏览器记录独立复算", "test-results/audit/v05-engineering-study-independent-verification-v2.json"),
    "real_plan": ("실제 모델 연결 계획 / 真实模型连接计划", "docs/v0.5/REAL_MODEL_INTEGRATION_PLAN.md"),
    "real_result": ("두 번의 실제 MLX 호출 / 两次真实 MLX 调用记录", f"{REAL}/result.json"),
    "real_verification": ("실제 입력·범위 독립 검증 / 真实输入与范围独立核验", f"{REAL}/verification.json"),
    "real_freeze": ("실제 실행 동결 / 真实运行冻结", f"{REAL}/PLAN_FREEZE.json"),
    "real_source_plan": ("고정 입력 계획 / 固定输入计划", f"{REAL}/SOURCE_PLAN.json"),
    "real_http_index": ("HTTP 호출 기록 / HTTP 调用记录", f"{REAL}/http-index.json"),
    "real_study_verification": ("공개 재생 독립 검증 / 公开回放独立核验", f"{REAL}/study-export-verification.json"),
    "real_mixed_order_zip": ("나사류 원본·영역 공정 기록 / 螺纹件根图与选区工单", f"{REAL}/mixed-screws-full-region/order-evidence.zip"),
    "wheel_verification": ("격리 wheel 실행 / 隔离 wheel 运行核验", "test-results/audit/v05-wheel-final-verification.json"),
    "wheel_documentation": ("wheel 검증 범위 / wheel 验证范围", "docs/v0.5/WHEEL_VERIFICATION.md"),
    "real_shutdown": ("모델 서비스 종료 / 模型服务停止", f"{REAL}/shutdown.json"),
    "real_a41_zip": ("A41 원본·영역 증거 / A41 根图与选区证据", f"{REAL}/ino-A41-author-region/order-evidence.zip"),
    "real_screws_zip": ("나사류 원본·영역 연구 증거 / 螺纹件根图与选区研究证据", f"{REAL}/public-replay-evidence.zip"),
    "real_study_export": ("공개 재생 JSON / 公开回放完整记录", f"{REAL}/public-replay.json"),
    "final_tests": ("최종 전체 CPU 테스트 / 最终全套 CPU 测试", "test-results/engineering-v05-final.xml"),
    "extracted_tests": ("압축 해제 소스 실제 테스트 / 解压源码实际测试", "test-results/audit/source_v05_verification.pytest.xml"),
    "source_archive": ("v0.5 소스 ZIP / v0.5 源码包", "output/KitGuard_source_v0.5.zip"),
    "source_verification": ("소스 ZIP 해제·해시 검증 / 源码 ZIP 解压与哈希验证", "test-results/audit/source_v05_verification.json"),
    "source_disclosure": ("AI·사진 출처 공개 / AI 与照片来源披露", "docs/AI_AND_SOURCE_DISCLOSURE.md"),
}
REQUIRED = {
    "final_evaluation", "final_tests", "extracted_tests", "source_archive", "source_verification",
    "real_result", "real_verification", "real_freeze", "real_a41_zip", "real_screws_zip", "real_study_export",
    "real_source_plan", "real_http_index", "real_study_verification", "real_mixed_order_zip",
    "method_preservation", "ui_api", "ui_visual", "ui_scroll", "ui_freeze",
    "engineering_api_export", "engineering_api_verification", "engineering_ui_export", "engineering_ui_verification",
}


def validated_artifact(path, root):
    if Path(path).suffix.lower() != ".whl":
        return validated_file(path, root)
    candidate = Path(path) if Path(path).is_absolute() else root / path
    if candidate.is_symlink() or not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError("Wheel must be a regular project-local artifact")
    with ZipFile(candidate) as archive:
        if archive.testzip() is not None or len(archive.namelist()) != len(set(archive.namelist())):
            raise ValueError("Invalid wheel CRC or duplicate member")
        for name in archive.namelist():
            member = PurePosixPath(name)
            if member.is_absolute() or ".." in member.parts or "\\" in name or member.suffix in {".db", ".sqlite3", ".gguf", ".safetensors"}:
                raise ValueError("Unsafe wheel member")
    return candidate.resolve()


def collect(root, overrides):
    if set(overrides) - set(DEFAULTS):
        raise ValueError("Unknown delivery artifact role")
    artifacts, missing = [], []
    for role, (title, default) in DEFAULTS.items():
        value = overrides.get(role) or default
        candidate = Path(value) if Path(value).is_absolute() else root / value
        if not candidate.exists():
            if role in overrides:
                raise ValueError(f"Explicit artifact does not exist: {value}")
            missing.append(role)
            continue
        source = validated_artifact(value, root)
        artifacts.append({"role": role, "title": title, "source": source.relative_to(root).as_posix(),
                          "destination": f"artifacts/{role}/{source.name}", "bytes": source.stat().st_size,
                          "sha256": sha(source)})
    return artifacts, missing


def strict_junit(path):
    counts = junit(path)
    cases = ET.parse(path).getroot().findall(".//testcase")
    if len(cases) != counts["tests"]:
        raise ValueError("JUnit declared count differs from actual testcase records")
    for name, tag in (("failures", "failure"), ("errors", "error"), ("skipped", "skipped")):
        if sum(case.find(tag) is not None for case in cases) != counts[name]:
            raise ValueError("JUnit declared outcomes differ from testcase records")
    return counts


def source_members(path):
    with ZipFile(path) as archive:
        manifest = json.loads(archive.read("KitGuard/SOURCE_MANIFEST.json"))
        records = manifest["files"]
        members = {record["path"]: record for record in records}
        if len(members) != len(records):
            raise ValueError("Source manifest contains duplicate paths")
        if set(archive.namelist()) != {"KitGuard/SOURCE_MANIFEST.json", *("KitGuard/" + name for name in members)}:
            raise ValueError("Source ZIP member set differs from its own manifest")
        for name, record in members.items():
            raw = archive.read("KitGuard/" + name)
            if len(raw) != record["bytes"] or hashlib.sha256(raw).hexdigest() != record["sha256"]:
                raise ValueError("Source ZIP member hash mismatch: " + name)
        return {name: record["sha256"] for name, record in members.items()}


def receipt_assertions(path):
    receipt = read_json(path)
    if receipt.get("status") != "passed" or receipt.get("errors"):
        raise ValueError("Browser receipt has not passed: " + str(path))
    count = len(receipt.get("checks", []))
    if count < 1 or receipt.get("assertions", count) != count:
        raise ValueError("Browser assertion count does not match retained checks")
    return count


def verify_engineering(export_path, verification_path):
    result = read_json(verification_path)
    study = read_json(export_path)["study"]
    if (result.get("status") != "verified_internal_consistency" or result.get("errors")
            or result.get("input_sha256") != sha(export_path) or result.get("study_id") != study.get("id")
            or result.get("source_kind") != "engineering_fixture" or study.get("source_kind") != "engineering_fixture"
            or result.get("physical_authenticity_verified") is not False or result.get("photo_bytes_verified") is not False):
        raise ValueError("Engineering verification does not bind the supplied engineering-only export")
    return {"status": result["status"], "planned_cases": result["planned_cases"], "input_sha256": result["input_sha256"],
            "photo_bytes_verified": False, "physical_authenticity_verified": False}


def evidence_zip(path, expected_images):
    with ZipFile(path) as archive:
        if archive.testzip() is not None or len(archive.namelist()) != len(set(archive.namelist())):
            raise ValueError("Invalid or duplicate evidence ZIP members")
        if "SHA256.json" in archive.namelist():
            records = json.loads(archive.read("SHA256.json"))
        else:
            records = json.loads(archive.read("MANIFEST.json"))["files"]
        image_hashes = set()
        for record in records:
            raw = archive.read(record["path"])
            digest = hashlib.sha256(raw).hexdigest()
            if digest != record["sha256"] or len(raw) != record["bytes"]:
                raise ValueError("Evidence ZIP member digest mismatch")
            if record["path"].endswith(".jpg"):
                image_hashes.add(digest)
        if not set(expected_images) <= image_hashes:
            raise ValueError("Evidence ZIP omits expected root/view bytes")


def verify_real(by_role, members=None):
    result, verification = read_json(by_role["real_result"]), read_json(by_role["real_verification"])
    if verification.get("status") != "verified" or verification.get("attempted_inspections") != 2:
        raise ValueError("Real-run verification has not verified two attempts")
    for role, key in {
        "real_result": "result_sha256", "real_freeze": "plan_freeze_sha256",
        "real_source_plan": "source_plan_sha256", "real_http_index": "http_index_sha256",
        "real_study_export": "study_export_sha256", "real_study_verification": "study_verifier_receipt_sha256",
    }.items():
        if verification.get(key) != sha(by_role[role]):
            raise ValueError("Real verification SHA mismatch: " + role)
    plan, freeze = read_json(by_role["real_source_plan"]), read_json(by_role["real_freeze"])
    if (plan.get("planned_inspections") != 2 or plan.get("retry_inference") is not False
            or plan.get("human_participants") != 0 or freeze.get("source_plan_sha256") != sha(by_role["real_source_plan"])):
        raise ValueError("Real plan/freeze does not retain two no-retry non-human inputs")
    if (result.get("status") not in {"completed", "completed_with_errors"}
            or result.get("source_changed") is not False or result.get("human_field_samples") != 0
            or result.get("planned_inspections") != 2 or result.get("attempted_inspections") != 2
            or len(result.get("cases", [])) != 2):
        raise ValueError("Real run must preserve exactly two planned attempts and unchanged source")
    cases = result["cases"]
    if ([case.get("id") for case in cases] != [case["id"] for case in plan["cases"]]
            or len({case.get("id") for case in cases}) != 2):
        raise ValueError("Real cases must retain distinct prespecified IDs in order")
    http = read_json(by_role["real_http_index"])
    inspections = [row for row in http if row.get("method") == "POST" and row.get("endpoint", "").endswith("/inspect")]
    if ([row["endpoint"] for row in inspections] != [f"/api/orders/{case['order_id']}/inspect" for case in cases]):
        raise ValueError("HTTP log does not retain exactly the two planned inspection requests")
    inputs = verification.get("inputs", [])
    if len(inputs) != 2:
        raise ValueError("Real verification must retain both root/view inputs")
    for case, planned, verified in zip(cases, plan["cases"], inputs, strict=True):
        if (case.get("inspect_attempted") is not True or verified.get("case") != case["id"]
                or verified.get("root_sha256") != planned["expected_root_sha256"]
                or verified.get("view_sha256") != planned["expected_view_sha256"]
                or verified.get("region_xyxy") != planned["region_xyxy"]):
            raise ValueError("Real input differs from prespecified root/view/region")
        check = case.get("check")
        if check is None:
            if not case.get("error"):
                raise ValueError("Real receipt dropped a failed attempt")
            continue
        identity, scope = check.get("runtime_identity", {}), check.get("inspection_scope", {})
        if (check.get("backend") != "mlx" or identity.get("repo_id") != plan["repo_id"]
                or identity.get("revision") != plan["model_revision"]
                or identity.get("observation_mode") != plan["observation_mode"]
                or identity.get("image_max_side") != plan["image_max_side"]
                or check.get("photo_sha256") != verified["view_sha256"]
                or scope.get("view_sha256") != verified["view_sha256"]
                or scope.get("root_photo_sha256") != verified["root_sha256"]
                or scope.get("region_xyxy") != verified["region_xyxy"]):
            raise ValueError("Real MLX identity or saved scope does not match frozen plan")
    frozen_sources = freeze.get("source_sha256")
    if not isinstance(frozen_sources, dict) or not frozen_sources or result.get("source_sha256_after") != frozen_sources:
        raise ValueError("Real before/after frozen source hashes differ")
    if members is not None:
        for name, value in frozen_sources.items():
            if members.get(name) != value:
                raise ValueError("Delivered source differs from real-run frozen source: " + name)
    archive_bindings = {row["path"]: row["sha256"] for row in verification.get("archives", [])}
    archives = [
        ("real_a41_zip", cases[0]["id"] + "/order-evidence.zip", inputs[0]),
        ("real_mixed_order_zip", cases[1]["id"] + "/order-evidence.zip", inputs[1]),
        ("real_screws_zip", "public-replay-evidence.zip", inputs[1]),
    ]
    if set(archive_bindings) != {row[1] for row in archives}:
        raise ValueError("Real verification does not retain the three evidence ZIPs")
    for role, relative, expected in archives:
        if archive_bindings[relative] != sha(by_role[role]):
            raise ValueError("Real evidence ZIP SHA mismatch: " + role)
        evidence_zip(by_role[role], [expected["root_sha256"], expected["view_sha256"]])
    study_receipt = read_json(by_role["real_study_verification"])
    if (study_receipt.get("status") != "verified_internal_consistency" or study_receipt.get("errors")
            or study_receipt.get("input_sha256") != sha(by_role["real_study_export"])
            or study_receipt.get("source_kind") != "public_replay"
            or study_receipt.get("physical_authenticity_verified") is not False):
        raise ValueError("Public replay independent verification binding failed")
    return {"status": result["status"], "planned_requests": 2, "attempted_requests": 2,
            "source_changed": False, "verification_status": verification["status"],
            "cases": [{"sample": case["id"], "status": case.get("status"),
                       "decision": (case.get("check") or {}).get("decision"), "error": case.get("error")}
                      for case in cases]}


def summarize(root, artifacts, final):
    paths = {record["role"]: root / record["source"] for record in artifacts}
    summary = {"human_field_samples": 0, "new_accuracy_samples_from_public_integration": 0,
               "operator_scope_completeness_certified": False, "release_status": "final" if final else "preparation",
               "pending_required_roles": sorted(REQUIRED - paths.keys()), "completed_gates": [], "pending_gates": []}
    if final and summary["pending_required_roles"]:
        raise ValueError("Final delivery missing: " + ", ".join(summary["pending_required_roles"]))
    for role in ("final_tests", "extracted_tests", "backend_tests", "independent_region_tests"):
        if role in paths:
            summary[role] = strict_junit(paths[role])
            if final and role in {"final_tests", "extracted_tests"} and any(summary[role][key] for key in ("failures", "errors")):
                raise ValueError("Final or extracted suite contains failures/errors")
    for role in ("ui_api", "ui_visual", "ui_scroll"):
        if role in paths:
            summary[role] = {"assertions": receipt_assertions(paths[role]), "scope": "engineering_fixture_or_read_only"}
    if {"ui_api", "ui_visual"} <= paths.keys():
        if read_json(paths["ui_visual"]).get("prior_receipt_sha256") != sha(paths["ui_api"]):
            raise ValueError("Final visual receipt does not bind the retained API receipt")
        summary["completed_gates"].append("UI API receipt -> final visual receipt SHA")
    if {"ui_api", "ui_visual", "ui_freeze", "engineering_ui_export"} <= paths.keys():
        ui_freeze = read_json(paths["ui_freeze"])
        for role, key in (("ui_api", "integration_receipt_sha256"), ("ui_visual", "visual_receipt_sha256"),
                          ("engineering_ui_export", "engineering_export_sha256")):
            if ui_freeze.get(key) != sha(paths[role]):
                raise ValueError("UI source freeze receipt binding mismatch: " + role)
        if ui_freeze.get("source_sha256") != read_json(paths["ui_visual"]).get("source_sha256"):
            raise ValueError("UI freeze differs from final visual source")
        summary["completed_gates"].append("UI API + final visual + engineering export SHA chain; scroll is supplementary")
    for stem in ("engineering_api", "engineering_ui"):
        required = {stem + "_export", stem + "_verification"}
        if required <= paths.keys():
            summary[stem + "_verification"] = verify_engineering(paths[stem + "_export"], paths[stem + "_verification"])
            summary["completed_gates"].append(stem + " export -> independent verification SHA")
    members = source_members(paths["source_archive"]) if "source_archive" in paths else None
    source_gate = {"final_tests", "extracted_tests", "source_archive", "source_verification"}
    if source_gate <= paths.keys():
        receipt = read_json(paths["source_verification"])
        extracted = receipt.get("extracted_suite", {})
        if (receipt.get("status") != "passed" or receipt.get("source_archive_sha256") != sha(paths["source_archive"])
                or receipt.get("zip_crc_verified") is not True or receipt.get("all_file_digests_verified") is not True
                or receipt.get("runtime_returncode") != 0 or extracted.get("returncode") != 0
                or extracted.get("junit_sha256") != sha(paths["extracted_tests"])):
            raise ValueError("Source verification does not bind the actual ZIP and extracted JUnit")
        if extracted.get("tests") != summary["final_tests"]["tests"]:
            raise ValueError("Extracted and final planned test totals differ")
        if any(extracted.get(key) != value for key, value in summary["extracted_tests"].items()):
            raise ValueError("Extracted suite receipt differs from the actual JUnit outcomes")
        if members.get("test-results/engineering-v05-final.xml") != sha(paths["final_tests"]):
            raise ValueError("Source archive does not contain the exact final JUnit")
        summary["source_verification"] = {"status": "passed", "source_archive_sha256": sha(paths["source_archive"]),
                                          "extracted_suite": summary["extracted_tests"]}
        summary["completed_gates"].append("final JUnit -> source ZIP -> extracted JUnit SHA/counts")
    else:
        summary["pending_gates"].append("final JUnit -> actual source ZIP -> extracted JUnit SHA/counts")
    if members is not None and "method_preservation" in paths:
        method = read_json(paths["method_preservation"])
        if method.get("unchanged") is not True or set(method.get("source_hashes", {})) != {"vision.py", "spatial.py", "consensus.py", "identity.py"}:
            raise ValueError("Observer method-preservation receipt is incomplete")
        for name, value in method["source_hashes"].items():
            if members.get("kitguard/" + name) != value:
                raise ValueError("Delivered observer method does not match preservation receipt")
        summary["completed_gates"].append("four unchanged observer method SHA values in delivered source")
    if members is not None and {"ui_api", "ui_visual"} <= paths.keys():
        api, visual = read_json(paths["ui_api"]), read_json(paths["ui_visual"])
        for name, value in visual.get("source_sha256", {}).items():
            if members.get("kitguard/static/" + name) != value:
                raise ValueError("Delivered static source differs from final visual receipt: " + name)
        for name, value in api.get("source_sha256", {}).items():
            if name.endswith((".js", ".html")) and members.get("kitguard/static/" + name) != value:
                raise ValueError("Delivered UI behavior differs from API receipt: " + name)
        summary["completed_gates"].append("UI behavior and final CSS SHA in delivered source")
    real_gate = {"real_result", "real_verification", "real_freeze", "real_a41_zip", "real_screws_zip", "real_study_export",
                 "real_source_plan", "real_http_index", "real_study_verification", "real_mixed_order_zip"}
    if real_gate <= paths.keys():
        summary["real_api"] = verify_real(paths, members)
        summary["completed_gates"].append("two actual MLX attempts -> verification -> root/view ZIP SHA")
    else:
        summary["pending_gates"].append("two actual MLX attempts -> verification -> root/view ZIP SHA")
        if "real_result" in paths:
            real = read_json(paths["real_result"])
            summary["real_api_pending"] = {"status": real.get("status"), "planned_requests": real.get("planned_inspections"),
                                           "attempted_requests": real.get("attempted_inspections")}
    return summary


def render(manifest):
    summary = manifest["summary"]
    tests = summary.get("final_tests")
    tests_text = f"{tests['passed']} passed / {tests['tests']} · skipped {tests['skipped']} · failures {tests['failures']} · errors {tests['errors']}" if tests else "최종 테스트 대기 / 等待最终测试文件"
    state = "최종 인도 / 最终交付" if manifest["final"] else "준비 미리보기 · pending / 准备预览，尚待最终证据"
    artifacts = "".join(f'<li><a href="{quote(item["destination"], safe="/")}">{html.escape(item["title"])}</a>'
                        f'<small>{item["bytes"]:,} B · SHA256 <code>{item["sha256"]}</code></small></li>'
                        for item in manifest["artifacts"])
    real_rows = "".join(f'<tr><td>{html.escape(str(row["sample"]))}</td><td>{html.escape(str(row["status"]))}</td>'
                        f'<td>{html.escape(str(row["decision"]))}</td><td>{html.escape(str(row["error"] or "—"))}</td></tr>'
                        for row in summary.get("real_api", {}).get("cases", []))
    gates = "".join(f"<li>{html.escape(value)}</li>" for value in summary["completed_gates"])
    pending = ", ".join(summary["pending_required_roles"] + summary["pending_gates"]) or "없음 / 无"
    ui = " · ".join(f"{name}: {summary[key]['assertions']}" for name, key in (("API", "ui_api"), ("visual", "ui_visual"), ("scroll", "ui_scroll")) if key in summary)
    return f'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>KitGuard v0.5 · 검사 범위와 원본 기록</title><style>
*{{box-sizing:border-box}}body{{max-width:1120px;margin:auto;padding:36px 20px 70px;background:#f5f7f3;color:#173e35;font:15px/1.75 system-ui,sans-serif;overflow-wrap:anywhere}}h1{{font-size:38px;line-height:1.2}}h2{{font-size:21px}}section{{background:white;border:1px solid #d6e3d8;border-radius:14px;padding:24px;margin:22px 0}}.notice{{background:#fff6e7;border-color:#ead5af}}.kicker{{font-size:12px;letter-spacing:2px;color:#4a7564}}.grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}}.metric{{background:#eaf2eb;padding:20px;border-radius:10px}}strong{{display:block;font-size:27px}}ul{{list-style:none;padding:0}}li{{padding:12px 0;border-bottom:1px solid #e3ebe5}}a{{color:#066452;text-underline-offset:3px}}small{{display:block;color:#567365;font-size:11px}}code{{font-size:11px}}table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{text-align:left;padding:10px;border-bottom:1px solid #dbe6df}}.scroll{{overflow:auto}}@media(max-width:640px){{body{{padding:25px 14px}}h1{{font-size:29px}}section{{padding:18px 15px}}.grid{{grid-template-columns:1fr}}}}
</style><header><p class="kicker">KITGUARD / SCOPE &amp; PROVENANCE</p><h1>검사한 범위와 원본을 함께 남깁니다.</h1><p>KitGuard v0.5 · {state}</p><p>保存检查范围，也保留被排除部分的完整照片。</p></header>
<div class="grid"><div class="metric"><strong>0</strong>真人现场样本 / 실제 사람 현장 표본</div><div class="metric"><strong>0</strong>公开集成新增准确率样本 / 신규 정확도 표본</div><div class="metric"><strong>同源视图</strong>裁剪不是新增物理照片 / 새 촬영 아님</div></div>
<section><h2>새로운 기능 / 本次功能</h2><p>完整归一化照片 → 操作者声明矩形范围 → 同源派生输入 → 核验 → 原图与范围一同导出。重新选择只能从根图派生，旧结果失效；已登记研究案例在批次关闭前锁定范围。默认整图输入保持原保存字节。</p><p>키보드·터치·모바일 공학 검사 / 键盘、触控和手机工程验收：{html.escape(ui or 'pending')}</p></section>
<section class="notice"><h2>주장할 수 없는 것 / 解释边界</h2><p>范围内包含全部待检件、边界未切断零件，是操作者声明，软件不认证其真实性。框外未核验。应用不是自动定位系统，作者框裁剪不证明用户成功框选。</p><p>已知公开开发图的两次真实 MLX 调用只验证连接和证据链，不证明准确率改善、泛化计数、现场收益或比赛名次。人工栏由脚本填入的作者数量不代表真人表现；工程替身的结果也不是模型成绩。</p><p>模型的观察、空间计数、双方向与身份核验方法保持原版本。公开数据来源许可见随包披露。</p></section>
<section><h2>최종 엔지니어링 증거 / 最终工程证据</h2><p>{html.escape(tests_text)}</p><p>源码实际解压复测：{html.escape(str(summary.get('source_verification',{}).get('status','pending')))}</p><ul>{gates or '<li>最终交叉绑定等待实际文件 / pending</li>'}</ul></section>
<section><h2>실제 MLX 연결 / 真实 MLX 连接</h2><p>下表只显示已核对 result 与 verification SHA 的实际记录；错误与未完成不会用替身补齐。API 决策 correct 表示需要调整数量。</p><div class="scroll"><table><thead><tr><th>开发样例</th><th>状态</th><th>API 决策</th><th>错误</th></tr></thead><tbody>{real_rows or '<tr><td colspan="4">真实运行或独立核验待补 / pending</td></tr>'}</tbody></table></div></section>
<section class="notice"><h2>대기 항목 / 待补证据</h2><p>{html.escape(pending)}</p><p>预览不能代替最终交付；最终模式会拒绝缺失证据、SHA错配、测试总数不符和不完整真实调用记录。</p></section>
<section><h2>동봉 자료 / 随包资料</h2><p>下列链接均指向随包相对文件，无需连接工作台。ZIP中的照片与原图按原许可使用。</p><ul>{artifacts}</ul><p><a href="BUILD_MANIFEST.json">BUILD_MANIFEST.json</a> · <a href="SHA256.json">SHA256.json</a></p></section>
<footer><small>{html.escape(manifest['created_at'])} · 不改 v0.4 源码快照、历史实验或旧交付。所有校验仅表示记录内部一致与已知字节绑定，不认证实物。</small></footer></html>'''


def build(output, *, root=ROOT, overrides=None, final=False):
    root, output = Path(root).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError("Refuse to overwrite an existing delivery")
    artifacts, missing = collect(root, overrides or {})
    summary = summarize(root, artifacts, final)
    manifest = {"schema_version": 1, "kind": "kitguard_v05_delivery", "final": final,
                "created_at": datetime.now(UTC).isoformat(), "summary": summary,
                "artifacts": artifacts, "missing_roles": missing}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".v05-build-", dir=output.parent) as temporary:
        stage = Path(temporary) / "delivery"
        stage.mkdir()
        for item in artifacts:
            source, target = root / item["source"], stage / item["destination"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            if sha(target) != item["sha256"]:
                raise ValueError("Artifact changed while copying: " + item["role"])
        (stage / "BUILD_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        (stage / "index.html").write_text(render(manifest))
        for link in re.findall(r'href="([^"]+)"', (stage / "index.html").read_text()):
            if link != "SHA256.json" and not (stage / unquote(link)).is_file():
                raise ValueError("Missing relative delivery link: " + link)
        hashes = {path.relative_to(stage).as_posix(): sha(path) for path in sorted(stage.rglob("*")) if path.is_file()}
        (stage / "SHA256.json").write_text(json.dumps(hashes, ensure_ascii=False, indent=2) + "\n")
        (stage / "SHA256.json.sha256").write_text(sha(stage / "SHA256.json") + "  SHA256.json\n")
        stage.rename(output)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "tmp/delivery-v05-preview")
    parser.add_argument("--final", action="store_true")
    for role in DEFAULTS:
        parser.add_argument("--" + role.replace("_", "-"), type=Path)
    args = parser.parse_args()
    overrides = {key: value for key, value in vars(args).items() if key not in {"output", "final"} and value is not None}
    result = build(args.output, overrides=overrides, final=args.final)
    print(json.dumps({"output": str(args.output), "final": result["final"], "artifacts": len(result["artifacts"]),
                      "summary": result["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
