from copy import deepcopy
import pytest
from backend.app.product_services.receiver_completion_expectation import build_receiver_completion_expectation
GID='2026_01_SF_WAS';A='00-0000001';B='00-0000002';PID='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
def fixture():
 events=[];source=[]
 for play,cp,c in[(1,.25,1),(2,.75,0)]:
  events.append(dict(game_id=GID,play_id=str(play),team='SF',unknown_channels=[],opportunities=[dict(channel='pass_attempts',source_player_id='00-0000099'),dict(channel='targets',source_player_id=A)]))
  source.append(dict(game_id=GID,play_id=str(play),season=2026,week=1,season_type='REG',posteam='SF',receiver_player_id=A,qb_spike=False,complete_pass=c,cp=cp))
 component=dict(version='sourcewide_official_channel_component_v1',before_period=202606,native_order=dict(rows=[dict(game_id=GID,play_id=r['play_id'])for r in source]),official_channel_event_basis=events,source_event_sha256='a'*64)
 return component,source,{A:PID}
def run(args=None):return build_receiver_completion_expectation(*(args or fixture()))
def row(x):return x['actor_game_rows'][0]
def test_matched_denominator_and_signed_expected_excess_not_receiving_score():
 r=row(run());assert r['known_matched_targets']==2 and r['known_completions']==1 and r['known_expected_completions']==1
 assert r['catalog_value']==r['known_sample_catch_fraction']-r['known_sample_mean_cp']==0
 assert run()['model_consumed']is False
@pytest.mark.parametrize('cp',[None,'nan','inf',-0.1,1.1,True])
def test_missing_invalid_probability_never_zero_or_complete_case_exact(cp):
 c,p,i=fixture();p[0]['cp']=cp;r=row(run((c,p,i)))
 assert r['catalog_value']is None and r['known_matched_targets']==1 and r['unknown_outcomes']==1
@pytest.mark.parametrize('cp',[0,1])
def test_real_probability_zero_one_valid(cp):
 c,p,i=fixture();p[0]['cp']=cp
 assert row(run((c,p,i)))['catalog_value']is not None
@pytest.mark.parametrize('field',['complete_pass','qb_spike'])
def test_unknown_completion_or_eligibility_masks_full_rate(field):
 c,p,i=fixture();p[0][field]=None;r=row(run((c,p,i)))
 assert r['catalog_value']is None and r['known_matched_targets']==1

def test_unattributed_known_target_masks_other_actor_but_remains_residual():
 c,p,i=fixture();c['official_channel_event_basis'][0]['opportunities'][1]['source_player_id']=None;p[0]['receiver_player_id']=None
 x=run((c,p,i));assert row(x)['catalog_value']is None and len(x['unattributed_events'])==1

def test_unknown_target_membership_is_not_known_no_target():
 c,p,i=fixture();c['official_channel_event_basis'][0]['opportunities'].pop();c['official_channel_event_basis'][0]['unknown_channels']=['targets']
 assert row(run((c,p,i)))['catalog_value']is None

def test_unresolved_identity_preserves_native_metric():
 c,p,i=fixture();i[A]=None;r=row(run((c,p,i)))
 assert r['native_exact_excess']==0 and r['catalog_value']is None

@pytest.mark.parametrize('bad',['projectionduplicate','eventduplicate','missingrow','receiverconflict','teamconflict','future','phase','badUUID'])
def test_exact_native_source_scope_and_cardinality_guards(bad):
 c,p,i=fixture()
 if bad=='projectionduplicate':p.append(deepcopy(p[0]))
 if bad=='eventduplicate':c['official_channel_event_basis'].append(deepcopy(c['official_channel_event_basis'][0]))
 if bad=='missingrow':p.pop()
 if bad=='receiverconflict':p[0]['receiver_player_id']=B
 if bad=='teamconflict':p[0]['posteam']='WAS'
 if bad=='future':c['before_period']=202601
 if bad=='phase':p[0]['season_type']='POST'
 if bad=='badUUID':i[A]='wrong'
 with pytest.raises(ValueError):run((c,p,i))

def test_spike_known_exclusion_and_empty_denominator_undefined():
 c,p,i=fixture()
 for r in p:r['qb_spike']=True
 assert run((c,p,i))['actor_game_rows']==[]

def test_all_unknown_matched_outcomes_sample_undefined_not_zero():
 c,p,i=fixture()
 for r in p:r['cp']=None
 r=row(run((c,p,i)));assert r['known_matched_targets']==0 and r['known_sample_excess']is None and r['catalog_value']is None
