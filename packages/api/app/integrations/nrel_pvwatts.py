"""NREL PVWatts v8 — solar production estimation.

CRITICAL: the developer host changed on 2026-05-29. Use developer.nlr.gov
(the prior developer.nrel.gov no longer resolves in public DNS).

Verified 2026-06-05 with NREL_API_KEY at Kern coord (35.35, -119.05):
  ac_annual=1,688,855 kWh, capacity_factor=19.28%, solrad_annual=6.20 kWh/m²/d
"""

from __future__ import annotations

import os
from typing import Any

import httpx

PVWATTS_URL = "https://developer.nlr.gov/api/pvwatts/v8.json"


async def pvwatts_v8(
    client: httpx.AsyncClient,
    *,
    latitude: float,
    longitude: float,
    system_capacity_kw: float = 1000.0,
    tilt: float = 20.0,
    azimuth: float = 180.0,
    array_type: int = 1,   # 1 = fixed-tilt, 2 = 1-axis, 3 = 1-axis-backtracking, 4 = 2-axis
    module_type: int = 0,  # 0 = standard, 1 = premium, 2 = thin film
    losses_pct: float = 14.0,
    timeframe: str = "monthly",
    api_key: str | None = None,
) -> dict[str, Any]:
    """Call PVWatts v8 and return the slice the scoring pipeline needs.

    Raises ``ValueError`` if NREL_API_KEY is unset, or ``httpx.HTTPStatusError``
    on a non-2xx response. The full provider response is included under
    ``raw`` for the decision trail.
    """
    key = api_key or os.environ.get("NREL_API_KEY")
    if not key:
        raise ValueError(
            "NREL_API_KEY is not set; PVWatts requires a free NREL developer key."
        )
    params = {
        "api_key": key,
        "lat": latitude,
        "lon": longitude,
        "system_capacity": system_capacity_kw,
        "tilt": tilt,
        "azimuth": azimuth,
        "array_type": array_type,
        "module_type": module_type,
        "losses": losses_pct,
        "timeframe": timeframe,
    }
    r = await client.get(PVWATTS_URL, params=params)
    r.raise_for_status()
    data = r.json()
    outputs = data.get("outputs") or {}
    station = data.get("station_info") or {}
    return {
        "ac_annual_kwh":       outputs.get("ac_annual"),
        "capacity_factor_pct": outputs.get("capacity_factor"),
        "solrad_annual":       outputs.get("solrad_annual"),
        "ac_monthly_kwh":      outputs.get("ac_monthly"),
        "dc_monthly_kwh":      outputs.get("dc_monthly"),
        "station": {
            "latitude":  station.get("lat"),
            "longitude": station.get("lon"),
            "elevation": station.get("elev"),
            "tz":        station.get("tz"),
            "location":  station.get("location"),
        },
        "version": data.get("version"),
        "warnings": data.get("warnings") or [],
    }
