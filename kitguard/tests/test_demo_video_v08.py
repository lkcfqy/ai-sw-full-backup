"""Small source-binding contracts; no encoding/model/browser/new evaluation images."""
import copy
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/v08/build_demo_video.py"
spec = importlib.util.spec_from_file_location("demo_video_v08", SCRIPT)
video = importlib.util.module_from_spec(spec)
spec.loader.exec_module(video)


def test_actual_authorized_sources_and_135_second_plan():
    plan = video.load(video.PLAN)
    assert video.validate_plan(plan) == 135
    index = video.source_index(plan)
    assert len(index["inputs"]) == 10
    assert index["human_participants"] == index["additional_model_calls"] == 0


@pytest.mark.parametrize("field,value", [("latency_ms", 51488), ("backend", "test"), ("valid", True)])
def test_reject_wrong_case_timing_backend_or_currentness(monkeypatch, field, value):
    original_load = video.load

    def modified(path):
        data = copy.deepcopy(original_load(path))
        if Path(path).name == "order.json":
            data["order"]["checks"][0][field] = value
        return data

    monkeypatch.setattr(video, "load", modified)
    with pytest.raises(ValueError):
        video.source_index(video.load(video.PLAN))


def test_reject_duplicate_capture_and_overlong_timeline():
    plan = video.load(video.PLAN)
    plan["scenes"][0]["seconds"] = 181
    with pytest.raises(ValueError, match="timeline"):
        video.validate_plan(plan)
