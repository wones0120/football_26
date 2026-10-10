"""Default stack variety must fit hard construction limits at any volume."""
from collections import Counter
from itertools import combinations

import pytest

from backend.app.product_services.classic_strategy_contract import (
    build_strategy_contract,
    execute_strategy_contract,
    portfolio_audit,
)
from backend.app.product_services.gpp_optimizer import analyze_slate, build_large_gpp_config
from backend.app.tests.product.test_classic_strategy_contract import options, pool


@pytest.mark.parametrize("team_cap,game_cap,templates", [
    (4, None, ((1, 0), (1, 1), (2, 0), (2, 1))),
    (2, 5, ((1, 0), (1, 1))),
    (4, 2, ((1, 0),)),
    (4, 3, ((1, 0), (1, 1), (2, 0))),
])
def test_default_stack_cycle_fits_team_and_game_maximums(team_cap, game_cap, templates):
    config = build_large_gpp_config(analyze_slate(pool()), ownership_available=False,
        max_from_team=team_cap, max_from_game=game_cap)
    assert config.stack_templates == templates
    assert config.stack_rules.max_from_team == team_cap
    assert config.stack_rules.max_from_game == game_cap


@pytest.mark.parametrize("limits", [{"max_from_team": 1}, {"max_from_game": 1}])
def test_impossible_common_stack_floor_reports_construction_conflict(limits):
    with pytest.raises(ValueError, match="QB and at least one teammate"):
        build_large_gpp_config(analyze_slate(pool()), ownership_available=False, **limits)


def test_explicit_incompatible_stack_request_is_not_silently_weakened():
    with pytest.raises(ValueError, match="Requested stack templates exceed"):
        build_large_gpp_config(analyze_slate(pool()), ownership_available=False,
            max_from_team=2, stack_templates=((1, 0), (2, 0)))


@pytest.mark.parametrize("count", [5, 150])
def test_two_player_team_cap_generates_complete_unique_portfolio(count):
    players = pool()
    pipeline = {**options(), "num_lineups": count, "max_from_team": 2,
        "max_from_game": 5, "max_lineup_overlap": 5, "precompute_correlation_terms": True}
    contract = build_strategy_contract(players=players, pipeline_options=pipeline,
        requested={"num_lineups": count, "max_exposure": .8, "max_lineup_overlap": 5}, metadata={})
    result = execute_strategy_contract(contract)
    assert result.status == "completed", result.message
    assert len(result.lineups) == count
    rosters = [frozenset(p.player_id for p in lineup) for lineup in result.lineups]
    assert len(set(rosters)) == count
    assert all(len(a & b) <= 5 for a, b in combinations(rosters, 2))
    for lineup in result.lineups:
        assert len(lineup) == 9
        assert sum(p.salary for p in lineup) <= 50000
        positions = Counter(p.position for p in lineup)
        assert positions["QB"] == positions["DST"] == 1
        assert positions["RB"] >= 2 and positions["WR"] >= 3 and positions["TE"] >= 1
        assert max(Counter(p.team for p in lineup).values()) <= 2
        assert max(Counter(tuple(sorted((p.team, p.opponent))) for p in lineup).values()) <= 5
    audit = portfolio_audit(contract, result.lineups, trace=result.selection_trace)
    assert audit["validation"]["status"] == "verified"
    assert not any(step["solver_status"] == "Infeasible" for step in result.selection_trace)
    assert all(step["stack_template"][0] == 1 for step in result.selection_trace)


def test_bulk_diagnostic_sampling_preserves_rosters_and_audits(monkeypatch):
    from backend.app.product_services import gpp_optimizer
    pipeline = {**options(), "max_from_team": 2, "include_control_comparisons": True}
    ordinary = build_strategy_contract(players=pool(), pipeline_options=pipeline, requested={}, metadata={})
    expected = execute_strategy_contract(ordinary)
    monkeypatch.setattr(gpp_optimizer, "FULL_CONTROL_COMPARISON_MAX_LINEUPS", 2)
    actual = execute_strategy_contract(ordinary)
    assert [[p.player_id for p in row] for row in actual.lineups] == [[p.player_id for p in row] for row in expected.lineups]
    assert len(actual.control_comparisons) == 1
    assert len(expected.control_comparisons) == 5
    assert len(actual.selection_trace) == 5
    assert [s["objective_sha256"] for s in actual.selection_trace] == [s["objective_sha256"] for s in expected.selection_trace]
    assert portfolio_audit(ordinary, actual.lineups)["validation"]["status"] == "verified"
