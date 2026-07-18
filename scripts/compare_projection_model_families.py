from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import and_, select

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal
from backend.app.models import PlayerGameFeatureMatrix


NUMERIC_FEATURE_NAMES = [
    "salary_k",
    "is_home",
    "game_total_line",
    "team_spread_line",
    "team_implied_total",
    "opponent_implied_total",
    "player_games_history",
    "player_roll3_mean",
    "player_roll8_mean",
    "player_roll8_std",
    "player_vs_opp_roll4",
    "defense_pos_allowed_roll3",
    "defense_pos_allowed_roll8",
    "defense_pos_allowed_p90_roll8",
    "injury_status_score",
    "team_skill_out_count",
    "team_position_out_count",
    "kickoff_early",
    "kickoff_late",
    "kickoff_prime",
    "kickoff_unknown",
]
POSITIONS = ["QB", "RB", "WR", "TE", "DST"]
FEATURE_NAMES = [*NUMERIC_FEATURE_NAMES, *[f"position_{position.lower()}" for position in POSITIONS]]


def _value(row: Any, field: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(field, default)
    return getattr(row, field, default)


def _number(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _injury_status_score(value: Any) -> float:
    normalized = str(value or "").strip().lower()
    if normalized in {"out", "ir", "injured_reserve", "pup"}:
        return -1.0
    if normalized in {"doubtful", "d"}:
        return -0.75
    if normalized in {"questionable", "q"}:
        return -0.35
    if normalized in {"probable", "p"}:
        return -0.10
    return 0.0


def _feature_vector(row: Any) -> np.ndarray:
    kickoff = str(_value(row, "kickoff_bucket", "unknown") or "unknown").strip().lower()
    position = str(_value(row, "position", "") or "").strip().upper()
    vector = [
        _number(_value(row, "salary"), 0.0) / 1000.0,
        1.0 if bool(_value(row, "is_home", False)) else 0.0,
        _number(_value(row, "game_total_line"), 45.0),
        _number(_value(row, "team_spread_line"), 0.0),
        _number(_value(row, "team_implied_total"), 22.0),
        _number(_value(row, "opponent_implied_total"), 22.0),
        _number(_value(row, "player_games_history"), 0.0),
        _number(_value(row, "player_roll3_mean"), 0.0),
        _number(_value(row, "player_roll8_mean"), 0.0),
        _number(_value(row, "player_roll8_std"), 0.0),
        _number(_value(row, "player_vs_opp_roll4"), 0.0),
        _number(_value(row, "defense_pos_allowed_roll3"), 0.0),
        _number(_value(row, "defense_pos_allowed_roll8"), 0.0),
        _number(_value(row, "defense_pos_allowed_p90_roll8"), 0.0),
        _injury_status_score(_value(row, "player_injury_status")),
        _number(_value(row, "team_skill_out_count"), 0.0),
        _number(_value(row, "team_position_out_count"), 0.0),
        1.0 if kickoff == "early" else 0.0,
        1.0 if kickoff == "late" else 0.0,
        1.0 if kickoff == "prime" else 0.0,
        1.0 if kickoff not in {"early", "late", "prime"} else 0.0,
        *[1.0 if position == candidate else 0.0 for candidate in POSITIONS],
    ]
    return np.asarray(vector, dtype=float)


def _slice_key(row: Any) -> tuple[int, int]:
    return int(_value(row, "season")), int(_value(row, "week"))


def chronological_split(
    rows: list[Any],
    *,
    train_fraction: float = 0.70,
    validation_fraction: float = 0.15,
) -> dict[str, list[Any]]:
    if not 0.0 < train_fraction < 1.0:
        raise ValueError("train_fraction must be between 0 and 1.")
    if not 0.0 < validation_fraction < 1.0:
        raise ValueError("validation_fraction must be between 0 and 1.")
    if train_fraction + validation_fraction >= 1.0:
        raise ValueError("train_fraction + validation_fraction must be below 1.")

    ordered_slices = sorted({_slice_key(row) for row in rows})
    if len(ordered_slices) < 3:
        raise ValueError("At least three historical week slices are required.")

    train_count = max(1, int(math.floor(len(ordered_slices) * train_fraction)))
    train_count = min(train_count, len(ordered_slices) - 2)
    validation_count = max(1, int(math.floor(len(ordered_slices) * validation_fraction)))
    validation_count = min(validation_count, len(ordered_slices) - train_count - 1)
    validation_end = train_count + validation_count

    train_slices = set(ordered_slices[:train_count])
    validation_slices = set(ordered_slices[train_count:validation_end])
    test_slices = set(ordered_slices[validation_end:])
    return {
        "train": [row for row in rows if _slice_key(row) in train_slices],
        "validation": [row for row in rows if _slice_key(row) in validation_slices],
        "test": [row for row in rows if _slice_key(row) in test_slices],
    }


def _arrays(rows: list[Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x_rows: list[np.ndarray] = []
    y_rows: list[float] = []
    positions: list[str] = []
    for row in rows:
        target = _number(_value(row, "dk_points"), float("nan"))
        position = str(_value(row, "position", "") or "").strip().upper()
        if not math.isfinite(target) or position not in POSITIONS:
            continue
        x_rows.append(_feature_vector(row))
        y_rows.append(target)
        positions.append(position)
    if not x_rows:
        raise ValueError("No model-ready rows were found.")
    return np.vstack(x_rows), np.asarray(y_rows, dtype=float), np.asarray(positions)


def regression_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float | int]:
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    if actual.shape != predicted.shape or actual.size == 0:
        raise ValueError("actual and predicted must be non-empty arrays with matching shapes.")
    residual = predicted - actual
    denominator = float(np.sum(np.square(actual - float(np.mean(actual)))))
    r_squared = (
        1.0 - (float(np.sum(np.square(residual))) / denominator)
        if denominator > 1e-12
        else 0.0
    )
    return {
        "rows": int(actual.size),
        "mae": float(np.mean(np.abs(residual))),
        "rmse": float(np.sqrt(np.mean(np.square(residual)))),
        "mean_error": float(np.mean(residual)),
        "r_squared": r_squared,
    }


def _fit_ridge(
    x_train: np.ndarray,
    y_train: np.ndarray,
    *,
    alpha: float,
) -> tuple[np.ndarray, float]:
    design = np.column_stack([x_train, np.ones(x_train.shape[0], dtype=float)])
    gram = design.T @ design
    gram[:-1, :-1] += np.eye(x_train.shape[1], dtype=float) * alpha
    rhs = design.T @ y_train
    try:
        coefficients = np.linalg.solve(gram, rhs)
    except np.linalg.LinAlgError:
        coefficients = np.linalg.pinv(gram) @ rhs
    return coefficients[:-1], float(coefficients[-1])


@dataclass
class RegressionTreeNode:
    prediction: float
    feature_index: int | None = None
    threshold: float | None = None
    left: RegressionTreeNode | None = None
    right: RegressionTreeNode | None = None


def _fit_regression_tree(
    x_rows: np.ndarray,
    y_rows: np.ndarray,
    *,
    max_depth: int,
    min_leaf: int,
    depth: int = 0,
) -> RegressionTreeNode:
    node = RegressionTreeNode(prediction=float(np.mean(y_rows)))
    if depth >= max_depth or y_rows.size < (2 * min_leaf) or float(np.var(y_rows)) < 1e-8:
        return node

    parent_sse = float(np.sum(np.square(y_rows - node.prediction)))
    best: tuple[float, int, float, np.ndarray] | None = None
    quantiles = np.linspace(0.10, 0.90, 9)
    for feature_index in range(x_rows.shape[1]):
        values = x_rows[:, feature_index]
        thresholds = np.unique(np.quantile(values, quantiles))
        for threshold in thresholds:
            left_mask = values <= threshold
            left_count = int(np.sum(left_mask))
            right_count = int(y_rows.size - left_count)
            if left_count < min_leaf or right_count < min_leaf:
                continue
            left_y = y_rows[left_mask]
            right_y = y_rows[~left_mask]
            split_sse = float(
                np.sum(np.square(left_y - float(np.mean(left_y))))
                + np.sum(np.square(right_y - float(np.mean(right_y))))
            )
            improvement = parent_sse - split_sse
            if best is None or improvement > best[0]:
                best = (improvement, feature_index, float(threshold), left_mask)

    if best is None or best[0] <= max(1e-8, parent_sse * 0.0005):
        return node
    _, feature_index, threshold, left_mask = best
    node.feature_index = feature_index
    node.threshold = threshold
    node.left = _fit_regression_tree(
        x_rows[left_mask],
        y_rows[left_mask],
        max_depth=max_depth,
        min_leaf=min_leaf,
        depth=depth + 1,
    )
    node.right = _fit_regression_tree(
        x_rows[~left_mask],
        y_rows[~left_mask],
        max_depth=max_depth,
        min_leaf=min_leaf,
        depth=depth + 1,
    )
    return node


def _predict_regression_tree(node: RegressionTreeNode, x_rows: np.ndarray) -> np.ndarray:
    predictions = np.empty(x_rows.shape[0], dtype=float)
    for index, row in enumerate(x_rows):
        current = node
        while (
            current.feature_index is not None
            and current.threshold is not None
            and current.left is not None
            and current.right is not None
        ):
            current = (
                current.left
                if row[current.feature_index] <= current.threshold
                else current.right
            )
        predictions[index] = current.prediction
    return predictions


def _fit_mlp(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_validation: np.ndarray,
    y_validation: np.ndarray,
    *,
    hidden_units: int,
    random_seed: int,
    epochs: int = 60,
    batch_size: int = 512,
    learning_rate: float = 0.002,
    patience: int = 10,
) -> dict[str, Any]:
    rng = np.random.default_rng(random_seed)
    y_mean = float(np.mean(y_train))
    y_std = max(float(np.std(y_train)), 1e-6)
    y_scaled = (y_train - y_mean) / y_std

    w1 = rng.normal(0.0, math.sqrt(2.0 / x_train.shape[1]), (x_train.shape[1], hidden_units))
    b1 = np.zeros(hidden_units, dtype=float)
    w2 = rng.normal(0.0, math.sqrt(1.0 / hidden_units), hidden_units)
    b2 = 0.0
    parameters: list[Any] = [w1, b1, w2, b2]
    first_moments: list[Any] = [np.zeros_like(w1), np.zeros_like(b1), np.zeros_like(w2), 0.0]
    second_moments: list[Any] = [np.zeros_like(w1), np.zeros_like(b1), np.zeros_like(w2), 0.0]
    best_parameters = [w1.copy(), b1.copy(), w2.copy(), b2]
    best_validation_mae = float("inf")
    stale_epochs = 0
    step = 0

    for _epoch in range(epochs):
        epoch_indices = rng.permutation(x_train.shape[0])
        for start in range(0, x_train.shape[0], batch_size):
            indices = epoch_indices[start : start + batch_size]
            xb = x_train[indices]
            yb = y_scaled[indices]
            hidden_linear = xb @ parameters[0] + parameters[1]
            hidden = np.maximum(hidden_linear, 0.0)
            prediction = hidden @ parameters[2] + parameters[3]
            gradient_prediction = (2.0 / max(1, yb.size)) * (prediction - yb)
            gradients: list[Any] = [
                xb.T @ ((gradient_prediction[:, None] * parameters[2][None, :]) * (hidden_linear > 0.0)),
                np.sum(
                    (gradient_prediction[:, None] * parameters[2][None, :])
                    * (hidden_linear > 0.0),
                    axis=0,
                ),
                hidden.T @ gradient_prediction,
                float(np.sum(gradient_prediction)),
            ]
            step += 1
            for index in range(4):
                first_moments[index] = (0.9 * first_moments[index]) + (0.1 * gradients[index])
                second_moments[index] = (0.999 * second_moments[index]) + (
                    0.001 * np.square(gradients[index])
                )
                first_hat = first_moments[index] / (1.0 - (0.9**step))
                second_hat = second_moments[index] / (1.0 - (0.999**step))
                parameters[index] = parameters[index] - (
                    learning_rate * first_hat / (np.sqrt(second_hat) + 1e-8)
                )

        validation_prediction = _predict_mlp(
            {
                "w1": parameters[0],
                "b1": parameters[1],
                "w2": parameters[2],
                "b2": parameters[3],
                "y_mean": y_mean,
                "y_std": y_std,
            },
            x_validation,
        )
        validation_mae = float(np.mean(np.abs(validation_prediction - y_validation)))
        if validation_mae < best_validation_mae - 1e-4:
            best_validation_mae = validation_mae
            best_parameters = [
                parameters[0].copy(),
                parameters[1].copy(),
                parameters[2].copy(),
                float(parameters[3]),
            ]
            stale_epochs = 0
        else:
            stale_epochs += 1
            if stale_epochs >= patience:
                break

    return {
        "w1": best_parameters[0],
        "b1": best_parameters[1],
        "w2": best_parameters[2],
        "b2": best_parameters[3],
        "y_mean": y_mean,
        "y_std": y_std,
        "validation_mae": best_validation_mae,
    }


def _predict_mlp(model: dict[str, Any], x_rows: np.ndarray) -> np.ndarray:
    hidden = np.maximum(x_rows @ model["w1"] + model["b1"], 0.0)
    return model["y_mean"] + (model["y_std"] * (hidden @ model["w2"] + model["b2"]))


def _split_metadata(rows: list[Any]) -> dict[str, Any]:
    slices = sorted({_slice_key(row) for row in rows})
    return {
        "rows": len(rows),
        "slices": len(slices),
        "start": {"season": slices[0][0], "week": slices[0][1]},
        "end": {"season": slices[-1][0], "week": slices[-1][1]},
    }


def _evaluate_family(
    *,
    y_validation: np.ndarray,
    validation_predictions: np.ndarray,
    y_test: np.ndarray,
    test_predictions: np.ndarray,
    test_positions: np.ndarray,
) -> dict[str, Any]:
    return {
        "validation": regression_metrics(y_validation, validation_predictions),
        "test": regression_metrics(y_test, test_predictions),
        "test_by_position": {
            position: regression_metrics(
                y_test[test_positions == position],
                test_predictions[test_positions == position],
            )
            for position in POSITIONS
            if int(np.sum(test_positions == position)) > 0
        },
    }


def compare_model_families(
    rows: list[Any],
    *,
    random_seed: int,
) -> dict[str, Any]:
    splits = chronological_split(rows)
    x_train, y_train, _ = _arrays(splits["train"])
    x_validation, y_validation, _ = _arrays(splits["validation"])
    x_test, y_test, test_positions = _arrays(splits["test"])
    x_mean = np.mean(x_train, axis=0)
    x_std = np.where(np.std(x_train, axis=0) < 1e-6, 1.0, np.std(x_train, axis=0))
    xs_train = (x_train - x_mean) / x_std
    xs_validation = (x_validation - x_mean) / x_std
    xs_test = (x_test - x_mean) / x_std

    baseline_index = FEATURE_NAMES.index("player_roll8_mean")
    baseline_fallback = float(np.mean(y_train))
    baseline_validation = np.where(
        x_validation[:, baseline_index] > 0.0,
        x_validation[:, baseline_index],
        baseline_fallback,
    )
    baseline_test = np.where(
        x_test[:, baseline_index] > 0.0,
        x_test[:, baseline_index],
        baseline_fallback,
    )

    ridge_weights, ridge_bias = _fit_ridge(xs_train, y_train, alpha=1.0)
    ridge_validation = xs_validation @ ridge_weights + ridge_bias
    ridge_test = xs_test @ ridge_weights + ridge_bias

    tree = _fit_regression_tree(xs_train, y_train, max_depth=6, min_leaf=60)
    tree_validation = _predict_regression_tree(tree, xs_validation)
    tree_test = _predict_regression_tree(tree, xs_test)

    mlp = _fit_mlp(
        xs_train,
        y_train,
        xs_validation,
        y_validation,
        hidden_units=24,
        random_seed=random_seed,
    )
    mlp_validation = _predict_mlp(mlp, xs_validation)
    mlp_test = _predict_mlp(mlp, xs_test)

    predictions = {
        "rolling_mean_baseline": (baseline_validation, baseline_test),
        "ridge_linear": (ridge_validation, ridge_test),
        "regression_tree": (tree_validation, tree_test),
        "shallow_neural_net": (mlp_validation, mlp_test),
    }
    families = {
        name: _evaluate_family(
            y_validation=y_validation,
            validation_predictions=family_predictions[0],
            y_test=y_test,
            test_predictions=family_predictions[1],
            test_positions=test_positions,
        )
        for name, family_predictions in predictions.items()
    }
    selected_family = min(
        ("ridge_linear", "regression_tree", "shallow_neural_net"),
        key=lambda name: float(families[name]["validation"]["mae"]),
    )
    return {
        "summary": {
            "rows": len(rows),
            "features": len(FEATURE_NAMES),
            "random_seed": random_seed,
            "selection_metric": "validation_mae",
            "selected_family": selected_family,
            "selected_validation_mae": families[selected_family]["validation"]["mae"],
            "selected_test_mae": families[selected_family]["test"]["mae"],
            "production_model_changed": False,
        },
        "time_split": {
            name: _split_metadata(split_rows)
            for name, split_rows in splits.items()
        },
        "feature_names": FEATURE_NAMES,
        "feature_set_hash": hashlib.sha256(
            "\n".join(FEATURE_NAMES).encode("utf-8")
        ).hexdigest(),
        "families": families,
        "acceptance": {
            "strict_time_split": True,
            "whole_week_boundaries": True,
            "test_used_for_selection": False,
            "note": (
                "The validation winner is reported for research only. "
                "Production projection blending remains gated by its existing walk-forward checks."
            ),
        },
    }


def _report_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Player Projection Model Family Comparison",
        "",
        f"- Rows: `{summary['rows']}`",
        f"- Features: `{summary['features']}`",
        f"- Validation-selected family: `{summary['selected_family']}`",
        f"- Selected validation MAE: `{summary['selected_validation_mae']:.3f}`",
        f"- Untouched test MAE: `{summary['selected_test_mae']:.3f}`",
        "- Production model changed: `no`",
        "",
        "## Strict Time Split",
        "",
        "| Split | Rows | Week slices | Start | End |",
        "|---|---:|---:|---|---|",
    ]
    for name in ("train", "validation", "test"):
        row = payload["time_split"][name]
        lines.append(
            f"| {name} | {row['rows']} | {row['slices']} | "
            f"{row['start']['season']}-W{row['start']['week']:02d} | "
            f"{row['end']['season']}-W{row['end']['week']:02d} |"
        )
    lines.extend([
        "",
        "## Results",
        "",
        "| Family | Validation MAE | Test MAE | Test RMSE | Test R² |",
        "|---|---:|---:|---:|---:|",
    ])
    for name, family in payload["families"].items():
        lines.append(
            f"| {name} | {family['validation']['mae']:.3f} | "
            f"{family['test']['mae']:.3f} | {family['test']['rmse']:.3f} | "
            f"{family['test']['r_squared']:.3f} |"
        )
    lines.extend([
        "",
        "The winner is selected only on the validation window; the later test window is untouched "
        "until final evaluation. This comparison is a research gate and does not automatically replace "
        "the production projection blend.",
    ])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare baseline, linear, tree, and neural player projection families.",
    )
    parser.add_argument("--source-system", default="draftkings")
    parser.add_argument("--season-start", type=int, default=2024)
    parser.add_argument("--season-end", type=int, default=2025)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument(
        "--output-json",
        default="docs/projection_model_family_comparison_2024_2025.json",
    )
    parser.add_argument(
        "--report-md",
        default="docs/projection_model_family_comparison_2024_2025.md",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    season_start = min(args.season_start, args.season_end)
    season_end = max(args.season_start, args.season_end)
    with SessionLocal() as session:
        rows = session.execute(
            select(PlayerGameFeatureMatrix).where(
                and_(
                    PlayerGameFeatureMatrix.source_system == args.source_system,
                    PlayerGameFeatureMatrix.season >= season_start,
                    PlayerGameFeatureMatrix.season <= season_end,
                    PlayerGameFeatureMatrix.position.in_(POSITIONS),
                )
            )
        ).scalars().all()
    if not rows:
        raise ValueError(
            f"No player game feature rows found for {args.source_system} "
            f"seasons {season_start}-{season_end}."
        )

    payload = compare_model_families(rows, random_seed=args.random_seed)
    payload["summary"].update({
        "source_system": args.source_system,
        "season_start": season_start,
        "season_end": season_end,
    })
    output_path = Path(args.output_json).expanduser().resolve()
    report_path = Path(args.report_md).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    report_path.write_text(_report_markdown(payload), encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))


if __name__ == "__main__":
    main()
