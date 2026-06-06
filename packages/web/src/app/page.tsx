import Link from "next/link";
import { currentUser } from "@clerk/nextjs/server";
import { TopNav } from "../components/top-nav";
import { ProductCard, type CardAccess } from "../components/product-card";
import { hasModuleAccess, readModuleMeta, type ModuleId } from "../lib/module-access";

export default async function Home() {
  // The landing page is public; show product cards as open / locked / signed-out
  // based on the viewer's module access (Auth + Module Permissioning Spec, Step 8).
  const user = await currentUser();
  const meta = readModuleMeta(user?.publicMetadata);
  const accessFor = (product: ModuleId): CardAccess =>
    !user ? "signed-out" : hasModuleAccess(meta, product) ? "open" : "locked";

  return (
    <div className="flex h-full flex-col">
      <TopNav />

      <main className="flex flex-1 flex-col items-center overflow-y-auto px-6 py-12">
        <div className="w-full max-w-6xl">
          {/* Hero */}
          <div className="mb-12 text-center">
            <h1 className="text-5xl font-bold tracking-tight text-white">HEAVI</h1>
            <p className="mt-3 text-sm uppercase tracking-[0.25em] text-blue-400">
              Deterministic validated spatial analysis
            </p>
            <p className="mx-auto mt-5 max-w-2xl text-base leading-relaxed text-zinc-300">
              Calibrated against ground truth. Peer-reviewed methodology. Three
              product experiences built on shared infrastructure — each one a
              standalone tool for its buyer.
            </p>
          </div>

          {/* Three product entries (Phase 5 acceptance criterion #2) */}
          <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
            <ProductCard
              product="energy"
              access={accessFor("energy")}
              title="Heavi Energy"
              tagline="Site screening for renewable development"
              buyer="solar, wind, battery storage, and data-center developers"
              blurb={
                "Score candidate parcels against the full federal data stack — " +
                "NREL PVWatts, USGS 3DEP, HIFLD transmission, USFWS critical " +
                "habitat, FEMA NFHL, NWI wetlands, EPA EJScreen, USDA SSURGO — " +
                "with audit-grade methodology documentation attached to every " +
                "scored result."
              }
              modules={["Solar suitability", "Environmental screening"]}
              primaryCta={{ href: "/energy", label: "Score a site →" }}
              secondaryCtas={[
                { href: "/portfolio", label: "Batch CSV" },
              ]}
            />

            <ProductCard
              product="hazard"
              access={accessFor("hazard")}
              title="Heavi Hazard"
              tagline="Natural hazard intelligence for investment decisions"
              buyer="CRE acquisition, commercial lenders, portfolio managers"
              blurb={
                "Multi-peril property risk assessment — wildfire (AUC 0.76 " +
                "validated), flood (16× discrimination), earthquake — with " +
                "portfolio aggregate analytics, methodology documentation, and " +
                "audit-ready PDF exports for LP, board, and lender review."
              }
              modules={["Wildfire", "Flood", "Earthquake"]}
              primaryCta={{ href: "/hazard", label: "Assess property →" }}
              secondaryCtas={[
                { href: "/portfolio", label: "Portfolio" },
              ]}
            />

            <ProductCard
              product="locations"
              access={accessFor("locations")}
              title="Heavi Locations"
              tagline="Trade area & site intelligence"
              buyer="retail expansion, QSR, healthcare, bank-branch teams"
              blurb={
                "Huff gravity-model trade-area analysis with documented " +
                "methodology. Census ACS demographics, drive-time isochrones, " +
                "competitive density, cannibalization detection — every " +
                "criterion grounded in peer-reviewed literature."
              }
              modules={["Trade area scoring", "Site comparison"]}
              primaryCta={{ href: "/locations", label: "Evaluate sites →" }}
            />
          </div>

          {/* Secondary footer */}
          <div className="mt-12 text-center text-xs text-zinc-500">
            <p>
              <Link href="/data-sources-browser" className="text-zinc-400 hover:text-blue-300">
                Data catalog (31 sources)
              </Link>
              {" · "}
              <Link href="/query" className="text-zinc-400 hover:text-blue-300">
                Natural-language spatial query
              </Link>
              {" · "}
              <Link href="/suitability" className="text-zinc-400 hover:text-blue-300">
                Multi-criteria suitability
              </Link>
            </p>
            <p className="mt-3 text-[10px] text-zinc-600">
              The methodology is published. The operationalization is not.
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}
