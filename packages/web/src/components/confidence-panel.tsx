"use client";

import { useState } from "react";
import type { SolarScoreV2 } from "../lib/api";

const TIER_STYLES: Record<string, { ring: string; chip: string; label: string }> = {
  HIGH: {
    ring: "ring-emerald-500/40", chip: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
    label: "HIGH",
  },
  MODERATE: {
    ring: "ring-amber-500/40", chip: "bg-amber-500/15 text-amber-300 border-amber-500/30",
    label: "MODERATE",
  },
  LOW: {
    ring: "ring-orange-500/40", chip: "bg-orange-500/15 text-orange-300 border-orange-500/30",
    label: "LOW",
  },
  INSUFFICIENT: {
    ring: "ring-red-500/40", chip: "bg-red-500/15 text-red-300 border-red-500/30",
    label: "INSUFFICIENT",
  },
  NONE: {
    ring: "ring-zinc-700", chip: "bg-zinc-700/40 text-zinc-300 border-zinc-700",
    label: "NONE",
  },
};

function tierStyle(tier: string) {
  return TIER_STYLES[tier] ?? TIER_STYLES.NONE;
}

/**
 * Phase 5 confidence + methodology display.
 *
 * Confidence is first-class output per the build spec — tier and composite
 * are surfaced at the TOP of the panel, not hidden in a collapsible section.
 * Gaps and per-criterion quality are rendered inline. Methodology
 * documentation (framework citations + academic sources) is accessible from
 * the same panel without a separate page visit.
 */
export function ConfidencePanel({ result }: { result: SolarScoreV2 }) {
  const [showMethodology, setShowMethodology] = useState(false);
  const t = tierStyle(result.confidence.tier);

  return (
    <div className="space-y-4">
      {/* Score + confidence (the two headline numbers, side by side) */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-5">
          <p className="text-[10px] uppercase tracking-wider text-zinc-500">Site score</p>
          <div className="mt-1 flex items-baseline gap-3">
            <p className="text-4xl font-bold tabular-nums text-white">
              {(result.score * 100).toFixed(0)}
            </p>
            <p className="text-sm text-zinc-500">/ 100</p>
            <span className={`ml-auto rounded-md border px-2.5 py-1 text-xs font-semibold ${
              result.rating === "Excluded" ? "border-red-500/30 bg-red-500/15 text-red-300"
              : result.rating === "High"   ? "border-emerald-500/30 bg-emerald-500/15 text-emerald-300"
              : result.rating === "Moderate" ? "border-amber-500/30 bg-amber-500/15 text-amber-300"
              : "border-orange-500/30 bg-orange-500/15 text-orange-300"
            }`}>{result.rating}</span>
          </div>
          {result.exclusions.length > 0 && (
            <p className="mt-2 text-xs text-red-300">
              Excluded by: {result.exclusions.join(", ")}
            </p>
          )}
        </div>

        <div className={`rounded-lg border border-zinc-800 bg-zinc-900 p-5 ring-1 ${t.ring}`}>
          <p className="text-[10px] uppercase tracking-wider text-zinc-500">Confidence</p>
          <div className="mt-1 flex items-baseline gap-3">
            <p className="text-4xl font-bold tabular-nums text-white">
              {(result.confidence.composite * 100).toFixed(0)}
            </p>
            <p className="text-sm text-zinc-500">/ 100</p>
            <span className={`ml-auto rounded-md border px-2.5 py-1 text-xs font-semibold ${t.chip}`}>
              {t.label}
            </span>
          </div>
          <p className="mt-2 text-[11px] text-zinc-400">{result.confidence.completeness}</p>
        </div>
      </div>

      {/* Confidence statement (first-class, not a footnote) */}
      <div className="rounded-md border border-zinc-800 bg-zinc-900/60 p-4 text-[13px] leading-relaxed text-zinc-200">
        {result.confidence.statement}
      </div>

      {/* Gaps prominent */}
      {result.confidence.gaps.length > 0 && (
        <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-4">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-amber-300">
            Data gaps — {result.confidence.gaps.length}
          </p>
          <ul className="mt-2 space-y-1 text-xs leading-relaxed text-zinc-300">
            {result.confidence.gaps.map((g, i) => <li key={i}>• {g}</li>)}
          </ul>
        </div>
      )}

      {/* Per-criterion table */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900">
        <div className="border-b border-zinc-800 px-4 py-2.5">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
            Per-criterion quality
          </p>
        </div>
        <div className="divide-y divide-zinc-800">
          {Object.entries(result.confidence.per_criterion).map(([cid, q]) => {
            const ts = tierStyle(q.tier);
            const cs = result.criteria_scores[cid];
            const es = result.exclusion_results[cid];
            const isScored = cs !== undefined;
            return (
              <div key={cid} className="grid grid-cols-12 items-center gap-2 px-4 py-2 text-xs">
                <span className="col-span-3 truncate font-mono text-zinc-300">{cid}</span>
                <span className={`col-span-2 rounded-md border px-2 py-0.5 text-center text-[10px] font-semibold ${ts.chip}`}>
                  {ts.label}
                </span>
                <span className="col-span-2 tabular-nums text-zinc-400">
                  conf {(q.confidence * 100).toFixed(0)}%
                </span>
                <span className="col-span-3 truncate text-zinc-500">
                  {q.selected_source ?? "—"}
                </span>
                <span className="col-span-2 text-right tabular-nums text-zinc-300">
                  {isScored && cs?.score !== null
                    ? `score ${(cs.score! * 100).toFixed(0)}`
                    : !isScored && es?.excluded === true
                      ? <span className="text-red-300">EXCLUDED</span>
                      : !isScored && es?.excluded === false
                        ? <span className="text-emerald-400">pass</span>
                        : "—"}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Strongest / weakest sources */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <div className="rounded-md border border-zinc-800 bg-zinc-900 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-emerald-300">Strongest data</p>
          <ul className="mt-1.5 space-y-1 text-[11px] text-zinc-300">
            {result.confidence.strongest_data.slice(0, 6).map((s, i) => <li key={i}>{s}</li>)}
            {result.confidence.strongest_data.length === 0 && (
              <li className="text-zinc-500">no criteria reached HIGH at this location</li>
            )}
          </ul>
        </div>
        <div className="rounded-md border border-zinc-800 bg-zinc-900 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-amber-300">Weakest data</p>
          <ul className="mt-1.5 space-y-1 text-[11px] text-zinc-300">
            {result.confidence.weakest_data.slice(0, 6).map((s, i) => <li key={i}>{s}</li>)}
            {result.confidence.weakest_data.length === 0 && (
              <li className="text-zinc-500">no proxy or partial data used</li>
            )}
          </ul>
        </div>
      </div>

      {/* Methodology toggle — accessible from every result */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900">
        <button
          onClick={() => setShowMethodology(!showMethodology)}
          className="flex w-full items-center justify-between px-4 py-3 text-left text-xs"
        >
          <span className="font-semibold text-zinc-200">
            Methodology · {result.methodology.criteria_count} criteria · {result.methodology.academic_sources.length} citations
          </span>
          <span className="text-zinc-500">{showMethodology ? "Hide" : "Show"} →</span>
        </button>
        {showMethodology && (
          <div className="border-t border-zinc-800 p-4 text-[11px] leading-relaxed text-zinc-300">
            <p className="font-semibold text-zinc-200">Framework</p>
            <ul className="mt-1 space-y-1">
              {result.methodology.framework_citations.map((f, i) => (
                <li key={i}>
                  <span className="text-zinc-100">{f.name}</span>
                  <span className="text-zinc-500"> · {f.role} · {f.venue}</span>
                </li>
              ))}
            </ul>

            <p className="mt-4 font-semibold text-zinc-200">Criteria + weights</p>
            <ul className="mt-1 space-y-1">
              {result.methodology.criteria
                .filter((c) => c.criterion_type === "scored")
                .map((c) => (
                  <li key={c.criterion_id} className="flex items-baseline justify-between">
                    <span>
                      <span className="font-mono text-zinc-100">{c.criterion_id}</span>
                      <span className="text-zinc-500"> — {c.criterion_name}</span>
                    </span>
                    <span className="tabular-nums text-zinc-400">
                      w {c.weight_default ?? "—"}
                    </span>
                  </li>
                ))}
            </ul>

            <p className="mt-4 font-semibold text-zinc-200">
              Exclusions ({result.methodology.exclusion_count})
            </p>
            <ul className="mt-1 space-y-1">
              {result.methodology.criteria
                .filter((c) => c.criterion_type === "exclusion")
                .map((c) => (
                  <li key={c.criterion_id}>
                    <span className="font-mono text-zinc-100">{c.criterion_id}</span>
                    <span className="text-zinc-500"> — {c.criterion_name} (threshold: {c.exclusion_threshold ?? "—"})</span>
                  </li>
                ))}
            </ul>

            <p className="mt-4 font-semibold text-zinc-200">
              Academic citations ({result.methodology.academic_sources.length})
            </p>
            <ul className="mt-1 space-y-1.5">
              {result.methodology.academic_sources.slice(0, 12).map((a, i) => (
                <li key={i}>
                  <span className="text-zinc-100">{a.author} ({a.year}).</span>{" "}
                  <span className="italic text-zinc-300">{a.title}.</span>
                  {a.journal && <span className="text-zinc-500"> {a.journal}{a.volume ? ` ${a.volume}` : ""}{a.pages ? `:${a.pages}` : ""}.</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
