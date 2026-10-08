"""Synthetic packages and isolated HTTP only; no final archive, model or new pixels."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.v08 import package_source as P


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "synthetic-source"
    for name in P.REQUIRED:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("" if path.suffix in {".py", ".js", ".cjs"} else "SYNTHETIC\n")
    (root / "pyproject.toml").write_text('[project]\nversion="0.8.0.dev1"\n')
    (root / "kitguard/__init__.py").write_text('__version__="0.8.0.dev1"\n')
    (root / P.old.CROP_SPECS).write_text('{"views": []}\n')
    rows = []
    for index, identifier in enumerate(sorted(P.old.DEMO_IDS)):
        # Package byte contracts do not decode; these are explicitly synthetic fixtures.
        path = root / f"datasets/synthetic/{identifier}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"SYNTHETIC DEMO BYTES {index}".encode())
        rows.append({"sample_id":identifier,"image":f"synthetic/{identifier}.png",
                     "source_sha256":P.sha_file(path),"license":"MVTec · CC BY-NC-SA 4.0",
                     "source_url":"https://www.mvtec.com/synthetic-contract", "derived_view":False})
    (root / "kitguard/public_demo_catalog.py").write_text("CATALOG = " + repr(rows) + "\n")
    return root


def test_preview_exact_members_reproducibility_and_no_overwrite(source, tmp_path):
    with pytest.raises(ValueError, match="--preview"):
        P.build(source, tmp_path / "without-preview.zip")
    first, second = tmp_path / "a.zip", tmp_path / "b.zip"
    result = P.build(source, first, preview=True)
    P.build(source, second, preview=True)
    assert result["preview"] is True and not result["smoke_verified"]
    assert first.read_bytes() == second.read_bytes()
    with ZipFile(first) as z:
        names = z.namelist()
        assert "KitGuard/kitguard/static/photo-documents.js" in names
        assert "KitGuard/kitguard/photo_documents.py" in names
        assert "KitGuard/docs/v0.8/PHOTO_DOCUMENT_GUIDE_KO_ZH.md" in names
        manifest = json.loads(z.read("KitGuard/SOURCE_MANIFEST.json"))
        assert manifest["schema"] == "kitguard.v08.source-package.v1"
        assert manifest["preview"] is True and len(manifest["public_samples"]) == 3
        assert "DEVELOPMENT PREVIEW" in z.read("KitGuard/SOURCE_PACKAGE.md").decode()
        for item in manifest["files"]:
            raw = z.read("KitGuard/"+item["path"])
            assert len(raw) == item["bytes"] and hashlib.sha256(raw).hexdigest() == item["sha256"]
    before = first.read_bytes()
    with pytest.raises(FileExistsError):
        P.build(source, first, preview=True)
    assert first.read_bytes() == before
    other = tmp_path / "sidecar.zip"
    Path(str(other)+".verification.json").write_text("prior attempt")
    with pytest.raises(FileExistsError):
        P.build(source, other, preview=True)
    assert not other.exists()


@pytest.mark.parametrize("name", ["kitguard/static/photo-documents.js", "kitguard/photo_documents.py",
                                  "docs/v0.8/PHOTO_DOCUMENT_GUIDE_KO_ZH.md"])
def test_missing_new_required_file_rejected(source, name):
    (source / name).unlink()
    with pytest.raises(ValueError, match="Required v0.8"):
        P.collect(source)


def test_explicit_external_index_private_data_and_unknown_large_file(source, tmp_path, monkeypatch):
    paths = {
        "datasets/manifests/v0.8/fod-a-v2.1/annotation_metadata.jsonl": b"optional research"*100,
        "docs/v0.8/synthetic_freeze/source_snapshot/kitguard/vision.py": b"# frozen source\n",
        "docs/v0.8/synthetic_freeze/freeze.json": b'{"synthetic":true}',
        "docs/v0.8/synthetic_freeze/normalized_inputs/never-read.png": b"DO NOT READ NEW PHOTOS",
        "docs/v0.8/synthetic_freeze.runtime-app-data/kitguard.sqlite3": b"PRIVATE",
        "docs/credentials.json": b"PRIVATE", "kitguard/.env": b"PRIVATE",
        "data/uploads/private.png": b"PRIVATE", "evaluation-runs/private.json": b"PRIVATE",
    }
    for name, raw in paths.items():
        path = source / name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(raw)
    original = P.sha_file
    def reject_private_or_pixels(path):
        if path.name == "never-read.png" or "runtime-app-data" in str(path) or P.private_file(path):
            raise AssertionError("Private/image bytes must not be hashed")
        return original(path)
    monkeypatch.setattr(P, "sha_file", reject_private_or_pixels)
    selected, _, index = P.collect(source)
    assert all(n not in selected for n in paths if not n.endswith("freeze.json"))
    indexed={r["path"]:r for r in index["external_files"]}
    for name in list(paths)[:2]:
        assert indexed[name]["bytes"] == len(paths[name])
        assert indexed[name]["sha256"] == hashlib.sha256(paths[name]).hexdigest()
    image_tree=next(r for r in index["external_trees"] if r["path"].endswith("normalized_inputs"))
    assert image_tree["binding"]["sha256"] == hashlib.sha256(paths[list(paths)[2]]).hexdigest()
    assert not any("PRIVATE" in json.dumps(r) for r in index["external_files"])
    monkeypatch.setattr(P,"MAX_FILE_BYTES",1024)
    large=source / "docs/unregistered-large.json";large.write_bytes(b"x"*1025)
    with pytest.raises(ValueError,match="Unknown oversized.*unregistered-large"):
        P.build(source,tmp_path/"large.zip",preview=True)
    assert not (tmp_path/"large.zip").exists()


@pytest.mark.parametrize("mutation", ["version", "mismatch", "demo_bytes", "license", "fourth_demo", "traversal", "symlink"])
def test_version_source_and_catalog_fail_closed(source, tmp_path, mutation):
    catalog=source/"kitguard/public_demo_catalog.py"
    rows=P.old.ast.literal_eval(P.old.ast.parse(catalog.read_text()).body[0].value)
    if mutation=="version":
        (source/"pyproject.toml").write_text('[project]\nversion="0.7.0"\n')
        (source/"kitguard/__init__.py").write_text('__version__="0.7.0"\n')
    elif mutation=="mismatch":
        (source/"kitguard/__init__.py").write_text('__version__="0.8.0.dev2"\n')
    elif mutation=="demo_bytes":
        (source/"datasets"/rows[0]["image"]).write_bytes(b"changed")
    elif mutation=="symlink":
        target=tmp_path/"outside.js";target.write_text("secret")
        path=source/"kitguard/static/photo-documents.js";path.unlink();path.symlink_to(target)
    else:
        if mutation=="license":rows[0]["license"]="Unverified claim"
        if mutation=="fourth_demo":rows.append({**rows[0],"sample_id":"unexpected"})
        if mutation=="traversal":rows[0]["image"]="../../outside.png"
        catalog.write_text("CATALOG = "+repr(rows)+"\n")
    with pytest.raises(ValueError):
        P.build(source,tmp_path/(mutation+".zip"),preview=True)


def test_current_source_inventory_includes_entry_without_reading_eval_images():
    selected, samples, index = P.collect(P.ROOT)
    assert P.REQUIRED <= selected.keys()
    assert len(samples)==3
    assert all("source_snapshot" not in Path(n).parts and "normalized_inputs" not in Path(n).parts
               and ".runtime-app-data/" not in n for n in selected)
    assert all(not n.startswith(tuple(P.EXTERNAL_PREFIXES)) for n in selected)
    assert all(p.stat().st_size <= P.MAX_FILE_BYTES for p in selected.values())
    assert sum(p.stat().st_size for p in selected.values()) < P.MAX_TOTAL_BYTES
    assert index["full_experiment_reproduction_self_contained"] is False


def test_real_current_http_smoke_uses_isolated_data_and_zero_model(tmp_path):
    # Exercises the exact extracted-package probe against current source, no release ZIP generated.
    result=P.runtime_probe(P.ROOT,tmp_path/"isolated-runtime")
    assert result["status"]=="passed"
    actual=result["runtime"]
    assert actual["model_calls"]==actual["human_participants"]==0 and not actual["mlx_imported"]
    assert actual["multipart_create"]==201 and actual["root_replace"]==actual["physical_complete"]==409
    assert actual["zip_manifest_verified"] and actual["unverified_source_preserved"]
