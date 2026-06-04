"use client";

import { useState } from "react";
import { postTradeAreaScoreV2, type TradeAreaScoreV2 } from "../lib/api";

const TIER_CHIP: Record<string, string> = {
  HIGH: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  MODERATE: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  LOW: "bg-orange-500/15 text-orange-300 border-orange-500/30",
  INSUFFICIENT: "bg-red-500/15 text-red-300 border-red-500/30",
  NONE: "bg-zinc-700/40 text-zinc-300 border-zinc-700",
};
const chip = (t: string | null | undefined) => TIER_CHIP[(t ?? "NONE").toUpperCase()] ?? TIER_CHIP.NONE;

const CATEGORIES = ["coffee_shop", "pharmacy", "restaurant", "fast_food", "bank", "gym", "grocery", "urgent_care"];

/** Trade area score via POST /trade-area/score-v2, surfacing the suitability
 *  rating, the data-selection-engine confidence tier, which POI/daytime sources
 *  were used (PostGIS vs Overpass; LEHD vs proxy), and data gaps (AC16). */
export function TradeAreaV2Panel() {
  const [address, setAddress] = useState("");
  const [category, setCategory] = useState("coffee_shop");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TradeAreaScoreV2 | null>(null);

  async function run() {
    setLoading(true);
    setError(null);
    try {
      const m = address.trim().match(/^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$/);
      const loc = m
        ? { latitude: parseFloat(m[1]), longitude: parseFloat(m[2]) }
        : { address: address.trim() };
      setResult(await postTradeAreaScoreV2({ ...loc, business_category: category }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  const c = result?.confidence;
  const src = result?.data_sources_used;

  return (
    <div className="mt-6 rounded-lg border border-zinc-800 bg-zinc-900 p-5">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-emerald-300">
        Trade area score (v2)
      </p>
      <p className="mt-1 text-sm text-zinc-400">
        Wired through the data selection engine. Enter an address or{" "}
        <span className="text-zinc-300">lat, lng</span>. Full coverage in Dallas County;
        on-demand fallback elsewhere.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <input
          value={address}
          onChange={(e) => setAddress(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && run()}
          placeholder="32.78, -96.80  or  Dallas, TX"
          className="min-w-[16rem] flex-1 rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600"
        />
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100"
        >
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>{c.replace("_", " ")}</option>
          ))}
        </select>
        <button
          onClick={run}
          disabled={loading || !address.trim()}
          className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-emerald-500 disabled:opacity-50"
        >
          {loading ? "Scoring…" : "Score"}
        </button>
      </div>

      {error && (
        <p className="mt-3 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          {error}
        </p>
      )}

      {result && c && (
        <div className="mt-4 space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-2xl font-bold text-white">{result.suitability_score.toFixed(2)}</span>
            <span className="text-sm font-semibold text-zinc-200">{result.suitability_rating}</span>
            <span className={`rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${chip(c.tier)}`}>
              confidence {c.tier} · {(c.composite * 100).toFixed(0)}%
            </span>
            <span className="rounded-full border border-zinc-700 bg-zinc-800/60 px-2 py-0.5 text-[10px] text-zinc-400">
              {result.coverage}
            </span>
          </div>
          <p className="text-xs leading-relaxed text-zinc-400">{c.statement}</p>

          {/* Which data sources were actually used (the spec's headline distinctions) */}
          {src && (
            <div className="grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-4">
              {[
                ["POI source", src.poi_source],
                ["Daytime source", src.daytime_source],
                ["Population", src.population_source],
                ["Flood", src.flood_source],
              ].map(([label, val]) => (
                <div key={label} className="rounded-md border border-zinc-800 bg-zinc-950/60 p-2">
                  <p className="text-zinc-500">{label}</p>
                  <p className="text-zinc-200">{val ?? "—"}</p>
                </div>
              ))}
            </div>
          )}

          {c.gaps.length > 0 && (
            <div className="rounded-md border border-amber-500/20 bg-amber-500/5 p-3">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-amber-300">
                Data gaps ({c.gaps.length})
              </p>
              <ul className="mt-1 space-y-0.5 text-[11px] text-zinc-400">
                {c.gaps.map((g, i) => <li key={i}>• {g}</li>)}
              </ul>
            </div>
          )}

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
