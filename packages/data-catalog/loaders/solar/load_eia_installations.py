"""Load EIA Form 860 solar generators → solar_eia_installations (national).

Validation dataset: where solar actually got built. The 3_3_Solar_Y2023 sheet
is already solar-only (PV + thermal); we join it to 2___Plant_Y2023 on
Plant Code to attach latitude/longitude, then build point geometry.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import Point

from . import _common as c

TABLE = "solar_eia_installations"
SOURCE_URL = "https://www.eia.gov/electricity/data/eia860/archive/xls/eia8602023.zip"
_CACHE = Path("/tmp/eia860.zip")


def _read_sheet(zf: zipfile.ZipFile, name_contains: str) -> pd.DataFrame:
    member = next(n for n in zf.namelist() if name_contains in n and n.endswith(".xlsx"))
    with zf.open(member) as f:
        # EIA sheets carry a 1-row title above the column header.
        return pd.read_excel(io.BytesIO(f.read()), header=1)


def main() -> None:
    if _CACHE.exists() and _CACHE.stat().st_size > 1_000_000:
        print(f"Using cached {_CACHE}")
        raw = _CACHE.read_bytes()
    else:
        print(f"Downloading EIA-860 → {_CACHE} ...")
        raw = requests.get(SOURCE_URL, timeout=180).content
        _CACHE.write_bytes(raw)

    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        solar = _read_sheet(zf, "3_3_Solar_Y2023")
        plant = _read_sheet(zf, "2___Plant_Y2023")

    plant_geo = plant[["Plant Code", "Latitude", "Longitude"]].drop_duplicates("Plant Code")
    df = solar.merge(plant_geo, on="Plant Code", how="left")
    df = df.dropna(subset=["Latitude", "Longitude"])

    out = pd.DataFrame(
        {
            "plant_code": df["Plant Code"],
            "plant_name": df["Plant Name"],
            "state": df["State"],
            "county": df["County"],
            "capacity_mw": pd.to_numeric(df["Nameplate Capacity (MW)"], errors="coerce"),
            "technology": df["Technology"],
            "operating_status": df["Status"],
            "operating_year": pd.to_numeric(df["Operating Year"], errors="coerce"),
            "latitude": df["Latitude"].astype(float),
            "longitude": df["Longitude"].astype(float),
        }
    )
    gdf = gpd.GeoDataFrame(
        out,
        geometry=[Point(xy) for xy in zip(out["longitude"], out["latitude"])],
        crs="EPSG:4326",
    )
    print(f"  {len(gdf)} solar generators with coordinates "
          f"({gdf['capacity_mw'].sum():,.0f} MW nameplate total)")
    n = c.write_postgis(
        gdf,
        TABLE,
        extra_indexes=[f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_state ON {TABLE} (state)"],
    )
    c.register_layer(
        TABLE,
        "EIA Form 860 (2023) solar generators — validation dataset of built solar "
        "(PV + thermal), national. Capacity / technology / operating status per generator.",
        SOURCE_URL,
        "Point",
        gdf=gdf,
        row_count=n,
    )
    print("Done.")


if __name__ == "__main__":
    main()
