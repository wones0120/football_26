"""Deterministic controls tests. No current slate data or entry actions."""
from collections import Counter
from datetime import UTC, datetime
from itertools import combinations
from hashlib import sha256
from types import SimpleNamespace
import json
from pathlib import Path
import tarfile

import pandas as pd
import pulp
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.product_routes import router
from backend.app.product_dependencies import get_optimizer_service
from backend.app.product_schemas import OptimizerRunRequest
from backend.app.product_services.classic_prospective import classify_pool, validate_classic_run_input
from backend.app.product_services.classic_strategy_contract import build_strategy_contract, execute_strategy_contract, portfolio_audit, model_fingerprints, digest
from backend.app.product_services.classic_primary_game import primary_game_exposure
from backend.app.product_services.optimizer import OptimizerService
from backend.app.tests.product.test_classic_strategy_contract import pool, options


def fixture_contract(**controls):
    players = pool()
    classifications = {p.player_id: {'bucket': 'questionable_elevated' if p.position == 'WR' and p.team == 'AAA' else 'normal'} for p in players}
    return build_strategy_contract(players=players, pipeline_options=options(**controls),
        requested={'num_lineups': 5, 'max_exposure': .8, **controls}, metadata={}, risk_classifications=classifications)


def test_submission_diagnostics_use_server_values_without_running_optimizer():
    from sqlalchemy import select
    from backend.app.db import get_db_session
    from backend.app.models import OperationalJob
    from backend.app.product_services.classic_portfolio_controls import saved_portfolio_submission_trace
    from backend.app.tests.product.overlap_ui_fixture import fixture_app
    app = fixture_app()
    payload = {'season': 2000, 'week': 1, 'slate': 'SYNTHETIC',
               'strategy': 'classic_large_gpp_v1', 'contest_format': 'classic',
               'objective': 'gpp', 'optimizer_run_id': 'diagnostic-only',
               'params': {'max_lineup_overlap': 5, 'portfolio_submission_trace': {
                   'rendered_dropdown_value': 5, 'backend_parsed_request_value': 7,
                   'saved_contract_requested_value': 7}}}
    response = TestClient(app).post('/api/optimizer/jobs', json=payload)
    assert response.status_code == 202
    sessions = app.dependency_overrides[get_db_session]()
    try:
        db = next(sessions)
        job = db.scalar(select(OperationalJob).where(OperationalJob.run_id == 'diagnostic-only'))
        params = job.request_json['params']
        assert params['portfolio_submission_trace']['backend_parsed_request_value'] == 5
        assert params['portfolio_submission_trace']['rendered_dropdown_value'] == 5
        params['effective_strategy_contract'] = {'requested': {'max_lineup_overlap': 5}}
        assert saved_portfolio_submission_trace(params)['saved_contract_requested_value'] == 5
        assert saved_portfolio_submission_trace({}) is None
    finally:
        sessions.close()


@pytest.mark.parametrize('layer', ['requested', 'effective', 'sources', 'resolved_config'])
def test_explicit_request_cannot_silently_default_in_contract(layer):
    from backend.app.product_services.classic_portfolio_controls import validate_requested_overlap
    contract = fixture_contract(max_lineup_overlap=5)
    validate_requested_overlap({'max_lineup_overlap': 5}, contract)
    if layer == 'resolved_config':
        contract['effective']['resolved_config']['uniqueness_overlap'] = 7
    else:
        contract[layer]['max_lineup_overlap'] = 'strategy_default' if layer == 'sources' else None
    with pytest.raises(ValueError, match='overlap consistency failure'):
        validate_requested_overlap({'max_lineup_overlap': 5}, contract)


@pytest.mark.parametrize('cap', [4, 3, 2])
def test_explicit_primary_game_reaches_production_solver(cap):
    saved = fixture_contract(max_lineups_per_primary_game=cap)
    result = execute_strategy_contract(saved)
    assert result.status == 'completed'
    assert max(primary_game_exposure(result.lineups).values()) <= cap
    audit = portfolio_audit(saved, result.lineups, trace=result.selection_trace)
    row = next(row for row in audit['settings'] if row['key'] == 'max_lineups_per_primary_game')
    assert row['requested'] == row['effective'] == cap
    assert row['source'] == 'request'
    assert row['achieved'] == primary_game_exposure(result.lineups)


@pytest.mark.parametrize('overlap', [7, 6, 5, 4])
def test_explicit_overlap_overrides_legacy_uniqueness(overlap):
    saved = fixture_contract(max_lineup_overlap=overlap)
    result = execute_strategy_contract(saved)
    ids = [set(p.player_id for p in row) for row in result.lineups]
    assert result.config.uniqueness_overlap == overlap
    assert max((len(a & b) for a, b in combinations(ids, 2)), default=0) <= overlap
    audit = portfolio_audit(saved, result.lineups)
    assert audit['maximum_overlap'] <= overlap
    assert saved['effective']['resolved_config']['uniqueness_overlap'] == overlap
    assert saved['requested']['max_lineup_overlap'] == overlap
    assert saved['sources']['max_lineup_overlap'] == 'request'


@pytest.mark.parametrize('rate,limit', [(.8,4),(.6,3),(.4,2),(.2,1),(.5,2),(.19,0),(0,0)])
def test_explicit_elevated_exposure_uses_floor_and_keeps_global_caps(rate, limit):
    saved = fixture_contract(elevated_player_max_exposure=rate)
    result = execute_strategy_contract(saved)
    counts = Counter(p.player_id for row in result.lineups for p in row)
    elevated = saved['effective']['pipeline_options']['elevated_player_ids']
    assert max(counts.values(), default=0) <= 4
    assert all(counts[pid] <= limit for pid in elevated)
    audit = portfolio_audit(saved, result.lineups)
    assert all(row['limit'] == limit for row in audit['elevated_player_exposures'].values())
    assert audit['validation']['status'] == 'verified'


@pytest.mark.parametrize('limit', [0, 1, 2])
def test_per_lineup_elevated_constraint_is_separate(limit):
    saved = fixture_contract(max_elevated_players_per_lineup=limit)
    result = execute_strategy_contract(saved)
    audit = portfolio_audit(saved, result.lineups)
    assert max(audit['elevated_players_per_lineup'], default=0) <= limit
    assert saved['effective']['elevated_player_max_exposure'] is None
    assert audit['validation']['status'] == 'verified'


def test_combined_constraints_do_not_relax():
    saved = fixture_contract(max_lineups_per_primary_game=3, max_lineup_overlap=4,
        elevated_player_max_exposure=.4, max_elevated_players_per_lineup=1)
    result = execute_strategy_contract(saved)
    audit = portfolio_audit(saved, result.lineups, trace=result.selection_trace)
    assert result.status == 'completed'
    assert audit['validation']['status'] == 'verified'
    assert max(audit['canonical_primary_games'].values()) <= 3
    assert audit['maximum_overlap'] <= 4
    assert max(audit['elevated_players_per_lineup']) <= 1
    assert all(row['appearances'] <= 2 for row in audit['elevated_player_exposures'].values())


def test_infeasible_combination_reports_active_and_saturated_constraints():
    saved = fixture_contract(max_lineups_per_primary_game=1, max_lineup_overlap=4,
        elevated_player_max_exposure=0, max_elevated_players_per_lineup=0)
    result = execute_strategy_contract(saved)
    audit = portfolio_audit(saved, result.lineups, trace=result.selection_trace)
    assert result.status == 'failed' and len(result.lineups) < 5
    assert 'no limits relaxed' in result.message
    assert audit['feasibility']['status'] == 'underfilled'
    assert audit['feasibility']['no_constraints_relaxed'] is True
    assert audit['feasibility']['active_constraints']['max_lineup_overlap'] == 4
    assert audit['feasibility']['saturated_primary_games']
    assert audit['feasibility']['failed_solver_steps']
    assert audit['validation']['violations'] == ['entry_count']
    assert result.config.uniqueness_overlap == 4
    assert max(audit['canonical_primary_games'].values()) <= 1


def test_locked_elevated_player_never_overrides_explicit_risk_limit():
    with pytest.raises(ValueError, match='Minimum exposure exceeds'):
        execute_strategy_contract(fixture_contract(elevated_player_max_exposure=.4,
            minimum_exposure_by_player={'AAA-WR-0':1}, maximum_exposure_by_player={'AAA-WR-0':1}))


def test_missing_evidence_is_normal_and_doubtful_out_policy_is_not_imported():
    rows = [{'player_id':'none'}, {'player_id':'q','injury_status':'Q'}, {'player_id':'d','injury_status':'D'}, {'player_id':'out','injury_status':'OUT'}]
    risks = classify_pool(rows, datetime.now(UTC))
    assert [risks[row['player_id']]['bucket'] for row in rows] == ['normal','questionable_elevated','doubtful','out']
    players = pool()
    mapping = {p.player_id: risks['q' if p.player_id == 'AAA-WR-0' else 'd' if p.player_id == 'BBB-WR-0' else 'none'] for p in players}
    saved = build_strategy_contract(players=players, pipeline_options=options(elevated_player_max_exposure=.4),
        requested={'elevated_player_max_exposure':.4}, metadata={}, risk_classifications=mapping)
    assert saved['effective']['pipeline_options']['elevated_player_ids'] == ['AAA-WR-0']
    assert saved['effective']['eligible_player_ids'] == sorted(p.player_id for p in players)


def test_independent_audit_detects_slot_insensitive_overlap_and_risk_violations():
    saved = fixture_contract(max_lineup_overlap=4, elevated_player_max_exposure=.2, max_elevated_players_per_lineup=0)
    wanted = ['AAA-QB-0','AAA-RB-0','AAA-RB-1','AAA-WR-0','AAA-WR-1','AAA-WR-2','AAA-WR-3','AAA-TE-0','AAA-DST-0']
    lineup = [p for p in pool() if p.player_id in wanted]
    # Same IDs in a different ordering simulate FLEX/slot differences.
    audit = portfolio_audit(saved, [lineup, list(reversed(lineup))])
    assert audit['maximum_overlap'] == 9
    assert {'overlap','elevated_player_exposure','elevated_players_per_lineup'} <= set(audit['validation']['violations'])


@pytest.mark.parametrize('key,value', [('max_lineup_overlap',True),('max_lineup_overlap',9),('max_lineup_overlap',4.5),('max_elevated_players_per_lineup',-1),('max_elevated_players_per_lineup','1'),('elevated_player_max_exposure',float('nan')),('elevated_player_max_exposure',1.1),('elevated_player_max_exposure',True)])
def test_invalid_controls_rejected_before_queue(key,value):
    with pytest.raises(ValueError):
        OptimizerRunRequest(season=2026,week=4,slate='SUNDAY_MAIN',strategy='classic_large_gpp_v1',params={key:value})


def test_large_controls_cannot_leak_into_small_field_policy():
    for key,value in [('max_lineup_overlap',4),('elevated_player_max_exposure',.4),('max_elevated_players_per_lineup',0)]:
        with pytest.raises(ValueError,match='separate policy'):
            OptimizerRunRequest(season=2026,week=4,slate='SUNDAY_MAIN',strategy='classic_small_field_gpp',params={key:value})
    request = OptimizerRunRequest(season=2026,week=4,slate='SUNDAY_MAIN',strategy='classic_small_field_gpp',params={'portfolio_constraints':{'max_lineup_overlap':6}})
    assert request.params['portfolio_constraints']['max_lineup_overlap'] == 6


@pytest.mark.parametrize("underfilled", [False, True])
def test_saved_api_returns_all_requested_effective_sources_and_achieved_values(underfilled):
    saved = fixture_contract(max_lineup_overlap=4,elevated_player_max_exposure=.4,max_elevated_players_per_lineup=1,
        **({"max_lineups_per_primary_game":1} if underfilled else {}))
    result = execute_strategy_contract(saved)
    audit = portfolio_audit(saved,result.lineups,trace=result.selection_trace)
    app = FastAPI(); app.include_router(router)
    now = datetime.now(UTC)
    job = SimpleNamespace(job_id='saved',status=result.status,strategy='classic_large_gpp_v1',contest_format='classic',objective='gpp',
        params={'effective_strategy_contract':saved,'portfolio_controls_report':audit},projection_run_id='projection',rule_run_id=None,data_cutoff_at=now,
        lineage_persisted=True,message=result.message,results=None if underfilled else [],created_at=now,updated_at=now)
    app.dependency_overrides[get_optimizer_service] = lambda: SimpleNamespace(get_job=lambda job_id:job)
    response = TestClient(app).get('/api/optimizer/results/saved')
    assert response.status_code == 200
    assert response.json()['portfolio_controls_report']['settings'] == audit['settings']
    assert response.json()['effective_strategy_contract']['requested'] == saved['requested']
    assert response.json()['status'] == ('failed' if underfilled else 'completed')
    assert response.json()['portfolio_controls_report']['feasibility']['status'] == ('underfilled' if underfilled else 'complete')


def test_omitted_controls_preserve_immutable_rosters_and_scoring_with_stack_eligibility_guards():
    # Only the original no-cap baseline, never a sensitivity or user portfolio.
    root = Path(__file__).resolve().parents[4]
    archive_path = root/'artifacts/classic_large_gpp_parity/d0e2ff8f_evidence.tar.gz'
    manifest = json.loads((root/'artifacts/classic_large_gpp_parity/d0e2ff8f_manifest.json').read_text())
    assert sha256(archive_path.read_bytes()).hexdigest() == manifest["archive_sha256"]
    with tarfile.open(archive_path) as archive:
        def read(name):
            member = next(row for row in archive.getmembers() if row.name.endswith('/'+name) or row.name == name)
            return json.load(archive.extractfile(member))
        job = read('app_fixture.json'); baseline = read('baseline_replay.json')
    snapshot = job['params']['strategy_runtime']['classic_run_input_snapshot']
    validate_classic_run_input(snapshot)
    payload = snapshot['payload']; parameters = payload['parameters']
    players = OptimizerService._gpp_players_from_pool(pd.DataFrame(payload['final_solver_rows']))
    opts = dict(season=job['season'],week=job['week'],slate=job['slate'],num_lineups=5,max_exposure=.8,
        ownership_available=True,large_gpp=True,enforce_single_te=parameters['enforce_single_te'],avoid_dst_opponents=parameters['avoid_dst_opponents'],
        minimum_uniqueness=parameters['minimum_uniqueness'],max_from_team=parameters['max_players_per_team'],max_from_game=parameters['max_players_per_game'],
        stack_templates=parameters.get('stack_templates'),maximum_exposure_by_player={},minimum_exposure_by_player={},
        include_control_comparisons=False,long_shot_mode=False,candidate_aware_ownership=False,solver_backend='bundled',precompute_correlation_terms=False,maximum_player_groups=None)
    saved = build_strategy_contract(players=players,pipeline_options=opts,requested=parameters,metadata={},mode='PARITY',
        risk_classifications=classify_pool(payload['final_solver_rows'],datetime.fromisoformat(job['data_cutoff_at'])))
    result = execute_strategy_contract(saved)
    assert result.status == 'completed' and len(result.lineups) == 5
    assert digest(saved['effective']['resolved_config']) == digest(job['params']['strategy_runtime']['config'])
    assert saved['effective']['eligible_player_ids'] == sorted(row['player_id'] for row in payload['final_solver_rows'])
    assert saved['effective']['pipeline_options']['max_lineups_per_primary_game'] is None
    assert saved['effective']['elevated_player_max_exposure'] is None
    assert saved['sources']['max_lineup_overlap'] == 'strategy_default'
    expected = [sorted(p['player_id'] for p in row) for row in job['results']]
    assert [sorted(p.player_id for p in row) for row in result.lineups] == expected
    audit = portfolio_audit(saved,result.lineups,trace=result.selection_trace)
    assert audit['validation']['status'] == 'verified'
    for index,(step,row) in enumerate(zip(result.selection_trace,job['results'])):
        replay = row[0]['lineup_control_comparison']['replay']
        old_model = pulp.LpProblem.fromDict(replay['model'])[1]
        # The construction audit closes the old empty-eligible-set bypass.
        # Model parity differs only by explicit guards for QBs unable to meet
        # this step's requested minimum. Archived selected rosters stay identical.
        for player_index, qb in enumerate(players):
            if qb.position != 'QB':
                continue
            for label, minimum, team, positions in (
                ('pass_catcher', step['stack_template'][0], qb.team, {'WR', 'TE'}),
                ('bring_back', step['stack_template'][1], qb.opponent, {'RB', 'WR', 'TE'}),
            ):
                if minimum > 0 and not any(p.team == team and p.position in positions for p in players):
                    old_model += old_model.variablesDict()[f'p_{player_index}'] == 0, f'missing_{label}_{player_index}'
        assert step['feasible_region_sha256'] == model_fingerprints(old_model)['feasible_region_sha256']
        old_model.setObjective(pulp.lpSum(term['value']*old_model.variablesDict()[term['name']] for term in baseline['steps'][index]['objective_coefficients']))
        assert step['objective_sha256'] == model_fingerprints(old_model)['objective_sha256']
        assert abs(step['objective_score']-replay['scored_objective']) < 1e-9
        assert abs(audit['candidate_rosters'][index]['objective_score']-replay['scored_objective']) < 1e-9


def test_fractional_exposure_floor_handles_decimal_boundaries():
    from backend.app.product_services.classic_portfolio_controls import explicit_appearance_limit
    assert explicit_appearance_limit(50, .58) == 29
    assert explicit_appearance_limit(5, .555) == 2
    assert explicit_appearance_limit(3, .4) == 1


def test_elevated_limit_intersects_stricter_individual_cap():
    saved = fixture_contract(elevated_player_max_exposure=.8,
        maximum_exposure_by_player={"AAA-WR-0":.2})
    result = execute_strategy_contract(saved)
    audit = portfolio_audit(saved,result.lineups)
    assert audit["elevated_player_exposures"]["AAA-WR-0"]["limit"] == 1
    assert audit["elevated_player_exposures"]["AAA-WR-0"]["appearances"] <= 1
    assert audit["validation"]["status"] == "verified"
