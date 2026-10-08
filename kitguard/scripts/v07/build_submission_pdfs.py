"""Render Korean Markdown sources into bounded A4 submission PDF drafts.

Run with the bundled Python containing ReportLab and pypdf. This script performs
no inference and reads no evaluation results automatically. Sources are the sole
content inputs. Explicit PAGE_BREAK comments define report pages; overflow raises
instead of shrinking text or silently adding pages. Rendering/visual QA is a
separate step. The PDF skill's operation marker is invoked once by the author,
not automatically on every rebuild.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape, quoteattr

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle, XPreformatted

ROOT = Path(__file__).resolve().parents[2]
FONT_DEFAULT = Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf")
PAGE_BREAK = "<!-- PAGE_BREAK -->"
INK = colors.HexColor("#15322D")
TEAL = colors.HexColor("#087C70")
MUTED = colors.HexColor("#536C65")
PALE = colors.HexColor("#EFF6F3")
LINE = colors.HexColor("#D0E0D9")
AMBER = colors.HexColor("#A35416")
PAGE_WIDTH, PAGE_HEIGHT = A4
LEFT = RIGHT = 44.0
TOP = PAGE_HEIGHT - 62.0
BOTTOM = 49.0
WIDTH = PAGE_WIDTH - LEFT - RIGHT


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize(text: str) -> str:
    return re.sub(r"[\u2010-\u2015\u2212]", "-", text)


@dataclass
class Block:
    kind: str
    content: str | list[list[str]]


def parse_blocks(text: str) -> list[Block]:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    lines = text.splitlines()
    blocks: list[Block] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith("```"):
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            if i == len(lines):
                raise ValueError("Unterminated code fence")
            blocks.append(Block("code", "\n".join(code)))
            i += 1
            continue
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                row = [cell.strip() for cell in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in row):
                    rows.append(row)
                i += 1
            if not rows or any(len(row) != len(rows[0]) for row in rows):
                raise ValueError("Malformed Markdown table")
            blocks.append(Block("table", rows))
            continue
        heading = re.match(r"^(#{1,3})\s+(.*)$", line)
        if heading:
            blocks.append(Block(f"h{len(heading[1])}", heading[2]))
            i += 1
            continue
        if re.match(r"^(\d+\.\s|[-*]\s)", line):
            blocks.append(Block("list", line))
            i += 1
            continue
        paragraph = [line]
        i += 1
        while i < len(lines) and lines[i].strip():
            upcoming = lines[i].strip()
            if upcoming.startswith(("#", "|", "```")) or re.match(r"^(\d+\.\s|[-*]\s)", upcoming):
                break
            paragraph.append(upcoming)
            i += 1
        blocks.append(Block("body", " ".join(paragraph)))
    return blocks


class Renderer:
    def __init__(self, source: Path, output: Path, size: float, technical: bool, status: str):
        self.source, self.output = source, output
        self.technical, self.status = technical, status
        self.links: list[dict] = []
        base = {"fontName": "Korean", "textColor": INK, "wordWrap": "CJK", "allowWidows": 0, "allowOrphans": 0}
        self.styles = {
            "body": ParagraphStyle("body", **base, fontSize=size, leading=size * 1.53),
            "list": ParagraphStyle("list", **base, fontSize=size, leading=size * 1.53),
            "h1": ParagraphStyle("h1", **base, fontSize=17 if technical else 21, leading=25 if technical else 29),
            "h2": ParagraphStyle("h2", **base, fontSize=15, leading=21),
            "h3": ParagraphStyle("h3", **base, fontSize=11.6, leading=17),
            "cell": ParagraphStyle("cell", **base, fontSize=size - 0.5, leading=(size - 0.5) * 1.44),
            "code": ParagraphStyle("code", **base, fontSize=9.4, leading=15),
        }
        for key in ("h2", "h3"):
            self.styles[key].textColor = TEAL

    def inline(self, text: str) -> str:
        pattern = r"\[([^\]]+)\]\(([^)]+)\)|\*\*(.+?)\*\*|`([^`]+)`"
        chunks, cursor = [], 0
        for match in re.finditer(pattern, text):
            chunks.append(escape(text[cursor:match.start()]))
            if match[1] is not None:
                label, target = match[1], match[2]
                if re.match(r"https?://", target):
                    href = target
                else:
                    resolved = (self.source.parent / target).resolve()
                    if not resolved.exists():
                        raise FileNotFoundError(f"Missing source link: {resolved}")
                    if self.status == "final":
                        self.links.append({"label": label, "source_target": target,
                                           "pdf_uri": None, "local_label_only": True})
                        chunks.append(escape(label))
                        cursor = match.end()
                        continue
                    href = quote(os.path.relpath(resolved, self.output.parent), safe="/")
                self.links.append({"label": label, "source_target": target, "pdf_uri": href})
                chunks.append(f'<link href={quoteattr(href)} color="#087C70">{escape(label)}</link>')
            elif match[3] is not None:
                color = "#A35416" if "미완료" in match[3] or "DRAFT" in match[3] else "#087C70"
                chunks.append(f'<font color="{color}">{self.inline(match[3])}</font>')
            else:
                chunks.append(f'<font color="#536C65">{escape(match[4])}</font>')
            cursor = match.end()
        chunks.append(escape(text[cursor:]))
        return "".join(chunks)

    def flowable(self, block: Block):
        if block.kind == "table":
            rows = block.content
            assert isinstance(rows, list)
            columns = len(rows[0])
            if columns == 2:
                widths = [WIDTH * 0.225, WIDTH * 0.775]
            elif columns == 6:
                widths = [WIDTH * factor for factor in (0.31, 0.065, 0.065, 0.065, 0.065, 0.43)]
            else:
                widths = [WIDTH / columns] * columns
            cells = [[Paragraph(self.inline(cell), self.styles["cell"]) for cell in row] for row in rows]
            item = Table(cells, colWidths=widths, hAlign="LEFT")
            item.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), PALE),
                ("LINEBELOW", (0, 0), (-1, 0), 0.75, TEAL),
                ("LINEBELOW", (0, 1), (-1, -1), 0.35, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5 if self.technical else 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5 if self.technical else 6),
            ]))
            return item, 7 if self.technical else 10
        text = block.content
        assert isinstance(text, str)
        if block.kind == "code":
            code = XPreformatted(escape(text), self.styles["code"])
            box = Table([[code]], colWidths=[WIDTH])
            box.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), PALE),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ]))
            return box, 9
        gaps = {"h1": 10, "h2": 10, "h3": 5, "list": 3, "body": 6 if self.technical else 9}
        return Paragraph(self.inline(text), self.styles[block.kind]), gaps[block.kind]

    def frame(self, pdf: canvas.Canvas, number: int, total: int) -> None:
        pdf.setFillColor(TEAL)
        pdf.rect(LEFT, PAGE_HEIGHT - 31, 26, 3, fill=1, stroke=0)
        pdf.setFont("Korean", 8.1)
        pdf.setFillColor(MUTED)
        pdf.drawString(LEFT + 34, PAGE_HEIGHT - 31, "KITGUARD / " + ("AGENT TECHNICAL NOTE" if self.technical else "RESULT REPORT"))
        pdf.setFillColor(AMBER if self.status == "draft" else TEAL)
        pdf.drawRightString(PAGE_WIDTH - RIGHT, PAGE_HEIGHT - 31, self.status.upper())
        pdf.setStrokeColor(LINE)
        pdf.line(LEFT, 37, PAGE_WIDTH - RIGHT, 37)
        pdf.setFont("Korean", 8)
        pdf.setFillColor(MUTED)
        label = "작성 기준 2026-10-02 / 미완료 항목은 본문에 명시" if self.status == "draft" else "KitGuard / 제출 자료"
        pdf.drawString(LEFT, 24, label)
        pdf.drawRightString(PAGE_WIDTH - RIGHT, 24, f"{number} / {total}")

    def build(self, expected_max: int) -> dict:
        raw = self.source.read_bytes()
        source_text = normalize(raw.decode("utf-8"))
        if self.status == "final" and re.search(r"DRAFT|미완료|작업본", source_text):
            raise ValueError("Final output requested but source still contains draft/incomplete markers")
        pages = source_text.split(PAGE_BREAK)
        if len(pages) > expected_max or (self.technical and len(pages) != 1):
            raise ValueError(f"Explicit page count {len(pages)} exceeds permitted {expected_max}")
        cmap = pdfmetrics.getFont("Korean").face.charToGlyph
        visible = re.sub(r"<!--.*?-->", "", source_text, flags=re.DOTALL)
        missing = sorted({char for char in visible if not char.isspace() and ord(char) not in cmap})
        if missing:
            raise ValueError(f"Font lacks glyphs: {missing}")
        stream = io.BytesIO()
        pdf = canvas.Canvas(stream, pagesize=A4, pageCompression=1, invariant=1)
        pdf.setTitle("KitGuard Agent 기술 설명" if self.technical else "KitGuard 결과보고서")
        pdf.setAuthor("해피 팀")
        pdf.setSubject(f"{self.status.upper()} - source-backed Korean submission document")
        positions = []
        for index, section in enumerate(pages, 1):
            self.frame(pdf, index, len(pages))
            y = TOP
            details = []
            for block in parse_blocks(section):
                flowable, gap = self.flowable(block)
                width, height = flowable.wrapOn(pdf, WIDTH, TOP - BOTTOM)
                if width > WIDTH + 0.5 or y - height < BOTTOM:
                    raise ValueError(
                        f"Overflow {self.source.name}, page {index}, block {block.kind}: "
                        f"bottom={y - height:.1f}, required >= {BOTTOM}; "
                        "shorten source or choose a readable explicit size"
                    )
                flowable.drawOn(pdf, LEFT, y - height)
                details.append({"kind": block.kind, "top": y, "bottom": y - height, "height": height})
                y -= height + gap
            positions.append({"page": index, "content_bottom": y + gap, "blocks": details})
            pdf.showPage()
        pdf.save()
        data = stream.getvalue()
        reader = PdfReader(io.BytesIO(data))
        if len(reader.pages) != len(pages):
            raise ValueError("Rendered PDF page count mismatch")
        text = "\n".join(page.extract_text() for page in reader.pages)
        if "KitGuard" not in text or "사진" not in text or "주문" not in text:
            raise ValueError("Expected Korean text was not extractable")
        if self.status == "draft" and any("DRAFT" not in page.extract_text() for page in reader.pages):
            raise ValueError("Every draft page must show DRAFT")
        self.output.write_bytes(data)
        return {
            "source": str(self.source), "source_sha256": sha256(raw),
            "pdf": str(self.output), "pdf_sha256": sha256(data),
            "status": self.status, "pages": len(reader.pages), "max_pages": expected_max,
            "body_font_size": self.styles["body"].fontSize,
            "cell_font_size": self.styles["cell"].fontSize,
            "missing_font_glyphs": missing, "layout": positions,
            "links": self.links, "visual_qa": "pending_render_and_human_visual_inspection",
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-source", type=Path, default=ROOT / "docs/v0.7/RESULT_REPORT_KO_DRAFT.md")
    parser.add_argument("--tech-source", type=Path, default=ROOT / "docs/v0.7/AGENT_TECH_KO_DRAFT.md")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output/pdf/v0.7-draft")
    parser.add_argument("--font", type=Path, default=FONT_DEFAULT)
    parser.add_argument("--report-size", type=float, default=10.6)
    parser.add_argument("--tech-size", type=float, default=9.7)
    parser.add_argument("--status", choices=("draft", "final"), default="draft")
    args = parser.parse_args()
    if args.report_size < 10 or args.tech_size < 9.5:
        parser.error("Body sizes below report 10pt / technical 9.5pt are not permitted")
    args.output_dir = args.output_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(TTFont("Korean", str(args.font)))
    pdfmetrics.registerFontFamily("Korean", normal="Korean", bold="Korean", italic="Korean", boldItalic="Korean")
    documents = []
    for source, name, size, technical, max_pages in (
        (args.report_source, "KitGuard_결과보고서_v0.7_draft.pdf", args.report_size, False, 5),
        (args.tech_source, "KitGuard_Agent_기술설명_v0.7_draft.pdf", args.tech_size, True, 1),
    ):
        if args.status == "final":
            name = name.replace("_draft", "")
        renderer = Renderer(source.resolve(), args.output_dir / name, size, technical, args.status)
        documents.append(renderer.build(max_pages))
    manifest = {
        "schema_version": 1,
        "generator": str(Path(__file__).resolve()),
        "generator_sha256": sha256(Path(__file__).read_bytes()),
        "font": str(args.font), "font_sha256": sha256(args.font.read_bytes()),
        "page_size": "A4", "documents": documents,
    }
    (args.output_dir / "BUILD_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    for document in documents:
        print(json.dumps({key: document[key] for key in ("pdf", "pages", "body_font_size", "pdf_sha256")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
