import assert from "node:assert/strict";
import test from "node:test";
import { defaultLineupControls, lineupControlParams, parseLineupControls, restoreLineupControls, serializeLineupControls } from "../src/lineupControls.ts";

test("both strategies default to five and preserve explicit volume and construction settings", () => {
  for (const format of ["classic", "showdown"] as const) {
    const defaults = defaultLineupControls(format);
    assert.equal(lineupControlParams(defaults, format).num_lineups, 5);
    const controls = { ...defaults, numLineups: 5, maxExposure: 80, maxLineupOverlap: 4, elevatedExposurePercent: 40, maxElevatedPerLineup: 1,
      primaryGameCap: 2, maxPlayersPerTeam: format === "classic" ? 3 : 4, captainMaxExposure: 60 };
    const params = lineupControlParams(controls, format);
    assert.equal(params.num_lineups, 5);
    assert.equal(params.max_exposure, .8);
    assert.equal(params.max_lineup_overlap, 4);
    assert.equal(params.elevated_player_max_exposure, .4);
    assert.equal(params.max_elevated_players_per_lineup, 1);
    assert.equal(params.max_players_per_team, controls.maxPlayersPerTeam);
    assert.equal(params.max_lineups_per_primary_game, format === "classic" ? 2 : undefined);
    assert.equal(params.captain_max_exposure, format === "showdown" ? .6 : undefined);
    assert.equal(params.soft_scenario_diversity, undefined);
  }
});

test("settings survive reload per format and old Classic preferences migrate", () => {
  const legacy = JSON.stringify({ numLineups: 5, maxExposure: 80, maxLineupOverlap: 5, maxElevatedPerLineup: null });
  const restored = restoreLineupControls(null, legacy);
  assert.equal(restored.classic.numLineups, 5);
  assert.equal(restored.classic.maxLineupOverlap, 5);
  assert.equal(restored.showdown.numLineups, 5);
  restored.showdown.numLineups = 3;
  restored.showdown.captainMaxExposure = 60;
  assert.deepEqual(restoreLineupControls(JSON.stringify(restored), legacy), restored);
  assert.equal(parseLineupControls('{"numLineups":0,"maxLineupOverlap":4}', "showdown").maxLineupOverlap, 4);
  assert.equal(parseLineupControls('{"numLineups":0,"maxLineupOverlap":4}', "showdown").numLineups, 5);
});

test("invalid limits are rejected before queuing", () => {
  const defaults = defaultLineupControls("showdown");
  for (const change of [{ numLineups: 0 }, { numLineups: 501 }, { numLineups: 1.5 }, { maxExposure: NaN },
    { maxLineupOverlap: 7 }, { maxElevatedPerLineup: 7 }, { maxPlayersPerTeam: 2 }, { captainMaxExposure: 101 }]) {
    assert.throws(() => lineupControlParams({ ...defaults, ...change }, "showdown"));
  }
});

test("hundreds of lineups submit and survive reload with matching primary-game limits", () => {
  for (const format of ["classic", "showdown"] as const) {
    for (const count of [100, 150, 300, 500]) {
      const controls = { ...defaultLineupControls(format), numLineups: count, primaryGameCap: count };
      assert.equal(lineupControlParams(controls, format).num_lineups, count);
      assert.deepEqual(parseLineupControls(JSON.stringify(controls), format), controls);
    }
  }
});

test("Captain minimum salary serializes, persists, clears and applies separately to Classic", () => {
  const controls = { ...defaultLineupControls("showdown"), minimumPlayerSalary: 1700 };
  assert.equal(lineupControlParams(controls, "showdown").minimum_player_salary, 1700);
  assert.equal(parseLineupControls(JSON.stringify(controls), "showdown").minimumPlayerSalary, 1700);
  assert.equal(lineupControlParams({...defaultLineupControls("classic"), minimumPlayerSalary: 3500}, "classic").minimum_player_salary, 3500);
  assert.equal(lineupControlParams({...controls, minimumPlayerSalary: null}, "showdown").minimum_player_salary, undefined);
  for (const invalid of [-1, 1.5, 50001, NaN]) assert.throws(() => lineupControlParams({...controls, minimumPlayerSalary: invalid}, "showdown"));
});


test("Captain defaults allow 4–2 and 3–3, migrate old five-player caps once, and preserve new overrides", () => {
  const controls = restoreLineupControls(null, null);
  assert.equal(lineupControlParams(controls.showdown, "showdown").max_players_per_team, 4);
  controls.showdown.maxPlayersPerTeam = 5;
  assert.equal(restoreLineupControls(JSON.stringify(controls), null).showdown.maxPlayersPerTeam, 4);
  assert.equal(restoreLineupControls(serializeLineupControls(controls), null).showdown.maxPlayersPerTeam, 5);
  controls.showdown.maxPlayersPerTeam = 3;
  assert.equal(restoreLineupControls(JSON.stringify(controls), null).showdown.maxPlayersPerTeam, 3);
  assert.equal(controls.classic.maxPlayersPerTeam, 4);
});


test("Classic position salary defaults, clearing, persistence and Captain isolation", () => {
  const controls = restoreLineupControls(null, null);
  assert.equal(lineupControlParams(controls.classic, "classic").minimum_qb_salary, 4500);
  assert.equal(lineupControlParams(controls.classic, "classic").minimum_rb_salary, 4500);
  controls.classic.minimumQbSalary = null;
  controls.classic.minimumRbSalary = 5000;
  const restored = restoreLineupControls(serializeLineupControls(controls), null);
  assert.equal(restored.classic.minimumQbSalary, null);
  assert.equal(lineupControlParams(restored.classic, "classic").minimum_rb_salary, 5000);
  assert.equal(lineupControlParams(restored.showdown, "showdown").minimum_qb_salary, undefined);
  assert.throws(() => lineupControlParams({...controls.classic, minimumRbSalary: -1}, "classic"));
});


test("Classic season-rank defaults serialize, migrate missing fields, persist overrides and omit Captain", () => {
  const restored = restoreLineupControls(JSON.stringify({classic:{minimumQbSalary:null}}),null);
  const p = lineupControlParams(restored.classic,"classic");
  assert.deepEqual([p.season_ppg_top_pct_qb,p.season_ppg_top_pct_rb,p.season_ppg_top_pct_wr,p.season_ppg_top_pct_te],[50,25,50,25]);
  restored.classic.seasonRankRb=null; restored.classic.seasonRankQb=75;
  const next=restoreLineupControls(serializeLineupControls(restored),null);
  assert.equal(next.classic.seasonRankRb,null);
  assert.equal(lineupControlParams(next.classic,"classic").season_ppg_top_pct_qb,75);
  assert.equal(lineupControlParams(next.classic,"classic").season_ppg_top_pct_rb,undefined);
  assert.equal(lineupControlParams({...next.showdown,seasonRankQb:50},"showdown").season_ppg_top_pct_qb,undefined);
  assert.throws(()=>lineupControlParams({...next.classic,seasonRankTe:30},"classic"));
});

test("favored position controls default RB/TE/DST on, serialize independently, persist, and omit Captain", () => {
  const defaults = defaultLineupControls("classic");
  for (const pos of ["qb", "rb", "wr", "te", "dst"]) assert.equal(lineupControlParams(defaults, "classic")[`force_favored_${pos}`], ["rb", "te", "dst"].includes(pos) ? 1 : 0);
  const selected = { ...defaults, favoredRb: 1, favoredDst: 1 };
  const restored = parseLineupControls(JSON.stringify(selected), "classic");
  assert.equal(restored.favoredRb, 1);
  assert.equal(restored.favoredDst, 1);
  assert.equal(lineupControlParams(restored, "classic").force_favored_rb, 1);
  assert.equal(lineupControlParams(restored, "classic").force_favored_qb, 0);
  assert.equal(lineupControlParams(restored, "showdown").force_favored_rb, undefined);
  assert.equal(parseLineupControls('{"favoredRb":2}', "classic").favoredRb, 1);
});


test("favored defaults migrate once and all later user overrides persist", () => {
  const old = { classic: { favoredQb: 1, favoredRb: 0, favoredWr: 1, favoredTe: 0, favoredDst: 0 } };
  const migrated = restoreLineupControls(JSON.stringify(old), null);
  assert.deepEqual([migrated.classic.favoredQb, migrated.classic.favoredRb, migrated.classic.favoredWr, migrated.classic.favoredTe, migrated.classic.favoredDst], [0, 1, 0, 1, 1]);
  Object.assign(migrated.classic, { favoredQb: 1, favoredRb: 0, favoredWr: 1, favoredTe: 0, favoredDst: 0 });
  assert.deepEqual(restoreLineupControls(serializeLineupControls(migrated), null), migrated);
});
