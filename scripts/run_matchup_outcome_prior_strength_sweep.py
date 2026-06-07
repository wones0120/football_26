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
            "Sweep classic matchup-outcome prior strengths and select the best by "
            "walk-forward actual-optimal gap lift."
        )
    )
    parser.add_argument("--source-system", default="draftkings", choices=["draftkings", "fanduel"])
    parser.add_argument("--season-start", type=int, default=2024)
    parser.add_argument("--season-end", type=int, default=2025)
    parser.add_argument("--slate", type=str, default=None)
    parser.add_argument("--lineups-per-slate", type=int, default=4000)
    parser.add_argument("--training-window-slates", type=int, default=24)
    parser.add_argument("--min-training-slates", type=int, default=6)
    parser.add_argument("--min-training-rows", type=int, default=12000)
    parser.add_argument("--limit-slates", type=int, default=0)
    parser.add_argument("--random-seed", type=int, default=20260224)
    parser.add_argument(
        "--matchup-outcome-model-path",
        type=str,
        default="docs/matchup_outcome_intelligence_2024_2025.json",
    )
    parser.add_argument(
        "--strengths",
        type=str,
        default="0.15,0.25,0.35,0.5,0.65,0.8",
        help="Comma-separated prior strengths in [0,1].",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default="docs/matchup_outcome_prior_strength_sweep_2024_2025.json",
    )
    parser.add_argument(
        "--report-md",
        type=str,
        default="docs/matchup_outcome_prior_strength_sweep_2024_2025.md",
    )
    parser.add_argument("--quiet-progress", action="store_true")
    return parser.parse_args()


def _run_backtest(
    *,
    service: LineupLearningService,
    request: OptimalVsPredictedBacktestRequest,
    label: str,
    quiet_progress: bool,
) -> dict[str, Any]:
    progress_hook = None
    if not quiet_progress:
        progress_hook = lambda message: print(f"[{label}] {message}", flush=True)
    result = service.run_optimal_vs_predicted_backtest(request, progress_hook=progress_hook)
    return result.model_dump()


def _build_row_lookup(rows: list[dict[str, Any]]) -> dict[tuple[int, int, str], dict[str, Any]]:
    out: dict[tuple[int, int, str], dict[str, Any]] = {}
    for row in rows:
        if row.get("status") != "ok":
            continue
        if row.get("gap_points") is None:
            continue
        out[(int(row["season"]), int(row["week"]), str(row["slate"]))] = row
    return out


def _safe_mean(values: list[float]) -> float | None:
    return float(statistics.mean(values)) if values else None


def _safe_median(values: list[float]) -> float | None:
    return float(statistics.median(values)) if values else None


def _safe_std(values: list[float]) -> float | None:
    return float(statistics.pstdev(values)) if values else None


def _completed_gaps(rows: list[dict[str, Any]]) -> list[float]:
    return [
        float(row["gap_points"])
        for row in rows
        if row.get("status") == "ok" and row.get("gap_points") is not None
    ]


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
        baseline_row = baseline_lookup[(season, week, slate)]
        informed_row = informed_lookup[(season, week, slate)]
        baseline_gap = float(baseline_row["gap_points"])
        informed_gap = float(informed_row["gap_points"])
        paired_rows.append(
            {
                "season": season,
                "week": week,
                "slate": slate,
                "baseline_gap_points": baseline_gap,
                "matchup_informed_gap_points": informed_gap,
                "gap_lift_points": baseline_gap - informed_gap,
                "baseline_predicted_actual_points": baseline_row.get("predicted_actual_points"),
                "matchup_predicted_actual_points": informed_row.get("predicted_actual_points"),
                "optimal_actual_points": informed_row.get("optimal_actual_points"),
            }
        )

    lifts = [float(row["gap_lift_points"]) for row in paired_rows]
    baseline_gaps = _completed_gaps(baseline_rows)
    informed_gaps = _completed_gaps(informed_rows)
    baseline_std = _safe_std(baseline_gaps)
    informed_std = _safe_std(informed_gaps)

    return {
        "paired_slates": len(paired_rows),
        "mean_gap_lift_points": _safe_mean(lifts),
        "median_gap_lift_points": _safe_median(lifts),
        "matchup_informed_win_rate": (
            float(sum(1 for row in paired_rows if row["gap_lift_points"] > 0) / len(paired_rows))
            if paired_rows
            else None
        ),
        "baseline_mean_gap_points": _safe_mean(baseline_gaps),
        "matchup_informed_mean_gap_points": _safe_mean(informed_gaps),
        "baseline_median_gap_points": _safe_median(baseline_gaps),
        "matchup_informed_median_gap_points": _safe_median(informed_gaps),
        "baseline_gap_stddev": baseline_std,
        "matchup_informed_gap_stddev": informed_std,
        "stability_lift_stddev_reduction": (
            baseline_std - informed_std
            if baseline_std is not None and informed_std is not None
            else None
        ),
        "paired_rows": paired_rows,
    }


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _render_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Matchup Outcome Prior Strength Sweep")
    lines.append("")
    lines.append(
        f"- Source: `{payload['config']['source_system']}`  "
        f"Seasons: `{payload['config']['season_start']}-{payload['config']['season_end']}`  "
        f"Slate filter: `{payload['config']['slate_filter'] or 'all classic'}`  "
        f"Lineups/slate: `{payload['config']['lineups_per_slate']}`"
    )
    lines.append(
        f"- Training window: `{payload['config']['training_window_slates']}` slates  "
        f"Minimum training: `{payload['config']['min_training_slates']}` slates / "
        f"`{payload['config']['min_training_rows']}` rows"
    )
    lines.append("")
    lines.append("## Ranked Results")
    lines.append("")
    lines.append(
        "| Rank | Strength | Mean Gap Lift | Median Gap Lift | Win Rate | "
        "Paired Slates | Baseline Mean Gap | Informed Mean Gap | Stddev Reduction |"
    )
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for index, row in enumerate(payload["ranked_results"], start=1):
        win_rate = row.get("matchup_informed_win_rate")
        lines.append(
            f"| {index} | {row['strength']:.2f} | "
            f"{_fmt(row.get('mean_gap_lift_points'))} | "
            f"{_fmt(row.get('median_gap_lift_points'))} | "
            f"{(win_rate * 100):.1f}% | " if win_rate is not None else
            f"| {index} | {row['strength']:.2f} | "
            f"{_fmt(row.get('mean_gap_lift_points'))} | "
            f"{_fmt(row.get('median_gap_lift_points'))} | - | "
        )
        lines[-1] += (
            f"{row.get('paired_slates', 0)} | "
            f"{_fmt(row.get('baseline_mean_gap_points'))} | "
            f"{_fmt(row.get('matchup_informed_mean_gap_points'))} | "
            f"{_fmt(row.get('stability_lift_stddev_reduction'))} |"
        )
    lines.append("")

    best = payload.get("best_strength_result")
    if best:
        best_win_rate = best.get("matchup_informed_win_rate")
        best_win_rate_text = f"{(best_win_rate * 100):.1f}%" if best_win_rate is not None else "-"
        lines.append("## Selected Strength")
        lines.append("")
        lines.append(
            f"- Best strength: `{best['strength']:.2f}` "
            f"(mean gap lift `{_fmt(best.get('mean_gap_lift_points'))}`, "
            f"win rate `{best_win_rate_text}`)."
        )
        lines.append("")
    return "\n".join(lines) + "\n"


def _parse_strengths(raw: str) -> list[float]:
    strengths: list[float] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        value = float(token)
        if value < 0 or value > 1:
            raise ValueError("All strengths must be between 0 and 1.")
        strengths.append(value)
    if not strengths:
        raise ValueError("At least one strength is required.")
    return strengths


def main() -> None:
    args = parse_args()
    season_start = min(args.season_start, args.season_end)
    season_end = max(args.season_start, args.season_end)
    model_path = str(Path(args.matchup_outcome_model_path).expanduser())
    strengths = _parse_strengths(args.strengths)

    baseline_request = OptimalVsPredictedBacktestRequest(
        source_system=args.source_system,
        season_start=season_start,
        season_end=season_end,
        slate=args.slate,
        slate_type="classic",
        lineups_per_slate=args.lineups_per_slate,
        training_window_slates=args.training_window_slates,
        min_training_slates=args.min_training_slates,
        min_training_rows=args.min_training_rows,
        learned_only=True,
        random_seed=args.random_seed,
        limit_slates=args.limit_slates,
        matchup_outcome_model_path=None,
        matchup_outcome_prior_strength=0.0,
    )

    with SessionLocal() as session:
        service = LineupLearningService(session)
        print("[matchup_sweep] baseline running...", flush=True)
        baseline = _run_backtest(
            service=service,
            request=baseline_request,
            label="baseline",
            quiet_progress=args.quiet_progress,
        )
        baseline_rows = baseline.get("rows", [])
        runs: list[dict[str, Any]] = []

        for strength in strengths:
            print(f"[matchup_sweep] strength={strength:.2f} running...", flush=True)
            informed_request = OptimalVsPredictedBacktestRequest(
                source_system=args.source_system,
                season_start=season_start,
                season_end=season_end,
                slate=args.slate,
                slate_type="classic",
                lineups_per_slate=args.lineups_per_slate,
                training_window_slates=args.training_window_slates,
                min_training_slates=args.min_training_slates,
                min_training_rows=args.min_training_rows,
                learned_only=True,
                random_seed=args.random_seed,
                limit_slates=args.limit_slates,
                matchup_outcome_model_path=model_path,
                matchup_outcome_prior_strength=float(strength),
            )
            informed = _run_backtest(
                service=service,
                request=informed_request,
                label=f"strength={strength:.2f}",
                quiet_progress=args.quiet_progress,
            )
            pair_summary = _summarize_pair(
                baseline_rows=baseline_rows,
                informed_rows=informed.get("rows", []),
            )
            runs.append(
                {
                    "strength": float(strength),
                    "baseline_completed_slates": baseline.get("completed_slates"),
                    "matchup_informed_completed_slates": informed.get("completed_slates"),
                    **pair_summary,
                }
            )

    ranked = sorted(
        runs,
        key=lambda row: (
            -(row["mean_gap_lift_points"] if row["mean_gap_lift_points"] is not None else -999999.0),
            -(row["matchup_informed_win_rate"] if row["matchup_informed_win_rate"] is not None else -999999.0),
            row["matchup_informed_mean_gap_points"]
            if row["matchup_informed_mean_gap_points"] is not None
            else 999999.0,
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
            "matchup_outcome_model_path": model_path,
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
        "best_win_rate": best["matchup_informed_win_rate"] if best else None,
        "output_json": str(output_json),
        "report_md": str(output_md),
    }
    print(json.dumps(console_summary, indent=2))


if __name__ == "__main__":
    main()
