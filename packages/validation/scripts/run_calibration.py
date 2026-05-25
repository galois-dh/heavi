"""Run calibration + methodology + audit for the site_suitability module.

Outputs:
  reports/site_suitability_calibration.json
  reports/site_suitability_calibration.md
  reports/site_suitability_methodology.md
  audit_logs/site_suitability.jsonl  (one record per case)
  audit_logs/sample_certificate.md   (cert for the first case)

Usage:
  python -m scripts.run_calibration
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from heavi_validation.audit import AuditLogger, run_with_audit  # noqa: E402
from heavi_validation.harness import run_calibration  # noqa: E402
from heavi_validation.methodology import generate_methodology  # noqa: E402
from heavi_validation.reports import render_calibration_markdown  # noqa: E402
from modules.site_suitability import (  # noqa: E402
    ALAMEDA_TEST_CASES,
    METADATA,
    SiteSuitabilityModule,
)

REPORTS_DIR = ROOT / "reports"
AUDIT_DIR = ROOT / "audit_logs"


async def _init_connection(conn: asyncpg.Connection) -> None:
    for typename in ("json", "jsonb"):
        await conn.set_type_codec(
            typename, encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
        )


async def main() -> int:
    load_dotenv(ROOT.parents[1] / ".env")
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 1

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    pool = await asyncpg.create_pool(
        db_url, min_size=1, max_size=4, ssl="require", init=_init_connection
    )

    module = SiteSuitabilityModule()

    # 1. Methodology doc (generated first so its hash can be linked into the cert).
    methodology = generate_methodology(METADATA)
    methodology_path = REPORTS_DIR / "site_suitability_methodology.md"
    methodology_path.write_text(methodology.markdown)
    print(f"methodology doc:  {methodology_path}  (hash {methodology.version_hash[:12]}…)")

    # 2. Calibration run against live DB.
    print(f"running calibration on {len(ALAMEDA_TEST_CASES)} cases…")
    report = await run_calibration(module, ALAMEDA_TEST_CASES, pool=pool)

    # Write methodology doc *again* with the calibration summary now attached
    # — the hash is stable because validation_summary is excluded from canonical
    # metadata (see methodology._canonical_metadata).
    METADATA.validation_report_path = "site_suitability_calibration.md"
    METADATA.validation_summary = report.summary
    methodology = generate_methodology(METADATA)
    methodology_path.write_text(methodology.markdown)

    # 3. Calibration report (json + md).
    json_path = REPORTS_DIR / "site_suitability_calibration.json"
    md_path = REPORTS_DIR / "site_suitability_calibration.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, default=str))
    md_path.write_text(render_calibration_markdown(report))
    print(f"calibration json: {json_path}")
    print(f"calibration md:   {md_path}")

    # 4. Audit trail — replay each case under the audit wrapper.
    audit_path = AUDIT_DIR / "site_suitability.jsonl"
    if audit_path.exists():
        audit_path.unlink()  # fresh log for the demo
    logger = AuditLogger(audit_path)

    sample_record = None
    for case in ALAMEDA_TEST_CASES:
        _, record = await run_with_audit(
            module,
            case.inputs,
            methodology_doc_version=methodology.version_hash,
            logger=logger,
            pool=pool,
        )
        if sample_record is None:
            sample_record = record

    cert_path = AUDIT_DIR / "sample_certificate.md"
    if sample_record is not None:
        cert_path.write_text(logger.certificate(sample_record))
    print(f"audit log:        {audit_path}  ({len(ALAMEDA_TEST_CASES)} records)")
    print(f"sample cert:      {cert_path}")

    # 5. Console summary.
    s = report.summary
    print()
    print("──────── calibration summary ────────")
    print(f" cases:         {s['n']}")
    print(f" in-range:      {s['in_range_count']}/{s['n']}  ({s['in_range_rate']*100:.1f}%)")
    print(f" MAE:           {s['mae']}  (95% CI {s['mae_ci95']})")
    print(f" RMSE:          {s['rmse']}")
    print(f" bias:          {s['bias']:+.2f}")
    print(f" max |error|:   {s['max_abs_error']}")
    print(f" latency p50/max: {s['latency_ms']['p50']} / {s['latency_ms']['max']} ms")
    print()
    print(f"{'ID':<4} {'scenario':<50} {'expect':>8} {'predict':>8} {'Δ':>7} {'status':>8}")
    for c in report.cases:
        status = "in-range" if c.in_range else "OUT"
        print(
            f"{c.case_id:<4} {c.name[:50]:<50} {c.expected_score:>8.1f} "
            f"{c.predicted_score:>8.1f} {c.error:>+7.2f} {status:>8}"
        )

    await pool.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
