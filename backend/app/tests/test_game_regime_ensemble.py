from __future__ import annotations

import pytest

from scripts.analyze_game_regime_ensemble import (
    fit_regime_ensemble,
    predict_regime_ensemble,
    regime_cell,
    select_candidate,
)


def _row(
    *,
    week: int,
    index: int,
    total: float | None = 50.0,
    spread: float | None = -2.0,
    position: str = "RB",
    points: float = 10.0,
) -> dict[str, object]:
    return {
        "season": 2025,
        "week": week,
        "player_id": f"player-{week}-{index}",
        "position": position,
        "dk_points": points,
        "salary": 6000,
        "is_home": True,
        "game_total_line": total,
        "team_spread_line": spread,
        "team_implied_total": 26.0,
        "opponent_implied_total": 24.0,
        "player_games_history": 8,
        "player_roll3_mean": points,
        "player_roll8_mean": points,
        "player_roll8_std": 2.0,
        "player_vs_opp_roll4": points,
        "defense_pos_allowed_roll3": points,
        "defense_pos_allowed_roll8": points,
        "defense_pos_allowed_p90_roll8": points + 5.0,
        "kickoff_bucket": "early",
    }


def test_regime_cell_uses_only_pregame_context_and_position() -> None:
    row = _row(week=5, index=1)

    assert regime_cell(row) == "high_total_close|RB"
    row["game_total_line"] = None
    row["team_spread_line"] = None
    assert regime_cell(row) == "unknown|RB"


def test_sparse_or_unknown_cell_uses_global_prediction_exactly() -> None:
    training = [
        _row(
            week=week,
            index=index,
            total=50.0 if index < 50 else 40.0,
            spread=-2.0 if index < 50 else 6.0,
            points=12.0 if index < 50 else 8.0,
        )
        for week in range(1, 5)
        for index in range(100)
    ]
    model = fit_regime_ensemble(
        training,
        minimum_fit_rows=60,
        specialist_min_leaf=30,
    )
    targets = [
        _row(week=5, index=1, total=None, spread=None),
        _row(week=5, index=2, total=45.0, spread=-7.0),
    ]

    predictions = predict_regime_ensemble(
        model,
        targets,
        prior_strength=100.0,
        min_cell_rows=300,
    )

    assert all(row["specialist_used"] is False for row in predictions)
    assert all(
        row["ensemble_points"] == pytest.approx(row["global_points"])
        for row in predictions
    )


def test_predictions_are_trained_only_through_prior_week() -> None:
    training = [
        _row(week=week, index=index, points=10.0 + week)
        for week in range(1, 5)
        for index in range(80)
    ]
    model = fit_regime_ensemble(
        training,
        minimum_fit_rows=60,
        specialist_min_leaf=30,
    )

    predictions = predict_regime_ensemble(
        model,
        [_row(week=5, index=1, points=-100.0)],
        prior_strength=100.0,
        min_cell_rows=60,
    )

    assert model.trained_through == (2025, 4)
    assert predictions[0]["trained_through_week"] == 4
    assert predictions[0]["ensemble_points"] > -100.0


def test_candidate_selection_uses_validation_metrics_only() -> None:
    candidates = {
        "validation-winner": {
            "min_cell_rows": 300,
            "prior_strength": 250.0,
            "validation": {
                "ensemble": {"mae": 2.0, "rmse": 3.0},
            },
        },
        "other": {
            "min_cell_rows": 150,
            "prior_strength": 100.0,
            "validation": {
                "ensemble": {"mae": 2.5, "rmse": 2.0},
            },
        },
    }

    assert select_candidate(candidates) == "validation-winner"


def test_target_rows_must_be_strictly_later_than_training() -> None:
    training = [
        _row(week=week, index=index)
        for week in range(1, 5)
        for index in range(80)
    ]
    model = fit_regime_ensemble(
        training,
        minimum_fit_rows=60,
        specialist_min_leaf=30,
    )

    with pytest.raises(ValueError, match="strictly later"):
        predict_regime_ensemble(
            model,
            [
                _row(week=4, index=999),
                _row(week=5, index=1000),
            ],
            prior_strength=100.0,
            min_cell_rows=60,
        )
