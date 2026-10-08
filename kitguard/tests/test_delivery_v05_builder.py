"""Small independent failure cases for the portable v0.5 delivery gate."""

import hashlib
import importlib.util
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

SPEC = importlib.util.spec_from_file_location("delivery_v05", Path(__file__).resolve().parents[1] / "scripts/build_v05_delivery.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return path


def test_preview_is_pending_and_does_not_invent_test_total(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    result = builder.build(tmp_path / "preview", root=root)
    assert result["final"] is False
    assert "final_tests" not in result["summary"]
    assert "final_tests" in result["summary"]["pending_required_roles"]
    assert "pending" in (tmp_path / "preview/index.html").read_text()
    for name, expected in json.loads((tmp_path / "preview/SHA256.json").read_text()).items():
        assert builder.sha(tmp_path / "preview" / name) == expected


def test_final_missing_evidence_does_not_publish(tmp_path):
    with pytest.raises(ValueError, match="Final delivery missing"):
        builder.build(tmp_path / "final", root=tmp_path, final=True)
    assert not (tmp_path / "final").exists()


def test_existing_delivery_is_never_overwritten(tmp_path):
    target = tmp_path / "existing"
    target.mkdir()
    sentinel = target / "keep.txt"
    sentinel.write_text("unchanged")
    with pytest.raises(ValueError, match="overwrite"):
        builder.build(target, root=tmp_path)
    assert sentinel.read_text() == "unchanged"


@pytest.mark.parametrize("declared", [2, 999])
def test_declared_test_count_cannot_inflate_actual_cases(tmp_path, declared):
    xml = tmp_path / "suite.xml"
    xml.write_text(f'<testsuites><testsuite tests="{declared}" failures="0" errors="0" skipped="0"><testcase name="one"/></testsuite></testsuites>')
    with pytest.raises(ValueError, match="actual testcase"):
        builder.strict_junit(xml)


def test_source_zip_manifest_cannot_hide_changed_bytes(tmp_path):
    target = tmp_path / "source.zip"
    manifest = {"files": [{"path": "app.py", "bytes": 4, "sha256": hashlib.sha256(b"good").hexdigest()}]}
    with ZipFile(target, "w") as archive:
        archive.writestr("KitGuard/SOURCE_MANIFEST.json", json.dumps(manifest))
        archive.writestr("KitGuard/app.py", b"evil")
    with pytest.raises(ValueError, match="hash mismatch"):
        builder.source_members(target)


def test_source_zip_manifest_cannot_omit_extra_member(tmp_path):
    target = tmp_path / "source.zip"
    with ZipFile(target, "w") as archive:
        archive.writestr("KitGuard/SOURCE_MANIFEST.json", '{"files": []}')
        archive.writestr("KitGuard/unlisted.py", b"extra")
    with pytest.raises(ValueError, match="member set"):
        builder.source_members(target)


def test_engineering_receipt_cannot_bind_another_export(tmp_path):
    export = write_json(tmp_path / "export.json", {"study": {"id": "s", "source_kind": "engineering_fixture"}})
    receipt = write_json(tmp_path / "receipt.json", {
        "status": "verified_internal_consistency", "errors": [], "input_sha256": "0" * 64,
        "study_id": "s", "source_kind": "engineering_fixture", "physical_authenticity_verified": False,
        "photo_bytes_verified": False,
    })
    with pytest.raises(ValueError, match="bind"):
        builder.verify_engineering(export, receipt)


def test_evidence_zip_requires_both_exact_root_and_view(tmp_path):
    path = tmp_path / "photos.zip"
    digest = hashlib.sha256(b"view").hexdigest()
    with ZipFile(path, "w") as archive:
        archive.writestr("photos/view.jpg", b"view")
        archive.writestr("SHA256.json", json.dumps([{"path": "photos/view.jpg", "bytes": 4, "sha256": digest}]))
    with pytest.raises(ValueError, match="root/view"):
        builder.evidence_zip(path, [digest, "0" * 64])


def test_real_verification_refuses_one_attempt_before_any_other_gate(tmp_path):
    paths = {
        "real_result": write_json(tmp_path / "result.json", {}),
        "real_verification": write_json(tmp_path / "verification.json", {"status": "verified", "attempted_inspections": 1}),
    }
    with pytest.raises(ValueError, match="two attempts"):
        builder.verify_real(paths)
