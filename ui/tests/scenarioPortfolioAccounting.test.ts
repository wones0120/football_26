import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { scenarioPortfolioAccountingHtml } from "../src/optimizerReport.ts";
import { scenarioAccountingDescription, scenarioAccountingRows, scenarioCreditExplanations } from "../src/scenarioPortfolioAccounting.ts";

test("old reports do not invent current accounting", () => {
  assert.deepEqual(scenarioAccountingRows({}), []);
  assert.match(scenarioAccountingDescription({}), /predates/);
});

test("unavailable conditional evidence and infeasible costs remain unavailable", () => {
  const report = { scenario_selection_policy: "baseline", scenario_diversity_affected_portfolio: false,
    scenario_definitions: [{ scenario_id: "a_win", label: "A decisive win" }],
    scenario_portfolio_accounting: [{ scenario_id: "a_win", candidates_generated: 20, passing_baseline_quality: 2,
      best_baseline_selector: 174, best_conditioned_selector: null, best_conditioned_p90_proxy: 154,
      constraint_surviving_candidates: 1, selected_lineups: 0, best_rejected_rank: 7, best_rejected_captain: "WR",
      primary_rejection_reason: "Quality floor", replacement_opportunity_cost: null, maximum_available_soft_credit: 0 }] };
  const row = scenarioAccountingRows(report)[0];
  assert.equal(row[0], "A decisive win");
  assert.equal(row[4], "Unavailable / 154.00");
  assert.equal(row[9], "Unavailable");
  assert.equal(row[10], "0.00");
  assert.match(scenarioAccountingDescription(report), /physical entries: no/);
});

test("credit explanation includes the actual baseline opportunity cost", () => {
  const explanations = scenarioCreditExplanations({ baseline_portfolio_selector: 199, selected_portfolio_selector: 198.5,
    selected_scenario_credits: [{ rank: 3, credit: 1.99, reason: "Differentiated winner construction", minimum_player_changes: 4,
      new_winner_captain: true, ceiling_uplift_fraction: .1, forced_baseline_portfolio_opportunity_cost: .5 }] });
  assert.match(explanations[0], /1.99 selector points/);
  assert.match(explanations[0], /portfolio selector cost 0.50/);
});

test("portfolio scenario policies remain research only and are absent from normal runs", () => {
  const source = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(source, /soft_scenario_diversity:|require_scenario_diversity:|setSoftScenarioDiversity/);
  assert.match(source, /<ScenarioPortfolioAccounting/);
});

test("export escapes source labels and preserves zero cost separately from missing", () => {
  const html = scenarioPortfolioAccountingHtml({ scenario_portfolio_accounting: [
    { scenario_id: "<script>alert(1)</script>", replacement_opportunity_cost: 0, primary_rejection_reason: "Duplicate" }] });
  assert.ok(!html.includes("<script>"));
  assert.match(html, /&lt;script&gt;/);
  assert.match(html, /<td>0.00<\/td>/);
});
