"""Digital opinions stay distinct from physical completion in portable exports."""

from copy import deepcopy

import pytest

from kitguard.evidence import render_viewer
from kitguard.public_review import digest


def payload():
    check = {"id": "fixture-check", "revision": 2, "evidence_epoch": 4, "photo_id": "fixture-photo",
             "valid": True, "decision": "ready", "backend": "test"}
    review = {"revision": 2, "evidence_epoch": 4, "photo_id": "fixture-photo", "check_id": "fixture-check",
              "check_sha256": digest(check), "conclusion": "disputed", "ai_decision": "ready",
              "operator_code": "fixture-reviewer", "note": "<script>unsafe</script> should be displayed as text"}
    return {"order": {"title": "ENGINEERING FIXTURE", "revision": 2, "evidence_epoch": 4,
                      "demo_source": {"kind": "public_photo_demo"}, "photos": [{"id": "fixture-photo"}],
                      "checks": [check], "latest_check": check, "public_reviews": [review], "completions": []},
            "photos": []}


def test_disagreement_keeps_ai_ready_and_does_not_become_physical_completion():
    data = payload()
    original = deepcopy(data)
    result = render_viewer(data)
    assert "不同意 AI 判断" in result
    assert "公开照片数量相符 · 非实物完工" in result
    # Incomplete legacy test-backend records are visible as history, never current.
    assert "历史记录 · 不适用于当前核验 · 不代表已解决" in result
    assert "对应导出时当前核验" not in result
    assert "不计为 AI 准确率、实物完工、出库或用户试验成绩" in result
    assert "&lt;script&gt;unsafe&lt;/script&gt;" in result and "<script>" not in result
    assert data == original


@pytest.mark.parametrize("change", ["revision", "epoch", "check", "photo", "content", "invalid"])
def test_changed_evidence_does_not_display_old_review_as_current(change):
    data = payload()
    order = data["order"]
    if change == "revision":
        order["revision"] += 1
    elif change == "epoch":
        order["evidence_epoch"] += 1
    elif change == "check":
        order["latest_check"]["id"] = "different-check"
    elif change == "photo":
        order["photos"].append({"id": "different-photo"})
    elif change == "content":
        order["latest_check"]["decision"] = "recapture"
    else:
        order["latest_check"]["valid"] = False
    result = render_viewer(data)
    assert "历史记录 · 不适用于当前核验" in result
    assert "对应导出时当前核验" not in result
