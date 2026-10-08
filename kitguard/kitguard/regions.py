"""Operator-declared views of one immutable normalized root photograph."""

import hashlib
import html
import io
import re
from pathlib import Path
from typing import Literal

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from .photo_documents import verify_document_source
from .store import StateError, now, uid

COORDINATES = "normalized_root_pixels_xyxy_half_open_v1"
DECLARATION = "operator_all_required_items_inside"


class InspectionRegion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: StrictInt = Field(ge=1)
    expected_photo_id: str = Field(min_length=1, max_length=80)
    expected_evidence_epoch: StrictInt = Field(ge=0)
    root_photo_id: str = Field(min_length=1, max_length=80)
    mode: Literal["region", "whole_image"]
    region_xyxy: list[StrictInt] | None
    confirmed_all_items_inside: Literal[True]

    @field_validator("confirmed_all_items_inside", mode="before")
    @classmethod
    def explicit_scope(cls, value):
        if value is not True:
            raise ValueError("검사 범위를 명시적으로 확인하세요 / 请明确确认全部待检件位于检查范围内")
        return value

    @model_validator(mode="after")
    def matching_mode(self):
        if self.mode == "whole_image" and self.region_xyxy is not None:
            raise ValueError("Whole-image mode requires null coordinates")
        if self.mode == "region" and (self.region_xyxy is None or len(self.region_xyxy) != 4):
            raise ValueError("Region mode requires four strict integer coordinates")
        return self


def source_family(photo):
    return photo.get("source_family_sha256") or photo.get("root_photo_sha256") or photo.get("sha256") or photo.get("photo_sha256")


def family_tokens(record):
    scope = record.get("inspection_scope") or {}
    keys = ("sha256", "photo_sha256", "source_sha256", "root_photo_sha256", "source_family_sha256")
    return {value for value in [*(record.get(key) for key in keys), scope.get("root_source_sha256"),
                                scope.get("root_photo_sha256"), scope.get("view_sha256")]
            if isinstance(value, str) and len(value) == 64}


def known_family_hashes(db, record):
    """Join only known exact byte links, never perceptual image similarity."""
    import json

    components = [family_tokens(photo) for row in db.execute("SELECT body FROM orders")
                  for photo in json.loads(row["body"]).get("photos", [])]
    connected = family_tokens(record)
    while True:
        expanded = connected.union(*(part for part in components if part & connected))
        if expanded == connected:
            return connected
        connected = expanded


def resolve_root(order, photo):
    if photo not in order.get("photos", []):
        raise StateError("주문 검사 사진이 아닙니다 / 不是此订单的检查照片")
    if photo.get("kind", "root_photo") == "inspection_region_view":
        root = next((p for p in order["photos"] if p["id"] == photo.get("root_photo_id")), None)
        if not root or root.get("kind", "root_photo") != "root_photo":
            raise StateError("원본 연결이 올바르지 않습니다 / 根图关联无效，不能递归裁剪")
        if (photo.get("root_photo_sha256") != root.get("sha256")
                or photo.get("source_family_sha256") != root.get("sha256")
                or photo.get("root_width") != root.get("width") or photo.get("root_height") != root.get("height")):
            raise StateError("원본 바인딩이 변경되었습니다 / 根图绑定已改变")
    elif photo.get("kind", "root_photo") == "root_photo":
        root = photo
    else:
        raise StateError("알 수 없는 사진 종류 / 未知照片来源类型")
    if (root.get("root_photo_id", root["id"]) != root["id"] or source_family(root) != root.get("sha256")
            or root.get("root_photo_sha256", root.get("sha256")) != root.get("sha256")
            or root.get("scope_mode", "whole_image") != "whole_image" or root.get("region_xyxy") is not None):
        raise StateError("원본 사진 연결이 잘못되었습니다 / 根照片来源绑定无效")
    return root


def inspection_scope(order, photo):
    root = resolve_root(order, photo)
    return {
        "mode": photo.get("scope_mode", "whole_image"), "view_photo_id": photo["id"],
        "view_sha256": photo["sha256"], "root_photo_id": root["id"], "root_photo_sha256": root["sha256"],
        "source_family_sha256": root["sha256"], "root_width": root.get("width"), "root_height": root.get("height"),
        "root_source_sha256": root.get("source_sha256"), "root_created_at": root.get("created_at"),
        "region_xyxy": photo.get("region_xyxy"), "coordinate_space": COORDINATES,
        "derivation": photo.get("derivation", "normalized_root_bytes_v1"),
        "scope_declaration": photo.get("scope_declaration"), "scope_confirmed_at": photo.get("scope_confirmed_at"),
    }


def stored_bytes(store, photo, db=None):
    if db is None:
        path = store.photo_path(photo["id"])
    else:
        record = db.execute("SELECT path FROM photos WHERE id=?", (photo["id"],)).fetchone()
        if record is None:
            raise StateError("사진 파일 기록이 없습니다 / 照片文件记录缺失")
        path = Path(record["path"])
        if not path.is_absolute():
            path = store.photos_dir / path
        if not path.resolve().is_relative_to(store.photos_dir.resolve()) or not path.is_file():
            raise StateError("사진 파일이 없습니다 / 照片文件缺失")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != photo.get("sha256"):
        raise StateError("사진 무결성 확인 실패 / 照片完整性校验失败")
    return raw


def verify_photo_lineage(store, order, photo, db=None):
    root = resolve_root(order, photo)
    raw = stored_bytes(store, root, db)
    if "document_source" in order:
        verify_document_source(order, root)
    with Image.open(io.BytesIO(raw)) as image:
        if image.size != (root.get("width", image.width), root.get("height", image.height)):
            raise StateError("원본 크기 정보가 바뀌었습니다 / 根图尺寸元数据已改变")
    if photo["id"] != root["id"]:
        view_raw = stored_bytes(store, photo, db)
        validate_rectangle(photo.get("scope_mode"), photo.get("region_xyxy"), root["width"], root["height"])
        if photo.get("scope_declaration") != DECLARATION or not photo.get("scope_confirmed_at"):
            raise StateError("검사 범위 확인 기록이 없습니다 / 缺少检查范围确认记录")
        expected_derivation = "normalized_root_bytes_v1"
        expected, size = raw, (root["width"], root["height"])
        if photo["scope_mode"] == "region":
            expected_derivation = "pillow_root_crop_rgb_jpeg95_v1"
            with Image.open(io.BytesIO(raw)) as opened:
                crop = opened.convert("RGB").crop(photo["region_xyxy"])
                stream = io.BytesIO()
                crop.save(stream, format="JPEG", quality=95)
                expected, size = stream.getvalue(), crop.size
        if (photo.get("coordinate_space") != COORDINATES or photo.get("derivation") != expected_derivation
                or (photo.get("width"), photo.get("height")) != size or view_raw != expected):
            raise StateError("선택 영역 바이트·좌표가 원본과 일치하지 않습니다 / 选区图字节、坐标或编码与根图不一致")
    return root, raw


def validate_rectangle(mode, rectangle, width, height):
    if mode == "whole_image" and rectangle is None:
        return
    if mode != "region" or not isinstance(rectangle, list) or len(rectangle) != 4 or any(type(n) is not int for n in rectangle):
        raise StateError("정수 영역 좌표가 필요합니다 / 需要四个整数区域边界", 422)
    left, top, right, bottom = rectangle
    if not (0 <= left < right <= width and 0 <= top < bottom <= height and right - left >= 32 and bottom - top >= 32):
        raise StateError("영역은 원본 안에 있고 양변이 32픽셀 이상이어야 합니다 / 选区须在根图内且两边至少32像素", 422)


def check_region_change(db, order, body):
    if (order["revision"] != body["expected_revision"] or order["evidence_epoch"] != body["expected_evidence_epoch"]
            or not order["photos"] or order["photos"][-1]["id"] != body["expected_photo_id"]):
        raise StateError("주문·사진·증거 버전이 바뀌었습니다 / 订单、照片或证据版本已改变，请刷新")
    if order.get("active_inspection") or order["status"] == "completed":
        raise StateError("검증 중 또는 완료된 주문은 범위를 바꿀 수 없습니다 / 核验中或已完成订单不能修改范围")
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='field_studies'").fetchone():
        import json

        for record in db.execute("SELECT body FROM field_studies"):
            study = json.loads(record["body"])
            if study["status"] != "closed" and any(c["order_id"] == order["id"] for c in study["cases"]):
                raise StateError("등록된 사례입니다. 배치를 닫은 후 범위를 다시 선택하세요 / 案例已登记，请关闭批次后重选检查范围")
    photo = order["photos"][-1]
    root = resolve_root(order, photo)
    if root["id"] != body["root_photo_id"] or photo["revision"] != order["revision"] or root["revision"] != order["revision"]:
        raise StateError("현재 버전의 원본 사진이 필요합니다 / 需要当前订单版本的对应根照片")
    return photo, root


def derive_photo(order, root, raw, body):
    mode, rectangle = body["mode"], body["region_xyxy"]
    validate_rectangle(mode, rectangle, root["width"], root["height"])
    if mode == "region":
        with Image.open(io.BytesIO(raw)) as image:
            crop = image.convert("RGB").crop(rectangle)
            output = io.BytesIO()
            crop.save(output, format="JPEG", quality=95)
            content, size = output.getvalue(), crop.size
    else:
        content, size = raw, (root["width"], root["height"])
    identifier, stamp = uid("img"), now()
    photo = {
        "id": identifier, "url": f"/api/photos/{identifier}", "sha256": hashlib.sha256(content).hexdigest(),
        "revision": order["revision"], "created_at": stamp, "width": size[0], "height": size[1],
        "kind": "inspection_region_view", "scope_mode": mode, "root_photo_id": root["id"],
        "root_photo_sha256": root["sha256"], "source_family_sha256": root["sha256"],
        "root_width": root["width"], "root_height": root["height"], "region_xyxy": rectangle,
        "coordinate_space": COORDINATES,
        "derivation": "pillow_root_crop_rgb_jpeg95_v1" if mode == "region" else "normalized_root_bytes_v1",
        "scope_declaration": DECLARATION, "scope_confirmed_at": stamp, "root_created_at": root.get("created_at"),
    }
    if order.get("demo_source"):
        photo["demo_source"] = order["demo_source"]
    if "document_source" in order:
        photo["document_source"] = order["document_source"]
        photo["physical_capture"] = False
    return photo, content


def scope_html(scope, root_path):
    """An offline root-view overlay; supplied model points remain on their own view."""
    width, height = scope.get("root_width"), scope.get("root_height")
    if (not isinstance(root_path, str) or not re.fullmatch(r"photos/[A-Za-z0-9_-]{1,100}\.jpg", root_path)
            or type(width) is not int or type(height) is not int or min(width, height) <= 0):
        return "<p>원본 범위 표시 불가 / 根图范围信息不足</p>"
    box = ""
    rectangle = scope.get("region_xyxy")
    if scope.get("mode") == "region" and isinstance(rectangle, list) and len(rectangle) == 4 and all(type(n) is int for n in rectangle):
        left, top, right, bottom = rectangle
        if 0 <= left < right <= width and 0 <= top < bottom <= height:
            box = (f'<rect x="{left}" y="{top}" width="{right-left}" height="{bottom-top}" '
                   f'fill="none" stroke="#d33a22" stroke-width="{max(2, width/200):.2f}"/>')
    label = "같은 사진의 선택 영역 · 영역 밖 미검사 / 同一照片的选区视图 · 框外未核验" if box else "전체 저장 사진 / 完整保存照片"
    return (f'<figure class="inspection-scope"><figcaption>{label}</figcaption>'
            f'<svg role="img" aria-label="完整归一化根图与声明检查范围" viewBox="0 0 {width} {height}" '
            f'style="display:block;width:100%;max-height:600px"><image href="{html.escape(root_path, quote=True)}" '
            f'width="{width}" height="{height}"/>{box}</svg>'
            '<p>저장된 정규화 원본이며 카메라 RAW가 아닙니다. 범위는 작업자 선언입니다 / '
            '根图为系统保存的完整归一化照片，并非相机原始文件；范围完整性由操作者声明。</p></figure>')
