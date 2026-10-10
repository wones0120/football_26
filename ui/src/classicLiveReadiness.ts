export function classicLivePreflightLabel(readiness?: Record<string, unknown> | null): string {
  if (readiness?.status === "READY") return "Ready for generation";
  if (readiness?.status === "NOT_READY") return "Blocked — source refresh required";
  if (readiness?.status === "ERROR") return "Blocked — evidence check failed";
  return "Unverified — readiness required";
}

export function classicLiveReadinessSummary(readiness?: Record<string, unknown> | null): string {
  const sources = readiness?.required_sources;
  if (!sources || typeof sources !== "object" || !Object.keys(sources).length) return "Required source assessment unavailable.";
  const checks = Object.values(sources) as Array<{status?: string}>;
  return `Required sources ready: ${checks.filter(check => check.status === "READY").length}/${checks.length}. Final entry clearance is separate.`;
}

export function classicLiveSourceActions(readiness?: Record<string, unknown> | null): string[] {
  const sources = (readiness?.required_sources ?? {}) as Record<string, {status?: string}>;
  const actions: Record<string, string> = {
    salary_pool: "Salary: verify the original CSV lineage and resolve identities; a validated file does not need replacement.",
    projection: "Projections: rebuild from verified current source dependencies.",
    player_status: "Availability: resolve missing or stale player status and role evidence.",
    market: "Markets: refresh sourced spread and total for every slate game.",
    ownership: "Ownership: rebuild from the verified current projection.",
  };
  return Object.entries(sources).filter(([, check]) => check.status !== "READY").map(([name]) => actions[name] ?? `${name}: verify required evidence.`);
}
