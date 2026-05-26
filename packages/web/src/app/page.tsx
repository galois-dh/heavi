"use client";

import { useRef, useState, useCallback } from "react";
import { MapView, type MapHandle } from "../components/map-view";
import { ChatPanel } from "../components/chat-panel";
import { DataTable } from "../components/data-table";
import { SqlPanel } from "../components/sql-panel";
import { SiteReportPanel, siteKey } from "../components/site-report";
import { WildfireReportPanel } from "../components/wildfire-report";
import {
  postSiteReport,
  postWildfireLoss,
  type QueryResult,
  type SiteReport,
  type WildfireRiskAssessment,
} from "../lib/api";

// Sonoma County bbox (per product spec). Click inside → wildfire risk
// assessment; click outside → site-suitability report. The bbox is
// generous on purpose — better to misroute a few edge clicks toward the
// wildfire model (which gracefully handles "no NSI within 500 m") than to
// silently strand Sonoma users in the Alameda-tuned suitability flow.
const SONOMA_BBOX = { latMin: 38.1, latMax: 38.9, lngMin: -123.1, lngMax: -122.3 };
function inSonomaCounty(lat: number, lng: number): boolean {
  return (
    lat >= SONOMA_BBOX.latMin &&
    lat <= SONOMA_BBOX.latMax &&
    lng >= SONOMA_BBOX.lngMin &&
    lng <= SONOMA_BBOX.lngMax
  );
}

// Report state is a discriminated union so only one panel can be open at
// a time and TypeScript narrows the right shape per branch.
type ReportState =
  | { kind: "suitability"; data: SiteReport }
  | { kind: "wildfire"; data: WildfireRiskAssessment }
  | null;

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
  const [report, setReport] = useState<ReportState>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [exporting, setExporting] = useState(false);

  const handleResult = useCallback((r: QueryResult) => {
    setResult(r);

    // Build a renderable FeatureCollection from either a normal feature
    // result OR the truncated-sample preview embedded in large_result_summary.
    // For the sample case, sample_rows entries are full GeoJSON Features
    // (see api.ts QueryResult). We filter to ones that carry geometry so
    // plain-row samples (aggregate-shaped) don't poison setGeoJSON.
    let features: GeoJSON.Feature[] = [];
    if (r.type === "FeatureCollection" && r.features?.length) {
      features = r.features;
    } else if (r.type === "large_result_summary" && r.sample_rows?.length) {
      // sample_rows is typed as Record<string,unknown>[] (it can also carry
      // plain row dicts for non-feature queries) — cast through unknown so
      // TS accepts the filter narrowing.
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

  const runSuitabilityReport = useCallback(
    async (body: { address?: string; latitude?: number; longitude?: number }) => {
      setReportLoading(true);
      try {
        const r = await postSiteReport(body);
        setReport({ kind: "suitability", data: r });
        mapRef.current?.setMarker(r.location.latitude, r.location.longitude);
      } finally {
        setReportLoading(false);
      }
    },
    [],
  );

  const runWildfireReport = useCallback(
    async (body: { address?: string; latitude?: number; longitude?: number }) => {
      setReportLoading(true);
      try {
        const r = await postWildfireLoss(body);
        setReport({ kind: "wildfire", data: r });
        // For wildfire we drop the marker on the *match* location (NSI snap)
        // when available, falling back to the click coord.
        const lat = r.match?.nsi_location.latitude ?? r.query.latitude;
        const lng = r.match?.nsi_location.longitude ?? r.query.longitude;
        mapRef.current?.setMarker(lat, lng);
      } finally {
        setReportLoading(false);
      }
    },
    [],
  );

  const handleMapPick = useCallback(
    (lat: number, lng: number) => {
      const fn = inSonomaCounty(lat, lng) ? runWildfireReport : runSuitabilityReport;
      fn({ latitude: lat, longitude: lng }).catch((err) => {
        console.error(err);
      });
    },
    [runSuitabilityReport, runWildfireReport],
  );

  // Chat-driven site-report requests stay on the suitability flow — the
  // intent matcher explicitly captures "score X" / "site report for X",
  // which are suitability semantics. Only map clicks branch by geography.
  const handleSiteReportRequest = useCallback(
    async (address: string) => {
      await runSuitabilityReport({ address });
    },
    [runSuitabilityReport],
  );

  const handleCloseReport = useCallback(() => {
    setReport(null);
    mapRef.current?.clearMarker();
  }, []);

  // Generalized PDF export — each panel passes the element to rasterize and
  // the desired filename. Decouples export from any specific report shape.
  const handleExport = useCallback(
    async (el: HTMLElement, filename: string) => {
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
        pdf.save(filename);
      } finally {
        setExporting(false);
      }
    },
    [],
  );

  return (
    <div className="flex h-full">
      {/* Left sidebar */}
      <div className="flex w-[420px] shrink-0 flex-col border-r border-zinc-800 bg-zinc-900">
        <div className="border-b border-zinc-800 px-4 py-3">
          <h1 className="text-lg font-semibold tracking-tight">Heavi</h1>
          <p className="text-xs text-zinc-500">Spatial decision intelligence</p>
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
            Click any point — Alameda → site report · Sonoma → wildfire risk
          </div>
        )}

        {report?.kind === "suitability" && (
          <SiteReportPanel
            key={`s:${siteKey(report.data)}`}
            report={report.data}
            onClose={handleCloseReport}
            onExport={(el) =>
              handleExport(el, `site-report-${siteKey(report.data)}.pdf`)
            }
            exporting={exporting}
          />
        )}
        {report?.kind === "wildfire" && (
          <WildfireReportPanel
            key={`w:${report.data.query.latitude.toFixed(5)},${report.data.query.longitude.toFixed(5)}`}
            report={report.data}
            onClose={handleCloseReport}
            onExport={handleExport}
            exporting={exporting}
          />
        )}
      </div>
    </div>
  );
}
