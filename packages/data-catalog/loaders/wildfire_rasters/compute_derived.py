"""Compute derived rasters from the Sonoma raster bundle.

All inputs are already on the same EPSG:3310 grid at 30 m resolution, so we
can operate on plain numpy arrays. Three outputs:

  * slope_deg.tif         — slope in degrees, from DEM (numpy gradients)
  * dist_to_burnable_m.tif — Euclidean distance to nearest burnable FBFM40
                             cell, in metres (scipy.ndimage.distance_transform_edt)
  * cc_30m / cc_100m / cc_300m — mean canopy cover within circular buffers of
                             those radii (FFT convolution with a disk kernel)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import rasterio
import scipy.ndimage as ndi
from scipy.signal import fftconvolve

from . import config as cfg


def _write_like(template_path: Path, dst_path: Path, data: np.ndarray, *, nodata: float, dtype: str) -> None:
    with rasterio.open(template_path) as src:
        profile = src.profile.copy()
    profile.update(
        {
            "dtype": dtype,
            "count": 1,
            "nodata": nodata,
            "compress": "lzw",
            "tiled": True,
        }
    )
    with rasterio.open(dst_path, "w", **profile) as dst:
        dst.write(data.astype(dtype), 1)
    print(f"  wrote {dst_path.name} ({data.shape[1]}×{data.shape[0]}, {dtype})")


def compute_slope() -> None:
    print("Computing slope from DEM ...")
    with rasterio.open(cfg.DEM_TIF) as src:
        dem = src.read(1).astype(np.float32)
        nodata = src.nodata
        # Pixel size in metres (EPSG:3310 is metric and uniform here).
        dx = abs(src.transform.a)
        dy = abs(src.transform.e)

    if nodata is not None:
        mask = dem == nodata
        dem = np.where(mask, np.nan, dem)
    else:
        mask = np.zeros_like(dem, dtype=bool)

    # Central-difference gradient. np.gradient handles edges with one-sided.
    dz_dy, dz_dx = np.gradient(dem, dy, dx)
    slope_rad = np.arctan(np.hypot(dz_dx, dz_dy))
    slope_deg = np.degrees(slope_rad)

    # Fill nodata.
    slope_deg = np.where(np.isnan(slope_deg) | mask, -9999.0, slope_deg).astype(np.float32)
    _write_like(cfg.DEM_TIF, cfg.SLOPE_TIF, slope_deg, nodata=-9999.0, dtype="float32")


def compute_distance_to_burnable() -> None:
    print("Computing distance-to-burnable from FBFM40 ...")
    with rasterio.open(cfg.FBFM40_TIF) as src:
        fbfm = src.read(1)
        px_m = abs(src.transform.a)

    # Burnable = cell IS in FBFM40 AND NOT a non-burnable code.
    burnable = ~np.isin(fbfm, list(cfg.NB_FBFM40_CODES))
    # distance_transform_edt computes distance from each False pixel to the
    # nearest True pixel — so we feed it the *non-burnable* mask and ask for
    # distance to the nearest burnable.
    # Equivalently: distance from every cell to the nearest True in `burnable`,
    # which is distance_transform_edt(~burnable) with the right convention.
    if burnable.sum() == 0:
        print("  WARN: no burnable cells in raster — output will be all nodata")
        dist = np.full_like(fbfm, -9999.0, dtype=np.float32)
    else:
        # distance_transform_edt(input) returns 0 where input is True and the
        # distance to the nearest True elsewhere. So feed it `burnable`.
        # But we need the OPPOSITE: distance from each cell to the nearest
        # burnable cell. That is achieved by passing the non-burnable mask:
        # distance_transform_edt(non-burnable) gives 0 in burnable cells and
        # distance to the nearest burnable in non-burnable cells — which is
        # actually distance to the nearest FALSE cell, i.e. burnable. Confirmed
        # by ndi docs.
        dist_px = ndi.distance_transform_edt(~burnable)
        dist = (dist_px * px_m).astype(np.float32)

    _write_like(cfg.FBFM40_TIF, cfg.DIST_TO_FUEL_TIF, dist, nodata=-9999.0, dtype="float32")


def _disk_kernel(radius_px: float) -> np.ndarray:
    r = int(np.ceil(radius_px))
    y, x = np.ogrid[-r : r + 1, -r : r + 1]
    mask = (x * x + y * y) <= radius_px * radius_px
    k = mask.astype(np.float32)
    k /= k.sum()
    return k


def compute_canopy_buffers() -> None:
    print("Computing canopy-cover buffer means (30, 100, 300 m radius) ...")
    with rasterio.open(cfg.CC_TIF) as src:
        cc = src.read(1).astype(np.float32)
        nodata = src.nodata
        px_m = abs(src.transform.a)

    valid = (cc != nodata) if nodata is not None else np.ones_like(cc, dtype=bool)
    cc_clean = np.where(valid, cc, 0.0)

    for radius_m, dst_path in (
        (30.0, cfg.CC_30_TIF),
        (100.0, cfg.CC_100_TIF),
        (300.0, cfg.CC_300_TIF),
    ):
        radius_px = max(radius_m / px_m, 1.0)
        kernel = _disk_kernel(radius_px)
        # Weighted mean: sum(value * mask_valid) / sum(mask_valid) within
        # the disk. Both convolutions are O(N log N) via FFT.
        num = fftconvolve(cc_clean, kernel, mode="same")
        den = fftconvolve(valid.astype(np.float32), kernel, mode="same")
        out = np.where(den > 1e-6, num / den, -9999.0).astype(np.float32)
        out = np.where(valid, out, -9999.0)
        _write_like(cfg.CC_TIF, dst_path, out, nodata=-9999.0, dtype="float32")


def main() -> int:
    cfg.ensure_dirs()
    for p in (cfg.DEM_TIF, cfg.FBFM40_TIF, cfg.CC_TIF, cfg.WRC_BP_TIF):
        if not p.exists():
            print(f"ERROR: missing {p}", file=sys.stderr)
            return 1
    compute_slope()
    compute_distance_to_burnable()
    compute_canopy_buffers()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
