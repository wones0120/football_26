from copy import deepcopy
from datetime import datetime,UTC,timedelta
import pytest
from backend.app.product_services.center_sack_response import build_first_snap_centers,build_center_sack_response
from backend.app.product_services.participation_source_components import normalize_participation_rows
from backend.app.product_services.schedule_context_features import VERSION as SCHEDULE_VERSION
from backend.app.product_services.participation_defense_catalog import VERSION as COVERAGE_VERSION
from backend.app.tests.product.test_offensive_line_participation import source,start,snap,schedule,aliases,native,gid,NOW


def fixture():
    original=[source(1),source(2,replace=(0,22)),source(3,replace=(0,22))]
    participation=normalize_participation_rows(original,season=2023)
    schedule_source=dict(version=SCHEDULE_VERSION,game_rows=schedule(),pregame_serving_eligible=False)
    records=[r for week in(1,2,3)for r in(start(week),snap(week))]
    centers=build_first_snap_centers(participation,records,schedule_source,before_period=202607,event_source_sha256='a'*64)
    events=[]
    for week in(1,2,3):
        for number in(100,101):events.append(dict(game_id=gid(week),play_id=str(number),offense='BUF',defense='MIA',eligible_nonspike_dropback=True,source_sack=week==2 and number==100))
    coverage=dict(version=COVERAGE_VERSION,season=2023,before_period=202607,team_game_rows=[dict(game_id=gid(w),team=t)for w in(1,2,3)for t in('BUF','MIA')],event_basis=events,pregame_serving_eligible=False,
        semantic_sha256='coverage',provenance=dict(participation_semantic_sha256=participation['semantic_sha256'],original_PBP_manifest=dict(sha256='a'*64)))
    return participation,records,schedule_source,centers,coverage


def build(centers=None,coverage=None,alias_rows=None):
    _,_,_,c,v=fixture();c=centers or c;v=coverage or v
    return build_center_sack_response([c],[v],aliases()if alias_rows is None else alias_rows,cutoff=NOW,identity_universe={native(n)for n in(1,2,3,4,5,22)})


def profile(out):return next(p for p in out['profiles']if p['team']=='BUF')
def unit(c,week):return next(u for u in c['units']if u['game_id']==gid(week)and u['team']=='BUF')


def test_independent_first_center_proof_pooled_matched_sack_response():
    out=build();p=profile(out)
    assert p['cells']['same']['exact_dropbacks']==2 and p['cells']['changed']['exact_sacks']==1
    assert p['same_minus_changed_sack_rate']==-.5
    first=next(r for r in out['game_rows']if r['team']=='BUF'and r['game_id']==gid(1))
    assert first['comparison_applicable']is False and first['center_class']is None
    assert out['pregame_serving_eligible']is False and out['forecast']is None


def test_one_center_with_nonstandard_five_line_shape_independently_qualified():
    p,r,s,_,_=fixture();source_row=p['rows'][0];positions=source_row['participant_scopes']['offense']['position_by_native_id']
    positions[native(2)]='T' # C1/G1/T3 is not C1/G2/T2, but oneC still source-proven.
    c=build_first_snap_centers(p,r,s,before_period=202607,event_source_sha256='a'*64);u=unit(c,1)
    assert u['source_proven_center']is True
    assert u['proof']['full_CGT_native_count_match']is False
    assert u['proof']['eleven_unique_aligned_positions']is True and u['proof']['no_earlier_possible_offense']is True
    assert u['proof']['source_center_candidates']==[native(1)]


@pytest.mark.parametrize('change',[dict(no_play=None),dict(play_type='no_play',play_type_nfl='PENALTY',pass_attempt=0),dict(order_sequence=None),dict(posteam=None)])
def test_earlier_possible_native_snap_cannot_be_qualified_by_role_shape(change):
    p,r,s,_,_=fixture();r.append(snap(1,number=30,order=1.5,**change))
    c=build_first_snap_centers(p,r,s,before_period=202607,event_source_sha256='a'*64)
    assert unit(c,1)['source_proven_center']is False


def test_missing_beginning_first_participation_or_aligned_positions_unknown():
    for mode in('start','participation','positions'):
        p,r,s,_,_=fixture()
        if mode=='start':r=[x for x in r if not(x['week']==1 and x['play_type_nfl']=='GAME_START')]
        elif mode=='participation':p['rows']=[x for x in p['rows']if x['week']!=1]
        else:p['rows'][0]['participant_scopes']['offense']['position_by_native_id']=None
        assert unit(build_first_snap_centers(p,r,s,before_period=202607,event_source_sha256='a'*64),1)['source_proven_center']is False


def test_two_centers_unknown_position_or_duplicate_native_players_not_oneC():
    for mode in('twoC','unknown','duplicate'):
        p,r,s,_,_=fixture();scope=p['rows'][0]['participant_scopes']['offense']
        if mode=='twoC':scope['position_by_native_id'][native(2)]='C'
        elif mode=='unknown':scope['position_by_native_id'][native(2)]='UNKNOWN'
        else:scope['native_player_ids'][-1]=native(1)
        assert unit(build_first_snap_centers(p,r,s,before_period=202607,event_source_sha256='a'*64),1)['source_proven_center']is False


def test_missing_intervening_center_never_skipped_and_masks_full_cells():
    p,r,s,c,v=fixture();unit(c,2).update(source_center_id=None,source_proven_center=False,unknown_reason='missing')
    out=build(c,v);row=next(x for x in out['game_rows']if x['team']=='BUF'and x['game_id']==gid(3))
    assert row['previous_same_season_game_id']==gid(2)and row['center_class']is None
    assert profile(out)['unknown_center_class_games']==2
    assert profile(out)['cells']['same']['rate']is None


def test_unknown_class_masks_measured_cell_but_preserves_known_sample():
    _,_,_,c,v=fixture();unit(c,1).update(source_center_id=None,source_proven_center=False)
    out=build(c,v);cell=profile(out)['cells']['same']
    assert cell['known_dropbacks']==2 and cell['known_outcome_sample_rate']==0
    assert cell['exact_dropbacks']is None and cell['rate']is None


def test_missing_sack_outcome_does_not_become_zero_or_other_group_exposure():
    _,_,_,c,v=fixture();v['event_basis'][-1]['source_sack']=None
    out=build(c,v);p=profile(out)
    assert p['cells']['same']['exact_dropbacks']==2 and p['cells']['same']['exact_sacks']is None
    assert p['same_minus_changed_sack_rate']is None and p['cells']['changed']['rate']==.5


def test_unknown_native_dropback_side_masks_candidate_response():
    _,_,_,c,v=fixture();v['event_basis'][-1]['offense']=None
    assert profile(build(c,v))['same_minus_changed_sack_rate']is None


def test_global_native_canonical_collision_withholds_across_all_periods():
    a=aliases();a[-1]['player_master_id']=a[0]['player_master_id']
    out=build(alias_rows=a)
    assert out['native_identity_receipts'][native(1)]['player_master_id']is None
    assert out['native_identity_receipts'][native(22)]['player_master_id']is None
    assert profile(out)['same_minus_changed_sack_rate']is None
    assert out['identity_review_requests']


def test_future_alias_and_master_proof_excluded_native_class_separate():
    a=aliases();a[-1]['created_at']='2099-01-01T00:00:00Z'
    out=build(alias_rows=a);p=profile(out)
    assert p['same_minus_changed_sack_rate']==-.5 # native proof remains explicit; no canonical attachment invented.
    rows=[r for r in out['game_rows']if r['team']=='BUF'and r['game_id']!=gid(1)]
    assert all(r['canonical_pair_qualified']is False for r in rows)
    assert any(r['source_player_id']==native(22)for r in out['identity_review_requests'])


def test_native_game_source_pair_and_future_cutoff_guards():
    _,_,_,c,v=fixture();v['provenance']['original_PBP_manifest']['sha256']='b'*64
    with pytest.raises(ValueError,match='event source'):build(c,v)
    _,_,_,c,v=fixture();v['event_basis'].append(deepcopy(v['event_basis'][0]))
    with pytest.raises(ValueError,match='Duplicate native dropback'):build(c,v)
    with pytest.raises(ValueError,match='nonfuture'):build_center_sack_response([c],[v],[],cutoff=datetime.now(UTC)+timedelta(days=1),identity_universe={native(1),native(22)})


def test_missing_coverage_game_not_zero_and_duplicate_source_side_rejected():
    _,_,_,c,v=fixture();v['team_game_rows']=[r for r in v['team_game_rows']if not(r['game_id']==gid(2)and r['team']=='MIA')]
    v['event_basis']=[r for r in v['event_basis']if r['game_id']!=gid(2)]
    out=build(c,v);cell=profile(out)['cells']['changed']
    assert cell['missing_source_games']==1 and cell['exact_dropbacks']is None and cell['exact_sacks']is None
    _,_,_,c,v=fixture();v['team_game_rows'].append(deepcopy(v['team_game_rows'][0]))
    with pytest.raises(ValueError,match='Duplicate coverage'):build(c,v)


def test_duplicate_or_missing_possible_native_order_not_numeric_play_sort():
    p,r,s,_,_=fixture();r.append(snap(1,number=20,order=2))
    c=build_first_snap_centers(p,r,s,before_period=202607,event_source_sha256='a'*64)
    assert unit(c,1)['source_proven_center']is False


def test_identity_incidents_use_existing_append_only_review_not_alias_repairs():
    from backend.app.product_services.center_sack_response import persist_center_identity_requests
    calls=[]
    class Connection:
        def execute(self,sql,params):calls.append((str(sql),params))
    out=build(alias_rows=[])
    result=persist_center_identity_requests(Connection(),out,source_refs=[])
    assert result['requests']==2
    assert all('ON CONFLICT (source_schema,source_table,source_record_key) DO NOTHING'in sql for sql,p in calls)
    assert all('UPDATE 'not in sql and 'display_name' in sql and p['native'].startswith('00-')for sql,p in calls)
    assert all(p['table']=='source_snapshot'for sql,p in calls)


def test_prior_receipt_id_is_bound_from_exact_companion_not_absent_durable_field():
    import importlib.util
    from pathlib import Path
    path=Path('research/center_sack_response_20261020/v1/identity_receipt.py')
    spec=importlib.util.spec_from_file_location('center_identity_receipt',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    old=dict(source_table='player_alias',source_record_key='key',status='open',first_seen_at='clock1',updated_at='clock2')
    companion=dict(source_table='player_alias',source_record_key='key',identity_quarantine_id='durable-id')
    current={**old,'identity_quarantine_id':'durable-id'}
    prior=dict(durable_readback_records=[old],records=[companion])
    result=module.compare_existing_cases([current],prior)
    assert result['unchanged_existing_cases']==1
    assert result['existing_case_comparison_evidence'][0]['prior_durable_id_field_present']is False
    assert module.compare_existing_cases([{**current,'identity_quarantine_id':'other'}],prior)['unchanged_existing_cases']==0
    assert module.compare_existing_cases([{**current,'updated_at':'changed'}],prior)['unchanged_existing_cases']==0
    assert module.compare_existing_cases([current],{**prior,'records':[]})['unchanged_existing_cases']==0
