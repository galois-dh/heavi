"""Structured metadata for the site_suitability module.

Drives the methodology document generator. Edit this file (not the markdown)
when data sources, parameters, references, or limitations change — the doc is
regenerated from this source of truth and its hash will change accordingly.
"""

from __future__ import annotations

from heavi_validation.methodology import (
    DataSource,
    Limitation,
    ModuleMetadata,
    Parameter,
    Reference,
)

METADATA = ModuleMetadata(
    name="site_suitability",
    version="0.1.0",
    description=(
        "Composite site-suitability score (0–100) for a point location, "
        "synthesizing flood risk, served demographics, transit access, "
        "environmental hazards, and competition density."
    ),
    methodology_summary=(
        "The module evaluates a candidate site against five orthogonal factors, "
        "each scored 0–100 on a documented rubric, and returns an unweighted "
        "arithmetic mean as the composite score. Each factor is computed by a "
        "deterministic PostGIS query against an authoritative public dataset, "
        "evaluated within a configurable analysis radius (default 1 mile / "
        "1609 m). The composite is intentionally simple and transparent: an "
        "auditor can independently reproduce any factor by running the "
        "documented SQL against the same data snapshot."
    ),
    data_sources=[
        DataSource(
            name="FEMA National Flood Hazard Layer (NFHL)",
            description=(
                "Special Flood Hazard Areas (SFHA) — Zones A/AE/V/VE corresponding "
                "to the 1%-annual-chance flood (100-year floodplain)."
            ),
            provenance="FEMA Map Service Center, NFHL v2 (clipped to Alameda County)",
            license="Public domain (U.S. Federal Government work)",
            url="https://msc.fema.gov/portal/advanceSearch",
            table_name="catalog_fema_flood",
        ),
        DataSource(
            name="U.S. Census ACS demographics",
            description="American Community Survey 5-year estimates at census-tract resolution.",
            provenance="U.S. Census Bureau, ACS 2019–2023 5-yr",
            license="Public domain",
            url="https://www.census.gov/programs-surveys/acs",
            table_name="catalog_census_demographics",
        ),
        DataSource(
            name="GTFS transit stops",
            description="Public transit stop locations aggregated from regional GTFS feeds.",
            provenance="Bay Area transit operators (BART, AC Transit, etc.) via 511.org",
            license="Open data, varies by operator",
            url="https://511.org/open-data",
            table_name="catalog_transit_stops",
        ),
        DataSource(
            name="EPA Facility Registry Service (FRS)",
            description="Regulated environmental facilities (TRI/RCRA/CERCLA/Brownfields).",
            provenance="EPA FRS, 2024",
            license="Public domain",
            url="https://www.epa.gov/frs",
            table_name="catalog_epa_facilities",
        ),
        DataSource(
            name="CalFire Fire Hazard Severity Zones (FHSZ)",
            description="State-mapped Moderate / High / Very-High fire hazard severity zones.",
            provenance="CAL FIRE FRAP, 2022 FHSZ map",
            license="Public domain",
            url="https://osfm.fire.ca.gov/divisions/community-wildfire-preparedness-and-mitigation/wildland-hazards-building-codes/fire-hazard-severity-zones-maps/",
            table_name="catalog_calfire_fhsz",
        ),
        DataSource(
            name="Overture Maps POIs",
            description="Points of interest used to estimate commercial competition density.",
            provenance="Overture Maps Foundation 2024-10 release",
            license="ODbL / CDLA-Permissive (varies per feature)",
            url="https://overturemaps.org/",
            table_name="catalog_overture_pois",
        ),
    ],
    methodology_steps=[
        "Geocode the request address to (lat, lng) if needed (Nominatim/OSM); "
        "otherwise use supplied coordinates directly.",
        "Construct a circular analysis buffer of `radius_meters` (default 1609 m) "
        "around the point in EPSG:3857, transformed back to EPSG:4326.",
        "**Flood:** `flood_risk = 0 if point ∈ FEMA SFHA polygon else 100`. "
        "Boolean containment, no soft margin.",
        "**Transit:** count GTFS stops intersecting the buffer; "
        "`transit_access = min(100, round(count / 5 * 100))`. "
        "Saturates at ≥5 stops within the radius.",
        "**Demographics:** `demographics = 75 if the point lies in a populated "
        "ACS tract else 40`. A coarse proxy for 'served area' coverage.",
        "**Environmental:** start at 100, subtract 20 per EPA facility within "
        "the buffer, subtract 40 if the point lies in any CalFire FHSZ polygon; "
        "floor at 0.",
        "**Competition:** count Overture POIs intersecting the buffer. "
        "0 POIs → 40 (dead zone). 1–30 POIs → 40 + (count/30)*40 (linear ramp "
        "to a 'sweet spot' of 80). >30 POIs → 80 − (count − 30) / 3 (saturation "
        "penalty), floored at 20.",
        "Composite = unweighted arithmetic mean of the five factor scores, "
        "rounded to the nearest integer.",
        "Return the composite, the per-factor breakdown, raw counts, and the "
        "three nearest schools, transit stops, and EPA facilities.",
    ],
    parameters=[
        Parameter(
            name="radius_meters",
            value=1609,
            unit="m",
            justification=(
                "1 statute mile — the de-facto pedestrian catchment used in U.S. "
                "transit-oriented-development literature (Cervero & Kockelman, "
                "1997). Lets transit-access and competition factors compare like-for-like "
                "with TOD studies and standard retail trade-area analyses."
            ),
        ),
        Parameter(
            name="transit_saturation",
            value=5,
            unit="stops",
            justification=(
                "Five stops within 1 mile is the empirical inflection point above "
                "which marginal accessibility gains diminish in NCHRP Report 684 "
                "transit-access scoring."
            ),
        ),
        Parameter(
            name="competition_sweet_spot",
            value=30,
            unit="POIs",
            justification=(
                "Roughly the mid-point of the commercial-cluster density observed "
                "in Glaeser & Gottlieb (2009) urban-agglomeration data — sufficient "
                "co-location to drive foot-traffic spillover without saturation."
            ),
        ),
        Parameter(
            name="environmental_per_facility_penalty",
            value=20,
            unit="points",
            justification=(
                "Calibrated so five EPA facilities within the radius reduces the "
                "factor score to zero, matching the OEHHA CalEnviroScreen 4.0 "
                "convention of using facility density as a categorical risk indicator."
            ),
        ),
        Parameter(
            name="fire_hazard_penalty",
            value=40,
            unit="points",
            justification=(
                "FHSZ containment is a binary regulatory designation in CA Public "
                "Resources Code §4201–4204; a 40-point penalty makes a fire-zone "
                "site uncompetitive on the environmental factor unless EPA hazards "
                "are absent. Threshold chosen so a fire-zone-only site still scores "
                "60/100, reflecting that mitigation (defensible space, materials) "
                "is feasible."
            ),
        ),
        Parameter(
            name="composite_aggregation",
            value="unweighted_mean",
            justification=(
                "Equal weighting is the most defensible default in the absence of a "
                "domain-specific weight elicitation (Saaty, 1980, AHP). Re-weighting "
                "should be done explicitly in a downstream module rather than baked "
                "into the base score."
            ),
        ),
    ],
    references=[
        Reference(
            citation=(
                "Cervero, R. & Kockelman, K. (1997). Travel demand and the 3Ds: "
                "Density, Diversity, and Design. Transportation Research Part D."
            ),
            kind="peer-reviewed",
        ),
        Reference(
            citation=(
                "Glaeser, E. L. & Gottlieb, J. D. (2009). The Wealth of Cities: "
                "Agglomeration Economies and Spatial Equilibrium in the United States. "
                "Journal of Economic Literature."
            ),
            kind="peer-reviewed",
        ),
        Reference(
            citation="Saaty, T. L. (1980). The Analytic Hierarchy Process. McGraw-Hill.",
            kind="framework",
        ),
        Reference(
            citation=(
                "OEHHA (2021). CalEnviroScreen 4.0 — methodology for cumulative "
                "environmental risk scoring."
            ),
            url="https://oehha.ca.gov/calenviroscreen",
            kind="framework",
        ),
        Reference(
            citation=(
                "FEMA (2020). Guidelines and Standards for Flood Risk Analysis and "
                "Mapping — Special Flood Hazard Area determination."
            ),
            url="https://www.fema.gov/flood-maps/guidance-partners",
            kind="standard",
        ),
        Reference(
            citation=(
                "California Public Resources Code §4201–4204 — Fire Hazard Severity "
                "Zone designation."
            ),
            kind="standard",
        ),
        Reference(
            citation=(
                "TRB (2013). NCHRP Report 684 — Estimating Demand and Benefits "
                "of Vibrant Walkable Mixed-Use Centers."
            ),
            kind="report",
        ),
    ],
    limitations=[
        Limitation(
            description=(
                "Boolean flood containment ignores SFHA proximity. A site 5 m "
                "outside the SFHA polygon scores identically to one 5 km away."
            ),
            severity="high",
            mitigation=(
                "Adopt a distance-decay penalty (e.g. linear 0→100 across the 0–200 m "
                "buffer) once we ingest FEMA depth grids."
            ),
        ),
        Limitation(
            description=(
                "Demographics factor only checks census-tract presence, not "
                "tract-level income, age, or population density."
            ),
            severity="high",
            mitigation=(
                "Replace with multi-variable scoring once ACS variables are "
                "joined onto catalog_census_demographics."
            ),
        ),
        Limitation(
            description=(
                "Transit count is unweighted by mode (a bus stop counts the same "
                "as a BART station) and ignores service frequency."
            ),
            severity="medium",
            mitigation="Ingest GTFS schedules; weight by trips-per-peak-hour.",
        ),
        Limitation(
            description=(
                "Competition POI curve is a heuristic; it has not been calibrated "
                "against revealed-preference retail location data."
            ),
            severity="medium",
            mitigation=(
                "Calibrate against historical site-success outcomes once we have "
                "a labelled training set."
            ),
        ),
        Limitation(
            description=(
                "EPA facility count is uniform-weighted; a Superfund site counts "
                "the same as a small dry-cleaner."
            ),
            severity="medium",
            mitigation="Weight by EPA program (CERCLA > RCRA > TRI > FRS-only).",
        ),
        Limitation(
            description=(
                "Unweighted-mean aggregation lets a single strong factor mask "
                "another critical one (e.g. an SFHA site can still score 60+ if "
                "the other four factors are high)."
            ),
            severity="medium",
            mitigation=(
                "Expose a `hard_disqualifier` flag (SFHA or VH-FHSZ) to downstream "
                "consumers."
            ),
        ),
        Limitation(
            description=(
                "Geocoding uses Nominatim with rate-limited public endpoint; "
                "high-volume callers should pre-resolve coordinates."
            ),
            severity="low",
        ),
    ],
    authors=["Heavi platform team"],
)
