#!/usr/bin/env python3
"""Recompute XML-only range plan from saved ZIP64 central-directory metadata."""
import json
import struct
from collections import defaultdict
from pathlib import Path

base = Path("datasets/raw/fod-a-v2.1/lineage")
data = (base / "original_zip_central_directory.bin").read_bytes()
central_offset = json.loads((base / "inspection.json").read_text())["original_archive"]["central_directory_offset"]
rows, position = [], 0
while position < len(data):
    fields = struct.unpack_from("<4s6H3I5H2I", data, position)
    if fields[0] != b"PK\x01\x02":
        raise ValueError("Invalid central directory signature")
    name_size, extra_size, comment_size = fields[10:13]
    name = data[position + 46:position + 46 + name_size].decode("utf-8" if fields[3] & 0x800 else "cp437")
    extra = data[position + 46 + name_size:position + 46 + name_size + extra_size]
    size, compressed, offset = fields[9], fields[8], fields[16]
    extra_position = 0
    while extra_position + 4 <= len(extra):
        tag, length = struct.unpack_from("<HH", extra, extra_position)
        payload = extra[extra_position + 4:extra_position + 4 + length]
        extra_position += 4 + length
        if tag == 1:
            cursor = 0
            if size == 0xFFFFFFFF:
                size = struct.unpack_from("<Q", payload, cursor)[0]
                cursor += 8
            if compressed == 0xFFFFFFFF:
                compressed = struct.unpack_from("<Q", payload, cursor)[0]
                cursor += 8
            if offset == 0xFFFFFFFF:
                offset = struct.unpack_from("<Q", payload, cursor)[0]
    rows.append({"path": name, "offset": offset, "compressed_bytes": compressed,
                 "uncompressed_bytes": size, "crc32": f"{fields[7]:08x}"})
    position += 46 + name_size + extra_size + comment_size
rows.sort(key=lambda row: row["offset"])
groups = defaultdict(list)
for index, row in enumerate(rows):
    row["end_offset_exclusive"] = rows[index + 1]["offset"] if index + 1 < len(rows) else central_offset
    if row["path"].endswith(".xml"):
        groups[str(Path(row["path"]).parent)].append(row)
ranges = []
for folder, entries in groups.items():
    start, end = entries[0]["offset"], entries[-1]["end_offset_exclusive"]
    other = [row["path"] for row in rows if start <= row["offset"] < end
             and not row["path"].endswith((".xml", "/"))]
    ranges.append({"xml_folder": folder, "start": start, "end_exclusive": end,
                   "range_bytes": end - start, "xml_count": len(entries), "non_xml_payloads": other})
plan = {"ranges": ranges, "xml_entries": [row for row in rows if row["path"].endswith(".xml")]}
destination = base / "original_xml_range_plan.json"
if destination.exists():
    if json.loads(destination.read_text()) != plan:
        raise ValueError("Computed plan differs from retained original; refusing overwrite")
    print("Existing XML range plan independently reconstructed exactly.")
else:
    destination.write_text(json.dumps(plan, indent=2) + "\n")
print(json.dumps({"ranges": len(ranges), "bytes": sum(row["range_bytes"] for row in ranges),
                  "xml_count": len(plan["xml_entries"]), "non_xml_payloads": sum(len(row["non_xml_payloads"]) for row in ranges)}))
