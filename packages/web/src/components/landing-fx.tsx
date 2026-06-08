"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

/**
 * Fade-and-rise a block in. This is a pure-CSS animation (.reveal in
 * globals.css runs `heavi-fade-up ... both` on mount) — intentionally NOT
 * gated on JavaScript or IntersectionObserver, so content can never get stuck
 * at opacity 0 if scripts fail to run. `delay` staggers grouped items.
 */
export function Reveal({
  children,
  className = "",
  delay = 0,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
}) {
  return (
    <div
      className={`reveal ${className}`}
      style={delay ? { animationDelay: `${delay}ms` } : undefined}
    >
      {children}
    </div>
  );
}

/**
 * A large stat number that counts up from 0 when scrolled into view, with a
 * small label below. Fail-safe: respects prefers-reduced-motion, and if the
 * IntersectionObserver never fires (or is unavailable) the final value is
 * still shown via a fallback timer — it never stays stuck at 0.
 */
export function StatCounter({
  value,
  label,
}: {
  value: number;
  label: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [n, setN] = useState(0);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const reduce =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce || typeof IntersectionObserver === "undefined") {
      setN(value);
      return;
    }

    let raf = 0;
    let start = 0;
    const duration = 1400;
    // Fail-safe: show the final number even if the observer never fires.
    const fallback = window.setTimeout(() => setN(value), 1800);

    const animate = () => {
      const tick = (t: number) => {
        if (!start) start = t;
        const p = Math.min(1, (t - start) / duration);
        const eased = 1 - Math.pow(1 - p, 3);
        setN(Math.round(eased * value));
        if (p < 1) raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
    };

    const io = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        io.disconnect();
        clearTimeout(fallback);
        animate();
      },
      { threshold: 0.4 },
    );
    io.observe(el);

    return () => {
      io.disconnect();
      clearTimeout(fallback);
      cancelAnimationFrame(raf);
    };
  }, [value]);

  return (
    <div ref={ref} className="text-center">
      <div className="text-3xl font-bold tabular-nums tracking-tight text-white sm:text-5xl">
        {n.toLocaleString("en-US")}
      </div>
      <div className="mt-2 text-[11px] uppercase tracking-wider text-zinc-500 sm:text-xs">
        {label}
      </div>
    </div>
  );
}
