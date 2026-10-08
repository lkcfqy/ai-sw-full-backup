"""Pure synthetic contracts; no Torch, inference, training, or held-back data loads."""
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.v08 import train_grouped_detector as m


def record(label=3, source="foda", group="w", key="a"):
    return {"id": key, "source": source, "group_id": group, "image_size": [100, 100],
            "ground_truth": [{"label": label, "box": [10, 10, 20, 20], "annotation_id": key}]}


def prediction(label=3, score=.5, box=None):
    return {"label": label, "score": score, "box": box or [10, 10, 20, 20]}


def test_fixed_protocol_has_three_targets_and_unsupported_bracket():
    assert m.CLASSES == {1: "bolt", 2: "nut", 3: "washer"}
    assert m.CONFIG["head_outputs"] == 4 and m.CONFIG["unsupported_classes"] == ["bracket"]
    assert (m.CONFIG["epochs"], m.CONFIG["seed"], m.CONFIG["batch_size"]) == (12, 20261002, 2)
    assert (m.CONFIG["min_size"], m.CONFIG["max_size"], m.CONFIG["device"]) == (640, 960, "mps")
    assert m.CONFIG["thresholds"] == [.1, .2, .3, .4, .5, .6, .7, .8, .9]


def test_import_is_stdlib_only():
    result = subprocess.run([sys.executable, "-I", "-c",
                             ("import runpy,sys; runpy.run_path(sys.argv[1]); "
                             "assert not any(x in sys.modules for x in ['torch','torchvision','PIL','kitguard'])"),
                             str(Path(m.__file__).resolve())], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_threshold_inclusive_and_washer_count_does_not_invent_bracket():
    scored = m.score_case(record(), [prediction()], .5)
    assert scored["exact_count"] and scored["per_class"]["washer"]["tp"] == 1
    assert "bracket" not in scored["truth_count"]
    assert not m.score_case(record(), [prediction()], .50001)["exact_count"]


def test_wrong_class_is_fp_and_fn_with_original_indices():
    scored = m.score_case(record(3), [prediction(2)], .5)
    assert scored["per_class"]["nut"]["fp"] == 1
    assert scored["per_class"]["washer"]["fn"] == 1
    assert scored["false_positive_indices"] == [0] and scored["missed_ground_truth_indices"] == [0]
    assert scored["count_error"] == {"bolt": 0, "nut": 1, "washer": -1}


def test_duplicate_box_is_not_double_matched():
    scored = m.score_case(record(), [prediction(score=.6), prediction(score=.7)], .5)
    assert scored["matches"][0]["prediction_index"] == 1
    assert scored["false_positive_indices"] == [0]
    assert scored["count_error"]["washer"] == 1


def test_equal_count_does_not_conflate_localization():
    scored = m.score_case(record(), [prediction(box=[80, 80, 90, 90])], .5)
    assert scored["exact_count"]
    assert scored["per_class"]["washer"]["tp"] == 0
    assert scored["per_class"]["washer"]["fp"] == scored["per_class"]["washer"]["fn"] == 1


@pytest.mark.parametrize("bad", [prediction(4), prediction(score=float("nan")), prediction(score=1.1),
                                  prediction(box=[1, 1, 101, 5]), prediction(box=[1, 1, 1, 5])])
def test_invalid_raw_prediction_is_not_accepted(bad):
    with pytest.raises(ValueError):
        m.score_case(record(), [bad], .5)


def test_balance_is_source_group_macro_not_pooled_frames():
    records = [record(source="screws", group="s", key="s")]
    records += [record(group="many", key=str(i)) for i in range(9)] + [record(group="one", key="one")]
    raw = [{"id": r["id"], "status": "ok", "predictions": [] if r["group_id"] == "many" else [prediction()]}
           for r in records]
    result = m.evaluate(records, raw, .5)
    assert result["balanced_exact_count_accuracy"] == .75  # .5*(1 + mean(0,1))
    assert result["foda"]["exact_count_accuracy"] == .1
    assert result["balanced_class_count_mae"] == pytest.approx(1 / 12)
    assert len(result["cases"]) == 11


@pytest.mark.parametrize("mutation", ["missing", "failed", "reordered"])
def test_full_validation_denominator_required(mutation):
    records = [record(source="screws", key="s"), record(key="f")]
    raw = [{"id": r["id"], "status": "ok", "predictions": [prediction()]} for r in records]
    if mutation == "missing":
        raw.pop()
    elif mutation == "failed":
        raw[1]["status"] = "failed"
    else:
        raw.reverse()
    with pytest.raises(ValueError):
        m.evaluate(records, raw, .5)


def metric(threshold=.5, accuracy=.7, mae=.2, f1=.5):
    return {"threshold": threshold, "balanced_exact_count_accuracy": accuracy,
            "balanced_class_count_mae": mae, "pooled": {"box_f1": f1}}


def test_rank_tie_breaks_lower_mae_then_box_f1_then_high_threshold():
    rows = [metric(.9, mae=.3), metric(.1), metric(.4), metric(.8, f1=.4)]
    assert m.select_threshold(rows)["threshold"] == .4
    assert m.select_threshold([metric(.1, accuracy=.8, mae=5), metric(.9)])["threshold"] == .1


def test_equal_rank_preserves_earlier_epoch_even_with_higher_threshold():
    best = {"rank": m.rank(metric(.1)), "epoch": 1}
    assert not m.update_best(best, metric(.9), 2)
    assert m.update_best(best, metric(.1, accuracy=.8), 2)
    assert m.update_best(None, metric(), 1)


def review():
    return {"schema": "kitguard.v08.foda-training-review.v1", "status": "approved_for_local_training",
            "annotation_scope": "author_annotated_target_only", "held_back_human_or_rendered": False,
            "all_frame_completeness_certified": False, "reviewed_preview_ids": list("abcdef"),
            "train_sha256": "train", "validation_sha256": "val", "preview_sha256": "preview",
            "notes": "Partial author targets allowed; six previews only."}


def test_review_is_bound_to_exact_train_val_and_preview():
    hashes = {"train.json": "train", "validation.json": "val", "development_preview.jpg": "preview"}
    protocol = {"preview_ids": list("abcdef")}
    m.validate_review(review(), protocol, hashes)
    bad = review()
    bad["train_sha256"] = "different"
    with pytest.raises(ValueError, match="binding"):
        m.validate_review(bad, protocol, hashes)


@pytest.mark.parametrize("field,value", [("held_back_human_or_rendered", True),
                                         ("all_frame_completeness_certified", True),
                                         ("annotation_scope", "full_scene_count"),
                                         ("status", "pending"), ("reviewed_preview_ids", ["a"])])
def test_review_gate_rejects_overclaims_or_incomplete_approval(field, value):
    bad = review()
    bad[field] = value
    with pytest.raises(ValueError):
        m.validate_review(bad, {"preview_ids": list("abcdef")},
                          {"train.json": "train", "validation.json": "val", "development_preview.jpg": "preview"})


@pytest.mark.parametrize("path", ["../outside", "/tmp/absolute", "datasets/held_back/image.jpg", "held_back.json"])
def test_forbidden_dataset_paths(tmp_path, path):
    with pytest.raises(ValueError):
        m.safe_local(tmp_path, path)


def test_foda_split_and_author_label_are_not_guessed():
    row = {"image_id": "1", "class_id": 3, "author_category": "Washer", "group_id": "g",
           "protocol_role": "train", "image_size": [300, 300], "box_xyxy": [1, 1, 2, 2],
           "local_image": "datasets/images/train/1.jpg", "image_sha256": "x", "rgb_sha256": "y",
           "annotation_member_path": "1.xml"}
    assert m.foda_records([row], "train", {"group_roles": {"g": "train"}})[0]["ground_truth"][0]["label"] == 3
    with pytest.raises(ValueError, match="leakage"):
        m.foda_records([row], "train", {"group_roles": {"g": "held_back"}})
    row["author_category"] = "Nut"
    with pytest.raises(ValueError, match="mapping"):
        m.foda_records([row], "train", {"group_roles": {"g": "train"}})


@pytest.mark.parametrize("kind", ["id", "group_id", "source_sha256"])
def test_partition_checks_ids_groups_and_bytes(kind):
    a = {"id": "a", "group_id": "a", "source": "foda", "source_sha256": "a"}
    b = {"id": "b", "group_id": "b", "source": "foda", "source_sha256": "b"}
    m.check_partition([a], [b])
    b[kind] = a[kind]
    with pytest.raises(ValueError):
        m.check_partition([a], [b])


def test_full_preflight_never_opens_held_back_manifest_or_original_test(tmp_path, monkeypatch):
    """A 614/80 synthetic metadata contract; file reads trap disallowed targets."""
    root = tmp_path
    sd = root / "datasets/derived/public_detector_v1"
    fd = root / "datasets/derived/v0.8/foda_grouped_v1"
    fd.mkdir(parents=True)
    (root / m.PLAN).parent.mkdir(parents=True)
    (root / m.PLAN).write_text("synthetic fixed plan")
    excluded = [{"original_filename": f"excluded{i}"} for i in range(104)]
    m.dump(sd / "manifest.json", {"excluded_originals": excluded, "excluded_original_count": 104})
    for split, n in (("train", 214), ("val", 44)):
        images = []
        for i in range(n):
            filename = f"screws/{split}/{i}.bin"
            file = root / filename
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(filename.encode())
            images.append({"id": f"{split}{i}", "original_filename": f"{split}{i}", "width": 100,
                           "height": 100, "file_name": filename, "source_sha256": m.sha(file)})
        m.dump(sd / f"{split}.json", {"categories": [{"id": 1, "name": "bolt"}, {"id": 2, "name": "nut"}],
                                     "images": images, "annotations": []})
    monkeypatch.setattr(m, "SCREWS_HASHES", {name: m.sha(sd / name) for name in m.SCREWS_HASHES})
    coco = root / "cache.bin"
    coco.write_bytes(b"syntheticcache")
    monkeypatch.setattr(m, "COCO_SHA", m.sha(coco))
    old = root / m.V1_PROTOCOL
    m.dump(old, {"pretrained_sha256": m.sha(coco), "trainable_parameters": ["x"]})
    monkeypatch.setattr(m, "V1_PROTOCOL_SHA", m.sha(old))
    (fd / "prepare_foda_grouped_development.py").write_text("# synthetic snapshot")
    (fd / "development_preview.jpg").write_bytes(b"not decoded by preflight")
    groups = {f"t{i}": "train" for i in range(8)} | {f"v{i}": "validation" for i in range(3)}
    groups["unopened"] = "held_back"
    for role, n in (("train", 400), ("validation", 36)):
        rows = []
        for i in range(n):
            gid = f"t{i // 50}" if role == "train" else f"v{i // 12}"
            label = (i // 12) + 1 if role == "validation" else (i % 3) + 1
            local = f"datasets/derived/v0.8/foda_grouped_v1/images/{role}/{i}.jpg"
            file = root / local
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(local.encode())
            rows.append({"image_id": f"{role}{i}", "class_id": label, "author_category": m.CLASSES[label].title(),
                         "group_id": gid, "protocol_role": role, "image_size": [300, 300],
                         "box_xyxy": [1, 1, 2, 2], "local_image": local, "image_sha256": m.sha(file),
                         "rgb_sha256": "unused_by_metadata_preflight", "annotation_member_path": f"{i}.xml"})
        m.dump(fd / f"{role}.json", rows)
    protocol = {"schema": "kitguard.v08.foda-grouped-development.v1", "independent_physical_objects": False,
                "preview_ids": [f"train{i}" for i in range(6)], "group_roles": groups,
                "script_sha256": m.sha(fd / "prepare_foda_grouped_development.py")}
    m.dump(fd / "protocol.json", protocol)
    m.dump(fd / "duplicate_audit.json", {"cross_source_group_conflicts": []})
    files = {name: m.sha(fd / name) for name in ("protocol.json", "duplicate_audit.json", "train.json",
                                               "validation.json", "development_preview.jpg")}
    files["held_back.json"] = "intentionally does not exist and must not be opened"
    m.dump(fd / "summary.json", {"files": files})
    rev = review() | {"reviewed_preview_ids": protocol["preview_ids"], "train_sha256": files["train.json"],
                      "validation_sha256": files["validation.json"], "preview_sha256": files["development_preview.jpg"]}
    m.dump(fd / "manual_review.json", rev)
    original_open = Path.open

    def guarded_open(path, *args, **kwargs):
        assert "held_back" not in path.name and path.name != "test.json", f"Forbidden read {path}"
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", guarded_open)
    receipt = m.preflight(root, fd, fd / "manual_review.json", coco)
    assert len(receipt["training"]) == 614 and len(receipt["validation"]) == 80
    assert receipt["held_back_read_by_trainer"] is False
    assert all("held_back" not in p for p in receipt["bindings"])
    # Metadata changes after preflight invalidate the immutable binding, before any model call.
    (fd / "train.json").write_text("[]")
    with pytest.raises(ValueError, match="changed"):
        m.assert_bindings(receipt["bindings"])


def test_held_back_symlink_cannot_hide_as_training_path(tmp_path):
    secret = tmp_path / "held_back" / "a.jpg"
    secret.parent.mkdir()
    secret.write_bytes(b"must not be read")
    (tmp_path / "training.jpg").symlink_to(secret)
    with pytest.raises(ValueError, match="held-back"):
        m.safe_local(tmp_path, "training.jpg")
