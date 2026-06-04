"use client";

import { type FormEvent, useCallback, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { TopNav } from "../../components/top-nav";
import { HeaviMap } from "../../components/heavi-map";
import { EnergyDetail } from "../../components/map-detail-panels";
import { GeocodeInput } from "../../components/geocode-input";
import { postSolarScoreV2, resolveLocation, type GeocodeResult, type SolarScoreV2 } from "../../lib/api";
import { ENERGY_CONSTRAINTS, fc, solarFeature } from "../../lib/map-features";

/**
 * Heavi Energy — map-first site screening (Map Interface Spec, Step 6).
 *
 * Left sidebar: input form (single site or CSV of candidate parcels) + the
 * detail panel that slides in on marker click. Map: scored parcels color-coded
 * by suitability, with toggleable constraint overlays.
 */
export default function EnergyProductPage() {
  const [query, setQuery] = useState("35.35, -119.05");
  const [resolved, setResolved] = useState<GeocodeResult | null>(null);
  const [results, setResults] = useState<Record<string, SolarScoreV2>>({});
  const [order, setOrder] = useState<string[]>([]);
  const [selectedFid, setSelectedFid] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const counter = useRef(0);

  const addResult = useCallback((r: SolarScoreV2) => {
    const fid = `s${counter.current++}`;
    setResults((prev) => ({ ...prev, [fid]: r }));
    setOrder((prev) => [...prev, fid]);
    setSelectedFid(fid);
    return fid;
  }, []);

  const scoreOne = useCallback(async (lat: number, lng: number) => {
    const r = await postSolarScoreV2({ latitude: lat, longitude: lng });
    addResult(r);
  }, [addResult]);

  const onSubmit = useCallback(async (e?: FormEvent) => {
    e?.preventDefault();
    if (!query.trim()) return;
    setLoading(true); setError(null);
    try {
      const g = await resolveLocation(query);
      setResolved(g);
      await scoreOne(g.latitude, g.longitude);
    } catch (err) {
      setResolved(null);
      setError(err instanceof Error ? err.message : "Scoring failed");
    } finally { setLoading(false); }
  }, [query, scoreOne]);

  const onCsv = useCallback(async (file: File) => {
    setLoading(true); setError(null);
    try {
      const text = await file.text();
      const coords: [number, number][] = [];
      for (const line of text.split(/\r?\n/)) {
        const m = line.match(/(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)/);
        if (m) {
          const lat = parseFloat(m[1]), lng = parseFloat(m[2]);
          if (Math.abs(lat) <= 90 && Math.abs(lng) <= 180) coords.push([lat, lng]);
        }
      }
      if (!coords.length) { setError("No 'lat,lng' rows found in CSV."); return; }
      // Score sequentially (each site is its own scoring call).
      for (const [lat, lng] of coords.slice(0, 25)) {
        try { await scoreOne(lat, lng); } catch { /* skip a failed row */ }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "CSV scoring failed");
    } finally { setLoading(false); }
  }, [scoreOne]);

  const features = useMemo(
    () => fc(order.map((fid) => solarFeature(fid, results[fid]))),
    [order, results],
  );
  const selected = selectedFid ? results[selectedFid] : null;

  return (
    <div className="flex h-full flex-col">
      <TopNav active="energy" />
      <div className="flex flex-1 overflow-hidden">
        {/* Left sidebar */}
        <aside className="flex w-[360px] shrink-0 flex-col overflow-y-auto border-r border-zinc-800 bg-zinc-950">
          <div className="border-b border-zinc-800 p-4">
            <span className="inline-block rounded-full border border-amber-500/30 bg-amber-500/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-amber-300">
              Heavi Energy
            </span>
            <h1 className="mt-2 text-lg font-bold text-white">Solar site screening</h1>
            <p className="mt-1 text-[11px] leading-relaxed text-zinc-400">
              Score parcels on suitability · view results on the map · toggle constraint layers.
            </p>
          </div>

          <form onSubmit={onSubmit} className="space-y-3 border-b border-zinc-800 p-4">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Score a site</p>
            <GeocodeInput value={query} onChange={setQuery} onEnter={() => onSubmit()} resolved={resolved} error={error} />
            <button type="submit" disabled={loading}
              className="w-full rounded-md bg-blue-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-blue-500 disabled:opacity-40">
              {loading ? "Scoring…" : "Score this site"}
            </button>
            <label className="block cursor-pointer rounded-md border border-dashed border-zinc-700 px-3 py-2 text-center text-[11px] text-zinc-400 hover:border-zinc-500">
              Upload CSV of parcels (lat,lng per row)
              <input type="file" accept=".csv,text/csv,text/plain" className="hidden"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) onCsv(f); e.target.value = ""; }} />
            </label>
          </form>

          {/* Detail panel — appears on marker selection */}
          <div className="flex-1 p-4">
            {selected ? (
              <EnergyDetail r={selected} />
            ) : (
              <p className="text-[11px] text-zinc-500">
                {order.length > 0 ? "Click a marker to inspect its assessment." : "Score a site to see it on the map."}
              </p>
            )}
            {order.length > 1 && (
              <p className="mt-3 text-[10px] text-zinc-600">{order.length} sites scored · <Link href="/portfolio" className="hover:text-zinc-400">portfolio →</Link></p>
            )}
          </div>
        </aside>

        {/* Map */}
        <div className="relative flex-1">
          <HeaviMap
            center={[-119.05, 35.35]}
            zoom={9}
            scoredFeatures={features}
            scoreColorScale="suitability"
            constraints={ENERGY_CONSTRAINTS}
            onFeatureClick={(f) => setSelectedFid((f.properties?.fid as string) ?? null)}
            selectedFid={selectedFid}
          />
        </div>
      </div>
    </div>
  );
}
