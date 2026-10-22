from copy import deepcopy
import pytest
from backend.app.tests.product.test_game_state_reconstruction import row
from backend.app.tests.product.test_event_boundary_progression import fixture
from research.game_progression_pilot_20261020.observation_contract.contract import (
    record,identity_census,native_key,clock_snapshot,timeout_snapshot,validate_record)

SHA='a'*64

def extract(raw=None,cycle=None,ordinal=0,census=None):
    raw=raw if raw is not None else row(home_timeouts_remaining=2,away_timeouts_remaining=3)
    key=native_key(raw)
    return record(raw,ordinal,SHA,census if census is not None else identity_census([raw]),{key:cycle}if cycle else{})

def test_source_snap_context_is_oriented_without_claiming_policy_or_play_end():
    raw=row(home_timeouts_remaining=2,away_timeouts_remaining=0,posteam_score=7,defteam_score=3,qb_kneel=1)
    before=deepcopy(raw);r=extract(raw)
    assert r['pre_event']['clock']['half_seconds']==1800
    assert r['pre_event']['timeouts']['offense']==0 and r['pre_event']['timeouts']['defense']==2
    assert r['pre_event']['score']['differential']==4 and r['observed_action']['kind']=='qb_kneel'
    assert r['play_end']['clock']is None and r['clock_control']['timeout_use']is None
    assert r['continuation_support']=='UNKNOWN'and not r['generated_policy_supported']
    assert r['observed_action']['policy_probability']is None and raw==before
    validate_record(r,0,SHA)

@pytest.mark.parametrize('value',[None,-1,4,1.5,True,'2',float('nan'),float('inf')])
def test_missing_or_invalid_timeout_budget_is_never_zero(value):
    raw=row(home_timeouts_remaining=value,away_timeouts_remaining=2)
    r=extract(raw);t=r['pre_event']['timeouts']
    assert t['home']is None and t['defense']is None
    assert t['status']=='UNKNOWN_OR_INVALID_TIMEOUT_SNAPSHOT'
    assert r['raw_pre_event']['home_timeouts_remaining']is value

@pytest.mark.parametrize('changes',[
    {'half_seconds_remaining':None},{'quarter_seconds_remaining':899},{'game_half':'Half2'},
    {'qtr':None},{'game_seconds_remaining':100},{'half_seconds_remaining':True},
])
def test_clock_conflicts_do_not_become_known_horizons(changes):
    r=clock_snapshot(row(**changes))
    assert r['status']=='UNKNOWN_OR_CONFLICTING_CLOCK'and r['half_seconds']is None

def test_overtime_and_control_rows_are_preserved_without_invented_snaps():
    raw=row(qtr=5,game_half='Overtime',play_type='time_out',play_type_nfl='TIMEOUT',home_timeouts_remaining=1,away_timeouts_remaining=2)
    r=extract(raw,ordinal=17)
    assert r['row_kind']=='CONTROL'and r['pre_event']['clock']['status']=='EXPLICIT_OVERTIME'
    assert r['provenance']['source_ordinal_zero_based']==17
    assert r['observed_action']['kind']=='time_out'and r['clock_control']['timeout_team']is None
    assert not r['pre_event']['timeouts']['timeout_use_proven']

@pytest.mark.parametrize('changes',[{'home_team':'BUF'},{'posteam':None},{'defteam':'BUF'}])
def test_unknown_team_orientation_does_not_assign_timeout_or_score_to_offense(changes):
    raw=row(home_timeouts_remaining=2,away_timeouts_remaining=1,**changes);r=extract(raw)
    assert r['pre_event']['timeouts']['offense']is None
    assert r['pre_event']['score']['differential']is None

def test_post_or_total_score_is_never_a_pre_action_substitute():
    r=extract(row(posteam_score=None,posteam_score_post=14,total_home_score=35,total_away_score=28))
    assert r['pre_event']['score']['offense']is None

@pytest.mark.parametrize('kind',['RIGHT_CENSORED','EXACT_NEXT_ACTION'])
def test_frozen_followup_and_unknown_marks_are_separate_from_terminal_observations(kind):
    c,_=fixture(kind=kind);c.update(context_key=['2023_01_BUF_NYJ','BUF'],state_certified=False,barriers=['unknown_source'])
    c['production'][0]['rushing_yards']=None
    raw=row(end_clock_time='00:00',end_yard_line='NYJ 1');before=deepcopy((raw,c));r=extract(raw,c)
    assert r['followup']['wait']['kind']==kind and not r['followup']['source_state_certified']
    assert r['followup']['joint_marks']['production'][0]['rushing_yards']is None
    assert r['followup']['next_action_or_boundary_state']==c['endpoint']
    assert r['followup']['next_action_native_id']is None and r['play_end']['field100']is None
    r['followup']['next_action_or_boundary_state']['field100']=1
    assert (raw,c)==before

@pytest.mark.parametrize('changes',[{'game_id':None},{'play_id':None},{'play_id':True},{'play_id':-1}])
def test_missing_native_identity_is_retained_without_cycle_join(changes):
    r=extract(row(**changes))
    assert r['provenance']['identity_status']=='MISSING_NATIVE_IDENTITY'
    assert r['followup']['status']=='NO_UNIQUE_COMPILED_CYCLE'

def test_duplicate_native_keys_have_unique_ordinal_ids_and_no_arbitrary_join():
    raw=row();c,_=fixture();census=identity_census([raw,deepcopy(raw)])
    a=extract(raw,c,0,census);b=extract(raw,c,1,census)
    assert a['record_id']!=b['record_id']
    assert a['provenance']['identity_status']=='AMBIGUOUS_NATIVE_IDENTITY'
    assert a['followup']['status']=='NO_UNIQUE_COMPILED_CYCLE'

@pytest.mark.parametrize('section,field,value',[
    ('play_end','clock',30),('clock_control','timeout_use',False),('clock_control','runoff',0),
    (None,'generated_policy_supported',True),
])
def test_contract_rejects_inferred_terminal_or_generated_support(section,field,value):
    r=extract()
    (r[section]if section else r)[field]=value
    with pytest.raises(ValueError):validate_record(r,0,SHA)
