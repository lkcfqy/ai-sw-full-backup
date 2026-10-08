"""Freeze/run one CPU-only detector-veto diagnostic over all exposed v0.7 photos.

No MLX, training, model download, threshold search, count correction or production
imports. Freeze is metadata/image validation only; run requires that exact freeze.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import importlib.util
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

from PIL import Image, ImageOps

PARTS = ("bolt", "nut", "washer", "bracket")
MODES = {"spatial_inventory", "spatial_guarded", "selective_identity_experimental_v1"}
BASELINE_FREEZE = "cec1cf5362a5154cfd6e4d27e5ed9dbb49d7757a12189474c13e643f1dc67be7"
CHECKPOINT_SHA = "2022c203a3b3b36dd146534c8bcfc538739cf8bf643066fc14a5b9611ebeb62c"
WORKER = "docs/v0.7/public_paired_freeze_v1/source_snapshot/kitguard/detector_worker.py"
VETO_ISSUE = "Experimental detector/VLM category conflict: nut and washer require additional evidence."
SCHEMA = "kitguard.v08.detector-veto"


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def inside(root, relative):
    relative = Path(relative)
    need(not relative.is_absolute() and ".." not in relative.parts, "Unsafe relative path")
    path = (root / relative).resolve()
    need(path.is_relative_to(root.resolve()), "Path escapes root")
    return path


def reference(root, path):
    path = Path(path).resolve()
    return {"path": path.relative_to(root.resolve()).as_posix(), "sha256": sha(path)}


def verify_ref(root, ref):
    path = inside(root, ref["path"])
    need(sha(path) == ref["sha256"], f"Hash mismatch: {ref['path']}")
    return path


def versions():
    return {"python": platform.python_version(),
            **{name: importlib.metadata.version(name) for name in ("Pillow", "torch", "torchvision")}}


def finite(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def decoded_normalized(path):
    with Image.open(path) as encoded:
        need(encoded.getexif().get(274) in (None, 1), "Normalized input has unresolved EXIF orientation")
        need(getattr(encoded, "n_frames", 1) == 1, "Animated input")
        image = ImageOps.exif_transpose(encoded).convert("RGB")
        image.load()
    return image


def bind_thumbnail(normalized, vlm_input, normalized_sha, vlm_sha, max_side=1536):
    """Reproduce the frozen resize-only lineage; never infer an unknown transform."""
    need(sha(normalized) == normalized_sha and sha(vlm_input) == vlm_sha, "Input hash mismatch")
    rgb = decoded_normalized(normalized)
    resized = rgb.copy()
    resized.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    resized.save(buffer, format="PNG")
    need(hashlib.sha256(buffer.getvalue()).hexdigest() == vlm_sha, "VLM thumbnail byte lineage mismatch")
    with Image.open(vlm_input) as saved:
        need(saved.size == resized.size and saved.convert("RGB").tobytes() == resized.tobytes(),
             "VLM thumbnail pixel/size lineage mismatch")
    need(sha(normalized) == normalized_sha and sha(vlm_input) == vlm_sha, "Input changed during decode")
    return {"detector_image_size": list(rgb.size), "vlm_image_size": list(resized.size),
            "normalized_rgb_sha256": hashlib.sha256(rgb.tobytes()).hexdigest(),
            "vlm_rgb_sha256": hashlib.sha256(resized.tobytes()).hexdigest(),
            "transform": "EXIF-oriented RGB, LANCZOS thumbnail max_side=1536; no crop/rotation"}


def washer_points(objects, image_size):
    width, height = image_size
    need(all(type(v) is int and v >= 2 for v in image_size), "Invalid coordinate dimensions")
    result = []
    for index, obj in enumerate(objects, 1):
        need(obj.get("part") in PARTS, "Unknown VLM part")
        center = obj.get("center")
        need(isinstance(center, list) and len(center) == 2 and all(finite(v, 0, 1) for v in center),
             "Invalid original VLM coordinates")
        if obj["part"] == "washer":
            result.append({"object_index": index, "center": center,
                           "point_xy": [center[0] * (width - 1), center[1] * (height - 1)]})
    return result


def fuse(base, objects, detector, binding, original):
    """Pure conservative fusion: every uncertain/unsupported result stays uncertain."""
    need(detector["input_sha256"] == binding["normalized_input"]["sha256"], "Detector input SHA mismatch")
    size = binding["lineage"]["detector_image_size"]
    need(detector["image_size"] == size, "Detector coordinate dimensions mismatch")
    need(detector["checkpoint_sha256"] == CHECKPOINT_SHA and detector["threshold"] == 0.5,
         "Detector checkpoint/threshold mismatch")
    points = washer_points(objects, size)
    expected_count = sum(o["part"] == "washer" for o in objects)
    observed_count = original["observed"]["washer"]
    eligible = ("washer" not in original["uncertain_parts"] and type(observed_count) is int
                and observed_count >= 0 and observed_count == expected_count)
    excluded = [] if eligible else [point | {"reason": "original_washer_category_unclear"} for point in points]
    points = points if eligible else []
    matches = []
    for index, prediction in enumerate(detector["predictions"]):
        label, score, box = prediction["label"], prediction["score"], prediction["bbox_xyxy"]
        need(type(label) is int and label in (1, 2), "Invalid detector class")
        need(prediction["class_name"] == {1: "bolt", 2: "nut"}[label], "Detector class mapping mismatch")
        need(finite(score, 0, 1), "Invalid detector score")
        need(isinstance(box, list) and len(box) == 4 and all(finite(v, 0, max(size)) for v in box),
             "Invalid detector box")
        need(0 <= box[0] < box[2] <= size[0] and 0 <= box[1] < box[3] <= size[1], "Box outside image")
        need(prediction["retained_at_frozen_threshold"] is (score >= 0.5), "Threshold receipt mismatch")
        if label == 2 and score >= 0.5:
            for point in points:
                x, y = point["point_xy"]
                if box[0] <= x <= box[2] and box[1] <= y <= box[3]:
                    matches.append({"object_index": point["object_index"], "prediction_index": index,
                                    "point_xy": point["point_xy"], "bbox_xyxy": box, "score": score})
    fused = copy.deepcopy(base)
    fused.pop("latency_ms", None)  # Historical VLM time is recorded separately, never a new end-to-end time.
    if matches:
        fused["observed"]["nut"] = None
        fused["observed"]["washer"] = None
        fused["issues"].append(VETO_ISSUE)
        if fused["action"]["kind"] == "none":
            fused["action"] = {"kind": "recapture", "message": VETO_ISSUE, "region": None}
    return fused, points, excluded, matches


def validate_config(config):
    need(config["schema"] == SCHEMA + ".config.v1", "Unknown config")
    need(config["architecture"] == "fasterrcnn_mobilenet_v3_large_320_fpn", "Architecture must be Faster R-CNN")
    need(config["checkpoint_sha256"] == CHECKPOINT_SHA and config["checkpoint_epoch"] == 10, "Not frozen v1 weights")
    need(type(config["threshold"]) is float and config["threshold"] == 0.5, "Threshold is fixed at 0.5")
    need(config["device"] == "cpu" and config["cpu_threads"] == 4, "Only fixed CPU execution is permitted")
    need(config["planned_photos"] == 51 and config["baseline_mode"] == "spatial_guarded", "Must use all51 guarded")
    need(config["vlm_image_max_side"] == 1536 and config["retries"] == 0 and config["warmup"] is False,
         "Unknown inference protocol")
    need(config["automatic_promotion"] is False, "No automatic promotion")
    need(config["baseline_artifacts"]["freeze.json"]["sha256"] == BASELINE_FREEZE, "Wrong v0.7 baseline")


def baseline_data(root, config):
    paths = {name: verify_ref(root, ref) for name, ref in config["baseline_artifacts"].items()}
    run, audit = read(paths["run.json"]), read(paths["independent_audit"])
    need(run["status"] == "completed" and run["completed_attempts"] == 153 and run["source_changed"] is False,
         "Baseline must be complete and unchanged")
    need(audit["status"] == "passed" and audit["completed_attempts"] == 153, "Baseline independent audit required")
    need(set(read(paths["freeze.json"])["modes"]) == MODES, "Wrong baseline methods")
    for name in ("run.json", "analysis.json", "manifest.json", "freeze.json", "predictions.jsonl"):
        need(audit["artifacts_sha256"][name] == sha(paths[name]), "Audit does not bind this baseline")
    cases = read(paths["manifest.json"])["cases"]
    need(len(cases) == 51 and len({c["id"] for c in cases}) == 51, "Exactly51 unique cases required")
    rows = [json.loads(line) for line in paths["predictions.jsonl"].read_text().splitlines()]
    need(len(rows) == 153, "Missing baseline attempts")
    guarded = {}
    for index, row in enumerate(rows, 1):
        if row["mode"] == "spatial_guarded":
            need(row["case_id"] not in guarded and not row["error"], "Duplicate/failed guarded result")
            guarded[row["case_id"]] = (index, row)
    need(set(guarded) == {c["id"] for c in cases}, "Guarded case set mismatch")
    return paths["run.json"].parent, audit, cases, guarded


def bind_case(root, run_dir, case, attempt, row, audit):
    need(row["case_id"] == case["id"] and row["source_id"] == case["source_id"]
         and row["sha256"] == case["sha256"] and row["ground_truth"] == case["ground_truth"], "Case/source mismatch")
    source = inside(root / "datasets", case.get("source_image", case["image"]))
    selected = inside(root / "datasets", case["image"])
    need(sha(source) == case["source_sha256"] and sha(selected) == case["sha256"], "Source/crop changed")
    relative = f"normalized_inputs/{attempt:03d}-spatial_guarded.jpg"
    normalized = inside(run_dir, relative)
    base = inside(run_dir, f"cases/{attempt:03d}-spatial_guarded")
    generation = base / "call-01/generation.json"
    need(sha(generation) == audit["artifacts_sha256"][generation.relative_to(run_dir).as_posix()], "Raw call changed")
    gen = read(generation)
    diag = row["observation_diagnostics"]
    original = diag["passes"][0]
    observation = row["observation"]
    evidence = observation["object_evidence"]
    need(original["transform"] == "original" and evidence["coordinate_frame"] == "normalized_original",
         "Wrong VLM coordinate frame")
    need(gen["status"] == "parsed" and json.loads(gen["raw_text"]) == gen["parsed"] == original["inventory"],
         "Original VLM raw/parsed evidence mismatch")
    objects = original["inventory"]["objects"]
    original_verification = observation["verification"]["passes"][0]
    need(original_verification["transform"] == "original", "Wrong verification orientation")
    need(objects == evidence["objects"] == original_verification["objects"], "Wrong VLM objects")
    need(original["inventory"]["uncertain_parts"] == original_verification["uncertain_parts"],
         "Original category certainty evidence mismatch")
    need(len(gen["images"]) == 1, "Unexpected original input count")
    vlm_input = inside(base, gen["images"][0]["path"])
    need(gen["images"][0]["sha256"] == original["input_sha256"]
         == observation["verification"]["passes"][0]["input_sha256"]
         == audit["artifacts_sha256"][vlm_input.relative_to(run_dir).as_posix()], "VLM image binding mismatch")
    need(row["normalized_sha256"] == diag["source_sha256"] == audit["artifacts_sha256"][relative],
         "Normalized image binding mismatch")
    lineage = bind_thumbnail(normalized, vlm_input, row["normalized_sha256"], original["input_sha256"])
    washer_points(objects, lineage["detector_image_size"])  # Reject invalid coordinates before any inference.
    return {"source_image": reference(root, source), "selected_image": reference(root, selected),
            "normalized_input": reference(root, normalized), "original_vlm_input": reference(root, vlm_input),
            "original_generation": reference(root, generation), "lineage": lineage}


def validate_exposure(root, exposure, cases):
    need(exposure["schema"] == "kitguard.v08.heterogeneous-veto.exposure.v1"
         and exposure["status"] == "checked", "Exposure audit is not checked")
    need(exposure["planned_cases"] == 51 and len(exposure["cases"]) == 51
         and {c["case_id"] for c in exposure["cases"]} == {c["id"] for c in cases},
         "Exposure case set differs")
    need(exposure["checkpoint_sha256"] == CHECKPOINT_SHA and exposure["threshold"] == 0.5
         and exposure["best_epoch"] == 10, "Exposure checkpoint differs")
    need(exposure["overlap_counts"] == {"train": 0, "val": 0, "test": 0}, "Recorded v1 exposure exists")
    need(exposure["independent_holdout"] is False and exposure["model_loaded_or_called"] is False,
         "Exposure scope is incorrect")
    for case in cases:
        row = next(r for r in exposure["cases"] if r["case_id"] == case["id"])
        need(row["source_id"] == case["source_id"] and row["source_sha256"] == case["source_sha256"]
             and row["already_exposed_in_v07"] is True
             and row["v1_stage_matches"] == {"train": [], "val": [], "test": []}, "Exposure source mismatch")
    need(bool(exposure["files_sha256"]), "Exposure lacks file hashes")
    for path, expected in exposure["files_sha256"].items():
        verify_ref(root, {"path": path, "sha256": expected})


def create_freeze(root, config_path, plan_path, exposure_path, output):
    need(not output.exists(), "Freeze output already exists")
    config = read(config_path)
    validate_config(config)
    checkpoint = inside(root, config["checkpoint"])
    need(sha(checkpoint) == CHECKPOINT_SHA, "Checkpoint hash mismatch")
    exposure = read(exposure_path)
    need(exposure["schema"] == "kitguard.v08.heterogeneous-veto.exposure.v1", "Exposure audit schema mismatch")
    need(plan_path.is_file(), "Predeclared plan missing")
    run_dir, audit, cases, guarded = baseline_data(root, config)
    validate_exposure(root, exposure, cases)
    bindings = []
    for case in cases:
        attempt, row = guarded[case["id"]]
        bindings.append({"case_id": case["id"], "baseline_attempt": attempt,
                         "binding": bind_case(root, run_dir, case, attempt, row, audit)})
    summary_path = checkpoint.parent / "training_summary.json"
    summary = read(summary_path)
    need(summary["best_checkpoint_sha256"] == CHECKPOINT_SHA and summary["threshold"] == 0.5
         and summary["best_epoch"] == 10, "Checkpoint summary mismatch")
    output.mkdir(parents=True, exist_ok=False)
    worker_path = inside(root, WORKER)
    baseline_freeze = read(verify_ref(root, config["baseline_artifacts"]["freeze.json"]))
    need(sha(worker_path) == baseline_freeze["source_hashes"]["kitguard/detector_worker.py"],
         "Frozen v0.7 detector worker changed")
    snapshot = output / "source_snapshot"
    snapshot.mkdir()
    sources = {"probe_detector_veto.py": Path(__file__).resolve(), "detector_worker.py": inside(root, WORKER),
               "config.json": config_path, "plan.md": plan_path, "exposure.json": exposure_path}
    for name, source in sources.items():
        shutil.copyfile(source, snapshot / name)
        need(sha(source) == sha(snapshot / name), "Source changed during freeze")
    freeze = {"schema": SCHEMA + ".freeze.v1", "created_at": datetime.now(UTC).isoformat(),
              "project_root": str(root), "config": config, "planned_photos": 51,
              "source_hashes": {name: sha(snapshot / name) for name in sources}, "versions": versions(),
              "checkpoint": reference(root, checkpoint), "training_summary": reference(root, summary_path),
              "cases": bindings, "new_holdout": False, "automatic_promotion": False,
              "note": "51 photos exposed during v0.7 development; post-hoc diagnostic only. No inference at freeze."}
    write_new(output / "freeze.json", freeze)
    return freeze


def outcome(observation, truth, error=None):
    if error or observation is None:
        return "E"
    if (observation["action"]["kind"] != "none" or observation["issues"]
            or any(observation["observed"][p] is None for p in PARTS)):
        return "U"
    return "C" if observation["observed"] == truth else "W"


def panels(case, observation, error=None):
    result = {}
    for name, parts in (("all_four", PARTS), ("source_supported", case["supported_positive_classes"])):
        orders = [dict.fromkeys(PARTS, 0) | dict(zip(parts, vector, strict=True))
                  for vector in itertools.product(range(4), repeat=len(parts)) if any(vector)]
        orders = [r for r in orders if r != case["ground_truth"]]
        actionable = observation is not None and outcome(observation, case["ground_truth"], error) in ("C", "W")
        false = [r for r in orders if actionable and observation["observed"] == r]
        result[name] = {"mismatched_orders": len(orders), "false_ready_orders": false,
                        "any_false_ready": bool(false), "risk_measured": observation is not None and not bool(error)}
    return result


def analyze(cases, records):
    need(len(records) == len(cases) == 51, "Full51 denominator required")
    need([r["case_id"] for r in records] == [c["id"] for c in cases], "Result order/case set mismatch")
    outcomes, transitions = Counter(), Counter()
    groups = {}
    changes, panels_by_case = [], []
    controls = {"planned": 0, "errors": 0, "veto_applied": 0, "previously_C_to_U": 0,
                "previously_C_denominator": 0, "unchanged_C": 0}
    for case, row in zip(cases, records, strict=True):
        base = outcome(row["base_observation"], case["ground_truth"])
        fused = outcome(row["fused_observation"], case["ground_truth"], row["error"])
        outcomes[fused] += 1
        transitions[f"{base}->{fused}"] += 1
        need(not (base in ("W", "U") and fused == "C"), "Conservative veto cannot repair counts")
        groups.setdefault(case["subgroup"], Counter())[fused] += 1
        changes.append({"case_id": case["id"], "base": base, "fused": fused,
                        "veto_applied": row["veto_applied"]})
        panels_by_case.append({"case_id": case["id"], "base": panels(case, row["base_observation"]),
                               "fused": panels(case, row["fused_observation"], row["error"])})
        if case["subgroup"] == "loco_normal_222" and case["ground_truth"]["washer"] > 0:
            controls["planned"] += 1
            controls["previously_C_denominator"] += int(base == "C")
            controls["errors"] += int(fused == "E")
            controls["veto_applied"] += int(row["veto_applied"])
            controls["previously_C_to_U"] += int(base == "C" and fused == "U")
            controls["unchanged_C"] += int(base == fused == "C")
    measured = [r["timing"]["added_seconds"] for r in records if r["timing"]["added_seconds"] is not None]
    def timing_summary(key):
        values = sorted(r["timing"][key] for r in records if r["timing"][key] is not None)
        return {"measured": len(values), "median_seconds": statistics.median(values) if values else None,
                "p90_seconds": values[max(0, (9 * len(values) + 9) // 10 - 1)] if values else None,
                "total_seconds": sum(values)}
    checks = {"full51": len(records) == 51, "zero_wrong_actionable": outcomes["W"] == 0,
              "zero_execution_or_missing": outcomes["E"] == outcomes["N"] == 0,
              "zero_all_four_false_ready": not any(p["fused"]["all_four"]["any_false_ready"] for p in panels_by_case),
              "no_previous_correct_lost": all(c["fused"] == "C" for c in changes if c["base"] == "C"),
              "loco_previous_correct_preserved": controls["unchanged_C"] == controls["previously_C_denominator"]}
    return {"schema": SCHEMA + ".analysis.v1", "planned_photos": 51,
            "outcomes": {k: outcomes[k] for k in "CWUEN"}, "paired_transitions": dict(sorted(transitions.items())),
            "source_groups": {name: {"planned": sum(ct.values()), "outcomes": {k: ct[k] for k in "CWUEN"}}
                              for name, ct in groups.items()},
            "case_transitions": changes, "panels": panels_by_case,
            "false_ready_summary": {name: {arm: sum(p[arm][name]["any_false_ready"] for p in panels_by_case)
                                           for arm in ("base", "fused")} for name in ("all_four", "source_supported")},
            "unmeasured_risk_images": outcomes["E"], "loco_true_washer_negative_controls": controls,
            "added_latency": {"measured": len(measured), "median_seconds": statistics.median(measured)
                              if measured else None, "total_seconds": sum(measured),
                              "scope": "CPU detector inference plus fusion only; excludes load/decode/tensor/logging, not end-to-end"},
            "timing": {key: timing_summary(key) for key in
                       ("cpu_detector_seconds", "fusion_seconds", "added_seconds", "case_wall_seconds")},
            "further_validation": {"checks": checks, "descriptive_conditions_met": all(checks.values()),
                                   "independent_audit_required": True, "eligibility": "pending_independent_audit"},
            "automatic_promotion": False, "new_holdout": False}


def load_worker(path):
    spec = importlib.util.spec_from_file_location("v08_frozen_detector_worker", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def recorded_detector_call(model, tensor, inference_mode, record):
    """Distinguish an attempted call, a model return, and downstream validation."""
    started = time.perf_counter()
    record["detector_call_started"] = True
    try:
        with inference_mode():
            returned = model([tensor])[0]
            record["detector_call_completed"] = True
            return {key: value.cpu() for key, value in returned.items()}
    finally:
        record["timing"]["cpu_detector_seconds"] = time.perf_counter() - started


def run(freeze_path, output):
    need(not output.exists(), "Run output already exists; no overwrite/resume/retry")
    freeze_hash, freeze = sha(freeze_path), read(freeze_path)
    need(freeze["schema"] == SCHEMA + ".freeze.v1" and freeze["planned_photos"] == 51, "Invalid freeze")
    root = Path(freeze["project_root"]).resolve()
    snapshot = freeze_path.parent / "source_snapshot"
    for name, expected in freeze["source_hashes"].items():
        need(sha(snapshot / name) == expected, f"Frozen source changed: {name}")
    need(sha(Path(__file__)) == freeze["source_hashes"]["probe_detector_veto.py"], "Execute exact frozen runner")
    need(versions() == freeze["versions"], "Dependency versions changed after freeze")
    config = freeze["config"]
    need(config == read(snapshot / "config.json"), "Config copy differs")
    validate_config(config)
    checkpoint = verify_ref(root, freeze["checkpoint"])
    verify_ref(root, freeze["training_summary"])
    run_dir, audit, cases, guarded = baseline_data(root, config)
    need([b["case_id"] for b in freeze["cases"]] == [c["id"] for c in cases], "Frozen case set/order mismatch")
    validate_exposure(root, read(snapshot / "exposure.json"), cases)
    output.mkdir(parents=True, exist_ok=False)
    write_new(output / "freeze.json", freeze)
    started = datetime.now(UTC).isoformat()
    initial = {"schema": SCHEMA + ".run.v1", "status": "running", "started_at": started,
               "freeze_sha256": freeze_hash, "planned_photos": 51, "completed_photos": 0,
               "device": "cpu", "platform": platform.platform(), "automatic_promotion": False}
    write_new(output / "run.json", initial)
    # Model loads once, only after all immutable top-level prerequisites pass.
    try:
        import torch
        from torchvision.transforms.functional import pil_to_tensor

        worker = load_worker(snapshot / "detector_worker.py")
        torch.set_num_threads(4)
        load_started = time.perf_counter()
        state = torch.load(checkpoint, map_location="cpu", weights_only=True)
        need(sha(checkpoint) == CHECKPOINT_SHA, "Checkpoint changed during loading")
        need(worker.frozen_threshold(state) == 0.5 and state["epoch"] == 10, "Checkpoint metadata mismatch")
        model = worker.build_model(state["config"])
        model.load_state_dict(state["model"], strict=True)
        model.to("cpu").eval()
        load_seconds = time.perf_counter() - load_started
    except Exception as exc:  # Preserve a failed run; never fall back to the VLM baseline.
        initial.update(status="failed_setup", error=f"{type(exc).__name__}: {exc}",
                       finished_at=datetime.now(UTC).isoformat())
        (output / "run.json").write_text(json.dumps(initial, indent=2) + "\n")
        raise
    records = []
    for index, (case, frozen_case) in enumerate(zip(cases, freeze["cases"], strict=True), 1):
        attempt, base_row = guarded[case["id"]]
        record = {"schema": SCHEMA + ".case.v1", "index": index, "case_id": case["id"],
                  "baseline_attempt": attempt, "binding": frozen_case["binding"],
                  "base_observation": base_row["observation"], "fused_observation": None,
                  "detector": None, "raw_detector_output": None, "detector_call_started": False,
                  "detector_call_completed": False,
                  "washer_points": [], "excluded_points": [], "veto_matches": [], "veto_applied": False,
                  "fused_observation_scope": "experimental overlay, not a revalidated production Observation",
                  "status": "failed", "error": None,
                  "timing": {"cpu_detector_seconds": None, "fusion_seconds": None, "added_seconds": None,
                             "baseline_guarded_reused_latency_ms": base_row["latency_ms"],
                             "case_wall_seconds": None, "full_end_to_end_measured": False}}
        case_started = time.perf_counter()
        try:
            binding = bind_case(root, run_dir, case, attempt, base_row, audit)
            need(binding == frozen_case["binding"] and attempt == frozen_case["baseline_attempt"],
                 "Per-case frozen lineage changed")
            image_path = verify_ref(root, binding["normalized_input"])
            image = decoded_normalized(image_path)
            tensor = pil_to_tensor(image).float() / 255.0
            raw = recorded_detector_call(model, tensor, torch.inference_mode, record)
            detector_seconds = record["timing"]["cpu_detector_seconds"]
            record["raw_detector_output"] = {k: raw[k].tolist() for k in ("labels", "boxes", "scores")}
            summary = worker.summarize_predictions(raw["labels"].tolist(), raw["boxes"].tolist(),
                                                   raw["scores"].tolist(), 0.5, image.size)
            detector = {"architecture": config["architecture"], "checkpoint_sha256": CHECKPOINT_SHA,
                        "checkpoint_epoch": 10, "device": "cpu", "input_sha256": sha(image_path),
                        "image_size": list(image.size), "coordinate_frame": "normalized_input absolute pixel xyxy",
                        "model_return_filter": "torchvision score floor .05, NMS .5, maximum100 detections",
                        "training_data_fingerprint": state["config"].get("data_fingerprint"), **summary}
            record["detector"] = detector  # Keep raw detector output even if subsequent fusion fails.
            t0 = time.perf_counter()
            fused, points, excluded, matches = fuse(base_row["observation"],
                                          base_row["observation_diagnostics"]["passes"][0]["inventory"]["objects"],
                                          detector, binding, base_row["observation"]["verification"]["passes"][0])
            fusion_seconds = time.perf_counter() - t0
            verify_ref(root, binding["normalized_input"])
            record.update(status="ok", fused_observation=fused, washer_points=points,
                          excluded_points=excluded, veto_matches=matches, veto_applied=bool(matches))
            record["timing"].update(cpu_detector_seconds=detector_seconds, fusion_seconds=fusion_seconds,
                                    added_seconds=detector_seconds + fusion_seconds)
        except Exception as exc:  # noqa: BLE001 -- record failure once; never retry or use G as fallback.
            record["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            record["timing"]["case_wall_seconds"] = time.perf_counter() - case_started
        with (output / "predictions.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
        records.append(record)
        print(json.dumps({"completed": index, "planned": 51, "status": record["status"]}), flush=True)
    result = analyze(cases, records)
    write_new(output / "analysis.json", result)
    unchanged = sha(freeze_path) == freeze_hash and sha(checkpoint) == CHECKPOINT_SHA
    unchanged &= all(sha(snapshot / n) == h for n, h in freeze["source_hashes"].items())
    for ref in config["baseline_artifacts"].values():
        unchanged &= sha(inside(root, ref["path"])) == ref["sha256"]
    for frozen_case in freeze["cases"]:
        for key, ref in frozen_case["binding"].items():
            if key != "lineage":
                unchanged &= sha(inside(root, ref["path"])) == ref["sha256"]
    final = initial | {"status": "completed" if unchanged else "failed_integrity", "completed_photos": len(records),
                       "finished_at": datetime.now(UTC).isoformat(), "source_changed": not unchanged,
                       "model_load_seconds": load_seconds,
                       "detector_model_calls_started": sum(r["detector_call_started"] for r in records),
                       "detector_model_calls_completed": sum(r["detector_call_completed"] for r in records),
                       "versions": versions(), "analysis_sha256": sha(output / "analysis.json"),
                       "predictions_sha256": sha(output / "predictions.jsonl"),
                       "latency_scope": "Added CPU inference/fusion excludes load/decode/tensor/logging; model load separate. "
                                        "Case wall includes binding/decode/tensor/inference/fusion up to serialization; "
                                        "no full end-to-end claim"}
    (output / "run.json").write_text(json.dumps(final, indent=2) + "\n")
    need(unchanged, "Immutable evidence changed during run")
    return final


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    freeze = sub.add_parser("freeze")
    freeze.add_argument("--project-root", type=Path, default=Path.cwd())
    freeze.add_argument("--config", type=Path, default=Path(__file__).with_name("detector_veto_v1.json"))
    freeze.add_argument("--plan", type=Path, required=True)
    freeze.add_argument("--exposure", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)
    execute = sub.add_parser("run")
    execute.add_argument("--freeze", type=Path, required=True)
    execute.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "freeze":
            create_freeze(args.project_root.resolve(), args.config.resolve(), args.plan.resolve(),
                          args.exposure.resolve(), args.output.resolve())
        else:
            run(args.freeze.resolve(), args.output.resolve())
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, ImportError) as exc:
        parser.exit(1, f"Detector veto refused: {exc}\n")


if __name__ == "__main__":
    main()
