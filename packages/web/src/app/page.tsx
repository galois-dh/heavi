import Link from "next/link";
import { Upload, Map as MapIcon, FileText } from "lucide-react";
import { LandingNav } from "../components/landing-nav";
import { Reveal, StatCounter } from "../components/landing-fx";

// The landing page is public (middleware allows "/"). It is solar-first: the
// hero, "how it works", and "what makes this different" all speak to a VP of
// Site Development screening solar sites. Hazard and Locations are secondary.
// See docs/specs/Heavi_Landing_Page_Spec.md.

const STATS = [
  { value: 6321, label: "installations validated" },
  { value: 10, label: "states · 5 NERC regions" },
  { value: 15, label: "federal data sources" },
  { value: 4426, label: "active queue projects" },
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

export default function Home() {
  // Public demo: "Start screening" goes straight to the (now public) product.
  const startHref = "/energy";

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
              className="heavi-reveal mt-6 text-6xl font-bold leading-[1.02] tracking-tight text-white md:text-8xl"
              style={{ animationDelay: "0.08s" }}
            >
              Screen solar sites in
              <br className="hidden sm:block" /> minutes, not months.
            </h1>
            <p
              className="heavi-reveal mx-auto mt-7 max-w-2xl text-lg leading-relaxed text-zinc-400"
              style={{ animationDelay: "0.16s" }}
            >
              Score candidate parcels against 15 federal data sources. See which
              sites are worth developing, which are constrained, and how
              confident you should be in each assessment.
            </p>
            <p
              className="heavi-reveal mx-auto mt-4 max-w-2xl text-base leading-relaxed text-zinc-500"
              style={{ animationDelay: "0.22s" }}
            >
              Every result includes the methodology documentation your lender can
              audit.
            </p>

            <div
              className="heavi-reveal mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row"
              style={{ animationDelay: "0.3s" }}
            >
              <Link
                href={startHref}
                className="inline-flex w-full items-center justify-center rounded-lg bg-amber-500 px-6 py-3 text-sm font-semibold text-zinc-950 shadow-lg shadow-amber-500/25 transition hover:bg-amber-400 sm:w-auto"
              >
                Start screening →
              </Link>
              <Link
                href="/sample-assessment.pdf"
                target="_blank"
                className="inline-flex w-full items-center justify-center rounded-lg border border-zinc-700 bg-zinc-950/40 px-6 py-3 text-sm font-semibold text-zinc-200 backdrop-blur-sm transition hover:border-zinc-500 hover:bg-zinc-900 sm:w-auto"
              >
                See a sample assessment →
              </Link>
            </div>

            <p
              className="heavi-reveal mt-10 inline-flex items-center gap-2 rounded-full border border-zinc-800 bg-zinc-900/60 px-4 py-1.5 text-xs text-zinc-400 backdrop-blur-sm"
              style={{ animationDelay: "0.38s" }}
            >
              <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
              Validated against 6,321 real US solar installations across 10
              states.
            </p>
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

        {/* ─────────────────── Section 2: How It Works ─────────────────── */}
        <section className="mx-auto max-w-6xl px-6 py-24">
          <Reveal>
            <SectionLabel>How it works</SectionLabel>
          </Reveal>
          <div className="mt-10 grid grid-cols-1 gap-5 md:grid-cols-3">
            <Reveal>
              <StepCard
                step="01"
                icon={<Upload size={22} strokeWidth={1.8} />}
                title="Upload your parcels"
                body="Drop a CSV of coordinates or addresses, or type a single location into the search bar. Batch up to 200 parcels at once."
              />
            </Reveal>
            <Reveal delay={120}>
              <StepCard
                step="02"
                icon={<MapIcon size={22} strokeWidth={1.8} />}
                title="See scored results on the map"
                body="Every parcel color-coded by suitability, ranked in a sidebar. Interconnection queue context from 4,426 active solar projects. Toggle constraint layers: protected areas, flood zones, transmission lines."
              />
            </Reveal>
            <Reveal delay={240}>
              <StepCard
                step="03"
                icon={<FileText size={22} strokeWidth={1.8} />}
                title="Export audit-ready PDFs"
                body="Per-site or portfolio. Score, confidence level, data sources used, methodology citations, known limitations. Hand it to your investment committee or your lender."
              />
            </Reveal>
          </div>
        </section>

        {/* ───────────── Section 3: What Makes This Different ───────────── */}
        <section className="border-y border-zinc-900 bg-zinc-900/20">
          <div className="mx-auto max-w-5xl px-6 py-24">
            <Reveal>
              <SectionLabel>What makes this different</SectionLabel>
            </Reveal>
            <div className="mt-12 space-y-12">
              <Reveal>
                <DiffBlock title="You know the score AND how much to trust it.">
                  Every assessment reports which federal data was available at
                  that location, which criteria used authoritative versus proxy
                  sources, and where the gaps are. No other screening tool tells
                  you this.
                </DiffBlock>
              </Reveal>
              <Reveal>
                <DiffBlock title="Methodology your lender can verify.">
                  14 criteria grounded in peer-reviewed literature. Weights
                  calibrated per grid region against real solar installation
                  records. Published whitepaper with full validation results.
                </DiffBlock>
              </Reveal>
              <Reveal>
                <DiffBlock title="Interconnection context built in.">
                  4,426 active solar projects from a national interconnection
                  queue dataset. See existing capacity and queue activity near
                  every scored parcel before you file an interconnection
                  application.
                </DiffBlock>
              </Reveal>
            </div>
          </div>
        </section>

        {/* ───────────────── Section 4: Market Validation ───────────────── */}
        <section className="mx-auto max-w-4xl px-6 py-24">
          <Reveal>
            <figure className="relative overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-900/50 p-10 sm:p-14">
              <span
                aria-hidden
                className="absolute -left-1 -top-6 select-none font-serif text-[10rem] leading-none text-amber-500/15"
              >
                &ldquo;
              </span>
              <blockquote className="relative space-y-5 text-xl leading-relaxed text-zinc-200 sm:text-2xl">
                <p>
                  The world&rsquo;s largest renewable energy company automated
                  their solar site selection against the same criteria Heavi
                  scores: land classification, ecology, flood risk, terrain, and
                  grid proximity.
                </p>
                <p className="text-zinc-400">
                  They built it inside a six-figure enterprise GIS license with a
                  dedicated GIS team.
                </p>
                <p className="font-medium text-white">
                  Heavi does the same analysis without the license or the team.
                </p>
              </blockquote>
            </figure>
          </Reveal>
        </section>

        {/* ──────────── Section 5: Secondary Modules + CTA ──────────── */}
        <section className="border-t border-zinc-900 bg-zinc-950">
          <div className="mx-auto max-w-6xl px-6 py-20">
            <Reveal>
              <SectionLabel>Also on the platform</SectionLabel>
            </Reveal>
            <div className="mt-8 grid grid-cols-1 gap-4 md:grid-cols-2">
              <Reveal>
                <SecondaryModule
                  accent="text-rose-300"
                  dot="bg-rose-400/70"
                  title="Heavi Hazard"
                  body="Wildfire and flood risk assessment for property portfolios. For CRE acquisition teams and commercial lenders."
                  href="/hazard"
                />
              </Reveal>
              <Reveal delay={120}>
                <SecondaryModule
                  accent="text-emerald-300"
                  dot="bg-emerald-400/70"
                  title="Heavi Locations"
                  body="Trade area analysis for retail and QSR expansion. Census demographics, competitive density, drive-time catchments."
                  href="/locations"
                />
              </Reveal>
            </div>

            {/* Closing CTA */}
            <Reveal>
              <div className="relative mt-16 overflow-hidden rounded-2xl border border-amber-500/30 bg-gradient-to-br from-amber-500/20 via-amber-500/5 to-zinc-900/0 px-8 py-14 text-center sm:px-12">
                <h2 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">
                  Running a solar development pipeline?
                </h2>
                <p className="mx-auto mt-4 max-w-xl text-base leading-relaxed text-zinc-300">
                  We&rsquo;re offering free 90-day pilots to mid-market developers
                  screening 50 to 500 MW.
                </p>
                <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
                  <a
                    href="mailto:pilots@heavi.ai?subject=Heavi%20solar%20pilot%20request"
                    className="inline-flex w-full items-center justify-center rounded-lg bg-amber-500 px-6 py-3 text-sm font-semibold text-zinc-950 shadow-lg shadow-amber-500/25 transition hover:bg-amber-400 sm:w-auto"
                  >
                    Request a pilot →
                  </a>
                  <Link
                    href="/whitepaper.pdf"
                    target="_blank"
                    className="inline-flex w-full items-center justify-center rounded-lg border border-zinc-700 px-6 py-3 text-sm font-semibold text-zinc-200 transition hover:border-zinc-500 hover:bg-zinc-900 sm:w-auto"
                  >
                    Read the whitepaper →
                  </Link>
                </div>
              </div>
            </Reveal>
          </div>
        </section>

        <footer className="border-t border-zinc-900 px-6 py-8 text-center text-xs text-zinc-600">
          Heavi · Spatial decision intelligence
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

function StepCard({
  step,
  icon,
  title,
  body,
}: {
  step: string;
  icon: React.ReactNode;
  title: string;
  body: string;
}) {
  return (
    <div className="flex h-full flex-col rounded-2xl border border-zinc-800 bg-zinc-900/40 p-7 transition duration-300 hover:border-zinc-600 hover:bg-zinc-900/70">
      <div className="flex items-center justify-between">
        <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-amber-500/10 text-amber-300">
          {icon}
        </span>
        <span className="text-sm font-semibold tabular-nums text-zinc-600">
          {step}
        </span>
      </div>
      <h3 className="mt-5 text-lg font-semibold text-white">{title}</h3>
      <p className="mt-2 text-sm leading-relaxed text-zinc-400">{body}</p>
    </div>
  );
}

function DiffBlock({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="max-w-3xl border-l-2 border-amber-500/60 pl-6">
      <h3 className="text-xl font-semibold tracking-tight text-white sm:text-2xl">
        {title}
      </h3>
      <p className="mt-3 text-base leading-relaxed text-zinc-400">{children}</p>
    </div>
  );
}

function SecondaryModule({
  accent,
  dot,
  title,
  body,
  href,
}: {
  accent: string;
  dot: string;
  title: string;
  body: string;
  href: string;
}) {
  return (
    <Link
      href={href}
      className="group flex h-full flex-col rounded-xl border border-zinc-800 bg-zinc-900/30 p-5 transition hover:border-zinc-700 hover:bg-zinc-900/60"
    >
      <div className="flex items-center gap-2">
        <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
        <h3 className={`text-sm font-semibold ${accent}`}>{title}</h3>
      </div>
      <p className="mt-2 text-sm leading-relaxed text-zinc-400">{body}</p>
      <span className="mt-3 text-xs font-medium text-zinc-500 transition group-hover:text-zinc-300">
        Learn more →
      </span>
    </Link>
  );
}
