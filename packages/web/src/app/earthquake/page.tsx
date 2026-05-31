"use client";

import { type FormEvent, useCallback, useRef, useState } from "react";
import { TopNav } from "../../components/top-nav";
import { MapView, type MapHandle } from "../../components/map-view";
import { postEarthquakeRisk, type EarthquakeRiskAssessment } from "../../lib/api";

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

function pct(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

export default function EarthquakePage() {
  const mapRef = useRef<MapHandle>(null);
  const [address, setAddress] = useState("");
  const [report, setReport] = useState<EarthquakeRiskAssessment | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const assess = useCallback(
    async (body: { address?: string; latitude?: number; longitude?: number }) => {
      setLoading(true);
      setError(null);
      try {
        const r = await postEarthquakeRisk(body);
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
      <TopNav active="earthquake" />

      <div className="flex shrink-0 items-center gap-3 border-b border-zinc-800 bg-zinc-900 px-5 py-3">
        <div>
          <h1 className="text-base font-semibold tracking-tight">Earthquake Risk Assessment</h1>
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
            Querying USGS Design Maps, 3DEP, and USACE NSI…
          </div>
        )}
        {!report && !loading && (
          <div className="pointer-events-none absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full bg-white/90 px-3 py-1 text-[11px] font-medium text-zinc-700 shadow">
            This assessment works for any US address — enter one above or click the map
          </div>
        )}
        {report && <EarthquakePanel report={report} onClose={() => setReport(null)} />}
      </div>
    </div>
  );
}

function EarthquakePanel({
  report,
  onClose,
}: {
  report: EarthquakeRiskAssessment;
  onClose: () => void;
}) {
  const r = report;
  const tier = r.risk_estimate.risk_tier;
  return (
    <div className="absolute right-0 top-0 h-full w-[400px] overflow-y-auto border-l border-zinc-800 bg-zinc-950/95 p-5 text-zinc-100 shadow-2xl backdrop-blur">
      <div className="mb-3 flex items-start justify-between">
        <div>
          <h2 className="text-sm font-semibold">Earthquake Risk</h2>
          <p className="mt-0.5 max-w-[300px] text-[11px] text-zinc-500">
            {r.query.resolved_address ??
              `${r.query.latitude.toFixed(5)}, ${r.query.longitude.toFixed(5)}`}
          </p>
        </div>
        <button
          onClick={onClose}
          className="text-zinc-500 hover:text-zinc-200"
          aria-label="Close"
        >
          ✕
        </button>
      </div>

      <div className="flex items-center gap-2">
        <span
          className={`rounded-md border px-2.5 py-1 text-xs font-semibold ${TIER_BADGE[tier] ?? ""}`}
        >
          {tier}
        </span>
        <span className="rounded-md border border-zinc-700 px-2.5 py-1 text-xs text-zinc-300">
          Site Class {r.site.site_class} · VS30 {r.site.vs30_m_per_s} m/s
        </span>
      </div>

      <div className="mt-4 rounded-lg border border-zinc-800 bg-zinc-900 p-4">
        <p className="text-[10px] uppercase tracking-wider text-zinc-500">
          Annual earthquake risk estimate
        </p>
        <p className="mt-1 text-3xl font-bold tabular-nums">
          {money(r.risk_estimate.annual_risk_estimate_usd)}
          <span className="ml-1 text-sm font-normal text-zinc-500">/yr</span>
        </p>
        <p className="mt-1 text-[11px] text-zinc-500">
          2% probability of exceedance in 50 years (≈ {r.hazard.return_period_years}-yr return period)
        </p>
      </div>

      <Section title="Ground motion">
        <Row label="Bedrock PGA (Class B)" value={`${r.hazard.bedrock_pga_g.toFixed(2)} g`} />
        <Row
          label="Site amplification"
          value={`${r.site.amplification_factor.toFixed(1)}× (${r.site.site_description})`}
        />
        <Row label="Adjusted PGA" value={`${r.hazard.adjusted_pga_g.toFixed(2)} g`} strong />
        <p className="mt-1 text-[10px] leading-relaxed text-zinc-500">{r.site.slope_basis}</p>
      </Section>

      <Section title="HAZUS damage state probabilities">
        <Row label="Slight" value={pct(r.damage_state_probabilities.exclusive.slight)} />
        <Row label="Moderate" value={pct(r.damage_state_probabilities.exclusive.moderate)} />
        <Row label="Extensive" value={pct(r.damage_state_probabilities.exclusive.extensive)} />
        <Row label="Complete" value={pct(r.damage_state_probabilities.exclusive.complete)} />
        <Row
          label="Expected damage ratio"
          value={pct(r.damage_state_probabilities.expected_damage_ratio)}
          strong
        />
      </Section>

      <Section title="Loss at hazard level">
        <Row label="Structural" value={money(r.risk_estimate.structural_loss_at_hazard_usd)} />
        <Row label="Contents" value={money(r.risk_estimate.contents_loss_at_hazard_usd)} />
        <Row label="Total event loss" value={money(r.risk_estimate.total_loss_at_hazard_usd)} strong />
      </Section>

      {r.structure && (
        <Section title="Structure (USACE NSI)">
          <Row
            label="HAZUS type / code level"
            value={`${r.structure.hazus_building_type} · ${r.structure.code_level}-code`}
          />
          <Row label="Year built" value={r.structure.median_year_built?.toString() ?? "—"} />
          <Row label="Stories" value={r.structure.num_stories?.toString() ?? "—"} />
          <Row
            label="Replacement value"
            value={money(r.structure.replacement_value_structure_usd)}
          />
          <Row label="Contents value" value={money(r.structure.replacement_value_contents_usd)} />
        </Section>
      )}

      <div className="mt-4 rounded-md border border-zinc-800 bg-zinc-900 p-3 text-[11px] leading-relaxed text-zinc-300">
        {r.natural_language_summary}
      </div>
      <p className="mt-3 text-[10px] leading-relaxed text-zinc-500">
        USGS ASCE 7-22 Design Maps + Wald & Allen (2007) slope-VS30 site amplification + HAZUS Earthquake Model fragility curves.
      </p>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-4">
      <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
        {title}
      </p>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function Row({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="flex items-baseline justify-between text-xs">
      <span className="text-zinc-500">{label}</span>
      <span
        className={`tabular-nums ${strong ? "font-semibold text-zinc-100" : "text-zinc-300"}`}
      >
        {value}
      </span>
    </div>
  );
}
