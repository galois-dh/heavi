import Link from "next/link";
import { TopNav } from "../../components/top-nav";
import { TradeAreaV2Panel } from "../../components/trade-area-v2-panel";

export default function LocationsProductPage() {
  return (
    <div className="flex h-full flex-col">
      <TopNav active="locations" />

      <main className="flex flex-1 flex-col overflow-y-auto px-6 py-8">
        <div className="mx-auto w-full max-w-4xl">
          {/* Product hero */}
          <div className="mb-8">
            <span className="inline-block rounded-full border border-emerald-500/30 bg-emerald-500/15 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-300">
              Heavi Locations
            </span>
            <h1 className="mt-3 text-3xl font-bold text-white">
              Trade area & site intelligence
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-zinc-400">
              For real-estate expansion teams at retail chains, QSR, healthcare systems,
              bank-branch networks, and logistics companies. Huff gravity-model trade-area
              analysis with documented methodology, validated against Dallas Starbucks at 96.7%.
            </p>
          </div>

          {/* Methodology framework */}
          <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-5">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-emerald-300">
              Methodology framework
            </p>
            <ul className="mt-3 space-y-1.5 text-[12px] leading-relaxed text-zinc-300">
              <li>
                <span className="text-zinc-100">Huff (1963, 1964)</span>
                <span className="text-zinc-500"> — gravity model for trade area delineation</span>
              </li>
              <li>
                <span className="text-zinc-100">Suárez-Vega et al. (2015)</span>
                <span className="text-zinc-500"> — multi-criteria extension with competitive density</span>
              </li>
              <li>
                <span className="text-zinc-100">Liang et al. (2020)</span>
                <span className="text-zinc-500"> — modern Huff calibration via mobile-phone data</span>
              </li>
              <li>
                <span className="text-zinc-100">Luo & Wang (2003)</span>
                <span className="text-zinc-500"> — two-step floating catchment area (healthcare)</span>
              </li>
            </ul>
          </div>

          {/* Inline v2 trade-area score (selection-engine confidence) */}
          <TradeAreaV2Panel />

          {/* CTAs */}
          <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-5">
              <h2 className="text-base font-semibold text-white">Score a candidate site</h2>
              <p className="mt-1.5 text-xs leading-relaxed text-zinc-400">
                Drive-time isochrones · Census ACS demographics · competitive density ·
                cannibalization detection. Per-site rating with documented rationale.
              </p>
              <Link
                href="/trade-area"
                className="mt-4 inline-block rounded-md bg-blue-600 px-3.5 py-2 text-sm font-medium text-white transition hover:bg-blue-500"
              >
                Open trade-area workflow →
              </Link>
            </div>

            <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-5">
              <h2 className="text-base font-semibold text-white">Compare multiple sites</h2>
              <p className="mt-1.5 text-xs leading-relaxed text-zinc-400">
                Multi-criteria suitability across uploaded candidate sites. Score each on
                shared criteria, ranked output, methodology attached.
              </p>
              <Link
                href="/suitability"
                className="mt-4 inline-block rounded-md border border-zinc-700 px-3.5 py-2 text-sm font-medium text-zinc-200 transition hover:border-zinc-500 hover:bg-zinc-800"
              >
                Open suitability comparison →
              </Link>
            </div>
          </div>

          <div className="mt-8 rounded-md border border-emerald-500/20 bg-emerald-500/5 p-4 text-xs leading-relaxed text-zinc-300">
            <p className="font-semibold text-emerald-300">Every output includes</p>
            <ul className="mt-1.5 space-y-0.5 text-[12px]">
              <li>• Confidence tier and composite confidence</li>
              <li>• Per-criterion data quality and provenance</li>
              <li>• Methodology documentation with academic citations</li>
              <li>• Data gaps surfaced as first-class output</li>
            </ul>
          </div>
        </div>
      </main>
    </div>
  );
}
