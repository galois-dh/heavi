import Link from "next/link";
import {
  Database,
  BookOpen,
  Workflow,
  ShieldCheck,
  Sun,
  Flame,
  Store,
  Map as MapIcon,
  FileText,
  MapPin,
  Layers,
  Bot,
  Tag,
  Code2,
} from "lucide-react";
import { LandingNav } from "../components/landing-nav";
import { Reveal, StatCounter } from "../components/landing-fx";

// Public portfolio landing page (middleware allows "/"). Frames Heavi as a
// platform: a four-layer architecture for auditable spatial analysis, with three
// equally-weighted modules built on shared infrastructure.

const GITHUB = "https://github.com/galois-dh/heavi";
const WHITEPAPER = "/whitepaper.pdf";

const STATS = [
  { value: 6321, label: "installations validated" },
  { value: 10, label: "states validated" },
  { value: 15, label: "federal data sources" },
  { value: 4426, label: "queue projects tracked" },
];

// Drifting concentric contour rings on the hero backdrop. Each pair shares a
// center (cx/cy) and a drift animation so they stay concentric while moving.
const RINGS = [
  { cx: "26%", cy: "34%", size: 460, color: "rgba(245,158,11,0.22)", drift: "a" },
  { cx: "26%", cy: "34%", size: 720, color: "rgba(245,158,11,0.13)", drift: "a" },
  { cx: "80%", cy: "60%", size: 520, color: "rgba(96,165,250,0.20)", drift: "b" },
  { cx: "80%", cy: "60%", size: 820, color: "rgba(96,165,250,0.12)", drift: "b" },
  { cx: "52%", cy: "46%", size: 1040, color: "rgba(244,244,245,0.08)", drift: "c" },
];

// Glowing "map point" dots scattered across the hero backdrop. Timing/size vary
// per dot so the pulse looks organic rather than synchronized.
const DOTS = [
  { top: "26%", left: "14%", color: "#fbbf24", size: 9, d: "2.4s", delay: "0s" },
  { top: "38%", left: "84%", color: "#60a5fa", size: 8, d: "2.8s", delay: "0.6s" },
  { top: "62%", left: "22%", color: "#60a5fa", size: 7, d: "2.2s", delay: "0.3s" },
  { top: "70%", left: "72%", color: "#fbbf24", size: 9, d: "3s", delay: "1s" },
  { top: "18%", left: "60%", color: "#fbbf24", size: 7, d: "2.6s", delay: "0.15s" },
  { top: "52%", left: "48%", color: "#60a5fa", size: 8, d: "2s", delay: "0.8s" },
];

const LAYERS = [
  {
    icon: <Database size={22} strokeWidth={1.8} />,
    title: "Data Repository",
    body: "34 federal and open datasets with per-source availability checking, so the platform knows what data actually exists at a location before it scores anything.",
  },
  {
    icon: <BookOpen size={22} strokeWidth={1.8} />,
    title: "Methodology Repository",
    body: "31 scored criteria, each with a quality-ordered data tree and academic citations grounding its weight, thresholds, and normalization.",
  },
  {
    icon: <Workflow size={22} strokeWidth={1.8} />,
    title: "Data Selection Engine",
    body: "Traverses each criterion's tree and selects the best available source at that exact location, falling back to documented proxies when authoritative data is missing.",
  },
  {
    icon: <ShieldCheck size={22} strokeWidth={1.8} />,
    title: "Confidence Scoring",
    body: "Reports which data was actually used, where the gaps are, and how much to trust the result — a weakest-link confidence tier, never a silent default.",
  },
];

const MODULES = [
  {
    icon: <Sun size={22} strokeWidth={1.8} />,
    iconWrap: "bg-amber-500/10 text-amber-300",
    link: "text-amber-300",
    name: "Heavi Energy",
    tag: "Solar site screening",
    body: "14 criteria, regional weight calibration against 6,321 EIA installations, interconnection queue context from 4,426 LBNL projects, batch scoring with map visualization.",
    href: "/energy",
  },
  {
    icon: <Flame size={22} strokeWidth={1.8} />,
    iconWrap: "bg-rose-500/10 text-rose-300",
    link: "text-rose-300",
    name: "Heavi Hazard",
    tag: "Wildfire + flood risk",
    body: "10 criteria, per-peril dollar estimates with NSI building data, NIFC + LANDFIRE fallback chains, multi-geography validation.",
    href: "/hazard",
  },
  {
    icon: <Store size={22} strokeWidth={1.8} />,
    iconWrap: "bg-emerald-500/10 text-emerald-300",
    link: "text-emerald-300",
    name: "Heavi Locations",
    tag: "Trade area analysis",
    body: "7 criteria, Huff gravity model, Census demographics, competitive density, drive-time isochrones, 96.7% Starbucks validation.",
    href: "/locations",
  },
];

const INFRA = [
  {
    icon: <MapIcon size={20} strokeWidth={1.8} />,
    title: "Map-based delivery",
    body: "MapLibre GL JS with toggleable constraint layers.",
  },
  {
    icon: <FileText size={20} strokeWidth={1.8} />,
    title: "PDF export",
    body: "Audit-ready reports with full methodology documentation.",
  },
  {
    icon: <MapPin size={20} strokeWidth={1.8} />,
    title: "Address geocoding",
    body: "Census geocoder with Nominatim fallback.",
  },
  {
    icon: <Layers size={20} strokeWidth={1.8} />,
    title: "Batch scoring",
    body: "Up to 200 locations per run.",
  },
  {
    icon: <Bot size={20} strokeWidth={1.8} />,
    title: "MCP tools",
    body: "Spatial tools exposed for AI-agent consumption.",
  },
  {
    icon: <Tag size={20} strokeWidth={1.8} />,
    title: "Natural-language labels",
    body: "Human-readable names throughout, never raw IDs.",
  },
];

export default function Home() {
  return (
    <div className="relative bg-zinc-950">
      <LandingNav />

      <main>
        {/* ───────────────────────── Section 1: Hero ───────────────────────── */}
        <section className="relative flex min-h-[100svh] flex-col overflow-hidden">
          {/* Animated, CSS-only backdrop: topographic contours, atmospheric
              glow, pulsing map points, and a fade into the page below. */}
          <div aria-hidden className="pointer-events-none absolute inset-0">
            <div
              className="absolute inset-0"
              style={{
                background:
                  "radial-gradient(60% 55% at 50% 8%, rgba(245,158,11,0.16) 0%, rgba(245,158,11,0) 60%), radial-gradient(45% 45% at 82% 28%, rgba(59,130,246,0.12) 0%, rgba(59,130,246,0) 70%)",
              }}
            />
            {RINGS.map((r, i) => (
              <span
                key={`ring-${i}`}
                className={`hero-ring hero-ring-${r.drift}`}
                style={{
                  left: r.cx,
                  top: r.cy,
                  width: r.size,
                  height: r.size,
                  marginLeft: -r.size / 2,
                  marginTop: -r.size / 2,
                  borderColor: r.color,
                }}
              />
            ))}
            {DOTS.map((dot, i) => (
              <span
                key={i}
                className="map-dot absolute rounded-full"
                style={
                  {
                    top: dot.top,
                    left: dot.left,
                    width: dot.size,
                    height: dot.size,
                    background: dot.color,
                    boxShadow: `0 0 ${dot.size * 2.4}px ${dot.color}`,
                    "--d": dot.d,
                    "--delay": dot.delay,
                  } as React.CSSProperties
                }
              />
            ))}
            <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-b from-transparent to-zinc-950" />
          </div>

          {/* Hero content */}
          <div className="relative z-10 flex flex-1 flex-col items-center justify-center px-6 pb-12 pt-28 text-center">
            <p className="heavi-reveal text-xs font-semibold uppercase tracking-[0.4em] text-amber-400">
              Heavi
            </p>
            <h1
              className="heavi-reveal mx-auto mt-6 max-w-5xl text-5xl font-bold leading-[1.04] tracking-tight text-white md:text-7xl"
              style={{ animationDelay: "0.08s" }}
            >
              Deterministic spatial analysis with confidence scoring.
            </h1>
            <p
              className="heavi-reveal mx-auto mt-7 max-w-2xl text-lg leading-relaxed text-zinc-400"
              style={{ animationDelay: "0.16s" }}
            >
              A platform that scores any US location against federal data sources,
              tells you which data was actually available, and documents the
              methodology behind every output. Built solo with Claude Code.
            </p>

            <div
              className="heavi-reveal mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row"
              style={{ animationDelay: "0.3s" }}
            >
              <Link
                href="/energy"
                className="inline-flex w-full items-center justify-center rounded-lg bg-amber-500 px-6 py-3 text-sm font-semibold text-zinc-950 shadow-lg shadow-amber-500/25 transition hover:bg-amber-400 sm:w-auto"
              >
                Explore the platform →
              </Link>
              <a
                href={GITHUB}
                target="_blank"
                rel="noreferrer noopener"
                className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-zinc-700 bg-zinc-950/40 px-6 py-3 text-sm font-semibold text-zinc-200 backdrop-blur-sm transition hover:border-zinc-500 hover:bg-zinc-900 sm:w-auto"
              >
                <Code2 size={16} strokeWidth={2} />
                Read the code →
              </a>
            </div>
          </div>

          {/* Stat counters — animate up from 0 when the row scrolls into view. */}
          <div className="relative z-10 border-t border-zinc-900/70 px-6 pb-12">
            <div className="mx-auto grid max-w-5xl grid-cols-2 gap-x-6 gap-y-8 py-8 md:grid-cols-4">
              {STATS.map((s) => (
                <StatCounter key={s.label} value={s.value} label={s.label} />
              ))}
            </div>
          </div>
        </section>

        {/* ─────────────── Section 2: Architecture (How it works) ─────────────── */}
        <section className="border-y border-zinc-900 bg-zinc-900/20">
          <div className="mx-auto max-w-5xl px-6 py-24">
            <Reveal>
              <SectionLabel>How it works</SectionLabel>
              <h2 className="mt-4 text-3xl font-bold tracking-tight text-white sm:text-4xl">
                A four-layer architecture for auditable spatial analysis
              </h2>
              <p className="mt-4 max-w-2xl text-base leading-relaxed text-zinc-400">
                Every output traces through the same pipeline: known data,
                documented methodology, the best available source per criterion,
                and an honest confidence score. This is the technical
                differentiator.
              </p>
            </Reveal>

            <div className="mt-12">
              {LAYERS.map((l, i) => (
                <Reveal key={l.title} delay={i * 80}>
                  <LayerCard
                    index={i + 1}
                    icon={l.icon}
                    title={l.title}
                    body={l.body}
                    last={i === LAYERS.length - 1}
                  />
                </Reveal>
              ))}
            </div>
          </div>
        </section>

        {/* ─────────────── Section 3: Three modules (equal weight) ─────────────── */}
        <section className="mx-auto max-w-6xl px-6 py-24">
          <Reveal>
            <SectionLabel>Three modules, one engine</SectionLabel>
            <p className="mt-4 max-w-2xl text-base leading-relaxed text-zinc-400">
              The same data-selection and confidence-scoring engine powers three
              domains. Each is independently validated against real-world ground
              truth.
            </p>
          </Reveal>
          <div className="mt-12 grid grid-cols-1 gap-5 md:grid-cols-3">
            {MODULES.map((m, i) => (
              <Reveal key={m.name} delay={i * 120}>
                <ModuleCard {...m} />
              </Reveal>
            ))}
          </div>
        </section>

        {/* ─────────────── Section 4: Shared infrastructure ─────────────── */}
        <section className="border-y border-zinc-900 bg-zinc-900/20">
          <div className="mx-auto max-w-6xl px-6 py-24">
            <Reveal>
              <SectionLabel>Shared infrastructure</SectionLabel>
              <p className="mt-4 max-w-2xl text-base leading-relaxed text-zinc-400">
                Every module inherits the same delivery, export, and integration
                layer.
              </p>
            </Reveal>
            <div className="mt-12 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {INFRA.map((f, i) => (
                <Reveal key={f.title} delay={(i % 3) * 100}>
                  <InfraItem icon={f.icon} title={f.title} body={f.body} />
                </Reveal>
              ))}
            </div>
          </div>
        </section>

        {/* ─────────────── Section 5: Built with AI ─────────────── */}
        <section className="mx-auto max-w-5xl px-6 py-24">
          <Reveal>
            <div className="relative overflow-hidden rounded-2xl border border-amber-500/30 bg-gradient-to-br from-amber-500/15 via-amber-500/5 to-zinc-900/0 px-8 py-14 sm:px-14">
              <SectionLabel>Built with AI</SectionLabel>
              <h2 className="mt-4 max-w-3xl text-2xl font-bold tracking-tight text-white sm:text-3xl">
                One person. Spec-driven development.
              </h2>
              <p className="mt-4 max-w-2xl text-base leading-relaxed text-zinc-300">
                This entire platform was built by one person using Claude Code and
                spec-driven development. Every spec is in the repo. Every commit
                traces to a specification.
              </p>
              <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                <a
                  href={GITHUB}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="inline-flex items-center justify-center gap-2 rounded-lg bg-amber-500 px-6 py-3 text-sm font-semibold text-zinc-950 shadow-lg shadow-amber-500/25 transition hover:bg-amber-400"
                >
                  <Code2 size={16} strokeWidth={2} />
                  View the code on GitHub →
                </a>
                <a
                  href={WHITEPAPER}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="inline-flex items-center justify-center rounded-lg border border-zinc-700 px-6 py-3 text-sm font-semibold text-zinc-200 transition hover:border-zinc-500 hover:bg-zinc-900"
                >
                  Read the methodology whitepaper →
                </a>
              </div>
            </div>
          </Reveal>
        </section>

        {/* ─────────────────────────── Footer ─────────────────────────── */}
        <footer className="border-t border-zinc-900 px-6 py-10">
          <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 text-xs text-zinc-500 sm:flex-row">
            <span>Heavi · Deterministic spatial analysis</span>
            <span className="flex flex-wrap items-center justify-center gap-x-2 gap-y-1">
              Code:{" "}
              <a
                href={GITHUB}
                target="_blank"
                rel="noreferrer noopener"
                className="text-zinc-300 transition hover:text-amber-300"
              >
                github.com/galois-dh/heavi
              </a>
              <span className="text-zinc-700">|</span>
              Whitepaper:{" "}
              <a
                href={WHITEPAPER}
                target="_blank"
                rel="noreferrer noopener"
                className="text-zinc-300 transition hover:text-amber-300"
              >
                methodology (PDF)
              </a>
            </span>
          </div>
        </footer>
      </main>
    </div>
  );
}

/* ─────────────────────────── Presentational bits ─────────────────────────── */

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-xs font-semibold uppercase tracking-[0.3em] text-amber-400/90">
      {children}
    </p>
  );
}

function LayerCard({
  index,
  icon,
  title,
  body,
  last,
}: {
  index: number;
  icon: React.ReactNode;
  title: string;
  body: string;
  last: boolean;
}) {
  return (
    <div>
      <div className="flex gap-5 rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6 transition duration-300 hover:border-zinc-600 hover:bg-zinc-900/70">
        <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-amber-500/10 text-amber-300">
          {icon}
        </span>
        <div className="flex-1">
          <div className="flex items-baseline gap-3">
            <span className="text-xs font-bold tabular-nums text-amber-400/80">
              {String(index).padStart(2, "0")}
            </span>
            <h3 className="text-lg font-semibold text-white">{title}</h3>
          </div>
          <p className="mt-2 text-sm leading-relaxed text-zinc-400">{body}</p>
        </div>
      </div>
      {!last && (
        <div
          aria-hidden
          className="ml-[2.75rem] h-5 w-px bg-gradient-to-b from-amber-500/50 to-zinc-800"
        />
      )}
    </div>
  );
}

function ModuleCard({
  icon,
  iconWrap,
  link,
  name,
  tag,
  body,
  href,
}: {
  icon: React.ReactNode;
  iconWrap: string;
  link: string;
  name: string;
  tag: string;
  body: string;
  href: string;
}) {
  return (
    <Link
      href={href}
      className="group flex h-full flex-col rounded-2xl border border-zinc-800 bg-zinc-900/40 p-7 transition duration-300 hover:border-zinc-600 hover:bg-zinc-900/70"
    >
      <span
        className={`flex h-11 w-11 items-center justify-center rounded-xl ${iconWrap}`}
      >
        {icon}
      </span>
      <h3 className="mt-5 text-lg font-semibold text-white">{name}</h3>
      <p className="mt-1 text-sm font-medium text-zinc-400">{tag}</p>
      <p className="mt-4 flex-1 text-sm leading-relaxed text-zinc-400">{body}</p>
      <span
        className={`mt-6 text-sm font-semibold ${link} transition group-hover:translate-x-0.5`}
      >
        Try it →
      </span>
    </Link>
  );
}

function InfraItem({
  icon,
  title,
  body,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
}) {
  return (
    <div className="flex h-full gap-4 rounded-xl border border-zinc-800 bg-zinc-900/30 p-5 transition hover:border-zinc-700">
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-zinc-800/80 text-zinc-300">
        {icon}
      </span>
      <div>
        <h3 className="text-sm font-semibold text-white">{title}</h3>
        <p className="mt-1 text-sm leading-relaxed text-zinc-400">{body}</p>
      </div>
    </div>
  );
}
