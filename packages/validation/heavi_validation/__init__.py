"""Heavi validation framework.

Three module-agnostic building blocks:

  - harness.run_calibration  -> calibration reports for any Module
  - methodology.generate     -> audit-ready methodology docs with version hash
  - audit.AuditLogger        -> per-execution audit certificates from a traced run

The framework deliberately avoids assumptions about what a module *does*; a
module only needs to expose a ``Module`` protocol shape (name, version,
``execute(inputs, tracer) -> {"score": float, ...}``) to plug in.
"""

from .audit import AuditLogger, AuditRecord, run_with_audit
from .harness import (
    CalibrationReport,
    CaseResult,
    Module,
    TestCase,
    run_calibration,
)
from .methodology import (
    DataSource,
    Limitation,
    MethodologyDoc,
    ModuleMetadata,
    Parameter,
    Reference,
    generate_methodology,
)
from .tracing import AuditQuery, QueryTracer, TracedPool

__all__ = [
    "AuditLogger",
    "AuditQuery",
    "AuditRecord",
    "CalibrationReport",
    "CaseResult",
    "DataSource",
    "Limitation",
    "MethodologyDoc",
    "Module",
    "ModuleMetadata",
    "Parameter",
    "QueryTracer",
    "Reference",
    "TestCase",
    "TracedPool",
    "generate_methodology",
    "run_calibration",
    "run_with_audit",
]
