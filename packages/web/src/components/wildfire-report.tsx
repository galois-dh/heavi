"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import type { WildfireRiskAssessment } from "../lib/api";

// ─── Risk-tier thresholds ────────────────────────────────────────────────
//   $0–$50     Low Risk      green
//   $50–$500   Moderate Risk amber
//   >$500      High Risk     red
// Match the product spec; thresholds are dollar EALs.
function riskTier(annualUsd: number): {
  label: string;
  color: string;
  bg: string;
  ring: string;
} {
  if (annualUsd > 500)
    return { label: "High Risk", color: "#b91c1c", bg: "#fee2e2", ring: "#dc2626" };
  if (annualUsd >= 50)
    return { label: "Moderate Risk", color: "#b45309", bg: "#fef3c7", ring: "#f59e0b" };
  return { label: "Low Risk", color: "#15803d", bg: "#dcfce7", ring: "#16a34a" };
}

// Color a per-factor bar by its fill ratio (0..1). 0 = safe, 1 = max risk.
function barColor(fraction: number): string {
  if (fraction >= 0.7) return "#dc2626";
  if (fraction >= 0.3) return "#f59e0b";
  return "#16a34a";
}

interface Props {
  report: WildfireRiskAssessment;
  onClose: () => void;
  onExport: (el: HTMLElement, filename: string) => Promise<void>;
  exporting: boolean;
}

export function WildfireReportPanel({ report, onClose, onExport, exporting }: Props) {
  const cardRef = useRef<HTMLDivElement>(null);

  // No NSI structure within the search radius — explain rather than render
  // an empty assessment with $0 EAL (which is technically true but useless).
  if (!report.match || !report.features || !report.risk_estimate || !report.property_vulnerability) {
    return <NoCoveragePanel report={report} onClose={onClose} />;
  }

  const eal =
    report.risk_estimate.annual_risk_estimate_usd_persisted ??
    report.risk_estimate.annual_risk_estimate_usd;
  const tier = riskTier(eal);
  const filename = `wildfire-risk-${wildfireKey(report)}.pdf`;

  return (
    <div className="absolute inset-y-0 right-0 z-20 flex w-[520px] flex-col border-l border-zinc-200 bg-white text-zinc-900 shadow-2xl">
      <div className="flex items-center justify-between border-b border-zinc-200 bg-zinc-50 px-5 py-2.5">
        <span className="text-xs font-medium uppercase tracking-wider text-zinc-500">
          Wildfire Risk Assessment
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={() => cardRef.current && onExport(cardRef.current, filename)}
            disabled={exporting}
            className="rounded-md bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-zinc-800 disabled:opacity-50"
          >
            {exporting ? "Exporting..." : "Export PDF"}
          </button>
          <button
            onClick={onClose}
            className="rounded-md border border-zinc-300 px-2 py-1.5 text-xs text-zinc-600 transition hover:bg-zinc-100"
            aria-label="Close"
          >
            ✕
          </button>
        </div>
      </div>

      <div ref={cardRef} className="flex-1 overflow-y-auto bg-white px-6 py-5">
        <ReportHeader report={report} />
        <RiskSummary eal={eal} tier={tier} />
        <RiskFactors report={report} />
        <PropertyDetails report={report} />
        <MiniMap lat={report.match.nsi_location.latitude} lng={report.match.nsi_location.longitude} />
        <MethodologySection report={report} />
        <ReportFooter />
      </div>
    </div>
  );
}

function ReportHeader({ report }: { report: WildfireRiskAssessment }) {
  const address =
    report.query.resolved_address ||
    report.query.address ||
    `${report.query.latitude.toFixed(5)}, ${report.query.longitude.toFixed(5)}`;
  return (
    <div className="mb-5 border-b border-zinc-200 pb-4">
      <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">Property</p>
      <h2 className="mt-1 text-lg font-semibold leading-snug text-zinc-900">{address}</h2>
      <p className="mt-1 text-xs text-zinc-500">
        {report.query.latitude.toFixed(5)}, {report.query.longitude.toFixed(5)} ·{" "}
        Sonoma County · NSI fd_id {report.match?.fd_id}
        {report.match && ` · ${report.match.match_distance_m.toFixed(0)} m from click`}
      </p>
    </div>
  );
}

function RiskSummary({
  eal,
  tier,
}: {
  eal: number;
  tier: ReturnType<typeof riskTier>;
}) {
  return (
    <div className="mb-6 flex items-start gap-5">
      <div
        className="flex h-24 w-24 shrink-0 flex-col items-center justify-center rounded-xl text-center text-[11px] font-bold uppercase leading-tight tracking-wide text-white"
        style={{ backgroundColor: tier.ring }}
      >
        <span>{tier.label.split(" ")[0]}</span>
        <span>{tier.label.split(" ")[1]}</span>
      </div>
      <div className="pt-1">
        <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">
          Annual Risk Estimate
        </p>
        <p className="mt-0.5 text-3xl font-bold tabular-nums" style={{ color: tier.color }}>
          ${eal < 1 ? eal.toFixed(2) : eal.toLocaleString(undefined, { maximumFractionDigits: 0 })}
          <span className="ml-1 text-base font-medium text-zinc-500">/year</span>
        </p>
        <p className="mt-2 text-xs leading-relaxed text-zinc-600">
          Expected destruction-driven loss this year, given the property's
          location, vegetation context, and structural exposure.
        </p>
      </div>
    </div>
  );
}

// Per-factor risk scales. Each maps the feature value to a 0–1 bar fill
// representing intuitive risk (1 = high risk, 0 = safe). Direction matches
// natural reading even where the calibrated coefficient is counter-intuitive
// — these bars communicate the feature value, not the in-model β contribution.
interface FactorRow {
  label: string;
  display: string;
  fraction: number;
  description: string;
}

function buildFactors(report: WildfireRiskAssessment): FactorRow[] {
  const f = report.features!;
  const clamp = (x: number) => Math.max(0, Math.min(1, x));
  return [
    {
      label: "Wildfire Likelihood",
      display: f.wildfire_likelihood.toFixed(4),
      fraction: clamp(f.wildfire_likelihood / 0.01),
      description: "Annual probability the parcel burns (USFS WRC FSim).",
    },
    {
      label: "Distance to Fuel",
      display: `${f.distance_to_fuel_m.toFixed(0)} m`,
      // Closer to fuel = higher risk. Saturate the "safe" end at 500 m.
      fraction: clamp(1 - f.distance_to_fuel_m / 500),
      description: "Metres to the nearest burnable LANDFIRE fuel cell.",
    },
    {
      label: "Defensible Space (Canopy 100 m)",
      display: `${f.canopy_cover_100m.toFixed(0)}%`,
      // More canopy near the structure = less defensible space = higher risk.
      // Saturate at 50% canopy (very heavily forested).
      fraction: clamp(f.canopy_cover_100m / 50),
      description: "Mean tree-canopy cover within 100 m of the property.",
    },
    {
      label: "Terrain Slope",
      display: `${f.slope_degrees.toFixed(1)}°`,
      // Fire spreads faster uphill. Saturate at 30°.
      fraction: clamp(f.slope_degrees / 30),
      description: "Local slope from 3DEP DEM. Steeper = faster spread.",
    },
  ];
}

function RiskFactors({ report }: { report: WildfireRiskAssessment }) {
  const factors = buildFactors(report);
  const propertyType =
    report.features!.is_res1 === 1
      ? "Residential (single-family)"
      : report.match?.occupancy_type
        ? `Commercial / Other (${report.match.occupancy_type})`
        : "Non-residential";

  return (
    <div className="mb-6">
      <h3 className="mb-2.5 text-xs font-semibold uppercase tracking-wider text-zinc-500">
        Key Risk Factors
      </h3>
      <div className="space-y-3">
        {factors.map((row) => {
          const color = barColor(row.fraction);
          return (
            <div key={row.label}>
              <div className="mb-1 flex items-baseline justify-between text-xs">
                <span className="font-medium text-zinc-700">{row.label}</span>
                <span className="tabular-nums font-semibold" style={{ color }}>
                  {row.display}
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-zinc-100">
                <div
                  className="h-full rounded-full transition-all"
                  style={{ width: `${row.fraction * 100}%`, backgroundColor: color }}
                />
              </div>
            </div>
          );
        })}
        <div className="flex items-baseline justify-between pt-1 text-xs">
          <span className="font-medium text-zinc-700">Property Type</span>
          <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-medium text-zinc-700">
            {propertyType}
          </span>
        </div>
      </div>
    </div>
  );
}

function PropertyDetails({ report }: { report: WildfireRiskAssessment }) {
  const v = report.property_vulnerability!;
  const l = report.risk_estimate!;
  const replacement = report.match!.replacement_value_usd;
  const rp = l.return_period_years;
  return (
    <div className="mb-6">
      <h3 className="mb-2.5 text-xs font-semibold uppercase tracking-wider text-zinc-500">
        Property Details
      </h3>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
        <Detail label="Replacement Value" value={`$${replacement.toLocaleString(undefined, { maximumFractionDigits: 0 })}`} />
        <Detail label="Damage Probability" value={`${(v.damage_probability * 100).toFixed(1)}%`} />
        <Detail
          label="Return Period"
          value={rp ? `${rp.toLocaleString()} years` : "—"}
        />
        <Detail
          label="Above Optimal Threshold"
          value={v.exceeds_risk_threshold ? "Yes" : "No"}
        />
      </dl>
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wider text-zinc-500">{label}</dt>
      <dd className="mt-0.5 text-sm font-semibold tabular-nums text-zinc-900">{value}</dd>
    </div>
  );
}

function MethodologySection({ report }: { report: WildfireRiskAssessment }) {
  const [open, setOpen] = useState(false);
  const v = report.property_vulnerability!;
  return (
    <div className="mb-6 rounded-lg border border-zinc-200 bg-zinc-50 px-4 py-2.5">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between text-xs font-semibold uppercase tracking-wider text-zinc-600 hover:text-zinc-900"
      >
        <span>Methodology</span>
        <span className="font-sans text-[10px] text-zinc-500">{open ? "Hide" : "Show"}</span>
      </button>
      {open && (
        <div className="mt-3 space-y-2 text-xs leading-relaxed text-zinc-700">
          <p>
            Validated against CAL FIRE damage inspections (AUC:{" "}
            <span className="tabular-nums font-semibold">{v.validation_auc_roc.toFixed(2)}</span>) for
            five Sonoma fires (Tubbs, Nuns, Kincade, Glass, LNU Lightning Complex).
          </p>
          <p>
            <span className="text-zinc-500">Data sources:</span> USFS WRC (burn probability),
            LANDFIRE 2022 (fuel + canopy), USGS 3DEP (terrain), USACE NSI (exposure).
          </p>
          <p className="break-all">
            <span className="text-zinc-500">Methodology hash:</span>{" "}
            <code className="rounded bg-white px-1 py-0.5 text-[10px] tabular-nums">
              {v.methodology_hash.slice(0, 16)}…
            </code>
          </p>
          {report.methodology_note && (
            <p className="text-[11px] italic text-zinc-600">{report.methodology_note}</p>
          )}
        </div>
      )}
    </div>
  );
}

function MiniMap({ lat, lng }: { lat: number; lng: number }) {
  const ref = useRef<HTMLDivElement>(null);
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
      center: [lng, lat],
      zoom: 13,
      interactive: false,
      canvasContextAttributes: { preserveDrawingBuffer: true },
    });
    map.on("load", () => {
      map.addSource("point", {
        type: "geojson",
        data: { type: "Feature", geometry: { type: "Point", coordinates: [lng, lat] }, properties: {} },
      });
      map.addLayer({
        id: "point",
        type: "circle",
        source: "point",
        paint: {
          "circle-radius": 8,
          "circle-color": "#dc2626",
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 2.5,
        },
      });
    });
    return () => {
      map.remove();
    };
  }, [lat, lng]);
  return (
    <div className="mb-6">
      <h3 className="mb-2.5 text-xs font-semibold uppercase tracking-wider text-zinc-500">
        Location
      </h3>
      <div ref={ref} className="h-[200px] w-full overflow-hidden rounded-lg border border-zinc-200" />
    </div>
  );
}

function ReportFooter() {
  return (
    <div className="border-t border-zinc-200 pt-3 text-[10px] text-zinc-500">
      <p>Generated by Heavi · Sonoma County wildfire risk model v0.1 · For investment, lending, and portfolio decision support.</p>
    </div>
  );
}

function NoCoveragePanel({
  report,
  onClose,
}: {
  report: WildfireRiskAssessment;
  onClose: () => void;
}) {
  return (
    <div className="absolute inset-y-0 right-0 z-20 flex w-[520px] flex-col border-l border-zinc-200 bg-white text-zinc-900 shadow-2xl">
      <div className="flex items-center justify-between border-b border-zinc-200 bg-zinc-50 px-5 py-2.5">
        <span className="text-xs font-medium uppercase tracking-wider text-zinc-500">
          Wildfire Risk Assessment
        </span>
        <button
          onClick={onClose}
          className="rounded-md border border-zinc-300 px-2 py-1.5 text-xs text-zinc-600 transition hover:bg-zinc-100"
          aria-label="Close"
        >
          ✕
        </button>
      </div>
      <div className="flex-1 overflow-y-auto bg-white px-6 py-5">
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900">
          <p className="font-semibold">No NSI structure within 500 m</p>
          <p className="mt-1 leading-relaxed">
            {report.message ??
              "The click point doesn't have a USACE NSI v2 structure inside the default search radius. Wildfire risk is only computed against catalogued structures."}
          </p>
        </div>
      </div>
    </div>
  );
}

export function wildfireKey(r: WildfireRiskAssessment): string {
  return `${r.query.latitude.toFixed(5)},${r.query.longitude.toFixed(5)}`;
}
