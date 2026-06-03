"""Constrained AHP weight optimization (Heavi Weight Adaptation Spec, Steps 4-5).

Given the cached per-criterion score matrices (from precompute_weight_matrix.py),
find, per NERC region, the weight vector W that best discriminates real EIA
installations from random in-region land — subject to the literature weight
bounds (W_min[i] ≤ W[i] ≤ W_max[i]) and the simplex constraint (Σ W = 1).

This is constrained optimization, NOT machine learning: the criteria and their
bounds are fixed by the academic literature; only the weights move, and only
within published ranges. The output is interpretable and deterministic.

Objective: a sum of the spec's two named objectives, both maximized —

    J(W) = [ mean σ((comp_eia-τ)/T) - mean σ((comp_random-τ)/T) ]   # high-rate sep (AC5)
         + [ mean(comp_eia)         - mean(comp_random)          ]   # mean sep (AC6)

with τ = 0.70 (the High cutoff). The composite for a location mirrors the
scoring pipeline exactly — a mask-weighted average over the criteria that had
data:

    comp(W) = Σ_j (score_j · W_j · mask_j) / Σ_j (W_j · mask_j)

The first term pushes EIA composites above the High cutoff while pushing random
land below it; the second preserves/improves the raw EIA-vs-random gap.
Optimized with scipy SLSQP (bounds + equality constraint), starting from the
literature default weights.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import asyncpg
import numpy as np
from scipy.optimize import minimize

from .nerc_regions import NERC_REGION_NAMES

CACHE_DIR = Path(__file__).resolve().parents[1] / "weight_cache"

HIGH_THRESHOLD = 0.70   # rating cutoff in solar_scoring_v2 (composite ≥ 0.70 → High)
SIGMOID_T = 0.05        # smoothing temperature for the high-rate surrogate
MIN_EIA_FOR_OPT = 20    # spec: regions with <20 EIA fall back to default weights

_ACADEMIC_BASIS = (
    "Weights constrained to ranges from Doorga et al. (2019) and Al-Shammari "
    "et al. (2026); optimized against EIA Form 860 installations within the "
    "literature-supported range (constrained AHP, not unconstrained ML)."
)

# Curated per-region grid/resource character (from the spec's NERC table) used to
# give weight changes a human-readable regional rationale.
_REGION_CHARACTER: dict[str, str] = {
    "WECC":  "sparse western transmission and highly variable terrain/resource",
    "ERCOT": "dense in-region grid with high, fairly uniform irradiance",
    "SPP":   "flat Great Plains terrain with moderate, variable resource",
    "MISO":  "dense Upper-Midwest grid over flat cropland",
    "PJM":   "very dense Mid-Atlantic grid over rolling-to-mountainous terrain",
    "SERC":  "moderate Southeastern grid, humid, moderate-to-high resource",
    "NPCC":  "dense Northeastern grid, lower and seasonal resource",
}


# ─── bounds + matrices ─────────────────────────────────────────────────────


async def load_bounds(pool: asyncpg.Pool) -> dict[str, dict[str, float]]:
    """criterion_id → {min, max, default} for the 8 scored solar criteria."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT criterion_id, weight_default, weight_min, weight_max
            FROM methodology_criteria
            WHERE workflow_type='solar_siting' AND criterion_type='scored'
            ORDER BY criterion_id
            """
        )
    return {
        r["criterion_id"]: {
            "min": float(r["weight_min"]), "max": float(r["weight_max"]),
            "default": float(r["weight_default"]),
        }
        for r in rows
    }


def _matrices(payload: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return (eia_scores, eia_mask, rnd_scores, rnd_mask) as float arrays,
    dropping rows that errored during precompute."""
    def build(rows: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
        good = [r for r in rows if r.get("scores") is not None and r.get("mask") is not None]
        if not good:
            n = len(payload["criteria_order"])
            return np.zeros((0, n)), np.zeros((0, n))
        s = np.array([r["scores"] for r in good], dtype=float)
        m = np.array([r["mask"] for r in good], dtype=float)
        return s, m
    es, em = build(payload["eia"])
    rs, rm = build(payload["random"])
    return es, em, rs, rm


def _composites(scores: np.ndarray, mask: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Mask-weighted average composite per row, mirroring the scoring pipeline."""
    if scores.shape[0] == 0:
        return np.zeros(0)
    num = (scores * mask) @ w
    den = mask @ w
    den = np.where(den <= 1e-9, np.nan, den)
    comp = num / den
    return np.nan_to_num(comp, nan=0.0)


# ─── projection: enforce bounds + Σ=1 exactly ──────────────────────────────


def _project(w: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """Project w onto {lo ≤ w ≤ hi, Σw = 1}. Feasible because Σlo ≤ 1 ≤ Σhi.
    Clip, then redistribute the residual into available headroom/slack."""
    w = np.clip(w, lo, hi)
    for _ in range(100):
        residual = 1.0 - w.sum()
        if abs(residual) < 1e-12:
            break
        if residual > 0:
            room = hi - w
            total = room.sum()
            if total <= 1e-12:
                break
            w = w + room * (residual / total)
        else:
            room = w - lo
            total = room.sum()
            if total <= 1e-12:
                break
            w = w + room * (residual / total)
        w = np.clip(w, lo, hi)
    return w


# ─── per-region optimization ───────────────────────────────────────────────


def _high_rate(comp: np.ndarray) -> float:
    return float(np.mean(comp >= HIGH_THRESHOLD)) if comp.size else 0.0


def optimize_region(
    region: str, payload: dict[str, Any], bounds: dict[str, dict[str, float]],
    calibrated_at: str,
) -> dict[str, Any]:
    """Run the constrained optimization for one region and build its profile."""
    crit = payload["criteria_order"]
    lo = np.array([bounds[c]["min"] for c in crit])
    hi = np.array([bounds[c]["max"] for c in crit])
    w0 = np.array([bounds[c]["default"] for c in crit])

    es, em, rs, rm = _matrices(payload)
    n_eia, n_rnd = es.shape[0], rs.shape[0]

    # in-sample baseline (default weights)
    comp_eia_def = _composites(es, em, w0)
    comp_rnd_def = _composites(rs, rm, w0)
    sep_default = float(comp_eia_def.mean() - comp_rnd_def.mean()) if n_eia and n_rnd else 0.0
    high_default = _high_rate(comp_eia_def)

    method = "constrained_optimization"
    note_fallback = None
    if n_eia < MIN_EIA_FOR_OPT or n_rnd == 0:
        method = "literature_default"
        note_fallback = (
            f"Only {n_eia} EIA installations available (<{MIN_EIA_FOR_OPT}); "
            "using literature default weights without optimization."
        )
        w_opt = w0.copy()
    else:
        def neg_obj(w: np.ndarray) -> float:
            ce = _composites(es, em, w)
            cr = _composites(rs, rm, w)
            # High-rate separation (spec "alternative objective" — targets AC5)
            high_sep = (np.mean(_sigmoid((ce - HIGH_THRESHOLD) / SIGMOID_T))
                        - np.mean(_sigmoid((cr - HIGH_THRESHOLD) / SIGMOID_T)))
            # Mean separation (spec "primary objective" — targets AC6)
            mean_sep = float(ce.mean() - cr.mean())
            return -(high_sep + mean_sep)

        res = minimize(
            neg_obj, x0=w0,
            bounds=list(zip(lo, hi)),
            constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1.0}],
            method="SLSQP",
            options={"maxiter": 500, "ftol": 1e-9},
        )
        w_opt = _project(np.asarray(res.x, dtype=float), lo, hi)

    # in-sample optimized metrics
    comp_eia_opt = _composites(es, em, w_opt)
    comp_rnd_opt = _composites(rs, rm, w_opt)
    sep_opt = float(comp_eia_opt.mean() - comp_rnd_opt.mean()) if n_eia and n_rnd else 0.0
    high_opt = _high_rate(comp_eia_opt)

    # per-criterion EIA-vs-random separation (drives the human reason text)
    crit_sep = (
        (es * em).sum(0) / np.maximum(em.sum(0), 1) -
        (rs * rm).sum(0) / np.maximum(rm.sum(0), 1)
    ) if n_eia and n_rnd else np.zeros(len(crit))

    weights = {c: round(float(w_opt[i]), 4) for i, c in enumerate(crit)}
    default_weights = {c: round(float(w0[i]), 4) for i, c in enumerate(crit)}
    weight_changes = _weight_changes(region, crit, w0, w_opt, crit_sep)

    profile = {
        "region": region,
        "region_name": NERC_REGION_NAMES.get(region, region),
        "method": method,
        "n_eia_installations": n_eia,
        "n_random_comparisons": n_rnd,
        "n_eia_excluded": payload.get("n_eia_excluded"),
        "optimized_weights": weights,
        "default_weights": default_weights,
        "weight_changes": weight_changes,
        "validation": {
            "pct_eia_high_default_weights": round(high_default, 4),
            "pct_eia_high_optimized_weights": round(high_opt, 4),
            "mean_separation_default": round(sep_default, 4),
            "mean_separation_optimized": round(sep_opt, 4),
        },
        "academic_basis": _ACADEMIC_BASIS,
        "calibrated_at": calibrated_at,
    }
    if note_fallback:
        profile["note"] = note_fallback
    return profile


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50, 50)))


def _weight_changes(
    region: str, crit: list[str], w0: np.ndarray, w: np.ndarray, crit_sep: np.ndarray,
) -> dict[str, dict[str, Any]]:
    """Human-readable change record for criteria whose weight moved ≥ 0.005."""
    character = _REGION_CHARACTER.get(region, "regional characteristics")
    out: dict[str, dict[str, Any]] = {}
    for i, c in enumerate(crit):
        delta = float(w[i] - w0[i])
        if abs(delta) < 0.005:
            continue
        direction = "increased" if delta > 0 else "decreased"
        sep = float(crit_sep[i])
        out[c] = {
            "from": round(float(w0[i]), 4),
            "to": round(float(w[i]), 4),
            "reason": (
                f"Weight {direction} ({delta:+.3f}) within the literature bound: "
                f"in {region} ({character}), this criterion's EIA-vs-random score "
                f"separation is {sep:+.3f}, so the calibration shifts weight "
                f"{'toward' if delta > 0 else 'away from'} it."
            ),
        }
    return out


# ─── storage ───────────────────────────────────────────────────────────────


async def store_profile(pool: asyncpg.Pool, profile: dict[str, Any]) -> None:
    """Upsert a regional weight profile. weights = optimized weights; metadata =
    everything else needed to explain the calibration."""
    weights = profile["optimized_weights"]
    metadata = {
        k: v for k, v in profile.items()
        if k not in ("optimized_weights", "calibrated_at")
    }
    cal = profile["calibrated_at"]
    if isinstance(cal, str):
        cal = datetime.fromisoformat(cal) if "T" in cal else date.fromisoformat(cal)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO regional_weight_profiles
                (region, workflow_type, weights, metadata, calibrated_at)
            VALUES ($1, 'solar_siting', $2, $3, $4)
            ON CONFLICT (region) DO UPDATE
              SET weights = EXCLUDED.weights,
                  metadata = EXCLUDED.metadata,
                  calibrated_at = EXCLUDED.calibrated_at
            """,
            profile["region"], json.dumps(weights), json.dumps(metadata),
            cal,
        )


async def get_profile(
    pool: asyncpg.Pool, region: str
) -> dict[str, Any] | None:
    """Fetch a stored profile (weights + metadata) for a region, or None."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT weights, metadata, calibrated_at FROM regional_weight_profiles "
            "WHERE region=$1 AND workflow_type='solar_siting'",
            region,
        )
    if row is None:
        return None
    weights = row["weights"]
    metadata = row["metadata"]
    if isinstance(weights, str):
        weights = json.loads(weights)
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    return {"weights": weights, "metadata": metadata, "calibrated_at": row["calibrated_at"]}
