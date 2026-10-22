from copy import deepcopy
import pytest
from backend.app.product_services.qb_teammate_rushing_td import build_qb_teammate_rushing_td,summarize
Q='00-0000001';R='00-0000002';P='00000000-0000-0000-0000-000000000001';S='00000000-0000-0000-0000-000000000002'


def inputs():
    actors=[];games=[];events=[]
    for w in range(1,5):
        gid=f'2026_{w:02d}_BUF_MIA'
        for team in ('BUF','MIA'):games.append(dict(game_id=gid,team=team,season=2026,week=w))
        for n,p,role in ((Q,P,'QB'),(R,S,'RB')):actors.append(dict(game_id=gid,team='BUF',native_GSIS=n,player_master_id=p,canonical_candidate_ids=[p],identity_proven=True,source_position=role,participation=True,source_scope_proven=True,official_rush_attempts=3))
        events.append(dict(game_id=gid,team='BUF',play_id='owned',rush_TD=False,rusher=None))
        if w in(1,3):
            for i,n in enumerate((Q,R)):
                events.append(dict(game_id=gid,team='BUF',play_id=str(i),rush_TD=True,rusher=n,original_rusher=n,lateral_rush=False))
    return actors,games,events


def test_source_event_count_once_pair_rest_and_matched_baselines():
    a,g,e=inputs();r=build_qb_teammate_rushing_td(a,g,e);p=r['profiles'][0]['exact'];assert p['samples']==4
    assert p['QB_TDs']==2 and p['teammate_TDs']==2 and p['rest_TDs']==0 and p['physical_TD_budget']==4
    assert p['coexceedance']['observed_joint']==0.5 and p['coexceedance']['independence_marginal_product']==0.25
    assert p['rushing_TD_counts']['covariance']==0.25
    assert p['budget_strata'][0]['team_rushing_TD_budget']==0 and p['budget_strata'][0]['QB_share']is None
    assert not set(r['pair_game_rows'][0]['QB_TD_play_ids'])&set(r['pair_game_rows'][0]['teammate_TD_play_ids'])


def test_multiple_pair_TDs_are_different_physical_events_and_duplicate_rejected():
    a,g,e=inputs();e.append(deepcopy(e[1]))
    with pytest.raises(ValueError,match='counted once'):build_qb_teammate_rushing_td(a,g,e)


def test_missing_own_log_unknown_not_zero_and_sample_separate():
    a,g,e=inputs();e=[x for x in e if x['game_id']!='2026_02_BUF_MIA'];r=build_qb_teammate_rushing_td(a,g,e)
    assert not r['pair_game_rows'][1]['complete']and r['profiles'][0]['exact']is None
    assert r['profiles'][0]['known_complete_sample']['samples']==3
    assert r['strict_prior_windows'][0]['exact']is None
    assert '2026_02_BUF_MIA'in r['strict_prior_windows'][0]['unknown_game_ids']


def test_unknown_eligibility_or_native_scorer_masks_pair_count_not_known_physical_TD():
    for value,scorer in ((None,None),(True,None)):
        a,g,e=inputs();e.append(dict(game_id='2026_02_BUF_MIA',team='BUF',play_id='unknown',rush_TD=value,rusher=scorer))
        r=build_qb_teammate_rushing_td(a,g,e);assert not r['pair_game_rows'][1]['complete']
        b=next(x for x in r['team_game_budget']if x['game_id']=='2026_02_BUF_MIA'and x['team']=='BUF')
        if value is True:assert b['known_rushing_TDs']==1 and b['unknown_scorer']==1
        else:assert b['unknown_eligibility']==1


def test_official_carry_unknown_not_zero_or_positive_participation_inferred():
    for field,value in (('official_rush_attempts',None),('participation',None),('source_scope_proven',False)):
        a,g,e=inputs();a[0][field]=value;r=build_qb_teammate_rushing_td(a,g,e)
        assert not r['pair_game_rows'][0]['complete']and r['profiles'][0]['exact']is None


def test_lateral_native_TD_scorer_may_have_zero_carry_not_original_rusher_credit():
    a,g,e=inputs();a[0]['official_rush_attempts']=0;e[1].update(rusher=Q,original_rusher=R,lateral_rush=True)
    r=build_qb_teammate_rushing_td(a,g,e);assert r['pair_game_rows'][0]['complete']
    assert r['pair_game_rows'][0]['QB_rushing_TDs']==1 and r['pair_game_rows'][0]['teammate_rushing_TDs']==1
    assert r['physical_rushing_TD_evidence'][0]['original_rusher']==R


def test_unexplained_TD_count_exceeds_carries_masks_exact_sample():
    a,g,e=inputs();a[0]['official_rush_attempts']=0;r=build_qb_teammate_rushing_td(a,g,e)
    assert not r['pair_game_rows'][0]['complete']and r['pair_game_rows'][0]['carry_sanity_compatible']is False


def test_all_potential_TD_scorers_need_same_frozen_identity_scope():
    a,g,e=inputs();e.append(dict(game_id='2026_02_BUF_MIA',team='BUF',play_id='u',rush_TD=None,rusher='00-0009999'))
    with pytest.raises(ValueError,match='Every potentially'):build_qb_teammate_rushing_td(a,g,e)


def test_inherited_withheld_and_all_edge_alias_closure_across_other_game():
    a,g,e=inputs();a[0]['canonical_candidate_ids']=[P,S];a[0]['identity_proven']=False
    r=build_qb_teammate_rushing_td(a,g,e);assert {Q,R}<=set(r['native_identity_conflicts'])
    assert all(not x['complete']for x in r['pair_game_rows'])
    a,g,e=inputs();a[0]['identity_proven']=False
    assert all(not x['complete']for x in build_qb_teammate_rushing_td(a,g,e)['pair_game_rows'])


def test_prior_pair_universe_uses_earlier_teammate_carry_or_TD_only():
    a,g,e=inputs()
    for row in a:
        if row['native_GSIS']==R and row['game_id']!='2026_04_BUF_MIA':row['official_rush_attempts']=0
    e=[x for x in e if x.get('rusher')!=R];e.append(dict(game_id='2026_04_BUF_MIA',team='BUF',play_id='firstR',rush_TD=True,rusher=R,original_rusher=R,lateral_rush=False))
    r=build_qb_teammate_rushing_td(a,g,e);assert r['strict_prior_windows']==[]


def test_strict_scheduled_prefix_not_latest_known_pair_games():
    a,g,e=inputs();a=[x for x in a if not(x['native_GSIS']==R and x['game_id']=='2026_02_BUF_MIA')]
    r=build_qb_teammate_rushing_td(a,g,e);w=r['strict_prior_windows'][0]
    assert w['target_period']==202603 and w['contributing_game_ids']==['2026_01_BUF_MIA','2026_02_BUF_MIA']
    assert w['exact']is None and w['known_complete_sample']is None


def test_canonical_UUID_and_native_scope_guards():
    a,g,e=inputs();a[0]['canonical_candidate_ids']=['bad']
    with pytest.raises(ValueError):build_qb_teammate_rushing_td(a,g,e)
    a,g,e=inputs();g[0]['team']='DEN'
    with pytest.raises(ValueError,match='Native scheduled'):build_qb_teammate_rushing_td(a,g,e)


def test_summarize_requires_two_samples_and_full_team_budget():
    assert summarize([])is None
    r=dict(QB_rushing_TDs=1,teammate_rushing_TDs=1,team_rushing_TDs=1,rest_rushing_TDs=0)
    with pytest.raises(ValueError,match='conserved'):summarize([r,r])
