"""Portable, read-only evidence archives with photographs and verifiable digests."""
from __future__ import annotations

import hashlib
import html
import json
import re
import tempfile
import zipfile
from pathlib import Path

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
                payload["photos"].append({"id": photo_id, "archive_path": relative, **metadata})
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


def render_viewer(payload):
    order = payload["order"]
    esc = lambda value: html.escape(str(value), quote=True)
    photo_paths = {photo["id"]: photo["archive_path"] for photo in payload["photos"]}
    parts = [
        "<!doctype html><html lang='ko'><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>KitGuard Evidence</title><style>body{font:16px system-ui,sans-serif;max-width:960px;margin:40px auto;padding:0 24px;color:#152b35;background:#f6f8f7}h1{font-size:32px}section{background:white;border:1px solid #d4dfdc;border-radius:12px;padding:24px;margin:20px 0}img{max-width:100%;max-height:420px;object-fit:contain}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px ui-monospace,monospace;background:#f0f4f2;padding:16px}small{color:#48615a}a{color:#09695c}.notice{border-left:4px solid #c08328;padding:12px;background:#fff5dc}</style><body>",
        f"<small>KitGuard · 읽기 전용 / 只读证据快照</small><h1>{esc(order['title'])}</h1><p>R{order['revision']} · {esc(order['status'])} · {esc(payload['exported_at'])}</p><p class='notice'>공개 이미지/사진 관찰은 실제 부품 조작의 증명이 아닙니다. 모델은 틀릴 수 있습니다.<br>图像观察不能证明实际物料操作，模型可能出错。此快照不能用于新工单完成。</p><p><a href='evidence.json'>完整 JSON</a> · <a href='SHA256.json'>SHA-256 清单</a> · <a href='README.txt'>使用说明</a></p>",
    ]
    for check in order.get("checks", []):
        parts.append(
            f"<section><h2>R{check['revision']} · {esc(check['decision'])}</h2><p>{esc(check['id'])} · {esc(check.get('created_at', ''))} · valid={esc(check.get('valid'))}</p>"
        )
        if check["photo_id"] in photo_paths:
            parts.append(
                f"<img src='{esc(photo_paths[check['photo_id']])}' alt='Stored inspection photograph'>"
            )
        parts.append("<pre>" + esc(json.dumps(check, ensure_ascii=False, indent=2)) + "</pre></section>")
    parts.append("<section><h2>모든 사진 / 全部照片</h2>")
    for photo in payload["photos"]:
        parts.append(
            f"<details><summary>{esc(photo['id'])} · R{photo.get('revision', '?')}</summary><img loading='lazy' src='{esc(photo['archive_path'])}' alt='Stored photograph'><pre>{esc(photo.get('sha256'))}</pre></details>"
        )
    parts.append(
        "</section><section><h2>한계 / 限制</h2>"
        + "".join(f"<p>{esc(item)}</p>" for item in LIMITATIONS)
        + "</section></body></html>"
    )
    return "".join(parts)
