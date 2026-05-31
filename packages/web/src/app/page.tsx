import Link from "next/link";
import { TopNav } from "../components/top-nav";
import { ModuleGrid } from "../components/module-cards";

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

          <ModuleGrid ids={["wildfire", "flood", "earthquake", "solar", "trade_area"]} />

          {/* Footer */}
          <div className="mt-10 text-center">
            <p className="text-xs text-zinc-500">
              Tailored views: <Link href="/insurance" className="text-zinc-400 hover:text-blue-300">Insurance</Link>
              {" · "}
              <Link href="/energy" className="text-zinc-400 hover:text-blue-300">Energy</Link>
              {" · "}
              <Link href="/realestate" className="text-zinc-400 hover:text-blue-300">Real Estate</Link>
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
