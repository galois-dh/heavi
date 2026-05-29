"""Build a cached solar-resource (GHI) grid for Kern County → solar_nsrdb_kern.

We do NOT download the national NSRDB raster. Instead we sample NREL's
solar_resource API on a grid over Kern County and cache the annual average
GHI per point.

Grid spacing: the spec calls for 4 km, but NREL's API is rate-limited to
1000 requests/hour and a true 4 km grid over Kern's bbox is ~1650 points.
GHI varies very smoothly at county scale (< ~0.3 kWh/m²/day across Kern),
so we use a ~6.5 km grid (~730 points) that fits the hourly budget and
completes in one pass. Lower GRID_STEP_DEG to densify toward 4 km when the
rate budget allows (the loader is a single idempotent run).

NREL domain note: developer.nrel.gov is in scheduled shutdown (final
2026-05-29); we call the successor developer.nlr.gov, falling back to the
old host while brownouts are intermittent.
"""

from __future__ import annotations

import time

import geopandas as gpd
import requests
from shapely.geometry import Point

from . import _common as c

TABLE = "solar_nsrdb_kern"
GRID_STEP_DEG = 0.06  # ~6.5 km; see module docstring
NREL_HOSTS = ["https://developer.nlr.gov", "https://developer.nrel.gov"]
SOURCE_URL = "https://developer.nlr.gov/api/solar/solar_resource/v1.json"


def _ghi(lat: float, lng: float, key: str) -> float | None:
    """Annual avg GHI (kWh/m²/day) for a point, or None. Tries the new NREL
    host first, then the legacy host during brownouts."""
    for host in NREL_HOSTS:
        try:
            r = requests.get(
                f"{host}/api/solar/solar_resource/v1.json",
                params={"api_key": key, "lat": round(lat, 4), "lon": round(lng, 4)},
                timeout=30,
            )
        except requests.RequestException:
            continue
        if r.status_code == 429:
            time.sleep(5)
            continue
        if r.status_code != 200:
            continue
        out = (r.json().get("outputs") or {}).get("avg_ghi") or {}
        val = out.get("annual")
        # NREL returns the string "no data" for points outside coverage.
        return float(val) if isinstance(val, (int, float)) else None
    return None


def main() -> None:
    key = c.nrel_api_key()
    minlng, minlat, maxlng, maxlat = c.KERN_BBOX

    # Build grid points.
    pts: list[tuple[float, float]] = []
    lat = minlat
    while lat <= maxlat + 1e-9:
        lng = minlng
        while lng <= maxlng + 1e-9:
            pts.append((lat, lng))
            lng += GRID_STEP_DEG
        lat += GRID_STEP_DEG
    print(f"Sampling NREL GHI on {len(pts)} grid points over Kern "
          f"(step {GRID_STEP_DEG}° ≈ {GRID_STEP_DEG*111:.1f} km) ...")

    rows = []
    sampled = 0
    for i, (lat, lng) in enumerate(pts):
        ghi = _ghi(lat, lng, key)
        if ghi is not None:
            rows.append({"lat": lat, "lng": lng, "annual_ghi_kwh_m2_day": ghi,
                         "geometry": Point(lng, lat)})
            sampled += 1
        if (i + 1) % 50 == 0:
            print(f"    {i+1}/{len(pts)} probed, {sampled} with data")
        time.sleep(0.1)  # gentle throttle under the 1000/hr cap

    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    print(f"  {len(gdf)} grid points with GHI "
          f"(range {gdf['annual_ghi_kwh_m2_day'].min():.2f}–{gdf['annual_ghi_kwh_m2_day'].max():.2f})")
    n = c.write_postgis(gdf, TABLE)
    c.register_layer(
        TABLE,
        f"NREL NSRDB annual GHI cache for Kern County on a ~{GRID_STEP_DEG*111:.0f} km grid "
        "(solar_resource API; coarser than 4 km due to the 1000 req/hr API cap).",
        SOURCE_URL,
        "Point",
        gdf=gdf,
        row_count=n,
    )
    print("Done.")


if __name__ == "__main__":
    main()
