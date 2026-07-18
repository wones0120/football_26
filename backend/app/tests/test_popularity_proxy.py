import numpy as np
import pytest

from backend.app.schemas import UltimateLineupRequest
from backend.app.services.lineup_learning import (
    LineupLearningService,
    PlayerPoolRow,
    _percentile_ranks,
)


def _player(
    uid: str,
    *,
    position: str,
    salary: int,
    mean: float,
    p90: float,
    implied_total: float,
) -> PlayerPoolRow:
    return PlayerPoolRow(
        uid=uid,
        name=uid,
        team="DAL",
        opponent="NYG",
        position=position,
        salary=salary,
        actual_points=0.0,
        projected_mean_points=mean,
        projected_p90_points=p90,
        team_implied_total=implied_total,
    )


def test_percentile_ranks_are_stable_for_ties() -> None:
    ranks = _percentile_ranks(np.asarray([10.0, 20.0, 20.0, 30.0], dtype=float))

    assert ranks.tolist() == [0.0, 0.5, 0.5, 1.0]


def test_popularity_and_duplication_proxies_follow_pregame_concentration() -> None:
    chalk_wr = _player(
        "chalk_wr",
        position="WR",
        salary=9000,
        mean=25.0,
        p90=36.0,
        implied_total=30.0,
    )
    value_wr = _player(
        "value_wr",
        position="WR",
        salary=5000,
        mean=11.0,
        p90=19.0,
        implied_total=20.0,
    )
    chalk_rb = _player(
        "chalk_rb",
        position="RB",
        salary=8200,
        mean=22.0,
        p90=31.0,
        implied_total=29.0,
    )
    value_rb = _player(
        "value_rb",
        position="RB",
        salary=4800,
        mean=10.0,
        p90=17.0,
        implied_total=19.0,
    )
    players = [chalk_wr, value_wr, chalk_rb, value_rb]
    candidates = [
        [chalk_wr, chalk_rb],
        [chalk_wr, chalk_rb],
        [chalk_wr, chalk_rb],
        [chalk_wr, value_rb],
        [value_wr, value_rb],
    ]
    service = LineupLearningService(session=None)  # type: ignore[arg-type]

    popularity, exposure = service._classic_player_popularity_proxy(
        players=players,
        candidate_lineups=candidates,
    )
    risks = service._classic_lineup_duplication_risk_scores(
        lineups=[[chalk_wr, chalk_rb], [value_wr, value_rb]],
        popularity_by_uid=popularity,
        reference_lineups=candidates,
    )

    assert exposure["chalk_wr"] == pytest.approx(0.8)
    assert exposure["value_wr"] == pytest.approx(0.2)
    assert popularity["chalk_wr"] > popularity["value_wr"]
    assert popularity["chalk_rb"] > popularity["value_rb"]
    assert 0.0 <= risks[1] < risks[0] <= 1.0

    for index, player in enumerate(players):
        player.actual_points = float(index * 100)
    popularity_after_outcomes, exposure_after_outcomes = (
        service._classic_player_popularity_proxy(
            players=players,
            candidate_lineups=candidates,
        )
    )
    assert popularity_after_outcomes == popularity
    assert exposure_after_outcomes == exposure


def test_duplication_penalty_is_opt_in_and_reduces_chalk_advantage() -> None:
    service = LineupLearningService(session=None)  # type: ignore[arg-type]
    composite = np.asarray([1.00, 0.95, 0.90], dtype=float)
    risks = np.asarray([0.95, 0.40, 0.10], dtype=float)

    unchanged = service._apply_duplication_risk_penalty(
        composite_scores=composite,
        duplication_risk_scores=risks,
        penalty_strength=0.0,
    )
    adjusted = service._apply_duplication_risk_penalty(
        composite_scores=composite,
        duplication_risk_scores=risks,
        penalty_strength=0.5,
    )

    assert unchanged.tolist() == composite.tolist()
    assert adjusted[0] - adjusted[2] < composite[0] - composite[2]
    assert UltimateLineupRequest(
        season=2025,
        week=1,
    ).duplication_risk_penalty == 0.0
