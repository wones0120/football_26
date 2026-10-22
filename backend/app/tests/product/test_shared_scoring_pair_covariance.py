from copy import deepcopy
import pytest
from backend.app.product_services.shared_scoring_pair_covariance import build_shared_scoring_pair_covariance
Q='00-0000001';R='00-0000002';OTHER='00-0000003';TRICK='00-0000004'
PID='00000000-0000-0000-0000-000000000001';RID='00000000-0000-0000-0000-000000000002'


def inputs():
    games=[dict(game_id=f'2023_{w:02}_BUF_MIA',season=2023,week=w,team='BUF')for w in (1,2,3)]
    rows=[];events=[]
    for w,g in enumerate(games,1):
        for native,pid,role in ((Q,PID,'QB'),(R,RID,'TE')):
            rows.append(dict(game_id=g['game_id'],team='BUF',native_GSIS=native,source_position=role,participation=True,identity_proven=True,player_master_id=pid,canonical_candidate_ids=[pid],official_pass_attempts=w*10 if native==Q else 0,official_targets=w if native==R else 0,official_passing_TDs=(1 if w<3 else 0)if native==Q else 0,official_receiving_TDs=(1 if w<3 else 0)if native==R else 0))
        events.append(dict(game_id=g['game_id'],play_id='1',team='BUF',physical_passing_TD=False,source_passer_id=None,source_TD_scorer_id=None))
    events.extend([dict(game_id=games[0]['game_id'],play_id='10',team='BUF',physical_passing_TD=True,source_passer_id=Q,source_TD_scorer_id=R),dict(game_id=games[1]['game_id'],play_id='20',team='BUF',physical_passing_TD=True,source_passer_id=Q,source_TD_scorer_id=OTHER),dict(game_id=games[1]['game_id'],play_id='30',team='BUF',physical_passing_TD=True,source_passer_id=TRICK,source_TD_scorer_id=R)])
    return rows,games,events


def build(rows=None,games=None,events=None):
    base=inputs()
    return build_shared_scoring_pair_covariance(rows if rows is not None else base[0],games if games is not None else base[1],events if events is not None else base[2],before_period=202607)


def test_matched_count_covariance_and_pinned_TD_score_components():
    r=build();p=r['profiles'][0];exact=p['exact']
    assert p['QB_player_master_id']==PID and p['receiver_player_master_id']==RID
    assert p['complete_matched_games']==3 and r['distinct_native_games']==3
    assert exact['pass_attempt_target']['covariance']==pytest.approx(20/3)
    assert exact['TD_score_components']['covariance']==pytest.approx(16/3)
    assert r['scoring_definition']['passing_TD_points']==4 and r['scoring_definition']['receiving_TD_points']==6
    assert not r['scoring_definition']['full_fantasy_scoring']and not r['pregame_serving_eligible']


def test_joint_TDs_are_not_automatically_the_same_physical_event():
    p=build()['profiles'][0];x=p['exact']['TD_coexceedance']
    assert x['observed_joint']==2/3
    assert x['independence_marginal_product']==pytest.approx(4/9)
    assert x['observed_minus_independence']==pytest.approx(2/9)
    assert p['shared_physical_TD_sum']==1
    assert p['exact']['TD_score_components']['mean_y']==4


def test_missing_stat_does_not_become_zero_despite_positive_participation():
    rows,_,_=inputs();rows[3]['official_targets']=None
    r=build(rows=rows);p=r['profiles'][0]
    assert p['exact']is None and p['complete_matched_games']==2
    assert r['pair_game_rows'][1]['official_receiver_targets']is None
    assert p['known_complete_sample']['pass_attempt_target']['samples']==2


def test_absent_actor_game_membership_unknown_not_nonparticipant_zero():
    rows,_,_=inputs();rows.pop(3)
    p=build(rows=rows)['profiles'][0]
    assert p['exact']is None and p['unknown_exposure_or_source_game_ids']==['2023_02_BUF_MIA']
    assert p['excluded_known_nonparticipating_or_nonrole_game_ids']==[]


def test_explicit_zero_offense_excludes_only_if_counts_do_not_contradict_it():
    rows,games,events=inputs();rows[3].update(participation=False,official_targets=0,official_receiving_TDs=0)
    events=[e for e in events if not(e['game_id']==games[1]['game_id']and e.get('source_TD_scorer_id')==R)]
    p=build(rows=rows,events=events)['profiles'][0]
    assert p['exact']is not None and p['complete_matched_games']==2
    assert p['excluded_known_nonparticipating_or_nonrole_game_ids']==[games[1]['game_id']]
    p=build(rows=rows)['profiles'][0]
    assert p['exact']is None and games[1]['game_id']in p['unknown_exposure_or_source_game_ids']


def test_lateral_TD_scorer_can_have_zero_targets_without_losing_actual_receiving_TD():
    rows,_,_=inputs();rows[1]['official_targets']=0
    r=build(rows=rows);g=r['pair_game_rows'][0]
    assert g['complete_matched_exposure']and g['receiver_observed_receiving_TDs']==1 and g['official_receiver_targets']==0


@pytest.mark.parametrize('changes',[dict(physical_passing_TD=None),dict(source_passer_id=None),dict(source_TD_scorer_id=None),dict(source_passer_id='bad-native')])
def test_unknown_physical_or_attribution_masks_pair_counts_not_zero(changes):
    rows,games,events=inputs();events[-1].update(changes)
    r=build(events=events);p=r['profiles'][0]
    assert p['exact']is None
    assert r['pair_game_rows'][1]['QB_observed_passing_TDs']is None
    if changes.get('physical_passing_TD',True)is True:
        assert next(g for g in r['source_game_physical_passing_TDs']if g['game_id']=='2023_02_BUF_MIA')['known_physical_passing_TDs']==2


def test_missing_whole_offense_source_log_cannot_invent_zero_TDs():
    _,games,events=inputs();events=[e for e in events if e['game_id']!=games[2]['game_id']]
    r=build(events=events)
    assert r['pair_game_rows'][2]['QB_observed_passing_TDs']is None
    assert r['profiles'][0]['exact']is None


def test_all_candidate_identity_edges_withhold_implicated_keys_across_games():
    rows,_,_=inputs();rows[0]['canonical_candidate_ids']=[PID,RID]
    r=build(rows=rows)
    assert r['native_canonical_conflict_keys']==[Q,R]
    assert r['profiles'][0]['exact']is None
    assert r['profiles'][0]['QB_player_master_id']is None


def test_nonQB_trick_passer_and_other_receiver_physical_events_preserved():
    r=build()
    assert len(r['physical_passing_TD_event_evidence'])==3
    g=next(g for g in r['source_game_physical_passing_TDs']if g['game_id']=='2023_02_BUF_MIA')
    assert g['known_physical_passing_TDs']==2
    assert r['pair_game_rows'][1]['pair_shared_physical_TDs']==0


def test_duplicate_physical_event_cannot_add_volume_and_single_game_not_covariance():
    rows,games,events=inputs()
    with pytest.raises(ValueError,match='One physical'):
        build(events=events+[events[-1]])
    r=build(rows=rows[:2],games=games[:1],events=[e for e in events if e['game_id']==games[0]['game_id']])
    assert r['profiles'][0]['exact']is None
    assert r['profiles'][0]['known_complete_sample']['TD_score_components']['covariance']is None


def test_inherited_global_withholding_not_undone_by_narrow_current_pair_universe():
    rows,_,_=inputs()
    # Another historic native key outside these rows already implicated this UUID.
    for r in rows:
        if r['native_GSIS']==Q:r['identity_proven']=False
    p=build(rows=rows)['profiles'][0]
    assert p['QB_player_master_id']is None and p['exact']is None


@pytest.mark.parametrize('missing_or_conflicting',[None,0,2])
def test_same_original_official_receiving_TD_field_must_match_native_TD_credit(missing_or_conflicting):
    rows,_,_=inputs();rows[1]['official_receiving_TDs']=missing_or_conflicting
    r=build(rows=rows)
    assert not r['pair_game_rows'][0]['TD_credit_compatible']and r['profiles'][0]['exact']is None
    assert r['pair_game_rows'][0]['receiver_official_receiving_TDs']==missing_or_conflicting


def test_positive_official_TD_conflicts_with_zero_snap_even_if_observed_ledger_misses_it():
    rows,games,events=inputs();rows[3].update(participation=False,official_targets=0)
    events=[e for e in events if not(e['game_id']==games[1]['game_id']and e.get('source_TD_scorer_id')==R)]
    r=build(rows=rows)
    assert r['pair_game_rows'][1]['positive_pair_participation']is None
    assert r['profiles'][0]['exact']is None
