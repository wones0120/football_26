from itertools import combinations

import pandas as pd
import pytest

from backend.app.product_services.optimizer import OptimizerService
from backend.app.product_services.showdown_captain_shortlist import build_captain_shortlist, POLICY_ID
from backend.app.tests.product.test_showdown_qb_preferences import service, offline_strategy_inputs


def players():
    return pd.DataFrame([
        dict(player_id=f'id-{i}', name=f'Player {i}', position='WR',
             player_team='AAA' if i % 2 == 0 else 'BBB',
             opponent_team='BBB' if i % 2 == 0 else 'AAA',
             salary=5000, projection=mean, p90=p90)
        for i, (mean, p90) in enumerate([(10, 40), (20, 35), (19, 30), (18, 25),
                                         (22, 24), (21, 23), (1, 22), (2, 21)])
    ])


def solve(pool, **kwargs):
    return OptimizerService.__new__(OptimizerService)._solve_lineup(
        pool, contest_type='captain', include_control_comparison=False, **kwargs)


def test_ranking_is_global_raw_p90_and_ties_use_canonical_ids():
    pool = players()
    pool.loc[pool.player_id.isin(['id-3', 'id-4']), 'p90'] = 25
    pool['captain_objective_multiplier'] = [1, 1, 1, 1, 100, 1, 1, 1]
    pool['optimizer_context_ceiling_score'] = 999
    before = pool.copy(deep=True)
    _, report = build_captain_shortlist(pool.sample(frac=1, random_state=4), params={}, flex_only_ids=set())
    assert [r['player_id'] for r in report['shortlist']] == ['id-0', 'id-1', 'id-2', 'id-3']
    assert {r['team'] for r in report['shortlist']} == {'AAA', 'BBB'}
    assert report['shortlist'][0]['pregame_p90'] == 40
    assert report['exclusions'][0]['exclusions'][0]['reason_code'] == 'outside_top_four_p90'
    pd.testing.assert_frame_equal(before, pool)


def test_preferences_filter_eligibility_without_changing_model_rank_or_flex():
    pool = players()
    pool.loc[0, 'position'] = 'QB'
    before = pool.copy(deep=True)
    frame, report = build_captain_shortlist(pool, params={'no_qb_captain': True}, flex_only_ids={'id-1'})
    assert [r['player_id'] for r in report['shortlist']] == ['id-2', 'id-3', 'id-4', 'id-5']
    assert report['shortlist'][0]['model_p90_rank'] == 3
    assert report['exclusions'][0]['exclusions'][0]['category'] == 'user_preference'
    assert len(frame) == len(pool)
    pd.testing.assert_frame_equal(pool, before)


def test_solver_enforces_shortlist_and_uses_mean_for_unrestricted_flex():
    pool = players()
    # Deliberately misleading legacy score and captain prior cannot affect objective.
    pool['legacy_score'] = [1, 1, 1, 1, 1, 1, 9999, 9999]
    pool['captain_objective_multiplier'] = [1, 1, 1, 1, 100, 100, 100, 100]
    before = pool.copy(deep=True)
    lineup = solve(pool, score_col='legacy_score')
    captain = next(row for row in lineup if row['roster_position'] == 'CPT')
    flex = [row for row in lineup if row['roster_position'] == 'FLEX']
    assert captain['player_id'] == 'id-0'
    assert {r['player_id'] for r in flex} == {'id-1', 'id-2', 'id-3', 'id-4', 'id-5'}
    assert captain['objective_score'] == 1.5 * 40
    assert captain['salary'] == 1.5 * 5000
    assert all(r['objective_score'] == r['base_projection'] for r in flex)
    assert all(r['salary'] == r['base_salary'] for r in flex)
    assert lineup[0]['solver_objective_value'] == 160
    assert solve(pool, locked_captain_player_id='id-4') is None
    pd.testing.assert_frame_equal(pool, before)


def test_salary_multiplier_is_enforced_by_solver_and_matches_exhaustive_optimum():
    pool = players()
    pool['salary'] = [12000, 9000, 8500, 8000, 7000, 6500, 3000, 2000]
    lineup = solve(pool)
    candidates = []
    for captain in range(4):
        for flex in combinations([i for i in range(len(pool)) if i != captain], 5):
            chosen = [captain, *flex]
            if max(pool.iloc[chosen].player_team.value_counts()) > 5:
                continue
            salary = pool.iloc[captain].salary * 1.5 + pool.iloc[list(flex)].salary.sum()
            if salary <= 50000:
                candidates.append(pool.iloc[captain].p90 * 1.5 + pool.iloc[list(flex)].projection.sum())
    assert sum(r['salary'] for r in lineup) <= 50000
    assert len(lineup) == len({r['player_id'] for r in lineup}) == 6
    assert lineup[0]['solver_objective_value'] == max(candidates)


def test_frozen_shortlist_does_not_promote_fifth_player_when_captains_exhausted():
    frame, _ = build_captain_shortlist(players(), params={}, flex_only_ids=set())
    frame['p90'] = list(reversed(frame.p90.tolist()))
    assert solve(frame, captain_exposure_remaining={f'id-{i}': 0 for i in range(4)}) is None
    assert solve(frame[frame.player_id != 'id-0'], locked_captain_player_id='id-4') is None


@pytest.mark.parametrize('size', [0, 1, 3])
def test_short_pool_does_not_pad_shortlist(size):
    _, report = build_captain_shortlist(players().iloc[:size], params={}, flex_only_ids=set())
    assert len(report['shortlist']) == size


def test_missing_p90_is_reported_and_does_not_change_flex_eligibility():
    pool = players()
    pool.loc[0, 'p90'] = float('nan')
    frame, report = build_captain_shortlist(pool, params={}, flex_only_ids=set())
    assert len(frame) == len(pool)
    excluded = next(r for r in report['exclusions'] if r['player_id'] == 'id-0')
    assert excluded['exclusions'][0]['reason_code'] == 'missing_finite_pregame_p90'


@pytest.mark.parametrize('strategy,objective', [
    ('showdown_cash_baseline_v1', 'cash'),
    ('showdown_gpp_portfolio_v3', 'gpp'),
    ('captain_single_lineup_v1', 'cash'),
])
def test_job_persists_shortlist_exclusions_and_model_values(strategy, objective):
    optimizer = service()
    original = optimizer._load_player_pool.return_value.copy(deep=True)
    job = optimizer.run_job(season=2026, week=4, slate='THURSDAY_NIGHT',
        strategy=strategy, contest_format='showdown', objective=objective,
        allow_incomplete_evidence=strategy == 'captain_single_lineup_v1',
        params={'num_lineups': 1, 'captain_positions': ['WR', 'RB']})
    assert job.status == 'completed', job.message
    report = job.params['strategy_runtime']['showdown_captain_shortlist']
    assert len(report['shortlist']) == 4
    assert report['policy_id'] == POLICY_ID
    assert job.results[0][0]['showdown_captain_shortlist'] == report
    assert next(r for r in job.results[0] if r['roster_position'] == 'CPT')['player_id'] in {
        r['player_id'] for r in report['shortlist']}
    assert job.params['objective_config']['captain_salary_multiplier'] == 1.5
    assert job.params['objective_config']['objective_weights'] == {'captain_p90': 1.5, 'flex_mean': 1.0}
    assert job.params['strategy_runtime']['lineup_correlation']['objective_multiplier'] == 0
    assert all(row['lineup_correlation_summary']['total_adjustment'] == 0 for row in job.results[0])
    assert any(r['captain_shortlist_exclusions'] for r in job.params['strategy_runtime']['player_pool']['rows'])
    pd.testing.assert_frame_equal(optimizer._load_player_pool.return_value, original)


@pytest.mark.parametrize('legacy_single_entry', [False, True])
def test_final_selectors_preserve_role_objective(legacy_single_entry):
    from backend.app.product_services.single_lineup import select_single_lineup
    from backend.app.product_services.showdown_single_entry import select_single_entry_lineups
    pool = players()
    strongest = solve(pool)
    alternative = solve(pool, locked_captain_player_id='id-1')
    assert strongest[0]['solver_objective_value'] > alternative[0]['solver_objective_value']
    # The old formula strongly prefers the alternative's floor/context/popularity.
    for row in alternative:
        row.update(predicted_p10=100, optimizer_context_adjustment=100, ownership=1)
    if legacy_single_entry:
        selected, report = select_single_entry_lineups([alternative, strongest], num_contests=1)
    else:
        selected, report = select_single_lineup([alternative, strongest], strategy='captain_single_lineup_v1')
        assert report['contract_id'] == POLICY_ID
        assert report['objective_weights'] == {'captain_p90': 1.5, 'flex_mean': 1.0}
    assert selected[0][0]['solver_objective_value'] == strongest[0]['solver_objective_value']


def test_shortlist_has_no_per_team_quota():
    pool = players()
    pool.loc[:3, 'player_team'] = 'AAA'
    pool.loc[4:, 'player_team'] = 'BBB'
    _, report = build_captain_shortlist(pool, params={}, flex_only_ids=set())
    assert [row['player_id'] for row in report['shortlist']] == ['id-0', 'id-1', 'id-2', 'id-3']
    assert {row['team'] for row in report['shortlist']} == {'AAA'}


def test_no_captain_eligible_is_infeasible_and_missing_p90_is_not_zero_filled():
    pool = players()
    pool['p90'] = float('nan')
    assert solve(pool) is None
    assert solve(players(), flex_only_player_ids=set(players().player_id)) is None


@pytest.mark.parametrize('allowed', [set(), {'id-1', 'id-2', 'id-3', 'id-4'}])
def test_final_validation_rejects_captain_outside_frozen_shortlist(allowed):
    lineup = solve(players())
    valid, reason = OptimizerService._validate_showdown_lineups(
        [lineup], requested_lineups=1, max_exposure=1,
        captain_positions=['WR', 'RB'], captain_shortlist_ids=allowed,
    )
    assert not valid
    assert 'top-four eligible pregame P90 shortlist' in reason


def test_final_validation_allows_non_shortlisted_flex_players():
    lineup = solve(players())
    valid, reason = OptimizerService._validate_showdown_lineups(
        [lineup], requested_lineups=1, max_exposure=1,
        captain_positions=['WR', 'RB'], captain_shortlist_ids={'id-0', 'id-1', 'id-2', 'id-3'},
    )
    assert valid, reason
    assert {'id-4', 'id-5'} <= {r['player_id'] for r in lineup if r['roster_position'] == 'FLEX'}
