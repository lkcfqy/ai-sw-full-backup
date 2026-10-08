"""Prepare, manually lock, and compare a declared capture batch without model calls.

Hashes support traceability and exact-overlap checks. They cannot authenticate
physical capture, independent annotators, or genuinely blind human counting.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
PARTS = ("bolt", "nut", "washer", "bracket")
SCOPES = {"bolt_nut": ("bolt", "nut"), "four_classes": PARTS}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
KNOWN_SOURCES = (
    {"name": "MVTec Screws (all official splits)", "expected_images": 384, "kind": "images",
     "path": "datasets/manifests/mvtec_screws/manifest.json",
     "sha256": "159bbcf94c26eaa1305b2d0f4dada8b902d6cb19710227b2cc2d1fabdf1e6159"},
    {"name": "MVTec LOCO screw_bag (all listed splits)", "expected_images": 761, "kind": "images",
     "path": "datasets/manifests/mvtec_loco_screw_bag/manifest.json",
     "sha256": "76e2ece56c7d24a9e52a9eaad0e856298c8ab979c35653e40efd7a672df0ec17"},
    {"name": "InO-10-190 origin/cropped color/depth PNG variants", "expected_images": 760, "kind": "ino_files",
     "path": "datasets/raw/ino-10-190/SOURCE_MANIFEST.json",
     "sha256": "7417b8e5ce9628aa6bbba8f1e643389cd69a448a8eb5842dfb42ecaca112fa13"},
    {"name": "Registered v0.3 benchmark views (including derived crops)", "expected_images": 76, "kind": "cases",
     "path": "datasets/manifests/v0.3/CANONICAL_NEW_SOURCE_BENCHMARK_V1.json",
     "sha256": "85f331c47d50256e1e98c3b346bef109e30a98e7e101da6ea3f46c9b7b3dcaf2"},
    {"name": "Registered InO bracket views", "expected_images": 20, "kind": "cases",
     "path": "datasets/manifests/v0.4/ino_l_bracket_external_v1/manifest.json",
     "sha256": "83465c4d2b35f072977bd652ca35cfcd7942898cc07c2a10e5796483ff18d27b"},
    {"name": "Registered InO two-bracket view", "expected_images": 1, "kind": "cases",
     "path": "datasets/manifests/v0.4/ino_two_bracket_diagnostic_v1/manifest.json",
     "sha256": "603d26994ba1565de1381293d6782ead26a5eac13eb67dfce38f46116a980c33"},
    {"name": "Registered InO multi-bracket views", "expected_images": 3, "kind": "cases",
     "path": "datasets/manifests/v0.4/ino_l_bracket_full_multi_v1/manifest.json",
     "sha256": "cc18eb6d9cf6e5cf01b2ef26fae3d4f76f0467cef6629b97998cdf309aa7a568"},
    {"name": "Product public demo catalog (including small-part/mixed-screws crops)", "expected_images": 3,
     "kind": "python_catalog", "path": "kitguard/public_demo_catalog.py",
     "sha256": "cc50ea4ed9f3d3c08ea8b59f671403df8961c900e06890aa0e082d1aecb6eddf"},
)


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_bytes(document: dict) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def read(path: Path) -> dict:
    return json.loads(path.read_text())


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def parse_time(value: str) -> datetime:
    timestamp = datetime.fromisoformat(value)
    if timestamp.tzinfo is None:
        raise ValueError("Timestamp must include a timezone")
    return timestamp.astimezone(UTC)


def safe_child(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Unsafe relative path: {relative}")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes directory: {relative}")
    return resolved


def image_identity(path: Path) -> dict:
    raw_hash = sha(path)
    with Image.open(path) as original:
        if original.format not in {"PNG", "JPEG"}:
            raise ValueError(f"Expected JPEG/PNG: {path.name}")
        if getattr(original, "n_frames", 1) != 1:
            raise ValueError(f"Multi-frame images are not supported: {path.name}")
        encoded_size = list(original.size)
        orientation = original.getexif().get(274)
        rgb = ImageOps.exif_transpose(original).convert("RGB")
        pixel_hash = hashlib.sha256(f"{rgb.width},{rgb.height},RGB\n".encode() + rgb.tobytes()).hexdigest()
        dimensions = list(rgb.size)
    if sha(path) != raw_hash:
        raise ValueError(f"Image changed while reading: {path.name}")
    return {"source_sha256": raw_hash, "normalized_pixel_sha256": pixel_hash,
            "dimensions": dimensions, "encoded_dimensions": encoded_size, "source_exif_orientation": orientation}


def public_source_index(root: Path, sources=KNOWN_SOURCES) -> tuple[set, set, list]:
    raw_hashes, pixel_hashes, coverage = set(), set(), []
    for source in sources:
        manifest = safe_child(root, source["path"])
        report = {"name": source["name"], "manifest": source["path"],
                  "expected_images": source["expected_images"], "raw_hash_records": 0,
                  "normalized_pixel_records": 0, "gaps": []}
        if not manifest.is_file():
            report["gaps"].append("source manifest missing; no overlap coverage for this source")
            coverage.append(report)
            continue
        report["manifest_sha256"] = sha(manifest)
        if report["manifest_sha256"] != source["sha256"]:
            raise ValueError(f"Known public source manifest changed: {source['path']}")
        if source["kind"] == "python_catalog":
            declarations = [n for n in ast.parse(manifest.read_text()).body if isinstance(n, ast.Assign)
                            and any(isinstance(t, ast.Name) and t.id == "CATALOG" for t in n.targets)]
            if len(declarations) != 1:
                raise ValueError("Public demo CATALOG declaration missing/ambiguous")
            catalog = ast.literal_eval(declarations[0].value)
            records = [(safe_child(root / "datasets", row["image"]), row["source_sha256"]) for row in catalog]
            data = None
        else:
            data = read(manifest)
        if source["kind"] == "images":
            records = [(safe_child(root, row["path"]), row["sha256"]) for row in data["images"]]
        elif source["kind"] == "ino_files":
            records = [(safe_child(manifest.parent, row["local_path"]), row["sha256"])
                       for row in data["files"] if Path(row["local_path"]).suffix.lower() in IMAGE_EXTENSIONS]
        elif source["kind"] == "cases":
            records = [(safe_child(root / "datasets", row["image"]), row["sha256"]) for row in data["cases"]]
        elif source["kind"] != "python_catalog":
            raise ValueError("Unknown public-source inventory kind")
        report["raw_hash_records"] = len(records)
        if len(records) != source["expected_images"]:
            report["gaps"].append("manifest image population differs from expected coverage")
        for path, digest in records:
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("Invalid public-source SHA256")
            raw_hashes.add(digest)
            if not path.is_file():
                report["gaps"].append(f"pixel coverage missing file: {path.relative_to(root)}")
                continue
            identity = image_identity(path)
            if identity["source_sha256"] != digest:
                raise ValueError(f"Known public image changed: {path.relative_to(root)}")
            pixel_hashes.add(identity["normalized_pixel_sha256"])
            report["normalized_pixel_records"] += 1
        coverage.append(report)
    return raw_hashes, pixel_hashes, coverage


def write_new_directory(output: Path, writer) -> None:
    if output.exists() or output.is_symlink():
        raise ValueError(f"Refuse to overwrite existing directory: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".capture-batch-", dir=output.parent) as temporary:
        staging = Path(temporary)
        writer(staging)
        if output.exists() or output.is_symlink():
            raise ValueError(f"Output appeared during preparation: {output}")
        staging.rename(output)


def prepare(images_dir: Path, output: Path, *, root: Path = ROOT, sources=KNOWN_SOURCES) -> dict:
    if output.exists() or output.is_symlink():
        raise ValueError(f"Refuse to overwrite existing directory: {output}")
    if not images_dir.is_dir():
        raise ValueError("Images directory does not exist")
    files = sorted(p for p in images_dir.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS)
    if not files:
        raise ValueError("Empty batch: no JPEG/PNG images")
    public_raw, public_pixels, coverage = public_source_index(root, sources)
    raw_seen, pixels_seen, cases, paths = set(), set(), [], {}
    for path in files:
        identity = image_identity(path)
        raw_hash, pixel_hash = identity["source_sha256"], identity["normalized_pixel_sha256"]
        if raw_hash in public_raw or pixel_hash in public_pixels:
            raise ValueError(f"Known public-source image cannot enter a new capture batch: {path.name}")
        if raw_hash in raw_seen or pixel_hash in pixels_seen:
            raise ValueError(f"Duplicate source or EXIF-normalized pixels within batch: {path.name}")
        raw_seen.add(raw_hash)
        pixels_seen.add(pixel_hash)
        case_id = f"capture-{len(cases) + 1:04d}-{raw_hash[:12]}"
        cases.append({"case_id": case_id, "image": f"images/{case_id}{path.suffix.lower()}",
                      "original_filename": path.name, **identity,
                      "ground_truth": {"status": "pending", "counts": dict.fromkeys(PARTS)}})
        paths[case_id] = path
    manifest = {
        "schema": "kitguard.detector-capture-batch.v1", "created_at": utc_now(),
        "status": "pending_manual_annotation", "case_count": len(cases), "cases": cases,
        "public_source_overlap_screen": {
            "coverage": coverage, "all_expected_sources_covered": bool(coverage) and all(not x["gaps"] for x in coverage),
            "raw_hash_records": sum(x["raw_hash_records"] for x in coverage),
            "normalized_pixel_records": sum(x["normalized_pixel_records"] for x in coverage),
            "unique_raw_hashes": len(public_raw), "unique_normalized_pixel_hashes": len(public_pixels),
            "method": "Original file SHA256 plus SHA256(width,height,RGB\\n + EXIF-oriented RGB pixels)",
            "limits": "Exact duplicates only; no near-duplicate, crop, recompression, or capture-authenticity guarantee.",
        },
        "physical_capture_verified": False,
        "note": "Candidate user capture batch. Public-overlap absence is not authentication. Ground truth must be human-entered and locked before predictions.",
    }

    def write(staging):
        (staging / "images").mkdir()
        for case in cases:
            copied = staging / case["image"]
            shutil.copyfile(paths[case["case_id"]], copied)
            if sha(copied) != case["source_sha256"]:
                raise ValueError("Image changed during batch import")
        (staging / "batch_manifest.json").write_bytes(json_bytes(manifest))
        manifest_hash = sha(staging / "batch_manifest.json")
        for pass_name in ("a", "b"):
            template = {"schema": "kitguard.detector-human-counts.v1", "pass": pass_name,
                        "batch_manifest_sha256": manifest_hash, "annotator": None,
                        "counted_without_model_predictions": None,
                        "cases": [{"case_id": c["case_id"], "source_sha256": c["source_sha256"],
                                   "status": "pending", "counts": dict.fromkeys(PARTS)} for c in cases]}
            (staging / f"annotation_{pass_name}.json").write_bytes(json_bytes(template))
    write_new_directory(output, write)
    return manifest


def verify_batch(batch: Path) -> tuple[dict, str]:
    manifest_path = batch / "batch_manifest.json"
    manifest = read(manifest_path)
    if manifest.get("schema") != "kitguard.detector-capture-batch.v1":
        raise ValueError("Unsupported batch manifest")
    cases = manifest["cases"]
    if not cases or manifest["case_count"] != len(cases):
        raise ValueError("Empty or inconsistent batch")
    if len({c["case_id"] for c in cases}) != len(cases) or len({c["source_sha256"] for c in cases}) != len(cases):
        raise ValueError("Duplicate batch case/source identity")
    for case in cases:
        identity = image_identity(safe_child(batch, case["image"]))
        if any(identity[k] != case[k] for k in identity):
            raise ValueError(f"Batch photo changed: {case['case_id']}")
    return manifest, sha(manifest_path)


def checked_counts(counts: dict, scope: str) -> dict:
    if not isinstance(counts, dict) or set(counts) != set(PARTS):
        raise ValueError("Counts must contain exactly bolt/nut/washer/bracket")
    for part in PARTS:
        value = counts[part]
        if part in SCOPES[scope]:
            if type(value) is not int or value < 0:
                raise ValueError(f"Manual {part} count must be a nonnegative integer, not null/pending")
        elif value is not None:
            raise ValueError(f"Out-of-scope {part} must remain null")
    return counts


def validate_annotation(document: dict, manifest: dict, manifest_hash: str, scope: str, pass_name: str) -> dict:
    if document.get("schema") != "kitguard.detector-human-counts.v1" or document.get("pass") != pass_name:
        raise ValueError("Wrong annotation schema/pass")
    if document.get("batch_manifest_sha256") != manifest_hash:
        raise ValueError("Annotation batch hash mismatch")
    if not isinstance(document.get("annotator"), str) or not document["annotator"].strip():
        raise ValueError("Human annotator declaration is required")
    if document.get("counted_without_model_predictions") is not True:
        raise ValueError("Human must declare counting without model predictions")
    cases = document["cases"]
    by_id = {case["case_id"]: case for case in cases}
    if len(by_id) != len(cases) or set(by_id) != {case["case_id"] for case in manifest["cases"]}:
        raise ValueError("Annotations must include every batch case exactly once")
    result = {}
    for case in manifest["cases"]:
        row = by_id[case["case_id"]]
        if row.get("source_sha256") != case["source_sha256"] or row.get("status") != "complete":
            raise ValueError("Annotation source mismatch or pending case")
        result[case["case_id"]] = checked_counts(row["counts"], scope)
    return result


def lock(batch: Path, scope: str, source_declaration: str, capture_session: str) -> dict:
    target, receipt = batch / "locked_ground_truth.json", batch / "locked_ground_truth.sha256"
    if target.exists() or receipt.exists() or target.is_symlink() or receipt.is_symlink():
        raise ValueError("Ground truth already locked or partial lock exists; never overwrite it")
    if scope not in SCOPES or not source_declaration.strip() or not capture_session.strip():
        raise ValueError("Explicit scope, source declaration and capture session are required")
    manifest, manifest_hash = verify_batch(batch)
    documents = {p: read(batch / f"annotation_{p}.json") for p in ("a", "b")}
    validated = {p: validate_annotation(d, manifest, manifest_hash, scope, p) for p, d in documents.items()}
    if validated["a"] != validated["b"]:
        raise ValueError("The two manual counting passes disagree; resolve before locking")
    locked = {
        "schema": "kitguard.detector-locked-counts.v1", "locked_at": utc_now(), "scope": scope,
        "batch_manifest_sha256": manifest_hash,
        "annotation_files": [{"path": f"annotation_{p}.json", "sha256": sha(batch / f"annotation_{p}.json"),
                              "annotator_declaration": documents[p]["annotator"]} for p in ("a", "b")],
        "source_declaration": source_declaration.strip(), "capture_session_declaration": capture_session.strip(),
        "declaration_status": "user_statement_not_independently_authenticated",
        "blind_counting_status": "two_matching_manual_declarations_not_independent_blinding_certification",
        "physical_capture_verified": False,
        "cases": [{"case_id": c["case_id"], "source_sha256": c["source_sha256"],
                   "counts": validated["a"][c["case_id"]]} for c in manifest["cases"]],
        "public_source_overlap_screen": manifest["public_source_overlap_screen"],
        "note": "Hash receipts detect later changes relative to the receipt; they are not signatures, proof of physical capture, or proof that humans did not see predictions.",
    }
    with target.open("xb") as stream:
        stream.write(json_bytes(locked))
    with receipt.open("x") as stream:
        stream.write(sha(target) + "\n")
    return locked


def verify_lock(batch: Path) -> tuple[dict, dict, str]:
    manifest, manifest_hash = verify_batch(batch)
    path = batch / "locked_ground_truth.json"
    digest = sha(path)
    if (batch / "locked_ground_truth.sha256").read_text().strip() != digest:
        raise ValueError("Locked ground truth hash mismatch")
    locked = read(path)
    if locked.get("schema") != "kitguard.detector-locked-counts.v1" or locked["batch_manifest_sha256"] != manifest_hash:
        raise ValueError("Locked batch manifest changed")
    scope = locked["scope"]
    if scope not in SCOPES:
        raise ValueError("Invalid locked scope")
    if {c["case_id"] for c in locked["cases"]} != {c["case_id"] for c in manifest["cases"]}:
        raise ValueError("Locked case population changed")
    expected = {c["case_id"]: c["counts"] for c in locked["cases"]}
    if len(expected) != len(locked["cases"]):
        raise ValueError("Duplicate locked case")
    if {c["case_id"]: c["source_sha256"] for c in locked["cases"]} != {
            c["case_id"]: c["source_sha256"] for c in manifest["cases"]}:
        raise ValueError("Locked source identity changed")
    for pass_name, file in zip(("a", "b"), locked["annotation_files"], strict=True):
        if file["path"] != f"annotation_{pass_name}.json" or sha(batch / file["path"]) != file["sha256"]:
            raise ValueError("Manual annotation changed after lock")
        if validate_annotation(read(batch / file["path"]), manifest, manifest_hash, scope, pass_name) != expected:
            raise ValueError("Locked counts do not match preserved manual annotations")
    return manifest, locked, digest


def validate_prediction(prediction: dict, case: dict, locked: dict) -> tuple[dict, tuple]:
    if prediction.get("schema") != "kitguard.public-detector.single-photo.v1":
        raise ValueError("Unsupported prediction schema")
    if parse_time(prediction["created_at"]) <= parse_time(locked["locked_at"]):
        raise ValueError("Prediction timestamp must be later than ground-truth lock")
    if prediction.get("image_size") != case["dimensions"] or prediction.get("decision") is not None:
        raise ValueError("Prediction dimensions/decision mismatch")
    if prediction.get("unsupported_classes") != ["washer", "bracket"]:
        raise ValueError("Unexpected detector class coverage")
    if prediction.get("model") != "fasterrcnn_mobilenet_v3_large_320_fpn":
        raise ValueError("Unsupported prediction model")
    if prediction.get("coordinate_frame") != (
            "absolute pixel xyxy in EXIF-oriented RGB image; origin upper-left; x right, y down"):
        raise ValueError("Prediction coordinate frame is not the fixed CLI frame")
    checkpoint_hash = prediction.get("checkpoint_sha256")
    if (not isinstance(checkpoint_hash, str) or len(checkpoint_hash) != 64
            or any(c not in "0123456789abcdef" for c in checkpoint_hash)):
        raise ValueError("Prediction checkpoint SHA256 missing/invalid")
    threshold = prediction.get("threshold")
    if type(threshold) not in (int, float) or not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("Invalid prediction threshold")
    if __package__:
        from .predict_public_detector import summarize_predictions
    else:
        from predict_public_detector import summarize_predictions
    predictions = prediction["predictions"]
    summary = summarize_predictions([p["label"] for p in predictions], [p["bbox_xyxy"] for p in predictions],
                                    [p["score"] for p in predictions], threshold, tuple(case["dimensions"]))
    if prediction.get("counts") != summary["counts"]:
        raise ValueError("Prediction counts do not match fixed-threshold boxes")
    return summary["counts"], (checkpoint_hash, threshold)


def evaluate(batch: Path, predictions_dir: Path, output: Path) -> dict:
    if output.exists() or output.is_symlink():
        raise ValueError(f"Refuse to overwrite evaluation: {output}")
    manifest, locked, lock_hash = verify_lock(batch)
    if not predictions_dir.is_dir():
        raise ValueError("Predictions directory does not exist")
    cases = {c["source_sha256"]: c for c in manifest["cases"]}
    truth = {c["case_id"]: c["counts"] for c in locked["cases"]}
    predictions = {}
    for path in sorted(predictions_dir.glob("*.json")):
        document = read(path)
        source_hash = document.get("source_sha256")
        if source_hash not in cases:
            raise ValueError(f"Prediction is not a locked batch source: {path.name}")
        if source_hash in predictions:
            raise ValueError(f"Duplicate predictions for one batch source: {path.name}")
        predictions[source_hash] = (document, path)
    results, identities = [], set()
    for source_hash, case in cases.items():
        row = {"case_id": case["case_id"], "source_sha256": source_hash,
               "ground_truth": truth[case["case_id"]], "status": "incomplete", "reason": "prediction_missing"}
        if source_hash in predictions:
            document, path = predictions[source_hash]
            row.update({"prediction_file": path.name, "prediction_file_sha256": sha(path)})
            if document.get("status") == "failed":
                row["reason"] = "prediction_failed"
                row["failure_declaration"] = str(document.get("error", "unspecified"))
            else:
                try:
                    counts, identity = validate_prediction(document, case, locked)
                    identities.add(identity)
                    if locked["scope"] == "four_classes":
                        raise ValueError("Current detector does not support locked four-class scope")
                    row["predicted_counts"] = counts
                    exact = all(counts[p] == truth[case["case_id"]][p] for p in SCOPES[locked["scope"]])
                    row["status"] = "accurate" if exact else "inaccurate"
                    row["reason"] = "all_in_scope_counts_match" if exact else "count_mismatch"
                except (ValueError, KeyError, TypeError) as exc:
                    row["reason"] = f"prediction_invalid_or_unsupported: {exc}"
        results.append(row)
    if len(identities) > 1:
        raise ValueError("Mixed checkpoint/threshold predictions cannot be compared as one frozen model")
    accurate = sum(r["status"] == "accurate" for r in results)
    inaccurate = sum(r["status"] == "inaccurate" for r in results)
    incomplete = len(results) - accurate - inaccurate
    identity = next(iter(identities)) if identities else (None, None)
    result = {
        "schema": "kitguard.detector-capture-comparison.v1", "created_at": utc_now(),
        "locked_ground_truth_sha256": lock_hash, "scope": locked["scope"],
        "checkpoint_sha256": identity[0], "threshold": identity[1],
        "total_cases": len(results), "accurate": accurate, "inaccurate": inaccurate, "incomplete": incomplete,
        "completed": accurate + inaccurate, "exact_count_rate_all_cases": accurate / len(results),
        "exact_count_rate_completed_cases": accurate / (accurate + inaccurate) if accurate + inaccurate else None,
        "full_denominator_preserved": True, "cases": results,
        "source_declaration": locked["source_declaration"], "capture_session_declaration": locked["capture_session_declaration"],
        "physical_capture_verified": False,
        "public_source_overlap_screen": locked["public_source_overlap_screen"],
        "conclusion": "Count comparison on this user-declared capture batch only; not authenticated field accuracy, independent blind-test certification, SKU validation, or a product safety/release decision.",
    }
    # Reverify after reading predictions so a changed label/photo is not silently used.
    if verify_lock(batch)[2] != lock_hash:
        raise ValueError("Ground-truth lock changed during comparison")
    write_new_directory(output, lambda staging: (staging / "comparison.json").write_bytes(json_bytes(result)))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--images-dir", type=Path, required=True)
    prepare_parser.add_argument("--output-dir", type=Path, required=True)
    lock_parser = sub.add_parser("lock")
    lock_parser.add_argument("--batch-dir", type=Path, required=True)
    lock_parser.add_argument("--scope", choices=tuple(SCOPES), required=True)
    lock_parser.add_argument("--source-declaration", required=True)
    lock_parser.add_argument("--capture-session", required=True)
    evaluate_parser = sub.add_parser("evaluate")
    evaluate_parser.add_argument("--batch-dir", type=Path, required=True)
    evaluate_parser.add_argument("--predictions-dir", type=Path, required=True)
    evaluate_parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            result = prepare(args.images_dir, args.output_dir)
            summary = {"output": str(args.output_dir), "cases": result["case_count"],
                       "public_source_overlap_screen": result["public_source_overlap_screen"]}
        elif args.command == "lock":
            result = lock(args.batch_dir, args.scope, args.source_declaration, args.capture_session)
            summary = {"locked": str(args.batch_dir / "locked_ground_truth.json"), "scope": result["scope"],
                       "cases": len(result["cases"]), "locked_at": result["locked_at"]}
        else:
            result = evaluate(args.batch_dir, args.predictions_dir, args.output_dir)
            summary = {k: result[k] for k in ("total_cases", "accurate", "inaccurate", "incomplete")}
            summary["output"] = str(args.output_dir / "comparison.json")
    except (ValueError, KeyError, OSError, TypeError) as exc:
        parser.exit(1, f"Batch operation refused: {exc}\n")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
