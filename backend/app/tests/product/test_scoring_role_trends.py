from copy import deepcopy
import pytest
from backend.app.product_services.scoring_role_trends import build_scoring_role_trends, METRICS
from backend.app.product_services.player_scoring_zone_components import VERSION
P='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'


def fixture():
    s=dict(version=VERSION,before_period=202607,evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,full_team_denominators=[],actor_game_rows=[],identity_review_requests=[],provenance={})
    for w in range(1,5):
        game=f'2026_{w:02}_SF_WAS';channels={}
        for d in METRICS.values():channels.setdefault(d['channel'],{})[d['zone']]=dict(exact_within_log_count=4)
        s['full_team_denominators'].append(dict(game_id=game,team='WAS',channels=channels))
        s['actor_game_rows'].append(dict(game_id=game,team='WAS',source_player_id='00-0031234',player_master_id=P,metrics={m:dict(exact_within_log_count=1 if w<4 else 2) for m in METRICS}))
    return s


def run(s=None):return build_scoring_role_trends(s or fixture(),before_period=202607)


def test_disjoint_opportunity_shares_not_TD_rates():
    r=run()['actor_trends'][0]
    assert len(r['metrics'])==6
    for m in r['metrics'].values():assert (m['prior_actor_count'],m['prior_full_team_count'],m['share_change'])==(3,12,.25)
    assert run()['forecast'] is None and run()['pregame_serving_eligible'] is False


def test_missing_latest_prior_and_unknown_budget_not_zero():
    s=fixture();s['actor_game_rows'].pop()
    assert all(m['share_change'] is None for m in run(s)['actor_trends'][0]['metrics'].values())
    s=fixture();s['actor_game_rows'].pop(0)
    assert all(m['prior_share'] is None for m in run(s)['actor_trends'][0]['metrics'].values())
    s=fixture();s['full_team_denominators'][0]['channels']['rush_attempts']['inside5']['exact_within_log_count']=None
    assert run(s)['actor_trends'][0]['metrics']['G11-M03']['share_change'] is None


def test_zero_exposure_undefined_not_zero_share():
    s=fixture()
    for r in s['full_team_denominators']:
        for c in r['channels'].values():
            for m in c.values():m['exact_within_log_count']=0
    for r in s['actor_game_rows']:
        for m in r['metrics'].values():m['exact_within_log_count']=0
    assert all(m['share_change'] is None for m in run(s)['actor_trends'][0]['metrics'].values())


@pytest.mark.parametrize('case',['duplicate','budget','future','identity','serving','team'])
def test_boundaries(case):
    s=fixture()
    if case=='duplicate':s['actor_game_rows'].append(deepcopy(s['actor_game_rows'][0]))
    if case=='budget':s['actor_game_rows'][0]['metrics']['G11-M03']['exact_within_log_count']=5
    if case=='future':s['full_team_denominators'][0]['game_id']='2026_07_SF_WAS'
    if case=='identity':s['actor_game_rows'][0]['player_master_id']='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
    if case=='serving':s['pregame_serving_eligible']=True
    if case=='team':s['full_team_denominators'][0]['team']='NYG'
    with pytest.raises(ValueError):run(s)


def test_order_and_provenance_clocks_stable():
    s=fixture();sha=run(s)['semantic_sha256'];s['actor_game_rows'].reverse();s['full_team_denominators'].reverse();s['provenance']['actual_read_at']='later'
    assert run(s)['semantic_sha256']==sha
