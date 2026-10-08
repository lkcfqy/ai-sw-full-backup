"""Run only after source-ready approval. Build from a clean snapshot; no installation/download."""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from email.parser import Parser
from pathlib import Path
from zoneinfo import ZoneInfo

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
VERSION = '0.6.0.dev2'
QA = OUT / 'verification'
SOURCE = QA / 'build-source'
EXTRACTED = QA / 'extracted-wheel'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def main():
    if '--source-ready' not in sys.argv:
        raise SystemExit('Refused: wait for root source-ready confirmation, then use --source-ready.')
    assert not list(OUT.glob('*.whl')), 'Preserve existing wheel; do not overwrite'
    QA.mkdir(exist_ok=False)
    SOURCE.mkdir()
    package_files = sorted([*ROOT.glob('kitguard/*.py'),
                            *(p for p in (ROOT / 'kitguard/static').rglob('*') if p.is_file())])
    assert package_files and all(not p.is_symlink() for p in package_files)
    source_files = [ROOT / 'pyproject.toml', *package_files]
    snapshot = {}
    for path in source_files:
        relative = path.relative_to(ROOT).as_posix()
        content = path.read_bytes()
        target = SOURCE / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        snapshot[relative] = {'sha256': sha(content), 'bytes': len(content)}
    save(QA / 'source_snapshot.json', snapshot)
    environment = dict(os.environ)
    environment.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
                       PIP_NO_INDEX='1', PYTHONDONTWRITEBYTECODE='1')
    for name in list(environment):
        if name.startswith('KITGUARD_') or name in ('PYTHONPATH', 'PYTHONHOME'):
            environment.pop(name, None)
    code = 'import setuptools.build_meta as backend; backend.build_wheel(' + repr(str(OUT)) + ')'
    built = subprocess.run([sys.executable, '-I', '-c', code], cwd=SOURCE, env=environment,
                           capture_output=True, text=True, timeout=120)
    (QA / 'build.log').write_text(built.stdout + '\n' + built.stderr)
    assert built.returncode == 0, built.stderr[-3000:]
    wheels = list(OUT.glob('*.whl'))
    assert len(wheels) == 1
    wheel = wheels[0]
    assert wheel.name == f'kitguard-{VERSION}-py3-none-any.whl', wheel.name
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert archive.testzip() is None and len(names) == len(set(names))
        assert all(not n.startswith('/') and '..' not in Path(n).parts for n in names)
        expected = {n for n in snapshot if n.startswith('kitguard/')}
        packaged = {n for n in names if n.startswith('kitguard/')}
        assert packaged == expected, (packaged - expected, expected - packaged)
        for name in sorted(expected):
            raw = archive.read(name)
            assert sha(raw) == snapshot[name]['sha256'] and len(raw) == snapshot[name]['bytes'], name
        required = {'kitguard/readiness.py', 'kitguard/task_trials.py', 'kitguard/task_trial_api.py',
                    'kitguard/inspection_jobs.py', 'kitguard/manual_review.py',
                    'kitguard/static/workflow.js', 'kitguard/static/workflow.css',
                    *[f'kitguard/static/{base}.{suffix}' for base in ('readiness', 'trials')
                      for suffix in ('html', 'js', 'css')]}
        assert required <= packaged, required - packaged
        prefix = f'kitguard-{VERSION}.dist-info/'
        assert all(n.startswith(('kitguard/', prefix)) for n in names)
        assert not any(Path(n).suffix in {'.pt', '.pth', '.safetensors', '.db', '.sqlite', '.sqlite3', '.pyc'} for n in names)
        metadata = Parser().parsestr(archive.read(prefix + 'METADATA').decode())
        assert metadata['Version'] == VERSION and metadata['Name'] == 'kitguard'
        for name, digest, length in csv.reader(io.StringIO(archive.read(prefix + 'RECORD').decode())):
            if name == prefix + 'RECORD':
                assert digest == length == ''
                continue
            raw = archive.read(name)
            assert int(length) == len(raw)
            assert digest == 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b'=').decode()
        EXTRACTED.mkdir()
        archive.extractall(EXTRACTED)
    environment['KITGUARD_DATA_DIR'] = str(QA / 'default-import-data')
    runtime = subprocess.run([sys.executable, '-I', str(OUT / 'runtime_smoke.py'), str(EXTRACTED), str(QA)],
                             cwd=QA, env=environment, capture_output=True, text=True, timeout=60)
    (QA / 'runtime_smoke.log').write_text(runtime.stdout + '\n' + runtime.stderr)
    assert runtime.returncode == 0, runtime.stderr[-3000:]
    runtime_result = json.loads(runtime.stdout.strip())
    unchanged = all(sha((ROOT / n).read_bytes()) == item['sha256'] for n, item in snapshot.items())
    assert unchanged, 'Source changed during build: wheel is not final'
    report = {
        'checked_at': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        'wheel': str(wheel), 'wheel_sha256': sha(wheel.read_bytes()), 'wheel_bytes': wheel.stat().st_size,
        'version': VERSION, 'zip_integrity': 'passed', 'record_hashes_and_sizes': 'passed',
        'source_unchanged_since_snapshot': unchanged, 'package_files_exact_match': len(packaged),
        'static_file_count': sum(n.startswith('kitguard/static/') for n in packaged),
        'included_files': sorted(packaged), 'new_required_files': sorted(required),
        'weights_databases_datasets_or_cache_included': False,
        'requires_python': metadata['Requires-Python'], 'extras': metadata.get_all('Provides-Extra'),
        'requires_dist': metadata.get_all('Requires-Dist'), 'runtime': runtime_result,
        'platform': platform.platform(), 'python': platform.python_version(),
        'build_method': 'existing setuptools.build_meta.build_wheel; isolated source snapshot; no installation/download',
        'limitations': [
            'Existing virtualenv dependencies are reused; not a clean-machine dependency installation.',
            'Wheel was independently unpacked and imported with Python -I and an explicit extracted-package path.',
            'No trained model is loaded and no inference, GPU or CUDA-environment validation is performed.',
            'Synthetic/disabled status providers only; no physical users or accuracy evidence.',
            'Browser rendering and interactions are verified separately by the root agent.',
            'Wheel excludes datasets, model weights, source-only launchers, training scripts and documentation.',
        ],
    }
    save(OUT / 'wheel_validation.json', report)
    (OUT / 'SHA256SUMS').write_text(report['wheel_sha256'] + '  ' + wheel.name + '\n')
    print(json.dumps({k: report[k] for k in ('wheel', 'wheel_sha256', 'wheel_bytes', 'package_files_exact_match',
                                           'static_file_count', 'source_unchanged_since_snapshot')}, indent=2))


if __name__ == '__main__':
    main()
