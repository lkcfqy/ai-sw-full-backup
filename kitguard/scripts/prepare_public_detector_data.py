"""Prepare an isolated, author-labelled two-class detector experiment; no inference.

Run from the KitGuard root. Images stay in their original locations. Existing
benchmarks and an existing output directory are never rewritten.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
RAW = "datasets/raw/mvtec_screws_v1.0"
SOURCE = "datasets/manifests/mvtec_screws/manifest.json"
ANNOTATIONS = f"{RAW}/mvtec_screws.json"
DEFAULT_OUTPUT = "datasets/derived/public_detector_v1"
CLASS_MAPPING = {i: (2 if i in {7, 9, 10, 11} else 1) for i in range(1, 14)}
CATEGORIES = [{"id": 1, "name": "bolt", "supercategory": "fastener"},
              {"id": 2, "name": "nut", "supercategory": "fastener"}]
EXCLUSION_FILES = (
    "datasets/manifests/kitguard_screws_counting_v1.json",
    "datasets/manifests/v0.3/screws_new_holdout_crop_specs_v1.json",
    "datasets/manifests/v0.3/source_grouped_v2/screws_new_holdout_crop_specs_v1.json",
    "datasets/manifests/v0.3/screws_crop_candidate_catalog.json",
    "datasets/manifests/v0.3/source_grouped_v2/screws_crop_candidate_catalog.json",
)
PINNED_HASHES = {
    SOURCE: "159bbcf94c26eaa1305b2d0f4dada8b902d6cb19710227b2cc2d1fabdf1e6159",
    ANNOTATIONS: "81257dff178531b5f02240addb89a132b701b557fb2663817981339176c80fa9",
    f"{RAW}/mvtec_screws_train.json": "56fb5070b9919add27a599c9d08dca1d8e3cdacc337030257f9e72604dbec6bc",
    f"{RAW}/mvtec_screws_val.json": "c746bee8f0ea2d48623960bcc41c80e02232914ca09bbf21928d924d22215599",
    f"{RAW}/mvtec_screws_test.json": "ae03cba64f0c35088cdfd716ce93975067392324de98d70f4f1b570ae78dab1c",
    EXCLUSION_FILES[0]: "e20544689e2281c4bc3886c4cca75335ad9f4822fcd0f826c24c040df2cd2604",
    EXCLUSION_FILES[1]: "8a6dd304c596edd19df2ac12b4a642341c7bfdf664d9c7bdc74fe2f8d929b6cd",
    EXCLUSION_FILES[2]: "6b05d4badd5bcd33f882f201fc0b5eaaddce36437983902fda872bdccc2541a0",
    EXCLUSION_FILES[3]: "581ece6f786cacfe3642be715b917447d1270c70ecd1582b614fae3c74b6a136",
    EXCLUSION_FILES[4]: "eeb5437ba955f9a30afcdc663b665dec8d31c3deecad2aef648f63fc97893c13",
}
EXPECTED_COUNTS = {"train": (214, 2597), "val": (44, 543), "test": (22, 315)}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_path(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Unsafe source path: {relative}")
    result = (root / path).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError(f"Source path escapes root: {relative}")
    return result


def load_pinned(root: Path, relative: str, expected: str) -> dict:
    path = safe_path(root, relative)
    if not path.is_file():
        raise ValueError(f"Missing source file: {relative}")
    data = path.read_bytes()
    if sha256(data) != expected:
        raise ValueError(f"Source hash mismatch: {relative}")
    return json.loads(data)


def unique_ids(rows: list[dict], label: str) -> dict[int, dict]:
    result = {}
    for row in rows:
        value = row.get("id")
        if type(value) is not int or value <= 0 or value in result:
            raise ValueError(f"Invalid or duplicate ID in {label}: {value}")
        result[value] = row
    return result


def author_box_to_xywh(bbox: list, width: int, height: int) -> tuple[list[float], bool]:
    """Convert author's centre row/column and full-axis lengths, then clip."""
    if (not isinstance(bbox, list) or len(bbox) != 5
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in bbox)):
        raise ValueError("Invalid author bbox: expected five finite numbers")
    row, col, box_width, box_height, phi = bbox
    if box_width <= 0 or box_height <= 0:
        raise ValueError("Invalid author bbox dimensions")
    # The pinned author data includes angles beyond pi despite its README.
    # sin/cos accept their finite, periodic radian representation unchanged.
    dx = abs(math.cos(phi)) * box_width / 2 + abs(math.sin(phi)) * box_height / 2
    dy = abs(math.sin(phi)) * box_width / 2 + abs(math.cos(phi)) * box_height / 2
    original = [col - dx, row - dy, col + dx, row + dy]
    clipped = [max(0.0, original[0]), max(0.0, original[1]),
               min(float(width), original[2]), min(float(height), original[3])]
    if not all(math.isfinite(v) for v in original) or clipped[2] <= clipped[0] or clipped[3] <= clipped[1]:
        raise ValueError("Author bbox has no finite visible area")
    return [clipped[0], clipped[1], clipped[2] - clipped[0], clipped[3] - clipped[1]], clipped != original


def validate_coco_like(data: dict, label: str) -> tuple[dict, dict]:
    categories = unique_ids(data["categories"], f"{label} categories")
    if set(categories) != set(CLASS_MAPPING):
        raise ValueError(f"Unknown or missing author categories in {label}")
    images = unique_ids(data["images"], f"{label} images")
    if len({i["file_name"] for i in images.values()}) != len(images):
        raise ValueError(f"Duplicate image filename in {label}")
    for im in images.values():
        if Path(im["file_name"]).name != im["file_name"]:
            raise ValueError(f"Non-basename author filename in {label}")
        if any(type(im.get(k)) is not int or im[k] <= 0 for k in ("width", "height")):
            raise ValueError(f"Invalid image dimensions in {label}")
    annotations = unique_ids(data["annotations"], f"{label} annotations")
    for ann in annotations.values():
        if type(ann.get("category_id")) is not int or ann["category_id"] not in CLASS_MAPPING:
            raise ValueError(f"Unknown annotation category in {label}")
        if type(ann.get("image_id")) is not int or ann["image_id"] not in images:
            raise ValueError(f"Unknown annotation image in {label}")
        if ann.get("is_crowd") != 0:
            raise ValueError(f"Unexpected crowd annotation in {label}")
        im = images[ann["image_id"]]
        author_box_to_xywh(ann["bbox"], im["width"], im["height"])
    return images, annotations


def annotation_signatures(images: dict, annotations: dict) -> dict:
    result = defaultdict(Counter)
    for ann in annotations.values():
        filename = images[ann["image_id"]]["file_name"]
        result[filename][(ann["category_id"], tuple(ann["bbox"]), ann["area"], ann["is_crowd"])] += 1
    return result


def decoded_rgb_hash(path: Path, width: int, height: int) -> str:
    with Image.open(path) as image:
        if image.size != (width, height):
            raise ValueError(f"Decoded image dimensions mismatch: {path.name}")
        rgb = image.convert("RGB")
        return sha256(f"{width},{height},RGB\n".encode() + rgb.tobytes())


def build_artifacts(root: Path, *, pinned_hashes: dict | None = None,
                    expected_counts: dict | None = None, expected_excluded: int = 104) -> dict:
    """Validate all inputs before producing artifacts. Overrides serve unit fixtures only."""
    hashes = PINNED_HASHES if pinned_hashes is None else pinned_hashes
    counts = EXPECTED_COUNTS if expected_counts is None else expected_counts
    required = {SOURCE, ANNOTATIONS, *EXCLUSION_FILES,
                *(f"{RAW}/mvtec_screws_{s}.json" for s in ("train", "val", "test"))}
    if set(hashes) != required:
        raise ValueError("Incomplete pinned input set")
    inputs = {name: load_pinned(root, name, hashes[name]) for name in sorted(required)}
    source, original = inputs[SOURCE], inputs[ANNOTATIONS]
    if source["upstream_annotation_path"] != ANNOTATIONS or source["upstream_annotation_sha256"] != hashes[ANNOTATIONS]:
        raise ValueError("Source manifest annotation identity mismatch")
    expected_mapping = {str(k): CATEGORIES[v - 1]["name"] for k, v in CLASS_MAPPING.items()}
    if source["category_mapping"] != expected_mapping:
        raise ValueError("Source manifest category mapping mismatch")
    images, annotations = validate_coco_like(original, "full dataset")
    unique_ids(source["images"], "source manifest images")
    by_name = {im["file_name"]: im for im in images.values()}
    metadata = {}
    for im in source["images"]:
        filename = Path(im["path"]).name
        if filename in metadata or im["path"] != f"{RAW}/images/{filename}":
            raise ValueError("Duplicate or invalid source manifest image path")
        metadata[filename] = im
    if set(metadata) != set(by_name) or source["image_count"] != len(images) or source["annotation_count"] != len(annotations):
        raise ValueError("Source manifest population mismatch")
    signatures = annotation_signatures(images, annotations)
    official_splits = {}
    for split in ("train", "val", "test"):
        split_images, split_anns = validate_coco_like(inputs[f"{RAW}/mvtec_screws_{split}.json"], split)
        split_signatures = annotation_signatures(split_images, split_anns)
        for im in split_images.values():
            filename = im["file_name"]
            if filename in official_splits or filename not in by_name:
                raise ValueError("Official splits overlap or contain unknown source")
            if any(im[k] != by_name[filename][k] for k in ("width", "height")):
                raise ValueError("Official split dimensions mismatch")
            if split_signatures[filename] != signatures[filename]:
                raise ValueError("Official split annotations mismatch by filename")
            official_splits[filename] = split
    if set(official_splits) != set(by_name):
        raise ValueError("Official splits do not partition full dataset")

    exclusion_evidence = defaultdict(list)
    exclusion_sources = []
    for relative in EXCLUSION_FILES:
        document = inputs[relative]
        key = "cases" if "cases" in document else "views"
        selected_sources = set()
        for index, row in enumerate(document[key]):
            if row.get("split") != "holdout" and row.get("proposed_split") != "holdout":
                continue
            source_path = row.get("source_image", row.get("image"))
            filename = Path(source_path).name
            if filename not in metadata:
                raise ValueError(f"Unknown protected source in {relative}: {filename}")
            identity = row.get("source_sha256", row.get("sha256"))
            if identity != metadata[filename]["sha256"]:
                raise ValueError(f"Protected source hash mismatch in {relative}: {filename}")
            selected_sources.add(filename)
            exclusion_evidence[filename].append({"path": relative, "pointer": f"/{key}/{index}",
                                                 "source_sha256": identity})
        exclusion_sources.append({"path": relative, "sha256": hashes[relative],
                                  "protected_original_count": len(selected_sources)})
    if len(exclusion_evidence) != expected_excluded:
        raise ValueError(f"Historical exclusion count changed: {len(exclusion_evidence)}")

    # Include historical protected originals in duplicate checks. A re-encoded
    # holdout image cannot enter training through a different filename or SHA.
    raw_hashes, pixel_hashes, decoded = {}, {}, {}
    for filename in sorted(by_name):
        im, meta = by_name[filename], metadata[filename]
        if any(meta[k] != im[k] for k in ("width", "height")) or meta["upstream_split"] != official_splits[filename]:
            raise ValueError(f"Source manifest dimensions/split mismatch: {filename}")
        path = safe_path(root, meta["path"])
        if not path.is_file():
            raise ValueError(f"Missing image: {meta['path']}")
        digest = sha256(path.read_bytes())
        if digest != meta["sha256"]:
            raise ValueError(f"Image source hash mismatch: {filename}")
        if digest in raw_hashes:
            raise ValueError(f"Duplicate image SHA: {filename}, {raw_hashes[digest]}")
        raw_hashes[digest] = filename
        pixel_digest = decoded_rgb_hash(path, im["width"], im["height"])
        if pixel_digest in pixel_hashes:
            raise ValueError(f"Duplicate decoded pixels: {filename}, {pixel_hashes[pixel_digest]}")
        pixel_hashes[pixel_digest] = filename
        decoded[filename] = pixel_digest

    licenses = original["licenses"]
    if isinstance(licenses, dict):
        licenses = [licenses]
    artifacts = {}
    statistics = {}
    clipped_records = []
    for split in ("train", "val", "test"):
        selected_names = {n for n, s in official_splits.items() if s == split and n not in exclusion_evidence}
        selected_images = []
        for filename in sorted(selected_names):
            im, meta = by_name[filename], metadata[filename]
            selected_images.append({**im, "file_name": meta["path"], "original_filename": filename,
                                    "original_split": split, "source_sha256": meta["sha256"],
                                    "source_decoded_rgb_sha256": decoded[filename]})
        selected_ids = {im["id"] for im in selected_images}
        selected_annotations = []
        class_counts = Counter()
        for annotation_id, ann in sorted(annotations.items()):
            if ann["image_id"] not in selected_ids:
                continue
            im = images[ann["image_id"]]
            bbox, clipped = author_box_to_xywh(ann["bbox"], im["width"], im["height"])
            category_id = CLASS_MAPPING[ann["category_id"]]
            class_counts[CATEGORIES[category_id - 1]["name"]] += 1
            converted = {"id": annotation_id, "image_id": ann["image_id"], "category_id": category_id,
                         "bbox": bbox, "area": bbox[2] * bbox[3], "iscrowd": 0,
                         "original_category_id": ann["category_id"], "original_annotation_id": annotation_id,
                         "original_bbox_row_col_width_height_phi": ann["bbox"], "bbox_clipped": clipped}
            selected_annotations.append(converted)
            if clipped:
                clipped_records.append({"split": split, "original_filename": im["file_name"],
                                        "annotation_id": annotation_id, "original_bbox": ann["bbox"],
                                        "clipped_bbox_xywh": bbox})
        actual = (len(selected_images), len(selected_annotations))
        if actual != tuple(counts[split]):
            raise ValueError(f"Unexpected {split} image/annotation counts: {actual}")
        artifacts[f"{split}.json"] = {"info": {"description": "MVTec Screws author labels projected to bolt/nut",
                                               "schema": "kitguard.public-detector.coco-aabb.v1",
                                               "image_path_base": "kitguard repository root",
                                               "bbox_format": "absolute pixel [x_min,y_min,width,height]"},
                                      "licenses": licenses, "categories": CATEGORIES,
                                      "images": selected_images, "annotations": selected_annotations}
        statistics[split] = {"images": actual[0], "annotations": actual[1],
                             "class_annotation_counts": dict(sorted(class_counts.items())),
                             "clipped_annotations": sum(r["split"] == split for r in clipped_records)}

    artifacts["manifest.json"] = {
        "schema": "kitguard.public-detector.dataset.v1", "name": "public_detector_v1",
        "status": "prepared_not_trained", "inference_performed": False, "model_generated_labels": False,
        "source": {key: source[key] for key in ("dataset", "author", "author_page", "source_page", "download_url",
                                                "archive_sha256", "license", "license_url")},
        "upstream_image_count": len(images), "upstream_annotation_count": len(annotations),
        "annotation_count_note": "Pinned archive contains 4427 instances; upstream README states 4426. No label dropped.",
        "source_files": [{"path": name, "sha256": digest} for name, digest in sorted(hashes.items())],
        "image_path_base": "kitguard repository root", "category_mapping": expected_mapping,
        "categories": CATEGORIES, "uncovered_categories": ["washer", "bracket"],
        "uncovered_category_policy": "No positive coverage; unknown/unsupported, never infer absence from this detector.",
        "split_rule": "Preserve official split by filename; exclude every original marked historical holdout/proposed_holdout.",
        "exclusion_sources": exclusion_sources, "excluded_original_count": len(exclusion_evidence),
        "excluded_originals": [{"original_filename": n, "source_image": metadata[n]["path"],
                                "source_sha256": metadata[n]["sha256"], "original_split": official_splits[n],
                                "evidence": exclusion_evidence[n]} for n in sorted(exclusion_evidence)],
        "splits": statistics, "clipped_annotations": clipped_records,
        "duplicate_audit": {"images_checked": len(images), "raw_sha_duplicates": 0, "decoded_rgb_duplicates": 0,
                            "includes_historical_excluded_sources": True,
                            "pixel_hash_encoding": "SHA256(UTF8(width,height,RGB\\n) + decoded RGB bytes)",
                            "scope": "Exact content only; near duplicates/acquisition sessions not established."},
        "box_conversion": {"source": "center row,col,full width,height,phi radians", "output": "clipped AABB xywh",
                           "no_annotation_dropped": True, "area": "clipped AABB width*height",
                           "finite_angles_used_as_provided": True,
                           "upstream_angles_outside_documented_minus_pi_to_pi":
                               sum(not -math.pi < a["bbox"][4] <= math.pi for a in annotations.values())},
        "limitations": ["Two broad categories on public wooden-background photographs; not SKU/size verification.",
                        "No washer or bracket positive examples; no full four-class product capability established.",
                        "Sources share an acquisition domain; this is not field validation or a new factory.",
                        "Independent training experiment; existing v0.5 model, benchmarks and results remain unchanged."],
    }
    return artifacts


def write_artifacts(artifacts: dict, output: Path) -> dict:
    if output.exists():
        raise ValueError(f"Refuse to overwrite existing output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".public-detector-", dir=output.parent) as staging:
        staging_path = Path(staging)
        split_receipts = []
        for name in ("train.json", "val.json", "test.json"):
            data = (json.dumps(artifacts[name], ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
            (staging_path / name).write_bytes(data)
            split_receipts.append({"path": name, "sha256": sha256(data)})
        manifest = {**artifacts["manifest.json"], "split_files": split_receipts,
                    "preparation_script_sha256": sha256(Path(__file__).read_bytes())}
        (staging_path / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2,
                                                             allow_nan=False) + "\n")
        if output.exists():
            raise ValueError(f"Output appeared during preparation: {output}")
        staging_path.rename(output)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path(DEFAULT_OUTPUT))
    args = parser.parse_args()
    output = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    try:
        if output.exists():
            raise ValueError(f"Refuse to overwrite existing output: {output}")
        manifest = write_artifacts(build_artifacts(ROOT), output)
    except (ValueError, KeyError, OSError, TypeError) as exc:
        parser.exit(1, f"Preparation refused: {exc}\n")
    print(json.dumps({"output": str(output), "splits": manifest["splits"],
                      "excluded_original_count": manifest["excluded_original_count"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
