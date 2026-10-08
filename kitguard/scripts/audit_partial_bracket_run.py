"""Read-only independent audit of frozen partial-label runs; CPU/Pillow only.

No runner, application, scorer, preparation helper or model module is imported.
The only optional write is a fresh report outside the audited run directory.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import statistics
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageOps

PARTS = ("bolt", "nut", "washer", "bracket")
OUTCOMES = ("C_b", "W_b", "U_b", "E")
PROJECT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError(f"Non-finite JSON constant: {value}")

    return json.loads(Path(path).read_text(), object_pairs_hook=pairs, parse_constant=invalid)


def inside(root, relative):
    root = Path(root).resolve()
    path = Path(relative)
    if path.is_absolute() or not (root / path).resolve().is_relative_to(root):
        raise ValueError(f"Path outside declared root: {relative}")
    result = (root / path).resolve()
    if not result.is_file():
        raise ValueError(f"Missing regular file: {relative}")
    return result


class Checks:
    def __init__(self):
        self.count = 0
        self.failures = []

    def check(self, condition, message):
        self.count += 1
        if not condition:
            self.failures.append(message)

    def equal(self, actual, expected, message):
        self.check(actual == expected, message)


def encoded(image, format="PNG", **options):
    stream = io.BytesIO()
    image.save(stream, format=format, **options)
    return stream.getvalue()


def reconstruct_author_view(case, dataset_root, checks):
    """Use original YOLO rows, independent margin arithmetic and original pixels."""
    prefix = case["id"]
    original = inside(dataset_root, case["source_image"])
    labels = inside(dataset_root, case["annotation"])
    checks.equal(sha(original), case["source_image_sha256"], prefix + ": origin SHA")
    checks.equal(sha(labels), case["annotation_sha256"], prefix + ": author annotation SHA")
    with Image.open(original) as image:
        width, height = image.size
        rgb = image.convert("RGB")
    boxes = []
    for line in labels.read_text().splitlines():
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 5:
            raise ValueError("Author label must have five YOLO fields")
        category = int(fields[0])
        cx, cy, w, h = map(float, fields[1:])
        if category not in range(10) or not all(math.isfinite(x) for x in (cx, cy, w, h)) or min(w, h) <= 0:
            raise ValueError("Invalid original author label")
        normalized = [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]
        checks.check(min(normalized[:2]) >= -1e-6 and max(normalized[2:]) <= 1 + 1e-6,
                     prefix + ": author box must stay inside origin")
        boxes.append((category, [normalized[0] * width, normalized[1] * height,
                                 normalized[2] * width, normalized[3] * height]))
    selected = case.get("selected_author_rows_zero_based")
    if selected is None:
        selected = [i for i, (category, _) in enumerate(boxes) if category == 0]
    checks.check(len(selected) == len(set(selected)) and bool(selected), prefix + ": selected row uniqueness")
    targets = []
    for index in selected:
        category, box = boxes[index]
        checks.equal(category, 0, prefix + ": selected author class is L-bracket")
        checks.check(min(box[2] - box[0], box[3] - box[1]) >= 32, prefix + ": target minimum short side")
        targets.append(box)
    checks.equal(case["ground_truth"], {"bracket": len(targets)}, prefix + ": truth from selected author rows")
    if case["view_kind"] == "full_image":
        checks.equal(len(targets), len(boxes), prefix + ": full image only author L-brackets")
        roi = [0, 0, width, height]
        rebuilt = original.read_bytes()
    else:
        left, top = min(b[0] for b in targets), min(b[1] for b in targets)
        right, bottom = max(b[2] for b in targets), max(b[3] for b in targets)
        margin = min(right - left, bottom - top) / 10
        roi = [math.floor(left - margin), math.floor(top - margin),
               math.ceil(right + margin), math.ceil(bottom + margin)]
        checks.check(roi[0] >= 0 and roi[1] >= 0 and roi[2] <= width and roi[3] <= height,
                     prefix + ": ROI inside source")
        for index, (_, box) in enumerate(boxes):
            if index not in selected:
                touches = roi[0] <= box[2] and roi[2] >= box[0] and roi[1] <= box[3] and roi[3] >= box[1]
                checks.check(not touches, prefix + f": omitted author box {index} must not touch ROI")
        rebuilt = encoded(rgb.crop(roi))
    checks.equal(roi, case["roi_xyxy"], prefix + ": independently recomputed integer ROI")
    checks.equal(digest(rebuilt), case["sha256"], prefix + ": rebuilt source view bytes")
    actual = inside(dataset_root, case["image"])
    checks.equal(sha(actual), digest(rebuilt), prefix + ": stored derived view equals rebuilt view")
    return rebuilt


def independently_normalize(source_bytes):
    with Image.open(io.BytesIO(source_bytes)) as image:
        clean = ImageOps.exif_transpose(image).convert("RGB")
        clean.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
        jpeg = encoded(clean, "JPEG", quality=95)
    with Image.open(io.BytesIO(jpeg)) as image:
        prepared = ImageOps.exif_transpose(image).convert("RGB")
        prepared.thumbnail((1536, 1536), Image.Resampling.LANCZOS)
        png = encoded(prepared)
        rotated = encoded(prepared.transpose(Image.Transpose.ROTATE_90))
    return jpeg, png, rotated


def inventory_counts(inventory):
    objects = inventory["objects"]
    uncertain = set(inventory["uncertain_parts"])
    if not uncertain and (inventory["issues"] or inventory["action"]["kind"] != "none"):
        uncertain = set(PARTS)
    if not uncertain.issubset(PARTS):
        raise ValueError("Inventory has an unknown category")
    counts = Counter(item["part"] for item in objects)
    if not set(counts).issubset(PARTS):
        raise ValueError("Inventory object has an unknown category")
    return {part: None if part in uncertain else counts[part] for part in PARTS}


def outcome(count, author_count):
    if count is None:
        return "U_b"
    if type(count) is not int or not 0 <= count <= 100:
        raise ValueError("Predicted count must be an integer or null")
    return "C_b" if count == author_count else "W_b"


def recompute_case(case, row, checks):
    prefix = case["id"]
    author_count = case["ground_truth"]["bracket"]
    observation = row.get("observation")
    error = row.get("error")
    category, clear, first = "E", None, None
    has_first = False
    diagnostics = row.get("observation_diagnostics") or {}
    passes = diagnostics.get("passes", [])
    if passes:
        checks.equal(passes[0]["transform"], "original", prefix + ": actual first frame")
        first = inventory_counts(passes[0]["inventory"])["bracket"]
        has_first = True
    if error is None:
        if not isinstance(observation, dict):
            raise ValueError("A no-error case must retain its observation")
        observed = observation["observed"]
        checks.equal(set(observed), set(PARTS), prefix + ": complete predicted keys")
        for value in observed.values():
            outcome(value, author_count)
        category = outcome(observed["bracket"], author_count)
        clear = all(observed[p] is not None for p in PARTS) and not observation["issues"] and observation["action"]["kind"] == "none"
        verification = observation["verification"]
        checks.equal(verification["mode"], "spatial_consensus", prefix + ": selected observer mode")
        checks.equal(len(passes), 2, prefix + ": actual two-pass diagnostics")
        original, rotated = (inventory_counts(p["inventory"]) for p in passes)
        for p, expected in zip(verification["passes"], (original, rotated), strict=True):
            checks.equal(p["observed"], expected, prefix + ": saved pass derived from actual inventory")
        expected = {p: original[p] if original[p] == rotated[p] else None for p in PARTS}
        identity = observation.get("identity_verification")
        if identity:
            for part in identity["blocked_categories"]:
                expected[part] = None
        checks.equal(observed, expected, prefix + ": final counts derived from saved two passes and identity blocks")
        checks.check(has_first, prefix + ": preserve real first pass")
    first_outcome = outcome(first, author_count) if has_first else None
    checks.equal(row["outcome"], category, prefix + ": independently recomputed outcome")
    checks.equal(row["app_clear"], clear, prefix + ": independently recomputed application clarity")
    checks.equal(row.get("first_pass_bracket"), first, prefix + ": first-pass bracket")
    checks.equal(row.get("first_pass_outcome"), first_outcome, prefix + ": first-pass outcome")
    if error is None:
        checks.equal(row["bracket_prediction"], observation["observed"]["bracket"], prefix + ": final bracket field")
    return {"outcome": category, "app_clear": clear, "first_pass_outcome": first_outcome,
            "view_kind": case["view_kind"], "author_count": author_count,
            "execution_status": row["execution_status"], "elapsed_ms": row["elapsed_ms"]}


def audit_inputs(case, row, run_dir, dataset_root, checks):
    prefix = case["id"]
    rebuilt = reconstruct_author_view(case, dataset_root, checks)
    jpeg, png, rotated = independently_normalize(rebuilt)
    for key in ("source_sha256_before", "source_sha256_after"):
        checks.equal(row.get(key), digest(rebuilt), prefix + ": " + key)
    if row.get("normalized_input") is None:
        checks.check(bool(row.get("error")), prefix + ": missing normalized input requires error")
        return {"id": prefix, "author_view_rebuilt": True, "normalized_available": False}
    normalized = inside(run_dir, row["normalized_input"])
    for value in (sha(normalized), row["model_input_sha256"], row["model_input_sha256_after"]):
        checks.equal(value, digest(jpeg), prefix + ": independently rebuilt app-upload JPEG")
    artifact_dir = (run_dir / row["case_artifacts"]).resolve()
    checks.check(artifact_dir.is_relative_to(run_dir.resolve()), prefix + ": artifact directory bound")
    artifacts = load(inside(run_dir, row["case_artifacts"] + "/artifacts.json"))
    files = {item["file"]: item for item in artifacts["files"]}
    checks.equal(len(files), len(artifacts["files"]), prefix + ": unique artifact filenames")
    checks.equal(set(files), {p.name for p in artifact_dir.glob("*.png")}, prefix + ": all saved PNGs listed")
    for name, record in files.items():
        path = inside(artifact_dir, name)
        checks.equal(sha(path), record["sha256"], prefix + ": artifact SHA " + name)
        checks.equal(path.stat().st_size, record["bytes"], prefix + ": artifact bytes " + name)
    for name, expected in (("inspection.png", png), ("inspection-rotated.png", rotated)):
        if name in files:
            checks.equal(files[name]["sha256"], digest(expected), prefix + ": reconstructed prepared PNG " + name)
    for index, call in enumerate(artifacts["calls"], start=1):
        checks.equal(call["call_index"], index, prefix + ": generation order")
        checks.check(bool(call["images"]), prefix + ": generation inputs retained")
        for image in call["images"]:
            checks.equal(files[image["file"]]["sha256"], image["sha256"], prefix + ": generation image SHA")
    diagnostics = row.get("observation_diagnostics") or {}
    for index, passed in enumerate(diagnostics.get("passes", [])):
        expected_name = "inspection.png" if index == 0 else "inspection-rotated.png"
        checks.equal(artifacts["calls"][index]["status"], "completed", prefix + ": saved successful generation")
        checks.equal(artifacts["calls"][index]["images"][0]["file"], expected_name, prefix + ": generated frame order")
        checks.equal(passed["input_sha256"], files[expected_name]["sha256"], prefix + ": pass input identity")
        checks.equal(artifacts["calls"][index]["parsed_result"], passed["inventory"], prefix + ": generation output equals saved inventory")
    identity = (row.get("observation") or {}).get("identity_verification") or diagnostics.get("identity", {})
    crops = identity.get("crops", [])
    with Image.open(io.BytesIO(jpeg)) as opened:
        normalized_image = opened.convert("RGB")
    for crop in crops:
        checks.equal(crop["source_sha256"], digest(jpeg), prefix + ": identity crop source")
        pixel = normalized_image.crop(crop["rect_source_px"])
        ratio = 512 / max(pixel.size)
        enlarged = pixel.resize((max(1, round(pixel.width * ratio)), max(1, round(pixel.height * ratio))),
                                Image.Resampling.LANCZOS)
        for key, expected in (("pixel_crop", encoded(pixel)), ("crop", encoded(enlarged))):
            name = Path(crop[key + "_file"]).name
            checks.equal(files[name]["sha256"], digest(expected), prefix + ": reconstructed " + name)
            checks.equal(crop[key + "_sha256"], digest(expected), prefix + ": metadata " + name)
    return {"id": prefix, "author_view_rebuilt": True, "normalized_available": True,
            "png_files_verified": len(files), "generation_calls_verified": len(artifacts["calls"]),
            "identity_crops_rebuilt": len(crops)}


def independent_summary(rows):
    counts = {key: sum(row["outcome"] == key for row in rows) for key in OUTCOMES}
    paired = [row for row in rows if row["first_pass_outcome"] is not None]
    attempted = [row for row in rows if row["execution_status"] == "attempted"]
    return {
        "planned_cases": len(rows), "outcomes": counts,
        "author_bracket_count_agreement_fraction": counts["C_b"] / len(rows),
        "outcome_by_application_clarity": {key: {
            "app_clear": sum(row["outcome"] == key and row["app_clear"] is True for row in rows),
            "app_not_clear": sum(row["outcome"] == key and row["app_clear"] is False for row in rows),
        } for key in OUTCOMES[:-1]},
        "paired_first_final": {"cases": len(paired), "transitions": {
            f"{a}->{b}": sum(row["first_pass_outcome"] == a and row["outcome"] == b for row in paired)
            for a in OUTCOMES[:-1] for b in OUTCOMES}},
        "constant_one_baseline": {"correct": sum(row["author_count"] == 1 for row in rows),
                                  "denominator": len(rows),
                                  "fraction": sum(row["author_count"] == 1 for row in rows) / len(rows)},
        "by_view_kind": {kind: {
            "cases": sum(row["view_kind"] == kind for row in rows),
            "outcomes": {key: sum(row["view_kind"] == kind and row["outcome"] == key for row in rows) for key in OUTCOMES},
        } for kind in ("full_image", "author_box_roi")},
        "median_pipeline_latency_ms": statistics.median(row["elapsed_ms"] for row in attempted) if attempted else None,
        "pipeline_latency_n": len(attempted),
    }


def audit_run(run_dir, dataset_root, manifest_path, freeze_path, project=PROJECT):
    checks = Checks()
    run_dir, dataset_root = Path(run_dir).resolve(), Path(dataset_root).resolve()
    manifest, freeze, run = load(manifest_path), load(freeze_path), load(run_dir / "run.json")
    if run.get("status") == "running":
        raise ValueError("Run is still active; audit only after it has finished")
    cases = manifest["cases"]
    rows = [json.loads(line) for line in (run_dir / "predictions.jsonl").read_text().splitlines()]
    checks.equal(run["status"], "completed", "Run completed")
    checks.equal(run.get("valid_frozen_run"), True, "Runner marks its frozen execution valid")
    checks.equal(sha(manifest_path), freeze["manifest_sha256"], "External manifest matches freeze")
    checks.equal(sha(run_dir / "manifest.json"), sha(manifest_path), "Saved manifest exactly matches external manifest")
    checks.equal(sha(run_dir / "freeze.json"), sha(freeze_path), "Saved freeze exactly matches external freeze")
    ids = [case["id"] for case in cases]
    checks.equal([row["id"] for row in rows], ids, "Prediction rows follow all planned case IDs exactly")
    checks.equal(len(set(ids)), len(ids), "Case IDs unique")
    checks.equal(len({case["source_id"] for case in cases}), len(cases), "Origin source IDs unique")
    for stored in (freeze, run):
        checks.equal(stored["case_ids"], ids, "Frozen/run planned case order")
        checks.equal(stored["expected_cases"], len(cases), "Frozen/run planned denominator")
        checks.equal(stored["label_scope"], "author_L_bracket_count_only", "Partial label scope")
        checks.equal(stored["fixed_observer_requirements"], dict.fromkeys(PARTS, 1), "Observer receives fixed truth-independent requirements")
        checks.equal(stored["observation_mode"], "spatial_guarded", "Selected guarded observer")
        checks.equal(stored["image_max_side"], 1536, "Selected prepared image maximum")
        checks.equal(stored["input_pipeline"], "app-upload", "Real upload pipeline")
        checks.equal(stored["model"], {"profile": "Qwen3.6-27B-4bit", "revision": "c000ac2c2057d94be3fa931000c31723aac53282"},
                     "Selected frozen model")
    for stage in ("model_before", "model_after"):
        model = run.get(stage)
        if model:
            checks.equal(model["repo_id"], "mlx-community/Qwen3.6-27B-4bit", stage + ": model repository")
            checks.equal(model["revision"], freeze["model"]["revision"], stage + ": model revision")
            checks.equal(model["observation_mode"], "spatial_guarded", stage + ": actual observation mode")
            checks.equal(model["image_max_side"], 1536, stage + ": actual maximum image size")
    checks.equal(run["completed_cases"], len(cases), "Full completed denominator")
    checks.equal(run.get("recorded_cases"), len(rows), "Persisted denominator")
    for key, external in (("manifest", manifest_path), ("freeze", freeze_path)):
        for suffix in ("", "_after"):
            checks.equal(run[key + "_sha256" + suffix], sha(external), key + " before/after identity")
    for suffix in ("", "_after"):
        checks.equal(run["source_hashes" + suffix], freeze["method_source_hashes"], "Method sources before/after equal freeze")
        checks.equal(run["runner_sha256" + suffix], freeze["runner_sha256"], "Runner before/after equals freeze")
    expected_files = set(freeze["method_source_hashes"])
    for root in (project, run_dir / "source_snapshot"):
        actual_files = {p.relative_to(root).as_posix() for p in (root / "kitguard").glob("*.py")}
        checks.equal(actual_files, expected_files, "Complete Python method source set: " + str(root))
        for relative, expected in freeze["method_source_hashes"].items():
            checks.equal(sha(inside(root, relative)), expected, "Method source SHA: " + str(root / relative))
        checks.equal(sha(inside(root, "scripts/run_partial_bracket_benchmark.py")), freeze["runner_sha256"],
                     "Runner source SHA: " + str(root))
    schema = load(run_dir / "observation_schema.json")
    checks.check("observed" in schema.get("properties", {}), "Observation schema saved")
    if manifest.get("source_manifest_sha256"):
        checks.equal(sha(dataset_root / "raw/ino-10-190/SOURCE_MANIFEST.json"), manifest["source_manifest_sha256"],
                     "Original author source manifest identity")
    recomputed, input_records = [], []
    for case, row in zip(cases, rows, strict=True):
        for key in ("source_id", "author_group", "view_kind", "ground_truth", "unlabeled_categories"):
            checks.equal(row[key], case[key], case["id"] + ": frozen " + key)
        checks.equal(set(case["ground_truth"]), {"bracket"}, case["id"] + ": bracket-only author truth")
        checks.equal(case["unlabeled_categories"], list(PARTS[:-1]), case["id"] + ": no fabricated other-category truth")
        recomputed.append(recompute_case(case, row, checks))
        input_records.append(audit_inputs(case, row, run_dir, dataset_root, checks))
    summary = independent_summary(recomputed)
    for key, value in summary.items():
        actual = run["summary"][key]
        if key == "constant_one_baseline":
            actual = {k: actual[k] for k in value}
        checks.equal(actual, value, "Independently recomputed summary: " + key)
    return {"schema_version": 1, "audited_at": datetime.now(UTC).isoformat(),
            "audit_script_sha256": sha(__file__), "run_directory": str(run_dir),
            "manifest_sha256": sha(manifest_path), "freeze_sha256": sha(freeze_path),
            "passed": not checks.failures, "checks": checks.count, "failures": checks.failures,
            "independent_summary": summary, "input_reconstruction": input_records,
            "independence": "No runner scoring/preparation/app/model imports. Original author labels and pixels independently reconstructed using Pillow. No GPU."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.report and (args.report.exists() or args.report.resolve().is_relative_to(args.run.resolve())):
        parser.error("Report must be a fresh path outside the audited run")
    report = audit_run(args.run, args.dataset_root, args.manifest, args.freeze)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("x") as output:
            output.write(text)
    print(text)
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
