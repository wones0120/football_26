"""Offensive centrality is opportunity-only and time-safe."""
import pandas as pd
import pytest

from backend.app.product_services.offensive_centrality import (
    apply_core_membership, blend_share, calibrate_core_thresholds,
    formulation_scores, historical_prediction_rows, role_class, score_current_players,
)


def test_dual_threat_bonus_preserves_separate_dimensions():
    scores = formulation_scores(0.30, 0.40)
    assert scores["max_dimension"] == pytest.approx(0.40)
    assert scores["max_plus_dual"] == pytest.approx(0.46)
    assert formulation_scores(0.0, 0.40)["max_plus_dual"] == pytest.approx(0.40)


def test_current_centrality_ignores_dfs_and_fantasy_columns():
    target = pd.DataFrame([{
        "player_id": "p1", "player_display_name": "Player", "recent_team": "AAA", "position": "RB",
        "target_share_mean_3": 0.20, "carry_share_mean_3": 0.60,
        "snap_share_mean_3": 0.70, "snap_share_mean_3_available": True,
        "player_games_history": 5, "predicted_mean": 1.0, "predicted_p90": 2.0,
        "salary": 3000, "ownership": 1.0,
    }])
    first = score_current_players(target)[0]
    target.loc[0, ["predicted_mean", "predicted_p90", "salary", "ownership"]] = [100, 200, 10000, 99]
    second = score_current_players(target)[0]
    assert first["receiving_centrality"] == second["receiving_centrality"]
    assert first["rushing_centrality"] == second["rushing_centrality"]
    assert first["overall_centrality"] == second["overall_centrality"]


def test_next_game_population_comes_from_prior_rosters_only():
    rows = []
    for week in range(1, 5):
        players = [("veteran", "WR", 8, 0), ("back", "RB", 2, 15)]
        if week >= 3:
            players.append(("debut", "WR", 10, 0))
        for player_id, position, targets, carries in players:
            rows.append({"season": 2025, "week": week, "team": "AAA",
                         "player_master_id": player_id, "position": position,
                         "targets": targets, "carries": carries})
    predicted = historical_prediction_rows(pd.DataFrame(rows))
    assert not ((predicted["week"].eq(3)) & predicted["player_id"].eq("debut")).any()
    assert ((predicted["week"].eq(4)) & predicted["player_id"].eq("debut")).any()


def test_recent_blend_is_conservative_and_classification_is_ordered():
    blended = blend_share([0.1] * 7 + [0.7])
    assert 0.1 < blended["value"] < 0.7
    assert blended["weights"] == {"baseline8": 0.4, "recent3": 0.45, "last": 0.15}
    assert role_class(0.95, receiving_raw=0.30) == "offensive centerpiece"
    assert role_class(0.05) == "peripheral"


def test_snap_share_cannot_create_rushing_centrality_without_carries():
    target = pd.DataFrame([{
        "player_id": "wr", "player_display_name": "Receiver", "recent_team": "AAA", "position": "WR",
        "target_share_mean_3": 0.25, "carry_share_mean_3": 0.0,
        "snap_share_mean_3": 1.0, "snap_share_mean_3_available": True,
        "player_games_history": 5,
    }])
    scored = score_current_players(target)[0]
    assert scored["rushing_centrality"] == 0.0
    assert scored["receiving_centrality_raw"] <= 0.25


def test_rushing_and_receiving_are_normalized_independently_within_team():
    target = pd.DataFrame([
        {"player_id": "rb", "player_display_name": "Back", "recent_team": "AAA", "position": "RB",
         "target_share_mean_3": 0.10, "carry_share_mean_3": 0.60, "player_games_history": 5},
        {"player_id": "wr", "player_display_name": "Receiver", "recent_team": "AAA", "position": "WR",
         "target_share_mean_3": 0.30, "carry_share_mean_3": 0.0, "player_games_history": 5},
    ])
    by_id = {row["player_id"]: row for row in score_current_players(target, "max_dimension")}
    assert by_id["rb"]["rushing_centrality"] == pytest.approx(1.0)
    assert by_id["wr"]["receiving_centrality"] == pytest.approx(1.0)
    assert by_id["rb"]["overall_centrality"] == pytest.approx(1.0)
    assert by_id["wr"]["overall_centrality"] == pytest.approx(1.0)


def test_core_membership_is_union_of_independent_dimensions():
    calibration = {
        "receiving": {"selected": {"threshold": 0.8, "rank_limit": 2}},
        "rushing": {"selected": {"threshold": 0.8, "rank_limit": 2}},
        "dual_threat": {
            "selected": {"receiving_threshold": 0.6, "rushing_threshold": 0.6}
        },
        "overall": {"selected": {"threshold": 0.9, "rank_limit": 2}},
    }
    rows = [
        {"team": "AAA", "player_id": "receiver", "player": "Receiver",
         "receiving_centrality": 0.95, "rushing_centrality": 0.0,
         "overall_centrality": 0.55},
        {"team": "AAA", "player_id": "runner", "player": "Runner",
         "receiving_centrality": 0.1, "rushing_centrality": 0.95,
         "overall_centrality": 0.85},
        {"team": "AAA", "player_id": "dual", "player": "Dual",
         "receiving_centrality": 0.7, "rushing_centrality": 0.7,
         "overall_centrality": 0.92},
    ]

    by_id = {row["player_id"]: row for row in apply_core_membership(rows, calibration)}

    assert by_id["receiver"]["receiving_core"] is True
    assert by_id["receiver"]["overall_core"] is True
    assert by_id["receiver"]["football_classification"] == "core receiving player"
    assert by_id["runner"]["rushing_core"] is True
    assert by_id["runner"]["overall_core"] is True
    assert by_id["runner"]["football_classification"] == "core rushing player"
    assert by_id["dual"]["dual_threat_core"] is True
    assert by_id["dual"]["football_classification"] == "offensive centerpiece"


def test_core_threshold_calibration_reports_precision_recall_tradeoffs():
    rows = []
    for period in range(202501, 202506):
        for team in ("AAA", "BBB"):
            rows.extend([
                {"period": period, "team": team, "player_id": f"{team}-one",
                 "receiving_centrality": 1.0, "rushing_centrality": 0.2,
                 "monotonic_fitted": 0.9, "actual_target_share": 0.45,
                 "actual_carry_share": 0.05, "actual_overall": 1.0},
                {"period": period, "team": team, "player_id": f"{team}-two",
                 "receiving_centrality": 0.85, "rushing_centrality": 1.0,
                 "monotonic_fitted": 0.85, "actual_target_share": 0.30,
                 "actual_carry_share": 0.70, "actual_overall": 0.9},
                {"period": period, "team": team, "player_id": f"{team}-three",
                 "receiving_centrality": 0.4, "rushing_centrality": 0.4,
                 "monotonic_fitted": 0.4, "actual_target_share": 0.10,
                 "actual_carry_share": 0.10, "actual_overall": 0.4},
            ])
    calibrated = calibrate_core_thresholds(pd.DataFrame(rows))

    for dimension in ("receiving", "rushing", "overall"):
        selected = calibrated[dimension]["selected"]
        assert selected["top_1_recall"] == pytest.approx(1.0)
        assert 0.0 <= selected["top_2_recall"] <= 1.0
        assert 0.0 <= selected["false_core_rate"] <= 1.0
        assert len(calibrated[dimension]["candidates"]) > 1
    assert calibrated["receiving"]["selected"]["top_2_recall"] == pytest.approx(1.0)
    assert calibrated["dual_threat"]["candidates"]
