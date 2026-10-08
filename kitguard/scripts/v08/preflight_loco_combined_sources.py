"""Exact source/RGB duplicate preflight, without display, models or truth edits.

Only the fixed 24 candidates, registered 112 originals and two reference
source/crop pairs are machine decoded. Historical exposure assertions remain
bound to their original receipt, not re-inferred from later semantic documents.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image
from PIL import __version__ as PILLOW_VERSION

ROOT = Path(__file__).resolve().parents[2]
SEMANTICS = "test-results/v0.8-loco-combined-label-semantics-v1.json"
REGISTRY = "test-results/v0.8-loco-remaining-metadata-audit-v2.json"
MANIFEST = "datasets/manifests/mvtec_loco_screw_bag/manifest.json"
REFERENCES = "docs/v0.8/reference_guarded_freeze_v1/freeze.json"
RGB_PROTOCOL = "sha256(str((width,height)).encode()+b'|RGB|'+image.convert('RGB').tobytes()); no EXIF transpose/resize"


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inside(root, relative):
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Only project-relative paths are allowed")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
        raise ValueError(f"Missing or outside-root input: {relative}")
    return resolved


def rgb_sha(rgb):
    return hashlib.sha256(str(rgb.size).encode() + b"|RGB|" + rgb.tobytes()).hexdigest()


def fingerprint(path):
    before = sha(path)
    with Image.open(path) as original:
        if getattr(original, "n_frames", 1) != 1:
            raise ValueError("Only a single-frame source is permitted")
        original.verify()
    with Image.open(path) as original:
        original.load()
        rgb = original.convert("RGB")
        result = {"sha256": before, "bytes": path.stat().st_size, "size": list(rgb.size),
                  "original_mode": original.mode, "format": original.format,
                  "exif_orientation": original.getexif().get(274),
                  "rgb_sha256": rgb_sha(rgb),
                  "rgb_bytes_sha256": hashlib.sha256(rgb.tobytes()).hexdigest()}
    if sha(path) != before:
        raise ValueError("Image bytes changed during decoding")
    return result


def compare(candidate, comparators):
    """Keep every comparison result; byte and dimension-bound RGB are distinct."""
    matches, no_matches, unavailable = [], [], []
    for other in comparators:
        if candidate.get("error") or other.get("error"):
            unavailable.append(other["key"])
            continue
        methods = []
        if candidate["sha256"] == other["sha256"]:
            methods.append("source_bytes")
        if candidate["rgb_sha256"] == other["rgb_sha256"]:
            methods.append("original_dimension_bound_rgb")
        if methods:
            matches.append({"comparator_key": other["key"], "methods": methods})
        else:
            no_matches.append(other["key"])
    return {"candidate_key": candidate["key"], "matches": matches,
            "no_match_keys": no_matches, "unavailable_keys": unavailable}


def historical_bindings(root, registry):
    # Past hashes belong to the past scan. Current hashes are separately labeled;
    # a drifted document must not rewrite the original 112-photo registration.
    past = {r["path"]: r for r in registry["text_inputs"] + registry["source_receipts"]}
    databases = {r["path"]: r for r in registry["application_metadata"]}
    referenced = sorted({p for groups in registry["exposure"].values() for paths in groups.values() for p in paths})
    result = []
    for path in referenced:
        if path in databases:
            result.append({"path": path, "kind": "historical_database_rows", "historical_receipt": databases[path],
                           "database_reread": False, "current_content_matches_historical": None})
            continue
        old = past.get(path, {}).get("sha256")
        try:
            current = sha(inside(root, path))
        except (OSError, ValueError):
            current = None
        result.append({"path": path, "kind": "historical_text_registration", "historical_sha256": old,
                       "historical_binding": "direct_file_hash" if old else "prior_registry_assertion_only",
                       "current_sha256": current, "current_content_matches_historical": current == old if old and current else None})
    return result


def preflight(root):
    started = datetime.now(UTC).isoformat()
    inputs = {}

    def read(relative, expected=None):
        path = inside(root, relative)
        digest = sha(path)
        if expected is not None and digest != expected:
            raise ValueError(f"Bound metadata SHA changed: {relative}")
        inputs[relative] = digest
        return json.loads(path.read_text())

    semantics, registry, manifest, frozen = [read(p) for p in (SEMANTICS, REGISTRY, MANIFEST, REFERENCES)]
    if semantics.get("schema") != "kitguard.v08.loco-combined-label-semantics-proposal.v1":
        raise ValueError("Wrong semantics proposal")
    if registry.get("schema") != "kitguard.v08.loco-remaining-metadata-audit.v1":
        raise ValueError("Wrong historical exposure registry")
    if len(registry["exposure"]) != registry["registered_exposed_or_selected_count"]:
        raise ValueError("Historical registry size differs")
    if len(registry["exposure"]) != 112 or len(semantics["records"]) != 24:
        raise ValueError("Expected fixed 112 registered plus complete 24 candidates")
    for bound in registry["source_receipts"]:
        read(bound["path"], bound["sha256"])
    for bound in semantics["sources"]:
        # Only JSON metadata dependencies are reread here; PDF/config integrity
        # was checked by the separately bound semantic review.
        if bound["path"] in {REGISTRY, MANIFEST} and inputs[bound["path"]] != bound["sha256"]:
            raise ValueError("Semantics is not bound to this registry/manifest")
    prior_pixels = registry["existing_decoded_pixel_inventory"]
    pixels = read(prior_pixels["path"], prior_pixels["sha256"])["all_original_pixel_hashes"]
    approval = read(frozen["approval"]["path"], frozen["approval"]["sha256"])
    if frozen.get("schema") != "kitguard.v08.reference-guarded.freeze.v1" or set(frozen["references"]) != {"nut", "washer"}:
        raise ValueError("Expected the existing two-reference binding")
    if {a["part"]: a for a in approval["items"]} != {p: r["approval"] for p, r in frozen["references"].items()}:
        raise ValueError("Current approved references differ from bound references")
    sources = {r["sha256"]: r for r in manifest["images"]}
    if len(sources) != len(manifest["images"]) or not set(registry["exposure"]) <= sources.keys():
        raise ValueError("Original source index is incomplete or duplicated")
    semantic_ids = {r["source_id"] for r in semantics["records"]}
    if len(semantic_ids) != 24 or semantic_ids != {r["source_id"] for r in registry["mixed_quantity_metadata_only"]["records"]}:
        raise ValueError("Candidate set differs from complete registered proposal")
    records, cache = [], {}

    def add(key, path, expected_sha, expected_rgb=None, **metadata):
        item = {"key": key, "path": path, "expected_sha256": expected_sha, **metadata}
        try:
            resolved = inside(root, path)
            if resolved not in cache:
                cache[resolved] = fingerprint(resolved)
            item.update(cache[resolved])
            if item["sha256"] != expected_sha:
                raise ValueError("Original bytes differ from registered SHA")
            if expected_rgb is not None and item["rgb_sha256"] != expected_rgb:
                raise ValueError("Decoded RGB differs from previously registered pixel SHA")
            item["registered_rgb_sha256"] = expected_rgb
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            item["error"] = f"{type(exc).__name__}: {exc}"
        records.append(item)
        return item

    candidates = []
    for item in semantics["records"]:
        source = sources.get(item["source_sha256"])
        if source is None or source["id"] != item["source_id"] or source["path"] != item["source_path"]:
            raise ValueError("Candidate identity differs from author manifest")
        if source["label_status"] != "unresolved" or source["kitguard_counts"] is not None:
            raise ValueError("Historical unresolved truth was modified")
        candidates.append(add("candidate:" + item["source_id"], item["source_path"], item["source_sha256"],
                              pixels[item["source_sha256"]], role="candidate", source_id=item["source_id"]))
    comparators = []
    for digest, registrations in sorted(registry["exposure"].items()):
        source = sources[digest]
        comparators.append(add("registered:" + source["id"], source["path"], digest, pixels[digest],
                               role="registered_original", source_id=source["id"], registrations=registrations))
    for part, reference in sorted(frozen["references"].items()):
        for role in ("source", "crop"):
            comparators.append(add(f"reference:{part}:{role}", reference[role]["path"], reference[role]["sha256"],
                                   reference[role + "_rgb_sha256"], role="reference_" + role, part=part))
    comparisons = [compare(c, comparators) for c in candidates]
    internal = [compare(c, candidates[i + 1:]) for i, c in enumerate(candidates)]
    integrity_errors = [{"key": r["key"], "error": r["error"]} for r in records if r.get("error")]
    all_matches = [row for row in comparisons + internal if row["matches"]]
    changed_inputs = [path for path, digest in inputs.items() if sha(inside(root, path)) != digest]
    forbidden = [name for name in ("torch", "mlx", "mlx_vlm", "kitguard") if name in sys.modules]
    if forbidden:
        raise ValueError("A model or production module was unexpectedly imported")
    clear = not (integrity_errors or all_matches or changed_inputs)
    return {
        "schema": "kitguard.v08.loco-combined-sources.preflight.v1", "started_at": started,
        "finished_at": datetime.now(UTC).isoformat(),
        "status": "passed_no_exact_overlap_in_bound_registry" if clear else "blocked_review_required",
        "scope": "Exact original-byte/RGB overlap against the fixed historical112 and current two reference source/crop pairs only",
        "model_called": False, "images_displayed_or_visually_reviewed": False,
        "machine_pixels_decoded": True, "purpose": "Integrity and exact duplicate checks only",
        "methods_selected_or_frozen": False, "new_truth_written": False,
        "planned_candidates": 24, "retained_candidates": len(candidates), "registered_originals": 112,
        "reference_roles": 4, "unique_image_files_decoded": len(cache), "pillow_version": PILLOW_VERSION,
        "rgb_protocol": RGB_PROTOCOL, "input_sha256": inputs,
        "tool_sha256": sha(Path(__file__).resolve()),
        "historical_registry_checked_at": registry["checked_at"],
        "historical_registration_bindings": historical_bindings(root, registry),
        "historical_application_receipts_not_reread": registry["application_metadata"],
        "records": records, "candidate_vs_registered_and_references": comparisons,
        "candidate_internal_pairs": internal, "overlap_candidate_records": all_matches,
        "integrity_errors": integrity_errors, "metadata_changed_during_check": changed_inputs,
        "forbidden_modules": forbidden,
        "limitations": [
            "Registered range only, not a claim that no person/AI has ever viewed these photos or that VLM pretraining is disjoint.",
            "Exact byte/RGB equality only: resized/lossy/near-duplicate scenes and same physical objects or capture sessions are not certified independent.",
            "Later metadata mentions of source hashes are not silently promoted to historical visual/model exposure.",
            "Historical text hashes are retained separately from current file identity; drift does not rewrite the fixed112 registration.",
            "This machine decode is recorded separately from visual exposure; no model result or new count truth is produced.",
            "Any overlap/error blocks the planned claim; all24 remain, with no silent replacement or exclusion.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Output exists; preserve prior preflight")
    result = preflight(args.project_root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({k: result[k] for k in ("status", "planned_candidates", "retained_candidates",
                                           "registered_originals", "reference_roles", "unique_image_files_decoded")}))
    if result["status"] != "passed_no_exact_overlap_in_bound_registry":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
