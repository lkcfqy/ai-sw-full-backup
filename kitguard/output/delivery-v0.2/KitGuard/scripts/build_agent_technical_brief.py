"""Build the one-page Korean draft technical brief; uses bundled ReportLab Python."""

from __future__ import annotations

import argparse
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

ROOT = Path(__file__).resolve().parents[1]
FONT_PATH = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
INK = colors.HexColor("#17332F")
MUTED = colors.HexColor("#526962")
TEAL = colors.HexColor("#167F70")
LINE = colors.HexColor("#D8E5DF")
PALE = colors.HexColor("#F0F7F4")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output/pdf/KitGuard_Agent_기술설명_v0.2.pdf")
    parser.add_argument("--candidate-status", default="동결 정적 보류 평가 완료")
    parser.add_argument("--loco-status", default="전체 원본 압축본 검증 완료")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(TTFont("Korean", FONT_PATH))
    width, height = A4
    document = canvas.Canvas(str(args.output), pagesize=A4, pageCompression=1)
    document.setTitle("KitGuard Agent 기술설명 v0.2 - 사전 프로토타입")
    document.setAuthor("해피 · KitGuard")
    document.setSubject("구현 범위, Agent 흐름, 로컬 모델과 공개 데이터, 검증 한계")

    def text(value, x, y, size=9.2, leading=14, color=INK, max_width=None):
        style = ParagraphStyle(
            "text",
            fontName="Korean",
            fontSize=size,
            leading=leading,
            textColor=color,
            alignment=TA_LEFT,
            wordWrap="CJK",
        )
        paragraph = Paragraph(value, style)
        _, used_height = paragraph.wrap(max_width or width - x - 38, height)
        paragraph.drawOn(document, x, y - used_height)
        return y - used_height

    def section(number, heading, y):
        document.setFillColor(TEAL)
        document.roundRect(38, y - 17, 23, 19, 5, fill=1, stroke=0)
        document.setFont("Korean", 9)
        document.setFillColor(colors.white)
        document.drawCentredString(49.5, y - 11, number)
        text(heading, 69, y + 1, size=11.5, leading=16)
        return y - 28

    document.setFillColor(INK)
    document.rect(0, height - 130, width, 130, fill=1, stroke=0)
    text("KitGuard", 38, height - 29, size=29, leading=35, color=colors.white)
    text(
        "사진 근거와 주문 버전을 함께 관리하는 로컬 검증 Agent",
        39,
        height - 76,
        size=12.3,
        leading=18,
        color=colors.HexColor("#D9F0E6"),
    )
    text(
        "AGENT TECHNICAL BRIEF v0.2   /   해피   /   구현 기준 2026-09-26",
        39,
        height - 107,
        size=8.2,
        leading=12,
        color=colors.HexColor("#B5D9CB"),
    )

    y = height - 149
    y = text(
        "목적: 소량 부품 키트의 누락·초과를 사진으로 확인하고, 근거가 부족하면 다음 행동을 요청한 뒤 새 사진으로 다시 판단합니다.",
        38,
        y,
        size=10.1,
        leading=15.5,
    )
    y -= 10
    steps = ["사진·참조", "물체 목록", "코드 계수", "BOM 비교", "새 증거", "사람 확인"]
    gap, box_width = 9, (width - 76 - 45) / 6
    for index, label in enumerate(steps):
        x = 38 + index * (box_width + gap)
        document.setFillColor(PALE)
        document.setStrokeColor(LINE)
        document.roundRect(x, y - 30, box_width, 30, 6, fill=1, stroke=1)
        document.setFillColor(INK)
        document.setFont("Korean", 9.2)
        document.drawCentredString(x + box_width / 2, y - 19, label)
        if index < len(steps) - 1:
            document.setStrokeColor(TEAL)
            document.line(x + box_width + 2, y - 15, x + box_width + 7, y - 15)
    y -= 41
    y = text(
        "현재 범위: 볼트·너트·와셔·브래킷 4분류 / 항목별 0-3개, 총 1-12개 / 세부 규격·SKU 판별 제외",
        38,
        y,
        size=8.4,
        leading=12,
        color=MUTED,
    )

    y = section("01", "모델과 실행 도구", y - 16)
    y = text(
        "선정 모델: Qwen3.6-27B, MLX 4-bit. 사진 최대 변 1536, 물체 목록 출력 최대 900토큰, 단일 관찰 호출입니다. "
        f"상태: {args.candidate_status}.<br/>"
        "실행 도구: FastAPI·SQLite·MLX-VLM·브라우저 UI. 수량 비교, 주문 개정, 사진/참조 등록, 완료 확인, 읽기 전용 증거 ZIP을 제공합니다.",
        38,
        y,
        size=9.1,
        leading=14,
    )

    y = section("02", "관찰 → 행동 → 새 근거의 실제 순환", y - 16)
    y = text(
        "모델은 각 물체의 분류·추정 중심점을 나열하고, 코드는 목록 항목을 세어 현재 BOM과 비교합니다. 목표 수량은 사진 관찰 입력에서 제외합니다. 점은 모델 추정이며, 표시된 위치와 목록도 틀릴 수 있습니다. 불명확한 분류는 null로 유지합니다.<br/>"
        "다음 공간 관찰에는 이전에 불명확했던 분류만 전달합니다. 이전 수량·목표·증감 지시·영역은 제외합니다. 새 사진 결과로 해소된 불확실성과 남은 차이를 계산하며 실제 부품 조작을 추정하지 않습니다.<br/>"
        "같은 저장 사진의 재검사는 새 증거로 세지 않습니다. 동일 버전·참조의 연속 불명확 구간에서 서로 다른 사진 2회 보완 후에도 불명확하면 수동 확인으로 전환합니다.",
        38,
        y,
        size=9.1,
        leading=14,
    )

    y = section("03", "팀의 신규 구현: 버전·근거·완료의 일관성", y - 16)
    y = text(
        "신규 사진·참조 교체·주문 개정은 기존 ready를 무효화합니다. 추론 전후의 revision과 evidence_epoch를 비교하여 오래된 결과 저장을 거절합니다. 명확한 판단이나 참조·버전 변경은 보완 예산을 새로 시작합니다.<br/>"
        "완료는 최신 유효 결과와 작업자의 명시적 실물 확인이 있어야 가능합니다. 동일 요청은 중복 처리하지 않으며 완료 후 개정해도 이전 기록을 보존합니다. 관찰·비교·다음 행동·저장 단계는 실제 실행 결과로 기록합니다.<br/>"
        "팀 개발 범위: 물체 목록의 코드 계수, 상태 저장소, 보완 피드백, 완료 보호, 웹 UI, 증거 내보내기, 평가 실행기. 공개 모델의 자체 학습 또는 원천 모델 개발을 주장하지 않습니다.",
        38,
        y,
        size=9.1,
        leading=14,
    )

    y = section("04", "공개 자료·로컬 처리·검증 범위", y - 16)
    y = text(
        "공개 자료: MVTec Screws·LOCO screw_bag (CC BY-NC-SA 4.0). Screws는 제품 범위 밖 계수 시험, LOCO는 제작자의 정상 구성·단일 수량 결함 기반 정적 시험입니다. "
        "동결 48장 중 완전 계수 46/48, 표준 주문의 이상 사진 false-ready 1/24입니다. 공개 사진은 실물 보완·출고 증거가 아닙니다.<br/>"
        "사진 추론과 주문 처리는 로컬에서 수행합니다. 저장 사진은 정규화하고 EXIF를 제거하며, 내보내기에는 사진·관찰·개정·확인 기록과 SHA-256을 담습니다. 해시는 추적 근거이지 촬영 진위나 물리 행동의 증명은 아닙니다.<br/>"
        "미검증 범위: 실제 현장 정확도·시간 절감·여러 사용자의 효용·브래킷 성능. 공개 사진의 정적 시험과 합성 공학 테스트는 실물 작업 효과를 증명하지 않습니다. 사람 확인이 남습니다.",
        38,
        y,
        size=9.1,
        leading=14,
    )

    y -= 10
    y = text(
        '<link href="https://huggingface.co/Qwen/Qwen3.6-27B" color="#167F70">Qwen 공식 모델카드</link> · '
        '<link href="https://huggingface.co/mlx-community/Qwen3.6-27B-4bit" color="#167F70">MLX 모델카드</link> · '
        '<link href="https://www.mvtec.com/research-teaching/datasets/mvtec-screws" color="#167F70">MVTec Screws</link> · '
        '<link href="https://www.mvtec.com/research-teaching/datasets/mvtec-loco-ad" color="#167F70">MVTec LOCO</link>',
        38,
        y,
        size=7.7,
        leading=11,
    )
    if y < 77:
        raise RuntimeError(f"Body overlaps the protected footer: bottom={y:.1f}")
    document.setStrokeColor(LINE)
    document.line(38, 67, width - 38, 67)
    text("2026-09-26 사전 프로토타입 · 미제출 초안", 38, 57, size=8.2, leading=12, color=TEAL)
    text(
        "사전 개발 코드의 대회 활용 적격성은 주최 측 확인이 필요합니다.",
        38,
        42,
        size=8.1,
        leading=12,
        color=MUTED,
    )
    document.setFont("Korean", 8)
    document.setFillColor(MUTED)
    document.drawRightString(width - 38, 32, "1 / 1")
    document.save()
    print(args.output)


if __name__ == "__main__":
    main()
