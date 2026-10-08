"""Synthetic pixel contracts; no dataset/model access or image display."""
import importlib.util
from pathlib import Path

import pytest
from PIL import Image, PngImagePlugin

PATH = Path(__file__).resolve().parents[1] / "scripts/v08/preflight_loco_combined_sources.py"
spec = importlib.util.spec_from_file_location("loco_source_preflight", PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_reencoded_pixels_match_rgb_without_matching_bytes(tmp_path):
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    image = Image.new("RGB", (8, 6), (11, 22, 33))
    image.save(a, compress_level=0)
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("synthetic", "different bytes, identical pixels")
    image.save(b, compress_level=9, pnginfo=metadata)
    candidate, other = {"key": "candidate", **m.fingerprint(a)}, {"key": "prior", **m.fingerprint(b)}
    assert candidate["sha256"] != other["sha256"]
    assert candidate["rgb_sha256"] == other["rgb_sha256"]
    assert m.compare(candidate, [other])["matches"] == [
        {"comparator_key": "prior", "methods": ["original_dimension_bound_rgb"]}]


def test_dimension_binding_prevents_equal_byte_stream_false_match(tmp_path):
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    Image.new("RGB", (2, 6), "red").save(a)
    Image.new("RGB", (3, 4), "red").save(b)
    left, right = m.fingerprint(a), m.fingerprint(b)
    assert left["rgb_bytes_sha256"] == right["rgb_bytes_sha256"]
    assert left["rgb_sha256"] != right["rgb_sha256"]


def test_every_comparison_retained_and_unreadable_is_not_no_match():
    candidate = {"key": "new", "sha256": "a", "rgb_sha256": "b"}
    result = m.compare(candidate, [{"key": "same", "sha256": "a", "rgb_sha256": "b"},
                                    {"key": "different", "sha256": "c", "rgb_sha256": "d"},
                                    {"key": "failed", "error": "decode failed"}])
    assert result["matches"] == [{"comparator_key": "same", "methods": ["source_bytes", "original_dimension_bound_rgb"]}]
    assert result["no_match_keys"] == ["different"]
    assert result["unavailable_keys"] == ["failed"]
    assert len(result["matches"]) + len(result["no_match_keys"]) + len(result["unavailable_keys"]) == 3


def test_corrupt_image_and_outside_paths_fail_closed(tmp_path):
    bad = tmp_path / "invalid.png"
    bad.write_bytes(b"not an image")
    with pytest.raises(OSError):
        m.fingerprint(bad)
    with pytest.raises(ValueError):
        m.inside(tmp_path, "../outside.png")
    with pytest.raises(ValueError):
        m.inside(tmp_path, str(bad))


def test_historical_hash_is_not_replaced_by_current_document(tmp_path):
    path = tmp_path / "record.json"
    path.write_text("current text")
    original = "a" * 64
    registry = {"exposure": {"source": {"category": ["record.json"]}},
                "text_inputs": [{"path": "record.json", "sha256": original}],
                "source_receipts": [], "application_metadata": []}
    binding = m.historical_bindings(tmp_path, registry)[0]
    assert binding["historical_sha256"] == original
    assert binding["current_sha256"] == m.sha(path)
    assert binding["current_content_matches_historical"] is False
    assert registry["text_inputs"][0]["sha256"] == original


def test_cli_refuses_to_overwrite_before_decoding(tmp_path, monkeypatch):
    target = tmp_path / "existing.json"
    target.write_text("original")
    monkeypatch.setattr(m.sys, "argv", ["preflight", "--output", str(target)])
    monkeypatch.setattr(m, "preflight", lambda root: pytest.fail("must not decode"))
    with pytest.raises(ValueError, match="Output exists"):
        m.main()
    assert target.read_text() == "original"
