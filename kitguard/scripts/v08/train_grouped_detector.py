"""Three-class shadow detector. No production imports, held-back evaluator, or network downloads.

preflight is stdlib-only. train loads Torch only after the review/data gates pass.
The fixed run uses COCO initialization, never the learned two-class v1 weights.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import random
import shutil
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLASSES = {1: "bolt", 2: "nut", 3: "washer"}
SCREWS_HASHES = {
    "manifest.json": "27044ecee0fd81d3f29b7cb70c5c8252f08d6588cbba46d346388b2cf83adf23",
    "train.json": "1a78dea3e7e8747d04ba54a0c100b465853b6c46d064a1f672a0b71885ea68c6",
    "val.json": "cd2604d0d11bee0824188f287168490436085e150784a599822180edef311d66",
}
V1_PROTOCOL = "training-runs/public_detector_v1_mps_20260930/protocol.json"
V1_PROTOCOL_SHA = "0172ed492c6ed0fa6ba3dc0bd2c3e7b1091290eb5761542673f218ab396f3d11"
COCO_SHA = "907ea3f91ff92242bc1baea8049276a3e76bca48ce7560bd268cc029f37977b5"
COCO_FILENAME = "fasterrcnn_mobilenet_v3_large_320_fpn-907ea3f9.pth"
PLAN = "docs/v0.8/GROUPED_DETECTOR_TRAINING_PLAN.md"
CONFIG = {
    "model": "fasterrcnn_mobilenet_v3_large_320_fpn", "classes": CLASSES,
    "head_outputs": 4, "unsupported_classes": ["bracket"],
    "epochs": 12, "batch_size": 2, "seed": 20261002, "device": "mps", "precision": "float32",
    "min_size": 640, "max_size": 960, "learning_rate": 0.005, "momentum": 0.9,
    "weight_decay": 0.0005, "lr_step_epoch": 8, "lr_gamma": 0.1, "warmup_steps": 100,
    "gradient_clip_norm": 10.0, "threads": 6, "thresholds": [i / 10 for i in range(1, 10)],
    "box_score_thresh": 0.05, "box_nms_thresh": 0.5, "box_detections_per_img": 100,
    "matching_iou": 0.5, "augmentation": "independent horizontal/vertical flip p=0.5; train only",
    "annotation_scope": "author_annotated_target_only",
    "screws_washer_policy": "No washer-positive annotations; zero means no projected author washer target, not field absence",
    "postprocessing_boundary": "All returned boxes retained after frozen detector score floor 0.05/NMS0.5/max100",
    "ranking": ["higher balanced exact count accuracy", "lower balanced three-class count MAE",
                "higher pooled class-aware box F1", "earlier epoch", "higher threshold within epoch"],
    "balance": "0.5*Screws image mean + 0.5*FOD validation source-group macro mean",
    "held_back_policy": "no held_back manifest/image reads; no held-back evaluation command",
    "initialization": "original COCO state; replace 91-class head with four outputs",
    "claim_limit": "Source groups are not certified physical objects. FOD count truth is author targets only.",
}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    temp.replace(path)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def valid_box(box, size=None):
    require(isinstance(box, (list, tuple)) and len(box) == 4 and all(number(x) for x in box),
            "Invalid/nonfinite bounding box")
    x0, y0, x1, y1 = box
    require(0 <= x0 < x1 and 0 <= y0 < y1, "Empty/reversed/negative bounding box")
    if size:
        require(x1 <= size[0] and y1 <= size[1], "Bounding box outside image")


def safe_local(root, relative):
    require(isinstance(relative, str) and not Path(relative).is_absolute(), "Expected relative dataset path")
    require(not any(p == "held_back" or p.startswith("held_back.") for p in Path(relative).parts),
            "Held-back path is forbidden")
    path = (root / relative).resolve()
    require(path.is_relative_to(root.resolve()), "Dataset path escapes project root")
    require(not any(p == "held_back" or p.startswith("held_back.") for p in path.parts),
            "Resolved held-back path is forbidden")
    return path


def validate_review(review, protocol, hashes):
    require(review.get("schema") == "kitguard.v08.foda-training-review.v1", "Missing review schema")
    require(review.get("status") == "approved_for_local_training", "FOD visual review not approved")
    require(review.get("annotation_scope") == "author_annotated_target_only", "Wrong annotation scope")
    require(review.get("held_back_human_or_rendered") is False, "Held-back human/render exposure gate")
    require(review.get("all_frame_completeness_certified") is False, "Six previews cannot certify all frames")
    require(sorted(review.get("reviewed_preview_ids", [])) == sorted(protocol["preview_ids"]),
            "Review does not cover exactly the six selected training previews")
    require(len(protocol["preview_ids"]) == len(set(protocol["preview_ids"])) == 6, "Need six preview IDs")
    for field, name in (("train_sha256", "train.json"), ("validation_sha256", "validation.json"),
                        ("preview_sha256", "development_preview.jpg")):
        require(review.get(field) == hashes[name], f"Review binding differs: {field}")
    require(isinstance(review.get("notes"), (str, list)) and bool(review["notes"]), "Review notes missing")


def foda_records(rows, role, protocol):
    records = []
    require(isinstance(rows, list), "FOD manifest must be an array")
    for row in rows:
        label = row["class_id"]
        require(type(label) is int and label in CLASSES, "Unknown FOD label")
        require(CLASSES[label] == row["author_category"].lower(), "FOD label mapping changed")
        require(row["protocol_role"] == role and protocol["group_roles"].get(row["group_id"]) == role,
                "FOD split/group leakage")
        require(row["image_size"] == [300, 300], "FOD image dimensions changed")
        require(f"/images/{role}/" in row["local_image"], "FOD file must be in its assigned split")
        valid_box(row["box_xyxy"], row["image_size"])
        records.append({
            "id": "foda:" + row["image_id"], "source": "foda", "group_id": row["group_id"],
            "role": role, "file_name": row["local_image"], "source_sha256": row["image_sha256"],
            "image_size": row["image_size"], "rgb_sha256": row["rgb_sha256"],
            "ground_truth": [{"label": label, "box": row["box_xyxy"],
                              "annotation_id": row["annotation_member_path"]}],
        })
    require(len({r["id"] for r in records}) == len(records), "Duplicate FOD image IDs")
    return records


def screws_records(data, role, excluded):
    require({c["id"]: c["name"] for c in data["categories"]} == {1: "bolt", 2: "nut"},
            "Original Screws two-class projection changed")
    annotations = defaultdict(list)
    for ann in data["annotations"]:
        require(ann["category_id"] in (1, 2), "Unknown Screws class")
        x, y, width, height = ann["bbox"]
        annotations[ann["image_id"]].append({"label": ann["category_id"],
                                           "box": [x, y, x + width, y + height],
                                           "annotation_id": ann["id"]})
    records = []
    for row in data["images"]:
        require(row["original_filename"] not in excluded, "Excluded Screws original leaked")
        size = [row["width"], row["height"]]
        for ann in annotations[row["id"]]:
            valid_box(ann["box"], size)
        records.append({"id": f"screws:{row['id']}", "source": "screws",
                        "group_id": row["original_filename"], "role": role, "file_name": row["file_name"],
                        "source_sha256": row["source_sha256"], "image_size": size,
                        "ground_truth": annotations[row["id"]]})
    require(set(annotations) <= {r["id"] for r in data["images"]}, "Orphan Screws annotation")
    require(len({r["id"] for r in records}) == len(records), "Duplicate Screws ID")
    return records


def check_partition(training, validation):
    require(not ({r["id"] for r in training} & {r["id"] for r in validation}), "Train/val image overlap")
    train_groups = {(r["source"], r["group_id"]) for r in training}
    val_groups = {(r["source"], r["group_id"]) for r in validation}
    require(not (train_groups & val_groups), "Train/val source-group overlap")
    require(not ({r["source_sha256"] for r in training} & {r["source_sha256"] for r in validation}),
            "Train/val exact-byte overlap")


def preflight(root, foda, review_path, coco_path):
    """Read only explicit train/validation metadata and image bytes; never held-back files."""
    root, foda = root.resolve(), foda.resolve()
    bindings = {}

    def bind(path):
        path = Path(path).resolve()
        require(not any(p == "held_back" or p.startswith("held_back.") for p in path.parts),
                "Held-back manifest is forbidden")
        value = sha(path)
        bindings[str(path)] = value
        return value

    screws = root / "datasets/derived/public_detector_v1"
    for name, expected in SCREWS_HASHES.items():
        require(bind(screws / name) == expected, f"Original Screws manifest changed: {name}")
    sm = read(screws / "manifest.json")
    excluded = {r["original_filename"] for r in sm["excluded_originals"]}
    require(len(excluded) == sm["excluded_original_count"] == 104, "Need original 104 source exclusions")
    sp = root / V1_PROTOCOL
    require(bind(sp) == V1_PROTOCOL_SHA, "Reference architecture protocol changed")
    architecture = read(sp)
    require(bind(coco_path) == COCO_SHA == architecture["pretrained_sha256"], "Original COCO cache changed")
    files = ("protocol.json", "summary.json", "duplicate_audit.json", "train.json", "validation.json",
             "development_preview.jpg", "prepare_foda_grouped_development.py")
    fh = {name: bind(foda / name) for name in files}
    protocol = read(foda / "protocol.json")
    require(protocol["schema"] == "kitguard.v08.foda-grouped-development.v1", "FOD protocol schema")
    require(protocol["independent_physical_objects"] is False, "Do not claim physical identity isolation")
    require(fh["prepare_foda_grouped_development.py"] == protocol["script_sha256"], "FOD preparer snapshot changed")
    summary = read(foda / "summary.json")
    # Deliberately do not iterate summary.files: it contains held-back file bindings.
    for name in ("protocol.json", "duplicate_audit.json", "train.json", "validation.json",
                 "development_preview.jpg"):
        require(summary["files"][name] == fh[name], f"FOD summary binding changed: {name}")
    duplicates = read(foda / "duplicate_audit.json")
    require(not duplicates["cross_source_group_conflicts"], "Cross-group duplicate conflicts")
    bind(review_path)
    validate_review(read(review_path), protocol, fh)
    training = screws_records(read(screws / "train.json"), "train", excluded)
    validation = screws_records(read(screws / "val.json"), "validation", excluded)
    require((len(training), len(validation)) == (214, 44), "Original Screws denominator changed")
    ft = foda_records(read(foda / "train.json"), "train", protocol)
    fv = foda_records(read(foda / "validation.json"), "validation", protocol)
    require(len(ft) == 400 and len(fv) == 36, "Fixed FOD selection denominator changed")
    groups = defaultdict(list)
    for row in fv:
        groups[row["group_id"]].append(row)
    require(len(groups) == 3 and all(len(rows) == 12 for rows in groups.values()), "Need three FOD val groups")
    require(Counter(r["ground_truth"][0]["label"] for r in fv) == {1: 12, 2: 12, 3: 12},
            "FOD validation class denominators changed")
    require(set(protocol["preview_ids"]) <= {r["id"].split(":")[1] for r in ft}, "Preview outside training")
    training += ft
    validation += fv
    check_partition(training, validation)
    for record in training + validation:
        path = safe_local(root, record["file_name"])
        require(bind(path) == record["source_sha256"], f"Image bytes changed: {record['id']}")
    bind(Path(__file__))
    bind(root / PLAN)
    return {"schema": "kitguard.v08.grouped-detector-preflight.v1", "status": "passed",
            "created_at": datetime.now(UTC).isoformat(), "project_root": str(root),
            "training": training, "validation": validation, "bindings": bindings,
            "trainable_parameters": architecture["trainable_parameters"], "coco_path": str(coco_path.resolve()),
            "review_path": str(review_path.resolve()), "foda_path": str(foda), "config": CONFIG,
            "held_back_human_or_rendered": False, "held_back_read_by_trainer": False,
            "preparer_decoded_all_candidates_for_integrity": True,
            "independent_physical_objects_certified": False}


def iou(a, b):
    area = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    return area / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - area)


def score_case(record, predictions, threshold):
    gt = record["ground_truth"]
    for item in predictions:
        require(type(item["label"]) is int and item["label"] in CLASSES, "Prediction class unsupported")
        require(number(item["score"]) and 0 <= item["score"] <= 1, "Prediction score invalid")
        valid_box(item["box"], record["image_size"])
    selected = [i for i, p in enumerate(predictions) if p["score"] >= threshold]
    ordered = sorted(selected, key=lambda i: (-predictions[i]["score"], i))
    matched, matches, fp = set(), [], []
    for pi in ordered:
        pred = predictions[pi]
        candidates = [(iou(pred["box"], truth["box"]), gi) for gi, truth in enumerate(gt)
                      if gi not in matched and truth["label"] == pred["label"]]
        candidates.sort(key=lambda pair: (-pair[0], pair[1]))
        if candidates and candidates[0][0] >= CONFIG["matching_iou"]:
            overlap, gi = candidates[0]
            matched.add(gi)
            matches.append({"prediction_index": pi, "ground_truth_index": gi, "iou": overlap})
        else:
            fp.append(pi)
    fn = [i for i in range(len(gt)) if i not in matched]
    truth_count = {CLASSES[k]: sum(g["label"] == k for g in gt) for k in CLASSES}
    pred_count = {CLASSES[k]: sum(predictions[i]["label"] == k for i in selected) for k in CLASSES}
    error = {name: pred_count[name] - truth_count[name] for name in CLASSES.values()}
    per_class = {name: {"tp": sum(gt[m["ground_truth_index"]]["label"] == label for m in matches),
                        "fp": sum(predictions[i]["label"] == label for i in fp),
                        "fn": sum(gt[i]["label"] == label for i in fn),
                        "count_error": error[name], "absolute_count_error": abs(error[name])}
                 for label, name in CLASSES.items()}
    return {"id": record["id"], "source": record["source"], "group_id": record["group_id"],
            "truth_count": truth_count, "predicted_count": pred_count, "count_error": error,
            "exact_count": all(v == 0 for v in error.values()),
            "count_mae": sum(abs(v) for v in error.values()) / len(CLASSES),
            "selected_prediction_indices": selected, "matches": matches,
            "false_positive_indices": fp, "missed_ground_truth_indices": fn, "per_class": per_class}


def aggregate(rows):
    require(bool(rows), "Empty metric denominator")
    classes = {name: {key: sum(r["per_class"][name][key] for r in rows) for key in ("tp", "fp", "fn")}
               for name in CLASSES.values()}
    for name, counts in classes.items():
        counts["count_mae"] = sum(r["per_class"][name]["absolute_count_error"] for r in rows) / len(rows)
        counts["signed_count_error"] = sum(r["per_class"][name]["count_error"] for r in rows)
    tp = sum(c["tp"] for c in classes.values())
    fp = sum(c["fp"] for c in classes.values())
    fn = sum(c["fn"] for c in classes.values())
    return {"n": len(rows), "exact_count_n": sum(r["exact_count"] for r in rows),
            "exact_count_accuracy": sum(r["exact_count"] for r in rows) / len(rows),
            "count_mae": sum(r["count_mae"] for r in rows) / len(rows), "per_class": classes,
            "tp": tp, "fp": fp, "fn": fn, "box_f1": 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else 0.0}


def evaluate(records, raw_predictions, threshold):
    require(len(records) == len(raw_predictions), "Validation must retain full denominator")
    require(all(p["id"] == r["id"] and p["status"] == "ok" for r, p in zip(records, raw_predictions)),
            "Validation failed, reordered or incomplete; selection forbidden")
    rows = [score_case(r, p["predictions"], threshold) for r, p in zip(records, raw_predictions)]
    screws = aggregate([r for r in rows if r["source"] == "screws"])
    foda = [r for r in rows if r["source"] == "foda"]
    groups = {gid: aggregate([r for r in foda if r["group_id"] == gid]) for gid in sorted({r["group_id"] for r in foda})}
    require(bool(groups), "FOD validation groups missing")
    group_accuracy = sum(g["exact_count_accuracy"] for g in groups.values()) / len(groups)
    group_mae = sum(g["count_mae"] for g in groups.values()) / len(groups)
    return {"threshold": threshold, "balanced_exact_count_accuracy": 0.5 * (screws["exact_count_accuracy"] + group_accuracy),
            "balanced_class_count_mae": 0.5 * (screws["count_mae"] + group_mae),
            "pooled": aggregate(rows), "screws": screws, "foda": aggregate(foda), "foda_groups": groups,
            "foda_group_macro_exact_count_accuracy": group_accuracy, "foda_group_macro_count_mae": group_mae,
            "cases": rows, "annotation_scope": CONFIG["annotation_scope"], "unsupported_classes": ["bracket"]}


def rank(metrics):
    return (metrics["balanced_exact_count_accuracy"], -metrics["balanced_class_count_mae"],
            metrics["pooled"]["box_f1"])


def select_threshold(sweep):
    require(bool(sweep), "Empty threshold sweep")
    return max(sweep, key=lambda m: (*rank(m), m["threshold"]))


def update_best(best, candidate, epoch):
    # Equal scores retain the earlier epoch even if the later selected threshold is higher.
    return best is None or rank(candidate) > tuple(best["rank"])


def assert_bindings(bindings):
    for path, expected in bindings.items():
        require(sha(path) == expected, f"Bound source/data changed: {path}")


class TrainingDataset:
    def __init__(self, root, records, augment=False):
        self.root, self.records, self.augment = root, records, augment

    def __len__(self):
        return len(self.records)

    def __getitem__(self, index):
        import torch
        from PIL import Image
        from torchvision.transforms.functional import pil_to_tensor
        record = self.records[index]
        path = safe_local(self.root, record["file_name"])
        require(sha(path) == record["source_sha256"], "Training image changed after preflight")
        with Image.open(path) as image:
            require(list(image.size) == record["image_size"], "Image size differs from bound annotation")
            tensor = pil_to_tensor(image.convert("RGB")).to(torch.float32) / 255.0
        boxes = torch.tensor([a["box"] for a in record["ground_truth"]], dtype=torch.float32).reshape(-1, 4)
        labels = torch.tensor([a["label"] for a in record["ground_truth"]], dtype=torch.int64)
        if self.augment and random.random() < 0.5:
            tensor = tensor.flip(-1)
            boxes[:, [0, 2]] = tensor.shape[-1] - boxes[:, [2, 0]]
        if self.augment and random.random() < 0.5:
            tensor = tensor.flip(-2)
            boxes[:, [1, 3]] = tensor.shape[-2] - boxes[:, [3, 1]]
        return tensor, {"boxes": boxes, "labels": labels, "image_id": torch.tensor(index)}


def collate(batch):
    return tuple(zip(*batch))


def build_model(preflight_record):
    import torch
    from torchvision.models.detection import fasterrcnn_mobilenet_v3_large_320_fpn
    from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
    from torchvision.ops.misc import FrozenBatchNorm2d
    model = fasterrcnn_mobilenet_v3_large_320_fpn(
        weights=None, weights_backbone=None, num_classes=91, progress=False,
        min_size=CONFIG["min_size"], max_size=CONFIG["max_size"],
        box_score_thresh=CONFIG["box_score_thresh"], box_nms_thresh=CONFIG["box_nms_thresh"],
        box_detections_per_img=CONFIG["box_detections_per_img"],
    )

    def frozen_bn(module):
        for name, child in list(module.named_children()):
            if isinstance(child, torch.nn.BatchNorm2d):
                setattr(module, name, FrozenBatchNorm2d(child.num_features, eps=child.eps))
            else:
                frozen_bn(child)
    frozen_bn(model)
    path = preflight_record["coco_path"]
    require(sha(path) == COCO_SHA, "COCO weights changed")
    model.load_state_dict(torch.load(path, map_location="cpu", weights_only=True), strict=True)
    model.roi_heads.box_predictor = FastRCNNPredictor(model.roi_heads.box_predictor.cls_score.in_features, 4)
    trainable = set(preflight_record["trainable_parameters"])
    require(trainable <= dict(model.named_parameters()).keys(), "Pinned trainable parameter policy mismatch")
    for name, param in model.named_parameters():
        param.requires_grad_(name in trainable)
    require(all(p.requires_grad for p in model.roi_heads.box_predictor.parameters()), "New head must train")
    return model


def runtime_bindings():
    """Pin actual local implementations; no loose import of the old metrics/trainer."""
    import importlib
    import inspect

    import torch
    import torchvision
    from PIL import Image
    from torchvision.models import mobilenetv3
    from torchvision.models.detection import faster_rcnn, roi_heads, rpn, transform
    from torchvision.ops import boxes, misc, poolers
    modules = (torch, torchvision, Image, faster_rcnn, roi_heads, rpn, transform, mobilenetv3,
               boxes, misc, poolers, importlib.import_module("torch.optim.sgd"), torch.optim.lr_scheduler)
    paths = {str(Path(inspect.getfile(m)).resolve()) for m in modules}
    # Compiled library hashes record the binary build that can affect numerical behavior.
    for base in (Path(torch.__file__).parent, Path(torchvision.__file__).parent):
        paths.update(str(p.resolve()) for p in base.glob("*.so"))
        if (base / "lib").exists():
            paths.update(str(p.resolve()) for p in (base / "lib").glob("*.dylib"))
    return {p: sha(p) for p in sorted(paths)}


def validation_predictions(model, dataset, device, output):
    import torch
    predictions = []
    model.eval()
    for index, record in enumerate(dataset.records):
        started = time.perf_counter()
        row = {"id": record["id"], "source": record["source"], "group_id": record["group_id"],
               "ground_truth": record["ground_truth"], "image_sha256": record["source_sha256"]}
        try:
            image, _ = dataset[index]
            torch.mps.synchronize()
            model_start = time.perf_counter()
            with torch.inference_mode():
                prediction = model([image.to(device)])[0]
            torch.mps.synchronize()
            row["predictions"] = [{"box": box, "label": int(label), "score": float(score)} for box, label, score in
                                  zip(prediction["boxes"].cpu().tolist(), prediction["labels"].cpu().tolist(),
                                      prediction["scores"].cpu().tolist())]
            row["model_and_transfer_seconds"] = time.perf_counter() - model_start
            score_case(record, row["predictions"], CONFIG["thresholds"][0])
            row["status"] = "ok"
        except Exception as exc:  # noqa: BLE001 -- persist every planned validation failure, then abort selection
            row["status"] = "failed"
            row["error"] = {"type": type(exc).__name__, "message": str(exc)}
            if "predictions" in row:
                row["raw_invalid_predictions_repr"] = repr(row.pop("predictions"))
        row["full_case_seconds"] = time.perf_counter() - started
        predictions.append(row)
        with output.open("a") as stream:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    return predictions


def cpu_state(value):
    import torch
    if isinstance(value, torch.Tensor):
        return value.detach().cpu().clone()
    if isinstance(value, dict):
        return {k: cpu_state(v) for k, v in value.items()}
    if isinstance(value, list):
        return [cpu_state(v) for v in value]
    if isinstance(value, tuple):
        return tuple(cpu_state(v) for v in value)
    return value


def train(receipt, output):
    require(not output.exists(), "Refusing to overwrite an existing experiment")
    require(os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK", "0") == "0", "CPU MPS fallback forbidden")
    output.mkdir(parents=True)
    dump(output / "preflight.json", receipt)
    source = output / "source"
    source.mkdir()
    shutil.copy2(__file__, source / Path(__file__).name)
    shutil.copy2(Path(receipt["foda_path"]) / "prepare_foda_grouped_development.py",
                 source / "prepare_foda_grouped_development.py")
    shutil.copy2(Path(receipt["project_root"]) / PLAN, source / "GROUPED_DETECTOR_TRAINING_PLAN.md")
    metadata = output / "data_bindings"
    metadata.mkdir()
    # Snapshot only permitted metadata, never the held-back manifest or integrity pixel records.
    for path in receipt["bindings"]:
        original = Path(path)
        if original.suffix == ".json":
            relative = original.relative_to(Path(receipt["project_root"]))
            dest = metadata / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, dest)
    state = {"schema": "kitguard.v08.grouped-detector-run.v1", "status": "starting",
             "started_at": datetime.now(UTC).isoformat(), "epochs_completed": 0,
             "held_back_read": False, "production_changed": False}
    dump(output / "run.json", state)
    try:
        import torch
        import torchvision
        from torch.utils.data import DataLoader
        require(torch.backends.mps.is_available(), "MPS required by fixed protocol")
        torch.set_num_threads(CONFIG["threads"])
        torch.manual_seed(CONFIG["seed"])
        torch.mps.manual_seed(CONFIG["seed"])
        random.seed(CONFIG["seed"])
        generator = torch.Generator().manual_seed(CONFIG["seed"])
        device = torch.device("mps")
        protocol = {"schema": "kitguard.v08.grouped-detector-protocol.v1", **CONFIG,
                    "started_at": state["started_at"], "python": platform.python_version(),
                    "platform": platform.platform(), "torch": str(torch.__version__),
                    "torchvision": str(torchvision.__version__),
                    "pillow": importlib.metadata.version("pillow"),
                    "mps_determinism": "Seeds fixed; bitwise MPS reproducibility not guaranteed",
                    "bindings": receipt["bindings"], "runtime_sha256": runtime_bindings(),
                    "trainable_parameters": receipt["trainable_parameters"], "pretrained_sha256": COCO_SHA,
                    "validation_denominators": {"screws_images": 44, "foda_images": 36, "foda_groups": 3},
                    "training_denominators": {"screws_images": 214, "foda_images": 400},
                    "preflight_sha256": sha(output / "preflight.json")}
        dump(output / "protocol.json", protocol)
        assert_bindings(receipt["bindings"])
        model = build_model(receipt).to(device)
        optimizer = torch.optim.SGD([p for p in model.parameters() if p.requires_grad],
                                    lr=CONFIG["learning_rate"], momentum=CONFIG["momentum"],
                                    weight_decay=CONFIG["weight_decay"])
        scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=CONFIG["lr_step_epoch"],
                                                     gamma=CONFIG["lr_gamma"])
        training = TrainingDataset(Path(receipt["project_root"]), receipt["training"], augment=True)
        validation = TrainingDataset(Path(receipt["project_root"]), receipt["validation"])
        loader = DataLoader(training, batch_size=CONFIG["batch_size"], shuffle=True, num_workers=0,
                            collate_fn=collate, generator=generator)
        best = None
        total_start = time.perf_counter()
        for epoch in range(1, CONFIG["epochs"] + 1):
            assert_bindings(receipt["bindings"])
            model.train()
            losses = []
            start = time.perf_counter()
            epoch_dir = output / "epochs" / f"epoch-{epoch:02d}"
            epoch_dir.mkdir(parents=True)
            for step, (images, targets) in enumerate(loader, 1):
                iteration = (epoch - 1) * len(loader) + step
                if iteration <= CONFIG["warmup_steps"]:
                    for group in optimizer.param_groups:
                        group["lr"] = CONFIG["learning_rate"] * (0.01 + 0.99 * iteration / CONFIG["warmup_steps"])
                loss_dict = model([i.to(device) for i in images], [{k: v.to(device) for k, v in t.items()} for t in targets])
                loss = sum(loss_dict.values())
                value = float(loss.detach())
                require(math.isfinite(value), f"Nonfinite loss at {epoch}/{step}")
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                norm = float(torch.nn.utils.clip_grad_norm_(model.parameters(), CONFIG["gradient_clip_norm"]))
                require(math.isfinite(norm), f"Nonfinite gradient at {epoch}/{step}")
                optimizer.step()
                losses.append(value)
                with (epoch_dir / "losses.jsonl").open("a") as stream:
                    stream.write(json.dumps({"step": step, "loss": value, "gradient_norm": norm,
                                             "components": {k: float(v.detach()) for k, v in loss_dict.items()},
                                             "learning_rate": optimizer.param_groups[0]["lr"]}) + "\n")
                if step == 1 or step % 25 == 0 or step == len(loader):
                    print(json.dumps({"event": "train", "epoch": epoch, "step": step, "steps": len(loader),
                                      "loss": value, "elapsed_seconds": time.perf_counter() - start}), flush=True)
            scheduler.step()
            train_seconds = time.perf_counter() - start
            raw = validation_predictions(model, validation, device, epoch_dir / "validation_predictions.jsonl")
            dump(epoch_dir / "validation_predictions.json", raw)
            require(all(r["status"] == "ok" for r in raw), "Validation failures retained; cannot select threshold")
            sweep = [evaluate(receipt["validation"], raw, t) for t in CONFIG["thresholds"]]
            dump(epoch_dir / "threshold_sweep.json", sweep)
            selected = select_threshold(sweep)
            dump(epoch_dir / "selected.json", selected)
            improved = update_best(best, selected, epoch)
            if improved:
                best = {"epoch": epoch, "threshold": selected["threshold"], "rank": rank(selected)}
            checkpoint = {"schema": "kitguard.v08.grouped-detector-checkpoint.v1", "epoch": epoch,
                          "model": cpu_state(model.state_dict()), "optimizer": cpu_state(optimizer.state_dict()),
                          "scheduler": cpu_state(scheduler.state_dict()), "config": protocol,
                          "selected": selected, "best": best, "torch_rng": torch.get_rng_state(),
                          "python_rng": random.getstate(), "loader_rng": generator.get_state(),
                          "mps_rng": torch.mps.get_rng_state(), "protocol_sha256": sha(output / "protocol.json")}
            torch.save(checkpoint, output / "last.pt.tmp")
            (output / "last.pt.tmp").replace(output / "last.pt")
            if improved:
                shutil.copy2(output / "last.pt", output / "best.pt")
                dump(output / "best_validation_metrics.json", selected)
                dump(output / "best_validation_predictions.json", raw)
            history = {"epoch": epoch, "loss_mean": sum(losses) / len(losses), "training_seconds": train_seconds,
                       "epoch_seconds": time.perf_counter() - start, "threshold": selected["threshold"],
                       "rank": rank(selected), "improved": improved,
                       "validation_predictions_sha256": sha(epoch_dir / "validation_predictions.json"),
                       "threshold_sweep_sha256": sha(epoch_dir / "threshold_sweep.json"),
                       "last_checkpoint_sha256": sha(output / "last.pt")}
            with (output / "history.jsonl").open("a") as stream:
                stream.write(json.dumps(history, allow_nan=False) + "\n")
            assert_bindings(receipt["bindings"])
            state.update(status="running", epochs_completed=epoch, best=best)
            dump(output / "run.json", state)
            print(json.dumps({"event": "epoch_completed", **history}), flush=True)
        assert_bindings(protocol["runtime_sha256"])
        state.update(status="completed", completed_at=datetime.now(UTC).isoformat(),
                     total_training_validation_seconds=time.perf_counter() - total_start,
                     source_changed_during_run=False, best_checkpoint_sha256=sha(output / "best.pt"),
                     last_checkpoint_sha256=sha(output / "last.pt"), protocol_sha256=sha(output / "protocol.json"))
        dump(output / "run.json", state)
    except BaseException as exc:
        state.update(status="failed", failed_at=datetime.now(UTC).isoformat(),
                     error={"type": type(exc).__name__, "message": str(exc)})
        dump(output / "run.json", state)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preflight", "train"))
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--foda-data", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--coco-cache", type=Path,
                        default=Path.home() / ".cache/torch/hub/checkpoints" / COCO_FILENAME)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    foda = args.foda_data or args.project_root / "datasets/derived/v0.8/foda_grouped_v1"
    review = args.review or foda / "manual_review.json"
    receipt = preflight(args.project_root, foda, review, args.coco_cache)
    require(not args.output.exists(), "Refusing to overwrite output")
    if args.command == "preflight":
        dump(args.output, receipt)
        print(json.dumps({"status": "passed", "training": len(receipt["training"]),
                          "validation": len(receipt["validation"]), "held_back_read": False,
                          "torch_loaded": False, "output": str(args.output)}))
    else:
        train(receipt, args.output)


if __name__ == "__main__":
    main()
