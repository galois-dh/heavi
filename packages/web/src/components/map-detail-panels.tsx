"use client";

import type { SolarScoreV2, HazardScoreV2, TradeAreaScoreV2 } from "../lib/api";
import { criterionName, sourceName } from "../lib/display-names";

const TIER_CHIP: Record<string, string> = {
  HIGH: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  HIGH_RISK: "bg-red-500/15 text-red-300 border-red-500/30",
  MODERATE: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  LOW: "bg-orange-500/15 text-orange-300 border-orange-500/30",
  INSUFFICIENT: "bg-red-500/15 text-red-300 border-red-500/30",
  STRONG: "bg-cyan-500/15 text-cyan-300 border-cyan-500/30",
  WEAK: "bg-slate-500/15 text-slate-300 border-slate-500/30",
  EXCLUDED: "bg-zinc-600/30 text-zinc-300 border-zinc-600",
  // CANNOT ASSESS — neutral gray/amber, visually distinct from green/red (AC4).
  "CANNOT ASSESS": "bg-zinc-500/20 text-zinc-200 border-zinc-400/40",
  NONE: "bg-zinc-700/40 text-zinc-300 border-zinc-700",
};
const chip = (t: string | null | undefined) => TIER_CHIP[(t ?? "NONE").toUpperCase()] ?? TIER_CHIP.NONE;
const usd = (v: number | null | undefined) => (v == null ? "—" : `$${Math.round(v).toLocaleString("en-US")}/yr`);

/** CANNOT ASSESS explanatory block — message + named missing sources + the
 *  "does NOT mean low risk" disclaimer (Insufficient Data Handling Spec, AC3). */
export function CannotAssess({
  label, message, sources,
}: { label: string; message?: string; sources?: string[] }) {
  return (
    <div className="rounded-md border border-zinc-400/40 bg-zinc-500/10 p-3 text-xs">
      <div className="flex items-center gap-2">
        <span aria-hidden className="text-zinc-300">ⓘ</span>
        <span className="rounded border border-zinc-400/40 bg-zinc-500/20 px-2 py-0.5 font-semibold text-zinc-200">
          {label} · CANNOT ASSESS
        </span>
      </div>
      <p className="mt-2 leading-relaxed text-zinc-300">
        {message ?? `${label} cannot be assessed at this location.`}
      </p>
      {sources && sources.length > 0 && (
        <ul className="mt-1.5 space-y-0.5 text-zinc-400">
          {sources.map((s, i) => <li key={i}>• {s}</li>)}
        </ul>
      )}
      <p className="mt-2 text-[11px] italic text-zinc-500">
        This does NOT mean the location is low risk — critical data is unavailable.
      </p>
    </div>
  );
}

function Header({ title, sub }: { title: string; sub: string }) {
  return (
    <div className="border-b border-zinc-800 pb-2">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">{title}</p>
      <p className="font-mono text-sm text-zinc-200">{sub}</p>
    </div>
  );
}

export function EnergyDetail({ r }: { r: SolarScoreV2 }) {
  const wp = r.weight_profile;
  const cites = r.methodology?.framework_citations?.length ?? 0;
  if (r.cannot_assess || r.rating === "CANNOT ASSESS") {
    return (
      <div className="space-y-3 text-xs">
        <Header title="Parcel assessment" sub={`${r.query.latitude.toFixed(4)}, ${r.query.longitude.toFixed(4)}`} />
        <CannotAssess
          label="Site score"
          message={r.message}
          sources={(r.missing_sources ?? []).flatMap((m) => m.sources)}
        />
      </div>
    );
  }
  return (
    <div className="space-y-3 text-xs">
      <Header title="Parcel assessment" sub={`${r.query.latitude.toFixed(4)}, ${r.query.longitude.toFixed(4)}`} />
      <div className="flex flex-wrap gap-2">
        <span className={`rounded-md border px-2 py-1 ${chip(r.rating)}`}>
          SCORE {Math.round((r.score ?? 0) * 100)} / 100 · {r.rating}
        </span>
        <span className={`rounded-md border px-2 py-1 ${chip(r.confidence.tier)}`}>
          CONFIDENCE {Math.round(r.confidence.composite * 100)} · {r.confidence.tier}
        </span>
      </div>
      <p className="leading-relaxed text-zinc-400">{r.confidence.statement}</p>

      {r.confidence.gaps.length > 0 && (
        <div className="rounded-md border border-amber-500/20 bg-amber-500/5 p-2">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-amber-300">Data gaps ({r.confidence.gaps.length})</p>
          <ul className="mt-1 space-y-0.5 text-zinc-400">{r.confidence.gaps.map((g, i) => <li key={i}>• {g.message}</li>)}</ul>
        </div>
      )}

      {r.interconnection_context && (() => {
        const ic = r.interconnection_context!;
        const sub = ic.nearest_substation;
        return (
          <div className="rounded-md border border-violet-500/20 bg-violet-500/5 p-2">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-violet-300">Interconnection context</p>
            <div className="mt-1 space-y-0.5">
              <div className="flex justify-between"><span className="text-zinc-400">Nearest substation</span>
                <span className="text-zinc-200">{sub ? `${sub.distance_mi} mi${sub.voltage_kv ? ` · ${sub.voltage_kv} kV` : ""}` : "—"}</span></div>
              <div className="flex justify-between"><span className="text-zinc-400">Existing capacity</span>
                <span className="text-zinc-200">{Math.round(ic.existing_capacity_mw)} MW · {ic.existing_plant_count} plants</span></div>
              <div className="flex justify-between"><span className="text-zinc-400">Active solar queue ({ic.iso ?? "—"})</span>
                <span className="text-zinc-200">{ic.queue_projects_nearby} projects · {Math.round(ic.queue_capacity_mw)} MW</span></div>
              <div className="flex justify-between"><span className="text-zinc-400">Source</span>
                <span className="text-zinc-500">LBNL Queued Up 2025</span></div>
            </div>
            <p className="mt-1.5 text-[10px] italic text-zinc-500">Informational context, not an interconnection study. County-centroid precision.</p>
          </div>
        );
      })()}

      <div>
        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Per-criterion scores</p>
        {Object.entries(r.criteria_scores).map(([id, c]) => (
          <div key={id} className="flex justify-between py-0.5">
            <span className="text-zinc-300">{c.display_name ?? criterionName(id)}</span>
            <span className="font-mono text-zinc-200">{c.score == null ? "—" : Math.round(c.score * 100)}</span>
          </div>
        ))}
      </div>

      <div>
        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Exclusions</p>
        {Object.entries(r.exclusion_results).map(([id, ex]) => (
          <div key={id} className="flex justify-between py-0.5">
            <span className="text-zinc-300">{ex.display_name ?? criterionName(id)}</span>
            <span className={ex.excluded ? "text-red-400" : "text-emerald-400"}>
              {ex.excluded === null ? "no data" : ex.excluded ? "EXCLUDED" : "pass"}
              <span className="text-zinc-600"> · {ex.source_display ?? sourceName(ex.selected_source)}</span>
            </span>
          </div>
        ))}
      </div>

      {wp && (
        <p className="text-zinc-400">
          <span className="text-[10px] uppercase tracking-wider text-zinc-500">Weight profile: </span>
          {wp.region ?? "—"} ({wp.method})
        </p>
      )}
      <p className="text-zinc-500">
        Methodology · {r.methodology.criteria_count} criteria · {cites} citations
      </p>
    </div>
  );
}

export function HazardDetail({ r }: { r: HazardScoreV2 }) {
  const wf = r.wildfire;
  const fl = r.flood;
  return (
    <div className="space-y-3 text-xs">
      <Header title="Property hazard assessment" sub={`${r.query.latitude.toFixed(4)}, ${r.query.longitude.toFixed(4)}`} />

      {wf.cannot_assess || wf.risk_tier === "CANNOT ASSESS" ? (
        <CannotAssess label="Wildfire" message={wf.message} sources={wf.missing_sources} />
      ) : (
        <div className="rounded-md border border-zinc-800 bg-zinc-950/60 p-2">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-white">Wildfire</span>
            <span className={`rounded border px-1.5 py-0.5 ${chip(wf.risk_tier)}`}>{wf.available ? wf.risk_tier : "NO DATA"}</span>
          </div>
          <p className="text-base font-bold text-zinc-100">{usd(wf.annual_risk_usd)}</p>
          {wf.damage_probability != null && <p className="text-zinc-500">damage prob {Math.round(wf.damage_probability * 100)}%</p>}
        </div>
      )}

      {fl.cannot_assess || fl.risk_tier === "CANNOT ASSESS" ? (
        <CannotAssess label="Flood" message={fl.message} sources={fl.missing_sources} />
      ) : (
        <div className="rounded-md border border-zinc-800 bg-zinc-950/60 p-2">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-white">Flood</span>
            <span className={`rounded border px-1.5 py-0.5 ${chip(fl.risk_tier)}`}>{fl.risk_tier ?? "—"}</span>
          </div>
          <p className="text-base font-bold text-zinc-100">{usd(fl.annual_risk_usd)}</p>
          <p className="text-zinc-500">
            zone {fl.flood_zone ?? "X/unmapped"}{fl.depth_ft != null && ` · depth ${fl.depth_ft} ft`}
          </p>
        </div>
      )}

      <div className="flex items-center gap-2">
        <span className="text-[10px] uppercase tracking-wider text-zinc-500">Confidence</span>
        <span className={`rounded border px-2 py-0.5 ${chip(r.confidence.tier)}`}>
          {r.confidence.tier} · {Math.round(r.confidence.composite * 100)}%
        </span>
      </div>
      <p className="leading-relaxed text-zinc-400">{r.confidence.statement}</p>

      <PerilCriteria title="Wildfire criteria" map={wf.criteria_confidence as CriteriaConfidence} />
      <PerilCriteria title="Flood criteria" map={fl.criteria_confidence as CriteriaConfidence} />

      {r.confidence.gaps.length > 0 && (
        <div className="rounded-md border border-amber-500/20 bg-amber-500/5 p-2">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-amber-300">Data gaps ({r.confidence.gaps.length})</p>
          <ul className="mt-1 space-y-0.5 text-zinc-400">{r.confidence.gaps.map((g, i) => <li key={i}>• {g.message}</li>)}</ul>
        </div>
      )}
    </div>
  );
}

type CriteriaConfidence = Record<string, { tier?: string; display_name?: string }> | undefined;

/** Per-criterion list for a hazard peril, with natural-language criterion names. */
function PerilCriteria({ title, map }: { title: string; map: CriteriaConfidence }) {
  const entries = Object.entries(map ?? {});
  if (entries.length === 0) return null;
  return (
    <div>
      <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">{title}</p>
      {entries.map(([id, c]) => (
        <div key={id} className="flex justify-between py-0.5">
          <span className="text-zinc-300">{c.display_name ?? criterionName(id)}</span>
          <span className="text-zinc-500">{c.tier ?? "—"}</span>
        </div>
      ))}
    </div>
  );
}

export function LocationsDetail({ r }: { r: TradeAreaScoreV2 }) {
  const q = r.query as { latitude: number; longitude: number; business_category?: string };
  const src = r.data_sources_used ?? {};
  const ca = (r.competitive_analysis ?? {}) as Record<string, unknown>;
  // 10-min ring demographics if present (full coverage).
  const rings = r.trade_area_rings ?? [];
  const ring10 = rings.find((x) => Math.abs(((x.drive_time_minutes as number) ?? 0) - 10) <= 3) as Record<string, unknown> | undefined;
  if (r.cannot_assess || r.suitability_rating === "CANNOT ASSESS") {
    return (
      <div className="space-y-3 text-xs">
        <Header title="Trade area assessment" sub={`${q.latitude.toFixed(4)}, ${q.longitude.toFixed(4)} · ${q.business_category ?? "—"}`} />
        <CannotAssess
          label="Trade area"
          message={r.message}
          sources={(r.missing_sources ?? []).flatMap((m) => m.sources)}
        />
      </div>
    );
  }
  return (
    <div className="space-y-3 text-xs">
      <Header title="Trade area assessment" sub={`${q.latitude.toFixed(4)}, ${q.longitude.toFixed(4)} · ${q.business_category ?? "—"}`} />
      <div className="flex flex-wrap gap-2">
        <span className={`rounded-md border px-2 py-1 ${chip(r.suitability_rating)}`}>
          SCORE {(r.suitability_score ?? 0).toFixed(2)} · {r.suitability_rating}
        </span>
        <span className={`rounded-md border px-2 py-1 ${chip(r.confidence.tier)}`}>
          CONFIDENCE {r.confidence.tier} · {Math.round(r.confidence.composite * 100)}%
        </span>
        <span className="rounded-md border border-zinc-700 bg-zinc-800/60 px-2 py-1 text-zinc-400">{r.coverage}</span>
      </div>

      {ring10 && (
        <div>
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Demographics (10-min drive)</p>
          {[["Population", "population"], ["Households", "households"], ["Median HHI", "median_household_income"], ["Daytime emp", "daytime_jobs"]].map(([label, key]) => (
            <div key={key} className="flex justify-between py-0.5">
              <span className="text-zinc-300">{label}</span>
              <span className="font-mono text-zinc-200">{(ring10[key] as number)?.toLocaleString?.("en-US") ?? "—"}</span>
            </div>
          ))}
        </div>
      )}

      {("competitor_count" in ca || ring10) && (
        <div>
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Competitive landscape</p>
          <div className="flex justify-between py-0.5">
            <span className="text-zinc-300">Same-category</span>
            <span className="font-mono text-zinc-200">{(ca.competitor_count as number) ?? (ring10?.competitor_count as number) ?? "—"}</span>
          </div>
          <div className="flex justify-between py-0.5">
            <span className="text-zinc-300">Complementary</span>
            <span className="font-mono text-zinc-200">{(ca.complementary_count as number) ?? (ring10?.complementary_count as number) ?? "—"}</span>
          </div>
        </div>
      )}

      {Object.keys(r.criteria_scores ?? {}).length > 0 && (
        <div>
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Criteria</p>
          {Object.entries(r.criteria_scores).map(([id, score]) => (
            <div key={id} className="flex justify-between py-0.5">
              <span className="text-zinc-300">{criterionName(id)}</span>
              <span className="font-mono text-zinc-200">{score == null ? "—" : Math.round((score as number) * 100)}</span>
            </div>
          ))}
        </div>
      )}

      <div>
        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Data sources</p>
        {[["POIs", src.poi_source], ["Daytime", src.daytime_source], ["Population", src.population_source], ["Flood", src.flood_source]].map(([label, val]) => (
          <div key={label} className="flex justify-between py-0.5">
            <span className="text-zinc-300">{label}</span>
            <span className="text-zinc-400">{sourceName(val as string | null)}</span>
          </div>
        ))}
      </div>

      {(r.coverage_gaps?.length ?? 0) > 0 && (
        <div className="rounded-md border border-amber-500/20 bg-amber-500/5 p-2">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-amber-300">Data gaps ({r.coverage_gaps!.length})</p>
          <ul className="mt-1 space-y-0.5 text-zinc-400">{r.coverage_gaps!.map((g, i) => <li key={i}>• {criterionName(g)}</li>)}</ul>
        </div>
      )}
    </div>
  );
}
