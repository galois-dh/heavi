"""Load Kern County zoning → solar_zoning_kern.

Kern County's official zoning feature service. The primary zone code (Zn_Cd1)
drives the solar land-use criterion: agricultural / rural / vacant parcels are
favorable for utility PV, residential / commercial are not. This is the layer
the parcel land_use enrichment (enrich_parcels.py) and ad-hoc Score Mode join
against.
"""

from __future__ import annotations

from . import _common as c

TABLE = "solar_zoning_kern"
SOURCE_URL = (
    "https://services5.arcgis.com/Y8jwjGUWbRjuqpG5/arcgis/rest/services/"
    "Kern_County_Zoning/FeatureServer/0"
)
OUT_FIELDS = "OBJECTID,Zn_Cd1,Dscrptn"


def main() -> None:
    print(f"Fetching {TABLE} (Kern County zoning) ...")
    gdf = c.fetch_arcgis_layer(
        SOURCE_URL, where="1=1", out_fields=OUT_FIELDS, out_sr=4326, page_size=2000
    )
    print(f"  {len(gdf)} zoning polygons")
    gdf = gdf.rename(columns={"Zn_Cd1": "zone_code", "Dscrptn": "description"})
    n = c.write_postgis(
        gdf,
        TABLE,
        extra_indexes=[
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_code ON {TABLE} (zone_code)"
        ],
    )
    c.register_layer(
        TABLE,
        "Kern County zoning (primary zone_code Zn_Cd1 + description). Drives the "
        "solar land-use criterion: agricultural/rural favorable, residential/"
        "commercial unfavorable for utility PV.",
        SOURCE_URL,
        "MultiPolygon",
        gdf=gdf,
        row_count=n,
    )
    print("Done.")


if __name__ == "__main__":
    main()
