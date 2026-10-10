type Row = Record<string, any>;

export const LOWER_CONCENTRATION_FAMILY = "QB + two WR/TE + one offensive bring-back";
export const LOWER_CONCENTRATION_LABEL = "Validated lower-concentration alternative on saved inputs";
const escape = (value: unknown) => String(value ?? "Unavailable").replace(/[&<>"']/g, c => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[c]!));
const number = (value: unknown) => typeof value === "number" ? value.toFixed(6) : "Unavailable";
const json = (value: unknown) => `<pre style="white-space:pre-wrap;overflow-wrap:anywhere">${escape(value == null ? "Unavailable" : JSON.stringify(value, null, 2))}</pre>`;

// Presentation only: use the returned canonical identities and frozen evidence.
// Never fetch, solve, persist a review, or assign roster slots here.
export function lowerConcentrationEvidenceHtml(review: Row): string {
  const result = review.comparisons?.find((row: Row) => row.family === LOWER_CONCENTRATION_FAMILY)?.replacement;
  if (result?.status !== "feasible" || result.portfolio_validation?.status !== "verified"
      || result.construction?.qb_pass_catchers !== 2 || result.construction?.bring_backs !== 1
      || !Number.isFinite(review.baseline?.construction?.max_team_all)
      || !Number.isFinite(result.construction?.max_team_all)
      || result.construction?.max_team_all >= review.baseline?.construction?.max_team_all) return "";
  const roster: Row[] = result.roster ?? [];
  const baseline: Row[] = review.baseline?.roster ?? [];
  const added = roster.filter(p => !baseline.some(b => b.player_id === p.player_id));
  const removed = baseline.filter(p => !roster.some(b => b.player_id === p.player_id));
  const names = (players: Row[]) => players.map(p => escape(p.name)).join(", ") || "None";
  const elevated = review.active_constraints?.elevated_player_ids;
  const risk = (p: Row) => !Array.isArray(elevated) ? "Unavailable" : elevated.includes(p.player_id) ? "Elevated (frozen)" : "Not listed in frozen elevated IDs";
  const components = Object.entries(result.components ?? {}).map(([key, value]) =>
    `<tr><td>${escape(key)}</td><td>${number(value)}</td><td>${escape(result.component_statuses?.[key]?.status)} ${escape(result.component_statuses?.[key]?.reason ?? "")}</td></tr>`).join("");
  const rb = review.comparisons?.find((row: Row) => row.family === "RB FLEX / three RBs")?.individual;
  const rbAdded: Row[] = rb?.roster?.filter((p: Row) => !baseline.some(b => b.player_id === p.player_id)) ?? [];
  const rbRemoved = baseline.filter(p => rb?.roster && !rb.roster.some((b: Row) => b.player_id === p.player_id));
  const rbBringbacks = rb?.stack?.bring_backs?.filter((p: Row) => p.position === "RB") ?? [];
  const exhaustedFamilies = (review.comparisons ?? []).filter((row: Row) => ["RB FLEX / three RBs", "TE FLEX / two TEs"].includes(row.family))
    .map((row: Row) => ({ family: row.family, players: (row.individual?.roster ?? []).filter((p: Row) => review.replacement_budgets?.remaining_player_appearances?.[p.player_id] === 0) }))
    .filter((row: Row) => row.players.length > 0);
  const rbComparison = rb?.status === "feasible" ? `<h4>WR baseline versus individual three-RB alternative</h4><p>${names(rbRemoved)} → ${names(rbAdded)}. Salary change $${escape(rb.salary - review.baseline.salary)}; mean ${number(rb.deltas_vs_saved_entry?.mean)}; summed marginal P90 ${number(rb.deltas_vs_saved_entry?.p90)}; objective ${number(rb.deltas_vs_saved_entry?.objective_score)}.</p><p>Offensive RB bring-back: ${names(rbBringbacks)}. Captured WR/TE bring-back reward: ${number(rb.components?.bring_back)}. A zero WR/TE reward does not mean no offensive bring-back.</p>${exhaustedFamilies.map((row: Row) => `<p>${escape(row.family)} individual cannot be inserted unchanged: ${names(row.players)} has zero remaining appearance budget. Exposure limits are retained.</p>`).join("")}<p>Individual quality under the formula, feasibility around the other four entries, and empirical tournament performance are separate questions.</p>` : "";
  return `<h4>${LOWER_CONCENTRATION_LABEL}</h4>
    <p>Saved run ${escape(review.job_id)} · entry ${escape(review.entry)} · diagnostic ${escape(review.request_id)}.</p>
    <p>Diagnostic alternative; not selected or applied. Current shared builder on frozen saved inputs. implementation_matches_saved=${escape(review.implementation_matches_saved)}. Saved team cap ${escape(review.active_constraints?.max_from_team)}; template minimums ${escape(review.active_template_minimums?.join(" / "))}.</p>
    <p>Salary $${escape(result.salary)} · projected mean ${number(result.mean)} · summed marginal P90 ${number(result.p90)} (NOT a lineup percentile) · objective ${number(result.objective_score)}.</p>
    <p>Versus saved entry: mean ${number(result.deltas_vs_saved_entry?.mean)} · summed marginal P90 ${number(result.deltas_vs_saved_entry?.p90)} · objective ${number(result.deltas_vs_saved_entry?.objective_score)}. Objective gaps are not winning-probability losses.</p>
    <div class="table-wrap"><table><thead><tr><th>Player</th><th>Position</th><th>Team</th><th>Salary</th><th>Frozen risk evidence</th><th>Canonical identity</th></tr></thead><tbody>${roster.map(p => `<tr><td>${escape(p.name)}</td><td>${escape(p.position)}</td><td>${escape(p.team)}</td><td>$${escape(p.salary)}</td><td>${risk(p)}</td><td>${escape(p.player_id)}</td></tr>`).join("")}</tbody></table></div>
    <p>Added: ${names(added)}. Removed: ${names(removed)}. Slots beyond natural positions are unavailable.</p>
    <p>Frozen risk membership is not current entry clearance; detailed risk reasons/timestamps are unavailable here.</p>
    <p>QB ${escape(result.qb?.name)} · same-team WR/TE: ${names(result.stack?.partners ?? [])} · offensive bring-back: ${names(result.stack?.bring_backs ?? [])}. QB-team offense including QB: ${escape(result.construction?.qb_team_offense_including_qb)} · QB-game players: ${escape(result.construction?.qb_game_all_players)} · primary game ${escape(result.construction?.primary_game)}.</p>
    <p>Portfolio validation: ${escape(result.portfolio_validation.status)} · violations: ${escape(result.portfolio_validation.violations?.join(", ") || "None")} · solver ${escape(result.solver?.solver_status)} (${escape(result.solver?.solution_status)}). Other entries remain fixed. This is not proof of joint portfolio optimality or empirical tournament performance.</p>
    <div class="table-wrap"><table><thead><tr><th>Weighted component</th><th>Contribution</th><th>Captured status</th></tr></thead><tbody>${components}</tbody></table></div>
    <p>Component sum matches solver: ${escape(result.component_sum_matches_solver)}. Leverage: ${escape(result.component_statuses?.leverage?.status)}; ownership-chalk: ${escape(result.component_statuses?.ownership_chalk?.status)}; duplication: ${escape(result.component_statuses?.duplication?.status)}. Absent evidence does not demonstrate differentiation.</p>
    <details><summary>Structural contributions, restrictions and replacement budgets</summary>${json({ correlation_rules: result.correlation_rules, construction: result.construction, active_constraints: review.active_constraints, replacement_budgets: review.replacement_budgets, portfolio_validation: result.portfolio_validation, solver: result.solver })}<p>No minimal binding-constraint certificate was captured.</p></details>${rbComparison}`;
}

export function constructionReviewExportHtml(review: Row): string {
  return `<!doctype html><html><head><meta charset="utf-8"><title>Saved-input construction review</title><style>body{font:16px system-ui;margin:32px;max-width:1100px}table{border-collapse:collapse}td,th{padding:8px;border:1px solid #bbb;text-align:left}.table-wrap{overflow:auto}</style></head><body>${lowerConcentrationEvidenceHtml(review)}<details><summary>Complete captured construction review (all comparisons)</summary>${json(review)}</details></body></html>`;
}

export function downloadConstructionReview(review: Row, format: "html" | "json") {
  const blob = new Blob([format === "html" ? constructionReviewExportHtml(review) : JSON.stringify(review, null, 2)],
    { type: format === "html" ? "text/html;charset=utf-8" : "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url; link.download = `construction-review-${review.job_id}-${review.request_id}.${format}`;
  link.click(); URL.revokeObjectURL(url);
}
