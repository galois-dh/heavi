"""Load major roads for Dallas County → trade_area_roads_dallas.

Used for the trade-area accessibility criterion (distance from a candidate to the
nearest highway/arterial). OSM via Overpass: motorway / trunk / primary (+ links).
"""

from __future__ import annotations

import time

import geopandas as gpd
import requests
from shapely.geometry import LineString

from ..solar import _common as c

TABLE = "trade_area_roads_dallas"
OVERPASS = "https://overpass-api.de/api/interpreter"
QUERY = """
[out:json][timeout:300];
area["name"="Dallas County"]["admin_level"="6"]->.da;
(
  way["highway"~"^(motorway|trunk|primary|motorway_link|trunk_link|primary_link)$"](area.da);
);
out geom;
"""
HEADERS = {
    "User-Agent": "Heavi/0.1 (trade-area roads)",
    "Accept": "application/json",
    "Content-Type": "application/x-www-form-urlencoded",
}


def _fetch() -> list[dict]:
    for attempt, wait in enumerate([0, 30, 60]):
        if wait:
            print(f"  retry in {wait}s ...", flush=True)
            time.sleep(wait)
        try:
            r = requests.post(OVERPASS, data={"data": QUERY}, headers=HEADERS, timeout=400)
            if r.status_code == 200:
                return r.json().get("elements", [])
            print(f"  attempt {attempt + 1}: HTTP {r.status_code}", flush=True)
        except requests.RequestException as e:
            print(f"  attempt {attempt + 1} failed: {e}", flush=True)
    raise RuntimeError("Overpass fetch failed after retries")


def main() -> None:
    print(f"Fetching {TABLE} (Dallas County major roads) ...")
    elements = _fetch()
    osm_ids, hwys, geoms = [], [], []
    for el in elements:
        geom = el.get("geometry")
        if not geom or len(geom) < 2:
            continue
        coords = [(p["lon"], p["lat"]) for p in geom]
        osm_ids.append(el["id"])
        hwys.append(el.get("tags", {}).get("highway"))
        geoms.append(LineString(coords))
    gdf = gpd.GeoDataFrame(
        {"osm_id": osm_ids, "highway": hwys, "geometry": geoms}, crs="EPSG:4326"
    )
    print(f"  {len(gdf)} major road segments")
    n = c.write_postgis(gdf, TABLE)
    c.register_layer(
        TABLE,
        "Dallas County major roads (OSM motorway/trunk/primary + links). "
        "Trade-area accessibility: distance from candidate to nearest highway.",
        "https://overpass-api.de/ (OSM Dallas County)",
        "LineString",
        gdf=gdf,
        row_count=n,
    )
    print("Done.")


if __name__ == "__main__":
    main()
