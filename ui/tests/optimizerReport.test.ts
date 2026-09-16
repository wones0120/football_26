import assert from "node:assert/strict";
import test from "node:test";

import type { OptimizerResponse } from "../src/api.ts";
import { buildOptimizerReportHtml } from "../src/optimizerReport.ts";

test("builds a readable optimizer report with summaries, players, and controls", () => {
  const optimizer = {
    job_id: "job-123456789",
    status: "completed",
    strategy: "showdown_gpp_captain_informed_v2",
    strategy_config: {},
    contest_format: "showdown",
    objective: "gpp",
    lineage_persisted: true,
    message: "Optimizer completed",
    player_pool: {
      initial_count: 39,
      raw_pool_count: 39,
      opportunity_eligible_count: 26,
      optimizer_eligible_count: 26,
      eligible_count: 26,
      included_count: 26,
      excluded_count: 13,
      removal_reason_counts: { showdown_cheap_punt_no_opportunity: 13 },
      warning_player_count: 2,
      rows: [{
        player_id: "punt-1",
        player_name: "Low Opportunity Punt",
        player_team: "BUF",
        position: "WR",
        salary: 200,
        projection: 1,
        p90: 4,
        included: false,
        removal_stage: "opportunity_gate",
        exclusion_reasons: ["showdown_cheap_punt_no_opportunity"],
      }],
    },
    results: [[
      {
        player_id: "p1",
        player_name: "Amon-Ra <St. Brown>",
        roster_position: "CPT",
        position: "WR",
        player_team: "DET",
        salary: 15600,
        projection: 26.35,
        p90: 28.99,
        ownership: 18.5,
        lineup_duplication_risk: {
          metric_id: "slot_ownership_log_product_v1",
          ownership_available: true,
          log_probability: -8.25,
          probability_product: 0.00026,
          relative_chalk_score: 72.5,
          optimization_weight: 0,
        },
        portfolio_exposure_report: {
          requested_lineups: 5,
          generated_lineups: 4,
          underfilled: true,
          configured_captain_cap: 0.4,
          captain_maximum_appearances: 2,
          rows: [{
            player_name: "Greg Dortch",
            scope: "player",
            exposure_class: "cheap_punt",
            configured_cap: 0.4,
            requested_lineups: 5,
            maximum_allowed_appearances: 2,
            generated_lineups: 4,
            actual_appearances: 2,
            final_generated_portfolio_exposure: 0.5,
            cap_status: "PASS",
          }],
        },
        portfolio_underfill_diagnostics: {
          attempted_lineup_number: 5,
          counts_may_overlap: true,
          quality_floors_relaxed: false,
          reason_counts: { failed_p90_floor: 1, exposure_constraint: 1 },
        },
        captain_diversification_report: {
          enabled: true,
          minimum_distinct_target: 3,
          both_teams_target: true,
          targets_achieved: true,
          qualifying_captain_candidates: [
            { player_name: "Amon-Ra St. Brown", team: "DET", lineup_mean: 94.23, lineup_p90: 159.46 },
            { player_name: "Khalil Shakir", team: "BUF", lineup_mean: 87.38, lineup_p90: 153.03 },
          ],
          quality_rejected_captain_candidates: [
            { player_name: "Jacob Saylors", team: "BUF", failed_mean_floor: true, failed_p90_floor: true },
          ],
          final_captain_exposures: [
            { player_name: "Amon-Ra St. Brown", team: "DET", appearances: 2, exposure: 0.5 },
            { player_name: "Khalil Shakir", team: "BUF", appearances: 1, exposure: 0.25 },
          ],
          selection_diagnostics: {
            construction_mode: "sequential_greedy",
            explanation: "The optimizer solves one lineup at a time.",
            selected_captain_quality: [{
              player_name: "DJ Moore",
              team: "BUF",
              selected_lineups: [
                {
                  selection_number: 1, lineup_number: 7,
                  lineup_mean: 86.38, lineup_p90: 152.04,
                  mean_delta_from_first_selected: 0, p90_delta_from_first_selected: 0,
                  mean_delta_from_standalone_best: -1.95, p90_delta_from_standalone_best: -1.52,
                  standalone_best_exposure_blockers: [],
                },
                {
                  selection_number: 2, lineup_number: 8,
                  lineup_mean: 83.97, lineup_p90: 149.20,
                  mean_delta_from_first_selected: -2.41, p90_delta_from_first_selected: -2.84,
                  mean_delta_from_standalone_best: -4.36, p90_delta_from_standalone_best: -4.36,
                  standalone_best_exposure_blockers: [{ player_name: "Sam LaPorta" }],
                },
              ],
            }],
            unselected_qualifying_captains: [{
              player_name: "Jared Goff",
              team: "DET",
              primary_reason: "lower_solver_objective_at_available_sequential_step",
              standalone_best: { lineup_mean: 94.52, lineup_p90: 159.30, solver_objective_value: 158.87 },
              best_available_sequential_step: {
                lineup_number: 8, lineup_mean: 94.01, lineup_p90: 157.40,
                solver_objective_value: 156.67,
                selected_captain_player_name: "DJ Moore",
                selected_solver_objective_value: 158.37,
                solver_objective_deficit: -1.70,
              },
            }],
          },
        },
        lineup_ceiling_summary: { value: 159.46 },
        lineup_correlation_summary: {
          total_adjustment: 4.57,
          construction_label: "3-3 · WR Captain",
          triggered_rules: [{ reason_code: "same_team", description: "Same-team pairing", score_contribution: 1.5 }],
        },
        lineup_control_comparison: {
          selection_changed: false,
          selection_effect: "same_selection",
          selected_only: [],
          control_only: [],
          control_lineup: [],
          scored_metrics: { mean: 94.23 },
          control_metrics: { mean: 94.23 },
          deltas_scored_minus_control: { mean: 0 },
          base_objective_opportunity_cost: 0,
          rule_contributions: [],
        },
      },
      { player_id: "p2", player_name: "Josh Allen", roster_position: "FLEX", position: "QB", player_team: "BUF", salary: 11400, projection: 20, p90: 30, ownership: 42.25 },
    ]],
  } satisfies OptimizerResponse;

  const html = buildOptimizerReportHtml(optimizer, { season: 2026, week: 2, slate: "THURSDAY_NIGHT" });

  assert.match(html, /2026 Week 2 THURSDAY NIGHT Optimizer Report/);
  assert.match(html, /Individual Ceiling Sum: 159\.46/);
  assert.match(html, /Compare with rules disabled · Same selection/);
  assert.match(html, /Correlation rules \(1\)/);
  assert.match(html, /CPT · WR/);
  assert.match(html, /Ownership: 60\.75/);
  assert.match(html, /Relative chalk: 72\.5\/100/);
  assert.match(html, /Caps use 5 requested lineups; final percentages use 4 generated lineups/);
  assert.match(html, /Requested\/configured CPT max:<\/strong> 40% · effective maximum 2 appearance\(s\) across 5 requested lineups/);
  assert.match(html, /Greg Dortch/);
  assert.match(html, /40%/);
  assert.match(html, /2 of 5 requested/);
  assert.match(html, /2 of 4 generated/);
  assert.match(html, /50\.0%/);
  assert.match(html, /PASS — 2 of 5 requested slots used/);
  assert.match(html, /Under-fill rejection diagnostics/);
  assert.match(html, /failed p90 floor: 1/);
  assert.match(html, /Captain diversification/);
  assert.match(html, /at least 3 distinct qualifying Captains with both teams represented/);
  assert.match(html, /Khalil Shakir \(BUF\)/);
  assert.match(html, /Rejected by quality floors \(1\)/);
  assert.match(html, /Portfolio construction:<\/strong> sequential greedy/);
  assert.match(html, /DJ Moore \(BUF\)<\/td><td>CPT #2/);
  assert.match(html, /-2\.41/);
  assert.match(html, /-2\.84/);
  assert.match(html, /Sam LaPorta/);
  assert.match(html, /Jared Goff \(DET\)/);
  assert.match(html, /lower solver objective at available sequential step/);
  assert.match(html, /Raw pool: 39 → opportunity eligible: 26 → optimizer eligible: 26/);
  assert.match(html, /showdown cheap punt no opportunity \(13\)/);
  assert.match(html, /Opportunity removals \(1\)/);
  assert.match(html, /Low Opportunity Punt · showdown cheap punt no opportunity/);
  assert.match(html, /<th>Ownership<\/th>/);
  assert.match(html, /Leverage sum<\/td><td>—/);
  assert.match(html, /Amon-Ra &lt;St\. Brown&gt;/);
  assert.doesNotMatch(html, /Amon-Ra <St\. Brown>/);
});

test("single-entry report explains A/B/A and featured alternatives", () => {
  const candidate = {
    rank: 2, captain: "B <Captain>", mean: 94.5, p90: 159.3,
    relative_chalk: 59.1, game_script: { label: "Shootout" },
    shared_players_with_a: 5, overlap_percentage_vs_a: 83.333,
    jaccard_similarity_vs_a: 5 / 7, quality_loss_vs_a: 0.013,
    diversification_benefit_vs_a: 0.0175,
    players: [{ slot: "CPT", name: "B <Captain>" }],
  };
  const comparison = {
    structure: "A / B / A", candidate_ranks: [1, 2, 1],
    quality_loss_total: 0.013, diversification_credit_total: 0.0175,
    heuristic_delta_vs_aaa: 0.0045,
  };
  const optimizer = {
    job_id: "single-entry-run", status: "completed",
    strategy: "showdown_single_entry_portfolio", strategy_config: {},
    contest_format: "showdown", objective: "gpp", lineage_persisted: true,
    results: [[{
      player_id: "captain", name: "A", roster_position: "CPT",
      position: "QB", player_team: "DET", salary: 12000,
      projection: 20, p90: 35,
      single_entry_report: {
        recommended_structure: "A / B / A", material_player_change_minimum: 2,
        selected_portfolio_comparison: comparison,
        assignments: [{ contest: 1 }, { contest: 2 }, { contest: 3 }],
        portfolio_comparisons: {
          aaa: { structure: "A / A / A", candidate_ranks: [1, 1, 1], quality_loss_total: 0, diversification_credit_total: 0, heuristic_delta_vs_aaa: 0 },
          best_one_alternate: comparison,
          best_two_alternates: { structure: "A / B / C", candidate_ranks: [1, 2, 3], quality_loss_total: 0.04, diversification_credit_total: 0.02, heuristic_delta_vs_aaa: -0.02 },
        },
        top_alternates: { different_captain_only: candidate, different_captain_material_players: null, different_game_script: null },
        candidates: [candidate], selected_candidates: [candidate],
      },
    }]],
  } as OptimizerResponse;
  const html = buildOptimizerReportHtml(optimizer, { season: 2026, week: 2, slate: "THURSDAY_NIGHT" });
  assert.match(html, /Recommended portfolio: A \/ B \/ A/);
  assert.match(html, /The best A \/ B \/ C scores/);
  assert.match(html, /Different Captain, same six players/);
  assert.match(html, /Jaccard/);
  assert.match(html, /B &lt;Captain&gt;/);
  assert.doesNotMatch(html, /B <Captain>/);
});

test("one selected contest omits diversification-combination language", () => {
  const optimizer = {
    job_id: "one-contest", status: "completed",
    strategy: "showdown_single_entry_portfolio", strategy_config: {},
    contest_format: "showdown", objective: "gpp", lineage_persisted: true,
    results: [[{
      player_id: "captain", name: "A", roster_position: "CPT",
      position: "QB", player_team: "DET", salary: 12000,
      projection: 20, p90: 35,
      single_entry_report: {
        recommended_structure: "A", assignments: [{ contest: 1 }],
        selected_portfolio_comparison: { structure: "A", candidate_ranks: [1] },
        portfolio_comparisons: {}, top_alternates: {},
        candidates: [], selected_candidates: [],
        contest_selection: {
          mode: "auto", selected_count: 1, available_count: 1, total_entry_fees: 5,
          note: "Payout proxy", selection_reason: "One contest has the highest value.",
          search_method: "exhaustive_subsets", evaluated_subsets: 1,
          selected_contest_ids: ["123"],
          count_comparisons: [{ contest_count: 1, contest_ids: ["123"], total_entry_fees: 5, heuristic_value: .25, independent_rank_proxy: .25, shared_percentile_proxy: .25 }],
          ranked_contests: [{ contest_id: "123", name: "Test contest", contest_score: .25, entry_fee: 5, capacity: 100, economics: {
            paid_percentage: .25, minimum_cash: 8, minimum_cash_multiple: 1.6,
            payout_at_field_percentiles: { "1": 50, "5": 8, "10": 8, "20": 8 }, median_paid_payout: 8,
            first_place_share: .1, top_10_share: .4, payout_flatness: .6, full_field_rake: .1,
            current_effective_rake: null,
          } }],
        },
      },
    }]],
  } as OptimizerResponse;
  const html = buildOptimizerReportHtml(optimizer, { season: 2026, week: 2, slate: "THURSDAY_NIGHT" });
  assert.match(html, /One contest selected/);
  assert.match(html, /Best subset/);
  assert.match(html, /Min cash/);
  assert.doesNotMatch(html, /A \/ A \/ A/);
  assert.doesNotMatch(html, /Diversification benefit/);
  assert.doesNotMatch(html, /candidate combinations with repetition/);
});
