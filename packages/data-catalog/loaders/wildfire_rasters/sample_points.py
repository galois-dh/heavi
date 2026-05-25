"""Sample every Sonoma NSI structure across all six derived/raw rasters.

Pulls (fd_id, lon, lat) for every row in wildfire_nsi_structures, reprojects
the points to EPSG:3310, then opens each raster once and reads pixel values
in one vectorised batch. Output: a parquet file with one row per fd_id and
the six derived feature columns ready to be UPDATE'd into PG.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import numpy as np
import psycopg2
import rasterio
from dotenv import load_dotenv
from pyproj import Transformer

from . import config as cfg

load_dotenv(Path(__file__).resolve().parents[4] / ".env")

OUT_PARQUET = cfg.RASTER_ROOT / "nsi_enrichment.parquet"
# Used in upload_columns.py too — keep the dtype hints together.
COLUMNS = [
    "burn_probability",
    "distance_to_fuel_m",
    "canopy_cover_30m",
    "canopy_cover_100m",
    "canopy_cover_300m",
    "slope_degrees",
]
RASTER_FOR = {
    "burn_probability": cfg.WRC_BP_TIF,
    "distance_to_fuel_m": cfg.DIST_TO_FUEL_TIF,
    "canopy_cover_30m": cfg.CC_30_TIF,
    "canopy_cover_100m": cfg.CC_100_TIF,
    "canopy_cover_300m": cfg.CC_300_TIF,
    "slope_degrees": cfg.SLOPE_TIF,
}


def fetch_points() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    print("Fetching all NSI points from Postgres ...")
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        with conn.cursor(name="nsi_cursor") as cur:
            cur.itersize = 50_000
            cur.execute(
                "SELECT fd_id, ST_X(geometry), ST_Y(geometry) "
                "FROM wildfire_nsi_structures"
            )
            ids, lons, lats = [], [], []
            for row in cur:
                ids.append(row[0])
                lons.append(row[1])
                lats.append(row[2])
    finally:
        conn.close()
    print(f"  {len(ids)} points")
    return (
        np.asarray(ids, dtype=np.int64),
        np.asarray(lons, dtype=np.float64),
        np.asarray(lats, dtype=np.float64),
    )


def sample_raster(tif: Path, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """Vectorised raster sampling. xs/ys must be in the raster's CRS."""
    with rasterio.open(tif) as src:
        inv = ~src.transform
        cols_f, rows_f = inv * (xs, ys)
        cols = np.floor(cols_f).astype(np.int64)
        rows = np.floor(rows_f).astype(np.int64)
        in_bounds = (rows >= 0) & (rows < src.height) & (cols >= 0) & (cols < src.width)
        out = np.full(xs.shape, np.nan, dtype=np.float64)
        if in_bounds.any():
            band = src.read(1)
            vals = band[rows[in_bounds], cols[in_bounds]]
            nodata = src.nodata
            if nodata is not None:
                # Treat nodata as NaN in the output.
                if np.issubdtype(band.dtype, np.floating):
                    bad = (~np.isfinite(vals)) | (vals == nodata)
                else:
                    bad = vals == nodata
                vals = np.where(bad, np.nan, vals.astype(np.float64))
            out[in_bounds] = vals
    return out


def main() -> int:
    t0 = time.perf_counter()
    fd_ids, lons, lats = fetch_points()

    print(f"Reprojecting {len(lons)} points → {cfg.WORKING_CRS} ...")
    tx = Transformer.from_crs("EPSG:4326", cfg.WORKING_CRS, always_xy=True)
    xs, ys = tx.transform(lons, lats)
    xs = np.asarray(xs); ys = np.asarray(ys)

    results: dict[str, np.ndarray] = {"fd_id": fd_ids}
    for col in COLUMNS:
        tif = RASTER_FOR[col]
        print(f"Sampling {tif.name} → {col} ...")
        t = time.perf_counter()
        results[col] = sample_raster(tif, xs, ys)
        print(f"  done in {time.perf_counter() - t:.2f}s, "
              f"non-null = {np.isfinite(results[col]).sum()}/{len(fd_ids)}")

    # Write parquet (pandas+pyarrow already available via pyarrow dependency).
    import pandas as pd

    df = pd.DataFrame(results)
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PARQUET, index=False)
    print(f"Wrote {OUT_PARQUET} ({OUT_PARQUET.stat().st_size / 1_000_000:.1f} MB) "
          f"in {time.perf_counter() - t0:.1f}s total.")

    # Quick summary.
    print()
    print("──────── feature summary (non-null) ────────")
    for col in COLUMNS:
        v = df[col].dropna().to_numpy()
        if v.size == 0:
            print(f"  {col:<22}  (no samples)")
            continue
        pcts = np.percentile(v, [5, 50, 95])
        print(
            f"  {col:<22}  n={v.size:>6}  min={v.min():.4f}  "
            f"p05={pcts[0]:.4f}  p50={pcts[1]:.4f}  p95={pcts[2]:.4f}  max={v.max():.4f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
