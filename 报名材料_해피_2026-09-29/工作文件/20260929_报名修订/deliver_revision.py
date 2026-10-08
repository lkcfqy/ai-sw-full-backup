from pathlib import Path
import json, shutil, hashlib, zipfile

BASE=Path(__file__).parent
ROOT=BASE.parents[2]
OUT=ROOT/'现在签名_해피'
OLD=ROOT/'报名材料_해피_2026-09-29/工作文件/20260928_HWP签名'
original=json.loads((OLD/'交付文件清单.json').read_text())
sha=lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
archive_name='창원대_해피_남청청외1명_20260929수정.zip'
old_archive=OUT/Path(original['archive']).name
assert sha(old_archive)==original['archive_sha256']
for entry in original['files']:
    assert sha(OUT/entry['name'])==entry['sha256']

app=BASE/original['files'][0]['name']
check=json.loads((BASE/'HWP结构核查.json').read_text())
assert sha(app)==check['revised_sha256']
qa=BASE/'本机韩文软件排版核验_非提交附件'
qa.mkdir(exist_ok=True)
for suffix in ['.pdf']+[f'-{i}.png' for i in range(1,5)]:
    p=Path('/tmp')/('kitguard-registration-revised-20260929-qa'+suffix)
    assert p.exists()
    shutil.copy2(p,qa/p.name)
check.update(native_layout_verification='Passed: opened in Hancom Office HWP; all 4 printed pages visually inspected',native_pages=4,signature_page=4,body_overflow_or_signature_overlap=False,application_date='2026-09-29',consent_dates_unchanged='2026-09-28')
(BASE/'HWP结构核查.json').write_text(json.dumps(check,ensure_ascii=False,indent=2))

backup=BASE/'修订前报名包_勿提交'
backup.mkdir(exist_ok=True)
for entry in original['files']:
    shutil.copy2(OUT/entry['name'],backup/entry['name'])
shutil.copy2(old_archive,backup/old_archive.name)
shutil.copy2(app,OUT/app.name)

paths=[OUT/entry['name'] for entry in original['files']]
new_archive=OUT/archive_name
assert not new_archive.exists()
with zipfile.ZipFile(new_archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for p in paths:z.write(p,p.name)
with zipfile.ZipFile(new_archive) as z:
    assert z.testzip() is None
    assert z.namelist()==[p.name for p in paths]
    for p in paths:assert z.read(p.name)==p.read_bytes()
assert new_archive.stat().st_size<100_000_000
# The previous ZIP remains available in the work-file archive; keep a single current ZIP here.
assert old_archive.read_bytes()==(backup/old_archive.name).read_bytes()
old_archive.unlink()

active_docs=[ROOT/'README.md',OUT/'签名位置与提交格式.md',ROOT/'报名材料_해피_2026-09-29/README_先看提交清单.md',ROOT/'报名材料_해피_2026-09-29/03_填写说明/20260927_报名操作与缺件清单.md',ROOT/'报名材料_해피_2026-09-29/03_填写说明/网页表单逐项填写.md']
for p in active_docs:
    content=p.read_text()
    (BASE/(p.stem+'_本轮修订前.md')).write_text(content)
    content=content.replace('창원대_해피_남청청외1명.zip',archive_name)
    if p==ROOT/'README.md':
        content=content.replace('日期为2026年9月28日','申请书日期更新为2026年9月29日，两份同意书日期保留9月28日')
    elif p.name=='README_先看提交清单.md':
        content=content.replace('日期均填2026年9月28日','原签署日期为2026年9月28日；9月29日修订申请书后，其日期更新为9月29日，两份同意书继续保留9月28日')
        content=content.replace('更新日期：2026年9月28日（地址与在学证明已补齐；赛事网页上次核查为9月27日）','更新日期：2026年9月29日（开发暂停，申请书按报名计划修订；主办方公告当日已复查）')
        content=content.replace('**先读[报名操作与缺件清单（9月28日补件更新）]','**先读[报名操作与缺件清单（9月29日修订）]')
        content+='\n9月29日修订：项目介绍、方法和指标按拟开展的报名方案表述；已有开发集中为第2页一段事实说明，保留9月26日起的实现与试验经历，写明目前暂停和待主办方确认。详见[修订说明](../现在签名_해피/20260929_修订说明.md)。\n'
    elif p.name=='20260927_报名操作与缺件清单.md':
        content=content.replace('# 报名操作与缺件清单（9月28日签署更新）','# 报名操作与缺件清单（9月29日修订）')
        content=content.replace('地址、2026年9月28日签署日期、两人的原图签名和两份同意书的四组选项均已完成','地址、日期、两人的原图签名和两份同意书的四组选项均已完成；9月29日修订的申请书日期为9月29日，同意书保留9月28日')
        content+='\n9月29日补充：开发已按用户指示暂停，申请书第2页保留集中事实说明。可使用[主办方确认短稿（未发送）](20260929_主办方确认短稿_未发送.md)确认能否受理及可用开发范围；本地修订不代表已获豁免或完成报名。\n'
    elif p.name=='网页表单逐项填写.md':
        content=content.replace('9月28日已完成签署的','9月29日已修订核验的')
    p.write_text(content)

delivered={
    'archive':str(new_archive),'bytes':new_archive.stat().st_size,'sha256':sha(new_archive),
    'files':[{'name':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in paths],
    'development_status':'Paused at user request; no automatic resume',
    'existing_work_disclosure':'One factual paragraph on application page 2; development since 2026-09-26, currently paused, organizer confirmation pending',
    'uploaded_or_submitted':False,'organizer_contacted':False,
}
(BASE/'本轮交付清单.json').write_text(json.dumps(delivered,ensure_ascii=False,indent=2))
print(json.dumps(delivered,ensure_ascii=False,indent=2))
