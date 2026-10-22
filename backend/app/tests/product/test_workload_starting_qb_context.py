from copy import deepcopy
import pytest
from backend.app.product_services.evaluation_record import digest
from backend.app.product_services.workload_starting_qb_context import (
    normalize_starting_qb_context, build_workload_starting_qb_context, _kickoff,
)
from backend.app.product_services.schedule_context_features import VERSION
from backend.app.tests.product.test_weekly_effectiveness_catalog_features import row, build

CUTOFF='2026-10-20T05:00:00Z'
QB='00-0031234'; OTHER='00-0031235'


def sources():
    records=[]; games=[]; raw=[]
    for week in (1,2,3,4,7):
        game=dict(season=2026,week=week,game_type='REG',game_id=str(week),home_team='LAR',away_team='SF')
        games.append(game)
        raw.append(game | dict(gameday=f'2026-10-{week+1:02}' if week!=7 else '2026-10-25',gametime='13:00',
                               home_qb_id=QB if week in (1,3,7) else OTHER,away_qb_id=OTHER))
        if week!=7:
            r=row(season=2026,week=week,source_id=week)
            r['raw_row_json'].update(season=2026,week=week,carries=week-1)
            records.append(r)
    weekly=build(records)
    # Frozen fixture source build has an actual derivation timestamp; pin it before the chosen decision.
    weekly['provenance']['actual_derived_at']='2026-10-20T04:00:00Z'
    schedule=dict(version=VERSION,game_rows=games,pregame_serving_eligible=False,semantic_sha256='schedule',
                  provenance=dict(snapshot_id='snapshot',sha256='sha',observed_at='2026-10-20T03:00:00Z',captured_at='2026-10-20T03:01:00Z'))
    return weekly,schedule,normalize_starting_qb_context(raw,schedule)


def run(w=None,s=None,q=None,cutoff=CUTOFF):
    weekly,schedule,starters=sources()
    return build_workload_starting_qb_context(w or weekly,s or schedule,q or starters,before_period=202607,target_game_ids=['7'],cutoff=cutoff)


def rehash(q):
    q['semantic_sha256']=digest({k:q[k] for k in ('version','rows','role_scope')})


def test_observed_starter_context_known_zero_and_whole_game_counts():
    x=run(); r=next(r for r in x['rows'] if r['team']=='LAR'); m=r['metrics']['rush_attempts']
    assert m['with_reported_target_starter']['exact_per_observed_log']==1
    assert m['other_reported_starter']['exact_per_observed_log']==2
    assert m['with_minus_other']==-1
    assert r['target_qb_player_master_id']=='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
    assert x['pregame_serving_eligible'] is False and x['forecast'] is None


@pytest.mark.parametrize('scope',['target','history'])
def test_missing_starter_identity_masks_not_inferred_from_attempts(scope):
    w,s,q=sources()
    for r in q['rows']:
        if r['team']=='LAR' and r['game_id']==('7' if scope=='target' else '1'):
            r.update(source_starter_native_id=None,original_source_qb_id='')
    rehash(q)
    r=run(w,s,q)['rows'][0]
    assert r['unknown_historical_starter_logs']>0
    assert r['metrics']['pass_attempts']['with_reported_target_starter']['exact_per_observed_log'] is None


def test_no_opposite_group_or_missing_count_is_not_zero():
    w,s,q=sources();w['rows']=w['rows'][:1]
    m=run(w,s,q)['rows'][0]['metrics']['rush_attempts']
    assert m['with_reported_target_starter']['exact_per_observed_log']==0
    assert m['other_reported_starter']['exact_per_observed_log'] is None and m['with_minus_other'] is None
    w,s,q=sources();w['rows'][0]['metrics']['G07-M01']['denominator']=None
    assert run(w,s,q)['rows'][0]['metrics']['rush_attempts']['with_reported_target_starter']['exact_per_observed_log'] is None


@pytest.mark.parametrize('mutation',['checksum','clock','pair','native','kickoff','past','period'])
def test_source_scope_clock_and_target_guards(mutation):
    w,s,q=sources()
    if mutation=='checksum':q['rows'][0]['team']='BUF'
    if mutation=='clock':q['provenance']['captured_at']='2026-10-21T00:00:00Z'
    if mutation=='pair':q['provenance']['sha256']='other'
    if mutation=='native':q['rows'][0]['source_starter_native_id']=OTHER;rehash(q)
    if mutation=='kickoff':q['rows'][0]['native_kickoff_at']='2026-10-25T17:00:00Z';rehash(q)
    if mutation=='past':
        for r in q['rows']:
            if r['game_id']=='7':r.update(source_game_date='2026-10-19',native_kickoff_at=_kickoff('2026-10-19','13:00'))
        rehash(q)
    if mutation=='period':
        for r in q['rows']:
            if r['game_id']=='7':r['week']=8
        rehash(q)
    with pytest.raises(ValueError):run(w,s,q)


def test_native_source_orientation_and_dst_not_guessed():
    w,s,q=sources();raw=[dict(game_id='1',season=2026,week=1,game_type='REG',home_team='SF',away_team='LAR')]
    with pytest.raises(ValueError):normalize_starting_qb_context(raw,s)
    assert _kickoff('2026-11-01','01:30') is None
    assert _kickoff('2026-03-08','02:30') is None
    assert _kickoff('2026-10-25','13:00')=='2026-10-25T17:00:00+00:00'


def test_recapture_and_input_order_stable_values():
    w,s,q=sources();sha=run(w,s,q)['semantic_sha256'];w['rows'].reverse()
    for r in w['rows']:r['source_ref']['imported_at']='2026-10-20T02:00:00Z'
    q['provenance']['captured_at']='2026-10-20T03:02:00Z'
    assert run(w,s,q)['semantic_sha256']==sha


def test_missing_native_side_and_current_serving_rejected():
    w,s,q=sources();q['rows'].pop();rehash(q)
    with pytest.raises(ValueError,match='universe'):run(w,s,q)
    from backend.app.product_services.workload_starting_qb_context import require_feature_use
    x=run();assert require_feature_use(x,purpose='offline_descriptive') is x
    for purpose in ('forecast','model','optimizer','scenario'):
        with pytest.raises(ValueError):require_feature_use(x,purpose=purpose)
