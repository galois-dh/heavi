"""Load the LBNL "Queued Up" ISO interconnection queue (Heavi, Feature 4 — real data).

Source: Lawrence Berkeley National Laboratory, *Queued Up* (interconnection queue
data through 2025), file ``data/interconnection/LBNL_Ix_Queue_Data_File_thru2025.xlsx``,
sheet ``03. Complete Queue Data``. LBNL aggregates the ISO/RTO and major-utility
interconnection queues into one normalized national table.

This loader extracts every **active solar** project (``q_status == 'active'`` and
``type_clean in {'Solar', 'Solar+Battery'}``) and loads it into
``interconnection_queue``, replacing the prior representative dataset.

Coordinates: the LBNL file has no lat/lon, so each project is placed at its
**county centroid** (5-digit FIPS → Census 2024 Gazetteer county internal point).
The ~handful of rows without a usable FIPS are geocoded from "county, state" and
skipped if that also fails. County-centroid precision is appropriate for the
50 km proximity context (which counts nearby queue activity); it is NOT a precise
project location. Provenance is flagged ``data_source='lbnl_queued_up_2025'``.

Usage:
    cd packages/api && source .venv/bin/activate && python load_interconnection_queue.py
"""

from __future__ import annotations

import asyncio
import io
import os
import sys
import zipfile
from pathlib import Path

import asyncpg
import httpx
import openpyxl
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.geocoding import geocode  # noqa: E402

MIGRATION = Path(__file__).resolve().parent / "migrations" / "2026-06-08_interconnection_queue.sql"
DATA_DIR = REPO_ROOT / "data" / "interconnection"
XLSX = DATA_DIR / "LBNL_Ix_Queue_Data_File_thru2025.xlsx"
SHEET = "03. Complete Queue Data"
GAZ_CACHE = DATA_DIR / "2024_Gaz_counties_national.txt"
GAZ_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
    "2024_Gazetteer/2024_Gaz_counties_national.zip"
)

SOLAR_TYPES = {"Solar", "Solar+Battery"}
DATA_SOURCE = "lbnl_queued_up_2025"


def _county_centroids() -> dict[str, tuple[float, float]]:
    """FIPS (5-digit) → (lat, lon) from the Census 2024 county gazetteer."""
    if not GAZ_CACHE.exists():
        print("downloading Census county gazetteer …")
        r = httpx.get(GAZ_URL, timeout=120, headers={"User-Agent": "Heavi/0.1"})
        r.raise_for_status()
        z = zipfile.ZipFile(io.BytesIO(r.content))
        GAZ_CACHE.write_bytes(z.read(z.namelist()[0]))
    out: dict[str, tuple[float, float]] = {}
    lines = GAZ_CACHE.read_text("latin-1").splitlines()
    header = [h.strip() for h in lines[0].split("\t")]
    gi, la, lo = header.index("GEOID"), header.index("INTPTLAT"), header.index("INTPTLONG")
    for line in lines[1:]:
        f = line.split("\t")
        if len(f) <= lo:
            continue
        try:
            out[f[gi].strip().zfill(5)] = (float(f[la].strip()), float(f[lo].strip()))
        except ValueError:
            continue
    return out


def _fips5(raw: object) -> str | None:
    """LBNL stores FIPS as an int (leading zero stripped); normalize to 5 digits."""
    if raw is None or raw == "":
        return None
    try:
        return str(int(float(raw))).zfill(5)
    except (TypeError, ValueError):
        s = str(raw).strip()
        return s.zfill(5) if s.isdigit() else None


def _num(v: object) -> float | None:
    try:
        return float(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def _extract_rows() -> list[dict]:
    """Active solar projects from the LBNL sheet (header in the 2nd row)."""
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    it = wb[SHEET].iter_rows(values_only=True)
    next(it)  # "RETURN TO CONTENTS" banner row
    header = list(next(it))
    h = {name: i for i, name in enumerate(header)}

    def g(row, col):
        v = row[h[col]] if h.get(col) is not None and h[col] < len(row) else None
        return v.strip() if isinstance(v, str) else v

    out: list[dict] = []
    for n, row in enumerate(it, start=1):
        status = (g(row, "q_status") or "").lower()
        type_clean = g(row, "type_clean") or ""
        if status != "active" or type_clean not in SOLAR_TYPES:
            continue
        county, state = g(row, "county"), g(row, "state")
        poi = g(row, "poi_name")
        proj = g(row, "project_name") or poi or (
            f"{county}, {state} solar" if county and state else "Solar project")
        qd = g(row, "q_date")
        out.append({
            "queue_id": f"LBNL-{n:05d}",
            "iso": g(row, "entity") or "Unknown",       # transmission provider (ISO or utility)
            "project_name": proj,
            "fuel_type": type_clean,
            "capacity_mw": _num(g(row, "mw_1")),
            "substation_poi": poi,
            "county": county,
            "state": state,
            "status": "Active",
            "queue_date": qd.date() if hasattr(qd, "date") else None,
            "study_phase": g(row, "IA_phase_clean"),
            "estimated_cost_millions": None,            # not provided by LBNL
            "fips": _fips5(g(row, "fips_code")),
        })
    return out


async def _resolve_coords(rows: list[dict], centroids: dict[str, tuple[float, float]]) -> int:
    """Attach lat/lon from county centroid; geocode 'county, state' as fallback."""
    geo_cache: dict[tuple[str, str], tuple[float, float] | None] = {}
    skipped = 0
    for r in rows:
        coord = centroids.get(r["fips"]) if r["fips"] else None
        if coord is None and r["county"] and r["state"]:
            key = (r["county"], r["state"])
            if key not in geo_cache:
                res = await geocode(f"{r['county']} County, {r['state']}")
                geo_cache[key] = (res["latitude"], res["longitude"]) if res else None
            coord = geo_cache[key]
        if coord is None:
            r["latitude"] = r["longitude"] = None
            skipped += 1
        else:
            r["latitude"], r["longitude"] = coord
    return skipped


async def main() -> None:
    if not XLSX.exists():
        raise SystemExit(f"LBNL file not found: {XLSX}")
    centroids = _county_centroids()
    print(f"county centroids: {len(centroids)}")
    rows = _extract_rows()
    print(f"active solar projects in LBNL: {len(rows)}")
    skipped = await _resolve_coords(rows, centroids)
    placed = [r for r in rows if r["latitude"] is not None]
    print(f"placed: {len(placed)}  (no coordinates, skipped: {skipped})")

    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=2)
    try:
        async with pool.acquire() as conn:
            await conn.execute(MIGRATION.read_text())
            await conn.execute("TRUNCATE interconnection_queue")
            await conn.executemany(
                """INSERT INTO interconnection_queue
                   (queue_id, iso, project_name, fuel_type, capacity_mw, substation_poi,
                    county, state, status, queue_date, study_phase, estimated_cost_millions,
                    latitude, longitude, geometry, data_source)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,
                           ST_SetSRID(ST_MakePoint($14,$13),4326), $15)""",
                [(r["queue_id"], r["iso"], r["project_name"], r["fuel_type"], r["capacity_mw"],
                  r["substation_poi"], r["county"], r["state"], r["status"], r["queue_date"],
                  r["study_phase"], r["estimated_cost_millions"], r["latitude"], r["longitude"],
                  DATA_SOURCE)
                 for r in placed],
            )
            total = await conn.fetchval("SELECT count(*) FROM interconnection_queue")
            mw = await conn.fetchval(
                "SELECT round(sum(capacity_mw)::numeric) FROM interconnection_queue")
            print(f"\nloaded {total} rows, {mw} MW total")
            dist = await conn.fetch(
                "SELECT iso, count(*) n, round(sum(capacity_mw)::numeric) mw "
                "FROM interconnection_queue GROUP BY iso ORDER BY n DESC LIMIT 12")
            for d in dist:
                print(f"  {d['iso']:8s} {d['n']:4d} projects  {d['mw']} MW")
            for nm, (lat, lng) in {"Kern CA": (35.35, -119.05), "Houston TX": (29.76, -95.37),
                                   "Chicago IL": (41.85, -87.65)}.items():
                row = await conn.fetchrow(
                    """SELECT count(*) n, round(coalesce(sum(capacity_mw),0)::numeric) mw
                       FROM interconnection_queue
                       WHERE status='Active' AND fuel_type ILIKE 'solar%%'
                         AND ST_DWithin(geometry::geography,
                             ST_SetSRID(ST_MakePoint($1,$2),4326)::geography, 50000)""",
                    lng, lat)
                print(f"  active solar within 50km of {nm}: {row['n']} projects, {row['mw']} MW")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
