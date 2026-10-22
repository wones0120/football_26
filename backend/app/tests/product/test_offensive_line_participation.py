from copy import deepcopy
from datetime import datetime,UTC,timedelta
from uuid import UUID
import pytest
from backend.app.product_services.offensive_line_participation import build_offensive_line_continuity,resolve_line_identity,persist_line_identity_requests
from backend.app.product_services.participation_source_components import normalize_participation_rows
from backend.app.tests.product.test_fumble_event_components import play
NOW=datetime(2026,10,20,6,tzinfo=UTC)

def native(n):return f'00-{n:07d}'
def gid(week):return f'2023_{week:02d}_BUF_MIA'
def schedule(weeks=(1,2,3)):
    return [dict(game_id=gid(w),season=2023,week=w,game_type='REG',home_team='MIA',away_team='BUF',game_date=f'2023-09-{w:02d}')for w in weeks]
def snap(w,number=100,order=2,**kw):return play(number,game_id=gid(w),season=2023,week=w,order_sequence=order)|kw
def start(w):return snap(w,900,1,posteam=None,defteam=None,play_type=None,play_type_nfl='GAME_START',pass_attempt=0,qb_dropback=0)
def source(w,replace=None,number=100,**kw):
    ids=[native(n)for n in range(1,12)]
    if replace:ids[replace[0]]=native(replace[1])
    return dict(nflverse_game_id=gid(w),play_id=number,possession_team='BUF',offense_players=ids,offense_positions=['C','G','G','T','T','QB','WR','WR','RB','TE','FB'],n_offense=11)|kw

def aliases(numbers=(1,2,3,4,5,22)):
    return [dict(alias_id=n,source_system='nflreadpy',source_key=native(n),player_master_id=str(UUID(int=n)),created_at=(NOW-timedelta(days=1)).isoformat(),player_master_created_at=(NOW-timedelta(days=2)).isoformat())for n in numbers]
def build(pbp=None,parts=None,expected=None,a=None):
    p=pbp if pbp is not None else [r for w in (1,2,3)for r in (start(w),snap(w))]
    parts=parts if parts is not None else [source(1),source(2,replace=(1,22)),source(3)]
    block=normalize_participation_rows(parts,season=2023);a=aliases()if a is None else a
    return build_offensive_line_continuity(block,p,expected or schedule(),a,before_period=202607,cutoff=NOW,identity_universe={r['source_key']for r in a}|{native(n)for n in (1,2,3,4,5,22)})
def line(r,week):return next(x for x in r['starting_units']if x['team']=='BUF'and x['game_id']==gid(week))
def contrast(r,week):return next(x for x in r['continuity_rows']if x['team']=='BUF'and x['game_id']==gid(week))

def test_first_native_snap_and_declared_role_family_index_not_left_right():
    r=build()
    assert line(r,1)['first_physical_play_id']=='100'
    assert line(r,1)['source_proven_starting_unit']is True
    assert contrast(r,1)['value']is None
    assert contrast(r,2)['value']==.8 and contrast(r,2)['canonical_qualified_value']==.8
    assert r['pregame_serving_eligible']is False and r['forecast']is None

def test_native_order_not_numeric_play_id_or_source_row_order():
    p=[start(1),snap(1),snap(1,20,3)]
    r=build(pbp=p[::-1],parts=[source(1),source(1,number=20,replace=(1,22))])
    assert line(r,1)['first_physical_play_id']=='100'

def test_missing_start_marker_cannot_be_promoted_from_earliest_observed_snap():
    r=build(pbp=[snap(1)])
    assert line(r,1)['source_proven_starting_unit']is False
    assert 'beginning'in line(r,1)['unknown_reason']

@pytest.mark.parametrize('change',[dict(no_play=None),dict(order_sequence=None),dict(posteam=None)])
def test_possible_earlier_or_unordered_offense_masks_first_snap(change):
    p=[start(1),snap(1,50,1.5,**change),snap(1)]
    r=build(pbp=p)
    assert line(r,1)['source_proven_starting_unit']is False

def test_duplicate_native_order_is_not_arbitrarily_chosen():
    r=build(pbp=[start(1),snap(1),snap(1,20,2)])
    assert line(r,1)['source_proven_starting_unit']is False

def test_missing_first_participation_not_skipped_to_later_known_unit():
    r=build(pbp=[start(1),snap(1),snap(1,20,3)],parts=[source(1,number=20)])
    assert line(r,1)['source_proven_starting_unit']is False
    assert line(r,1)['first_physical_play_id']=='100'

def test_jumbo_six_ol_or_missing_positions_cannot_select_five():
    s=source(1);s['offense_positions'][-1]='T'
    r=build(parts=[s]);assert line(r,1)['source_proven_starting_unit']is False
    s=source(1);s['offense_positions']=None
    assert line(build(parts=[s]),1)['source_proven_starting_unit']is False

def test_unknown_middle_scheduled_game_is_not_skipped_for_previous_known_unit():
    r=build(pbp=[start(1),snap(1),start(3),snap(3)],parts=[source(1),source(3)])
    assert contrast(r,3)['previous_same_season_game_id']==gid(2)
    assert contrast(r,3)['value']is None

def test_unresolved_alias_keeps_native_measure_separate_and_requests_review():
    a=[r for r in aliases()if r['source_key']!=native(4)]
    r=build(a=a)
    assert contrast(r,2)['value']==.8 and contrast(r,2)['canonical_qualified_value']is None
    assert any(q['source_player_id']==native(4)for q in r['identity_review_requests'])

def test_future_alias_never_attaches_to_unit_or_resolves_canonical_coverage():
    a=aliases();a[3]['created_at']=(NOW+timedelta(hours=1)).isoformat();r=build(a=a)
    assert line(r,1)['native_line_members'][3]['player_master_id']is None
    assert len(r['future_alias_evidence_excluded'])==1

def test_canonical_collision_with_other_season_native_universe_masks_entire_batch():
    a=aliases();a[-1]['player_master_id']=a[0]['player_master_id'];r=build(a=a)
    assert r['native_identity_receipts'][native(1)]['status']=='canonical_native_conflict'
    assert contrast(r,2)['value']is None and contrast(r,3)['value']is None

def test_same_source_identity_with_multiple_alias_candidates_is_not_first_chosen():
    a=aliases();a.append({**a[0],'alias_id':99,'player_master_id':str(UUID(int=99))})
    proof,_=resolve_line_identity({r['source_key']for r in a},a,cutoff=NOW)
    assert proof[native(1)]['player_master_id']is None

def test_unknown_game_dates_masks_chronology_not_week_fallback():
    s=schedule();s[1]['game_date']=None;r=build(expected=s)
    assert all(x['value']is None for x in r['continuity_rows']if x['team']=='BUF')

def test_append_only_identity_requests_are_bound_and_never_update_resolved_records():
    r=build(a=[]);seen=[]
    class Connection:
        def execute(self,sql,params):seen.append((str(sql),params))
    out=persist_line_identity_requests(Connection(),[r],source_refs=[{'snapshot_id':'source'}])
    assert out['requests']==6
    assert all('ON CONFLICT'in sql and 'DO NOTHING'in sql and 'UPDATE 'not in sql for sql,_ in seen)
    assert all(p['native'].startswith('00-')for _,p in seen)


def test_native_units_can_bind_one_global_alias_receipt_without_second_source_load():
    from backend.app.product_services.offensive_line_participation import reattach_line_identities
    expected=build();universe={native(n)for n in (1,2,3,4,5,22)}
    rebound=reattach_line_identities(build(a=[]),aliases(),cutoff=NOW,identity_universe=universe)
    assert rebound['semantic_sha256']==expected['semantic_sha256']


def test_future_canonical_entity_receipt_never_attaches_even_when_alias_is_old():
    a=aliases();a[0]['player_master_created_at']=(NOW+timedelta(hours=1)).isoformat()
    proof,future=resolve_line_identity({r['source_key']for r in a},a,cutoff=NOW)
    assert proof[native(1)]['player_master_id']is None and len(future)==1


def test_earlier_nullified_penalty_might_have_been_physical_snap_not_skipped():
    p=[start(1),snap(1,50,1.5,play_type='no_play',play_type_nfl='PENALTY',pass_attempt=0,qb_dropback=0),snap(1)]
    assert line(build(pbp=p),1)['source_proven_starting_unit']is False


def test_known_quiet_timeout_before_first_snap_does_not_invent_offensive_unit():
    p=[start(1),snap(1,50,1.5,play_type='no_play',play_type_nfl='TIMEOUT',pass_attempt=0,qb_dropback=0),snap(1)]
    assert line(build(pbp=p),1)['source_proven_starting_unit']is True
