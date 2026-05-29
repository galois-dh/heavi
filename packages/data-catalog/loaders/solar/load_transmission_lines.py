"""Load national HIFLD electric power transmission lines → solar_transmission_lines.

Federal NGDA-hosted feature service (the substations counterpart of the dead
hifld-geoplatform portal). ~52k polylines nationally; paginate at 2000/page.
"""

from __future__ import annotations

from . import _common as c

TABLE = "solar_transmission_lines"
SOURCE_URL = (
    "https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services/"
    "Electric_Power_Transmission_Lines/FeatureServer/0"
)
OUT_FIELDS = "OBJECTID,ID,TYPE,STATUS,OWNER,VOLTAGE,VOLT_CLASS,SUB_1,SUB_2"


def main() -> None:
    print(f"Fetching {TABLE} (national, ~52k polylines) ...")
    gdf = c.fetch_arcgis_layer(SOURCE_URL, out_fields=OUT_FIELDS, out_sr=4326, page_size=2000)
    print(f"  {len(gdf)} transmission lines")
    n = c.write_postgis(
        gdf,
        TABLE,
        extra_indexes=[f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_voltage ON {TABLE} (voltage)"],
    )
    c.register_layer(
        TABLE,
        "HIFLD electric power transmission lines (national). Voltage / owner / "
        "substation endpoints per line.",
        SOURCE_URL,
        "MultiLineString",
        gdf=gdf,
        row_count=n,
    )
    print("Done.")


if __name__ == "__main__":
    main()
