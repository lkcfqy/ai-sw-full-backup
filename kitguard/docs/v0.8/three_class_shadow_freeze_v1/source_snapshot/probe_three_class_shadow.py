"""Freeze/run a three-class CPU shadow over all 51 already exposed G inputs.

No production imports or VLM calls. preflight/freeze read evidence and pixels but
never import Torch or load a model. run requires a completed, bound training run.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import io
import itertools
import json
import math
import platform
import shutil
import statistics
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PARTS = ("bolt", "nut", "washer", "bracket")
CLASSES = {1: "bolt", 2: "nut", 3: "washer"}
SCHEMA = "kitguard.v08.three-class-shadow"
ISSUE = "Experimental detector/G count conflict: nut and washer require additional evidence."
PLAN = "docs/v0.8/THREE_CLASS_SHADOW_PLAN.md"
ANNOTATIONS = "datasets/raw/mvtec_screws_v1.0/mvtec_screws.json"
ANNOTATIONS_SHA = "81257dff178531b5f02240addb89a132b701b557fb2663817981339176c80fa9"
BASE = "evaluation-runs/v0.7/public_paired_v1"
BASE_HASHES = {
    "run.json": "98d26a66c384466fc85f2e6c3f9c2266d2be89b8a2a3d3ad034da6fae2789661",
    "analysis.json": "13f1775f4f6c57a6f21e01dbb6584654d4beb36a1749ae5430179d7a95f037c4",
    "manifest.json": "efe4633e873d45032101a26e035c23d267bafa6605d147d3d2f7fcb51b697643",
    "freeze.json": "cec1cf5362a5154cfd6e4d27e5ed9dbb49d7757a12189474c13e643f1dc67be7",
    "predictions.jsonl": "9b525702cb2665274c37a7d7740c1d93c05562ab5fb5a17e171e31b75a6859ee",
}
AUDIT = "test-results/v0.7/public-paired-audit-v1.json"
AUDIT_SHA = "94c71e45341a5065ee90fe601e606cd3a54242094d5dcc08770f6aae8c588fe9"
TRAINING_AUDIT = "test-results/v0.8-grouped-detector-independent-audit-v1.json"
POLICY = {
    "planned_photos": 51, "device": "cpu", "cpu_threads": 4, "retries": 0, "warmup": False,
    "input": "G call-01 original generation.images[0], full actual input, no VLM points/ROI",
    "model": "fasterrcnn_mobilenet_v3_large_320_fpn", "head_outputs": 4,
    "min_size": 640, "max_size": 960, "box_score_thresh": .05,
    "box_nms_thresh": .5, "box_detections_per_img": 100,
    "cross_class_policy": "retain all; IoU>=0.5 pairs reported only, no suppression",
    "count_rule": "score >= validation-selected shared threshold; predicted candidates, not truth lower bounds",
    "fusion": "any known G nut/washer count exceeded => both unknown; no count repairs",
    "unknown": "never interpreted as zero", "annotation_scope": "author_annotated_target_only",
    "new_holdout": False, "automatic_promotion": False,
}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def write_new(path, value):
    with Path(path).open("x") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def replace_json(path, value):
    temporary = Path(path).with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def inside(root, relative):
    need(isinstance(relative, str) and relative and not Path(relative).is_absolute()
         and ".." not in Path(relative).parts, "Unsafe evidence path")
    path = (root / relative).resolve()
    need(path.is_relative_to(root.resolve()), "Evidence path escapes root")
    return path


def ref(root, path):
    path = Path(path).resolve()
    return {"path": path.relative_to(root).as_posix(), "sha256": sha(path)}


def verify(root, item):
    path = inside(root, item["path"])
    need(sha(path) == item["sha256"], f"Evidence changed: {item['path']}")
    return path


def canonical(value):
    # JSON represents integer class-map keys as strings; this is the only normalization.
    return json.dumps(value, sort_keys=True, allow_nan=False)


def number(value, low=0, high=math.inf):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def versions():
    return {"python": platform.python_version(), **{p: importlib.metadata.version(p)
            for p in ("torch", "torchvision", "Pillow")}}


def rank(metric):
    return (metric["balanced_exact_count_accuracy"], -metric["balanced_class_count_mae"],
            metric["pooled"]["box_f1"])


def validate_training_config(config):
    for key in ("model", "head_outputs", "min_size", "max_size", "box_score_thresh",
                "box_nms_thresh", "box_detections_per_img", "annotation_scope"):
        need(config[key] == POLICY[key], f"Training config differs: {key}")
    need(config["classes"] in (CLASSES, {str(k): v for k, v in CLASSES.items()}), "Three-class map differs")
    need(config["epochs"] == 12 and config["thresholds"] == [i / 10 for i in range(1, 10)], "Training selection differs")


def training_receipt(root, directory):
    """Metadata only; verify all 12 recorded threshold/epoch selections before any shadow inference."""
    directory = directory.resolve()
    need(directory.is_relative_to(root), "Training run must be within project")
    run, protocol = read(directory / "run.json"), read(directory / "protocol.json")
    need(run["status"] == "completed" and run["epochs_completed"] == 12
         and run["source_changed_during_run"] is False, "Training must finish all12 unchanged")
    need(sha(directory / "protocol.json") == run["protocol_sha256"], "Training protocol SHA mismatch")
    validate_training_config(protocol)
    need(protocol["training_denominators"] == {"screws_images": 214, "foda_images": 400}
         and protocol["validation_denominators"] == {"screws_images": 44, "foda_images": 36, "foda_groups": 3},
         "Training/validation denominator differs")
    bound = [directory / name for name in ("run.json", "protocol.json", "preflight.json", "best.pt",
                                          "history.jsonl", "best_validation_metrics.json", "best_validation_predictions.json")]
    need(sha(directory / "best.pt") == run["best_checkpoint_sha256"], "Best checkpoint SHA mismatch")
    preflight = read(directory / "preflight.json")
    need(preflight["status"] == "passed" and sha(directory / "preflight.json") == protocol["preflight_sha256"],
         "Training preflight mismatch")
    history = rows(directory / "history.jsonl")
    need([r["epoch"] for r in history] == list(range(1, 13)), "Need complete ordered epoch history")
    best = None
    for epoch, history_row in enumerate(history, 1):
        folder = directory / "epochs" / f"epoch-{epoch:02d}"
        sweep_path, selection_path = folder / "threshold_sweep.json", folder / "selected.json"
        predictions_path = folder / "validation_predictions.json"
        bound.extend((sweep_path, selection_path, predictions_path))
        need(sha(sweep_path) == history_row["threshold_sweep_sha256"]
             and sha(predictions_path) == history_row["validation_predictions_sha256"], "Epoch hashes differ")
        sweep, selected = read(sweep_path), read(selection_path)
        need([r["threshold"] for r in sweep] == protocol["thresholds"], "Threshold sweep differs")
        need(selected == max(sweep, key=lambda x: (*rank(x), x["threshold"])), "Threshold selection tie/rank differs")
        need(history_row["threshold"] == selected["threshold"] and history_row["rank"] == list(rank(selected)),
             "Epoch history/selection differs")
        raw = read(predictions_path)
        need(len(raw) == 80 and all(r["status"] == "ok" for r in raw), "Validation incomplete/failed")
        need([r["id"] for r in raw] == [r["id"] for r in preflight["validation"]], "Validation IDs differ")
        improved = best is None or rank(selected) > tuple(best["rank"])
        need(history_row["improved"] is improved, "Epoch choice differs")
        if improved:
            best = {"epoch": epoch, "threshold": selected["threshold"], "rank": list(rank(selected))}
    need(best == run["best"], "Final best choice differs")
    audit_path = root / TRAINING_AUDIT
    training_audit = read(audit_path)
    need(training_audit["status"] == "passed" and training_audit["checkpoint_metadata_inspected"] is True
         and training_audit["validation_observations"] == 960 and training_audit["all_validation_errors"] == 0
         and training_audit["best"] == best, "Independent training audit missing/incomplete")
    for key, name in (("run", "run.json"), ("protocol", "protocol.json"), ("history", "history.jsonl"),
                      ("best_checkpoint", "best.pt")):
        need(training_audit["source_hashes"][key] == sha(directory / name), "Training audit binding differs")
    bound.append(audit_path)
    best_metrics = read(directory / "best_validation_metrics.json")
    selected_path = directory / "epochs" / f"epoch-{best['epoch']:02d}" / "selected.json"
    need(best_metrics == read(selected_path), "Best metrics differ from selected epoch")
    need(read(directory / "best_validation_predictions.json") == read(selected_path.parent / "validation_predictions.json"),
         "Best raw predictions differ")
    for path, expected in protocol["bindings"].items():
        need("held_back" not in Path(path).name and "held_back" not in Path(path).parts, "Forbidden training binding")
        need(sha(path) == expected, f"Training data/source binding changed: {path}")
    for path, expected in protocol["runtime_sha256"].items():
        need(sha(path) == expected, f"Training runtime changed: {path}")
    source_hashes = {r["source_sha256"] for r in preflight["training"] + preflight["validation"]}
    source_names = {r["group_id"] for r in preflight["training"] + preflight["validation"] if r["source"] == "screws"}
    return {"files": [ref(root, p) for p in bound], "checkpoint": ref(root, directory / "best.pt"),
            "protocol": protocol, "selection": best, "selected_metrics": best_metrics,
            "training_source_hashes": sorted(source_hashes),
            "screws_source_names": sorted(source_names), "selection_recomputed_from_saved_metrics": True,
            "raw_validation_metrics_independently_recomputed": True,
            "independent_training_audit": ref(root, audit_path)}


def baseline(root):
    directory = root / BASE
    audit_path = root / AUDIT
    need(sha(audit_path) == AUDIT_SHA, "Baseline audit changed")
    audit = read(audit_path)
    need(audit["status"] == "passed" and audit["completed_attempts"] == 153, "Baseline not fully audited")
    files = [ref(root, audit_path)]
    for name, expected in BASE_HASHES.items():
        path = directory / name
        need(sha(path) == expected == audit["artifacts_sha256"][name], "Baseline files changed")
        files.append(ref(root, path))
    cases, predictions = read(directory / "manifest.json")["cases"], rows(directory / "predictions.jsonl")
    need(len(cases) == len({c["id"] for c in cases}) == 51 and len(predictions) == 153, "Baseline denominator differs")
    guarded = {}
    for attempt, row in enumerate(predictions, 1):
        if row["mode"] == "spatial_guarded":
            need(row["case_id"] not in guarded and not row["error"], "Duplicate/failed G")
            guarded[row["case_id"]] = (attempt, row)
    need(set(guarded) == {c["id"] for c in cases}, "G case set differs")
    return cases, guarded, audit, files


def decoded(path):
    from PIL import Image
    with Image.open(path) as image:
        need(image.getexif().get(274) in (None, 1) and getattr(image, "n_frames", 1) == 1,
             "Unsupported orientation/animation")
        rgb = image.convert("RGB")
        rgb.load()
    return rgb


def pixel_sha(image):
    """Same explicit dimensions/mode namespace as the frozen v0.7 source-family hash."""
    return hashlib.sha256(str(image.size).encode() + b"|RGB|" + image.tobytes()).hexdigest()


def oriented_aabb(ann):
    row, col, width, height, angle = ann["bbox"]
    need(all(number(x, -math.inf) for x in (row, col, width, height, angle)) and width > 0 and height > 0,
         "Invalid author oriented box")
    corners = [(col + x * math.cos(angle) - y * math.sin(angle),
                row + x * math.sin(angle) + y * math.cos(angle))
               for x in (-width / 2, width / 2) for y in (-height / 2, height / 2)]
    return [min(x for x, _ in corners), min(y for _, y in corners),
            max(x for x, _ in corners), max(y for _, y in corners)]


def author_boxes(case, annotations, source_size, actual_size):
    if case["subgroup"] == "loco_normal_222":
        return {"available": False, "reason": "Author normal-count composition only; no instance boxes", "objects": None}
    need(case["subgroup"] == "screws_author_safe_crop", "Unknown source scope")
    image = next(r for r in annotations["images"] if r["file_name"] == Path(case["source_image"]).name)
    need(source_size == [image["width"], image["height"]], "Author source dimensions differ")
    left, top, right, bottom = case["crop_xyxy"]
    need(0 <= left < right <= source_size[0] and 0 <= top < bottom <= source_size[1], "Invalid crop")
    need(case["bbox_margin_px"] == 16, "Crop margin differs")
    objects, included = [], []
    for ann in annotations["annotations"]:
        if ann["image_id"] != image["id"]:
            continue
        box = oriented_aabb(ann)
        need(0 <= box[0] < box[2] <= source_size[0] and 0 <= box[1] < box[3] <= source_size[1],
             "Author box outside source")
        wholly_inside = box[0] - 16 >= left and box[1] - 16 >= top and box[2] + 16 <= right and box[3] + 16 <= bottom
        wholly_outside = box[2] + 16 <= left or box[3] + 16 <= top or box[0] - 16 >= right or box[1] - 16 >= bottom
        need(wholly_inside or wholly_outside, "Crop cuts an author box/margin")
        if wholly_inside:
            included.append(ann["id"])
            need(1 <= ann["category_id"] <= 13, "Unknown author type_ID")
            label = 2 if ann["category_id"] in {7, 9, 10, 11} else 1
            sx, sy = actual_size[0] / (right - left), actual_size[1] / (bottom - top)
            transformed = [(box[0] - left) * sx, (box[1] - top) * sy,
                           (box[2] - left) * sx, (box[3] - top) * sy]
            objects.append({"label": label, "box": transformed, "annotation_id": ann["id"],
                            "original_category_id": ann["category_id"], "original_oriented_box": ann["bbox"],
                            "source_aabb": box})
    need(len(included) == len(set(included)) and sorted(included) == sorted(case["included_annotation_ids"]),
         "Included author boxes differ")
    truth = {p: sum(CLASSES[o["label"]] == p for o in objects) for p in PARTS}
    need(truth == case["ground_truth"], "Author projected count differs")
    return {"available": True, "scope": "author_annotated_target_only; projected type_ID semantics",
            "transform": "oriented author bbox->AABB; safe crop translation; independent x/y resize to actual G input",
            "objects": objects, "image_size": actual_size, "truth_count": truth}


def bind_case(root, case, attempt, row, audit, annotations):
    from PIL import Image
    need(row["case_id"] == case["id"] and row["source_id"] == case["source_id"]
         and row["sha256"] == case["sha256"] and row["ground_truth"] == case["ground_truth"], "G/case differs")
    directory = root / BASE
    source = inside(root / "datasets", case.get("source_image", case["image"]))
    selected = inside(root / "datasets", case["image"])
    need(sha(source) == case["source_sha256"] and sha(selected) == case["sha256"], "Source/view changed")
    base = directory / "cases" / f"{attempt:03d}-spatial_guarded"
    gen_path = base / "call-01/generation.json"
    need(sha(gen_path) == audit["artifacts_sha256"][gen_path.relative_to(directory).as_posix()], "G generation changed")
    gen = read(gen_path)
    original = row["observation_diagnostics"]["passes"][0]
    verification = row["observation"]["verification"]["passes"][0]
    need(original["transform"] == verification["transform"] == "original" and gen["status"] == "parsed"
         and gen["schema"] == "SpatialInventory" and len(gen["images"]) == 1, "Not original G call-01")
    need(json.loads(gen["raw_text"]) == gen["parsed"] == original["inventory"], "G raw/parsed differs")
    actual = inside(base, gen["images"][0]["path"])
    need(sha(actual) == gen["images"][0]["sha256"] == original["input_sha256"] == verification["input_sha256"]
         == audit["artifacts_sha256"][actual.relative_to(directory).as_posix()], "Actual G image binding differs")
    normalized = directory / "normalized_inputs" / f"{attempt:03d}-spatial_guarded.jpg"
    need(sha(normalized) == row["normalized_sha256"] == row["observation_diagnostics"]["source_sha256"]
         == audit["artifacts_sha256"][normalized.relative_to(directory).as_posix()], "Normalized input changed")
    source_rgb, view, normalized_rgb, actual_rgb = [decoded(p) for p in (source, selected, normalized, actual)]
    need(pixel_sha(source_rgb) == case["source_decoded_rgb_sha256"], "Source RGB namespace/hash differs")
    if case["derived_view"]:
        crop = source_rgb.crop(case["crop_xyxy"])
        need(crop.size == view.size and crop.tobytes() == view.tobytes(), "Selected crop differs from source")
    else:
        need(source_rgb.size == view.size and source_rgb.tobytes() == view.tobytes(), "Whole-image view differs")
    upload = view.copy()
    upload.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    upload.save(buffer, format="JPEG", quality=95)
    need(hashlib.sha256(buffer.getvalue()).hexdigest() == row["normalized_sha256"], "Upload geometry/encoding lineage differs")
    prepared = normalized_rgb.copy()
    prepared.thumbnail((1536, 1536), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    prepared.save(buffer, format="PNG")
    need(hashlib.sha256(buffer.getvalue()).hexdigest() == gen["images"][0]["sha256"]
         and prepared.size == actual_rgb.size and prepared.tobytes() == actual_rgb.tobytes(), "Actual G thumbnail lineage differs")
    return {"files": [ref(root, p) for p in (source, selected, normalized, gen_path, actual)],
            "actual_input": ref(root, actual), "actual_input_size": list(actual_rgb.size),
            "actual_input_rgb_sha256": pixel_sha(actual_rgb),
            "rgb_hash_namespace": "str((width,height)).encode()+b'|RGB|'+RGB_bytes",
            "view_size": list(view.size), "normalized_size": list(normalized_rgb.size),
            "source_size": list(source_rgb.size), "source_rgb_sha256": pixel_sha(source_rgb),
            "author_boxes": author_boxes(case, annotations, list(source_rgb.size), list(actual_rgb.size))}


def preflight(root, training_directory):
    root = root.resolve()
    training = training_receipt(root, training_directory)
    cases, guarded, audit, base_files = baseline(root)
    annotation_path = root / ANNOTATIONS
    need(sha(annotation_path) == ANNOTATIONS_SHA, "Original author annotations changed")
    annotations = read(annotation_path)
    bound_cases = []
    for case in cases:
        need(case["source_sha256"] not in training["training_source_hashes"]
             and Path(case.get("source_image", case["image"])).name not in training["screws_source_names"],
             "Regression source appears in training/validation")
        attempt, row = guarded[case["id"]]
        bound_cases.append({"case": case, "baseline_attempt": attempt, "base_observation": row["observation"],
                            "baseline_latency_ms": row["latency_ms"],
                            "binding": bind_case(root, case, attempt, row, audit, annotations)})
    need(Counter(c["case"]["subgroup"] for c in bound_cases) == {"screws_author_safe_crop": 35, "loco_normal_222": 16},
         "Expected source denominators differ")
    return {"schema": SCHEMA + ".preflight.v1", "status": "passed", "created_at": datetime.now(UTC).isoformat(),
            "project_root": str(root), "policy": POLICY, "versions": versions(), "training": training,
            "baseline_files": base_files, "annotations": ref(root, annotation_path), "cases": bound_cases,
            "plan": ref(root, root / PLAN), "runner": ref(root, Path(__file__)),
            "model_loaded_or_called": False, "already_exposed_development_only": True}


def create_freeze(root, training_directory, output):
    need(not output.exists(), "Refusing to overwrite freeze")
    receipt = preflight(root, training_directory)
    output.mkdir(parents=True)
    snapshot = output / "source_snapshot"
    snapshot.mkdir()
    shutil.copy2(__file__, snapshot / "probe_three_class_shadow.py")
    shutil.copy2(root / PLAN, snapshot / "plan.md")
    need(sha(snapshot / "probe_three_class_shadow.py") == receipt["runner"]["sha256"]
         and sha(snapshot / "plan.md") == receipt["plan"]["sha256"], "Source changed during freeze")
    freeze = {**receipt, "schema": SCHEMA + ".freeze.v1", "source_hashes": {
        "probe_three_class_shadow.py": sha(snapshot / "probe_three_class_shadow.py"), "plan.md": sha(snapshot / "plan.md")}}
    write_new(output / "freeze.json", freeze)
    return freeze


def iou(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    return intersection / ((a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - intersection)


def summarize(raw, threshold, size):
    need(number(threshold, .1, .9) and threshold in [i / 10 for i in range(1, 10)], "Invalid selected threshold")
    need(set(raw) == {"labels", "boxes", "scores"} and all(isinstance(raw[k], list) for k in raw), "Invalid raw output")
    need(len(raw["labels"]) == len(raw["boxes"]) == len(raw["scores"]) <= 100, "Raw array length differs")
    counts, predictions = dict.fromkeys(CLASSES.values(), 0), []
    for index, (label, box, score) in enumerate(zip(raw["labels"], raw["boxes"], raw["scores"], strict=True)):
        need(type(label) is int and label in CLASSES and number(score, 0, 1), "Invalid class/score")
        need(isinstance(box, list) and len(box) == 4 and all(number(v) for v in box), "Invalid box")
        need(0 <= box[0] < box[2] <= size[0] and 0 <= box[1] < box[3] <= size[1], "Box outside actual input")
        retained = score >= threshold
        counts[CLASSES[label]] += int(retained)
        predictions.append({"index": index, "label": label, "class_name": CLASSES[label], "box": box,
                            "score": score, "retained": retained})
    pairs = []
    for a, b in itertools.combinations(predictions, 2):
        if a["label"] != b["label"]:
            overlap = iou(a["box"], b["box"])
            if overlap >= .5:
                pairs.append({"indices": [a["index"], b["index"]], "iou": overlap,
                              "both_retained": a["retained"] and b["retained"]})
    return {"threshold": threshold, "counts": counts, "predictions": predictions, "cross_class_overlaps": pairs,
            "unsupported_classes": ["bracket"], "counts_are_true_lower_bounds": False}


def fuse(base, detector):
    """No case ID, truth, BOM, VLM points, crop, or author annotation accepted."""
    effective = copy.deepcopy(base)
    uncertain = set((base.get("object_evidence") or {}).get("uncertain_parts", []))
    triggers = []
    for part in ("nut", "washer"):
        known = base["observed"][part]
        if type(known) is int and known >= 0 and part not in uncertain and detector["counts"][part] > known:
            triggers.append({"part": part, "G_count": known, "detector_candidates": detector["counts"][part],
                             "prediction_indices": [p["index"] for p in detector["predictions"]
                                                    if p["class_name"] == part and p["retained"]]})
    if triggers:
        effective["observed"]["nut"] = effective["observed"]["washer"] = None
        effective["issues"] = [*effective["issues"], ISSUE]
    return effective, triggers


def outcome(observation, truth, error=None):
    if error or observation is None:
        return "E"
    if (observation["action"]["kind"] != "none" or observation["issues"]
            or any(observation["observed"][p] is None for p in PARTS)):
        return "U"
    return "C" if observation["observed"] == truth else "W"


def panel(case, observation, error=None):
    actionable = outcome(observation, case["ground_truth"], error) in ("C", "W")
    result = {}
    for name, parts in (("all_four", PARTS), ("source_supported", case["supported_positive_classes"])):
        orders = [dict.fromkeys(PARTS, 0) | dict(zip(parts, vector, strict=True))
                  for vector in itertools.product(range(4), repeat=len(parts)) if any(vector)]
        orders = [o for o in orders if o != case["ground_truth"]]
        bad = [o for o in orders if actionable and observation["observed"] == o]
        result[name] = {"mismatched_orders": len(orders), "false_ready_orders": bad, "any_false_ready": bool(bad)}
    return result


def detector_metrics(case, detector, box_truth):
    retained = [p for p in detector["predictions"] if p["retained"]]
    expected = {p: case["ground_truth"][p] for p in CLASSES.values()}
    errors = {p: detector["counts"][p] - expected[p] for p in expected}
    result = {"annotation_scope": "author_annotated_target_only", "truth_count": expected,
              "prediction_count": detector["counts"], "signed_count_error": errors,
              "exact_count": not any(errors.values()), "count_mae": sum(abs(x) for x in errors.values()) / 3,
              "box_metrics_available": box_truth["available"]}
    if not box_truth["available"]:
        return result | {"box_metrics": None, "reason": box_truth["reason"]}
    gt, matched, matches, false = box_truth["objects"], set(), [], []
    for prediction in sorted(retained, key=lambda p: (-p["score"], p["index"])):
        choices = sorted(((iou(prediction["box"], g["box"]), i) for i, g in enumerate(gt)
                          if i not in matched and g["label"] == prediction["label"]), key=lambda pair: (-pair[0], pair[1]))
        if choices and choices[0][0] >= .5:
            overlap, gi = choices[0]
            matched.add(gi)
            matches.append({"prediction_index": prediction["index"], "ground_truth_index": gi, "iou": overlap})
        else:
            false.append(prediction["index"])
    missed = [i for i in range(len(gt)) if i not in matched]
    per_class = {}
    for label, name in CLASSES.items():
        tp = sum(gt[m["ground_truth_index"]]["label"] == label for m in matches)
        fp = sum(detector["predictions"][i]["label"] == label for i in false)
        fn = sum(gt[i]["label"] == label for i in missed)
        per_class[name] = {"tp": tp, "fp": fp, "fn": fn, "precision": tp/(tp+fp) if tp+fp else 0,
                           "recall": tp/(tp+fn) if tp+fn else 0, "f1": 2*tp/(2*tp+fp+fn) if tp+fp+fn else 0}
    return result | {"box_metrics": {"per_class": per_class, "matches": matches,
                                      "false_positive_indices": false, "missed_ground_truth_indices": missed}}


def analyze(frozen_cases, records):
    need(len(frozen_cases) == len(records) == 51, "Full51 required")
    need([c["case"]["id"] for c in frozen_cases] == [r["case_id"] for r in records], "Case order/set differs")
    outcomes, transitions, strata = Counter(), Counter(), {}
    changes, panels = [], []
    correct_lost = loco_preserved = loco_old_c = old_w_caught = 0
    for frozen, record in zip(frozen_cases, records, strict=True):
        case, base = frozen["case"], frozen["base_observation"]
        old = outcome(base, case["ground_truth"])
        new = "N" if not record["detector_call_started"] else outcome(record["effective_observation"], case["ground_truth"], record["error"])
        need(not (old in ("W", "U") and new == "C"), "Veto cannot repair counts")
        outcomes[new] += 1
        transitions[f"{old}->{new}"] += 1
        strata.setdefault(case["subgroup"], Counter())[new] += 1
        correct_lost += old == "C" and new != "C"
        old_w_caught += old == "W" and new == "U"
        if case["subgroup"] == "loco_normal_222":
            loco_old_c += old == "C"
            loco_preserved += old == new == "C"
        changes.append({"case_id": case["id"], "old": old, "new": new, "veto_applied": bool(record["triggers"])})
        panels.append({"case_id": case["id"], "base": panel(case, base),
                       "shadow": panel(case, record["effective_observation"], record["error"] or ("not attempted" if new == "N" else None))})
    false_ready = {name: sum(p["shadow"][name]["any_false_ready"] for p in panels)
                   for name in ("all_four", "source_supported")}
    timing = {}
    for key in ("decode_tensor_seconds", "detector_seconds", "fusion_seconds", "case_wall_seconds"):
        values = sorted(r["timing"][key] for r in records if r["timing"][key] is not None)
        timing[key] = {"measured": len(values), "p50": statistics.median(values) if values else None,
                       "p90": values[math.ceil(.9*len(values))-1] if values else None, "sum": sum(values)}
    checks = {"all51_called_once": sum(r["detector_call_started"] for r in records) == 51,
              "all51_calls_completed": sum(r["detector_call_completed"] for r in records) == 51,
              "zero_error_or_unattempted": outcomes["E"] == outcomes["N"] == 0,
              "three_original_wrong_rejected": old_w_caught == 3,
              "all14_loco_correct_preserved": loco_preserved == loco_old_c == 14,
              "C_at_least_41": outcomes["C"] >= 41, "zero_W": outcomes["W"] == 0,
              "zero_all_four_AFR": false_ready["all_four"] == 0}
    return {"schema": SCHEMA + ".analysis.v1", "planned": 51, "outcomes": {k: outcomes[k] for k in "CWUEN"},
            "paired_transitions": dict(transitions), "strata": {s: {k: ct[k] for k in "CWUEN"} for s, ct in strata.items()},
            "old_C_lost": correct_lost, "original_W_rejected": old_w_caught,
            "loco_old_C": loco_old_c, "loco_C_preserved": loco_preserved, "changes": changes, "panels": panels,
            "any_false_ready_images": false_ready, "risk_denominator": 51, "unmeasured_risk": outcomes["E"] + outcomes["N"],
            "timing": timing, "full_end_to_end_measured": False, "development_checks": checks,
            "development_gate_passed": all(checks.values()), "independent_audit_required": True,
            "new_holdout": False, "automatic_promotion": False}


def validate_checkpoint(state, frozen):
    expected = frozen["training"]
    need(state["schema"] == "kitguard.v08.grouped-detector-checkpoint.v1", "Wrong checkpoint schema")
    need(canonical(state["config"]) == canonical(expected["protocol"]), "Checkpoint config/protocol differ")
    validate_training_config(state["config"])
    protocol_ref = next(r for r in expected["files"] if r["path"].endswith("/protocol.json"))
    need(state["protocol_sha256"] == protocol_ref["sha256"], "Checkpoint protocol SHA differs")
    choice = expected["selection"]
    need(state["epoch"] == choice["epoch"] and state["selected"]["threshold"] == choice["threshold"]
         and rank(state["selected"]) == tuple(choice["rank"])
         and canonical(state["best"]) == canonical(choice), "Checkpoint selection differs")
    need(canonical(state["selected"]) == canonical(expected["selected_metrics"]), "Checkpoint full selected metrics differ")
    return choice["threshold"]


def build_model(config):
    import torch
    from torchvision.models.detection import fasterrcnn_mobilenet_v3_large_320_fpn
    from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
    from torchvision.ops.misc import FrozenBatchNorm2d
    validate_training_config(config)
    model = fasterrcnn_mobilenet_v3_large_320_fpn(weights=None, weights_backbone=None, num_classes=91,
        progress=False, min_size=640, max_size=960, box_score_thresh=.05, box_nms_thresh=.5, box_detections_per_img=100)

    def replace_bn(module):
        for name, child in list(module.named_children()):
            if isinstance(child, torch.nn.BatchNorm2d):
                setattr(module, name, FrozenBatchNorm2d(child.num_features, eps=child.eps))
            else:
                replace_bn(child)
    replace_bn(model)
    model.roi_heads.box_predictor = FastRCNNPredictor(model.roi_heads.box_predictor.cls_score.in_features, 4)
    return model


def all_refs(frozen):
    yield from frozen["baseline_files"]
    yield frozen["annotations"]
    yield from frozen["training"]["files"]
    for case in frozen["cases"]:
        yield from case["binding"]["files"]


def verify_freeze(freeze_path):
    frozen = read(freeze_path)
    need(frozen["schema"] == SCHEMA + ".freeze.v1" and frozen["policy"] == POLICY, "Freeze policy differs")
    root = Path(frozen["project_root"])
    snapshot = freeze_path.parent / "source_snapshot"
    for name, expected in frozen["source_hashes"].items():
        need(sha(snapshot / name) == expected, "Frozen source changed")
    need(sha(__file__) == frozen["source_hashes"]["probe_three_class_shadow.py"], "Execute the exact frozen runner")
    need(versions() == frozen["versions"], "Runtime versions changed")
    for item in all_refs(frozen):
        verify(root, item)
    for path, expected in frozen["training"]["protocol"]["runtime_sha256"].items():
        need(sha(path) == expected, "Runtime implementation changed")
    need(len(frozen["cases"]) == len({c["case"]["id"] for c in frozen["cases"]}) == 51, "Freeze case denominator differs")
    return frozen, root


def empty_record(item, index):
    return {"schema": SCHEMA + ".case.v1", "index": index, "case_id": item["case"]["id"],
            "baseline_attempt": item["baseline_attempt"], "binding": item["binding"],
            "base_observation": item["base_observation"], "effective_observation": None,
            "overlay_scope": "experiment only; original G evidence unchanged, not production Observation",
            "raw_detector_output": None, "raw_invalid_output_repr": None, "detector": None,
            "detector_metrics": None, "triggers": [], "detector_call_started": False, "detector_call_completed": False,
            "status": "not_attempted", "error": None,
            "timing": {"decode_tensor_seconds": None, "detector_seconds": None, "fusion_seconds": None,
                       "case_wall_seconds": None, "historical_G_latency_ms": item["baseline_latency_ms"]}}


def run(freeze_path, output):
    need(not output.exists(), "Run output exists; no overwrite/retry/resume")
    frozen, root = verify_freeze(freeze_path)
    freeze_hash = sha(freeze_path)
    output.mkdir(parents=True)
    write_new(output / "freeze.json", frozen)
    records = [empty_record(item, index) for index, item in enumerate(frozen["cases"], 1)]
    state = {"schema": SCHEMA + ".run.v1", "status": "running", "started_at": datetime.now(UTC).isoformat(),
             "freeze_sha256": freeze_hash, "planned": 51, "new_holdout": False, "automatic_promotion": False}
    write_new(output / "run.json", state)
    load_seconds, setup_error = None, None
    try:
        import torch
        from torchvision.transforms.functional import pil_to_tensor
        torch.set_num_threads(4)
        checkpoint = verify(root, frozen["training"]["checkpoint"])
        started = time.perf_counter()
        checkpoint_state = torch.load(checkpoint, map_location="cpu", weights_only=True)
        verify(root, frozen["training"]["checkpoint"])
        threshold = validate_checkpoint(checkpoint_state, frozen)
        model = build_model(checkpoint_state["config"])
        model.load_state_dict(checkpoint_state["model"], strict=True)
        model.to("cpu").eval()
        load_seconds = time.perf_counter() - started
    except Exception as exc:  # noqa: BLE001 -- setup failure must retain the whole planned denominator
        setup_error = f"{type(exc).__name__}: {exc}"
    for item, record in zip(frozen["cases"], records, strict=True):
        started = time.perf_counter()
        try:
            if setup_error:
                raise RuntimeError("setup failed: " + setup_error)
            tick = time.perf_counter()
            path = verify(root, item["binding"]["actual_input"])
            image = decoded(path)
            need(list(image.size) == item["binding"]["actual_input_size"]
                 and pixel_sha(image) == item["binding"]["actual_input_rgb_sha256"], "Actual input pixels changed")
            tensor = pil_to_tensor(image).to(torch.float32) / 255.0
            record["timing"]["decode_tensor_seconds"] = time.perf_counter() - tick
            tick = time.perf_counter()
            record["detector_call_started"] = True
            try:
                with torch.inference_mode():
                    returned = model([tensor])[0]
                record["detector_call_completed"] = True
                raw = {key: value.cpu().tolist() for key, value in returned.items()}
                try:
                    json.dumps(raw, allow_nan=False)
                    record["raw_detector_output"] = raw
                except (TypeError, ValueError):
                    record["raw_invalid_output_repr"] = repr(raw)
                    raise ValueError("Non-JSON/nonfinite raw output") from None
            finally:
                record["timing"]["detector_seconds"] = time.perf_counter() - tick
            detector = summarize(raw, threshold, image.size)
            record["detector"] = detector
            tick = time.perf_counter()
            effective, triggers = fuse(item["base_observation"], detector)
            record["timing"]["fusion_seconds"] = time.perf_counter() - tick
            record.update(effective_observation=effective, triggers=triggers,
                          detector_metrics=detector_metrics(item["case"], detector, item["binding"]["author_boxes"]))
            verify(root, item["binding"]["actual_input"])
            record["status"] = "ok"
        except Exception as exc:  # noqa: BLE001 -- no retry or successful baseline fallback
            record["status"] = "failed" if record["detector_call_started"] else "not_attempted"
            record["error"] = f"{type(exc).__name__}: {exc}"
        record["timing"]["case_wall_seconds"] = time.perf_counter() - started
        with (output / "predictions.jsonl").open("a") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
        print(json.dumps({"completed_records": record["index"], "planned": 51, "status": record["status"]}), flush=True)
    result = analyze(frozen["cases"], records)
    write_new(output / "analysis.json", result)
    changed = None
    try:
        need(sha(freeze_path) == freeze_hash, "Freeze changed during run")
        verify_freeze(freeze_path)
    except (ValueError, OSError) as exc:
        changed = str(exc)
    state.update(status="failed_integrity" if changed else "failed_setup" if setup_error else "completed",
                 finished_at=datetime.now(UTC).isoformat(), source_changed=bool(changed), integrity_error=changed,
                 setup_error=setup_error, model_load_seconds=load_seconds, recorded_cases=len(records),
                 detector_calls_started=sum(r["detector_call_started"] for r in records),
                 detector_calls_completed=sum(r["detector_call_completed"] for r in records),
                 predictions_sha256=sha(output / "predictions.jsonl"), analysis_sha256=sha(output / "analysis.json"),
                 full_end_to_end_measured=False)
    replace_json(output / "run.json", state)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("preflight", "freeze"):
        item = sub.add_parser(command)
        item.add_argument("--project-root", type=Path, default=ROOT)
        item.add_argument("--training-run", type=Path, required=True)
        item.add_argument("--output", type=Path, required=True)
    item = sub.add_parser("run")
    item.add_argument("--freeze", type=Path, required=True)
    item.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "preflight":
        write_new(args.output, preflight(args.project_root.resolve(), args.training_run.resolve()))
    elif args.command == "freeze":
        create_freeze(args.project_root.resolve(), args.training_run.resolve(), args.output.resolve())
    else:
        result = run(args.freeze.resolve(), args.output.resolve())
        if result["status"] != "completed":
            parser.exit(1, "Shadow run preserved a setup/integrity failure; see run.json\n")


if __name__ == "__main__":
    main()
