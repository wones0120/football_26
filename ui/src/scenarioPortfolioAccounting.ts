type Row = Record<string, unknown>;

export const SCENARIO_ACCOUNTING_HEADERS = ["Scenario", "Generated", "Baseline screen", "Best baseline selector",
  "Best conditioned selector / P90 proxy", "Constraint survivors", "Selected", "Best rejected", "Primary reason",
  "Portfolio replacement cost", "Maximum soft credit", "Best eligible rejected / cost"];

const numeric = (value: unknown, digits = 2) => value == null || !Number.isFinite(Number(value)) ? "Unavailable" : Number(value).toFixed(digits);

export function scenarioAccountingRows(report: Row): string[][] {
  const definitions = (report.scenario_definitions ?? []) as Row[];
  return ((report.scenario_portfolio_accounting ?? []) as Row[]).map(row => [
    String(definitions.find(d => d.scenario_id === row.scenario_id)?.label ?? row.scenario_id),
    numeric(row.candidates_generated, 0), numeric(row.passing_baseline_quality, 0), numeric(row.best_baseline_selector),
    `${numeric(row.best_conditioned_selector)} / ${numeric(row.best_conditioned_p90_proxy)}`,
    numeric(row.constraint_surviving_candidates, 0), numeric(row.selected_lineups, 0),
    row.best_rejected_rank == null ? "None" : `#${row.best_rejected_rank} · ${row.best_rejected_captain ?? ""}`,
    String(row.primary_rejection_reason ?? "None"), numeric(row.replacement_opportunity_cost), numeric(row.maximum_available_soft_credit),
    row.best_eligible_rejected_rank == null ? "None" : `#${row.best_eligible_rejected_rank} / ${numeric(row.best_eligible_rejected_opportunity_cost)}`,
  ]);
}

export function scenarioAccountingDescription(report: Row): string {
  if (!Array.isArray(report.scenario_portfolio_accounting)) return "This saved run predates scenario portfolio accounting. No new selection has been run.";
  return `Policy: ${report.scenario_selection_policy ?? "baseline"}. Scenario diversity changed physical entries: ${report.scenario_diversity_affected_portfolio ? "yes" : "no"}. ` +
    "The joint 95% baseline mean/P90 screen remains in force. Soft coverage is opt-in and bounded; no scenario quota. " +
    "Constraint survivors can belong to a full maximum-fill portfolio under the existing caps and physical roster uniqueness. " +
    "Replacement cost compares the best full baseline portfolio with the best one containing that candidate; unavailable means it failed the screen or cannot fit. P90 is a sum of marginal ceilings, not a joint percentile.";
}

export function scenarioCreditExplanations(report: Row): string[] {
  const baseline = Number(report.baseline_portfolio_selector ?? 0);
  const selected = Number(report.selected_portfolio_selector ?? baseline);
  return ((report.selected_scenario_credits ?? []) as Row[]).map(row =>
    `Rank #${row.rank} earns ${numeric(row.credit)} selector points of marginal coverage credit: ${row.reason}. ` +
    `Minimum player changes ${numeric(row.minimum_player_changes, 0)}, new winner Captain ${row.new_winner_captain ? "yes" : "no"}, ` +
    `conditional ceiling uplift ${numeric(Number(row.ceiling_uplift_fraction) * 100)}%. ` +
    `Forced baseline portfolio cost ${numeric(row.forced_baseline_portfolio_opportunity_cost)}; total portfolio selector cost ${numeric(baseline - selected)}. ` +
    `Added ranks ${(report.scenario_added_ranks as number[] | undefined)?.join(", ") ?? "unavailable"}; replaced baseline ranks ${(report.ordinary_replaced_ranks as number[] | undefined)?.join(", ") ?? "unavailable"}.`);
}
