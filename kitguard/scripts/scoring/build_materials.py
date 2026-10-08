"""Same-version Korean final report and official Agent explanation, with exact evidence."""
from __future__ import annotations

import hashlib
import io
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Image, Paragraph

from kitguard import __version__
from scripts.v08.build_submission_pdfs import (
 A4,
 BOTTOM,
 FONT,
 INK,
 LEFT,
 LINE,
 MUTED,
 RIGHT,
 TEAL,
 TOP,
 WIDTH,
 H,
 Renderer,
 W,
 block,
 inline,
)

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/competition-final-dev4'
SOURCES={'A':'test-results/scoring-v1/GOAL_ACCEPTANCE.json','B':'test-results/scoring-v1/machine-tasks/RESULTS.json',
 'C':'test-results/scoring-v1/all-run.json','D':'test-results/scoring-v1/full-regression.xml',
 'E':'docs/v0.8/LOCO_COMBINED_DECISION.json','F':'docs/v0.7/FINAL_EVALUATION.md',
 'G':'docs/scoring/SOURCE_AI_DISCLOSURE_KO.md','H':'test-results/scoring-v1/official-rules.docx','I':'docs/scoring/CAPACITY.json'}

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')

def facts():
 a=json.loads((ROOT/SOURCES['A']).read_text());b=json.loads((ROOT/SOURCES['B']).read_text());c=json.loads((ROOT/SOURCES['C']).read_text())
 assert a['version']==__version__=='0.9.0.dev4' and a['tests_passed']==1877
 assert b['planned_tasks']==b['workflow_outcomes_met']==5 and b['real_mlx_checks']==4
 assert c['status']=='completed' and c['version']==__version__ and c['planned_checks']==4
 assert all(check['backend']=='mlx' for case in c['cases'] for check in case['checks'])
 xml=ET.parse(ROOT/SOURCES['D']).getroot();t=next(iter(xml)) if xml.tag=='testsuites' else xml
 assert int(t.attrib['tests'])==1877 and int(t.attrib['errors'])==int(t.attrib['failures'])==0
 loco=json.loads((ROOT/SOURCES['E']).read_text());assert loco['outcomes']=={'C':23,'W':0,'U':1,'E':0,'N':0}
 return {'version':__version__,'date':'2026-10-04','tests_passed':1877,'human_participants':0,'physical_completions':0,
 'new_image_accuracy_denominator':0,'machine_tasks':b,'demo':c,'capacity':json.loads((ROOT/SOURCES['I']).read_text()),
 'sources':{k:{'path':v,'sha256':sha(ROOT/v)} for k,v in SOURCES.items()}}

def content(f):
 tasks=f['machine_tasks']['tasks'];demo=f['demo']
 task_names={'quantity':'자료 수량 차이','uncertain':'작은 링 부품 불확실','matching':'현재 BOM 수량 일치','changed_bom':'주문 변경·옛 목표 거절','physical_source':'실물 범위 거절'}
 findings={'quantity_difference':'차이 기록','needs_more_evidence':'추가 자료 요청','quantities_match':'수량 일치 기록'}
 task_rows=[['사전 과제','실제 결과','모델 / 새 목표 실행']]+[[task_names[t['id']],findings.get(t['finding'],'409 정책 거절') if t['id']!='changed_bom' else '옛 목표409 → 새 차이 기록',f"{t['actual_checks']}회 / {t['elapsed_ms']/1000:.3f}초" if t['elapsed_ms'] is not None else '0회 / 시간 N/A'] for t in tasks]
 report=[
 {'title':'KitGuard: 사진·BOM 검토를 맡기는 Agent','kicker':'01  문제·목표·현재 결과','blocks':[
 block('body','팀 해피 / 일반부 / 업무 생산성 향상 AI Agent / 0.9.0.dev4. 사진과 주문 수량표를 각각 전달하면, 주문이 바뀌어도 이전 AI 결과를 현재 결과로 오인할 수 있다. KitGuard는 현재 자료 사진과 BOM을 하나의 목표로 받아 로컬 모델로 비교하고, 차이·불확실성과 사용한 증거를 남긴다.'),
 block('h2','사용자가 지정한 현재 입력에서 시작'),
 block('body','사용자가 로컬 사진과 BOM을 등록한 뒤 자율 검토를 시작한다. Agent는 입력 버전·사진·검사 범위를 고정하고 새 모델 검증을 실행한다. 차이가 있으면 목록으로 남기고, 불확실하면 추가 자료 요청으로 종료한다. AI 관찰로 요구 수량을 임의로 수정하지 않는다. 등록 출처는 사용자 진술로 표시한다.'),
 {'kind':'image','path':'test-results/scoring-v1/recording/all-cases/0030.jpg','height':265},
 block('small','실제 브라우저 실행 중 화면. 왼쪽은 차이, 가운데는 불확실성, 오른쪽은 R2의 새 추론을 기다리는 상태다. 공개 개발 사진의 반복 실행이며 새 이미지 정확도나 사용자 실증이 아니다. [C]'),
 block('callout',f"현존 M5 Pro 64GB만 사용 / 실물 구매·외부 GPU·모집 참여자 0\n사전 고정한 대표 기계 과제5건의 흐름 결과가 모두 충족되었다. 실제 MLX 검증4회와 정책 거절을 구분한다. 별도 3장 자율 시연은 4회 검증, 전체 {demo['elapsed_ms']/1000:.3f}초였다. [A-C]"),
 block('body','대상 사용자 가설은 교육 키트 운영자와 소규모 조립 자료 검토자다. 현재 지원은 나사류·너트·와셔·브래킷 4개 굵은 종류, 종류별 BOM 0-3개이다. 세부 규격·SKU 동일성, 실물 출고와 안전 승인은 지원 근거가 없다. 자체 완성도는 Level3 MVP로 기록한다. 실제 사용자의 반복 효과가 필요한 Level4 Pilot은 미확인이다.')
 ]},
 {'title':'Agent 목표·계획·도구·기억','kicker':'02  실제 구현 구조','blocks':[
 block('h2','규칙 계획과 실제 모델 관찰의 역할'),
 block('table',rows=[['단계','계획과 실제 도구'],['목표 이해','사용자가 고른 현재 사진·BOM·버전·범위를 확정. 네 굵은 종류의 수량 자료 검토라는 범위를 고지'],['계획','입력 검증 → 새 로컬 검증 → 저장된 결과별 분기 → 디지털 증거 ZIP. 공개 R2 연습은 실행 전에 정한 모의 변경'],['관찰·추론','Qwen3.6-27B 4-bit / MLX. 원방향·회전 공간 목록과 조건부 국소 확인. BOM/정답을 관찰 모델에 입력하지 않음'],['도구 실행','FastAPI·SQLite 검사 작업, 사진 계보·SHA 검증, 수량 비교, 명시적 개정·재검사, ZIP·JSON·HTML 내보내기'],['Memory / Feedback','revision·photo SHA·check·epoch·runtime identity 저장. 독립 위치 복검 의견은 원AI와 별도 저장하며 바뀐 입력/의견 후 만료']],widths=[.23,.77]),
 block('h2','세 가지 결과에서 다음 행동 결정'),
 block('table',rows=[['저장된 결과','실행할 행동','보존 경계'],['수량 상이','차이 목록과 현재 BOM 보존','AI 추정으로 주문을 바꾸지 않음'],['불확실·복검 필요','추가 자료 요청','같은 픽셀을 반복해 확정 답을 강요하지 않음'],['네 굵은 종류 일치','현재 수량 일치 기록과 증거 묶음','검증된 정답·SKU 동일성·실물 완료로 승격하지 않음']],widths=[.22,.38,.40]),
 block('callout','자율 실행은 브라우저를 닫아도 지속된다\n새로고침은 저장된 작업을 읽는다. 요청 키 중복은 재실행하지 않고, 서비스 중단은 interrupted와 시간 미상으로 보존한다. 취소는 실제 모델이 끝날 때까지 gate를 유지하고 후속 도구를 중지한다. 실패하면 입력 사진과 실행 오류를 남긴다.'),
 block('body','자율성은 명시적 상태 계획의 자동 실행이다. 자유 형식의 임의 목표 생성이나 독립적인 두 번째 AI 검토자로 설명하지 않는다. 현재 자료 목표에는 R2를 자동 적용하지 않으며 입력이 바뀌면 새 목표를 명시적으로 시작해야 한다. 공개 시연의 R2는 사전에 정한 테스트 계획이다.'),
 block('small','주요 코드: kitguard/autonomy.py, inspection_jobs.py, store.py, public_review.py, digital_review_state.py. 관찰 core4파일은 이전 실측 버전과 바이트 동일하다. [A-C]')
 ]},
 {'title':'대표 기계 과제와 비교 결과','kicker':'03  전체 분모·대조·시간','blocks':[
 block('body','프로토콜 five_machine_goal_tasks_v1을 첫 실행 전에 저장하고 SHA로 고정했다. 공개 개발 사진3장을 사용한5개 과제를 전부 기록했다. 성공 기준은 사전 계획한 분기 또는 거절이며, 사진 정답 정확도와 사람의 업무 효익이 아니다. 작업 입력에는 저자 정답을 넣지 않았다. [B]'),
 block('table',rows=task_rows,widths=[.32,.38,.30]),
 block('h2','동일 모델 결과에서 버전 결합만 제거한 대조'),
 block('body','R1의 2/2/2/0 사진 수량 일치 기록 후, 사전 계획에 따라 요구를 3/2/2/0으로 바꿨다. 버전 결합을 생략하고 최근 검사만 읽는 CPU 대조는 옛 ready를 계속 반환했다. KitGuard의 현재 검사 guard는 옛 검사를 거절했고, 같은 사진의 명시적 디지털 재사용 후 새 실제 검증은 차이를 기록했다. 이 대조는 결합 장치의 작동을 확인하는 기능 제거 실험이다. 독립 모델·시장 서비스와의 성능 대결은 아니다.'),
 block('table',rows=[['관찰 평가 / 분리된 분모','C / W / U / E / N','false-ready'],['기존 공개51장','41 / 3 / 7 / 0 / 0','3/51'],['LOCO 조합24장','23 / 0 / 1 / 0 / 0','0/24'],['이번 기계 과제·시연 반복','새 이미지 분모0','새 정확도 수치 없음']],widths=[.45,.33,.22]),
 block('small','C=정확한 확정, W=잘못 확정, U=불확실, E=실행 오류, N=미시도. LOCO24는 같은 도메인·전체6개·브래킷 양성0의 제한된 조합 자료이며 넓은 현장 신뢰성을 보장하지 않는다. 분모를 합치지 않는다. [E-F]'),
 block('callout','측정한 시간은 서버의 자율 실행 시간\n수락된 목표의 worker 시작부터 종료까지 입력 결합 확인·모델 대기를 포함한다. 사진 등록·개정·재사용 조작은 이 4개 목표 시간에서 제외한다. 새 목표20.213-49.417초이며 사람 시간·비용 절감은 미측정이다. 모델 재실행과 사진 재사용은 새 이미지가 아니다.')
 ]},
 {'title':'실행 안정성·데이터·안전','kicker':'04  경계와 검증','blocks':[
 block('table',rows=[['검증 영역','현재 구현과 확인'],['버전·입력 연결','옛 revision/photo/epoch 목표를409 거절. 변경 전후 새 검사를 구분하고 과거 증거는 역사 기록으로 표시'],['실패 보존','검사 실패에서 사진·BOM·입력 결합과 오류를 ZIP에 남김. 미실행 과제와 계획 분모를 누락하지 않음'],['중복·취소·복구','같은 요청키 재실행 방지, 다른 계획 재사용 거절, 실제 추론 thread 종료까지 gate 유지, 재시작 후 중단 상태 보존'],['내보내기','저장 사진 계보·실제 바이트SHA·manifest 검증. 오프라인 HTML은 원 이미지와 검사·도구 이력을 함께 표시'],['실물 구분','사진 자료는 실물 완료 금지. 자기 사진 출처와 사용권은 user_declared_unverified로 유지']],widths=[.26,.74]),
 block('callout','회귀1,877개 통과 / 현재 목표·실패 입력 계약33개 통과\nHTTP·상태·입력·취소·증거 계약 테스트이다. 합성 관찰 fixture는 실제 MLX와 사람 수·인식 성과로 집계하지 않는다. 실제 기계 과제와 브라우저 시연은 별도 근거에 보존한다. [A-D]'),
 block('h2','로컬 처리와 사용권의 범위'),
 block('body','추론과 저장은 기존 Mac에서 수행하고 서버는127.0.0.1에만 바인딩한다. 입력은 크기를 제한하고 이미지로 정규화해 EXIF를 제거한다. 외부 출처 URL은 설명용 진술이며 서버가 따라가 인증하지 않는다. 소스 ZIP에 모델 가중치·개인 주문DB·사용자 사진을 포함하지 않는다. 증거 ZIP에는 선택한 사진과 주문 내용이 있으므로 받는 대상을 운영자가 결정한다.'),
 block('body','공개 예시는 MVTec LOCO AD/Screws의 CC BY-NC-SA4.0 조건과 출처를 유지한다. 연구·대회 예시이며 상업 고객 자료로 그대로 전용하지 않는다. Qwen/MLX 변환은 저장된 모델 revision·manifest·Apache-2.0 고지를 따른다. 프로그램 SHA는 파일 무결성 확인이지 저자 서명이나 인증된 진실이 아니다.'),
 block('h2','남아 있는 모델 오류'),
 block('body','작은 링 종류, 세부 규격, 가림·빛 변화에 취약하고 브래킷 양성 검증이 부족하다. 같은 모델의 회전/국소 관찰은 상관되어 독립 앙상블이 아니다. 기존51장의 false-ready3건을 숨기지 않는다. 자동 출고·산업 안전·현장 실물 동일성을 보장하지 않는다. 후보 연구 결과가 출시 기준을 넘지 않으면 현재 관찰 코어를 유지한다.')
 ]},
 {'title':'도입 조건·사업 가설·개발 기여','kicker':'05  활용과 제출 준비','blocks':[
 block('h2','현존 장비에서의 도입 경계'),
 block('body','첫 도입 가설은 사진/BOM 한 작업을 검토하는 단일 담당자의 로컬 설치와 업무 양식 설정·유지보수 서비스다. 유료 수요·가격·고객 수·작업시간 절감은 아직 검증하지 않았다. 고객이 권리를 확보한 사진과 적합한 로컬 장비가 필요하다. 구매·계약·현장 검증은 이번 구현 결과가 아니다.'),
 block('table',rows=[['운영 조건','근거 있는 설명'],['설치·실행','소스 ZIP 풀기 → scripts/setup.sh → 별도 모델 설치/경로 확인 → scripts/run_competition.sh. 기존 장비에서 실행하며 가중치는 ZIP에서 제외'],['로컬 처리','한 모델 worker, 대기열0. 처리 중 다른 요청은 명확하게 거절. 장시간·다중 사용자 운영과 권한은 별도 검증 필요'],['가정 용량','4개 실측 단일 목표20.213-49.417초를 그대로 재사용하고 추론 점유50%라 가정하면 시간당36-89건. 사진 등록·검토·휴지시간 제외; 지속 처리 실측이나 SLA 아님'],['비용·수익','이번 신규 실물 구매·외부GPU 호출 없음. 전기·장비 감가·운영비·가격은 미측정이며0원 이익으로 계산하지 않음']],widths=[.24,.76]),
 block('h2','기존 자산과 공식 개발기간의 추가분'),
 block('body','실제 개발은9월26일에 시작했고 공식 개발기간은9월29일-10월6일이다. 기존 사진 관찰·주문·증거 엔진을 재사용했다. 기간 중 비동기 복구·사용자 사진 자료·개정 재검사·독립 위치 복검을 추가했고,10월4일 현재 자료 목표의 자율 실행·실패 입력 보존·5과제 프로토콜과 버전 기능 제거 대조를 구현·검증했다. 기반 VLM을 새 학습하지 않았다.'),
 block('body','OpenAI Codex를 코드·실험·검사·문서·발표자료 제작에 광범위하게 사용했다. 대회 이전 자산과 AI 보조를 공개하며 사람별 작성 비율이나 개발 시작일 코드 스냅샷을 보유했다고 주장하지 않는다. 영상은 실제 브라우저 화면을 시간대로 채집해 만든 기록이며 연속 네이티브 화면 녹화와 구분한다. 모델 기다림을 압축해 처리시간처럼 표시하지 않는다.'),
 block('callout','동일 버전의 최종5종 준비\nA4 보고서5쪽 / AI Agent 기술설명1쪽 / 소스 ZIP / 실제 실행 영상3분 이내 / 발표자료9장. 준비는 제출·접수와 다르다. 공식 제출기한은10월6일12:00 KST. 자체 Level3 MVP, 실제 참여자0명, 새 실물 검증0건.'),
 block('small','근거키: [A]GOAL_ACCEPTANCE [B]machine-tasks/RESULTS [C]all-run [D]full-regression (모두 test-results/scoring-v1). [E]docs/v0.8/LOCO_COMBINED_DECISION [F]docs/v0.7/FINAL_EVALUATION [G]출처·AI 공개 [H]공식 규정 [I]CAPACITY. facts.json에 정확한 경로와 SHA. 공식: contest.gnict.org/bbs/board.php?bo_table=notice&wr_id=5, 10월4일 확인.')
 ]}]
 rows=[['항목','KitGuard / 2026-10-04 / 0.9.0.dev4'],['팀명·부문·주제','해피 / 일반부 / 업무 생산성 향상 AI Agent'],['작품명·문제','사진·BOM 디지털 검토 Agent. 사진/주문 변경 뒤 이전 AI 결과가 현재 결과로 오인될 수 있는 작업'],['대상사용자','교육 키트 운영자·소규모 조립 자료 검토자 (수요 가설)'],['Agent Goal','지정한 현재 사진·BOM을 검토해 차이·불확실성과 버전이 결합된 증거를 보존'],['사용 AI/LLM/모델','Qwen3.6-27B-4bit / MLX / spatial_guarded1536. 기반 VLM 신규학습 없음'],['Tool/API/Data/장비','FastAPI·SQLite·Pillow·로컬 브라우저 / MVTec 공개 개발3장·사용자 선언 자료 / 기존 M5 Pro64GB'],['Memory·State·Feedback','버전·photoSHA·check·epoch·모델 identity 결합. 독립 위치 복검은 AI와 별도. 새 증거 뒤 과거 결과/의견 만료'],['핵심 Workflow','현재 목표 결합 → 새 로컬 관찰 → 저장 결과별 차이/불확실/일치 분기 → 디지털 증거. 공개 예정R2는 옛검사 무효화·동일사진 재사용·새추론'],['핵심기능5개','① 사진/BOM 목표 ② 로컬 수량 검증 ③ 자율 분기 ④ 버전·의견 최신성/독립 복검 ⑤ 실패 입력 포함 증거 ZIP'],['기존자산·기간 신규','9/26 관찰·주문 엔진 재사용. 공식9/29-10/6 중 비동기 복구·사진 자료·개정·위치 복검. 10/4 현재 목표 자율 실행·실패 입력·5과제 대조'],['대표 테스트5건','① 수량 차이20.213초 ② 불확실21.739초 ③ 일치48.628초 ④ 옛 목표409·새 차이49.417초 ⑤ 실물범위409·모델0회. 기계 과제, 사람0명'],['현재 완성도','자가평가 Level3 MVP. 실제 고객·현장 반복 효과 미검증'],['소스코드·실행','KitGuard_source_v0.9_dev4.zip / bash scripts/run_competition.sh. 가중치 별도, 저장 모델 고지 준수'],['출처·오류·AI 보조','MVTec CC BY-NC-SA4.0. Codex 코드·실험·자료 보조 공개. 회귀1877통과, 기존51 C41/W3/U7/AFR3. LOCO24 C23/W0/U1 별도 분모'],['추가 정보','기계5과제/실제MLX4회와 3사진자율시연/MLX4회를 분리. 새이미지 정확도분모0, 실물 완료0. 사용자 선언 출처 미인증']]
 technical=[{'title':'AI Agent 기술설명서','kicker':'별지1  공식 항목 대응','blocks':[block('table',rows=rows,widths=[.26,.74]),block('small','실물 완료·SKU 동일성·인증된 정답과 구분한다. 자동 목표는 입력이 바뀌면 새로 시작하며 임의 BOM 변경을 하지 않는다. 공식 항목에 대응한 제출 준비본, 대회 접수 결과가 아니다.')]}]
 return report,technical

class FinalRenderer(Renderer):
 def flow(self,item):
  if item['kind']=='image':
   from PIL import Image as PILImage
   source=ROOT/item['path'];w,h=PILImage.open(source).size;scale=min(WIDTH/w,item['height']/h)
   return Image(str(source),width=w*scale,height=h*scale),7
  return super().flow(item)
 def render(self,pages,destination):
  assert len(pages)<=(1 if self.technical else 5)
  stream=io.BytesIO();pdf=canvas.Canvas(stream,pagesize=A4,pageCompression=1,invariant=1);pdf.setTitle('KitGuard AI Agent 기술설명서' if self.technical else 'KitGuard 결과보고서');pdf.setAuthor('해피 / AI-assisted');layout=[]
  for n,page in enumerate(pages,1):
   pdf.setFillColor(TEAL);pdf.rect(LEFT,H-32,25,3,fill=1,stroke=0);pdf.setFont('KR',8);pdf.setFillColor(MUTED);pdf.drawString(LEFT+34,H-33,'KITGUARD / '+page['kicker'])
   title=Paragraph(inline(page['title']),ParagraphStyle('title',fontName='KR',fontSize=20 if self.technical else 23,leading=30,wordWrap='CJK',textColor=INK));_,h=title.wrap(WIDTH,100);title.drawOn(pdf,LEFT,TOP-h);y=TOP-h-14
   for item in page['blocks']:
    flow,gap=self.flow(item);w,h=flow.wrapOn(pdf,WIDTH,TOP-BOTTOM)
    if w>WIDTH+.1 or y-h<BOTTOM:raise ValueError(f'Overflow {destination.name} p{n} {item["kind"]} {y-h:.1f}')
    flow.drawOn(pdf,LEFT,y-h);y-=h+gap
   pdf.setStrokeColor(LINE);pdf.line(LEFT,37,W-RIGHT,37);pdf.setFont('KR',7.8);pdf.setFillColor(MUTED);pdf.drawString(LEFT,24,__version__+' / 2026-10-04 / 해피 / 제출 전 검토본');pdf.drawRightString(W-RIGHT,24,f'{n} / {len(pages)}');layout.append({'page':n,'bottom':y});pdf.showPage()
  pdf.save();destination.write_bytes(stream.getvalue());assert len(PdfReader(destination).pages)==len(pages)
  return {'path':destination.name,'pages':len(pages),'sha256':sha(destination),'layout':layout}

def main():
 OUT.mkdir(parents=True,exist_ok=True);f=facts();save(OUT/'facts.json',f)
 pdfmetrics.registerFont(TTFont('KR',str(FONT)));pdfmetrics.registerFontFamily('KR',normal='KR',bold='KR',italic='KR',boldItalic='KR')
 report,technical=content(f);save(OUT/'content-source.json',{'report':report,'technical':technical});docs=[]
 for pages,name,tech in [(report,'KitGuard_report_5p.pdf',False),(technical,'KitGuard_agent_1p.pdf',True)]:docs.append(FinalRenderer(__version__,tech).render(pages,OUT/name))
 save(OUT/'pdf-build.json',{'documents':docs,'builder_sha256':sha(__file__),'visual_qa':'pending'});print(json.dumps(docs,ensure_ascii=False))
if __name__=='__main__':main()
