"""NERC reliability-region segmentation (Heavi Weight Adaptation Spec, Step 1).

The weight-adaptation layer calibrates solar-siting criterion weights per NERC
region. This module holds the canonical state→NERC mapping used both to build
the `nerc_regions` polygon layer (state polygons dissolved by membership) and to
sample EIA installations by region, plus the runtime lookup that maps an
arbitrary location to its region via ST_Contains.

The mapping is intentionally single-region-per-state. The spec's region table
lists "States (approx)" and explicitly permits a simple lookup; assigning each
state to exactly one region makes the dissolved polygons disjoint, so any CONUS
point maps to exactly one region. AK/HI (ASCC/HICC, outside the seven listed
NERC regions) are deliberately unmapped — points there fall back to literature
default weights.
"""

from __future__ import annotations

import asyncpg

# region → human-readable name
NERC_REGION_NAMES: dict[str, str] = {
    "WECC":  "Western Electricity Coordinating Council",
    "ERCOT": "Electric Reliability Council of Texas",
    "SPP":   "Southwest Power Pool",
    "MISO":  "Midcontinent Independent System Operator",
    "PJM":   "PJM Interconnection",
    "SERC":  "SERC Reliability Corporation",
    "NPCC":  "Northeast Power Coordinating Council",
}

# Canonical single-region-per-state membership (postal codes). Approximates the
# spec's region table; AK and HI are intentionally absent (no listed NERC region).
STATE_TO_NERC: dict[str, str] = {
    # WECC — Western Interconnect
    "CA": "WECC", "NV": "WECC", "AZ": "WECC", "CO": "WECC", "UT": "WECC",
    "NM": "WECC", "OR": "WECC", "WA": "WECC", "MT": "WECC", "WY": "WECC",
    "ID": "WECC",
    # ERCOT — Texas
    "TX": "ERCOT",
    # SPP — Great Plains
    "OK": "SPP", "KS": "SPP", "NE": "SPP", "SD": "SPP", "ND": "SPP",
    # MISO — Upper Midwest + Mid-South
    "MN": "MISO", "WI": "MISO", "IA": "MISO", "IL": "MISO", "IN": "MISO",
    "MI": "MISO", "MO": "MISO", "AR": "MISO", "LA": "MISO",
    # PJM — Mid-Atlantic
    "PA": "PJM", "NJ": "PJM", "OH": "PJM", "VA": "PJM", "WV": "PJM",
    "MD": "PJM", "DE": "PJM", "KY": "PJM", "DC": "PJM",
    # SERC — Southeast
    "NC": "SERC", "SC": "SERC", "GA": "SERC", "AL": "SERC", "TN": "SERC",
    "MS": "SERC", "FL": "SERC",
    # NPCC — Northeast
    "NY": "NPCC", "ME": "NPCC", "NH": "NPCC", "VT": "NPCC", "MA": "NPCC",
    "RI": "NPCC", "CT": "NPCC",
}


def states_for_region(region: str) -> list[str]:
    """Postal codes belonging to `region`."""
    return sorted(s for s, r in STATE_TO_NERC.items() if r == region)


async def get_nerc_region(
    pool: asyncpg.Pool, latitude: float, longitude: float
) -> str | None:
    """Return the NERC region containing (lat, lng), or None if the point is
    outside all loaded regions (offshore, AK/HI, or nerc_regions not loaded)."""
    try:
        async with pool.acquire() as conn:
            return await conn.fetchval(
                """
                SELECT region FROM nerc_regions
                WHERE ST_Contains(geometry, ST_SetSRID(ST_MakePoint($1, $2), 4326))
                LIMIT 1
                """,
                longitude, latitude,
            )
    except Exception:  # noqa: BLE001 — table missing or PostGIS error → default weights
        return None
