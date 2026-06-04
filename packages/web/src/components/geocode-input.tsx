"use client";

import type { GeocodeResult } from "../lib/api";

/** Unified location input (Month-1 Sprint, Feature 1). Accepts an address,
 *  place name, city/state, or raw lat,lng; renders the resolved coordinates +
 *  formatted address once the page resolves them. */
export function GeocodeInput({
  value,
  onChange,
  onEnter,
  resolved,
  error,
  placeholder = "Enter address, place name, or lat,lng",
}: {
  value: string;
  onChange: (v: string) => void;
  onEnter?: () => void;
  resolved?: GeocodeResult | null;
  error?: string | null;
  placeholder?: string;
}) {
  return (
    <div className="space-y-1.5">
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && onEnter?.()}
        placeholder={placeholder}
        className="w-full rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-100 placeholder:text-zinc-600"
      />
      {resolved && (
        <p className="text-[11px] text-emerald-300/90">
          Resolved: {resolved.latitude.toFixed(4)}, {resolved.longitude.toFixed(4)}
          {resolved.formatted_address && (
            <span className="text-zinc-500"> ({resolved.formatted_address})</span>
          )}
          {resolved.source !== "coordinates" && (
            <span className="text-zinc-600"> · {resolved.source}</span>
          )}
        </p>
      )}
      {error && (
        <p className="rounded-md border border-red-900/50 bg-red-950/40 px-2 py-1.5 text-[11px] text-red-300">
          {error}
        </p>
      )}
    </div>
  );
}
