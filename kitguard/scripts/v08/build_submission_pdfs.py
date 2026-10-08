"""Build two source-bound Korean A4 development-preview PDFs; no model or network.

The author invokes the PDF skill operation marker once, outside this script.
Every build writes content sources, explicit layout/evidence hashes and two PDFs.
PDF local evidence references are readable labels, never invalid relocated links.
Render all pages separately and visually inspect before delivery.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import tomllib
from pathlib import Path
from xml.sax.saxutils import escape

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Flowable, Paragraph, Table, TableStyle

ROOT = Path(__file__).resolve().parents[2]
OUT_DEFAULT = ROOT / "output/report/v0.8-preview"
FONT = Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf")
INK, TEAL = colors.HexColor("#193630"), colors.HexColor("#087F75")
MUTED, PALE = colors.HexColor("#536E67"), colors.HexColor("#EFF6F2")
LINE, AMBER = colors.HexColor("#CFDDD7"), colors.HexColor("#96551F")
W, H = A4
LEFT, RIGHT, TOP, BOTTOM = 43, 43, H - 69, 49
WIDTH = W - LEFT - RIGHT
EVIDENCE = {
    "E1": "test-results/v0.8/photo-document-live-api-v1/receipt.json",
    "E2": "test-results/v0.8-loco-combined-independent-audit-v2.json",
    "E3": "evaluation-runs/v0.8/loco_combined_v1/analysis.json",
    "E4": "evaluation-runs/v0.7/public_paired_v1/analysis.json",
    "E5": "test-results/v0.7/public-paired-audit-v1.json",
    "E6": "test-results/v0.8-photo-document-backend-v2.json",
    "E7": "test-results/v0.8/reference-live-api-v1/receipt.json",
    "E8": "docs/v0.8/DELIVERY_UPDATE_PLAN.md",
    "E9": "docs/v0.7/CONTEST_PERIOD_CONTRIBUTIONS.md",
    "E10": "docs/v0.8/SCREWS_CATEGORY_SEMANTICS_REVIEW.md",
    "E11": "docs/v0.8/LOCO_COMBINED_RESULT.md",
    "E12": "docs/v0.8/LOCO_COMBINED_DECISION.json",
    "E13": "test-results/v0.8-preview-full-v1.xml",
    "E14": "test-results/browser/photo-document-live-v08/browser-receipt.json",
    "E15": "docs/v0.7/OFFICIAL_RULE_CHECK_20261002.txt",
    "E16": "docs/v0.8/CONTEST_PERIOD_CONTRIBUTIONS.md",
    "E17": "docs/v0.8/CONTRIBUTION_DIFF_FROM_SEALED_V07.json",
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def plain(text):
    return re.sub(r"[\u2010-\u2015\u2212]", "-", text)


def inline(text):
    value = escape(plain(text))
    value = re.sub(r"\*\*(.+?)\*\*", r'<font color="#087F75">\1</font>', value)
    return value.replace("\n", "<br/>")


class Process(Flowable):
    """Vector process diagram, not an application screenshot or empirical evidence."""
    def __init__(self, steps):
        super().__init__()
        self.steps, self.width, self.height = steps, WIDTH, 86

    def draw(self):
        pdf, n = self.canv, len(self.steps)
        gap = 16
        box = (self.width - gap * (n - 1)) / n
        style = ParagraphStyle("flow", fontName="KR", fontSize=9.8, leading=15,
                               textColor=INK, wordWrap="CJK", alignment=1)
        for i, (label, subtitle) in enumerate(self.steps):
            x = i * (box + gap)
            pdf.setFillColor(PALE)
            pdf.setStrokeColor(LINE)
            pdf.roundRect(x, 5, box, 74, 7, fill=1, stroke=1)
            pdf.setFillColor(TEAL)
            pdf.setFont("KR", 8)
            pdf.drawCentredString(x + box / 2, 65, f"0{i + 1}")
            p = Paragraph(inline(label + "\n" + subtitle), style)
            _, h = p.wrap(box - 12, 48)
            p.drawOn(pdf, x + 6, 53 - h)
            if i < n - 1:
                pdf.setStrokeColor(TEAL)
                pdf.line(x + box + 3, 41, x + box + gap - 3, 41)
                pdf.line(x + box + gap - 7, 44, x + box + gap - 3, 41)
                pdf.line(x + box + gap - 7, 38, x + box + gap - 3, 41)


def block(kind, text=None, **kwargs):
    return {"kind": kind, "text": text, **kwargs}


def contents(facts, regression):
    latency = facts["api"]["inspection_results"]
    seconds = [f"{x['latency_ms'] / 1000:.3f}" for x in latency]
    regression_text = (f"전체 Python 회귀 {regression['passed']:,}건 통과. 이는 소프트웨어 계약 검증이며 "
                       "인식 정확도나 실제 사용자 검증 수가 아니다." if regression else
                       "최신 전체 회귀 실행 수는 이 문서에 미확정 값으로 기입하지 않았다. 자료 등록·개정·내보내기의 "
                       "관련 CPU 계약과 실제 MLX 연동 기록은 분리 보존한다.")
    report = [
        {"title": "사진과 주문을 함께 검토하는\nKitGuard", "kicker": "01 / 제품과 사용 문제", "blocks": [
            block("lead", "같은 사진이라도 주문이 바뀌면, 그 사진에 대한 검토도 다시 해야 합니다."),
            block("body", "KitGuard는 합법적으로 보유한 부품 사진과 수량표(BOM)를 연결하는 로컬 디지털 자료 검토 도구다. "
                  "사진 속 나사류·너트·와셔·브래킷의 굵은 범주를 관찰하고, 현재 주문과의 차이·불확실성·검토 이력을 남긴다. "
                  "규격이나 SKU를 인증하는 시스템은 아니다."),
            block("process", steps=[("자료 등록", "사진 + 출처 진술"), ("AI 비교", "현재 주문과 연결"),
                                    ("명시적 개정", "이전 근거는 과거로"), ("새 관찰·기록", "의견 + 증거 ZIP")]),
            block("h2", "평가자가 직접 확인할 네 가지 기능"),
            block("table", rows=[
                ["기능", "실행 가능한 동작"],
                ["내 사진으로 시작", "JPEG/PNG/WebP 한 장, 출처 설명, 주문 수량으로 자료 주문을 생성한다. URL·이용 조건은 선택 입력이며 서버가 원격으로 내려받지 않는다."],
                ["버전별 재검토", "수량 변경 후 이전 AI 결과와 의견을 현재 근거에서 제외한다. 동일 사진의 명시적 재사용 뒤 새로 추론한다."],
                ["참고 입력 추적", "종류별 참고 예시가 어느 공간 관찰 단계에 입력됐는지 보존한다. 참고는 검사 대상 수량에 포함하지 않는다."],
                ["실패와 이력 보존", "현재 실패를 새로고침 뒤에도 안내하고, 명시적으로 재시도한다. 출처·원본 연결·개정·원래 AI 결과와 의견을 ZIP으로 내보낸다."],
            ], widths=[0.23, 0.77]),
            block("callout", "디지털 전용 경계\n사용자가 진술한 출처·URL·라이선스는 항상 ‘미인증’이다. 등록된 공개 갤러리 세 예제와 별도 유형으로 관리하며, "
                  "자료 주문 및 확인 가능한 동일 바이트 계열을 실물 완료·현장 시험으로 전환하지 못하게 한다."),
            block("small", "범위: 주문은 종류별 0-3개, 전체 1-12개. 관찰 결과의 4개는 유효하며 3개로 잘라 저장하지 않는다. "
                  "사진 자료 검토이며 공장 출고·현장 안전을 보장하지 않는다. 근거 [E1, E6]."),
        ]},
        {"title": "모델의 관찰과 도구의 실행을 분리", "kicker": "02 / AI Agent 구현", "blocks": [
            block("lead", "AI가 사진을 해석하고, 서버의 고정 규칙이 다음 행동과 증거의 유효 범위를 통제한다."),
            block("body", "현재 기본 G(spatial_guarded)는 같은 로컬 Qwen3.6-27B-4bit 모델로 원방향·90도 회전 사진을 관찰한다. "
                  "두 공간 목록이 명확하게 합의한 경우 필요한 너트·와셔 대상을 잘라 조건부 신원 확인을 수행한다. "
                  "같은 모델의 반복 관찰이므로 독립 심사나 정확성 보증으로 취급하지 않는다."),
            block("table", rows=[
                ["단계 / 도구", "입력과 실행", "실행을 제한하는 조건"],
                ["사진 관찰", "공간 객체 목록과 불확실성을 구조화 JSON으로 반환", "관찰 프롬프트에 주문 정답 수량을 주지 않음"],
                ["비교·상태 관리", "현재 BOM과 관찰 수량 비교; 차이·추가 자료·수동 확인 안내", "파싱 실패·미확인 수량은 자동 통과로 바꾸지 않음"],
                ["주문 개정", "사용자 명시 변경을 새 revision으로 저장; 자연어 제안은 승인 후 반영", "사진 수량에 맞추려고 AI가 주문을 자체 수정하지 않음"],
                ["자료 재사용", "같은 바이트임을 확인해 새 revision에 연결; 새 추론 요구", "새 촬영이나 부품 보충으로 기록하지 않음"],
                ["검토·내보내기", "의견을 check·사진·버전·해시에 묶고 오프라인 ZIP 생성", "검토 의견을 정답·실물 완료·사용자 실증으로 승격하지 않음"],
            ], widths=[0.22, 0.42, 0.36]),
            block("h2", "상태를 갖는 제한된 Agent"),
            block("body", "단순 설명문 반환을 넘어 사진 등록, 구조화 관찰, 비교, 상태 전이, 개정, 재검사, 기록·내보내기 도구를 연결한다. "
                  "다만 자유로운 자율 계획 Agent가 아니라 서버 규칙으로 관리되는 작업 흐름이다. 주문·사진·증거 epoch가 바뀌면 "
                  "기존 판단을 무효화하며, 실패가 남은 상태를 성공으로 숨기지 않는다."),
            block("callout", "참고 이미지의 사실만 기록\n현재 제품의 원방향·회전 단계는 선택한 참고 이미지를 받을 수 있으나 신원 확인 단계는 참고를 받지 않는다. "
                  "종류, 저장 파일 SHA, 실제 준비 PNG SHA, 순서와 단계 상태를 기록한다. 일반 제품은 준비 PNG 바이트를 보존하지 않아 완전한 바이트 재생을 약속하지 않는다."),
            block("small", "자체 구현: 주문/자료 스키마, 원자 등록·실패 롤백, 버전/해시 결합, 디지털 제한, 화면, 이력·내보내기, 평가·감사. "
                  "재사용: 공개 사전학습 모델, MLX, FastAPI, Pydantic, Pillow. 모델을 직접 사전학습했다고 주장하지 않는다. [E6, E7]"),
        ]},
        {"title": "같은 사진, 두 주문 버전의 실제 실행", "kicker": "03 / 실제 MLX 연동 증거", "blocks": [
            block("body", "2026-10-02, 이미 사용한 MVTec LOCO AD screw_bag/train/good/016.png를 새 자료 업로드 API로 등록했다. "
                  "MVTec 출처와 CC BY-NC-SA 4.0을 진술했지만 서버 검증 상태는 user_declared_unverified로 유지했다. "
                  "참고 0장, 재시도 0회, 워밍업 0회로 G 관찰을 두 번 실행했다. [E1]"),
            block("table", rows=[
                ["단계", "주문 / 실제 관찰", "결과·시간"],
                ["R1 검사", "BOM 3/2/2/0 → 관찰 2/2/2/0", f"correct · {seconds[0]}초"],
                ["명시적 R2", "조작자의 사전 지정 지시로 BOM 2/2/2/0 승인", "R1 검사와 의견은 현재 근거에서 제외"],
                ["동일 사진 재사용", "저장 사진 바이트 SHA 동일; 새 사진 ID와 버전 연결", "모델 호출 0회; 새 추론 대기"],
                ["R2 검사", "BOM 2/2/2/0 → 관찰 2/2/2/0", f"ready · {seconds[1]}초"],
            ], widths=[0.20, 0.49, 0.31]),
            block("small", "수량 순서: 나사류 / 너트 / 와셔 / 브래킷. 시간은 저장된 check의 latency_ms이며 첫 검사는 콜드 로드를 포함한다. "
                  "전체 6회 실제 모델 생성; API 왕복 시간·화면 조작 시간과 혼용하지 않는다."),
            block("h2", "변경의 이유와 보존된 사실"),
            block("body", "3→2는 모델이 초록색 결과를 만들기 위해 수량을 줄인 것이 아니다. 이번 API 연동은 사전 지정된 조작자의 명시적 수량 변경을 직접 반영했다. "
                  "자연어 제안이나 AI의 자체 주문 수정으로 만든 결과가 아니다. "
                  "고정 주문의 부족분을 해결했다는 시연이 아니며 R1 차이 기록은 남는다."),
            block("table", rows=[
                ["검증 항목", "보존·거부 결과"],
                ["두 세대 이력", "서로 다른 check/사진 ID, 원래 AI 결과, 의견과 주문 스냅샷이 남고 최신성은 분리된다."],
                ["디지털 의견", "ENGINEERING-AGENT가 각 버전에 inconclusive를 기록. user_validation:false, physical_completion:false."],
                ["실물 완료", "두 버전 모두 HTTP 409로 거부. ready는 사진 수량 비교 결과이며 실물 완료가 아니다."],
                ["추적 가능성", "원본·저장·선언 결합, 실행 전후 소스, 모델 파일, 실제 입력/출력, ZIP 전 멤버 SHA를 확인했다."],
            ], widths=[0.23, 0.77]),
            block("callout", "이 실행은 정확도 평가나 사용자 실증이 아니다\n이미 노출된 동일 사진의 기능 연동 사례이며 실제 참여자 0명이다. "
                  "이후 실제 기록의 한국어·중국어 화면과 ZIP 다운로드도 읽기 전용으로 확인했다(31 GET, 추가 추론 0). "
                  "합성 계약·화면 확인·실제 모델 관찰을 별도로 집계한다. " + regression_text),
        ]},
        {"title": "전체 분모로 확인한 성과와 한계", "kicker": "04 / 평가 및 독립 감사", "blocks": [
            block("body", "방법·입력·채점 규칙을 고정한 뒤 실행하고 원문·실제 입력·규칙 계산을 독립적으로 재확인했다. "
                  "새 LOCO 24장은 이전에 보류된 조합 수량 라벨을 저자 설정과 논문에 따라 별도 규칙으로 유도한 검증이다. "
                  "저자가 제공한 네 범주 원생 계수표가 아니며, 물리적으로 독립된 현장 표본이라고 주장하지 않는다. [E2, E3]"),
            block("table", rows=[
                ["자료 / 방법", "C", "W", "U", "E/N", "주 AFR"],
                ["기존 공개 51장 / G", "41", "3", "7", "0/0", "3/51"],
                ["LOCO 조합 24장 / G", "23", "0", "1", "0/0", "0/24"],
                ["동일 24장 / 상수 2/2/2/0", "0", "24", "0", "0/0", "24/24"],
                ["동일 24장 / 전부 보류", "0", "0", "24", "0/0", "0/24"],
            ], widths=[0.40, 0.09, 0.09, 0.09, 0.12, 0.21]),
            block("small", "C=정확하고 사용 가능한 관찰, W=잘못된 확정 관찰, U=불확실/보류, E=실행 오류, N=미시도. "
                  "AFR은 허용 주문 중 하나라도 잘못 ready가 된 이미지 수/전체 계획 이미지 수. 주문 조합은 새 사진이 아니다."),
            block("h2", "24장 안에서도 적용 범위를 나눈다"),
            block("body", "네 수량 조합은 각 6장이다: 2/0/4/0, 2/1/3/0, 2/3/1/0, 2/4/0/0. "
                  "종류별 4개인 12장도 관찰 점수의 분모에 모두 포함했다. 단, 제품 BOM 입력은 종류별 최대 3개라 "
                  "정답과 같은 주문 생성 과제는 12장 N/A, 적용 가능한 나머지 12장 중 올바른 ready는 11장이다."),
            block("body", "주 지표는 이미지당 4범주 합법 주문 255개를 재비교한 AFR 0/24이다. 브래킷 0에 한정한 "
                  "보조 패널 63개도 0/24지만 주 지표를 대신하지 않는다. 71회 생성·163개 실제 입력·92개 신원 crop을 "
                  "검증한 독립 감사가 통과했다. 반복 주문 패널은 상관된 규칙 검사다."),
            block("callout", "0 AFR은 전부 정답이라는 뜻이 아니다\n전부 보류 기준선도 0 AFR이다. G는 23C·1U였으며, "
                  "과거 51장의 Screws 3개 확정 오류는 여전히 남는다. type_007의 nut 투영은 프로젝트의 기존 "
                  "분류 매핑이며 저자의 직접 영어 명명으로 단정하지 않는다. 두 자료의 분모를 합치지 않는다."),
            block("small", "새 결과로 생산 승격하지 않는다. 같은 LOCO 도메인, 저자 주석 완전성 의존, 전체 수량 6개·나사류 2개·브래킷 0개로 고정된 범위, "
                  "사전학습 데이터 노출 여부 미확인, 실제 작업시간 절감·현장 품질·사람 평가 미측정을 한계로 둔다. [E2-E5, E10]"),
        ]},
        {"title": "신규 개발분, 도입 가설, 증거 경로", "kicker": "05 / 완성도와 활용 계획", "blocks": [
            block("h2", "이번 개발분을 기존 자산과 구분한다"),
            block("body", "2026-09-26 시작한 원형에 이미 존재한 사진 관찰·주문 상태·공개 데이터 연구를 새로 만들었다고 주장하지 않는다. "
                  "공식 개발기간은 09-29부터 10-06까지다. "
                  "10월 2일의 v0.8 추가분은 사용자 자료 업로드와 고정 출처 결합, 원자 등록/실패 롤백, 동일 자료의 디지털 제한, "
                  "단계별 참고 추적, 실패 복구 화면, 신규 자료의 두 버전 검토·내보내기 연동이다. 이전 후보 실험의 성적을 "
                  "현재 제품 개선으로 합산하지 않는다. 핵심 소스 58경로의 비교는 전체 파일 수나 개발 시작 시각을 뜻하지 않는다. [E9, E16-E17]"),
            block("body", "기존 자산·공개 모델·라이브러리·AI 코딩 도구 사용은 별지 2에 출처와 신규 개발분으로 신고할 자료를 준비했다. "
                  "9월 26일 원형을 참가에 사용할 수 있다는 주최 측 확인 회신은 현재 증거에 없다. 이 보고서는 허가나 제출 완료를 뜻하지 않는다."),
            block("table", rows=[
                ["활용 가설", "검증할 다음 단계"],
                ["초기 사용자", "교육용 키트·소규모 조립 담당자가 사진과 주문을 주고받으며 버전별 검토 이력을 남기는 상황."],
                ["가치와 비용", "사진 재검토와 근거 정리 비용을 줄일 가능성. Apple Silicon Mac, 별도 로컬 모델과 대기 시간이 필요하며 절감 효과는 아직 측정하지 않았다."],
                ["수익 가설", "팀별 로컬 설치/도입 지원과 기록 보관·내보내기 운영 지원. 유료 고객·매출·구매 의향을 확인한 사실은 없다."],
                ["검증 계획", "동의한 실제 사용자로 완료/실패/협조 여부와 걸린 시간을 그대로 기록. 모델 오인·보류가 업무에 미치는 손실을 함께 측정."],
            ], widths=[0.23, 0.77]),
            block("h2", "평가자 실행 경로"),
            block("body", "소스와 고정 의존성을 설치하고 로컬 모델을 별도 준비한 뒤 실행한다. 작업대의 ‘사진 자료 주문 만들기’에서 "
                  "자기 파일과 출처 설명을 등록하거나, 별도 공개 갤러리 세 예제로 시작할 수 있다. "
                  "출처 URL은 자동 다운로드·권리 인증 기능이 아니다. 생성되는 기록은 개발 미리보기 범위다."),
            block("small", "실행: bash scripts/setup.sh → 모델 준비 → bash scripts/run.sh\n"
                  "주소: http://127.0.0.1:8765/?new=photo-document\n"
                  "안내: docs/v0.8/PHOTO_DOCUMENT_GUIDE_KO_ZH.md. 현재 버전 0.8.0.dev1; 정식 출시·대회 제출 전."),
            block("h2", "핵심 근거 색인"),
            block("refs", rows=[
                ["E1", "자료 두 버전 실제 실행", EVIDENCE["E1"]],
                ["E2-E3", "LOCO24 독립 감사·전체 분석", EVIDENCE["E2"] + " / " + EVIDENCE["E3"]],
                ["E4-E5", "기존 공개51 분석·감사", EVIDENCE["E4"] + " / " + EVIDENCE["E5"]],
                ["E6-E17", "제품·전체 회귀·결과·개발 이력", "전체 파일 경로와 SHA-256은 동봉 SOURCE_EVIDENCE.json에 기재"],
            ]),
            block("small", "상세 근거는 교부용 색인과 소스 패키지의 해당 경로를 참조한다. 큰 raw 실험·모델·사진은 외부 의존성으로 별도 보존한다. "
                  "해시는 무결성 단서이며 저작권·인물·장면 진위를 인증하지 않는다."),
        ]},
    ]
    tech = [{"title": "KitGuard AI Agent 기술 설명", "kicker": "TECHNICAL NOTE / 1 PAGE", "blocks": [
        block("body", "**목표**  사진 + 버전별 BOM + 출처 진술을 현재 검토 근거로 묶는다. 공개 갤러리와 사용자 자료의 출처 유형을 구분하고, "
              "자료를 실물 완료로 처리하지 않는다. 0.8.0.dev1 개발 미리보기이며 정식 제출본이 아니다."),
        block("table", rows=[
            ["구성", "구현과 통제"],
            ["로컬 인지", "Qwen3.6-27B-4bit / MLX. G: 원방향 + 90도 공간 목록, 명확한 합의 뒤 조건부 너트·와셔 crop 확인. 공간 900 / 신원 1,800 토큰. 모델에 BOM 정답을 주지 않는다."],
            ["규칙·도구 Agent", "관찰 → 현재 BOM 비교 → 차이·보류·수동 안내 → 명시 개정 → 근거 무효화 → 새 관찰 → 의견·ZIP. 자유 계획형이 아닌 서버 규칙 관리형 작업 흐름."],
            ["출처·원자성", "서버 user_declared_photo 유형; 첫 root/저장 SHA/원본 SHA/선언 SHA를 결합. 출처 설명 필수, HTTP(S) URL·이용 조건 선택. 업로드+DB 등록 실패는 롤백, 이후 다른 root로 교체 불가."],
            ["참고·감사", "참고는 종류 예시, 대상 수량 아님. 실제 범주/파일·준비 PNG SHA/순서/단계 상태를 검사에 저장. 현재 신원 단계는 참고 없음. 과거 누락 필드를 현재 참고로 보충하지 않음."],
            ["상태·실행 안전", "revision/photo/check/epoch와 모델 정체성을 결합. 실패·중단은 완료가 아님. 동일 사진 재사용은 새 촬영이 아니며 새 추론 필요. 의견은 모델 정답·현장 실증으로 전환하지 않음."],
        ], widths=[0.21, 0.79]),
        block("h2", "검증된 실행과 실패 경계"),
        block("body", f"실제 자료 API: 같은 016 사진 R1 3/2/2/0 → correct {seconds[0]}초; 조작자 명시 개정·같은 사진 재사용 뒤 "
              f"R2 2/2/2/0 → ready {seconds[1]}초. 2회 검사/6회 생성/0재시도, 두 세대 이력·ZIP SHA·실물 완료 거부 확인. "
              "ENGINEERING-AGENT의 inconclusive 의견이며 실제 사람 0명. [E1]"),
        block("body", "LOCO 조합 라벨 유도 24장 G: 23C/0W/1U/0E/0N, 주 AFR 0/24; 4개 수량 12장도 관찰 채점에 포함, "
              "같은 수량 주문은 12장 N/A·적용 11/12 ready. 상수 2/2/2/0은 24W, 전부 보류는 24U로 따로 비교. "
              "기존 51장 G의 41C/3W/7U와 분모를 합치지 않으며 3개 Screws 오류는 미해결. [E2-E5]"),
        block("small", "직접 구현: 자료/주문 상태, 결합·무효화·실패 복구, 화면과 증거 ZIP, 고정 실험·감사. 재사용: 공개 모델, MLX/FastAPI/Pydantic/Pillow; "
              "코드 작성·검토에 AI 도구 사용. 사전학습을 직접 수행하지 않음. 09-26 기존 원형과 10-02 신규분을 구분해 신고하며 참가 사용 허가 회신 미확인. [E6-E9, E16]"),
        block("callout", "적용 한계  동일 모델의 관련 관찰, 동일 도메인·저자 주석 의존, 사전학습 노출 미확인, 브래킷 양성 부재. "
              "현장 신뢰성·사용자 효익·산업 안전을 입증하지 않았다. 추가 실험의 통과를 생산 승격으로 간주하지 않는다."),
        block("small", "전체 근거 경로·SHA는 SOURCE_EVIDENCE.json 및 5쪽 결과보고서 색인 참조. 제품은 준비 PNG 바이트를 일반 저장하지 않는다. "
              "실제 실험 recorder의 raw 보존과 제품의 보존 범위를 구분한다."),
    ]}]
    return report, tech


class Renderer:
    def __init__(self, version, technical=False):
        self.version, self.technical = version, technical
        size = 9.8 if technical else 10.3
        base = {"fontName": "KR", "wordWrap": "CJK", "textColor": INK}
        self.styles = {
            "body": ParagraphStyle("body", **base, fontSize=size, leading=size * 1.52),
            "lead": ParagraphStyle("lead", **base, fontSize=12.4, leading=19),
            "small": ParagraphStyle("small", **base, fontSize=8.1 if technical else 8.6,
                                    leading=12.3 if technical else 13.1),
            "h2": ParagraphStyle("h2", **base, fontSize=11.8 if technical else 13.2,
                                 leading=17.8, spaceBefore=0),
            "cell": ParagraphStyle("cell", **base, fontSize=9.1 if technical else 9.4, leading=13.8),
            "th": ParagraphStyle("th", fontName="KR", wordWrap="CJK", textColor=colors.white,
                                 fontSize=9.1 if technical else 9.4, leading=13.8),
            "ref": ParagraphStyle("ref", **base, fontSize=7.9, leading=11.5),
        }
        self.styles["h2"].textColor = TEAL
        self.styles["small"].textColor = MUTED

    def flow(self, item):
        kind = item["kind"]
        if kind == "process":
            return Process(item["steps"]), 10
        if kind in {"table", "refs"}:
            style = self.styles["ref"] if kind == "refs" else self.styles["cell"]
            rows = item["rows"]
            widths = [WIDTH * x / sum(item.get("widths", [])) for x in item["widths"]] if "widths" in item else [53, 100, WIDTH - 153]
            cells = [[Paragraph(inline(text), self.styles["th"] if kind == "table" and i == 0 else style)
                      for text in row] for i, row in enumerate(rows)]
            table = Table(cells, colWidths=widths)
            commands = [("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                        ("TOPPADDING", (0, 0), (-1, -1), 6 if not self.technical else 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6 if not self.technical else 5),
                        ("LINEBELOW", (0, 0), (-1, -1), 0.35, LINE)]
            if kind == "table":
                commands += [("BACKGROUND", (0, 0), (-1, 0), TEAL),
                             ("ROWBACKGROUNDS", (0, 1), (-1, -1), [PALE, colors.white])]
            table.setStyle(TableStyle(commands))
            return table, 9
        if kind == "callout":
            p = Paragraph(inline(item["text"]), self.styles["body"])
            box = Table([[p]], colWidths=[WIDTH])
            box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PALE),
                ("LINEBEFORE", (0, 0), (0, -1), 2.5, TEAL),
                ("LEFTPADDING", (0, 0), (-1, -1), 11), ("RIGHTPADDING", (0, 0), (-1, -1), 11),
                ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9)]))
            return box, 9
        return Paragraph(inline(item["text"]), self.styles[kind]), (7 if kind != "h2" else 6)

    def render(self, pages, destination):
        if len(pages) > (1 if self.technical else 5):
            raise ValueError("A4 page budget exceeded")
        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4, pageCompression=1, invariant=1)
        pdf.setTitle("KitGuard Agent 기술 설명 - 개발 미리보기" if self.technical else "KitGuard 결과보고서 - 개발 미리보기")
        pdf.setAuthor("KitGuard")
        pdf.setSubject(self.version + " DEVELOPMENT PREVIEW - not a submitted/released artifact")
        layout = []
        for number, page in enumerate(pages, 1):
            pdf.setFillColor(TEAL)
            pdf.rect(LEFT, H - 32, 25, 3, fill=1, stroke=0)
            pdf.setFont("KR", 8)
            pdf.setFillColor(MUTED)
            pdf.drawString(LEFT + 34, H - 33, "KITGUARD / " + page["kicker"])
            pdf.setFillColor(AMBER)
            pdf.drawRightString(W - RIGHT, H - 33, "DEVELOPMENT PREVIEW")
            title = Paragraph(inline(page["title"]), ParagraphStyle("title", fontName="KR", fontSize=19 if self.technical else 23,
                              leading=26 if self.technical else 31, wordWrap="CJK", textColor=INK))
            _, height = title.wrap(WIDTH, 90)
            title.drawOn(pdf, LEFT, TOP - height)
            y, placements = TOP - height - (13 if self.technical else 16), []
            for item in page["blocks"]:
                flow, gap = self.flow(item)
                width, height = flow.wrapOn(pdf, WIDTH, TOP - BOTTOM)
                if width > WIDTH + 0.1 or y - height < BOTTOM:
                    raise ValueError(f"Overflow: {destination.name} page {number} {item['kind']} bottom={y-height:.2f}")
                flow.drawOn(pdf, LEFT, y - height)
                placements.append({"kind": item["kind"], "top": y, "bottom": y - height})
                y -= height + gap
            pdf.setStrokeColor(LINE)
            pdf.line(LEFT, 37, W - RIGHT, 37)
            pdf.setFont("KR", 7.8)
            pdf.setFillColor(MUTED)
            pdf.drawString(LEFT, 24, f"{self.version} / 2026-10-02 / 정식 출시·제출 전")
            pdf.drawRightString(W - RIGHT, 24, f"{number} / {len(pages)}")
            layout.append({"page": number, "blocks": placements, "bottom": y + gap})
            pdf.showPage()
        pdf.save()
        destination.write_bytes(buffer.getvalue())
        reader = PdfReader(destination)
        assert len(reader.pages) == len(pages)
        assert all("DEVELOPMENT PREVIEW" in p.extract_text() and ("KitGuard" in p.extract_text() or
                   "KITGUARD" in p.extract_text()) for p in reader.pages)
        return {"path": str(destination.relative_to(ROOT)), "sha256": sha(destination), "pages": len(pages),
                "body_font_pt": self.styles["body"].fontSize, "cell_font_pt": self.styles["cell"].fontSize,
                "layout": layout}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUT_DEFAULT)
    parser.add_argument("--regression-xml", type=Path)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if not output.is_relative_to(ROOT / "output/report/v0.8-preview"):
        raise ValueError("This preview builder writes only the new preview output tree")
    output.mkdir(parents=True, exist_ok=True)
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    assert version == "0.8.0.dev1", "Review wording when the project version changes"
    facts = {key: json.loads((ROOT / path).read_text()) for key, path in
             {"api": EVIDENCE["E1"], "audit": EVIDENCE["E2"], "analysis": EVIDENCE["E3"]}.items()}
    assert facts["api"]["status"] == "passed" and facts["api"]["inspect_attempts"] == 2
    assert facts["audit"]["status"] == "passed" and facts["audit"]["completed_attempts"] == 24
    assert facts["analysis"]["methods"]["spatial_guarded"]["outcomes"] == {"C": 23, "W": 0, "U": 1, "E": 0, "N": 0}
    regression = None
    if args.regression_xml:
        import xml.etree.ElementTree as ET
        tree = ET.parse(args.regression_xml).getroot()
        suites = list(tree) if tree.tag == "testsuites" else [tree]
        values = {k: sum(int(s.get(k, "0")) for s in suites) for k in ("tests", "errors", "failures", "skipped")}
        assert values["errors"] == values["failures"] == 0
        regression = {"passed": values["tests"] - values["skipped"], "path": str(args.regression_xml),
                      "sha256": sha(args.regression_xml), **values}
    pdfmetrics.registerFont(TTFont("KR", str(FONT)))
    pdfmetrics.registerFontFamily("KR", normal="KR", bold="KR", italic="KR", boldItalic="KR")
    report, technical = contents(facts, regression)
    content = {"version": version, "status": "development_preview", "report": report, "technical": technical}
    chars = json.dumps(content, ensure_ascii=False)
    cmap = pdfmetrics.getFont("KR").face.charToGlyph
    missing = sorted({c for c in plain(chars) if not c.isspace() and ord(c) not in cmap})
    assert not missing, missing
    save(output / "CONTENT_SOURCE.json", content)
    evidence = {key: {"path": path, "sha256": sha(ROOT / path)} for key, path in EVIDENCE.items()}
    save(output / "SOURCE_EVIDENCE.json", {"sources": evidence, "regression": regression,
        "local_pdf_links": "Labels only; no relocated relative clickable links", "evidence_scope": "No source archive self-hash"})
    documents = []
    for pages, name, tech in [(report, "KitGuard_결과보고서_v0.8_preview.pdf", False),
                              (technical, "KitGuard_Agent_기술설명_v0.8_preview.pdf", True)]:
        documents.append(Renderer(version, tech).render(pages, output / name))
    manifest = {"schema": "kitguard.v08.preview-pdfs.v1", "version": version,
        "builder": {"path": str(Path(__file__).relative_to(ROOT)), "sha256": sha(__file__)},
        "font": {"path": str(FONT), "sha256": sha(FONT)}, "documents": documents,
        "content_source_sha256": sha(output / "CONTENT_SOURCE.json"),
        "source_evidence_sha256": sha(output / "SOURCE_EVIDENCE.json"),
        "regression": regression, "visual_qa": "pending_all_page_render_and_visual_review"}
    save(output / "BUILD_MANIFEST.json", manifest)
    print(json.dumps([{k: d[k] for k in ("path", "sha256", "pages")} for d in documents], ensure_ascii=False))


if __name__ == "__main__":
    main()
