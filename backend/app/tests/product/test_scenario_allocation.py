from copy import deepcopy
from collections import Counter

import pytest

from backend.app.product_services.scenario_allocation import AllocationControls,build_ideas,plan_slots,conditional_world,dependence_audit,generate_allocated
from scripts.run_merged_analyst_fixture import scenario_fixture


def supported_fixture():
    packet,snapshot=scenario_fixture('CLASSIC')
    for p in packet['players']:
        p['workload_evidence']['historical']={channel+'_mean_3':dict(value=(20 if p['position']=='RB' else 2) if channel=='carries' else (8 if p['position'] in {'WR','TE'} else 2),status='observed',available=True) for channel in ['targets','carries']}
    return packet,snapshot


def test_plan_precedes_solves_and_cosmetic_labels_do_not_create_new_ideas():
    packet,snapshot=supported_fixture();controls=AllocationControls()
    # Add renamed copies of one primary game world: canonical idea identities dedup.
    single=deepcopy(packet['scenario_assumptions']['scenarios'][0]);single['assumptions']=single['assumptions'][:2]
    packet['scenario_assumptions']['scenarios']=[{**deepcopy(single),'scenario_id':'renamed_'+str(i)} for i in range(5)]
    ideas,_=build_ideas(packet,snapshot['players'],controls)
    assert len({i['idea_id'] for i in ideas})==len(ideas)==2
    plan=plan_slots(ideas,5,controls)
    assert plan['phase']=='before_any_roster_solve'
    assert any(slot['repeated'] for slot in plan['slots'])
    assert all(slot['repetition_justification'] for slot in plan['slots'])


def test_conserved_meaningful_budgets_change_pass_and_rush_in_opposite_directions():
    packet,snapshot=supported_fixture();scenario=deepcopy(packet['scenario_assumptions']['scenarios'][0]);scenario['assumptions']=scenario['assumptions'][:2];packet['scenario_assumptions']['scenarios']=[scenario]
    ideas,_=build_ideas(packet,snapshot['players'],AllocationControls())
    worlds=[conditional_world(i,snapshot['players'],packet,AllocationControls()) for i in ideas]
    for world in worlds:
        budget=world['opportunity_budget']
        assert budget['conditional_targets']+budget['conditional_carries']==pytest.approx(100)
        assert (budget['pass_ratio']-1)*(budget['rush_ratio']-1)<0
    assert worlds[0]['opportunity_budget']['conditional_targets']!=worlds[1]['opportunity_budget']['conditional_targets']


def test_shared_actual_core_is_not_five_outcomes_despite_different_names():
    rows=[dict(player_id=str(i),position='WR' if i<2 else 'RB',player_team='A',opponent_team='B') for i in range(8)]
    candidates=[dict(allocated_idea_id='different_'+str(i),roster=[dict(player_master_id=str(j)) for j in [0,1,2,3+i]]) for i in range(5)]
    audit=dependence_audit(candidates,rows,5)
    assert audit['all_lineups_share_three_players'] and audit['receiving_pairs'][0]['count']==5
    assert len(audit['allocated_ideas'])==5  # Labels cannot hide shared dependence.


def test_weak_unmeasured_branches_are_rejected_and_feasibility_is_explicit():
    packet,snapshot=scenario_fixture('CLASSIC');single=deepcopy(packet['scenario_assumptions']['scenarios'][0]);single['assumptions']=single['assumptions'][:2];packet['scenario_assumptions']['scenarios']=[single]
    ideas,rejected=build_ideas(packet,snapshot['players'],AllocationControls())
    assert not ideas and rejected
    candidates,worlds,selection,plan=generate_allocated(snapshot,packet,snapshot['players'],{},5)
    assert not candidates and selection['achieved']==0 and not selection['constraints_relaxed']
    assert plan['phase']=='before_any_roster_solve'


def test_distinct_evidenced_alternatives_allocated_before_rosters_and_hard_constraints_hold():
    packet,snapshot=supported_fixture();original=deepcopy(packet['scenario_assumptions']['scenarios'][0]);packet['scenario_assumptions']['scenarios']=[]
    for index,game in enumerate(packet['games']):
        scenario=deepcopy(original);scenario.update(scenario_id='game_'+str(index),assumptions=[a for a in original['assumptions'] if a['game_id']==game['game_id']]);packet['scenario_assumptions']['scenarios'].append(scenario)
    candidates,worlds,selection,plan=generate_allocated(snapshot,packet,snapshot['players'],{'max_exposure':1,'minimum_uniqueness':2},3)
    assert selection['achieved']==3
    assert len({s['idea_id'] for s in plan['slots']})==3
    assert all(c['construction_compliance'] for c in candidates)
    assert not plan['actual_roster_audit']['all_lineups_share_three_players'] or plan['controls']['shared_triple_max_fraction']*3>=2
    # Impossible cap blocks every roster without relaxing or making generic fallback.
    blocked,_,result,blocked_plan=generate_allocated(snapshot,packet,snapshot['players'],{'maximum_exposure_by_player':{p['player_id']:0 for p in snapshot['players']}},3)
    assert not blocked and result['achieved']==0
    assert all(s['status']=='underfilled' for s in blocked_plan['slots'])


def test_durable_plan_callback_happens_before_any_solve(monkeypatch):
    import pulp
    from backend.app.product_services.analyst_shadow import digest
    packet,snapshot=supported_fixture();scenario=deepcopy(packet['scenario_assumptions']['scenarios'][0]);scenario['assumptions']=scenario['assumptions'][:2];packet['scenario_assumptions']['scenarios']=[scenario]
    frozen=[];original=pulp.LpProblem.solve
    def solve(model,*args,**kwargs):
        assert frozen and digest(frozen[0]['planning_snapshot'])==frozen[0]['sha256_before_generation']
        assert all('status' not in s for s in frozen[0]['slots'])
        return original(model,*args,**kwargs)
    monkeypatch.setattr(pulp.LpProblem,'solve',solve)
    candidates,_,_,plan=generate_allocated(snapshot,packet,snapshot['players'],{},2,on_plan=lambda p:frozen.append(p))
    assert len(frozen)==1 and candidates
    assert all(c['construction_audit']['passed'] for c in candidates)
    assert frozen[0]['planning_snapshot']==plan['planning_snapshot']


def test_explicit_player_locks_remain_hard_under_allocation():
    packet,snapshot=supported_fixture();scenario=deepcopy(packet['scenario_assumptions']['scenarios'][0]);scenario['assumptions']=scenario['assumptions'][:2];packet['scenario_assumptions']['scenarios']=[scenario]
    pid=snapshot['players'][0]['player_id']
    # The frozen legal model itself carries locks; emulate that contract explicitly.
    import pulp
    variables,model=pulp.LpProblem.fromDict(deepcopy(snapshot['model']))
    name=next(n for n,r in snapshot['variable_players'].items() if r['player_master_id']==pid)
    model+=variables[name]==1;snapshot['model']=model.toDict()
    candidates,_,_,plan=generate_allocated(snapshot,packet,snapshot['players'],{'locked_player_ids':[pid]},2)
    assert candidates and all(pid in {p['player_master_id'] for p in c['roster']} for c in candidates)
    assert plan['locked_core_exemptions']['player_master_ids']==[pid]


def test_intent_scoped_classic_ideas_never_invent_opposite_channel():
    packet, snapshot = supported_fixture()
    scenario = deepcopy(packet['scenario_assumptions']['scenarios'][0])
    scenario['assumptions'] = scenario['assumptions'][:2]
    packet['scenario_assumptions']['scenarios'] = [scenario]
    mixed, _ = build_ideas(packet, snapshot['players'], AllocationControls())
    assert {idea['script'] for idea in mixed} == {'passing', 'run_control'}
    packet['intent_scope'] = {'intent': 'EXPECTED_GAME'}
    scoped, _ = build_ideas(packet, snapshot['players'], AllocationControls())
    assert len(scoped) == 1
    assert not scoped[0]['derived_alternative']
    assert scoped[0]['script'] == 'passing'
