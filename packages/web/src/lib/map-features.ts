import type { ConstraintDescriptor } from "../components/heavi-map";
import type { SolarScoreV2, HazardScoreV2, TradeAreaScoreV2 } from "./api";

/** A scored map feature carries { fid, score (0-1), label } for color + selection. */
export function pointFeature(
  fid: string, lng: number, lat: number, score: number, label: string,
  extra: Record<string, unknown> = {},
): GeoJSON.Feature {
  return {
    type: "Feature",
    geometry: { type: "Point", coordinates: [lng, lat] },
    properties: { fid, score, label, ...extra },
  };
}

export function solarFeature(fid: string, r: SolarScoreV2): GeoJSON.Feature {
  return pointFeature(fid, r.query.longitude, r.query.latitude, r.score ?? 0, r.rating);
}

export function hazardFeature(fid: string, r: HazardScoreV2): GeoJSON.Feature {
  // Color by the worse of the two assessable peril tiers; gray only if BOTH
  // perils are CANNOT ASSESS (otherwise show the known risk).
  const order: Record<string, number> = { HIGH: 3, MODERATE: 2, LOW: 1 };
  const wf = r.wildfire.risk_tier ?? "";
  const fl = r.flood.risk_tier ?? "";
  const wfCa = r.wildfire.cannot_assess || wf === "CANNOT ASSESS";
  const flCa = r.flood.cannot_assess || fl === "CANNOT ASSESS";
  let label = "LOW";
  if (wfCa && flCa) label = "CANNOT ASSESS";
  else label = (order[wf] ?? 0) >= (order[fl] ?? 0) ? (wfCa ? fl : wf) : (flCa ? wf : fl);
  return pointFeature(fid, r.query.longitude, r.query.latitude, 0, label || "LOW");
}

export function tradeAreaFeature(fid: string, r: TradeAreaScoreV2): GeoJSON.Feature {
  const q = r.query as { latitude: number; longitude: number };
  return pointFeature(fid, q.longitude, q.latitude, r.suitability_score ?? 0, r.suitability_rating);
}

export function fc(features: GeoJSON.Feature[]): GeoJSON.FeatureCollection {
  return { type: "FeatureCollection", features };
}

// ─── Constraint descriptors per product (Map Interface Spec) ────────────────

export const ENERGY_CONSTRAINTS: ConstraintDescriptor[] = [
  { id: "padus", name: "Protected Areas (PAD-US)", category: "Environmental", geomKind: "fill", color: "#f87171", defaultVisible: false },
  { id: "nwi", name: "Wetlands (NWI)", category: "Environmental", geomKind: "fill", color: "#2dd4bf", defaultVisible: false },
  { id: "transmission", name: "Transmission Lines", category: "Infrastructure", geomKind: "line", color: "#eab308", defaultVisible: false },
  { id: "substations", name: "Substations", category: "Infrastructure", geomKind: "circle", color: "#fb923c", defaultVisible: false },
  { id: "eia_solar", name: "EIA Solar Installations", category: "Infrastructure", geomKind: "circle", color: "#22c55e", defaultVisible: true },
  { id: "interconnection_queue", name: "Interconnection Queue", category: "Infrastructure", geomKind: "circle", color: "#a855f7", defaultVisible: false },
];

export const HAZARD_CONSTRAINTS: ConstraintDescriptor[] = [
  { id: "nfhl", name: "FEMA Flood Zones", category: "Hazard", geomKind: "fill", color: "#3b82f6", defaultVisible: false },
  { id: "padus", name: "Protected Areas (PAD-US)", category: "Environmental", geomKind: "fill", color: "#f87171", defaultVisible: false },
];

export const LOCATIONS_CONSTRAINTS: ConstraintDescriptor[] = [
  { id: "nfhl", name: "FEMA Flood Zones", category: "Hazard", geomKind: "fill", color: "#3b82f6", defaultVisible: false },
];
