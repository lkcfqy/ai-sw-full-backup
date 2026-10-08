from pathlib import Path
import hashlib
import json
import shutil
import zipfile

BASE = Path(__file__).parent
ROOT = BASE.parents[2]
OUT = ROOT / '现在签名_해피'
REG = ROOT / '报名材料_해피_2026-09-29'
manifest = json.loads((BASE / '签署记录.json').read_text())
assert len(json.loads((BASE / '签署核查结果.json').read_text())) == 3
backup = OUT / '未签名备份_勿提交'
backup.mkdir(exist_ok=True)

files = []
for item in manifest['files']:
    source = BASE / item['file']
    assert hashlib.sha256(source.read_bytes()).hexdigest() == item['sha256']
    destination = OUT / source.name
    if destination.exists():
        assert destination.read_bytes() == source.read_bytes()
    else:
        shutil.copy2(source, destination)
    files.append(destination)
for path in sorted(OUT.glob('0[123]_*서명전.hwp')):
    destination = backup / path.name
    assert not destination.exists()
    path.rename(destination)
for name in ['04_재학증명서_남청청.pdf', '05_재학증명서_이개심.pdf']:
    p = OUT / name
    assert p.read_bytes() == (REG / '02_资格证明放这里' / name).read_bytes()
    files.append(p)

archive = OUT / '창원대_해피_남청청외1명.zip'
assert not archive.exists()
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for p in files:
        z.write(p, p.name)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert z.namelist() == [p.name for p in files]
    for p in files:
        assert z.read(p.name) == p.read_bytes()
assert archive.stat().st_size < 100_000_000

qa = BASE / '本机韩文软件排版核验_非提交附件'
qa.mkdir(exist_ok=True)
for n, pages in [('01', 4), ('02', 2), ('03', 2)]:
    for p in [Path('/tmp') / f'kitguard-signed-{n}-qa.pdf'] + [Path('/tmp') / f'kitguard-signed-{n}-qa-{page}.png' for page in range(1, pages + 1)]:
        shutil.copy2(p, qa / p.name)

result = {
    'archive': str(archive),
    'archive_bytes': archive.stat().st_size,
    'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
    'files': [{'name': p.name, 'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in files],
    'zip_integrity_verified': True,
    'uploaded_or_submitted': False,
    'organizer_confirmation_status': 'Unchanged; see registration checklist',
}
(BASE / '交付文件清单.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps(result, ensure_ascii=False, indent=2))
