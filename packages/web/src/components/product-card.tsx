import Link from "next/link";

/** Module access state for the landing-page cards (Auth spec, Step 8). */
export type CardAccess = "open" | "locked" | "signed-out";

export interface ProductCardProps {
  product: "energy" | "hazard" | "locations";
  title: string;
  tagline: string;
  buyer: string;
  blurb: string;
  modules: string[];
  primaryCta: { href: string; label: string };
  secondaryCtas?: { href: string; label: string }[];
  /** Defaults to "open" so non-auth usages (if any) render unchanged. */
  access?: CardAccess;
}

const ACCENT: Record<ProductCardProps["product"], string> = {
  energy:    "from-amber-500/20 to-amber-500/0 border-amber-500/30",
  hazard:    "from-rose-500/20 to-rose-500/0 border-rose-500/30",
  locations: "from-emerald-500/20 to-emerald-500/0 border-emerald-500/30",
};

const ACCENT_BADGE: Record<ProductCardProps["product"], string> = {
  energy:    "bg-amber-500/15 text-amber-300 border-amber-500/30",
  hazard:    "bg-rose-500/15 text-rose-300 border-rose-500/30",
  locations: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
};

export function ProductCard(props: ProductCardProps) {
  const { product, title, tagline, buyer, blurb, modules, primaryCta, secondaryCtas } = props;
  const access: CardAccess = props.access ?? "open";
  const locked = access === "locked";

  // The primary call-to-action depends on access state (Auth spec, Step 8).
  const cta =
    access === "signed-out"
      ? { href: "/sign-in", label: "Sign in to access →" }
      : access === "locked"
        ? { href: `/no-access?module=${product}`, label: "Request access →" }
        : { href: primaryCta.href, label: "Open →" };

  return (
    <div
      className={`relative flex flex-col rounded-2xl border bg-gradient-to-br ${ACCENT[product]} bg-zinc-900 p-7 transition hover:border-zinc-600 ${
        locked ? "opacity-50" : ""
      }`}
    >
      <span
        className={`mb-3 inline-block w-fit rounded-full border px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${ACCENT_BADGE[product]}`}
      >
        Heavi {product[0].toUpperCase() + product.slice(1)}
      </span>
      <h2 className="text-xl font-semibold text-white">{title}</h2>
      <p className="mt-1 text-sm text-zinc-400">{tagline}</p>
      <p className="mt-2 text-[11px] uppercase tracking-wider text-zinc-500">
        For {buyer}
      </p>
      <p className="mt-4 flex-1 text-sm leading-relaxed text-zinc-300">{blurb}</p>

      <div className="mt-4">
        <p className="text-[10px] uppercase tracking-wider text-zinc-500">
          Workflows
        </p>
        <p className="mt-1 text-xs text-zinc-400">{modules.join(" · ")}</p>
      </div>

      <div className="mt-6 flex flex-wrap gap-2">
        <Link
          href={cta.href}
          className={`rounded-md px-3.5 py-2 text-sm font-medium transition ${
            locked
              ? "border border-zinc-700 text-zinc-300 hover:border-zinc-500 hover:bg-zinc-800"
              : "bg-blue-600 text-white hover:bg-blue-500"
          }`}
        >
          {cta.label}
        </Link>
        {/* Secondary CTAs only when the module is actually open. */}
        {access === "open" &&
          secondaryCtas?.map((c) => (
            <Link
              key={c.href}
              href={c.href}
              className="rounded-md border border-zinc-700 px-3.5 py-2 text-sm font-medium text-zinc-200 transition hover:border-zinc-500 hover:bg-zinc-800"
            >
              {c.label}
            </Link>
          ))}
      </div>
    </div>
  );
}
