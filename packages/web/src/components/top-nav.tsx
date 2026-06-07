"use client";

import Link from "next/link";
import { UserButton, useUser } from "@clerk/nextjs";

type NavKey = "energy" | "hazard" | "locations";

// The three authenticated product pages. The old "Modules" dropdown (individual
// wildfire/flood/earthquake/solar/trade-area/portfolio/suitability/query tool
// pages) was removed along with those routes.
const PRODUCTS: { key: NavKey; label: string; href: string }[] = [
  { key: "energy",    label: "Energy",    href: "/energy" },
  { key: "hazard",    label: "Hazard",    href: "/hazard" },
  { key: "locations", label: "Locations", href: "/locations" },
];

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
          const isCurrent = active === p.key;
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

        <AuthControls />
      </nav>
    </header>
  );
}
