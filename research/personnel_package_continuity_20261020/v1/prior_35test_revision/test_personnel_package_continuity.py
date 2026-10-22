from copy import deepcopy
from uuid import UUID
import pytest
from backend.app.product_services.personnel_package_continuity import build_personnel_package_continuity as build,physical_membership,globally_qualified_identity
from backend.app.product_services.participation_source_components import VERSION


def fixture():
    games=[dict(game_id='2025_01_SF_LA',season=2025,week=1,game_type='REG',game_date='2025-09-07',home_team='LAR',away_team='SF'),
        dict(game_id='2025_02_SF_NYG',season=2025,week=2,game_type='REG',game_date='2025-09-14',home_team='NYG',away_team='SF'),
        dict(game_id='2025_03_SF_LA',season=2025,week=3,game_type='REG',game_date='2025-09-21',home_team='LAR',away_team='SF')]
    roles=['C','G','G','T','T','QB','RB','WR','WR','WR','TE'];ids=[f'00-{i:07d}' for i in range(1,13)]
    receipts={n:dict(status='unique_native_alias',player_master_id=str(UUID(int=i+1)),original_alias_evidence=[]) for i,n in enumerate(ids)}
    rows=[];sources=[]
    for g in games:
        for play in ('1','2'):
            rows.append(dict(game_id=g['game_id'],play_id=play,season=2025,week=g['week'],season_type='REG',posteam='SF',defteam=g['home_team'],
                play_type='run',play_type_nfl='RUSH',no_play=0,two_point_attempt=0,pass_attempt=0,rush_attempt=1,sack=0))
            mapping=dict(zip(ids[:11],roles))
            sources.append(dict(game_id=g['game_id'],play_id=play,season=2025,week=g['week'],native_phase=None,possession_team='SF',
                participant_scopes=dict(offense=dict(status='aligned_native_position_list',native_player_ids=list(mapping),position_by_native_id=mapping))))
    part=dict(version=VERSION,season=2025,pregame_serving_eligible=False,rows=sources)
    return part,rows,games,receipts


def run(args):return build(*args,before_period=202519)
def sf(result):return [r for r in result['continuity_rows'] if r['team']=='SF']
def replace(source,old='00-0000010',new='00-0000012'):
    scope=source['participant_scopes']['offense'];role=scope['position_by_native_id'].pop(old);scope['position_by_native_id'][new]=role;scope['native_player_ids']=list(scope['position_by_native_id'])


def test_same_participant_roles_retained_and_firstgame_na():
    result=run(fixture());rows=sf(result)
    assert rows[0]['first_game_not_applicable'] and rows[0]['catalog_value'] is None
    assert rows[1]['catalog_value']==1 and rows[2]['catalog_value']==1


def test_snap_weighted_retention_not_average_of_unique_packages():
    args=fixture();part,raw,games,_=args
    for p in part['rows']:
        if p['week']==2 and p['play_id']=='2':replace(p)
    for play in ('3','4'):
        source=deepcopy(part['rows'][3]);source['play_id']=play;part['rows'].append(source)
        r=deepcopy(raw[3]);r['play_id']=play;raw.append(r)
    row=sf(run(args))[1]
    assert row['catalog_value']==0.25
    assert row['canonical']['known_retained_snaps']==1 and row['canonical']['known_nonretained_snaps']==3


def test_unknown_prior_can_still_prove_observed_retention_but_not_false():
    args=fixture();args[0]['rows'].pop(1)
    row=sf(run(args))[1];assert row['catalog_value']==1 and row['canonical']['prior_observed_universe_unknown']
    for p in args[0]['rows']:
        if p['week']==2:replace(p)
    row=sf(run(args))[1];assert row['catalog_value'] is None
    assert row['canonical']['known_nonretained_snaps']==0


def test_new_role_count_tuple_is_noncomparable_not_nonretained():
    args=fixture()
    for p in args[0]['rows']:
        if p['week']==2:p['participant_scopes']['offense']['position_by_native_id']['00-0000010']='TE'
    row=sf(run(args))[1]
    assert row['catalog_value'] is None and row['canonical']['known_noncomparable_snaps']==2


def test_unknown_current_unit_masks_whole_fraction_keeps_known_sample():
    args=fixture();args[0]['rows'].pop(3)
    row=sf(run(args))[1]
    assert row['catalog_value'] is None and row['canonical']['known_classified_sample_fraction']==1


def test_missing_prior_scheduled_log_not_skipped_to_old_game():
    args=fixture();args[1][:]=[r for r in args[1] if r['week']!=2]
    row=sf(run(args))[2]
    assert row['prior_scheduled_game_id']=='2025_02_SF_NYG' and row['catalog_value'] is None


def test_unassigned_side_masks_both_existing_team_cohorts_without_invented_unit():
    args=fixture();args[1][2]['posteam']=None
    result=run(args);unknown=[r for r in result['game_rows'] if r['game_id']=='2025_02_SF_NYG']
    assert all(r['unknown_physical_or_side']==1 for r in unknown)
    assert next(e for e in result['event_basis'] if e['game_id']=='2025_02_SF_NYG' and e['play_id']=='1')['unit_id'] is None
    assert sf(result)[1]['catalog_value'] is None


@pytest.mark.parametrize('field,value',[('no_play',None),('two_point_attempt',None),('play_type_nfl','UNSPECIFIED')])
def test_unknown_physical_membership_masks_current(field,value):
    args=fixture();args[1][2][field]=value
    assert sf(run(args))[1]['catalog_value'] is None


def test_excluded_no_play_and_two_point_not_weighted():
    for field in ('no_play','two_point_attempt'):
        args=fixture();args[1][2][field]=1
        assert sf(run(args))[1]['canonical']['known_comparable_snaps']==1


def test_official_pass_sack_union_once_and_kneel_included():
    args=fixture();raw=args[1][2];raw.update(play_type='pass',play_type_nfl='SACK',pass_attempt=1,sack=1,rush_attempt=0)
    assert physical_membership(raw) is True and sf(run(args))[1]['canonical']['known_comparable_snaps']==2
    raw.update(play_type='qb_kneel',play_type_nfl='QB_KNEEL',pass_attempt=0,sack=0,rush_attempt=1)
    assert physical_membership(raw) is None  # Unproven native vocabulary is not silently accepted.
    raw['play_type_nfl']='RUSH'
    assert physical_membership(raw) is True


def test_canonical_conflict_withheld_native_variant_retained():
    args=fixture();args[3]['00-0000001'].update(status='canonical_native_conflict',player_master_id=None)
    row=sf(run(args))[1]
    assert row['catalog_value'] is None and row['native_variant']['value']==1
    assert run(args)['identity_request_native_ids']==['00-0000001']


def test_all_edge_global_collision_closure_includes_noncohort_native():
    args=fixture();receipts=args[3];pid=receipts['00-0000001']['player_master_id'];other=str(UUID(int=99))
    receipts['00-0000999']=dict(status='canonical_native_conflict',player_master_id=None,original_alias_evidence=[dict(player_master_id=pid),dict(player_master_id=other)])
    result=run(args)
    assert set(result['global_identity_withheld_native_ids'])=={'00-0000001','00-0000999'}
    assert sf(result)[1]['catalog_value'] is None


@pytest.mark.parametrize('change',['wrong_team','wrong_phase','duplicate_id','wrong_role','not_gsis'])
def test_exact11_native_source_unit_required(change):
    args=fixture();source=args[0]['rows'][2];scope=source['participant_scopes']['offense']
    if change=='wrong_team':source['possession_team']='NYG'
    elif change=='wrong_phase':source['native_phase']='POST'
    elif change=='duplicate_id':scope['native_player_ids'][-1]=scope['native_player_ids'][0]
    elif change=='wrong_role':scope['position_by_native_id']['00-0000001']=None
    else:scope['native_player_ids'][0]='raw-name'
    assert sf(run(args))[1]['catalog_value'] is None


def test_duplicate_native_events_and_source_scope_rejected():
    args=fixture();args[1].append(deepcopy(args[1][0]))
    with pytest.raises(ValueError):run(args)
    args=fixture();args[0]['rows'][0]['season']=2024
    with pytest.raises(ValueError):run(args)


def test_known_conflicting_defense_rejected():
    args=fixture();args[1][2]['defteam']='SF'
    with pytest.raises(ValueError):run(args)


def test_missing_season_beginning_not_firstgame_na():
    args=fixture();args[2][:]=args[2][1:];args[1][:]=[r for r in args[1] if r['week']>1]
    row=sf(run(args))[0];assert not row['first_game_not_applicable'] and row['catalog_value'] is None


def test_shared_minimal_position_component_contract_accepted():
    from backend.app.product_services.participation_position_components import VERSION as POSITION_VERSION
    args=fixture();args[0]['version']=POSITION_VERSION
    assert sf(run(args))[1]['catalog_value']==1


def test_invalid_canonical_uuid_not_qualified_or_name_filled():
    args=fixture();args[3]['00-0000001']['player_master_id']='raw-name'
    row=sf(run(args))[1]
    assert row['catalog_value'] is None and row['native_variant']['value']==1


def test_append_only_incidents_are_idempotent_and_never_reopen():
    from backend.app.product_services.personnel_package_continuity import persist_package_identity_requests
    class Fake:
        def __init__(self):self.rows={};self.calls=[]
        def execute(self,sql,values):
            assert 'DO NOTHING' in str(sql) and 'DO UPDATE' not in str(sql)
            self.calls.append((str(sql),dict(values)));self.rows.setdefault(values['key'],dict(values,status='resolved'))
    args=fixture();args[3]['00-0000001'].update(status='canonical_native_conflict',player_master_id=None)
    block=run(args);fake=Fake();first=persist_package_identity_requests(fake,[block],source_refs=['immutable']);before=deepcopy(fake.rows)
    again=persist_package_identity_requests(fake,[block],source_refs=['immutable'])
    assert first==again and fake.rows==before and len(fake.rows)==1
    assert first['records'][0]['source_player_key']=='00-0000001'
    assert all(values['native']=='00-0000001' and values['candidates']=='[]' for _,values in fake.calls)


def test_minimal_original_pbp_loader_binds_hash_scope_and_clock(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    import hashlib
    from datetime import datetime,UTC,timedelta
    from backend.app.product_services.personnel_package_continuity import load_package_physical_source
    args=fixture();rows=args[1][:2];path=tmp_path/'original.parquet';pq.write_table(pa.Table.from_pylist(rows),path)
    raw=path.read_bytes();now=datetime.now(UTC)
    descriptor=dict(path=str(path),manifest=dict(url='https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2025.parquet',
        sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),received_at=(now-timedelta(seconds=1)).isoformat()))
    result,proof=load_package_physical_source(descriptor,season=2025,cutoff=now)
    assert len(result)==2 and proof['scoped_REG_rows']==2 and proof['field_availability']['no_play']
    for change in ('hash','bytes','future','uri'):
        bad=deepcopy(descriptor)
        if change=='hash':bad['manifest']['sha256']='bad'
        elif change=='bytes':bad['manifest']['bytes']=1
        elif change=='future':bad['manifest']['received_at']=(now+timedelta(seconds=10)).isoformat()
        else:bad['manifest']['url']='https://example.test/source'
        with pytest.raises(ValueError):load_package_physical_source(bad,season=2025,cutoff=now)
    with pytest.raises(ValueError):load_package_physical_source(descriptor,season=2025,cutoff=now,max_rows=1)


def test_source_only_participation_row_cannot_vanish_from_complete_universe():
    args=fixture();extra=deepcopy(args[0]['rows'][0]);extra['play_id']='99';args[0]['rows'].append(extra)
    for source in args[0]['rows']:
        if source['week']==2:replace(source)
    row=sf(run(args))[1]
    assert row['catalog_value'] is None and row['canonical']['known_nonretained_snaps']==0
    assert any(e['unknown_reason']=='source_participation_has_no_matching_REG_PBP_event' for e in run(args)['event_basis'])
    extra['game_id']='2025_02_SF_NYG';extra['week']=2
    assert sf(run(args))[1]['catalog_value'] is None


def test_unknown_scheduled_date_masks_order_not_missing_game_skip():
    args=fixture();args[2][1]['game_date']=None
    rows=sf(run(args));assert all(r['catalog_value'] is None for r in rows)
    assert all(not r['scheduled_predecessor_order_proven'] and r['prior_scheduled_game_id'] is None for r in rows)


def test_immediate_predecessor_uses_native_scheduled_date_not_numeric_week():
    args=fixture();args[2][1]['game_date']='2025-09-28'
    rows=sf(run(args));week2=next(r for r in rows if r['week']==2)
    assert week2['prior_scheduled_game_id']=='2025_03_SF_LA'


@pytest.mark.parametrize('flag',['qb_dropback','qb_scramble','qb_spike','qb_kneel'])
def test_positive_physical_indicators_cannot_hide_behind_zero_union(flag):
    raw=dict(play_type='no_play',play_type_nfl='TIMEOUT',no_play=0,two_point_attempt=0,pass_attempt=0,rush_attempt=0,sack=0)
    # Explicitly excluded no_play remains excluded, independent of inconsistent indicators.
    raw['play_type']=None;raw[flag]=1
    assert physical_membership(raw) is None
    raw['no_play']=1
    assert physical_membership(raw) is False


def test_live_native_physical_class_with_zero_official_union_is_unknown():
    args=fixture();raw=args[1][2];raw.update(pass_attempt=0,rush_attempt=0,sack=0)
    assert physical_membership(raw) is None and sf(run(args))[1]['catalog_value'] is None


def test_published_physical_flag_reader_binds_exact_semantics_and_producer(tmp_path):
    import json,hashlib
    from pathlib import Path
    from datetime import datetime,UTC,timedelta
    from backend.app.product_services.personnel_package_continuity import PHYSICAL_VERSION,load_package_physical_component
    from backend.app.product_services.evaluation_record import digest
    now=datetime.now(UTC);core=dict(version=PHYSICAL_VERSION,season=2025,source_rows=1,rows=fixture()[1][:1],pregame_serving_eligible=False)
    producer=Path('backend/app/product_services/personnel_package_continuity.py')
    value=dict(**core,semantic_sha256=digest(core),provenance=dict(original_descriptor=dict(manifest=dict(received_at=(now-timedelta(seconds=2)).isoformat())),
        actual_read_at=(now-timedelta(seconds=1)).isoformat(),actual_publication_at=now.isoformat(),producer_code_sha256=hashlib.sha256(producer.read_bytes()).hexdigest()))
    raw=json.dumps(value).encode();sha=hashlib.sha256(raw).hexdigest();path=tmp_path/(sha+'.json');path.write_bytes(raw);ref=dict(path=str(path),sha256=sha,bytes=len(raw))
    assert load_package_physical_component(ref,cutoff=datetime.now(UTC),directory=tmp_path)['source_rows']==1
    with pytest.raises(ValueError):load_package_physical_component(ref,cutoff=now-timedelta(seconds=3),directory=tmp_path)
    path.write_bytes(raw+b' ')
    with pytest.raises(ValueError):load_package_physical_component(ref,cutoff=datetime.now(UTC),directory=tmp_path)
