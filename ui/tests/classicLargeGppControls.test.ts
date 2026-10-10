import { canOpenSavedOptimizerReport } from "../src/optimizerHistory.ts";
import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { DEFAULT_LARGE_GPP_CONTROLS, largeGppControlParams, parseSavedLargeGppControls, parseSavedLargeGppVolume } from "../src/classicLargeGppControls.ts";
import { portfolioSettingsRows } from "../src/classicPortfolioReport.ts";
import { buildOptimizerReportHtml } from "../src/optimizerReport.ts";
import type { OptimizerResponse } from "../src/api.ts";

test("Strategy default omits optional constraints, while preset/custom values serialize exactly", () => {
  assert.deepEqual(largeGppControlParams(DEFAULT_LARGE_GPP_CONTROLS), {});
  for (const overlap of [7, 6, 5, 4, 0, 8]) {
    assert.deepEqual(largeGppControlParams({ ...DEFAULT_LARGE_GPP_CONTROLS, maxLineupOverlap: overlap }), { max_lineup_overlap: overlap });
  }
  for (const percent of [80, 60, 40, 20, 0, 55.5]) {
    assert.deepEqual(largeGppControlParams({ ...DEFAULT_LARGE_GPP_CONTROLS, elevatedExposurePercent: percent }), { elevated_player_max_exposure: percent / 100 });
  }
  for (const count of [0, 1, 2, 7]) {
    assert.deepEqual(largeGppControlParams({ ...DEFAULT_LARGE_GPP_CONTROLS, maxElevatedPerLineup: count }), { max_elevated_players_per_lineup: count });
  }
});

test("Invalid portfolio limits are rejected before submitting or refreshing inputs", () => {
  for (const overlap of [9, -1, NaN, 1.5]) assert.throws(() => largeGppControlParams({ ...DEFAULT_LARGE_GPP_CONTROLS, maxLineupOverlap: overlap }));
  for (const rate of [-1, 101, NaN, Infinity]) assert.throws(() => largeGppControlParams({ ...DEFAULT_LARGE_GPP_CONTROLS, elevatedExposurePercent: rate }));
  for (const count of [-1, 10, NaN, 1.5]) assert.throws(() => largeGppControlParams({ ...DEFAULT_LARGE_GPP_CONTROLS, maxElevatedPerLineup: count }));
});

test("Reload restores the user's optional choices and Large-GPP volume; invalid storage uses existing defaults", () => {
  const controls = { maxLineupOverlap: 4, elevatedExposurePercent: 40, maxElevatedPerLineup: 0 };
  const persisted = JSON.stringify({ ...controls, numLineups: 5, maxExposure: 80 });
  assert.deepEqual(parseSavedLargeGppControls(persisted), controls);
  assert.deepEqual(parseSavedLargeGppVolume(persisted), { numLineups: 5, maxExposure: 80 });
  for (const raw of [null, "bad", "{}", "null"]) {
    assert.deepEqual(parseSavedLargeGppControls(raw), DEFAULT_LARGE_GPP_CONTROLS);
    assert.deepEqual(parseSavedLargeGppVolume(raw), { numLineups: 20, maxExposure: 60 });
  }
  assert.deepEqual(parseSavedLargeGppControls('{"maxLineupOverlap":9}'), DEFAULT_LARGE_GPP_CONTROLS);
});

test("Normal run paths restore lineup controls while historical components remain available", () => {
  const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
  assert.match(app, /optimizer_params: optimizerParams\(\)/);
  assert.match(app, /<OptimizerLineupControls/);
  assert.match(app, /lineupControlParams\(lineupControls, contestFormat\)/);
  assert.doesNotMatch(app, /submittedClassicControls|<ClassicLargeGppPortfolioControls/);
  const component = readFileSync(new URL("../src/ClassicLargeGppPortfolioControls.tsx", import.meta.url), "utf8");
  assert.match(component, /Portfolio diversification/);
  assert.match(component, /Advanced portfolio constraints/);
  assert.doesNotMatch(component, /min_distinct_primary_games/);
});

test("Saved reports display all settings and underfill diagnostics using saved achieved values", () => {
  const optimizer = { job_id: "fixture", status: "failed", strategy: "classic_large_gpp_v1", contest_format: "classic", objective: "gpp", results: [],
    effective_strategy_contract: { contract_id: "classic_large_gpp_effective_strategy_v1", effective: {} },
    portfolio_controls_report: {
      settings: [
        { key: "entry_count", setting: "Entry count", requested: 5, effective: 5, source: "request", achieved: 3 },
        { key: "max_exposure", setting: "Max player exposure", requested: .8, effective: .8, source: "request", achieved: "3/5 requested entries; global limit 4" },
        { key: "max_lineups_per_primary_game", setting: "Max primary-game appearances", requested: 3, effective: 3, source: "request", achieved: { "CIN-JAX": 3 } },
        { key: "max_lineup_overlap", setting: "Max lineup overlap", requested: 4, effective: 4, source: "request", achieved: 4 },
        { key: "elevated_player_max_exposure", setting: "Elevated-player max exposure", requested: .4, effective: .4, source: "request", achieved: "2/5 requested entries; limit 2" },
        { key: "max_elevated_players_per_lineup", setting: "Per-lineup elevated max", requested: null, effective: null, source: "strategy_default", achieved: 1 },
      ],
      validation: { status: "failed", violations: ["entry_count"] },
      feasibility: { status: "underfilled", explanation: "Combined active limits", active_constraints: { max_lineup_overlap: 4 }, saturated_primary_games: ["CIN-JAX"], saturated_player_ids: [] },
    },
  } as OptimizerResponse;
  const rows = portfolioSettingsRows(optimizer);
  assert.equal(rows.length, 6);
  assert.equal(rows[1].requested, "80%");
  assert.equal(rows[4].effective, "40%");
  assert.equal(rows[5].requested, "Strategy default");
  assert.equal(rows[5].effective, "No additional cap");
  const html = buildOptimizerReportHtml(optimizer, { season: 2026, week: 4, slate: "SUNDAY_MAIN" });
  for (const label of ["Setting", "Requested", "Effective", "Source", "Achieved", "Saved portfolio settings", "40%", "2/5 requested entries; limit 2", "Underfilled portfolio · no limits relaxed", "Combined active limits"]) assert.ok(html.includes(label), label);
});


test("Saved failed reports can reopen after refresh while queued or unsaved failures cannot", () => {
  assert.equal(canOpenSavedOptimizerReport({ status: "failed", saved_report_available: true }), true);
  assert.equal(canOpenSavedOptimizerReport({ status: "failed", saved_report_available: false }), false);
  assert.equal(canOpenSavedOptimizerReport({ status: "queued", saved_report_available: true }), false);
  assert.equal(canOpenSavedOptimizerReport({ status: "running", saved_report_available: true }), false);
  assert.equal(canOpenSavedOptimizerReport({ status: "completed" }), true);
});


test("Overlap 5 and the per-lineup elevated-risk default persist independently", () => {
  const selected = { ...DEFAULT_LARGE_GPP_CONTROLS, maxLineupOverlap: 5 };
  assert.deepEqual(largeGppControlParams(selected), { max_lineup_overlap: 5 });
  const restored = parseSavedLargeGppControls(JSON.stringify(selected));
  assert.equal(restored.maxLineupOverlap, 5);
  assert.equal(restored.maxElevatedPerLineup, null);
  assert.deepEqual(largeGppControlParams(restored), { max_lineup_overlap: 5 });
});
