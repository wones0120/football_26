from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal
from backend.app.schemas import UltimateLineupRequest
from backend.app.services.lineup_learning import LineupLearningService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate ultimate lineups from 100k+ candidates.")
    parser.add_argument("--source-system", default="draftkings", choices=["draftkings", "fanduel"])
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--slate", type=str, default="sunday_main")
    parser.add_argument("--candidate-lineups", type=int, default=100000)
    parser.add_argument("--output-lineups", type=int, default=150)
    parser.add_argument("--min-salary-floor", type=int, default=43000)
    parser.add_argument("--training-start-season", type=int, default=2024)
    parser.add_argument("--training-window-slates", type=int, default=24)
    parser.add_argument("--training-lineups-per-slate", type=int, default=1500)
    parser.add_argument("--min-training-slates", type=int, default=4)
    parser.add_argument("--min-training-rows", type=int, default=2000)
    parser.add_argument("--learned-only", dest="learned_only", action="store_true")
    parser.add_argument("--allow-heuristics", dest="learned_only", action="store_false")
    parser.set_defaults(learned_only=True)
    parser.add_argument("--max-player-exposure", type=float, default=0.35)
    parser.add_argument("--max-qb-exposure", type=float, default=0.25)
    parser.add_argument("--max-dst-exposure", type=float, default=0.30)
    parser.add_argument("--classic-value-driver-model-path", type=str, default=None)
    parser.add_argument("--classic-value-driver-prior-strength", type=float, default=0.0)
    parser.add_argument("--matchup-outcome-model-path", type=str, default=None)
    parser.add_argument("--matchup-outcome-prior-strength", type=float, default=0.0)
    parser.add_argument("--matchup-prior-gate-model-path", type=str, default=None)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--show-lineups", type=int, default=20)
    parser.add_argument("--show-exposures", type=int, default=35)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    request = UltimateLineupRequest(
        source_system=args.source_system,
        season=args.season,
        week=args.week,
        slate=args.slate,
        candidate_lineups=args.candidate_lineups,
        output_lineups=args.output_lineups,
        min_salary_floor=args.min_salary_floor,
        training_start_season=args.training_start_season,
        training_window_slates=args.training_window_slates,
        training_lineups_per_slate=args.training_lineups_per_slate,
        min_training_slates=args.min_training_slates,
        min_training_rows=args.min_training_rows,
        learned_only=args.learned_only,
        max_player_exposure=args.max_player_exposure,
        max_qb_exposure=args.max_qb_exposure,
        max_dst_exposure=args.max_dst_exposure,
        classic_value_driver_model_path=args.classic_value_driver_model_path,
        classic_value_driver_prior_strength=args.classic_value_driver_prior_strength,
        matchup_outcome_model_path=args.matchup_outcome_model_path,
        matchup_outcome_prior_strength=args.matchup_outcome_prior_strength,
        matchup_prior_gate_model_path=args.matchup_prior_gate_model_path,
        random_seed=args.random_seed,
    )
    with SessionLocal() as session:
        service = LineupLearningService(session)
        result = service.build_ultimate_lineups(request)

    summary = {
        "source_system": result.source_system,
        "season": result.season,
        "week": result.week,
        "slate": result.slate,
        "candidate_lineups_requested": result.candidate_lineups_requested,
        "generated_candidate_lineups": result.generated_candidate_lineups,
        "output_lineups": result.output_lineups,
        "training_slates_used": result.training_slates_used,
        "training_rows_used": result.training_rows_used,
        "training_positive_rate": result.training_positive_rate,
        "classic_value_driver_model_path": result.classic_value_driver_model_path,
        "classic_value_driver_prior_strength": result.classic_value_driver_prior_strength,
        "matchup_outcome_model_path": result.matchup_outcome_model_path,
        "matchup_outcome_prior_strength": result.matchup_outcome_prior_strength,
        "matchup_prior_gate_model_path": result.matchup_prior_gate_model_path,
        "discovered_patterns": result.discovered_patterns,
    }
    print(json.dumps(summary, indent=2))

    print(f"\nTop {min(args.show_lineups, len(result.rows))} lineups:")
    for row in result.rows[: args.show_lineups]:
        names = " | ".join(
            f"{p.position}:{p.player_name}({p.team or '-'},{p.salary})"
            for p in row.players
        )
        print(
            f"  #{row.rank:03d} salary={row.salary_used} left={row.salary_left} "
            f"mean={row.projected_mean_points:.2f} p90={row.projected_p90_points:.2f} "
            f"policy={row.policy_score:.4f} score={row.composite_score:.4f}"
        )
        print(f"    {names}")

    print(f"\nTop {min(args.show_exposures, len(result.exposures))} exposures:")
    for row in result.exposures[: args.show_exposures]:
        print(
            f"  {row.player_name:<28} {row.position:<3} {row.team or '-':<4} "
            f"{row.salary:>5}  {row.exposure_count:>4}/{result.output_lineups} ({row.exposure_rate:.1%})"
        )


if __name__ == "__main__":
    main()
