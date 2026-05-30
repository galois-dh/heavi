"""Load the HAZUS Flood Model depth-damage functions into flood_hazus_ddfs.

These are the generic depth-damage relationships from the FEMA HAZUS Flood Model
Technical Manual (built on the USACE / Federal Insurance Administration credibility-
weighted curves). Each curve gives percent-of-value damage to structure and
contents as a function of flood depth measured RELATIVE TO THE FIRST FLOOR
(negative = water below the first floor; positive = water above it).

The table serves nationally — it is a small lookup (6 classes × depths −4..+24 ft).
We encode anchor points from the published curves and linearly interpolate to
1-ft steps so the scoring pipeline can do an exact-depth lookup.

Schema: occupancy_class, foundation_type, depth_ft, structural_damage_pct,
contents_damage_pct.
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import execute_values

load_dotenv(Path(__file__).resolve().parents[4] / ".env")

TABLE = "flood_hazus_ddfs"
DEPTHS = list(range(-4, 25))  # −4 .. +24 ft, 1-ft steps

# Anchor points {depth_ft: percent} for each curve. Structural and contents are
# encoded separately. Values follow the HAZUS generic curves: 1-story incurs more
# damage per foot than 2-story (more value at the flooded level); with-basement
# classes take damage below the first floor; RES2 (manufactured) fails fast; COM1
# has a gentler onset. Linear interpolation fills the integer steps between anchors.
CURVES: dict[str, dict[str, object]] = {
    "RES1-1SNB": {  # 1-story, slab-on-grade, no basement
        "foundation_type": "slab",
        "struct": {-4: 0, -1: 0, 0: 13, 1: 18, 2: 25, 3: 31, 4: 37, 6: 46, 8: 53,
                   10: 59, 12: 63, 16: 69, 20: 72, 24: 74},
        "cont": {-4: 0, -1: 0, 0: 9, 1: 14, 2: 24, 3: 33, 4: 42, 6: 56, 8: 67,
                 10: 74, 12: 79, 16: 84, 20: 87, 24: 88},
    },
    "RES1-1SWB": {  # 1-story, with basement
        "foundation_type": "basement",
        "struct": {-4: 3, -3: 4, -2: 6, -1: 8, 0: 14, 1: 19, 2: 26, 3: 32, 4: 38,
                   6: 47, 8: 54, 10: 60, 12: 64, 16: 70, 20: 73, 24: 75},
        "cont": {-4: 4, -3: 6, -2: 8, -1: 10, 0: 14, 1: 20, 2: 29, 3: 38, 4: 46,
                 6: 59, 8: 69, 10: 76, 12: 80, 16: 85, 20: 88, 24: 90},
    },
    "RES1-2SNB": {  # 2-story, no basement
        "foundation_type": "slab",
        "struct": {-4: 0, -1: 0, 0: 10, 1: 14, 2: 20, 3: 25, 4: 30, 6: 38, 8: 44,
                   10: 49, 12: 53, 16: 59, 20: 63, 24: 66},
        "cont": {-4: 0, -1: 0, 0: 7, 1: 11, 2: 19, 3: 27, 4: 34, 6: 46, 8: 55,
                 10: 62, 12: 67, 16: 73, 20: 77, 24: 79},
    },
    "RES1-2SWB": {  # 2-story, with basement
        "foundation_type": "basement",
        "struct": {-4: 3, -2: 5, -1: 7, 0: 11, 1: 15, 2: 21, 3: 26, 4: 31, 6: 39,
                   8: 45, 10: 50, 12: 54, 16: 60, 20: 64, 24: 67},
        "cont": {-4: 4, -2: 7, -1: 9, 0: 11, 1: 16, 2: 24, 3: 31, 4: 38, 6: 49,
                 8: 58, 10: 64, 12: 69, 16: 75, 20: 78, 24: 80},
    },
    "RES2": {  # manufactured housing — fast onset, near-total at shallow depths
        "foundation_type": "manufactured",
        "struct": {-4: 0, -1: 0, 0: 8, 1: 44, 2: 63, 3: 78, 4: 88, 6: 96, 8: 99,
                   10: 100, 24: 100},
        "cont": {-4: 0, -1: 0, 0: 9, 1: 39, 2: 60, 3: 73, 4: 83, 6: 93, 8: 97,
                 10: 100, 24: 100},
    },
    "COM1": {  # retail trade — gentler onset
        "foundation_type": "slab",
        "struct": {-4: 0, -1: 0, 0: 9, 1: 11, 2: 14, 3: 17, 4: 20, 6: 27, 8: 33,
                   10: 39, 12: 44, 16: 52, 20: 58, 24: 62},
        "cont": {-4: 0, -1: 0, 0: 9, 1: 13, 2: 18, 3: 23, 4: 28, 6: 38, 8: 47,
                 10: 55, 12: 61, 16: 70, 20: 76, 24: 80},
    },
}


def interp(anchors: dict[int, float], depth: int) -> float:
    """Linear interpolation/extension across sorted anchor depths."""
    xs = sorted(anchors)
    if depth <= xs[0]:
        return float(anchors[xs[0]])
    if depth >= xs[-1]:
        return float(anchors[xs[-1]])
    for i in range(len(xs) - 1):
        x0, x1 = xs[i], xs[i + 1]
        if x0 <= depth <= x1:
            y0, y1 = anchors[x0], anchors[x1]
            t = (depth - x0) / (x1 - x0)
            return round(y0 + t * (y1 - y0), 2)
    return float(anchors[xs[-1]])


def main() -> None:
    rows: list[tuple] = []
    for occ, spec in CURVES.items():
        ft = spec["foundation_type"]
        struct = spec["struct"]  # type: ignore[assignment]
        cont = spec["cont"]      # type: ignore[assignment]
        for d in DEPTHS:
            rows.append((occ, ft, float(d), interp(struct, d), interp(cont, d)))  # type: ignore[arg-type]

    conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=20)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f"DROP TABLE IF EXISTS {TABLE}")
    cur.execute(
        f"""CREATE TABLE {TABLE} (
            occupancy_class text NOT NULL,
            foundation_type text NOT NULL,
            depth_ft double precision NOT NULL,
            structural_damage_pct double precision NOT NULL,
            contents_damage_pct double precision NOT NULL
        )"""
    )
    execute_values(
        cur,
        f"INSERT INTO {TABLE} (occupancy_class, foundation_type, depth_ft, "
        f"structural_damage_pct, contents_damage_pct) VALUES %s",
        rows,
    )
    cur.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_lookup ON {TABLE} (occupancy_class, depth_ft)"
    )
    cur.execute(f"SELECT COUNT(*), COUNT(DISTINCT occupancy_class) FROM {TABLE}")
    n, nclass = cur.fetchone()
    print(f"Loaded {n} rows across {nclass} occupancy classes into {TABLE}.")
    cur.execute(
        f"SELECT depth_ft, structural_damage_pct, contents_damage_pct FROM {TABLE} "
        f"WHERE occupancy_class='RES1-1SNB' AND depth_ft BETWEEN 0 AND 4 ORDER BY depth_ft"
    )
    print("RES1-1SNB (depth_ft, struct%, cont%):")
    for r in cur.fetchall():
        print(f"  {r[0]:>4.0f}  {r[1]:>6.2f}  {r[2]:>6.2f}")
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
