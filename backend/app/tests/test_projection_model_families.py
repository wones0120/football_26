import numpy as np

from scripts.compare_projection_model_families import (
    _fit_regression_tree,
    _predict_regression_tree,
    chronological_split,
    regression_metrics,
)


def test_chronological_split_keeps_whole_weeks_and_time_order() -> None:
    rows = [
        {"season": 2024, "week": week, "row": row}
        for week in range(1, 11)
        for row in range(3)
    ]

    splits = chronological_split(rows)
    train_slices = {(row["season"], row["week"]) for row in splits["train"]}
    validation_slices = {(row["season"], row["week"]) for row in splits["validation"]}
    test_slices = {(row["season"], row["week"]) for row in splits["test"]}

    assert train_slices.isdisjoint(validation_slices)
    assert train_slices.isdisjoint(test_slices)
    assert validation_slices.isdisjoint(test_slices)
    assert max(train_slices) < min(validation_slices)
    assert max(validation_slices) < min(test_slices)
    assert len(splits["train"]) + len(splits["validation"]) + len(splits["test"]) == len(rows)


def test_regression_tree_learns_simple_threshold() -> None:
    x_rows = np.arange(200, dtype=float).reshape(-1, 1)
    y_rows = np.where(x_rows[:, 0] < 100.0, 2.0, 20.0)

    tree = _fit_regression_tree(
        x_rows,
        y_rows,
        max_depth=3,
        min_leaf=10,
    )
    predictions = _predict_regression_tree(tree, x_rows)

    assert regression_metrics(y_rows, predictions)["mae"] < 1.0


def test_regression_metrics_reports_expected_error() -> None:
    metrics = regression_metrics(
        np.asarray([1.0, 2.0, 3.0]),
        np.asarray([2.0, 2.0, 2.0]),
    )

    assert metrics["rows"] == 3
    assert metrics["mae"] == 2.0 / 3.0
    assert metrics["rmse"] == np.sqrt(2.0 / 3.0)
