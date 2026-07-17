from scripts.run_classic_parameter_sweep import (
    _parse_float_grid,
    _parse_int_grid,
    _select_best_run,
)


def _run(
    *,
    mean_gap: float,
    median_gap: float,
    completed_rate: float,
    completed: int = 10,
    candidates: int = 200,
) -> dict:
    return {
        "status": "ok",
        "config": {
            "lineups_per_slate": candidates,
            "training_window_slates": 8,
            "classic_top_target_percentile": 98.0,
        },
        "slates_completed": completed,
        "completed_rate": completed_rate,
        "mean_gap_points": mean_gap,
        "median_gap_points": median_gap,
    }


def test_parameter_grid_parsers_deduplicate_and_sort() -> None:
    assert _parse_int_grid("600, 200,600", minimum=100) == [200, 600]
    assert _parse_float_grid("98,95,98", minimum=80.0, maximum=99.5) == [95.0, 98.0]


def test_select_best_run_enforces_coverage_before_gap() -> None:
    low_coverage = _run(mean_gap=80.0, median_gap=75.0, completed_rate=0.4)
    eligible = _run(mean_gap=100.0, median_gap=95.0, completed_rate=0.8)

    assert _select_best_run(
        [low_coverage, eligible],
        min_completed_rate=0.6,
    ) is eligible


def test_select_best_run_uses_lower_cost_config_as_final_tiebreaker() -> None:
    expensive = _run(
        mean_gap=100.0,
        median_gap=95.0,
        completed_rate=0.8,
        candidates=600,
    )
    efficient = _run(
        mean_gap=100.0,
        median_gap=95.0,
        completed_rate=0.8,
        candidates=200,
    )

    assert _select_best_run(
        [expensive, efficient],
        min_completed_rate=0.6,
    ) is efficient
