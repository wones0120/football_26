from copy import deepcopy
from pathlib import Path
import pytest
from backend.app.product_services.pfr_sack_conversion_catalog import build_pfr_sack_conversion

PID='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'

def fixture():
    sid='source';rows=[];actors=[]
    for index,(native,p,s) in enumerate((('PassAa00',10,2),('PassBb00',2,1))):
        rows.append(dict(game_id='2026_01_WAS_SF',season=2026,week=1,game_type='REG',team='WAS',opponent='SF',pfr_player_id=native,times_pressured=p,times_sacked=s,_source_snapshot_id=sid,_native_row=index))
        actors.append(dict(game_id='2026_01_WAS_SF',team='WAS',pfr_player_id=native,player_master_id=PID if index==0 else None,
            metrics={'G13-M03':dict(pressure_count=p)},source_refs=[dict(snapshot_id=sid,stat_type='pass')]))
    proof=[dict(snapshot_id=sid,season=2026,source_sha256='sha')]
    schedule=dict(game_rows=[dict(game_id='2026_01_WAS_SF',season=2026,week=1,game_type='REG',home_team='SF',away_team='WAS')],provenance={'snapshot_id':'schedule'})
    return rows,actors,proof,schedule

def run(args=None):return build_pfr_sack_conversion(*(args or fixture()),before_period=202606)

def metric(r,team='SF'):return next(x for x in r['game_rows'] if x['defense_team']==team)['metrics']['G14-M03']

def test_pooled_native_passer_counts_not_defender_votes_or_mean_fraction():
    result=run();m=metric(result)
    assert m['value']==3/12 and m['exact_sack_count']==3 and m['exact_pressure_count']==12
    row=next(r for r in result['game_rows'] if r['defense_team']=='SF')
    assert row['canonical_unknown_passers']==1 and len(row['native_passers'])==2
    assert result['pregame_serving_eligible'] is False and 'Weekly PFR lacks' in result['G14_M01_source_gap']

def test_missing_schedule_side_is_unknown_not_zero_pressure_game():
    m=metric(run(),'WAS');assert m['value'] is None and m['exact_sack_count'] is None
    assert m['source_game_status']=='missing_native_passer_source_unknown_not_zero'

@pytest.mark.parametrize('field',['times_pressured','times_sacked'])
def test_unknown_count_masks_exact_not_lower_bounds(field):
    rows,actors,proof,s=fixture();rows[0][field]=None
    if field=='times_pressured':actors[0]['metrics']['G13-M03']['pressure_count']=None
    m=metric(run((rows,actors,proof,s)))
    assert m['value'] is None and m['unknown_count_rows']==1


def test_known_zero_sacks_and_zero_pressure_are_distinct():
    rows,actors,proof,s=fixture()
    for row in rows:row['times_sacked']=0
    assert metric(run((rows,actors,proof,s)))['value']==0
    for row in rows:row['times_pressured']=0
    for a in actors:a['metrics']['G13-M03']['pressure_count']=0
    m=metric(run((rows,actors,proof,s)));assert m['value'] is None and m['exact_pressure_count']==0

@pytest.mark.parametrize('change',['sack_subset','native_opponent','period','duplicate','identity','source','count_receipt'])
def test_native_scope_identity_source_and_pressure_subset_guards(change):
    rows,actors,proof,s=fixture()
    if change=='sack_subset':rows[0]['times_sacked']=11
    elif change=='native_opponent':rows[0]['opponent']='GB'
    elif change=='period':rows[0]['week']=6
    elif change=='duplicate':rows.append(deepcopy(rows[0]))
    elif change=='identity':actors[1]['player_master_id']=PID
    elif change=='source':actors[0]['source_refs'][0]['snapshot_id']='other'
    else:actors[0]['metrics']['G13-M03']['pressure_count']=7
    with pytest.raises(ValueError):run((rows,actors,proof,s))


def test_phase_and_future_rows_never_enter_prior_measures():
    rows,actors,proof,s=fixture();rows[0]['game_type']='POST'
    with pytest.raises(ValueError):run((rows,actors,proof,s))


def test_source_row_and_receipt_order_do_not_change_semantics():
    args=fixture();original=run(args)['semantic_sha256'];args[0].reverse();args[1].reverse()
    assert run(args)['semantic_sha256']==original


def test_missing_canonical_native_receipt_never_silently_drops_source_passer():
    rows,actors,proof,s=fixture();actors.pop()
    with pytest.raises(ValueError,match='Missing reviewed'):run((rows,actors,proof,s))


def test_actual_indexed_load_canonical_alias_clock_and_byte_integrity(tmp_path):
    from datetime import datetime,UTC
    from types import SimpleNamespace
    import hashlib,json
    import polars as pl
    from backend.app.tests.test_source_capture import _session
    from backend.app.product_services.pfr_source_components import capture_pfr_asset,BASE
    from backend.app.product_services.schedule_context_features import capture_schedule_context
    from backend.app.product_services.pfr_sack_conversion_catalog import derive_pfr_sack_conversion
    from backend.app.product_services import pfr_advanced_features as producer
    from backend.app.services.source_capture import SourceCaptureService,SnapshotIntegrityError
    from backend.app.models import SourceSnapshot
    from backend.app.tests.product.test_schedule_context_features import row as schedule_row
    now=datetime(2026,10,20,3,tzinfo=UTC);session=_session()
    try:
        service=SourceCaptureService(session,snapshot_root=tmp_path/'source',clock=lambda:now)
        rows,actors,_,_=fixture();frame=pl.DataFrame([{k:v for k,v in row.items() if not k.startswith('_')}|dict(pfr_game_id='202609130sfo') for row in rows]);from io import BytesIO
        stream=BytesIO();frame.write_parquet(stream);buf=stream.getvalue();name='advstats_week_pass_2026.parquet'
        capture=capture_pfr_asset(service,dict(name=name,url=BASE+name,bytes=len(buf)),capture_season=2026,fetch=lambda asset:(buf,{}),clock=lambda:now)
        snapshot=session.get(SourceSnapshot,capture['source_snapshot_id'])
        for actor in actors:actor['source_refs'][0]['snapshot_id']=str(snapshot.snapshot_id)
        provider=SimpleNamespace(load_schedules=lambda seasons:pl.DataFrame([schedule_row(game_id='2026_01_WAS_SF',week=1)]))
        c=capture_schedule_context(service,season=2026,week=7,slate='FEATURES',slate_lock_at='2026-10-27T00:15:00Z',nfl_module=provider)
        schedule=session.get(SourceSnapshot,c.snapshot.snapshot_id)
        obj=dict(producer_code_sha256=hashlib.sha256(Path(producer.__file__).read_bytes()).hexdigest(),actual_derived_at=now.isoformat(),identity_queue=dict(requests=1),features=dict(version=producer.VERSION,before_period=202606,actor_game_rows=actors,provenance=dict(decision_cutoff_at=now.isoformat(),alias_receipts=[dict(source_system='pfr',source_key='PassAa00',player_master_id=PID,created_at='2026-10-19T00:00:00Z')],source_refs=[dict(snapshot_id=str(snapshot.snapshot_id),source_sha256=snapshot.content_sha256)])))
        def save():
            raw=json.dumps(obj,sort_keys=True).encode();sha=hashlib.sha256(raw).hexdigest();p=tmp_path/(sha+'.json');p.write_bytes(raw);return dict(path=str(p),sha256=sha,bytes=len(raw))
        ref=save();result=derive_pfr_sack_conversion([snapshot],ref,schedule,before_period=202606,cutoff=now,canonical_directory=tmp_path)
        assert metric(result)['value']==.25
        obj['features']['provenance']['alias_receipts'][0]['created_at']='2026-10-21T00:00:00Z'
        with pytest.raises(ValueError,match='alias'):derive_pfr_sack_conversion([snapshot],save(),schedule,before_period=202606,cutoff=now,canonical_directory=tmp_path)
        obj['features']['provenance']['alias_receipts'][0]['created_at']='2026-10-19T00:00:00Z'
        with pytest.raises(ValueError):derive_pfr_sack_conversion([snapshot],save(),schedule,before_period=202606,cutoff='2026-10-20T02:59:59Z',canonical_directory=tmp_path)
        original_rows=snapshot.row_count;snapshot.row_count+=1
        with pytest.raises((ValueError,SnapshotIntegrityError)):derive_pfr_sack_conversion([snapshot],save(),schedule,before_period=202606,cutoff=now,canonical_directory=tmp_path)
        snapshot.row_count=original_rows
        snapshot.content_sha256='0'*64
        with pytest.raises(SnapshotIntegrityError):derive_pfr_sack_conversion([snapshot],save(),schedule,before_period=202606,cutoff=now,canonical_directory=tmp_path)
    finally:session.close()
