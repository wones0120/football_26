import test from "node:test";
import assert from "node:assert/strict";
import {scenarioIssue,scenarioKey,scenarioParams} from "../src/scenarioMode.ts";
import {optimizerHasPreparedInputs} from "../src/preparedOptimizer.ts";

const mode={team:"BUF",passing_factor:1.2,rushing_factor:1,rationale:"Authored passing game"};
test("off preserves all baseline settings; on retains explicit controls and locks",()=>{
 const baseline={num_lineups:5,locked_player_ids:["canonical"],max_players_per_team:3,analyst_strategy:"MERGED_SCENARIOS"};
 assert.deepEqual(scenarioParams(baseline),baseline);
 const selected=scenarioParams(baseline,mode);
 assert.equal(selected.num_lineups,1);assert.deepEqual(selected.locked_player_ids,["canonical"]);
 assert.equal(selected.max_players_per_team,3);assert.equal(selected.analyst_strategy,undefined);
 assert.equal(baseline.num_lineups,5);
});
test("bounded typed factors, explanation and edited assumptions",()=>{
 assert.equal(scenarioIssue(mode),null);
 assert.ok(scenarioIssue({...mode,rationale:" "}));assert.ok(scenarioIssue({...mode,passing_factor:2}));
 assert.ok(scenarioIssue({...mode,passing_factor:1}));
 assert.notEqual(scenarioKey(mode),scenarioKey({...mode,rushing_factor:.8}));
});
test("Showdown comparison keeps Captain preferences and uses the common scenario contract",()=>{
 const original={num_lineups:5,captain_positions:['WR','RB'],no_two_qbs:true,classic_selection_objective:'baseline_mean'};
 const selected=scenarioParams(original,mode,'showdown');
 assert.equal(selected.classic_selection_objective,undefined);
 assert.equal(selected.num_lineups,1);assert.deepEqual(selected.captain_positions,['WR','RB']);
 assert.equal(selected.no_two_qbs,true);assert.equal(original.num_lineups,5);
});
test("prepared selection changes require another Prepare, including turning off",()=>{
 const scope={season:2026,week:4,slate:"MAIN"};
 const status:any={scope,build_current:true,prelock:true,jobs:[],latest_build:{...scope,action:"prepare",contest_format:"classic",data_readiness:{status:"READY"},availability_overrides:[],scenario_mode:{config:mode}}};
 assert.equal(optimizerHasPreparedInputs(status,scope,"classic",[],null,mode),true);
 assert.equal(optimizerHasPreparedInputs(status,scope,"classic",[],null,{...mode,passing_factor:1.3}),false);
 assert.equal(optimizerHasPreparedInputs(status,scope,"classic",[],null),false);
 delete status.latest_build.scenario_mode;
 assert.equal(optimizerHasPreparedInputs(status,scope,"classic",[],null),true);
});

test("primary scoring accepts unchanged volume and invalidates sensitivity receipts",()=>{
 const primary={...mode,passing_factor:1,scoring_mode:"new_model_primary" as const};
 assert.equal(scenarioIssue(primary),null);
 assert.notEqual(scenarioKey(primary),scenarioKey({...primary,scoring_mode:"sensitivity"}));
 assert.equal((scenarioParams({},primary,"showdown").scenario_mode as typeof primary).scoring_mode,"new_model_primary");
});
