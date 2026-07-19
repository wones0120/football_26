from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal
from backend.app.models import CuratedSalary, RawNflWeeklyStat
from backend.app.services.lineup_learning import LineupLearningService
from backend.app.services.residual_learning import (
    ELIGIBLE_POSITIONS,
    SCOPE_PRIOR_MULTIPLIERS,
    ResidualObservation,
    fit_residual_model,
    game_regime,
    slice_key as _slice_key,
    team_key as _team_key,
)
from backend.app.services.simulation import (
    SimulationService,
    calculate_dk_points,
    normalize_position,
)


def _history_for_slice(
    observations: list[ResidualObservation],
    *,
    target_slice: tuple[int, int],
    history_window_slices: int,
) -> tuple[list[ResidualObservation], list[tuple[int, int]]]:
    prior_slices = sorted(
        {
            row.slice_key
            for row in observations
            if row.slice_key < target_slice
        }
    )
    selected_slices = prior_slices[-history_window_slices:]
    selected_set = set(selected_slices)
    return (
        [row for row in observations if row.slice_key in selected_set],
        selected_slices,
    )


def walk_forward_predictions(
    observations: list[ResidualObservation],
    *,
    prior_strength: float,
    history_window_slices: int,
    min_training_slices: int,
    max_abs_adjustment: float,
) -> list[dict[str, Any]]:
    if history_window_slices < 1:
        raise ValueError("history_window_slices must be at least 1.")
    if min_training_slices < 1:
        raise ValueError("min_training_slices must be at least 1.")
    if min_training_slices > history_window_slices:
        raise ValueError("min_training_slices cannot exceed history_window_slices.")

    predictions: list[dict[str, Any]] = []
    target_slices = sorted({row.slice_key for row in observations})
    for target_slice in target_slices:
        history, history_slices = _history_for_slice(
            observations,
            target_slice=target_slice,
            history_window_slices=history_window_slices,
        )
        if len(history_slices) < min_training_slices:
            continue
        model = fit_residual_model(
            history,
            prior_strength=prior_strength,
            max_abs_adjustment=max_abs_adjustment,
        )
        if model.trained_through >= target_slice:
            raise AssertionError("Residual model included the target or a future week.")

        for observation in observations:
            if observation.slice_key != target_slice:
                continue
            adjustment, scopes_used = model.adjustment_for(observation)
            predictions.append(
                {
                    "season": observation.season,
                    "week": observation.week,
                    "position": observation.position,
                    "baseline_points": observation.baseline_points,
                    "adjusted_points": max(
                        0.0,
                        observation.baseline_points + adjustment,
                    ),
                    "actual_points": observation.actual_points,
                    "adjustment": adjustment,
                    "scopes_used": scopes_used,
                    "training_rows": model.training_rows,
                    "training_slices": model.training_slices,
                    "trained_through_season": model.trained_through[0],
                    "trained_through_week": model.trained_through[1],
                }
            )
    return predictions


def _prediction_metrics(
    rows: list[dict[str, Any]],
    *,
    prediction_field: str,
) -> dict[str, float | int]:
    if not rows:
        raise ValueError("Prediction metrics require at least one row.")
    predicted = np.asarray(
        [float(row[prediction_field]) for row in rows],
        dtype=float,
    )
    actual = np.asarray(
        [float(row["actual_points"]) for row in rows],
        dtype=float,
    )
    error = predicted - actual
    return {
        "rows": int(actual.size),
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(np.square(error)))),
        "mean_error": float(np.mean(error)),
    }


def comparison_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    baseline = _prediction_metrics(rows, prediction_field="baseline_points")
    adjusted = _prediction_metrics(rows, prediction_field="adjusted_points")
    baseline_mae = float(baseline["mae"])
    baseline_rmse = float(baseline["rmse"])
    adjustments = np.asarray(
        [float(row["adjustment"]) for row in rows],
        dtype=float,
    )
    return {
        "baseline": baseline,
        "adjusted": adjusted,
        "mae_lift_pct": (
            ((baseline_mae - float(adjusted["mae"])) / baseline_mae) * 100.0
            if baseline_mae > 1e-12
            else 0.0
        ),
        "rmse_lift_pct": (
            ((baseline_rmse - float(adjusted["rmse"])) / baseline_rmse) * 100.0
            if baseline_rmse > 1e-12
            else 0.0
        ),
        "mean_abs_adjustment": float(np.mean(np.abs(adjustments))),
        "adjustment_rate": float(np.mean(np.abs(adjustments) > 1e-9)),
        "mean_scopes_used": float(
            np.mean([float(row["scopes_used"]) for row in rows])
        ),
    }


def _split_evaluation_slices(
    prediction_rows: list[dict[str, Any]],
    *,
    test_fraction: float,
) -> tuple[set[tuple[int, int]], set[tuple[int, int]]]:
    if not 0.0 < test_fraction < 1.0:
        raise ValueError("test_fraction must be between 0 and 1.")
    slices = sorted(
        {
            _slice_key(int(row["season"]), int(row["week"]))
            for row in prediction_rows
        }
    )
    if len(slices) < 4:
        raise ValueError("At least four evaluated week slices are required.")
    test_count = max(2, int(math.ceil(len(slices) * test_fraction)))
    test_count = min(test_count, len(slices) - 2)
    return set(slices[:-test_count]), set(slices[-test_count:])


def evaluate_prior_strengths(
    observations: list[ResidualObservation],
    *,
    prior_strengths: list[float],
    history_window_slices: int,
    min_training_slices: int,
    max_abs_adjustment: float,
    test_fraction: float,
    minimum_test_mae_lift_pct: float,
) -> dict[str, Any]:
    if not prior_strengths:
        raise ValueError("At least one prior strength is required.")
    all_predictions = {
        float(prior_strength): walk_forward_predictions(
            observations,
            prior_strength=float(prior_strength),
            history_window_slices=history_window_slices,
            min_training_slices=min_training_slices,
            max_abs_adjustment=max_abs_adjustment,
        )
        for prior_strength in prior_strengths
    }
    first_rows = next(iter(all_predictions.values()))
    validation_slices, test_slices = _split_evaluation_slices(
        first_rows,
        test_fraction=test_fraction,
    )

    candidates: dict[str, dict[str, Any]] = {}
    for prior_strength, rows in all_predictions.items():
        validation_rows = [
            row
            for row in rows
            if _slice_key(int(row["season"]), int(row["week"]))
            in validation_slices
        ]
        test_rows = [
            row
            for row in rows
            if _slice_key(int(row["season"]), int(row["week"])) in test_slices
        ]
        candidates[str(prior_strength)] = {
            "validation": comparison_metrics(validation_rows),
            "test": comparison_metrics(test_rows),
        }

    selected_prior_strength = min(
        all_predictions,
        key=lambda value: (
            float(candidates[str(value)]["validation"]["adjusted"]["mae"]),
            float(value),
        ),
    )
    selected_rows = all_predictions[selected_prior_strength]
    selected_validation_rows = [
        row
        for row in selected_rows
        if _slice_key(int(row["season"]), int(row["week"])) in validation_slices
    ]
    selected_test_rows = [
        row
        for row in selected_rows
        if _slice_key(int(row["season"]), int(row["week"])) in test_slices
    ]
    validation_metrics = comparison_metrics(selected_validation_rows)
    test_metrics = comparison_metrics(selected_test_rows)
    improves_bias = abs(float(test_metrics["adjusted"]["mean_error"])) <= abs(
        float(test_metrics["baseline"]["mean_error"])
    )
    promotion_candidate = (
        float(test_metrics["mae_lift_pct"]) >= minimum_test_mae_lift_pct
        and improves_bias
    )

    by_position = {
        position: comparison_metrics(
            [
                row
                for row in selected_test_rows
                if str(row["position"]) == position
            ]
        )
        for position in sorted(
            {str(row["position"]) for row in selected_test_rows}
        )
    }
    slice_results = []
    for season, week in sorted(
        {
            _slice_key(int(row["season"]), int(row["week"]))
            for row in selected_rows
        }
    ):
        slice_rows = [
            row
            for row in selected_rows
            if _slice_key(int(row["season"]), int(row["week"]))
            == (season, week)
        ]
        slice_results.append(
            {
                "season": season,
                "week": week,
                "window": (
                    "validation"
                    if (season, week) in validation_slices
                    else "test"
                ),
                **comparison_metrics(slice_rows),
            }
        )

    return {
        "selected_prior_strength": selected_prior_strength,
        "validation_slices": sorted(validation_slices),
        "test_slices": sorted(test_slices),
        "candidates": candidates,
        "selected": {
            "validation": validation_metrics,
            "test": test_metrics,
            "test_by_position": by_position,
            "slice_results": slice_results,
        },
        "acceptance": {
            "minimum_test_mae_lift_pct": minimum_test_mae_lift_pct,
            "test_mae_gate_passed": (
                float(test_metrics["mae_lift_pct"])
                >= minimum_test_mae_lift_pct
            ),
            "test_mean_bias_not_worse": improves_bias,
            "promotion_candidate": promotion_candidate,
            "production_model_changed": False,
        },
    }


def _actual_points_by_master(
    *,
    session: Session,
    season: int,
    week: int,
    tracked_player_ids: list[str],
    player_id_to_masters: dict[str, set[str]],
) -> dict[str, float]:
    if not tracked_player_ids:
        return {}
    rows = session.execute(
        select(RawNflWeeklyStat).where(
            and_(
                RawNflWeeklyStat.source_system == "nflreadpy",
                RawNflWeeklyStat.season == season,
                RawNflWeeklyStat.week == week,
                RawNflWeeklyStat.player_id.in_(tracked_player_ids),
            )
        )
    ).scalars().all()
    points_by_master: dict[str, float] = {}
    for row in rows:
        if not row.player_id:
            continue
        points = calculate_dk_points(row.raw_row_json or {})
        if not math.isfinite(points):
            continue
        for master_id in player_id_to_masters.get(row.player_id, set()):
            points_by_master[str(master_id)] = max(
                points_by_master.get(str(master_id), 0.0),
                float(points),
            )
    return points_by_master


def collect_residual_observations(
    *,
    session: Session,
    source_system: str,
    season_start: int,
    season_end: int,
    slate: str,
    iterations: int,
    min_history_games: int,
    prior_weight: float,
    noise_scale: float,
    random_seed: int,
) -> tuple[list[ResidualObservation], dict[str, Any]]:
    simulation_service = SimulationService(session)
    lineup_service = LineupLearningService(session)
    slices = lineup_service._fetch_available_slate_slices(
        source_system=source_system,
        season_start=season_start,
        season_end=season_end,
        slate_filter=slate,
    )
    observations_by_key: dict[
        tuple[int, int, str],
        ResidualObservation,
    ] = {}
    failures: list[dict[str, Any]] = []
    slice_summaries: list[dict[str, Any]] = []

    for season, week, current_slate in slices:
        try:
            (
                players_considered,
                simulated_rows,
                player_id_to_masters,
                tracked_player_ids,
                _role_shock_impacts,
                _point_in_time_shock_impacts,
                _residual_adjustment_impacts,
                _residual_snapshot_count,
                scenario_warnings,
            ) = simulation_service._simulate_salary_slice(
                source_system=source_system,
                season=season,
                week=week,
                slate=current_slate,
                iterations=iterations,
                min_history_games=min_history_games,
                prior_weight=prior_weight,
                noise_scale=noise_scale,
                random_seed=random_seed,
                use_calibration=True,
                role_shocks=[],
            )
            actual_by_master = _actual_points_by_master(
                session=session,
                season=season,
                week=week,
                tracked_player_ids=tracked_player_ids,
                player_id_to_masters=player_id_to_masters,
            )
            salary_rows = session.execute(
                select(CuratedSalary).where(
                    and_(
                        CuratedSalary.source_system == source_system,
                        CuratedSalary.season == season,
                        CuratedSalary.week == week,
                        CuratedSalary.slate == current_slate,
                    )
                )
            ).scalars().all()
            salary_by_master = {
                str(row.player_master_id): row
                for row in salary_rows
                if row.player_master_id
            }
            salary_by_source = {
                str(row.source_player_key): row
                for row in salary_rows
                if row.source_player_key
            }
            context_by_team = lineup_service._game_context_by_team(
                season=season,
                week=week,
            )

            observations_added = 0
            for row in simulated_rows:
                position = normalize_position(row.get("position"))
                if position not in ELIGIBLE_POSITIONS:
                    continue
                master_id = (
                    str(row["player_master_id"])
                    if row.get("player_master_id")
                    else None
                )
                source_key = (
                    str(row["source_player_key"])
                    if row.get("source_player_key")
                    else None
                )
                if not master_id and not source_key:
                    continue
                actual_points = actual_by_master.get(master_id or "")
                if actual_points is None:
                    continue
                salary_row = (
                    salary_by_master.get(master_id or "")
                    or salary_by_source.get(source_key or "")
                )
                team = _team_key(
                    (salary_row.team if salary_row is not None else None)
                    or row.get("team")
                )
                context = context_by_team.get(team, {})
                identity = (
                    f"master:{master_id}"
                    if master_id
                    else f"source:{source_key}"
                )
                observation = ResidualObservation(
                    season=season,
                    week=week,
                    player_master_id=master_id,
                    source_player_key=source_key,
                    team=team or None,
                    opponent=(
                        _team_key(salary_row.opponent) or None
                        if salary_row is not None
                        else None
                    ),
                    position=position,
                    salary=(
                        int(salary_row.salary)
                        if salary_row is not None
                        and salary_row.salary is not None
                        else (
                            int(row["salary"])
                            if row.get("salary") is not None
                            else None
                        )
                    ),
                    game_total_line=(
                        float(context["game_total_line"])
                        if context.get("game_total_line") is not None
                        else None
                    ),
                    team_spread_line=(
                        float(context["team_spread_line"])
                        if context.get("team_spread_line") is not None
                        else None
                    ),
                    baseline_points=float(row["mean_points"]),
                    actual_points=float(actual_points),
                )
                observations_by_key[(season, week, identity)] = observation
                observations_added += 1

            slice_summaries.append(
                {
                    "season": season,
                    "week": week,
                    "slate": current_slate,
                    "players_considered": players_considered,
                    "players_simulated": len(simulated_rows),
                    "observations": observations_added,
                    "warnings": scenario_warnings,
                }
            )
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            failures.append(
                {
                    "season": season,
                    "week": week,
                    "slate": current_slate,
                    "error": str(exc),
                }
            )

    return (
        sorted(
            observations_by_key.values(),
            key=lambda row: (
                row.season,
                row.week,
                row.position,
                row.identity_key or "",
            ),
        ),
        {
            "slates_attempted": len(slices),
            "slates_completed": len(slice_summaries),
            "slates_failed": len(failures),
            "slice_summaries": slice_summaries,
            "failures": failures,
        },
    )


def _git_metadata() -> tuple[str | None, bool | None]:
    revision_result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if revision_result.returncode != 0:
        return None, None
    status_result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    dirty = (
        bool(status_result.stdout.strip())
        if status_result.returncode == 0
        else None
    )
    return revision_result.stdout.strip() or None, dirty


def _format_slice(slice_value: list[int] | tuple[int, int]) -> str:
    return f"{int(slice_value[0])}-W{int(slice_value[1]):02d}"


def _report_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    selection = payload["selection"]
    selected = selection["selected"]
    acceptance = selection["acceptance"]
    status = (
        "promotion candidate for broader integration"
        if acceptance["promotion_candidate"]
        else "research-only; not promoted"
    )
    lines = [
        "# Online Weekly Residual Learning",
        "",
        f"- Slice: `{summary['source_system']} {summary['season_start']}-{summary['season_end']} {summary['slate']}`",
        f"- Historical observations: `{summary['observations']}` across `{summary['slates_completed']}` completed slates.",
        f"- Selected shrinkage strength: `{selection['selected_prior_strength']}` using validation MAE only.",
        f"- Candidate status: `{status}`.",
        "- Production model changed: `no`.",
        "",
        "## Untouched Test Result",
        "",
        "| Metric | Baseline | Residual-adjusted | Lift / Change |",
        "|---|---:|---:|---:|",
        f"| MAE | {selected['test']['baseline']['mae']:.3f} | "
        f"{selected['test']['adjusted']['mae']:.3f} | "
        f"{selected['test']['mae_lift_pct']:+.2f}% |",
        f"| RMSE | {selected['test']['baseline']['rmse']:.3f} | "
        f"{selected['test']['adjusted']['rmse']:.3f} | "
        f"{selected['test']['rmse_lift_pct']:+.2f}% |",
        f"| Mean error | {selected['test']['baseline']['mean_error']:+.3f} | "
        f"{selected['test']['adjusted']['mean_error']:+.3f} | "
        f"{selected['test']['adjusted']['mean_error'] - selected['test']['baseline']['mean_error']:+.3f} |",
        "",
        "## Validation-Only Strength Selection",
        "",
        "| Prior strength | Validation adjusted MAE | Validation lift | Test adjusted MAE | Test lift |",
        "|---:|---:|---:|---:|---:|",
    ]
    for prior_strength, candidate in selection["candidates"].items():
        lines.append(
            f"| {float(prior_strength):.1f} | "
            f"{candidate['validation']['adjusted']['mae']:.3f} | "
            f"{candidate['validation']['mae_lift_pct']:+.2f}% | "
            f"{candidate['test']['adjusted']['mae']:.3f} | "
            f"{candidate['test']['mae_lift_pct']:+.2f}% |"
        )

    lines.extend(
        [
            "",
            "## Test Result by Position",
            "",
            "| Position | Rows | Baseline MAE | Adjusted MAE | Lift | Mean error before | Mean error after |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for position, metrics in selected["test_by_position"].items():
        lines.append(
            f"| {position} | {metrics['baseline']['rows']} | "
            f"{metrics['baseline']['mae']:.3f} | "
            f"{metrics['adjusted']['mae']:.3f} | "
            f"{metrics['mae_lift_pct']:+.2f}% | "
            f"{metrics['baseline']['mean_error']:+.3f} | "
            f"{metrics['adjusted']['mean_error']:+.3f} |"
        )

    lines.extend(
        [
            "",
            "## Walk-Forward Slices",
            "",
            "| Slice | Window | Rows | Baseline MAE | Adjusted MAE | Lift | Mean absolute adjustment |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in selected["slice_results"]:
        lines.append(
            f"| {row['season']}-W{row['week']:02d} | {row['window']} | "
            f"{row['baseline']['rows']} | {row['baseline']['mae']:.3f} | "
            f"{row['adjusted']['mae']:.3f} | {row['mae_lift_pct']:+.2f}% | "
            f"{row['mean_abs_adjustment']:.3f} |"
        )

    lines.extend(
        [
            "",
            "## Time-Safety and Scope",
            "",
            f"- Validation: `{_format_slice(selection['validation_slices'][0])}` through "
            f"`{_format_slice(selection['validation_slices'][-1])}`.",
            f"- Untouched test: `{_format_slice(selection['test_slices'][0])}` through "
            f"`{_format_slice(selection['test_slices'][-1])}`.",
            f"- Rolling history window: `{payload['config']['history_window_slices']}` completed week slices.",
            f"- Maximum absolute adjustment: `{payload['config']['max_abs_adjustment']:.1f}` points.",
            "- Inputs: canonical player identity, team-position, opponent-position, salary bucket, "
            "projected-value bucket, and pre-lock total/spread regime.",
            "- Every target week is scored only from residuals belonging to strictly earlier week slices. "
            "Raw display names are never used as identity keys.",
        ]
    )
    return "\n".join(lines) + "\n"


def _parse_prior_strengths(value: str) -> list[float]:
    strengths = sorted(
        {
            float(item.strip())
            for item in value.split(",")
            if item.strip()
        }
    )
    if not strengths or any(item <= 0.0 for item in strengths):
        raise ValueError("--prior-strengths must contain positive numbers.")
    return strengths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate point-in-time weekly residual adjustments with sample-size "
            "shrinkage and an untouched later test window."
        )
    )
    parser.add_argument(
        "--source-system",
        default="draftkings",
        choices=["draftkings"],
    )
    parser.add_argument("--season-start", type=int, default=2024)
    parser.add_argument("--season-end", type=int, default=2025)
    parser.add_argument("--slate", default="sunday_main")
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--min-history-games", type=int, default=4)
    parser.add_argument("--simulation-prior-weight", type=float, default=12.0)
    parser.add_argument("--noise-scale", type=float, default=0.12)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--history-window-slices", type=int, default=12)
    parser.add_argument("--min-training-slices", type=int, default=4)
    parser.add_argument(
        "--prior-strengths",
        default="5,10,20,40,80",
    )
    parser.add_argument("--max-abs-adjustment", type=float, default=6.0)
    parser.add_argument("--test-fraction", type=float, default=0.40)
    parser.add_argument("--minimum-test-mae-lift-pct", type=float, default=0.5)
    parser.add_argument(
        "--output-json",
        default="docs/online_residual_learning_2024_2025.json",
    )
    parser.add_argument(
        "--report-md",
        default="docs/online_residual_learning_2024_2025.md",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.iterations < 500:
        raise ValueError("--iterations must be at least 500.")
    if args.history_window_slices < 1:
        raise ValueError("--history-window-slices must be at least 1.")
    if args.min_training_slices > args.history_window_slices:
        raise ValueError(
            "--min-training-slices cannot exceed --history-window-slices."
        )
    season_start = min(args.season_start, args.season_end)
    season_end = max(args.season_start, args.season_end)
    prior_strengths = _parse_prior_strengths(args.prior_strengths)

    with SessionLocal() as session:
        observations, collection = collect_residual_observations(
            session=session,
            source_system=args.source_system,
            season_start=season_start,
            season_end=season_end,
            slate=args.slate,
            iterations=args.iterations,
            min_history_games=args.min_history_games,
            prior_weight=args.simulation_prior_weight,
            noise_scale=args.noise_scale,
            random_seed=args.random_seed,
        )
    if not observations:
        raise ValueError("No residual-learning observations were collected.")

    selection = evaluate_prior_strengths(
        observations,
        prior_strengths=prior_strengths,
        history_window_slices=args.history_window_slices,
        min_training_slices=args.min_training_slices,
        max_abs_adjustment=args.max_abs_adjustment,
        test_fraction=args.test_fraction,
        minimum_test_mae_lift_pct=args.minimum_test_mae_lift_pct,
    )
    revision, dirty = _git_metadata()
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": {
            "source_system": args.source_system,
            "season_start": season_start,
            "season_end": season_end,
            "slate": args.slate,
            "observations": len(observations),
            "slates_attempted": collection["slates_attempted"],
            "slates_completed": collection["slates_completed"],
            "slates_failed": collection["slates_failed"],
            "evaluated_slices": len(selection["validation_slices"])
            + len(selection["test_slices"]),
            "code_revision": revision,
            "code_dirty": dirty,
        },
        "config": {
            "iterations": args.iterations,
            "min_history_games": args.min_history_games,
            "simulation_prior_weight": args.simulation_prior_weight,
            "noise_scale": args.noise_scale,
            "random_seed": args.random_seed,
            "history_window_slices": args.history_window_slices,
            "min_training_slices": args.min_training_slices,
            "prior_strengths": prior_strengths,
            "max_abs_adjustment": args.max_abs_adjustment,
            "test_fraction": args.test_fraction,
            "eligible_positions": sorted(ELIGIBLE_POSITIONS),
            "scope_prior_multipliers": SCOPE_PRIOR_MULTIPLIERS,
        },
        "collection": collection,
        "selection": selection,
        "acceptance_notes": [
            "The shrinkage strength is selected only on the earlier validation window.",
            "The later test window is untouched until final evaluation.",
            "Every target uses only strictly earlier completed week slices.",
            "The result is research-only and never changes production automatically.",
        ],
    }

    output_json = Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    report_md = Path(args.report_md)
    report_md.parent.mkdir(parents=True, exist_ok=True)
    report_md.write_text(_report_markdown(payload), encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    print(
        json.dumps(
            {
                "selected_prior_strength": selection[
                    "selected_prior_strength"
                ],
                "validation": selection["selected"]["validation"],
                "test": selection["selected"]["test"],
                "acceptance": selection["acceptance"],
            },
            indent=2,
        )
    )
    print(f"Wrote JSON: {output_json}")
    print(f"Wrote Markdown: {report_md}")


if __name__ == "__main__":
    main()
