from copy import deepcopy
import pulp
import pytest
from backend.app.product_services.joint_opportunity import prepare_world,enable_world,attach_objective,score_roster,candidate_metric


def fixture():
 rows=[]
 for p,pos,t,opp,targets,carries in [('q','QB','A','B',0,3),('w1','WR','A','B',8,0),('w2','WR','A','B',7,0),('te','TE','A','B',5,0),('rb','RB','A','B',3,14),('rb2','RB','A','B',2,8),('ow','WR','B','A',7,0),('other','WR','C','D',8,0)]:
  rows.append(dict(player_id=p,name=p,position=pos,player_team=t,opponent_team=opp,projection=10,p90=30,game_total_line=44.5,team_targets_mean_3=25,team_carries_mean_3=25,workload_evidence={'historical':{k+'_mean_3':dict(status='observed',value=v) for k,v in [('targets',targets),('carries',carries)]}}))
 world=dict(scenario_id='competitive',label='Both offenses sustain drives; A passing roles benefit together',moments={r['player_id']:dict(mean=10,p90=30,changes=[]) for r in rows});return rows,world


def roster(*ids,cap=None):return [dict(player_master_id=p,role='CPT' if p==cap else 'SELECTED') for p in ids]


def test_shared_budget_conserves_touches_and_qb_receiver_event_not_doubled():
 rows,w=fixture();original=deepcopy(rows);book=prepare_world(w,rows);assert all(b['attributed_share']+b['unattributed_share']==pytest.approx(1) for b in book['budgets'])
 assert 'A:targets' not in book['costs']['q']
 s=score_roster(roster('q','w1','w2','te','rb'),w,book,rows)
 assert all(b['total_used_share']<=1+1e-7 for b in s['budget_balances'])
 assert s['supported_tail_credit']<s['independent_tail_sum'] and s['conditional_mean_sum']==50
 assert s['not_joint_p90'] and rows==original
 assert any('positive football' in p['relationship'] for p in s['relationships'])


def test_constructive_full_roster_objective_soft_credit_never_prohibits_teammates():
 rows,w=fixture();book=prepare_world(w,rows);mapping={r['player_id']:dict(player_master_id=r['player_id'],role='SELECTED') for r in rows};model=pulp.LpProblem('joint',pulp.LpMaximize);v={p:pulp.LpVariable(p,cat='Binary') for p in mapping};model+=pulp.lpSum(v.values())==4
 for p in ['w1','w2','rb','rb2']:model+=v[p]==1
 attach_objective(model,v,mapping,w,book);model.solve(pulp.PULP_CBC_CMD(msg=False));assert model.status==pulp.LpStatusOptimal
 s=score_roster(roster('w1','w2','rb','rb2'),w,book,rows);assert pulp.value(model.objective)==pytest.approx(s['score'])
 # 44.5 is contextual evidence, not a cutoff; both WRs and both RBs remain legal.
 assert v['w1'].value()==v['w2'].value()==v['rb'].value()==v['rb2'].value()==1


def test_captain_scoring_does_not_multiply_physical_opportunity():
 rows,w=fixture();book=prepare_world(w,rows);a=score_roster(roster('w1'),w,book,rows);b=score_roster(roster('w1',cap='w1'),w,book,rows)
 assert b['score']==pytest.approx(1.5*a['score'])
 assert [x['selected_base_share'] for x in a['budget_balances']]==[x['selected_base_share'] for x in b['budget_balances']]
 with pytest.raises(ValueError,match='distinct'):score_roster(roster('w1','w1',cap='w1'),w,book,rows)


def test_positive_shared_environment_opponent_response_and_unknowns_are_explicit():
 rows,w=fixture();enable_world(w,rows);s=score_roster(roster('q','w1','ow'),w,w['joint_opportunity'],rows)
 assert any('two-sided' in p['relationship'] for p in s['relationships'])
 boosted=deepcopy(w)
 for p in ['q','w1','ow']:boosted['moments'][p]['mean']+=5;boosted['moments'][p]['p90']+=5
 assert candidate_metric({'roster':roster('q','w1','ow')},boosted)>s['score']
 rows[1]['workload_evidence']={};book=prepare_world(w,rows);assert {'player_master_id':'w1','channel':'targets'} in book['missing_measurements']
 assert 'not forecast' in book['budgets'][0]['unit'] and 'No supported' in book['td_budget_status']

@pytest.mark.parametrize('fmt',['CLASSIC','SHOWDOWN'])
def test_live_merged_integration_full_legal_rosters_and_base_truth(fmt):
 from datetime import datetime,timezone
 from unittest.mock import patch
 import pandas as pd
 from scripts.run_merged_analyst_fixture import scenario_fixture
 from backend.app.product_services.analyst_scenarios import run_merged
 from backend.app.product_services.optimizer import OptimizerService
 packet,snapshot=scenario_fixture(fmt)
 for p in packet['players']:
  p['workload_evidence']['historical']={c+'_mean_3':dict(value=5,status='observed',available=True) for c in ('targets','carries')}
 original=deepcopy(snapshot);params=dict(analyst_joint_opportunity_enabled=True,analyst_strategy='MERGED_SCENARIOS',analyst_portfolio_mode='CONDITIONAL_COVERAGE',analyst_candidates_per_thesis=2,max_exposure=1)
 service=OptimizerService.__new__(OptimizerService)
 with patch('backend.app.product_services.analyst_scenarios.datetime') as clock:
  clock.now.return_value=datetime(2099,9,1,12,tzinfo=timezone.utc)
  lineups,report=run_merged(service,pd.DataFrame(snapshot['players']),params=params,packet=packet,fmt=fmt,season=2099,week=1,slate='SYNTHETIC_'+fmt,requested=1,research_only_joint_opportunity=True,solve_kwargs=dict(contest_type='captain' if fmt=='SHOWDOWN' else 'classic',score_col='p90',stack_params={'enabled':False},locked_player_ids=set(),quality_floor=None,include_control_comparison=False))
 assert len(lineups)==1 and snapshot==original
 assert lineups[0][0]['analyst_joint_opportunity_summary']['not_joint_p90']
 assert all(b['total_used_share']<=1+1e-6 for b in lineups[0][0]['analyst_joint_opportunity_summary']['budget_balances'])
 assert len(lineups[0])==(6 if fmt=='SHOWDOWN' else 9) and sum(p['salary'] for p in lineups[0])<=50000


def test_joint_prototype_cannot_activate_via_production_optimizer_params():
 from backend.app.product_services.analyst_scenarios import run_merged
 with pytest.raises(ValueError,match='inactive pending'):
  run_merged(None,None,params={'analyst_joint_opportunity_enabled':True},packet={},fmt='CLASSIC',season=2026,week=6,slate='SUNDAY_MAIN',requested=1,solve_kwargs={})
