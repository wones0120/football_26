from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import patch

import pandas as pd
import pytest

from backend.app.product_services.analyst_scenarios import build_scenarios, run_merged, validate_scenarios, select_portfolio
from backend.app.product_services.analyst_packets import validate
from backend.app.product_services.optimizer import OptimizerService
from scripts.build_analyst_shadow_fixtures import fixture

NOW=datetime(2099,9,1,12,tzinfo=timezone.utc)


from scripts.run_merged_analyst_fixture import scenario_fixture


@pytest.mark.parametrize('fmt',['CLASSIC','SHOWDOWN'])
def test_merged_end_to_end_no_quality_veto_base_truth_and_legality(fmt):
    packet,snapshot=scenario_fixture(fmt); original=deepcopy(snapshot)
    pool=pd.DataFrame(snapshot['players']);service=OptimizerService.__new__(OptimizerService)
    params=dict(analyst_strategy='MERGED_SCENARIOS',analyst_portfolio_mode='CONDITIONAL_COVERAGE',analyst_candidates_per_thesis=3,max_exposure=1,minimum_uniqueness=1)
    kwargs=dict(contest_type='captain' if fmt=='SHOWDOWN' else 'classic',score_col='p90',stack_params={'enabled':False},locked_player_ids=set(snapshot['policy']['locked_ids']),exposure_remaining={snapshot['policy']['zero_remaining_exposure_ids'][0]:0},quality_floor={'mean':9999,'p90':9999},include_control_comparison=False)
    with patch('backend.app.product_services.analyst_scenarios.datetime') as clock:
        clock.now.return_value=NOW
        lineups,report=run_merged(service,pool,params=params,packet=packet,fmt=fmt,season=2099,week=1,slate='SYNTHETIC_'+fmt,requested=2,solve_kwargs=kwargs)
        repeated,again=run_merged(service,pool,params=params,packet=packet,fmt=fmt,season=2099,week=1,slate='SYNTHETIC_'+fmt,requested=2,solve_kwargs=kwargs)
    assert len(lineups)==2 and report['quality_screen']=='none' and report['baseline_veto'] is False
    assert report['selection']['quality_rejected']==0
    assert report['input_snapshot_sha256']==again['input_snapshot_sha256']
    assert [[(p['player_id'],p.get('roster_position')) for p in l] for l in lineups]==[[(p['player_id'],p.get('roster_position')) for p in l] for l in repeated]
    assert snapshot==original
    for lineup in lineups:
        ids={p['player_id'] for p in lineup}
        assert len(ids)==(6 if fmt=='SHOWDOWN' else 9) and sum(p['salary'] for p in lineup)<=50000
        assert set(snapshot['policy']['locked_ids'])<=ids
        assert not set(snapshot['policy']['zero_remaining_exposure_ids'])&ids
        for p in lineup:
            base=next(r for r in snapshot['players'] if r['player_id']==p['player_id'])
            # Captain rendering multiplies its base projection by 1.5.
            assert p['projection']==pytest.approx(base['projection']*(1.5 if p.get('roster_position')=='CPT' else 1))
    assert len(report['scenario_definitions'])==2
    if fmt=='CLASSIC': assert len({a['game_id'] for a in packet['scenario_assumptions']['scenarios'][0]['assumptions']})==3


def test_concentration_conserves_targets_with_attributed_measurements():
    packet,snapshot=scenario_fixture('CLASSIC')
    game=packet['games'][0];team=game['teams'][0]
    members=[p for p in packet['players'] if p['team']==team and p['position'] in {'RB','WR','TE'}]
    for p in members:p['workload_evidence']['historical']['targets_mean_3']=dict(status='observed',available=True,value=5)
    packet['scenario_assumptions']['scenarios']=[dict(scenario_id='concentration',label='Synthetic concentration',hypothesis_ids=['synthetic_context'],assumptions=[dict(kind='target_concentration',game_id=game['game_id'],team=team,player_master_ids=[members[0]['player_id']],share_delta=.1,elasticity=.5)])]
    result=build_scenarios(packet,snapshot['players'],fmt='CLASSIC',decision_at=NOW.isoformat())[0]
    changes=[result['moments'][p['player_id']]['changes'][0] for p in members]
    assert sum(c['workload_before']*c['ratio'] for c in changes)==pytest.approx(30)
    assert all(c['workload_lineage']=='historical.targets_mean_3' for c in changes)
    members[1]['workload_evidence']['historical']={}
    with pytest.raises(ValueError,match='complete measured'):build_scenarios(packet,snapshot['players'],fmt='CLASSIC',decision_at=NOW.isoformat())


@pytest.mark.parametrize('value',[float('nan'),float('inf'),2,True])
def test_nonfinite_unbounded_assumptions_rejected(value):
    packet,_=scenario_fixture('CLASSIC');packet['scenario_assumptions']['scenarios'][0]['assumptions'][0]['factor']=value
    assert validate_scenarios(packet) and validate(packet)


def test_future_packet_and_expiry_rejected():
    packet,snapshot=scenario_fixture('SHOWDOWN')
    with pytest.raises(ValueError,match='future-sourced'):build_scenarios(packet,snapshot['players'],fmt='SHOWDOWN',decision_at='2099-08-01T12:00:00Z')
    with pytest.raises(ValueError,match='not pregame'):build_scenarios(packet,snapshot['players'],fmt='SHOWDOWN',decision_at='2099-09-03T12:00:00Z')


def test_scenario_portfolio_can_select_roster_below_legacy_95percent_floor():
    rows=[dict(player_id='a',position='WR',projection=100,p90=120),dict(player_id='b',position='WR',projection=80,p90=90)]
    scenarios=[dict(scenario_id='analyst_outcome',moments={'a':dict(mean=50,p90=60),'b':dict(mean=120,p90=130)})]
    candidates=[dict(roster=[dict(player_master_id=pid,role='SELECTED')],scenario_ids=['analyst_outcome']) for pid in ['a','b']]
    selected,report=select_portfolio(candidates,scenarios,rows,requested=1,params={},fmt='CLASSIC')
    assert selected[0]['roster'][0]['player_master_id']=='b'
    assert rows[1]['projection']<.95*rows[0]['projection'] and rows[1]['p90']<.95*rows[0]['p90']
    assert report['quality_rejected']==0
    selected,report=select_portfolio(candidates,scenarios,rows,requested=1,params={'maximum_exposure_by_player':{'b':0}},fmt='CLASSIC')
    assert selected[0]['roster'][0]['player_master_id']=='a'


@pytest.mark.parametrize('fmt,strategy',[('CLASSIC','classic_large_gpp_v1'),('SHOWDOWN','showdown_single_entry_gpp'),('SHOWDOWN','showdown_small_max_gpp')])
def test_full_optimizer_job_persists_explicit_strategy_and_scenario_report(fmt,strategy):
    from sqlalchemy import create_engine
    from backend.app.product_services.analyst_packets import packet_digest
    class InMemoryService(OptimizerService):
        def __init__(self,pool):
            super().__init__(); self.engine=create_engine('sqlite://'); self.pool=pool; self.saved=[]
        def _load_player_pool(self,*args,**kwargs): return self.pool.copy(deep=True)
        def _resolve_run_lineage(self,**kwargs): return 'synthetic-projection',None,datetime(2099,9,1,10,tzinfo=timezone.utc)
        def _persist_optimizer_run(self,job): self.saved.append(job); return True
    packet,snapshot=scenario_fixture(fmt)
    rows=pd.DataFrame(snapshot['players']);rows['showdown_qb_eligible']=rows['position'].eq('QB');rows['is_starting_qb']=rows['position'].eq('QB');rows['official_availability_status']='available';rows['pregame_role_uncertain']=False
    service=InMemoryService(rows)
    with patch('backend.app.product_services.analyst_packets.load_packet',return_value=packet),patch('backend.app.product_services.analyst_scenarios.datetime') as clock:
        clock.now.return_value=NOW
        job=service.run_job(2099,1,'SYNTHETIC_'+fmt,strategy,dict(num_lineups=2,max_exposure=1,analyst_strategy='MERGED_SCENARIOS',analyst_portfolio_mode='CONDITIONAL_COVERAGE',analyst_packet_sha256=packet_digest(packet),analyst_candidates_per_thesis=3),contest_format=fmt.lower(),objective='gpp',allow_incomplete_evidence=True)
    assert job.status=='completed' and len(job.results)==2
    report=job.params['strategy_runtime']['football_analyst']
    assert report['mode']=='MERGED_SCENARIOS' and report['quality_screen']=='none'
    assert job.params['analyst_strategy']=='MERGED_SCENARIOS' and service.saved
    if fmt=='SHOWDOWN': assert 'NON-PRODUCTION incomplete-evidence override' in job.message


def test_transfer_conserves_workload_and_retains_source_lineage():
    packet,snapshot=scenario_fixture('SHOWDOWN');game=packet['games'][0];team=game['teams'][0]
    members=[p for p in packet['players'] if p['team']==team and p['position'] in {'RB','WR','TE'}]
    for p in members:p['workload_evidence']['historical']['carries_mean_3']=dict(status='observed',available=True,value=5)
    packet['scenario_assumptions']['scenarios']=[dict(scenario_id='transfer',label='Synthetic conditional workload transfer',hypothesis_ids=['synthetic_context'],assumptions=[dict(kind='workload_transfer',game_id=game['game_id'],team=team,workload='carries',from_player_master_id=members[0]['player_id'],to_player_master_id=members[1]['player_id'],fraction=.5,elasticity=.5)])]
    scenario=build_scenarios(packet,snapshot['players'],fmt='SHOWDOWN',decision_at=NOW.isoformat())[0]
    assert sum(scenario['moments'][p['player_id']]['changes'][0]['workload_before']*scenario['moments'][p['player_id']]['changes'][0]['ratio'] for p in members)==pytest.approx(30)
    packet['players'][1]['workload_evidence']['lineage']={'workload_feature_cutoff_at':'2099-09-02T10:00:00Z'}
    with pytest.raises(ValueError,match='future workload'):build_scenarios(packet,snapshot['players'],fmt='SHOWDOWN',decision_at=NOW.isoformat())


def test_merged_captain_pool_preserves_preferences_without_base_top_four_veto():
    from backend.app.product_services.showdown_captain_shortlist import build_captain_shortlist
    _,snapshot=fixture('SHOWDOWN');pool=pd.DataFrame(snapshot['players'])
    old,old_report=build_captain_shortlist(pool,params={},flex_only_ids=set())
    new,report=build_captain_shortlist(pool,params={'analyst_strategy':'MERGED_SCENARIOS','no_qb_captain':True},flex_only_ids={snapshot['players'][3]['player_id']})
    assert int(old['showdown_captain_shortlisted'].sum())==4
    assert int(new['showdown_captain_shortlisted'].sum())>4
    assert not new.loc[new['position']=='QB','showdown_captain_shortlisted'].any()
    assert not new.loc[new['player_id']==snapshot['players'][3]['player_id'],'showdown_captain_shortlisted'].any()
    assert report['policy_id']=='analyst_scenario_all_eligible_captains_v1'
    assert old_report['policy_id']=='showdown_top_four_p90_v1'


def test_live_missing_projection_distribution_is_audited_never_filled_zero():
    from backend.app.product_services.analyst_scenarios import projection_distribution_pool
    packet,snapshot=scenario_fixture('CLASSIC');pool=pd.DataFrame(snapshot['players'])
    missing_id=str(pool.loc[3,'player_id']);pool.loc[3,'projection']=None
    filtered,excluded=projection_distribution_pool(pool)
    assert missing_id not in set(filtered['player_id'])
    assert excluded[0]['player_master_id']==missing_id
    service=OptimizerService.__new__(OptimizerService)
    with patch('backend.app.product_services.analyst_scenarios.datetime') as clock:
        clock.now.return_value=NOW
        lineups,report=run_merged(service,pool,params={'analyst_candidates_per_thesis':2,'analyst_portfolio_mode':'CONDITIONAL_COVERAGE'},packet=packet,fmt='CLASSIC',season=2099,week=1,slate='SYNTHETIC_CLASSIC',requested=2,solve_kwargs={'contest_type':'classic','stack_params':{'enabled':False},'include_control_comparison':False})
        with pytest.raises(ValueError,match='Locked player'):
            run_merged(service,pool,params={},packet=packet,fmt='CLASSIC',season=2099,week=1,slate='SYNTHETIC_CLASSIC',requested=1,solve_kwargs={'locked_player_ids':{missing_id}})
    assert len(lineups)==2
    assert all(missing_id not in {p['player_id'] for p in lineup} for lineup in lineups)
    audit=report['projection_distribution_eligibility']
    assert audit['excluded'][0]['player_master_id']==missing_id and audit['excluded'][0]['base_projection'] is None
    assert len(audit['original_input_rows'])==len(snapshot['players']) and audit['quality_screen']=='none'


def test_showdown_candidate_search_covers_captain_cap_without_relaxing_it():
    packet,snapshot=scenario_fixture('SHOWDOWN')
    # A single neutral world with a one-roster initial budget cannot supply four
    # different Captains. The same legal model has enough feasible alternatives.
    packet['scenario_assumptions']['scenarios']=packet['scenario_assumptions']['scenarios'][:1]
    for a in packet['scenario_assumptions']['scenarios'][0]['assumptions']:a['factor']=1
    pool=pd.DataFrame(snapshot['players'])
    service=OptimizerService.__new__(OptimizerService)
    params={'analyst_candidates_per_thesis':1,'max_exposure':1,'captain_max_exposure':.25}
    with patch('backend.app.product_services.analyst_scenarios.datetime') as clock:
        clock.now.return_value=NOW
        lineups,report=run_merged(service,pool,params=params,packet=packet,fmt='SHOWDOWN',
            season=2099,week=1,slate='SYNTHETIC_SHOWDOWN',requested=4,
            solve_kwargs={'contest_type':'captain','score_col':'p90','stack_params':{'enabled':False},
                          'include_control_comparison':False})
    assert len(lineups)==4
    captains=[next(p['player_id'] for p in lineup if p['roster_position']=='CPT') for lineup in lineups]
    assert len(set(captains))==4
    assert report['initial_generated_candidate_count']==1
    assert report['captain_exposure_coverage']['added_candidates']==3
    assert report['selection']['constraints_relaxed'] is False
    assert params['captain_max_exposure']==.25
    assert all(attempt['solver_status']=='Optimal' for attempt in report['generation'])


def test_captain_search_cannot_bypass_a_locked_captain_exposure_conflict():
    packet,snapshot=scenario_fixture('SHOWDOWN')
    packet['scenario_assumptions']['scenarios']=packet['scenario_assumptions']['scenarios'][:1]
    pool=pd.DataFrame(snapshot['players'])
    # The shortlisted WR is a feasible Captain, but its 25% cap permits only one of 4.
    locked=next(r['player_id'] for r in snapshot['players'] if r['position']=='WR')
    with patch('backend.app.product_services.analyst_scenarios.datetime') as clock:
        clock.now.return_value=NOW
        lineups,report=run_merged(OptimizerService.__new__(OptimizerService),pool,
            params={'analyst_candidates_per_thesis':1,'max_exposure':1,'captain_max_exposure':.25},
            packet=packet,fmt='SHOWDOWN',season=2099,week=1,slate='SYNTHETIC_SHOWDOWN',requested=4,
            solve_kwargs={'contest_type':'captain','score_col':'p90','stack_params':{'enabled':False},
                'locked_captain_player_id':locked,'include_control_comparison':False})
    assert len(lineups)==1
    assert report['status']=='underfilled'
    assert report['captain_exposure_coverage']['added_candidates']==0
    assert report['generation'][-1]['solver_status']=='Infeasible'
    assert report['selection']['constraints_relaxed'] is False
