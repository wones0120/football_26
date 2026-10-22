from copy import deepcopy
import hashlib
from uuid import UUID

import pandas as pd
import pytest
from backend.app.product_services.player_opportunity_history import load_retrospective_player_components
from backend.app.product_services.player_opportunity_components import require_component_use
from backend.app.tests.product.test_environment_context_evidence import event,CUTOFF

Q='00-0000001';W='00-0000002';IDS={Q:str(UUID(int=1)),W:str(UUID(int=2))}


def source(tmp_path,rows=None,drop=()):
    rows=deepcopy(rows if rows is not None else [event(1,complete_pass=1,air_yards=-3,first_down_rush=0,half_seconds_remaining=1700,ydstogo=1)])
    for row in rows:
        for field,native in [('passer_player_id',Q),('rusher_player_id',Q),('receiver_player_id',W)]:row.setdefault(field,native);row[field]=native if row[field] in {'q','w'} else row[field]
    frame=pd.DataFrame(rows).drop(columns=list(drop),errors='ignore');path=tmp_path/'pbp.parquet';frame.to_parquet(path,index=False)
    return dict(path=str(path),manifest=dict(url='https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2026.parquet',received_at='2026-10-19T19:00:00Z',sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size))


def load(desc,**changes):return load_retrospective_player_components(desc,cutoff=CUTOFF,canonical_ids=IDS,**changes)


def test_real_retained_parquet_additional_measurements_canonical_ids_and_original_clocks(tmp_path):
    desc=source(tmp_path);block=load(desc)
    assert block['field_availability']==dict.fromkeys(('complete_pass','air_yards','first_down_rush','half_seconds_remaining','ydstogo'),True)
    receiver=next(r for r in block['actor_game_rows'] if r['source_player_id']==W)
    assert receiver['player_master_id']==IDS[W] and receiver['shares']['average_target_depth']==-3
    assert block['provenance']['actual_source_received_at']=='2026-10-19T19:00:00+00:00'
    assert 'NOT a historical operational' in block['provenance']['source']['verification_basis']
    assert block['evidence_use']=='revised_retrospective_training_not_original_pregame'
    with pytest.raises(ValueError,match='not approved'):require_component_use(block,purpose='current_forecast')


def test_missing_measurement_columns_explicit_unknown_not_zero_and_unmapped_actors_retained(tmp_path):
    desc=source(tmp_path,drop=('complete_pass','air_yards','first_down_rush','half_seconds_remaining','ydstogo'))
    block=load_retrospective_player_components(desc,cutoff=CUTOFF)
    assert not any(block['field_availability'].values())
    assert len(block['identity_review_requests'])==2
    receiver=next(r for r in block['actor_game_rows'] if r['source_player_id']==W)
    assert receiver['metrics']['air_yards']['observed_outcome_sum'] is None
    assert receiver['shares']['average_target_depth'] is None
    assert block['team_denominators'][0]['official']['counts']['targets']==1


@pytest.mark.parametrize('change',[dict(sha256='0'*64),dict(received_at='2026-10-20T00:00:00Z'),dict(received_at='2026-10-19T19:00:00'),dict(url='https://other.invalid/pbp'),dict(url='https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2025.parquet')])
def test_manifest_hash_clock_source_and_native_season_guards(tmp_path,change):
    desc=source(tmp_path);desc['manifest'].update(change)
    with pytest.raises(ValueError):load(desc)


@pytest.mark.parametrize('rows,match',[
    ([event(1),event(1)],'Duplicate native'),
    ([event(1,play_id=1.5)],'Nonintegral'),
    ([event(1,posteam='GB')],'contradicts native'),
    ([event(1,receiver_player_id='Raw Name')],'native GSIS'),
])
def test_native_identity_and_game_keys_not_names_or_fractional_duplicates(tmp_path,rows,match):
    with pytest.raises(ValueError,match=match):load(source(tmp_path,rows))


def test_bounds_and_explicit_regular_phase_selection(tmp_path):
    desc=source(tmp_path,[event(1),event(2,season_type='POST')])
    with pytest.raises(ValueError,match='row bound'):load(desc,max_rows=1)
    with pytest.raises(ValueError,match='byte bound'):load(desc,max_bytes=1)
    block=load(desc)
    assert block['provenance']['source_rows']==2 and block['provenance']['excluded_not_explicit_REG_rows']==1
    assert block['provenance']['scoped_event_rows']==1


def test_quiet_exact_weather_bookend_retained_positive_offense_conflict_rejected(tmp_path):
    quiet=dict(posteam=None,play_type=None,pass_attempt=None,rush_attempt=None,sack=None,qb_dropback=None,qb_spike=None,qb_kneel=None,qb_scramble=None,two_point_attempt=None)
    rows=[event(1),event(2,**quiet,desc='The game has been suspended. Lightning in the area.')]
    block=load(source(tmp_path,rows))
    assert block['provenance']['retained_control_rows']==1
    rows[1]['qb_scramble']=1
    with pytest.raises(ValueError,match='Unscoped historical offense'):load(source(tmp_path,rows))


def test_source_order_invariance_but_measurement_and_field_availability_changes_significant(tmp_path):
    rows=[event(1,air_yards=10),event(2,air_yards=-2)]
    first=load(source(tmp_path,rows));second=load(source(tmp_path,rows[::-1]))
    assert first['semantic_measurements_sha256']==second['semantic_measurements_sha256']
    rows[0]['air_yards']=11
    assert first['semantic_measurements_sha256']!=load(source(tmp_path,rows))['semantic_measurements_sha256']



def test_native_yards_to_go_produces_known_shortyard_split_missing_column_unknown(tmp_path):
    rows=[event(1,play_type='run',pass_attempt=0,rush_attempt=1,qb_dropback=0,ydstogo=1),
          event(2,play_type='run',pass_attempt=0,rush_attempt=1,qb_dropback=0,ydstogo=3)]
    block=load(source(tmp_path,rows))
    rusher=next(r for r in block['actor_game_rows'] if r['source_player_id']==Q)
    short=rusher['metrics']['short_yard_carries']
    assert short['eligible_events']==1 and short['exact_within_log_sum']==1
    assert short['unknown_eligibility_events']==0
    missing=load(source(tmp_path,rows,drop=('ydstogo',)))
    rusher=next(r for r in missing['actor_game_rows'] if r['source_player_id']==Q)
    assert missing['field_availability']['ydstogo'] is False
    assert rusher['metrics']['short_yard_carries']['unknown_eligibility_events']==2
    assert rusher['metrics']['short_yard_carries']['exact_within_log_sum'] is None
