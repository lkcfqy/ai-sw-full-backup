"""Package an inspectable source snapshot without weights, photos, databases or environments."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".cjs",
    ".mjs",
    ".html",
    ".css",
    ".svg",
    ".md",
    ".json",
    ".jsonl",
    ".toml",
    ".bib",
    ".txt",
    ".sh",
}
EXCLUDED = {"__pycache__", "node_modules", ".venv", ".pytest_cache", ".ruff_cache"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def collect():
    paths = {
        ROOT / name
        for name in (
            "README.md",
            "pyproject.toml",
            "requirements-lock.txt",
            "启动KitGuard.command",
            ".gitignore",
        )
    }
    for directory in ("kitguard", "scripts", "tests", "docs", "third_party"):
        for path in (ROOT / directory).rglob("*"):
            if (
                path.is_file()
                and not path.is_symlink()
                and (path.suffix in SUFFIXES or path.name in {"LICENSE", "NOTICE"})
                and not EXCLUDED.intersection(path.parts)
            ):
                paths.add(path)
    for directory in ("datasets/manifests", "evaluation-runs"):
        for path in (ROOT / directory).rglob("*"):
            if (
                path.is_file()
                and path.suffix in {".json", ".jsonl", ".py", ".toml"}
                and not EXCLUDED.intersection(path.parts)
            ):
                paths.add(path)
    # Preserve authored analytical content without shipping the plugin's runtime.
    report = ROOT / "reports/self-evaluation"
    for name in ("src/data.json", "src/theme.css", "AGENTS.md"):
        path = report / name
        if path.is_file():
            paths.add(path)
    for path in (report / "src/content").rglob("*"):
        if path.is_file() and not path.is_symlink() and path.suffix in SUFFIXES:
            paths.add(path)
    for path in (ROOT / "test-results").rglob("*"):
        if path.is_file() and (("audit" in path.parts and path.suffix in {".json", ".txt", ".md", ".log", ".py"}) or path.name in {
            "engineering-current.xml",
            "engineering-v03-final.xml",
            "engineering-v03-packaging.xml",
            "engineering-v04-final.xml",
            "engineering-v05-final.xml",
            "v05-backend-final.xml",
            "inspection-region-independent-review.xml",
            "v05-method-preservation.json",
            "engineering-study-export.json",
            "result.json",
            "browser-results.json",
            "browser-result.json",
            "offline-result.json",
            "visual-qa.json",
            "video-metadata.json",
            "QA_SUMMARY.md",
            "final-result.json",
            "archive-manifest.json",
        }):
            paths.add(path)
    # Preserve v0.4 HTTP receipts and recorder exports, excluding photos/databases.
    for directory in ("field-study-v04", "field-study-real-v04", "field-study-flow-review-v04",
                      "inspection-region-v05", "inspection-region-real-v05"):
        for path in (ROOT / "test-results/browser" / directory).rglob("*"):
            if (path.is_file() and not path.is_symlink() and path.suffix in SUFFIXES
                    and not EXCLUDED.intersection(path.parts)):
                paths.add(path)
    for path in (ROOT / "test-results/v05-api-scope-fixture").rglob("*"):
        if path.is_file() and not path.is_symlink() and path.suffix in SUFFIXES:
            paths.add(path)
    for path in (ROOT / "test-results/browser").glob("*/*"):
        if path.is_file() and not path.is_symlink() and path.suffix in {".py", ".cjs", ".mjs"}:
            paths.add(path)
    return sorted(paths)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Preserve the previous package; choose a new output name")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    records = []
    with ZipFile(args.output, "w", ZIP_DEFLATED, compresslevel=9) as archive:
        for path in collect():
            relative = path.relative_to(ROOT).as_posix()
            data = path.read_bytes()
            records.append({"path": relative, "bytes": len(data), "sha256": sha(data)})
            archive.write(path, f"KitGuard/{relative}")
        manifest = {
            "created_at": datetime.now(UTC).isoformat(),
            "actual_development_date": "2026-09-26–2026-09-27 Asia/Seoul",
            "submission_status": "Internal review snapshot; eligibility for pre-development assets unresolved",
            "excluded": [
                "model weights",
                "original and normalized photographs",
                "SQLite databases",
                "Python/node environments",
                "private registration documents",
                "Data plugin protected report runtime (offline rendered report delivered separately)",
            ],
            "sources_and_licenses": "docs/AI_AND_SOURCE_DISCLOSURE.md",
            "files": records,
        }
        archive.writestr(
            "KitGuard/SOURCE_MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        )
    with ZipFile(args.output) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(records) + 1
        for record in records:
            assert sha(archive.read(f"KitGuard/{record['path']}")) == record["sha256"]
    checksum = sha(args.output.read_bytes())
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(f"{checksum}  {args.output.name}\n")
    print(
        json.dumps(
            {
                "path": str(args.output.resolve()),
                "files": len(records),
                "bytes": args.output.stat().st_size,
                "sha256": checksum,
                "roundtrip_verified": True,
            }
        )
    )


if __name__ == "__main__":
    main()
