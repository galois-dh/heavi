"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { UserButton, useUser } from "@clerk/nextjs";

const LINKS = [
  { label: "Energy", href: "/energy" },
  { label: "Hazard", href: "/hazard" },
  { label: "Locations", href: "/locations" },
];

/** Sign-in link when signed out, UserButton when signed in (mirrors TopNav). */
function Auth() {
  const { isLoaded, isSignedIn } = useUser();
  if (!isLoaded) return <span className="h-7 w-7" aria-hidden />;
  return isSignedIn ? (
    <UserButton />
  ) : (
    <Link
      href="/sign-in"
      className="rounded-md px-3 py-1.5 text-sm font-medium text-zinc-200 transition hover:text-white"
    >
      Sign in
    </Link>
  );
}

/**
 * Landing-only navigation: floating + transparent over the hero, turning solid
 * with a backdrop blur once the page is scrolled. Product pages keep the solid
 * TopNav; this component is mounted only on "/".
 */
export function LandingNav() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 16);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={`fixed inset-x-0 top-0 z-50 border-b transition-colors duration-300 ${
        scrolled
          ? "border-zinc-800/80 bg-zinc-950/80 backdrop-blur-md"
          : "border-transparent bg-transparent"
      }`}
    >
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3.5">
        <Link href="/" className="text-base font-bold tracking-tight text-white">
          HEAVI
        </Link>

        <nav className="hidden items-center gap-1 text-sm sm:flex">
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className="rounded-md px-3 py-1.5 font-medium text-zinc-300 transition hover:bg-zinc-800/60 hover:text-white"
            >
              {l.label}
            </Link>
          ))}
        </nav>

        <Auth />
      </div>
    </header>
  );
}
