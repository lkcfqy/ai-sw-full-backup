"""Synthetic data and checkpoint guards; no detector inference or training."""

import importlib.util
import json
import sys
from argparse import Namespace
from copy import deepcopy
from pathlib import Path

import pytest
from PIL import Image

torch = pytest.importorskip("torch")
pytest.importorskip("torchvision")
from torchvision.ops.misc import FrozenBatchNorm2d


@pytest.fixture(scope="module")
def trainer():
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    spec = importlib.util.spec_from_file_location(
        "public_detector_training_under_test", scripts / "train_public_detector.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(scripts))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


@pytest.fixture
def sample(tmp_path, monkeypatch, trainer):
    monkeypatch.setattr(trainer, "ROOT", tmp_path)
    image = Image.new("RGB", (10, 8))
    image.putdata([(x * 20, y * 20, (x + y) * 10) for y in range(8) for x in range(10)])
    image_path = tmp_path / "sample.png"
    image.save(image_path)
    payload = {
        "categories": [{"id": 1, "name": "bolt"}, {"id": 2, "name": "nut"}],
        "images": [{"id": 7, "file_name": "sample.png", "source_sha256": trainer.sha(image_path)}],
        "annotations": [
            {"image_id": 7, "category_id": 1, "bbox": [1, 2, 3, 2]},
            {"image_id": 7, "category_id": 2, "bbox": [0, 0, 2, 3]},
        ],
    }
    path = tmp_path / "split.json"
    path.write_text(json.dumps(payload))
    return path, payload, image_path


def test_restore_keeps_frozen_batch_norm_and_exact_trainable_names(trainer, monkeypatch):
    def reject_download(*args, **kwargs):
        pytest.fail("Restoring a checkpoint must not download pretrained weights")

    monkeypatch.setattr("torchvision.models._api.load_state_dict_from_url", reject_download)
    config = {
        "min_size": 640,
        "max_size": 960,
        "trainable_parameters": ["roi_heads.box_predictor.cls_score.weight"],
    }
    original = deepcopy(config)
    # Construction initializes CPU parameters only; there is no forward/backward call.
    model = trainer.build_model(config, pretrained=False)
    assert config == original
    assert not any(isinstance(module, torch.nn.BatchNorm2d) for module in model.modules())
    assert any(isinstance(module, FrozenBatchNorm2d) for module in model.modules())
    assert not any(name.endswith("num_batches_tracked") for name in model.state_dict())
    assert [name for name, parameter in model.named_parameters() if parameter.requires_grad] == (
        config["trainable_parameters"]
    )
    assert model.roi_heads.box_predictor.cls_score.out_features == 3
    assert model.roi_heads.box_predictor.bbox_pred.out_features == 12
    assert model.transform.min_size == (640,)
    assert model.transform.max_size == 960


@pytest.mark.parametrize(
    ("draws", "axes", "expected_boxes"),
    [
        ((0.9, 0.9), (), [[1, 2, 4, 4], [0, 0, 2, 3]]),
        ((0.1, 0.9), (-1,), [[6, 2, 9, 4], [8, 0, 10, 3]]),
        ((0.9, 0.1), (-2,), [[1, 4, 4, 6], [0, 5, 2, 8]]),
        ((0.1, 0.1), (-1, -2), [[6, 4, 9, 6], [8, 5, 10, 8]]),
    ],
)
def test_training_flips_keep_pixels_boxes_and_labels_aligned(
    trainer, sample, monkeypatch, draws, axes, expected_boxes
):
    path, _, _ = sample
    reference, _ = trainer.ScrewsDataset(path, augment=False)[0]
    sequence = iter(draws)
    monkeypatch.setattr(trainer.random, "random", lambda: next(sequence))
    actual, target = trainer.ScrewsDataset(path, augment=True)[0]
    expected_image = reference.flip(axes) if axes else reference
    torch.testing.assert_close(actual, expected_image, rtol=0, atol=0)
    torch.testing.assert_close(target["boxes"], torch.tensor(expected_boxes, dtype=torch.float32))
    assert target["labels"].tolist() == [1, 2]
    assert target["labels"].dtype == torch.int64
    assert int(target["image_id"]) == 7


def test_validation_never_draws_augmentation_randomness(trainer, sample, monkeypatch):
    path, _, _ = sample

    def reject_random():
        pytest.fail("Validation must never apply random augmentation")

    monkeypatch.setattr(trainer.random, "random", reject_random)
    image, target = trainer.ScrewsDataset(path)[0]
    assert image.shape == (3, 8, 10)
    assert image[:, 0, 0].tolist() == [0.0, 0.0, 0.0]
    assert target["boxes"].tolist() == [[1.0, 2.0, 4.0, 4.0], [0.0, 0.0, 2.0, 3.0]]


def test_empty_annotation_image_retains_valid_shapes_during_augmentation(trainer, sample, monkeypatch):
    path, payload, _ = sample
    payload["annotations"] = []
    path.write_text(json.dumps(payload))
    monkeypatch.setattr(trainer.random, "random", lambda: 0.1)
    image, target = trainer.ScrewsDataset(path, augment=True)[0]
    assert image.shape == (3, 8, 10)
    assert target["boxes"].shape == (0, 4)
    assert target["labels"].shape == (0,)


@pytest.mark.parametrize("fault", ["changed", "missing"])
def test_source_image_tampering_or_loss_is_rejected(trainer, sample, fault):
    path, _, image_path = sample
    if fault == "changed":
        Image.new("RGB", (10, 8), "red").save(image_path)
    else:
        image_path.unlink()
    with pytest.raises(ValueError, match="Source image missing/modified"):
        trainer.ScrewsDataset(path)


def test_swapped_class_mapping_is_rejected(trainer, sample):
    path, payload, _ = sample
    payload["categories"] = [{"id": 1, "name": "nut"}, {"id": 2, "name": "bolt"}]
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="Only background/bolt/nut"):
        trainer.ScrewsDataset(path)


def test_evaluation_rejects_changed_split_before_constructing_model(trainer, tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    for name in ("manifest.json", "train.json", "val.json", "test.json"):
        (data / name).write_text("{}")
    checkpoint = {"config": {"data_fingerprint": trainer.fingerprint(data)}}
    (data / "test.json").write_text('{"changed": true}')
    monkeypatch.setattr(trainer.torch, "load", lambda *args, **kwargs: checkpoint)
    monkeypatch.setattr(trainer.torch, "set_num_threads", lambda *args: None)
    monkeypatch.setattr(
        trainer, "build_model", lambda *args, **kwargs: pytest.fail("Changed test split reached model setup")
    )
    args = Namespace(
        output=tmp_path / "evaluation",
        device="cpu",
        threads=1,
        checkpoint=tmp_path / "best.pt",
        data=data,
    )
    with pytest.raises(ValueError, match="Data changed since training"):
        trainer.final_evaluate(args)


@pytest.mark.parametrize("changed_key", ["data_fingerprint", "min_size", "batch_size", "learning_rate"])
def test_resume_rejects_changed_protocol_before_constructing_model(
    trainer, tmp_path, monkeypatch, changed_key
):
    fingerprint = {"train.json": "fixed-test-digest"}
    old = {
        "data_fingerprint": fingerprint,
        "min_size": 640,
        "max_size": 960,
        "batch_size": 2,
        "seed": 20260930,
        "learning_rate": 0.005,
        "lr_step_epoch": 8,
        "momentum": 0.9,
        "weight_decay": 0.0005,
        "augmentation": "independent horizontal/vertical flip p=0.5, training only",
    }
    old[changed_key] = "different"
    monkeypatch.setattr(trainer, "fingerprint", lambda path: fingerprint)
    monkeypatch.setattr(trainer.torch, "load", lambda *args, **kwargs: {"config": old})
    monkeypatch.setattr(trainer.torch, "set_num_threads", lambda *args: None)
    monkeypatch.setattr(
        trainer, "build_model", lambda *args, **kwargs: pytest.fail("Changed protocol reached model setup")
    )
    args = Namespace(
        output=tmp_path / "training",
        device="cpu",
        threads=1,
        data=tmp_path / "data",
        epochs=12,
        batch_size=2,
        min_size=640,
        max_size=960,
        lr=0.005,
        lr_step=8,
        seed=20260930,
        resume=tmp_path / "last.pt",
    )
    with pytest.raises(ValueError, match=f"Resume configuration mismatch: {changed_key}"):
        trainer.train(args)
