"""Load SSURGO soils (Kern County AOI) → solar_soils_kern.

SSURGO has a complex relational structure. We use USDA Soil Data Access (SDA),
which runs SQL against the national SSURGO DB and returns geometry as WKT,
avoiding the dynamic-dated Web Soil Survey cached downloads.

Two queries, joined on mukey:
  1. SPATIAL  — mupolygon geometry (WKT) + mukey, intersecting the AOI.
  2. TABULAR  — per-mapunit DOMINANT component (max comppct_r):
                  nirrcapcl  → soil_capability_class
                  hydricrating → hydric_rating
     i.e. the mapunit→component join the spec calls for.

Scope: a central-Kern developable-valley AOI (full-county SSURGO is 100k+
polygons). Widen AOI_WKT when the module expands. The relational join logic
is identical at any extent.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import requests
from shapely import wkt as shapely_wkt

from . import _common as c

TABLE = "solar_soils_kern"
SDA_URL = "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest"
SOURCE_URL = "https://websoilsurvey.nrcs.usda.gov/ (via USDA Soil Data Access)"
# Central-Kern valley AOI (where utility-solar siting is relevant).
AOI_WKT = "POLYGON((-119.4 35.1, -118.8 35.1, -118.8 35.5, -119.4 35.5, -119.4 35.1))"


def _sda(query: str) -> list[list]:
    r = requests.post(SDA_URL, json={"format": "JSON", "query": query}, timeout=180)
    r.raise_for_status()
    data = r.json()
    return data.get("Table", []) or []


def main() -> None:
    print("SDA spatial: fetching mupolygon geometry + mukey for the Kern AOI ...")
    spatial_q = (
        "SELECT mukey, mupolygongeo.STAsText() AS wkt "
        "FROM mupolygon "
        f"WHERE mupolygongeo.STIntersects(geometry::STGeomFromText('{AOI_WKT}',4326))=1"
    )
    rows = _sda(spatial_q)
    print(f"  {len(rows)} map-unit polygons")
    if not rows:
        print("  no polygons returned; nothing to load.")
        return
    geo_df = pd.DataFrame(rows, columns=["mukey", "wkt"])
    mukeys = sorted(set(geo_df["mukey"].astype(str)))
    print(f"  {len(mukeys)} distinct map units")

    print("SDA tabular: dominant-component capability class + hydric per map unit ...")
    in_list = ",".join(f"'{k}'" for k in mukeys)
    tab_q = (
        "SELECT mukey, capability_class, hydric_rating FROM ("
        "  SELECT m.mukey AS mukey, c.nirrcapcl AS capability_class, "
        "         c.hydricrating AS hydric_rating, "
        "         ROW_NUMBER() OVER (PARTITION BY m.mukey ORDER BY c.comppct_r DESC) AS rn "
        "  FROM mapunit m JOIN component c ON c.mukey = m.mukey "
        f"  WHERE m.mukey IN ({in_list})"
        ") t WHERE rn = 1"
    )
    tab_rows = _sda(tab_q)
    tab_df = pd.DataFrame(tab_rows, columns=["mukey", "soil_capability_class", "hydric_rating"])
    print(f"  {len(tab_df)} map units with component attributes")

    merged = geo_df.merge(tab_df, on="mukey", how="left")
    merged["geometry"] = merged["wkt"].apply(shapely_wkt.loads)
    gdf = gpd.GeoDataFrame(
        merged[["mukey", "soil_capability_class", "hydric_rating", "geometry"]],
        geometry="geometry",
        crs="EPSG:4326",
    )
    print(f"  {len(gdf)} soil polygons "
          f"(capability classes: {sorted(gdf['soil_capability_class'].dropna().unique())})")
    n = c.write_postgis(
        gdf,
        TABLE,
        extra_indexes=[f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_mukey ON {TABLE} (mukey)"],
    )
    c.register_layer(
        TABLE,
        "USDA SSURGO soils, central-Kern valley AOI (via Soil Data Access). "
        "Per-mapunit dominant-component land capability class (nirrcapcl) + "
        "hydric rating. Full-county extent deferred.",
        SOURCE_URL,
        "MultiPolygon",
        gdf=gdf,
        row_count=n,
    )
    print("Done.")


if __name__ == "__main__":
    main()
