"""Packaged CPU-only worker for a fixed experimental detector checkpoint.

No torch import occurs until predict() is called. Model construction requests
neither detector nor backbone pretrained weights; loading never downloads them.
This module performs one prediction and exits. It has no order/release logic.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageOps

CLASSES = {1: "bolt", 2: "nut"}
ARCHITECTURE = "fasterrcnn_mobilenet_v3_large_320_fpn"


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def frozen_threshold(state):
    threshold = state["selected"]["threshold"]
    if type(threshold) not in (int, float) or not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("Invalid frozen threshold")
    if state["config"]["classes"] != CLASSES or state["config"]["model"] != ARCHITECTURE:
        raise ValueError("Unsupported checkpoint")
    return float(threshold)


def build_model(config):
    """Restore the training architecture on CPU, without any downloaded weights."""
    import torch
    from torchvision.models.detection import fasterrcnn_mobilenet_v3_large_320_fpn
    from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
    from torchvision.ops.misc import FrozenBatchNorm2d

    if config["model"] != ARCHITECTURE or config["classes"] != CLASSES:
        raise ValueError("Unsupported checkpoint architecture/classes")
    for key in ("min_size", "max_size"):
        if type(config.get(key)) is not int or not 32 <= config[key] <= 4096:
            raise ValueError("Invalid checkpoint image size")
    if config["min_size"] > config["max_size"]:
        raise ValueError("Invalid checkpoint resize order")
    model = fasterrcnn_mobilenet_v3_large_320_fpn(
        weights=None, weights_backbone=None, progress=False,
        min_size=config["min_size"], max_size=config["max_size"],
        box_score_thresh=0.05, box_nms_thresh=0.5, box_detections_per_img=100,
    )

    def replace_batch_norm(module):
        for name, child in module.named_children():
            if isinstance(child, torch.nn.BatchNorm2d):
                setattr(module, name, FrozenBatchNorm2d(child.num_features, eps=child.eps))
            else:
                replace_batch_norm(child)

    replace_batch_norm(model)
    model.roi_heads.box_predictor = FastRCNNPredictor(model.roi_heads.box_predictor.cls_score.in_features, 3)
    return model


def summarize_predictions(labels, boxes, scores, threshold, image_size):
    """Same count and box contract as the original standalone prediction CLI."""
    if len(labels) != len(boxes) or len(labels) != len(scores):
        raise ValueError("Model output lengths differ")
    if type(threshold) not in (int, float) or not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("Invalid frozen threshold")
    width, height = image_size
    counts = {"bolt": 0, "nut": 0, "washer": None, "bracket": None}
    predictions = []
    for label, box, score in zip(labels, boxes, scores):
        if type(label) is not int or label not in CLASSES:
            raise ValueError("Unknown predicted class")
        if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError("Invalid predicted score")
        if (not isinstance(box, (list, tuple)) or len(box) != 4
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in box)):
            raise ValueError("Invalid predicted box")
        if not 0 <= box[0] < box[2] <= width or not 0 <= box[1] < box[3] <= height:
            raise ValueError("Predicted box outside image")
        retained = score >= threshold
        counts[CLASSES[label]] += int(retained)
        predictions.append({"label": label, "class_name": CLASSES[label], "bbox_xyxy": list(box),
                            "score": float(score), "retained_at_frozen_threshold": retained})
    return {"predictions": predictions, "counts": counts, "unsupported_classes": ["washer", "bracket"],
            "decision": None, "threshold": threshold, "threshold_comparison": "score >= threshold"}


def predict(checkpoint, image_path):
    import torch
    from torchvision.transforms.functional import pil_to_tensor

    torch.set_num_threads(4)
    checkpoint, image_path = Path(checkpoint).resolve(), Path(image_path).resolve()
    checkpoint_sha = sha(checkpoint)
    state = torch.load(checkpoint, map_location="cpu", weights_only=True)
    if sha(checkpoint) != checkpoint_sha:
        raise ValueError("Checkpoint changed while loading")
    threshold = frozen_threshold(state)
    model = build_model(state["config"])
    model.load_state_dict(state["model"], strict=True)
    model.to("cpu")
    model.eval()
    image_sha = sha(image_path)
    with Image.open(image_path) as original:
        encoded_size = list(original.size)
        exif_orientation = original.getexif().get(274)
        image = ImageOps.exif_transpose(original).convert("RGB")
        image.load()
    if sha(image_path) != image_sha:
        raise ValueError("Image changed while decoding")
    tensor = pil_to_tensor(image).float() / 255.0
    started = time.perf_counter()
    with torch.inference_mode():
        output = model([tensor])[0]
        output = {key: value.cpu() for key, value in output.items()}
    seconds = time.perf_counter() - started
    summary = summarize_predictions(output["labels"].tolist(), output["boxes"].tolist(),
                                    output["scores"].tolist(), threshold, image.size)
    return {
        "schema": "kitguard.public-detector.single-photo.v1", "status": "experimental_prediction",
        "created_at": datetime.now(UTC).isoformat(), "image": str(image_path), "source_sha256": image_sha,
        "image_size": list(image.size), "encoded_image_size": encoded_size, "size_order": "width,height",
        "source_exif_orientation": exif_orientation, "exif_transpose_applied": True,
        "coordinate_frame": "absolute pixel xyxy in EXIF-oriented RGB image; origin upper-left; x right, y down",
        "checkpoint": str(checkpoint), "checkpoint_sha256": checkpoint_sha, "checkpoint_epoch": state["epoch"],
        "model": state["config"]["model"], "training_data_fingerprint": state["config"].get("data_fingerprint"),
        "device": "cpu", "torch": str(torch.__version__), "inference_seconds": seconds,
        "threshold_source": "checkpoint.selected.threshold, chosen on validation; no order or override input",
        "model_return_filter": "All model-returned boxes after score floor 0.05, NMS 0.5 and maximum 100 detections",
        "latency_scope": "CPU model preprocessing/inference/postprocessing; excludes model load and file decode",
        "prediction_script_sha256": sha(Path(__file__)), **summary,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.output.exists() or args.output.is_symlink():
            raise ValueError("Output already exists")
        result = predict(args.checkpoint, args.image)
        content = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(content)
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, ImportError):
        parser.exit(1, "CPU detector unavailable or prediction invalid\n")


if __name__ == "__main__":
    main()
