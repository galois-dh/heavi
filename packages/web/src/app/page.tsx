import Link from "next/link";
import { TopNav } from "../components/top-nav";

export default function Home() {
  return (
    <div className="flex h-full flex-col">
      <TopNav />

      <main className="flex flex-1 flex-col items-center overflow-y-auto px-6 py-12">
        <div className="w-full max-w-4xl">
          {/* Hero */}
          <div className="mb-10 text-center">
            <h1 className="text-4xl font-bold tracking-tight text-white">HEAVI</h1>
            <p className="mt-2 text-sm uppercase tracking-[0.2em] text-blue-400">
              Spatial decision intelligence
            </p>
            <p className="mx-auto mt-4 max-w-xl text-sm leading-relaxed text-zinc-400">
              Module-based geospatial risk and suitability analytics. Pick a module to begin.
            </p>
          </div>

          {/* Module cards */}
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
            <ModuleCard
              title="Wildfire Risk Assessment"
              status="LIVE"
              region="Sonoma County"
              blurb="Calibrated annual-loss estimates per structure, validated against CAL FIRE damage inspections."
            >
              <CardButton href="/wildfire" primary>
                Assess Single Property
              </CardButton>
              <CardButton href="/portfolio">Score Portfolio</CardButton>
            </ModuleCard>

            <ModuleCard
              title="Solar Site Suitability"
              status="LIVE"
              region="Kern County, California"
              blurb="Multi-criteria solar development site scoring validated against EIA Form 860 installations."
            >
              <CardButton href="/solar" primary>
                Discover Sites
              </CardButton>
              <CardButton href="/solar?mode=score">Score Your Parcels</CardButton>
            </ModuleCard>

            <ModuleCard
              title="Flood Risk Assessment"
              status="LIVE"
              region="National Coverage"
              blurb="HAZUS-based property flood risk assessment with FEMA flood zone analysis. Works for any US address."
            >
              <CardButton href="/flood" primary>
                Assess Property
              </CardButton>
            </ModuleCard>
          </div>

          {/* Footer */}
          <div className="mt-10 text-center">
            <p className="text-xs text-zinc-500">
              More modules coming: Flood Risk, Seismic Risk, Trade Area Analytics
            </p>
            <Link
              href="/query"
              className="mt-4 inline-block text-xs font-medium text-zinc-400 transition hover:text-blue-300"
            >
              Advanced: Natural Language Spatial Query →
            </Link>
          </div>
        </div>
      </main>
    </div>
  );
}

function ModuleCard({
  title,
  status,
  region,
  blurb,
  children,
}: {
  title: string;
  status: string;
  region: string;
  blurb: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col rounded-xl border border-zinc-800 bg-zinc-900 p-6 transition hover:border-zinc-700">
      <div className="mb-3 flex items-center gap-2">
        <span className="rounded-full bg-green-500/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-green-400">
          {status}
        </span>
        <span className="text-[11px] uppercase tracking-wider text-zinc-500">{region}</span>
      </div>
      <h2 className="text-lg font-semibold text-white">{title}</h2>
      <p className="mt-2 flex-1 text-sm leading-relaxed text-zinc-400">{blurb}</p>
      <div className="mt-5 flex flex-wrap gap-2">{children}</div>
    </div>
  );
}

function CardButton({
  href,
  children,
  primary = false,
}: {
  href: string;
  children: React.ReactNode;
  primary?: boolean;
}) {
  return (
    <Link
      href={href}
      className={`rounded-md px-3.5 py-2 text-sm font-medium transition ${
        primary
          ? "bg-blue-600 text-white hover:bg-blue-500"
          : "border border-zinc-700 text-zinc-200 hover:border-zinc-500 hover:bg-zinc-800"
      }`}
    >
      {children}
    </Link>
  );
}
