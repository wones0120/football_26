from __future__ import annotations

import pytest

from backend.app.services.bootstrap_metrics import bootstrap_confidence_intervals


def test_bootstrap_confidence_intervals_are_deterministic_and_order_stable() -> None:
    metrics = {
        "mean_gap_points": ([1.0, 2.0, 3.0, 4.0], "mean"),
        "median_gap_points": ([1.0, 2.0, 3.0, 4.0], "median"),
    }

    first = bootstrap_confidence_intervals(
        metrics,
        confidence_level=0.95,
        bootstrap_samples=500,
        random_seed=17,
    )
    second = bootstrap_confidence_intervals(
        dict(reversed(metrics.items())),
        confidence_level=0.95,
        bootstrap_samples=500,
        random_seed=17,
    )

    assert first["method"] == "nonparametric_percentile_bootstrap"
    assert first["confidence_level"] == 0.95
    assert first["bootstrap_samples"] == 500
    assert first["random_seed"] == 17
    assert first["metrics"]["mean_gap_points"] == second["metrics"]["mean_gap_points"]
    assert first["metrics"]["median_gap_points"] == second["metrics"]["median_gap_points"]

    mean_interval = first["metrics"]["mean_gap_points"]
    assert mean_interval is not None
    assert mean_interval["estimate"] == 2.5
    assert mean_interval["lower"] <= mean_interval["estimate"] <= mean_interval["upper"]
    assert mean_interval["standard_error"] > 0
    assert mean_interval["sample_size"] == 4


def test_bootstrap_confidence_intervals_support_rates_and_missing_samples() -> None:
    result = bootstrap_confidence_intervals(
        {
            "captain_informed_win_rate": ([1.0, 0.0, 1.0, 1.0], "mean"),
            "missing_metric": ([], "mean"),
        },
        bootstrap_samples=250,
        random_seed=42,
    )

    rate_interval = result["metrics"]["captain_informed_win_rate"]
    assert rate_interval is not None
    assert rate_interval["estimate"] == 0.75
    assert 0.0 <= rate_interval["lower"] <= rate_interval["upper"] <= 1.0
    assert result["metrics"]["missing_metric"] is None


@pytest.mark.parametrize(
    ("confidence_level", "bootstrap_samples"),
    [
        (0.0, 100),
        (1.0, 100),
        (0.95, 0),
    ],
)
def test_bootstrap_confidence_intervals_validate_parameters(
    confidence_level: float,
    bootstrap_samples: int,
) -> None:
    with pytest.raises(ValueError):
        bootstrap_confidence_intervals(
            {"metric": ([1.0], "mean")},
            confidence_level=confidence_level,
            bootstrap_samples=bootstrap_samples,
        )
