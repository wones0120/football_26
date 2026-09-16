import type { OptimizerResponse } from "./api.ts";
import { individualCeilingSummary } from "./optimizerPresentation.ts";

type ReportContext = {
  season: number;
  week: number;
  slate: string;
};

type ReportPlayer = Record<string, unknown>;

const escapeHtml = (value: unknown): string => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

const number = (value: unknown, digits = 2): string => {
  if (value === null || value === undefined || value === "") return "—";
  const parsed = Number(value);
  return Number.isFinite(parsed)
    ? parsed.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits })
    : "—";
};

const playerName = (player: ReportPlayer): string => String(
  player.name ?? player.player_name ?? player.player_display_name ?? player.player_id ?? "Unknown",
);

const playerSlot = (player: ReportPlayer): string => {
  const slot = String(player.roster_position ?? "").toUpperCase();
  const position = String(player.position ?? "").toUpperCase();
  return slot && position && slot !== position ? `${slot} · ${position}` : slot || position || "—";
};

const playerTeam = (player: ReportPlayer): string => String(
  player.player_team ?? player.team ?? player.recent_team ?? "—",
);

const projection = (player: ReportPlayer): number => Number(
  player.projection ?? player.predicted_mean ?? 0,
) || 0;

const ceiling = (player: ReportPlayer): number => Number(
  player.predicted_p90 ?? player.p90 ?? player.projection ?? 0,
) || 0;

const orderedLineup = (lineup: ReportPlayer[]): ReportPlayer[] => [...lineup].sort((left, right) => {
  const leftSlot = String(left.roster_position ?? "").toUpperCase();
  const rightSlot = String(right.roster_position ?? "").toUpperCase();
  if (leftSlot === "CPT" && rightSlot !== "CPT") return -1;
  if (rightSlot === "CPT" && leftSlot !== "CPT") return 1;
  const leftIndex = Number(left.lineup_slot_index);
  const rightIndex = Number(right.lineup_slot_index);
  if (Number.isFinite(leftIndex) && Number.isFinite(rightIndex)) return leftIndex - rightIndex;
  return projection(right) - projection(left);
});

const playerRules = (player: ReportPlayer): string => {
  if (player.symbolic_rule_summary) return String(player.symbolic_rule_summary);
  const explanations = Array.isArray(player.symbolic_explanations)
    ? player.symbolic_explanations as ReportPlayer[]
    : [];
  return explanations
    .map((item) => item.rule_id ?? item.rule_name)
    .filter(Boolean)
    .join(", ") || "—";
};

const playersLabel = (rows: unknown): string => Array.isArray(rows) && rows.length
  ? rows.map((row) => {
      const player = row as ReportPlayer;
      return `${playerName(player)} (${playerSlot(player)})`;
    }).join(", ")
  : "None";

function controlComparisonHtml(comparison: unknown): string {
  if (!comparison || typeof comparison !== "object") {
    return '<p class="muted">Control comparison unavailable for this saved run.</p>';
  }
  const value = comparison as ReportPlayer;
  const changed = Boolean(value.selection_changed);
  const effect = value.selection_effect === "alternate_optimum"
    ? "Tied alternative"
    : changed ? "Selection changed" : "Same selection";
  const scored = (value.scored_metrics ?? {}) as ReportPlayer;
  const control = (value.control_metrics ?? {}) as ReportPlayer;
  const deltas = (value.deltas_scored_minus_control ?? {}) as ReportPlayer;
  const metricRows = [
    ["mean", "Mean"],
    ["individual_ceiling_sum", "Individual Ceiling Sum"],
    ["salary", "Salary"],
    ["ownership_sum", "Ownership sum"],
    ["leverage_sum", "Leverage sum"],
  ].map(([key, label]) => `<tr><td>${label}</td><td>${number(scored[key])}</td><td>${number(control[key])}</td><td>${number(deltas[key])}</td></tr>`).join("");
  const contributions = Array.isArray(value.rule_contributions)
    ? (value.rule_contributions as ReportPlayer[]).map((rule) => `<tr><td>${escapeHtml(rule.rule_id)}</td><td>${number(rule.scored)}</td><td>${number(rule.control_if_enabled)}</td><td>${number(rule.delta)}</td></tr>`).join("")
    : "";
  return `<details><summary>Compare with rules disabled · ${effect}</summary>
    <p><strong>Selected instead:</strong> ${escapeHtml(playersLabel(value.selected_only))}<br>
    <strong>Control alternatives:</strong> ${escapeHtml(playersLabel(value.control_only))}</p>
    <table><thead><tr><th>Metric</th><th>Scored</th><th>Control</th><th>Delta</th></tr></thead><tbody>${metricRows}</tbody></table>
    <p>Base objective opportunity cost: ${number(value.base_objective_opportunity_cost)}.</p>
    <p><strong>Full control lineup:</strong> ${escapeHtml(playersLabel(value.control_lineup))}</p>
    ${contributions ? `<table><thead><tr><th>Rule</th><th>Scored</th><th>Control if enabled</th><th>Delta</th></tr></thead><tbody>${contributions}</tbody></table>` : ""}
  </details>`;
}

function lineupHtml(lineup: ReportPlayer[], index: number): string {
  const totalSalary = lineup.reduce((sum, player) => sum + (Number(player.salary) || 0), 0);
  const totalMean = lineup.reduce((sum, player) => sum + projection(player), 0);
  const ceilingSummary = individualCeilingSummary(lineup);
  const first = lineup[0] ?? {};
  const context = Number((first.lineup_context_summary as ReportPlayer | undefined)?.total_adjustment
    ?? lineup.reduce((sum, player) => sum + (Number(player.optimizer_context_adjustment) || 0), 0));
  const correlation = (first.lineup_correlation_summary ?? {}) as ReportPlayer;
  const correlationAdjustment = Number(correlation.total_adjustment ?? 0);
  const correlationRules = Array.isArray(correlation.triggered_rules)
    ? correlation.triggered_rules as ReportPlayer[]
    : [];
  const stack = (first.lineup_stack_summary as ReportPlayer | undefined)?.label;
  const script = (correlation.implied_game_script as ReportPlayer | undefined)?.label;
  const construction = correlation.construction_label;
  const ownershipValues = lineup
    .map((player) => player.ownership)
    .filter((value) => value !== null && value !== undefined && Number.isFinite(Number(value)));
  const ownershipSummary = ownershipValues.length === lineup.length
    ? `Ownership: ${number(ownershipValues.reduce<number>((sum, value) => sum + Number(value), 0))}`
    : "GPP ownership unavailable — optimizing ceiling/correlation only";
  const duplicationRisk = (first.lineup_duplication_risk ?? {}) as ReportPlayer;
  const chalkSummary = duplicationRisk.ownership_available
    ? `Relative chalk: ${number(duplicationRisk.relative_chalk_score, 1)}/100 · log ownership: ${number(duplicationRisk.log_probability, 3)}`
    : "Relative chalk unavailable";
  const summaryParts = [
    `Salary: ${totalSalary.toLocaleString()}`,
    `Mean: ${number(totalMean)}`,
    `${ceilingSummary.label}: ${number(ceilingSummary.value)}`,
    `Context: ${context >= 0 ? "+" : ""}${number(context)}`,
    `Correlation: ${correlationAdjustment >= 0 ? "+" : ""}${number(correlationAdjustment)}`,
    stack ? `Stack: ${String(stack)}` : null,
    script ? `Script: ${String(script)}` : null,
    construction ? `Construction: ${String(construction)}` : null,
    ownershipSummary,
    chalkSummary,
  ].filter(Boolean).map((item) => `<span class="metric">${escapeHtml(item)}</span>`).join("");
  const rules = correlationRules.length
    ? `<details><summary>Correlation rules (${correlationRules.length})</summary><ul>${correlationRules.map((rule) => {
        const contribution = Number(rule.objective_contribution ?? rule.score_contribution ?? 0);
        const players = Array.isArray(rule.players)
          ? (rule.players as ReportPlayer[]).map(playerName).join(" + ")
          : "";
        return `<li>${contribution >= 0 ? "+" : ""}${number(contribution)} · ${escapeHtml(rule.description ?? rule.reason_code)}${players ? ` · ${escapeHtml(players)}` : ""}</li>`;
      }).join("")}</ul></details>`
    : "";
  const rows = orderedLineup(lineup).map((player) => `<tr>
    <td>${escapeHtml(playerName(player))}</td><td>${escapeHtml(playerSlot(player))}</td>
    <td>${escapeHtml(playerTeam(player))}</td><td>${number(player.salary, 0)}</td>
    <td>${number(projection(player))}</td><td>${number(ceiling(player))}</td><td>${number(player.ownership)}</td>
    <td>${escapeHtml(playerRules(player))}</td></tr>`).join("");
  return `<section class="lineup"><h2>Lineup ${index + 1}</h2><div class="metrics">${summaryParts}</div>
    ${controlComparisonHtml(first.lineup_control_comparison)}${rules}
    <table><thead><tr><th>Player</th><th>Slot · Pos</th><th>Team</th><th>Salary</th><th>Proj</th><th>P90</th><th>Ownership</th><th>Rules</th></tr></thead><tbody>${rows}</tbody></table></section>`;
}

function portfolioDiagnosticsHtml(lineups: ReportPlayer[][]): string {
  const first = lineups[0]?.[0] ?? {};
  const exposure = (first.portfolio_exposure_report ?? {}) as ReportPlayer;
  const exposureRows = Array.isArray(exposure.rows) ? exposure.rows as ReportPlayer[] : [];
  const exposureHtml = exposureRows.length
    ? `<details open><summary>Portfolio exposure accounting</summary><p><strong>Requested/configured CPT max:</strong> ${number(Number(exposure.configured_captain_cap) * 100, 0)}% · effective maximum ${number(exposure.captain_maximum_appearances, 0)} appearance(s) across ${number(exposure.requested_lineups, 0)} requested lineups.</p><p>Caps use ${number(exposure.requested_lineups, 0)} requested lineups; final percentages use ${number(exposure.generated_lineups, 0)} generated lineups.</p><table><thead><tr><th>Player</th><th>Scope</th><th>Class</th><th>Cap</th><th>Maximum</th><th>Actual</th><th>Final exposure</th><th>Status</th></tr></thead><tbody>${exposureRows.map((row) => `<tr><td>${escapeHtml(row.player_name)}</td><td>${escapeHtml(row.scope)}</td><td>${escapeHtml(String(row.exposure_class).replaceAll("_", " "))}</td><td>${number(Number(row.configured_cap) * 100, 0)}%</td><td>${number(row.maximum_allowed_appearances, 0)} of ${number(row.requested_lineups, 0)} requested</td><td>${number(row.actual_appearances, 0)} of ${number(row.generated_lineups, 0)} generated</td><td>${number(Number(row.final_generated_portfolio_exposure) * 100, 1)}%</td><td>${escapeHtml(row.cap_status)} — ${number(row.actual_appearances, 0)} of ${number(row.requested_lineups, 0)} requested slots used</td></tr>`).join("")}</tbody></table></details>`
    : "";
  const underfill = (first.portfolio_underfill_diagnostics ?? {}) as ReportPlayer;
  const reasons = (underfill.reason_counts ?? {}) as Record<string, unknown>;
  const underfillHtml = Object.keys(reasons).length
    ? `<details open><summary>Under-fill rejection diagnostics</summary><p>Attempted lineup ${number(underfill.attempted_lineup_number, 0)}. Counts may overlap because one rejected solve can violate multiple constraint groups. Quality floors were not relaxed.</p><ul>${Object.entries(reasons).map(([reason, count]) => `<li>${escapeHtml(reason.replaceAll("_", " "))}: ${number(count, 0)}</li>`).join("")}</ul></details>`
    : "";
  const captain = (first.captain_diversification_report ?? {}) as ReportPlayer;
  const qualifyingCaptains = Array.isArray(captain.qualifying_captain_candidates)
    ? captain.qualifying_captain_candidates as ReportPlayer[] : [];
  const rejectedCaptains = Array.isArray(captain.quality_rejected_captain_candidates)
    ? captain.quality_rejected_captain_candidates as ReportPlayer[] : [];
  const captainExposures = Array.isArray(captain.final_captain_exposures)
    ? captain.final_captain_exposures as ReportPlayer[] : [];
  const selectionDiagnostics = (captain.selection_diagnostics ?? {}) as ReportPlayer;
  const selectedCaptainQuality = Array.isArray(selectionDiagnostics.selected_captain_quality)
    ? selectionDiagnostics.selected_captain_quality as ReportPlayer[] : [];
  const unselectedCaptains = Array.isArray(selectionDiagnostics.unselected_qualifying_captains)
    ? selectionDiagnostics.unselected_qualifying_captains as ReportPlayer[] : [];
  const selectedQualityHtml = selectedCaptainQuality.length
    ? `<h3>Selected Captain quality and marginal cost</h3><table><thead><tr><th>Captain</th><th>Selection</th><th>Lineup</th><th>Mean</th><th>P90</th><th>Δ mean vs first</th><th>Δ P90 vs first</th><th>Δ mean vs standalone</th><th>Δ P90 vs standalone</th><th>Standalone blockers at this step</th></tr></thead><tbody>${selectedCaptainQuality.flatMap((captainRow) => {
        const selectedLineups = Array.isArray(captainRow.selected_lineups)
          ? captainRow.selected_lineups as ReportPlayer[] : [];
        return selectedLineups.map((row) => {
          const blockers = Array.isArray(row.standalone_best_exposure_blockers)
            ? row.standalone_best_exposure_blockers as ReportPlayer[] : [];
          return `<tr><td>${escapeHtml(captainRow.player_name)} (${escapeHtml(captainRow.team)})</td><td>CPT #${number(row.selection_number, 0)}</td><td>${number(row.lineup_number, 0)}</td><td>${number(row.lineup_mean)}</td><td>${number(row.lineup_p90)}</td><td>${number(row.mean_delta_from_first_selected)}</td><td>${number(row.p90_delta_from_first_selected)}</td><td>${number(row.mean_delta_from_standalone_best)}</td><td>${number(row.p90_delta_from_standalone_best)}</td><td>${blockers.map((blocker) => escapeHtml(blocker.player_name)).join(", ") || "None"}</td></tr>`;
        });
      }).join("")}</tbody></table>`
    : "";
  const unselectedHtml = unselectedCaptains.length
      ? `<h3>Qualifying Captains not selected</h3><table><thead><tr><th>Captain</th><th>Standalone best</th><th>Primary reason</th><th>Best available sequential step</th></tr></thead><tbody>${unselectedCaptains.map((row) => {
        const standalone = (row.standalone_best ?? {}) as ReportPlayer;
        const bestStep = (row.best_available_sequential_step ?? {}) as ReportPlayer;
        const stepResults = Array.isArray(row.step_results)
          ? row.step_results as ReportPlayer[] : [];
        const stepText = bestStep.lineup_number
          ? `Lineup ${number(bestStep.lineup_number, 0)}: ${number(bestStep.lineup_mean)} mean / ${number(bestStep.lineup_p90)} P90 / ${number(bestStep.solver_objective_value)} objective; selected ${escapeHtml(bestStep.selected_captain_player_name)} at ${number(bestStep.selected_solver_objective_value)} (${number(bestStep.solver_objective_deficit)} candidate objective delta)`
          : "No unreserved step remained feasible under the constraints available at that point.";
        const stepAudit = stepResults.length
          ? `<details><summary>All lineup-step decisions</summary><ul>${stepResults.map((step) => {
              if (step.status === "captain_diversity_reserved_slot") {
                return `<li>Lineup ${number(step.lineup_number, 0)}: reserved for ${escapeHtml(step.reserved_for_player_name)}</li>`;
              }
              if (step.status === "available_lower_sequential_objective") {
                return `<li>Lineup ${number(step.lineup_number, 0)}: feasible at ${number(step.lineup_mean)} mean / ${number(step.lineup_p90)} P90 / ${number(step.solver_objective_value)} objective; ${escapeHtml(step.selected_captain_player_name)} selected at ${number(step.selected_solver_objective_value)} (${number(step.solver_objective_deficit)} candidate objective delta)</li>`;
              }
              const reasons = Array.isArray(step.reasons) ? step.reasons.map((reason) => String(reason).replaceAll("_", " ")).join(", ") : "other constraint";
              const blockers = Array.isArray(step.blocking_players) ? (step.blocking_players as ReportPlayer[]).map((blocker) => escapeHtml(blocker.player_name)).join(", ") : "";
              return `<li>Lineup ${number(step.lineup_number, 0)}: blocked by ${escapeHtml(reasons)}${blockers ? ` (${blockers})` : ""}</li>`;
            }).join("")}</ul></details>`
          : "";
        return `<tr><td>${escapeHtml(row.player_name)} (${escapeHtml(row.team)})</td><td>${number(standalone.lineup_mean)} mean / ${number(standalone.lineup_p90)} P90 / ${number(standalone.solver_objective_value)} objective</td><td>${escapeHtml(String(row.primary_reason).replaceAll("_", " "))}</td><td>${stepText}${stepAudit}</td></tr>`;
      }).join("")}</tbody></table>`
    : "";
  const captainHtml = captain.enabled
    ? `<details open><summary>Captain diversification</summary><p>Target: at least ${number(captain.minimum_distinct_target, 0)} distinct qualifying Captains${captain.both_teams_target ? " with both teams represented" : ""}. Status: <strong>${captain.targets_achieved ? "PASS" : "LIMITED"}</strong>.</p>
      ${selectionDiagnostics.construction_mode ? `<p><strong>Portfolio construction:</strong> ${escapeHtml(String(selectionDiagnostics.construction_mode).replaceAll("_", " "))}. ${escapeHtml(selectionDiagnostics.explanation)}</p>` : ""}
      <p><strong>Final Captain exposure:</strong> ${captainExposures.map((row) => `${escapeHtml(row.player_name)} (${escapeHtml(row.team)}): ${number(row.appearances, 0)}/${number(exposure.generated_lineups, 0)} · ${number(Number(row.exposure) * 100, 1)}%`).join("; ") || "None"}</p>
      <p><strong>Qualifying Captain candidates (${qualifyingCaptains.length}):</strong> ${qualifyingCaptains.map((row) => `${escapeHtml(row.player_name)} (${escapeHtml(row.team)} · ${number(row.lineup_mean)} mean · ${number(row.lineup_p90)} P90 · ${number(row.solver_objective_value)} solver objective)`).join("; ") || "None"}</p>
      <p><strong>Rejected by quality floors (${rejectedCaptains.length}):</strong> ${rejectedCaptains.map((row) => `${escapeHtml(row.player_name)} (${escapeHtml(row.team)}${row.failed_mean_floor ? " · mean" : ""}${row.failed_p90_floor ? " · P90" : ""})`).join("; ") || "None"}</p>${selectedQualityHtml}${unselectedHtml}</details>`
    : "";
  return exposureHtml + captainHtml + underfillHtml;
}

function singleEntryReportHtml(lineups: ReportPlayer[][]): string {
  const report = lineups[0]?.[0]?.single_entry_report as ReportPlayer | undefined;
  if (!report) return "";
  const comparisons = (report.portfolio_comparisons ?? {}) as ReportPlayer;
  const selected = (report.selected_portfolio_comparison ?? {}) as ReportPlayer;
  const contestSelection = (report.contest_selection ?? {}) as ReportPlayer;
  const rankedContests = Array.isArray(contestSelection.ranked_contests) ? contestSelection.ranked_contests as ReportPlayer[] : [];
  const selectedIds = Array.isArray(contestSelection.selected_contest_ids) ? contestSelection.selected_contest_ids as string[] : [];
  const countComparisons = Array.isArray(contestSelection.count_comparisons) ? contestSelection.count_comparisons as ReportPlayer[] : [];
  const sensitivity = Array.isArray(contestSelection.sensitivity) ? contestSelection.sensitivity as ReportPlayer[] : [];
  const sensitivityHtml = sensitivity.length ? `<h3>Correlation sensitivity</h3><p>Fixed shared-rank weights blend independent-rank and fully shared-percentile payout proxies. The best subset may change at each weight.</p><table><thead><tr><th>Shared-rank weight</th>${countComparisons.map((row) => `<th>${number(row.contest_count, 0)} contest(s)</th>`).join("")}<th>Preferred count</th></tr></thead><tbody>${sensitivity.map((row) => `<tr><td>${number(Number(row.shared_rank_weight) * 100, 0)}%</td>${((row.by_count ?? []) as ReportPlayer[]).map((value) => `<td>${number(Number(value.profitability_proxy) * 100, 2)}%</td>`).join("")}<td>${number(row.recommended_count, 0)}</td></tr>`).join("")}</tbody></table><p>${((contestSelection.crossovers ?? []) as ReportPlayer[]).length ? ((contestSelection.crossovers ?? []) as ReportPlayer[]).map((row) => `Around ${number(Number(row.shared_rank_weight_approx) * 100, 1)}%: ${number(row.from_count, 0)} → ${number(row.to_count, 0)} contests`).join(" · ") : "No count crossover from 0% to 100% shared rank."}</p><h3>Recommended count: ${number(contestSelection.selected_count, 0)} · ${escapeHtml(contestSelection.recommendation_status)}</h3><p>${escapeHtml(contestSelection.recommendation_status_reason)} This is a heuristic stability label, not statistical confidence.</p>${contestSelection.overlay_changed_recommendation ? `<p>Near-lock overlay changed the count versus the full-field reference (${number(contestSelection.full_field_reference_count, 0)}).</p>` : ""}` : "";
  const contestHtml = rankedContests.length ? `<h3>Contest selection</h3>
    <p>${escapeHtml(contestSelection.mode)} · ${number(contestSelection.selected_count, 0)} of ${number(contestSelection.available_count, 0)} contests · $${number(contestSelection.total_entry_fees, 2)} total entry fees. ${escapeHtml(contestSelection.note)}</p>
    <p>${escapeHtml(contestSelection.selection_reason)} Search: ${escapeHtml(contestSelection.search_method)}; ${number(contestSelection.evaluated_subsets, 0)} subsets evaluated.</p>
    <h3>Best subset by contest count</h3><table><thead><tr><th>Contests</th><th>Best subset</th><th>Entry fees</th><th>Heuristic value</th><th>Independent ranks</th><th>Shared percentile</th></tr></thead><tbody>${countComparisons.map((row) => `<tr><td>${number(row.contest_count, 0)}</td><td>${escapeHtml(((row.contest_names ?? row.contest_ids) as string[]).join(", "))}</td><td>$${number(row.total_entry_fees, 2)}</td><td>${number(Number(row.heuristic_value) * 100, 1)}%</td><td>${number(Number(row.independent_rank_proxy) * 100, 1)}%</td><td>${number(Number(row.shared_percentile_proxy) * 100, 1)}%</td></tr>`).join("")}</tbody></table>${sensitivityHtml}<h3>Available contests</h3>
    <div style="overflow-x:auto"><table><thead><tr><th>Selected</th><th>Contest</th><th>Single-contest proxy</th><th>Entry</th><th>Field</th><th>Paid</th><th>Min cash</th><th>Top 1%</th><th>5%</th><th>10%</th><th>20%</th><th>Median paid</th><th>1st share</th><th>Top 10 share</th><th>Flatness</th><th>Full rake</th><th>Near-lock rake / overlay</th></tr></thead><tbody>${rankedContests.map((row) => { const e = (row.economics ?? {}) as ReportPlayer; const percentiles = (e.payout_at_field_percentiles ?? {}) as ReportPlayer; return `<tr><td>${selectedIds.includes(String(row.contest_id)) ? "Yes" : "No"}</td><td>${escapeHtml(row.name)}</td><td>${number(Number(row.contest_score) * 100, 1)}%</td><td>$${number(row.entry_fee, 2)}</td><td>${number(row.capacity, 0)}</td><td>${number(Number(e.paid_percentage) * 100, 1)}%</td><td>$${number(e.minimum_cash, 2)} (${number(e.minimum_cash_multiple, 2)}×)</td><td>$${number(percentiles["1"], 2)}</td><td>$${number(percentiles["5"], 2)}</td><td>$${number(percentiles["10"], 2)}</td><td>$${number(percentiles["20"], 2)}</td><td>$${number(e.median_paid_payout, 2)}</td><td>${number(Number(e.first_place_share) * 100, 1)}%</td><td>${number(Number(e.top_10_share) * 100, 1)}%</td><td>${number(e.payout_flatness, 3)}</td><td>${number(Number(e.full_field_rake) * 100, 1)}%</td><td>${e.current_effective_rake == null ? "Too early" : `${number(Number(e.current_effective_rake) * 100, 1)}% / $${number(e.current_overlay, 2)}`}</td></tr>`; }).join("")}</tbody></table></div>` : "";
  const comparisonRows = [comparisons.aaa, comparisons.best_one_alternate, comparisons.best_repeated_alternate, comparisons.best_two_alternates]
    .filter(Boolean) as ReportPlayer[];
  const comparisonHtml = comparisonRows.map((row) => `<tr><td>${escapeHtml(row.structure)}</td><td>${escapeHtml((row.candidate_ranks as number[]).join(" / "))}</td><td>${number(row.quality_loss_total, 3)}</td><td>${number(row.diversification_credit_total, 3)}</td><td>${number(row.heuristic_delta_vs_aaa, 3)}</td></tr>`).join("");
  const featured = (report.top_alternates ?? {}) as ReportPlayer;
  const alternateRows: [string, unknown][] = [
    ["Different Captain, same six players", featured.different_captain_only],
    ["Different Captain and player combination", featured.different_captain_material_players],
    ["Different game script", featured.different_game_script],
  ];
  const candidates = [
    ...((report.candidates ?? []) as ReportPlayer[]),
    ...((report.selected_candidates ?? []) as ReportPlayer[]),
    ...alternateRows.map(([, row]) => row).filter(Boolean) as ReportPlayer[],
  ];
  const unique = [...new Map(candidates.map((row) => [Number(row.rank), row])).values()]
    .sort((left, right) => Number(left.rank) - Number(right.rank));
  const multipleContests = ((report.assignments ?? []) as ReportPlayer[]).length > 1;
  const assignmentOptions = [report.assignment_comparison_aa, report.assignment_comparison_ab,
    ...((report.assignment_comparisons ?? []) as ReportPlayer[])].filter(Boolean) as ReportPlayer[];
  const seenAssignments = new Set<string>();
  const assignmentRows = assignmentOptions.filter((row) => {
    const key = ((row.candidate_ranks ?? []) as number[]).join(",");
    if (seenAssignments.has(key)) return false;
    seenAssignments.add(key);
    return true;
  }).slice(0, 12);
  const assignmentHtml = assignmentRows.length ? `<h3>Lineup assignment and adaptive payout proxy</h3><p>${escapeHtml(report.lineup_correlation_formula)}</p><table><thead><tr><th>Structure / ranks</th><th>Mean / P90 / chalk by entry</th><th>Cost</th><th>Shared / overlap / Jaccard</th><th>Captain / script / team</th><th>Quality loss / diversity</th><th>Correlation proxy / shared weight</th><th>Independent / shared / adaptive payout proxy</th><th>Joint delta</th></tr></thead><tbody>${assignmentRows.map((row) => { const pairs = (row.pair_diagnostics ?? []) as ReportPlayer[]; const means = (row.mean_by_entry ?? []) as number[]; const p90s = (row.p90_by_entry ?? []) as number[]; const chalk = (row.relative_chalk_by_entry ?? []) as number[]; return `<tr><td>${escapeHtml(row.structure)} (#${escapeHtml(((row.candidate_ranks ?? []) as number[]).join(" / #"))})</td><td>${means.map((value, index) => `${number(value, 1)} / ${number(p90s[index], 1)} / ${number(chalk[index], 1)}`).join("; ")}</td><td>$${number(row.total_entry_fees, 2)}</td><td>${pairs.map((pair) => `${number(pair.shared_players, 0)}/6 · ${number(pair.overlap_percentage, 1)}% · ${number(pair.jaccard_similarity, 3)}`).join("; ")}</td><td>${pairs.map((pair) => `${pair.same_captain ? "same" : "different"} / ${pair.same_script ? "same" : "different"} / ${pair.same_team_emphasis ? "same" : "different"}`).join("; ")}</td><td>${number(row.quality_loss_total, 3)} / ${number(row.diversification_credit_total, 3)}</td><td>${number(row.lineup_correlation_proxy, 3)} / ${number(Number(row.adaptive_shared_rank_weight) * 100, 1)}%</td><td>${number(Number(row.independent_rank_proxy) * 100, 2)}% / ${number(Number(row.shared_percentile_proxy) * 100, 2)}% / ${number(Number(row.adaptive_profitability_proxy) * 100, 2)}%</td><td>${number(row.joint_heuristic_delta_vs_repeat_a, 3)}</td></tr>`; }).join("")}</tbody></table><p>Selected ${escapeHtml(selected.structure)} by the joint heuristic. Contest placement uses field size × top-10 prize share as a restrained tie-break.</p>` : "";
  const candidateRows = unique.map((row) => {
    const script = (row.game_script ?? {}) as ReportPlayer;
    const players = Array.isArray(row.players) ? row.players as ReportPlayer[] : [];
    return `<tr><td>${number(row.rank, 0)}</td><td>${escapeHtml(row.captain)}</td><td>${number(row.mean, 1)}</td><td>${number(row.p90, 1)}</td><td>${number(row.relative_chalk, 1)}</td><td>${escapeHtml(script.label)}</td>${multipleContests ? `<td>${number(row.shared_players_with_a, 0)}/6</td><td>${number(row.overlap_percentage_vs_a, 1)}%</td><td>${number(row.jaccard_similarity_vs_a, 3)}</td><td>${number(row.quality_loss_vs_a, 3)}</td><td>${number(row.diversification_benefit_vs_a, 3)}</td>` : ""}<td>${escapeHtml(players.map((player) => `${player.slot} ${player.name}`).join(", "))}</td></tr>`;
  }).join("");
  return `<section class="lineup"><h2>Recommended portfolio: ${escapeHtml(report.recommended_structure ?? "A")}</h2>
    ${contestHtml}
    ${assignmentHtml}
    <h3>Recommended lineup assignment</h3><ul>${((report.assignments ?? []) as ReportPlayer[]).map((row) => `<li>${escapeHtml(row.contest_name ?? `Contest ${row.contest}`)} (${escapeHtml(row.contest_id ?? "")}) → candidate #${number(row.candidate_rank, 0)}. ${escapeHtml(row.reason)}</li>`).join("")}</ul>
    <p>${multipleContests ? "Lineup assignment is heuristic; lineup payout probabilities require game and opponent-field simulation." : "One contest selected; lineup A is the highest-ranked single-entry construction."} P90 is the sum of player P90 projections.</p>
    ${multipleContests && Number(report.evaluated_portfolio_count) > 0 ? `<p>Compared ${number(report.evaluated_portfolio_count, 0)} candidate combinations with repetition; the table shows the strongest in each structure.</p>` : ""}
    ${multipleContests && comparisonRows.length ? `
    <p>Letters name distinct lineups within each row; candidate ranks identify the exact lineups.</p>
    <p>Versus A / A / A: ${number(selected.diversification_credit_total, 3)} diversification credit − ${number(selected.quality_loss_total, 3)} quality loss = ${number(selected.heuristic_delta_vs_aaa, 3)} heuristic points. The best A / B / C scores ${number((comparisons.best_two_alternates as ReportPlayer | undefined)?.heuristic_delta_vs_aaa, 3)}.</p>` : ""}
    ${multipleContests && comparisonRows.length ? `<table><thead><tr><th>Structure</th><th>Candidate ranks</th><th>Quality loss</th><th>Diversification credit</th><th>Delta vs A / A / A</th></tr></thead><tbody>${comparisonHtml}</tbody></table>` : ""}
    ${multipleContests ? `<h3>Closest construction alternatives</h3><p>Material player change: at least ${number(report.material_player_change_minimum, 0)} of six players.</p>
    <ul>${alternateRows.map(([label, value]) => {
      const row = value as ReportPlayer | undefined;
      return `<li>${escapeHtml(label)}: ${row ? `#${number(row.rank, 0)} ${escapeHtml(row.captain)} · ${escapeHtml((row.game_script as ReportPlayer)?.label)} · quality loss ${number(row.quality_loss_vs_a, 3)} · benefit ${number(row.diversification_benefit_vs_a, 3)}` : "No qualifying candidate in the generated pool"}</li>`;
    }).join("")}</ul>` : ""}
    <h3>${multipleContests ? "Selected, top 10, and featured alternate lineups" : "Selected lineup and top candidates"}</h3><div style="overflow-x:auto"><table><thead><tr><th>Rank</th><th>Captain</th><th>Mean</th><th>Sum P90</th><th>Relative chalk</th><th>Script</th>${multipleContests ? "<th>Shared with A</th><th>Overlap</th><th>Jaccard</th><th>Quality loss</th><th>Diversification benefit</th>" : ""}<th>Players</th></tr></thead><tbody>${candidateRows}</tbody></table></div></section>`;
}

export function buildOptimizerReportHtml(
  optimizer: OptimizerResponse,
  context: ReportContext,
): string {
  const lineups = Array.isArray(optimizer.results)
    ? optimizer.results.filter(Array.isArray) as ReportPlayer[][]
    : [];
  const pool = optimizer.player_pool;
  const poolSummary = pool
    ? `Raw pool: ${pool.raw_pool_count ?? pool.initial_count} → opportunity eligible: ${pool.opportunity_eligible_count ?? pool.eligible_count ?? pool.initial_count} → optimizer eligible: ${pool.optimizer_eligible_count ?? pool.included_count} · Pool warnings: ${pool.warning_player_count ?? 0}`
    : "Player-pool summary unavailable";
  const removalSummary = pool?.removal_reason_counts && Object.keys(pool.removal_reason_counts).length
    ? `Removals: ${Object.entries(pool.removal_reason_counts).map(([reason, count]) => `${reason.replaceAll("_", " ")} (${count})`).join(" · ")}`
    : "No pool removals.";
  const removedPlayers = pool?.rows?.filter((row) => row.removal_stage === "opportunity_gate") ?? [];
  const removedPlayerDetails = removedPlayers.length
    ? `<details><summary>Opportunity removals (${removedPlayers.length})</summary><ul>${removedPlayers.map((row) => {
        const reasons = Array.isArray(row.exclusion_reasons) && row.exclusion_reasons.length
          ? row.exclusion_reasons.map((reason) => String(reason).replaceAll("_", " ")).join(", ")
          : "reason unavailable";
        return `<li>${escapeHtml(row.player_name)} · ${escapeHtml(reasons)}</li>`;
      }).join("")}</ul></details>`
    : "";
  const title = `${context.season} Week ${context.week} ${context.slate.replaceAll("_", " ")} Optimizer Report`;
  return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>${escapeHtml(title)}</title><style>
  :root{font-family:Inter,system-ui,sans-serif;color:#e8edf4;background:#0b1017}body{max-width:1200px;margin:0 auto;padding:32px}h1,h2{color:#fff}.meta,.muted{color:#9aa8b8}.lineup{border:1px solid #273241;border-radius:12px;padding:20px;margin:24px 0;background:#101720}.metrics{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}.metric{margin-right:14px}table{border-collapse:collapse;width:100%;margin:14px 0}th,td{text-align:left;padding:9px;border-bottom:1px solid #273241;vertical-align:top}th{color:#9aa8b8;background:#121b27}summary{cursor:pointer;font-weight:650;margin:12px 0}li{margin:6px 0}@media print{:root{color:#111;background:#fff}body{padding:0}h1,h2{color:#111}.lineup{break-inside:avoid;background:#fff;border-color:#bbb}th{color:#333;background:#eee}th,td{border-color:#ccc}}
  </style></head><body><h1>${escapeHtml(title)}</h1>
  <div class="meta"><p>Job ${escapeHtml(optimizer.job_id)} · ${escapeHtml(optimizer.contest_format)} ${escapeHtml(optimizer.objective)} · ${escapeHtml(optimizer.strategy)}</p>
  <p>${escapeHtml(optimizer.message ?? optimizer.status)}</p><p>${escapeHtml(poolSummary)}</p><p>${escapeHtml(removalSummary)}</p>${removedPlayerDetails}</div>
  ${singleEntryReportHtml(lineups)}${portfolioDiagnosticsHtml(lineups)}${lineups.map(lineupHtml).join("")}<footer class="meta">Generated ${escapeHtml(new Date().toLocaleString())}</footer></body></html>`;
}

export function downloadOptimizerReport(
  optimizer: OptimizerResponse,
  context: ReportContext,
): void {
  const blob = new Blob([buildOptimizerReportHtml(optimizer, context)], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `optimizer-report-${context.season}-w${context.week}-${context.slate.toLowerCase()}-${optimizer.job_id.slice(0, 8)}.html`;
  link.click();
  URL.revokeObjectURL(url);
}
