from copy import deepcopy

import pytest

from backend.app.product_services.showdown_candidate_comparison import baseline_rescore_discovery
from backend.app.product_services.showdown_ownership_policy import showdown_ownership_policy
from backend.app.product_services.showdown_portfolio_selection import select_showdown_portfolio, signature
from backend.app.product_services.optimizer import summarize_showdown_portfolio_exposure
from backend.app.tests.product.test_showdown_portfolio_selection import lineup
from backend.app.product_services.lineup_correlation_scoring import score_lineup_correlations
from backend.app.product_services.rule_library import resolve_strategy_profile


def test_canonical_roster_ignores_row_order_but_retains_captain():
    a=lineup('canonical-c',['a','b','c','d','e'],80,140,100)
    assert signature(a)==signature(list(reversed(a)))
    b=deepcopy(a);b[0]['roster_position']='FLEX';b[1]['roster_position']='CPT'
    assert signature(a)!=signature(b)


def test_discovery_is_rescored_on_exact_baseline_and_keeps_conditional_evidence():
    conditional=lineup('c',['a','b','d','e','f'],120,210,180)
    baseline=lineup('c',['a','b','d','e','f'],80,140,100)
    called=[]
    def solve(ids, captain):
        called.append((ids,captain));return deepcopy(baseline)
    result=baseline_rescore_discovery(conditional,solve)
    assert called==[({'c','a','b','d','e','f'},'c')]
    assert sum(r['projection'] for r in result)==pytest.approx(80)
    assert sum(r['conditioned_projection'] for r in result)==pytest.approx(120)
    assert result[0]['solver_objective_value']==100
    assert result[0]['conditioned_selector']==180
    assert conditional[0]['solver_objective_value']==180


def test_rescoring_cannot_change_canonical_roster():
    conditional=lineup('c',['a','b','d','e','f'],120,210,180)
    with pytest.raises(ValueError,match='baseline legality'):
        baseline_rescore_discovery(conditional,lambda *_:lineup('x',['a','b','d','e','f'],80,140,100))


def test_conditional_projection_cannot_raise_common_baseline_quality_floor():
    baseline=lineup('base',['a','b','c','d','e'],80,140,100)
    conditional=lineup('condition',['a','b','c','d','f'],120,210,101)
    for row in conditional:
        row.update(baseline_projection=80/6,baseline_p90=140/6,showdown_scenario_id='winner')
    selected,report=select_showdown_portfolio([baseline,conditional],requested=2,player_limits={},captain_limit=2)
    assert len(selected)==2
    assert report['best_mean']==pytest.approx(80)
    assert report['best_p90']==pytest.approx(140)
    assert report['quality_basis']=='common_baseline'


def test_global_ownership_validation_does_not_imply_showdown_promotion():
    headers=[{'metrics_json':{'promotion_gate':{'status':'passed','policy':'diagnostic only'}}}]
    assert not showdown_ownership_policy(headers,['run'])['eligible']
    headers[0]['metrics_json']['selector_approval_by_format']={'showdown':{'status':'approved'}}
    assert showdown_ownership_policy(headers,['run'])['eligible']
    assert not showdown_ownership_policy([],['run'])['eligible']
    assert not showdown_ownership_policy(headers,['run','another'])['eligible']


def test_underfill_reports_binding_exposure_and_both_denominators():
    candidates=[lineup(str(i),['core','a','b','c',str(i+10)],80,140,100-i) for i in range(5)]
    for l in candidates:
        for r in l:r.update(position='WR',base_salary=5000)
    selected,report=select_showdown_portfolio(candidates,requested=5,player_limits={'core':4},captain_limit=3)
    assert len(selected)==4
    assert report['underfill_diagnostics']['reason']=='player/captain exposure caps prevent filling from distinct quality-eligible rosters'
    exposure=summarize_showdown_portfolio_exposure(selected,requested_lineups=5,exposure_rates={'core':.8})
    core=next(r for r in exposure['rows'] if r['player_id']=='core' and r['scope']=='player')
    assert exposure['cap_denominator']==5 and exposure['realized_exposure_denominator']==4
    assert core['maximum_allowed_appearances']==4 and core['final_generated_portfolio_exposure']==1
    assert core['cap_respected']


def test_cle_baseline_underdog_cannot_trigger_favorite_five_one():
    profile=resolve_strategy_profile(contest_format='showdown',objective='gpp')
    rows=[{'player_id':str(i),'player_team':'CLE' if i<5 else 'PIT','position':'RB',
           'opponent_team':'PIT' if i<5 else 'CLE','team_spread_line':2.5 if i<5 else -2.5,
           'game_total_line':38.5,'market_context_point_in_time_safe':True,'roster_position':'CPT' if i==0 else 'FLEX'} for i in range(6)]
    result=score_lineup_correlations(rows,profile=profile)
    assert 'favorite_five_one_construction' not in result['positive_reason_codes']
    for r in rows:
        r['team_spread_line']=-14 if r['player_team']=='CLE' else 14
        r['showdown_scenario_id']='team_a_decisive_win'
    conditioned=score_lineup_correlations(rows,profile=profile)
    rule=next(r for r in conditioned['triggered_rules'] if r['reason_code']=='favorite_five_one_construction')
    assert rule['objective_contribution']==pytest.approx(.60)
    assert rule['evidence']['market_basis']=='conditional_winner_assumption'
    assert 'conditional decisive-winner assumption' in rule['description']
    assert result['total_adjustment']==pytest.approx(0)


def test_scenario_local_floor_and_common_floor_are_distinct_policies():
    from scripts.summarize_showdown_parity import local_quality
    baseline=lineup('base',['a','b','c','d','e'],80,140,100)
    conditional=lineup('condition',['a','b','c','d','f'],120,210,101)
    for r in conditional:r['showdown_scenario_id']='winner'
    assert len(local_quality([baseline,conditional]))==2
    # Legacy mixed-world maxima exclude baseline; the production common
    # baseline guard must not reproduce that cross-world contamination.
    assert baseline[0]['projection']*6<.95*conditional[0]['projection']*6


def test_postgame_fields_cannot_influence_baseline_comparison():
    baseline=lineup('c',['a','b','d','e','f'],80,140,100)
    discovered=lineup('c',['a','b','d','e','f'],120,210,180)
    plain=baseline_rescore_discovery(discovered,lambda *_:deepcopy(baseline))
    for row in discovered:
        row['actual_fantasy_points']=1000000
        row['realized_ownership']=100
    adversarial=baseline_rescore_discovery(discovered,lambda *_:deepcopy(baseline))
    assert adversarial==plain
