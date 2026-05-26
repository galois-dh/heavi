"""Multi-page portfolio PDF generator.

reportlab over weasyprint to keep the runtime image minimal — no Pango/Cairo
system deps to install on Railway. The trade-off is no CSS; we compose the
document from Platypus flowables and a small palette.

Five pages, single-column, Letter portrait, 0.75" margins, Helvetica throughout.
The look is restrained on purpose — navy/white with a single accent blue, no
gradients, no decorative graphics.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from .portfolio_risk import PortfolioJob

# ─── Palette ──────────────────────────────────────────────────────────────
NAVY = colors.HexColor("#0a2540")
ACCENT = colors.HexColor("#0e6fff")
INK = colors.HexColor("#1f2937")
MUTED = colors.HexColor("#6b7280")
RULE = colors.HexColor("#d1d5db")
HIGH = colors.HexColor("#b91c1c")
MED = colors.HexColor("#b45309")
LOW = colors.HexColor("#15803d")
TABLE_BG = colors.HexColor("#f3f4f6")


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=32,
            leading=38,
            textColor=NAVY,
            alignment=TA_LEFT,
            spaceAfter=12,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=14,
            leading=20,
            textColor=MUTED,
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=NAVY,
            spaceBefore=0,
            spaceAfter=10,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=NAVY,
            spaceBefore=14,
            spaceAfter=6,
            letterSpacing=0.6,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=15,
            textColor=INK,
            spaceAfter=6,
        ),
        "small": ParagraphStyle(
            "small",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=MUTED,
        ),
        "kpi_label": ParagraphStyle(
            "kpi_label",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=MUTED,
        ),
        "kpi_value": ParagraphStyle(
            "kpi_value",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            textColor=NAVY,
        ),
    }


# ─── Page header / footer ────────────────────────────────────────────────


def _draw_chrome(canvas, doc):
    canvas.saveState()
    # Header rule
    canvas.setStrokeColor(NAVY)
    canvas.setLineWidth(1.5)
    canvas.line(0.75 * inch, 10.3 * inch, 7.75 * inch, 10.3 * inch)
    # Top-left wordmark
    canvas.setFillColor(NAVY)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(0.75 * inch, 10.45 * inch, "HEAVI")
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 9)
    canvas.drawString(1.20 * inch, 10.45 * inch, "·  Spatial decision intelligence")
    # Top-right doc title
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 9)
    canvas.drawRightString(7.75 * inch, 10.45 * inch, "Wildfire Risk Assessment")
    # Footer
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.4)
    canvas.line(0.75 * inch, 0.55 * inch, 7.75 * inch, 0.55 * inch)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(
        0.75 * inch,
        0.4 * inch,
        f"Generated {datetime.utcnow().strftime('%Y-%m-%d')} · Sonoma County wildfire model v0.1 · Confidential",
    )
    canvas.drawRightString(7.75 * inch, 0.4 * inch, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


# ─── Page builders ───────────────────────────────────────────────────────


def _page_cover(job: PortfolioJob, styles: dict[str, ParagraphStyle]) -> list[Any]:
    n = job.portfolio_summary.get("property_count", 0)
    date_str = job.created_at.strftime("%B %d, %Y")
    flowables: list[Any] = []
    flowables.append(Spacer(1, 1.8 * inch))
    flowables.append(Paragraph("Wildfire Risk", styles["title"]))
    flowables.append(Paragraph("Portfolio Assessment", styles["title"]))
    flowables.append(Spacer(1, 0.35 * inch))
    flowables.append(
        Paragraph(
            f"<font color='{ACCENT.hexval()}'>{n}</font> properties · Sonoma County, California",
            styles["subtitle"],
        )
    )
    flowables.append(Paragraph(date_str, styles["subtitle"]))
    flowables.append(Spacer(1, 3.0 * inch))
    flowables.append(Paragraph("Prepared by Heavi", styles["body"]))
    flowables.append(
        Paragraph(
            "This document estimates per-property and aggregate wildfire risk "
            "using calibrated hazard, vulnerability, and exposure models. "
            "Intended for decision support; not an insurance pricing document.",
            styles["small"],
        )
    )
    flowables.append(PageBreak())
    return flowables


def _page_executive_summary(job: PortfolioJob, styles: dict[str, ParagraphStyle]) -> list[Any]:
    s = job.portfolio_summary
    flowables: list[Any] = []
    flowables.append(Paragraph("Executive Summary", styles["h1"]))

    # KPI strip (4 boxes)
    kpis = [
        ("Total Annual Risk", _money(s.get("total_annual_risk", 0))),
        ("Mean Risk / Property", _money(s.get("mean_risk", 0))),
        ("High-Risk Properties", f"{s.get('high_risk_count', 0)} / {s.get('scored_count', 0)}"),
        ("Median Risk / Property", _money(s.get("median_risk", 0))),
    ]
    kpi_cells = []
    for label, value in kpis:
        kpi_cells.append(
            [Paragraph(label, styles["kpi_label"]), Paragraph(value, styles["kpi_value"])]
        )
    kpi_table = Table(
        [[c[0] for c in kpi_cells], [c[1] for c in kpi_cells]],
        colWidths=[1.625 * inch] * 4,
        rowHeights=[0.25 * inch, 0.45 * inch],
    )
    kpi_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEABOVE", (0, 0), (-1, 0), 0.5, NAVY),
                ("LINEBELOW", (0, 1), (-1, 1), 0.5, NAVY),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    flowables.append(kpi_table)

    # Narrative
    high_n = s.get("high_risk_count", 0)
    mod_n = s.get("moderate_risk_count", 0)
    low_n = s.get("low_risk_count", 0)
    total_scored = s.get("scored_count", 0)
    total_risk = s.get("total_annual_risk", 0)
    max_risk = s.get("max_risk", 0)

    top_areas = _top_area_phrase(job)

    paragraphs = [
        f"The portfolio carries an estimated <b>{_money(total_risk)} per year</b> in expected "
        f"wildfire-driven destruction loss across {total_scored} scored properties. "
        f"<b>{high_n}</b> of those exceed the high-risk threshold (>$500/yr), "
        f"<b>{mod_n}</b> sit in the moderate band ($50–$500/yr), and "
        f"<b>{low_n}</b> are classified low risk (<$50/yr).",
        f"The highest single-property exposure reaches <b>{_money(max_risk)}/yr</b>, "
        f"with risk concentrating in {top_areas}. Recommended action is to prioritise "
        "defensible-space and home-hardening investment at the top-decile properties "
        "before broader portfolio-wide treatment.",
        "All estimates use the Heavi Sonoma wildfire model v0.1, validated against "
        "CAL FIRE damage inspections from the 2017–2020 Sonoma fire cohort "
        f"(model AUC {job.portfolio_summary.get('model_auc_roc', MODEL_AUC_FALLBACK):.2f} "
        "when available). See Methodology page for the full data lineage.",
    ]
    for p in paragraphs:
        flowables.append(Paragraph(p, styles["body"]))

    flowables.append(PageBreak())
    return flowables


MODEL_AUC_FALLBACK = 0.76


def _top_area_phrase(job: PortfolioJob) -> str:
    """Produce a human-readable description of where the top risk sits."""
    addresses = [
        r.get("resolved_address") or r.get("input_address") or ""
        for r in job.top_10_highest_risk[:3]
    ]
    cities: list[str] = []
    for a in addresses:
        if not a:
            continue
        # Heuristic: pull the city token by finding "..., <City>, Sonoma County"
        parts = [p.strip() for p in a.split(",")]
        for i, part in enumerate(parts):
            if "Sonoma County" in part and i > 0:
                cities.append(parts[i - 1])
                break
    if not cities:
        return "the wildland-urban interface zones north and east of Santa Rosa"
    seen: list[str] = []
    for c in cities:
        if c and c not in seen:
            seen.append(c)
    return "the " + " / ".join(seen[:3]) + " area" + ("s" if len(seen) > 1 else "")


def _page_summary_table(job: PortfolioJob, styles: dict[str, ParagraphStyle]) -> list[Any]:
    s = job.portfolio_summary
    flowables: list[Any] = []
    flowables.append(Paragraph("Portfolio Summary", styles["h1"]))

    flowables.append(Paragraph("AGGREGATE STATISTICS", styles["h2"]))
    agg_rows = [
        ["Property count", str(s.get("property_count", 0))],
        ["Scored", str(s.get("scored_count", 0))],
        ["Geocoding / coverage gaps",
         str(s.get("error_count", 0) + s.get("no_coverage_count", 0))],
        ["Total annual risk", _money(s.get("total_annual_risk", 0))],
        ["Mean risk / property", _money(s.get("mean_risk", 0))],
        ["Median risk / property", _money(s.get("median_risk", 0))],
        ["95th percentile", _money(s.get("p95_risk", 0))],
        ["Maximum", _money(s.get("max_risk", 0))],
    ]
    agg = Table(agg_rows, colWidths=[3.0 * inch, 4.0 * inch])
    agg.setStyle(_kv_table_style())
    flowables.append(agg)

    flowables.append(Paragraph("RISK TIER COUNTS", styles["h2"]))
    tier_rows = [
        ["", "Threshold", "Count", "Share"],
        ["High Risk", ">$500 / yr", str(s.get("high_risk_count", 0)),
         _pct(s.get("high_risk_count", 0), s.get("scored_count", 0))],
        ["Moderate Risk", "$50–500 / yr", str(s.get("moderate_risk_count", 0)),
         _pct(s.get("moderate_risk_count", 0), s.get("scored_count", 0))],
        ["Low Risk", "<$50 / yr", str(s.get("low_risk_count", 0)),
         _pct(s.get("low_risk_count", 0), s.get("scored_count", 0))],
    ]
    tier = Table(tier_rows, colWidths=[1.8 * inch, 1.6 * inch, 1.6 * inch, 2.0 * inch])
    tier.setStyle(_header_table_style(tier_color_col=0, color_map={
        1: HIGH, 2: MED, 3: LOW,
    }))
    flowables.append(tier)

    flowables.append(Paragraph("RISK DISTRIBUTION", styles["h2"]))
    dist_rows = [["Bucket", "Properties", "Share"]]
    n_scored = s.get("scored_count", 0) or 1
    for entry in s.get("risk_distribution", []):
        dist_rows.append(
            [
                entry["bucket"],
                str(entry["n"]),
                _pct(entry["n"], n_scored),
            ]
        )
    dist = Table(dist_rows, colWidths=[2.5 * inch, 2.5 * inch, 2.0 * inch])
    dist.setStyle(_header_table_style())
    flowables.append(dist)

    flowables.append(PageBreak())
    return flowables


def _page_top10(job: PortfolioJob, styles: dict[str, ParagraphStyle]) -> list[Any]:
    flowables: list[Any] = []
    flowables.append(Paragraph("Top 10 Highest-Risk Properties", styles["h1"]))
    flowables.append(
        Paragraph(
            "Sorted by annual risk estimate (descending). Key factors columns show the "
            "raw value plus a tier callout (H / M / L) reflecting that factor's risk "
            "contribution.",
            styles["small"],
        )
    )
    flowables.append(Spacer(1, 0.15 * inch))

    header = [
        "#",
        "Address",
        "Annual Risk",
        "P(destroy)",
        "Wildfire Likelihood",
        "Dist. to Fuel",
        "Canopy (100m)",
        "Slope",
    ]
    rows: list[list[str]] = [header]
    for i, r in enumerate(job.top_10_highest_risk, 1):
        addr = _short_address(r.get("resolved_address") or r.get("input_address") or "—")
        eal = _money(r.get("annual_risk_usd") or 0)
        feats = r.get("features") or {}
        vs = r.get("vulnerability_score") or {}
        rows.append(
            [
                str(i),
                addr,
                eal,
                f"{(vs.get('p_destroyed', 0) * 100):.1f}%",
                f"{feats.get('burn_probability', 0):.4f}",
                f"{feats.get('distance_to_fuel_m', 0):.0f} m",
                f"{feats.get('canopy_cover_100m', 0):.0f}%",
                f"{feats.get('slope_degrees', 0):.1f}°",
            ]
        )

    col_widths = [
        0.30 * inch,
        2.20 * inch,
        0.85 * inch,
        0.75 * inch,
        0.90 * inch,
        0.75 * inch,
        0.75 * inch,
        0.55 * inch,
    ]
    table = Table(rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("ALIGN", (0, 0), (0, -1), "RIGHT"),
                ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
                ("ALIGN", (1, 0), (1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
                ("LINEBELOW", (0, 0), (-1, 0), 1.0, NAVY),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, TABLE_BG]),
            ]
        )
    )
    flowables.append(table)
    flowables.append(PageBreak())
    return flowables


def _page_methodology(job: PortfolioJob, styles: dict[str, ParagraphStyle]) -> list[Any]:
    flowables: list[Any] = []
    flowables.append(Paragraph("Methodology & Data Sources", styles["h1"]))

    flowables.append(Paragraph("DECOMPOSITION", styles["h2"]))
    flowables.append(
        Paragraph(
            "<b>Risk Estimate = Wildfire Likelihood × P(destroyed | features) × "
            "Replacement Value.</b><br/>"
            "Classical frequency-severity decomposition "
            "(Klugman, Panjer & Willmot, <i>Loss Models</i>, §6).",
            styles["body"],
        )
    )

    flowables.append(Paragraph("DATA SOURCES", styles["h2"]))
    data_rows = [
        ["Layer", "Source", "Vintage"],
        ["Wildfire likelihood", "USFS WRC FSim simulation", "LANDFIRE 2014"],
        ["Fuel & canopy cover", "USGS LANDFIRE (FBFM40, CC)", "2022"],
        ["Terrain slope", "USGS 3DEP 1 m DEM, resampled to 30 m", "Current"],
        ["Structure exposure", "USACE National Structures Inventory (NSI) v2", "2024"],
        ["Calibration labels", "CAL FIRE Damage Inspection (DINS)", "2017–2020"],
    ]
    src = Table(data_rows, colWidths=[1.75 * inch, 3.75 * inch, 1.5 * inch])
    src.setStyle(_header_table_style())
    flowables.append(src)

    flowables.append(Paragraph("VALIDATION", styles["h2"]))
    auc = job.portfolio_summary.get("model_auc_roc") or MODEL_AUC_FALLBACK
    flowables.append(
        Paragraph(
            f"Calibrated logistic-regression vulnerability model with AUC-ROC "
            f"<b>{auc:.2f}</b> on a held-out 20% validation sample (1,420 properties), "
            "stratified by fire event across Tubbs (2017), Nuns (2017), Kincade (2019), "
            "Glass (2020), and the LNU Lightning Complex (2020).",
            styles["body"],
        )
    )

    flowables.append(Paragraph("KNOWN LIMITATIONS", styles["h2"]))
    flowables.append(
        Paragraph(
            "<b>Conditioning caveat (high severity).</b> Wildfire likelihood appears "
            "both in the hazard term and as a predictor in the vulnerability model. "
            "The two contributions partially cancel; absolute risk magnitudes are "
            "directionally informative but should not be treated as cardinal dollar "
            "expectations.",
            styles["body"],
        )
    )
    flowables.append(
        Paragraph(
            "<b>Tubbs dominance (high severity).</b> 75% of destroyed-class training "
            "records come from the Tubbs fire. Coffey Park-style urban-edge geometries "
            "are over-represented in the calibrated coefficients.",
            styles["body"],
        )
    )
    flowables.append(
        Paragraph(
            "<b>Total-loss severity (low severity).</b> Severity is set to 100% of "
            "replacement value given destruction; industry-typical mean damage ratios "
            "are 0.70–0.85, so reported risk is biased upward 15–30%.",
            styles["body"],
        )
    )

    flowables.append(Paragraph("HASH", styles["h2"]))
    flowables.append(
        Paragraph(
            f"Methodology hash <font face='Courier'>"
            f"{(job.portfolio_summary.get('methodology_hash') or '').strip() or 'see model bundle'}"
            f"</font>. The hash binds this document to a specific model version; "
            "regenerated when data sources, parameters, references, or limitations change.",
            styles["small"],
        )
    )
    return flowables


# ─── Table styles ────────────────────────────────────────────────────────


def _kv_table_style() -> TableStyle:
    return TableStyle(
        [
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 10.5),
            ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
            ("TEXTCOLOR", (1, 0), (1, -1), INK),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
    )


def _header_table_style(
    *,
    tier_color_col: int | None = None,
    color_map: dict[int, colors.Color] | None = None,
) -> TableStyle:
    style = TableStyle(
        [
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9.5),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("TEXTCOLOR", (0, 1), (-1, -1), INK),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, TABLE_BG]),
        ]
    )
    if color_map and tier_color_col is not None:
        for row_idx, color in color_map.items():
            style.add("TEXTCOLOR", (tier_color_col, row_idx), (tier_color_col, row_idx), color)
            style.add(
                "FONTNAME",
                (tier_color_col, row_idx),
                (tier_color_col, row_idx),
                "Helvetica-Bold",
            )
    return style


# ─── Helpers ─────────────────────────────────────────────────────────────


def _money(v: float | int) -> str:
    if v is None:
        return "—"
    if v < 1:
        return f"${v:.2f}"
    return f"${v:,.0f}"


def _pct(num: float, den: float) -> str:
    if not den:
        return "—"
    return f"{(num / den * 100):.1f}%"


def _short_address(addr: str, max_len: int = 38) -> str:
    if len(addr) <= max_len:
        return addr
    # Take the leading "<street>, <city>" if present.
    parts = [p.strip() for p in addr.split(",")]
    head = ", ".join(parts[:2]) if len(parts) >= 2 else addr
    return head[: max_len - 1] + "…" if len(head) > max_len else head


# ─── Driver ──────────────────────────────────────────────────────────────


def render_pdf(job: PortfolioJob) -> bytes:
    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf,
        pagesize=LETTER,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=1.0 * inch,
        bottomMargin=0.85 * inch,
        title="Wildfire Risk Assessment",
        author="Heavi",
    )
    frame = Frame(
        doc.leftMargin,
        doc.bottomMargin,
        doc.width,
        doc.height,
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )
    doc.addPageTemplates([PageTemplate(id="main", frames=frame, onPage=_draw_chrome)])

    styles = _styles()
    story: list[Any] = []
    story.extend(_page_cover(job, styles))
    story.extend(_page_executive_summary(job, styles))
    story.extend(_page_summary_table(job, styles))
    story.extend(_page_top10(job, styles))
    story.extend(_page_methodology(job, styles))

    doc.build(story)
    return buf.getvalue()
