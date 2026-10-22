from copy import deepcopy
import pytest
from backend.app.tests.product.test_game_state_reconstruction import row
from research.game_progression_pilot_20261020.control_linkage.linkage import (
    indexes,enrichment,timeout_evidence,marker_link,clock_format,native_key)

def samples():
    before=row(play_id=900,order_sequence=1,quarter_seconds_remaining=136,half_seconds_remaining=1036,
        game_seconds_remaining=2836,home_timeouts_remaining=3,away_timeouts_remaining=3,timeout=0,timeout_team=None)
    event=row(play_id=895,order_sequence=2,quarter_seconds_remaining=103,half_seconds_remaining=1003,
        game_seconds_remaining=2803,home_timeouts_remaining=3,away_timeouts_remaining=2,timeout=1,timeout_team='BUF',play_type_nfl='TIMEOUT')
    after=row(play_id=883,order_sequence=3,quarter_seconds_remaining=103,half_seconds_remaining=1003,
        game_seconds_remaining=2803,home_timeouts_remaining=3,away_timeouts_remaining=2,timeout=0,timeout_team=None)
    return before,event,after

def test_native_timeout_and_debit_use_order_not_play_id_without_mutation():
    rows=list(samples());snapshot=deepcopy(rows);census,unique,previous,order=indexes(rows)
    r=enrichment(rows[1],1,'a'*64,census,unique,previous,order,{})
    t=r['timeout_use']
    assert t['status']=='REPORTED_TEAM_TIMEOUT'and t['team']=='BUF'
    assert t['prior_native_id'].endswith(':900')and t['prior_budget_snapshot']==[3,3]
    assert t['observed_budget_snapshot']==[3,2]and t['debit_status']=='CORROBORATED_SOURCE_BUDGET_DEBIT'
    assert t['snapshot_timing']=='AFTER_CURRENT_REPORTED_DEBIT'
    assert not r['continuation_supported']and r['play_end_game_clock']is None and rows==snapshot

@pytest.mark.parametrize('changes',[{'timeout':None},{'timeout_team':None},{'timeout_team':'OTHER'},
    {'play_deleted':1},{'replay_or_challenge':1,'replay_or_challenge_result':'reversed'},
    {'replay_or_challenge':1,'replay_or_challenge_result':None},{'timeout':0}])
def test_native_class_or_budget_drop_cannot_replace_timeout_evidence(changes):
    before,event,_=samples();event.update(changes)
    t=timeout_evidence(event,before,True)
    assert t['status']!='REPORTED_TEAM_TIMEOUT'and t['debit_status']=='UNKNOWN_OR_UNCORROBORATED_DEBIT'

@pytest.mark.parametrize('changes',[{'away_timeouts_remaining':3},{'home_timeouts_remaining':2},
    {'away_timeouts_remaining':None},{'away_timeouts_remaining':-1},{'away_timeouts_remaining':1.5},
    {'qtr':3,'game_half':'Half2','half_seconds_remaining':1003,'game_seconds_remaining':1003}])
def test_conflicting_budgets_or_half_reset_do_not_prove_debit(changes):
    before,event,_=samples();event.update(changes)
    t=timeout_evidence(event,before,True)
    assert t['status']=='REPORTED_TEAM_TIMEOUT'and t['debit_status']=='UNKNOWN_OR_UNCORROBORATED_DEBIT'

def test_attached_upheld_challenge_keeps_timeout_clock_unobserved():
    before,event,_=samples();event.update(play_type_nfl='PASS',replay_or_challenge=1,replay_or_challenge_result='upheld')
    t=timeout_evidence(event,before,True)
    assert t['status']=='REPORTED_TEAM_TIMEOUT'and t['attachment']=='ATTACHED_TO_NATIVE_PLAY'
    assert marker_link(event,None,{native_key(event):event})['source_event_clock']is None

@pytest.mark.parametrize('field',['order_sequence','play_id'])
def test_ambiguous_order_or_identity_disables_historical_links(field):
    rows=list(samples());rows[1][field]=rows[0][field]
    census,unique,previous,order=indexes(rows)
    assert not order[rows[0]['game_id']]and not previous
    r=enrichment(rows[1],1,'a'*64,census,unique,previous,order,{})
    assert r['clock_control_link']['status']=='NO_VALIDATED_FROZEN_ADMIN_LINK'
    assert r['timeout_use']['debit_status']=='UNKNOWN_OR_UNCORROBORATED_DEBIT'

def test_timeout_stop_clock_uses_bound_admin_proof_without_play_end_or_restart():
    rows=list(samples());_,unique,_,_=indexes(rows);event=rows[1]
    proof=dict(certified=True,kind='TIMEOUT',boundary_state=dict(half=1,half_seconds_remaining=1003),
        preceding_score_play_id='900',corroborating_next_play_id='883')
    r=marker_link(event,dict(proof=proof),unique)
    assert r['status']=='FROZEN_CERTIFIED_ADMIN_LINK'and r['timeout_stop_event_observed']
    assert r['source_event_clock']['half_seconds']==1003
    assert r['preceding_native_id'].endswith(':900')and r['following_native_id'].endswith(':883')
    assert r['play_end_game_clock']is None and r['restart']is None and r['runoff_enforcement']is None
    proof['boundary_state']['half_seconds_remaining']=1002
    assert marker_link(event,dict(proof=proof),unique)['status']=='NO_VALIDATED_FROZEN_ADMIN_LINK'
    proof['boundary_state']['half_seconds_remaining']=1003;del unique[native_key(rows[2])]
    assert marker_link(event,dict(proof=proof),unique)['status']=='NO_VALIDATED_FROZEN_ADMIN_LINK'

@pytest.mark.parametrize('value,expected',[(None,'MISSING'),('2023-09-10T17:03:25.203Z','WALL_TIMESTAMP'),
    ('2023-09-10T17:03:25+00:00','WALL_TIMESTAMP'),('01:03','QUARTER_CLOCK_LIKE_UNVALIDATED'),('0','OTHER_UNVALIDATED')])
def test_wall_timestamp_never_becomes_remaining_game_clock(value,expected):
    assert clock_format(value)==expected
