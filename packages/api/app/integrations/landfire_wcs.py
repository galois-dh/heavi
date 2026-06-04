"""LANDFIRE on-demand point values (fuel model + canopy cover).

The Data Tree Completeness Spec calls these "WCS" sources. In practice the
LANDFIRE geoserver's WMS GetFeatureInfo returns a single pixel value directly
(no client-side Albers reprojection, no GeoTIFF parsing — far lighter than a
full WCS GetCoverage), so that is the extraction path used here.

Verified 2026-06-08:
  fuel   → landfire_wcs:LF2023_FBFM40_CONUS (FBFM40 code; 91=urban, 93=ag,
           98=water, 99=barren; 101-204 burnable)
  canopy → landfire_wcs:LF2023_CC_CONUS (forest canopy cover %, 0-100)
The spec's coverage ids (LC23_F40_240 / LC23_CC_240) and the conus_sf canopy
endpoint were outdated.
"""

from __future__ import annotations

import httpx

WMS_ENDPOINT = "https://edcintl.cr.usgs.gov/geoserver/landfire_wcs/wms"
FUEL_LAYER = "landfire_wcs:LF2023_FBFM40_CONUS"
CANOPY_LAYER = "landfire_wcs:LF2023_CC_CONUS"

# FBFM40 non-burnable codes.
NONBURNABLE = {91, 92, 93, 98, 99}


async def query_landfire_value(
    client: httpx.AsyncClient,
    *,
    latitude: float,
    longitude: float,
    layer: str,
) -> int | None:
    """Return the LANDFIRE raster value at a point via WMS GetFeatureInfo, or
    None if unavailable/off-coverage."""
    d = 0.0008
    params = {
        "service": "WMS", "version": "1.3.0", "request": "GetFeatureInfo",
        "layers": layer, "query_layers": layer, "crs": "EPSG:4326",
        # WMS 1.3.0 EPSG:4326 axis order is lat,lng.
        "bbox": f"{latitude - d},{longitude - d},{latitude + d},{longitude + d}",
        "width": "3", "height": "3", "i": "1", "j": "1",
        "info_format": "application/json",
    }
    try:
        r = await client.get(WMS_ENDPOINT, params=params,
                             headers={"User-Agent": "Heavi/0.1 (landfire)"})
        feats = r.json().get("features") or []
    except Exception:  # noqa: BLE001
        return None
    if not feats:
        return None
    val = (feats[0].get("properties") or {}).get("GRAY_INDEX")
    try:
        return int(val) if val is not None else None
    except (TypeError, ValueError):
        return None


async def query_landfire_fuel(
    client: httpx.AsyncClient, *, latitude: float, longitude: float,
) -> dict[str, object] | None:
    """FBFM40 fuel model at a point → {fbfm40, burnable}."""
    v = await query_landfire_value(client, latitude=latitude, longitude=longitude, layer=FUEL_LAYER)
    if v is None:
        return None
    return {"fbfm40": v, "burnable": v not in NONBURNABLE}


async def query_landfire_canopy(
    client: httpx.AsyncClient, *, latitude: float, longitude: float,
) -> float | None:
    """Forest canopy cover percentage (0-100) at a point."""
    v = await query_landfire_value(client, latitude=latitude, longitude=longitude, layer=CANOPY_LAYER)
    return float(v) if v is not None else None
