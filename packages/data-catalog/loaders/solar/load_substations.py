"""Load HIFLD electric substations into solar_substations.

NOTE ON SOURCE: the canonical national HIFLD substations feature service
(~70k records) could not be located on public ArcGIS at build time — the
original hifld-geoplatform.opendata.arcgis.com endpoint is dead. The service
below was provided as the source but contains only ~128 records (Pennsylvania
subset). It is loaded as-is and flagged in catalog_layers; replace SOURCE_URL
with the canonical national service when available and re-run.
"""

from __future__ import annotations

from . import _common as c

TABLE = "solar_substations"
SOURCE_URL = (
    "https://services.arcgis.com/G4S1dGvn7PIgYd6Y/ArcGIS/rest/services/"
    "HIFLD_electric_power_substations/FeatureServer/0"
)


def main() -> None:
    print(f"Fetching {TABLE} from HIFLD substations service (native SR 3857 → 4326) ...")
    gdf = c.fetch_arcgis_layer(SOURCE_URL, out_sr=4326, page_size=2000)
    print(f"  {len(gdf)} substations")
    n = c.write_postgis(
        gdf,
        TABLE,
        extra_indexes=[f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_state ON {TABLE} (state)"],
    )
    c.register_layer(
        TABLE,
        "HIFLD electric substations. PARTIAL: source service returned ~128 records "
        "(Pennsylvania subset); canonical national ~70k service pending.",
        SOURCE_URL,
        "Point",
        gdf=gdf,
        row_count=n,
    )
    print("Done.")


if __name__ == "__main__":
    main()
