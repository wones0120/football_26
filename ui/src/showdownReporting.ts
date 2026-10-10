type Row = Record<string, unknown>;

export function showdownPreflightLabel(gateStatus: string, readiness?: Row | null): string {
  if (gateStatus === "fail" || readiness?.status === "NOT_READY" || readiness?.status === "ERROR") return "Blocked";
  return readiness?.status === "READY" ? "Saved inputs ready" : "Generation readiness unchecked";
}

export function qbLineupLimit(report: Row): number {
  return report.no_qbs ? 0 : report.no_two_qbs ? 1 : 2;
}

export function qbCaptainAllowed(report: Row): boolean {
  return !report.no_qbs && !report.no_qb_captain && report.allow_qb_captain !== false;
}

export function captainPositionsDescription(report: Row): string {
  if (!Array.isArray(report.allowed_positions)) return "Captain positions: unavailable in this saved report";
  return `Captain positions: ${report.allowed_positions.length ? report.allowed_positions.join(", ") + " only" : "Any position"}`;
}

export function teamLimitDescription(report: Row): string {
  const limit = report.max_players_per_team;
  if (limit === 3) return "Max players per team: 3 · requires 3–3";
  if (limit === 4) return "Max players per team: 4 · allows 4–2 and 3–3";
  if (limit === 5) return "Max players per team: 5 · allows 5–1, 4–2 and 3–3";
  return "Max players per team: unavailable in this saved report";
}

export function exposureWarning(row: Row): string | null {
  return Number(row.generated_lineups) < Number(row.requested_lineups)
    && Number(row.final_generated_portfolio_exposure) > Number(row.configured_cap) + 1e-8
    ? row.cap_status === "FAIL"
      ? "UNDERFILLED PORTFOLIO — realized exposure exceeds configured percentage; requested-count cap also failed."
      : "UNDERFILLED PORTFOLIO — requested-count cap passed, but realized final exposure exceeds configured percentage."
    : null;
}

// Older runs retained per-player conditional evidence, but not lineup totals.
// Read those saved values without falling back to a baseline as a condition.
export function conditionedTotal(row: Row, field: "mean" | "p90"): unknown {
  const total = row[`conditioned_${field}`];
  if (total != null) return total;
  if (row.scenario_id === "baseline") return row[`baseline_${field}`] ?? row[field];
  const players = (row.players ?? []) as Row[];
  const values = players.map(p => (p.adjustment as Row | undefined)?.[`scenario_${field}`]);
  return players.length === 6 && values.every(v => v != null && Number.isFinite(Number(v)))
    ? values.reduce<number>((sum, value) => sum + Number(value), 0) : null;
}

export function lineupConditionedTotal(lineup: Row[], field: "mean" | "p90"): string {
  const key = field === "mean" ? "conditioned_projection" : "conditioned_p90";
  const value = conditionedTotal({
    scenario_id: lineup[0]?.showdown_scenario_id,
    [`baseline_${field}`]: lineup.reduce((sum, row) => sum + Number(row[field === "mean" ? "projection" : "p90"] ?? 0), 0),
    [`conditioned_${field}`]: lineup.every(row => row[key] != null)
      ? lineup.reduce((sum, row) => sum + Number(row[key]), 0) : null,
    players: lineup.map(row => ({ adjustment: row.showdown_scenario_adjustment })),
  }, field);
  return value == null ? "Unavailable" : Number(value).toFixed(2);
}

export function captainFamilies(report: Row): Row[] {
  const retained = (report.family_rows ?? []) as Row[];
  const metrics = (report.ranked_metrics ?? []) as Row[];
  if (!metrics.length) return retained;
  const selected = new Set((report.selected_ranks ?? []) as number[]);
  const reasons = (report.omission_reasons ?? {}) as Record<string, string>;
  const ids = [...new Set(metrics.map(r => r.captain_player_id))];
  return ids.map((id): Row => {
    const rows = metrics.filter(r => r.captain_player_id === id).sort((a, b) => Number(a.rank) - Number(b.rank));
    const best = rows[0];
    const eligible = rows.find(r => r.quality_eligible === true);
    const reasonRow = eligible ?? best;
    const reason = selected.has(Number(reasonRow.rank)) ? "Selected candidate" : reasons[String(reasonRow.rank)] ?? "Reason unavailable";
    return { ...retained.find(r => r.captain_player_id === id), ...best,
      best_eligible_candidate: eligible, best_eligible_reason: eligible ? reason : null,
      selected: rows.some(r => selected.has(Number(r.rank))),
      reason: eligible ? reason : `No family candidate passed the joint screen. ${reason}` };
  }).sort((a, b) => Number(a.rank) - Number(b.rank));
}
