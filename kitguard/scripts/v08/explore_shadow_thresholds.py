#!/usr/bin/env python3
"""Post-hoc saved-box threshold exploration; stdlib only, no inference."""

from __future__ import annotations

import copy
import hashlib
import importlib.abc
import importlib.util
import json
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "docs/v0.8/THREE_CLASS_THRESHOLD_EXPLORATION_PLAN.json"
THRESHOLDS = [0.5, 0.7, 0.9, 0.95, 0.99, 0.995, 0.999]
FORBIDDEN = {"torch", "torchvision", "mlx", "mlx_vlm", "PIL"}


class NoModelOrImageImport(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in FORBIDDEN:
            raise RuntimeError(f"Forbidden in saved-JSON exploration: {fullname}")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def need(condition, message):
    if not condition:
        raise ValueError(message)


def at_threshold(validated_detector, threshold):
    """Change only retained score flags/counts; preserve class and raw index."""
    need(type(threshold) is float and threshold in THRESHOLDS, "Unplanned threshold")
    result = copy.deepcopy(validated_detector)
    result["threshold"] = threshold
    result["counts"] = dict.fromkeys(("bolt", "nut", "washer"), 0)
    for prediction in result["predictions"]:
        prediction["retained"] = prediction["score"] >= threshold
        result["counts"][prediction["class_name"]] += int(prediction["retained"])
    for pair in result["cross_class_overlaps"]:
        pair["both_retained"] = all(result["predictions"][i]["retained"] for i in pair["indices"])
    return result


def main():
    tick = time.perf_counter()
    need(not any(n.split(".")[0] in FORBIDDEN for n in sys.modules), "Model/image module already loaded")
    sys.meta_path.insert(0, NoModelOrImageImport())
    plan = read(PLAN)
    need(plan["thresholds"] == THRESHOLDS, "Plan thresholds differ")
    plan_sha = sha(PLAN)
    output = ROOT / plan["output"]
    need(not output.parent.exists(), "Preserve existing exploration output")
    bindings = {r["path"]: r["sha256"] for r in plan["inputs"]}
    for relative, digest in bindings.items():
        need(sha(ROOT / relative) == digest, f"Planned evidence changed: {relative}")
    base = ROOT / "evaluation-runs/v0.8/three_class_shadow_v1"
    run, frozen, original = [read(base / f) for f in ("run.json", "freeze.json", "analysis.json")]
    records = [json.loads(line) for line in (base / "predictions.jsonl").read_text().splitlines()]
    need(run["status"] == "completed" and run["source_changed"] is False, "Original run incomplete or changed")
    need(run["freeze_sha256"] == sha(base / "freeze.json"), "Original freeze binding differs")
    need(run["predictions_sha256"] == sha(base / "predictions.jsonl"), "Prediction binding differs")
    need(run["analysis_sha256"] == sha(base / "analysis.json"), "Analysis binding differs")
    need(len(records) == len(frozen["cases"]) == 51, "Full51 required")
    need(len({r["case_id"] for r in records}) == 51, "Repeated case")
    need(sum(len(r["raw_detector_output"]["boxes"]) for r in records) == 643, "Expected saved643 boxes")
    source = ROOT / "docs/v0.8/three_class_shadow_freeze_v1/source_snapshot/probe_three_class_shadow.py"
    spec = importlib.util.spec_from_file_location("frozen_shadow_cpu_scoring", source)
    scoring = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scoring)
    validated, baseline_outcomes = [], Counter()
    for item, record in zip(frozen["cases"], records, strict=True):
        case = item["case"]
        need(case["id"] == record["case_id"], "Case order differs")
        need(item["base_observation"] == record["base_observation"] and item["binding"] == record["binding"], "G/input binding differs")
        need(record["status"] == "ok" and record["error"] is None
             and record["detector_call_started"] and record["detector_call_completed"], "Original case incomplete")
        detector = scoring.summarize(record["raw_detector_output"], .5, item["binding"]["actual_input_size"])
        need(detector == record["detector"], "0.5 detector recomputation differs")
        effective, triggers = scoring.fuse(item["base_observation"], detector)
        need(effective == record["effective_observation"] and triggers == record["triggers"], "0.5 per-case fusion differs")
        validated.append(detector)
        baseline_outcomes[scoring.outcome(item["base_observation"], case["ground_truth"])] += 1
    need(dict(baseline_outcomes) == {"C": 41, "U": 7, "W": 3}, "Expected original G41/3/7")
    summaries = []
    for threshold in THRESHOLDS:
        outcomes, transitions, strata = Counter(), Counter(), {}
        lost, loco_kept, original_w, details = [], [], [], []
        afr = dict.fromkeys(("all_four", "source_supported"), 0)
        for item, detector in zip(frozen["cases"], validated, strict=True):
            case, base_observation = item["case"], item["base_observation"]
            filtered = at_threshold(detector, threshold)
            effective, triggers = scoring.fuse(base_observation, filtered)
            old = scoring.outcome(base_observation, case["ground_truth"])
            new = scoring.outcome(effective, case["ground_truth"])
            need(not (old in {"W", "U"} and new == "C"), "Veto cannot correct counts")
            outcomes[new] += 1
            transitions[f"{old}->{new}"] += 1
            strata.setdefault(case["subgroup"], Counter())[new] += 1
            if old == "C" and new != "C":
                lost.append(case["id"])
            if old == new == "C" and case["subgroup"] == "loco_normal_222":
                loco_kept.append(case["id"])
            if old == "W":
                original_w.append({"case_id": case["id"], "new": new})
            panels = scoring.panel(case, effective)
            for name in afr:
                afr[name] += panels[name]["any_false_ready"]
            details.append({"case_id": case["id"], "old": old, "new": new,
                            "detector_counts": filtered["counts"], "triggers": triggers,
                            "effective_counts": effective["observed"],
                            "any_false_ready": {n: panels[n]["any_false_ready"] for n in afr}})
        summary = {"threshold": threshold, "outcomes": {k: outcomes[k] for k in "CWUEN"},
                   "paired_transitions": dict(transitions), "old_C_lost": len(lost),
                   "old_C_denominator": 41, "old_C_lost_case_ids": lost,
                   "original_W_destinations": original_w,
                   "original_W_rejected": sum(x["new"] == "U" for x in original_w),
                   "loco_C_preserved": len(loco_kept), "loco_old_C": 14,
                   "loco_C_preserved_case_ids": loco_kept, "any_false_ready_images": afr,
                   "risk_denominator": 51, "unmeasured_risk": outcomes["E"] + outcomes["N"],
                   "strata": {s: {k: c[k] for k in "CWUEN"} for s, c in strata.items()}, "cases": details}
        if threshold == .5:
            for key in ("outcomes", "paired_transitions", "old_C_lost", "original_W_rejected",
                        "loco_C_preserved", "loco_old_C", "any_false_ready_images", "strata"):
                need(summary[key] == original[key], f"0.5 aggregate differs: {key}")
        summaries.append(summary)
    for relative, digest in bindings.items():
        need(sha(ROOT / relative) == digest, "Original evidence changed during exploration")
    need(sha(PLAN) == plan_sha, "Plan changed during exploration")
    forbidden_loaded = sorted(n for n in sys.modules if n.split(".")[0] in FORBIDDEN)
    need(not forbidden_loaded, "Forbidden module loaded")
    result = {"schema": "kitguard.v08.three-class-shadow.threshold-exploration.analysis.v1",
              "status": "completed_post_hoc_exploratory", "created_at_utc": datetime.now(UTC).isoformat(),
              "plan_sha256": plan_sha, "script_sha256": sha(Path(__file__)), "inputs": plan["inputs"],
              "planned_photos": 51, "saved_boxes": 643, "new_model_calls": 0,
              "images_read_or_decoded": 0, "forbidden_modules_loaded": forbidden_loaded,
              "zero_point_five_per_case_and_aggregate_reproduced": True,
              "original_G_outcomes": {k: baseline_outcomes[k] for k in "CWUEN"},
              "threshold_results": summaries, "new_holdout": False, "automatic_promotion": False,
              "new_official_threshold_selected": None, "original_zero_point_five_decision_changed": False,
              "limitations": ["Post-hoc thresholds chosen after reviewing exposed development failures; multiple-comparison/selection bias.",
                              "Results reuse post-floor/NMS returned boxes, not new inference or full network logits.",
                              "Scores are detector outputs, not calibrated truth probabilities.",
                              "CPU JSON recomputation time is not detector or end-to-end inference latency."],
              "cpu_json_recomputation_seconds": time.perf_counter() - tick}
    output.parent.mkdir(parents=True)
    with output.open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        stream.write("\n")
    print("threshold C/W/U/E/N lost41 W_to_U/3 LOCO_kept/14 AFR_all4/source")
    for summary in summaries:
        print(summary["threshold"], "/".join(str(summary["outcomes"][k]) for k in "CWUEN"),
              summary["old_C_lost"], summary["original_W_rejected"], summary["loco_C_preserved"],
              "/".join(str(summary["any_false_ready_images"][k]) for k in ("all_four", "source_supported")))
    print(f"saved {output.relative_to(ROOT)} SHA256 {sha(output)}")


if __name__ == "__main__":
    main()
