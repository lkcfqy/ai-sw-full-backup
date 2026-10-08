from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree as E
import json, hashlib
ROOT=Path(__file__).resolve().parents[2]
old=ROOT/'01_待补地址与签字/01_해피_참가신청서_개발계획서_주소서명전.docx'
out=ROOT/'04_20260927更新_仍待补地址签字'
out.mkdir(exist_ok=True)
new=out/'01_해피_참가신청서_개발계획서_20260927_주소서명전.docx'
assert not new.exists()
data=json.loads((ROOT/'工作文件/报名字段正文.json').read_text())
updates={
'intro_purpose':'소량·다품종 키팅에서는 주문 변경을 놓치거나 배경 고정물을 대상에 포함하면 부품 수량과 완료 판단이 어긋날 수 있다. KitGuard는 주문 버전, 작업자가 선언한 검사 범위, 사진 증거를 연결하여 부품 확인과 최종 실물 확인을 지원하는 탁상형 AI Agent이다.',
'intro_content':'사전 연구에서는 로컬 시각 모델의 물체 목록을 프로그램이 수량으로 계산하고, 주문과 비교하며, 불확실하면 재촬영을 요청하는 흐름을 구현·시험했다. 검사 영역을 바꿀 때 전체 사진과 좌표를 보존하고 이전 결과를 무효화한다. 같은 사진의 재선택을 새 촬영으로 세지 않으며, 실물 완료에는 작업자의 별도 확인이 필요하다.',
'intro_effect':'볼트·너트·와셔·L형 브래킷 4종, 품목별 주문 0~3개, 총 12개 이하를 다룬다. 실제 작업자·새 실물 사진의 검증은 아직 수행하지 않았다. 공식 기간에는 주최 측이 허용하는 개발 범위 안에서 현장 사진 과제의 오류·보류·실패와 사용성을 검증하고, 범위 누락과 적용 한계를 공개할 계획이다.',
'method':'사전 연구용 코드·공개 데이터 시험은 2026.9.26부터 진행했다. 개발기간 외 사전 개발 관련 동의 조항의 적용을 주최 측에 확인한 뒤, 허용되는 기존 자산과 공식 기간 신규 구현을 구분한다. 기존 결과를 공식 기간 신규 성과로 기재하지 않는다. 주문·사진 범위·모델 결과를 연결하고 증거 변경 시 재검증하도록 구성한다.',
'schedule':'9.29 설명회와 사전 개발 허용 범위를 확인하고 신규 작업 및 평가 계획을 확정한다. 9.30~10.2 새 실물 사진 수집·범위 선택·오류 대응을 검증한다. 10.3~4 허용 범위의 수정과 분리된 사례 재검증을 수행한다. 10.5 보고서·기술설명서·발표·영상·소스를 정리하고 10.6 12:00 전 제출한다.',
'methodology':'기존 공개 이미지 실험과 새 실물 시험을 별도로 보고한다. 새 시험은 확보 가능한 실물 부품과 참여자를 먼저 확인하고 12사례를 초기 목표로 사전 등록한다. 각 사례의 실제 수량을 재확인하고 주문·사진·범위를 동결한 뒤 수기 사진 계수와 AI 결과를 기록한다. 같은 사진의 여러 영역을 독립 사례로 늘리지 않고 실패·보류·미시작을 남긴다. 실제 참여 인원은 그대로 보고한다.',
'targets':'신규 검증 목표는 변경된 주문·사진 범위에 이전 결과를 사용한 완료 처리 0건, 예정 사례의 누락 없는 기록, 수량 정답·명확한 오답·불확실·실행 실패의 분리 보고이다. 이는 목표이며 현장 실측 성과가 아니다. 수기 선행의 고정 순서와 사진 선택 사전 노출 때문에 시간 차이를 인과적 생산성 향상으로 주장하지 않는다.',
'as_is':'비교 기준은 사람이 같은 주문과 동결된 사진 범위를 보고 수량을 기록하는 방식이다. 실제 공장 전체 업무의 시간·비용을 대표한다고 가정하지 않는다.',
'to_be':'주문 버전과 범위를 확인하고 AI 관찰을 프로그램 수량 비교에 사용한다. 근거가 부족하면 보완을 요구하고, 전체 사진·선택 영역·실제 입력과 결과를 함께 내보내어 사후 확인할 수 있게 한다.',
'other':'현재 사전 연구 실행 환경은 MacBook Pro M5 Pro 64 GB, Qwen3.6-27B 4-bit/MLX-VLM이다. RTX 3080 장비는 아직 연결·검증하지 않았다. 신규 학습·치수·나사산·재질 판정·생산설비 제어는 제외한다. Codex, 모델·데이터 출처, 실제 개발일과 변경 내역을 공개하고 기존 자료 사용은 주최 측 지침에 따른다.'}
# Correct Korean spelling, without inventing a participant or result.
updates['methodology']=updates['methodology'].replace('물료','물료')
repl={data[k]:v for k,v in updates.items()}
repl.update({
'□ 국내 LLM  ■ 기타: Qwen3-VL-8B/4B-Instruct':'□ 국내 LLM  ■ 기타: Qwen3.6-27B 4-bit',
'로컬 후보 비교 후 고정, 신규 학습 없음.':'MLX-VLM 로컬 추론, 신규 학습 없음.',
'MacBook Pro M5 Pro 64 GB 단독 실행 목표.':'MacBook Pro M5 Pro 64 GB 사전 연구 실행.',
'RTX 3080 10 GB 데스크톱은 비교 평가·예비 추론.':'RTX 3080 데스크톱은 미연결·미검증.',
'AI 모델과 환경은 개발용 자료로 평가한 뒤 고정하며, 실제 성능과 오프라인 실행 여부는 개발 기간에 검증한다.':'사전 연구와 공식 기간 신규 개발을 구분하며, 기존 자산 사용은 주최 측 확인 후 정한다.'})
repl={k:v.replace('물료','물료') for k,v in repl.items()}
ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
with ZipFile(old) as z:
 records={n:z.read(n) for n in z.namelist()}
r=E.fromstring(records['word/document.xml']);seen=set()
for n in r.findall('.//w:t',ns):
 if n.text in repl:
  seen.add(n.text);n.text=repl[n.text]
assert seen==set(repl),(set(repl)-seen)
# Keep original section, tables, typography, personal fields and official conditions.
records['word/document.xml']=E.tostring(r,xml_declaration=True,encoding='UTF-8',standalone=True)
with ZipFile(new,'x',ZIP_DEFLATED) as z:
 for n,b in records.items():z.writestr(n,b)
with ZipFile(old) as a,ZipFile(new) as b:
 assert set(a.namelist())==set(b.namelist())
 assert all(a.read(n)==b.read(n) for n in a.namelist() if n!='word/document.xml')
 assert b.testzip() is None
alltext=''.join(r.itertext());assert 'Qwen3-VL-8B' not in alltext and '2026.9.26' in alltext
assert '[팀장 상세 주소 입력]' in alltext and '[거주 시·군 입력]' in alltext
report={'source':str(old),'output':str(new),'source_sha256':hashlib.sha256(old.read_bytes()).hexdigest(),'output_sha256':hashlib.sha256(new.read_bytes()).hexdigest(),'replaced_slots':len(seen),'unchanged_other_package_parts':True,'addresses_and_signatures_missing':True,'organizer_predevelopment_and_leader_eligibility_confirmation_required':True}
Path(__file__).with_name('document-update.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
Path(__file__).with_name('updated-plan-fields.json').write_text(json.dumps(updates,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False))
