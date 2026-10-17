import test from "node:test";
import assert from "node:assert/strict";
import { analystOptimizerParams, analystPacketScopeIssue, captainAnalystEnabled, type AnalystPacketMetadata } from "../src/analystPacket.ts";
const packet: AnalystPacketMetadata = { contract_id: "wones_football_analyst_v1", packet_id: "packet", analyst_name: "Wones Football Analyst",
  analyst_packet_sha256: "a".repeat(64), decision_at: "2026-10-13T14:00:00Z", frozen_at: "2026-10-13T14:00:00Z", assessment_count: 2,
  games: [{game_id:"SEA_DEN",season:2026,week:6,teams:["SEA","DEN"],kickoff_at:"2026-10-16T00:15:00Z",format_membership:{SHOWDOWN:"confirmed_in_scope",CLASSIC:"out_of_scope_sunday_main"}},
    {game_id:"LAC_KC",season:2026,week:6,teams:["LAC","KC"],kickoff_at:"2026-10-18T20:25:00Z",format_membership:{CLASSIC:"confirmed_in_scope"}}] };
test("selected hash flows to both optimizer formats and clear produces baseline params", () => {
  for (const format of ["classic", "showdown"] as const) {
    assert.equal(analystPacketScopeIssue(packet,2026,6,format),null);
    assert.deepEqual(analystOptimizerParams(packet),{analyst_packet_sha256:"a".repeat(64),analyst_candidates_per_thesis:2,analyst_strategy:"CONSTRUCTION"});
  }
  assert.deepEqual(analystOptimizerParams(null),{});
});
test("wrong week, season and unconfirmed format cannot be selected", () => {
  assert.ok(analystPacketScopeIssue(packet,2026,7,"showdown"));
  assert.ok(analystPacketScopeIssue(packet,2025,6,"classic"));
  assert.ok(analystPacketScopeIssue({...packet,games:[packet.games[0]]},2026,6,"classic"));
});

test("merged scenario strategy is explicit in persisted request params", () => {
  assert.equal(analystOptimizerParams({...packet,scenario_count:3,selected_strategy:"MERGED_SCENARIOS"}).analyst_strategy,"MERGED_SCENARIOS");
});

test("Captain Analyst activates only for its explicit packet contract and Showdown merged strategy", () => {
  const enabled = {...packet, scenario_count: 2, captain_analysis_contract: "captain_analysis_v1", selected_strategy: "MERGED_SCENARIOS" as const};
  assert.equal(captainAnalystEnabled(enabled, "showdown"), true);
  assert.equal(captainAnalystEnabled(enabled, "classic"), false);
  assert.equal(captainAnalystEnabled({...enabled, selected_strategy: "CONSTRUCTION"}, "showdown"), false);
  assert.equal(captainAnalystEnabled({...enabled, captain_analysis_contract: null}, "showdown"), false);
  assert.deepEqual(analystOptimizerParams(enabled, "showdown"), {analyst_packet_sha256: "a".repeat(64), analyst_candidates_per_thesis: 2, analyst_strategy: "MERGED_SCENARIOS"});
});

test("blind-spot hunter is explicit opt-in only for merged packet requests", () => {
  assert.equal(analystOptimizerParams({...packet,selected_strategy:"MERGED_SCENARIOS"}).analyst_challenger_enabled,undefined);
  assert.equal(analystOptimizerParams({...packet,selected_strategy:"MERGED_SCENARIOS",challenger_enabled:true}).analyst_challenger_enabled,true);
  assert.equal(analystOptimizerParams({...packet,selected_strategy:"CONSTRUCTION",challenger_enabled:true}).analyst_challenger_enabled,undefined);
});


test("scenario-first mode and optional hunters are scoped to Classic", () => {
  const enabled = {...packet, selected_strategy:"MERGED_SCENARIOS" as const, challenger_enabled:true, teammate_enabled:true};
  assert.equal(analystOptimizerParams(enabled,"classic").analyst_portfolio_mode,"SCENARIO_FIRST");
  assert.equal(analystOptimizerParams(enabled,"showdown").analyst_portfolio_mode,undefined);
  assert.equal(analystOptimizerParams(enabled,"showdown").analyst_challenger_enabled,undefined);
});

test('selected-only focus persists exact IDs in both formats and suppresses unselected hunter branches', () => {
  const selected = { ...packet, selected_strategy: 'MERGED_SCENARIOS' as const, focus_mode: 'SELECTED_ONLY' as const, focus_ids: ['declared_story'], challenger_enabled: true, teammate_enabled: true };
  for (const format of ['classic', 'showdown'] as const) {
    const params = analystOptimizerParams(selected, format);
    assert.equal(params.analyst_scenario_focus_mode, 'SELECTED_ONLY');
    assert.deepEqual(params.analyst_scenario_focus_ids, ['declared_story']);
    assert.equal(params.analyst_challenger_enabled, undefined);
    assert.equal(params.analyst_teammate_enabled, undefined);
  }
  assert.equal(analystOptimizerParams({ ...selected, selected_strategy: 'CONSTRUCTION' }).analyst_scenario_focus_mode, undefined);
});

test('explicit unchecked mixed Classic tools survive automatic preparation defaults', () => {
  const selected = { ...packet, selected_strategy: 'MERGED_SCENARIOS' as const, challenger_enabled: false, teammate_enabled: false };
  const params = analystOptimizerParams(selected, 'classic');
  assert.equal(params.analyst_challenger_enabled, false);
  assert.equal(params.analyst_teammate_enabled, false);
  const unspecified = analystOptimizerParams({ ...packet, selected_strategy: 'MERGED_SCENARIOS' }, 'classic');
  assert.equal(unspecified.analyst_challenger_enabled, undefined);
  assert.equal(unspecified.analyst_teammate_enabled, undefined);
  for (const scoped of [analystOptimizerParams(selected, 'showdown'), analystOptimizerParams({ ...selected, focus_mode: 'SELECTED_ONLY', focus_ids: ['story'] }, 'classic')]) {
    assert.equal(scoped.analyst_challenger_enabled, undefined);
    assert.equal(scoped.analyst_teammate_enabled, undefined);
  }
});
