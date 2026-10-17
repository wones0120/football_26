import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { DEFAULT_LARGE_GPP_CONTROLS } from "../src/classicLargeGppControls.ts";
import { overlapFixtureRequest } from "./overlapFixtureRequest.ts";
import { buildOptimizerReportHtml } from "../src/optimizerReport.ts";
import { largeGppReadinessHtml } from "../src/classicReadinessReport.ts";
import type { OptimizerResponse } from "../src/api.ts";

test("Explicit offline fixture: queued API -> durable optimizer handler -> saved readiness -> result API -> HTML", () => {
  const root = fileURLToPath(new URL("../../", import.meta.url));
  const payload = overlapFixtureRequest("classic_large_gpp_v1", 5, 80, 3,
    { ...DEFAULT_LARGE_GPP_CONTROLS, maxLineupOverlap: 5 });
  Object.assign(payload.params, { max_players_per_team: 3, enforce_single_te: false,
    exclude_opponent_teams: ["DEN"], exclude_questionable: false });
  const run = spawnSync(root + ".venv/bin/python", ["backend/app/tests/product/overlap_ui_fixture.py"], {
    cwd: root, env: { ...process.env, PYTHONPATH: root }, input: JSON.stringify([payload]),
    encoding: "utf8", timeout: 120_000, maxBuffer: 16 * 1024 * 1024,
  });
  assert.equal(run.status, 0, run.stderr);
  const [result] = JSON.parse(run.stdout);
  assert.equal(result.executor, "durable optimizer handler");
  assert.equal(result.report.status, "completed");
  const ready = result.report.entry_readiness;
  assert.equal(ready.version, "classic_large_gpp_readiness_v1");
  assert.equal(ready.preview_valid, true);
  assert.equal(ready.entry_ready, false);
  assert.equal(ready.checks["Legal roster and requested portfolio constraints"].status, "PASS");
  assert.equal(ready.checks["Player/team/opponent identity"].status, "BLOCKER");
  assert.equal(ready.checks["Market/game environment"].status, "DEVELOPMENT_PREVIEW");
  assert.equal(ready.checks["Candidate-pool size"], undefined);
  assert.deepEqual(ready, result.saved_options.entry_readiness);
  for (const key of ["max_exposure", "max_lineup_overlap", "max_players_per_team", "max_players_per_game", "enforce_single_te", "exclude_opponent_teams", "exclude_questionable"]) {
    assert.deepEqual(result.saved_options[key], payload.params[key]);
  }
  const html = buildOptimizerReportHtml(result.report, {season: 2000, week: 1, slate: "SUNDAY_MAIN"});
  assert.match(html, /ENTRY READY: NO/);
  assert.doesNotMatch(html, /readiness was not evaluated/);
  assert.match(html, /Current entry availability clearance/);
  assert.match(html, /Actual player appearances by game/);
  assert.equal(result.report.game_appearances.roster_appearances, 45);
  assert.ok(result.report.execution_runtime.modules["classic_large_gpp_readiness.py"]);
});

test("Unavailable checks cannot become unqualified entry-ready; current assessment does not rewrite original", () => {
  const original = {status: "DEVELOPMENT_PREVIEW", entry_ready: false};
  const optimizer = {entry_readiness: original, readiness_assessment: {
    status: "READY", entry_ready: true, current_entry_clearance: "VERIFIED",
    checks: {Weather: {status: "UNAVAILABLE", reason: "<missing>"}}, scope: "present-time",
  }} as unknown as OptimizerResponse;
  const html = largeGppReadinessHtml(optimizer);
  assert.match(html, /ENTRY READY: NO/);
  assert.match(html, /Original saved readiness: DEVELOPMENT_PREVIEW/);
  assert.match(html, /&lt;missing&gt;/);
  assert.deepEqual(original, {status: "DEVELOPMENT_PREVIEW", entry_ready: false});
});

test("Certified coverage and unresolved quarantine populations remain separate and visible", () => {
  const optimizer = {data_readiness: {status: "NOT_READY", solver_called: false, override_used: false,
    required_sources: {}, pool_populations: {native_salary_rows: 78, canonically_resolved_salary_rows: 78,
      confirmed_unavailable: 0, role_ineligible: 0, unresolved: 1, quarantined_unresolved_evidence: 6, certified_generation_eligible: 71},
    projection_coverage: {complete_players: 71, required_players: 71},
    ownership_coverage: {complete_players: 71, required_players: 71},
    blocker_groups: {source_level: ["salary_native_draft_group_missing"], material_players: [{player: "Material player"}]},
    players: [{player: "Unknown backup", disposition: "quarantined_unresolved_evidence", availability: "unknown"}],
  }} as unknown as OptimizerResponse;
  const html = largeGppReadinessHtml(optimizer);
  assert.match(html, /71\/71 players/);
  assert.match(html, /Certified generation pool/);
  assert.match(html, /Quarantined unresolved evidence/);
  assert.match(html, /salary_native_draft_group_missing/);
  assert.match(html, /Material player/);
  assert.match(html, /Unknown backup/);
  assert.match(html, /Solver called: no/);
  assert.match(html, /ENTRY READY: NO/);
});

test("Saved-input validation cannot launch refresh, optimization, or change form preferences", () => {
  const component = readFileSync(new URL("../src/ClassicLargeGppReadinessReport.tsx", import.meta.url), "utf8");
  assert.match(component, /assessSavedOptimizerReadiness\(optimizer.job_id\)/);
  assert.doesNotMatch(component, /runOptimizer|set.*Controls|loadRaw|runPredictions|useEffect/);
  const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
  for (const name of ["launchWeeklyRun", "runOptimizerJob"]) {
    const handler = app.split("const " + name + " = async () => {")[1].split("\n  };" )[0];
    assert.ok(handler.indexOf("submittedClassicControls(") < handler.indexOf("await "));
  }
  for (const name of ["runSlateLoad", "runStartingQBs", "runBuildFeatures"]) {
    const handler = app.split("const " + name + " = async ")[1].split("\n  };" )[0];
    assert.doesNotMatch(handler, /setLargeGppControls|setMaxExposure|setNumLineups|setMaxPlayersPerTeam|setMaxPlayersPerGame|setEnforceSingleTE|setExcludeOpponent|setExcludePlayer|setLockedPlayer/);
  }
});

test("preliminary report shows the frozen research receipt and never presents normal clearance", () => {
  const optimizer = {strategy:"classic_large_gpp_v1",status:"completed",results:[[]],
    entry_readiness:{entry_ready:true,current_entry_clearance:"VERIFIED",checks:{invented:{status:"PASS"}}},
    analyst_handoff_applied:{checked_packet_sha256:"checked-packet",compatibility_sha256:"checked-compatibility"},
    preliminary_report:{entry_ready:false,snapshot_sha256:"frozen-research",assumption_manifest_sha256:"frozen-assumptions",
      normal_readiness:{status:"ERROR",reason_codes:["player_status_missing"],required_sources:{market:{status:"READY"},player_status:{status:"NOT_READY"}}},
      assumption_manifest:{declared_at:"2026-10-14T16:00:00Z",exclude_player_ids:["unknown"],source_truth:"Original facts unchanged",players:[{player:"Unknown <player>",availability:"unknown",reason_codes:["player_status_missing"]}]}}} as unknown as OptimizerResponse;
  const html=largeGppReadinessHtml(optimizer);
  for (const value of ["Preliminary research · not entry cleared","ENTRY READY: NO","frozen-research","frozen-assumptions","checked-packet","checked-compatibility","NOT_READY","player_status_missing","Unknown &lt;player&gt;"]) assert.ok(html.includes(value),value);
  assert.ok(!html.includes("Solver called: unrecorded") && !html.includes("Not frozen") && !html.includes("ENTRY READY: YES"));
});
