"use client";

import { type FormEvent, useCallback, useRef, useState } from "react";
import { TopNav } from "../../components/top-nav";
import { MapView, type MapHandle } from "../../components/map-view";
import { WildfireReportPanel } from "../../components/wildfire-report";
import {
  postWildfireLoss,
  type WildfireRiskAssessment,
} from "../../lib/api";
import { exportElementToPdf } from "../../lib/export-pdf";

// Sonoma County camera.
const SONOMA_CENTER: [number, number] = [-122.8, 38.5];
const SONOMA_ZOOM = 9.2;

export default function WildfirePage() {
  const mapRef = useRef<MapHandle>(null);
  const [address, setAddress] = useState("");
  const [report, setReport] = useState<WildfireRiskAssessment | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const assess = useCallback(
    async (body: { address?: string; latitude?: number; longitude?: number }) => {
      setLoading(true);
      setError(null);
      try {
        const r = await postWildfireLoss(body);
        setReport(r);
        const lat = r.match?.nsi_location.latitude ?? r.query.latitude;
        const lng = r.match?.nsi_location.longitude ?? r.query.longitude;
        mapRef.current?.setMarker(lat, lng);
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

  const onClose = useCallback(() => {
    setReport(null);
    mapRef.current?.clearMarker();
  }, []);

  const onExport = useCallback(async (el: HTMLElement, filename: string) => {
    setExporting(true);
    try {
      await exportElementToPdf(el, filename);
    } finally {
      setExporting(false);
    }
  }, []);

  return (
    <div className="flex h-full flex-col">
      <TopNav active="wildfire" />

      {/* Control bar */}
      <div className="flex shrink-0 items-center gap-3 border-b border-zinc-800 bg-zinc-900 px-5 py-3">
        <div>
          <h1 className="text-base font-semibold tracking-tight">Wildfire Risk Assessment</h1>
          <p className="text-[11px] text-zinc-500">Sonoma County · single property</p>
        </div>
        <form onSubmit={onSubmit} className="ml-2 flex flex-1 items-center gap-2">
          <input
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            placeholder="Enter a Sonoma County address, or click the map"
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

      {/* Map + slide-in panel */}
      <div className="relative min-h-0 flex-1">
        <MapView
          ref={mapRef}
          onPointPick={onMapPick}
          center={SONOMA_CENTER}
          zoom={SONOMA_ZOOM}
        />
        {loading && (
          <div className="absolute left-1/2 top-4 -translate-x-1/2 rounded-full bg-zinc-900/90 px-4 py-1.5 text-xs text-zinc-300 shadow-lg">
            Assessing wildfire risk…
          </div>
        )}
        {!report && !loading && (
          <div className="pointer-events-none absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full bg-white/90 px-3 py-1 text-[11px] font-medium text-zinc-700 shadow">
            Enter an address above or click any point in Sonoma County
          </div>
        )}

        {report && (
          <WildfireReportPanel
            key={`${report.query.latitude.toFixed(5)},${report.query.longitude.toFixed(5)}`}
            report={report}
            onClose={onClose}
            onExport={onExport}
            exporting={exporting}
          />
        )}
      </div>
    </div>
  );
}
