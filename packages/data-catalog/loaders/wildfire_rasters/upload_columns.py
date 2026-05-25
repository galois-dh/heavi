"""Upload the raster-derived feature columns to wildfire_nsi_structures.

Adds the six enrichment columns if missing, then UPDATEs them from the
parquet produced by sample_points.py. The UPDATE is done via a temp table +
single bulk join to keep round-trips off the wire — pure per-row UPDATEs
across 185 k rows over a Supabase pooler is too slow.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import execute_values

from .sample_points import COLUMNS, OUT_PARQUET

load_dotenv(Path(__file__).resolve().parents[4] / ".env")

TABLE = "wildfire_nsi_structures"


def main() -> int:
    if not OUT_PARQUET.exists():
        print(f"ERROR: {OUT_PARQUET} not found — run sample_points first", file=sys.stderr)
        return 1

    df = pd.read_parquet(OUT_PARQUET)
    print(f"Loaded {len(df)} rows from {OUT_PARQUET}")

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 1

    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            # 1. ALTER TABLE add columns if missing.
            print("Ensuring columns exist on", TABLE, "...")
            for col in COLUMNS:
                cur.execute(
                    f"ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS {col} double precision"
                )

            # 2. Stage to a temp table and bulk update.
            print("Creating temp staging table ...")
            cur.execute(
                "CREATE TEMP TABLE _nsi_enrich ("
                "fd_id BIGINT PRIMARY KEY, "
                + ", ".join(f"{c} DOUBLE PRECISION" for c in COLUMNS)
                + ") ON COMMIT DROP"
            )

            print(f"Bulk loading {len(df)} rows into temp table ...")
            t = time.perf_counter()
            rows = [
                (
                    int(r.fd_id),
                    *(None if pd.isna(getattr(r, c)) else float(getattr(r, c)) for c in COLUMNS),
                )
                for r in df.itertuples(index=False)
            ]
            execute_values(
                cur,
                f"INSERT INTO _nsi_enrich (fd_id, {', '.join(COLUMNS)}) VALUES %s",
                rows,
                page_size=20_000,
            )
            print(f"  staged in {time.perf_counter() - t:.1f}s")

            print(f"Joining temp → {TABLE} ...")
            t = time.perf_counter()
            set_clause = ", ".join(f"{c} = s.{c}" for c in COLUMNS)
            cur.execute(
                f"UPDATE {TABLE} t SET {set_clause} "
                f"FROM _nsi_enrich s WHERE t.fd_id = s.fd_id"
            )
            print(f"  UPDATE affected {cur.rowcount} rows in {time.perf_counter() - t:.1f}s")

        conn.commit()
        print("Commit OK.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
