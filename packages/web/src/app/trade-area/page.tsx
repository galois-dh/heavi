"use client";

import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import { TopNav } from "../../components/top-nav";
import {
  postTradeAreaDiscover,
  postTradeAreaScore,
  type TradeAreaCandidate,
  type TradeAreaRating,
  type TradeAreaScoreResponse,
} from "../../lib/api";

const DALLAS_CENTER: [number, number] = [-96.8, 32.78];
const DALLAS_ZOOM = 9.3;

const CATEGORIES = [
  "coffee_shop", "pharmacy", "restaurant", "fast_food",
  "bank", "gym", "grocery", "urgent_care",
];

const RATING_BG: Record<TradeAreaRating, string> = {
  Strong: "bg-green-100 text-green-800 border-green-200",
  Moderate: "bg-amber-100 text-amber-800 border-amber-200",
  Weak: "bg-red-100 text-red-800 border-red-200",
};
// Ring fill by drive-time (inner darkest).
const RING_HEX: Record<number, string> = { 5: "#1d4ed8", 10: "#3b82f6", 15: "#93c5fd" };

function num(v: number | null | undefined): string {
  return v == null ? "—" : v.toLocaleString("en-US");
}

// ─── Map ─────────────────────────────────────────────────────────────────

function TradeAreaMap({
  rings,
  marker,
  candidates,
}: {
  rings?: TradeAreaScoreResponse["trade_area_rings"];
  marker?: [number, number] | null;
  candidates?: TradeAreaCandidate[];
}) {
  const ref = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markerRef = useRef<maplibregl.Marker | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const map = new maplibregl.Map({
      container: ref.current,
      style: {
        version: 8,
        sources: {
          carto: {
            type: "raster",
            tiles: ["https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}@2x.png"],
            tileSize: 256,
            attribution: "© OSM © CARTO",
          },
        },
        layers: [{ id: "carto", type: "raster", source: "carto" }],
      },
      center: DALLAS_CENTER,
      zoom: DALLAS_ZOOM,
    });
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Isochrone rings (Score mode).
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const apply = () => {
      const fc: GeoJSON.FeatureCollection = {
        type: "FeatureCollection",
        features: (rings ?? [])
          .slice()
          .sort((a, b) => b.drive_time_minutes - a.drive_time_minutes) // outer first
          .map((r) => ({
            type: "Feature",
            geometry: r.isochrone,
            properties: { minutes: r.drive_time_minutes },
          })),
      };
      const src = map.getSource("rings") as maplibregl.GeoJSONSource | undefined;
      if (src) {
        src.setData(fc);
      } else {
        map.addSource("rings", { type: "geojson", data: fc });
        const color: maplibregl.ExpressionSpecification = [
          "match", ["get", "minutes"],
          5, RING_HEX[5], 10, RING_HEX[10], 15, RING_HEX[15], "#3b82f6",
        ];
        map.addLayer({
          id: "rings-fill", type: "fill", source: "rings",
          paint: { "fill-color": color, "fill-opacity": 0.18 },
        });
        map.addLayer({
          id: "rings-line", type: "line", source: "rings",
          paint: { "line-color": color, "line-width": 1.5 },
        });
      }
      if (fc.features.length) {
        const b = new maplibregl.LngLatBounds();
        for (const f of fc.features) {
          const g = f.geometry as GeoJSON.Polygon;
          for (const c of g.coordinates[0] ?? []) b.extend(c as [number, number]);
        }
        if (!b.isEmpty()) map.fitBounds(b, { padding: 50, maxZoom: 13, duration: 700 });
      }
    };
    if (map.isStyleLoaded()) apply();
    else map.once("load", apply);
  }, [rings]);

  // Marker (Score mode).
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    markerRef.current?.remove();
    if (marker) {
      const el = document.createElement("div");
      el.style.cssText =
        "width:16px;height:16px;border-radius:50%;background:#dc2626;border:3px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4);";
      markerRef.current = new maplibregl.Marker({ element: el }).setLngLat(marker).addTo(map);
    }
  }, [marker]);

  // Candidate markers (Discover mode).
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const apply = () => {
      const fc: GeoJSON.FeatureCollection = {
        type: "FeatureCollection",
        features: (candidates ?? []).map((c, i) => ({
          type: "Feature",
          geometry: { type: "Point", coordinates: [c.longitude, c.latitude] },
          properties: { score: c.lightweight_score, rank: i + 1 },
        })),
      };
      const src = map.getSource("cands") as maplibregl.GeoJSONSource | undefined;
      if (src) {
        src.setData(fc);
      } else {
        map.addSource("cands", { type: "geojson", data: fc });
        map.addLayer({
          id: "cands-pt", type: "circle", source: "cands",
          paint: {
            "circle-radius": 7,
            "circle-color": [
              "interpolate", ["linear"], ["get", "score"],
              0.4, "#f59e0b", 0.7, "#84cc16", 1.0, "#16a34a",
            ],
            "circle-stroke-color": "#ffffff", "circle-stroke-width": 1.5,
          },
        });
      }
      if (fc.features.length) {
        const b = new maplibregl.LngLatBounds();
        for (const f of fc.features) {
          if (f.geometry.type === "Point") b.extend(f.geometry.coordinates as [number, number]);
        }
        if (!b.isEmpty()) map.fitBounds(b, { padding: 50, maxZoom: 12, duration: 700 });
      }
    };
    if (map.isStyleLoaded()) apply();
    else map.once("load", apply);
  }, [candidates]);

  return <div ref={ref} className="h-full w-full" />;
}

// ─── Criterion bar ─────────────────────────────────────────────────────────

function Bar({ label, score }: { label: string; score: number }) {
  const pct = Math.round(Math.max(0, Math.min(1, score)) * 100);
  const color = score >= 0.7 ? "bg-green-500" : score >= 0.4 ? "bg-amber-500" : "bg-red-500";
  return (
    <div>
      <div className="flex items-baseline justify-between text-[11px]">
        <span className="text-zinc-600 capitalize">{label.replace(/_/g, " ")}</span>
        <span className="tabular-nums text-zinc-500">{score.toFixed(2)}</span>
      </div>
      <div className="mt-0.5 h-1.5 w-full overflow-hidden rounded-full bg-zinc-200">
        <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

// ─── Score tab ─────────────────────────────────────────────────────────────

function ScoreTab() {
  const [address, setAddress] = useState("");
  const [category, setCategory] = useState("coffee_shop");
  const [resp, setResp] = useState<TradeAreaScoreResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      if (!address.trim() || loading) return;
      setLoading(true);
      setError(null);
      try {
        const r = await postTradeAreaScore({ address: address.trim(), business_category: category });
        setResp(r);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Scoring failed");
      } finally {
        setLoading(false);
      }
    },
    [address, category, loading],
  );

  const marker: [number, number] | null = resp
    ? [resp.query.longitude, resp.query.latitude]
    : null;

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[420px_1fr]">
      <section className="flex min-h-0 flex-col overflow-y-auto border-r border-zinc-200 bg-white p-5">
        <form onSubmit={onSubmit} className="space-y-2">
          <label className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
            Location
          </label>
          <input
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            placeholder="Dallas address (e.g. 1500 Marilla St, Dallas, TX)"
            className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
          <label className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
            Business category
          </label>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          >
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c.replace(/_/g, " ")}
              </option>
            ))}
          </select>
          <button
            type="submit"
            disabled={loading || !address.trim()}
            className="w-full rounded-md bg-blue-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-blue-500 disabled:opacity-40"
          >
            {loading ? "Scoring trade area…" : "Score location"}
          </button>
        </form>
        {error && (
          <p className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
            {error}
          </p>
        )}

        {resp && (
          <div className="mt-5 space-y-4">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-2xl font-bold tabular-nums">{resp.suitability_score.toFixed(2)}</p>
                <p className="text-[11px] text-zinc-500">{resp.query.resolved_address}</p>
              </div>
              <span className={`rounded-md border px-2.5 py-1 text-xs font-semibold ${RATING_BG[resp.suitability_rating]}`}>
                {resp.suitability_rating}
              </span>
            </div>

            <div>
              <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
                Trade area rings
              </p>
              <table className="w-full text-[11px]">
                <thead className="text-zinc-500">
                  <tr>
                    <th className="text-left font-medium">min</th>
                    <th className="text-right font-medium">pop</th>
                    <th className="text-right font-medium">income</th>
                    <th className="text-right font-medium">jobs</th>
                    <th className="text-right font-medium">comp</th>
                  </tr>
                </thead>
                <tbody className="tabular-nums">
                  {resp.trade_area_rings.map((r) => (
                    <tr key={r.drive_time_minutes} className="border-t border-zinc-100">
                      <td className="py-1">{r.drive_time_minutes}</td>
                      <td className="py-1 text-right">{num(r.population)}</td>
                      <td className="py-1 text-right">
                        {r.median_household_income ? `$${num(r.median_household_income)}` : "—"}
                      </td>
                      <td className="py-1 text-right">{num(r.daytime_jobs)}</td>
                      <td className="py-1 text-right">{r.competitor_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div>
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
                Criteria
              </p>
              <div className="space-y-2">
                {Object.entries(resp.criteria_scores).map(([k, v]) => (
                  <Bar key={k} label={k} score={v} />
                ))}
              </div>
            </div>

            {resp.cannibalization && (
              <div className="rounded-md border border-zinc-200 bg-zinc-50 p-2.5 text-[11px]">
                <span className="font-semibold">Cannibalization:</span>{" "}
                {resp.cannibalization.cannibalization_risk} risk · nearest existing{" "}
                {resp.cannibalization.nearest_existing_km} km
              </div>
            )}

            <div className="rounded-md border border-zinc-200 bg-zinc-50 p-3 text-xs leading-relaxed text-zinc-700">
              {resp.natural_language_summary}
            </div>
          </div>
        )}
      </section>

      <section className="relative min-h-0">
        <TradeAreaMap rings={resp?.trade_area_rings} marker={marker} />
        {!resp && (
          <div className="pointer-events-none absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full bg-white/90 px-3 py-1 text-[11px] font-medium text-zinc-700 shadow">
            Enter a Dallas address and category to see the drive-time trade area
          </div>
        )}
      </section>
    </div>
  );
}

// ─── Discover tab ────────────────────────────────────────────────────────────

function DiscoverTab() {
  const [category, setCategory] = useState("coffee_shop");
  const [resp, setResp] = useState<{
    results: TradeAreaCandidate[];
    candidates_passing_filters: number;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async (cat: string) => {
    setLoading(true);
    setError(null);
    try {
      const r = await postTradeAreaDiscover({ geography: "dallas", business_category: cat, top_n: 25 });
      setResp(r);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Discover failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    run(category);
  }, [category, run]);

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[360px_1fr]">
      <section className="flex min-h-0 flex-col overflow-y-auto border-r border-zinc-200 bg-white p-5">
        <label className="mb-1 text-xs font-semibold uppercase tracking-wider text-zinc-500">
          Business category
        </label>
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="mb-4 w-full rounded-md border border-zinc-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
        >
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c.replace(/_/g, " ")}
            </option>
          ))}
        </select>
        {loading && <p className="text-xs text-zinc-400">Scanning Dallas County…</p>}
        {error && (
          <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
            {error}
          </p>
        )}
        {resp && (
          <>
            <p className="mb-2 text-[11px] text-zinc-500">
              Top {resp.results.length} of {resp.candidates_passing_filters.toLocaleString()} candidate
              locations
            </p>
            <div className="space-y-1">
              {resp.results.map((c, i) => (
                <div
                  key={`${c.latitude},${c.longitude}`}
                  className="flex items-center justify-between rounded-md border border-zinc-200 px-2.5 py-1.5 text-xs"
                >
                  <span className="flex items-center gap-2">
                    <span className="w-4 text-right tabular-nums text-zinc-400">{i + 1}</span>
                    <span className="font-mono text-[10px] text-zinc-600">
                      {c.latitude.toFixed(3)}, {c.longitude.toFixed(3)}
                    </span>
                  </span>
                  <span className="flex items-center gap-3 tabular-nums">
                    <span className="text-zinc-500">{num(c.approx_population_1mi)} pop</span>
                    <span className="text-zinc-500">{c.competitor_count_1mi} comp</span>
                    <span className="font-semibold text-zinc-900">{c.lightweight_score.toFixed(2)}</span>
                  </span>
                </div>
              ))}
            </div>
          </>
        )}
      </section>
      <section className="relative min-h-0">
        <TradeAreaMap candidates={resp?.results} />
        <div className="pointer-events-none absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full bg-white/90 px-3 py-1 text-[11px] font-medium text-zinc-700 shadow">
          Candidates ranked by population + competitive gap (straight-line proxy)
        </div>
      </section>
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────

export default function TradeAreaPage() {
  const [tab, setTab] = useState<"score" | "discover">("score");

  useEffect(() => {
    if (typeof window !== "undefined") {
      const m = new URLSearchParams(window.location.search).get("mode");
      if (m === "discover") setTab("discover");
    }
  }, []);

  return (
    <div className="flex h-full flex-col bg-zinc-50 text-zinc-900">
      <TopNav active="trade-area" />
      <header className="flex items-center justify-between border-b border-zinc-200 bg-white px-6 py-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Trade Area Analysis</h1>
          <p className="text-xs text-zinc-500">
            Demographic · competitive · accessibility site scoring · Dallas County, TX
          </p>
        </div>
        <div className="flex rounded-md border border-zinc-300 p-0.5 text-sm">
          <button
            onClick={() => setTab("score")}
            className={`rounded px-3 py-1 font-medium transition ${
              tab === "score" ? "bg-blue-600 text-white" : "text-zinc-600 hover:bg-zinc-100"
            }`}
          >
            Score
          </button>
          <button
            onClick={() => setTab("discover")}
            className={`rounded px-3 py-1 font-medium transition ${
              tab === "discover" ? "bg-blue-600 text-white" : "text-zinc-600 hover:bg-zinc-100"
            }`}
          >
            Discover
          </button>
        </div>
      </header>
      <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {tab === "score" ? <ScoreTab /> : <DiscoverTab />}
      </main>
    </div>
  );
}
