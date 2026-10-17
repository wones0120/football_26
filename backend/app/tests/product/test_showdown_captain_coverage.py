from itertools import combinations

import pytest

from backend.app.tests.product.test_showdown_qb_preferences import service, offline_strategy_inputs


def run(optimizer, **params):
    return optimizer.run_job(season=2026, week=4, slate='THURSDAY_NIGHT',
        strategy='showdown_gpp_portfolio_v3', contest_format='showdown', objective='gpp',
        params={'num_lineups': 4, 'captain_max_exposure': .25, **params})


def captains(job):
    return [next(r['player_id'] for r in lineup if r['roster_position'] == 'CPT') for lineup in job.results]


@pytest.mark.parametrize('rate', [.25, 25])
def test_four_captains_include_qbs_and_best_legal_flex(rate):
    optimizer = service()
    job = run(optimizer, captain_max_exposure=rate)
    assert job.status == 'completed', job.message
    assert captains(job) == ['p0', 'p1', 'p2', 'p3']
    assert job.params['strategy_runtime']['showdown_captain_coverage']['underfill'] == 0
    pool = optimizer._load_player_pool.return_value
    # Enumerate all legal FLEX alternatives independently of the solver objective.
    for lineup in job.results:
        captain = next(r for r in lineup if r['roster_position'] == 'CPT')
        alternatives = []
        remaining = pool[pool.player_id != captain['player_id']].to_dict('records')
        for flex in combinations(remaining, 5):
            candidate = [captain, *[{**r, 'roster_position': 'FLEX', 'base_salary': r['salary']} for r in flex]]
            valid, _ = optimizer._validate_showdown_lineups([candidate], requested_lineups=4,
                max_exposure=1, portfolio_policy=True)
            if valid:
                alternatives.append(1.5 * captain['base_p90'] + sum(r['projection'] for r in flex))
        assert sum(r['objective_score'] for r in lineup) == max(alternatives)


@pytest.mark.parametrize('status,extra', [('OUT', {}), ('Q', {'exclude_questionable': True})])
def test_injury_filters_precede_shortlist_and_promote_next_eligible(status, extra):
    optimizer = service()
    optimizer._load_player_pool.return_value.loc[2, 'player_status'] = status
    optimizer._load_player_pool.return_value.loc[10, 'position'] = 'WR'
    job = run(optimizer, **extra)
    assert job.status == 'completed', job.message
    assert captains(job) == ['p0', 'p1', 'p3', 'p4']
    assert all(r['player_id'] != 'p2' for lineup in job.results for r in lineup)


def test_explicit_qb_exclusion_applies_before_ranking():
    job = run(service(), no_qb_captain=True)
    assert captains(job) == ['p2', 'p3', 'p4', 'p5']


def test_quality_floor_warns_without_replacing_captain():
    optimizer = service()
    optimizer._load_player_pool.return_value.loc[0, ['p90', 'projection']] = 1000
    job = run(optimizer, no_two_qbs=True)
    assert job.status == 'completed', job.message
    assert captains(job) == ['p0', 'p1', 'p2', 'p3']
    report = job.params['strategy_runtime']['showdown_captain_coverage']
    second = report['captains'][1]
    assert {warning['metric'] for warning in second['quality_floor_warnings']} == {'projection', 'p90'}
    assert second['projection_gap']['p90'] > 0
    assert report['quality_floor_policy'] == 'diagnostic_only'
    assert job.results[1][0]['showdown_captain_coverage'] == report


def test_salary_infeasibility_underfills_without_promoting_fifth():
    optimizer = service()
    optimizer._load_player_pool.return_value.loc[0, 'salary'] = 20000
    # CPT p0 costs 30k plus five 5k FLEX = 55k. p0 remains legal at FLEX.
    job = run(optimizer)
    assert job.status == 'completed', job.message
    assert captains(job) == ['p1', 'p2', 'p3']
    report = job.params['strategy_runtime']['showdown_captain_coverage']
    assert report['underfill'] == 1
    assert report['captains'][0]['solver_status'] == 'Infeasible'
    assert 'salary_cap' in report['captains'][0]['reason']
    assert 'underfill=1' in job.message


def test_other_exposure_setting_preserves_existing_path():
    job = run(service(), captain_max_exposure=.60)
    assert job.status == 'completed', job.message
    assert 'showdown_captain_coverage' not in job.params['strategy_runtime']


def test_cash_multi_lineup_mode_keeps_user_hard_limits():
    optimizer = service()
    job = optimizer.run_job(season=2026, week=4, slate='THURSDAY_NIGHT',
        strategy='captain_single_lineup_v1', contest_format='showdown', objective='cash',
        allow_incomplete_evidence=True,
        params={'num_lineups': 4, 'captain_max_exposure': .25, 'max_lineup_overlap': 4,
                'maximum_exposure_by_player': {'p6': 0}, 'max_players_per_team': 3})
    assert job.status == 'completed', job.message
    assert captains(job) == ['p0', 'p1', 'p2', 'p3']
    sets = [{r['player_id'] for r in lineup} for lineup in job.results]
    assert all('p6' not in ids for ids in sets)
    assert all(len(a & b) <= 4 for a, b in combinations(sets, 2))
    assert all(sum(r['player_team'] == 'SEA' for r in lineup) == 3 for lineup in job.results)


def test_no_feasible_lineups_reports_conflicts_through_api():
    from backend.app.api.product_routes import get_optimizer_results
    optimizer = service()
    optimizer._load_player_pool.return_value['salary'] = 10000
    job = run(optimizer)
    assert job.status == 'failed'
    assert not job.results
    response = get_optimizer_results(job.job_id, service=optimizer)
    assert response.showdown_captain_coverage['underfill'] == 4
    assert all('salary_cap' in row['reason'] for row in response.showdown_captain_coverage['captains'])


def test_fewer_eligible_captains_reports_underfill():
    optimizer = service()
    job = run(optimizer, captain_positions=['RB'])
    assert job.status == 'completed', job.message
    assert captains(job) == ['p4', 'p5']
    report = job.params['strategy_runtime']['showdown_captain_coverage']
    assert report['missing_eligible_captains'] == report['underfill'] == 2
    assert 'only 2 eligible captains' in job.message
