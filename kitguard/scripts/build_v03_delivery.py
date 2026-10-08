"""Build a new, verified v0.3 delivery directory from already reviewed local artifacts.

This script does not run inference, generate evaluation claims, submit anything, or
modify an existing delivery. See docs/v0.3/DELIVERY_PLAN.md for the input contract.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from urllib.parse import quote
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "final_evaluation": {".md", ".pdf"},
    "offline_report": {".html"},
    "source_archive": {".zip"},
    "demo_video": {".mp4", ".webm"},
    "demo_evidence": {".zip"},
    "demo_verification": {".json"},
    "source_verification": {".json"},
    "holdout_run": {".json"},
    "gate_report": {".json"},
}
FORBIDDEN_SUFFIXES = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".safetensors",
    ".gguf",
    ".pt",
    ".pth",
    ".bin",
    ".tar",
    ".tgz",
    ".gz",
}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}
RESERVED = {"index.html", "SHA256.json", "SHA256.json.sha256", "BUILD_MANIFEST.json"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def local_file(value, base):
    require(isinstance(value, str) and value.strip(), "Artifact path must be a nonempty local path")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    require(not path.is_symlink(), f"Symlink input is not accepted: {path}")
    path = path.resolve(strict=True)
    require(path.is_file(), f"Artifact is not a file: {path}")
    require(path.stat().st_size > 0, f"Artifact is empty: {path}")
    require(
        not any("报名" in p or "등록신청" in p for p in path.parts),
        f"Private registration input is forbidden: {path}",
    )
    require(
        path.suffix.lower() not in FORBIDDEN_SUFFIXES | IMAGE_SUFFIXES,
        f"Standalone photo, database, raw archive or weight file is forbidden: {path}",
    )
    return path


def safe_relative(value, *, destination=True):
    require(
        isinstance(value, str) and value and "\\" not in value,
        "Destination must be a POSIX relative file path",
    )
    path = PurePosixPath(value)
    require(
        not path.is_absolute() and ".." not in path.parts and ":" not in value,
        f"Unsafe relative path: {value}",
    )
    require(path.as_posix() == value, f"Noncanonical path: {value}")
    if destination:
        require(value not in RESERVED, f"Reserved path: {value}")
        require(
            not any(part.startswith(".") for part in path.parts), f"Hidden paths are not accepted: {value}"
        )
    return value


def assertion_value(payload, pointer):
    require(isinstance(pointer, str) and pointer.startswith("/"), "Assertion requires a JSON Pointer")
    current = payload
    for token in pointer[1:].split("/"):
        key = token.replace("~1", "/").replace("~0", "~")
        current = current[int(key)] if isinstance(current, list) else current[key]
    return current


def verify_assertions(artifact, path):
    assertions = artifact.get("assertions", [])
    require(isinstance(assertions, list), "assertions must be a list")
    if artifact["role"] in {"demo_verification", "source_verification"}:
        require(assertions, f"Explicit completed verification assertions required: {artifact['role']}")
    if assertions:
        require(path.suffix.lower() == ".json", "Assertions are only supported for JSON records")
        payload = json_read(path)
        for item in assertions:
            require(isinstance(item, dict) and "equals" in item, "Assertion requires pointer and equals")
            actual = assertion_value(payload, item.get("pointer"))
            expected = item["equals"]
            require(
                type(actual) is type(expected) and actual == expected,
                f"Verification assertion failed: {artifact['role']} {item['pointer']}",
            )


def archive_members(archive):
    names = archive.namelist()
    require(len(names) == len(set(names)), "Duplicate ZIP entries are forbidden")
    for info in archive.infolist():
        path = PurePosixPath(info.filename)
        require(
            not path.is_absolute() and ".." not in path.parts and "\\" not in info.filename,
            f"Unsafe ZIP member: {info.filename}",
        )
        require(not info.flag_bits & 1, "Encrypted ZIP entries are not accepted")
        require((info.external_attr >> 16) & 0o170000 != 0o120000, "Symlink ZIP entries are not accepted")
        require(
            path.suffix.lower() not in FORBIDDEN_SUFFIXES,
            f"Weight, database or raw archive ZIP member: {info.filename}",
        )
        require(
            not any("报名" in p or "등록신청" in p for p in path.parts),
            "Private registration archive member is forbidden",
        )
    require(archive.testzip() is None, "ZIP CRC verification failed")
    return {item.filename for item in archive.infolist() if not item.is_dir()}


def verify_zip(path, role):
    with ZipFile(path) as archive:
        names = archive_members(archive)
        if role == "source_archive":
            require(
                "KitGuard/SOURCE_MANIFEST.json" in names,
                "Source ZIP must contain KitGuard/SOURCE_MANIFEST.json",
            )
            require(
                not any(PurePosixPath(n).suffix.lower() in IMAGE_SUFFIXES for n in names),
                "Source ZIP must not contain photographs",
            )
            manifest = json.loads(archive.read("KitGuard/SOURCE_MANIFEST.json"))
            records = manifest["files"]
            expected = {"KitGuard/SOURCE_MANIFEST.json"}
            for item in records:
                name = "KitGuard/" + safe_relative(item["path"], destination=False)
                require(name not in expected, "Duplicate source manifest entry")
                expected.add(name)
                raw = archive.read(name)
                require(
                    len(raw) == item["bytes"] and hashlib.sha256(raw).hexdigest() == item["sha256"],
                    f"Source member digest mismatch: {name}",
                )
            require(names == expected, "Source ZIP has unmanifested or missing files")
        elif role == "demo_evidence":
            require(
                {"evidence.json", "OPEN_ME.html", "SHA256.json", "README.txt"} <= names,
                "Evidence ZIP is not a KitGuard order export",
            )
            payload = json.loads(archive.read("evidence.json"))
            require(
                payload.get("schema_version") == 2 and isinstance(payload.get("order"), dict),
                "Evidence ZIP schema is unsupported",
            )
            provenance = payload["order"].get("demo_source")
            require(
                isinstance(provenance, dict) and provenance.get("source_url") and provenance.get("license"),
                "Public demo evidence must retain source and license provenance",
            )
            require(
                not payload["order"].get("completions") and payload["order"].get("status") != "completed",
                "Public demo evidence must not claim physical completion",
            )
            checks = payload["order"].get("checks", [])
            require(isinstance(checks, list) and checks, "Evidence must contain actual recorded checks")
            for check in checks:
                runtime = check.get("runtime_identity", {})
                require(
                    check.get("backend") == "mlx"
                    and runtime.get("repo_id")
                    and runtime.get("revision")
                    and runtime.get("observation_mode"),
                    "Evidence check must identify its local MLX model and method",
                )
            photos = payload.get("photos", [])
            require(
                isinstance(photos, list) and photos, "Evidence must contain linked normalized order photos"
            )
            allowed_photos = set()
            for item in photos:
                photo_id = item.get("id", "")
                require(re.fullmatch(r"[A-Za-z0-9_-]{1,100}", photo_id), "Invalid evidence photo id")
                name = f"photos/{photo_id}.jpg"
                require(item.get("archive_path") == name, "Only linked normalized order photos are accepted")
                require(
                    hashlib.sha256(archive.read(name)).hexdigest() == item.get("sha256"),
                    "Evidence photo digest mismatch",
                )
                allowed_photos.add(name)
            require(
                names == allowed_photos | {"evidence.json", "OPEN_ME.html", "SHA256.json", "README.txt"},
                "Evidence ZIP contains unrelated files",
            )
            records = json.loads(archive.read("SHA256.json"))
            declared = set()
            for item in records:
                require(item["path"] not in declared, "Duplicate evidence manifest entry")
                declared.add(item["path"])
                raw = archive.read(item["path"])
                require(
                    len(raw) == item["bytes"] and hashlib.sha256(raw).hexdigest() == item["sha256"],
                    "Evidence member digest mismatch",
                )
            require(
                declared == allowed_photos | {"evidence.json", "OPEN_ME.html"},
                "Evidence manifest coverage mismatch",
            )
        else:
            raise ValueError("Only source_archive and demo_evidence ZIP roles are accepted")


def source_display(path):
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def load_inputs(manifest_path):
    manifest = json_read(manifest_path)
    require(
        manifest.get("schema_version") == 1 and manifest.get("release") == "v0.3",
        "Expected v0.3 delivery schema_version 1",
    )
    require(
        manifest.get("status") == "completed",
        "Delivery manifest is not completed; draft/running inputs cannot be published",
    )
    require(
        isinstance(manifest.get("summary"), str) and manifest["summary"].strip(),
        "A reviewed final summary is required",
    )
    require(
        isinstance(manifest.get("limitations"), list)
        and manifest["limitations"]
        and all(isinstance(v, str) and v.strip() for v in manifest["limitations"]),
        "Reviewed limitations are required",
    )
    require(
        manifest.get("selected_default") in {"spatial_inventory", "spatial_guarded"},
        "Explicit selected_default is required",
    )
    require(
        type(manifest.get("expected_holdout_cases")) is int and manifest["expected_holdout_cases"] == 64,
        "v0.3 delivery requires all 64 frozen holdout cases",
    )
    require(isinstance(manifest.get("artifacts"), list), "artifacts must be a list")
    records, used_paths, by_role = [], set(), {}
    for item in manifest["artifacts"]:
        require(isinstance(item, dict), "Artifact must be an object")
        role = item.get("role")
        require(isinstance(role, str) and re.fullmatch(r"[a-z][a-z0-9_]*", role), "Invalid artifact role")
        require(
            role not in by_role or role not in REQUIRED or role == "demo_evidence",
            f"Duplicate required role: {role}",
        )
        require(isinstance(item.get("title"), str) and item["title"].strip(), "Artifact title is required")
        require(isinstance(item.get("note"), str) and item["note"].strip(), "Artifact scope note is required")
        path = local_file(item.get("path"), manifest_path.parent)
        target = safe_relative(item.get("destination"))
        require(target not in used_paths, f"Duplicate destination: {target}")
        used_paths.add(target)
        require(
            Path(target).suffix.lower() == path.suffix.lower(),
            "Destination must retain the artifact file type",
        )
        if role in REQUIRED:
            require(path.suffix.lower() in REQUIRED[role], f"Wrong file type for {role}")
        digest = sha_file(path)
        require(item.get("sha256") == digest, f"Reviewed SHA-256 mismatch or missing: {role} ({path})")
        verify_assertions(item, path)
        if path.suffix.lower() == ".zip":
            verify_zip(path, role)
        record = {
            "role": role,
            "title": item["title"],
            "note": item["note"],
            "path": target,
            "source": source_display(path),
            "bytes": path.stat().st_size,
            "sha256": digest,
        }
        records.append((record, path))
        by_role[role] = (record, path)
    require(
        REQUIRED.keys() <= by_role.keys(),
        f"Missing required roles: {sorted(REQUIRED.keys() - by_role.keys())}",
    )
    run = json_read(by_role["holdout_run"][1])
    expected = manifest["expected_holdout_cases"]
    ids = run.get("case_ids", [])
    require(
        run.get("status") == "completed" and run.get("finished_at") and run.get("split") == "holdout",
        "Holdout run must be finished and identify the holdout split",
    )
    require(
        run.get("expected_cases") == run.get("completed_cases") == len(ids) == len(set(ids)) == expected,
        "Incomplete or duplicated holdout run",
    )
    gate = json_read(by_role["gate_report"][1])
    require(
        gate.get("complete") is True
        and gate.get("stage") == "holdout"
        and gate.get("planned_images") == gate.get("completed_images") == expected,
        "Gate report must cover the completed 64-image holdout",
    )
    require(
        gate.get("run_json_sha256") == by_role["holdout_run"][0]["sha256"],
        "Gate report is not bound to the supplied run.json",
    )
    candidate = gate.get("candidate", {})
    values = [candidate.get(key) for key in ("C", "W", "U", "E")]
    require(
        all(type(v) is int and v >= 0 for v in values)
        and sum(values) == expected
        and candidate.get("images") == expected,
        "Gate C/W/U/E denominator is inconsistent",
    )
    require(
        type(gate.get("stage_passed")) is bool and type(gate.get("default_adoption_eligible")) is bool,
        "Gate adoption decision is missing",
    )
    if manifest["selected_default"] == "spatial_guarded":
        require(
            gate["default_adoption_eligible"] is True,
            "Guarded default cannot be selected when the internally frozen adoption gate failed",
        )
    history = []
    for item in manifest.get("historical_references", []):
        require(
            isinstance(item.get("title"), str) and isinstance(item.get("note"), str) and item["note"].strip(),
            "Historical references require title and scope note",
        )
        path = local_file(item.get("path"), manifest_path.parent)
        digest = sha_file(path)
        require(item.get("sha256") == digest, "Historical reference SHA-256 mismatch")
        history.append(
            (
                {
                    "title": item["title"],
                    "note": item["note"],
                    "source": source_display(path),
                    "bytes": path.stat().st_size,
                    "sha256": digest,
                },
                path,
            )
        )
    return manifest, records, history, gate


def link(path):
    return html.escape(quote(path, safe="/"), quote=True)


def render_page(manifest, records, history, gate):
    esc = html.escape
    cards = "".join(
        f'<a class="card" href="{link(r["path"])}"><h3>{esc(r["title"])}</h3><p>{esc(r["note"])}</p><span>{esc(Path(r["path"]).suffix[1:].upper())} · {r["bytes"] / 1024:.1f} KB　打开文件 ↗</span></a>'
        for r in records
    )
    historical = "".join(
        f'<li><a href="{link(r["href"])}">{esc(r["title"])}</a><p>{esc(r["note"])}</p></li>' for r in history
    )
    limits = "".join(f"<li>{esc(value)}</li>" for value in manifest["limitations"])
    c = gate["candidate"]
    metrics = "".join(
        f"<div><b>{c[key]}<small> / 64</small></b><span>{label}</span></div>"
        for key, label in (
            ("C", "正确且可行动"),
            ("W", "错误且可行动"),
            ("U", "要求补拍 / 人工确认"),
            ("E", "执行错误"),
        )
    )
    gate_label = "达到内部事前冻结的留出门槛" if gate["stage_passed"] else "未达到内部事前冻结的留出门槛"
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><title>KitGuard v0.3 · 交付与自检</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f2f5f4;color:#183b35;font:16px/1.7 system-ui,-apple-system,sans-serif}}main{{max-width:1120px;margin:auto;padding:52px 24px 28px}}a{{color:#076657;text-underline-offset:4px}}a:focus-visible{{outline:3px solid #d58a28;outline-offset:5px}}.eyebrow{{font-size:12px;letter-spacing:.16em;color:#53766d;font-weight:750}}h1{{font-size:clamp(30px,5vw,52px);line-height:1.16;margin:16px 0}}h2{{font-size:23px;line-height:1.4;margin:0 0 16px}}h3{{font-size:18px;line-height:1.45;margin:0 0 8px}}.lead{{max-width:900px;font-size:18px}}nav{{display:flex;flex-wrap:wrap;gap:10px 24px;margin:28px 0 32px}}section{{margin-top:34px}}.metric{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border:1px solid #c5d7cf;border-radius:16px;background:#fff;overflow:hidden}}.metric div{{padding:20px;border-right:1px solid #e0e9e5}}.metric div:last-child{{border:0}}.metric b{{display:block;font-size:34px;line-height:1.25}}.metric small{{font-size:15px;font-weight:400;color:#527268}}.metric span{{font-size:13px}}.scope{{font-size:14px;color:#536e67}}.tag{{display:inline-block;padding:5px 10px;border-radius:5px;background:#e1ece6;font-size:13px}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}.card{{display:block;background:#fff;border:1px solid #cbdcd4;border-radius:14px;padding:21px;text-decoration:none;overflow-wrap:anywhere}}.card:hover{{border-color:#076657;background:#fafffc}}.card p{{color:#3d6056;margin:0 0 15px;font-size:14px}}.card span{{font-size:12px;color:#597b6c}}.notice{{border:1px solid #e1c792;border-left:5px solid #af7a23;border-radius:9px;padding:23px;background:#fff8e9}}li{{margin-bottom:9px}}.history{{background:#e9efec;padding:23px;border-radius:12px}}.history p{{margin:3px 0 15px;font-size:14px}}code{{overflow-wrap:anywhere;font-size:13px}}footer{{border-top:1px solid #ccdad4;padding:22px 0;margin-top:40px;font-size:13px;color:#557168}}@media(max-width:620px){{main{{padding:28px 16px}}.grid{{grid-template-columns:1fr}}.metric{{grid-template-columns:repeat(2,minmax(0,1fr))}}.metric div{{border-bottom:1px solid #e0e9e5}}.metric div:nth-child(2){{border-right:0}}.metric div:nth-child(3){{border-bottom:0}}.metric b{{font-size:29px}}.lead{{font-size:16px}}}}
</style></head><body><main><header><div class="eyebrow">해피 · KITGUARD · v0.3</div><h1>交付与自检材料</h1><p lang="ko">개발 결과 · 검증 자료 · 공개 사진 기반 시연</p><p class="lead">{esc(manifest["summary"])}</p><nav aria-label="页面导航"><a href="#evaluation">评估结果</a><a href="#files">交付文件</a><a href="#boundaries">使用边界</a><a href="#history">历史版本</a></nav></header>
<section id="evaluation"><h2>冻结后的 64 张留出测试 <span lang="ko">/ 최종 검증</span></h2><div class="metric">{metrics}</div><p class="scope">C / W / U / E 来自完整门槛报告，分母包含全部 64 张预定图片。正确且可行动不等于工业现场准确率；补拍与执行错误均未计为成功。门槛是团队内部事前冻结，并非外部正式预注册。</p><p><span class="tag">{gate_label}</span>　启动脚本默认方法：<code>{esc(manifest["selected_default"])}</code></p></section>
<section id="files"><h2>本次交付 <span lang="ko">/ 이번 버전 산출물</span></h2><div class="grid">{cards}</div><p class="scope">文档、报告和录像可以本地打开。证据 ZIP 请解压后打开 OPEN_ME.html。源码 ZIP 不含模型权重、原始数据集、数据库或私人报名表。</p></section>
<section id="boundaries" class="notice"><h2>事实与使用边界 <span lang="ko">/ 범위와 한계</span></h2><ul>{limits}</ul><p>这是内部技术交付，未代为报名或向比赛提交。文件哈希用于检查一致性，不证明照片真实性、实物完成或比赛资格，也不保证名次。</p></section>
<section id="history" class="history"><h2>历史资料 <span lang="ko">/ 이전 버전 참고</span></h2><p>以下文件保留原版本与原测量范围，仅供对照，不计入 v0.3 新测试。历史引用依赖原项目的同级目录，不随本目录复制。</p><ul>{historical or "<li>本交付清单未加入历史文件引用。</li>"}</ul></section>
<footer>完整性清单：<a href="SHA256.json">SHA256.json</a> · <a href="SHA256.json.sha256">清单自身 SHA-256</a> · <a href="BUILD_MANIFEST.json">交付来源与构建记录</a><p>清单覆盖所有交付文件（清单自身由独立 SHA256.json.sha256 记录，避免循环校验）；历史引用单独记录，不伪装为随包文件。此页面没有外部 CDN 或网络依赖。</p></footer></main></body></html>"""


def build(manifest_path, output):
    require(not output.exists(), "Output already exists; preserve it and select a new directory")
    require(output.name != "delivery-v0.2", "The historical v0.2 directory is protected")
    manifest, inputs, history_inputs, gate = load_inputs(manifest_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".v03-delivery-", dir=output.parent))
    try:
        records = []
        for record, source in inputs:
            target = staging / record["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            require(sha_file(target) == record["sha256"], f"Source changed during copying: {source}")
            records.append(record)
        history = [
            {**record, "href": Path(os.path.relpath(source, output)).as_posix()}
            for record, source in history_inputs
        ]
        provenance = {
            "schema_version": 1,
            "release": "v0.3",
            "created_at": datetime.now(UTC).isoformat(),
            "status": "completed",
            "manifest_source": source_display(manifest_path),
            "manifest_sha256": sha_file(manifest_path),
            "selected_default": manifest["selected_default"],
            "artifacts": records,
            "historical_references": history,
            "scope": "Internal reviewed artifact bundle; not a contest submission or rank guarantee",
        }
        (staging / "BUILD_MANIFEST.json").write_text(
            json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (staging / "index.html").write_text(render_page(manifest, records, history, gate), encoding="utf-8")
        file_records = [
            {
                "path": path.relative_to(staging).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha_file(path),
            }
            for path in sorted(staging.rglob("*"))
            if path.is_file()
        ]
        checksum_manifest = {
            "schema_version": 1,
            "release": "v0.3",
            "created_at": provenance["created_at"],
            "scope": "All bundle files except SHA256.json and its detached checksum; historical references are not bundle files",
            "files": file_records,
            "historical_references": history,
        }
        (staging / "SHA256.json").write_text(
            json.dumps(checksum_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (staging / "SHA256.json.sha256").write_text(
            f"{sha_file(staging / 'SHA256.json')}  SHA256.json\n", encoding="utf-8"
        )
        require(not output.exists(), "Output appeared during build; refusing replacement")
        staging.rename(output)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {
        "output": str(output),
        "artifact_files": len(inputs),
        "manifested_files": len(file_records),
        "historical_references": len(history),
        "sha256_manifest": sha_file(output / "SHA256.json"),
        "status": "completed",
    }


def template():
    specs = [
        (
            "final_evaluation",
            "中文最终自检评估",
            "docs/v0.3/FINAL_EVALUATION.md",
            "review/FINAL_EVALUATION.md",
        ),
        (
            "offline_report",
            "中文交互评估报告",
            "output/report/KitGuard_v0.3.html",
            "review/KitGuard_v0.3.html",
        ),
        (
            "source_archive",
            "源码与复算记录",
            "output/KitGuard_source_v0.3.zip",
            "source/KitGuard_source_v0.3.zip",
        ),
        ("demo_video", "真实本地 API 演示", "REPLACE/demo.mp4", "demo/KitGuard_real_API_v0.3.mp4"),
        ("demo_evidence", "实际订单离线证据", "REPLACE/evidence.zip", "demo/evidence.zip"),
        (
            "demo_verification",
            "演示验证记录",
            "REPLACE/demo-verification.json",
            "verification/demo-verification.json",
        ),
        (
            "source_verification",
            "源码验收记录",
            "REPLACE/source-verification.json",
            "verification/source-verification.json",
        ),
        (
            "holdout_run",
            "64 张完整留出运行记录",
            "evaluation-runs/v03_guarded_holdout_v1/run.json",
            "verification/holdout-run.json",
        ),
        (
            "gate_report",
            "内部事前冻结门槛判定",
            "evaluation-runs/v03_guarded_holdout_v1/gate_report_v1.json",
            "verification/holdout-gate.json",
        ),
        (
            "judge_qa",
            "韩文评委问答 / 심사위원 질의응답",
            "docs/v0.3/JUDGES_QA_KO.md",
            "review/JUDGES_QA_KO.md",
        ),
    ]
    artifacts = []
    for role, title, path, destination in specs:
        item = {
            "role": role,
            "title": title,
            "path": str(ROOT / path),
            "destination": destination,
            "note": "DRAFT: replace with this artifact's measured scope and version",
            "sha256": "REPLACE_AFTER_FINAL_QA",
        }
        if role == "demo_verification":
            item["assertions"] = [{"pointer": "/status", "equals": "passed"}]
        elif role == "source_verification":
            item["assertions"] = [
                {"pointer": "/zip_crc_verified", "equals": True},
                {"pointer": "/all_file_digests_verified", "equals": True},
            ]
        artifacts.append(item)
    return {
        "schema_version": 1,
        "release": "v0.3",
        "status": "draft",
        "summary": "DRAFT: wait for the complete frozen holdout and real API evidence before writing final conclusions",
        "selected_default": "spatial_inventory",
        "expected_holdout_cases": 64,
        "limitations": [
            "DRAFT: reviewed limits required; retain correlated-model, public-static-data, absent bracket/field evidence and competition eligibility boundaries"
        ],
        "artifacts": artifacts,
        "historical_references": [
            {
                "title": "v0.2 历史交付入口",
                "path": str(ROOT / "output/delivery-v0.2/index.html"),
                "note": "原版本文档、录像和 48 张历史评测；不是 v0.3 新留出结果",
                "sha256": "REPLACE_WITH_EXISTING_HISTORY_HASH",
            }
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--manifest", type=Path)
    group.add_argument(
        "--write-template", type=Path, help="Write a non-executable draft input manifest; refuse overwrite"
    )
    parser.add_argument("--output", type=Path, default=ROOT / "output/delivery-v0.3")
    args = parser.parse_args()
    try:
        if args.write_template:
            require(not args.write_template.exists(), "Template path already exists")
            args.write_template.parent.mkdir(parents=True, exist_ok=True)
            args.write_template.write_text(
                json.dumps(template(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            print(
                json.dumps(
                    {"template": str(args.write_template.resolve()), "status": "draft"}, ensure_ascii=False
                )
            )
        else:
            print(
                json.dumps(
                    build(args.manifest.resolve(strict=True), args.output.resolve()), ensure_ascii=False
                )
            )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f"Delivery build refused: {exc}") from exc


if __name__ == "__main__":
    main()
