"""Synthetic export rendering: user statements never become source certification."""
from copy import deepcopy

import pytest

from kitguard.evidence import render_viewer
from kitguard.public_review import digest


def payload():
    check = {"id": "synthetic-check", "revision": 2, "evidence_epoch": 4, "photo_id": "synthetic-photo",
             "valid": True, "decision": "ready", "backend": "test", "action": {"kind": "none", "message": "SYNTHETIC"}}
    source = {"schema_version": 1, "kind": "user_declared_photo", "verification": "user_declared_unverified",
              "physical_completion_allowed": False, "source_note": "<script>UNTRUSTED NOTE</script>",
              "source_url": "javascript:alert(1)", "license_note": "CLAIM ONLY <img onerror=x>",
              "source_sha256": "a" * 64, "storage_sha256": "b" * 64,
              "statement_sha256": "c" * 64, "binding_sha256": "d" * 64,
              "original_root_photo_id": "synthetic-root", "declared_at": "2026-01-01T00:00:00Z"}
    review = {"revision": 2, "evidence_epoch": 4, "photo_id": "synthetic-photo", "check_id": check["id"],
              "check_sha256": digest(check), "conclusion": "disputed", "ai_decision": "ready",
              "operator_code": "SYNTHETIC", "note": "Synthetic display contract", "user_validation": False}
    return {"order": {"title": "SYNTHETIC PHOTO DOCUMENT", "revision": 2, "evidence_epoch": 4,
                      "document_source": source, "photos": [{"id": "synthetic-photo"}],
                      "checks": [check], "latest_check": check, "public_reviews": [review],
                      "public_replays": [{"revision": 2, "physical_capture": False}], "completions": []},
            "photos": []}


def test_unverified_statement_and_digital_result_are_explicit_and_read_only():
    data = payload()
    before = deepcopy(data)
    html = render_viewer(data)
    assert "사용자 진술 · 출처와 이용 조건 미검증" in html
    assert "用户自报 · 来源与使用条件未核实" in html
    assert "照片资料数量相符 · 非实物完工" in html
    assert "历史记录 · 不适用于当前核验 · 不代表已解决" in html and "不同意 AI 判断" in html
    assert "对应导出时当前核验" not in html
    assert "不计为 AI 准确率、实物完工、出库或用户试验成绩" in html
    assert "同一资料照片回放" in html and "不代表重新拍摄或实物发生变化" in html
    assert "&lt;script&gt;UNTRUSTED NOTE&lt;/script&gt;" in html
    assert "CLAIM ONLY &lt;img onerror=x&gt;" in html
    assert "<script>" not in html and "href='javascript:" not in html
    assert "照片与声明关联记录" in html and "c" * 64 in html and "d" * 64 in html
    assert "공학 테스트 기록" in html
    assert data == before


@pytest.mark.parametrize("field", ["revision", "evidence_epoch"])
def test_document_review_old_scope_is_not_current(field):
    data = payload()
    data["order"][field] += 1
    html = render_viewer(data)
    assert "历史记录 · 不适用于当前核验" in html
    assert "对应导出时当前核验" not in html


def test_legacy_order_has_no_backfilled_statement_and_catalog_keeps_its_license():
    data = payload()
    del data["order"]["document_source"]
    html = render_viewer(data)
    assert "data-source-verification='user_declared_unverified'" not in html
    assert "来源声明 SHA-256" not in html
    data["order"]["demo_source"] = {"kind": "public_photo_demo", "license": "SYNTHETIC CATALOG LICENSE"}
    html = render_viewer(data)
    assert "公开照片演示" in html and "SYNTHETIC CATALOG LICENSE" in html
    assert "公开照片数量相符 · 非实物完工" in html
    assert "data-source-verification='user_declared_unverified'" not in html
