"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";

// OpenFreeMap dark vector style — free, no API key (Map Interface Spec).
const BASEMAP = "https://tiles.openfreemap.org/styles/dark";
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type ScoreScale = "suitability" | "risk" | "tradearea";

/** Toggleable constraint layer (loaded on-demand from /constraints/{id}). */
export interface ConstraintDescriptor {
  id: string;
  name: string;
  category: "Environmental" | "Infrastructure" | "Hazard" | "Administrative";
  geomKind: "fill" | "line" | "circle";
  color: string;
  defaultVisible?: boolean;
}

/** Extra GeoJSON overlay drawn beneath the scored layer (isochrones, POIs). */
export interface MapOverlay {
  id: string;
  geojson: GeoJSON.FeatureCollection;
  type: "fill" | "line" | "circle";
  paint: Record<string, unknown>;
}

interface HeaviMapProps {
  center: [number, number];
  zoom: number;
  scoredFeatures?: GeoJSON.FeatureCollection;
  scoreColorScale?: ScoreScale;
  constraints?: ConstraintDescriptor[];
  overlays?: MapOverlay[];
  onFeatureClick?: (feature: GeoJSON.Feature) => void;
  selectedFid?: string | number | null;
  fitOnUpdate?: boolean;
}

const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

// CANNOT ASSESS is a distinct neutral gray (not green/red) across all scales.
const CANNOT_ASSESS_COLOR = "#9ca3af";

// Circle-color expression per color scale. Features carry { score, label }.
function colorExpr(scale: ScoreScale): maplibregl.ExpressionSpecification {
  if (scale === "risk") {
    return [
      "match", ["upcase", ["to-string", ["coalesce", ["get", "label"], ""]]],
      "CANNOT ASSESS", CANNOT_ASSESS_COLOR,
      "HIGH", "#ef4444", "MODERATE", "#eab308", "LOW", "#22c55e",
      "#64748b",
    ];
  }
  if (scale === "tradearea") {
    return [
      "match", ["to-string", ["coalesce", ["get", "label"], ""]],
      "CANNOT ASSESS", CANNOT_ASSESS_COLOR,
      "Strong", "#06b6d4", "Moderate", "#8b5cf6", "Weak", "#64748b",
      "#64748b",
    ];
  }
  // suitability (default): CANNOT ASSESS / Excluded → gray, else step on score.
  return [
    "case",
    ["==", ["to-string", ["coalesce", ["get", "label"], ""]], "CANNOT ASSESS"], CANNOT_ASSESS_COLOR,
    ["==", ["to-string", ["coalesce", ["get", "label"], ""]], "Excluded"], "#6b7280",
    ["step", ["coalesce", ["get", "score"], 0], "#ef4444", 0.4, "#eab308", 0.7, "#22c55e"],
  ];
}

const LEGENDS: Record<ScoreScale, [string, string][]> = {
  suitability: [["#22c55e", "High ≥0.70"], ["#eab308", "Moderate"], ["#ef4444", "Low <0.40"], ["#6b7280", "Excluded"]],
  risk: [["#ef4444", "High risk"], ["#eab308", "Moderate"], ["#22c55e", "Low risk"]],
  tradearea: [["#06b6d4", "Strong"], ["#8b5cf6", "Moderate"], ["#64748b", "Weak"]],
};

export function HeaviMap({
  center, zoom, scoredFeatures, scoreColorScale = "suitability",
  constraints = [], overlays = [], onFeatureClick, selectedFid, fitOnUpdate = true,
}: HeaviMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const loadedRef = useRef(false);
  const onClickRef = useRef(onFeatureClick);
  onClickRef.current = onFeatureClick;
  const scaleRef = useRef(scoreColorScale);
  scaleRef.current = scoreColorScale;

  const [ready, setReady] = useState(false);
  const [enabled, setEnabled] = useState<Set<string>>(
    () => new Set(constraints.filter((c) => c.defaultVisible).map((c) => c.id)),
  );
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;
  const constraintsRef = useRef(constraints);
  constraintsRef.current = constraints;

  // ── Create the map once ──────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: BASEMAP,
      center,
      zoom,
      attributionControl: { compact: true },
      pitchWithRotate: false,
      dragRotate: false,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "imperial" }), "bottom-left");
    mapRef.current = map;

    map.on("load", () => {
      // Scored features source + layers.
      map.addSource("scored", { type: "geojson", data: scoredFeatures ?? EMPTY });
      map.addLayer({
        id: "scored-circles",
        type: "circle",
        source: "scored",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 6, 6, 14, 9],
          "circle-color": colorExpr(scaleRef.current),
          "circle-stroke-color": "#0b0b0c",
          "circle-stroke-width": 1.5,
          "circle-opacity": 0.95,
        },
      });
      // Selection highlight ring (filtered to the selected fid).
      map.addLayer({
        id: "scored-selected",
        type: "circle",
        source: "scored",
        filter: ["==", ["get", "fid"], ""],
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 6, 11, 14, 15],
          "circle-color": "rgba(0,0,0,0)",
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 3,
        },
      });

      map.on("click", "scored-circles", (e) => {
        const f = e.features?.[0];
        if (f) onClickRef.current?.(f as unknown as GeoJSON.Feature);
      });
      map.on("mouseenter", "scored-circles", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "scored-circles", () => {
        map.getCanvas().style.cursor = "";
      });
      // Debounced constraint refetch as the viewport changes.
      map.on("moveend", () => refetchConstraints());

      loadedRef.current = true;
      setReady(true);
    });

    return () => {
      map.remove();
      mapRef.current = null;
      loadedRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Scored features: update data + fit bounds ───────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    (map.getSource("scored") as maplibregl.GeoJSONSource)?.setData(scoredFeatures ?? EMPTY);
    map.setPaintProperty("scored-circles", "circle-color", colorExpr(scoreColorScale));
    if (fitOnUpdate && scoredFeatures && scoredFeatures.features.length > 0) {
      const b = new maplibregl.LngLatBounds();
      for (const f of scoredFeatures.features) {
        const g = f.geometry;
        if (g?.type === "Point") b.extend(g.coordinates as [number, number]);
      }
      if (!b.isEmpty()) {
        if (scoredFeatures.features.length === 1) {
          map.easeTo({ center: b.getCenter(), zoom: Math.max(map.getZoom(), 11), duration: 700 });
        } else {
          map.fitBounds(b, { padding: 80, maxZoom: 13, duration: 700 });
        }
      }
    }
  }, [scoredFeatures, scoreColorScale, ready, fitOnUpdate]);

  // ── Selection highlight ─────────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    map.setFilter("scored-selected", ["==", ["get", "fid"], selectedFid ?? ""]);
  }, [selectedFid, ready]);

  // ── Overlays (isochrones, POIs) — add/update/remove ─────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const ids = new Set(overlays.map((o) => o.id));
    // Remove stale overlays.
    for (const id of overlayIdsRef.current) {
      if (!ids.has(id)) {
        if (map.getLayer(`ov-${id}`)) map.removeLayer(`ov-${id}`);
        if (map.getSource(`ov-${id}`)) map.removeSource(`ov-${id}`);
      }
    }
    // Add/update current overlays (inserted beneath the scored circles).
    for (const o of overlays) {
      const src = map.getSource(`ov-${o.id}`) as maplibregl.GeoJSONSource | undefined;
      if (src) {
        src.setData(o.geojson);
      } else {
        map.addSource(`ov-${o.id}`, { type: "geojson", data: o.geojson });
        map.addLayer(
          { id: `ov-${o.id}`, type: o.type, source: `ov-${o.id}`, paint: o.paint } as maplibregl.LayerSpecification,
          "scored-circles",
        );
      }
    }
    overlayIdsRef.current = ids;
  }, [overlays, ready]);
  const overlayIdsRef = useRef<Set<string>>(new Set());

  // ── Constraint layers: on-demand fetch for the current viewport ─────────
  const refetchConstraints = useCallback(async () => {
    const map = mapRef.current;
    if (!map) return;
    const b = map.getBounds();
    const bbox = `${b.getWest()},${b.getSouth()},${b.getEast()},${b.getNorth()}`;
    for (const c of constraintsRef.current) {
      if (!enabledRef.current.has(c.id)) continue;
      try {
        const res = await fetch(`${API_BASE}/constraints/${c.id}?bbox=${bbox}&limit=3000`);
        if (!res.ok) continue;
        const fc = (await res.json()) as GeoJSON.FeatureCollection;
        const sid = `con-${c.id}`;
        const src = map.getSource(sid) as maplibregl.GeoJSONSource | undefined;
        if (src) src.setData(fc);
      } catch {
        /* ignore transient fetch errors */
      }
    }
  }, []);

  function addConstraint(c: ConstraintDescriptor) {
    const map = mapRef.current;
    if (!map) return;
    const sid = `con-${c.id}`;
    if (!map.getSource(sid)) {
      map.addSource(sid, { type: "geojson", data: EMPTY });
      const beforeId = map.getLayer("scored-circles") ? "scored-circles" : undefined;
      if (c.geomKind === "fill") {
        map.addLayer({ id: `${sid}-fill`, type: "fill", source: sid,
          paint: { "fill-color": c.color, "fill-opacity": 0.25 } }, beforeId);
        map.addLayer({ id: `${sid}-line`, type: "line", source: sid,
          paint: { "line-color": c.color, "line-width": 1, "line-opacity": 0.8 } }, beforeId);
      } else if (c.geomKind === "line") {
        map.addLayer({ id: `${sid}-line`, type: "line", source: sid,
          paint: { "line-color": c.color, "line-width": 1.5, "line-opacity": 0.85 } }, beforeId);
      } else {
        map.addLayer({ id: `${sid}-circle`, type: "circle", source: sid,
          paint: { "circle-radius": 3.5, "circle-color": c.color,
            "circle-stroke-color": "#0b0b0c", "circle-stroke-width": 0.5, "circle-opacity": 0.85 } }, beforeId);
      }
    }
  }

  function removeConstraint(c: ConstraintDescriptor) {
    const map = mapRef.current;
    if (!map) return;
    const sid = `con-${c.id}`;
    for (const suffix of ["-fill", "-line", "-circle"]) {
      if (map.getLayer(`${sid}${suffix}`)) map.removeLayer(`${sid}${suffix}`);
    }
    if (map.getSource(sid)) map.removeSource(sid);
  }

  function toggle(c: ConstraintDescriptor) {
    setEnabled((prev) => {
      const next = new Set(prev);
      if (next.has(c.id)) {
        next.delete(c.id);
        removeConstraint(c);
      } else {
        next.add(c.id);
        addConstraint(c);
        // fetch immediately for the current viewport (on-demand load).
        setTimeout(() => refetchConstraints(), 0);
      }
      return next;
    });
  }

  // Apply default-visible constraints once the map is ready.
  useEffect(() => {
    if (!ready) return;
    for (const c of constraintsRef.current) {
      if (enabledRef.current.has(c.id)) {
        addConstraint(c);
      }
    }
    refetchConstraints();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready]);

  const grouped = constraints.reduce<Record<string, ConstraintDescriptor[]>>((acc, c) => {
    (acc[c.category] ??= []).push(c);
    return acc;
  }, {});

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" />

      {/* Layer toggle panel (top-right) */}
      {constraints.length > 0 && (
        <div className="absolute right-3 top-3 z-10 w-56 rounded-lg border border-zinc-700 bg-zinc-900/90 p-3 text-xs shadow-xl backdrop-blur">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-zinc-400">Layers</p>
          {Object.entries(grouped).map(([cat, items]) => (
            <div key={cat} className="mb-2">
              <p className="mb-1 text-[9px] uppercase tracking-wider text-zinc-600">{cat}</p>
              {items.map((c) => (
                <label key={c.id} className="flex cursor-pointer items-center gap-2 py-0.5 text-zinc-300 hover:text-white">
                  <input
                    type="checkbox"
                    checked={enabled.has(c.id)}
                    onChange={() => toggle(c)}
                    className="h-3 w-3 accent-blue-500"
                  />
                  <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: c.color }} />
                  <span>{c.name}</span>
                </label>
              ))}
            </div>
          ))}
        </div>
      )}

      {/* Color-scale legend (bottom-left, above scale bar) */}
      <div className="absolute bottom-10 left-3 z-10 rounded-lg border border-zinc-700 bg-zinc-900/90 px-3 py-2 text-[10px] shadow-xl backdrop-blur">
        {LEGENDS[scoreColorScale].map(([color, label]) => (
          <div key={label} className="flex items-center gap-1.5 py-0.5 text-zinc-300">
            <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: color }} />
            <span>{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
