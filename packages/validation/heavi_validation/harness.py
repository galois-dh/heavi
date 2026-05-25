"""Calibration harness.

Module-agnostic: any callable that conforms to the :class:`Module` protocol
(``name``, ``version``, ``async execute(inputs, tracer) -> {"score": float, ...}``)
can be calibrated against a list of :class:`TestCase` objects with known
expected outcomes.

The harness produces a :class:`CalibrationReport` containing per-case results,
aggregate error statistics, a bootstrap confidence interval on the mean
absolute error, and timing metrics.
"""

from __future__ import annotations

import math
import random
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from .tracing import QueryTracer


@runtime_checkable
class Module(Protocol):
    """Minimal interface a module must satisfy to be calibrated."""

    name: str
    version: str

    async def execute(
        self, inputs: dict[str, Any], tracer: QueryTracer | None = None
    ) -> dict[str, Any]:
        """Run the module. Returned dict must contain ``score`` (0–100)."""
        ...


@dataclass
class TestCase:
    """A single calibration scenario."""

    id: str
    name: str
    inputs: dict[str, Any]
    expected_score: float
    expected_range: tuple[float, float]
    justification: str
    expected_factors: dict[str, tuple[float, float]] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["expected_range"] = list(self.expected_range)
        d["expected_factors"] = {k: list(v) for k, v in self.expected_factors.items()}
        return d


@dataclass
class CaseResult:
    case_id: str
    name: str
    predicted_score: float
    expected_score: float
    expected_range: tuple[float, float]
    in_range: bool
    error: float
    abs_error: float
    factors: dict[str, float]
    factor_violations: list[str]
    latency_ms: float
    query_count: int
    queried_layers: list[str]
    raw_output: dict[str, Any]
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["expected_range"] = list(self.expected_range)
        return d


@dataclass
class CalibrationReport:
    run_id: str
    module_name: str
    module_version: str
    started_at: str
    finished_at: str
    total_latency_ms: float
    case_count: int
    summary: dict[str, Any]
    cases: list[CaseResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "module_name": self.module_name,
            "module_version": self.module_version,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_latency_ms": round(self.total_latency_ms, 2),
            "case_count": self.case_count,
            "summary": self.summary,
            "cases": [c.to_dict() for c in self.cases],
        }


def _bootstrap_ci(values: list[float], n_resamples: int = 2000, alpha: float = 0.05) -> tuple[float, float]:
    """Percentile-bootstrap CI for the mean. Deterministic seed for reproducibility."""
    if not values:
        return (0.0, 0.0)
    rng = random.Random(42)
    n = len(values)
    means = []
    for _ in range(n_resamples):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int((alpha / 2) * n_resamples)]
    hi = means[int((1 - alpha / 2) * n_resamples) - 1]
    return (lo, hi)


def _summarize(results: list[CaseResult]) -> dict[str, Any]:
    errors = [r.error for r in results]
    abs_errors = [r.abs_error for r in results]
    in_range = sum(1 for r in results if r.in_range)
    n = len(results)

    mae = sum(abs_errors) / n if n else 0.0
    rmse = math.sqrt(sum(e * e for e in errors) / n) if n else 0.0
    bias = sum(errors) / n if n else 0.0
    mae_lo, mae_hi = _bootstrap_ci(abs_errors)

    # Histogram of absolute errors in 10-point buckets.
    buckets = {"0-5": 0, "5-10": 0, "10-20": 0, "20-30": 0, "30+": 0}
    for e in abs_errors:
        if e < 5:
            buckets["0-5"] += 1
        elif e < 10:
            buckets["5-10"] += 1
        elif e < 20:
            buckets["10-20"] += 1
        elif e < 30:
            buckets["20-30"] += 1
        else:
            buckets["30+"] += 1

    latencies = [r.latency_ms for r in results]
    return {
        "n": n,
        "in_range_count": in_range,
        "in_range_rate": round(in_range / n, 3) if n else 0.0,
        "mae": round(mae, 2),
        "mae_ci95": [round(mae_lo, 2), round(mae_hi, 2)],
        "rmse": round(rmse, 2),
        "bias": round(bias, 2),
        "error_buckets": buckets,
        "max_abs_error": round(max(abs_errors), 2) if abs_errors else 0.0,
        "latency_ms": {
            "min": round(min(latencies), 2) if latencies else 0.0,
            "max": round(max(latencies), 2) if latencies else 0.0,
            "mean": round(sum(latencies) / n, 2) if n else 0.0,
            "p50": round(sorted(latencies)[n // 2], 2) if n else 0.0,
        },
    }


def _check_factors(
    expected: dict[str, tuple[float, float]], actual: dict[str, float]
) -> list[str]:
    violations = []
    for name, (lo, hi) in expected.items():
        v = actual.get(name)
        if v is None:
            violations.append(f"{name}: missing")
            continue
        if not (lo <= v <= hi):
            violations.append(f"{name}={v} outside [{lo}, {hi}]")
    return violations


async def run_calibration(
    module: Module,
    cases: list[TestCase],
    *,
    pool: Any = None,
) -> CalibrationReport:
    """Execute ``module`` against each test case and produce a CalibrationReport.

    If ``pool`` is provided it is forwarded to ``module.execute`` as an extra
    keyword (modules that need a DB pool should accept ``pool`` plus the
    tracer). Each execution gets a fresh :class:`QueryTracer` so per-case query
    counts and queried layers are recorded.
    """

    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    t_run = time.perf_counter()

    results: list[CaseResult] = []
    for case in cases:
        tracer = QueryTracer()
        t0 = time.perf_counter()
        if pool is not None:
            raw = await module.execute(case.inputs, tracer=tracer, pool=pool)  # type: ignore[call-arg]
        else:
            raw = await module.execute(case.inputs, tracer=tracer)
        latency_ms = (time.perf_counter() - t0) * 1000.0

        predicted = float(raw.get("score"))
        factors = raw.get("factors") or {}
        in_range = case.expected_range[0] <= predicted <= case.expected_range[1]
        error = predicted - case.expected_score
        violations = _check_factors(case.expected_factors, factors)

        results.append(
            CaseResult(
                case_id=case.id,
                name=case.name,
                predicted_score=predicted,
                expected_score=case.expected_score,
                expected_range=case.expected_range,
                in_range=in_range,
                error=round(error, 2),
                abs_error=round(abs(error), 2),
                factors={k: float(v) for k, v in factors.items()},
                factor_violations=violations,
                latency_ms=round(latency_ms, 2),
                query_count=len(tracer.queries),
                queried_layers=tracer.data_layers,
                raw_output=raw,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        )

    total_latency_ms = (time.perf_counter() - t_run) * 1000.0
    finished_at = datetime.now(timezone.utc).isoformat()

    return CalibrationReport(
        run_id=run_id,
        module_name=module.name,
        module_version=module.version,
        started_at=started_at,
        finished_at=finished_at,
        total_latency_ms=total_latency_ms,
        case_count=len(results),
        summary=_summarize(results),
        cases=results,
    )
