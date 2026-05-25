"""Ten Alameda County calibration scenarios for the site_suitability module.

Expected ranges were derived analytically from the documented scoring rubric
plus public knowledge of each location's flood zone, transit, environmental,
and density characteristics. Each case lists the dominant factor(s) driving
the expected band; mismatches between expected and predicted in the
calibration report should be interpreted against this justification.
"""

from __future__ import annotations

from heavi_validation.harness import TestCase

ALAMEDA_TEST_CASES: list[TestCase] = [
    # ─── HIGH-SCORE (3) ──────────────────────────────────────────────────────
    TestCase(
        id="H1",
        name="Rockridge BART, Oakland",
        inputs={"latitude": 37.8444, "longitude": -122.2509},
        expected_score=82.0,
        expected_range=(75.0, 92.0),
        justification=(
            "Residential-commercial neighborhood centered on Rockridge BART. "
            "Outside any FEMA SFHA, inside a populated ACS tract, ≥5 transit "
            "stops within 1 mi (BART + AC Transit 51A/79). No EPA facilities "
            "in the immediate radius, not in a FHSZ. POI count likely in the "
            "30–80 sweet-spot band along College Ave."
        ),
        expected_factors={
            "flood_risk": (100, 100),
            "demographics": (75, 75),
            "transit_access": (60, 100),
            "environmental": (60, 100),
        },
        tags=["high", "transit", "tod"],
    ),
    TestCase(
        id="H2",
        name="North Berkeley BART / Solano Ave",
        inputs={"latitude": 37.8740, "longitude": -122.2830},
        expected_score=82.0,
        expected_range=(75.0, 92.0),
        justification=(
            "Walkable residential neighborhood adjacent to North Berkeley BART "
            "and the Solano Ave commercial strip. Outside SFHA, inside ACS "
            "tract, ≥5 stops, low EPA density, not in FHSZ, moderate POI."
        ),
        expected_factors={
            "flood_risk": (100, 100),
            "demographics": (75, 75),
            "transit_access": (60, 100),
            "environmental": (60, 100),
        },
        tags=["high", "transit", "tod"],
    ),
    TestCase(
        id="H3",
        name="Downtown Alameda — Park Street",
        inputs={"latitude": 37.7660, "longitude": -122.2425},
        expected_score=78.0,
        expected_range=(70.0, 88.0),
        justification=(
            "Main commercial corridor on Alameda island. The Park St spine "
            "sits on higher ground than the perimeter and is mapped outside "
            "the SFHA. AC Transit lines 19/51A/96 thread the corridor; "
            "POI density is moderate (1-mi buffer reaches mid-island)."
        ),
        expected_factors={
            "flood_risk": (100, 100),
            "demographics": (75, 75),
            "transit_access": (40, 100),
        },
        tags=["high", "main-street"],
    ),
    # ─── MID-SCORE (4) ───────────────────────────────────────────────────────
    TestCase(
        id="M1",
        name="Downtown Oakland — 12th St BART",
        inputs={"latitude": 37.8044, "longitude": -122.2712},
        expected_score=66.0,
        expected_range=(55.0, 78.0),
        justification=(
            "Maximum transit and demographics scores, but 1-mi buffer captures "
            "hundreds of Overture POIs → competition curve enters the saturation "
            "regime (likely floor at 20). One or more EPA-listed facilities in "
            "downtown's industrial-adjacent fringe pulls the environmental "
            "factor below 100. Net composite lands in the mid-60s."
        ),
        expected_factors={
            "flood_risk": (100, 100),
            "demographics": (75, 75),
            "transit_access": (100, 100),
            "competition": (20, 60),
        },
        tags=["mid", "downtown", "competition-saturated"],
    ),
    TestCase(
        id="M2",
        name="Downtown Hayward — Hayward BART",
        inputs={"latitude": 37.6688, "longitude": -122.0808},
        expected_score=66.0,
        expected_range=(55.0, 78.0),
        justification=(
            "Hayward BART + downtown civic core. Outside SFHA, inside tract, "
            "5+ transit, but eastern hills push the 1-mi buffer into a CalFire "
            "moderate FHSZ band → environmental penalty likely. POI density "
            "moderate-high but not saturated."
        ),
        expected_factors={
            "flood_risk": (100, 100),
            "demographics": (75, 75),
            "transit_access": (80, 100),
        },
        tags=["mid", "transit", "fhsz-edge"],
    ),
    TestCase(
        id="M3",
        name="San Leandro residential",
        inputs={"latitude": 37.7249, "longitude": -122.1561},
        expected_score=62.0,
        expected_range=(50.0, 72.0),
        justification=(
            "Quiet residential block ~1 mi from San Leandro BART. Outside SFHA, "
            "inside tract. Transit access depends on whether BART falls inside "
            "the 1-mi buffer; AC Transit lines partially cover it. Low POI, "
            "low EPA, no FHSZ — pulled down primarily by transit & competition "
            "both landing mid-range."
        ),
        tags=["mid", "suburban"],
    ),
    TestCase(
        id="M4",
        name="Pleasanton residential",
        inputs={"latitude": 37.6624, "longitude": -121.8747},
        expected_score=56.0,
        expected_range=(45.0, 68.0),
        justification=(
            "Far East Bay residential. Outside SFHA, inside tract, but transit "
            "is sparse outside the I-580 corridor — likely <5 stops in the "
            "buffer. Low competition, no FHSZ, no EPA. Score pulled down by "
            "transit_access."
        ),
        expected_factors={
            "flood_risk": (100, 100),
            "demographics": (75, 75),
            "transit_access": (0, 80),
        },
        tags=["mid", "suburban", "low-transit"],
    ),
    # ─── LOW-SCORE (3) ───────────────────────────────────────────────────────
    TestCase(
        id="L1",
        name="Oakland Coliseum / Doolittle industrial — SFHA",
        inputs={"latitude": 37.7470, "longitude": -122.1980},
        expected_score=42.0,
        expected_range=(28.0, 55.0),
        justification=(
            "Industrial strip between Coliseum and the airport. Squarely "
            "inside FEMA SFHA (flood_risk = 0). Multiple EPA-listed facilities "
            "expected within the radius → environmental factor sharply "
            "discounted. Coliseum BART within 1 mi provides high transit but "
            "stadium-area POI density likely saturates competition near floor."
        ),
        expected_factors={
            "flood_risk": (0, 0),
            "environmental": (0, 60),
        },
        tags=["low", "sfha", "environmental"],
    ),
    TestCase(
        id="L2",
        name="Bay Farm Island shoreline, Alameda — SFHA",
        inputs={"latitude": 37.7240, "longitude": -122.2545},
        expected_score=48.0,
        expected_range=(35.0, 60.0),
        justification=(
            "Coastal residential edge of Bay Farm Island. FEMA-mapped SFHA "
            "(Zone AE coastal) → flood_risk = 0. Inside tract but transit and "
            "POI density are low at the island's perimeter. No EPA / FHSZ "
            "penalty, so environmental stays at 100 — the score is pulled "
            "down by flood and transit."
        ),
        expected_factors={
            "flood_risk": (0, 0),
            "demographics": (75, 75),
        },
        tags=["low", "sfha", "coastal"],
    ),
    TestCase(
        id="L3",
        name="Niles Canyon / Sunol unincorporated",
        inputs={"latitude": 37.5860, "longitude": -121.9510},
        expected_score=50.0,
        expected_range=(35.0, 62.0),
        justification=(
            "Rural canyon between Fremont and Sunol. Outside SFHA but the area "
            "is mapped within the CalFire High FHSZ → environmental factor "
            "drops by 40. Effectively zero transit stops within 1 mi, near-zero "
            "POI density → competition floors at 40. May fall outside any "
            "populated ACS tract polygon, dropping demographics to 40."
        ),
        expected_factors={
            "transit_access": (0, 20),
            "environmental": (40, 80),
        },
        tags=["low", "fhsz", "rural"],
    ),
]
