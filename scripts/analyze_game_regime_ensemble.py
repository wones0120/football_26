from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import and_, select

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal
from backend.app.models import PlayerGameFeatureMatrix
from backend.app.services.residual_learning import game_regime
from scripts.compare_projection_model_families import (
    FEATURE_NAMES,
    POSITIONS,
    _feature_vector,
    _fit_regression_tree,
    _predict_regression_tree,
    _slice_key,
    _value,
    chronological_split,
    regression_metrics,
)


DEFAULT_PRIOR_STRENGTHS = [100.0, 250.0, 500.0, 1000.0]
DEFAULT_MIN_CELL_ROWS = [150, 300, 600]
DEFAULT_MAX_DEPTH = 6
DEFAULT_GLOBAL_MIN_LEAF = 60
DEFAULT_SPECIALIST_MIN_LEAF = 30
MINIMUM_TEST_MAE_LIFT_PCT = 0.5
MINIMUM_IMPROVED_SLICE_RATE = 0.6


def _optional_number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _actual_points(row: Any) -> float | None:
    return _optional_number(_value(row, "dk_points"))


def _model_ready_rows(rows: list[Any]) -> list[Any]:
    return [
        row
        for row in rows
        if str(_value(row, "position", "") or "").strip().upper()
        in POSITIONS
        and _actual_points(row) is not None
    ]


def regime_cell(row: Any) -> str:
    position = str(_value(row, "position", "") or "").strip().upper()
    regime = game_regime(
        game_total_line=_optional_number(_value(row, "game_total_line")),
        team_spread_line=_optional_number(_value(row, "team_spread_line")),
    )
    return f"{regime}|{position or 'UNKNOWN'}"


def _regime_name(cell: str) -> str:
    return cell.split("|", 1)[0]


@dataclass
class FittedTree:
    x_mean: np.ndarray
    x_std: np.ndarray
    tree: Any
    training_rows: int
    trained_through: tuple[int, int]

    def predict(self, rows: list[Any]) -> np.ndarray:
        if not rows:
            return np.asarray([], dtype=float)
        x_rows = np.vstack([_feature_vector(row) for row in rows])
        standardized = (x_rows - self.x_mean) / self.x_std
        return _predict_regression_tree(self.tree, standardized)


@dataclass
class RegimeEnsemble:
    global_model: FittedTree
    specialists: dict[str, FittedTree]
    cell_counts: dict[str, int]
    trained_through: tuple[int, int]


def _fit_tree(
    rows: list[Any],
    *,
    max_depth: int,
    min_leaf: int,
) -> FittedTree:
    ready = _model_ready_rows(rows)
    if not ready:
        raise ValueError("At least one model-ready row is required.")
    x_rows = np.vstack([_feature_vector(row) for row in ready])
    y_rows = np.asarray(
        [float(_actual_points(row)) for row in ready],
        dtype=float,
    )
    x_mean = np.mean(x_rows, axis=0)
    x_std = np.where(
        np.std(x_rows, axis=0) < 1e-6,
        1.0,
        np.std(x_rows, axis=0),
    )
    standardized = (x_rows - x_mean) / x_std
    tree = _fit_regression_tree(
        standardized,
        y_rows,
        max_depth=max_depth,
        min_leaf=min_leaf,
    )
    return FittedTree(
        x_mean=x_mean,
        x_std=x_std,
        tree=tree,
        training_rows=len(ready),
        trained_through=max(_slice_key(row) for row in ready),
    )


def fit_regime_ensemble(
    training_rows: list[Any],
    *,
    minimum_fit_rows: int,
    max_depth: int = DEFAULT_MAX_DEPTH,
    global_min_leaf: int = DEFAULT_GLOBAL_MIN_LEAF,
    specialist_min_leaf: int = DEFAULT_SPECIALIST_MIN_LEAF,
) -> RegimeEnsemble:
    ready = _model_ready_rows(training_rows)
    if minimum_fit_rows < 2 * specialist_min_leaf:
        raise ValueError(
            "minimum_fit_rows must be at least twice specialist_min_leaf."
        )
    global_model = _fit_tree(
        ready,
        max_depth=max_depth,
        min_leaf=global_min_leaf,
    )
    by_cell: dict[str, list[Any]] = defaultdict(list)
    for row in ready:
        cell = regime_cell(row)
        if _regime_name(cell) != "unknown":
            by_cell[cell].append(row)
    cell_counts = {
        cell: len(cell_rows)
        for cell, cell_rows in by_cell.items()
    }
    specialists = {
        cell: _fit_tree(
            cell_rows,
            max_depth=max_depth,
            min_leaf=specialist_min_leaf,
        )
        for cell, cell_rows in by_cell.items()
        if len(cell_rows) >= minimum_fit_rows
    }
    return RegimeEnsemble(
        global_model=global_model,
        specialists=specialists,
        cell_counts=cell_counts,
        trained_through=global_model.trained_through,
    )


def predict_regime_ensemble(
    model: RegimeEnsemble,
    target_rows: list[Any],
    *,
    prior_strength: float,
    min_cell_rows: int,
) -> list[dict[str, Any]]:
    if prior_strength <= 0.0:
        raise ValueError("prior_strength must be positive.")
    ready = _model_ready_rows(target_rows)
    if not ready:
        return []
    if min(_slice_key(row) for row in ready) <= model.trained_through:
        raise ValueError("Target rows must be strictly later than training rows.")

    global_predictions = model.global_model.predict(ready)
    ensemble_predictions = global_predictions.copy()
    specialist_used = np.zeros(len(ready), dtype=bool)
    blend_weights = np.zeros(len(ready), dtype=float)
    indices_by_cell: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(ready):
        indices_by_cell[regime_cell(row)].append(index)

    for cell, indices in indices_by_cell.items():
        cell_count = model.cell_counts.get(cell, 0)
        specialist = model.specialists.get(cell)
        if (
            _regime_name(cell) == "unknown"
            or specialist is None
            or cell_count < min_cell_rows
        ):
            continue
        rows_for_cell = [ready[index] for index in indices]
        local_predictions = specialist.predict(rows_for_cell)
        weight = float(cell_count / (cell_count + prior_strength))
        index_array = np.asarray(indices, dtype=int)
        ensemble_predictions[index_array] = (
            ((1.0 - weight) * global_predictions[index_array])
            + (weight * local_predictions)
        )
        specialist_used[index_array] = True
        blend_weights[index_array] = weight

    predictions: list[dict[str, Any]] = []
    for index, row in enumerate(ready):
        season, week = _slice_key(row)
        cell = regime_cell(row)
        predictions.append(
            {
                "season": season,
                "week": week,
                "position": (
                    str(_value(row, "position", "") or "").strip().upper()
                ),
                "regime": _regime_name(cell),
                "cell": cell,
                "actual_points": float(_actual_points(row)),
                "global_points": float(global_predictions[index]),
                "ensemble_points": float(ensemble_predictions[index]),
                "specialist_used": bool(specialist_used[index]),
                "blend_weight": float(blend_weights[index]),
                "cell_training_rows": int(
                    model.cell_counts.get(cell, 0)
                ),
                "trained_through_season": model.trained_through[0],
                "trained_through_week": model.trained_through[1],
            }
        )
    return predictions


def _prediction_metrics(
    predictions: list[dict[str, Any]],
) -> dict[str, Any]:
    actual = np.asarray(
        [row["actual_points"] for row in predictions],
        dtype=float,
    )
    global_points = np.asarray(
        [row["global_points"] for row in predictions],
        dtype=float,
    )
    ensemble_points = np.asarray(
        [row["ensemble_points"] for row in predictions],
        dtype=float,
    )
    global_metrics = regression_metrics(actual, global_points)
    ensemble_metrics = regression_metrics(actual, ensemble_points)
    global_mae = float(global_metrics["mae"])
    ensemble_mae = float(ensemble_metrics["mae"])
    return {
        "global": global_metrics,
        "ensemble": ensemble_metrics,
        "mae_lift_pct": (
            ((global_mae - ensemble_mae) / global_mae) * 100.0
            if global_mae > 0.0
            else 0.0
        ),
        "specialist_rows": sum(
            1 for row in predictions if row["specialist_used"]
        ),
        "specialist_coverage": (
            sum(1 for row in predictions if row["specialist_used"])
            / len(predictions)
            if predictions
            else 0.0
        ),
        "known_regime_rows": sum(
            1 for row in predictions if row["regime"] != "unknown"
        ),
        "known_regime_coverage": (
            sum(1 for row in predictions if row["regime"] != "unknown")
            / len(predictions)
            if predictions
            else 0.0
        ),
        "mean_blend_weight_when_used": (
            float(
                np.mean(
                    [
                        row["blend_weight"]
                        for row in predictions
                        if row["specialist_used"]
                    ]
                )
            )
            if any(row["specialist_used"] for row in predictions)
            else 0.0
        ),
    }


def _grouped_metrics(
    predictions: list[dict[str, Any]],
    *,
    field: str,
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in predictions:
        grouped[str(row[field])].append(row)
    return {
        key: _prediction_metrics(group_rows)
        for key, group_rows in sorted(grouped.items())
    }


def select_candidate(
    candidates: dict[str, dict[str, Any]],
) -> str:
    if not candidates:
        raise ValueError("At least one candidate is required.")
    return min(
        candidates,
        key=lambda key: (
            float(candidates[key]["validation"]["ensemble"]["mae"]),
            float(candidates[key]["validation"]["ensemble"]["rmse"]),
            float(candidates[key]["prior_strength"]),
            int(candidates[key]["min_cell_rows"]),
        ),
    )


def _split_metadata(rows: list[Any]) -> dict[str, Any]:
    slices = sorted({_slice_key(row) for row in rows})
    return {
        "rows": len(rows),
        "slices": len(slices),
        "start": {"season": slices[0][0], "week": slices[0][1]},
        "end": {"season": slices[-1][0], "week": slices[-1][1]},
    }


def _code_metadata() -> dict[str, Any]:
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return {
        "code_revision": (
            revision.stdout.strip()
            if revision.returncode == 0
            else "unknown"
        ),
        "code_dirty": bool(dirty.stdout.strip())
        if dirty.returncode == 0
        else None,
    }


def evaluate_game_regime_ensemble(
    rows: list[Any],
    *,
    prior_strengths: list[float],
    min_cell_rows_grid: list[int],
) -> dict[str, Any]:
    if not prior_strengths or not min_cell_rows_grid:
        raise ValueError("Candidate grids cannot be empty.")
    if min(prior_strengths) <= 0.0:
        raise ValueError("All prior strengths must be positive.")
    if min(min_cell_rows_grid) < 2 * DEFAULT_SPECIALIST_MIN_LEAF:
        raise ValueError("min_cell_rows values are too small.")

    ready = _model_ready_rows(rows)
    splits = chronological_split(ready)
    validation_model = fit_regime_ensemble(
        splits["train"],
        minimum_fit_rows=min(min_cell_rows_grid),
    )
    candidates: dict[str, dict[str, Any]] = {}
    for min_cell_rows in sorted(set(min_cell_rows_grid)):
        for prior_strength in sorted(set(prior_strengths)):
            predictions = predict_regime_ensemble(
                validation_model,
                splits["validation"],
                prior_strength=float(prior_strength),
                min_cell_rows=int(min_cell_rows),
            )
            key = (
                f"min_rows={int(min_cell_rows)}:"
                f"prior={float(prior_strength):g}"
            )
            candidates[key] = {
                "min_cell_rows": int(min_cell_rows),
                "prior_strength": float(prior_strength),
                "validation": _prediction_metrics(predictions),
            }

    selected_key = select_candidate(candidates)
    selected = candidates[selected_key]
    selected_validation_predictions = predict_regime_ensemble(
        validation_model,
        splits["validation"],
        prior_strength=float(selected["prior_strength"]),
        min_cell_rows=int(selected["min_cell_rows"]),
    )
    test_training_rows = [
        *splits["train"],
        *splits["validation"],
    ]
    test_model = fit_regime_ensemble(
        test_training_rows,
        minimum_fit_rows=min(min_cell_rows_grid),
    )
    test_predictions = predict_regime_ensemble(
        test_model,
        splits["test"],
        prior_strength=float(selected["prior_strength"]),
        min_cell_rows=int(selected["min_cell_rows"]),
    )
    test_metrics = _prediction_metrics(test_predictions)
    test_by_position = _grouped_metrics(
        test_predictions,
        field="position",
    )
    test_by_regime = _grouped_metrics(
        test_predictions,
        field="regime",
    )
    test_by_slice = _grouped_metrics(
        [
            {
                **row,
                "slice": f"{row['season']}-W{row['week']:02d}",
            }
            for row in test_predictions
        ],
        field="slice",
    )
    improved_slices = sum(
        1
        for metrics in test_by_slice.values()
        if float(metrics["mae_lift_pct"]) > 0.0
    )
    improved_slice_rate = (
        improved_slices / len(test_by_slice)
        if test_by_slice
        else 0.0
    )
    promotion_passed = bool(
        float(selected["validation"]["mae_lift_pct"]) > 0.0
        and float(test_metrics["mae_lift_pct"])
        >= MINIMUM_TEST_MAE_LIFT_PCT
        and float(test_metrics["ensemble"]["rmse"])
        <= float(test_metrics["global"]["rmse"])
        and improved_slice_rate >= MINIMUM_IMPROVED_SLICE_RATE
    )
    feature_hash = hashlib.sha256(
        "\n".join(
            [
                *FEATURE_NAMES,
                "position_by_pregame_total_spread_regime_specialist",
                "sample_size_blend_to_global_tree",
                "sparse_and_unknown_global_fallback",
            ]
        ).encode("utf-8")
    ).hexdigest()
    canonical_identity_rows = sum(
        1
        for row in ready
        if str(_value(row, "player_master_id", "") or "").strip()
    )
    known_regime_rows = sum(
        1
        for row in ready
        if _regime_name(regime_cell(row)) != "unknown"
    )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": {
            "rows": len(ready),
            "slices": len({_slice_key(row) for row in ready}),
            "selected_candidate": selected_key,
            "selected_min_cell_rows": selected["min_cell_rows"],
            "selected_prior_strength": selected["prior_strength"],
            "validation_mae_lift_pct": (
                selected["validation"]["mae_lift_pct"]
            ),
            "test_mae_lift_pct": test_metrics["mae_lift_pct"],
            "test_global_mae": test_metrics["global"]["mae"],
            "test_ensemble_mae": test_metrics["ensemble"]["mae"],
            "test_global_rmse": test_metrics["global"]["rmse"],
            "test_ensemble_rmse": test_metrics["ensemble"]["rmse"],
            "improved_test_slices": improved_slices,
            "test_slices": len(test_by_slice),
            "improved_test_slice_rate": improved_slice_rate,
            "candidate_status": (
                "promotion_candidate"
                if promotion_passed
                else "research_not_promoted"
            ),
            "production_model_changed": False,
            **_code_metadata(),
        },
        "time_split": {
            name: _split_metadata(split_rows)
            for name, split_rows in splits.items()
        },
        "model": {
            "baseline": "global_regression_tree",
            "specialist_cell": "pregame_total_spread_regime|position",
            "global_max_depth": DEFAULT_MAX_DEPTH,
            "global_min_leaf": DEFAULT_GLOBAL_MIN_LEAF,
            "specialist_min_leaf": DEFAULT_SPECIALIST_MIN_LEAF,
            "feature_names": FEATURE_NAMES,
            "feature_set_hash": feature_hash,
            "pregame_regime_inputs": [
                "game_total_line",
                "team_spread_line",
                "position",
            ],
            "unknown_regime_policy": "global_fallback",
            "sparse_cell_policy": "global_fallback",
            "training_windows": {
                "validation_model": {
                    "rows": validation_model.global_model.training_rows,
                    "trained_through": {
                        "season": validation_model.trained_through[0],
                        "week": validation_model.trained_through[1],
                    },
                },
                "untouched_test_model": {
                    "rows": test_model.global_model.training_rows,
                    "trained_through": {
                        "season": test_model.trained_through[0],
                        "week": test_model.trained_through[1],
                    },
                    "policy": (
                        "refit on train plus validation after parameter "
                        "selection and before opening the test window"
                    ),
                },
            },
        },
        "coverage": {
            "rows": len(ready),
            "canonical_identity_rows": canonical_identity_rows,
            "canonical_identity_coverage": (
                canonical_identity_rows / len(ready)
                if ready
                else 0.0
            ),
            "known_pregame_regime_rows": known_regime_rows,
            "known_pregame_regime_coverage": (
                known_regime_rows / len(ready)
                if ready
                else 0.0
            ),
            "identity_policy": (
                "player_master_id coverage is reported, but identity is not "
                "used as a join key or model feature in this row-level comparison"
            ),
            "low_coverage_policy": (
                "unknown regimes and cells below the validation-selected "
                "minimum use the global prediction exactly"
            ),
        },
        "selection": {
            "metric": "validation_ensemble_mae",
            "selected_candidate": selected_key,
            "candidates": candidates,
            "selected_validation_by_position": _grouped_metrics(
                selected_validation_predictions,
                field="position",
            ),
            "selected_validation_by_regime": _grouped_metrics(
                selected_validation_predictions,
                field="regime",
            ),
            "test_used_for_selection": False,
        },
        "test": {
            "overall": test_metrics,
            "by_position": test_by_position,
            "by_regime": test_by_regime,
            "by_slice": test_by_slice,
        },
        "acceptance": {
            "strict_time_split": True,
            "whole_week_boundaries": True,
            "target_or_future_rows_used": False,
            "pregame_features_only": True,
            "canonical_feature_matrix": True,
            "global_fallback_for_sparse_or_unknown": True,
            "minimum_test_mae_lift_pct": (
                MINIMUM_TEST_MAE_LIFT_PCT
            ),
            "minimum_improved_slice_rate": (
                MINIMUM_IMPROVED_SLICE_RATE
            ),
            "promotion_passed": promotion_passed,
            "note": (
                "Validation selects the blend parameters. The later test "
                "window is opened once, and production remains unchanged."
            ),
        },
    }


def _report_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    validation = payload["selection"]["candidates"][
        payload["selection"]["selected_candidate"]
    ]["validation"]
    test = payload["test"]["overall"]
    lines = [
        "# Future-Safe Game-Regime Projection Ensemble",
        "",
        f"- Rows: `{summary['rows']}` across `{summary['slices']}` week slices",
        f"- Selected minimum cell rows: `{summary['selected_min_cell_rows']}`",
        f"- Selected prior strength: `{summary['selected_prior_strength']}`",
        f"- Candidate status: `{summary['candidate_status']}`",
        "- Production model changed: `no`",
        (
            "- Canonical identity coverage: "
            f"`{payload['coverage']['canonical_identity_coverage']:.1%}`"
        ),
        (
            "- Known pregame regime coverage: "
            f"`{payload['coverage']['known_pregame_regime_coverage']:.1%}`"
        ),
        "",
        "## Validation-Selected Candidate",
        "",
        "| Window | Global MAE | Ensemble MAE | MAE lift | Specialist coverage |",
        "|---|---:|---:|---:|---:|",
        (
            f"| validation | {validation['global']['mae']:.3f} | "
            f"{validation['ensemble']['mae']:.3f} | "
            f"{validation['mae_lift_pct']:+.2f}% | "
            f"{validation['specialist_coverage']:.1%} |"
        ),
        (
            f"| untouched test | {test['global']['mae']:.3f} | "
            f"{test['ensemble']['mae']:.3f} | "
            f"{test['mae_lift_pct']:+.2f}% | "
            f"{test['specialist_coverage']:.1%} |"
        ),
        "",
        "## Untouched Test by Position",
        "",
        "| Position | Rows | Global MAE | Ensemble MAE | Lift |",
        "|---|---:|---:|---:|---:|",
    ]
    for position, metrics in payload["test"]["by_position"].items():
        lines.append(
            f"| {position} | {metrics['global']['rows']} | "
            f"{metrics['global']['mae']:.3f} | "
            f"{metrics['ensemble']['mae']:.3f} | "
            f"{metrics['mae_lift_pct']:+.2f}% |"
        )
    lines.extend(
        [
            "",
            "## Untouched Test by Week",
            "",
            "| Slice | Rows | Global MAE | Ensemble MAE | Lift |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for slice_name, metrics in payload["test"]["by_slice"].items():
        lines.append(
            f"| {slice_name} | {metrics['global']['rows']} | "
            f"{metrics['global']['mae']:.3f} | "
            f"{metrics['ensemble']['mae']:.3f} | "
            f"{metrics['mae_lift_pct']:+.2f}% |"
        )
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- Total and spread are pregame schedule inputs.",
            "- Every validation/test prediction is trained only on earlier whole-week slices.",
            "- Unknown and sparse regime-position cells use the global tree exactly.",
            "- Blend parameters are selected on validation; the test window is not used for selection.",
            (
                "- Position/regime test improvements are not promoted when "
                "the same subset did not improve validation."
            ),
            "- The result is research-only and does not change production automatically.",
        ]
    )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate a future-safe global plus game-regime specialist "
            "projection ensemble."
        )
    )
    parser.add_argument("--source-system", default="draftkings")
    parser.add_argument("--season-start", type=int, default=2024)
    parser.add_argument("--season-end", type=int, default=2025)
    parser.add_argument(
        "--prior-strengths",
        default=",".join(str(value) for value in DEFAULT_PRIOR_STRENGTHS),
    )
    parser.add_argument(
        "--min-cell-rows",
        default=",".join(str(value) for value in DEFAULT_MIN_CELL_ROWS),
    )
    parser.add_argument(
        "--output-json",
        default="docs/game_regime_ensemble_2024_2025.json",
    )
    parser.add_argument(
        "--report-md",
        default="docs/game_regime_ensemble_2024_2025.md",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    season_start = min(args.season_start, args.season_end)
    season_end = max(args.season_start, args.season_end)
    prior_strengths = [
        float(value)
        for value in str(args.prior_strengths).split(",")
        if value.strip()
    ]
    min_cell_rows_grid = [
        int(value)
        for value in str(args.min_cell_rows).split(",")
        if value.strip()
    ]
    with SessionLocal() as session:
        rows = session.execute(
            select(PlayerGameFeatureMatrix).where(
                and_(
                    PlayerGameFeatureMatrix.source_system
                    == args.source_system,
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
    payload = evaluate_game_regime_ensemble(
        rows,
        prior_strengths=prior_strengths,
        min_cell_rows_grid=min_cell_rows_grid,
    )
    payload["summary"].update(
        {
            "source_system": args.source_system,
            "season_start": season_start,
            "season_end": season_end,
        }
    )
    output_path = Path(args.output_json).expanduser().resolve()
    report_path = Path(args.report_md).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        _report_markdown(payload),
        encoding="utf-8",
    )
    print(json.dumps(payload["summary"], indent=2))
    print(f"Wrote JSON: {output_path}")
    print(f"Wrote Markdown: {report_path}")


if __name__ == "__main__":
    main()
