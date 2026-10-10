import assert from "node:assert/strict";
import test from "node:test";
import { defaultLineupControls, lineupControlParams, parseLineupControls, restoreLineupControls } from "../src/lineupControls.ts";

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
