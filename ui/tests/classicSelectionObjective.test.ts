import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { classicSelectionParams } from "../src/classicSelectionObjective.ts";

test("highest mean request clears only player locks and scenario scoring, retaining other settings", () => {
  const prior = {num_lineups:5,max_exposure:1,locked_player_ids:["canonical"],locked_players:["player"],
    analyst_strategy:"MERGED_SCENARIOS",analyst_optimization_intent:"EXPECTED_GAME",analyst_teammate_choice:{required:"x"},
    minimum_rb_salary:4500,minimum_qb_salary:4500,enforce_single_te:true,force_favored_rb:1,force_favored_dst:1,
    max_players_per_team:4,max_players_per_game:5,exclude_opponent_teams:["DEN"],exclude_questionable:true,season_ppg_top_pct_qb:50};
  const next = classicSelectionParams(prior,true);
  assert.equal(next.classic_selection_objective,"baseline_mean");assert.equal(next.num_lineups,1);
  assert.deepEqual(next.locked_player_ids,[]);assert.deepEqual(next.locked_players,[]);
  assert.equal(next.analyst_strategy,undefined);assert.equal(next.analyst_teammate_choice,undefined);
  assert.equal(next.analyst_handoff_mode,"BASELINE");assert.equal(next.analyst_optimization_intent,"MIXED");
  for (const key of ["minimum_rb_salary","minimum_qb_salary","enforce_single_te","force_favored_rb","force_favored_dst","max_players_per_team","max_players_per_game","exclude_opponent_teams","exclude_questionable","season_ppg_top_pct_qb"]) assert.deepEqual(next[key],prior[key as keyof typeof prior]);
  assert.equal(prior.num_lineups,5);assert.deepEqual(prior.locked_player_ids,["canonical"]);
});

test("ordinary/Showdown requests preserve their existing settings", () => {
  const params={captain_max_exposure:.5,captain_position_exception_ids:["JSN"],analyst_optimization_intent:"EXPECTED_GAME",locked_player_ids:["canonical"]};
  assert.deepEqual(classicSelectionParams(params,false),params);
  const source=readFileSync(new URL('../src/App.tsx',import.meta.url),'utf8');
  assert.match(source,/const highestProjection = contestFormat === "classic"/);
  assert.match(source,/Highest baseline projection · optional stacks/);
  assert.match(source,/params = classicSelectionParams\(params, highestProjection\)/);
});

test("saved highest objective is recovered from the persisted player report on older API responses", async () => {
  const {savedHighestProjectionReport} = await import("../src/classicSelectionObjective.ts");
  const report={objective_label:"Highest baseline projection",solver_status:"Optimal",optimal:true,locked_player_ids:[],input_snapshot_sha256:"frozen",base_mean:133.18};
  assert.deepEqual(savedHighestProjectionReport({results:[[{selection_objective:"baseline_mean",highest_projection_report:report}]]}),report);
  assert.equal(savedHighestProjectionReport({results:[[{projection:20}]]}),null);
});
