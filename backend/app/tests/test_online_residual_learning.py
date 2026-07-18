import pytest

from scripts.analyze_online_residual_learning import (
    ResidualObservation,
    evaluate_prior_strengths,
    fit_residual_model,
    game_regime,
    walk_forward_predictions,
)


def _observation(
    *,
    week: int,
    player: str,
    baseline: float,
    actual: float,
    position: str = "RB",
    team: str = "DAL",
    opponent: str = "NYG",
) -> ResidualObservation:
    return ResidualObservation(
        season=2025,
        week=week,
        player_master_id=player,
        source_player_key=f"dk-{player}",
        team=team,
        opponent=opponent,
        position=position,
        salary=6000,
        game_total_line=47.0,
        team_spread_line=-2.5,
        baseline_points=baseline,
        actual_points=actual,
    )


def test_residual_walk_forward_never_uses_target_or_future_week() -> None:
    observations = [
        _observation(week=1, player="player-a", baseline=10.0, actual=14.0),
        _observation(week=2, player="player-a", baseline=10.0, actual=14.0),
        _observation(week=3, player="player-a", baseline=10.0, actual=14.0),
        _observation(week=4, player="player-a", baseline=10.0, actual=14.0),
        _observation(week=5, player="player-a", baseline=10.0, actual=10.0),
        _observation(week=6, player="player-a", baseline=10.0, actual=-100.0),
    ]

    rows = walk_forward_predictions(
        observations,
        prior_strength=10.0,
        history_window_slices=4,
        min_training_slices=4,
        max_abs_adjustment=20.0,
    )

    week_five = next(row for row in rows if row["week"] == 5)
    assert week_five["adjustment"] > 0.0
    assert week_five["trained_through_week"] == 4


def test_shrinkage_reduces_sparse_player_effect() -> None:
    history = [
        _observation(
            week=week,
            player=f"neutral-{week}",
            baseline=10.0,
            actual=10.0,
        )
        for week in range(1, 21)
    ]
    history.append(
        _observation(
            week=21,
            player="target",
            baseline=10.0,
            actual=30.0,
        )
    )
    target = _observation(
        week=22,
        player="target",
        baseline=10.0,
        actual=10.0,
    )

    weak_shrinkage = fit_residual_model(
        history,
        prior_strength=2.0,
        max_abs_adjustment=100.0,
    ).adjustment_for(target)[0]
    strong_shrinkage = fit_residual_model(
        history,
        prior_strength=80.0,
        max_abs_adjustment=100.0,
    ).adjustment_for(target)[0]

    assert 0.0 < strong_shrinkage < weak_shrinkage < 20.0


def test_strength_selection_uses_validation_not_test(monkeypatch: pytest.MonkeyPatch) -> None:
    observations = [
        _observation(
            week=week,
            player=f"player-{week}",
            baseline=10.0,
            actual=10.0,
        )
        for week in range(1, 9)
    ]

    def fake_walk_forward(
        _observations: list[ResidualObservation],
        *,
        prior_strength: float,
        **_kwargs: object,
    ) -> list[dict[str, object]]:
        rows = []
        for week in range(5, 9):
            is_validation = week <= 6
            adjusted = (
                10.0
                if (prior_strength == 5.0 and is_validation)
                or (prior_strength == 80.0 and not is_validation)
                else 15.0
            )
            rows.append(
                {
                    "season": 2025,
                    "week": week,
                    "position": "RB",
                    "baseline_points": 12.0,
                    "adjusted_points": adjusted,
                    "actual_points": 10.0,
                    "adjustment": adjusted - 12.0,
                    "scopes_used": 1,
                }
            )
        return rows

    monkeypatch.setattr(
        "scripts.analyze_online_residual_learning.walk_forward_predictions",
        fake_walk_forward,
    )
    result = evaluate_prior_strengths(
        observations,
        prior_strengths=[5.0, 80.0],
        history_window_slices=4,
        min_training_slices=4,
        max_abs_adjustment=6.0,
        test_fraction=0.5,
        minimum_test_mae_lift_pct=0.5,
    )

    assert result["selected_prior_strength"] == 5.0
    assert (
        result["candidates"]["80.0"]["test"]["adjusted"]["mae"]
        < result["candidates"]["5.0"]["test"]["adjusted"]["mae"]
    )


@pytest.mark.parametrize(
    ("total", "spread", "expected"),
    [
        (50.0, -2.0, "high_total_close"),
        (50.0, -7.0, "high_total"),
        (40.0, -6.0, "low_total_favorite"),
        (40.0, 6.0, "low_total_underdog"),
        (45.0, 1.0, "mid_total_close"),
        (None, None, "unknown"),
    ],
)
def test_game_regime_is_future_safe_and_deterministic(
    total: float | None,
    spread: float | None,
    expected: str,
) -> None:
    assert (
        game_regime(
            game_total_line=total,
            team_spread_line=spread,
        )
        == expected
    )
