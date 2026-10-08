"""Read-only saved reference participation, without current-order reconstruction."""

from copy import deepcopy

from kitguard.evidence import _reference_evidence, render_viewer


def evidence():
    return {
        "images": [{"part": "nut", "image_index": 2, "prepared_size": [76, 76],
                    "photo_id": "<img src=x onerror=alert(1)>", "stored_sha256": "a" * 64,
                    "prepared_sha256": "b" * 64, "upload_source_sha256": "c" * 64}],
        "stages": [{"stage": "original", "reference_image_indices": [2], "status": "completed"},
                   {"stage": "rotate_90_ccw", "reference_image_indices": [2], "status": "completed"},
                   {"stage": "identity", "reference_image_indices": [], "status": "skipped_base_unclear"}],
        "prepared_bytes_retained": False, "pillow_version": "test", "preprocessing": "test",
    }


def test_offline_stages_escape_metadata_and_do_not_claim_identity_reference_use():
    check = {"reference_evidence": evidence()}
    before = deepcopy(check)
    html = _reference_evidence(check)
    assert check == before
    identity = html.split("data-reference-stage='identity'", 1)[1].split("</tr>", 1)[0]
    assert "未执行：前序不明确" in identity and "无类别参考输入" in identity
    assert "#2" not in identity
    assert "<img src=x" not in html and "&lt;img" in html
    assert "b" * 64 not in html.split("<details class='raw'>", 1)[0]
    assert "b" * 64 in html and "未单独保留其字节" in html


def test_legacy_viewer_never_borrows_current_reference_participation():
    payload = {"order": {"references": {"nut": {"id": "CURRENT_ONLY"}},
                         "checks": [{"id": "legacy", "reference_ids": {"nut": "old"}}]}, "photos": []}
    html = render_viewer(payload)
    section = html.split("<details class='reference-evidence'>", 1)[1].split("</details>", 1)[0]
    assert "未记录各阶段的参考输入" in section
    assert "CURRENT_ONLY" not in section
    assert "data-reference-stage=" not in section


def test_recorded_zero_references_is_distinct_from_missing_trace():
    html = _reference_evidence({"reference_evidence": {"images": [], "stages": [
        {"stage": "original", "reference_image_indices": [], "status": "completed"}]}})
    assert "无类别参考输入" in html and "未记录各阶段" not in html
    assert "data-reference-stage='identity'" not in html
