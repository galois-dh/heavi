"""Load Kern County assessor parcels → solar_parcels_kern.

Source: official Kern County GIS "Assessor Parcels Land 2025" feature service
(421,684 parcels total). For a utility-solar Discover-Mode demo we load parcels
>= 5 acres (~55k) — the developable scope that the suitability scoring and the
proximity checks care about; tiny urban parcels are noise here. Lower
ACRE_MIN to widen.

The source layer has no land_use field (APN + acreage only); land_use is added
as NULL and can be enriched from a county zoning/land-use layer later.
"""

from __future__ import annotations

from . import _common as c

TABLE = "solar_parcels_kern"
SOURCE_URL = (
    "https://services5.arcgis.com/Y8jwjGUWbRjuqpG5/arcgis/rest/services/"
    "Assessor_Parcels_Land_2025/FeatureServer/0"
)
ACRE_MIN = 5


def main() -> None:
    print(f"Fetching {TABLE} (Kern parcels >= {ACRE_MIN} acres) ...")
    gdf = c.fetch_arcgis_layer(
        SOURCE_URL,
        where=f"SHAPE_ACRE>={ACRE_MIN}",
        out_fields="OBJECTID,APN,APN_LABEL,SHAPE_ACRE",
        out_sr=4326,
        page_size=2000,
    )
    print(f"  {len(gdf)} parcels >= {ACRE_MIN} acres")
    gdf = gdf.rename(columns={"APN": "apn", "SHAPE_ACRE": "acreage"})
    gdf["land_use"] = None  # not present in source layer; enrich later
    n = c.write_postgis(
        gdf,
        TABLE,
        chunk_size=10_000,
        extra_indexes=[f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_apn ON {TABLE} (apn)"],
    )
    c.register_layer(
        TABLE,
        f"Kern County assessor parcels >= {ACRE_MIN} acres (APN + acreage). "
        "Developable-scope subset of 421,684 total; land_use pending zoning join.",
        SOURCE_URL,
        "MultiPolygon",
        gdf=gdf,
        row_count=n,
    )
    print("Done.")


if __name__ == "__main__":
    main()
