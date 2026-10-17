from copy import deepcopy
import pytest
from backend.app.product_services.opponent_qb_context import QBContextIndex,FEATURE_COLUMNS
A='00000000-0000-4000-8000-000000000001';B='00000000-0000-4000-8000-000000000002'
def log(pid=A,week=1,**changes):
 return dict(player_master_id=pid,team='PHI',season=2026,week=week,completed_at=f'2026-09-{week+10:02d}T00:00:00Z',available_at=f'2026-09-{week+11:02d}T00:00:00Z',source_row_id=f'{pid}:{week}',attempts=30,sacks=3,interceptions=1,sack_fumbles_lost=0,passing_yards=240,passing_epa=5,carries=5,rushing_yards=20,**changes)
def build(rows,**kw):return QBContextIndex(rows).context(opponent_team='PHI',season=2026,week=3,decision_at='2026-09-20T00:00:00Z',**kw)
def test_same_and_future_periods_cannot_leak_or_choose_actual_next_starter():
 before=build([log()]);after=build([log(),log(B,3),log(B,4)])
 assert before==after and after['player_master_id']==A
 assert after['features']['opponent_qb_sack_rate']==pytest.approx(3/33)
def test_source_receipt_gates_strict_mode_and_reconstruction_is_explicit():
 row=log();row['available_at']='2026-10-01T00:00:00Z'
 assert build([row])['features']['opponent_qb_context_missing']==1
 reconstructed=build([row],strict_source_clocks=False)
 assert reconstructed['player_master_id']==A and reconstructed['source_clock_mode'].startswith('retrospective')
def test_missing_or_late_completion_cannot_be_used_even_reconstructed():
 for at in [None,'2026-10-01T00:00:00Z']:
  row=log();row['completed_at']=at
  assert build([row],strict_source_clocks=False)['player_master_id'] is None
def test_sourced_backup_change_uses_only_that_qbs_prior_history_no_invented_prior():
 evidence=dict(team='PHI',player_master_id=B,source_uri='https://example.org/club',evidence_tier='inferred',observed_at='2026-09-19T00:00:00Z',received_at='2026-09-19T01:00:00Z')
 result=build([log()],starter_evidence=evidence)
 assert result['player_master_id']==B and result['features']['opponent_qb_changed_from_last_primary']==1
 assert result['features']['opponent_qb_starter_uncertain']==1
 assert result['features']['opponent_qb_prior_games']==0
 assert result['features']['opponent_qb_interception_rate'] is None
 assert set(result['features'])==set(FEATURE_COLUMNS)
@pytest.mark.parametrize('field,value',[('received_at','2026-10-01T00:00:00Z'),('observed_at',None),('team','CHI'),('source_uri','')])
def test_invalid_or_future_starter_evidence_cannot_override_prior_proxy(field,value):
 e=dict(team='PHI',player_master_id=B,source_uri='https://example.org/club',evidence_tier='confirmed',observed_at='2026-09-19T00:00:00Z',received_at='2026-09-19T01:00:00Z');e[field]=value
 r=build([log()],starter_evidence=e);assert r['player_master_id']==A and r['rejected_starter_evidence']
def test_canonical_identity_and_duplicate_period_validation():
 bad=log();bad['player_master_id']='Jalen Hurts'
 with pytest.raises(ValueError):QBContextIndex([bad])
 with pytest.raises(ValueError,match='Duplicate'):QBContextIndex([log(),log()])
def test_missing_stat_is_not_zero_and_small_sample_is_explicit():
 row=log();row['interceptions']=None;r=build([row]);f=r['features']
 assert f['opponent_qb_interception_rate'] is None and f['opponent_qb_interception_rate_missing']==1
 assert f['opponent_qb_small_sample']==1 and f['opponent_qb_prior_games']==1

def test_dst_label_guard_rejects_impossible_zero_but_not_a_plausible_zero():
 from backend.app.product_services.opponent_qb_context import dst_label_lower_bound_violation
 assert dst_label_lower_bound_violation(0,5,2) is True
 assert dst_label_lower_bound_violation(0,2,1) is False
 assert dst_label_lower_bound_violation(None,5,2) is None
 with pytest.raises(ValueError):dst_label_lower_bound_violation(0,-1,0)

def test_candidate_scenario_stays_conditional_and_uncertain_without_mixture_weights():
 e=dict(team='PHI',player_master_id=B,source_uri='https://example.org/club',evidence_tier='inferred',observed_at='2026-09-19T00:00:00Z',received_at='2026-09-19T01:00:00Z',conditional_scenario=True)
 r=build([log()],starter_evidence=e)
 assert r['selection']=='conditional_starter_scenario' and r['features']['opponent_qb_starter_uncertain']==1
 assert 'probability' not in r
