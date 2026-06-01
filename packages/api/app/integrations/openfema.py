"""OpenFEMA — Disaster Declarations + NFIP Claims.

Verified 2026-06-05:
  GET /api/open/v2/DisasterDeclarationsSummaries (Harris County → Hurricane
       Beryl 2024, severe storms 2024, winter storms 2021)
  GET /api/open/v2/FimaNfipClaims                (queryable by reportedZipCode)

Both endpoints are anonymous, JSON, OData-style $filter syntax.
"""

from __future__ import annotations

from typing import Any

import httpx

BASE = "https://www.fema.gov/api/open/v2"


async def disaster_declarations(
    client: httpx.AsyncClient,
    *,
    state_abbr: str | None = None,
    county_name: str | None = None,
    declaration_type: str = "DR",
    top: int = 50,
) -> list[dict[str, Any]]:
    """Return disaster-declaration records for a state/county. ``state_abbr``
    is the two-letter postal code, ``county_name`` matches the FEMA
    ``designatedArea`` field (e.g. 'Harris (County)')."""
    filters = [f"declarationType eq '{declaration_type}'"]
    if state_abbr:
        filters.append(f"state eq '{state_abbr}'")
    if county_name:
        filters.append(f"designatedArea eq '{county_name}'")
    r = await client.get(
        f"{BASE}/DisasterDeclarationsSummaries",
        params={
            "$filter":   " and ".join(filters),
            "$top":      top,
            "$orderby":  "declarationDate desc",
        },
    )
    r.raise_for_status()
    items = r.json().get("DisasterDeclarationsSummaries") or []
    return [
        {
            "disaster_number":     it.get("disasterNumber"),
            "declaration_date":    it.get("declarationDate"),
            "declaration_title":   it.get("declarationTitle"),
            "incident_type":       it.get("incidentType"),
            "incident_begin_date": it.get("incidentBeginDate"),
            "incident_end_date":   it.get("incidentEndDate"),
            "designated_area":     it.get("designatedArea"),
            "state":               it.get("state"),
            "fips_county_code":    it.get("fipsCountyCode"),
        }
        for it in items
    ]


async def nfip_claims_by_zip(
    client: httpx.AsyncClient, *, zip_code: str, top: int = 100
) -> dict[str, Any]:
    """Aggregate NFIP claims for a ZIP. Returns count + paid totals + recent
    sample. The endpoint exposes one row per claim — we summarize."""
    r = await client.get(
        f"{BASE}/FimaNfipClaims",
        params={
            "$filter": f"reportedZipCode eq '{zip_code}'",
            "$top":    top,
            "$select": ("dateOfLoss,amountPaidOnBuildingClaim,"
                        "amountPaidOnContentsClaim,causeOfDamage"),
            "$orderby": "dateOfLoss desc",
        },
    )
    r.raise_for_status()
    claims = r.json().get("FimaNfipClaims") or []
    paid_b = sum((c.get("amountPaidOnBuildingClaim") or 0) for c in claims)
    paid_c = sum((c.get("amountPaidOnContentsClaim") or 0) for c in claims)
    return {
        "zip_code":               zip_code,
        "claim_count":            len(claims),
        "total_building_paid":    round(paid_b, 2),
        "total_contents_paid":    round(paid_c, 2),
        "recent_claims":          claims[:10],
        "note": (
            "FimaNfipClaims is per-claim with redacted address; counts shown "
            "are paginated up to $top — bump for full aggregates."
        ),
    }
