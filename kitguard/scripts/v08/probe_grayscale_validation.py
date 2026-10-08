"""Prepare/run one fixed grayscale diagnostic over the exposed validation80.

Imports are stdlib-only until image preparation or the explicitly invoked run.
No training, threshold selection, production imports or new-source evaluation.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import platform
import shutil
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRAINING = "training-runs/v0.8/grouped_detector_v1"
PLAN_DOC = "docs/v0.8/GRAYSCALE_VALIDATION_DIAGNOSTIC_PLAN.md"
PINS = {
    "best.pt": "2a70848fa26207fe8702e8d39e15794e8902212b8b439bfa536edf7d63a83613",
    "protocol.json": "0230682fac7d542cf6669a42a6ba274402747908795da874b80f1f33c54be24a",
    "preflight.json": "f3e31e0420ef5b18e731484d9e0da58f5f51ca3c0479d7cdc064917622e1b63e",
    "best_validation_predictions.json": "5db3384fe8ebb439f6e3b585e021eb7c61cdb06712ed3ac50c136b976f502f19",
    "best_validation_metrics.json": "772723fa948ae9b3a60744b42ee3b88554bddce12514284a7de470840adf49d6",
    "source/train_grouped_detector.py": "61234d376fc885e4cba0c5e6ccb3bd18424aa84759eeab836f0cbeda71ef86ec",
}
POLICY = {"planned": 80, "screws": 44, "foda": 36, "device": "mps", "precision": "float32",
          "epoch": 7, "threshold": .5, "iou": .5, "retries": 0, "warmup": False, "threads": 6,
          "transform": "Pillow image.convert('RGB').convert('L').convert('RGB'); no resize, EXIF transpose, augmentation or saving",
          "tensor": "torchvision pil_to_tensor -> float32 / 255.0; model internal transform unchanged",
          "min_size": 640, "max_size": 960, "box_score_thresh": .05,
          "box_nms_thresh": .5, "box_detections_per_img": 100, "new_holdout": False,
          "automatic_promotion": False, "historical_rgb_only": True}


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def need(condition, message):
    if not condition:
        raise ValueError(message)


def local(root, relative):
    value = Path(relative)
    need(not value.is_absolute() and ".." not in value.parts, "Unsafe relative path")
    path = (root / value).resolve()
    need(path.is_relative_to(root.resolve()), "Path escapes project")
    need(not any("held_back" in p.lower() or "manta" in p.lower() or "mvtec_loco" in p.lower()
                 for p in path.parts), "Excluded dataset path")
    return path


def write(path, value, *, exclusive=False):
    path = Path(path)
    data = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if exclusive:
        with path.open("x") as stream:
            stream.write(data)
    else:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(data)
        temporary.replace(path)


def scoring_module(root):
    path = root / TRAINING / "source/train_grouped_detector.py"
    need(sha(path) == PINS["source/train_grouped_detector.py"], "Frozen trainer/scorer changed")
    spec = importlib.util.spec_from_file_location("grayscale_frozen_scoring", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def versions():
    return {"python": platform.python_version(), **{name: importlib.metadata.version(name)
            for name in ("torch", "torchvision", "Pillow")}}


def prepare(root):
    need(not any(name in sys.modules for name in ("torch", "mlx", "mlx_vlm")), "Preparation must run without a model runtime")
    bindings = {}
    for name, expected in PINS.items():
        path = root / TRAINING / name
        need(sha(path) == expected, f"Pinned training artifact changed: {name}")
        bindings[str(path)] = expected
    folder = root / TRAINING
    run, protocol, preflight = [read(folder / p) for p in ("run.json", "protocol.json", "preflight.json")]
    bindings[str(folder / "run.json")] = sha(folder / "run.json")
    need(run["status"] == "completed" and run["epochs_completed"] == 12
         and run["best"]["epoch"] == 7 and run["best"]["threshold"] == .5
         and run["best_checkpoint_sha256"] == PINS["best.pt"]
         and run["source_changed_during_run"] is False, "Wrong completed training/best checkpoint")
    need(run["protocol_sha256"] == PINS["protocol.json"]
         and protocol["preflight_sha256"] == PINS["preflight.json"], "Training lineage mismatch")
    records = preflight["validation"]
    need(len(records) == len({r["id"] for r in records}) == 80, "Expected complete unique validation80")
    need(Counter(r["source"] for r in records) == {"screws": 44, "foda": 36}, "Source denominator differs")
    need(Counter((r["group_id"], r["ground_truth"][0]["label"]) for r in records if r["source"] == "foda")
         == {("GOPR0181", 1): 12, ("GOPR0183", 2): 12, ("unprefixed_Washer", 3): 12}, "FOD groups differ")
    for record in records:
        need(record["role"] == "validation", "Only original validation records allowed")
        prefix = "datasets/raw/mvtec_screws_v1.0/images/" if record["source"] == "screws" else "datasets/derived/v0.8/foda_grouped_v1/images/validation/"
        need(record["file_name"].startswith(prefix), "Image not in the bound validation source")
        path = local(root, record["file_name"])
        need(sha(path) == record["source_sha256"], "Validation image changed")
        bindings[str(path)] = record["source_sha256"]
    baseline = read(folder / "best_validation_predictions.json")
    need(len(baseline) == 80 and [r["id"] for r in baseline] == [r["id"] for r in records], "RGB baseline order differs")
    for record, row in zip(records, baseline, strict=True):
        need(row["status"] == "ok" and row["image_sha256"] == record["source_sha256"]
             and row["ground_truth"] == record["ground_truth"], "Historical RGB baseline not source-bound")
    scorer = scoring_module(root)
    need(scorer.evaluate(records, baseline, .5) == read(folder / "best_validation_metrics.json"), "RGB metric replay differs")
    for path, expected in protocol["runtime_sha256"].items():
        need(sha(path) == expected, "Historical runtime implementation differs")
        bindings[path] = expected
    for package, relative in (("torchvision", "torchvision/transforms/functional.py"),
                              ("torchvision", "torchvision/transforms/_functional_pil.py"),
                              ("torchvision", "torchvision/transforms/_functional_tensor.py")):
        path = Path(importlib.metadata.distribution(package).locate_file(relative)).resolve()
        bindings[str(path)] = sha(path)
    for path in (Path(__file__).resolve(), root / PLAN_DOC):
        bindings[str(path)] = sha(path)
    need(versions() == {"python": protocol["python"], "torch": protocol["torch"],
                        "torchvision": protocol["torchvision"], "Pillow": protocol["pillow"]}, "Runtime versions differ")
    need(not any(name in sys.modules for name in ("torch", "mlx", "mlx_vlm")), "Preparation imported a model runtime")
    return {"schema": "kitguard.v08.grayscale-validation.plan.v1", "created_at": datetime.now(UTC).isoformat(),
            "project_root": str(root), "policy": POLICY, "bindings": bindings, "versions": versions(),
            "records": records, "baseline": baseline, "training_protocol": protocol,
            "model_called": False, "image_pixels_decoded": False, "evaluation_started": False, "forbidden_model_modules": []}


def grayscale(image):
    return image.convert("RGB").convert("L").convert("RGB")


def normalized_checkpoint_config(config):
    """Only the confirmed JSON object-key conversion: classes 1/2/3 -> strings."""
    need(isinstance(config, dict) and isinstance(config.get("classes"), dict), "Missing checkpoint class mapping")
    classes = config["classes"]
    need((all(type(k) is int for k in classes) and set(classes) == {1, 2, 3})
         or (all(type(k) is str for k in classes) and set(classes) == {"1", "2", "3"}),
         "Unexpected checkpoint class keys")
    normalized = {str(k): v for k, v in classes.items()}
    need(len(normalized) == 3 and set(normalized) == {"1", "2", "3"}, "Conflicting checkpoint class keys")
    return {**config, "classes": normalized}


def validate_checkpoint(checkpoint, protocol, metrics):
    need(checkpoint["schema"] == "kitguard.v08.grouped-detector-checkpoint.v1"
         and checkpoint["epoch"] == 7 and checkpoint["selected"]["threshold"] == .5
         and checkpoint["protocol_sha256"] == PINS["protocol.json"]
         and checkpoint["selected"] == metrics
         and normalized_checkpoint_config(checkpoint["config"]) == protocol,
         "Checkpoint identity/config mismatch")


def confusion(record, predictions, scorer):
    """Class-agnostic score-ordered 1:1 IoU matching; no many-to-one inflation."""
    used, matches = set(), []
    for pi in sorted((i for i, p in enumerate(predictions) if p["score"] >= .5), key=lambda i: (-predictions[i]["score"], i)):
        possibilities = sorted(((scorer.iou(predictions[pi]["box"], g["box"]), gi)
                                for gi, g in enumerate(record["ground_truth"]) if gi not in used), key=lambda x: (-x[0], x[1]))
        if possibilities and possibilities[0][0] >= .5:
            overlap, gi = possibilities[0]
            used.add(gi)
            matches.append({"prediction_index": pi, "ground_truth_index": gi, "iou": overlap,
                            "truth_label": record["ground_truth"][gi]["label"], "predicted_label": predictions[pi]["label"]})
    return {"matches": matches, "missed_ground_truth_indices": [i for i in range(len(record["ground_truth"])) if i not in used],
            "nut_to_washer": sum(m["truth_label"] == 2 and m["predicted_label"] == 3 for m in matches)}


def analyze(records, baseline, rows, scorer):
    need(len({r["id"] for r in rows}) == len(rows) and {r["id"] for r in rows} <= {r["id"] for r in records}, "Duplicate/unplanned row")
    by_id = {r["id"]: r for r in rows}
    details, rgb_scores, gray_scores = [], [], []
    for record, old in zip(records, baseline, strict=True):
        need(old["id"] == record["id"], "Baseline order mismatch")
        original = scorer.score_case(record, old["predictions"], .5)
        rgb_scores.append(original)
        current = by_id.get(record["id"])
        if current:
            need(current.get("source_sha256") == record["source_sha256"], "Gray result source identity differs")
        state = current.get("status") if current else "not_attempted"
        need(state in {"ok", "failed", "not_attempted"}, "Unknown attempt status")
        metrics = scorer.score_case(record, current["predictions"], .5) if state == "ok" else None
        if metrics:
            gray_scores.append(metrics)
        details.append({"id": record["id"], "source": record["source"], "group_id": record["group_id"],
                        "status": state, "rgb_metrics": original, "gray_metrics": metrics,
                        "rgb_geometry_confusion": confusion(record, old["predictions"], scorer),
                        "gray_geometry_confusion": confusion(record, current["predictions"], scorer) if metrics else None})

    def summary(ids):
        selected = [d for d in details if d["id"] in ids]
        valid = [d for d in selected if d["gray_metrics"] is not None]
        rgb = scorer.aggregate([d["rgb_metrics"] for d in selected])
        gray = scorer.aggregate([d["gray_metrics"] for d in valid]) if valid else None
        return {"planned": len(selected), "completed": len(valid),
                "failed": sum(d["status"] == "failed" for d in selected),
                "not_attempted": sum(d["status"] == "not_attempted" for d in selected),
                "rgb_historical_metrics": rgb, "gray_measured_subset_metrics": gray,
                "gray_exact_count_n": sum(d["gray_metrics"]["exact_count"] for d in valid),
                "gray_exact_count_fraction_of_planned": sum(d["gray_metrics"]["exact_count"] for d in valid) / len(selected),
                "full_denominator_metrics_available": len(valid) == len(selected),
                "rgb_nut_to_washer": sum(d["rgb_geometry_confusion"]["nut_to_washer"] for d in selected),
                "gray_measured_nut_to_washer": sum(d["gray_geometry_confusion"]["nut_to_washer"] for d in valid),
                "unmeasured_nut_gt": sum(sum(g["label"] == 2 for g in r["ground_truth"]) for r in records
                                          if r["id"] in ids and by_id.get(r["id"], {}).get("status") != "ok"),
                "exact_to_inexact": [d["id"] for d in valid if d["rgb_metrics"]["exact_count"] and not d["gray_metrics"]["exact_count"]],
                "inexact_to_exact": [d["id"] for d in valid if not d["rgb_metrics"]["exact_count"] and d["gray_metrics"]["exact_count"]]}
    groups = {source: summary({r["id"] for r in records if r["source"] == source}) for source in {r["source"] for r in records}}
    fod_groups = {g: summary({r["id"] for r in records if r["source"] == "foda" and r["group_id"] == g})
                  for g in sorted({r["group_id"] for r in records if r["source"] == "foda"})}
    return {"schema": "kitguard.v08.grayscale-validation.analysis.v1", "policy": POLICY,
            "all": summary({r["id"] for r in records}), "sources": groups, "foda_groups": fod_groups,
            "cases": details, "new_holdout": False, "automatic_promotion": False,
            "limits": "Post-hoc input intervention on exposed validation; historical RGB baseline, non-bitwise-deterministic MPS. Not training causality or speed comparison."}


def build_model():
    import torch
    from torchvision.models.detection import fasterrcnn_mobilenet_v3_large_320_fpn
    from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
    from torchvision.ops.misc import FrozenBatchNorm2d
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


def verify(plan):
    need(plan["schema"] == "kitguard.v08.grayscale-validation.plan.v1" and plan["policy"] == POLICY, "Plan policy differs")
    need(versions() == plan["versions"], "Versions changed")
    need(len(plan["records"]) == 80, "Planned80 required")
    need(str(Path(__file__).resolve()) in plan["bindings"], "Runner not bound")
    root = Path(plan["project_root"])
    folder = root / TRAINING
    for name, expected in PINS.items():
        need(plan["bindings"].get(str(folder / name)) == expected and sha(folder / name) == expected,
             "Required fixed artifact identity missing/changed")
    need(plan["records"] == read(folder / "preflight.json")["validation"]
         and plan["baseline"] == read(folder / "best_validation_predictions.json")
         and plan["training_protocol"] == read(folder / "protocol.json"), "Plan records/baseline/protocol were edited")
    for record in plan["records"]:
        need(plan["bindings"].get(str(local(root, record["file_name"]))) == record["source_sha256"], "Unbound validation image")
    for path, expected in plan["training_protocol"]["runtime_sha256"].items():
        need(plan["bindings"].get(path) == expected, "Missing historical runtime binding")
    for path, digest in plan["bindings"].items():
        need(sha(path) == digest, f"Bound input/source/runtime changed: {path}")


def run(plan_path, output):
    plan = read(plan_path)
    verify(plan)
    root = Path(plan["project_root"])
    need(not output.exists(), "Output exists; no resume/retry/overwrite")
    output.mkdir(parents=True)
    write(output / "plan.json", plan, exclusive=True)
    snapshot = output / "source_snapshot"
    source_copies = []
    for source, relative in ((Path(__file__).resolve(), "scripts/v08/probe_grayscale_validation.py"),
                             (root / PLAN_DOC, PLAN_DOC)):
        target = snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        need(sha(target) == plan["bindings"][str(source)], "Pre-run source snapshot differs from plan")
        source_copies.append({"original_path": str(source), "sha256": sha(target),
                              "snapshot_path": str(target.relative_to(output))})
    write(snapshot / "source_receipt.json", {"schema": "kitguard.v08.grayscale-validation.source-snapshot.v1",
          "saved_before_model_import": True, "plan_sha256": sha(plan_path), "files": source_copies}, exclusive=True)
    state = {"schema": "kitguard.v08.grayscale-validation.run.v1", "status": "running", "started_at": datetime.now(UTC).isoformat(),
             "plan_sha256": sha(plan_path), "model_load_seconds": None, "setup_error": None, "policy": POLICY}
    rows = [{"id": r["id"], "source_sha256": r["source_sha256"], "status": "not_attempted",
             "model_call_started": False, "model_call_completed": False} for r in plan["records"]]
    write(output / "run.json", state)
    write(output / "predictions.json", rows)
    scorer = scoring_module(root)
    completed_loop = False
    try:
        setup_error = None
        try:
            import torch
            from PIL import Image
            from torchvision.transforms.functional import pil_to_tensor
            need(torch.backends.mps.is_available(), "Fixed MPS device unavailable; no CPU fallback")
            torch.set_num_threads(6)
            started = time.perf_counter()
            checkpoint = torch.load(root / TRAINING / "best.pt", map_location="cpu", weights_only=True)
            validate_checkpoint(checkpoint, plan["training_protocol"], read(root / TRAINING / "best_validation_metrics.json"))
            model = build_model()
            model.load_state_dict(checkpoint["model"], strict=True)
            model.to("mps").eval()
            torch.mps.synchronize()
            state["model_load_seconds"] = time.perf_counter() - started
        except Exception as exc:  # noqa: BLE001 -- all planned rows remain on setup failure
            setup_error = f"{type(exc).__name__}: {exc}"
        state["setup_error"] = setup_error
        write(output / "run.json", state)
        for record, row in zip(plan["records"], rows, strict=True):
            started = time.perf_counter()
            try:
                if setup_error:
                    raise RuntimeError(setup_error)
                path = local(root, record["file_name"])
                need(sha(path) == record["source_sha256"], "Source image changed")
                with Image.open(path) as image:
                    need(list(image.size) == record["image_size"], "Original dimensions changed")
                    gray = grayscale(image)
                    row["input_size"] = list(gray.size)
                    row["grayscale_rgb_sha256"] = hashlib.sha256(str(gray.size).encode() + b"|RGB|" + gray.tobytes()).hexdigest()
                    tensor = pil_to_tensor(gray).to(torch.float32) / 255.0
                    row["tensor"] = {"shape": list(tensor.shape), "dtype": "float32", "byteorder": sys.byteorder,
                                     "sha256": hashlib.sha256(tensor.contiguous().numpy().tobytes()).hexdigest()}
                row["decode_tensor_seconds"] = time.perf_counter() - started
                torch.mps.synchronize()
                tick = time.perf_counter()
                row["model_call_started"] = True
                try:
                    with torch.inference_mode():
                        returned = model([tensor.to("mps")])[0]
                    torch.mps.synchronize()
                    row["model_call_completed"] = True
                    raw = {key: value.cpu().tolist() for key, value in returned.items()}
                    try:
                        json.dumps(raw, allow_nan=False)
                        row["raw_detector_output"] = raw
                    except ValueError:
                        row["raw_invalid_output_repr"] = repr(raw)
                        raise
                finally:
                    row["model_and_transfer_seconds"] = time.perf_counter() - tick
                row["predictions"] = [{"box": b, "label": label, "score": score}
                                      for b, label, score in zip(raw["boxes"], raw["labels"], raw["scores"], strict=True)]
                scorer.score_case(record, row["predictions"], .5)
                need(sha(path) == record["source_sha256"], "Source changed during inference")
                row["status"] = "ok"
            except Exception as exc:  # noqa: BLE001 -- keep raw output and every failed case
                row["status"] = "failed"
                row["error"] = f"{type(exc).__name__}: {exc}"
            finally:
                row["full_case_seconds"] = time.perf_counter() - started
                write(output / "predictions.json", rows)
        completed_loop = True
    finally:
        state["status"] = "completed" if completed_loop else "interrupted"
        state["finished_at"] = datetime.now(UTC).isoformat()
        state["model_calls_started"] = sum(r["model_call_started"] for r in rows)
        state["model_calls_completed"] = sum(r["model_call_completed"] for r in rows)
        state["changed_bindings"] = [p for p, digest in plan["bindings"].items() if not Path(p).is_file() or sha(p) != digest]
        state["integrity_passed"] = not state["changed_bindings"]
        state["successful_cases"] = sum(r["status"] == "ok" for r in rows)
        write(output / "predictions.json", rows)
        analysis = analyze(plan["records"], plan["baseline"], rows, scorer)
        analysis["integrity_passed"] = state["integrity_passed"]
        write(output / "analysis.json", analysis)
        write(output / "run.json", state)
    return state["successful_cases"] == 80 and state["integrity_passed"] and state["status"] == "completed"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("run")
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        need(not args.output.exists(), "Plan exists; do not overwrite")
        value = prepare(ROOT)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write(args.output, value, exclusive=True)
        print(json.dumps({"planned": len(value["records"]), "model_called": False, "image_pixels_decoded": False}))
    else:
        if not run(args.plan, args.output):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
