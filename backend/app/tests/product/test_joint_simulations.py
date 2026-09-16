from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest
from fastapi import HTTPException

from backend.app.product_services.joint_simulations import (
    FactorPrior, sample_joint_outcomes, lineup_distribution, evaluate_experiment,
    replay_experiment, save_experiment, run_joint_research,
)
from backend.app.product_schemas import JointResearchRequest
from backend.app.api.product_routes import run_joint_simulation_research


def pool():
    positions = ['QB', 'WR', 'WR', 'TE', 'RB', 'RB', 'RB', 'WR', 'DST', 'TE']
    return pd.DataFrame([
        {'player_id': f'p{i:02}', 'position': pos, 'team_id': 'A' if i < 8 else 'B',
         'opponent_team_id': 'B' if i < 8 else 'A', 'game_id': 'canonical-game-1',
         'salary': 4000, 'projection_mean': 20,
         'projection_p10': 5, 'projection_p25': 12, 'projection_p50': 20,
         'projection_p75': 28, 'projection_p90': 35}
        for i, pos in enumerate(positions)])


def lineups(frame):
    scored = frame.iloc[:9].to_dict('records')
    control = frame.iloc[:9].copy().to_dict('records')
    scored[0]['lineup_control_comparison'] = {'control_lineup': control}
    return [scored]


def test_joint_sampler_preserves_exact_marginals_and_canonical_order():
    frame, independent, joint, evidence = sample_joint_outcomes(pool(), num_simulations=20000, seed=603)
    assert np.array_equal(np.sort(independent, axis=0), np.sort(joint, axis=0))
    reordered = sample_joint_outcomes(pool().iloc[::-1], num_simulations=20000, seed=603)[2]
    assert np.array_equal(joint, reordered)
    assert evidence['marginals_preserved_exactly']
    # Shared offense rises together; opposing DST moves against the QB.
    assert np.corrcoef(joint[:, 0], joint[:, 1])[0, 1] > .25
    assert np.corrcoef(joint[:, 0], joint[:, 8])[0, 1] < -.15
    assert abs(np.corrcoef(independent[:, 0], independent[:, 1])[0, 1]) < .04


def test_different_games_remain_independent_and_missing_identity_fails():
    frame = pool()
    frame.loc[1, ['team_id', 'opponent_team_id', 'game_id']] = ['C', 'D', 'canonical-game-2']
    joint = sample_joint_outcomes(frame, num_simulations=20000, seed=603)[2]
    assert abs(np.corrcoef(joint[:, 0], joint[:, 1])[0, 1]) < .04
    frame.loc[1, 'game_id'] = ''
    with pytest.raises(ValueError, match='canonical game_id'):
        sample_joint_outcomes(frame, num_simulations=100, seed=603)


def test_invalid_quantiles_duplicate_ids_and_factor_variance_fail():
    frame = pool()
    frame.loc[0, 'projection_p90'] = 1
    with pytest.raises(ValueError, match='quantiles'):
        sample_joint_outcomes(frame, num_simulations=100, seed=1)
    frame = pool()
    frame.loc[1, 'player_id'] = frame.loc[0, 'player_id']
    with pytest.raises(ValueError, match='Duplicate'):
        sample_joint_outcomes(frame, num_simulations=100, seed=1)
    with pytest.raises(ValueError, match='variance'):
        sample_joint_outcomes(pool(), num_simulations=100, seed=1, prior=replace(FactorPrior(), team_passing=1))


def test_lineup_quantiles_are_joint_and_captain_applies_once():
    frame, independent, joint, _ = sample_joint_outcomes(pool(), num_simulations=20000, seed=3)
    scored = frame.iloc[:9].to_dict('records')
    _, summary = lineup_distribution(joint, frame, scored, contest_format='classic')
    assert summary['p90'] == pytest.approx(np.quantile(joint[:, :9].sum(axis=1), .9))
    assert summary['p90'] != pytest.approx(sum(np.quantile(joint[:, :9], .9, axis=0)))
    showdown = frame.iloc[:6].to_dict('records')
    for i, row in enumerate(showdown):
        row['roster_position'] = 'CPT' if i == 0 else 'FLEX'
    totals, summary = lineup_distribution(joint, frame, showdown, contest_format='showdown', threshold=150)
    assert np.array_equal(totals, joint[:, 0]*1.5 + joint[:, 1] + joint[:, 2] + joint[:, 3] + joint[:, 4] + joint[:, 5])
    assert 0 <= summary['probability_at_or_above_threshold'] <= 1
    with pytest.raises(ValueError, match='missing'):
        showdown[0]['player_id'] = 'not-in-snapshot'
        lineup_distribution(joint, frame, showdown, contest_format='showdown')


def test_same_lineup_controls_have_zero_paired_variance_and_replay(tmp_path):
    result = evaluate_experiment(pool(), lineage={'contest_format': 'classic'}, lineups=lineups(pool()), num_simulations=1000)
    for mode in ('independent', 'joint'):
        comparison = result['comparisons'][0][mode]
        assert comparison['paired_mean_delta'] == 0
        assert comparison['paired_mean_mc_standard_error'] == 0
        assert comparison['probability_tie'] == 1
    assert not result['performance_claim_eligible']
    assert not result['production_promotion_eligible']
    assert replay_experiment(result) == result
    first = save_experiment(result, tmp_path)
    assert save_experiment(result, tmp_path) == first
    assert len(list(tmp_path.glob('*.json'))) == 1
    result['replay_inputs']['seed'] += 1
    with pytest.raises(ValueError, match='checksum'):
        replay_experiment(result)


def services():
    source = SimpleNamespace(season=2026, week=1, slate='SUNDAY_MAIN', contest_format='classic',
                             projection_run_id='projection-1', data_cutoff_at=datetime(2026, 9, 13, 16, tzinfo=timezone.utc))
    job = SimpleNamespace(**source.__dict__, status='completed', results=lineups(pool()))
    simulation, optimizer = Mock(), Mock()
    simulation.fetch_by_id.return_value = source
    simulation._load_persisted_pool.return_value = pool()
    optimizer.get_job.return_value = job
    return simulation, optimizer, source, job


def test_research_service_checks_exact_lineage_and_cutoff(tmp_path):
    simulation, optimizer, source, job = services()
    result = run_joint_research(simulation, optimizer, simulation_run_id='sim-1', optimizer_run_id='opt-1', num_simulations=100, artifact_root=tmp_path)
    assert result['comparisons']
    job.projection_run_id = 'later-projections'
    with pytest.raises(ValueError, match='lineage'):
        run_joint_research(simulation, optimizer, simulation_run_id='sim-1', optimizer_run_id='opt-1', artifact_root=tmp_path)
    source.data_cutoff_at = None
    with pytest.raises(ValueError, match='no cutoff'):
        run_joint_research(simulation, optimizer, simulation_run_id='sim-1', artifact_root=tmp_path)
    result = run_joint_research(simulation, optimizer, simulation_run_id='sim-1', allow_missing_cutoff=True, num_simulations=100, artifact_root=tmp_path)
    assert result['lineage']['cutoff_status'] == 'missing_exploratory_only'
    assert not result['production_promotion_eligible']


def test_api_returns_actionable_validation_errors():
    simulation, optimizer, source, job = services()
    source.data_cutoff_at = None
    with pytest.raises(HTTPException) as failure:
        run_joint_simulation_research(JointResearchRequest(simulation_run_id='sim-1'), simulation, optimizer)
    assert failure.value.status_code == 422
    assert 'cutoff' in failure.value.detail


def test_signed_dst_marginals_are_retained_without_mutating_source():
    frame = pool()
    frame.loc[8, list(frame.columns[frame.columns.str.startswith('projection_')])] = [0, -4, -2, 0, 2, 4]
    original = frame.copy(deep=True)
    _, independent, joint, diagnostic = sample_joint_outcomes(frame, num_simulations=1000, seed=10)
    assert (joint[:, 8] < 0).any()
    assert np.array_equal(np.sort(joint[:, 8]), np.sort(independent[:, 8]))
    assert diagnostic['negative_outcomes_retained'] > 0
    pd.testing.assert_frame_equal(original, frame)


def test_different_controls_use_the_same_player_draws():
    frame = pool()
    pairs = lineups(frame)
    pairs[0][3] = frame.iloc[9].to_dict()
    result = evaluate_experiment(frame, lineage={'contest_format': 'classic'}, lineups=pairs, num_simulations=1000, seed=11)
    _, _, draws, _ = sample_joint_outcomes(frame, num_simulations=1000, seed=11)
    differences = draws[:, 9] - draws[:, 3]
    comparison = result['comparisons'][0]['joint']
    assert comparison['paired_mean_delta'] == pytest.approx(differences.mean())
    assert comparison['paired_mean_mc_standard_error'] == pytest.approx(differences.std(ddof=1) / np.sqrt(1000))


def test_missing_controls_and_api_success(monkeypatch, tmp_path):
    from backend.app.product_services import joint_simulations
    simulation, optimizer, source, job = services()
    original = joint_simulations.save_experiment
    monkeypatch.setattr(joint_simulations, 'save_experiment', lambda report, root: original(report, tmp_path))
    result = run_joint_simulation_research(
        JointResearchRequest(simulation_run_id='sim-1', optimizer_run_id='opt-1', num_simulations=100), simulation, optimizer)
    assert result['status'] == 'completed_research'
    assert result['comparisons'][0]['joint']['probability_tie'] == 1
    job.results[0][0].pop('lineup_control_comparison')
    with pytest.raises(HTTPException) as failure:
        run_joint_simulation_research(JointResearchRequest(simulation_run_id='sim-1', optimizer_run_id='opt-1', num_simulations=100), simulation, optimizer)
    assert failure.value.status_code == 422
    assert 'OPT-007' in failure.value.detail
