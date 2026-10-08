"""Synthetic and CPU checkpoint metadata contracts; never build/forward a model."""
import copy
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("grayscale_diagnostic", ROOT / "scripts/v08/probe_grayscale_validation.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def scorer():
    return m.scoring_module(ROOT)


def record(i, source="foda", label=2):
    return {"id": f"synthetic:{i}", "source": source, "source_sha256": f"{i:064x}",
            "group_id": "synthetic-nut" if source == "foda" else f"source-{i}", "image_size": [20, 20],
            "ground_truth": [{"label": label, "box": [1, 1, 10, 10], "annotation_id": i}]}


def prediction(label=2, score=.5, box=None):
    return {"label": label, "score": score, "box": box or [1, 1, 10, 10]}


def test_standalone_import_has_no_torch_mlx_or_production():
    result = subprocess.run([sys.executable, "-I", "-c",
                             ("import runpy,sys;runpy.run_path(sys.argv[1]);"
                              "assert not any(n in sys.modules for n in ['torch','mlx','mlx_vlm','kitguard','PIL'])"),
                             m.__file__], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("mode", ["RGB", "RGBA", "P"])
def test_gray_is_only_rgb_l_rgb_without_geometry_or_original_changes(mode):
    image = Image.new("RGB", (9, 5), (230, 40, 100))
    image.putpixel((3, 2), (1, 120, 250))
    image = image.convert(mode)
    before = image.tobytes()
    gray = m.grayscale(image)
    expected = ImageOps.grayscale(image.convert("RGB")).convert("RGB")
    assert gray.mode == "RGB" and gray.size == image.size
    assert gray.tobytes() == expected.tobytes()
    assert image.tobytes() == before
    assert all(r == g == b for r, g, b in gray.get_flattened_data())


def test_confusion_requires_localization_and_one_to_one_matching():
    score = scorer()
    predictions = [prediction(3, .9), prediction(3, .8), prediction(2, .7),
                   prediction(3, .99, [11, 11, 19, 19])]
    got = m.confusion(record(1), predictions, score)
    assert got["nut_to_washer"] == 1
    assert len(got["matches"]) == 1 and got["matches"][0]["prediction_index"] == 0
    assert m.confusion(record(1), [prediction(3, .499)], score)["nut_to_washer"] == 0
    assert m.confusion(record(1), [prediction(3, .5)], score)["nut_to_washer"] == 1


def test_all80_failures_retained_and_not_converted_to_empty_predictions():
    records = [record(i, "screws" if i < 44 else "foda") for i in range(80)]
    rgb = [{"id": r["id"], "predictions": [prediction()]} for r in records]
    rows = [{"id": records[0]["id"], "source_sha256": records[0]["source_sha256"], "status": "failed",
             "predictions": [prediction(3)], "error": "synthetic model failure"},
            {"id": records[1]["id"], "source_sha256": records[1]["source_sha256"], "status": "ok", "predictions": []}]
    result = m.analyze(records, rgb, rows, scorer())
    assert result["all"]["planned"] == 80
    assert result["all"]["completed"] == 1 and result["all"]["failed"] == 1
    assert result["all"]["not_attempted"] == 78
    assert result["all"]["full_denominator_metrics_available"] is False
    assert result["all"]["gray_exact_count_fraction_of_planned"] == 0
    assert result["cases"][0]["gray_metrics"] is None
    assert result["cases"][1]["gray_metrics"]["missed_ground_truth_indices"] == [0]
    assert result["all"]["unmeasured_nut_gt"] == 79
    assert len(result["cases"]) == 80


def test_baseline_immutable_and_raw_low_score_boxes_are_not_counted():
    records = [record(1)]
    rgb = [{"id": "synthetic:1", "predictions": [prediction(3, .7)]}]
    raw = [prediction(2, .5), prediction(3, .49)]
    rows = [{"id": "synthetic:1", "source_sha256": records[0]["source_sha256"], "status": "ok", "predictions": raw}]
    before = copy.deepcopy((rgb, rows))
    result = m.analyze(records, rgb, rows, scorer())
    assert (rgb, rows) == before and len(rows[0]["predictions"]) == 2
    assert result["all"]["rgb_nut_to_washer"] == 1 and result["all"]["gray_measured_nut_to_washer"] == 0
    assert result["all"]["inexact_to_exact"] == ["synthetic:1"]
    bad = copy.deepcopy(rows)
    bad[0]["source_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="source identity"):
        m.analyze(records, rgb, bad, scorer())


@pytest.mark.parametrize("path", ["../escape.png", "datasets/derived/x/held_back/image.jpg",
                                  "datasets/raw/manta-identity-v1/image.png", "datasets/raw/mvtec_loco_ad/screw_bag/x.png"])
def test_excluded_data_paths_rejected_before_open(path):
    with pytest.raises(ValueError):
        m.local(ROOT, path)


def test_modified_plan_truth_is_rejected_without_loading_model(monkeypatch):
    records = [record(i) | {"file_name": f"synthetic/{i}.png"} for i in range(80)]
    baseline = [{"id": r["id"], "predictions": [prediction()]} for r in records]
    protocol = {"runtime_sha256": {}}
    folder = ROOT / m.TRAINING
    plan = {"schema": "kitguard.v08.grayscale-validation.plan.v1", "policy": m.POLICY,
            "versions": {}, "project_root": str(ROOT), "records": copy.deepcopy(records),
            "baseline": baseline, "training_protocol": protocol,
            "bindings": {str(Path(m.__file__).resolve()): "runner",
                         **{str(folder / name): digest for name, digest in m.PINS.items()}}}
    monkeypatch.setattr(m, "versions", dict)
    monkeypatch.setattr(m, "sha", lambda path: plan["bindings"][str(path)])
    def fake_read(path):
        return {"preflight.json": {"validation": records}, "best_validation_predictions.json": baseline,
                "protocol.json": protocol}[Path(path).name]
    monkeypatch.setattr(m, "read", fake_read)
    plan["records"][0]["ground_truth"][0]["label"] = 3
    with pytest.raises(ValueError, match="were edited"):
        m.verify(plan)


def test_actual_cpu_checkpoint_metadata_passes_with_only_class_key_normalization(monkeypatch):
    import torch
    folder = ROOT / m.TRAINING
    assert m.sha(folder / "best.pt") == m.PINS["best.pt"]
    checkpoint = torch.load(folder / "best.pt", map_location="cpu", weights_only=True)
    protocol, metrics = m.read(folder / "protocol.json"), m.read(folder / "best_validation_metrics.json")
    monkeypatch.setattr(m, "build_model", lambda: pytest.fail("No model construction allowed"))
    assert all(value.device.type == "cpu" for value in checkpoint["model"].values())
    assert checkpoint["config"] != protocol
    assert [key for key in checkpoint["config"] if checkpoint["config"][key] != protocol[key]] == ["classes"]
    assert m.normalized_checkpoint_config(checkpoint["config"]) == protocol
    m.validate_checkpoint(checkpoint, protocol, metrics)
    changed = {**checkpoint, "config": {**checkpoint["config"], "box_nms_thresh": .6}}
    with pytest.raises(ValueError, match="identity/config"):
        m.validate_checkpoint(changed, protocol, metrics)
    changed = {**checkpoint, "selected": {**checkpoint["selected"], "threshold": .6}}
    with pytest.raises(ValueError, match="identity/config"):
        m.validate_checkpoint(changed, protocol, metrics)
    changed = {**checkpoint, "config": {**checkpoint["config"], "classes": {1: "bolt", 2: "washer", 3: "nut"}}}
    with pytest.raises(ValueError, match="identity/config"):
        m.validate_checkpoint(changed, protocol, metrics)
    with pytest.raises(ValueError):
        m.normalized_checkpoint_config({"classes": {1: "bolt", "1": "bolt", 2: "nut", 3: "washer"}})
    with pytest.raises(ValueError):
        m.normalized_checkpoint_config({"classes": {1: "bolt", "2": "nut", "3": "washer"}})


def test_cli_failing_run_exits_nonzero(monkeypatch, tmp_path):
    monkeypatch.setattr(m.sys, "argv", ["gray", "run", "--plan", str(tmp_path / "plan.json"), "--output", str(tmp_path / "out")])
    monkeypatch.setattr(m, "run", lambda *_: False)
    with pytest.raises(SystemExit) as stopped:
        m.main()
    assert stopped.value.code == 1
