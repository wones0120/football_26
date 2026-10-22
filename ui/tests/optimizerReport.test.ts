import assert from "node:assert/strict";
import test from "node:test";

import type { OptimizerResponse } from "../src/api.ts";
import { buildOptimizerReportHtml } from "../src/optimizerReport.ts";

for (const contest_format of ["classic", "showdown"] as const) {
  test(`${contest_format} report separates shared historical workload, proxies and unavailable forecasts at every salary`, () => {
    const packet = {contract_id: "workload_evidence_v1", status: "supported_history",
      historical: {snap_share_mean_3: {value: 0.497, status: "observed"}, targets_mean_3: {value: 0, status: "observed"},
        carries_mean_3: {value: null, status: "unavailable"}},
      derived_proxies: {projected_targets: {value: 5.165, status: "present"}},
      explicit_pregame: {pregame_expected_targets: {value: null, status: "unavailable"}},
      historical_coverage: {opportunity_history_window: null},
      lineage: {pregame_context_run_id: "source-run", pregame_context_observed_at: "2026-10-10T11:00:00Z"}};
    const optimizer = {job_id: "evidence", status: "completed", contest_format, objective: "cash", enforce_single_te: false, results: [],
      player_pool: {rows: [{player_id: "cheap", player_name: "Cheap <player>", salary: 1600, workload_evidence: packet},
        {player_id: "expensive", player_name: "Expensive player", salary: 9000, workload_evidence: packet}]}} as unknown as OptimizerResponse;
    const html = buildOptimizerReportHtml(optimizer, {season: 2026, week: 5, slate: "MAIN"});
    assert.match(html, /Shared workload evidence \(2 players\)/);
    assert.match(html, /Cheap &lt;player&gt;/);
    assert.match(html, /Expensive player/);
    assert.match(html, /0 \(observed\)/);
    assert.match(html, /5\.165 \(present\)/);
    assert.match(html, /Unavailable \(unavailable\)/);
    assert.match(html, /source-run/);
    assert.match(html, /2026-10-10T11:00:00Z/);
    assert.match(html, /Availability and depth alone do not establish workload/);
  });
}

test("v2 workload report preserves original observations separately from allocated counts", () => {
  const packet = {contract_id:"workload_evidence_v2",status:"supported_history",
    historical:{carries_mean_3:{value:17,status:"observed",source_field:"pregame_base_carries_mean_3"},
      targets_mean_3:{value:null,status:"original_history_unavailable"}},
    derived_proxies:{projected_carries:{value:10.76,status:"present"}},explicit_pregame:{}};
  const optimizer = {job_id:"typed-history",status:"completed",contest_format:"classic",objective:"gpp",results:[],
    player_pool:{rows:[{player_id:"p",player_name:"Synthetic RB",workload_evidence:packet}]}} as unknown as OptimizerResponse;
  const before=JSON.stringify(optimizer);
  const html=buildOptimizerReportHtml(optimizer,{season:2099,week:1,slate:"SYNTHETIC"});
  assert.match(html,/17 \(observed\)/);
  assert.match(html,/10\.76 \(present\)/);
  assert.match(html,/Unavailable \(original_history_unavailable\)/);
  assert.equal(JSON.stringify(optimizer),before);
});

test("Showdown exported report uses saved Captain position and effective QB policy", () => {
  const optimizer = {
    job_id: "captain-position", status: "completed", strategy: "showdown_cash_baseline_v1",
    contest_format: "showdown", objective: "cash", enforce_single_te: false, results: [[{
      player_id: "wr", name: "Receiver", roster_position: "CPT", position: "WR", salary: 9000,
      showdown_captain_preferences: {allowed_positions: ["WR"]},
      showdown_qb_preferences: {allow_qb_captain: false, requested_portfolio_size: 1},
    }]],
  } as unknown as OptimizerResponse;
  const html = buildOptimizerReportHtml(optimizer, {season: 2026, week: 4, slate: "THURSDAY_NIGHT"});
  assert.match(html, /Captain positions: WR only/);
  assert.match(html, /QB Captain allowed: No/);
  assert.match(html, /Effective QB-Captain lineup limit: 0/);
});

test("Showdown exported report discloses named Captain exceptions under a position restriction", () => {
  const optimizer = {
    job_id: "named-qb", status: "completed", strategy: "showdown_gpp_portfolio_v3", enforce_single_te: false,
    contest_format: "showdown", objective: "gpp", results: [[{
      name: "Named QB", player_id: "qb", position: "QB", salary: 15000, is_captain: true,
      showdown_qb_preferences: {allow_qb_captain: false, named_captain_position_exception_ids: ["qb"]},
      showdown_captain_preferences: {allowed_positions: ["WR", "RB"], named_position_exception_ids: ["qb"]},
    }]],
  } as unknown as OptimizerResponse;
  const html = buildOptimizerReportHtml(optimizer, {season: 2026, week: 6, slate: "SUNDAY_MORNING"});
  assert.match(html, /QB Captain allowed: Named exceptions may qualify/);
  assert.match(html, /Effective QB-Captain lineup limit: 1 if a named QB is eligible/);
  assert.match(html, /WR, RB only; 1 named position exception/);
});

test("Classic failure report leads with gate diagnostics and suppresses production lineups", () => {
  const optimizer = {
    job_id: "blocked", status: "failed", strategy: "classic_large_gpp_v1", contest_format: "classic", objective: "gpp",
    results: [[{name: "Must not render", player_id: "p", salary: 5000}]],
    data_readiness: {status: "NOT_READY", solver_called: false, override_used: false,
      reason_codes: ["market_game_evidence_missing"], required_sources: {market: {status: "NOT_READY"}},
      market_coverage: {covered_game_ids: [], required_game_ids: ["a", "b"]},
      optional_sources: {weather: {status: "NOT_REQUIRED_BY_CURRENT_MODEL", required: false}}},
  } as unknown as OptimizerResponse;
  const html = buildOptimizerReportHtml(optimizer, {season: 2026, week: 5, slate: "SUNDAY_MAIN"});
  assert.match(html, /Generation evidence: NOT_READY/);
  assert.match(html, /Solver called: no · Override used: no/);
  assert.match(html, /0\/2 games/);
  assert.match(html, /market_game_evidence_missing/);
  assert.match(html, /no · NOT_REQUIRED_BY_CURRENT_MODEL/);
  assert.doesNotMatch(html, /<h2>Lineup 1<\/h2>|Must not render/);
});

test("Classic explicit preview cannot imply entry-ready and renders actual objective contribution", () => {
  const optimizer = {
    job_id: "preview", status: "completed", strategy: "classic_large_gpp_v1", contest_format: "classic", objective: "gpp",
    data_readiness: {status: "DEVELOPMENT_PREVIEW", solver_called: true, override_used: true, reason_codes: ["salary_pool_stale"]},
    entry_readiness: {status: "READY", entry_ready: true, current_entry_clearance: "VERIFIED", checks: {Test: {status: "PASS"}}},
    results: [[{name: "Player", player_id: "p", salary: 5000, projection: 10, p90: 15,
      lineup_correlation_summary: {total_adjustment: 0},
      lineup_objective_components: {projection: 1, ceiling: 2, leverage: .1, context: .2, correlation: .375,
        total: 3.675, solver_objective: 3.675, reconciliation_delta: 0, weights: {correlation: .15}}}]],
  } as unknown as OptimizerResponse;
  const html = buildOptimizerReportHtml(optimizer, {season: 2026, week: 5, slate: "SUNDAY_MAIN"});
  assert.match(html, /DEVELOPMENT_PREVIEW — explicit incomplete-evidence override/);
  assert.match(html, /Solver called: yes · Override used: yes/);
  assert.match(html, /ENTRY READY: NO/);
  assert.match(html, /Actual solver objective components/);
  assert.match(html, /<td>correlation<\/td><td>0\.375000<\/td>/);
  assert.match(html, /Correlation: \+0\.38/);
  assert.match(html, /solver_objective/);
});

test("Showdown role audit preserves depth, uncertainty and excluded kicker evidence", () => {
  const optimizer = {
    job_id: "roles", status: "completed", strategy: "showdown_gpp_portfolio_v3",
    contest_format: "showdown", objective: "gpp", enforce_single_te: false, results: [],
    entry_readiness: {entry_ready: false, status: "BLOCKED", checks: {},
      current_slate_role_availability_audit: {players: [
        {player: "Promoted <RB>", team: "NO", position: "RB", role_availability: "rostered",
          expected_depth_role: "expected_starter", role_starter_evidence: "Coach & chart",
          role_change: "Starter removed", projection_before: 7.44, projection_change: 8.77,
          optimizer_eligible: true, role_confidence: "medium", role_resolution_warning: "Workload unresolved"},
        {player: "Backup kicker", team: "NO", position: "K", role_availability: "unavailable",
          expected_depth_role: "expected_backup", projection: 0, optimizer_eligible: false,
          role_confidence: "high"},
      ]}},
  } as unknown as OptimizerResponse;
  const html = buildOptimizerReportHtml(optimizer, {season: 2026, week: 4, slate: "MONDAY_NIGHT"});
  const section = html.split("CURRENT SLATE ROLE AND AVAILABILITY AUDIT")[1].split("</section>")[0];
  assert.equal((section.match(/<th>/g) ?? []).length, 10);
  assert.match(section, /Promoted &lt;RB&gt;/);
  assert.match(section, /Coach &amp; chart/);
  assert.match(section, /7\.44 → 8\.77/);
  assert.match(section, /expected_starter/);
  assert.match(section, /expected_backup/);
  assert.match(section, /Excluded/);
  assert.match(section, /medium · Workload unresolved/);
  assert.match(section, /overflow-x:auto/);
  assert.match(html, /ENTRY READY: NO/);
});

test("Showdown report displays scenario coverage and baseline versus conditioned player values", () => {
  const optimizer = {
    job_id: "scenario-audit", status: "completed", strategy: "showdown_gpp_portfolio_v3",
    strategy_config: {}, contest_format: "showdown", objective: "gpp",
    enforce_single_te: false,
    results: [[{
      player_id: "a-rb", name: "A RB", position: "RB", roster_position: "CPT",
      player_team: "AAA", salary: 12000, projection: 18, p90: 30,
      baseline_projection: 15, baseline_p90: 26,
      showdown_scenario_id: "team_a_decisive_win",
      showdown_scenario: {scenario_id: "team_a_decisive_win", label: "AAA DECISIVE WIN",
        conditioned_winner: "AAA", decisive_margin_threshold: 14},
      showdown_scenario_adjustment: {reason: "winning-team rush-volume increase"},
      showdown_candidate_source: "captain_family",
      showdown_selection_diagnostic: {global_candidate_rank: 3, mean_loss: 1,
        p90_loss: 2, selector_loss: 0.5, scenario_diversity_changed_selection: true,
        selection_reason: "scenario diversity with quality and exposure constraints"},
      captain_family_coverage_report: {
        candidate_count: 3, quality_eligible_count: 3, quality_fraction: 0.95,
        scenario_generation_status: "complete", require_scenario_diversity: true,
        ordinary_selected_ranks: [1],
        scenario_definitions: [
          {scenario_id: "baseline", label: "BASELINE / MARKET SCRIPT", adjustment_method: "market_margin_role_conditioning_v1"},
          {scenario_id: "team_a_decisive_win", label: "AAA DECISIVE WIN", conditioned_winner: "AAA", decisive_margin_threshold: 14},
          {scenario_id: "team_b_decisive_win", label: "BBB DECISIVE WIN", conditioned_winner: "BBB", decisive_margin_threshold: 14},
        ],
        scenario_family_coverage: [
          {scenario_id: "baseline", candidate_count: 1, best_rank: 1, best_mean: 70, best_p90: 130, best_selector: 100, best_captain: "B QB", best_team_split: "AAA 3 / BBB 3", best_salary: 49000, selected: false, reason: "selector tradeoff"},
          {scenario_id: "team_a_decisive_win", candidate_count: 1, best_rank: 3, best_mean: 69, best_p90: 129, best_selector: 99, best_captain: "A RB", best_team_split: "AAA 4 / BBB 2", best_salary: 48000, selected: true, reason: "selected"},
        ],
        ranked_metrics: [{rank: 3, scenario_id: "team_a_decisive_win", candidate_source: "captain_family",
          captain_name: "A RB", team_split: "AAA 4 / BBB 2", salary: 48000,
          baseline_mean: 65, mean: 69, baseline_p90: 124, p90: 129,
          selector: 99, quality_eligible: true}],
      },
    }]],
  } as OptimizerResponse;
  const html = buildOptimizerReportHtml(optimizer, {season: 2026, week: 3, slate: "MONDAY_NIGHT"});
  assert.match(html, /SHOWDOWN GAME-SCRIPT SCENARIOS/);
  assert.match(html, /AAA wins by 14\+/);
  assert.match(html, /Scenario diversity selected a lower-ranked lineup: yes/);
  assert.match(html, /winning-team rush-volume increase/);
  assert.match(html, /Baseline lineup mean 15\.00/);
  assert.match(html, /captain_family/);
});

test("Showdown report exposes saved market response and team-count context", () => {
  const optimizer = {
    job_id: "market-audit", status: "completed", strategy: "showdown_gpp_portfolio_v3",
    strategy_config: {}, contest_format: "showdown", objective: "gpp",
    enforce_single_te: false,
    results: [[{
      player_id: "qb", name: "Quarterback", position: "QB", roster_position: "CPT",
      player_team: "PHI", salary: 12000, projection: 20, p90: 35,
      qb_correlation_multiplier: 0.53,
      projection_market_audit: {
        status: "review_required_direction_mismatch",
        model_response: [{team: "CHI", implied_total_delta: -1.75,
          offensive_projection_delta: 0.23, direction_mismatch: true}],
      },
      captain_family_coverage_report: {
        candidate_count: 120, quality_eligible_count: 60,
        quality_fraction: 0.95, ownership_selection_status: "Partial",
        source_coverage: {"script:PHI_4_2_control_rb": 1},
        family_rows: [{captain_name: "Quarterback", rank: 1, selected: true}],
      },
      showdown_game_environment: {
        team_counts: "PHI 4 / CHI 2", game_total: 41.5,
        market_source: "public_market", market_observed_at: "2026-09-28T19:07:12Z",
        explanation: "Favorite-led construction.",
        teams: [{team: "PHI", players: 4, spread: -3.5, implied_total: 22.5,
          projected_mean: 70, selector_contribution: 78}],
      },
    }]],
  } as OptimizerResponse;
  const html = buildOptimizerReportHtml(optimizer, {season: 2026, week: 3, slate: "MONDAY_NIGHT"});
  assert.match(html, /Direct model: opposite direction/);
  assert.match(html, /PHI 4 \/ CHI 2/);
  assert.match(html, /QB correlation reward factors/);
  assert.match(html, /public_market/);
  assert.match(html, /PHI 4 2 control rb/);
});

test("Showdown report displays measured Captain rates and shadow-only QB archetype status", () => {
  const optimizer = {
    job_id: "captain-history", status: "completed", strategy: "showdown_gpp_portfolio_v3",
    strategy_config: {}, contest_format: "showdown", objective: "gpp",
    enforce_single_te: false,
    results: [[{
      player_id: "qb", name: "Rush QB", position: "QB", roster_position: "CPT",
      player_team: "AAA", salary: 12000, projection: 20, p90: 35,
      historical_captain_optimality: {
        slate_count: 43, positions: [{label: "QB", optimal_count: 11,
          eligible_opportunities: 290, slate_optimal_share: 11 / 43,
          optimal_rate: 11 / 290}],
        qb_archetype_thresholds_recent_carries: [1.67, 3.33],
        actual_source_counts: {raw_nfl_weekly_stat: 1000, unavailable: 1200},
        excluded_games: [{season: 2026, week: 3, slate: "MONDAY_NIGHT",
          reason: "final_actual_usage_incomplete"}],
        qb_archetypes: [{label: "Pocket-oriented", optimal_count: 0,
          eligible_opportunities: 105, optimal_rate: 0, wilson_95: [0, 0.035],
          reliability: "limited"}],
        starter_identification: {identified: 72, team_opportunities: 86,
          complete_two_team_games: 30, rule: "Pregame evidence or clear salary and prior volume",
          methods: {salary_and_prior_pass_volume_inferred: 68, pregame_inferred: 4}},
        starter_qb_archetypes: [{label: "Pocket-oriented", optimal_count: 0,
          eligible_opportunities: 16, optimal_rate: 0, wilson_95: [0, 0.194],
          reliability: "limited"}],
        starter_qb_game_shares: [{label: "Either identified starting QB", optimal_count: 8,
          eligible_games: 30, optimal_game_share: 8 / 30, wilson_95: [0.142, 0.444],
          reliability: "limited"}],
        qb_buckets: {recent_carries: [{label: "0–2", optimal_count: 0,
          eligible_opportunities: 105, optimal_rate: 0}]},
        starter_qb_buckets: {recent_carries: [{label: "0–2", optimal_count: 0,
          eligible_opportunities: 16, optimal_rate: 0, wilson_95: [0, 0.194],
          reliability: "limited"}]},
        current_qbs: [{qb: "Rush QB", team: "AAA", archetype: "High-rush / goal-line unverified",
          recent_carries: 5.5, recent_carries_source: "carries_mean_3",
          historical_archetype_rate: 0.08, historical_archetype_count: 6,
          historical_archetype_opportunities: 75, historical_rush_bucket: "4–6",
          historical_rush_bucket_rate: 0.1, goal_line_role: "unavailable",
          historical_starter_archetype_rate: 0.154,
          historical_starter_archetype_count: 6,
          historical_starter_archetype_opportunities: 39,
          historical_starter_reliability: "limited",
          existing_position_prior_multiplier: 1.08, archetype_prior_adjustment: 0,
          best_family_rank: 4, best_family_mean: 72, best_family_p90: 135,
          selected: true}],
        prior_application: {status: "shadow_only", reason: "Insufficient training events"},
        shadow_qb_captain: {status: "diagnostic_unvalidated", formula: "Saved candidates only"},
        qb_statistical_validation: {status: "exploratory_insufficient_training_events",
          training_period: "2024", training_optimal_qbs: 3, test_optimal_qbs: 8,
          base: {holdout_brier: 0.049}, with_recent_carries: {holdout_brier: 0.0489}},
        historical_cpt_ownership: {status: "unavailable"},
        feature_coverage: {expected_carries: {observed: 237, eligible_qbs: 290}},
        unavailable_features: ["rushing TD expectation"],
      },
    }]],
  } as OptimizerResponse;
  const html = buildOptimizerReportHtml(optimizer, {season: 2026, week: 3, slate: "MONDAY_NIGHT"});
  assert.match(html, /Historical Captain Optimality/);
  assert.match(html, /Pocket-oriented/);
  assert.match(html, /0\.0%/);
  assert.match(html, /Pregame-identified starter QB archetypes/);
  assert.match(html, /72\/86/);
  assert.match(html, /salary_and_prior_pass_volume_inferred 68/);
  assert.match(html, /2026 W3 MONDAY_NIGHT: final_actual_usage_incomplete/);
  assert.match(html, /26\.7%/);
  assert.match(html, /diagnostic_unvalidated/);
  assert.match(html, /Rush QB/);
  assert.match(html, /shadow_only/);
  assert.match(html, /Historical CPT field ownership: unavailable/);
});

test("long-shot report is explicitly labeled and discloses ownership evidence", () => {
  const optimizer: OptimizerResponse = {
    job_id: "long-shot", status: "completed", strategy: "classic_large_gpp_v1",
    strategy_config: {}, contest_format: "classic", objective: "gpp",
    lineage_persisted: true, long_shot_mode: true,
    results: [[{
      player_id: "qb", name: "Contrarian QB", position: "QB", player_team: "AAA",
      salary: 6000, projection: 18, p90: 30, ownership: 4,
      lineup_variant: "long_shot",
      long_shot_report: {
        enabled: true, ownership_status: "available", ownership_sum: 72.5,
        method: "classic_low_ownership_leverage_objective",
        note: "Football projections are unchanged.",
      },
    }]],
  };

  const html = buildOptimizerReportHtml(optimizer, { season: 2026, week: 2, slate: "SUNDAY_MAIN" });

  assert.match(html, /Long-shot selection/);
  assert.match(html, /Long-shot lineup/);
  assert.match(html, /ownership sum: 72\.5/);
  assert.match(html, /Football projections are unchanged/);
});

test("Classic small-field report exposes candidate scoring and stack diagnostics", () => {
  const candidate = {
    rank: 1, roster: [{ name: "QB One", position: "QB" }], salary: 49900,
    mean: 132.4, p90: 211.5, ownership_sum: 125, relative_chalk: 44,
    qb: { name: "QB One", label: "moderate rushing QB", basis: "expected carries" },
    stack: { type: "QB+2+bring-back", bring_backs: [{ name: "Opponent WR" }],
      game_stack_size: 4, game_stack_salary: 23000, game_stack_ownership: 65 },
    primary_game: "AAA–BBB", game_environment: { label: "high-total competitive", game_total: 52 },
    correlation_positive: 1.2, correlation_negative: -0.2,
    objective_score: 4.5, base_solver: 4.5,
    components: { mean: 2, p90: 2, context: .2, leverage: .1, qb_stack: .3,
      bring_back: .1, game_environment: 0, correlation: 0, ownership_chalk: 0,
      duplication: 0, penalties: -.2, other_residual: 0 },
    rbs: [], pass_catchers: { salary: 21000, high_owned_count: 1,
      low_owned_count: 1, one_offs: [], te_in_qb_stack: true, flex_position: "WR" },
    cheap_skill_opportunity: [], correlation_rules: [],
    rb_dst_football_sanity_flags: [{ kind: "same_team_rb_dst", key: "rb_dst:rb:dst",
      label: "RB One + AAA DST: underdog by at least 6", why: "Same-team RB and DST",
      status: "informational", production_impacting: false, recent_carries: 10,
      recent_targets: 4, receiving_role_strength: .5,
      strongest_candidate_without_flag: { rank: 2, mean_cost: 1, p90_cost: 2,
        selector_cost: .1 } }],
    football_sanity: { script: "AAA passing through two stack partners", driving_players: [],
      cheap_players: [], omitted_central_players: [{ name: "Central WR", team: "AAA",
        explanation: "selection tradeoff unresolved", mean: 18, p90: 29, salary: 7500,
        candidate_count: 12, candidate_total: 120, selected_count: 0, selected_total: 1 }],
      role_projection_disagreements: [], flags: [] },
    mean_loss_vs_best: 0, p90_loss_vs_best: 0,
    chalk_improvement_vs_best_quality: 0, ownership_objective_gain_vs_best_quality: 0,
  };
  const lineup = [{ player_id: "qb", name: "QB One", position: "QB", salary: 6000,
    projection: 20, p90: 30, player_team: "AAA",
    classic_small_field_report: { candidate_count: 120, requested_candidate_count: 120,
      policy_contract: {contract_id: "classic_requested_effective_policy_v1", requested: {portfolio_constraints: {max_lineup_overlap: 4}}, effective: {max_lineup_overlap: 4}, sources: {max_lineup_overlap: "request"}, automatic_decisions: {total_quality_budget: .5}},
      policy_validation: {status: "verified", actual_max_overlap: 4},
      contest_intent: {assignment_status: "UNASSIGNED", intended_entry_count: null},
      selected_ranks: [1], note: "Existing scoring.", top_20: [candidate],
      all_candidates: [candidate],
      production_controls: { mode: "conservative", selection_tradeoffs: {} },
      production_funnel: { admission_method: "joint_max_count_then_selector_score",
        status: "complete", requested: 205, solved: 285, legal: 285,
        rejected_by_player_cap: 64, accepted: 205, remaining_deficit: 0 },
      highest_p90_candidates_omitted: [{ rank: 2, qb: "QB Two", mean: 130,
        p90: 230, objective_score: 4.4, stack_family: "QB+1" }],
      generation_funnel: { eligible_player_pool: 300, sequential_unique: 120,
        saved_candidates: 120, selected: 1 },
      pregame_coverage: { qb: [{ name: "QB One", mean: 20, p90: 30,
        ownership: 5, game_total: 50, team_total: 27,
        candidate_count: 12, selected_count: 1, families: { "QB+2": 12 } }],
        games: [{ game: "AAA–BBB", qb: 12, pass_catcher: 30, bring_back: 4 }],
        players: [{ name: "High P90 WR", p90_percentile: 99,
          candidate_pct: 1, candidate_count: 1 }],
        stack_families: { "QB+2": 50 }, bring_back_distribution: { 0: 80, 1: 40 },
        selected_bring_back_distribution: { 0: 1 },
        diversity: { unique_roster_count: 120, candidate_count: 120,
          average_pairwise_overlap: 3.5, effective_family_count: 15 } },
      strategy_policy_alignment: { requested_strategy: "classic_small_field_gpp",
        applied_profile_id: "classic_large_gpp_v1", status: "borrowed_unvalidated",
        warning: "Historical validation pending." },
      prospective_experiment: {
        contract: "classic_prospective_structural_coverage_v1",
        frozen_snapshot_sha256: "abc123",
        availability_risk: { players: [{ player: "Questionable WR", designation: "Q",
          evidence_timestamp: "2026-09-26T20:00:00Z", practice_status: "LIMITED",
          workload_status: null, workload_confidence: "uncertain",
          bucket: "questionable_elevated", candidate_exposure: 25,
          selected_exposure: 40, candidate_cap: .25, selected_cap: .4,
          candidate_cap_binding: true }],
          production_candidate: { pct_with_at_least: { "1": 90 } },
          shadow_candidate: { pct_with_at_least: { "1": 25 } },
          shadow_selected: { pct_with_at_least: { "1": 40 } } },
        shadow_generation: { candidate_target: 120, candidate_underfill: 0,
          selected_ranks: [2], risk_policy_tradeoff: { mean_points_sacrificed: 1.2,
            ceiling_points_sacrificed: 2.3, comparison: "saved pregame comparison" } },
        shadow_portfolio: { selected_ranks: [3] },
      },
      selected_portfolio: { core_players: ["RB One"], constraints: { max_lineup_overlap: 6 },
        player_exposure: [{ name: "RB One", percent: 100 }],
        game_exposure: [{ game_id: "AAA-BBB", percent: 100 }], overlap_matrix: [[9]],
        lineups: [{ lineup: 1, rank: 1, qb: "QB One", primary_game: "AAA-BBB",
          construction_archetype: "QB+2 / WR FLEX", projected_score: 140,
          ceiling_proxy: 240, projected_ownership_sum: 55, leverage_proxy: 2,
          unique_players: [{ name: "QB One" }], selection_reason: "Distinct QB path." }] },
      rb_dst_diagnostics: { warning_only: true, player_why: [{ name: "RB One",
        team: "AAA", salary: 7000, mean: 17, p90: 27,
        role_class: "offensive centerpiece", snap_share_mean_3: .75,
        carries_mean_3: 10, targets_mean_3: 4, target_share_mean_3: .13,
        receiving_role_strength: .5, team_implied_total: 18,
        spread: 7, game_total: 43, model_version: "v4.2-role-opportunity",
        explanation_limit: "Saved one-feature role counterfactuals",
        model_explanation: { importance: [{ delta: -1 }, { delta: 0 }] },
        external_benchmark: { reason: "No saved same-slate benchmark" } }],
        selected_flag_exposure: [{ key: "rb_dst:rb:dst", appearances: 1,
          selected_count: 1 }] },
      selected_football_sanity: [candidate.football_sanity],
      contest: { contest_id: "123", name: "Sunday GPP", entry_fee: 5, capacity: 1000,
        current_entries: 800, maximum_entries: 1, payout_ladder: [{ from: 1, to: 1, cash: 1000 }],
        economics: { paid_percentage: .2, first_place_share: .1, full_field_rake: .15 },
        unavailable_fields: [] },
      top_qbs: [{ qb: "QB One", candidate_frequency: 35, average_score: 4.1, best_score: 4.5 }],
      stack_types: { "QB+2+bring-back": 40 }, primary_games_top_20: { "AAA–BBB": 6 },
      player_exposures: { top_20: { "QB One": 10 }, top_50: {}, entire_pool: {} },
      role_exposure: [{ player_id: "rb", name: "RB One", team: "AAA", position: "RB",
        importance: .55, role_class: "offensive centerpiece", role_confidence: "high",
        mean: 17, p90: 27, salary: 7000, mean_per_1000_salary: 2.43,
        ownership: null, candidate_count: 78, candidate_rate: .65,
        selected_count: 1, selected_rate: 1,
        role_counterfactual: { baseline_model_mean: 17, importance: [{ input: .45, model_mean: 16.5, delta: -.5 }], completeness: [] },
        opportunity_validation: { recent_targets_mean_3: 3, projected_targets_proxy: 3, targets_proxy_minus_recent: 0, context_adjusted: false },
        role_trend: { snap_share_trend: .1, target_share_trend: -.02, rush_share_trend: .05 } }],
      role_projection_anomalies: [{ name: "RB One", team: "AAA", role_importance: .55,
        role_class: "offensive centerpiece", team_role_rank: 1, team_mean_rank: 2,
        team_p90_rank: 2, position_value_rank: 14, position_value_count: 20,
        mean: 17, p90: 27, salary: 7000, candidate_count: 1, candidate_total: 120,
        possible_drivers: { matchup_context: { team_total: 21 }, recent_volume: { targets_mean_3: 3 },
          allocated_volume_proxy: { projected_targets: 3 } } }],
      historical_role_calibration: { status: "available", method: "held-out",
        by_position_and_role_class: { "RB|offensive centerpiece": { rows: 80, mean_fantasy_points: 17,
          mean_projection_error_predicted_minus_actual: 1.1, mae: 6, rmse: 8,
          ceiling_hit_rate: .12, ceiling_evaluable_rows: 70 } } },
      team_reconciliation: [{ team: "AAA", expected_pass_attempts: null,
        expected_rush_attempts: null, lagged_team_targets_proxy: 31,
        lagged_rb_carries_proxy: 22, role_coverage: 0.8,
        top_roles: [{ name: "RB One", importance: .55, role_class: "offensive centerpiece" }],
        target_distribution: [{ name: "WR One", value: 8 }],
        carry_distribution: [{ name: "RB One", value: 17 }],
        red_zone_distribution: [], missing_role_players: ["WR Two"] }],
      candidate_families: [{ qb: "QB One", best_by_stack: [3, 1, 1, null] }],
      ownership_evidence: { status: "unavailable", source: "target.ownership_projection",
        covered_players: 0, eligible_players: 317, missing_reason: "No current-slate ownership projections" },
      concentration: [{ name: "WR One", position: "WR", frequency: 120, salary: 4500,
        mean: 12, p90: 22, p90_per_1k: 4.89, mean_rank: 5, p90_rank: 6,
        value_rank: 2, template_boundary_count: 4, one_off_count: 80, no_comparable_swap_count: 115 }],
      qb_family_coverage: [{ qb: "QB One", salary: 6000, mean: 20, p90: 30,
        p90_per_1k: 5, rushing: { label: "moderate rushing QB" },
        families: [{ family: "QB+1", score: 4.2, reason: "legal diagnostic solve" }] }],
    } }, { player_id: "rb", name: "RB One", position: "RB", salary: 7000,
      projection: 17, p90: 27, player_team: "AAA" }];
  const html = buildOptimizerReportHtml({ job_id: "small", status: "completed",
    strategy: "classic_small_field_gpp", strategy_config: {}, contest_format: "classic",
    objective: "gpp", message: "done", results: [lineup] } as OptimizerResponse,
  { season: 2026, week: 2, slate: "SUNDAY_MAIN" });
  assert.match(html, /Classic small-field GPP diagnostic baseline/);
  assert.match(html, /not admitted after joint cap\/target selection 64/);
  assert.match(html, /Strategy and applied policy/);
  assert.match(html, /borrowed_unvalidated/);
  assert.match(html, /Selected portfolio paths/);
  assert.match(html, /Requested and effective portfolio policy/);
  assert.match(html, /Achieved overlap:<\/strong> 4/);
  assert.match(html, /UNASSIGNED/);
  assert.match(html, /Availability risk/);
  assert.match(html, /Questionable WR/);
  assert.match(html, /Projected points sacrificed due to availability-risk controls:<\/strong> 1\.20/);
  assert.match(html, /Original-pool overlap≤6 shadow/);
  assert.match(html, /Lineup overlap matrix/);
  assert.match(html, /Pregame candidate coverage and generation funnel/);
  assert.match(html, /High P90 WR/);
  assert.match(html, /Highest summed-P90 candidates omitted from selection/);
  assert.match(html, /120 legal candidates generated/);
  assert.match(html, /QB\+2\+bring-back/);
  assert.match(html, /ownership_chalk: 0\.000 inactive as soft term/);
  assert.match(html, /Sunday GPP/);
  assert.match(html, /sum of individual player ceilings/);
  assert.match(html, /Candidate families/);
  assert.match(html, /covered 0\/317 eligible players/);
  assert.match(html, /No current-slate ownership projections/);
  assert.match(html, /Candidate concentration/);
  assert.match(html, /Offensive role versus lineup exposure/);
  assert.match(html, /offensive centerpiece/);
  assert.match(html, /Offense opportunity reconciliation/);
  assert.match(html, /WR Two/);
  assert.match(html, /Top 10 QB family coverage/);
  assert.match(html, /QB\+1: 4\.200/);
  assert.match(html, /Selected lineup football sanity/);
  assert.match(html, /Central WR/);
  assert.match(html, /selection tradeoff unresolved/);
  assert.match(html, /Controlled role counterfactuals/);
  assert.match(html, /0\.45 → 16\.50/);
  assert.match(html, /High-role projection and exposure gaps/);
  assert.match(html, /High-role opportunity and trend validation/);
  assert.match(html, /Historical role calibration/);
  assert.match(html, /Player why · RB projection and role/);
  assert.match(html, /v4\.2-role-opportunity/);
  assert.match(html, /Lineup football sanity · warning only/);
  assert.match(html, /RB One \+ AAA DST/);
  assert.match(html, /Portfolio flagged-construction exposure/);
});

test("five-entry report includes verified contest economics and payout ladder", () => {
  const players = [
    { player_id: "qb", player_name: "Quarterback", roster_position: "CPT", position: "QB", player_team: "BUF", salary: 12000, projection: 20, p90: 35,
      showdown_selection_diagnostic: { global_candidate_rank: 3, mean_loss: 1.2, p90_loss: 2.4,
        selector_loss: 0.8, higher_ranked_skipped: [{ rank: 2, blockers: ["player exposure: core"] }] },
      captain_family_coverage_report: { candidate_count: 21, quality_eligible_count: 12,
        quality_fraction: 0.95, ownership_selection_status: "partial role ownership: selector ownership term disabled",
        family_rows: [{ captain_name: "Jalen Hurts", rank: 2, salary: 49000, mean: 76,
          p90: 142, correlation: 1.1, captain_ownership: null, lineup_ownership: null,
          selector: 100, selected: false, reason: "player exposure core" }] },
      portfolio_contest_report: {
        name: "Showdown 5 Entry Max", maximum_entries: 5, requested_entries: 5,
        generated_entries: 5, generated_entry_cost: 5, requested_entry_cost: 5,
        current_entries: 5529, capacity: 8917, prize_pool: 7500,
        lock_time: "2026-09-18T00:15:00Z", payout_ladder: [{ from: 1, to: 1, cash: 750 }],
        economics: { paid_percentage: .2585, minimum_cash: 1.5, full_field_rake: .1589, near_lock: false },
      } },
    ...["a", "b", "c", "d", "e"].map((id) => ({ player_id: id, player_name: id, roster_position: "FLEX", position: "WR", player_team: "DET", salary: 5000, projection: 10, p90: 20 })),
  ];
  const html = buildOptimizerReportHtml({ job_id: "5max-test", status: "completed", strategy: "showdown_gpp_portfolio_v3",
    strategy_config: {}, contest_format: "showdown", objective: "gpp", enforce_single_te: true,
    message: "done", results: [players] } as OptimizerResponse,
  { season: 2026, week: 2, slate: "THURSDAY_NIGHT" });
  assert.match(html, /5-max contest: Showdown 5 Entry Max/);
  assert.match(html, /Verified maximum 5 entries/);
  assert.match(html, /Full payout ladder/);
  assert.match(html, /750\.00/);
  assert.match(html, /Captain family coverage/);
  assert.match(html, /Jalen Hurts/);
  assert.match(html, /Global candidate rank #3/);
  assert.match(html, /player exposure: core/);
});

test("3-max report shows count comparisons and the best three-entry version", () => {
  const three = {
    candidate_ranks: [2, 8, 13], captains: ["Josh Allen", "Jameson Williams", "Jameson Williams"],
    scripts: ["Shootout", "Shootout", "Shootout"], total_entry_fees: 15,
    portfolio_objective: .1872, payout_proxy: .155, lineup_quality_contribution: .029,
    diversification_contribution: .0032, average_mean: 88.3, minimum_mean: 86.7,
    average_p90: 153.4, minimum_p90: 151.9, average_relative_chalk: 42.5,
    unique_captains: 2, script_diversity: 1,
    captain_exposures: { "Josh Allen": 1 / 3, "Jameson Williams": 2 / 3 },
    player_exposures: { "Josh Allen": 1 },
    pairwise: [{ candidate_ranks: [8, 13], shared_players: 5, overlap_percentage: 83.3,
      jaccard_similarity: .714, same_captain: true, same_script: true,
      same_team_emphasis: true, same_value_player_ids: [], relative_chalk_difference: 2.9,
      repeated_captain_materially_different: false }],
    lineups: [{ rank: 2, captain: "Josh Allen", mean: 91.2, p90: 155.8,
      relative_chalk: 32.8, script: "Shootout", players: [{ slot: "CPT", name: "Josh Allen" }] }],
  };
  const report = {
    selected_count: 1, contest: { name: "Representative 3-max", entry_fee: 5, maximum_entries: 3 },
    enforce_single_te: true, note: "Uncalibrated heuristic.",
    qualifying_candidate_count: 40, candidate_count: 40,
    count_comparisons: [{ ...three, candidate_ranks: [1], total_entry_fees: 5 },
      { ...three, candidate_ranks: [3, 4], total_entry_fees: 10 }, three],
    selected: { ...three, candidate_ranks: [1], pairwise: [], unique_captains: 1 },
    marginal_entries: [], structure_comparisons: { two_captains: three },
  };
  const lineup = [
    { player_id: "p1", player_name: "Josh Allen", roster_position: "CPT", position: "QB", player_team: "BUF", salary: 15000, projection: 20, p90: 35 },
    ...["p2", "p3", "p4", "p5", "p6"].map((id) => ({ player_id: id, player_name: id, roster_position: "FLEX", position: "WR", player_team: "DET", salary: 5000, projection: 10, p90: 20 })),
  ];
  (lineup[1] as any).three_max_report = report;
  const html = buildOptimizerReportHtml({ job_id: "3max-test", status: "completed", strategy: "showdown_3max_gpp",
    strategy_config: {}, contest_format: "showdown", objective: "gpp", enforce_single_te: true,
    message: "done", results: [lineup] } as OptimizerResponse,
  { season: 2026, week: 2, slate: "THURSDAY_NIGHT" });
  assert.match(html, /Small-max recommendation: 1 entry/);
  assert.match(html, /Best three-entry version/);
  assert.match(html, /Jameson Williams/);
  assert.match(html, /83\.3% overlap/);
});

test("small-max report explains the fifth entry's fee, quality, and portfolio change", () => {
  const report = {
    selected_count: 4, contest: { name: "Thursday 5-max", entry_fee: 1, maximum_entries: 5 },
    enforce_single_te: true, note: "Uniform-rank proxy.",
    qualifying_candidate_count: 5, searched_candidate_count: 5, candidate_count: 5,
    count_comparisons: [1, 2, 3, 4, 5].map((count) => ({ candidate_ranks: Array.from({ length: count }, (_, i) => i + 1),
      total_entry_fees: count, portfolio_objective: count === 5 ? .19 : .20,
      payout_proxy: .17, lineup_quality_contribution: .025,
      diversification_contribution: .005, average_mean: 85,
      minimum_mean: 78.45, average_p90: 150, minimum_p90: 141.31,
      average_relative_chalk: 40, captains: ["Josh Allen"] })),
    selected: { candidate_ranks: [1, 2, 3, 4], unique_captains: 1, script_diversity: 1,
      captain_exposures: {}, player_exposures: {}, pairwise: [],
      lineups: [{ rank: 1, relative_chalk: 63.5 }] },
    count_marginals: [{ from_count: 4, entry_count: 5, objective_change: -.01,
      payout_proxy_change: -.008, lineup_quality_change: -.002,
      diversification_change: 0, added_candidate_ranks: [5], removed_candidate_ranks: [],
      added_lineups: [{ mean: 78.45, p90: 141.31 }], fee_delta: 1 }],
    leave_one_out: [{ candidate_rank: 1, captain: "Josh Allen", mean: 90, p90: 155,
      relative_chalk: 63.5, remaining_candidate_ranks: [2, 3, 4],
      objective_without_lineup: .18, objective_change_if_removed: -.02 }],
  };
  const lineup = [
    { player_id: "qb", player_name: "Josh Allen", roster_position: "CPT", position: "QB", player_team: "BUF", salary: 15000, projection: 20, p90: 35, small_max_report: report },
    ...["a", "b", "c", "d", "e"].map((id) => ({ player_id: id, player_name: id, roster_position: "FLEX", position: "WR", player_team: "DET", salary: 5000, projection: 10, p90: 20 })),
  ];
  (lineup[1] as any).lineup_duplication_risk = {
    ownership_available: true, relative_chalk_score: report.selected.lineups[0].relative_chalk,
    log_probability: -8,
  };
  const html = buildOptimizerReportHtml({ job_id: "small-max-test", status: "completed", strategy: "showdown_small_max_gpp",
    strategy_config: {}, contest_format: "showdown", objective: "gpp", enforce_single_te: true,
    message: "done", results: [lineup] } as OptimizerResponse,
  { season: 2026, week: 2, slate: "THURSDAY_NIGHT" });
  assert.match(html, /Small-max recommendation: 4 entries/);
  assert.match(html, /Best 5-entry portfolio vs best 4-entry portfolio/);
  assert.match(html, /objective delta -0\.0100/);
  assert.match(html, /fee delta \$1\.00/);
  assert.match(html, /Remove candidate #1/);
  assert.match(html, /change if removed -0\.0200/);
  assert.match(html, /Relative chalk: 63\.5\/100/);
  const forced = { ...report, selection_mode: "configured", entries_to_use: "5",
    configured_entry_count: 5, selected_count: 5, auto_recommended_count: 1 };
  (lineup[0] as any).small_max_report = forced;
  const forcedHtml = buildOptimizerReportHtml({ job_id: "forced-small-max", status: "completed", strategy: "showdown_small_max_gpp",
    strategy_config: {}, contest_format: "showdown", objective: "gpp", enforce_single_te: true,
    message: "done", results: [lineup] } as OptimizerResponse,
  { season: 2026, week: 2, slate: "THURSDAY_NIGHT" });
  assert.match(forcedHtml, /Configured portfolio: 5 entries/);
  assert.match(forcedHtml, /Configured entry count: 5/);
  assert.match(forcedHtml, /Auto recommendation under current heuristic: 1 entry/);
  assert.doesNotMatch(forcedHtml, /Small-max recommendation: 5 entries/);
});

test("generic small-max report omits contest economics", () => {
  const report = {
    contest_mode: "generic", contest: null, maximum_entries: 3,
    entries_to_use: "auto", selection_mode: "auto", selected_count: 1,
    enforce_single_te: true, note: "No contest payout or ROI estimate is made.",
    qualifying_candidate_count: 3, candidate_count: 3,
    count_comparisons: [{ candidate_ranks: [1], lineup_quality_contribution: 1,
      diversification_contribution: 0, average_mean: 76, minimum_mean: 76,
      average_p90: 142, minimum_p90: 142, captains: ["Player A"], scripts: ["pass-led"] }],
    selected: { candidate_ranks: [1], unique_captains: 1, script_diversity: 1,
      captain_exposures: { "Player A": 1 }, player_exposures: { "Player A": 1 }, pairwise: [] },
  };
  const lineup = [
    { player_id: "a", player_name: "Player A", roster_position: "CPT", position: "QB", player_team: "AAA", salary: 15000, projection: 20, p90: 35, small_max_report: report },
    ...["b", "c", "d", "e", "f"].map((id) => ({ player_id: id, player_name: id, roster_position: "FLEX", position: "WR", player_team: "BBB", salary: 5000, projection: 10, p90: 20 })),
  ];
  const html = buildOptimizerReportHtml({ job_id: "generic-small-max", status: "completed", strategy: "showdown_small_max_gpp",
    strategy_config: {}, contest_format: "showdown", objective: "gpp", enforce_single_te: true,
    message: "done", results: [lineup] } as OptimizerResponse,
  { season: 2026, week: 2, slate: "MONDAY_NIGHT" });
  assert.match(html, /Generic small-max lineup selection: 1 entry/);
  assert.match(html, /Auto selected one lineup/);
  assert.match(html, /Quality score/);
  assert.doesNotMatch(html, /Payout proxy/);
  assert.doesNotMatch(html, /Entry fees/);
});

test("builds a readable optimizer report with summaries, players, and controls", () => {
  const optimizer = {
    job_id: "job-123456789",
    status: "completed",
    strategy: "showdown_gpp_captain_informed_v2",
    strategy_config: {},
    contest_format: "showdown",
    objective: "gpp",
    enforce_single_te: true,
    exclude_opponent_teams: ["DEN"],
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
      prior_eligibility_removal_reason_counts: { user_excluded: 1 },
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
      }, {
        player_id: "jax-1",
        player_name: "Strong Jacksonville Player",
        team: "JAX",
        opponent_team: "DEN",
        position: "WR",
        salary: 7000,
        projection: 18.4,
        p90: 31.2,
        included: false,
        optimizer_eligibility: "excluded_by_user_preference",
        removal_stage: "optimizer_filter",
        exclusion_reasons: ["excluded_opponent_team"],
        exclusion_details: [{
          rule_id: "user.preference.opponent_exclusion_v1",
          reason_code: "excluded_opponent_team",
          description: "User preference — opponent DEN",
          category: "user",
        }],
        user_preference_exclusions: [{
          rule_id: "user.preference.opponent_exclusion_v1",
          reason_code: "excluded_opponent_team",
          description: "User preference — opponent DEN",
          category: "user",
        }],
        model_assessment: { projection: 18.4, p90: 31.2, role_label: "primary option" },
      }, {
        player_id: "lar-1",
        player_name: "Scenario Receiver",
        team: "LAR",
        opponent_team: "NYG",
        position: "WR",
        salary: 11000,
        projection: 0,
        p90: 0,
        official_availability_status: "QUESTIONABLE",
        availability_override: "assume_out",
        model_availability_used: 0,
        projection_before_scenario: 18.88,
        projection_after_scenario: 0,
        opportunity_redistributed: true,
        included: false,
        optimizer_eligibility: "excluded",
        removal_stage: "optimizer_filter",
        exclusion_reasons: ["pregame_availability_zero"],
        exclusion_details: [{
          rule_id: "eligibility.zero_availability_v1",
          reason_code: "pregame_availability_zero",
          description: "Zero model availability",
          category: "eligibility",
        }],
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
  assert.match(html, /Hard exclude players facing: DEN/);
  assert.match(html, /User preference exclusions \(1\)/);
  assert.match(html, /Strong Jacksonville Player/);
  assert.match(html, /Projection 18\.40 DK · P90 31\.20 · primary option/);
  assert.match(html, /EXCLUDED/);
  assert.match(html, /User preference — opponent DEN/);
  assert.match(html, /Manual player decisions \(2\)/);
  assert.match(html, /Scenario Receiver/);
  assert.match(html, /QUESTIONABLE/);
  assert.match(html, /assume out/);
  assert.match(html, /18\.88/);
  assert.match(html, /Opportunity redistributed\?<\/th>/);
  assert.match(html, /Zero model availability/);

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
  assert.match(html, /user excluded \(1\)/);
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
    single_entry_score: 0.7,
    solver_objective: 160,
    objective_contributions: { mean: 0.3, p90: 0.3, solver: 0.2, correlation: 0.1, context: 0.03, chalk_penalty: -0.03, duplication_uniqueness: 0, script: 0, other_penalties: 0 },
    solver_objective_components: { p90_ceiling: 150, context: 5, captain_prior: 10, ownership_penalty: -8, correlation_and_format: 3, other_or_unattributed: 0 },
    quality_sacrifice_for_chalk: { mean_loss_vs_best_mean: 1.29, p90_loss_vs_best_p90: 5.02, chalk_improvement_vs_best_quality: 66.6, chalk_objective_gain_vs_best_quality: 0.02, large_ceiling_sacrifice_for_uniqueness: true, best_p90_candidate_rank: 1, best_quality_candidate_rank: 1 },
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
    enforce_single_te: true,
    results: [[{
      player_id: "captain", name: "A", roster_position: "CPT",
      position: "QB", player_team: "DET", salary: 12000,
      projection: 20, p90: 35,
      lineup_controls: { enforce_single_te: true },
      single_entry_report: {
        enforce_single_te: true,
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
  assert.match(html, /Enforce single TE \(no double-TE lineups\): True/);
  assert.match(html, /Single-entry objective decomposition/);
  assert.match(html, /Nested solver objective/);
  assert.match(html, /0\.3000/);
  assert.match(html, /150\.000/);
  assert.match(html, /reduces summed P90 by 5\.02 points/);
  assert.match(html, /The best A \/ B \/ C scores/);
  assert.match(html, /Different Captain, same six players/);
  assert.match(html, /Jaccard/);
  assert.match(html, /B &lt;Captain&gt;/);
  assert.doesNotMatch(html, /B <Captain>/);
  assert.throws(() => buildOptimizerReportHtml({ ...optimizer, enforce_single_te: null }, { season: 2026, week: 2, slate: "THURSDAY_NIGHT" }), /configuration error.*enforce_single_te/);
});

test("one selected contest omits diversification-combination language", () => {
  const optimizer = {
    job_id: "one-contest", status: "completed",
    strategy: "showdown_single_entry_portfolio", strategy_config: {},
    contest_format: "showdown", objective: "gpp", lineage_persisted: true,
    enforce_single_te: false,
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
          snapshot_fallbacks: [{ contest_id: "123", observed_at: "2026-09-17 12:00:00+00:00" }],
          count_comparisons: [{ contest_count: 1, contest_ids: ["123"], total_entry_fees: 5, heuristic_value: .25, independent_rank_proxy: .25, shared_percentile_proxy: .25 }],
          sensitivity: [{ shared_rank_weight: 0, by_count: [{ contest_count: 1, profitability_proxy: .25 }], recommended_count: 1 }],
          crossovers: [], recommendation_status: "ROBUST", recommendation_status_reason: "One feasible count.",
          ranked_contests: [{ contest_id: "123", name: "Test contest", source: "saved_snapshot", contest_score: .25, entry_fee: 5, capacity: 100, economics: {
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
  assert.match(html, /Correlation sensitivity/);
  assert.match(html, /Recommended count: 1 · ROBUST/);
  assert.match(html, /Best subset/);
  assert.match(html, /Min cash/);
  assert.match(html, /Saved snapshot fallback/);
  assert.match(html, /Snapshot; not applied/);
  assert.doesNotMatch(html, /A \/ A \/ A/);
  assert.doesNotMatch(html, /Diversification benefit/);
  assert.doesNotMatch(html, /candidate combinations with repetition/);
});

test("GPP report records one provisional recommendation without inventing returns", () => {
  const candidate = {candidate_id: 'candidate', lineup_number: 2, rank: 1, projected_points: 120,
    marginal_upside_sum: 210, salary: 49900, availability_exceptions: []};
  const optimizer = {job_id: 'gpp', status: 'completed', strategy: 'classic_large_gpp_v1',
    contest_format: 'classic', objective: 'gpp', results: [], gpp_recommendation: {
      policy_id: 'gpp_projection_first_recommendation_v1', status: 'provisional',
      reason: 'Projected points <not paid probability>', recommended: candidate, candidates: [candidate],
      exceptions: [], limitations: ['Not a lineup percentile'],
    }} as unknown as OptimizerResponse;
  const html = buildOptimizerReportHtml(optimizer, {season: 2026, week: 5, slate: 'SUNDAY_MAIN'});
  assert.match(html, /Recommended lineup #2/);
  assert.match(html, /Expected return: unavailable/);
  assert.match(html, /Paid-finish probability: unavailable/);
  assert.match(html, /Sum of player P90s/);
  assert.match(html, /&lt;not paid probability&gt;/);
  assert.doesNotMatch(buildOptimizerReportHtml({...optimizer, status:'failed'},
    {season:2026,week:5,slate:'SUNDAY_MAIN'}), /Recommended lineup #2/);
});

test("Showdown report renders P90 shortlist and separates user exclusions", () => {
  const optimizer = {
    job_id: "shortlist", status: "completed", strategy: "captain_single_lineup_v1",
    contest_format: "showdown", objective: "cash", enforce_single_te: false,
    results: [[{player_id: "id-a", name: "Receiver", position: "WR", roster_position: "CPT",
      showdown_captain_shortlist: {
        shortlist: [{player_id: "id-a", name: "<Receiver>", team: "AAA", pregame_p90: 30,
          eligible_p90_rank: 1, exclusions: []}],
        exclusions: [{player_id: "id-b", name: "Flex", team: "BBB", pregame_p90: 20,
          eligible_p90_rank: 5, exclusions: [{reason_code: "outside_top_four_p90", category: "optimizer_policy"}]},
          {player_id: "id-q", name: "QB", team: "BBB", pregame_p90: 40, eligible_p90_rank: null,
            exclusions: [{reason_code: "user_no_qb_captain", category: "user_preference"}]}],
      },
    }]],
  } as unknown as OptimizerResponse;
  const html = buildOptimizerReportHtml(optimizer, {season: 2026, week: 4, slate: "THURSDAY_NIGHT"});
  assert.match(html, /Top-four P90 captain shortlist/);
  assert.match(html, /Captain score = 1.5 × P90; FLEX score = mean/);
  assert.match(html, /Captain salary = 1.5 × base salary/);
  assert.match(html, /optimizer_policy: outside_top_four_p90/);
  assert.match(html, /user_preference: user_no_qb_captain/);
  assert.match(html, /&lt;Receiver&gt; \/ id-a/);
  assert.match(html, /does not restrict FLEX eligibility/);
});

test("Captain coverage report shows gaps, warnings and hard underfill even without lineups", () => {
  const optimizer = {
    job_id: "coverage", status: "failed", strategy: "showdown_gpp_portfolio_v3", enforce_single_te: false,
    contest_format: "showdown", objective: "gpp", results: [],
    showdown_captain_coverage: {underfill: 1, missing_eligible_captains: 0, captains: [
      {name: "Quarterback", status: "selected", projection_gap: {projection: 8, p90: 20},
        quality_floor_warnings: [{metric: "p90", gap: 10, value: 80, floor: 90}]},
      {name: "Receiver", status: "infeasible", reason: "salary_cap: exceeds $50000 <required>"},
    ]},
  } as unknown as OptimizerResponse;
  const html = buildOptimizerReportHtml(optimizer, {season: 2026, week: 4, slate: "MONDAY_NIGHT"});
  assert.match(html, /Four-captain coverage/);
  assert.match(html, /Underfill: 1/);
  assert.match(html, /<td>8.00<\/td><td>20.00<\/td>/);
  assert.match(html, /p90 below floor by 10.00/);
  assert.match(html, /salary_cap: exceeds \$50000 &lt;required&gt;/);
});

test("explicit preliminary reports retain real rosters while preserving blocked normal readiness", () => {
  const optimizer = {job_id:"preliminary",status:"completed",strategy:"classic_large_gpp_v1",contest_format:"classic",objective:"gpp",enforce_single_te:true,
    data_readiness:{status:"ERROR",reason_codes:["official_player_status_refresh_failed"]},entry_readiness:{entry_ready:false,status:"PRELIMINARY_NOT_ENTRY_CLEARED"},
    preliminary_report:{classification:"PRELIMINARY_RESEARCH",entry_ready:false,snapshot_sha256:"snapshot",assumption_manifest_sha256:"assumptions"},
    results:[[{player_id:"real-player",name:"Research Roster Player",position:"QB",salary:6400,projection:20,p90:25}]]} as unknown as OptimizerResponse;
  const html=buildOptimizerReportHtml(optimizer,{season:2026,week:6,slate:"SUNDAY_MAIN"});
  assert.match(html,/Preliminary research · not entry cleared/);
  assert.match(html,/Research Roster Player/);
  assert.match(html,/official_player_status_refresh_failed/);
  assert.match(html,/CSV download requires Check upload readiness/);
});


test("primary report separates selection forecast and old optimizer comparison with immutable evidence",()=>{
 const optimizer={job_id:"primary",status:"completed",contest_format:"showdown",objective:"gpp",enforce_single_te:false,
 results:[[{player_id:"p",name:"Primary Receiver",roster_position:"CPT",position:"WR",projection:18,scenario_mean:27,salary:12000,showdown_captain_shortlist:{policy_id:"new_model_primary_covered_captains_v1",shortlist:[{player_id:"p",name:"Primary Receiver",team:"NE"}]}}]],
 scenario_mode:{prepared:{new_model_primary:true,limitations:["Calibration unproven"],sha256:"frozen-source-model-receipt"},conditional_mean:27,scenario_lineup_baseline_mean:18,baseline_mean:22,
 baseline_lineup:[{player_id:"q",name:"Old Receiver",roster_position:"CPT",position:"WR",salary:9000,projection:22}]}} as unknown as OptimizerResponse;
 const html=buildOptimizerReportHtml(optimizer,{season:2026,week:7,slate:"THURSDAY_NIGHT"});
 assert.match(html,/New-model Captain eligibility/);assert.doesNotMatch(html,/Top-four P90 captain shortlist/);
 assert.match(html,/New models drive selection/);assert.match(html,/Selection forecast: 27.00/);
 assert.match(html,/Baseline proj/);assert.match(html,/CPT · Old Receiver/);
 assert.match(html,/frozen-source-model-receipt/);assert.match(html,/not a selector-only experiment/);
});
