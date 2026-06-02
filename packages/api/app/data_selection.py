"""Data Selection Engine — Heavi Platform Build Spec Phase 3.

The orchestrator that turns (workflow_type, lat, lng) into a
DataSelectionResult: which sources were actually queried, which were selected
per criterion, the per-criterion + composite confidence, and the gaps.

Three layers:

  Step 1  resolve_sources           Query each unique source ONCE, cache result.
  Step 2  traverse_data_tree        Per criterion, pick best available
                                    (alternatives) or assemble components.
  Step 3  compute_composite_confidence   Weighted composite + exclusion penalty.

The result carries source_cache so Phase 4 (scoring) reuses the same data
without re-querying.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import asyncpg

from .data_repository_check import SourceResult, check_source_availability
from .methodology_repository import (
    CriterionSpec,
    get_all_source_ids_for_workflow,
    get_criteria_for_workflow,
)

# ─── Result types ──────────────────────────────────────────────────────────


@dataclass
class CriterionSelection:
    criterion_id:     str
    criterion_type:   str               # 'scored' | 'exclusion'
    relationship:     str               # 'alternative' | 'component' | 'empty'
    selected_sources: list[dict[str, Any]]
    confidence:       float              # 0.0 - 1.0
    confidence_tier:  str               # 'HIGH' | 'MODERATE' | 'LOW' | 'NONE'
    quality_note:     str
    sources_tried:    list[dict[str, Any]] = field(default_factory=list)
    missing_components: list[str] = field(default_factory=list)
    supplementary_sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion_id":          self.criterion_id,
            "criterion_type":        self.criterion_type,
            "relationship":          self.relationship,
            "selected_sources":      self.selected_sources,
            "confidence":            round(self.confidence, 4),
            "confidence_tier":       self.confidence_tier,
            "quality_note":          self.quality_note,
            "sources_tried":         self.sources_tried,
            "missing_components":    self.missing_components,
            "supplementary_sources": self.supplementary_sources,
        }


@dataclass
class DataSelectionResult:
    workflow_type:        str
    latitude:             float
    longitude:            float
    criteria:             list[CriterionSelection]
    composite_confidence: float
    confidence_tier:      str         # 'HIGH' | 'MODERATE' | 'LOW' | 'INSUFFICIENT'
    confidence_statement: str
    completeness:         str
    gaps:                 list[str]
    strongest_data:       list[str]
    weakest_data:         list[str]
    source_cache:         dict[str, SourceResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_type":        self.workflow_type,
            "latitude":             self.latitude,
            "longitude":            self.longitude,
            "composite_confidence": round(self.composite_confidence, 4),
            "confidence_tier":      self.confidence_tier,
            "confidence_statement": self.confidence_statement,
            "completeness":         self.completeness,
            "gaps":                 self.gaps,
            "strongest_data":       self.strongest_data,
            "weakest_data":         self.weakest_data,
            "criteria":             [c.to_dict() for c in self.criteria],
            "source_cache":         {k: v.to_dict() for k, v in self.source_cache.items()},
        }


# ─── Confidence tiering ────────────────────────────────────────────────────


def tier_from_confidence(confidence: float) -> str:
    """Per-criterion tier per provenance doc."""
    if confidence >= 0.85:
        return "HIGH"
    if confidence >= 0.65:
        return "MODERATE"
    if confidence >= 0.40:
        return "LOW"
    return "NONE"


def composite_tier(confidence: float) -> str:
    """Composite tier per provenance doc — bottom band is INSUFFICIENT, not NONE."""
    if confidence >= 0.85:
        return "HIGH"
    if confidence >= 0.65:
        return "MODERATE"
    if confidence >= 0.40:
        return "LOW"
    return "INSUFFICIENT"


# ─── Step 1 — source resolution ────────────────────────────────────────────


async def resolve_sources(
    pool: asyncpg.Pool,
    workflow_type: str,
    latitude: float,
    longitude: float,
) -> dict[str, SourceResult]:
    """Resolve every unique data source for this workflow at this location.

    Each source is queried ONCE. The result is a cache keyed by source_id,
    which downstream criteria reuse — this is the spec's "data source reuse
    rule" (e.g., usgs_3dep appears in solar_slope, solar_aspect, excl_steep
    but only one HTTP/SQL hit is paid)."""
    source_ids = await get_all_source_ids_for_workflow(pool, workflow_type)
    cache: dict[str, SourceResult] = {}
    for sid in sorted(source_ids):  # sorted for deterministic ordering
        cache[sid] = await check_source_availability(pool, sid, latitude, longitude)
    return cache


# ─── Step 2 — tree traversal ───────────────────────────────────────────────


def _traverse_alternatives(
    criterion: CriterionSpec, cache: dict[str, SourceResult],
) -> CriterionSelection:
    """Top-to-bottom: pick the first node whose source is available."""
    sources_tried: list[dict[str, Any]] = []
    for node in criterion.data_tree:
        if node.get("relationship") != "alternative":
            continue
        sid = node["source_id"]
        result = cache.get(sid)
        sources_tried.append({
            "source_id": sid,
            "quality":   node.get("quality"),
            "checked":   result is not None,
            "available": bool(result and result.available),
        })
        if result and result.available:
            conf = float(node.get("confidence_value") or 0.0)
            return CriterionSelection(
                criterion_id=criterion.criterion_id,
                criterion_type=criterion.criterion_type,
                relationship="alternative",
                selected_sources=[{
                    "source_id":  sid,
                    "quality":    node.get("quality"),
                    "provides":   node.get("provides"),
                    "provenance": node.get("provenance"),
                }],
                confidence=conf,
                confidence_tier=tier_from_confidence(conf),
                quality_note=(
                    f"Using {node.get('quality')} source ({sid}): "
                    f"{node.get('provides') or node.get('role') or '?'}"
                ),
                sources_tried=sources_tried,
            )
    return CriterionSelection(
        criterion_id=criterion.criterion_id,
        criterion_type=criterion.criterion_type,
        relationship="alternative",
        selected_sources=[],
        confidence=0.0,
        confidence_tier="NONE",
        quality_note=(
            f"No data available for {criterion.criterion_name}. "
            f"Tried: {', '.join(s['source_id'] for s in sources_tried) or '(none)'}"
        ),
        sources_tried=sources_tried,
    )


def _traverse_components(
    criterion: CriterionSpec, cache: dict[str, SourceResult],
) -> CriterionSelection:
    """All components needed. Confidence = min(available component confidences),
    further degraded by the worst missing_confidence among absent components."""
    sources_tried: list[dict[str, Any]] = []
    components_available: list[dict[str, Any]] = []
    components_missing: list[dict[str, Any]] = []
    supplementary_available: list[str] = []

    for node in criterion.data_tree:
        rel = node.get("relationship")
        sid = node["source_id"]
        result = cache.get(sid)
        avail = bool(result and result.available)
        sources_tried.append({
            "source_id":   sid,
            "quality":     node.get("quality"),
            "relationship": rel,
            "available":   avail,
        })
        if rel == "component":
            (components_available if avail else components_missing).append(node)
        elif rel == "supplementary" and avail:
            supplementary_available.append(sid)

    if not components_missing and components_available:
        confidence = min(
            float(n.get("confidence_value") or 0.0) for n in components_available
        )
        note = (
            f"All {len(components_available)} component source(s) available"
        )
    elif components_available:
        available_conf = min(
            float(n.get("confidence_value") or 0.0) for n in components_available
        )
        worst_missing = min(
            float(n.get("missing_confidence", 0.0) or 0.0) for n in components_missing
        )
        confidence = min(available_conf, worst_missing)
        missing_names = ", ".join(
            f"{n['source_id']} ({n.get('missing_impact','?')})"
            for n in components_missing
        )
        note = f"Partial data: missing {missing_names}"
    else:
        confidence = 0.0
        note = "No component data available"

    if supplementary_available:
        note = f"{note}. Supplementary data available: {', '.join(supplementary_available)}"

    return CriterionSelection(
        criterion_id=criterion.criterion_id,
        criterion_type=criterion.criterion_type,
        relationship="component",
        selected_sources=[
            {
                "source_id":  n["source_id"],
                "quality":    n.get("quality"),
                "role":       n.get("role"),
                "provenance": n.get("provenance"),
            }
            for n in components_available
        ],
        confidence=confidence,
        confidence_tier=tier_from_confidence(confidence),
        quality_note=note,
        sources_tried=sources_tried,
        missing_components=[n["source_id"] for n in components_missing],
        supplementary_sources=supplementary_available,
    )


def traverse_data_tree(
    criterion: CriterionSpec, source_cache: dict[str, SourceResult],
) -> CriterionSelection:
    """Dispatch on the criterion's tree relationship type."""
    rel = criterion.tree_relationship_type()
    if rel == "component":
        return _traverse_components(criterion, source_cache)
    if rel == "alternative":
        return _traverse_alternatives(criterion, source_cache)
    # Degenerate tree — nothing to select.
    return CriterionSelection(
        criterion_id=criterion.criterion_id,
        criterion_type=criterion.criterion_type,
        relationship="empty",
        selected_sources=[],
        confidence=0.0,
        confidence_tier="NONE",
        quality_note="data tree has no actionable nodes",
        sources_tried=[],
    )


# ─── Step 3 / 4 — composite confidence ────────────────────────────────────


def compute_composite_confidence(
    selections: list[CriterionSelection],
    specs: list[CriterionSpec],
) -> tuple[float, str, str]:
    """Weighted composite over scored criteria, minus exclusion penalty.

    composite = (Σ weight × confidence) / (Σ weight)
              × (1 − 0.3 × (exclusion_NONE_count / total_exclusions))
    """
    scored_num = 0.0
    scored_den = 0.0
    spec_by_id = {s.criterion_id: s for s in specs}
    for sel in selections:
        spec = spec_by_id.get(sel.criterion_id)
        if spec is None or spec.criterion_type != "scored":
            continue
        w = float(spec.weight_default or 0.0)
        scored_num += w * sel.confidence
        scored_den += w
    scored_confidence = (scored_num / scored_den) if scored_den > 0 else 0.0

    exclusion_sels = [
        sel for sel in selections
        if (spec := spec_by_id.get(sel.criterion_id)) is not None
        and spec.criterion_type == "exclusion"
    ]
    excl_none = sum(1 for s in exclusion_sels if s.confidence == 0.0)
    total_excl = len(exclusion_sels)
    penalty = (excl_none / total_excl) if total_excl > 0 else 0.0
    composite = scored_confidence * (1.0 - 0.3 * penalty)
    tier = composite_tier(composite)

    # Always identify non-authoritative selections, regardless of tier, so the
    # reader sees the degraded criteria even when the composite is HIGH.
    # The provenance composite math only penalises NONE-confidence exclusion
    # criteria, so a single proxy exclusion (e.g. SSURGO hydric for wetlands)
    # may not drop the tier — but the user still needs to know.
    non_auth_scored = [
        sel.criterion_id for sel in selections
        if (sp := spec_by_id.get(sel.criterion_id)) is not None
        and sp.criterion_type == "scored"
        and 0.0 < sel.confidence < 0.85
    ]
    non_auth_excl = [
        sel.criterion_id for sel in selections
        if (sp := spec_by_id.get(sel.criterion_id)) is not None
        and sp.criterion_type == "exclusion"
        and 0.0 < sel.confidence < 0.85
    ]

    if tier == "HIGH":
        if non_auth_scored or non_auth_excl:
            bits = []
            if non_auth_scored:
                bits.append(f"scored: {', '.join(non_auth_scored)}")
            if non_auth_excl:
                bits.append(f"exclusion (proxy): {', '.join(non_auth_excl)}")
            statement = (
                "This assessment uses authoritative data for the majority of "
                "criteria. Proxy or partial data was used for: "
                + "; ".join(bits)
                + ". Verify those before relying on the result."
            )
        else:
            statement = "This assessment is based on authoritative data for all major criteria."
    elif tier == "MODERATE":
        degraded = [
            s.criterion_id for s in selections
            if 0.0 < s.confidence < 0.85 and s.criterion_type == "scored"
        ]
        proxy_excl = [
            s.criterion_id for s in selections
            if 0.0 < s.confidence < 0.85 and s.criterion_type == "exclusion"
        ]
        bits: list[str] = []
        if degraded:
            bits.append(f"scored: {', '.join(degraded)}")
        if proxy_excl:
            bits.append(f"exclusion (proxy): {', '.join(proxy_excl)}")
        if excl_none:
            bits.append(f"exclusion (gap): {excl_none} criterion(s)")
        detail = "; ".join(bits) if bits else "see per-criterion detail"
        statement = (
            f"This assessment uses proxy or partial data for some criteria — "
            f"{detail}. Results are directionally reliable but should be verified."
        )
    elif tier == "LOW":
        gaps = [s.criterion_id for s in selections if s.confidence < 0.4]
        statement = (
            f"This assessment has significant data gaps affecting "
            f"{len(gaps)} criteria: {', '.join(gaps) or '(see per-criterion detail)'}."
            " Results should be treated as preliminary screening, not definitive."
        )
    else:
        gaps = [s.criterion_id for s in selections if s.confidence == 0.0]
        statement = (
            "Insufficient data available at this location to produce a reliable "
            f"assessment. Missing: {', '.join(gaps[:5]) or '(see per-criterion detail)'}."
        )
    return composite, tier, statement


# ─── Step 5 — public entry point ───────────────────────────────────────────


async def select_data(
    pool: asyncpg.Pool,
    workflow_type: str,
    latitude: float,
    longitude: float,
) -> DataSelectionResult:
    """The orchestrator. One source-resolution pass, one per-criterion
    traversal pass, one composite computation."""
    specs = await get_criteria_for_workflow(pool, workflow_type)
    source_cache = await resolve_sources(pool, workflow_type, latitude, longitude)

    selections = [traverse_data_tree(spec, source_cache) for spec in specs]

    composite, tier, statement = compute_composite_confidence(selections, specs)

    gaps = [
        f"{s.criterion_id}: {s.quality_note}"
        for s in selections if s.confidence == 0.0
    ]
    strongest = [
        f"{s.criterion_id} ({s.selected_sources[0]['quality']})"
        for s in selections
        if s.confidence >= 0.85 and s.selected_sources
    ]
    weakest = [
        f"{s.criterion_id} ({s.quality_note})"
        for s in selections
        if 0.0 < s.confidence < 0.65
    ]

    scored_total = sum(1 for s in selections if s.criterion_type == "scored")
    excl_total = sum(1 for s in selections if s.criterion_type == "exclusion")
    scored_avail = sum(
        1 for s in selections if s.criterion_type == "scored" and s.confidence > 0
    )
    excl_avail = sum(
        1 for s in selections if s.criterion_type == "exclusion" and s.confidence > 0
    )
    completeness = (
        f"{scored_avail} of {scored_total} scored criteria, "
        f"{excl_avail} of {excl_total} exclusion criteria"
    )

    return DataSelectionResult(
        workflow_type=workflow_type,
        latitude=latitude,
        longitude=longitude,
        criteria=selections,
        composite_confidence=composite,
        confidence_tier=tier,
        confidence_statement=statement,
        completeness=completeness,
        gaps=gaps,
        strongest_data=strongest,
        weakest_data=weakest,
        source_cache=source_cache,
    )
