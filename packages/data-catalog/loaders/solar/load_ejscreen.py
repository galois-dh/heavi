"""Load EPA EJScreen 2024 v2.32 block-group data into PostGIS.

EPA discontinued the public EJScreen web tool in Feb 2025; gaftp.epa.gov/EJScreen/*
returns 404. The dataset is preserved on the Internet Archive (Wayback Machine)
from Feb 6 2025 — that's the source we use.

Wayback URL (verified 2026-06-05):
  https://web.archive.org/web/20250206123608id_/https://gaftp.epa.gov/
  EJSCREEN/2024/2.32_August_UseMe/EJSCREEN_2024_BG_StatePct_with_AS_CNMI_GU_VI.csv.zip

CSV is 428 MB unzipped, 243,023 rows × 229 columns (one row per US census
block group + territories). We keep ID + state/county + the demographic and
percentile fields the solar module's EJ screening uses (~40 columns), drop
the rest.

This is a non-geometry table; the EJ integration module looks up a block
group GEOID via the Census Geocoder API and joins.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

TABLE_NAME = "ejscreen_blockgroups"
CSV_PATH = Path(os.environ.get(
    "HEAVI_EJSCREEN_CSV",
    "/tmp/heavi_ej/EJSCREEN_2024_BG_StatePct_with_AS_CNMI_GU_VI.csv",
))
SOURCE_URL = (
    "https://web.archive.org/web/20250206123608id_/https://gaftp.epa.gov/"
    "EJSCREEN/2024/2.32_August_UseMe/"
    "EJSCREEN_2024_BG_StatePct_with_AS_CNMI_GU_VI.csv.zip"
)

# Columns to keep (~40 of 229). Selection focus: identifiers, population,
# demographic index, and state-percentile (P_*) versions of every EJ indicator.
KEEP = [
    # Identifiers + population context
    "ID", "STATE_NAME", "ST_ABBREV", "CNTY_NAME", "REGION", "ACSTOTPOP",
    # Demographic indicators (raw)
    "DEMOGIDX_2", "DEMOGIDX_5",
    "PEOPCOLORPCT", "LOWINCPCT", "UNEMPPCT", "DISABILITYPCT",
    "LINGISOPCT", "LESSHSPCT", "UNDER5PCT", "OVER64PCT",
    "LIFEEXPPCT", "PRE1960PCT",
    # Demographic state-percentiles
    "P_DEMOGIDX_2", "P_DEMOGIDX_5",
    "P_PEOPCOLORPCT", "P_LOWINCPCT", "P_UNEMPPCT", "P_DISABILITYPCT",
    # Environmental-burden state-percentiles
    "P_PM25", "P_OZONE", "P_DSLPM", "P_RSEI_AIR", "P_PTRAF",
    "P_LDPNT", "P_PNPL", "P_PRMP", "P_PTSDF", "P_UST",
    "P_PWDIS", "P_NO2", "P_DWATER",
    # Composite "supplemental" indexes (2-component + 5-component on PM2.5/OZONE)
    "P_D2_PM25", "P_D5_PM25", "P_D2_OZONE", "P_D5_OZONE",
]


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr); sys.exit(1)
    if not CSV_PATH.exists():
        print(f"ERROR: EJScreen CSV not found at {CSV_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading {CSV_PATH} ({CSV_PATH.stat().st_size/1e6:.0f} MB)…")
    t0 = time.perf_counter()
    # The CSV has a UTF-8 BOM on the first column header (﻿ID).
    df = pd.read_csv(
        CSV_PATH,
        dtype={"ID": str},
        usecols=lambda c: c.lstrip("﻿") in KEEP,
        low_memory=False,
        encoding="utf-8-sig",
    )
    # Normalize BOM'd headers + lowercase column names.
    df.columns = [c.lstrip("﻿").lower() for c in df.columns]
    df["id"] = df["id"].str.zfill(12)  # block group GEOID
    print(f"  {len(df):,} rows × {len(df.columns)} columns in {time.perf_counter()-t0:.1f}s")

    # Bulk-load via COPY FROM — pd.to_sql() with multi-row INSERTs stalls the
    # Supabase SSL connection on chunks this big (PendingRollbackError).
    print(f"Writing to {TABLE_NAME} via COPY FROM…")
    import io
    conn2 = psycopg2.connect(database_url)
    cur = conn2.cursor()
    # Supabase pooler enforces a per-role statement timeout (often 8s). DDL +
    # 243k-row COPY can exceed that; bump for this session.
    cur.execute("SET statement_timeout = '600s'")
    cur.execute(f"DROP TABLE IF EXISTS {TABLE_NAME} CASCADE")
    # Build the column definition from the dataframe dtypes.
    coldefs = ["id text PRIMARY KEY"]
    for col in df.columns:
        if col == "id":
            continue
        dt = df[col].dtype
        if str(dt).startswith("int") or str(dt).startswith("float"):
            coldefs.append(f"{col} double precision")
        else:
            coldefs.append(f"{col} text")
    cur.execute(f"CREATE TABLE {TABLE_NAME} ({', '.join(coldefs)})")
    conn2.commit()

    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False, na_rep="")
    buf.seek(0)
    cols = ", ".join(df.columns)
    cur.copy_expert(
        f"COPY {TABLE_NAME} ({cols}) FROM STDIN WITH (FORMAT CSV, NULL '')",
        buf,
    )
    conn2.commit()
    cur.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_st_abbrev "
        f"ON {TABLE_NAME} (st_abbrev)")
    conn2.commit()
    cur.close(); conn2.close()
    print("Loaded + indexed.")
    engine = create_engine(database_url)  # for downstream catalog write below

    # Catalog registration (non-geometry — geometry_type null is fine for
    # tabular data; the catalog still lists it).
    conn2 = psycopg2.connect(database_url); conn2.autocommit = True
    cur = conn2.cursor()
    cur.execute(
        """
        INSERT INTO catalog_layers (name, description, source_url, geometry_type, bbox, row_count, updated_at)
        VALUES (%s, %s, %s, %s, NULL, %s, now())
        ON CONFLICT (name) DO UPDATE SET
            description = EXCLUDED.description, source_url = EXCLUDED.source_url,
            row_count = EXCLUDED.row_count, updated_at = now();
        """,
        (
            TABLE_NAME,
            "EPA EJScreen 2024 v2.32 — block-group demographic + environmental "
            "burden indicators with state percentiles. Sourced from the Internet "
            "Archive Wayback Machine snapshot of gaftp.epa.gov/EJSCREEN/2024/ "
            "from 2025-02-06 (the EPA public service was discontinued Feb 2025). "
            "Keyed by 12-digit block group GEOID — pair with a Census Geocoder "
            "lookup to resolve any lat/lng to a block group.",
            SOURCE_URL,
            "Tabular (non-geometry)",
            len(df),
        ),
    )
    cur.close(); conn2.close()
    print(f"Registered '{TABLE_NAME}' in catalog_layers. Done.")


if __name__ == "__main__":
    main()
