"""Deepened solar site-feasibility module — stage-by-stage pipeline.

Each stage is an independent function that accepts a ``RequestContext`` (for
SQL/HTTP tracing + decision-trail event emission) and returns a structured
``Stage{N}Result`` dict downstream stages consume.

Stage inventory (per deep_module_specifications.md, see docs/):
  Stage 1  Solar Resource Assessment       (this file)
  Stage 2  Terrain Optimization            (this file)
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

import math
from typing import Any

from .decision_trail import RequestContext
from .integrations import elev_multipoint_m, pvwatts_v8, slope_aspect_from_grid

MODULE_NAME = "solar_site_feasibility_deep"
MODULE_VERSION = "0.2.0"  # Stage 2 (terrain) added


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


# ─── Stage 2 — Terrain Optimization ───────────────────────────────────────


# Grid sampling defaults. 5×5 = 25 elevations from one 3DEP multipoint call;
# 3×3 interior cells supply slope + aspect via central differences. The grid
# is laid out as a square covering the parcel bounding box derived from
# acreage (assumes roughly square parcel — true for utility-scale ground-
# mount sites which favour rectangular layouts).
TERRAIN_GRID_N = 5  # rows == cols; 25 sample points

# Aspect / slope qualitative thresholds.
ASPECT_SOUTH_DEG       = 180.0
ASPECT_DEVIATION_WARN  = 30.0   # advise re-running PVWatts beyond this
SLOPE_MODERATE_PCT     = 5.0    # grading costs increase
SLOPE_LIKELY_EXCLUDE_PCT = 15.0 # likely excluded for utility-scale
ASPECT_FACTOR_FLOOR    = 0.7    # clamp lower bound for aspect-adjusted irradiance
# Below this slope, aspect is mathematically defined but practically irrelevant
# for solar production (essentially flat — any azimuth performs equivalently).
# Used to silence false-positive aspect advisories on flat parcels.
ASPECT_MEANINGFUL_SLOPE_PCT = 1.0


def _parcel_side_m(acreage: float) -> float:
    """Convert acreage → side length (m) of a square of equal area."""
    area_m2 = acreage * 4046.8564224  # international acre
    return math.sqrt(area_m2)


def _make_grid_points(
    *, latitude: float, longitude: float, side_m: float, n: int
) -> list[tuple[float, float]]:
    """Return ``n × n`` (lng, lat) pairs covering the parcel bbox, row-major.

    Row 0 is the SOUTHERNMOST row; column 0 is the WESTERNMOST column. This
    matches the contract of slope_aspect_from_grid (north up)."""
    side_lat_deg = side_m / 111_320.0
    side_lng_deg = side_m / (111_320.0 * max(math.cos(math.radians(latitude)), 0.1))
    points: list[tuple[float, float]] = []
    for i in range(n):  # row (south → north)
        lat = latitude - side_lat_deg / 2 + side_lat_deg * i / (n - 1)
        for j in range(n):  # col (west → east)
            lng = longitude - side_lng_deg / 2 + side_lng_deg * j / (n - 1)
            points.append((lng, lat))
    return points


def _aspect_deviation_from_south(aspect_deg: float | None) -> float | None:
    if aspect_deg is None:
        return None
    dev = abs(aspect_deg - ASPECT_SOUTH_DEG)
    return round(min(dev, 360.0 - dev), 1)


def _aspect_irradiance_factor(deviation_deg: float | None) -> float:
    """Cosine of aspect deviation, clamped to [0.7, 1.0]. South-facing → 1.0,
    east/west → ~0.7, north → 0.7 (clamped floor)."""
    if deviation_deg is None:
        return 1.0
    f = math.cos(math.radians(deviation_deg))
    return round(max(ASPECT_FACTOR_FLOOR, min(1.0, f)), 3)


def _terrain_rating(uniformity_m: float) -> str:
    if uniformity_m < 2.0:
        return "flat"
    if uniformity_m < 5.0:
        return "gently rolling"
    if uniformity_m < 15.0:
        return "variable"
    return "steep/irregular"


async def stage2_terrain_optimization(
    ctx: RequestContext,
    *,
    latitude: float,
    longitude: float,
    parcel_acreage: float,
    grid_n: int = TERRAIN_GRID_N,
) -> dict[str, Any]:
    """Stage 2 — Terrain Optimization via USGS 3DEP elevation sampling.

    Computes three metrics across a parcel-bbox grid:
      1. Mean slope (% grade)
      2. Slope-weighted dominant aspect (compass degrees) + deviation from south
         + aspect-adjusted irradiance factor (cos of deviation, [0.7, 1.0])
      3. Terrain variability — standard deviation of elevation across the grid
         (qualitative rating: flat / gently rolling / variable / steep-irregular)

    Emits to the trail:
      - data_source         USGS 3DEP 1/3 arc-second DEM
      - step                terrain_sampling (n×n grid, bbox extent, samples)
      - factor              mean_slope_pct, dominant_aspect_deg,
                            aspect_deviation_from_south_deg, aspect_irradiance_factor,
                            terrain_uniformity_m, terrain_rating
      - advisory (cond.)    azimuth_recommendation — if aspect deviates > 30°
                            from 180°, advises re-running Stage 1 PVWatts with
                            the terrain-optimal azimuth
      - advisory (cond.)    steep_slope — if mean slope > 15% (likely exclusion)
      - advisory (cond.)    irregular_terrain — if uniformity rating is
                            "steep/irregular" (recommend site survey)
    """
    if parcel_acreage <= 0:
        raise ValueError("Stage 2 needs parcel_acreage > 0 to size the bbox grid.")
    trail = ctx.trail

    side_m = _parcel_side_m(parcel_acreage)
    dx_m = side_m / (grid_n - 1)
    dy_m = side_m / (grid_n - 1)
    points = _make_grid_points(
        latitude=latitude, longitude=longitude, side_m=side_m, n=grid_n
    )

    # ── Data source declaration ────────────────────────────────────────────
    trail.data_source(
        "USGS 3DEP 1/3 arc-second DEM",
        source="elevation.nationalmap.gov",
        vintage="2024 (continuous national elevation product, ~10 m resolution)",
        kind="federal HTTP ArcGIS ImageServer",
        license="public",
    )

    # ── 3DEP multipoint sample (single HTTP call for N² elevations) ────────
    async with ctx.http_client(timeout=30.0) as client:
        elevs = await elev_multipoint_m(client, points)
    have = sum(1 for e in elevs if e is not None)

    bbox = {
        "south": round(min(p[1] for p in points), 6),
        "north": round(max(p[1] for p in points), 6),
        "west":  round(min(p[0] for p in points), 6),
        "east":  round(max(p[0] for p in points), 6),
        "side_m": round(side_m, 1),
    }
    trail.step(
        "terrain_sampling",
        source="USGS 3DEP getSamples (multipoint)",
        value={"samples": have, "grid_n": grid_n, "spacing_m": round(dx_m, 1)},
        units="elevations",
        result="resolved" if have == len(points) else "partial",
        bbox=bbox,
    )

    if have < grid_n * grid_n:
        trail.advisory(
            f"3DEP returned {have} of {grid_n * grid_n} elevations — "
            "grid points outside CONUS or in data gaps were skipped.",
            severity="warning",
            name="terrain_data_gap",
        )

    # ── Slope, aspect, uniformity ──────────────────────────────────────────
    grid = [elevs[i * grid_n : (i + 1) * grid_n] for i in range(grid_n)]
    _, summary = slope_aspect_from_grid(grid, dx_m=dx_m, dy_m=dy_m)
    valid_elevs = [e for e in elevs if e is not None]
    if len(valid_elevs) >= 2:
        mean_elev = sum(valid_elevs) / len(valid_elevs)
        uniformity_m = math.sqrt(
            sum((e - mean_elev) ** 2 for e in valid_elevs) / len(valid_elevs)
        )
    else:
        mean_elev = valid_elevs[0] if valid_elevs else None
        uniformity_m = 0.0
    uniformity_m = round(uniformity_m, 2)
    terrain_rating = _terrain_rating(uniformity_m)

    mean_slope_pct      = summary["mean_slope_pct"]
    mean_slope_deg      = summary["mean_slope_deg"]
    dominant_aspect_deg = summary["dominant_aspect_deg"]
    # Below the meaningful-slope threshold, aspect is reported but not acted on:
    # the parcel is effectively flat and any azimuth produces equivalent yield.
    aspect_is_meaningful = (
        mean_slope_pct is not None
        and mean_slope_pct >= ASPECT_MEANINGFUL_SLOPE_PCT
    )
    aspect_dev_deg = (
        _aspect_deviation_from_south(dominant_aspect_deg)
        if aspect_is_meaningful else None
    )
    aspect_factor = (
        _aspect_irradiance_factor(aspect_dev_deg)
        if aspect_is_meaningful else 1.0
    )

    # ── Factor events ──────────────────────────────────────────────────────
    trail.factor("mean_slope_pct", value=mean_slope_pct, source="3DEP grid central diff")
    trail.factor("mean_slope_deg", value=mean_slope_deg, source="3DEP grid central diff")
    trail.factor(
        "dominant_aspect_deg", value=dominant_aspect_deg,
        source="slope-weighted circular mean of grid aspects",
    )
    trail.factor(
        "aspect_deviation_from_south_deg", value=aspect_dev_deg,
        source="|aspect − 180°| with wraparound",
    )
    trail.factor(
        "aspect_irradiance_factor", value=aspect_factor,
        source=(
            f"cos(deviation), clamped to [{ASPECT_FACTOR_FLOOR}, 1.0]"
            if aspect_is_meaningful
            else f"parcel mean slope {mean_slope_pct}% < "
                 f"{ASPECT_MEANINGFUL_SLOPE_PCT}% — aspect not meaningful, factor pinned to 1.0"
        ),
    )
    trail.factor(
        "terrain_uniformity_m", value=uniformity_m,
        source="stdev of elevation across grid",
        rating=terrain_rating, mean_elev_m=round(mean_elev, 1) if mean_elev else None,
    )
    trail.factor(
        "terrain_rating", value=terrain_rating,
        source=f"qualitative bucket from terrain_uniformity_m={uniformity_m} m",
    )

    # ── Conditional advisories ─────────────────────────────────────────────
    # Slope-driven exclusions
    if mean_slope_pct is not None:
        if mean_slope_pct >= SLOPE_LIKELY_EXCLUDE_PCT:
            trail.advisory(
                f"Mean slope {mean_slope_pct:.1f}% exceeds the {SLOPE_LIKELY_EXCLUDE_PCT}% "
                "utility-scale threshold — parcel is likely excluded from fixed-tilt "
                "development. Consider single-axis tracking or a different site.",
                severity="warning", name="steep_slope",
                mean_slope_pct=mean_slope_pct,
            )
        elif mean_slope_pct >= SLOPE_MODERATE_PCT:
            trail.advisory(
                f"Mean slope {mean_slope_pct:.1f}% is moderate (above the {SLOPE_MODERATE_PCT}% "
                "threshold) — expect higher grading costs in Stage 6 LCOE.",
                severity="info", name="moderate_slope",
                mean_slope_pct=mean_slope_pct,
            )

    # Aspect-driven cross-stage recommendation (this is the key Stage 1 → Stage 2 loop)
    if (
        aspect_is_meaningful
        and dominant_aspect_deg is not None
        and aspect_dev_deg is not None
        and aspect_dev_deg > ASPECT_DEVIATION_WARN
    ):
        trail.advisory(
            f"Terrain aspect {dominant_aspect_deg:.0f}° deviates {aspect_dev_deg:.0f}° from "
            f"south (180°). Consider re-running Stage 1 PVWatts with "
            f"azimuth={dominant_aspect_deg:.0f}° for a terrain-aligned production estimate. "
            f"The aspect-adjusted irradiance factor is {aspect_factor} "
            f"(1.0 = south-facing optimal).",
            severity="warning", name="azimuth_recommendation",
            recommended_azimuth_deg=dominant_aspect_deg,
            aspect_deviation_deg=aspect_dev_deg,
            aspect_irradiance_factor=aspect_factor,
            cross_stage="Stage 1 PVWatts re-run candidate",
        )

    # Variability-driven exclusions
    if terrain_rating == "steep/irregular":
        trail.advisory(
            f"Terrain variability {uniformity_m:.1f} m (rating: {terrain_rating}) "
            "indicates irregular terrain. Recommend a topographic site survey "
            "before committing capital.",
            severity="warning", name="irregular_terrain",
            terrain_uniformity_m=uniformity_m, terrain_rating=terrain_rating,
        )

    # ── Stage 2 result ─────────────────────────────────────────────────────
    interpretation_parts = []
    if mean_slope_pct is not None:
        interpretation_parts.append(
            f"Mean slope {mean_slope_pct:.2f}% ({mean_slope_deg:.2f}°)."
        )
    if dominant_aspect_deg is not None and aspect_is_meaningful:
        interpretation_parts.append(
            f"Dominant aspect {dominant_aspect_deg:.0f}° "
            f"(dev {aspect_dev_deg:.0f}° from south; irradiance factor {aspect_factor})."
        )
    elif dominant_aspect_deg is not None:
        interpretation_parts.append(
            f"Dominant aspect {dominant_aspect_deg:.0f}° but slope is below "
            f"{ASPECT_MEANINGFUL_SLOPE_PCT}% — effectively flat, any azimuth equivalent."
        )
    interpretation_parts.append(
        f"Terrain variability {uniformity_m:.1f} m — {terrain_rating}."
    )
    interpretation = " ".join(interpretation_parts)

    return {
        "stage":      2,
        "stage_name": "Terrain Optimization",
        "inputs": {
            "latitude": latitude, "longitude": longitude,
            "parcel_acreage": parcel_acreage,
            "grid_n": grid_n, "grid_spacing_m": round(dx_m, 1),
            "bbox": bbox,
        },
        "samples": {
            "requested":            grid_n * grid_n,
            "returned":             have,
            "mean_elevation_m":     round(mean_elev, 1) if mean_elev else None,
        },
        "factors": {
            "mean_slope_pct":                   mean_slope_pct,
            "mean_slope_deg":                   mean_slope_deg,
            "dominant_aspect_deg":              dominant_aspect_deg,
            "aspect_deviation_from_south_deg":  aspect_dev_deg,
            "aspect_irradiance_factor":         aspect_factor,
            "terrain_uniformity_m":             uniformity_m,
            "terrain_rating":                   terrain_rating,
        },
        "recommendations": {
            # The Stage 1 → Stage 2 azimuth loop. Stage 1 (or a Stage 8
            # composite) can choose to re-run PVWatts using this azimuth —
            # but only when slope makes aspect operationally meaningful.
            "azimuth_deg_terrain_optimized": (
                dominant_aspect_deg if aspect_is_meaningful else None
            ),
            "should_rerun_pvwatts":         (
                aspect_is_meaningful
                and aspect_dev_deg is not None
                and aspect_dev_deg > ASPECT_DEVIATION_WARN
            ),
            "aspect_is_meaningful": aspect_is_meaningful,
        },
        "interpretation": interpretation,
    }
