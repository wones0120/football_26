from scripts.analyze_projection_calibration_drift import (
    calibration_drift_summary,
    coverage_metrics,
)


def _row(actual: float, p75: float, p90: float, p95: float, ceiling_prob: float) -> dict:
    return {
        "actual_points": actual,
        "predicted_mean_points": actual + 1.0,
        "predicted_p75_points": p75,
        "predicted_p90_points": p90,
        "predicted_p95_points": p95,
        "predicted_ceiling_prob_25": ceiling_prob,
    }


def test_coverage_metrics_tracks_intervals_and_tail_probability() -> None:
    metrics = coverage_metrics([
        _row(10.0, 12.0, 14.0, 16.0, 0.10),
        _row(30.0, 20.0, 35.0, 40.0, 0.60),
    ])

    assert metrics["players"] == 2
    assert metrics["p75_coverage"] == 0.5
    assert metrics["p90_coverage"] == 1.0
    assert metrics["p95_coverage"] == 1.0
    assert metrics["actual_ceiling_25_rate"] == 0.5
    assert metrics["predicted_ceiling_25_rate"] == 0.35


def test_drift_summary_alerts_on_large_coverage_shift() -> None:
    early = {
        **coverage_metrics([_row(20.0, 25.0, 25.0, 25.0, 0.2) for _ in range(100)]),
        "season": 2024,
        "week": 1,
        "slate": "main",
    }
    late = {
        **coverage_metrics([_row(30.0, 20.0, 20.0, 20.0, 0.2) for _ in range(100)]),
        "season": 2024,
        "week": 2,
        "slate": "main",
    }

    result = calibration_drift_summary(
        [early, late],
        calibration_alert_threshold=0.10,
        drift_alert_threshold=0.08,
        minimum_players=100,
    )

    assert any(
        alert["type"] == "coverage_drift" and alert["metric"] == "p90_coverage"
        for alert in result["alerts"]
    )
