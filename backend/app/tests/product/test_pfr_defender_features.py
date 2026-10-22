from copy import deepcopy
import pytest
from backend.app.product_services.pfr_defender_features import build_defender_measurements

PID='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
A=[dict(source_system='pfr',source_key='Native00',player_master_id=PID,created_at='2026-10-19T00:00:00Z')]
def row(**kw):
    r=dict(summary_level='week',stat_type='def',season=2026,week=5,game_type='REG',game_id='2026_05_WAS_DAL',team='WAS',pfr_player_id='Native00',def_missed_tackle_pct=.125,def_missed_tackles=1,def_tackles_combined=7,def_pressures=2)
    r.update(kw);return r
def build(rows=None,aliases=A):return build_defender_measurements(rows or [row()],aliases,before_period=202606,cutoff='2026-10-20T03:00:00Z')
def test_source_fraction_not_percentage_division_or_team_rate():
    r=build()['actor_game_rows'][0]
    assert r['metrics']['G15-M07']['value']==.125
    assert r['metrics']['pressures']==2 and 'not_certified_team' in r['metrics']['G15-M07']['variant']
    assert build([row(def_missed_tackle_pct=12.5)])['actor_game_rows'][0]['metrics']['G15-M07']['value'] is None

def test_unknown_zero_and_fractional_count():
    assert build([row(def_missed_tackle_pct=None,def_missed_tackles=0)])['actor_game_rows'][0]['metrics']['missed_tackles']==0
    assert build([row(def_pressures=1.5)])['actor_game_rows'][0]['metrics']['pressures'] is None

def test_no_name_fallback_future_alias_and_conflict():
    assert build(aliases=[])['identity_review_requests']
    a=deepcopy(A);a[0]['created_at']='2026-10-21T00:00:00Z'
    assert build(aliases=a)['actor_game_rows'][0]['player_master_id'] is None
    assert build(aliases=A+[{**A[0],'player_master_id':'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'}])['identity_review_requests'][0]['reason']=='conflicting_native_alias'

@pytest.mark.parametrize('changes',[dict(summary_level='season'),dict(week=6),dict(game_type='POST'),dict(team='SF')])
def test_grain_and_period(changes):
    with pytest.raises(ValueError):build([row(**changes)])

def test_native_and_canonical_duplicates_reject():
    with pytest.raises(ValueError,match='Duplicate'):build([row(),row()])
    v=build([row(),row(pfr_player_id='Other00')],A+[{**A[0],'source_key':'Other00'}])
    assert len(v['actor_game_rows'])==2 and all(r['player_master_id'] is None for r in v['actor_game_rows'])
    assert len(v['canonical_identity_collisions'])==1 and len(v['identity_review_requests'])==2
    assert {q['reason'] for q in v['identity_review_requests']}=={'canonical_native_game_collision'}

def test_recapture_clocks_and_refs_not_semantic():
    a=deepcopy(A);a[0]['created_at']='2026-10-19T01:00:00Z'
    assert build([row(source_ref='a')])['semantic_sha256']==build([row(source_ref='b')],a)['semantic_sha256']

def test_verified_weekly_defense_wrapper_and_integrity(tmp_path):
    from io import BytesIO
    from datetime import datetime,UTC
    import polars as pl
    from backend.app.tests.test_source_capture import _session
    from backend.app.services.source_capture import SourceCaptureService,SnapshotIntegrityError
    from backend.app.models import SourceSnapshot
    from backend.app.product_services.pfr_source_components import capture_pfr_asset,BASE
    from backend.app.product_services.pfr_defender_features import build_verified_defender_features
    now=datetime(2026,10,20,3,tzinfo=UTC);session=_session()
    try:
        source={k:v for k,v in row().items() if k not in {'summary_level','stat_type'}}
        source['pfr_game_id']='202610110dal';source['opponent']='DAL'
        b=BytesIO();pl.DataFrame([source]).write_parquet(b);raw=b.getvalue();name='advstats_week_def_2026.parquet'
        report=capture_pfr_asset(SourceCaptureService(session,snapshot_root=tmp_path/'source',clock=lambda:now),dict(name=name,url=BASE+name),capture_season=2026,fetch=lambda a:(raw,{}),clock=lambda:now)
        s=session.get(SourceSnapshot,report['source_snapshot_id'])
        result=build_verified_defender_features([s],A,before_period=202606,cutoff=now)
        assert result['actor_game_rows'][0]['metrics']['G15-M07']['value']==.125
        assert result['pregame_serving_eligible'] is False
        with pytest.raises(ValueError,match='clock'):build_verified_defender_features([s],A,before_period=202606,cutoff='2026-10-20T02:59:00Z')
        s.content_sha256='0'*64
        with pytest.raises(SnapshotIntegrityError):build_verified_defender_features([s],A,before_period=202606,cutoff=now)
    finally:session.close()

def test_native_identity_queue_same_person_key_preserves_decisions():
    from backend.app.product_services.pfr_defender_features import persist_defender_identity_requests
    calls=[]
    class C:
        def execute(self,sql,params):calls.append((str(sql),params))
    v=build(aliases=[])
    q=persist_defender_identity_requests(C(),v)
    assert q['requests']==1 and calls[0][1]['key']=='pfr-player:Native00'
    assert 'DO NOTHING' in calls[0][0] and 'UPDATE' not in calls[0][0]

def test_nonfinite_native_fraction_remains_serializable_unknown():
    import json
    v=build([row(def_missed_tackle_pct=float('nan'))])
    assert v['actor_game_rows'][0]['metrics']['G15-M07']['value'] is None
    json.dumps(v,allow_nan=False)

def test_collision_quarantine_applies_to_native_key_in_other_games_not_global_alias_mutation():
    a=A+[{**A[0],'source_key':'Other00'}]
    before=deepcopy(a)
    v=build([row(),row(pfr_player_id='Other00'),row(game_id='2026_04_WAS_SF',week=4)],a)
    assert all(r['player_master_id'] is None for r in v['actor_game_rows'])
    assert a==before and len(v['actor_game_rows'])==3

def test_new_alias_contradiction_gets_evidence_key_without_reopening_person_resolution():
    from backend.app.product_services.pfr_defender_features import persist_defender_identity_requests
    calls=[]
    class C:
        def execute(self,sql,params):calls.append((str(sql),params))
    v=build([row(),row(pfr_player_id='Other00')],A+[{**A[0],'source_key':'Other00'}])
    result=persist_defender_identity_requests(C(),v)
    assert result['requests']==2
    assert all(p['key'].startswith('pfr-alias-conflict:') for _,p in calls)
    assert all('DO NOTHING' in sql and 'UPDATE' not in sql for sql,_ in calls)
    again=[]
    class D:
        def execute(self,sql,params):again.append(params['key'])
    persist_defender_identity_requests(D(),v)
    assert again==[p['key'] for _,p in calls]
