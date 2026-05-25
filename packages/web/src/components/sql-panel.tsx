"use client";

import { useState } from "react";

export function SqlPanel({ sql }: { sql: string }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="border-t border-zinc-800">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-1.5 px-4 py-2 text-xs font-medium text-zinc-500 hover:text-zinc-300 transition"
      >
        <svg
          className={`h-3 w-3 transition-transform ${open ? "rotate-90" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>
        Show SQL
      </button>
      {open && (
        <pre className="mx-4 mb-3 overflow-x-auto rounded bg-zinc-950 p-3 text-xs text-emerald-400 leading-relaxed">
          {sql}
        </pre>
      )}
    </div>
  );
}
