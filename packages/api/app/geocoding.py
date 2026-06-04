"""Address / place-name geocoding (Heavi Month-1 Sprint, Feature 1).

Accepts street addresses, place names, city/state, or raw lat,lng and resolves a
single best coordinate. Census Bureau geocoder first (free, no API key, no rate
limit — ideal for the precise parcel addresses developers paste), Nominatim
(OpenStreetMap) fallback for place names, city/state, and named POIs.

Census is used only when it returns EXACTLY ONE match (high confidence). Zero
matches (place names) or multiple ambiguous matches (e.g. "1600 Pennsylvania Ave"
returns both SE and NW) fall through to Nominatim, whose POI/place ranking
resolves them the way a user expects (the White House).
"""

from __future__ import annotations

import re
from typing import Any

import httpx

CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_UA = "Heavi/0.1 (geocode)"

# "35.35, -119.05" or "35.35 -119.05" — lat,lng with lat in [-90,90], lng in [-180,180].
_COORD_RE = re.compile(
    r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*[, ]\s*(-?\d{1,3}(?:\.\d+)?)\s*$"
)


def parse_coords(q: str) -> tuple[float, float] | None:
    """Return (lat, lng) if the string is a raw coordinate pair, else None."""
    m = _COORD_RE.match(q or "")
    if not m:
        return None
    lat, lng = float(m.group(1)), float(m.group(2))
    if -90 <= lat <= 90 and -180 <= lng <= 180:
        return lat, lng
    return None


async def _census(client: httpx.AsyncClient, q: str) -> dict[str, Any] | None:
    """Census onelineaddress — return a result only on a single confident match."""
    try:
        r = await client.get(
            CENSUS_URL,
            params={"address": q, "benchmark": "Public_AR_Current", "format": "json"},
            headers={"User-Agent": _UA},
        )
        matches = (r.json().get("result") or {}).get("addressMatches") or []
    except Exception:  # noqa: BLE001
        return None
    if len(matches) != 1:
        return None  # 0 = no match; >1 = ambiguous → let Nominatim decide
    m = matches[0]
    c = m.get("coordinates") or {}
    if c.get("y") is None or c.get("x") is None:
        return None
    return {
        "latitude": float(c["y"]),
        "longitude": float(c["x"]),
        "formatted_address": m.get("matchedAddress"),
        "source": "census",
    }


async def _nominatim(client: httpx.AsyncClient, q: str) -> dict[str, Any] | None:
    try:
        r = await client.get(
            NOMINATIM_URL,
            params={"q": q, "format": "json", "limit": 1, "addressdetails": 0},
            headers={"User-Agent": _UA},
        )
        data = r.json()
    except Exception:  # noqa: BLE001
        return None
    if not data:
        return None
    d = data[0]
    return {
        "latitude": float(d["lat"]),
        "longitude": float(d["lon"]),
        "formatted_address": d.get("display_name"),
        "source": "nominatim",
    }


async def geocode(query: str) -> dict[str, Any] | None:
    """Resolve a query to {latitude, longitude, formatted_address, source}, or
    None if nothing matches. Raw coordinates are returned without any HTTP call."""
    q = (query or "").strip()
    if not q:
        return None
    coords = parse_coords(q)
    if coords is not None:
        lat, lng = coords
        return {
            "latitude": lat, "longitude": lng,
            "formatted_address": f"{lat:.5f}, {lng:.5f}",
            "source": "coordinates",
        }
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        result = await _census(client, q)
        if result is not None:
            return result
        return await _nominatim(client, q)
