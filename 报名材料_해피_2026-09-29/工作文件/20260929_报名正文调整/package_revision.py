from pathlib import Path
import json,hashlib,shutil,zipfile

BASE=Path(__file__).parent
ROOT=BASE.parents[2]
OUT=ROOT/'现在签名_해피'
previous=json.loads((BASE.parent/'20260929_报名修订/本轮交付清单.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
old_zip=Path(previous['archive'])
assert sha(old_zip)==previous['sha256']
for item in previous['files']:
    assert sha(OUT/item['name'])==item['sha256']
name=previous['files'][0]['name']
new_app=BASE/name
audit=json.loads((BASE/'HWP结构核查.json').read_text())
assert sha(new_app)==audit['revised_sha256']
assert audit['changed_paragraphs']==4

qa=BASE/'本机韩文软件排版核验_非提交附件'
qa.mkdir(exist_ok=True)
for suffix in ['.pdf']+[f'-{n}.png' for n in range(1,5)]:
    p=Path('/tmp')/('kitguard-registration-plan-20260929-qa'+suffix)
    assert p.exists()
    shutil.copy2(p,qa/p.name)
audit.update(native_layout_verification='Passed: 4 pages opened and printed in Hancom Office HWP, then visually checked',native_pages=4,signature_page=4,application_date='2026-09-29',applicant_added_early_development_explanations_removed=True,official_consent_documents_unchanged=True)
(BASE/'HWP结构核查.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))

backup=BASE/'上版材料_勿提交'
backup.mkdir(exist_ok=True)
shutil.copy2(OUT/name,backup/name)
shutil.copy2(new_app,OUT/name)
archive=OUT/'창원대_해피_남청청외1명_20260929수정2.zip'
assert not archive.exists()
files=[OUT/i['name'] for i in previous['files']]
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for p in files:z.write(p,p.name)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert z.namelist()==[p.name for p in files]
    for p in files:assert z.read(p.name)==p.read_bytes()
assert archive.stat().st_size<100_000_000
old_zip.rename(backup/old_zip.name)

docs=[ROOT/'README.md',OUT/'签名位置与提交格式.md',OUT/'20260929_修订说明.md',ROOT/'报名材料_해피_2026-09-29/README_先看提交清单.md',ROOT/'报名材料_해피_2026-09-29/03_填写说明/20260927_报名操作与缺件清单.md',ROOT/'报名材料_해피_2026-09-29/03_填写说明/网页表单逐项填写.md']
for p in docs:
    text=p.read_text()
    (BASE/(p.stem+'_调整前.md')).write_text(text)
    p.write_text(text.replace(old_zip.name,archive.name))

manifest={'archive':str(archive),'bytes':archive.stat().st_size,'sha256':sha(archive),'files':[{'name':p.name,'sha256':sha(p),'bytes':p.stat().st_size} for p in files],'changed_application_paragraphs':4,'development_status':'Paused','uploaded_or_submitted':False,'consent_documents_unchanged':True,'certificate_documents_unchanged':True}
(BASE/'交付清单.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print(json.dumps(manifest,ensure_ascii=False,indent=2))
