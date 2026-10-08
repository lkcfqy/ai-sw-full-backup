#!/usr/bin/env python3
"""Acquire the author-linked FOD-A VOC v2.1 archive for metadata inspection.

This script does not execute downloaded code, decode images, extract the archive,
or authorize adoption of its photographs. Python standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import html.parser
import json
import urllib.parse
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path

FILE_ID = "1RdErcq8PGRXZUOGauaACkQG44T-QyZ4x"
AUTHOR_REPO = "https://github.com/FOD-UNOmaha/FOD-data"
DOWNLOAD_PAGE = f"https://drive.google.com/file/d/{FILE_ID}/view?usp=sharing"
ARCHIVE_NAME = "FODPascalVOCFormat-V.2.1.zip"
MAX_BYTES = 800 * 1024 * 1024


def now() -> str:
    return datetime.now(UTC).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def request(url: str):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "KitGuard-dataset-metadata/0.8"}),
        timeout=60,
    )


class DownloadForm(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.action = None
        self.inputs = {}
        self.in_form = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "form" and values.get("id") == "download-form":
            self.in_form = True
            self.action = values.get("action")
        if self.in_form and tag == "input" and values.get("type") == "hidden":
            self.inputs[values["name"]] = values.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form":
            self.in_form = False


def download(directory: Path) -> dict:
    start = now()
    url = f"https://drive.google.com/uc?export=download&id={FILE_ID}"
    response = request(url)
    if "text/html" in response.headers.get("Content-Type", ""):
        landing = response.read(128 * 1024)
        response.close()
        (directory / "download_landing.html").write_bytes(landing)
        form = DownloadForm()
        form.feed(landing.decode("utf-8"))
        if not form.action or urllib.parse.urlparse(form.action).hostname != "drive.usercontent.google.com":
            raise RuntimeError("Expected public Google Drive download confirmation form")
        if form.inputs.get("id") != FILE_ID:
            raise RuntimeError("Download form file ID changed")
        response = request(form.action + "?" + urllib.parse.urlencode(form.inputs))
    if "text/html" in response.headers.get("Content-Type", ""):
        raise RuntimeError("Drive returned HTML instead of the archive")
    headers = {key: response.headers.get(key) for key in (
        "Content-Type", "Content-Length", "Content-Disposition", "Last-Modified", "ETag"
    ) if response.headers.get(key) is not None}
    partial = directory / (ARCHIVE_NAME + ".partial")
    digest = hashlib.sha256()
    size = 0
    next_progress = 32 * 1024 * 1024
    with response, partial.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_BYTES:
                raise RuntimeError("Archive exceeds the explicit 800 MiB acquisition limit")
            output.write(chunk)
            digest.update(chunk)
            if size >= next_progress:
                print(json.dumps({"downloaded_bytes": size}), flush=True)
                next_progress += 32 * 1024 * 1024
    if not zipfile.is_zipfile(partial):
        raise RuntimeError("Downloaded content is not a ZIP archive")
    archive = directory / ARCHIVE_NAME
    partial.replace(archive)
    return {"started_at_utc": start, "completed_at_utc": now(), "bytes": size,
            "sha256": digest.hexdigest(), "response_headers": headers,
            "public_archive_checksum": None,
            "public_checksum_status": "Not found in author README, LICENSE, or public download landing page"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("datasets/raw/fod-a-v2.1"))
    args = parser.parse_args()
    directory = args.output.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    metadata_path = directory / "acquisition.json"
    archive = directory / ARCHIVE_NAME
    if archive.exists():
        if not metadata_path.exists():
            raise RuntimeError("Existing archive has no provenance receipt; refusing to overwrite")
        metadata = json.loads(metadata_path.read_text())
        if sha256(archive) != metadata["archive"]["sha256"]:
            raise RuntimeError("Existing archive differs from the saved acquisition hash")
        print(json.dumps({"status": "existing_archive_hash_verified", "archive": str(archive)}))
        return
    with request("https://api.github.com/repos/FOD-UNOmaha/FOD-data/commits/main") as response:
        commit = json.load(response)["sha"]
    snapshots = []
    for name in ("README.md", "LICENSE"):
        url = f"https://raw.githubusercontent.com/FOD-UNOmaha/FOD-data/{commit}/{name}"
        with request(url) as response:
            data = response.read(1024 * 1024)
        target = directory / ("author_" + name)
        target.write_bytes(data)
        snapshots.append({"path": target.name, "source_url": url, "bytes": len(data),
                          "sha256": hashlib.sha256(data).hexdigest()})
    metadata = {"dataset": "FOD-A", "version": "2.1", "format": "Pascal VOC",
                "purpose": "metadata and license inspection only; not adopted for training/evaluation",
                "source_repository": AUTHOR_REPO, "source_commit": commit,
                "author_download_page": DOWNLOAD_PAGE, "claimed_archive_size": "412 mb",
                "claimed_resolution": "300x300", "source_snapshots": snapshots,
                "license_status": "repository MIT; external photo archive terms require inspection",
                "archive": download(directory), "archive_filename": ARCHIVE_NAME,
                "images_viewed": False, "image_pixels_decoded": False,
                "model_inference_performed": False, "external_code_executed": False}
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": "acquired_for_inspection", "receipt": str(metadata_path),
                      "bytes": metadata["archive"]["bytes"], "sha256": metadata["archive"]["sha256"]}))


if __name__ == "__main__":
    main()
