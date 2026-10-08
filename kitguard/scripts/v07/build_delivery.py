"""Assemble five verified submission components and evidence in a fresh local folder.

Run with a Python environment containing pypdf after all source experiments and
artifact QA have finished. This tool does not publish or submit anything.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
EVALUATION_MODES = ("spatial_inventory", "spatial_guarded", "selective_identity_experimental_v1")
EVALUATION_FREEZE_SHA = "cec1cf5362a5154cfd6e4d27e5ed9dbb49d7757a12189474c13e643f1dc67be7"
PRIMARY = {
    "report": ("결과 보고서", "结果报告", ".pdf"),
    "technical": ("Agent 기술 설명", "Agent 技术说明", ".pdf"),
    "source": ("실행 소스", "可运行源码", ".zip"),
    "video": ("실제 실행 시연", "真实运行演示", ".mp4"),
    "slides": ("발표 자료", "主讲幻灯片", ".pptx"),
}


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def local_file(value, root):
    path = root / value
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
        raise ValueError(f"Expected regular project-local artifact: {value}")
    return path.resolve()


def junit(path):
    cases = ET.parse(path).getroot().findall(".//testcase")
    if not cases:
        raise ValueError("Missing executed software tests")
    if any(c.find("failure") is not None or c.find("error") is not None for c in cases):
        raise ValueError("Software test failures must be resolved before release")
    skipped = sum(c.find("skipped") is not None for c in cases)
    return {"total": len(cases), "passed": len(cases) - skipped, "skipped": skipped}


def evaluation_evidence(checks, root):
    """Bind a completed independent audit to this exact frozen experiment.

    This is a receipt/identity gate, not a new raw-call audit or a model run.
    Failed engineering acceptance remains reportable; missing/mismatched evidence
    cannot pass merely because a summary labels itself successful.
    """
    required = ("evaluation_run", "evaluation_analysis", "evaluation_freeze", "evaluation_audit")
    if any(not isinstance(checks.get(key), str) or not checks[key] for key in required):
        raise ValueError("Require evaluation_run, evaluation_analysis, evaluation_freeze and evaluation_audit checks")
    paths, records = {}, {}

    def load(key, value):
        path = local_file(value, root)
        raw = path.read_bytes()
        paths[key] = path
        records[key] = {"path": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(raw).hexdigest()}
        return json.loads(raw)

    run = load("evaluation_run", checks["evaluation_run"])
    # Do not inspect predictions or partial results while a run is still active.
    if (run.get("status") != "completed" or type(run.get("completed_attempts")) is not int
            or run["completed_attempts"] != 153 or type(run.get("planned_attempts")) is not int
            or run["planned_attempts"] != 153 or run.get("source_changed") is not False
            or run.get("isolated_python") is not True):
        raise ValueError("The frozen three-method evaluation has not finished unchanged and isolated")
    freeze = load("evaluation_freeze", checks["evaluation_freeze"])
    scores = load("evaluation_analysis", checks["evaluation_analysis"])
    audit = load("evaluation_audit", checks["evaluation_audit"])
    if (freeze.get("schema") != "kitguard.v07.public-paired.freeze.v1"
            or scores.get("schema") != "kitguard.v07.public-paired.analysis.v1"
            or audit.get("schema") != "kitguard.v07.public-paired.independent-audit.v1"):
        raise ValueError("Evaluation freeze, analysis or independent audit has the wrong schema/version")
    if records["evaluation_freeze"]["sha256"] != EVALUATION_FREEZE_SHA or run.get("freeze_sha256") != EVALUATION_FREEZE_SHA:
        raise ValueError("Evaluation is not bound to the registered v0.7 three-method freeze")
    if (tuple(freeze.get("modes", [])) != EVALUATION_MODES or freeze.get("cases") != 51
            or freeze.get("attempts") != 153 or set(scores.get("modes", {})) != set(EVALUATION_MODES)):
        raise ValueError("Exactly the three registered modes and their complete denominator are required")
    if (audit.get("status") != "passed" or audit.get("source_changed") is not False
            or audit.get("model_loaded_or_called") is not False
            or audit.get("planned_photos") != 51 or audit.get("planned_attempts") != 153
            or audit.get("completed_attempts") != 153):
        raise ValueError("A completed, passed independent CPU audit is required")
    independent = audit.get("independent_results", {})
    if any(set(mapping) != set(EVALUATION_MODES) for mapping in (
            independent.get("modes", {}), audit.get("model_identity", {}), audit.get("raw_evidence_by_mode", {}))):
        raise ValueError("Independent audit must contain exactly all three registered modes")
    for mode in EVALUATION_MODES:
        group = scores["modes"][mode].get("all", {})
        outcomes = group.get("outcomes", {})
        if (type(group.get("planned")) is not int or group["planned"] != 51
                or set(outcomes) != set("CWUEN") or any(type(n) is not int or n < 0 for n in outcomes.values())
                or sum(outcomes.values()) != 51 or outcomes["N"] != 0):
            raise ValueError("Every method must retain 51 outcomes with no missing attempts")
        frozen_identity = freeze.get("model_identity", {}).get(mode, {})
        identity = audit["model_identity"][mode]
        identity_keys = {"label", "repo_id", "revision", "observer_protocol_sha256", "observer_source_hashes",
                         "observation_mode", "image_max_side", "path"}
        if set(identity) != identity_keys or any(identity[key] != frozen_identity.get(key) for key in identity_keys):
            raise ValueError("Audited model/protocol identity differs from the registered freeze")
    if not isinstance(audit.get("artifacts_sha256"), dict) or not isinstance(audit.get("evidence_sha256"), dict):
        raise ValueError("Independent audit is missing actual artifact hash bindings")  # noqa: TRY004 -- Invalid evidence, not an API argument type.
    run_dir = paths["evaluation_run"].parent
    if paths["evaluation_run"].name != "run.json" or paths["evaluation_analysis"] != run_dir / "analysis.json":
        raise ValueError("Evaluation metadata and analysis must come from the same audited run directory")
    for filename, key in (("run.json", "evaluation_run"), ("analysis.json", "evaluation_analysis")):
        if audit["artifacts_sha256"].get(filename) != records[key]["sha256"]:
            raise ValueError(f"Independent audit does not bind the actual {filename} bytes")
    evidence_hashes = {"freeze.json": EVALUATION_FREEZE_SHA,
                       "manifest.json": freeze.get("manifest_sha256"),
                       "predictions.jsonl": audit["evidence_sha256"].get("predictions")}
    for filename, expected in evidence_hashes.items():
        path = local_file((run_dir / filename).relative_to(root).as_posix(), root)
        actual = sha(path)
        if (not isinstance(expected, str) or len(expected) != 64 or actual != expected
                or audit["artifacts_sha256"].get(filename) != actual):
            raise ValueError(f"Independent audit does not bind the actual run {filename}")
        records[filename] = {"path": path.relative_to(root).as_posix(), "sha256": actual}
    if (audit["evidence_sha256"].get("freeze") != EVALUATION_FREEZE_SHA
            or audit["evidence_sha256"].get("manifest") != freeze.get("manifest_sha256")):
        raise ValueError("Independent audit evidence belongs to another freeze or manifest")
    auditor = local_file("scripts/v07/audit_public_paired.py", root)
    if audit["evidence_sha256"].get("auditor") != sha(auditor):
        raise ValueError("Independent audit was produced by a different auditor source version")
    records["auditor"] = {"path": auditor.relative_to(root).as_posix(), "sha256": sha(auditor)}
    # The auditor exposes this lightweight comparison independently of its CPU replay.
    from scripts.v07.audit_public_paired import cross_check_report

    cross_check_report(independent, scores)
    if (set(scores.get("comparisons_vs_inventory", {})) != set(EVALUATION_MODES[1:])
            or set(independent.get("comparisons_vs_inventory", {})) != set(EVALUATION_MODES[1:])
            or scores.get("default_change_authorized_by_this_report") is not False
            or audit.get("default_change_authorized") is not False):
        raise ValueError("Evaluation comparison scope or default-change authority is inconsistent")
    # Pin these compact source records for rechecking immediately before delivery is sealed.
    return {"evaluation_attempts": run["completed_attempts"], "evaluation_modes": list(EVALUATION_MODES),
            "evaluation_freeze_sha256": EVALUATION_FREEZE_SHA, "evaluation_independent_audit_status": "passed",
            "evaluation_evidence": records,
            "evaluation_verification_scope": "Independent CPU audit receipt bound to actual run, analysis, freeze, manifest, predictions and auditor bytes"}


def validate(config, paths, root):
    from pypdf import PdfReader

    from scripts.v07.package_source import verify_archive

    report_pages = len(PdfReader(paths["report"]).pages)
    technical_pages = len(PdfReader(paths["technical"]).pages)
    if not 1 <= report_pages <= 5 or technical_pages != 1:
        raise ValueError("Require at most five report pages and exactly one technical page")
    with ZipFile(paths["slides"]) as archive:
        presentation = ET.fromstring(archive.read("ppt/presentation.xml"))
        slides = len(presentation.findall(".//{http://schemas.openxmlformats.org/presentationml/2006/main}sldId"))
        if not 1 <= slides <= 10 or archive.testzip() is not None:
            raise ValueError("Invalid presentation or more than ten slides")
    source_manifest = json.loads(verify_archive(paths["source"]))
    if source_manifest["version"] != config["version"]:
        raise ValueError("Source version differs from delivery version")
    source_check = read(local_file(config["checks"]["source"], root))
    if source_check.get("status") != "passed" or source_check.get("archive_sha256") != sha(paths["source"]):
        raise ValueError("Source archive lacks its matching extracted runtime verification")
    video = read(local_file(config["checks"]["video"], root))
    measured = video.get("verification", {})
    duration = measured.get("duration_seconds")
    if (video.get("status") != "encoded_and_decode_verified"
            or video.get("video", {}).get("sha256") != sha(paths["video"])
            or measured.get("full_decode_passed") is not True
            or not isinstance(duration, (int, float)) or not 0 < duration <= 180):
        raise ValueError("Video lacks matching hash, completed decode, or measured duration <=180s")
    evaluation = evaluation_evidence(config["checks"], root)
    return {
        "report_pages": report_pages, "technical_pages": technical_pages,
        "presentation_slides": slides, "video_duration_seconds": duration,
        "source_version": source_manifest["version"], "source_sha256": sha(paths["source"]),
        "software_tests": junit(local_file(config["checks"]["tests"], root)),
        **evaluation,
        "experimental_acceptance_is_not_a_release_guarantee": True,
        "real_user_validation_claimed": False, "physical_task_validation_claimed": False,
    }


def index_markup(config, records, verified):
    esc = html.escape
    primary = []
    evidence = []
    for row in records:
        link = f'<a href="{quote(row["destination"])}">{esc(row["title"])}</a>'
        if row["role"] in PRIMARY:
            primary.append(f'<article><span>{esc(PRIMARY[row["role"]][1])}</span><h2>{link}</h2>'
                           f'<p>{row["bytes"] / 1048576:.1f} MiB</p></article>')
        else:
            evidence.append(f'<li>{link}</li>')
    note = "".join(f"<p>{esc(value)}</p>" for value in config["summary"])
    video = next(r["destination"] for r in records if r["role"] == "video")
    return f'''<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; media-src 'self';">
<title>KitGuard {esc(config['version'])} · 제출 자료 / 交付材料</title>
<style>
:root{{font-family:system-ui,-apple-system,sans-serif;color:#143c3a;background:#eef5f2}}
*{{box-sizing:border-box}}body{{margin:0}}main{{max-width:1080px;margin:auto;padding:48px 24px}}
header{{padding:36px;border-radius:24px;background:#143c3a;color:#fff}}header small{{letter-spacing:.12em;color:#b4ded0}}
h1{{font-size:clamp(30px,5vw,54px);line-height:1.08;margin:22px 0}}p{{line-height:1.7;max-width:78ch}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px;margin:24px 0}}
article{{background:white;border:1px solid #d6e5df;padding:24px;border-radius:18px}}h2{{font-size:21px;margin:12px 0}}
article span{{font-size:13px;color:#56786e}}a{{color:#125d50;text-underline-offset:4px}}a:focus{{outline:3px solid #f1ad42;outline-offset:4px}}
section{{background:white;border:1px solid #d6e5df;border-radius:18px;padding:24px;margin:20px 0}}
video{{width:100%;border-radius:12px;background:#143c3a}}li{{margin:12px 0;overflow-wrap:anywhere}}
.meta{{font-size:14px;color:#507469}}code{{overflow-wrap:anywhere}}@media(max-width:600px){{main{{padding:16px}}header{{padding:24px}}}}
</style><main><header><small>해피 · LOCAL PHOTO REVIEW AGENT</small><h1>KitGuard {esc(config['version'])}</h1>
<p>공개 사진과 주문을 대조하고, 변경된 버전의 증거를 다시 확인합니다.</p>
<p>公开照片与订单核对 · 版本变更后重新核验 · 可离线复查</p></header>
<div class="grid">{''.join(primary)}</div>
<section><h2>검증 범위 / 验证范围</h2>{note}<p class="meta">보고서 {verified['report_pages']}쪽 · 기술 설명 {verified['technical_pages']}쪽 · 발표 {verified['presentation_slides']}장 · 영상 {verified['video_duration_seconds']:.1f}초</p></section>
<section><h2>실제 실행 화면 편집본 / 真实运行画面剪辑</h2><video controls preload="metadata" src="{quote(video)}"></video>
<p class="meta">실제 공개 사진·로컬 추론. 대기·조작 구간을 줄인 화면 편집본이며 연속 실시간 녹화가 아닙니다.</p></section>
<section><h2>근거와 재현 안내 / 证据与复现说明</h2><ul>{''.join(evidence)}</ul>
<p><a href="BUILD_MANIFEST.json">交付清单 / Manifest</a> · <a href="SHA256.json">SHA-256</a></p>
<p class="meta">이 폴더는 로컬 자료 묶음입니다. 대회 포털에 제출하거나 외부에 게시하지 않았습니다.<br>本目录尚未向比赛平台提交或对外发布。哈希用于完整性校验，不是签名或现场认证。</p></section></main></html>'''


def build(config_path, output, root=ROOT):
    root = root.resolve()
    if output.exists() or output.is_symlink():
        raise FileExistsError("Use a fresh delivery directory; prior artifacts are preserved")
    config = read(config_path)
    if set(config["primary"]) != set(PRIMARY):
        raise ValueError("Exactly five primary submission components are required")
    paths = {role: local_file(value, root) for role, value in config["primary"].items()}
    for role, path in paths.items():
        if path.suffix.lower() != PRIMARY[role][2]:
            raise ValueError(f"Unexpected format: {role}")
    verified = validate(config, paths, root)
    sources = [(role, PRIMARY[role][0], path) for role, path in paths.items()]
    sources += [(f"evidence_{index}", row["title"], local_file(row["path"], root))
                for index, row in enumerate(config.get("evidence", []))]
    output.mkdir(parents=True)
    records = []
    for role, title, source in sources:
        relative = Path("files") / role / source.name
        destination = output / relative
        destination.parent.mkdir(parents=True)
        before = sha(source)
        shutil.copyfile(source, destination)
        if sha(destination) != before or sha(source) != before:
            raise ValueError("Artifact changed while being copied; preserve this failed build")
        records.append({"role": role, "title": title, "source": source.relative_to(root).as_posix(),
                        "destination": relative.as_posix(), "sha256": before, "bytes": source.stat().st_size})
    for record in verified["evaluation_evidence"].values():
        if sha(local_file(record["path"], root)) != record["sha256"]:
            raise ValueError("Audited evaluation evidence changed during delivery assembly; preserve this failed build")
    (output / "index.html").write_text(index_markup(config, records, verified))
    write(output / "BUILD_MANIFEST.json", {
        "schema": "kitguard.v07.delivery.v1", "created_at": datetime.now(UTC).isoformat(),
        "version": config["version"], "submission_sent": False,
        "validation": verified, "summary": config["summary"], "artifacts": records,
        "config_sha256": sha(config_path),
    })
    write(output / "SHA256.json", [
        {"path": p.relative_to(output).as_posix(), "sha256": sha(p), "bytes": p.stat().st_size}
        for p in sorted(output.rglob("*")) if p.is_file()
    ])
    (output / "SHA256.json.sha256").write_text(f"{sha(output / 'SHA256.json')}  SHA256.json\n")
    return {"output": str(output), "artifacts": len(records), "validation": verified}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.config, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
