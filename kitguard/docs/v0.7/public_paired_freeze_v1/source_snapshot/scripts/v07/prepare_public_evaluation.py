"""Freeze source-disjoint public-photo selection without loading a model.

Run from the repository root with ``python -m scripts.v07.prepare_public_evaluation``.
Historical metadata-only candidate catalogues are not model exposure; actual run
manifests, training splits, old protected cases, and browser artifacts are.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SEED = "KitGuard-v07-public-paired-20261002-v1"
PARTS = ("bolt", "nut", "washer", "bracket")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(path.read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def objects(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from objects(item)
    elif isinstance(value, list):
        for item in value:
            yield from objects(item)


def stable(value):
    return digest(f"{SEED}|{value}".encode())


def select_views(views):
    """One deterministic view per original; balance counts without model output."""
    by_source = defaultdict(list)
    for view in views:
        by_source[view["source_sha256"]].append(view)
    counts, chosen = Counter(), []
    for sha in sorted(by_source, key=stable):
        view = min(by_source[sha], key=lambda v: (
            counts[tuple(v["ground_truth"][p] for p in PARTS)],
            stable(v["id"]),
        ))
        chosen.append(view)
        counts[tuple(view["ground_truth"][p] for p in PARTS)] += 1
    return chosen


def verify_crop(view, annotation_by_id):
    """Recompute rotated corners from author labels, independently of cached AABBs."""
    left, top, right, bottom = view["crop_xyxy"]
    included = []
    counts = dict.fromkeys(PARTS, 0)
    for ann_id in view["included_annotation_ids"] + view["excluded_annotation_ids"]:
        ann = annotation_by_id[ann_id]
        row, col, width, height, phi = ann["bbox"]
        corners = [(col + x * math.cos(phi) - y * math.sin(phi),
                    row + x * math.sin(phi) + y * math.cos(phi))
                   for x in (-width / 2, width / 2) for y in (-height / 2, height / 2)]
        x0, y0 = min(x for x, _ in corners), min(y for _, y in corners)
        x1, y1 = max(x for x, _ in corners), max(y for _, y in corners)
        if x0 < 0 or y0 < 0 or x1 > view["source_width"] or y1 > view["source_height"]:
            raise ValueError("Author box extends beyond source")
        inside = x0 - 16 >= left and y0 - 16 >= top and x1 + 16 <= right and y1 + 16 <= bottom
        outside = x1 + 16 <= left or y1 + 16 <= top or x0 - 16 >= right or y0 - 16 >= bottom
        if not inside and not outside:
            raise ValueError("Crop touches an author box or its safety margin")
        if inside:
            included.append(ann_id)
            counts["nut" if ann["category_id"] in {7, 9, 10, 11} else "bolt"] += 1
    if set(included) != set(view["included_annotation_ids"]) or counts != view["ground_truth"]:
        raise ValueError("Independent author count disagrees")


def prepare(root, output):
    if output.exists():
        raise ValueError("Output already exists; preserve the previous freeze")
    source_paths = [
        "datasets/manifests/mvtec_screws/manifest.json",
        "datasets/manifests/mvtec_loco_screw_bag/kitguard_eligible.json",
        "datasets/manifests/v0.3/source_grouped_v2/screws_crop_candidate_catalog.json",
        "datasets/manifests/v0.3/source_grouped_v2/decoded_pixel_duplicate_audit.json",
        "datasets/raw/mvtec_screws_v1.0/mvtec_screws.json",
    ]
    screws, loco, catalogue, pixels, annotations = [load(root / p) for p in source_paths]
    originals = {i["sha256"]: i for i in screws["images"] + loco}
    evidence_files = sorted(set(
        list(root.glob("evaluation-runs/*/manifest.json"))
        + list(root.glob("evaluation-runs/*/development_manifest.json"))
        + [root / f"datasets/derived/public_detector_v1/{split}.json" for split in ("train", "val", "test")]
        + [root / "datasets/manifests/kitguard_screws_counting_v1.json"]
    ))
    exposure = defaultdict(list)
    for path in evidence_files:
        for row in objects(load(path)):
            for key in ("sha256", "source_sha256"):
                sha = row.get(key)
                if sha in originals:
                    exposure[sha].append(str(path.relative_to(root)))
    # Supplement semantic manifests with all prior actual evaluation/browser JSON
    # artifacts and docs, including records that only retain a source filename.
    scanned = []
    for folder in ("evaluation-runs", "test-results/browser", "docs"):
        for path in sorted((root / folder).rglob("*")):
            if (not path.is_file() or path.suffix not in {".json", ".jsonl", ".md"}
                    or "source_snapshot" in path.parts or "v0.7" in path.parts):
                continue
            content = path.read_text(errors="replace")
            scanned.append(path)
            for sha, item in originals.items():
                # LOCO basenames are not globally unique, so use complete raw paths.
                name = (Path(item["path"]).name if "screws_v1.0" in item["path"]
                        else item["path"].removeprefix("datasets/"))
                if sha in content or name in content:
                    exposure[sha].append(str(path.relative_to(root)))
    available = [v for v in catalogue["views"] if v["source_sha256"] not in exposure]
    views = select_views(available)
    normal_pool = [i for i in loco if i["sha256"] not in exposure and i["upstream_kind"] == "good"]
    normal = sorted(normal_pool, key=lambda i: stable(i["sha256"]))[:16]
    if len(views) != 35 or len(normal) != 16:
        raise ValueError(f"Exposure population changed: {len(views)} Screws and {len(normal)} LOCO; review before freezing")
    annotation_by_id = {a["id"]: a for a in annotations["annotations"]}
    expected_pixels = pixels["all_original_pixel_hashes"]
    selected_shas = [v["source_sha256"] for v in views] + [i["sha256"] for i in normal]
    selected_pixel_shas = [expected_pixels[s] for s in selected_shas]
    exposed_pixels = {expected_pixels[s] for s in exposure if s in expected_pixels}
    if len(set(selected_pixel_shas)) != 51 or set(selected_pixel_shas) & exposed_pixels:
        raise ValueError("Selected sources overlap exposed decoded pixels")
    output.mkdir(parents=True)
    cases = []
    for view in views:
        source = root / "datasets" / view["source_image"]
        original = originals[view["source_sha256"]]
        if set(original["annotation_ids"]) != set(view["included_annotation_ids"] + view["excluded_annotation_ids"]):
            raise ValueError("Candidate omits author annotations from its source")
        verify_crop(view, annotation_by_id)
        verify_source(source, view["source_sha256"], expected_pixels[view["source_sha256"]])
        case_id = view["id"].replace("v03-", "v07-")
        image_path = output / "images" / f"{case_id}.png"
        image_path.parent.mkdir(exist_ok=True)
        with Image.open(source) as image:
            image.convert("RGB").crop(view["crop_xyxy"]).save(image_path)
        cases.append({
            "id": case_id, "image": str(image_path.relative_to(root / "datasets")),
            "sha256": digest(image_path.read_bytes()), "source_id": view["source_id"],
            "source_image": view["source_image"], "source_sha256": view["source_sha256"],
            "source_decoded_rgb_sha256": expected_pixels[view["source_sha256"]],
            "split": "holdout", "ground_truth": view["ground_truth"],
            "subgroup": "screws_author_safe_crop", "supported_positive_classes": ["bolt", "nut"],
            "derived_view": True, "crop_xyxy": view["crop_xyxy"],
            "included_annotation_ids": view["included_annotation_ids"],
            "ground_truth_basis": view["ground_truth_basis"], "bbox_margin_px": 16,
            "candidate_was_previously_catalogued": True,
        })
    for item in normal:
        source = root / item["path"]
        verify_source(source, item["sha256"], expected_pixels[item["sha256"]])
        cases.append({
            "id": "v07-loco-" + item["id"].replace("/", "-"),
            "image": item["path"].removeprefix("datasets/"), "sha256": item["sha256"],
            "source_id": "mvtec-loco-ad:" + item["id"], "source_sha256": item["sha256"],
            "source_decoded_rgb_sha256": expected_pixels[item["sha256"]],
            "split": "holdout", "ground_truth": item["kitguard_counts"],
            "nominal_requirements": item["kitguard_counts"], "subgroup": "loco_normal_222",
            "supported_positive_classes": ["bolt", "nut", "washer"], "derived_view": False,
            "ground_truth_basis": item["ground_truth_basis"],
        })
    cases.sort(key=lambda c: stable(c["source_sha256"]))
    manifest = {"schema_version": 1, "name": "v07 paired public-photo holdout", "cases": cases,
                "dataset_root": "datasets", "selection_seed": SEED,
                "limitations": ["Previously catalogued candidates, no prior project model use found.",
                                "Same public capture domains; pretraining and near-duplicate scene overlap unknown.",
                                "No new bracket positives or LOCO physical quantity anomalies.",
                                "Screws uses safe crops, not full-photo product-scope claims."]}
    write(output / "manifest.json", manifest)
    audit = {
        "created_at": datetime.now(UTC).isoformat(), "no_model_loaded_or_called": True,
        "selection_seed": SEED, "screws_originals": 384, "screws_unexposed_sources": len(views),
        "screws_unexposed_safe_views": len(available), "loco_unexposed_normal_pool": len(normal_pool),
        "loco_unexposed_quantity_anomalies": sum(i["sha256"] not in exposure and i["upstream_kind"] != "good" for i in loco),
        "selected": {"screws": 35, "loco": 16, "unique_sources": 51},
        "crop_count_vectors": dict(Counter(str(tuple(c["ground_truth"][p] for p in PARTS)) for c in cases if c["derived_view"])),
        "exposure": {sha: sorted(set(paths)) for sha, paths in sorted(exposure.items())},
        "inputs": {str(p.relative_to(root)): digest(p.read_bytes()) for p in sorted(set(evidence_files + scanned + [root / p for p in source_paths]))},
        "pixel_audit_reused": source_paths[3], "selected_sources_rehashed_and_decoded": 51,
        "scope": "Project model/training/browser records; source catalogs alone are not model exposure. No external pretraining certification.",
    }
    write(output / "selection_audit.json", audit)
    return manifest, audit


def verify_source(path, expected_file, expected_pixel):
    if digest(path.read_bytes()) != expected_file:
        raise ValueError(f"Source file changed: {path}")
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        # Match the pinned v0.3 all-original audit's explicit byte convention.
        pixel = digest(str(rgb.size).encode() + b"|RGB|" + rgb.tobytes())
    if pixel != expected_pixel:
        raise ValueError(f"Source decoded pixels changed: {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "datasets/derived/v0.7/public_paired_v1")
    args = parser.parse_args()
    manifest, audit = prepare(ROOT, args.output.resolve())
    print(json.dumps({"cases": len(manifest["cases"]), "selection": audit["selected"], "output": str(args.output)}))


if __name__ == "__main__":
    main()
