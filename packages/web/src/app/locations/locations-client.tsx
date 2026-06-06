"use client";

import { type FormEvent, useCallback, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { TopNav } from "../../components/top-nav";
import { HeaviMap, type MapOverlay } from "../../components/heavi-map";
import { LocationsDetail } from "../../components/map-detail-panels";
import { GeocodeInput } from "../../components/geocode-input";
import { postTradeAreaScoreV2, resolveLocation, type GeocodeResult, type TradeAreaScoreV2 } from "../../lib/api";
import { LOCATIONS_CONSTRAINTS, fc, tradeAreaFeature } from "../../lib/map-features";

const CATEGORIES = ["coffee_shop", "pharmacy", "restaurant", "fast_food", "bank", "gym", "grocery", "urgent_care"];

/**
 * Heavi Locations — map-first trade-area scoring (Map Interface Spec, Step 8).
 * Score a site → marker color-coded by trade-area score, isochrone polygons
 * (5/10/15 min graduated opacity) and competitor POIs overlaid, detail panel
 * with demographics + competitive analysis + data provenance.
 */
export default function LocationsClient() {
  const [addr, setAddr] = useState("32.78, -96.80");
  const [resolved, setResolved] = useState<GeocodeResult | null>(null);
  const [category, setCategory] = useState("coffee_shop");
  const [results, setResults] = useState<Record<string, TradeAreaScoreV2>>({});
  const [order, setOrder] = useState<string[]>([]);
  const [selectedFid, setSelectedFid] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const counter = useRef(0);

  const score = useCallback(async (e?: FormEvent) => {
    e?.preventDefault();
    if (!addr.trim()) return;
    setLoading(true); setError(null);
    try {
      const g = await resolveLocation(addr);
      setResolved(g);
      const r = await postTradeAreaScoreV2({ latitude: g.latitude, longitude: g.longitude, business_category: category });
      const fid = `t${counter.current++}`;
      setResults((prev) => ({ ...prev, [fid]: r }));
      setOrder((prev) => [...prev, fid]);
      setSelectedFid(fid);
    } catch (err) {
      setResolved(null);
      setError(err instanceof Error ? err.message : "Scoring failed");
    } finally { setLoading(false); }
  }, [addr, category]);

  const features = useMemo(() => fc(order.map((fid) => tradeAreaFeature(fid, results[fid]))), [order, results]);
  const selected = selectedFid ? results[selectedFid] : null;

  // Isochrone polygons (graduated opacity by drive time) + competitor POIs for
  // the selected site.
  const overlays = useMemo<MapOverlay[]>(() => {
    if (!selected) return [];
    const out: MapOverlay[] = [];
    const rings = selected.trade_area_rings ?? [];
    const isoFeatures: GeoJSON.Feature[] = [];
    for (const r of rings) {
      const geom = r.isochrone as GeoJSON.Geometry | undefined;
      const minutes = (r.drive_time_minutes as number) ?? 0;
      if (geom) isoFeatures.push({ type: "Feature", geometry: geom, properties: { minutes } });
    }
    if (isoFeatures.length) {
      out.push({
        id: "isochrones",
        geojson: fc(isoFeatures),
        type: "fill",
        paint: {
          "fill-color": "#06b6d4",
          // 5 min darkest → 15 min lightest (graduated opacity).
          "fill-opacity": ["match", ["get", "minutes"], 5, 0.28, 10, 0.18, 15, 0.1, 0.15],
        },
      });
      out.push({
        id: "isochrone-lines",
        geojson: fc(isoFeatures),
        type: "line",
        paint: { "line-color": "#06b6d4", "line-width": 1, "line-opacity": 0.5 },
      });
    }
    const pois = selected.competitor_pois ?? [];
    if (pois.length) {
      out.push({
        id: "competitor-pois",
        geojson: fc(pois.map((p) => ({
          type: "Feature", geometry: { type: "Point", coordinates: [p.longitude, p.latitude] }, properties: {},
        }))),
        type: "circle",
        paint: {
          "circle-radius": 3, "circle-color": "#ef4444",
          "circle-stroke-color": "#0b0b0c", "circle-stroke-width": 0.5, "circle-opacity": 0.85,
        },
      });
    }
    return out;
  }, [selected]);

  return (
    <div className="flex h-full flex-col">
      <TopNav active="locations" />
      <div className="flex flex-1 overflow-hidden">
        <aside className="flex w-[360px] shrink-0 flex-col overflow-y-auto border-r border-zinc-800 bg-zinc-950">
          <div className="border-b border-zinc-800 p-4">
            <span className="inline-block rounded-full border border-emerald-500/30 bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-300">
              Heavi Locations
            </span>
            <h1 className="mt-2 text-lg font-bold text-white">Trade area scoring</h1>
            <p className="mt-1 text-[11px] leading-relaxed text-zinc-400">
              Drive-time isochrones · competitive density · color-coded by trade-area score.
            </p>
          </div>

          <form onSubmit={score} className="space-y-3 border-b border-zinc-800 p-4">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Score a site</p>
            <GeocodeInput value={addr} onChange={setAddr} onEnter={() => score()} resolved={resolved} error={error} />
            <select value={category} onChange={(e) => setCategory(e.target.value)}
              className="w-full rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-100">
              {CATEGORIES.map((c) => <option key={c} value={c}>{c.replace("_", " ")}</option>)}
            </select>
            <button type="submit" disabled={loading}
              className="w-full rounded-md bg-emerald-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-emerald-500 disabled:opacity-40">
              {loading ? "Scoring…" : "Score"}
            </button>
            <p className="text-[10px] text-zinc-600">Full coverage in Dallas County · <Link href="/trade-area" className="hover:text-zinc-400">advanced workflow →</Link></p>
          </form>

          <div className="flex-1 p-4">
            {selected ? (
              <LocationsDetail r={selected} />
            ) : (
              <p className="text-[11px] text-zinc-500">
                {order.length > 0 ? "Click a site marker to inspect its trade area." : "Score a site to see it on the map."}
              </p>
            )}
          </div>
        </aside>

        <div className="relative flex-1">
          <HeaviMap
            center={[-96.80, 32.78]}
            zoom={11}
            scoredFeatures={features}
            scoreColorScale="tradearea"
            constraints={LOCATIONS_CONSTRAINTS}
            overlays={overlays}
            onFeatureClick={(f) => setSelectedFid((f.properties?.fid as string) ?? null)}
            selectedFid={selectedFid}
          />
        </div>
      </div>
    </div>
  );
}
