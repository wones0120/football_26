from collections import Counter
from dataclasses import replace
from types import SimpleNamespace
from datetime import UTC, datetime
import json

import pytest
import pulp
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.product_services.classic_primary_game import canonical_primary_game, resolve_primary_game_cap, primary_game_exposure
from backend.app.product_services.classic_strategy_contract import build_strategy_contract, execute_strategy_contract, portfolio_audit, validate_strategy_contract, model_fingerprints, digest
from backend.app.product_services.gpp_optimizer import Player, generate_portfolio, build_large_gpp_config
from backend.app.product_schemas import OptimizerRunRequest
from backend.app.product_dependencies import get_optimizer_service
from backend.app.api.product_routes import router


def pool():
    players=[]
    teams=['AAA','BBB','CCC','DDD','EEE','FFF']
    for n,team in enumerate(teams):
        opponent=teams[n^1]
        for position,count in [('QB',1),('RB',3),('WR',5),('TE',2),('DST',1)]:
            for k in range(count):
                mean=30-n if position=='QB' else 12+((n*13+k*7)%11)/10
                players.append(Player(player_id=f'{team}-{position}-{k}',name=f'{team} {position} {k}',
                    team=team,opponent=opponent,position=position,salary=4000,
                    projection=mean,ceiling=mean+15,ownership=None))
    return players


def options(**changes):
    return dict(season=2026,week=4,slate='SUNDAY_MAIN',num_lineups=5,max_exposure=.8,
        ownership_available=False,large_gpp=True,minimum_uniqueness=2,include_control_comparisons=False,**changes)


def contract(**changes):
    return build_strategy_contract(players=pool(),pipeline_options=options(**changes),requested={},metadata={})


@pytest.mark.parametrize('value',[0,-1,True,False,2.0,'3'])
def test_cap_rejects_non_positive_integers(value):
    with pytest.raises(ValueError):resolve_primary_game_cap(value)
    with pytest.raises(ValueError):OptimizerRunRequest(season=2026,week=4,slate='SUNDAY_MAIN',
        strategy='classic_large_gpp_v1',params={'max_lineups_per_primary_game':value})


def test_canonical_identity_is_direction_and_case_independent():
    assert canonical_primary_game(' jax ','cin')==canonical_primary_game('CIN','JAX')=='CIN-JAX'
    with pytest.raises(ValueError):canonical_primary_game('JAX','JAX')


def test_serialized_contract_replays_same_default_and_preserves_80_percent():
    saved=json.loads(json.dumps(contract()))
    replay=execute_strategy_contract(saved)
    original=generate_portfolio(players=pool(),config_builder=build_large_gpp_config,**{k:v for k,v in options().items() if k!='large_gpp'})
    assert replay.status==original.status=='completed'
    assert [[p.player_id for p in row] for row in replay.lineups]==[[p.player_id for p in row] for row in original.lineups]
    audit=portfolio_audit(saved,replay.lineups)
    assert audit['validation']['status']=='verified'
    assert max(row['appearances'] for row in audit['player_exposures'].values())<=4
    assert all(row['limit']==4 for row in audit['player_exposures'].values())
    assert saved['effective']['max_lineups_per_primary_game'] is None
    assert saved['sources']['max_lineups_per_primary_game']=='strategy_default_no_limit'
    assert len(saved['effective']['eligible_player_ids'])==len(pool())


def test_cap_blocks_both_qb_directions_and_does_not_relax_player_exposure():
    saved=contract(max_lineups_per_primary_game=2)
    result=execute_strategy_contract(saved)
    assert result.status=='completed' and len(result.lineups)==5
    assert max(primary_game_exposure(result.lineups).values())<=2
    assert max(Counter(p.player_id for row in result.lineups for p in row).values())<=4
    assert any(step['blocked_primary_games'] for step in result.selection_trace)
    for step in result.selection_trace:
        for key in step['blocked_primary_games']:
            qb=next(p for p in pool() if p.player_id in step['player_ids'] and p.position=='QB')
            assert canonical_primary_game(qb.team,qb.opponent)!=key


def test_infeasible_cap_does_not_relax_or_report_a_full_portfolio():
    saved=contract(max_lineups_per_primary_game=1)
    result=execute_strategy_contract(saved)
    assert result.status=='failed' and len(result.lineups)<5
    assert max(primary_game_exposure(result.lineups).values(),default=0)<=1
    assert 'entry_count' in portfolio_audit(saved,result.lineups)['validation']['violations']


def test_checksum_and_mode_guard_against_silent_research():
    saved=contract();saved['effective']['pipeline_options']['max_exposure']=1
    with pytest.raises(ValueError,match='checksum'):validate_strategy_contract(saved)
    with pytest.raises(ValueError,match='RESEARCH_SHADOW'):
        build_strategy_contract(players=pool(),pipeline_options=options(),requested={},metadata={},mode='PARITY',deviations=['expanded'])
    with pytest.raises(ValueError,match='RESEARCH_SHADOW'):
        build_strategy_contract(players=pool(),pipeline_options=options(),requested={},metadata={},mode='RESEARCH_SHADOW')
    with pytest.raises(ValueError,match='RESEARCH_SHADOW'):
        OptimizerRunRequest(season=2026,week=4,slate='SUNDAY_MAIN',strategy='classic_large_gpp_v1',params={'classic_expanded_discovery':True})


def test_model_fingerprint_compares_actual_coefficients_and_bounds():
    model=pulp.LpProblem('a',pulp.LpMaximize);x=pulp.LpVariable('x',0,1,cat='Binary')
    model+=2*x;model+=x<=1
    copy=pulp.LpProblem.fromDict(model.toDict())[1]
    assert model_fingerprints(model)==model_fingerprints(copy)
    copy.constraints['_C1'].constant=-.5
    assert model_fingerprints(model)['feasible_region_sha256']!=model_fingerprints(copy)['feasible_region_sha256']


def test_saved_result_api_retains_cap_contract_and_achieved_counts():
    app=FastAPI();app.include_router(router)
    now=datetime.now(UTC);saved=contract(max_lineups_per_primary_game=3)
    concentration={'requested':3,'effective':3,'source':'request','achieved_game_exposure':{'CIN-JAX':3,'DAL-HOU':2},'validation':'verified'}
    job=SimpleNamespace(job_id='saved',status='completed',strategy='classic_large_gpp_v1',
        contest_format='classic',objective='gpp',params={'effective_strategy_contract':saved,'primary_game_constraint':concentration},
        projection_run_id='projection',rule_run_id=None,data_cutoff_at=now,lineage_persisted=True,
        message='Saved',results=[],created_at=now,updated_at=now)
    app.dependency_overrides[get_optimizer_service]=lambda:SimpleNamespace(get_job=lambda job_id:job)
    response=TestClient(app).get('/api/optimizer/results/saved')
    assert response.status_code==200
    assert response.json()['effective_strategy_contract']==json.loads(json.dumps(saved))
    assert response.json()['primary_game_constraint']==concentration



def test_unspecified_ownership_does_not_enable_long_shot_weights():
    players = [replace(p, ownership=8.0) for p in pool()]
    result = generate_portfolio(season=2026, week=4, slate="SUNDAY_MAIN", num_lineups=1,
        players=players, config_builder=build_large_gpp_config, ownership_available=None,
        long_shot_mode=True, include_control_comparisons=False)
    assert result.config.objective_weights.projection == .35
    assert result.config.objective_weights.ceiling == .48
    assert result.config.objective_weights.leverage == 0


def test_small_field_cap_counts_opposite_qbs_in_one_canonical_game():
    from backend.app.product_services.classic_small_field import _select_global
    candidates = [
        {"player_ids": [f"a-{i}" for i in range(9)], "qb": {"player_id": "qa", "team": "JAX", "opponent": "CIN"}, "objective_score": 10},
        {"player_ids": [f"b-{i}" for i in range(9)], "qb": {"player_id": "qb", "team": "CIN", "opponent": "JAX"}, "objective_score": 9},
        {"player_ids": [f"c-{i}" for i in range(9)], "qb": {"player_id": "qc", "team": "DAL", "opponent": "HOU"}, "objective_score": 8},
    ]
    selected = _select_global(candidates, 2, 1, set(), {}, {}, max_lineup_overlap=7, canonical_game_cap=1)
    assert set(selected) == {0, 2}
    assert set(_select_global(candidates, 2, 1, set(), {}, {}, canonical_game_cap=8)) == {0, 1}
