from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal
from backend.app.services.lineup_learning import (
    SHOWDOWN_FEATURE_INDEX,
    SHOWDOWN_TOP_TARGET_PERCENTILE,
    LineupLearningService,
    ShowdownLineup,
    _sigmoid,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Walk-forward showdown backtest: exact actual-optimal lineup vs learned-predicted lineup per slate."
        )
    )
    parser.add_argument("--source-system", default="draftkings", choices=["draftkings", "fanduel"])
    parser.add_argument("--season-start", type=int, default=2024)
    parser.add_argument("--season-end", type=int, default=2025)
    parser.add_argument("--slate", type=str, default=None)
    parser.add_argument("--lineups-per-slate", type=int, default=2500)
    parser.add_argument("--training-window-slates", type=int, default=24)
    parser.add_argument("--min-training-slates", type=int, default=2)
    parser.add_argument("--min-training-rows", type=int, default=500)
    parser.add_argument("--learned-only", dest="learned_only", action="store_true")
    parser.add_argument("--allow-heuristics", dest="learned_only", action="store_false")
    parser.set_defaults(learned_only=True)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--limit-slates", type=int, default=0)
    parser.add_argument("--output-json", type=str, default="")
    parser.add_argument("--quiet-progress", action="store_true")
    return parser.parse_args()


def _lineup_to_names(lineup: ShowdownLineup) -> list[str]:
    captain = lineup.captain
    rows = [
        (
            f"CPT:{captain.name}({captain.team or '-'},${captain.captain_salary},"
            f"actual={1.5 * captain.actual_points:.2f},base={captain.actual_points:.2f})"
        )
    ]
    rows.extend(
        f"FLEX:{player.name}({player.team or '-'},${player.flex_salary},actual={player.actual_points:.2f})"
        for player in lineup.flex_players
    )
    return rows


def main() -> None:
    args = parse_args()
    season_start = min(args.season_start, args.season_end)
    season_end = max(args.season_start, args.season_end)
    rng = np.random.default_rng(args.random_seed)

    rows: list[dict] = []
    gaps: list[float] = []
    history_x: list[np.ndarray] = []
    history_y: list[np.ndarray] = []
    history_points: list[np.ndarray] = []

    with SessionLocal() as session:
        service = LineupLearningService(session)
        slices = service._fetch_available_slate_slices(
            source_system=args.source_system,
            season_start=season_start,
            season_end=season_end,
            slate_filter=args.slate,
        )
        slices = service._filter_slices_by_slate_type(
            source_system=args.source_system,
            slices=slices,
            slate_type="showdown",
        )
        if args.limit_slates and args.limit_slates > 0:
            slices = slices[: args.limit_slates]

        for index, (season, week, slate) in enumerate(slices, start=1):
            current_slate_type = "showdown"
            try:
                projection_lookup, dst_projection_lookup = service._compute_player_projection_lookup(
                    source_system=args.source_system,
                    season=season,
                    week=week,
                    slate=slate,
                )
                pool = service._fetch_showdown_player_pool(
                    source_system=args.source_system,
                    season=season,
                    week=week,
                    slate=slate,
                    projection_lookup=projection_lookup,
                    dst_projection_lookup=dst_projection_lookup,
                )
                optimal = service.optimize_actual_showdown_lineup(players=pool)
                if optimal is None:
                    rows.append(
                        {
                            "season": season,
                            "week": week,
                            "slate": slate,
                            "slate_type": current_slate_type,
                            "status": "skipped",
                            "error": "No feasible actual-optimal showdown lineup.",
                        }
                    )
                    continue
                optimal_lineup, optimal_points, optimal_salary = optimal

                x_slate, points_slate, generated_lineups = service._generate_showdown_lineups_for_slate(
                    players=pool,
                    lineups_target=args.lineups_per_slate,
                    rng=rng,
                )
                if len(generated_lineups) == 0:
                    rows.append(
                        {
                            "season": season,
                            "week": week,
                            "slate": slate,
                            "slate_type": current_slate_type,
                            "status": "failed",
                            "error": "No generated showdown candidate lineups.",
                        }
                    )
                    continue

                train_rows = int(sum(chunk.shape[0] for chunk in history_x))
                predicted_lineup: ShowdownLineup | None = None
                policy_score: float | None = None

                if len(history_x) >= args.min_training_slates and train_rows >= args.min_training_rows:
                    x_train = np.vstack(history_x)
                    y_train = np.concatenate(history_y)
                    points_train = np.concatenate(history_points)
                    weights, bias, mean, std = service._fit_logistic(x_train, y_train)
                    probs = _sigmoid(((x_slate - mean) / std) @ weights + bias)
                    (
                        points_weights,
                        points_bias,
                        points_x_mean,
                        points_x_std,
                        points_y_mean,
                        points_y_std,
                        has_point_signal,
                    ) = service._fit_point_regression(x_train, points_train)
                    has_policy_signal = float(np.max(np.abs(weights))) > 1e-8
                    has_learned_signal = has_policy_signal or has_point_signal
                    if has_learned_signal:
                        expected_points = service._predict_point_regression(
                            x_rows=x_slate,
                            weights=points_weights,
                            bias=points_bias,
                            x_mean=points_x_mean,
                            x_std=points_x_std,
                            y_mean=points_y_mean,
                            y_std=points_y_std,
                        )
                        projected_mean = x_slate[:, SHOWDOWN_FEATURE_INDEX["lineup_projected_mean"]]
                        projected_p90 = x_slate[:, SHOWDOWN_FEATURE_INDEX["lineup_projected_p90"]]
                        composite = service._composite_lineup_selection_scores(
                            policy_scores=probs,
                            expected_points=expected_points,
                            projected_mean=projected_mean,
                            projected_p90=projected_p90,
                        )
                        idx = int(np.argmax(composite))
                        predicted_lineup = generated_lineups[idx]
                        policy_score = float(probs[idx])
                    elif not args.learned_only:
                        projected_mean = x_slate[:, SHOWDOWN_FEATURE_INDEX["lineup_projected_mean"]]
                        idx = int(np.argmax(projected_mean))
                        predicted_lineup = generated_lineups[idx]
                        policy_score = None
                elif not args.learned_only:
                    projected_mean = x_slate[:, SHOWDOWN_FEATURE_INDEX["lineup_projected_mean"]]
                    idx = int(np.argmax(projected_mean))
                    predicted_lineup = generated_lineups[idx]
                    policy_score = None

                if predicted_lineup is None:
                    rows.append(
                        {
                            "season": season,
                            "week": week,
                            "slate": slate,
                            "slate_type": current_slate_type,
                            "status": "warmup_or_no_signal",
                            "error": (
                                "Insufficient learned history for learned-only mode."
                                if args.learned_only
                                else "Could not produce predicted lineup."
                            ),
                        }
                    )
                else:
                    predicted_actual_points = service._showdown_actual_points(predicted_lineup)
                    predicted_salary = service._showdown_salary_used(predicted_lineup)
                    predicted_projected_mean = service._showdown_projected_mean(predicted_lineup)
                    predicted_projected_p90 = service._showdown_projected_p90(predicted_lineup)
                    gap = float(optimal_points - predicted_actual_points)
                    gaps.append(gap)
                    rows.append(
                        {
                            "season": season,
                            "week": week,
                            "slate": slate,
                            "slate_type": current_slate_type,
                            "status": "ok",
                            "optimal_actual_points": round(float(optimal_points), 4),
                            "predicted_actual_points": round(float(predicted_actual_points), 4),
                            "gap_points": round(float(gap), 4),
                            "optimal_salary_used": int(optimal_salary),
                            "predicted_salary_used": int(predicted_salary),
                            "predicted_projected_mean_points": round(float(predicted_projected_mean), 4),
                            "predicted_projected_p90_points": round(float(predicted_projected_p90), 4),
                            "predicted_policy_score": round(policy_score, 6) if policy_score is not None else None,
                            "optimal_lineup": _lineup_to_names(optimal_lineup),
                            "predicted_lineup": _lineup_to_names(predicted_lineup),
                        }
                    )

                threshold = float(np.percentile(points_slate, SHOWDOWN_TOP_TARGET_PERCENTILE))
                if np.isfinite(threshold) and float(np.std(points_slate)) > 1e-9:
                    y_slate = (points_slate >= threshold).astype(float)
                    pos_rate = float(np.mean(y_slate))
                    if 0.0 < pos_rate < 1.0:
                        history_x.append(x_slate)
                        history_y.append(y_slate)
                        history_points.append(points_slate)
                while len(history_x) > args.training_window_slates:
                    history_x.pop(0)
                    history_y.pop(0)
                    history_points.pop(0)

                if not args.quiet_progress:
                    status = rows[-1].get("status") if rows else "unknown"
                    print(
                        f"[showdown_backtest] {index}/{len(slices)} {season} W{week:02d} {slate} "
                        f"type={current_slate_type} status={status}",
                        flush=True,
                    )
            except Exception as exc:  # noqa: BLE001
                rows.append(
                    {
                        "season": season,
                        "week": week,
                        "slate": slate,
                        "slate_type": current_slate_type,
                        "status": "failed",
                        "error": str(exc),
                    }
                )
                if not args.quiet_progress:
                    print(
                        f"[showdown_backtest] {index}/{len(slices)} {season} W{week:02d} {slate} "
                        f"type={current_slate_type} status=failed error={exc}",
                        flush=True,
                    )

    completed = [row for row in rows if row.get("status") == "ok"]
    summary = {
        "source_system": args.source_system,
        "season_start": season_start,
        "season_end": season_end,
        "slate_filter": args.slate,
        "slate_type": "showdown",
        "lineups_per_slate": args.lineups_per_slate,
        "training_window_slates": args.training_window_slates,
        "learned_only": args.learned_only,
        "slates_total": len(rows),
        "slates_completed": len(completed),
        "slates_failed_or_skipped": len(rows) - len(completed),
        "mean_gap_points": round(float(statistics.mean(gaps)), 4) if gaps else None,
        "median_gap_points": round(float(statistics.median(gaps)), 4) if gaps else None,
        "best_case_gap_points": round(float(min(gaps)), 4) if gaps else None,
        "worst_case_gap_points": round(float(max(gaps)), 4) if gaps else None,
    }
    payload = {"summary": summary, "rows": rows}

    print(json.dumps(summary, indent=2))
    if args.output_json:
        output_path = Path(args.output_json).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nWrote detailed results: {output_path}")

    print("\nTop 10 showdown slate gaps (largest missed opportunity):")
    ranked = sorted(
        [row for row in rows if row.get("status") == "ok"],
        key=lambda row: float(row["gap_points"]),
        reverse=True,
    )[:10]
    for row in ranked:
        print(
            f"  {row['season']} W{row['week']:02d} {row['slate']}: "
            f"optimal={row['optimal_actual_points']:.2f} "
            f"predicted={row['predicted_actual_points']:.2f} "
            f"gap={row['gap_points']:.2f}"
        )


if __name__ == "__main__":
    main()
