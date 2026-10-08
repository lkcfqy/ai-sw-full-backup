"""Build an explicit, hash-bound local preview; never publish or gather directories."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import stat
import subprocess
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from urllib.parse import quote
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[2]
VERSION = "0.8.0.dev1"
SCHEMA = "kitguard.v08.delivery-plan.v1"
LOCO_FREEZE = "513b461a7574e6c68f1bdd6674769fe4b9fa95f3626b1302969f01c70b3deffd"
LOCO_AUDIT = "f9f1256442934061982c3aaca7f96c15a365d83e2a5aff000a5fef13ea20f263"
OLD_BUILDER = "132f8bb282e40674d6594b24d31e90a75dd6d45fa46ddb2b56233402c2dd2a9e"
OLD_PACKAGER = "16e1f5b2c170d400462cfbfe041268b781438a9f975cea726004a417fdf0d8bc"
# Exact pre-existing text notices/metadata, not model payloads. New paths or bytes require review.
MODEL_NOTICE_SHA256 = {'third_party/models/Qwen3-VL-8B-Instruct-8bit.manifest.json': 'c94dd094c4fc4dd403a0fa9decaf63cc8a16568bb85e9e2be0c3ad5a1c9ce173',
    'third_party/models/Qwen3-VL-8B-Instruct/LICENSE-2.0.txt': 'cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30',
    'third_party/models/Qwen3-VL-8B-Instruct/README.md': '6d5d06e0c3f069097002445d30dce9ee107db3afaf15563f09e6df49b8dcb4d7',
    'third_party/models/Qwen3.6-27B-4bit.manifest.json': 'd4595e09a870f9cf9ed081bbf33971dc8948bfdecab547c9c39888129455e3b0',
    'third_party/models/Qwen3.6-27B/LICENSE': '50cbab8a892c5f2993b8c7351a99182507472def3b1374558308605d99b86b32',
    'third_party/models/Qwen3.6-27B/README.md': 'bb936d6da51014f1edc9aa4cf9abf28d98695b7616ad56adfeeebfa752051d3d',
    'third_party/models/grounding-dino-tiny/DOWNLOAD_MANIFEST.json': 'd49f5f395d1fb4bcf00308918e0ee0f58406dca7b963f89b59484899f2aea2c5',
    'third_party/models/grounding-dino-tiny/LICENSE': 'cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30',
    'third_party/models/grounding-dino-tiny/README.md': 'cf46f74c7b6850f1d5cbe406028324d8798148726016d46a69a365b4a2d3e89f',
    'third_party/models/grounding-dino-tiny/UPSTREAM_API_METADATA.json': 'ce6de55a8cf5ce08b9e6ca3848a5f7b041268e6540e5c6b113cf68cbe84f1b60',
    'third_party/models/owlv2-base-patch16-ensemble/DOWNLOAD_MANIFEST.json': '4a0e7981a87be856ec8efb7211d30b61ea5905d1a62e78c52af561e093d6db22',
    'third_party/models/owlv2-base-patch16-ensemble/LICENSE': 'cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30',
    'third_party/models/owlv2-base-patch16-ensemble/README.md': '7c7426bc5ec939a42d1f96fb093031b6263400cceac4129ebb941a0c8c11b9b9',
    'third_party/models/owlv2-base-patch16-ensemble/UPSTREAM_API_METADATA.json': '9cf2e58e88d7e55ff169228f5e944621dad3d915dddabbfc812055b67445bd2e'}

API_SOURCE = "3d97e65b2f54a690a9383fb8a1e35c53f21b59a1f96ed378a4ba6a6a636a31d9"
API_STORAGE = "eb43a537626e945c43b7232a7b4005c637da99cc5e6d661e258e6561e80a7949"
API_BASE = "test-results/v0.8/photo-document-live-api-v1/"
LOCO_BASE = "evaluation-runs/v0.8/loco_combined_v1/"
OLD_BASE = "evaluation-runs/v0.7/public_paired_v1/"
BROWSER_BASE = "test-results/browser/photo-document-live-v08/"
SYNTHETIC_BROWSER_BASE = "test-results/browser/photo-document-v08/"
VIDEO_BASE = "output/demo/v0.7/public-photo-edit-01/"
VIDEO_LABEL = "v0.7历史图库流程，未覆盖v0.8新入口 / v0.7 과거 공개사진 흐름; v0.8 신규 진입 미포함"
PRIMARY = {"report": ".pdf", "technical": ".pdf", "slides": ".pptx", "source": ".zip"}
# No arbitrary attachment role. A new role requires reviewed code, not a plan loophole.
FIXED = {
    "report_sources": "output/report/v0.8-preview/SOURCE_EVIDENCE.json",
    "report_qa": "output/report/v0.8-preview/QA.json",
    "slides_qa": "test-results/v0.8-slides-preview-qa-v1.json",
    "backend_receipt": "test-results/v0.8-photo-document-backend-v2.json",
    "reference_live_receipt": "test-results/v0.8/reference-live-api-v1/receipt.json",
    "delivery_update_plan": "docs/v0.8/DELIVERY_UPDATE_PLAN.md",
    "contributions_v07": "docs/v0.7/CONTEST_PERIOD_CONTRIBUTIONS.md",
    "category_semantics": "docs/v0.8/SCREWS_CATEGORY_SEMANTICS_REVIEW.md",
    "official_rules": "docs/v0.7/OFFICIAL_RULE_CHECK_20261002.txt",
    "readme": "README.md", "index": "docs/v0.8/EXPERIMENT_INDEX.md",
    "guide": "docs/v0.8/PHOTO_DOCUMENT_GUIDE_KO_ZH.md",
    "contributions": "docs/v0.8/CONTEST_PERIOD_CONTRIBUTIONS.md",
    "contribution_diff": "docs/v0.8/CONTRIBUTION_DIFF_FROM_SEALED_V07.json",
    "loco_result": "docs/v0.8/LOCO_COMBINED_RESULT.md",
    "loco_decision": "docs/v0.8/LOCO_COMBINED_DECISION.json",
    "loco_freeze": "docs/v0.8/loco_combined_freeze_v1/freeze.json",
    "loco_selection": "docs/v0.8/loco_combined_method_selection_v1.json",
    "loco_audit": "test-results/v0.8-loco-combined-independent-audit-v2.json",
    "loco_failure": "test-results/v0.8-loco-combined-independent-audit-v1.json",
    "loco_repair": "test-results/v0.8-loco-combined-audit-repair-v2.json",
    "loco_run": LOCO_BASE + "run.json", "loco_analysis": LOCO_BASE + "analysis.json",
    "loco_predictions": LOCO_BASE + "predictions.json",
    "old51_run": OLD_BASE + "run.json", "old51_analysis": OLD_BASE + "analysis.json",
    "old51_freeze": "docs/v0.7/public_paired_freeze_v1/freeze.json",
    "old51_audit": "test-results/v0.7/public-paired-audit-v1.json",
    "api_receipt": API_BASE + "receipt.json", "api_plan": API_BASE + "plan.json",
    "api_observer_r1": API_BASE + "observer-r1.json", "api_observer_r2": API_BASE + "observer-r2.json",
    "api_source_before": API_BASE + "source-before.json", "api_source_after": API_BASE + "source-after.json",
    "api_zip": API_BASE + "evidence.zip",
    "api_model_receipt": API_BASE + "model-full-sha256.json",
    "browser_receipt": BROWSER_BASE + "browser-receipt.json",
    "browser_download_receipt": BROWSER_BASE + "download-verification.json",
    "browser_ko": BROWSER_BASE + "r2-ko.jpg", "browser_zh": BROWSER_BASE + "reviews-zh.jpg",
    "tests_xml": "test-results/v0.8-preview-full-v1.xml",
    "tests_log": "test-results/v0.8-preview-full-v1.log",
    "ruff_log": "test-results/v0.8-preview-full-ruff-v1.log",
    "loco_license": "third_party/datasets/MVTec_LOCO_license.txt",
    "screws_license": "third_party/datasets/MVTec_Screws_README_v1.0.txt",
}
OPTIONAL = {"historical_video": VIDEO_BASE + "KitGuard_v07_public_photo_walkthrough.mp4",
            "historical_video_receipt": VIDEO_BASE + "video_receipt.json",
            "synthetic_browser_receipt": SYNTHETIC_BROWSER_BASE + "browser-receipt.json",
            "synthetic_browser_addendum": SYNTHETIC_BROWSER_BASE + "browser-receipt-addendum.json"}
REQUIRED = set(FIXED) | set(PRIMARY) | {"source_smoke"}
MAX_SMALL = 16 * 1024**2
MAX_TOTAL = 512 * 1024**2
RESERVED = {"START_HERE.html", "PLAN.json", "BUILD_MANIFEST.json", "SHA256.json", "SHA256.json.sha256"}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def read(path):
    return json.loads(path.read_bytes())


def safe_name(value):
    need(isinstance(value, str) and value and "\\" not in value and "\x00" not in value,
         "Require a nonempty POSIX relative path")
    parts = value.split("/")
    need(not value.startswith("/") and all(p not in {"", ".", ".."} for p in parts), "Unsafe relative path")
    return PurePosixPath(value)


def local(root, value, *, must_exist=True):
    relative = safe_name(value)
    p = root.joinpath(*relative.parts)
    need(not any(q.is_symlink() for q in (p, *p.parents) if q == root or root in q.parents),
         "Symlink path is forbidden")
    need(p.resolve().is_relative_to(root), "Path escapes project root")
    if must_exist:
        need(p.is_file(), f"Missing regular artifact: {value}")
    return p


def validate_plan(plan, root):
    need(set(plan) == {"schema", "version", "preview", "output_directory", "output_zip", "files"},
         "Unexpected/missing plan field; no directory scans or implicit attachments")
    need(plan["schema"] == SCHEMA and plan["version"] == VERSION and plan["preview"] is True,
         "Only explicit 0.8.0.dev1 development preview supported")
    need(isinstance(plan["files"], list), "Files must be an explicit list")
    rows, paths, destinations = {}, {}, set()
    for row in plan["files"]:
        need(isinstance(row, dict) and set(row) == {"role", "path", "sha256", "destination", "title"},
             "Every file requires exactly role/path/sha256/destination/title")
        role = row["role"]
        need(role in REQUIRED | set(OPTIONAL) and role not in rows, "Unknown or duplicate role")
        need(isinstance(row["title"], str) and 1 <= len(row["title"]) <= 180, "Invalid artifact title")
        need(isinstance(row["sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", row["sha256"]),
             "Every file needs an actual SHA-256; no pending placeholder")
        destination = safe_name(row["destination"]).as_posix()
        need(destination.casefold() not in destinations and destination not in RESERVED,
             "Duplicate/reserved destination")
        prefix = "materials/" if role in PRIMARY or role == "historical_video" else "evidence/"
        need(destination.startswith(prefix), "Place primary materials in materials/ and receipts in evidence/")
        path = local(root, row["path"])
        expected = (FIXED | OPTIONAL).get(role)
        need(expected is None or row["path"] == expected, f"Unapproved source for {role}")
        if role in PRIMARY:
            need(row["path"].startswith("output/") and path.suffix == PRIMARY[role], "Primary type/location differs")
        limit = MAX_TOTAL if role in {"source", "historical_video"} else MAX_SMALL
        need(path.stat().st_size <= limit, "Artifact too large; no automatic truncation")
        need(path.suffix == Path(destination).suffix, "Destination must preserve artifact type")
        need(sha(path) == row["sha256"], f"Artifact SHA mismatch: {role}")
        rows[role], paths[role] = dict(row), path
        destinations.add(destination.casefold())
    need(REQUIRED <= rows.keys(), "Required evidence role missing")
    need(("historical_video" in rows) == ("historical_video_receipt" in rows), "Historical video requires its receipt")
    if "historical_video" in rows:
        need(rows["historical_video"]["title"] == VIDEO_LABEL, "Historical video label must disclose old scope")
    for role in ("synthetic_browser_receipt", "synthetic_browser_addendum"):
        if role in rows:
            need("synthetic" in rows[role]["title"].lower() and "合成" in rows[role]["title"],
                 "Auxiliary synthetic browser evidence must be explicitly labeled")
    need(paths["source_smoke"] == Path(str(paths["source"]) + ".verification.json"), "Source smoke must be matching sidecar")
    need(sum(p.stat().st_size for p in paths.values()) <= MAX_TOTAL, "Delivery exceeds bounded size")
    output = local(root, plan["output_directory"], must_exist=False)
    archive = local(root, plan["output_zip"], must_exist=False)
    need(plan["output_directory"].startswith("output/") and plan["output_zip"].startswith("output/")
         and "preview" in output.name and "preview" in archive.name and archive.suffix == ".zip",
         "Use explicit new output/ preview folder and ZIP")
    need(not archive.is_relative_to(output) and not output.is_relative_to(archive), "ZIP must be outside delivery directory")
    for p in (output, archive, Path(str(archive) + ".sha256")):
        need(not p.exists() and not p.is_symlink(), "Existing output is never overwritten")
    need(all(not p.is_relative_to(output) and p != archive for p in paths.values()), "Inputs overlap outputs")
    return rows, paths, output, archive


def loco_evidence(paths):
    run = read(paths["loco_run"])
    need(run.get("status") == "completed" and run.get("planned") == 24 and run.get("completed_attempts") == 24
         and run.get("final_integrity_verified") is True and run.get("source_changed") is False,
         "LOCO24 must be complete and unchanged")
    audit, analysis = read(paths["loco_audit"]), read(paths["loco_analysis"])
    need(sha(paths["loco_freeze"]) == LOCO_FREEZE and sha(paths["loco_audit"]) == LOCO_AUDIT,
         "Require exact registered LOCO freeze and successful independent audit")
    need(run["freeze_sha256"] == LOCO_FREEZE and audit.get("status") == "passed"
         and audit.get("completed_attempts") == 24 and audit.get("model_loaded_or_called") is False,
         "LOCO audit/run identity differs")
    for key in ("freeze", "run", "analysis", "predictions", "selection"):
        need(audit["evidence_sha256"][key] == sha(paths["loco_" + key]), "LOCO audited bytes changed")
    need(audit["independent_analysis"] == analysis, "LOCO independent/runner analysis differs")
    need(set(analysis["methods"]) == {"spatial_guarded"} and analysis["planned_cases"] == 24
         and analysis["planned_observations"] == 24, "LOCO scope differs")
    g = analysis["methods"]["spatial_guarded"]
    need(g["outcomes"] == {"C": 23, "W": 0, "U": 1, "E": 0, "N": 0} and g["planned"] == 24,
         "LOCO final full denominator/result differs")
    need(len(g["groups"]) == 4 and all(x["planned"] == 6 for x in g["groups"])
         and g["matched_order_applicable"] == 12 and g["matched_order_not_applicable"] == 12
         and g["matched_order_correct_ready"] == 11, "LOCO groups/count4 boundary differs")
    for key in ("all_four_panel", "source_supported_panel"):
        need(g[key]["planned_image_denominator"] == 24 and g[key]["observed_any_false_ready_images"] == 0
             and g[key]["unmeasured_images"] == 0, "LOCO risk denominator differs")
    normal = analysis["historical_normal16"]
    need(normal["exposed_nonconcurrent_not_pooled"] is True
         and normal["methods"]["spatial_guarded"]["planned"] == 16, "Historical normal16 must remain separate")
    pred = read(paths["loco_predictions"])
    need(len(pred) == 24 and len({p["case_id"] for p in pred}) == 24, "LOCO predictions incomplete")
    decision = read(paths["loco_decision"])
    need(decision["outcomes"] == g["outcomes"] and decision["production_unchanged"] is True
         and decision["automatic_promotion"] is False, "No production promotion authorized")
    bound = {e["path"]: e["sha256"] for e in decision["evidence"]}
    for role in ("loco_result", "loco_audit", "loco_failure", "loco_repair"):
        need(bound[FIXED[role]] == sha(paths[role]), "Decision evidence changed")
    return {"population": 24, "outcomes": g["outcomes"], "groups": g["groups"],
            "matched_ready": "11/12; other12 count4 N/A", "any_false_ready": "0/24 on both panels",
            "historical_normal16": "C14/W0/U2/E0/N0; exposed nonconcurrent, never pooled", "automatic_promotion": False}


def old51_evidence(paths, root):
    need(sha(local(root, "scripts/v07/build_delivery.py")) == OLD_BUILDER
         and sha(local(root, "scripts/v07/package_source.py")) == OLD_PACKAGER,
         "Sealed v0.7 validators changed")
    from scripts.v07.build_delivery import evaluation_evidence
    checks = {"evaluation_" + k: str(paths["old51_" + k].relative_to(root))
              for k in ("run", "analysis", "freeze", "audit")}
    result = evaluation_evidence(checks, root)
    need(read(paths["old51_analysis"])["modes"]["spatial_guarded"]["all"]["outcomes"]
         == {"C": 41, "W": 3, "U": 7, "E": 0, "N": 0}, "Retain original 51 errors and denominator")
    return {"photos": 51, "methods": 3, "observations": result["evaluation_attempts"],
            "guarded": {"C": 41, "W": 3, "U": 7, "E": 0, "N": 0}, "audit": "passed", "pooled_with_loco24": False}


def zip_members(archive, max_total=100 * 1024**2):
    infos = archive.infolist()
    need(len(infos) == len({i.filename for i in infos}) and len(infos) <= 3000, "Duplicate/excessive ZIP members")
    need(sum(i.file_size for i in infos) <= max_total, "Uncompressed ZIP exceeds limit")
    for info in infos:
        safe_name(info.filename)
        need(not info.is_dir() and not stat.S_ISLNK(info.external_attr >> 16), "Directory/symlink ZIP member forbidden")
    need(archive.testzip() is None, "ZIP CRC failure")
    return {i.filename for i in infos}


def api_evidence(paths):
    r, plan = read(paths["api_receipt"]), read(paths["api_plan"])
    need(r.get("status") == "passed" and r.get("inspect_attempts") == 2 and r.get("human_participants") == 0
         and r.get("model_calls_started") == 6 and r.get("model_calls_completed") == 6
         and r.get("source_unchanged") is True and r.get("replay_model_calls") == 0
         and r.get("physical_completion_rejections") == 2 and r.get("physical_completion") is False,
         "Require actual two-inspection/six-call/zero-human API receipt")
    need(plan["purpose"] == "real_mlx_photo_document_api_integration" and plan["source_sha256"] == API_SOURCE
         and plan["source_already_exposed"] is True and plan["human_participants"] == 0
         and plan["physical_completion"] is False and plan["accuracy_evaluation"] is False,
         "API source and engineering-only scope differ")
    need(sha(paths["api_source_before"]) == sha(paths["api_source_after"]) == r["source_after_sha256"]
         == plan["source_before_sha256"], "API before/after source receipt differs")
    need(sha(paths["api_model_receipt"]) == r["full_model_sha256_receipt"], "API model receipt differs")
    for revision in (1, 2):
        o = read(paths[f"api_observer_r{revision}"])
        calls = o["last_observation_attempt"]["generation_calls"]
        need(o["loaded"] is True and o["observation_mode"] == "spatial_guarded" and len(calls) == 3
             and all(c["status"] == "parsed" and c["model_call_started"] is True
                     and c["model_call_completed"] is True and c["raw_text"] for c in calls), "Actual observer calls missing")
    need(sha(paths["api_zip"]) == r["evidence_zip_sha256"], "API evidence ZIP differs")
    with ZipFile(paths["api_zip"]) as z:
        names = zip_members(z)
        payload = json.loads(z.read("SHA256.json"))
        e = json.loads(z.read("evidence.json"))
        photos = e["photos"]
        need(len(photos) == 2 and {p["revision"] for p in photos} == {1, 2}, "Exactly two API generations required")
        allowed = {"evidence.json", "OPEN_ME.html", "SHA256.json", "README.txt"}
        for p in photos:
            need(p["source_sha256"] == API_SOURCE and p["sha256"] == API_STORAGE
                 and p["physical_capture"] is False and p["archive_path"].startswith("photos/")
                 and p["archive_path"].endswith(".jpg"), "Only the exposed016 normalized photo is allowed")
            need(digest(z.read(p["archive_path"])) == API_STORAGE, "Unexpected image bytes in API ZIP")
            allowed.add(p["archive_path"])
        need(names == allowed and len(names) == 6, "No extra images/raw inputs/database in API ZIP")
        need({x["path"] for x in payload} == names - {"SHA256.json", "README.txt"}, "API manifest coverage differs")
        for x in payload:
            data = z.read(x["path"])
            need(digest(data) == x["sha256"] and len(data) == x["bytes"], "API payload hash mismatch")
        source = e["order"]["document_source"]
        need(source["source_sha256"] == API_SOURCE and source["verification"] == "user_declared_unverified"
             and source["physical_completion_allowed"] is False and "CC BY-NC-SA 4.0" in source["license_note"],
             "API source/license/digital-only statement lost")
        need(len(e["order"]["checks"]) == 2 and not e["order"]["completions"], "API engineering history differs")
    return {"real_observations": 2, "real_generation_calls": 6, "human_participants": 0,
            "engineering_only": True, "same_exposed_source": "LOCO train/good/016", "physical_completion": False}


def source_evidence(paths, root):
    from scripts.v07.package_source import (
        OMIT_PARTS,
        SOURCE_TREES,
        TEXT_SUFFIXES,
        TOP_FILES,
        public_samples,
        verify_archive,
    )
    from scripts.v08.package_source import EXTERNAL_PREFIXES, private_file, source_version
    from scripts.v08.package_source import REQUIRED as SOURCE_REQUIRED
    with ZipFile(paths["source"]) as z:
        zip_members(z)
        need(all(info.file_size <= MAX_SMALL for info in z.infolist()), "Source member exceeds16MiB limit")
    manifest = json.loads(verify_archive(paths["source"]))
    need(manifest.get("schema") == "kitguard.v08.source-package.v1" and manifest["version"] == VERSION
         and manifest.get("preview") is True and manifest.get("full_experiment_reproduction_self_contained") is False,
         "Source must be a bounded matching development preview")
    source_paths = {r["path"] for r in manifest["files"]}
    need(SOURCE_REQUIRED <= source_paths, "Required new source modules/guide missing")
    samples = manifest["public_samples"]
    expected_samples = public_samples(root)  # Reads only the three explicit licensed catalog demos.
    need(samples == expected_samples, "Source demo provenance differs from exact catalog allowlist")
    need(len(samples) == 3 and {x["sample_id"] for x in samples} == {"bag-revision", "small-part", "mixed-screws"}
         and all(x["license"] == "MVTec · CC BY-NC-SA 4.0" for x in samples), "Source demo allowlist differs")
    image_paths = {x["archive_path"] for x in samples}
    with ZipFile(paths["source"]) as z:
        need(source_version({name: z.read("KitGuard/" + name) for name in
                             ("pyproject.toml", "kitguard/__init__.py")}, True) == VERSION,
             "Actual archived version bytes differ from preview manifest")
        for x in samples:
            need(digest(z.read("KitGuard/" + x["archive_path"])) == x["source_sha256"], "Source demo hash mismatch")
        for record in manifest["files"]:
            p = PurePosixPath(record["path"])
            if "models" in p.parts:
                need(MODEL_NOTICE_SHA256.get(str(p)) == record["sha256"],
                     "Only14 registered exact model notice/metadata texts are allowed")
                need("\x00" not in z.read("KitGuard/" + str(p)).decode("utf-8"), "Model notice must remain UTF-8 text")
            need(not any(v in p.parts for v in ("data", "source_snapshot", "raw-generation", "normalized_inputs"))
                 and p.suffix.lower() not in {".sqlite3", ".sqlite", ".db", ".safetensors", ".pt", ".pem", ".key"}
                 and not p.name.startswith(".env"), "Private/model/raw snapshot payload in source ZIP")
            need(not private_file(Path(p)) and not any(v in OMIT_PARTS or v.endswith(".runtime-app-data") for v in p.parts)
                 and not any(str(p) == prefix or str(p).startswith(prefix + "/") for prefix in EXTERNAL_PREFIXES)
                 and not p.name.endswith((".sqlite3-wal", ".sqlite3-shm", ".db-wal", ".db-shm")),
                 "Private/runtime/explicitly external source path forbidden")
            in_tree = any(str(p).startswith(tree + "/") for tree in SOURCE_TREES)
            generated = {"SOURCE_PACKAGE.md", "EXTERNAL_ARTIFACT_INDEX.json", "启动检测验证台.command"}
            need(in_tree or str(p) in set(TOP_FILES) | generated | image_paths,
                 "Source member outside explicit package trees/top files/demo allowlist")
            allowed_text = p.suffix in TEXT_SUFFIXES | {".command"} or p.name in {".gitignore", "LICENSE", "NOTICE"}
            allowed_font = str(p).startswith("kitguard/static/") and p.suffix in {".woff", ".woff2"}
            need(allowed_text or allowed_font or str(p) in image_paths,
                 "Only source/text/static font and three declared demo raster images allowed")
        need("KitGuard/third_party/datasets/MVTec_LOCO_license.txt" in z.namelist()
             and "KitGuard/third_party/datasets/MVTec_Screws_README_v1.0.txt" in z.namelist(), "Source attribution missing")
    smoke = read(paths["source_smoke"])
    runtime = smoke.get("runtime", {})
    need(smoke.get("status") == "passed" and smoke.get("archive_sha256") == sha(paths["source"])
         and smoke.get("version") == VERSION and smoke.get("preview") is True
         and smoke.get("shell_syntax") == "passed" and runtime.get("version") == VERSION
         and runtime.get("synthetic") is True and runtime.get("model_calls") == 0
         and runtime.get("human_participants") == 0 and runtime.get("mlx_imported") is False
         and runtime.get("multipart_create") == 201 and runtime.get("root_replace") == 409
         and runtime.get("physical_complete") == 409 and runtime.get("zip_manifest_verified") is True,
         "Require matching successful extracted-source synthetic smoke")
    return {"version": VERSION, "preview": True, "demo_images": 3, "extracted_smoke": "passed",
            "smoke_scope": "Existing dependencies, synthetic HTTP; no clean-machine install or model call"}


def pdf_pages(path):
    try:
        from pypdf import PdfReader
    except ImportError:
        # Metadata parser only; no page rendering or image/model execution.
        result = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, check=True, timeout=15)
        matches = re.findall(r"^Pages:\s+(\d+)\s*$", result.stdout, re.MULTILINE)
        need(len(matches) == 1, "PDF page metadata unavailable")
        return int(matches[0])
    return len(PdfReader(path).pages)


def presentation_evidence(paths, root):
    report = pdf_pages(paths["report"])
    technical = pdf_pages(paths["technical"])
    need(1 <= report <= 5 and technical == 1, "Report <=5 pages; technical exactly1 page required")
    with ZipFile(paths["slides"]) as z:
        zip_members(z)
        tree = ET.fromstring(z.read("ppt/presentation.xml"))
        n = len(tree.findall(".//{http://schemas.openxmlformats.org/presentationml/2006/main}sldId"))
        need(1 <= n <= 8, "Presentation must have1..8 slides")
    qa = read(paths["report_qa"])
    need(qa["status"] == "passed" and qa["version"] == VERSION
         and qa["release_status"] == "development_preview_not_released_or_submitted"
         and qa["source_evidence_sha256"] == sha(paths["report_sources"]), "PDF QA/source-index binding differs")
    docs = {r["path"]: r for r in qa["pdf_documents"]}
    for role, pages in (("report", report), ("technical", technical)):
        record = docs.get(paths[role].relative_to(root).as_posix(), {})
        need(record.get("sha256") == sha(paths[role]) and record.get("pages") == pages, "PDF bytes/page QA mismatch")
    bundled = {p.relative_to(root).as_posix(): sha(p) for p in paths.values()}
    sources = read(paths["report_sources"])["sources"]
    need(set(sources) == {f"E{i}" for i in range(1, 18)}, "Report requires all17 cited source labels")
    for source in sources.values():
        need(bundled.get(source["path"]) == source["sha256"], "Every PDF cited source must be copied and hash-bound")
    slides_qa = read(paths["slides_qa"])
    need(slides_qa["status"] == "passed" and slides_qa["preview"] is True and slides_qa["version"] == VERSION
         and slides_qa["slide_count"] == n and slides_qa["output"]["sha256"] == sha(paths["slides"])
         and slides_qa["output"]["path"] == paths["slides"].relative_to(root).as_posix()
         and slides_qa["visual_qa"]["all_final_slides_rendered_and_individually_viewed"] is True,
         "PPT bytes/pages/visual QA receipt mismatch")
    return {"report_pages": report, "technical_pages": technical, "slides": n,
            "pdf_cited_sources_copied": len(sources),
            "visual_qa": "Author QA receipts bound to exact delivered files; no new rendering by delivery builder"}


def engineering_evidence(paths):
    cases = ET.parse(paths["tests_xml"]).getroot().findall(".//testcase")
    need(len(cases) == 1530 and all(not any(c.find(t) is not None for t in ("failure", "error", "skipped")) for c in cases),
         "Require the full1530-pass snapshot; not a claim about later builder tests")
    need("1530 passed, 2 warnings in 42.49s" in paths["tests_log"].read_text(), "Full test log differs")
    need(paths["ruff_log"].read_text().strip() == "All checks passed!", "Ruff snapshot failed")
    browser = read(paths["browser_receipt"])
    scope = browser["browser_scope"]
    need(browser["schema"] == "kitguard.v08.photo-document-live-browser.v1"
         and browser["status"] == "passed_read_only_display_and_download"
         and browser["human_participants"] == 0 and browser["saved_order_unchanged"] is True
         and browser["production_source_changed_since_real_api_run"] == [] and browser["limitations"],
         "Require real-API-history read-only browser scope and limitations")
    need(scope["http_request_methods_observed"] == ["GET"] and scope["http_request_count"] == 31
         and scope["get_only_service_enforced"] is True and scope["additional_model_calls"] == 0
         and scope["new_review_or_mutation_requests"] == 0 and scope["mlx_imported"] is False
         and scope["actual_zip_download"] is True, "Browser must be31 GET/zero new model or mutation")
    need(browser["prior_real_api_run"]["receipt_sha256"] == sha(paths["api_receipt"])
         and browser["order_id"] == read(paths["api_receipt"])["order_id"], "Browser/API receipt binding differs")
    for role in ("browser_ko", "browser_zh", "browser_download_receipt"):
        need(browser["artifacts_sha256"][FIXED[role]] == sha(paths[role]), "Browser screenshot/download not bound")
    download = read(paths["browser_download_receipt"])
    need(download["order_equals_original_api_export"] is True and download["checks"] == 2
         and download["public_reviews"] == 2 and download["public_replays"] == 1
         and download["completions"] == 0 and download["all_reviews_engineering_agent_zero_humans"] is True,
         "Downloaded browser history differs from real API export")
    need(download["zip_sha256"] == browser["artifacts_sha256"][BROWSER_BASE + "browser-download-evidence.zip"],
         "Actual download receipt does not bind browser ZIP")
    return {"full_test_snapshot_passed": 1530, "warnings": 2, "ruff": "passed",
            "later_builder_contracts_not_in_this_count": True,
            "browser": "Actual Chrome read-only display/download of prior real API history;31 GET,0 new model calls,0 humans; upload/file:// limitations retained"}


def contribution_evidence(paths, root):
    record = read(paths["contribution_diff"])
    need(record["schema"] == "kitguard.v08.core-diff-from-sealed-v07.v1" and record["current_version"] == VERSION
         and record["baseline_is_contest_start_snapshot"] is False
         and record["eligibility_authorization_not_evidenced"] is True, "Contribution comparison scope differs")
    need(record["counts"] == {"added": 2, "modified": 21, "removed": 0, "unchanged": 35}
         and len(record["files"]) == 58 and len({r["path"] for r in record["files"]}) == 58,
         "Core58 comparison denominator differs")
    baseline = local(root, record["baseline"])
    need(sha(baseline) == record["baseline_sha256"], "Original sealed source archive differs")
    with ZipFile(baseline) as before, ZipFile(paths["source"]) as after:
        counts = {k: 0 for k in record["counts"]}
        for row in record["files"]:
            name = "KitGuard/" + safe_name(row["path"]).as_posix()
            old = digest(before.read(name)) if name in before.namelist() else None
            new = digest(after.read(name)) if name in after.namelist() else None
            status = "added" if old is None else "removed" if new is None else "unchanged" if old == new else "modified"
            need(old == row["before_sha256"] and new == row["after_sha256"] and row["status"] == status,
                 "Contribution receipt differs from actual source ZIP versions")
            counts[status] += 1
        need(counts == record["counts"], "Contribution counts inconsistent")
    return {"core_paths": 58, "added": 2, "modified": 21, "unchanged": 35, "removed": 0,
            "baseline_is_contest_start_snapshot": False, "eligibility_authorization_not_evidenced": True}


def validate_evidence(paths, root):
    verified = {"loco24": loco_evidence(paths), "old51": old51_evidence(paths, root),
                "api": api_evidence(paths), "source": source_evidence(paths, root),
                "documents": presentation_evidence(paths, root), "engineering": engineering_evidence(paths),
                "contributions": contribution_evidence(paths, root)}
    if "historical_video" in paths:
        v = read(paths["historical_video_receipt"])
        need(v.get("status") == "encoded_and_decode_verified" and v["video"]["sha256"] == sha(paths["historical_video"])
             and v["verification"]["full_decode_passed"] is True
             and 0 < v["verification"]["duration_seconds"] <= 180, "Historical video receipt differs")
        verified["historical_video"] = {"label": VIDEO_LABEL, "seconds": v["verification"]["duration_seconds"]}
    return verified


def index_markup(rows):
    links = "\n".join(f'<li><a href="{quote(r["destination"])}">{html.escape(r["title"])}</a>'
                       f' <small>{html.escape(r["role"])}</small></li>' for r in rows)
    return f'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline';">
<title>KitGuard {VERSION} 개발 미리보기 / 开发预览</title>
<style>body{{font:17px/1.65 system-ui,sans-serif;max-width:980px;margin:40px auto;padding:0 24px;color:#173831;background:#f6f8f7}}h1{{line-height:1.2}}a{{color:#075b50}}li{{margin:.55em 0}}small{{color:#52635c}}aside{{border-left:4px solid #c58129;padding:12px 20px;background:#fff7e8}}</style>
<h1>KitGuard {VERSION}<br>개발 미리보기 · 本地开发预览</h1>
<p>압축을 푼 뒤 이 파일을 여세요. 모든 아래 링크는 이 폴더 안의 파일입니다. / 解压后打开本页，下面每份材料都有本地链接。</p>
<aside>제출·수상·상용 안전 인증을 뜻하지 않습니다. / 不代表已提交、获奖或商业安全认证。<br>
실제 사용자 0명. 디지털 검토는 실물 완료가 아닙니다. / 真人参与者为0，数字审查不等于实物完成。</aside>
<p>새 LOCO24: 23C / 0W / 1U / 0E / 0N. 저자 수량 라벨에서 추론한 동일 도메인 자료이며 12장의 count4 주문은 N/A입니다. 적용 가능한 일치 주문11/12, 주 오류-ready0/24. / 同域作者标签推导；全24与适用12分母分开。</p>
<p>과거51: G 41C / 3W / 7U. 과거 정상16은14C/2U. 새24와 합산하지 않습니다. / 旧51三错仍保留，正常16为历史非同期，不与新24合并。</p>
<p>새 자료 API는 이미 노출된016 사진, 실제2회 관찰·6회 생성·0명 참여. 브라우저는 저장된 실제 API 이력을 읽기 전용으로 표시·다운로드했습니다(31 GET, 신규 모델0). 업로드/file:// 제약은 원문에 보존됩니다. / 浏览器只读展示真实历史，31次GET、无新增推理；不是从浏览器上传开始的完整真人流程。</p>
<p>{html.escape(VIDEO_LABEL)}。 영상이 있으면 이 과거 범위에만 해당합니다. / 所附旧视频不证明新入口。</p>
<ul>{links}</ul>
<p><a href="PLAN.json">Explicit plan</a> · <a href="BUILD_MANIFEST.json">Build manifest</a> · <a href="SHA256.json">All-file SHA-256</a> · <a href="SHA256.json.sha256">Hash-index checksum</a></p>
<p>模型与完整研究输入不在交付包；源码含3张已许可演示图，真实API证据ZIP仅含旧016的两代归一图。哈希用于一致性检查，不是数字签名。</p></html>'''


def verify_bundle(folder, archive):
    hashes = read(folder / "SHA256.json")
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
    expected = {r["path"] for r in hashes} | {"SHA256.json", "SHA256.json.sha256"}
    need(actual == expected and len(hashes) == len({r["path"] for r in hashes}), "Folder hash coverage differs")
    for row in hashes:
        p = local(folder, row["path"])
        need(p.stat().st_size == row["bytes"] and sha(p) == row["sha256"], "Copied file hash mismatch")
    need((folder / "SHA256.json.sha256").read_text() == f'{sha(folder / "SHA256.json")}  SHA256.json\n', "Hash-index sidecar differs")
    with ZipFile(archive) as z:
        need(zip_members(z, MAX_TOTAL) == actual, "Delivery ZIP members differ from folder")
        for name in actual:
            need(digest(z.read(name)) == sha(folder / name), "ZIP byte mismatch")
    return {"status": "passed", "files": len(actual), "zip_sha256": sha(archive)}


def build(plan_path, root=ROOT):
    root = root.resolve()
    raw = plan_path.read_bytes()
    plan = json.loads(raw)
    rows, paths, output, archive = validate_plan(plan, root)
    verified = validate_evidence(paths, root)
    need(all(sha(paths[k]) == r["sha256"] for k, r in rows.items()), "Evidence changed during verification")
    # Exclusive creation preserves failed partial outputs; never removes an older delivery.
    output.mkdir(parents=True, exist_ok=False)
    records = []
    for role, row in rows.items():
        dest = output / row["destination"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        with paths[role].open("rb") as src, dest.open("xb") as target:
            for block in iter(lambda: src.read(1024**2), b""):
                target.write(block)
        need(sha(dest) == row["sha256"], "Input changed during copy")
        records.append({**row, "bytes": dest.stat().st_size})
    (output / "PLAN.json").write_bytes(raw)
    (output / "START_HERE.html").write_text(index_markup(records))
    manifest = {"schema": "kitguard.v08.delivery-manifest.v1", "version": VERSION, "preview": True,
                "built_at": datetime.now(UTC).isoformat(), "plan_sha256": digest(raw),
                "builder_sha256": sha(Path(__file__)), "files": records, "verification": verified,
                "published_or_submitted": False, "human_participants": 0, "automatic_promotion": False,
                "integrity_scope": "SHA256.json hashes all files except itself and its checksum sidecar; sidecar hashes that index. Outer ZIP checksum is external. No circular plan/output hashes."}
    (output / "BUILD_MANIFEST.json").write_bytes(encoded(manifest))
    hashes = [{"path": p.relative_to(output).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p)}
              for p in sorted(output.rglob("*")) if p.is_file()]
    (output / "SHA256.json").write_bytes(encoded(hashes))
    (output / "SHA256.json.sha256").write_text(f'{sha(output / "SHA256.json")}  SHA256.json\n')
    need(all(sha(paths[k]) == r["sha256"] for k, r in rows.items()), "Original evidence changed before sealing")
    archive.parent.mkdir(parents=True, exist_ok=True)
    with archive.open("xb") as stream, ZipFile(stream, "w", ZIP_DEFLATED) as z:
        for p in sorted(output.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(output).as_posix())
    result = verify_bundle(output, archive)
    with Path(str(archive) + ".sha256").open("x") as handle:
        handle.write(f'{result["zip_sha256"]}  {archive.name}\n')
    return {**result, "output_directory": str(output), "output_zip": str(archive), "preview": True,
            "published_or_submitted": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        _, paths, _, _ = validate_plan(read(args.plan), ROOT)
        print(json.dumps(validate_evidence(paths, ROOT), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(build(args.plan), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
