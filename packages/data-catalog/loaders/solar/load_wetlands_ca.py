"""Load USFWS National Wetlands Inventory → solar_wetlands_ca.

Scope note: full-California NWI is millions of polygons. For Discover Mode
(Kern County) we load the Kern AOI extract via the USFWS Wetlands MapServer,
clipped to the Kern bbox (~31k polygons). The table keeps the _ca name;
densify to statewide when the module expands beyond Kern.
"""

from __future__ import annotations

from . import _common as c

TABLE = "solar_wetlands_ca"
SOURCE_URL = (
    "https://fwspublicservices.wim.usgs.gov/wetlandsmapservice/rest/services/"
    "Wetlands/MapServer/0"
)


def main() -> None:
    minlng, minlat, maxlng, maxlat = c.KERN_BBOX
    env = f"{minlng},{minlat},{maxlng},{maxlat}"
    print(f"Fetching {TABLE} (NWI, Kern AOI {env}) ...")
    gdf = c.fetch_arcgis_layer(
        SOURCE_URL,
        out_fields="WETLAND_TYPE,ACRES,ATTRIBUTE",
        out_sr=4326,
        page_size=2000,
        geometry=env,
        geometry_type="esriGeometryEnvelope",
        in_sr=4326,
    )
    print(f"  {len(gdf)} wetland polygons in Kern AOI")
    # MapServer joined-view columns may arrive prefixed; normalize to wetland_type.
    rename = {col: "wetland_type" for col in gdf.columns if col.lower().endswith("wetland_type")}
    rename.update({col: "acres" for col in gdf.columns if col.lower().endswith(".acres") or col.lower() == "acres"})
    gdf = gdf.rename(columns=rename)
    n = c.write_postgis(
        gdf,
        TABLE,
        extra_indexes=[
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_type ON {TABLE} (wetland_type)"
        ]
        if "wetland_type" in [col.lower() for col in gdf.columns]
        else None,
    )
    c.register_layer(
        TABLE,
        "USFWS National Wetlands Inventory, Kern County AOI extract "
        "(wetland_type polygons). CA-wide load deferred (millions of polygons).",
        SOURCE_URL,
        "MultiPolygon",
        gdf=gdf,
        row_count=n,
    )
    print("Done.")


if __name__ == "__main__":
    main()
