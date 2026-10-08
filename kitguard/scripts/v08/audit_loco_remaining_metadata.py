"""Read metadata only: LOCO source availability and registered exposure, never select images.

No PIL/image decoding/model imports. Existing photo hashes are read from the author
manifest; only textual registries are inspected. Remaining means no registered use,
not proof that nobody ever viewed a file or that the VLM never pretrained on it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = "datasets/manifests/mvtec_loco_screw_bag/manifest.json"
PRIOR = "datasets/derived/v0.7/public_paired_v1/selection_audit.json"
PUBLIC51 = "datasets/derived/v0.7/public_paired_v1/manifest.json"
CURRENT = "evaluation-runs/v0.8/reference_guarded_v1"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def profile(rows):
    c = Counter((r["upstream_split"], r["upstream_kind"], r["label_status"]) for r in rows)
    return [{"split": k[0], "kind": k[1], "label_status": k[2], "images": n} for k, n in sorted(c.items())]


def inspect(root):
    manifest = read(root / MANIFEST)
    photos = {r["sha256"]: r for r in manifest["images"]}
    if len(photos) != 761 or len({r["id"] for r in photos.values()}) != 761:
        raise ValueError("Unexpected author photo denominator/duplicate raw hash")
    config_path = root / manifest["defect_config_path"]
    if sha(config_path) != manifest["defect_config_sha256"]:
        raise ValueError("Author defect config changed")
    config = {r["pixel_value"]: r["defect_name"] for r in read(config_path)}
    for record in photos.values():
        for mask in record["source_masks"]:
            if [config[v] for v in mask["pixel_values"]] != mask["defect_names"]:
                raise ValueError("Retained mask names do not match author label config")
    usage = defaultdict(lambda: defaultdict(set))
    prior = read(root / PRIOR)
    for digest, sources in prior["exposure"].items():
        if digest in photos:
            usage[digest]["prior_conservative_exposure_registry"].update(sources)
    for case in read(root / PUBLIC51)["cases"]:
        if case["source_sha256"] in photos:
            usage[case["source_sha256"]]["frozen_public51_observed"].add(PUBLIC51)
    candidates = {}
    for path in (root / "evaluation-runs").rglob("*"):
        relative = str(path.relative_to(root))
        if not path.is_file() or "source_snapshot" in path.parts or "cases" in path.parts:
            continue
        if relative.startswith(CURRENT + "/") and path.name != "manifest.json":
            continue  # Never inspect current candidate prefixes, raw outputs or analysis.
        if path.name in {"manifest.json", "development_manifest.json"}:
            candidates[path] = "evaluation_selected_manifest"
        elif path.name.startswith("predictions") and path.suffix in {".json", ".jsonl"}:
            candidates[path] = "recorded_model_attempt"
        elif path.parent == root / "evaluation-runs" and path.suffix == ".json":
            candidates[path] = "legacy_evaluation_record"
    for path in (root / "test-results/browser").rglob("*"):
        if path.is_file() and path.suffix in {".json", ".jsonl", ".md"}:
            candidates[path] = "browser_or_visual_record"
    for path in (root / "docs").rglob("*.md"):
        if "source_snapshot" not in path.parts and not path.name.startswith("LOCO_REMAINING"):
            candidates[path] = "documented_use_or_review_conservative"
    for folder in ("class_reference_dev_v1", "class_reference_dev_v2"):
        for path in (root / "datasets/derived/v0.8" / folder).glob("*.json"):
            candidates[path] = "reference_selection_or_review"
    # The actual local supervised detector datasets contain no LOCO. Read only their
    # selected train/val/test records, not an all-source candidate inventory.
    for path in (root / "datasets/derived/public_detector_v1").glob("*.json"):
        if path.stem in {"train", "val", "test"}:
            candidates[path] = "local_detector_selected_dataset"
    for path in (root / "training-runs").rglob("*.json"):
        if path.name == "protocol.json" or ("data_bindings" in path.parts and path.name in {"train.json", "validation.json", "val.json"}):
            candidates[path] = "local_detector_training_binding"
    receipts = []
    for path, category in sorted(candidates.items()):
        text = path.read_text(errors="replace")
        matches = set(re.findall(r"\b[a-f0-9]{64}\b", text)) & photos.keys()
        for digest, record in photos.items():
            suffix = record["path"].split("screw_bag/", 1)[1]
            if f"screw_bag/{suffix}" in text or "mvtec-loco-screw_bag-" + suffix[:-4].replace("/", "-") in text:
                matches.add(digest)
        relative = str(path.relative_to(root))
        for digest in matches:
            usage[digest][category].add(relative)
        receipts.append({"path": relative, "sha256": sha(path), "category": category, "matched_photos": len(matches)})
    database_receipts = []
    for path in sorted(root.glob("data*/kitguard.sqlite3")):
        with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as conn:
            rows = conn.execute("SELECT id,body FROM orders ORDER BY id").fetchall()
        relative = str(path.relative_to(root))
        text = "\n".join(body for _id, body in rows)
        matches = set(re.findall(r"\b[a-f0-9]{64}\b", text)) & photos.keys()
        for digest, record in photos.items():
            suffix = record["path"].split("screw_bag/", 1)[1]
            if f"screw_bag/{suffix}" in text:
                matches.add(digest)
        for digest in matches:
            usage[digest]["read_only_application_order_metadata"].add(relative)
        database_receipts.append({"path": relative, "orders_read": len(rows), "matched_photos": len(matches),
                                  "ordered_rows_sha256": hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode()).hexdigest()})
    pixel_path = "datasets/manifests/v0.3/source_grouped_v2/decoded_pixel_duplicate_audit.json"
    pixel_receipt = read(root / pixel_path)
    pixels = pixel_receipt["all_original_pixel_hashes"]
    if not photos.keys() <= pixels.keys() or len({pixels[d] for d in photos}) != 761:
        raise ValueError("Existing decoded-pixel inventory does not show all unique LOCO sources")
    remaining = [r for digest, r in photos.items() if digest not in usage]
    unresolved = [r for r in remaining if r["label_status"] == "unresolved"]
    combinations = Counter(tuple(name for mask in r["source_masks"] for name in mask["defect_names"]) for r in unresolved)
    mixed = []
    for record in unresolved:
        labels = [name for mask in record["source_masks"] for name in mask["defect_names"]]
        if len(labels) > 1 and all(name in manifest["quantity_defect_mapping"] for name in labels):
            # A hypothesis, never written back as accepted truth or used to choose a holdout.
            conditional = {"bolt": 2, "nut": 2, "washer": 2, "bracket": 0}
            for label in labels:
                part, delta = manifest["quantity_defect_mapping"][label]
                conditional[part] += delta
            mixed.append({"source_id": record["id"], "source_sha256": record["sha256"], "labels": labels,
                          "mask_count": len(record["source_masks"]), "conditional_additive_counts_not_accepted_truth": conditional,
                          "conditional_order_scope_0_to_3": all(0 <= n <= 3 for n in conditional.values())})
    training = [d for d, categories in usage.items() if any(k.startswith("local_detector") for k in categories)]
    actual = [d for d, categories in usage.items() if "recorded_model_attempt" in categories]
    return {"schema": "kitguard.v08.loco-remaining-metadata-audit.v1", "checked_at": datetime.now(UTC).isoformat(),
            "image_pixels_read": False, "model_called": False, "new_holdout_selected": False,
            "author_photo_count": len(photos), "author_profile": profile(list(photos.values())),
            "registered_exposed_or_selected_count": len(usage), "registered_profile": profile([photos[d] for d in usage]),
            "recorded_model_attempt_distinct_photos": len(actual), "local_detector_training_or_selected_overlap": len(training),
            "no_registered_exposure_count": len(remaining), "no_registered_exposure_profile": profile(remaining),
            "remaining_existing_accepted_quantity_truth": sum(r["label_status"] == "author_single_quantity_defect_rule" for r in remaining),
            "remaining_existing_accepted_normal_truth": sum(r["label_status"] == "author_normal_rule" for r in remaining),
            "remaining_unresolved_anomalies": len(unresolved),
            "remaining_unresolved_defect_groups": [{"labels": list(k), "images": n} for k, n in sorted(combinations.items())],
            "mixed_quantity_metadata_only": {"count": len(mixed), "conditional_in_scope": sum(r["conditional_order_scope_0_to_3"] for r in mixed),
                                               "accepted_truth_count": 0, "records": mixed},
            "exposure": {digest: {k: sorted(v) for k, v in sorted(c.items())} for digest, c in sorted(usage.items())},
            "source_receipts": [{"path": p, "sha256": sha(root / p)} for p in (MANIFEST, PRIOR, PUBLIC51, manifest["defect_config_path"])],
            "text_inputs": receipts, "application_metadata": database_receipts,
            "existing_decoded_pixel_inventory": {"path": pixel_path, "sha256": sha(root / pixel_path),
                                                  "loco_covered": 761, "exact_decoded_duplicate_groups": 0,
                                                  "decoded_again_this_audit": False, "near_duplicate_or_session_independence_certified": False},
            "limitations": ["No registered exposure is an exact inventory result, not proof of never viewed; no exhaustive historical UI or human viewing log exists.",
                            "Prior source hashes and metadata-only pixel inventories are not themselves model/view exposure.",
                            "Existing normal/single-quantity accepted labels remain unchanged. Mixed additive counts are conditional metadata hypotheses, not newly accepted labels.",
                            "Images, not physical hardware IDs or sessions, are available; these same-scene public photos are not certified independent physical acquisitions.",
                            "Local supervised datasets contain no LOCO; general VLM pretraining exposure remains unknown.",
                            "Current reference trial content was not read, apart from its previously frozen source-selection manifest."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Output exists; preserve prior audit")
    result = inspect(args.project_root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("author_photo_count", "registered_exposed_or_selected_count", "recorded_model_attempt_distinct_photos", "local_detector_training_or_selected_overlap", "no_registered_exposure_count", "remaining_existing_accepted_quantity_truth", "remaining_existing_accepted_normal_truth", "remaining_unresolved_anomalies")}))


if __name__ == "__main__":
    main()
