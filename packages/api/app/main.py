from __future__ import annotations

import json
import os
from pathlib import Path

import asyncpg
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from .data_repository import get_source_availability, get_sources_for_workflow
from .data_repository_check import check_source_availability
from .data_selection import select_data
from .decision_trail import RequestContext, persist_trail
from .earthquake_scoring import assess_earthquake_risk
from .earthquake_scoring import methodology_doc as earthquake_methodology_doc
from .flood_scoring import MODULE_NAME as FLOOD_MODULE
from .flood_scoring import MODULE_VERSION as FLOOD_VERSION
from .flood_scoring import assess_flood_risk
from .flood_scoring import methodology_doc as flood_methodology_doc
from .methodology_repository import (
    get_all_source_ids_for_workflow,
    get_methodology_doc,
)
from .portfolio_pdf import render_pdf
from .portfolio_risk import (
    MAX_ROWS,
    get_job,
    job_to_response,
    parse_csv,
    run_portfolio,
)
from .site_report import geocode, reverse_geocode, site_report
from .solar_scoring import (
    build_config,
    methodology_doc,
    parse_csv_addresses,
    parse_geojson,
    run_discover_mode,
    run_score_mode,
)
from .solar_scoring_v2 import score_solar_siting as solar_v2_score
from .spatial_query import spatial_query
from .trade_area_scoring import discover_trade_area, score_trade_area
from .trade_area_scoring import methodology_doc as trade_area_methodology_doc
from .wildfire_loss import wildfire_loss

# Best-effort .env load — for local dev where the file lives at the monorepo
# root (~/heavi/.env). On Railway/Render the file at /app/app/main.py only has
# 3 parents so parents[3] would IndexError; we guard the depth check and skip
# silently when the path can't be resolved. Hosted envs inject vars directly.
_parents = Path(__file__).resolve().parents
if len(_parents) >= 4:
    load_dotenv(_parents[3] / ".env")

app = FastAPI(title="Heavi API", version="0.1.0")

# ALLOWED_ORIGINS is a comma-separated list of allowed Origin headers, e.g.
# "https://heavi.vercel.app,http://localhost:3000". Defaults to localhost:3000
# for dev. Trailing slashes/blank entries are tolerated.
_origins_env = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
_allowed_origins = [o.strip().rstrip("/") for o in _origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

pool: asyncpg.Pool | None = None


async def _init_connection(conn: asyncpg.Connection) -> None:
    # asyncpg returns jsonb as str by default; decode to dict so FastAPI
    # serializes nested features as objects instead of escaped strings.
    for typename in ("json", "jsonb"):
        await conn.set_type_codec(
            typename,
            encoder=json.dumps,
            decoder=json.loads,
            schema="pg_catalog",
        )


@app.on_event("startup")
async def startup() -> None:
    global pool
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL not set")
    pool = await asyncpg.create_pool(
        database_url,
        min_size=2,
        max_size=10,
        ssl="require",
        init=_init_connection,
    )


@app.on_event("shutdown")
async def shutdown() -> None:
    if pool:
        await pool.close()


class HealthResponse(BaseModel):
    status: str
    postgis: bool


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    if not pool:
        raise HTTPException(503, "Database pool not initialized")
    try:
        async with pool.acquire() as conn:
            result = await conn.fetchval("SELECT PostGIS_Version()")
            return HealthResponse(status="ok", postgis=result is not None)
    except Exception:
        return HealthResponse(status="degraded", postgis=False)


class LayerSummary(BaseModel):
    name: str
    geometry_type: str
    srid: int
    feature_count: int


@app.get("/layers", response_model=list[LayerSummary])
async def list_layers() -> list[LayerSummary]:
    if not pool:
        raise HTTPException(503, "Database pool not initialized")
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT f_table_name AS name, type AS geometry_type, srid
               FROM geometry_columns ORDER BY f_table_name"""
        )
        layers = []
        for row in rows:
            count = await conn.fetchval(f'SELECT COUNT(*) FROM "{row["name"]}"')
            layers.append(
                LayerSummary(
                    name=row["name"],
                    geometry_type=row["geometry_type"],
                    srid=row["srid"],
                    feature_count=count,
                )
            )
        return layers


# ─── Data Repository (Platform Refactor Phase 1) ───────────────────────────


@app.get("/data-sources")
async def data_sources_list(workflow: str | None = None) -> dict:
    """Heavi data catalog. Pass ?workflow=solar_siting (or hazard_assessment /
    trade_area) to filter by applicable workflow. With no filter, returns the
    full catalog so the UI / caller can render the "we know what we know" view."""
    if not pool:
        raise HTTPException(503, "Database pool not initialized")
    if workflow:
        rows = await get_sources_for_workflow(pool, workflow)
    else:
        async with pool.acquire() as conn:
            raw = await conn.fetch(
                "SELECT * FROM data_sources ORDER BY data_category, source_id"
            )
        rows = [dict(r) for r in raw]
    return {
        "workflow":      workflow,
        "source_count":  len(rows),
        "sources":       rows,
    }


@app.get("/data-sources/{source_id}/availability")
async def data_source_availability(
    source_id: str, lat: float, lng: float,
) -> dict:
    """Catalog-level availability (no live probe) per Phase 1 spec — uses
    coverage_type + coverage_states + reliability metadata to answer."""
    if not pool:
        raise HTTPException(503, "Database pool not initialized")
    return await get_source_availability(pool, source_id, latitude=lat, longitude=lng)


@app.get("/data-sources/{source_id}/check")
async def data_source_check(
    source_id: str, lat: float, lng: float,
) -> dict:
    """Source-specific live probe (per Phase 1 spec acceptance criterion #3).

    Returns the SourceResult with the actual probe data attached, so the
    Phase 3 selection engine can reuse it across criteria without re-querying.
    """
    if not pool:
        raise HTTPException(503, "Database pool not initialized")
    return (await check_source_availability(
        pool, source_id, latitude=lat, longitude=lng
    )).to_dict()


# ─── Methodology Repository (Platform Build Spec Phase 2) ──────────────────


@app.get("/methodology/{workflow_type}")
async def methodology_for_workflow(workflow_type: str) -> dict:
    """Full methodology documentation for a workflow.

    Returns framework citations, per-criterion weights + rationale + data
    sources, and the deduplicated academic source list — the same payload
    that gets attached to every scored assessment from Phase 4 onward."""
    if not pool:
        raise HTTPException(503, "Database pool not initialized")
    doc = await get_methodology_doc(pool, workflow_type)
    if doc["criteria_count"] == 0:
        raise HTTPException(404, f"no criteria registered for workflow '{workflow_type}'")
    return doc


class SolarScoreV2Request(BaseModel):
    latitude: float
    longitude: float
    weights_override: dict[str, float] | None = None


@app.post("/solar/score-v2")
async def solar_score_v2(req: SolarScoreV2Request) -> dict:
    """Phase 4 — single-location solar siting score consuming the data
    selection engine. Returns score + rating + criteria_scores + exclusions
    + full confidence report + methodology documentation.

    The legacy CSV-batch endpoint at POST /solar/score is unchanged."""
    if not pool:
        raise HTTPException(503, "Database pool not initialized")
    return await solar_v2_score(
        pool, req.latitude, req.longitude, req.weights_override,
    )


@app.get("/data-selection")
async def data_selection_endpoint(
    workflow: str, lat: float, lng: float,
) -> dict:
    """Phase 3 selection engine — for a given workflow + location returns
    which sources were queried, which were selected per criterion, the
    per-criterion + composite confidence, gaps, strongest/weakest data, and
    the source cache so downstream scoring can reuse without re-querying."""
    if not pool:
        raise HTTPException(503, "Database pool not initialized")
    result = await select_data(pool, workflow, lat, lng)
    return result.to_dict()


@app.get("/methodology/{workflow_type}/sources")
async def methodology_source_ids(workflow_type: str) -> dict:
    """Deduplicated source_ids referenced across this workflow's data trees.
    Phase 3's resolve_sources() uses this to know what to query."""
    if not pool:
        raise HTTPException(503, "Database pool not initialized")
    ids = await get_all_source_ids_for_workflow(pool, workflow_type)
    return {"workflow_type": workflow_type, "source_count": len(ids),
            "source_ids": sorted(ids)}


class QueryRequest(BaseModel):
    question: str
    limit: int = 1000


@app.post("/query")
async def query_endpoint(req: QueryRequest) -> dict:
    if not pool:
        raise HTTPException(503, "Database pool not initialized")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(500, "ANTHROPIC_API_KEY not configured")

    result = await spatial_query(pool, req.question, api_key, req.limit)
    return result


class SiteReportRequest(BaseModel):
    latitude: float | None = None
    longitude: float | None = None
    address: str | None = None
    radius_meters: int = 1609  # 1 mile


@app.post("/site-report")
async def site_report_endpoint(req: SiteReportRequest) -> dict:
    if not pool:
        raise HTTPException(503, "Database pool not initialized")

    lat = req.latitude
    lng = req.longitude
    address = None

    if req.address:
        g = await geocode(req.address)
        if not g:
            raise HTTPException(404, f"Could not geocode: {req.address}")
        lat, lng, address = g
    elif lat is not None and lng is not None:
        address = await reverse_geocode(lat, lng) or f"{lat:.5f}, {lng:.5f}"
    else:
        raise HTTPException(400, "Provide either address or latitude+longitude")

    return await site_report(pool, lat, lng, req.radius_meters, address)


class WildfireLossRequest(BaseModel):
    latitude: float | None = None
    longitude: float | None = None
    address: str | None = None
    search_radius_m: int = 500


@app.post("/wildfire-loss")
async def wildfire_loss_endpoint(req: WildfireLossRequest) -> dict:
    if not pool:
        raise HTTPException(503, "Database pool not initialized")
    if req.latitude is None and req.longitude is None and not req.address:
        raise HTTPException(400, "Provide either address or latitude+longitude")
    try:
        return await wildfire_loss(
            pool,
            latitude=req.latitude,
            longitude=req.longitude,
            address=req.address,
            search_radius_m=req.search_radius_m,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/portfolio-risk")
async def portfolio_risk_endpoint(file: UploadFile = File(...)) -> dict:
    """Score a CSV of properties. Returns the job_id + inline results.
    Run sequentially; Nominatim ≤1 req/s so this can take ~rows×1.1 s."""
    if not pool:
        raise HTTPException(503, "Database pool not initialized")
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Empty upload")
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(413, "CSV exceeds 10 MB.")
    try:
        rows = parse_csv(raw)
    except ValueError as e:
        # Distinguish a row-cap overflow so the client can show a 413 message.
        if str(e).startswith("CSV has ") and "per-request cap" in str(e):
            raise HTTPException(413, str(e))
        raise HTTPException(400, str(e))

    job = await run_portfolio(pool, rows)
    return job_to_response(job)


@app.get("/portfolio-risk/{job_id}/report")
async def portfolio_report_endpoint(job_id: str) -> Response:
    """Generate the multi-page PDF for a previously-run portfolio job.
    Jobs live in process memory for up to an hour; restarts wipe them."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(404, f"No portfolio job {job_id} (cache miss or TTL expired)")
    pdf_bytes = render_pdf(job)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="wildfire-risk-{job_id[:8]}.pdf"'
            ),
        },
    )


@app.get("/portfolio-risk/limits")
async def portfolio_limits_endpoint() -> dict:
    """Public knobs for the upload UI so the form can show 'up to N rows'."""
    return {"max_rows": MAX_ROWS}


# ─── Trade area analysis ─────────────────────────────────────────────────────


class TradeAreaRequest(BaseModel):
    latitude: float | None = None
    longitude: float | None = None
    address: str | None = None
    business_category: str = "coffee_shop"
    custom_categories: list[str] | None = None
    existing_locations: list[dict] | None = None  # [{latitude, longitude, name?}]
    thresholds: list[float] | None = None  # drive-time minutes; default 5/10/15
    weights: dict[str, float] | None = None
    huff_beta: float = 2.0


@app.post("/trade-area/score")
async def trade_area_score_endpoint(req: TradeAreaRequest) -> dict:
    """Score Mode: drive-time isochrones → area-weighted demographics + daytime
    jobs + competitive analysis → weighted composite score, with optional Huff
    cannibalization vs. existing_locations."""
    if not pool:
        raise HTTPException(503, "Database pool not initialized")
    lat, lng, resolved = req.latitude, req.longitude, None
    if lat is None or lng is None:
        if not req.address:
            raise HTTPException(400, "Provide either address or latitude+longitude")
        from .portfolio_risk import _geocode_one

        async with httpx.AsyncClient(timeout=20.0) as client:
            g = await _geocode_one(client, req.address)
        if not g:
            raise HTTPException(404, f"Could not geocode: {req.address}")
        lat, lng, resolved = g
    try:
        return await score_trade_area(
            pool,
            latitude=lat,
            longitude=lng,
            business_category=req.business_category,
            custom_categories=req.custom_categories,
            existing_locations=req.existing_locations,
            address=req.address,
            resolved_address=resolved,
            thresholds=req.thresholds,
            weights=req.weights,
            huff_beta=req.huff_beta,
        )
    except RuntimeError as e:
        raise HTTPException(502, str(e))


class TradeAreaDiscoverRequest(BaseModel):
    geography: str | list[float] = "dallas"
    business_category: str = "coffee_shop"
    min_population: float = 30000.0
    max_competitive_density: float | None = None
    top_n: int = 25


@app.post("/trade-area/discover")
async def trade_area_discover_endpoint(req: TradeAreaDiscoverRequest) -> dict:
    """Discover Mode: grid-scan a geography for promising candidate locations using
    straight-line-buffer proxies (no external API calls). Returns top_n candidates."""
    if not pool:
        raise HTTPException(503, "Database pool not initialized")
    top_n = max(1, min(req.top_n, 200))
    return await discover_trade_area(
        pool,
        geography=req.geography,
        business_category=req.business_category,
        min_population=req.min_population,
        max_competitive_density=req.max_competitive_density,
        top_n=top_n,
    )


@app.get("/trade-area/methodology")
async def trade_area_methodology_endpoint() -> dict:
    """Trade-area methodology: pipeline, data sources, ACS variables, limitations."""
    return trade_area_methodology_doc()


# ─── Flood risk ────────────────────────────────────────────────────────────


class FloodRiskRequest(BaseModel):
    latitude: float | None = None
    longitude: float | None = None
    address: str | None = None


@app.post("/flood/risk")
async def flood_risk_endpoint(req: FloodRiskRequest) -> dict:
    """Single-property flood risk assessment (lat/lng or address). Hazard and
    exposure data are queried on-demand from FEMA NFHL, USACE NSI, and USGS 3DEP.
    Every call produces a decision trail (returned on the response and persisted
    to the decision_trails audit table)."""
    if not pool:
        raise HTTPException(503, "Database pool not initialized")
    lat = req.latitude
    lng = req.longitude
    resolved_address = None
    if lat is None or lng is None:
        if not req.address:
            raise HTTPException(400, "Provide either address or latitude+longitude")
        from .portfolio_risk import _geocode_one

        async with httpx.AsyncClient(timeout=20.0) as client:
            g = await _geocode_one(client, req.address)
        if not g:
            raise HTTPException(404, f"Could not geocode: {req.address}")
        lat, lng, resolved_address = g

    ctx = RequestContext.begin(pool, module=FLOOD_MODULE, module_version=FLOOD_VERSION)
    result = await assess_flood_risk(
        ctx,
        latitude=lat,
        longitude=lng,
        address=req.address,
        resolved_address=resolved_address,
    )
    finalized = ctx.finalize(scored_output=result)
    inputs = {
        "address": req.address, "latitude": lat, "longitude": lng,
        "resolved_address": resolved_address,
    }
    await persist_trail(pool, finalized=finalized, inputs=inputs)
    return {**result, "decision_trail": finalized}


@app.get("/flood/methodology")
async def flood_methodology_endpoint() -> dict:
    """Full flood methodology: pipeline, data sources, HAZUS citations,
    annual-probability assumptions, configurable defaults, and limitations."""
    return flood_methodology_doc()


# ─── Earthquake risk ───────────────────────────────────────────────────────


class EarthquakeRiskRequest(BaseModel):
    latitude: float | None = None
    longitude: float | None = None
    address: str | None = None


@app.post("/earthquake/risk")
async def earthquake_risk_endpoint(req: EarthquakeRiskRequest) -> dict:
    """Single-property earthquake risk assessment (lat/lng or address). Hazard
    (USGS ASCE 7-22), site amplification (3DEP + Wald & Allen), and exposure
    (USACE NSI) are queried on-demand. No pre-loading required."""
    lat = req.latitude
    lng = req.longitude
    resolved_address = None
    if lat is None or lng is None:
        if not req.address:
            raise HTTPException(400, "Provide either address or latitude+longitude")
        from .portfolio_risk import _geocode_one

        async with httpx.AsyncClient(timeout=20.0) as client:
            g = await _geocode_one(client, req.address)
        if not g:
            raise HTTPException(404, f"Could not geocode: {req.address}")
        lat, lng, resolved_address = g
    try:
        return await assess_earthquake_risk(
            latitude=lat,
            longitude=lng,
            address=req.address,
            resolved_address=resolved_address,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/earthquake/methodology")
async def earthquake_methodology_endpoint() -> dict:
    """Full earthquake methodology: USGS ASCE 7-22 + Wald & Allen VS30 + HAZUS
    fragility curves, citations, code-level defaults, and known limitations."""
    return earthquake_methodology_doc()


# ─── Solar site suitability ───────────────────────────────────────────────


@app.post("/solar/score")
async def solar_score_endpoint(
    file: UploadFile = File(...),
    options: str | None = Form(default=None),
) -> dict:
    """Score Mode. Accepts a GeoJSON FeatureCollection (.geojson/.json) of parcel
    polygons or points, or a CSV of addresses / lat-lng pairs. `options` is an
    optional JSON string of config overrides (min_acreage, max_slope, weights, …)."""
    if not pool:
        raise HTTPException(503, "Database pool not initialized")
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Empty upload")
    if len(raw) > 25 * 1024 * 1024:
        raise HTTPException(413, "Upload exceeds 25 MB.")

    overrides = None
    if options:
        try:
            overrides = json.loads(options)
        except ValueError:
            raise HTTPException(400, "`options` is not valid JSON.")
    cfg = build_config(overrides)

    name = (file.filename or "").lower()
    stripped = raw.lstrip()
    is_geojson = name.endswith((".geojson", ".json")) or stripped[:1] in (b"{", b"[")
    try:
        if is_geojson:
            parcels = parse_geojson(raw)
            to_geocode: list[tuple[str, str]] = []
        else:
            parcels, to_geocode = parse_csv_addresses(raw)
    except ValueError as e:
        raise HTTPException(400, str(e))

    if len(parcels) > 1000:
        raise HTTPException(413, f"{len(parcels)} parcels exceeds the 1000-per-request cap.")

    # Forward-geocode address-only rows (Nominatim ≤1 req/s when no Mapbox token).
    if to_geocode:
        import asyncio
        import time

        from .portfolio_risk import _active_geocoder
        from .solar_scoring import _geocode

        by_id = {p.parcel_id: p for p in parcels}
        throttle = _active_geocoder() == "nominatim"
        async with httpx.AsyncClient(timeout=20.0) as client:
            last = 0.0
            for pid, address in to_geocode:
                if throttle:
                    elapsed = time.perf_counter() - last
                    if elapsed < 1.05:
                        await asyncio.sleep(1.05 - elapsed)
                    last = time.perf_counter()
                g = await _geocode(client, address)
                if g and pid in by_id:
                    by_id[pid].lat, by_id[pid].lng = g[0], g[1]
                elif pid in by_id:
                    by_id[pid].note = f"geocoding failed: {address!r}"

    return await run_score_mode(pool, parcels, cfg)


class SolarDiscoverRequest(BaseModel):
    geography: str | list[float] = "kern"
    top_n: int = 25
    min_acreage: float | None = None
    max_slope: float | None = None
    weights: dict[str, float] | None = None


@app.post("/solar/discover")
async def solar_discover_endpoint(req: SolarDiscoverRequest) -> dict:
    """Discover Mode. Identify candidate parcels within a geography ("kern" or a
    [min_lng, min_lat, max_lng, max_lat] bbox) and return the top-N ranked."""
    if not pool:
        raise HTTPException(503, "Database pool not initialized")
    cfg = build_config(
        {"min_acreage": req.min_acreage, "max_slope": req.max_slope, "weights": req.weights}
    )
    top_n = max(1, min(req.top_n, 200))
    return await run_discover_mode(pool, req.geography, cfg, top_n=top_n)


@app.get("/solar/methodology")
async def solar_methodology_endpoint() -> dict:
    """Full methodology: citations, weight justification, data sources with
    vintages, configurable thresholds with defaults/rationale, and limitations."""
    return methodology_doc()


@app.get("/portfolio-risk/sample.csv")
async def portfolio_sample_endpoint() -> Response:
    """Serve the canonical 50-address Sonoma sample CSV. The file lives
    INSIDE the `app` package (sibling to this module) so it ships with the
    Python package whether Railway runs from source (CWD-relative) or
    installs the package into site-packages (Nixpacks default for pyproject
    projects). Setuptools package-data in pyproject.toml ensures the CSV is
    bundled in the wheel. Resolution tries a handful of candidate paths so
    a slightly different layout (e.g. editable install vs build copy) still
    finds the file."""
    _here = Path(__file__).resolve().parent
    candidates = [
        # Override hatch (ops can pin an absolute path).
        Path(os.environ["PORTFOLIO_SAMPLE_PATH"]).expanduser()
        if os.getenv("PORTFOLIO_SAMPLE_PATH")
        else None,
        # Primary location — sibling to main.py, inside the package.
        _here / "sample_portfolio.csv",
        # Legacy location — kept as a fallback in case an older deploy
        # still has the file one level up.
        _here.parent / "sample_portfolio.csv",
    ]
    for path in candidates:
        if path is None:
            continue
        if path.exists():
            return Response(
                content=path.read_bytes(),
                media_type="text/csv",
                headers={
                    "Content-Disposition": 'attachment; filename="heavi_sample_portfolio.csv"',
                },
            )
    tried = "\n  ".join(str(p) for p in candidates if p is not None)
    raise HTTPException(
        404, f"sample_portfolio.csv not found. Tried:\n  {tried}"
    )
