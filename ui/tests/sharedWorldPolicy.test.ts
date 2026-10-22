import assert from "node:assert/strict";
import test from "node:test";
import { SHARED_WORLD_POLICY, sharedWorldEvidence, sharedWorldHtml } from "../src/sharedWorldPolicy.ts";

test("other saved strategies do not acquire shared-world claims", () => {
  assert.equal(sharedWorldEvidence({policy_id:"legacy"}), null);
  assert.equal(sharedWorldHtml(undefined), "");
});

test("saved anchor order, unknowns and canonical roster identity remain visible", () => {
  const report={policy_id:SHARED_WORLD_POLICY,status:"completed",requested:2,achieved:2,
    anchor_world_id:"expected",probability_status:"Likelihood unknown",
    frozen_world_inputs:[{world_id:"counter",mechanism:"<supported>",counterevidence:["Shared failure"],unknowns:["No probability"],source_refs:["official"]}],
    selection_steps:[{rank:1,roster:[{player_master_id:"p",role:"CPT"}],anchor_conditional_mean_points:90,
      original_base_expected_points:80,maximum_incremental_gain_points:0,
      strongest_admissible_alternative:{roster:[{player_master_id:"q",role:"FLEX"}]}},
      {rank:2,roster:[{player_master_id:"q",role:"CPT"}],original_base_expected_points:100}]};
  const players=[{player_id:"p",name:"Player <one>"},{player_master_id:"q",player_name:"Player two"}];
  const before=JSON.stringify(report);
  const result=sharedWorldEvidence(report,players)!;
  assert.deepEqual(result.steps.map(s=>s.rank),[1,2]);
  assert.equal(result.steps[0].roster,"CPT: Player <one>");
  assert.equal(result.steps[0].gain,"0.00");
  assert.equal(result.steps[1].anchorMean,"unknown");
  assert.match(result.coverageSummary,/No incremental scenario coverage achieved/);
  const html=sharedWorldHtml(report,players);
  assert.match(html,/Player &lt;one&gt;/);
  assert.match(html,/&lt;supported&gt;/);
  assert.match(html,/FLEX: Player two/);
  assert.match(html,/Counterevidence: Shared failure/);
  assert.match(html,/not demonstrated scenario diversification/);
  assert.equal(JSON.stringify(report),before);
});

test("saved count component changes distinguish actual OUT from linear-only delta",()=>{
  const report={policy_id:SHARED_WORLD_POLICY,frozen_world_inputs:[{world_id:"sourced",count_component_response:{response:{players:[{
    player_master_id:"p",base_fp:8,conditional_mean:0,conditional_delta_points:-8,linear_component_delta_points:-5,
    supported_components:["rushing_yards"],inactive_override:true,assumption:"Conditional <source>",anchor_inconsistency:true
  }]}}}],selection_steps:[]};
  const html=sharedWorldHtml(report,[{player_id:"p",name:"Known player"}]);
  assert.match(html,/base FP 8.00 → conditional FP 0.00/);
  assert.match(html,/change -8.00; matched linear change -5.00/);
  assert.match(html,/Factual OUT: all world production zero/);
  assert.match(html,/anchoring inconsistency flagged/);
  assert.match(html,/Conditional &lt;source&gt;/);
});
