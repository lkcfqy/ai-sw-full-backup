"""Independent saved-output shadow audit. Stdlib + PIL; no runner/model imports or inference."""
from __future__ import annotations

import argparse
import copy
import hashlib
import itertools
import json
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

PARTS = ("bolt", "nut", "washer", "bracket")
CLASSES = {1: "bolt", 2: "nut", 3: "washer"}
ISSUE = "Experimental detector/G count conflict: nut and washer require additional evidence."


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def compare(a, b, context):
    if isinstance(b, dict):
        require(isinstance(a, dict) and a.keys() == b.keys(), context + " keys")
        for key in b:
            compare(a[key], b[key], context + "." + str(key))
    elif isinstance(b, list):
        require(isinstance(a, list) and len(a) == len(b), context + " list")
        for i, value in enumerate(b):
            compare(a[i], value, context + f"[{i}]")
    elif type(b) is float:
        require(type(a) in (int, float) and math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12), context + " float")
    else:
        require(type(a) is type(b) and a == b, context + " value")


def overlap(a, b):
    inter = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    return inter / ((a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter)


def detector(raw, threshold, size):
    require(set(raw) == {"labels", "scores", "boxes"}, "Raw output keys")
    require(len(raw["labels"]) == len(raw["scores"]) == len(raw["boxes"]) <= 100, "Raw length")
    counts, predictions = dict.fromkeys(CLASSES.values(), 0), []
    for i, (label, score, box) in enumerate(zip(raw["labels"], raw["scores"], raw["boxes"], strict=True)):
        require(type(label) is int and label in CLASSES, "Raw class")
        require(type(score) in (int, float) and math.isfinite(score) and 0 <= score <= 1, "Raw score")
        require(len(box) == 4 and all(type(x) in (int, float) and math.isfinite(x) for x in box), "Raw box")
        require(0 <= box[0] < box[2] <= size[0] and 0 <= box[1] < box[3] <= size[1], "Box outside actual input")
        kept = score >= threshold
        counts[CLASSES[label]] += int(kept)
        predictions.append({"index": i, "label": label, "class_name": CLASSES[label], "box": box,
                            "score": score, "retained": kept})
    pairs = []
    for i in range(len(predictions)):
        for j in range(i + 1, len(predictions)):
            a, b = predictions[i], predictions[j]
            if a["label"] != b["label"]:
                value = overlap(a["box"], b["box"])
                if value >= .5:
                    pairs.append({"indices": [i, j], "iou": value, "both_retained": a["retained"] and b["retained"]})
    return {"threshold": threshold, "counts": counts, "predictions": predictions, "cross_class_overlaps": pairs,
            "unsupported_classes": ["bracket"], "counts_are_true_lower_bounds": False}


def fusion(base, detection):
    """No truth, requirements, case name or VLM center arguments accepted."""
    observed = base["observed"]
    uncertain = (base.get("object_evidence") or {}).get("uncertain_parts", [])
    triggers = []
    for part in ("nut", "washer"):
        if (type(observed[part]) is int and observed[part] >= 0 and part not in uncertain
                and detection["counts"][part] > observed[part]):
            triggers.append({"part": part, "G_count": observed[part], "detector_candidates": detection["counts"][part],
                                 "prediction_indices": [p["index"] for p in detection["predictions"]
                                                        if p["retained"] and p["class_name"] == part]})
    result = copy.deepcopy(base)
    if triggers:
        result["observed"]["nut"] = None
        result["observed"]["washer"] = None
        result["issues"].append(ISSUE)
    return result, triggers


def outcome(observation, truth):
    if observation is None:
        return "E"
    if observation["action"]["kind"] != "none" or observation["issues"] or any(observation["observed"][p] is None for p in PARTS):
        return "U"
    return "C" if observation["observed"] == truth else "W"


def risk(case, observation):
    actionable = outcome(observation, case["ground_truth"]) in ("C", "W")
    panels = {}
    for name, parts in (("all_four", PARTS), ("source_supported", case["supported_positive_classes"])):
        orders = []
        for numbers in itertools.product(range(4), repeat=len(parts)):
            if not any(numbers):
                continue
            order = dict.fromkeys(PARTS, 0)
            order.update(zip(parts, numbers, strict=True))
            if order != case["ground_truth"]:
                orders.append(order)
        wrong = [o for o in orders if actionable and observation["observed"] == o]
        panels[name] = {"mismatched_orders": len(orders), "false_ready_orders": wrong, "any_false_ready": bool(wrong)}
    return panels


def audit(root, run_dir, freeze_path):
    from PIL import Image
    state, frozen, summary = (read(run_dir / x) for x in ("run.json", "freeze.json", "analysis.json"))
    require(state["status"] == "completed" and state["source_changed"] is False, "Completed unchanged run required")
    require(state["recorded_cases"] == state["detector_calls_started"] == state["detector_calls_completed"] == 51,
            "Need all 51 actual calls")
    require(sha(freeze_path) == sha(run_dir / "freeze.json") == state["freeze_sha256"], "Freeze hash")
    compare(frozen, read(freeze_path), "freeze copy")
    for name, expected in frozen["source_hashes"].items():
        require(sha(freeze_path.parent / "source_snapshot" / name) == expected, "Source snapshot hash")
    require(sha(run_dir / "predictions.jsonl") == state["predictions_sha256"], "Prediction hash")
    require(sha(run_dir / "analysis.json") == state["analysis_sha256"], "Analysis hash")
    refs = frozen["baseline_files"] + frozen["training"]["files"] + [frozen["annotations"], frozen["plan"]]
    refs += [ref for item in frozen["cases"] for ref in item["binding"]["files"]]
    for ref in refs:
        p = (root / ref["path"]).resolve()
        require(p.is_relative_to(root), "Evidence path escapes root")
        require(sha(p) == ref["sha256"], f"Bound file changed {p}")
    for path, value in frozen["training"]["protocol"]["runtime_sha256"].items():
        require(sha(path) == value, "Detector runtime changed")
    training_audit = read(root / frozen["training"]["independent_training_audit"]["path"])
    require(training_audit["status"] == "passed" and training_audit["checkpoint_metadata_inspected"] is True,
            "Independent checkpoint selection audit missing")
    compare(frozen["training"]["selection"], training_audit["best"], "Training selection")
    threshold = training_audit["best"]["threshold"]
    require(threshold == .5 and training_audit["best"]["epoch"] == 7, "Unexpected frozen selected threshold")
    baseline_directory = root / "evaluation-runs/v0.7/public_paired_v1"
    original = [json.loads(line) for line in (baseline_directory / "predictions.jsonl").read_text().splitlines()]
    guard = {r["case_id"]: r for r in original if r["mode"] == "spatial_guarded"}
    original_manifest = read(baseline_directory / "manifest.json")
    cases = {c["id"]: c for c in original_manifest["cases"]}
    rows = [json.loads(line) for line in (run_dir / "predictions.jsonl").read_text().splitlines()]
    require(len(rows) == len(frozen["cases"]) == len({r["case_id"] for r in rows}) == 51, "Full case set")
    counts, transitions, strata, changes, panels = Counter(), Counter(), {}, [], []
    old_counts, lost, old_wrong, loco = Counter(), [], [], []
    boxes = kept = cross_pairs = cross_kept = 0
    for index, (item, row) in enumerate(zip(frozen["cases"], rows, strict=True), 1):
        case, base = item["case"], item["base_observation"]
        require(row["index"] == index and row["case_id"] == case["id"], "Case order")
        compare(case, cases[case["id"]], "Original manifest case")
        compare(base, guard[case["id"]]["observation"], "Original G observation")
        compare(row["base_observation"], base, "Saved base")
        compare(row["binding"], item["binding"], "Input binding")
        require(row["status"] == "ok" and row["error"] is None
                and row["detector_call_started"] is True and row["detector_call_completed"] is True,
                "All calls must be successfully preserved for this accepted audit")
        actual = root / item["binding"]["actual_input"]["path"]
        require(sha(actual) == item["binding"]["actual_input"]["sha256"], "Actual input SHA")
        with Image.open(actual) as im:
            im = im.convert("RGB")
            require(list(im.size) == item["binding"]["actual_input_size"], "Actual input size")
            h = hashlib.sha256(str(im.size).encode() + b"|RGB|" + im.tobytes()).hexdigest()
            require(h == item["binding"]["actual_input_rgb_sha256"], "Actual input pixels")
        generation_ref = next(x for x in item["binding"]["files"] if x["path"].endswith("call-01/generation.json"))
        gen = read(root / generation_ref["path"])
        require(gen["images"][0]["sha256"] == sha(actual), "Original G generation input differs")
        require(guard[case["id"]]["observation_diagnostics"]["passes"][0]["transform"] == "original", "G pass not original")
        computed = detector(row["raw_detector_output"], threshold, item["binding"]["actual_input_size"])
        compare(row["detector"], computed, "Raw detector recomputation")
        effective, triggers = fusion(base, computed)
        compare(row["effective_observation"], effective, "Fusion")
        compare(row["triggers"], triggers, "Triggers")
        old, new = outcome(base, case["ground_truth"]), outcome(effective, case["ground_truth"])
        require(not (old in ("W", "U") and new == "C"), "Veto cannot repair counts")
        old_counts[old] += 1
        counts[new] += 1
        transitions[f"{old}->{new}"] += 1
        strata.setdefault(case["subgroup"], Counter())[new] += 1
        item_change = {"case_id": case["id"], "old": old, "new": new, "veto_applied": bool(triggers)}
        changes.append(item_change)
        if old == "C" and new != "C":
            lost.append(case["id"])
        if old == "W":
            old_wrong.append(item_change | {"G_counts": base["observed"], "detector_counts": computed["counts"], "triggers": triggers})
        if case["subgroup"] == "loco_normal_222":
            loco.append(item_change)
        panels.append({"case_id": case["id"], "base": risk(case, base), "shadow": risk(case, effective)})
        boxes += len(computed["predictions"])
        kept += sum(p["retained"] for p in computed["predictions"])
        cross_pairs += len(computed["cross_class_overlaps"])
        cross_kept += sum(p["both_retained"] for p in computed["cross_class_overlaps"])
    any_risk = {name: sum(p["shadow"][name]["any_false_ready"] for p in panels) for name in ("all_four", "source_supported")}
    old_loco_c = sum(x["old"] == "C" for x in loco)
    preserved = sum(x["old"] == x["new"] == "C" for x in loco)
    rejected = sum(x["new"] == "U" for x in old_wrong)
    checks = {"all51_called_once": True, "all51_calls_completed": True, "zero_error_or_unattempted": True,
              "three_original_wrong_rejected": rejected == 3, "all14_loco_correct_preserved": preserved == old_loco_c == 14,
              "C_at_least_41": counts["C"] >= 41, "zero_W": counts["W"] == 0, "zero_all_four_AFR": any_risk["all_four"] == 0}
    expected = {"outcomes": {c: counts[c] for c in "CWUEN"}, "paired_transitions": dict(transitions),
                "strata": {s: {c: v[c] for c in "CWUEN"} for s, v in strata.items()}, "old_C_lost": len(lost),
                "original_W_rejected": rejected, "loco_old_C": old_loco_c, "loco_C_preserved": preserved,
                "changes": changes, "panels": panels, "any_false_ready_images": any_risk, "risk_denominator": 51,
                "unmeasured_risk": 0, "development_checks": checks, "development_gate_passed": all(checks.values())}
    for key, value in expected.items():
        compare(summary[key], value, f"analysis.{key}")
    return {"schema": "kitguard.v08.three-class-shadow-independent-audit.v1", "status": "passed",
            "created_at": datetime.now(UTC).isoformat(), "input_count": 51, "threshold": threshold,
            "base_outcomes": {c: old_counts[c] for c in "CWUEN"}, **expected,
            "old_C_lost_case_ids": lost, "original_wrong_case_details": old_wrong, "loco_case_transitions": loco,
            "raw_boxes": boxes, "retained_candidates": kept, "cross_class_pairs": cross_pairs,
            "cross_class_pairs_both_retained": cross_kept, "new_model_calls": 0,
            "production_changed": False, "candidate_promoted": False, "new_holdout": False,
            "scope": "Recomputed saved boxes/counts/fusion and risk; hashes prove records, not physical truth or model rerun",
            "hashes": {"auditor": sha(__file__), "freeze": sha(freeze_path), "run": sha(run_dir / "run.json"),
                       "predictions": sha(run_dir / "predictions.jsonl"), "analysis": sha(run_dir / "analysis.json"),
                       "training_audit": sha(root / frozen["training"]["independent_training_audit"]["path"])}}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project-root", type=Path, required=True)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--freeze", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    require(not args.output.exists(), "Audit overwrite forbidden")
    result = audit(args.project_root.resolve(), args.run.resolve(), args.freeze.resolve())
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": result["status"], "outcomes": result["outcomes"],
                      "old_C_lost": result["old_C_lost"], "gate": result["development_gate_passed"]}))


if __name__ == "__main__":
    main()
