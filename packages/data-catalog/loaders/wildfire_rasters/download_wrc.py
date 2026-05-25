"""Download the USFS WRC California bundle and extract the burn-probability
GeoTIFF clipped to the Sonoma County extent.

The WRC California archive (RDS-2020-0060-2) bundles every WRC layer for the
state into a ~1 GB ZIP. We download once, unpack only the BurnProbability
raster, and clip-and-reproject it to ``rasters/sonoma/raw/wrc_bp_sonoma.tif``.
"""

from __future__ import annotations

import io
import shutil
import sys
import zipfile
from pathlib import Path

import rasterio
import requests
from rasterio.warp import Resampling, calculate_default_transform, reproject
from rasterio.windows import from_bounds

from . import config as cfg


def _download(url: str, dest: Path) -> None:
    print(f"Downloading {url} → {dest} ...")
    with requests.get(url, stream=True, timeout=3600) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        seen = 0
        with dest.open("wb") as f:
            for chunk in r.iter_content(chunk_size=8 << 20):
                f.write(chunk)
                seen += len(chunk)
                if total:
                    pct = seen / total * 100
                    print(f"\r  {seen / 1_000_000:.0f}/{total / 1_000_000:.0f} MB ({pct:.1f}%)", end="")
        print()


def _find_bp_member(zf: zipfile.ZipFile) -> str:
    """Locate the CONUS burn-probability raster.

    In RDS-2016-0034-2 the layer lives at
    ``Data/I_FSim_CONUS_LF2014_270m/CONUS_iBP.tif`` (``iBP`` for
    "integrated burn probability"). The naming differs between the 30 m
    upsampled and 270 m source bundles, so accept either ``iBP`` or
    ``BurnProbability`` suffixes.
    """
    names = zf.namelist()
    candidates = [
        n for n in names
        if n.lower().endswith(".tif") and (
            "burnprobability" in n.lower().replace("_", "")
            or n.lower().endswith("ibp.tif")
            or n.lower().endswith("_bp.tif")
        )
    ]
    # Drop Alaska/Hawaii regional outputs; we're scoped to CONUS.
    candidates = [n for n in candidates if "conus" in n.lower() or "alaska" not in n.lower() and "hawaii" not in n.lower()]
    candidates = [n for n in candidates if "alaska" not in n.lower() and "hawaii" not in n.lower()]
    if not candidates:
        tifs = [n for n in names if n.lower().endswith(".tif")][:20]
        raise RuntimeError(f"No BurnProbability TIFF in zip; saw: {tifs}")
    candidates.sort(key=lambda n: (n.count("/"), len(n)))
    return candidates[0]


def _clip_and_reproject(src_path: Path, dst_path: Path) -> None:
    print(f"Clipping + reprojecting {src_path.name} → {dst_path.name} ({cfg.WORKING_CRS}) ...")
    with rasterio.open(src_path) as src:
        # First clip to the Sonoma bbox in the source CRS to avoid resampling
        # the whole CONUS raster.
        from rasterio.warp import transform_bounds

        src_bbox = transform_bounds(
            "EPSG:4326",
            src.crs,
            *cfg.SONOMA_BBOX_4326,
            densify_pts=21,
        )
        window = from_bounds(*src_bbox, transform=src.transform).round_offsets().round_lengths()
        # Pad by one pixel so reprojection has neighbours at the edge.
        window = window.crop(src.height, src.width)
        clip = src.read(1, window=window)
        clip_transform = src.window_transform(window)

        # Compute target grid in the working CRS at TARGET_PIX_M resolution.
        from rasterio.warp import transform_bounds as tb

        tgt_bbox = tb("EPSG:4326", cfg.WORKING_CRS, *cfg.SONOMA_BBOX_4326)
        dst_transform, dst_w, dst_h = calculate_default_transform(
            src.crs,
            cfg.WORKING_CRS,
            window.width,
            window.height,
            *src_bbox,
            resolution=cfg.TARGET_PIX_M,
        )
        # Force the requested resolution and bbox so all derived rasters align.
        from rasterio.transform import from_origin

        dst_transform = from_origin(tgt_bbox[0], tgt_bbox[3], cfg.TARGET_PIX_M, cfg.TARGET_PIX_M)
        dst_w = int(round((tgt_bbox[2] - tgt_bbox[0]) / cfg.TARGET_PIX_M))
        dst_h = int(round((tgt_bbox[3] - tgt_bbox[1]) / cfg.TARGET_PIX_M))

        import numpy as np

        out = np.full((dst_h, dst_w), src.nodata if src.nodata is not None else -9999, dtype=np.float32)
        reproject(
            source=clip.astype(np.float32),
            destination=out,
            src_transform=clip_transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs=cfg.WORKING_CRS,
            resampling=Resampling.bilinear,
            src_nodata=src.nodata,
            dst_nodata=src.nodata if src.nodata is not None else -9999,
        )
        profile = {
            "driver": "GTiff",
            "dtype": "float32",
            "count": 1,
            "width": dst_w,
            "height": dst_h,
            "transform": dst_transform,
            "crs": cfg.WORKING_CRS,
            "nodata": src.nodata if src.nodata is not None else -9999,
            "compress": "lzw",
            "tiled": True,
        }
        with rasterio.open(dst_path, "w", **profile) as dst:
            dst.write(out, 1)
    print(f"  wrote {dst_path} ({dst_w}×{dst_h})")


def main() -> int:
    cfg.ensure_dirs()
    if cfg.WRC_BP_TIF.exists():
        print(f"Already have {cfg.WRC_BP_TIF}; skipping.")
        return 0

    if not cfg.WRC_CA_ZIP.exists() or cfg.WRC_CA_ZIP.stat().st_size < 500_000_000:
        _download(cfg.WRC_CA_URL, cfg.WRC_CA_ZIP)
    else:
        print(f"Using cached {cfg.WRC_CA_ZIP}")

    print("Inspecting zip for BurnProbability member ...")
    with zipfile.ZipFile(cfg.WRC_CA_ZIP) as zf:
        member = _find_bp_member(zf)
        print(f"  → {member}")
        extracted = cfg.RAW_DIR / "wrc_bp_california.tif"
        with zf.open(member) as src, extracted.open("wb") as out:
            shutil.copyfileobj(src, out)
    print(f"  extracted {extracted} ({extracted.stat().st_size / 1_000_000:.0f} MB)")

    _clip_and_reproject(extracted, cfg.WRC_BP_TIF)

    # Save disk: remove the California-wide intermediate now we have the
    # Sonoma clip.
    try:
        extracted.unlink()
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
