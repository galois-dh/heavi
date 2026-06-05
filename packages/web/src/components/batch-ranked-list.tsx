"use client";

import { useEffect, useRef } from "react";
import type { SolarScoreV2 } from "../lib/api";

export type BatchResult = SolarScoreV2 & { name?: string };

const TIER_DOT: Record<string, string> = {
  HIGH: "bg-emerald-400", MODERATE: "bg-amber-400", LOW: "bg-orange-400",
  INSUFFICIENT: "bg-red-400", "CANNOT ASSESS": "bg-zinc-400", NONE: "bg-zinc-600",
};
const RATING_COLOR: Record<string, string> = {
  High: "text-emerald-300", Moderate: "text-amber-300", Low: "text-orange-300",
  Excluded: "text-zinc-400", "CANNOT ASSESS": "text-zinc-300",
};

function isExcluded(r: BatchResult): boolean {
  return r.rating === "Excluded" || r.cannot_assess === true || r.rating === "CANNOT ASSESS";
}

/** Ranked batch results (Month-1 Sprint F2). Non-excluded sorted by score desc,
 *  excluded grouped at the bottom with the exclusion reason. Selected row is
 *  highlighted and scrolled into view (marker click → list scroll). */
export function BatchRankedList({
  results, order, selectedFid, onSelect,
}: {
  results: Record<string, BatchResult>;
  order: string[];
  selectedFid: string | null;
  onSelect: (fid: string) => void;
}) {
  const items = order.map((fid) => ({ fid, r: results[fid] })).filter((x) => x.r);
  const scored = items
    .filter((x) => !isExcluded(x.r))
    .sort((a, b) => (b.r.score ?? -1) - (a.r.score ?? -1));
  const excluded = items.filter((x) => isExcluded(x.r));

  const selectedRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    selectedRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selectedFid]);

  const Row = ({ fid, r, rank }: { fid: string; r: BatchResult; rank: number }) => {
    const sel = fid === selectedFid;
    const excl = isExcluded(r);
    const reason = r.cannot_assess
      ? "cannot assess"
      : (r.exclusions && r.exclusions[0]) || "excluded";
    return (
      <button
        ref={sel ? selectedRef : undefined}
        onClick={() => onSelect(fid)}
        className={`flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs transition ${
          sel ? "bg-blue-500/15 ring-1 ring-blue-500/40" : "hover:bg-zinc-800/60"
        }`}
      >
        <span className="w-5 shrink-0 text-right text-[10px] text-zinc-500">{rank}</span>
        <span className="flex-1 truncate text-zinc-200">{r.name || `${r.query.latitude.toFixed(3)}, ${r.query.longitude.toFixed(3)}`}</span>
        {excl ? (
          <span className="shrink-0 text-[10px] text-zinc-400">{reason}</span>
        ) : (
          <>
            <span className={`shrink-0 font-mono ${RATING_COLOR[r.rating] ?? "text-zinc-300"}`}>
              {r.score == null ? "—" : Math.round(r.score * 100)}
            </span>
            <span className={`shrink-0 text-[10px] ${RATING_COLOR[r.rating] ?? "text-zinc-400"}`}>{r.rating}</span>
            <span className={`h-2 w-2 shrink-0 rounded-full ${TIER_DOT[(r.confidence?.tier ?? "NONE").toUpperCase()] ?? "bg-zinc-600"}`}
              title={`confidence ${r.confidence?.tier}`} />
          </>
        )}
      </button>
    );
  };

  return (
    <div className="space-y-0.5">
      {scored.map((x, i) => <Row key={x.fid} fid={x.fid} r={x.r} rank={i + 1} />)}
      {excluded.length > 0 && (
        <>
          <p className="px-2 pt-2 text-[10px] uppercase tracking-wider text-zinc-600">
            Excluded ({excluded.length})
          </p>
          {excluded.map((x, i) => <Row key={x.fid} fid={x.fid} r={x.r} rank={scored.length + i + 1} />)}
        </>
      )}
    </div>
  );
}
