"use client";

import Link from "next/link";
import { UserButton, useUser } from "@clerk/nextjs";

type NavKey =
  | "energy" | "hazard" | "locations"
  | "wildfire" | "solar" | "flood" | "earthquake" | "trade-area"
  | "portfolio" | "suitability" | "query";

// Phase 5: leads with the three products, secondary nav for individual modules.
const PRODUCTS: { key: NavKey; label: string; href: string }[] = [
  { key: "energy",    label: "Energy",    href: "/energy" },
  { key: "hazard",    label: "Hazard",    href: "/hazard" },
  { key: "locations", label: "Locations", href: "/locations" },
];

const SECONDARY: { key: NavKey; label: string; href: string }[] = [
  { key: "wildfire",    label: "Wildfire",     href: "/wildfire" },
  { key: "flood",       label: "Flood",        href: "/flood" },
  { key: "earthquake",  label: "Earthquake",   href: "/earthquake" },
  { key: "solar",       label: "Solar",        href: "/solar" },
  { key: "trade-area",  label: "Trade Area",   href: "/trade-area" },
  { key: "portfolio",   label: "Portfolio",    href: "/portfolio" },
  { key: "suitability", label: "Suitability",  href: "/suitability" },
];

const PRODUCT_OF: Record<string, "energy" | "hazard" | "locations" | undefined> = {
  solar: "energy",
  wildfire: "hazard",
  flood: "hazard",
  earthquake: "hazard",
  portfolio: "hazard",
  "trade-area": "locations",
};

/** Sign-in link when signed out, UserButton (avatar + sign-out) when signed in. */
function AuthControls() {
  const { isLoaded, isSignedIn } = useUser();
  if (!isLoaded) return null;
  return isSignedIn ? (
    <UserButton />
  ) : (
    <Link
      href="/sign-in"
      className="rounded-md px-3 py-1.5 font-semibold text-zinc-200 transition hover:bg-zinc-800 hover:text-white"
    >
      Sign in
    </Link>
  );
}

export function TopNav({ active }: { active?: NavKey }) {
  const productContext = active ? PRODUCT_OF[active] : undefined;
  return (
    <header className="flex shrink-0 items-center justify-between border-b border-zinc-800 bg-zinc-950 px-5 py-2.5">
      <Link href="/" className="group flex items-baseline gap-2">
        <span className="text-base font-bold tracking-tight text-white">HEAVI</span>
        <span className="hidden text-[11px] text-zinc-500 group-hover:text-zinc-400 sm:inline">
          Spatial decision intelligence
        </span>
      </Link>

      <nav className="flex items-center gap-1 text-sm">
        {PRODUCTS.map((p) => {
          const isCurrent = active === p.key || productContext === p.key;
          return (
            <Link
              key={p.key}
              href={p.href}
              className={`rounded-md px-3 py-1.5 font-semibold transition ${
                isCurrent
                  ? "bg-blue-600/15 text-blue-300"
                  : "text-zinc-200 hover:bg-zinc-800 hover:text-white"
              }`}
            >
              {p.label}
            </Link>
          );
        })}

        <span className="mx-2 hidden h-4 w-px bg-zinc-800 sm:block" />

        <details className="relative">
          <summary
            className="cursor-pointer list-none rounded-md border border-zinc-800 px-2.5 py-1 text-[11px] text-zinc-400 hover:border-zinc-600 hover:text-zinc-200"
          >
            Modules
          </summary>
          <div className="absolute right-0 z-50 mt-1 w-56 rounded-md border border-zinc-800 bg-zinc-950 py-1 shadow-xl">
            {SECONDARY.map((s) => (
              <Link
                key={s.key}
                href={s.href}
                className={`block px-3 py-1.5 text-xs transition ${
                  active === s.key
                    ? "bg-blue-600/15 text-blue-300"
                    : "text-zinc-300 hover:bg-zinc-800 hover:text-white"
                }`}
              >
                {s.label}
              </Link>
            ))}
            <div className="my-1 h-px bg-zinc-800" />
            <Link
              href="/query"
              className={`block px-3 py-1.5 text-xs transition ${
                active === "query"
                  ? "bg-blue-600/15 text-blue-300"
                  : "text-zinc-300 hover:bg-zinc-800 hover:text-white"
              }`}
            >
              Natural-language query
            </Link>
          </div>
        </details>

        <span className="mx-2 hidden h-4 w-px bg-zinc-800 sm:block" />

        <AuthControls />
      </nav>
    </header>
  );
}
