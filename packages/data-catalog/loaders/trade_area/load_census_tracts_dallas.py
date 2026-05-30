"""Load Dallas County (FIPS 48113) census tract boundaries → trade_area_census_tracts_dallas.

Geometries come from Census TIGERweb (keyless ArcGIS REST). They are the spatial
substrate for isochrone↔demographics intersection; ACS demographic values are
fetched on-demand at query time and joined by GEOID.
"""

from __future__ import annotations

from ..solar import _common as c

TABLE = "trade_area_census_tracts_dallas"
SOURCE_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
    "Tracts_Blocks/MapServer/0"
)


def main() -> None:
    print(f"Fetching {TABLE} (Dallas County tracts, FIPS 48113) ...")
    gdf = c.fetch_arcgis_layer(
        SOURCE_URL,
        where="GEOID LIKE '48113%'",
        out_fields="GEOID,BASENAME,NAME",
        out_sr=4326,
        page_size=2000,
    )
    print(f"  {len(gdf)} tracts")
    gdf = gdf.rename(columns={"GEOID": "geoid", "BASENAME": "basename", "NAME": "name"})
    n = c.write_postgis(
        gdf,
        TABLE,
        extra_indexes=[f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_geoid ON {TABLE} (geoid)"],
    )
    c.register_layer(
        TABLE,
        "Dallas County (48113) census tract boundaries from Census TIGERweb. "
        "Spatial substrate for trade-area isochrone↔ACS demographic intersection.",
        SOURCE_URL,
        "MultiPolygon",
        gdf=gdf,
        row_count=n,
    )
    print("Done.")


if __name__ == "__main__":
    main()
