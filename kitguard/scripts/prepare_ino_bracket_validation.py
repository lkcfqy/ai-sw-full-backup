"""Derive one prespecified author-box view per InO source; never invent other-class truth."""

import argparse
import hashlib
import json
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

RULES = {
    "source_variant": "origin", "target_class": 0, "count_range": [1, 3],
    "target_bbox_min_short_side_px": 32, "margin_union_short_side_fraction": 0.10,
    "bbox_boundary_epsilon_normalized": 1e-6, "other_class_intersection_includes_touch": True,
    "full_image_if_only_target_labels": True, "one_case_per_source": True,
    "ground_truth": "Only author class 0 L-bracket count. Bolt/nut/washer are UNLABELED, not zero.",
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parse_rows(text):
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 5 or not fields[0].isdigit():
            raise ValueError("Expected author YOLO class and four numeric fields")
        class_id = int(fields[0])
        values = [float(x) for x in fields[1:]]
        if class_id not in range(10) or not all(math.isfinite(v) for v in values) or min(values[2:]) <= 0:
            raise ValueError("Invalid author class, finite geometry or positive area")
        x, y, w, h = values
        rows.append({"class_id": class_id, "xyxy": [x-w/2, y-h/2, x+w/2, y+h/2], "original_line": line})
    return rows


def choose_view(rows, width, height):
    if any(min(r["xyxy"][:2]) < -1e-6 or max(r["xyxy"][2:]) > 1+1e-6 for r in rows):
        return None, "author_bbox_outside_origin"
    targets = [r for r in rows if r["class_id"] == 0]
    if not targets:
        return None, "no_author_class0"
    if len(targets) > 3:
        return None, "author_class0_count_over_3"
    boxes = [{**r, "xyxy": [r["xyxy"][0]*width, r["xyxy"][1]*height,
                           r["xyxy"][2]*width, r["xyxy"][3]*height]} for r in rows]
    targets = [r["xyxy"] for r in boxes if r["class_id"] == 0]
    if any(min(b[2]-b[0], b[3]-b[1]) < 32 for b in targets):
        return None, "target_bbox_too_small"
    if len(targets) == len(rows):
        return {"kind": "full_image", "roi": [0, 0, width, height], "count": len(targets)}, None
    union = [min(b[0] for b in targets), min(b[1] for b in targets),
             max(b[2] for b in targets), max(b[3] for b in targets)]
    pad = .1 * min(union[2]-union[0], union[3]-union[1])
    roi = [math.floor(union[0]-pad), math.floor(union[1]-pad),
           math.ceil(union[2]+pad), math.ceil(union[3]+pad)]
    if roi[0] < 0 or roi[1] < 0 or roi[2] > width or roi[3] > height:
        return None, "roi_outside_origin"
    for row in boxes:
        b = row["xyxy"]
        if row["class_id"] != 0 and roi[0] <= b[2] and roi[2] >= b[0] and roi[1] <= b[3] and roi[3] >= b[1]:
            return None, "roi_touches_non0_author_bbox"
    return {"kind": "author_box_roi", "roi": roi, "count": len(targets)}, None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=Path("datasets"))
    parser.add_argument("--output-name", default="ino_l_bracket_external_v1")
    parser.add_argument("--independent-preview", type=Path, required=True)
    args = parser.parse_args()
    if not args.output_name.replace("_", "").isalnum():
        raise SystemExit("Output name must use letters/digits/underscore")
    root = args.dataset_root.resolve()
    source = root / "raw/ino-10-190"
    manifest_dir = root / "manifests/v0.4" / args.output_name
    derived_dir = root / "derived/v0.4" / args.output_name
    if manifest_dir.exists() or derived_dir.exists():
        raise SystemExit("Preserve previous preparation; use a new name")
    source_manifest = json.loads((source / "SOURCE_MANIFEST.json").read_text())
    if source_manifest["author_commit"] != "c733a3543157135c591cbe3f9de27e209964af63":
        raise ValueError("Unexpected author revision")
    for record in source_manifest["files"]:
        path = source / record["local_path"]
        if not path.resolve().is_relative_to(source) or path.stat().st_size != record["bytes"] or sha(path) != record["sha256"]:
            raise ValueError("Source byte mismatch: " + record["local_path"])
    labels = (source / "data/test_01_class.names").read_text().splitlines()
    assert labels[0] == "L-bracket" and len(labels) == 10
    preview = json.loads(args.independent_preview.read_text())
    preview_by_id = {p["source_id"]: p for p in preview["sources"]}
    paths = sorted((source / "data/origin").glob("*/*_color.txt"),
                   key=lambda p: (p.parent.name, int(p.stem.removesuffix("_color"))))
    assert len(paths) == len(preview_by_id) == 190
    records = []
    for annotation in paths:
        source_id = annotation.parent.name + "/" + annotation.stem.removesuffix("_color")
        image = annotation.with_suffix(".png")
        with Image.open(image) as opened:
            width, height = opened.size
        rows = parse_rows(annotation.read_text())
        selection, reason = choose_view(rows, width, height)
        independent = preview_by_id[source_id]
        assert bool(selection) == independent["eligible"], source_id
        if selection:
            assert selection["roi"] == independent["candidate_roi_xyxy"], source_id
        records.append({"source_id": source_id, "author_group": annotation.parent.name,
                        "annotation": str(annotation.relative_to(root)), "annotation_sha256": sha(annotation),
                        "source_image": str(image.relative_to(root)), "source_image_sha256": sha(image),
                        "source_dimensions": [width, height], "author_rows": rows,
                        "selection": selection, "excluded_reason": reason})
    eligible = [r for r in records if r["selection"]]
    assert len(eligible) == 20 and all(r["selection"]["count"] == 1 for r in eligible)
    manifest_dir.mkdir(parents=True)
    derived_dir.mkdir(parents=True)
    cases = []
    for row in eligible:
        selected = row["selection"]
        if selected["kind"] == "full_image":
            image = root / row["source_image"]
        else:
            image = derived_dir / (row["source_id"].replace("/", "_") + ".png")
            with Image.open(root / row["source_image"]) as opened:
                opened.convert("RGB").crop(selected["roi"]).save(image, format="PNG")
        cases.append({
            "id": "ino-l-bracket-" + row["source_id"].replace("/", "-"),
            "source_id": "ino-10-190:" + row["source_id"], "author_group": row["author_group"],
            "image": str(image.relative_to(root)), "sha256": sha(image), "view_kind": selected["kind"],
            "ground_truth": {"bracket": selected["count"]}, "unlabeled_categories": ["bolt", "nut", "washer"],
            "author_class_id": 0, "source_image": row["source_image"],
            "source_image_sha256": row["source_image_sha256"], "annotation": row["annotation"],
            "annotation_sha256": row["annotation_sha256"], "roi_xyxy": selected["roi"],
        })
    assert len({c["sha256"] for c in cases}) == len(cases)
    stamp = datetime.now(UTC).isoformat()
    limitations = [
        "Only the author's L-bracket count is labelled. Other three categories are unknown, never filled with zero.",
        "Sixteen views are oracle ROIs selected using author boxes; four are full images. Not open-scene detection.",
        "All 20 eligible sources contain one L-bracket. No multi-bracket counting or negative-class false-positive claim.",
        "Sources share author groups and object instances; distinct source IDs are not independent factories or sessions.",
        "No model tuning or inference was used to select these cases; all 170 exclusions and original author rows are retained.",
        "Author annotations contain 919 boxes per variant, versus 920 described in the repository README; original labels remain unchanged.",
    ]
    manifest = {"schema_version": 1, "name": args.output_name, "created_at": stamp,
                "label_scope": "author_L_bracket_count_only", "cases": cases, "rules": RULES,
                "source_repository": source_manifest["author_repository"],
                "source_commit": source_manifest["author_commit"], "license": source_manifest["license"],
                "source_manifest_sha256": sha(source / "SOURCE_MANIFEST.json"), "limitations": limitations,
                "inference_performed": False, "preparation_source_sha256": sha(Path(__file__))}
    audit = {"created_at": stamp, "source_records": 190, "author_boxes": sum(len(r["author_rows"]) for r in records),
             "all_downloaded_files_verified": len(source_manifest["files"]),
             "paired_variants_not_counted_twice": True, "eligible": len(cases),
             "kind_counts": dict(Counter(c["view_kind"] for c in cases)),
             "group_counts": dict(Counter(c["author_group"] for c in cases)),
             "exclusions": dict(Counter(r["excluded_reason"] for r in records if r["excluded_reason"])),
             "independent_coordinates_match": True, "unique_derived_hashes": len(cases), "records": records}
    for name, value in (("manifest.json", manifest), ("data_quality.json", audit)):
        (manifest_dir / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    (derived_dir / "README.md").write_text("# Author-box L-bracket views\n\n" + "\n\n".join(limitations) + "\n")
    print(json.dumps({"manifest": str(manifest_dir / "manifest.json"), "sha256": sha(manifest_dir / "manifest.json"),
                      "eligible": len(cases), "views": audit["kind_counts"], "exclusions": audit["exclusions"]}))


if __name__ == "__main__":
    main()
