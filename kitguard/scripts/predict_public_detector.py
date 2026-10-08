"""Run a frozen bolt/nut experiment checkpoint on one new photograph.

This CLI is independent of the production app. It cannot accept an order,
adjust the validation-selected threshold, or make a release/safety decision.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageOps

CLASSES = {1: "bolt", 2: "nut"}
UNSUPPORTED = ["washer", "bracket"]


def frozen_threshold(state: dict) -> float:
    threshold = state["selected"]["threshold"]
    if type(threshold) not in (int, float) or not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("Checkpoint selected.threshold must be finite and in [0,1]")
    if state["config"]["classes"] != CLASSES:
        raise ValueError("Checkpoint must use class 1=bolt and class 2=nut")
    if state["config"]["model"] != "fasterrcnn_mobilenet_v3_large_320_fpn":
        raise ValueError("Unsupported checkpoint architecture")
    return float(threshold)


def oriented_rgb(path: Path) -> tuple[Image.Image, dict]:
    with Image.open(path) as original:
        encoded_size = list(original.size)
        exif_orientation = original.getexif().get(274)
        rgb = ImageOps.exif_transpose(original).convert("RGB")
        rgb.load()
    return rgb, {
        "encoded_image_size": encoded_size,
        "image_size": list(rgb.size),
        "size_order": "width,height",
        "source_exif_orientation": exif_orientation,
        "exif_transpose_applied": True,
        "coordinate_frame": "absolute pixel xyxy in EXIF-oriented RGB image; origin upper-left; x right, y down",
    }


def summarize_predictions(labels: list, boxes: list, scores: list, threshold: float,
                          image_size: tuple[int, int]) -> dict:
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
            raise ValueError("Predicted box outside oriented image or without positive area")
        retained = score >= threshold
        if retained:
            counts[CLASSES[label]] += 1
        predictions.append({"label": label, "class_name": CLASSES[label], "bbox_xyxy": list(box),
                            "score": float(score), "retained_at_frozen_threshold": retained})
    return {"predictions": predictions, "counts": counts, "unsupported_classes": UNSUPPORTED,
            "decision": None, "threshold": threshold, "threshold_comparison": "score >= threshold"}


def predict_one(checkpoint: Path, image: Path, device_name: str) -> dict:
    # Lazy imports keep pure processing tests independent of torch/device state.
    import torch
    from torchvision.transforms.functional import pil_to_tensor
    from train_public_detector import build_model, choose_device, sha, sync

    checkpoint = checkpoint.resolve()
    image = image.resolve()
    checkpoint_sha = sha(checkpoint)
    state = torch.load(checkpoint, map_location="cpu", weights_only=True)
    if sha(checkpoint) != checkpoint_sha:
        raise ValueError("Checkpoint changed while loading; retry with a frozen checkpoint")
    threshold = frozen_threshold(state)
    model = build_model(state["config"], pretrained=False)
    model.load_state_dict(state["model"], strict=True)
    device = choose_device(device_name)
    model.to(device)
    model.eval()
    image_sha = sha(image)
    rgb, image_metadata = oriented_rgb(image)
    if sha(image) != image_sha:
        raise ValueError("Source image changed while decoding")
    tensor = pil_to_tensor(rgb).float() / 255.0
    sync(device)
    started = time.perf_counter()
    with torch.inference_mode():
        raw = model([tensor.to(device)])[0]
        raw = {name: value.cpu() for name, value in raw.items()}
        sync(device)
    seconds = time.perf_counter() - started
    summary = summarize_predictions(raw["labels"].tolist(), raw["boxes"].tolist(), raw["scores"].tolist(),
                                    threshold, rgb.size)
    return {
        "schema": "kitguard.public-detector.single-photo.v1",
        "status": "experimental_prediction", "created_at": datetime.now(UTC).isoformat(),
        "image": str(image), "source_sha256": image_sha, **image_metadata,
        "checkpoint": str(checkpoint), "checkpoint_sha256": checkpoint_sha,
        "checkpoint_epoch": state["epoch"], "model": state["config"]["model"],
        "training_data_fingerprint": state["config"].get("data_fingerprint"),
        "device": str(device), "torch": str(torch.__version__),
        "threshold_source": "checkpoint.selected.threshold, chosen on validation; no order or override input",
        "model_return_filter": "All model-returned boxes after score floor 0.05, NMS 0.5 and maximum 100 detections",
        "inference_seconds": seconds,
        "latency_scope": "tensor device transfer, model preprocessing/inference/postprocessing and CPU output; excludes load/decode; no warmup",
        **summary,
        "note": "Experimental public-data bolt/nut detector; not production four-class verification, SKU identification or a safety/release decision. Washer and bracket are unknown, not zero.",
        "prediction_script_sha256": sha(Path(__file__)),
    }


def write_result(output: Path, result: dict) -> None:
    serialized = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(serialized)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", choices=("auto", "cpu", "mps", "cuda"), default="auto")
    args = parser.parse_args()
    try:
        if args.output.exists() or args.output.is_symlink():
            raise ValueError(f"Refuse to overwrite existing output: {args.output}")
        result = predict_one(args.checkpoint, args.image, args.device)
        write_result(args.output, result)
    except (ValueError, KeyError, OSError, TypeError, RuntimeError) as exc:
        parser.exit(1, f"Prediction refused: {exc}\n")
    print(json.dumps({"output": str(args.output.resolve()), "counts": result["counts"],
                      "threshold": result["threshold"], "decision": None}, ensure_ascii=False))


if __name__ == "__main__":
    main()
