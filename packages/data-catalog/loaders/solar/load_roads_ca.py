"""Load California primary & secondary roads → solar_roads_ca.

Census TIGER PRISECROADS for FIPS 06. The PRISECROADS product is already
limited to primary (S1100) and secondary (S1200) roads statewide; we filter
on MTFCC defensively anyway. Keeps the layer small enough for proximity/
access scoring without the full all-roads file.
"""

from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
import requests

from . import _common as c

TABLE = "solar_roads_ca"
SOURCE_URL = "https://www2.census.gov/geo/tiger/TIGER2023/PRISECROADS/tl_2023_06_prisecroads.zip"
KEEP_MTFCC = {"S1100", "S1200"}


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        zpath = Path(tmp) / "ca_roads.zip"
        print("Downloading TIGER CA primary/secondary roads ...")
        zpath.write_bytes(requests.get(SOURCE_URL, timeout=180).content)
        with zipfile.ZipFile(zpath) as zf:
            zf.extractall(tmp)
        shp = next(Path(tmp).glob("*.shp"))
        gdf = gpd.read_file(shp, engine="pyogrio")

    gdf.columns = [col.lower() for col in gdf.columns]
    gdf = gdf[gdf["mtfcc"].isin(KEEP_MTFCC)].copy()
    out = gdf.rename(columns={"fullname": "road_name", "mtfcc": "road_type"})[
        ["linearid", "road_name", "road_type", "rttyp", "geometry"]
    ]
    if out.crs is None or out.crs.to_epsg() != 4326:
        out = out.to_crs(4326)
    print(f"  {len(out)} primary/secondary road segments "
          f"(S1100={int((out['road_type']=='S1100').sum())}, "
          f"S1200={int((out['road_type']=='S1200').sum())})")
    n = c.write_postgis(
        out,
        TABLE,
        extra_indexes=[f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_type ON {TABLE} (road_type)"],
    )
    c.register_layer(
        TABLE,
        "Census TIGER 2023 primary (S1100) and secondary (S1200) roads, California.",
        SOURCE_URL,
        "MultiLineString",
        gdf=out,
        row_count=n,
    )
    print("Done.")


if __name__ == "__main__":
    main()
