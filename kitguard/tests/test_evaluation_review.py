"""Independent metric/leakage regression tests; no real photographs or model claims."""

import json

import pytest

from kitguard.evaluation import read_manifest, score_case, summarize, validate_case, wilson_interval


def make_case(**changes):
    case = {
        "id": "engineering-case-1",
        "source_id": "original-1",
        "image": "image-1.png",
        "sha256": "a" * 64,
        "split": "development",
        "ground_truth": {"bolt": 2, "nut": 1, "washer": 0, "bracket": 0},
    }
    case.update(changes)
    return case


def make_observation():
    return {
        "observed": {"bolt": 2, "nut": 1, "washer": 0, "bracket": 0},
        "issues": [],
        "action": {"kind": "none", "message": "Synthetic metric fixture", "region": None},
        "backend": "test",
    }


def write_manifest(tmp_path, cases):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"schema_version": 1, "cases": cases}))
    return path


@pytest.mark.parametrize(
    "malformed",
    [
        {},
        {"observed": {"bolt": True}},
        {"observed": {"bolt": 2.5}},
        {**make_observation(), "action": {"kind": "ready"}},
        {**make_observation(), "issues": "not a list"},
    ],
)
def test_malformed_predictions_are_failed_rows_not_batch_aborts(malformed):
    failed = score_case(make_case(), malformed, 250)
    good = score_case(make_case(id="case-2", source_id="original-2", sha256="b" * 64), make_observation(), 500)
    summary = summarize([failed, good])
    assert failed["error"].startswith("InvalidObservation:")
    assert all(task["decision"] == "error" for task in failed["tasks"])
    assert summary["errors"]["numerator"] == 1
    assert summary["count_exact"]["denominator"] == 2
    assert summary["count_exact"]["rate"] == 0.5
    assert summary["matched_order_ready"]["denominator"] == 2


def test_absent_prediction_without_exception_is_still_recorded_as_error():
    row = score_case(make_case(), None, 250)
    assert row["error"].startswith("MissingObservation:")
    assert summarize([row])["errors"]["rate"] == 1


def test_explicit_failure_cannot_be_overridden_by_partial_prediction():
    row = score_case(make_case(), make_observation(), 250, "timeout after partial result")
    assert row["counts_exact"] is False
    assert row["actionable_counts"] is False
    assert all(task["decision"] == "error" for task in row["tasks"])


def test_out_of_scope_stress_image_has_no_order_success_denominator():
    truth = {"bolt": 8, "nut": 2, "washer": 0, "bracket": 0}
    observation = make_observation()
    observation["observed"] = truth
    row = score_case(make_case(ground_truth=truth), observation, 1000)
    summary = summarize([row])
    assert row["counts_exact"] is True
    assert row["in_product_scope"] is False
    assert summary["order_eligible_images"] == 0
    assert summary["order_out_of_scope_images"] == 1
    assert summary["matched_order_ready"]["denominator"] == 0
    assert summary["matched_order_ready"]["rate"] is None
    assert summary["mismatched_order_false_ready"]["rate"] is None


@pytest.mark.parametrize("identity", ["hash", "path", "source"])
def test_manifest_rejects_each_cross_split_leakage_identity(tmp_path, identity):
    first = make_case()
    second = make_case(id="case-2", image="image-2.png", source_id="original-2", sha256="b" * 64, split="holdout")
    if identity == "hash":
        second["sha256"] = first["sha256"].upper()
    elif identity == "path":
        second["image"] = "./" + first["image"]
    else:
        second["source_id"] = first["source_id"]
    with pytest.raises(ValueError, match="leaks"):
        read_manifest(write_manifest(tmp_path, [first, second]))


@pytest.mark.parametrize("identity", ["hash", "path"])
def test_same_split_duplicate_photo_cannot_inflate_sample_count(tmp_path, identity):
    first = make_case()
    second = make_case(id="case-2", image="image-2.png", source_id="original-2", sha256="b" * 64)
    second["sha256" if identity == "hash" else "image"] = first["sha256" if identity == "hash" else "image"]
    with pytest.raises(ValueError, match="inflate"):
        read_manifest(write_manifest(tmp_path, [first, second]))


def test_related_distinct_crops_stay_grouped_but_not_independent(tmp_path):
    first = make_case(split="holdout")
    second = make_case(id="crop-2", image="crop-2.png", sha256="b" * 64, split="holdout")
    manifest = read_manifest(write_manifest(tmp_path, [first, second]))
    rows = [score_case(case, make_observation(), 1000) for case in manifest["cases"]]
    summary = summarize(rows, independent_sample=True)
    assert summary["unique_image_hashes"] == 2
    assert summary["unique_source_images"] == 1
    assert summary["count_exact"]["wilson_95"] is None


@pytest.mark.parametrize("split", ["development", "holdout"])
def test_interval_is_not_automatically_claimed_for_convenience_benchmark(split):
    row = score_case(make_case(split=split), make_observation(), 1000)
    assert summarize([row])["count_exact"]["wilson_95"] is None
    explicit = summarize([row], independent_sample=True)
    assert (explicit["count_exact"]["wilson_95"] is not None) == (split == "holdout")


def test_manifest_duplicate_json_key_is_not_silently_overwritten(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text('{"schema_version":1,"cases":[],"cases":[]}')
    with pytest.raises(ValueError, match="Duplicate manifest JSON key"):
        read_manifest(path)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_manifest_metadata_is_rejected(tmp_path, value):
    path = tmp_path / "manifest.json"
    path.write_text('{"schema_version":1,"cases":[],"sampling":' + value + '}')
    with pytest.raises(ValueError, match="Non-finite"):
        read_manifest(path)


@pytest.mark.parametrize(
    "changes",
    [
        {"id": ""},
        {"source_id": "   "},
        {"image": "../outside.png"},
        {"image": "/tmp/outside.png"},
        {"sha256": "not a digest"},
        {"split": []},
        {"ground_truth": None},
        {"ground_truth": {"bolt": True, "nut": 1, "washer": 0, "bracket": 0}},
    ],
)
def test_invalid_case_metadata_is_rejected_before_inference(tmp_path, changes):
    with pytest.raises(ValueError):
        read_manifest(write_manifest(tmp_path, [make_case(**changes)]))


def test_validate_case_rejects_symlink_escape_even_with_matching_hash(tmp_path):
    import hashlib

    root = tmp_path / "dataset"
    root.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"synthetic filesystem fixture; not an image evaluation")
    (root / "image-1.png").symlink_to(outside)
    item = make_case(sha256=hashlib.sha256(outside.read_bytes()).hexdigest())
    with pytest.raises(ValueError, match="inside"):
        validate_case(item, root)


@pytest.mark.parametrize("successes,count", [(1, 0), (-1, 10), (11, 10), (True, 10), (1, -1)])
def test_wilson_rejects_invalid_denominators(successes, count):
    with pytest.raises(ValueError):
        wilson_interval(successes, count)
