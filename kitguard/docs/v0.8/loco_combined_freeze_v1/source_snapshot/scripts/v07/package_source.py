"""Build a reproducible source ZIP plus exactly three licensed public demo images.

No inference, model download, live database, experiment output, or holdout photos.
An explicit unused output path is required; existing artifacts are never replaced.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[2]
TEXT_SUFFIXES = {".py", ".js", ".jsx", ".cjs", ".mjs", ".html", ".css", ".svg", ".md",
                 ".json", ".jsonl", ".toml", ".bib", ".txt", ".sh", ".sha256"}
STATIC_SUFFIXES = TEXT_SUFFIXES | {".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".woff", ".woff2"}
SOURCE_TREES = ("kitguard", "scripts", "tests", "docs", "third_party", "datasets/manifests")
OMIT_PARTS = {"__pycache__", "node_modules", ".venv", ".pytest_cache", ".ruff_cache", ".git", ".DS_Store"}
DEMO_IDS = {"bag-revision", "small-part", "mixed-screws"}
CROP_SPECS = "datasets/manifests/v0.3/source_grouped_v2/screws_new_development_crop_specs_v1.json"
TOP_FILES = ("README.md", "pyproject.toml", "requirements-lock.txt", "启动KitGuard.command", ".gitignore")
REQUIRED = {
    *TOP_FILES, "kitguard/public_review.py", "kitguard/public_demo_catalog.py", "kitguard/store.py",
    "kitguard/static/public-review.js", "kitguard/static/public-review.css", "kitguard/static/demo.html",
    "kitguard/static/demo.js", "kitguard/static/demo.css", "scripts/setup.sh", "scripts/run.sh",
    "scripts/download_candidate_model.py", "scripts/run_benchmark.py", "scripts/probe_selective_identity.py",
    "scripts/v07/package_source.py", "scripts/v07/prepare_public_evaluation.py", "scripts/v07/run_public_paired.py",
    "scripts/v07/analyze_public_paired.py", "docs/v0.7/PUBLIC_REVIEW_API.md", "docs/v0.7/PUBLIC_EVALUATION_PLAN.md",
    "third_party/datasets/MVTec_LOCO_license.txt", "third_party/datasets/MVTec_Screws_README_v1.0.txt", CROP_SPECS,
}
FIXED_TIME = (1980, 1, 1, 0, 0, 0)
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 100 * 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def regular_file(root, relative):
    path = root / relative
    if (not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root)
            or any(parent.is_symlink() for parent in path.parents if parent != root and root in parent.parents)):
        raise ValueError(f"Missing or unsafe regular source file: {relative}")
    return path


def public_samples(root):
    tree = ast.parse(regular_file(root, "kitguard/public_demo_catalog.py").read_text())
    catalog = next((ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                    and any(isinstance(name, ast.Name) and name.id == "CATALOG" for name in node.targets)), None)
    if not isinstance(catalog, list) or {row.get("sample_id") for row in catalog} != DEMO_IDS or len(catalog) != 3:
        raise ValueError("Review the explicit three-image package allowlist before changing the demo catalog")
    specs = json.loads(regular_file(root, CROP_SPECS).read_text())["views"]
    samples = []
    for row in catalog:
        relative = PurePosixPath("datasets") / row["image"]
        if ".." in relative.parts or relative.is_absolute() or "\\" in str(relative):
            raise ValueError("Unsafe public image path")
        path = regular_file(root, str(relative))
        if sha(path.read_bytes()) != row["source_sha256"]:
            raise ValueError(f"Public image does not match its catalog SHA-256: {relative}")
        if row["license"] != "MVTec · CC BY-NC-SA 4.0" or not row["source_url"].startswith("https://www.mvtec.com/"):
            raise ValueError("Review public-image license/source changes before redistributing")
        sample = {**row, "archive_path": str(relative)}
        if row["derived_view"]:
            spec = next((spec for spec in specs if spec["id"] == row["source_case_id"]), None)
            if spec is None:
                raise ValueError(f"Missing crop provenance: {row['source_case_id']}")
            sample["crop_provenance"] = {key: spec[key] for key in (
                "source_image", "source_sha256", "crop_xyxy", "pixel_transform", "annotation_sha256")}
            sample["crop_provenance"]["spec_file"] = CROP_SPECS
        samples.append(sample)
    return samples


def collect(root):
    root = root.resolve()
    selected = {name: regular_file(root, name) for name in TOP_FILES}
    optional = root / "启动检测验证台.command"
    if optional.is_file():
        selected[optional.name] = regular_file(root, optional.name)
    for directory in SOURCE_TREES:
        for parent, dirs, files in os.walk(root / directory, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in OMIT_PARTS and not (Path(parent) / d).is_symlink())
            for name in sorted(files):
                path = Path(parent) / name
                relative = path.relative_to(root).as_posix()
                suffixes = STATIC_SUFFIXES if relative.startswith("kitguard/static/") else TEXT_SUFFIXES
                if (name in OMIT_PARTS or path.is_symlink() or any(part in OMIT_PARTS for part in path.parts)
                        or (path.suffix not in suffixes and name not in {"LICENSE", "NOTICE"})):
                    continue
                selected[relative] = regular_file(root, relative)
    missing = REQUIRED - selected.keys()
    if missing:
        raise ValueError(f"Required v0.7 source files are missing: {', '.join(sorted(missing))}")
    samples = public_samples(root)
    for sample in samples:
        selected[sample["archive_path"]] = regular_file(root, sample["archive_path"])
    return dict(sorted(selected.items())), samples


def package_note(version, samples):
    rows = "\n".join(f"| {s['sample_id']} | {s['archive_path']} | {s['source_url']} |" for s in samples)
    return f"""# KitGuard {version} · source snapshot / 소스 스냅샷 / 源码快照

This development snapshot includes application code, static UI, tests, scripts,
authored text documentation, public dataset manifests, third-party notices, and
exactly three licensed development photographs. It is not a final contest delivery.
Use this file for package contents; the main README retains earlier version history.

## Run the public-photo workflow on Apple Silicon macOS

```sh
bash scripts/setup.sh
.venv/bin/python scripts/download_candidate_model.py
bash scripts/run.sh
```

Setup requires `uv` and downloads the pinned Python dependencies. The model download
is separate and uses the pinned upstream model revision and file hashes. If the
verified model is already installed, set KITGUARD_MODEL_PATH to its directory and
skip downloading. No model weights or Python environment are in this ZIP.

Open http://127.0.0.1:8765/static/demo.html. All three image previews are included.
Selecting a photo creates a source-tagged order with no cached observation. Run the
real local model, record a human digital opinion, revise the order and explicitly
replay the same photo, then export the offline evidence ZIP. Replay is not a new
capture, physical repair, or completion. The UI can start without weights; actual
inference requires the separately installed local model and sufficient memory.

Windows/Linux model inference is not verified. Package smoke verification uses
existing dependencies, checks imports/routes/images, and does not load MLX or
establish clean-machine installation or recognition accuracy.

## Included public images and license

MVTec authors' images are redistributed under CC BY-NC-SA 4.0; retain attribution,
noncommercial use, and ShareAlike terms. The complete stored notices are in
third_party/datasets/. Source links and image SHA-256 values are also in
SOURCE_MANIFEST.json and kitguard/public_demo_catalog.py.

| Sample | Included photograph | Original source |
| --- | --- | --- |
{rows}

The two Screws images are integer crops of original photographs. No compositing
or object deletion was performed. Crop coordinates, original file hashes, and
author annotation hashes are recorded in the manifest's crop_provenance, linked
to {CROP_SPECS}. These three previously used development examples are not fresh
holdout data, recognition scores, or user feedback.

## External experiment data

scripts/v07/prepare_public_evaluation.py, run_public_paired.py, and
analyze_public_paired.py are included, as are their source-code dependencies.
Full datasets, the new 51-photo set, author raw annotations, historical experiment
outputs, training splits/weights, and browser records are external. Reproducing a
source-disjoint selection requires those exact historical exposure records and
their hashes; do not substitute an empty history or describe these three demo
images as new held-out evidence. Restore verified external inputs according to
docs/v0.7/PUBLIC_EVALUATION_PLAN.md before executing those experiments.

Photo-/history-dependent tests may require these excluded external artifacts.
No private SQLite database, user uploads, participant records, model weights,
cached environment, or generated delivery/report output is packaged.

## Verify and rebuild

SOURCE_MANIFEST.json lists every payload file's byte size, SHA-256, and normalized
mode. The archive uses sorted paths, fixed ZIP metadata, and content-derived
metadata. The same source bytes produce the same archive bytes with the same
Python/zlib toolchain. Checksums are integrity checks, not signatures.

```sh
.venv/bin/python -m scripts.v07.package_source --output /new/path/kitguard-source.zip --verify-runtime
```

The ZIP, .manifest.json, .sha256, and (when requested) .verification.json paths
must all be new. Existing artifacts are never overwritten. Development continues
after this snapshot; create a new explicitly named path for each later package.
""".encode()


def zip_write(archive, relative, data, mode):
    info = ZipInfo("KitGuard/" + relative, FIXED_TIME)
    info.create_system = 3
    info.compress_type = ZIP_DEFLATED
    info.external_attr = (stat.S_IFREG | mode) << 16
    archive.writestr(info, data, compress_type=ZIP_DEFLATED, compresslevel=9)


def verify_archive(path):
    with ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or archive.testzip() is not None:
            raise ValueError("Invalid ZIP membership/CRC")
        manifest_bytes = archive.read("KitGuard/SOURCE_MANIFEST.json")
        manifest = json.loads(manifest_bytes)
        records = manifest["files"]
        if set(names) != {"KitGuard/SOURCE_MANIFEST.json", *("KitGuard/" + row["path"] for row in records)}:
            raise ValueError("Archive membership does not match its manifest")
        for record in records:
            name = "KitGuard/" + record["path"]
            if ".." in PurePosixPath(name).parts or "\\" in name or PurePosixPath(record["path"]).is_absolute():
                raise ValueError("Unsafe ZIP member")
            data = archive.read(name)
            if len(data) != record["bytes"] or sha(data) != record["sha256"]:
                raise ValueError(f"Payload mismatch: {name}")
            if record["path"].endswith(".py"):
                compile(data, record["path"], "exec")
    return manifest_bytes


def verify_runtime(path):
    """Only isolated imports and HTTP calls; never inspect, download, or load MLX."""
    with tempfile.TemporaryDirectory(prefix="kitguard-v07-package-") as temporary:
        folder = Path(temporary)
        with ZipFile(path) as archive:
            archive.extractall(folder)  # Membership was validated by verify_archive first.
        source = folder / "KitGuard"
        env = dict(os.environ)
        for key in list(env):
            if key.startswith("KITGUARD_") or key in {"PYTHONPATH", "PYTHONHOME"}:
                env.pop(key)
        env.update({"KITGUARD_DATA_DIR": str(folder / "isolated-data"),
                    "KITGUARD_MODEL_PATH": str(folder / "absent-model"),
                    "KITGUARD_MODEL_PROFILE": "Qwen3.6-27B-4bit", "KITGUARD_OBSERVATION_MODE": "spatial_guarded",
                    "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1"})
        program = r'''
import hashlib, json, sys, tomllib
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
import kitguard
from kitguard.app import app
from fastapi.testclient import TestClient
from scripts.v07 import analyze_public_paired, prepare_public_evaluation, run_public_paired, package_source
assert Path(kitguard.__file__).resolve().is_relative_to(Path.cwd())
with TestClient(app) as client:
    paths = ['/', '/static/demo.html', '/static/demo.js', '/static/demo.css',
             '/static/public-review.js', '/static/public-review.css', '/static/workflow.js',
             '/static/trials.html', '/static/study.html', '/static/readiness.html', '/api/orders']
    routes = {p: client.get(p).status_code for p in paths}
    assert all(code == 200 for code in routes.values()), routes
    assert client.get('/api/orders').json() == {'orders': []}
    health = client.get('/api/health').json()
    assert health['version'] == tomllib.loads(Path('pyproject.toml').read_text())['project']['version']
    assert not health['model']['available'] and not health['model']['loaded']
    assert not any(n == 'mlx' or n.startswith('mlx.') for n in sys.modules)
    samples = client.get('/api/public-demos').json()['samples']
    assert len(samples) == 3 and all(s['available'] for s in samples)
    checked = []
    for sample in samples:
        image = client.get('/api/public-demos/' + sample['sample_id'] + '/photo')
        assert image.status_code == 200
        assert hashlib.sha256(image.content).hexdigest() == sample['source_sha256']
        created = client.post('/api/public-demos/' + sample['sample_id'] + '/orders')
        assert created.status_code == 201, created.text
        order = created.json()['order']
        assert order['checks'] == [] and order['completions'] == []
        state = client.get('/api/orders/' + order['id'] + '/public-review-summary')
        assert state.status_code == 200 and not state.json()['can_review']
        checked.append(sample['sample_id'])
    assert not any(n == 'mlx' or n.startswith('mlx.') for n in sys.modules)
print(json.dumps({'version': kitguard.__version__, 'routes': routes, 'public_samples': checked,
                  'isolated_import': True, 'mlx_imported': False, 'model_loaded': False,
                  'inference_called': False, 'experiment_runner_imports': True}))
'''
        result = subprocess.run([sys.executable, "-I", "-c", program], cwd=source, env=env,
                                capture_output=True, text=True, timeout=60, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"Extracted runtime smoke check failed: {result.stdout}\n{result.stderr}")
        for script in ["scripts/setup.sh", "scripts/run.sh", "启动KitGuard.command"]:
            subprocess.run(["bash", "-n", script], cwd=source, capture_output=True, text=True, check=True)
        return {"status": "passed", "scope": "Extracted source, existing dependencies; no clean install or inference",
                "runtime": json.loads(result.stdout), "shell_syntax": "passed", "python": sys.version}


def build(root, output, *, smoke=False):
    root = root.resolve()
    if output.is_symlink():
        raise FileExistsError("Preserve an existing output symlink")
    output = output.resolve()
    if output.suffix != ".zip":
        raise ValueError("Choose an explicit new .zip output path")
    if output.is_relative_to(root) and any(output.is_relative_to(root / tree) for tree in SOURCE_TREES):
        raise ValueError("Write packages outside included source trees, for example tmp/ or output/")
    sidecars = [output, Path(str(output) + ".manifest.json"), Path(str(output) + ".sha256")]
    if smoke:
        sidecars.append(Path(str(output) + ".verification.json"))
    if any(path.exists() or path.is_symlink() for path in sidecars):
        raise FileExistsError("Preserve existing archive/sidecars; choose a completely new output path")
    selected, samples = collect(root)
    payload = {}
    for relative, path in selected.items():
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError(f"Unexpected large source file: {relative}")
        payload[relative] = path.read_bytes()
    version = tomllib.loads(payload["pyproject.toml"].decode())["project"]["version"]
    init = ast.parse(payload["kitguard/__init__.py"])
    package_version = next(ast.literal_eval(n.value) for n in init.body if isinstance(n, ast.Assign)
                           and any(isinstance(t, ast.Name) and t.id == "__version__" for t in n.targets))
    if version != package_version or not version.startswith("0.7."):
        raise ValueError("pyproject and package must declare the same v0.7 version")
    # Source and sample bytes may be edited while collection runs: verify the exact captured bytes.
    for sample in samples:
        if sha(payload[sample["archive_path"]]) != sample["source_sha256"]:
            raise ValueError("Public sample changed during packaging")
    payload["SOURCE_PACKAGE.md"] = package_note(version, samples)
    if sum(map(len, payload.values())) > MAX_TOTAL_BYTES:
        raise ValueError("Source payload exceeds the intentional 100 MiB size ceiling")
    records = [{"path": name, "bytes": len(data), "sha256": sha(data),
                "mode": 0o755 if name.endswith((".sh", ".command")) else 0o644}
               for name, data in sorted(payload.items())]
    manifest = {"schema": "kitguard.v07.source-package.v1", "version": version,
                "submission_status": "Development source snapshot; not final contest delivery",
                "reproducible_zip_metadata": {"date_time": FIXED_TIME, "order": "sorted", "compression": "deflate-9"},
                "source_tree_sha256": sha(encoded(records)), "files": records, "public_demo_images": samples,
                "excluded": ["Model/training weights", "Private databases and uploaded photographs",
                             "Full datasets and new 51-photo holdout", "Experimental/browser outputs and participant records",
                             "Python/node environments, caches, generated reports/deliveries"],
                "image_policy": "Exactly the three catalog development photographs plus authored app static assets",
                "sources_and_licenses": "third_party/datasets/"}
    manifest_bytes = encoded(manifest)
    output.parent.mkdir(parents=True, exist_ok=True)
    handles, created = [], []
    try:
        # Exclusive creation reserves every output before producing any archive bytes.
        for path in sidecars:
            handles.append(path.open("xb")); created.append(path)
        with ZipFile(handles[0], "w", ZIP_DEFLATED, compresslevel=9) as archive:
            for record in records:
                zip_write(archive, record["path"], payload[record["path"]], record["mode"])
            zip_write(archive, "SOURCE_MANIFEST.json", manifest_bytes, 0o644)
        handles[0].close()
        if verify_archive(output) != manifest_bytes:
            raise ValueError("Written manifest differs")
        verification = verify_runtime(output) if smoke else None
        handles[1].write(manifest_bytes)
        checksum = sha(output.read_bytes())
        handles[2].write(f"{checksum}  {output.name}\n{sha(manifest_bytes)}  {sidecars[1].name}\n".encode())
        if smoke:
            handles[3].write(encoded({**verification, "archive_sha256": checksum,
                                      "source_tree_sha256": manifest["source_tree_sha256"]}))
        return {"path": str(output), "files": len(records), "bytes": output.stat().st_size, "sha256": checksum,
                "source_tree_sha256": manifest["source_tree_sha256"], "public_images": len(samples),
                "roundtrip_verified": True, "runtime_verified": smoke,
                "manifest": str(sidecars[1]), "checksums": str(sidecars[2])}
    except BaseException:
        for handle in handles:
            handle.close()
        for path in created:
            path.unlink(missing_ok=True)
        raise
    finally:
        for handle in handles:
            handle.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-runtime", action="store_true", help="Extract and smoke-check with existing dependencies; no MLX")
    args = parser.parse_args()
    try:
        print(json.dumps(build(ROOT, args.output, smoke=args.verify_runtime), ensure_ascii=False))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
