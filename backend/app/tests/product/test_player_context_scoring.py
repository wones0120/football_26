from __future__ import annotations

import pandas as pd
import pytest

from backend.app.product_services.player_context_scoring import (
    PLAYER_CONTEXT_LIBRARY_ID,
    PLAYER_CONTEXT_LIBRARY_VERSION,
    score_player_context,
)
from backend.app.product_services.optimizer import OptimizerService
from backend.app.product_services.rule_library import resolve_strategy_profile


def _row(player_id: str, **overrides) -> dict:
    row = {
        "player_id": player_id,
        "name": player_id,
        "position": "WR",
        "projection": 15.0,
        "p90": 24.0,
        "game_total_line": 44.0,
        "team_spread_line": 0.0,
        "team_implied_total": 22.0,
        "market_context_point_in_time_safe": True,
        "pregame_context_run_id": "context-1",
        "pregame_expected_routes": 32.0,
        "pregame_expected_targets": 8.0,
        "pregame_role_uncertain": False,
        "pregame_newly_assigned_role": False,
        "pregame_depth_chart_conflict": False,
    }
    row.update(overrides)
    return row


def _score(rows: list[dict], *, objective: str = "gpp"):
    return score_player_context(
        pd.DataFrame(rows),
        profile=resolve_strategy_profile(
            contest_format="classic",
            objective=objective,
        ),
    )


def test_game_environment_adjustments_scale_continuously() -> None:
    result = _score(
        [
            _row(
                "moderate",
                game_total_line=46.0,
                team_implied_total=26.0,
            ),
            _row(
                "elite",
                game_total_line=54.0,
                team_implied_total=30.0,
            ),
        ]
    )
    rows = result.scored_pool.set_index("player_id")

    assert rows.loc["elite", "optimizer_context_adjustment"] > rows.loc[
        "moderate", "optimizer_context_adjustment"
    ]
    assert rows.loc["elite", "projection"] == pytest.approx(15.0)
    assert rows.loc["elite", "p90"] == pytest.approx(24.0)
    assert rows.loc["elite", "optimizer_context_mean_score"] > 15.0
    elite_audit = next(row for row in result.audit_rows if row["player_id"] == "elite")
    trigger = next(
        row
        for row in elite_audit["rule_evaluation"]["triggered_rules"]
        if row["reason_code"] == "high_game_total"
    )
    assert trigger["magnitude"] == pytest.approx(1.0)


def test_favorite_goal_line_and_underdog_role_rules_remain_soft() -> None:
    result = _score(
        [
            _row(
                "favorite-back",
                position="RB",
                team_spread_line=-10.0,
                team_implied_total=27.0,
                pregame_expected_routes=8.0,
                pregame_expected_targets=2.0,
                pregame_expected_carries=19.0,
                pregame_goal_line_share=0.60,
                pregame_red_zone_share=0.35,
            ),
            _row(
                "underdog-back",
                position="RB",
                team_spread_line=10.0,
                team_implied_total=19.0,
                pregame_expected_routes=24.0,
                pregame_expected_targets=6.0,
                pregame_expected_carries=14.0,
            ),
        ]
    )
    audits = {row["player_id"]: row for row in result.audit_rows}
    favorite_codes = set(audits["favorite-back"]["reason_codes"])
    underdog_codes = set(audits["underdog-back"]["reason_codes"])

    assert {
        "favorite_running_back",
        "favorite_goal_line_running_back",
        "strong_red_zone_involvement",
    } <= favorite_codes
    assert {
        "underdog_receiving_volume",
        "underdog_early_down_running_back",
    } <= underdog_codes
    assert all(not row["rule_evaluation"]["excluded"] for row in result.audit_rows)


def test_h2h_role_stability_outscores_explicit_uncertainty() -> None:
    result = _score(
        [
            _row("stable"),
            _row("uncertain", pregame_role_uncertain=True),
        ],
        objective="cash",
    )
    rows = result.scored_pool.set_index("player_id")

    assert rows.loc["stable", "optimizer_context_adjustment"] > 0.0
    assert rows.loc["uncertain", "optimizer_context_adjustment"] < 0.0
    uncertain = next(row for row in result.audit_rows if row["player_id"] == "uncertain")
    assert "uncertain_current_role" in uncertain["reason_codes"]


def test_missing_context_warns_without_blocking_or_changing_projection() -> None:
    result = _score(
        [
            {
                "player_id": "missing-wr",
                "name": "Missing WR",
                "position": "WR",
                "projection": 12.0,
                "p90": 20.0,
            },
            {
                "player_id": "dst",
                "name": "Defense",
                "position": "DST",
                "projection": 8.0,
                "p90": 14.0,
            },
        ]
    )
    rows = result.scored_pool.set_index("player_id")
    audits = {row["player_id"]: row for row in result.audit_rows}

    assert rows.loc["missing-wr", "optimizer_context_adjustment"] == 0.0
    assert rows.loc["missing-wr", "optimizer_context_mean_score"] == 12.0
    assert set(warning["reason_code"] for warning in audits["missing-wr"]["warnings"]) == {
        "game_environment_missing",
        "current_opportunity_missing",
    }
    assert audits["dst"]["warnings"] == []
    assert result.summary["library_id"] == PLAYER_CONTEXT_LIBRARY_ID
    assert result.summary["library_version"] == PLAYER_CONTEXT_LIBRARY_VERSION
    assert result.summary["status"] == "degraded"
    assert result.summary["processed_count"] == 2
    assert result.summary["offensive_player_count"] == 1
    assert result.summary["context_evaluable_count"] == 0
    assert result.summary["market_context_count"] == 0
    assert result.summary["opportunity_context_count"] == 0
    assert result.summary["adjusted_count"] == 0
    assert result.summary["gpp_context_warning"]["reason_code"] == (
        "gpp_game_context_unavailable"
    )


def test_mutable_market_fallback_is_not_used_for_scoring() -> None:
    result = _score(
        [_row("unsafe-market", market_context_point_in_time_safe=False)]
    )
    audit = result.audit_rows[0]

    assert "game_environment_missing" in {
        warning["reason_code"] for warning in audit["warnings"]
    }
    assert "high_game_total" not in audit["reason_codes"]
    assert "high_implied_team_total" not in audit["reason_codes"]
    assert audit["evidence"]["point_in_time_safe"] is False


def test_market_context_without_explicit_lineage_safety_fails_closed() -> None:
    row = _row("unmarked-market")
    row.pop("market_context_point_in_time_safe")

    result = _score([row])
    audit = result.audit_rows[0]

    assert audit["evidence"]["market_available"] is False
    assert "game_environment_missing" in {
        warning["reason_code"] for warning in audit["warnings"]
    }
    assert result.summary["market_context_count"] == 0


def test_context_scored_pool_remains_solvable_for_classic_and_showdown() -> None:
    classic_positions = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "WR", "DST"]
    classic_teams = ["AAA", "AAA", "BBB", "AAA", "BBB", "BBB", "CCC", "CCC", "CCC"]
    opponents = {"AAA": "BBB", "BBB": "AAA", "CCC": "DDD"}
    classic_rows = [
        _row(
            f"classic-{index}",
            position=position,
            salary=5000,
            player_team=team,
            opponent_team=opponents[team],
        )
        for index, (position, team) in enumerate(zip(classic_positions, classic_teams))
    ]
    classic = _score(classic_rows).scored_pool
    service = OptimizerService.__new__(OptimizerService)

    classic_lineup = service._solve_lineup(
        classic,
        score_col="optimizer_context_ceiling_score",
        contest_type="classic",
        stack_params={"enabled": False},
    )
    assert classic_lineup is not None
    assert len(classic_lineup) == 9

    showdown_rows = [
        _row(
            f"showdown-{index}",
            position="QB" if index in {0, 3} else "WR",
            salary=5000,
            player_team="AAA" if index < 3 else "BBB",
            opponent_team="BBB" if index < 3 else "AAA",
        )
        for index in range(6)
    ]
    showdown = score_player_context(
        pd.DataFrame(showdown_rows),
        profile=resolve_strategy_profile(
            contest_format="showdown",
            objective="gpp",
        ),
    ).scored_pool
    showdown_lineup = service._solve_lineup(
        showdown,
        score_col="optimizer_context_ceiling_score",
        contest_type="captain",
        stack_params={"enabled": False},
    )
    assert showdown_lineup is not None
    assert len(showdown_lineup) == 6
    assert sum(row["roster_position"] == "CPT" for row in showdown_lineup) == 1
