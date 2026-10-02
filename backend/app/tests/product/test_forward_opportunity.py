"""Shadow opportunity forecasts preserve time ordering and team conservation."""

import pandas as pd
import pytest

from backend.app.product_services.forward_opportunity import (
    STAT_COLUMNS, _blend_role_share, forecast_player_opportunities,
    prepare_weekly_stats, project_components, team_games_from_weekly,
)


def _weekly():
    rows = []
    for week in range(1, 9):
        for pid, pos, attempts, carries, targets in (
            ("qb", "QB", 35, 3, 0),
            ("lead", "RB", 0, 18, 3),
            ("backup", "RB", 0, 6, 2),
            ("receiver", "WR", 0, 1, 9),
        ):
            row = {field: 0.0 for field in STAT_COLUMNS}
            row.update(season=2025, week=week, team="AAA", position=pos,
                       player_master_id=pid, attempts=attempts, carries=carries,
                       targets=targets, completions=24 if pos == "QB" else 0,
                       passing_yards=250 if pos == "QB" else 0,
                       passing_tds=2 if pos == "QB" else 0,
                       passing_interceptions=1 if pos == "QB" else 0,
                       rushing_yards=carries * 4,
                       rushing_tds=1 if pid == "lead" and week % 2 else 0,
                       receptions=targets * 0.7,
                       receiving_yards=targets * 8,
                       receiving_tds=1 if pid == "receiver" and week % 2 else 0)
            rows.append(row)
    return prepare_weekly_stats(pd.DataFrame(rows))


def _targets(lead_importance=0.6):
    return pd.DataFrame([
        {"player_id": "qb", "recent_team": "AAA", "position": "QB", "season": 2026, "week": 1,
         "predicted_mean": 19.0},
        {"player_id": "lead", "recent_team": "AAA", "position": "RB", "season": 2026, "week": 1,
         "offensive_role_importance": lead_importance, "offensive_role_completeness": 1.0,
         "predicted_mean": 17.0},
        {"player_id": "backup", "recent_team": "AAA", "position": "RB", "season": 2026, "week": 1,
         "offensive_role_importance": 0.2, "offensive_role_completeness": 1.0,
         "predicted_mean": 6.0},
        {"player_id": "receiver", "recent_team": "AAA", "position": "WR", "season": 2026, "week": 1,
         "offensive_role_importance": 0.5, "offensive_role_completeness": 1.0,
         "predicted_mean": 16.0},
    ])


def _team_forecast():
    return {"AAA": {"status": "available", "pass_attempts": 34.0,
                    "rush_attempts": 27.0, "offensive_plays_proxy": 61.0,
                    "offensive_tds": 3.0, "targets_per_pass_attempt": 0.9,
                    "rb_carries_per_rush_attempt": 0.85, "pass_td_fraction": 0.7,
                    "volume_confidence": "low", "touchdown_confidence": "low",
                    "features": {"last_observed_period": 202518}}}


def test_role_blend_is_conservative_and_exposes_weights():
    values = pd.Series([0.1] * 7 + [0.6])
    blend = _blend_role_share(values)
    assert blend["weights"] == {"baseline8": 0.4, "recent3": 0.45, "last": 0.15}
    assert 0.1 < blend["forecast"] < 0.6


def test_higher_role_increases_opportunity_and_team_totals_reconcile():
    weekly = _weekly()
    period = 202601
    lower, low_rec = forecast_player_opportunities(
        weekly, _targets(0.3), _team_forecast(), period=period)
    higher, high_rec = forecast_player_opportunities(
        weekly, _targets(0.8), _team_forecast(), period=period)
    low_lead = next(row for row in lower if row["player_id"] == "lead")
    high_lead = next(row for row in higher if row["player_id"] == "lead")
    assert high_lead["expected_carries"] > low_lead["expected_carries"]
    assert high_lead["role_factor"] > low_lead["role_factor"]
    team = high_rec["AAA"]
    assert team["allocated_targets"] + team["unallocated_targets"] == pytest.approx(team["target_budget"])
    assert team["allocated_rb_carries"] + team["unallocated_rb_carries"] == pytest.approx(team["rb_carry_budget"])
    assert (team["allocated_rb_carries"] + team["allocated_qb_carries"]
            + team["allocated_wr_te_carries"] + team["unallocated_rush_attempts"]
            == pytest.approx(team["expected_rush_attempts"]))
    assert team["volume_confidence"] == "low"
    assert team_games_from_weekly(weekly).iloc[0]["offensive_plays_proxy"] == 63


def test_future_game_does_not_change_opportunity_or_components():
    weekly = _weekly()
    forecast = _team_forecast()
    first, _ = forecast_player_opportunities(weekly, _targets(), forecast, period=202601)
    first_components = project_components(weekly, first, forecast, period=202601)
    future = weekly.loc[weekly["week"].eq(8)].copy()
    future["season"] = 2026
    future["week"] = 2
    future["period"] = 202602
    future["targets"] = 1000.0
    future["carries"] = 1000.0
    extended = pd.concat([weekly, future], ignore_index=True)
    second, _ = forecast_player_opportunities(extended, _targets(), _team_forecast(), period=202601)
    second_components = project_components(extended, second, _team_forecast(), period=202601)
    by_first = {row["player_id"]: row for row in first_components}
    by_second = {row["player_id"]: row for row in second_components}
    for player_id in by_first:
        assert by_first[player_id]["expected_targets"] == by_second[player_id]["expected_targets"]
        assert by_first[player_id]["expected_carries"] == by_second[player_id]["expected_carries"]
        assert by_first[player_id]["component_mean"] == by_second[player_id]["component_mean"]


def test_opportunity_sanity_identifies_central_role_workload_mismatch():
    from backend.app.product_services.forward_opportunity import opportunity_sanity
    rows = [
        {"player_id": "lead", "team": "AAA", "position": "RB", "role_importance": 0.8,
         "expected_carries": 3.0, "expected_targets": 2.0},
        {"player_id": "backup", "team": "AAA", "position": "RB", "role_importance": 0.3,
         "expected_carries": 15.0, "expected_targets": 1.0},
    ]
    budget = {"AAA": {"target_budget": 30.0, "allocated_targets": 3.0,
                       "rb_carry_budget": 22.0, "allocated_rb_carries": 18.0,
                       "allocated_qb_carries": 2.0, "allocated_wr_te_carries": 0.0,
                       "expected_rush_attempts": 26.0}}
    codes = {flag["code"] for flag in opportunity_sanity(rows, budget)}
    assert "central_rb_low_carries" in codes
    assert "secondary_exceeds_centerpiece" in codes
    assert "rushes_exceed_budget" not in codes


def test_team_volume_forecast_ignores_future_games():
    from backend.app.product_services.forward_opportunity import forecast_team_volumes
    template = _weekly().loc[_weekly()["week"].eq(1)].drop(columns="period")
    frames = []
    for season in (2023, 2024, 2025):
        for week in range(1, 19):
            for team in ("AAA", "BBB"):
                part = template.copy()
                part["season"] = season
                part["week"] = week
                part["team"] = team
                frames.append(part)
    weekly = prepare_weekly_stats(pd.concat(frames, ignore_index=True))
    contexts = weekly[["season", "week", "team"]].drop_duplicates()
    target = pd.DataFrame([{"season": 2026, "week": 2, "team": "AAA"}])
    first = forecast_team_volumes(weekly, contexts, target, period=202602)
    future = template.copy()
    future["season"] = 2026
    future["week"] = 3
    future["team"] = "AAA"
    future.loc[future["position"].eq("QB"), "attempts"] = 1000
    extended = pd.concat([weekly, prepare_weekly_stats(future)], ignore_index=True)
    second = forecast_team_volumes(extended, contexts, target, period=202602)
    assert first["AAA"]["status"] == "available"
    assert first["AAA"]["pass_attempts"] == pytest.approx(second["AAA"]["pass_attempts"])
    assert first["AAA"]["rush_attempts"] == pytest.approx(second["AAA"]["rush_attempts"])
