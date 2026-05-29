"""Load PAD-US protected areas (California) → solar_protected_areas.

USGS PAD-US Fee feature service, filtered to California. The national GDB is
multi-GB; querying the hosted feature service for State_Nm='CA' avoids the
download and keeps this to ~18k polygons.

Scope note: this loads the Fee feature class (the dominant protected-areas
layer). Easement is a much smaller separate PAD-US class and is deferred to a
follow-on; Marine is intentionally excluded per spec.
"""

from __future__ import annotations

from . import _common as c

TABLE = "solar_protected_areas"
SOURCE_URL = (
    "https://services.arcgis.com/v01gqwM5QqNysAAi/arcgis/rest/services/"
    "Fee_Manager/FeatureServer/0"
)
OUT_FIELDS = "OBJECTID,Unit_Nm,Des_Tp,Pub_Access,Own_Type,Mang_Name,GAP_Sts,State_Nm,GIS_Acres"


def main() -> None:
    print(f"Fetching {TABLE} (PAD-US Fee, California) ...")
    gdf = c.fetch_arcgis_layer(
        SOURCE_URL, where="State_Nm='CA'", out_fields=OUT_FIELDS, out_sr=4326, page_size=2000
    )
    print(f"  {len(gdf)} CA Fee protected-area polygons")
    # Friendlier column names matching the spec.
    gdf = gdf.rename(
        columns={"Unit_Nm": "name", "Des_Tp": "designation_type", "Pub_Access": "public_access"}
    )
    n = c.write_postgis(
        gdf,
        TABLE,
        extra_indexes=[
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_access ON {TABLE} (public_access)"
        ],
    )
    c.register_layer(
        TABLE,
        "USGS PAD-US Fee protected areas, California (name / designation_type / "
        "public_access). Easement class deferred; Marine excluded.",
        SOURCE_URL,
        "MultiPolygon",
        gdf=gdf,
        row_count=n,
    )
    print("Done.")


if __name__ == "__main__":
    main()
