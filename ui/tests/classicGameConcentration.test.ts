import assert from "node:assert/strict";
import test from "node:test";
import type { OptimizerResponse } from "../src/api.ts";
import { classicGameCapParams, parseSavedPrimaryGameCap } from "../src/classicGameConcentration.ts";
import { buildOptimizerReportHtml } from "../src/optimizerReport.ts";

test("No limit omits the optional cap; preset and custom choices serialize exactly", () => {
  assert.deepEqual(classicGameCapParams(null), {});
  for (const value of [4, 3, 2, 1, 7]) assert.deepEqual(classicGameCapParams(value), { max_lineups_per_primary_game: value });
  for (const value of [0, -1, 1.5, NaN]) assert.throws(() => classicGameCapParams(value));
});

test("Only valid persisted choices are restored, and omission remains No limit", () => {
  for (const raw of [null, "null", "bad", "0", "false", '"3"', "1.5"]) assert.equal(parseSavedPrimaryGameCap(raw), null);
  assert.equal(parseSavedPrimaryGameCap("3"), 3);
  assert.equal(parseSavedPrimaryGameCap("7"), 7);
});

test("Downloaded saved report renders requested/effective concentration and contract mode", () => {
  const optimizer = { job_id: "frozen", status: "completed", strategy: "classic_large_gpp_v1", contest_format: "classic", objective: "gpp", results: [],
    primary_game_constraint: { requested: 3, effective: 3, source: "request", validation: "verified", achieved_game_exposure: { "CIN-JAX": 3, "DAL-HOU": 2 } },
    effective_strategy_contract: { contract_id: "classic_large_gpp_effective_strategy_v1", execution_mode: "PARITY", strategy_label: "classic_large_gpp_v1", effective_sha256: "checksum", deviations: [], effective: {} },
  } as OptimizerResponse;
  const html = buildOptimizerReportHtml(optimizer, { season: 2026, week: 4, slate: "SUNDAY_MAIN" });
  assert.match(html, /Requested: 3 · Effective: 3/);
  assert.match(html, /CIN-JAX: 3 · DAL-HOU: 2/);
  assert.match(html, /Saved strategy contract/);
  assert.match(html, /PARITY/);
  const omitted = buildOptimizerReportHtml({ ...optimizer, primary_game_constraint: { ...optimizer.primary_game_constraint!, requested: null, effective: null } }, { season: 2026, week: 4, slate: "SUNDAY_MAIN" });
  assert.match(omitted, /Requested: No limit · Effective: No limit/);
});
