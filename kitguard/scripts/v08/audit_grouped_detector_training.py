"""Read-only, completed-run audit. Recomputes all nine thresholds; never invokes a model.

No trainer imports. Optional checkpoint inspection uses CPU torch.load(weights_only=True)
only after all twelve epochs complete; it does not instantiate an architecture or call forward.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

NAMES = {1: "bolt", 2: "nut", 3: "washer"}


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def check(value, message):
    if not value:
        raise ValueError(message)


def same(actual, expected, path="root"):
    if isinstance(expected, dict):
        check(isinstance(actual, dict) and actual.keys() == expected.keys(), f"Keys differ: {path}")
        for key in expected:
            same(actual[key], expected[key], f"{path}.{key}")
    elif isinstance(expected, list):
        check(isinstance(actual, list) and len(actual) == len(expected), f"List differs: {path}")
        for index, value in enumerate(expected):
            same(actual[index], value, f"{path}[{index}]")
    elif isinstance(expected, float):
        check(type(actual) in (float, int) and math.isfinite(actual)
              and math.isclose(actual, expected, abs_tol=1e-12, rel_tol=1e-12), f"Number differs: {path}")
    else:
        check(type(actual) is type(expected) and actual == expected, f"Value differs: {path}: {actual!r} vs {expected!r}")


def overlap(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    return intersection / union


def case_metric(record, raw, threshold):
    gt, predictions = record["ground_truth"], raw["predictions"]
    selected = []
    for pi, item in enumerate(predictions):
        box = item["box"]
        check(type(item["label"]) is int and item["label"] in NAMES, "Unknown detector label")
        check(math.isfinite(item["score"]) and 0 <= item["score"] <= 1, "Invalid detector score")
        check(len(box) == 4 and all(math.isfinite(x) for x in box), "Invalid detector box")
        check(0 <= box[0] < box[2] <= record["image_size"][0]
              and 0 <= box[1] < box[3] <= record["image_size"][1], "Invalid box dimensions")
        if item["score"] >= threshold:
            selected.append(pi)
    claimed, matches, false = set(), [], []
    for pi in sorted(selected, key=lambda i: (-predictions[i]["score"], i)):
        candidate = None
        best = -1.0
        for gi, truth in enumerate(gt):
            if gi in claimed or truth["label"] != predictions[pi]["label"]:
                continue
            score = overlap(truth["box"], predictions[pi]["box"])
            if score > best:
                candidate, best = gi, score
        if candidate is not None and best >= .5:
            claimed.add(candidate)
            matches.append({"prediction_index": pi, "ground_truth_index": candidate, "iou": best})
        else:
            false.append(pi)
    missed = [i for i in range(len(gt)) if i not in claimed]
    truth_count = {name: sum(g["label"] == label for g in gt) for label, name in NAMES.items()}
    pred_count = {name: sum(predictions[i]["label"] == label for i in selected) for label, name in NAMES.items()}
    errors = {name: pred_count[name] - truth_count[name] for name in NAMES.values()}
    by_class = {name: {"tp": sum(gt[m["ground_truth_index"]]["label"] == label for m in matches),
                       "fp": sum(predictions[i]["label"] == label for i in false),
                       "fn": sum(gt[i]["label"] == label for i in missed), "count_error": errors[name],
                       "absolute_count_error": abs(errors[name])} for label, name in NAMES.items()}
    return {"id": record["id"], "source": record["source"], "group_id": record["group_id"],
            "truth_count": truth_count, "predicted_count": pred_count, "count_error": errors,
            "exact_count": all(e == 0 for e in errors.values()),
            "count_mae": sum(abs(e) for e in errors.values()) / 3,
            "selected_prediction_indices": selected, "matches": matches,
            "false_positive_indices": false, "missed_ground_truth_indices": missed, "per_class": by_class}


def group_metric(rows):
    check(bool(rows), "Empty metric denominator")
    classes = {}
    for name in NAMES.values():
        classes[name] = {k: sum(r["per_class"][name][k] for r in rows) for k in ("tp", "fp", "fn")}
        classes[name]["count_mae"] = sum(abs(r["count_error"][name]) for r in rows) / len(rows)
        classes[name]["signed_count_error"] = sum(r["count_error"][name] for r in rows)
    tp, fp, fn = (sum(c[k] for c in classes.values()) for k in ("tp", "fp", "fn"))
    exact = sum(r["exact_count"] for r in rows)
    return {"n": len(rows), "exact_count_n": exact, "exact_count_accuracy": exact / len(rows),
            "count_mae": sum(r["count_mae"] for r in rows) / len(rows), "per_class": classes,
            "tp": tp, "fp": fp, "fn": fn, "box_f1": 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else 0.0}


def recompute(records, predictions, threshold):
    check(len(records) == len(predictions), "Validation denominator mismatch")
    cases = []
    for record, raw in zip(records, predictions):
        check(raw["status"] == "ok" and raw["id"] == record["id"], "Failed or reordered validation")
        same(raw["ground_truth"], record["ground_truth"], "raw truth")
        check(raw["image_sha256"] == record["source_sha256"], "Raw input hash binding mismatch")
        cases.append(case_metric(record, raw, threshold))
    sc = group_metric([c for c in cases if c["source"] == "screws"])
    fo = [c for c in cases if c["source"] == "foda"]
    groups = {name: group_metric([c for c in fo if c["group_id"] == name]) for name in sorted({c["group_id"] for c in fo})}
    acc = sum(g["exact_count_accuracy"] for g in groups.values()) / len(groups)
    mae = sum(g["count_mae"] for g in groups.values()) / len(groups)
    return {"threshold": threshold, "balanced_exact_count_accuracy": (sc["exact_count_accuracy"] + acc) / 2,
            "balanced_class_count_mae": (sc["count_mae"] + mae) / 2, "pooled": group_metric(cases),
            "screws": sc, "foda": group_metric(fo), "foda_groups": groups,
            "foda_group_macro_exact_count_accuracy": acc, "foda_group_macro_count_mae": mae,
            "cases": cases, "annotation_scope": "author_annotated_target_only", "unsupported_classes": ["bracket"]}


def ranking(metrics):
    return (metrics["balanced_exact_count_accuracy"], -metrics["balanced_class_count_mae"], metrics["pooled"]["box_f1"])


def reconstruct_sources(preflight):
    """Independently bind derived preflight GT to the two original allowed JSON sources."""
    root = Path(preflight["project_root"])
    screws = root / "datasets/derived/public_detector_v1"
    excluded = {x["original_filename"] for x in read(screws / "manifest.json")["excluded_originals"]}
    check(len(excluded) == 104, "Screws 104 exclusions changed")
    for split, key, denominator in (("train", "training", 214), ("val", "validation", 44)):
        source = read(screws / f"{split}.json")
        rows = {r["id"]: r for r in preflight[key] if r["source"] == "screws"}
        check(len(rows) == denominator == len(source["images"]), "Screws source denominator")
        annotations = defaultdict(list)
        for ann in source["annotations"]:
            x, y, w, h = ann["bbox"]
            annotations[ann["image_id"]].append({"label": ann["category_id"], "box": [x, y, x + w, y + h],
                                               "annotation_id": ann["id"]})
        for image in source["images"]:
            check(image["original_filename"] not in excluded, "Excluded Screws source present")
            row = rows[f"screws:{image['id']}"]
            same(row["ground_truth"], annotations[image["id"]], "Screws GT")
            check(row["file_name"] == image["file_name"] and row["source_sha256"] == image["source_sha256"],
                  "Screws source identity mismatch")
    foda = Path(preflight["foda_path"])
    protocol = read(foda / "protocol.json")
    for split, key, denominator in (("train", "training", 400), ("validation", "validation", 36)):
        rows = {r["id"]: r for r in preflight[key] if r["source"] == "foda"}
        source = read(foda / f"{split}.json")
        check(len(rows) == len(source) == denominator, "FOD denominator")
        for original in source:
            row = rows[f"foda:{original['image_id']}"]
            same(row["ground_truth"], [{"label": original["class_id"], "box": original["box_xyxy"],
                                       "annotation_id": original["annotation_member_path"]}], "FOD GT")
            check(row["source_sha256"] == original["image_sha256"] and row["file_name"] == original["local_image"],
                  "FOD source identity mismatch")
            check(row["group_id"] == original["group_id"] and protocol["group_roles"][row["group_id"]] == split,
                  "FOD source role mismatch")


def checkpoint_metadata(path, protocol, selected, best):
    import torch
    state = torch.load(path, map_location="cpu", weights_only=True)
    normalize = lambda x: json.loads(json.dumps(x))
    check(state["schema"] == "kitguard.v08.grouped-detector-checkpoint.v1", "Checkpoint schema mismatch")
    same(normalize(state["config"]), protocol, "checkpoint config")
    same(normalize(state["selected"]), selected, "checkpoint selected")
    same(normalize(state["best"]), best, "checkpoint best history")
    check(state["model"]["roi_heads.box_predictor.cls_score.weight"].shape[0] == 4, "Head not four outputs")
    check(state["model"]["roi_heads.box_predictor.bbox_pred.weight"].shape[0] == 16, "Box head output mismatch")
    check(all(k in state for k in ("optimizer", "scheduler", "torch_rng", "python_rng", "loader_rng", "mps_rng")),
          "Checkpoint resumable state incomplete")
    return {"epoch": state["epoch"], "protocol_sha256": state["protocol_sha256"],
            "threshold": state["selected"]["threshold"], "tensor_devices": sorted({str(x.device) for x in state["model"].values()}),
            "head_outputs": 4, "model_forward_calls": 0}


def audit(run_dir, inspect_checkpoints=False):
    state, protocol, pre = (read(run_dir / name) for name in ("run.json", "protocol.json", "preflight.json"))
    check(state["status"] == "completed" and state["epochs_completed"] == 12, "Only complete twelve-epoch runs accepted")
    check(state["source_changed_during_run"] is False and state["held_back_read"] is False, "Source/read contract failed")
    check(protocol["epochs"] == 12 and protocol["thresholds"] == [x / 10 for x in range(1, 10)], "Protocol changed")
    check(protocol["classes"] == {"1": "bolt", "2": "nut", "3": "washer"}, "Class mapping changed")
    check(protocol["device"] == "mps" and protocol["precision"] == "float32", "Runtime protocol changed")
    for key, expected in {"seed": 20261002, "batch_size": 2, "min_size": 640, "max_size": 960,
                          "learning_rate": .005, "momentum": .9, "weight_decay": .0005,
                          "lr_step_epoch": 8, "lr_gamma": .1, "warmup_steps": 100,
                          "gradient_clip_norm": 10.0, "threads": 6}.items():
        same(protocol[key], expected, f"fixed protocol {key}")
    check(len(pre["training"]) == 614 and len(pre["validation"]) == 80, "Training/validation denominators")
    check(Counter(r["source"] for r in pre["validation"]) == {"screws": 44, "foda": 36}, "Validation source counts")
    check(sha(run_dir / "protocol.json") == state["protocol_sha256"], "Protocol hash mismatch")
    check(sha(run_dir / "preflight.json") == protocol["preflight_sha256"], "Preflight hash mismatch")
    same(protocol["bindings"], pre["bindings"], "preflight bindings")
    for category in ("bindings", "runtime_sha256"):
        for path, digest in protocol[category].items():
            check(not any(x == "held_back" or x.startswith("held_back.") for x in Path(path).parts),
                  "Held-back file unexpectedly in bindings")
            check(sha(path) == digest, f"File changed: {path}")
    for snapshot in (run_dir / "source").iterdir():
        check(any(Path(path).name == snapshot.name and digest == sha(snapshot)
                  for path, digest in protocol["bindings"].items()), f"Source snapshot mismatch {snapshot}")
    for snapshot in (run_dir / "data_bindings").rglob("*.json"):
        original = Path(pre["project_root"]) / snapshot.relative_to(run_dir / "data_bindings")
        check(sha(snapshot) == protocol["bindings"][str(original)], "Metadata snapshot mismatch")
    reconstruct_sources(pre)
    history = [json.loads(line) for line in (run_dir / "history.jsonl").read_text().splitlines()]
    check(len(history) == 12 and [h["epoch"] for h in history] == list(range(1, 13)), "History incomplete/reordered")
    best, epochs = None, []
    selected_all = {}
    for epoch in range(1, 13):
        directory = run_dir / "epochs" / f"epoch-{epoch:02d}"
        raw = read(directory / "validation_predictions.json")
        stream = [json.loads(line) for line in (directory / "validation_predictions.jsonl").read_text().splitlines()]
        same(stream, raw, "append-only validation stream")
        losses = [json.loads(line) for line in (directory / "losses.jsonl").read_text().splitlines()]
        check(len(losses) == 307 and [l["step"] for l in losses] == list(range(1, 308)), "Training step log incomplete")
        check(all(math.isfinite(l["loss"]) and math.isfinite(l["gradient_norm"]) for l in losses), "Nonfinite training")
        for loss in losses:
            iteration = (epoch - 1) * 307 + loss["step"]
            expected_lr = .005 * (.01 + .99 * iteration / 100) if iteration <= 100 else .005 * (.1 if epoch >= 9 else 1)
            same(loss["learning_rate"], expected_lr, "fixed learning rate schedule")
            check(all(math.isfinite(v) for v in loss["components"].values()), "Nonfinite loss component")
        sweep = [recompute(pre["validation"], raw, x / 10) for x in range(1, 10)]
        same(read(directory / "threshold_sweep.json"), sweep, f"epoch {epoch} all thresholds")
        selected = max(sweep, key=lambda m: (*ranking(m), m["threshold"]))
        selected_all[epoch] = selected
        same(read(directory / "selected.json"), selected, f"epoch {epoch} selection")
        improved = best is None or ranking(selected) > tuple(best["rank"])
        if improved:
            best = {"epoch": epoch, "threshold": selected["threshold"], "rank": list(ranking(selected))}
        item = history[epoch - 1]
        same(item["loss_mean"], sum(l["loss"] for l in losses) / len(losses), "history mean loss")
        same(item["rank"], list(ranking(selected)), "history rank")
        check(item["threshold"] == selected["threshold"] and item["improved"] == improved, "History selection mismatch")
        check(item["validation_predictions_sha256"] == sha(directory / "validation_predictions.json"), "Raw history hash")
        check(item["threshold_sweep_sha256"] == sha(directory / "threshold_sweep.json"), "Sweep history hash")
        epochs.append({"epoch": epoch, "threshold": selected["threshold"], "rank": list(ranking(selected)),
                       "screws_exact": selected["screws"]["exact_count_n"], "foda_exact": selected["foda"]["exact_count_n"],
                       "foda_groups": {g: {"n": v["n"], "exact": v["exact_count_n"]} for g, v in selected["foda_groups"].items()},
                       "pooled_per_class": selected["pooled"]["per_class"], "improved": improved})
    same(state["best"], best, "run best")
    best_metric = selected_all[best["epoch"]]
    same(read(run_dir / "best_validation_metrics.json"), best_metric, "saved best metrics")
    same(read(run_dir / "best_validation_predictions.json"),
         read(run_dir / "epochs" / f"epoch-{best['epoch']:02d}" / "validation_predictions.json"), "saved best raw")
    check(sha(run_dir / "best.pt") == state["best_checkpoint_sha256"]
          == history[best["epoch"] - 1]["last_checkpoint_sha256"], "Best checkpoint history hash")
    check(sha(run_dir / "last.pt") == state["last_checkpoint_sha256"] == history[-1]["last_checkpoint_sha256"],
          "Last checkpoint history hash")
    checkpoints = {}
    if inspect_checkpoints:
        for name, epoch in (("best", best["epoch"]), ("last", 12)):
            checkpoints[name] = checkpoint_metadata(run_dir / f"{name}.pt", protocol, selected_all[epoch], best)
            check(checkpoints[name]["epoch"] == epoch and checkpoints[name]["protocol_sha256"] == state["protocol_sha256"],
                  "Checkpoint epoch/protocol mismatch")
    return {"schema": "kitguard.v08.grouped-detector-independent-audit.v1", "status": "passed",
            "created_at": datetime.now(UTC).isoformat(), "run_dir": str(run_dir.resolve()), "best": best,
            "epochs": epochs, "training_examples_per_epoch": 614, "validation_examples_per_epoch": 80,
            "validation_observations": 960, "threshold_case_evaluations": 8640,
            "all_validation_errors": 0, "bindings_verified": len(protocol["bindings"]),
            "runtime_bindings_verified": len(protocol["runtime_sha256"]), "held_back_files_read": False,
            "model_forward_calls": 0, "checkpoint_metadata": checkpoints,
            "checkpoint_metadata_inspected": inspect_checkpoints,
            "annotation_scope": "author_annotated_target_only", "production_promotion": False,
            "source_hashes": {"auditor": sha(__file__), "run": sha(run_dir / "run.json"),
                              "protocol": sha(run_dir / "protocol.json"), "history": sha(run_dir / "history.jsonl"),
                              "best_checkpoint": sha(run_dir / "best.pt"), "last_checkpoint": sha(run_dir / "last.pt")}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--inspect-checkpoints", action="store_true")
    args = parser.parse_args()
    check(not args.output.exists(), "Do not overwrite an earlier audit")
    result = audit(args.run, args.inspect_checkpoints)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": result["status"], "best": result["best"], "output": str(args.output)}))


if __name__ == "__main__":
    main()
