"""Portable closed-study evidence with the exact normalized input photographs."""

import hashlib
import html
import json
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from .field_study import render_report
from .regions import scope_html
from .store import StateError, now


def build_study_archive(studies, study_id):
    payload = studies.export(study_id)
    study = payload["study"]
    files = {"STUDY.json": (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode(),
             "REPORT.html": render_report(payload).encode()}
    bindings = []
    cards = []
    for case in study["cases"]:
        inputs = [("target", case["photo_id"], case["photo_sha256"])] + [
            ("reference:" + part, photo_id, case["reference_sha256"][part])
            for part, photo_id in case["reference_ids"].items()
        ]
        scope = case.get("inspection_scope")
        if scope and scope["root_photo_id"] != case["photo_id"]:
            inputs.append(("root", scope["root_photo_id"], scope["root_photo_sha256"]))
        case_images = []
        for role, photo_id, expected in inputs:
            raw = studies.store.photo_path(photo_id).read_bytes()
            actual = hashlib.sha256(raw).hexdigest()
            if actual != expected:
                raise StateError("등록된 사진 파일이 바뀌었습니다 / 登记照片文件已改变，不能导出错配证据")
            filename = f"photos/{actual}.jpg"
            files[filename] = raw
            bindings.append({"case_id": case["id"], "role": role, "photo_id": photo_id,
                             "sha256": actual, "bytes": len(raw), "archive_path": filename,
                             **({"inspection_scope": scope} if scope and role in {"target", "root"} else {})})
            if role == "root" and scope:
                case_images.append(scope_html(scope, filename))
                continue
            case_images.append(f'<figure><img src="{filename}" alt="{html.escape(role)}">'
                               f'<figcaption>{html.escape(role)} · {html.escape(photo_id)}<br>SHA256 {actual}</figcaption></figure>')
        cards.append(f'<article><h2>{html.escape(case["label"])}</h2><p>{html.escape(case["id"])} · '
                     f'{html.escape(case["order_id"])} · R{case["revision"]}</p>{"".join(case_images)}</article>')
    style = ('body{font-family:system-ui,sans-serif;max-width:1100px;margin:32px auto;padding:0 18px;'
             'color:#193e37;background:#f7f8f5;line-height:1.65;overflow-wrap:anywhere}'
             'article{background:white;border:1px solid #ccd8d3;border-radius:12px;padding:20px;margin:20px 0}'
             'img{display:block;max-width:100%;max-height:700px;object-fit:contain}figure{margin:12px 0}a{color:inherit}')
    title = html.escape(study["title"])
    source = html.escape(study["source_kind"])
    files["PHOTOS.html"] = (f'<!doctype html><html lang="ko"><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} · Photos</title>'
        f'<style>{style}</style><a href="OPEN_ME.html">← KitGuard</a><h1>{title}</h1>'
        f'<p>사진 증거 / 照片证据 · {source}</p><p>저장된 정규화 사진 / 登记的归一化照片，未包含相机原始EXIF。'
        f'文件散列不证明拍摄者、时间或实物真实性。</p>{"".join(cards)}</html>').encode()
    files["OPEN_ME.html"] = (f'<!doctype html><html lang="ko"><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>'
        f'<style>{style}</style><h1>{title}</h1><p>검증 증거 패키지 / 验证证据包 · {source}</p>'
        '<article><p><a href="REPORT.html">검증 보고서 / 统计与逐例报告 →</a></p>'
        '<p><a href="PHOTOS.html">원본 입력 사진 / 实际输入照片 →</a></p>'
        '<p><a href="STUDY.json">完整记录 JSON →</a></p>'
        '<p><a href="MANIFEST.json">文件校验清单 →</a></p></article>'
        '<p>완료한 물품의 인증서가 아닙니다 / 这不是实物完工证明。'
        '来源、独立计数与现场真实性仍是操作者声明；公开图和工程测试不能作为真人现场结果。</p></html>').encode()
    manifest = {"schema_version": 1, "kind": "kitguard_closed_study_evidence", "study_id": study_id,
                "created_at": now(), "source_kind": study["source_kind"], "photo_bindings": bindings,
                "files": [{"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
                          for name, raw in sorted(files.items())],
                "scope": "Closed-study text and exact normalized photos; not signatures, scene authenticity or field-effectiveness certification."}
    files["MANIFEST.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    folder = studies.store.directory / "exports"
    folder.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix="study-", suffix=".zip", dir=folder, delete=False) as temporary:
        path = Path(temporary.name)
    try:
        with ZipFile(path, "w", ZIP_DEFLATED, compresslevel=6) as archive:
            for name, raw in files.items():
                archive.writestr(name, raw)
        return path
    except BaseException:
        path.unlink(missing_ok=True)
        raise
