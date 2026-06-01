"""Deepened solar site-feasibility module — stage-by-stage pipeline.

Each stage is an independent function that accepts a ``RequestContext`` (for
SQL/HTTP tracing + decision-trail event emission) and returns a structured
``Stage{N}Result`` dict downstream stages consume.

Stage inventory (per deep_module_specifications.md, see docs/):
  Stage 1  Solar Resource Assessment       (this file)
  Stage 2  Terrain Optimization            (TBD)
  Stage 3  Buildable Area Calculation      (TBD)
  Stage 4  Interconnection Analysis        (TBD)
  Stage 5  Geotechnical Screening          (TBD)
  Stage 6  LCOE Estimation                 (TBD)
  Stage 7  Environmental Constraint Screen (TBD)
  Stage 8  Composite Feasibility Score     (TBD)

Each stage is shipped independently with its own decision-trail instrumentation
+ verification. The existing solar_scoring.py (Doorga 2019 weighted overlay)
remains as the Discover-mode demo for Kern parcels until Stage 8 is in place.
"""

from __future__ import annotations

from typing import Any

from .decision_trail import RequestContext
from .integrations import pvwatts_v8

MODULE_NAME = "solar_site_feasibility_deep"
MODULE_VERSION = "0.1.0"


# ─── Stage 1 — Solar Resource Assessment ──────────────────────────────────


# Capacity density assumptions (acres per MW DC) for utility-scale PV.
# Source: NREL Land Use by System Technology (LBNL/NREL 2013, updated 2023).
ACRES_PER_MW = {
    0: 5.0,   # array_type 0 — fixed open rack
    1: 5.0,   # array_type 1 — fixed roof mount (treated same for utility scale)
    2: 7.5,   # 1-axis tracking
    3: 7.5,   # 1-axis backtracking
    4: 9.0,   # 2-axis tracking
}

ARRAY_TYPE_LABEL = {
    0: "Fixed open rack",
    1: "Fixed roof mount",
    2: "1-axis tracking",
    3: "1-axis backtracking",
    4: "2-axis tracking",
}

MODULE_TYPE_LABEL = {0: "Standard", 1: "Premium", 2: "Thin film"}

# Tilt rule of thumb for fixed-tilt utility solar: optimal annual energy yield
# in the northern hemisphere is roughly at latitude − 5°, capped at 35° to
# limit wind loading and snow shed for utility-scale racking.
TILT_LAT_OFFSET = 5.0
TILT_MAX = 35.0
TILT_MIN = 5.0


def _suggested_tilt(latitude: float, array_type: int) -> float:
    """Tracking arrays don't take a tilt parameter the same way — PVWatts
    accepts whatever is passed but tracking output is dominated by tracker
    geometry. For tracking we still pass an axis-tilt; default 0° (horizontal)."""
    if array_type in (2, 3):
        return 0.0
    if array_type == 4:
        return 0.0  # 2-axis: tilt is dynamic; the param is ignored
    # Fixed: latitude − 5°, clamped.
    t = max(TILT_MIN, min(TILT_MAX, abs(latitude) - TILT_LAT_OFFSET))
    return round(t, 1)


def _sizing_from_acreage(acreage_total: float, array_type: int) -> float:
    """Convert parcel acreage to system DC capacity (kW).
    Returns 0 if acreage is None/<=0 (downstream can supply explicit capacity)."""
    if not acreage_total or acreage_total <= 0:
        return 0.0
    apm = ACRES_PER_MW.get(array_type, 5.0)
    return round((acreage_total / apm) * 1000.0, 1)  # MW → kW


def _capacity_factor_interp(cf_pct: float) -> str:
    if cf_pct >= 23:
        return "excellent (top decile of US fixed-tilt sites)"
    if cf_pct >= 20:
        return "strong (typical SW US fixed-tilt)"
    if cf_pct >= 17:
        return "moderate"
    if cf_pct >= 14:
        return "weak"
    return "very weak (would not justify development)"


async def stage1_solar_resource(
    ctx: RequestContext,
    *,
    latitude: float,
    longitude: float,
    parcel_acreage: float | None = None,
    system_capacity_kw: float | None = None,
    tilt: float | None = None,
    azimuth: float = 180.0,
    array_type: int = 0,            # 0 = fixed open rack (utility-scale default)
    module_type: int = 0,           # 0 = standard crystalline-Si
    losses_pct: float = 14.08,      # NREL default
) -> dict[str, Any]:
    """Stage 1 — Solar Resource Assessment via NREL PVWatts v8.

    Either ``parcel_acreage`` or ``system_capacity_kw`` must be provided; if
    both are given, the explicit capacity wins. Tilt defaults to a clamped
    latitude rule (fixed-tilt) or 0° (tracking).

    Emits to the decision trail:
      - data_source         NREL PVWatts v8 / NSRDB TMY weather
      - api_call            full inputs + outputs of the PVWatts call
      - factor              annual_production_kwh
      - factor              capacity_factor_pct
      - factor              specific_yield_kwh_per_kw
      - advisory            (optional) low-CF warning or station distance

    Returns the Stage 1 result dict consumed by downstream stages.
    """
    trail = ctx.trail

    # ── Sizing + tilt resolution ───────────────────────────────────────────
    if system_capacity_kw is None:
        system_capacity_kw = _sizing_from_acreage(parcel_acreage or 0.0, array_type)
    if system_capacity_kw <= 0:
        raise ValueError(
            "Stage 1 needs either parcel_acreage > 0 or system_capacity_kw > 0; "
            "neither was usable."
        )
    if tilt is None:
        tilt = _suggested_tilt(latitude, array_type)

    # ── Data source declaration ────────────────────────────────────────────
    trail.data_source(
        "NREL PVWatts v8",
        source="developer.nlr.gov",
        vintage="PVWatts v8.5.0 (NSRDB TMY 2020 typical-meteorological-year weather)",
        kind="federal HTTP API",
        license="public",
    )

    # ── PVWatts API call ───────────────────────────────────────────────────
    parameters = {
        "latitude":           round(latitude, 5),
        "longitude":          round(longitude, 5),
        "system_capacity_kw": round(system_capacity_kw, 1),
        "tilt_deg":           tilt,
        "azimuth_deg":        round(azimuth, 1),
        "array_type":         array_type,
        "array_type_label":   ARRAY_TYPE_LABEL.get(array_type, "?"),
        "module_type":        module_type,
        "module_type_label":  MODULE_TYPE_LABEL.get(module_type, "?"),
        "losses_pct":         losses_pct,
        "sizing_basis": (
            f"{parcel_acreage} acres × 1 MW / {ACRES_PER_MW.get(array_type, 5.0)} acres"
            if parcel_acreage and parcel_acreage > 0
            else "explicit system_capacity_kw"
        ),
    }
    async with ctx.http_client(timeout=30.0) as client:
        pv = await pvwatts_v8(
            client,
            latitude=latitude,
            longitude=longitude,
            system_capacity_kw=system_capacity_kw,
            tilt=tilt,
            azimuth=azimuth,
            array_type=array_type,
            module_type=module_type,
            losses_pct=losses_pct,
        )

    ac_annual = pv.get("ac_annual_kwh") or 0.0
    cf_pct    = pv.get("capacity_factor_pct") or 0.0
    solrad    = pv.get("solrad_annual") or 0.0
    station   = pv.get("station") or {}
    specific_yield = round(ac_annual / system_capacity_kw, 1) if system_capacity_kw > 0 else None

    response_summary = {
        "ac_annual_kwh":       round(ac_annual, 0),
        "ac_annual_mwh":       round(ac_annual / 1000.0, 1),
        "capacity_factor_pct": round(cf_pct, 2),
        "solrad_annual_kwh_per_m2_per_day": round(solrad, 2),
        "specific_yield_kwh_per_kw_yr":     specific_yield,
        "ac_monthly_kwh":      pv.get("ac_monthly_kwh"),
        "pvwatts_version":     pv.get("version"),
        "station_lat":         station.get("latitude"),
        "station_lng":         station.get("longitude"),
        "station_elev_m":      station.get("elevation"),
        "station_tz":          station.get("tz"),
        "station_label":       station.get("location"),
    }

    interpretation = (
        f"PVWatts predicts {response_summary['ac_annual_mwh']:.0f} MWh/yr for a "
        f"{round(system_capacity_kw/1000.0, 1)} MW {parameters['array_type_label'].lower()} "
        f"system at {tilt}° tilt / {azimuth:.0f}° azimuth. Capacity factor "
        f"{cf_pct:.1f}% — {_capacity_factor_interp(cf_pct)}. Specific yield "
        f"{specific_yield:,} kWh/kW-yr. Annual GHI {solrad:.2f} kWh/m²/day."
    )

    trail.api_call(
        "pvwatts_resource_assessment",
        provider="NREL PVWatts v8 (NSRDB TMY)",
        endpoint="https://developer.nlr.gov/api/pvwatts/v8.json",
        parameters=parameters,
        response_summary=response_summary,
        message=interpretation,
    )

    # ── Factor events for downstream stages ────────────────────────────────
    trail.factor(
        "annual_production_kwh",
        value=round(ac_annual, 0),
        source="NREL PVWatts v8",
    )
    trail.factor(
        "capacity_factor_pct",
        value=round(cf_pct, 2),
        source="NREL PVWatts v8",
        interpretation=_capacity_factor_interp(cf_pct),
    )
    trail.factor(
        "specific_yield_kwh_per_kw_yr",
        value=specific_yield,
        source="ac_annual / system_capacity_kw",
    )
    trail.factor(
        "solrad_annual_kwh_per_m2_per_day",
        value=round(solrad, 2),
        source="NREL NSRDB (via PVWatts)",
    )

    # ── Advisories ─────────────────────────────────────────────────────────
    if cf_pct < 17:
        trail.advisory(
            f"Capacity factor of {cf_pct:.1f}% is below the 17% threshold typical "
            "for economically viable utility-scale solar. Verify resource data or "
            "consider alternative siting.",
            severity="warning",
            name="low_capacity_factor",
        )
    if station.get("latitude") is not None:
        # Crude great-circle distance to the weather station.
        import math
        dlat = math.radians(latitude - float(station["latitude"]))
        dlng = math.radians(longitude - float(station["longitude"]))
        avg_lat = math.radians((latitude + float(station["latitude"])) / 2)
        dist_km = 6371 * math.sqrt(dlat * dlat + (dlng * math.cos(avg_lat)) ** 2)
        if dist_km > 50:
            trail.advisory(
                f"Nearest NSRDB weather station is {dist_km:.0f} km away; "
                "PVWatts uses TMY data from that station which may not capture "
                "local microclimate (e.g. coastal fog, mountain shadow).",
                severity="info",
                name="distant_weather_station",
                distance_km=round(dist_km, 0),
            )

    # ── Stage 1 result ─────────────────────────────────────────────────────
    return {
        "stage":               1,
        "stage_name":          "Solar Resource Assessment",
        "inputs":              parameters,
        "pvwatts_outputs":     response_summary,
        "factors": {
            "annual_production_kwh":            round(ac_annual, 0),
            "capacity_factor_pct":              round(cf_pct, 2),
            "specific_yield_kwh_per_kw_yr":     specific_yield,
            "solrad_annual_kwh_per_m2_per_day": round(solrad, 2),
        },
        "interpretation":      interpretation,
    }
