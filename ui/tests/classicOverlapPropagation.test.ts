import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { classicOptimizerControlParams } from "../src/classicOptimizerControls.ts";
import { DEFAULT_LARGE_GPP_CONTROLS, parseSavedLargeGppControls } from "../src/classicLargeGppControls.ts";
import { portfolioSettingsRows } from "../src/classicPortfolioReport.ts";
import { overlapFixtureRequest } from "./overlapFixtureRequest.ts";
import type { OptimizerResponse } from "../src/api.ts";

test("A malformed sibling preference cannot reset valid overlap 5 on reload", () => {
  const controls = parseSavedLargeGppControls(JSON.stringify({
    maxLineupOverlap: 5, elevatedExposurePercent: 101, maxElevatedPerLineup: null,
  }));
  assert.equal(controls.maxLineupOverlap, 5);
  assert.equal(controls.elevatedExposurePercent, null);
});

test("Large overlap is independent of Small/Showdown policy and snapshots survive later edits", () => {
  const form = { largeGppControls: { ...DEFAULT_LARGE_GPP_CONTROLS, maxLineupOverlap: 5 },
    primaryGameCap: 3, minimumUniqueness: 4, maxPlayersPerTeam: 4, maxPlayersPerGame: 5 };
  const snapshot = classicOptimizerControlParams("classic_large_gpp_v1", form);
  assert.equal(snapshot.max_lineup_overlap, 5);
  assert.equal(snapshot.minimum_uniqueness, undefined);
  const small = classicOptimizerControlParams("classic_small_field_gpp", form);
  assert.equal(small.max_lineup_overlap, undefined);
  assert.equal(small.minimum_uniqueness, 4);
  assert.deepEqual(classicOptimizerControlParams("showdown_gpp_v1", form), {});
  form.largeGppControls.maxLineupOverlap = 7;
  assert.equal(snapshot.max_lineup_overlap, 5);
  form.largeGppControls.maxLineupOverlap = 0;
  assert.equal(classicOptimizerControlParams("classic_large_gpp_v1", form).max_lineup_overlap, 0);
});

test("Frontend Large 5/80/game3/overlap -> queued API JSON -> real service/solver -> persisted report", () => {
  const overlaps = [5, 4, 6, 7, null];
  const payloads = overlaps.map(maxLineupOverlap => overlapFixtureRequest("classic_large_gpp_v1", 5, 80, 3,
    parseSavedLargeGppControls(JSON.stringify({ ...DEFAULT_LARGE_GPP_CONTROLS, maxLineupOverlap }))));
  // This assertion is deliberately outside the backend. Omission cannot pass as default.
  assert.equal(payloads[0].params.max_lineup_overlap, 5);
  const root = fileURLToPath(new URL("../../", import.meta.url));
  const run = spawnSync(root + ".venv/bin/python", ["backend/app/tests/product/overlap_ui_fixture.py"], {
    cwd: root, env: { ...process.env, PYTHONPATH: root }, input: JSON.stringify(payloads),
    encoding: "utf8", timeout: 120_000, maxBuffer: 16 * 1024 * 1024,
  });
  assert.equal(run.status, 0, run.stderr);
  const results = JSON.parse(run.stdout);
  const evidence = results.map((r: any, index: number) => {
    const overlap = overlaps[index];
    const effective = overlap ?? 7;
    assert.equal(r.fixture_only, true);
    assert.equal(r.api_request.params.max_lineup_overlap ?? null, overlap);
    assert.equal(r.saved_options.max_lineup_overlap ?? null, overlap);
    const contract = r.report.effective_strategy_contract;
    assert.equal(contract.requested.max_lineup_overlap, overlap);
    assert.equal(contract.effective.max_lineup_overlap, effective);
    assert.equal(contract.sources.max_lineup_overlap, overlap === null ? "strategy_default" : "request");
    assert.equal(r.report.status, "completed");
    const audit = r.report.portfolio_controls_report;
    const row = audit.settings.find((r: any) => r.key === "max_lineup_overlap");
    assert.equal(row.requested, overlap);
    assert.equal(row.effective, effective);
    assert.equal(audit.validation.status, "verified");
    assert.ok(row.achieved <= effective);
    // Separate canonical-ID calculation, independent of the saved achieved field.
    const sets = r.report.results.map((lineup: any[]) => new Set(lineup.map(p => p.player_id)));
    for (let i = 0; i < sets.length; i++) for (let j = 0; j < i; j++) {
      assert.ok([...sets[i]].filter(id => sets[j].has(id)).length <= effective);
    }
    const savedRow = portfolioSettingsRows(r.report as OptimizerResponse).find(r => r.setting === "Max lineup overlap");
    assert.equal(savedRow?.requested, overlap === null ? "Strategy default" : String(overlap));
    return { overlap, api_params: r.api_request.params, saved_overlap: r.saved_options.max_lineup_overlap ?? null,
      contract_requested: contract.requested, contract_effective_overlap: effective, row, validation: audit.validation };
  });
  if (process.env.OVERLAP_EVIDENCE_PATH) writeFileSync(process.env.OVERLAP_EVIDENCE_PATH, JSON.stringify(evidence, null, 2));
});

test("Normal entry points use the same builder with shared user lineup controls", () => {
  const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
  assert.match(app, /lineupControlParams\(lineupControls, contestFormat\)/);
  for (const name of ["launchWeeklyRun", "runOptimizerJob"]) {
    const handler = app.split("const " + name + " = async () => {")[1].split("\n  };")[0];
    assert.match(handler, /optimizerParams\(\)/);
    assert.doesNotMatch(handler, /submittedClassicControls|max_lineup_overlap/);
  }
});
