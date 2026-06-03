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
    but only one HTTP/SQL hit is paid).

    Set HEAVI_SELECTION_TIMING=1 to print per-source probe wall time to
    stdout (diagnostic only — no impact when unset)."""
    import os, time  # local import keeps prod hot-path imports unchanged
    log_timing = os.getenv("HEAVI_SELECTION_TIMING") == "1"

    source_ids = await get_all_source_ids_for_workflow(pool, workflow_type)
    cache: dict[str, SourceResult] = {}
    timings: list[tuple[str, float]] = []

    for sid in sorted(source_ids):  # sorted for deterministic ordering
        t0 = time.perf_counter()
        cache[sid] = await check_source_availability(pool, sid, latitude, longitude)
        ms = (time.perf_counter() - t0) * 1000.0
        timings.append((sid, ms))
        if log_timing:
            print(f"  {sid}: {ms:.1f} ms", flush=True)

    if log_timing:
        total_ms = sum(ms for _, ms in timings)
        print(f"  --- top 5 slowest ---", flush=True)
        for sid, ms in sorted(timings, key=lambda x: -x[1])[:5]:
            share = (ms / total_ms) * 100.0 if total_ms else 0.0
            print(f"  {sid}: {ms:.1f} ms  ({share:.1f}% of probe wall)", flush=True)
        print(f"  --- sum of probe wall: {total_ms/1000.0:.2f} s "
              f"across {len(timings)} sources ---", flush=True)

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


# Per-exclusion-criterion remediation language — the exclusion_id is the lookup
# key, the value is the human-readable proxy advisory used in the statement when
# THIS exclusion is the dominant degradation. Adding new entries here is the
# only place to change wording for a specific source-fallback case.
_EXCLUSION_PROXY_GUIDANCE: dict[str, str] = {
    "excl_wetlands": (
        "Wetland exclusion screening used SSURGO hydric soils as proxy rather "
        "than NWI boundary data. Recommend field delineation before committing."
    ),
}


def compute_composite_confidence(
    selections: list[CriterionSelection],
    specs: list[CriterionSpec],
) -> tuple[float, str, str]:
    """Weighted composite over scored criteria, scaled by the WEAKEST exclusion.

    composite = scored_confidence × exclusion_factor
      where  scored_confidence    = (Σ weight × confidence) / Σ weight
             worst_excl           = min(confidence over exclusion criteria)
             exclusion_factor     = 0.5 + 0.5 × worst_excl

    Rationale: a single missed fatal-flaw check (e.g., wetlands via SSURGO
    proxy rather than NWI) materially weakens the entire assessment, because
    the cost of overlooking that flaw at site-commitment is asymmetric. The
    earlier formula (penalty only for NONE-confidence exclusions) treated a
    proxy and an authoritative source identically, which masked the gap. The
    revised mapping:

        worst exclusion 1.0 (authoritative) → factor 1.00 (no penalty)
        worst exclusion 0.7 (fallback)      → factor 0.85
        worst exclusion 0.4 (proxy)         → factor 0.70
        worst exclusion 0.0 (gap)           → factor 0.50

    See the provenance doc § "Step 4: Composite Confidence" (revised 2026-06-06)
    for the worked-out maths and tier mapping.
    """
    spec_by_id = {s.criterion_id: s for s in specs}

    # 1) Scored — weighted sum.
    scored_num = 0.0
    scored_den = 0.0
    for sel in selections:
        spec = spec_by_id.get(sel.criterion_id)
        if spec is None or spec.criterion_type != "scored":
            continue
        w = float(spec.weight_default or 0.0)
        scored_num += w * sel.confidence
        scored_den += w
    scored_confidence = (scored_num / scored_den) if scored_den > 0 else 0.0

    # 2) Exclusion — weakest-link factor.
    exclusion_sels = [
        sel for sel in selections
        if (sp := spec_by_id.get(sel.criterion_id)) is not None
        and sp.criterion_type == "exclusion"
    ]
    if exclusion_sels:
        worst_excl = min(s.confidence for s in exclusion_sels)
    else:
        worst_excl = 1.0  # no exclusions defined → no factor
    exclusion_factor = 0.5 + 0.5 * worst_excl

    composite = scored_confidence * exclusion_factor
    tier = composite_tier(composite)

    # 3) Identify non-authoritative selections for the statement.
    non_auth_scored = [
        sel.criterion_id for sel in selections
        if (sp := spec_by_id.get(sel.criterion_id)) is not None
        and sp.criterion_type == "scored"
        and 0.0 < sel.confidence < 0.85
    ]
    weak_excl_sels = [
        s for s in exclusion_sels if s.confidence < 1.0
    ]
    weak_excl_ids = [s.criterion_id for s in weak_excl_sels]
    none_excl_ids = [s.criterion_id for s in exclusion_sels if s.confidence == 0.0]

    # Source-specific remediation language for the worst exclusion driver.
    worst_excl_sel = min(weak_excl_sels, key=lambda s: s.confidence, default=None)
    worst_guidance = (
        _EXCLUSION_PROXY_GUIDANCE.get(worst_excl_sel.criterion_id)
        if worst_excl_sel else None
    )

    if tier == "HIGH":
        if non_auth_scored or weak_excl_ids:
            bits = []
            if non_auth_scored:
                bits.append(f"scored: {', '.join(non_auth_scored)}")
            if weak_excl_ids:
                bits.append(f"exclusion: {', '.join(weak_excl_ids)}")
            statement = (
                "This assessment uses authoritative data for the majority of "
                "criteria. Proxy or partial data was used for: "
                + "; ".join(bits)
                + ". Verify those before relying on the result."
            )
        else:
            statement = (
                "This assessment is based on authoritative data for all major criteria."
            )
    elif tier == "MODERATE":
        # Lead with the specific exclusion driver if we have remediation language.
        if worst_guidance:
            statement = (
                f"{worst_guidance} Composite confidence is MODERATE "
                f"(scored {scored_confidence:.2f} × exclusion factor "
                f"{exclusion_factor:.2f} = {composite:.2f})."
            )
        else:
            bits = []
            if non_auth_scored:
                bits.append(f"scored: {', '.join(non_auth_scored)}")
            if weak_excl_ids:
                bits.append(f"exclusion: {', '.join(weak_excl_ids)}")
            if none_excl_ids:
                bits.append(f"exclusion gaps: {', '.join(none_excl_ids)}")
            detail = "; ".join(bits) if bits else "see per-criterion detail"
            statement = (
                f"This assessment uses proxy or partial data for some criteria — "
                f"{detail}. Results are directionally reliable but should be "
                "verified for those gaps."
            )
    elif tier == "LOW":
        gaps = [s.criterion_id for s in selections if s.confidence < 0.4]
        lead = worst_guidance + " " if worst_guidance else ""
        statement = (
            f"{lead}This assessment has significant data gaps affecting "
            f"{len(gaps)} criteria: {', '.join(gaps) or '(see per-criterion detail)'}."
            " Results should be treated as preliminary screening, not definitive."
        )
    else:  # INSUFFICIENT
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
