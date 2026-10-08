"""Validate and seal the five contest deliverables and reviewer evidence.

This builds local files only. It never signs, uploads, or submits a Google Form.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/submission-final-20261005"
TESTS = ROOT / "test-results/submission-final-20261005"
MATERIALS = (
    "KitGuard_report_5p.pdf",
    "KitGuard_agent_1p.pdf",
    "KitGuard_source.zip",
    "KitGuard_demo_ko.mp4",
    "KitGuard_presentation_9slides.pptx",
)
SUPPLEMENTAL = (
    "KitGuard_presentation_9slides.pdf",
    "SOURCE_AI_DISCLOSURE_KO.txt",
    "SOURCE_AI_DISCLOSURE_KO.md",
    "PRESENTATION_SCRIPT_KO.md",
    "PRIOR_ART_POSITION_KO_ZH.md",
    "README_KO.txt",
    "START_HERE.html",
    "KitGuard_execution_evidence.zip",
    "KitGuard_final_runtime_evidence.zip",
    "FINAL_ACCEPTANCE.json",
)


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def record(path: Path) -> dict:
    return {"path": path.name, "bytes": path.stat().st_size, "sha256": sha(path)}


def junit(path: Path) -> dict:
    suites = ET.parse(path).getroot()
    if suites.tag == "testsuites":
        elements = list(suites)
    else:
        elements = [suites]
    totals = {
        key: sum(int(s.attrib.get(key, 0)) for s in elements)
        for key in ("tests", "failures", "errors", "skipped")
    }
    if totals["tests"] < 1 or totals["failures"] or totals["errors"]:
        raise ValueError(f"Failed or empty JUnit: {path}")
    return totals


def verify_source(path: Path) -> dict:
    with ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError("Source CRC failed")
        manifest = json.loads(archive.read("KitGuard/SOURCE_MANIFEST.json"))
        if manifest["version"] != "0.9.0.dev4":
            raise ValueError("Source version mismatch")
        rows = manifest["files"]
        for row in rows:
            payload = archive.read("KitGuard/" + row["path"])
            if len(payload) != row["bytes"] or hashlib.sha256(payload).hexdigest() != row["sha256"]:
                raise ValueError("Source payload mismatch: " + row["path"])
        for name in archive.namelist():
            p = Path(name)
            if p.is_absolute() or ".." in p.parts:
                raise ValueError("Unsafe archive path")
            if p.suffix in {".sqlite", ".sqlite3", ".db", ".pem", ".key", ".safetensors"}:
                raise ValueError("Private database/key/model included: " + name)
            if p.name.startswith(".env"):
                raise ValueError("Environment secrets included")
    return {"payload_files": len(rows), "crc": "passed", "payload_sha256": "passed"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    if args.archive.exists():
        raise SystemExit("Preserve a sealed archive; use a new revision filename")
    for name in MATERIALS:
        if not (OUT / name).is_file():
            raise ValueError("Required material missing: " + name)
    pages = [len(PdfReader(OUT / name).pages) for name in MATERIALS[:2]]
    if not 1 <= pages[0] <= 5 or pages[1] != 1:
        raise ValueError("Report/technical explanation page limit failed")
    with ZipFile(OUT / MATERIALS[4]) as archive:
        if archive.testzip() is not None:
            raise ValueError("Presentation CRC failed")
        slides = sum(
            n.startswith("ppt/slides/slide") and n.endswith(".xml")
            and "/_rels/" not in n for n in archive.namelist()
        )
    if not 1 <= slides <= 10:
        raise ValueError("Slide count exceeds official limit")
    video = json.loads((OUT / "video-build.json").read_text())
    if not 0 < video["duration_seconds"] <= 180 or video["sha256"] != sha(OUT / MATERIALS[3]):
        raise ValueError("Video duration/hash failed")
    source = verify_source(OUT / MATERIALS[2])
    if len(PdfReader(OUT / "KitGuard_presentation_9slides.pdf").pages) != slides:
        raise ValueError("Presentation PDF/PPTX page mismatch")
    acceptance = json.loads((OUT / "FINAL_ACCEPTANCE.json").read_text())
    if acceptance["status"] != "passed":
        raise ValueError("Final acceptance not passed")
    if acceptance["source_acceptance"]["archive_sha256"] != sha(OUT / MATERIALS[2]):
        raise ValueError("Source acceptance not bound to this ZIP")
    live = acceptance["live_runtime"]
    if live["status"] != "completed" or live["real_mlx_checks"] != 4:
        raise ValueError("Actual local workflow did not complete")
    core = acceptance["observer_frozen"]
    for relative, expected in core.items():
        if sha(ROOT / relative) != expected:
            raise ValueError("Frozen observer changed: " + relative)
    chosen = [OUT / name for name in (*MATERIALS, *SUPPLEMENTAL) if (OUT / name).is_file()]
    required_extra = {"SOURCE_AI_DISCLOSURE_KO.txt", "README_KO.txt", "START_HERE.html", "FINAL_ACCEPTANCE.json"}
    if required_extra - {p.name for p in chosen}:
        raise ValueError("Reviewer instructions/disclosure missing")
    manifest = {
        "schema": "kitguard.contest-submission.20261005.v1",
        "code_version": "0.9.0.dev4",
        "material_revision": "2026-10-05",
        "sealed_at_utc": datetime.now(UTC).isoformat(),
        "team": "해피",
        "members": ["남청청", "이개심"],
        "division": "일반부",
        "track": "업무혁신·생산성 향상 AI Agent",
        "pages": pages,
        "slides": slides,
        "video_seconds": video["duration_seconds"],
        "source_integrity": source,
        "human_participants": 0,
        "physical_completions": 0,
        "new_image_accuracy_denominator": 0,
        "submission_status": "Prepared locally; user submits through the official final form",
        "qualification_receipt": None,
        "submission_receipt": None,
        "five_materials": list(MATERIALS),
        "files": [record(path) for path in chosen],
        "checksum_scope": "Integrity only; no authenticity, official score, acceptance or rank claim",
    }
    (OUT / "SUBMISSION_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    args.archive.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(args.archive, "w", ZIP_DEFLATED, compresslevel=9) as archive:
        for path in chosen:
            archive.write(path, "KitGuard/" + path.name)
        archive.write(OUT / "SUBMISSION_MANIFEST.json", "KitGuard/SUBMISSION_MANIFEST.json")
    with ZipFile(args.archive) as archive:
        if archive.testzip() is not None:
            raise ValueError("Outer ZIP CRC failed")
        for row in manifest["files"]:
            payload = archive.read("KitGuard/" + row["path"])
            if hashlib.sha256(payload).hexdigest() != row["sha256"]:
                raise ValueError("Outer payload mismatch")
    digest = sha(args.archive)
    args.archive.with_suffix(".zip.sha256").write_text(f"{digest}  {args.archive.name}\n")
    receipt = {
        "archive": str(args.archive.resolve()),
        "bytes": args.archive.stat().st_size,
        "sha256": digest,
        "crc": "passed",
        "bound_payloads": len(chosen),
        "status": "passed",
    }
    args.archive.with_suffix(".zip.verification.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    main()
