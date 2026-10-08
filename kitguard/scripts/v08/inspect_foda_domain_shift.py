"""Bounded visual diagnostic of already exposed FOD train/validation sources.

Select two image IDs per nut/washer source group before decoding any pixels.
No held-back files, models, relabelling or inference are used.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "datasets/derived/v0.8/foda_grouped_v1"
OUT = ROOT / "test-results/v0.8/foda-domain-visual-diagnostic-v1"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    groups = defaultdict(list)
    bindings = []
    for role in ("train", "validation"):
        path = DATA / f"{role}.json"
        bindings.append({"path": str(path.relative_to(ROOT)), "sha256": sha(path)})
        for row in json.loads(path.read_text()):
            if row["author_category"] in ("Nut", "Washer"):
                assert row["protocol_role"] == role
                groups[(row["author_category"], role, row["group_id"])].append(row)
    selected = [row for key in sorted(groups)
                for row in sorted(groups[key], key=lambda r: r["image_id"])[:2]]
    selection = {"created_at": datetime.now(UTC).isoformat(),
                 "selection_rule": "Two lexicographically smallest image IDs per author class, role and source group",
                 "purpose": "posthoc_visual_diagnosis_only", "model_called": False,
                 "held_back_read": False, "exposure": "previously_used_for_training_or_validation",
                 "annotation_scope": "author_annotated_target_only", "source_bindings": bindings,
                 "script_sha256": sha(__file__), "items": selected}
    save(OUT / "selection_before_decode.json", selection)
    font = ImageFont.load_default(size=17)
    small = ImageFont.load_default(size=14)
    products = []
    for category in ("Nut", "Washer"):
        rows = [r for r in selected if r["author_category"] == category]
        sheet = Image.new("RGB", (650, 365 * len(rows) + 56), "#ffffff")
        draw = ImageDraw.Draw(sheet)
        draw.text((12, 9), f"Author {category}: exposed development sources", fill="black", font=font)
        draw.text((12, 31), "Left: original + author box. Right: crop enlarged, no new detail.", fill="black", font=small)
        for i, row in enumerate(rows):
            path = ROOT / row["local_image"]
            assert sha(path) == row["image_sha256"]
            image = Image.open(path).convert("RGB")
            assert image.size == tuple(row["image_size"])
            x1, y1, x2, y2 = row["box_xyxy"]
            crop_box = (max(0, math.floor(x1) - 4), max(0, math.floor(y1) - 4),
                        min(image.width, math.ceil(x2) + 4), min(image.height, math.ceil(y2) + 4))
            crop = image.crop(crop_box)
            crop_path = OUT / f"{row['protocol_role']}-{row['image_id']}-crop.png"
            crop.save(crop_path)
            display = image.copy()
            ImageDraw.Draw(display).rectangle(row["box_xyxy"], outline="#d02626", width=1)
            y = 56 + 365 * i
            label = f"{row['protocol_role']} / {row['group_id']} / {row['image_id']}"
            draw.text((12, y), label, fill="black", font=font)
            draw.text((12, y + 23), f"Author box {x2-x1:.1f} x {y2-y1:.1f}px; crop {crop.width} x {crop.height}px",
                      fill="#333333", font=small)
            sheet.paste(display, (12, y + 47))
            enlarged = crop.copy()
            enlarged.thumbnail((300, 300), Image.Resampling.NEAREST)
            scale = min(300 / crop.width, 300 / crop.height)
            enlarged = crop.resize((round(crop.width * scale), round(crop.height * scale)),
                                   Image.Resampling.NEAREST)
            sheet.paste(enlarged, (335, y + 47))
            products.append({"image_id": row["image_id"], "crop_xyxy": crop_box,
                             "path": str(crop_path.relative_to(ROOT)), "sha256": sha(crop_path),
                             "size": list(crop.size), "original_pixels_preserved": True})
        path = OUT / f"{category.lower()}-contact.png"
        sheet.save(path)
        products.append({"path": str(path.relative_to(ROOT)), "sha256": sha(path), "size": list(sheet.size)})
    save(OUT / "receipt.json", {"selection_sha256": sha(OUT / "selection_before_decode.json"),
                               "products": products, "label_changes": False,
                               "visual_findings_pending": True})
    print(json.dumps({"status": "prepared", "images": len(selected), "output": str(OUT)}))


if __name__ == "__main__":
    main()
