import { gameEnvironmentReviewHtml } from "./classicGameEnvironment.ts";
import type { OptimizerResponse } from "./api";

type Row = Record<string, any>;
const escape = (value: unknown) => String(value ?? "Unavailable").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");
const points = (value: unknown) => typeof value === "number" && Number.isFinite(value) ? value.toFixed(2) : "Unavailable";

export function singleLineupReportHtml(optimizer: OptimizerResponse): string {
  const lineup = (Array.isArray(optimizer.results) ? optimizer.results[0] ?? [] : []) as Row[];
  const report = (lineup.find(row => row.single_lineup_report)?.single_lineup_report ?? optimizer.single_lineup_selection) as Row | undefined;
  if (!report) return ""; // Saved legacy reports keep their original presentation.
  const best = report.recommended as Row;
  if (!best) return `<section class="single-lineup-report"><h2>Requested lineup count could not be met</h2><p>Requested ${escape(report.requested_count)} · Selected 0. No limits were relaxed. No cash probability is available.</p><p>No candidate fits the saved user limits within this generated pool. Review the settings before starting another run.</p><details><summary>Saved lineup settings and constraint selection</summary><pre>${escape(JSON.stringify({ settings: report.user_constraints, selection: report.constraint_selection }, null, 2))}</pre></details></section>`;
  const contest = report.contest as Row | undefined;
  const facts = contest?.facts as Row | undefined;
  const candidates = (report.all_candidates ?? []) as Row[];
  const alternatives = (report.notable_alternatives ?? []) as Row[];
  const candidateRows = (rows: Row[]) => rows.map(row => `<tr><td>#${escape(row.rank)}</td><td>${points(row.selection_score)}</td><td>${points(row.expected_points)}</td><td>${points(row.downside_diagnostic)}</td><td>${points(row.upside_diagnostic)}</td><td>${escape(row.rejection_reason ?? (row.primary_recommendation === false ? "Additional requested lineup" : "Primary recommendation"))}</td></tr>`).join("");
  return `<section class="single-lineup-report" aria-label="Single cash-oriented lineup recommendation">
    <h2>Recommended ${optimizer.contest_format === "classic" ? "Classic" : "Captain / Showdown"} lineup</h2>
    <p><strong>Transparent cash-oriented selection proxy · unvalidated.</strong></p>
    <p>Requested ${escape(report.requested_count ?? 1)} lineup(s) · Selected ${escape(report.selected_count ?? 1)} · One primary recommendation.${(report.selected_count ?? 1) > 1 ? " Additional requested lineups appear below in cash-oriented rank order." : ""}</p>
    ${report.constraint_selection?.status === "underfilled" ? "<p><strong>Requested count could not be met within the candidate pool and user limits. No limits were relaxed. Review the saved settings before starting another run.</strong></p>" : ""}
    <p>Expected fantasy points: <strong>${points(best.expected_points)}</strong> · Downside diagnostic: ${points(best.downside_diagnostic)} · Upside diagnostic: ${points(best.upside_diagnostic)}.</p>
    <p>Cash probability unavailable. ${escape(report.cash_probability_unavailable_reason)}</p>
    <div style="overflow-x:auto"><table><thead><tr><th>Slot</th><th>Player</th><th>Team</th><th>Salary</th><th>Expected points</th></tr></thead><tbody>${lineup.map(p => `<tr><td>${escape(p.roster_position ?? p.position)}</td><td>${escape(p.name ?? p.player_name ?? p.player_id)}</td><td>${escape(p.player_team ?? p.team)}</td><td>${points(p.salary)}</td><td>${points(p.projection)}</td></tr>`).join("")}</tbody></table></div>
    ${optimizer.contest_format === "classic" ? gameEnvironmentReviewHtml(optimizer.classic_game_environment_review) : ""}
    <h3>Why this lineup was preferred</h3><p>${escape(report.why_preferred)}</p>
    <p>Score ${points(best.selection_score)} · ${escape(report.candidate_count)} unique legal candidates · competition evidence: ${escape(report.competition_status)}.</p>
    ${report.user_constraints ? `<details><summary>Saved lineup settings and constraint selection</summary><pre>${escape(JSON.stringify({ settings: report.user_constraints, selection: report.constraint_selection }, null, 2))}</pre></details>` : ""}
    <h3>Major risk factors</h3><ul>${(best.risk_factors as string[]).map(risk => `<li>${escape(risk)}</li>`).join("") || "<li>No additional player-specific risk flags; modeling limitations still apply.</li>"}</ul>
    <h3>Why notable alternatives were rejected</h3><div style="overflow-x:auto"><table><thead><tr><th>Candidate</th><th>Proxy score</th><th>Expected</th><th>Downside</th><th>Upside</th><th>Reason</th></tr></thead><tbody>${candidateRows(alternatives) || "<tr><td colspan=\"6\">No distinct alternative under these constraints.</td></tr>"}</tbody></table></div>
    <p>Contest evidence: ${escape(contest?.status ?? "generic_no_contest")}. ${facts ? `${escape(facts.name)} · paid places ${escape(facts.paid_places)} · capacity ${escape(facts.capacity)} · source ${escape(facts.source)}.` : "No specific contest supplied."} ${escape(contest?.note ?? "Generic cash-oriented objective; no contest cutoff inferred.")}</p>
    <details><summary>Candidate diagnostics / research (${escape(candidates.length)})</summary>
      <p>The selected candidates are marked. Unselected candidates remain research alternatives. Proxy contributions and full frozen rosters are retained.</p>
      <div style="overflow-x:auto"><table><thead><tr><th>Candidate</th><th>Proxy score</th><th>Expected</th><th>Downside</th><th>Upside</th><th>Reason</th></tr></thead><tbody>${candidateRows(candidates)}</tbody></table></div>
      ${candidates.map(row => `<details><summary>Candidate #${escape(row.rank)} roster and objective</summary><p>${(row.players as Row[]).map(p => `${escape(p.roster_position ?? p.position)} ${escape(p.name ?? p.player_name ?? p.player_id)}`).join(" · ")}</p><pre>${escape(JSON.stringify({ contributions: row.objective_contributions, deltas_vs_selected: row.term_deltas_vs_selected }, null, 2))}</pre></details>`).join("")}
      <p>Fixed weights: ${escape(JSON.stringify(report.objective_weights))}. Correlation assumptions: ${escape(best.correlation_assumptions)}.</p>
    </details>
    <details><summary>Modeling limitations and contest provenance</summary><ul>${(report.limitations as string[]).map(note => `<li>${escape(note)}</li>`).join("")}</ul><pre>${escape(JSON.stringify(contest, null, 2))}</pre></details>
  </section>`;
}
