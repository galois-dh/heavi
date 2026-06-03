"""Multi-page portfolio PDF generator.

reportlab over weasyprint to keep the runtime image minimal — no Pango/Cairo
system deps to install on Railway. The trade-off is no CSS; we compose the
document from Platypus flowables and a small palette.

Single-column, Letter portrait, 0.75" margins, Helvetica throughout. The look
is restrained on purpose — navy/white with a single accent blue, no
gradients, no decorative graphics.

Page sequence:
  1. Cover
  2. Executive summary — KPI strip + benchmark + validation callout + narrative
  3. Portfolio risk map (matplotlib scatter)
  4. Portfolio summary tables
  5–7. Top-10 properties as cards (2-3 per page) with satellite imagery,
        factor table, historical-fire context, and interpretive narrative
  Final. Methodology
"""

from __future__ import annotations

import io
import math
import os
import statistics
from datetime import datetime
from typing import Any

import httpx
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    Image,
    KeepTogether,
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
CALLOUT_BG = colors.HexColor("#eef4ff")
CALLOUT_RULE = colors.HexColor("#bfd2ff")

# Risk-tier hex values used in the matplotlib map page. Slightly more saturated
# than the table-cell palette so the dots read at small sizes.
MAP_HIGH = "#EF4444"
MAP_MED = "#EAB308"
MAP_LOW = "#22C55E"

MODEL_AUC_FALLBACK = 0.76


# ─── Styles ──────────────────────────────────────────────────────────────


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
        "h3": ParagraphStyle(
            "h3",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=NAVY,
            spaceBefore=4,
            spaceAfter=4,
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
        "narrative": ParagraphStyle(
            "narrative",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=9.5,
            leading=13,
            textColor=INK,
            leftIndent=4,
            spaceBefore=4,
            spaceAfter=2,
        ),
        "callout_body": ParagraphStyle(
            "callout_body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=NAVY,
            spaceAfter=4,
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
        "tier_badge": ParagraphStyle(
            "tier_badge",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=11,
            textColor=colors.white,
            alignment=1,  # center
        ),
        "card_addr": ParagraphStyle(
            "card_addr",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=13,
            textColor=NAVY,
        ),
        "card_meta": ParagraphStyle(
            "card_meta",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=10,
            textColor=MUTED,
        ),
    }


# ─── Page header / footer ────────────────────────────────────────────────


def _draw_chrome(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(NAVY)
    canvas.setLineWidth(1.5)
    canvas.line(0.75 * inch, 10.3 * inch, 7.75 * inch, 10.3 * inch)
    canvas.setFillColor(NAVY)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(0.75 * inch, 10.45 * inch, "HEAVI")
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 9)
    canvas.drawString(1.20 * inch, 10.45 * inch, "·  Spatial decision intelligence")
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 9)
    canvas.drawRightString(7.75 * inch, 10.45 * inch, "Wildfire Risk Assessment")
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


# ─── Mapbox imagery (graceful fallback when MAPBOX_TOKEN not set) ────────


def _mapbox_url(lat: float, lng: float) -> str | None:
    token = os.getenv("MAPBOX_TOKEN")
    if not token:
        return None
    return (
        "https://api.mapbox.com/styles/v1/mapbox/satellite-v9/static/"
        f"{lng},{lat},18,0/400x300@2x?access_token={token}"
    )


def _fetch_satellite(lat: float, lng: float, cache: dict[str, bytes | None]) -> bytes | None:
    """Fetch a Mapbox satellite tile for the given coordinate.
    Returns None on any failure — the PDF renders fine without imagery.
    Caches the bytes (or the negative result) on the job dict so repeated
    PDF generations for the same job don't re-fetch."""
    key = f"{lat:.6f},{lng:.6f}"
    if key in cache:
        return cache[key]
    url = _mapbox_url(lat, lng)
    if not url:
        cache[key] = None
        return None
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(url)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
            cache[key] = r.content
            return r.content
    except httpx.HTTPError:
        pass
    cache[key] = None
    return None


def _fetch_basemap(
    center_lng: float, center_lat: float, zoom: float, pixel_w: int, pixel_h: int
) -> bytes | None:
    """Fetch a Mapbox light-v11 basemap centered on (lng, lat) at the given
    zoom. Used as the underlay for the portfolio map. Returns None on any
    failure so the caller falls back to the blank-background scatter."""
    token = os.getenv("MAPBOX_TOKEN")
    if not token:
        return None
    # Mapbox caps width/height at 1280 each; we stay well under that. The @2x
    # suffix doubles the rendered pixel count without changing the geographic
    # extent so the basemap is crisp on the PDF page.
    url = (
        "https://api.mapbox.com/styles/v1/mapbox/light-v11/static/"
        f"{center_lng},{center_lat},{zoom:.2f},0,0/"
        f"{pixel_w}x{pixel_h}@2x?access_token={token}"
    )
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(url)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
            return r.content
    except httpx.HTTPError:
        pass
    return None


# Web-Mercator helpers for translating a Mapbox static-map response back
# into a (lon_min, lon_max, lat_min, lat_max) extent. The Mapbox API renders
# in Web Mercator; latitude bounds need the inverse-Mercator function so the
# basemap aligns with the scatter points (which are in raw lat/lng).
def _lat_to_mercator_y(lat_deg: float, world_pixels: float) -> float:
    lat_rad = math.radians(lat_deg)
    return world_pixels * (
        0.5 - math.log(math.tan(math.pi / 4 + lat_rad / 2)) / (2 * math.pi)
    )


def _mercator_y_to_lat(y: float, world_pixels: float) -> float:
    n = math.pi * (1 - 2 * y / world_pixels)
    return math.degrees(math.atan(math.sinh(n)))


def _image_extent_from_center(
    center_lng: float, center_lat: float, zoom: float, pixel_w: int, pixel_h: int
) -> tuple[float, float, float, float]:
    """Return (lon_min, lon_max, lat_min, lat_max) for a Mapbox image of
    pixel_w × pixel_h pixels centred on (center_lng, center_lat) at the
    given zoom. Longitude uses the linear Mercator equation; latitude uses
    the inverse Mercator so the bottom and top edges line up with the
    actual rendered geography (matters more as the extent grows)."""
    world_pixels = 256.0 * (2 ** zoom)
    half_lon = (pixel_w / 2) * 360.0 / world_pixels
    cy_pixel = _lat_to_mercator_y(center_lat, world_pixels)
    lat_top = _mercator_y_to_lat(cy_pixel - pixel_h / 2, world_pixels)
    lat_bot = _mercator_y_to_lat(cy_pixel + pixel_h / 2, world_pixels)
    return (center_lng - half_lon, center_lng + half_lon, lat_bot, lat_top)


# ─── Matplotlib portfolio map ────────────────────────────────────────────


def _portfolio_map_png(job: PortfolioJob) -> bytes | None:
    """Render the portfolio map as a PNG byte string.

    When MAPBOX_TOKEN is set we fetch a Mapbox light-v11 basemap covering
    the property bounding box and lay the risk-tier scatter dots on top.
    When the token is unset or the fetch fails we fall back to the
    previous white-background scatter with the Sonoma bbox in grey. Either
    way the function is allowed to return None only if matplotlib itself
    is missing — the PDF caller treats that as "skip this page" and the
    rest of the document still renders.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")  # no display server
        import matplotlib.image as mpimg
        import matplotlib.patches as mpatches
        import matplotlib.pyplot as plt
    except Exception:
        return None

    high, mod, low, unscored = [], [], [], []
    for r in job.per_property:
        if r.get("latitude") is None or r.get("longitude") is None:
            continue
        point = (r["longitude"], r["latitude"])
        eal = r.get("annual_risk_usd")
        if eal is None:
            unscored.append(point)
        elif eal > 500:
            high.append(point)
        elif eal >= 50:
            mod.append(point)
        else:
            low.append(point)

    all_pts = high + mod + low + unscored
    SONOMA_BBOX = (-123.55, 38.05, -122.35, 38.86)

    # Compute a padded bbox around the points (or fall back to Sonoma).
    if all_pts:
        xs = [p[0] for p in all_pts]
        ys = [p[1] for p in all_pts]
        bbox = [min(xs), min(ys), max(xs), max(ys)]
    else:
        bbox = list(SONOMA_BBOX)
    pad_x = max(0.06, (bbox[2] - bbox[0]) * 0.15)
    pad_y = max(0.06, (bbox[3] - bbox[1]) * 0.15)
    bbox = (bbox[0] - pad_x, bbox[1] - pad_y, bbox[2] + pad_x, bbox[3] + pad_y)

    center_lng = (bbox[0] + bbox[2]) / 2
    center_lat = (bbox[1] + bbox[3]) / 2
    lon_span = max(bbox[2] - bbox[0], 1e-6)
    lat_span = max(bbox[3] - bbox[1], 1e-6)

    pixel_w, pixel_h = 720, 540  # matches the 7.0 × 5.0 inch figsize at 102 dpi
    # Zoom that exactly fits the bbox in each dimension; min of the two so the
    # whole bbox is visible. The minus-0.2 padding shrinks the zoom slightly so
    # the edge points aren't pinned to the image border.
    lon_zoom = math.log2(360.0 * pixel_w / (256.0 * lon_span))
    lat_zoom = math.log2(
        360.0 * pixel_h * math.cos(math.radians(center_lat)) / (256.0 * lat_span)
    )
    zoom = max(0.0, min(18.0, min(lon_zoom, lat_zoom) - 0.2))

    basemap_bytes = _fetch_basemap(center_lng, center_lat, zoom, pixel_w, pixel_h)

    fig, ax = plt.subplots(figsize=(7.0, 5.0), dpi=160)

    if basemap_bytes is not None:
        # Layer the basemap underneath the scatter. We pin aspect='auto' and
        # the axis limits to the image extent so the points plot in the same
        # lat/lng coordinates the basemap was rendered with.
        try:
            img = mpimg.imread(io.BytesIO(basemap_bytes), format="png")
            extent = _image_extent_from_center(
                center_lng, center_lat, zoom, pixel_w, pixel_h
            )
            ax.imshow(img, extent=extent, origin="upper", aspect="auto", zorder=0)
            ax.set_xlim(extent[0], extent[1])
            ax.set_ylim(extent[2], extent[3])
            # Hide tick labels — the basemap provides geographic context.
            ax.set_xticks([])
            ax.set_yticks([])
            ax.set_xlabel("")
            ax.set_ylabel("")
            for spine in ax.spines.values():
                spine.set_color("#9ca3af")
                spine.set_linewidth(0.6)
        except Exception:
            # PNG decode failed for some reason — fall through to plain bg.
            basemap_bytes = None

    if basemap_bytes is None:
        # Fallback: previous white-background scatter with the Sonoma bbox.
        rect = mpatches.Rectangle(
            (SONOMA_BBOX[0], SONOMA_BBOX[1]),
            SONOMA_BBOX[2] - SONOMA_BBOX[0],
            SONOMA_BBOX[3] - SONOMA_BBOX[1],
            linewidth=1.0,
            edgecolor="#9ca3af",
            facecolor="#f3f4f6",
            zorder=1,
        )
        ax.add_patch(rect)
        ax.set_xlim(bbox[0], bbox[2])
        ax.set_ylim(bbox[1], bbox[3])
        ax.set_aspect("equal", adjustable="datalim")
        ax.set_xlabel("Longitude", fontsize=8, color="#6b7280")
        ax.set_ylabel("Latitude", fontsize=8, color="#6b7280")
        ax.tick_params(labelsize=7, colors="#6b7280")
        for spine in ax.spines.values():
            spine.set_color("#d1d5db")
            spine.set_linewidth(0.6)
        ax.grid(True, color="#e5e7eb", linewidth=0.4, zorder=0)

    def _scatter(points, color, label):
        if not points:
            return
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        ax.scatter(
            xs,
            ys,
            c=color,
            s=44,
            edgecolors="white",
            linewidths=0.6,
            zorder=3,
            label=label,
        )

    _scatter(high, MAP_HIGH, f"High ({len(high)})")
    _scatter(mod, MAP_MED, f"Moderate ({len(mod)})")
    _scatter(low, MAP_LOW, f"Low ({len(low)})")
    if unscored:
        _scatter(unscored, "#64748b", f"Unscored ({len(unscored)})")

    leg = ax.legend(
        loc="upper right",
        fontsize=8,
        frameon=True,
        facecolor="white",
        edgecolor="#d1d5db",
    )
    if leg:
        leg.get_frame().set_linewidth(0.5)

    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


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
            "Intended for investment, lending, and portfolio decision support.",
            styles["small"],
        )
    )
    flowables.append(PageBreak())
    return flowables


def _page_executive_summary(job: PortfolioJob, styles: dict[str, ParagraphStyle]) -> list[Any]:
    s = job.portfolio_summary
    flowables: list[Any] = []
    flowables.append(Paragraph("Executive Summary", styles["h1"]))

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
    flowables.append(Spacer(1, 0.15 * inch))

    # Benchmark vs Sonoma county-wide mean.
    portfolio_mean = float(s.get("mean_risk", 0) or 0)
    bench_mean = float(s.get("county_benchmark_mean_eal", 0) or 0)
    bench_n = int(s.get("county_benchmark_n_structures", 0) or 0)
    if bench_mean > 0:
        if bench_mean > 0:
            ratio = portfolio_mean / bench_mean if bench_mean else 0
            comparison = (
                f"{ratio:.1f}× the county average"
                if ratio >= 1.05
                else f"{(1 / ratio):.1f}× below the county average"
                if 0 < ratio < 0.95
                else "in line with the county average"
            )
        bench_para = (
            f"This portfolio's average annual risk of <b>{_money(portfolio_mean)}/property</b> "
            f"compares to the Sonoma County average of <b>{_money(bench_mean)}/property</b> "
            f"(county-wide assessment of {bench_n:,} structures) — "
            f"<b>{comparison}</b>."
        )
        flowables.append(Paragraph(bench_para, styles["body"]))

    # Validation callout: "of N in historical fire perimeters, X% high/mod".
    n_in_perim = int(s.get("in_perimeter_count", 0) or 0)
    if n_in_perim > 0:
        n_hm = int(s.get("in_perimeter_high_or_moderate_count", 0) or 0)
        share = (s.get("in_perimeter_high_or_moderate_share") or 0) * 100
        callout = (
            f"<b>Model validation.</b> Of the <b>{n_in_perim}</b> portfolio "
            f"propert{'y' if n_in_perim == 1 else 'ies'} that fall within historical "
            f"CAL FIRE perimeters (FRAP, all years), the model assigned <b>{n_hm} "
            f"({share:.0f}%)</b> to the High or Moderate risk tiers — concrete "
            f"correspondence between model output and where wildfires actually burned."
        )
        flowables.append(_callout(callout, styles))

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
        f"(model AUC {job.portfolio_summary.get("validation_auc_roc", MODEL_AUC_FALLBACK):.2f} "
        "when available). See Methodology page for the full data lineage.",
    ]
    for p in paragraphs:
        flowables.append(Paragraph(p, styles["body"]))

    flowables.append(PageBreak())
    return flowables


def _callout(html: str, styles: dict[str, ParagraphStyle]) -> Table:
    """A subtle blue callout box for evidence/validation notes."""
    body = Paragraph(html, styles["callout_body"])
    tbl = Table([[body]], colWidths=[7.0 * inch])
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), CALLOUT_BG),
                ("LINEABOVE", (0, 0), (-1, 0), 1.0, CALLOUT_RULE),
                ("LINEBELOW", (0, 0), (-1, -1), 1.0, CALLOUT_RULE),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return tbl


def _top_area_phrase(job: PortfolioJob) -> str:
    addresses = [
        r.get("resolved_address") or r.get("input_address") or ""
        for r in job.top_10_highest_risk[:3]
    ]
    cities: list[str] = []
    for a in addresses:
        if not a:
            continue
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


def _page_portfolio_map(job: PortfolioJob, styles: dict[str, ParagraphStyle]) -> list[Any]:
    flowables: list[Any] = []
    flowables.append(Paragraph("Portfolio Risk Map", styles["h1"]))
    png = _portfolio_map_png(job)
    if png is None:
        flowables.append(
            Paragraph(
                "Map rendering skipped (matplotlib not installed in this build).",
                styles["small"],
            )
        )
        flowables.append(PageBreak())
        return flowables

    img = Image(io.BytesIO(png), width=7.0 * inch, height=5.0 * inch, kind="proportional")
    flowables.append(img)
    flowables.append(Spacer(1, 0.1 * inch))
    flowables.append(
        Paragraph(
            "Properties color-coded by annual risk tier. "
            "Red = High (>$500/yr), Amber = Moderate ($50-$500/yr), Green = Low (<$50/yr). "
            "Light grey box shows the Sonoma County extent.",
            styles["small"],
        )
    )
    flowables.append(PageBreak())
    return flowables


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


# ─── Top-10 detail cards ─────────────────────────────────────────────────


def _factor_drivers(
    record: dict[str, Any], medians: dict[str, float]
) -> list[tuple[str, str]]:
    """Identify the top-2 risk-driving factors by comparing each feature to
    the portfolio median. Direction matters — proximity to fuel is risky
    *low*, canopy is risky *high*. Returns [(label, human_value), …] in
    descending order of risk contribution."""
    f = record.get("features") or {}
    if not f:
        return []
    candidates: list[tuple[float, str, str]] = []  # (score, label, human_value)

    def _norm(value: float, median: float) -> float:
        if median == 0:
            return abs(value)
        return (value - median) / abs(median)

    # wildfire_likelihood: higher = riskier
    bp = float(f.get("wildfire_likelihood", 0) or 0)
    m = medians.get("wildfire_likelihood", 0) or 1e-9
    candidates.append((_norm(bp, m), "elevated wildfire likelihood", f"{bp:.4f}"))

    # distance_to_fuel_m: LOWER = riskier (invert direction)
    dist = float(f.get("distance_to_fuel_m", 0) or 0)
    m = medians.get("distance_to_fuel_m", 0) or 1.0
    candidates.append((_norm(m, dist), "direct adjacency to wildland fuel", f"{dist:.0f} m"))

    # canopy_cover_100m: higher = riskier
    cc = float(f.get("canopy_cover_100m", 0) or 0)
    m = medians.get("canopy_cover_100m", 0) or 1e-9
    candidates.append((_norm(cc, m), "dense canopy within 100 m", f"{cc:.0f}%"))

    # slope_degrees: higher = riskier
    sl = float(f.get("slope_degrees", 0) or 0)
    m = medians.get("slope_degrees", 0) or 1e-9
    candidates.append((_norm(sl, m), "steep terrain slope", f"{sl:.1f}°"))

    # Pick the top 2 by score, but only those clearly above median (>0).
    candidates.sort(key=lambda x: x[0], reverse=True)
    top = [(label, val) for score, label, val in candidates if score > 0][:2]
    if len(top) < 2:
        # Fall back to highest-magnitude drivers regardless of sign.
        top = [(label, val) for _, label, val in candidates[:2]]
    return top


def _portfolio_medians(job: PortfolioJob) -> dict[str, float]:
    """Median feature values across SCORED properties — used as a baseline
    for the per-property narrative."""
    keys = ["wildfire_likelihood", "distance_to_fuel_m", "canopy_cover_100m", "slope_degrees"]
    medians: dict[str, float] = {}
    for k in keys:
        vals = [
            float((r.get("features") or {}).get(k) or 0)
            for r in job.per_property
            if r.get("status") == "scored" and (r.get("features") or {}).get(k) is not None
        ]
        medians[k] = float(statistics.median(vals)) if vals else 0.0
    return medians


def _narrative(record: dict[str, Any], medians: dict[str, float], portfolio_mean: float) -> str:
    """Template-driven 1–2 sentence narrative per property."""
    eal = float(record.get("annual_risk_usd") or 0)
    tier = "High" if eal > 500 else "Moderate" if eal >= 50 else "Low"
    drivers = _factor_drivers(record, medians)

    if len(drivers) >= 2:
        driver_phrase = (
            f"{drivers[0][0]} ({drivers[0][1]}) and {drivers[1][0]} ({drivers[1][1]})"
        )
    elif len(drivers) == 1:
        driver_phrase = f"{drivers[0][0]} ({drivers[0][1]})"
    else:
        driver_phrase = "no single dominant factor"

    # Fire history context — pick the largest-acreage fire that contains
    # the property, if any.
    history = record.get("fire_history") or []
    contained = [f for f in history if f.get("contains_point")]
    if contained:
        contained.sort(key=lambda f: f.get("gis_acres", 0), reverse=True)
        fire = contained[0]
        yr = fire.get("year")
        nm = fire.get("fire_name") or "Unknown"
        if yr:
            history_phrase = (
                f" This property is within the {int(yr)} {nm} fire perimeter "
                f"({fire.get('gis_acres', 0):,.0f} acres burned)."
            )
        else:
            history_phrase = f" This property is within the {nm} fire perimeter."
    elif history:
        nearest = history[0]
        history_phrase = (
            f" Nearest historical fire: the "
            f"{int(nearest['year']) if nearest.get('year') else ''} {nearest['fire_name']} "
            f"at {nearest['distance_miles']:.1f} miles."
        ).strip().replace("  ", " ")
    else:
        history_phrase = ""

    # Comparison to portfolio average.
    if portfolio_mean > 0 and eal > 0:
        ratio = eal / portfolio_mean
        if ratio >= 1.5:
            comp = f"{ratio:.1f}× the portfolio average"
        elif ratio <= 0.5:
            comp = f"{(1 / ratio):.1f}× below the portfolio average"
        else:
            comp = "near the portfolio average"
    else:
        comp = "near the portfolio average"

    return (
        f"{tier} risk driven by {driver_phrase}.{history_phrase} "
        f"Annual risk estimate of {_money(eal)} represents {comp}."
    )


def _tier_chip(tier: str) -> Table:
    color, label = {
        "high": (HIGH, "HIGH"),
        "moderate": (MED, "MODERATE"),
        "low": (LOW, "LOW"),
    }.get(tier, (MUTED, "—"))
    cell = Paragraph(
        f"<font color='white'><b>{label}</b></font>",
        ParagraphStyle("chip", fontName="Helvetica-Bold", fontSize=8, alignment=1, textColor=colors.white),
    )
    tbl = Table([[cell]], colWidths=[0.85 * inch], rowHeights=[0.22 * inch])
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), color),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return tbl


def _property_card(
    rank: int,
    record: dict[str, Any],
    styles: dict[str, ParagraphStyle],
    medians: dict[str, float],
    portfolio_mean: float,
    image_cache: dict[str, bytes | None],
) -> Any:
    """Render a single property card. Returns a KeepTogether of flowables so
    a card never splits across a page break."""
    addr = record.get("resolved_address") or record.get("input_address") or "—"
    eal = float(record.get("annual_risk_usd") or 0)
    tier = "high" if eal > 500 else "moderate" if eal >= 50 else "low"
    feats = record.get("features") or {}
    vs = record.get("property_vulnerability") or {}
    match = record.get("match") or {}

    # Top row: rank · address · tier chip.
    head_cells = [
        Paragraph(f"<b>#{rank}</b>", styles["card_addr"]),
        Paragraph(_short_address(addr, 65), styles["card_addr"]),
        _tier_chip(tier),
    ]
    head = Table(
        [head_cells],
        colWidths=[0.4 * inch, 5.75 * inch, 0.85 * inch],
        rowHeights=[0.30 * inch],
    )
    head.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    # Sub-meta line.
    sub = Paragraph(
        f"<font color='{MUTED.hexval()}'>"
        f"property_id {record.get('property_id') or '—'} · "
        f"{record.get('latitude'):.5f}, {record.get('longitude'):.5f} · "
        f"NSI fd_id {match.get('fd_id', '—')}"
        f"</font>",
        styles["card_meta"],
    )

    # Two-column body: satellite image on the left, factors+fires on the right.
    img_flowable: Any
    img_bytes = _fetch_satellite(
        float(record["latitude"]), float(record["longitude"]), image_cache
    ) if record.get("latitude") is not None and record.get("longitude") is not None else None
    if img_bytes is not None:
        try:
            img = ImageReader(io.BytesIO(img_bytes))
            img_flowable = Image(io.BytesIO(img_bytes), width=2.3 * inch, height=1.725 * inch)
            _ = img  # silence linter; ImageReader probe ensures it's a valid image
        except Exception:
            img_flowable = Paragraph(
                "<i>imagery unavailable</i>", styles["card_meta"]
            )
    else:
        img_flowable = Paragraph(
            "<font color='#9ca3af'><i>"
            f"{'satellite imagery requires MAPBOX_TOKEN' if not os.getenv('MAPBOX_TOKEN') else 'imagery unavailable'}"
            "</i></font>",
            styles["card_meta"],
        )

    # Factor table.
    feature_rows = [
        ["Annual Risk", _money(eal)],
        ["P(destroy)", f"{(vs.get('damage_probability', 0) * 100):.1f}%"],
        ["Wildfire Likelihood", f"{feats.get('wildfire_likelihood', 0):.4f}"],
        ["Distance to Fuel", f"{feats.get('distance_to_fuel_m', 0):.0f} m"],
        ["Canopy (100m)", f"{feats.get('canopy_cover_100m', 0):.0f}%"],
        ["Slope", f"{feats.get('slope_degrees', 0):.1f}°"],
        ["Replacement Value", _money(match.get("replacement_value_usd", 0) or 0)],
    ]
    feature_table = Table(feature_rows, colWidths=[1.4 * inch, 1.2 * inch])
    feature_table.setStyle(_kv_table_style(font_size=8.5, line_below=False))

    # Fire history table (compact).
    fires = record.get("fire_history") or []
    if fires:
        fire_rows: list[list[Any]] = [["Year", "Fire", "Acres", "Dist (mi)"]]
        for f in fires[:6]:
            yr = f.get("year")
            fire_rows.append(
                [
                    str(int(yr)) if yr is not None else "—",
                    _short_text(f.get("fire_name") or "—", 22),
                    f"{f.get('gis_acres', 0):,.0f}",
                    f"{f.get('distance_miles', 0):.1f}",
                ]
            )
        fire_table = Table(
            fire_rows,
            colWidths=[0.45 * inch, 1.6 * inch, 0.7 * inch, 0.65 * inch],
            repeatRows=1,
        )
        fire_table.setStyle(_fire_table_style())
    else:
        fire_table = Paragraph(
            "<font color='#9ca3af'><i>No fires within 5 miles.</i></font>",
            styles["card_meta"],
        )

    right_col_inner = Table(
        [
            [Paragraph("FACTORS", styles["h2"])],
            [feature_table],
            [Paragraph("HISTORICAL FIRES WITHIN 5 MILES", styles["h2"])],
            [fire_table],
        ],
        colWidths=[3.6 * inch],
    )
    right_col_inner.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )

    body = Table(
        [[img_flowable, right_col_inner]],
        colWidths=[2.5 * inch, 4.5 * inch],
    )
    body.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 8),
                ("RIGHTPADDING", (1, 0), (1, 0), 0),
            ]
        )
    )

    narrative = Paragraph(_narrative(record, medians, portfolio_mean), styles["narrative"])

    rule = HRFlowable(width="100%", thickness=0.4, color=RULE, spaceBefore=4, spaceAfter=4)

    return KeepTogether(
        [
            head,
            sub,
            Spacer(1, 0.08 * inch),
            body,
            narrative,
            rule,
        ]
    )


def _pages_top10(job: PortfolioJob, styles: dict[str, ParagraphStyle]) -> list[Any]:
    flowables: list[Any] = []
    flowables.append(Paragraph("Top 10 Highest-Risk Properties", styles["h1"]))
    flowables.append(
        Paragraph(
            "Each card shows the property's satellite context, factor breakdown, "
            "historical fires within five miles, and a one-sentence narrative "
            "identifying the top risk drivers and the property's position relative "
            "to the portfolio average.",
            styles["small"],
        )
    )
    flowables.append(Spacer(1, 0.15 * inch))

    medians = _portfolio_medians(job)
    portfolio_mean = float(job.portfolio_summary.get("mean_risk", 0) or 0)

    for rank, record in enumerate(job.top_10_highest_risk, 1):
        flowables.append(
            _property_card(
                rank=rank,
                record=record,
                styles=styles,
                medians=medians,
                portfolio_mean=portfolio_mean,
                image_cache=job.satellite_image_cache,
            )
        )

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
        ["Historical fire perimeters", "CAL FIRE FRAP", "1878–present"],
        ["Satellite imagery", "Mapbox Satellite (when MAPBOX_TOKEN set)", "Current"],
    ]
    src = Table(data_rows, colWidths=[1.75 * inch, 3.75 * inch, 1.5 * inch])
    src.setStyle(_header_table_style())
    flowables.append(src)

    flowables.append(Paragraph("VALIDATION", styles["h2"]))
    auc = job.portfolio_summary.get("validation_auc_roc") or MODEL_AUC_FALLBACK
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


def _kv_table_style(*, font_size: float = 10.5, line_below: bool = True) -> TableStyle:
    styles = [
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ("TEXTCOLOR", (1, 0), (1, -1), INK),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    if line_below:
        styles.append(("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE))
    return TableStyle(styles)


def _fire_table_style() -> TableStyle:
    return TableStyle(
        [
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
            ("ALIGN", (1, 0), (1, -1), "LEFT"),
            ("TEXTCOLOR", (0, 1), (-1, -1), INK),
            ("LINEBELOW", (0, 0), (-1, -1), 0.3, RULE),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
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
    parts = [p.strip() for p in addr.split(",")]
    head = ", ".join(parts[:2]) if len(parts) >= 2 else addr
    return head[: max_len - 1] + "…" if len(head) > max_len else head


def _short_text(s: str, max_len: int) -> str:
    return s if len(s) <= max_len else s[: max_len - 1] + "…"


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
    story.extend(_page_portfolio_map(job, styles))
    story.extend(_page_summary_table(job, styles))
    story.extend(_pages_top10(job, styles))
    story.extend(_page_methodology(job, styles))

    doc.build(story)
    return buf.getvalue()
