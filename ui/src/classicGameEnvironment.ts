export const RESEARCH_LABEL = "RESEARCH_ONLY / OBSERVATIONAL / NOT PRODUCTION VALIDATED";
export const HISTORICAL_CONTEXT = "Historical research context: top-10% offensive selections were 45.9% highest quarter, 38.1% middle half and 16.0% lowest quarter; field 40.0%, 41.0% and 19.0%. Eight contests, three slates (2026 Weeks 1–3). These are observations, not lineup targets. Top 10% is not actual cashing; cash outcomes unavailable.";
export type EnvironmentPlayer = {
  player_id: string; player: string; position: string; slot: string; team: string | null; opponent: string | null;
  game_id: string | null; game_total: number | null; team_spread: number | null; team_implied_points: number | null;
  opponent_implied_points: number | null; tier: string | null; projection: number | null; projected_ownership: number | null;
  ownership_run_id: string | null; market_source: string | null; market_snapshot_id: string | null;
  source_snapshot_id: string | null; market_observed_at: string | null; market_ingested_at: string | null; availability_reason: string | null;
};
export type GameEnvironmentReview = {
  contract_id: string; nonbinding: boolean; primary_lineup_only: boolean; selection_effect: string; status: string;
  frozen_at: string | null; evidence_cutoff: string | null; evidence_sha256: string | null;
  rows: EnvironmentPlayer[]; tier_convention: string; spread_convention: string; freshness_basis: string;
  roster_valid: boolean; slate_games: number; verified_market_games: number;
  composition: { offensive_slots: number; highest_quarter: number; middle_half: number; lowest_quarter: number; unavailable: number;
    mean_offensive_game_total: number | null; distinct_offensive_games: number | null;
    by_position: Record<string, Record<string, number>> } | null;
  dst: EnvironmentPlayer | null; observations: string[]; limitations: string[];
};
export type ClassicEnvironmentResearch = {
  contract_id: string; title: string; label: string; verification: string; sample_period: string; success_definition: string;
  sample: { contests: number; independent_slates: number; top_10_entries: number; field_entries: number };
  rows: { tier: string; top_10: number; field: number }[];
  findings: string[]; limitations: string[]; controlled_comparisons: string[];
  source: { path: string; sha256: string; reproduced_at: string }; cash_outcomes: string;
};
const escape = (value: unknown) => String(value ?? "Unavailable").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");
const fmt = (v: unknown, digits = 1) => typeof v === "number" && Number.isFinite(v) ? v.toFixed(digits) : "Unavailable";
const tierNames: Record<string, string> = { highest_quarter: "Highest quarter", middle_half: "Middle half", lowest_quarter: "Lowest quarter" };
const tier = (v: string | null) => tierNames[v ?? ""] ?? "Unavailable";

export function gameEnvironmentReviewHtml(review?: GameEnvironmentReview | null): string {
  if (!review || review.contract_id !== "classic_game_environment_review_v1" || review.nonbinding !== true || review.selection_effect !== "none") {
    return `<details aria-label="Classic Game Environment Review"><summary>Classic Game Environment Review</summary><p>Unavailable: this saved run has no supported frozen review.</p><p>Informational only. No lineup selection effect.</p></details>`;
  }
  const c = review.composition, dst = review.dst;
  return `<details aria-label="Classic Game Environment Review"><summary>Classic Game Environment Review · ${escape(review.status)}</summary>
    <p><strong>${review.verified_market_games > 0 ? "Verified frozen current-slate information" : "Current-slate evidence unavailable"} · informational only.</strong> One primary recommendation. No selection effect.</p>
    <p>Frozen at ${escape(review.frozen_at)} · Evidence cutoff ${escape(review.evidence_cutoff)} · Verified market games ${review.verified_market_games}/${review.slate_games}.</p>
    <p>${escape(review.freshness_basis)}</p>
    ${c ? `<p>Eight offensive slots, including FLEX: highest quarter <strong>${c.highest_quarter}</strong> · middle half <strong>${c.middle_half}</strong> · lowest quarter <strong>${c.lowest_quarter}</strong> · Unavailable <strong>${c.unavailable}</strong>.</p>
      <p>Average offensive game total ${fmt(c.mean_offensive_game_total, 2)} · Distinct offensive games ${escape(c.distinct_offensive_games)}.</p>
      <div style="overflow-x:auto"><table><thead><tr><th>Position</th><th>Slots</th><th>Highest quarter</th><th>Middle half</th><th>Lowest quarter</th><th>Unavailable</th></tr></thead><tbody>${Object.entries(c.by_position).map(([pos,x]) => `<tr><td>${escape(pos)}</td><td>${x.slots}</td><td>${x.highest_quarter}</td><td>${x.middle_half}</td><td>${x.lowest_quarter}</td><td>${x.unavailable}</td></tr>`).join("")}</tbody></table></div>` : "<p>Offensive composition unavailable: a legal nine-player Classic roster is required.</p>"}
    <div style="overflow-x:auto"><table><thead><tr><th>Player</th><th>Position / slot</th><th>Team</th><th>Opponent</th><th>Game O/U</th><th>Team spread</th><th>Team implied</th><th>Tier</th><th>Projected points</th><th>Projected ownership</th></tr></thead><tbody>${review.rows.map(p => `<tr><td>${escape(p.player)}</td><td>${escape(p.position)} / ${escape(p.slot)}</td><td>${escape(p.team)}</td><td>${escape(p.opponent)}</td><td>${fmt(p.game_total)}</td><td>${fmt(p.team_spread)}</td><td>${fmt(p.team_implied_points)}</td><td>${tier(p.tier)}</td><td>${fmt(p.projection, 2)}</td><td>${p.projected_ownership === null ? "Unavailable" : fmt(p.projected_ownership) + "%"}</td></tr>`).join("")}</tbody></table></div>
    <p><strong>DST separately:</strong> ${escape(dst?.player)} · game O/U ${fmt(dst?.game_total)} · <strong>opponent implied points ${fmt(dst?.opponent_implied_points)}</strong>.</p>
    <ul>${review.observations.map(v => `<li>${escape(v)}</li>`).join("")}</ul>
    <p><strong>${RESEARCH_LABEL}</strong></p><p>${HISTORICAL_CONTEXT}</p>
    <details><summary>Source evidence, unavailable inputs and tier convention</summary><p>${escape(review.tier_convention)}</p><p>${escape(review.spread_convention)}</p>
      <ul>${review.rows.map(p => `<li>${escape(p.player)}: ${escape(p.market_source)} · snapshot ${escape(p.market_snapshot_id)} · raw source ${escape(p.source_snapshot_id)} · observed ${escape(p.market_observed_at)} · received ${escape(p.market_ingested_at)} · projected ownership run ${escape(p.ownership_run_id)}.${p.availability_reason ? " " + escape(p.availability_reason) : ""}</li>`).join("")}</ul>
      <p style="overflow-wrap:anywhere">Frozen evidence SHA-256: ${escape(review.evidence_sha256)}</p>${review.limitations.map(x => `<p>${escape(x)}</p>`).join("")}</details>
  </details>`;
}
