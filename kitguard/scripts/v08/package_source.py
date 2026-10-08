"""Bounded v0.8 source component; external research artifacts stay external.

No model, original evaluation-image decode, private database, or submission action.
Development versions require --preview. Every output and sidecar must be new.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from zipfile import ZipFile

from scripts.v07 import package_source as old

ROOT = Path(__file__).resolve().parents[2]
MAX_FILE_BYTES, MAX_TOTAL_BYTES = old.MAX_FILE_BYTES, old.MAX_TOTAL_BYTES
SOURCE_TREES, TOP_FILES = old.SOURCE_TREES, old.TOP_FILES
REQUIRED = old.REQUIRED | {
    "kitguard/photo_documents.py", "kitguard/static/photo-documents.js",
    "kitguard/static/audit.js", "kitguard/static/workflow.js",
    "docs/v0.8/PHOTO_DOCUMENT_GUIDE_KO_ZH.md", "scripts/v08/package_source.py",
}
# Explicit research collections, not a size-based discard heuristic.
EXTERNAL_PREFIXES = {
    "datasets/manifests/v0.8/fod-a-v2.1": "FOD-A acquisition/annotation/group metadata; optional research dependency",
    "datasets/manifests/v0.8/manta-identity-v1": "MANTA archive member metadata; optional research dependency",
}
PRIVATE_NAMES = {"credentials.json", "secrets.json", "secrets.toml", "config.local.toml"}
PRIVATE_SUFFIXES = {".sqlite", ".sqlite3", ".db", ".pem", ".key", ".p12"}


def sha_file(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def private_file(path):
    return path.name.startswith(".env") or path.name in PRIVATE_NAMES or path.suffix in PRIVATE_SUFFIXES


def tree_binding(root, directory):
    """Bind omitted images/snapshots to an adjacent small freeze, never read pixels."""
    freeze = directory.parent / "freeze.json"
    if freeze.is_file():
        relative = freeze.relative_to(root).as_posix()
        old.regular_file(root, relative)
        if freeze.stat().st_size > MAX_FILE_BYTES:
            raise ValueError(f"Oversized freeze metadata: {relative}")
        return {"path": relative, "bytes": freeze.stat().st_size, "sha256": sha_file(freeze)}
    return None


def external_text_files(root, directory, purpose):
    """Hash external source/text only; runtime data, images and binaries are not read."""
    records = []
    for parent, dirs, files in os.walk(directory, followlinks=False):
        kept = []
        for name in sorted(dirs):
            p = Path(parent) / name
            if name in old.OMIT_PARTS or name.endswith(".runtime-app-data") or name in {"data", "normalized_inputs"}:
                continue
            if p.is_symlink():
                raise ValueError(f"Unsafe external source symlink: {p.relative_to(root)}")
            kept.append(name)
        dirs[:] = kept
        for name in sorted(files):
            path = Path(parent) / name
            if private_file(path) or name in old.OMIT_PARTS:
                continue
            if path.suffix not in old.TEXT_SUFFIXES and name not in {"LICENSE", "NOTICE"}:
                continue
            relative = path.relative_to(root).as_posix()
            old.regular_file(root, relative)
            records.append({"path": relative, "bytes": path.stat().st_size, "sha256": sha_file(path), "purpose": purpose})
    return records


def collect(root):
    root = root.resolve()
    selected = {name: old.regular_file(root, name) for name in TOP_FILES}
    optional = "启动检测验证台.command"
    if (root / optional).is_file():
        selected[optional] = old.regular_file(root, optional)
    external, omitted = [], []
    for directory in SOURCE_TREES:
        base = root / directory
        if base.is_symlink():
            raise ValueError(f"Unsafe source tree symlink: {directory}")
        for parent, dirs, files in os.walk(base, followlinks=False):
            keep = []
            for name in sorted(dirs):
                path = Path(parent) / name
                relative = path.relative_to(root).as_posix()
                if name in old.OMIT_PARTS or name.endswith(".runtime-app-data"):
                    continue
                if path.is_symlink():
                    raise ValueError(f"Unsafe source symlink: {relative}")
                reason = EXTERNAL_PREFIXES.get(relative)
                if name == "source_snapshot":
                    reason = "Frozen historical source snapshot; exact raw replay requires this external tree"
                if reason:
                    external.extend(external_text_files(root, path, reason))
                    omitted.append({"path": relative, "purpose": reason, "binding": tree_binding(root, path),
                                    "indexed_scope": "regular source/text files only; no runtime data or images"})
                elif name == "normalized_inputs":
                    omitted.append({"path": relative, "purpose": "External evaluation photographs; not inspected or bundled",
                                    "binding": tree_binding(root, path), "indexed_scope": "tree only; image bytes not read"})
                else:
                    keep.append(name)
            dirs[:] = keep
            for name in sorted(files):
                path = Path(parent) / name
                if private_file(path) or name in old.OMIT_PARTS:
                    continue
                relative = path.relative_to(root).as_posix()
                suffixes = old.STATIC_SUFFIXES if relative.startswith("kitguard/static/") else old.TEXT_SUFFIXES
                if path.suffix not in suffixes and name not in {"LICENSE", "NOTICE"}:
                    continue
                selected[relative] = old.regular_file(root, relative)
    missing = REQUIRED - selected.keys()
    if missing:
        raise ValueError("Required v0.8 files missing: " + ", ".join(sorted(missing)))
    samples = old.public_samples(root)  # Three IDs, exact bytes, source, license and crop provenance.
    for sample in samples:
        selected[sample["archive_path"]] = old.regular_file(root, sample["archive_path"])
    index = {
        "schema": "kitguard.v08.external-artifact-index.v1",
        "scope": "Optional research text/source omitted by explicit path rules; hashes are integrity checks, not signatures",
        "external_files": sorted(external, key=lambda r: r["path"]),
        "external_trees": sorted(omitted, key=lambda r: r["path"]),
        "not_scanned_or_bundled": ["models/", "data/", "user uploads and private runtime databases",
                                   "datasets/raw/ except the exact three catalog demo files", "evaluation-runs/",
                                   "test-results/", "output/", "*.runtime-app-data/"],
        "full_experiment_reproduction_self_contained": False,
    }
    return dict(sorted(selected.items())), samples, index


def source_version(payload, preview):
    version = tomllib.loads(payload["pyproject.toml"].decode())["project"]["version"]
    tree = ast.parse(payload["kitguard/__init__.py"])
    declared = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "__version__" for t in n.targets))
    if version != declared or not re.fullmatch(r"0\.8\.\d+(?:\.dev\d+)?", version):
        raise ValueError("Matching v0.8 project/package versions required")
    if ".dev" in version and not preview:
        raise ValueError("Development source requires explicit --preview")
    return version


def package_note(version, preview, samples):
    rows = "\n".join(f"| {s['sample_id']} | {s['archive_path']} | {s['source_url']} |" for s in samples)
    label = "DEVELOPMENT PREVIEW / 개발 미리보기 / 开发预览" if preview else "SOURCE COMPONENT / 소스 구성요소 / 源码组件"
    return f"""# KitGuard {version} · {label}

This is a source component, not a complete contest submission or accuracy/safety
certification. Consult the accompanying delivery manifest. Version bytes are read
from this source; fixed ZIP timestamps are reproducibility metadata, not a release date.

## Run / 실행 / 运行

On Apple Silicon macOS, with uv installed:

```sh
bash scripts/setup.sh
.venv/bin/python scripts/download_candidate_model.py
bash scripts/run.sh
```

Model weights and Python dependencies are separate downloads. The downloader uses
the repository's pinned model revision/hashes. An already verified installation may
set KITGUARD_MODEL_PATH instead. Open http://127.0.0.1:8765/?new=photo-document
for a local JPEG/PNG/WebP photo with a required source statement, or
http://127.0.0.1:8765/static/demo.html for the three included development examples.
Follow docs/v0.8/PHOTO_DOCUMENT_GUIDE_KO_ZH.md. A URL is a statement, not a download.
User-declared source/license remain unverified. Digital review is not physical
completion; order revision requires explicit same-photo reuse and a new inspection.

The UI starts without weights. Actual inference requires the separate local model
and adequate memory. Windows/Linux inference and clean-machine installation are
not established by the package smoke test. That test uses existing dependencies,
synthetic pixels and HTTP contracts only; no MLX/model call or human participation.

## Included demo photographs

| ID | Package path | Source |
| --- | --- | --- |
{rows}

Retain MVTec attribution and CC BY-NC-SA 4.0 terms in third_party/datasets/.
Two Screws samples are integer crops with recorded source and annotation hashes;
SOURCE_MANIFEST.json includes crop provenance. The three images are previously
exposed development examples, not new holdout evidence or user feedback. No new
reference crops, FOD/MANTA photos or original training/evaluation collections are bundled.

## External research evidence

EXTERNAL_ARTIFACT_INDEX.json records explicitly omitted research metadata and
historical source text with project-relative path, byte size, SHA-256 and purpose.
Nested frozen source snapshots and normalized evaluation images are external;
small freeze metadata may remain as a dependency map. Excluded evaluation/training
images are not read; the three listed demo images are read and hashed. Full run/raw
outputs, weights and exposure records are also external.
Restoring the correct hashes is required for research replay. This ZIP alone cannot
reproduce all reported experiments. Data-dependent tests may need those artifacts.
Repository-relative links to test-results/evaluation-runs may be absent here; use
the accompanying delivery evidence index rather than interpreting them as packaged.

Private SQLite databases, user uploads, runtime directories and credentials are not
included. Unknown oversized source files fail; no file is dropped because of size.
Every bundled file is listed with byte size and SHA in SOURCE_MANIFEST.json.

## Rebuild to a new path

```sh
.venv/bin/python -m scripts.v08.package_source --preview \\
  --output /new/path/kitguard-source-preview.zip --verify-runtime
```

The ZIP and its .manifest.json, .sha256 and .verification.json sidecars must be new.
The same bytes and Python/zlib toolchain yield the same archive. Integrity hashes
are not identity signatures, authorization, or proof of physical capture.
""".encode()


SMOKE_PROGRAM = r'''
import hashlib, io, json, sys, tomllib
from pathlib import Path
from zipfile import ZipFile
sys.path.insert(0, str(Path.cwd()))
from PIL import Image
from fastapi.testclient import TestClient
import kitguard
from kitguard.app import app
from kitguard.photo_documents import is_digital_only
routes_list = ['/', '/?new=photo-document', '/static/photo-documents.js', '/static/app.js',
               '/static/audit.js', '/static/public-review.js', '/static/public-review.css',
               '/static/workflow.js', '/static/demo.html', '/static/demo.js', '/static/demo.css',
               '/static/readiness.html', '/api/orders']
with TestClient(app) as client:
    routes = {p: client.get(p).status_code for p in routes_list}
    assert all(v == 200 for v in routes.values()), routes
    assert client.get('/api/orders').json() == {'orders': []}
    health = client.get('/api/health').json()
    assert health['version'] == tomllib.loads(Path('pyproject.toml').read_text())['project']['version']
    assert not health['model']['available'] and not health['model']['loaded']
    js = client.get('/static/photo-documents.js').text
    assert '사용자 진술' in js and '用户自报' in js
    page = client.get('/').text
    assert 'photo-documents.js' in page
    pixels = io.BytesIO(); Image.new('RGB', (64,64), '#f2e3bf').save(pixels, format='PNG')
    raw = pixels.getvalue()
    metadata = {'title':'SYNTHETIC source-package smoke', 'requirements':dict(bolt=1,nut=1,washer=1,bracket=0),
                'source_note':'Synthetic CPU smoke pixels; no real parts or user', 'source_url':None,
                'license_note':None, 'confirmed_digital_only':True}
    bad = client.post('/api/photo-documents', data={'metadata':json.dumps(metadata)}, files={'photo':('invalid.png',b'NOT IMAGE','image/png')})
    assert bad.status_code == 422 and client.get('/api/orders').json() == {'orders': []}
    created = client.post('/api/photo-documents', data={'metadata':json.dumps(metadata)}, files={'photo':('synthetic.png',raw,'image/png')})
    assert created.status_code == 201, created.text
    body=created.json(); order=body['order']; photo=body['photo']; oid=order['id']
    assert is_digital_only(order) and not order.get('demo_source')
    source=order['document_source']
    assert source['verification']=='user_declared_unverified' and source['physical_completion_allowed'] is False
    assert source['source_sha256']==hashlib.sha256(raw).hexdigest()
    assert source['original_root_photo_id']==photo['id'] and order['checks']==[] and order['completions']==[]
    summary=client.get(f'/api/orders/{oid}/public-review-summary').json()
    assert summary['scope']=='photo_document_digital_review' and not summary['can_review']
    replace=client.post(f'/api/orders/{oid}/photos',data={'expected_revision':'1'},files={'photo':('synthetic.png',raw,'image/png')})
    assert replace.status_code == 409, replace.text
    complete=client.post(f'/api/orders/{oid}/complete',json={'expected_revision':1,'check_id':'synthetic-no-check','confirmed':True,'idempotency_key':'synthetic-package-no-complete'})
    assert complete.status_code == 409, complete.text
    exported=client.get(f'/api/orders/{oid}/evidence.zip')
    assert exported.status_code == 200
    with ZipFile(io.BytesIO(exported.content)) as archive:
        evidence=json.loads(archive.read('evidence.json'))
        assert evidence['order']['document_source']==source
        assert not evidence['order']['checks'] and not evidence['order']['completions']
        assert '用户自报' in archive.read('OPEN_ME.html').decode()
        manifest=json.loads(archive.read('SHA256.json'))
        for record in manifest:
            blob=archive.read(record['path'])
            assert len(blob)==record['bytes'] and hashlib.sha256(blob).hexdigest()==record['sha256']
    demos=client.get('/api/public-demos').json()['samples']
    assert len(demos)==3 and all(d['available'] for d in demos)
    for demo in demos:
        response=client.get('/api/public-demos/'+demo['sample_id']+'/photo')
        assert response.status_code==200 and hashlib.sha256(response.content).hexdigest()==demo['source_sha256']
    assert not any(n=='mlx' or n.startswith('mlx.') for n in sys.modules)
print(json.dumps({'version':kitguard.__version__,'routes':routes,'synthetic':True,'model_calls':0,'human_participants':0,
                  'mlx_imported':False,'multipart_create':201,'invalid_upload':422,'root_replace':409,
                  'physical_complete':409,'unverified_source_preserved':True,'zip_manifest_verified':True,
                  'public_samples':[d['sample_id'] for d in demos]}))
'''


def runtime_probe(source, runtime_dir):
    env = {k: v for k, v in os.environ.items() if not k.startswith("KITGUARD_") and k not in {"PYTHONPATH", "PYTHONHOME"}}
    env.update({"KITGUARD_DATA_DIR": str(runtime_dir / "data"), "KITGUARD_MODEL_PATH": str(runtime_dir / "absent-model"),
                "KITGUARD_MODEL_PROFILE": "Qwen3.6-27B-4bit", "KITGUARD_OBSERVATION_MODE": "spatial_guarded",
                "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1"})
    result = subprocess.run([sys.executable, "-I", "-c", SMOKE_PROGRAM], cwd=source, env=env,
                            capture_output=True, text=True, timeout=60, check=False)
    if result.returncode:
        raise RuntimeError(f"Synthetic source smoke failed: {result.stdout}\n{result.stderr}")
    for script in ("scripts/setup.sh", "scripts/run.sh", "启动KitGuard.command"):
        subprocess.run(["bash", "-n", script], cwd=source, capture_output=True, text=True, check=True)
    return {"status": "passed", "scope": "Existing dependencies; synthetic HTTP only, no clean install, model or browser",
            "runtime": json.loads(result.stdout), "shell_syntax": "passed"}


def verify_runtime(archive):
    old.verify_archive(archive)
    with tempfile.TemporaryDirectory(prefix="kitguard-v08-source-") as temporary:
        folder = Path(temporary)
        with ZipFile(archive) as zipped:
            zipped.extractall(folder)  # Paths/member equality already checked by verify_archive.
        return runtime_probe(folder / "KitGuard", folder / "isolated-runtime")


def build(root, output, *, preview=False, smoke=False):
    root = root.resolve()
    if output.is_symlink():
        raise FileExistsError("Output symlink cannot be replaced")
    output = output.resolve()
    if output.suffix != ".zip" or any(output.is_relative_to(root / tree) for tree in SOURCE_TREES):
        raise ValueError("Use a new ZIP path outside included source trees")
    sidecars = [output, Path(str(output)+".manifest.json"), Path(str(output)+".sha256"), Path(str(output)+".verification.json")]
    if any(p.exists() or p.is_symlink() for p in sidecars):
        raise FileExistsError("Preserve existing output and sidecars; choose a new path")
    selected, samples, external = collect(root)
    payload = {}
    for name, path in selected.items():
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError(f"Unknown oversized included source file: {name}")
        payload[name] = path.read_bytes()
    version = source_version(payload, preview)
    for sample in samples:
        if old.sha(payload[sample["archive_path"]]) != sample["source_sha256"]:
            raise ValueError("Demo bytes changed during collection")
    payload["SOURCE_PACKAGE.md"] = package_note(version, preview, samples)
    payload["EXTERNAL_ARTIFACT_INDEX.json"] = old.encoded(external)
    if any(len(v) > MAX_FILE_BYTES for v in payload.values()) or sum(map(len, payload.values())) > MAX_TOTAL_BYTES:
        raise ValueError("Source payload exceeds unchanged 16 MiB file / 100 MiB total limits")
    records = [{"path": n, "bytes": len(v), "sha256": old.sha(v), "mode": 0o755 if n.endswith((".sh", ".command")) else 0o644}
               for n,v in sorted(payload.items())]
    manifest = {"schema": "kitguard.v08.source-package.v1", "version": version, "preview": preview,
                "submission_status": "Source component; no claim of complete submission; consult accompanying delivery manifest",
                "files": records, "public_samples": samples, "full_experiment_reproduction_self_contained": False,
                "external_index_sha256": old.sha(payload["EXTERNAL_ARTIFACT_INDEX.json"])}
    # Refuse source races after capture rather than pairing inconsistent live bytes.
    if any(sha_file(path) != old.sha(payload[name]) for name,path in selected.items()):
        raise ValueError("Source changed during capture")
    if any(sha_file(root / r["path"]) != r["sha256"] for r in external["external_files"]):
        raise ValueError("External index changed during capture")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream, ZipFile(stream, "w") as archive:
        for record in records:
            old.zip_write(archive, record["path"], payload[record["path"]], record["mode"])
        old.zip_write(archive, "SOURCE_MANIFEST.json", old.encoded(manifest), 0o644)
    old.verify_archive(output)
    with sidecars[1].open("xb") as stream:
        stream.write(old.encoded(manifest))
    with sidecars[2].open("x") as stream:
        stream.write(f"{sha_file(output)}  {output.name}\n")
    if smoke:
        result = verify_runtime(output)
        result.update(archive_sha256=sha_file(output), version=version, preview=preview)
        with sidecars[3].open("xb") as stream:
            stream.write(old.encoded(result))
    return {"path": str(output), "sha256": sha_file(output), "bytes": output.stat().st_size,
            "version": version, "preview": preview, "files": len(records), "smoke_verified": smoke}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--verify-runtime", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build(ROOT, args.output, preview=args.preview, smoke=args.verify_runtime), ensure_ascii=False))


if __name__ == "__main__":
    main()
