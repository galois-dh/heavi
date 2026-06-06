"""Professional PDF export of a property hazard assessment (wildfire + flood).

Single-site report for the score_hazard() output: per-peril risk cards with the
NSI replacement-value provenance, confidence, and methodology. Reuses the solar
PDF's palette and layout helpers; the chrome footer is hazard-specific.

The dollar estimate reads "N/A — no structure data available" when NSI matched no
structure at the location (rather than valuing a non-existent building).
"""

from __future__ import annotations

import io
from datetime import date
from typing import Any

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from .solar_pdf import AMBER, GRAY, GREEN, MUTED, NAVY, RED, RULE, _kpi_card, _styles

# Hazard risk tiers invert the solar palette: HIGH risk is bad (red), LOW is good.
_RISK_COLOR = {"HIGH": RED, "MODERATE": AMBER, "LOW": GREEN, "CANNOT ASSESS": GRAY}
NSI_NA = "N/A — no structure data available"


def _money(v: float | None) -> str:
    return "—" if v is None else f"${round(v):,.0f}/yr"


def _chrome(canvas: Any, doc: Any) -> None:
    canvas.saveState()
    w, h = LETTER
    canvas.setFillColor(NAVY)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(0.75 * inch, h - 0.55 * inch, "HEAVI HAZARD")
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(w - 0.75 * inch, h - 0.55 * inch, "Property Hazard Assessment")
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.75)
    canvas.line(0.75 * inch, h - 0.62 * inch, w - 0.75 * inch, h - 0.62 * inch)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(0.75 * inch, 0.5 * inch, f"Generated {date.today().isoformat()} · Heavi")
    canvas.drawRightString(w - 0.75 * inch, 0.5 * inch, f"Page {doc.page}")
    canvas.restoreState()


def _nsi_basis_line(st: dict, peril: dict[str, Any]) -> list:
    """The 'Based on NSI estimated replacement value of $X (building type)' line."""
    val = peril.get("nsi_replacement_value")
    if peril.get("nsi_available") is False or val is None:
        return []
    bt = peril.get("nsi_building_type")
    suffix = f" ({bt})" if bt else ""
    src = peril.get("nsi_source") or "USACE National Structure Inventory"
    return [Paragraph(
        f"Based on {src} estimated replacement value of ${round(val):,.0f}{suffix}.",
        st["small"])]


def _peril_section(st: dict, title: str, peril: dict[str, Any], extra: list) -> list:
    story: list = [Paragraph(title, st["h2"])]
    cannot = peril.get("cannot_assess") or peril.get("risk_tier") == "CANNOT ASSESS"
    if cannot:
        story.append(Paragraph(
            peril.get("message") or f"{title} cannot be assessed at this location.", st["body"]))
        return story

    tier = peril.get("risk_tier")
    na = peril.get("nsi_available") is False
    dollar = NSI_NA if na else _money(peril.get("annual_risk_usd"))
    color = _RISK_COLOR.get((tier or "").upper(), NAVY)
    story.append(_kpi_card(st, "ANNUAL RISK", dollar, f"{tier or '—'} risk", color))
    story.append(Spacer(1, 4))
    story += _nsi_basis_line(st, peril)
    for line in extra:
        story.append(Paragraph(line, st["body"]))
    return story


def hazard_single_pdf(r: dict[str, Any], address: str | None = None) -> bytes:
    st = _styles()
    q = r.get("query") or {}
    lat, lng = q.get("latitude"), q.get("longitude")
    wf = r.get("wildfire") or {}
    fl = r.get("flood") or {}
    conf = r.get("confidence") or {}

    story: list = [Paragraph("Property Hazard Assessment", st["title"])]
    loc = address or (f"{lat:.4f}, {lng:.4f}" if lat is not None else "—")
    story.append(Paragraph(f"LOCATION: {loc}", st["sub"]))
    story.append(Spacer(1, 8))

    # Wildfire
    wf_extra = []
    if wf.get("damage_probability") is not None:
        wf_extra.append(f"Damage probability if a fire reaches the vicinity: "
                        f"{round(wf['damage_probability'] * 100)}%.")
    if wf.get("fire_frequency_per_year") is not None:
        wf_extra.append(f"Historical fire frequency: {wf['fire_frequency_per_year']} per year.")
    story += _peril_section(st, "WILDFIRE", wf, wf_extra)
    story.append(Spacer(1, 8))

    # Flood
    fl_extra = []
    zone = fl.get("flood_zone")
    fl_extra.append(f"FEMA flood zone: {zone or 'X / unmapped'}"
                    + (f" · depth {fl['depth_ft']} ft" if fl.get("depth_ft") is not None else "")
                    + ".")
    dmg = fl.get("damage") or {}
    if dmg.get("total_loss_usd") is not None and fl.get("nsi_available") is not False:
        fl_extra.append(f"Modeled loss if the design flood occurs: "
                        f"${round(dmg['total_loss_usd']):,.0f} "
                        f"(structure + contents, HAZUS {dmg.get('hazus_occupancy_class', '—')}).")
    story += _peril_section(st, "FLOOD", fl, fl_extra)
    story.append(Spacer(1, 10))

    # Confidence
    if conf.get("statement"):
        story.append(Paragraph("CONFIDENCE", st["h2"]))
        story.append(Paragraph(
            f"{conf.get('tier', '—')} · {conf['statement']}", st["body"]))
    gaps = conf.get("gaps") or []
    if gaps:
        story.append(Paragraph("DATA GAPS", st["h2"]))
        for g in gaps[:6]:
            msg = g.get("message") if isinstance(g, dict) else g
            story.append(Paragraph(f"• {msg}", st["body"]))

    # Provenance / disclaimer
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Replacement values are sourced from the USACE National Structure Inventory (NSI). "
        "Where NSI matches no structure at the location, the dollar estimate is reported as "
        "N/A rather than valued against a default. This assessment is for screening and does "
        "not replace a site-specific engineering or insurance appraisal.", st["small"]))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=LETTER,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.85 * inch, bottomMargin=0.75 * inch,
        title="Heavi — Property Hazard Assessment", author="Heavi",
    )
    doc.build(story, onFirstPage=_chrome, onLaterPages=_chrome)
    return buf.getvalue()
