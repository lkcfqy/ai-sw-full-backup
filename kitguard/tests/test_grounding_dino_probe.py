"""CPU engineering fixtures for phrase ambiguity and detector probe accounting."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

PATH = Path(__file__).resolve().parents[1] / "scripts/probe_grounding_dino_detector.py"
SPEC = importlib.util.spec_from_file_location("dino_probe", PATH)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


@pytest.mark.parametrize(
    ("phrase", "part"),
    [
        ("a metal screw or bolt", "bolt"),
        ("metal nut", "nut"),
        ("washer", "washer"),
        ("L-shaped metal bracket", "bracket"),
        ("nut washer", None),
        ("metal", None),
        ("", None),
        ("nutrient", None),
        ("bolt bracket", None),
    ],
)
def test_phrase_requires_exactly_one_whole_word_category(phrase, part):
    assert probe.map_phrase(phrase) == part


def test_unmapped_boxes_are_retained_without_class_forcing():
    import torch
    from PIL import Image

    class Processor:
        tokenizer = SimpleNamespace(convert_ids_to_tokens=lambda ids: [str(i) for i in ids])

        def __call__(self, **kwargs):
            assert set(kwargs) == {"images", "text", "return_tensors"}
            assert kwargs["text"] == "fixed caption"
            return {"pixel_values": torch.zeros((1, 3, 2, 2)), "input_ids": torch.tensor([[1, 2, 3]])}

        def post_process_grounded_object_detection(self, outputs, **kwargs):
            assert kwargs["threshold"] == 0.4
            assert kwargs["text_threshold"] == 0.3
            return [
                {
                    "boxes": torch.tensor([[0, 0, 2, 2]] * 3),
                    "scores": torch.tensor([0.95, 0.88, 0.98]),
                    "text_labels": ["metal nut", "nut washer", "metal"],
                }
            ]

    def model(**inputs):
        assert all(item.device.type == "cpu" for item in inputs.values())
        return SimpleNamespace(
            logits=torch.tensor([[[-2.0, 3.0], [-3.0, 2.0], [-1.0, 4.0]]]),
            pred_boxes=torch.ones((1, 3, 4)) / 2,
        )

    values, raw = probe.infer(
        Image.new("RGB", (8, 8)), Processor(), model, torch, "fixed caption", 0.4, 0.3, 0.5
    )
    assert len(values["pre_nms"]) == 3
    assert len(values["unmapped"]) == 2
    assert values["counts"] == {"bolt": 0, "nut": 1, "washer": 0, "bracket": 0}
    assert raw["logits"].shape == (3, 2)
    truth = [{"annotation_id": 1, "part": "nut", "box_xyxy": [0, 0, 2, 2]}]
    matched = probe.match_boxes(values["post_nms"] + values["unmapped"], truth)
    assert (matched["tp"], matched["fp"], matched["fn"]) == (1, 2, 0)
