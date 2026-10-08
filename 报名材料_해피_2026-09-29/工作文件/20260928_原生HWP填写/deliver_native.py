from pathlib import Path
import shutil,hashlib,json
ROOT=Path('/Users/lkc/Downloads/AI·SW');BASE=Path(__file__).parent;DEST=ROOT/'现在签名_해피'; REG=ROOT/'报名材料_해피_2026-09-29'
audit=json.loads((BASE/'最终HWP核查.json').read_text())
for a in audit:
 src=BASE/a['file'];dst=DEST/src.name
 assert hashlib.sha256(src.read_bytes()).hexdigest()==a['sha256']
 if dst.exists():assert dst.read_bytes()==src.read_bytes(),f'Existing different file: {dst}'
 else:shutil.copy2(src,dst)
 assert dst.read_bytes()==src.read_bytes()
archive=DEST/'旧版PDF_已停用勿提交';archive.mkdir(exist_ok=True)
pdf_sources={
 '01_해피_참가신청서_개발계획서_서명전.pdf':REG/'05_20260928地址已补_待签字/01_해피_참가신청서_개발계획서_20260928_서명전.pdf',
 '02_참가자_동의서_남청청_선택서명전.pdf':REG/'01_待补地址与签字/02_참가자_동의서_남청청_선택서명전.pdf',
 '03_참가자_동의서_이개심_선택서명전.pdf':REG/'01_待补地址与签字/03_참가자_동의서_이개심_선택서명전.pdf'}
for n,canonical in pdf_sources.items():
 src=DEST/n
 if src.exists():
  assert src.read_bytes()==canonical.read_bytes(),f'PDF modified; preserve in place: {n}'
  dst=archive/n
  assert not dst.exists(),f'Archive collision: {dst}'
  shutil.move(src,dst)
old=DEST/'签名位置与提交格式.md'
if old.exists():shutil.copy2(old,BASE/'签名位置与提交格式_更新前.md')
old.write_text('''# 签名位置与提交格式（官方 HWP 原表填写版）

2026年9月28日更新：按你的要求直接填写官方修订r1的原生 `.hwp`。现在使用本文件夹的01、02、03三份HWP；04、05为你提供的原始在学证明PDF。旧版重排PDF已经移入“旧版PDF_已停用勿提交”，不再作为本次签署主文件。

三份HWP均已在Hancom Office HWP中实际打开，检查完整打印输出。申请书保留原表的三个表格、字段和注意事项；个人同意书保留官方条款及四组选择项。只是填入已知信息，没有代选个人同意项、代签或提交。

| 文件 | 需要本人完成 | 页数与位置 |
|---|---|---|
| 01_해피_참가신청서_개발계획서_서명전.hwp | 남청청填写实际签署日期，在姓名右侧“(인)”签字或盖章 | 全文4页；日期和签名均在第4页 |
| 02_참가자_동의서_남청청_선택서명전.hwp | 남청청阅读并选择四组同意项，填写日期，在“(인 또는 서명)”签署 | 全文2页；签名在第2页 |
| 03_참가자_동의서_이개심_선택서명전.hwp | 이개심本人完成同意选择、日期和签署 | 全文2页；签名在第2页 |

以本机Hancom核验分页为准；其他软件如分页不同，请按对应栏位定位。保留每份文件的全部页面。原表已经预印2026年9月，“日”留空。打印姓名不等于签名。第1页“개인정보 제3자 제공 동의 (선택)”为可选项，原文注明不同意该项不影响参赛。

签署工作继续以HWP为主文件，最终保存为`.hwp`；不要把PDF直接更改扩展名。若打印后手签，保留完整扫描件，并将签字图放入“签好后放这里”，再在HWP对应位置完成签名图嵌入。两份在学证明PDF保留原始文件，不需重写或签署。

本机Hancom当前提示“只读”，是该软件编辑功能需要付费订阅，并非这三份HWP加密或锁定；已验证可打开和打印。直接编辑及保存签名需要具备编辑功能的HWP软件。

最终附件包按三份已完成签署的HWP和两份原始在学证明PDF准备；当前没有生成最终ZIP。规则确认事项继续见[报名操作与缺件清单](../报名材料_해피_2026-09-29/03_填写说明/20260927_报名操作与缺件清单.md)。此前采用PDF的建议已由本说明替代。
''')
qa=BASE/'本机韩文编辑器排版核验';qa.mkdir(exist_ok=True)
for f in ['kitguard-native-application-delivery-qa.pdf','kitguard-native-consent-leader-qa.pdf','kitguard-native-consent-member-qa.pdf']:
 shutil.copy2(Path('/tmp')/f,qa/f)
# Update the main entry points while preserving prior factual content.
p=REG/'README_先看提交清单.md';s=p.read_text();shutil.copy2(p,BASE/'报名README_更新前.md')
s=s.replace('三份待签PDF和两份在学证明已集中放好；签字位置及HWP/PDF格式核查结论见该说明。','三份官方原表填写的待签HWP和两份原始在学证明PDF已集中放好；签字位置见该说明。')
s=s.replace('申请书使用05目录的地址已补版，01目录只继续使用两份个人同意书。','申请书和个人同意书统一使用“现在签名_해피”中的三份HWP；01、04、05目录保留历史，不用于本次签署。')
a=s.index('## 文件\n');b=s.index('## 最终打包\n',a)
s=s[:a]+'''## 文件

- [申请书及开发计划 HWP](../现在签名_해피/01_해피_참가신청서_개발계획서_서명전.hwp)
- [남청청个人同意书 HWP](../现在签名_해피/02_참가자_동의서_남청청_선택서명전.hwp)
- [이개심个人同意书 HWP](../现在签名_해피/03_참가자_동의서_이개심_선택서명전.hwp)
- [남청청在学证明 PDF](../现在签名_해피/04_재학증명서_남청청.pdf)
- [이개심在学证明 PDF](../现在签名_해피/05_재학증명서_이개심.pdf)
- [网页字段填写对照](03_填写说明/网页表单逐项填写.md)
- [官方r1原始空表，仅供核对](03_填写说明/官方r1原始空表_仅供核对.hwp)

2026年9月28日已直接填写官方原生HWP，保留原表的字段、表格和官方条款。三份都通过Hancom实际打开与打印核验，页数为4、2、2。申请书第4页签署，两份同意书各在第2页签署。原DOCX和重排PDF保留历史，不作为当前主文件。个人同意书中的已填姓名只是打印姓名，不等同本人签名。

'''+s[b:]
s=s.replace('01_해피_참가신청서_개발계획서_서명본.pdf','01_해피_참가신청서_개발계획서_서명본.hwp').replace('02_참가자_동의서_남청청_서명본.pdf','02_참가자_동의서_남청청_서명본.hwp').replace('03_참가자_동의서_이개심_서명본.pdf','03_참가자_동의서_이개심_서명본.hwp')
s=s.replace('可另附申请书可编辑版，但公开要求没有明确强制指定ZIP内部只能HWP或PDF。','三份表格按用户要求保留官方HWP格式；两份证明维持收到的PDF格式。')
s=s.replace('9月28日已在9月27日版基础上仅补齐两处地址，全部四页排版已检查；申请日期及本人签署仍留空。申请书请用05目录的最新版，9月26日和9月27日版保留历史，不要混用。','9月28日已补齐两处地址，并将现有内容填入官方HWP原表。申请日期、个人同意选择及本人签署仍留空。请用“现在签名_해피”的HWP，历史版本不要混用。')
p.write_text(s)
p=REG/'03_填写说明/20260927_报名操作与缺件清单.md';s=p.read_text();shutil.copy2(p,BASE/'报名操作清单_更新前.md')
a=s.index('申请书更新版：');b=s.index('\n\n## 地址填写结果',a)
s=s[:a]+'''当前统一使用[“现在签名_해피”中的官方HWP填写版](../../现在签名_해피/签名位置与提交格式.md)：申请书4页，两份同意书各2页，均已通过本机Hancom打开与打印核验。原DOCX和重排PDF保留历史，不再用于本次签署。两份在学证明PDF同在该文件夹。如需重新发行证明，学校入口为https://changwon.certpia.com/ 。'''+s[b:]
s=s.replace('保存清晰完整的PDF/扫描件。','以HWP原表完成并保存签署版；打印手签的完整扫描件保留，并将签名嵌回对应HWP。')
p.write_text(s)
p=ROOT/'README.md';s=p.read_text();s=s.replace('已填提供的身份及项目信息；地址、本人同意选择及签章、两人资格证明仍需补齐。','已填身份、地址及项目信息，两份在学证明已归档；[现在签名_해피](现在签名_해피/签名位置与提交格式.md)集中放置三份官方原表填写的HWP和两份证明PDF，仍待本人同意选择及签章。');p.write_text(s)
print('Delivered native HWP files:')
for a in audit:print(DEST/a['file'])
print('Certificate PDFs retained unchanged. Prior PDFs archived; signed-file folder untouched.')
