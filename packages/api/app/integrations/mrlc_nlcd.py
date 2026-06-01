"""MRLC NLCD via WMS GetFeatureInfo — on-demand land cover per US point.

Background: MRLC's downloadable NLCD bucket structure was reorganized; the
prior s3-us-west-2 URLs return 403. Their geoserver WMS at
``mrlc.gov/geoserver/mrlc_download/wms`` is up and serves the NLCD product
suite via GetFeatureInfo. Verified 2026-06-05 at Kern → palette index 22
(Developed, Open Space).

We default to the 2021 CONUS layer because it matches what the rest of the
data catalog references; bump ``layer`` to switch to the Annual NLCD series.
"""

from __future__ import annotations

from typing import Any

import httpx

WMS_URL = "https://www.mrlc.gov/geoserver/mrlc_download/wms"

# NLCD palette → human-readable class. Source: MRLC NLCD legend (2021/2019/2016
# all share the L1 16-class scheme).
NLCD_PALETTE = {
    11: "Open Water",
    12: "Perennial Ice/Snow",
    21: "Developed, Open Space",
    22: "Developed, Low Intensity",
    23: "Developed, Medium Intensity",
    24: "Developed, High Intensity",
    31: "Barren Land (Rock/Sand/Clay)",
    41: "Deciduous Forest",
    42: "Evergreen Forest",
    43: "Mixed Forest",
    51: "Dwarf Scrub",
    52: "Shrub/Scrub",
    71: "Grassland/Herbaceous",
    72: "Sedge/Herbaceous",
    73: "Lichens",
    74: "Moss",
    81: "Pasture/Hay",
    82: "Cultivated Crops",
    90: "Woody Wetlands",
    95: "Emergent Herbaceous Wetlands",
}

# Coarse class grouping useful for solar siting (cultivated land / grassland /
# shrubland are usually buildable; wetlands and developed-high are exclusions).
NLCD_GROUP = {
    "water":     {11, 12},
    "developed": {21, 22, 23, 24},
    "barren":    {31},
    "forest":    {41, 42, 43},
    "shrubland": {51, 52},
    "grassland": {71, 72, 73, 74},
    "cropland":  {81, 82},
    "wetlands":  {90, 95},
}


def _group_for(code: int) -> str | None:
    for g, codes in NLCD_GROUP.items():
        if code in codes:
            return g
    return None


async def nlcd_class_at_point(
    client: httpx.AsyncClient,
    *,
    latitude: float,
    longitude: float,
    layer: str = "NLCD_2021_Land_Cover_L48",
) -> dict[str, Any] | None:
    """Return {code, label, group, layer} for the NLCD pixel at the point,
    or None if the WMS returns no value (e.g. ocean / outside CONUS)."""
    # Tiny 0.02° bbox centered on the point; sample the middle pixel.
    half = 0.01
    bbox = f"{longitude-half},{latitude-half},{longitude+half},{latitude+half}"
    r = await client.get(
        WMS_URL,
        params={
            "service":      "WMS",
            "version":      "1.1.1",
            "request":      "GetFeatureInfo",
            "layers":       layer,
            "query_layers": layer,
            "srs":          "EPSG:4326",
            "width":        2,
            "height":       2,
            "x":            1,
            "y":            1,
            "bbox":         bbox,
            "info_format":  "application/json",
        },
    )
    r.raise_for_status()
    data = r.json()
    feats = data.get("features") or []
    if not feats:
        return None
    props = (feats[0].get("properties") or {})
    # GeoServer returns either GRAY_INDEX (single-band continuous) or
    # PALETTE_INDEX (indexed) depending on how the layer is published.
    code = props.get("PALETTE_INDEX") or props.get("GRAY_INDEX")
    if code is None:
        return None
    try:
        code = int(code)
    except (TypeError, ValueError):
        return None
    return {
        "code":  code,
        "label": NLCD_PALETTE.get(code, "Unknown"),
        "group": _group_for(code),
        "layer": layer,
    }
