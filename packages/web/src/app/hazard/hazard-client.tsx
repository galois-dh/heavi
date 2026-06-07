"use client";

import { type FormEvent, useCallback, useMemo, useRef, useState } from "react";
import { TopNav } from "../../components/top-nav";
import { HeaviMap } from "../../components/heavi-map";
import { HazardDetail } from "../../components/map-detail-panels";
import { GeocodeInput } from "../../components/geocode-input";
import { downloadHazardPdf, postHazardScoreV2, resolveLocation, type GeocodeResult, type HazardScoreV2 } from "../../lib/api";
import { HAZARD_CONSTRAINTS, fc, hazardFeature } from "../../lib/map-features";

/**
 * Heavi Hazard — map-first wildfire + flood assessment (Map Interface Spec,
 * Step 7). Same layout as Energy: input sidebar + detail panel, map with
 * risk-tier color coding and toggleable FEMA flood-zone overlay.
 */
export default function HazardClient() {
  const [addr, setAddr] = useState("38.4405, -122.7144");
  const [resolved, setResolved] = useState<GeocodeResult | null>(null);
  const [results, setResults] = useState<Record<string, HazardScoreV2>>({});
  const [order, setOrder] = useState<string[]>([]);
  const [selectedFid, setSelectedFid] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pdfBusy, setPdfBusy] = useState(false);
  const counter = useRef(0);

  const addResult = useCallback((r: HazardScoreV2) => {
    const fid = `h${counter.current++}`;
    setResults((prev) => ({ ...prev, [fid]: r }));
    setOrder((prev) => [...prev, fid]);
    setSelectedFid(fid);
  }, []);

  const assess = useCallback(async (e?: FormEvent) => {
    e?.preventDefault();
    if (!addr.trim()) return;
    setLoading(true); setError(null);
    try {
      const g = await resolveLocation(addr);
      setResolved(g);
      addResult(await postHazardScoreV2({ latitude: g.latitude, longitude: g.longitude }));
    } catch (err) {
      setResolved(null);
      setError(err instanceof Error ? err.message : "Assessment failed");
    } finally { setLoading(false); }
  }, [addr, addResult]);

  const features = useMemo(() => fc(order.map((fid) => hazardFeature(fid, results[fid]))), [order, results]);
  const selected = selectedFid ? results[selectedFid] : null;

  return (
    <div className="flex h-full flex-col">
      <TopNav active="hazard" />
      <div className="flex flex-1 overflow-hidden">
        <aside className="flex w-[360px] shrink-0 flex-col overflow-y-auto border-r border-zinc-800 bg-zinc-950">
          <div className="border-b border-zinc-800 p-4">
            <span className="inline-block rounded-full border border-rose-500/30 bg-rose-500/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-rose-300">
              Heavi Hazard
            </span>
            <h1 className="mt-2 text-lg font-bold text-white">Wildfire + flood assessment</h1>
            <p className="mt-1 text-[11px] leading-relaxed text-zinc-400">
              Combined per-peril risk · color-coded by risk tier · toggle FEMA flood zones.
            </p>
          </div>

          <form onSubmit={assess} className="space-y-3 border-b border-zinc-800 p-4">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Assess a property</p>
            <GeocodeInput value={addr} onChange={setAddr} onEnter={() => assess()} resolved={resolved} error={error} />
            <button type="submit" disabled={loading}
              className="w-full rounded-md bg-blue-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-blue-500 disabled:opacity-40">
              {loading ? "Assessing…" : "Assess"}
            </button>
          </form>

          <div className="flex-1 p-4">
            {selected ? (
              <>
                <div className="mb-2 flex justify-end">
                  <button
                    onClick={async () => {
                      const q = selected.query as { latitude: number; longitude: number };
                      setPdfBusy(true);
                      try { await downloadHazardPdf(q.latitude, q.longitude, addr); }
                      catch (err) { setError(err instanceof Error ? err.message : "PDF export failed"); }
                      finally { setPdfBusy(false); }
                    }}
                    disabled={pdfBusy}
                    className="rounded-md bg-zinc-800 px-3 py-1.5 text-[11px] font-medium text-zinc-200 transition hover:bg-zinc-700 disabled:opacity-40">
                    {pdfBusy ? "Generating PDF…" : "Export PDF"}
                  </button>
                </div>
                <HazardDetail r={selected} />
              </>
            ) : (
              <p className="text-[11px] text-zinc-500">
                {order.length > 0 ? "Click a property marker to inspect its hazard assessment." : "Assess a property to see it on the map."}
              </p>
            )}
          </div>
        </aside>

        <div className="relative flex-1">
          <HeaviMap
            center={[-122.7144, 38.4405]}
            zoom={9}
            scoredFeatures={features}
            scoreColorScale="risk"
            constraints={HAZARD_CONSTRAINTS}
            onFeatureClick={(f) => setSelectedFid((f.properties?.fid as string) ?? null)}
            selectedFid={selectedFid}
          />
        </div>
      </div>
    </div>
  );
}
