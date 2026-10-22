from copy import deepcopy
from datetime import timedelta
import pytest
from backend.app.product_services.guard_interior_response import build_guard_interior_response,_interior
from backend.app.product_services.center_sack_response import build_first_snap_centers
from backend.app.product_services.participation_source_components import normalize_participation_rows
from backend.app.product_services.schedule_context_features import VERSION as SCHEDULE_VERSION
from backend.app.product_services.defensive_front_rush_exposure import VERSION as RUSH_VERSION
from backend.app.tests.product.test_offensive_line_participation import source,start,snap,schedule,aliases,native,gid,NOW


def fixture():
    raw=[source(1),source(2,replace=(1,22)),source(3,replace=(1,22))]
    part=normalize_participation_rows(raw,season=2023)
    first=build_first_snap_centers(part,[r for w in(1,2,3)for r in(start(w),snap(w))],dict(version=SCHEDULE_VERSION,game_rows=schedule(),pregame_serving_eligible=False),before_period=202607,event_source_sha256='a'*64)
    rush=dict(version=RUSH_VERSION,season=2023,before_period=202607,pregame_serving_eligible=False,team_game_rows=[dict(game_id=gid(w),offense=t)for w in(1,2,3)for t in('BUF','MIA')],
        provenance=dict(participation_semantic_sha256=part['semantic_sha256'],original_PBP_manifest=dict(sha256='a'*64)),
        event_basis=[dict(game_id=gid(w),play_id='100',offense='BUF',defense='MIA',eligible=True,original_run_location='middle',original_run_gap=None,rushing_yards=2 if w==2 else 6,epa=-1 if w==2 else 2)for w in(1,2,3)])
    return first,rush,part


def build(f=None,r=None,p=None,a=None):
    x,y,z=fixture();return build_guard_interior_response([f or x],[r or y],[p or z],aliases((1,2,3,4,5,22))if a is None else a,cutoff=NOW,identity_universe={native(n)for n in(1,2,3,4,5,22)})
def row(out,week):return next(x for x in out['game_rows']if x['game_id']==gid(week)and x['team']=='BUF')
def profile(out):return next(x for x in out['profiles']if x['team']=='BUF')


def test_unordered_guard_pair_native_overlap_and_matched_signed_response():
    out=build();a=profile(out)
    assert row(out,1)['comparison_applicable']is False
    assert row(out,2)['continuity_index']==.5 and row(out,2)['guard_class']=='changed'
    assert row(out,3)['continuity_index']==1 and row(out,3)['guard_class']=='same'
    assert a['same_minus_changed_yards']==4 and a['same_minus_changed_EPA']==3
    assert row(out,2)['interior_response']['EPA_per_interior_rush']==-1
    assert out['pregame_serving_eligible']is False and out['forecast']is None


@pytest.mark.parametrize('location,gap,expected',[('middle',None,True),('left','guard',True),('right','guard',True),('middle','tackle',True),('left','end',False),('right','tackle',False),('left',None,None),(None,'end',None),(None,'guard',True),('unknown','bad',None)])
def test_native_interior_union_three_state_without_invented_axis_conflicts(location,gap,expected):
    assert _interior(dict(original_run_location=location,original_run_gap=gap))is expected


def test_independent_two_guards_not_center_success_or_failure_string():
    f,r,p=fixture()
    for u in f['units']:
        if u['team']=='BUF':
            u['source_proven_center']=False;u['unknown_reason']='Exactly one source-reported C not proven'
            u['proof']['original_first_snap_position_by_native_id'][native(1)]='T'
    for source_row in p['rows']:source_row['participant_scopes']['offense']['position_by_native_id'][native(1)]='T'
    out=build(f,r,p)
    assert row(out,2)['guard_class']=='changed'and row(out,3)['guard_class']=='same'
    assert all(u['source_proven_guard_pair']for u in out['starting_guard_units']if u['team']=='BUF')
    f,r,p=fixture();f['units'][0]['unknown_reason']='Exactly one source-reported C not proven';f['units'][0]['proof']['no_earlier_possible_offense']=False
    out=build(f,r,p);assert row(out,2)['guard_class']is None


@pytest.mark.parametrize('mode',['start','earlier','order','eleven','join','phase','extraG'])
def test_firstsnap_boundary_participant_join_and_exactG2_are_all_required(mode):
    f,r,p=fixture();u=next(u for u in f['units']if u['game_id']==gid(2)and u['team']=='BUF');proof=u['proof'];part=p['rows'][1]
    if mode=='start':proof['unique_quiet_native_GAME_START']=False
    elif mode=='earlier':proof['earlier_possible_play_ids']=['42']
    elif mode=='order':proof['first_physical_native_order']='NaN'
    elif mode=='eleven':proof['eleven_unique_aligned_positions']=False
    elif mode=='join':part['possession_team']='MIA'
    elif mode=='phase':part['native_phase']='POST'
    else:
        proof['original_first_snap_position_by_native_id'][native(4)]='G'
        part['participant_scopes']['offense']['position_by_native_id'][native(4)]='G'
    out=build(f,r,p);assert row(out,2)['guard_class']is None and row(out,3)['guard_class']is None
    assert profile(out)['same_minus_changed_EPA']is None


def test_middle_scheduled_unknown_guard_pair_not_skipped():
    f,r,p=fixture();p['rows']=[x for x in p['rows']if x['week']!=2]
    out=build(f,r,p)
    assert row(out,3)['previous_scheduled_game_id']==gid(2)and row(out,3)['continuity_index']is None


def test_unknown_interior_exposure_and_outcome_masks_remain_separate():
    f,r,p=fixture();r['event_basis'][1]['original_run_location']='left';r['event_basis'][1]['original_run_gap']=None
    out=build(f,r,p);assert row(out,2)['interior_response']['exact_interior_rushes']is None
    assert profile(out)['same_minus_changed_yards']is None
    f,r,p=fixture();r['event_basis'][1]['epa']=None
    out=build(f,r,p);assert profile(out)['same_minus_changed_yards']==4 and profile(out)['same_minus_changed_EPA']is None


def test_zero_exposure_undefined_and_known_outside_excludes_unknown_flags():
    f,r,p=fixture();r['event_basis'][1].update(original_run_location='left',original_run_gap='end',eligible=None)
    out=build(f,r,p);c=row(out,2)['interior_response']
    assert c['exact_interior_rushes']==0 and c['EPA_per_interior_rush']is None


def test_global_alias_conflict_withholds_pair_class_all_periods_future_ignored():
    a=aliases((1,2,3,4,5,22));a[-1]['player_master_id']=a[1]['player_master_id'];out=build(a=a)
    assert row(out,2)['guard_class']is None and row(out,3)['guard_class']is None
    assert {q['source_player_id']for q in out['identity_review_requests']}=={native(2),native(22)}
    a=aliases((1,2,3,4,5,22));a[1]['created_at']=(NOW+timedelta(days=1)).isoformat();out=build(a=a)
    assert len(out['future_alias_evidence_excluded'])==1
    assert row(out,2)['guard_class']=='changed'and row(out,2)['canonical_qualified']is False


def test_prior_response_window_does_not_include_current_game_outcome():
    out=build();w=next(x for x in out['prior_windows']if x['team']=='BUF'and x['game_id']==gid(3))
    assert w['max_contributing_period']==202302 and w['target_period']==202303
    assert w['cells']['changed']['EPA_per_interior_rush']==-1 and w['cells']['same']['EPA_per_interior_rush']is None


def test_native_source_hash_duplicate_and_universe_contracts():
    f,r,p=fixture();r['provenance']['original_PBP_manifest']['sha256']='b'*64
    with pytest.raises(ValueError,match='PBP'):build(f,r,p)
    f,r,p=fixture();r['event_basis'].append(deepcopy(r['event_basis'][0]))
    with pytest.raises(ValueError,match='Duplicate native rushing'):build(f,r,p)
    f,r,p=fixture();f['units'].append(deepcopy(f['units'][0]))
    with pytest.raises(ValueError,match='Duplicate firstsnap'):build(f,r,p)


def test_append_only_native_guard_incidents_never_reopen_or_repair_aliases():
    from backend.app.product_services.guard_interior_response import persist_guard_identity_requests
    calls=[]
    class Connection:
        def execute(self,sql,params):calls.append((str(sql),params))
    out=build(a=[]);r=persist_guard_identity_requests(Connection(),out,source_refs=[])
    assert r['requests']>0
    assert all('ON CONFLICT (source_schema,source_table,source_record_key) DO NOTHING'in sql and 'UPDATE 'not in sql for sql,p in calls)
    assert all(p['table']=='source_snapshot'and p['native'].startswith('00-')for sql,p in calls)
