// Module permissioning helpers (Auth + Module Permissioning Spec).
//
// Access is stored in Clerk user publicMetadata; this module turns that metadata
// into access decisions. The pure functions here are unit-tested; the server
// pages call `moduleAccessRedirect` and `redirect()` to the returned path.

/** Shape of the module-access fields we read from Clerk `publicMetadata`. */
export interface UserModuleMeta {
  modules?: string[];
  plan?: "design_partner" | "trial" | "paid" | string;
  pilot_expires?: string; // ISO date, e.g. "2026-09-09"
  batch_limit?: number;
  company?: string;
}

export const DEFAULT_BATCH_LIMIT = 200;

/** The three gated product modules. */
export type ModuleId = "energy" | "hazard" | "locations";

export const MODULE_LABEL: Record<ModuleId, string> = {
  energy: "Energy",
  hazard: "Hazard",
  locations: "Locations",
};

/** Coerce arbitrary Clerk metadata into our typed view. */
export function readModuleMeta(metadata: unknown): UserModuleMeta {
  const m = (metadata ?? {}) as Record<string, unknown>;
  return {
    modules: Array.isArray(m.modules) ? (m.modules as string[]) : [],
    plan: typeof m.plan === "string" ? m.plan : undefined,
    pilot_expires: typeof m.pilot_expires === "string" ? m.pilot_expires : undefined,
    batch_limit: typeof m.batch_limit === "number" ? m.batch_limit : undefined,
    company: typeof m.company === "string" ? m.company : undefined,
  };
}

/** True if the user's pilot has a set expiry that is in the past (vs `now`). */
export function isPilotExpired(meta: UserModuleMeta, now: Date = new Date()): boolean {
  if (!meta.pilot_expires) return false;
  const exp = new Date(meta.pilot_expires);
  return !Number.isNaN(exp.getTime()) && exp.getTime() < now.getTime();
}

/** True if the user can access `module` (has it AND pilot not expired). */
export function hasModuleAccess(meta: UserModuleMeta, module: ModuleId, now: Date = new Date()): boolean {
  return (meta.modules ?? []).includes(module) && !isPilotExpired(meta, now);
}

/**
 * The redirect path a server page should send the user to, or `null` to render.
 * Order: no module → /no-access; module present but pilot expired → /pilot-expired.
 */
export function moduleAccessRedirect(
  metadata: unknown,
  module: ModuleId,
  now: Date = new Date(),
): string | null {
  const meta = readModuleMeta(metadata);
  if (!(meta.modules ?? []).includes(module)) {
    return `/no-access?module=${module}`;
  }
  if (isPilotExpired(meta, now)) {
    return "/pilot-expired";
  }
  return null;
}

/** Per-user batch upload cap from metadata, falling back to the default. */
export function batchLimitFor(metadata: unknown): number {
  const meta = readModuleMeta(metadata);
  return typeof meta.batch_limit === "number" && meta.batch_limit > 0
    ? meta.batch_limit
    : DEFAULT_BATCH_LIMIT;
}
