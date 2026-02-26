from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal
from backend.app.schemas import BacktestRangeABRequest
from backend.app.services.simulation import SimulationService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run baseline vs calibrated backtests across a historical season range.",
    )
    parser.add_argument("--source-system", default="draftkings", choices=["draftkings", "fanduel"])
    parser.add_argument("--season-start", type=int, default=2024)
    parser.add_argument("--season-end", type=int, default=2025)
    parser.add_argument("--slate", type=str, default=None)
    parser.add_argument("--iterations", type=int, default=3000)
    parser.add_argument("--min-history-games", type=int, default=4)
    parser.add_argument("--prior-weight", type=float, default=12.0)
    parser.add_argument("--noise-scale", type=float, default=0.12)
    parser.add_argument("--evaluation-top-n", type=int, default=25)
    parser.add_argument("--low-salary-threshold", type=int, default=4500)
    parser.add_argument("--low-salary-hit-points", type=float, default=15.0)
    parser.add_argument("--no-persist-calibration", action="store_true")
    parser.add_argument("--reset-existing-calibration", action="store_true")
    parser.add_argument("--show-top", type=int, default=12, help="Show top N slices by MAE lift.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    request = BacktestRangeABRequest(
        source_system=args.source_system,
        season_start=args.season_start,
        season_end=args.season_end,
        slate=args.slate,
        iterations=args.iterations,
        min_history_games=args.min_history_games,
        prior_weight=args.prior_weight,
        noise_scale=args.noise_scale,
        evaluation_top_n=args.evaluation_top_n,
        low_salary_threshold=args.low_salary_threshold,
        low_salary_hit_points=args.low_salary_hit_points,
        persist_calibration=not args.no_persist_calibration,
        reset_existing_calibration=args.reset_existing_calibration,
    )

    with SessionLocal() as session:
        service = SimulationService(session)
        result = service.backtest_range_ab(request)

    summary = {
        "source_system": result.source_system,
        "season_start": result.season_start,
        "season_end": result.season_end,
        "slate": result.slate,
        "total_slates": result.total_slates,
        "slates_evaluated": result.slates_evaluated,
        "slates_failed": result.slates_failed,
        "players_with_actuals_total": result.players_with_actuals_total,
        "baseline_mae": result.baseline_mae,
        "calibrated_mae": result.calibrated_mae,
        "mae_lift_pct": result.mae_lift_pct,
        "baseline_rmse": result.baseline_rmse,
        "calibrated_rmse": result.calibrated_rmse,
        "rmse_lift_pct": result.rmse_lift_pct,
        "baseline_top_n_hit_rate": result.baseline_top_n_hit_rate,
        "calibrated_top_n_hit_rate": result.calibrated_top_n_hit_rate,
        "top_n_hit_rate_lift_pct": result.top_n_hit_rate_lift_pct,
        "baseline_low_salary_hit_rate": result.baseline_low_salary_hit_rate,
        "calibrated_low_salary_hit_rate": result.calibrated_low_salary_hit_rate,
        "low_salary_hit_rate_lift_pct": result.low_salary_hit_rate_lift_pct,
    }
    print(json.dumps(summary, indent=2))

    successful = [row for row in result.rows if row.error_message is None and row.mae_lift_pct is not None]
    successful.sort(key=lambda row: row.mae_lift_pct or -9999, reverse=True)
    print(f"\nTop {min(args.show_top, len(successful))} slices by MAE lift:")
    for row in successful[: args.show_top]:
        print(
            f"  {row.season}-W{row.week:02d} {row.slate:<16} "
            f"MAE {row.baseline_mae:.3f} -> {row.calibrated_mae:.3f} ({row.mae_lift_pct:+.2f}%)"
        )

    failed = [row for row in result.rows if row.error_message]
    if failed:
        print(f"\nFailed slices ({len(failed)}):")
        for row in failed[:20]:
            print(f"  {row.season}-W{row.week:02d} {row.slate}: {row.error_message}")


if __name__ == "__main__":
    main()
