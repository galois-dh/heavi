"""Download a 30 m DEM clip over Sonoma from the USGS 3DEP ImageServer.

The 3DEP service is natively ~1 m and supports exportImage with arbitrary
output bbox / CRS / size. We request directly into our working CRS / grid so
the DEM aligns 1:1 with the LANDFIRE clips — no second-pass reprojection
needed, and slope can be computed in true metres.
"""

from __future__ import annotations

import sys
from pathlib import Path

import requests
from rasterio.warp import transform_bounds

from . import config as cfg


def main() -> int:
    cfg.ensure_dirs()
    if cfg.DEM_TIF.exists():
        print(f"Already have {cfg.DEM_TIF}; skipping.")
        return 0

    # Compute target grid in working CRS (EPSG:3310).
    tgt_bbox = transform_bounds("EPSG:4326", cfg.WORKING_CRS, *cfg.SONOMA_BBOX_4326)
    width = int(round((tgt_bbox[2] - tgt_bbox[0]) / cfg.TARGET_PIX_M))
    height = int(round((tgt_bbox[3] - tgt_bbox[1]) / cfg.TARGET_PIX_M))
    print(f"Requesting {width}×{height} DEM @ {cfg.TARGET_PIX_M:.0f} m in {cfg.WORKING_CRS} ...")

    # f=image returns 500 for grids over ~3000 px on a side; f=json returns a
    # JSON descriptor with an ``href`` to the temp output TIFF on the same
    # host. Fetch the href in a second request.
    params = {
        "bbox": ",".join(str(v) for v in tgt_bbox),
        "bboxSR": "3310",
        "size": f"{width},{height}",
        "imageSR": "3310",
        "format": "tiff",
        "pixelType": "F32",
        "interpolation": "RSP_BilinearInterpolation",
        "noDataInterpretation": "esriNoDataMatchAny",
        "f": "json",
    }
    r = requests.get(cfg.DEM_IMAGESERVER_URL, params=params, timeout=600)
    r.raise_for_status()
    meta = r.json()
    href = meta.get("href")
    if not href:
        raise RuntimeError(f"exportImage returned no href: {meta}")
    print(f"  fetching {href}")
    r = requests.get(href, timeout=600, stream=True)
    r.raise_for_status()
    with cfg.DEM_TIF.open("wb") as f:
        for chunk in r.iter_content(chunk_size=4 << 20):
            f.write(chunk)
    print(f"  wrote {cfg.DEM_TIF} ({cfg.DEM_TIF.stat().st_size / 1_000_000:.1f} MB)")

    # Quick sanity check: ensure rasterio can read what we got (the
    # exportImage endpoint will sometimes return a small JSON error blob
    # instead of binary).
    import rasterio

    try:
        with rasterio.open(cfg.DEM_TIF) as src:
            print(f"  dtype={src.dtypes[0]} crs={src.crs} size={src.width}×{src.height}")
            if src.width != width or src.height != height:
                print(
                    f"  WARN: returned size {src.width}×{src.height} != requested {width}×{height}"
                )
    except Exception as e:
        # Show whatever the server sent — usually a small JSON error.
        head = cfg.DEM_TIF.read_bytes()[:500]
        print(f"  ERROR: cannot open as raster ({e}); head={head[:200]!r}", file=sys.stderr)
        cfg.DEM_TIF.unlink()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
