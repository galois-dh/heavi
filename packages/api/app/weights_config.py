"""Runtime weight configuration.

Calibrated per-NERC solar-siting weights are private and live in
`config/weights.json` (gitignored). A public clone instead ships
`config/weights.example.json`, which carries the published literature default
weights (Doorga et al. 2019) and an empty `regional` map — so scoring falls back
to the literature defaults everywhere and the system still works end to end.

Precedence at scoring time (in `solar_scoring_v2.score_solar_siting`):
caller override > this file's calibrated regional profile > database profile >
literature defaults. If `weights.json` is absent the calibrated map is empty and
the file simply contributes nothing.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import Any

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


@functools.lru_cache(maxsize=1)
def _load() -> dict[str, Any]:
    """Load weights.json (private) if present, else weights.example.json
    (literature defaults). Returns {} when neither file is readable."""
    for name in ("weights.json", "weights.example.json"):
        path = _CONFIG_DIR / name
        if path.exists():
            try:
                data = json.loads(path.read_text())
                return data if isinstance(data, dict) else {}
            except (OSError, ValueError):
                return {}
    return {}


def file_weight_profile(region: str | None) -> dict[str, Any] | None:
    """Calibrated weight profile for `region` from the config file, shaped like
    the database profile (``{"weights": {...}, "metadata": {...}}``), or None
    when the file has no calibrated entry for that region (e.g. a public clone
    with only literature defaults)."""
    if not region:
        return None
    entry = _load().get("regional", {}).get(region)
    if not entry or not entry.get("weights"):
        return None
    metadata = entry.get("metadata") or {}
    return {
        "weights": entry["weights"],
        "metadata": {
            "method": metadata.get("method", "constrained_optimization"),
            "n_eia_installations": metadata.get("n_eia_installations"),
        },
    }
