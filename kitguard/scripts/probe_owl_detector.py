"""Fixed 28-development-image OWLv2 CPU shadow probe; never changes KitGuard decisions.

No holdout selector, accelerator path, order targets, or model-guided image selection.
See docs/v0.3/OWL_DEVELOPMENT_PROTOCOL.json, written before first inference.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "docs/v0.3/OWL_DEVELOPMENT_PROTOCOL.json"
MODEL = Path.home() / "Downloads/AI-Models/owlv2-base-patch16-ensemble"
PARTS = ("bolt", "nut", "washer", "bracket")
CATEGORY_MAP = {str(i): "nut" if i in (7, 9, 10, 11) else "bolt" for i in range(1, 14)}
SPEC = ROOT / "datasets/manifests/v0.3/source_grouped_v2/screws_new_development_crop_specs_v1.json"


def sha(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def dump(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def iou(a: list[float], b: list[float]) -> float:
    overlap = max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - overlap
    return overlap / union if union > 0 else 0.0


def nms(candidates: list[dict], threshold: float) -> tuple[list[dict], list[dict]]:
    """Deterministic same-class suppression; never fit desired quantities."""
    kept, suppressed = [], []
    for candidate in sorted(candidates, key=lambda item: (-item["score"], item["raw_index"])):
        conflict = next(
            (
                other
                for other in kept
                if other["part"] == candidate["part"]
                and iou(other["box_xyxy"], candidate["box_xyxy"]) > threshold
            ),
            None,
        )
        if conflict is None:
            kept.append(candidate)
        else:
            suppressed.append({**candidate, "suppressed_by_raw_index": conflict["raw_index"]})
    return kept, suppressed


def match_boxes(predicted: list[dict], truth: list[dict]) -> dict:
    """Score-ordered one-to-one class-aware AABB matches at the fixed IoU 0.5."""
    remaining = {item["annotation_id"]: item for item in truth}
    matches, false_positives = [], []
    for item in sorted(predicted, key=lambda row: (-row["score"], row["raw_index"])):
        candidates = [
            (iou(item["box_xyxy"], gt["box_xyxy"]), annotation_id)
            for annotation_id, gt in remaining.items()
            if gt["part"] == item["part"]
        ]
        candidates.sort(key=lambda pair: (-pair[0], pair[1]))
        if candidates and candidates[0][0] >= 0.5:
            overlap, annotation_id = candidates[0]
            matches.append(
                {
                    "raw_index": item["raw_index"],
                    "annotation_id": annotation_id,
                    "iou": overlap,
                    "part": item["part"],
                }
            )
            del remaining[annotation_id]
        else:
            false_positives.append(item["raw_index"])
    return {
        "tp": len(matches),
        "fp": len(false_positives),
        "fn": len(remaining),
        "matches": matches,
        "false_positive_raw_indices": false_positives,
        "missed_annotation_ids": sorted(remaining),
    }


def author_boxes(case: dict, view: dict, input_size: tuple[int, int]) -> list[dict]:
    if case["id"] != view["id"] or case["crop_xyxy"] != view["crop_xyxy"]:
        raise ValueError("Author view identity mismatch")
    x0, y0, x1, y1 = view["crop_xyxy"]
    scale_x, scale_y = input_size[0] / (x1 - x0), input_size[1] / (y1 - y0)
    selected = set(case["included_annotation_ids"])
    boxes = []
    for item in view["all_source_annotations"]:
        if item["id"] not in selected:
            continue
        a, b, c, d = item["conservative_aabb_xyxy"]
        if not (x0 <= a < c <= x1 and y0 <= b < d <= y1):
            raise ValueError("Included author box is not fully inside crop")
        boxes.append(
            {
                "annotation_id": item["id"],
                "part": CATEGORY_MAP[str(item["category_id"])],
                "box_xyxy": [(a - x0) * scale_x, (b - y0) * scale_y, (c - x0) * scale_x, (d - y0) * scale_y],
                "source_oriented_box_row_col_w_h_phi": item["bbox_row_col_width_height_phi"],
            }
        )
    if {item["annotation_id"] for item in boxes} != selected:
        raise ValueError("Missing or duplicated author box")
    counts = {part: sum(box["part"] == part for box in boxes) for part in PARTS}
    if counts != case["ground_truth"]:
        raise ValueError("Author box projection disagrees with count truth")
    return boxes


def summarize(rows: list[dict], planned: list[dict]) -> dict:
    result = {}
    for dataset in ("loco", "screws", "all"):
        cases = [c for c in planned if dataset == "all" or c["dataset"] == dataset]
        actual = [r for r in rows if dataset == "all" or r["dataset"] == dataset]
        success = [r for r in actual if r.get("error") is None]
        group = {
            "planned": len(cases),
            "completed": len(actual),
            "successful_inferences": len(success),
            "errors": len(actual) - len(success),
            "exact_count_images": sum(r["counts_exact"] for r in success),
            "exact_count_denominator": len(cases),
            "per_class_exact": {
                part: sum(r["counts"][part] == r["ground_truth"][part] for r in success) for part in PARTS
            },
            "per_class_exact_denominator": len(cases),
            "per_class_absolute_error_sum_successful": {
                part: sum(abs(r["counts"][part] - r["ground_truth"][part]) for r in success) for part in PARTS
            },
            "absolute_error_denominator_successful": len(success),
            "median_cpu_pipeline_ms": statistics.median([r["latency_ms"] for r in success])
            if success
            else None,
            "max_cpu_pipeline_ms": max([r["latency_ms"] for r in success], default=None),
        }
        if dataset == "screws":
            localized = [r for r in success if r.get("localization") is not None]
            totals = {key: sum(r["localization"][key] for r in localized) for key in ("tp", "fp", "fn")}
            tp, fp, fn = totals["tp"], totals["fp"], totals["fn"]
            group["localization_at_iou_0_5"] = {
                **totals,
                "successful_image_denominator": len(localized),
                "precision": tp / (tp + fp) if tp + fp else None,
                "recall": tp / (tp + fn) if tp + fn else None,
                "failed_images_excluded_and_reported_separately": len(actual) - len(localized),
                "box_definition": "AABB enclosing author oriented box after crop translation; not oriented IoU or mAP",
            }
        result[dataset] = group
    return result


def infer(image, processor, model, torch, queries: list[str], threshold: float, nms_threshold: float):
    """Only image and fixed queries enter this function; never receives a case or truth."""
    inputs = processor(images=image, text=[queries], return_tensors="pt")
    if any(tensor.device.type != "cpu" for tensor in inputs.values()):
        raise RuntimeError("Non-CPU processor tensor rejected")
    pixel_values = inputs["pixel_values"].detach().contiguous().numpy()
    pixel_metadata = {
        "sha256": hashlib.sha256(pixel_values.tobytes()).hexdigest(),
        "shape": list(pixel_values.shape),
        "dtype": str(pixel_values.dtype),
        "byte_order": "C contiguous native endian",
    }
    with torch.inference_mode():
        outputs = model(**inputs)
    raw = {"logits": outputs.logits[0].detach().numpy(), "pred_boxes": outputs.pred_boxes[0].detach().numpy()}
    if outputs.objectness_logits is not None:
        raw["objectness_logits"] = outputs.objectness_logits[0].detach().numpy()
    if not all(bool(torch.isfinite(torch.from_numpy(array)).all()) for array in raw.values()):
        raise ValueError("Non-finite detector output")
    max_scores = outputs.logits[0].max(dim=-1).values.sigmoid()
    raw_indices = torch.nonzero(max_scores > threshold, as_tuple=False).flatten().tolist()
    result = processor.post_process_grounded_object_detection(
        outputs, threshold=threshold, target_sizes=[(image.height, image.width)], text_labels=[queries]
    )[0]
    if len(raw_indices) != len(result["boxes"]):
        raise RuntimeError("Official postprocessing changed raw-box selection contract")
    candidates, invalid = [], []
    for raw_index, box, score, label in zip(
        raw_indices, result["boxes"], result["scores"], result["labels"], strict=True
    ):
        original = box.tolist()
        clipped = [
            max(0.0, min(image.width, original[0])),
            max(0.0, min(image.height, original[1])),
            max(0.0, min(image.width, original[2])),
            max(0.0, min(image.height, original[3])),
        ]
        item = {
            "raw_index": raw_index,
            "part": PARTS[int(label)],
            "query_index": int(label),
            "score": float(score),
            "box_xyxy": clipped,
            "unclipped_box_xyxy": original,
        }
        if clipped[2] <= clipped[0] or clipped[3] <= clipped[1]:
            invalid.append(item)
        else:
            candidates.append(item)
    kept, suppressed = nms(candidates, nms_threshold)
    counts = {part: sum(item["part"] == part for item in kept) for part in PARTS}
    return {
        "pixel_values": pixel_metadata,
        "pre_nms": candidates,
        "post_nms": kept,
        "suppressed": suppressed,
        "invalid_boxes": invalid,
        "counts": counts,
    }, raw


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "evaluation-runs/v03_owl_development_v1")
    parser.add_argument(
        "--resume-slow",
        action="store_true",
        help="Continue only a saved pause after >60s image, with unchanged code/protocol",
    )
    args = parser.parse_args()
    protocol = json.loads(PROTOCOL.read_text())
    if protocol["model"]["device"] != "cpu" or protocol["model"]["torch_threads"] > 4:
        raise ValueError("CPU-only, at most four threads")
    planned = [{**c, "dataset": group["dataset"]} for group in protocol["groups"] for c in group["cases"]]
    if [sum(c["dataset"] == key for c in planned) for key in ("loco", "screws")] != [16, 12] or any(
        c["split"] != "development" for c in planned
    ):
        raise ValueError("Exactly 16 LOCO +12 Screws development cases required")
    if len({c["id"] for c in planned}) != 28:
        raise ValueError("Duplicate case identity")
    for case in planned:
        if (
            sha(ROOT / case["input_jpeg"]) != case["input_sha256"]
            or sha(ROOT / "datasets" / case["source_image"]) != case["source_sha256"]
        ):
            raise ValueError(f"Input/source hash mismatch: {case['id']}")
    download = json.loads((MODEL / "DOWNLOAD_MANIFEST.json").read_text())
    if (
        download["repo_id"] != protocol["model"]["repo_id"]
        or download["revision"] != protocol["model"]["revision"]
    ):
        raise ValueError("Pinned model mismatch")
    for item in download["files"]:
        if sha(MODEL / item["path"]) != item["sha256"]:
            raise ValueError(f"Model file SHA mismatch: {item['path']}")
    if sha(MODEL / "model.safetensors") != protocol["model"]["safetensors_sha256"]:
        raise ValueError("Weights do not match pre-inference protocol")
    output = args.output.resolve()
    if output.exists() and not args.resume_slow:
        raise ValueError("Refusing to overwrite output directory")
    rows = []
    if args.resume_slow:
        run = json.loads((output / "run.json").read_text())
        if (
            run["status"] != "paused_slow_case"
            or run["script_sha256"] != sha(Path(__file__))
            or run["protocol_sha256"] != sha(PROTOCOL)
        ):
            raise ValueError("Resume requires unchanged code/protocol and slow-case pause")
        rows = [json.loads(line) for line in (output / "predictions.jsonl").read_text().splitlines()]
        if [r["case_id"] for r in rows] != [c["id"] for c in planned[: len(rows)]]:
            raise ValueError("Saved output is not a completed prefix")
    else:
        output.mkdir(parents=True)
        for folder in ("inputs", "raw_outputs", "source_snapshot"):
            (output / folder).mkdir()
        shutil.copy2(PROTOCOL, output / "protocol.json")
        shutil.copy2(Path(__file__), output / "source_snapshot/probe_owl_detector.py")
        shutil.copy2(MODEL / "DOWNLOAD_MANIFEST.json", output / "model_download_manifest.json")
        run = {
            "started_at_utc": datetime.now(UTC).isoformat(),
            "status": "running",
            "protocol_sha256": sha(PROTOCOL),
            "script_sha256": sha(Path(__file__)),
            "model": protocol["model"],
            "case_ids": [c["id"] for c in planned],
            "python": platform.python_version(),
            "platform": platform.platform(),
        }
    dump(output / "run.json", run)
    os.environ.update(
        {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
            "OMP_NUM_THREADS": "4",
            "MKL_NUM_THREADS": "4",
            "TOKENIZERS_PARALLELISM": "false",
        }
    )
    import numpy as np
    import torch
    import transformers
    from PIL import Image
    from transformers import Owlv2ForObjectDetection, Owlv2Processor

    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    device = torch.device("cpu")
    load_started = time.perf_counter()
    processor = Owlv2Processor.from_pretrained(MODEL, local_files_only=True)
    model = (
        Owlv2ForObjectDetection.from_pretrained(MODEL, local_files_only=True, dtype=torch.float32)
        .to(device)
        .eval()
    )
    if any(parameter.device.type != "cpu" for parameter in model.parameters()):
        raise RuntimeError("Non-CPU model parameter rejected")
    run.update(
        {
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "model_load_seconds": round(time.perf_counter() - load_started, 3),
            "torch_num_threads": torch.get_num_threads(),
            "device": str(device),
            "dtype": str(next(model.parameters()).dtype),
        }
    )
    specifications = {view["id"]: view for view in json.loads(SPEC.read_text())["views"]}
    run["screws_dev_specs_sha256"] = sha(SPEC)
    queries = [item["text"] for item in protocol["queries"]]
    dump(output / "run.json", run)
    for index, case in enumerate(planned[len(rows) :], len(rows) + 1):
        started = time.perf_counter()
        row = {
            "case_id": case["id"],
            "dataset": case["dataset"],
            "source_id": case["source_id"],
            "source_sha256": case["source_sha256"],
            "input_sha256": case["input_sha256"],
            "ground_truth": case["ground_truth"],
            "model_revision": protocol["model"]["revision"],
            "device": "cpu",
            "error": None,
        }
        try:
            destination = output / "inputs" / f"{index:03}.jpg"
            shutil.copy2(ROOT / case["input_jpeg"], destination)
            with Image.open(destination) as source:
                image = source.convert("RGB")
            row["input_size"] = list(image.size)
            values, raw = infer(
                image,
                processor,
                model,
                torch,
                queries,
                protocol["postprocess"]["score_threshold"],
                protocol["postprocess"]["nms_iou_threshold"],
            )
            raw_path = output / "raw_outputs" / f"{index:03}.npz"
            np.savez_compressed(raw_path, **raw)
            row.update(values)
            row["raw_output_path"] = str(raw_path.relative_to(output))
            row["raw_output_sha256"] = sha(raw_path)
            row["counts_exact"] = row["counts"] == case["ground_truth"]
            if case["dataset"] == "screws":
                row["author_truth_boxes"] = author_boxes(case, specifications[case["id"]], image.size)
                row["localization"] = match_boxes(row["post_nms"], row["author_truth_boxes"])
            else:
                row["localization"] = None
        except Exception as error:  # noqa: BLE001 — failed cases stay in the denominator
            row["error"] = {"type": type(error).__name__, "message": str(error)}
            row["counts_exact"] = False
        row["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
        rows.append(row)
        with (output / "predictions.jsonl").open("a") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        run["summary"] = summarize(rows, planned)
        run["completed_cases"] = len(rows)
        run["script_changed_during_run"] = run["script_sha256"] != sha(Path(__file__))
        print(
            json.dumps(
                {
                    "index": index,
                    "case_id": case["id"],
                    "latency_ms": row["latency_ms"],
                    "counts": row.get("counts"),
                    "exact": row["counts_exact"],
                    "error": row["error"],
                }
            ),
            flush=True,
        )
        if row["latency_ms"] > 60000 and not args.resume_slow:
            run["status"] = "paused_slow_case"
            dump(output / "run.json", run)
            print("Paused after a >60-second case; notify parent before any continuation.", flush=True)
            return
        dump(output / "run.json", run)
    run["status"] = "completed"
    run["finished_at_utc"] = datetime.now(UTC).isoformat()
    dump(output / "run.json", run)


if __name__ == "__main__":
    main()
