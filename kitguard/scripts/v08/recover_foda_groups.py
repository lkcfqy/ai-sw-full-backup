#!/usr/bin/env python3
"""Fetch bounded XML-only ZIP ranges, then join exact transformed annotations.

No images are fetched/decoded, no author code runs, and no ordering-based join is
allowed. All unknown or non-unique annotation matches remain unresolved.
"""
from __future__ import annotations

import hashlib
import json
import struct
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
import zlib
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from acquire_foda import DownloadForm, now, request
from inspect_foda_lineage import ORIGINAL_ID, get_range

BASE = Path("datasets/raw/fod-a-v2.1/lineage")
OUTPUT = Path("datasets/manifests/v0.8/fod-a-v2.1")
CHUNKS = BASE / "xml_range_chunks"
ARCHIVE = BASE.parent / "FODPascalVOCFormat-V.2.1.zip"
POLICY = {
    "name": "foda_exact_annotation_group_recovery_v1",
    "transport": "150 precomputed XML-only spans, HTTP 206 required, local XML CRC/size verified",
    "transform": "Apply author converter filename replacement/default field insertion and author resizer round(float*target/source,4); omit filename for canonical comparison",
    "join": "Exact full ordered XML element tree with normalized whitespace/numeric bbox fields; unique on both original and VOC sides only",
    "unknown": "Zero/multiple exact matches or shared VOC fingerprint: never infer group from ID or archive order",
    "not_proven": "Matching annotations establish annotation lineage, not unique physical object identity or photo licensing",
}


def xml_root(data):
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("DTD/entity XML is unsupported")
    return ET.fromstring(data)


def canonical(element):
    if element.tag == "filename":
        return None
    text = (element.text or "").strip()
    if element.tag in ("xmin", "xmax", "ymin", "ymax", "width", "height") and text:
        text = str(round(float(text), 4))
    children = [canonical(child) for child in element]
    return [element.tag, sorted(element.attrib.items()), text,
            [child for child in children if child is not None]]


def fingerprint(root):
    data = json.dumps(canonical(root), separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(data).hexdigest()


def transform_original(root):
    if root.find("object") is None:
        return None
    width, height = float(root.findtext("size/width")), float(root.findtext("size/height"))
    for obj in root.findall("object"):
        # Reimplement documented source transformations; never import/run it.
        for position, tag, value in ((2, "truncated", "0"), (3, "difficult", "0"),
                                     (4, "pose", "Unspecified")):
            if root.find(tag) is None:  # Exact condition in author's converter.
                child = ET.Element(tag)
                child.text = value
                obj.insert(position, child)
        for key in ("xmin", "xmax", "ymin", "ymax"):
            child = obj.find("bndbox/" + key)
            ratio = 300 / (width if key.startswith("x") else height)
            child.text = str(round(float(child.text) * ratio, 4))
    root.find("size/width").text = "300"
    root.find("size/height").text = "300"
    return root


def main():
    started = now()
    plan = json.loads((BASE / "original_xml_range_plan.json").read_text())
    spans = plan["ranges"]
    if len(spans) > 160 or sum(row["range_bytes"] for row in spans) > 16 * 1024 * 1024:
        raise ValueError("XML transport plan exceeds agreed metadata-only budget")
    if any(row["non_xml_payloads"] for row in spans):
        raise ValueError("A planned XML span contains non-XML payloads")
    CHUNKS.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "group_recovery_policy.json").write_text(json.dumps(POLICY, indent=2) + "\n")
    with request(f"https://drive.google.com/uc?export=download&id={ORIGINAL_ID}") as response:
        if "text/html" not in response.headers.get("Content-Type", ""):
            raise ValueError("Expected confirmation form, refusing full response body")
        page = response.read(128 * 1024)
    form = DownloadForm()
    form.feed(page.decode())
    if not form.action or urllib.parse.urlparse(form.action).hostname != "drive.usercontent.google.com" or form.inputs.get("id") != ORIGINAL_ID:
        raise ValueError("Unexpected author original ZIP download form")
    url = form.action + "?" + urllib.parse.urlencode(form.inputs)

    def fetch(index, span):
        target = CHUNKS / f"{index:03d}.bin"
        receipt_path = CHUNKS / f"{index:03d}.json"
        if target.exists() and receipt_path.exists():
            saved = json.loads(receipt_path.read_text())
            if hashlib.sha256(target.read_bytes()).hexdigest() != saved["transport"]["sha256"]:
                raise ValueError("Saved XML range hash differs")
            return saved
        data, receipt = get_range(url, f"bytes={span['start']}-{span['end_exclusive'] - 1}", span["range_bytes"])
        expected = f"bytes {span['start']}-{span['end_exclusive'] - 1}/8925497958"
        if data is None or receipt["content_range"] != expected or len(data) != span["range_bytes"]:
            raise ValueError("XML span response did not match its exact byte range")
        target.write_bytes(data)
        saved = {"xml_folder": span["xml_folder"], "local_path": str(target),
                 "start": span["start"], "transport": receipt}
        receipt_path.write_text(json.dumps(saved, indent=2) + "\n")
        return saved

    receipts = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(fetch, index, span) for index, span in enumerate(spans)]
        for future in as_completed(futures):
            receipts.append(future.result())
            if len(receipts) % 20 == 0:
                print(json.dumps({"xml_ranges_completed": len(receipts), "total": len(spans)}), flush=True)
    receipts_by_folder = {row["xml_folder"]: row for row in receipts}
    original_by_fingerprint = defaultdict(list)
    original_count, empty_count = 0, 0
    original_output = OUTPUT / "original_xml_fingerprints.jsonl"
    entries_by_folder = defaultdict(list)
    for entry in plan["xml_entries"]:
        entries_by_folder[str(Path(entry["path"]).parent)].append(entry)
    with original_output.open("w") as output:
        for folder, entries in entries_by_folder.items():
            receipt = receipts_by_folder[folder]
            chunk = Path(receipt["local_path"]).read_bytes()
            for entry in entries:
                start = entry["offset"] - receipt["start"]
                header = struct.unpack_from("<4s5H3I2H", chunk, start)
                if header[0] != b"PK\x03\x04":
                    raise ValueError("Bad ZIP local header")
                name_len, extra_len = header[9:11]
                raw_name = chunk[start + 30:start + 30 + name_len].decode("utf-8" if header[2] & 0x800 else "cp437")
                if raw_name != entry["path"]:
                    raise ValueError("Local XML path disagrees with central directory")
                data_start = start + 30 + name_len + extra_len
                compressed = chunk[data_start:data_start + entry["compressed_bytes"]]
                if header[3] == 8:
                    raw = zlib.decompress(compressed, -15)
                elif header[3] == 0:
                    raw = compressed
                else:
                    raise ValueError("Unsupported XML ZIP compression")
                if len(raw) != entry["uncompressed_bytes"] or f"{zlib.crc32(raw):08x}" != entry["crc32"]:
                    raise ValueError("Original XML size/CRC mismatch")
                root = xml_root(raw)
                transformed = transform_original(root)
                digest = fingerprint(transformed) if transformed is not None else None
                record = {"original_xml_path": entry["path"], "source_directory": str(Path(entry["path"]).parent.parent),
                          "xml_sha256": hashlib.sha256(raw).hexdigest(), "transformed_fingerprint": digest}
                output.write(json.dumps(record, separators=(",", ":")) + "\n")
                original_count += 1
                if digest:
                    original_by_fingerprint[digest].append(record)
                else:
                    empty_count += 1
    voc_by_fingerprint = defaultdict(list)
    with zipfile.ZipFile(ARCHIVE) as archive:
        for name in archive.namelist():
            if name.endswith(".xml"):
                digest = fingerprint(xml_root(archive.read(name)))
                voc_by_fingerprint[digest].append(Path(name).stem)
    candidates = {json.loads(line)["image_id"] for line in (OUTPUT / "metadata_candidates.jsonl").open()}
    status_counts, candidate_status_counts = Counter(), Counter()
    recovered_group_counts, candidate_group_counts = Counter(), Counter()
    mapping_path = OUTPUT / "voc_original_group_mapping.jsonl"
    with mapping_path.open("w") as output:
        for digest, image_ids in sorted(voc_by_fingerprint.items()):
            originals = original_by_fingerprint.get(digest, [])
            status = ("unique_exact_annotation_match" if len(originals) == 1 and len(image_ids) == 1
                      else "unmatched" if not originals else "ambiguous")
            for identity in image_ids:
                group = originals[0]["source_directory"] if status == "unique_exact_annotation_match" else None
                record = {"voc_image_id": identity, "fingerprint": digest, "status": status,
                          "matching_original_count": len(originals), "same_fingerprint_voc_count": len(image_ids),
                          "original_xml_path": originals[0]["original_xml_path"] if group else None,
                          "annotation_source_directory": group, "physical_object_identity": None,
                          "metadata_candidate": identity in candidates}
                output.write(json.dumps(record, separators=(",", ":")) + "\n")
                status_counts[status] += 1
                if group:
                    recovered_group_counts[group] += 1
                if identity in candidates:
                    candidate_status_counts[status] += 1
                    if group:
                        candidate_group_counts[group] += 1
    summary = {"started_at_utc": started, "completed_at_utc": now(), "policy": POLICY,
               "xml_range_count": len(receipts), "xml_range_bytes": sum(r["transport"]["bytes_read"] for r in receipts),
               "original_xml_count": original_count, "original_empty_annotations": empty_count,
               "voc_status_counts": dict(status_counts), "candidate_status_counts": dict(candidate_status_counts),
               "recovered_annotation_source_directories": dict(sorted(recovered_group_counts.items())),
               "candidate_recovered_annotation_source_directories": dict(sorted(candidate_group_counts.items())),
               "images_fetched_from_original_archive": 0, "image_pixels_decoded": False,
               "physical_object_identity_confirmed": False, "photo_license_resolved": False,
               "holdout_created": False, "outputs": []}
    for path in (original_output, mapping_path):
        summary["outputs"].append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                  "bytes": path.stat().st_size})
    (OUTPUT / "group_recovery_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({key: summary[key] for key in ("xml_range_count", "xml_range_bytes", "original_xml_count", "original_empty_annotations", "voc_status_counts", "candidate_status_counts")}, indent=2))


if __name__ == "__main__":
    main()
