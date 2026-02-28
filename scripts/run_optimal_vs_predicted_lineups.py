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
    LineupLearningService,
    PlayerPoolRow,
    _sigmoid,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Walk-forward backtest: exact actual-optimal lineup vs learned-predicted top lineup per slate."
        )
    )
    parser.add_argument("--source-system", default="draftkings", choices=["draftkings", "fanduel"])
    parser.add_argument("--season-start", type=int, default=2024)
    parser.add_argument("--season-end", type=int, default=2025)
    parser.add_argument("--slate", type=str, default=None)
    parser.add_argument("--lineups-per-slate", type=int, default=4000)
    parser.add_argument("--training-window-slates", type=int, default=24)
    parser.add_argument("--min-training-slates", type=int, default=4)
    parser.add_argument("--min-training-rows", type=int, default=2000)
    parser.add_argument("--learned-only", dest="learned_only", action="store_true")
    parser.add_argument("--allow-heuristics", dest="learned_only", action="store_false")
    parser.set_defaults(learned_only=True)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--limit-slates", type=int, default=0)
    parser.add_argument("--output-json", type=str, default="")
    return parser.parse_args()


def _lineup_to_names(lineup: list[PlayerPoolRow]) -> list[str]:
    return [
        f"{row.position}:{row.name}({row.team or '-'},${row.salary},actual={row.actual_points:.2f})"
        for row in lineup
    ]


def _lineup_projected_mean(lineup: list[PlayerPoolRow]) -> float:
    return float(sum(row.projected_mean_points for row in lineup))


def _lineup_projected_p90(lineup: list[PlayerPoolRow]) -> float:
    return float(sum(row.projected_p90_points for row in lineup))


def _lineup_actual(lineup: list[PlayerPoolRow]) -> float:
    return float(sum(row.actual_points for row in lineup))


def main() -> None:
    args = parse_args()
    season_start = min(args.season_start, args.season_end)
    season_end = max(args.season_start, args.season_end)
    rng = np.random.default_rng(args.random_seed)

    rows: list[dict] = []
    gaps: list[float] = []
    history_x: list[np.ndarray] = []
    history_y: list[np.ndarray] = []

    with SessionLocal() as session:
        service = LineupLearningService(session)
        slices = service._fetch_available_slate_slices(
            source_system=args.source_system,
            season_start=season_start,
            season_end=season_end,
            slate_filter=args.slate,
        )
        if args.limit_slates and args.limit_slates > 0:
            slices = slices[: args.limit_slates]

        for season, week, slate in slices:
            try:
                projection_lookup, dst_projection_lookup = service._compute_player_projection_lookup(
                    source_system=args.source_system,
                    season=season,
                    week=week,
                    slate=slate,
                )
                pool = service._fetch_slate_player_pool(
                    source_system=args.source_system,
                    season=season,
                    week=week,
                    slate=slate,
                    projection_lookup=projection_lookup,
                    dst_projection_lookup=dst_projection_lookup,
                )
                optimal = service.optimize_actual_lineup(players=pool)
                if optimal is None:
                    rows.append(
                        {
                            "season": season,
                            "week": week,
                            "slate": slate,
                            "status": "skipped",
                            "error": "No feasible actual-optimal lineup.",
                        }
                    )
                    continue
                optimal_lineup, optimal_points, optimal_salary = optimal

                x_slate, points_slate, generated_lineups = service._generate_lineups_for_slate(
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
                            "status": "failed",
                            "error": "No generated candidate lineups.",
                        }
                    )
                    continue

                train_rows = int(sum(chunk.shape[0] for chunk in history_x))
                predicted_lineup: list[PlayerPoolRow] | None = None
                policy_score: float | None = None

                if len(history_x) >= args.min_training_slates and train_rows >= args.min_training_rows:
                    x_train = np.vstack(history_x)
                    y_train = np.concatenate(history_y)
                    weights, bias, mean, std = service._fit_logistic(x_train, y_train)
                    has_learned_signal = float(np.max(np.abs(weights))) > 1e-8
                    if has_learned_signal:
                        probs = _sigmoid(((x_slate - mean) / std) @ weights + bias)
                        idx = int(np.argmax(probs))
                        predicted_lineup = generated_lineups[idx]
                        policy_score = float(probs[idx])
                    elif not args.learned_only:
                        idx = int(np.argmax([_lineup_projected_mean(lineup) for lineup in generated_lineups]))
                        predicted_lineup = generated_lineups[idx]
                        policy_score = None
                elif not args.learned_only:
                    idx = int(np.argmax([_lineup_projected_mean(lineup) for lineup in generated_lineups]))
                    predicted_lineup = generated_lineups[idx]
                    policy_score = None

                if predicted_lineup is None:
                    rows.append(
                        {
                            "season": season,
                            "week": week,
                            "slate": slate,
                            "status": "warmup_or_no_signal",
                            "error": (
                                "Insufficient learned history for learned-only mode."
                                if args.learned_only
                                else "Could not produce predicted lineup."
                            ),
                        }
                    )
                else:
                    predicted_actual_points = _lineup_actual(predicted_lineup)
                    gap = float(optimal_points - predicted_actual_points)
                    gaps.append(gap)
                    rows.append(
                        {
                            "season": season,
                            "week": week,
                            "slate": slate,
                            "status": "ok",
                            "optimal_actual_points": round(float(optimal_points), 4),
                            "predicted_actual_points": round(float(predicted_actual_points), 4),
                            "gap_points": round(float(gap), 4),
                            "optimal_salary_used": int(optimal_salary),
                            "predicted_salary_used": int(sum(row.salary for row in predicted_lineup)),
                            "predicted_projected_mean_points": round(_lineup_projected_mean(predicted_lineup), 4),
                            "predicted_projected_p90_points": round(_lineup_projected_p90(predicted_lineup), 4),
                            "predicted_policy_score": round(policy_score, 6) if policy_score is not None else None,
                            "optimal_lineup": _lineup_to_names(optimal_lineup),
                            "predicted_lineup": _lineup_to_names(predicted_lineup),
                        }
                    )

                threshold = float(np.percentile(points_slate, 98.0))
                if np.isfinite(threshold) and threshold > 0.0 and float(np.std(points_slate)) > 1e-9:
                    y_slate = (points_slate >= threshold).astype(float)
                    pos_rate = float(np.mean(y_slate))
                    if 0.0 < pos_rate < 1.0:
                        history_x.append(x_slate)
                        history_y.append(y_slate)
                while len(history_x) > args.training_window_slates:
                    history_x.pop(0)
                    history_y.pop(0)

            except Exception as exc:  # noqa: BLE001
                rows.append(
                    {
                        "season": season,
                        "week": week,
                        "slate": slate,
                        "status": "failed",
                        "error": str(exc),
                    }
                )

    completed = [row for row in rows if row.get("status") == "ok"]
    summary = {
        "source_system": args.source_system,
        "season_start": season_start,
        "season_end": season_end,
        "slate_filter": args.slate,
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

    print("\nTop 10 slate gaps (largest missed opportunity):")
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
