"""Load OSM power=substation nodes + ways for the top US solar states.

Architecture rationale: a national Overpass query times out at 180s. Geofabrik
PBFs are stable but require pyosmium to build a global node-location index
before way centroids can be resolved — that takes 5-10 min per state with the
2 GB Texas PBF. The proven CA pattern (loaders/solar/load_substations_osm.py)
uses Overpass per-state with a 300-600s timeout, which completes in ~30-60s
per state. We replicate that here for TX/AZ/NV/FL/NC.

This grows the existing solar_substations_osm (CA-only, 3,970 features) into
substations_osm_us covering the top 6 solar markets.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import geopandas as gpd
import psycopg2
import requests
from dotenv import load_dotenv
from shapely.geometry import Point
from sqlalchemy import create_engine, text

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

TABLE_NAME = "substations_osm_us"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
HEADERS = {
    "User-Agent": "Heavi/0.1 solar-data-catalog (contact: dhazarik@gmail.com)",
    "Accept": "application/json",
    "Content-Type": "application/x-www-form-urlencoded",
}
STATES = [
    ("California",     "CA"),
    ("Texas",          "TX"),
    ("Arizona",        "AZ"),
    ("Nevada",         "NV"),
    ("Florida",        "FL"),
    ("North Carolina", "NC"),
]


def query_state(name: str, timeout_s: int) -> list[dict] | None:
    q = f"""[out:json][timeout:{timeout_s}];
area["name"="{name}"]["admin_level"="4"]->.st;
(node["power"="substation"](area.st);way["power"="substation"](area.st););
out center;"""
    try:
        r = requests.post(
            OVERPASS_URL, data={"data": q}, headers=HEADERS, timeout=timeout_s + 60
        )
    except requests.RequestException as e:
        print(f"  Overpass error: {e}", flush=True)
        return None
    if r.status_code != 200:
        print(f"  Overpass HTTP {r.status_code}", flush=True)
        return None
    try:
        return r.json().get("elements", [])
    except ValueError:
        return None


def rows_for_state(state_abbrev: str, elements: list[dict]) -> list[dict]:
    out: list[dict] = []
    for el in elements:
        if el.get("type") == "node":
            lat, lon = el.get("lat"), el.get("lon")
        else:
            ctr = el.get("center") or {}
            lat, lon = ctr.get("lat"), ctr.get("lon")
        if lat is None or lon is None:
            continue
        tags = el.get("tags", {})
        out.append({
            "osm_id":    el.get("id"),
            "osm_type":  el.get("type"),
            "state":     state_abbrev,
            "name":      tags.get("name"),
            "voltage":   tags.get("voltage"),
            "operator":  tags.get("operator"),
            "substation": tags.get("substation"),
            "frequency": tags.get("frequency"),
            "geometry":  Point(float(lon), float(lat)),
        })
    return out


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr); sys.exit(1)

    all_rows: list[dict] = []
    for name, abbr in STATES:
        print(f"\n[{abbr}] querying Overpass for {name} substations…", flush=True)
        t0 = time.perf_counter()
        elements = query_state(name, timeout_s=300)
        if elements is None:
            print(f"  retrying {name} with timeout=600 …", flush=True)
            elements = query_state(name, timeout_s=600)
        if elements is None:
            print(f"  {name}: Overpass failed both attempts; skipping.", flush=True)
            continue
        rows = rows_for_state(abbr, elements)
        print(f"  {name}: {len(rows)} substations in {time.perf_counter()-t0:.1f}s",
              flush=True)
        all_rows.extend(rows)

    if not all_rows:
        print("ERROR: no substations parsed from any state", file=sys.stderr)
        sys.exit(1)

    gdf = gpd.GeoDataFrame(all_rows, geometry="geometry", crs="EPSG:4326")
    print(f"\nTotal across {len(STATES)} states: {len(gdf):,}")

    engine = create_engine(database_url)
    print(f"Writing {len(gdf):,} rows to {TABLE_NAME}…", flush=True)
    gdf.to_postgis(TABLE_NAME, engine, if_exists="replace", index=False)
    with engine.begin() as conn:
        conn.execute(text(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_geom "
                          f"ON {TABLE_NAME} USING GIST (geometry)"))
        conn.execute(text(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_state "
                          f"ON {TABLE_NAME} (state)"))

    bb_q = (
        f"SELECT ST_XMin(ST_Extent(geometry)), ST_YMin(ST_Extent(geometry)), "
        f"ST_XMax(ST_Extent(geometry)), ST_YMax(ST_Extent(geometry)) FROM {TABLE_NAME}"
    )
    with engine.connect() as conn:
        xmin, ymin, xmax, ymax = list(conn.execute(text(bb_q)).first())  # type: ignore[misc]
    conn2 = psycopg2.connect(database_url); conn2.autocommit = True
    cur = conn2.cursor()
    cur.execute(
        """
        INSERT INTO catalog_layers (name, description, source_url, geometry_type, bbox, row_count, updated_at)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s, now())
        ON CONFLICT (name) DO UPDATE SET
            description = EXCLUDED.description, source_url = EXCLUDED.source_url,
            geometry_type = EXCLUDED.geometry_type, bbox = EXCLUDED.bbox,
            row_count = EXCLUDED.row_count, updated_at = now();
        """,
        (
            TABLE_NAME,
            f"OSM power=substation features for the top 6 US solar states "
            f"({', '.join(a for _,a in STATES)}). Way centroids via Overpass "
            "`out center`. Substitute for HIFLD (publication paused).",
            "https://overpass-api.de/api/interpreter",
            "Point",
            json.dumps({"minx": xmin, "miny": ymin, "maxx": xmax, "maxy": ymax}),
            len(gdf),
        ),
    )
    cur.close(); conn2.close()
    print(f"Indexes created; registered '{TABLE_NAME}' in catalog_layers.", flush=True)


if __name__ == "__main__":
    main()
