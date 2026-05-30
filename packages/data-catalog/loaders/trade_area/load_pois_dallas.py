"""Load Dallas County POIs → trade_area_pois_dallas.

Overture Places distribution is cloud-native GeoParquet (heavy tooling); per the
build spec we use the OpenStreetMap Overpass API instead (same pattern as the
solar OSM substations loader). We pull amenity / shop / office / leisure /
healthcare features in Dallas County and store each as a Point with its category.
"""

from __future__ import annotations

import time

import geopandas as gpd
import requests
from shapely.geometry import Point

from ..solar import _common as c

TABLE = "trade_area_pois_dallas"
OVERPASS = "https://overpass-api.de/api/interpreter"
CATEGORIES = ["amenity", "shop", "office", "leisure", "healthcare"]
QUERY = """
[out:json][timeout:300];
area["name"="Dallas County"]["admin_level"="6"]->.da;
(
  node["amenity"](area.da);
  way["amenity"](area.da);
  node["shop"](area.da);
  way["shop"](area.da);
  node["office"](area.da);
  node["leisure"](area.da);
  way["leisure"](area.da);
  node["healthcare"](area.da);
);
out center;
"""
HEADERS = {
    "User-Agent": "Heavi/0.1 (trade-area POIs)",
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
    print(f"Fetching {TABLE} (Dallas County POIs via Overpass) ...")
    elements = _fetch()
    print(f"  {len(elements)} raw elements")

    osm_ids, names, categories, geoms = [], [], [], []
    for el in elements:
        tags = el.get("tags", {})
        category = None
        for key in CATEGORIES:
            if key in tags:
                category = f"{key}:{tags[key]}"
                break
        if category is None:
            continue
        if el["type"] == "node":
            lon, lat = el.get("lon"), el.get("lat")
        else:  # way/relation → center
            ctr = el.get("center", {})
            lon, lat = ctr.get("lon"), ctr.get("lat")
        if lon is None or lat is None:
            continue
        osm_ids.append(el["id"])
        names.append(tags.get("name"))
        categories.append(category)
        geoms.append(Point(lon, lat))

    gdf = gpd.GeoDataFrame(
        {"osm_id": osm_ids, "name": names, "category": categories, "geometry": geoms},
        crs="EPSG:4326",
    )
    print(f"  {len(gdf)} POIs with a category")
    n = c.write_postgis(
        gdf,
        TABLE,
        extra_indexes=[f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_category ON {TABLE} (category)"],
    )
    c.register_layer(
        TABLE,
        "Dallas County POIs (OSM via Overpass): amenity / shop / office / leisure / "
        "healthcare, category = '<key>:<value>'. Trade-area competitive/retail context.",
        "https://overpass-api.de/ (OSM Dallas County)",
        "Point",
        gdf=gdf,
        row_count=n,
    )
    print("Done.")


if __name__ == "__main__":
    main()
