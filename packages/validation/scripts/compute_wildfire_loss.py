"""Stage 4: Wildfire loss estimation.

Pipeline:
  1. Load fitted vulnerability model coefficients.
  2. Pull every NSI structure with the features we need.
  3. Compute P(destroyed | features) vectorised in numpy.
  4. EAL_i = burn_probability_i × P(destroyed)_i × val_struct_i.
  5. ALTER+UPDATE expected_annual_loss on wildfire_nsi_structures.
  6. Portfolio aggregations + EP curve + reports.
  7. Methodology doc + audit log.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import asyncpg
import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import execute_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from heavi_validation.audit import AuditLogger, AuditRecord
from heavi_validation.methodology import generate_methodology
from heavi_validation.tracing import AuditQuery
from modules.wildfire_loss.metadata import METADATA

load_dotenv(ROOT.parents[1] / ".env")

REPORT_DIR = ROOT / "reports" / "wildfire_loss"
AUDIT_DIR = ROOT / "audit_logs"
FITTED_MODEL_PATH = ROOT / "modules" / "wildfire_vulnerability" / "fitted_model.json"
TABLE = "wildfire_nsi_structures"

STANDARD_RETURN_PERIODS = [10, 25, 50, 100, 250, 500, 1000]

# Histogram buckets in dollars per the user's spec.
EAL_BUCKETS = [
    (0.0, 0.0, "$0"),
    (0.0, 10.0, "$0-10"),
    (10.0, 100.0, "$10-100"),
    (100.0, 500.0, "$100-500"),
    (500.0, 1000.0, "$500-1000"),
    (1000.0, math.inf, "$1000+"),
]


def load_model() -> dict[str, Any]:
    if not FITTED_MODEL_PATH.exists():
        raise RuntimeError(f"No fitted model at {FITTED_MODEL_PATH}; run Stage 3 first.")
    bundle = json.loads(FITTED_MODEL_PATH.read_text())
    print(
        f"Loaded vulnerability model: run_id={bundle['run_id'][:8]}…  "
        f"methodology={bundle['methodology_hash'][:12]}…  "
        f"AUC={bundle['auc_roc']:.3f}"
    )
    return bundle


PULL_SQL = """
SELECT
    fd_id,
    occtype,
    st_damcat,
    val_struct,
    burn_probability,
    distance_to_fuel_m,
    canopy_cover_100m,
    slope_degrees,
    cbfips,
    ST_X(geometry) AS lng,
    ST_Y(geometry) AS lat
FROM wildfire_nsi_structures
WHERE val_struct IS NOT NULL
  AND val_struct > 0
  AND burn_probability IS NOT NULL
  AND distance_to_fuel_m IS NOT NULL
  AND canopy_cover_100m IS NOT NULL
  AND slope_degrees IS NOT NULL
  AND occtype IS NOT NULL
"""


async def pull_structures() -> tuple[pd.DataFrame, list[AuditQuery]]:
    db_url = os.environ["DATABASE_URL"]
    pool = await asyncpg.create_pool(
        db_url, min_size=1, max_size=2, ssl="require", command_timeout=300
    )
    queries: list[AuditQuery] = []
    try:
        async with pool.acquire() as conn:
            await conn.execute("SET statement_timeout = '300s'")
            t = time.perf_counter()
            rows = await conn.fetch(PULL_SQL)
            dt_ms = (time.perf_counter() - t) * 1000.0
            queries.append(
                AuditQuery(
                    sql=PULL_SQL,
                    duration_ms=dt_ms,
                    row_count=len(rows),
                    table_hits=["wildfire_nsi_structures"],
                )
            )
    finally:
        await pool.close()
    df = pd.DataFrame([dict(r) for r in rows])
    return df, queries


def score(df: pd.DataFrame, bundle: dict[str, Any]) -> np.ndarray:
    coef = bundle["coefficients"]
    is_res1 = df["occtype"].astype(str).str.startswith("RES1").astype(float)
    z = (
        coef["const"]
        + coef["burn_probability"] * df["burn_probability"].astype(float)
        + coef["distance_to_fuel_m"] * df["distance_to_fuel_m"].astype(float)
        + coef["canopy_cover_100m"] * df["canopy_cover_100m"].astype(float)
        + coef["slope_degrees"] * df["slope_degrees"].astype(float)
        + coef["is_res1"] * is_res1
    ).to_numpy()
    p = 1.0 / (1.0 + np.exp(-z))
    return p


def upload_eal(df: pd.DataFrame) -> AuditQuery:
    """Append the expected_annual_loss column and bulk-UPDATE."""
    db_url = os.environ["DATABASE_URL"]
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"ALTER TABLE {TABLE} "
                "ADD COLUMN IF NOT EXISTS expected_annual_loss double precision"
            )
            cur.execute(
                "CREATE TEMP TABLE _nsi_eal (fd_id BIGINT PRIMARY KEY, "
                "expected_annual_loss DOUBLE PRECISION) ON COMMIT DROP"
            )
            rows = [
                (int(r.fd_id), float(r.expected_annual_loss))
                for r in df.itertuples(index=False)
            ]
            execute_values(
                cur,
                "INSERT INTO _nsi_eal (fd_id, expected_annual_loss) VALUES %s",
                rows,
                page_size=20_000,
            )
            t = time.perf_counter()
            cur.execute(
                f"UPDATE {TABLE} t SET expected_annual_loss = s.expected_annual_loss "
                f"FROM _nsi_eal s WHERE t.fd_id = s.fd_id"
            )
            dt_ms = (time.perf_counter() - t) * 1000.0
            affected = cur.rowcount
            # Helpful index for the MCP tool's "sort by EAL" queries.
            cur.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_eal "
                f"ON {TABLE} (expected_annual_loss DESC NULLS LAST)"
            )
        conn.commit()
    finally:
        conn.close()
    return AuditQuery(
        sql=f"UPDATE {TABLE} SET expected_annual_loss = … (bulk via temp table)",
        duration_ms=dt_ms,
        row_count=affected,
        table_hits=[TABLE],
    )


# ─── Aggregations ────────────────────────────────────────────────────────────


def aggregate_by_occtype(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["occ_group"] = df["occtype"].astype(str).str.slice(0, 3)
    agg = (
        df.groupby("occ_group")
        .agg(
            n=("expected_annual_loss", "count"),
            total_eal=("expected_annual_loss", "sum"),
            mean_eal=("expected_annual_loss", "mean"),
            median_eal=("expected_annual_loss", "median"),
            total_exposure=("val_struct", "sum"),
        )
        .reset_index()
        .sort_values("total_eal", ascending=False)
    )
    agg["share_of_total_eal"] = agg["total_eal"] / agg["total_eal"].sum()
    return agg


def aggregate_by_tract(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["tract_fips"] = df["cbfips"].astype(str).str.slice(0, 11)
    agg = (
        df.groupby("tract_fips")
        .agg(
            n_structures=("expected_annual_loss", "count"),
            total_eal=("expected_annual_loss", "sum"),
            mean_eal=("expected_annual_loss", "mean"),
            total_exposure=("val_struct", "sum"),
            centroid_lng=("lng", "mean"),
            centroid_lat=("lat", "mean"),
        )
        .reset_index()
        .sort_values("total_eal", ascending=False)
    )
    return agg


def eal_histogram(df: pd.DataFrame) -> pd.DataFrame:
    eal = df["expected_annual_loss"].to_numpy()
    rows = []
    for lo, hi, label in EAL_BUCKETS:
        if hi == 0.0:
            mask = eal == 0.0
        elif math.isinf(hi):
            mask = eal >= lo
        else:
            mask = (eal > lo) & (eal <= hi)
        rows.append(
            {
                "bucket": label,
                "n": int(mask.sum()),
                "share": float(mask.sum() / len(eal)),
                "bucket_total_eal": float(eal[mask].sum()),
            }
        )
    return pd.DataFrame(rows)


def top_n_by_eal(df: pd.DataFrame, n: int = 100) -> pd.DataFrame:
    out = df.nlargest(n, "expected_annual_loss").copy()
    out["tract_fips"] = out["cbfips"].astype(str).str.slice(0, 11)
    cols = [
        "fd_id",
        "occtype",
        "val_struct",
        "expected_annual_loss",
        "p_destroyed",
        "burn_probability",
        "distance_to_fuel_m",
        "canopy_cover_100m",
        "slope_degrees",
        "lat",
        "lng",
        "tract_fips",
    ]
    return out[cols]


def ep_curve(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Occurrence Exceedance Probability (OEP) curve.

    For each property the annual exceedance frequency of an individual loss
    ≥ val_struct is λ_i = BP_i × P(destroyed)_i. We sort the (val_struct, λ)
    pairs descending by val_struct and cumulate λ; the cumulative λ(X) is the
    expected annual frequency of ANY individual loss exceeding the loss level
    X. Return period T(X) = 1 / λ(X).

    Returned curves:
      * `full` — every unique loss level (dense, hundreds of rows)
      * `standard` — values at insurance-industry standard return periods.
    """
    arr = df[["val_struct", "lambda_destroy"]].dropna().to_numpy()
    order = np.argsort(-arr[:, 0])
    losses = arr[order, 0]
    lambdas = arr[order, 1]
    cum_lambda = np.cumsum(lambdas)

    # Keep one row per unique loss level (so dense curve isn't huge).
    keep = np.concatenate(([True], losses[1:] != losses[:-1]))
    full = pd.DataFrame(
        {
            "loss_amount": losses[keep],
            "annual_freq_exceed": cum_lambda[keep],
            "return_period_years": np.where(cum_lambda[keep] > 0, 1.0 / cum_lambda[keep], np.inf),
        }
    )

    # Standard return periods: interpolate to find loss at each RP.
    rp = np.array(STANDARD_RETURN_PERIODS, dtype=float)
    target_lambda = 1.0 / rp
    # losses are descending, cum_lambda increasing → interpolate cum_lambda → loss.
    loss_at_rp = np.interp(target_lambda, cum_lambda[keep], losses[keep])
    standard = pd.DataFrame(
        {
            "return_period_years": rp.astype(int),
            "annual_freq_exceed": target_lambda,
            "loss_amount": loss_at_rp,
        }
    )
    return full, standard


# ─── Nominatim reverse geocoding for top-tract ZIP labels ────────────────────


def reverse_geocode_zip(lat: float, lng: float) -> str | None:
    """One-shot Nominatim reverse geocode → ZIP, with conservative rate limit."""
    import urllib.parse
    import urllib.request

    url = (
        "https://nominatim.openstreetmap.org/reverse?"
        + urllib.parse.urlencode(
            {"lat": lat, "lon": lng, "format": "json", "zoom": 18, "addressdetails": 1}
        )
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Heavi/0.1 (wildfire-loss-report)"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        return (data.get("address") or {}).get("postcode")
    except Exception:
        return None


def attach_top_tract_zips(top_tracts: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    top_tracts = top_tracts.head(n).copy()
    zips: list[str | None] = []
    for i, r in top_tracts.iterrows():
        z = reverse_geocode_zip(r["centroid_lat"], r["centroid_lng"])
        zips.append(z)
        print(f"  tract {r['tract_fips']} → ZIP {z}")
        time.sleep(1.05)  # Nominatim ToS: ≤1 req/sec
    top_tracts["zip_code"] = zips
    return top_tracts


# ─── Report rendering ────────────────────────────────────────────────────────


def render_summary_md(
    *,
    bundle: dict[str, Any],
    n_structures: int,
    total_eal: float,
    mean_eal: float,
    median_eal: float,
    top_tracts: pd.DataFrame,
    by_occ: pd.DataFrame,
    hist: pd.DataFrame,
    standard_ep: pd.DataFrame,
    methodology_hash: str,
    run_id: str,
) -> str:
    lines: list[str] = []
    lines.append("# Wildfire Loss Estimation — Sonoma County Summary\n")
    lines.append(f"_Run ID:_ `{run_id}`  ")
    lines.append(f"_Methodology hash:_ `{methodology_hash}`  ")
    lines.append(f"_Vulnerability model:_ run `{bundle['run_id'][:8]}…` AUC = {bundle['auc_roc']:.3f}  ")
    lines.append(f"_Generated:_ {datetime.now(timezone.utc).isoformat()}\n")

    lines.append("## Portfolio totals\n")
    lines.append(f"- **Structures scored:** {n_structures:,}")
    lines.append(f"- **Total expected annual loss:** ${total_eal:,.0f}")
    lines.append(f"- **Mean EAL / structure:** ${mean_eal:,.2f}")
    lines.append(f"- **Median EAL / structure:** ${median_eal:,.2f}\n")

    lines.append("## EAL distribution\n")
    lines.append("| Bucket | n | share | total EAL in bucket |")
    lines.append("|--------|--:|------:|--------------------:|")
    for _, r in hist.iterrows():
        lines.append(
            f"| {r['bucket']} | {r['n']:,} | {r['share']*100:.1f}% | ${r['bucket_total_eal']:,.0f} |"
        )
    lines.append("")

    lines.append("## EAL by occupancy class (first three NSI occtype chars)\n")
    lines.append("| Class | n | total EAL | mean EAL | share | total exposure |")
    lines.append("|-------|--:|----------:|---------:|------:|---------------:|")
    for _, r in by_occ.iterrows():
        lines.append(
            f"| {r['occ_group']} | {r['n']:,} | ${r['total_eal']:,.0f} | ${r['mean_eal']:,.2f} "
            f"| {r['share_of_total_eal']*100:.1f}% | ${r['total_exposure']:,.0f} |"
        )
    lines.append("")

    lines.append("## Top 20 areas by aggregate EAL\n")
    lines.append("_Aggregated by census tract; ZIP attached via Nominatim reverse-geocoding "
                 "of the tract centroid (see limitations)._\n")
    lines.append("| Rank | Tract FIPS | ZIP | n_structures | Total EAL | Mean EAL |")
    lines.append("|----:|-----------|----:|------------:|----------:|---------:|")
    for i, (_, r) in enumerate(top_tracts.iterrows(), 1):
        lines.append(
            f"| {i} | `{r['tract_fips']}` | {r.get('zip_code') or '—'} "
            f"| {r['n_structures']:,} | ${r['total_eal']:,.0f} | ${r['mean_eal']:,.2f} |"
        )
    lines.append("")

    lines.append("## Loss exceedance probability (OEP curve)\n")
    lines.append("| Return period (yr) | Annual freq. of exceedance | Loss amount |")
    lines.append("|------------------:|---------------------------:|------------:|")
    for _, r in standard_ep.iterrows():
        lines.append(
            f"| {int(r['return_period_years'])} | {r['annual_freq_exceed']:.4f} "
            f"| ${r['loss_amount']:,.0f} |"
        )
    lines.append("")
    lines.append(
        "_The OEP curve gives the expected annual frequency of ANY single-property "
        "loss exceeding the listed amount. Return period = 1 / frequency. Built on "
        "the Bernoulli-independence assumption — see limitations._\n"
    )

    lines.append("## Documented limitations\n")
    for lim in METADATA.limitations:
        sev = lim.severity.upper()
        mit = f" *Mitigation:* {lim.mitigation}" if lim.mitigation else ""
        lines.append(f"- **[{sev}]** {lim.description}{mit}\n")
    lines.append(
        "\n_For full methodology, references, and parameter justifications see "
        "`methodology.md` in this folder._\n"
    )
    return "\n".join(lines)


# ─── Driver ──────────────────────────────────────────────────────────────────


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()

    bundle = load_model()

    print("Pulling NSI structures with features ...")
    df, queries = asyncio.run(pull_structures())
    print(f"  {len(df)} structures with complete features + val_struct>0")

    print("Scoring P(destroyed | features) ...")
    df["p_destroyed"] = score(df, bundle)
    df["lambda_destroy"] = df["burn_probability"] * df["p_destroyed"]
    df["expected_annual_loss"] = df["lambda_destroy"] * df["val_struct"]

    print("Uploading expected_annual_loss column to Postgres ...")
    q = upload_eal(df)
    queries.append(q)
    print(f"  ALTER+UPDATE complete: {q.row_count} rows in {q.duration_ms/1000:.1f}s")

    # Aggregations.
    total_eal = float(df["expected_annual_loss"].sum())
    mean_eal = float(df["expected_annual_loss"].mean())
    median_eal = float(df["expected_annual_loss"].median())
    print(f"  portfolio total EAL = ${total_eal:,.0f}  "
          f"mean = ${mean_eal:.2f}  median = ${median_eal:.2f}")

    print("Aggregating by occupancy class ...")
    by_occ = aggregate_by_occtype(df)
    by_occ.to_csv(REPORT_DIR / "eal_by_occtype.csv", index=False)

    print("Aggregating by census tract ...")
    by_tract = aggregate_by_tract(df)
    by_tract.to_csv(REPORT_DIR / "eal_by_tract.csv", index=False)

    print("Reverse-geocoding top-20 tract centroids → ZIP (Nominatim, 1 req/s) ...")
    top_tracts = attach_top_tract_zips(by_tract, n=20)
    top_tracts.to_csv(REPORT_DIR / "top_20_tracts.csv", index=False)

    print("Building EAL distribution histogram ...")
    hist = eal_histogram(df)
    hist.to_csv(REPORT_DIR / "eal_distribution.csv", index=False)

    print("Selecting top 100 structures by EAL ...")
    top100 = top_n_by_eal(df, 100)
    top100.to_csv(REPORT_DIR / "top_100_eal.csv", index=False)

    print("Building OEP curve ...")
    full_ep, standard_ep = ep_curve(df)
    full_ep.to_csv(REPORT_DIR / "ep_curve.csv", index=False)
    standard_ep.to_csv(REPORT_DIR / "ep_curve_standard.csv", index=False)
    print(f"  standard return-period losses: "
          + ", ".join(f"{int(r.return_period_years)}yr=${r.loss_amount:,.0f}"
                       for r in standard_ep.itertuples(index=False)))

    # Portfolio JSON.
    portfolio = {
        "run_id": run_id,
        "generated_at": started,
        "vulnerability_model_run_id": bundle["run_id"],
        "vulnerability_model_methodology_hash": bundle["methodology_hash"],
        "n_structures": int(len(df)),
        "total_eal": total_eal,
        "mean_eal": mean_eal,
        "median_eal": median_eal,
        "p5_eal": float(df["expected_annual_loss"].quantile(0.05)),
        "p95_eal": float(df["expected_annual_loss"].quantile(0.95)),
        "max_eal": float(df["expected_annual_loss"].max()),
        "total_exposure": float(df["val_struct"].sum()),
        "implied_portfolio_burn_freq_per_year": float(df["lambda_destroy"].sum()),
        "distribution": hist.to_dict(orient="records"),
        "by_occtype": by_occ.to_dict(orient="records"),
        "top_20_tracts": top_tracts.to_dict(orient="records"),
        "standard_ep_curve": standard_ep.to_dict(orient="records"),
    }
    (REPORT_DIR / "portfolio_eal.json").write_text(json.dumps(portfolio, indent=2, default=str))

    # Methodology doc (hash-stable; validation summary attached).
    METADATA.validation_report_path = "summary.md"
    METADATA.validation_summary = {
        "n_structures": int(len(df)),
        "total_eal_usd": round(total_eal, 0),
        "mean_eal_usd": round(mean_eal, 2),
        "vulnerability_auc": round(bundle["auc_roc"], 4),
        "vulnerability_methodology_hash": bundle["methodology_hash"],
    }
    doc = generate_methodology(METADATA)
    (REPORT_DIR / "methodology.md").write_text(doc.markdown)

    summary_md = render_summary_md(
        bundle=bundle,
        n_structures=len(df),
        total_eal=total_eal,
        mean_eal=mean_eal,
        median_eal=median_eal,
        top_tracts=top_tracts,
        by_occ=by_occ,
        hist=hist,
        standard_ep=standard_ep,
        methodology_hash=doc.version_hash,
        run_id=run_id,
    )
    (REPORT_DIR / "summary.md").write_text(summary_md)

    # Audit.
    audit = AuditLogger(AUDIT_DIR / "wildfire_loss.jsonl")
    record = AuditRecord(
        execution_id=run_id,
        timestamp=started,
        module_name="wildfire_loss",
        module_version=METADATA.version,
        methodology_doc_version=doc.version_hash,
        inputs={
            "vulnerability_model_run_id": bundle["run_id"],
            "vulnerability_methodology_hash": bundle["methodology_hash"],
            "predictors": bundle["predictors"],
            "coefficients": bundle["coefficients"],
            "return_periods_yr": STANDARD_RETURN_PERIODS,
        },
        data_layers=["wildfire_nsi_structures"],
        queries=queries,
        scored_output={
            "n_structures": int(len(df)),
            "total_eal": total_eal,
            "mean_eal": mean_eal,
            "median_eal": median_eal,
            "ep_curve": standard_ep.to_dict(orient="records"),
        },
        duration_ms=(time.perf_counter() - t0) * 1000.0,
        raw_output_excerpt={
            "by_occtype_top": by_occ.head(3).to_dict(orient="records"),
            "top_tracts_top": top_tracts.head(3)[
                ["tract_fips", "zip_code", "total_eal"]
            ].to_dict(orient="records"),
        },
    )
    audit.log(record)
    (AUDIT_DIR / "wildfire_loss_cert.md").write_text(audit.certificate(record))
    print(f"  audit log + certificate written under {AUDIT_DIR}")

    # Console summary.
    print()
    print("──────── loss summary ────────")
    print(f"  structures               = {len(df):,}")
    print(f"  total EAL                = ${total_eal:,.0f}")
    print(f"  mean EAL                 = ${mean_eal:,.2f}")
    print(f"  median EAL               = ${median_eal:,.2f}")
    print(f"  implied portfolio λ/yr   = {df['lambda_destroy'].sum():.2f} expected total losses")
    print(f"  EP curve (standard RPs):")
    for _, r in standard_ep.iterrows():
        print(f"    {int(r['return_period_years']):>4}-yr  λ={r['annual_freq_exceed']:.4f}  "
              f"loss=${r['loss_amount']:,.0f}")
    print(f"\n  reports written → {REPORT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
