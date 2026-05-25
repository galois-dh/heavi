"use client";

import { useRef, useState, useCallback } from "react";
import { MapView, type MapHandle } from "../components/map-view";
import { ChatPanel } from "../components/chat-panel";
import { DataTable } from "../components/data-table";
import { SqlPanel } from "../components/sql-panel";
import { SiteReportPanel, siteKey } from "../components/site-report";
import { postSiteReport, type QueryResult, type SiteReport } from "../lib/api";

// html2canvas's color parser pre-dates CSS Color Level 4, so any oklch(...)
// value blows up. Fix in two passes: rewrite <style> text so Tailwind's
// custom properties and pseudo-element rules emit rgb instead of oklch, then
// pin any remaining oklch computed values (e.g. from external stylesheets)
// as inline styles. html2canvas also reads html/body backgrounds directly
// for the page-background fallback, so normalize those too — not just the
// capture subtree.
//
// Note: canvas.fillStyle accepts oklch in modern Chrome but serializes it
// back as oklch(...). To force a real sRGB conversion we rasterize a 1x1
// pixel and read back its bytes.
function normalizeOklchColors(doc: Document, root: HTMLElement): void {
  const win = doc.defaultView;
  if (!win) return;
  const canvas = doc.createElement("canvas");
  canvas.width = 1;
  canvas.height = 1;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return;

  const toRgb = (text: string): string =>
    text.replace(/oklch\([^)]+\)/gi, (match) => {
      try {
        ctx.clearRect(0, 0, 1, 1);
        ctx.fillStyle = "#000";
        ctx.fillStyle = match;
        ctx.fillRect(0, 0, 1, 1);
        const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data;
        return a === 255
          ? `rgb(${r}, ${g}, ${b})`
          : `rgba(${r}, ${g}, ${b}, ${(a / 255).toFixed(3)})`;
      } catch {
        return match;
      }
    });

  doc.querySelectorAll<HTMLStyleElement>("style").forEach((s) => {
    const t = s.textContent;
    if (t && t.includes("oklch")) s.textContent = toRgb(t);
  });

  const visit = (el: HTMLElement) => {
    const cs = win.getComputedStyle(el);
    for (let i = 0; i < cs.length; i++) {
      const prop = cs[i];
      const val = cs.getPropertyValue(prop);
      if (val.includes("oklch")) {
        el.style.setProperty(prop, toRgb(val));
      }
    }
  };

  if (doc.documentElement) visit(doc.documentElement);
  if (doc.body) visit(doc.body);
  visit(root);
  root.querySelectorAll<HTMLElement>("*").forEach(visit);
}

export default function Home() {
  const mapRef = useRef<MapHandle>(null);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState<SiteReport | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [exporting, setExporting] = useState(false);

  const handleResult = useCallback((r: QueryResult) => {
    setResult(r);
    if (r.type === "FeatureCollection" && r.features?.length) {
      mapRef.current?.setGeoJSON({
        type: "FeatureCollection",
        features: r.features,
      });
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
      runReport({ latitude: lat, longitude: lng }).catch((err) => {
        console.error(err);
      });
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
        const [{ default: html2canvas }, jsPDFModule] = await Promise.all([
          import("html2canvas"),
          import("jspdf"),
        ]);
        const canvas = await html2canvas(el, {
          backgroundColor: "#ffffff",
          scale: 2,
          useCORS: true,
          logging: false,
          onclone: (doc, cloned) => {
            normalizeOklchColors(doc, cloned as HTMLElement);
          },
        });
        const imgData = canvas.toDataURL("image/png");
        const pdf = new jsPDFModule.jsPDF({
          unit: "pt",
          format: "letter",
          orientation: "portrait",
        });
        const pageW = pdf.internal.pageSize.getWidth();
        const pageH = pdf.internal.pageSize.getHeight();
        const margin = 32;
        const maxW = pageW - margin * 2;
        const maxH = pageH - margin * 2;
        const ratio = Math.min(maxW / canvas.width, maxH / canvas.height);
        const drawW = canvas.width * ratio;
        const drawH = canvas.height * ratio;
        pdf.addImage(imgData, "PNG", (pageW - drawW) / 2, margin, drawW, drawH);
        const filename = `site-report-${siteKey(report)}.pdf`;
        pdf.save(filename);
      } finally {
        setExporting(false);
      }
    },
    [report],
  );

  return (
    <div className="flex h-full">
      {/* Left sidebar */}
      <div className="flex w-[420px] shrink-0 flex-col border-r border-zinc-800 bg-zinc-900">
        <div className="border-b border-zinc-800 px-4 py-3">
          <h1 className="text-lg font-semibold tracking-tight">Heavi</h1>
          <p className="text-xs text-zinc-500">Spatial computation platform</p>
        </div>

        <ChatPanel
          onResult={handleResult}
          onSiteReportRequest={handleSiteReportRequest}
          loading={loading}
          setLoading={setLoading}
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
            Click any point on the map for a site report
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
