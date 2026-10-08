"""Build a five-page Korean v0.3 supplement only from complete final evidence.

Uses the Codex bundled Python for ReportLab/pypdf. --validate-only uses stdlib
only and neither creates a PDF nor calls the required artifact marker. No model
is imported, no photo is opened, and no benchmark is run by this builder.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
PDF_SKILL = Path("/Users/lkc/.codex/plugins/cache/openai-primary-runtime/pdf/26.905.11957/skills/pdf")
FONT = Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf")
PROTOCOL = ROOT / "docs/v0.3/HOLDOUT_GATES_V1.json"
PROTOCOL_SHA = "563bf149286d6cacb7e14992b5ee9d1b1895752fae7f407a4da37ab11d65b8b6"
DEV_GATE = ROOT / "evaluation-runs/v03_guarded_integrated_development_v1/gate_report_v1.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate JSON field: {key}")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError(f"Non-finite JSON: {value}")

    result = json.loads(path.read_text(), object_pairs_hook=unique, parse_constant=invalid)
    if not isinstance(result, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return result


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value, name, minimum=0):
    require(type(value) is int and value >= minimum, f"Invalid integer: {name}")
    return value


def validate_metric(metric: dict, n: int, *, measured: bool):
    require(metric["images"] == n, "Image denominator mismatch")
    counts = [integer(metric[key], key) for key in ("C", "W", "U", "E")]
    require(sum(counts) == n, "C/W/U/E must partition the full image denominator")
    for key, numerator, denominator in (
        ("correct_actionable", metric["C"], n),
        ("wrong_actionable_all_images", metric["W"], n),
        ("actionable_coverage", metric["C"] + metric["W"], n),
        ("wrong_given_actionable", metric["W"], metric["C"] + metric["W"]),
    ):
        rate = metric[key]
        require(
            rate["numerator"] == numerator and rate["denominator"] == denominator,
            f"Invalid rate denominator: {key}",
        )
        expected = numerator / denominator if denominator else None
        require(rate["rate"] == expected, f"Invalid rate value: {key}")
    if measured:
        timing = metric["latency_ms"]
        for key in ("median", "maximum"):
            value = timing[key]
            require(
                type(value) in (int, float) and math.isfinite(value) and value >= 0,
                f"Missing actual latency: {key}",
            )
    else:
        require(metric["latency_ms"] is None, "First-pass baseline cannot claim independent total latency")


def validate_gate(path: Path, stage: str, protocol: dict) -> dict:
    gate = read_json(path)
    n = 28 if stage == "development" else 64
    require(gate["stage"] == stage and gate["complete"] is True, "Gate is not complete for this stage")
    require(gate["planned_images"] == gate["completed_images"] == n, "Incomplete planned image count")
    require(gate["protocol_sha256"] == PROTOCOL_SHA, "Gate protocol is not the final preholdout freeze")
    require(
        type(gate["stage_passed"]) is bool and type(gate["default_adoption_eligible"]) is bool,
        "Selection flags must be explicit booleans",
    )
    for key, measured in (("candidate", True), ("baseline", False)):
        validate_metric(gate[key], n, measured=measured)
    run = Path(gate["run_path"])
    for filename, field in (
        ("run.json", "run_json_sha256"),
        ("predictions.jsonl", "predictions_sha256"),
        ("manifest.json", "manifest_sha256"),
    ):
        require(digest(run / filename) == gate[field], f"Gate input changed: {filename}")
    meta = read_json(run / "run.json")
    require(
        meta["status"] == "completed" and meta["source_changed_during_run"] is False,
        "Partial run or changed source cannot become a final PDF",
    )
    require(meta["expected_cases"] == meta["completed_cases"] == n, "Underlying run is incomplete")
    config = protocol["stages"][stage]
    require(meta["case_ids"] == config["case_ids"], "Underlying case sequence is not frozen sequence")
    require(gate["manifest_sha256"] == config["manifest_sha256"], "Wrong stage manifest")
    require(set(gate["groups"]) == set(config["groups"]), "Missing or extra gate groups")
    groups_pass = []
    for name, frozen in config["groups"].items():
        group = gate["groups"][name]
        for key, measured in (("candidate", True), ("baseline", False)):
            validate_metric(group[key], frozen["images"], measured=measured)
        candidate = group["candidate"]
        passed = (
            candidate["C"] >= frozen["correct_actionable_min"]
            and candidate["W"] == 0
            and candidate["E"] == 0
            and candidate["latency_ms"]["median"] <= config["median_latency_ms_max"]
        )
        require(group["passed"] is passed, "Group pass flag contradicts its counts or latency")
        groups_pass.append(passed)
    rule_pass = []
    for name, expected_n in config["zero_false_ready_gates"].items():
        metric = gate["candidate"][name]
        require(metric["denominator"] == expected_n, f"Wrong rule denominator: {name}")
        rule_pass.append(metric["numerator"] == 0)
    require(gate["stage_passed"] is (all(groups_pass) and all(rule_pass)), "Gate pass flag inconsistent")
    comparison = gate["comparison"]
    matrix = comparison["paired_matrix_baseline_rows_candidate_columns"]
    for label in ("C", "W", "U", "E"):
        require(
            sum(integer(matrix[label][x], "paired count") for x in ("C", "W", "U", "E"))
            == gate["baseline"][label],
            "Paired matrix row mismatch",
        )
        require(
            sum(matrix[x][label] for x in ("C", "W", "U", "E")) == gate["candidate"][label],
            "Paired matrix column mismatch",
        )
    benefit = (
        gate["baseline"]["W"] > 0
        and gate["candidate"]["W"] < gate["baseline"]["W"]
        and sum(matrix[x]["W"] for x in ("C", "U", "E")) == 0
    )
    require(comparison["demonstrated_error_blocking_benefit"] is benefit, "Benefit flag inconsistent")
    if stage == "development":
        require(gate["default_adoption_eligible"] is False, "Development alone cannot select a default")
    else:
        eligible = gate["stage_passed"] and benefit and gate["development_gate_passed"] is True
        require(gate["default_adoption_eligible"] is eligible, "Default eligibility flag inconsistent")
    return gate


def validate_audit(path: Path, gate: dict) -> dict:
    audit = read_json(path)
    for audit_key, gate_key in (
        ("run_sha256", "run_json_sha256"),
        ("predictions_sha256", "predictions_sha256"),
        ("manifest_sha256", "manifest_sha256"),
    ):
        require(audit[audit_key] == gate[gate_key], "Independent audit is for different evidence")
    require(
        audit["schema_revalidated"] == 64 and audit["input_audit"]["verified"] is True,
        "Incomplete independent schema or input audit",
    )
    require(
        audit["correct_actionable"]["final"] == gate["candidate"]["C"]
        and audit["correct_actionable"]["first_pass"] == gate["baseline"]["C"]
        and audit["correct_actionable"]["denominator"] == 64,
        "Independent C recount mismatch",
    )
    for label, source in (("final", "candidate"), ("first_pass", "baseline")):
        require(audit[label]["images"] == 64, "Audit image denominator mismatch")
        require(
            audit[label]["wrong_actionable_count"]["numerator"] == gate[source]["W"],
            "Independent W recount mismatch",
        )
        require(audit[label]["errors"]["numerator"] == gate[source]["E"], "Independent E recount mismatch")
    return audit


def read_junit(path: Path) -> dict:
    root = ET.parse(path).getroot()
    cases = root.findall(".//testcase")
    require(bool(cases), "No engineering test cases")
    failed = sum(case.find("failure") is not None for case in cases)
    errors = sum(case.find("error") is not None for case in cases)
    skipped = sum(case.find("skipped") is not None for case in cases)
    return {
        "total": len(cases),
        "passed": len(cases) - failed - errors - skipped,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
    }


def validate_demo(path: Path) -> dict:
    demo = read_json(path)
    require(
        demo["status"] in ("completed", "completed_with_execution_errors"),
        "Demo receipt is incomplete or interrupted",
    )
    require(
        demo["planned_samples"] == 3 and demo["planned_inspections"] == 4,
        "Unexpected demo scope; update the document contract explicitly",
    )
    require(
        demo["attempted_inspections"] == 4 and len(demo["outcomes"]) == 4,
        "Demo does not contain all planned inspections",
    )
    require(
        demo["source_changed_during_run"] is False
        and demo["source_sha256_before"] == demo["source_sha256_after"],
        "Demo source changed",
    )
    require(bool(demo["source_sha256_before"]), "Missing demo source provenance")
    for field in (
        "checks",
        "errors",
        "failed_requests",
        "fatal",
        "orderIds",
        "notes",
        "http_receipts",
        "runtime_configuration",
        "scope",
        "passed_engineering_assertions",
    ):
        require(field in demo, f"Missing demo field: {field}")
    require(bool(demo["scope"]), "Demo must describe its evidence scope")
    require(
        demo["planned_instruction_calls"] == demo["attempted_instruction_calls"] == 1,
        "Demo must retain its one actual instruction proposal request",
    )
    require(
        demo["planned_model_requests"] == demo["attempted_model_requests"] == 5,
        "Expected four visual API requests plus one instruction request, not four total calls",
    )
    instruction = demo["instruction_outcome"]
    require(
        instruction["status"]
        in ("proposal_returned", "clarification", "proposal_mismatch", "execution_error"),
        "Incomplete instruction proposal outcome",
    )
    require(
        type(instruction["fallback_used"]) is bool
        and (not instruction["fallback_used"] or bool(instruction.get("fallback_reason"))),
        "Instruction fallback must be explicit",
    )
    for field in (
        "via",
        "performed",
        "applied",
        "http_status",
        "to_revision",
        "requirements",
        "automated_ui_action",
    ):
        require(field in instruction["approval"], f"Missing actual revision approval: {field}")
    for row in demo["outcomes"]:
        for field in (
            "sample",
            "revision",
            "order_id",
            "http_status",
            "request_wall_ms",
            "response",
            "check_latency_ms",
            "check_id",
            "status",
            "runtime_mode",
            "backend",
            "decision",
        ):
            require(field in row, f"Incomplete real API outcome: {field}")
        require(
            type(row["http_status"]) is int and 100 <= row["http_status"] <= 599,
            "Missing actual HTTP response status",
        )
        require(
            type(row["request_wall_ms"]) in (int, float) and row["request_wall_ms"] >= 0,
            "Missing actual request duration",
        )
        if 200 <= row["http_status"] < 300:
            require(row["backend"] == "mlx", "Successful demonstration is not a real local MLX result")
    # Neither non-ready model answers nor recorded failed HTTP requests are
    # silently dropped. Their outcome is displayed in the PDF as observed.
    return demo


def load_bundle(args) -> dict:
    require(digest(PROTOCOL) == PROTOCOL_SHA, "Preholdout selection protocol has changed")
    protocol = read_json(PROTOCOL)
    development = validate_gate(args.development_gate, "development", protocol)
    gate = validate_gate(args.gate, "holdout", protocol)
    require(
        gate["development_report_sha256"] == digest(args.development_gate),
        "Holdout gate used a different development report",
    )
    audit = validate_audit(args.audit, gate)
    engineering = read_junit(args.engineering_junit)
    demo = validate_demo(args.demo_receipt)
    paths = {
        "holdout_gate": args.gate,
        "development_gate": args.development_gate,
        "independent_audit": args.audit,
        "engineering_junit": args.engineering_junit,
        "real_api_demo": args.demo_receipt,
        "protocol": PROTOCOL,
    }
    detectors = []
    for label, name in (
        ("OWLv2 Base Ensemble", "v03_owl_development_v1"),
        ("Grounding DINO Tiny", "v03_grounding_dino_development_v1"),
    ):
        path = ROOT / "evaluation-runs" / name / "run.json"
        run = read_json(path)
        require(
            run["status"] == "completed"
            and run["completed_cases"] == 28
            and run["script_changed_during_run"] is False,
            "Detector comparison is not complete",
        )
        for group, n in (("loco", 16), ("screws", 12)):
            require(
                run["summary"][group]["planned"] == run["summary"][group]["completed"] == n,
                "Detector comparison has a partial denominator",
            )
        detectors.append({"label": label, "summary": run["summary"]})
        paths[name] = path
    return {
        "gate": gate,
        "development": development,
        "audit": audit,
        "engineering": engineering,
        "demo": demo,
        "protocol": protocol,
        "detectors": detectors,
        "sources": {
            name: {"path": str(path.resolve()), "sha256": digest(path)} for name, path in paths.items()
        },
    }


def fraction(metric):
    return f"{metric['numerator']}/{metric['denominator']}" if metric["denominator"] else "해당 없음"


def seconds(milliseconds):
    return "별도 측정 없음" if milliseconds is None else f"{milliseconds / 1000:.2f}초"


def render(args, data):
    # Optional PDF dependencies are imported only after all evidence is complete.
    from pypdf import PdfReader
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        Flowable,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    require(not args.output.exists(), "Keep prior PDF evidence; output already exists")
    require(FONT.is_file(), "Required Korean font is unavailable")
    pdfmetrics.registerFont(TTFont("KitGuardKorean", str(FONT)))
    ink, teal, muted = [colors.HexColor(x) for x in ("#16342E", "#137E70", "#536B63")]
    pale, line = [colors.HexColor(x) for x in ("#EDF6F1", "#D7E5DD")]
    width = A4[0] - 84
    styles = {
        "title": ParagraphStyle(
            "title",
            fontName="KitGuardKorean",
            fontSize=23,
            leading=30,
            textColor=ink,
            spaceAfter=12,
            wordWrap="CJK",
        ),
        "heading": ParagraphStyle(
            "heading",
            fontName="KitGuardKorean",
            fontSize=12.4,
            leading=18,
            textColor=teal,
            spaceBefore=10,
            spaceAfter=7,
            wordWrap="CJK",
        ),
        "body": ParagraphStyle(
            "body",
            fontName="KitGuardKorean",
            fontSize=9.6,
            leading=14.7,
            textColor=ink,
            spaceAfter=8,
            wordWrap="CJK",
        ),
        "small": ParagraphStyle(
            "small",
            fontName="KitGuardKorean",
            fontSize=8.2,
            leading=12,
            textColor=muted,
            spaceAfter=7,
            wordWrap="CJK",
        ),
        "cell": ParagraphStyle(
            "cell", fontName="KitGuardKorean", fontSize=8.7, leading=12.5, textColor=ink, wordWrap="CJK"
        ),
    }
    story = []

    def paragraph(text, kind="body"):
        story.append(Paragraph(escape(str(text)).replace("\n", "<br/>"), styles[kind]))

    def page(title):
        if story:
            story.append(PageBreak())
        paragraph(title, "title")

    def table(headers, rows, widths):
        cells = [
            [Paragraph(escape(str(value)).replace("\n", "<br/>"), styles["cell"]) for value in row]
            for row in [headers, *rows]
        ]
        item = Table(cells, colWidths=widths, repeatRows=1, hAlign="LEFT")
        item.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), pale),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.7, teal),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.4, line),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        story.extend([item, Spacer(1, 8)])

    class Architecture(Flowable):
        def __init__(self):
            super().__init__()
            self.width, self.height = width, 72

        def draw(self):
            labels = [
                ("사진 근거", "현재 버전 결합"),
                ("시각 관찰", "목록 + 조건부 검증"),
                ("프로그램", "계수 + 주문 비교"),
                ("다음 행동", "보완 / 사람 확인"),
            ]
            gap, cell = 10, (width - 30) / 4
            for index, pair in enumerate(labels):
                x = index * (cell + gap)
                self.canv.setFillColor(pale)
                self.canv.setStrokeColor(line)
                self.canv.roundRect(x, 14, cell, 48, 6, fill=1, stroke=1)
                self.canv.setFont("KitGuardKorean", 10)
                self.canv.setFillColor(ink)
                self.canv.drawCentredString(x + cell / 2, 44, pair[0])
                self.canv.setFont("KitGuardKorean", 8)
                self.canv.drawCentredString(x + cell / 2, 27, pair[1])
                if index < 3:
                    self.canv.setStrokeColor(teal)
                    self.canv.line(x + cell + 2, 38, x + cell + 8, 38)

    gate, dev, audit, engineering, demo = [
        data[k] for k in ("gate", "development", "audit", "engineering", "demo")
    ]
    eligible = gate["default_adoption_eligible"]
    adoption = "연구용 기본 채택 수치 조건 충족" if eligible else "연구용 기본 채택 수치 조건 미충족"
    page("01 / 근거를 잇는 업무 Agent")
    paragraph("KitGuard v0.3 기술·결과 보충 / 팀 해피", "heading")
    paragraph("국립창원대학교 인공지능융합공학과 / 2026-09-26 사전 개발 기록 / 공식 제출본 아님", "small")
    paragraph(
        "소량 부품 준비 과정에서 주문 변경과 낡은 검사 근거가 어긋나는 문제를 다룹니다. 현재 주문, 사진, 참고 자료와 검사 결과를 버전으로 결합하고, 수량 차이와 불확실성에 다음 행동을 연결합니다."
    )
    story.append(Architecture())
    table(
        ["모델이 하는 일", "프로그램과 사람이 하는 일"],
        [
            [
                "보이는 물체의 종류·위치 제안\n조건부 확대 관찰의 신원·개구 형태 응답",
                "목록 계수와 현재 주문 차이 계산\n불확실성 보존, 버전 일치 검사, 완료 확인",
            ],
            ["목표 수량·정답을 받지 않는 관찰", "수량을 주문에 맞춰 자동 수정하지 않음"],
        ],
        [width / 2] * 2,
    )
    paragraph("v0.3에서 추가한 기능", "heading")
    paragraph(
        "동일 내용의 재업로드를 새 보완 증거로 중복 계산하지 않습니다. 촬영 세션과 주문을 묶고 명시적으로 저장한 사진만 전송합니다. 공개 자료 체험은 실제 출고 완료와 분리하고, 신원 검증의 응답·좌표·원본 해시를 감사 화면에 표시합니다."
    )
    paragraph("현재 선택 판단", "heading")
    paragraph(
        f"{adoption}. 문서화한 배포 선택은 {args.deployment_mode}입니다. 수치 조건 통과는 자동 배포나 현장 안전 인증을 뜻하지 않습니다."
    )
    paragraph(
        "핵심 구현은 공개 모델 자체가 아니라, 모델의 관찰을 검증 가능한 업무 상태·도구 결과·보완 요청·사람 확인에 연결하는 부분입니다.",
        "small",
    )

    page("02 / 고정한 분모와 답변의 대가")
    paragraph(
        "C=정확·실행 가능, W=오답·실행 가능, U=보류, E=실행 오류. 모든 사진을 남기며 C+W+U+E=N입니다. 아래 개발과 새 평가는 합산하지 않습니다."
    )
    rows = []
    for name, group in dev["groups"].items():
        m = group["candidate"]
        rows.append(
            [
                "개발 LOCO16" if name == "loco16" else "개발 Screws12",
                m["images"],
                m["C"],
                m["W"],
                m["U"],
                m["E"],
            ]
        )
    names = {
        "loco_normal16": "새 평가 LOCO 정상",
        "loco_anomaly16": "새 평가 LOCO 수량 이상",
        "screws32": "새 평가 Screws",
    }
    for name, group in gate["groups"].items():
        m = group["candidate"]
        rows.append([names[name], m["images"], m["C"], m["W"], m["U"], m["E"]])
    table(["서로 구분한 자료", "N", "C", "W", "U", "E"], rows, [width - 200] + [40] * 5)
    comparison = gate["comparison"]
    table(
        ["동일 새 평가 64장", "C", "W", "U", "E"],
        [
            ["같은 실행의 실제 첫 관찰", *[gate["baseline"][k] for k in ("C", "W", "U", "E")]],
            ["최종 후보 절차", *[gate["candidate"][k] for k in ("C", "W", "U", "E")]],
        ],
        [width - 200] + [50] * 4,
    )
    paragraph(
        f"기존 오답 중 확정하지 않게 된 사진 {comparison['blocked_baseline_wrong']}장, 정확했던 답이 보류된 사진 {comparison['correct_to_abstention']}장, 새로 생긴 확정 오답 {comparison['introduced_wrong']}장입니다. 첫 관찰은 같은 실행의 실제 출력으로 재구성했으며 별도 실행이나 독립 전문가가 아닙니다.",
        "small",
    )
    m = gate["candidate"]
    table(
        ["잘못된 준비 완료를 따로 측정", "사진 기준 결과"],
        [
            ["정상 명목 주문 아래 수량 이상", fraction(m["nominal_anomaly_false_ready"])],
            ["사진별 한 개의 고정 교란 주문", fraction(m["fixed_perturbation_false_ready"])],
            ["255개 유효 주문 중 하나라도 잘못 일치", fraction(m["panel_any_false_ready"])],
        ],
        [width - 120, 120],
    )
    paragraph(
        f"정확한 답변 범위 {fraction(m['correct_actionable'])}, 확정 답 중 오류 {fraction(m['wrong_given_actionable'])}. 개발 통과 뒤에도 새 평가 그룹별 최소 C=13/16, 13/16, 27/32와 W=E=0, 중위 60초 이내를 요구합니다. 양쪽 모두 W=0이면 추가 검증의 오류 차단 이익은 입증되지 않습니다.",
        "small",
    )

    page("03 / 채택하지 않은 실험도 기록")
    paragraph("후보의 관찰 절차", "heading")
    paragraph(
        "원본과 90도 회전에서 각각 물체 목록을 얻습니다. 명확한 일치가 있고 너트·와셔 후보가 있을 때 전체 영상과 위치별 확대 영상을 한 번 더 확인합니다. 처음 두 호출은 각 900 출력 토큰, 조건부 세 번째는 1,800 토큰입니다. 불일치는 관련 수량을 미확인으로 바꿀 뿐, 정답 수량을 추측하거나 다시 분류해 맞추지 않습니다."
    )
    detector_rows = [
        [
            item["label"],
            f"{item['summary']['loco']['exact_count_images']}/16",
            f"{item['summary']['screws']['exact_count_images']}/12",
        ]
        for item in data["detectors"]
    ]
    table(
        ["고정 설정의 CPU 개발 진단", "LOCO16 전체 계수", "Screws12 전체 계수"],
        detector_rows,
        [width - 208, 104, 104],
    )
    paragraph(
        "서로 다른 검출기라도 진실을 대신하지 않습니다. 작은 금속 부품의 누락·오분류·넓은 오검출 때문에 두 후보를 판단 경로에 넣지 않았습니다. 이는 사전에 고정한 제로샷 질의와 임계값의 결과이며, 모델 계열 전체가 실패한다는 주장은 아닙니다.",
        "small",
    )
    paragraph("새 64장 전체 절차의 실제 지연시간", "heading")
    table(
        ["그룹", "중위", "최대"],
        [
            [
                names[name],
                seconds(group["candidate"]["latency_ms"]["median"]),
                seconds(group["candidate"]["latency_ms"]["maximum"]),
            ]
            for name, group in gate["groups"].items()
        ],
        [width - 180, 90, 90],
    )
    paragraph(
        "업로드 정규화·로딩·실제 호출을 포함한 실행 시간이며 첫 사진도 제외하지 않았습니다. 동일 실행의 첫 관찰에는 독립된 전체 지연시간이 없습니다. 이 시간은 사람이 촬영·수정·확인하는 전체 작업 시간과 다릅니다.",
        "small",
    )
    paragraph("사진, 좌표, 분류의 증거", "heading")
    paragraph(
        "원본 정규화 사진의 해시, 방향별 입력과 물체 목록, 확대 영역의 좌표·픽셀 해시와 분류 응답을 연결합니다. 표시되는 점은 모델의 추정 위치입니다. 회전과 확대는 새 사진이 아니며, 같은 모델의 반복 오류나 처음부터 누락한 물체를 해결한다고 보장하지 않습니다. 임시 확대 PNG 자체의 영구 보관과 재구성 가능한 메타데이터는 구분합니다."
    )

    page("04 / 실제 API와 공학적 검증")
    paragraph("공개 사진을 사용한 실제 API 시연", "heading")
    decision_names = {
        "ready": "수량 일치\n(사람 확인 필요)",
        "correct": "수량 조정 필요",
        "recapture": "재촬영",
        "manual": "직접 확인",
    }
    rows = []
    for index, outcome in enumerate(demo["outcomes"], 1):
        decision = decision_names.get(outcome["decision"], str(outcome["decision"] or "검사 결과 없음"))
        rows.append(
            [
                f"요청 {index} / R{outcome['revision']}",
                outcome["http_status"],
                decision,
                seconds(outcome["request_wall_ms"]),
            ]
        )
    table(
        ["개발 표본 3개 / 시각 검사 4회", "HTTP", "관찰된 결과", "요청 시간"],
        rows,
        [160, 45, width - 285, 80],
    )
    paragraph(
        f"시연 기록 상태: {demo['status']}. 엔지니어링 assertion 통과 기록: {demo['passed_engineering_assertions']}. 준비 완료가 아닌 답과 오류 응답도 그대로 표시합니다. 이 시연은 공개 사진을 사용하는 실제 로컬 MLX API 흐름이며, 실물 보충이나 사람의 완료 확인을 수행한 증거가 아닙니다.",
        "small",
    )
    instruction = demo["instruction_outcome"]
    instruction_labels = {
        "proposal_returned": "수정 제안 반환",
        "clarification": "명확화 요청",
        "proposal_mismatch": "의도와 다른 제안",
        "execution_error": "실행 오류",
    }
    fallback = "구조화 입력 대안 사용" if instruction["fallback_used"] else "대안 입력 미사용"
    approved = "적용됨" if instruction["approval"]["applied"] else "적용되지 않음"
    matched = "예" if instruction.get("proposal_matches_intended") is True else "아니오 또는 미확인"
    paragraph(
        f"별도로 한국어 지시 제안 요청 {demo['attempted_instruction_calls']}회를 기록했습니다. "
        f"결과: {instruction_labels[instruction['status']]}; {fallback}; 변경 {approved}. "
        f"의도한 수량과 일치: {matched}; 제안 응답 {seconds(instruction.get('request_wall_ms'))}. "
        "제안과 적용을 구분하며, UI 승인은 자동화된 시연 조작입니다. 시각 API 한 요청 안에는 여러 관찰 호출이 있어 총 모델 생성 횟수를 4회나 5회라고 부르지 않습니다.",
        "small",
    )
    paragraph("모델 성능과 분리한 소프트웨어 검증", "heading")
    table(
        ["JUnit에서 직접 읽은 공학 시험", "건수"],
        [
            ["전체 / 통과", f"{engineering['total']} / {engineering['passed']}"],
            [
                "실패 / 실행 오류 / 건너뜀",
                f"{engineering['failed']} / {engineering['errors']} / {engineering['skipped']}",
            ],
        ],
        [width - 150, 150],
    )
    paragraph(
        "버전 변경, 오래된 검사 차단, 동일 내용 사진의 보완 예산, 참고 자료 격리, 동시 요청, 오류 추적과 수동 확인 계약을 시험합니다. 모의 모델·합성 fixture를 사용한 공학 시험은 인식 정확도 표본에 더하지 않습니다."
    )
    ia = audit["input_audit"]
    paragraph("독립 재계산과 입력 복원", "heading")
    paragraph(
        f"완료된 새 평가 {audit['schema_revalidated']}개 기록의 schema와 계수를 다시 검증했습니다. 방향별 준비 입력 {ia['prepared_inputs_recreated']}개, 확대 관련 파일 {ia['identity_crop_files_recreated']}개를 결정론적으로 재구성해 기록과 비교했습니다. 실행·예측·manifest 해시는 최종 gate와 일치합니다."
    )
    paragraph(
        "SHA-256은 파일 동일성과 변경을 추적합니다. 촬영자 신원, 현장 진위나 작성자가 기록과 해시를 함께 바꾸지 않았다는 사실을 인증하는 전자서명은 아닙니다.",
        "small",
    )

    page("05 / 재현 범위와 다음 검증")
    paragraph("실제로 시험한 실행 환경", "heading")
    paragraph(
        "M5 Pro 통합 메모리 64GB의 Mac, MLX 로컬 실행, Qwen3.6-27B 4비트입니다. 모델 revision은 c000ac2c2057d94be3fa931000c31723aac53282로 고정했습니다. 정상 관찰은 클라우드 모델 API로 사진을 보내지 않습니다. RTX 3080 PC나 Windows의 설치·속도는 실측하지 않았습니다."
    )
    paragraph("재현과 기록", "heading")
    paragraph(
        "저장된 gate_report와 독립 audit, 입력 해시, 코드 스냅샷으로 결과를 검산할 수 있습니다. evaluate_v03_gate.py는 완성된 전체 실행만 수용하고, analyze_consensus_run.py는 실제 첫 관찰과 픽셀 변환을 재계산합니다. 새 실행은 별도 출력 디렉터리를 사용하며 기존 기록을 덮어쓰지 않습니다. 이미 사용한 64장을 다시 실행하면 회귀 검증이지 새 미사용 평가가 아닙니다."
    )
    table(
        ["남은 검증", "현재 설명 가능한 범위"],
        [
            [
                "실물 작업과 사용자 대조",
                "보충 전후 새 실물 사진, 사람 기준, 최종 오류와 전체 작업 시간은 아직 실측 결과 없음",
            ],
            [
                "공개 데이터와 분류",
                "출처별 분할은 새 공장·독립 촬영 회차가 아님. 각도 브래킷 양성 없음, Screws 와셔 양성 없음",
            ],
            [
                "모델·좌표·개구 형태",
                "같은 모델의 관련된 관찰. 사전학습 중복 미상. 좌표·관통 구멍 응답도 추정",
            ],
            [
                "참가와 공개 도구",
                "AI 코딩 도구·공개 모델 활용을 공개. 9월26일 사전 개발 자산의 공식 사용 자격은 주최 측 확인 필요",
            ],
        ],
        [125, width - 125],
    )
    paragraph("검토용 출처 식별자", "heading")
    source_labels = {
        "holdout_gate": "새 평가 gate",
        "independent_audit": "독립 감사",
        "engineering_junit": "공학 시험",
        "real_api_demo": "실제 API",
    }
    rows = [
        [label, Path(data["sources"][name]["path"]).name, data["sources"][name]["sha256"][:16]]
        for name, label in source_labels.items()
    ]
    table(["증거", "파일", "SHA-256 앞 16자리"], rows, [108, width - 224, 116])
    paragraph(
        "전체 경로와 64자리 해시는 PDF 옆의 sources.json에 보존합니다. v0.2의 과거 48장 성적은 이 새 결과에 합치지 않았습니다. 이 문서는 대회 점수·수상 확률·현장 효과를 추정하지 않습니다.",
        "small",
    )

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(line)
        canvas.line(42, 39, A4[0] - 42, 39)
        canvas.setFont("KitGuardKorean", 7.2)
        canvas.setFillColor(muted)
        canvas.drawString(
            42, 26, "KitGuard v0.3 / 2026-09-26 사전 제작 / 공식 제출본 아님 / 참가 사용 자격 확인 필요"
        )
        canvas.drawRightString(A4[0] - 42, 26, f"{doc.page} / 5")
        canvas.restoreState()

    temporary = ROOT / "tmp/pdfs"
    temporary.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Required skill marker occurs exactly once and immediately before PDF
    # authoring, only after complete evidence, fonts and output checks passed.
    subprocess.run(
        [
            args.node,
            "container_tools/mark_artifact_operation_started.mjs",
            "--operation-kind",
            "create",
            "--expected-output-count",
            "1",
            "--output-format",
            "pdf",
        ],
        cwd=PDF_SKILL,
        check=True,
    )
    with tempfile.TemporaryDirectory(prefix="v03-addendum-", dir=temporary) as directory:
        staged = Path(directory) / "addendum.pdf"
        doc = SimpleDocTemplate(
            str(staged),
            pagesize=A4,
            leftMargin=42,
            rightMargin=42,
            topMargin=40,
            bottomMargin=54,
            title="KitGuard v0.3 기술·결과 보충",
            author="해피 / 국립창원대학교",
        )
        doc.build(story, onFirstPage=footer, onLaterPages=footer)
        reader = PdfReader(staged)
        require(len(reader.pages) == 5, f"Layout overflow: expected5 pages, got{len(reader.pages)}")
        require(all((page.extract_text() or "").strip() for page in reader.pages), "PDF has a blank page")
        with args.output.open("xb") as destination:
            destination.write(staged.read_bytes())
    sidecar = args.output.with_suffix(".sources.json")
    with sidecar.open("x") as stream:
        json.dump(
            {
                "created_at": datetime.now(UTC).isoformat(),
                "pdf_sha256": digest(args.output),
                "builder_sha256": digest(Path(__file__)),
                "sources": data["sources"],
                "deployment_mode_as_documented": args.deployment_mode,
                "pages": 5,
                "visual_qa": "pending: render and inspect every page before delivery",
            },
            stream,
            ensure_ascii=False,
            indent=2,
        )
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--development-gate", type=Path, default=DEV_GATE)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--engineering-junit", type=Path, required=True)
    parser.add_argument("--demo-receipt", type=Path, required=True)
    parser.add_argument("--deployment-mode", choices=["spatial_inventory", "spatial_guarded"], required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "output/pdf/KitGuard_v0.3_기술결과_보충.pdf")
    parser.add_argument("--node", default="node", help="Node executable for the PDF skill marker")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    try:
        data = load_bundle(args)
        if args.validate_only:
            print(
                json.dumps(
                    {
                        "valid": True,
                        "planned_pdf_pages": 5,
                        "pdf_created": False,
                        "holdout_images": data["gate"]["completed_images"],
                    }
                )
            )
            return
        require(not args.output.with_suffix(".sources.json").exists(), "Source sidecar already exists")
        render(args, data)
    except (ValueError, OSError, KeyError, TypeError, ET.ParseError) as exc:
        parser.exit(2, f"No final PDF generated: {exc}\n")
    print(json.dumps({"pdf": str(args.output.resolve()), "pages": 5, "visual_qa_required": True}))


if __name__ == "__main__":
    main()
