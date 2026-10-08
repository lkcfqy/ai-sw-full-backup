"""Independent completed-run grayscale audit: no runner, trainer, Torch or model imports."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
import traceback
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRAINING = ROOT / "training-runs/v0.8/grouped_detector_v1"
HELPER = ROOT / "scripts/v08/audit_grouped_detector_training.py"
HELPER_SHA = "22bd2bf41070532aed4258beadc42ebc33320899dce78cc5e19a638f01f3453d"
TRAINING_AUDIT = ROOT / "test-results/v0.8-grouped-detector-independent-audit-v1.json"
TRAINING_AUDIT_SHA = "ebba458d862fde4fae9cc6be9236dffab76d709e25bd9c4779dab26da2a782fa"
PINS = {
    "best.pt": "2a70848fa26207fe8702e8d39e15794e8902212b8b439bfa536edf7d63a83613",
    "protocol.json": "0230682fac7d542cf6669a42a6ba274402747908795da874b80f1f33c54be24a",
    "preflight.json": "f3e31e0420ef5b18e731484d9e0da58f5f51ca3c0479d7cdc064917622e1b63e",
    "best_validation_predictions.json": "5db3384fe8ebb439f6e3b585e021eb7c61cdb06712ed3ac50c136b976f502f19",
    "best_validation_metrics.json": "772723fa948ae9b3a60744b42ee3b88554bddce12514284a7de470840adf49d6",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def independent_metrics():
    require(sha(HELPER) == HELPER_SHA, "Independent metric helper changed")
    spec = importlib.util.spec_from_file_location("independent_grouped_metrics", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def geometry_confusion(record, predictions, metrics):
    available = set(range(len(record["ground_truth"])))
    matches = []
    eligible = sorted((i for i, p in enumerate(predictions) if p["score"] >= .5),
                      key=lambda i: (-predictions[i]["score"], i))
    for pi in eligible:
        candidates = [(metrics.overlap(predictions[pi]["box"], record["ground_truth"][gi]["box"]), gi)
                      for gi in sorted(available)]
        if not candidates:
            continue
        overlap, gi = max(candidates, key=lambda pair: (pair[0], -pair[1]))
        if overlap >= .5:
            available.remove(gi)
            matches.append({"prediction_index": pi, "ground_truth_index": gi, "iou": overlap,
                            "truth_label": record["ground_truth"][gi]["label"],
                            "predicted_label": predictions[pi]["label"]})
    return {"matches": matches, "missed_ground_truth_indices": sorted(available),
            "nut_to_washer": sum(x["truth_label"] == 2 and x["predicted_label"] == 3 for x in matches)}


def recompute(records, baseline, rows, metrics):
    require(len(records) == len(baseline) == len(rows), "Full denominator mismatch")
    details = []
    for record, rgb, gray in zip(records, baseline, rows, strict=True):
        require(record["id"] == rgb["id"] == gray["id"], "Case order differs")
        require(gray["source_sha256"] == record["source_sha256"], "Case source differs")
        require(gray["status"] in {"ok", "failed", "not_attempted"}, "Unknown status")
        original = metrics.case_metric(record, rgb, .5)
        current = metrics.case_metric(record, gray, .5) if gray["status"] == "ok" else None
        details.append({"id": record["id"], "source": record["source"], "group_id": record["group_id"],
                        "status": gray["status"], "rgb_metrics": original, "gray_metrics": current,
                        "rgb_geometry_confusion": geometry_confusion(record, rgb["predictions"], metrics),
                        "gray_geometry_confusion": geometry_confusion(record, gray["predictions"], metrics)
                        if current is not None else None})

    def summary(indices):
        selected = [details[i] for i in indices]
        valid = [d for d in selected if d["gray_metrics"] is not None]
        correct = sum(d["gray_metrics"]["exact_count"] for d in valid)
        return {"planned": len(selected), "completed": len(valid),
                "failed": sum(d["status"] == "failed" for d in selected),
                "not_attempted": sum(d["status"] == "not_attempted" for d in selected),
                "rgb_historical_metrics": metrics.group_metric([d["rgb_metrics"] for d in selected]),
                "gray_measured_subset_metrics": metrics.group_metric([d["gray_metrics"] for d in valid])
                if valid else None, "gray_exact_count_n": correct,
                "gray_exact_count_fraction_of_planned": correct / len(selected),
                "full_denominator_metrics_available": len(valid) == len(selected),
                "rgb_nut_to_washer": sum(d["rgb_geometry_confusion"]["nut_to_washer"] for d in selected),
                "gray_measured_nut_to_washer": sum(d["gray_geometry_confusion"]["nut_to_washer"] for d in valid),
                "unmeasured_nut_gt": sum(sum(g["label"] == 2 for g in records[i]["ground_truth"])
                                         for i in indices if rows[i]["status"] != "ok"),
                "exact_to_inexact": [d["id"] for d in valid if d["rgb_metrics"]["exact_count"]
                                     and not d["gray_metrics"]["exact_count"]],
                "inexact_to_exact": [d["id"] for d in valid if not d["rgb_metrics"]["exact_count"]
                                     and d["gray_metrics"]["exact_count"]]}
    return {"all": summary(list(range(len(records)))),
            "sources": {s: summary([i for i, r in enumerate(records) if r["source"] == s])
                        for s in sorted({r["source"] for r in records})},
            "foda_groups": {g: summary([i for i, r in enumerate(records)
                                        if r["source"] == "foda" and r["group_id"] == g])
                            for g in sorted({r["group_id"] for r in records if r["source"] == "foda"})},
            "cases": details}


def validate_raw(record, row, metrics):
    require(row.get("model_call_started") is True and row.get("model_call_completed") is True,
            "Successful case missing completed model-call flags")
    raw = row["raw_detector_output"]
    require(set(raw) == {"boxes", "labels", "scores"}, "Unexpected raw detector keys")
    require(len(raw["boxes"]) == len(raw["labels"]) == len(raw["scores"]) <= 100,
            "Raw boxes/labels/scores lengths differ or exceed frozen maximum")
    reconstructed = [{"box": box, "label": label, "score": score} for box, label, score in
                     zip(raw["boxes"], raw["labels"], raw["scores"], strict=True)]
    require(row["predictions"] == reconstructed, "Stored predictions filter/change original returned boxes")
    metrics.case_metric(record, row, .5)
    return len(reconstructed)


def reconstruct_tensor(path, record, row):
    import numpy as np
    from PIL import Image
    with Image.open(path) as original:
        require(list(original.size) == record["image_size"], "Input dimensions changed")
        # Independent byte reconstruction: no torchvision/torch or runner transformation imports.
        rgb = original.convert("RGB")
        luminance = rgb.convert("L")
        gray = Image.merge("RGB", (luminance, luminance, luminance))
        gray_sha = hashlib.sha256(str(gray.size).encode() + b"|RGB|" + gray.tobytes()).hexdigest()
        plane = np.asarray(luminance, dtype=np.float32) / np.float32(255)
        tensor_bytes = np.stack((plane, plane, plane)).tobytes(order="C")
        tensor = {"shape": [3, gray.height, gray.width], "dtype": "float32", "byteorder": sys.byteorder,
                  "sha256": hashlib.sha256(tensor_bytes).hexdigest()}
        require(row["input_size"] == list(gray.size) and row["grayscale_rgb_sha256"] == gray_sha,
                "Grayscale input pixel fingerprint differs")
        require(row["tensor"] == tensor, "Reconstructed actual FP32 CHW tensor differs")
        return {"id": record["id"], "grayscale_rgb_sha256": gray_sha, "tensor": tensor}


def tree_hashes(directory):
    return {str(p.relative_to(directory)): sha(p) for p in sorted(directory.rglob("*")) if p.is_file()}


def audit(directory):
    directory = directory.resolve()
    state = read(directory / "run.json")
    require(state["status"] == "completed", "Only completed runs may be audited")
    before = tree_hashes(directory)
    plan = read(directory / "plan.json")
    rows = read(directory / "predictions.json")
    require(len(rows) == len(plan["records"]) == 80, "Complete80 required before reading scores")
    require(len({r["id"] for r in rows}) == 80, "Duplicate case IDs")
    require(sha(directory / "plan.json") == state["plan_sha256"], "Saved plan differs from run")
    require(state["integrity_passed"] is True and state["changed_bindings"] == [], "Run integrity failed")
    require(state["policy"] == plan["policy"], "Runtime policy differs")
    receipt = read(directory / "source_snapshot/source_receipt.json")
    require(receipt["schema"] == "kitguard.v08.grayscale-validation.source-snapshot.v1"
            and receipt["saved_before_model_import"] is True
            and receipt["plan_sha256"] == state["plan_sha256"], "Pre-model source snapshot receipt differs")
    required_sources = {"scripts/v08/probe_grayscale_validation.py",
                        "docs/v0.8/GRAYSCALE_VALIDATION_DIAGNOSTIC_PLAN.md"}
    require({str(Path(r["original_path"]).relative_to(ROOT)) for r in receipt["files"]} == required_sources
            and len(receipt["files"]) == 2, "Exact runner/plan snapshot set required")
    for item in receipt["files"]:
        relative = Path(item["original_path"]).relative_to(ROOT)
        require(item["snapshot_path"] == str(Path("source_snapshot") / relative), "Snapshot path differs")
        require(item["sha256"] == plan["bindings"][item["original_path"]]
                == sha(directory / item["snapshot_path"]), "Source snapshot bytes differ")
    policy = plan["policy"]
    for key, expected in {"planned": 80, "screws": 44, "foda": 36, "epoch": 7, "threshold": .5,
                          "iou": .5, "device": "mps", "precision": "float32", "min_size": 640,
                          "max_size": 960, "box_score_thresh": .05, "box_nms_thresh": .5,
                          "box_detections_per_img": 100, "retries": 0, "warmup": False,
                          "new_holdout": False, "automatic_promotion": False}.items():
        require(policy[key] == expected, f"Frozen policy differs: {key}")
    for name, expected in PINS.items():
        require(sha(TRAINING / name) == expected, f"Training evidence changed: {name}")
    require(sha(TRAINING_AUDIT) == TRAINING_AUDIT_SHA and read(TRAINING_AUDIT)["status"] == "passed",
            "Original checkpoint/selection audit differs")
    require(plan["records"] == read(TRAINING / "preflight.json")["validation"], "Validation80 plan edited")
    require(plan["baseline"] == read(TRAINING / "best_validation_predictions.json"), "RGB baseline edited")
    require(plan["training_protocol"] == read(TRAINING / "protocol.json"), "Training protocol edited")
    records = plan["records"]
    require(Counter(r["source"] for r in records) == {"screws": 44, "foda": 36}, "Source denominators")
    require(Counter(r["group_id"] for r in records if r["source"] == "foda")
            == {"GOPR0181": 12, "GOPR0183": 12, "unprefixed_Washer": 12}, "FOD group denominators")
    verified = {}
    for original, expected in plan["bindings"].items():
        path = Path(original)
        relative = path.relative_to(ROOT) if path.is_relative_to(ROOT) else None
        copy = directory / "source_snapshot" / relative if relative else None
        # Bound source snapshots take precedence over mutable current workspace source.
        target = copy if copy and copy.is_file() else path
        require(sha(target) == expected, f"Bound source/data/runtime differs: {original}")
        verified[original] = {"sha256": expected, "checked_path": str(target)}
    metrics = independent_metrics()
    metrics.same(metrics.recompute(records, plan["baseline"], .5),
                 read(TRAINING / "best_validation_metrics.json"), "independent RGB metrics")
    input_audits, raw_count = [], 0
    for record, row in zip(records, rows, strict=True):
        require(row["id"] == record["id"] and row["source_sha256"] == record["source_sha256"],
                "Source/order binding differs")
        path = ROOT / record["file_name"]
        require(not any("held_back" in p.lower() or "manta" in p.lower() or "mvtec_loco" in p.lower()
                        for p in path.parts), "Forbidden dataset read")
        require(sha(path) == record["source_sha256"], "Input source hash differs")
        if row["status"] == "ok":
            raw_count += validate_raw(record, row, metrics)
            input_audits.append(reconstruct_tensor(path, record, row))
        else:
            require(row["status"] in {"failed", "not_attempted"}, "Unknown terminal status")
            if row["status"] == "failed":
                require(bool(row.get("error")), "Failed case missing error")
            if "tensor" in row:
                input_audits.append(reconstruct_tensor(path, record, row))
        for key, value in row.items():
            if key.endswith("_seconds"):
                require(type(value) in (int, float) and math.isfinite(value) and value >= 0, "Bad timing")
    require(sum(r["status"] == "ok" for r in rows) == state["successful_cases"], "Success total differs")
    require(sum(r["model_call_started"] for r in rows) == state["model_calls_started"], "Started total differs")
    require(sum(r["model_call_completed"] for r in rows) == state["model_calls_completed"], "Completed total differs")
    actual = read(directory / "analysis.json")
    calculated = recompute(records, plan["baseline"], rows, metrics)
    for key, value in calculated.items():
        metrics.same(actual[key], value, f"independent gray analysis.{key}")
    require(actual["policy"] == policy and actual["new_holdout"] is False
            and actual["automatic_promotion"] is False and actual["integrity_passed"] is True,
            "Analysis scope/integrity flags differ")
    require(before == tree_hashes(directory), "Run artifacts changed during read-only audit")
    require(not any(n in sys.modules for n in ("torch", "torchvision", "mlx", "mlx_vlm", "kitguard")),
            "Model/production modules were unexpectedly imported")
    return {"schema": "kitguard.v08.grayscale-validation.independent-audit.v1", "status": "passed",
            "checked_at": datetime.now(UTC).isoformat(), "planned": 80,
            "model_imported_or_called": False, "new_model_calls": 0,
            "actual_inputs_reconstructed": len(input_audits), "raw_boxes_retained_and_validated": raw_count,
            "independent_results": calculated, "input_audits": input_audits,
            "bindings_verified": verified, "artifacts_sha256": before,
            "evidence_sha256": {"auditor": sha(__file__), "independent_metric_helper": HELPER_SHA,
                                "training_audit": TRAINING_AUDIT_SHA},
            "production_unchanged": True, "automatic_promotion": False,
            "limits": ["Saved-data consistency, not proof of the authenticity of original model returns.",
                       "Post-hoc exposed-validation input sensitivity, not training-color causality.",
                       "Historical RGB was not rerun concurrently; MPS is not bitwise deterministic.",
                       "Author-annotated targets only; no general mixed-BOM count validation."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "Never overwrite prior audit")
    require(not args.output.resolve().is_relative_to(args.run.resolve()), "Audit must be outside run")
    try:
        result = audit(args.run)
    except Exception as exc:  # noqa: BLE001 -- preserve first independent audit failure
        result = {"schema": "kitguard.v08.grayscale-validation.independent-audit.v1", "status": "failed",
                  "checked_at": datetime.now(UTC).isoformat(), "error": f"{type(exc).__name__}: {exc}",
                  "traceback": traceback.format_exc(), "auditor_sha256": sha(__file__)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({k: result[k] for k in ("status", "error", "actual_inputs_reconstructed",
                     "raw_boxes_retained_and_validated") if k in result}))
    raise SystemExit(0 if result["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
