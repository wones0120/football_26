from copy import deepcopy

import pytest

from research.game_progression_pilot_20261020.player_role_evidence.evidence import build_evidence

PID='11111111-1111-4111-8111-111111111111'
CUTOFF='2026-10-19T23:00:00Z'


def inputs():
    actor=dict(player_master_id=PID,source_player_id='00-0000001',team='WAS',position='WR')
    base=dict(player_id=PID,team='WAS',position='WR',season=2026,week=6,
        source='retained',source_uri='https://www.commanders.com/news/report',source_ids=['snapshot','native-key'],
        observed_at='2026-10-19T15:00:00Z',received_at='2026-10-19T15:00:01Z')
    roster=dict(base,kind='roster_status',status='ACT')
    depth=dict(base,kind='depth_role',depth_position=1)
    game=dict(base,kind='game_status',status='QUESTIONABLE',report_contract='official_final_team_report_v1',
        report_phase='final',scope_verified=True,published_at='2026-10-17T12:00:00Z',
        kickoff_at='2026-10-20T00:15:00Z')
    return dict(extracted=dict(season=2026,week=6,actors=[actor],facts=[roster,depth],
        roster_coverage={'WAS':dict(player_master_ids=[PID],provider_rows_exhaustively_processed=True)},
        identity_review_requests=[dict(source_player_id='unmapped',team='WAS')],role_scope_exclusions=[]),
        official=dict(season=2026,week=6,facts=[game],identity_review_requests=[],
            identity_resolution_actions=[dict(source_key='native-key',player_master_id=PID,method='source_native_id')]),
        cutoff=CUTOFF,alias_recorded_at='2026-10-20T02:12:32Z')


def test_full_source_actor_retained_with_dated_facts_and_no_inferred_work():
    case=inputs();before=deepcopy(case);result=build_evidence(**case)
    assert case==before and build_evidence(**case)==result
    row=result['actors'][0]
    assert row['source_player_id']=='00-0000001' and row['depth_rank']==1
    assert row['designation_resolution']['effective_designation']=='QUESTIONABLE'
    assert row['participation']=='UNKNOWN'
    assert all(v is None for v in row['opportunity_shares'].values())
    assert row['replacement_work'] is None and result['identity_review_requests']==case['extracted']['identity_review_requests']
    assert result['alias_recorded_after_cutoff'] and not result['historical_pregame_identity_proven']
    assert not result['full_team_completeness_proven'] and not result['allocation_consumer_connected'] and not result['activation']


@pytest.mark.parametrize('status,participation',[('OUT','UNAVAILABLE_REPORTED'),('QUESTIONABLE','UNKNOWN'),
    ('NO_GAME_DESIGNATION','UNKNOWN')])
def test_game_designation_stays_separate_from_dressing_and_workload(status,participation):
    case=inputs();case['official']['facts'][0]['status']=status
    row=build_evidence(**case)['actors'][0]
    assert row['designation_resolution']['effective_designation']==status
    assert row['participation']==participation and row['replacement_work'] is None


def test_roster_act_or_no_report_row_does_not_prove_game_availability():
    case=inputs();case['official']['facts']=[]
    row=build_evidence(**case)['actors'][0]
    assert row['roster_facts'][0]['status']=='ACT'
    assert row['designation_resolution']['status']=='unknown' and row['participation']=='UNKNOWN'


def test_user_preference_metadata_does_not_clear_questionable():
    case=inputs();before=build_evidence(**case)
    case['official']['facts'][0]['optimizer_eligible']=True
    result=build_evidence(**case)
    assert result['actors'][0]['participation']==before['actors'][0]['participation']=='UNKNOWN'
    assert result['actors'][0]['designation_resolution']['effective_designation']=='QUESTIONABLE'


@pytest.mark.parametrize('change',['future','reversed','event_future','future_practice','foreign_team',
    'foreign_position','foreign_period','foreign_identity','duplicate','missing_native','missing_source',
    'universe_mismatch','period_mismatch','bad_uuid'])
def test_invalid_fact_identity_scope_and_chronology_rejected(change):
    case=inputs();f=case['official']['facts'][0];e=case['extracted']
    if change=='future':f['received_at']='2026-10-20T00:00:00Z'
    if change=='reversed':f['received_at']='2026-10-19T14:00:00Z'
    if change=='event_future':f['published_at']='2026-10-20T00:00:00Z'
    if change=='future_practice':f.update(kind='practice',practice_date='2026-10-20')
    if change=='foreign_team':f['team']='SF'
    if change=='foreign_position':f['position']='QB'
    if change=='foreign_period':f['week']=7
    if change=='foreign_identity':f['player_id']='22222222-2222-4222-8222-222222222222'
    if change=='duplicate':e['actors'].append(deepcopy(e['actors'][0]))
    if change=='missing_native':e['actors'][0]['source_player_id']=None
    if change=='missing_source':f['source_ids']=[]
    if change=='universe_mismatch':e['roster_coverage']['WAS']['player_master_ids']=[]
    if change=='period_mismatch':case['official']['week']=7
    if change=='bad_uuid':f['player_id']='Display Name'
    with pytest.raises(ValueError):build_evidence(**case)


@pytest.mark.parametrize('conflict',[False,True])
def test_stale_or_conflicting_depth_does_not_become_workload(conflict):
    case=inputs();depth=case['extracted']['facts'][1]
    if conflict:case['extracted']['facts'].append(dict(depth,depth_position=2))
    else:depth.update(observed_at='2026-10-17T15:00:00Z')
    row=build_evidence(**case)['actors'][0]
    assert row['depth_rank'] is None and row['depth_status']==('CONFLICT' if conflict else 'UNKNOWN')


def test_dated_practice_is_retained_without_donation_or_share_estimate():
    case=inputs();practice=dict(case['official']['facts'][0],kind='practice',practice_date='2026-10-16',practice_status='LP')
    case['official']['facts'].append(practice)
    row=build_evidence(**case)['actors'][0]
    assert row['dated_practice_facts']==[practice] and row['replacement_work'] is None
