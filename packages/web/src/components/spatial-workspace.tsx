"use client";

import { useCallback, useRef, useState } from "react";
import { MapView, type MapHandle } from "./map-view";
import { ChatPanel } from "./chat-panel";
import { DataTable } from "./data-table";
import { SqlPanel } from "./sql-panel";
import { SiteReportPanel, siteKey } from "./site-report";
import { postSiteReport, type QueryResult, type SiteReport } from "../lib/api";
import { exportElementToPdf } from "../lib/export-pdf";

interface Props {
  // Sidebar heading + chat placeholder vary by page (Suitability vs Query)
  // but the underlying workspace — NL chat, map, SQL panel, data table, and
  // click-to-site-report — is identical.
  title: string;
  subtitle: string;
  chatPlaceholder?: string;
}

export function SpatialWorkspace({ title, subtitle, chatPlaceholder }: Props) {
  const mapRef = useRef<MapHandle>(null);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState<SiteReport | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [exporting, setExporting] = useState(false);

  const handleResult = useCallback((r: QueryResult) => {
    setResult(r);
    let features: GeoJSON.Feature[] = [];
    if (r.type === "FeatureCollection" && r.features?.length) {
      features = r.features;
    } else if (r.type === "large_result_summary" && r.sample_rows?.length) {
      features = (r.sample_rows as unknown[]).filter((row): row is GeoJSON.Feature => {
        if (row === null || typeof row !== "object") return false;
        const rec = row as Record<string, unknown>;
        const geom = rec.geometry as { type?: string } | null | undefined;
        return !!geom && typeof geom === "object" && typeof geom.type === "string";
      });
    }
    if (features.length) {
      mapRef.current?.setGeoJSON({ type: "FeatureCollection", features });
    } else {
      mapRef.current?.clearGeoJSON();
    }
  }, []);

  const runReport = useCallback(
    async (body: { address?: string; latitude?: number; longitude?: number }) => {
      setReportLoading(true);
      try {
        const r = await postSiteReport(body);
        setReport(r);
        mapRef.current?.setMarker(r.location.latitude, r.location.longitude);
      } finally {
        setReportLoading(false);
      }
    },
    [],
  );

  const handleMapPick = useCallback(
    (lat: number, lng: number) => {
      runReport({ latitude: lat, longitude: lng }).catch((err) => console.error(err));
    },
    [runReport],
  );

  const handleSiteReportRequest = useCallback(
    async (address: string) => {
      await runReport({ address });
    },
    [runReport],
  );

  const handleCloseReport = useCallback(() => {
    setReport(null);
    mapRef.current?.clearMarker();
  }, []);

  const handleExport = useCallback(
    async (el: HTMLElement) => {
      if (!report) return;
      setExporting(true);
      try {
        await exportElementToPdf(el, `site-report-${siteKey(report)}.pdf`);
      } finally {
        setExporting(false);
      }
    },
    [report],
  );

  return (
    <div className="flex min-h-0 flex-1">
      {/* Left sidebar */}
      <div className="flex w-[420px] shrink-0 flex-col border-r border-zinc-800 bg-zinc-900">
        <div className="border-b border-zinc-800 px-4 py-3">
          <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
          <p className="text-xs text-zinc-500">{subtitle}</p>
        </div>

        <ChatPanel
          onResult={handleResult}
          onSiteReportRequest={handleSiteReportRequest}
          loading={loading}
          setLoading={setLoading}
          placeholder={chatPlaceholder}
        />

        {result?.sql || result?.generated_sql || result?.metadata?.sql ? (
          <SqlPanel sql={(result.sql ?? result.generated_sql ?? result.metadata?.sql)!} />
        ) : null}

        <DataTable result={result} />
      </div>

      {/* Map */}
      <div className="relative flex-1">
        <MapView ref={mapRef} onPointPick={handleMapPick} />
        {(loading || reportLoading) && (
          <div className="absolute left-1/2 top-4 -translate-x-1/2 rounded-full bg-zinc-900/90 px-4 py-1.5 text-xs text-zinc-300 shadow-lg">
            {reportLoading ? "Scoring site..." : "Querying..."}
          </div>
        )}
        {!report && !reportLoading && (
          <div className="pointer-events-none absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full bg-white/90 px-3 py-1 text-[11px] font-medium text-zinc-700 shadow">
            Click any point on the map for a site suitability report
          </div>
        )}

        {report && (
          <SiteReportPanel
            key={siteKey(report)}
            report={report}
            onClose={handleCloseReport}
            onExport={handleExport}
            exporting={exporting}
          />
        )}
      </div>
    </div>
  );
}
