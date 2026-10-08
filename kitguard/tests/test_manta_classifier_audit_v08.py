"""Independent scoring contracts; only synthetic predictions, no training/model call."""
import importlib.util
import json
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("manta_audit", ROOT / "scripts/v08/audit_manta_classifier.py")
a = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(a)


def record(i, label=0, group="g0"):
    return {"input_id": f"r{i}", "input_sha256": str(i) * 64, "label": label,
            "class_name": tuple(a.CLASSES)[label], "final_group": group, "role": "validation"}


def prediction(row, probabilities=(.95, .05), status="ok"):
    p = {"input_id": row["input_id"], "input_sha256": row["input_sha256"], "status": status}
    if status == "ok":
        p.update(probabilities=list(probabilities), logits=[math.log(v) for v in probabilities])
    if status == "failed":
        p["error"] = {"type": "RuntimeError", "message": "synthetic failure"}
    return p


@pytest.mark.parametrize("confidence,expected", [(.9, "C"), (.9 - 1e-12, "U"), (.9 + 1e-12, "C")])
def test_threshold_has_no_floating_tolerance(confidence, expected):
    row = record(1)
    assert a.verdict(row, prediction(row, (confidence, 1-confidence)))[0] == expected


def test_full_denominator_including_errors_unknown_and_not_attempted():
    rows = [record(i, label=i % 2, group=f"g{i}") for i in range(5)]
    preds = [prediction(rows[0]), prediction(rows[1]), prediction(rows[2], (.5, .5)),
             prediction(rows[3], status="failed"), prediction(rows[4], status="not_attempted")]
    summary = a.independent_summary(rows, preds)
    assert summary["threshold_0_9"]["CWUEN"] == {"C": 1, "W": 1, "U": 1, "E": 1, "N": 1}
    assert summary["forced_argmax"]["CWUEN"] == {"C": 2, "W": 1, "U": 0, "E": 1, "N": 1}
    assert summary["continuation_gate"] is False
    assert summary["constant_identity_baselines"]["nut"] == {"C": 3, "W": 2, "U": 0, "E": 0, "N": 0}


def test_group_macro_cannot_be_replaced_by_record_accuracy():
    rows = [record(i, 0, "large") for i in range(100)]
    rows += [record(100+i, 0, f"small{i}") for i in range(3)]
    rows += [record(104, 1, "washer")]
    preds = [prediction(r) if i < 100 else prediction(r, (.5, .5)) for i, r in enumerate(rows[:-1])]
    preds.append(prediction(rows[-1], (.01, .99)))
    summary = a.independent_summary(rows, preds)
    nut = summary["threshold_0_9"]["classes"]["nut"]
    assert nut["record_correct_coverage"] > .95
    assert nut["group_macro_correct_coverage"] == .25
    assert summary["continuation_gate"] is False


@pytest.mark.parametrize("variant", ["wrong_logits", "nan", "missing_error", "wrong_input", "unknown_status"])
def test_corrupt_raw_records_fail_audit_instead_of_becoming_unknown(variant):
    row = record(1)
    p = prediction(row)
    if variant == "wrong_logits":
        p["logits"] = [0, 9]
    elif variant == "nan":
        p["probabilities"][0] = float("nan")
    elif variant == "missing_error":
        p["status"] = "failed"
    elif variant == "wrong_input":
        p["input_sha256"] = "wrong"
    else:
        p["status"] = "retry_later"
    with pytest.raises(ValueError):
        a.verdict(row, p)


def test_prediction_order_and_missing_population_rejected():
    rows = [record(0), record(1, 1)]
    preds = [prediction(r) for r in rows]
    with pytest.raises(ValueError, match="order"):
        a.independent_summary(rows, list(reversed(preds)))
    with pytest.raises(ValueError, match="denominator"):
        a.independent_summary(rows, preds[:1])


def test_complete_run_gate_does_not_read_partial_predictions(tmp_path):
    (tmp_path / "run.json").write_text(json.dumps({"schema": "kitguard.v08.manta-classifier.training-run.v1", "status": "running"}))
    # No predictions or analysis file exists, and neither is needed to reject this state.
    with pytest.raises(ValueError, match="complete"):
        a.completed_run_metadata(tmp_path)


@pytest.mark.parametrize("field,value", [("selected_epoch", 7), ("epochs_completed", 9),
                                         ("validation_count", 255), ("final_integrity_passed", False)])
def test_earlier_epoch_or_shrunk_population_cannot_pass_completion(tmp_path, field, value):
    run = {"schema": "kitguard.v08.manta-classifier.training-run.v1", "status": "completed",
           "epochs_completed": 10, "selected_epoch": 10, "training_count": 768, "validation_count": 256,
           "body_unchanged": True, "final_integrity_passed": True, "production_change": False,
           "new_holdout_claim": False}
    run[field] = value
    (tmp_path / "run.json").write_text(json.dumps(run))
    with pytest.raises(ValueError):
        a.completed_run_metadata(tmp_path)


def test_actual_preparation_population_metadata_contract():
    rows = json.loads((ROOT / "datasets/derived/v0.8/manta_classifier_v1/records.json").read_text())
    val = a.check_population(rows)
    assert len(val) == 256 and len({r["final_group"] for r in val}) == 8
    bad = json.loads(json.dumps(rows))
    old = next(r for r in bad if r["previously_exposed"])
    old["role"] = "validation"
    with pytest.raises(ValueError):
        a.check_population(bad)


def checkpoint_fixture():
    import torch
    before = {"body.synthetic": torch.tensor([1., 2.]), "head.weight": torch.zeros(2, 960), "head.bias": torch.zeros(2)}
    after = {k: v.clone() for k, v in before.items()}
    after["head.weight"] += .01
    after["head.bias"] += .02
    group = {"params": [0, 1], "lr": .01, "momentum": .9, "weight_decay": .0001,
             "dampening": 0, "nesterov": False, "maximize": False}
    checkpoints = []
    for i, state in enumerate((before, after)):
        checkpoints.append({"model_state_dict": state,
                            "body_state_sha256": a.state_digest({"synthetic": state["body.synthetic"]}),
                            "head_state_sha256": a.state_digest({k.removeprefix('head.'): v for k, v in state.items() if k.startswith('head.')}),
                            "optimizer_state_dict": {"param_groups": [group.copy()], "state": {} if not i else {
                                0: {"momentum_buffer": torch.ones(2, 960)}, 1: {"momentum_buffer": torch.ones(2)}}}})
    return *checkpoints, {"backbone.body.synthetic": before["body.synthetic"].clone()}


def test_full_state_and_both_head_parameter_updates_are_verified():
    initial, final, coco = checkpoint_fixture()
    result = a.check_checkpoint_pair(initial, final, coco)
    assert result["body_tensor_count"] == 1
    assert result["head_parameters_changed"] == {"head.weight": True, "head.bias": True}


@pytest.mark.parametrize("what", ["body", "one_head", "original", "optimizer"])
def test_weight_or_optimizer_tampering_rejected(what):
    initial, final, coco = checkpoint_fixture()
    if what == "body":
        final["model_state_dict"]["body.synthetic"][0] = 4
    elif what == "one_head":
        final["model_state_dict"]["head.bias"] = initial["model_state_dict"]["head.bias"].clone()
    elif what == "original":
        coco["backbone.body.synthetic"][0] = 7
    else:
        final["optimizer_state_dict"]["param_groups"][0]["params"].append(2)
    with pytest.raises(ValueError):
        a.check_checkpoint_pair(initial, final, coco)


def test_normalized_tensor_rebuild_matches_broadcast_reference(tmp_path):
    import numpy as np
    import torch
    from PIL import Image
    image = Image.new('RGB', (224, 224), (73, 73, 73))
    path = tmp_path/'synthetic.png'
    image.save(path)
    reference = torch.from_numpy(np.array(image, copy=True)).permute(2, 0, 1).to(torch.float32) / 255
    reference = (reference - torch.tensor([.485, .456, .406])[:, None, None]) / torch.tensor([.229, .224, .225])[:, None, None]
    row = {"input_id": "test", "input_path": path.name, "input_sha256": a.sha(path)}
    assert a.verify_input_tensors([row], tmp_path, {"test": a.tensor_digest(reference)}) == 1
    with pytest.raises(ValueError, match="tensor differs"):
        a.verify_input_tensors([row], tmp_path, {"test": "incorrect"})
