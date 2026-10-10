"""Shared-format simulation correctness and immutable replay contracts."""
from datetime import datetime, timezone
from itertools import combinations
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
import pytest

from backend.app.product_services.simulations import (
    SimulationService, build_simulation_rows, simulate_showdown_lineups,
)
from backend.app.tests.product.test_simulations import classic_pool


def showdown_pool():
    pool = classic_pool().iloc[:8].copy()
    pool['team_id'] = ['A'] * 6 + ['B'] * 2
    pool['opponent_team_id'] = ['B'] * 6 + ['A'] * 2
    pool['game_id'] = 'game-1'
    pool['salary'] = [12000, 10000, 9000, 8000, 7000, 4000, 200, 4000]
    pool['captain_salary'] = pool['salary'] * 1.5
    pool.loc[6, 'position'] = 'K'
    return pool


def test_captain_solver_matches_exhaustive_legal_roster_oracle():
    pool = showdown_pool()
    draws = np.array([[40, 30, 25, 20, 15, 8, 2, 6], [5, 6, 7, 8, 9, 10, 15, 40]], dtype=float)
    expected, expected_captains = np.zeros(len(pool), int), np.zeros(len(pool), int)
    for draw in draws:
        legal = []
        for captain in range(len(pool)):
            for flex in combinations([i for i in range(len(pool)) if i != captain], 5):
                chosen = [captain, *flex]
                if pool.iloc[chosen].team_id.nunique() != 2:
                    continue
                if pool.iloc[captain].captain_salary + pool.iloc[list(flex)].salary.sum() > 50000:
                    continue
                tie = (2 * len(pool) - captain + sum(len(pool) - i for i in flex)) * 1e-9
                legal.append((draw[captain] * 1.5 + draw[list(flex)].sum() + tie, captain, chosen))
        _, captain, chosen = max(legal)
        expected[chosen] += 1
        expected_captains[captain] += 1
    with patch('backend.app.product_services.simulations.sample_independent_outcomes', return_value=draws) as sampler:
        counts, captains, successful = simulate_showdown_lineups(pool, num_simulations=2, seed=7)
    assert successful == 2
    np.testing.assert_array_equal(counts, expected)
    np.testing.assert_array_equal(captains, expected_captains)
    assert sampler.call_count == 1  # Physical outcomes are shared, never redrawn for CPT.


def test_showdown_seed_and_role_accounting_round_trip():
    pool = showdown_pool()
    counts, captains, successful = simulate_showdown_lineups(pool, num_simulations=8, seed=7)
    again = simulate_showdown_lineups(pool, num_simulations=8, seed=7)
    assert successful == 8
    np.testing.assert_array_equal(counts, again[0])
    np.testing.assert_array_equal(captains, again[1])
    assert counts.sum() == 6 * successful
    assert captains.sum() == successful
    rows = build_simulation_rows(pool, counts, successful_simulations=successful, captain_counts=captains)
    assert sum(r['captain_optimal_probability'] for r in rows) == pytest.approx(100)
    assert sum(r['flex_optimal_probability'] for r in rows) == pytest.approx(500)
    for row in rows:
        restored = SimulationService._public_player_result({
            'player_id': row['player_id'], 'result_json': {k: v for k, v in row.items() if k.startswith(('captain_', 'flex_'))}})
        assert restored['captain_optimal_count'] == row['captain_optimal_count']
        assert restored['captain_salary'] == row['captain_salary']


@pytest.mark.parametrize('problem', ['duplicate', 'teams', 'game', 'salary'])
def test_showdown_rejects_incompatible_scope_and_slot_evidence(problem):
    pool = showdown_pool()
    if problem == 'duplicate':
        pool.loc[1, 'player_id'] = pool.loc[0, 'player_id']
    elif problem == 'teams':
        pool['team_id'] = 'A'
    elif problem == 'game':
        pool.loc[0, 'game_id'] = 'another-game'
    else:
        pool.loc[0, 'captain_salary'] = np.nan
    with pytest.raises(ValueError):
        simulate_showdown_lineups(pool, num_simulations=1, seed=7)


def test_infeasible_showdown_does_not_relax_salary_cap():
    counts, captains, successful = simulate_showdown_lineups(showdown_pool(), num_simulations=1, seed=7, salary_cap=100)
    assert successful == 0
    assert counts.sum() == captains.sum() == 0


@pytest.mark.parametrize('slate,format', [
    ('SUNDAY_MAIN', 'classic'), ('SUNDAY_EARLY', 'classic'), ('SUNDAY_LATE', 'classic'),
    ('THURSDAY_NIGHT', 'showdown'), ('SUNDAY_NIGHT', 'showdown'), ('MONDAY_NIGHT', 'showdown'),
    ('SUNDAY_NIGHT_GAME_2', 'showdown'),
])
def test_run_uses_shared_format_path_and_rejects_cross_scope_retries(slate, format):
    service = SimulationService.__new__(SimulationService)
    pool = showdown_pool() if format == 'showdown' else classic_pool()
    service._load_pool = Mock(return_value=(pool, 'projection-1', None, datetime.now(timezone.utc)))
    service._persist = Mock()
    service.fetch_by_id = Mock(return_value=None)
    result = service.run(season=2026, week=5, slate=slate, contest_format=format,
                         num_simulations=2, simulation_run_id='sim-1')
    assert result.contest_format == format
    assert result.slate == slate
    assert service._load_pool.call_args.kwargs['contest_format'] == format
    assert sum(r['optimal_lineup_count'] for r in result.rows) == 2 * (6 if format == 'showdown' else 9)
    assert 'not GPP paid-finish' in result.message
    service.fetch_by_id.return_value = result
    assert service.run(season=2026, week=5, slate=slate, contest_format=format,
                       num_simulations=2, simulation_run_id='sim-1') is result
    with pytest.raises(ValueError, match='different scope'):
        service.run(season=2026, week=5, slate='DIFFERENT', contest_format=format,
                    num_simulations=2, simulation_run_id='sim-1')
