"""Compare the shipped default expectation with actual observer source identity.

No model files or MLX runtime are required; this catches stale release pins that
synthetic health fixtures built from DEFAULT_EXPECTED_IDENTITY cannot detect.
"""

from pathlib import Path

from kitguard.readiness import DEFAULT_EXPECTED_IDENTITY
from kitguard.vision import LocalVision


def test_default_readiness_pin_matches_actual_guarded_source(tmp_path, monkeypatch):
    monkeypatch.delenv("KITGUARD_MODEL_PROFILE", raising=False)
    model = LocalVision(model_path=tmp_path / "Qwen3.6-27B-4bit",
                        observation_mode="spatial_guarded", image_max_side=1536)
    status = model.status()
    assert {key: status[key] for key in DEFAULT_EXPECTED_IDENTITY} == DEFAULT_EXPECTED_IDENTITY
    assert not status["available"]
    assert not Path(model.model_path).exists()
