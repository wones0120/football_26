import assert from "node:assert/strict";
import test from "node:test";
import { sameOptimizerRunScope } from "../src/optimizerHistory.ts";
import { ACTIVE_OPTIMIZER_STRATEGIES, defaultTournamentStrategyId, DEFAULT_OPTIMIZER_OBJECTIVE } from "../src/optimizerStrategy.ts";
import { singleLineupReportHtml } from "../src/singleLineupReport.ts";
import type { OptimizerResponse } from "../src/api.ts";

test("normal strategies use GPP for both Classic and Showdown", () => {
  assert.deepEqual(ACTIVE_OPTIMIZER_STRATEGIES.map(r => r.id), ["showdown_gpp_portfolio_v3", "classic_large_gpp_v1"]);
  assert.equal(defaultTournamentStrategyId("classic"), "classic_large_gpp_v1");
  assert.equal(defaultTournamentStrategyId("showdown"), "showdown_gpp_portfolio_v3");
  assert.equal(DEFAULT_OPTIMIZER_OBJECTIVE, "gpp");
});

test("one recommendation is prominent and candidate research is collapsed and escaped", () => {
  const candidate = { rank: 1, expected_points: 120, downside_diagnostic: 80, upside_diagnostic: 160,
    selection_score: 101, risk_factors: ["Availability <uncertain>"], correlation_assumptions: "unvalidated",
    players: [{ player_id: "id", name: "<script>alert(1)</script>", position: "QB" }] };
  const response = { contest_format: "classic", results: [[{ ...candidate.players[0], salary: 5000, projection: 120,
    single_lineup_report: { recommended: candidate, all_candidates: [candidate], notable_alternatives: [],
      candidate_count: 1, cash_probability: null, limitations: ["Unvalidated"], why_preferred: "Highest proxy", objective_weights: { mean: 1 } } }]] } as unknown as OptimizerResponse;
  const html = singleLineupReportHtml(response);
  assert.match(html, /Recommended Classic lineup/);
  assert.match(html, /Cash probability unavailable/);
  assert.match(html, /Expected fantasy points/);
  assert.match(html, /<details><summary>Candidate diagnostics \/ research/);
  assert.ok(!html.includes("<details open"));
  assert.ok(!html.includes("<script>"));
  assert.match(html, /&lt;script&gt;/);
  assert.equal(singleLineupReportHtml({ results: [[{ player_id: "legacy" }]] } as unknown as OptimizerResponse), "");
});

test("saved Classic results cannot recover over a Captain or different slate selection", () => {
  const saved = { season: 2026, week: 1, slate: "SUNDAY_MAIN", contest_format: "classic" };
  assert.equal(sameOptimizerRunScope(saved, { ...saved, slate: "sunday_main" }), true);
  for (const change of [{contest_format: "showdown"}, {season: 2025}, {week: 2}, {slate: "SUNDAY_NIGHT"}])
    assert.equal(sameOptimizerRunScope(saved, { ...saved, ...change }), false);
});

test("explicit multiple outputs retain one primary and report requested counts and limits", () => {
  const candidate = { rank: 1, selection_score: 20, expected_points: 22, downside_diagnostic: 15, upside_diagnostic: 30,
    players: [], risk_factors: [], correlation_assumptions: 'assumed', selected: true };
  const response = { contest_format: 'classic', results: [[{ name: 'Primary', player_id: 'p', single_lineup_report: {
    recommended: candidate, all_candidates: [candidate], notable_alternatives: [], limitations: [], requested_count: 3, selected_count: 2,
    user_constraints: { num_lineups: 3, max_exposure: .5 }, constraint_selection: { status: 'underfilled', limits_relaxed: false },
  } }]] } as unknown as OptimizerResponse;
  const html = singleLineupReportHtml(response);
  assert.match(html, /Requested 3 lineup\(s\) · Selected 2 · One primary/);
  assert.match(html, /Additional requested lineups/);
  assert.match(html, /No limits were relaxed/);
  assert.match(html, /Saved lineup settings/);
  assert.match(html, /max_exposure/);
});

test("zero-output saved reports retain the rejected settings", () => {
  const response = { results: [], single_lineup_selection: { requested_count: 3, selected_count: 0, recommended: null,
    user_constraints: { max_exposure: 0 }, constraint_selection: { status: 'underfilled', limits_relaxed: false } } } as unknown as OptimizerResponse;
  const html = singleLineupReportHtml(response);
  assert.match(html, /Requested 3 · Selected 0/);
  assert.match(html, /max_exposure/);
  assert.match(html, /No limits were relaxed/);
});
