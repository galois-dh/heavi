"""Methodology document generator.

Takes structured metadata about a module and emits an audit-ready markdown
document. The document includes a deterministic SHA-256 hash of the canonical
metadata so a published doc can be cryptographically tied to a specific module
version.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class DataSource:
    """A single data layer the module reads from."""

    name: str
    description: str
    provenance: str
    license: str | None = None
    url: str | None = None
    last_updated: str | None = None
    table_name: str | None = None


@dataclass
class Parameter:
    """A modeling parameter with a justification for its chosen value."""

    name: str
    value: Any
    justification: str
    unit: str | None = None


@dataclass
class Reference:
    """A peer-reviewed paper, framework, or regulatory standard."""

    citation: str
    url: str | None = None
    kind: str = "peer-reviewed"  # "peer-reviewed" | "framework" | "standard" | "report"


@dataclass
class Limitation:
    """A known limitation of the module."""

    description: str
    severity: str = "medium"  # "low" | "medium" | "high"
    mitigation: str | None = None


@dataclass
class ModuleMetadata:
    name: str
    version: str
    description: str
    methodology_summary: str
    data_sources: list[DataSource]
    methodology_steps: list[str]
    parameters: list[Parameter]
    references: list[Reference]
    limitations: list[Limitation]
    authors: list[str] = field(default_factory=list)
    validation_report_path: str | None = None
    validation_summary: dict[str, Any] | None = None


@dataclass
class MethodologyDoc:
    markdown: str
    version_hash: str
    generated_at: str


def _canonical_metadata(meta: ModuleMetadata) -> str:
    """Stable JSON for hashing — sorted keys, no whitespace variance."""
    raw = asdict(meta)
    # Exclude validation summary from the hash (it's run-dependent; the
    # methodology itself shouldn't change just because we re-ran calibration).
    raw.pop("validation_summary", None)
    raw.pop("validation_report_path", None)
    return json.dumps(raw, sort_keys=True, separators=(",", ":"), default=str)


def _hash(meta: ModuleMetadata) -> str:
    return hashlib.sha256(_canonical_metadata(meta).encode()).hexdigest()


def _render(meta: ModuleMetadata, version_hash: str, generated_at: str) -> str:
    lines: list[str] = []
    lines.append(f"# Methodology — `{meta.name}` v{meta.version}\n")
    lines.append(f"_{meta.description}_\n")
    lines.append("")
    lines.append("## Document identity\n")
    lines.append(f"- **Module:** `{meta.name}`")
    lines.append(f"- **Module version:** `{meta.version}`")
    lines.append(f"- **Methodology hash (sha256):** `{version_hash}`")
    lines.append(f"- **Generated:** {generated_at}")
    if meta.authors:
        lines.append(f"- **Authors:** {', '.join(meta.authors)}")
    lines.append("")
    lines.append(
        "> This hash is computed over the canonical metadata (name, version, "
        "data sources, methodology steps, parameters, references, limitations). "
        "Any change to inputs that drive the score regenerates the hash; an "
        "audit consumer can verify they're reading the doc matched to a "
        "specific module version.\n"
    )

    lines.append("## Summary\n")
    lines.append(meta.methodology_summary.strip() + "\n")

    lines.append("## Data sources & provenance\n")
    for ds in meta.data_sources:
        lines.append(f"### {ds.name}")
        lines.append(f"- **Description:** {ds.description}")
        lines.append(f"- **Provenance:** {ds.provenance}")
        if ds.license:
            lines.append(f"- **License:** {ds.license}")
        if ds.url:
            lines.append(f"- **URL:** {ds.url}")
        if ds.last_updated:
            lines.append(f"- **Last refreshed:** {ds.last_updated}")
        if ds.table_name:
            lines.append(f"- **Backing table:** `{ds.table_name}`")
        lines.append("")

    lines.append("## Methodology\n")
    for i, step in enumerate(meta.methodology_steps, 1):
        lines.append(f"{i}. {step}")
    lines.append("")

    lines.append("## Parameter selection\n")
    lines.append("| Parameter | Value | Justification |")
    lines.append("|-----------|-------|---------------|")
    for p in meta.parameters:
        value = f"{p.value} {p.unit}" if p.unit else str(p.value)
        lines.append(f"| `{p.name}` | {value} | {p.justification} |")
    lines.append("")

    lines.append("## Academic & regulatory basis\n")
    for ref in meta.references:
        cite = ref.citation
        if ref.url:
            cite = f"[{cite}]({ref.url})"
        lines.append(f"- _{ref.kind}_ — {cite}")
    lines.append("")

    lines.append("## Validation\n")
    if meta.validation_report_path:
        lines.append(
            f"Calibration evidence: [`{meta.validation_report_path}`]({meta.validation_report_path})\n"
        )
    if meta.validation_summary:
        s = meta.validation_summary
        lines.append("Most recent calibration summary:\n")
        lines.append(f"- Cases: {s.get('n')}")
        lines.append(f"- In-range rate: {s.get('in_range_rate')}")
        lines.append(f"- MAE: {s.get('mae')} (95% CI {s.get('mae_ci95')})")
        lines.append(f"- RMSE: {s.get('rmse')}")
        lines.append(f"- Bias: {s.get('bias')}")
        lines.append("")
    if not meta.validation_report_path and not meta.validation_summary:
        lines.append("_No calibration report linked to this revision._\n")

    lines.append("## Known limitations\n")
    for lim in meta.limitations:
        mit = f" — _mitigation:_ {lim.mitigation}" if lim.mitigation else ""
        lines.append(f"- **[{lim.severity}]** {lim.description}{mit}")
    lines.append("")

    lines.append("---\n")
    lines.append(
        "_This document is generated from structured metadata; do not edit "
        "by hand. Regenerate via `scripts/generate_methodology.py` when the "
        "module's data sources, parameters, references, or limitations change._"
    )
    return "\n".join(lines)


def generate_methodology(meta: ModuleMetadata) -> MethodologyDoc:
    version_hash = _hash(meta)
    generated_at = datetime.now(timezone.utc).isoformat()
    md = _render(meta, version_hash, generated_at)
    return MethodologyDoc(markdown=md, version_hash=version_hash, generated_at=generated_at)
