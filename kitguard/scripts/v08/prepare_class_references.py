#!/usr/bin/env python3
"""Prepare two explicitly selected development references; never load a model.

Selection is saved before decoding. Original-coordinate crops are unresized,
and remain pending AI visual review rather than becoming approved references.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "datasets/derived/v0.8/class_reference_dev_v1"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now():
    return datetime.now(UTC).isoformat()


def save(path, payload):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def oriented_box(bbox):
    """Author phi is positive towards image top, per README_v1.0.txt."""
    row, col, width, height, phi = bbox
    cosine, sine = math.cos(phi), math.sin(phi)
    return [
        [col + u * cosine + v * sine, row - u * sine + v * cosine]
        for u, v in [(-width / 2, -height / 2), (width / 2, -height / 2),
                     (width / 2, height / 2), (-width / 2, height / 2)]
    ]


def overlap_area(polygon, rect):
    """Sutherland-Hodgman intersection with a continuous XYXY rectangle."""
    for axis, bound, sign in [(0, rect[0], 1), (0, rect[2], -1),
                              (1, rect[1], 1), (1, rect[3], -1)]:
        clipped = []
        for a, b in zip(polygon, polygon[1:] + polygon[:1]):
            inside_a = sign * (a[axis] - bound) >= 0
            inside_b = sign * (b[axis] - bound) >= 0
            if inside_a:
                clipped.append(a)
            if inside_a != inside_b:
                ratio = (bound - a[axis]) / (b[axis] - a[axis])
                clipped.append([a[i] + ratio * (b[i] - a[i]) for i in range(2)])
        polygon = clipped
    return abs(sum(a[0] * b[1] - b[0] * a[1]
                   for a, b in zip(polygon, polygon[1:] + polygon[:1]))) / 2


def main():
    if OUTPUT.exists():
        raise FileExistsError(f"Preserve existing preparation: {OUTPUT}")
    original_path = ROOT / "datasets/raw/mvtec_screws_v1.0/mvtec_screws.json"
    original = json.loads(original_path.read_text())
    target = next(a for a in original["annotations"] if a["id"] == 2001)
    assert target["image_id"] == 2 and target["category_id"] == 7
    assert target["bbox"] == [185.4, 872.465, 64, 62.5631, 0]
    points = oriented_box(target["bbox"])
    nut_rect = [math.floor(min(p[0] for p in points)), math.floor(min(p[1] for p in points)),
                math.ceil(max(p[0] for p in points)), math.ceil(max(p[1] for p in points))]
    selection = {
        "schema": "kitguard.v08.class-reference-development.selection.v1",
        "created_at_utc": now(), "status": "selected_before_decode_and_inference",
        "development_only": True, "frozen_inference_protocol": False,
        "selection_basis": "Pre-inference clarity/completeness development review, not model outcomes",
        "reviewer": "Codex root AI visual inspection; not a human annotator",
        "model_called": False, "script_sha256": sha(Path(__file__)),
        "annotations": {"path": str(original_path.relative_to(ROOT)), "sha256": sha(original_path)},
        "rejected_candidates": [
            {"source": "datasets/derived/v0.8/foda_grouped_v1/images/train/016255.jpg",
             "reason": "Existing AI review: small and blurry; unsuitable as clear reference"},
            {"source": "datasets/raw/mvtec_loco_ad/screw_bag/train/good/046.png",
             "reason": "Root AI compared original 046/057: right washer closer to neighboring nut"},
        ],
    }
    # Literal expected source identities, independent of current file contents.
    selection["items"] = [
        {"part": "nut", "source": "datasets/raw/mvtec_screws_v1.0/images/screws_002.png",
         "source_sha256": "50538bce31d1a2377e5fad3b087d1a8864c14084b9ee7a579b7bd233e0448fbe",
         "expected_source_size": [1920, 1440], "rect_source_px": nut_rect,
         "source_role": "Official train; already used in public_detector_v1 training",
         "label_basis": "Author type_007 annotation 2001; Neuromatch alias and existing KitGuard mapping to nut",
         "box_basis": "Outward-rounded AABB enclosing author's oriented box; phi=0 for this instance",
         "author_annotation": target, "output": "nut-screws002-a2001.png"},
        {"part": "washer", "source": "datasets/raw/mvtec_loco_ad/screw_bag/train/good/057.png",
         "source_sha256": "525a366f58623a4e100dbd04387c9c8ddeac39b025fd6545ed2cb94dd3791f88",
         "expected_source_size": [1600, 1100], "rect_source_px": [524, 682, 665, 819],
         "source_role": "Official train/good; already exposed in integrated 28 development set",
         "label_basis": "Author normal screw_bag composition plus root AI identification of lower silver split/spring washer",
         "box_basis": "Root AI-selected original-image rectangle; not an author instance annotation",
         "visual_selection_note": "Root viewed originals 046/057; selected complete lower isolated washer in 057, estimated center (596,750)",
         "output": "washer-loco057-ai-selected.png"},
    ]
    for item in selection["items"]:
        source = ROOT / item["source"]
        if sha(source) != item["source_sha256"]:
            raise ValueError(f"Source SHA differs: {source}")
        item["license"] = "CC BY-NC-SA 4.0; local noncommercial research"
    OUTPUT.mkdir(parents=True)
    save(OUTPUT / "selection.json", selection)
    receipt = {
        "schema": "kitguard.v08.class-reference-development.preparation.v1",
        "started_at_utc": now(), "selection_sha256": sha(OUTPUT / "selection.json"),
        "selection_preceded_decoding": True, "model_called": False,
        "pixel_resampling": False, "exif_transpose": False,
        "images_decoded": 0, "images": [], "status": "preparing",
        "approved_for_inference": False,
    }
    try:
        from PIL import Image

        for item in selection["items"]:
            source = ROOT / item["source"]
            with Image.open(source) as image:
                if list(image.size) != item["expected_source_size"]:
                    raise ValueError(f"Original coordinate size mismatch: {source}")
                if image.format != "PNG" or image.mode != "RGB" or image.getexif():
                    raise ValueError("Expected unrotated RGB PNG with no EXIF")
                image.load()
                receipt["images_decoded"] += 1
                left, top, right, bottom = item["rect_source_px"]
                if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
                    raise ValueError("Crop rectangle outside verified original size")
                output = OUTPUT / item["output"]
                crop = image.crop((left, top, right, bottom))
                with output.open("xb") as stream:
                    crop.save(stream, format="PNG")
                record = {**item, "source_size_verified": list(image.size),
                          "crop_size": list(crop.size), "crop_sha256": sha(output),
                          "crop_rgb_sha256": hashlib.sha256(crop.tobytes()).hexdigest(),
                          "qa_status": "awaiting_root_ai_visual_review"}
                if item["part"] == "nut":
                    neighbors = []
                    for other in original["annotations"]:
                        if other["image_id"] != 2 or other["id"] == 2001:
                            continue
                        polygon = oriented_box(other["bbox"])
                        aabb = [[min(p[0] for p in polygon), min(p[1] for p in polygon)],
                                [max(p[0] for p in polygon), min(p[1] for p in polygon)],
                                [max(p[0] for p in polygon), max(p[1] for p in polygon)],
                                [min(p[0] for p in polygon), max(p[1] for p in polygon)]]
                        neighbors.append({"annotation_id": other["id"], "category_id": other["category_id"],
                                          "author_bbox": other["bbox"],
                                          "aabb_intersection_px2": overlap_area(aabb, item["rect_source_px"]),
                                          "oriented_box_intersection_px2": overlap_area(polygon, item["rect_source_px"])})
                    record["neighbor_annotation_checks"] = neighbors
                    record["neighbor_warning"] = "Author boxes overlap this crop; pixel-level contamination must be visually reviewed"
                receipt["images"].append(record)
        receipt["status"] = "prepared_awaiting_root_ai_visual_review"
    except Exception as exc:
        receipt["status"] = "failed_partial_preserved"
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        receipt["finished_at_utc"] = now()
        save(OUTPUT / "preparation.json", receipt)
    print(json.dumps({"status": receipt["status"], "output": str(OUTPUT),
                      "crops": [r["output"] for r in receipt["images"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
