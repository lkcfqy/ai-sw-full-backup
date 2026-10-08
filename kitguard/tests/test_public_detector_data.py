"""Synthetic metadata fixtures test conversion and isolation, not model quality."""

import copy
import json
import math

import pytest
from PIL import Image

from scripts import prepare_public_detector_data as prepare


def save(root, relative, data):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def load(root, relative):
    return json.loads((root / relative).read_text())


def repin(root):
    source = load(root, prepare.SOURCE)
    source["upstream_annotation_sha256"] = prepare.sha256((root / prepare.ANNOTATIONS).read_bytes())
    save(root, prepare.SOURCE, source)
    return {path: prepare.sha256((root / path).read_bytes()) for path in prepare.PINNED_HASHES}


@pytest.fixture
def source_fixture(tmp_path):
    categories = [{"id": i, "name": f"type_{i:03d}", "supercategory": "object"} for i in range(1, 14)]
    images, annotations, metadata = [], [], []
    split_for = {1: "train", 2: "train", 3: "val", 4: "test", 5: "train"}
    for index in range(1, 6):
        filename = f"screws_{index:03d}.png"
        relative = f"{prepare.RAW}/images/{filename}"
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (10, 8), color=(index * 40, 20, 30)).save(path)
        digest = prepare.sha256(path.read_bytes())
        images.append({"id": index, "file_name": filename, "width": 10, "height": 8, "license": 1})
        annotations.append({"id": index * 1000 + 1, "image_id": index, "category_id": 7 if index % 2 else 1,
                            "bbox": [4, 5, 4, 2, 0], "area": 8, "is_crowd": 0})
        metadata.append({"id": index, "path": relative, "width": 10, "height": 8,
                         "sha256": digest, "upstream_split": split_for[index]})
    original = {"categories": categories, "images": images, "annotations": annotations,
                "licenses": {"id": 1, "name": "CC-BY-NC-SA-4.0", "url": "https://example.invalid/license"}}
    save(tmp_path, prepare.ANNOTATIONS, original)
    for split in ("train", "val", "test"):
        document = {**original, "images": [], "annotations": []}
        # Split-local IDs deliberately restart, like the real author data.
        for local_id, image in enumerate((i for i in images if split_for[i["id"]] == split), 1):
            document["images"].append({**image, "id": local_id})
            annotation = annotations[image["id"] - 1]
            document["annotations"].append({**annotation, "image_id": local_id, "id": local_id * 1000 + 1})
        save(tmp_path, f"{prepare.RAW}/mvtec_screws_{split}.json", document)
    source = {"dataset": "SYNTHETIC UNIT FIXTURE", "author": "unit test", "author_page": "https://example.invalid",
              "source_page": "https://example.invalid", "download_url": "https://example.invalid",
              "archive_sha256": "0" * 64, "license": "CC-BY-NC-SA-4.0", "license_url": "https://example.invalid",
              "upstream_annotation_path": prepare.ANNOTATIONS, "upstream_annotation_sha256": "pending",
              "category_mapping": {str(k): prepare.CATEGORIES[v - 1]["name"] for k, v in prepare.CLASS_MAPPING.items()},
              "image_count": 5, "annotation_count": 5, "images": metadata}
    save(tmp_path, prepare.SOURCE, source)
    for index, relative in enumerate(prepare.EXCLUSION_FILES):
        if index == 0:
            document = {"cases": [{"id": "old-evaluation", "image": metadata[4]["path"],
                                   "sha256": metadata[4]["sha256"], "split": "holdout"}]}
        else:
            document = {"views": [{"id": f"crop-{index}", "source_image": metadata[4]["path"],
                                   "source_sha256": metadata[4]["sha256"], "proposed_split": "holdout"}]}
        save(tmp_path, relative, document)
    return tmp_path, repin(tmp_path)


def build(fixture):
    root, hashes = fixture
    return prepare.build_artifacts(root, pinned_hashes=hashes,
                                   expected_counts={"train": (2, 2), "val": (1, 1), "test": (1, 1)},
                                   expected_excluded=1)


@pytest.mark.parametrize("phi,expected", [
    (0, [16, 8, 8, 4]),
    (math.pi / 2, [18, 6, 4, 8]),
    (math.pi / 4, [20 - 3 * math.sqrt(2), 10 - 3 * math.sqrt(2), 6 * math.sqrt(2), 6 * math.sqrt(2)]),
    (-math.pi / 4, [20 - 3 * math.sqrt(2), 10 - 3 * math.sqrt(2), 6 * math.sqrt(2), 6 * math.sqrt(2)]),
    (3 * math.pi / 2, [18, 6, 4, 8]),
])
def test_rotation_uses_row_col_centers_and_full_lengths(phi, expected):
    bbox, clipped = prepare.author_box_to_xywh([10, 20, 8, 4, phi], 100, 80)
    assert bbox == pytest.approx(expected)
    assert not clipped


def test_clip_keeps_visible_annotation_and_recomputes_area():
    bbox, clipped = prepare.author_box_to_xywh([0, 1, 6, 4, 0], 10, 8)
    assert bbox == [0, 0, 4, 2] and clipped


@pytest.mark.parametrize("bbox", [[1, 2, 0, 2, 0], [1, 2, 2, -1, 0], [1, 2, 2, 2, math.inf],
                                 [math.nan, 2, 2, 2, 0], [1, 2, 2, 2],
                                 [1000, 1000, 2, 2, 0], [True, 2, 2, 2, 0]])
def test_invalid_bbox_fails_closed(bbox):
    with pytest.raises(ValueError):
        prepare.author_box_to_xywh(bbox, 10, 8)


def test_author_split_join_and_all_same_source_crops_are_excluded(source_fixture):
    artifacts = build(source_fixture)
    assert [i["id"] for i in artifacts["val.json"]["images"]] == [3]
    assert artifacts["val.json"]["annotations"][0]["image_id"] == 3
    assert artifacts["val.json"]["annotations"][0]["category_id"] == 2
    assert len(artifacts["train.json"]["images"]) == 2
    manifest = artifacts["manifest.json"]
    assert manifest["excluded_original_count"] == 1
    assert len(manifest["excluded_originals"][0]["evidence"]) == 5
    assert manifest["uncovered_categories"] == ["washer", "bracket"]
    assert artifacts["test.json"]["images"][0]["file_name"].startswith(prepare.RAW)
    assert artifacts["test.json"]["images"][0]["original_split"] == "test"
    assert manifest["duplicate_audit"]["images_checked"] == 5


def test_raw_manifest_tampering_is_rejected_before_conversion(source_fixture):
    root, _ = source_fixture
    (root / prepare.SOURCE).write_text((root / prepare.SOURCE).read_text() + " ")
    with pytest.raises(ValueError, match="Source hash mismatch"):
        build(source_fixture)


@pytest.mark.parametrize("kind", ["image", "annotation"])
def test_duplicate_original_ids_fail_closed(source_fixture, kind):
    root, _ = source_fixture
    document = load(root, prepare.ANNOTATIONS)
    records = document["images" if kind == "image" else "annotations"]
    records[1]["id"] = records[0]["id"]
    save(root, prepare.ANNOTATIONS, document)
    with pytest.raises(ValueError, match="duplicate ID"):
        build((root, repin(root)))


def test_unknown_author_category_cannot_become_background(source_fixture):
    root, _ = source_fixture
    document = load(root, prepare.ANNOTATIONS)
    document["annotations"][0]["category_id"] = 14
    save(root, prepare.ANNOTATIONS, document)
    with pytest.raises(ValueError, match="Unknown annotation category"):
        build((root, repin(root)))


def test_missing_original_even_when_excluded_fails_closed(source_fixture):
    root, _ = source_fixture
    (root / prepare.RAW / "images/screws_005.png").unlink()
    with pytest.raises(ValueError, match="Missing image"):
        build(source_fixture)


def test_source_image_bytes_must_match_provenance(source_fixture):
    root, _ = source_fixture
    path = root / prepare.RAW / "images/screws_001.png"
    path.write_bytes(path.read_bytes() + b"modified")
    with pytest.raises(ValueError, match="Image source hash mismatch"):
        build(source_fixture)


def test_reencoded_identical_pixels_cannot_cross_train_test(source_fixture):
    root, _ = source_fixture
    first = root / prepare.RAW / "images/screws_001.png"
    test_path = root / prepare.RAW / "images/screws_004.png"
    with Image.open(first) as image:
        image.save(test_path, compress_level=0)
    assert prepare.sha256(first.read_bytes()) != prepare.sha256(test_path.read_bytes())
    source = load(root, prepare.SOURCE)
    source["images"][3]["sha256"] = prepare.sha256(test_path.read_bytes())
    save(root, prepare.SOURCE, source)
    with pytest.raises(ValueError, match="Duplicate decoded pixels"):
        build((root, repin(root)))


def test_historical_exclusion_identity_cannot_silently_drift(source_fixture):
    root, _ = source_fixture
    document = load(root, prepare.EXCLUSION_FILES[1])
    document["views"][0]["source_sha256"] = "0" * 64
    save(root, prepare.EXCLUSION_FILES[1], document)
    with pytest.raises(ValueError, match="Protected source hash mismatch"):
        build((root, repin(root)))


def test_split_annotations_must_match_by_filename_not_local_id(source_fixture):
    root, _ = source_fixture
    path = f"{prepare.RAW}/mvtec_screws_test.json"
    document = load(root, path)
    document["annotations"][0]["bbox"][0] += 1
    save(root, path, document)
    with pytest.raises(ValueError, match="annotations mismatch by filename"):
        build((root, repin(root)))


def test_output_clipping_is_recorded_without_dropping_labels(source_fixture):
    root, _ = source_fixture
    document = load(root, prepare.ANNOTATIONS)
    document["annotations"][0]["bbox"] = [0, 1, 6, 4, 0]
    save(root, prepare.ANNOTATIONS, document)
    path = f"{prepare.RAW}/mvtec_screws_train.json"
    document = load(root, path)
    document["annotations"][0]["bbox"] = [0, 1, 6, 4, 0]
    save(root, path, document)
    artifacts = build((root, repin(root)))
    assert len(artifacts["train.json"]["annotations"]) == 2
    annotation = artifacts["train.json"]["annotations"][0]
    assert annotation["bbox"] == [0, 0, 4, 2] and annotation["area"] == 8
    assert annotation["bbox_clipped"]
    assert artifacts["manifest.json"]["splits"]["train"]["clipped_annotations"] == 1


def test_output_receipts_match_and_existing_output_is_preserved(source_fixture):
    root, _ = source_fixture
    artifacts = build(source_fixture)
    output = root / "prepared"
    manifest = prepare.write_artifacts(copy.deepcopy(artifacts), output)
    for receipt in manifest["split_files"]:
        assert prepare.sha256((output / receipt["path"]).read_bytes()) == receipt["sha256"]
    before = (output / "manifest.json").read_bytes()
    with pytest.raises(ValueError, match="Refuse to overwrite"):
        prepare.write_artifacts(artifacts, output)
    assert (output / "manifest.json").read_bytes() == before


def test_source_paths_cannot_escape_repository(tmp_path):
    with pytest.raises(ValueError, match="Unsafe source path"):
        prepare.safe_path(tmp_path, "../outside.png")
