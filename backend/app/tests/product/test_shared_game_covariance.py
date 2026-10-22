from copy import deepcopy
import pytest
from backend.app.product_services.shared_game_covariance import build_shared_game_covariance,AXES
from backend.app.product_services.offensive_environment_catalog import VERSION as PLAYS_VERSION
from backend.app.product_services.scoreboard_result_features import VERSION as SCORES_VERSION


def fixture():
    plays=[];scores=[]
    for week,(h,a,hs,aws)in enumerate(((40,60,7,21),(50,50,14,14),(60,40,21,7)),start=1):
        gid=f'2026_{week:02d}_BUF_MIA'
        for team,n in(('MIA',h),('BUF',a)):plays.append(dict(game_id=gid,period=202600+week,team=team,metrics={'G01-M01':dict(value=n,known_lower_bound=n,unknown_eligibility=0)}))
        scores.append(dict(game_id=gid,season=2026,week=week,home_team='MIA',away_team='BUF',exact_completed_score=[hs,aws],unknown_reason=None))
    return dict(version=PLAYS_VERSION,before_period=202606,game_rows=plays,semantic_sha256='plays',pregame_serving_eligible=False),dict(version=SCORES_VERSION,before_period=202606,game_rows=scores,semantic_sha256='scores',pregame_serving_eligible=False)

def build(p=None,s=None):
    a,b=fixture();return build_shared_game_covariance(p or a,s or b)

def profile(r,team='MIA'):return next(x for x in r['team_season_profiles']if x['team']==team)


def test_four_paired_axes_covariance_independence_baseline_and_no_doublecount():
    r=build();g=r['global_season_profiles'][0]['exact_full_observed_cohort'];a,b,c,d=AXES
    assert g['games']==3 and g['means']=={a:50,b:50,c:14,d:14}
    assert g['population_covariance'][a][b]==pytest.approx(-200/3)
    assert g['population_covariance'][c][d]==pytest.approx(-98/3)
    assert g['correlation'][a][b]==pytest.approx(-1)
    assert g['observed_cross_moments'][a][b]-g['independence_marginal_products'][a][b]==pytest.approx(g['population_covariance'][a][b])
    assert len(r['game_rows'])==3 and sum(x['observed_games']for x in r['team_season_profiles'])==6
    assert g['games']!=6 and r['pregame_serving_eligible']is False and r['forecast']is None
    assert r['pending_other_catalog_ids']==['G24-M05']


def test_team_orientation_swaps_values_without_adding_independent_games():
    r=build();home=profile(r,'MIA');away=profile(r,'BUF')
    assert home['logs'][0]['values']==[40,60,7,21]
    assert away['logs'][0]['values']==[60,40,21,7]
    assert home['unique_game_ids']==away['unique_game_ids']
    assert len(set(home['unique_game_ids']+away['unique_game_ids']))==3


def test_unknown_physical_pair_masks_full_statistics_known_sample_separate():
    p,s=fixture();p['game_rows'][0]['metrics']['G01-M01'].update(value=None,unknown_eligibility=1)
    r=build(p,s);g=r['global_season_profiles'][0]
    assert g['observed_games']==3 and g['known_complete_sample']['games']==2
    assert g['exact_full_observed_cohort']['population_covariance']is None
    assert g['exact_full_observed_cohort']['games']==3
    assert g['known_complete_sample']['population_covariance']is not None
    assert g['unknown_axes'][AXES[0]]==1 and g['unknown_axes'][AXES[1]]==0


def test_missing_score_game_or_one_physical_side_is_unknown_never_zero():
    p,s=fixture();s['game_rows']=s['game_rows'][1:]
    r=build(p,s);assert r['game_rows'][0]['values'][2:]==[None,None]
    assert r['global_season_profiles'][0]['known_complete_sample']['games']==2
    p,s=fixture();p['game_rows']=p['game_rows'][1:]
    assert build(p,s)['game_rows'][0]['values'][0]is None


def test_provider_reported_unproven_score_not_substituted_for_completed_score():
    p,s=fixture();s['game_rows'][0].update(exact_completed_score=None,opponent_team_reported_final_scores=dict(home=7,away=21),unknown_reason='unfinished/conflicting')
    r=build(p,s);assert r['game_rows'][0]['values'][2:]==[None,None]
    assert r['game_rows'][0]['completed_score_unknown_reason']=='unfinished/conflicting'


def test_whole_team_points_remain_intact_no_dst_or_offense_only_deduction():
    p,s=fixture();s['game_rows'][0]['exact_completed_score']=[35,28]
    assert build(p,s)['game_rows'][0]['values'][2:]==[35,28]


def test_empty_and_constant_variance_have_undefined_correlation():
    p,s=fixture()
    for x in p['game_rows']:x['metrics']['G01-M01'].update(value=50,known_lower_bound=50)
    r=build(p,s);m=r['global_season_profiles'][0]['exact_full_observed_cohort']
    assert m['population_covariance'][AXES[0]][AXES[0]]==0
    assert all(v is None for v in m['correlation'][AXES[0]].values())
    p['game_rows']=[];s['game_rows']=[];r=build(p,s)
    assert r['game_rows']==[] and r['global_season_profiles']==[]


@pytest.mark.parametrize('field,value',[('value',-1),('value',1.5),('value',True),('known_lower_bound',None)])
def test_invalid_physical_exact_count_contract_rejected(field,value):
    p,s=fixture();p['game_rows'][0]['metrics']['G01-M01'][field]=value
    with pytest.raises(ValueError):build(p,s)


def test_unknown_physical_eligibility_cannot_carry_exact_count():
    p,s=fixture();p['game_rows'][0]['metrics']['G01-M01']['unknown_eligibility']=1
    with pytest.raises(ValueError,match='contract'):build(p,s)


def test_native_identity_duplicates_source_scope_and_score_integrality():
    p,s=fixture();p['game_rows'].append(deepcopy(p['game_rows'][0]))
    with pytest.raises(ValueError,match='Unique native physical'):build(p,s)
    p,s=fixture();s['game_rows'].append(deepcopy(s['game_rows'][0]))
    with pytest.raises(ValueError,match='Unique completed'):build(p,s)
    p,s=fixture();s['game_rows'][0]['home_team']='BUF'
    with pytest.raises(ValueError,match='home-away'):build(p,s)
    p,s=fixture();s['before_period']=202607
    with pytest.raises(ValueError,match='boundary'):build(p,s)
    p,s=fixture();s['game_rows'][0]['exact_completed_score']=[7,-1]
    with pytest.raises(ValueError,match='integer'):build(p,s)
