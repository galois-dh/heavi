"""Regulatory-filing methodology PDF for the wildfire risk module.

Same ReportLab/Platypus pipeline as portfolio_pdf.py (no system deps). Renders a
7-section "Regulatory Filing Support Document" from the published wildfire
vulnerability model artifact (app/wildfire_model_params.json — coefficients,
standard errors, p-values, decile calibration, training cohort). Every page
footer carries the methodology hash, document version, and generation date.
"""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

NAVY = colors.HexColor("#0a2540")
ACCENT = colors.HexColor("#0e6fff")
INK = colors.HexColor("#1f2937")
MUTED = colors.HexColor("#6b7280")
RULE = colors.HexColor("#d1d5db")
LIGHT = colors.HexColor("#f3f4f6")

DOC_VERSION = "1.0"


# ─── Model artifact ──────────────────────────────────────────────────────────


def _load_params() -> dict[str, Any]:
    here = Path(__file__).resolve().parent
    for p in (here / "wildfire_model_params.json", here / "wildfire_vulnerability_model.json"):
        if p.exists():
            return json.loads(p.read_text())
    raise RuntimeError("regulator_pdf: wildfire model params not found")


# Predictor → regulator-facing definition.
FEATURE_DEFS = [
    ("wildfire_likelihood", "burn_probability",
     "Annual probability the location burns, from USFS Wildfire Risk to Communities "
     "(FSim simulation)."),
    ("distance_to_fuel", "distance_to_fuel_m",
     "Distance in metres from the structure to the nearest burnable LANDFIRE fuel cell."),
    ("canopy_cover_100m", "canopy_cover_100m",
     "Mean percent tree-canopy cover within a 100 m radius (LANDFIRE)."),
    ("slope_degrees", "slope_degrees",
     "Terrain slope in degrees at the structure (USGS 3DEP elevation)."),
    ("is_residential", "is_res1",
     "1 if the structure is single-family residential (USACE NSI RES1), else 0."),
]

CITATIONS = [
    "Finney, M.A., et al. (2011). A method for ensemble wildland fire simulation. "
    "Environmental Modeling & Assessment, 16(2): 153-167. — FSim wildfire hazard simulation.",
    "Syphard, A.D., et al. (2012). Housing arrangement and location determine the "
    "likelihood of housing loss due to wildfire. PLoS ONE, 7(3): e33954. — housing "
    "arrangement and wildfire damage.",
    "Kramer, H.A., et al. (2018). Where wildfires destroy buildings in the US "
    "relative to the wildland-urban interface and national fire outreach programs. "
    "International Journal of Wildland Fire, 27(5): 329-341. — WUI damage patterns.",
    "Klugman, S.A., Panjer, H.H., & Willmot, G.E. (2019). Loss Models: From Data to "
    "Decisions (5th ed.). Wiley. — frequency-severity loss modeling framework.",
    "Rollins, M.G. (2009). LANDFIRE: a nationally consistent vegetation, wildland "
    "fire, and fuel assessment. International Journal of Wildland Fire, 18(3): "
    "235-249. — LANDFIRE vegetation/fuel data.",
]

DATA_SOURCES = [
    ["USFS Wildfire Risk to Communities (WRC)", "USDA Forest Service", "2020 (FSim)",
     "270 m", "wildfirerisk.org"],
    ["LANDFIRE (fuels, canopy)", "USGS / USFS", "LF 2022", "30 m", "landfire.gov"],
    ["3DEP elevation (slope)", "USGS", "current", "10 m", "elevation.nationalmap.gov"],
    ["National Structure Inventory (NSI)", "USACE", "2022", "structure point",
     "nsi.sec.usace.army.mil"],
    ["Damage Inspection (DINS)", "CAL FIRE", "2017-2020", "structure point",
     "data.ca.gov (CAL FIRE DINS)"],
    ["Fire perimeters (FRAP)", "CAL FIRE", "2017-2020", "perimeter polygon",
     "frap.fire.ca.gov"],
]

LIMITATIONS = [
    ("Geographic & temporal scope", "Medium",
     "Calibrated on Sonoma County fires (2017-2020). Transfer to other regions or "
     "fire regimes is not yet independently validated.",
     "Expand the training cohort across additional counties and fire regimes."),
    ("Binary damage outcome", "Medium",
     "The model predicts Destroyed (>50%) vs. No Damage; partial-damage classes are "
     "excluded, so it does not estimate graded damage severity.",
     "Move to an ordinal/multi-class severity model."),
    ("Structure-hardening features absent", "High",
     "Roof material, vents, and defensible space — known drivers of structure loss — "
     "are not in the feature set (no national structured source).",
     "Ingest parcel/permit or customer-supplied hardening attributes."),
    ("Hazard resolution", "Medium",
     "Burn probability derives from 270 m FSim; sub-parcel hazard variation is not "
     "resolved.",
     "Adopt higher-resolution burn-probability and structure-level fuel layers."),
    ("Exposure values are modeled", "Low-Medium",
     "Replacement values come from the USACE NSI (modeled), not appraisals.",
     "Use customer-provided or appraised replacement values when available."),
    ("Training class balance", "Medium",
     "The damage-inspection cohort is 82% destroyed — a sampling artifact of "
     "post-fire inspections, not a population base rate.",
     "Reweight to population priors for absolute-probability calibration."),
]


# ─── Styles & chrome ─────────────────────────────────────────────────────────


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=base["Title"], fontName="Helvetica-Bold",
                                fontSize=20, leading=25, textColor=NAVY, spaceAfter=10),
        "subtitle": ParagraphStyle("subtitle", parent=base["Normal"], fontName="Helvetica",
                                   fontSize=12, leading=16, textColor=MUTED),
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontName="Helvetica-Bold",
                             fontSize=15, leading=19, textColor=NAVY, spaceBefore=4, spaceAfter=8),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName="Helvetica-Bold",
                             fontSize=11, leading=14, textColor=ACCENT, spaceBefore=10,
                             spaceAfter=4),
        "body": ParagraphStyle("body", parent=base["Normal"], fontName="Helvetica",
                              fontSize=9.5, leading=14, textColor=INK, spaceAfter=7),
        "small": ParagraphStyle("small", parent=base["Normal"], fontName="Helvetica",
                               fontSize=8, leading=11, textColor=MUTED),
        "cell": ParagraphStyle("cell", parent=base["Normal"], fontName="Helvetica",
                              fontSize=8, leading=10.5, textColor=INK),
        "cellb": ParagraphStyle("cellb", parent=base["Normal"], fontName="Helvetica-Bold",
                               fontSize=8, leading=10.5, textColor=NAVY),
    }


_HASH = ""


def _chrome(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(NAVY)
    canvas.setLineWidth(1.5)
    canvas.line(0.75 * inch, 10.45 * inch, 7.75 * inch, 10.45 * inch)
    canvas.setFillColor(NAVY)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(0.75 * inch, 10.55 * inch, "HEAVI")
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(7.75 * inch, 10.55 * inch,
                           "Wildfire Methodology — Regulatory Filing")
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.4)
    canvas.line(0.75 * inch, 0.6 * inch, 7.75 * inch, 0.6 * inch)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7)
    gen = datetime.now(UTC).strftime("%Y-%m-%d")
    canvas.drawString(
        0.75 * inch, 0.42 * inch,
        f"Methodology hash {_HASH[:16]}…  ·  Document v{DOC_VERSION}  ·  Generated {gen}",
    )
    canvas.drawRightString(7.75 * inch, 0.42 * inch, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


def _table(data, col_widths, header=True):
    t = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, NAVY),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        style += [("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
                  ("TEXTCOLOR", (0, 0), (-1, 0), NAVY)]
    t.setStyle(TableStyle(style))
    return t


# ─── Document ────────────────────────────────────────────────────────────────


def render_methodology_filing() -> bytes:
    global _HASH
    p = _load_params()
    _HASH = p.get("methodology_hash", "")
    s = _styles()
    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf, pagesize=LETTER,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.95 * inch, bottomMargin=0.75 * inch,
    )
    frame = Frame(0.75 * inch, 0.75 * inch, 7.0 * inch, 9.45 * inch, id="main")
    doc.addPageTemplates([PageTemplate(id="all", frames=[frame], onPage=_chrome)])

    el: list[Any] = []
    gen = datetime.now(UTC).strftime("%B %d, %Y")

    # ── Page 1 — Cover ──
    el += [
        Spacer(1, 1.6 * inch),
        Paragraph("Wildfire Risk Assessment Methodology", s["title"]),
        Paragraph("Regulatory Filing Support Document", s["subtitle"]),
        Spacer(1, 0.4 * inch),
        HRFlowable(width="100%", thickness=1, color=NAVY),
        Spacer(1, 0.3 * inch),
        Paragraph("Prepared by Heavi (Heaviside Intelligence, Inc.)", s["body"]),
        Paragraph(f"Date: {gen}", s["body"]),
        Paragraph(f"Document version: {DOC_VERSION}", s["body"]),
        Paragraph(f"Methodology hash: {_HASH}", s["small"]),
        Paragraph(f"Model run ID: {p.get('run_id', 'n/a')}", s["small"]),
        Spacer(1, 0.5 * inch),
        Paragraph(
            "CONFIDENTIALITY NOTICE. This document is provided to support regulatory "
            "review of Heavi's wildfire risk assessment methodology. It contains "
            "proprietary model specifications and is shared in confidence; it is not "
            "for redistribution without the written consent of Heaviside Intelligence, Inc.",
            s["small"],
        ),
        PageBreak(),
    ]

    # ── Page 2 — Methodology Summary ──
    el += [
        Paragraph("1. Methodology Summary", s["h1"]),
        Paragraph(
            "The Heavi wildfire risk assessment module produces property-level annual "
            "risk estimates by combining published federal wildfire hazard data with a "
            "vulnerability model calibrated against historical damage inspections. For a "
            "given property, Heavi looks up how likely the surrounding landscape is to "
            "burn in a given year, how exposed the specific structure is (its distance to "
            "burnable vegetation, the tree cover around it, the steepness of the terrain, "
            "and whether it is a home), and the cost to rebuild it.",
            s["body"],
        ),
        Paragraph(
            "These inputs feed a statistical model that estimates the chance a structure "
            "would be destroyed if a fire reaches it. That conditional damage probability "
            "is multiplied by the annual likelihood of a fire and by the structure's "
            "replacement value to yield an estimated annual risk in dollars. The model "
            "was fitted on thousands of post-fire damage inspections from recent Northern "
            "California wildfires, so its predictions are anchored to what actually "
            "happened to real buildings.",
            s["body"],
        ),
        Paragraph(
            "Every input layer is a public federal or state dataset, and every assessment "
            "is reproducible: the same property scored twice returns the same result, and "
            "each run is stamped with a methodology hash that identifies the exact model "
            "version used. The sections that follow document the data sources, the model "
            "specification, the calibration and validation evidence, the known "
            "limitations, and the data-governance controls.",
            s["body"],
        ),
        PageBreak(),
    ]

    # ── Page 3 — Academic and Data Sources ──
    el += [Paragraph("2. Academic and Data Sources", s["h1"]),
           Paragraph("Academic references", s["h2"])]
    for c in CITATIONS:
        el.append(Paragraph("• " + c, s["body"]))
    el += [
        Paragraph("Federal and state data sources", s["h2"]),
        _table(
            [["Dataset", "Provider", "Vintage", "Resolution", "Public access"]]
            + [[Paragraph(r[0], s["cell"]), Paragraph(r[1], s["cell"]),
                Paragraph(r[2], s["cell"]), Paragraph(r[3], s["cell"]),
                Paragraph(r[4], s["cell"])] for r in DATA_SOURCES],
            [1.7 * inch, 1.4 * inch, 0.9 * inch, 1.0 * inch, 2.0 * inch],
        ),
        PageBreak(),
    ]

    # ── Page 4 — Model Specification ──
    coef, se = p["coefficients"], p.get("std_errors", {})
    zv, pv = p.get("z_values", {}), p.get("p_values", {})

    def fmt_p(x):
        return "< 0.001" if x is not None and x < 0.001 else (f"{x:.3g}" if x is not None else "—")

    coef_rows = [["Term", "Coefficient", "Std. error", "z", "p-value"]]
    coef_rows.append([Paragraph("Intercept (const)", s["cellb"]),
                      Paragraph(f"{coef['const']:.4f}", s["cell"]),
                      Paragraph(f"{se.get('const', 0):.4f}", s["cell"]),
                      Paragraph(f"{zv.get('const', 0):.2f}", s["cell"]),
                      Paragraph(fmt_p(pv.get('const')), s["cell"])])
    for label, key, _ in FEATURE_DEFS:
        coef_rows.append([Paragraph(label, s["cell"]),
                          Paragraph(f"{coef[key]:.4f}", s["cell"]),
                          Paragraph(f"{se.get(key, 0):.4f}", s["cell"]),
                          Paragraph(f"{zv.get(key, 0):.2f}", s["cell"]),
                          Paragraph(fmt_p(pv.get(key)), s["cell"])])

    el += [
        Paragraph("3. Model Specification", s["h1"]),
        Paragraph("Feature definitions", s["h2"]),
        _table(
            [["Feature", "Definition"]]
            + [[Paragraph(label, s["cellb"]), Paragraph(desc, s["cell"])]
               for label, _key, desc in FEATURE_DEFS],
            [1.6 * inch, 5.4 * inch],
        ),
        Paragraph("Fitted coefficients", s["h2"]),
        Paragraph(
            "Binary logistic regression (logit link). Outcome: P(structure destroyed | "
            f"fire reaches it). Fitted on n = {p.get('n_train', 0):,} structures; "
            f"McFadden pseudo-R² = {p.get('pseudo_r2', 0):.3f}.",
            s["body"],
        ),
        _table(coef_rows,
               [1.9 * inch, 1.3 * inch, 1.3 * inch, 1.0 * inch, 1.5 * inch]),
        Paragraph("Link function and risk formula", s["h2"]),
        Paragraph(
            "P(damage | x) = 1 / (1 + exp(−(β₀ + Σ βᵢ·xᵢ))), the standard logistic "
            "(logit) link.",
            s["body"],
        ),
        Paragraph(
            "annual_risk = wildfire_likelihood × P(damage | features) × replacement_value",
            s["cellb"],
        ),
        Paragraph(
            "where wildfire_likelihood is the annual burn probability and "
            "replacement_value is the structure's reconstruction cost (USACE NSI).",
            s["small"],
        ),
        PageBreak(),
    ]

    # ── Page 5 — Calibration and Validation Evidence ──
    cohort = p.get("training_cohort", [])
    cohort_rows = [["Fire", "Year", "Inspected structures", "Destroyed", "Damage rate"]]
    for c in cohort:
        cohort_rows.append([
            Paragraph(c["fire"], s["cell"]), Paragraph(str(c["year"]), s["cell"]),
            Paragraph(f"{c['records']:,}", s["cell"]), Paragraph(f"{c['destroyed']:,}", s["cell"]),
            Paragraph(f"{c['damage_rate'] * 100:.1f}%", s["cell"]),
        ])

    dec_rows = [["Decile", "n", "Pred. range", "Mean predicted", "Observed", "Residual"]]
    for d in p.get("decile_calibration", []):
        resid = d["obs_mean"] - d["pred_mean"]
        dec_rows.append([
            Paragraph(str(d["decile"]), s["cell"]), Paragraph(str(d["n"]), s["cell"]),
            Paragraph(f"{d['pred_min']:.2f}–{d['pred_max']:.2f}", s["cell"]),
            Paragraph(f"{d['pred_mean']:.3f}", s["cell"]),
            Paragraph(f"{d['obs_mean']:.3f}", s["cell"]),
            Paragraph(f"{resid:+.3f}", s["cell"]),
        ])

    el += [
        Paragraph("4. Calibration and Validation Evidence", s["h1"]),
        Paragraph(
            "Training/validation split: structures are split 80/20, stratified by fire "
            "event (random seed 42), so each fire is represented in both train and "
            f"validation. Training n = {p.get('n_train', 0):,}; validation n = "
            f"{p.get('n_val', 0):,}.",
            s["body"],
        ),
        Paragraph("Training cohort composition", s["h2"]),
        _table(cohort_rows, [2.0 * inch, 0.8 * inch, 1.8 * inch, 1.2 * inch, 1.2 * inch]),
        Paragraph(
            "Cohort fires: Tubbs, Nuns, Kincade, Glass, and LNU Lightning Complex "
            "(2017-2020). Damage rates reflect the post-fire inspection sample, not "
            "the general building population.",
            s["small"],
        ),
        Paragraph("Discrimination", s["h2"]),
        Paragraph(
            f"AUC-ROC = {p.get('auc_roc', 0):.2f}    ·    Gini = {p.get('gini', 0):.2f}    "
            f"·    optimal classification threshold = {p.get('optimal_threshold', 0):.3f}",
            s["body"],
        ),
        Paragraph("Calibration by predicted-probability decile (held-out validation set)", s["h2"]),
        _table(dec_rows,
               [0.7 * inch, 0.6 * inch, 1.4 * inch, 1.4 * inch, 1.2 * inch, 1.2 * inch]),
        Paragraph(
            "A well-calibrated model shows small residuals (observed − predicted) across "
            "all deciles. Held-out evidence is the 20% validation set above; each cohort "
            "fire also appears in validation, so performance is measured on structures "
            "the model did not train on.",
            s["small"],
        ),
        PageBreak(),
    ]

    # ── Page 6 — Known Limitations ──
    lim_rows = [["Limitation", "Severity", "Description", "Enhancement path"]]
    for name, sev, desc, enh in LIMITATIONS:
        lim_rows.append([
            Paragraph(name, s["cellb"]), Paragraph(sev, s["cell"]),
            Paragraph(desc, s["cell"]), Paragraph(enh, s["cell"]),
        ])
    el += [
        Paragraph("5. Known Limitations", s["h1"]),
        Paragraph(
            "The following limitations are disclosed for regulatory transparency. Each is "
            "rated by severity and paired with a planned enhancement path.",
            s["body"],
        ),
        _table(lim_rows, [1.4 * inch, 0.8 * inch, 2.6 * inch, 2.2 * inch]),
        PageBreak(),
    ]

    # ── Page 7 — Data Governance ──
    el += [
        Paragraph("6. Data Governance", s["h1"]),
        Paragraph("Customer-data-native architecture", s["h2"]),
        Paragraph(
            "The customer provides the properties to be assessed; Heavi enriches each "
            "against public federal and state data and returns the scored result. Heavi "
            "does not require or retain the customer's policy or portfolio data beyond "
            "the assessment.",
            s["body"],
        ),
        Paragraph("Non-public personal information (NPPI)", s["h2"]),
        Paragraph(
            "No NPPI is stored beyond the assessment session. Inputs are limited to "
            "location (address or coordinates) and, optionally, a replacement value; the "
            "module does not ingest policyholder identity or claims detail.",
            s["body"],
        ),
        Paragraph("Audit trail and reproducibility", s["h2"]),
        Paragraph(
            "Every model execution is logged with a methodology hash that uniquely "
            f"identifies the model version (current: {_HASH[:24]}…) and a run identifier. "
            "Re-scoring the same property with the same model version returns an identical "
            "result, and the methodology hash on this document ties the filing to the "
            "exact deployed model.",
            s["body"],
        ),
        Paragraph("Data flow", s["h2"]),
        _table(
            [["Step", "Description"]]
            + [[Paragraph(a, s["cellb"]), Paragraph(b, s["cell"])] for a, b in [
                ("1. Customer input", "Property address or coordinates (± replacement value)."),
                ("2. Geocoding", "Address resolved to coordinates."),
                ("3. Federal data enrichment",
                 "Burn probability, fuel distance, canopy, slope, occupancy, NSI value."),
                ("4. Scoring", "Logistic vulnerability model → annual risk estimate."),
                ("5. Documented output",
                 "Result returned with methodology hash; execution logged."),
            ]],
            [1.7 * inch, 5.3 * inch],
        ),
    ]

    doc.build(el)
    return buf.getvalue()
