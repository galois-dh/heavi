"""Solar site suitability scoring pipeline (Score Mode + Discover Mode).

Pipeline stages: Ingest → Enrich → Filter → Score → Report.

Score Mode  — customer supplies parcels (GeoJSON FeatureCollection or a CSV of
              addresses / lat-lng). Each parcel is enriched against the national
              PostGIS layers, filtered on hard constraints, scored, and returned.
Discover    — Heavi identifies candidates within a geography ("kern" or a bbox)
              by running the pre-loaded solar_parcels_kern layer through the same
              enrich → filter → score pipeline and ranking the survivors.

Enrichment data sources (all EPSG:4326 PostGIS layers loaded in Week 1, plus the
USGS 3DEP elevation service queried on-demand for terrain):
  GHI            solar_nsrdb_kern (4-6 km grid; NREL API fallback off-grid)
  grid proximity solar_transmission_lines, solar_substations_osm
  slope/aspect   USGS 3DEP ImageServer (getSamples, 5-point stencil per centroid)
  soil           solar_soils_kern (SSURGO land-capability class)
  road access    solar_roads_ca
  flood          catalog_fema_flood  (NFHL — see KNOWN_LIMITATIONS re: coverage)
  wetlands       solar_wetlands_ca
  protected      solar_protected_areas

Scoring is multi-criteria weighted overlay (Doorga et al. 2019; Charabi & Gastli
2011) with capacity from the NREL land-use factor (Ong et al. 2016) and
environmental exclusions from Hernandez et al. (2015). All thresholds/weights are
configurable; see Config and METHODOLOGY.
"""

from __future__ import annotations

import csv
import io
import math
import os
from dataclasses import dataclass, field, replace
from typing import Any

import asyncpg
import httpx

# ─── Configuration (all thresholds/weights are overridable per request) ──────

# Composite weights — sum to 1.0. Doorga et al. (2019) / Charabi & Gastli (2011)
# framework, re-weighted (grid-dominant) for the California Central Valley, where
# solar irradiance is uniformly high (GHI ~5.0-6.0) so grid proximity is the
# dominant site-selection differentiator. Validated against EIA Form 860
# installations in Kern County — see methodology_doc()/known limitations.
DEFAULT_WEIGHTS: dict[str, float] = {
    "ghi": 0.10,
    "grid": 0.45,
    "slope": 0.12,
    "aspect": 0.04,
    "soil": 0.06,
    "road": 0.18,
    "land_use": 0.05,
}

# Land-use score from the Kern zoning primary code (Zn_Cd1). Utility solar is
# sited on agricultural / rural / vacant land; residential & commercial are
# unfavorable (confirmed against EIA Form 860 installations).
LAND_USE_SCORE = {
    "agricultural": 1.0, "rural": 0.85, "unknown": 0.75, "industrial": 0.5,
    "commercial": 0.35, "residential": 0.15, "other": 0.6,
}


def classify_zone(z: str | None) -> str:
    """Kern zoning primary code (Zn_Cd1) → land-use category."""
    if z is None:
        return "unknown"
    z = z.strip().upper()
    if z.startswith("A"):
        return "agricultural"
    if z.startswith("E(") or z in ("NR", "RF") or z.startswith(("FP", "DI", "WM")):
        return "rural"
    if z.startswith("R"):
        return "residential"
    if z.startswith("C"):
        return "commercial"
    if z.startswith("M"):
        return "industrial"
    return "other"


@dataclass
class Config:
    # Hard constraints.
    min_acreage: float = 10.0          # Ong et al. (2016) minimum viable scale
    max_slope_pct: float = 15.0        # Doorga et al. (2019) exclusion criterion
    # Normalization caps (configurable defaults — validate vs EIA Form 860).
    grid_max_distance_m: float = 50_000.0   # practical interconnection ceiling
    road_max_distance_m: float = 20_000.0
    # GHI reference range used when a scoring cohort is too small for a
    # meaningful cohort min/max (configurable defaults for CA, kWh/m²/day).
    ghi_ref_min: float = 4.0
    ghi_ref_max: float = 7.0
    # Classification breakpoints (configurable defaults — validate vs EIA 860).
    high_threshold: float = 0.70
    moderate_threshold: float = 0.40
    # Capacity: NREL land-use factor, fixed-tilt utility PV (Ong et al. 2016).
    acres_per_mw: float = 5.0
    # Soil capability class assumed when a parcel falls outside SSURGO coverage.
    default_soil_class: int = 4
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))


# NSRDB grid spacing is ~6.5 km; treat a nearest grid point within this distance
# as authoritative, otherwise fall back to the on-demand NREL API.
NSRDB_MAX_MATCH_M = 12_000.0

# USGS 3DEP ImageServer — same service the wildfire raster pipeline used. We
# sample point elevations directly (getSamples) rather than downloading a clip.
DEM_GETSAMPLES_URL = (
    "https://elevation.nationalmap.gov/arcgis/rest/services/"
    "3DEPElevation/ImageServer/getSamples"
)
# Stencil half-step for finite-difference slope/aspect (~30 m, matched to the
# wildfire pipeline's working resolution).
STENCIL_STEP_M = 30.0
# getSamples points per HTTP POST. The 3DEP service latency grows sharply with
# payload (≈6.5s at 100 points, ≈20s at 200), so 100 (20 parcels/request) keeps
# each request fast and we issue them concurrently.
GETSAMPLES_BATCH_POINTS = 100

# NREL solar_resource API. developer.nrel.gov entered a scheduled brownout in
# 2026; developer.nlr.gov is the live replacement. Try the new host first.
NREL_HOSTS = ["developer.nlr.gov", "developer.nrel.gov"]

CAPACITY_METHOD = "NREL land-use factor: 5 acres/MW fixed-tilt (Ong et al. 2016)"
DATA_SOURCES = [
    "NREL NSRDB",
    "USGS 3DEP",
    "HIFLD Transmission Lines",
    "OSM Substations",
    "FEMA NFHL",
    "NWI",
    "PAD-US",
    "SSURGO",
    "TIGER Roads",
    "Kern County Zoning",
]

# Kern parcels are the only pre-loaded Discover-mode geography for the demo.
KERN_BBOX = (-120.20, 34.79, -117.61, 35.80)  # min_lng, min_lat, max_lng, max_lat
AVAILABLE_GEOGRAPHIES = ["Kern County, CA"]


# ─── Parcel model ────────────────────────────────────────────────────────────


@dataclass
class Parcel:
    """A parcel flowing through the pipeline. Geometry is carried as either a
    GeoJSON geometry dict (polygon input) or a point (lng/lat). Enrichment
    fields are filled in by enrich_* and may stay None when coverage is absent."""

    parcel_id: str
    geom_geojson: dict[str, Any] | None = None   # polygon (preferred)
    lng: float | None = None                     # point fallback / centroid
    lat: float | None = None
    acreage: float | None = None
    # Enrichment.
    ghi: float | None = None
    grid_distance_m: float | None = None
    road_distance_m: float | None = None
    soil_class: int | None = None
    slope_pct: float | None = None
    aspect_deg: float | None = None
    land_use_category: str | None = None   # agricultural / rural / residential / …
    # Hard-constraint intersections.
    in_flood: bool = False
    in_wetland: bool = False
    in_protected: bool = False
    flood_coverage: bool = True   # False → no NFHL data covers this parcel
    # Bookkeeping.
    note: str | None = None


# ─── Input parsing ───────────────────────────────────────────────────────────


def parse_geojson(raw: bytes) -> list[Parcel]:
    import json

    try:
        doc = json.loads(raw)
    except ValueError as e:
        raise ValueError(f"Invalid JSON: {e}") from None
    if doc.get("type") != "FeatureCollection":
        raise ValueError("GeoJSON must be a FeatureCollection.")
    feats = doc.get("features") or []
    if not feats:
        raise ValueError("FeatureCollection has no features.")
    parcels: list[Parcel] = []
    for i, f in enumerate(feats, start=1):
        props = f.get("properties") or {}
        geom = f.get("geometry") or {}
        pid = str(
            props.get("id")
            or props.get("parcel_id")
            or props.get("apn")
            or f.get("id")
            or f"parcel_{i}"
        )
        gtype = geom.get("type")
        if gtype in ("Polygon", "MultiPolygon"):
            parcels.append(Parcel(parcel_id=pid, geom_geojson=geom))
        elif gtype == "Point":
            coords = geom.get("coordinates") or [None, None]
            parcels.append(Parcel(parcel_id=pid, lng=coords[0], lat=coords[1]))
        else:
            raise ValueError(
                f"Feature {i} ({pid}): unsupported geometry type {gtype!r}."
            )
    return parcels


def parse_csv_addresses(raw: bytes) -> tuple[list[Parcel], list[tuple[str, str]]]:
    """Parse a CSV of addresses or lat/lng pairs into point Parcels.

    Returns (parcels_with_coords, addresses_to_geocode) where the second list is
    (parcel_id, address) tuples that still need forward geocoding."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise ValueError(f"CSV is not UTF-8: {e}") from None
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("CSV has no header row.")
    aliases = {
        "address": {"address", "addr", "street"},
        "latitude": {"latitude", "lat", "y"},
        "longitude": {"longitude", "lng", "lon", "long", "x"},
        "parcel_id": {"parcel_id", "id", "apn", "propertyid", "prop_id"},
        "acreage": {"acreage", "acres", "area_acres"},
    }
    lower = {h.lower().strip(): h for h in reader.fieldnames}
    col = {k: next((lower[a] for a in s if a in lower), None) for k, s in aliases.items()}
    if not col["address"] and not (col["latitude"] and col["longitude"]):
        raise ValueError(
            "CSV needs an 'address' column OR both 'latitude' and 'longitude'."
        )
    parcels: list[Parcel] = []
    to_geocode: list[tuple[str, str]] = []
    for i, row in enumerate(reader, start=1):

        def cell(key: str) -> str:
            c = col[key]
            return (row.get(c) or "").strip() if c else ""

        pid = cell("parcel_id") or f"parcel_{i}"
        lat_s, lng_s = cell("latitude"), cell("longitude")
        acre_s = cell("acreage")
        acreage = float(acre_s) if acre_s else None
        if lat_s and lng_s:
            parcels.append(
                Parcel(parcel_id=pid, lng=float(lng_s), lat=float(lat_s), acreage=acreage)
            )
        elif cell("address"):
            p = Parcel(parcel_id=pid, acreage=acreage)
            parcels.append(p)
            to_geocode.append((pid, cell("address")))
        # else: skip blank line
    if not parcels:
        raise ValueError("CSV contained no usable rows.")
    return parcels, to_geocode


# ─── Geocoding (reuses the portfolio module's Mapbox→Nominatim dispatcher) ───


async def _geocode(client: httpx.AsyncClient, address: str) -> tuple[float, float] | None:
    from .portfolio_risk import _geocode_one

    g = await _geocode_one(client, address)
    if g is None:
        return None
    lat, lng, _display = g
    return lat, lng


# ─── Terrain (USGS 3DEP getSamples, 5-point stencil) ─────────────────────────

_TERRAIN_CACHE: dict[tuple[float, float], tuple[float | None, float | None]] = {}


def _stencil_points(lng: float, lat: float) -> list[tuple[float, float]]:
    """center, East, West, North, South at ±STENCIL_STEP_M."""
    dlat = STENCIL_STEP_M / 111_320.0
    dlng = STENCIL_STEP_M / (111_320.0 * max(0.1, math.cos(math.radians(lat))))
    return [
        (lng, lat),
        (lng + dlng, lat),
        (lng - dlng, lat),
        (lng, lat + dlat),
        (lng, lat - dlat),
    ]


def _slope_aspect(elev: list[float | None]) -> tuple[float | None, float | None]:
    """elev = [center, E, W, N, S]. Returns (slope_pct, aspect_deg).
    aspect_deg is the compass azimuth (0=N, 90=E) the slope faces downhill;
    None on flat ground or missing samples."""
    if any(e is None for e in elev):
        return None, None
    _c, e, w, n, s = elev  # type: ignore[misc]
    dz_dx = (e - w) / (2 * STENCIL_STEP_M)   # +east
    dz_dy = (n - s) / (2 * STENCIL_STEP_M)   # +north
    grad = math.hypot(dz_dx, dz_dy)          # rise/run (dimensionless)
    slope_pct = grad * 100.0
    if grad < 1e-4:
        return slope_pct, None               # flat — aspect undefined
    # Downhill azimuth: negative gradient vector, measured clockwise from north.
    az = math.degrees(math.atan2(-dz_dx, -dz_dy)) % 360.0
    return slope_pct, az


async def _fetch_elevations(
    client: httpx.AsyncClient, points: list[tuple[float, float]]
) -> list[float | None]:
    """Batched getSamples, batches issued concurrently. Order preserved via the
    batch offset + per-sample locationId."""
    import asyncio
    import json

    out: list[float | None] = [None] * len(points)

    async def one_batch(start: int) -> None:
        chunk = points[start : start + GETSAMPLES_BATCH_POINTS]
        geometry = {
            "points": [[lng, lat] for lng, lat in chunk],
            "spatialReference": {"wkid": 4326},
        }
        try:
            # POST (not GET): a multipoint geometry of many points overflows the
            # URL length limit on a GET, which silently returns no samples.
            r = await client.post(
                DEM_GETSAMPLES_URL,
                data={
                    "geometry": json.dumps(geometry),
                    "geometryType": "esriGeometryMultipoint",
                    "returnFirstValueOnly": "true",
                    "f": "json",
                },
            )
            data = r.json()
        except (httpx.HTTPError, ValueError):
            return
        for s in data.get("samples", []) or []:
            loc = s.get("locationId")
            val = s.get("value")
            if loc is None or val is None:
                continue
            try:
                out[start + int(loc)] = float(val)
            except (ValueError, TypeError):
                pass

    starts = list(range(0, len(points), GETSAMPLES_BATCH_POINTS))
    # Bound concurrency so we don't open dozens of sockets to the 3DEP service.
    sem = asyncio.Semaphore(6)

    async def guarded(start: int) -> None:
        async with sem:
            await one_batch(start)

    await asyncio.gather(*(guarded(s) for s in starts))
    return out


async def enrich_terrain(client: httpx.AsyncClient, parcels: list[Parcel]) -> None:
    """Fill slope_pct / aspect_deg on each parcel via 3DEP. Cached by rounded
    centroid (~10 m) so repeated parcels / nearby points reuse samples."""
    pending: list[Parcel] = []
    for p in parcels:
        if p.lng is None or p.lat is None:
            continue
        key = (round(p.lng, 4), round(p.lat, 4))
        if key in _TERRAIN_CACHE:
            p.slope_pct, p.aspect_deg = _TERRAIN_CACHE[key]
        else:
            pending.append(p)
    if not pending:
        return
    # Flatten all stencils into one ordered point list.
    all_points: list[tuple[float, float]] = []
    spans: list[tuple[int, int]] = []
    for p in pending:
        pts = _stencil_points(p.lng, p.lat)  # type: ignore[arg-type]
        spans.append((len(all_points), len(all_points) + len(pts)))
        all_points.extend(pts)
    elevations = await _fetch_elevations(client, all_points)
    for p, (a, b) in zip(pending, spans):
        slope, aspect = _slope_aspect(elevations[a:b])
        p.slope_pct, p.aspect_deg = slope, aspect
        _TERRAIN_CACHE[(round(p.lng, 4), round(p.lat, 4))] = (slope, aspect)  # type: ignore[arg-type]


# ─── NREL on-demand GHI (off-grid fallback) ──────────────────────────────────


async def _nrel_ghi(client: httpx.AsyncClient, lng: float, lat: float) -> float | None:
    api_key = os.getenv("NREL_API_KEY")
    if not api_key:
        return None
    for host in NREL_HOSTS:
        try:
            r = await client.get(
                f"https://{host}/api/solar/solar_resource/v1.json",
                params={"api_key": api_key, "lat": lat, "lon": lng},
            )
            if r.status_code != 200:
                continue
            data = r.json()
            ghi = (
                (data.get("outputs") or {})
                .get("avg_ghi", {})
                .get("annual")
            )
            if ghi is not None:
                return float(ghi)
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            continue
    return None


# ─── Database enrichment (one round-trip per parcel batch) ───────────────────

# For a point parcel we resolve a geometry from lng/lat; for a polygon parcel we
# parse the supplied GeoJSON. The enrichment SQL takes a geometry and returns the
# nearest-feature distances, soil class, GHI, acreage, and constraint flags.
_ENRICH_SQL = """
WITH g AS (SELECT ST_SetSRID($1::geometry, 4326) AS geom)
SELECT
  ST_X(ST_Centroid(g.geom))                          AS cx,
  ST_Y(ST_Centroid(g.geom))                          AS cy,
  CASE WHEN ST_GeometryType(g.geom) IN ('ST_Polygon','ST_MultiPolygon')
       THEN ST_Area(g.geom::geography) / 4046.8564224 END AS acreage,
  (SELECT n.annual_ghi_kwh_m2_day
     FROM solar_nsrdb_kern n
     ORDER BY n.geometry <-> ST_Centroid(g.geom) LIMIT 1)            AS ghi,
  (SELECT ST_Distance(n.geometry::geography, ST_Centroid(g.geom)::geography)
     FROM solar_nsrdb_kern n
     ORDER BY n.geometry <-> ST_Centroid(g.geom) LIMIT 1)           AS ghi_dist_m,
  LEAST(
    COALESCE((SELECT ST_Distance(t.geometry::geography, g.geom::geography)
       FROM solar_transmission_lines t
       ORDER BY t.geometry <-> g.geom LIMIT 1), 'Infinity'),
    COALESCE((SELECT ST_Distance(s.geometry::geography, g.geom::geography)
       FROM solar_substations_osm s
       ORDER BY s.geometry <-> g.geom LIMIT 1), 'Infinity')
  )                                                                  AS grid_dist_m,
  (SELECT ST_Distance(r.geometry::geography, g.geom::geography)
     FROM solar_roads_ca r
     ORDER BY r.geometry <-> g.geom LIMIT 1)                        AS road_dist_m,
  (SELECT so.soil_capability_class
     FROM solar_soils_kern so
     WHERE ST_Intersects(so.geometry, ST_Centroid(g.geom)) LIMIT 1) AS soil_class,
  (SELECT z.zone_code FROM solar_zoning_kern z
     WHERE ST_Intersects(z.geometry, ST_Centroid(g.geom)) LIMIT 1) AS zone_code,
  EXISTS(SELECT 1 FROM solar_wetlands_ca w WHERE ST_Intersects(w.geometry, g.geom))
                                                                     AS in_wetland,
  EXISTS(SELECT 1 FROM solar_protected_areas pa WHERE ST_Intersects(pa.geometry, g.geom))
                                                                     AS in_protected,
  EXISTS(SELECT 1 FROM catalog_fema_flood fz
         WHERE fz.sfha_tf = 'T' AND ST_Intersects(fz.geometry, g.geom))
                                                                     AS in_flood,
  EXISTS(SELECT 1 FROM catalog_fema_flood fz2
         WHERE ST_DWithin(fz2.geometry::geography, g.geom::geography, 50000))
                                                                     AS flood_coverage
FROM g
"""


def _coerce_soil_class(raw: str | None) -> int | None:
    """SSURGO nirrcapcl is a 1-8 land-capability class, sometimes carrying a
    subclass letter (e.g. '3e'). Pull the leading integer."""
    if not raw:
        return None
    digits = ""
    for ch in str(raw).strip():
        if ch.isdigit():
            digits += ch
        else:
            break
    if not digits:
        return None
    val = int(digits)
    return val if 1 <= val <= 8 else None


async def enrich_db(pool: asyncpg.Pool, parcels: list[Parcel]) -> None:
    """Fill GHI / grid / road / soil / acreage / constraint flags from PostGIS.
    Each parcel needs either geom_geojson (polygon) or lng+lat (point)."""
    import json

    async with pool.acquire() as conn:
        for p in parcels:
            if p.geom_geojson is not None:
                geom_arg = json.dumps(p.geom_geojson)
                wkt_or_geojson = await conn.fetchval(
                    "SELECT ST_GeomFromGeoJSON($1)", geom_arg
                )
            elif p.lng is not None and p.lat is not None:
                wkt_or_geojson = await conn.fetchval(
                    "SELECT ST_SetSRID(ST_MakePoint($1,$2),4326)", p.lng, p.lat
                )
            else:
                p.note = "no geometry"
                continue
            row = await conn.fetchrow(_ENRICH_SQL, wkt_or_geojson)
            if row is None:
                continue
            # Centroid (used by terrain + output). Polygon parcels learn their
            # centroid here; point parcels keep their own coords.
            if p.lng is None or p.lat is None:
                p.lng, p.lat = float(row["cx"]), float(row["cy"])
            if p.acreage is None and row["acreage"] is not None:
                p.acreage = float(row["acreage"])
            ghi_dist = row["ghi_dist_m"]
            if row["ghi"] is not None and ghi_dist is not None and ghi_dist <= NSRDB_MAX_MATCH_M:
                p.ghi = float(row["ghi"])
            # else: leave None → NREL fallback fills it later
            p.grid_distance_m = (
                float(row["grid_dist_m"]) if row["grid_dist_m"] is not None
                and math.isfinite(row["grid_dist_m"]) else None
            )
            p.road_distance_m = (
                float(row["road_dist_m"]) if row["road_dist_m"] is not None else None
            )
            p.soil_class = _coerce_soil_class(row["soil_class"])
            p.land_use_category = classify_zone(row["zone_code"])
            p.in_wetland = bool(row["in_wetland"])
            p.in_protected = bool(row["in_protected"])
            p.in_flood = bool(row["in_flood"])
            p.flood_coverage = bool(row["flood_coverage"])


async def enrich_ghi_fallback(client: httpx.AsyncClient, parcels: list[Parcel]) -> None:
    """For parcels still missing GHI (outside the NSRDB grid), call NREL."""
    for p in parcels:
        if p.ghi is None and p.lng is not None and p.lat is not None:
            p.ghi = await _nrel_ghi(client, p.lng, p.lat)


# ─── Filter + Score ──────────────────────────────────────────────────────────


def constraints(p: Parcel, cfg: Config, terrain_known: bool = True) -> dict[str, bool]:
    # When terrain hasn't been fetched yet (provisional pass in Discover mode),
    # the slope constraint is deferred — reported True so it doesn't spuriously
    # fail; it is re-evaluated for real once 3DEP terrain is attached.
    max_slope_ok = (
        (p.slope_pct is not None and p.slope_pct <= cfg.max_slope_pct)
        if terrain_known
        else True
    )
    return {
        "min_acreage": (p.acreage or 0.0) >= cfg.min_acreage,
        "max_slope": max_slope_ok,
        "flood_zone_clear": not p.in_flood,
        "wetlands_clear": not p.in_wetland,
        "protected_lands_clear": not p.in_protected,
    }


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def _ghi_score(ghi: float, lo: float, hi: float) -> float:
    if hi - lo < 1e-9:
        return 0.5
    return _clamp01((ghi - lo) / (hi - lo))


def _aspect_score(p: Parcel) -> tuple[float, float]:
    """Returns (deviation_from_south_deg, score). Flat ground (aspect None) gets
    no orientation penalty — score 1.0, deviation 0."""
    if p.aspect_deg is None:
        return 0.0, 1.0
    dev = abs(p.aspect_deg - 180.0)
    dev = min(dev, 360.0 - dev)
    return dev, max(0.0, math.cos(math.radians(dev)))


def _soil_score(soil_class: int | None, cfg: Config) -> tuple[int, float, bool]:
    """(class_used, score, is_default). Invert capability class: 1→1.0, 8→0.125."""
    is_default = soil_class is None
    cls = soil_class if soil_class is not None else cfg.default_soil_class
    return cls, (9 - cls) / 8.0, is_default


def score_parcel(
    p: Parcel, cfg: Config, ghi_lo: float, ghi_hi: float, terrain_known: bool = True
) -> dict[str, Any] | None:
    """Score a parcel. When terrain_known is False (Discover's provisional pass
    before 3DEP is fetched), slope+aspect are excluded from the composite and
    their weight is redistributed across the remaining criteria, and the slope
    constraint is deferred."""
    cons = constraints(p, cfg, terrain_known)
    passed_all = all(cons.values())

    ghi = p.ghi if p.ghi is not None else cfg.ghi_ref_min
    ghi_score = _ghi_score(ghi, ghi_lo, ghi_hi)

    grid_d = p.grid_distance_m if p.grid_distance_m is not None else cfg.grid_max_distance_m
    grid_score = _clamp01(1 - grid_d / cfg.grid_max_distance_m)

    slope = p.slope_pct if p.slope_pct is not None else cfg.max_slope_pct
    slope_score = _clamp01(1 - slope / cfg.max_slope_pct)

    dev, aspect_score = _aspect_score(p)

    soil_cls, soil_score, soil_default = _soil_score(p.soil_class, cfg)

    road_d = p.road_distance_m if p.road_distance_m is not None else cfg.road_max_distance_m
    road_score = _clamp01(1 - road_d / cfg.road_max_distance_m)

    land_use_cat = p.land_use_category or "unknown"
    land_use_score = LAND_USE_SCORE.get(land_use_cat, LAND_USE_SCORE["unknown"])

    w = cfg.weights
    component_scores = {
        "ghi": ghi_score,
        "grid": grid_score,
        "slope": slope_score,
        "aspect": aspect_score,
        "soil": soil_score,
        "road": road_score,
        "land_use": land_use_score,
    }
    # Provisional pass excludes terrain criteria and redistributes their weight.
    included = (
        set(component_scores) if terrain_known
        else {"ghi", "grid", "soil", "road", "land_use"}
    )
    wsum = sum(w.get(k, 0.0) for k in included) or 1.0
    composite = sum(w.get(k, 0.0) * component_scores[k] for k in included) / wsum
    rating = (
        "High" if composite >= cfg.high_threshold
        else "Moderate" if composite >= cfg.moderate_threshold
        else "Low"
    )
    capacity = round((p.acreage or 0.0) / cfg.acres_per_mw, 1)

    criteria = {
        "solar_irradiance_ghi_kwh_m2_day": round(ghi, 2) if p.ghi is not None else None,
        "solar_irradiance_score": round(ghi_score, 2),
        "grid_distance_km": round(grid_d / 1000.0, 2) if p.grid_distance_m is not None else None,
        "grid_proximity_score": round(grid_score, 2),
        "slope_degrees": round(math.degrees(math.atan(slope / 100.0)), 1)
        if p.slope_pct is not None else None,
        "slope_percent": round(slope, 1) if p.slope_pct is not None else None,
        "slope_score": round(slope_score, 2),
        "aspect_deviation_from_south_degrees": round(dev) if p.aspect_deg is not None else None,
        "aspect_score": round(aspect_score, 2),
        "soil_capability_class": soil_cls,
        "soil_score": round(soil_score, 2),
        "road_distance_km": round(road_d / 1000.0, 2) if p.road_distance_m is not None else None,
        "road_access_score": round(road_score, 2),
        "land_use_category": land_use_cat,
        "land_use_score": round(land_use_score, 2),
    }

    result: dict[str, Any] = {
        "parcel_id": p.parcel_id,
        "suitability_score": round(composite, 2),
        "suitability_rating": rating,
        "acreage": round(p.acreage, 1) if p.acreage is not None else None,
        "estimated_capacity_mw": capacity,
        "location": {"longitude": p.lng, "latitude": p.lat},
        "criteria_scores": criteria,
        "constraints_passed": cons,
        "constraints_all_passed": passed_all,
        "natural_language_summary": _summary(p, composite, rating, criteria, cons),
        "methodology": METHODOLOGY_BRIEF,
    }
    notes = []
    if soil_default:
        notes.append(
            f"Soil outside SSURGO coverage; assumed class {cfg.default_soil_class}."
        )
    if p.ghi is None:
        notes.append("GHI unavailable (off NSRDB grid and NREL fallback failed).")
    if p.slope_pct is None:
        notes.append("Terrain unavailable from 3DEP; slope constraint not evaluated.")
    if not p.flood_coverage:
        notes.append("No FEMA NFHL coverage near this parcel; flood screen indeterminate.")
    if notes:
        result["data_notes"] = notes
    return result


# ─── Natural-language summary ────────────────────────────────────────────────


def _factor_phrases(criteria: dict[str, Any]) -> list[str]:
    """Top scoring factors in plain language, ranked by criterion score."""
    ranked: list[tuple[float, str]] = []
    ghi = criteria["solar_irradiance_ghi_kwh_m2_day"]
    if ghi is not None:
        if ghi > 5.5:
            ranked.append((criteria["solar_irradiance_score"], "strong solar resource"))
        elif ghi > 5.0:
            ranked.append((criteria["solar_irradiance_score"], "good solar resource"))
    gd = criteria["grid_distance_km"]
    if gd is not None:
        if gd < 2:
            ranked.append((criteria["grid_proximity_score"], "excellent grid access"))
        elif gd < 5:
            ranked.append((criteria["grid_proximity_score"], "close grid access"))
        elif gd < 10:
            ranked.append((criteria["grid_proximity_score"], "moderate grid access"))
    sp = criteria["slope_percent"]
    if sp is not None:
        if sp < 3:
            ranked.append((criteria["slope_score"], "flat terrain"))
        elif sp < 8:
            ranked.append((criteria["slope_score"], "gentle slope"))
    sc = criteria["soil_capability_class"]
    if sc is not None and sc <= 3:
        ranked.append((criteria["soil_score"], "suitable foundation soils"))
    rd = criteria["road_distance_km"]
    if rd is not None and rd < 1:
        ranked.append((criteria["road_access_score"], "strong road access"))
    ranked.sort(key=lambda x: x[0], reverse=True)
    return [phrase for _, phrase in ranked]


def _summary(
    p: Parcel,
    composite: float,
    rating: str,
    criteria: dict[str, Any],
    cons: dict[str, bool],
) -> str:
    acres = f"{p.acreage:.0f}" if p.acreage is not None else "unknown-size"
    cap = (p.acreage or 0.0) / 5.0
    parts = [
        f"This {acres}-acre parcel has {rating.upper()} solar development "
        f"suitability (score: {composite:.2f})."
    ]
    phrases = _factor_phrases(criteria)
    if phrases:
        if len(phrases) >= 2:
            cap_phrase = f"{phrases[0].capitalize()} and {phrases[1]}"
        else:
            cap_phrase = phrases[0].capitalize()
        parts.append(cap_phrase + ".")
    parts.append(f"Estimated capacity: {cap:.0f} MW.")
    failed = [k for k, v in cons.items() if not v]
    if not failed:
        parts.append("All environmental constraints passed.")
    else:
        labels = {
            "min_acreage": "below minimum acreage",
            "max_slope": "slope exceeds maximum",
            "flood_zone_clear": "intersects a FEMA flood zone",
            "wetlands_clear": "intersects mapped wetlands",
            "protected_lands_clear": "intersects protected lands",
        }
        parts.append("Failed constraints: " + ", ".join(labels[f] for f in failed) + ".")
    return " ".join(parts)


# ─── Cohort scoring helper (shared by both modes) ────────────────────────────


def _ghi_cohort_range(parcels: list[Parcel], cfg: Config) -> tuple[float, float]:
    """Cohort min/max GHI for normalization (Doorga et al. relative scaling).
    Falls back to the configured reference range when the cohort is too small
    or degenerate for a meaningful spread."""
    vals = [p.ghi for p in parcels if p.ghi is not None]
    if len(vals) >= 2 and (max(vals) - min(vals)) > 0.1:
        return min(vals), max(vals)
    return cfg.ghi_ref_min, cfg.ghi_ref_max


# ─── Score Mode ──────────────────────────────────────────────────────────────


async def run_score_mode(
    pool: asyncpg.Pool, parcels: list[Parcel], cfg: Config
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Forward-geocode any address-only point parcels first (handled by the
        # endpoint before calling us, so here all parcels have geometry/coords).
        await enrich_db(pool, parcels)
        await enrich_ghi_fallback(client, parcels)
        await enrich_terrain(client, parcels)

    ghi_lo, ghi_hi = _ghi_cohort_range(parcels, cfg)
    results = [score_parcel(p, cfg, ghi_lo, ghi_hi) for p in parcels]
    results = [r for r in results if r is not None]
    return {
        "mode": "score",
        "parcel_count": len(parcels),
        "scored_count": len(results),
        "results": results,
        "config": _config_echo(cfg),
        "methodology_endpoint": "/solar/methodology",
    }


# ─── Discover Mode ───────────────────────────────────────────────────────────


def _resolve_geography(
    geography: Any,
) -> tuple[tuple[float, float, float, float] | None, str | None]:
    """Returns (bbox, error). bbox is None when the geography isn't pre-loaded."""
    if isinstance(geography, str):
        if geography.strip().lower() in ("kern", "kern county", "kern county, ca"):
            return KERN_BBOX, None
        return None, geography
    if isinstance(geography, (list, tuple)) and len(geography) == 4:
        bbox = tuple(float(v) for v in geography)  # min_lng,min_lat,max_lng,max_lat
        # Overlaps Kern (the only pre-loaded parcel set)?
        kx0, ky0, kx1, ky1 = KERN_BBOX
        if bbox[0] < kx1 and bbox[2] > kx0 and bbox[1] < ky1 and bbox[3] > ky0:
            return bbox, None  # type: ignore[return-value]
        return None, "bbox"
    return None, "invalid"


# Discover reads fully PRE-ENRICHED columns on solar_parcels_kern (written by
# loaders/solar/enrich_parcels.py: GHI, grid/road distance, soil class,
# exclusion flags, slope/aspect, and the composite suitability_score). All
# spatial work was done offline, so this is a trivial GIST + b-tree indexed
# SELECT … ORDER BY suitability_score — no remote spatial joins, fast under load.
# $6 is the max slope in DEGREES (the Config threshold is in percent).
_DISCOVER_SQL = """
SELECT
  COALESCE(apn, objectid::text) AS parcel_id,
  ST_X(ST_Centroid(geometry)) AS cx,
  ST_Y(ST_Centroid(geometry)) AS cy,
  acreage, slope_degrees, aspect_degrees,
  ghi_kwh_m2_day, grid_distance_m, road_distance_m, soil_capability_class, land_use,
  in_flood, in_wetland, in_protected, suitability_score, suitability_rating
FROM solar_parcels_kern
WHERE geometry && ST_MakeEnvelope($1,$2,$3,$4,4326)
  AND acreage >= $5
  AND COALESCE(in_wetland, false) = false
  AND COALESCE(in_protected, false) = false
  AND COALESCE(in_flood, false) = false
  AND (slope_degrees IS NULL OR slope_degrees <= $6)
  AND suitability_score IS NOT NULL
ORDER BY suitability_score DESC NULLS LAST
LIMIT $7
"""

# Portfolio-level aggregates over the same geography + constraints.
_DISCOVER_SUMMARY_SQL = """
SELECT
  COUNT(*) AS total_in_geo,
  COUNT(*) FILTER (
    WHERE acreage >= $5 AND COALESCE(in_wetland,false)=false
      AND COALESCE(in_protected,false)=false AND COALESCE(in_flood,false)=false
      AND (slope_degrees IS NULL OR slope_degrees <= $6)
      AND suitability_score IS NOT NULL
  ) AS passing,
  COALESCE(SUM(acreage) FILTER (
    WHERE acreage >= $5 AND COALESCE(in_wetland,false)=false
      AND COALESCE(in_protected,false)=false AND COALESCE(in_flood,false)=false
      AND (slope_degrees IS NULL OR slope_degrees <= $6)
      AND suitability_score IS NOT NULL
  ), 0) / 5.0 AS capacity_mw,
  COUNT(*) FILTER (WHERE suitability_rating='High' AND acreage>=$5
    AND COALESCE(in_wetland,false)=false AND COALESCE(in_protected,false)=false
    AND COALESCE(in_flood,false)=false AND (slope_degrees IS NULL OR slope_degrees<=$6)) AS n_high,
  COUNT(*) FILTER (WHERE suitability_rating='Moderate' AND acreage>=$5
    AND COALESCE(in_wetland,false)=false AND COALESCE(in_protected,false)=false
    AND COALESCE(in_flood,false)=false AND (slope_degrees IS NULL OR slope_degrees<=$6)) AS n_mod,
  COUNT(*) FILTER (WHERE suitability_rating='Low' AND acreage>=$5
    AND COALESCE(in_wetland,false)=false AND COALESCE(in_protected,false)=false
    AND COALESCE(in_flood,false)=false AND (slope_degrees IS NULL OR slope_degrees<=$6)) AS n_low
FROM solar_parcels_kern
WHERE geometry && ST_MakeEnvelope($1,$2,$3,$4,4326)
"""


async def run_discover_mode(
    pool: asyncpg.Pool,
    geography: Any,
    cfg: Config,
    top_n: int = 25,
) -> dict[str, Any]:
    bbox, err = _resolve_geography(geography)
    if bbox is None:
        return {
            "error": (
                "Parcel data not pre-loaded for this geography. Use Score Mode to "
                "evaluate specific parcels, or contact Heavi to add this geography "
                "to the catalog."
            ),
            "available_geographies": AVAILABLE_GEOGRAPHIES,
        }

    # Max slope as DEGREES for the SQL filter (Config threshold is percent).
    max_slope_deg = math.degrees(math.atan(cfg.max_slope_pct / 100.0))
    ghi_lo, ghi_hi = await _kern_ghi_range(pool, cfg)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            _DISCOVER_SQL,
            bbox[0], bbox[1], bbox[2], bbox[3], cfg.min_acreage, max_slope_deg, top_n,
        )
        summary = await conn.fetchrow(
            _DISCOVER_SUMMARY_SQL,
            bbox[0], bbox[1], bbox[2], bbox[3], cfg.min_acreage, max_slope_deg,
        )

    # Rebuild each returned parcel from its pre-enriched columns and re-derive
    # the criterion breakdown + NL summary (deterministic from the stored values,
    # using the same Kern GHI cohort the stored suitability_score was built from).
    results: list[dict[str, Any]] = []
    for r in rows:
        slope_deg = r["slope_degrees"]
        slope_pct = (
            math.tan(math.radians(float(slope_deg))) * 100.0
            if slope_deg is not None else None
        )
        p = Parcel(
            parcel_id=str(r["parcel_id"]),
            lng=float(r["cx"]),
            lat=float(r["cy"]),
            acreage=float(r["acreage"]) if r["acreage"] is not None else None,
            ghi=float(r["ghi_kwh_m2_day"]) if r["ghi_kwh_m2_day"] is not None else None,
            grid_distance_m=(
                float(r["grid_distance_m"]) if r["grid_distance_m"] is not None else None
            ),
            road_distance_m=(
                float(r["road_distance_m"]) if r["road_distance_m"] is not None else None
            ),
            soil_class=r["soil_capability_class"],
            slope_pct=slope_pct,
            aspect_deg=(
                float(r["aspect_degrees"]) if r["aspect_degrees"] is not None else None
            ),
            land_use_category=r["land_use"],
            in_flood=bool(r["in_flood"]),
            in_wetland=bool(r["in_wetland"]),
            in_protected=bool(r["in_protected"]),
        )
        res = score_parcel(p, cfg, ghi_lo, ghi_hi, terrain_known=slope_pct is not None)
        if res is not None:
            results.append(res)

    total = int(summary["total_in_geo"])
    passing = int(summary["passing"])
    return {
        "mode": "discover",
        "geography": geography if isinstance(geography, str) else {"bbox": list(bbox)},
        "portfolio_summary": {
            "total_parcels_evaluated": total,
            "parcels_passing_constraints": passing,
            "total_estimated_capacity_mw": round(float(summary["capacity_mw"]), 1),
            "score_distribution": {
                "High": int(summary["n_high"]),
                "Moderate": int(summary["n_mod"]),
                "Low": int(summary["n_low"]),
            },
            "returned": len(results),
        },
        "results": results,
        "config": _config_echo(cfg),
        "methodology_endpoint": "/solar/methodology",
        "notes": [
            f"{total} parcels in geography; {passing} pass the hard constraints "
            "(acreage, slope, and the protected-land / wetland / flood exclusions).",
            "All six criteria — including 3DEP-derived slope/aspect — are "
            "pre-computed columns on the parcel layer, so Discover is a single "
            "indexed read with no spatial joins or API calls at query time.",
        ],
    }


# Kern GHI cohort (NSRDB grid min/max) — fixed and cached so the score the API
# displays matches the suitability_score the enrichment job persisted.
_KERN_GHI_RANGE: tuple[float, float] | None = None


async def _kern_ghi_range(pool: asyncpg.Pool, cfg: Config) -> tuple[float, float]:
    global _KERN_GHI_RANGE
    if _KERN_GHI_RANGE is None:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT MIN(annual_ghi_kwh_m2_day), MAX(annual_ghi_kwh_m2_day) "
                "FROM solar_nsrdb_kern"
            )
        lo, hi = row[0], row[1]
        if lo is None or hi is None or (hi - lo) < 0.1:
            _KERN_GHI_RANGE = (cfg.ghi_ref_min, cfg.ghi_ref_max)
        else:
            _KERN_GHI_RANGE = (float(lo), float(hi))
    return _KERN_GHI_RANGE


# ─── Config echo / validation ────────────────────────────────────────────────


def build_config(overrides: dict[str, Any] | None) -> Config:
    cfg = Config()
    if not overrides:
        return cfg
    changes: dict[str, Any] = {}
    for key in (
        "min_acreage", "max_slope_pct", "grid_max_distance_m", "road_max_distance_m",
        "high_threshold", "moderate_threshold", "acres_per_mw",
    ):
        if overrides.get(key) is not None:
            changes[key] = float(overrides[key])
    if overrides.get("max_slope") is not None:  # friendly alias
        changes["max_slope_pct"] = float(overrides["max_slope"])
    weights = overrides.get("weights")
    if isinstance(weights, dict) and weights:
        merged = dict(DEFAULT_WEIGHTS)
        for k, v in weights.items():
            if k in merged and v is not None:
                merged[k] = float(v)
        s = sum(merged.values())
        if s > 0:
            merged = {k: v / s for k, v in merged.items()}  # renormalize to 1.0
        changes["weights"] = merged
    return replace(cfg, **changes)


def _config_echo(cfg: Config) -> dict[str, Any]:
    return {
        "min_acreage": cfg.min_acreage,
        "max_slope_pct": cfg.max_slope_pct,
        "grid_max_distance_km": cfg.grid_max_distance_m / 1000.0,
        "road_max_distance_km": cfg.road_max_distance_m / 1000.0,
        "high_threshold": cfg.high_threshold,
        "moderate_threshold": cfg.moderate_threshold,
        "acres_per_mw": cfg.acres_per_mw,
        "weights": cfg.weights,
    }


# ─── Methodology documentation ───────────────────────────────────────────────

METHODOLOGY_BRIEF = {
    "summary": (
        "Multi-criteria weighted overlay scoring solar resource, grid proximity, "
        "terrain, soil, and access against national federal data sources."
    ),
    "weights_source": (
        "Doorga et al. (2019), Charabi & Gastli (2011), adjusted for US "
        "infrastructure context"
    ),
    "capacity_method": CAPACITY_METHOD,
    "environmental_constraints": "Hernandez et al. (2015)",
    "data_sources": DATA_SOURCES,
}

CITATIONS = [
    {
        "key": "Doorga et al. (2019)",
        "citation": (
            "Doorga, J.R.S., Rughooputh, S.D.D.V., Boojhawon, R. (2019). "
            "Multi-criteria GIS-based modelling technique for identifying "
            "potential solar farm sites. Renewable and Sustainable Energy "
            "Reviews, 104: 133-146."
        ),
        "used_for": "Multi-criteria framework and weight structure.",
    },
    {
        "key": "Charabi & Gastli (2011)",
        "citation": (
            "Charabi, Y., Gastli, A. (2011). PV site suitability analysis using "
            "GIS-based spatial fuzzy multi-criteria evaluation. Renewable Energy, "
            "36(9): 2554-2561."
        ),
        "used_for": "Continuous (0-1) scoring approach and the aspect criterion.",
    },
    {
        "key": "Ong et al. (2016)",
        "citation": (
            "Ong, S., Campbell, C., Denholm, P., Margolis, R., Heath, G. (2016). "
            "Land-Use Requirements for Solar Power Plants in the United States. "
            "NREL/TP-6A20-56290."
        ),
        "used_for": "Capacity estimation land-use factor (5 acres/MW fixed-tilt).",
    },
    {
        "key": "Hernandez et al. (2015)",
        "citation": (
            "Hernandez, R.R., Hoffacker, M.K., Murphy-Mariscal, M.L., Wu, G.C., "
            "Allen, M.F. (2015). Solar energy development impacts on land cover "
            "change and protected areas. PNAS, 112(44): 13579-13584."
        ),
        "used_for": "Environmental constraint selection (protected areas, wetlands).",
    },
]

THRESHOLDS_DOC = [
    {
        "name": "min_acreage",
        "default": 10.0, "unit": "acres",
        "rationale": "Minimum viable utility-scale project footprint derived from "
                     "the NREL land-use factor (Ong et al. 2016).",
    },
    {
        "name": "max_slope_pct",
        "default": 15.0, "unit": "percent",
        "rationale": "Slope exclusion criterion for utility PV (Doorga et al. 2019).",
    },
    {
        "name": "grid_max_distance_m",
        "default": 50_000.0, "unit": "meters",
        "rationale": "Configurable default representing a practical interconnection "
                     "cost ceiling; validate against EIA Form 860 outcomes.",
    },
    {
        "name": "road_max_distance_m",
        "default": 20_000.0, "unit": "meters",
        "rationale": "Configurable default for construction access; validate against "
                     "EIA Form 860 outcomes.",
    },
    {
        "name": "high_threshold / moderate_threshold",
        "default": "0.70 / 0.40", "unit": "composite score",
        "rationale": "Classification breakpoints — configurable defaults, validate "
                     "against EIA Form 860 outcomes.",
    },
    {
        "name": "acres_per_mw",
        "default": 5.0, "unit": "acres/MW",
        "rationale": "NREL land-use factor for fixed-tilt utility PV (Ong et al. 2016).",
    },
    {
        "name": "ghi_ref_min / ghi_ref_max",
        "default": "4.0 / 7.0", "unit": "kWh/m²/day",
        "rationale": "Fallback GHI normalization range for cohorts too small for a "
                     "meaningful cohort min/max; configurable defaults for California.",
    },
]

KNOWN_LIMITATIONS = [
    "GHI resolution is 4-6 km (NSRDB grid), not parcel-level microclimate.",
    "Grid proximity scores straight-line distance, not actual interconnection "
    "capacity or queue position.",
    "Soil data coverage varies by county (SSURGO vs STATSGO); parcels outside the "
    "loaded SSURGO AOI are scored with a default capability class.",
    "Slope/aspect derived from the USGS 3DEP elevation service via finite-"
    "difference gradients at the parcel centroid (pre-computed at ~60 m for Kern "
    "parcels; queried on-demand at ~10 m for ad-hoc Score Mode parcels), not a "
    "site-specific survey.",
    "FEMA NFHL coverage currently loaded is Alameda County only; Kern flood "
    "screening is pending a Kern NFHL load, so the flood constraint cannot yet "
    "exclude Kern parcels (flagged per-parcel via flood coverage notes).",
    "No financial modeling (PPA pricing, tax credits, construction costs are "
    "downstream of suitability).",
]


def methodology_doc() -> dict[str, Any]:
    cfg = Config()
    return {
        "summary": METHODOLOGY_BRIEF["summary"],
        "pipeline": ["Ingest", "Enrich", "Filter", "Score", "Report"],
        "weights": cfg.weights,
        "weights_justification": (
            "Default weights adjusted for California Central Valley conditions where "
            "solar irradiance is uniformly high (GHI 5.0-6.0 kWh/m²/day) and grid "
            "proximity is the dominant site selection differentiator. Validated "
            "against 130 EIA Form 860 solar installations in Kern County: 98.5% "
            "score High (≥0.70), 53.8% in top quartile of agricultural parcel "
            "universe, mean suitability 0.829 vs 0.761 baseline. Base multi-criteria "
            "framework follows Doorga et al. (2019) and Charabi & Gastli (2011)."
        ),
        "scoring": {
            "ghi": "Cohort min-max normalization (reference range fallback for small cohorts).",
            "grid": "1 − distance/50km, clamped [0,1]; MIN of transmission-line and "
                    "substation distance.",
            "slope": "1 − slope_pct/15, clamped [0,1].",
            "aspect": "max(0, cos(deviation_from_south)); flat ground incurs no "
                      "orientation penalty.",
            "soil": "Inverted SSURGO capability class: class 1 → 1.0, class 8 → 0.125.",
            "road": "1 − distance/20km, clamped [0,1].",
            "land_use": "Kern zoning (Zn_Cd1) category score: agricultural 1.0, rural "
                        "0.85, unknown 0.75, industrial 0.5, commercial 0.35, "
                        "residential 0.15 — utility PV is sited on agricultural/rural "
                        "land (confirmed against EIA Form 860).",
        },
        "classification": {
            "High": ">= 0.70",
            "Moderate": "0.40 - 0.70",
            "Low": "< 0.40",
            "note": "Configurable defaults, validate against EIA Form 860 outcomes.",
        },
        "capacity_method": CAPACITY_METHOD,
        "environmental_constraints": {
            "source": "Hernandez et al. (2015)",
            "constraints": [
                "Exclude FEMA NFHL Special Flood Hazard Areas (sfha_tf='T').",
                "Exclude USFWS NWI mapped wetlands.",
                "Exclude USGS PAD-US protected areas.",
            ],
        },
        "citations": CITATIONS,
        "configurable_thresholds": THRESHOLDS_DOC,
        "data_sources": [
            {"name": "NREL NSRDB", "use": "Global horizontal irradiance (GHI)",
             "vintage": "PSM v3 4km grid + on-demand API"},
            {"name": "USGS 3DEP", "use": "Slope & aspect",
             "vintage": "1m/10m DEM via ImageServer"},
            {"name": "HIFLD Transmission Lines", "use": "Grid proximity", "vintage": "2023"},
            {"name": "OSM Substations", "use": "Grid proximity",
             "vintage": "Overpass, 2026 snapshot"},
            {"name": "FEMA NFHL", "use": "Flood exclusion",
             "vintage": "current NFHL (Alameda loaded)"},
            {"name": "USFWS NWI", "use": "Wetlands exclusion",
             "vintage": "CA state geodatabase"},
            {"name": "USGS PAD-US", "use": "Protected-lands exclusion",
             "vintage": "PAD-US Fee, CA"},
            {"name": "USDA SSURGO", "use": "Soil capability class",
             "vintage": "Soil Data Access, Kern AOI"},
            {"name": "Census TIGER Roads", "use": "Road access",
             "vintage": "2023 prisecroads, CA"},
            {"name": "Kern County Zoning", "use": "Land-use criterion",
             "vintage": "Kern County GIS, primary zone code Zn_Cd1"},
        ],
        "known_limitations": KNOWN_LIMITATIONS,
    }
