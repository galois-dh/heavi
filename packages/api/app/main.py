from __future__ import annotations

import json
import os
from pathlib import Path

import asyncpg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .site_report import geocode, reverse_geocode, site_report
from .spatial_query import spatial_query
from .wildfire_loss import wildfire_loss

# Load .env from monorepo root
load_dotenv(Path(__file__).resolve().parents[3] / ".env")

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
