"""Fixed MANTA identity-component training; no product imports or automatic downloads.

preflight hashes approved prepared inputs without decoding them or importing Torch.
model-contract is a separate CPU-only original-weight/synthetic-tensor check.
train requires an exact preflight and a separate root approval. No search/resume/retry.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
import platform
import random
import re
import shutil
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = "scripts/v08/train_manta_classifier.py"
TEST = "tests/test_manta_classifier_training_v08.py"
FREEZE = "docs/v0.8/manta_classifier_freeze_v1/freeze.json"
FREEZE_SHA = "226f739d011c5f4095888251b572663fd2c12a485c6b48d8c36e206553111f9e"
PREPARER = "scripts/v08/prepare_manta_classifier.py"
WEIGHT_SHA = "907ea3f91ff92242bc1baea8049276a3e76bca48ce7560bd268cc029f37977b5"
WEIGHT_BYTES = 77844807
CLASSES = {"nut": 0, "yellow_green_washer": 1}
CONFIG = {"epochs": 10, "optimizer": "SGD", "learning_rate": .01, "momentum": .9,
          "weight_decay": .0001, "batch_size": 32, "seed": 20261002, "device": "mps",
          "precision": "float32", "workers": 0, "augmentation": "none", "probability_threshold": .9,
          "normalization_mean": [.485, .456, .406], "normalization_std": [.229, .224, .225]}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for part in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def read(path):
    return json.loads(Path(path).read_text())


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def now():
    return datetime.now(UTC).isoformat()


def safe_path(base, relative):
    base = Path(base).resolve()
    require(isinstance(relative, str) and not Path(relative).is_absolute() and ".." not in Path(relative).parts,
            "Unsafe relative artifact path")
    path = base / relative
    require(path.resolve().is_relative_to(base) and not any(p.is_symlink() for p in [path, *path.parents] if p != base.parent),
            "Symlink or path escape")
    require(path.is_file(), "Missing bound file")
    return path


def runtime():
    """Read installed files/version metadata only; never import model libraries."""
    result = {"python": sys.version, "executable": str(Path(sys.executable).resolve()),
              "platform": platform.platform(), "packages": {}, "files": {}}
    for package, module, names in (
        ("torch", "torch", ["nn/modules/linear.py", "nn/modules/module.py", "optim/sgd.py", "nn/functional.py"]),
        ("torchvision", "torchvision", ["models/mobilenetv3.py", "models/detection/backbone_utils.py",
                                        "models/detection/faster_rcnn.py", "models/_utils.py", "ops/misc.py",
                                        "transforms/functional.py"]),
        ("Pillow", "PIL", ["Image.py", "PngImagePlugin.py"]),
    ):
        result["packages"][package] = importlib.metadata.version(package)
        base = Path(importlib.util.find_spec(module).origin).parent
        files = {base / name for name in names}
        files.update(base.glob("*.so"))
        files.update((base / "lib").glob("*.dylib"))
        for path in sorted(files):
            result["files"][str(path.resolve())] = sha(path)
    return result


def preparation_module(root):
    freeze_path = Path(root) / FREEZE
    require(sha(freeze_path) == FREEZE_SHA, "Unexpected preparation freeze")
    freeze = read(freeze_path)
    for rel, expected in freeze["source_snapshot"].items():
        require(sha(safe_path(freeze_path.parent / "source_snapshot", rel)) == expected, "Frozen source changed")
    source = freeze_path.parent / "source_snapshot" / PREPARER
    spec = importlib.util.spec_from_file_location("frozen_manta_preparer", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    protocol = module.verify_freeze(root, freeze_path, FREEZE_SHA, require_snapshot=False)
    require({k: protocol["policy"]["training"][k] for k in CONFIG} == CONFIG, "Training policy mismatch")
    return module, protocol


def validate_layout(prepared, preparation_sha, rows, visual):
    require(visual["schema"] == "kitguard.v08.manta-classifier.visual-review.v1"
            and visual["status"] == "passed" and visual["training_authorized"] is False, "Layout review not passed")
    require(visual["reviewer"]["kind"] == "AI" and visual["reviewer"]["human_participants"] == 0,
            "Unexpected layout reviewer scope")
    for key, value in {"freeze_sha256": FREEZE_SHA, "preparation_sha256": preparation_sha,
                       "records_sha256": prepared["records_sha256"], "grouping_sha256": prepared["grouping_sha256"]}.items():
        require(visual[key] == value, f"Wrong layout binding: {key}")
    require(visual["sheets"] == prepared["qa_sheets"] and len(visual["sheets"]) == 6, "Sheet set differs")
    expected = {r["input_id"]: r for r in rows if r["visual_qa_selected"]}
    reviewed = visual["reviewed_records"]
    require(len(expected) == len(reviewed) == 36 and {r["input_id"] for r in reviewed} == set(expected), "Layout QA population differs")
    require(len({s["path"] for s in visual["sheets"]}) == 6
            and sorted(i for s in visual["sheets"] for i in s["record_ids"]) == sorted(expected), "Sheet coverage differs")
    for item in reviewed:
        row = expected[item["input_id"]]
        require(item["accepted"] is True and all(item[k] == row[k] for k in ("member_path", "role", "input_sha256")),
                "Layout rejected or input/role changed")


def validate_population(rows, protocol_records, grouped):
    require(len(rows) == len(protocol_records) == 1024, "Incomplete planned population")
    require(len({r["input_id"] for r in rows}) == 1024, "Duplicate input ID")
    for row, original in zip(rows, protocol_records, strict=True):
        require(all(row.get(k) == v for k, v in original.items()), "Prepared record differs from frozen selection")
        require(row["status"] == "prepared" and row["error"] is None and row["role"] in ("train", "validation"),
                "Failed/not_attempted/quarantined records cannot be silently dropped")
        require(row["author_split"] == "train" and row["author_condition"] == "good"
                and row["label"] == CLASSES[row["class_name"]], "Invalid author label/split")
        require(row["input_path"] == f"inputs/{row['input_id']}.png" and re.fullmatch(r"record-\d{4}", row["input_id"]), "Input name is not neutral")
        require(row["input_size"] == [224, 224] and row["source_mode"] == "RGB" and row["exif"] == {}
                and row["view_index"] == 0 and row["structural_layout_check"] == "passed", "Unsupported prepared image")
        require(not row["previously_exposed"] or row["role"] == "train", "Old exposure in validation")
    require(grouped["label_conflict_groups"] == 0, "Conflicting labels")
    groups = {g["group_id"]: g for g in grouped["groups"]}
    require(len(groups) == len(grouped["groups"]), "Duplicate group")
    require(sorted(i for g in groups.values() for i in g["members"]) == sorted(r["input_id"] for r in rows), "Group census mismatch")
    for row in rows:
        group = groups[row["final_group"]]
        require(row["input_id"] in group["members"] and row["role"] == group["role"], "Group crosses partitions")
    for name in CLASSES:
        for role, minimum in (("train", 256), ("validation", 64)):
            part = [r for r in rows if r["class_name"] == name and r["role"] == role]
            require(len(part) >= minimum and len({r["final_group"] for r in part}) >= 2, "Insufficient final partition; no replacement")


def verify_prepared(root, prepared_path, expected_sha, visual_path, visual_sha):
    root, prepared_path, visual_path = Path(root).resolve(), Path(prepared_path).resolve(), Path(visual_path).resolve()
    require(sha(prepared_path) == expected_sha and sha(visual_path) == visual_sha, "Preparation/QA SHA changed")
    module, protocol = preparation_module(root)
    prepared, visual, base = read(prepared_path), read(visual_path), prepared_path.parent
    require(prepared["schema"] == "kitguard.v08.manta-classifier.preparation.v1"
            and prepared["status"] == "prepared_pending_visual_review" and prepared["training_authorized"] is False,
            "Preparation is not eligible")
    require(prepared["freeze_sha256"] == FREEZE_SHA and prepared["protocol_sha256"] == read(root / FREEZE)["protocol_sha256"], "Wrong protocol binding")
    require(prepared["population"] == 1024 and prepared["status_counts"] == {"prepared": 1024}
            and prepared["adequate_partitions"] is True and not prepared["processing_error"]
            and not prepared["final_integrity_error"] and prepared["model_called"] is False
            and prepared["test_payloads_extracted"] == prepared["test_images_decoded"] == 0, "Incomplete/inconsistent preparation")
    for name in ("records", "grouping", "attempts"):
        suffix = ".jsonl" if name == "attempts" else ".json"
        require(sha(safe_path(base, name + suffix)) == prepared[name + "_sha256"], "Prepared artifact changed")
    rows, grouped = read(base / "records.json"), read(base / "grouping.json")
    validate_population(rows, protocol["records"], grouped)
    rebuilt = copy.deepcopy(rows)
    require(module.group_records(rebuilt) == grouped
            and [(r["role"], r["final_group"]) for r in rebuilt] == [(r["role"], r["final_group"]) for r in rows], "Duplicate groups not reproducible")
    require(dict(Counter(r["role"] for r in rows)) == prepared["role_counts"], "Role denominator differs")
    for row in rows:
        require(sha(safe_path(base, row["input_path"])) == row["input_sha256"], "Prepared image changed")
    for sheet in prepared["qa_sheets"]:
        require(sha(safe_path(base, sheet["path"])) == sheet["sha256"], "Layout sheet changed")
    validate_layout(prepared, expected_sha, rows, visual)
    weights = Path(protocol["weights"]["path"])
    require(weights.stat().st_size == WEIGHT_BYTES and sha(weights) == WEIGHT_SHA, "Wrong original COCO weights")
    return {"records": rows, "base": str(base), "weights": str(weights), "policy": protocol["policy"]["training"]}


def preflight(root, prepared, expected, visual, visual_sha, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    require(not output.exists(), "Preflight output exists")
    checked = verify_prepared(root, prepared, expected, visual, visual_sha)
    output.mkdir(parents=True)
    sources = {}
    for rel in (SCRIPT, TEST):
        target = output / "source_snapshot" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / rel, target)
        sources[rel] = sha(target)
        require(sources[rel] == sha(root / rel), "Source changed during preflight")
    plan = {"schema": "kitguard.v08.manta-classifier.training-plan.v1", "status": "prepared_not_authorized",
            "created_at_utc": now(), "project_root": str(root), "freeze_sha256": FREEZE_SHA,
            "preparation_path": str(Path(prepared).resolve()), "preparation_sha256": expected,
            "visual_review_path": str(Path(visual).resolve()), "visual_review_sha256": visual_sha,
            "source_snapshot": sources, "runtime": runtime(), "config": CONFIG, "classes": CLASSES,
            "weights_path": checked["weights"], "weights_sha256": WEIGHT_SHA, "input_base": checked["base"],
            "records": checked["records"], "validation_selection": "final epoch 10 only; each epoch complete fixed validation",
            "batch_order": "Python Random(seed) shuffled neutral training indices once per epoch; validation fixed order in batches32",
            "torch_imported": "torch" in sys.modules, "pixels_decoded": 0, "model_called": False,
            "production_change": False, "new_holdout_claim": False, "mps_bitwise_determinism_claim": False}
    write_new(output / "plan.json", plan)
    return {"plan": str(output / "plan.json"), "sha256": sha(output / "plan.json"), "model_called": False}


def validate_approval(plan_path, expected_sha, approval_path, approval_sha):
    require(sha(plan_path) == expected_sha and sha(approval_path) == approval_sha, "Plan/approval changed")
    plan, approval = read(plan_path), read(approval_path)
    require(plan["schema"] == "kitguard.v08.manta-classifier.training-plan.v1"
            and plan["status"] == "prepared_not_authorized" and set(plan["source_snapshot"]) == {SCRIPT, TEST}, "Unexpected plan schema or source set")
    require(approval["schema"] == "kitguard.v08.manta-classifier.training-approval.v1"
            and approval["status"] == "approved" and approval["authorized_by"] == "root", "Separate root approval required")
    for key, value in {"plan_sha256": expected_sha, "freeze_sha256": FREEZE_SHA,
                       "preparation_sha256": plan["preparation_sha256"], "visual_review_sha256": plan["visual_review_sha256"],
                       "training_source_sha256": plan["source_snapshot"][SCRIPT], "epochs": 10, "production_change": False}.items():
        require(approval[key] == value, f"Approval binding differs: {key}")
    require(plan["config"] == CONFIG and plan["classes"] == CLASSES and plan["freeze_sha256"] == FREEZE_SHA,
            "Wrong fixed training plan")
    return plan


def verify_plan(plan_path, plan):
    base = Path(plan_path).parent
    for rel, expected in plan["source_snapshot"].items():
        require(sha(safe_path(base / "source_snapshot", rel)) == expected, "Frozen training source changed")
    require(Path(__file__).resolve() == (base / "source_snapshot" / SCRIPT).resolve(), "Train only from preflight source snapshot")
    require(runtime() == plan["runtime"], "Training dependencies changed")
    checked = verify_prepared(plan["project_root"], plan["preparation_path"], plan["preparation_sha256"],
                              plan["visual_review_path"], plan["visual_review_sha256"])
    require(checked["records"] == plan["records"] and checked["weights"] == plan["weights_path"], "Prepared inputs differ")
    return checked


def score_row(row, prediction, forced=False):
    status = prediction["status"]
    if status == "failed":
        return "E", None
    if status == "not_attempted":
        return "N", None
    require(status == "ok", "Unknown prediction status")
    probabilities = prediction["probabilities"]
    require(isinstance(probabilities, list) and len(probabilities) == 2
            and all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1 for v in probabilities)
            and abs(sum(probabilities) - 1) < 1e-5, "Invalid probability vector")
    predicted = max(range(2), key=lambda i: probabilities[i])
    if not forced and probabilities[predicted] < CONFIG["probability_threshold"]:
        return "U", None
    return ("C" if predicted == row["label"] else "W"), predicted


def summarize(rows, predictions):
    require(len(rows) == len(predictions) and [r["input_id"] for r in rows] == [p["input_id"] for p in predictions], "Validation denominator/order differs")
    result = {}
    for panel, forced in (("threshold_0_9", False), ("forced_argmax", True)):
        counts = Counter({k: 0 for k in "CWUEN"})
        classes, groups = {}, defaultdict(list)
        for row, pred in zip(rows, predictions, strict=True):
            label, choice = score_row(row, pred, forced)
            counts[label] += 1
            group = groups[(row["class_name"], row["final_group"])]
            group.append(label)
            one = classes.setdefault(row["class_name"], {"denominator": 0, "CWUEN": {k: 0 for k in "CWUEN"},
                                                        "confusion": {"nut": 0, "yellow_green_washer": 0, "unknown": 0, "error": 0, "not_attempted": 0}})
            one["denominator"] += 1
            one["CWUEN"][label] += 1
            col = list(CLASSES)[choice] if choice is not None else {"U": "unknown", "E": "error", "N": "not_attempted"}[label]
            one["confusion"][col] += 1
        group_rows = [{"class_name": name, "group_id": gid, "denominator": len(items),
                       "CWUEN": {k: items.count(k) for k in "CWUEN"},
                       "correct_coverage": items.count("C") / len(items),
                       "coverage": (items.count("C") + items.count("W")) / len(items)} for (name, gid), items in sorted(groups.items())]
        for name, one in classes.items():
            values = [g for g in group_rows if g["class_name"] == name]
            one["group_count"] = len(values)
            one["group_macro_correct_coverage"] = sum(g["correct_coverage"] for g in values) / len(values)
            one["group_macro_coverage"] = sum(g["coverage"] for g in values) / len(values)
            one["record_correct_coverage"] = one["CWUEN"]["C"] / one["denominator"]
        result[panel] = {"denominator": len(rows), "CWUEN": dict(counts), "classes": classes, "groups": group_rows,
                         "coverage": (counts["C"] + counts["W"]) / len(rows) if rows else None}
    main = result["threshold_0_9"]
    result["continuation_gate"] = (set(main["classes"]) == set(CLASSES)
                                   and all(main["CWUEN"][k] == 0 for k in "WEN")
                                   and all(c["group_macro_correct_coverage"] >= .75 for c in main["classes"].values()))
    result["constant_identity_baselines"] = {name: {"C": sum(r["label"] == label for r in rows),
                                                          "W": sum(r["label"] != label for r in rows), "U": 0, "E": 0, "N": 0}
                                             for name, label in CLASSES.items()}
    result["production_promotion"] = False
    result["scope"] = "Author-train two-class component validation; proxy groups; 8 initial validation records seen only for layout QA; no physical/pretraining independence. Class-correlated geometry, aspect ratio, background and padding may provide shortcuts; internal scores do not establish cross-domain performance."
    return result


def tensor_digest(tensor):
    value = tensor.detach().cpu().contiguous()
    return hashlib.sha256(canonical({"shape": list(value.shape), "dtype": str(value.dtype)}).encode() + b"\0" + value.numpy().tobytes()).hexdigest()


def state_digest(module):
    return hashlib.sha256(canonical({k: tensor_digest(v) for k, v in sorted(module.state_dict().items())}).encode()).hexdigest()


def cpu_state(value):
    """Portable tensor evidence; optimizer momentum must not retain MPS storage."""
    if isinstance(value, dict):
        return {k: cpu_state(v) for k, v in value.items()}
    if isinstance(value, list):
        return [cpu_state(v) for v in value]
    if isinstance(value, tuple):
        return tuple(cpu_state(v) for v in value)
    return value.detach().cpu().clone() if hasattr(value, "detach") else value


def prediction_rows(rows):
    return [{**{k: r[k] for k in ("input_id", "input_sha256", "class_name", "label", "final_group")},
             "status": "not_attempted", "logits": None, "probabilities": None, "error": None} for r in rows]


def full_checkpoint(model, optimizer, plan_sha, epoch, path):
    import torch
    torch.save({"schema": "kitguard.v08.manta-classifier.full-checkpoint.v1", "epoch": epoch,
                "plan_sha256": plan_sha, "config": CONFIG, "classes": CLASSES,
                "original_coco_sha256": WEIGHT_SHA, "body_state_sha256": state_digest(model.body),
                "head_state_sha256": state_digest(model.head),
                "model_state_dict": cpu_state(model.state_dict()),
                "optimizer_state_dict": cpu_state(optimizer.state_dict())}, path)
    return {"path": Path(path).name, "sha256": sha(path), "epoch": epoch,
            "body_state_sha256": state_digest(model.body), "head_state_sha256": state_digest(model.head)}


def build_model(weights):
    import torch
    from torchvision.models.detection import fasterrcnn_mobilenet_v3_large_320_fpn
    from torchvision.ops.misc import FrozenBatchNorm2d
    require(Path(weights).stat().st_size == WEIGHT_BYTES and sha(weights) == WEIGHT_SHA, "Original COCO weights changed")
    original = fasterrcnn_mobilenet_v3_large_320_fpn(weights=None, weights_backbone=None, num_classes=91, progress=False)

    def replace_bn(module):
        for name, child in list(module.named_children()):
            if isinstance(child, torch.nn.BatchNorm2d):
                setattr(module, name, FrozenBatchNorm2d(child.num_features, eps=child.eps))
            else:
                replace_bn(child)
    replace_bn(original)
    original.load_state_dict(torch.load(weights, map_location="cpu", weights_only=True), strict=True)
    body = original.backbone.body
    for p in body.parameters():
        p.requires_grad_(False)

    class Classifier(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.body, self.head = body, torch.nn.Linear(960, 2)
            self.body.eval()

        def train(self, mode=True):
            super().train(mode)
            self.body.eval()
            return self

        def forward(self, images):
            require(not self.body.training, "Frozen backbone entered train mode")
            with torch.no_grad():
                features = self.body(images)
                require(isinstance(features, dict) and "1" in features, "Backbone lacks fixed output key1")
                last = features["1"]
                require(last.ndim == 4 and last.shape[0] == images.shape[0] and last.shape[1] == 960
                        and min(last.shape[2:]) > 0, "Backbone feature is not N x960xHxW")
                pooled = torch.nn.functional.adaptive_avg_pool2d(last, (1, 1)).flatten(1)
            return self.head(pooled)
    model = Classifier()
    require({name for name, p in model.named_parameters() if p.requires_grad} == {"head.weight", "head.bias"}, "Unexpected trainable parameters")
    return model


def input_tensor(base, row, tensor_hashes):
    import torch
    from PIL import Image
    from torchvision.transforms.functional import pil_to_tensor
    path = safe_path(base, row["input_path"])
    require(sha(path) == row["input_sha256"], "Prepared input changed")
    with Image.open(path) as image:
        require(image.format == "PNG" and image.mode == "RGB" and image.size == (224, 224)
                and not dict(image.getexif()), "Unexpected normalized input")
        pixels = pil_to_tensor(image)
    require(torch.equal(pixels[0], pixels[1]) and torch.equal(pixels[1], pixels[2]), "Input is not gray RGB")
    tensor = pixels.to(torch.float32) / 255
    tensor = (tensor - torch.tensor(CONFIG["normalization_mean"])[:, None, None]) / torch.tensor(CONFIG["normalization_std"])[:, None, None]
    fingerprint = tensor_digest(tensor)
    require(row["input_id"] not in tensor_hashes or tensor_hashes[row["input_id"]] == fingerprint, "Tensor changed across epochs")
    tensor_hashes[row["input_id"]] = fingerprint
    return tensor


def evaluate(model, rows, base, device, tensor_hashes, output):
    import torch
    predictions = prediction_rows(rows)
    model.eval()
    interruption = None
    with Path(output).open("x") as stream:
        for start in range(0, len(rows), CONFIG["batch_size"]):
            batch, results = rows[start:start + 32], predictions[start:start + 32]
            started = time.perf_counter()
            called = False
            try:
                images = torch.stack([input_tensor(base, row, tensor_hashes) for row in batch]).to(device)
                torch.mps.synchronize()
                called = True
                with torch.inference_mode():
                    logits = model(images)
                    require(logits.shape == (len(batch), 2) and torch.isfinite(logits).all().item(), "Invalid logits")
                    probabilities = logits.softmax(dim=1)
                torch.mps.synchronize()
                for result, values, probs in zip(results, logits.cpu().tolist(), probabilities.cpu().tolist(), strict=True):
                    result.update(status="ok", logits=values, probabilities=probs)
            except BaseException as error:  # noqa: BLE001 -- retain full denominator, do not retry
                for result in results:
                    result.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
                if not isinstance(error, Exception):
                    interruption = error
            finally:
                elapsed = time.perf_counter() - started
                for result in results:
                    result.update(batch_forward_started=called, batch_wall_seconds=elapsed, batch_size=len(batch))
                    stream.write(canonical(result) + "\n")
                stream.flush()
            if interruption:
                break
        # Not-attempted rows are explicitly retained in the same raw file.
        for result in predictions:
            if result["status"] == "not_attempted":
                stream.write(canonical(result) + "\n")
    return predictions, interruption


def model_contract(weights, output):
    """Only explicitly invoked after root code review; synthetic CPU tensor only."""
    import torch
    output = Path(output)
    require(not output.exists(), "Contract output exists")
    output.mkdir(parents=True)
    torch.manual_seed(CONFIG["seed"])
    result = {"schema": "kitguard.v08.manta-classifier.model-contract.v1", "status": "failed",
              "source_sha256": sha(__file__), "weights_sha256": sha(weights), "runtime": runtime(),
              "device": "cpu", "real_images": 0, "training_steps": 0}
    try:
        model = build_model(weights)
        before = state_digest(model.body)
        model.train()
        with torch.inference_mode():
            logits = model(torch.zeros((2, 3, 224, 224), dtype=torch.float32))
        require(logits.shape == (2, 2) and torch.isfinite(logits).all().item(), "Invalid synthetic logits")
        require(state_digest(model.body) == before and not model.body.training, "Frozen body/buffers changed")
        result.update(status="passed", output_shape=list(logits.shape), body_frozen=True,
                      body_state_sha256=before, trainable=[n for n, p in model.named_parameters() if p.requires_grad])
    except BaseException as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)}
        write_new(output / "contract.json", result)
        raise
    write_new(output / "contract.json", result)
    return result


def train(plan_path, expected, approval_path, approval_sha, output):
    begin_run = time.perf_counter()
    plan_path, output = Path(plan_path).resolve(), Path(output).resolve()
    plan = validate_approval(plan_path, expected, approval_path, approval_sha)
    require(not output.exists(), "Refusing existing training output")
    require(os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK", "0") == "0", "MPS fallback forbidden")
    output.mkdir(parents=True)
    shutil.copyfile(plan_path, output / "plan.json")
    shutil.copyfile(approval_path, output / "approval.json")
    validation = [r for r in plan["records"] if r["role"] == "validation"]
    training = [r for r in plan["records"] if r["role"] == "train"]
    final_predictions = prediction_rows(validation)
    result = {"schema": "kitguard.v08.manta-classifier.training-run.v1", "status": "running", "started_at_utc": now(),
              "plan_sha256": expected, "approval_sha256": approval_sha, "epochs_completed": 0,
              "training_count": len(training), "validation_count": len(validation), "model_initialization_started": False,
              "selected_epoch": None, "production_change": False, "human_participants": 0,
              "new_holdout_claim": False, "timing_scope": "This component run only; MPS not bitwise deterministic or concurrent baseline timing"}
    write_new(output / "started.json", result)
    tensor_hashes, stage, interrupted, model, body_before = {}, "preflight", None, None, None
    optimizer, history, initial_checkpoint = None, [], None
    try:
        checked = verify_plan(plan_path, plan)
        import torch
        require(torch.backends.mps.is_available(), "Pinned MPS device unavailable")
        random.seed(CONFIG["seed"])
        torch.manual_seed(CONFIG["seed"])
        torch.mps.manual_seed(CONFIG["seed"])
        rng = random.Random(CONFIG["seed"])
        stage = "model_initialization"
        result["model_initialization_started"] = True
        model = build_model(checked["weights"]).to("mps", dtype=torch.float32)
        body_before = state_digest(model.body)
        optimizer = torch.optim.SGD(model.head.parameters(), lr=.01, momentum=.9, weight_decay=.0001)
        require({id(p) for g in optimizer.param_groups for p in g["params"]} == {id(p) for p in model.head.parameters()}, "Optimizer includes backbone")
        initial_checkpoint = full_checkpoint(model, optimizer, expected, 0, output / "initial.pt")
        result["initial_checkpoint"] = initial_checkpoint
        for epoch in range(1, 11):
            stage = f"train_epoch_{epoch}"
            order = list(range(len(training)))
            rng.shuffle(order)
            attempts = [{"input_id": r["input_id"], "status": "not_attempted"} for r in training]
            model.train()
            losses = []
            try:
                with (output / f"epoch-{epoch:02}-batches.jsonl").open("x") as stream:
                    for start in range(0, len(order), 32):
                        ids = order[start:start + 32]
                        batch = [training[i] for i in ids]
                        record = {"epoch": epoch, "batch": start // 32, "input_ids": [r["input_id"] for r in batch], "status": "attempted"}
                        begin = time.perf_counter()
                        try:
                            images = torch.stack([input_tensor(checked["base"], r, tensor_hashes) for r in batch]).to("mps")
                            # Labels are a separate loss argument; they never reach image preprocessing/forward.
                            labels = torch.tensor([r["label"] for r in batch], dtype=torch.long, device="mps")
                            optimizer.zero_grad(set_to_none=True)
                            logits = model(images)
                            loss = torch.nn.functional.cross_entropy(logits, labels)
                            require(torch.isfinite(loss).item(), "Nonfinite training loss")
                            loss.backward()
                            optimizer.step()
                            torch.mps.synchronize()
                            value = float(loss.item())
                            losses.append((value, len(batch)))
                            record.update(status="trained", loss=value)
                            for i in ids:
                                attempts[i]["status"] = "trained"
                        except BaseException as error:
                            record.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
                            for i in ids:
                                attempts[i].update(status="failed_batch", error=record["error"])
                            raise
                        finally:
                            record["batch_wall_seconds"] = time.perf_counter() - begin
                            stream.write(canonical(record) + "\n")
                            stream.flush()
            finally:
                write_new(output / f"epoch-{epoch:02}-training-records.json", attempts)
            require(state_digest(model.body) == body_before, "Backbone parameters/buffers changed")
            stage = f"validation_epoch_{epoch}"
            preds, interruption = evaluate(model, validation, checked["base"], "mps", tensor_hashes,
                                           output / f"epoch-{epoch:02}-validation.jsonl")
            summary = summarize(validation, preds)
            write_new(output / f"epoch-{epoch:02}-metrics.json", {"epoch": epoch, "training_loss": sum(v*n for v,n in losses)/sum(n for _,n in losses), "validation": summary})
            # Per-epoch checkpoints store head/optimizer; initial/final also retain the complete frozen body.
            checkpoint = {"schema": "kitguard.v08.manta-classifier.head-checkpoint.v1", "epoch": epoch,
                          "plan_sha256": expected, "config": CONFIG, "classes": CLASSES, "body_state_sha256": body_before,
                          "original_coco_sha256": WEIGHT_SHA, "head_state_dict": {k: v.detach().cpu().clone() for k,v in model.head.state_dict().items()},
                          "optimizer_state_dict": cpu_state(optimizer.state_dict())}
            torch.save(checkpoint, output / f"epoch-{epoch:02}.pt")
            write_new(output / f"epoch-{epoch:02}-checkpoint.json", {"epoch": epoch, "sha256": sha(output / f"epoch-{epoch:02}.pt"), "scope": "head and CPU SGD state; complete body retained in initial/final checkpoints"})
            history.append({"epoch": epoch, "files": {
                filename: sha(output / filename) for filename in (
                    f"epoch-{epoch:02}-validation.jsonl", f"epoch-{epoch:02}-metrics.json",
                    f"epoch-{epoch:02}-training-records.json", f"epoch-{epoch:02}-batches.jsonl",
                    f"epoch-{epoch:02}.pt", f"epoch-{epoch:02}-checkpoint.json")}})
            if epoch == 10:
                final_predictions = preds
            if interruption:
                raise interruption
            require(all(p["status"] == "ok" for p in preds), "Validation failures retained; stop, no retry/epoch selection")
            require(state_digest(model.body) == body_before, "Validation mutated backbone state")
            result["epochs_completed"] = epoch
        result.update(status="completed", selected_epoch=10)
    except BaseException as error:  # noqa: BLE001 -- persist setup/train/validation/interruption failures
        result.update(status="failed", failure_stage=stage, error={"type": type(error).__name__, "message": str(error)})
        if not isinstance(error, Exception):
            interrupted = error
    finally:
        if model is not None and body_before is not None:
            try:
                result["body_unchanged"] = state_digest(model.body) == body_before
                require(result["body_unchanged"], "Final backbone state changed")
            except Exception as error:  # noqa: BLE001 -- preserve integrity failure
                result.update(status="failed_integrity", body_integrity_error={"type": type(error).__name__, "message": str(error)})
        try:
            verify_plan(plan_path, plan)
            require(sha(approval_path) == approval_sha, "Approval changed")
            result["final_integrity_passed"] = True
        except Exception as error:  # noqa: BLE001 -- never keep success after a changed input/source
            result.update(status="failed_integrity", final_integrity_passed=False,
                          integrity_error={"type": type(error).__name__, "message": str(error)})
        if model is not None and optimizer is not None and initial_checkpoint is not None:
            try:
                result["final_checkpoint"] = full_checkpoint(model, optimizer, expected, result["epochs_completed"], output / "final.pt")
                result["final_checkpoint"]["scope"] = "State at exit; on failure epoch denotes last fully completed epoch, possibly partial later updates"
                result["head_changed"] = result["final_checkpoint"]["head_state_sha256"] != initial_checkpoint["head_state_sha256"]
            except Exception as error:  # noqa: BLE001 -- checkpoint write failure invalidates completion
                result.update(status="failed_integrity", checkpoint_error={"type": type(error).__name__, "message": str(error)})
        write_new(output / "history.json", history)
        write_new(output / "tensor_hashes.json", tensor_hashes)
        write_new(output / "final_predictions.json", final_predictions)
        analysis = summarize(validation, final_predictions)
        analysis["final_epoch_executed_successfully"] = result["status"] == "completed"
        analysis["selection"] = "Epoch 10 only. If not reached, all final rows remain N; earlier raw evaluations are retained, never selected."
        analysis["training_failure"] = result.get("error")
        analysis["continuation_gate"] = analysis["continuation_gate"] and result["status"] == "completed"
        write_new(output / "analysis.json", analysis)
        result.update(finished_at_utc=now(), final_predictions_sha256=sha(output / "final_predictions.json"),
                      analysis_sha256=sha(output / "analysis.json"), tensor_hashes_sha256=sha(output / "tensor_hashes.json"),
                      history_sha256=sha(output / "history.json"))
        inventory = {p.name: {"bytes": p.stat().st_size, "sha256": sha(p)} for p in sorted(output.iterdir()) if p.is_file()}
        write_new(output / "artifact_inventory.json", inventory)
        result.update(artifact_inventory_sha256=sha(output / "artifact_inventory.json"),
                      wall_seconds=time.perf_counter() - begin_run)
        write_new(output / "run.json", result)
    if interrupted:
        raise interrupted
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preflight", "model-contract", "train"))
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--prepared", type=Path)
    parser.add_argument("--expected-preparation-sha256")
    parser.add_argument("--visual-review", type=Path)
    parser.add_argument("--expected-visual-sha256")
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--expected-plan-sha256")
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--expected-approval-sha256")
    parser.add_argument("--weights", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "preflight":
        require(all((args.prepared, args.expected_preparation_sha256, args.visual_review, args.expected_visual_sha256)), "Missing preparation/visual review binding")
        result = preflight(args.project_root, args.prepared, args.expected_preparation_sha256,
                           args.visual_review, args.expected_visual_sha256, args.output)
    elif args.command == "model-contract":
        require(args.weights is not None, "Explicit original COCO weights path required")
        result = model_contract(args.weights, args.output)
    else:
        require(all((args.plan, args.expected_plan_sha256, args.approval, args.expected_approval_sha256)), "Training requires plan and separate root approval")
        result = train(args.plan, args.expected_plan_sha256, args.approval, args.expected_approval_sha256, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get("status", "").startswith("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
