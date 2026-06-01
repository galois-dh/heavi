"""Google GRRR (Global Runoff Reanalysis & Reforecast) — Zarr in public GCS.

Source: gs://flood-forecasting/hydrologic_predictions/model_id_8583a5c2_v0/
  reanalysis/streamflow.zarr/         daily streamflow 1980-2023
  reforecast/streamflow.zarr/         daily reforecast
  return_periods.zarr/                10/50/100/500-yr return period flows

Coverage: ~1 M global HydroBASINS reaches. CC-BY-4.0.

Per-point usage: resolve the catchment ID for a lat/lng (HydroBASINS Pfafstetter
level-12 polygon), then fetch the streamflow time series for that catchment.
This requires the xarray + zarr + gcsfs stack which is heavy; we do a lazy
import so the rest of the API package boots without them.
"""

from __future__ import annotations

from typing import Any

BUCKET = "gs://flood-forecasting/hydrologic_predictions/model_id_8583a5c2_v0"
RETURN_PERIODS_PATH = f"{BUCKET}/return_periods.zarr"
REANALYSIS_PATH = f"{BUCKET}/reanalysis/streamflow.zarr"


def _open_return_periods() -> Any:
    """Lazy-load the Zarr return-periods dataset from public GCS.

    Requires ``xarray``, ``zarr``, and ``gcsfs`` (anonymous mode works since
    the bucket is public). Raises ImportError with a helpful message if not
    installed."""
    try:
        import xarray as xr
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "xarray + zarr + gcsfs are required to query GRRR. Install with:\n"
            "  pip install 'xarray[complete]' zarr gcsfs"
        ) from e
    return xr.open_zarr(RETURN_PERIODS_PATH, storage_options={"token": "anon"})


def grrr_return_periods(catchment_id: int) -> dict[str, float] | None:
    """Return {10: cfs, 50: cfs, 100: cfs, 500: cfs} for one HydroBASINS reach,
    or None if the catchment_id is not in the dataset.

    NOT async — Zarr/GCSFS use synchronous IO; call from a threadpool if you
    need non-blocking behaviour in FastAPI."""
    ds = _open_return_periods()
    if catchment_id not in ds["hybas_id"].values:
        return None
    sel = ds.sel(hybas_id=catchment_id)
    return {
        int(rp): float(sel["streamflow"].sel(return_period=int(rp)).values)
        for rp in sel["return_period"].values
        if int(rp) in (10, 50, 100, 500)
    }
