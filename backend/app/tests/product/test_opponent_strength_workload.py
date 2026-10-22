from copy import deepcopy
import pytest
from backend.app.product_services.opponent_strength_workload import build_lagged_defense_strength,build_opponent_strength_workload
from backend.app.product_services.schedule_context_features import VERSION as SCHEDULE_VERSION
from backend.app.product_services.weekly_effectiveness_catalog_features import VERSION as WEEKLY_VERSION
from backend.app.tests.product.test_fumble_event_components import play


def sources():
    games=[];records=[];weekly=[];levels={'MIA':-3,'BUF':-1,'NYJ':1,'NE':3}
    for week in range(1,6):
        pairs=[('BUF','MIA'),('NYJ','NE')]if week!=5 else[('BUF','NE'),('MIA','NYJ')]
        for away,home in pairs:
            gid=f'2025_{week:02d}_{away}_{home}'
            games.append(dict(game_id=gid,season=2025,week=week,game_type='REG',home_team=home,away_team=away))
            for number,(off,defense)in enumerate(((away,home),(home,away)),1):
                records.append(play(number,game_id=gid,season=2025,week=week,posteam=off,defteam=defense,epa=levels[defense]))
            if 'BUF'in(away,home):
                weekly.append(dict(season=2025,week=week,season_type='REG',team='BUF',source_player_id='00-0000001',player_master_id='11111111-1111-4111-8111-111111111111',native_game_id=gid,
                    metrics={'G04-M01':dict(denominator=week*10),'G07-M01':dict(denominator=week),'G09-M01':dict(denominator=week*2)},source_ref=dict(source_id=week)))
    schedule=dict(version=SCHEDULE_VERSION,game_rows=games,pregame_serving_eligible=False,semantic_sha256='native-schedule',provenance={})
    weekly=dict(version=WEEKLY_VERSION,before_period=202607,rows=weekly,provenance={},identity_review_requests=[],semantic_sha256='weekly',pregame_serving_eligible=False)
    return records,schedule,weekly


def run(records=None,schedule=None,weekly=None):
    r,s,w=sources();r=records if records is not None else r;s=schedule if schedule is not None else s;w=weekly if weekly is not None else w
    strength=build_lagged_defense_strength(r,s,season=2025,before_period=202607)
    return build_opponent_strength_workload(w,s,[strength],before_period=202607),strength


def test_fixed_first3_reference_bins_strict_lag_and_observed_channel_difference():
    out,c=run();r=out['rows'][0]
    assert c['reference_terciles']==dict(lower=-1,upper=1,known_defenses=4,unknown_defenses=0)
    assert r['channels']['pass_attempts']['strong_minus_weak']==-10
    assert r['channels']['rush_attempts']['strong_minus_weak']==-1
    assert r['channels']['targets']['strong_minus_weak']==-2
    assert [log['evaluation_scope']for log in r['logs']]==[False,False,False,True,True]
    assert all(x['max_contributing_period']is None or x['max_contributing_period']<202500+x['week']for x in c['contexts'])
    assert out['pregame_serving_eligible']is False and out['forecast']is None


def test_target_future_epa_never_changes_own_target_context_or_reference():
    r,s,w=sources();_,base=run()
    for row in r:
        if row['week']==5:row['epa']=1000
    _,changed=run(r,s,w)
    assert changed['reference_rows']==base['reference_rows']
    assert changed['reference_terciles']==base['reference_terciles']
    assert changed['contexts']==base['contexts']


def test_missing_scheduled_prior_game_masks_not_skipped_to_latest_known():
    r,s,w=sources();r=[row for row in r if not(row['week']==4 and row['game_id'].endswith('NYJ_NE'))]
    out,c=run(r,s,w);context=next(x for x in c['contexts']if x['game_id']=='2025_05_BUF_NE'and x['defense']=='NE')
    assert context['missing_source_games']==1 and context['group']is None
    assert '2025_04_NYJ_NE'in context['contributing_games']
    assert out['rows'][0]['unknown_strength_membership']==1
    assert out['rows'][0]['channels']['targets']['strong_minus_weak']is None


def test_unknown_eligible_or_epa_masks_exact_strength_not_known_zero():
    for change in(dict(no_play=None),dict(epa=None),dict(defteam=None),dict(season_type=None)):
        r,s,w=sources();r[0]|=change
        _,context=run(r,s,w)
        mia=next(x for x in context['contexts']if x['game_id']=='2025_04_BUF_MIA'and x['defense']=='MIA')
        assert mia['epa_per_physical_play']is None and mia['group']is None


def test_physical_union_spikes_kneels_scrambles_sacks_once_no2pt():
    r,s,w=sources();first=r[0]
    extra=[first|dict(play_id=3,pass_attempt=0,sack=1),first|dict(play_id=4,play_type='qb_spike',play_type_nfl='PASS',qb_spike=1),first|dict(play_id=5,play_type='qb_kneel',play_type_nfl='RUSH',rush_attempt=1,pass_attempt=0,qb_kneel=1),first|dict(play_id=6,play_type='run',play_type_nfl='RUSH',rush_attempt=1,pass_attempt=0,qb_scramble=1),first|dict(play_id=7,two_point_attempt=1)]
    _,c=run(r+extra,s,w);g=next(x for x in c['game_rows']if x['game_id']==first['game_id']and x['defense']=='MIA')
    assert g['known_physical_exposures']==5 and g['known_epa_sum']==-15


def test_zero_exposure_undefined_and_no_prior_game_unknown():
    _,c=run()
    first=next(x for x in c['contexts']if x['week']==1)
    assert first['epa_per_physical_play']is None and first['exact_exposures']is None


def test_unknown_group_masks_cell_stats_but_preserves_known_samples():
    out,c=run();c=deepcopy(c)
    # Add an observed actor log with an unavailable opponent context.
    r,s,w=sources();extra=deepcopy(w['rows'][-1]);extra.update(week=6,native_game_id=None);w['rows'].append(extra)
    s['game_rows'].append(dict(game_id='2025_06_BUF_NYJ',season=2025,week=6,game_type='REG',home_team='NYJ',away_team='BUF'))
    out=build_opponent_strength_workload(w,s,[c],before_period=202607);m=out['rows'][0]['channels']['targets']
    assert out['rows'][0]['unknown_strength_membership']==1
    assert m['cells']['strong']['per_observed_log']is None
    assert m['cells']['strong']['known_sample_mean']==8
    assert m['strong_minus_weak']is None


def test_missing_count_only_masks_its_channel_no_absent_player_zero():
    r,s,w=sources();w['rows'][-1]['metrics']['G09-M01']['denominator']=None
    out,_=run(r,s,w)
    assert out['rows'][0]['channels']['targets']['strong_minus_weak']is None
    assert out['rows'][0]['channels']['rush_attempts']['strong_minus_weak']==-1
    w['rows']=w['rows'][:-1];out,_=run(r,s,w)
    assert out['rows'][0]['channels']['rush_attempts']['cells']['weak']['observed_logs']==0
    assert out['rows'][0]['channels']['rush_attempts']['strong_minus_weak']is None


def test_future_context_reference_scope_duplicate_source_and_native_guard():
    r,s,w=sources();_,c=run();bad=deepcopy(c);bad['contexts'][0]['max_contributing_period']=202599
    with pytest.raises(ValueError,match='future|clock differs'):build_opponent_strength_workload(w,s,[bad],before_period=202607)
    with pytest.raises(ValueError,match='Duplicate source season'):build_opponent_strength_workload(w,s,[c,c],before_period=202607)
    with pytest.raises(ValueError,match='Duplicate native PBP'):run(r+[r[0]],s,w)
    r[0]['defteam']='SF'
    with pytest.raises(ValueError,match='sides contradict'):run(r,s,w)


def test_degenerate_reference_bins_do_not_force_strong_weak():
    r,s,w=sources()
    for row in r:row['epa']=0
    out,c=run(r,s,w)
    assert c['reference_terciles']['lower']==c['reference_terciles']['upper']==0
    assert all(x['group']is None for x in c['contexts'])
    assert out['rows'][0]['channels']['rush_attempts']['strong_minus_weak']is None


def test_native_order_of_input_and_source_receipt_times_do_not_change_measurements():
    r,s,w=sources();out,c=run(r,s,w);r.reverse();s['game_rows'].reverse();w['rows'].reverse()
    for row in w['rows']:row['source_ref']['imported_at']='2026-10-20T07:00:00Z'
    new,new_c=run(r,s,w)
    assert new_c['semantic_sha256']==c['semantic_sha256']
    assert new['semantic_sha256']==out['semantic_sha256']


def test_future_reference_or_contributing_key_cannot_hide_behind_authored_max_clock():
    r,s,w=sources();_,c=run();bad=deepcopy(c)
    bad['reference_rows'][0]['contributing_games'].append('2025_05_BUF_NE')
    with pytest.raises(ValueError,match='Reference contains'):build_opponent_strength_workload(w,s,[bad],before_period=202607)
    bad=deepcopy(c);bad['contexts'][0]['contributing_games'].append(bad['contexts'][0]['game_id'])
    with pytest.raises(ValueError,match='target/future'):build_opponent_strength_workload(w,s,[bad],before_period=202607)


def test_retained_loader_exact_bytes_schema_actual_clocks_not_original_pregame(tmp_path):
    import hashlib
    import pyarrow as pa
    import pyarrow.parquet as pq
    from backend.app.product_services.opponent_strength_workload import load_retained_defense_strength_context
    r,s,w=sources();path=tmp_path/'original.parquet';pq.write_table(pa.Table.from_pylist(r),path);raw=path.read_bytes()
    descriptor=dict(path=str(path),manifest=dict(url='https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2025.parquet',received_at='2026-10-13T12:00:00Z',sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)))
    out=load_retained_defense_strength_context(descriptor,s,before_period=202607)
    assert out['semantic_sha256']==run()[1]['semantic_sha256']
    assert out['pregame_serving_eligible']is False and 'unknown'in out['provenance']['historical_availability']
    bad=deepcopy(descriptor);bad['manifest']['received_at']='2099-01-01T00:00:00Z'
    with pytest.raises(ValueError,match='clocks'):load_retained_defense_strength_context(bad,s,before_period=202607)
    bad=deepcopy(descriptor);bad['manifest']['sha256']='0'*64
    with pytest.raises(ValueError,match='hash'):load_retained_defense_strength_context(bad,s,before_period=202607)
    with pytest.raises(ValueError,match='row bound'):load_retained_defense_strength_context(descriptor,s,before_period=202607,max_rows=1)
