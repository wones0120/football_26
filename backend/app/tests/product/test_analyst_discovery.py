from copy import deepcopy
import pytest
from backend.app.product_services.analyst_discovery import scan,prepare_actions,validate_discovery,apply_opportunity_transfer
from backend.app.product_services.scenario_allocation import AllocationControls,build_ideas,generate_allocated
from backend.app.tests.product.test_scenario_allocation import supported_fixture


def investigated_fixture():
    packet,snapshot=supported_fixture();original=deepcopy(packet['scenario_assumptions']['scenarios'][0]);packet['scenario_assumptions']['scenarios']=[]
    for index,game in enumerate(packet['games']):
        s=deepcopy(original);s.update(scenario_id='single_'+str(index),assumptions=[a for a in original['assumptions'] if a['game_id']==game['game_id']]);packet['scenario_assumptions']['scenarios'].append(s)
    ideas,_=build_ideas(packet,snapshot['players'],AllocationControls());idea=ideas[-1];pid=idea['eligible_rb_ids'][0] if idea['script']=='run_control' else idea['eligible_receiver_ids'][0]
    finding=dict(finding_id='investigated_edge',game_id=idea['game_id'],player_master_ids=[pid],source_ids=[s['source_id'] for s in packet['sources'] if s['coverage']=='verified'],as_of=packet['decision_at'],classification='hypothesized_model_blindspot',status='supported_provisional',evidence_strength=.75,model_accounting=dict(status='partial',included_fields=['historical workload'],delta_fields=['conditional role concentration'],rationale='Hypothesis conditional on sourced role evidence, beyond averaged baseline'),mechanism='Conditional concentration rather than historical trend double count',counterevidence=['Role evidence incomplete; opposite game flow'],unknowns=['Current role uncertainty'],action=dict(idea_id=idea['idea_id'],required_player_ids=[pid]))
    packet['discovery']=dict(contract_id='analyst_discovery_v1',scan_snapshot_sha256='a'*64,scanned_game_ids=[g['game_id'] for g in packet['games']],findings=[finding]);return packet,snapshot,idea,pid


def test_scan_covers_all_games_and_low_projection_players_without_automatic_boost():
    packet,snapshot,_,_=investigated_fixture()
    low=snapshot['players'][-1];low.update(target_share_trend=.2,projection=.5)
    scan1=scan(packet,snapshot['players']);assert scan1==scan(packet,snapshot['players'])
    assert len(scan1['scanned_games'])==len(packet['games'])
    assert any(str(low['player_id']) in c['player_master_ids'] for c in scan1['candidate_edges'])
    assert all(c['automatic_status']=='watchlist' for c in scan1['candidate_edges'])


def test_temporal_identity_coverage_and_model_delta_validation():
    packet,_,_,_=investigated_fixture();assert not validate_discovery(packet)
    for mutate,match in [(lambda p:p['discovery'].update(scanned_game_ids=[]),'every Classic'),(lambda p:p['discovery']['findings'][0].update(as_of='2200-01-01T00:00:00Z'),'after decision'),(lambda p:p['discovery']['findings'][0].update(player_master_ids=['not-canonical']),'canonical'),(lambda p:p['discovery']['findings'][0]['model_accounting'].update(status='already_accounted'),'distinct model delta')]:
        p=deepcopy(packet);mutate(p);assert any(match in e for e in validate_discovery(p))


def test_weak_already_accounted_and_ineligible_findings_do_not_reserve():
    packet,snapshot,_,pid=investigated_fixture();ideas,_=build_ideas(packet,snapshot['players'],AllocationControls())
    p=deepcopy(packet);p['discovery']['findings'][0]['evidence_strength']=.4
    assert not prepare_actions(p,snapshot['players'],deepcopy(ideas),5,{})['reserved_idea_ids']
    p['discovery']['findings'][0].update(status='watchlist');assert not prepare_actions(p,snapshot['players'],deepcopy(ideas),5,{})['reserved_idea_ids']
    report=prepare_actions(packet,[r for r in snapshot['players'] if str(r['player_id'])!=pid],deepcopy(ideas),5,{})
    assert not report['reserved_idea_ids'] and 'ineligible' in report['findings'][0]['decision_reason']


def test_real_bounded_reserved_construction_effect_before_solves_and_disabled_comparison():
    packet,snapshot,idea,pid=investigated_fixture();before=deepcopy(snapshot['players'])
    candidates,_,_,plan=generate_allocated(snapshot,packet,snapshot['players'],{},5)
    assert plan['slots'][0]['idea_id']==idea['idea_id'] and 'discovery' in plan['slots'][0]['reason']
    assert pid in {p['player_master_id'] for p in candidates[0]['roster']}
    assert candidates[0]['discovery_finding_ids']==['investigated_edge']
    assert plan['discovery']['findings'][0]['actual_allocation_slots']
    assert snapshot['players']==before
    _,_,_,off=generate_allocated(snapshot,packet,snapshot['players'],{'analyst_discovery_enabled':False},5)
    assert not off['discovery']['reserved_idea_ids']
    # Hard exposure veto wins over the investigated action and is recorded.
    _,_,_,blocked=generate_allocated(snapshot,packet,snapshot['players'],{'maximum_exposure_by_player':{pid:0}},5)
    assert blocked['discovery']['findings'][0]['action_status']=='infeasible_or_displaced'


def test_carry_and_target_transfers_conserve_budget_and_are_bounded():
    rows=[dict(player_id='a',player_team='T',position='RB',projected_targets=2,projected_carries=8),dict(player_id='b',player_team='T',position='RB',projected_targets=2,projected_carries=8)]
    for channel in ['targets','carries']:
        world=dict(moments={p:dict(mean=10,p90=15,changes=[]) for p in ['a','b']});idea=dict(team='T',discovery_finding_ids=['f'],discovery_opportunity_transfer=dict(channel=channel,recipient_id='a',share=.05))
        apply_opportunity_transfer(world,idea,rows);budget=world['discovery_opportunity_budget']
        assert budget['sum_before']==pytest.approx(budget['sum_after'])==1
        assert world['moments']['a']['mean']>10>world['moments']['b']['mean']
    world=dict(moments={p:dict(mean=10,p90=15,changes=[]) for p in ['a','b']});idea['discovery_opportunity_transfer']['share']=.5
    with pytest.raises(ValueError,match='ratio bounds'):apply_opportunity_transfer(world,idea,rows)


def test_deterministic_replay_and_conflicting_locked_qb_are_audited():
    import pulp
    packet,snapshot,idea,pid=investigated_fixture()
    first=generate_allocated(snapshot,packet,snapshot['players'],{},5)
    second=generate_allocated(snapshot,packet,snapshot['players'],{},5)
    assert first==second
    assert idea['script']=='run_control'
    qb=idea['eligible_qb_ids'][0];variables,model=pulp.LpProblem.fromDict(deepcopy(snapshot['model']))
    var_name=next(n for n,r in snapshot['variable_players'].items() if r['player_master_id']==qb)
    model+=variables[var_name]==1;snapshot['model']=model.toDict()
    candidates,_,result,plan=generate_allocated(snapshot,packet,snapshot['players'],{'locked_player_ids':[qb]},5)
    assert all(qb in {p['player_master_id'] for p in c['roster']} for c in candidates)
    assert plan['discovery']['findings'][0]['action_status']=='infeasible_or_displaced'
    assert result['constraints_relaxed'] is False
