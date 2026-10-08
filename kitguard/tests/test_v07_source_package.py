"""Archive safety/reproducibility fixtures; no real photographs or model evidence."""

import hashlib
import json
import os
from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.v07 import package_source as package


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    for name in package.REQUIRED | {"kitguard/__init__.py", "kitguard/static/icon.svg"}:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Synthetic fixture\n" if path.suffix in {".py", ".sh", ".command"} else "Synthetic fixture\n")
    (root / "kitguard/__init__.py").write_text('__version__ = "0.7.0.dev1"\n')
    (root / "pyproject.toml").write_text('[project]\nname = "synthetic-kitguard"\nversion = "0.7.0.dev1"\n')
    catalog, specs = [], []
    for index, sample_id in enumerate(sorted(package.DEMO_IDS)):
        image = f"{'derived' if index else 'raw'}/synthetic/{sample_id}.png"
        content = f"SYNTHETIC NOT A REAL PHOTO {index}".encode()
        path = root / "datasets" / image
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        catalog.append({"sample_id": sample_id, "image": image, "source_sha256": hashlib.sha256(content).hexdigest(),
                        "source_url": "https://www.mvtec.com/research-teaching/datasets/fixture",
                        "license": "MVTec · CC BY-NC-SA 4.0", "derived_view": bool(index),
                        "source_case_id": sample_id, "title": "Synthetic fixture"})
        specs.append({"id": sample_id, "source_image": "raw/synthetic-origin.png", "source_sha256": "a" * 64,
                      "crop_xyxy": [0, 0, 32, 32], "pixel_transform": "Synthetic crop metadata",
                      "annotation_sha256": "b" * 64})
    (root / "kitguard/public_demo_catalog.py").write_text("CATALOG = " + repr(catalog) + "\n")
    (root / package.CROP_SPECS).write_text(json.dumps({"views": specs}))
    return root


def test_identical_inputs_have_identical_zip_despite_mtime_permissions_and_output_name(source, tmp_path):
    one, two = tmp_path / "one.zip", tmp_path / "two.zip"
    first = package.build(source, one)
    for path in source.rglob("*"):
        if path.is_file():
            os.utime(path, (1_000_000_000, 1_000_000_000))
            path.chmod(0o600)
    second = package.build(source, two)
    assert first["sha256"] == second["sha256"]
    assert one.read_bytes() == two.read_bytes()
    assert Path(str(one) + ".manifest.json").read_bytes() == Path(str(two) + ".manifest.json").read_bytes()
    with ZipFile(one) as archive:
        manifest = json.loads(archive.read("KitGuard/SOURCE_MANIFEST.json"))
        for record in manifest["files"]:
            info = archive.getinfo("KitGuard/" + record["path"])
            assert info.date_time == package.FIXED_TIME
            assert (info.external_attr >> 16) & 0o777 == record["mode"]
        assert "KitGuard/scripts/v07/run_public_paired.py" in archive.namelist()
        assert "KitGuard/kitguard/static/public-review.js" in archive.namelist()
        assert len(manifest["public_demo_images"]) == 3


def test_only_allowlisted_dataset_images_and_source_text_are_included(source, tmp_path):
    omitted = ["data/kitguard.sqlite3", "data/photos/person.jpg", "data-preview/orders.json",
               "datasets/raw/extra-photo.png", "datasets/derived/v0.7/holdout/secret.png",
               "evaluation-runs/private-result.json", "test-results/browser/participant.json",
               "training-runs/model.pt", "third_party/model.safetensors", "scripts/__pycache__/cached.py",
               ".venv/pyvenv.cfg", "kitguard/private.sqlite3", "docs/personal-photo.png",
               "output/prior-source.zip"]
    for name in omitted:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("DO NOT PACKAGE")
    destination = tmp_path / "selected.zip"
    package.build(source, destination)
    with ZipFile(destination) as archive:
        names = set(archive.namelist())
        assert not names & {"KitGuard/" + name for name in omitted}
        images = [n for n in names if n.startswith("KitGuard/datasets/") and n.endswith(".png")]
        assert len(images) == 3
        assert "KitGuard/third_party/datasets/MVTec_LOCO_license.txt" in names


@pytest.mark.parametrize("suffix", ["", ".manifest.json", ".sha256", ".verification.json"])
def test_all_existing_output_artifacts_are_preserved(source, tmp_path, suffix):
    destination = tmp_path / "existing.zip"
    existing = Path(str(destination) + suffix)
    existing.write_bytes(b"PRESERVE EXISTING ARTIFACT")
    with pytest.raises(FileExistsError):
        package.build(source, destination, smoke=True)
    assert existing.read_bytes() == b"PRESERVE EXISTING ARTIFACT"
    assert set(tmp_path.glob("existing.zip*")) == {existing}


@pytest.mark.parametrize("change", ["pixels", "crop_provenance", "license", "catalog_count", "required", "version"])
def test_broken_source_or_demo_provenance_fails_before_output(source, tmp_path, change):
    samples = package.public_samples(source)
    if change == "pixels":
        (source / samples[0]["archive_path"]).write_bytes(b"altered")
    elif change == "crop_provenance":
        (source / package.CROP_SPECS).write_text('{"views": []}')
    elif change in {"license", "catalog_count"}:
        catalog = [{k: v for k, v in s.items() if k not in {"archive_path", "crop_provenance"}} for s in samples]
        if change == "license":
            catalog[0]["license"] = "Unreviewed terms"
        else:
            catalog.pop()
        (source / "kitguard/public_demo_catalog.py").write_text("CATALOG = " + repr(catalog))
    elif change == "required":
        (source / "kitguard/static/public-review.js").unlink()
    else:
        (source / "kitguard/__init__.py").write_text('__version__ = "0.6.0"')
    with pytest.raises(ValueError):
        package.build(source, tmp_path / "invalid.zip")
    assert not list(tmp_path.glob("invalid.zip*"))


def test_required_symlink_and_output_into_source_trees_are_rejected(source, tmp_path):
    outside = tmp_path / "outside.py"
    outside.write_text("SECRET")
    required = source / "kitguard/public_review.py"
    required.unlink()
    required.symlink_to(outside)
    with pytest.raises(ValueError, match="missing"):
        package.build(source, tmp_path / "bad-link.zip")
    required.unlink()
    required.write_text("# fixture\n")
    link = tmp_path / "linked-docs"
    link.symlink_to(source / "docs", target_is_directory=True)
    with pytest.raises(ValueError, match="outside included"):
        package.build(source, link / "bad-location.zip")


def test_failed_smoke_verification_rolls_back_only_owned_outputs(source, tmp_path, monkeypatch):
    destination = tmp_path / "failed.zip"
    untouched = tmp_path / "unrelated.zip"
    untouched.write_bytes(b"KEEP")

    def fail(_):
        raise RuntimeError("Synthetic smoke failure")

    monkeypatch.setattr(package, "verify_runtime", fail)
    with pytest.raises(RuntimeError, match="Synthetic"):
        package.build(source, destination, smoke=True)
    assert not list(tmp_path.glob("failed.zip*"))
    assert untouched.read_bytes() == b"KEEP"


def test_source_change_changes_payload_hash(source, tmp_path):
    first = package.build(source, tmp_path / "first.zip")
    (source / "kitguard/public_review.py").write_text("# modified synthetic source\n")
    second = package.build(source, tmp_path / "second.zip")
    assert first["sha256"] != second["sha256"]
    assert first["source_tree_sha256"] != second["source_tree_sha256"]


def test_missing_app_entrypoint_fails_before_archive_creation(source, tmp_path):
    (source / "kitguard/app.py").unlink()
    with pytest.raises(ValueError, match="kitguard/app.py"):
        package.build(source, tmp_path / "missing-app.zip")
    assert not list(tmp_path.glob("missing-app.zip*"))
