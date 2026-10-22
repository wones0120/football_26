from copy import deepcopy
import pytest
from backend.app.product_services.workload_venue_splits import build_workload_venue_splits
from backend.app.product_services.schedule_context_features import VERSION
from backend.app.tests.product.test_weekly_effectiveness_catalog_features import row, build


def sources():
    records=[]; games=[]
    for week in range(1,5):
        r=row(week=week,source_id=week);r['raw_row_json']['week']=week;r['raw_row_json']['carries']=week
        records.append(r)
        games.append(dict(season=2025,week=week,game_type='REG',game_id=str(week),home_team='LA' if week%2 else 'SF',away_team='SF' if week%2 else 'LA'))
    return build(records),dict(version=VERSION,game_rows=games,pregame_serving_eligible=False,semantic_sha256='schedule',provenance={})


def run(w=None,s=None):
    weekly,schedule=sources();return build_workload_venue_splits(w or weekly,s or schedule,before_period=202607)


def test_native_home_away_known_zero_and_separate_counts():
    r=run()['rows'][0];m=r['metrics']['rush_attempts']
    assert r['team']=='LAR' and m['home']['exact_sum']==4 and m['away']['exact_sum']==6
    assert m['home_minus_away']==-1 and r['metrics']['pass_attempts']['home_minus_away']==0
    assert run()['pregame_serving_eligible'] is False


def test_missing_exposure_no_skip_and_unmatched_venue_not_guessed():
    w,s=sources();w['rows'][0]['metrics']['G07-M01']['denominator']=None
    assert run(w,s)['rows'][0]['metrics']['rush_attempts']['home_minus_away'] is None
    w,s=sources();s['game_rows'].pop()
    assert run(w,s)['rows'][0]['metrics']['rush_attempts']['unknown_venue_logs']==1
    assert run(w,s)['rows'][0]['metrics']['rush_attempts']['home_minus_away'] is None


def test_single_side_no_absence_zero_and_seasons_teams_separate():
    w,s=sources();w['rows']=w['rows'][:1]
    assert run(w,s)['rows'][0]['metrics']['rush_attempts']['away']['per_observed_log'] is None
    w,s=sources();w['rows'][0]['team']='SF'
    assert len(run(w,s)['rows'])==2


@pytest.mark.parametrize('mutation',['future','duplicate','game','negative','identity','serving','schedule'])
def test_guards(mutation):
    w,s=sources()
    if mutation=='future':w['rows'][0].update(season=2026,week=7)
    if mutation=='duplicate':w['rows'].append(deepcopy(w['rows'][0]))
    if mutation=='game':w['rows'][0]['native_game_id']='wrong'
    if mutation=='negative':w['rows'][0]['metrics']['G07-M01']['denominator']=-1
    if mutation=='identity':w['rows'][0]['player_master_id']='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
    if mutation=='serving':s['pregame_serving_eligible']=True
    if mutation=='schedule':s['game_rows'].append(deepcopy(s['game_rows'][0]))
    with pytest.raises(ValueError):run(w,s)


def test_order_and_source_clock_stability():
    w,s=sources();sha=run(w,s)['semantic_sha256'];w['rows'].reverse();s['game_rows'].reverse()
    for r in w['rows']:r['source_ref']['imported_at']='2026-10-20T00:00:00Z'
    assert run(w,s)['semantic_sha256']==sha


def test_unbound_native_team_masks_other_same_season_group():
    w,s=sources();extra=deepcopy(w['rows'][0]);extra['team']=None;extra['week']=5;w['rows'].append(extra)
    r=next(r for r in run(w,s)['rows'] if r['team']=='LAR')
    assert r['native_team_scope_unknown'] and r['metrics']['rush_attempts']['home_minus_away'] is None
