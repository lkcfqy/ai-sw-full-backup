"""Summarize verified MANTA archive path metadata; never read image payloads."""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

ROOT = Path("datasets/manifests/v0.8/manta-identity-v1")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    manifest_path = ROOT / "source_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    output = ROOT / "record_metadata.jsonl"
    summaries = []
    with output.open("x", encoding="utf-8") as stream:
        for archive in manifest["archive_metadata"]:
            entry_ref = archive["entry_manifest"]
            path = Path(entry_ref["path"])
            if sha(path) != entry_ref["sha256"]:
                raise ValueError("Archive entry metadata changed")
            entries = [json.loads(line) for line in path.read_text().splitlines()]
            masks, images, unexpected = {}, [], []
            for entry in entries:
                if entry["type"] != "file":
                    continue
                p = PurePosixPath(entry["path"])
                if len(p.parts) != 4 or p.parts[0] != archive["class_name"] or p.suffix != ".png":
                    unexpected.append(entry["path"])
                    continue
                _, split, label, filename = p.parts
                if split == "ground_truth":
                    if (label, filename) in masks:
                        raise ValueError("Duplicate mask path")
                    masks[label, filename] = entry["path"]
                elif split in ("train", "test"):
                    images.append((entry, split, label, filename, p.stem))
                else:
                    unexpected.append(entry["path"])
            counts, stems = Counter(), defaultdict(list)
            paired_masks = set()
            for entry, split, label, filename, stem in images:
                mask = masks.get((label, filename))
                if mask:
                    paired_masks.add(mask)
                counts[f"{split}/{label}"] += 1
                stems[stem].append(entry["path"])
                record = {"class_name": archive["class_name"], "archive_sha256": archive["archive_sha256"],
                          "image_path": entry["path"], "image_bytes": entry["bytes"], "split": split,
                          "author_condition_label": label, "record_id_from_filename": stem,
                          "paired_anomaly_mask_path": mask,
                          "five_view_record_key": f"{archive['class_name']}/{stem}",
                          "five_view_basis": "Author dataset description; image payload not inspected",
                          "physical_object_id": None, "capture_session_id": None,
                          "view_order": None, "view_axis": None,
                          "group_status": "File record identifier only; physical independence unconfirmed"}
                stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            summaries.append({"class_name": archive["class_name"], "image_records": len(images),
                              "records_by_split_and_condition": dict(sorted(counts.items())),
                              "mask_records": len(masks), "paired_masks": len(paired_masks),
                              "unpaired_mask_paths": sorted(set(masks.values()) - paired_masks),
                              "repeated_record_ids": {k: v for k, v in stems.items() if len(v) > 1},
                              "unexpected_file_paths": unexpected,
                              "normal_is_author_label": "good; no image verification performed"})
    summary = {"schema": "kitguard.v08.manta-identity.records.v1", "created_at_utc": datetime.now(UTC).isoformat(),
               "source_manifest": {"path": str(manifest_path), "sha256": sha(manifest_path)},
               "record_metadata": {"path": str(output), "sha256": sha(output)}, "classes": summaries,
               "images_decoded_or_viewed": False, "model_called": False, "new_independent_holdout": False,
               "limitations": ["Record IDs and official train/test directories do not certify physical-object/session independence.",
                               "Anomaly masks are not instance counting boxes.",
                               "Five-view association comes from author description; axis and view order remain unverified.",
                               "No image-level cryptographic/perceptual duplicate comparison performed."]}
    with (ROOT / "record_summary.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"record_summary": str(ROOT / "record_summary.json"), "classes": summaries}, ensure_ascii=False))


if __name__ == "__main__":
    main()
