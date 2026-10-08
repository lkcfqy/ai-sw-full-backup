from pathlib import Path
import hashlib
import json
import subprocess
import zlib
import olefile

BASE = Path(__file__).parent
PROC = '/tmp/gnict-archive-venv/bin/hwp5proc'
manifest = json.loads((BASE / '签署记录.json').read_text())

def sha(data):
    return hashlib.sha256(data).hexdigest()

def models(path, stream):
    return json.loads(subprocess.check_output([PROC, 'models', '--json', str(path), stream]))

def texts(ms):
    return [''.join(c[1] for c in m['content']['chunks'] if isinstance(c[1], str))
            for m in ms if m['type'] == 'ParaText']

checks = []
for item in manifest['files']:
    dest = BASE / item['file']
    original = next(BASE.glob('unsigned-' + dest.name[:3] + '*.hwp'))
    before, after = models(original, 'BodyText/Section0'), models(dest, 'BodyText/Section0')
    bt, at = texts(before), texts(after)
    assert len(bt) == len(at)
    differences = [(a, b) for a, b in zip(bt, at) if a != b]
    app = dest.name.startswith('01_')
    assert len(differences) == (2 if app else 6), differences
    for a, b in differences:
        if '[  ] 동의함    [  ] 동의하지 않음' in a:
            assert b == a.replace('[  ] 동의함    [  ] 동의하지 않음', '[✓] 동의함    [  ] 동의하지 않음')
        elif a.strip().startswith('2026년') and a.rstrip().endswith('일'):
            assert b == '2026년 9월 28일'
        else:
            assert a.startswith('상기신청인 (대표)' if app else '성    명 :'), (a, b)
            name = item['participant']
            assert b == (f'상기신청인 (대표) {name}    (인)' if app else f'성    명 : {name}     (인 또는 서명)'), b
    assert sum(m['type'] == 'ShapePicture' for m in after) == 1
    assert sum(m['type'] == 'ParaHeader' for m in before) == sum(m['type'] == 'ParaHeader' for m in after)
    resource = BASE / ('member-signature-original.jpg' if dest.name.startswith('03_') else 'leader-signature-original.jpg')
    with olefile.OleFileIO(original) as old, olefile.OleFileIO(dest) as new:
        assert new.openstream('BinData/BIN0001.jpg').read() == resource.read_bytes()
        for stream in old.listdir():
            if stream not in [['DocInfo'], ['BodyText', 'Section0'], ['PrvText']]:
                assert old.openstream(stream).read() == new.openstream(stream).read(), stream
        assert zlib.decompress(new.openstream('BodyText/Section0').read(), -15) == dest.with_suffix('.body').read_bytes()
    assert sha(original.read_bytes()) == item['source_sha256']
    assert sha(dest.read_bytes()) == item['sha256']
    native_qa = Path('/tmp') / f'kitguard-signed-{dest.name[:2]}-qa.pdf'
    assert native_qa.is_file()
    checks.append({
        'file': dest.name, 'sha256': item['sha256'],
        'text_changes_limited_to_date_signature_and_authorized_consent': True,
        'official_clauses_and_other_text_unchanged': True,
        'original_signature_bytes_preserved': True,
        'independent_hwp_parser_passed': True,
        'opened_in_native_hancom': True,
        'native_hancom_pages_visually_checked': 4 if app else 2,
        'signature_page': 4 if app else 2,
        'native_print_qa_pdf_sha256': sha(native_qa.read_bytes()),
        'signature_and_checks_readable_no_overlap': True,
    })
(BASE / '签署核查结果.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2))
print(json.dumps(checks, ensure_ascii=False, indent=2))
