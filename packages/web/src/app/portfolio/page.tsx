"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { TopNav } from "../../components/top-nav";
import maplibregl from "maplibre-gl";
import {
  postPortfolioRisk,
  portfolioReportUrl,
  portfolioSampleCsvUrl,
  type PortfolioResponse,
  type PortfolioRow,
} from "../../lib/api";

// ─── Risk tier helpers ──────────────────────────────────────────────────

type Tier = "high" | "moderate" | "low" | "unscored";

function tierFor(eal: number | null | undefined): Tier {
  if (eal == null) return "unscored";
  if (eal > 500) return "high";
  if (eal >= 50) return "moderate";
  return "low";
}

const TIER_LABEL: Record<Tier, string> = {
  high: "High",
  moderate: "Moderate",
  low: "Low",
  unscored: "—",
};

const TIER_BG: Record<Tier, string> = {
  high: "bg-red-100 text-red-800 border-red-200",
  moderate: "bg-amber-100 text-amber-800 border-amber-200",
  low: "bg-green-100 text-green-800 border-green-200",
  unscored: "bg-zinc-100 text-zinc-600 border-zinc-200",
};

const TIER_MARKER_HEX: Record<Tier, string> = {
  high: "#dc2626",
  moderate: "#f59e0b",
  low: "#16a34a",
  unscored: "#64748b",
};

function fmtMoney(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v < 1) return `$${v.toFixed(2)}`;
  return `$${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

// ─── Sorting ────────────────────────────────────────────────────────────

type SortKey =
  | "row_index"
  | "property_id"
  | "address"
  | "annual_risk_usd"
  | "tier";
type SortDir = "asc" | "desc";

function sortRows(
  rows: PortfolioRow[],
  key: SortKey,
  dir: SortDir,
): PortfolioRow[] {
  const mul = dir === "asc" ? 1 : -1;
  const get = (r: PortfolioRow): string | number => {
    switch (key) {
      case "row_index":
        return r.row_index;
      case "property_id":
        return r.property_id ?? "";
      case "address":
        return r.resolved_address ?? r.input_address ?? "";
      case "annual_risk_usd":
        return r.annual_risk_usd ?? -Infinity;
      case "tier":
        return ["high", "moderate", "low", "unscored"].indexOf(
          tierFor(r.annual_risk_usd),
        );
    }
  };
  return [...rows].sort((a, b) => {
    const av = get(a);
    const bv = get(b);
    if (av < bv) return -1 * mul;
    if (av > bv) return 1 * mul;
    return 0;
  });
}

// ─── Map ─────────────────────────────────────────────────────────────────

function PortfolioMap({ rows }: { rows: PortfolioRow[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

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
      center: [-122.7, 38.5],
      zoom: 9.5,
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
        features: rows
          .filter((r) => r.latitude != null && r.longitude != null)
          .map((r) => ({
            type: "Feature",
            geometry: { type: "Point", coordinates: [r.longitude!, r.latitude!] },
            properties: {
              tier: tierFor(r.annual_risk_usd),
              eal: r.annual_risk_usd ?? 0,
              addr: r.resolved_address ?? r.input_address ?? "",
            },
          })),
      };
      const existing = map.getSource("portfolio") as maplibregl.GeoJSONSource | undefined;
      if (existing) {
        existing.setData(fc);
      } else {
        map.addSource("portfolio", { type: "geojson", data: fc });
        map.addLayer({
          id: "portfolio-points",
          type: "circle",
          source: "portfolio",
          paint: {
            "circle-radius": 7,
            "circle-color": [
              "match",
              ["get", "tier"],
              "high",
              TIER_MARKER_HEX.high,
              "moderate",
              TIER_MARKER_HEX.moderate,
              "low",
              TIER_MARKER_HEX.low,
              TIER_MARKER_HEX.unscored,
            ],
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": 1.5,
          },
        });
      }
      // Fit bounds to plotted points.
      const bounds = new maplibregl.LngLatBounds();
      let any = false;
      for (const f of fc.features) {
        if (f.geometry.type === "Point") {
          bounds.extend(f.geometry.coordinates as [number, number]);
          any = true;
        }
      }
      if (any) map.fitBounds(bounds, { padding: 60, maxZoom: 14, duration: 700 });
    };

    if (map.isStyleLoaded()) apply();
    else map.once("load", apply);
  }, [rows]);

  return <div ref={ref} className="h-full w-full" />;
}

// ─── Page ────────────────────────────────────────────────────────────────

export default function PortfolioPage() {
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<PortfolioResponse | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("annual_risk_usd");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const onFile = useCallback((f: File) => {
    setFile(f);
    setError(null);
    setResponse(null);
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setDragging(false);
      const f = e.dataTransfer.files?.[0];
      if (f) onFile(f);
    },
    [onFile],
  );

  const submit = useCallback(async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const res = await postPortfolioRisk(file);
      setResponse(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [file]);

  const sorted = useMemo(
    () => (response ? sortRows(response.per_property, sortKey, sortDir) : []),
    [response, sortKey, sortDir],
  );

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "annual_risk_usd" ? "desc" : "asc");
    }
  };

  return (
    <div className="flex h-full flex-col bg-zinc-50 text-zinc-900">
      <TopNav active="portfolio" />
      {/* Page sub-header */}
      <header className="flex items-center justify-between border-b border-zinc-200 bg-white px-6 py-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Portfolio Risk Assessment</h1>
          <p className="text-xs text-zinc-500">Upload a property portfolio → wildfire risk per property + portfolio PDF</p>
        </div>
      </header>

      <main className="grid flex-1 grid-cols-1 gap-0 overflow-hidden lg:grid-cols-[480px_1fr]">
        {/* Sidebar */}
        <section className="flex min-h-0 flex-col overflow-y-auto border-r border-zinc-200 bg-white p-5">
          <UploadCard
            file={file}
            dragging={dragging}
            loading={loading}
            error={error}
            onFile={onFile}
            onDrop={onDrop}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onSubmit={submit}
          />
          {response && <SummaryCard response={response} />}
        </section>

        {/* Right column: map + table */}
        <section className="grid min-h-0 grid-rows-[55%_45%]">
          <div className="relative border-b border-zinc-200">
            <PortfolioMap rows={response?.per_property ?? []} />
            {!response && (
              <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-xs text-zinc-400">
                Properties appear here after scoring.
              </div>
            )}
          </div>
          <div className="min-h-0 overflow-auto bg-white">
            {response ? (
              <ResultsTable
                rows={sorted}
                sortKey={sortKey}
                sortDir={sortDir}
                onSort={toggleSort}
              />
            ) : (
              <div className="flex h-full items-center justify-center text-xs text-zinc-400">
                Per-property table will appear here.
              </div>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}

// ─── Upload card ─────────────────────────────────────────────────────────

interface UploadCardProps {
  file: File | null;
  dragging: boolean;
  loading: boolean;
  error: string | null;
  onFile: (f: File) => void;
  onDrop: (e: React.DragEvent<HTMLDivElement>) => void;
  onDragOver: (e: React.DragEvent<HTMLDivElement>) => void;
  onDragLeave: () => void;
  onSubmit: () => void;
}

function UploadCard({
  file,
  dragging,
  loading,
  error,
  onFile,
  onDrop,
  onDragOver,
  onDragLeave,
  onSubmit,
}: UploadCardProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  return (
    <div className="mb-6">
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">
        1 · Upload property CSV
      </h2>
      <div
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        className={`rounded-lg border-2 border-dashed px-4 py-6 text-center transition ${
          dragging
            ? "border-blue-500 bg-blue-50"
            : "border-zinc-300 bg-zinc-50"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv,text/csv"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onFile(f);
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
            <p className="text-sm text-zinc-700">Drag a CSV here</p>
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
        Columns: <code className="rounded bg-zinc-100 px-1">address</code> OR{" "}
        <code className="rounded bg-zinc-100 px-1">latitude</code> +{" "}
        <code className="rounded bg-zinc-100 px-1">longitude</code>. Optional{" "}
        <code className="rounded bg-zinc-100 px-1">property_id</code>. Up to 500 rows.
        Geocoded addresses cost ~1 s each (Nominatim rate limit).{" "}
        <a
          href={portfolioSampleCsvUrl()}
          className="font-medium text-blue-600 hover:text-blue-800"
          download
        >
          Download a 50-row Sonoma sample
        </a>
        .
      </p>

      <button
        onClick={onSubmit}
        disabled={!file || loading}
        className="mt-4 w-full rounded-md bg-blue-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-blue-500 disabled:opacity-40"
      >
        {loading ? "Scoring portfolio…" : "Score portfolio"}
      </button>
      {loading && (
        <p className="mt-2 text-[11px] text-zinc-500">
          Geocoding and scoring sequentially. For large portfolios expect roughly{" "}
          <span className="tabular-nums">N × 1.2 s</span> wall time.
        </p>
      )}
      {error && (
        <p className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {error}
        </p>
      )}
    </div>
  );
}

// ─── Summary card ────────────────────────────────────────────────────────

function SummaryCard({ response }: { response: PortfolioResponse }) {
  const s = response.portfolio_summary;
  return (
    <div className="mb-6 rounded-lg border border-zinc-200 bg-zinc-50 p-4">
      <div className="flex items-baseline justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
          2 · Portfolio summary
        </h2>
        <a
          href={portfolioReportUrl(response.job_id)}
          download
          className="rounded-md bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-zinc-800"
        >
          Export PDF
        </a>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
        <Kpi label="Total annual risk" value={fmtMoney(s.total_annual_risk)} />
        <Kpi label="Mean / property" value={fmtMoney(s.mean_risk)} />
        <Kpi label="Median / property" value={fmtMoney(s.median_risk)} />
        <Kpi label="Scored" value={`${s.scored_count} / ${s.property_count}`} />
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
        <TierChip tier="high" count={s.high_risk_count} />
        <TierChip tier="moderate" count={s.moderate_risk_count} />
        <TierChip tier="low" count={s.low_risk_count} />
      </div>
      {(s.error_count > 0 || s.no_coverage_count > 0) && (
        <p className="mt-3 text-[11px] text-zinc-500">
          {s.error_count > 0 && <>· {s.error_count} geocoding errors </>}
          {s.no_coverage_count > 0 && <>· {s.no_coverage_count} outside Sonoma NSI coverage</>}
        </p>
      )}
    </div>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wider text-zinc-500">{label}</p>
      <p className="mt-0.5 text-base font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function TierChip({ tier, count }: { tier: Tier; count: number }) {
  return (
    <div className={`rounded-md border px-2 py-1.5 text-center ${TIER_BG[tier]}`}>
      <p className="text-[10px] font-medium uppercase tracking-wider">{TIER_LABEL[tier]}</p>
      <p className="text-sm font-semibold tabular-nums">{count}</p>
    </div>
  );
}

// ─── Results table ───────────────────────────────────────────────────────

interface ResultsTableProps {
  rows: PortfolioRow[];
  sortKey: SortKey;
  sortDir: SortDir;
  onSort: (key: SortKey) => void;
}

function ResultsTable({ rows, sortKey, sortDir, onSort }: ResultsTableProps) {
  return (
    <table className="w-full text-xs">
      <thead className="sticky top-0 z-10 bg-white text-zinc-500 shadow-[0_1px_0_rgba(0,0,0,.08)]">
        <tr>
          <Th label="#" sortKey="row_index" active={sortKey} dir={sortDir} onSort={onSort} align="right" />
          <Th label="ID" sortKey="property_id" active={sortKey} dir={sortDir} onSort={onSort} />
          <Th label="Address" sortKey="address" active={sortKey} dir={sortDir} onSort={onSort} />
          <Th label="Annual risk" sortKey="annual_risk_usd" active={sortKey} dir={sortDir} onSort={onSort} align="right" />
          <Th label="Tier" sortKey="tier" active={sortKey} dir={sortDir} onSort={onSort} />
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const tier = tierFor(r.annual_risk_usd);
          return (
            <tr key={r.row_index} className="border-t border-zinc-100">
              <td className="px-3 py-1.5 text-right tabular-nums text-zinc-600">{r.row_index}</td>
              <td className="px-3 py-1.5 font-mono text-[11px] text-zinc-700">{r.property_id ?? "—"}</td>
              <td className="px-3 py-1.5">
                <div className="max-w-[440px] truncate" title={r.resolved_address ?? r.input_address ?? ""}>
                  {r.resolved_address ?? r.input_address ?? "—"}
                </div>
                {r.status === "error" && r.error && (
                  <p className="text-[10px] italic text-red-600">{r.error}</p>
                )}
              </td>
              <td className="px-3 py-1.5 text-right tabular-nums font-semibold">
                {r.annual_risk_usd != null
                  ? fmtMoney(r.annual_risk_usd)
                  : r.status === "no_coverage"
                    ? "no NSI"
                    : "—"}
              </td>
              <td className="px-3 py-1.5">
                <span className={`rounded border px-2 py-0.5 text-[10px] font-medium ${TIER_BG[tier]}`}>
                  {TIER_LABEL[tier]}
                </span>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function Th({
  label,
  sortKey,
  active,
  dir,
  onSort,
  align = "left",
}: {
  label: string;
  sortKey: SortKey;
  active: SortKey;
  dir: SortDir;
  onSort: (key: SortKey) => void;
  align?: "left" | "right";
}) {
  const isActive = sortKey === active;
  return (
    <th
      onClick={() => onSort(sortKey)}
      className={`select-none cursor-pointer px-3 py-2 font-medium uppercase tracking-wider hover:text-zinc-900 ${
        align === "right" ? "text-right" : "text-left"
      }`}
    >
      {label}
      {isActive && <span className="ml-1 text-zinc-400">{dir === "asc" ? "↑" : "↓"}</span>}
    </th>
  );
}
