"""Trace all existing two-category quantity labels without opening image pixels.

This produces a proposal receipt, not a new accepted benchmark or modified truth.
Original mask bytes are hashed; pixel-value lists come from the prior verified
archive manifest. No pixel decoder, model, image viewer or sample selection runs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def audit(root):
    manifest_path = root / "datasets/manifests/mvtec_loco_screw_bag/manifest.json"
    raw_index_path = root / "datasets/manifests/mvtec_loco_screw_bag/raw_files_sha256.json"
    exposure_path = root / "test-results/v0.8-loco-remaining-metadata-audit-v2.json"
    paper_path = root / "datasets/provenance/mvtec_loco/original_paper.pdf"
    paper_text = root / "test-results/v0.8-loco-author-paper-text.txt"
    manifest, raw_index = read(manifest_path), read(raw_index_path)
    config_path = root / manifest["defect_config_path"]
    config = {r["pixel_value"]: r for r in read(config_path)}
    raw_hashes = {r["path"]: r["sha256"] for r in raw_index}
    if sha(config_path) != manifest["defect_config_sha256"] or manifest["full_archive_verification_pending"]:
        raise ValueError("Author annotation config/full-archive verification missing")
    exposure = read(exposure_path)["exposure"]
    expected_codes = {frozenset((249, 241)), frozenset((247, 243)), frozenset((248, 240)), frozenset((246, 242))}
    base = {"bolt": 2, "nut": 2, "washer": 2, "bracket": 0}
    records = []
    for record in manifest["images"]:
        masks = record["source_masks"]
        names = [name for mask in masks for name in mask["defect_names"]]
        if len(names) <= 1 or not all(name in manifest["quantity_defect_mapping"] for name in names):
            continue
        if record["upstream_kind"] != "logical_anomalies" or record["label_status"] != "unresolved" or record["kitguard_counts"] is not None:
            raise ValueError("Historical unresolved label changed")
        if len(masks) != 2 or any(len(m["pixel_values"]) != 1 or len(m["defect_names"]) != 1 for m in masks):
            raise ValueError("Not exactly two single-defect masks")
        code_pair = frozenset(m["pixel_values"][0] for m in masks)
        if code_pair not in expected_codes:
            raise ValueError("Unexpected combined-quantity code pair")
        source = Path(record["path"])
        # Author's source and GT stem relationship, not inference from image appearance.
        expected_dir = root / source.parent.parent.parent / "ground_truth" / "logical_anomalies" / source.stem
        actual_files = {p.resolve() for p in expected_dir.glob("*.png")}
        declared_files = {(root / m["path"]).resolve() for m in masks}
        if actual_files != declared_files:
            raise ValueError("Missing/unregistered additional mask")
        deltas = []
        for mask in masks:
            path = root / mask["path"]
            code = mask["pixel_values"][0]
            name = mask["defect_names"][0]
            if config[code]["defect_name"] != name or sha(path) != mask["sha256"] or raw_hashes[mask["path"]] != mask["sha256"]:
                raise ValueError("Original mask bytes/author config lineage differs")
            part, delta = manifest["quantity_defect_mapping"][name]
            deltas.append({"part": part, "delta": delta, "pixel_value": code, "defect_name": name,
                           "mask": mask["path"], "mask_sha256": mask["sha256"]})
        if {d["part"] for d in deltas} != {"nut", "washer"} or sum(d["delta"] for d in deltas) != 0:
            raise ValueError("Defects are not distinct-category equal replacement deltas")
        proposed = dict(base)
        for delta in deltas:
            proposed[delta["part"]] += delta["delta"]
        if record["sha256"] in exposure:
            raise ValueError("A combined-quantity photo already appears in registered exposure")
        records.append({"source_id": record["id"], "source_path": record["path"], "source_sha256": record["sha256"],
                        "original_label_status": "unresolved", "original_counts": None,
                        "actual_mask_count": len(actual_files), "other_registered_defects": [], "deltas": deltas,
                        "proposed_author_derived_counts_not_frozen": proposed,
                        "within_order_scope_0_to_3": all(0 <= n <= 3 for n in proposed.values()),
                        "observation_count_4_should_not_be_clipped_or_excluded": max(proposed.values()) == 4})
    groups = Counter(tuple(r["proposed_author_derived_counts_not_frozen"][p] for p in base) for r in records)
    if len(records) != 24 or sorted(groups.values()) != [6, 6, 6, 6]:
        raise ValueError("Expected complete 24-picture metadata family")
    sources = [manifest_path, raw_index_path, exposure_path, config_path, paper_path, paper_text,
               root / "datasets/raw/mvtec_loco_ad/screw_bag/readme.txt"]
    return {"schema": "kitguard.v08.loco-combined-label-semantics-proposal.v1", "checked_at": datetime.now(UTC).isoformat(),
            "status": "author_derived_count_mapping_supported_proposal_only", "new_truth_accepted_or_written": False,
            "new_holdout_selected_or_frozen": False, "image_or_mask_pixels_decoded_this_check": False,
            "model_called": False, "registered_unexposed_photos": 24, "original_masks_byte_hash_verified": 48,
            "every_photo_exactly_two_distinct_category_quantity_defects": True,
            "other_registered_defects_count": 0, "in_order_scope_photos": 12, "count4_photos": 12,
            "proposed_full_denominator": 24, "proposed_subgroups": [{"counts": dict(zip(base, k, strict=True)), "photos": n} for k, n in sorted(groups.items())],
            "reasoning": ["Paper section 3.1 defines the normal base as two nuts/two washers/one long and one short screw.",
                          "Paper section 3.2 states that all present anomalies have ground-truth annotations.",
                          "Appendix D/Table 12 explicitly maps GT gray values to named additional/missing quantities; defects_config.json independently agrees.",
                          "Each actual per-image GT directory contains exactly the two declared masks, each with one previously verified nonzero defect value on a different category.",
                          "Therefore base plus the two distinct-category quantities is a supported author-derived projection, not object counting from filenames or mask component areas.",
                          "The paper does not publish a four-class count field or an explicit algebraic mixed-count equation; additivity is the project's stated derivation under the author's label completeness, not a verbatim author count annotation."],
            "records": records, "sources": [{"path": str(p.relative_to(root)), "sha256": sha(p)} for p in sources],
            "limitations": ["Existing truth remains unresolved. A future protocol must separately approve/freeze this derivation before any model results are read.",
                            "Retained pixel-value inventories are verified against original mask SHA; this pass does not repeat pixel decoding or inspect photo content.",
                            "No physical/session IDs exist; same dataset/domain and unknown pretrained exposure remain.",
                            "Count4 is a valid observation value but cannot equal a valid order's <=3 requirement. Include these 12 in count/error/recapture analysis; do not clip or drop them.",
                            "Full24 all-anomaly evaluation needs fixed normal controls and per-group reporting to expose always-reject behavior."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Output exists")
    result = audit(ROOT)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("status", "registered_unexposed_photos", "original_masks_byte_hash_verified", "in_order_scope_photos", "count4_photos")}))


if __name__ == "__main__":
    main()
