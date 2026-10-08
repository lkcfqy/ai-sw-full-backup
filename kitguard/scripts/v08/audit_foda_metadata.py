#!/usr/bin/env python3
"""Audit FOD-A VOC archive labels/ZIP metadata without decoding any image."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path, PurePosixPath

ATOMIC = frozenset(("Bolt", "Nut", "Washer"))
COMPOUND = frozenset(("BoltWasher", "BoltNutSet"))


def file_hash(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=Path("datasets/raw/fod-a-v2.1/FODPascalVOCFormat-V.2.1.zip"))
    parser.add_argument("--output", type=Path, default=Path("datasets/manifests/v0.8/fod-a-v2.1"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    labels_path = args.output / "annotation_metadata.jsonl"
    candidate_path = args.output / "metadata_candidates.jsonl"
    zip_manifest_path = args.output / "zip_file_metadata.jsonl"
    class_objects, class_images, folders, sources, attributes = (Counter() for _ in range(5))
    dimensions, count_distribution, combinations, validity, flags = (Counter() for _ in range(5))
    candidates_by_class, candidates_by_count, candidates_by_signature = (Counter() for _ in range(3))
    candidate_ids, all_ids, no_target, compound_ids = [], [], [], []
    crc_groups = defaultdict(list)
    with zipfile.ZipFile(args.archive) as archive, labels_path.open("w") as output, candidate_path.open("w") as selected:
        entries = archive.infolist()
        files = [entry for entry in entries if not entry.is_dir()]
        with zip_manifest_path.open("w") as metadata_output:
            for entry in files:
                metadata_output.write(json.dumps({"path": entry.filename,
                    "uncompressed_bytes": entry.file_size, "compressed_bytes": entry.compress_size,
                    "crc32": f"{entry.CRC:08x}", "zip_datetime": entry.date_time},
                    ensure_ascii=False, separators=(",", ":")) + "\n")
        names = [entry.filename for entry in files]
        name_set = set(names)
        xml_names = sorted(name for name in names if name.endswith(".xml"))
        image_entries = [entry for entry in files if Path(entry.filename).suffix.lower() in (".jpg", ".jpeg", ".png")]
        image_stems = {Path(entry.filename).stem for entry in image_entries}
        other_names = [name for name in names if Path(name).suffix.lower() not in (".xml", ".jpg", ".jpeg", ".png")]
        for entry in image_entries:
            crc_groups[(entry.file_size, entry.CRC)].append(Path(entry.filename).stem)
        split_lists = {}
        for name in names:
            if name.endswith(("/test.txt", "/trainval.txt")):
                split_lists[Path(name).stem] = archive.read(name).decode("utf-8-sig").split()
        categorization_name = next(name for name in names if name.endswith("FOD_categorization_annotations.csv"))
        category_rows = list(csv.DictReader(io.StringIO(archive.read(categorization_name).decode("utf-8-sig"))))
        category_counts = Counter(row["File"] for row in category_rows)
        categories = {row["File"]: row for row in category_rows}
        for name in xml_names:
            raw = archive.read(name)
            if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
                raise ValueError(f"Unsupported XML entity/DTD in {name}")
            root = ET.fromstring(raw)
            identity = Path(name).stem
            all_ids.append(identity)
            width, height = float(root.findtext("size/width")), float(root.findtext("size/height"))
            folder, filename = root.findtext("folder"), root.findtext("filename")
            source = {element.tag: element.text for element in root.findall("source/*")}
            folders[str(folder)] += 1
            sources[json.dumps(source, sort_keys=True)] += 1
            dimensions[f"{width:g}x{height:g}"] += 1
            problems = []
            if identity not in image_stems:
                problems.append("missing_image")
            if filename != identity + ".jpg":
                problems.append("filename_mismatch")
            objects = []
            for element in root.findall("object"):
                label = element.findtext("name")
                box = [float(element.findtext("bndbox/" + key)) for key in ("xmin", "ymin", "xmax", "ymax")]
                if not all(math.isfinite(v) for v in box) or not (0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height):
                    problems.append("invalid_bbox")
                object_flags = {key: element.findtext(key) for key in ("occluded", "truncated", "difficult")}
                for key, value in object_flags.items():
                    flags[f"{key}={value}"] += 1
                attrs = {item.findtext("name"): item.findtext("value") for item in element.findall("attributes/attribute")}
                attributes.update(attrs.keys())
                objects.append({"name": label, "bbox": box, "flags": object_flags, "attributes": attrs})
            counts = Counter(item["name"] for item in objects)
            class_objects.update(counts)
            class_images.update(counts.keys())
            count_distribution[len(objects)] += 1
            signature = "+".join(sorted(counts)) or "EMPTY"
            combinations[signature] += 1
            validity.update(set(problems))
            if not set(counts) & ATOMIC:
                no_target.append(identity)
            if set(counts) & COMPOUND:
                compound_ids.append(identity)
            passes_count = 1 <= len(objects) <= 12 and max(counts.values(), default=0) <= 3
            only_atomic = bool(counts) and set(counts) <= ATOMIC
            flags_clear = all(all(value == "0" for value in item["flags"].values()) for item in objects)
            eligible = only_atomic and passes_count and not problems and flags_clear
            record = {"image_id": identity, "xml_path": name,
                      "xml_sha256": hashlib.sha256(raw).hexdigest(), "filename": filename,
                      "folder": folder, "source": source, "size": [width, height],
                      "objects": objects, "counts": dict(counts), "problems": problems,
                      "weather_light": categories.get(filename),
                      "metadata_candidate": eligible, "authoritative_source_family": None}
            output.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            if eligible:
                candidate_ids.append(identity)
                candidates_by_class.update(counts.keys())
                candidates_by_count[len(objects)] += 1
                candidates_by_signature[signature] += 1
                selected.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        ids = set(all_ids)
        split_sets = {key: set(value) for key, value in split_lists.items()}
        train, test = split_sets.get("trainval", set()), split_sets.get("test", set())
        # This quantifies neighboring numeric IDs crossing the supplied split;
        # numeric adjacency is not declared to prove a shared original video.
        numeric_ids = sorted(int(value) for value in ids)
        adjacent_cross_split = sum(
            1 for left, right in pairwise(numeric_ids) if right == left + 1
            and ((f"{left:06d}" in train and f"{right:06d}" in test)
                 or (f"{left:06d}" in test and f"{right:06d}" in train))
        )
        duplicate_crc = [values for values in crc_groups.values() if len(values) > 1]
        summary = {
            "dataset": "FOD-A VOC v2.1", "audited_at_utc": datetime.now(UTC).isoformat(),
            "archive_path": str(args.archive), "archive_bytes": args.archive.stat().st_size,
            "archive_sha256": file_hash(args.archive),
            "status": "metadata_only_not_adopted_not_split_not_evaluated",
            "image_pixels_decoded": False, "images_viewed": False, "model_inference_performed": False,
            "zip": {"entry_count": len(entries), "file_count": len(files),
                    "uncompressed_bytes": sum(entry.file_size for entry in files),
                    "duplicate_entry_names": len(names) - len(name_set),
                    "unsafe_names": [name for name in names if PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts],
                    "annotation_files": len(xml_names), "image_files": len(image_entries),
                    "other_files": other_names,
                    "license_named_entries": [name for name in names if any(term in Path(name).name.lower() for term in ("license", "licence", "copyright", "readme", "terms"))]},
            "class_instance_counts": dict(sorted(class_objects.items())),
            "class_image_counts": dict(sorted(class_images.items())),
            "object_count_distribution": dict(sorted(count_distribution.items())),
            "label_combinations": dict(sorted(combinations.items())),
            "dimensions": dict(dimensions), "xml_folders": dict(folders), "xml_sources": dict(sources),
            "attribute_name_counts": dict(attributes), "object_flags": dict(flags),
            "validity_problem_image_counts": dict(validity),
            "missing_annotations": sorted(image_stems - ids),
            "categorization": {"rows": len(category_rows), "unique_filenames": len(category_counts),
                               "duplicate_filenames": {key: value for key, value in category_counts.items() if value > 1},
                               "missing_from_annotations": sorted(set(category_counts) - {value + ".jpg" for value in ids})},
            "provided_splits": {key: {"rows": len(value), "unique": len(set(value)),
                                       "duplicate_ids": {identity: count for identity, count in Counter(value).items() if count > 1},
                                       "unknown_ids": sorted(set(value) - ids)} for key, value in split_lists.items()},
            "split_overlap_ids": sorted(train & test), "missing_from_both_splits": sorted(ids - train - test),
            "adjacent_numeric_id_pairs_crossing_split": adjacent_cross_split,
            "zip_crc_size_matching_image_groups": duplicate_crc,
            "crc_note": "CRC+size equality is a duplicate lead, not cryptographic or perceptual proof; image bytes were not individually decoded or hashed",
            "metadata_candidates": {
                "definition": "All annotated objects belong to exact Bolt/Nut/Washer; 1<=total<=12 and each class<=3; matching image/XML; finite in-bounds positive boxes; all occluded/truncated/difficult flags exactly 0",
                "count": len(candidate_ids), "class_positive_image_counts": dict(candidates_by_class),
                "total_count_distribution": dict(candidates_by_count), "label_combinations": dict(candidates_by_signature),
                "compound_class_image_count_excluded": len(compound_ids),
                "independent_video_or_object_count": None,
                "limitations": ["Annotation completeness is not a visual fact verified by this metadata audit",
                                "No bracket positive class; three atomic classes permit at most nine objects under the <=3 constraint",
                                "Screw and all compound/other classes excluded without remapping",
                                "Numeric IDs, shared track_id, weather and light do not establish original video identity"]},
            "source_family": {"authoritative_mapping_available": False,
                              "reason": "VOC numeric IDs with generic folder/source fields and no original-video mapping in archive; inspect reported fields before use",
                              "near_duplicate_visual_check_performed": False},
        }
    summary["outputs"] = [{"path": str(path), "bytes": path.stat().st_size, "sha256": file_hash(path)}
                          for path in (labels_path, candidate_path, zip_manifest_path)]
    summary_path = args.output / "audit_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"summary": str(summary_path), "annotations": len(all_ids),
                      "candidates": len(candidate_ids), "classes": dict(class_objects)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
