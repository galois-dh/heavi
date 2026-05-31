import Link from "next/link";

export type ModuleId = "wildfire" | "solar" | "flood" | "earthquake" | "trade_area";

interface ModuleDef {
  title: string;
  status: string;
  region: string;
  blurb: string;
  buttons: { href: string; label: string; primary?: boolean }[];
}

export const MODULES: Record<ModuleId, ModuleDef> = {
  wildfire: {
    title: "Wildfire Risk Assessment",
    status: "LIVE",
    region: "Sonoma County",
    blurb:
      "Calibrated annual-loss estimates per structure, validated against CAL FIRE damage inspections.",
    buttons: [
      { href: "/wildfire", label: "Assess Single Property", primary: true },
      { href: "/portfolio", label: "Score Portfolio" },
    ],
  },
  solar: {
    title: "Solar Site Suitability",
    status: "LIVE",
    region: "Kern County, California",
    blurb:
      "Multi-criteria solar development site scoring validated against EIA Form 860 installations.",
    buttons: [
      { href: "/solar", label: "Discover Sites", primary: true },
      { href: "/solar?mode=score", label: "Score Your Parcels" },
    ],
  },
  flood: {
    title: "Flood Risk Assessment",
    status: "LIVE",
    region: "National Coverage",
    blurb:
      "HAZUS-based property flood risk assessment with FEMA flood zone analysis. Works for any US address.",
    buttons: [{ href: "/flood", label: "Assess Property", primary: true }],
  },
  earthquake: {
    title: "Earthquake Risk Assessment",
    status: "LIVE",
    region: "National Coverage",
    blurb:
      "HAZUS-based property earthquake risk with USGS NSHM ground motion, site-class amplification, and fragility-curve damage estimates.",
    buttons: [{ href: "/earthquake", label: "Assess Property", primary: true }],
  },
  trade_area: {
    title: "Trade Area Analysis",
    status: "LIVE",
    region: "Dallas County, Texas",
    blurb: "Demographic, competitive, and accessibility scoring for site selection.",
    buttons: [
      { href: "/trade-area", label: "Score Location", primary: true },
      { href: "/trade-area?mode=discover", label: "Discover Sites" },
    ],
  },
};

export function ModuleGrid({ ids }: { ids: ModuleId[] }) {
  return (
    <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
      {ids.map((id) => {
        const m = MODULES[id];
        return (
          <ModuleCard key={id} title={m.title} status={m.status} region={m.region} blurb={m.blurb}>
            {m.buttons.map((b) => (
              <CardButton key={b.href} href={b.href} primary={b.primary}>
                {b.label}
              </CardButton>
            ))}
          </ModuleCard>
        );
      })}
    </div>
  );
}

export function ModuleCard({
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

export function CardButton({
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
