from copy import deepcopy
import math
import pytest
from backend.app.product_services.receiver_pair_competition import decompose,actor_channels,build_receiver_pair_competition,SOURCE_VERSION
A='00-0000001';B='00-0000002';P='00000000-0000-0000-0000-000000000001';Q='00000000-0000-0000-0000-000000000002'

def rows():
    return [dict(targets_a=1,targets_b=3,team_targets=5,EPA_a=-2.,EPA_b=4.),dict(targets_a=3,targets_b=1,team_targets=5,EPA_a=5.,EPA_b=-1.),dict(targets_a=2,targets_b=2,team_targets=8,EPA_a=2.,EPA_b=3.)]

def test_exact_four_term_efficiency_and_team_budget_covariance_identities():
    d=decompose(rows());assert d['samples']==3
    assert math.isclose(d['observed_EPA_covariance'],d['EPA_decomposition']['reconstructed_EPA_covariance'])
    assert math.isclose(d['target_count_covariance'],d['within_budget_target_covariance']+d['between_budget_target_covariance'])
    assert d['pooled_targets_a']+d['pooled_targets_b']+d['pooled_rest_targets']==d['pooled_team_targets']
    assert [c['weight']for c in d['team_budget_strata']]==[2/3,1/3]
    assert d['team_budget_strata'][1]['single_sample_algebra_only']
    assert math.isclose(d['EPA_decomposition']['target_weighted_EPA_per_target_a'],5/6)


def test_no_forced_negative_competition_and_same_budget_rest_can_move_both():
    r=[dict(targets_a=1,targets_b=1,team_targets=8,EPA_a=1.,EPA_b=2.),dict(targets_a=2,targets_b=2,team_targets=8,EPA_a=2.,EPA_b=4.)]
    assert decompose(r)['within_budget_target_covariance']>0


def test_zero_target_games_stay_in_identical_efficiency_sample():
    r=rows();r[0].update(targets_a=0,EPA_a=0.)
    d=decompose(r);assert d['samples']==3 and d['pooled_targets_a']==5
    assert math.isclose(sum(d['EPA_decomposition']['terms'].values()),d['observed_EPA_covariance'])


def test_zero_pooled_target_denominator_undefined_not_fake_efficiency():
    r=rows()
    for x in r:x.update(targets_a=0,EPA_a=0.)
    d=decompose(r);assert d['EPA_decomposition']is None and d['target_count_covariance']==0
    assert decompose(r[:1])is None and decompose([])is None


@pytest.mark.parametrize('change',[dict(team_targets=1),dict(targets_a=-1),dict(EPA_a=float('nan')),dict(targets_a=False),dict(targets_a=0,EPA_a=2.)])
def test_bad_budget_or_unmatched_EPA_rejected(change):
    r=rows();r[0].update(change)
    with pytest.raises(ValueError):decompose(r)


def source():
    games=[];actors=[];events=[]
    for w in range(1,5):
        gid=f'2023_{w:02d}_BUF_MIA';games.append(dict(game_id=gid,season=2023,week=w,sides=['BUF','MIA'],game_date=f'2023-09-{w:02d}'))
        for n in (A,B):actors.append(dict(game_id=gid,team='BUF',source_player_id=n,source_roles=['WR']))
        for k,n in enumerate((A,B),1):events.append(dict(game_id=gid,play_id=str(k),offense='BUF',eligible_target_attempt=True,attributed_receiver_id=n,target_play_EPA=float(w*k),verified_offensive_eleven=True,native_offensive_players=[A,B]+[f'00-{i:07d}'for i in range(3,12)],attribution_conflict=False))
    return dict(version=SOURCE_VERSION,pregame_serving_eligible=False,season=2023,before_period=202318,native_identity_universe=[A,B],expected_games=games,game_rows=actors,event_basis=events,semantic_sha256='reviewed-native-semantic'),{A:dict(status='unique_native_alias',player_master_id=P),B:dict(status='unique_native_alias',player_master_id=Q)}


def test_full_parent_direct_categories_not_required_and_matched_strict_windows():
    b,ids=source();r=build_receiver_pair_competition(b,ids)
    assert len(r['observed_profiles'])==1 and r['observed_profiles'][0]['exact']['samples']==4
    assert len(r['strict_prior_windows'])==2
    assert r['strict_prior_windows'][0]['target_period']==202303
    assert r['strict_prior_windows'][0]['contributing_game_ids']==['2023_01_BUF_MIA','2023_02_BUF_MIA']
    assert r['strict_prior_windows'][0]['exact']['samples']==2
    assert all(x['native_a']==A and x['native_b']==B for x in r['pair_game_rows'])


def test_unknown_game_not_skipped_but_known_complete_sample_kept():
    b,ids=source();b['event_basis'][2]['eligible_target_attempt']=None
    r=build_receiver_pair_competition(b,ids);p=r['observed_profiles'][0]
    assert p['exact']is None and p['known_complete_sample']['samples']==3
    assert r['strict_prior_windows'][0]['exact']is None
    assert '2023_02_BUF_MIA'in r['strict_prior_windows'][0]['unknown_game_ids']


def test_missing_actor_participation_not_zero_and_no_future_actor_cohort_selection():
    b,ids=source();b['game_rows']=[a for a in b['game_rows']if not(a['source_player_id']==B and a['game_id'].startswith('2023_01'))]
    r=build_receiver_pair_competition(b,ids)
    assert r['pair_game_rows'][0]['complete']is False
    assert r['strict_prior_windows'][0]['exact']is None
    b['game_rows']=[a for a in b['game_rows']if a['source_player_id']!=B or a['game_id'].startswith('2023_04')]
    assert build_receiver_pair_competition(b,ids)['strict_prior_windows']==[]


def test_missing_own_offense_source_log_unknown_not_zero():
    b,ids=source();teams,actors=actor_channels(b,ids)
    assert teams[('2023_01_BUF_MIA','MIA')]['exact_team_targets']is None
    b['event_basis']=[e for e in b['event_basis']if e['game_id']!='2023_01_BUF_MIA']
    _,actors=actor_channels(b,ids);assert actors[('2023_01_BUF_MIA','BUF',A)]['exact_targets']is None


def test_off_field_can_exclude_actor_unknown_but_full_budget_still_unknown():
    b,ids=source();e=deepcopy(b['event_basis'][0]);e.update(play_id='other',eligible_target_attempt=None,attributed_receiver_id=None,native_offensive_players=[f'00-{i:07d}'for i in range(3,14)],verified_offensive_eleven=True)
    b['event_basis'].append(e);teams,actors=actor_channels(b,ids)
    assert actors[('2023_01_BUF_MIA','BUF',A)]['exact_targets']==1
    assert teams[('2023_01_BUF_MIA','BUF')]['exact_team_targets']is None
    e['attribution_conflict']=True;teams,actors=actor_channels(b,ids)
    assert actors[('2023_01_BUF_MIA','BUF',A)]['exact_targets']is None


def test_missing_EPA_keeps_target_count_and_masks_identical_pair_sample():
    b,ids=source();b['event_basis'][0]['target_play_EPA']=None;teams,actors=actor_channels(b,ids)
    assert teams[('2023_01_BUF_MIA','BUF')]['exact_team_targets']==2
    assert actors[('2023_01_BUF_MIA','BUF',A)]['exact_targets']==1
    assert actors[('2023_01_BUF_MIA','BUF',A)]['exact_EPA_sum']is None
    assert build_receiver_pair_competition(b,ids)['pair_game_rows'][0]['complete']is False


def test_global_identity_withholding_and_complete_receipt_universe():
    b,ids=source();ids[A].update(status='canonical_native_conflict',player_master_id=None)
    assert all(not g['complete']for g in build_receiver_pair_competition(b,ids)['pair_game_rows'])
    ids.pop(A)
    with pytest.raises(ValueError,match='global identity'):build_receiver_pair_competition(b,ids)


def test_native_duplicate_and_bad_role_rejected():
    b,ids=source();b['event_basis'].append(deepcopy(b['event_basis'][0]))
    with pytest.raises(ValueError,match='Unique native'):build_receiver_pair_competition(b,ids)
    b,ids=source();b['game_rows'][0]['source_roles']=['CB']
    with pytest.raises(ValueError,match='receiving-role'):build_receiver_pair_competition(b,ids)


def test_false_exact_eleven_header_cannot_certify_off_field_exclusion():
    b,ids=source();b['event_basis'][0]['native_offensive_players']=[A]
    with pytest.raises(ValueError,match='Exact11'):actor_channels(b,ids)


def test_missing_source_budget_and_unresolved_canonical_cannot_create_zero_pair():
    b,ids=source();b['event_basis']=[]
    r=build_receiver_pair_competition(b,ids)
    assert all(not x['complete']for x in r['pair_game_rows'])
    assert all(x['exact']is None for x in r['strict_prior_windows'])
