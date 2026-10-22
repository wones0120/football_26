from copy import deepcopy

import pytest

from research.game_progression_pilot_20261020.prior_workload_reference.reference import build_reference

PID='11111111-1111-4111-8111-111111111111'


def inputs():
    def row(native,counts,period):
        return dict(source_player_id=native,counts=dict(zip(('pass_attempts','rush_attempts','targets'),counts)),
            period=period,team='SF',game_id=f'2026_{period%100:02d}_DEN_SF',received_at='2026-10-15T00:00:00Z')
    def book(period):
        return dict(period=period,team='SF',game_id=f'2026_{period%100:02d}_DEN_SF',
            visual_review=True,stat_scope='FULL_GAME_INCLUDING_ANY_OVERTIME',pdf_observed_at='2026-10-15T00:00:00Z',
            counts=dict(pass_attempts=10,rush_attempts=10,targets=8),sacks=1,physical_plays=21,receiving_target_rows=[3,5])
    return dict(rows=[row(n,c,p) for p in [202604,202605] for n,c in [('native',(10,2,3)),('other',(0,8,5))]],
        actors=[dict(player_master_id=PID,source_player_id='native',team='SF')],
        official=[book(p) for p in [202604,202605]],periods=[202604,202605],before_period=202606,cutoff='2026-10-19T23:00:00Z')


def test_shared_window_full_team_denominator_keeps_unmapped_work():
    case=inputs();before=deepcopy(case);r=build_reference(**case)
    assert case==before and build_reference(**case)==r
    p=r['players'][0]['channels']['targets']
    assert p['observed_window_sum']==6 and p['official_window_denominator']==16 and p['observed_share']==.375
    assert p['observed_mean']==3
    for team in r['team_reconciliation']:
        c=team['channels']['targets']
        assert c['current_roster_known_count']==3 and c['other_native_actor_known_count']==5
        assert c['unaccounted_official_count']==0
    assert len(r['identity_review_requests'])==2 and not r['activation'] and not r['forecast']


def test_absent_actor_row_is_unknown_not_inactive_or_zero():
    case=inputs();case['rows']=case['rows'][1:]
    p=build_reference(**case)['players'][0]['channels']['targets']
    assert p['observed_counts']==[None,3] and p['missing_row_periods']==[202604]
    assert p['observed_share'] is None and p['observed_mean'] is None


@pytest.mark.parametrize('kind',['missing_component','dropped_other_actor','disagreement','missing_book'])
def test_unsupported_source_reconciliation_never_becomes_exact_share(kind):
    case=inputs()
    if kind=='missing_component':case['rows'][1]['counts']['targets']=None
    if kind=='dropped_other_actor':del case['rows'][1]
    if kind=='disagreement':case['rows'][1]['counts']['targets']=4
    if kind=='missing_book':case['official'].pop(0)
    r=build_reference(**case)
    assert r['players'][0]['channels']['targets']['observed_share'] is None
    assert r['team_reconciliation'][0]['channels']['targets']['status']=='UNSUPPORTED_SOURCE_RECONCILIATION'


def test_zero_team_denominator_has_undefined_share_and_measured_zero_reference():
    case=inputs()
    for row in case['rows']:row['counts']['targets']=0
    for book in case['official']:book['counts']['targets']=0;book['receiving_target_rows']=[0]
    p=build_reference(**case)['players'][0]['channels']['targets']
    assert p['observed_share'] is None and p['share_reason']=='zero_denominator' and p['observed_mean']==0


@pytest.mark.parametrize('kind',['future_period','future_source','future_book','duplicate_native','duplicate_canonical',
    'foreign_team','foreign_game','book_team','book_period','duplicate_book','noninteger','negative','nan','bool',
    'target_over_pass','physical','target_rows','wrong_scope','unreviewed','bad_uuid'])
def test_invalid_time_identity_scope_or_football_accounting_rejected(kind):
    case=inputs();row=case['rows'][0];book=case['official'][0]
    if kind=='future_period':case['periods']=[202606]
    if kind=='future_source':row['received_at']='2026-10-20T00:00:00Z'
    if kind=='future_book':book['pdf_observed_at']='2026-10-20T00:00:00Z'
    if kind=='duplicate_native':case['rows'].append(deepcopy(row))
    if kind=='duplicate_canonical':case['actors'].append(deepcopy(case['actors'][0]))
    if kind=='foreign_team':row['team']='WAS'
    if kind=='foreign_game':row['game_id']='2026_06_DEN_SF'
    if kind=='book_team':book['game_id']='2026_04_DEN_WAS'
    if kind=='book_period':book['game_id']='2026_05_DEN_SF'
    if kind=='duplicate_book':case['official'].append(deepcopy(book))
    if kind=='noninteger':row['counts']['targets']=1.5
    if kind=='negative':row['counts']['targets']=-1
    if kind=='nan':row['counts']['targets']=float('nan')
    if kind=='bool':row['counts']['targets']=True
    if kind=='target_over_pass':book['counts']['targets']=11
    if kind=='physical':book['physical_plays']=20
    if kind=='target_rows':book['receiving_target_rows']=[2]
    if kind=='wrong_scope':book['stat_scope']='REGULATION_ONLY'
    if kind=='unreviewed':book['visual_review']=False
    if kind=='bad_uuid':case['actors'][0]['player_master_id']='Display Name'
    with pytest.raises(ValueError):build_reference(**case)


def test_omitting_current_actor_does_not_shrink_denominator_or_redistribute():
    case=inputs();case['actors'].append(dict(player_master_id='22222222-2222-4222-8222-222222222222',source_player_id='other',team='SF'))
    original=build_reference(**case)
    case['actors'].pop()
    omitted=build_reference(**case)
    assert omitted['players'][0]==original['players'][0]
    assert omitted['team_reconciliation'][0]['channels']['targets']['official_denominator']==8


def test_current_availability_preferences_do_not_rewrite_historical_counts():
    case=inputs();before=build_reference(**case)
    case['actors'][0].update(participation='UNAVAILABLE_REPORTED',optimizer_excluded=True)
    assert build_reference(**case)==before
