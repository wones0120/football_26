from copy import deepcopy

import pytest

from research.game_progression_pilot_20261020.conditional_vacancy_accounting.accounting import account

DONOR='11111111-1111-4111-8111-111111111111'
RECIPIENT='22222222-2222-4222-8222-222222222222'
CUTOFF='2026-10-19T23:00:00Z'
CHANNELS=('pass_attempts','rush_attempts','targets')


def inputs():
    actors=[];players=[]
    for pid,native,counts,out in [(DONOR,'native-donor',(0,10,2),True),(RECIPIENT,'native-recipient',(0,3.5,1.5),False)]:
        base=dict(player_id=pid,team='WAS',position='RB',source='retained',source_ids=['snapshot','native-key-'+native],
            source_uri='https://www.commanders.com/news/report',observed_at='2026-10-19T15:00:00Z',
            received_at='2026-10-19T15:00:01Z',season=2026,week=6)
        chosen=dict(base,kind='game_status',status='OUT') if out else None
        actors.append(dict(player_master_id=pid,source_player_id=native,team='WAS',position='RB',participation='UNAVAILABLE_REPORTED' if out else 'UNKNOWN',
            depth_rank=1,depth_status='REPORTED',depth_facts=[dict(base,kind='depth_role',depth_position=1)],roster_facts=[dict(base,status='ACT',kind='roster_status')],
            designation_resolution=dict(status='resolved' if out else 'unknown',effective_designation='OUT' if out else None,chosen_fact=chosen)))
        players.append(dict(player_master_id=pid,source_player_id=native,team='WAS',channels={c:dict(observed_mean=n,status='SUPPORTED_OBSERVED_REFERENCE') for c,n in zip(CHANNELS,counts)}))
    workload=dict(before_period=202606,cutoff=CUTOFF,periods=[202604,202605],players=players,
        team_reconciliation=[dict(team='WAS',period=p,channels={c:dict(status='RECONCILED_FULL_SOURCE_AND_OFFICIAL',official_denominator=n) for c,n in zip(CHANNELS,(30,26,29.5))}) for p in [202604,202605]])
    roles=dict(season=2026,week=6,original_source_cutoff=CUTOFF,actors=actors)
    assumption=dict(assumption_id='AUTHORED_HALF',rationale='Conditional arithmetic sensitivity, likelihood unknown',
        donor_player_master_id=DONOR,recipient_player_master_id=RECIPIENT,channel='rush_attempts',fraction=.5)
    return workload,roles,[assumption]


def test_half_known_vacancy_preserves_budget_reference_and_partial_residual():
    args=inputs();before=deepcopy(args);out=account(*args)
    assert args==before and account(*args)==out
    players={p['player_master_id']:p for p in out['conditional_world']['players']}
    assert players[DONOR]['counts']['rush_attempts']==0
    assert players[DONOR]['hypothetical_active_role_reference_counts']['rush_attempts']==10
    assert players[RECIPIENT]['counts']['rush_attempts']==8.5 and players[RECIPIENT]['world_activity'] is None
    c=out['conditional_world']['teams']['WAS']['reconciliation']['rush_attempts']
    assert c['allocated_known']==8.5 and c['unallocated']==17.5
    assert out['reference']['players'][0]['counts']['rush_attempts']==10
    assert not out['activation'] and out['likelihood']=='UNKNOWN' and out['production_or_scoring'] is None


def test_no_authored_allocation_donates_nothing():
    workload,roles,_=inputs();out=account(workload,roles)
    assert not out['conditional_world']['availability_conditions']['conditional_allocations']
    assert out['conditional_world']['teams']['WAS']['reconciliation']['rush_attempts']['unallocated']==22.5


@pytest.mark.parametrize('which',[0,1])
def test_missing_reference_abstains_without_turning_unknown_proxy_into_known_vacancy(which):
    workload,roles,a=inputs()
    workload['players'][which]['channels']['rush_attempts'].update(observed_mean=None,status='UNKNOWN_INCOMPLETE_REFERENCE')
    out=account(workload,roles,a)
    t=out['conditional_world']['availability_conditions']['conditional_allocations'][0]
    assert t['transferred'] is None and t['status']=='unavailable_missing_reference_or_recipient_count'
    p=next(p for p in out['conditional_world']['players'] if p['player_master_id']==RECIPIENT)
    assert p['counts']['rush_attempts']==(3.5 if which==0 else None)


@pytest.mark.parametrize('kind',['Q','missing_role','IR_recipient','PS_recipient'])
def test_missing_or_adverse_evidence_is_explicit_abstention(kind):
    workload,roles,a=inputs()
    if kind=='Q':roles['actors'][0]['designation_resolution'].update(effective_designation='QUESTIONABLE',chosen_fact=None)
    if kind=='missing_role':roles['actors'][1].update(depth_rank=None,depth_facts=[],depth_status='UNKNOWN')
    if kind in {'IR_recipient','PS_recipient'}:roles['actors'][1]['roster_facts'][0]['status']='IR' if kind=='IR_recipient' else 'PS'
    out=account(workload,roles,a)
    assert out['abstentions'][0]['transferred'] is None and out['abstentions'][0]['status']=='ABSTAIN'
    assert not out['conditional_world']['availability_conditions']['conditional_allocations']


@pytest.mark.parametrize('kind',['future_scope','foreign_identity','duplicate_actor','overallocated','negative','bool','duplicate_assumption',
    'missing_rationale','bad_channel','foreign_team','self_transfer','unsupported_mean','unsupported_budget','future_role','stale_role','wrong_role_identity','wrong_out_proof'])
def test_invalid_inputs_fail_instead_of_redistributing(kind):
    workload,roles,a=inputs()
    if kind=='future_scope':roles['week']=7
    if kind=='foreign_identity':roles['actors'][1]['source_player_id']='other-native'
    if kind=='duplicate_actor':roles['actors'].append(deepcopy(roles['actors'][0]))
    if kind=='overallocated':a.append(dict(a[0],assumption_id='SECOND',fraction=.6))
    if kind=='negative':a[0]['fraction']=-.1
    if kind=='bool':a[0]['fraction']=True
    if kind=='duplicate_assumption':a.append(deepcopy(a[0]))
    if kind=='missing_rationale':a[0]['rationale']=''
    if kind=='bad_channel':a[0]['channel']='fantasy_points'
    if kind=='foreign_team':roles['actors'][1]['team']='SF'
    if kind=='self_transfer':a[0]['recipient_player_master_id']=DONOR
    if kind=='unsupported_mean':workload['players'][0]['channels']['rush_attempts']['status']='UNKNOWN'
    if kind=='unsupported_budget':workload['team_reconciliation'][0]['channels']['rush_attempts']['status']='UNKNOWN'
    if kind=='future_role':roles['actors'][1]['depth_facts'][0]['received_at']='2026-10-20T00:00:00Z'
    if kind=='stale_role':roles['actors'][1]['depth_facts'][0]['observed_at']='2026-10-17T00:00:00Z'
    if kind=='wrong_role_identity':roles['actors'][1]['depth_facts'][0]['player_id']=DONOR
    if kind=='wrong_out_proof':roles['actors'][0]['designation_resolution']['chosen_fact']['status']='QUESTIONABLE'
    with pytest.raises(ValueError):account(workload,roles,a)


def test_user_preferences_do_not_create_vacancies_or_change_amounts():
    workload,roles,a=inputs();before=account(workload,roles,a)
    for actor in roles['actors']:actor['optimizer_user_excluded']=True
    assert account(workload,roles,a)==before


def test_fractions_share_one_donor_channel_budget_across_recipients():
    workload,roles,a=inputs();a.append(dict(a[0],assumption_id='REST',fraction=.5))
    out=account(workload,roles,a)
    assert sum(t['transferred'] for t in out['conditional_world']['availability_conditions']['conditional_allocations'])==10
    assert out['conditional_world']['teams']['WAS']['reconciliation']['rush_attempts']['unallocated']==12.5
