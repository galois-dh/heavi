"""Load the HAZUS Flood Model depth-damage functions into flood_hazus_ddfs.

Values are TRANSCRIBED from FEMA's HAZUS flood damage-function database (the
flDmgFn table shipped with HAZUS, as published in the HAZUS Flood Model Technical
Manual and distributed in machine-readable form via the CRAN `hazus` package's
`haz_fl_dept` dataset). Each curve is identified by its HAZUS DmgFnId so the
provenance is auditable.

Curve selection (A-Zone / riverine defaults):
  RES1-1SNB  struct DmgFnId 105 (FIA, one floor, no basement, A-Zone)
             cont   DmgFnId  21 (FIA, one floor, no basement, A-Zone)
  RES1-1SWB  struct DmgFnId 106 (FIA, one floor, w/ basement, A-Zone)
             cont   DmgFnId  22 (FIA, one floor, w/ basement, A-Zone)
  RES1-2SNB  struct DmgFnId 107 (FIA, two floors, no basement, A-Zone)
             cont   DmgFnId  23 (FIA, two floors, no basement, A-Zone)
  RES1-2SWB  struct DmgFnId 108 (FIA, two floors, w/ basement, A-Zone)
             cont   DmgFnId  24 (FIA, two floors, w/ basement, A-Zone)
  RES2       struct DmgFnId 189 (FIA, mobile home, A-Zone)
             cont   DmgFnId  74 (FIA, mobile home, A-Zone)
  COM1       struct DmgFnId 217 (USACE-Galveston, Average Retail, Structure)
             cont   DmgFnId  90 (USACE-Galveston, Average retail trade contents)

Damage is percent-of-value, indexed by flood depth RELATIVE TO THE FIRST FLOOR,
from −4 to +24 ft in 1-ft steps (29 values per curve, no interpolation).

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
DEPTHS = list(range(-4, 25))  # −4 .. +24 ft (29 values)

# Authoritative HAZUS percent-damage curves (index 0 = −4 ft … index 28 = +24 ft).
CURVES: dict[str, dict[str, object]] = {
    "RES1-1SNB": {
        "foundation_type": "slab",
        "struct": [0, 0, 0, 0, 18, 22, 25, 28, 30, 31, 40, 43, 43, 45, 46, 47, 47, 49,
                   50, 50, 50, 51, 51, 52, 52, 53, 53, 54, 54],
        "cont": [0, 0, 0, 0, 12, 25, 35, 36, 38, 41, 45, 50, 55, 60, 60, 60, 60, 60, 60,
                 60, 60, 60, 60, 60, 60, 60, 60, 60, 60],
    },
    "RES1-1SWB": {
        "foundation_type": "basement",
        "struct": [7, 7, 7, 11, 17, 21, 29, 34, 38, 43, 50, 50, 54, 55, 55, 57, 58, 60,
                   62, 63, 65, 67, 69, 70, 72, 74, 76, 77, 79],
        "cont": [0, 5, 7, 8, 16, 20, 22, 28, 33, 39, 44, 50, 55, 60, 60, 60, 60, 60, 60,
                 60, 60, 60, 60, 60, 60, 60, 60, 60, 60],
    },
    "RES1-2SNB": {
        "foundation_type": "slab",
        "struct": [0, 0, 0, 0, 11, 12, 14, 18, 20, 22, 24, 26, 30, 34, 38, 39, 40, 42,
                   43, 44, 45, 47, 48, 49, 50, 52, 53, 54, 56],
        "cont": [0, 0, 0, 0, 8, 11, 19, 23, 28, 33, 39, 44, 50, 54, 58, 60, 60, 60, 60,
                 60, 60, 60, 60, 60, 60, 60, 60, 60, 60],
    },
    "RES1-2SWB": {
        "foundation_type": "basement",
        "struct": [4, 4, 8, 14, 19, 21, 26, 29, 34, 39, 44, 50, 55, 57, 59, 61, 63, 65,
                   66, 68, 69, 71, 72, 74, 75, 77, 79, 80, 82],
        "cont": [0, 5, 7, 8, 16, 18, 25, 29, 33, 37, 42, 46, 52, 55, 58, 60, 60, 60, 60,
                 60, 60, 60, 60, 60, 60, 60, 60, 60, 60],
    },
    "RES2": {
        "foundation_type": "manufactured",
        "struct": [0, 0, 0, 0, 11, 44, 63, 73, 78, 79, 81, 82, 83, 84, 85, 86, 88, 89,
                   90, 91, 92, 94, 95, 96, 97, 98, 99, 100, 100],
        "cont": [0, 0, 0, 0, 3, 27, 49, 64, 70, 76, 78, 79, 81, 83, 83, 83, 83, 83, 83,
                 83, 83, 83, 83, 83, 83, 83, 83, 83, 83],
    },
    "COM1": {
        "foundation_type": "slab",
        "struct": [0, 0, 0, 0, 1, 9, 14, 16, 18, 20, 23, 26, 30, 34, 38, 42, 47, 51, 55,
                   58, 61, 64, 67, 69, 71, 74, 76, 78, 80],
        "cont": [0, 0, 0, 0, 2, 26, 42, 56, 68, 78, 83, 85, 87, 88, 89, 90, 91, 92, 92,
                 92, 93, 93, 94, 94, 94, 94, 94, 94, 94],
    },
}


def main() -> None:
    # Validate array lengths up front.
    for occ, spec in CURVES.items():
        for key in ("struct", "cont"):
            if len(spec[key]) != len(DEPTHS):  # type: ignore[arg-type]
                raise ValueError(f"{occ}.{key}: {len(spec[key])} values, expected {len(DEPTHS)}")  # type: ignore[arg-type]

    rows: list[tuple] = []
    for occ, spec in CURVES.items():
        ft = spec["foundation_type"]
        for i, d in enumerate(DEPTHS):
            rows.append((occ, ft, float(d),
                         float(spec["struct"][i]), float(spec["cont"][i])))  # type: ignore[index]

    conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=20)
    conn.autocommit = True
    cur = conn.cursor()

    # ── Diff log against the values currently in the table ──────────────────
    cur.execute(
        "SELECT to_regclass(%s)", (TABLE,)
    )
    exists = cur.fetchone()[0] is not None
    if exists:
        cur.execute(
            f"SELECT occupancy_class, depth_ft, structural_damage_pct, contents_damage_pct "
            f"FROM {TABLE}"
        )
        old = {(r[0], float(r[1])): (float(r[2]), float(r[3])) for r in cur.fetchall()}
        print("Differences vs. current table (authoritative − current):")
        per_class: dict[str, list[float]] = {}
        for occ, ft, d, s_new, c_new in rows:
            o = old.get((occ, d))
            if o is None:
                print(f"  {occ} @ {d:+.0f} ft: NEW row (struct {s_new}, cont {c_new})")
                continue
            ds, dc = round(s_new - o[0], 2), round(c_new - o[1], 2)
            if ds != 0 or dc != 0:
                per_class.setdefault(occ, []).extend([abs(ds), abs(dc)])
                print(f"  {occ} @ {d:+.0f} ft: struct {o[0]:.0f}→{s_new:.0f} ({ds:+.0f}), "
                      f"cont {o[1]:.0f}→{c_new:.0f} ({dc:+.0f})")
        print("\nPer-class mean |Δ| (percentage points):")
        for occ in CURVES:
            diffs = per_class.get(occ, [])
            mean_d = sum(diffs) / len(diffs) if diffs else 0.0
            print(f"  {occ:10} mean|Δ| {mean_d:5.1f}  (cells changed: {len(diffs)})")
    else:
        print(f"{TABLE} does not exist yet — creating fresh.")

    # ── Replace with the authoritative values ───────────────────────────────
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
    print(f"\nLoaded {n} authoritative HAZUS rows across {nclass} occupancy classes into {TABLE}.")
    cur.execute(
        f"SELECT depth_ft, structural_damage_pct, contents_damage_pct FROM {TABLE} "
        f"WHERE occupancy_class='RES1-1SNB' AND depth_ft BETWEEN 0 AND 4 ORDER BY depth_ft"
    )
    print("RES1-1SNB (depth_ft, struct%, cont%):")
    for r in cur.fetchall():
        print(f"  {r[0]:>4.0f}  {r[1]:>6.1f}  {r[2]:>6.1f}")
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
