"""Build the handbook PDF. Documentation-only dependency: reportlab>=4.

Run: python docs/build_handbook_pdf.py
Reads PROJECT_HANDBOOK.md and END_TO_END_GUIDE.md beside this file.
"""
from __future__ import annotations

import re
import textwrap
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Flowable, Frame, PageBreak,
    PageTemplate, Paragraph, Spacer, Table, TableStyle, Preformatted,
)
from reportlab.platypus.tableofcontents import TableOfContents

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "VerityLake_Complete_Project_Handbook.pdf"
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
for name, filename in [
    ("Body", "DejaVuSans.ttf"), ("BodyBold", "DejaVuSans-Bold.ttf"),
    ("BodyItalic", "DejaVuSans-Oblique.ttf"), ("Mono", "DejaVuSansMono.ttf"),
]:
    pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / filename)))
pdfmetrics.registerFontFamily("Body", normal="Body", bold="BodyBold", italic="BodyItalic", boldItalic="BodyBold")

NAVY = colors.HexColor("#142B45")
TEAL = colors.HexColor("#007D83")
INK = colors.HexColor("#263749")
MUTED = colors.HexColor("#627182")
PALE = colors.HexColor("#EEF5F8")
WIDTH, HEIGHT = A4
MARGIN = 48
CONTENT = WIDTH - 2 * MARGIN
styles = getSampleStyleSheet()
styles.add(ParagraphStyle("Text", fontName="Body", fontSize=9.5, leading=13.5,
                          textColor=INK, spaceAfter=8, splitLongWords=True))
styles.add(ParagraphStyle("Chapter", parent=styles["Text"], fontName="BodyBold",
                          fontSize=21, leading=27, textColor=NAVY, spaceAfter=19,
                          keepWithNext=True))
styles.add(ParagraphStyle("Section", parent=styles["Text"], fontName="BodyBold",
                          fontSize=12, leading=17, textColor=TEAL,
                          spaceBefore=9, spaceAfter=6, keepWithNext=True))
styles.add(ParagraphStyle("Small", parent=styles["Text"], fontSize=8, leading=11.7))
styles.add(ParagraphStyle("Cell", parent=styles["Text"], fontSize=8, leading=11.5, spaceAfter=0))
styles.add(ParagraphStyle("CellHead", parent=styles["Cell"], fontName="BodyBold", textColor=colors.white))
styles.add(ParagraphStyle("CodeBlock", fontName="Mono", fontSize=7.1, leading=10.5,
                          textColor=INK, backColor=PALE, borderPadding=9, spaceBefore=7, spaceAfter=12))
styles.add(ParagraphStyle("Check", parent=styles["Text"], fontName="BodyItalic",
                          backColor=PALE, borderPadding=10, spaceBefore=10, spaceAfter=13))
styles.add(ParagraphStyle("CoverTitle", parent=styles["Chapter"], fontSize=43, leading=52))
styles.add(ParagraphStyle("CoverSub", parent=styles["Text"], fontSize=21, leading=29, textColor=TEAL))


def inline(s):
    s = escape(s)
    s = re.sub(r"`([^`]+)`", r'<font name="Mono" size="8">\1</font>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2" color="#007D83">\1</a>', s)
    return s


class Architecture(Flowable):
    def __init__(self):
        Flowable.__init__(self)
        self.width, self.height = CONTENT, 300

    def draw(self):
        c = self.canv
        box_w = (CONTENT - 30) / 4
        def row(y, labels):
            for i, label in enumerate(labels):
                x = i * (box_w + 10)
                c.setFillColor(PALE)
                c.setStrokeColor(TEAL)
                c.roundRect(x, y, box_w, 44, 5, fill=1, stroke=1)
                c.setFillColor(INK)
                c.setFont("BodyBold", 8)
                for j, line in enumerate(label.split("\n")):
                    c.drawCentredString(x + box_w / 2, y + 26 - 12 * j, line)
                if i < len(labels) - 1:
                    c.setStrokeColor(TEAL)
                    c.line(x + box_w, y + 22, x + box_w + 9, y + 22)
                    c.line(x + box_w + 6, y + 25, x + box_w + 9, y + 22)
                    c.line(x + box_w + 6, y + 19, x + box_w + 9, y + 22)
        c.setFillColor(TEAL)
        c.setFont("BodyBold", 10)
        c.drawString(0, 280, "BUILD AND PUBLISH / Airflow")
        row(218, ["Crawl + raw\nHTTPX / MinIO", "Tables + checks\nBronze / Silver / Gold", "Embed + index\nNomic / Chroma", "Publish\nManifest + pointer"])
        c.setFillColor(INK)
        c.setFont("Body", 9)
        c.drawString(0, 188, "Only a successful publication changes the selected release.")
        c.setFillColor(TEAL)
        c.setFont("BodyBold", 10)
        c.drawString(0, 149, "RETRIEVE AND ANSWER / FastAPI")
        row(84, ["Question\nAuth + release checks", "Retrieve\nNomic + Chroma", "Generate\nQwen via Ollama", "Validate + return\nQuotes + source IDs"])
        c.setFillColor(MUTED)
        c.setFont("Body", 8)
        c.drawString(0, 54, "MinIO: evidence and tables   |   PostgreSQL: Airflow state")
        c.drawString(0, 38, "DuckDB: deduplication and catalog   |   Chroma: retrieval text and vectors")


class Handbook(BaseDocTemplate):
    def __init__(self, filename):
        super().__init__(str(filename), pagesize=A4, leftMargin=MARGIN,
                         rightMargin=MARGIN, topMargin=55, bottomMargin=49,
                         title="VerityLake — Complete Project Handbook",
                         author="VerityLake project learning documentation",
                         subject="Beginner-to-interview guide to the VerityLake codebase")
        frame = Frame(MARGIN, 49, CONTENT, HEIGHT - 104, id="main", leftPadding=0,
                      rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates(PageTemplate(id="pages", frames=[frame], onPage=self.decorate))

    def decorate(self, canvas, doc):
        canvas.saveState()
        if doc.page > 1:
            canvas.setStrokeColor(colors.HexColor("#CAD8E1"))
            canvas.line(MARGIN, HEIGHT - 35, WIDTH - MARGIN, HEIGHT - 35)
            canvas.setFont("BodyBold", 7.5)
            canvas.setFillColor(MUTED)
            canvas.drawString(MARGIN, HEIGHT - 26, "VERITYLAKE  /  PROJECT HANDBOOK")
            canvas.setFont("Body", 7)
            canvas.drawRightString(WIDTH - MARGIN, HEIGHT - 26, "LEARN • TRACE • EXPLAIN")
        canvas.setFont("Body", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(MARGIN, 27, "Repository edition · 21 September 2026")
        canvas.drawRightString(WIDTH - MARGIN, 27, str(doc.page))
        canvas.restoreState()

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and hasattr(flowable, "toc_key"):
            key, label = flowable.toc_key, flowable.getPlainText()
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(label, key, level=flowable.toc_level, closed=False)
            self.notify("TOCEntry", (flowable.toc_level, label, self.page, key))


story = []
serial = 0


def heading(label, appendix=False):
    global serial
    serial += 1
    if not appendix:
        story.append(PageBreak())
    p = Paragraph(inline(label), styles["Section" if appendix else "Chapter"])
    p.toc_key = f"section-{serial}"
    p.toc_level = 1 if appendix else 0
    story.append(p)


def parse_markdown(text, appendix=False):
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith("# "):
            i += 1
            continue
        if line.startswith("## "):
            heading(line[3:], appendix)
            i += 1
            continue
        if line.startswith("### "):
            story.append(Paragraph(inline(line[4:]), styles["Section"]))
            i += 1
            continue
        if line.startswith("```"):
            language = line[3:].strip()
            block = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i])
                i += 1
            i += 1
            if language == "mermaid":
                story.append(Architecture())
            else:
                wrapped = []
                for value in block:
                    wrapped.extend(textwrap.wrap(value, width=94, subsequent_indent="    ",
                                                  replace_whitespace=False, drop_whitespace=False) or [""])
                story.append(Preformatted("\n".join(wrapped), styles["CodeBlock"]))
            continue
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [x.strip() for x in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r"[:\- ]+", cell) for cell in cells):
                    rows.append(cells)
                i += 1
            n = len(rows[0])
            if rows[0][0] == "Remember":
                story.append(PageBreak())
                story.append(Paragraph("Quick revision sheet", styles["Chapter"]))
            if n == 2:
                widths = [CONTENT * .35, CONTENT * .65]
            elif n == 3:
                widths = [CONTENT * .24, CONTENT * .39, CONTENT * .37]
            else:
                widths = [CONTENT / n] * n
            content = [[Paragraph(inline(cell), styles["CellHead" if r == 0 else "Cell"])
                        for cell in row] for r, row in enumerate(rows)]
            table = Table(content, colWidths=widths, repeatRows=1, hAlign="LEFT")
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LINEBELOW", (0, 0), (-1, 0), .6, TEAL),
            ]))
            story.extend([table, Spacer(1, 12)])
            continue
        if re.match(r"^(?:- |\d+\. )", line):
            story.append(Paragraph(inline(line), styles["Text"]))
            i += 1
            continue
        para = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(?:#|\||```|- |\d+\. )", lines[i]):
            para.append(lines[i].strip())
            i += 1
        value = " ".join(para)
        style = styles["Check"] if value.startswith("Checkpoint:") else styles["Text"]
        story.append(Paragraph(inline(value), style))


story.extend([
    Spacer(1, 78),
    Paragraph("VERITYLAKE", styles["CoverTitle"]),
    Paragraph("From first principles<br/>to interview readiness", styles["CoverSub"]),
    Spacer(1, 22),
    Paragraph("The complete project handbook", styles["Chapter"]),
    Paragraph("Understand the purpose. Follow every data stage. Explain the code, tools, decisions and failure boundaries.", styles["Text"]),
    Spacer(1, 20),
    Paragraph("28 learning chapters · 28 interview questions · Worked examples<br/>Operational guide · Complete implementation reference", styles["Text"]),
    Spacer(1, 35),
    Paragraph("WEBSITE → LAKEHOUSE → CHECKED RELEASE → CITED ANSWER", styles["Small"]),
    Spacer(1, 45),
    Paragraph("Based on the local repository · 21 September 2026", styles["Small"]),
    Paragraph("Implementation descriptions are separated from measured runtime evidence. Illustrative examples are labeled throughout.", styles["Small"]),
    PageBreak(),
    Paragraph("Contents", styles["Chapter"]),
    Paragraph("Select an entry to jump to its page. PDF bookmarks provide the same navigation.", styles["Small"]),
])
toc = TableOfContents()
toc.levelStyles = [
    ParagraphStyle("TOC0", fontName="Body", fontSize=9, leading=13, spaceBefore=5, textColor=INK),
    ParagraphStyle("TOC1", fontName="Body", fontSize=8, leading=11.5, leftIndent=15, spaceBefore=3, textColor=MUTED),
]
story.append(toc)
heading("Architecture at a glance")
story.append(Architecture())
story.append(Paragraph("Read the top lane when studying data engineering. Read the bottom lane when studying the application. Publication connects them: questions use a selected release rather than an unfinished candidate.", styles["Text"]))
parse_markdown((HERE / "PROJECT_HANDBOOK.md").read_text())
heading("Implementation reference")
story.append(Paragraph("The repository's end-to-end codebase guide, included for lookup. Its historical setup observations retain their original scope.", styles["Text"]))
parse_markdown((HERE / "END_TO_END_GUIDE.md").read_text(), appendix=True)
Handbook(OUTPUT).multiBuild(story)
print(OUTPUT)
