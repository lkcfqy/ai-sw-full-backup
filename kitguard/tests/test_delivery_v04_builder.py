"""Portable delivery is grounded in files; no model/field-performance claim."""
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("delivery_v04", Path(__file__).resolve().parents[1] / "scripts/build_v04_delivery.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_preparation_has_no_invented_final_tests_or_field_samples(tmp_path):
    output = tmp_path / "preview"
    manifest = MODULE.build(output, root=tmp_path)
    assert not manifest["final"]
    assert manifest["summary"]["human_field_samples"] == 0
    assert "final_tests" not in manifest["summary"]
    text = (output / "index.html").read_text()
    assert "等待最终测试文件" in text
    assert "恒定回答1即可20/20" in text
    assert "准备预览" in text
    for name, digest in MODULE.read_json(output / "SHA256.json").items():
        assert MODULE.sha(output / name) == digest


def test_existing_delivery_is_never_overwritten(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    (output / "keep.txt").write_text("historical")
    with pytest.raises(ValueError, match="overwrite"):
        MODULE.build(output, root=tmp_path)
    assert (output / "keep.txt").read_text() == "historical"


def test_final_requires_real_missing_inputs(tmp_path):
    with pytest.raises(ValueError, match="Final delivery missing"):
        MODULE.build(tmp_path / "final", root=tmp_path, final=True)
    assert not (tmp_path / "final").exists()


def test_junit_counts_come_from_actual_file_and_failures_preserved(tmp_path):
    source = tmp_path / "tests.xml"
    source.write_text('<testsuites><testsuite tests="7" failures="1" errors="1" skipped="2"/></testsuites>')
    manifest = MODULE.build(tmp_path / "preview", root=tmp_path, overrides={"final_tests": source})
    assert manifest["summary"]["final_tests"] == {"tests": 7, "failures": 1, "errors": 1, "skipped": 2, "passed": 3}
    assert "失败" not in manifest["artifacts"][0]["title"]


def test_partial_row_count_does_not_drop_failed_predictions(tmp_path):
    source = tmp_path / "predictions.jsonl"
    source.write_text(json.dumps({"observed": {"bracket": 1}}) + '\n' + json.dumps({"error": "execution failed"}) + '\n')
    manifest = MODULE.build(tmp_path / "preview", root=tmp_path, overrides={"partial_predictions": source})
    assert manifest["summary"]["partial_prediction_records"] == 2
    assert "四类准确率" in (tmp_path / "preview/index.html").read_text()


def test_unsafe_external_or_contact_artifacts_rejected(tmp_path):
    outside = tmp_path.parent / "outside-delivery-review.json"
    outside.write_text('{}')
    with pytest.raises(ValueError, match="outside project"):
        MODULE.validated_file(outside, tmp_path)
    private = tmp_path / "private.md"
    private.write_text("test_person" + "@" + "gmail.com")
    with pytest.raises(ValueError, match="Personal contact"):
        MODULE.validated_file(private, tmp_path)
    symlink = tmp_path / "link.json"
    symlink.symlink_to(outside)
    with pytest.raises(ValueError, match="Symbolic"):
        MODULE.validated_file(symlink, tmp_path)
