"use client";

import { useState } from "react";
import { postHazardScoreV2, type HazardScoreV2 } from "../lib/api";

const TIER_CHIP: Record<string, string> = {
  HIGH: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  MODERATE: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  LOW: "bg-orange-500/15 text-orange-300 border-orange-500/30",
  INSUFFICIENT: "bg-red-500/15 text-red-300 border-red-500/30",
  NONE: "bg-zinc-700/40 text-zinc-300 border-zinc-700",
};

function chip(tier: string | null | undefined) {
  return TIER_CHIP[(tier ?? "NONE").toUpperCase()] ?? TIER_CHIP.NONE;
}

function usd(v: number | null | undefined) {
  return v == null ? "—" : `$${Math.round(v).toLocaleString("en-US")}/yr`;
}

/** Combined wildfire + flood assessment via POST /hazard/score-v2, surfacing
 *  per-peril risk tiers, the data-selection-engine confidence tier, data gaps,
 *  and per-criterion quality (AC15). */
export function HazardV2Panel() {
  const [address, setAddress] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<HazardScoreV2 | null>(null);

  async function run() {
    setLoading(true);
    setError(null);
    try {
      // Accept "lat, lng" or a street address.
      const m = address.trim().match(/^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$/);
      const body = m
        ? { latitude: parseFloat(m[1]), longitude: parseFloat(m[2]) }
        : { address: address.trim() };
      setResult(await postHazardScoreV2(body));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  const c = result?.confidence;

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-5">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-rose-300">
        Combined hazard assessment (v2)
      </p>
      <p className="mt-1 text-sm text-zinc-400">
        Wildfire + flood in one call, wired through the data selection engine. Enter an
        address or <span className="text-zinc-300">lat, lng</span>.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <input
          value={address}
          onChange={(e) => setAddress(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && run()}
          placeholder="38.4405, -122.7144  or  123 Main St, Santa Rosa CA"
          className="min-w-[20rem] flex-1 rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600"
        />
        <button
          onClick={run}
          disabled={loading || !address.trim()}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-500 disabled:opacity-50"
        >
          {loading ? "Assessing…" : "Assess"}
        </button>
      </div>

      {error && (
        <p className="mt-3 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          {error}
        </p>
      )}

      {result && c && (
        <div className="mt-4 space-y-3">
          {/* Combined confidence tier — first-class, at the top */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] uppercase tracking-wider text-zinc-500">
              Combined confidence
            </span>
            <span className={`rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${chip(c.tier)}`}>
              {c.tier} · {(c.composite * 100).toFixed(0)}%
            </span>
          </div>
          <p className="text-xs leading-relaxed text-zinc-400">{c.statement}</p>

          {/* Per-peril cards */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="rounded-md border border-zinc-800 bg-zinc-950/60 p-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-white">Wildfire</span>
                <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${chip(result.wildfire.risk_tier)}`}>
                  {result.wildfire.available ? result.wildfire.risk_tier : "NO DATA"}
                </span>
              </div>
              <p className="mt-1 text-lg font-bold text-zinc-100">{usd(result.wildfire.annual_risk_usd)}</p>
              {result.wildfire.damage_probability != null && (
                <p className="text-[11px] text-zinc-500">
                  damage probability {(result.wildfire.damage_probability * 100).toFixed(0)}%
                </p>
              )}
            </div>
            <div className="rounded-md border border-zinc-800 bg-zinc-950/60 p-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-white">Flood</span>
                <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${chip(result.flood.risk_tier)}`}>
                  {result.flood.risk_tier ?? "—"}
                </span>
              </div>
              <p className="mt-1 text-lg font-bold text-zinc-100">{usd(result.flood.annual_risk_usd)}</p>
              <p className="text-[11px] text-zinc-500">
                FEMA zone {result.flood.flood_zone ?? "X/unmapped"}
                {result.flood.depth_ft != null && ` · depth ${result.flood.depth_ft} ft`}
              </p>
            </div>
          </div>

          {/* Data gaps — first-class */}
          {c.gaps.length > 0 && (
            <div className="rounded-md border border-amber-500/20 bg-amber-500/5 p-3">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-amber-300">
                Data gaps ({c.gaps.length})
              </p>
              <ul className="mt-1 space-y-0.5 text-[11px] text-zinc-400">
                {c.gaps.map((g, i) => (
                  <li key={i}>• {g}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Per-criterion quality */}
          <details className="rounded-md border border-zinc-800 bg-zinc-950/40 p-3">
            <summary className="cursor-pointer text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
              Per-criterion quality ({Object.keys(c.per_criterion).length})
            </summary>
            <div className="mt-2 space-y-1">
              {Object.entries(c.per_criterion).map(([id, q]) => (
                <div key={id} className="flex items-center justify-between gap-2 text-[11px]">
                  <span className="text-zinc-300">{id}</span>
                  <span className="flex items-center gap-2">
                    <span className="text-zinc-500">{q.selected_source ?? "—"}</span>
                    <span className={`rounded border px-1.5 py-0.5 ${chip(q.tier)}`}>{q.tier}</span>
                  </span>
                </div>
              ))}
            </div>
          </details>
        </div>
      )}
    </div>
  );
}
