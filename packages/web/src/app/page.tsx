import Link from "next/link";
import { currentUser } from "@clerk/nextjs/server";
import { TopNav } from "../components/top-nav";

// The landing page is public (middleware allows "/"). It is solar-first: the
// hero, "how it works", and "what makes this different" all speak to a VP of
// Site Development screening solar sites. Hazard and Locations are secondary.
// See docs/specs/Heavi_Landing_Page_Spec.md.
export default async function Home() {
  const user = await currentUser();
  // "Start screening" goes straight to the product when signed in, otherwise
  // through sign-in (the /energy server wrapper would redirect there anyway).
  const startHref = user ? "/energy" : "/sign-in";

  return (
    <div className="flex h-full flex-col">
      <TopNav />

      <main className="flex-1 overflow-y-auto">
        {/* ───────────────────────── Section 1: Hero ───────────────────────── */}
        <section className="relative overflow-hidden border-b border-zinc-900">
          {/* Atmospheric solar glow behind the hero. */}
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0"
            style={{
              background:
                "radial-gradient(60% 55% at 50% 0%, rgba(245,158,11,0.16) 0%, rgba(245,158,11,0) 60%), radial-gradient(45% 45% at 80% 20%, rgba(59,130,246,0.12) 0%, rgba(59,130,246,0) 70%)",
            }}
          />
          <div className="relative mx-auto max-w-4xl px-6 py-24 text-center sm:py-32">
            <p className="heavi-reveal text-xs font-semibold uppercase tracking-[0.4em] text-amber-400">
              Heavi
            </p>
            <h1
              className="heavi-reveal mt-6 text-4xl font-bold leading-[1.05] tracking-tight text-white sm:text-6xl"
              style={{ animationDelay: "0.08s" }}
            >
              Screen solar sites in
              <br className="hidden sm:block" /> minutes, not months.
            </h1>
            <p
              className="heavi-reveal mx-auto mt-7 max-w-2xl text-lg leading-relaxed text-zinc-300"
              style={{ animationDelay: "0.16s" }}
            >
              Score candidate parcels against 15 federal data sources. See which
              sites are worth developing, which are constrained, and how
              confident you should be in each assessment.
            </p>
            <p
              className="heavi-reveal mx-auto mt-4 max-w-2xl text-base leading-relaxed text-zinc-400"
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
                className="inline-flex w-full items-center justify-center rounded-lg bg-amber-500 px-6 py-3 text-sm font-semibold text-zinc-950 shadow-lg shadow-amber-500/20 transition hover:bg-amber-400 sm:w-auto"
              >
                Start screening →
              </Link>
              <Link
                href="/sample-assessment.pdf"
                target="_blank"
                className="inline-flex w-full items-center justify-center rounded-lg border border-zinc-700 px-6 py-3 text-sm font-semibold text-zinc-200 transition hover:border-zinc-500 hover:bg-zinc-900 sm:w-auto"
              >
                See a sample assessment →
              </Link>
            </div>

            <p
              className="heavi-reveal mt-10 inline-flex items-center gap-2 rounded-full border border-zinc-800 bg-zinc-900/60 px-4 py-1.5 text-xs text-zinc-400"
              style={{ animationDelay: "0.38s" }}
            >
              <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
              Validated against 6,321 real US solar installations across 10
              states.
            </p>
          </div>
        </section>

        {/* ─────────────────── Section 2: How It Works ─────────────────── */}
        <section className="mx-auto max-w-6xl px-6 py-20">
          <SectionLabel>How it works</SectionLabel>
          <div className="mt-10 grid grid-cols-1 gap-5 md:grid-cols-3">
            <StepCard
              step="01"
              icon={<UploadIcon />}
              title="Upload your parcels"
              body="Drop a CSV of coordinates or addresses, or type a single location into the search bar. Batch up to 200 parcels at once."
            />
            <StepCard
              step="02"
              icon={<MapIcon />}
              title="See scored results on the map"
              body="Every parcel color-coded by suitability, ranked in a sidebar. Interconnection queue context from 4,426 active solar projects. Toggle constraint layers: protected areas, flood zones, transmission lines."
            />
            <StepCard
              step="03"
              icon={<DocIcon />}
              title="Export audit-ready PDFs"
              body="Per-site or portfolio. Score, confidence level, data sources used, methodology citations, known limitations. Hand it to your investment committee or your lender."
            />
          </div>
        </section>

        {/* ───────────── Section 3: What Makes This Different ───────────── */}
        <section className="border-y border-zinc-900 bg-zinc-900/20">
          <div className="mx-auto max-w-5xl px-6 py-24">
            <SectionLabel>What makes this different</SectionLabel>
            <div className="mt-12 space-y-14">
              <DiffBlock title="You know the score AND how much to trust it.">
                Every assessment reports which federal data was available at that
                location, which criteria used authoritative versus proxy
                sources, and where the gaps are. No other screening tool tells
                you this.
              </DiffBlock>
              <DiffBlock title="Methodology your lender can verify.">
                14 criteria grounded in peer-reviewed literature. Weights
                calibrated per grid region against real solar installation
                records. Published whitepaper with full validation results.
              </DiffBlock>
              <DiffBlock title="Interconnection context built in.">
                4,426 active solar projects from a national interconnection queue
                dataset. See existing capacity and queue activity near every
                scored parcel before you file an interconnection application.
              </DiffBlock>
            </div>
          </div>
        </section>

        {/* ───────────────── Section 4: Market Validation ───────────────── */}
        <section className="mx-auto max-w-4xl px-6 py-24">
          <figure className="relative rounded-2xl border border-zinc-800 bg-zinc-900/50 p-10 sm:p-14">
            <span
              aria-hidden
              className="absolute left-6 top-4 select-none font-serif text-7xl leading-none text-amber-500/20"
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
        </section>

        {/* ──────────── Section 5: Secondary Modules + CTA ──────────── */}
        <section className="border-t border-zinc-900 bg-zinc-950">
          <div className="mx-auto max-w-6xl px-6 py-20">
            <SectionLabel>Also on the platform</SectionLabel>
            <div className="mt-8 grid grid-cols-1 gap-4 md:grid-cols-2">
              <SecondaryModule
                accent="text-rose-300"
                dot="bg-rose-400/70"
                title="Heavi Hazard"
                body="Wildfire and flood risk assessment for property portfolios. For CRE acquisition teams and commercial lenders."
                href="/hazard"
              />
              <SecondaryModule
                accent="text-emerald-300"
                dot="bg-emerald-400/70"
                title="Heavi Locations"
                body="Trade area analysis for retail and QSR expansion. Census demographics, competitive density, drive-time catchments."
                href="/locations"
              />
            </div>

            {/* Closing CTA */}
            <div className="relative mt-16 overflow-hidden rounded-2xl border border-amber-500/25 bg-gradient-to-br from-amber-500/10 to-zinc-900/0 px-8 py-14 text-center sm:px-12">
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
                  className="inline-flex w-full items-center justify-center rounded-lg bg-amber-500 px-6 py-3 text-sm font-semibold text-zinc-950 shadow-lg shadow-amber-500/20 transition hover:bg-amber-400 sm:w-auto"
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
    <div className="flex flex-col rounded-2xl border border-zinc-800 bg-zinc-900/40 p-7 transition hover:border-zinc-700">
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
    <div className="max-w-3xl">
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
      className="group flex flex-col rounded-xl border border-zinc-800 bg-zinc-900/30 p-5 transition hover:border-zinc-700 hover:bg-zinc-900/60"
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

/* Inline icons (stroke = currentColor so they inherit the amber accent). */
function UploadIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 16V4m0 0L7 9m5-5 5 5" />
      <path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
    </svg>
  );
}

function MapIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="m9 4 6 2 5-2v14l-5 2-6-2-5 2V6l5-2Z" />
      <path d="M9 4v14M15 6v14" />
    </svg>
  );
}

function DocIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z" />
      <path d="M14 3v5h5M9 13h6M9 17h6" />
    </svg>
  );
}
