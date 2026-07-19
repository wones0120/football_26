from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from backend.app.schemas import UltimateLineupRequest
from backend.app.services.lineup_learning import (
    CONTEST_OBJECTIVE_WEIGHTS,
    LineupLearningService,
)


def _score(
    objective: str,
    *,
    base: list[float],
    mean: list[float],
    p90: list[float],
    policy: list[float],
    ceiling: list[float],
    quality: list[float],
    duplication: list[float],
) -> np.ndarray:
    service = LineupLearningService(session=None)  # type: ignore[arg-type]
    return service._apply_contest_objective(
        contest_objective=objective,
        base_composite_scores=np.asarray(base, dtype=float),
        projected_mean_points=np.asarray(mean, dtype=float),
        projected_p90_points=np.asarray(p90, dtype=float),
        policy_scores=np.asarray(policy, dtype=float),
        ceiling_scores=np.asarray(ceiling, dtype=float),
        quality_scores=np.asarray(quality, dtype=float),
        duplication_risk_scores=np.asarray(duplication, dtype=float),
    )


def test_balanced_objective_preserves_existing_scores_exactly() -> None:
    base = [1.25, -0.5, 0.75]

    result = _score(
        "balanced",
        base=base,
        mean=[1.0, 100.0, -50.0],
        p90=[100.0, 1.0, 50.0],
        policy=[0.1, 0.9, 0.5],
        ceiling=[0.8, 0.2, 0.4],
        quality=[0.2, 0.9, 0.6],
        duplication=[0.9, 0.1, 0.5],
    )

    assert result.tolist() == base
    assert UltimateLineupRequest(
        season=2025,
        week=1,
    ).contest_objective == "balanced"


def test_cash_objective_rewards_mean_and_bust_avoidance() -> None:
    result = _score(
        "cash",
        base=[0.0, 0.0, 0.0],
        mean=[24.0, 18.0, 20.0],
        p90=[25.0, 60.0, 40.0],
        policy=[0.2, 0.9, 0.5],
        ceiling=[0.2, 0.9, 0.5],
        quality=[0.9, 0.2, 0.6],
        duplication=[0.9, 0.1, 0.5],
    )

    assert result[0] > result[2] > result[1]
    assert CONTEST_OBJECTIVE_WEIGHTS["cash"] == {
        "base": 0.25,
        "projected_mean": 0.45,
        "quality": 0.30,
        "policy": 0.0,
        "ceiling": 0.0,
        "projected_p90": 0.0,
        "duplication_risk": 0.0,
    }


def test_gpp_objective_rewards_ceiling_and_proxy_uniqueness() -> None:
    result = _score(
        "gpp",
        base=[0.0, 0.0, 0.0],
        mean=[20.0, 20.0, 20.0],
        p90=[30.0, 40.0, 40.0],
        policy=[0.3, 0.8, 0.8],
        ceiling=[0.3, 0.9, 0.9],
        quality=[0.9, 0.4, 0.4],
        duplication=[0.2, 0.9, 0.1],
    )

    assert result[2] > result[1] > result[0]
    assert CONTEST_OBJECTIVE_WEIGHTS["gpp"]["duplication_risk"] == 0.15


def test_contest_objective_rejects_bad_shape_and_value() -> None:
    service = LineupLearningService(session=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="shape mismatch"):
        service._apply_contest_objective(
            contest_objective="cash",
            base_composite_scores=np.asarray([1.0, 2.0]),
            projected_mean_points=np.asarray([1.0]),
            projected_p90_points=np.asarray([1.0, 2.0]),
            policy_scores=np.asarray([0.1, 0.2]),
            ceiling_scores=np.asarray([0.1, 0.2]),
            quality_scores=np.asarray([0.9, 0.8]),
            duplication_risk_scores=np.asarray([0.1, 0.2]),
        )

    with pytest.raises(ValidationError, match="contest_objective"):
        UltimateLineupRequest(
            season=2025,
            week=1,
            contest_objective="invalid",  # type: ignore[arg-type]
        )
