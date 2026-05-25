"""Initialize the catalog_layers metadata table."""

from __future__ import annotations

import os
import sys

import psycopg2
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

DDL = """
CREATE TABLE IF NOT EXISTS catalog_layers (
    name         TEXT PRIMARY KEY,
    description  TEXT NOT NULL,
    source_url   TEXT,
    geometry_type TEXT,
    bbox         JSONB,
    row_count    INTEGER DEFAULT 0,
    created_at   TIMESTAMPTZ DEFAULT now(),
    updated_at   TIMESTAMPTZ DEFAULT now()
);
"""


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    conn = psycopg2.connect(database_url)
    conn.autocommit = True
    cur = conn.cursor()

    # Ensure PostGIS extension exists
    cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
    print("PostGIS extension OK")

    cur.execute(DDL)
    print("catalog_layers table OK")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
