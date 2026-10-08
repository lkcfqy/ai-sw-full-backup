"""Rebuild the five-page Korean prototype report from explicit saved benchmark runs.

Run with the Codex bundled Python (ReportLab, pypdf). No inference occurs here.
Metrics are read from completed run.json and predictions.jsonl, never invented.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
INK = colors.HexColor("#17332F")
TEAL = colors.HexColor("#167F70")
MUTED = colors.HexColor("#526962")
PALE = colors.HexColor("#F0F7F4")
LINE = colors.HexColor("#D8E5DF")
AMBER = colors.HexColor("#FFF5DE")
WIDTH = A4[0] - 80


class FlowStrip(Flowable):
    def __init__(self):
        super().__init__()
        self.width, self.height = WIDTH, 44

    def draw(self):
        labels = ["사진·참조", "물체 목록", "코드 계수", "BOM·보완", "사람 확인"]
        gap = 9
        cell = (self.width - gap * 4) / 5
        self.canv.setFont("Korean", 9.2)
        for i, label in enumerate(labels):
            x = i * (cell + gap)
            self.canv.setFillColor(PALE)
            self.canv.setStrokeColor(LINE)
            self.canv.roundRect(x, 8, cell, 29, 5, fill=1, stroke=1)
            self.canv.setFillColor(INK)
            self.canv.drawCentredString(x + cell / 2, 18, label)
            if i < 4:
                self.canv.setStrokeColor(TEAL)
                self.canv.line(x + cell + 2, 22, x + cell + 7, 22)


def saved_run(relative: str, label: str) -> dict:
    path = ROOT / relative / "run.json"
    raw = path.read_bytes()
    run = json.loads(raw)
    predictions = (path.parent / "predictions.jsonl").read_bytes()
    count = sum(bool(line.strip()) for line in predictions.splitlines())
    summary = run["summary"]
    if not run.get("finished_at") or count != summary["images"]:
        raise ValueError(f"Run is not a completed image benchmark: {relative}")
    if run.get("status", "completed") != "completed":
        raise ValueError(f"Run status is not completed: {relative}")
    return {
        "path": relative,
        "label": label,
        "summary": summary,
        "run_sha256": hashlib.sha256(raw).hexdigest(),
        "predictions_sha256": hashlib.sha256(predictions).hexdigest(),
        "manifest_sha256": run.get("manifest_sha256"),
        "model": run.get("model_before", {}).get("label"),
        "input_pipeline": run.get("input_pipeline", "original"),
        "image_max_side": run.get("model_before", {}).get("image_max_side"),
        "observation_mode": run.get("observation_mode")
        or run.get("model_before", {}).get("observation_mode", "single"),
    }


def ratio(metric: dict) -> str:
    denominator = metric["denominator"]
    if not denominator:
        return "분모 없음"
    return f"{metric['numerator']}/{denominator}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output/pdf/KitGuard_결과보고서_v0.2.pdf")
    parser.add_argument("--candidate-status", default="동결 48장 정적 평가 및 독립 재계산 완료")
    parser.add_argument("--loco-status", default="전체 원본 압축본 검증 완료")
    parser.add_argument(
        "--run",
        action="append",
        default=[],
        metavar="LABEL=RELATIVE_DIRECTORY",
        help="Use explicit completed runs instead of the default historic comparison",
    )
    parser.add_argument(
        "--extra-run",
        action="append",
        default=[],
        metavar="LABEL=RELATIVE_DIRECTORY",
        help="Add a completed image benchmark to the retained historic results",
    )
    args = parser.parse_args()
    runs = (
        [saved_run(relative, label) for label, relative in (value.split("=", 1) for value in args.run)]
        if args.run
        else [
            saved_run("evaluation-runs/loco_development_release_v1", "개발 / 공간 목록"),
            saved_run("evaluation-runs/loco_holdout_27b_single_control_v1", "보류 / 직접 계수"),
            saved_run("evaluation-runs/loco_holdout_release_v1", "보류 / 공간 목록"),
        ]
    )
    for value in args.extra_run:
        label, relative = value.split("=", 1)
        runs.append(saved_run(relative, label))
    if len(runs) > 6:
        raise ValueError("A five-page report can show up to six runs; summarize scope separately")
    release = saved_run("evaluation-runs/loco_holdout_release_v1", "선정 보류 실행")
    control = saved_run("evaluation-runs/loco_holdout_27b_single_control_v1", "동일 모델 대조")
    rs, cs = release["summary"], control["summary"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(TTFont("Korean", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"))
    styles = {
        "body": ParagraphStyle(
            "body", fontName="Korean", fontSize=10, leading=15.5, textColor=INK, wordWrap="CJK", spaceAfter=8
        ),
        "small": ParagraphStyle(
            "small",
            fontName="Korean",
            fontSize=8.5,
            leading=12.5,
            textColor=MUTED,
            wordWrap="CJK",
            spaceAfter=6,
        ),
        "cell": ParagraphStyle(
            "cell", fontName="Korean", fontSize=9, leading=13, textColor=INK, wordWrap="CJK"
        ),
        "heading": ParagraphStyle(
            "heading",
            fontName="Korean",
            fontSize=13.5,
            leading=19,
            textColor=TEAL,
            spaceBefore=13,
            spaceAfter=7,
        ),
        "title": ParagraphStyle(
            "title", fontName="Korean", fontSize=23, leading=31, textColor=INK, spaceAfter=13
        ),
    }
    story = []

    def p(value, kind="body"):
        return Paragraph(value, styles[kind])

    def paragraph(value, kind="body"):
        story.append(p(value, kind))

    def heading(value):
        story.append(p(value, "heading"))

    def table(headers, rows, widths=None):
        values = [
            [p(escape(str(value)).replace("\n", "<br/>"), "cell") for value in row]
            for row in [headers, *rows]
        ]
        item = Table(values, colWidths=widths, hAlign="LEFT", repeatRows=1)
        item.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), PALE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.7, TEAL),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        story.append(item)
        story.append(Spacer(1, 9))

    def callout(value):
        box = Table([[p(value)]], colWidths=[WIDTH])
        box.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), AMBER),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E6D6AA")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                    ("TOPPADDING", (0, 0), (-1, -1), 9),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        story.append(KeepTogether([box, Spacer(1, 10)]))

    def page(title):
        if story:
            story.append(PageBreak())
        story.append(p(title, "title"))

    page("01 / 문제와 제안")
    paragraph("KitGuard · 소량 키트의 수량과 근거를 함께 검증하는 로컬 Agent", "heading")
    paragraph(
        "팀: 해피 / 국립창원대학교 인공지능융합공학과<br/>작성 기준: 2026-09-26 / v0.2 사전 프로토타입 / 정식 제출본 아님",
        "small",
    )
    callout(
        "소프트웨어 흐름 구현과 동결 정적 평가를 완료했습니다. 선정한 LOCO 보류 사진 48장 중 네 분류 전체 계수가 맞은 것은 46장입니다. 두 오답 중 하나는 표준 주문에 잘못된 ready를 냈습니다. 현장 성능·작업 시간 개선·대회 적격성은 별도로 확인해야 합니다."
    )
    heading("해결하려는 상황")
    paragraph(
        "소량 키트는 단순해 보여도 누락·초과, 주문 수량 변경, 예전 사진의 재사용 때문에 확인 근거가 어긋날 수 있습니다. KitGuard는 사진에서 관찰한 수량과 현재 주문을 분리해 비교하고, 부족한 근거에는 다음 행동을 요청합니다. 수량이 맞아도 사람이 실물을 확인해야 완료됩니다."
    )
    story.append(FlowStrip())
    heading("현재 제품 범위")
    table(
        ["포함", "제외 또는 미검증"],
        [
            [
                "볼트·너트·와셔·브래킷 4분류\n항목별 0-3개, 합계 1-12개",
                "나사 길이·재질·나사산·SKU 구분\n복잡한 조립 상태와 안전 인증",
            ],
            [
                "사진과 선택적 단품 참조, 수량 수정 제안\n한·중 UI, 한·중·영 수량 변경 문장",
                "실제 공장 도입 성과·불량 비용 절감\n지원 범위를 넘는 장면의 자동 처리",
            ],
            [
                "Mac 로컬 처리, 단일 작업자 프로토타입",
                "Windows·RTX 3080/CUDA 실측\n다중 사용자 운영·공개 서버 배포",
            ],
        ],
        [WIDTH / 2, WIDTH / 2],
    )
    heading("차별화의 정확한 범위")
    paragraph(
        "개별 이미지의 검출 성능을 새로 발명했다고 주장하지 않습니다. 팀의 구현 초점은 주문 버전·참조·사진·검증 결과를 묶고, 이전 요청과 새 관찰을 비교하여 보완 흐름을 유지하는 데 있습니다. 이 설계가 실제 오류와 시간을 줄이는지는 별도 대조 실험으로 확인해야 합니다."
    )

    page("02 / 실제 구현과 Agent 흐름")
    table(
        ["단계", "실행과 기록"],
        [
            [
                "1. 요구 확인",
                "구조화 수량을 저장합니다. 자연어 변경은 승인 전 제안이며 주문을 직접 바꾸지 않습니다.",
            ],
            [
                "2. 물체 목록",
                "로컬 VLM이 물체마다 분류·추정 중심점을 출력합니다. 사진과 선택적 참조만 사용하고 목표 수량은 제외합니다. 목록과 위치는 검증된 정답이 아닙니다.",
            ],
            [
                "3. 코드 계수",
                "코드가 목록 항목을 세고 현재 BOM과 차이를 계산합니다. 불명확한 분류는 null로 남깁니다. 형식 오류·모델 실패·시간 초과는 성공으로 처리하지 않습니다.",
            ],
            [
                "4. 다음 행동",
                "불확실하면 분리·재촬영·수동 확인, 명확한 수량 차이는 추가/제거를 안내합니다. 관찰값을 주문 상한에 억지로 맞추지 않습니다.",
            ],
            [
                "5. 새 근거 검토",
                "이전 불명확 분류만 공간 관찰의 주의 정보로 전달합니다. 이전 수량·목표/증감 문구·영역은 제외하며 새 사진의 모든 물체를 다시 나열합니다.",
            ],
            [
                "6. 확인·저장",
                "최신 유효 ready와 명시적 사람 확인이 있어야 완료 기록을 만듭니다. 이력에는 요구·사진·관찰·차이·모델·실행 단계가 남습니다.",
            ],
        ],
        [83, WIDTH - 83],
    )
    heading("상태와 근거의 보호")
    paragraph(
        "새 사진, 참조 변경, 주문 개정은 이전 ready를 무효화합니다. 추론 시작 때의 revision과 evidence_epoch를 종료 시 다시 확인하므로 오래된 추론 결과가 새 상태를 덮어쓸 수 없습니다. 완료 요청은 트랜잭션과 멱등 키로 처리하며, 완료 후 개정해도 과거 확인 기록은 보존됩니다."
    )
    paragraph(
        "보완 예산은 같은 버전·참조의 연속 불명확 구간만 셉니다. 같은 저장 사진 재검사는 새 증거가 아니며, 서로 다른 사진 두 번의 보완 후에도 불명확하면 수동 확인으로 전환합니다. 명확한 판단이나 버전·참조 변경은 구간을 재설정합니다. 사진 ID 규칙은 실제 촬영 진위나 중복 재업로드를 인증하지 않습니다."
    )
    heading("모델과 도구")
    paragraph(
        "선정 구성은 Qwen3.6-27B MLX 4-bit, 사진 최대 변 1536, 공간 물체 목록 최대 900토큰, 단일 호출입니다. 상태: "
        + escape(args.candidate_status)
        + ". Qwen3-VL-8B는 이전 비교 기준입니다. 코드로 수를 세어도 모델의 누락·중복·오분류는 남으므로 위치 표시만으로 정확성을 보장하지 않습니다."
    )
    paragraph(
        "구성: FastAPI / SQLite / MLX-VLM / HTML·CSS·JavaScript. 증거 ZIP은 당시 사진·참조·개정·관찰·확인 및 SHA-256과 오프라인 뷰어를 담는 읽기 전용 스냅샷입니다.",
        "small",
    )

    page("03 / 동결 정적 평가와 대조")
    paragraph(
        "2026-09-26 19:44:49 KST에 모델·프롬프트·코드·48개 ID를 동결했고, 저장된 첫 보류 실행은 19:45:00에 시작했습니다. 개발 16장은 모델 선택에 사용했습니다. 보류 48장은 정상 24·단일 수량 이상 24이며, 공식 전체 테스트 성적은 아닙니다. 사전학습 데이터 중복 여부도 알 수 없습니다."
    )
    rows = []
    for run in runs:
        summary = run["summary"]
        rows.append(
            [
                run["label"],
                summary["images"],
                ratio(summary["count_exact"]),
                ratio(summary["actionable_coverage"]),
                ratio(summary["wrong_actionable_count"]),
                f"{summary['latency_ms']['median'] / 1000:.2f}초",
            ]
        )
    table(
        ["27B / 1536", "사진", "전체 계수 정답", "명확한 관찰", "그중 계수 오답", "중위 시간"],
        rows,
        [121, 39, 88, 84, 100, WIDTH - 432],
    )
    paragraph(
        "동일 48장에서 34/48 → 46/48로 +25.0%p입니다. 둘 다 정답 34, 목록만 정답 12, 직접 계수만 정답 0, 둘 다 오답 2입니다. 같은 모델·업로드 JPEG·해상도지만 직접 계수 450 vs 목록 900토큰이며 프롬프트·출력 구조도 달라집니다. 목록 또는 위치만의 인과 효과를 분리하지 못합니다. 개발 행은 독립 성능이 아닙니다.",
        "small",
    )
    heading("정상·이상 분리와 주문 결과")
    table(
        ["보류 48장 지표", "직접 계수", "공간 목록"],
        [
            [
                "정상 24장 전체 계수 정답",
                ratio(cs["subgroups"]["normal_constant_222"]["count_exact"]),
                ratio(rs["subgroups"]["normal_constant_222"]["count_exact"]),
            ],
            [
                "수량 이상 24장 전체 계수 정답",
                ratio(cs["subgroups"]["quantity_anomaly"]["count_exact"]),
                ratio(rs["subgroups"]["quantity_anomaly"]["count_exact"]),
            ],
            [
                "표준 주문에서 이상 사진의 잘못된 ready",
                ratio(cs["nominal_order"]["quantity_anomalies_false_ready"]),
                ratio(rs["nominal_order"]["quantity_anomalies_false_ready"]),
            ],
            [
                "고정 교란 주문의 잘못된 ready",
                ratio(cs["mismatched_order_false_ready"]),
                ratio(rs["mismatched_order_false_ready"]),
            ],
            ["실행 오류 / 선정 사진", ratio(cs["errors"]), ratio(rs["errors"])],
        ],
        [285, 112, WIDTH - 397],
    )
    paragraph(
        "명확한 관찰은 non-null 수량·issues=[]·action=none인 출력이며 정답이나 ready가 아닙니다. 전체 계수는 네 분류가 모두 맞아야 합니다. 오류·거절도 전체 사진 분모에 남깁니다. 주문 지표는 관찰을 규칙에 넣은 오프라인 결과이며 실제 출고가 아닙니다. 같은 사진에서 파생된 주문은 독립 표본이 아닙니다.",
        "small",
    )
    paragraph(
        "시간은 임시 앱·DB·실제 업로드 정규화와 관찰을 포함한 app-upload 사례별 벽시계 시간입니다. 순수 추론 시간이나 사람의 전체 작업 시간이 아닙니다. 관찰은 직접 호출했으며 /inspect·/complete 전체 경로와 사람 확인은 이 지표에 포함하지 않습니다.",
        "small",
    )
    heading("데이터 범위")
    paragraph(
        "정상 구성은 bolt/nut/washer/bracket=2/2/2/0입니다. 정상·이상 균형 48장에 상수 2/2/2/0을 출력하면 24/48만 맞습니다. 길이가 다른 나사를 bolt로 합쳐 규격 대체를 평가하지 않으며 bracket 양성도 없습니다. Screws 개발 16장은 모두 분류별 3개 상한을 넘어 주문 분모가 0입니다. 초기 8B v2의 3/16 정답·13/16 명확한 오답 기록도 삭제하지 않았습니다.",
        "small",
    )

    page("04 / 남은 오류와 제품 수용 조건")
    heading("정적 보류 평가의 두 오류")
    table(
        ["사례 / 저자 기반 진실값", "모델 출력과 결과"],
        [
            [
                "test/good/113\n진실값 (2,2,2,0)",
                "출력 (2,4,2,0). 표준 주문에 nut 2개를 빼라고 잘못 제안했습니다. 추정 추가 nut 점은 bolt 머리 부근이며, 이는 보조적 시각 해석입니다.",
            ],
            [
                "logical_anomalies/042\n진실값 (3,2,2,0)",
                "출력 (2,2,2,0). 1개 많은 bolt를 놓쳐 표준 주문에 잘못된 ready를 냈습니다. 저자 마스크 값 251은 1_additional_long_screw입니다.",
            ],
        ],
        [176, WIDTH - 176],
    )
    paragraph(
        "순서는 bolt·nut·washer·bracket입니다. 042의 표준 주문 오류 1/24와 고정 교란 오류 1/48은 같은 사진·같은 2/2/2/0 주문이므로 두 번의 독립 오출고가 아닙니다. 실제 출고·사람 조작은 없었습니다. 사람 확인이 필요하지만 잘못된 ready 자체가 사라지는 것은 아닙니다."
    )
    heading("진실값과 재현 근거")
    paragraph(
        "정상 수량은 저자 논문 §3.1(PDF 5쪽), 이상 수량은 defects_config와 단일 수량 결함 마스크에서 가져왔습니다. 마스크 면적이나 모델 시각 판단으로 물체 수를 새로 만들지 않았습니다. 원본·업로드 JPEG·manifest·소스 스냅샷 SHA를 독립 확인했고 48장 전처리를 재현했습니다. 단일 관찰의 중간 PNG 실제 해시는 마지막 사례만 보존되어 나머지는 재구성 값입니다.",
        "small",
    )
    heading("구현 검증과 아직 필요한 실물 검증")
    paragraph(
        "공학 회귀 186개가 통과했고 독립 관련 88개 재검증은 그 하위 집합입니다. 사진·참조·개정의 변경, 오래된 추론, 실패·시간 초과, 멱등 완료, 목록/계수 모순을 검사했습니다. 합성 사진과 가짜 모델 출력 테스트는 실제 인식 표본이나 산업 안전 증거가 아닙니다."
    )
    table(
        ["수용 대상", "확인할 근거"],
        [
            [
                "상태 일관성",
                "새 증거·참조·개정 뒤 과거 결과로 완료되지 않으며 실패가 성공 기록을 만들지 않을 것",
            ],
            [
                "실물 보완 효과",
                "동일 실물의 전후 구성과 촬영·사람 조작을 별도로 기록하고 요청-새 관찰-남은 차이를 재생할 것",
            ],
            [
                "사용자 효용",
                "사람 체크리스트 / 단발 VLM / KitGuard 순서를 교차해 최종 오류·시간·사진 수·개입 비용을 함께 비교할 것",
            ],
        ],
        [130, WIDTH - 130],
    )
    paragraph(
        "실물·사용자 대조는 아직 수행하지 않았습니다. CC0 실제 bracket 보조 사진 2장은 출처 검토용이며 수량 정답이 없고 평가에 섞지 않았습니다. 결과를 본 뒤 핵심 모델을 수정하지 않았으며, 남은 오류를 숨기거나 임의 정확도 목표로 제품 수용을 대신하지 않습니다.",
        "small",
    )

    page("05 / 배포·재현·출처와 개발 고지")
    heading("현재 실행과 재현")
    paragraph(
        "본기기 검증은 Apple Silicon Mac의 MLX 경로입니다. 사용자 제공 사양은 M5 Pro·64 GB입니다. 데스크톱 i9-9900KF·RTX 3080 10 GB·RAM 32 GB를 보유했지만 이 문서는 Windows/CUDA 실행 성과를 주장하지 않습니다. 사진 추론은 로컬이며 외부 LLM API로 사진을 보내지 않습니다."
    )
    table(
        ["절차", "프로젝트 루트에서 실행 / 확인"],
        [
            ["환경", "bash scripts/setup.sh\nrequirements-lock.txt로 의존성 확인"],
            [
                "선정 모델",
                ".venv/bin/python scripts/download_candidate_model.py\n16개 원본 파일·SHA·라이선스 manifest 확인",
            ],
            [
                "실행 설정",
                "run.sh 기본값: 27B / spatial_inventory / 1536\nKITGUARD_MODEL_PATH로 모델 경로 변경",
            ],
            ["기동", "bash scripts/run.sh\nhttp://127.0.0.1:8765 (단일 프로세스)"],
            ["검증", ".venv/bin/python -m pytest -q\n.venv/bin/ruff check kitguard tests scripts"],
            [
                "백업·평가",
                "서비스 종료 후 data/ 전체 복사\nscripts/run_benchmark.py, run_instruction_benchmark.py의 --help 확인",
            ],
        ],
        [96, WIDTH - 96],
    )
    paragraph(
        "다운로드는 네트워크가 필요합니다. 모델 원본 16개 총 16,081,490,064바이트의 SHA를 검증했습니다. wheel 빌드·격리 해제 후 앱/정적 파일 기동은 기존 의존성 환경에서 확인했으며 새 컴퓨터 전체 설치 시험은 아닙니다. HTTP 시간 초과 후에도 하위 추론이 남을 수 있습니다.",
        "small",
    )
    heading("AI 코드 사용과 팀 개발 범위")
    paragraph(
        "Codex가 공개 자료 조사, 앱·상태관리·보완 피드백·UI·테스트·평가 도구와 문서 초안의 생성·수정에 참여했습니다. 공개 Qwen/MLX 모델을 이용하며 가중치를 자체 학습했다고 주장하지 않습니다. 테스트와 문서 생성에는 Pillow·ReportLab 등 공개 도구를 사용했습니다. 팀은 제출 전 실행·출처·수치·라이선스와 AI 사용 고지를 최종 검토해야 합니다."
    )
    heading("실제 개발 날짜와 참가 자격 미결")
    paragraph(
        "실제 개발 시작은 2026-09-26입니다. r1 최종 신청서의 참가자 동의서에는 “개발기간 외 사전 개발, 타인 작품 도용,부문 교차 구성 등의 부정행위를 하지 않겠습니다.”라는 조항이 있습니다. 공개 모델·AI 도구 허용을 사전 개발 코드 허용으로 해석하지 않습니다. 본 사전 프로토타입의 대회 사용 적격성은 주최 측 확인이 필요하며, 이 초안은 제출 또는 승인된 문서가 아닙니다."
    )
    paragraph(
        '<link href="https://contest.gnict.org/rule.php" color="#167F70">대회 공식 규정</link> · '
        '<link href="https://huggingface.co/Qwen/Qwen3.6-27B" color="#167F70">Qwen 모델카드</link> · '
        '<link href="https://www.mvtec.com/research-teaching/datasets" color="#167F70">MVTec 공개 데이터</link><br/>'
        "로컬 근거: docs/FINAL_INDEPENDENT_AUDIT.md, docs/RELEASE_EVALUATION_FREEZE.json, evaluation-runs/*/run.json. "
        "Qwen 모델은 Apache-2.0, Screws·LOCO 데이터는 CC BY-NC-SA 4.0으로 출처와 이용 조건을 보존합니다.",
        "small",
    )

    def footer(c, doc):
        c.setStrokeColor(LINE)
        c.line(40, 53, A4[0] - 40, 53)
        c.setFont("Korean", 7.8)
        c.setFillColor(MUTED)
        c.drawString(40, 39, "2026-09-26 사전 프로토타입 / 미제출 초안 / 대회 적격성 주최 측 확인 필요")
        c.drawRightString(A4[0] - 40, 39, f"{doc.page} / 5")
        c.setFont("Korean", 8)
        c.setFillColor(TEAL)
        c.drawString(40, A4[1] - 31, "KitGuard · 해피 · 개발 결과보고")
        c.drawRightString(A4[0] - 40, A4[1] - 31, "v0.2 / DRAFT")

    document = SimpleDocTemplate(
        str(args.output),
        pagesize=A4,
        leftMargin=40,
        rightMargin=40,
        topMargin=53,
        bottomMargin=68,
        title="KitGuard 결과보고서 v0.2 - 사전 프로토타입",
        author="해피 · KitGuard",
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    from pypdf import PdfReader

    reader = PdfReader(args.output)
    if len(reader.pages) != 5:
        raise RuntimeError(f"Expected exactly five pages; rendered {len(reader.pages)}. Fix layout.")
    metadata = {
        "artifact": str(args.output.resolve()),
        "pages": len(reader.pages),
        "candidate_status": args.candidate_status,
        "loco_status": args.loco_status,
        "report_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "runs": runs,
        "note": "Frozen static holdout and same-model protocol comparison; not physical field performance. "
        "Rendering and visual QA are required after each content update.",
    }
    args.output.with_suffix(".sources.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n"
    )
    print(args.output)


if __name__ == "__main__":
    main()
