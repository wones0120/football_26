import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { preliminaryRunParams, preliminaryScopeIssue, analystFocusedRunIssue, type PreliminarySnapshot } from "../src/preliminaryResearch.ts";
const snapshot = {scope:{season:2026,week:6,slate:"SUNDAY_MAIN",contest_format:"classic"},entry_ready:false} as PreliminarySnapshot;
test("preliminary scoped input rejects different slate and never asserts entry clearance", () => {
  assert.equal(preliminaryScopeIssue(snapshot,{season:2026,week:6,slate:"SUNDAY_MAIN"}),null);
  assert.ok(preliminaryScopeIssue(snapshot,{season:2026,week:7,slate:"SUNDAY_MAIN"}));
  assert.ok(preliminaryScopeIssue({...snapshot,entry_ready:true} as unknown as PreliminarySnapshot,{season:2026,week:6,slate:"SUNDAY_MAIN"}));
});
test("explicit rank choice changes only this request and retains all other constraints", () => {
  const params={exclude_questionable:true,availability_overrides:[],season_ppg_top_pct_qb:50,season_ppg_top_pct_rb:25,num_lineups:5,minimum_rb_salary:4500,max_exposure:.8,locked_player_ids:['canonical'],analyst_packet_sha256:'packet',analyst_challenger_enabled:true};
  const research=preliminaryRunParams(params,true);assert.equal(research.season_ppg_top_pct_qb,undefined);assert.equal(research.season_ppg_top_pct_rb,undefined);assert.equal(params.season_ppg_top_pct_rb,25);
  for(const key of ['num_lineups','minimum_rb_salary','max_exposure','locked_player_ids','analyst_packet_sha256','analyst_challenger_enabled']) assert.deepEqual(research[key],params[key as keyof typeof params]);
  assert.deepEqual(preliminaryRunParams(params,false),params);
});
test("Q preference and no availability/readiness override remain enforced", () => {
  assert.throws(()=>preliminaryRunParams({exclude_questionable:false},true),/Exclude questionable/);
  assert.throws(()=>preliminaryRunParams({exclude_questionable:true,availability_overrides:[{}]},true),/availability/);
  assert.throws(()=>preliminaryRunParams({exclude_questionable:true,prepared_input_job_id:'normal'},true),/explicit preliminary/);
});
test("UI uses dynamic snapshot/finished preparation selectors and explicit assumptions, separate from ordinary run", () => {
  const source=readFileSync(new URL('../src/PreliminaryClassicControls.tsx',import.meta.url),'utf8'),app=readFileSync(new URL('../src/App.tsx',import.meta.url),'utf8');
  assert.match(source,/fetchPreliminarySnapshots\(scope\)/);assert.match(source,/acceptedAssumptions/);assert.match(source,/No season-average rank restriction for this research run only/);assert.match(source,/Generate preliminary research lineups/);
  assert.ok(!source.includes('1d4bd679') && !source.includes('e7227a48'));
  assert.match(app,/preliminaryRunParams\(\{ \.\.\.optimizerParams\(\), \.\.\.analystOptimizerParams/);assert.match(app,/runPreliminaryOptimizer\(snapshot/);
});

test("focused generation blocks unloaded, empty or unsupported stories; original strategy remains usable", () => {
  const focused = {selected_strategy:"MERGED_SCENARIOS" as const,focus_mode:"SELECTED_ONLY" as const,focus_ids:[] as string[],scenario_options:[{scenario_id:"den-passing",label:"Denver passing what-if",game_ids:["SEA_DEN"],focus_applicable:true},{scenario_id:"mixed-stress",label:"Composite",game_ids:["SEA_DEN"],focus_applicable:false}]};
  assert.match(analystFocusedRunIssue({...focused,scenario_options:undefined})!,/not loaded/);
  assert.match(analystFocusedRunIssue(focused)!,/at least one/);
  assert.ok(analystFocusedRunIssue({...focused,focus_ids:["mixed-stress"]}));
  assert.equal(analystFocusedRunIssue({...focused,focus_ids:["den-passing"]}),null);
  assert.equal(analystFocusedRunIssue({...focused,selected_strategy:"CONSTRUCTION"}),null);
});

test("fresh research preparation requests the unknown-and-questionable receipt policy", () => {
  const api = readFileSync(new URL("../src/api.ts", import.meta.url), "utf8");
  const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
  const controls = readFileSync(new URL("../src/PreliminaryClassicControls.tsx", import.meta.url), "utf8");
  assert.match(api, /injury_policy: "exclude_unknown_and_questionable"/);
  assert.match(app, /preliminary_research: preliminary/);
  assert.match(app, /if \(preliminary\) return await freezePreliminarySnapshot/);
  assert.match(controls, /Prepare preliminary research inputs/);
  assert.match(controls, /Excluded from research; original facts unchanged/);
});
