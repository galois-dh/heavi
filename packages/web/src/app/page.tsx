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
import { Reveal } from "../components/landing-fx";

// Public portfolio landing page (middleware allows "/"). Frames Heavi as a
// platform: lead with what you can do (three modules), then how it works (the
// four-layer architecture), on shared infrastructure.

const GITHUB = "https://github.com/galois-dh/heavi";
const WHITEPAPER = "/whitepaper.pdf";

// Faint drifting contour rings — now terrain texture (very low opacity), not a
// focal point. Each pair shares a center (cx/cy) + drift so they stay concentric.
const RINGS = [
  { cx: "26%", cy: "34%", size: 460, color: "rgba(245,158,11,0.08)", drift: "a" },
  { cx: "26%", cy: "34%", size: 720, color: "rgba(245,158,11,0.05)", drift: "a" },
  { cx: "80%", cy: "60%", size: 520, color: "rgba(96,165,250,0.07)", drift: "b" },
  { cx: "80%", cy: "60%", size: 820, color: "rgba(96,165,250,0.05)", drift: "b" },
  { cx: "52%", cy: "46%", size: 1040, color: "rgba(244,244,245,0.05)", drift: "c" },
];

// Glowing "analysis" clusters at approximate US geographic positions across the
// hero. Varying sizes suggest different analysis densities. Each pulses softly.
const CLUSTERS = [
  { left: "15%", top: "42%", size: 120, d: "7s", delay: "0s" },
  { left: "23%", top: "60%", size: 70, d: "9s", delay: "1.4s" },
  { left: "38%", top: "33%", size: 95, d: "8s", delay: "0.7s" },
  { left: "50%", top: "54%", size: 60, d: "6.5s", delay: "2.1s" },
  { left: "57%", top: "30%", size: 85, d: "10s", delay: "0.3s" },
  { left: "69%", top: "46%", size: 110, d: "7.5s", delay: "1.1s" },
  { left: "80%", top: "32%", size: 75, d: "8.5s", delay: "2.4s" },
  { left: "85%", top: "56%", size: 50, d: "6s", delay: "0.6s" },
  { left: "32%", top: "72%", size: 65, d: "9.5s", delay: "1.8s" },
  { left: "63%", top: "68%", size: 45, d: "7s", delay: "3s" },
];

// Tiny particles drifting upward at different rates, like data points rising
// from the terrain. Hardcoded (not random) to keep SSR/client markup identical.
const PARTICLES = [
  { left: "9%", top: "68%", size: 3, dur: "12s", delay: "0s", color: "#fbbf24" },
  { left: "17%", top: "82%", size: 2, dur: "15s", delay: "2.1s", color: "#cbd5e1" },
  { left: "26%", top: "55%", size: 4, dur: "10s", delay: "1.2s", color: "#fbbf24" },
  { left: "31%", top: "78%", size: 2, dur: "14s", delay: "3.4s", color: "#cbd5e1" },
  { left: "38%", top: "63%", size: 3, dur: "11s", delay: "0.6s", color: "#fbbf24" },
  { left: "44%", top: "84%", size: 2, dur: "16s", delay: "2.8s", color: "#cbd5e1" },
  { left: "49%", top: "58%", size: 3, dur: "9s", delay: "1.7s", color: "#fbbf24" },
  { left: "55%", top: "75%", size: 2, dur: "13s", delay: "0.3s", color: "#cbd5e1" },
  { left: "61%", top: "62%", size: 4, dur: "10.5s", delay: "2.4s", color: "#fbbf24" },
  { left: "66%", top: "80%", size: 2, dur: "15.5s", delay: "1s", color: "#cbd5e1" },
  { left: "72%", top: "57%", size: 3, dur: "11.5s", delay: "3s", color: "#fbbf24" },
  { left: "77%", top: "73%", size: 2, dur: "14.5s", delay: "0.9s", color: "#cbd5e1" },
  { left: "83%", top: "64%", size: 3, dur: "9.5s", delay: "2.2s", color: "#fbbf24" },
  { left: "88%", top: "79%", size: 2, dur: "13.5s", delay: "1.5s", color: "#cbd5e1" },
  { left: "13%", top: "50%", size: 2, dur: "16s", delay: "3.6s", color: "#cbd5e1" },
  { left: "42%", top: "48%", size: 3, dur: "12.5s", delay: "0.4s", color: "#fbbf24" },
  { left: "70%", top: "50%", size: 2, dur: "15s", delay: "2.6s", color: "#cbd5e1" },
  { left: "92%", top: "46%", size: 3, dur: "10s", delay: "1.9s", color: "#fbbf24" },
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
          {/* Satellite-view backdrop: dark terrain at night with amber analysis
              hotspots. CSS-only (gradients + transform/opacity animations); the
              parallax is a CSS scroll-driven enhancement, no JavaScript. */}
          <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
            {/* Dark terrain base — layered gradients for depth + noise-like
                variation; lighter toward center, darker at the edges. */}
            <div
              className="absolute inset-0"
              style={{
                backgroundColor: "#0a0f1a",
                backgroundImage: [
                  "radial-gradient(90% 75% at 50% 30%, rgba(17,24,39,0.85) 0%, rgba(13,17,23,0) 60%)",
                  "radial-gradient(55% 50% at 18% 72%, rgba(15,23,42,0.55) 0%, rgba(10,15,26,0) 70%)",
                  "radial-gradient(52% 50% at 82% 64%, rgba(17,24,39,0.5) 0%, rgba(10,15,26,0) 70%)",
                  "radial-gradient(45% 40% at 66% 22%, rgba(13,17,23,0.6) 0%, rgba(10,15,26,0) 72%)",
                  "radial-gradient(120% 120% at 50% 0%, rgba(20,28,46,0.35) 0%, rgba(10,15,26,0) 55%)",
                ].join(", "),
              }}
            />

            {/* Atmospheric haze band across the horizon. */}
            <div
              className="absolute inset-x-0 top-1/2 h-48 -translate-y-1/2"
              style={{
                background:
                  "linear-gradient(180deg, rgba(30,58,138,0) 0%, rgba(30,58,138,0.13) 50%, rgba(30,58,138,0) 100%)",
              }}
            />

            {/* Faint contour rings — terrain texture. */}
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

            {/* Glowing analysis clusters (parallax-slow). */}
            <div className="parallax-clusters absolute inset-0">
              {CLUSTERS.map((c, i) => (
                <span
                  key={`cluster-${i}`}
                  className="hero-cluster absolute rounded-full"
                  style={
                    {
                      left: c.left,
                      top: c.top,
                      width: c.size,
                      height: c.size,
                      marginLeft: -c.size / 2,
                      marginTop: -c.size / 2,
                      background:
                        "radial-gradient(circle, rgba(251,191,36,0.55) 0%, rgba(251,191,36,0.14) 42%, rgba(251,191,36,0) 70%)",
                      "--d": c.d,
                      "--delay": c.delay,
                    } as React.CSSProperties
                  }
                />
              ))}
            </div>

            {/* Floating data particles rising from the terrain (parallax-fast). */}
            <div className="parallax-particles absolute inset-0">
              {PARTICLES.map((p, i) => (
                <span
                  key={`particle-${i}`}
                  className="hero-particle absolute rounded-full"
                  style={
                    {
                      left: p.left,
                      top: p.top,
                      width: p.size,
                      height: p.size,
                      background: p.color,
                      "--dur": p.dur,
                      "--delay": p.delay,
                    } as React.CSSProperties
                  }
                />
              ))}
            </div>

            {/* Fade into the page below. */}
            <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-b from-transparent to-zinc-950" />
          </div>

          {/* Hero content */}
          <div className="relative z-10 flex flex-1 flex-col items-center justify-center px-6 pb-12 pt-28 text-center">
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
              Three spatial analysis modules built on shared infrastructure. 34
              federal data sources with a data selection engine that reports which
              sources were available at each location, where the gaps are, and the
              academic methodology behind every criterion.
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
                View on GitHub →
              </a>
            </div>
          </div>
        </section>

        {/* ─────────────── Section 2: Three modules (equal weight) ─────────────── */}
        <section className="mx-auto max-w-6xl px-6 py-24">
          <Reveal>
            <SectionLabel>What you can do</SectionLabel>
            <p className="mt-4 max-w-2xl text-base leading-relaxed text-zinc-400">
              Three modules, one engine. Each scores a different domain and is
              independently validated against real-world ground truth.
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

        {/* ─────────────── Section 3: Architecture (How it works) ─────────────── */}
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

        {/* ─────────────── Section 4: Shared infrastructure ─────────────── */}
        <section className="mx-auto max-w-6xl px-6 py-24">
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
