"""Audit trail generator.

Wraps a module execution, captures inputs / SQL / outputs / timing, and writes
the result to an append-only JSON-lines log. A per-execution markdown
certificate can be produced on demand for compliance review.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .harness import Module
from .tracing import AuditQuery, QueryTracer


@dataclass
class AuditRecord:
    execution_id: str
    timestamp: str
    module_name: str
    module_version: str
    methodology_doc_version: str
    inputs: dict[str, Any]
    data_layers: list[str]
    queries: list[AuditQuery]
    scored_output: dict[str, Any]
    duration_ms: float
    raw_output_excerpt: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["queries"] = [q.to_dict() if hasattr(q, "to_dict") else q for q in self.queries]
        return d


def _excerpt(raw: dict[str, Any], max_chars: int = 4000) -> dict[str, Any]:
    """Trim large nested arrays so the audit log stays scannable. Full
    detail is reconstructable from inputs + queries; this is just for the cert."""
    blob = json.dumps(raw, default=str)
    if len(blob) <= max_chars:
        return raw
    out: dict[str, Any] = {}
    for k, v in raw.items():
        if isinstance(v, list) and len(v) > 3:
            out[k] = v[:3] + [{"_truncated": len(v) - 3}]
        else:
            out[k] = v
    return out


class AuditLogger:
    """Append-only JSON-lines audit log."""

    def __init__(self, log_path: Path | str) -> None:
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, record: AuditRecord) -> None:
        with self.log_path.open("a") as f:
            f.write(json.dumps(record.to_dict(), default=str) + "\n")

    def read_all(self) -> list[dict[str, Any]]:
        if not self.log_path.exists():
            return []
        return [json.loads(line) for line in self.log_path.read_text().splitlines() if line]

    def certificate(self, record: AuditRecord) -> str:
        """Render a per-execution markdown certificate."""
        lines: list[str] = []
        lines.append(f"# Audit Certificate — `{record.module_name}` v{record.module_version}\n")
        lines.append(f"**Execution ID:** `{record.execution_id}`  ")
        lines.append(f"**Timestamp:** {record.timestamp}  ")
        lines.append(f"**Methodology doc version:** `{record.methodology_doc_version}`  ")
        lines.append(f"**Duration:** {record.duration_ms:.1f} ms  \n")

        lines.append("## Inputs\n```json")
        lines.append(json.dumps(record.inputs, indent=2, default=str))
        lines.append("```\n")

        lines.append("## Scored output\n```json")
        lines.append(json.dumps(record.scored_output, indent=2, default=str))
        lines.append("```\n")

        lines.append("## Data layers consulted\n")
        for layer in record.data_layers:
            lines.append(f"- `{layer}`")
        lines.append("")

        lines.append(f"## Queries executed ({len(record.queries)})\n")
        for i, q in enumerate(record.queries, 1):
            qd = q.to_dict() if hasattr(q, "to_dict") else q
            sql = qd["sql"].strip().replace("\n", " ")
            if len(sql) > 240:
                sql = sql[:240] + " …"
            lines.append(
                f"{i}. ({qd['duration_ms']:.1f} ms, {qd['row_count']} rows) "
                f"layers={qd.get('table_hits', [])}"
            )
            lines.append(f"   ```sql\n   {sql}\n   ```")
        lines.append("")

        lines.append("## Attestation\n")
        lines.append(
            "This certificate records the exact inputs, SQL executed, data layers consulted, "
            "and scored output for a single module execution. A compliance reviewer can "
            "re-run the recorded SQL against the same database snapshot to reproduce the "
            "raw inputs to the scoring function, then apply the methodology document "
            f"(`{record.methodology_doc_version}`) to reproduce the output deterministically."
        )
        return "\n".join(lines)


async def run_with_audit(
    module: Module,
    inputs: dict[str, Any],
    *,
    methodology_doc_version: str,
    logger: AuditLogger,
    pool: Any = None,
) -> tuple[dict[str, Any], AuditRecord]:
    """Execute a module under a tracer, append an audit record, and return both."""
    tracer = QueryTracer()
    execution_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()
    if pool is not None:
        raw = await module.execute(inputs, tracer=tracer, pool=pool)  # type: ignore[call-arg]
    else:
        raw = await module.execute(inputs, tracer=tracer)
    duration_ms = (time.perf_counter() - t0) * 1000.0

    scored = {
        "score": raw.get("score"),
        "factors": raw.get("factors", {}),
        "counts": raw.get("counts", {}),
    }

    record = AuditRecord(
        execution_id=execution_id,
        timestamp=started,
        module_name=module.name,
        module_version=module.version,
        methodology_doc_version=methodology_doc_version,
        inputs=inputs,
        data_layers=tracer.data_layers,
        queries=tracer.queries,
        scored_output=scored,
        duration_ms=duration_ms,
        raw_output_excerpt=_excerpt(raw),
    )
    logger.log(record)
    return raw, record
