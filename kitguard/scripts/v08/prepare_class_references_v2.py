#!/usr/bin/env python3
"""Prepare only the three parent-selected training crops for AI visual QA."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from prepare_class_references import ROOT, now, oriented_box, overlap_area, save, sha

OUTPUT = ROOT / "datasets/derived/v0.8/class_reference_dev_v2"


def main():
    if OUTPUT.exists():
        raise FileExistsError(f"Preserve existing preparation: {OUTPUT}")
    rank_path = ROOT / "datasets/derived/v0.8/class_reference_dev_v1/nut_quality_candidates.json"
    ranking = json.loads(rank_path.read_text())
    train_path = ROOT / "datasets/derived/public_detector_v1/train.json"
    if sha(train_path) != ranking["train_manifest_sha256"]:
        raise ValueError("Training metadata changed after candidate ranking")
    train = json.loads(train_path.read_text())
    images = {i["id"]: i for i in train["images"]}
    annotations = {a["id"]: a for a in train["annotations"]}
    items = [{
        "part": "washer", "source": "datasets/raw/mvtec_loco_ad/screw_bag/train/good/057.png",
        "source_sha256": "525a366f58623a4e100dbd04387c9c8ddeac39b025fd6545ed2cb94dd3791f88",
        "expected_source_size": [1600, 1100], "rect_source_px": [528, 690, 663, 819],
        "source_role": "Official LOCO train/good; previously exposed development",
        "label_basis": "Author normal bag composition plus root AI identification; not author instance annotation",
        "box_basis": "Root AI original-image rectangle, tightened after inspecting v1 crop",
        "output": "washer-loco057-ai-selected-tight.png",
    }]
    expected = [(297004, [1028, 144, 1104, 220]), (339004, [704, 989, 782, 1065])]
    for rank, (candidate, (annotation_id, rect)) in enumerate(zip(ranking["top_two"], expected, strict=True), 1):
        if candidate["annotation_id"] != annotation_id or candidate["crop_with_margin"] != rect:
            raise ValueError("Ranked candidate differs from root-selected metadata")
        annotation = annotations[annotation_id]
        original = images[annotation["image_id"]]
        if original["original_split"] != "train" or original["file_name"] != candidate["source"]:
            raise ValueError("Candidate is not in official train214")
        if annotation["original_category_id"] != 7 or annotation["bbox_clipped"]:
            raise ValueError("Expected un-clipped type_007")
        neighbors = []
        for other in train["annotations"]:
            if other["image_id"] != annotation["image_id"] or other["id"] == annotation_id:
                continue
            x, y, w, h = other["bbox"]
            area = overlap_area([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], rect)
            oriented_area = overlap_area(oriented_box(other["original_bbox_row_col_width_height_phi"]), rect)
            neighbors.append({"annotation_id": other["id"], "aabb_intersection_px2": area,
                              "oriented_box_intersection_px2": oriented_area})
        if any(n["aabb_intersection_px2"] > 1e-7 for n in neighbors):
            raise ValueError("Padded crop intersects a neighboring author AABB")
        items.append({
            "part": "nut", "quality_rank": rank, "source": candidate["source"],
            "source_sha256": candidate["source_sha256"], "expected_source_size": [original["width"], original["height"]],
            "rect_source_px": rect, "source_role": "Official Screws train; public_detector_v1 train214",
            "label_basis": "Author type_007 -> Neuromatch teaching alias -> existing KitGuard nut projection",
            "box_basis": "Author oriented box converted to AABB, outward integer rounding and 4px margin",
            "author_annotation": annotation, "neighbor_annotation_checks": neighbors,
            "output": f"nut-rank{rank}-screws{annotation['image_id']:03d}-a{annotation_id}.png",
        })
    for item in items:
        if sha(ROOT / item["source"]) != item["source_sha256"]:
            raise ValueError(f"Source SHA differs: {item['source']}")
        item["license"] = "CC BY-NC-SA 4.0; local noncommercial research"
    selection = {
        "schema": "kitguard.v08.class-reference-development.selection.v2",
        "created_at_utc": now(), "status": "selected_for_visual_qa_before_decode",
        "development_only": True, "frozen_inference_protocol": False, "model_called": False,
        "reviewer": "Codex root AI; not human annotation or user validation",
        "script_sha256": sha(Path(__file__)),
        "helper_script_sha256": sha(Path(__file__).with_name("prepare_class_references.py")),
        "ranking_sha256": sha(rank_path), "train_manifest_sha256": sha(train_path),
        "v1_review": {
            "nut_002_2001": "Root viewed v1 crop: white ring visible with other bright material/context at edge; not adopted, preserved",
            "washer_057": "Root viewed v1 crop: complete clear washer, tiny gray tip of upper neighboring bolt at upper-right edge; tighten original-coordinate rectangle",
        },
        "qa_selection_rule": "Inspect rank1 first; use if acceptable, otherwise inspect rank2 and record quality reason. No model predictions used.",
        "items": items,
    }
    OUTPUT.mkdir(parents=True)
    save(OUTPUT / "selection.json", selection)
    receipt = {"schema": "kitguard.v08.class-reference-development.preparation.v2",
               "started_at_utc": now(), "selection_sha256": sha(OUTPUT / "selection.json"),
               "selection_preceded_decoding": True, "model_called": False,
               "pixel_resampling": False, "exif_transpose": False, "images_decoded": 0,
               "approved_for_inference": False, "status": "preparing", "images": []}
    try:
        from PIL import Image

        for item in items:
            with Image.open(ROOT / item["source"]) as image:
                if list(image.size) != item["expected_source_size"] or image.format != "PNG":
                    raise ValueError("Original coordinate size/format mismatch")
                if image.mode != "RGB" or image.getexif():
                    raise ValueError("Expected RGB source without EXIF transform")
                image.load()
                receipt["images_decoded"] += 1
                left, top, right, bottom = item["rect_source_px"]
                if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
                    raise ValueError("Crop outside original image")
                crop = image.crop((left, top, right, bottom))
                path = OUTPUT / item["output"]
                with path.open("xb") as stream:
                    crop.save(stream, format="PNG")
                receipt["images"].append({**item, "source_size_verified": list(image.size),
                                          "crop_size": list(crop.size), "crop_sha256": sha(path),
                                          "crop_rgb_sha256": hashlib.sha256(crop.tobytes()).hexdigest(),
                                          "qa_status": "awaiting_root_ai_visual_review"})
        receipt["status"] = "prepared_awaiting_root_ai_visual_review"
    except Exception as exc:
        receipt.update(status="failed_partial_preserved", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        receipt["finished_at_utc"] = now()
        save(OUTPUT / "preparation.json", receipt)
    print(json.dumps({"status": receipt["status"], "crops": [str(OUTPUT / i["output"]) for i in items]}))


if __name__ == "__main__":
    main()
