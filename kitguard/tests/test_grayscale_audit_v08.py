"""Independent audit contracts using synthetic bytes; no detector/model calls."""
import copy
import hashlib
import importlib.util
import struct
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("gray_independent_audit", ROOT / "scripts/v08/audit_grayscale_validation.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def record(i=1, source="foda"):
    return {"id": str(i), "source": source, "group_id": "g" if source == "foda" else str(i),
            "source_sha256": "a" * 64, "image_size": [20, 20],
            "ground_truth": [{"label": 2, "box": [1, 1, 10, 10]}]}


def pred(label=2, score=.5, box=None):
    return {"label": label, "score": score, "box": box or [1, 1, 10, 10]}


def test_no_model_modules_imported():
    p = subprocess.run([sys.executable, "-I", "-c",
                        "import runpy,sys;runpy.run_path(sys.argv[1]);assert not any(n in sys.modules for n in ['torch','torchvision','mlx','mlx_vlm','kitguard'])",
                        m.__file__], capture_output=True, text=True, check=False)
    assert p.returncode == 0, p.stderr


def test_incomplete_run_rejected_before_predictions(tmp_path):
    (tmp_path / "run.json").write_text('{"status":"running"}')
    with pytest.raises(ValueError, match="Only completed"):
        m.audit(tmp_path)


def test_tensor_all_256_values_against_ieee_fp32_bytes(tmp_path):
    path = tmp_path / "gray.png"
    image = Image.frombytes("L", (256, 1), bytes(range(256))).convert("RGB")
    image.save(path)
    pixels = hashlib.sha256(b"(256, 1)|RGB|" + image.tobytes()).hexdigest()
    expected = b"".join(struct.pack("<f" if sys.byteorder == "little" else ">f", i / 255.0)
                        for i in range(256)) * 3
    row = {"input_size": [256, 1], "grayscale_rgb_sha256": pixels,
           "tensor": {"shape": [3, 1, 256], "dtype": "float32", "byteorder": sys.byteorder,
                      "sha256": hashlib.sha256(expected).hexdigest()}}
    m.reconstruct_tensor(path, {"id": "synthetic", "image_size": [256, 1]}, row)
    row["tensor"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="tensor differs"):
        m.reconstruct_tensor(path, {"id": "synthetic", "image_size": [256, 1]}, row)


def test_every_raw_box_must_survive_scoring_projection():
    items = [pred(2, .5), pred(3, .1)]
    row = {"predictions": items, "model_call_started": True, "model_call_completed": True,
           "raw_detector_output": {"boxes": [p["box"] for p in items], "labels": [2, 3], "scores": [.5, .1]}}
    assert m.validate_raw(record(), row, m.independent_metrics()) == 2
    broken = copy.deepcopy(row)
    broken["predictions"] = broken["predictions"][:1]
    with pytest.raises(ValueError, match="filter/change"):
        m.validate_raw(record(), broken, m.independent_metrics())


def test_geometry_class_confusion_needs_iou_and_unique_truth():
    items = [pred(3, .99, [11, 11, 19, 19]), pred(3, .9), pred(3, .8), pred(2, .7)]
    got = m.geometry_confusion(record(), items, m.independent_metrics())
    assert got["nut_to_washer"] == 1 and len(got["matches"]) == 1
    assert got["matches"][0]["prediction_index"] == 1


def test_complete80_denominator_and_error_never_scores_as_empty_success():
    records = [record(i, "screws" if i < 44 else "foda") for i in range(80)]
    baseline = [{"id": r["id"], "predictions": [pred(3)]} for r in records]
    rows = [{"id": r["id"], "source_sha256": r["source_sha256"], "status": "not_attempted"} for r in records]
    rows[0].update(status="ok", predictions=[pred(2)])
    rows[1].update(status="failed", error="failed", predictions=[pred(2)])
    got = m.recompute(records, baseline, rows, m.independent_metrics())
    assert got["all"]["planned"] == 80 and got["all"]["completed"] == 1
    assert got["all"]["failed"] == 1 and got["all"]["not_attempted"] == 78
    assert got["all"]["gray_exact_count_fraction_of_planned"] == 1 / 80
    assert got["all"]["inexact_to_exact"] == ["0"]
    assert got["all"]["rgb_nut_to_washer"] == 80
    assert got["all"]["gray_measured_nut_to_washer"] == 0
    assert got["all"]["unmeasured_nut_gt"] == 79
    assert got["cases"][1]["gray_metrics"] is None
