"""Final Korean submission materials, revising copy without changing dev4 evidence."""
from __future__ import annotations

import io
import json
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from scripts.scoring import build_materials as previous

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/submission-final-20261005"
REVISION = "20261005"


def revise(report, technical):
    report[0]["title"] = "KitGuard: 현재 주문과 연결된 사진 검토"
    report[0]["blocks"][0]["text"] = (
        "팀 해피 / 일반부 / 업무혁신, 생산성향상 AI Agent. 국립창원대학교 소속 "
        "팀장 남청청, 팀원 이개심. 소프트웨어 0.9.0.dev4, 최종 자료 개정 20261005. "
        "사진과 주문 수량표(BOM)를 따로 관리하면 주문이 바뀐 뒤에도 이전 AI의 ‘일치’ 결과를 "
        "현재 주문에 적용할 수 있다. KitGuard는 검토 대상 사진과 현재 주문 버전을 함께 고정하고, "
        "새 모델 검사에서 차이 또는 불확실성을 기록한다."
    )
    report[0]["blocks"][1]["text"] = "한 번 맡긴 현재 자료를 검토하고 근거를 저장"
    report[0]["blocks"][2]["text"] = (
        "사용자가 보유한 사진과 BOM을 등록하고 자율 검토를 시작한다. Agent는 입력을 확인하고 "
        "로컬 모델 검사를 실행한 뒤 결과에 맞는 후속 도구를 선택한다. 차이는 목록으로 남기고, "
        "불확실성은 추가 자료 요청으로 보존한다. 완료 시 사진·주문·검사 이력을 증거 ZIP으로 "
        "묶는다. 입력이 바뀌면 이전 결과를 현재 근거에서 제외하고 새 목표를 요구한다."
    )
    report[0]["blocks"][-1]["text"] = (
        "대상 사용자 가설은 교육 키트 운영자와 소규모 조립 자료 검토자다. 현재 네 가지 부품 "
        "범주(나사류·너트·와셔·브래킷), 종류별 BOM 0-3개를 지원한다. 핵심 가치는 ‘어느 사진과 "
        "어느 주문을 확인했는가’를 결과와 함께 보존하는 것이다. 현재 Level 3 MVP이며, "
        "실제 사용자 효과·세부 규격·SKU 동일성·실물 출고는 검증 범위에 포함하지 않는다."
    )
    report[2]["blocks"][3]["text"] = (
        "사진 관찰이 2/2/2/0이고 R1의 요구도 같을 때 일치 결과를 기록했다. 이후 미리 정한 "
        "R2 요구를 3/2/2/0으로 바꿨다. 같은 저장 관찰을 쓰면서 버전 결합만 제거한 CPU 대조는 "
        "옛 ready를 계속 반환했다. KitGuard는 옛 목표와 검사를 거절했다. 같은 사진을 명시적으로 "
        "재사용한 새 실제 검사에서는 나사류 1개 부족을 기록했다. 이 기능 제거 대조는 요구 변경 "
        "후 오래된 일치 결과의 재사용을 차단한 사례이며, 경쟁 제품 비교나 통계적 효과 측정은 아니다."
    )
    for row in report[2]["blocks"][4]["rows"]:
        if row[0] == "LOCO 조합24장":
            row[0] = "LOCO 별도 평가24장"
    report[2]["blocks"][5]["text"] = (
        "C=정확한 확정, W=잘못 확정, U=불확실, E=실행 오류, N=미시도. LOCO24는 "
        "동일 도메인의 별도 고정 평가이며 독립적인 실행·분모 감사가 통과했다. 전체 부품6개, "
        "브래킷 양성0의 제한이 있고 물리·세션 독립성은 미확인이다. 51장과 합산하지 않는다. [E-F]"
    )
    report[4]["blocks"][1]["text"] = (
        "첫 도입 가설은 한 담당자가 사진과 주문의 비교 근거를 남겨야 하는 업무다. 설치와 "
        "업무 양식 설정·유지보수 서비스를 사업 방식으로 검토한다. 현재 확인한 효과는 모의 주문 "
        "변경에서 옛 일치 결과의 재사용을 막고 새 차이 기록을 만든 것이다. 사람의 작업시간 "
        "절감·가격·구매 의향은 측정하지 않았다. 고객 적용에는 사용권을 확보한 자료와 적합한 "
        "로컬 장비가 필요하다."
    )
    report[4]["blocks"][-2]["text"] = (
        "최종 제출자료5종\n보고서5쪽 / Agent 기술설명1쪽 / KitGuard_source.zip / "
        "177.417초 실제 실행 영상 / 발표자료9장. 소프트웨어는0.9.0.dev4이며 이번 개정은 "
        "제출 문구·팀 정보·파일명·표시 호환성을 정리했다. 모델과 인식 알고리즘은 변경하지 않았다."
    )
    report[4]["blocks"][-1]["text"] = (
        "근거: [A]GOAL_ACCEPTANCE [B]machine-tasks/RESULTS [C]all-run [D]full-regression "
        "[E]LOCO_COMBINED_DECISION [F]FINAL_EVALUATION [G]출처·AI 공개 [H]공식 운영규정 "
        "[I]CAPACITY. facts.json에 경로와 SHA. 10월2일 공식 공지5: "
        "contest.gnict.org/bbs/board.php?bo_table=notice&wr_id=5. 마감10월6일12:00 KST."
    )
    live = json.loads((ROOT / "test-results/submission-final-20261005/live-summary.json").read_text())
    assert live["status"] == "completed" and live["scenarios"] == 3 and live["real_mlx_checks"] == 4
    report[3]["blocks"][1]["text"] += (
        f"\n10/5 최종 실행 점검: 기존 공개3장으로3개 시나리오, 실제MLX4회, "
        f"{live['elapsed_ms']/1000:.3f}초. 기존 사진의 엔지니어링 재실행이며 새 정확도 분모는 추가하지 않았다. [J]"
    )
    report[4]["blocks"][-1]["text"] = report[4]["blocks"][-1]["text"].replace(
        "[I]CAPACITY.", "[I]CAPACITY [J]10/5 live-summary.")
    rows = technical[0]["blocks"][0]["rows"]
    rows[0][1] = "KitGuard / 0.9.0.dev4 / 최종 자료 개정20261005"
    rows[1][1] = "해피 / 일반부 / 업무혁신, 생산성향상 AI Agent. 팀장 남청청, 팀원 이개심"
    for row in rows:
        if row[0] == "소스코드·실행":
            row[1] = "KitGuard_source.zip / SOURCE_PACKAGE.md / bash scripts/run_competition.sh. 모델 가중치·의존성 별도 준비"
        elif row[0] == "기존자산·기간 신규":
            row[1] += ". 10/5 자료 개정에서 모델·인식 알고리즘 변경 없음"
        elif row[0] == "출처·오류·AI 보조":
            row[1] = "MVTec CC BY-NC-SA4.0. Codex 보조 공개. 회귀1877. 기존51 C41/W3/U7, LOCO 별도24 C23/W0/U1"
    technical[0]["blocks"][1]["text"] = (
        "출처·AI 사용은 SOURCE_AI_DISCLOSURE_KO.md에 공개한다. 실물 완료·SKU 동일성은 검증하지 않았다. "
        "목표 입력이 바뀌면 새 검토를 시작하며 AI가 BOM을 임의 수정하지 않는다."
    )
    # Natural Korean category wording throughout inherited copy.
    for pages in (report, technical):
        for page in pages:
            for item in page["blocks"]:
                if isinstance(item.get("text"), str):
                    item["text"] = item["text"].replace("굵은 종류", "주요 범주")
                if "rows" in item:
                    item["rows"] = [[x.replace("굵은 종류", "주요 범주") for x in row] for row in item["rows"]]
    return report, technical


class SubmissionRenderer(previous.FinalRenderer):
    def render(self, pages, destination):
        assert len(pages) == (1 if self.technical else 5)
        stream = io.BytesIO()
        pdf = canvas.Canvas(stream, pagesize=previous.A4, pageCompression=1, invariant=1)
        pdf.setTitle("KitGuard AI Agent 기술설명서" if self.technical else "KitGuard 개발완료보고서")
        pdf.setAuthor("해피 / 남청청 / 이개심 / AI-assisted")
        layout = []
        for number, page in enumerate(pages, 1):
            pdf.setFont("KR", 8)
            pdf.setFillColor(previous.MUTED)
            pdf.drawString(previous.LEFT, previous.H - 33, "KITGUARD / " + page["kicker"])
            title = Paragraph(previous.inline(page["title"]), ParagraphStyle(
                "title", fontName="KR", fontSize=20 if self.technical else 23,
                leading=30, wordWrap="CJK", textColor=previous.INK))
            _, height = title.wrap(previous.WIDTH, 100)
            title.drawOn(pdf, previous.LEFT, previous.TOP - height)
            y = previous.TOP - height - 14
            for item in page["blocks"]:
                flow, gap = self.flow(item)
                width, height = flow.wrapOn(pdf, previous.WIDTH, previous.TOP - previous.BOTTOM)
                if width > previous.WIDTH + .1 or y - height < previous.BOTTOM:
                    raise ValueError(f"Overflow {destination.name} p{number} {item['kind']} {y-height:.1f}")
                flow.drawOn(pdf, previous.LEFT, y-height)
                y -= height + gap
            pdf.setStrokeColor(previous.LINE)
            pdf.line(previous.LEFT, 37, previous.W - previous.RIGHT, 37)
            pdf.setFont("KR", 7.5)
            pdf.setFillColor(previous.MUTED)
            pdf.drawString(previous.LEFT, 24, "0.9.0.dev4 / 해피 / 최종 자료 개정 20261005")
            pdf.drawRightString(previous.W-previous.RIGHT, 24, f"{number} / {len(pages)}")
            layout.append({"page": number, "bottom": y})
            pdf.showPage()
        pdf.save()
        destination.write_bytes(stream.getvalue())
        assert len(PdfReader(destination).pages) == len(pages)
        return {"path": destination.name, "pages": len(pages), "sha256": previous.sha(destination), "layout": layout}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    facts = json.loads((OUT / "facts.json").read_text())
    assert facts["version"] == "0.9.0.dev4" and facts["tests_passed"] == 1877
    pdfmetrics.registerFont(TTFont("KR", str(previous.FONT)))
    pdfmetrics.registerFontFamily("KR", normal="KR", bold="KR", italic="KR", boldItalic="KR")
    report, technical = revise(*previous.content(facts))
    previous.save(OUT / "content-source.json", {"version": facts["version"], "material_revision": REVISION, "report": report, "technical": technical})
    documents = []
    for pages, name, technical_mode in [(report, "KitGuard_report_5p.pdf", False), (technical, "KitGuard_agent_1p.pdf", True)]:
        documents.append(SubmissionRenderer(facts["version"], technical_mode).render(pages, OUT/name))
    live_path = "test-results/submission-final-20261005/live-summary.json"
    previous.save(OUT / "pdf-build.json", {"documents": documents, "builder_sha256": previous.sha(__file__), "material_revision": REVISION, "final_runtime_source": {"path": live_path, "sha256": previous.sha(ROOT/live_path)}, "visual_qa": "pending"})
    print(json.dumps(documents, ensure_ascii=False))


if __name__ == "__main__":
    main()
