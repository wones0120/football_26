from __future__ import annotations

import pandas as pd
import pytest
import pulp

from backend.app.product_services.lineup_correlation_scoring import (
    LINEUP_CORRELATION_LIBRARY,
    LINEUP_CORRELATION_LIBRARY_ID,
    LINEUP_CORRELATION_LIBRARY_VERSION,
    active_format_specific_terms,
    add_format_specific_objective,
    build_format_specific_terms,
    build_lineup_correlation_terms,
    score_lineup_correlations,
)
from backend.app.product_services.optimizer import OptimizerService
from backend.app.product_services.rule_library import (
    RuleType,
    resolve_strategy_profile,
)


def _player(player_id: str, position: str, team: str, opponent: str, **overrides) -> dict:
    row = {
        "player_id": player_id,
        "name": player_id,
        "position": position,
        "player_team": team,
        "opponent_team": opponent,
        "salary": 5000,
        "projection": 12.0,
        "p90": 20.0,
        "game_total_line": 52.0,
        "team_spread_line": -1.0 if team == "AAA" else 1.0,
        "team_implied_total": 26.0,
        "market_context_point_in_time_safe": True,
        "optimizer_receiving_role_strength": 0.0,
        "optimizer_rushing_role_strength": 0.0,
    }
    row.update(overrides)
    return row


def _adjustment(players: list[dict], *, contest_format: str, objective: str) -> float:
    profile = resolve_strategy_profile(
        contest_format=contest_format, objective=objective
    )
    return sum(
        term.adjustment
        for term in build_lineup_correlation_terms(players, profile=profile)
        if term.kind == "pair"
    )


def _format_adjustment(
    players: list[dict], *, contest_format: str, objective: str
) -> float:
    profile = resolve_strategy_profile(
        contest_format=contest_format, objective=objective
    )
    captain_indexes = {
        index
        for index, row in enumerate(players)
        if row.get("is_captain") or row.get("roster_position") == "CPT"
    }
    return sum(
        term.adjustment
        for term in active_format_specific_terms(
            build_format_specific_terms(players, profile=profile),
            selected_indexes=set(range(len(players))),
            captain_indexes=captain_indexes,
        )
    )


def test_lineup_library_contains_only_soft_preferences() -> None:
    assert LINEUP_CORRELATION_LIBRARY.library_id == LINEUP_CORRELATION_LIBRARY_ID
    assert LINEUP_CORRELATION_LIBRARY.version == LINEUP_CORRELATION_LIBRARY_VERSION
    assert {
        rule.rule_type for rule in LINEUP_CORRELATION_LIBRARY.rules
    } <= {RuleType.SOFT_BOOST, RuleType.SOFT_PENALTY}


def test_qb_receiver_boost_and_opposing_dst_penalty_are_profile_weighted() -> None:
    quarterback = _player("qb", "QB", "AAA", "BBB")
    receiver = _player("wr", "WR", "AAA", "BBB")
    opposing_dst = _player("dst", "DST", "BBB", "AAA")

    gpp_stack = _adjustment(
        [quarterback, receiver], contest_format="classic", objective="gpp"
    )
    h2h_stack = _adjustment(
        [quarterback, receiver], contest_format="classic", objective="cash"
    )
    gpp_conflict = _adjustment(
        [quarterback, opposing_dst], contest_format="classic", objective="gpp"
    )

    assert 0.0 < gpp_stack < 0.80
    assert h2h_stack == pytest.approx(gpp_stack * 0.50)
    assert gpp_conflict == pytest.approx(-1.50)


def test_qb_stack_bonus_scales_with_context_and_has_no_structural_floor() -> None:
    high_context = [
        _player(
            "high-qb",
            "QB",
            "AAA",
            "BBB",
            game_total_line=54.0,
            team_implied_total=30.0,
            team_spread_line=-2.0,
        ),
        _player("high-wr", "WR", "AAA", "BBB"),
    ]
    low_context = [
        _player(
            "low-qb",
            "QB",
            "CCC",
            "DDD",
            game_total_line=38.0,
            team_implied_total=19.0,
            team_spread_line=6.0,
        ),
        _player("low-wr", "WR", "CCC", "DDD"),
    ]
    missing_context = [
        _player(
            "missing-qb",
            "QB",
            "EEE",
            "FFF",
            game_total_line=None,
            team_implied_total=None,
            team_spread_line=None,
            market_context_point_in_time_safe=False,
        ),
        _player("missing-wr", "WR", "EEE", "FFF"),
    ]

    high = _adjustment(high_context, contest_format="classic", objective="gpp")
    low = _adjustment(low_context, contest_format="classic", objective="gpp")
    missing = _adjustment(
        missing_context, contest_format="classic", objective="gpp"
    )

    assert high > low > 0.0
    assert missing == 0.0

    summary = score_lineup_correlations(
        high_context,
        profile=resolve_strategy_profile(
            contest_format="classic", objective="gpp"
        ),
    )
    trigger = next(
        row
        for row in summary["triggered_rules"]
        if row["reason_code"] == "qb_same_team_pass_catcher"
    )
    assert trigger["evidence"]["stack_environment"]["available"] is True
    assert trigger["magnitude"] == pytest.approx(
        trigger["evidence"]["stack_environment"]["stack_environment"]
    )


def test_rb_dst_bonus_requires_cutoff_safe_game_script() -> None:
    safe = [
        _player(
            "rb",
            "RB",
            "AAA",
            "BBB",
            game_total_line=42.0,
            team_spread_line=-9.0,
        ),
        _player("dst", "DST", "AAA", "BBB"),
    ]
    unsafe = [
        dict(
            safe[0],
            market_context_point_in_time_safe=False,
        ),
        safe[1],
    ]

    assert _adjustment(safe, contest_format="classic", objective="gpp") > 0.0
    assert _adjustment(unsafe, contest_format="classic", objective="gpp") == 0.0


def test_market_driven_bring_back_requires_point_in_time_safe_evidence() -> None:
    quarterback = _player("qb", "QB", "AAA", "BBB")
    bring_back = _player("wr", "WR", "BBB", "AAA")

    safe = _adjustment(
        [quarterback, bring_back], contest_format="classic", objective="gpp"
    )
    bring_back["market_context_point_in_time_safe"] = False
    quarterback["market_context_point_in_time_safe"] = False
    unsafe = _adjustment(
        [quarterback, bring_back], contest_format="classic", objective="gpp"
    )

    assert safe > 0.0
    assert unsafe == 0.0


def test_showdown_summary_explains_captain_rules_once_and_game_script() -> None:
    lineup = [
        _player("captain-wr", "WR", "AAA", "BBB", roster_position="CPT", is_captain=True),
        _player("qb-a", "QB", "AAA", "BBB", roster_position="FLEX"),
        _player("k-a", "K", "AAA", "BBB", roster_position="FLEX"),
        _player("wr-b", "WR", "BBB", "AAA", roster_position="FLEX"),
        _player("rb-b", "RB", "BBB", "AAA", roster_position="FLEX"),
        _player("k-b", "K", "BBB", "AAA", roster_position="FLEX"),
    ]
    summary = score_lineup_correlations(
        lineup,
        profile=resolve_strategy_profile(
            contest_format="showdown", objective="gpp"
        ),
    )
    reason_codes = [row["reason_code"] for row in summary["triggered_rules"]]

    assert reason_codes.count("high_total_offensive_captain") == 1
    assert "pass_catcher_captain_with_qb" in reason_codes
    assert summary["total_adjustment"] > 0.0
    assert summary["construction_label"].endswith("captain-wr Captain")
    assert summary["implied_game_script"]["label"] == "High-scoring shootout"


def test_showdown_five_one_underdog_build_is_labeled_not_banned() -> None:
    lineup = [
        _player(
            f"bbb-{index}",
            "QB" if index == 0 else "WR",
            "BBB",
            "AAA",
            roster_position="CPT" if index == 0 else "FLEX",
            is_captain=index == 0,
            team_spread_line=8.0,
        )
        for index in range(5)
    ] + [
        _player(
            "aaa-0",
            "WR",
            "AAA",
            "BBB",
            roster_position="FLEX",
            team_spread_line=-8.0,
        )
    ]
    summary = score_lineup_correlations(
        lineup,
        profile=resolve_strategy_profile(
            contest_format="showdown", objective="gpp"
        ),
    )

    assert summary["construction_label"].startswith("5-1")
    assert summary["implied_game_script"]["script_id"] == "underdog_upset"
    assert "underdog_five_one_construction" in summary["negative_reason_codes"]


def test_showdown_five_one_favorite_build_receives_gpp_support() -> None:
    lineup = [
        _player(
            f"aaa-{index}",
            "QB" if index == 0 else "WR",
            "AAA",
            "BBB",
            roster_position="CPT" if index == 0 else "FLEX",
            is_captain=index == 0,
            team_spread_line=-8.0,
        )
        for index in range(5)
    ] + [
        _player(
            "bbb-0",
            "WR",
            "BBB",
            "AAA",
            roster_position="FLEX",
            team_spread_line=8.0,
        )
    ]
    summary = score_lineup_correlations(
        lineup,
        profile=resolve_strategy_profile(
            contest_format="showdown", objective="gpp"
        ),
    )

    assert summary["implied_game_script"]["script_id"] == "favorite_dominates"
    assert "favorite_five_one_construction" in summary["positive_reason_codes"]


def test_showdown_five_one_pickem_does_not_invent_a_favorite() -> None:
    lineup = [
        _player(
            f"aaa-{index}",
            "QB" if index == 0 else "WR",
            "AAA",
            "BBB",
            roster_position="CPT" if index == 0 else "FLEX",
            is_captain=index == 0,
            team_spread_line=0.0,
        )
        for index in range(5)
    ] + [
        _player(
            "bbb-0",
            "WR",
            "BBB",
            "AAA",
            roster_position="FLEX",
            team_spread_line=0.0,
        )
    ]
    summary = score_lineup_correlations(
        lineup,
        profile=resolve_strategy_profile(
            contest_format="showdown", objective="gpp"
        ),
    )

    assert summary["construction_label"].startswith("5-1")
    assert summary["implied_game_script"]["script_id"] == "one_sided_build"
    assert "favorite_five_one_construction" not in summary[
        "positive_reason_codes"
    ]
    assert "underdog_five_one_construction" not in summary[
        "negative_reason_codes"
    ]


def test_classic_naked_qb_penalty_allows_a_rushing_qb_exception() -> None:
    pocket_qb = _player(
        "pocket-qb",
        "QB",
        "AAA",
        "BBB",
        optimizer_rushing_role_strength=0.0,
    )
    rushing_qb = _player(
        "rushing-qb",
        "QB",
        "AAA",
        "BBB",
        optimizer_rushing_role_strength=1.0,
    )

    assert _format_adjustment(
        [pocket_qb], contest_format="classic", objective="gpp"
    ) == pytest.approx(-1.10)
    assert _format_adjustment(
        [rushing_qb], contest_format="classic", objective="gpp"
    ) == pytest.approx(0.0)


def test_negative_format_indicator_matches_completed_lineup_audit() -> None:
    players = [
        _player(
            "pocket-qb",
            "QB",
            "AAA",
            "BBB",
            optimizer_rushing_role_strength=0.0,
        )
    ]
    profile = resolve_strategy_profile(
        contest_format="classic", objective="gpp"
    )
    model = pulp.LpProblem("phase5_negative_indicator", pulp.LpMaximize)
    selected = {0: pulp.LpVariable("selected_0", cat="Binary")}
    model += selected[0] == 1
    objective = add_format_specific_objective(
        model,
        build_format_specific_terms(players, profile=profile),
        selected_vars=selected,
        prefix="phase5_test",
    )
    model += objective

    status = model.solve(pulp.PULP_CBC_CMD(msg=False))

    assert status == pulp.LpStatusOptimal
    assert pulp.value(objective) == pytest.approx(
        _format_adjustment(
            players, contest_format="classic", objective="gpp"
        )
    )


def test_classic_higher_order_stack_and_skill_cluster_rules_are_explained() -> None:
    double_stack = [
        _player("qb-a", "QB", "AAA", "BBB"),
        _player("wr-a", "WR", "AAA", "BBB"),
        _player("te-a", "TE", "AAA", "BBB"),
    ]
    unsupported_cluster = [
        _player("rb-c", "RB", "CCC", "DDD"),
        _player("wr-c", "WR", "CCC", "DDD"),
        _player("te-c", "TE", "CCC", "DDD"),
    ]

    stack_summary = score_lineup_correlations(
        double_stack,
        profile=resolve_strategy_profile(
            contest_format="classic", objective="gpp"
        ),
    )
    cluster_summary = score_lineup_correlations(
        unsupported_cluster,
        profile=resolve_strategy_profile(
            contest_format="classic", objective="gpp"
        ),
    )

    assert "quarterback_double_stack" in stack_summary["positive_reason_codes"]
    assert (
        "same_team_skill_cluster_without_quarterback"
        in cluster_summary["negative_reason_codes"]
    )


def test_qb_double_stack_bonus_requires_cutoff_safe_environment() -> None:
    safe = [
        _player(
            "qb-a",
            "QB",
            "AAA",
            "BBB",
            game_total_line=52.0,
            team_implied_total=28.0,
            team_spread_line=-3.0,
        ),
        _player("wr-a", "WR", "AAA", "BBB"),
        _player("te-a", "TE", "AAA", "BBB"),
    ]
    unsafe = [
        dict(
            safe[0],
            game_total_line=None,
            team_implied_total=None,
            team_spread_line=None,
            market_context_point_in_time_safe=False,
        ),
        safe[1],
        safe[2],
    ]

    assert _format_adjustment(
        safe, contest_format="classic", objective="gpp"
    ) > 0.0
    assert _format_adjustment(
        unsafe, contest_format="classic", objective="gpp"
    ) == 0.0


def test_showdown_qb_captain_double_stack_requires_safe_environment() -> None:
    safe = [
        _player(
            "qb-a",
            "QB",
            "AAA",
            "BBB",
            roster_position="CPT",
            is_captain=True,
        ),
        _player("wr-a", "WR", "AAA", "BBB", roster_position="FLEX"),
        _player("te-a", "TE", "AAA", "BBB", roster_position="FLEX"),
    ]
    unsafe = [
        dict(
            safe[0],
            game_total_line=None,
            team_implied_total=None,
            team_spread_line=None,
            market_context_point_in_time_safe=False,
        ),
        safe[1],
        safe[2],
    ]

    assert _format_adjustment(
        safe, contest_format="showdown", objective="gpp"
    ) > 0.0
    assert _format_adjustment(
        unsafe, contest_format="showdown", objective="gpp"
    ) == 0.0


def test_classic_contradictory_game_script_is_detected_not_banned() -> None:
    lineup = [
        _player(
            "rb-a",
            "RB",
            "AAA",
            "BBB",
            team_spread_line=-9.0,
            optimizer_rushing_role_strength=1.0,
        ),
        _player("dst-b", "DST", "BBB", "AAA", team_spread_line=9.0),
        _player("wr-b", "WR", "BBB", "AAA", team_spread_line=9.0),
        _player("te-b", "TE", "BBB", "AAA", team_spread_line=9.0),
    ]
    summary = score_lineup_correlations(
        lineup,
        profile=resolve_strategy_profile(
            contest_format="classic", objective="gpp"
        ),
    )

    assert "contradictory_favorite_rb_underdog_stack" in summary[
        "negative_reason_codes"
    ]


def test_showdown_captain_and_team_split_rules_are_higher_order() -> None:
    lineup = [
        _player(
            "qb-a",
            "QB",
            "AAA",
            "BBB",
            roster_position="CPT",
            is_captain=True,
        ),
        _player("wr-a", "WR", "AAA", "BBB", roster_position="FLEX"),
        _player("te-a", "TE", "AAA", "BBB", roster_position="FLEX"),
        _player("qb-b", "QB", "BBB", "AAA", roster_position="FLEX"),
        _player("wr-b", "WR", "BBB", "AAA", roster_position="FLEX"),
        _player("rb-b", "RB", "BBB", "AAA", roster_position="FLEX"),
    ]
    summary = score_lineup_correlations(
        lineup,
        profile=resolve_strategy_profile(
            contest_format="showdown", objective="gpp"
        ),
    )

    assert "quarterback_captain_double_stack" in summary["positive_reason_codes"]
    assert "competitive_three_three_construction" in summary[
        "positive_reason_codes"
    ]
    assert summary["format_specific_rule_count"] >= 2


def test_showdown_pass_catcher_captain_without_qb_is_penalized_not_banned() -> None:
    lineup = [
        _player(
            "wr-a",
            "WR",
            "AAA",
            "BBB",
            roster_position="CPT",
            is_captain=True,
        ),
        _player("rb-a", "RB", "AAA", "BBB", roster_position="FLEX"),
        _player("wr-a2", "WR", "AAA", "BBB", roster_position="FLEX"),
        _player("qb-b", "QB", "BBB", "AAA", roster_position="FLEX"),
        _player("wr-b", "WR", "BBB", "AAA", roster_position="FLEX"),
        _player("te-b", "TE", "BBB", "AAA", roster_position="FLEX"),
    ]
    summary = score_lineup_correlations(
        lineup,
        profile=resolve_strategy_profile(
            contest_format="showdown", objective="gpp"
        ),
    )

    assert "pass_catcher_captain_without_quarterback" in summary[
        "negative_reason_codes"
    ]


def test_showdown_fragile_punt_penalty_requires_missing_role_evidence() -> None:
    captain = _player(
        "qb-a",
        "QB",
        "AAA",
        "BBB",
        roster_position="CPT",
        is_captain=True,
    )
    fragile = _player(
        "punt",
        "WR",
        "BBB",
        "AAA",
        salary=200,
        roster_position="FLEX",
    )
    viable = dict(fragile, pregame_expected_routes=12.0)

    assert _format_adjustment(
        [captain, fragile], contest_format="showdown", objective="gpp"
    ) < _format_adjustment(
        [captain, viable], contest_format="showdown", objective="gpp"
    )


def test_classic_solver_uses_soft_stack_bonus_without_forcing_stack() -> None:
    fixed = [
        _player("qb-a", "QB", "AAA", "BBB", projection=20.0),
        _player("rb-b", "RB", "BBB", "AAA", projection=18.0),
        _player("rb-c", "RB", "CCC", "DDD", projection=17.0),
        _player("rb-e", "RB", "EEE", "FFF", projection=16.0),
        _player("wr-b", "WR", "BBB", "AAA", projection=15.0),
        _player("wr-c", "WR", "CCC", "DDD", projection=14.0),
        _player("te-e", "TE", "EEE", "FFF", projection=13.0),
        _player("dst-f", "DST", "FFF", "EEE", projection=11.0),
    ]
    stack_receiver = _player(
        "stack-wr", "WR", "AAA", "BBB", projection=9.5
    )
    raw_receiver = _player(
        "raw-wr", "WR", "DDD", "CCC", projection=10.0
    )
    pool = pd.DataFrame([*fixed, stack_receiver, raw_receiver])
    service = OptimizerService.__new__(OptimizerService)

    raw_lineup = service._solve_lineup(
        pool,
        score_col="projection",
        contest_type="classic",
        stack_params={"enabled": False},
    )
    correlated_lineup = service._solve_lineup(
        pool,
        score_col="projection",
        contest_type="classic",
        stack_params={"enabled": False},
        rule_profile=resolve_strategy_profile(
            contest_format="classic", objective="gpp"
        ),
    )

    assert raw_lineup is not None
    assert correlated_lineup is not None
    assert "raw-wr" in {row["player_id"] for row in raw_lineup}
    assert "stack-wr" in {row["player_id"] for row in correlated_lineup}


def test_classic_solver_uses_phase5_double_stack_scoring() -> None:
    fixed = [
        _player("qb-a", "QB", "AAA", "BBB", projection=20.0),
        _player("rb-b", "RB", "BBB", "AAA", projection=18.0),
        _player("rb-c", "RB", "CCC", "DDD", projection=17.0),
        _player("wr-a1", "WR", "AAA", "BBB", projection=16.0),
        _player("wr-b", "WR", "BBB", "AAA", projection=15.0),
        _player("wr-c", "WR", "CCC", "DDD", projection=14.0),
        _player("te-e", "TE", "EEE", "FFF", projection=13.0),
        _player("dst-f", "DST", "FFF", "EEE", projection=11.0),
    ]
    second_stack_receiver = _player(
        "stack-wr2", "WR", "AAA", "BBB", projection=9.0
    )
    raw_receiver = _player(
        "raw-wr2", "WR", "DDD", "CCC", projection=10.0
    )
    pool = pd.DataFrame([*fixed, second_stack_receiver, raw_receiver])
    service = OptimizerService.__new__(OptimizerService)

    raw_lineup = service._solve_lineup(
        pool,
        score_col="projection",
        contest_type="classic",
        stack_params={"enabled": False},
    )
    format_lineup = service._solve_lineup(
        pool,
        score_col="projection",
        contest_type="classic",
        stack_params={"enabled": False},
        rule_profile=resolve_strategy_profile(
            contest_format="classic", objective="gpp"
        ),
    )

    assert raw_lineup is not None
    assert format_lineup is not None
    assert "raw-wr2" in {row["player_id"] for row in raw_lineup}
    assert "stack-wr2" in {row["player_id"] for row in format_lineup}


def test_locked_negative_correlation_remains_solvable() -> None:
    pool = pd.DataFrame(
        [
            _player("qb-a", "QB", "AAA", "BBB", projection=20.0),
            _player("rb-a", "RB", "AAA", "BBB", projection=18.0),
            _player("rb-c", "RB", "CCC", "DDD", projection=17.0),
            _player("wr-a", "WR", "AAA", "BBB", projection=16.0),
            _player("wr-b", "WR", "BBB", "AAA", projection=15.0),
            _player("wr-c", "WR", "CCC", "DDD", projection=14.0),
            _player("te-c", "TE", "CCC", "DDD", projection=13.0),
            _player("rb-e", "RB", "EEE", "FFF", projection=12.0),
            _player("dst-b", "DST", "BBB", "AAA", projection=11.0),
        ]
    )
    service = OptimizerService.__new__(OptimizerService)
    lineup = service._solve_lineup(
        pool,
        score_col="projection",
        contest_type="classic",
        stack_params={"enabled": False},
        locked_player_ids={"qb-a", "dst-b"},
        rule_profile=resolve_strategy_profile(
            contest_format="classic", objective="gpp"
        ),
    )

    assert lineup is not None
    assert {"qb-a", "dst-b"} <= {row["player_id"] for row in lineup}


@pytest.mark.parametrize(
    ("contest_format", "objective"),
    [
        ("classic", "cash"),
        ("classic", "gpp"),
        ("showdown", "cash"),
        ("showdown", "gpp"),
    ],
)
def test_all_four_phase4_profiles_keep_the_solver_feasible(
    contest_format: str, objective: str
) -> None:
    service = OptimizerService.__new__(OptimizerService)
    profile = resolve_strategy_profile(
        contest_format=contest_format, objective=objective
    )
    if contest_format == "showdown":
        pool = pd.DataFrame(
            [
                _player(
                    f"showdown-{index}",
                    "QB" if index in {0, 3} else "WR",
                    "AAA" if index < 3 else "BBB",
                    "BBB" if index < 3 else "AAA",
                )
                for index in range(6)
            ]
        )
        lineup = service._solve_lineup(
            pool,
            score_col="p90",
            contest_type="captain",
            stack_params={"enabled": False},
            rule_profile=profile,
        )
        assert lineup is not None
        assert len(lineup) == 6
        assert sum(row["roster_position"] == "CPT" for row in lineup) == 1
        return

    pool = pd.DataFrame(
        [
            _player("qb-a", "QB", "AAA", "BBB"),
            _player("rb-a", "RB", "AAA", "BBB"),
            _player("rb-b", "RB", "BBB", "AAA"),
            _player("wr-a", "WR", "AAA", "BBB"),
            _player("wr-b", "WR", "BBB", "AAA"),
            _player("wr-c", "WR", "CCC", "DDD"),
            _player("te-c", "TE", "CCC", "DDD"),
            _player("rb-e", "RB", "EEE", "FFF"),
            _player("dst-f", "DST", "FFF", "EEE"),
        ]
    )
    lineup = service._solve_lineup(
        pool,
        score_col="projection",
        contest_type="cash" if objective == "cash" else "classic",
        stack_params={"enabled": False},
        rule_profile=profile,
    )
    assert lineup is not None
    assert len(lineup) == 9
