from copy import deepcopy
import hashlib
import pandas as pd
import pytest

from backend.app.product_services.team_opportunity_matrix import load_retrospective_context,build_team_matrix,FEATURES
from backend.app.tests.product.test_environment_context_evidence import event
from backend.app.tests.product.test_defense_context_evidence import build as defense,CUTOFF
from backend.app.tests.product.test_environment_context_evidence import build as environment


def contexts():
    rows=[]
    for week in range(1,6):
        rows.extend([event(1,game_id=f'2026_{week:02d}_BUF_MIA',week=week),event(2,game_id=f'2026_{week:02d}_BUF_MIA',week=week,
            posteam='MIA',defteam='BUF',passer_player_id='other-q',receiver_player_id='other-w')])
    return [dict(defense=defense(rows),environment=environment(rows))]


def weekly():
    rows=[]
    for period in (202518,202601,202602,202603,202604,202605):
        for team in ('BUF','MIA'):
            # Unmapped non-QB carries stay in official full-source label budget.
            for actor,position,passes,rushes in [('q','QB',30,2),('unmapped','RB',0,20)]:
                rows.append(dict(player_master_id=team+'-'+actor if actor=='q' else None,source_player_id=team+'-'+actor,
                    period=period,team=team,position=position,pass_attempts=passes,rush_attempts=rushes,targets=0,
                    imported_at='2026-10-19T19:00:00Z'))
    return pd.DataFrame(rows)


def target(week):return dict(game_id=f'2026_{week:02d}_BUF_MIA',season=2026,week=week,team='BUF',opponent='MIA')


def test_prior_currentseason_context_and_separate_crossseason_legacy_windows():
    matrix=build_team_matrix(weekly(),[target(3),target(6)],contexts(),before_period=202606,cutoff=CUTOFF)
    historical,current=matrix['rows']
    assert historical['context_periods']==[202601,202602]
    assert 202518 in historical['legacy_periods']
    assert historical['labels']==dict(pass_attempts=30,rush_attempts=22)
    assert historical['features']['pass_mean3']==30
    assert historical['features']['own_context_games']==2
    assert current['features']['own_context_games']==5
    assert current['labels']==dict.fromkeys(('pass_attempts','rush_attempts'))
    assert list(current['features'])==list(FEATURES)
    assert current['features']['opponent_dropback_success_known_exposure']==5


def test_target_game_features_never_enter_own_or_opponent_prefix():
    original=contexts();changed=deepcopy(original)
    for kind in ('defense','environment'):
        for row in changed[0][kind]['game_rows']:
            if row['week']==3:
                for metric in row['metrics'].values():metric['observed_outcome_sum']=999
    a=build_team_matrix(weekly(),[target(3)],original,before_period=202606,cutoff=CUTOFF)
    b=build_team_matrix(weekly(),[target(3)],changed,before_period=202606,cutoff=CUTOFF)
    assert a['matrix_sha256']==b['matrix_sha256']


def test_no_context_is_unknown_not_zero_and_missing_label_unscoreable():
    history=weekly();history.loc[(history.period==202603)&history.position.eq('RB'),'rush_attempts']=None
    result=build_team_matrix(history,[target(3)],[],before_period=202606,cutoff=CUTOFF)['rows'][0]
    assert result['features']['own_pass_call_mean'] is None
    assert result['features']['own_context_games']==0
    assert result['labels']['rush_attempts'] is None
    assert result['label_status']=='unscoreable_or_forward'


def test_native_conflict_duplicate_and_future_target_rejected():
    for targets in ([target(6),target(6)],[target(7)],[target(6)|dict(opponent='GB')]):
        with pytest.raises(ValueError):build_team_matrix(weekly(),targets,contexts(),before_period=202606,cutoff=CUTOFF)
    with pytest.raises(ValueError,match='Duplicate measured'):
        build_team_matrix(weekly(),[target(6)],contexts()*2,before_period=202606,cutoff=CUTOFF)


def source(tmp_path,rows=None):
    values=rows or [event()]
    for r in values:
        r['passer_player_id']='00-0000001';r['receiver_player_id']='00-0000002';r['rusher_player_id']='00-0000001'
    path=tmp_path/'history.parquet';pd.DataFrame(values).to_parquet(path,index=False)
    return dict(path=str(path),manifest=dict(url='https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2026.parquet',
        received_at='2026-10-19T19:00:00Z',sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size))


def test_real_parquet_manifest_hash_native_keys_and_later_source_clock_preserved(tmp_path):
    descriptor=source(tmp_path)
    result=load_retrospective_context(descriptor,cutoff=CUTOFF)
    assert result['status']=='verified_revised_retrospective_context'
    assert result['source']['captured_at']=='2026-10-19T19:00:00Z'
    assert 'not a historical operational Snapshot' in result['source']['verification_basis']
    assert result['environment']['game_rows'][0]['known_offensive_snaps']==1
    assert result['defense']['game_rows'][0]['metrics']['G14-M07']['known_outcome_events']==1


@pytest.mark.parametrize('change',[dict(received_at='2026-10-20T00:00:00Z'),dict(received_at='2026-10-19T19:00:00'),dict(sha256='0'*64),dict(url='https://other.invalid/pbp')])
def test_retrospective_source_bad_hash_future_naive_or_wrong_source_rejected(tmp_path,change):
    descriptor=source(tmp_path);descriptor['manifest'].update(change)
    with pytest.raises(ValueError):load_retrospective_context(descriptor,cutoff=CUTOFF)


def test_retrospective_native_duplicate_and_row_bounds(tmp_path):
    descriptor=source(tmp_path,[event(),event(1)])
    with pytest.raises(ValueError,match='Duplicate native'):load_retrospective_context(descriptor,cutoff=CUTOFF)
    with pytest.raises(ValueError,match='row bound'):load_retrospective_context(descriptor,cutoff=CUTOFF,max_rows=1)


def test_current_matrix_means_match_actual_serving_builder_windows():
    context=contexts()[0]
    result=build_team_matrix(weekly(),[target(6)],[context],before_period=202606,cutoff=CUTOFF)['rows'][0]
    own=next(r for r in context['environment']['team_windows'] if r['team']=='BUF')
    opponent=next(r for r in context['defense']['team_windows'] if r['defense_team']=='MIA')
    assert result['features']['own_pass_call_mean']==own['metrics']['G02-M01']['observed_known_mean']
    assert result['features']['opponent_dropback_epa_mean']==opponent['metrics']['dropback_epa_support']['observed_known_mean']
    assert result['features']['opponent_inside5_rush_td_known_exposure']==opponent['metrics']['G15-M09']['known_outcome_events']
    assert result['features']['own_known_snaps_per_observed_log']==own['offensive_play_volume']['known_snaps_per_observed_log']


def archived_market(week=3):
    return dict(game_id=f'2026_{week:02d}_BUF_MIA',season=2026,week=week,home_team='MIA',away_team='BUF',game_total=48.5,home_spread=-3,
        market_kind='retrospective_archived_pregame_line',actual_received_at='2026-10-19T19:00:00Z',source_sha256='a'*64)


def live_market():
    return archived_market(6)|dict(market_kind='captured_pregame_snapshot',observed_at='2026-10-19T19:00:00Z',
        ingested_at='2026-10-19T19:01:00Z',kickoff_at='2026-10-20T00:15:00Z',source_snapshot_id='raw',market_snapshot_id='market')


def test_pregame_market_away_home_sign_current_parity_missingmask_and_score_exclusion():
    rows=[target(6),target(6)|dict(team='MIA',opponent='BUF')]
    quoted=live_market()|dict(result=99,total=1000,home_score=999)
    result=build_team_matrix(weekly(),rows,contexts(),before_period=202606,cutoff=CUTOFF,market_rows=[quoted])
    by={r['team']:r for r in result['rows']}
    assert by['BUF']['features']['game_total_line']==48.5
    assert by['BUF']['features']['team_spread_line']==3
    assert by['MIA']['features']['team_spread_line']==-3
    absent=build_team_matrix(weekly(),[target(6)],contexts(),before_period=202606,cutoff=CUTOFF,market_rows=[archived_market(6)])
    assert absent['rows'][0]['features']['game_total_line'] is None
    assert absent['rows'][0]['market_context']['status']=='missing'
    changed=live_market()|dict(game_total=55)
    other=build_team_matrix(weekly(),rows,contexts(),before_period=202606,cutoff=CUTOFF,market_rows=[changed])
    assert result['matrix_sha256']!=other['matrix_sha256']


def test_market_future_or_wrong_native_orientation_rejected_and_archived_lateclock_honest():
    for update in (dict(observed_at='2026-10-20T01:00:00Z'),dict(home_team='BUF',away_team='MIA')):
        with pytest.raises(ValueError):build_team_matrix(weekly(),[target(6)],contexts(),before_period=202606,cutoff=CUTOFF,market_rows=[live_market()|update])
    result=build_team_matrix(weekly(),[target(3)],contexts(),before_period=202606,cutoff=CUTOFF,market_rows=[archived_market()])
    assert result['rows'][0]['features']['game_total_line']==48.5
    assert result['provenance']['market_rows'][0]['actual_received_at']=='2026-10-19T19:00:00Z'


def test_archived_schedule_raw_home_margin_transforms_to_canonical_wager_sign(tmp_path):
    from backend.app.product_services.team_opportunity_matrix import load_retrospective_markets
    rows=[dict(game_id='2023_01_BUF_MIA',season=2023,week=1,game_type='REG',home_team='MIA',away_team='BUF',
        total_line=48.5,spread_line=3,gameday='2023-09-10',gametime='13:00',result=100,total=200)]
    path=tmp_path/'games.parquet';pd.DataFrame(rows).to_parquet(path,index=False)
    descriptor=dict(path=str(path),manifest=dict(url='https://github.com/nflverse/nflverse-data/releases/download/schedules/games.parquet',
        received_at='2026-10-13T16:48:52Z',sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size))
    market=load_retrospective_markets(descriptor,cutoff=CUTOFF)[0]
    assert market['home_spread']==-3 and market['game_total']==48.5
    assert market['original_quote_at'] is None
    assert 'result' not in market and 'total' not in market


@pytest.mark.parametrize('description',['The game has been suspended. Lightning in the area.','The game has resumed. Total delay time of 1 hour and 17 minutes.'])
def test_historical_weather_bookends_are_guarded_native_adjacency_controls(tmp_path,description):
    quiet=dict(posteam=None,defteam=None,play_type=None,desc=description,pass_attempt=None,rush_attempt=None,sack=None,
        qb_dropback=None,qb_scramble=0,qb_spike=0,qb_kneel=0,two_point_attempt=None)
    descriptor=source(tmp_path,[event(1),event(2,**quiet),event(3)])
    result=load_retrospective_context(descriptor,cutoff=CUTOFF)
    assert result['environment']['game_rows'][0]['known_offensive_snaps']==2
    assert result['environment']['game_rows'][0]['metrics']['G01-M04']['known_outcome_events']==0
    assert result['environment']['adjacency_control_breaks'][0]['play_id']=='2'
    descriptor=source(tmp_path,[event(2,**(quiet|dict(qb_scramble=1)))])
    with pytest.raises(ValueError,match='Unscoped historical offense'):
        load_retrospective_context(descriptor,cutoff=CUTOFF)


def test_unknown_unscoped_weather_prose_is_not_promoted_to_administrative(tmp_path):
    descriptor=source(tmp_path,[event(2,posteam=None,defteam=None,play_type=None,desc='The weather was delayed.',
        pass_attempt=None,rush_attempt=None,sack=None,qb_dropback=None,qb_scramble=0,qb_spike=0,qb_kneel=0,two_point_attempt=None)])
    with pytest.raises(ValueError,match='Unscoped historical offense'):
        load_retrospective_context(descriptor,cutoff=CUTOFF)
