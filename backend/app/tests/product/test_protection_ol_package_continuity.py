from copy import deepcopy
from uuid import UUID
import pytest
from backend.app.product_services.personnel_package_continuity import build_personnel_package_continuity,PHYSICAL_VERSION
from backend.app.product_services.participation_source_components import VERSION
from backend.app.product_services.protection_ol_package_continuity import build_protection_ol_continuity,_unit


def fixture():
    games=[dict(game_id=f'2025_{w:02d}_SF_LA',season=2025,week=w,game_type='REG',game_date=f'2025-09-{w*7:02d}',home_team='LAR',away_team='SF') for w in (1,2,3)]
    roles=['C','G','G','T','T','QB','RB','WR','WR','WR','TE'];ids=[f'00-{i:07d}' for i in range(1,13)]
    identity={n:dict(status='unique_native_alias',player_master_id=str(UUID(int=i+1)),original_alias_evidence=[]) for i,n in enumerate(ids)}
    rows=[];sources=[]
    for g in games:
        for play in ('1','2'):
            rows.append(dict(game_id=g['game_id'],play_id=play,season=2025,week=g['week'],season_type='REG',posteam='SF',defteam='LAR',play_type='pass',play_type_nfl='PASS',no_play=0,two_point_attempt=0,pass_attempt=1,rush_attempt=0,sack=0,qb_scramble=0,qb_spike=0,qb_kneel=0,qb_dropback=1))
            mapping=dict(zip(ids[:11],roles))
            sources.append(dict(game_id=g['game_id'],play_id=play,season=2025,week=g['week'],native_phase=None,possession_team='SF',participant_scopes=dict(offense=dict(status='aligned_native_position_list',native_player_ids=list(mapping),position_by_native_id=mapping))))
    return dict(version=VERSION,season=2025,pregame_serving_eligible=False,rows=sources),rows,games,identity


def run(args):
    part,raw,games,identity=args
    p=build_personnel_package_continuity(part,raw,games,identity,before_period=202519)
    physical=dict(version=PHYSICAL_VERSION,season=2025,pregame_serving_eligible=False,rows=raw)
    return build_protection_ol_continuity(p,physical,identity)


def sf(block):return [r for r in block['continuity_rows'] if r['team']=='SF']


def replace(source,old='00-0000002',new='00-0000012'):
    scope=source['participant_scopes']['offense'];role=scope['position_by_native_id'].pop(old);scope['position_by_native_id'][new]=role;scope['native_player_ids']=list(scope['position_by_native_id'])


def test_retained_firstgame_na_and_no_complete_log_claim():
    b=run(fixture());rows=sf(b)
    assert rows[0]['first_game_not_applicable'] and rows[0]['catalog_value'] is None
    assert rows[1]['catalog_value']==rows[2]['catalog_value']==1
    assert b['pregame_serving_eligible'] is False


def test_weight_by_DB_snaps_not_unique_OL_units():
    a=fixture();replace(a[0]['rows'][3])
    for play in ('3','4'):
        r=deepcopy(a[1][3]);r['play_id']=play;a[1].append(r)
        p=deepcopy(a[0]['rows'][3]);p['play_id']=play;a[0]['rows'].append(p)
    r=sf(run(a))[1]
    assert r['catalog_value']==.25 and r['canonical']['known_nonretained_snaps']==3


def test_literal_nonstandard_five_tuple_allowed_not_alignment_inferred():
    a=fixture()
    for p in a[0]['rows']:p['participant_scopes']['offense']['position_by_native_id']['00-0000003']='T'
    b=run(a);assert sf(b)[1]['catalog_value']==1
    assert next(iter(b['unit_registry'].values()))['role_count_tuple']==[('C',1),('G',1),('T',3)]


def test_only_same_tuple_compared():
    a=fixture()
    for p in a[0]['rows']:
        if p['week']==2:p['participant_scopes']['offense']['position_by_native_id']['00-0000003']='T'
    r=sf(run(a))[1];assert r['catalog_value'] is None and r['canonical']['known_noncomparable_snaps']==2


@pytest.mark.parametrize('position',['T','WR'])
def test_six_or_four_OL_remains_unknown(position):
    a=fixture();a[0]['rows'][2]['participant_scopes']['offense']['position_by_native_id']['00-0000011' if position=='T' else '00-0000003']=position
    assert sf(run(a))[1]['catalog_value'] is None


def test_prior_unknown_allows_positive_match_but_not_negative():
    a=fixture();a[0]['rows'].pop(1)
    assert sf(run(a))[1]['catalog_value']==1
    for p in a[0]['rows']:
        if p['week']==2:replace(p)
    assert sf(run(a))[1]['catalog_value'] is None


def test_current_missing_unit_masks_exact_keeps_sample():
    a=fixture();a[0]['rows'].pop(3)
    r=sf(run(a))[1];assert r['catalog_value'] is None and r['canonical']['known_classified_sample_fraction']==1


def test_missing_prior_log_never_skips_to_older_known_game():
    a=fixture();a[1][:]=[r for r in a[1] if r['week']!=2];a[0]['rows'][:]=[r for r in a[0]['rows'] if r['week']!=2]
    r=sf(run(a))[2];assert r['prior_scheduled_game_id']=='2025_02_SF_LA' and r['catalog_value'] is None


def test_non_OL_identity_does_not_mask_qualified_OL():
    a=fixture();a[3]['00-0000010']['status']='missing_frozen_attachment';a[3]['00-0000010']['player_master_id']=None
    assert sf(run(a))[1]['catalog_value']==1


def test_OL_conflict_retains_native_variant_and_withholds_canonical():
    a=fixture();a[3]['00-0000002']['status']='missing_frozen_attachment';a[3]['00-0000002']['player_master_id']=None
    r=sf(run(a))[1];assert r['catalog_value'] is None and r['native_variant']['value']==1


def test_all_edge_collision_including_ambiguous_key_withholds_unique_neighbor():
    a=fixture();pid=a[3]['00-0000002']['player_master_id']
    a[3]['00-0000012']['original_alias_evidence']=[dict(player_master_id=pid),dict(player_master_id=str(UUID(int=99)))]
    b=run(a);assert '00-0000002' in b['global_identity_withheld_native_ids'] and sf(b)[1]['catalog_value'] is None


@pytest.mark.parametrize('kind',['spike','kneel','run','excluded'])
def test_non_DB_exclusions_not_in_denominator(kind):
    a=fixture();r=a[1][2]
    if kind=='spike':r.update(qb_spike=1,play_type='qb_spike')
    if kind in ('kneel','run'):r.update(pass_attempt=0,rush_attempt=1,qb_dropback=0,play_type='run',play_type_nfl='RUSH',qb_kneel=int(kind=='kneel'))
    if kind=='excluded':r['no_play']=1
    assert sf(run(a))[1]['canonical']['known_comparable_snaps']==1


def test_sack_union_once_and_official_scramble_once():
    a=fixture();a[1][2].update(sack=1,play_type_nfl='SACK');a[1][3].update(pass_attempt=0,rush_attempt=1,qb_scramble=1,play_type='run',play_type_nfl='RUSH')
    assert sf(run(a))[1]['canonical']['known_comparable_snaps']==2


@pytest.mark.parametrize('field',['pass_touchdown','rush_touchdown','first_down_pass','first_down_rush','qb_dropback'])
def test_positive_control_unknown_not_ignored(field):
    a=fixture();a[1][2].update(pass_attempt=0,rush_attempt=0,sack=0,qb_dropback=0,play_type=None,play_type_nfl='TIMEOUT');a[1][2][field]=1
    r=sf(run(a))[1];assert r['catalog_value'] is None and r['canonical']['known_comparable_snaps']==1


def test_unknown_side_masks_both_scheduled_sides():
    a=fixture();a[1][2]['posteam']=None
    b=run(a);assert sf(b)[1]['catalog_value'] is None
    assert all(r['unknown_physical_or_side']==1 for r in b['game_rows'] if r['week']==2)


def test_source_only_row_remains_possible_DB():
    a=fixture();a[1].pop(3)
    assert sf(run(a))[1]['catalog_value'] is None


def test_unknown_position_cannot_leave_qualified_five():
    unit=dict(native_participant_roles=[(f'00-{i:07d}',role) for i,role in enumerate(['C','G','G','T','T','QB','RB','WR','WR','WR',None])])
    assert _unit(unit,{}) is None
