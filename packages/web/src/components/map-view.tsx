"use client";

import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import maplibregl from "maplibre-gl";

const STYLE: maplibregl.StyleSpecification = {
  version: 8,
  name: "Carto Light",
  sources: {
    carto: {
      type: "raster",
      tiles: [
        "https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}@2x.png",
      ],
      tileSize: 256,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
    },
  },
  layers: [{ id: "carto-tiles", type: "raster", source: "carto" }],
};

// Alameda County center
const CENTER: [number, number] = [-122.05, 37.68];

export interface MapHandle {
  setGeoJSON: (geojson: GeoJSON.FeatureCollection) => void;
  clearGeoJSON: () => void;
  setMarker: (lat: number, lng: number) => void;
  clearMarker: () => void;
}

interface Props {
  onPointPick?: (lat: number, lng: number) => void;
}

export const MapView = forwardRef<MapHandle, Props>(function MapView({ onPointPick }, ref) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markerRef = useRef<maplibregl.Marker | null>(null);
  const sourceAdded = useRef(false);
  const onPointPickRef = useRef(onPointPick);
  onPointPickRef.current = onPointPick;

  useEffect(() => {
    if (!containerRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: STYLE,
      center: CENTER,
      zoom: 10.5,
    });

    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.getCanvas().style.cursor = "crosshair";
    map.on("click", (e) => {
      onPointPickRef.current?.(e.lngLat.lat, e.lngLat.lng);
    });
    mapRef.current = map;

    map.on("load", () => {
      map.addSource("results", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

      // Polygon fill
      map.addLayer({
        id: "results-fill",
        type: "fill",
        source: "results",
        filter: ["==", "$type", "Polygon"],
        paint: {
          "fill-color": "#6366f1",
          "fill-opacity": 0.25,
        },
      });

      // Polygon outline
      map.addLayer({
        id: "results-outline",
        type: "line",
        source: "results",
        filter: ["==", "$type", "Polygon"],
        paint: {
          "line-color": "#6366f1",
          "line-width": 1.5,
        },
      });

      // Lines
      map.addLayer({
        id: "results-line",
        type: "line",
        source: "results",
        filter: ["==", "$type", "LineString"],
        paint: {
          "line-color": "#6366f1",
          "line-width": 2,
        },
      });

      // Points
      map.addLayer({
        id: "results-point",
        type: "circle",
        source: "results",
        filter: ["==", "$type", "Point"],
        paint: {
          "circle-radius": 5,
          "circle-color": "#6366f1",
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1.5,
        },
      });

      sourceAdded.current = true;
    });

    return () => {
      map.remove();
    };
  }, []);

  useImperativeHandle(ref, () => ({
    setGeoJSON(geojson: GeoJSON.FeatureCollection) {
      const map = mapRef.current;
      if (!map || !sourceAdded.current) return;

      const source = map.getSource("results") as maplibregl.GeoJSONSource;
      source.setData(geojson);

      // Fit bounds
      if (geojson.features.length > 0) {
        const bounds = new maplibregl.LngLatBounds();
        for (const f of geojson.features) {
          const geom = f.geometry;
          if (geom.type === "Point") {
            bounds.extend(geom.coordinates as [number, number]);
          } else if (geom.type === "Polygon" || geom.type === "MultiPolygon") {
            const coords =
              geom.type === "Polygon"
                ? geom.coordinates[0]
                : geom.coordinates.flatMap((p) => p[0]);
            for (const c of coords) {
              bounds.extend(c as [number, number]);
            }
          } else if (geom.type === "LineString") {
            for (const c of geom.coordinates) {
              bounds.extend(c as [number, number]);
            }
          }
        }
        if (!bounds.isEmpty()) {
          map.fitBounds(bounds, { padding: 60, maxZoom: 15 });
        }
      }
    },
    clearGeoJSON() {
      const map = mapRef.current;
      if (!map || !sourceAdded.current) return;
      const source = map.getSource("results") as maplibregl.GeoJSONSource;
      source.setData({ type: "FeatureCollection", features: [] });
    },
    setMarker(lat: number, lng: number) {
      const map = mapRef.current;
      if (!map) return;
      markerRef.current?.remove();
      const el = document.createElement("div");
      el.style.cssText =
        "width:18px;height:18px;border-radius:50%;background:#f97316;border:3px solid #fff;box-shadow:0 0 0 1px rgba(0,0,0,.25),0 2px 6px rgba(0,0,0,.25);";
      markerRef.current = new maplibregl.Marker({ element: el })
        .setLngLat([lng, lat])
        .addTo(map);
      map.flyTo({ center: [lng, lat], zoom: Math.max(map.getZoom(), 13), duration: 700 });
    },
    clearMarker() {
      markerRef.current?.remove();
      markerRef.current = null;
    },
  }));

  return <div ref={containerRef} className="h-full w-full" />;
});
