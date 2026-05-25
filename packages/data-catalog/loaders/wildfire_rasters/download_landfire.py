"""Download LANDFIRE 2022 FBFM40 + Canopy Cover for Sonoma via the LFPS API.

LFPS (LANDFIRE Product Service) is an ArcGIS GP service that accepts a
semicolon-delimited layer list and an AOI, runs an async job, and returns a
zip containing a multi-band GeoTIFF and per-layer GeoTIFFs.

We submit one job for both FBFM40 (``220F40``) and Canopy Cover (``220CC``),
poll until done, download the zip, and unpack the individual layer rasters
into raw/. Then we clip + reproject each into the working CRS / 30 m grid.
"""

from __future__ import annotations

import shutil
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import rasterio
import requests
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds

from . import config as cfg

AOI = " ".join(str(v) for v in cfg.SONOMA_BBOX_4326)  # "W S E N", WGS84


def submit_job() -> str:
    print(f"Submitting LFPS job: layers={cfg.LANDFIRE_LAYER_LIST}  AOI={AOI}")
    body = {
        "Layer_List": cfg.LANDFIRE_LAYER_LIST,
        "Area_of_Interest": AOI,
        "Email": cfg.LANDFIRE_EMAIL,
    }
    r = requests.post(
        cfg.LANDFIRE_SUBMIT_URL,
        json=body,
        headers={"Content-Type": "application/json"},
        timeout=60,
    )
    r.raise_for_status()
    j = r.json()
    if not j.get("jobId"):
        raise RuntimeError(f"submit failed: {j}")
    print(f"  jobId = {j['jobId']}")
    return j["jobId"]


def poll_until_done(job_id: str, timeout_s: int = 1200) -> dict:
    t0 = time.time()
    while True:
        r = requests.get(cfg.LANDFIRE_STATUS_URL, params={"JobId": job_id}, timeout=60)
        r.raise_for_status()
        j = r.json()
        status = j.get("status", "?")
        elapsed = time.time() - t0
        print(f"  [{elapsed:6.1f}s] status={status}")
        if status == "Succeeded":
            return j
        if status in {"Failed", "Cancelled", "TimedOut"}:
            msgs = "\n".join(m.get("description", "") for m in j.get("messages", [])[-6:])
            raise RuntimeError(f"LFPS job {job_id} failed:\n{msgs}")
        if elapsed > timeout_s:
            raise RuntimeError(f"LFPS job {job_id} timed out after {timeout_s}s")
        time.sleep(10)


def fetch_output(status_json: dict) -> str:
    out_url = status_json.get("outputFile")
    if not out_url:
        raise RuntimeError(f"No outputFile in status: {status_json}")
    return out_url


def download(url: str, dest: Path) -> None:
    print(f"Downloading {url} → {dest}")
    with requests.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            for chunk in r.iter_content(chunk_size=4 << 20):
                f.write(chunk)
    print(f"  {dest.stat().st_size / 1_000_000:.1f} MB")


def _grid_3310():
    """Target grid spec in EPSG:3310 at TARGET_PIX_M."""
    tgt_bbox = transform_bounds("EPSG:4326", cfg.WORKING_CRS, *cfg.SONOMA_BBOX_4326)
    transform = from_origin(tgt_bbox[0], tgt_bbox[3], cfg.TARGET_PIX_M, cfg.TARGET_PIX_M)
    w = int(round((tgt_bbox[2] - tgt_bbox[0]) / cfg.TARGET_PIX_M))
    h = int(round((tgt_bbox[3] - tgt_bbox[1]) / cfg.TARGET_PIX_M))
    return transform, w, h


def reproject_to_working(src_path: Path, dst_path: Path, *, categorical: bool) -> None:
    transform, w, h = _grid_3310()
    with rasterio.open(src_path) as src:
        src_data = src.read(1)
        src_nodata = src.nodata
        out_dtype = "int16" if categorical else "float32"
        nodata_out = src_nodata if src_nodata is not None else (-9999 if not categorical else -1)
        out = np.full((h, w), nodata_out, dtype=out_dtype)
        reproject(
            source=src_data,
            destination=out,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=transform,
            dst_crs=cfg.WORKING_CRS,
            resampling=Resampling.nearest if categorical else Resampling.bilinear,
            src_nodata=src_nodata,
            dst_nodata=nodata_out,
        )
        profile = {
            "driver": "GTiff",
            "dtype": out_dtype,
            "count": 1,
            "width": w,
            "height": h,
            "transform": transform,
            "crs": cfg.WORKING_CRS,
            "nodata": nodata_out,
            "compress": "lzw",
            "tiled": True,
        }
        with rasterio.open(dst_path, "w", **profile) as dst:
            dst.write(out, 1)
    print(f"  wrote {dst_path} ({w}×{h}, {out_dtype})")


def main() -> int:
    cfg.ensure_dirs()
    if cfg.FBFM40_TIF.exists() and cfg.CC_TIF.exists():
        print("Already have FBFM40 + CC clips; skipping.")
        return 0

    if not cfg.LANDFIRE_ZIP.exists() or cfg.LANDFIRE_ZIP.stat().st_size < 100_000:
        job_id = submit_job()
        status_json = poll_until_done(job_id)
        out_url = fetch_output(status_json)
        download(out_url, cfg.LANDFIRE_ZIP)
    else:
        print(f"Using cached {cfg.LANDFIRE_ZIP}")

    print("Extracting LANDFIRE multi-band TIFF ...")
    with zipfile.ZipFile(cfg.LANDFIRE_ZIP) as zf:
        tifs = [n for n in zf.namelist() if n.lower().endswith(".tif")]
        if not tifs:
            raise RuntimeError(f"No TIFF in LFPS output zip; members: {zf.namelist()}")
        multiband_tmp = cfg.RAW_DIR / "landfire_multiband.tif"
        with zf.open(tifs[0]) as s, multiband_tmp.open("wb") as o:
            shutil.copyfileobj(s, o)

    print(f"Splitting bands from {multiband_tmp.name} and reprojecting → {cfg.WORKING_CRS} ...")
    _split_and_reproject(multiband_tmp)

    try:
        multiband_tmp.unlink()
    except OSError:
        pass
    return 0


def _split_and_reproject(multiband_path: Path) -> None:
    """Split a LFPS multi-band TIFF (band 1 = FBFM40, band 2 = CC) into two
    single-band rasters in the working CRS / 30 m grid. Band assignment is
    verified by the per-band ``BandName`` tag so this also tolerates
    reordering in future LFPS releases."""
    transform, w, h = _grid_3310()
    with rasterio.open(multiband_path) as src:
        band_map: dict[str, int] = {}
        for b in range(1, src.count + 1):
            name = (src.tags(b).get("BandName") or src.descriptions[b - 1] or "").upper()
            if "F40" in name or "FBFM40" in name:
                band_map["fbfm40"] = b
            elif "_CC_" in name or name.endswith("_CC") or "CANOPY" in name:
                band_map["cc"] = b
        if "fbfm40" not in band_map or "cc" not in band_map:
            raise RuntimeError(f"Could not identify FBFM40/CC bands in {multiband_path}; tags="
                               f"{[src.tags(b) for b in range(1, src.count + 1)]}")
        print(f"  band map: {band_map}")

        for key, b_idx in band_map.items():
            categorical = key == "fbfm40"
            out_dtype = "int16" if categorical else "float32"
            nodata_out = int(src.nodata) if src.nodata is not None else (-1 if categorical else -9999)
            out = np.full((h, w), nodata_out, dtype=out_dtype)
            reproject(
                source=src.read(b_idx),
                destination=out,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=transform,
                dst_crs=cfg.WORKING_CRS,
                resampling=Resampling.nearest if categorical else Resampling.bilinear,
                src_nodata=src.nodata,
                dst_nodata=nodata_out,
            )
            dst_path = cfg.FBFM40_TIF if key == "fbfm40" else cfg.CC_TIF
            profile = {
                "driver": "GTiff",
                "dtype": out_dtype,
                "count": 1,
                "width": w,
                "height": h,
                "transform": transform,
                "crs": cfg.WORKING_CRS,
                "nodata": nodata_out,
                "compress": "lzw",
                "tiled": True,
            }
            with rasterio.open(dst_path, "w", **profile) as dst:
                dst.write(out, 1)
            print(f"  wrote {dst_path} ({w}×{h}, {out_dtype})")


if __name__ == "__main__":
    raise SystemExit(main())
