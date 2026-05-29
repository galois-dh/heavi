"use client";

import Link from "next/link";

type NavKey = "wildfire" | "solar" | "portfolio" | "suitability" | "query";

const PRIMARY: { key: NavKey; label: string; href: string }[] = [
  { key: "wildfire", label: "Wildfire", href: "/wildfire" },
  { key: "solar", label: "Solar", href: "/solar" },
  { key: "portfolio", label: "Portfolio", href: "/portfolio" },
  { key: "suitability", label: "Suitability", href: "/suitability" },
];

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
        {PRIMARY.map((item) => (
          <Link
            key={item.key}
            href={item.href}
            className={`rounded-md px-3 py-1.5 font-medium transition ${
              active === item.key
                ? "bg-blue-600/15 text-blue-300"
                : "text-zinc-300 hover:bg-zinc-800 hover:text-white"
            }`}
          >
            {item.label}
          </Link>
        ))}
        {/* Query is the power-user tool — smaller / secondary styling. */}
        <Link
          href="/query"
          className={`ml-1 rounded-md border px-2.5 py-1 text-[12px] transition ${
            active === "query"
              ? "border-blue-700 text-blue-300"
              : "border-zinc-700 text-zinc-400 hover:border-zinc-500 hover:text-zinc-200"
          }`}
        >
          Query
        </Link>
      </nav>
    </header>
  );
}
