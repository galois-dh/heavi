"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import { TopNav } from "../../components/top-nav";
import {
  postSolarDiscover,
  postSolarScore,
  type SolarCriteria,
  type SolarDiscoverResponse,
  type SolarRating,
  type SolarResult,
  type SolarScoreResponse,
} from "../../lib/api";

// ─── Rating helpers ────────────────────────────────────────────────────────

const RATING_BG: Record<SolarRating, string> = {
  High: "bg-green-100 text-green-800 border-green-200",
  Moderate: "bg-amber-100 text-amber-800 border-amber-200",
  Low: "bg-red-100 text-red-800 border-red-200",
};
const RATING_HEX: Record<SolarRating, string> = {
  High: "#16a34a",
  Moderate: "#f59e0b",
  Low: "#dc2626",
};

const KERN_CENTER: [number, number] = [-119.0, 35.4];
const KERN_ZOOM = 9;

// ─── Map ─────────────────────────────────────────────────────────────────

function SolarMap({
  results,
  selectedId,
  onSelect,
}: {
  results: SolarResult[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

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
      center: KERN_CENTER,
      zoom: KERN_ZOOM,
    });
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const apply = () => {
      const fc: GeoJSON.FeatureCollection = {
        type: "FeatureCollection",
        features: results
          .filter((r) => r.location.latitude != null && r.location.longitude != null)
          .map((r) => ({
            type: "Feature",
            geometry: {
              type: "Point",
              coordinates: [r.location.longitude!, r.location.latitude!],
            },
            properties: { id: r.parcel_id, rating: r.suitability_rating, score: r.suitability_score },
          })),
      };
      const existing = map.getSource("solar") as maplibregl.GeoJSONSource | undefined;
      if (existing) {
        existing.setData(fc);
      } else {
        map.addSource("solar", { type: "geojson", data: fc });
        const colorExpr: maplibregl.ExpressionSpecification = [
          "match",
          ["get", "rating"],
          "High",
          RATING_HEX.High,
          "Moderate",
          RATING_HEX.Moderate,
          "Low",
          RATING_HEX.Low,
          "#64748b",
        ];
        map.addLayer({
          id: "solar-points",
          type: "circle",
          source: "solar",
          paint: {
            "circle-radius": 7,
            "circle-color": colorExpr,
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": 1.5,
          },
        });
        // Selection ring (filter updated below).
        map.addLayer({
          id: "solar-selected",
          type: "circle",
          source: "solar",
          filter: ["==", ["get", "id"], "__none__"],
          paint: {
            "circle-radius": 11,
            "circle-color": "rgba(0,0,0,0)",
            "circle-stroke-color": "#1d4ed8",
            "circle-stroke-width": 3,
          },
        });
        map.on("click", "solar-points", (e) => {
          const f = e.features?.[0];
          const id = f?.properties?.id;
          if (typeof id === "string") onSelectRef.current(id);
        });
        map.on("mouseenter", "solar-points", () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", "solar-points", () => {
          map.getCanvas().style.cursor = "";
        });
      }
      const bounds = new maplibregl.LngLatBounds();
      let any = false;
      for (const f of fc.features) {
        if (f.geometry.type === "Point") {
          bounds.extend(f.geometry.coordinates as [number, number]);
          any = true;
        }
      }
      if (any) map.fitBounds(bounds, { padding: 60, maxZoom: 12, duration: 700 });
    };
    if (map.isStyleLoaded()) apply();
    else map.once("load", apply);
  }, [results]);

  // Update selection ring.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const setFilter = () => {
      if (map.getLayer("solar-selected")) {
        map.setFilter("solar-selected", ["==", ["get", "id"], selectedId ?? "__none__"]);
      }
    };
    if (map.isStyleLoaded()) setFilter();
    else map.once("load", setFilter);
  }, [selectedId]);

  return <div ref={ref} className="h-full w-full" />;
}

// ─── Criterion bar ─────────────────────────────────────────────────────────

function Bar({ label, score, value }: { label: string; score: number; value: string }) {
  const pct = Math.round(Math.max(0, Math.min(1, score)) * 100);
  const color = score >= 0.7 ? "bg-green-500" : score >= 0.4 ? "bg-amber-500" : "bg-red-500";
  return (
    <div>
      <div className="flex items-baseline justify-between text-[11px]">
        <span className="text-zinc-600">{label}</span>
        <span className="tabular-nums text-zinc-500">{value}</span>
      </div>
      <div className="mt-0.5 h-1.5 w-full overflow-hidden rounded-full bg-zinc-200">
        <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function criteriaBars(c: SolarCriteria) {
  const km = (v: number | null) => (v == null ? "—" : `${v.toFixed(1)} km`);
  return [
    {
      label: "Solar resource (GHI)",
      score: c.solar_irradiance_score,
      value: c.solar_irradiance_ghi_kwh_m2_day == null ? "—" : `${c.solar_irradiance_ghi_kwh_m2_day} kWh/m²/d`,
    },
    { label: "Grid proximity", score: c.grid_proximity_score, value: km(c.grid_distance_km) },
    {
      label: "Slope",
      score: c.slope_score,
      value: c.slope_percent == null ? "—" : `${c.slope_percent}%`,
    },
    {
      label: "Aspect",
      score: c.aspect_score,
      value:
        c.aspect_deviation_from_south_degrees == null
          ? "flat"
          : `${c.aspect_deviation_from_south_degrees}° from S`,
    },
    {
      label: "Soil",
      score: c.soil_score,
      value: c.soil_capability_class == null ? "—" : `class ${c.soil_capability_class}`,
    },
    { label: "Road access", score: c.road_access_score, value: km(c.road_distance_km) },
    {
      label: "Land use",
      score: c.land_use_score,
      value: c.land_use_category ?? "—",
    },
  ];
}

// ─── Detail panel ──────────────────────────────────────────────────────────

function DetailPanel({ r }: { r: SolarResult }) {
  const failed = Object.entries(r.constraints_passed)
    .filter(([, v]) => !v)
    .map(([k]) => k);
  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <p className="font-mono text-xs text-zinc-500">{r.parcel_id}</p>
          <p className="mt-1 text-2xl font-bold tabular-nums text-zinc-900">
            {r.suitability_score.toFixed(2)}
          </p>
        </div>
        <span className={`rounded-md border px-2.5 py-1 text-xs font-semibold ${RATING_BG[r.suitability_rating]}`}>
          {r.suitability_rating}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-md border border-zinc-200 bg-zinc-50 p-2.5">
          <p className="text-[10px] uppercase tracking-wider text-zinc-500">Acreage</p>
          <p className="text-base font-semibold tabular-nums">{r.acreage ?? "—"}</p>
        </div>
        <div className="rounded-md border border-zinc-200 bg-zinc-50 p-2.5">
          <p className="text-[10px] uppercase tracking-wider text-zinc-500">Est. capacity</p>
          <p className="text-base font-semibold tabular-nums">{r.estimated_capacity_mw} MW</p>
        </div>
      </div>

      <div>
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
          Criteria
        </p>
        <div className="space-y-2.5">
          {criteriaBars(r.criteria_scores).map((b) => (
            <Bar key={b.label} {...b} />
          ))}
        </div>
      </div>

      <div className="rounded-md border border-zinc-200 bg-zinc-50 p-3 text-xs leading-relaxed text-zinc-700">
        {r.natural_language_summary}
      </div>

      {failed.length > 0 && (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-[11px] text-red-700">
          Failed constraints: {failed.join(", ").replace(/_/g, " ")}
        </div>
      )}

      <p className="text-[10px] leading-relaxed text-zinc-400">
        {r.methodology.summary} Weights: {r.methodology.weights_source}. Capacity:{" "}
        {r.methodology.capacity_method}.
      </p>
    </div>
  );
}

// ─── Discover tab ──────────────────────────────────────────────────────────

function DiscoverTab() {
  const [minAcreage, setMinAcreage] = useState(10);
  const [maxSlope, setMaxSlope] = useState(15);
  const [data, setData] = useState<SolarDiscoverResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Fetch on mount + when filters change (debounced — discover is ~5 s).
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const t = setTimeout(async () => {
      try {
        const res = await postSolarDiscover({
          geography: "kern",
          top_n: 50,
          min_acreage: minAcreage,
          max_slope: maxSlope,
        });
        if (cancelled) return;
        if (res.error) {
          setError(res.error);
          setData(null);
        } else {
          setData(res);
          setSelectedId((cur) => cur ?? res.results[0]?.parcel_id ?? null);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 600);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [minAcreage, maxSlope]);

  const selected = useMemo(
    () => data?.results.find((r) => r.parcel_id === selectedId) ?? null,
    [data, selectedId],
  );
  const summary = data?.portfolio_summary;

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[340px_1fr_360px]">
      {/* Filters + ranked list */}
      <section className="flex min-h-0 flex-col overflow-y-auto border-r border-zinc-200 bg-white p-5">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-zinc-500">
          Filters
        </h2>
        <Slider
          label="Min acreage"
          value={minAcreage}
          min={5}
          max={200}
          step={5}
          suffix=" ac"
          onChange={setMinAcreage}
        />
        <Slider
          label="Max slope"
          value={maxSlope}
          min={2}
          max={30}
          step={1}
          suffix="%"
          onChange={setMaxSlope}
        />

        <h2 className="mb-2 mt-6 text-xs font-semibold uppercase tracking-wider text-zinc-500">
          Top sites {data && `(${data.results.length})`}
        </h2>
        {loading && <p className="text-xs text-zinc-400">Scoring Kern County parcels…</p>}
        {error && (
          <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
            {error}
          </p>
        )}
        <div className="space-y-1">
          {data?.results.map((r, i) => (
            <button
              key={r.parcel_id}
              onClick={() => setSelectedId(r.parcel_id)}
              className={`flex w-full items-center justify-between rounded-md border px-2.5 py-1.5 text-left text-xs transition ${
                selectedId === r.parcel_id
                  ? "border-blue-400 bg-blue-50"
                  : "border-zinc-200 hover:bg-zinc-50"
              }`}
            >
              <span className="flex items-center gap-2">
                <span className="w-4 text-right tabular-nums text-zinc-400">{i + 1}</span>
                <span
                  className="inline-block h-2.5 w-2.5 rounded-full"
                  style={{ background: RATING_HEX[r.suitability_rating] }}
                />
                <span className="font-mono text-[11px] text-zinc-700">{r.parcel_id}</span>
              </span>
              <span className="tabular-nums font-semibold text-zinc-900">
                {r.suitability_score.toFixed(2)}
              </span>
            </button>
          ))}
        </div>
      </section>

      {/* Map + summary strip */}
      <section className="relative flex min-h-0 flex-col">
        {summary && (
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-zinc-200 bg-white px-4 py-2 text-xs">
            <Stat label="Evaluated" value={summary.total_parcels_evaluated.toLocaleString()} />
            <Stat label="Pass constraints" value={summary.parcels_passing_constraints.toLocaleString()} />
            <Stat
              label="Capacity"
              value={`${Math.round(summary.total_estimated_capacity_mw).toLocaleString()} MW`}
            />
            <span className="flex items-center gap-2">
              <Pill color={RATING_HEX.High} label={`${summary.score_distribution.High} High`} />
              <Pill color={RATING_HEX.Moderate} label={`${summary.score_distribution.Moderate} Mod`} />
              <Pill color={RATING_HEX.Low} label={`${summary.score_distribution.Low} Low`} />
            </span>
          </div>
        )}
        <div className="relative flex-1">
          <SolarMap results={data?.results ?? []} selectedId={selectedId} onSelect={setSelectedId} />
          {loading && (
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-white/40 text-xs text-zinc-500">
              Loading parcels…
            </div>
          )}
        </div>
      </section>

      {/* Detail panel */}
      <section className="min-h-0 overflow-y-auto border-l border-zinc-200 bg-white p-5">
        {selected ? (
          <DetailPanel r={selected} />
        ) : (
          <p className="text-xs text-zinc-400">Select a parcel on the map or list to see details.</p>
        )}
      </section>
    </div>
  );
}

function Slider({
  label,
  value,
  min,
  max,
  step,
  suffix,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  suffix: string;
  onChange: (v: number) => void;
}) {
  return (
    <div className="mb-3">
      <div className="flex items-baseline justify-between text-xs">
        <span className="text-zinc-600">{label}</span>
        <span className="font-semibold tabular-nums text-zinc-900">
          {value}
          {suffix}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-1 w-full accent-blue-600"
      />
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <span className="flex items-baseline gap-1.5">
      <span className="text-[10px] uppercase tracking-wider text-zinc-400">{label}</span>
      <span className="font-semibold tabular-nums text-zinc-900">{value}</span>
    </span>
  );
}

function Pill({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1 text-[11px] text-zinc-600">
      <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: color }} />
      {label}
    </span>
  );
}

// ─── Score tab ─────────────────────────────────────────────────────────────

type ScoreSortKey = "parcel_id" | "suitability_score" | "estimated_capacity_mw" | "rating";

function ScoreTab() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resp, setResp] = useState<SolarScoreResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<ScoreSortKey>("suitability_score");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const submit = useCallback(async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const res = await postSolarScore(file);
      setResp(res);
      setSelectedId(res.results[0]?.parcel_id ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [file]);

  const sorted = useMemo(() => {
    if (!resp) return [];
    const mul = sortDir === "asc" ? 1 : -1;
    const get = (r: SolarResult): string | number => {
      switch (sortKey) {
        case "parcel_id":
          return r.parcel_id;
        case "suitability_score":
          return r.suitability_score;
        case "estimated_capacity_mw":
          return r.estimated_capacity_mw;
        case "rating":
          return ["High", "Moderate", "Low"].indexOf(r.suitability_rating);
      }
    };
    return [...resp.results].sort((a, b) => {
      const av = get(a);
      const bv = get(b);
      return av < bv ? -1 * mul : av > bv ? 1 * mul : 0;
    });
  }, [resp, sortKey, sortDir]);

  const toggleSort = (k: ScoreSortKey) => {
    if (sortKey === k) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(k);
      setSortDir(k === "parcel_id" ? "asc" : "desc");
    }
  };

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[420px_1fr]">
      <section className="flex min-h-0 flex-col overflow-y-auto border-r border-zinc-200 bg-white p-5">
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">
          Upload parcels
        </h2>
        <div
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            const f = e.dataTransfer.files?.[0];
            if (f) {
              setFile(f);
              setResp(null);
              setError(null);
            }
          }}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          className={`rounded-lg border-2 border-dashed px-4 py-6 text-center transition ${
            dragging ? "border-blue-500 bg-blue-50" : "border-zinc-300 bg-zinc-50"
          }`}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".geojson,.json,.csv,application/geo+json,application/json,text/csv"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) {
                setFile(f);
                setResp(null);
                setError(null);
              }
            }}
          />
          {file ? (
            <div className="text-sm">
              <p className="font-medium text-zinc-900">{file.name}</p>
              <p className="text-xs text-zinc-500">{(file.size / 1024).toFixed(1)} KB</p>
              <button
                onClick={() => inputRef.current?.click()}
                className="mt-2 text-xs font-medium text-blue-600 hover:text-blue-800"
              >
                Choose a different file
              </button>
            </div>
          ) : (
            <div>
              <p className="text-sm text-zinc-700">Drag a GeoJSON or CSV here</p>
              <button
                onClick={() => inputRef.current?.click()}
                className="mt-2 rounded-md bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-zinc-800"
              >
                Or browse
              </button>
            </div>
          )}
        </div>
        <p className="mt-2 text-[11px] leading-relaxed text-zinc-500">
          GeoJSON FeatureCollection of parcel polygons/points, or a CSV with{" "}
          <code className="rounded bg-zinc-100 px-1">address</code> or{" "}
          <code className="rounded bg-zinc-100 px-1">latitude</code>+
          <code className="rounded bg-zinc-100 px-1">longitude</code>. This works for any US
          geography — your parcels are enriched against national data layers.
        </p>
        <button
          onClick={submit}
          disabled={!file || loading}
          className="mt-4 w-full rounded-md bg-blue-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-blue-500 disabled:opacity-40"
        >
          {loading ? "Scoring parcels…" : "Score parcels"}
        </button>
        {error && (
          <p className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
            {error}
          </p>
        )}
        {resp && (
          <p className="mt-3 text-xs text-zinc-500">
            Scored {resp.scored_count} of {resp.parcel_count} parcels.
          </p>
        )}
        {resp && selectedId && (
          <div className="mt-4 border-t border-zinc-200 pt-4">
            {(() => {
              const r = resp.results.find((x) => x.parcel_id === selectedId);
              return r ? <DetailPanel r={r} /> : null;
            })()}
          </div>
        )}
      </section>

      <section className="grid min-h-0 grid-rows-[55%_45%]">
        <div className="relative border-b border-zinc-200">
          <SolarMap results={resp?.results ?? []} selectedId={selectedId} onSelect={setSelectedId} />
          {!resp && (
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-xs text-zinc-400">
              Scored parcels appear here, color-coded by suitability.
            </div>
          )}
        </div>
        <div className="min-h-0 overflow-auto bg-white">
          {resp ? (
            <table className="w-full text-xs">
              <thead className="sticky top-0 z-10 bg-white text-zinc-500 shadow-[0_1px_0_rgba(0,0,0,.08)]">
                <tr>
                  <ScoreTh label="Parcel" k="parcel_id" sk={sortKey} dir={sortDir} onSort={toggleSort} />
                  <ScoreTh label="Score" k="suitability_score" sk={sortKey} dir={sortDir} onSort={toggleSort} align="right" />
                  <ScoreTh label="Rating" k="rating" sk={sortKey} dir={sortDir} onSort={toggleSort} />
                  <ScoreTh label="MW" k="estimated_capacity_mw" sk={sortKey} dir={sortDir} onSort={toggleSort} align="right" />
                  <th className="px-3 py-2 text-left font-medium uppercase tracking-wider">Top factors</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((r) => {
                  const top = criteriaBars(r.criteria_scores)
                    .slice()
                    .sort((a, b) => b.score - a.score)
                    .slice(0, 2)
                    .map((b) => b.label);
                  return (
                    <tr
                      key={r.parcel_id}
                      onClick={() => setSelectedId(r.parcel_id)}
                      className={`cursor-pointer border-t border-zinc-100 ${
                        selectedId === r.parcel_id ? "bg-blue-50" : "hover:bg-zinc-50"
                      }`}
                    >
                      <td className="px-3 py-1.5 font-mono text-[11px] text-zinc-700">{r.parcel_id}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums font-semibold">
                        {r.suitability_score.toFixed(2)}
                      </td>
                      <td className="px-3 py-1.5">
                        <span className={`rounded border px-2 py-0.5 text-[10px] font-medium ${RATING_BG[r.suitability_rating]}`}>
                          {r.suitability_rating}
                        </span>
                      </td>
                      <td className="px-3 py-1.5 text-right tabular-nums">{r.estimated_capacity_mw}</td>
                      <td className="px-3 py-1.5 text-zinc-600">{top.join(", ")}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <div className="flex h-full items-center justify-center text-xs text-zinc-400">
              Per-parcel results will appear here.
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function ScoreTh({
  label,
  k,
  sk,
  dir,
  onSort,
  align = "left",
}: {
  label: string;
  k: ScoreSortKey;
  sk: ScoreSortKey;
  dir: "asc" | "desc";
  onSort: (k: ScoreSortKey) => void;
  align?: "left" | "right";
}) {
  return (
    <th
      onClick={() => onSort(k)}
      className={`cursor-pointer select-none px-3 py-2 font-medium uppercase tracking-wider hover:text-zinc-900 ${
        align === "right" ? "text-right" : "text-left"
      }`}
    >
      {label}
      {sk === k && <span className="ml-1 text-zinc-400">{dir === "asc" ? "↑" : "↓"}</span>}
    </th>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────

export default function SolarPage() {
  const [tab, setTab] = useState<"discover" | "score">("discover");

  // Honor ?mode=score deep link from the landing page.
  useEffect(() => {
    if (typeof window !== "undefined") {
      const m = new URLSearchParams(window.location.search).get("mode");
      if (m === "score") setTab("score");
    }
  }, []);

  return (
    <div className="flex h-full flex-col bg-zinc-50 text-zinc-900">
      <TopNav active="solar" />
      <header className="flex items-center justify-between border-b border-zinc-200 bg-white px-6 py-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Solar Site Suitability</h1>
          <p className="text-xs text-zinc-500">
            Multi-criteria utility-solar scoring · Kern County, California · validated against EIA
            Form 860
          </p>
        </div>
        <div className="flex rounded-md border border-zinc-300 p-0.5 text-sm">
          <button
            onClick={() => setTab("discover")}
            className={`rounded px-3 py-1 font-medium transition ${
              tab === "discover" ? "bg-blue-600 text-white" : "text-zinc-600 hover:bg-zinc-100"
            }`}
          >
            Discover
          </button>
          <button
            onClick={() => setTab("score")}
            className={`rounded px-3 py-1 font-medium transition ${
              tab === "score" ? "bg-blue-600 text-white" : "text-zinc-600 hover:bg-zinc-100"
            }`}
          >
            Score Your Parcels
          </button>
        </div>
      </header>

      <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {tab === "discover" ? <DiscoverTab /> : <ScoreTab />}
      </main>
    </div>
  );
}
