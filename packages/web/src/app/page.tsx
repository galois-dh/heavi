import Link from "next/link";
import {
  Database,
  BookOpen,
  Workflow,
  ShieldCheck,
  Sun,
  Flame,
  Store,
  Check,
  ArrowRight,
  CornerDownRight,
  Code2,
} from "lucide-react";
import { LandingNav } from "../components/landing-nav";
import { Reveal } from "../components/landing-fx";

// Technical-showcase landing page (public; middleware allows "/"). The content
// IS the visual — a real API response, the architecture, a data tree, and the
// validation table. No animated background. See
// docs/specs/Heavi_Technical_Homepage_Spec.md.

const GITHUB = "https://github.com/galois-dh/heavi";
const SPECS_URL = `${GITHUB}/tree/main/docs/specs`;
const WHITEPAPER = "/whitepaper.pdf";
const EMAIL = "dhazarik@gmail.com";

// ── Section 2: real scored response for Kern County (35.35, -119.05) ──
const API_RESPONSE = `{
  "location": { "latitude": 35.35, "longitude": -119.05 },
  "score": 78,
  "rating": "High",
  "weight_profile": "WECC (calibrated)",
  "confidence": {
    "tier": "HIGH",
    "composite": 0.95,
    "statement": "Based on authoritative data for all major criteria."
  },
  "criteria": {
    "Transmission proximity": { "score": 86, "source": "HIFLD Transmission Lines", "confidence": "HIGH" },
    "Solar resource (GHI)": { "score": 67, "source": "NREL PVWatts v8", "confidence": "HIGH" },
    "Terrain slope": { "score": 99, "source": "USGS 3D Elevation Program", "confidence": "HIGH" },
    "Road access": { "score": 50, "source": "OpenStreetMap Roads", "confidence": "HIGH" },
    "Terrain aspect": { "score": 100, "source": "USGS 3D Elevation Program", "confidence": "HIGH" },
    "Land cover type": { "score": 10, "source": "National Land Cover Database", "confidence": "HIGH" },
    "Soil buildability": { "score": 100, "source": "USDA SSURGO", "confidence": "HIGH" }
  },
  "exclusions": {
    "Protected areas": { "result": "pass", "source": "USGS PAD-US" },
    "Wetlands": { "result": "pass", "source": "National Wetlands Inventory" },
    "Critical habitat": { "result": "pass", "source": "USFWS" },
    "Steep slope": { "result": "pass", "source": "USGS 3DEP" },
    "Developed land": { "result": "pass", "source": "NLCD 2021" }
  },
  "gaps": [
    { "criterion": "Environmental Justice", "message": "EPA EJScreen discontinued." }
  ],
  "interconnection": {
    "nearest_substation_mi": 1.7,
    "existing_capacity_mw": 314,
    "queue_projects": 52,
    "queue_capacity_mw": 13169,
    "iso": "CAISO"
  }
}`;

// Token-based JSON syntax highlighter. Content is static/trusted, so emitting
// HTML with token <span>s and dangerouslySetInnerHTML is safe here.
const JSON_TOKEN = /("(?:\\.|[^"\\])*"\s*:?|\b(?:true|false|null)\b|-?\d+(?:\.\d+)?)/g;
function highlightJson(src: string): string {
  const escaped = src
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  return escaped.replace(JSON_TOKEN, (tok) => {
    let cls = "tok-num";
    if (tok.startsWith("&quot;") || tok.startsWith('"')) {
      cls = tok.trimEnd().endsWith(":") ? "tok-key" : "tok-str";
    } else if (tok === "true" || tok === "false") {
      cls = "tok-bool";
    } else if (tok === "null") {
      cls = "tok-null";
    }
    return `<span class="${cls}">${tok}</span>`;
  });
}

const PIPELINE = [
  {
    icon: <Database size={20} strokeWidth={1.8} />,
    title: "Data Repository",
    head: "34 sources",
    body: "Federal and open data with availability checking per location.",
  },
  {
    icon: <BookOpen size={20} strokeWidth={1.8} />,
    title: "Methodology Repository",
    head: "31 criteria",
    body: "Data trees and academic citations. Doorga, Hernandez, Huff, Scawthorn, Finney.",
  },
  {
    icon: <Workflow size={20} strokeWidth={1.8} />,
    title: "Data Selection Engine",
    head: "Quality-ordered",
    body: "Traverses trees per criterion. Selects the best source at each location: authoritative → fallback → proxy → gap.",
  },
  {
    icon: <ShieldCheck size={20} strokeWidth={1.8} />,
    title: "Confidence Scoring",
    head: "Five tiers",
    body: "Reports what data was used, where gaps are, and how much to trust the result. HIGH to CANNOT ASSESS.",
  },
];

const TREE = [
  {
    title: "NWI PostGIS",
    kind: "authoritative · confidence 1.0",
    note: "National Wetlands Inventory loaded for Kern County",
    status: "Available at this location",
    tone: "ok",
  },
  {
    title: "NWI REST API",
    kind: "authoritative · confidence 1.0",
    note: "National NWI service (currently degraded)",
    status: "Would try if PostGIS unavailable",
    tone: "idle",
  },
  {
    title: "SSURGO Hydric Proxy",
    kind: "proxy · confidence 0.4",
    note: "Soil-based wetland indicator from USDA",
    status: "Fallback used outside loaded geographies",
    tone: "proxy",
  },
];

const MODULES = [
  {
    icon: <Sun size={22} strokeWidth={1.8} />,
    iconWrap: "bg-amber-500/10 text-amber-300",
    link: "text-amber-300",
    name: "Heavi Energy",
    tag: "Solar site screening",
    specs: "14 criteria · regional weight calibration · 6,321 EIA installations",
    validated: "71% High across 10 states",
    href: "/energy",
  },
  {
    icon: <Flame size={22} strokeWidth={1.8} />,
    iconWrap: "bg-rose-500/10 text-rose-300",
    link: "text-rose-300",
    name: "Heavi Hazard",
    tag: "Wildfire + flood risk",
    specs: "10 criteria · per-peril dollar estimates · NSI building data",
    validated: "AUC 0.76 (Sonoma), 16x discrimination (Lee County)",
    href: "/hazard",
  },
  {
    icon: <Store size={22} strokeWidth={1.8} />,
    iconWrap: "bg-emerald-500/10 text-emerald-300",
    link: "text-emerald-300",
    name: "Heavi Locations",
    tag: "Trade area analysis",
    specs: "7 criteria · Huff gravity model · drive-time isochrones",
    validated: "96.7% Starbucks Strong (Dallas)",
    href: "/locations",
  },
];

const VALIDATION = [
  { state: "Texas", nerc: "ERCOT", eia: "87%", random: "47%", sep: "+0.079" },
  { state: "Arizona", nerc: "WECC", eia: "40%", random: "33%", sep: "+0.220" },
  { state: "North Carolina", nerc: "SERC", eia: "53%", random: "40%", sep: "+0.044" },
  { state: "Nevada", nerc: "WECC", eia: "47%", random: "7%", sep: "+0.204" },
  { state: "Florida", nerc: "SERC", eia: "53%", random: "0%", sep: "+0.184" },
  { state: "California", nerc: "WECC", eia: "53%", random: "33%", sep: "+0.118" },
  { state: "Georgia", nerc: "SERC", eia: "47%", random: "20%", sep: "+0.104" },
  { state: "Colorado", nerc: "WECC", eia: "73%", random: "40%", sep: "+0.190" },
  { state: "Indiana", nerc: "MISO", eia: "40%", random: "20%", sep: "+0.062" },
  { state: "Ohio", nerc: "PJM", eia: "20%", random: "33%", sep: "+0.017" },
];

const CATALOG = [
  { group: "Solar Resource", sources: ["NREL PVWatts v8", "NREL NSRDB"] },
  { group: "Terrain", sources: ["USGS 3DEP"] },
  { group: "Infrastructure", sources: ["HIFLD Transmission", "OSM Substations", "OSM Roads", "EIA Form 860"] },
  { group: "Environmental", sources: ["USFWS NWI", "USFWS Critical Habitat", "USGS PAD-US", "EPA EJScreen"] },
  { group: "Land & Soil", sources: ["MRLC NLCD 2021", "USDA SSURGO"] },
  {
    group: "Hazard",
    sources: ["FEMA NFHL", "USFS FSim", "NIFC Fire Perimeters", "LANDFIRE", "USACE NSI", "HAZUS DDFs", "OpenFEMA", "USGS Peak Flow"],
  },
  { group: "Demographics", sources: ["Census ACS", "Census LEHD"] },
  { group: "POIs", sources: ["OpenStreetMap", "OpenRouteService"] },
  { group: "Interconnection", sources: ["LBNL Queued Up 2025"] },
];

const SPECS = [
  "Platform Architecture — data repository, methodology repository, data selection engine",
  "Methodology & Data Provenance — 31 criteria with academic citations and data trees",
  "Weight Adaptation — NERC regional calibration via constrained optimization",
  "Exclusion Precision — refined thresholds from conservative literature defaults",
  "Workflow Integration — hazard and trade area through the shared architecture",
  "Map Interface — MapLibre GL JS delivery surface",
  "Data Tree Completeness — LANDFIRE and NIFC fallback chains",
  "Insufficient Data Handling — CANNOT ASSESS safety net",
  "Month 1 Sprint — geocoding, batch scoring, PDF export, interconnection",
  "10-State Validation — 300-location validation protocol",
  "Month 2 Sprint — methodology whitepaper, precision framework, sample package",
  "Natural Language Display — human-readable labels replacing technical IDs",
];

const METRICS = [
  { value: "34", label: "data sources integrated" },
  { value: "31", label: "scored criteria across 3 modules" },
  { value: "12", label: "specification documents" },
  { value: "300", label: "locations validated" },
  { value: "14", label: "peer-reviewed citations" },
  { value: "~20", label: "commits from first spec to production" },
];

export default function Home() {
  const highlighted = highlightJson(API_RESPONSE);

  return (
    <div className="relative bg-zinc-950">
      <LandingNav />

      <main>
        {/* ───────────────── Section 1: Hero (clean, no animation) ───────────────── */}
        <section className="flex min-h-[88svh] flex-col items-center justify-center px-6 py-32 text-center">
          <p className="heavi-reveal text-xs font-semibold uppercase tracking-[0.4em] text-amber-400">
            Heavi
          </p>
          <h1
            className="heavi-reveal mx-auto mt-6 max-w-4xl text-5xl font-bold leading-[1.05] tracking-tight text-white md:text-7xl"
            style={{ animationDelay: "0.08s" }}
          >
            Solar siting. Hazard risk. Trade areas.
            <br className="hidden sm:block" />{" "}
            <span className="text-amber-400">Analyzed and auditable.</span>
          </h1>
          <p
            className="heavi-reveal mx-auto mt-7 max-w-2xl text-lg leading-relaxed text-zinc-400"
            style={{ animationDelay: "0.16s" }}
          >
            A spatial analysis platform with 34 federal data sources, confidence
            scoring, and documented methodology.
          </p>
          <div
            className="heavi-reveal mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row"
            style={{ animationDelay: "0.24s" }}
          >
            <Link
              href="/energy"
              className="inline-flex w-full items-center justify-center rounded-lg bg-amber-500 px-6 py-3 text-sm font-semibold text-zinc-950 transition hover:bg-amber-400 sm:w-auto"
            >
              Explore the platform →
            </Link>
            <a
              href={GITHUB}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-zinc-700 px-6 py-3 text-sm font-semibold text-zinc-200 transition hover:border-zinc-500 hover:bg-zinc-900 sm:w-auto"
            >
              <Code2 size={16} strokeWidth={2} />
              View on GitHub →
            </a>
          </div>
        </section>

        {/* ───────────────── Section 2: Live API Response ───────────────── */}
        <Section heading="What the API returns">
          <div className="overflow-hidden rounded-xl border border-zinc-800 bg-[#0d1117] shadow-xl shadow-black/30">
            <div className="flex items-center gap-2 border-b border-zinc-800 bg-zinc-900/60 px-4 py-2.5">
              <span className="h-3 w-3 rounded-full bg-rose-500/70" />
              <span className="h-3 w-3 rounded-full bg-amber-500/70" />
              <span className="h-3 w-3 rounded-full bg-emerald-500/70" />
              <span className="ml-3 font-mono text-xs text-zinc-500">
                POST /solar/score-v2 · 35.35, -119.05
              </span>
            </div>
            <pre className="overflow-x-auto px-5 py-4 font-mono text-[12.5px] leading-relaxed text-zinc-300">
              <code dangerouslySetInnerHTML={{ __html: highlighted }} />
            </pre>
          </div>
          <p className="mt-4 text-sm text-zinc-500">
            Every assessment returns the score, the data source for each
            criterion, the confidence level, and where the gaps are.
          </p>
        </Section>

        {/* ───────────────── Section 3: Architecture Pipeline ───────────────── */}
        <Section heading="How it works" banded>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-4 md:gap-0">
            {PIPELINE.map((p, i) => (
              <div key={p.title} className="flex items-stretch">
                <div className="flex h-full flex-1 flex-col rounded-xl border border-zinc-800 bg-zinc-900/40 p-5 transition hover:border-zinc-600 md:mx-2">
                  <div className="flex items-center justify-between">
                    <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-amber-500/10 text-amber-300">
                      {p.icon}
                    </span>
                    <span className="font-mono text-xs font-bold text-zinc-600">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                  </div>
                  <h3 className="mt-4 text-base font-semibold text-white">{p.title}</h3>
                  <p className="mt-0.5 text-xs font-semibold uppercase tracking-wider text-amber-400/80">
                    {p.head}
                  </p>
                  <p className="mt-2 text-sm leading-relaxed text-zinc-400">{p.body}</p>
                </div>
                {i < PIPELINE.length - 1 && (
                  <span className="hidden items-center px-1 text-zinc-700 md:flex">
                    <ArrowRight size={18} />
                  </span>
                )}
              </div>
            ))}
          </div>
        </Section>

        {/* ───────────────── Section 4: Data Tree Example ───────────────── */}
        <Section heading="Adaptive data selection">
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-6 sm:p-8">
            <p className="font-mono text-sm font-semibold text-white">Wetlands criterion</p>
            <div className="mt-4 ml-2 border-l border-zinc-800 pl-5">
              <div className="space-y-4">
                {TREE.map((n) => {
                  const tone =
                    n.tone === "ok"
                      ? { ring: "border-emerald-500/40", chip: "bg-emerald-500/10 text-emerald-300", icon: <Check size={14} /> }
                      : n.tone === "proxy"
                        ? { ring: "border-amber-500/40", chip: "bg-amber-500/10 text-amber-300", icon: <CornerDownRight size={14} /> }
                        : { ring: "border-zinc-700", chip: "bg-zinc-800 text-zinc-400", icon: <CornerDownRight size={14} /> };
                  return (
                    <div key={n.title} className="relative">
                      <span className="absolute -left-5 top-4 h-px w-4 bg-zinc-800" />
                      <div className={`rounded-lg border bg-zinc-950/40 p-4 ${tone.ring}`}>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className={`flex h-5 w-5 items-center justify-center rounded ${tone.chip}`}>
                            {tone.icon}
                          </span>
                          <span className="font-mono text-sm font-semibold text-white">{n.title}</span>
                          <span className="font-mono text-[11px] text-zinc-500">{n.kind}</span>
                        </div>
                        <p className="mt-2 text-sm text-zinc-400">{n.note}</p>
                        <p className="mt-1 text-xs text-zinc-500">
                          <span className="text-zinc-400">Status:</span> {n.status}
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
          <p className="mt-4 text-sm text-zinc-500">
            At each location, the engine tries the highest-quality source first. If
            unavailable, it falls back and reports reduced confidence. Outside Kern
            County, wetlands data falls back to the SSURGO soil proxy. The output
            tells you exactly which source was used.
          </p>
        </Section>

        {/* ───────────────── Section 5: Three Modules ───────────────── */}
        <Section heading="Three analysis modules" banded>
          <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
            {MODULES.map((m) => (
              <Link
                key={m.name}
                href={m.href}
                className="group flex h-full flex-col rounded-2xl border border-zinc-800 bg-zinc-900/40 p-7 transition duration-300 hover:border-zinc-600 hover:bg-zinc-900/70"
              >
                <span className={`flex h-11 w-11 items-center justify-center rounded-xl ${m.iconWrap}`}>
                  {m.icon}
                </span>
                <h3 className="mt-5 text-lg font-semibold text-white">{m.name}</h3>
                <p className="mt-1 text-sm font-medium text-zinc-400">{m.tag}</p>
                <p className="mt-4 text-sm leading-relaxed text-zinc-400">{m.specs}</p>
                <p className="mt-3 flex-1 text-sm text-zinc-300">
                  <span className="font-semibold text-emerald-300">Validated:</span> {m.validated}
                </p>
                <span className={`mt-6 text-sm font-semibold ${m.link} transition group-hover:translate-x-0.5`}>
                  Try it →
                </span>
              </Link>
            ))}
          </div>
        </Section>

        {/* ───────────────── Section 6: Validation Results ───────────────── */}
        <Section heading="10-state solar validation">
          <div className="overflow-x-auto rounded-xl border border-zinc-800">
            <table className="w-full min-w-[560px] text-left text-sm">
              <thead>
                <tr className="border-b border-zinc-800 bg-zinc-900/60 text-xs uppercase tracking-wider text-zinc-500">
                  <th className="px-4 py-3 font-semibold">State</th>
                  <th className="px-4 py-3 font-semibold">NERC</th>
                  <th className="px-4 py-3 font-semibold">EIA %High</th>
                  <th className="px-4 py-3 font-semibold">Random %High</th>
                  <th className="px-4 py-3 font-semibold">Separation</th>
                </tr>
              </thead>
              <tbody>
                {VALIDATION.map((r) => (
                  <tr
                    key={r.state}
                    className="border-b border-zinc-900 text-zinc-300 transition hover:bg-zinc-900/40"
                  >
                    <td className="px-4 py-3 font-medium text-white">{r.state}</td>
                    <td className="px-4 py-3 font-mono text-zinc-400">{r.nerc}</td>
                    <td className="px-4 py-3 tabular-nums">{r.eia}</td>
                    <td className="px-4 py-3 tabular-nums text-zinc-400">{r.random}</td>
                    <td className="px-4 py-3 font-mono tabular-nums font-semibold text-emerald-400">
                      {r.sep}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-4 text-sm text-zinc-500">
            300 locations (150 real EIA installations + 150 matched random rural).
            71% of greenfield-eligible installations score High. Positive
            discrimination in all 10 states.
          </p>
        </Section>

        {/* ───────────────── Section 7: Data Source Catalog ───────────────── */}
        <Section heading="34 federal and open data sources" banded>
          <div className="grid grid-cols-1 gap-x-8 gap-y-6 sm:grid-cols-2 lg:grid-cols-3">
            {CATALOG.map((c) => (
              <div key={c.group}>
                <p className="text-xs font-semibold uppercase tracking-wider text-amber-400/80">
                  {c.group}
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {c.sources.map((s) => (
                    <span
                      key={s}
                      className="rounded-md border border-zinc-800 bg-zinc-900/60 px-2.5 py-1 font-mono text-xs text-zinc-300"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Section>

        {/* ───────────────── Section 8: The Specifications ───────────────── */}
        <Section heading="Built from specifications">
          <p className="max-w-3xl text-base leading-relaxed text-zinc-400">
            This platform was built using spec-driven development. Each feature
            started as a detailed specification document with data models, API
            endpoints, and acceptance criteria. Claude Code read the spec and
            implemented it.
          </p>
          <ol className="mt-8 grid grid-cols-1 gap-3 md:grid-cols-2">
            {SPECS.map((s, i) => (
              <li key={i}>
                <a
                  href={SPECS_URL}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="flex h-full gap-3 rounded-lg border border-zinc-800 bg-zinc-900/30 p-4 transition hover:border-zinc-600 hover:bg-zinc-900/60"
                >
                  <span className="font-mono text-xs font-bold text-amber-400/80">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <span className="text-sm leading-relaxed text-zinc-300">{s}</span>
                </a>
              </li>
            ))}
          </ol>
          <p className="mt-6 text-sm text-zinc-500">
            12 specifications. Every acceptance criterion traced to a commit.
          </p>
        </Section>

        {/* ───────────────── Section 9: Build Metrics ───────────────── */}
        <Section heading="Build metrics" banded>
          <div className="grid grid-cols-2 gap-x-6 gap-y-10 md:grid-cols-3 lg:grid-cols-6">
            {METRICS.map((m) => (
              <div key={m.label}>
                <div className="font-mono text-4xl font-bold tracking-tight text-white">
                  {m.value}
                </div>
                <div className="mt-2 text-xs leading-snug text-zinc-500">{m.label}</div>
              </div>
            ))}
          </div>
        </Section>

        {/* ───────────────── Section 10: Footer ───────────────── */}
        <footer className="border-t border-zinc-900 px-6 py-12">
          <div className="mx-auto max-w-5xl space-y-2 font-mono text-sm text-zinc-500">
            <p>
              Code:{" "}
              <a href={GITHUB} target="_blank" rel="noreferrer noopener" className="text-zinc-300 hover:text-amber-300">
                github.com/galois-dh/heavi
              </a>
            </p>
            <p>
              Whitepaper:{" "}
              <a href={WHITEPAPER} target="_blank" rel="noreferrer noopener" className="text-zinc-300 hover:text-amber-300">
                heavi-web.vercel.app/whitepaper.pdf
              </a>
            </p>
            <p>
              Built by Danial Hazarika ·{" "}
              <a href={`mailto:${EMAIL}`} className="text-zinc-300 hover:text-amber-300">
                {EMAIL}
              </a>
            </p>
          </div>
        </footer>
      </main>
    </div>
  );
}

/* ─────────────────────────── Section wrapper ─────────────────────────── */

function Section({
  heading,
  banded,
  children,
}: {
  heading: string;
  banded?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section className={banded ? "border-y border-zinc-900 bg-zinc-900/20" : ""}>
      <div className="mx-auto max-w-5xl px-6 py-20">
        <Reveal>
          <h2 className="text-3xl font-bold tracking-tight text-white">{heading}</h2>
          <div className="mt-10">{children}</div>
        </Reveal>
      </div>
    </section>
  );
}
