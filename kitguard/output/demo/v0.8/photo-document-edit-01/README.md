# KitGuard · 0.8.0.dev1 preview · 실제 실행 화면 편집

135초 / 1920×1080 / 한국어 설명 / 무음. API의 실제 MLX 실행 기록과 이후 읽기 전용 Chrome 정지 화면을 편집한 영상입니다. 연속 화면 녹화나 실제 사용자 시험이 아닙니다. 실제 사용자 0명이며 두 의견은 ENGINEERING-AGENT의 자동화 공학 기록입니다.

기존 사진의 R1 요구와 관찰 차이 → 사전 설정한 API 요구 변경 → 같은 사진에서 R2 새 관찰 → 디지털 의견 이력 → 실제 ZIP 다운로드 증빙을 설명합니다. 실물 보충·새 촬영·출고를 뜻하지 않습니다. 파일 선택창과 file:// 오프라인 화면의 시각 검증은 권한 제한으로 완료하지 못했습니다. API 업로드, 저장 이력, 실제 다운로드와 CPU 구조 검증의 범위를 구분합니다.

- `EDIT_PLAN.json`: 표시된 한국어 문구와 6개 구간.
- `SOURCE_INDEX.json`: 5개 원본 캡처 및 API/browser JSON의 원래 경로, SHA-256, 범위.
- `source-json/`와 `SOURCE_JSON_COPIES.json`: 기존 API/browser JSON의 동일 바이트 복사. 새 모델 결과가 아닙니다.
- `TIMELINE.json`, `scenes/`: 개별 영상 레이어와 타임라인. 원본 캡처는 변경하지 않았습니다.
- `commands.jsonl`, `*-version.log`, `ffmpeg-license.log`: 로컬 FFmpeg 명령·버전·라이선스. 도구 바이너리와 시스템 글꼴은 배포하지 않습니다.
- `receipt.json`: 실제 인코딩, 전체 디코딩, 길이, 오디오, 추출 프레임 검증.
- 최종 별도 시각 QA와 독립 심사 회신은 해당 JSON으로 기록하며 중간 준비/인코딩 회신을 덮어쓰지 않습니다.

사진 출처: MVTec LOCO AD `screw_bag/train/good/016.png`, https://www.mvtec.com/research-teaching/datasets/mvtec-loco-ad ; CC BY-NC-SA 4.0 https://creativecommons.org/licenses/by-nc-sa/4.0/ . 앱에 저장된 출처는 사용자 신고이며 인증된 출처로 승격하지 않았습니다. 영상은 원본 UI 화면을 비례 축소하고 별도의 자막과 사실 카드를 더한 편집입니다.

재생성은 저장소 루트에서 새 출력 경로를 지정합니다. 준비 후 동료 심사는 그 PREPARATION.json SHA에 새로 결합해야 하며, 기존 결과를 덮어쓸 수 없습니다.

```sh
.venv/bin/python scripts/v08/build_demo_video.py prepare --output output/demo/v0.8/NEW_NAME
.venv/bin/python scripts/v08/build_demo_video.py encode --output output/demo/v0.8/NEW_NAME --approval PATH_TO_NEW_PEER_APPROVAL.json
```

기존 `source-json/` 복사는 원본 JSON 보존 편의를 위한 별도 패키징 단계이며 영상 빌더의 입력은 SOURCE_INDEX에 지정한 기존 원본입니다.

최종 인코딩 길이는 135.0초입니다. 24fps 변환 과정에서 다섯 장면 경계가 명목 시각보다 한 프레임(약41.7ms) 빠르며, 자막과 화면은 함께 전환됩니다. `ENCODED_TIMELINE.json`과 `qa-exact/`, `qa-boundary-before/`에 실제 디코딩 프레임 경계가 기록되어 있습니다. 이는 편집 경계의 양자화이며 표시된 API 추론 시간과 무관합니다.
