"""USGS Peak-Flow water-services — RDB parser.

Verified 2026-06-05:
  GET nwis.waterdata.usgs.gov/nwis/peak?site_no=…&agency_cd=USGS&format=rdb
  e.g. site_no=08074500 (Buffalo Bayou at Houston) returns annual peaks back
  to 1929 in tab-separated RDB.

The RDB format is USGS's tab-delimited text with '#'-prefixed header comments
and a type-row immediately below the column headers.
"""

from __future__ import annotations

from typing import Any

import httpx

URL = "https://nwis.waterdata.usgs.gov/nwis/peak"


async def peak_flows_for_site(
    client: httpx.AsyncClient, *, site_no: str
) -> list[dict[str, Any]]:
    """Return parsed annual peak-flow records for a USGS gauge.

    Each record has: peak_date (YYYY-MM-DD or YYYY for partial), peak_flow_cfs,
    gage_height_ft, qualifier_codes. Missing fields are None."""
    r = await client.get(
        URL,
        params={"site_no": site_no, "agency_cd": "USGS", "format": "rdb"},
    )
    r.raise_for_status()
    return _parse_rdb(r.text)


def _parse_rdb(rdb: str) -> list[dict[str, Any]]:
    lines = [line for line in rdb.splitlines() if line and not line.startswith("#")]
    if len(lines) < 3:
        return []
    header = lines[0].split("\t")
    rows = lines[2:]  # skip the column-type row
    out: list[dict[str, Any]] = []
    for line in rows:
        parts = line.split("\t")
        rec = dict(zip(header, parts, strict=False))
        out.append({
            "peak_date":      rec.get("peak_dt") or None,
            "peak_flow_cfs":  _to_float(rec.get("peak_va")),
            "gage_height_ft": _to_float(rec.get("gage_ht")),
            "qualifier":      rec.get("peak_cd") or None,
        })
    return out


def _to_float(v: Any) -> float | None:
    if v in (None, "", " "):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
