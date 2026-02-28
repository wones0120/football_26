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
        description="Sweep showdown captain prior strengths and select the best by walk-forward gap lift."
    )
    parser.add_argument("--source-system", default="draftkings", choices=["draftkings", "fanduel"])
    parser.add_argument("--season-start", type=int, default=2024)
    parser.add_argument("--season-end", type=int, default=2025)
    parser.add_argument("--slate", type=str, default=None)
    parser.add_argument("--lineups-per-slate", type=int, default=2000)
    parser.add_argument("--training-window-slates", type=int, default=24)
    parser.add_argument("--min-training-slates", type=int, default=2)
    parser.add_argument("--min-training-rows", type=int, default=500)
    parser.add_argument("--limit-slates", type=int, default=0)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument(
        "--showdown-captain-model-path",
        type=str,
        default="docs/showdown_captain_model_2024_2025.json",
    )
    parser.add_argument(
        "--strengths",
        type=str,
        default="0.15,0.25,0.35,0.5",
        help="Comma-separated prior strengths in [0,1].",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default="docs/showdown_captain_strength_sweep_2024_2025.json",
    )
    parser.add_argument(
        "--report-md",
        type=str,
        default="docs/showdown_captain_strength_sweep_2024_2025.md",
    )
    return parser.parse_args()


def _run_backtest(
    *,
    service: LineupLearningService,
    request: OptimalVsPredictedBacktestRequest,
) -> dict[str, Any]:
    result = service.run_optimal_vs_predicted_backtest(request)
    return result.model_dump()


def _build_row_lookup(rows: list[dict[str, Any]]) -> dict[tuple[int, int, str], dict[str, Any]]:
    out: dict[tuple[int, int, str], dict[str, Any]] = {}
    for row in rows:
        if row.get("status") != "ok":
            continue
        if row.get("gap_points") is None:
            continue
        key = (int(row["season"]), int(row["week"]), str(row["slate"]))
        out[key] = row
    return out


def _std(values: list[float]) -> float | None:
    if not values:
        return None
    return float(statistics.pstdev(values))


def _summarize_pair(
    *,
    baseline_rows: list[dict[str, Any]],
    informed_rows: list[dict[str, Any]],
) -> dict[str, Any]:
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
            }
        )

    lifts = [row["gap_lift_points"] for row in paired_rows]
    baseline_gaps = [float(row["gap_points"]) for row in baseline_rows if row.get("status") == "ok" and row.get("gap_points") is not None]
    informed_gaps = [float(row["gap_points"]) for row in informed_rows if row.get("status") == "ok" and row.get("gap_points") is not None]
    baseline_std = _std(baseline_gaps)
    informed_std = _std(informed_gaps)

    return {
        "paired_slates": len(paired_rows),
        "mean_gap_lift_points": float(statistics.mean(lifts)) if lifts else None,
        "median_gap_lift_points": float(statistics.median(lifts)) if lifts else None,
        "captain_informed_win_rate": (
            float(sum(1 for row in paired_rows if row["gap_lift_points"] > 0) / len(paired_rows))
            if paired_rows
            else None
        ),
        "baseline_gap_stddev": baseline_std,
        "captain_informed_gap_stddev": informed_std,
        "stability_lift_stddev_reduction": (
            (baseline_std - informed_std)
            if baseline_std is not None and informed_std is not None
            else None
        ),
        "paired_rows": paired_rows,
    }


def _render_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Showdown Captain Prior Strength Sweep")
    lines.append("")
    lines.append(
        f"- Source: `{payload['config']['source_system']}`  "
        f"Seasons: `{payload['config']['season_start']}-{payload['config']['season_end']}`  "
        f"Lineups/slate: `{payload['config']['lineups_per_slate']}`"
    )
    lines.append("")
    lines.append("## Ranked Results")
    lines.append("")
    lines.append("| Rank | Strength | Mean Gap Lift | Median Gap Lift | Win Rate | Paired Slates | Baseline Mean Gap | Informed Mean Gap |")
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|")
    for index, row in enumerate(payload["ranked_results"], start=1):
        lines.append(
            f"| {index} | {row['strength']:.2f} | "
            f"{row['mean_gap_lift_points'] if row['mean_gap_lift_points'] is not None else '-'} | "
            f"{row['median_gap_lift_points'] if row['median_gap_lift_points'] is not None else '-'} | "
            f"{(row['captain_informed_win_rate'] * 100):.1f}% | "
            f"{row['paired_slates']} | "
            f"{row['baseline_mean_gap_points'] if row['baseline_mean_gap_points'] is not None else '-'} | "
            f"{row['captain_informed_mean_gap_points'] if row['captain_informed_mean_gap_points'] is not None else '-'} |"
        )
    lines.append("")
    best = payload.get("best_strength_result")
    if best:
        lines.append("## Selected Strength")
        lines.append("")
        lines.append(
            f"- Best strength: `{best['strength']:.2f}` "
            f"(mean gap lift `{best['mean_gap_lift_points']:.3f}`, win rate `{best['captain_informed_win_rate'] * 100:.1f}%`)."
        )
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    season_start = min(args.season_start, args.season_end)
    season_end = max(args.season_start, args.season_end)
    model_path = str(Path(args.showdown_captain_model_path).expanduser())
    strengths = []
    for token in args.strengths.split(","):
        token = token.strip()
        if not token:
            continue
        value = float(token)
        if value < 0 or value > 1:
            raise ValueError("All strengths must be between 0 and 1.")
        strengths.append(value)
    if not strengths:
        raise ValueError("At least one strength is required.")

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
        learned_only=True,
        random_seed=args.random_seed,
        limit_slates=args.limit_slates,
        showdown_captain_model_path=None,
        showdown_captain_prior_strength=0.0,
    )

    with SessionLocal() as session:
        service = LineupLearningService(session)
        baseline = _run_backtest(service=service, request=baseline_request)
        baseline_rows = baseline.get("rows", [])
        runs: list[dict[str, Any]] = []

        for strength in strengths:
            print(f"[captain_sweep] strength={strength:.2f} running...", flush=True)
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
                learned_only=True,
                random_seed=args.random_seed,
                limit_slates=args.limit_slates,
                showdown_captain_model_path=model_path,
                showdown_captain_prior_strength=float(strength),
            )
            informed = _run_backtest(service=service, request=informed_request)
            pair_summary = _summarize_pair(
                baseline_rows=baseline_rows,
                informed_rows=informed.get("rows", []),
            )
            runs.append(
                {
                    "strength": float(strength),
                    "baseline_mean_gap_points": baseline.get("mean_gap_points"),
                    "captain_informed_mean_gap_points": informed.get("mean_gap_points"),
                    **{key: value for key, value in pair_summary.items() if key != "paired_rows"},
                    "paired_rows": pair_summary["paired_rows"],
                }
            )

    ranked = sorted(
        runs,
        key=lambda row: (
            -(row["mean_gap_lift_points"] if row["mean_gap_lift_points"] is not None else -999999.0),
            -(row["captain_informed_win_rate"] if row["captain_informed_win_rate"] is not None else -999999.0),
        ),
    )
    best = ranked[0] if ranked else None
    payload = {
        "config": {
            "source_system": args.source_system,
            "season_start": season_start,
            "season_end": season_end,
            "slate_filter": args.slate,
            "lineups_per_slate": args.lineups_per_slate,
            "training_window_slates": args.training_window_slates,
            "min_training_slates": args.min_training_slates,
            "min_training_rows": args.min_training_rows,
            "limit_slates": args.limit_slates,
            "random_seed": args.random_seed,
            "showdown_captain_model_path": model_path,
            "strengths": strengths,
        },
        "ranked_results": ranked,
        "best_strength_result": best,
    }

    output_json = Path(args.output_json).expanduser().resolve()
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    output_md = Path(args.report_md).expanduser().resolve()
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(_render_markdown(payload), encoding="utf-8")

    console_summary = {
        "source_system": args.source_system,
        "season_start": season_start,
        "season_end": season_end,
        "lineups_per_slate": args.lineups_per_slate,
        "best_strength": best["strength"] if best else None,
        "best_mean_gap_lift_points": best["mean_gap_lift_points"] if best else None,
        "best_win_rate": best["captain_informed_win_rate"] if best else None,
        "output_json": str(output_json),
        "report_md": str(output_md),
    }
    print(json.dumps(console_summary, indent=2))


if __name__ == "__main__":
    main()
