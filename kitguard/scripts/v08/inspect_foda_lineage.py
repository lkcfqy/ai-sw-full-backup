#!/usr/bin/env python3
"""Read author tool source and optional original ZIP directory only; execute none."""
from __future__ import annotations

import hashlib
import io
import json
import struct
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from acquire_foda import DownloadForm, now, request

COMMIT = "a22e5bd5c314f4c7b5d5c5f01224db453c62248f"
ORIGINAL_ID = "1lLBJXXaQCWaFa-1MeLAANPpSwMhCJqGh"
OUTPUT = Path("datasets/raw/fod-a-v2.1/lineage")
MAX_DIRECTORY = 32 * 1024 * 1024


def get_range(url, byte_range, limit):
    req = urllib.request.Request(url, headers={"Range": byte_range,
                                              "User-Agent": "KitGuard-dataset-metadata/0.8"})
    with urllib.request.urlopen(req, timeout=60) as response:
        receipt = {"requested_range": byte_range, "status": response.status,
                   "content_range": response.headers.get("Content-Range"),
                   "content_length": response.headers.get("Content-Length"), "bytes_read": 0}
        if response.status != 206:
            # Do not consume a full-file body if the server ignores Range.
            return None, receipt
        size = response.headers.get("Content-Length")
        if size is not None and int(size) > limit:
            raise ValueError("Partial response larger than its metadata budget")
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError("Range body exceeded metadata budget")
        receipt["bytes_read"] = len(data)
        receipt["sha256"] = hashlib.sha256(data).hexdigest()
        return data, receipt


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    receipt = {"started_at_utc": now(), "source_commit": COMMIT,
               "external_code_executed": False, "image_pixels_decoded": False, "downloads": []}
    tree_url = f"https://api.github.com/repos/FOD-UNOmaha/FOD-data/git/trees/{COMMIT}?recursive=1"
    with request(tree_url) as response:
        tree = response.read(1024 * 1024)
    (OUTPUT / "author_repository_tree.json").write_bytes(tree)
    for relative in ("Tools/FODtoPascal/FODtoPASCAL-Version-1.2.zip",
                     "Tools/FODExpansionTool/FODExpansionTool.py"):
        url = f"https://raw.githubusercontent.com/FOD-UNOmaha/FOD-data/{COMMIT}/{relative}"
        with request(url) as response:
            data = response.read(1024 * 1024)
        target = OUTPUT / Path(relative).name
        target.write_bytes(data)
        receipt["downloads"].append({"url": url, "path": str(target), "bytes": len(data),
                                     "sha256": hashlib.sha256(data).hexdigest()})
        if relative.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                receipt["converter_zip_entries"] = archive.namelist()
                for name in archive.namelist():
                    if name.lower().endswith((".py", ".txt", ".md")):
                        text = archive.read(name)
                        destination = OUTPUT / ("converter_" + Path(name).name)
                        destination.write_bytes(text)
    landing_url = f"https://drive.google.com/uc?export=download&id={ORIGINAL_ID}"
    with request(landing_url) as response:
        if "text/html" not in response.headers.get("Content-Type", ""):
            receipt["original_archive"] = {"status": "no_HTML_confirmation_returned_body_not_read"}
            (OUTPUT / "inspection.json").write_text(json.dumps(receipt, indent=2) + "\n")
            return
        landing = response.read(128 * 1024)
    (OUTPUT / "original_download_landing.html").write_bytes(landing)
    form = DownloadForm()
    form.feed(landing.decode())
    if not form.action or urllib.parse.urlparse(form.action).hostname != "drive.usercontent.google.com" or form.inputs.get("id") != ORIGINAL_ID:
        raise ValueError("Unexpected original archive download form")
    url = form.action + "?" + urllib.parse.urlencode(form.inputs)
    tail, tail_receipt = get_range(url, "bytes=-65557", 65557)
    receipt["original_archive"] = {"source_page": f"https://drive.google.com/file/d/{ORIGINAL_ID}/view?usp=sharing",
                                  "tail_request": tail_receipt, "full_archive_downloaded": False}
    if tail is not None:
        (OUTPUT / "original_zip_tail.bin").write_bytes(tail)
        eocd = tail.rfind(b"PK\x05\x06")
        if eocd < 0:
            raise ValueError("No ZIP end-of-central-directory in the requested tail")
        fields = struct.unpack_from("<4s4H2IH", tail, eocd)
        count, central_size, central_offset = fields[4:7]
        if central_size == 0xFFFFFFFF or central_offset == 0xFFFFFFFF or count == 0xFFFF:
            zip64 = tail.rfind(b"PK\x06\x06", 0, eocd)
            if zip64 < 0:
                raise ValueError("ZIP64 end record not found in tail; stop without full download")
            count = struct.unpack_from("<Q", tail, zip64 + 32)[0]
            central_size, central_offset = struct.unpack_from("<QQ", tail, zip64 + 40)
        receipt["original_archive"].update({"central_directory_bytes": central_size,
                                             "central_directory_offset": central_offset,
                                             "central_directory_entry_count": count})
        if central_size > MAX_DIRECTORY:
            raise ValueError("Central directory exceeds 32 MiB metadata budget")
        directory, directory_receipt = get_range(url, f"bytes={central_offset}-{central_offset + central_size - 1}", central_size)
        receipt["original_archive"]["directory_request"] = directory_receipt
        if directory is not None:
            (OUTPUT / "original_zip_central_directory.bin").write_bytes(directory)
            rows, position = [], 0
            while position < len(directory):
                fields = struct.unpack_from("<4s6H3I5H2I", directory, position)
                if fields[0] != b"PK\x01\x02":
                    raise ValueError("Unexpected ZIP central directory signature")
                name_len, extra_len, comment_len = fields[10:13]
                filename = directory[position + 46:position + 46 + name_len].decode("utf-8" if fields[3] & 0x800 else "cp437")
                rows.append({"path": filename, "compressed_bytes_32bit": fields[8],
                             "uncompressed_bytes_32bit": fields[9], "crc32": f"{fields[7]:08x}"})
                position += 46 + name_len + extra_len + comment_len
            if len(rows) != count:
                raise ValueError("Central directory entry count mismatch")
            with (OUTPUT / "original_zip_file_metadata.jsonl").open("w") as output:
                for row in rows:
                    output.write(json.dumps(row, separators=(",", ":")) + "\n")
    receipt["completed_at_utc"] = now()
    (OUTPUT / "inspection.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
