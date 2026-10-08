# KitGuard 출처·AI 활용 신고 내용 초안

2026-10-02 12:07 KST 기준. 팀 **해피**, 작품 **KitGuard**, 작업 버전 **0.8.0.dev1**. 공식 별지2 서식을 아직 확보하지 못했으므로 이 문서는 **전사 가능한 신고 내용**이며 공식 서식·서명·제출 완료를 뜻하지 않는다. 이후 연구와 제출 시점의 사용 내역은 추가해야 한다.

## 개발 기간과 팀의 기여

원형은 **2026-09-26**부터 개발했다. 공식 개발기간은 **2026-09-29–10-06**이다. 공식 교육자료 4·29쪽의 기존 자산 활용 안내에 따라 선행 코드·모델·데이터와 대회 기간의 개선을 구분해 신고한다. [공식 근거 보완](OFFICIAL_RULE_CLARIFICATION_20261002.md)을 함께 보관한다.

개발 기록상의 날짜에 따라 다음처럼 구분한다. 정확한 대회 시작일 코드 스냅샷이나 사람별 작성 비율을 보유했다고 주장하지 않는다.

- **9월26–27일 기존 자산:** 로컬 사진 정규화, 공간 관찰·회전·국소 확인, 주문 상태와 수량 판정, 증거 저장·내보내기, 검사 범위 선택 및 앞선 검증 도구. [v0.3 기록](../v0.3/DEVELOPMENT_RECORD.md), [v0.5 기록](../v0.5/FINAL_EVALUATION.md)에 날짜를 보존한다. 검사 범위 선택을 대회 기간의 신규 기능으로 다시 신고하지 않는다.
- **9월30일–10월1일 추가:** 검출기 지도학습·별도 검증대, 비동기 검사·복구 등. [v0.6 개발 기록](../v0.6/DEVELOPMENT_PREVIEW.md)과 [10월1일 검증 기록](../v0.6/SOFTWARE_ACCEPTANCE_20261001.md)을 따른다.
- **10월2일 추가:** 공개 사진의 디지털 의견, 주문 개정 후 같은 사진의 명시적 재사용·새 추론·이력 무효화, 출처가 연결된 자료 주문, 검사 단계의 실제 참고 입력 추적, 관련 검증·포장 도구와 비교 실험. [v0.7 기여 내역](../v0.7/CONTEST_PERIOD_CONTRIBUTIONS.md), [v0.8 연속 기록](CONTINUATION_20261002.md)에 근거한다. 원래 증거 ZIP 기능 자체를 새 기능으로 다시 계산하지 않는다.

10월2일 앞선 봉인 v0.7과 현재 핵심 앱을 비교하면 **58경로 중 신규2·수정21·동일35·삭제0**이다. 신규는 `photo_documents.py`, `photo-documents.js`이다. 이는 대회 시작일과의 비교가 아니다. [파일별 차이](CONTRIBUTION_DIFF_FROM_SEALED_V07.json), [추가 기능 설명](CONTEST_PERIOD_CONTRIBUTIONS.md)을 참조한다.

## AI 도구와 모델

| 자산·원출처 | 실제 사용 | 버전·조건 및 주장 범위 |
|---|---|---|
| OpenAI Codex | 팀 지시에 따라 코드 생성·수정, 테스트, 실험 구현·검토, 문서·한국어 자료·영상 스크립트 작성 | 여러 에이전트의 검토도 AI 보조이다. 전부 팀원이 한 줄씩 직접 작성했다거나 사람이 평가에 참여했다고 주장하지 않는다. 개발 보조 서비스와 로컬 제품 추론은 별개이다. |
| [Qwen3.6-27B](https://huggingface.co/Qwen/Qwen3.6-27B), [MLX community 4-bit 변환](https://huggingface.co/mlx-community/Qwen3.6-27B-4bit) | 현재 기본 로컬 VLM. 공간 관찰, 회전 비교 및 조건부 국소 정체성 확인 | community revision `c000ac2c2057d94be3fa931000c31723aac53282`; Apache-2.0 원문과 모델카드·파일SHA 보관. 기반 VLM을 학습·미세조정한 것은 아니다. |
| [Qwen3-VL-8B-Instruct](https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct), [MLX 8-bit 변환](https://huggingface.co/mlx-community/Qwen3-VL-8B-Instruct-8bit) | 초기 실제 추론 및 비교 | Apache-2.0; 현재 기본 모델로 표시하지 않는다. 고정 버전과 파일은 기존 manifest에 보관. |
| [OWLv2](https://huggingface.co/google/owlv2-base-patch16-ensemble), [Grounding DINO tiny](https://huggingface.co/IDEA-Research/grounding-dino-tiny) | v0.3 CPU 개발 진단 | Apache-2.0; revision 각각 `cfd3195ba4ea9592eec887ded089f4c08eff231d`, `a2bb814dd30d776dcf7e30523b00659f4f141c71`. 기본 제품에 채택하지 않았다. |
| [Torchvision Faster R-CNN MobileNetV3 320 FPN](https://docs.pytorch.org/vision/stable/models/generated/torchvision.models.detection.fasterrcnn_mobilenet_v3_large_320_fpn.html) | COCO 사전학습 가중치에서 2·3클래스 검출기 지도학습. 2클래스 첫 모델은 별도 연구용 검증대, 후속 후보는 기본 주문 판정에 미채택 | 원 가중치 파일 `fasterrcnn_mobilenet_v3_large_320_fpn-907ea3f9.pth`, SHA `907ea3f91ff92242bc1baea8049276a3e76bca48ce7560bd268cc029f37977b5`. 기반 VLM 무학습과 검출기 학습은 구분한다. Torchvision 소프트웨어 라이선스를 모든 사전학습 데이터의 권리 허가로 확대하지 않는다. |

제품의 사진 관찰은 로컬 MLX에서 실행한다. 사용자 사진을 외부 클라우드 LLM API로 보내는 제품 경로는 사용하지 않는다. 개발 중 Codex 이용·공개 자료 웹 조회는 별도로 공개한다. 전체 모델 가중치를 제출 소스 ZIP에 포함하지 않고 원출처와 재현용 manifest를 제공한다.

## 데이터와 파생 자료

| 원출처 | 사용과 변환 | 권리·증거의 한계 |
|---|---|---|
| [MVTec Screws](https://www.mvtec.com/research-teaching/datasets/mvtec-screws), [Neuromatch 교육 자료](https://deeplearning.neuromatch.io/projects/ComputerVision/screws.html) | 저자 사진·회전 상자에서 전체 사진/완전 ROI 개발·평가 및 검출기 학습. type_007 등의 익명 ID는 평가 전에 고정한 교육 자료 기반 의미 투영으로 nut에 매핑 | MVTec 데이터 CC BY-NC-SA 4.0. 저자가 영문 nut라고 직접 표기했다거나 팀이 촬영·실물 나사산을 인증했다고 쓰지 않는다. |
| [MVTec LOCO AD](https://www.mvtec.com/research-teaching/datasets/mvtec-loco-ad) | screw_bag 정상 및 수량 이상 사진. 저자의 정상 구성·결함 설명으로 수량 진실값 파생; 이번 24장은 서로 다른 두 클래스의 결함 차이를 결합 | CC BY-NC-SA 4.0. 원생 4클래스 개수 표나 현장 표본이 아니다. 정상16·기존51·신규24의 분모를 따로 보고한다. 긴/짧은 나사나 SKU 판별을 보증하지 않는다. |
| [InO-10-190 저자 저장소](https://git.sztaki.hu/emi/sim2real-object-detection) | bracket 단일 클래스 양성 진단, 전체 사진과 저자 ROI; 기존 20사례와 별도 개발 진단 | revision `c733a3543157135c591cbe3f9de27e209964af63`. 저자 저장소 MIT 원문 보관. origin/cropped를 독립 실물로 중복 계산하지 않는다. 저장소 고지를 넘어 모든 외부 이미지 권리를 새로 인증한 것으로 쓰지 않는다. |
| [FOD-A 저자 저장소](https://github.com/FOD-UNOmaha/FOD-data)와 연결 VOC v2.1 자료 | 로컬 3클래스 검출기 연구에 train400·validation36 사용; 원 폴더 복원·보수적 그룹 분리, 실패 진단과 회색조 비교 | 코드 저장소 MIT와 외부 사진의 권리 고지는 구분한다. 사진의 명시적 별도 라이선스는 미확인 상태로 유지하며 제출 묶음에 사진을 재배포하지 않는다. held-back36은 모델 평가에 사용하지 않았다. |
| [MANTA 저자 자료](https://grainnet.github.io/MANTA), 저자가 연결한 Figshare | nut / yellow_green_washer 두 패키지의 출처·메타데이터 조사, 사전 선택 train 개발4기록의 고정 제0시점 관찰. 후속 분류기 준비는 진행 중이며 이 초안 기준 새 학습 결과 없음 | 저자 CC BY-NC-SA 4.0과 Figshare CC BY 4.0 표기가 충돌하여 더 엄격한 저자 비상업 조건으로 로컬 연구만 수행. 5시점은 같은 composite 기록이며 물리件·촬영session ID가 없어 물리 독립을 인증하지 않는다. 저자 test는 모델 개발·평가에 쓰지 않았다. |
| 합성 테스트 그림·고정 관찰 | Pillow 생성 그림, test backend, HTTP·상태·증거 구조 확인 | 실제 모델 정확도나 실제 사용자 검증의 분모에 넣지 않는다. |
| 로컬 자료 주문에 입력하는 출처·라이선스 진술 | 사용자가 넣은 선언과 사진 해시를 고정해 보관. 현재 실제 연동은 기존 공개 LOCO016 사진 | 사용자 진술은 `user_declared_unverified`; 사진 권리·현장성을 자동 인증하지 않는다. URL은 기록하며 사진 다운로드에 쓰지 않는다. |

MVTec 및 MANTA의 비상업·저작자표시·동일조건공유 조항과 다른 자산의 개별 조건을 보존한다. 현재 소스 미리보기에는 명시적으로 선정한 MVTec 개발 예시3장만 포함한다. 전체 데이터 패키지, FOD/MANTA 사진, 모델 가중치, 실제 주문 데이터베이스는 포함하지 않는다. 일반적인 대회 재사용 허용은 개별 데이터의 라이선스를 대체하지 않는다.

## 라이브러리와 제작 도구

| 범위 | 주요 도구 | 기록 |
|---|---|---|
| 제품 | FastAPI, Uvicorn, Pydantic, python-multipart, Pillow, MLX/MLX-VLM, Transformers, Hugging Face Hub, Safetensors, SQLite | 정확한 설치 버전·패키지 라이선스 표기는 [PACKAGE_METADATA_20261002.json](PACKAGE_METADATA_20261002.json), 재현 의존성은 `requirements-lock.txt`. 주요 항목 목록이며 완전한 SBOM으로 표시하지 않는다. |
| 연구 | PyTorch, Torchvision, NumPy 및 관련 의존성 | 잠금 파일과 실제 실행 환경을 각 실험 protocol에 보관. PyTorch 등의 복합 라이선스 표기는 그대로 보존한다. |
| 문서·발표·영상 | ReportLab PDF, Artifact Tool 편집 가능한 PPT, Pillow, FFmpeg, 저장된 실제 브라우저 화면 | v0.8 영상은 저장 화면과 실제 API 기록을 편집한 영상이다. 연속 사용자 녹화·브라우저 업로드 성공·사람의 의견으로 표시하지 않는다. 새 영상은 이 초안 작성 시 제작 중이다. |

## 성과를 적는 범위

- 기존51장 기본 G: **정확41 / 오류3 / 미확인7**. 두 참조 이미지 후보는 통과하지 못하여 기본에 채택하지 않았다.
- 추가 LOCO24: **정확23 / 오류0 / 미확인1**, 한 도메인의 총6개 조합 변화에 한정. 기존3오류를 삭제하거나 새24와 합쳐 포괄적 정확도로 홍보하지 않는다.
- 자료 주문 실제 API 연동: 기존 공개사진1장, 검사2회·실제 생성6회. R1 요구량3에서 사전 설정 R2 요구량2로 바꾼 같은 사진의 새 추론이며 실제 부품 보충이 아니다.
- 자동 의견2건은 `ENGINEERING-AGENT`, **실제 참여자0·실물 완료0**이다. 소프트웨어 회귀1,530통과는 해당 시점의 공학 검사 결과이며 실제 사진의 정확도와 다르다.

中文填表提示：保留真实开始日期、赛前原型与赛期增量；把“基础视觉模型未微调”和“另行训练过检测器”分别写清楚。上述清单是现有事实的韩文草稿。拿到官方别纸2后，按原表字段转填，再由队员核实姓名、所属、签名及最终使用情况。
