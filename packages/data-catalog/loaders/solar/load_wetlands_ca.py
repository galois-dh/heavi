"""Load USFWS National Wetlands Inventory (California) → solar_wetlands_ca.

The Wetlands MapServer query API returns counts but no geometry for this
joined view, so we download the California state geodatabase directly and
read it with pyogrio.

CA-wide NWI is millions of polygons — too large for Supabase — so we clip to
the Kern County bounding box on read (the spec's fallback). Lower/remove
KERN_BBOX to widen when the module expands beyond Kern.

Fields: wetland_type (from the NWI ATTRIBUTE column), geometry (Polygon, 4326).
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import geopandas as gpd
import pyogrio
import requests
from pyproj import Transformer

from . import _common as c

TABLE = "solar_wetlands_ca"
SOURCE_URL = (
    "https://documentst.ecosphere.fws.gov/wetlands/data/State-Downloads/"
    "CA_geodatabase_wetlands.zip"
)
# User-specified Kern clip box (lng_min, lat_min, lng_max, lat_max).
KERN_BBOX = (-119.9, 34.8, -117.6, 35.8)
_ZIP = Path("/tmp/ca_nwi.zip")
_EXTRACT = Path("/tmp/ca_nwi_gdb")


def _ensure_gdb() -> Path:
    if not _ZIP.exists() or _ZIP.stat().st_size < 500_000_000:
        print(f"Downloading CA NWI geodatabase → {_ZIP} (~1.2 GB) ...")
        with requests.get(SOURCE_URL, stream=True, timeout=1800) as r:
            r.raise_for_status()
            with _ZIP.open("wb") as f:
                for chunk in r.iter_content(chunk_size=8 << 20):
                    f.write(chunk)
    _EXTRACT.mkdir(exist_ok=True)
    if not any(_EXTRACT.glob("*.gdb")):
        print("Extracting geodatabase ...")
        with zipfile.ZipFile(_ZIP) as zf:
            zf.extractall(_EXTRACT)
    gdb = next(_EXTRACT.rglob("*.gdb"))
    return gdb


def main() -> None:
    gdb = _ensure_gdb()
    layers = [name for name, _ in pyogrio.list_layers(gdb)]
    print(f"  GDB layers: {layers}")
    # NWI wetlands polygon layer is named like 'CA_Wetlands' / '*_Wetlands'
    # (exclude the historic and project-metadata layers).
    layer = next(
        l for l in layers
        if l.lower().endswith("wetlands") and "historic" not in l.lower()
    )
    # The GDB is in NAD83 Albers (metres), not lat/lng — pyogrio's bbox filter
    # is applied in the layer's native CRS, so transform the Kern lat/lng box
    # there first. Transform all four corners (Albers isn't axis-aligned) and
    # take the enclosing envelope.
    native_crs = pyogrio.read_info(gdb, layer=layer).get("crs")
    tr = Transformer.from_crs("EPSG:4326", native_crs, always_xy=True)
    mnx, mny, mxx, mxy = KERN_BBOX
    corners = [tr.transform(x, y) for x in (mnx, mxx) for y in (mny, mxy)]
    xs = [c[0] for c in corners]
    ys = [c[1] for c in corners]
    native_bbox = (min(xs), min(ys), max(xs), max(ys))
    print(f"  reading layer '{layer}' clipped to Kern bbox (native CRS) {tuple(round(v) for v in native_bbox)} ...")
    gdf = gpd.read_file(gdb, layer=layer, engine="pyogrio", bbox=native_bbox)
    print(f"  {len(gdf)} wetland polygons in Kern AOI")

    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(4326)
    # Normalize the NWI ATTRIBUTE column → wetland_type.
    cols = {col.lower(): col for col in gdf.columns}
    attr = cols.get("attribute")
    keep = gpd.GeoDataFrame(
        {
            "wetland_type": gdf[attr] if attr else None,
            "geometry": gdf.geometry,
        },
        geometry="geometry",
        crs="EPSG:4326",
    )
    # Wetland polygons are geometry-heavy; smaller chunks keep each insert
    # well under the pooler's idle/statement window (a 20k chunk dropped the
    # connection mid-write).
    n = c.write_postgis(
        keep,
        TABLE,
        chunk_size=2_500,
        extra_indexes=[f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_type ON {TABLE} (wetland_type)"],
    )
    c.register_layer(
        TABLE,
        "USFWS National Wetlands Inventory, Kern County clip from the CA state "
        "geodatabase (wetland_type = NWI ATTRIBUTE code). CA-wide load deferred "
        "(millions of polygons).",
        SOURCE_URL,
        "MultiPolygon",
        gdf=keep,
        row_count=n,
    )
    print("Done.")


if __name__ == "__main__":
    main()
