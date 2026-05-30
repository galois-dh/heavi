"use client";

import { type FormEvent, useCallback, useRef, useState } from "react";
import { TopNav } from "../../components/top-nav";
import { MapView, type MapHandle } from "../../components/map-view";
import { postFloodRisk, type FloodRiskAssessment } from "../../lib/api";

// National default camera (this module works for any US address).
const US_CENTER: [number, number] = [-98.5, 39.5];
const US_ZOOM = 3.6;

const TIER_BADGE: Record<string, string> = {
  HIGH: "bg-red-500/15 text-red-300 border-red-500/30",
  MODERATE: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  LOW: "bg-green-500/15 text-green-300 border-green-500/30",
};

function money(v: number | null | undefined): string {
  if (v == null) return "—";
  return `$${Math.round(v).toLocaleString("en-US")}`;
}

export default function FloodPage() {
  const mapRef = useRef<MapHandle>(null);
  const [address, setAddress] = useState("");
  const [report, setReport] = useState<FloodRiskAssessment | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const assess = useCallback(
    async (body: { address?: string; latitude?: number; longitude?: number }) => {
      setLoading(true);
      setError(null);
      try {
        const r = await postFloodRisk(body);
        setReport(r);
        mapRef.current?.setMarker(r.query.latitude, r.query.longitude);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Assessment failed");
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  const onSubmit = useCallback(
    (e: FormEvent) => {
      e.preventDefault();
      const a = address.trim();
      if (!a || loading) return;
      assess({ address: a });
    },
    [address, loading, assess],
  );

  const onMapPick = useCallback(
    (lat: number, lng: number) => {
      assess({ latitude: lat, longitude: lng }).catch((err) => console.error(err));
    },
    [assess],
  );

  return (
    <div className="flex h-full flex-col">
      <TopNav active="flood" />

      <div className="flex shrink-0 items-center gap-3 border-b border-zinc-800 bg-zinc-900 px-5 py-3">
        <div>
          <h1 className="text-base font-semibold tracking-tight">Flood Risk Assessment</h1>
          <p className="text-[11px] text-zinc-500">National coverage · any US address</p>
        </div>
        <form onSubmit={onSubmit} className="ml-2 flex flex-1 items-center gap-2">
          <input
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            placeholder="Enter any US address, or click the map"
            className="flex-1 rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:border-blue-500 focus:outline-none"
          />
          <button
            type="submit"
            disabled={loading || !address.trim()}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-500 disabled:opacity-40"
          >
            {loading ? "Assessing…" : "Assess"}
          </button>
        </form>
      </div>

      {error && (
        <div className="shrink-0 border-b border-red-900/50 bg-red-950/40 px-5 py-2 text-xs text-red-300">
          {error}
        </div>
      )}

      <div className="relative min-h-0 flex-1">
        <MapView ref={mapRef} onPointPick={onMapPick} center={US_CENTER} zoom={US_ZOOM} />
        {loading && (
          <div className="absolute left-1/2 top-4 -translate-x-1/2 rounded-full bg-zinc-900/90 px-4 py-1.5 text-xs text-zinc-300 shadow-lg">
            Querying FEMA NFHL, USACE NSI, and USGS 3DEP…
          </div>
        )}
        {!report && !loading && (
          <div className="pointer-events-none absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full bg-white/90 px-3 py-1 text-[11px] font-medium text-zinc-700 shadow">
            This assessment works for any US address — enter one above or click the map
          </div>
        )}
        {report && <FloodPanel report={report} onClose={() => setReport(null)} />}
      </div>
    </div>
  );
}

function FloodPanel({ report, onClose }: { report: FloodRiskAssessment; onClose: () => void }) {
  const r = report;
  const tier = r.risk_estimate.risk_tier;
  const zone = r.flood_zone.zone ?? "X / unmapped";
  return (
    <div className="absolute right-0 top-0 h-full w-[400px] overflow-y-auto border-l border-zinc-800 bg-zinc-950/95 p-5 text-zinc-100 shadow-2xl backdrop-blur">
      <div className="mb-3 flex items-start justify-between">
        <div>
          <h2 className="text-sm font-semibold">Flood Risk</h2>
          <p className="mt-0.5 max-w-[300px] text-[11px] text-zinc-500">
            {r.query.resolved_address ?? `${r.query.latitude.toFixed(5)}, ${r.query.longitude.toFixed(5)}`}
          </p>
        </div>
        <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200" aria-label="Close">
          ✕
        </button>
      </div>

      <div className="flex items-center gap-2">
        <span className={`rounded-md border px-2.5 py-1 text-xs font-semibold ${TIER_BADGE[tier] ?? ""}`}>
          {tier}
        </span>
        <span className="rounded-md border border-zinc-700 px-2.5 py-1 text-xs text-zinc-300">
          Zone {zone}
          {r.flood_zone.in_special_flood_hazard_area ? " · SFHA" : ""}
        </span>
      </div>

      <div className="mt-4 rounded-lg border border-zinc-800 bg-zinc-900 p-4">
        <p className="text-[10px] uppercase tracking-wider text-zinc-500">Annual flood risk estimate</p>
        <p className="mt-1 text-3xl font-bold tabular-nums">
          {money(r.risk_estimate.annual_risk_estimate_usd)}
          <span className="ml-1 text-sm font-normal text-zinc-500">/yr</span>
        </p>
        <p className="mt-1 text-[11px] text-zinc-500">
          1-in-{r.flood_zone.return_period_years} event ({r.flood_zone.annual_exceedance_probability} annual probability)
        </p>
      </div>

      <Section title="Depth analysis">
        <Row label="Base flood elevation" value={r.flood_zone.static_bfe_ft != null ? `${r.flood_zone.static_bfe_ft} ft` : "not published"} />
        <Row label="Ground elevation" value={r.elevation.ground_elevation_ft != null ? `${r.elevation.ground_elevation_ft} ft` : "—"} />
        <Row label="First-floor height" value={`${r.elevation.first_floor_height_ft} ft`} />
        <Row
          label="Flood depth (above 1st floor)"
          value={r.elevation.flood_depth_above_first_floor_ft != null ? `${r.elevation.flood_depth_above_first_floor_ft} ft` : "n/a"}
        />
        <p className="mt-1 text-[10px] leading-relaxed text-zinc-500">{r.elevation.depth_basis}</p>
      </Section>

      <Section title="HAZUS damage estimate">
        <Row label="Occupancy class" value={r.damage.hazus_occupancy_class} />
        <Row label="Structural damage" value={`${r.damage.structural_damage_pct}% · ${money(r.damage.structural_loss_usd)}`} />
        <Row label="Contents damage" value={`${r.damage.contents_damage_pct}% · ${money(r.damage.contents_loss_usd)}`} />
        <Row label="Total event loss" value={money(r.damage.total_loss_usd)} strong />
      </Section>

      {r.structure && (
        <Section title="Structure (USACE NSI)">
          <Row label="Replacement value" value={money(r.structure.replacement_value_structure_usd)} />
          <Row label="Contents value" value={money(r.structure.replacement_value_contents_usd)} />
          <Row label="Stories / foundation" value={`${r.structure.num_stories ?? "—"} · ${r.structure.foundation_type ?? "—"}`} />
        </Section>
      )}

      <div className="mt-4 rounded-md border border-zinc-800 bg-zinc-900 p-3 text-[11px] leading-relaxed text-zinc-300">
        {r.natural_language_summary}
      </div>
      <p className="mt-3 text-[10px] leading-relaxed text-zinc-500">
        FEMA HAZUS depth-damage methodology with NFHL hazard data, USACE NSI exposure, and USGS 3DEP elevation.
      </p>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-4">
      <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">{title}</p>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function Row({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="flex items-baseline justify-between text-xs">
      <span className="text-zinc-500">{label}</span>
      <span className={`tabular-nums ${strong ? "font-semibold text-zinc-100" : "text-zinc-300"}`}>{value}</span>
    </div>
  );
}
