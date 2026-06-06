"""Phase 4 — refactored solar scoring pipeline.

Consumes the Phase 3 data_selection.select_data() output instead of querying
data sources directly. Per the build spec:

  1. score_solar_siting() calls select_data("solar_siting", lat, lng) FIRST.
  2. Per-criterion scoring uses the source the selection engine PICKED for
     that criterion (authoritative vs fallback vs proxy). The criterion's
     confidence carries forward into the per-criterion result.
  3. Exclusion checks consult the source picked by the selection engine.
  4. Output bundles score + rating + criteria_scores + exclusions + the
     selection engine's full confidence report + the methodology document
     from the methodology repo.

Measurements that the spec-1 probe doesn't capture (the actual elevation,
the irradiance, the soil drainage class, etc.) are fetched inside a
``_Measurements`` cache so each underlying source is hit at most once per
assessment — honouring the "no redundant queries" rule.
"""

from __future__ import annotations

import json
import math
from typing import Any

import asyncpg
import httpx

from .critical_sources import (
    CANNOT_ASSESS,
    cannot_assess_statement,
    scoring_critical_gap,
    selection_critical_gaps,
)
from .data_selection import CriterionSelection, DataSelectionResult, select_data
from .display_names import criterion_name, enrich_result, gap_message
from .integrations import (
    critical_habitat_at_point,
    ejscreen_at_point,
    elev_multipoint_m,
    nlcd_class_at_point,
    padus_at_point,
    pvwatts_v8,
    sda_point,
    slope_aspect_from_grid,
)
from .interconnection import get_interconnection_context
from .methodology_repository import get_methodology_doc
from .nerc_regions import get_nerc_region

MODULE_NAME = "solar_siting_scoring_v2"
MODULE_VERSION = "0.5.0"  # exclusion-precision refinements (GAP/NLCD/flood/slope)

# Slope exclusion threshold (percent). Raised from 15% to 20% per the Exclusion
# Precision Spec: literature ranges from 3% (Hernandez 2015, conservative) to 20°
# (~36%); 20% (~11.3°) is moderate and accommodates single-axis trackers on
# rolling terrain.
SLOPE_EXCLUSION_THRESHOLD = 20.0


# ─── Measurement cache — one query per source per assessment ──────────────


class _Measurements:
    """Memoizes measurement queries so each source is hit at most once per
    assessment. Selection engine probes establish AVAILABILITY; these calls
    pull the actual VALUES needed for scoring."""

    def __init__(self, pool: asyncpg.Pool, client: httpx.AsyncClient,
                 latitude: float, longitude: float) -> None:
        self.pool = pool
        self.client = client
        self.lat = latitude
        self.lng = longitude
        self._cache: dict[str, Any] = {}

    async def _get(self, key: str, fetcher: Any) -> Any:
        if key not in self._cache:
            try:
                self._cache[key] = await fetcher()
            except Exception:  # noqa: BLE001 — degrade gracefully on per-source errors
                self._cache[key] = None
        return self._cache[key]

    async def pvwatts(self) -> dict[str, Any] | None:
        return await self._get("pvwatts", lambda: pvwatts_v8(
            self.client, latitude=self.lat, longitude=self.lng,
            system_capacity_kw=1000.0, tilt=20.0, azimuth=180.0,
            array_type=0, module_type=0, losses_pct=14.0,
        ))

    async def terrain(self) -> dict[str, Any] | None:
        return await self._get("terrain", lambda: self._fetch_terrain())

    async def _fetch_terrain(self) -> dict[str, Any] | None:
        """3×3 grid around the point → slope + aspect of the interior cell."""
        side_m = 200.0
        d_lat = side_m / 111_320.0
        d_lng = side_m / (111_320.0 * max(math.cos(math.radians(self.lat)), 0.1))
        pts = []
        for i in range(3):
            for j in range(3):
                pts.append((
                    self.lng - d_lng / 2 + d_lng * j / 2,
                    self.lat - d_lat / 2 + d_lat * i / 2,
                ))
        elevs = await elev_multipoint_m(self.client, pts)
        grid = [elevs[i * 3:(i + 1) * 3] for i in range(3)]
        cells, _summary = slope_aspect_from_grid(grid, dx_m=side_m / 2, dy_m=side_m / 2)
        c = cells[1][1] if cells and cells[1] and cells[1][1] is not None else None
        return {
            "elev_m":     elevs[4],
            "slope_pct":  (c and c["slope_pct"]),
            "aspect_deg": (c and c["aspect_deg"]),
        }

    async def soil(self) -> dict[str, Any] | None:
        return await self._get("soil", lambda: sda_point(
            self.client, latitude=self.lat, longitude=self.lng,
        ))

    async def land_cover(self) -> dict[str, Any] | None:
        return await self._get("land_cover", lambda: nlcd_class_at_point(
            self.client, latitude=self.lat, longitude=self.lng,
        ))

    async def padus(self) -> list[dict[str, Any]]:
        return await self._get("padus", lambda: padus_at_point(
            self.client, latitude=self.lat, longitude=self.lng,
        )) or []

    async def critical_habitat(self) -> list[dict[str, Any]]:
        return await self._get("ch", lambda: critical_habitat_at_point(
            self.client, latitude=self.lat, longitude=self.lng,
        )) or []

    async def ejscreen(self) -> dict[str, Any] | None:
        return await self._get("ejscreen", lambda: ejscreen_at_point(
            self.pool, self.client, latitude=self.lat, longitude=self.lng,
        ))

    async def nfhl_zone(self) -> str | None:
        from .flood_scoring import query_nfhl
        nfhl = await self._get(
            "nfhl", lambda: query_nfhl(self.client, self.lng, self.lat),
        )
        return (nfhl or {}).get("flood_zone")

    async def transmission_distance_km(self) -> float | None:
        return await self._get(
            "tx_km", lambda: _nearest_postgis_km(
                self.pool, "solar_transmission_lines", self.lat, self.lng,
            ),
        )

    async def substation_distance_km(self) -> float | None:
        return await self._get(
            "sub_km", lambda: _nearest_postgis_km(
                self.pool, "substations_osm_us", self.lat, self.lng,
            ),
        )


async def _nearest_postgis_km(
    pool: asyncpg.Pool, table: str, lat: float, lng: float,
) -> float | None:
    """Distance in km from (lat, lng) to the nearest feature in ``table``,
    bounded to a 50 km probe radius."""
    try:
        async with pool.acquire() as conn:
            d = await conn.fetchval(
                f"""
                SELECT MIN(ST_Distance(
                    t.geometry::geography,
                    ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography
                ))
                FROM {table} t
                WHERE ST_DWithin(
                    t.geometry::geography,
                    ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography,
                    50000
                )
                """,
                lng, lat,
            )
    except Exception:  # noqa: BLE001
        return None
    return (float(d) / 1000.0) if d is not None else None


# ─── Scoring helpers ──────────────────────────────────────────────────────


def _linear(x: float | None, lo: float, hi: float, *, inverted: bool = False) -> float:
    """Linear 0-1 score with x mapped from [lo, hi]. ``inverted`` flips the
    direction (used for "smaller is better" metrics like distance)."""
    if x is None:
        return 0.0
    if hi == lo:
        return 0.5
    t = (x - lo) / (hi - lo)
    if inverted:
        t = 1 - t
    return max(0.0, min(1.0, t))


def _selected_source_id(sel: CriterionSelection) -> str | None:
    return sel.selected_sources[0]["source_id"] if sel.selected_sources else None


# ─── Per-criterion scorers ────────────────────────────────────────────────


async def _score_solar_ghi(m: _Measurements) -> tuple[float, dict[str, Any]]:
    pv = await m.pvwatts()
    if not pv:
        # solar_ghi is THE solar resource — flag it as a critical unavailability
        # so the orchestrator returns CANNOT ASSESS rather than a partial score.
        return 0.0, {"reason": "PVWatts unavailable", "critical_unavailable": True}
    cf = pv.get("capacity_factor_pct") or 0.0
    return _linear(cf, 14.0, 22.0), {
        "capacity_factor_pct": round(cf, 2),
        "ac_annual_kwh":       pv.get("ac_annual_kwh"),
        "formula":             "linear 14% → 0.0, 22% → 1.0",
    }


async def _score_solar_slope(m: _Measurements) -> tuple[float, dict[str, Any]]:
    t = await m.terrain()
    s = t and t.get("slope_pct")
    if s is None:
        return 0.0, {"reason": "3DEP unavailable"}
    return _linear(s, 0.0, 15.0, inverted=True), {
        "slope_pct": round(s, 2),
        "formula":   "linear 0 % → 1.0, 15 % → 0.0",
    }


async def _score_solar_aspect(m: _Measurements) -> tuple[float, dict[str, Any]]:
    t = await m.terrain()
    if not t:
        return 0.0, {"reason": "3DEP unavailable"}
    aspect = t.get("aspect_deg")
    slope = t.get("slope_pct") or 0.0
    if aspect is None or slope < 1.0:
        return 1.0, {"slope_pct": round(slope, 2),
                     "note": "slope < 1 % → aspect not meaningful, full credit"}
    dev = abs(aspect - 180.0)
    dev = min(dev, 360 - dev)
    return max(0.0, math.cos(math.radians(dev))), {
        "aspect_deg": round(aspect, 1),
        "deviation_from_south_deg": round(dev, 1),
        "formula": "cos(deviation from south), clamped [0, 1]",
    }


async def _score_solar_transmission(
    m: _Measurements, sel: CriterionSelection, selection: DataSelectionResult,
) -> tuple[float, dict[str, Any]]:
    """Use the source the selection engine chose. If hifld_transmission, read
    distance straight from the source_cache (the Phase 1 probe captured it)
    rather than re-querying."""
    chosen = _selected_source_id(sel)
    dist_km: float | None = None
    source_used: str | None = None

    if chosen == "hifld_transmission":
        sr = selection.source_cache.get("hifld_transmission")
        if sr and sr.data and sr.data.get("nearest_m") is not None:
            dist_km = float(sr.data["nearest_m"]) / 1000.0
            source_used = "hifld_transmission"
    if dist_km is None and chosen in (
        "osm_substations", "osm_substations_overpass",
    ):
        sr = selection.source_cache.get("osm_substations")
        if sr and sr.data and sr.data.get("nearest_m") is not None:
            dist_km = float(sr.data["nearest_m"]) / 1000.0
            source_used = "osm_substations"
    # Last-resort: query PostGIS direct (covers misalignment between selection
    # and source_cache).
    if dist_km is None:
        dist_km = await m.transmission_distance_km()
        source_used = "hifld_transmission (live)"
    if dist_km is None:
        return 0.0, {"reason": "no transmission or substation within 50 km"}
    return _linear(dist_km, 0.0, 16.0, inverted=True), {
        "distance_km": round(dist_km, 2),
        "source_used": source_used,
        "formula":     "linear 0 km → 1.0, 16 km (~10 mi) → 0.0",
    }


async def _score_solar_road(m: _Measurements) -> tuple[float, dict[str, Any]]:
    # OSM roads on-demand not wired here; the methodology trees include
    # osm_roads_overpass but the integration helper isn't built. Default to
    # 0.5 with an explicit note so the consumer knows the criterion was
    # registered but not yet measured.
    return 0.5, {
        "reason": ("osm_roads_overpass integration not yet wired; default "
                   "midpoint score 0.5"),
    }


async def _score_solar_land_cover(m: _Measurements) -> tuple[float, dict[str, Any]]:
    lc = await m.land_cover()
    if not lc:
        return 0.0, {"reason": "NLCD unavailable"}
    code = lc.get("code")
    score_map = {
        11: 0.0, 12: 0.0,                       # water + ice
        21: 0.3, 22: 0.1, 23: 0.0, 24: 0.0,     # developed
        31: 0.9,                                # barren
        41: 0.3, 42: 0.3, 43: 0.3,              # forest
        51: 0.6, 52: 0.6,                       # shrub
        71: 0.7, 72: 0.7, 73: 0.7, 74: 0.7,     # grass/herbaceous
        81: 0.8,                                # pasture
        82: 0.9,                                # cultivated crops
        90: 0.0, 95: 0.0,                       # wetlands
    }
    score = score_map.get(code, 0.5)
    return score, {
        "nlcd_code":  code,
        "nlcd_label": lc.get("label"),
        "group":      lc.get("group"),
    }


async def _score_solar_soil(m: _Measurements) -> tuple[float, dict[str, Any]]:
    soil = await m.soil()
    if not soil:
        return 0.5, {"reason": "SSURGO unavailable, midpoint score"}
    drain = (soil.get("drainage_class") or "").lower()
    hydric = (soil.get("hydric_rating") or "").lower()
    if hydric == "yes":
        score = 0.2
    elif "well drained" in drain and "moderately" not in drain:
        score = 1.0
    elif "moderately well drained" in drain:
        score = 0.8
    elif "somewhat poorly drained" in drain:
        score = 0.5
    elif "poorly drained" in drain:
        score = 0.3
    else:
        score = 0.6
    return score, {
        "mapunit_name":   soil.get("mapunit_name"),
        "drainage_class": soil.get("drainage_class"),
        "hydric_rating":  soil.get("hydric_rating"),
    }


async def _score_solar_ej(m: _Measurements) -> tuple[float, dict[str, Any]]:
    ej = await m.ejscreen()
    if not ej or not ej.get("found_in_dataset"):
        return 0.5, {"reason": "EJScreen unavailable, midpoint score"}
    pct = ej.get("p_demogidx_2") or 50.0
    return _linear(pct, 0.0, 100.0, inverted=True), {
        "block_group_geoid": ej.get("block_group_geoid"),
        "demogidx_percentile": pct,
        "pm25_percentile":     ej.get("p_pm25"),
        "formula": "lower demographic-index percentile → higher score",
    }


# ─── Exclusion checks ─────────────────────────────────────────────────────


async def _excl_protected(m: _Measurements) -> tuple[bool, dict[str, Any]]:
    """Hard-exclude only GAP 1-2 (biodiversity-managed: wilderness, nature
    preserves, national parks). GAP 3-4 (BLM/national forest/multi-use, tribal,
    DOD, conservation easement) frequently permit solar with approvals — these
    become an advisory, not an exclusion. Per the Exclusion Precision Spec; many
    of the largest US solar farms sit on GAP 3 BLM land."""
    pa = await m.padus()
    if not pa:
        return False, {}
    hard = [p for p in pa if str(p.get("gap_status")) in ("1", "2")]
    if hard:
        return True, {
            "gap_status":   sorted({str(p.get("gap_status")) for p in hard}),
            "units":        [p.get("unit_name") for p in hard if p.get("unit_name")][:3],
            "designations": [p.get("designation_type") for p in hard if p.get("designation_type")][:3],
            "reason": ("GAP 1-2 protected area — managed for biodiversity, "
                       "development not permitted"),
        }
    # Only GAP 3-4 overlap → advisory, NOT a hard exclusion.
    return False, {
        "advisory":        True,
        "gap_status":      sorted({str(p.get("gap_status")) for p in pa}),
        "units":           [p.get("unit_name") for p in pa if p.get("unit_name")][:3],
        "managing_agency": [p.get("manager_name") for p in pa if p.get("manager_name")][:3],
        "designations":    [p.get("designation_type") for p in pa if p.get("designation_type")][:3],
        "note": ("GAP 3-4 managed land (multiple-use) — solar may be permitted "
                 "with appropriate approvals; verify permitted use with the "
                 "managing agency"),
    }


async def _score_solar_flood(m: _Measurements) -> tuple[float, dict[str, Any]]:
    """Flood as a SCORED criterion (Exclusion Precision Spec): A/AE 100-year
    floodplains no longer hard-exclude — solar operates there with elevated
    mounting and floodplain permitting — they take a scored penalty instead. V
    zones (coastal high hazard, wave action) remain a hard exclusion, signalled
    via ``hard_exclude`` in the basis. Outside the SFHA → full credit."""
    z = await m.nfhl_zone()
    if z is None:
        return 0.5, {"flood_zone": None, "reason": "NFHL query failed — midpoint"}
    zu = (z or "").upper()
    if zu.startswith("V"):
        return 0.0, {
            "flood_zone": z, "hard_exclude": True,
            "reason": ("FEMA Zone " + z + " — coastal high hazard; wave action "
                       "incompatible with ground-mount solar"),
        }
    if zu.startswith("A"):
        return 0.35, {
            "flood_zone": z, "penalty": True,
            "note": ("FEMA Zone " + z + " — 100-year floodplain. Solar development "
                     "possible with elevated mounting and floodplain permitting; "
                     "insurance costs may be higher."),
        }
    return 1.0, {"flood_zone": z or "X/none",
                 "note": "outside the Special Flood Hazard Area"}


async def _excl_wetlands(
    m: _Measurements, sel: CriterionSelection,
) -> tuple[bool | None, dict[str, Any]]:
    chosen = _selected_source_id(sel)
    if chosen == "nwi_wetlands":
        try:
            async with m.pool.acquire() as conn:
                n = await conn.fetchval(
                    """
                    SELECT COUNT(*) FROM solar_wetlands_ca
                    WHERE ST_Intersects(
                        geometry, ST_SetSRID(ST_MakePoint($1, $2), 4326)
                    )
                    """,
                    m.lng, m.lat,
                )
            return (int(n) > 0), {"source": "nwi_wetlands", "feature_count": int(n)}
        except Exception as e:  # noqa: BLE001
            return None, {"reason": f"NWI PostGIS query failed: {e}"}
    if chosen == "usda_sda_ssurgo":
        soil = await m.soil()
        if not soil:
            return None, {"reason": "SSURGO unavailable"}
        hydric = (soil.get("hydric_rating") or "").lower()
        return (hydric == "yes"), {
            "source": "usda_sda_ssurgo (proxy)",
            "hydric_rating": soil.get("hydric_rating"),
            "advisory":      ("hydric soils flag is a proxy for wetlands; "
                              "field delineation recommended before commitment"),
        }
    return None, {"reason": f"no usable source (selected: {chosen})"}


async def _excl_critical_habitat(m: _Measurements) -> tuple[bool, dict[str, Any]]:
    ch = await m.critical_habitat()
    if ch:
        species = sorted({c.get("common_name") for c in ch if c.get("common_name")})[:3]
        return True, {"species": species}
    return False, {}


# NOTE: flood is no longer a hard-exclusion check — it is a scored criterion
# (_score_solar_flood above), with V zones signalling a hard exclusion via the
# basis. The old binary _excl_flood (A or V → excluded) has been removed.


async def _excl_steep(
    m: _Measurements, threshold_pct: float = SLOPE_EXCLUSION_THRESHOLD,
) -> tuple[bool | None, dict[str, Any]]:
    t = await m.terrain()
    s = t and t.get("slope_pct")
    if s is None:
        return None, {"reason": "3DEP slope unavailable"}
    return (s >= threshold_pct), {"slope_pct": round(s, 2),
                                  "threshold_pct": threshold_pct}


async def _excl_urban(m: _Measurements) -> tuple[bool | None, dict[str, Any]]:
    """Hard-exclude only NLCD 23-24 (medium/high-intensity development —
    incompatible with utility-scale solar). NLCD 21 (Developed Open Space:
    parks, golf courses, campuses) and 22 (Low Intensity) become an advisory,
    not an exclusion, per the Exclusion Precision Spec."""
    lc = await m.land_cover()
    if not lc:
        return None, {"reason": "NLCD unavailable"}
    code = lc.get("code")
    if code in (23, 24):
        return True, {
            "nlcd_code": code, "nlcd_label": lc.get("label"),
            "reason": (f"NLCD {code} ({lc.get('label')}) — dense development "
                       "incompatible with utility-scale solar"),
        }
    if code in (21, 22):
        return False, {
            "advisory": True, "nlcd_code": code, "nlcd_label": lc.get("label"),
            "note": (f"NLCD {code} ({lc.get('label')}) — developed context; "
                     "verify zoning permits solar"),
        }
    return False, {"nlcd_code": code, "nlcd_label": lc.get("label")}


# ─── Regional weight resolution (Weight Adaptation Spec, Step 6) ───────────


async def _regional_weight_profile(
    pool: asyncpg.Pool, region: str | None,
) -> dict[str, Any] | None:
    """Fetch the stored regional weight profile for a region (weights +
    metadata), or None. Kept inline (a single read) so the scoring hot path
    doesn't import the scipy-backed optimizer module."""
    if not region:
        return None
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT weights, metadata FROM regional_weight_profiles "
                "WHERE region=$1 AND workflow_type='solar_siting'",
                region,
            )
    except Exception:  # noqa: BLE001 — table missing → defaults
        return None
    if row is None:
        return None
    weights, metadata = row["weights"], row["metadata"]
    if isinstance(weights, str):
        weights = json.loads(weights)
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    return {"weights": weights, "metadata": metadata}


def _resolve_weights(
    default_weights: dict[str, float],
    region: str | None,
    profile: dict[str, Any] | None,
    weights_override: dict[str, float] | None,
) -> tuple[dict[str, float], dict[str, Any]]:
    """Pick the weight vector and build the documenting weight_profile section.

    Precedence: explicit weights_override > calibrated regional profile >
    literature defaults. Always returns a full weight per scored criterion."""
    if weights_override:
        weights = dict(default_weights)
        for k, v in weights_override.items():
            if k in weights:
                weights[k] = float(v)
        return weights, {
            "region": region,
            "method": "explicit_override",
            "note": "Caller-supplied weights_override applied over literature defaults.",
        }

    if profile:
        md, pw = profile["metadata"], profile["weights"]
        if md.get("method") == "constrained_optimization":
            n = md.get("n_eia_installations")
            weights = {c: float(pw.get(c, default_weights[c])) for c in default_weights}
            return weights, {
                "region": region,
                "method": "calibrated",
                "n_installations_in_calibration": n,
                "note": (
                    f"Weights calibrated against {n} EIA Form 860 installations in "
                    f"{region} region, constrained to ranges from Doorga et al. (2019) "
                    "and Al-Shammari et al. (2026)."
                ),
            }
        # Profile exists but was a sparse-data literature_default fallback.
        return dict(default_weights), {
            "region": region,
            "method": "literature_default",
            "note": (
                f"Fewer than 20 EIA installations in {region}. Using literature "
                "default weights from Doorga et al. (2019)."
            ),
        }

    return dict(default_weights), {
        "region": region,
        "method": "literature_default",
        "note": (
            f"No calibrated profile for {region}; using literature default weights "
            "from Doorga et al. (2019)."
            if region else
            "Location is outside the calibrated NERC regions; using literature "
            "default weights from Doorga et al. (2019)."
        ),
    }


# ─── Orchestrator ─────────────────────────────────────────────────────────


_SCORERS = {
    "solar_ghi":          _score_solar_ghi,
    "solar_slope":        _score_solar_slope,
    "solar_aspect":       _score_solar_aspect,
    "solar_road":         _score_solar_road,
    "solar_land_cover":   _score_solar_land_cover,
    "solar_soil":         _score_solar_soil,
    "solar_ej":           _score_solar_ej,
    # excl_flood was reclassified exclusion → scored (A/AE = penalty, V = hard
    # exclusion via the basis); scored here like any other criterion.
    "excl_flood":         _score_solar_flood,
    # solar_transmission is handled specially (needs the SelectionResult).
}


async def score_solar_siting(
    pool: asyncpg.Pool,
    latitude: float,
    longitude: float,
    weights_override: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Single-location solar siting score per Phase 4 build spec.

    Returns the structured result with score, rating, criteria_scores,
    exclusions, confidence (from the selection engine), and methodology
    documentation (from the methodology repo)."""

    # Step 1 — select data.
    selection = await select_data(pool, "solar_siting", latitude, longitude)

    # Step 2 — load methodology + weights (regional calibration when available).
    methodology = await get_methodology_doc(pool, "solar_siting")
    default_weights = {
        c["criterion_id"]: float(c["weight_default"] or 0.0)
        for c in methodology["criteria"]
        if c["criterion_type"] == "scored" and c["weight_default"] is not None
    }
    region = await get_nerc_region(pool, latitude, longitude)
    profile = await _regional_weight_profile(pool, region)
    weights, weight_profile = _resolve_weights(
        default_weights, region, profile, weights_override
    )

    # Interconnection proximity context (F4) — informational, independent of the
    # suitability score, so it is attached whether or not the site is assessable.
    interconnection = await get_interconnection_context(pool, latitude, longitude)

    # Step 3 — score + check exclusions, sharing one measurement cache.
    criteria_scores: dict[str, Any] = {}
    exclusion_results: dict[str, Any] = {}
    exclusions: list[str] = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        meas = _Measurements(pool, client, latitude, longitude)

        for sel in selection.criteria:
            selected_source = _selected_source_id(sel)

            if sel.criterion_type == "scored":
                if sel.confidence == 0.0:
                    criteria_scores[sel.criterion_id] = {
                        "score":            None,
                        "weight":           weights.get(sel.criterion_id),
                        "basis":            {"reason": "no data available"},
                        "confidence":       0.0,
                        "selected_source":  selected_source,
                    }
                    continue
                if sel.criterion_id == "solar_transmission":
                    score, basis = await _score_solar_transmission(meas, sel, selection)
                else:
                    scorer = _SCORERS.get(sel.criterion_id)
                    if scorer is None:
                        score, basis = 0.5, {"reason": "no scorer registered"}
                    else:
                        score, basis = await scorer(meas)
                w = weights.get(sel.criterion_id) or 0.0
                criteria_scores[sel.criterion_id] = {
                    "score":                  round(score, 4),
                    "weight":                 w,
                    "weighted_contribution":  round(score * w, 4),
                    "basis":                  basis,
                    "confidence":             sel.confidence,
                    "selected_source":        selected_source,
                }
                # A scored criterion may still signal a hard exclusion (flood V
                # zone): honour it so the rating becomes "Excluded".
                if isinstance(basis, dict) and basis.get("hard_exclude"):
                    exclusions.append(sel.criterion_id)
            else:  # exclusion
                if sel.confidence == 0.0:
                    exclusion_results[sel.criterion_id] = {
                        "excluded": None,
                        "basis":    {"reason": "no data available"},
                        "confidence": 0.0,
                        "selected_source": selected_source,
                    }
                    continue
                if sel.criterion_id == "excl_protected":
                    excluded, basis = await _excl_protected(meas)
                elif sel.criterion_id == "excl_wetlands":
                    excluded, basis = await _excl_wetlands(meas, sel)
                elif sel.criterion_id == "excl_critical_habitat":
                    excluded, basis = await _excl_critical_habitat(meas)
                elif sel.criterion_id == "excl_steep":
                    excluded, basis = await _excl_steep(meas)
                elif sel.criterion_id == "excl_urban":
                    excluded, basis = await _excl_urban(meas)
                else:
                    excluded, basis = None, {"reason": "no exclusion check"}
                exclusion_results[sel.criterion_id] = {
                    "excluded":         excluded,
                    "basis":            basis,
                    "confidence":       sel.confidence,
                    "selected_source":  selected_source,
                }
                if excluded:
                    exclusions.append(sel.criterion_id)

    # Critical-source check (Insufficient Data Handling Spec): solar_ghi (the
    # solar resource) is critical. If its whole tree is exhausted, or PVWatts
    # was unobtainable at scoring time, do NOT produce a partial score.
    critical_gaps = selection_critical_gaps(selection, "solar_siting")
    ghi_basis = (criteria_scores.get("solar_ghi") or {}).get("basis") or {}
    if ghi_basis.get("critical_unavailable") and not any(
        g["criterion"] == "solar_ghi" for g in critical_gaps
    ):
        critical_gaps.append(scoring_critical_gap("solar_siting", "solar_ghi"))
    if critical_gaps:
        return enrich_result({
            "module":          MODULE_NAME,
            "module_version":  MODULE_VERSION,
            "query":           {"latitude": latitude, "longitude": longitude},
            "score":           None,
            "rating":          CANNOT_ASSESS,
            "cannot_assess":   True,
            "missing_sources": critical_gaps,
            "message":         critical_gaps[0]["message"],
            "weight_profile":  weight_profile,
            "interconnection_context": interconnection,
            "criteria_scores": criteria_scores,
            "confidence": {
                "tier":      CANNOT_ASSESS,
                "composite": None,
                "statement": cannot_assess_statement(critical_gaps),
                "gaps":      [
                    {"criterion": g["criterion"],
                     "display_name": criterion_name(g["criterion"]),
                     "message": g.get("message") or gap_message(g["criterion"]),
                     "tried": g.get("sources", [])}
                    for g in critical_gaps
                ],
            },
            "methodology":     methodology,
        })

    # Step 4 — composite (weighted scored, exclusion overrides to "Excluded").
    # Flood is excluded from the weighted average and applied as a *deduction*
    # (Exclusion Precision Spec, Step 3): adding it as an averaged term would lift
    # every flood-free site toward 1.0 and compress EIA-vs-random separation. As
    # a penalty it leaves the majority (outside-SFHA) composites untouched.
    valid = [
        (cs["score"], cs["weight"])
        for cid, cs in criteria_scores.items()
        if cid != "excl_flood" and cs["score"] is not None and cs["weight"]
    ]
    if valid:
        num = sum(s * w for s, w in valid)
        den = sum(w for _, w in valid)
        composite = num / den if den > 0 else 0.0
    else:
        composite = 0.0

    # Flood penalty — only A/AE zones (basis.penalty) deduct weight·(1−score);
    # outside-SFHA and unavailable-NFHL sites are unaffected; V zones already
    # hard-excluded above.
    flood_cs = criteria_scores.get("excl_flood")
    if flood_cs is not None:
        flood_cs["applied_as"] = "penalty_deduction"
        deduction = 0.0
        if (flood_cs.get("basis") or {}).get("penalty") and flood_cs["score"] is not None:
            deduction = flood_cs["weight"] * (1.0 - flood_cs["score"])
            composite = max(0.0, composite - deduction)
        # display the actual composite effect (a deduction), not a positive term
        flood_cs["weighted_contribution"] = -round(deduction, 4)

    if exclusions:
        rating = "Excluded"
    elif composite >= 0.70:
        rating = "High"
    elif composite >= 0.40:
        rating = "Moderate"
    else:
        rating = "Low"

    # Step 5 — assemble output.
    return enrich_result({
        "module":          MODULE_NAME,
        "module_version":  MODULE_VERSION,
        "query":           {"latitude": latitude, "longitude": longitude},
        "score":           round(composite, 4),
        "rating":          rating,
        "exclusions":      exclusions,
        "weight_profile":  weight_profile,
        "interconnection_context": interconnection,
        "criteria_scores": criteria_scores,
        "exclusion_results": exclusion_results,
        "confidence": {
            "tier":       selection.confidence_tier,
            "composite":  round(selection.composite_confidence, 4),
            "statement":  selection.confidence_statement,
            "completeness": selection.completeness,
            "gaps":         selection.gaps,
            "strongest_data": selection.strongest_data,
            "weakest_data":   selection.weakest_data,
            "per_criterion": {
                c.criterion_id: {
                    "confidence":      c.confidence,
                    "tier":            c.confidence_tier,
                    "quality_note":    c.quality_note,
                    "selected_source": _selected_source_id(c),
                }
                for c in selection.criteria
            },
        },
        "methodology": methodology,
    })
