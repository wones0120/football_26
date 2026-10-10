import assert from "node:assert/strict";
import test from "node:test";
import { assertLargeGppOverlapResult, assertPortfolioSummaryMatchesRequest } from "../src/classicOverlapConsistency.ts";
import type { OptimizerResponse } from "../src/api.ts";

function report() {
  return { effective_strategy_contract: { requested: { max_lineup_overlap: 5 }, effective: { max_lineup_overlap: 5 }, sources: { max_lineup_overlap: "request" } },
    portfolio_controls_report: { settings: [{ key: "max_lineup_overlap", requested: 5, effective: 5, source: "request", achieved: 5 }] },
    results: [Array.from({ length: 9 }, (_, i) => ({ player_id: `player-${i}` })), Array.from({ length: 9 }, (_, i) => ({ player_id: `player-${i + 4}` }))] } as unknown as OptimizerResponse;
}
const check = (response: OptimizerResponse) => assertLargeGppOverlapResult("classic_large_gpp_v1", { max_lineup_overlap: 5 }, response);
test("Pre-submit assertion blocks explicit overlap loss and verifies intentional default null", () => {
  const params = { num_lineups: 5, max_exposure: .8, max_lineups_per_primary_game: 3, max_lineup_overlap: 5 };
  assert.doesNotThrow(() => assertPortfolioSummaryMatchesRequest(params, JSON.stringify({ params })));
  for (const value of [null, undefined, 4, 7, "5"]) {
    assert.throws(() => assertPortfolioSummaryMatchesRequest(params, JSON.stringify({ params: { ...params, max_lineup_overlap: value } })), /max_lineup_overlap.*Submission blocked/);
  }
  const defaults = { ...params, max_lineup_overlap: null };
  assert.doesNotThrow(() => assertPortfolioSummaryMatchesRequest(defaults, JSON.stringify({ params: defaults })));
  assert.throws(() => assertPortfolioSummaryMatchesRequest(defaults, JSON.stringify({ params: { ...params, max_lineup_overlap: undefined } })), /Submission blocked/);
  assert.throws(() => assertPortfolioSummaryMatchesRequest(params, JSON.stringify({ params: { ...params, num_lineups: 20 } })), /num_lineups.*Submission blocked/);
});
test("Explicit overlap rejects dropped/defaulted contract layers and missing report evidence", () => {
  assert.doesNotThrow(() => check(report()));
  for (const key of ["requested", "effective", "sources"]) {
    const r = report();
    delete r.effective_strategy_contract![key];
    assert.throws(() => check(r), /consistency failure/);
  }
  const r = report();
  r.portfolio_controls_report!.settings![0].effective = 7;
  assert.throws(() => check(r), /consistency failure/);
  delete r.portfolio_controls_report;
  assert.throws(() => check(r), /consistency failure/);
});
test("Actual canonical intersections are checked independently of a claimed achieved 5", () => {
  const r = report();
  r.results = [(r.results as unknown[][])[0], (r.results as unknown[][])[0]];
  assert.throws(() => check(r), /rosters exceed/);
  r.results = [[{}], [{}]];
  assert.throws(() => check(r), /canonical player ID/);
  const misleading = report();
  misleading.portfolio_controls_report!.settings[0].achieved = 4;
  assert.throws(() => check(misleading), /achieved value disagrees/);
});
test("Strategy default and unrelated strategies retain their existing result handling", () => {
  assert.doesNotThrow(() => assertLargeGppOverlapResult("classic_large_gpp_v1", {}, {} as OptimizerResponse));
  assert.doesNotThrow(() => assertLargeGppOverlapResult("classic_small_field_gpp", { max_lineup_overlap: 5 }, {} as OptimizerResponse));
});
