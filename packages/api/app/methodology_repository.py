"""Methodology Repository — query API (Heavi Platform Build Spec Phase 2).

Three functions plus a small CriterionSpec dataclass:

  get_criteria_for_workflow(workflow_type) → list[CriterionSpec]
    Every criterion for the workflow with data tree and academic sources.

  get_all_source_ids_for_workflow(workflow_type) → set[str]
    Unique source_ids referenced across all data trees for the workflow.
    Used by Phase 3 to resolve every source once per request.

  get_methodology_doc(workflow_type) → dict
    Framework citations + per-criterion weights + academic sources, formatted
    for attachment to every scored output.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import asyncpg


@dataclass
class CriterionSpec:
    criterion_id:       str
    workflow_type:      str
    criterion_name:     str
    criterion_type:     str               # 'scored' | 'exclusion'
    weight_default:     float | None
    weight_min:         float | None
    weight_max:         float | None
    weight_rationale:   str | None
    exclusion_threshold: str | None
    exclusion_rationale: str | None
    data_tree:          list[dict[str, Any]]
    academic_sources:   list[dict[str, Any]]
    confidence_rules:   dict[str, Any] | None = None

    def alternatives(self) -> list[dict[str, Any]]:
        return [n for n in self.data_tree if n.get("relationship") == "alternative"]

    def components(self) -> list[dict[str, Any]]:
        return [n for n in self.data_tree if n.get("relationship") == "component"]

    def supplementary(self) -> list[dict[str, Any]]:
        return [n for n in self.data_tree if n.get("relationship") == "supplementary"]

    def tree_relationship_type(self) -> str:
        """The dominant relationship type of this criterion's tree.

        'alternative' if any alternative node exists (and no components);
        'component'   if any component node exists;
        'empty'       if the tree is degenerate (only supplementary or none).
        Used by the Phase 3 traversal to pick the correct algorithm.
        """
        if any(n.get("relationship") == "component" for n in self.data_tree):
            return "component"
        if any(n.get("relationship") == "alternative" for n in self.data_tree):
            return "alternative"
        return "empty"


def _row_to_spec(r: dict[str, Any]) -> CriterionSpec:
    return CriterionSpec(
        criterion_id        = r["criterion_id"],
        workflow_type       = r["workflow_type"],
        criterion_name      = r["criterion_name"],
        criterion_type      = r["criterion_type"],
        weight_default      = r.get("weight_default"),
        weight_min          = r.get("weight_min"),
        weight_max          = r.get("weight_max"),
        weight_rationale    = r.get("weight_rationale"),
        exclusion_threshold = r.get("exclusion_threshold"),
        exclusion_rationale = r.get("exclusion_rationale"),
        data_tree           = _ensure_list(r["data_tree"]),
        academic_sources    = _ensure_list(r["academic_sources"]),
        confidence_rules    = _ensure_dict(r.get("confidence_rules")),
    )


def _ensure_list(v: Any) -> list[Any]:
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:  # noqa: BLE001
            return []
    return list(v or [])


def _ensure_dict(v: Any) -> dict[str, Any] | None:
    if v is None:
        return None
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:  # noqa: BLE001
            return None
    return dict(v) if v else None


# ─── 1. get_criteria_for_workflow ──────────────────────────────────────────


async def get_criteria_for_workflow(
    pool: asyncpg.Pool, workflow_type: str
) -> list[CriterionSpec]:
    """Return every criterion (scored + exclusion) for the workflow, with the
    full data tree and academic sources attached. Stable ordering: scored
    first by weight desc, then exclusion alphabetical."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT criterion_id, workflow_type, criterion_name, criterion_type,
                   weight_default, weight_min, weight_max, weight_rationale,
                   exclusion_threshold, exclusion_rationale,
                   data_tree, academic_sources, confidence_rules
            FROM methodology_criteria
            WHERE workflow_type = $1
            ORDER BY
              CASE criterion_type WHEN 'scored' THEN 0 ELSE 1 END,
              COALESCE(-weight_default, 0),
              criterion_id
            """,
            workflow_type,
        )
    return [_row_to_spec(dict(r)) for r in rows]


# ─── 2. get_all_source_ids_for_workflow ────────────────────────────────────


async def get_all_source_ids_for_workflow(
    pool: asyncpg.Pool, workflow_type: str
) -> set[str]:
    """Return the deduplicated set of source_ids referenced anywhere in any
    data tree for this workflow. Phase 3 uses this to know which sources to
    resolve once at the start of each query."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT jsonb_array_elements(data_tree)->>'source_id' AS sid
            FROM methodology_criteria
            WHERE workflow_type = $1
            """,
            workflow_type,
        )
    return {r["sid"] for r in rows if r["sid"]}


# ─── 3. get_methodology_doc ────────────────────────────────────────────────


# Framework-level citations per workflow.
_FRAMEWORK_CITATIONS: dict[str, list[dict[str, Any]]] = {
    "solar_siting": [
        {"name": "Doorga et al. (2019)",
         "role": "GIS-MCDA framework (AHP + WLC)",
         "venue": "Renewable and Sustainable Energy Reviews 104:133-146"},
        {"name": "Hernandez et al. (2015)",
         "role": "exclusion criteria (PAD-US, NWI, NLCD, HIFLD, TIGER)",
         "venue": "PNAS 112:13579-13584"},
        {"name": "Al-Shammari et al. (2026)",
         "role": "CONUS national-scale validation",
         "venue": "Renewable Energy (in press)"},
        {"name": "Charabi & Gastli (2011)",
         "role": "fuzzy continuous scoring; aspect for fixed-tilt",
         "venue": "Renewable Energy 36(9):2554-2561"},
        {"name": "Ong et al. (2013)",
         "role": "land-use intensity factors (acres/MW)",
         "venue": "NREL/TP-6A20-56290"},
    ],
    "hazard_assessment": [
        {"name": "Finney et al. (2011)",
         "role": "FSim wildfire simulation framework",
         "venue": "Stochastic Environmental Research and Risk Assessment 25:973-1000"},
        {"name": "Syphard et al. (2012)",
         "role": "housing-arrangement wildfire exposure",
         "venue": "PLoS ONE 7(3):e33954"},
        {"name": "Kramer et al. (2018)",
         "role": "Coffey Park pattern — structure-to-structure cascades",
         "venue": "International Journal of Wildland Fire 27:329-341"},
        {"name": "Rollins (2009)",
         "role": "LANDFIRE fuel + canopy methodology",
         "venue": "International Journal of Wildland Fire 18:235-249"},
        {"name": "Scawthorn et al. (2006, I & II)",
         "role": "HAZUS flood loss methodology",
         "venue": "Natural Hazards Review 7(2):60-71 and 72-81"},
    ],
    "trade_area": [
        {"name": "Huff (1963, 1964)",
         "role": "gravity model for trade area delineation",
         "venue": "Land Economics 39(1):81-90 and Journal of Marketing 28(3):34-38"},
        {"name": "Suárez-Vega et al. (2015)",
         "role": "multi-criteria extension with competitive density",
         "venue": "Applied Geography 59:142-153"},
        {"name": "Liang et al. (2020)",
         "role": "modern calibration via mobile-phone data",
         "venue": "Transactions in GIS 24(3):680-701"},
        {"name": "Luo & Wang (2003)",
         "role": "two-step floating catchment area",
         "venue": "Environment and Planning B 30(6):865-884"},
    ],
}


async def get_methodology_doc(
    pool: asyncpg.Pool, workflow_type: str
) -> dict[str, Any]:
    """Return the formatted methodology documentation for this workflow.

    The result is what gets attached to every scored assessment: framework
    citations, all criteria with weights + rationale + data sources used, and
    the deduplicated academic source list (one entry per unique citation
    across all criteria)."""
    criteria = await get_criteria_for_workflow(pool, workflow_type)

    # Deduplicate academic citations across criteria — same paper often cited
    # by multiple criteria.
    seen: set[tuple[Any, ...]] = set()
    deduped: list[dict[str, Any]] = []
    for c in criteria:
        for a in c.academic_sources:
            key = (a.get("author"), a.get("year"), a.get("title"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(a)

    return {
        "workflow_type":         workflow_type,
        "framework_citations":   _FRAMEWORK_CITATIONS.get(workflow_type, []),
        "criteria_count":        len(criteria),
        "scored_count":          sum(1 for c in criteria if c.criterion_type == "scored"),
        "exclusion_count":       sum(1 for c in criteria if c.criterion_type == "exclusion"),
        "criteria": [
            {
                "criterion_id":       c.criterion_id,
                "criterion_name":     c.criterion_name,
                "criterion_type":     c.criterion_type,
                "weight_default":     c.weight_default,
                "weight_range":       (
                    [c.weight_min, c.weight_max] if c.weight_min is not None else None
                ),
                "weight_rationale":   c.weight_rationale,
                "exclusion_threshold": c.exclusion_threshold,
                "exclusion_rationale": c.exclusion_rationale,
                "data_sources":       [
                    {
                        "source_id":     n["source_id"],
                        "relationship":  n.get("relationship"),
                        "quality":       n.get("quality"),
                        "provides":      n.get("provides") or n.get("role"),
                    }
                    for n in c.data_tree
                ],
            }
            for c in criteria
        ],
        "academic_sources":      deduped,
    }
