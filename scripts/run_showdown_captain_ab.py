from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal
from backend.app.schemas import OptimalVsPredictedBacktestRequest
from backend.app.services.lineup_learning import LineupLearningService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "A/B showdown backtest: baseline lineup generation vs captain-informed lineup generation."
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
    parser.add_argument(
        "--showdown-captain-model-path",
        type=str,
        default="docs/showdown_captain_model_2024_2025.json",
    )
    parser.add_argument("--showdown-captain-prior-strength", type=float, default=0.35)
    parser.add_argument(
        "--output-json",
        type=str,
        default="docs/optimal_vs_predicted_showdown_captain_ab_2024_2025.json",
    )
    parser.add_argument("--quiet-progress", action="store_true")
    return parser.parse_args()


def _run(
    *,
    service: LineupLearningService,
    request: OptimalVsPredictedBacktestRequest,
    quiet_progress: bool,
) -> dict[str, Any]:
    def _progress(message: str) -> None:
        if not quiet_progress:
            print(message, flush=True)

    response = service.run_optimal_vs_predicted_backtest(
        request,
        progress_hook=_progress if not quiet_progress else None,
    )
    return response.model_dump()


def _build_row_lookup(rows: list[dict[str, Any]]) -> dict[tuple[int, int, str], dict[str, Any]]:
    out: dict[tuple[int, int, str], dict[str, Any]] = {}
    for row in rows:
        if row.get("status") != "ok":
            continue
        key = (int(row["season"]), int(row["week"]), str(row["slate"]))
        out[key] = row
    return out


def _gap_std(rows: list[dict[str, Any]]) -> float | None:
    values = [float(row["gap_points"]) for row in rows if row.get("status") == "ok" and row.get("gap_points") is not None]
    if not values:
        return None
    return float(statistics.pstdev(values))


def _near_optimal_rate(rows: list[dict[str, Any]], threshold_ratio: float = 0.9) -> float | None:
    ok = [row for row in rows if row.get("status") == "ok"]
    if not ok:
        return None
    hits = 0
    for row in ok:
        optimal = float(row.get("optimal_actual_points") or 0.0)
        predicted = float(row.get("predicted_actual_points") or 0.0)
        if optimal <= 0:
            continue
        if (predicted / optimal) >= threshold_ratio:
            hits += 1
    return float(hits / len(ok))


def main() -> None:
    args = parse_args()
    season_start = min(args.season_start, args.season_end)
    season_end = max(args.season_start, args.season_end)
    captain_prior_strength = float(min(max(args.showdown_captain_prior_strength, 0.0), 1.0))

    baseline_request = OptimalVsPredictedBacktestRequest(
        source_system=args.source_system,
        season_start=season_start,
        season_end=season_end,
        slate=args.slate,
        slate_type="showdown",
        lineups_per_slate=args.lineups_per_slate,
        training_window_slates=args.training_window_slates,
        min_training_slates=args.min_training_slates,
        min_training_rows=args.min_training_rows,
        learned_only=args.learned_only,
        random_seed=args.random_seed,
        limit_slates=args.limit_slates,
        showdown_captain_model_path=None,
        showdown_captain_prior_strength=0.0,
    )
    informed_request = OptimalVsPredictedBacktestRequest(
        source_system=args.source_system,
        season_start=season_start,
        season_end=season_end,
        slate=args.slate,
        slate_type="showdown",
        lineups_per_slate=args.lineups_per_slate,
        training_window_slates=args.training_window_slates,
        min_training_slates=args.min_training_slates,
        min_training_rows=args.min_training_rows,
        learned_only=args.learned_only,
        random_seed=args.random_seed,
        limit_slates=args.limit_slates,
        showdown_captain_model_path=args.showdown_captain_model_path,
        showdown_captain_prior_strength=captain_prior_strength,
    )

    with SessionLocal() as session:
        service = LineupLearningService(session)
        baseline = _run(service=service, request=baseline_request, quiet_progress=args.quiet_progress)
        informed = _run(service=service, request=informed_request, quiet_progress=args.quiet_progress)

    baseline_rows = baseline.get("rows", [])
    informed_rows = informed.get("rows", [])
    baseline_lookup = _build_row_lookup(baseline_rows)
    informed_lookup = _build_row_lookup(informed_rows)
    shared_keys = sorted(set(baseline_lookup.keys()) & set(informed_lookup.keys()))

    paired_rows: list[dict[str, Any]] = []
    for season, week, slate in shared_keys:
        base_row = baseline_lookup[(season, week, slate)]
        inf_row = informed_lookup[(season, week, slate)]
        base_gap = float(base_row["gap_points"])
        inf_gap = float(inf_row["gap_points"])
        paired_rows.append(
            {
                "season": season,
                "week": week,
                "slate": slate,
                "baseline_gap_points": base_gap,
                "captain_informed_gap_points": inf_gap,
                "gap_lift_points": base_gap - inf_gap,
                "baseline_predicted_actual_points": float(base_row["predicted_actual_points"]),
                "captain_informed_predicted_actual_points": float(inf_row["predicted_actual_points"]),
                "optimal_actual_points": float(base_row["optimal_actual_points"]),
            }
        )

    gap_lifts = [row["gap_lift_points"] for row in paired_rows]
    mean_gap_lift = float(statistics.mean(gap_lifts)) if gap_lifts else None
    median_gap_lift = float(statistics.median(gap_lifts)) if gap_lifts else None
    win_rate = (
        float(sum(1 for row in paired_rows if row["gap_lift_points"] > 0) / len(paired_rows))
        if paired_rows
        else None
    )

    baseline_std = _gap_std(baseline_rows)
    informed_std = _gap_std(informed_rows)
    stability_lift = (
        (baseline_std - informed_std)
        if baseline_std is not None and informed_std is not None
        else None
    )

    baseline_near_optimal = _near_optimal_rate(baseline_rows, threshold_ratio=0.9)
    informed_near_optimal = _near_optimal_rate(informed_rows, threshold_ratio=0.9)
    near_optimal_lift = (
        (informed_near_optimal - baseline_near_optimal)
        if baseline_near_optimal is not None and informed_near_optimal is not None
        else None
    )

    summary = {
        "source_system": args.source_system,
        "season_start": season_start,
        "season_end": season_end,
        "lineups_per_slate": args.lineups_per_slate,
        "training_window_slates": args.training_window_slates,
        "learned_only": args.learned_only,
        "showdown_captain_model_path": args.showdown_captain_model_path,
        "showdown_captain_prior_strength": captain_prior_strength,
        "paired_slates": len(paired_rows),
        "mean_gap_lift_points": mean_gap_lift,
        "median_gap_lift_points": median_gap_lift,
        "captain_informed_win_rate": win_rate,
        "baseline_gap_stddev": baseline_std,
        "captain_informed_gap_stddev": informed_std,
        "stability_lift_stddev_reduction": stability_lift,
        "baseline_near_optimal_rate_90pct": baseline_near_optimal,
        "captain_informed_near_optimal_rate_90pct": informed_near_optimal,
        "near_optimal_rate_lift_90pct": near_optimal_lift,
        "baseline_mean_gap_points": baseline.get("mean_gap_points"),
        "captain_informed_mean_gap_points": informed.get("mean_gap_points"),
    }
    payload = {
        "summary": summary,
        "baseline": baseline,
        "captain_informed": informed,
        "paired_rows": paired_rows,
    }

    print(json.dumps(summary, indent=2))

    output_path = Path(args.output_json).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nWrote A/B results: {output_path}")

    print("\nTop 10 captain-informed slate lifts:")
    top_rows = sorted(paired_rows, key=lambda row: row["gap_lift_points"], reverse=True)[:10]
    for row in top_rows:
        print(
            f"  {row['season']} W{row['week']:02d} {row['slate']}: "
            f"gap_lift={row['gap_lift_points']:.2f} "
            f"(baseline={row['baseline_gap_points']:.2f}, captain={row['captain_informed_gap_points']:.2f})"
        )


if __name__ == "__main__":
    main()
