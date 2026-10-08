"""Read-only independent metadata/raw-result audits; never import a detector or MLX.

Only new report files outside immutable input directories may be created.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import itertools
import json
import math
import statistics
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKPOINT_SHA = "2022c203a3b3b36dd146534c8bcfc538739cf8bf643066fc14a5b9611ebeb62c"
MANIFEST_SHA = "efe4633e873d45032101a26e035c23d267bafa6605d147d3d2f7fcb51b697643"
AUDIT_SHA = "94c71e45341a5065ee90fe601e606cd3a54242094d5dcc08770f6aae8c588fe9"
PARTS = ("bolt", "nut", "washer", "bracket")
VETO_ISSUE = "Experimental detector/VLM category conflict: nut and washer require additional evidence."


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def exposure_matches(case, images):
    """Recorded original family match; never use the derived view hash as its family."""
    name = Path(case.get("source_image") or case["source_id"].split(":")[-1]).name
    matches = []
    for image in images:
        reasons = []
        if case["source_sha256"] == image["source_sha256"]:
            reasons.append("original_file_sha256")
        if case["source_decoded_rgb_sha256"] == image["source_decoded_rgb_sha256"]:
            reasons.append("original_decoded_rgb_sha256")
        if name == image["original_filename"]:
            reasons.append("original_filename")
        if reasons:
            matches.append({"original_filename": image["original_filename"], "reasons": reasons})
    return matches


def audit_exposure(root=ROOT):
    root = root.resolve()
    data = root / "datasets/derived/public_detector_v1"
    training = root / "training-runs/public_detector_v1_mps_20260930"
    manifest_path = root / "datasets/derived/v0.7/public_paired_v1/manifest.json"
    prior_path = root / "test-results/v0.7/public-paired-audit-v1.json"
    require(sha(manifest_path) == MANIFEST_SHA, "Previously exposed 51-image manifest changed")
    require(sha(prior_path) == AUDIT_SHA, "Prior independent audit changed")
    prior = read(prior_path)
    require(prior["status"] == "passed" and prior["completed_attempts"] == 153, "Prior audit incomplete")
    cases = read(manifest_path)["cases"]
    require(len(cases) == len({c["source_sha256"] for c in cases}) == 51, "Need exactly 51 source families")
    protocol, summary = read(training / "protocol.json"), read(training / "training_summary.json")
    fingerprints = {name: sha(data / name) for name in ("manifest.json", "train.json", "val.json", "test.json")}
    require(fingerprints == protocol["data_fingerprint"], "Detector data differs from recorded training protocol")
    checkpoint = training / "best.pt"
    require(sha(checkpoint) == summary["best_checkpoint_sha256"] == CHECKPOINT_SHA, "Fixed v1 checkpoint changed")
    require(summary["status"] == "complete" and summary["best_epoch"] == 10 and summary["threshold"] == .5,
            "Detector selection metadata differs from fixed v1")
    selected = read(training / "best_validation_metrics.json")
    require(selected["threshold"] == .5, "Validation-selected threshold differs")
    splits = {split: read(data / f"{split}.json")["images"] for split in ("train", "val", "test")}
    require({k: len(v) for k, v in splits.items()} == {"train": 214, "val": 44, "test": 22}, "Training split sizes changed")
    rows = [{"case_id": case["id"], "source_id": case["source_id"], "subgroup": case["subgroup"],
             "source_sha256": case["source_sha256"], "source_decoded_rgb_sha256": case["source_decoded_rgb_sha256"],
             "v1_stage_matches": {split: exposure_matches(case, images) for split, images in splits.items()},
             "already_exposed_in_v07": True} for case in cases]
    paths = [manifest_path, prior_path, training / "protocol.json", training / "training_summary.json",
             training / "best_validation_metrics.json", checkpoint, *[data / name for name in fingerprints]]
    return {"schema": "kitguard.v08.heterogeneous-veto.exposure.v1", "status": "checked",
            "checked_at": datetime.now(UTC).isoformat(), "planned_cases": 51,
            "training_stage_sizes": {k: len(v) for k, v in splits.items()},
            "overlap_counts": {split: sum(bool(r["v1_stage_matches"][split]) for r in rows) for split in splits},
            "checkpoint_sha256": CHECKPOINT_SHA, "checkpoint_bytes": checkpoint.stat().st_size,
            "threshold": .5, "best_epoch": 10, "detector_config": {k: protocol[k] for k in ("model", "min_size", "max_size", "classes")},
            "files_sha256": {str(p.relative_to(root)): sha(p) for p in paths}, "cases": rows,
            "independent_holdout": False, "model_loaded_or_called": False,
            "limitations": ["No exact recorded source family overlap does not establish statistical/domain independence.",
                            "All 51 cases were observed in v0.7, and their failures motivated this candidate; this is development only.",
                            "Same physical objects/capture sessions and foundation-model pretraining overlap cannot be certified.",
                            "The detector has bolt/nut training only; true washer negatives are mandatory and absence cannot be inferred."]}


def inside(root, relative):
    require(isinstance(relative, str) and relative and not Path(relative).is_absolute(), "Expected relative path")
    require(".." not in Path(relative).parts, "Parent traversal in evidence path")
    path = (root / relative).resolve()
    require(path.is_relative_to(root.resolve()), "Evidence path escapes root")
    require(not (root / relative).is_symlink(), "Evidence symlink is not accepted")
    return path


def verify_ref(root, ref):
    path = inside(root, ref["path"])
    require(sha(path) == ref["sha256"], f"Changed evidence: {ref['path']}")
    return path


def number(value, low=0, high=math.inf):
    return type(value) in (float, int) and math.isfinite(value) and low <= value <= high


def source_pixel_sha(image):
    """Original-family hash includes dimensions/mode, as frozen by v0.7."""
    rgb = image.convert("RGB")
    return hashlib.sha256(str(rgb.size).encode() + b"|RGB|" + rgb.tobytes()).hexdigest()


def validate_raw(raw, size):
    """Rebuild every returned detection without importing the worker or torch."""
    require(set(raw) == {"labels", "boxes", "scores"}, "Unexpected raw detector output keys")
    require(all(isinstance(raw[k], list) for k in raw), "Raw arrays must be lists")
    require(len(raw["labels"]) == len(raw["boxes"]) == len(raw["scores"]) <= 100, "Raw array lengths differ")
    predictions, counts = [], {"bolt": 0, "nut": 0, "washer": None, "bracket": None}
    for label, box, score in zip(raw["labels"], raw["boxes"], raw["scores"], strict=True):
        require(type(label) is int and label in (1, 2), "Invalid raw label")
        require(number(score, 0, 1), "Invalid raw score")
        require(isinstance(box, list) and len(box) == 4 and all(number(v) for v in box), "Invalid raw box")
        require(0 <= box[0] < box[2] <= size[0] and 0 <= box[1] < box[3] <= size[1], "Raw box outside image")
        name = {1: "bolt", 2: "nut"}[label]
        retained = score >= .5
        counts[name] += int(retained)
        predictions.append({"label": label, "class_name": name, "bbox_xyxy": box, "score": float(score),
                            "retained_at_frozen_threshold": retained})
    return predictions, counts


def reconstruct_overlay(base, original, size, predictions):
    """No truth, BOM, case label or detector count is accepted by this function."""
    require(len(size) == 2 and all(type(v) is int and v >= 2 for v in size), "Invalid image dimensions")
    objects = original["objects"]
    candidates = []
    for index, obj in enumerate(objects, 1):
        require(obj["part"] in PARTS, "Invalid original part")
        center = obj["center"]
        require(isinstance(center, list) and len(center) == 2 and all(number(v, 0, 1) for v in center),
                "Invalid original center")
        if obj["part"] == "washer":
            candidates.append({"object_index": index, "center": center,
                               "point_xy": [center[0] * (size[0] - 1), center[1] * (size[1] - 1)]})
    count = original["observed"]["washer"]
    eligible = "washer" not in original["uncertain_parts"] and type(count) is int and count == len(candidates)
    points = candidates if eligible else []
    excluded = [] if eligible else [point | {"reason": "original_washer_category_unclear"} for point in candidates]
    matches = []
    for p in points:
        x, y = p["point_xy"]
        for j, prediction in enumerate(predictions):
            x1, y1, x2, y2 = prediction["bbox_xyxy"]
            if prediction["label"] == 2 and prediction["score"] >= .5 and x1 <= x <= x2 and y1 <= y <= y2:
                matches.append({"object_index": p["object_index"], "prediction_index": j,
                                "point_xy": p["point_xy"], "bbox_xyxy": prediction["bbox_xyxy"],
                                "score": prediction["score"]})
    # Runner enumerates boxes then points; order is evidence, not a set.
    matches.sort(key=lambda m: (m["prediction_index"], m["object_index"]))
    fused = copy.deepcopy(base)
    fused.pop("latency_ms", None)
    if matches:
        fused["observed"]["nut"] = None
        fused["observed"]["washer"] = None
        fused["issues"].append(VETO_ISSUE)
        if fused["action"]["kind"] == "none":
            fused["action"] = {"kind": "recapture", "message": VETO_ISSUE, "region": None}
    return fused, points, excluded, matches


def classify(observation, truth, error=None):
    if error or observation is None:
        return "E"
    require(set(observation["observed"]) == set(PARTS), "Observation part set differs")
    require(all(v is None or (type(v) is int and v >= 0) for v in observation["observed"].values()),
            "Invalid observed count")
    if observation["issues"] or observation["action"]["kind"] != "none" or None in observation["observed"].values():
        return "U"
    return "C" if observation["observed"] == truth else "W"


def panels(case, observation, error=None):
    result = {}
    for name, parts in (("all_four", PARTS), ("source_supported", case["supported_positive_classes"])):
        requirements = [dict.fromkeys(PARTS, 0) | dict(zip(parts, v, strict=True))
                        for v in itertools.product(range(4), repeat=len(parts)) if any(v)]
        mismatched = [r for r in requirements if r != case["ground_truth"]]
        actionable = classify(observation, case["ground_truth"], error) in ("C", "W")
        false = [r for r in mismatched if actionable and observation["observed"] == r]
        result[name] = {"mismatched_orders": len(mismatched), "false_ready_orders": false,
                        "any_false_ready": bool(false), "risk_measured": not bool(error)}
    return result


def verify_lineage(root, case, base_row, binding, attempt, prior):
    from PIL import Image

    paths = {key: verify_ref(root, ref) for key, ref in binding.items() if key != "lineage"}
    source = inside(root / "datasets", case.get("source_image", case["image"]))
    selected = inside(root / "datasets", case["image"])
    require(paths["source_image"] == source and paths["selected_image"] == selected, "Source family path differs")
    require(sha(source) == case["source_sha256"] and sha(selected) == case["sha256"], "Source family hash differs")
    with Image.open(source) as image:
        require(source_pixel_sha(image) == case["source_decoded_rgb_sha256"],
                "Original decoded RGB fingerprint differs")
        if case["derived_view"]:
            crop_buffer = io.BytesIO()
            image.convert("RGB").crop(case["crop_xyxy"]).save(crop_buffer, format="PNG")
            require(hashlib.sha256(crop_buffer.getvalue()).hexdigest() == case["sha256"], "Source crop lineage differs")
    run = root / "evaluation-runs/v0.7/public_paired_v1"
    stem = f"{attempt:03d}-spatial_guarded"
    require(paths["normalized_input"] == run / "normalized_inputs" / f"{stem}.jpg", "Wrong normalized input path")
    require(paths["original_generation"] == run / "cases" / stem / "call-01/generation.json", "Wrong original call path")
    require(paths["original_vlm_input"] == run / "cases" / stem / "call-01/image-01.png", "Wrong original VLM input path")
    for key in ("normalized_input", "original_generation", "original_vlm_input"):
        require(sha(paths[key]) == prior["artifacts_sha256"][paths[key].relative_to(run).as_posix()],
                "Input no longer matches independent v0.7 audit")
    generation = read(paths["original_generation"])
    obs, diagnostic = base_row["observation"], base_row["observation_diagnostics"]
    original = obs["verification"]["passes"][0]
    inventory = diagnostic["passes"][0]["inventory"]
    require(generation["status"] == "parsed" and json.loads(generation["raw_text"]) == generation["parsed"] == inventory,
            "Original raw/parsed inventory differs")
    require(original["transform"] == diagnostic["passes"][0]["transform"] == "original", "Original pass missing")
    require(obs["object_evidence"]["coordinate_frame"] == "normalized_original", "Wrong original coordinate frame")
    require(original["objects"] == inventory["objects"] == obs["object_evidence"]["objects"], "Original object list differs")
    require(original["uncertain_parts"] == inventory["uncertain_parts"], "Original uncertainty differs")
    require(sha(paths["normalized_input"]) == base_row["normalized_sha256"] == diagnostic["source_sha256"],
            "Normalized input row SHA differs")
    require(len(generation["images"]) == 1 and generation["images"][0]["sha256"] == original["input_sha256"]
            == diagnostic["passes"][0]["input_sha256"] == sha(paths["original_vlm_input"]), "Original call input differs")
    with Image.open(paths["normalized_input"]) as encoded:
        require(encoded.getexif().get(274) in (None, 1) and getattr(encoded, "n_frames", 1) == 1, "Unbound EXIF/animation")
        rgb = encoded.convert("RGB")
        rgb.load()
    vlm = rgb.copy()
    vlm.thumbnail((1536, 1536), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    vlm.save(buffer, format="PNG")
    require(hashlib.sha256(buffer.getvalue()).hexdigest() == sha(paths["original_vlm_input"]), "Thumbnail byte lineage differs")
    with Image.open(paths["original_vlm_input"]) as saved:
        require(saved.size == vlm.size and saved.convert("RGB").tobytes() == vlm.tobytes(), "Thumbnail pixel lineage differs")
    expected = {"detector_image_size": list(rgb.size), "vlm_image_size": list(vlm.size),
                "normalized_rgb_sha256": hashlib.sha256(rgb.tobytes()).hexdigest(),
                "vlm_rgb_sha256": hashlib.sha256(vlm.tobytes()).hexdigest(),
                "transform": "EXIF-oriented RGB, LANCZOS thumbnail max_side=1536; no crop/rotation"}
    require(binding["lineage"] == expected, "Recorded coordinate lineage differs")
    return original, list(rgb.size)


def verify_case(row, base_row, original, size):
    require(row["base_observation"] == base_row["observation"], "Baseline observation changed")
    require(row["fused_observation_scope"] == "experimental overlay, not a revalidated production Observation",
            "Overlay must not claim production validation")
    timing = row["timing"]
    require(timing["full_end_to_end_measured"] is False
            and timing["baseline_guarded_reused_latency_ms"] == base_row["latency_ms"], "Historical latency relabelled")
    for field in ("cpu_detector_seconds", "fusion_seconds", "added_seconds"):
        require(timing[field] is None or number(timing[field]), "Invalid timing")
    require(number(timing["case_wall_seconds"]), "Missing full attempt wall time")
    require(type(row["detector_call_started"]) is bool and type(row["detector_call_completed"]) is bool,
            "Call states must be booleans")
    require(not row["detector_call_completed"] or row["detector_call_started"], "Call completed without start")
    require((timing["cpu_detector_seconds"] is not None) == row["detector_call_started"], "Started call lost elapsed time")
    require(timing["cpu_detector_seconds"] is None or timing["case_wall_seconds"] >= timing["cpu_detector_seconds"],
            "Attempt wall time shorter than model call")
    raw, detector = row["raw_detector_output"], row["detector"]
    parsed, raw_error = None, None
    if raw is not None:
        require(row["detector_call_started"] is True and row["detector_call_completed"] is True, "Raw result without completed call")
        try:
            parsed = validate_raw(raw, size)
        except ValueError as exc:
            raw_error = str(exc)
    if detector is not None:
        require(parsed is not None, "Detector summary exists without valid raw arrays")
        predictions, counts = parsed
        require(detector["predictions"] == predictions and detector["counts"] == counts, "Raw detector summary differs")
        require(detector["checkpoint_sha256"] == CHECKPOINT_SHA and detector["checkpoint_epoch"] == 10
                and detector["device"] == "cpu" and detector["threshold"] == .5, "Wrong detector identity")
        require(detector["architecture"] == "fasterrcnn_mobilenet_v3_large_320_fpn"
                and detector["coordinate_frame"] == "normalized_input absolute pixel xyxy"
                and detector["threshold_comparison"] == "score >= threshold"
                and detector["model_return_filter"] == "torchvision score floor .05, NMS .5, maximum100 detections",
                "Detector coordinate/filter metadata differs")
        require(detector["input_sha256"] == row["binding"]["normalized_input"]["sha256"]
                and detector["image_size"] == size, "Wrong detector image binding")
        require(detector["unsupported_classes"] == ["washer", "bracket"] and detector["decision"] is None,
                "Detector claims unsupported class or decision")
    if row["status"] == "failed":
        require(isinstance(row["error"], str) and row["error"] and row["fused_observation"] is None,
                "Failed case must preserve error without G fallback")
        require(row["veto_applied"] is False and row["washer_points"] == row["excluded_points"] == row["veto_matches"] == [],
                "Failed case cannot preserve a successful overlay")
        return {"failure_replay": "raw_validation_failed" if raw_error else "runtime_failure_not_reexecuted",
                "raw_validation_error": raw_error}
    require(row["status"] == "ok" and row["error"] is None and detector is not None and parsed is not None,
            "Successful row has missing raw result or error")
    require(all(number(timing[k]) for k in ("cpu_detector_seconds", "fusion_seconds", "added_seconds")), "Missing successful timing")
    require(math.isclose(timing["added_seconds"], timing["cpu_detector_seconds"] + timing["fusion_seconds"],
                         rel_tol=1e-12, abs_tol=1e-12), "Added timing is not CPU plus fusion")
    require(timing["case_wall_seconds"] >= timing["added_seconds"], "Added time exceeds attempt wall time")
    fused, points, excluded, matches = reconstruct_overlay(base_row["observation"], original, size, parsed[0])
    require(row["fused_observation"] == fused, "Overlay changed more than the frozen conservative rule")
    require(row["washer_points"] == points and row["excluded_points"] == excluded, "Eligible/excluded washer points differ")
    require(row["veto_matches"] == matches and row["veto_applied"] is bool(matches), "Geometric veto matches differ")
    return {"failure_replay": None, "raw_validation_error": None}


def audit_run(root, run_dir, freeze_path):
    root, run_dir, freeze_path = root.resolve(), run_dir.resolve(), freeze_path.resolve()
    metadata = read(run_dir / "run.json")
    require(metadata["status"] == "completed", "Run incomplete; predictions intentionally unread")
    require(metadata["planned_photos"] == metadata["completed_photos"] == 51 and metadata["source_changed"] is False,
            "Completed immutable 51-photo denominator required")
    require(metadata["freeze_sha256"] == sha(freeze_path), "Run freeze SHA differs")
    freeze = read(freeze_path)
    require(read(run_dir / "freeze.json") == freeze and freeze["planned_photos"] == 51, "Freeze copy differs")
    require(freeze["automatic_promotion"] is False and freeze["new_holdout"] is False, "Scope flags changed")
    snapshot = freeze_path.parent / "source_snapshot"
    for name, expected in freeze["source_hashes"].items():
        require(sha(inside(snapshot, name)) == expected, "Frozen snapshot changed")
    config = freeze["config"]
    require(config == read(snapshot / "config.json"), "Frozen config copy differs")
    require(config["checkpoint_sha256"] == CHECKPOINT_SHA and config["threshold"] == .5
            and config["retries"] == 0 and config["warmup"] is False and config["cpu_threads"] == 4
            and config["device"] == "cpu" and config["planned_photos"] == 51, "Inference protocol changed")
    require(metadata["versions"] == freeze["versions"], "Dependency versions changed")
    require(sha(verify_ref(root, freeze["checkpoint"])) == CHECKPOINT_SHA, "Checkpoint differs")
    verify_ref(root, freeze["training_summary"])
    assets = {name: verify_ref(root, ref) for name, ref in config["baseline_artifacts"].items()}
    require(sha(assets["manifest.json"]) == MANIFEST_SHA and sha(assets["independent_audit"]) == AUDIT_SHA,
            "Baseline pin differs")
    prior = read(assets["independent_audit"])
    require(prior["status"] == "passed" and prior["completed_attempts"] == 153, "Baseline audit incomplete")
    for name in ("run.json", "analysis.json", "manifest.json", "freeze.json", "predictions.jsonl"):
        require(sha(assets[name]) == prior["artifacts_sha256"][name], "Baseline not covered by prior audit")
    exposure = read(snapshot / "exposure.json")
    require(exposure["status"] == "checked" and exposure["planned_cases"] == 51 and exposure["independent_holdout"] is False,
            "Exposure scope differs")
    for path, expected in exposure["files_sha256"].items():
        require(sha(inside(root, path)) == expected, "Exposure audit source changed")
    cases = read(assets["manifest.json"])["cases"]
    old = [json.loads(line) for line in assets["predictions.jsonl"].read_text().splitlines()]
    guarded = {r["case_id"]: (i, r) for i, r in enumerate(old, 1) if r["mode"] == "spatial_guarded"}
    require(len(old) == 153 and len(guarded) == len(cases) == 51, "Baseline denominator differs")
    records = [json.loads(line) for line in (run_dir / "predictions.jsonl").read_text().splitlines()]
    require(len(records) == 51 and [r["case_id"] for r in records] == [c["id"] for c in cases]
            == [b["case_id"] for b in freeze["cases"]], "Missing/duplicate/reordered cases")
    require(metadata["predictions_sha256"] == sha(run_dir / "predictions.jsonl")
            and metadata["analysis_sha256"] == sha(run_dir / "analysis.json"), "Run ledger hash differs")
    for state in ("started", "completed"):
        require(metadata[f"detector_model_calls_{state}"] == sum(r[f"detector_call_{state}"] for r in records),
                "Model call count differs")
    outcomes, base_counts, transitions = Counter(), Counter(), Counter()
    groups, receipt_rows, panel_rows, changes = {}, [], [], []
    controls = {"planned": 0, "previously_C_denominator": 0, "errors": 0, "veto_applied": 0,
                "previously_C_to_U": 0, "unchanged_C": 0}
    for index, (case, row, frozen_case) in enumerate(zip(cases, records, freeze["cases"], strict=True), 1):
        attempt, base_row = guarded[case["id"]]
        require(row["schema"] == "kitguard.v08.detector-veto.case.v1" and row["index"] == index
                and row["baseline_attempt"] == frozen_case["baseline_attempt"] == attempt
                and row["binding"] == frozen_case["binding"], "Case binding differs")
        original, size = verify_lineage(root, case, base_row, row["binding"], attempt, prior)
        details = verify_case(row, base_row, original, size)
        if row["detector"] is not None:
            require(row["detector"]["training_data_fingerprint"] == read(root / "training-runs/public_detector_v1_mps_20260930/protocol.json")["data_fingerprint"],
                    "Detector training fingerprint differs")
        before = classify(base_row["observation"], case["ground_truth"])
        after = classify(row["fused_observation"], case["ground_truth"], row["error"])
        require(after in (before, "U", "E"), "Overlay improperly improved actionability/counts")
        outcomes[after] += 1
        base_counts[before] += 1
        transitions[f"{before}->{after}"] += 1
        groups.setdefault(case["subgroup"], Counter())[after] += 1
        pair = {"case_id": case["id"], "base": before, "fused": after, "veto_applied": row["veto_applied"]}
        changes.append(pair)
        receipt_rows.append(pair | details)
        panel_rows.append({"case_id": case["id"], "base": panels(case, base_row["observation"]),
                           "fused": panels(case, row["fused_observation"], row["error"])})
        if case["subgroup"] == "loco_normal_222":
            require(case["ground_truth"] == dict(zip(PARTS, (2, 2, 2, 0), strict=True)), "LOCO control truth changed")
            controls["planned"] += 1
            controls["previously_C_denominator"] += int(before == "C")
            controls["errors"] += int(after == "E")
            controls["veto_applied"] += int(row["veto_applied"])
            controls["previously_C_to_U"] += int(before == "C" and after == "U")
            controls["unchanged_C"] += int(before == after == "C")
    counts = lambda counter: {k: counter[k] for k in "CWUEN"}
    require(counts(base_counts) == dict(zip("CWUEN", (41, 3, 7, 0, 0), strict=True)), "Saved G baseline outcomes differ")
    require(controls["planned"] == 16 and controls["previously_C_denominator"] == 14, "True-washer control denominator differs")
    false_ready = {name: {arm: sum(p[arm][name]["any_false_ready"] for p in panel_rows) for arm in ("base", "fused")}
                   for name in ("all_four", "source_supported")}
    analysis = read(run_dir / "analysis.json")
    for key, expected in {"outcomes": counts(outcomes), "paired_transitions": dict(sorted(transitions.items())),
                          "case_transitions": changes, "panels": panel_rows, "false_ready_summary": false_ready,
                          "unmeasured_risk_images": outcomes["E"]}.items():
        require(analysis[key] == expected, f"Analysis {key} differs from independent result")
    require(analysis["loco_true_washer_negative_controls"] == controls, "LOCO control report differs")
    expected_groups = {name: {"planned": sum(counter.values()), "outcomes": counts(counter)} for name, counter in groups.items()}
    require(analysis["source_groups"] == expected_groups, "Source group outcomes differ")
    require(analysis["automatic_promotion"] is False and analysis["new_holdout"] is False, "Analysis scope flags changed")
    elapsed = [r["timing"]["added_seconds"] for r in records if r["timing"]["added_seconds"] is not None]
    expected_elapsed = {"measured": len(elapsed), "median_seconds": statistics.median(elapsed) if elapsed else None,
                        "total_seconds": sum(elapsed)}
    require(all(analysis["added_latency"][k] == v for k, v in expected_elapsed.items()), "Timing summary differs")
    for field in ("cpu_detector_seconds", "fusion_seconds", "added_seconds", "case_wall_seconds"):
        values = sorted(r["timing"][field] for r in records if r["timing"][field] is not None)
        expected = {"measured": len(values), "median_seconds": statistics.median(values) if values else None,
                    "p90_seconds": values[(9 * len(values) + 9) // 10 - 1] if values else None,
                    "total_seconds": sum(values)}
        require(analysis["timing"][field] == expected, "Timing stage summary differs")
    checks = {"all_51_attempted": outcomes["N"] == 0, "no_wrong": outcomes["W"] == 0,
              "no_errors": outcomes["E"] == 0, "no_all_four_false_ready": false_ready["all_four"]["fused"] == 0,
              "no_correct_coverage_loss": outcomes["C"] == base_counts["C"],
              "no_loco_correct_loss": controls["unchanged_C"] == controls["previously_C_denominator"]}
    expected_gates = {"full51": True, "zero_wrong_actionable": checks["no_wrong"],
                      "zero_execution_or_missing": checks["no_errors"],
                      "zero_all_four_false_ready": checks["no_all_four_false_ready"],
                      "no_previous_correct_lost": checks["no_correct_coverage_loss"],
                      "loco_previous_correct_preserved": checks["no_loco_correct_loss"]}
    require(analysis["further_validation"] == {"checks": expected_gates,
            "descriptive_conditions_met": all(expected_gates.values()), "independent_audit_required": True,
            "eligibility": "pending_independent_audit"}, "Predeclared followup condition report differs")
    return {"schema": "kitguard.v08.heterogeneous-veto.audit.v1", "status": "passed",
            "audited_at": datetime.now(UTC).isoformat(), "planned_photos": 51,
            "baseline_outcomes": counts(base_counts), "outcomes": counts(outcomes),
            "source_group_outcomes": {k: counts(v) for k, v in groups.items()},
            "paired_transitions": dict(sorted(transitions.items())), "false_ready_summary": false_ready,
            "loco_true_washer_negative_controls": controls, "new_source_followup_checks": checks,
            "eligible_for_new_source_validation": all(checks.values()), "automatic_promotion": False,
            "new_holdout": False, "model_loaded_or_called": False, "runtime_failures_reexecuted": False,
            "cases": receipt_rows, "freeze_sha256": sha(freeze_path), "auditor_sha256": sha(Path(__file__)),
            "artifacts_sha256": {p.name: sha(p) for p in (run_dir / "run.json", run_dir / "predictions.jsonl",
                                                         run_dir / "analysis.json", run_dir / "freeze.json")},
            "limitations": ["Audits preserved outputs, not physical truth or detector computation by rerunning it.",
                            "CPU detector/fusion timings do not measure a new end-to-end VLM pipeline.",
                            "All 51 images are exposed development evidence; no independent generalization claim."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["exposure", "run"])
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--freeze", type=Path)
    args = parser.parse_args()
    require(not args.output.exists(), "Do not overwrite an existing audit receipt")
    if args.command == "run":
        require(args.run_dir is not None and args.freeze is not None, "run requires --run-dir and --freeze")
        require(not args.output.resolve().is_relative_to(args.run_dir.resolve())
                and not args.output.resolve().is_relative_to(args.freeze.parent.resolve()), "Audit output must be outside immutable inputs")
        result = audit_run(args.project_root, args.run_dir, args.freeze)
    else:
        result = audit_exposure(args.project_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"status": result["status"], "overlap_counts": result.get("overlap_counts"),
                      "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
