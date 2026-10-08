"""Invented image/count fixtures verify protocol mechanics, never field accuracy."""

import json
from datetime import timedelta

import pytest
from PIL import Image

from scripts import prepare_detector_field_batch as batch_tool


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def make_image(path, color, compress_level=6):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (12, 8), color).save(path, compress_level=compress_level)


@pytest.fixture
def fixture(tmp_path):
    source = tmp_path / "datasets/raw/public.png"
    make_image(source, (1, 2, 3))
    manifest = tmp_path / "datasets/known.json"
    save(manifest, {"images": [{"path": "datasets/raw/public.png", "sha256": batch_tool.sha(source)}]})
    inventory = ({"name": "SYNTHETIC PUBLIC INVENTORY", "expected_images": 1, "kind": "images",
                  "path": "datasets/known.json", "sha256": batch_tool.sha(manifest)},)
    input_dir = tmp_path / "captures"
    for i in range(1, 5):
        make_image(input_dir / f"image-{i}.png", (i * 40, 80, 100))
    output = tmp_path / "batch"
    return tmp_path, input_dir, output, inventory


def prepare_fixture(fixture):
    root, input_dir, output, sources = fixture
    return batch_tool.prepare(input_dir, output, root=root, sources=sources)


def fill_manual(output, scope="bolt_nut"):
    for pass_name in ("a", "b"):
        path = output / f"annotation_{pass_name}.json"
        document = batch_tool.read(path)
        document.update({"annotator": f"SYNTHETIC FIXTURE PASS {pass_name}", "counted_without_model_predictions": True})
        for row in document["cases"]:
            row["status"] = "complete"
            row["counts"] = {"bolt": 1, "nut": 0, "washer": None, "bracket": None}
            if scope == "four_classes":
                row["counts"].update({"washer": 0, "bracket": 0})
        save(path, document)


def lock_fixture(fixture, scope="bolt_nut"):
    prepare_fixture(fixture)
    output = fixture[2]
    fill_manual(output, scope)
    locked = batch_tool.lock(output, scope, "Synthetic fixture only, not physical capture", "fixture-session")
    return batch_tool.read(output / "batch_manifest.json"), locked


def prediction(case, locked, *, count=1, threshold=0.5, checkpoint="a" * 64):
    return {"schema": "kitguard.public-detector.single-photo.v1", "status": "experimental_prediction",
            "source_sha256": case["source_sha256"],
            "created_at": (batch_tool.parse_time(locked["locked_at"]) + timedelta(seconds=1)).isoformat(),
            "image_size": case["dimensions"], "decision": None, "unsupported_classes": ["washer", "bracket"],
            "checkpoint_sha256": checkpoint, "threshold": threshold,
            "model": "fasterrcnn_mobilenet_v3_large_320_fpn",
            "coordinate_frame": "absolute pixel xyxy in EXIF-oriented RGB image; origin upper-left; x right, y down",
            "predictions": [{"label": 1, "bbox_xyxy": [i, 0, i + 1, 1], "score": 0.9} for i in range(count)],
            "counts": {"bolt": count, "nut": 0, "washer": None, "bracket": None}}


def test_prepare_creates_only_pending_unknown_counts_and_records_coverage(fixture):
    manifest = prepare_fixture(fixture)
    assert manifest["case_count"] == 4 and not manifest["physical_capture_verified"]
    assert manifest["public_source_overlap_screen"]["raw_hash_records"] == 1
    assert manifest["public_source_overlap_screen"]["normalized_pixel_records"] == 1
    assert manifest["public_source_overlap_screen"]["all_expected_sources_covered"]
    assert all(c["ground_truth"] == {"status": "pending", "counts": dict.fromkeys(batch_tool.PARTS)}
               for c in manifest["cases"])
    for pass_name in ("a", "b"):
        annotation = batch_tool.read(fixture[2] / f"annotation_{pass_name}.json")
        assert annotation["annotator"] is None and annotation["counted_without_model_predictions"] is None
    with pytest.raises(ValueError, match="Refuse to overwrite"):
        prepare_fixture(fixture)


@pytest.mark.parametrize("source_kind", ["within_batch", "public"])
def test_reencoded_pixel_duplicates_rejected(fixture, source_kind):
    root, input_dir, output, _ = fixture
    original = input_dir / "image-1.png" if source_kind == "within_batch" else root / "datasets/raw/public.png"
    with Image.open(original) as image:
        image.save(input_dir / "duplicate.png", compress_level=0)
    assert batch_tool.sha(original) != batch_tool.sha(input_dir / "duplicate.png")
    with pytest.raises(ValueError, match="Duplicate|Known public-source"):
        prepare_fixture(fixture)
    assert not output.exists()


def test_exif_normalized_pixel_hash_detects_orientation_equivalence(tmp_path):
    path = tmp_path / "oriented.png"
    image = Image.new("RGB", (12, 8), "red")
    exif = Image.Exif()
    exif[274] = 6
    image.save(path, exif=exif)
    rotated = tmp_path / "rotated.png"
    Image.new("RGB", (8, 12), "red").save(rotated)
    assert batch_tool.image_identity(path)["normalized_pixel_sha256"] == batch_tool.image_identity(rotated)["normalized_pixel_sha256"]


def test_public_demo_catalog_derived_crop_is_screened_without_executing_python(fixture):
    root, input_dir, output, sources = fixture
    derived = root / "datasets/derived/public-crop.png"
    make_image(derived, (210, 210, 210))
    catalog = root / "kitguard/public_demo_catalog.py"
    catalog.parent.mkdir()
    catalog.write_text("CATALOG = " + repr([{"image": "derived/public-crop.png", "source_sha256": batch_tool.sha(derived)}])
                       + "\nraise RuntimeError('must not execute')\n")
    with Image.open(derived) as image:
        image.save(input_dir / "not-a-new-photo.png", compress_level=0)
    extended = (*sources, {"name": "fixture catalog", "expected_images": 1, "kind": "python_catalog",
                          "path": "kitguard/public_demo_catalog.py", "sha256": batch_tool.sha(catalog)})
    with pytest.raises(ValueError, match="Known public-source"):
        batch_tool.prepare(input_dir, output, root=root, sources=extended)


def test_missing_known_pixels_report_partial_coverage(fixture):
    root, _, _, _ = fixture
    (root / "datasets/raw/public.png").unlink()
    manifest = prepare_fixture(fixture)
    coverage = manifest["public_source_overlap_screen"]
    assert not coverage["all_expected_sources_covered"]
    assert coverage["raw_hash_records"] == 1 and coverage["normalized_pixel_records"] == 0
    assert coverage["coverage"][0]["gaps"]


def test_empty_batch_is_rejected(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="Empty batch"):
        batch_tool.prepare(empty, tmp_path / "output", root=tmp_path, sources=())


def test_pending_or_disagreeing_manual_counts_cannot_lock(fixture):
    prepare_fixture(fixture)
    output = fixture[2]
    with pytest.raises(ValueError, match="annotator declaration"):
        batch_tool.lock(output, "bolt_nut", "fixture source", "session")
    fill_manual(output)
    path = output / "annotation_b.json"
    document = batch_tool.read(path)
    document["cases"][0]["counts"]["bolt"] = 2
    save(path, document)
    with pytest.raises(ValueError, match="disagree"):
        batch_tool.lock(output, "bolt_nut", "fixture source", "session")
    assert not (output / "locked_ground_truth.json").exists()


def test_lock_requires_scope_source_session_and_preserves_manual_declarations(fixture):
    prepare_fixture(fixture)
    output = fixture[2]
    fill_manual(output)
    with pytest.raises(ValueError, match="required"):
        batch_tool.lock(output, "bolt_nut", "", "session")
    locked = batch_tool.lock(output, "bolt_nut", "fixture source", "session")
    assert locked["declaration_status"] == "user_statement_not_independently_authenticated"
    assert not locked["physical_capture_verified"]
    assert (output / "locked_ground_truth.sha256").read_text().strip() == batch_tool.sha(output / "locked_ground_truth.json")
    with pytest.raises(ValueError, match="already locked"):
        batch_tool.lock(output, "bolt_nut", "new statement", "session")


@pytest.mark.parametrize("mutation", ["annotation", "image", "truth"])
def test_modification_after_lock_is_rejected(fixture, mutation):
    manifest, _ = lock_fixture(fixture)
    root, _, output, _ = fixture
    if mutation == "annotation":
        with (output / "annotation_a.json").open("a") as stream:
            stream.write(" ")
    elif mutation == "image":
        make_image(output / manifest["cases"][0]["image"], "blue")
    else:
        with (output / "locked_ground_truth.json").open("a") as stream:
            stream.write(" ")
    predictions = root / "predictions"
    predictions.mkdir()
    with pytest.raises(ValueError, match="changed|hash mismatch"):
        batch_tool.evaluate(output, predictions, root / "comparison")


def test_comparison_keeps_failures_and_missing_predictions_in_denominator(fixture):
    manifest, locked = lock_fixture(fixture)
    root, _, output, _ = fixture
    predictions = root / "predictions"
    save(predictions / "correct.json", prediction(manifest["cases"][0], locked))
    save(predictions / "incorrect.json", prediction(manifest["cases"][1], locked, count=2))
    save(predictions / "failed.json", {"source_sha256": manifest["cases"][2]["source_sha256"],
                                       "status": "failed", "error": "synthetic timeout"})
    result = batch_tool.evaluate(output, predictions, root / "comparison")
    assert (result["total_cases"], result["accurate"], result["inaccurate"], result["incomplete"]) == (4, 1, 1, 2)
    assert result["exact_count_rate_all_cases"] == 0.25
    assert result["exact_count_rate_completed_cases"] == 0.5
    assert len(result["cases"]) == 4 and not result["physical_capture_verified"]


@pytest.mark.parametrize("change", ["before_lock", "counts"])
def test_invalid_prediction_remains_incomplete_in_full_denominator(fixture, change):
    manifest, locked = lock_fixture(fixture)
    root, _, output, _ = fixture
    record = prediction(manifest["cases"][0], locked)
    if change == "before_lock":
        record["created_at"] = locked["locked_at"]
    else:
        record["counts"]["bolt"] = 3
    predictions = root / "predictions"
    save(predictions / "invalid.json", record)
    result = batch_tool.evaluate(output, predictions, root / "comparison")
    assert result["incomplete"] == 4 and result["accurate"] == 0


@pytest.mark.parametrize("change", ["checkpoint", "threshold", "duplicate", "foreign"])
def test_mixed_or_ambiguous_prediction_sets_are_rejected(fixture, change):
    manifest, locked = lock_fixture(fixture)
    root, _, output, _ = fixture
    first = prediction(manifest["cases"][0], locked)
    second = prediction(manifest["cases"][1], locked)
    if change == "checkpoint":
        second["checkpoint_sha256"] = "b" * 64
    elif change == "threshold":
        second["threshold"] = 0.6
    elif change == "duplicate":
        second = first
    else:
        second["source_sha256"] = "0" * 64
    predictions = root / "predictions"
    save(predictions / "first.json", first)
    save(predictions / "second.json", second)
    with pytest.raises(ValueError, match="Mixed|Duplicate|not a locked"):
        batch_tool.evaluate(output, predictions, root / "comparison")


def test_four_class_scope_cannot_claim_two_class_detector_success(fixture):
    manifest, locked = lock_fixture(fixture, "four_classes")
    root, _, output, _ = fixture
    predictions = root / "predictions"
    for index, case in enumerate(manifest["cases"]):
        save(predictions / f"{index}.json", prediction(case, locked))
    result = batch_tool.evaluate(output, predictions, root / "comparison")
    assert result["incomplete"] == 4 and result["completed"] == 0
    assert result["exact_count_rate_completed_cases"] is None
    assert all("four-class" in row["reason"] for row in result["cases"])
