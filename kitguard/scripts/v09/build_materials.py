"""Build Korean competition PDFs and a source-backed facts file for v0.9.

PDF operation marker is invoked once by the author before this script.
All screenshots are original CUA captures, fitted without retouching.
"""
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

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/competition-v0.9"
EVIDENCE = {
    "A": "test-results/v0.9/ACCEPTANCE.json",
    "B": "test-results/v0.9/browser/r2-order.json",
    "C": "test-results/v0.9/full-regression-v2.xml",
    "D": "docs/v0.8/LOCO_COMBINED_DECISION.json",
    "E": "docs/v0.7/FINAL_EVALUATION.md",
    "F": "docs/v0.9/SOURCE_AI_DISCLOSURE_KO.md",
    "G": "docs/v0.9/RELEASE_NOTES.md",
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def facts():
    order = json.loads((ROOT / EVIDENCE["B"]).read_text())["order"]
    checks = order["checks"]
    assert len(checks) == 2 and all(c["backend"] == "mlx" for c in checks)
    assert [c["latency_ms"] for c in checks] == [55052, 49773]
    assert [c["decision"] for c in checks] == ["correct", "ready"]
    assert all(c["observed"] == {"bolt": 2, "nut": 2, "washer": 2, "bracket": 0} for c in checks)
    assert len({c["photo_sha256"] for c in checks}) == 1
    resolutions = order["digital_resolutions"]
    assert [r["outcome"] for r in resolutions] == ["mismatch", "matched"]
    assert all(r["purpose"] == "engineering_rehearsal" and not r["user_validation"]
               and not r["physical_completion"] for r in resolutions)
    suites = ET.parse(ROOT / EVIDENCE["C"]).getroot().findall("testsuite")
    assert sum(int(s.get("tests")) for s in suites) == 1826
    assert not sum(int(s.get("failures")) + int(s.get("errors")) for s in suites)
    return {"version": "0.9.0.dev1", "date": "2026-10-03", "tests_passed": 1826,
            "checks": [{k: c[k] for k in ("id", "revision", "backend", "latency_ms", "decision", "observed")} for c in checks],
            "resolution_outcomes": [r["outcome"] for r in resolutions], "human_participants": 0,
            "physical_completion": 0,
            "sources": {k: {"path": p, "sha256": sha(ROOT / p)} for k, p in EVIDENCE.items()}}


def content():
    report = [
        {"title": "사진과 주문의 검토를 끝까지 연결하는\nKitGuard", "kicker": "01  문제와 사용자", "blocks": [
            block("lead", "사진의 수량을 확인한 뒤, 누가 무엇을 근거로 결론을 냈는지까지 남깁니다."),
            block("body", "교육 키트·소규모 조립 업무에서는 사진과 수량표가 따로 전달될 수 있다. 요구 수량이 바뀌면 과거 사진의 판단을 그대로 사용하기 쉽고, 확인자의 결론도 메시지에 흩어진다. KitGuard는 이 작업을 사진 등록부터 AI 관찰, 위치 표시 복검, 개정, 증거 내보내기까지 연결하는 로컬 디지털 검토 MVP다. 대상 업무와 효익은 검증할 가설이며 고객 도입 실적은 아직 없다."),
            block("process", steps=[("사진·주문", "출처와 범위 등록"), ("로컬 AI", "관찰·수량 비교"), ("위치 복검", "결론과 이유 저장"), ("개정·증거", "새 검사·ZIP")]),
            block("h2", "이번 버전의 핵심 기능"),
            block("table", rows=[["기능", "사용자가 얻는 결과"],
                ["사진 자료 주문", "합법적으로 보유한 사진과 종류별 BOM을 함께 등록한다. 출처 선언과 원본 해시를 보존한다."],
                ["AI 비교와 보류", "나사류·너트·와셔·브래킷의 관찰을 현재 BOM과 비교하고, 모호하면 추가 근거를 요구한다."],
                ["그림 위 복검", "보이는 대상을 직접 표시한다. 프로그램이 표시를 계수하여 일치·차이·추가 자료 결론을 만든다."],
                ["개정과 새 검사", "BOM 변경 후 과거 결론을 이력으로 돌린다. 같은 사진도 명시적으로 재사용하고 다시 추론한다."],
                ["증거 내보내기", "원래 AI 결과, 검토 위치·수량·이유, 주문 버전, 사진과 SHA를 함께 내려받는다."]], widths=[0.23, 0.77]),
            block("callout", "현존 장비로 실행\nApple M5 Pro / 통합 메모리 64GB / 로컬 Qwen 4-bit. 이번 개발과 시연은 기존 공개 사진을 사용했으며 새 실물 구매·외부 GPU 신청·클라우드 추론 키 없이 수행했다."),
            block("small", "팀 해피 / 일반부 / 업무 생산성 향상 AI Agent. 사진의 거친 범주와 수량을 검토하는 범위이며 SKU·규격·재질 인증과 실물 출고 승인은 제공하지 않는다. [A, B]"),
        ]},
        {"title": "복검의 근거가 사진에 남습니다", "kicker": "02  실제 화면과 기능", "blocks": [
            block("body", "이번 신규 기능은 의견만 남기던 흐름에 별도의 검토 결론을 더한다. 검토자는 위치와 범주를 표시하거나 추가 자료를 요청한다. AI 원관찰은 수정하지 않으며, 검토값을 모델의 정답으로 사용하지 않는다."),
            block("image", path="test-results/v0.9/browser/04-r2-marked.jpg", height=282),
            block("small", "실제 로컬 브라우저 화면. 표시 6개는 ENGINEERING-AGENT가 기능 리허설로 입력했으며 실제 참여자 0명이다. 원사진: MVTec LOCO AD screw_bag/train/good/016.png, CC BY-NC-SA 4.0. 이미지 수정 없이 화면 전체를 축소했다."),
            block("table", rows=[["재현한 작업", "저장된 사실"],
                ["R1 요구 3/2/2/0", "AI 관찰 2/2/2/0, 55.052초. 위치 6개를 표시한 검토도 나사류 1개 차이로 저장."],
                ["명시적 주문 변경", "요구를 R2 2/2/2/0으로 변경. R1 검사·검토 결론이 현재 근거에서 제외됨."],
                ["같은 사진의 R2", "새 AI 관찰 2/2/2/0, 49.773초. 새 위치 복검 후 수량 일치. R1 차이 이력 유지."],
                ["다운로드와 확인", "브라우저에서 증거 ZIP을 내려받고 모든 목록 해시를 검증. 추출 HTML과 위치 표시를 로컬 정적 서버로 확인."]], widths=[0.27, 0.73]),
            block("small", "수량 순서: 나사류/너트/와셔/브래킷. 이 시연의 3→2는 요구 변경이다. 부품을 보충해 고정 주문을 만족시킨 사례가 아니다. 2회 관찰은 이미 노출된 같은 개발 사진의 기능 검증이며 새 정확도 분모가 아니다. [A, B]"),
        ]},
        {"title": "모델 관찰과 상태 제어의 역할", "kicker": "03  AI Agent 구조", "blocks": [
            block("lead", "사진 해석은 로컬 VLM이, 수량 대조와 근거의 유효성은 프로그램이 담당합니다."),
            block("table", rows=[["단계", "구현과 실행 조건"],
                ["입력", "사진·출처 선언·BOM·검사 범위를 저장. 기본 주문은 종류별 0-3개, 총 1-12개."],
                ["판단", "Qwen3.6-27B-4bit / MLX. 원방향·90도 회전 공간 목록을 생성하고 조건 충족 시 너트·와셔 국소 확인. 관찰 프롬프트에 BOM 정답을 주지 않음."],
                ["도구 실행", "Python이 목록을 계수해 BOM과 비교. 재촬영/수동 확인/차이/사진 수량 일치 안내. FastAPI·SQLite가 검사 작업과 이력을 유지."],
                ["Feedback", "의견과 위치 표시 결론을 별도 저장. 확인자가 결론을 내리며 AI 원결과는 유지. 새 의견은 기존 결론을 만료시켜 재검토 요구."],
                ["Memory / State", "주문 revision, 사진 ID·SHA, evidence epoch, check SHA, 실행 identity, 의견 집합 hash와 직전 결론을 묶음. 새 자료·검사·버전·실행 정체 변경 후 과거 근거 재사용 차단."],
                ["결과", "사진·JSON·정적 HTML·SHA 목록으로 내보냄. 실물 완료와 디지털 결론을 구분하고 반복 요청의 중복 저장 방지."]], widths=[0.20, 0.80]),
            block("h2", "제한된 작업 Agent의 구현 범위"),
            block("body", "도구 연결과 상태 전이는 고정 정책으로 관리한다. 모델이 자유롭게 계획하거나 주문을 스스로 수정하지 않는다. 구조화 관찰과 검토 기록을 실제 작업 상태에 반영하지만 물리 작업은 제어하지 않는다. 기본 모델과 관찰 절차는 이번 버전에서 교체·미세조정하지 않았다."),
            block("h2", "실패도 사용자가 확인할 수 있게"),
            block("body", "비동기 검사와 새로고침 복구, 실패 후 명시적 재시도, 오래된 폼 거절, 동시 저장 충돌과 idempotency를 관리한다. 화면의 위치는 검토자의 진술이며 시스템이 물체 정답을 인증하지 않는다. 불명확한 사진은 추가 자료 요청 결론으로 남길 수 있다."),
            block("small", "구현: kitguard/digital_resolution.py, public_review.py, evidence.py와 static/digital-resolution.js. 기존 vision.py, spatial.py, consensus.py, identity.py의 관찰 프로토콜은 그대로 유지. [A, G]"),
        ]},
        {"title": "모델 성과와 소프트웨어 검증", "kicker": "04  전체 결과와 한계", "blocks": [
            block("table", rows=[["모델 자료 / 기본 G", "정확 C", "오류 W", "보류 U", "실패/미실행"],
                ["기존 공개 51장", "41", "3", "7", "0 / 0"],
                ["LOCO 조합 24장", "23", "0", "1", "0 / 0"]], widths=[0.42, 0.14, 0.14, 0.14, 0.18]),
            block("body", "C는 정확하고 실행 가능한 관찰, W는 잘못된 확정 관찰, U는 불확실/보류다. 24장은 저자의 조합 라벨로 수량을 유도한 한 도메인의 제한된 검증이며, 총 6개·나사류 2개·브래킷 0개 조건이다. 기존 51장의 세 오류를 지우거나 분모를 합치지 않는다. 참고·검출기·분류기 연구 후보는 전이 문제를 해결하지 못하여 기본 모델에 채택하지 않았다."),
            block("body", "24장에 합법 BOM 255개를 각각 대조한 오확정 발생 사진은 0/24였다. 전부 보류 기준선도 0/24이므로 이 수치만으로 유용성을 주장할 수 없다. 수량 4개를 포함한 12장은 같은 수량의 합법 BOM을 만들 수 없어 일치 주문 과제는 N/A다. 나머지 12장 중 올바른 일치는 11장이다. 반복 BOM은 독립 사진이 아니다. [D, E]"),
            block("h2", "대표 기능 테스트 5건"),
            block("table", rows=[["종류", "입력·검증", "결과"],
                ["실제 MLX + UI", "R1 사진과 3/2/2/0 주문", "관찰 2/2/2/0, 차이 검토 저장"],
                ["실제 UI + MLX", "R2 명시 변경과 동일 사진 재검사", "이전 결론 만료, 새 일치 검토 저장"],
                ["합성 계약", "새 의견·오래된 폼·identity 변경", "만료 또는 409 거절"],
                ["합성 계약", "추가 자료 요청·반복 저장", "수량 확정 없이 보존, 중복 방지"],
                ["실제 다운로드", "증거 ZIP·HTML·사진 위치", "전체 SHA 일치, 로컬 서버 표시 확인"]], widths=[0.23, 0.44, 0.33]),
            block("callout", "1,826개 회귀 테스트 통과 / 실제 참여자 0명\n회귀는 HTTP·상태·입력·증거 계약 검증이다. 모델 정확도·사람 수·현장 효익으로 환산하지 않는다. 2회의 실제 관찰은 55.052초와 49.773초이며 사용자 전체 작업시간은 측정하지 않았다. [A-C]"),
            block("small", "현재 한계: 혼동되는 작은 부품, 브래킷 양성 검증 부족, 가림·조명 변화, 같은 모델의 상관된 반복 판단, 사전학습 노출 미확인. 실물 출고·산업 안전 용도로 검증하지 않았다."),
        ]},
        {"title": "도입 가설과 개발 기여", "kicker": "05  활용·출처·다음 검증", "blocks": [
            block("h2", "첫 사용자는 사진으로 키트를 검토하는 담당자"),
            block("body", "초기 도입 가설은 교육 키트 운영자와 소규모 조립 담당자다. 먼저 사진·수량표를 주고받는 한 작업을 로컬 단일 사용자 도구로 지원한다. 담당자가 기존 방식과 KitGuard로 같은 범위의 작업을 수행하고 전체 소요시간·놓친 차이·잘못된 일치·도움 요청을 비교한다. 현재 시간 절감·구매 의향·고객 수를 측정하지 않았다."),
            block("table", rows=[["사업화 가설", "검증 후 진행할 사항"],
                ["수익 방식", "조직별 로컬 설치·업무 양식 설정·유지보수 계약. 가격은 인터뷰와 파일럿 후 결정."],
                ["도입 조건", "고객이 권리를 확보한 사진, 적합한 로컬 장비, 담당자의 최종 확인. 비상업 연구 사진을 상용 고객 데이터로 전용하지 않음."],
                ["확장 순서", "한 업무에서 효익 확인 후 클래스별 자료 확보, 모호한 부품의 검증 개선, 다중 사용자 권한·감사 관리."]], widths=[0.24, 0.76]),
            block("h2", "기존 자산과 대회 기간의 추가분"),
            block("body", "실제 개발은 9월26일 시작했다. 공식 개발기간은 9월29일-10월6일이다. 기존 사진 처리·관찰·주문·증거 엔진을 재사용했다. 대회 기간에는 비동기 검사·복구, 사진 자료 주문, 디지털 의견·개정 재검사, 참고 입력 추적을 추가했고, 10월3일 위치 복검 결론·의견 변경 만료·오프라인 위치 근거를 구현했다. 시작일 코드 스냅샷이나 사람별 작성 비율을 보유했다고 주장하지 않는다."),
            block("body", "OpenAI Codex를 코드 작성·수정·검사·실험·문서와 발표자료 제작에 광범위하게 사용했다. 기반 VLM은 공개 사전학습 모델이며 팀이 새로 학습하지 않았다. 별도 연구 검출기·분류기 학습은 있었지만 기본 제품에 승격하지 않았다. 원출처·버전·라이선스·AI 보조 범위는 출처 공개 문서에 연결한다."),
            block("callout", "자가평가 Level 3 MVP\n한 디지털 검토 흐름을 실제로 실행·보존했다. Level 4 Pilot의 실사용 효과는 아직 확인하지 않았다. 소스 ZIP, 5쪽 보고서, 1쪽 기술설명, 9장 발표자료, 3분 이내 영상으로 검토할 수 있게 준비한다."),
            block("small", "근거 경로: [A] test-results/v0.9/ACCEPTANCE.json  [B] browser/r2-order.json  [C] full-regression-v2.xml (B,C는 A와 같은 디렉터리 계열). [D] docs/v0.8/LOCO_COMBINED_DECISION.json  [E] docs/v0.7/FINAL_EVALUATION.md  [F] docs/v0.9/SOURCE_AI_DISCLOSURE_KO.md  [G] docs/v0.9/RELEASE_NOTES.md. 패키지 facts.json에 경로와 SHA 수록."),
            block("small", "공식 기준: contest.gnict.org/bbs/board.php?bo_table=notice&wr_id=5 (10월2일 공지, 10월3일 확인). 최종 제출 10월6일 12:00 KST. 기존 자산의 이용 조건과 개별 자료 라이선스를 준수한다. 이 자료의 생성은 대회 제출·접수 완료를 뜻하지 않는다."),
        ]},
    ]
    rows = [
        ["항목", "KitGuard / 2026-10-03"],
        ["팀명 / 부문 / 주제", "해피 / 일반부 / 업무 생산성 향상 AI Agent"],
        ["작품명", "KitGuard: 사진·BOM 디지털 검토 Agent"],
        ["해결 문제", "사진과 주문 버전이 분리되고 복검 근거가 흩어지는 작업"],
        ["대상사용자", "교육 키트 운영자·소규모 조립 담당자 (도입 가설)"],
        ["Agent Goal", "사진 수량과 현재 BOM 차이를 확인하고 근거 있는 검토 결론과 이력을 보존"],
        ["사용 AI/LLM/모델", "Qwen3.6-27B-4bit / MLX / spatial_guarded. 기반 VLM 미세조정 없음"],
        ["Tool/API/Data/장비", "FastAPI·SQLite·Pillow·로컬 브라우저 / MVTec 공개 사진 / 기존 M5 Pro 64GB"],
        ["Memory/State/Feedback", "revision·사진 SHA·check·epoch·실행 identity와 의견 집합을 결합. 위치 복검을 원 AI와 별도 저장. 새 버전·검사·의견 후 과거 결론 만료"],
        ["핵심 Workflow\nEnd-to-End", "사진·BOM 등록 → 원방향·회전 AI 관찰 및 조건부 국소 확인 → 프로그램 계수·비교 → 위치 표시/추가 자료 결론 → 개정 후 재검사 → JSON·HTML·사진 ZIP"],
        ["핵심기능 5개", "① 출처 결합 자료 주문 ② 로컬 AI 대조 ③ 위치 복검 결론 ④ 버전 변경·재검사 ⑤ 검토 근거 내보내기"],
        ["기존자산 / 8일 신규", "9/26 시작한 관찰·주문·증거 엔진 재사용. 9/30 이후 비동기 복구·자료 주문·개정 재검사 추가. 10/3 위치 결론·의견 만료·오프라인 위치 근거 추가"],
        ["대표 테스트 5건", "① 실제 MLX R1 차이 55.052초 ② 실제 MLX R2 일치 49.773초 ③ 합성: 오래된 결론/폼 만료·거절 ④ 합성: 추가 자료·중복 요청 보존 ⑤ 실제 ZIP 다운로드·전체 해시·로컬 HTML 표시 통과"],
        ["현재 완성도 Level", "자가평가 Level 3 MVP. 실제 참여자 0명, 현장 효익 미측정"],
        ["소스코드/저장소", "KitGuard_source_v0.9.zip / kitguard/ / 실행: bash scripts/run_competition.sh"],
        ["정보출처 및 기타", "회귀 1,826 통과. 모델 기존51 C41/W3/U7, LOCO24 C23/W0/U1 (분모 분리). MVTec CC BY-NC-SA 4.0. Codex 개발·문서 보조 공개. docs/v0.9/SOURCE_AI_DISCLOSURE_KO.md 참조"],
    ]
    technical = [{"title": "AI Agent 기술설명서", "kicker": "별지 1  공식 항목 대응", "blocks": [
        block("table", rows=rows, widths=[0.26, 0.74]),
        block("small", "사진 자료 검토 전용. 위치 표시는 검토자 진술이며 원 AI 관찰을 바꾸거나 실물 출고를 승인하지 않는다. 공식 항목에 맞춘 1쪽 작성본, 자가평가이며 대회 접수 결과는 아니다."),
    ]}]
    return report, technical


class CompetitionRenderer(Renderer):
    def flow(self, item):
        if item["kind"] == "image":
            from PIL import Image as PILImage
            source = ROOT / item["path"]
            w, h = PILImage.open(source).size
            scale = min(WIDTH / w, item["height"] / h)
            return Image(str(source), width=w * scale, height=h * scale), 7
        return super().flow(item)

    def render(self, pages, destination):
        assert len(pages) <= (1 if self.technical else 5)
        stream = io.BytesIO()
        pdf = canvas.Canvas(stream, pagesize=A4, pageCompression=1, invariant=1)
        pdf.setTitle("KitGuard AI Agent 기술설명서" if self.technical else "KitGuard 결과보고서")
        pdf.setAuthor("해피 / AI-assisted")
        layout = []
        for n, page in enumerate(pages, 1):
            pdf.setFillColor(TEAL); pdf.rect(LEFT, H - 32, 25, 3, fill=1, stroke=0)
            pdf.setFont("KR", 8); pdf.setFillColor(MUTED)
            pdf.drawString(LEFT + 34, H - 33, "KITGUARD / " + page["kicker"])
            title = Paragraph(inline(page["title"]), ParagraphStyle("title", fontName="KR", fontSize=20 if self.technical else 23, leading=30, wordWrap="CJK", textColor=INK))
            _, h = title.wrap(WIDTH, 100); title.drawOn(pdf, LEFT, TOP - h)
            y = TOP - h - 14
            for item in page["blocks"]:
                flow, gap = self.flow(item); w, h = flow.wrapOn(pdf, WIDTH, TOP - BOTTOM)
                if w > WIDTH + .1 or y - h < BOTTOM:
                    raise ValueError(f"Overflow {destination.name} p{n} {item['kind']} {y-h:.1f}")
                flow.drawOn(pdf, LEFT, y - h); y -= h + gap
            pdf.setStrokeColor(LINE); pdf.line(LEFT, 37, W - RIGHT, 37)
            pdf.setFont("KR", 7.8); pdf.setFillColor(MUTED)
            pdf.drawString(LEFT, 24, "0.9.0.dev1 / 2026-10-03 / 해피 / 제출 전 검토본")
            pdf.drawRightString(W - RIGHT, 24, f"{n} / {len(pages)}")
            layout.append({"page": n, "bottom": y}); pdf.showPage()
        pdf.save(); destination.write_bytes(stream.getvalue())
        assert len(PdfReader(destination).pages) == len(pages)
        return {"path": destination.name, "pages": len(pages), "sha256": sha(destination), "layout": layout}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    f = facts(); save(OUT / "facts.json", f)
    pdfmetrics.registerFont(TTFont("KR", str(FONT)))
    pdfmetrics.registerFontFamily("KR", normal="KR", bold="KR", italic="KR", boldItalic="KR")
    report, technical = content()
    save(OUT / "content-source.json", {"report": report, "technical": technical})
    docs = []
    for pages, name, tech in [(report, "KitGuard_report_5p.pdf", False), (technical, "KitGuard_agent_1p.pdf", True)]:
        docs.append(CompetitionRenderer("0.9.0.dev1", tech).render(pages, OUT / name))
    save(OUT / "pdf-build.json", {"documents": docs, "builder_sha256": sha(__file__), "visual_qa": "pending"})
    print(json.dumps(docs, ensure_ascii=False))


if __name__ == "__main__":
    main()
