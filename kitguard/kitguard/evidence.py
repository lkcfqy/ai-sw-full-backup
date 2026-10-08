"""Portable, read-only evidence archives with photographs and verifiable digests."""

from __future__ import annotations

import hashlib
import html
import json
import re
import tempfile
import zipfile
from pathlib import Path

from .digital_resolution import current_resolution
from .digital_review_state import derive_digital_review_feedback
from .photo_documents import is_digital_only
from .regions import inspection_scope, scope_html, verify_photo_lineage
from .store import StateError, now

LIMITATIONS = [
    "Stored photos are normalized copies; original uploads are represented by their source SHA-256 only.",
    "Photo hashes provide traceability, not proof of scene authenticity or physical action.",
    "Model observations are fallible. Completion records represent an operator confirmation, not certification.",
    "Images and text may be private; export does not grant permission for redistribution.",
]


def build_evidence_archive(store, order_id):
    """Snapshot only one order and its linked photographs; never export the database."""
    order = store.get(order_id)
    for photograph in order.get("photos", []):
        verify_photo_lineage(store, order, photograph)
    photos = {item["id"]: item for item in order.get("photos", [])}
    for entry in order.get("reference_history", []):
        photos[entry["photo"]["id"]] = entry["photo"]
    for item in order.get("references", {}).values():
        photos[item["id"]] = item
    payload = {
        "schema_version": 2,
        "exported_at": now(),
        "order": order,
        "limitations": LIMITATIONS,
        "photos": [],
    }
    with tempfile.NamedTemporaryFile(prefix="kitguard-evidence-", suffix=".zip", delete=False) as handle:
        archive_path = Path(handle.name)
    try:
        manifest = []
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
            for photo_id, metadata in photos.items():
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", photo_id):
                    raise StateError("사진 식별자가 올바르지 않습니다 / 照片标识无效", 409)
                raw = store.photo_path(photo_id).read_bytes()
                digest = hashlib.sha256(raw).hexdigest()
                if digest != metadata.get("sha256"):
                    raise StateError("사진 무결성 확인 실패 / 照片完整性校验失败", 409)
                relative = f"photos/{photo_id}.jpg"
                archive.writestr(relative, raw)
                manifest.append({"path": relative, "bytes": len(raw), "sha256": digest})
                payload["photos"].append({**metadata, "id": photo_id, "archive_path": relative})
            json_bytes = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode()
            archive.writestr("evidence.json", json_bytes)
            manifest.append(
                {
                    "path": "evidence.json",
                    "bytes": len(json_bytes),
                    "sha256": hashlib.sha256(json_bytes).hexdigest(),
                }
            )
            viewer = render_viewer(payload).encode()
            archive.writestr("OPEN_ME.html", viewer)
            manifest.append(
                {"path": "OPEN_ME.html", "bytes": len(viewer), "sha256": hashlib.sha256(viewer).hexdigest()}
            )
            archive.writestr("SHA256.json", json.dumps(manifest, indent=2) + "\n")
            archive.writestr(
                "README.txt",
                "KitGuard evidence archive / 증거 묶음 / 证据包\n\nExtract the ZIP, then open OPEN_ME.html. No server or Internet needed.\nRead evidence.json for full event, reference, revision, check and confirmation history.\nSHA256.json hashes all evidence and viewer files; it is not a digital signature.\nThe export is a snapshot and cannot be imported as a new approval.\n\n"
                + "\n".join(LIMITATIONS)
                + "\n",
            )
        return archive_path
    except BaseException:
        archive_path.unlink(missing_ok=True)
        raise


_PART_LABELS = {
    "bolt": "나사류 / 螺纹件",
    "nut": "너트 / 螺母",
    "washer": "와셔 / 垫圈",
    "bracket": "브래킷 / 角码",
}
_DECISIONS = {
    "ready": "수량 일치 · 담당자 실물 확인 필요 / 数量相符 · 仍须本人确认实物",
    "correct": "수량 조정 필요 / 需要调整数量",
    "recapture": "추가 사진 필요 / 需要补充照片",
    "manual": "사람의 확인 필요 / 需要人工核查",
}
_ACTIONS = {
    "none": "추가 자동 조치 없음 / 无额外自动动作",
    "add_remove": "수량 수정 후 새 사진 / 调整数量后重新拍照",
    "recapture": "다시 촬영 / 重新拍摄",
    "separate": "물체를 분리해 촬영 / 分开物体后拍摄",
    "manual": "사람의 확인 / 人工核查",
}
_UNKNOWN = "미확인 / 未确认"
_MISSING = "미기록 / 未记录"


def _esc(value):
    return html.escape(str(value), quote=True)


def _text(value):
    return _esc(_MISSING if value is None or value == "" else value)


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _records(value):
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _count(value):
    return value if type(value) is int and value >= 0 else None


def _quantity(value):
    number = _count(value)
    return str(number) if number is not None else "미확인<br>未确认"


def _flag(value):
    if value is True:
        return "예 / 是 (true)"
    if value is False:
        return "아니요 / 否 (false)"
    return _UNKNOWN


def _facts(items):
    return (
        "<dl class='facts'>"
        + "".join(f"<div><dt>{_esc(label)}</dt><dd>{_text(value)}</dd></div>" for label, value in items)
        + "</dl>"
    )


def _json_details(title, value):
    return (
        f"<details class='raw'><summary>{_esc(title)}</summary>"
        f"<pre>{_esc(json.dumps(value, ensure_ascii=False, indent=2))}</pre></details>"
    )


def _safe_photo_path(photo):
    photo_id, path = photo.get("id"), photo.get("archive_path")
    if (
        isinstance(photo_id, str)
        and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", photo_id)
        and path == f"photos/{photo_id}.jpg"
    ):
        return path
    return None


def _reference_evidence(check):
    """Only this check's saved inputs; never reconstruct history from current refs."""
    evidence = _mapping(check.get("reference_evidence"))
    opening = "<details class='reference-evidence'><summary>기준 사진 입력 기록 / 参考图参与记录</summary>"
    if not evidence:
        return opening + "<p>단계별 기준 입력 미기록 · 현재 사진으로 채우지 않음 / 未记录各阶段的参考输入，不用当前参考图补填。</p></details>"
    images, stages = _records(evidence.get("images")), _records(evidence.get("stages"))
    names = {"original": "원래 방향 / 原始方向", "rotate_90_ccw": "회전 방향 / 旋转方向", "identity": "국소 종류 재확인 / 局部身份复核"}
    statuses = {"completed": "완료 / 已完成", "attempted": "시도 / 已尝试", "failed": "실패 / 失败",
                "skipped_base_unclear": "미실행: 앞선 관찰 불명확 / 未执行：前序不明确",
                "skipped_no_candidates": "미실행: 후보 없음 / 未执行：没有候选"}
    rows = []
    for stage in stages:
        indices = stage.get("reference_image_indices")
        supplied = _MISSING
        if isinstance(indices, list):
            labels = []
            for index in indices:
                image = next((i for i in images if i.get("image_index") == index), {})
                part = image.get("part")
                labels.append(f"#{index} · {_PART_LABELS.get(part, _MISSING) if isinstance(part, str) else _MISSING}")
            supplied = ", ".join(labels) if labels else "종류별 기준 입력 없음 / 无类别参考输入"
        name, status = stage.get("stage"), stage.get("status")
        rows.append(f"<tr data-reference-stage='{_esc(name)}'><th scope='row'>{_text(names.get(name) if isinstance(name, str) else None)}</th>"
                    f"<td>{_text(statuses.get(status) if isinstance(status, str) else None)}</td><td>{_esc(supplied)}</td></tr>")
    facts = []
    for image in images:
        size, part = image.get("prepared_size"), image.get("part")
        facts.append(f"<h4>#{_text(image.get('image_index'))} · {_esc(_PART_LABELS.get(part, _MISSING) if isinstance(part, str) else _MISSING)}</h4>"
                     + _facts([("사진 ID / 照片 ID", image.get("photo_id")),
                               ("실제 입력 크기 / 实际输入尺寸", " × ".join(map(str, size)) if isinstance(size, list) else None),
                               ("원래 업로드 SHA-256 / 原始上传 SHA-256", image.get("upload_source_sha256")),
                               ("저장 사진 SHA-256 / 存储图 SHA-256", image.get("stored_sha256")),
                               ("실제 기준 입력 PNG SHA-256 / 实际参考输入 PNG SHA-256", image.get("prepared_sha256"))]))
    return (opening + "<p class='small'>각 단계에 제출한 종류 예시입니다. 검사 수량에 포함하지 않으며 실제 활용을 증명하지 않습니다.<br>"
            "这是提交给各阶段的类别示例，不计入待检数量，也不证明模型实际利用了示例。</p>"
            + ("<table><thead><tr><th>단계 / 阶段</th><th>저장 상태 / 保存状态</th><th>종류별 기준 입력 / 类别参考输入</th></tr></thead><tbody>"
               + "".join(rows) + "</tbody></table>" if rows else f"<p>{_esc(_MISSING)}</p>")
            + "<details class='raw'><summary>입력 식별값·전처리 / 输入标识与预处理</summary>"
            + _facts([("관찰 프로토콜 SHA-256 / 观察协议 SHA-256", evidence.get("observer_protocol_sha256")),
                      ("Pillow", evidence.get("pillow_version")), ("전처리 / 预处理", evidence.get("preprocessing"))])
            + "".join(facts)
            + ("<p class='small'>전처리 PNG는 식별 기록만 보존합니다 / 仅保存预处理PNG的标识，未单独保留其字节。</p>"
               if evidence.get("prepared_bytes_retained") is False else "") + "</details></details>")


def _count_table(check):
    # A missing historical snapshot is not permission to borrow today's order.
    required = _mapping(check.get("requirements_snapshot"))
    observed = _mapping(check.get("observed"))
    rows = []
    for part, label in _PART_LABELS.items():
        wanted, seen = _count(required.get(part)), _count(observed.get(part))
        delta = _UNKNOWN if wanted is None or seen is None else f"{seen - wanted:+d}"
        if wanted is not None and seen == wanted:
            delta = "0"
        rows.append(
            f"<tr data-part='{part}'><th scope='row'>{_esc(label)}</th>"
            f"<td data-value='required'>{_quantity(wanted)}</td>"
            f"<td data-value='observed'>{_quantity(seen)}</td>"
            f"<td data-value='delta'>{_esc(delta)}</td></tr>"
        )
    return (
        "<table class='counts'><caption>당시 검사 수량 / 当时检查数量</caption>"
        "<thead><tr><th scope='col'>부품 / 零件</th><th scope='col'>당시 요구 / 当时需求</th>"
        "<th scope='col'>관찰 / 观察</th><th scope='col'>차이 / 差值</th></tr></thead>"
        "<tbody>" + "".join(rows) + "</tbody></table>"
        "<p class='small'>차이 = 관찰 − 당시 요구 스냅샷. 미확인은 0이 아닙니다.<br>"
        "差值＝观察－当时需求快照。未确认不等于 0；不使用当前订单补填历史数据。</p>"
    )


def _action(check, *, public_photo=False, document_photo=False):
    action = _mapping(check.get("action"))
    kind = action.get("kind")
    heading = _ACTIONS.get(kind, _MISSING) if isinstance(kind, str) else _MISSING
    record = (
        "<div class='action'><h3>다음 행동 기록 / 后续动作记录</h3>"
        f"<p><strong>{_esc(heading)}</strong></p><p>{_text(action.get('message'))}</p>"
        + _facts([("동작 코드 / 动作代码", kind)])
        + "</div>"
    )
    if public_photo:
        scope_note = (
            "사진 자료에 대한 실물 작업 지시가 아닙니다 / 不作为照片资料的实物操作指令。"
            if document_photo else
            "공개 사진에 대한 실물 작업 지시가 아닙니다 / 不作为公开照片的实物操作指令。"
        )
        return (
            "<div class='action'><h3>디지털 자료 후속 검토 / 数字资料后续审查</h3>"
            "<p>사진과 주문의 차이를 검토하고 필요한 자료를 기록하세요.<br>"
            "核对照片与订单差异，并记录需要补充的资料。</p>"
            "<details><summary>원래 저장된 일반 작업 제안 / 原始保存的通用动作建议</summary>"
            f"<p class='small'>{scope_note}</p>"
            + record + "</details></div>"
        )
    return record


def _feedback(check):
    feedback = _mapping(check.get("evidence_feedback"))
    if not feedback:
        return "<p class='small'>보완 증거 비교 미기록 / 未记录补证比较；不能据此推断实物已调整。</p>"
    groups = []
    for key, label in (
        ("resolved_uncertainties", "불명확 해소 / 已解除不确定"),
        ("remaining_uncertainties", "남은 불명확 / 仍未确认"),
        ("remaining_mismatches", "남은 수량 차이 / 仍有数量差异"),
    ):
        values = feedback.get(key)
        text = (
            ", ".join(_PART_LABELS.get(p, str(p)) for p in values if isinstance(p, str))
            if isinstance(values, list)
            else _MISSING
        )
        groups.append((label, text or "없음 / 无"))
    rows = []
    for change in _records(feedback.get("observed_changes")):
        part = change.get("part")
        name = _PART_LABELS.get(part, str(part)) if isinstance(part, str) else _MISSING
        rows.append(
            f"<tr><th scope='row'>{_esc(name)}</th><td>{_quantity(change.get('before'))}</td>"
            f"<td>{_quantity(change.get('after'))}</td></tr>"
        )
    table = (
        (
            "<table><caption>관찰 값의 변화 / 观察值变化</caption><thead><tr>"
            "<th>부품 / 零件</th><th>이전 / 之前</th><th>이후 / 之后</th></tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table>"
        )
        if rows
        else ""
    )
    return (
        "<div class='feedback'><h3>보완 증거 비교 / 补证比较</h3>"
        f"<p>{_text(feedback.get('message'))}</p>"
        + _facts(
            [
                ("결과 코드 / 结果代码", feedback.get("outcome")),
                ("이전 검사 / 上次检查", feedback.get("previous_check_id")),
                ("이전 사진 / 上次照片", feedback.get("previous_photo_id")),
                *groups,
            ]
        )
        + table
        + "<p class='small'>저장된 관찰의 비교이며 실제 부품 이동이나 현장 수정의 증명이 아닙니다.<br>"
        "这是保存的观察记录之间的比较，不证明实际移动了零件或完成现场纠正。</p></div>"
    )


def _verification(check):
    verification = _mapping(check.get("observation_verification"))
    if not verification:
        return ""
    passes = _records(verification.get("passes"))
    labels = {"original": "원본 / 原图", "rotate_90_ccw": "반시계 90° / 逆时针90°"}
    headings = []
    for item in passes:
        transform = item.get("transform")
        label = labels.get(transform, str(transform)) if isinstance(transform, str) else _MISSING
        headings.append(label)
    rows = []
    for part, label in _PART_LABELS.items():
        rows.append(
            f"<tr data-verification-part='{part}'><th scope='row'>{_esc(label)}</th>"
            + "".join(f"<td>{_quantity(_mapping(item.get('observed')).get(part))}</td>" for item in passes)
            + "</tr>"
        )
    table = (
        (
            "<table><caption>각 방향에 저장된 수량 / 每轮保存的数量</caption><thead><tr>"
            "<th>부품 / 零件</th>"
            + "".join(f"<th>{_esc(label)}</th>" for label in headings)
            + "</tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table>"
        )
        if passes
        else "<p>방향별 관찰 미기록 / 未保存各方向观察。</p>"
    )
    details = []
    for index, item in enumerate(passes):
        details.append(
            f"<details class='pass'><summary>{_esc(headings[index])} · 세부 기록 / 详细记录</summary>"
            + _facts(
                [
                    ("입력 SHA-256 / 输入 SHA-256", item.get("input_sha256")),
                    ("좌표계 / 坐标系", item.get("transform")),
                ]
            )
            + _json_details("저장된 이 방향의 JSON / 本轮原始 JSON", item)
            + "</details>"
        )
    return (
        "<div class='verification'><h3>동일 모델의 두 방향 관찰 / 同一模型的双方向观察</h3>"
        "<p class='notice'>상관된 모델 호출이며 독립 전문가 검증이나 새 촬영이 아닙니다.<br>"
        "这是相关的同模型调用，不是独立专家核验，也不是新拍摄的物理证据。</p>"
        + _facts(
            [
                ("방식 / 方式", verification.get("mode")),
                ("수량 일치 / 计数一致", _flag(verification.get("counts_agree"))),
                ("명확한 일치 / 明确一致", _flag(verification.get("clear_agreement"))),
            ]
        )
        + table
        + "".join(details)
        + "<p class='small'>최종 관찰은 위 표의 어느 한 방향으로 보충하지 않습니다. 회전 좌표는 원본에 겹치지 않습니다.<br>"
        "不以任一轮数量补填最终未确认项；旋转图坐标不叠加到原图。</p></div>"
    )


def _identity_verification(check):
    review = _mapping(check.get("identity_verification"))
    if not review:
        return ""
    response = _mapping(review.get("response"))
    crops = _records(review.get("crops"))
    part_labels = {**_PART_LABELS, "unknown": _UNKNOWN}
    status_labels = {
        "independent_object": "독립 물체 / 独立物体",
        "attached_feature": "부속 형상 / 附属特征",
        "no_object": "물체 없음 / 无物体",
        "uncertain": _UNKNOWN,
    }
    opening_labels = {
        "through_hole": "관통 구멍 / 贯穿孔",
        "closed_recess": "막힌 홈 / 封闭凹槽",
        "uncertain": _UNKNOWN,
        "not_applicable": "해당 없음 / 不适用",
    }

    def label(value, labels):
        return labels.get(value, value) if isinstance(value, str) else _MISSING

    blocked = review.get("blocked_categories")
    blocked_text = (
        ", ".join(label(part, part_labels) for part in blocked) or "없음 / 无"
        if isinstance(blocked, list)
        else _MISSING
    )
    rows = []
    for item in _records(response.get("objects")):
        matches = [crop for crop in crops if isinstance(item.get("id"), str) and crop.get("id") == item["id"]]
        # Never guess the source class if metadata is missing or ambiguous.
        original_part = matches[0].get("original_part") if len(matches) == 1 else None
        issue = "없음 / 无" if item.get("issue") == "" else item.get("issue")
        rows.append(
            "<tr class='identity-target'>"
            f"<th scope='row'>{_text(item.get('id'))}</th>"
            f"<td><span class='small'>첫 관찰 / 首轮</span><br>{_esc(label(original_part, part_labels))}"
            f"<br><span class='small'>재확인 / 复核</span><br>{_esc(label(item.get('part'), part_labels))}</td>"
            f"<td>{_esc(label(item.get('status'), status_labels))}</td>"
            f"<td>{_esc(label(item.get('opening'), opening_labels))}</td></tr>"
            f"<tr class='identity-issue'><td colspan='4'><strong>가시적 문제 / 可见问题：</strong>{_text(issue)}</td></tr>"
        )
    table = (
        "<table class='identity-table'><caption>저장된 대상별 응답 / 保存的逐目标回答</caption>"
        "<thead><tr><th>대상 / 目标</th><th>종류 / 类别</th><th>독립성 / 独立性</th>"
        "<th>구멍 형상 / 孔形</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
        if rows
        else "<p>대상별 응답 미기록 / 未保存逐目标回答；不补造复核结果。</p>"
    )
    details = []
    for crop in crops:
        details.append(
            f"<details class='identity-crop'><summary>{_text(crop.get('id'))} · 자르기 기록 / 裁剪记录</summary>"
            + _facts(
                [
                    ("첫 관찰 종류 / 首轮类别", label(crop.get("original_part"), part_labels)),
                    ("원본 목록 순번 / 原图列表序号", crop.get("object_index")),
                    ("원본 목표 [x,y] / 原图目标坐标", crop.get("center")),
                    ("자른 그림 목표 [x,y] / 裁剪图目标坐标", crop.get("target_center_crop")),
                    ("원본 크기 px / 来源尺寸", crop.get("source_size")),
                    ("원본 자르기 [L,T,R,B] / 来源裁剪边界", crop.get("rect_source_px")),
                    ("원래 자른 크기 px / 原始裁剪尺寸", crop.get("crop_source_size")),
                    ("모델 입력 크기 px / 模型输入尺寸", crop.get("crop_size")),
                    ("보간법 / 插值方式", crop.get("resampling")),
                    (
                        "보간으로 정보 생성 / 插值创造信息（保存值）",
                        _flag(crop.get("interpolation_creates_information")),
                    ),
                    ("원본 SHA-256 / 来源 SHA-256", crop.get("source_sha256")),
                    ("원래 자른 그림 SHA-256 / 原始裁剪 SHA-256", crop.get("pixel_crop_sha256")),
                    ("모델 입력 자른 그림 SHA-256 / 模型裁剪 SHA-256", crop.get("crop_sha256")),
                    ("원래 자른 파일명 (기록) / 原始裁剪文件名记录", crop.get("pixel_crop_file")),
                    ("모델 입력 파일명 (기록) / 模型裁剪文件名记录", crop.get("crop_file")),
                ]
            )
            + "</details>"
        )
    return (
        "<div class='identity-verification'><h3>부품 종류·구멍 재확인 / 零件类别与孔形复核</h3>"
        "<p class='notice'>동일 모델의 상관된 재확인이며 독립 검증이나 실측 기하 검사가 아닙니다.<br>"
        "这是同模型的相关复核，不是独立验证或几何实测。只检查已选目标，不能发现遗漏物体。</p>"
        + _facts(
            [
                ("프로토콜 / 协议", review.get("protocol")),
                ("상관된 동일 모델 호출 / 同模型相关调用", _flag(review.get("same_model_correlated_calls"))),
                ("미확인 처리 종류 / 置为未确认的类别", blocked_text),
                ("전체 입력 SHA-256 / 全图输入 SHA-256", review.get("full_input_sha256")),
                ("저장 사진 SHA-256 / 来源照片 SHA-256", review.get("source_sha256")),
            ]
        )
        + table
        + "<p class='small'>정수 수량을 재배정하지 않습니다. 확인하지 못한 종류만 미확인 처리합니다.<br>"
        "不重新赋整数计数，仅把无法确认的类别置为未知。图像插值不创造新信息；坐标不是几何真值。"
        "裁剪文件名与哈希是保存的元数据，不表示这些裁剪图已附在证据包内。</p>"
        + "".join(details)
        + _json_details("재확인 원본 JSON / 身份复核完整 JSON", review)
        + "</div>"
    )


def _original_points(check, photo):
    evidence = _mapping(check.get("object_evidence"))
    if not evidence:
        return ""
    objects = _records(evidence.get("objects"))
    verified = (
        evidence.get("coordinate_frame") == "normalized_original"
        and evidence.get("protocol") == "spatial_inventory_v1"
        and photo is not None
        and isinstance(photo.get("sha256"), str)
        and re.fullmatch(r"[a-fA-F0-9]{64}", photo["sha256"])
        and check.get("photo_sha256") == photo["sha256"]
    )
    passes = _records(_mapping(check.get("observation_verification")).get("passes"))
    if passes:
        first = passes[0]
        verified = verified and first.get("transform") == "original"
        if "objects" in first:
            verified = verified and first["objects"] == evidence.get("objects")
    if not verified:
        return (
            "<p class='small points-unavailable'>원본 사진·좌표 연결을 확인할 수 없어 점을 겹치지 않습니다.<br>"
            "无法确认原图、哈希和坐标的关联，因此不叠加点位；原始记录仍在 JSON 中。</p>"
        )
    markers = []
    for index, item in enumerate(objects, start=1):
        center, part = item.get("center"), item.get("part")
        if (
            not isinstance(center, list)
            or len(center) != 2
            or not all(type(v) in (int, float) and 0 <= v <= 1 for v in center)
            or not isinstance(part, str)
            or part not in _PART_LABELS
        ):
            continue
        x, y = (100 * value for value in center)
        markers.append(
            f"<span class='point' style='left:{x:.5f}%;top:{y:.5f}%' "
            f"title='{_esc(_PART_LABELS[part])}'>{index}</span>"
        )
    return (
        "<details class='points'><summary>원본 첫 관찰의 추정 점 / 原图首轮估计点</summary>"
        "<p class='small'>모델 추정 위치이며 정답·물체 ID가 아닙니다. 최종 미확인 수량을 확정하지 않습니다.<br>"
        "点位只是模型估计，不是真值或稳定物体身份，也不能将最终未确认数量变成确定值。</p>"
        f"<div class='point-image'><img src='{_esc(photo['archive_path'])}' alt='원본 첫 관찰 / 原图首轮估计点'>"
        + "".join(markers)
        + "</div></details>"
    )


_VIEWER_CSS = """
:root{color-scheme:light;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
color:#173c37;background:#eef3ef;line-height:1.55}*{box-sizing:border-box}
body{margin:0}main{max-width:1180px;margin:auto;padding:32px 24px 64px}
h1,h2,h3,p{margin:0 0 12px}h1{font-size:clamp(27px,4vw,42px);line-height:1.2}
h2{font-size:24px;line-height:1.3}h3{font-size:18px;margin-top:20px}
header{background:#153c36;color:white;padding:32px;border-radius:20px}
header a{color:#d8f4da}header .small,header .facts dt{color:#d0e0d7}.eyebrow{letter-spacing:.1em;font-size:12px}
.notice{background:#fff4dd;border-left:4px solid #b7832c;color:#533d13;padding:14px 16px;border-radius:4px}
header .notice{margin-top:22px}.small{font-size:13px;color:#5e7169}
a{color:#086353;overflow-wrap:anywhere}nav{display:flex;flex-wrap:wrap;gap:10px 20px;margin-top:20px}
section{background:#fff;border:1px solid #cfdbd2;border-radius:16px;margin-top:22px;padding:26px}
.summary{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:20px}
.summary div{background:#f4f8f3;border-radius:10px;padding:16px}.summary strong{display:block;font-size:25px}
.check-heading{display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between}
.badge{font-size:13px;background:#edf3e9;border:1px solid #d4dfca;border-radius:20px;padding:6px 12px}
.invalid{background:#f7eee8;color:#7c4725;border-color:#e9d6c4}.decision{font-weight:650;font-size:17px;color:#176353}
.check-grid{display:grid;grid-template-columns:minmax(0,.95fr) minmax(0,1.15fr);gap:26px;margin-top:18px}
.check-grid>*{min-width:0}.photo{margin:0}.photo img,.point-image img{display:block;width:100%;height:auto;border-radius:8px}
.photo figcaption{font-size:12px;color:#5e7169;margin-top:8px;overflow-wrap:anywhere}
table{width:100%;border-collapse:collapse;table-layout:fixed;font-size:14px;margin:14px 0}
caption{text-align:left;font-weight:700;padding-bottom:8px}th,td{padding:10px 9px;border:1px solid #d6e1d8;text-align:left;
overflow-wrap:anywhere;vertical-align:top}thead{background:#ecf3eb}tbody th{font-weight:600;width:30%}
.facts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px 20px;margin:14px 0}
.facts div{min-width:0}.facts dt{font-size:12px;color:#677a70}.facts dd{margin:3px 0 0;font-size:14px;overflow-wrap:anywhere}
.action,.feedback,.verification,.identity-verification{background:#f6f9f4;border:1px solid #dfE7dc;border-radius:10px;padding:16px;margin:16px 0}
.action h3,.feedback h3,.verification h3,.identity-verification h3{margin-top:0}
.identity-issue td{background:#eef4ea;font-size:13px}.identity-table th:first-child{width:16%}
details{margin-top:12px;border-top:1px solid #dae3d9;padding-top:12px}summary{cursor:pointer;font-weight:600;overflow-wrap:anywhere}
summary:focus-visible,a:focus-visible{outline:3px solid #d29933;outline-offset:4px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:520px;overflow:auto;font:12px/1.6 ui-monospace,monospace;
background:#edf2ee;padding:16px;border-radius:8px}
.point-image{position:relative;width:100%;max-width:700px;margin:16px auto;overflow:hidden}
.point{position:absolute;transform:translate(-50%,-50%);display:grid;place-items:center;width:24px;height:24px;
background:#fff1ab;border:1px solid #285246;border-radius:50%;color:#173c37;font:12px/1 system-ui}
.gallery{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.gallery img{width:100%;height:auto}
h1,h2,h3,p,.badge{overflow-wrap:anywhere}footer{margin-top:24px}
@media(max-width:700px){main{padding:14px 12px 36px}header{padding:24px 18px;border-radius:14px}
section{padding:19px 15px}.check-grid,.facts,.gallery{grid-template-columns:1fr}.summary{gap:7px}
.summary div{padding:10px 8px;font-size:12px}.summary strong{font-size:22px}h2{font-size:21px}
th,td{padding:8px 5px;font-size:12px}.action,.feedback,.verification,.identity-verification{padding:13px}.check-grid{gap:16px}}
@media print{body{background:white}main{padding:0}.check{break-inside:avoid}nav,.raw{display:none}header{color:#173c37;background:white}}
"""


def _document_source(order):
    source = _mapping(order.get("document_source"))
    return (
        "<section class='document-source' data-source-verification='user_declared_unverified'>"
        "<h2>사진 자료 출처 / 照片资料来源</h2>"
        "<p class='notice'>사용자 진술 · 출처와 이용 조건 미검증 / 用户自报 · 来源与使用条件未核实。</p>"
        "<p>사진과 진술이 고정된 디지털 자료입니다. 실물 완료 또는 출고를 인증하지 않습니다.<br>"
        "照片与声明固定关联，仅用于数字审查，不认证实物完工或出库。</p>"
        + _facts([
            ("출처 설명 (사용자 진술) / 来源说明（用户自报）", source.get("source_note")),
            ("출처 URL (텍스트·미검증) / 来源网址（文本·未核实）", source.get("source_url")),
            ("이용 조건 (사용자 진술) / 使用条件（用户自报）", source.get("license_note")),
            ("진술 등록 시각 / 声明登记时间", source.get("declared_at")),
        ])
        + "<details><summary>사진·진술 연결 기록 / 照片与声明关联记录</summary>"
        + _facts([
            ("고정 원본 사진 ID / 固定根照片 ID", source.get("original_root_photo_id")),
            ("원래 업로드 SHA-256 / 原始上传 SHA-256", source.get("source_sha256")),
            ("저장 사진 SHA-256 / 存储照片 SHA-256", source.get("storage_sha256")),
            ("출처 진술 SHA-256 / 来源声明 SHA-256", source.get("statement_sha256")),
            ("사진·진술 연결 SHA-256 / 照片与声明关联 SHA-256", source.get("binding_sha256")),
        ])
        + "</details></section>"
    )


def _public_review_history(order):
    """Show saved digital opinions without treating them as ground truth or release."""
    reviews = _records(order.get("public_reviews"))
    replays = _records(order.get("public_replays"))
    if not reviews and not replays:
        return ""
    labels = {
        "acknowledged": "검사 내용을 읽고 동의함 / 已阅读并认可本次核验",
        "needs_more_evidence": "추가 자료 필요 / 需要补充资料",
        "disputed": "AI 판단에 동의하지 않음 / 不同意 AI 判断",
        "inconclusive": "현재 판단 불가 / 目前无法判断",
    }
    feedback = derive_digital_review_feedback(order)
    title = ("사진 자료 디지털 검토 / 照片资料数字审查" if "document_source" in order
             else "공개 사진 디지털 검토 / 公开照片数字审查")
    parts = [(f"<section class='public-review' id='digital-review-history'><h2>{title}</h2>"
             "<p class='notice'>사람의 검토 의견입니다. AI 정확도, 실물 완료, 출고 또는 사용자 시험 성과가 아닙니다.<br>"
             "这里保存人工审查意见，不计为 AI 准确率、实物完工、出库或用户试验成绩。</p>")]
    for review in reviews:
        linked = review.get("id") in feedback["current_review_ids"]
        parts.append("<article class='digital-review-record'><h3>"
                     + _text(labels.get(review.get("conclusion"), _MISSING)) + "</h3>"
                     + _facts([
                         ("기록 적용 범위 / 记录适用范围", "내보낼 당시 저장된 검사 연결 / 对应导出时当前核验（仅保存绑定）" if linked
                          else "이전 기록 · 현재 적용 안 됨 · 해결을 뜻하지 않음 / 历史记录 · 不适用于当前核验 · 不代表已解决"),
                         ("버전 / 版本", review.get("revision")),
                         ("검토자 코드 / 审查人代号", review.get("operator_code")),
                         ("시각 / 时间", review.get("created_at")),
                         ("AI 원래 판단 / AI 原判断", review.get("ai_decision")),
                         ("검토 근거 / 审查依据", review.get("note")),
                         ("검사 ID / 检查 ID", review.get("check_id")),
                         ("검사 SHA-256 / 检查 SHA-256", review.get("check_sha256")),
                     ]) + _json_details("저장된 검토 원본 / 保存的审查原始记录", review) + "</article>")
    parts.append("<p class='small'>내보낸 기록만 비교합니다. 현재 모델 실행, 검토자 신원 또는 서명을 인증하지 않습니다.<br>"
                 "适用范围只对照导出快照，不验证当前模型运行、审查人身份或签名。</p></section>")
    if replays:
        title = ("같은 자료 사진 재사용 / 同一资料照片回放" if "document_source" in order
                 else "같은 공개 사진 재사용 / 同一公开照片回放")
        parts.append(f"<section class='public-replays'><h2>{title}</h2>"
                     "<p>새 촬영이나 실물 변경을 의미하지 않습니다 / 不代表重新拍摄或实物发生变化。</p>"
                     + _json_details("회차별 재사용 기록 / 逐次回放记录", replays) + "</section>")
    return "".join(parts)


def _digital_review_feedback(order):
    if not is_digital_only(order):
        return ""
    feedback = derive_digital_review_feedback(order)
    resolution = current_resolution(order)
    if resolution:
        return ("<section class='notice'><h2>연결 의견 검토 기록 / 绑定意见复核记录</h2>"
                f"<p>{feedback['current_count']}건의 기존 의견과 연결된 별도 검토 결론이 있습니다. "
                "AI 원판단과 모든 의견은 그대로 보존됩니다.<br>"
                f"已针对当前 {feedback['current_count']} 条意见保存独立复核结论；AI 原判断及意见原文完整保留。"
                "结论表达审查人的处理判断，不保证其正确。</p></section>")
    label = {
        "needs_clarification": "설명이 필요한 검토 의견 / 待澄清意见",
        "recorded": "검토 의견 기록됨 / 已记录审查意见",
        "none": "현재 검사에 연결된 검토 의견 없음 / 当前核验暂无绑定意见",
        "not_applicable": "현재 검사에 적용할 수 없음 / 不适用于当前核验",
    }[feedback["status"]]
    decision = _mapping(order.get("latest_check")).get("decision")
    return (f"<section class='digital-review-feedback notice' data-feedback-status='{feedback['status']}'>"
            f"<h2>{label}</h2>"
            + _facts([("AI 저장 판단 (변경 없음) / AI 保存判断（未改写）", decision),
                      ("현재 연결 의견 / 当前绑定意见", feedback["current_count"]),
                      ("설명이 필요한 의견 / 待澄清意见数", feedback["pending_count"])])
            + "<p>나중의 동의는 앞선 이견을 지우지 않습니다. 이전 기록의 적용 만료도 해결을 뜻하지 않습니다.<br>"
            "后续认可不会清除先前异议；历史意见不再适用也不代表问题已解决。</p>"
            "<p class='small'>내보낼 때 저장된 연결만 비교합니다. 현재 실행 환경이나 검토자 신원을 확인하지 않습니다.<br>"
            "仅对照导出时保存的绑定，不验证当前运行环境或审查人身份。</p>"
            + ("<a href='#digital-review-history'>의견과 근거 보기 / 查看意见及依据</a>" if _records(order.get("public_reviews")) else "")
            + "</section>")


def _digital_resolution_history(order, photo_map):
    records = _records(order.get("digital_resolutions"))
    if not records:
        return ""
    current = current_resolution(order)
    labels = {"matched": "검토 수량 일치 / 复核数量相符", "mismatch": "검토 수량 차이 / 复核发现数量差异",
              "needs_more_evidence": "추가 자료 요청 / 已记录补资料要求"}
    parts = [("<section id='digital-resolution'><h2>사진 자료 검토 결론 / 照片资料审核结论</h2>"
             "<p class='notice'>표시는 검토자 진술입니다. AI 원관찰을 바꾸거나 실물 출고를 승인하지 않습니다.<br>"
             "标记是审查人的声明；不改写 AI 原观察、不批准实物出库、不作为模型准确率。</p>")]
    for r in reversed(records):
        linked = bool(current and current.get("id") == r.get("id"))
        parts.append("<article><h3>" + _text(labels.get(r.get("outcome"), _MISSING)) + "</h3>"
                     + _facts([("적용 / 适用", "현재 저장된 결론 / 导出时当前结论" if linked else "이전 기록 / 历史记录"),
                               ("버전 / 版本", r.get("expected_revision")),
                               ("검토자 / 审查人", r.get("operator_code")),
                               ("용도 / 用途", "기능 리허설 / 功能演练" if r.get("purpose") == "engineering_rehearsal"
                                else "본인 검토 진술 / 本人审查声明"),
                               ("근거 / 依据", r.get("note")),
                               ("AI 원판단 / AI 原判断", _mapping(r.get("check_snapshot")).get("decision")),
                               ("연결 의견 / 绑定意见数", len(_records(r.get("review_snapshot"))))]))
        counts = _mapping(r.get("reviewed_counts"))
        check = _mapping(r.get("check_snapshot"))
        requirements = _mapping(r.get("requirements_snapshot"))
        parts.append("<table><thead><tr><th>종류 / 类别</th><th>주문 / 订单</th><th>AI</th>"
                     "<th>검토 / 复核</th><th>차이 / 差额</th></tr></thead><tbody>"
                     + "".join("<tr><th>" + label + "</th>" + "".join("<td>" + _text(value) + "</td>" for value in
                                (requirements.get(part), _mapping(check.get("observed")).get(part),
                                 counts.get(part), _mapping(r.get("difference")).get(part))) + "</tr>"
                               for part, label in _PART_LABELS.items()) + "</tbody></table>")
        photo = photo_map.get(r.get("photo_id"))
        if photo and _safe_photo_path(photo):
            markers = []
            for i, point in enumerate(_records(r.get("points")), 1):
                x, y = point.get("x"), point.get("y")
                if type(x) is int and type(y) is int and 0 <= x <= 1000 and 0 <= y <= 1000:
                    markers.append(f"<span class='review-dot' style='left:{x / 10}%;top:{y / 10}%' "
                                   f"title='{_text(_PART_LABELS.get(point.get('part'), _MISSING))}'>{i}</span>")
            parts.append(f"<div class='review-photo'><img src='{_safe_photo_path(photo)}' "
                         "alt='검토자가 표시한 사진 / 审查人标记照片'>" + "".join(markers) + "</div>"
                         + "<p>" + " · ".join(f"{i} {_text(_PART_LABELS.get(p.get('part'), _MISSING))}"
                                               for i, p in enumerate(_records(r.get("points")), 1)) + "</p>")
        parts.append(_json_details("원기록 / 完整审核记录", r) + "</article>")
    return "".join(parts) + "</section>"


def render_viewer(payload):
    """Render escaped, network-free HTML from this export's historical records only."""
    order = _mapping(payload.get("order"))
    photos = _records(payload.get("photos"))
    photo_map = {p["id"]: p for p in photos if _safe_photo_path(p)}
    checks = _records(order.get("checks"))
    demo_source = _mapping(order.get("demo_source"))
    digital_only = is_digital_only(order)
    boundary = (
        "사진 자료의 디지털 검토 기록입니다. 실물 완료를 승인하지 않습니다.<br>"
        "这是照片资料的数字审查记录，不批准实物完工。"
        if "document_source" in order else
        "공개 사진의 디지털 검토 기록입니다. 실물 완료를 승인하지 않습니다.<br>"
        "这是公开照片的数字审查记录，不批准实物完工。"
        if demo_source else
        "이 파일은 완료 승인이나 실물 조작의 증명이 아닙니다. 모델은 틀릴 수 있습니다.<br>"
        "本报告不能批准新任务，也不证明实际物料操作。模型可能出错；ready 仍须本人核对实物。"
    )
    parts = [
        "<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; img-src 'self' file:; "
        "style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; connect-src 'none'\">"
        "<title>KitGuard · Offline Evidence</title><style>" + _VIEWER_CSS + ".review-photo{position:relative;max-width:720px;line-height:0}.review-photo img{width:100%;display:block}.review-dot{position:absolute;transform:translate(-50%,-50%);width:28px;height:28px;border:2px solid white;border-radius:50%;background:#285f52;color:white;text-align:center;line-height:24px;font-size:12px;font-weight:bold;box-shadow:0 1px 4px #0009}" + "</style></head><body><main>",
        "<header><p class='eyebrow'>KITGUARD · OFFLINE EVIDENCE</p>"
        f"<h1>{_text(order.get('title'))}</h1><p>읽기 전용 증거 보고서 / 只读证据报告</p>"
        + _facts(
            [
                ("현재 기록 버전 / 导出时订单版本", order.get("revision")),
                ("상태 코드 / 状态代码", order.get("status")),
                ("내보낸 시각 / 导出时间", payload.get("exported_at")),
                ("주문 ID / 订单 ID", order.get("id")),
            ]
        )
        + f"<p class='notice'>{boundary}</p>"
        "<nav aria-label='증거 파일 / 证据文件'><a href='evidence.json'>전체 JSON / 完整 JSON</a>"
        "<a href='SHA256.json'>SHA-256 목록 / 哈希清单</a><a href='README.txt'>안내 / 使用说明</a></nav></header>",
        (
            "<div class='summary'>"
            f"<div><strong>{len(checks)}</strong>검사 기록 / 检查记录</div>"
            f"<div><strong>{len(photo_map)}</strong>보관 사진 / 保存照片</div>"
            f"<div><strong>{len(_records(order.get('completions')))}</strong>담당자 확인 기록 / 人工确认记录</div></div>"
        ),
    ]
    parts.append(_digital_resolution_history(order, photo_map))
    parts.append(_digital_review_feedback(order))
    if "document_source" in order:
        parts.append(_document_source(order))
    if demo_source:
        parts.append(
            "<section class='demo-source'><h2>공개 사진 시연 / 公开照片演示</h2>"
            "<p class='notice'>현장 촬영이나 실제 부품 보충을 검증한 주문이 아닙니다. 실물 완료 확인 대상이 아닙니다.<br>"
            "此订单使用公开照片演示，不是现场拍摄或真实补件验证，不能记为实体完工。</p>"
            + _facts(
                [
                    ("시연 유형 / 演示类型", demo_source.get("kind")),
                    ("표본 ID / 样例 ID", demo_source.get("sample_id")),
                    ("원본 사례 ID / 来源案例 ID", demo_source.get("source_case_id")),
                    ("출처 URL (텍스트) / 来源网址（文本）", demo_source.get("source_url")),
                    ("이용 허락 / 许可证", demo_source.get("license")),
                    ("원본 SHA-256 / 来源 SHA-256", demo_source.get("source_sha256")),
                    ("출처 설명 / 来源说明", demo_source.get("source_note")),
                ]
            )
            + "</section>"
        )
    for review in _records(order.get("manual_reviews")):
        actual = _mapping(review.get("actual_counts"))
        required = _mapping(review.get("requirements_snapshot"))
        parts.append(
            "<section class='manual-review'><h2>사람의 실물 확인 기록 / 人工实物复核记录</h2>"
            "<p class='notice'>AI 검사 성공으로 집계하지 않습니다 / 不计为 AI 核验成功。</p>"
            + _facts([
                ("확인 결과 / 复核结果", "수량 일치 / 数量相符" if review.get("matches_requirements") is True else "미해결 / 未解决"),
                ("버전 / 版本", review.get("revision")), ("작업자 코드 / 操作者代号", review.get("operator_code")),
                ("확인 시각 / 复核时间", review.get("created_at")), ("처리 메모 / 处理说明", review.get("reason")),
                ("사진 / 照片 ID", review.get("photo_id")), ("AI 검사 / AI 核验 ID", review.get("check_id")),
            ])
            + "<table><thead><tr><th>부품 / 零件</th><th>당시 요구 / 当时需求</th><th>실물 직접 계수 / 人工实点</th></tr></thead><tbody>"
            + "".join(f"<tr><td>{_text(label)}</td><td>{_text(required.get(part))}</td><td>{_text(actual.get(part))}</td></tr>"
                      for part, label in _PART_LABELS.items())
            + "</tbody></table><p class='small'>작업자의 실물 확인 선언입니다. 사진·해시가 실물 진위를 증명하지 않습니다 / 来源是操作者的实物确认声明，照片和哈希不认证实物真实性。</p></section>"
        )
    parts.append(_public_review_history(order))
    if not checks:
        parts.append(
            "<section><h2>검사 기록 없음 / 暂无检查记录</h2><p>수량 정확성을 추정하지 않습니다 / 不推断数量是否正确。</p></section>"
        )
    for index, check in enumerate(checks, start=1):
        decision = check.get("decision")
        decision_text = _DECISIONS.get(decision, _MISSING) if isinstance(decision, str) else _MISSING
        if "document_source" in order and decision == "ready":
            decision_text = "사진 자료 수량 일치 · 실물 완료 아님 / 照片资料数量相符 · 非实物完工"
        elif demo_source and decision == "ready":
            decision_text = "공개 사진 수량 일치 · 실물 완료 아님 / 公开照片数量相符 · 非实物完工"
        elif "document_source" in order and decision == "correct":
            decision_text = "사진 자료와 주문의 차이 / 照片资料与订单有差异"
        elif demo_source and decision == "correct":
            decision_text = "공개 사진과 주문의 차이 / 公开照片与订单有差异"
        invalid = " invalid" if check.get("valid") is False else ""
        parts.append(
            f"<section class='check' id='check-{index}'><div class='check-heading'>"
            f"<h2>검사 {index:02d} / 检查 {index:02d} · R{_text(check.get('revision'))}</h2>"
            f"<span class='badge{invalid}'>내보낼 때 valid / 导出时有效：{_esc(_flag(check.get('valid')))}</span>"
            f"</div><p class='decision'>{_esc(decision_text)}</p>"
            + _facts(
                [
                    ("저장된 판단 코드 / 保存的判断代码", decision),
                    ("검사 ID / 检查 ID", check.get("id")),
                    ("검사 시각 / 检查时间", check.get("created_at")),
                    ("모델 / 模型", check.get("model_label")),
                    ("실행 방식 / 后端", check.get("backend")),
                    ("소요 시간 ms / 耗时毫秒", check.get("latency_ms")),
                ]
            )
        )
        if check.get("backend") == "test":
            parts.append(
                "<p class='notice'>공학 테스트 기록 / 工程夹具记录：不是模型准确率或实物验证证据。</p>"
            )
        photo = photo_map.get(check.get("photo_id")) if isinstance(check.get("photo_id"), str) else None
        parts.append("<div class='check-grid'><div>")
        if photo:
            scope = check.get("inspection_scope")
            root = photo_map.get(scope.get("root_photo_id")) if isinstance(scope, dict) else None
            if root and scope.get("mode") == "region":
                parts.append(scope_html(scope, _safe_photo_path(root)))
            parts.append(
                f"<figure class='photo'><img src='{_esc(photo['archive_path'])}' "
                "alt='저장된 검사 사진 / 保存的检查照片'>"
                f"<figcaption>{_text(photo.get('id'))} · R{_text(photo.get('revision'))}</figcaption></figure>"
            )
        else:
            parts.append(
                "<p class='notice'>이 검사에 연결된 로컬 사진 없음 / 未找到此检查对应的本地照片。</p>"
            )
        parts.append(
            _facts(
                [
                    ("검사에 저장된 사진 SHA-256 / 检查保存的照片 SHA-256", check.get("photo_sha256")),
                    ("묶음 사진 SHA-256 / 包内照片 SHA-256", photo.get("sha256") if photo else None),
                ]
            )
            + _original_points(check, photo)
            + "</div><div>"
        )
        if not isinstance(check.get("requirements_snapshot"), dict):
            parts.append(
                "<p class='notice'>당시 요구 스냅샷 미기록 / 缺少当时需求快照；未用当前订单补填。</p>"
            )
        parts.append(_count_table(check) + _action(check, public_photo=digital_only,
                     document_photo="document_source" in order) + "</div></div>" + _feedback(check))
        parts.append(_reference_evidence(check))
        parts.append(_verification(check))
        parts.append(_identity_verification(check))
        parts.append(_json_details("이 검사의 원본 JSON / 此检查完整 JSON", check) + "</section>")
    parts.append("<section><h2>사진 목록 / 照片目录</h2><div class='gallery'>")
    for photo in photos:
        path = _safe_photo_path(photo)
        parts.append(
            f"<details><summary>{_text(photo.get('id'))} · R{_text(photo.get('revision'))}</summary>"
        )
        if path:
            parts.append(f"<img loading='lazy' src='{_esc(path)}' alt='보관 사진 / 包内照片'>")
            if photo.get("kind") == "inspection_region_view":
                root = photo_map.get(photo.get("root_photo_id"))
                if root:
                    saved_photo = next(p for p in order["photos"] if p["id"] == photo["id"])
                    scope = inspection_scope(order, saved_photo)
                    parts.append(scope_html(scope, _safe_photo_path(root)))
                    parts.append(_json_details("검사 범위 기록 / 检查范围记录", scope))
        else:
            parts.append("<p>허용된 로컬 사진 경로가 아님 / 非允许的本地照片路径，不加载。</p>")
        parts.append(
            _facts(
                [
                    ("SHA-256", photo.get("sha256")),
                    ("원본 업로드 SHA-256 / 原始上传 SHA-256", photo.get("source_sha256")),
                ]
            )
        )
        parts.append("</details>")
    parts.append(
        "</div></section><section><h2>이 보고서의 범위 / 本报告的边界</h2>"
        "<p>해시는 무결성 추적 수단이며 전자서명이나 현장 인증이 아닙니다. 사진은 정규화된 저장본입니다.<br>"
        "哈希用于追溯文件完整性，不是数字签名或现场认证。包内图片是归一化后的保存版本。</p>"
        "<p>본인 확인 기록은 담당자의 확인을 저장한 것이며 제품 안전 인증이 아닙니다.<br>"
        "人工确认记录只保存操作者的确认，不是产品安全认证。导出不授予图片和文字的再分发权限。</p>"
        + "".join(f"<p class='small'>{_esc(item)}</p>" for item in LIMITATIONS)
        + _json_details("전체 증거 원본 JSON / 全部证据原始 JSON", payload)
        + "</section><footer class='small'>KitGuard · 읽기 전용 / 只读 · 서버·스크립트·네트워크 불필요 / 无需服务器、脚本或网络</footer>"
        "</main></body></html>"
    )
    return "".join(parts)
