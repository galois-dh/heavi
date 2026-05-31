import Link from "next/link";
import { notFound } from "next/navigation";
import { TopNav } from "../../components/top-nav";
import { ModuleGrid, type ModuleId } from "../../components/module-cards";

interface Persona {
  title: string;
  subtitle: string;
  modules: ModuleId[];
}

const PERSONAS: Record<string, Persona> = {
  insurance: {
    title: "Heavi for Insurance",
    subtitle: "Multi-peril property risk intelligence",
    modules: ["wildfire", "flood", "earthquake"],
  },
  energy: {
    title: "Heavi for Energy",
    subtitle: "Solar development site screening",
    modules: ["solar"],
  },
  realestate: {
    title: "Heavi for Real Estate",
    subtitle: "Property risk and location intelligence",
    modules: ["wildfire", "flood", "trade_area"],
  },
};

export function generateStaticParams() {
  return Object.keys(PERSONAS).map((persona) => ({ persona }));
}

export const dynamicParams = false;

export default async function PersonaPage({
  params,
}: {
  params: Promise<{ persona: string }>;
}) {
  const { persona } = await params;
  const cfg = PERSONAS[persona];
  if (!cfg) notFound();

  return (
    <div className="flex h-full flex-col">
      <TopNav />
      <main className="flex flex-1 flex-col items-center overflow-y-auto px-6 py-12">
        <div className="w-full max-w-4xl">
          <div className="mb-10 text-center">
            <h1 className="text-3xl font-bold tracking-tight text-white">{cfg.title}</h1>
            <p className="mx-auto mt-3 max-w-xl text-sm leading-relaxed text-zinc-400">
              {cfg.subtitle}
            </p>
          </div>

          <ModuleGrid ids={cfg.modules} />

          <div className="mt-10 text-center">
            <Link
              href="/"
              className="inline-block text-xs font-medium text-zinc-400 transition hover:text-blue-300"
            >
              View all modules →
            </Link>
          </div>
        </div>
      </main>
    </div>
  );
}
