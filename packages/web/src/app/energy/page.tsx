"use client";

import { type FormEvent, useCallback, useState } from "react";
import Link from "next/link";
import { TopNav } from "../../components/top-nav";
import { ConfidencePanel } from "../../components/confidence-panel";
import { postSolarScoreV2, type SolarScoreV2 } from "../../lib/api";

/**
 * Heavi Energy — site screening for renewable development.
 *
 * Workflow: enter a coordinate → POST /solar/score-v2 (the Phase 4 scoring
 * pipeline that consumes the data-selection-engine output) → render the
 * ConfidencePanel (Phase 5 component). Confidence tier + composite are
 * surfaced at the top of the result, methodology documentation is
 * accessible from the same panel — exactly the Phase 5 acceptance criteria.
 */
export default function EnergyProductPage() {
  const [latText, setLatText] = useState("35.35");
  const [lngText, setLngText] = useState("-119.05");
  const [result, setResult] = useState<SolarScoreV2 | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = useCallback(async (e: FormEvent) => {
    e.preventDefault();
    const lat = Number(latText);
    const lng = Number(lngText);
    if (Number.isNaN(lat) || Number.isNaN(lng)) {
      setError("Latitude and longitude must be numbers.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const r = await postSolarScoreV2({ latitude: lat, longitude: lng });
      setResult(r);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scoring failed");
    } finally {
      setLoading(false);
    }
  }, [latText, lngText]);

  return (
    <div className="flex h-full flex-col">
      <TopNav active="energy" />

      <main className="flex flex-1 flex-col overflow-y-auto px-6 py-8">
        <div className="mx-auto w-full max-w-4xl">
          {/* Product hero */}
          <div className="mb-8">
            <span className="inline-block rounded-full border border-amber-500/30 bg-amber-500/15 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-amber-300">
              Heavi Energy
            </span>
            <h1 className="mt-3 text-3xl font-bold text-white">
              Site screening for renewable development
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-zinc-400">
              For VP of Site Origination, Director of Development, GIS Analyst at
              renewable energy developers (solar, wind, battery storage, data centers).
              Calibrated against EIA Form 860 installations · validated in Kern County
              at 97.7%. Methodology documentation attached to every output.
            </p>
            <div className="mt-3 text-[11px] text-zinc-500">
              Workflows: solar suitability · environmental screening ·{" "}
              <Link href="/portfolio" className="hover:text-zinc-300">batch CSV upload →</Link>
            </div>
          </div>

          {/* Scoring form */}
          <form
            onSubmit={onSubmit}
            className="rounded-lg border border-zinc-800 bg-zinc-900 p-5"
          >
            <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
              Score a single site
            </p>
            <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-3">
              <div>
                <label className="block text-[10px] uppercase tracking-wider text-zinc-500">Latitude</label>
                <input
                  value={latText}
                  onChange={(e) => setLatText(e.target.value)}
                  className="mt-1 w-full rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:border-blue-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-[10px] uppercase tracking-wider text-zinc-500">Longitude</label>
                <input
                  value={lngText}
                  onChange={(e) => setLngText(e.target.value)}
                  className="mt-1 w-full rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:border-blue-500 focus:outline-none"
                />
              </div>
              <div className="flex items-end">
                <button
                  type="submit"
                  disabled={loading}
                  className="w-full rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-500 disabled:opacity-40"
                >
                  {loading ? "Scoring…" : "Score this site"}
                </button>
              </div>
            </div>
            <p className="mt-2 text-[11px] text-zinc-500">
              Calls POST /solar/score-v2 — 8 scored + 6 exclusion criteria from the methodology
              repository, each computed from the source the data-selection engine picked.
            </p>
          </form>

          {error && (
            <div className="mt-4 rounded-md border border-red-900/50 bg-red-950/40 px-4 py-2 text-xs text-red-300">
              {error}
            </div>
          )}

          {/* Results — confidence is first-class (Phase 5 acceptance criterion #3) */}
          {result && (
            <div className="mt-8">
              <p className="mb-3 text-[10px] uppercase tracking-wider text-zinc-500">
                Result · {result.query.latitude.toFixed(4)}, {result.query.longitude.toFixed(4)}
              </p>
              <ConfidencePanel result={result} />
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
