"use client";

import { type FormEvent, useCallback, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { TopNav } from "../../components/top-nav";
import { HeaviMap } from "../../components/heavi-map";
import { EnergyDetail } from "../../components/map-detail-panels";
import { GeocodeInput } from "../../components/geocode-input";
import { BatchRankedList, type BatchResult } from "../../components/batch-ranked-list";
import { downloadSolarBatchPdf, downloadSolarPdf, postSolarScoreV2, resolveLocation, type GeocodeResult } from "../../lib/api";
import { parseLocationCsv } from "../../lib/csv-locations";
import { ENERGY_CONSTRAINTS, fc, solarFeature } from "../../lib/map-features";

/**
 * Heavi Energy — map-first site screening (Map + Month-1 Sprint F2).
 *
 * Single site (address/coords) or a CSV of candidate parcels scored as a batch
 * with a progress indicator, a ranked list in the sidebar, and bidirectional
 * map↔list selection.
 */
export default function EnergyClient({ batchLimit }: { batchLimit: number }) {
  const [query, setQuery] = useState("35.35, -119.05");
  const [resolved, setResolved] = useState<GeocodeResult | null>(null);
  const [results, setResults] = useState<Record<string, BatchResult>>({});
  const [order, setOrder] = useState<string[]>([]);
  const [selectedFid, setSelectedFid] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pdfBusy, setPdfBusy] = useState<"single" | "batch" | null>(null);
  const counter = useRef(0);

  const addResult = useCallback((r: BatchResult, name?: string, select = true) => {
    const fid = `s${counter.current++}`;
    setResults((prev) => ({ ...prev, [fid]: { ...r, name } }));
    setOrder((prev) => [...prev, fid]);
    if (select) setSelectedFid(fid);
  }, []);

  const onSubmit = useCallback(async (e?: FormEvent) => {
    e?.preventDefault();
    if (!query.trim()) return;
    setLoading(true); setError(null);
    try {
      const g = await resolveLocation(query);
      setResolved(g);
      const r = await postSolarScoreV2({ latitude: g.latitude, longitude: g.longitude });
      addResult(r, g.source === "coordinates" ? undefined : g.formatted_address);
    } catch (err) {
      setResolved(null);
      setError(err instanceof Error ? err.message : "Scoring failed");
    } finally { setLoading(false); }
  }, [query, addResult]);

  const onCsv = useCallback(async (file: File) => {
    setError(null);
    const { rows, error: parseErr } = parseLocationCsv(await file.text(), batchLimit);
    if (parseErr) { setError(parseErr); return; }
    setLoading(true);
    setProgress({ done: 0, total: rows.length });
    for (const row of rows) {
      let lat = row.latitude, lng = row.longitude, name = row.name;
      if ((lat == null || lng == null) && row.address) {
        try {
          const g = await resolveLocation(row.address);
          lat = g.latitude; lng = g.longitude; name = name || g.formatted_address;
        } catch { setProgress((p) => p && { ...p, done: p.done + 1 }); continue; }
      }
      if (lat == null || lng == null) { setProgress((p) => p && { ...p, done: p.done + 1 }); continue; }
      try {
        const r = await postSolarScoreV2({ latitude: lat, longitude: lng });
        addResult(r, name, false);  // don't yank the map around mid-batch
      } catch { /* skip a failed row */ }
      setProgress((p) => p && { ...p, done: p.done + 1 });
    }
    setProgress(null);
    setLoading(false);
  }, [addResult, batchLimit]);

  const exportSingle = useCallback(async () => {
    if (!selectedFid) return;
    const r = results[selectedFid];
    setPdfBusy("single"); setError(null);
    try { await downloadSolarPdf(r.query.latitude, r.query.longitude, r.name); }
    catch (e) { setError(e instanceof Error ? e.message : "PDF export failed"); }
    finally { setPdfBusy(null); }
  }, [selectedFid, results]);

  const exportBatch = useCallback(async () => {
    setPdfBusy("batch"); setError(null);
    try {
      const locs = order.map((fid) => ({
        latitude: results[fid].query.latitude,
        longitude: results[fid].query.longitude,
        name: results[fid].name,
      }));
      await downloadSolarBatchPdf(locs);
    } catch (e) { setError(e instanceof Error ? e.message : "PDF export failed"); }
    finally { setPdfBusy(null); }
  }, [order, results]);

  const features = useMemo(
    () => fc(order.map((fid) => solarFeature(fid, results[fid]))),
    [order, results],
  );
  const selected = selectedFid ? results[selectedFid] : null;
  const isBatch = order.length > 1 || (progress?.total ?? 0) > 1;
  const pct = progress ? Math.round((progress.done / Math.max(progress.total, 1)) * 100) : 0;

  return (
    <div className="flex h-full flex-col">
      <TopNav active="energy" />
      <div className="flex flex-1 overflow-hidden">
        <aside className="flex w-[360px] shrink-0 flex-col overflow-y-auto border-r border-zinc-800 bg-zinc-950">
          <div className="border-b border-zinc-800 p-4">
            <span className="inline-block rounded-full border border-amber-500/30 bg-amber-500/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-amber-300">
              Heavi Energy
            </span>
            <h1 className="mt-2 text-lg font-bold text-white">Solar site screening</h1>
            <p className="mt-1 text-[11px] leading-relaxed text-zinc-400">
              Score one site or a CSV of parcels · ranked results on the map.
            </p>
          </div>

          <form onSubmit={onSubmit} className="space-y-3 border-b border-zinc-800 p-4">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Score a site</p>
            <GeocodeInput value={query} onChange={setQuery} onEnter={() => onSubmit()} resolved={resolved} error={error} />
            <button type="submit" disabled={loading}
              className="w-full rounded-md bg-blue-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-blue-500 disabled:opacity-40">
              {loading && !progress ? "Scoring…" : "Score this site"}
            </button>
            <label className="block cursor-pointer rounded-md border border-dashed border-zinc-700 px-3 py-2 text-center text-[11px] text-zinc-400 hover:border-zinc-500">
              Upload CSV (latitude,longitude or address — optional name)
              <input type="file" accept=".csv,text/csv,text/plain" className="hidden"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) onCsv(f); e.target.value = ""; }} />
            </label>
          </form>

          {/* Batch progress indicator */}
          {progress && (
            <div className="border-b border-zinc-800 p-4">
              <p className="text-[11px] text-zinc-300">
                Scoring {progress.done} of {progress.total}…
              </p>
              <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-zinc-800">
                <div className="h-full bg-blue-500 transition-all" style={{ width: `${pct}%` }} />
              </div>
            </div>
          )}

          {/* Results: ranked list (batch) + selected detail */}
          <div className="flex-1 space-y-3 p-4">
            {isBatch && order.length > 0 && (
              <div>
                <div className="mb-1.5 flex items-center justify-between">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
                    Ranked results ({order.length}{progress ? ` of ${progress.total}` : ""})
                  </p>
                  {!progress && (
                    <button onClick={exportBatch} disabled={pdfBusy !== null}
                      className="rounded border border-zinc-700 px-2 py-0.5 text-[10px] text-zinc-300 transition hover:border-zinc-500 hover:text-white disabled:opacity-40">
                      {pdfBusy === "batch" ? "Generating…" : "Export portfolio PDF"}
                    </button>
                  )}
                </div>
                <BatchRankedList results={results} order={order} selectedFid={selectedFid} onSelect={setSelectedFid} />
              </div>
            )}
            {selected ? (
              <div className={isBatch ? "border-t border-zinc-800 pt-3" : ""}>
                <div className="mb-2 flex justify-end">
                  <button onClick={exportSingle} disabled={pdfBusy !== null}
                    className="rounded-md bg-zinc-800 px-3 py-1.5 text-[11px] font-medium text-zinc-200 transition hover:bg-zinc-700 disabled:opacity-40">
                    {pdfBusy === "single" ? "Generating PDF…" : "Export PDF"}
                  </button>
                </div>
                <EnergyDetail r={selected} />
              </div>
            ) : !isBatch ? (
              <p className="text-[11px] text-zinc-500">
                {order.length > 0 ? "Click a marker to inspect its assessment." : "Score a site to see it on the map."}
              </p>
            ) : null}
            {order.length > 1 && (
              <p className="text-[10px] text-zinc-600"><Link href="/portfolio" className="hover:text-zinc-400">portfolio workflow →</Link></p>
            )}
          </div>
        </aside>

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
