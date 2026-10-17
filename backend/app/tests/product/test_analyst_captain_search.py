from copy import deepcopy
from unittest.mock import patch

import pulp

from backend.app.product_services.analyst_captain_search import broaden_captains
from backend.app.product_services.cbc_solver import make_cbc_solver


def search_fixture():
    rows = [dict(player_id=pid, showdown_captain_shortlisted=pid != 'no-captain')
            for pid in ['a', 'b', 'c', 'no-captain']]
    mapping = {role + pid: dict(player_master_id=pid, role=role)
               for pid in ['a', 'b', 'c', 'no-captain'] for role in ['CPT', 'FLEX']}
    worlds = [dict(scenario_id='normal'), dict(scenario_id='alternate')]
    def model(scenario):
        m = pulp.LpProblem('legal', pulp.LpMaximize)
        v = {name: pulp.LpVariable(name, cat='Binary') for name in mapping}
        m += pulp.lpSum(v['CPT' + pid] for pid in ['a', 'b', 'c', 'no-captain']) == 1
        m += pulp.lpSum(v['FLEX' + pid] for pid in ['a', 'b', 'c', 'no-captain']) == 2
        for pid in ['a', 'b', 'c', 'no-captain']:
            m += v['CPT' + pid] + v['FLEX' + pid] <= 1
        # A hard user restriction, and an alternate-story requirement.
        m += v['CPTc'] == 0
        if scenario['scenario_id'] == 'alternate':
            m += v['FLEXa'] == 1
        m += pulp.lpSum((10 - i) * v[name] for i, name in enumerate(mapping))
        return v, m
    return worlds, rows, mapping, model


def test_search_adds_distinct_support_rosters_and_preserves_legal_story_gates():
    worlds, rows, mapping, model = search_fixture()
    before = deepcopy(rows)
    candidates = {}
    attempts, report = broaden_captains(scenarios=worlds, rows=rows, mapping=mapping,
        candidates=candidates, scenario_model=model, solver=make_cbc_solver, per_captain=2)
    assert rows == before
    assert report['supporting_rosters_per_captain'] == 2
    assert report['budget_exhausted'] is False
    assert set(report['eligible_captain_ids']) == {'a', 'b', 'c'}
    assert any(row['solver_status'] == 'Infeasible' for row in attempts)
    assert next(row for row in report['coverage'] if row['scenario_id'] == 'normal' and row['captain_player_master_id'] == 'a')['distinct_supporting_rosters'] == 2
    for signature, candidate in candidates.items():
        assert len({pid for pid, _ in signature}) == 3
        assert not any((pid, 'CPT') in signature for pid in ['c', 'no-captain'])
        if 'alternate' in candidate['scenario_ids']:
            assert ('a', 'FLEX') in signature
    again = {}
    _, repeated = broaden_captains(scenarios=worlds, rows=rows, mapping=mapping,
        candidates=again, scenario_model=model, solver=make_cbc_solver, per_captain=2)
    assert candidates == again and report == repeated


def test_seed_rosters_count_toward_target_and_budget_exhaustion_is_explicit():
    worlds, rows, mapping, model = search_fixture()
    candidates = {}
    with patch('backend.app.product_services.analyst_captain_search.MAX_SOLVES', 1):
        attempts, report = broaden_captains(scenarios=worlds, rows=rows, mapping=mapping,
            candidates=candidates, scenario_model=model, solver=make_cbc_solver, per_captain=2)
    assert len(attempts) == report['solves_used'] == 1
    assert report['budget_exhausted'] is True
    assert any(row['status'] == 'budget_exhausted' for row in report['coverage'])
    seed = deepcopy(candidates)
    _, complete = broaden_captains(scenarios=worlds[:1], rows=rows, mapping=mapping,
        candidates=candidates, scenario_model=model, solver=make_cbc_solver, per_captain=2)
    assert set(seed) <= set(candidates)
    assert next(row for row in complete['coverage'] if row['captain_player_master_id'] == 'a')['distinct_supporting_rosters'] == 2
