"""Freeze every unused, pure author-L-bracket full image with more than one target."""

import copy
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parent = ROOT / "datasets/manifests/v0.4/ino_l_bracket_external_v1"
    original = json.loads((parent / "manifest.json").read_text())
    quality = json.loads((parent / "data_quality.json").read_text())
    output = parent.parent / "ino_l_bracket_full_multi_v1"
    if output.exists():
        raise SystemExit("Preserve the existing preparation")
    used = {case["source_id"] for case in original["cases"]}
    cases = []
    reviewed = []
    for row in quality["records"]:
        source_id = "ino-10-190:" + row["source_id"]
        labels = row["author_rows"]
        eligible = (source_id not in used and len(labels) > 1
                    and all(item["class_id"] == 0 for item in labels)
                    and all(min(item["xyxy"][:2]) >= 0 and max(item["xyxy"][2:]) <= 1
                            for item in labels))
        reviewed.append({"source_id": source_id, "eligible": eligible,
                         "classes": [item["class_id"] for item in labels]})
        if not eligible:
            continue
        for filename, digest in ((row["source_image"], row["source_image_sha256"]),
                                 (row["annotation"], row["annotation_sha256"])):
            assert hashlib.sha256((ROOT / "datasets" / filename).read_bytes()).hexdigest() == digest
        width, height = row["source_dimensions"]
        cases.append({
            "id": "ino-full-multi-" + row["source_id"].replace("/", "-"),
            "source_id": source_id, "author_group": row["author_group"],
            "image": row["source_image"], "sha256": row["source_image_sha256"],
            "view_kind": "full_image", "ground_truth": {"bracket": len(labels)},
            "unlabeled_categories": ["bolt", "nut", "washer"], "author_class_id": 0,
            "source_image": row["source_image"], "source_image_sha256": row["source_image_sha256"],
            "annotation": row["annotation"], "annotation_sha256": row["annotation_sha256"],
            "roi_xyxy": [0, 0, width, height],
        })
    assert [case["source_id"] for case in cases] == ["ino-10-190:F/52", "ino-10-190:F/53", "ino-10-190:F/54"]
    assert all(case["ground_truth"] == {"bracket": 4} for case in cases)
    manifest = copy.deepcopy(original)
    manifest.update({
        "name": output.name, "created_at": datetime.now(UTC).isoformat(), "cases": cases,
        "status": "metadata_exploration_not_evaluated",
        "preparation_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "parent_manifest_sha256": hashlib.sha256((parent / "manifest.json").read_bytes()).hexdigest(),
        "rules": {"source_variant": "origin", "unused_source_ids_only": True,
                  "all_author_boxes_class0": True, "minimum_target_count": 2,
                  "valid_boxes_required": True, "input": "full unchanged author image"},
        "inference_performed": False,
        "limitations": [
            "Three full-image sources, all four L-brackets, all author group F. Metadata exploration only: not executed; four exceeds product per-class BOM limit of three.",
            "Selection was added after metadata inspection found the original count<=3 limit excluded all multi-target images, before any inference.",
            "Original twenty-case manifest is unchanged. This is a separate prespecified extension, not a replacement or selected model success.",
            "Only author class 0 bracket counts are labelled; bolt/nut/washer remain unlabelled.",
            "Constant prediction 4 scores 3/3 on this extension; constant prediction 1 scores 0/3. This is a small diagnostic, not generic counting validation.",
            "Author target locations did not crop or modify these full-image inputs. Class labels still select pure-target scenes.",
        ],
    })
    output.mkdir()
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    (output / "selection_audit.json").write_text(json.dumps({"records": reviewed, "selected": len(cases)}, indent=2) + "\n")
    print(json.dumps({"path": str(output / "manifest.json"), "cases": len(cases),
                      "sha256": hashlib.sha256((output / "manifest.json").read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()
