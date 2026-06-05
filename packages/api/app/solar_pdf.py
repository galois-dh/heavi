"""Professional PDF export of a solar suitability assessment (Month-1 Sprint F3).

Single-site (summary + per-criterion + methodology) and batch portfolio (ranked
summary + one detail page per site) PDFs, rendered with reportlab platypus —
same engine as portfolio_pdf.py, kept self-contained here.

Input is the score_solar_siting() output dict; for batch, a list of them.
"""

from __future__ import annotations

import io
from datetime import date
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ─── Palette ────────────────────────────────────────────────────────────────
NAVY = colors.HexColor("#0a2540")
ACCENT = colors.HexColor("#0e6fff")
INK = colors.HexColor("#1f2937")
MUTED = colors.HexColor("#6b7280")
RULE = colors.HexColor("#d1d5db")
GREEN = colors.HexColor("#15803d")
AMBER = colors.HexColor("#b45309")
RED = colors.HexColor("#b91c1c")
GRAY = colors.HexColor("#6b7280")
TABLE_BG = colors.HexColor("#f3f4f6")
CALLOUT_BG = colors.HexColor("#eef4ff")

_RATING_COLOR = {"High": GREEN, "Moderate": AMBER, "Low": RED, "Excluded": GRAY,
                 "CANNOT ASSESS": GRAY}
_TIER_COLOR = {"HIGH": GREEN, "MODERATE": AMBER, "LOW": RED, "INSUFFICIENT": RED,
               "CANNOT ASSESS": GRAY, "NONE": GRAY}

_EXCL_NAMES = {
    "excl_protected": "Protected areas",
    "excl_wetlands": "Wetlands",
    "excl_critical_habitat": "Critical habitat",
    "excl_steep": "Steep slope",
    "excl_urban": "Urban land",
    "excl_flood": "Flood zone (V)",
}

_DISCLAIMER = (
    "DISCLAIMER: This assessment is based on publicly available federal data and "
    "peer-reviewed methodology. It is intended for screening purposes and does not "
    "replace site-specific field investigation, interconnection studies, or "
    "environmental surveys."
)
_KNOWN_LIMITATIONS = [
    "NWI wetlands data unavailable nationally (SSURGO hydric-soil proxy used).",
    "EJScreen data is a static 2024 snapshot (EPA tool discontinued).",
    "Scoring does not assess interconnection capacity or queue position.",
]


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    def s(name: str, **kw: Any) -> ParagraphStyle:
        kw.setdefault("fontName", "Helvetica")
        kw.setdefault("textColor", INK)
        kw.setdefault("alignment", TA_LEFT)
        return ParagraphStyle(name, parent=base["Normal"], **kw)
    return {
        "title": s("title", fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=NAVY, spaceAfter=2),
        "sub": s("sub", fontSize=10, leading=14, textColor=MUTED, spaceAfter=4),
        "h2": s("h2", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=NAVY, spaceBefore=14, spaceAfter=5),
        "body": s("body", fontSize=10, leading=14, spaceAfter=5),
        "small": s("small", fontSize=8.5, leading=12, textColor=MUTED),
        "kpi_v": s("kpi_v", fontName="Helvetica-Bold", fontSize=22, leading=24, textColor=NAVY),
        "kpi_l": s("kpi_l", fontSize=8, leading=10, textColor=MUTED),
        "callout": s("callout", fontSize=10.5, leading=15, textColor=NAVY),
        "cell": s("cell", fontSize=9, leading=12),
        "cellb": s("cellb", fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=NAVY),
        "disc": s("disc", fontSize=8.5, leading=12, textColor=MUTED, spaceBefore=8),
    }


def _chrome(canvas: Any, doc: Any) -> None:
    """Branded header rule + footer (date, branding, page number) on every page."""
    canvas.saveState()
    w, h = LETTER
    canvas.setFillColor(NAVY)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(0.75 * inch, h - 0.55 * inch, "HEAVI ENERGY")
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(w - 0.75 * inch, h - 0.55 * inch, "Solar Site Suitability Assessment")
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.75)
    canvas.line(0.75 * inch, h - 0.62 * inch, w - 0.75 * inch, h - 0.62 * inch)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(0.75 * inch, 0.5 * inch, f"Generated {date.today().isoformat()} · Heavi")
    canvas.drawRightString(w - 0.75 * inch, 0.5 * inch, f"Page {doc.page}")
    canvas.restoreState()


def _pct(v: float | None) -> str:
    return "—" if v is None else str(round(v * 100))


def _kpi_card(st: dict, label: str, value: str, sub: str, color: Any) -> Table:
    inner = Table(
        [[Paragraph(label, st["kpi_l"])],
         [Paragraph(f'<font color="#{color.hexval()[2:]}">{value}</font>', st["kpi_v"])],
         [Paragraph(sub, st["kpi_l"])]],
        colWidths=[3.0 * inch],
    )
    inner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), TABLE_BG),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBEFORE", (0, 0), (0, -1), 3, color),
    ]))
    return inner


# ─── Single-site flowables ─────────────────────────────────────────────────


def _single_story(st: dict, r: dict[str, Any], address: str | None) -> list:
    q = r.get("query") or {}
    lat, lng = q.get("latitude"), q.get("longitude")
    wp = r.get("weight_profile") or {}
    conf = r.get("confidence") or {}
    rating = r.get("rating") or "—"
    cannot = r.get("cannot_assess") or rating == "CANNOT ASSESS"
    story: list = []

    story.append(Paragraph("Solar Site Suitability Assessment", st["title"]))
    loc = address or (f"{lat:.4f}, {lng:.4f}" if lat is not None else "—")
    story.append(Paragraph(
        f"LOCATION: {loc}" + (f"  ·  NERC REGION: {wp.get('region')}" if wp.get("region") else ""),
        st["sub"]))
    story.append(Spacer(1, 8))

    if cannot:
        story.append(_kpi_card(st, "SITE SCORE", "CANNOT ASSESS", rating, GRAY))
        story.append(Spacer(1, 8))
        story.append(Paragraph(r.get("message") or conf.get("statement") or
                               "Critical data sources unavailable.", st["callout"]))
        return story

    score100 = _pct(r.get("score"))
    cards = Table(
        [[_kpi_card(st, "SITE SCORE", f"{score100} / 100", rating, _RATING_COLOR.get(rating, NAVY)),
          _kpi_card(st, "CONFIDENCE", f"{_pct(conf.get('composite'))} / 100",
                    conf.get("tier") or "—", _TIER_COLOR.get((conf.get("tier") or "").upper(), NAVY))]],
        colWidths=[3.3 * inch, 3.3 * inch],
    )
    cards.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("RIGHTPADDING", (0, 0), (0, 0), 10),
                               ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(cards)
    story.append(Spacer(1, 8))

    if conf.get("statement"):
        story.append(Paragraph(f'"{conf["statement"]}"', st["callout"]))

    gaps = conf.get("gaps") or []
    if gaps:
        story.append(Paragraph("DATA GAPS", st["h2"]))
        for g in gaps[:6]:
            story.append(Paragraph(f"• {g}", st["body"]))

    # Interconnection context (F4) — below the score, above the criterion detail.
    story += _interconnection_section(st, r.get("interconnection_context"))

    # Exclusion screening
    excl = r.get("exclusion_results") or {}
    if excl:
        story.append(Paragraph("EXCLUSION SCREENING", st["h2"]))
        rows = [[Paragraph("Screen", st["cellb"]), Paragraph("Result", st["cellb"]),
                 Paragraph("Source", st["cellb"])]]
        for cid, e in excl.items():
            ex = e.get("excluded")
            mark = "✓ pass" if ex is False else ("✗ EXCLUDED" if ex else "— no data")
            rows.append([Paragraph(_EXCL_NAMES.get(cid, cid), st["cell"]),
                         Paragraph(mark, st["cell"]),
                         Paragraph(str(e.get("selected_source") or "—"), st["cell"])])
        t = Table(rows, colWidths=[2.4 * inch, 1.6 * inch, 2.6 * inch])
        t.setStyle(_table_style())
        story.append(t)

    # Per-criterion detail
    story.append(Paragraph("SCORED CRITERIA", st["h2"]))
    cs = r.get("criteria_scores") or {}
    per = (conf.get("per_criterion") or {})
    rows = [[Paragraph(h, st["cellb"]) for h in ("Criterion", "Weight", "Score", "Source", "Confidence")]]
    for cid, c in cs.items():
        sc = c.get("score")
        rows.append([
            Paragraph(cid, st["cell"]),
            Paragraph(f"{c.get('weight'):.2f}" if c.get("weight") is not None else "—", st["cell"]),
            Paragraph("—" if sc is None else str(round(sc * 100)), st["cell"]),
            Paragraph(str(c.get("selected_source") or "—"), st["cell"]),
            Paragraph(str((per.get(cid) or {}).get("tier") or "—"), st["cell"]),
        ])
    t = Table(rows, colWidths=[1.7 * inch, 0.8 * inch, 0.7 * inch, 2.2 * inch, 1.2 * inch])
    t.setStyle(_table_style())
    story.append(t)

    if wp.get("region"):
        n = wp.get("n_installations_in_calibration")
        note = (f"WEIGHT PROFILE: {wp['region']} — "
                + (f"calibrated against {n} EIA Form 860 installations"
                   if n else str(wp.get("method") or "literature default weights")))
        story.append(Spacer(1, 4))
        story.append(Paragraph(note, st["small"]))
    return story


def _interconnection_section(st: dict, ic: dict[str, Any] | None) -> list:
    if not ic:
        return []
    story: list = [Paragraph("INTERCONNECTION CONTEXT", st["h2"])]
    sub = ic.get("nearest_substation")
    if sub:
        v = f", {sub['voltage_kv']} kV" if sub.get("voltage_kv") else ""
        story.append(Paragraph(
            f"Nearest substation: {sub.get('name')} ({sub.get('distance_mi')} mi{v})", st["body"]))
    story.append(Paragraph(
        f"Existing capacity (within {ic.get('radius_km', 50):.0f} km): "
        f"{ic.get('existing_capacity_mw')} MW across {ic.get('existing_plant_count')} "
        "operating plants (EIA Form 860).", st["body"]))
    qs = ic.get("queue_summary") or {}
    story.append(Paragraph(
        f"Queue activity ({ic.get('iso') or 'n/a'}): {ic.get('queue_projects_nearby')} active "
        f"solar projects totaling {ic.get('queue_capacity_mw')} MW; "
        f"{qs.get('active', 0)} active, {qs.get('completed', 0)} completed, "
        f"{qs.get('withdrawn', 0)} withdrawn (all fuels).", st["body"]))
    story.append(Paragraph(
        "NOTE: Informational context from public data, not an interconnection study. "
        "Actual capacity availability requires an interconnection application with the "
        "ISO/RTO. Queue dataset is representative for demonstration.", st["small"]))
    return story


def _methodology_story(st: dict, r: dict[str, Any]) -> list:
    m = r.get("methodology") or {}
    story: list = [PageBreak(), Paragraph("Methodology", st["title"]), Spacer(1, 4)]
    story.append(Paragraph("FRAMEWORK", st["h2"]))
    story.append(Paragraph("GIS-based Multi-Criteria Decision Analysis (GIS-MCDA)", st["body"]))
    for c in (m.get("framework_citations") or [])[:6]:
        story.append(Paragraph(f"• {c.get('name')} — {c.get('venue', '')}", st["small"]))
    story.append(Paragraph("WEIGHT CALIBRATION", st["h2"]))
    story.append(Paragraph(
        "Constrained optimization (scipy SLSQP) within literature-supported bounds "
        "against EIA Form 860 ground truth, per NERC region.", st["body"]))
    story.append(Paragraph("DATA SOURCES", st["h2"]))
    story.append(Paragraph(
        f"{m.get('criteria_count', 0)} criteria ({m.get('scored_count', 0)} scored, "
        f"{m.get('exclusion_count', 0)} exclusion) from federal and open data sources, "
        "with per-criterion source selection via the data-selection engine and "
        "quality-ordered data trees.", st["body"]))
    story.append(Paragraph("KNOWN LIMITATIONS", st["h2"]))
    for lim in _KNOWN_LIMITATIONS:
        story.append(Paragraph(f"• {lim}", st["body"]))
    story.append(HRFlowable(width="100%", thickness=0.75, color=RULE, spaceBefore=10, spaceAfter=6))
    story.append(Paragraph(_DISCLAIMER, st["disc"]))
    return story


def _table_style() -> TableStyle:
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, TABLE_BG]),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, NAVY),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ])


def _doc(buf: io.BytesIO) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        buf, pagesize=LETTER,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.85 * inch, bottomMargin=0.7 * inch,
        title="Heavi Energy — Solar Site Suitability Assessment", author="Heavi",
    )


# ─── Public API ─────────────────────────────────────────────────────────────


def solar_single_pdf(r: dict[str, Any], address: str | None = None) -> bytes:
    buf = io.BytesIO()
    st = _styles()
    story = _single_story(st, r, address)
    story += _methodology_story(st, r)
    _doc(buf).build(story, onFirstPage=_chrome, onLaterPages=_chrome)
    return buf.getvalue()


def solar_batch_pdf(results: list[dict[str, Any]]) -> bytes:
    """Portfolio PDF: ranked summary page + one detail page per site."""
    buf = io.BytesIO()
    st = _styles()
    story: list = [Paragraph("Solar Portfolio Assessment", st["title"]),
                   Paragraph(f"{len(results)} candidate sites", st["sub"]), Spacer(1, 8)]

    def sort_key(x: dict) -> float:
        if x.get("cannot_assess") or x.get("rating") in ("Excluded", "CANNOT ASSESS"):
            return -1.0
        return x.get("score") or 0.0
    ranked = sorted(results, key=sort_key, reverse=True)

    rows = [[Paragraph(h, st["cellb"]) for h in ("#", "Site", "Score", "Rating", "Confidence")]]
    for i, x in enumerate(ranked, 1):
        excl = x.get("cannot_assess") or x.get("rating") in ("Excluded", "CANNOT ASSESS")
        sc = x.get("score")
        name = x.get("name") or _loc_label(x)
        rows.append([
            Paragraph(str(i), st["cell"]), Paragraph(str(name), st["cell"]),
            Paragraph(x.get("rating") if excl else ("—" if sc is None else str(round(sc * 100))), st["cell"]),
            Paragraph(str(x.get("rating") or "—"), st["cell"]),
            Paragraph(str(((x.get("confidence") or {}).get("tier")) or "—"), st["cell"]),
        ])
    t = Table(rows, colWidths=[0.4 * inch, 2.8 * inch, 0.9 * inch, 1.3 * inch, 1.4 * inch])
    t.setStyle(_table_style())
    story.append(t)

    for x in ranked:
        story.append(PageBreak())
        if x.get("name"):
            story.append(Paragraph(str(x["name"]), st["h2"]))
        story += _single_story(st, x, address=x.get("name"))

    _doc(buf).build(story, onFirstPage=_chrome, onLaterPages=_chrome)
    return buf.getvalue()


def _loc_label(x: dict[str, Any]) -> str:
    q = x.get("query") or {}
    lat, lng = q.get("latitude"), q.get("longitude")
    return f"{lat:.4f}, {lng:.4f}" if lat is not None else "site"
