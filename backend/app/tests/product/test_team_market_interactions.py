from copy import deepcopy
import pytest
from backend.app.product_services.team_market_interactions import build_team_market_interactions
from backend.app.product_services.environment_context_evidence import DEFINITIONS
from backend.app.product_services.workload_market_contexts import MARKET_VERSION


def fixture():
    lineage=dict(source=dict(snapshot_id='source',content_sha256='raw'),event_receipt_sha256='events')
    env=dict(version='environment_context_evidence_v1',before_period=202606,forecast=None,definitions=deepcopy(DEFINITIONS),semantic_measurements_sha256='environment',provenance=deepcopy(lineage),game_rows=[])
    official=dict(version='official_workload_components_v1',before_period=202606,forecast=None,pregame_serving_eligible=False,evidence_use='postlock_descriptive_not_pregame_or_serving',semantic_measurements_sha256='official',provenance=deepcopy(lineage),full_team_denominators=[])
    market=dict(version=MARKET_VERSION,before_period=202607,market_kind='revised_archived_intended_pregame_line',pregame_serving_eligible=False,evidence_use='postlock_descriptive_not_pregame_or_serving',semantic_sha256='market',provenance={},rows=[])
    for week in range(1,7):
        gid=f'2026_{week:02d}_WAS_SF'
        market['rows'].append(dict(game_id=gid,team='WAS',season=2026,week=week,game_total_line=40+week,team_spread_line=-week,team_implied_points=20+week))
        if week<6:
            env['game_rows'].append(dict(game_id=gid,team='WAS',season=2026,week=week,known_offensive_snaps=week*10,unknown_snap_eligibility=0,metrics={'G02-M01':dict(observed_outcome_sum=4+week,eligible_events=10,known_outcome_events=10,unknown_outcome_events=0,unknown_eligibility_events=0)}))
            official['full_team_denominators'].append(dict(game_id=gid,team='WAS',measurements={'official_carries':dict(exact_within_log_count=4*week,unknown_eligibility_events=0,unknown_outcome_events=0)}))
    return env,official,market


def run(args=None,**kwargs):return build_team_market_interactions(*(args or fixture()),before_period=202607,reference_before_period=202604,**kwargs)


def row(result,period=202604):return next(r for r in result['game_rows'] if r['period']==period)


def test_actual_centered_products_and_no_new_budget_or_response_claim():
    r=run();m=row(r)['metrics']
    assert m['X01-M01']['value']==15 and m['X01-M02']['value']==pytest.approx(-.15) and m['X01-M03']['value']==6
    assert all(v['not_a_physical_budget'] for v in m.values())
    assert r['reference']['means']['prior_physical_snaps_mean']==12.5 and r['reference']['known_reference_counts']['prior_physical_snaps_mean']==2
    assert r['pregame_serving_eligible'] is False and r['forecast'] is None


def test_reference_is_frozen_before_targets_and_target_workload_cannot_leak():
    args=fixture();original=run(args);args[0]['game_rows'][3]['known_offensive_snaps']=1000
    changed=run(args)
    assert changed['reference']==original['reference'] and row(changed)['metrics']==row(original)['metrics']
    assert row(changed,202605)['metrics']['X01-M01']!=row(original,202605)['metrics']['X01-M01']
    assert all(r['max_history_period']<r['period'] for r in changed['game_rows'])


def test_target_market_is_consumed_not_only_attached():
    args=fixture();old=run(args);args[2]['rows'][3].update(game_total_line=46,team_implied_points=25)
    new=run(args)
    assert row(new)['metrics']['X01-M01']['value']==30 and new['reference']==old['reference']
    assert row(new)['metrics']['X01-M03']['value']==9

@pytest.mark.parametrize('kind',['volume','rush','calls','missing_whole_game'])
def test_unknown_prior_parent_does_not_become_zero_or_skip_known_slot(kind):
    env,official,m=fixture()
    if kind=='volume':env['game_rows'][2]['unknown_snap_eligibility']=1
    elif kind=='rush':official['full_team_denominators'][2]['measurements']['official_carries']['exact_within_log_count']=None
    elif kind=='calls':env['game_rows'][2]['metrics']['G02-M01']['unknown_eligibility_events']=1
    else:env['game_rows'].pop(2);official['full_team_denominators'].pop(2)
    result=row(run((env,official,m)));mid={'volume':'X01-M01','rush':'X01-M03','calls':'X01-M02','missing_whole_game':'X01-M01'}[kind]
    assert result['metrics'][mid]['value'] is None and result['observed_prior_game_slots']==3


def test_all_missing_reference_is_null_never_imputed_zero():
    args=fixture()
    for r in args[1]['full_team_denominators']:r['measurements']['official_carries']['exact_within_log_count']=None
    r=run(args);assert r['reference']['means']['prior_official_carries_mean'] is None and r['reference']['known_reference_counts']['prior_official_carries_mean']==0
    assert all(g['metrics']['X01-M03']['value'] is None for g in r['game_rows'])


def test_pooled_called_pass_history_not_mean_game_fractions():
    args=fixture();a=args[0]['game_rows'][0]['metrics']['G02-M01'];a.update(observed_outcome_sum=1,eligible_events=1,known_outcome_events=1)
    target=row(run(args));assert target['parents']['prior_called_pass_fraction']==14/21


def test_known_zero_carries_stays_known_and_zero_centered_product_valid():
    args=fixture()
    for r in args[1]['full_team_denominators']:r['measurements']['official_carries']['exact_within_log_count']=0
    assert all(r['metrics']['X01-M03']['value']==0 for r in run(args)['game_rows'])


def test_source_row_order_and_provenance_clocks_not_independent_measurements():
    args=fixture();original=run(args)['semantic_sha256']
    for block,field in zip(args,('game_rows','full_team_denominators','rows')):block[field].reverse();block['provenance']['actual_read_at']='2026-10-20T01:00:00Z'
    assert run(args)['semantic_sha256']==original

@pytest.mark.parametrize('kind',['lineage','future_parent','duplicate','future_reference','implied','forecast','unknown_as_exact'])
def test_scope_identity_reference_and_unknown_contract_guards(kind):
    env,official,m=fixture()
    if kind=='lineage':official['provenance']['source']['content_sha256']='other'
    elif kind=='future_parent':env['game_rows'][0].update(game_id='2026_06_WAS_SF',week=6)
    elif kind=='duplicate':m['rows'].append(deepcopy(m['rows'][0]))
    elif kind=='future_reference':
        with pytest.raises(ValueError):build_team_market_interactions(env,official,m,before_period=202607,reference_before_period=202607)
        return
    elif kind=='implied':m['rows'][0]['team_implied_points']=99
    elif kind=='forecast':env['forecast']={'pass_attempts':30}
    else:official['full_team_denominators'][0]['measurements']['official_carries']['unknown_eligibility_events']=1
    with pytest.raises(ValueError):run((env,official,m))
