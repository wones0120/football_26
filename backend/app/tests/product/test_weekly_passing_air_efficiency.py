from copy import deepcopy
import pytest
from backend.app.product_services.weekly_passing_air_efficiency import build_weekly_passing_air_efficiency,INPUT_VERSION


def source():
    ref=dict(source_id=1,ingest_run_id='ingest',imported_at='2000-01-01T00:00:00+00:00')
    actor=dict(season=2026,week=1,team='SF',source_player_id='native',player_master_id='uuid',native_game_id='2026_01_SF_WAS',QB_scope_source_proven=True,source_ref=ref,metrics={'G04-M01':dict(denominator=20)})
    weekly=dict(version=INPUT_VERSION,before_period=202607,pregame_serving_eligible=False,rows=[actor],identity_review_requests=[])
    row=dict(ref,game_id='2026_01_SF_WAS',source_player_id='native',season=2026,week=1,team='SF',position='QB',raw_row_json=dict(season_type='REG',position='QB',attempts=20,passing_air_yards=140))
    extract=dict(before_period=202607,actual_read_at='2000-01-02T00:00:00+00:00',rows=[row])
    return weekly,extract


def run(w=None,e=None):
    a,b=source();return build_weekly_passing_air_efficiency(w or a,e or b,cutoff='2000-01-03T00:00:00+00:00')['rows'][0]


def test_matched_official_aggregate_ratio():assert run()['value']==7


@pytest.mark.parametrize('air,expected',[(-40,-2),(0,0),(None,None),('bad',None),(float('inf'),None),(False,None)])
def test_signed_zero_missing_invalid_preserved(air,expected):
    w,e=source();e['rows'][0]['raw_row_json']['passing_air_yards']=air;assert run(w,e)['value']==expected


def test_zero_attempts_undefined():
    w,e=source();w['rows'][0]['metrics']['G04-M01']['denominator']=0;e['rows'][0]['raw_row_json']['attempts']=0
    assert run(w,e)['value'] is None


@pytest.mark.parametrize('field,value',[('source_player_id','other'),('season',2025),('week',2),('team','WAS'),('position','WR'),('ingest_run_id','new'),('imported_at','2000-01-02T00:00:00+00:00')])
def test_revision_mismatch_masks_not_silent_join(field,value):
    w,e=source();e['rows'][0][field]=value;row=run(w,e);assert row['value'] is None and row['source_revision_issue']


def test_changed_attempts_masks_incompatible_numerator():
    w,e=source();e['rows'][0]['raw_row_json']['attempts']=21;assert run(w,e)['value'] is None


def test_missing_retained_row_not_zero_or_dropped():
    w,e=source();e['rows']=[];row=run(w,e);assert row['value'] is None and row['source_revision_issue']


def test_duplicate_raw_row_rejected():
    w,e=source();e['rows']*=2
    with pytest.raises(ValueError):run(w,e)


def test_no_raw_projection_rows_outside_frozen_qb_universe():
    w,e=source();w['rows'][0]['QB_scope_source_proven']=False
    with pytest.raises(ValueError):run(w,e)


def test_target_week_outcomes_rejected_not_used():
    w,e=source();w['rows'][0]['week']=7;e['rows'][0]['week']=7
    with pytest.raises(ValueError):run(w,e)


def test_raw_native_and_period_contradiction_masks():
    w,e=source();e['rows'][0]['raw_row_json']['player_id']='other'
    assert run(w,e)['value'] is None
    w,e=source();e['rows'][0]['raw_row_json']['week']=2
    assert run(w,e)['value'] is None


def test_alias_attempt_conflict_masks():
    w,e=source();e['rows'][0]['raw_row_json']['passing_attempts']=21
    assert run(w,e)['value'] is None


def test_reader_uses_only_reviewed_ids_and_whitelisted_raw_fields():
    from datetime import datetime,UTC
    from backend.app.product_services.weekly_passing_air_efficiency import read_retained_air_projection
    w,e=source();record=deepcopy(e['rows'][0]);record['imported_at']=datetime(2000,1,1,tzinfo=UTC)
    class Result:
        def mappings(self):return self
        def all(self):return [record]
    class Connection:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,params):
            assert str(sql).lstrip().startswith('SELECT') and params['ids']==[1]
            assert 'passing_air_yards' in params['fields'] and 'player_display_name' not in params['fields']
            return Result()
    class Engine:
        def connect(self):return Connection()
    out=read_retained_air_projection(Engine(),w,cutoff='2000-01-03T00:00:00+00:00')
    assert out['expected_reviewed_QB_rows']==1 and out['rows'][0]['raw_row_json']['passing_air_yards']==140


def test_reviewed_input_loader_authenticates_bytes_producer_clock(tmp_path,monkeypatch):
    import json,hashlib
    from pathlib import Path
    from backend.app.product_services import weekly_effectiveness_catalog_features as producer
    from backend.app.product_services.weekly_passing_air_efficiency import load_reviewed_weekly_input,require_feature_use
    monkeypatch.chdir(tmp_path);w,e=source();w['provenance']=dict(actual_publication_at='2000-01-02T00:00:00+00:00',producer_code_sha256=hashlib.sha256(Path(producer.__file__).read_bytes()).hexdigest())
    raw=json.dumps(w).encode();sha=hashlib.sha256(raw).hexdigest();folder=tmp_path/'artifacts/weekly_effectiveness_catalog';folder.mkdir(parents=True);path=folder/(sha+'.json');path.write_bytes(raw);ref=dict(path=str(path),sha256=sha,bytes=len(raw))
    assert load_reviewed_weekly_input(ref,cutoff='2000-01-03T00:00:00+00:00')['rows']
    with pytest.raises(ValueError):load_reviewed_weekly_input(ref,cutoff='2000-01-01T00:00:00+00:00')
    block=dict(version='official_weekly_passing_air_per_attempt_v1',pregame_serving_eligible=False)
    with pytest.raises(ValueError):require_feature_use(block,purpose='model')
    path.write_text('changed')
    with pytest.raises(ValueError):load_reviewed_weekly_input(ref,cutoff='2000-01-03T00:00:00+00:00')


def test_native_game_id_change_cannot_reuse_weekly_exposure():
    w,e=source();e['rows'][0]['game_id']='2026_01_LA_SEA'
    assert run(w,e)['value'] is None
    e['rows'][0]['game_id']='2026_01_SF_SEA'
    assert run(w,e)['value'] is None


def test_every_present_raw_position_alias_checked():
    w,e=source();e['rows'][0]['raw_row_json']['pos']='WR'
    assert run(w,e)['value'] is None


def test_absent_native_game_ids_retain_explicit_period_team_grain():
    w,e=source();w['rows'][0]['native_game_id']=None;e['rows'][0]['game_id']=None
    row=run(w,e);assert row['value']==7 and 'grain only' in row['native_game_binding_basis']
    w['rows'][0]['native_game_id']='2026_01_SF_WAS'
    assert run(w,e)['value'] is None
