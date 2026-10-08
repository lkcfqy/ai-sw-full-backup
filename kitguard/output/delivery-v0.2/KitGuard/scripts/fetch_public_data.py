#!/usr/bin/env python3
"""Fetch the public Neuromatch mirror of MVTec Screws; verify before extraction.

No accounts, contact forms, credentials, or model outputs are used. The original
dataset license remains CC BY-NC-SA 4.0, separate from this downloader's code.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import io
import json
import os
import shutil
import tarfile
import time
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
URL = "https://osf.io/ruca6/download"
DIRECT_URL = "https://files.ca-1.osf.io/v1/resources/hygbm/providers/osfstorage/61092c550e15cb00bcf8e31e"
SIZE = 1_361_662_840
SHA256 = "a742c5744cea973eca5d9eeee5896c8b458d3d695fb107a58707a9e7e0cc1342"
SOURCE_PAGE = "https://deeplearning.neuromatch.io/projects/ComputerVision/screws.html"
AUTHOR_PAGE = "https://www.mvtec.com/research-teaching/datasets/mvtec-screws"
LICENSE_URL = "https://creativecommons.org/licenses/by-nc-sa/4.0/"
SOURCES = {
    "neuromatch_course.html": SOURCE_PAGE,
    "mvtec_dataset_page.html": AUTHOR_PAGE,
    "osf_file_metadata.json": "https://api.osf.io/v2/files/ruca6/",
    "osf_project_metadata.json": "https://api.osf.io/v2/nodes/hygbm/",
}
LOCO_URL = "https://www.mydrive.ch/shares/48237/1b9106ccdfbb09a0c414bd49fe44a14a/download/430647091-1646842701/mvtec_loco_anomaly_detection.tar.xz"
LOCO_SIZE = 6_126_996_224
LOCO_SHA256 = "9e7c84dba550fd2e59d8e9e231c929c45ba737b6b6a6d3814100f54d63aae687"
LOCO_ADAPTER = "https://raw.githubusercontent.com/open-edge-platform/anomalib/bc94f1abebbc06215aa2f992e7c44cb7c19b33cb/src/anomalib/data/datasets/image/mvtec_loco.py"
LOCO_COUNT_DELTAS = {
    "1_additional_long_screw": ("bolt", 1),
    "1_additional_short_screw": ("bolt", 1),
    "1_additional_nut": ("nut", 1),
    "2_additional_nuts": ("nut", 2),
    "1_additional_washer": ("washer", 1),
    "2_additional_washers": ("washer", 2),
    "1_missing_long_screw": ("bolt", -1),
    "1_missing_short_screw": ("bolt", -1),
    "1_missing_nut": ("nut", -1),
    "2_missing_nuts": ("nut", -2),
    "1_missing_washer": ("washer", -1),
    "2_missing_washers": ("washer", -2),
}
LOCO_SELECTION_SEED = "KitGuard-LOCO-v1-20260926"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch_range(path: Path, start: int, end: int, url: str = DIRECT_URL, size: int = SIZE) -> None:
    expected = end - start + 1
    if path.exists() and path.stat().st_size == expected:
        return
    for attempt in range(4):
        try:
            offset = path.stat().st_size if path.exists() else 0
            if offset == expected:
                return
            if offset > expected:
                raise RuntimeError("Existing download chunk exceeds its declared range")
            requested_start = start + offset
            req = urllib.request.Request(
                url,
                headers={"Range": f"bytes={requested_start}-{end}", "User-Agent": "KitGuard-public-data/1.0"},
            )
            with urllib.request.urlopen(req, timeout=60) as response:
                if (
                    response.status != 206
                    or response.headers.get("Content-Range") != f"bytes {requested_start}-{end}/{size}"
                ):
                    raise RuntimeError("Server did not return the exact requested range")
                with path.open("ab") as stream:
                    copied = offset
                    while block := response.read(1024 * 1024):
                        copied += len(block)
                        if copied > expected:
                            raise RuntimeError("Response exceeds the requested byte limit")
                        stream.write(block)
            if path.stat().st_size != expected:
                raise RuntimeError("Incomplete download chunk")
            return
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))


def download(
    archive: Path, workers: int, url: str = DIRECT_URL, size: int = SIZE, expected_sha256: str = SHA256
) -> None:
    if archive.exists():
        if archive.stat().st_size != size or sha256(archive) != expected_sha256:
            raise RuntimeError("Existing archive is not the pinned release; preserving it without overwrite")
        return
    chunks = archive.parent / f".{archive.name}-download-parts"
    chunks.mkdir(parents=True, exist_ok=True)
    chunk_size = 16 * 1024 * 1024
    jobs = [
        (chunks / f"{start:012d}.part", start, min(size - 1, start + chunk_size - 1))
        for start in range(0, size, chunk_size)
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fetch_range, *job, url, size) for job in jobs]
        for n, future in enumerate(concurrent.futures.as_completed(futures), 1):
            future.result()
            print(f"Downloaded chunks {n}/{len(jobs)}", flush=True)
    temporary = archive.with_suffix(archive.suffix + ".partial")
    with temporary.open("wb") as output:
        for part, _, _ in jobs:
            with part.open("rb") as source:
                shutil.copyfileobj(source, output)
    actual = sha256(temporary)
    if actual != expected_sha256:
        raise RuntimeError(f"Archive SHA256 mismatch: {actual}")
    os.replace(temporary, archive)
    archive.chmod(0o444)
    shutil.rmtree(chunks)


def extract(archive: Path, raw: Path) -> None:
    marker = raw / ".verified_archive_sha256"
    if marker.exists() and marker.read_text().strip() == SHA256:
        return
    if raw.exists():
        raise RuntimeError(f"Unverified existing extraction preserved: {raw}")
    staging = raw.with_name(raw.name + ".extracting")
    if staging.exists():
        raise RuntimeError(f"Prior partial extraction preserved: {staging}; inspect before retry")
    staging.mkdir(parents=True)
    extracted_size = 0
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle:
            relative = PurePosixPath(member.name)
            if relative.is_absolute() or ".." in relative.parts or member.issym() or member.islnk():
                raise RuntimeError(f"Unsafe archive entry: {member.name}")
            target = staging.joinpath(*relative.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise RuntimeError(f"Unsupported archive entry: {member.name}")
            extracted_size += member.size
            if extracted_size > 3_000_000_000:
                raise RuntimeError("Unexpected extracted dataset size")
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.extractfile(member) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(0o444)
    (staging / ".verified_archive_sha256").write_text(SHA256 + "\n")
    (staging / ".verified_archive_sha256").chmod(0o444)
    os.replace(staging, raw)
    for folder in sorted((item for item in raw.rglob("*") if item.is_dir()), reverse=True):
        folder.chmod(0o555)
    raw.chmod(0o555)


def inventory(raw: Path, output: Path) -> None:
    annotations_path = next(raw.rglob("mvtec_screws.json"))
    base = annotations_path.parent
    data = json.loads(annotations_path.read_text())
    readme = base / "README_v1.0.txt"
    if "Attribution-NonCommercial-ShareAlike 4.0" not in readme.read_text():
        raise RuntimeError("Expected upstream dataset license not found")
    if len(data["images"]) != 384 or len(data["annotations"]) != 4427:
        raise RuntimeError("Dataset content differs from the documented v1.0 release")
    if len({item["id"] for item in data["annotations"]}) != len(data["annotations"]):
        raise RuntimeError("Duplicate annotation IDs")
    categories = {item["id"]: item for item in data["categories"]}
    annotations = {}
    for annotation in data["annotations"]:
        annotations.setdefault(annotation["image_id"], []).append(annotation)
    splits = {}
    for split in ("train", "val", "test"):
        split_data = json.loads((base / f"mvtec_screws_{split}.json").read_text())
        for image in split_data["images"]:
            if image["file_name"] in splits:
                raise RuntimeError("The upstream splits overlap")
            splits[image["file_name"]] = split
    # The runtime defines bolt as a broad 'threaded shaft with head'. This is
    # an explicit taxonomy projection, NOT a claim of identical screw SKUs.
    mapping = {
        category_id: "nut" if category_id in {7, 9, 10, 11} else "bolt" for category_id in range(1, 14)
    }
    if set(categories) != set(mapping):
        raise RuntimeError("Unexpected upstream categories; refuse to guess taxonomy mapping")
    images = []
    for image in data["images"]:
        objects = annotations.get(image["id"], [])
        counts = Counter(item["category_id"] for item in objects)
        compatible = all(category_id in mapping for category_id in counts)
        projected = {"bolt": 0, "nut": 0, "washer": 0, "bracket": 0}
        for category_id, count in counts.items():
            if category_id in mapping:
                projected[mapping[category_id]] += count
        eligible = compatible and 1 <= sum(projected.values()) <= 12 and max(projected.values()) <= 3
        image_path = base / "images" / image["file_name"]
        images.append(
            {
                "id": image["id"],
                "path": str(image_path.relative_to(ROOT)),
                "sha256": sha256(image_path),
                "width": image["width"],
                "height": image["height"],
                "upstream_split": splits.get(image["file_name"]),
                "annotation_ids": [a["id"] for a in objects],
                "category_counts": dict(counts),
                "kitguard_counts": projected if compatible else None,
                "kitguard_eligible": eligible,
                "real_photo": True,
                "transformed": False,
                "exclusion_reason": None
                if eligible
                else "Unsupported upstream category"
                if not compatible
                else "Count exceeds KitGuard scope",
            }
        )
    manifest = {
        "dataset": "MVTec Screws v1.0",
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "author": "MVTec Software GmbH",
        "mirror_operator": "Neuromatch Academy",
        "source_page": SOURCE_PAGE,
        "author_page": AUTHOR_PAGE,
        "download_url": URL,
        "archive_sha256": SHA256,
        "archive_bytes": SIZE,
        "license": "CC-BY-NC-SA-4.0",
        "license_url": LICENSE_URL,
        "sha256_verified_against": "OSF API file metadata extra.hashes.sha256",
        "upstream_readme_path": str(readme.relative_to(ROOT)),
        "upstream_readme_sha256": sha256(readme),
        "upstream_annotation_path": str(annotations_path.relative_to(ROOT)),
        "upstream_annotation_sha256": sha256(annotations_path),
        "categories": list(categories.values()),
        "category_mapping": mapping,
        "mapping_note": "Whole-frame counts derived from upstream object instances: bolt is the runtime's broad headed threaded fastener class (IDs 1-6,8,12,13, including wood screws), nut is IDs 7,9,10,11. This projection does not validate fine SKU/type/length distinctions. No washer/bracket positive examples; no model-generated labels.",
        "image_count": len(images),
        "annotation_count": len(data["annotations"]),
        "annotation_count_note": "Downloaded pinned archive contains 4427 unique annotations (3119 train + 647 val + 661 test); author README and landing page state 4426. All original annotations are preserved without correction.",
        "split_join_note": "Join split JSONs by file_name; split-local image_id values restart from 1 and are not the full-dataset image_id.",
        "eligible_count": sum(i["kitguard_eligible"] for i in images),
        "total_at_most_12_count": sum(
            sum(i["kitguard_counts"].values()) <= 12 for i in images if i["kitguard_counts"]
        ),
        "images": images,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    (output / "kitguard_eligible.json").write_text(
        json.dumps([i for i in images if i["kitguard_eligible"]], ensure_ascii=False, indent=2) + "\n"
    )
    files = [
        {
            "path": str(path.relative_to(ROOT)),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
            "origin": "local_verification_metadata"
            if path.name in {".verified_archive_sha256", "acquisition_status.json"}
            else "original_archive_member",
        }
        for path in sorted(raw.rglob("*"))
        if path.is_file()
    ]
    (output / "raw_files_sha256.json").write_text(json.dumps(files, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps({k: manifest[k] for k in ["image_count", "annotation_count", "eligible_count"]}),
        flush=True,
    )


def extract_loco(archive: Path, raw: Path) -> None:
    marker = raw / ".verified_archive_sha256"
    if marker.exists() and marker.read_text().strip() == LOCO_SHA256:
        return
    if raw.exists():
        raise RuntimeError(f"Unverified existing extraction preserved: {raw}")
    staging = raw.with_name(raw.name + ".extracting")
    if staging.exists():
        raise RuntimeError(f"Prior partial extraction preserved: {staging}")
    staging.mkdir(parents=True)
    extracted_size = 0
    kept = 0
    with tarfile.open(archive, "r|xz") as bundle:
        for member in bundle:
            relative = PurePosixPath(member.name)
            if relative.is_absolute() or ".." in relative.parts or member.issym() or member.islnk():
                raise RuntimeError(f"Unsafe archive entry: {member.name}")
            if "screw_bag" in relative.parts:
                parts = relative.parts[relative.parts.index("screw_bag") :]
            elif len(relative.parts) == 1 and any(
                word in relative.name.lower() for word in ("license", "readme")
            ):
                parts = (relative.name,)
            else:
                continue
            target = staging.joinpath(*parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise RuntimeError(f"Unsupported archive entry: {member.name}")
            extracted_size += member.size
            if extracted_size > 3_000_000_000:
                raise RuntimeError("Unexpected screw_bag extracted size")
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.extractfile(member) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(0o444)
            kept += 1
            if kept % 100 == 0:
                print(f"Extracted screw_bag files: {kept}", flush=True)
    if not (staging / "screw_bag").is_dir():
        raise RuntimeError("Expected screw_bag directory is absent")
    (staging / ".verified_archive_sha256").write_text(LOCO_SHA256 + "\n")
    (staging / ".verified_archive_sha256").chmod(0o444)
    os.replace(staging, raw)
    for folder in sorted((item for item in raw.rglob("*") if item.is_dir()), reverse=True):
        folder.chmod(0o555)
    raw.chmod(0o555)


def inventory_loco(raw: Path, output: Path, *, archive_verified: bool = True) -> None:
    from PIL import Image

    base = raw / "screw_bag"
    readme = base / "readme.txt"
    if "Attribution-NonCommercial-ShareAlike 4.0" not in readme.read_text():
        raise RuntimeError("Expected upstream dataset license not found")
    defect_config_path = base / "defects_config.json"
    defect_config = json.loads(defect_config_path.read_text())
    defect_names = {item["pixel_value"]: item["defect_name"] for item in defect_config}
    if not set(LOCO_COUNT_DELTAS) <= set(defect_names.values()):
        raise RuntimeError("Expected author quantity-defect names are absent")
    images = []
    for split in ("train", "validation", "test"):
        for image in sorted((base / split).rglob("*.png")):
            kind = image.parent.name
            good = kind == "good"
            counts = {"bolt": 2, "nut": 2, "washer": 2, "bracket": 0} if good else None
            basis = (
                "Author-defined normal bag composition: 1 long screw + 1 short screw + 2 nuts + 2 washers"
                if good
                else "Exact counts unresolved; anomaly masks are not full instance annotations"
            )
            label_status = "author_normal_rule" if good else "unresolved"
            masks = sorted((base / "ground_truth" / kind / image.stem).glob("*.png")) if not good else []
            mask_records = []
            for mask in masks:
                with Image.open(mask) as mask_image:
                    if mask_image.mode != "L":
                        raise RuntimeError(f"Unexpected annotation image mode: {mask_image.mode}")
                    colors = mask_image.getcolors(maxcolors=256)
                    if colors is None:
                        raise RuntimeError("Unexpected mask label range")
                    values = sorted(value for _, value in colors if value != 0)
                if any(value not in defect_names for value in values):
                    raise RuntimeError("Mask contains an unknown author defect pixel value")
                mask_records.append(
                    {
                        "path": str(mask.relative_to(ROOT)),
                        "sha256": sha256(mask),
                        "pixel_values": values,
                        "defect_names": [defect_names[value] for value in values],
                    }
                )
            # One original mask with one explicit quantity defect only. Multiple
            # masks, mixed defects, size substitutions and damage remain unlabeled.
            if (
                kind == "logical_anomalies"
                and len(mask_records) == 1
                and len(mask_records[0]["defect_names"]) == 1
            ):
                defect_name = mask_records[0]["defect_names"][0]
                if defect_name in LOCO_COUNT_DELTAS:
                    part, delta = LOCO_COUNT_DELTAS[defect_name]
                    counts = {"bolt": 2, "nut": 2, "washer": 2, "bracket": 0}
                    counts[part] += delta
                    basis = f"Author normal composition plus the single original mask defect {defect_name}: {part} {delta:+d}"
                    label_status = "author_single_quantity_defect_rule"
            eligible = (
                counts is not None
                and 1 <= sum(counts.values()) <= 12
                and all(0 <= n <= 3 for n in counts.values())
            )
            images.append(
                {
                    "id": f"screw_bag/{split}/{kind}/{image.stem}",
                    "path": str(image.relative_to(ROOT)),
                    "sha256": sha256(image),
                    "upstream_split": split,
                    "upstream_kind": kind,
                    "kitguard_counts": counts,
                    "ground_truth_basis": basis,
                    "label_status": label_status,
                    "source_masks": mask_records,
                    "kitguard_eligible": eligible,
                    "real_photo": True,
                    "transformed": False,
                }
            )
    manifest = {
        "dataset": "MVTec LOCO AD screw_bag",
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "author": "MVTec Software GmbH",
        "author_page": "https://www.mvtec.com/research-teaching/datasets/mvtec-loco-ad",
        "download_url": LOCO_URL,
        "archive_sha256": LOCO_SHA256 if archive_verified else None,
        "expected_archive_sha256": LOCO_SHA256,
        "full_archive_verification_pending": not archive_verified,
        "archive_bytes": LOCO_SIZE,
        "sha256_verified_against": "Open Edge Platform Anomalib official MVTec LOCO dataset adapter",
        "license": "CC-BY-NC-SA-4.0",
        "license_url": LICENSE_URL,
        "upstream_readme_path": str(readme.relative_to(ROOT)),
        "upstream_readme_sha256": sha256(readme),
        "defect_config_path": str(defect_config_path.relative_to(ROOT)),
        "defect_config_sha256": sha256(defect_config_path),
        "quantity_defect_mapping": LOCO_COUNT_DELTAS,
        "annotation_note": "Normal composition from author paper section 3.1. Anomaly counts are derived only when exactly one original mask contains exactly one explicit quantity-defect label. Original pixel values, names and mask hashes are retained. Mixed/size/structural defects remain unresolved. Long/short screws are projected to broad bolt; this does not test screw-length distinction.",
        "image_count": len(images),
        "eligible_count": sum(i["kitguard_eligible"] for i in images),
        "split_kind_counts": dict(Counter(f"{i['upstream_split']}/{i['upstream_kind']}" for i in images)),
        "label_status_counts": dict(Counter(i["label_status"] for i in images)),
        "eligible_quantity_anomalies": sum(
            i["kitguard_eligible"] and i["label_status"] == "author_single_quantity_defect_rule"
            for i in images
        ),
        "images": images,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    (output / "kitguard_eligible.json").write_text(
        json.dumps([i for i in images if i["kitguard_eligible"]], ensure_ascii=False, indent=2) + "\n"
    )
    files = [
        {
            "path": str(path.relative_to(ROOT)),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
            "origin": "local_verification_metadata"
            if path.name in {".verified_archive_sha256", "acquisition_status.json"}
            else "original_archive_member",
        }
        for path in sorted(raw.rglob("*"))
        if path.is_file()
    ]
    (output / "raw_files_sha256.json").write_text(json.dumps(files, ensure_ascii=False, indent=2) + "\n")
    freeze_loco_benchmark(manifest, output)
    if archive_verified:
        verify_staged_against_full(raw, output)
    print(
        json.dumps({k: manifest[k] for k in ("image_count", "eligible_count", "split_kind_counts")}),
        flush=True,
    )


def freeze_loco_benchmark(manifest: dict, output: Path) -> None:
    """Select before model output; retain the first immutable benchmark release."""

    def key(image: dict) -> str:
        return hashlib.sha256(f"{LOCO_SELECTION_SEED}|{image['sha256']}".encode()).hexdigest()

    def interleave(first: list, second: list) -> list:
        return [
            pool[index]
            for index in range(max(len(first), len(second)))
            for pool in (first, second)
            if index < len(pool)
        ]

    images = [item for item in manifest["images"] if item["kitguard_eligible"]]
    train_normal = sorted(
        [i for i in images if i["upstream_split"] == "train" and i["label_status"] == "author_normal_rule"],
        key=key,
    )
    test_normal = sorted(
        [i for i in images if i["upstream_split"] == "test" and i["label_status"] == "author_normal_rule"],
        key=key,
    )
    quantity = sorted(
        [
            i
            for i in images
            if i["upstream_split"] == "test" and i["label_status"] == "author_single_quantity_defect_rule"
        ],
        key=key,
    )
    dev_normal, dev_quantity = train_normal[:8], quantity[:8]
    dev_hashes = {i["sha256"] for i in dev_normal + dev_quantity}
    holdout_normal = [i for i in test_normal if i["sha256"] not in dev_hashes][:24]
    holdout_quantity = [i for i in quantity[8:] if i["sha256"] not in dev_hashes][:24]
    cases = []
    for split, items in (
        ("development", interleave(dev_normal, dev_quantity)),
        ("holdout", interleave(holdout_normal, holdout_quantity)),
    ):
        for item in items:
            cases.append(
                {
                    "id": f"mvtec-loco-{item['id'].replace('/', '-')}",
                    "image": str(Path(item["path"]).relative_to("datasets")),
                    "sha256": item["sha256"],
                    "source_id": f"mvtec-loco-ad:{item['id']}",
                    "split": split,
                    "ground_truth": item["kitguard_counts"],
                    "upstream_split": item["upstream_split"],
                    "upstream_kind": item["upstream_kind"],
                    "subgroup": "normal_constant_222"
                    if item["label_status"] == "author_normal_rule"
                    else "quantity_anomaly",
                    "ground_truth_basis": item["ground_truth_basis"],
                    "source_masks": item["source_masks"],
                }
            )
    if len({i["sha256"] for i in cases}) != len(cases):
        raise RuntimeError("Duplicate source image hash in frozen benchmark")
    frozen = {
        "schema_version": 1,
        "name": "KitGuard LOCO screw_bag static counting v1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "dataset_root": "datasets",
        "source_archive_sha256": manifest["archive_sha256"],
        "expected_source_archive_sha256": LOCO_SHA256,
        "full_archive_verification_pending": manifest["full_archive_verification_pending"],
        "defect_config_sha256": manifest["defect_config_sha256"],
        "selection": {
            "seed": LOCO_SELECTION_SEED,
            "sort_key": "SHA256(UTF-8(seed + '|' + original_image_sha256)) ascending",
            "normal_pool": "Official train good for development; official test good for holdout",
            "quantity_pool": "Official test logical_anomalies, exactly one mask / one explicit quantity defect / counts within product scope",
            "development_request": {"normal": 8, "quantity_anomaly": 8},
            "holdout_request": {"normal": 24, "quantity_anomaly": 24},
            "order": "Development first, holdout second; within each split alternate normal then quantity, retaining sorted order",
            "shortfall_policy": "Use available eligible images only; never broaden label interpretation to fill quotas",
            "upstream_test_repartition_note": "The first 8 eligible official-test quantity anomalies are explicitly reassigned to development. Remaining selected quantity anomalies form our custom holdout; this is not the untouched official-test protocol.",
        },
        "actual_subgroup_counts": dict(Counter(f"{i['split']}/{i['subgroup']}" for i in cases)),
        "candidate_counts": {
            "train_normal": len(train_normal),
            "test_normal": len(test_normal),
            "quantity_anomaly": len(quantity),
        },
        "limitations": [
            "Report constant-222 normal images separately from variable-count anomalies; constant guessing cannot establish visual counting skill.",
            "Original full photographs only; no crops, composites or generated images.",
            "Count labels use author definitions and original masks, not model-generated answers or claimed human labeling.",
            "No positive bracket examples; broad class counts do not validate screw length/SKU, actual physical recapture or unseen-factory generalization.",
        ],
        "cases": cases,
    }
    path = output / "benchmark_v1.json"
    if path.exists():
        existing = json.loads(path.read_text())
        if existing["cases"] != cases or existing["selection"] != frozen["selection"]:
            raise RuntimeError("Refusing to overwrite a previously frozen benchmark with different cases")
    else:
        path.write_text(json.dumps(frozen, ensure_ascii=False, indent=2) + "\n")
        path.chmod(0o444)
        checksum_path = output / "benchmark_v1.sha256"
        checksum_path.write_text(sha256(path) + "  benchmark_v1.json\n")
        checksum_path.chmod(0o444)
    print(
        json.dumps(
            {
                "frozen_benchmark": str(path),
                "sha256": sha256(path),
                "actual_subgroup_counts": frozen["actual_subgroup_counts"],
            }
        ),
        flush=True,
    )
    create_nominal_benchmark_v2(path)


def create_nominal_benchmark_v2(v1_path: Path) -> Path:
    """Refine a metric after development without changing preselected images."""
    original = json.loads(v1_path.read_text())
    updated = json.loads(v1_path.read_text())
    updated["name"] = "KitGuard LOCO screw_bag static counting v2 with nominal-order metric"
    updated["selection_frozen_at_utc"] = original["created_at_utc"]
    updated["created_at_utc"] = datetime.now(UTC).isoformat()
    updated["previous_manifest_sha256"] = sha256(v1_path)
    updated["metric_revision"] = {
        "reason": "Add the author's fixed normal order to expose false-ready decisions on actual quantity anomalies, including a model that always guesses 2/2/2/0",
        "timing": "Metric refined after reviewing 8B development results; holdout model inference had not been run when the v2 protocol was adopted",
        "selection_unchanged": True,
        "note": "v1 and all prior development results remain preserved; this is not a claim that v2 metrics were specified before development",
    }
    for case in updated["cases"]:
        case["nominal_requirements"] = {"bolt": 2, "nut": 2, "washer": 2, "bracket": 0}
    for before, after in zip(original["cases"], updated["cases"], strict=True):
        if {k: v for k, v in after.items() if k != "nominal_requirements"} != before:
            raise RuntimeError("Nominal metric revision unexpectedly changed a selected case")
    path = v1_path.with_name("benchmark_v2.json")
    if path.exists():
        previous = json.loads(path.read_text())
        if (
            previous["cases"] != updated["cases"]
            or previous["previous_manifest_sha256"] != updated["previous_manifest_sha256"]
        ):
            raise RuntimeError("Refusing to overwrite a frozen v2 benchmark")
    else:
        path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n")
        path.chmod(0o444)
        checksum_path = path.with_suffix(".sha256")
        checksum_path.write_text(sha256(path) + "  benchmark_v2.json\n")
        checksum_path.chmod(0o444)
    print(
        json.dumps(
            {
                "nominal_metric_manifest": str(path),
                "sha256": sha256(path),
                "unchanged_case_count": len(updated["cases"]),
            }
        ),
        flush=True,
    )
    return path


def extract_received_loco_prefix(root: Path) -> Path:
    """Stage complete PNGs without claiming the partial archive's SHA is verified."""
    from PIL import Image

    destination = root / "staging" / "mvtec_loco_ad"
    if destination.exists():
        status = json.loads((destination / "acquisition_status.json").read_text())
        if status.get("full_archive_verification_pending") is not True:
            raise RuntimeError("Unexpected staging status")
        return destination
    staging = destination.with_name(destination.name + ".extracting")
    if staging.exists():
        raise RuntimeError(f"Prior partial staging preserved: {staging}")
    staging.mkdir(parents=True)

    class ReceivedPrefix(io.RawIOBase):
        def __init__(self):
            self.parts = root / "archives" / ".mvtec_loco_anomaly_detection.tar.xz-download-parts"
            self.index = 0
            self.current = None

        def readable(self):
            return True

        def readinto(self, buffer):
            if self.current is None:
                path = self.parts / f"{self.index * 16777216:012d}.part"
                if not path.exists() or path.stat().st_size != 16777216:
                    return 0
                self.current = path.open("rb")
            count = self.current.readinto(buffer)
            if count:
                return count
            self.current.close()
            self.current = None
            self.index += 1
            return self.readinto(buffer)

        def close(self):
            if self.current is not None:
                self.current.close()
            super().close()

    found = False
    complete_section = False
    source_files = []
    with tarfile.open(fileobj=io.BufferedReader(ReceivedPrefix()), mode="r|xz") as bundle:
        for member in bundle:
            relative = PurePosixPath(member.name)
            if relative.is_absolute() or ".." in relative.parts or member.issym() or member.islnk():
                raise RuntimeError(f"Unsafe archive entry: {member.name}")
            if relative.parts and relative.parts[0] == "screw_bag":
                found = True
            elif found and relative.parts:
                complete_section = True
                break
            else:
                continue
            target = staging.joinpath(*relative.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise RuntimeError(f"Unsupported archive entry: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.extractfile(member) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
            if target.stat().st_size != member.size:
                raise RuntimeError("Staged member size differs from its archive header")
            source_files.append({"path": str(relative), "bytes": member.size, "sha256": sha256(target)})
    if not complete_section:
        raise RuntimeError("Complete screw_bag tar section has not been received")
    expected = {
        "train/good": 360,
        "validation/good": 60,
        "test/good": 122,
        "test/logical_anomalies": 137,
        "test/structural_anomalies": 82,
    }
    observed = Counter()
    verified_pngs = 0
    for path in sorted((staging / "screw_bag").rglob("*.png")):
        with Image.open(path) as im:
            if im.format != "PNG" or im.size != (1600, 1100):
                raise RuntimeError(f"Unexpected original image format/dimensions: {path}")
            im.load()
        verified_pngs += 1
        relative = path.relative_to(staging / "screw_bag")
        if relative.parts[0] in {"train", "validation", "test"}:
            observed["/".join(relative.parts[:2])] += 1
            if relative.parts[1] != "good" and not any(
                (staging / "screw_bag" / "ground_truth" / relative.parts[1] / path.stem).glob("*.png")
            ):
                raise RuntimeError("An anomalous image is missing its original mask")
    if dict(observed) != expected:
        raise RuntimeError(f"Staged image counts differ from the author paper: {dict(observed)}")
    status = {
        "full_archive_verification_pending": True,
        "status": "Complete screw_bag section staged from already received public HTTPS archive prefix; full archive SHA not yet verified",
        "source_url": LOCO_URL,
        "expected_archive_sha256": LOCO_SHA256,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "author_expected_image_counts": expected,
        "actual_image_counts": dict(observed),
        "fully_decoded_original_pngs_including_masks": verified_pngs,
        "files": source_files,
        "later_verification_policy": "Compare every staged source file against the fully SHA-verified archive extraction. Invalidate and rerun prior evaluations if any file differs.",
    }
    (staging / "acquisition_status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n")
    os.replace(staging, destination)
    for path in destination.rglob("*"):
        if path.is_file():
            path.chmod(0o444)
    for path in sorted((p for p in destination.rglob("*") if p.is_dir()), reverse=True):
        path.chmod(0o555)
    destination.chmod(0o555)
    print(
        json.dumps(
            {
                "staged": str(destination),
                "files": len(source_files),
                "pngs_fully_decoded": verified_pngs,
                "full_archive_verification_pending": True,
            }
        ),
        flush=True,
    )
    return destination


def verify_staged_against_full(raw: Path, output: Path) -> None:
    """Keep historical pending manifests; separately prove later byte equality."""
    staged = ROOT / "datasets" / "staging" / "mvtec_loco_ad"
    acquisition = staged / "acquisition_status.json"
    if not acquisition.exists():
        return
    archive = ROOT / "datasets" / "archives" / "mvtec_loco_anomaly_detection.tar.xz"
    if not archive.is_file() or archive.stat().st_size != LOCO_SIZE or sha256(archive) != LOCO_SHA256:
        raise RuntimeError("Full archive must match the pinned size/SHA before certifying staged results")
    recorded = json.loads(acquisition.read_text())
    differences = []
    for item in recorded["files"]:
        source = raw / item["path"]
        prior = staged / item["path"]
        for label, path in (("full", source), ("staged", prior)):
            if not path.is_file() or path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
                differences.append({"source": label, "path": item["path"]})
    benchmarks = []
    pending = output.with_name("mvtec_loco_screw_bag_pending")
    for version in ("v1", "v2"):
        old_path, new_path = pending / f"benchmark_{version}.json", output / f"benchmark_{version}.json"
        if old_path.exists() and new_path.exists():
            old, new = json.loads(old_path.read_text()), json.loads(new_path.read_text())

            def identity(case):
                return {
                    "id": case["id"],
                    "source_id": case["source_id"],
                    "sha256": case["sha256"],
                    "split": case["split"],
                    "ground_truth": case["ground_truth"],
                    "nominal_requirements": case.get("nominal_requirements"),
                    "mask_evidence": [
                        {k: v for k, v in mask.items() if k != "path"} for mask in case["source_masks"]
                    ],
                }

            same = [identity(c) for c in old["cases"]] == [identity(c) for c in new["cases"]]
            if not same:
                differences.append({"source": "benchmark", "path": version})
            benchmarks.append(
                {
                    "version": version,
                    "pending_manifest_sha256": sha256(old_path),
                    "fully_verified_manifest_sha256": sha256(new_path),
                    "same_selected_images_order_splits_labels_and_mask_evidence": same,
                    "historical_selection_frozen_at_utc": old.get(
                        "selection_frozen_at_utc", old["created_at_utc"]
                    ),
                    "fully_verified_manifest_generated_at_utc": new["created_at_utc"],
                    "timestamp_note": "The fully verified manifest was regenerated after development began; its local creation/freeze timestamp is not the original image-selection time. The unchanged historical pending manifest proves the earlier selection.",
                }
            )
    report = {
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "full_archive_verification_pending": False,
        "full_archive_sha256": LOCO_SHA256,
        "full_archive_bytes": LOCO_SIZE,
        "compared_original_files": len(recorded["files"]),
        "differences": differences,
        "staged_development_results_source_integrity_validated": not differences,
        "benchmarks": benchmarks,
        "historical_manifest_policy": "Original pending v1/v2 manifests and prior model runs are preserved unchanged; this report supplies subsequent whole-archive and file-equality evidence. Any difference invalidates prior source-dependent evaluations and requires reruns.",
    }
    path = output / "pending_to_verified_audit.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "staging_full_archive_comparison": str(path),
                "files": len(recorded["files"]),
                "differences": len(differences),
            }
        ),
        flush=True,
    )
    if differences:
        raise RuntimeError(
            "Staged data differ from the fully verified source; prior evaluations must be rerun"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=4, choices=range(1, 17))
    parser.add_argument("--dataset", choices=("screws", "loco"), default="screws")
    parser.add_argument("--max-download-bytes", type=int, default=3_000_000_000)
    parser.add_argument("--inventory-only", action="store_true")
    parser.add_argument(
        "--extract-received-prefix",
        action="store_true",
        help="Stage a fully received screw_bag tar section while full-archive verification remains pending",
    )
    args = parser.parse_args()
    if args.extract_received_prefix and args.dataset != "loco":
        parser.error("--extract-received-prefix applies only to --dataset loco")
    size = SIZE if args.dataset == "screws" else LOCO_SIZE
    if size > args.max_download_bytes and not (args.inventory_only or args.extract_received_prefix):
        raise SystemExit("Pinned archive exceeds the authorized download budget")
    root = ROOT / "datasets"
    archives = root / "archives"
    if args.dataset == "loco":
        provenance = root / "provenance" / "mvtec_loco"
        raw = root / "raw" / "mvtec_loco_ad"
        archives.mkdir(parents=True, exist_ok=True)
        provenance.mkdir(parents=True, exist_ok=True)
        if args.extract_received_prefix:
            staged = extract_received_loco_prefix(root)
            inventory_loco(
                staged, root / "manifests" / "mvtec_loco_screw_bag_pending", archive_verified=False
            )
            return
        if not args.inventory_only:
            sources = {
                "mvtec_dataset_page.html": "https://www.mvtec.com/research-teaching/datasets/mvtec-loco-ad",
                "anomalib_download_adapter.py.txt": LOCO_ADAPTER,
            }
            for name, url in sources.items():
                path = provenance / name
                if not path.exists():
                    with urllib.request.urlopen(url, timeout=30) as response:
                        body = response.read(5_000_001)
                    if len(body) > 5_000_000:
                        raise RuntimeError("Unexpected provenance page size")
                    path.write_bytes(body)
                    path.chmod(0o444)
            archive = archives / "mvtec_loco_anomaly_detection.tar.xz"
            download(archive, args.workers, LOCO_URL, LOCO_SIZE, LOCO_SHA256)
            extract_loco(archive, raw)
        inventory_loco(raw, root / "manifests" / "mvtec_loco_screw_bag")
        return
    provenance = root / "provenance" / "mvtec_screws"
    raw = root / "raw" / "mvtec_screws_v1.0"
    archives.mkdir(parents=True, exist_ok=True)
    provenance.mkdir(parents=True, exist_ok=True)
    if not args.inventory_only:
        for name, url in SOURCES.items():
            path = provenance / name
            if not path.exists():
                with urllib.request.urlopen(url, timeout=30) as response:
                    body = response.read(5_000_001)
                if len(body) > 5_000_000:
                    raise RuntimeError("Unexpected provenance page size")
                path.write_bytes(body)
                path.chmod(0o444)
        archive = archives / "mvtec_screws_v1.0.tar.gz"
        download(archive, args.workers)
        extract(archive, raw)
    inventory(raw, root / "manifests" / "mvtec_screws")


if __name__ == "__main__":
    main()
