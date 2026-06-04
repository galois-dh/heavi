import Link from "next/link";
import { TopNav } from "../../components/top-nav";
import { HazardV2Panel } from "../../components/hazard-v2-panel";

const HAZARDS = [
  {
    id: "wildfire",
    title: "Wildfire risk",
    validation: "AUC 0.76 in Sonoma County (Finney 2011 FSim + Kramer 2018 + Syphard 2012)",
    blurb: "Probabilistic burn probability × structure exposure × HAZUS-style vulnerability. Per-structure annual loss estimate with full provenance.",
    href: "/wildfire",
    cta: "Assess a single property",
  },
  {
    id: "flood",
    title: "Flood risk",
    validation: "16× discrimination in Lee County (Scawthorn 2006 HAZUS + FEMA NFHL)",
    blurb: "FEMA NFHL zone + Base Flood Elevation + USGS 3DEP elevation + USACE NSI building characteristics → depth-damage curve loss estimate.",
    href: "/flood",
    cta: "Assess a single property",
  },
  {
    id: "earthquake",
    title: "Earthquake risk",
    validation: "USGS NSHM hazard + HAZUS damage functions",
    blurb: "Peak ground acceleration + site-class amplification + building fragility → damage-state probabilities.",
    href: "/earthquake",
    cta: "Assess a single property",
  },
];

export default function HazardProductPage() {
  return (
    <div className="flex h-full flex-col">
      <TopNav active="hazard" />

      <main className="flex flex-1 flex-col overflow-y-auto px-6 py-8">
        <div className="mx-auto w-full max-w-4xl">
          {/* Product hero */}
          <div className="mb-8">
            <span className="inline-block rounded-full border border-rose-500/30 bg-rose-500/15 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-rose-300">
              Heavi Hazard
            </span>
            <h1 className="mt-3 text-3xl font-bold text-white">
              Natural hazard intelligence for investment decisions
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-zinc-400">
              For CRE acquisition teams, commercial lenders, property managers, and
              institutional investors evaluating natural-hazard exposure for properties
              or portfolios. Audit-grade methodology documentation suitable for LP,
              board, and lender review.
            </p>
          </div>

          {/* Combined v2 assessment (wildfire + flood + confidence) */}
          <div className="mb-6">
            <HazardV2Panel />
          </div>

          {/* Per-hazard cards */}
          <div className="grid grid-cols-1 gap-4">
            {HAZARDS.map((h) => (
              <div
                key={h.id}
                className="rounded-lg border border-zinc-800 bg-zinc-900 p-5 transition hover:border-zinc-700"
              >
                <div className="flex flex-wrap items-baseline justify-between gap-3">
                  <h2 className="text-lg font-semibold text-white">{h.title}</h2>
                  <span className="text-[11px] text-zinc-500">{h.validation}</span>
                </div>
                <p className="mt-2 text-sm leading-relaxed text-zinc-300">{h.blurb}</p>
                <div className="mt-4 flex flex-wrap gap-2">
                  <Link
                    href={h.href}
                    className="rounded-md bg-blue-600 px-3.5 py-2 text-sm font-medium text-white transition hover:bg-blue-500"
                  >
                    {h.cta} →
                  </Link>
                </div>
              </div>
            ))}
          </div>

          {/* Portfolio panel */}
          <div className="mt-6 rounded-lg border border-zinc-800 bg-zinc-900/60 p-5">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
              Portfolio
            </p>
            <p className="mt-2 text-sm text-zinc-300">
              Upload a CSV of properties for multi-hazard portfolio assessment with
              aggregate analytics, methodology documentation, and audit-ready PDF
              export.
            </p>
            <Link
              href="/portfolio"
              className="mt-3 inline-block rounded-md border border-zinc-700 px-3.5 py-2 text-sm font-medium text-zinc-200 transition hover:border-zinc-500 hover:bg-zinc-800"
            >
              Open portfolio workflow →
            </Link>
          </div>

          {/* Methodology + confidence guarantee */}
          <div className="mt-8 rounded-md border border-rose-500/20 bg-rose-500/5 p-4 text-xs leading-relaxed text-zinc-300">
            <p className="font-semibold text-rose-300">Every output includes</p>
            <ul className="mt-1.5 space-y-0.5 text-[12px]">
              <li>• Confidence tier (HIGH / MODERATE / LOW / INSUFFICIENT) and composite confidence</li>
              <li>• Per-criterion quality (which source was used, why)</li>
              <li>• Methodology documentation (framework citations + academic sources)</li>
              <li>• Data gaps surfaced as first-class output, not footnotes</li>
            </ul>
          </div>
        </div>
      </main>
    </div>
  );
}
