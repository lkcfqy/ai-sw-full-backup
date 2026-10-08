"""Derive the sole nonintersecting two-bracket author ROI, before any inference."""

import copy
import hashlib
import itertools
import json
import math
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def main():
    parent = ROOT / "datasets/manifests/v0.4/ino_l_bracket_external_v1"
    original = json.loads((parent / "manifest.json").read_text())
    quality = json.loads((parent / "data_quality.json").read_text())
    output = parent.parent / "ino_two_bracket_diagnostic_v1"
    derived = ROOT / "datasets/derived/v0.4/ino_two_bracket_diagnostic_v1"
    if output.exists() or derived.exists():
        raise SystemExit("Preserve previous preparation")
    used = {case["source_id"] for case in original["cases"]}
    records, selections = [], []
    for row in quality["records"]:
        labels = row["author_rows"]
        if ("ino-10-190:" + row["source_id"] in used or len(labels) <= 1
                or any(item["class_id"] != 0 for item in labels)):
            continue
        width, height = row["source_dimensions"]
        boxes = [[item["xyxy"][0]*width, item["xyxy"][1]*height,
                  item["xyxy"][2]*width, item["xyxy"][3]*height] for item in labels]
        candidates = []
        for count in (2, 3):
            for selected in itertools.combinations(range(len(boxes)), count):
                chosen = [boxes[i] for i in selected]
                union = [min(b[0] for b in chosen), min(b[1] for b in chosen),
                         max(b[2] for b in chosen), max(b[3] for b in chosen)]
                pad = .1 * min(union[2]-union[0], union[3]-union[1])
                roi = [math.floor(union[0]-pad), math.floor(union[1]-pad),
                       math.ceil(union[2]+pad), math.ceil(union[3]+pad)]
                if roi[0] < 0 or roi[1] < 0 or roi[2] > width or roi[3] > height:
                    continue
                if any(roi[0] <= b[2] and roi[2] >= b[0] and roi[1] <= b[3] and roi[3] >= b[1]
                       for i, b in enumerate(boxes) if i not in selected):
                    continue
                candidates.append({"count": count, "selected_rows_zero_based": list(selected),
                                   "roi": roi, "area": (roi[2]-roi[0])*(roi[3]-roi[1])})
        ranked = sorted(candidates, key=lambda c: (-c["count"], -c["area"], c["roi"]))
        records.append({"source_id": row["source_id"], "candidates": ranked,
                        "selected": ranked[0] if ranked else None})
        if ranked:
            selections.append((row, ranked[0]))
    assert len(selections) == 1
    row, chosen = selections[0]
    # Independent metadata-only reviewer reproduced these coordinates and row identities.
    assert row["source_id"] == "F/52" and chosen["count"] == 2
    assert chosen["roi"] == [612, 277, 839, 635] and chosen["selected_rows_zero_based"] == [1, 3]
    source = ROOT / "datasets" / row["source_image"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == row["source_image_sha256"]
    derived.mkdir(parents=True)
    image = derived / "F_52_two.png"
    with Image.open(source) as opened:
        opened.convert("RGB").crop(chosen["roi"]).save(image)
    case = {"id": "ino-two-bracket-F-52", "source_id": "ino-10-190:F/52", "author_group": "F",
            "image": str(image.relative_to(ROOT / "datasets")),
            "sha256": hashlib.sha256(image.read_bytes()).hexdigest(), "view_kind": "author_box_roi",
            "ground_truth": {"bracket": 2}, "unlabeled_categories": ["bolt", "nut", "washer"],
            "author_class_id": 0, "source_image": row["source_image"],
            "source_image_sha256": row["source_image_sha256"], "annotation": row["annotation"],
            "annotation_sha256": row["annotation_sha256"], "roi_xyxy": chosen["roi"],
            "selected_author_rows_zero_based": chosen["selected_rows_zero_based"]}
    manifest = copy.deepcopy(original)
    manifest.update({"name": output.name, "created_at": datetime.now(UTC).isoformat(), "cases": [case],
        "preparation_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "parent_manifest_sha256": hashlib.sha256((parent / "manifest.json").read_bytes()).hexdigest(),
        "rules": {"source_variant": "origin", "unused_pure_class0_sources_only": True,
                  "enumerate_counts": [2, 3], "margin_short_side_fraction": .1,
                  "other_box_touch_disallowed": True,
                  "selection_order": "most targets, largest ROI, coordinates lexicographic",
                  "one_case_per_source": True},
        "limitations": [
            "Exactly one two-bracket case. This cannot establish multi-object stability or generic counting accuracy.",
            "Author-box oracle ROI: selected complete boxes are inside; every omitted box is outside and does not touch.",
            "A constant answer 2 scores 1/1. Constant 1 scores 0/1. This is a separate diagnostic, not a new balanced benchmark.",
            "Counts 2 and 3 were enumerated before inference on all unused pure-class0 source images; only F/52 yields a valid crop.",
            "No input image was viewed or model output consulted when selecting the ROI. No object is pasted, erased or partially cut by a box.",
            "The other three product categories remain unlabelled; no four-class readiness claim.",
        ]})
    output.mkdir()
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    (output / "selection_audit.json").write_text(json.dumps({"reviewed": records}, indent=2) + "\n")
    print(json.dumps({"manifest": str(output / "manifest.json"),
                      "sha256": hashlib.sha256((output / "manifest.json").read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()
