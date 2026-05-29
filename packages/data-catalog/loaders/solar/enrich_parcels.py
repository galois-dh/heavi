"""Fully enrich solar_parcels_kern, then store the results (and a composite
suitability score) as columns so Discover mode is a trivial indexed SELECT.

Hybrid strategy (the big wetland/protected polygon layers are too large to pull
into Python reliably — the SSL connection drops mid-transfer):

  LOCAL compute (small point/line layers downloaded once, distances via
  scipy cKDTree / shapely STRtree):
    grid_distance_m       nearest transmission line OR substation
    road_distance_m       nearest primary/secondary road
    ghi_kwh_m2_day        nearest NREL NSRDB grid value
    soil_capability_class SSURGO land-capability class at the centroid
    suitability_score     composite of all six criteria (slope/aspect already
                          on the table from enrich_parcel_terrain.py)

  ON SUPABASE (batched centroid-in-polygon EXISTS, 500 parcels/UPDATE — uses the
  GIST indexes, each batch well under the statement timeout):
    in_wetland, in_protected, in_flood

Discover then reads pre-computed columns only — no remote spatial joins, fast
even under database load.
"""

from __future__ import annotations

import math
import os
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import execute_values
from scipy.spatial import cKDTree
from shapely import STRtree
from sqlalchemy import create_engine

load_dotenv(Path(__file__).resolve().parents[4] / ".env")

METRIC_CRS = "EPSG:3310"  # California Albers, metres

# Scoring config — mirrors packages/api/app/solar_scoring.py (canonical there).
# Grid-dominant weights tuned for the California Central Valley (uniform GHI,
# grid proximity the dominant differentiator) — see the methodology note.
WEIGHTS = {"ghi": 0.10, "grid": 0.45, "slope": 0.12, "aspect": 0.04,
           "soil": 0.06, "road": 0.18, "land_use": 0.05}
GRID_MAX_M = 50_000.0
ROAD_MAX_M = 20_000.0
DEFAULT_SOIL_CLASS = 4
HIGH_T, MOD_T = 0.70, 0.40
BATCH = 500

# Land-use score from the Kern zoning primary code (Zn_Cd1). Solar PV is sited on
# agricultural / rural / vacant land; residential & commercial are unfavorable.
LU_SCORE = {"agricultural": 1.0, "rural": 0.85, "unknown": 0.75, "industrial": 0.5,
            "commercial": 0.35, "residential": 0.15, "other": 0.6}


def classify_zone(z: str | None) -> str:
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


def _engine():
    url = os.environ["DATABASE_URL"]
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return create_engine(url, connect_args={"options": "-c statement_timeout=120000"})


def _load(eng, sql: str, label: str) -> gpd.GeoDataFrame:
    t = time.time()
    gdf = gpd.read_postgis(sql, eng, geom_col="geometry")
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    gdf = gdf.to_crs(METRIC_CRS)
    print(f"  loaded {label}: {len(gdf)} ({time.time() - t:.1f}s)", flush=True)
    return gdf


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def main() -> None:
    t0 = time.time()
    eng = _engine()
    print("Downloading point/line layers from Supabase ...", flush=True)
    parcels = _load(
        eng,
        "SELECT objectid, acreage, slope_degrees, aspect_degrees, "
        "ST_Centroid(geometry) AS geometry FROM solar_parcels_kern",
        "parcels (centroids)",
    )
    trans = _load(eng, "SELECT geometry FROM solar_transmission_lines", "transmission")
    subs = _load(eng, "SELECT geometry FROM solar_substations_osm", "substations")
    roads = _load(eng, "SELECT geometry FROM solar_roads_ca", "roads")
    soils = _load(
        eng, "SELECT soil_capability_class, geometry FROM solar_soils_kern", "soils"
    )
    nsrdb = _load(
        eng, "SELECT annual_ghi_kwh_m2_day, geometry FROM solar_nsrdb_kern", "nsrdb"
    )
    # Simplify zoning on read (≈22 m) to keep the 22K-polygon payload small.
    zoning = _load(
        eng,
        "SELECT zone_code, ST_SimplifyPreserveTopology(geometry, 0.0002) AS geometry "
        "FROM solar_zoning_kern",
        "zoning",
    )

    pts = parcels.geometry.values  # shapely points (EPSG:3310)
    n = len(parcels)
    print(f"Computing distances/GHI/soil for {n} parcels locally ...", flush=True)

    def nearest_dist(geoms) -> np.ndarray:
        out = np.full(n, np.inf)
        if len(geoms) == 0:
            return out
        tree = STRtree(geoms)
        idx, dists = tree.query_nearest(pts, all_matches=False, return_distance=True)
        in_idx = idx[0] if (hasattr(idx, "ndim") and idx.ndim == 2) else idx
        out[in_idx] = dists
        return out

    t = time.time()
    grid_geoms = list(trans.geometry.values) + list(subs.geometry.values)
    grid_dist = nearest_dist(grid_geoms)
    road_dist = nearest_dist(list(roads.geometry.values))
    print(f"  grid + road nearest ({time.time() - t:.1f}s)", flush=True)

    t = time.time()
    nsrdb_xy = np.column_stack([nsrdb.geometry.x.values, nsrdb.geometry.y.values])
    ghi_vals = nsrdb["annual_ghi_kwh_m2_day"].to_numpy(dtype=float)
    parcel_xy = np.column_stack([parcels.geometry.x.values, parcels.geometry.y.values])
    _d, gi = cKDTree(nsrdb_xy).query(parcel_xy, k=1)
    ghi = ghi_vals[gi]
    print(f"  GHI nearest ({time.time() - t:.1f}s)", flush=True)

    t = time.time()
    soil_idx = np.full(n, -1, dtype=np.int64)
    soil_geoms = list(soils.geometry.values)
    if soil_geoms:
        stree = STRtree(soil_geoms)
        in_idx, tree_idx = stree.query(pts, predicate="intersects")
        for pi, ti in zip(in_idx[::-1], tree_idx[::-1]):
            soil_idx[pi] = ti
    soil_class_arr = soils["soil_capability_class"].to_numpy()
    print(f"  soil point-in-polygon ({time.time() - t:.1f}s)", flush=True)

    t = time.time()
    zone_idx = np.full(n, -1, dtype=np.int64)
    zone_geoms = list(zoning.geometry.values)
    if zone_geoms:
        ztree = STRtree(zone_geoms)
        in_idx, tree_idx = ztree.query(pts, predicate="intersects")
        for pi, ti in zip(in_idx[::-1], tree_idx[::-1]):
            zone_idx[pi] = ti
    zone_code_arr = zoning["zone_code"].to_numpy()
    print(f"  zoning point-in-polygon ({time.time() - t:.1f}s)", flush=True)

    # ── Composite suitability score (full six criteria; terrain pre-computed) ─
    ghi_lo, ghi_hi = float(np.nanmin(ghi_vals)), float(np.nanmax(ghi_vals))
    ghi_span = (ghi_hi - ghi_lo) if (ghi_hi - ghi_lo) > 1e-9 else 1.0

    def soil_to_int(raw) -> int | None:
        if raw is None:
            return None
        s = "".join(c for c in str(raw).strip() if c.isdigit())[:1]
        return int(s) if s and 1 <= int(s) <= 8 else None

    payload = []
    rating_counts = {"High": 0, "Moderate": 0, "Low": 0}
    for i in range(n):
        oid = int(parcels.iloc[i]["objectid"])
        slope_deg = parcels.iloc[i]["slope_degrees"]
        aspect_deg = parcels.iloc[i]["aspect_degrees"]
        gd = float(grid_dist[i]) if math.isfinite(grid_dist[i]) else None
        rd = float(road_dist[i]) if math.isfinite(road_dist[i]) else None
        soil_cls = soil_to_int(soil_class_arr[soil_idx[i]]) if soil_idx[i] >= 0 else None

        ghi_score = _clamp01((ghi[i] - ghi_lo) / ghi_span)
        grid_score = _clamp01(1 - (gd if gd is not None else GRID_MAX_M) / GRID_MAX_M)
        road_score = _clamp01(1 - (rd if rd is not None else ROAD_MAX_M) / ROAD_MAX_M)
        if slope_deg is not None:
            slope_score = _clamp01(1 - (math.tan(math.radians(float(slope_deg))) * 100.0) / 15.0)
        else:
            slope_score = 0.0
        if aspect_deg is not None:
            dev = abs(float(aspect_deg) - 180.0)
            dev = min(dev, 360.0 - dev)
            aspect_score = max(0.0, math.cos(math.radians(dev)))
        else:
            aspect_score = 1.0
        cls_used = soil_cls if soil_cls is not None else DEFAULT_SOIL_CLASS
        soil_score = (9 - cls_used) / 8.0
        zone_code = zone_code_arr[zone_idx[i]] if zone_idx[i] >= 0 else None
        land_use = classify_zone(zone_code)
        land_use_score = LU_SCORE[land_use]

        composite = (
            WEIGHTS["ghi"] * ghi_score + WEIGHTS["grid"] * grid_score
            + WEIGHTS["slope"] * slope_score + WEIGHTS["aspect"] * aspect_score
            + WEIGHTS["soil"] * soil_score + WEIGHTS["road"] * road_score
            + WEIGHTS["land_use"] * land_use_score
        )
        rating = "High" if composite >= HIGH_T else "Moderate" if composite >= MOD_T else "Low"
        rating_counts[rating] += 1
        payload.append((
            oid,
            round(float(ghi[i]), 3),
            None if gd is None else round(gd, 1),
            None if rd is None else round(rd, 1),
            soil_cls,
            land_use,
            round(float(composite), 4),
            rating,
        ))
    print(f"  scored {n} parcels: {rating_counts}", flush=True)

    # ── Upload local enrichment + score ──────────────────────────────────────
    conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=20)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SET statement_timeout='120s'")
    cur.execute(
        "ALTER TABLE solar_parcels_kern "
        "ADD COLUMN IF NOT EXISTS ghi_kwh_m2_day double precision, "
        "ADD COLUMN IF NOT EXISTS grid_distance_m double precision, "
        "ADD COLUMN IF NOT EXISTS road_distance_m double precision, "
        "ADD COLUMN IF NOT EXISTS soil_capability_class integer, "
        "ADD COLUMN IF NOT EXISTS in_flood boolean, "
        "ADD COLUMN IF NOT EXISTS in_wetland boolean, "
        "ADD COLUMN IF NOT EXISTS in_protected boolean, "
        "ADD COLUMN IF NOT EXISTS land_use text, "
        "ADD COLUMN IF NOT EXISTS suitability_score double precision, "
        "ADD COLUMN IF NOT EXISTS suitability_rating text"
    )
    print("Uploading local enrichment (chunks of 500) ...", flush=True)
    t = time.time()
    for i in range(0, len(payload), BATCH):
        execute_values(
            cur,
            "UPDATE solar_parcels_kern p SET "
            "ghi_kwh_m2_day=v.ghi, grid_distance_m=v.grid, road_distance_m=v.road, "
            "soil_capability_class=v.soil, land_use=v.lu, suitability_score=v.score, "
            "suitability_rating=v.rating "
            "FROM (VALUES %s) AS v(oid, ghi, grid, road, soil, lu, score, rating) "
            "WHERE p.objectid = v.oid",
            payload[i : i + BATCH],
            template="(%s,%s::float8,%s::float8,%s::float8,%s::int,%s::text,%s::float8,%s::text)",
        )
    print(f"  uploaded {len(payload)} rows ({time.time() - t:.1f}s)", flush=True)

    cur.close()
    conn.close()

    compute_exclusion_flags()
    finalize(ghi_lo, ghi_hi, t0)


def _connect():
    conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=20)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SET statement_timeout='120s'")
    return conn, cur


def compute_exclusion_flags() -> None:
    """Set in_wetland / in_protected / in_flood via batched centroid-in-polygon
    EXISTS. Resumable (only touches parcels whose flags are still NULL) and
    resilient to the pooler dropping a long-lived connection mid-run."""
    flag_sql = (
        "UPDATE solar_parcels_kern p SET "
        "in_wetland = EXISTS(SELECT 1 FROM solar_wetlands_ca w "
        "  WHERE ST_Intersects(w.geometry, ST_Centroid(p.geometry))), "
        "in_protected = EXISTS(SELECT 1 FROM solar_protected_areas pa "
        "  WHERE ST_Intersects(pa.geometry, ST_Centroid(p.geometry))), "
        "in_flood = EXISTS(SELECT 1 FROM catalog_fema_flood fz "
        "  WHERE fz.sfha_tf='T' AND ST_Intersects(fz.geometry, ST_Centroid(p.geometry))) "
        "WHERE p.objectid = ANY(%s)"
    )
    conn, cur = _connect()
    cur.execute("SELECT objectid FROM solar_parcels_kern WHERE in_wetland IS NULL "
                "ORDER BY objectid")
    pending = [r[0] for r in cur.fetchall()]
    nb = (len(pending) + BATCH - 1) // BATCH
    print(f"Computing exclusion flags ({len(pending)} parcels pending, {BATCH}/batch) ...",
          flush=True)
    t = time.time()
    bi = 0
    i = 0
    while i < len(pending):
        chunk = pending[i : i + BATCH]
        try:
            cur.execute(flag_sql, (chunk,))
        except psycopg2.OperationalError as e:
            print(f"    reconnect after drop at batch {bi + 1}: {e}", flush=True)
            try:
                conn.close()
            except Exception:
                pass
            time.sleep(2)
            conn, cur = _connect()
            continue  # retry same chunk
        i += BATCH
        bi += 1
        if bi % 20 == 1 or bi == nb:
            print(f"    flags batch {bi}/{nb} ({time.time() - t:.0f}s elapsed)", flush=True)
    print(f"  exclusion flags done ({time.time() - t:.0f}s)", flush=True)
    conn.close()


def finalize(ghi_lo: float, ghi_hi: float, t0: float) -> None:
    conn, cur = _connect()
    print("Indexing + analyzing ...", flush=True)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_parcels_suit ON solar_parcels_kern "
        "(suitability_score DESC)"
    )
    cur.execute("ANALYZE solar_parcels_kern")
    cur.execute(
        "SELECT COUNT(*) FILTER (WHERE in_wetland), COUNT(*) FILTER (WHERE in_protected), "
        "COUNT(*) FILTER (WHERE in_flood), "
        "COUNT(*) FILTER (WHERE acreage>=10 AND NOT in_wetland AND NOT in_protected "
        "  AND NOT in_flood AND slope_degrees <= degrees(atan(0.15))), "
        "MIN(suitability_score), MAX(suitability_score) FROM solar_parcels_kern"
    )
    w, pa, fl, passing, smin, smax = cur.fetchone()
    print(f"GHI cohort: {ghi_lo:.2f}-{ghi_hi:.2f} kWh/m²/day", flush=True)
    print(f"Flags: in_wetland={w} in_protected={pa} in_flood={fl}", flush=True)
    print(f"Parcels passing discover constraints (>=10ac, slope<=15%, clear): {passing}",
          flush=True)
    print(f"suitability_score: min={smin:.3f} max={smax:.3f}", flush=True)
    print(f"Done in {time.time() - t0:.1f}s total.", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
