"""Markdown → polished PDF renderer (Heavi Month-2, Deliverable 1).

A small, dependency-free (reportlab-only) Markdown renderer used to turn the
methodology whitepaper and one-page product overview into branded, multi-page
PDFs. Supports the subset of Markdown those documents use: ATX headings
(`#`/`##`/`###`), pipe tables, unordered (`-`) and ordered (`1.`) lists,
horizontal rules (`---`), blockquotes (`>`), and inline `**bold**` / `` `code` ``.

The first `#` line plus everything up to the first `---` becomes a cover page;
the rest flows as body. Header/footer chrome matches solar_pdf.py.
"""

from __future__ import annotations

import io
import re
from datetime import date
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

NAVY = colors.HexColor("#0a2540")
ACCENT = colors.HexColor("#0e6fff")
INK = colors.HexColor("#1f2937")
MUTED = colors.HexColor("#6b7280")
RULE = colors.HexColor("#d1d5db")
HEADER_BG = colors.HexColor("#0a2540")
ROW_BG = colors.HexColor("#f3f4f6")

CONTENT_W = LETTER[0] - 1.5 * inch  # 0.75" margins


def _styles(footer_label: str) -> dict[str, Any]:
    base = getSampleStyleSheet()

    def s(name: str, **kw: Any) -> ParagraphStyle:
        kw.setdefault("fontName", "Helvetica")
        kw.setdefault("textColor", INK)
        kw.setdefault("alignment", TA_LEFT)
        return ParagraphStyle(name, parent=base["Normal"], **kw)

    return {
        "cover_title": s("cover_title", fontName="Helvetica-Bold", fontSize=24, leading=29,
                         textColor=NAVY, alignment=TA_CENTER, spaceAfter=10),
        "cover_sub": s("cover_sub", fontName="Helvetica", fontSize=14, leading=19,
                       textColor=ACCENT, alignment=TA_CENTER, spaceAfter=18),
        "cover_meta": s("cover_meta", fontSize=10, leading=14, textColor=MUTED,
                        alignment=TA_CENTER),
        "h1": s("h1", fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=NAVY,
                spaceBefore=16, spaceAfter=6),
        "h2": s("h2", fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=NAVY,
                spaceBefore=11, spaceAfter=4),
        "h3": s("h3", fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=INK,
                spaceBefore=8, spaceAfter=3),
        "body": s("body", fontSize=10, leading=15, spaceAfter=7),
        "li": s("li", fontSize=10, leading=14.5),
        "quote": s("quote", fontSize=9.5, leading=14, textColor=NAVY, leftIndent=10,
                   spaceAfter=6),
        "cell": s("cell", fontSize=7.8, leading=10),
        "cellh": s("cellh", fontName="Helvetica-Bold", fontSize=7.8, leading=10,
                   textColor=colors.white),
        "footer_label": footer_label,
    }


_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"\*([^*\n]+?)\*")
_CODE = re.compile(r"`([^`]+?)`")


def _inline(text: str) -> str:
    """Markdown inline → reportlab mini-HTML (escape first, then markup).

    Bold (`**x**`) is resolved before italic (`*x*`) so the double-star delimiters
    are consumed first and the remaining single stars are unambiguously italic.
    """
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = _BOLD.sub(r"<b>\1</b>", text)
    text = _ITALIC.sub(r"<i>\1</i>", text)
    text = _CODE.sub(r'<font face="Courier" size="8.5">\1</font>', text)
    return text


def _chrome_factory(footer_label: str):
    def _chrome(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        w, h = LETTER
        canvas.setFillColor(NAVY)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(0.75 * inch, h - 0.55 * inch, "HEAVI ENERGY")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(w - 0.75 * inch, h - 0.55 * inch, footer_label)
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.75)
        canvas.line(0.75 * inch, h - 0.62 * inch, w - 0.75 * inch, h - 0.62 * inch)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(0.75 * inch, 0.5 * inch, f"Generated {date.today().isoformat()} · Heavi")
        canvas.drawRightString(w - 0.75 * inch, 0.5 * inch, f"Page {doc.page}")
        canvas.restoreState()
    return _chrome


def _table_flowable(rows: list[list[str]], st: dict) -> Table:
    header, body = rows[0], rows[1:]
    ncols = len(header)
    # Even columns, but give a roomier first column for label-led tables.
    if ncols >= 4:
        first = CONTENT_W * 0.20
        rest = (CONTENT_W - first) / (ncols - 1)
        widths = [first] + [rest] * (ncols - 1)
    else:
        widths = [CONTENT_W / ncols] * ncols
    data = [[Paragraph(_inline(c), st["cellh"]) for c in header]]
    for r in body:
        data.append([Paragraph(_inline(c), st["cell"]) for c in r])
    t = Table(data, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, NAVY),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, RULE),
    ]
    for i in range(1, len(body) + 1):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), ROW_BG))
    t.setStyle(TableStyle(style))
    return t


def _split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_sep(line: str) -> bool:
    return bool(re.fullmatch(r"\|?[\s:\-|]+\|?", line.strip())) and "-" in line


def markdown_to_pdf(md: str, footer_label: str = "Methodology Whitepaper",
                    cover: bool = True) -> bytes:
    st = _styles(footer_label)
    lines = md.split("\n")
    story: list[Any] = []

    i = 0
    n = len(lines)
    if i < n and lines[i].startswith("# ") and cover:
        # ── Full cover page: title, subtitle, meta lines, to first '---'
        story.append(Spacer(1, 1.6 * inch))
        story.append(Paragraph(_inline(lines[i][2:].strip()), st["cover_title"]))
        i += 1
        while i < n and not lines[i].startswith("---"):
            ln = lines[i].strip()
            if ln.startswith("## "):
                story.append(Paragraph(_inline(ln[3:].strip()), st["cover_sub"]))
            elif ln:
                story.append(Paragraph(_inline(ln), st["cover_meta"]))
            i += 1
        story.append(Spacer(1, 0.4 * inch))
        story.append(HRFlowable(width="40%", thickness=1, color=RULE,
                                hAlign="CENTER", spaceBefore=8, spaceAfter=8))
        story.append(PageBreak())
        if i < n and lines[i].startswith("---"):
            i += 1
    elif i < n and lines[i].startswith("# "):
        # ── Inline title (short documents): big heading, no separate cover page
        story.append(Paragraph(_inline(lines[i][2:].strip()), st["h1"]))
        i += 1

    # ── Body
    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue
        if stripped.startswith("---"):
            story.append(HRFlowable(width="100%", thickness=0.5, color=RULE,
                                    spaceBefore=6, spaceAfter=6))
            i += 1
            continue
        if stripped.startswith("### "):
            story.append(Paragraph(_inline(stripped[4:]), st["h3"]))
            i += 1
            continue
        if stripped.startswith("## "):
            story.append(Paragraph(_inline(stripped[3:]), st["h2"]))
            i += 1
            continue
        if stripped.startswith("# "):
            story.append(Paragraph(_inline(stripped[2:]), st["h1"]))
            i += 1
            continue

        # Pipe table: header row followed by a separator row
        if stripped.startswith("|") and i + 1 < n and _is_sep(lines[i + 1]):
            rows = [_split_row(stripped)]
            i += 2  # skip header + separator
            while i < n and lines[i].strip().startswith("|"):
                rows.append(_split_row(lines[i]))
                i += 1
            story.append(_table_flowable(rows, st))
            story.append(Spacer(1, 5))
            continue

        # Ordered list (1. 2. ...)
        if re.match(r"\d+\.\s+", stripped):
            items = []
            while i < n and re.match(r"\d+\.\s+", lines[i].strip()):
                txt = re.sub(r"^\d+\.\s+", "", lines[i].strip())
                # continuation lines (indented, no new marker)
                j = i + 1
                while j < n and lines[j].strip() and not re.match(r"\d+\.\s+", lines[j].strip()) \
                        and not lines[j].strip().startswith(("-", "#", "|", ">")):
                    txt += " " + lines[j].strip()
                    j += 1
                items.append(ListItem(Paragraph(_inline(txt), st["li"]), leftIndent=18))
                i = j
            story.append(ListFlowable(items, bulletType="1", leftIndent=14,
                                      bulletFormat="%s.", spaceAfter=6))
            continue

        # Unordered list (- ...)
        if stripped.startswith("- "):
            items = []
            while i < n and lines[i].strip().startswith("- "):
                txt = lines[i].strip()[2:]
                j = i + 1
                while j < n and lines[j].strip() and not lines[j].strip().startswith(
                        ("-", "#", "|", ">")) and not re.match(r"\d+\.\s+", lines[j].strip()):
                    txt += " " + lines[j].strip()
                    j += 1
                items.append(ListItem(Paragraph(_inline(txt), st["li"]), leftIndent=12))
                i = j
            story.append(ListFlowable(items, bulletType="bullet", leftIndent=12,
                                      start="•", spaceAfter=6))
            continue

        # Blockquote
        if stripped.startswith(">"):
            txt = stripped.lstrip(">").strip()
            story.append(Paragraph(_inline(txt), st["quote"]))
            i += 1
            continue

        # Paragraph: gather until blank or a block marker
        buf = [stripped]
        i += 1
        while i < n and lines[i].strip() and not lines[i].strip().startswith(
                ("#", "-", "|", ">", "---")) and not re.match(r"\d+\.\s+", lines[i].strip()):
            buf.append(lines[i].strip())
            i += 1
        story.append(Paragraph(_inline(" ".join(buf)), st["body"]))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=LETTER,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.85 * inch, bottomMargin=0.75 * inch,
        title="Heavi Energy — Methodology Whitepaper", author="Heavi Energy",
    )
    chrome = _chrome_factory(footer_label)
    doc.build(story, onFirstPage=chrome, onLaterPages=chrome)
    return buf.getvalue()
