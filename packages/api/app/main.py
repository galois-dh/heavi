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

from .flood_scoring import assess_flood_risk
from .flood_scoring import methodology_doc as flood_methodology_doc
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
from .spatial_query import spatial_query
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


# ─── Flood risk ────────────────────────────────────────────────────────────


class FloodRiskRequest(BaseModel):
    latitude: float | None = None
    longitude: float | None = None
    address: str | None = None


@app.post("/flood/risk")
async def flood_risk_endpoint(req: FloodRiskRequest) -> dict:
    """Single-property flood risk assessment (lat/lng or address). Hazard and
    exposure data are queried on-demand from FEMA NFHL, USACE NSI, and USGS 3DEP."""
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
    return await assess_flood_risk(
        pool,
        latitude=lat,
        longitude=lng,
        address=req.address,
        resolved_address=resolved_address,
    )


@app.get("/flood/methodology")
async def flood_methodology_endpoint() -> dict:
    """Full flood methodology: pipeline, data sources, HAZUS citations,
    annual-probability assumptions, configurable defaults, and limitations."""
    return flood_methodology_doc()


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
