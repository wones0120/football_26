from copy import deepcopy

import pytest

from research.game_progression_pilot_20261020.shared_event_assignment.assignment import assign
from research.game_progression_pilot_20261020.shared_event_assignment.fixtures import cases,roster,event,IDS


@pytest.mark.parametrize('case',cases(),ids=lambda c:c['case_id'])
def test_case_conservation_identity_input_preservation_and_unknowns(case):
    args={k:v for k,v in case.items() if k!='case_id'};before=deepcopy(args)
    result=assign(**args)
    assert args==before and assign(**args)==result
    for team in result['teams']:
        for channel,c in team['channels'].items():
            assert c['assigned_count']+c['residual_count']==c['known_eligible_count']
            assert c['exact_count']==(None if c['unknown_eligibility_events'] else c['known_eligible_count'])
            players=[p for p in result['players'] if p['team']==team['team']]
            assert sum(p['assigned_counts_lower_bound'][channel] for p in players)==c['assigned_count']
    assert not result['forecast'] and not result['activation'] and result['likelihood']=='UNKNOWN'
    assert all(e['production'] is None and e['scoring'] is None for e in result['events'])


def test_shared_pass_is_one_physical_event_with_two_linked_official_channels():
    result=assign([event(1,'targeted_pass',passer=IDS['qb'],receiver=IDS['wr'])],roster(),evidence_kind='synthetic_fixture')
    assert len(result['events'])==1 and result['teams'][0]['exact_physical_count']==1
    credits=result['events'][0]['credits']
    assert [(c['channel'],c['player_master_id']) for c in credits]==[('pass_attempts',IDS['qb']),('targets',IDS['wr'])]


def test_sack_spike_scramble_kneel_and_exclusions_do_not_inflate_opportunities():
    case=cases()[0];case.pop('case_id');result=assign(**case);team=result['teams'][0]
    assert team['exact_physical_count']==7
    assert {c:v['exact_count'] for c,v in team['channels'].items()}==dict(pass_attempts=3,rush_attempts=3,targets=1)
    by_id={p['player_master_id']:p for p in result['players']}
    assert by_id[IDS['qb']]['assigned_counts_lower_bound']==dict(pass_attempts=3,rush_attempts=2,targets=0)
    assert all(not e['credits'] for e in result['events'] if e['kind'] in {'sack','no_play','two_point_try','control'})


def test_known_target_with_unknown_actor_is_different_from_unknown_target_eligibility():
    a=assign([event(1,'targeted_pass',passer=IDS['qb'])],roster(),evidence_kind='synthetic_fixture')
    b=assign([event(1,'pass_unknown_target',passer=IDS['qb'])],roster(),evidence_kind='synthetic_fixture')
    assert a['teams'][0]['channels']['targets']['exact_count']==1
    assert a['teams'][0]['channels']['targets']['residual_count']==1
    assert b['teams'][0]['channels']['targets']['exact_count'] is None
    assert b['teams'][0]['channels']['targets']['residual_count']==0
    assert all(p['channel_eligibility_unknown']['targets'] for p in b['players'] if p['team']=='A')


def test_unknown_mechanism_does_not_become_control_or_zero_physical_plays():
    result=assign([event(1,'unknown')],roster(),evidence_kind='synthetic_fixture')
    team=result['teams'][0]
    assert team['exact_physical_count'] is None and team['unknown_physical_events']==1
    assert all(c['exact_count'] is None for c in team['channels'].values())


@pytest.mark.parametrize('kind',['unknown_role','unknown_participation','unavailable_actor','unmapped_uuid'])
def test_unresolved_actor_retains_target_as_residual_without_transferring_it(kind):
    case=next(c for c in cases() if c['case_id']==kind);case.pop('case_id');result=assign(**case)
    assert result['teams'][0]['channels']['targets']['residual_count']==1
    assert result['teams'][0]['channels']['pass_attempts']['assigned_count']==1
    assert len(result['unresolved_assignments'])==1
    assert all(p['assigned_counts_lower_bound']['targets']==0 for p in result['players'])


@pytest.mark.parametrize('kind',['duplicate_event','duplicate_player','cross_team','name_instead_of_uuid',
    'missing_actor_slot','receiver_on_spike','rusher_on_pass','unknown_kind','missing_kind','non_fixture',
    'bad_participation','bad_roles','missing_team','multiple_receivers','multiple_games'])
def test_invalid_scope_identity_and_mechanism_rejected(kind):
    events=[event(1,'targeted_pass',passer=IDS['qb'],receiver=IDS['wr'])];actors=roster();evidence='synthetic_fixture'
    if kind=='duplicate_event':events.append(deepcopy(events[0]))
    if kind=='duplicate_player':actors.append(deepcopy(actors[0]))
    if kind=='cross_team':events[0]['actors']['receiver']=IDS['other']
    if kind=='name_instead_of_uuid':events[0]['actors']['receiver']='Receiver Name'
    if kind=='missing_actor_slot':del events[0]['actors']['rusher']
    if kind=='receiver_on_spike':events[0]['kind']='spike'
    if kind=='rusher_on_pass':events[0]['actors']['rusher']=IDS['rb']
    if kind=='unknown_kind':events[0]['kind']='invented_event'
    if kind=='missing_kind':events[0]['kind']=None
    if kind=='non_fixture':evidence='historical_or_forecast'
    if kind=='bad_participation':actors[2]['participation']='questionable_means_active'
    if kind=='bad_roles':actors[2]['roles']=['salary_eligible']
    if kind=='missing_team':events[0]['team']=''
    if kind=='multiple_receivers':events[0]['actors']['receiver']=[IDS['wr'],IDS['rb']]
    if kind=='multiple_games':events.append(dict(events[0],game_id='second-game'))
    with pytest.raises(ValueError):assign(events,actors,evidence_kind=evidence)


def test_missing_passer_residual_is_independent_of_known_receiver_credit():
    r=assign([event(1,'targeted_pass',receiver=IDS['wr'])],roster(),evidence_kind='synthetic_fixture')
    assert r['teams'][0]['channels']['pass_attempts']['residual_count']==1
    assert r['teams'][0]['channels']['targets']['assigned_count']==1


def test_preference_metadata_does_not_remove_or_reassign_football_credit():
    events=[event(1,'targeted_pass',passer=IDS['qb'],receiver=IDS['wr'])];actors=roster()
    a=assign(events,actors,evidence_kind='synthetic_fixture');actors[2]['optimizer_user_excluded']=True
    b=assign(events,actors,evidence_kind='synthetic_fixture')
    assert a['events']==b['events'] and a['teams']==b['teams']


def test_omitted_actor_goes_to_residual_without_giving_credit_to_remaining_receiver():
    events=[event(1,'targeted_pass',passer=IDS['qb'],receiver=IDS['wr'])];actors=roster();del actors[2]
    r=assign(events,actors,evidence_kind='synthetic_fixture')
    assert r['teams'][0]['channels']['targets']['residual_count']==1
    assert all(p['assigned_counts_lower_bound']['targets']==0 for p in r['players'])
