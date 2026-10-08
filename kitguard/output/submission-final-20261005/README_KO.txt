KitGuard 최종 제출 자료
해피 팀 / 남청청(팀장), 이개심(팀원)
일반부 / 업무혁신·생산성 향상 AI Agent
코드 0.9.0.dev4 / 최종 자료 정리 2026-10-05

START_HERE.html을 열면 제출물과 검증 자료를 읽을 수 있습니다.

필수 제출물 5종
1. KitGuard_report_5p.pdf: 개발완료보고서, A4 5쪽
2. KitGuard_agent_1p.pdf: AI Agent 기술설명서, 1쪽
3. KitGuard_source.zip: 실행 가능한 소스와 공개 개발 사진 3장
4. KitGuard_demo_ko.mp4: 실제 실행 영상, 177.42초
5. KitGuard_presentation_9slides.pptx: 발표자료, 9장

추가 자료
KitGuard_presentation_9slides.pdf는 발표자료의 동일 내용 열람본입니다.
SOURCE_AI_DISCLOSURE_KO.txt에는 기존 자산·공식 기간 추가분·AI 도움·출처와 조건을 공개합니다.
KitGuard_execution_evidence.zip은 제출 영상에 대응하는 기존 실제 실행 증거입니다.
KitGuard_final_runtime_evidence.zip은 10월5일 최종 재실행의 전체 사진·BOM·검사·도구 이력입니다.
각 증거 ZIP은 압축을 푼 뒤 index.html을 열면 서버 없이 읽을 수 있습니다.
FINAL_ACCEPTANCE.json과 SUBMISSION_MANIFEST.json은 검사 범위와 파일 SHA-256을 기록합니다.

작품에서 볼 수 있는 동작
사용자가 현재 사진과 BOM의 검토를 맡깁니다. 목표는 주문·버전·사진에 결합됩니다.
로컬 VLM이 실제 사진을 관찰하고, 프로그램은 수량 차이·추가 자료·현재 수량 일치로 분기합니다.
주문이 바뀌면 기존 결과는 만료되고, 같은 사진을 디지털 재사용하더라도 새 검사를 실행합니다.
입력과 실패, 원래 AI 결과를 보존하고 오프라인 증거로 내보냅니다.

소스 실행
1. KitGuard_source.zip을 해제하고 KitGuard/SOURCE_PACKAGE.md를 읽습니다.
2. 확인한 실행 환경은 Apple Silicon macOS, Python 3.12, M5 Pro 64GB입니다.
3. KitGuard 폴더에서 bash scripts/setup.sh를 실행합니다. 최초 의존성 설치는 인터넷이 필요합니다.
4. .venv/bin/python scripts/download_candidate_model.py로 고정 모델을 설치하거나 기존 모델의
   절대 경로를 KITGUARD_MODEL_PATH에 지정합니다. 가중치 약16GB는 소스에 포함하지 않습니다.
5. bash scripts/run_competition.sh를 실행하고 http://127.0.0.1:8765/static/autonomy.html을 엽니다.
6. 전체 3개 시나리오를 시작합니다. 준비된 환경에서는 인터넷 없이 실제 추론합니다.
   하나의 서비스와 하나의 모델 worker를 사용하고, 첫 로드는 기다려 주십시오.
7. 자신의 사진/BOM은 홈페이지 자료 주문에 등록하고 현재 주문의 자율 검토를 시작합니다.
   공개 자료/사진의 실행은 실물 출고나 실물 완료를 승인하지 않습니다.

결과 해석
5개 사전 기계 과제의 분기/거절 확인과 사진 정확도를 구분합니다.
기존 51장 결과는 41 정확, 3 오류, 7 미확정입니다. LOCO24는 같은 공개 도메인에서 따로
고정한 제한된 평가집합이며 23 정확, 0 오류, 1 미확정입니다. 두 분모를 합치지 않습니다.
10월5일 최종 점검은 같은 개발 사진 3장으로 4회 실제 MLX 검사, 135.542초를 기록했습니다.
새 정확도 분모는 0, 실제 참가 사용자와 실물 완료는 0입니다.
영상을 시간대로 채집한 실제 브라우저 화면으로 만들었고 모델 기다림을 보존했습니다.
음성은 합성 한국어이며, 연속 네이티브 녹화라고 주장하지 않습니다.
MVTec 사진의 CC BY-NC-SA 4.0 조건을 유지합니다. 상업 고객 자료 사용권은 별도로 확보해야 합니다.

이 자료는 로컬 제출 준비본입니다. 공식 접수, 자격 승인, 점수 또는 순위를 증명하지 않습니다.
