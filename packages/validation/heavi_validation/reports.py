"""Markdown formatters for calibration reports and audit certificates."""

from __future__ import annotations

from typing import Any

from .harness import CalibrationReport, CaseResult


def _pct(n: float, d: float) -> str:
    return f"{(n / d * 100):.1f}%" if d else "n/a"


def _status_emoji(in_range: bool) -> str:
    # Plain ASCII to honor "no emojis unless requested".
    return "PASS" if in_range else "FAIL"


def _case_table(cases: list[CaseResult]) -> str:
    head = (
        "| ID | Scenario | Expected | Predicted | Δ | Range | Status | Latency (ms) |\n"
        "|----|----------|---------:|----------:|--:|-------|--------|-------------:|\n"
    )
    rows = []
    for c in cases:
        rng = f"[{c.expected_range[0]:.0f}, {c.expected_range[1]:.0f}]"
        rows.append(
            f"| {c.case_id} | {c.name} | {c.expected_score:.1f} | {c.predicted_score:.1f} | "
            f"{c.error:+.1f} | {rng} | {_status_emoji(c.in_range)} | {c.latency_ms:.1f} |"
        )
    return head + "\n".join(rows)


def _factor_table(cases: list[CaseResult]) -> str:
    factor_names: list[str] = []
    for c in cases:
        for k in c.factors:
            if k not in factor_names:
                factor_names.append(k)
    if not factor_names:
        return ""
    header = "| ID | " + " | ".join(factor_names) + " | violations |\n"
    sep = "|----|" + "|".join(["---:"] * len(factor_names)) + "|------------|\n"
    rows = []
    for c in cases:
        vals = " | ".join(f"{c.factors.get(f, 0):.0f}" for f in factor_names)
        viol = "; ".join(c.factor_violations) if c.factor_violations else "—"
        rows.append(f"| {c.case_id} | {vals} | {viol} |")
    return header + sep + "\n".join(rows)


def _error_distribution(summary: dict[str, Any]) -> str:
    buckets = summary["error_buckets"]
    total = sum(buckets.values()) or 1
    lines = ["| Abs error band | Count | Share |", "|----------------|------:|------:|"]
    for label in ("0-5", "5-10", "10-20", "20-30", "30+"):
        n = buckets[label]
        lines.append(f"| {label} | {n} | {_pct(n, total)} |")
    return "\n".join(lines)


def render_calibration_markdown(report: CalibrationReport) -> str:
    s = report.summary
    lat = s["latency_ms"]
    parts: list[str] = []
    parts.append(f"# Calibration Report — `{report.module_name}` v{report.module_version}\n")
    parts.append(
        f"- **Run ID:** `{report.run_id}`\n"
        f"- **Started:** {report.started_at}\n"
        f"- **Finished:** {report.finished_at}\n"
        f"- **Total wall time:** {report.total_latency_ms / 1000:.2f} s\n"
        f"- **Cases:** {report.case_count}\n"
    )
    parts.append("\n## Summary\n")
    parts.append(
        f"- **In-range rate:** {s['in_range_count']}/{s['n']} "
        f"({_pct(s['in_range_count'], s['n'])})\n"
        f"- **MAE:** {s['mae']}  (95% CI: {s['mae_ci95'][0]} – {s['mae_ci95'][1]}, bootstrap n=2000)\n"
        f"- **RMSE:** {s['rmse']}\n"
        f"- **Bias (signed mean error):** {s['bias']:+.2f}  "
        f"(positive ⇒ module over-scores vs expectation)\n"
        f"- **Max |error|:** {s['max_abs_error']}\n"
    )
    parts.append("\n### Latency per case\n")
    parts.append(
        f"- min {lat['min']} ms · p50 {lat['p50']} ms · mean {lat['mean']} ms · max {lat['max']} ms\n"
    )
    parts.append("\n### Error distribution\n")
    parts.append(_error_distribution(s) + "\n")
    parts.append("\n## Per-case results\n")
    parts.append(_case_table(report.cases) + "\n")
    parts.append("\n## Per-factor breakdown\n")
    ft = _factor_table(report.cases)
    parts.append((ft or "_module did not report factors_") + "\n")
    parts.append("\n## Notes\n")
    parts.append(
        "- A case passes when the predicted composite score falls within the test "
        "case's accepted range. The expected midpoint is used for error metrics; the "
        "range is used for pass/fail.\n"
        "- The MAE confidence interval uses percentile bootstrap (n=2000, seed=42).\n"
        "- Latency includes the full module call (geocoding skipped — coordinates "
        "are supplied directly).\n"
    )
    return "".join(parts)
