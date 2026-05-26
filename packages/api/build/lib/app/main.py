from __future__ import annotations

import json
import os
from pathlib import Path

import asyncpg
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from .portfolio_pdf import render_pdf
from .portfolio_risk import (
    MAX_ROWS,
    get_job,
    job_to_response,
    parse_csv,
    run_portfolio,
)
from .site_report import geocode, reverse_geocode, site_report
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
