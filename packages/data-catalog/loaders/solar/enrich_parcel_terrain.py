"""Pre-compute slope & aspect for every Kern County parcel, then store them as
columns on solar_parcels_kern.

Mirrors the wildfire raster-enrichment pattern (loaders/wildfire_rasters): pull a
3DEP DEM clip for the AOI into a working metric CRS, derive slope/aspect with
finite-difference gradients (numpy), and sample the rasters at each feature
centroid in one vectorised batch. The Discover pipeline then reads slope_degrees
/ aspect_degrees straight from PostGIS — zero 3DEP API calls at query time. The
on-demand 3DEP path remains only for Score Mode's ad-hoc customer parcels.

Adds columns to solar_parcels_kern:
  slope_degrees   terrain slope at the parcel centroid (degrees)
  aspect_degrees  downslope compass azimuth (0=N, 90=E, 180=S); NULL on flat ground
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import numpy as np
import psycopg2
import rasterio
import requests
from dotenv import load_dotenv
from psycopg2.extras import execute_values
from pyproj import Transformer
from rasterio.warp import transform_bounds

load_dotenv(Path(__file__).resolve().parents[4] / ".env")

# Kern County AOI (lng_min, lat_min, lng_max, lat_max), EPSG:4326 — matches the
# parcel layer extent.
KERN_BBOX_4326 = (-120.20, 34.79, -117.61, 35.80)
WORKING_CRS = "EPSG:3310"   # California Albers (NAD83), metric — same as wildfire
TARGET_PIX_M = 60.0         # ~3950×1910 px over Kern; one exportImage request
DEM_IMAGESERVER_URL = (
    "https://elevation.nationalmap.gov/arcgis/rest/services/"
    "3DEPElevation/ImageServer/exportImage"
)
DEM_TIF = Path("/tmp/kern_dem_3310.tif")
NODATA = -9999.0


def download_dem() -> None:
    if DEM_TIF.exists() and DEM_TIF.stat().st_size > 1_000_000:
        print(f"Already have {DEM_TIF}; skipping download.")
        return
    tgt = transform_bounds("EPSG:4326", WORKING_CRS, *KERN_BBOX_4326)
    width = int(round((tgt[2] - tgt[0]) / TARGET_PIX_M))
    height = int(round((tgt[3] - tgt[1]) / TARGET_PIX_M))
    print(f"Requesting {width}×{height} 3DEP DEM @ {TARGET_PIX_M:.0f} m in {WORKING_CRS} ...")
    params = {
        "bbox": ",".join(str(v) for v in tgt),
        "bboxSR": "3310",
        "size": f"{width},{height}",
        "imageSR": "3310",
        "format": "tiff",
        "pixelType": "F32",
        "interpolation": "RSP_BilinearInterpolation",
        "noDataInterpretation": "esriNoDataMatchAny",
        "f": "json",
    }
    r = requests.get(DEM_IMAGESERVER_URL, params=params, timeout=600)
    r.raise_for_status()
    href = r.json().get("href")
    if not href:
        raise RuntimeError(f"exportImage returned no href: {r.json()}")
    print(f"  fetching {href}")
    with requests.get(href, timeout=600, stream=True) as resp:
        resp.raise_for_status()
        with DEM_TIF.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=4 << 20):
                f.write(chunk)
    with rasterio.open(DEM_TIF) as src:
        print(f"  wrote {DEM_TIF} dtype={src.dtypes[0]} crs={src.crs} "
              f"size={src.width}×{src.height}")


def compute_slope_aspect() -> tuple[np.ndarray, np.ndarray, rasterio.Affine, int, int]:
    with rasterio.open(DEM_TIF) as src:
        dem = src.read(1).astype(np.float64)
        nodata = src.nodata
        transform = src.transform
        dx = abs(src.transform.a)
        dy = abs(src.transform.e)
        h, w = src.height, src.width
    mask = (dem == nodata) if nodata is not None else np.zeros_like(dem, bool)
    dem = np.where(mask, np.nan, dem)

    # np.gradient over axis0 (rows, increasing southward) and axis1 (cols, east).
    dz_drow, dz_dx = np.gradient(dem, dy, dx)
    slope_deg = np.degrees(np.arctan(np.hypot(dz_dx, dz_drow)))

    # Downslope compass azimuth (0=N, clockwise). Rows increase southward, so the
    # north gradient is -dz_drow; the downhill vector is (-dz_dx east, +dz_drow
    # north-of-south = ...). Compose directly:
    #   east_down = -dz_dx ; north_down = dz_drow  (since +row = south)
    aspect = (np.degrees(np.arctan2(-dz_dx, dz_drow))) % 360.0
    grad = np.hypot(dz_dx, dz_drow)
    aspect = np.where(grad < 1e-4, np.nan, aspect)   # flat → undefined

    slope_deg = np.where(np.isnan(slope_deg) | mask, NODATA, slope_deg)
    aspect = np.where(np.isnan(aspect) | mask, NODATA, aspect)
    return slope_deg, aspect, transform, h, w


def sample(arr: np.ndarray, transform, h: int, w: int,
           xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    inv = ~transform
    cols_f, rows_f = inv * (xs, ys)
    cols = np.floor(cols_f).astype(np.int64)
    rows = np.floor(rows_f).astype(np.int64)
    ok = (rows >= 0) & (rows < h) & (cols >= 0) & (cols < w)
    out = np.full(xs.shape, np.nan, dtype=np.float64)
    if ok.any():
        vals = arr[rows[ok], cols[ok]]
        vals = np.where(vals == NODATA, np.nan, vals)
        out[ok] = vals
    return out


def main() -> None:
    t0 = time.perf_counter()
    download_dem()
    print("Computing slope & aspect ...")
    slope_arr, aspect_arr, transform, h, w = compute_slope_aspect()

    conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=20)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SET statement_timeout='300s'")

    print("Fetching parcel centroids ...")
    cur.execute(
        "SELECT objectid, ST_X(ST_Centroid(geometry)), ST_Y(ST_Centroid(geometry)) "
        "FROM solar_parcels_kern"
    )
    rows = cur.fetchall()
    oids = np.array([r[0] for r in rows], dtype=np.int64)
    lons = np.array([r[1] for r in rows], dtype=np.float64)
    lats = np.array([r[2] for r in rows], dtype=np.float64)
    print(f"  {len(oids)} parcels")

    tx = Transformer.from_crs("EPSG:4326", WORKING_CRS, always_xy=True)
    xs, ys = tx.transform(lons, lats)
    xs = np.asarray(xs)
    ys = np.asarray(ys)
    slope_vals = sample(slope_arr, transform, h, w, xs, ys)
    aspect_vals = sample(aspect_arr, transform, h, w, xs, ys)
    n_slope = int(np.isfinite(slope_vals).sum())
    print(f"  sampled slope for {n_slope}/{len(oids)} parcels")

    print("Adding columns + writing values ...")
    cur.execute(
        "ALTER TABLE solar_parcels_kern "
        "ADD COLUMN IF NOT EXISTS slope_degrees double precision, "
        "ADD COLUMN IF NOT EXISTS aspect_degrees double precision"
    )
    payload = [
        (
            int(o),
            None if not np.isfinite(s) else round(float(s), 3),
            None if not np.isfinite(a) else round(float(a), 1),
        )
        for o, s, a in zip(oids, slope_vals, aspect_vals)
    ]
    t = time.time()
    for i in range(0, len(payload), 5000):
        chunk = payload[i : i + 5000]
        execute_values(
            cur,
            "UPDATE solar_parcels_kern p SET slope_degrees = v.s, aspect_degrees = v.a "
            "FROM (VALUES %s) AS v(oid, s, a) WHERE p.objectid = v.oid",
            chunk,
            template="(%s,%s::double precision,%s::double precision)",
        )
    print(f"  updated {len(payload)} parcels ({time.time() - t:.1f}s)")

    cur.execute("ANALYZE solar_parcels_kern")
    cur.execute(
        "SELECT COUNT(slope_degrees), MIN(slope_degrees), AVG(slope_degrees), "
        "MAX(slope_degrees), COUNT(*) FILTER (WHERE slope_degrees > 15) "
        "FROM solar_parcels_kern"
    )
    cnt, mn, avg, mx, steep = cur.fetchone()
    print(f"slope_degrees: n={cnt} min={mn:.2f} avg={avg:.2f} max={mx:.2f} "
          f"(>15°: {steep})")
    print(f"Done in {time.perf_counter() - t0:.1f}s total.")
    conn.close()


if __name__ == "__main__":
    main()
