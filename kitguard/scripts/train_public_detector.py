"""Isolated public bolt/nut experiment. Does not load or change the KitGuard app.

Train/threshold selection use train/val only. Run `evaluate` once after selecting
the best checkpoint; it records all test predictions and the frozen threshold.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import random
import shutil
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import torch
import torchvision
from PIL import Image
from public_detector_metrics import evaluate, select_threshold
from torch.utils.data import DataLoader, Dataset
from torchvision.models.detection import (
    FasterRCNN_MobileNet_V3_Large_320_FPN_Weights,
    fasterrcnn_mobilenet_v3_large_320_fpn,
)
from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
from torchvision.ops.misc import FrozenBatchNorm2d
from torchvision.transforms.functional import pil_to_tensor

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "datasets/derived/public_detector_v1"
CLASSES = {1: "bolt", 2: "nut"}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dump(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def fingerprint(data):
    return {name: sha(data / name) for name in ("manifest.json", "train.json", "val.json", "test.json")}


def sync(device):
    if device.type == "mps":
        torch.mps.synchronize()
    elif device.type == "cuda":
        torch.cuda.synchronize(device)


def choose_device(name):
    if name == "auto":
        name = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
    if name == "mps" and not torch.backends.mps.is_available():
        raise ValueError("MPS is unavailable")
    if name == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA is unavailable; install a matching NVIDIA PyTorch build on the GPU host")
    return torch.device(name)


class ScrewsDataset(Dataset):
    def __init__(self, path, augment=False):
        data = json.loads(Path(path).read_text())
        if {c["id"]: c["name"] for c in data["categories"]} != CLASSES:
            raise ValueError("Only background/bolt/nut are supported")
        self.images = data["images"]
        self.annotations = defaultdict(list)
        self.augment = augment
        for ann in data["annotations"]:
            self.annotations[ann["image_id"]].append(ann)
        for image in self.images:
            file = ROOT / image["file_name"]
            if not file.is_file() or sha(file) != image["source_sha256"]:
                raise ValueError(f"Source image missing/modified: {file}")

    def __len__(self):
        return len(self.images)

    def __getitem__(self, index):
        record = self.images[index]
        with Image.open(ROOT / record["file_name"]) as image:
            tensor = pil_to_tensor(image.convert("RGB")).float() / 255.0
        annotations = self.annotations[record["id"]]
        boxes = torch.tensor(
            [
                [a["bbox"][0], a["bbox"][1], a["bbox"][0] + a["bbox"][2], a["bbox"][1] + a["bbox"][3]]
                for a in annotations
            ],
            dtype=torch.float32,
        ).reshape(-1, 4)
        labels = torch.tensor([a["category_id"] for a in annotations], dtype=torch.int64)
        if self.augment and random.random() < 0.5:
            tensor = tensor.flip(-1)
            boxes[:, [0, 2]] = tensor.shape[-1] - boxes[:, [2, 0]]
        if self.augment and random.random() < 0.5:
            tensor = tensor.flip(-2)
            boxes[:, [1, 3]] = tensor.shape[-2] - boxes[:, [3, 1]]
        return tensor, {"boxes": boxes, "labels": labels, "image_id": torch.tensor(record["id"])}


def collate(batch):
    return tuple(zip(*batch))


def build_model(config, pretrained):
    weights = FasterRCNN_MobileNet_V3_Large_320_FPN_Weights.COCO_V1 if pretrained else None
    model = fasterrcnn_mobilenet_v3_large_320_fpn(
        weights=weights,
        weights_backbone=None,
        progress=False,
        min_size=config["min_size"],
        max_size=config["max_size"],
        box_score_thresh=0.05,
        box_nms_thresh=0.5,
        box_detections_per_img=100,
    )
    if not pretrained:
        # Torchvision otherwise chooses ordinary BN when no weights are requested.
        # Match the COCO-initialized model exactly before strict checkpoint loading.
        def freeze_batch_norm(module):
            for name, child in module.named_children():
                if isinstance(child, torch.nn.BatchNorm2d):
                    setattr(module, name, FrozenBatchNorm2d(child.num_features, eps=child.eps))
                else:
                    freeze_batch_norm(child)

        freeze_batch_norm(model)
    model.roi_heads.box_predictor = FastRCNNPredictor(model.roi_heads.box_predictor.cls_score.in_features, 3)
    # Preserve the exact frozen parameter set on resume without pretrained weights.
    if "trainable_parameters" in config:
        trainable = set(config["trainable_parameters"])
        for name, parameter in model.named_parameters():
            parameter.requires_grad_(name in trainable)
    return model


@torch.inference_mode()
def predict(model, dataset, device):
    model.eval()
    records = []
    for index in range(len(dataset)):
        image, target = dataset[index]
        sync(device)
        started = time.perf_counter()
        output = model([image.to(device)])[0]
        output = {key: value.cpu() for key, value in output.items()}
        sync(device)
        seconds = time.perf_counter() - started
        records.append(
            {
                "image_id": int(target["image_id"]),
                "file_name": dataset.images[index]["file_name"],
                "ground_truth": [
                    {"label": int(label), "box": box.tolist()}
                    for label, box in zip(target["labels"], target["boxes"])
                ],
                "predictions": [
                    {"label": int(label), "box": box.tolist(), "score": float(score)}
                    for label, box, score in zip(output["labels"], output["boxes"], output["scores"])
                ],
                "inference_seconds": seconds,
            }
        )
    return records


def rank(metrics):
    mae = metrics["count_mae_per_class"]
    return (metrics["exact_count_accuracy"], -sum(mae.values()) / len(mae), metrics["f1"])


def checkpoint(path, model, optimizer, scheduler, epoch, config, selected, best_rank, generator):
    # CPU tensors allow torch.load(map_location='cpu', weights_only=True) on another host.
    state = {
        "model": {k: v.detach().cpu() for k, v in model.state_dict().items()},
        "optimizer": optimizer.state_dict(),
        "scheduler": scheduler.state_dict(),
        "epoch": epoch,
        "config": config,
        "selected": selected,
        "best_rank": best_rank,
        "torch_rng": torch.get_rng_state(),
        "python_rng": random.getstate(),
        "loader_rng": generator.get_state(),
        "device_rng": (
            torch.mps.get_rng_state()
            if next(model.parameters()).device.type == "mps"
            else torch.cuda.get_rng_state()
            if next(model.parameters()).device.type == "cuda"
            else None
        ),
    }
    # Optimizer tensors may be accelerator tensors; serialization is portable via map_location.
    temporary = path.with_suffix(".tmp")
    torch.save(state, temporary)
    temporary.replace(path)


def train(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    device = choose_device(args.device)
    torch.set_num_threads(args.threads)
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    generator = torch.Generator().manual_seed(args.seed)
    data = args.data.resolve()
    config = {
        "model": "fasterrcnn_mobilenet_v3_large_320_fpn",
        "min_size": args.min_size,
        "max_size": args.max_size,
        "classes": CLASSES,
        "uncovered_classes": ["washer", "bracket"],
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "seed": args.seed,
        "learning_rate": args.lr,
        "momentum": 0.9,
        "weight_decay": 0.0005,
        "lr_step_epoch": args.lr_step,
        "lr_gamma": 0.1,
        "warmup_steps": 100,
        "augmentation": "independent horizontal/vertical flip p=0.5, training only",
        "thresholds": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
        "selection": "validation exact two-class count, then count MAE, then detection F1",
        "data_fingerprint": fingerprint(data),
        "device": str(device),
        "torch": str(torch.__version__),
        "torchvision": str(torchvision.__version__),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "started_at": datetime.now(UTC).isoformat(),
        "threads": args.threads,
        "mps_fallback": os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK", "0"),
        "precision": "float32",
        "resume_from": str(args.resume.resolve()) if args.resume else None,
        "note": "Same-source public data only. No claim about field accuracy, SKU, washer or bracket.",
    }
    previous = None
    if args.resume:
        previous = torch.load(args.resume, map_location="cpu", weights_only=True)
        old = previous["config"]
        for key in (
            "data_fingerprint",
            "min_size",
            "max_size",
            "batch_size",
            "seed",
            "learning_rate",
            "lr_step_epoch",
            "momentum",
            "weight_decay",
            "augmentation",
            "model",
            "classes",
            "thresholds",
            "selection",
            "lr_gamma",
            "warmup_steps",
            "precision",
        ):
            if old[key] != config[key]:
                raise ValueError(f"Resume configuration mismatch: {key}")
        config["trainable_parameters"] = old["trainable_parameters"]
    # Save the protocol before downloading weights or training.
    dump(output / "protocol.json", config)
    source_dir = output / "source"
    source_dir.mkdir()
    for name in ("train_public_detector.py", "public_detector_metrics.py", "prepare_public_detector_data.py"):
        shutil.copy2(ROOT / "scripts" / name, source_dir / name)
    config["source_sha256"] = {p.name: sha(p) for p in source_dir.iterdir()}
    print(json.dumps({"event": "loading", "device": str(device), "output": str(output)}), flush=True)
    model = build_model(config, pretrained=previous is None)
    config["trainable_parameters"] = [n for n, p in model.named_parameters() if p.requires_grad]
    weights = FasterRCNN_MobileNet_V3_Large_320_FPN_Weights.COCO_V1
    config["pretrained_url"] = weights.url
    if previous:
        config["pretrained_sha256"] = previous["config"].get("pretrained_sha256")
    else:
        config["pretrained_sha256"] = sha(Path(torch.hub.get_dir()) / "checkpoints" / Path(weights.url).name)
    model.to(device)
    optimizer = torch.optim.SGD(
        [p for p in model.parameters() if p.requires_grad], lr=args.lr, momentum=0.9, weight_decay=0.0005
    )
    scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=args.lr_step, gamma=0.1)
    start_epoch, best_rank = 1, (-1.0, -float("inf"), -1.0)
    if previous:
        model.load_state_dict(previous["model"])
        optimizer.load_state_dict(previous["optimizer"])
        scheduler.load_state_dict(previous["scheduler"])
        start_epoch = previous["epoch"] + 1
        if args.epochs < start_epoch:
            raise ValueError("--epochs is the total target epoch and must exceed the checkpoint epoch")
        best_rank = tuple(previous["best_rank"])
        torch.set_rng_state(previous["torch_rng"])
        random.setstate(previous["python_rng"])
        generator.set_state(previous["loader_rng"])
        if previous["config"]["device"] == str(device) and previous["device_rng"] is not None:
            if device.type == "mps":
                torch.mps.set_rng_state(previous["device_rng"])
            elif device.type == "cuda":
                torch.cuda.set_rng_state(previous["device_rng"])
        # Preserve the earlier best model if no later epoch improves it.
        prior_best = args.resume.parent / "best.pt"
        if not prior_best.is_file():
            raise ValueError("Resume needs sibling best.pt to preserve previous model selection")
        prior_best_state = torch.load(prior_best, map_location="cpu", weights_only=True)
        for key in (
            "data_fingerprint",
            "model",
            "min_size",
            "max_size",
            "classes",
            "thresholds",
            "selection",
            "trainable_parameters",
        ):
            if prior_best_state["config"][key] != config[key]:
                raise ValueError(f"Prior best checkpoint configuration mismatch: {key}")
        if (
            prior_best_state["epoch"] > previous["epoch"]
            or rank(prior_best_state["selected"]["metrics"]) != best_rank
        ):
            raise ValueError("Prior best checkpoint does not match the saved selection history")
        shutil.copy2(prior_best, output / "best.pt")
        for name in ("best_validation_predictions.json", "best_validation_metrics.json"):
            if (args.resume.parent / name).is_file():
                shutil.copy2(args.resume.parent / name, output / name)
    dump(output / "protocol.json", config)
    training = ScrewsDataset(data / "train.json", augment=True)
    validation = ScrewsDataset(data / "val.json")
    loader = DataLoader(
        training,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=0,
        collate_fn=collate,
        generator=generator,
    )
    total_started = time.perf_counter()
    for epoch in range(start_epoch, args.epochs + 1):
        model.train()
        losses = []
        epoch_started = time.perf_counter()
        for step, (images, targets) in enumerate(loader, 1):
            iteration = (epoch - 1) * len(loader) + step
            if iteration <= config["warmup_steps"]:
                for group in optimizer.param_groups:
                    group["lr"] = args.lr * (0.01 + 0.99 * iteration / config["warmup_steps"])
            images = [image.to(device) for image in images]
            targets = [{k: v.to(device) for k, v in target.items()} for target in targets]
            loss_dict = model(images, targets)
            loss = sum(loss_dict.values())
            value = float(loss.detach())
            if not math.isfinite(value):
                raise RuntimeError(f"Non-finite loss at epoch {epoch}, step {step}: {value}")
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 10.0)
            if not math.isfinite(float(norm)):
                raise RuntimeError("Non-finite gradient")
            optimizer.step()
            losses.append(value)
            if step == 1 or step % 20 == 0 or step == len(loader):
                print(
                    json.dumps(
                        {
                            "event": "train",
                            "epoch": epoch,
                            "step": step,
                            "steps": len(loader),
                            "loss": value,
                            "elapsed_seconds": round(time.perf_counter() - epoch_started, 2),
                        }
                    ),
                    flush=True,
                )
        scheduler.step()
        records = predict(model, validation, device)
        selected = select_threshold(records, config["thresholds"])
        metrics = selected["metrics"]
        score = rank(metrics)
        improved = score > best_rank
        if improved:
            best_rank = score
        checkpoint(
            output / "last.pt", model, optimizer, scheduler, epoch, config, selected, best_rank, generator
        )
        if improved:
            shutil.copy2(output / "last.pt", output / "best.pt")
            dump(output / "best_validation_predictions.json", records)
            dump(output / "best_validation_metrics.json", selected)
        row = {
            "epoch": epoch,
            "mean_train_loss": sum(losses) / len(losses),
            "threshold": selected["threshold"],
            "validation": metrics,
            "selected_best": improved,
            "epoch_seconds": time.perf_counter() - epoch_started,
            "elapsed_seconds": time.perf_counter() - total_started,
        }
        with (output / "history.jsonl").open("a") as handle:
            handle.write(json.dumps(row, allow_nan=False) + "\n")
        print(json.dumps({"event": "epoch_complete", **row}), flush=True)
    best = torch.load(output / "best.pt", map_location="cpu", weights_only=True)
    dump(
        output / "training_summary.json",
        {
            "status": "complete",
            "epochs_completed": args.epochs,
            "best_epoch": best["epoch"],
            "threshold": best["selected"]["threshold"],
            "validation": best["selected"]["metrics"],
            "best_checkpoint_sha256": sha(output / "best.pt"),
            "elapsed_seconds": time.perf_counter() - total_started,
            "test_evaluated": False,
            "completed_at": datetime.now(UTC).isoformat(),
        },
    )


def final_evaluate(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    device = choose_device(args.device)
    torch.set_num_threads(args.threads)
    state = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    config = state["config"]
    if fingerprint(args.data.resolve()) != config["data_fingerprint"]:
        raise ValueError("Data changed since training")
    dump(
        output / "evaluation_protocol.json",
        {
            "checkpoint_sha256": sha(args.checkpoint),
            "frozen_threshold": state["selected"]["threshold"],
            "split": "test",
            "device": str(device),
            "source_sha256": {
                name: sha(ROOT / "scripts" / name)
                for name in ("train_public_detector.py", "public_detector_metrics.py")
            },
        },
    )
    model = build_model(config, pretrained=False)
    model.load_state_dict(state["model"])
    model.to(device)
    records = predict(model, ScrewsDataset(args.data / "test.json"), device)
    metrics = evaluate(records, state["selected"]["threshold"])
    dump(output / "predictions.json", records)
    result = {
        "metrics": metrics,
        "threshold": state["selected"]["threshold"],
        "epoch": state["epoch"],
        "checkpoint_sha256": sha(args.checkpoint),
        "data_fingerprint": config["data_fingerprint"],
        "device": str(device),
        "torch": str(torch.__version__),
        "torchvision": str(torchvision.__version__),
        "scope": "22 same-acquisition-domain public images; bolt/nut only; not COCO mAP or field results",
        "latency_scope": "single-image tensor transfer, model preprocessing/inference/postprocessing and CPU output; excludes file decode and app workflow; no warmup",
        "created_at": datetime.now(UTC).isoformat(),
    }
    dump(output / "metrics.json", result)
    print(json.dumps(result, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("train", "evaluate"):
        command = sub.add_parser(name)
        command.add_argument("--data", type=Path, default=DEFAULT_DATA)
        command.add_argument(
            "--output", type=Path, required=True, help="New directory; existing directories refused"
        )
        command.add_argument("--device", choices=("auto", "mps", "cuda", "cpu"), default="auto")
        command.add_argument("--threads", type=int, default=6)
        if name == "train":
            command.add_argument("--epochs", type=int, default=12)
            command.add_argument("--batch-size", type=int, default=2)
            command.add_argument("--min-size", type=int, default=640)
            command.add_argument("--max-size", type=int, default=960)
            command.add_argument("--lr", type=float, default=0.005)
            command.add_argument("--lr-step", type=int, default=8)
            command.add_argument("--seed", type=int, default=20260930)
            command.add_argument("--resume", type=Path)
        else:
            command.add_argument("--checkpoint", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "train":
        if min(args.epochs, args.batch_size, args.min_size, args.max_size, args.lr_step, args.threads) <= 0:
            parser.error("Sizes, epochs, threads and lr-step must be positive")
        if not math.isfinite(args.lr) or args.lr <= 0 or args.max_size < args.min_size:
            parser.error("Invalid learning rate or resize dimensions")
        train(args)
    else:
        final_evaluate(args)


if __name__ == "__main__":
    main()
