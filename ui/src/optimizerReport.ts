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
  player.p90 ?? player.predicted_p90 ?? player.projection ?? 0,
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
    : "Lineup ownership unavailable: one or more selected slots lack ownership";
  const duplicationRisk = (lineup.find((player) => player.lineup_duplication_risk)?.lineup_duplication_risk ?? {}) as ReportPlayer;
  const chalkSummary = duplicationRisk.ownership_available
    ? `Relative chalk: ${number(duplicationRisk.relative_chalk_score, 1)}/100 · log ownership: ${number(duplicationRisk.log_probability, 3)}`
    : "Relative chalk unavailable";
  const selection = (first.showdown_selection_diagnostic ?? {}) as ReportPlayer;
  const scenario = (first.showdown_scenario ?? {}) as ReportPlayer;
  const scenarioPlayers = lineup.some((row) => row.showdown_scenario_adjustment);
  const scenarioHtml = scenarioPlayers ? `<details open><summary>Game-script scenario and player changes</summary><p><strong>Scenario:</strong> ${escapeHtml(scenario.label ?? "BASELINE / MARKET SCRIPT")} · conditioned winner ${escapeHtml(scenario.conditioned_winner ?? "None")} · decisive threshold ${number(scenario.decisive_margin_threshold, 0)} points · team split ${escapeHtml([...new Set(lineup.map((row) => String(row.player_team ?? "")))].sort().map((team) => `${team} ${lineup.filter((row) => row.player_team === team).length}`).join(" / "))}. Candidate source: ${escapeHtml(first.showdown_candidate_source ?? "baseline")}. Selection: ${escapeHtml(selection.selection_reason ?? "unavailable")}.</p><p>Baseline lineup mean ${number(lineup.reduce((sum, row) => sum + Number(row.baseline_projection ?? row.projection ?? 0), 0))} · scenario mean ${number(totalMean)} · baseline summed P90 ${number(lineup.reduce((sum, row) => sum + Number(row.baseline_p90 ?? row.p90 ?? 0), 0))} · scenario summed P90 ${number(ceilingSummary.value)}. These P90 values are sums of player ceilings, not joint lineup quantiles.</p><table><thead><tr><th>Player</th><th>Baseline mean</th><th>Scenario mean</th><th>Baseline P90</th><th>Scenario P90</th><th>Change</th><th>Reason</th></tr></thead><tbody>${orderedLineup(lineup).map((row) => { const adjustment = (row.showdown_scenario_adjustment ?? {}) as ReportPlayer; return `<tr><td>${escapeHtml(playerName(row))}</td><td>${number(row.baseline_projection ?? row.projection)}</td><td>${number(row.projection)}</td><td>${number(row.baseline_p90 ?? row.p90)}</td><td>${number(row.p90)}</td><td>${number(Number(row.projection ?? 0) - Number(row.baseline_projection ?? row.projection ?? 0))}</td><td>${escapeHtml(adjustment.reason ?? "market baseline")}</td></tr>`; }).join("")}</tbody></table></details>` : "";
  const gameEnvironment = (first.showdown_game_environment ?? {}) as ReportPlayer;
  const marketTeams = Array.isArray(gameEnvironment.teams)
    ? gameEnvironment.teams as ReportPlayer[] : [];
  const qbFactors = lineup.filter((player) => player.position === "QB" && player.qb_correlation_multiplier != null)
    .map((player) => `${escapeHtml(player.name)} ×${number(player.qb_correlation_multiplier, 2)}`);
  const gameEnvironmentHtml = marketTeams.length ? `<details open><summary>Team count and game environment</summary><p>${escapeHtml(gameEnvironment.team_counts)} · total ${gameEnvironment.game_total == null ? "Unavailable" : number(gameEnvironment.game_total)} · market source ${escapeHtml(gameEnvironment.market_source ?? "Unavailable")} · observed ${escapeHtml(gameEnvironment.market_observed_at ?? "Unavailable")}. ${escapeHtml(gameEnvironment.explanation)}</p>${qbFactors.length ? `<p>QB correlation reward factors: ${qbFactors.join(", ")}. These scale positive QB-linked bonuses without changing player projections.</p>` : ""}<table><thead><tr><th>Team</th><th>Players</th><th>Spread</th><th>Implied total</th><th>Selected mean</th><th>Selector contribution</th></tr></thead><tbody>${marketTeams.map((team) => `<tr><td>${escapeHtml(team.team)}</td><td>${number(team.players, 0)}</td><td>${team.spread == null ? "Unavailable" : number(team.spread)}</td><td>${team.implied_total == null ? "Unavailable" : number(team.implied_total)}</td><td>${number(team.projected_mean)}</td><td>${number(team.selector_contribution)}</td></tr>`).join("")}</tbody></table></details>` : "";
  const skipped = Array.isArray(selection.higher_ranked_skipped)
    ? selection.higher_ranked_skipped as ReportPlayer[] : [];
  const selectionHtml = selection.global_candidate_rank ? `<details open><summary>Portfolio selection cost</summary><p>Global candidate rank #${number(selection.global_candidate_rank, 0)} · mean loss ${number(selection.mean_loss)} · P90 loss ${number(selection.p90_loss)} · selector loss ${number(selection.selector_loss)} versus the respective best candidate. Scenario diversity selected a lower-ranked lineup: ${selection.scenario_diversity_changed_selection ? "yes" : "no"}.</p><details><summary>Higher-ranked candidates skipped (${skipped.length})</summary><p>${skipped.length ? skipped.map((row) => `#${number(row.rank, 0)}: ${escapeHtml(((row.blockers ?? []) as string[]).join(", "))}`).join("; ") : "None"}</p></details></details>` : "";
  const duplicationHtml = Object.keys(duplicationRisk).length ? `<details><summary>Showdown uniqueness signals</summary><p>Salary unused: $${number(duplicationRisk.salary_left_unused, 0)} · CPT ownership: ${number(duplicationRisk.captain_ownership)} · summed FLEX ownership: ${number(duplicationRisk.flex_ownership_sum)} · very-low-owned players (&lt;5%): ${number(duplicationRisk.very_low_owned_count, 0)}.</p><p>Slot ownership product: ${number(duplicationRisk.probability_product, 8)} · log product: ${number(duplicationRisk.log_probability, 3)}. ${escapeHtml(duplicationRisk.interpretation)} Structural commonness: ${duplicationRisk.structurally_common === "unavailable_without_field_lineup_model" ? "unavailable without a field lineup model" : escapeHtml(duplicationRisk.structurally_common)}.</p>${(duplicationRisk.missing_ownership_players as string[] | undefined)?.length ? `<p>Missing role ownership: ${escapeHtml((duplicationRisk.missing_ownership_players as string[]).join(", "))}.</p>` : ""}</details>` : "";
  const summaryParts = [
    `Salary: ${totalSalary.toLocaleString()}`,
    `Mean: ${number(totalMean)}`,
    `${ceilingSummary.label}: ${number(ceilingSummary.value)}`,
    `Context: ${context >= 0 ? "+" : ""}${number(context)}`,
    `Correlation: ${correlationAdjustment >= 0 ? "+" : ""}${number(correlationAdjustment)}`,
    stack ? `Stack: ${String(stack)}` : null,
    script ? `Lineup structure: ${String(script)}` : null,
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
    <td>${number(projection(player))}</td><td>${number(ceiling(player))}</td><td>${player.ownership == null ? "Unavailable" : number(player.ownership)}</td>
    <td>${escapeHtml(playerRules(player))}</td></tr>`).join("");
  const heading = first.lineup_variant === "long_shot" ? "Long-shot lineup" : `Lineup ${index + 1}`;
  return `<section class="lineup"><h2>${escapeHtml(heading)}</h2><div class="metrics">${summaryParts}</div>
    ${scenarioHtml}${gameEnvironmentHtml}${selectionHtml}${duplicationHtml}${controlComparisonHtml(first.lineup_control_comparison)}${rules}
    <table><thead><tr><th>Player</th><th>Slot · Pos</th><th>Team</th><th>Salary</th><th>Proj</th><th>P90</th><th>Ownership</th><th>Rules</th></tr></thead><tbody>${rows}</tbody></table></section>`;
}

function classicSmallFieldHtml(lineups: ReportPlayer[][]): string {
  const report = lineups[0]?.[0]?.classic_small_field_report as ReportPlayer | undefined;
  if (!report) return "";
  const contest = (report.contest ?? {}) as ReportPlayer;
  const economics = (contest.economics ?? {}) as ReportPlayer;
  const contestHtml = contest.contest_id ? `<h3>Classic contest context</h3><p>${escapeHtml(contest.name ?? contest.contest_id)} · $${number(contest.entry_fee, 2)} entry · ${number(contest.current_entries, 0)}/${number(contest.capacity, 0)} filled · maximum ${number(contest.maximum_entries, 0)} entries · ${number(Number(economics.paid_percentage) * 100, 1)}% paid · first-place share ${number(Number(economics.first_place_share) * 100, 1)}% · full-field rake ${number(Number(economics.full_field_rake) * 100, 1)}% · near-lock overlay ${economics.current_overlay == null ? "unavailable" : `$${number(economics.current_overlay, 2)}`} · missing: ${escapeHtml(((contest.unavailable_fields ?? []) as string[]).join(", ") || "none")}${contest.error ? ` · ${escapeHtml(contest.error)}` : ""}.</p><details><summary>Payout ladder</summary><table><thead><tr><th>Ranks</th><th>Prize</th></tr></thead><tbody>${((contest.payout_ladder ?? []) as ReportPlayer[]).map((tier) => `<tr><td>${number(tier.from, 0)}–${number(tier.to, 0)}</td><td>$${number(tier.cash, 2)}</td></tr>`).join("")}</tbody></table></details>` : "";
  const candidates = (report.top_20 ?? []) as ReportPlayer[];
  const qbs = (report.top_qbs ?? []) as ReportPlayer[];
  const families = (report.candidate_families ?? []) as ReportPlayer[];
  const stackTypes = (report.stack_types ?? {}) as Record<string, number>;
  const games = (report.primary_games_top_20 ?? {}) as Record<string, number>;
  const exposures = (report.player_exposures ?? {}) as Record<string, Record<string, number>>;
  const components = ["mean", "p90", "context", "leverage", "qb_stack", "bring_back", "game_environment", "correlation", "ownership_chalk", "duplication", "penalties", "other_residual"];
  const available = (value: unknown, digits = 2): string => value == null ? "Unavailable" : number(value, digits);
  const ownership = (report.ownership_evidence ?? {}) as ReportPlayer;
  const concentration = (report.concentration ?? []) as ReportPlayer[];
  const teams = (report.team_reconciliation ?? []) as ReportPlayer[];
  const teamHtml = teams.length ? `<h3>Offense opportunity reconciliation</h3><p>Pass and rush attempts are shown as Unavailable until independently forecast. Target and RB carry allocations are lagged proxies. Missing route and red-zone evidence remains Unavailable.</p><table><thead><tr><th>Team</th><th>Pass / rush attempts</th><th>Targets / RB carries proxy</th><th>Top measured roles</th><th>Target / carry / red-zone distribution</th><th>Role coverage / blockers</th></tr></thead><tbody>${teams.map((team) => {
    const top = (team.top_roles ?? []) as ReportPlayer[];
    const targets = (team.target_distribution ?? []) as ReportPlayer[];
    const carries = (team.carry_distribution ?? []) as ReportPlayer[];
    const red = (team.red_zone_distribution ?? []) as ReportPlayer[];
    const distribution = (rows: ReportPlayer[]) => rows.slice(0, 5).map((p) => `${p.name} ${available(p.value, 2)}`).join("; ") || "Unavailable";
    return `<tr><td>${escapeHtml(team.team)}</td><td>${available(team.expected_pass_attempts)} / ${available(team.expected_rush_attempts)}</td><td>${available(team.lagged_team_targets_proxy)} / ${available(team.lagged_rb_carries_proxy)}</td><td>${escapeHtml(top.map((p) => `${p.name} ${available(p.importance, 3)} ${p.role_class ?? "unknown"}`).join("; "))}</td><td>Targets: ${escapeHtml(distribution(targets))}<br>Carries: ${escapeHtml(distribution(carries))}<br>Red zone: ${escapeHtml(distribution(red))}</td><td>${number(Number(team.role_coverage) * 100, 1)}% · ${escapeHtml(((team.missing_role_players ?? []) as string[]).join(", ") || "none")}</td></tr>`;
  }).join("")}</tbody></table>` : "";
  const qbCoverage = (report.qb_family_coverage ?? []) as ReportPlayer[];
  let ownershipHtml = `<h3>Ownership evidence</h3><p>${escapeHtml(ownership.status ?? "unavailable")} · source ${escapeHtml(ownership.source ?? "unknown")} · covered ${available(ownership.covered_players, 0)}/${available(ownership.eligible_players, 0)} eligible players · ${escapeHtml(ownership.missing_reason ?? "complete coverage")}. Missing ownership is displayed as Unavailable; internal solver zero values are not ownership estimates.</p>`;
  const selectedSanity = (report.selected_football_sanity ?? []) as ReportPlayer[];
  if (selectedSanity.length) {
    ownershipHtml += `<h3>Selected lineup football sanity</h3><ol>${selectedSanity.map((item) => {
      const drivers = (item.driving_players ?? []) as ReportPlayer[];
      const cheap = (item.cheap_players ?? []) as ReportPlayer[];
      const omitted = (item.omitted_central_players ?? []) as ReportPlayer[];
      const conflicts = (item.role_projection_disagreements ?? []) as ReportPlayer[];
      const missingRole = (item.missing_role_evidence ?? []) as ReportPlayer[];
      return `<li>${escapeHtml(item.script ?? "Script unavailable")} · flags ${escapeHtml(((item.flags ?? []) as string[]).join(", ") || "none")}<br>Offensive drivers: ${escapeHtml(drivers.map((p) => `${p.name} (${p.team} ${p.position}, role ${available(p.importance, 3)})`).join("; ") || "role evidence unavailable")}<br>Cheap-player evidence: ${escapeHtml(cheap.map((p) => `${p.name}: ${p.evidence_class}; ${p.retention_reason}`).join("; ") || "none")}<br>Omitted central players: ${escapeHtml(omitted.map((p) => `${p.name}: ${p.explanation}; projection: ${p.projection_reason ?? "Unavailable"}; salary/value: ${p.salary_value_reason ?? "Unavailable"}; stack: ${p.stack_correlation_reason ?? "Unavailable"}; ownership: ${p.ownership_reason ?? "Unavailable"}`).join("; ") || "none with sufficient evidence")}<br>Role evidence blockers: ${escapeHtml(missingRole.map((p) => `${p.team} ${p.name}: ${((p.missing ?? []) as string[]).join(", ")}`).join("; ") || "none")}<br>Role/projection conflicts: ${escapeHtml(conflicts.map((p) => `${p.name}: role #${p.role_rank}, mean #${p.mean_rank}, P90 #${p.p90_rank}`).join("; ") || "none detected")}</li>`;
    }).join("")}</ol>`;
  }
  const roleExposure = (report.role_exposure ?? []) as ReportPlayer[];
  const roleSummary = (report.role_evidence_summary ?? {}) as ReportPlayer;
  if (roleSummary.eligible_skill_players != null) {
    ownershipHtml += `<p><strong>Football role coverage:</strong> ${available(roleSummary.measured_role_players, 0)}/${available(roleSummary.eligible_skill_players, 0)} eligible skill players have measured role scores. Missing players are listed by offense below.</p>`;
  }
  if (roleExposure.length) {
    ownershipHtml += `<h3>Offensive role versus lineup exposure</h3><p>Candidate and selected exposure describe this saved optimizer run. Role score is a football-usage diagnostic; salary, ownership, stacks, and portfolio constraints affect selection separately.</p><table><thead><tr><th>Player</th><th>Importance / role</th><th>Mean / P90</th><th>Salary / value</th><th>Ownership</th><th>Candidate exposure</th><th>Selected exposure</th><th>Sanity check</th></tr></thead><tbody>${roleExposure.map((row) => `<tr><td>${escapeHtml(row.name)} (${escapeHtml(row.team)} ${escapeHtml(row.position)})</td><td>${available(row.importance, 3)} / ${escapeHtml(row.role_class ?? "Unavailable")} (${escapeHtml(row.role_confidence ?? "Unavailable")})</td><td>${available(row.mean)} / ${available(row.p90)}</td><td>$${available(row.salary, 0)} / ${available(row.mean_per_1000_salary)}</td><td>${available(row.ownership)}</td><td>${available(row.candidate_count, 0)}/${available(report.candidate_count, 0)} (${number(Number(row.candidate_rate) * 100, 1)}%)</td><td>${available(row.selected_count, 0)}/${available(report.selected_count, 0)} (${number(Number(row.selected_rate) * 100, 1)}%)</td><td>${escapeHtml(row.sanity_flag ?? "—")}</td></tr>`).join("")}</tbody></table>`;
  }
  const selectedIds = new Set(lineups.flat().map((player) => String(player.player_id ?? "")));
  const counterfactualHtml = `<h3>Controlled role counterfactuals</h3><p>One role input varies at a time with all other model inputs fixed. Model means are before separate opportunity adjustments; production projections are unchanged.</p><table><thead><tr><th>Selected player</th><th>Baseline model mean</th><th>Importance scenarios: input → mean (delta)</th><th>Completeness scenarios: input → mean (delta)</th></tr></thead><tbody>${roleExposure.filter((row) => selectedIds.has(String(row.player_id ?? ""))).map((row) => {
    const grid = row.role_counterfactual as ReportPlayer | null;
    const scenarios = (key: string) => ((grid?.[key] ?? []) as ReportPlayer[]).map((item) => `${number(item.input, 2)} → ${number(item.model_mean, 2)} (${number(item.delta, 2)})`).join("; ") || "Unavailable for this projection run";
    return `<tr><td>${escapeHtml(row.name)}</td><td>${available(grid?.baseline_model_mean)}</td><td>${escapeHtml(scenarios("importance"))}</td><td>${escapeHtml(scenarios("completeness"))}</td></tr>`;
  }).join("")}</tbody></table>`;
  const anomalies = (report.role_projection_anomalies ?? []) as ReportPlayer[];
  const anomalyHtml = `<h3>High-role projection and exposure gaps</h3><p>Flags cover the full eligible pool. Inputs below are possible explanations, not causal attribution.</p><table><thead><tr><th>Player</th><th>Role / team ranks</th><th>Mean / P90</th><th>Salary / value rank</th><th>Candidate exposure</th><th>Context / volume</th></tr></thead><tbody>${anomalies.slice(0, 40).map((row) => {
    const drivers = (row.possible_drivers ?? {}) as ReportPlayer;
    const context = (drivers.matchup_context ?? {}) as ReportPlayer;
    const recent = (drivers.recent_volume ?? {}) as ReportPlayer;
    const volume = (drivers.allocated_volume_proxy ?? {}) as ReportPlayer;
    const efficiency = (drivers.recent_efficiency_proxy ?? {}) as ReportPlayer;
    return `<tr><td>${escapeHtml(row.name)} (${escapeHtml(row.team)})</td><td>${available(row.role_importance, 3)} ${escapeHtml(row.role_class)} · role #${available(row.team_role_rank, 0)}, mean #${available(row.team_mean_rank, 0)}, P90 #${available(row.team_p90_rank, 0)}</td><td>${available(row.mean)} / ${available(row.p90)}</td><td>$${available(row.salary, 0)} · #${available(row.position_value_rank, 0)}/${available(row.position_value_count, 0)}</td><td>${available(row.candidate_count, 0)}/${available(row.candidate_total, 0)}</td><td>Team total ${available(context.team_total)}; recent targets/carries ${available(recent.targets_mean_3)} / ${available(recent.carries_mean_3)}; allocated proxy ${available(volume.projected_targets)} / ${available(volume.projected_carries)}; recent fantasy-point proxy ${available(efficiency.player_roll3_mean)}; TD expectation separate: unavailable; ownership ${available(drivers.ownership)}; construction cause unisolated</td></tr>`;
  }).join("")}</tbody></table>`;
  const highRole = roleExposure.filter((row) => row.role_class === "offensive centerpiece" || row.role_class === "primary option");
  const opportunityValidationHtml = `<h3>High-role opportunity and trend validation</h3><p>Allocated opportunities are lagged proxies, not independent forward forecasts. Trend is last observed game minus the preceding three games.</p><table><thead><tr><th>Player</th><th>Recent → allocated target proxy</th><th>Recent → allocated carry proxy</th><th>Game / opportunity context</th><th>Snap / target / rush share trend</th></tr></thead><tbody>${highRole.map((row) => {
    const o = (row.opportunity_validation ?? {}) as ReportPlayer;
    const t = (row.role_trend ?? {}) as ReportPlayer;
    const game = (o.point_model_context ?? {}) as ReportPlayer;
    const trend = (value: unknown) => value == null ? "Unavailable" : `${number(value, 3)} ${Number(value) > 0 ? "increasing" : Number(value) < 0 ? "decreasing" : "flat"}`;
    return `<tr><td>${escapeHtml(row.name)}</td><td>${available(o.recent_targets_mean_3)} → ${available(o.projected_targets_proxy)} (delta ${available(o.targets_proxy_minus_recent)})</td><td>${available(o.recent_carries_mean_3)} → ${available(o.projected_carries_proxy)} (delta ${available(o.carries_proxy_minus_recent)})</td><td>Point model: total ${available(game.game_total)}, spread ${available(game.team_spread)}, team implied ${available(game.team_implied_total)} (separate effect unavailable); opportunity counts: ${o.context_adjusted ? "pregame-adjusted" : "no measured adjustment"}</td><td>${trend(t.snap_share_trend)} / ${trend(t.target_share_trend)} / ${trend(t.rush_share_trend)}</td></tr>`;
  }).join("")}</tbody></table>`;
  const calibration = (report.historical_role_calibration ?? {}) as ReportPlayer;
  const calibrationRows = (calibration.by_position_and_role_class ?? {}) as Record<string, ReportPlayer>;
  const calibrationClasses = (calibration.by_role_class ?? {}) as Record<string, ReportPlayer>;
  const calibrationClassHtml = Object.keys(calibrationClasses).length ? `<h4>All positions by role class</h4><table><thead><tr><th>Role class</th><th>Rows</th><th>Actual mean</th><th>Mean error</th><th>MAE / RMSE</th><th>Ceiling hit / evaluable rows</th></tr></thead><tbody>${Object.entries(calibrationClasses).map(([key, row]) => `<tr><td>${escapeHtml(key)}</td><td>${available(row.rows, 0)}</td><td>${available(row.mean_fantasy_points)}</td><td>${available(row.mean_projection_error_predicted_minus_actual)}</td><td>${available(row.mae)} / ${available(row.rmse)}</td><td>${available(row.ceiling_hit_rate == null ? null : Number(row.ceiling_hit_rate) * 100, 1)}% / ${available(row.ceiling_evaluable_rows, 0)}</td></tr>`).join("")}</tbody></table>` : "";
  const calibrationHtml = `<h3>Historical role calibration</h3><p>${escapeHtml(calibration.method ?? calibration.reason ?? "Unavailable")}. ${escapeHtml(calibration.ceiling_note ?? "")}</p>${calibrationClassHtml}${Object.keys(calibrationRows).length ? `<table><thead><tr><th>Position / role</th><th>Rows</th><th>Actual mean</th><th>Mean error (predicted − actual)</th><th>MAE / RMSE</th><th>Ceiling hit / evaluable rows</th></tr></thead><tbody>${Object.entries(calibrationRows).map(([key, row]) => `<tr><td>${escapeHtml(key)}</td><td>${available(row.rows, 0)}</td><td>${available(row.mean_fantasy_points)}</td><td>${available(row.mean_projection_error_predicted_minus_actual)}</td><td>${available(row.mae)} / ${available(row.rmse)}</td><td>${available(row.ceiling_hit_rate == null ? null : Number(row.ceiling_hit_rate) * 100, 1)}% / ${available(row.ceiling_evaluable_rows, 0)}</td></tr>`).join("")}</tbody></table>` : "<p>Unavailable for this saved projection.</p>"}`;
  const opportunity = (report.opportunity_gate ?? {}) as ReportPlayer;
  const opportunityClasses = (opportunity.candidate_low_cost_skill_evidence ?? {}) as Record<string, number>;
  const opportunityHtml = `<h3>Opportunity gate evidence</h3><p>${escapeHtml(opportunity.evaluated_stage ?? "Stage unavailable")} · surviving pool ${available(opportunity.surviving_pool_size, 0)} · ${escapeHtml(opportunity.retention_rule ?? "Rule unavailable")}. Candidate appearance counts by evidence class: ${escapeHtml(Object.entries(opportunityClasses).map(([key, value]) => `${key} ${value}`).join(" · ") || "Unavailable")}.</p>`;
  const concentrationHtml = `<h3>Candidate concentration</h3><p>Frequency reflects the generated pool. Counts for salary dominance, stack boundaries, and correlation overlap; they do not sum to a causal attribution. Candidate generation cap: 100%.</p><table><thead><tr><th>Player</th><th>Frequency</th><th>Salary</th><th>Mean / P90 / P90 per $1k</th><th>Position ranks: mean / P90 / value</th><th>Role</th><th>Ownership</th><th>At stack minimum</th><th>Correlation rule</th><th>No comparable salary swap</th></tr></thead><tbody>${concentration.map((row) => `<tr><td>${escapeHtml(row.name)} (${escapeHtml(row.position)})</td><td>${available(row.frequency, 0)}/${available(report.candidate_count, 0)}</td><td>$${available(row.salary, 0)}</td><td>${available(row.mean)} / ${available(row.p90)} / ${available(row.p90_per_1k)}</td><td>${available(row.mean_rank, 0)} / ${available(row.p90_rank, 0)} / ${available(row.value_rank, 0)}</td><td>${available(row.role_importance, 3)} ${escapeHtml(row.role_class ?? "Unavailable")}</td><td>${available(row.ownership)}</td><td>${available(row.template_boundary_count, 0)}</td><td>${available(row.correlation_rule_count, 0)}</td><td>${available(row.no_comparable_swap_count, 0)}</td></tr>`).join("")}</tbody></table>`;
  const qbCoverageHtml = `<h3>Top 10 QB family coverage</h3>${qbCoverage.length ? `<table><thead><tr><th>QB</th><th>Salary / mean / P90 / value</th><th>Rushing</th><th>Best exact stack families</th></tr></thead><tbody>${qbCoverage.map((row) => `<tr><td>${escapeHtml(row.qb)}</td><td>$${available(row.salary, 0)} / ${available(row.mean)} / ${available(row.p90)} / ${available(row.p90_per_1k)}</td><td>${escapeHtml(((row.rushing ?? {}) as ReportPlayer).label)}</td><td>${((row.families ?? []) as ReportPlayer[]).map((family) => `${escapeHtml(family.family)}: ${available(family.score, 3)} (${escapeHtml(family.reason)})`).join("<br>")}</td></tr>`).join("")}</tbody></table>` : `<p>Not computed in this run. Exact QB family diagnostics are enabled by default for new Classic small-field runs; this saved run may have disabled them.</p>`}`;
  const candidateRows = candidates.map((row) => {
    const roster = (row.roster ?? []) as ReportPlayer[];
    const qb = (row.qb ?? {}) as ReportPlayer;
    const stack = (row.stack ?? {}) as ReportPlayer;
    const game = (row.game_environment ?? {}) as ReportPlayer;
    const parts = (row.components ?? {}) as ReportPlayer;
    const componentStatuses = (row.component_statuses ?? {}) as Record<string, ReportPlayer>;
    const bringBacks = (stack.bring_backs ?? []) as ReportPlayer[];
    const cheap = (row.cheap_skill_opportunity ?? []) as ReportPlayer[];
    const rbs = (row.rbs ?? []) as ReportPlayer[];
    const catchers = (row.pass_catchers ?? {}) as ReportPlayer;
    const rules = (row.correlation_rules ?? []) as ReportPlayer[];
    const football = (row.football_sanity ?? {}) as ReportPlayer;
    const drivers = (football.driving_players ?? []) as ReportPlayer[];
    const missingCentral = (football.omitted_central_players ?? []) as ReportPlayer[];
    const roleConflicts = (football.role_projection_disagreements ?? []) as ReportPlayer[];
    const cheapEvidence = (football.cheap_players ?? []) as ReportPlayer[];
    const bringBackDetails = ((stack.bring_back_evaluations ?? []) as ReportPlayer[]).map((item) => `${item.name}: ${item.game}; total ${available(item.game_total, 1)}, spread ${available(item.team_spread, 1)}; ${item.rule_id}; fired ${item.rule_fired}; raw ${available(item.raw_rule_value, 3)}; selector ${available(item.selector_contribution, 3)}; ${item.reason}`).join("; ");
    const rbDetails = rbs.map((item) => { const role = (item.receiving_role_diagnostic ?? {}) as ReportPlayer; return `${item.name}: targets ${available(role.expected_targets)} (recent ${available(role.recent_targets_mean_3)}), share ${available(role.target_share, 3)}, routes ${available(role.expected_routes)}, receptions ${available(role.receptions_mean_3)}, receiving yards ${available(role.receiving_yards_mean_3)}, receiving fantasy points ${available(role.receiving_fantasy_points)}, role strength ${available(role.strength, 3)} from ${role.source ?? "unavailable"}`; }).join("; ");
    const decomposition = components.map((key) => {
      const component = componentStatuses[key];
      return `${key}: ${component ? `${component.status}${component.value == null ? "" : ` ${number(component.value, 3)}`}${component.reason ? ` (${component.reason})` : ""}` : `${number(parts[key], 3)}${["ownership_chalk", "duplication"].includes(key) ? " inactive as soft term" : ""}`}`;
    }).join(" · ");
    return `<tr><td>#${number(row.rank, 0)}</td><td>${escapeHtml(roster.map((p) => `${p.position} ${p.name}`).join(" / "))}</td><td>$${number(row.salary, 0)}</td><td>${number(row.mean)} / ${number(row.p90)}</td><td>${row.relative_chalk == null ? "Ownership unavailable" : `${number(row.ownership_sum, 1)} sum / ${number(row.relative_chalk, 1)} chalk`}</td><td>${escapeHtml(qb.name)}<br>${escapeHtml(qb.label)} (${escapeHtml(qb.basis)})</td><td>${escapeHtml(stack.type)}<br>${escapeHtml(bringBacks.map((p) => p.name).join(", ") || "No bring-back")}<br>${number(stack.game_stack_size, 0)} players / $${number(stack.game_stack_salary, 0)} / ${available(stack.game_stack_ownership, 1)}% stack ownership<br>bring-back correlation ${number(stack.bring_back_correlation_contribution, 3)}</td><td>${escapeHtml(row.primary_game)}<br>${escapeHtml(game.label)} / ${available(game.game_total, 1)} total<br>team total ${available(game.team_total, 1)} / spread ${available(game.team_spread, 1)} / raw ${available(game.raw_rule_score, 3)} / selector ${available(game.selector_contribution, 3)}<br>${escapeHtml(game.reason)}<br>games ${escapeHtml(((row.games_represented ?? []) as string[]).join(", "))}</td><td>${number(row.correlation_positive, 3)} / ${number(row.correlation_negative, 3)}</td><td>${number(row.objective_score, 3)}</td><td><details><summary>Inspect</summary><p><strong>Football sanity:</strong> ${escapeHtml(football.script ?? "Unavailable")}. Drivers: ${escapeHtml(drivers.map((p) => `${p.name} (${p.team} ${p.position}; role ${available(p.importance, 3)} ${p.role_class ?? "unknown"})`).join("; ") || "role evidence unavailable")}.</p><p><strong>Cheap player support:</strong> ${escapeHtml(cheapEvidence.map((p) => `${p.name}: ${p.evidence_class}; ${p.retention_reason}`).join("; ") || "no cheap skill player")}.</p><p><strong>Omitted central players:</strong> ${escapeHtml(missingCentral.map((p) => `${p.name} (${p.team}): ${p.explanation}; mean ${available(p.mean)}, P90 ${available(p.p90)}, salary $${available(p.salary, 0)}, candidate ${p.candidate_count}/${p.candidate_total}, selected ${p.selected_count}/${p.selected_total}`).join("; ") || "none with measured medium/high-confidence central role on represented offenses")}.</p><p><strong>Role/model disagreements:</strong> ${escapeHtml(roleConflicts.map((p) => `${p.name} (${p.team}): role rank ${p.role_rank}, mean rank ${p.mean_rank}, P90 rank ${p.p90_rank}`).join("; ") || "none detected with sufficient role evidence")}.</p><p><strong>Objective:</strong> ${escapeHtml(decomposition)} · base solver ${number(row.base_solver, 3)} · final selector ${number(row.objective_score, 3)}.</p><p>Mean loss ${number(row.mean_loss_vs_best)}; P90 loss ${number(row.p90_loss_vs_best)}; chalk improvement ${available(row.chalk_improvement_vs_best_quality, 1)}; ownership objective gain ${number(row.ownership_objective_gain_vs_best_quality, 3)}${row.large_ceiling_sacrifice_for_chalk ? "; ceiling sacrifice and chalk improvement flag" : ""}.</p><p><strong>Bring-back rule:</strong> ${escapeHtml(bringBackDetails || "No structural bring-back")}</p><p><strong>RB receiving evidence:</strong> ${escapeHtml(rbDetails || "No RBs")}</p><p><strong>RBs:</strong> ${escapeHtml(rbs.map((p) => `${p.name} $${p.salary} / ${number(p.projection)} / ${number(p.p90)} / ${available(p.ownership)}% · RB+DST ${p.same_team_dst} · opposing DST ${p.opposing_dst} · QB game ${p.in_qb_game} · receiving role ${available(p.receiving_role_strength, 2)}`).join("; "))}</p><p><strong>WR/TE:</strong> $${number(catchers.salary, 0)} total · ${available(catchers.high_owned_count, 0)} high owned · ${available(catchers.low_owned_count, 0)} low owned · one-offs ${escapeHtml(((catchers.one_offs ?? []) as string[]).join(", ") || "none")} · TE stacked ${escapeHtml(catchers.te_in_qb_stack)} · FLEX ${escapeHtml(catchers.flex_position)}</p><p><strong>Cheap skill roles:</strong> ${escapeHtml(cheap.map((p) => `${p.name}: active ${p.pregame_availability_probability ?? "unknown"}, role ${p.pregame_role_label ?? "unknown"}, snaps ${p.pregame_expected_snaps ?? "unknown"}, routes ${p.pregame_expected_routes ?? "unknown"}, carries ${p.pregame_expected_carries ?? "unknown"}, targets ${p.pregame_expected_targets ?? "unknown"}, roster ${p.roster_status ?? "unknown"}, depth ${p.depth_chart_position ?? "unknown"}, explicit role ${p.explicit_role_signal ?? "unknown"}, recent targets ${p.targets_mean_3 ?? "Unavailable"}, recent snap share ${p.snap_share_mean_3 ?? "Unavailable"}, evidence ${p.evidence_class ?? "insufficient_role_data"}, retention ${p.retention_reason ?? "unknown"}`).join("; ") || "none")}</p><p><strong>Correlation terms:</strong> ${escapeHtml(rules.map((r) => `${r.reason_code}: ${number(r.objective_contribution, 3)}`).join("; ") || "none")}</p></details></td></tr>`;
  }).join("");
  const exposureTable = (["top_20", "top_50", "entire_pool"] as const).map((scope) => `<details><summary>Player exposure · ${scope.replaceAll("_", " ")}</summary><p>${Object.entries(exposures[scope] ?? {}).slice(0, 40).map(([name, count]) => `${escapeHtml(name)} ${number(count, 0)}`).join(" · ")}</p></details>`).join("");
  const rbDst = (report.rb_dst_diagnostics ?? {}) as ReportPlayer;
  const rbWhy = (rbDst.player_why ?? []) as ReportPlayer[];
  const allCandidates = (report.all_candidates ?? []) as ReportPlayer[];
  const selectedRanks = (report.selected_ranks ?? []) as number[];
  const alignment = (report.strategy_policy_alignment ?? {}) as ReportPlayer;
  const policyHtml = alignment.applied_profile_id
    ? `<h3>Strategy and applied policy</h3><p><strong>Requested:</strong> ${escapeHtml(alignment.requested_strategy)} · <strong>Applied correlation policy:</strong> ${escapeHtml(alignment.applied_profile_id)} · ${escapeHtml(alignment.status)}. ${escapeHtml(alignment.warning ?? "")}</p>`
    : "";
  const portfolio = (report.selected_portfolio ?? {}) as ReportPlayer;
  const portfolioLineups = (portfolio.lineups ?? []) as ReportPlayer[];
  const portfolioPlayers = (portfolio.player_exposure ?? []) as ReportPlayer[];
  const portfolioGames = (portfolio.game_exposure ?? []) as ReportPlayer[];
  const primaryGames = (portfolio.primary_game_exposure ?? []) as ReportPlayer[];
  const overlap = (portfolio.overlap_matrix ?? []) as number[][];
  const portfolioHtml = portfolioLineups.length ? `<h3>Selected portfolio paths</h3><p>Constraints: ${escapeHtml(JSON.stringify(portfolio.constraints ?? {}))} · Core players: ${escapeHtml(((portfolio.core_players ?? []) as string[]).join(", ") || "none")}. Projected score and ceiling are player sums; leverage is a proxy, not payout EV.</p><table><thead><tr><th>Lineup</th><th>QB path</th><th>Construction</th><th>Projected / ceiling</th><th>Ownership / leverage</th><th>Unique players</th><th>Why included</th></tr></thead><tbody>${portfolioLineups.map((row) => `<tr><td>${number(row.lineup, 0)}</td><td>${escapeHtml(row.qb)} · ${escapeHtml(row.primary_game)}</td><td>${escapeHtml(row.construction_archetype)}</td><td>${number(row.projected_score)} / ${number(row.ceiling_proxy)}</td><td>${available(row.projected_ownership_sum, 1)} / ${available(row.leverage_proxy, 2)}</td><td>${escapeHtml(((row.unique_players ?? []) as ReportPlayer[]).map((p) => p.name).join(", ") || "none")}</td><td>${escapeHtml(row.selection_reason)}</td></tr>`).join("")}</tbody></table><p><strong>Player exposure:</strong> ${escapeHtml(portfolioPlayers.map((p) => `${p.name} ${number(p.percent, 0)}%`).join(" · "))}</p><p><strong>Primary QB game exposure:</strong> ${escapeHtml(primaryGames.map((g) => `${g.game} ${number(g.percent, 0)}%`).join(" · ") || "unavailable")}</p><p><strong>Any-player game exposure:</strong> ${escapeHtml(portfolioGames.map((g) => `${g.game_id} ${number(g.percent, 0)}%`).join(" · ") || "unavailable")}</p><p><strong>Lineup overlap matrix:</strong> ${escapeHtml(overlap.map((row) => row.join(" / ")).join("; "))}</p>` : "";
  const prospective = (report.prospective_experiment ?? {}) as ReportPlayer;
  const availability = (prospective.availability_risk ?? {}) as ReportPlayer;
  const riskPlayers = (availability.players ?? []) as ReportPlayer[];
  const generationShadow = (prospective.shadow_generation ?? {}) as ReportPlayer;
  const riskTradeoff = (generationShadow.risk_policy_tradeoff ?? {}) as ReportPlayer;
  const overlapShadow = (prospective.shadow_portfolio ?? {}) as ReportPlayer;
  const riskHtml = prospective.contract ? `<section><h3>Availability risk</h3><p>Pregame classification only. Questionable players without timestamped full-practice and unrestricted-workload evidence use the elevated-risk bucket. The saved shadow is a structural comparison; production controls and their admission funnel appear above.</p><p><strong>Projected points sacrificed due to availability-risk controls:</strong> ${available(riskTradeoff.mean_points_sacrificed)} · <strong>Projected ceiling sacrificed due to availability-risk controls:</strong> ${available(riskTradeoff.ceiling_points_sacrificed)}. ${escapeHtml(riskTradeoff.comparison ?? "")}</p><table><thead><tr><th>Player</th><th>Designation / evidence</th><th>Practice / workload</th><th>Risk bucket</th><th>Shadow candidate / selected</th><th>Caps</th><th>Binding</th></tr></thead><tbody>${riskPlayers.map((row) => `<tr><td>${escapeHtml(row.player)}</td><td>${escapeHtml(row.designation ?? "Unavailable")} · ${escapeHtml(row.evidence_timestamp ?? "timestamp unavailable")}</td><td>${escapeHtml(row.practice_status ?? "Unavailable")} (trend ${escapeHtml(row.practice_trend ?? "Unavailable")}) @ ${escapeHtml(row.practice_observed_at ?? "timestamp unavailable")} / ${escapeHtml(row.workload_status ?? "Unavailable")} @ ${escapeHtml(row.workload_observed_at ?? "timestamp unavailable")} · ${escapeHtml(row.workload_confidence)}</td><td>${escapeHtml(row.bucket)}</td><td>${number(row.candidate_exposure, 1)}% / ${number(row.selected_exposure, 1)}%</td><td>${row.candidate_cap == null ? "—" : `${number(Number(row.candidate_cap) * 100, 0)}%`} / ${row.selected_cap == null ? "—" : `${number(Number(row.selected_cap) * 100, 0)}%`}</td><td>${row.candidate_cap_binding ? "Candidate cap" : ""}${row.selected_cap_binding ? `${row.candidate_cap_binding ? ", " : ""}selected cap` : ""}${!row.candidate_cap_binding && !row.selected_cap_binding ? "No" : ""}${row.override ? ` · override: ${escapeHtml((row.override as ReportPlayer).reason)}` : ""}</td></tr>`).join("")}</tbody></table><p>Questionable-player exposure: production candidates ${escapeHtml(JSON.stringify((availability.production_candidate ?? {}) && ((availability.production_candidate as ReportPlayer).pct_with_at_least ?? {})))}; structural shadow candidates ${escapeHtml(JSON.stringify((availability.shadow_candidate ?? {}) && ((availability.shadow_candidate as ReportPlayer).pct_with_at_least ?? {})))}; structural selected ${escapeHtml(JSON.stringify((availability.shadow_selected ?? {}) && ((availability.shadow_selected as ReportPlayer).pct_with_at_least ?? {})))}. Counts are percentages with at least 1, 2, or 3 questionable players.</p><h3>Prospective shadows · frozen before lock</h3><p>Frozen input SHA-256: ${escapeHtml(prospective.frozen_snapshot_sha256)}. Structural shadow: ${number(generationShadow.candidate_target, 0)} target, ${number(generationShadow.candidate_underfill, 0)} underfill, selected ranks ${escapeHtml(((generationShadow.selected_ranks ?? []) as number[]).join(", ") || "infeasible")}. Original-pool overlap≤6 shadow: ranks ${escapeHtml(((overlapShadow.selected_ranks ?? []) as number[]).join(", ") || "infeasible")}; no distinct-QB rule.</p></section>` : prospective.status ? `<section><h3>Availability risk and prospective shadows</h3><p>Unavailable: ${escapeHtml(prospective.reason ?? prospective.status)}. Frozen input SHA-256: ${escapeHtml(prospective.frozen_snapshot_sha256)}.</p></section>` : "";
  const production = (report.production_controls ?? {}) as ReportPlayer;
  const admission = (report.production_funnel ?? {}) as ReportPlayer;
  const tradeoffs = (production.selection_tradeoffs ?? {}) as ReportPlayer;
  const nonadmittedLabel = admission.admission_method === "joint_max_count_then_selector_score"
    ? "not admitted after joint cap/target selection" : "player-cap rejected";
  const productionHtml = production.mode ? `<section><h3>Production controls</h3><p>Availability mode ${escapeHtml(production.mode)} · candidate admission ${escapeHtml(admission.status ?? "Unavailable")} · requested ${number(admission.requested, 0)}, solved ${number(admission.solved, 0)}, legal ${number(admission.legal, 0)}, duplicate ${number(admission.duplicate ?? 0, 0)}, quality rejected ${number(admission.rejected_by_quality ?? 0, 0)}, ${nonadmittedLabel} ${number(admission.rejected_by_player_cap ?? 0, 0)}, injury-cap rejected ${number(admission.rejected_by_injury_cap ?? 0, 0)}, family constrained ${number(admission.rejected_by_family_constraint ?? 0, 0)}, accepted ${number(admission.accepted, 0)}, deficit ${number(admission.remaining_deficit, 0)}.</p><p>Quality tolerance per lineup ${available(tradeoffs.quality_loss_tolerance_per_lineup, 2)} selector points · alternative stack-family selector cost ${available(tradeoffs.alternative_stack_family_selector_cost, 3)} · selected stack families ${available(tradeoffs.selected_stack_family_count, 0)}. QB path frontier: ${escapeHtml(JSON.stringify(tradeoffs.path_frontier ?? {}))}</p></section>` : "";
  const coverage = (report.pregame_coverage ?? {}) as ReportPlayer;
  const coverageQbs = (coverage.qb ?? []) as ReportPlayer[];
  const coverageGames = (coverage.games ?? []) as ReportPlayer[];
  const coveragePlayers = (coverage.players ?? []) as ReportPlayer[];
  const diversity = (coverage.diversity ?? {}) as ReportPlayer;
  const funnel = (report.generation_funnel ?? {}) as ReportPlayer;
  const lowCoverageCeilings = coveragePlayers.filter((row) => Number(row.p90_percentile) >= 95 && Number(row.candidate_pct) < 5).slice(0, 20);
  const coverageHtml = coverageQbs.length ? `<details><summary>Pregame candidate coverage and generation funnel</summary><p>Distinct rosters ${number(diversity.unique_roster_count, 0)}/${number(diversity.candidate_count, 0)} · average pairwise overlap ${number(diversity.average_pairwise_overlap, 2)} of 9 · effective QB/game/stack families ${number(diversity.effective_family_count, 1)}. Eligible player pool ${number(funnel.eligible_player_pool, 0)} → sequential ${number(funnel.sequential_unique, 0)} → saved ${number(funnel.saved_candidates, 0)} → selected ${number(funnel.selected, 0)}. Theoretical legal roster count is unavailable.</p><p><strong>Stack families:</strong> ${escapeHtml(Object.entries((coverage.stack_families ?? {}) as Record<string, number>).map(([key, count]) => `${key} ${count}`).join(" · "))}</p><table><thead><tr><th>QB</th><th>Saved mean / P90</th><th>Ownership</th><th>Game total / team total</th><th>Generated / selected</th><th>Families</th></tr></thead><tbody>${coverageQbs.map((row) => `<tr><td>${escapeHtml(row.name)}</td><td>${available(row.mean)} / ${available(row.p90)}</td><td>${available(row.ownership)}%</td><td>${available(row.game_total)} / ${available(row.team_total)}</td><td>${number(row.candidate_count, 0)} / ${number(row.selected_count, 0)}</td><td>${escapeHtml(Object.entries((row.families ?? {}) as Record<string, number>).map(([key, count]) => `${key} ${count}`).join(" · "))}</td></tr>`).join("")}</tbody></table><p><strong>Game exposure:</strong> ${escapeHtml(coverageGames.map((row) => `${row.game}: QB ${row.qb ?? 0}, catchers ${row.pass_catcher ?? 0}, bring-back ${row.bring_back ?? 0}, RB ${row.rb ?? 0}, DST ${row.dst ?? 0}`).join(" · "))}</p><p><strong>High-P90 players below 5% candidate exposure:</strong> ${escapeHtml(lowCoverageCeilings.map((row) => `${row.name} ${row.candidate_count}/${coverage.candidate_count ?? report.candidate_count}`).join(" · ") || "none")}. These are pregame coverage signals, not forced plays.</p></details>` : "";
  const omittedP90 = (report.highest_p90_candidates_omitted ?? []) as ReportPlayer[];
  const omittedP90Html = omittedP90.length ? `<details><summary>Highest summed-P90 candidates omitted from selection</summary><p>${escapeHtml(omittedP90.map((row) => `#${row.rank} ${row.qb} ${row.stack_family}: mean ${number(row.mean)}, summed P90 ${number(row.p90)}, selector ${number(row.objective_score, 3)}`).join(" · "))}</p><p><strong>Bring-back counts, candidates / selected:</strong> ${escapeHtml(Object.entries((coverage.bring_back_distribution ?? {}) as Record<string, number>).map(([count, total]) => `${count}: ${total}/${((coverage.selected_bring_back_distribution ?? {}) as Record<string, number>)[count] ?? 0}`).join(" · "))}</p></details>` : "";
  const flagExposure = (rbDst.selected_flag_exposure ?? []) as ReportPlayer[];
  const rbWhyHtml = rbWhy.length ? `<details open><summary>Player why · RB projection and role</summary><p>Role counterfactuals vary one saved feature at a time; they are not causal effects. Same-slate external benchmark data is shown only when captured with the run.</p><div style="overflow-x:auto"><table><thead><tr><th>RB</th><th>Salary</th><th>Mean / P90</th><th>Role</th><th>Recent snaps / carries / targets / target share</th><th>Receiving strength</th><th>Team total / spread / game total</th><th>Model / explanation</th><th>External benchmark</th></tr></thead><tbody>${rbWhy.map((row) => { const grid = (row.model_explanation ?? {}) as ReportPlayer; const importance = (grid.importance ?? []) as ReportPlayer[]; const deltas = importance.map((item) => Number(item.delta)).filter(Number.isFinite); const effect = deltas.length ? `${number(Math.min(...deltas), 2)} to ${number(Math.max(...deltas), 2)} across saved role-importance probes` : "Unavailable"; const benchmark = (row.external_benchmark ?? {}) as ReportPlayer; return `<tr><td>${escapeHtml(row.name)} (${escapeHtml(row.team)})</td><td>$${number(row.salary, 0)}</td><td>${number(row.mean)} / ${number(row.p90)}</td><td>${escapeHtml(row.role_class)}</td><td>${available(row.snap_share_mean_3, 3)} / ${available(row.carries_mean_3)} / ${available(row.targets_mean_3)} / ${available(row.target_share_mean_3, 3)}</td><td>${available(row.receiving_role_strength, 3)}</td><td>${available(row.team_implied_total)} / ${available(row.spread)} / ${available(row.game_total)}</td><td>${escapeHtml(row.model_version ?? "Unavailable")} · ${escapeHtml(effect)}<br>${escapeHtml(row.explanation_limit)}</td><td>${escapeHtml(benchmark.reason ?? benchmark.status ?? "Unavailable")}</td></tr>`; }).join("")}</tbody></table></div></details>` : "";
  const flagRows: ReportPlayer[] = allCandidates.filter((row) => selectedRanks.includes(Number(row.rank))).flatMap((row) => ((row.rb_dst_football_sanity_flags ?? []) as ReportPlayer[]).map((flag): ReportPlayer => ({ rank: row.rank, ...flag })));
  const flagsHtml = rbDst.warning_only ? `<details open><summary>Lineup football sanity · warning only</summary><p>These flags do not change scores or eligibility. Avoidance costs compare with the strongest saved candidate without the flagged construction.</p>${flagRows.length ? `<table><thead><tr><th>Lineup</th><th>Flag</th><th>Why</th><th>Status</th><th>Strongest alternative / quality cost</th></tr></thead><tbody>${flagRows.map((flag) => { const alternative = (flag.strongest_candidate_without_flag ?? {}) as ReportPlayer; return `<tr><td>#${number(flag.rank, 0)}</td><td>${escapeHtml(flag.label)}</td><td>${escapeHtml(flag.why)}${flag.kind === "same_team_rb_dst" ? `<br>Recent carries ${available(flag.recent_carries)}; targets ${available(flag.recent_targets)}; receiving strength ${available(flag.receiving_role_strength, 3)}` : ""}</td><td>${escapeHtml(flag.status)} · ${flag.production_impacting ? "production impacting" : "no production impact"}</td><td>${alternative.rank == null ? "Unavailable" : `#${number(alternative.rank, 0)} · mean cost ${number(alternative.mean_cost)} · P90 cost ${number(alternative.p90_cost)} · selector cost ${number(alternative.selector_cost, 3)}`}</td></tr>`; }).join("")}</tbody></table>` : "<p>No selected lineup triggered a flag.</p>"}</details><details><summary>Portfolio flagged-construction exposure</summary><p>${flagExposure.map((item) => `${escapeHtml(item.key)} ${number(item.appearances, 0)}/${number(item.selected_count, 0)}`).join(" · ") || "No selected flagged constructions."}</p></details>` : "";
  return `<section class="lineup"><h2>Classic small-field GPP diagnostic baseline</h2><p>${number(report.candidate_count, 0)} legal candidates generated; target ${number(report.requested_candidate_count, 0)}. Globally selected ranks ${escapeHtml(((report.selected_ranks ?? []) as number[]).join(", "))}. ${escapeHtml(report.note)} P90 here is the sum of individual player ceilings, not a simulated lineup percentile.</p>${policyHtml}${productionHtml}${riskHtml}${portfolioHtml}${coverageHtml}${omittedP90Html}${report.candidate_pool_warning ? `<p><strong>Candidate pool warning:</strong> ${escapeHtml(report.candidate_pool_warning)}</p>` : ""}${contestHtml}${ownershipHtml}${counterfactualHtml}${anomalyHtml}${opportunityValidationHtml}${calibrationHtml}${teamHtml}${opportunityHtml}${concentrationHtml}${qbCoverageHtml}${rbWhyHtml}${flagsHtml}<h3>Top QBs</h3><table><thead><tr><th>QB</th><th>Frequency</th><th>Average score</th><th>Best score</th></tr></thead><tbody>${qbs.map((row) => `<tr><td>${escapeHtml(row.qb)}</td><td>${number(row.candidate_frequency, 0)}</td><td>${number(row.average_score, 3)}</td><td>${number(row.best_score, 3)}</td></tr>`).join("")}</tbody></table><p><strong>Stack types:</strong> ${escapeHtml(Object.entries(stackTypes).map(([key, value]) => `${key} ${value}`).join(" · "))}</p><p><strong>Primary games, top 20:</strong> ${escapeHtml(Object.entries(games).map(([key, value]) => `${key} ${value}`).join(" · "))}</p><h3>Top 20 candidates and objective decomposition</h3><div style="overflow-x:auto"><table><thead><tr><th>Rank</th><th>Roster</th><th>Salary</th><th>Mean / P90</th><th>Ownership</th><th>QB</th><th>Stack</th><th>Game</th><th>Positive / negative correlation</th><th>Selector</th><th>Details</th></tr></thead><tbody>${candidateRows}</tbody></table></div><h3>Candidate families</h3><ul>${families.map((row) => `<li>${escapeHtml(row.qb)}: ${escapeHtml(((row.best_by_stack ?? []) as (number | null)[]).map((rank, index) => `${["QB+1", "QB+2", "QB+2+bring-back", "QB+3"][index]} #${rank ?? "unavailable"}`).join(" · "))}</li>`).join("")}</ul>${exposureTable}</section>`;
}

function historicalCaptainHtml(lineups: ReportPlayer[][]): string {
  const report = (lineups[0]?.[0]?.historical_captain_optimality ?? {}) as ReportPlayer;
  if (!report.slate_count) return report.status ? `<section class="lineup"><h2>Historical Captain Optimality</h2><p>${escapeHtml(report.status)}: ${escapeHtml(report.reason)}</p></section>` : "";
  const percent = (value: unknown): string => value == null ? "Unavailable" : `${number(Number(value) * 100, 1)}%`;
  const rateRows = (value: unknown): ReportPlayer[] => Array.isArray(value) ? value as ReportPlayer[] : [];
  const positions = rateRows(report.positions);
  const archetypes = rateRows(report.qb_archetypes);
  const starterArchetypes = rateRows(report.starter_qb_archetypes);
  const buckets = (report.qb_buckets ?? {}) as ReportPlayer;
  const starterBuckets = (report.starter_qb_buckets ?? {}) as ReportPlayer;
  const starterGameShares = rateRows(report.starter_qb_game_shares);
  const starterIdentification = (report.starter_identification ?? {}) as ReportPlayer;
  const starterMethods = (starterIdentification.methods ?? {}) as Record<string, unknown>;
  const excludedGames = rateRows(report.excluded_games);
  const actualSources = (report.actual_source_counts ?? {}) as Record<string, unknown>;
  const currentQbs = rateRows(report.current_qbs);
  const validation = (report.qb_statistical_validation ?? {}) as ReportPlayer;
  const starterValidation = (report.starter_qb_statistical_validation ?? {}) as ReportPlayer;
  const shadow = (report.shadow_qb_captain ?? {}) as ReportPlayer;
  const measuredModel = (validation.all_measured_features ?? {}) as ReportPlayer;
  const measuredCoefficients = (measuredModel.standardized_coefficients ?? {}) as Record<string, unknown>;
  const prior = (report.prior_application ?? {}) as ReportPlayer;
  const fullValidation = (report.full_optimizer_validation ?? {}) as ReportPlayer;
  const coverage = (report.feature_coverage ?? {}) as Record<string, ReportPlayer>;
  const ci = (row: ReportPlayer): string => {
    return Array.isArray(row.wilson_95) && (row.wilson_95 as unknown[]).length === 2
      ? `${percent((row.wilson_95 as unknown[])[0])}–${percent((row.wilson_95 as unknown[])[1])}` : "Unavailable";
  };
  const available = (value: unknown, digits = 2): string => value == null ? "Unavailable" : number(value, digits);
  const bucketTable = (title: string, rows: ReportPlayer[]): string => rows.length
    ? `<details><summary>${escapeHtml(title)}</summary><table><thead><tr><th>Bucket</th><th>Optimal CPT</th><th>Eligible QBs</th><th>Optimal CPT %</th><th>95% interval</th><th>Reliability</th></tr></thead><tbody>${rows.map((row) => `<tr><td>${escapeHtml(row.label)}</td><td>${number(row.optimal_count, 0)}</td><td>${number(row.eligible_opportunities, 0)}</td><td>${percent(row.optimal_rate)}</td><td>${ci(row)}</td><td>${escapeHtml(row.reliability)}</td></tr>`).join("")}</tbody></table></details>` : "";
  const validationTable = (label: string, study: ReportPlayer): string => {
    if (!study.base) return `<p>${escapeHtml(label)} validation: ${escapeHtml(study.status)}</p>`;
    const models: [string, string][] = [["A. Base", "base"], ["B. + carries", "with_recent_carries"], ["C. + prior TD proxy", "with_td_proxy"], ["D. + archetype", "with_archetype"], ["E. Full supported", "full_supported"]];
    return `<details><summary>${escapeHtml(label)} chronological validation: ${number(study.training_optimal_qbs, 0)}/${number(study.training_rows, 0)} train, ${number(study.test_optimal_qbs, 0)}/${number(study.test_rows, 0)} holdout</summary><table><thead><tr><th>Model</th><th>AUC</th><th>Brier</th><th>Log loss</th><th>Calibration error</th></tr></thead><tbody>${models.map(([name, key]) => { const result = (study[key] ?? {}) as ReportPlayer; return `<tr><td>${escapeHtml(name)}</td><td>${available(result.holdout_auc, 3)}</td><td>${available(result.holdout_brier, 4)}</td><td>${available(result.holdout_log_loss, 4)}</td><td>${available(result.holdout_calibration_error, 4)}</td></tr>`; }).join("")}</tbody></table><p>Exploratory: ${escapeHtml(study.status)}. Calibration bins and coefficients are saved in the JSON artifact.</p></details>`;
  };
  const archetypeTable = (title: string, rows: ReportPlayer[]): string => `<h3>${escapeHtml(title)}</h3><table><thead><tr><th>QB archetype</th><th>Optimal CPT</th><th>Eligible QBs</th><th>Optimal CPT %</th><th>95% interval</th><th>Reliability</th></tr></thead><tbody>${rows.map((row) => `<tr><td>${escapeHtml(row.label)}</td><td>${number(row.optimal_count, 0)}</td><td>${number(row.eligible_opportunities, 0)}</td><td>${percent(row.optimal_rate)}</td><td>${ci(row)}</td><td>${escapeHtml(row.reliability)}</td></tr>`).join("")}</tbody></table>`;
  const bucketKeys: [string, string][] = [["recent_carries", "rush attempts"], ["recent_rushing_tds", "prior rush TD proxy"], ["recent_rushing_yards", "prior rush yards"], ["favorite_status", "favorite status"], ["team_implied_total", "implied total"], ["qb_salary", "salary"], ["projected_mean", "projection"], ["passing_volume", "pass volume"], ["teammate_target_concentration", "teammate target concentration"]];
  return `<section class="lineup"><h2>Historical Captain Optimality</h2><p>${number(report.slate_count, 0)} unique completed legal actual-score games; seasons ${escapeHtml(JSON.stringify(report.games_by_season ?? {}))}. ${number(((report.duplicates_removed ?? []) as unknown[]).length, 0)} duplicate removed; ${number(report.games_with_captain_ties, 0)} tied-optimum game retained. ${number(((report.excluded_games ?? []) as unknown[]).length, 0)} incomplete game excluded. No older DraftKings salaries are stored. Position shares count one optimal Captain per game.</p>
  <p><strong>QB archetype prior:</strong> ${escapeHtml(prior.status)}. ${escapeHtml(prior.reason)} The existing Captain-position prior remains the live scoring input. ${escapeHtml(report.historical_feature_note)}</p>
  <h3>Overall positions</h3><table><thead><tr><th>Position</th><th>Optimal CPT</th><th>Games</th><th>Game share</th><th>95% interval</th><th>Eligible opportunities</th><th>Opportunity rate</th><th>Reliability</th></tr></thead><tbody>${positions.map((row) => `<tr><td>${escapeHtml(row.label)}</td><td>${number(row.optimal_count, 0)}</td><td>${number(report.slate_count, 0)}</td><td>${percent(row.slate_optimal_share)}</td><td>${ci({...row, wilson_95: row.slate_share_wilson_95})}</td><td>${number(row.eligible_opportunities, 0)}</td><td>${percent(row.optimal_rate)}</td><td>${escapeHtml(row.reliability)}</td></tr>`).join("")}</tbody></table>
  <p><strong>Historical coverage:</strong> ${escapeHtml(Object.entries(actualSources).map(([source, count]) => `${source} ${count}`).join(" · "))}. Oracle scoring assigns zero to salary rows missing from both actual-stat sources; this may mean inactivity or a source gap, so those zeros are not independently verified. Excluded games: ${escapeHtml(excludedGames.map((row) => `${row.season} W${row.week} ${row.slate}: ${row.reason}`).join("; ") || "none")}.</p>
  <p><strong>Starter coverage:</strong> ${number(starterIdentification.identified, 0)}/${number(starterIdentification.team_opportunities, 0)} team opportunities; both starters identified in ${number(starterIdentification.complete_two_team_games, 0)}/${number(report.slate_count, 0)} games. Methods: ${escapeHtml(Object.entries(starterMethods).map(([method, count]) => `${method} ${count}`).join(" · "))}. ${escapeHtml(starterIdentification.rule)} Ambiguous teams remain excluded from starter-only rates. Actual game usage is audit-only.</p>
  <p>Carry archetype boundaries: ${((report.qb_archetype_thresholds_recent_carries ?? []) as unknown[]).map((value) => number(value, 2)).join(" and ")}. High rushing volume does not establish a goal-line role.</p>
  ${archetypeTable("All eligible QB archetypes, including backups", archetypes)}${archetypeTable("Pregame-identified starter QB archetypes", starterArchetypes)}
  <h3>Starting-QB Captain game shares</h3><table><thead><tr><th>Group</th><th>Optimal-CPT games</th><th>Games with group</th><th>Share</th><th>95% interval</th><th>Reliability</th></tr></thead><tbody>${starterGameShares.map((row) => `<tr><td>${escapeHtml(row.label)}</td><td>${number(row.optimal_count, 0)}</td><td>${number(row.eligible_games, 0)}</td><td>${percent(row.optimal_game_share)}</td><td>${ci(row)}</td><td>${escapeHtml(row.reliability)}</td></tr>`).join("")}</tbody></table>
  ${bucketKeys.map(([key, label]) => `${bucketTable(`All QB ${label} buckets`, rateRows(buckets[key]))}${bucketTable(`Starter QB ${label} buckets`, rateRows(starterBuckets[key]))}`).join("")}
  <p><strong>Goal-line buckets:</strong> ${escapeHtml(((report.goal_line_buckets ?? {}) as ReportPlayer).reason)}. Recent rushing TDs are a prior-game proxy, not a measured goal-line role.</p>
  <h3>Current slate starting QBs</h3><div style="overflow-x:auto"><table><thead><tr><th>QB / starter source</th><th>Archetype</th><th>Mean / P90</th><th>FLEX / CPT salary</th><th>Recent carries</th><th>Recent rush yards / TDs</th><th>Projected rush yards / TDs</th><th>Red zone / goal line</th><th>Designed / scramble</th><th>Implied / spread</th><th>All-QB archetype</th><th>Starter-only archetype</th><th>Carry bucket (all / starters)</th><th>Prior rush-TD bucket</th><th>Current prior / CPT objective contribution</th><th>Best CPT family</th><th>Shadow delta / rank</th><th>Portfolio</th></tr></thead><tbody>${currentQbs.map((row) => `<tr><td>${escapeHtml(row.qb)} (${escapeHtml(row.team)}) · ${escapeHtml(row.starter_status)} · ${escapeHtml(row.starter_evidence_tier)}</td><td>${escapeHtml(row.archetype)}</td><td>${available(row.mean)} / ${available(row.p90)}</td><td>$${available(row.flex_salary, 0)} / $${available(row.captain_salary, 0)}</td><td>${available(row.recent_carries)} (${escapeHtml(row.recent_carries_source)})</td><td>${available(row.recent_rushing_yards)} / ${available(row.recent_rushing_tds, 3)}</td><td>${available(row.projected_rushing_yards)} / ${available(row.rushing_td_expectation, 3)}</td><td>${available(row.red_zone_role, 3)} / ${available(row.goal_line_role, 3)}</td><td>${available(row.designed_run_rate, 3)} / ${available(row.scramble_rate, 3)}</td><td>${available(row.team_implied_total)} / ${available(row.team_spread)}</td><td>${percent(row.historical_archetype_rate)} (${number(row.historical_archetype_count, 0)}/${number(row.historical_archetype_opportunities, 0)})</td><td>${percent(row.historical_starter_archetype_rate)} (${number(row.historical_starter_archetype_count, 0)}/${number(row.historical_starter_archetype_opportunities, 0)}; ${escapeHtml(row.historical_starter_reliability)})</td><td>${escapeHtml(row.historical_rush_bucket)}: ${percent(row.historical_rush_bucket_rate)} / ${percent(row.historical_starter_rush_bucket_rate)} (${number(row.historical_starter_rush_bucket_count, 0)}/${number(row.historical_starter_rush_bucket_opportunities, 0)})</td><td>${escapeHtml(row.historical_starter_td_bucket)}: ${percent(row.historical_starter_td_bucket_rate)} (${number(row.historical_starter_td_bucket_count, 0)}/${number(row.historical_starter_td_bucket_opportunities, 0)})</td><td>×${available(row.existing_position_prior_multiplier, 3)} / ${available(row.captain_position_prior_contribution, 3)}</td><td>${row.best_family_rank == null ? "Unavailable" : `#${number(row.best_family_rank, 0)} · ${available(row.best_family_mean)} mean / ${available(row.best_family_p90)} P90 · ${available(row.best_family_selector)} selector`}</td><td>${available(row.shadow_qb_cpt_adjustment, 3)} / #${available(row.shadow_rank, 0)}</td><td>${row.selected ? "Yes" : `No: ${escapeHtml(row.family_reason)}`}</td></tr>`).join("")}</tbody></table></div>
  <p><strong>Shadow candidate rerank:</strong> ${escapeHtml(shadow.status)}. ${escapeHtml(shadow.formula)} This does not change the live optimizer or final portfolio.</p>
  ${validationTable("All QB", validation)}${validationTable("Starter QB", starterValidation)}
  <p><strong>Full optimizer A/B/C replay:</strong> ${escapeHtml(fullValidation.status)}. ${escapeHtml(fullValidation.reason)}</p>
  <details><summary>Exploratory QB logistic coefficients</summary><p>Associations after standardizing measured inputs; ${number(validation.training_optimal_qbs, 0)} training events are insufficient for a reliable material effect.</p><table><thead><tr><th>Feature</th><th>Standardized coefficient</th></tr></thead><tbody>${Object.entries(measuredCoefficients).map(([feature, value]) => `<tr><td>${escapeHtml(feature.replaceAll("_", " "))}</td><td>${number(value, 3)}</td></tr>`).join("")}</tbody></table></details>
  <p><strong>Missing evidence:</strong> ${escapeHtml(((report.unavailable_features ?? []) as string[]).join(", "))}. Historical CPT field ownership: ${escapeHtml(((report.historical_cpt_ownership ?? {}) as ReportPlayer).status)}. Tournament-winning Captains and top-1% Captain distributions are unavailable. No missing feature or ownership is zero-filled. QB recent-carry coverage: ${number(coverage.expected_carries?.observed, 0)}/${number(coverage.expected_carries?.eligible_qbs, 0)}.</p><details><summary>Why historical QB features are unavailable</summary><ul>${Object.entries((report.missing_data_report ?? {}) as Record<string, unknown>).map(([feature, reason]) => `<li><strong>${escapeHtml(feature)}:</strong> ${escapeHtml(reason)}</li>`).join("")}</ul></details></section>`;
}

function showdownScenarioHtml(lineups: ReportPlayer[][]): string {
  const report = (lineups[0]?.[0]?.captain_family_coverage_report ?? {}) as ReportPlayer;
  const coverage = (report.scenario_family_coverage ?? []) as ReportPlayer[];
  if (!coverage.length) return "";
  const definitions = (report.scenario_definitions ?? []) as ReportPlayer[];
  const candidates = (report.ranked_metrics ?? []) as ReportPlayer[];
  const definition = (id: unknown) => definitions.find((row) => row.scenario_id === id) ?? {};
  const requested = ["baseline", "team_a_decisive_win", "team_b_decisive_win"];
  const rows = requested.map((id) => {
    const row = coverage.find((item) => item.scenario_id === id);
    const condition = definition(id);
    return `<tr><td>${escapeHtml(condition.label ?? id.replaceAll("_", " ").toUpperCase())}</td><td>${condition.conditioned_winner ? `${escapeHtml(condition.conditioned_winner)} wins by ${number(condition.decisive_margin_threshold, 0)}+` : id === "baseline" ? "Market distribution" : "Unavailable"}</td><td>${number(row?.candidate_count ?? 0, 0)}</td><td>${row ? `#${number(row.best_rank, 0)}` : "—"}</td><td>${row ? number(row.best_mean) : "—"}</td><td>${row ? number(row.best_p90) : "—"}</td><td>${row ? number(row.best_selector) : "—"}</td><td>${escapeHtml(row?.best_captain ?? "—")}</td><td>${escapeHtml(row?.best_team_split ?? "—")}</td><td>${row ? `$${number(row.best_salary, 0)}` : "—"}</td><td>${row?.selected ? "Yes" : "No"}</td><td>${escapeHtml(row?.reason ?? report.scenario_generation_status ?? "No candidates generated")}</td></tr>`;
  }).join("");
  const candidateRows = candidates.map((row) => { const condition = definition(row.scenario_id); return `<tr><td>#${number(row.rank, 0)}</td><td>${escapeHtml(condition.label ?? row.scenario_id)}</td><td>${condition.conditioned_winner ? `${escapeHtml(condition.conditioned_winner)} by ${number(condition.decisive_margin_threshold, 0)}+` : "Market"}</td><td>${escapeHtml(row.candidate_source)}</td><td>${escapeHtml(row.captain_name)}</td><td>${escapeHtml(row.team_split)}</td><td>$${number(row.salary, 0)}</td><td>${number(row.baseline_mean)} → ${number(row.mean)}</td><td>${number(row.baseline_p90)} → ${number(row.p90)}</td><td>${number(row.selector)}</td><td>${row.quality_eligible ? "Yes" : "No"}</td></tr>`; }).join("");
  return `<section class="lineup"><h2>SHOWDOWN GAME-SCRIPT SCENARIOS</h2><p>${escapeHtml(report.scenario_generation_status ?? "")}. Require scenario diversity: ${report.require_scenario_diversity ? "on" : "off"}. ${report.require_scenario_diversity ? `Unconstrained selected ranks: ${escapeHtml(((report.ordinary_selected_ranks ?? []) as number[]).join(", "))}.` : "Scenario candidates compete on the normal selector and joint quality floor."}</p><p>Scenario conditioning method: ${escapeHtml(definitions[0]?.adjustment_method ?? "unavailable")}. Candidate P90 is the sum of player ceilings, not a simulated joint percentile.</p><div style="overflow-x:auto"><table><thead><tr><th>Scenario</th><th>Condition</th><th>Candidates</th><th>Best rank</th><th>Best mean</th><th>Best P90</th><th>Best selector</th><th>Best Captain</th><th>Team split</th><th>Salary</th><th>Selected</th><th>Coverage reason</th></tr></thead><tbody>${rows}</tbody></table></div><details><summary>All scenario candidates (${candidates.length})</summary><div style="overflow-x:auto"><table><thead><tr><th>Global rank</th><th>Scenario</th><th>Condition</th><th>Source</th><th>Captain</th><th>Team split</th><th>Salary</th><th>Baseline → conditioned mean</th><th>Baseline → conditioned P90</th><th>Selector</th><th>Quality floor</th></tr></thead><tbody>${candidateRows}</tbody></table></div></details></section>`;
}

function portfolioDiagnosticsHtml(lineups: ReportPlayer[][]): string {
  const first = lineups[0]?.[0] ?? {};
  const familyReport = (first.captain_family_coverage_report ?? {}) as ReportPlayer;
  const familyRows = Array.isArray(familyReport.family_rows) ? familyReport.family_rows as ReportPlayer[] : [];
  const sourceCoverage = (familyReport.source_coverage ?? {}) as Record<string, unknown>;
  const favoriteControlSources = Object.entries(sourceCoverage).filter(([source, count]) => source.startsWith("script:PHI_") && Number(count) > 0);
  const favoriteControlHtml = favoriteControlSources.length ? `<p>Favorite-control discovery candidates tested: ${favoriteControlSources.map(([source]) => escapeHtml(source.replace("script:", "").replaceAll("_", " "))).join(", ")}. These compete with all other candidates; they are not portfolio requirements.</p>` : "";
  const familyHtml = familyRows.length ? `<details open><summary>Captain family coverage</summary><p>${number(familyReport.candidate_count, 0)} distinct candidates; ${number(familyReport.quality_eligible_count, 0)} pass the joint ${number(Number(familyReport.quality_fraction) * 100, 0)}% mean/P90 screen. ${escapeHtml(familyReport.ownership_selection_status)}. A lineup has ownership diagnostics only when all six roster slots have role ownership. Shadow columns rerank saved candidates only.</p>${favoriteControlHtml}<table><thead><tr><th>Captain</th><th>Position</th><th>Historical optimal CPT %</th><th>QB archetype / rate</th><th>Archetype live adjustment</th><th>Best legal rank</th><th>Salary</th><th>Mean</th><th>P90</th><th>Correlation</th><th>CPT ownership</th><th>Lineup ownership</th><th>Live selector</th><th>CPT prior contribution</th><th>Shadow delta</th><th>Hypothetical selector</th><th>Shadow rank</th><th>Portfolio</th><th>Reason</th></tr></thead><tbody>${familyRows.map((row) => `<tr><td>${escapeHtml(row.captain_name)}</td><td>${escapeHtml(row.captain_position)}</td><td>${row.historical_position_optimal_share == null ? "Unavailable" : `${number(Number(row.historical_position_optimal_share) * 100, 1)}%`}</td><td>${row.captain_archetype ? `${escapeHtml(row.captain_archetype)} / ${row.historical_archetype_optimal_rate == null ? "Unavailable" : `${number(Number(row.historical_archetype_optimal_rate) * 100, 1)}%`}` : "—"}</td><td>${number(row.archetype_prior_adjustment, 3)}</td><td>#${number(row.rank, 0)}</td><td>$${number(row.salary, 0)}</td><td>${number(row.mean)}</td><td>${number(row.p90)}</td><td>${number(row.correlation)}</td><td>${number(row.captain_ownership)}</td><td>${number(row.lineup_ownership)}</td><td>${number(row.selector)}</td><td>${number(row.captain_position_prior_contribution, 3)}</td><td>${row.shadow_qb_cpt_adjustment == null ? "Unavailable" : number(row.shadow_qb_cpt_adjustment, 3)}</td><td>${row.hypothetical_selector == null ? "Unavailable" : number(row.hypothetical_selector, 3)}</td><td>${row.shadow_rank == null ? "Unavailable" : `#${number(row.shadow_rank, 0)}`}</td><td>${row.selected ? "Selected" : "Not selected"}</td><td>${escapeHtml(row.reason)}</td></tr>`).join("")}</tbody></table></details>` : "";
  const contest = first.portfolio_contest_report as ReportPlayer | undefined;
  const economics = contest?.economics as ReportPlayer | undefined;
  const contestHtml = contest && economics ? `<section class="lineup"><h2>5-max contest: ${escapeHtml(contest.name)}</h2><p>Verified maximum ${number(contest.maximum_entries, 0)} entries · ${number(contest.generated_entries, 0)}/${number(contest.requested_entries, 0)} lineups generated · $${number(contest.generated_entry_cost, 2)} generated cost ($${number(contest.requested_entry_cost, 2)} for all five).</p><p>Filled ${number(contest.current_entries, 0)}/${number(contest.capacity, 0)} · prize pool $${number(contest.prize_pool, 2)} · paid ${number(Number(economics.paid_percentage) * 100, 1)}% · min cash $${number(economics.minimum_cash, 2)} · full-field rake ${number(Number(economics.full_field_rake) * 100, 1)}% · lock ${escapeHtml(contest.lock_time)}${economics.near_lock ? ` · near-lock overlay $${number(economics.current_overlay, 2)}` : ""}</p><details><summary>Full payout ladder</summary><table><thead><tr><th>Ranks</th><th>Prize</th></tr></thead><tbody>${((contest.payout_ladder ?? []) as ReportPlayer[]).map((tier) => `<tr><td>${number(tier.from, 0)}–${number(tier.to, 0)}</td><td>$${number(tier.cash, 2)}</td></tr>`).join("")}</tbody></table></details><p>This five-lineup strategy does not compare entry counts or estimate contest-specific payout probability.</p></section>` : "";
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
  return contestHtml + familyHtml + exposureHtml + captainHtml + underfillHtml;
}

function singleEntryReportHtml(lineups: ReportPlayer[][], enforceSingleTe: boolean): string {
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
    ${((contestSelection.snapshot_fallbacks ?? []) as ReportPlayer[]).length ? `<p><strong>Saved snapshot fallback:</strong> ${((contestSelection.snapshot_fallbacks ?? []) as ReportPlayer[]).map((row) => `${escapeHtml(row.contest_id)} observed ${escapeHtml(row.observed_at)}`).join("; ")}. Refresh DraftKings data before lock to evaluate current entries and overlay.</p>` : ""}
    <p>${escapeHtml(contestSelection.selection_reason)} Search: ${escapeHtml(contestSelection.search_method)}; ${number(contestSelection.evaluated_subsets, 0)} subsets evaluated.</p>
    <h3>Best subset by contest count</h3><table><thead><tr><th>Contests</th><th>Best subset</th><th>Entry fees</th><th>Heuristic value</th><th>Independent ranks</th><th>Shared percentile</th></tr></thead><tbody>${countComparisons.map((row) => `<tr><td>${number(row.contest_count, 0)}</td><td>${escapeHtml(((row.contest_names ?? row.contest_ids) as string[]).join(", "))}</td><td>$${number(row.total_entry_fees, 2)}</td><td>${number(Number(row.heuristic_value) * 100, 1)}%</td><td>${number(Number(row.independent_rank_proxy) * 100, 1)}%</td><td>${number(Number(row.shared_percentile_proxy) * 100, 1)}%</td></tr>`).join("")}</tbody></table>${sensitivityHtml}<h3>Available contests</h3>
    <div style="overflow-x:auto"><table><thead><tr><th>Selected</th><th>Contest</th><th>Single-contest proxy</th><th>Entry</th><th>Field</th><th>Paid</th><th>Min cash</th><th>Top 1%</th><th>5%</th><th>10%</th><th>20%</th><th>Median paid</th><th>1st share</th><th>Top 10 share</th><th>Flatness</th><th>Full rake</th><th>Near-lock rake / overlay</th></tr></thead><tbody>${rankedContests.map((row) => { const e = (row.economics ?? {}) as ReportPlayer; const percentiles = (e.payout_at_field_percentiles ?? {}) as ReportPlayer; return `<tr><td>${selectedIds.includes(String(row.contest_id)) ? "Yes" : "No"}</td><td>${escapeHtml(row.name)}</td><td>${number(Number(row.contest_score) * 100, 1)}%</td><td>$${number(row.entry_fee, 2)}</td><td>${number(row.capacity, 0)}</td><td>${number(Number(e.paid_percentage) * 100, 1)}%</td><td>$${number(e.minimum_cash, 2)} (${number(e.minimum_cash_multiple, 2)}×)</td><td>$${number(percentiles["1"], 2)}</td><td>$${number(percentiles["5"], 2)}</td><td>$${number(percentiles["10"], 2)}</td><td>$${number(percentiles["20"], 2)}</td><td>$${number(e.median_paid_payout, 2)}</td><td>${number(Number(e.first_place_share) * 100, 1)}%</td><td>${number(Number(e.top_10_share) * 100, 1)}%</td><td>${number(e.payout_flatness, 3)}</td><td>${number(Number(e.full_field_rake) * 100, 1)}%</td><td>${row.source === "saved_snapshot" ? "Snapshot; not applied" : e.current_effective_rake == null ? "Too early" : `${number(Number(e.current_effective_rake) * 100, 1)}% / $${number(e.current_overlay, 2)}`}</td></tr>`; }).join("")}</tbody></table></div>` : "";
  const comparisonRows = [comparisons.aaa, comparisons.best_one_alternate, comparisons.best_repeated_alternate, comparisons.best_two_alternates]
    .filter(Boolean) as ReportPlayer[];
  const comparisonHtml = comparisonRows.map((row) => `<tr><td>${escapeHtml(row.structure)}</td><td>${escapeHtml((row.candidate_ranks as number[]).join(" / "))}</td><td>${number(row.quality_loss_total, 3)}</td><td>${number(row.diversification_credit_total, 3)}</td><td>${number(row.heuristic_delta_vs_aaa, 3)}</td></tr>`).join("");
  const featured = (report.top_alternates ?? {}) as ReportPlayer;
  const alternateRows: [string, unknown][] = [
    ["Different Captain, same six players", featured.different_captain_only],
    ["Different Captain and player combination", featured.different_captain_material_players],
    ["Different lineup structure", featured.different_game_script],
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
  const hasDecomposition = unique.every((row) => row.objective_contributions && row.solver_objective_components);
  const decompositionRows = unique.map((row) => {
    const terms = (row.objective_contributions ?? {}) as ReportPlayer;
    const solver = (row.solver_objective_components ?? {}) as ReportPlayer;
    const sacrifice = (row.quality_sacrifice_for_chalk ?? {}) as ReportPlayer;
    return `<tr><td>#${number(row.rank, 0)} ${escapeHtml(row.captain)}</td><td>${number(row.single_entry_score, 4)}</td><td>${number(terms.mean, 4)}</td><td>${number(terms.p90, 4)}</td><td>${number(terms.solver, 4)}</td><td>${number(terms.correlation, 4)}</td><td>${number(terms.context, 4)}</td><td>${number(terms.chalk_penalty, 4)}</td><td>${number(terms.duplication_uniqueness, 4)} (inactive)</td><td>${number(terms.script, 4)} (inactive)</td><td>${number(terms.other_penalties, 4)}</td><td>${number(sacrifice.mean_loss_vs_best_mean, 2)}</td><td>${number(sacrifice.p90_loss_vs_best_p90, 2)}</td><td>${number(sacrifice.chalk_improvement_vs_best_quality, 1)}</td><td>${number(sacrifice.chalk_objective_gain_vs_best_quality, 4)}</td><td>${sacrifice.large_ceiling_sacrifice_for_uniqueness ? "Flag" : "—"}</td></tr>`;
  }).join("");
  const solverRows = unique.map((row) => {
    const terms = (row.solver_objective_components ?? {}) as ReportPlayer;
    return `<tr><td>#${number(row.rank, 0)} ${escapeHtml(row.captain)}</td><td>${number(row.solver_objective, 3)}</td><td>${number(terms.p90_ceiling, 3)}</td><td>${number(terms.context, 3)}</td><td>${number(terms.captain_prior, 3)}</td><td>${number(terms.ownership_penalty, 3)}</td><td>${number(terms.correlation_and_format, 3)}</td><td>${number(terms.other_or_unattributed, 3)}</td></tr>`;
  }).join("");
  const flagged = unique.filter((row) => Boolean(((row.quality_sacrifice_for_chalk ?? {}) as ReportPlayer).large_ceiling_sacrifice_for_uniqueness));
  const sacrificeNotes = flagged.map((row) => {
    const trade = row.quality_sacrifice_for_chalk as ReportPlayer;
    return `<li>Candidate #${number(row.rank, 0)} reduces summed P90 by ${number(trade.p90_loss_vs_best_p90, 2)} points versus candidate #${number(trade.best_p90_candidate_rank, 0)} in exchange for a ${number(trade.chalk_improvement_vs_best_quality, 1)}-point improvement in relative chalk versus quality reference #${number(trade.best_quality_candidate_rank, 0)}.</li>`;
  }).join("");
  const first = unique[0] as ReportPlayer | undefined;
  const second = unique[1] as ReportPlayer | undefined;
  const topTwo = first && second ? `<h3>Candidate #1 versus #2</h3><p>#2 minus #1: mean ${number(Number(second.mean) - Number(first.mean), 4)} points; summed P90 ${number(Number(second.p90) - Number(first.p90), 4)} points; relative chalk ${number(Number(second.relative_chalk) - Number(first.relative_chalk), 4)} points. Selector margin (#1 minus #2): ${number(Number(first.single_entry_score) - Number(second.single_entry_score), 6)}.</p>${hasDecomposition ? `<p>Weighted selector differences (#1 minus #2): ${["mean", "p90", "solver", "correlation", "context", "chalk_penalty", "duplication_uniqueness", "script", "other_penalties"].map((key) => `${escapeHtml(key)} ${number(Number((first.objective_contributions as ReportPlayer)[key]) - Number((second.objective_contributions as ReportPlayer)[key]), 6)}`).join("; ")}. Positive terms favor #1; their sum explains its selector lead.</p>` : ""}` : "";
  return `<section class="lineup"><h2>Recommended portfolio: ${escapeHtml(report.recommended_structure ?? "A")}</h2>
    <p><strong>Enforce single TE: ${enforceSingleTe ? "True" : "False"}</strong></p>
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
    ${topTwo}
    <h3>Single-entry objective decomposition</h3><p>Weighted selector contributions sum to the single-entry score. Solver is a nested component; its raw terms are shown separately below. Duplication and script have no direct selector term in this version. The quality reference maximizes the weighted mean plus summed-P90 terms before chalk.</p>${hasDecomposition ? `<div style="overflow-x:auto"><table><thead><tr><th>Candidate</th><th>Total</th><th>Mean</th><th>P90</th><th>Solver</th><th>Correlation</th><th>Context</th><th>Chalk</th><th>Duplication</th><th>Script</th><th>Other</th><th>Mean loss</th><th>P90 loss</th><th>Chalk improvement</th><th>Chalk score gain</th><th>Ceiling trade</th></tr></thead><tbody>${decompositionRows}</tbody></table></div>` : `<p>Configuration error: this saved run predates component lineage. Rerun the optimizer to obtain numerical objective decomposition.</p>`}
    ${hasDecomposition ? `<h3>Nested solver objective</h3><p>Raw solver points reconcile to the solver total. The selector applies its solver weight to the normalized total above; these raw terms must not be added again to the selector score.</p><div style="overflow-x:auto"><table><thead><tr><th>Candidate</th><th>Solver total</th><th>Summed P90</th><th>Context</th><th>Captain prior</th><th>Slot ownership</th><th>Correlation / format</th><th>Other / residual</th></tr></thead><tbody>${solverRows}</tbody></table></div>` : ""}${sacrificeNotes ? `<ul>${sacrificeNotes}</ul>` : ""}
    <h3>${multipleContests ? "Selected, top 10, and featured alternate lineups" : "Selected lineup and top candidates"}</h3><div style="overflow-x:auto"><table><thead><tr><th>Rank</th><th>Captain</th><th>Mean</th><th>Sum P90</th><th>Relative chalk</th><th>Script</th>${multipleContests ? "<th>Shared with A</th><th>Overlap</th><th>Jaccard</th><th>Quality loss</th><th>Diversification benefit</th>" : ""}<th>Players</th></tr></thead><tbody>${candidateRows}</tbody></table></div></section>`;
}

function threeMaxReportHtml(lineups: ReportPlayer[][]): string {
  const report = (lineups[0]?.find((row) => row.small_max_report || row.three_max_report)?.small_max_report ?? lineups[0]?.find((row) => row.three_max_report)?.three_max_report) as ReportPlayer | undefined;
  if (!report) return "";
  if (report.contest_mode === "generic") {
    const selected = report.selected as ReportPlayer | undefined;
    const configured = report.selection_mode === "configured";
    const counts = (report.count_comparisons ?? []) as (ReportPlayer | null)[];
    const rows = counts.map((row, index) => `<tr><td>${index + 1}</td>${row ? `<td>${escapeHtml((row.candidate_ranks as number[]).join(" / "))}</td><td>${number(row.lineup_quality_contribution, 4)}</td><td>${number(row.diversification_contribution, 4)}</td><td>${number(row.average_mean, 1)} / ${number(row.minimum_mean, 1)}</td><td>${number(row.average_p90, 1)} / ${number(row.minimum_p90, 1)}</td><td>${escapeHtml((row.captains as string[]).join(" / "))}</td><td>${escapeHtml((row.scripts as string[]).join(" / "))}</td>` : `<td colspan="7">No qualifying portfolio under the quality and exposure rules</td>`}</tr>`).join("");
    const pairs = ((selected?.pairwise ?? []) as ReportPlayer[]).map((pair) => `<li>#${escapeHtml((pair.candidate_ranks as number[]).join(" / #"))}: ${number(pair.shared_players, 0)} shared · ${number(pair.overlap_percentage, 1)}% overlap · Captain ${pair.same_captain ? "same" : "different"} · script ${pair.same_script ? "same" : "different"}</li>`).join("");
    return `<section class="lineup"><h2>Generic small-max lineup selection: ${number(report.selected_count, 0)} ${Number(report.selected_count) === 1 ? "entry" : "entries"}</h2><p>${escapeHtml(report.note ?? "")} Entry limit: ${number(report.maximum_entries, 0)}. ${configured ? `Requested entries: ${number(report.configured_entry_count, 0)}.` : "Auto selected one lineup; entry-count economics require a contest."} Enforce single TE: ${report.enforce_single_te ? "True" : "False"}.</p><p>${number(report.qualifying_candidate_count, 0)} qualifying candidates of ${number(report.candidate_count, 0)} unique lineups.</p><table><thead><tr><th>Entries</th><th>Ranks</th><th>Quality score</th><th>Diversity credit</th><th>Mean avg / min</th><th>P90 avg / min</th><th>Captains</th><th>Scripts</th></tr></thead><tbody>${rows}</tbody></table>${selected ? `<p>Selected ranks ${escapeHtml((selected.candidate_ranks as number[]).join(" / "))}; ${number(selected.unique_captains, 0)} unique Captains and ${number(selected.script_diversity, 0)} scripts. Captain exposures: ${Object.entries((selected.captain_exposures ?? {}) as Record<string, number>).map(([name, rate]) => `${escapeHtml(name)} ${number(rate * 100, 0)}%`).join("; ")}. Player exposures: ${Object.entries((selected.player_exposures ?? {}) as Record<string, number>).map(([name, rate]) => `${escapeHtml(name)} ${number(rate * 100, 0)}%`).join("; ")}.</p><h3>Pairwise overlap</h3><ul>${pairs}</ul>` : ""}</section>`;
  }
  const selected = report.selected as ReportPlayer | undefined;
  const counts = (report.count_comparisons ?? []) as (ReportPlayer | null)[];
  const rows = counts.map((row, index) => `<tr><td>${index + 1}</td>${row ? `<td>${escapeHtml((row.candidate_ranks as number[]).join(" / "))}</td><td>$${number(row.total_entry_fees, 2)}</td><td>${number(row.lineup_selection_score, 4)}</td><td>${number(row.portfolio_objective, 4)}</td><td>${number(row.payout_proxy, 4)}</td><td>${number(row.lineup_quality_contribution, 4)}</td><td>${number(row.diversification_contribution, 4)}</td><td>${number(row.average_mean, 1)} / ${number(row.minimum_mean, 1)}</td><td>${number(row.average_p90, 1)} / ${number(row.minimum_p90, 1)}</td><td>${number(row.average_relative_chalk, 1)}</td><td>${escapeHtml((row.captains as string[]).join(" / "))}</td>` : `<td colspan="11">No qualifying portfolio</td>`}</tr>`).join("");
  const pairs = ((selected?.pairwise ?? []) as ReportPlayer[]).map((pair) => `<li>#${escapeHtml((pair.candidate_ranks as number[]).join(" / #"))}: ${number(pair.shared_players, 0)} shared · ${number(pair.overlap_percentage, 1)}% overlap · Jaccard ${number(pair.jaccard_similarity, 3)} · Captain ${pair.same_captain ? "same" : "different"} · script ${pair.same_script ? "same" : "different"} · team emphasis ${pair.same_team_emphasis ? "same" : "different"} · shared punts ${escapeHtml(((pair.same_value_player_ids ?? []) as string[]).join(", ") || "none")} · chalk difference ${number(pair.relative_chalk_difference, 1)} · repeated Captain materially different ${pair.repeated_captain_materially_different ? "yes" : "no"}</li>`).join("");
  const autoCount = Number(report.auto_recommended_count ?? counts.reduce<{ score: number; count: number }>((best, row, index) => row && Number(row.portfolio_objective) > best.score ? { score: Number(row.portfolio_objective), count: index + 1 } : best, { score: -Infinity, count: 0 }).count);
  const configured = report.selection_mode === "configured" || (report.entries_to_use != null && report.entries_to_use !== "auto");
  const configuredCount = Number(report.configured_entry_count ?? report.entries_to_use ?? report.selected_count);
  const heading = configured
    ? configuredCount === Number(report.selected_count) ? `Configured portfolio: ${configuredCount} ${configuredCount === 1 ? "entry" : "entries"}` : `Configured target: ${configuredCount} entries; feasible portfolio: ${number(report.selected_count, 0)} entries`
    : `Small-max recommendation: ${number(report.selected_count, 0)} ${Number(report.selected_count) === 1 ? "entry" : "entries"}`;
  const countMarginal = ((report.count_marginals ?? []) as ReportPlayer[]).map((row) => `<li>Best ${number(row.entry_count, 0)}-entry portfolio vs best ${number(row.from_count ?? Number(row.entry_count) - 1, 0)}-entry portfolio: objective delta ${row.objective_change == null ? "baseline" : number(row.objective_change, 4)}, payout-proxy delta ${row.payout_proxy_change == null ? "baseline" : number(row.payout_proxy_change, 4)}, quality delta ${row.lineup_quality_change == null ? "baseline" : number(row.lineup_quality_change, 4)}, diversity delta ${row.diversification_change == null ? "baseline" : number(row.diversification_change, 4)}, fee delta $${number(row.fee_delta ?? row.additional_entry_fee, 2)}; candidates added ${escapeHtml(((row.added_candidate_ranks ?? []) as number[]).join(", ") || "none")}, removed ${escapeHtml(((row.removed_candidate_ranks ?? []) as number[]).join(", ") || "none")}</li>`).join("");
  const leaveOneOut = ((report.leave_one_out ?? []) as ReportPlayer[]).map((row) => `<li>Remove candidate #${number(row.candidate_rank, 0)} (${escapeHtml(row.captain)} CPT, mean ${number(row.mean, 2)}, P90 ${number(row.p90, 2)}, chalk ${number(row.relative_chalk, 1)}): remaining ranks ${escapeHtml(((row.remaining_candidate_ranks ?? []) as number[]).join(", ") || "none")}; objective without ${number(row.objective_without_lineup, 4)}; change if removed ${number(row.objective_change_if_removed, 4)}</li>`).join("");
  const contest = report.contest as ReportPlayer;
  const economics = contest.economics as ReportPlayer | undefined;
  const contestEconomics = economics ? `<p>Field ${number(contest.current_entries, 0)}/${number(contest.capacity, 0)} · prize pool $${number(contest.prize_pool, 2)} · paid ${number(Number(economics.paid_percentage) * 100, 1)}% · min cash $${number(economics.minimum_cash, 2)} · first-place share ${number(Number(economics.first_place_share) * 100, 1)}% · full-field rake ${number(Number(economics.full_field_rake) * 100, 1)}% · lock ${escapeHtml(contest.lock_time)}${economics.near_lock ? ` · near-lock overlay $${number(economics.current_overlay, 2)}` : ""}</p>` : "";
  const bestThree = counts[2];
  const threeLineups = ((bestThree?.lineups ?? []) as ReportPlayer[]).map((row) => `<li>#${number(row.rank, 0)} ${escapeHtml(row.captain)} CPT · mean ${number(row.mean, 1)} · P90 ${number(row.p90, 1)} · chalk ${number(row.relative_chalk, 1)} · ${escapeHtml(row.script)} · ${((row.players ?? []) as ReportPlayer[]).map((player) => `${escapeHtml(player.slot)} ${escapeHtml(player.name)}`).join(" / ")}</li>`).join("");
  const structures = Object.entries((report.structure_comparisons ?? {}) as Record<string, ReportPlayer | null>).map(([name, row]) => `${escapeHtml(name.replaceAll("_", " "))}: ${row ? `#${escapeHtml((row.candidate_ranks as number[]).join(" / #"))} objective ${number(row.portfolio_objective, 4)}` : "unavailable"}`).join("; ");
  return `<section class="lineup"><h2>${heading}</h2><p>Configured entry count: ${configured ? configuredCount : "Auto"}. Auto recommendation under current heuristic: ${autoCount} ${autoCount === 1 ? "entry" : "entries"}.</p><p>${escapeHtml(contest.name)} · $${number(contest.entry_fee, 2)} each · ${number(contest.maximum_entries, 0)} maximum entries. Enforce single TE: ${report.enforce_single_te ? "True" : "False"}.</p>${contestEconomics}<p>${escapeHtml(report.note ?? "")} ${number(report.qualifying_candidate_count, 0)} qualifying candidates of ${number(report.candidate_count, 0)} unique lineups.</p><table><thead><tr><th>Entries</th><th>Ranks</th><th>Cost</th><th>Lineup set score</th><th>Count objective</th><th>Payout proxy</th><th>Quality</th><th>Diversity</th><th>Mean avg / min</th><th>P90 avg / min</th><th>Chalk avg</th><th>Captains</th></tr></thead><tbody>${rows}</tbody></table>${selected ? `<p>Selected ranks ${escapeHtml((selected.candidate_ranks as number[]).join(" / "))}; ${number(selected.unique_captains, 0)} unique Captains and ${number(selected.script_diversity, 0)} scripts. Captain exposures: ${Object.entries((selected.captain_exposures ?? {}) as Record<string, number>).map(([name, rate]) => `${escapeHtml(name)} ${number(rate * 100, 0)}%`).join("; ")}. Player exposures: ${Object.entries((selected.player_exposures ?? {}) as Record<string, number>).map(([name, rate]) => `${escapeHtml(name)} ${number(rate * 100, 0)}%`).join("; ")}.</p><h3>Pairwise overlap</h3><ul>${pairs}</ul><h3>Best portfolio count comparisons</h3><ul>${countMarginal}</ul><h3>Selected portfolio leave-one-out</h3><ul>${leaveOneOut}</ul>` : ""}${bestThree ? `<h3>Best three-entry version</h3><ul>${threeLineups}</ul><p>Captain exposure: ${Object.entries((bestThree.captain_exposures ?? {}) as Record<string, number>).map(([name, rate]) => `${escapeHtml(name)} ${number(rate * 100, 0)}%`).join("; ")}. Player exposure: ${Object.entries((bestThree.player_exposures ?? {}) as Record<string, number>).map(([name, rate]) => `${escapeHtml(name)} ${number(rate * 100, 0)}%`).join("; ")}.</p><ul>${((bestThree.pairwise ?? []) as ReportPlayer[]).map((pair) => `<li>#${escapeHtml((pair.candidate_ranks as number[]).join(" / #"))}: ${number(pair.shared_players, 0)} shared · ${number(pair.overlap_percentage, 1)}% overlap · Jaccard ${number(pair.jaccard_similarity, 3)} · Captain ${pair.same_captain ? "same" : "different"} · script ${pair.same_script ? "same" : "different"} · team emphasis ${pair.same_team_emphasis ? "same" : "different"} · shared punts ${escapeHtml(((pair.same_value_player_ids ?? []) as string[]).join(", ") || "none")} · chalk difference ${number(pair.relative_chalk_difference, 1)}</li>`).join("")}</ul><p>Captain structures: ${structures}</p>` : ""}</section>`;
}

export function buildOptimizerReportHtml(
  optimizer: OptimizerResponse,
  context: ReportContext,
): string {
  const lineups = Array.isArray(optimizer.results)
    ? optimizer.results.filter(Array.isArray) as ReportPlayer[][]
    : [];
  const pool = optimizer.player_pool;
  const isShowdown = Boolean(lineups[0]?.[0]?.single_entry_report) || String(optimizer.strategy ?? "").startsWith("showdown_");
  if (isShowdown && typeof optimizer.enforce_single_te !== "boolean") {
    throw new Error("Showdown configuration error: enforce_single_te is missing from the saved optimizer request.");
  }
  const singleTeMetadata = optimizer.enforce_single_te === true ? "True" : optimizer.enforce_single_te === false ? "False" : "Not applicable";
  const poolSummary = pool
    ? `Raw pool: ${pool.raw_pool_count ?? pool.initial_count} → opportunity eligible: ${pool.opportunity_eligible_count ?? pool.eligible_count ?? pool.initial_count} → optimizer eligible: ${pool.optimizer_eligible_count ?? pool.included_count} · Pool warnings: ${pool.warning_player_count ?? 0}`
    : "Player-pool summary unavailable";
  const removalReasons = {
    ...(pool?.prior_eligibility_removal_reason_counts ?? {}),
    ...(pool?.removal_reason_counts ?? {}),
  };
  const removalSummary = Object.keys(removalReasons).length
    ? `Removals: ${Object.entries(removalReasons).map(([reason, count]) => `${reason.replaceAll("_", " ")} (${count})`).join(" · ")}`
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
  const userExcludedPlayers = pool?.rows?.filter((row) =>
    row.optimizer_eligibility === "excluded_by_user_preference"
    || row.exclusion_details?.some((detail) => detail.category === "user")
  ) ?? [];
  const userExclusionDetails = userExcludedPlayers.length
    ? `<details open><summary>User preference exclusions (${userExcludedPlayers.length})</summary><p>These constraints are applied after the football and projection layers. The model assessment shown here is retained unchanged.</p><div style="overflow-x:auto"><table><thead><tr><th>Player</th><th>Football / model assessment</th><th>Optimizer eligibility</th><th>User preference reason</th></tr></thead><tbody>${userExcludedPlayers.map((row) => {
        const reasons = (row.user_preference_exclusions?.length
          ? row.user_preference_exclusions
          : row.exclusion_details?.filter((detail) => detail.category === "user") ?? []
        ).map((detail) => detail.description || detail.reason_code.replaceAll("_", " ")).join("; ");
        return `<tr><td>${escapeHtml(row.player_name)} · ${escapeHtml(row.team)} vs ${escapeHtml(row.opponent_team ?? "Unknown")}</td><td>Projection ${number(row.projection, 2)} DK · P90 ${number(row.p90, 2)}${row.model_assessment?.role_label ? ` · ${escapeHtml(row.model_assessment.role_label)}` : ""}</td><td>EXCLUDED</td><td>${escapeHtml(reasons || "User preference")}</td></tr>`;
      }).join("")}</tbody></table></div></details>`
    : "";
  const manuallyAffectedPlayers = pool?.rows?.filter((row) =>
    (row.availability_override != null && row.availability_override !== "default")
    || row.optimizer_eligibility === "excluded_by_user_preference"
    || Boolean(row.user_preference_exclusions?.length)
  ) ?? [];
  const manualDecisionDetails = manuallyAffectedPlayers.length
    ? `<details open><summary>Manual player decisions (${manuallyAffectedPlayers.length})</summary><p>Availability overrides change the football scenario before projection. Lineup preferences are applied afterward and leave the model unchanged.</p><div style="overflow-x:auto"><table><thead><tr><th>Player</th><th>Official status</th><th>Availability override</th><th>Model availability used</th><th>Projection before</th><th>Projection after</th><th>Opportunity redistributed?</th><th>Optimizer eligibility</th><th>Reason</th></tr></thead><tbody>${manuallyAffectedPlayers.map((row) => {
        const preferenceReasons = (row.user_preference_exclusions ?? [])
          .map((detail) => detail.description || detail.reason_code.replaceAll("_", " "));
        const otherReasons = (row.exclusion_details ?? [])
          .filter((detail) => detail.category !== "user")
          .map((detail) => detail.description || detail.reason_code.replaceAll("_", " "));
        const reasons = [...preferenceReasons, ...otherReasons];
        const before = row.projection_before_scenario ?? row.projection;
        const after = row.projection_after_scenario ?? row.projection;
        return `<tr><td>${escapeHtml(row.player_name)}</td><td>${escapeHtml(row.official_availability_status ?? row.pregame_injury_status ?? "Unavailable")}</td><td>${escapeHtml(String(row.availability_override ?? "default").replaceAll("_", " "))}</td><td>${row.model_availability_used == null ? "Unavailable" : number(row.model_availability_used, 2)}</td><td>${number(before, 2)}</td><td>${number(after, 2)}</td><td>${row.opportunity_redistributed ? "Yes" : "No"}</td><td>${row.included ? "ELIGIBLE" : "EXCLUDED"}</td><td>${escapeHtml(reasons.join("; ") || (row.availability_override === "assume_out" ? "Availability scenario: Assume Out" : "None"))}</td></tr>`;
      }).join("")}</tbody></table></div></details>`
    : "";
  const lowCostSurvivors = pool?.rows?.filter((row) => row.included && ["RB", "WR", "TE"].includes(row.position) && row.salary <= 2000) ?? [];
  const opportunityDetails = lowCostSurvivors.length ? `<details open><summary>Low-cost opportunity gate survivors (${lowCostSurvivors.length})</summary><p>Missing signals are shown as unavailable; the fallback result states why a player remains eligible under the current rule.</p><div style="overflow-x:auto"><table><thead><tr><th>Player</th><th>Salary / mean / P90</th><th>Roster / active / depth / role</th><th>Expected snaps / routes / carries / targets</th><th>Recent snap share / carries / targets</th><th>Usage shares</th><th>Explicit role / injury opportunity</th><th>Fallback threshold / reason</th></tr></thead><tbody>${lowCostSurvivors.map((row) => { const d = (row.opportunity_diagnostic ?? {}) as Record<string, unknown>; const value = (key: string) => d[key] == null ? "Unavailable" : String(d[key]); return `<tr><td>${escapeHtml(row.player_name)}</td><td>$${number(row.salary, 0)} / ${number(row.projection, 2)} / ${number(row.p90, 2)}</td><td>${escapeHtml(value("roster_status"))} / ${escapeHtml(value("expected_active_probability"))} / ${escapeHtml(value("depth_chart_role"))} / ${escapeHtml(value("role_label"))}</td><td>${["expected_snaps", "expected_routes", "expected_carries", "expected_targets"].map((key) => escapeHtml(value(key))).join(" / ")}</td><td>${["recent_snap_share_mean_3", "recent_carries_mean_3", "recent_targets_mean_3"].map((key) => escapeHtml(value(key))).join(" / ")}</td><td>${["carry_share", "target_share", "red_zone_share", "goal_line_share"].map((key) => escapeHtml(value(key))).join(" / ")}</td><td>${escapeHtml(value("explicit_role_signal"))} / ${escapeHtml(value("injury_created_opportunity"))}</td><td>${escapeHtml(value("low_salary_fallback_threshold_met"))} / ${escapeHtml(value("retention_reason"))}</td></tr>`; }).join("")}</tbody></table></div></details>` : "";
  const title = `${context.season} Week ${context.week} ${context.slate.replaceAll("_", " ")} Optimizer Report`;
  const readiness = ((lineups[0]?.[0]?.classic_small_field_report ?? {}) as ReportPlayer).entry_readiness as ReportPlayer | undefined;
  const readinessChecks = (readiness?.checks ?? {}) as Record<string, ReportPlayer>;
  const marketCoverage = (readiness?.market_coverage ?? {}) as ReportPlayer;
  const skillApprovalCases = (((lineups[0]?.[0]?.classic_small_field_report ?? {}) as ReportPlayer).skill_exposure_approvals ?? []) as ReportPlayer[];
  const marketSummary = marketCoverage.total_games == null ? "Market coverage unavailable" :
    `Market coverage: ${number(marketCoverage.sourced_games, 0)}/${number(marketCoverage.total_games, 0)} games · Fresh: ${((marketCoverage.fresh_games ?? []) as string[]).length} · Aging: ${((marketCoverage.aging_games ?? []) as string[]).length} · Stale: ${((marketCoverage.stale_games ?? []) as string[]).length} · Missing: ${((marketCoverage.missing_games ?? []) as string[]).length} · Latest refresh: ${escapeHtml(marketCoverage.newest_observed_at ?? "Unavailable")}`;
  const marketGames = Array.isArray(marketCoverage.games) ? marketCoverage.games as ReportPlayer[] : [];
  const marketGameTable = marketGames.length ? `<table><thead><tr><th>Game</th><th>Status</th><th>Source</th><th>Observed</th><th>Age at decision</th></tr></thead><tbody>${marketGames.map((game) => `<tr><td>${escapeHtml(game.game_id)}</td><td>${escapeHtml(game.status)}</td><td>${escapeHtml(game.source ?? "Unavailable")}</td><td>${escapeHtml(game.observed_at ?? "Unavailable")}</td><td>${game.age_hours == null ? "Unavailable" : `${number(game.age_hours, 1)} h`}</td></tr>`).join("")}</tbody></table>` : "";
  const approvalSummary = skillApprovalCases.length ? skillApprovalCases.map((row) => {
    const original = (row.original ?? {}) as ReportPlayer;
    const capped = (row.capped_80 ?? {}) as ReportPlayer;
    return `<tr><td>${escapeHtml(row.player)} (${escapeHtml(row.position)}) · ${number(row.selected_count, 0)}/${number(row.selected_total, 0)}</td><td>${number(row.mean)} / ${number(row.p90)} · $${number(row.salary, 0)} · value ${number(row.value)} · ownership ${number(row.ownership)}</td><td>${escapeHtml(row.core_classification)} · ${escapeHtml(row.availability)} · candidates ${number(row.candidate_count, 0)}/${number(row.candidate_total, 0)}</td><td>${number(original.selector_sum, 3)} / ${number(original.mean_sum)} / ${number(original.p90_sum)} · overlap ${number(original.max_overlap, 0)} · QBs ${escapeHtml(((original.qb_paths ?? []) as string[]).join(", "))}</td><td>${capped.selector_sum == null ? "Infeasible" : `${number(capped.selector_sum, 3)} / ${number(capped.mean_sum)} / ${number(capped.p90_sum)} · overlap ${number(capped.max_overlap, 0)} · QBs ${escapeHtml(((capped.qb_paths ?? []) as string[]).join(", "))}`}</td><td>${number(row.selector_cost, 3)} / ${number(row.mean_cost)} / ${number(row.p90_cost)}</td></tr>`;
  }).join("") : "";
  const fallbackReadiness = optimizer.status === "failed" ? "BLOCKED" : "DEVELOPMENT_PREVIEW";
  const readinessHtml = `<section class="lineup"><h2>Entry readiness</h2><p><strong>${readiness?.entry_ready === true ? "ENTRY READY: YES" : "ENTRY READY: NO"}</strong> · ${escapeHtml(readiness?.status ?? fallbackReadiness)}${readiness?.status === "DEVELOPMENT_PREVIEW" || !readiness && fallbackReadiness === "DEVELOPMENT_PREVIEW" ? " — NOT ENTRY READY" : ""}</p><h3>Market</h3><p>${marketSummary}</p>${marketGameTable}<h3>Approval required</h3>${skillApprovalCases.length ? `<p>100% skill-player exposure approval required. The optimizer prefers 100% exposure. Here is the cost of reducing it. Approve or choose an 80%/custom cap in the optimizer UI before export.</p><table><thead><tr><th>Player</th><th>Mean / P90 · salary · value · ownership</th><th>Core · availability · candidate exposure</th><th>Original selector / mean / P90 · overlap · QB paths</th><th>Capped 80%</th><th>Selector / mean / P90 cost</th></tr></thead><tbody>${approvalSummary}</tbody></table>` : "<p>None.</p>"}<table><thead><tr><th>Check</th><th>Status</th></tr></thead><tbody>${Object.entries(readinessChecks).map(([name, check]) => `<tr><td>${escapeHtml(name)}</td><td>${escapeHtml(check.status)}${check.reason ? ` · ${escapeHtml(check.reason)}` : ""}</td></tr>`).join("") || `<tr><td>Pre-entry validation</td><td>${fallbackReadiness} · ${optimizer.status === "failed" ? escapeHtml(optimizer.message ?? "optimizer failed") : "readiness was not evaluated for this run"}</td></tr>`}</tbody></table>${readiness?.entry_ready === true ? "" : `<p>Not entry-ready because: ${escapeHtml((readiness?.reasons as string[] | undefined)?.join("; ") || optimizer.message || "pre-entry validation unavailable")}</p>`}</section>`;
  const longShot = (lineups[0]?.[0]?.long_shot_report ?? {}) as ReportPlayer;
  const longShotHtml = longShot.enabled ? `<section class="lineup"><h2>Long-shot selection</h2><p>${escapeHtml(longShot.note)}</p><p>Ownership evidence: ${escapeHtml(longShot.ownership_status)} · ownership sum: ${longShot.ownership_sum == null ? "Unavailable" : number(longShot.ownership_sum, 1)} · method: ${escapeHtml(String(longShot.method ?? "").replaceAll("_", " "))}.</p></section>` : "";
  const marketAudit = (lineups[0]?.[0]?.projection_market_audit ?? {}) as ReportPlayer;
  const marketResponses = Array.isArray(marketAudit.model_response) ? marketAudit.model_response as ReportPlayer[] : [];
  const marketAuditHtml = marketResponses.length ? `<section class="lineup"><h2>Starter and market sanity check</h2><p>Status: ${escapeHtml(marketAudit.status ?? "Unavailable")}. The model's direct response is compared with a prior-only team-market calibration. The final adjustment adds only the difference, so the model's existing response is counted once. This is an aggregate offense adjustment; pass efficiency, explosive plays, touchdowns, and play volume are not estimated separately.</p><table><thead><tr><th>Team</th><th>Implied total change</th><th>Direct model change</th><th>Final offensive change</th><th>Response</th></tr></thead><tbody>${marketResponses.map((row) => `<tr><td>${escapeHtml(row.team)}</td><td>${number(row.implied_total_delta)}</td><td>${number(row.model_offensive_projection_delta ?? row.offensive_projection_delta)}</td><td>${row.final_offensive_projection_delta == null ? "Unavailable" : number(row.final_offensive_projection_delta)}</td><td>${row.direction_mismatch_before_reconciliation || row.direction_mismatch ? "Direct model: opposite direction" : "Direct model: same direction"}</td></tr>`).join("")}</tbody></table></section>` : "";
  return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>${escapeHtml(title)}</title><style>
  :root{font-family:Inter,system-ui,sans-serif;color:#e8edf4;background:#0b1017}body{max-width:1200px;margin:0 auto;padding:32px}h1,h2{color:#fff}.meta,.muted{color:#9aa8b8}.lineup{border:1px solid #273241;border-radius:12px;padding:20px;margin:24px 0;background:#101720}.metrics{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}.metric{margin-right:14px}table{border-collapse:collapse;width:100%;margin:14px 0}th,td{text-align:left;padding:9px;border-bottom:1px solid #273241;vertical-align:top}th{color:#9aa8b8;background:#121b27}summary{cursor:pointer;font-weight:650;margin:12px 0}li{margin:6px 0}@media print{:root{color:#111;background:#fff}body{padding:0}h1,h2{color:#111}.lineup{break-inside:avoid;background:#fff;border-color:#bbb}th{color:#333;background:#eee}th,td{border-color:#ccc}}
  </style></head><body><h1>${escapeHtml(title)}</h1>${readinessHtml}
  <div class="meta"><p>Job ${escapeHtml(optimizer.job_id)} · ${escapeHtml(optimizer.contest_format)} ${escapeHtml(optimizer.objective)} · ${escapeHtml(optimizer.strategy)}</p>
  <p>${escapeHtml(optimizer.message ?? optimizer.status)}</p><p>Enforce single TE (no double-TE lineups): ${singleTeMetadata}</p><p>Hard exclude players facing: ${escapeHtml(optimizer.exclude_opponent_teams?.join(", ") || "None")}</p><p>${escapeHtml(poolSummary)}</p><p>${escapeHtml(removalSummary)}</p>${manualDecisionDetails}${userExclusionDetails}${removedPlayerDetails}${opportunityDetails}</div>
  ${marketAuditHtml}${historicalCaptainHtml(lineups)}${longShotHtml}${classicSmallFieldHtml(lineups)}${singleEntryReportHtml(lineups, optimizer.enforce_single_te === true)}${threeMaxReportHtml(lineups)}${showdownScenarioHtml(lineups)}${portfolioDiagnosticsHtml(lineups)}${lineups.map(lineupHtml).join("")}<footer class="meta">Generated ${escapeHtml(new Date().toLocaleString())}</footer></body></html>`;
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
