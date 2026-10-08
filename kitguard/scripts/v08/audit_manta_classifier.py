"""Independent CPU audit of a completed fixed MANTA classifier run.

Never imports the trainer, builds a model, calls forward, or changes run evidence.
Raw saved probabilities drive the exact frozen >=.9 decision; a separately calculated
stable softmax checks their coherence with saved logits (MPS rounding tolerance only).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLASSES = {"nut": 0, "yellow_green_washer": 1}
PREP_FREEZE_SHA = "226f739d011c5f4095888251b572663fd2c12a485c6b48d8c36e206553111f9e"
COCO_SHA = "907ea3f91ff92242bc1baea8049276a3e76bca48ce7560bd268cc029f37977b5"
TRAINER_SHA = "5f3475a5b911cada936eb62fae24890b1f4096153307a6b64a7e5619bca9057c"
BODY_SHA = "f56ef796a2db2b8a9e3b2ad253f1c3789609500c8554b375c2126f9824152351"
MODEL_CONTRACT_SHA = "7abd046c7ccc64345fb5bace724d300c008fd843f749e1a31b076aab9a6d873a"
CONFIG = {"epochs": 10, "optimizer": "SGD", "learning_rate": .01, "momentum": .9,
          "weight_decay": .0001, "batch_size": 32, "seed": 20261002, "device": "mps",
          "precision": "float32", "workers": 0, "augmentation": "none", "probability_threshold": .9,
          "normalization_mean": [.485, .456, .406], "normalization_std": [.229, .224, .225]}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def lines(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def verdict(record, prediction, forced=False):
    require(prediction["input_id"] == record["input_id"]
            and prediction["input_sha256"] == record["input_sha256"], "Prediction/input binding differs")
    require(type(record["label"]) is int and record["label"] in (0, 1), "Invalid author class")
    state = prediction["status"]
    if state == "failed":
        require(isinstance(prediction.get("error"), dict) and prediction["error"].get("type"), "Missing failure cause")
        return "E", "error"
    if state == "not_attempted":
        return "N", "not_attempted"
    require(state == "ok", "Unknown observation status")
    logits, probs = prediction["logits"], prediction["probabilities"]
    require(isinstance(logits, list) and len(logits) == 2 and all(finite(v) for v in logits), "Invalid logits")
    require(isinstance(probs, list) and len(probs) == 2 and all(finite(v) and 0 <= v <= 1 for v in probs)
            and abs(sum(probs) - 1) < 1e-5, "Invalid probabilities")
    exp = [math.exp(x - max(logits)) for x in logits]
    computed = [x / sum(exp) for x in exp]
    require(max(abs(a - b) for a, b in zip(probs, computed, strict=True)) <= 2e-6,
            "Saved probability/logit mismatch beyond fixed numerical tolerance")
    choice = 0 if probs[0] >= probs[1] else 1
    # Do not use numerical tolerance on the decision boundary.
    if not forced and probs[choice] < .9:
        return "U", "unknown"
    return ("C" if choice == record["label"] else "W"), tuple(CLASSES)[choice]


def tally(labels):
    return {code: labels.count(code) for code in "CWUEN"}


def independent_summary(records, predictions):
    require(len(records) > 0 and len(records) == len(predictions), "Wrong full validation denominator")
    require(len({r["input_id"] for r in records}) == len(records), "Repeated validation identity")
    require([p["input_id"] for p in predictions] == [r["input_id"] for r in records], "Validation order changed")
    require(all(r["class_name"] in CLASSES and r["label"] == CLASSES[r["class_name"]] for r in records),
            "Class-name/label mapping mismatch")
    require(all(r["role"] == "validation" for r in records), "Nonvalidation record in scoring")
    result = {}
    for panel, forced in (("threshold_0_9", False), ("forced_argmax", True)):
        answers = [verdict(r, p, forced) for r, p in zip(records, predictions, strict=True)]
        labels = [answer[0] for answer in answers]
        counts = tally(labels)
        groups = []
        classes = {}
        for name in sorted({r["class_name"] for r in records}):
            indices = [i for i, r in enumerate(records) if r["class_name"] == name]
            group_ids = sorted({records[i]["final_group"] for i in indices})
            local_groups = []
            for group_id in group_ids:
                group_answers = [labels[i] for i in indices if records[i]["final_group"] == group_id]
                local = tally(group_answers)
                group = {"class_name": name, "group_id": group_id, "denominator": len(group_answers),
                         "CWUEN": local, "correct_coverage": local["C"] / len(group_answers),
                         "coverage": (local["C"] + local["W"]) / len(group_answers)}
                local_groups.append(group)
            c = tally([labels[i] for i in indices])
            confusion = {key: sum(answers[i][1] == key for i in indices)
                         for key in ("nut", "yellow_green_washer", "unknown", "error", "not_attempted")}
            classes[name] = {"denominator": len(indices), "CWUEN": c, "confusion": confusion,
                             "group_count": len(group_ids), "record_correct_coverage": c["C"] / len(indices),
                             "group_macro_correct_coverage": sum(g["correct_coverage"] for g in local_groups) / len(group_ids),
                             "group_macro_coverage": sum(g["coverage"] for g in local_groups) / len(group_ids)}
            groups.extend(local_groups)
        result[panel] = {"denominator": len(records), "CWUEN": counts, "classes": classes,
                         "groups": sorted(groups, key=lambda g: (g["class_name"], g["group_id"])),
                         "coverage": (counts["C"] + counts["W"]) / len(records)}
    main = result["threshold_0_9"]
    result["continuation_gate"] = (
        set(main["classes"]) == set(CLASSES)
        and sum(main["CWUEN"][key] for key in ("W", "E", "N")) == 0
        and all(c["group_macro_correct_coverage"] >= .75 for c in main["classes"].values())
    )
    result["constant_identity_baselines"] = {
        name: {"C": sum(r["label"] == target for r in records), "W": sum(r["label"] != target for r in records),
               "U": 0, "E": 0, "N": 0} for name, target in CLASSES.items()
    }
    result["production_promotion"] = False
    return result


def check_population(records):
    require(len(records) == 1024 and len({r["input_id"] for r in records}) == 1024, "Training population not complete")
    require(Counter(r["role"] for r in records) == {"train": 768, "validation": 256}, "Role denominators changed")
    grouped = defaultdict(list)
    for r in records:
        require(r["status"] == "prepared" and r["author_split"] == "train", "Invalid prepared role/status")
        require(r["class_name"] in CLASSES and r["label"] == CLASSES[r["class_name"]], "Class mapping differs")
        require(not r["previously_exposed"] or r["role"] == "train", "Old exposure in validation")
        grouped[r["final_group"]].append(r)
    require(len(grouped) == 32, "Proxy group count differs")
    for members in grouped.values():
        require(len(members) == 32 and len({r["class_name"] for r in members}) == 1
                and len({r["role"] for r in members}) == 1, "Group split/class conflict")
    for name in CLASSES:
        subset = [r for r in records if r["class_name"] == name]
        require(Counter(r["role"] for r in subset) == {"train": 384, "validation": 128}, "Per-class denominator differs")
        require(len({r["final_group"] for r in subset if r["role"] == "validation"}) == 4, "Validation groups differ")
    require(sum(r["previously_exposed"] for r in records) == 4, "Previous exposure population changed")
    require(sum(r["visual_qa_selected"] for r in records) == 36
            and sum(r["visual_qa_selected"] and r["role"] == "validation" for r in records) == 8, "Layout exposure contract differs")
    return [r for r in records if r["role"] == "validation"]


def compare_report(independent, recorded):
    for key in ("threshold_0_9", "forced_argmax", "constant_identity_baselines", "continuation_gate", "production_promotion"):
        require(independent[key] == recorded[key], f"Independent metric differs: {key}")


def completed_run_metadata(run_path):
    """Called before loading any prediction or analysis file."""
    run = read(Path(run_path) / "run.json")
    require(run["schema"] == "kitguard.v08.manta-classifier.training-run.v1" and run["status"] == "completed",
            "Only a complete run may be audited for quality")
    require(run["epochs_completed"] == 10 and run["selected_epoch"] == 10, "Final fixed epoch was not uniquely selected")
    require(run["training_count"] == 768 and run["validation_count"] == 256, "Run population incomplete")
    require(run["body_unchanged"] is True and run["final_integrity_passed"] is True, "Run integrity not confirmed")
    require(run["production_change"] is False and run["new_holdout_claim"] is False, "Unsupported promotion/holdout claim")
    return run


def tensor_digest(tensor):
    value = tensor.detach().cpu().contiguous()
    return hashlib.sha256(canonical({"shape": list(value.shape), "dtype": str(value.dtype)}).encode()
                          + b"\0" + value.numpy().tobytes()).hexdigest()


def state_digest(state):
    return hashlib.sha256(canonical({key: tensor_digest(value) for key, value in sorted(state.items())}).encode()).hexdigest()


def check_optimizer(state, initial=False):
    groups = state["param_groups"]
    require(len(groups) == 1, "Unexpected optimizer groups")
    g = groups[0]
    require(len(g["params"]) == 2 and len(set(g["params"])) == 2, "Optimizer includes more than two head tensors")
    for key, value in {"lr": .01, "momentum": .9, "weight_decay": .0001,
                       "dampening": 0, "nesterov": False, "maximize": False}.items():
        require(g[key] == value, f"Optimizer parameter changed: {key}")
    require(set(state["state"]) <= set(g["params"]), "Optimizer state outside head")
    if initial:
        require(not state["state"], "Initial optimizer was not empty")
    else:
        require(set(state["state"]) == set(g["params"]), "Final momentum missing")
        for key, shape in zip(g["params"], ((2, 960), (2,)), strict=True):
            momentum = state["state"][key]["momentum_buffer"]
            require(tuple(momentum.shape) == shape and str(momentum.dtype) == "torch.float32"
                    and momentum.isfinite().all().item(), "Invalid optimizer momentum")


def check_checkpoint_pair(initial, final, coco):
    """Accepts already loaded CPU tensors; no model or forward is constructed."""
    import torch
    before, after = initial["model_state_dict"], final["model_state_dict"]
    require(set(before) == set(after), "Checkpoint tensor inventory differs")
    body_keys = sorted(k for k in before if k.startswith("body."))
    head_keys = sorted(k for k in before if k.startswith("head."))
    require(body_keys and head_keys == ["head.bias", "head.weight"]
            and set(body_keys + head_keys) == set(before), "Unexpected model state inventory")
    for key in body_keys:
        original_key = "backbone.body." + key.removeprefix("body.")
        require(original_key in coco and torch.equal(before[key], coco[original_key]), "Initial body not original COCO")
        require(torch.equal(before[key], after[key]) and before[key].dtype == after[key].dtype,
                f"Frozen backbone tensor changed: {key}")
    require({"body." + k.removeprefix("backbone.body.") for k in coco if k.startswith("backbone.body.")}
            == set(body_keys), "Backbone omitted original tensors")
    changes = {}
    for key, shape in (("head.weight", (2, 960)), ("head.bias", (2,))):
        require(tuple(before[key].shape) == shape == tuple(after[key].shape)
                and str(before[key].dtype) == str(after[key].dtype) == "torch.float32", "Wrong classifier head")
        require(before[key].isfinite().all().item() and after[key].isfinite().all().item(), "Nonfinite head")
        changes[key] = not torch.equal(before[key], after[key])
        require(changes[key], f"Head tensor never updated: {key}")
    body = {k.removeprefix("body."): before[k] for k in body_keys}
    body_sha = state_digest(body)
    require(initial["body_state_sha256"] == final["body_state_sha256"] == body_sha, "Stored backbone digest differs")
    for checkpoint, state in ((initial, before), (final, after)):
        head = {k.removeprefix("head."): state[k] for k in head_keys}
        require(state_digest(head) == checkpoint["head_state_sha256"], "Stored head digest differs")
    check_optimizer(initial["optimizer_state_dict"], initial=True)
    check_optimizer(final["optimizer_state_dict"])
    return {"body_tensor_count": len(body_keys), "body_state_sha256": body_sha,
            "all_body_tensors_equal_original_coco_and_final": True, "head_parameters_changed": changes}


def verify_input_tensors(records, base, stored):
    """Rebuild normalized CPU tensors from prepared PNGs; never run a model."""
    import numpy as np
    import torch
    from PIL import Image
    require(set(stored) == {r["input_id"] for r in records}, "Tensor evidence missing planned inputs")
    for r in records:
        path = Path(base) / r["input_path"]
        require(sha(path) == r["input_sha256"], "Prepared input changed")
        with Image.open(path) as im:
            require(im.format == "PNG" and im.mode == "RGB" and im.size == (224, 224), "Unexpected input image")
            array = np.array(im, dtype=np.uint8, copy=True)
        require(np.array_equal(array[:, :, 0], array[:, :, 1]) and np.array_equal(array[:, :, 1], array[:, :, 2]),
                "Prepared input no longer grayscale")
        tensor = torch.from_numpy(array).permute(2, 0, 1).contiguous().to(torch.float32).div(255)
        for channel, (mean, std) in enumerate(zip(CONFIG["normalization_mean"], CONFIG["normalization_std"], strict=True)):
            tensor[channel] = (tensor[channel] - mean) / std
        require(tensor_digest(tensor) == stored[r["input_id"]], "Normalized input tensor differs")
    return len(records)


def audit(run_path, plan_path, expected_plan, approval_path):
    run_path, plan_path, approval_path = Path(run_path).resolve(), Path(plan_path).resolve(), Path(approval_path).resolve()
    run = completed_run_metadata(run_path)
    require(sha(run_path / "artifact_inventory.json") == run["artifact_inventory_sha256"], "Artifact inventory changed")
    inventory = read(run_path / "artifact_inventory.json")
    expected_artifacts = {"started.json", "plan.json", "approval.json", "initial.pt", "final.pt", "history.json",
                          "tensor_hashes.json", "final_predictions.json", "analysis.json"}
    expected_artifacts |= {f"epoch-{epoch:02}{ending}" for epoch in range(1, 11)
                           for ending in ("-validation.jsonl", "-metrics.json", "-training-records.json",
                                          "-batches.jsonl", ".pt", "-checkpoint.json")}
    require(set(inventory) == expected_artifacts and {p.name for p in run_path.iterdir()}
            == expected_artifacts | {"run.json", "artifact_inventory.json"}, "Missing/extra run artifacts")
    for name, binding in inventory.items():
        path = run_path / name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size == binding["bytes"]
                and sha(path) == binding["sha256"], "Inventory member bytes differ")
    require(sha(plan_path) == expected_plan == run["plan_sha256"], "Training plan SHA differs")
    plan = read(plan_path)
    require(plan["schema"] == "kitguard.v08.manta-classifier.training-plan.v1"
            and plan["config"] == CONFIG and plan["classes"] == CLASSES, "Pinned training config differs")
    require(plan["source_snapshot"]["scripts/v08/train_manta_classifier.py"] == TRAINER_SHA, "Unreviewed trainer source")
    require(sha(run_path / "plan.json") == expected_plan and read(run_path / "plan.json") == plan, "Run plan copy differs")
    require(sha(approval_path) == run["approval_sha256"], "Training approval SHA differs")
    approval = read(approval_path)
    require(sha(run_path / "approval.json") == run["approval_sha256"]
            and read(run_path / "approval.json") == approval and approval["status"] == "approved"
            and approval["authorized_by"] == "root", "Root training approval differs")
    for key, value in {"plan_sha256": expected_plan, "freeze_sha256": PREP_FREEZE_SHA,
                       "preparation_sha256": plan["preparation_sha256"], "visual_review_sha256": plan["visual_review_sha256"],
                       "training_source_sha256": plan["source_snapshot"]["scripts/v08/train_manta_classifier.py"],
                       "epochs": 10, "production_change": False}.items():
        require(approval[key] == value, f"Approval field differs: {key}")
    bindings = {str(plan_path): expected_plan, str(approval_path): sha(approval_path), str(run_path / "run.json"): sha(run_path / "run.json"),
                str(run_path / "artifact_inventory.json"): run["artifact_inventory_sha256"]}
    for rel, expected in plan["source_snapshot"].items():
        path = plan_path.parent / "source_snapshot" / rel
        require(sha(path) == expected, "Frozen trainer source changed")
        bindings[str(path)] = expected
    for path, expected in plan["runtime"]["files"].items():
        require(sha(path) == expected, "Pinned runtime implementation changed")
    root = Path(plan["project_root"])
    model_contract_path = root / "test-results/v0.8-manta-classifier-model-contract-v1/contract.json"
    require(sha(model_contract_path) == MODEL_CONTRACT_SHA, "Prior CPU model contract changed")
    bindings[str(model_contract_path)] = MODEL_CONTRACT_SHA
    freeze_path = root / "docs/v0.8/manta_classifier_freeze_v1/freeze.json"
    require(sha(freeze_path) == PREP_FREEZE_SHA == plan["freeze_sha256"], "Preparation freeze changed")
    freeze = read(freeze_path)
    require(sha(freeze_path.parent / "protocol.json") == freeze["protocol_sha256"], "Prepared protocol changed")
    prep_protocol = read(freeze_path.parent / "protocol.json")
    for rel, expected in prep_protocol["bindings"].items():
        require(sha(root / rel) == expected, "Original preparation source metadata changed")
    for archive in prep_protocol["archives"]:
        require(sha(root / archive["path"]) == archive["sha256"], "Original archive bytes changed")
    for rel, expected in freeze["source_snapshot"].items():
        require(sha(freeze_path.parent / "source_snapshot" / rel) == expected, "Frozen preparer changed")
    preparation_path = Path(plan["preparation_path"])
    require(sha(preparation_path) == plan["preparation_sha256"], "Preparation receipt changed")
    prepared = read(preparation_path)
    require(prepared["status"] == "prepared_pending_visual_review" and prepared["status_counts"] == {"prepared": 1024},
            "Preparation was incomplete")
    for name in ("records", "grouping"):
        require(sha(preparation_path.parent / f"{name}.json") == prepared[f"{name}_sha256"], "Preparation data changed")
    records = read(preparation_path.parent / "records.json")
    require(records == plan["records"], "Planned records differ from prepared records")
    validation = check_population(records)
    training = [r for r in records if r["role"] == "train"]
    visual_path = Path(plan["visual_review_path"])
    require(sha(visual_path) == plan["visual_review_sha256"], "Layout review changed")
    visual = read(visual_path)
    require(visual["schema"] == "kitguard.v08.manta-classifier.visual-review.v1"
            and visual["status"] == "passed" and visual["training_authorized"] is False
            and visual["preparation_sha256"] == plan["preparation_sha256"], "Invalid layout review")
    require({r["input_id"] for r in visual["reviewed_records"]} == {r["input_id"] for r in records if r["visual_qa_selected"]}
            and len(visual["reviewed_records"]) == 36 and all(r["accepted"] is True for r in visual["reviewed_records"]),
            "Layout reviewed population differs")
    by_id = {r["input_id"]: r for r in records}
    for reviewed in visual["reviewed_records"]:
        require(all(reviewed[k] == by_id[reviewed["input_id"]][k] for k in ("member_path", "role", "input_sha256")),
                "Visual review source identity differs")
    require(visual["sheets"] == prepared["qa_sheets"], "Review sheet inventory differs")
    for sheet in prepared["qa_sheets"]:
        require(sha(preparation_path.parent / sheet["path"]) == sheet["sha256"], "Reviewed sheet changed")
    for name in ("history", "final_predictions", "analysis", "tensor_hashes"):
        path = run_path / f"{name}.json"
        require(sha(path) == run[f"{name}_sha256"], "Final evidence hash differs")
        bindings[str(path)] = sha(path)
    history = read(run_path / "history.json")
    require([x["epoch"] for x in history] == list(range(1, 11)), "Ten complete epochs not recorded")
    rng = random.Random(20261002)
    epochs = []
    for entry in history:
        epoch = entry["epoch"]
        expected_files = {f"epoch-{epoch:02}-validation.jsonl", f"epoch-{epoch:02}-metrics.json",
                          f"epoch-{epoch:02}-training-records.json", f"epoch-{epoch:02}-batches.jsonl",
                          f"epoch-{epoch:02}.pt", f"epoch-{epoch:02}-checkpoint.json"}
        require(set(entry["files"]) == expected_files, "Per-epoch evidence inventory differs")
        for filename, expected in entry["files"].items():
            require(sha(run_path / filename) == expected, "Per-epoch evidence changed")
        checkpoint_receipt = read(run_path / f"epoch-{epoch:02}-checkpoint.json")
        require(checkpoint_receipt["epoch"] == epoch and checkpoint_receipt["sha256"] == sha(run_path / f"epoch-{epoch:02}.pt"),
                "Epoch checkpoint receipt differs")
        attempts = read(run_path / f"epoch-{epoch:02}-training-records.json")
        require([x["input_id"] for x in attempts] == [r["input_id"] for r in training]
                and all(x["status"] == "trained" for x in attempts), "Incomplete training epoch")
        order = list(range(768))
        rng.shuffle(order)
        batches = lines(run_path / f"epoch-{epoch:02}-batches.jsonl")
        require(len(batches) == 24, "Wrong epoch batch count")
        for i, batch in enumerate(batches):
            require(batch["epoch"] == epoch and batch["batch"] == i and batch["status"] == "trained"
                    and batch["input_ids"] == [training[j]["input_id"] for j in order[i*32:(i+1)*32]]
                    and finite(batch["loss"]) and batch["loss"] >= 0, "Training batch/order mismatch")
        predictions = lines(run_path / f"epoch-{epoch:02}-validation.jsonl")
        require(len(predictions) == 256 and all(x["status"] == "ok" and x["error"] is None for x in predictions),
                "Incomplete saved validation epoch")
        for row, pred in zip(validation, predictions, strict=True):
            require(all(pred[k] == row[k] for k in ("input_id", "input_sha256", "class_name", "label", "final_group")),
                    "Raw validation metadata differs")
            require(pred["batch_forward_started"] is True and pred["batch_size"] == 32
                    and finite(pred["batch_wall_seconds"]) and pred["batch_wall_seconds"] >= 0, "Missing historical batch record")
        recomputed = independent_summary(validation, predictions)
        metrics = read(run_path / f"epoch-{epoch:02}-metrics.json")
        require(metrics["epoch"] == epoch and abs(metrics["training_loss"] - sum(b["loss"] for b in batches)/24) <= 1e-10,
                "Training loss aggregate differs")
        compare_report(recomputed, metrics["validation"])
        epochs.append({"epoch": epoch, "independent_metrics": recomputed})
    final_predictions = read(run_path / "final_predictions.json")
    require(final_predictions == lines(run_path / "epoch-10-validation.jsonl"), "Selected output is not exact final epoch")
    final_summary = independent_summary(validation, final_predictions)
    compare_report(final_summary, read(run_path / "analysis.json"))
    require(read(run_path / "analysis.json")["final_epoch_executed_successfully"] is True, "Final epoch success not retained")
    # Torch is loaded only for CPU deserialization/arithmetic after complete raw evidence validation.
    import torch
    checkpoints = []
    for key, filename, epoch in (("initial_checkpoint", "initial.pt", 0), ("final_checkpoint", "final.pt", 10)):
        receipt = run[key]
        require(receipt["path"] == filename and receipt["epoch"] == epoch and sha(run_path / filename) == receipt["sha256"],
                "Full checkpoint hash/epoch differs")
        checkpoint = torch.load(run_path / filename, map_location="cpu", weights_only=True)
        require(checkpoint["schema"] == "kitguard.v08.manta-classifier.full-checkpoint.v1" and checkpoint["epoch"] == epoch
                and checkpoint["plan_sha256"] == expected_plan and checkpoint["config"] == CONFIG
                and checkpoint["classes"] == CLASSES and checkpoint["original_coco_sha256"] == COCO_SHA, "Checkpoint contract differs")
        for field in ("body_state_sha256", "head_state_sha256"):
            require(checkpoint[field] == receipt[field], "Checkpoint digest/receipt differs")
        checkpoints.append(checkpoint)
        bindings[str(run_path / filename)] = receipt["sha256"]
    require(sha(plan["weights_path"]) == plan["weights_sha256"] == COCO_SHA, "Original COCO weights changed")
    coco = torch.load(plan["weights_path"], map_location="cpu", weights_only=True)
    weight_evidence = check_checkpoint_pair(checkpoints[0], checkpoints[1], coco)
    require(weight_evidence["body_state_sha256"] == BODY_SHA, "Backbone differs from prior strict-load CPU contract")
    final_head = {k.removeprefix("head."): v for k, v in checkpoints[1]["model_state_dict"].items() if k.startswith("head.")}
    for epoch in range(1, 11):
        checkpoint = torch.load(run_path / f"epoch-{epoch:02}.pt", map_location="cpu", weights_only=True)
        require(checkpoint["schema"] == "kitguard.v08.manta-classifier.head-checkpoint.v1"
                and checkpoint["epoch"] == epoch and checkpoint["plan_sha256"] == expected_plan
                and checkpoint["config"] == CONFIG and checkpoint["classes"] == CLASSES
                and checkpoint["body_state_sha256"] == weight_evidence["body_state_sha256"]
                and checkpoint["original_coco_sha256"] == COCO_SHA, "Epoch checkpoint contract differs")
        check_optimizer(checkpoint["optimizer_state_dict"])
        require(set(checkpoint["head_state_dict"]) == {"weight", "bias"}, "Epoch head inventory differs")
        for key, shape in (("weight", (2, 960)), ("bias", (2,))):
            value = checkpoint["head_state_dict"][key]
            require(tuple(value.shape) == shape and str(value.dtype) == "torch.float32" and value.isfinite().all().item(),
                    "Epoch head shape/type/finite contract differs")
        if epoch == 10:
            require(all(torch.equal(checkpoint["head_state_dict"][k], v) for k, v in final_head.items()), "Final head not epoch10")
            a, b = checkpoint["optimizer_state_dict"], checkpoints[1]["optimizer_state_dict"]
            require(a["param_groups"] == b["param_groups"] and set(a["state"]) == set(b["state"]), "Final optimizer not epoch10")
            require(all(torch.equal(a["state"][k]["momentum_buffer"], b["state"][k]["momentum_buffer"]) for k in a["state"]),
                    "Final momentum not epoch10")
    normalized = verify_input_tensors(records, plan["input_base"], read(run_path / "tensor_hashes.json"))
    bindings.update({str(freeze_path): PREP_FREEZE_SHA, str(preparation_path): plan["preparation_sha256"],
                     str(visual_path): plan["visual_review_sha256"], str(plan["weights_path"]): COCO_SHA})
    return {"status": "passed", "bindings": bindings, "independent_results": final_summary,
            "epochs": epochs, "selected_epoch": 10, "validation_records": 256, "all_prepared_groups": 32,
            "validation_groups": 8, "weight_evidence": weight_evidence, "normalized_inputs_rebuilt": normalized,
            "new_model_calls": 0, "new_training_steps": 0, "production_change": False,
            "limitations": ["Saved raw/weight/data consistency audit, not attestation of the historical physical execution.",
                            "Wall clocks and historical forward flags are retained records, not newly measured calls.",
                            "Softmax/logit check uses 2e-6 numerical tolerance; exact .9 decision uses saved probabilities without tolerance.",
                            "All validation comes from author-train records with proxy grouping; 8 records had declared image layout QA.",
                            "Passing internal continuation gate permits only further development diagnostics, not production promotion.",
                            "Shape, brightness, crop dimensions and padding can remain shortcuts; silver mixed-hardware transfer unproven."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--approval", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "Audit output exists; preserve prior attempt")
    require(not args.output.resolve().is_relative_to(args.run.resolve()), "Do not write audit inside original run")
    started = datetime.now(UTC).isoformat()
    try:
        result = audit(args.run, args.plan, args.expected_plan_sha256, args.approval)
    except Exception as error:  # noqa: BLE001 -- preserve independent audit failure without changing evidence
        result = {"status": "failed", "error": {"type": type(error).__name__, "message": str(error)},
                  "new_model_calls": 0, "new_training_steps": 0, "production_change": False}
    result.update(schema="kitguard.v08.manta-classifier.independent-audit.v1", started_at_utc=started,
                  finished_at_utc=datetime.now(UTC).isoformat(), auditor_sha256=sha(__file__))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": result["status"], "output": str(args.output), "sha256": sha(args.output)}, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
