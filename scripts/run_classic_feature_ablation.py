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
from backend.app.services.lineup_learning import (
    CLASSIC_FEATURE_ABLATION_GROUPS,
    LineupLearningService,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure classic lineup feature contribution with deterministic walk-forward ablations.",
    )
    parser.add_argument("--source-system", default="draftkings", choices=["draftkings", "fanduel"])
    parser.add_argument("--season-start", type=int, default=2024)
    parser.add_argument("--season-end", type=int, default=2025)
    parser.add_argument("--slate", type=str, default=None)
    parser.add_argument("--lineups-per-slate", type=int, default=2000)
    parser.add_argument("--training-window-slates", type=int, default=24)
    parser.add_argument("--min-training-slates", type=int, default=4)
    parser.add_argument("--min-training-rows", type=int, default=2000)
    parser.add_argument("--learned-only", dest="learned_only", action="store_true")
    parser.add_argument("--allow-heuristics", dest="learned_only", action="store_false")
    parser.set_defaults(learned_only=True)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--limit-slates", type=int, default=0)
    parser.add_argument(
        "--groups",
        nargs="+",
        default=sorted(CLASSIC_FEATURE_ABLATION_GROUPS),
        choices=sorted(CLASSIC_FEATURE_ABLATION_GROUPS),
    )
    parser.add_argument("--quiet-progress", action="store_true")
    parser.add_argument("--output-json", type=str, required=True)
    return parser.parse_args()


def _completed_rows(payload: dict[str, Any]) -> dict[tuple[int, int, str], dict[str, Any]]:
    return {
        (int(row["season"]), int(row["week"]), str(row["slate"])): row
        for row in payload.get("rows", [])
        if row.get("status") == "ok" and row.get("gap_points") is not None
    }


def _mean_gap(rows: dict[tuple[int, int, str], dict[str, Any]]) -> float | None:
    if not rows:
        return None
    return float(statistics.mean(float(row["gap_points"]) for row in rows.values()))


def _comparison(
    baseline: dict[str, Any],
    ablated: dict[str, Any],
) -> dict[str, Any]:
    baseline_rows = _completed_rows(baseline)
    ablated_rows = _completed_rows(ablated)
    paired_keys = sorted(set(baseline_rows) & set(ablated_rows))
    full_model_better = sum(
        1
        for key in paired_keys
        if float(baseline_rows[key]["gap_points"]) < float(ablated_rows[key]["gap_points"])
    )
    tied = sum(
        1
        for key in paired_keys
        if float(baseline_rows[key]["gap_points"]) == float(ablated_rows[key]["gap_points"])
    )
    baseline_mean = _mean_gap({key: baseline_rows[key] for key in paired_keys})
    ablated_mean = _mean_gap({key: ablated_rows[key] for key in paired_keys})
    return {
        "paired_slates": len(paired_keys),
        "full_model_better_count": full_model_better,
        "full_model_better_rate": (
            float(full_model_better / len(paired_keys)) if paired_keys else None
        ),
        "tied_count": tied,
        "full_model_mean_gap_points": baseline_mean,
        "ablated_mean_gap_points": ablated_mean,
        "mean_gap_contribution_points": (
            float(ablated_mean - baseline_mean)
            if baseline_mean is not None and ablated_mean is not None
            else None
        ),
    }


def main() -> None:
    args = parse_args()
    request = OptimalVsPredictedBacktestRequest(
        source_system=args.source_system,
        season_start=args.season_start,
        season_end=args.season_end,
        slate=args.slate,
        slate_type="classic",
        lineups_per_slate=args.lineups_per_slate,
        training_window_slates=args.training_window_slates,
        min_training_slates=args.min_training_slates,
        min_training_rows=args.min_training_rows,
        learned_only=args.learned_only,
        random_seed=args.random_seed,
        limit_slates=args.limit_slates,
    )

    with SessionLocal() as session:
        service = LineupLearningService(session)

        def run(label: str, groups: list[str]) -> dict[str, Any]:
            service.set_classic_feature_ablation_groups(groups)
            hook = (
                None
                if args.quiet_progress
                else (lambda message: print(f"[{label}] {message}", flush=True))
            )
            return service.run_optimal_vs_predicted_backtest(
                request,
                progress_hook=hook,
            ).model_dump()

        baseline = run("full", [])
        ablations: dict[str, dict[str, Any]] = {}
        for group in args.groups:
            result = run(f"without_{group}", [group])
            ablations[group] = {
                "disabled_features": list(CLASSIC_FEATURE_ABLATION_GROUPS[group]),
                "comparison": _comparison(baseline, result),
                "result": result,
            }

    payload = {
        "request": request.model_dump(),
        "available_groups": {
            name: list(features)
            for name, features in CLASSIC_FEATURE_ABLATION_GROUPS.items()
        },
        "baseline": baseline,
        "ablations": ablations,
    }
    output_path = Path(args.output_json).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(
        {
            group: details["comparison"]
            for group, details in ablations.items()
        },
        indent=2,
    ))
    print(f"\nWrote ablation: {output_path}")


if __name__ == "__main__":
    main()
