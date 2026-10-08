"""Verify an actual source ZIP and exercise its extracted code with existing dependencies."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-tests", type=int)
    parser.add_argument("--expected-skipped", type=int, default=5)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Preserve existing verification; choose a new output path")
    archive_path = args.archive.resolve()
    result = {
        "checked_at": datetime.now(UTC).isoformat(),
        "source_archive": str(archive_path),
        "source_archive_sha256": digest(archive_path.read_bytes()),
        "status": "failed",
        "scope": "Actual ZIP extracted to an isolated directory; CPU suite and HTTP routes with existing dependencies. No clean-machine installation, GPU inference or photographic re-evaluation.",
        "python": sys.version,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="kitguard-source-") as temporary:
            folder = Path(temporary).resolve()
            with ZipFile(archive_path) as archive:
                names = archive.namelist()
                assert len(names) == len(set(names)), "Duplicate archive members"
                assert all(
                    n.startswith("KitGuard/") and ".." not in PurePosixPath(n).parts
                    and not PurePosixPath(n).is_absolute() and "\\" not in n
                    for n in names
                ), "Unsafe archive path"
                assert archive.testzip() is None
                result["zip_crc_verified"] = True
                manifest = json.loads(archive.read("KitGuard/SOURCE_MANIFEST.json"))
                records = manifest["files"]
                assert set(names) == {"KitGuard/SOURCE_MANIFEST.json"} | {
                    "KitGuard/" + r["path"] for r in records
                }
                for record in records:
                    data = archive.read("KitGuard/" + record["path"])
                    assert len(data) == record["bytes"]
                    assert digest(data) == record["sha256"]
                result["all_file_digests_verified"] = True
                result["source_files"] = len(records)
                result["excluded"] = manifest["excluded"]
                archive.extractall(folder)
            root = folder / "KitGuard"
            env = dict(os.environ)
            env.update({
                "PYTHONPATH": str(root), "KITGUARD_DATA_DIR": str(folder / "isolated-data"),
                "KITGUARD_OBSERVATION_MODE": "spatial_guarded", "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1",
            })
            check = r'''
import json
import tomllib
from pathlib import Path
from fastapi.testclient import TestClient
import kitguard
from kitguard.app import app
assert Path(kitguard.__file__).resolve().is_relative_to(Path.cwd().resolve())
with TestClient(app) as client:
    paths = ['/', '/static/styles.css', '/static/app.js', '/static/demo.html',
             '/static/camera.js', '/static/audit.js', '/static/study.html', '/static/study.js',
             '/static/study.css', '/api/studies', '/api/public-demos', '/api/orders']
    if Path('kitguard/static/region.js').is_file():
        paths.extend(['/static/region.js', '/static/region.css'])
    routes = {path: client.get(path).status_code for path in paths}
    assert all(code == 200 for code in routes.values()), routes
    assert client.get('/api/orders').json() == {'orders': []}
    health = client.get('/api/health').json()
    expected_version = tomllib.loads(Path('pyproject.toml').read_text())['project']['version']
    assert health['ok'] and health['version'] == expected_version
    assert not health['model']['loaded']
    assert health['model']['observation_mode'] == 'spatial_guarded'
    print(json.dumps({'import_path': kitguard.__file__, 'routes': routes, 'health': health}))
'''
            run = subprocess.run([sys.executable, "-c", check], cwd=root, env=env,
                                 capture_output=True, text=True, timeout=60, check=False)
            result["runtime_returncode"] = run.returncode
            result["runtime_stderr"] = run.stderr
            assert run.returncode == 0, run.stdout + run.stderr
            result["runtime"] = json.loads(run.stdout)
            junit = folder / "extracted-tests.xml"
            suite = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "-rs", f"--junitxml={junit}"],
                cwd=root, env=env, capture_output=True, text=True, timeout=180, check=False,
            )
            log_path = args.output.with_suffix(".pytest.log")
            log_path.write_text(suite.stdout + suite.stderr)
            xml_path = args.output.with_suffix(".pytest.xml")
            xml_path.write_bytes(junit.read_bytes())
            suites = ET.parse(junit).getroot().findall("testsuite")
            counts = {key: sum(int(s.get(key, 0)) for s in suites)
                      for key in ("tests", "failures", "errors", "skipped")}
            result["extracted_suite"] = {
                **counts, "passed": counts["tests"] - counts["skipped"] - counts["failures"] - counts["errors"],
                "returncode": suite.returncode, "log": str(log_path.resolve()),
                "junit": str(xml_path.resolve()), "junit_sha256": digest(xml_path.read_bytes()),
                "skip_policy": f"Exactly {args.expected_skipped} declared photo/source replay checks require excluded public input photographs or author annotations; all other tests execute against extracted code and text records.",
            }
            assert suite.returncode == 0, suite.stdout + suite.stderr
            if args.expected_tests is not None:
                assert counts["tests"] == args.expected_tests
            assert counts["skipped"] == args.expected_skipped
            result["status"] = "passed"
    except (AssertionError, OSError, ValueError, KeyError, subprocess.SubprocessError, BadZipFile, ET.ParseError) as error:
        result["error"] = f"{type(error).__name__}: {error}"
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in {"runtime", "runtime_stderr"}}, ensure_ascii=False))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
