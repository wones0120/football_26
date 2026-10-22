from copy import deepcopy
import pytest
from backend.app.product_services.backup_qb_experience import build_backup_qb_experience
from backend.app.product_services.active_workload_distributions import VERSION
P='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'

def inputs():
 f=dict(kind='role',position='QB',source_position='QB',source_unit='QB',season=2026,week=6,player_id=P,team='SF',role='expected_backup',observed_at='2026-10-19T09:00:00Z',effective_at='2026-10-19T09:00:00Z',received_at='2026-10-19T10:00:00Z')
 roles=dict(evidence_use='postlock_descriptive_not_pregame_or_serving',actual_derived_at='2026-10-20T01:00:00Z',extracted=dict(actors=[dict(player_master_id=P,source_player_id='00-0031234',team='SF',position='QB')],facts=[f]))
 history=dict(version=VERSION,provenance=dict(actual_publication_at='2026-10-20T01:00:00Z'),rows=[dict(season=2026,team='SF',player_master_id=P,source_position='QB',logs=[dict(week=1,counts=dict(pass_attempts=0),positive_offensive_participation_proven=True),dict(week=2,counts=dict(pass_attempts=3),positive_offensive_participation_proven=False)])])
 return roles,history

def build(r,h):return build_backup_qb_experience(r,h,season=2026,week=6,cutoff='2026-10-20T02:00:00Z')

def test_attempts_and_participation_separate():
 v=build(*inputs())['rows'][0];assert v['official_pass_attempts']==3 and v['proven_participating_games']==2

def test_no_snaps_zero_attempt_not_dnp():
 r,h=inputs();h['rows'][0]['logs'][0]['positive_offensive_participation_proven']=False
 v=build(r,h)['rows'][0];assert v['official_pass_attempts']==3 and v['proven_participating_games'] is None and v['proven_participating_games_lower_bound']==1

def test_unknown_attempt_not_zero():
 r,h=inputs();h['rows'][0]['logs'][0]['counts']['pass_attempts']=None
 assert build(r,h)['rows'][0]['official_pass_attempts'] is None

def test_absent_history_unknown():
 r,h=inputs();h['rows']=[];v=build(r,h)['rows'][0]
 assert v['official_pass_attempts'] is None and v['proven_participating_games'] is None

def test_starter_not_backup():
 r,h=inputs();r['extracted']['facts'][0]['role']='expected_starter';assert not build(r,h)['rows']

def test_other_team_not_transferred():
 r,h=inputs();h['rows'][0]['team']='WAS';assert build(r,h)['rows'][0]['official_pass_attempts'] is None

@pytest.mark.parametrize('kind',['negative_count','future_role','conflict','identity'])
def test_guards(kind):
 r,h=inputs()
 if kind=='negative_count':h['rows'][0]['logs'][0]['counts']['pass_attempts']=-1
 if kind=='future_role':r['extracted']['facts'][0]['effective_at']='2026-10-21T10:00:00Z'
 if kind=='conflict':f=deepcopy(r['extracted']['facts'][0]);f['role']='expected_starter';r['extracted']['facts'].append(f)
 if kind=='identity':r['extracted']['actors'][0]['team']='WAS'
 with pytest.raises(ValueError):build(r,h)


def test_target_outcome_excluded():
 r,h=inputs();h['rows'][0]['logs'].append(dict(week=6,counts=dict(pass_attempts=9000),positive_offensive_participation_proven=True))
 assert build(r,h)['rows'][0]['official_pass_attempts']==3


def test_missing_weekly_positive_participant_masks_totals():
 r,h=inputs();h['positive_participants_missing_weekly_rows']=[dict(season=2026,week=3,team='SF',player_master_id=P)]
 v=build(r,h)['rows'][0];assert v['official_pass_attempts'] is None and v['proven_participating_games'] is None

def test_canonical_role_duplicate_rejected():
 r,h=inputs();r['extracted']['actors'].append(deepcopy(r['extracted']['actors'][0]))
 with pytest.raises(ValueError):build(r,h)
