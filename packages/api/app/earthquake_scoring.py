"""National earthquake-risk scoring — federal hazard/exposure data queried on-demand.

Mirrors the flood module pattern: nothing pre-loaded except HAZUS earthquake
fragility curves (encoded inline below). For any US point we query, at request time:
  - USGS ASCE 7-22 Design Maps  (bedrock PGA at MCEr level)        REST/JSON
  - USGS 3DEP                   (elevation samples → slope → VS30)  ArcGIS
  - USACE NSI                   (nearest structure: occupancy, values)
then apply Wald & Allen (2007) slope-based VS30 → NEHRP site class →
HAZUS-style site amplification, compute damage-state probabilities from
lognormal fragility curves, and estimate annual risk.

Risk tiers match the flood/wildfire modules: HIGH > $500/yr, MODERATE $50-500, LOW < $50.
"""

from __future__ import annotations

import math
from typing import Any

import httpx

# ─── Federal services ──────────────────────────────────────────────────────
ASCE_DESIGN_URL = "https://earthquake.usgs.gov/ws/designmaps/asce7-22.json"
NSI_URL = "https://nsi.sec.usace.army.mil/nsiapi/structures"
DEM_GETSAMPLES_URL = (
    "https://elevation.nationalmap.gov/arcgis/rest/services/"
    "3DEPElevation/ImageServer/getSamples"
)
UA = "Mozilla/5.0 Heavi/0.1 (earthquake-risk)"

# Hazard level returned by ASCE 7-22 PGAm: 2% probability of exceedance in 50
# years (the MCEr / risk-targeted design basis). This corresponds to an
# approximate 2475-year return period and is what current US building codes use.
ANNUAL_PROB_AT_HAZARD_LEVEL = 1.0 / 2475.0
RETURN_PERIOD_YEARS = 2475

# Default first-floor and basement assumptions are not needed for shaking risk
# (PGA acts on the whole structure regardless of FFH), unlike flood.

# HAZUS structural damage ratios — Table 15.3, HAZUS 5.1 Earthquake Technical
# Manual (percentage of replacement value, by damage state). These are the
# RES1/COM-default values; HAZUS varies these slightly by occupancy but the
# differences are second-order vs. fragility-curve uncertainty.
DAMAGE_RATIOS = {
    "slight": 0.02,
    "moderate": 0.10,
    "extensive": 0.50,
    "complete": 1.00,
}

# NEHRP site class boundaries (VS30 in m/s) per ASCE 7-22 / NEHRP 2020.
# Wald & Allen's slope-VS30 proxy doesn't resolve Class A (very hard rock), so
# the practical floor is Class B.
SITE_CLASSES = [
    ("A", 1500.0, math.inf, 0.8, "hard rock"),
    ("B", 760.0, 1500.0, 1.0, "rock"),
    ("C", 360.0, 760.0, 1.2, "very dense soil / soft rock"),
    ("D", 180.0, 360.0, 1.6, "stiff soil"),
    ("E", 0.0, 180.0, 2.5, "soft clay / fill"),
]


# Wald & Allen (2007), "Topographic Slope as a Proxy for Seismic Site
# Conditions", BSSA 97(5): Table 2 — active tectonic regime (covers most of
# the conterminous US that matters seismically). Slope is the local topographic
# gradient (m/m); VS30 is the inferred shear-wave velocity (m/s).
WALD_ALLEN_ACTIVE = [
    # (slope_max_m_per_m, vs30_m_per_s)
    (0.0005,   180.0),
    (0.0014,   240.0),
    (0.0028,   300.0),
    (0.0044,   360.0),
    (0.0078,   400.0),
    (0.0136,   490.0),
    (0.0250,   620.0),
    (0.0480,   760.0),
    (math.inf, 900.0),
]


METHODOLOGY_NOTE = (
    "Earthquake risk estimated from USGS ASCE 7-22 Design Maps (bedrock PGA at "
    "the MCEr / 2% in 50 yr hazard level), a Wald & Allen (2007) slope-based "
    "VS30 site amplification, USACE National Structure Inventory exposure, and "
    "HAZUS Earthquake Model lognormal fragility curves. See the methodology "
    "endpoint for full data lineage, citations, and known limitations."
)


# ─── HAZUS Earthquake Fragility Curves ──────────────────────────────────────
# Lognormal medians (g) and dispersion β for the four HAZUS damage states,
# indexed by [building_type][code_level]. Values follow HAZUS 5.1 Earthquake
# Technical Manual Tables 5.9a/c (PGA-based / short-period fragility) for the
# most common occupancy + structural-system combinations.
#
# building_type:
#   W1   – wood, light frame, 1-2 stories (US single-family residential)
#   W2   – wood, commercial/industrial, multistory
#   S1L  – steel moment frame, low-rise
#   C1L  – concrete moment frame, low-rise
#   RM1L – reinforced masonry bearing walls with wood/light-steel diaphragms
#   URML – unreinforced masonry bearing walls, low-rise (highest vulnerability)
#   MH   – manufactured housing (mobile homes)
#
# code_level: pre_code (pre-1940), low (1941-1973), moderate (1974-1996),
#   high (1997+ post-Northridge). Defaults match HAZUS regional convention.

# Each inner dict has medians (g) for slight/moderate/extensive/complete plus
# the lognormal dispersion β. β is held constant per HAZUS (0.64 for short-period
# PGA-based fragility) across types and code levels.
_B = 0.64


def _row(s: float, m: float, e: float, c: float) -> dict[str, float]:
    return {"slight": s, "moderate": m, "extensive": e, "complete": c, "beta": _B}


FRAGILITY: dict[str, dict[str, dict[str, float]]] = {
    "W1": {
        "pre_code": _row(0.18, 0.29, 0.51, 0.77),
        "low":      _row(0.20, 0.34, 0.62, 1.03),
        "moderate": _row(0.24, 0.43, 0.91, 1.80),
        "high":     _row(0.26, 0.55, 1.28, 2.50),
    },
    "W2": {
        "pre_code": _row(0.14, 0.22, 0.40, 0.70),
        "low":      _row(0.16, 0.28, 0.55, 1.00),
        "moderate": _row(0.20, 0.38, 0.80, 1.55),
        "high":     _row(0.24, 0.50, 1.10, 2.10),
    },
    "S1L": {
        "pre_code": _row(0.10, 0.15, 0.28, 0.55),
        "low":      _row(0.12, 0.19, 0.35, 0.70),
        "moderate": _row(0.15, 0.25, 0.49, 1.05),
        "high":     _row(0.18, 0.32, 0.66, 1.55),
    },
    "C1L": {
        "pre_code": _row(0.10, 0.14, 0.24, 0.43),
        "low":      _row(0.12, 0.18, 0.34, 0.65),
        "moderate": _row(0.15, 0.24, 0.49, 1.05),
        "high":     _row(0.18, 0.31, 0.65, 1.55),
    },
    "RM1L": {
        "pre_code": _row(0.13, 0.19, 0.34, 0.62),
        "low":      _row(0.15, 0.24, 0.45, 0.85),
        "moderate": _row(0.19, 0.32, 0.66, 1.40),
        "high":     _row(0.22, 0.41, 0.88, 2.10),
    },
    "URML": {
        # Unreinforced masonry has no "high-code" rating — modern code prohibits
        # bearing URM; HAZUS holds curves flat at "moderate".
        "pre_code": _row(0.13, 0.17, 0.26, 0.37),
        "low":      _row(0.14, 0.20, 0.32, 0.46),
        "moderate": _row(0.18, 0.27, 0.46, 0.71),
        "high":     _row(0.18, 0.27, 0.46, 0.71),
    },
    "MH": {
        # Manufactured housing — high lateral vulnerability (no foundation
        # bracing in pre-1976 HUD-code units).
        "pre_code": _row(0.11, 0.18, 0.31, 0.60),
        "low":      _row(0.13, 0.22, 0.40, 0.80),
        "moderate": _row(0.13, 0.22, 0.40, 0.80),
        "high":     _row(0.13, 0.22, 0.40, 0.80),
    },
}

# Building-type metadata for the summary text.
BUILDING_DESCRIPTIONS = {
    "W1":   "wood light frame (typical residential)",
    "W2":   "wood commercial/industrial",
    "S1L":  "low-rise steel moment frame",
    "C1L":  "low-rise concrete moment frame",
    "RM1L": "low-rise reinforced masonry",
    "URML": "unreinforced masonry (highly vulnerable)",
    "MH":   "manufactured housing",
}


# ─── Standard normal CDF (no scipy dependency) ──────────────────────────────


def _phi(x: float) -> float:
    """Standard normal CDF Φ(x) via the error function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


# ─── Federal API queries ────────────────────────────────────────────────────


async def query_bedrock_pga(client: httpx.AsyncClient, lat: float, lng: float) -> float | None:
    """USGS ASCE 7-22 design-maps PGAm at the point, on reference bedrock
    (siteClass=B), in units of g. This is the 2% in 50-yr MCEr PGA."""
    try:
        r = await client.get(
            ASCE_DESIGN_URL,
            params={
                "latitude": lat,
                "longitude": lng,
                "siteClass": "B",
                "riskCategory": "II",
                "title": "Heavi earthquake assessment",
            },
            headers={"User-Agent": UA},
        )
        data = r.json()
    except (httpx.HTTPError, ValueError):
        return None
    try:
        val = data["response"]["data"]["pgam"]
        return float(val) if val is not None else None
    except (KeyError, TypeError, ValueError):
        return None


async def query_3dep_elev_m(
    client: httpx.AsyncClient, lng: float, lat: float
) -> float | None:
    """USGS 3DEP elevation at the point, in metres (the service's native unit)."""
    import json as _json

    geometry = {"points": [[lng, lat]], "spatialReference": {"wkid": 4326}}
    try:
        r = await client.get(
            DEM_GETSAMPLES_URL,
            params={
                "geometry": _json.dumps(geometry),
                "geometryType": "esriGeometryMultipoint",
                "returnFirstValueOnly": "true",
                "f": "json",
            },
        )
        data = r.json()
    except (httpx.HTTPError, ValueError):
        return None
    samples = data.get("samples") or []
    if not samples:
        return None
    try:
        return float(samples[0]["value"])
    except (KeyError, TypeError, ValueError):
        return None


async def estimate_slope(client: httpx.AsyncClient, lat: float, lng: float) -> float | None:
    """Local topographic slope (m/m) estimated by finite-difference of 3DEP
    elevations sampled ~30 m east/west/north/south of the point. Returns the
    gradient magnitude. Falls back to None if any sample is missing."""
    # 0.00027° ≈ 30 m near 37°N; cos(lat) compensates for E-W convergence.
    dlat = 0.00027
    dlng = 0.00027 / max(math.cos(math.radians(lat)), 0.1)
    coords = [
        (lng + dlng, lat),  # east
        (lng - dlng, lat),  # west
        (lng,        lat + dlat),  # north
        (lng,        lat - dlat),  # south
    ]
    elevations: list[float | None] = []
    for (x, y) in coords:
        elevations.append(await query_3dep_elev_m(client, x, y))
    if any(e is None for e in elevations):
        return None
    e_e, e_w, e_n, e_s = elevations  # type: ignore[misc]
    # Central differences over the 60-m E-W and N-S spans.
    dz_dx = (e_e - e_w) / 60.0  # type: ignore[operator]
    dz_dy = (e_n - e_s) / 60.0  # type: ignore[operator]
    return math.hypot(dz_dx, dz_dy)


async def query_nsi(
    client: httpx.AsyncClient, lng: float, lat: float
) -> dict[str, Any] | None:
    """Nearest USACE NSI structure to the point (POST a small polygon — the
    documented alternative since the bbox GET 500s server-side)."""
    d = 0.005
    poly = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [lng - d, lat - d],
                            [lng + d, lat - d],
                            [lng + d, lat + d],
                            [lng - d, lat + d],
                            [lng - d, lat - d],
                        ]
                    ],
                },
            }
        ],
    }
    try:
        r = await client.post(
            NSI_URL,
            params={"fmt": "fc"},
            json=poly,
            headers={"User-Agent": UA, "Content-Type": "application/json"},
        )
        data = r.json()
    except (httpx.HTTPError, ValueError):
        return None
    feats = data.get("features") if isinstance(data, dict) else None
    if not feats:
        return None
    best = None
    best_d2 = float("inf")
    for f in feats:
        coords = (f.get("geometry") or {}).get("coordinates")
        if not coords or len(coords) < 2:
            continue
        sx, sy = float(coords[0]), float(coords[1])
        d2 = (sx - lng) ** 2 + (sy - lat) ** 2
        if d2 < best_d2:
            best_d2 = d2
            best = f
    if best is None:
        return None
    p = best.get("properties", {})
    coords = best["geometry"]["coordinates"]
    return {
        "occtype": p.get("occtype"),
        "bldgtype": p.get("bldgtype"),
        "num_story": p.get("num_story"),
        "med_yr_blt": p.get("med_yr_blt"),
        "val_struct": p.get("val_struct"),
        "val_cont": p.get("val_cont"),
        "longitude": float(coords[0]),
        "latitude": float(coords[1]),
        "distance_m": math.sqrt(best_d2) * 111_320.0,
    }


# ─── VS30 / site amplification / building-type mapping ──────────────────────


def slope_to_vs30(slope_m_per_m: float) -> float:
    """Wald & Allen (2007) slope-based VS30 proxy, active tectonic regime."""
    s = abs(slope_m_per_m)
    for s_max, vs in WALD_ALLEN_ACTIVE:
        if s <= s_max:
            return vs
    return WALD_ALLEN_ACTIVE[-1][1]


def vs30_to_site_class(vs30: float) -> tuple[str, float, str]:
    """Returns (NEHRP class letter, F_PGA amplification factor, description)."""
    for letter, lo, hi, amp, desc in SITE_CLASSES:
        if lo <= vs30 < hi:
            return letter, amp, desc
    # vs30 == inf or unbounded — fall back to class A
    return "A", 0.8, "hard rock"


def map_building_type(occtype: str | None, bldgtype: str | None, num_story: Any) -> str:
    """Map NSI (occtype, bldgtype, num_story) → HAZUS earthquake building type.

    NSI bldgtype codes: W=wood, S=steel, C=concrete, M=masonry, MH=manufactured.
    NSI occtype: RES1=single family, RES2=mobile home, RES3=multi-family,
    COM*=commercial, IND*=industrial.
    """
    occ = (occtype or "").upper()
    bt = (bldgtype or "").upper()
    try:
        stories = int(float(num_story)) if num_story is not None else 1
    except (TypeError, ValueError):
        stories = 1

    if occ.startswith("RES2") or bt == "MH":
        return "MH"
    if bt.startswith("M") and occ.startswith("RES"):
        return "URML"  # older unreinforced masonry residential
    if bt.startswith("M"):
        return "RM1L"  # default modern masonry → reinforced
    if bt.startswith("S"):
        return "S1L"
    if bt.startswith("C"):
        return "C1L"
    if occ.startswith("RES"):
        return "W1"
    # Commercial / industrial wood
    return "W2" if (bt.startswith("W") or stories <= 2) else "S1L"


def assume_code_level(med_yr_blt: Any) -> str:
    """Default HAZUS code level based on median year built (NSI med_yr_blt).
    Falls back to 'low' (a conservative default for an unknown vintage)."""
    try:
        yr = int(float(med_yr_blt))
    except (TypeError, ValueError):
        return "low"
    if yr >= 1997:
        return "high"      # post-Northridge / modern seismic provisions
    if yr >= 1974:
        return "moderate"  # post-1973 California Field Act era
    if yr >= 1941:
        return "low"
    return "pre_code"


# ─── Fragility evaluation ───────────────────────────────────────────────────


def damage_state_probabilities(
    building_type: str, code_level: str, pga_g: float
) -> dict[str, float]:
    """For each damage state ds, return P(D ≥ ds | PGA = pga_g) using the HAZUS
    lognormal fragility: P = Φ((ln(PGA) − ln(median_ds)) / β).
    """
    if pga_g <= 0:
        return {ds: 0.0 for ds in ("slight", "moderate", "extensive", "complete")}
    curve = FRAGILITY[building_type][code_level]
    beta = curve["beta"]
    ln_pga = math.log(pga_g)
    return {
        ds: _phi((ln_pga - math.log(curve[ds])) / beta)
        for ds in ("slight", "moderate", "extensive", "complete")
    }


def expected_damage_ratio(p_geq: dict[str, float]) -> tuple[dict[str, float], float]:
    """Convert cumulative-exceedance probabilities into exclusive damage-state
    probabilities (P[D = ds]) and return the expected structural damage ratio
    Σ P(D=ds) × damage_ratio(ds). Includes P(D = none) implicitly: the four
    probabilities below sum to 1 − P(D ≥ slight)."""
    p = {
        "slight":    p_geq["slight"]    - p_geq["moderate"],
        "moderate":  p_geq["moderate"]  - p_geq["extensive"],
        "extensive": p_geq["extensive"] - p_geq["complete"],
        "complete":  p_geq["complete"],
    }
    # Numerical guard — exceedance ordering can flip by ~1e-9 due to floating point.
    for k in p:
        if p[k] < 0:
            p[k] = 0.0
    ratio = sum(p[ds] * DAMAGE_RATIOS[ds] for ds in p)
    return p, ratio


# ─── Natural-language summary ────────────────────────────────────────────────


def _tier(annual_risk: float) -> str:
    return "HIGH" if annual_risk > 500 else "MODERATE" if annual_risk >= 50 else "LOW"


def _hazard_label(pga_bedrock_g: float) -> str:
    if pga_bedrock_g >= 0.40:
        return "high"
    if pga_bedrock_g >= 0.15:
        return "moderate"
    return "low"


def natural_language_summary(
    annual_risk: float,
    pga_bedrock_g: float,
    pga_adjusted_g: float,
    site_class: str,
    site_desc: str,
    vs30: float,
    amplification: float,
    building_type: str,
    code_level: str,
) -> str:
    tier = _tier(annual_risk)
    hazard = _hazard_label(pga_bedrock_g)
    btype = BUILDING_DESCRIPTIONS.get(building_type, building_type)
    return (
        f"This property has {tier} earthquake risk with an annual risk estimate "
        f"of ${round(annual_risk):,}. Located in a {hazard} seismic hazard zone "
        f"(bedrock PGA {pga_bedrock_g:.2f}g at the 2% in 50-yr MCEr level) on "
        f"site class {site_class} — {site_desc} (VS30 {round(vs30)} m/s, "
        f"amplification {amplification:.1f}× → adjusted PGA "
        f"{pga_adjusted_g:.2f}g). Structure modeled as {btype} ({code_level}-code). "
        f"Assessment uses USGS ASCE 7-22 Design Maps and HAZUS fragility curves."
    )


# ─── Pipeline ────────────────────────────────────────────────────────────────


async def assess_earthquake_risk(
    *,
    latitude: float,
    longitude: float,
    address: str | None = None,
    resolved_address: str | None = None,
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        pga_b = await query_bedrock_pga(client, latitude, longitude)
        slope = await estimate_slope(client, latitude, longitude)
        nsi = await query_nsi(client, longitude, latitude)

    if pga_b is None:
        raise ValueError(
            "USGS ASCE 7-22 Design Maps service did not return a PGA value for "
            "this location (the service covers the conterminous US and Alaska/"
            "Hawaii but excludes territories with no published design maps)."
        )

    # Site characterization (Wald & Allen). Falls back to Class C (representative
    # of most US developed land) if slope can't be resolved.
    if slope is not None:
        vs30 = slope_to_vs30(slope)
        slope_basis = "Wald & Allen (2007) slope-VS30 proxy from 3DEP elevation"
    else:
        vs30 = 490.0  # class C midpoint
        slope_basis = "default Class C (3DEP slope unavailable)"
    site_class, amp, site_desc = vs30_to_site_class(vs30)
    pga_adj = pga_b * amp

    # Structure mapping.
    if nsi:
        building_type = map_building_type(
            nsi.get("occtype"), nsi.get("bldgtype"), nsi.get("num_story")
        )
        code_level = assume_code_level(nsi.get("med_yr_blt"))
        val_struct = float(nsi.get("val_struct") or 0.0)
        val_cont = float(nsi.get("val_cont") or 0.0)
    else:
        building_type = "W1"  # national modal occupancy
        code_level = "low"
        val_struct = 0.0
        val_cont = 0.0

    # Fragility → damage state probabilities → expected damage ratio.
    p_geq = damage_state_probabilities(building_type, code_level, pga_adj)
    p_excl, damage_ratio = expected_damage_ratio(p_geq)

    # Loss = (structural + 50% × contents) × damage ratio. HAZUS treats
    # contents as more vulnerable than structure for some damage states but the
    # simplest defensible default is to weight contents by 0.5× the structural
    # ratio — matches the flood module's contents-vs-structure ordering.
    structural_loss = round(val_struct * damage_ratio, 2)
    contents_loss = round(val_cont * damage_ratio * 0.5, 2)
    total_loss = round(structural_loss + contents_loss, 2)
    annual_risk = round(total_loss * ANNUAL_PROB_AT_HAZARD_LEVEL, 2)

    summary = natural_language_summary(
        annual_risk=annual_risk,
        pga_bedrock_g=pga_b,
        pga_adjusted_g=pga_adj,
        site_class=site_class,
        site_desc=site_desc,
        vs30=vs30,
        amplification=amp,
        building_type=building_type,
        code_level=code_level,
    )

    return {
        "natural_language_summary": summary,
        "query": {
            "latitude": latitude,
            "longitude": longitude,
            "address": address,
            "resolved_address": resolved_address,
        },
        "hazard": {
            "bedrock_pga_g": round(pga_b, 3),
            "adjusted_pga_g": round(pga_adj, 3),
            "hazard_level": "2% probability of exceedance in 50 years (MCEr)",
            "return_period_years": RETURN_PERIOD_YEARS,
            "annual_exceedance_probability": ANNUAL_PROB_AT_HAZARD_LEVEL,
        },
        "site": {
            "vs30_m_per_s": round(vs30),
            "site_class": site_class,
            "site_description": site_desc,
            "amplification_factor": amp,
            "slope_m_per_m": round(slope, 4) if slope is not None else None,
            "slope_basis": slope_basis,
        },
        "structure": (
            {
                "match_distance_m": round(nsi["distance_m"], 1),
                "occupancy_type": nsi.get("occtype"),
                "nsi_building_type": nsi.get("bldgtype"),
                "hazus_building_type": building_type,
                "code_level": code_level,
                "num_stories": nsi.get("num_story"),
                "median_year_built": nsi.get("med_yr_blt"),
                "replacement_value_structure_usd": val_struct,
                "replacement_value_contents_usd": val_cont,
                "structure_location": {
                    "latitude": nsi["latitude"],
                    "longitude": nsi["longitude"],
                },
            }
            if nsi
            else None
        ),
        "damage_state_probabilities": {
            "exceedance": {ds: round(p_geq[ds], 4) for ds in p_geq},
            "exclusive":  {ds: round(p_excl[ds], 4) for ds in p_excl},
            "expected_damage_ratio": round(damage_ratio, 4),
        },
        "risk_estimate": {
            "annual_risk_estimate_usd": annual_risk,
            "risk_tier": _tier(annual_risk),
            "structural_loss_at_hazard_usd": structural_loss,
            "contents_loss_at_hazard_usd": contents_loss,
            "total_loss_at_hazard_usd": total_loss,
            "annual_exceedance_probability": ANNUAL_PROB_AT_HAZARD_LEVEL,
            "return_period_years": RETURN_PERIOD_YEARS,
        },
        "methodology_note": METHODOLOGY_NOTE,
    }


# ─── Methodology documentation ───────────────────────────────────────────────


def methodology_doc() -> dict[str, Any]:
    return {
        "summary": (
            "On-demand national earthquake-risk assessment combining USGS ASCE "
            "7-22 Design Maps (bedrock PGA at the MCEr / 2% in 50-yr hazard "
            "level), a Wald & Allen (2007) slope-based VS30 site amplification "
            "from USGS 3DEP elevation, USACE National Structure Inventory "
            "exposure, and HAZUS Earthquake Model lognormal fragility curves to "
            "estimate annual earthquake risk per property."
        ),
        "pipeline": [
            "Geocode (if address) → point",
            "USGS ASCE 7-22 Design Maps (siteClass=B): bedrock PGA at MCEr level",
            "USGS 3DEP: 4-point elevation sample → slope → Wald & Allen VS30",
            "VS30 → NEHRP site class → F_PGA amplification → adjusted PGA",
            "USACE NSI: nearest structure (occupancy, building type, vintage, values)",
            "NSI occupancy + bldgtype + vintage → HAZUS building type & code level",
            "Lognormal fragility → P(damage state) at adjusted PGA",
            "Expected damage ratio Σ P(ds)·dr(ds) → loss = value × ratio",
            "Annual risk = loss × annual exceedance probability (1/2475)",
        ],
        "data_sources": [
            {
                "name": "USGS ASCE 7-22 Design Maps Web Service",
                "use": "Bedrock PGA at 2% in 50-yr MCEr hazard level",
                "endpoint": ASCE_DESIGN_URL,
                "citation": (
                    "U.S. Geological Survey & American Society of Civil Engineers "
                    "(2022). ASCE 7-22 Seismic Design Maps. Built on the 2023 USGS "
                    "National Seismic Hazard Model for the conterminous United States."
                ),
            },
            {
                "name": "USGS 3DEP",
                "use": "Elevation for slope-based VS30 proxy",
                "endpoint": DEM_GETSAMPLES_URL,
            },
            {
                "name": "USACE National Structure Inventory (NSI)",
                "use": "Building exposure (occupancy, type, vintage, replacement value)",
                "endpoint": NSI_URL,
            },
            {
                "name": "HAZUS 5.1 Earthquake Model",
                "use": "Lognormal fragility curves and structural damage ratios",
                "citation": (
                    "Federal Emergency Management Agency (2024). Hazus Earthquake "
                    "Model Technical Manual, Version 5.1. Chapter 5 (building "
                    "fragility), Table 5.9 (PGA-based short-period medians); "
                    "Chapter 15 (damage ratios), Table 15.3."
                ),
            },
        ],
        "site_amplification": {
            "model": "Wald, D.J. and Allen, T.I. (2007). Topographic Slope as a "
            "Proxy for Seismic Site Conditions and Amplification. Bulletin of "
            "the Seismological Society of America, 97(5): 1379-1395.",
            "regime": "Active tectonic (BSSA 2007 Table 2).",
            "site_classes": [
                {"class": "A", "vs30": ">1500", "f_pga": 0.8, "description": "hard rock"},
                {"class": "B", "vs30": "760-1500", "f_pga": 1.0, "description": "rock"},
                {"class": "C", "vs30": "360-760", "f_pga": 1.2,
                 "description": "very dense soil / soft rock"},
                {"class": "D", "vs30": "180-360", "f_pga": 1.6, "description": "stiff soil"},
                {"class": "E", "vs30": "<180", "f_pga": 2.5, "description": "soft clay / fill"},
            ],
        },
        "fragility_curves": {
            "form": "Lognormal: P(D ≥ ds | PGA) = Φ((ln PGA − ln median_ds) / β).",
            "building_types": list(FRAGILITY.keys()),
            "code_levels": ["pre_code", "low", "moderate", "high"],
            "damage_states": list(DAMAGE_RATIOS.keys()),
            "damage_ratios_pct_of_value": {ds: f"{v*100:.0f}%" for ds, v in DAMAGE_RATIOS.items()},
        },
        "hazard_level": {
            "definition": "2% probability of exceedance in 50 years (MCEr).",
            "return_period_years": RETURN_PERIOD_YEARS,
            "annual_exceedance_probability": ANNUAL_PROB_AT_HAZARD_LEVEL,
            "rationale": (
                "Aligns with the ASCE 7-22 design basis returned directly by the "
                "USGS Design Maps service. Lower-RP estimates (e.g. 475-yr / 10% "
                "in 50-yr) can be approximated by scaling but introduce additional "
                "uncertainty; we report at the hazard level the source data is "
                "authored at and compute annual risk consistently."
            ),
        },
        "risk_tiers": {"HIGH": "> $500/yr", "MODERATE": "$50-500/yr", "LOW": "< $50/yr"},
        "code_level_defaults": {
            "pre_code": "Pre-1941 vintage (legacy construction, no seismic provisions)",
            "low":      "1941-1973 vintage (early seismic awareness, pre-Field Act)",
            "moderate": "1974-1996 vintage (post-Field Act, pre-Northridge)",
            "high":     "1997+ vintage (post-Northridge, modern UBC/IBC seismic provisions)",
            "fallback": "When NSI med_yr_blt is missing, defaults to 'low'.",
        },
        "known_limitations": [
            "Single-hazard-level point estimate, not a full hazard-curve integration "
            "(average annualized loss AAL). Properties dominated by frequent "
            "moderate shaking will be understated; rare-but-severe-dominated sites "
            "(e.g. parts of the Pacific Northwest) may be overstated.",
            "Wald & Allen slope-VS30 proxy is a topographic surrogate and cannot "
            "resolve engineered fill, liquefiable soils, or basin-edge amplification — "
            "all of which can drive site response well beyond the NEHRP class amplifier.",
            "Code-level assignment from NSI med_yr_blt is heuristic; pre-1976 HUD "
            "manufactured housing and unretrofitted URM stock dominate observed loss "
            "but are not always flagged in NSI bldgtype.",
            "Fragility curves are HAZUS-default short-period (PGA-based) values; "
            "long-period structures (high-rises, base-isolated buildings) require "
            "spectral-acceleration fragility not captured here.",
            "Treats PGA as the damage-driving demand parameter. Tsunami, "
            "liquefaction-induced ground failure, and surface-fault-rupture losses "
            "are out of scope.",
            "Validation against observed damage from specific events (e.g. 2014 "
            "Napa M6.0) is pending; reasonableness checks against the USGS hazard "
            "ordering are reported in the validation field below.",
        ],
        "validation": {
            "status": "reasonableness ordering verified",
            "method": (
                "Bedrock PGA values queried from the same source for San Francisco, "
                "Sacramento, and Dallas confirm the expected hazard ordering "
                "(SF > Sacramento > Dallas) and Memphis (New Madrid Seismic Zone) "
                "registers as comparably high to coastal California."
            ),
        },
    }
