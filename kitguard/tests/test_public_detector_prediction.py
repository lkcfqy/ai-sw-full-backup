"""Pure postprocessing/EXIF checks; no model loading, downloads or inference."""

import math

import pytest
from PIL import Image

from scripts.predict_public_detector import (
    frozen_threshold,
    oriented_rgb,
    summarize_predictions,
    write_result,
)


def checkpoint_metadata(threshold):
    return {"selected": {"threshold": threshold},
            "config": {"classes": {1: "bolt", 2: "nut"}, "model": "fasterrcnn_mobilenet_v3_large_320_fpn"}}


def test_checkpoint_threshold_is_used_without_order_adjustment():
    threshold = frozen_threshold(checkpoint_metadata(0.6))
    result = summarize_predictions([1, 1, 2], [[0, 0, 2, 2], [2, 0, 4, 2], [0, 3, 2, 5]],
                                   [0.59, 0.6, 0.9], threshold, (10, 8))
    assert result["counts"] == {"bolt": 1, "nut": 1, "washer": None, "bracket": None}
    assert len(result["predictions"]) == 3
    assert [p["retained_at_frozen_threshold"] for p in result["predictions"]] == [False, True, True]
    assert result["unsupported_classes"] == ["washer", "bracket"]
    assert result["decision"] is None


@pytest.mark.parametrize("threshold", [None, True, -0.1, 1.1, math.nan, math.inf, "0.5"])
def test_invalid_threshold_cannot_silently_default(threshold):
    with pytest.raises(ValueError):
        frozen_threshold(checkpoint_metadata(threshold))


def test_incompatible_checkpoint_mapping_is_rejected():
    state = checkpoint_metadata(0.5)
    state["config"]["classes"] = {1: "nut", 2: "bolt"}
    with pytest.raises(ValueError, match="class 1=bolt"):
        frozen_threshold(state)


def test_empty_predictions_leave_unsupported_classes_unknown():
    result = summarize_predictions([], [], [], 0.5, (10, 8))
    assert result["counts"] == {"bolt": 0, "nut": 0, "washer": None, "bracket": None}
    assert result["decision"] is None


@pytest.mark.parametrize("labels,boxes,scores", [
    ([3], [[0, 0, 2, 2]], [0.9]),
    ([1], [[0, 0, 2, 2]], [math.nan]),
    ([1], [[0, 0, 11, 2]], [0.9]),
    ([1], [[0, 0, 0, 2]], [0.9]),
    ([1], [[0, 0, 2, 2]], []),
])
def test_invalid_predictions_are_rejected_before_threshold_filter(labels, boxes, scores):
    with pytest.raises(ValueError):
        summarize_predictions(labels, boxes, scores, 1.0, (10, 8))


def test_exif_rotation_defines_output_coordinate_frame(tmp_path):
    path = tmp_path / "oriented.jpg"
    image = Image.new("RGB", (12, 8), "red")
    exif = Image.Exif()
    exif[274] = 6
    image.save(path, exif=exif)
    rgb, metadata = oriented_rgb(path)
    assert rgb.mode == "RGB" and rgb.size == (8, 12)
    assert metadata["encoded_image_size"] == [12, 8]
    assert metadata["image_size"] == [8, 12]
    assert metadata["source_exif_orientation"] == 6
    assert "EXIF-oriented" in metadata["coordinate_frame"]


def test_result_cannot_overwrite_existing_evidence(tmp_path):
    output = tmp_path / "prediction.json"
    write_result(output, {"decision": None})
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        write_result(output, {"decision": "changed"})
    assert output.read_bytes() == before
