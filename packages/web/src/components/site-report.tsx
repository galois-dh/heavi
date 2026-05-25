"use client";

import {
  type FactorKey,
  type NearbyFeature,
  type SiteReport,
} from "../lib/api";
import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";

const FACTOR_LABELS: Record<FactorKey, string> = {
  flood_risk: "Flood Risk",
  demographics: "Demographics",
  transit_access: "Transit Access",
  environmental: "Environmental",
  competition: "Competition",
};

const FACTOR_ORDER: FactorKey[] = [
  "flood_risk",
  "demographics",
  "transit_access",
  "environmental",
  "competition",
];

function scoreColor(score: number): string {
  if (score >= 70) return "#16a34a"; // green-600
  if (score >= 50) return "#ca8a04"; // yellow-600
  return "#dc2626"; // red-600
}

function scoreLabel(score: number): string {
  if (score >= 70) return "Strong";
  if (score >= 50) return "Moderate";
  return "Weak";
}

interface Props {
  report: SiteReport;
  onClose: () => void;
  onExport: (el: HTMLElement) => Promise<void>;
  exporting: boolean;
}

export function SiteReportPanel({ report, onClose, onExport, exporting }: Props) {
  const cardRef = useRef<HTMLDivElement>(null);

  return (
    <div className="absolute inset-y-0 right-0 z-20 flex w-[520px] flex-col border-l border-zinc-200 bg-white text-zinc-900 shadow-2xl">
      {/* Toolbar — excluded from PDF capture */}
      <div className="flex items-center justify-between border-b border-zinc-200 bg-zinc-50 px-5 py-2.5">
        <span className="text-xs font-medium uppercase tracking-wider text-zinc-500">
          Site Report
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={() => cardRef.current && onExport(cardRef.current)}
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

      {/* Report body — this div is what gets rasterized */}
      <div ref={cardRef} className="flex-1 overflow-y-auto bg-white px-6 py-5">
        <ReportHeader report={report} />
        <ScoreSummary report={report} />
        <FactorBars report={report} />
        <NearbySection report={report} />
        <MiniMap report={report} />
        <ReportFooter report={report} />
      </div>
    </div>
  );
}

function ReportHeader({ report }: { report: SiteReport }) {
  return (
    <div className="mb-5 border-b border-zinc-200 pb-4">
      <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">Property</p>
      <h2 className="mt-1 text-lg font-semibold leading-snug text-zinc-900">
        {report.address}
      </h2>
      <p className="mt-1 text-xs text-zinc-500">
        {report.location.latitude.toFixed(5)}, {report.location.longitude.toFixed(5)} · {" "}
        {(report.radius_meters / 1609).toFixed(2)} mi analysis radius
      </p>
    </div>
  );
}

function ScoreSummary({ report }: { report: SiteReport }) {
  const score = report.composite_score;
  const color = scoreColor(score);
  return (
    <div className="mb-6 flex items-start gap-5">
      <div
        className="flex h-24 w-24 shrink-0 items-center justify-center rounded-xl text-3xl font-bold text-white"
        style={{ backgroundColor: color }}
      >
        {score}
      </div>
      <div className="pt-1">
        <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">
          Composite Score
        </p>
        <p className="mt-0.5 text-lg font-semibold" style={{ color }}>
          {scoreLabel(score)} suitability
        </p>
        <p className="mt-2 text-xs leading-relaxed text-zinc-600">
          Weighted average of 5 factors. Scores range 0–100 with thresholds at 50 and 70.
        </p>
      </div>
    </div>
  );
}

function FactorBars({ report }: { report: SiteReport }) {
  return (
    <div className="mb-6">
      <h3 className="mb-2.5 text-xs font-semibold uppercase tracking-wider text-zinc-500">
        Factor Breakdown
      </h3>
      <div className="space-y-2.5">
        {FACTOR_ORDER.map((key) => {
          const score = report.factors[key];
          const color = scoreColor(score);
          return (
            <div key={key}>
              <div className="mb-1 flex items-baseline justify-between text-xs">
                <span className="font-medium text-zinc-700">{FACTOR_LABELS[key]}</span>
                <span className="tabular-nums font-semibold" style={{ color }}>
                  {score}
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-zinc-100">
                <div
                  className="h-full rounded-full transition-all"
                  style={{ width: `${score}%`, backgroundColor: color }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function NearbySection({ report }: { report: SiteReport }) {
  const sections: { title: string; items: NearbyFeature[]; nameKey: string }[] = [
    { title: "Schools", items: report.nearby.schools, nameKey: "name" },
    { title: "Transit Stops", items: report.nearby.transit_stops, nameKey: "stop_name" },
    { title: "EPA Facilities", items: report.nearby.epa_facilities, nameKey: "facility_name" },
  ];

  return (
    <div className="mb-6">
      <h3 className="mb-2.5 text-xs font-semibold uppercase tracking-wider text-zinc-500">
        Nearby
      </h3>
      <div className="space-y-3">
        {sections.map((s) => (
          <div key={s.title}>
            <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
              {s.title}
            </p>
            {s.items.length === 0 ? (
              <p className="text-xs italic text-zinc-400">None within radius</p>
            ) : (
              <ul className="space-y-0.5 text-xs">
                {s.items.map((item, i) => {
                  const name =
                    (item.properties[s.nameKey] as string) ||
                    (item.properties.name as string) ||
                    "(unnamed)";
                  return (
                    <li key={i} className="flex items-baseline justify-between gap-3">
                      <span className="truncate text-zinc-800">{name}</span>
                      <span className="tabular-nums text-zinc-500">
                        {formatDistance(item.distance_m)}
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function formatDistance(m: number): string {
  if (m < 1000) return `${m} m`;
  return `${(m / 1609).toFixed(2)} mi`;
}

function MiniMap({ report }: { report: SiteReport }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const { latitude: lat, longitude: lng } = report.location;

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
      zoom: 12.5,
      interactive: false,
      canvasContextAttributes: { preserveDrawingBuffer: true },
    });

    map.on("load", () => {
      map.addSource("radius", {
        type: "geojson",
        data: circlePolygon(lat, lng, report.radius_meters),
      });
      map.addLayer({
        id: "radius-fill",
        type: "fill",
        source: "radius",
        paint: { "fill-color": "#f97316", "fill-opacity": 0.12 },
      });
      map.addLayer({
        id: "radius-line",
        type: "line",
        source: "radius",
        paint: { "line-color": "#f97316", "line-width": 1.5, "line-dasharray": [2, 2] },
      });
      map.addSource("point", {
        type: "geojson",
        data: {
          type: "Feature",
          geometry: { type: "Point", coordinates: [lng, lat] },
          properties: {},
        },
      });
      map.addLayer({
        id: "point",
        type: "circle",
        source: "point",
        paint: {
          "circle-radius": 7,
          "circle-color": "#f97316",
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 2.5,
        },
      });
    });

    return () => {
      map.remove();
    };
  }, [report.location.latitude, report.location.longitude, report.radius_meters]);

  return (
    <div className="mb-6">
      <h3 className="mb-2.5 text-xs font-semibold uppercase tracking-wider text-zinc-500">
        Site &amp; 1-mile Radius
      </h3>
      <div
        ref={ref}
        className="h-[220px] w-full overflow-hidden rounded-lg border border-zinc-200"
      />
    </div>
  );
}

function ReportFooter({ report }: { report: SiteReport }) {
  const c = report.counts;
  const chip = (label: string, value: string, on: boolean) => (
    <span
      className={`rounded-full px-2.5 py-0.5 text-[10px] font-medium ${
        on ? "bg-red-50 text-red-700" : "bg-zinc-100 text-zinc-600"
      }`}
    >
      {label}: {value}
    </span>
  );
  return (
    <div className="border-t border-zinc-200 pt-3 text-[10px] text-zinc-500">
      <div className="mb-2 flex flex-wrap gap-1.5">
        {chip("Flood zone", c.in_flood_zone ? "Yes" : "No", c.in_flood_zone)}
        {chip("Fire hazard", c.in_fire_hazard ? "Yes" : "No", c.in_fire_hazard)}
        {chip("Transit stops", String(c.transit_stops), false)}
        {chip("POIs", c.pois.toLocaleString(), false)}
      </div>
      <p>Generated by Heavi · Data: FEMA, NCES, US Census, EPA, Overture, CalFire</p>
    </div>
  );
}

function circlePolygon(lat: number, lng: number, radiusM: number): GeoJSON.Feature {
  const coords: [number, number][] = [];
  const R = 6378137;
  const segments = 64;
  for (let i = 0; i <= segments; i++) {
    const t = (i / segments) * 2 * Math.PI;
    const dLat = ((radiusM / R) * (180 / Math.PI)) * Math.sin(t);
    const dLng =
      ((radiusM / R) * (180 / Math.PI)) * Math.cos(t) /
      Math.cos((lat * Math.PI) / 180);
    coords.push([lng + dLng, lat + dLat]);
  }
  return {
    type: "Feature",
    geometry: { type: "Polygon", coordinates: [coords] },
    properties: {},
  };
}

export function siteKey(r: SiteReport): string {
  return `${r.location.latitude.toFixed(5)},${r.location.longitude.toFixed(5)}`;
}
