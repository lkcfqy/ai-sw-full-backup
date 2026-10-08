"""Build bounded source-group FOD-A development data; never run a model.

All candidate images are decoded only for integrity/duplicate checks. Only six
preselected training examples are exposed in a contact sheet. Held-back images
remain inside the archive and are not rendered or copied to training outputs.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import UTC, datetime
import hashlib
import io
import json
from pathlib import Path
import shutil
import zipfile

from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[2]
META = ROOT / "datasets/manifests/v0.8/fod-a-v2.1"
ARCHIVE = ROOT / "datasets/raw/fod-a-v2.1/FODPascalVOCFormat-V.2.1.zip"
ARCHIVE_SHA = "408af3ac5be8af399367a7a846c6bd720727391c2d89de17985321c27468dd87"
CLASSES = {"Bolt": 1, "Nut": 2, "Washer": 3}
SEED = "kitguard-foda-source-groups-20261002-v1"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def readlines(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def rank(kind, identity):
    return hashlib.sha256(f"{SEED}|{kind}|{identity}".encode()).hexdigest()


def verified_metadata(group_path):
    """Validate the metadata chain without opening the image archive."""
    grouping = json.loads(group_path.read_text())
    mapping_path = META / "voc_original_group_mapping.jsonl"
    candidate_path = META / "metadata_candidates.jsonl"
    expected_paths = (mapping_path, candidate_path, META / "group_recovery_summary.json")
    expected_names = {str(p.relative_to(ROOT)) for p in expected_paths}
    if set(grouping["source_sha256"]) != expected_names:
        raise ValueError("Unexpected grouping source manifest")
    for path in expected_paths:
        if sha(path) != grouping["source_sha256"][str(path.relative_to(ROOT))]:
            raise ValueError(f"Grouping source SHA-256 changed: {path.name}")
    mapping_rows = readlines(mapping_path)
    mappings = {r["voc_image_id"]: r for r in mapping_rows}
    if len(mappings) != len(mapping_rows):
        raise ValueError("Duplicate mapping IDs")
    candidates = readlines(candidate_path)
    if len({r["image_id"] for r in candidates}) != len(candidates):
        raise ValueError("Duplicate candidate IDs")
    if any(len(r["image_id"]) != 6 or not r["image_id"].isascii()
           or not r["image_id"].isdigit() for r in candidates):
        raise ValueError("Unexpected candidate ID")
    return grouping, mappings, candidates, mapping_path, candidate_path


def roles(groups):
    """Assign whole groups before image access; at least three groups per class."""
    assigned = {}
    for category in CLASSES:
        rows = [g for g in groups if g["author_class"] == category]
        if len(rows) < 3:
            raise ValueError(f"Need >=3 source groups for {category}; no frame-random fallback")
        for index, group in enumerate(sorted(rows, key=lambda g: rank("group", g["group_id"]))):
            gid = group["group_id"]
            role = "validation" if index == 0 else "held_back" if index == 1 else "train"
            if gid in assigned:
                raise ValueError("Repeated or cross-class group requires an explicit joint policy")
            assigned[gid] = role
    return assigned


def bounded_selection(rows, assigned):
    by_group = defaultdict(list)
    for row in rows:
        by_group[row["group_id"]].append(row)
    selected = []
    for gid, members in sorted(by_group.items()):
        limit = 50 if assigned[gid] == "train" else 12
        selected.extend(sorted(members, key=lambda r: rank("image", r["image_id"]))[:limit])
    return selected


def prepare(output, group_path):
    if output.exists():
        raise FileExistsError(f"Refuse to overwrite: {output}")
    # Artifact paths are repository-relative throughout the output protocol.
    output.relative_to(ROOT)
    grouping, mappings, candidates, mapping_path, candidate_path = verified_metadata(group_path)
    if sha(ARCHIVE) != ARCHIVE_SHA:
        raise ValueError("FOD archive changed")
    groups = grouping["groups"]
    assigned = roles(groups)
    directory_group = {}
    for group in groups:
        for directory in group["directories"]:
            if directory in directory_group:
                raise ValueError("Source directory assigned twice")
            directory_group[directory] = group
    rows, excluded = [], []
    for candidate in candidates:
        ident = candidate["image_id"]
        mapping = mappings[ident]
        if not candidate["metadata_candidate"] or not mapping["metadata_candidate"]:
            raise ValueError("Candidate/mapping eligibility mismatch")
        if mapping["status"] != "unique_exact_annotation_match":
            excluded.append({"image_id": ident, "reason": mapping["status"]})
            continue
        group = directory_group[mapping["annotation_source_directory"]]
        if len(candidate["objects"]) != 1 or candidate["objects"][0]["name"] != group["author_class"]:
            raise ValueError("Category/group mismatch")
        obj = candidate["objects"][0]
        if candidate["size"] != [300, 300] or candidate["counts"] != {obj["name"]: 1}:
            raise ValueError("Candidate size/count mismatch")
        expected_xml = f"FODPascalVOCFormat-V.2.1/VOC2007/Annotations/{ident}.xml"
        if candidate["xml_path"] != expected_xml or candidate["filename"] != ident + ".jpg":
            raise ValueError("Candidate archive path/ID mismatch")
        x0, y0, x1, y1 = obj["bbox"]
        if not (0 <= x0 < x1 <= 300 and 0 <= y0 < y1 <= 300):
            raise ValueError("Invalid author continuous-coordinate box")
        rows.append({"image_id": ident, "group_id": group["group_id"],
                     "protocol_role": assigned[group["group_id"]],
                     "author_category": obj["name"], "class_id": CLASSES[obj["name"]],
                     "box_xyxy": obj["bbox"], "annotation_xml_sha256": candidate["xml_sha256"],
                     "annotation_member_path": expected_xml,
                     "source_directory": mapping["annotation_source_directory"],
                     "original_xml_path": mapping["original_xml_path"],
                     "member_path": candidate["xml_path"].replace("/Annotations/", "/JPEGImages/")
                     .removesuffix(".xml") + ".jpg"})
    actual_counts = Counter(r["group_id"] for r in rows)
    if any(actual_counts[g["group_id"]] != g["candidate_count"] for g in groups):
        raise ValueError("Group candidate counts changed")
    directory_counts = Counter(r["source_directory"] for r in rows)
    if any(directory_counts[d] != count for g in groups
           for d, count in g["directory_candidate_counts"].items()):
        raise ValueError("Source directory candidate counts changed")
    if any(set(g["directories"]) != set(g["directory_candidate_counts"]) for g in groups):
        raise ValueError("Directory count membership mismatch")
    if sorted(r["image_id"] for r in excluded) != sorted(grouping["unknown"]["image_ids"]):
        raise ValueError("Unknown candidate membership changed")
    if len(rows) != grouping["summary"]["grouped_candidate_count"] or len(candidates) != grouping["summary"]["candidate_count"]:
        raise ValueError("Grouping summary count changed")
    selected = bounded_selection(rows, assigned)
    selected_ids = {r["image_id"] for r in selected}
    previews = []
    for category in CLASSES:
        previews.extend(sorted((r for r in selected if r["author_category"] == category
                                and r["protocol_role"] == "train"),
                               key=lambda r: rank("preview", r["image_id"]))[:2])
    preview_ids = {r["image_id"] for r in previews}
    output.mkdir(parents=True)
    write(output / "protocol.json", {
        "schema": "kitguard.v08.foda-grouped-development.v1", "created_at_utc": datetime.now(UTC).isoformat(),
        "seed": SEED, "group_roles": assigned, "group_rank": "SHA256(seed|group|group_id), per class",
        "role_rank": ["validation", "held_back", "remaining=train"],
        "sample_rank": "SHA256(seed|image|image_id), 50/train group, 12/other group",
        "preview_rank": "First two per class among selected train by SHA256(seed|preview|image_id)",
        "preview_ids": sorted(preview_ids), "archive_sha256": ARCHIVE_SHA,
        "sources": {str(p.relative_to(ROOT)): sha(p) for p in (group_path, candidate_path, mapping_path)},
        "script_sha256": sha(Path(__file__)), "independent_physical_objects": False,
        "license": "Photo terms unresolved; local research only, no redistribution authorization asserted",
        "bbox_interpretation": "Author floating xmin,ymin,xmax,ymax retained as continuous image coordinates",
        "failure_policy": "Preserve incomplete directory; no automatic retries, regrouping or replacement"})
    shutil.copyfile(__file__, output / Path(__file__).name)
    write(output / "selection_before_decode.json", selected)
    write(output / "excluded.json", excluded)
    hashes = defaultdict(list)
    raw_hashes = defaultdict(list)
    preview_images = {}
    with zipfile.ZipFile(ARCHIVE) as archive, (output / "integrity.jsonl").open("x") as integrity:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate ZIP member names")
        for row in rows:
            if hashlib.sha256(archive.read(row["annotation_member_path"])).hexdigest() != row["annotation_xml_sha256"]:
                raise ValueError(f"Annotation XML SHA-256 changed: {row['image_id']}")
            content = archive.read(row["member_path"])
            raw_sha = hashlib.sha256(content).hexdigest()
            with Image.open(io.BytesIO(content)) as image:
                if image.size != (300, 300) or image.format != "JPEG":
                    raise ValueError("Author dimensions/format mismatch")
                if image.getexif().get(274, 1) != 1:
                    raise ValueError("Nontrivial EXIF orientation requires a new coordinate policy")
                rgb = image.convert("RGB")
                pixel_sha = hashlib.sha256(b"300x300|RGB|" + rgb.tobytes()).hexdigest()
                if row["image_id"] in preview_ids:
                    preview_images[row["image_id"]] = rgb.copy()
            row.update(image_sha256=raw_sha, rgb_sha256=pixel_sha, image_size=[300, 300])
            hashes[pixel_sha].append(row)
            raw_hashes[raw_sha].append(row)
            integrity.write(json.dumps(row, separators=(",", ":")) + "\n")
            if row["image_id"] in selected_ids and row["protocol_role"] != "held_back":
                destination = output / "images" / row["protocol_role"] / (row["image_id"] + ".jpg")
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
                row["local_image"] = str(destination.relative_to(ROOT))
    duplicate_groups = [[{"image_id": r["image_id"], "group_id": r["group_id"],
                          "role": r["protocol_role"]} for r in rs] for rs in hashes.values() if len(rs) > 1]
    conflicts = [rs for rs in duplicate_groups if len({r["group_id"] for r in rs}) > 1]
    write(output / "duplicate_audit.json", {"decoded_groups": duplicate_groups,
          "raw_duplicate_groups": sum(len(rs) > 1 for rs in raw_hashes.values()),
          "cross_source_group_conflicts": conflicts, "near_duplicate_audit": "not performed"})
    if conflicts:
        raise ValueError("Exact duplicates cross source groups; preserve evidence and revise grouping explicitly")
    # The selected rows reference the same objects as the integrity list.
    for role in ("train", "validation", "held_back"):
        write(output / (role + ".json"), [r for r in selected if r["protocol_role"] == role])
    board = Image.new("RGB", (900, 660), "#eeeeee")
    draw = ImageDraw.Draw(board)
    for index, row in enumerate(previews):
        image = preview_images[row["image_id"]]
        ImageDraw.Draw(image).rectangle(tuple(row["box_xyxy"]), outline="red", width=2)
        x, y = (index % 3) * 300, (index // 3) * 330
        board.paste(ImageOps.contain(image, (300, 300)), (x, y + 30))
        draw.text((x + 5, y + 5), f'{row["image_id"]} {row["author_category"]} / TRAIN', fill="black")
    board.save(output / "development_preview.jpg", quality=95)
    write(output / "summary.json", {"completed_at_utc": datetime.now(UTC).isoformat(),
          "candidate_images": len(candidates), "grouped_decoded_images": len(rows),
          "excluded_ambiguous_images": len(excluded), "groups": len(groups),
          "selected": {role: dict(Counter(r["author_category"] for r in selected
                       if r["protocol_role"] == role)) for role in ("train", "validation", "held_back")},
          "per_group": {gid: {"role": assigned[gid], "available": actual_counts[gid],
                        "selected": sum(r["group_id"] == gid for r in selected)} for gid in assigned},
          "preview_ids": sorted(preview_ids), "all_images_decoded_for_integrity_only": True,
          "held_back_images_rendered_or_extracted": False, "near_duplicate_audit_performed": False,
          "model_called": False, "production_changed": False,
          "files": {str(p.relative_to(output)): sha(p) for p in sorted(output.rglob("*")) if p.is_file()}})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--groups", type=Path, default=META / "conservative_groups_v1.json")
    args = parser.parse_args()
    prepare(args.output.resolve(), args.groups.resolve())


if __name__ == "__main__":
    main()
