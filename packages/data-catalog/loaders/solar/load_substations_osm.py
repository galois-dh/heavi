"""Load OpenStreetMap substations (California) → solar_substations_osm.

Enrichment layer for grid-proximity scoring, complementing HIFLD transmission
lines. HIFLD's national substations service was unavailable at build time
(only a 128-record PA subset surfaced), so OSM substations are the practical
substation source for California. Pulled via the Overpass API:
power=substation nodes + ways (way centroids via `out center`).

Retry once with a longer timeout on failure; if Overpass still fails, the
loader exits non-zero and substations remain deferred (scoring falls back to
transmission lines only).
"""

from __future__ import annotations

import sys

import geopandas as gpd
import requests
from shapely.geometry import Point

from . import _common as c

TABLE = "solar_substations_osm"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def _query(timeout_s: int) -> dict | None:
    q = f"""[out:json][timeout:{timeout_s}];
area["name"="California"]["admin_level"="4"]->.ca;
(
  node["power"="substation"](area.ca);
  way["power"="substation"](area.ca);
);
out center;"""
    # Overpass 406s without a UA / on some Accept headers; send an explicit
    # browser-ish UA and Accept, query as the raw urlencoded `data` field.
    headers = {
        "User-Agent": "Heavi/0.1 solar-data-catalog (contact: dhazarik@gmail.com)",
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    try:
        r = requests.post(
            OVERPASS_URL, data={"data": q}, headers=headers, timeout=timeout_s + 30
        )
    except requests.RequestException as e:
        print(f"  Overpass request error: {e}")
        return None
    if r.status_code != 200:
        print(f"  Overpass HTTP {r.status_code}")
        return None
    try:
        return r.json()
    except ValueError:
        print("  Overpass returned non-JSON")
        return None


def main() -> int:
    print("Querying Overpass for California power=substation (nodes + ways) ...")
    data = _query(300)
    if data is None:
        print("  retrying with timeout=600 ...")
        data = _query(600)
    if data is None:
        print("  Overpass failed twice — substations DEFERRED (transmission-only scoring).")
        return 1

    elements = data.get("elements", [])
    print(f"  Overpass returned {len(elements)} elements")

    rows = []
    for el in elements:
        if el.get("type") == "node":
            lat, lon = el.get("lat"), el.get("lon")
        else:  # way → center
            ctr = el.get("center") or {}
            lat, lon = ctr.get("lat"), ctr.get("lon")
        if lat is None or lon is None:
            continue
        tags = el.get("tags", {})
        rows.append(
            {
                "osm_id": el.get("id"),
                "osm_type": el.get("type"),
                "name": tags.get("name"),
                "voltage": tags.get("voltage"),
                "operator": tags.get("operator"),
                "geometry": Point(float(lon), float(lat)),
            }
        )

    if not rows:
        print("  No substation elements parsed — DEFERRED.")
        return 1

    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    print(f"  {len(gdf)} California OSM substations parsed")
    n = c.write_postgis(gdf, TABLE)
    c.register_layer(
        TABLE,
        "OpenStreetMap power=substation (California) via Overpass — enrichment "
        "layer for grid-proximity scoring alongside HIFLD transmission lines.",
        OVERPASS_URL,
        "Point",
        gdf=gdf,
        row_count=n,
    )
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
