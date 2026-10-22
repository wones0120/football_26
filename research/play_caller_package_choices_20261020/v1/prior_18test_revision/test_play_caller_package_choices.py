from copy import deepcopy
from uuid import UUID
import pytest
from backend.app.product_services.personnel_package_continuity import build_personnel_package_continuity,PHYSICAL_VERSION
from backend.app.product_services.participation_source_components import VERSION
from backend.app.product_services.documented_playcaller_change import VERSION as CALLER_VERSION
from backend.app.product_services.play_caller_package_choices import build_play_caller_package_choices as build


def fixture():
    games=[dict(game_id=f'2023_{w:02d}_SF_LA',season=2023,week=w,game_type='REG',game_date=f'2023-09-{w*7:02d}',home_team='LAR',away_team='SF') for w in (1,2,3)]
    ids=[f'00-{i:07d}' for i in range(1,12)];roles=['C','G','G','T','T','QB','RB','WR','WR','WR','TE']
    identity={n:dict(status='unique_native_alias',player_master_id=str(UUID(int=i+1)),original_alias_evidence=[]) for i,n in enumerate(ids)}
    part=[];raw=[]
    for g in games:
        for play in (1,2):
            raw.append(dict(game_id=g['game_id'],play_id=play,season=2023,week=g['week'],season_type='REG',posteam='SF',defteam='LAR',play_type='pass',play_type_nfl='PASS',no_play=0,two_point_attempt=0,pass_attempt=1,rush_attempt=0,sack=0,qb_scramble=0,qb_spike=0,qb_kneel=0,qb_dropback=1))
            mapping=dict(zip(ids,roles));part.append(dict(game_id=g['game_id'],play_id=str(play),season=2023,week=g['week'],native_phase=None,possession_team='SF',participant_scopes=dict(offense=dict(status='aligned_native_position_list',native_player_ids=ids,position_by_native_id=mapping))))
    source=dict(version=VERSION,season=2023,pregame_serving_eligible=False,rows=part)
    transition=dict(version=CALLER_VERSION,team_id='SF',measured_effective_game_id=games[2]['game_id'],incoming_first_calling_game_source_proven=True,outgoing_playcalling_duties_ended_before_this_game=True,source_incoming_person='Documented caller',source_outgoing_person='Released caller',semantic_sha256='frozen caller evidence',pregame_serving_eligible=False)
    return source,raw,games,identity,transition


def run(a):
    part,raw,games,identity,transition=a
    p=build_personnel_package_continuity(part,raw,games,identity,before_period=202319)
    physical=dict(version=PHYSICAL_VERSION,season=2023,pregame_serving_eligible=False,rows=raw)
    return build(transition,p,physical)


def rush(row):row.update(pass_attempt=0,rush_attempt=1,play_type='run',play_type_nfl='RUSH',qb_dropback=0)


def test_joint_same_snap_not_separate_marginals_and_immediate_prior():
    a=fixture();rush(a[1][3]);b=run(a)
    assert b['prior_scheduled_game_id']=='2023_02_SF_LA' and b['prior_game_actual_playcaller'] is None
    assert b['comparisons'][0]['within_package_pass_call_fraction_difference']==.5
    assert len(b['event_basis'])==4 and len(b['games'])==2


def test_package_union_preserves_new_and_known_absent_states():
    a=fixture();a[0]['rows'][4]['participant_scopes']['offense']['position_by_native_id']['00-0000008']='TE'
    b=run(a);assert len(b['comparisons'])==2
    new=[r for r in b['games'][0]['packages'] if r['known_physical_snaps']==0][0]
    assert new['exact_physical_snaps']==0 and new['package_use_fraction']==0 and new['pass_call_fraction'] is None
    assert sum(r['known_physical_snaps'] for r in b['games'][1]['packages'])==2


def test_native_team_counts_do_not_assert_unknown_canonical_members():
    a=fixture();a[3]['00-0000002'].update(status='missing_frozen_attachment',player_master_id=None)
    b=run(a);assert b['games'][0]['canonical_member_unknown_snaps']==2
    assert b['comparisons'][0]['within_package_pass_call_fraction_difference']==0
    assert all(not e['canonical_member_set_known'] for e in b['event_basis'])


def test_unknown_package_masks_all_compatible_full_cells_keeps_known_samples():
    a=fixture();a[0]['rows'].pop(5)
    b=run(a);g=b['games'][1]
    assert g['unknown_package_snaps']==1 and not g['full_native_package_cohort_known']
    assert g['packages'][0]['package_use_fraction'] is None and g['packages'][0]['known_package_use_sample_fraction']==.5
    assert b['comparisons'][0]['within_package_pass_call_fraction_difference'] is None


def test_unknown_call_masks_matching_conditional_not_package_membership():
    a=fixture();a[1][5]['qb_dropback']=None
    b=run(a);g=b['games'][1]
    assert g['packages'][0]['unknown_choice_snaps']==1 and g['packages'][0]['package_use_fraction']==1
    assert g['packages'][0]['pass_call_fraction'] is None and g['packages'][0]['known_classified_call_sample_fraction']==1


def test_spikes_kneels_separate_and_not_ordinary_budget():
    a=fixture();a[1][4]['qb_spike']=1;rush(a[1][5]);a[1][5]['qb_kneel']=1
    b=run(a);p=b['games'][1]['packages'][0]
    assert p['known_joint_choice_counts']=={'pass':0,'rush':0,'spike':1,'kneel':1}
    assert p['known_joint_choice_counts']['spike']==1 and p['known_joint_choice_counts']['kneel']==1
    assert p['ordinary_call_exposures']==0 and p['pass_call_fraction'] is None


def test_scramble_sack_are_pass_calls_once():
    a=fixture();a[1][4].update(sack=1,play_type_nfl='SACK');rush(a[1][5]);a[1][5].update(qb_scramble=1,qb_dropback=1)
    p=run(a)['games'][1]['packages'][0]
    assert p['known_joint_choice_counts']['pass']==2 and p['known_joint_choice_counts']['rush']==0


@pytest.mark.parametrize('field',['pass_touchdown','rush_touchdown','first_down_pass','qb_dropback'])
def test_positive_control_does_not_disappear(field):
    a=fixture();a[1][5].update(pass_attempt=0,rush_attempt=0,sack=0,play_type=None,play_type_nfl='TIMEOUT',qb_dropback=0);a[1][5][field]=1
    g=run(a)['games'][1];assert g['unknown_physical_or_side']==1 and g['packages'][0]['pass_call_fraction'] is None


def test_unknown_offense_can_belong_to_measured_team():
    a=fixture();a[1][5]['posteam']=None
    assert run(a)['games'][1]['unknown_physical_or_side']==1


def test_missing_prior_log_unknown_not_zero_and_no_skip():
    a=fixture();a[1][:]=[r for r in a[1] if r['week']!=2];a[0]['rows'][:]=[r for r in a[0]['rows'] if r['week']!=2]
    b=run(a);assert b['prior_scheduled_game_id']=='2023_02_SF_LA'
    assert b['games'][0]['source_log_missing'] and all(c['package_use_fraction_difference'] is None for c in b['comparisons'])


def test_source_only_potential_event_not_discarded():
    a=fixture();a[1].pop(5)
    assert run(a)['games'][1]['unknown_physical_or_side']==1


@pytest.mark.parametrize('field',['incoming_first_calling_game_source_proven','outgoing_playcalling_duties_ended_before_this_game'])
def test_announcement_title_does_not_replace_calling_proof(field):
    a=fixture();a[4][field]=None
    with pytest.raises(ValueError,match='Direct first'):run(a)


def test_duplicate_native_row_rejected():
    a=fixture();a[1].append(deepcopy(a[1][5]))
    with pytest.raises(ValueError,match='Duplicate native'):run(a)


def test_missing_administrative_source_row_cannot_fake_complete_cohort():
    a=fixture();control=deepcopy(a[1][5]);control.update(play_id=3,pass_attempt=0,rush_attempt=0,sack=0,qb_dropback=0,play_type=None,play_type_nfl='TIMEOUT');a[1].append(control)
    parent=build_personnel_package_continuity(a[0],a[1],a[2],a[3],before_period=202319)
    physical=dict(version=PHYSICAL_VERSION,season=2023,pregame_serving_eligible=False,rows=a[1][:-1])
    with pytest.raises(ValueError,match='Entire observed'):build(a[4],parent,physical)
