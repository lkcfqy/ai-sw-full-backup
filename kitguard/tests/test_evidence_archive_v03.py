"""Offline report safety and historical fidelity; all generated data are engineering fixtures."""

import json
import zipfile
from copy import deepcopy
from hashlib import sha256
from html.parser import HTMLParser
from io import BytesIO

import pytest

from kitguard.evidence import render_viewer


class ReportParser(HTMLParser):
    """Tiny semantic DOM for assertions without adding a runtime parser dependency."""

    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.root = {"tag": "root", "attrs": {}, "children": []}
        self.stack = [self.root]
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        node = {"tag": tag, "attrs": dict(attrs), "children": []}
        self.stack[-1]["children"].append(node)
        if tag not in {"meta", "img", "br", "hr", "input", "link"}:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index]["tag"] == tag:
                self.stack = self.stack[:index]
                return

    def handle_data(self, data):
        self.stack[-1]["children"].append(data)


def nodes(node, tag=None, **attrs):
    matched = []
    if isinstance(node, dict):
        if (tag is None or node["tag"] == tag) and all(node["attrs"].get(k) == v for k, v in attrs.items()):
            matched.append(node)
        for child in node["children"]:
            matched.extend(nodes(child, tag, **attrs))
    return matched


def content(node):
    return "".join(content(child) if isinstance(child, dict) else child for child in node["children"])


def table_values(check):
    values = {}
    for row in nodes(check, "tr"):
        if part := row["attrs"].get("data-part"):
            values[part] = {cell["attrs"]["data-value"]: content(cell) for cell in nodes(row, "td")}
    return values


@pytest.fixture
def report_payload():
    digest = "a" * 64
    point = {"part": "bolt", "center": [0.2, 0.3]}
    return {
        "schema_version": 2,
        "exported_at": "2026-09-26T12:00:00+00:00",
        "photos": [
            {
                "id": "synthetic-photo",
                "revision": 1,
                "archive_path": "photos/synthetic-photo.jpg",
                "sha256": digest,
            }
        ],
        "order": {
            "id": "synthetic-order",
            "title": "SYNTHETIC ENGINEERING REPORT",
            "revision": 9,
            "status": "pending",
            "requirements": {"bolt": 3, "nut": 3, "washer": 3, "bracket": 3},
            "completions": [],
            "checks": [
                {
                    "id": "synthetic-check",
                    "revision": 1,
                    "valid": False,
                    "decision": "recapture",
                    "photo_id": "synthetic-photo",
                    "photo_sha256": digest,
                    "created_at": "2026-09-26T11:00:00+00:00",
                    "model_label": "SYNTHETIC TEST FIXTURE ONLY",
                    "backend": "test",
                    "latency_ms": 1,
                    "requirements_snapshot": {"bolt": 1, "nut": 2, "washer": 0, "bracket": 0},
                    "observed": {"bolt": None, "nut": 1, "washer": 0, "bracket": 0},
                    "action": {"kind": "recapture", "message": "SYNTHETIC: take another photo"},
                    "object_evidence": {
                        "protocol": "spatial_inventory_v1",
                        "coordinate_frame": "normalized_original",
                        "objects": [point],
                    },
                    "observation_verification": {
                        "mode": "spatial_consensus",
                        "same_model_correlated_calls": True,
                        "counts_agree": False,
                        "clear_agreement": False,
                        "passes": [
                            {
                                "transform": "original",
                                "input_sha256": "b" * 64,
                                "observed": {"bolt": 1, "nut": 1, "washer": 0, "bracket": 0},
                                "objects": [point],
                            },
                            {
                                "transform": "rotate_90_ccw",
                                "input_sha256": "c" * 64,
                                "observed": {"bolt": 2, "nut": 1, "washer": 0, "bracket": 0},
                                "objects": [{"part": "bolt", "center": [0.9, 0.8]}],
                            },
                        ],
                    },
                }
            ],
        },
    }


def test_historical_counts_do_not_borrow_current_revision_or_replace_unknown(report_payload):
    original = deepcopy(report_payload)
    dom = ReportParser(render_viewer(report_payload)).root
    check = nodes(dom, "section", id="check-1")[0]
    assert table_values(check) == {
        "bolt": {"required": "1", "observed": "미확인未确认", "delta": "미확인 / 未确认"},
        "nut": {"required": "2", "observed": "1", "delta": "-1"},
        "washer": {"required": "0", "observed": "0", "delta": "0"},
        "bracket": {"required": "0", "observed": "0", "delta": "0"},
    }
    assert "· R1" in content(nodes(check, "h2")[0])
    assert "否 (false)" in content(nodes(check, "span", **{"class": "badge invalid"})[0])
    assert report_payload == original
    whole_json = nodes(dom, "pre")[-1]
    assert json.loads(content(whole_json)) == original


def test_absent_snapshot_and_null_values_stay_unknown(report_payload):
    check = report_payload["order"]["checks"][0]
    check.pop("requirements_snapshot")
    check["valid"] = None
    check["observed"] = {"bolt": None, "nut": False, "washer": "0", "bracket": -1}
    dom = ReportParser(render_viewer(report_payload)).root
    values = table_values(nodes(dom, "section", id="check-1")[0])
    assert all("未确认" in value for row in values.values() for value in row.values())
    assert "缺少当时需求快照；未用当前订单补填" in content(dom)
    assert "导出时有效：미확인 / 未确认" in content(dom)


def test_ready_is_not_completion_and_feedback_is_observation_only(report_payload):
    check = report_payload["order"]["checks"][0]
    check.update(decision="ready", valid=True)
    check["evidence_feedback"] = {
        "outcome": "improved",
        "message": "SYNTHETIC: uncertainty resolved",
        "previous_check_id": "prior-check",
        "previous_photo_id": "prior-photo",
        "resolved_uncertainties": ["bolt"],
        "remaining_uncertainties": [],
        "remaining_mismatches": ["nut"],
        "observed_changes": [{"part": "bolt", "before": None, "after": 1}],
        "physical_action_verified": False,
    }
    dom = ReportParser(render_viewer(report_payload)).root
    assert "仍须本人确认实物" in content(nodes(dom, "p", **{"class": "decision"})[0])
    feedback = nodes(dom, "div", **{"class": "feedback"})[0]
    assert "prior-check" in content(feedback) and "prior-photo" in content(feedback)
    assert "不证明实际移动了零件或完成现场纠正" in content(feedback)
    assert [content(c) for c in nodes(feedback, "td")] == ["미확인未确认", "1"]
    assert not nodes(dom, "form") and not nodes(dom, "button")


def test_directional_counts_do_not_fill_final_null_or_plot_rotated_points(report_payload):
    dom = ReportParser(render_viewer(report_payload)).root
    check = nodes(dom, "section", id="check-1")[0]
    assert "未确认" in table_values(check)["bolt"]["observed"]
    direction_row = nodes(check, "tr", **{"data-verification-part": "bolt"})[0]
    assert [content(c) for c in nodes(direction_row, "td")] == ["1", "2"]
    assert "不是独立专家核验" in content(check)
    markers = nodes(check, "span", **{"class": "point"})
    assert len(markers) == 1
    assert markers[0]["attrs"]["style"] == "left:20.00000%;top:30.00000%"
    assert "left:90.00000%" not in render_viewer(report_payload)


@pytest.mark.parametrize("fault", ["photo_hash", "coordinate_frame", "first_transform", "first_objects"])
def test_unverified_coordinate_association_suppresses_overlay(report_payload, fault):
    check = report_payload["order"]["checks"][0]
    if fault == "photo_hash":
        check["photo_sha256"] = "d" * 64
    elif fault == "coordinate_frame":
        check["object_evidence"]["coordinate_frame"] = "normalized_rotated"
    elif fault == "first_transform":
        check["observation_verification"]["passes"][0]["transform"] = "rotate_90_ccw"
    else:
        check["observation_verification"]["passes"][0]["objects"] = []
    dom = ReportParser(render_viewer(report_payload)).root
    assert not nodes(dom, "span", **{"class": "point"})
    assert "因此不叠加点位" in content(dom)
    assert json.loads(content(nodes(dom, "pre")[-1])) == report_payload


def test_public_demo_displays_provenance_as_text_and_never_implies_physical_completion(report_payload):
    report_payload["order"]["demo_source"] = {
        "kind": "public_photo_demo",
        "sample_id": "demo-1",
        "source_case_id": "source-1",
        "source_url": "https://example.invalid/never-request-this",
        "license": "CC BY-NC-SA 4.0",
        "source_sha256": "d" * 64,
        "source_note": "SYNTHETIC PROVENANCE TEST",
    }
    dom = ReportParser(render_viewer(report_payload)).root
    section = nodes(dom, "section", **{"class": "demo-source"})[0]
    assert "公开照片演示" in content(section) and "不能记为实体完工" in content(section)
    assert "CC BY-NC-SA 4.0" in content(section)
    assert "https://example.invalid/never-request-this" in content(section)
    assert not nodes(section, "a")


def test_all_untrusted_text_is_escaped_and_only_allowlisted_relative_resources_load(report_payload):
    attack = "</pre><script>alert(17)</script><img src=https://example.invalid/x onerror=alert(18)>\"'"
    report_payload["order"]["title"] = attack
    check = report_payload["order"]["checks"][0]
    check["action"]["message"] = attack
    check["model_label"] = attack
    check["evidence_feedback"] = {"message": attack}
    check["observation_verification"]["passes"][1]["transform"] = attack
    report_payload["photos"].extend(
        [
            {"id": "foreign", "archive_path": "https://example.invalid/private.jpg"},
            {"id": "traversal", "archive_path": "../../secret.jpg"},
            {"id": "file", "archive_path": "file:///etc/passwd"},
            {"id": attack, "archive_path": "photos/synthetic-photo.jpg"},
        ]
    )
    source = render_viewer(report_payload)
    dom = ReportParser(source).root
    assert not nodes(dom, "script") and not nodes(dom, "iframe") and not nodes(dom, "form")
    assert not any(key.lower().startswith("on") for node in nodes(dom) for key in node["attrs"])
    assert all(node["attrs"]["src"] == "photos/synthetic-photo.jpg" for node in nodes(dom, "img"))
    assert {n["attrs"]["href"] for n in nodes(dom, "a")} == {"evidence.json", "SHA256.json", "README.txt"}
    assert "&lt;script&gt;alert(17)&lt;/script&gt;" in source
    assert (
        "default-src 'none'"
        in nodes(dom, "meta", **{"http-equiv": "Content-Security-Policy"})[0]["attrs"]["content"]
    )
    assert json.loads(content(nodes(dom, "pre")[-1])) == report_payload


def test_new_archive_preserves_photo_bytes_and_hash_contract(client, order, inspected):
    saved = inspected["order"]
    photo = saved["photos"][0]
    photo_bytes = client.app.state.store.photo_path(photo["id"]).read_bytes()
    response = client.get(f"/api/orders/{order['id']}/evidence.zip")
    assert response.status_code == 200
    with zipfile.ZipFile(BytesIO(response.content)) as archive:
        records = json.loads(archive.read("SHA256.json"))
        for record in records:
            raw = archive.read(record["path"])
            assert record["bytes"] == len(raw)
            assert record["sha256"] == sha256(raw).hexdigest()
        assert archive.read(f"photos/{photo['id']}.jpg") == photo_bytes
        evidence = json.loads(archive.read("evidence.json"))
        assert evidence["order"] == saved
        dom = ReportParser(archive.read("OPEN_ME.html").decode()).root
        assert table_values(nodes(dom, "section", id="check-1")[0])["bolt"] == {
            "required": "2",
            "observed": "2",
            "delta": "0",
        }
        assert "仍须本人确认实物" in content(dom)


def identity_review_fixture():
    """Display fixture only; not a live identity inference or physical inspection."""
    return {
        "protocol": "identity_geometry_v2",
        "same_model_correlated_calls": True,
        "blocked_categories": ["bolt", "washer"],
        "source_sha256": "d" * 64,
        "full_input_sha256": "e" * 64,
        "response": {
            "objects": [
                {
                    "id": "p006",
                    "part": "bolt",
                    "status": "independent_object",
                    "opening": "closed_recess",
                    "issue": "",
                }
            ]
        },
        "crops": [
            {
                "id": "p006",
                "object_index": 6,
                "original_part": "washer",
                "center": [0.5, 0.5],
                "target_center_crop": [0.5, 0.5],
                "source_size": [640, 480],
                "rect_source_px": [260, 180, 380, 300],
                "crop_source_size": [120, 120],
                "crop_size": [512, 512],
                "resampling": "LANCZOS",
                "interpolation_creates_information": False,
                "source_sha256": "d" * 64,
                "crop_sha256": "f" * 64,
                "pixel_crop_sha256": "b" * 64,
                "crop_file": "p006.png",
                "pixel_crop_file": "p006-pixels.png",
            }
        ],
    }


@pytest.mark.parametrize("value", [None, {}])
def test_old_records_do_not_invent_identity_review(report_payload, value):
    baseline = render_viewer(report_payload)
    assert not nodes(ReportParser(baseline).root, "div", **{"class": "identity-verification"})
    report_payload["order"]["checks"][0]["identity_verification"] = value
    dom = ReportParser(render_viewer(report_payload)).root
    assert not nodes(dom, "div", **{"class": "identity-verification"})


def test_identity_report_shows_saved_categories_geometry_and_blocking_without_recount(report_payload):
    review = identity_review_fixture()
    check = report_payload["order"]["checks"][0]
    check["identity_verification"] = review
    before = deepcopy(report_payload)
    dom = ReportParser(render_viewer(report_payload)).root
    block = nodes(dom, "div", **{"class": "identity-verification"})[0]
    text = content(block)
    assert all(
        item in text
        for item in (
            "p006",
            "首轮",
            "와셔 / 垫圈",
            "复核",
            "나사류 / 螺纹件",
            "독립 물체 / 独立物体",
            "막힌 홈 / 封闭凹槽",
            "置为未确认的类别",
            "不是独立验证或几何实测",
            "不重新赋整数计数",
            "图像插值不创造新信息",
            "不能发现遗漏物体",
            "不表示这些裁剪图已附在证据包内",
        )
    )
    assert "未确认" in table_values(nodes(dom, "section", id="check-1")[0])["bolt"]["observed"]
    crop = nodes(block, "details", **{"class": "identity-crop"})[0]
    assert all(item in content(crop) for item in ("[0.5, 0.5]", "[512, 512]", "LANCZOS", "f" * 64, "b" * 64))
    assert "否 (false)" in content(crop)
    assert not nodes(block, "img") and not nodes(block, "a")
    assert json.loads(content(nodes(block, "pre")[-1])) == review
    assert report_payload == before


def test_identity_report_missing_or_duplicate_crop_ids_do_not_guess_original_class(report_payload):
    review = identity_review_fixture()
    review["crops"] *= 2
    report_payload["order"]["checks"][0]["identity_verification"] = review
    dom = ReportParser(render_viewer(report_payload)).root
    row = nodes(dom, "tr", **{"class": "identity-target"})[0]
    classification = content(nodes(row, "td")[0])
    assert "未记录" in classification and "垫圈" not in classification
    assert "螺纹件" in classification


def test_identity_report_escapes_hostile_response_and_metadata_as_inert_text(report_payload):
    attack = "</td><img src='https://example.invalid/x' onerror='alert(33)'><script>alert(34)</script>"
    review = identity_review_fixture()
    review["response"]["objects"][0].update(
        id=attack, part=attack, status=attack, opening=attack, issue=attack
    )
    review["crops"][0].update(
        id=attack, original_part=attack, crop_file="../../SECRET.jpg", pixel_crop_file=attack
    )
    review["blocked_categories"] = [attack, None]
    report_payload["order"]["checks"][0]["identity_verification"] = review
    source = render_viewer(report_payload)
    dom = ReportParser(source).root
    block = nodes(dom, "div", **{"class": "identity-verification"})[0]
    assert not nodes(block, "script") and not nodes(block, "img") and not nodes(block, "a")
    assert not any(key.startswith("on") for node in nodes(block) for key in node["attrs"])
    assert "../../SECRET.jpg" in content(block)
    assert "&lt;script&gt;alert(34)&lt;/script&gt;" in source
    assert json.loads(content(nodes(block, "pre")[-1])) == review
