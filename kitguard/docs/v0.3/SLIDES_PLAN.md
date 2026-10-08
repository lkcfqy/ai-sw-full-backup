# KitGuard v0.3 검증 보충 발표 계획

기존 9장 v0.2 발표를 수정하지 않는 **6장 기술·검증 보충 자료**이다. 이 계획은 새로운 평가 결과가 나오기 전에 작성했다. 현재 준비 단계에서는 완료한 개발 28장의 스키마만 확인하며, 진행 중인 64장의 부분 예측이나 사진은 읽지 않는다.

### 완료 자료 업데이트

새 평가가 전체 완료된 뒤 `evaluation-runs/v03_guarded_holdout_v1/gate_report_v1.json`과 `test-results/audit/v03-guarded-holdout-analysis.json`을 읽기 전용 검증했다. 사진은 열지 않았다. 최종 C/W/U/E는 **59/0/5/0**, 같은 실행의 첫 관찰은 **62/2/0/0**이다. 첫 관찰 오류 2건을 차단했으며 정확했던 3건도 보류했다. LOCO 정상 16/0/0/0, LOCO 수량 이상 15/0/1/0, Screws 28/0/4/0이다. `counts_exact` 역시 59장이며 근거 없는 60장 값은 사용하지 않는다. 연구 게이트와 채택 조건은 통과했고 root의 실제 채택 모드는 `spatial_guarded`이다. 전체 통합 지연 중앙값은 40.5795초이며 독립 API 검사 요청 시간과 구분한다.

게이트 SHA-256: `8f8fa784b9abca802ffab08e1fc8b23efd75407a2ede9cc235c3496b442f599f`.
독립 감사 SHA-256: `76a878c1b75fc09dcbaf4ae5d3139c97f46cfdc859c8c0200f0014215c5b3408`.

실제 API 시연 v1은 UI 자동화의 응답 읽기 단계에서 중단되었고 모델 요청은 0회였다. 실패 기록을 보존하며 발표의 성공 자료로 쓰지 않는다. v2의 전체 회수 기록과 실제 스크린샷을 받은 뒤 최종 생성한다.

## 페이지 구성

| 장 | 핵심 질문 | 표현과 근거 |
|---|---|---|
| 1 | 실제 업무에서 무엇이 달라지는가? | 목표와 관찰 분리, 불확실할 때 재확인, 버전과 증거 보존. 실제 API 감사 화면 한 장. 시간 절감은 미측정으로 유지. |
| 2 | 왜 모델 답변만 보여주는 도구가 아닌가? | BOM을 숨긴 공간 목록, 디지털 회전 일치, 국소 정체 확인, 규칙 비교를 편집 가능한 구조로 설명. 같은 모델의 관련된 호출이며 정수 수정 없이 null만 추가한다. |
| 3 | 정확도와 보류의 대가는 무엇인가? | 완료 개발 28장과 새 평가 64장의 그룹별 C/W/U/E. 같은 실행의 실제 첫 관찰과 최종 결과를 대응 비교. 확정 비율과 통합 지연을 병기한다. |
| 4 | 실패한 실험을 숨겼는가? | OWLv2, Grounding DINO, 초기 정체 확인 v1을 남긴다. 개발 단계의 탐지기 정확도와 업무 지표를 혼합하지 않는다. 고정 게이트와 실제 채택 모드를 구분한다. |
| 5 | 실제로 동작하는가? | 실제 한국어 API 작업 화면을 통째로 크게 표시. 공학 테스트는 XML에서 계산. 시각 검사 4회와 자연어 요청 1회를 따로 기록한다. R1, 제안, 승인, R2, 같은 사진 재업로드의 범위를 설명한다. |
| 6 | 다음에 무엇을 증명해야 하는가? | 새 현장 사진, 실제 부품 수정 전후, 작업자 시간·오류 비교. 브래킷 양성·다른 공장 일반화·사전학습 중복 한계를 밝힌다. 실제 개발일과 자격 확인 대기를 보존한다. |

C = 정확한 확정 수량, W = 틀린 확정 수량, U = 불확실·보류, E = 실행 오류. 이 네 항목은 사진 분모를 분할한다. U/E를 제외해 정확도만 높이지 않는다. 첫 관찰에는 별도 전체 지연이 없으며, 모델 호출 시간·CPU 탐지기 시간·과거 결과 재생의 합산 시간을 통합 API 지연과 비교하지 않는다.

## 생성 입력과 거부 조건

생성기: `scripts/build_v03_slides.mjs`. 데이터 검증은 `scripts/build_v03_korean_addendum.py`의 읽기 전용 `load_bundle`를 재사용하고 개발 독립 감사·언어 호출·실제 HTTP 본문 해시를 추가 확인한다. 다음이 없거나 일치하지 않으면 PPT를 만들지 않는다.

- 개발 28장 및 새 평가 64장의 `complete: true` 게이트와 완료된 원본 run, predictions, manifest 해시
- 같은 실행을 가리키는 독립 감사, 스키마 전체 재검증과 입력 재현 성공
- 4개 시각 요청과 1개 자연어 요청의 완료된 실제 API 회수 기록, 변경 없는 소스
- 자연어 `instruction_outcome`과 명시적 승인. 자연어 실패·명확화 후 구조화 입력을 쓴 경우 해당 fallback을 그대로 표시
- 실제 실행 디렉터리에 존재하는 서로 다른 PNG 스크린샷 2개
- 완료 공학 회귀 JUnit XML 및 실제 채택 모드

`completed_with_execution_errors`는 완료한 실패 증거로 보존할 수 있지만, 성공이나 정확도로 바꾸지 않는다. 강화 모드를 기본값으로 썼다고 표시하려면 연구 게이트의 `default_adoption_eligible`도 true여야 한다. 게이트 통과 자체는 현장 안전, 출하 또는 대회 우승 보증이 아니다.

## CLI

먼저 GPU를 사용하지 않는 완료 개발 입력 점검:

```sh
/Users/lkc/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node scripts/build_v03_slides.mjs --development-only
```

최종 파일이 모두 나온 뒤 명시적 경로로 실행한다. 아래 대괄호 항목은 실제 완료 파일 경로로 채우며 더미 파일을 만들지 않는다.

```text
node scripts/build_v03_slides.mjs
  --gate [completed holdout gate]
  --audit [completed independent holdout audit]
  --demo-receipt [actual browser/result.json]
  --engineering-junit [completed regression XML]
  --deployment-mode [actual selected mode]
  --validate-only
```

동일 인수에서 `--validate-only`를 제거하면 최종 PPT를 생성한다. 기본 파일은 `output/presentations/KitGuard_검증보충_v0.3.pptx`, 작업·검증 폴더는 `.presentation-v03-build/final-v1/`이다. 기존 최종 파일은 덮어쓰지 않는다. 필요하면 `--output` 및 `--build-dir`에 새 버전을 지정한다.

## 제작·검증 계약

Presentations SKILL 전체, implementation, finalization, native evidence 및 table API를 읽었다. 생성 작업 시작 marker를 authoring 전에 한 번 성공 호출했다. 생성기는 중복 호출하지 않는다. JS ES module과 `@oai/artifact-tool`만 사용하며, python-pptx는 사용하지 않는다. 16:9, 한국어 Apple SD Gothic Neo, v0.2와 연결되는 짙은 녹색·밝은 배경의 단순한 구성이다. 표와 구조는 편집 가능하며 화면 캡처는 원본 비율을 유지한다. 인용과 소스 SHA는 발표자 노트와 별도 sources.json에 보존한다.

최종화 때 총 6장, 3/4/6장 native table, 폰트·패키지·레이아웃·ArtifactTool 재가져오기를 검사한다. 이후 **최종 PPT 전체 페이지를 렌더하고 각 페이지를 실제로 열어** 한글 줄바꿈, 여백, 겹침, 표 숫자, 스크린샷 가독성을 확인한다. contact sheet만으로 완료를 선언하지 않는다. 실제 PowerPoint에서 열지 않았다면 PowerPoint 실행 검증을 주장하지 않는다. QA 완료 전에는 최종 제출 준비 완료로 표시하지 않는다.

공개 사진은 MVTec 원본·보수적 파생 자료이며 CC BY-NC-SA 4.0을 명시한다. 동일 사진의 재업로드를 새 현장 사진이나 실제 부품 수정으로 표현하지 않는다. 개인 연락처는 포함하지 않는다. 상세 공식 점수표나 우승 확률을 만들지 않는다.

## 최종 결과

`output/presentations/KitGuard_검증보충_v0.3.pptx`를 6장으로 생성했다. SHA-256은 `4cfe783b4ce5561c35df087558639abfd33f4f51bc75685ed5f6e935e2502c26`이다. 실제 제작 입력은 완료한 candidate-real-api-v2의 `browser/result.json`, `test-results/engineering-v03-final.xml`의 428/428, 완료 개발·평가 게이트와 독립 감사이다. 발표에 사용한 두 화면은 `bag-revision-r1-workspace.png`와 `bag-revision-r2-audit.png`이며 두 원본을 먼저 열어 확인했다.

최종 PPT를 ArtifactTool로 다시 가져온 뒤 6장 모두 1920×1080으로 렌더하고 페이지별로 직접 확인했다. 첫 시각 검토에서 한국어 문구와 페이지 하단 간격을 정리했고 이전 파일을 `.presentation-v03-build/final-v2/pre-visual-repair.pptx`에 보존했다. 최종 작업 폴더는 `.presentation-v03-build/final-v3/`, 확인 기록은 `output/presentations/qa-v0.3/`이다. 소스와 검증기에는 실패한 입력을 거부하는 경로가 있으며 미완료 v1 실록을 성공 자료로 사용하지 않았다.

ArtifactTool finalizer는 6장, native table 3개, 폰트·패키지·레이아웃 및 재가져오기 검사에서 findings/warnings 0을 기록했다. 정수 벡터 셀의 합은 native 단순 산술 검사가 자동으로 해석하지 못하므로 소스 게이트 검증과 실제 표시값 대조로 확인했다. PowerPoint/Google Slides를 직접 열어 검사하지 않았고 LibreOffice는 사용하지 않았다.

최종 사용자 전달에서는 지원 시 PPT를 한 번만 `:codex-file-citation{path="/Users/lkc/Downloads/AI·SW/kitguard/output/presentations/KitGuard_검증보충_v0.3.pptx" purpose="output"}`로 링크한다. 미지원 시 일반 파일 링크를 사용한다. 임시 파일을 전달하거나 일상적인 검증 내역을 전부 나열할 필요는 없으며, 사용에 영향을 주는 범위와 한계는 설명한다.
