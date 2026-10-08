"""Download only preselected MANTA class archives; inspect tar headers, never image pixels."""
from __future__ import annotations

import hashlib
import json
import os
import tarfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from urllib.request import Request, urlopen

ROOT = Path("datasets/raw/manta-identity-v1")
DEST = Path("datasets/manifests/v0.8/manta-identity-v1")


def now():
    return datetime.now(UTC).isoformat()


def write(path, value):
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download(info):
    destination = ROOT / info["name"]
    part = destination.with_suffix(destination.suffix + ".partial")
    receipt_path = ROOT / (info["name"] + ".acquisition.json")
    if destination.exists() or part.exists() or receipt_path.exists():
        raise FileExistsError(f"Refuse to overwrite prior acquisition: {destination}")
    receipt = {"schema": "kitguard.v08.manta-identity.download.v1", "started_at_utc": now(),
               "file_metadata": info, "requested_url": info["download_url"], "status": "started"}
    total, digest, md5 = 0, hashlib.sha256(), hashlib.md5()
    try:
        req = Request(info["download_url"], headers={"User-Agent": "KitGuard local research acquisition"})
        with urlopen(req, timeout=90) as response, part.open("xb") as stream:
            receipt.update(http_status=response.status,
                           response_headers={k: v for k, v in response.headers.items()
                                             if k.lower() in {"content-length", "content-type", "etag", "last-modified"}})
            if response.status != 200:
                raise ValueError("Full archive response must be 200")
            declared = response.headers.get("Content-Length")
            if declared is not None and int(declared) != info["size"]:
                raise ValueError("Response Content-Length differs from official file size")
            last_report = time.monotonic()
            while block := response.read(1024 * 1024):
                total += len(block)
                if total > info["size"]:
                    raise ValueError("Response exceeds preselected official file size")
                digest.update(block)
                md5.update(block)
                stream.write(block)
                if time.monotonic() - last_report >= 15:
                    print(json.dumps({"file": info["name"], "bytes": total, "expected": info["size"]}), flush=True)
                    last_report = time.monotonic()
            stream.flush()
            os.fsync(stream.fileno())
        receipt.update(bytes=total, sha256=digest.hexdigest(), md5=md5.hexdigest(),
                       size_matches=total == info["size"],
                       computed_md5_matches=md5.hexdigest() == info["computed_md5"],
                       supplied_md5_matches=md5.hexdigest() == info["supplied_md5"])
        if not all(receipt[k] for k in ("size_matches", "computed_md5_matches", "supplied_md5_matches")):
            raise ValueError("Official size/MD5 validation failed; partial file preserved")
        if destination.exists():
            raise FileExistsError(destination)
        part.rename(destination)
        receipt.update(status="verified", path=str(destination), completed_at_utc=now())
        write(receipt_path, receipt)
        print(json.dumps({"file": info["name"], "status": "verified", "bytes": total}), flush=True)
        return receipt
    except Exception as error:
        receipt.update(status="failed", bytes_received=total, sha256_received=digest.hexdigest(),
                       md5_received=md5.hexdigest(), error=f"{type(error).__name__}: {error}", completed_at_utc=now())
        if not receipt_path.exists():
            write(receipt_path, receipt)
        raise


def metadata(receipt):
    source = Path(receipt["path"])
    kind = receipt["file_metadata"]["name"].removesuffix(".tar.gz")
    output = DEST / (kind + "_archive_entries.jsonl")
    counts, prefixes, images, text_metadata = Counter(), Counter(), [], []
    unsafe, symlinks, duplicate_names = [], [], []
    seen = set()
    uncompressed = 0
    with tarfile.open(source, "r|gz") as archive, output.open("x", encoding="utf-8") as records:
        for member in archive:
            path = PurePosixPath(member.name)
            is_unsafe = path.is_absolute() or ".." in path.parts or "\\" in member.name
            if is_unsafe:
                unsafe.append(member.name)
            if member.issym() or member.islnk():
                symlinks.append({"path": member.name, "linkname": member.linkname})
            if member.name in seen:
                duplicate_names.append(member.name)
            seen.add(member.name)
            entry_type = "file" if member.isfile() else "directory" if member.isdir() else "other"
            counts[entry_type] += 1
            suffix = path.suffix.lower()
            record = {"path": member.name, "type": entry_type, "bytes": member.size,
                      "mtime": member.mtime, "linkname": member.linkname or None}
            records.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            if member.isfile():
                uncompressed += member.size
                prefixes[str(path.parent)] += 1
                counts["suffix:" + suffix] += 1
                if suffix in {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}:
                    images.append(member.name)
                if suffix in {".json", ".jsonl", ".csv", ".txt", ".md", ".yaml", ".yml", ".xml"}:
                    text_metadata.append({"path": member.name, "bytes": member.size})
            # No image payload is opened; tar streaming skips/decompresses bytes only.
    result = {"archive": receipt["path"], "archive_sha256": receipt["sha256"], "class_name": kind,
              "entry_manifest": {"path": str(output), "sha256": sha(output)},
              "entries": dict(counts), "uncompressed_file_bytes": uncompressed,
              "parent_directory_file_counts": dict(sorted(prefixes.items())),
              "unsafe_paths": unsafe, "links": symlinks, "duplicate_names": duplicate_names,
              "text_metadata_entries": text_metadata,
              "image_paths_count": len(images), "image_path_examples": images[:5],
              "image_payloads_decoded": False, "images_viewed": False,
              "authoritative_physical_object_group_ids": None,
              "group_status": "Path labels/record identifiers only; physical-object/session identity not inferred",
              "multiview_status": "Author describes five viewpoints per record; no image inspection or view splitting here"}
    write(DEST / (kind + "_archive_summary.json"), result)
    print(json.dumps({"class": kind, "metadata_only": True, "entry_counts": dict(counts)}), flush=True)
    return result


def main():
    selection = json.loads((ROOT / "selection.json").read_text())
    files = selection["selected_files"]
    expected_washer = min((selection["candidate_files"][n] for n in
                          ("red_washer.tar.gz", "yellow_green_washer.tar.gz")), key=lambda x: (x["size"], x["name"]))
    if files != [selection["candidate_files"]["nut.tar.gz"], expected_washer]:
        raise ValueError("Selection differs from fixed file-size-only rule")
    if sum(x["size"] for x in files) > 3_000_000_000:
        raise ValueError("Combined download exceeds authorized 3GB")
    DEST.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=2) as executor:
        downloads = list(executor.map(download, files))
    summaries = [metadata(receipt) for receipt in downloads]
    write(DEST / "source_manifest.json", {"schema": "kitguard.v08.manta-identity.source.v1", "created_at_utc": now(),
          "selection": {"path": str(ROOT / "selection.json"), "sha256": sha(ROOT / "selection.json")},
          "downloads": downloads, "archive_metadata": summaries,
          "license_status": "Author dataset CC BY-NC-SA 4.0 / non-commercial; conflicting Figshare CC BY4.0 retained",
          "usage_scope": "Local research acquisition only; no image publication or contest/commercial redistribution claim",
          "new_independent_holdout": False, "model_called": False, "training_performed": False,
          "images_decoded": False, "images_viewed": False, "archives_extracted": False,
          "script_sha256": sha(Path(__file__))})


if __name__ == "__main__":
    main()
