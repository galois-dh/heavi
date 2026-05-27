"use client";

import {
  type FormEvent,
  type KeyboardEvent,
  useCallback,
  useRef,
  useState,
} from "react";
import { postQuery, type QueryResult } from "../lib/api";

interface ChatMessage {
  role: "user" | "assistant";
  text: string;
}

interface Props {
  // The original question is passed alongside the result so the parent can
  // decide map-click context (wildfire vs site-suitability) from the query
  // text, not just the returned SQL.
  onResult: (r: QueryResult, question: string) => void;
  onSiteReportRequest: (address: string) => Promise<void>;
  loading: boolean;
  setLoading: (v: boolean) => void;
}

const SITE_REPORT_INTENT =
  /^(?:score|site\s*report(?:\s+for)?|report\s+for|suitability(?:\s+of|\s+for)?)\s+(.+?)(?:\s+for\s+site\s+suitability)?\.?\s*$/i;

export function ChatPanel({ onResult, onSiteReportRequest, loading, setLoading }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  const submit = useCallback(
    async (e?: FormEvent) => {
      e?.preventDefault();
      const q = input.trim();
      if (!q || loading) return;

      setMessages((prev) => [...prev, { role: "user", text: q }]);
      setInput("");
      setLoading(true);

      const intent = q.match(SITE_REPORT_INTENT);
      if (intent) {
        const address = intent[1].trim();
        try {
          await onSiteReportRequest(address);
          setMessages((prev) => [
            ...prev,
            { role: "assistant", text: `Site report for **${address}** opened on the right.` },
          ]);
        } catch (err) {
          const msg = err instanceof Error ? err.message : "Unknown error";
          setMessages((prev) => [...prev, { role: "assistant", text: `Error: ${msg}` }]);
        } finally {
          setLoading(false);
          setTimeout(() => scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight), 50);
        }
        return;
      }

      try {
        const result = await postQuery(q);
        onResult(result, q);

        let reply: string;
        if (result.type === "error" || result.type === "sql_error") {
          reply = result.message ?? "An error occurred.";
        } else if (result.type === "aggregate_result") {
          const rows = result.rows ?? [];
          if (rows.length === 1) {
            const vals = Object.entries(rows[0])
              .map(([k, v]) => `**${k}**: ${v}`)
              .join(", ");
            reply = vals;
          } else {
            reply = `${rows.length} result rows returned.`;
          }
        } else if (result.type === "FeatureCollection") {
          const n = result.features?.length ?? 0;
          const total = result.metadata?.total_count ?? n;
          reply = `Showing ${n} of ${total} features on the map.`;
        } else if (result.type === "large_result_summary") {
          reply = result.message ?? `${result.total_count?.toLocaleString()} features matched.`;
        } else if (result.type === "row_result") {
          reply = `${result.row_count} rows returned.`;
        } else {
          reply = "Query completed.";
        }

        setMessages((prev) => [...prev, { role: "assistant", text: reply }]);
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Unknown error";
        setMessages((prev) => [
          ...prev,
          { role: "assistant", text: `Error: ${msg}` },
        ]);
      } finally {
        setLoading(false);
        setTimeout(() => scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight), 50);
      }
    },
    [input, loading, onResult, onSiteReportRequest, setLoading],
  );

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.length === 0 && (
          <p className="text-xs text-zinc-500 italic">
            Ask a spatial question about Alameda County...
          </p>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`text-sm leading-relaxed ${
              m.role === "user"
                ? "text-zinc-100"
                : "text-zinc-400"
            }`}
          >
            <span className="mr-1.5 text-xs font-medium text-zinc-600">
              {m.role === "user" ? "You" : "Heavi"}
            </span>
            <span>{m.text}</span>
          </div>
        ))}
        {loading && (
          <div className="text-xs text-zinc-600 animate-pulse">Thinking...</div>
        )}
      </div>

      {/* Input */}
      <form onSubmit={submit} className="border-t border-zinc-800 p-3">
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="How many buildings are in a flood zone?"
            rows={2}
            className="flex-1 resize-none rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:border-indigo-500 focus:outline-none"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="self-end rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Ask
          </button>
        </div>
      </form>
    </div>
  );
}
