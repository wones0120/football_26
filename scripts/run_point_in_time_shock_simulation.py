from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal
from backend.app.schemas import PointInTimeShockRequest, SimulateWeekRequest
from backend.app.services.simulation import SimulationService


def _comma_values(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a reproducible, manually entered point-in-time weather/news "
            "projection shock."
        )
    )
    parser.add_argument(
        "--source-system",
        default="draftkings",
        choices=["draftkings", "fanduel"],
    )
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--slate", type=str, default="sunday_main")
    parser.add_argument(
        "--shock-type",
        choices=["weather", "news"],
        required=True,
    )
    parser.add_argument(
        "--scenario-as-of",
        required=True,
        help="Timezone-aware ISO cutoff for information allowed in the scenario.",
    )
    parser.add_argument(
        "--observed-at",
        required=True,
        help="Timezone-aware ISO timestamp when the shock input became known.",
    )
    parser.add_argument("--label", required=True)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--teams",
        help="Comma-separated team abbreviations for a team/position shock.",
    )
    target.add_argument(
        "--player-master-ids",
        help="Comma-separated canonical player IDs for a news shock.",
    )
    target.add_argument(
        "--source-player-keys",
        help="Comma-separated source-native player IDs for a news shock.",
    )
    parser.add_argument(
        "--positions",
        default="QB,RB,WR,TE,K,DST",
        help="Comma-separated positions used with --teams.",
    )
    parser.add_argument("--mean-multiplier", type=float, default=1.0)
    parser.add_argument("--volatility-multiplier", type=float, default=1.0)
    parser.add_argument("--iterations", type=int, default=5000)
    parser.add_argument("--top-n", type=int, default=40)
    parser.add_argument("--min-history-games", type=int, default=4)
    parser.add_argument("--prior-weight", type=float, default=12.0)
    parser.add_argument("--noise-scale", type=float, default=0.12)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--output-json", type=str, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    shock = PointInTimeShockRequest(
        shock_type=args.shock_type,
        observed_at=args.observed_at,
        label=args.label,
        teams=_comma_values(args.teams or ""),
        positions=_comma_values(args.positions),
        player_master_ids=_comma_values(args.player_master_ids or ""),
        source_player_keys=_comma_values(args.source_player_keys or ""),
        mean_multiplier=args.mean_multiplier,
        volatility_multiplier=args.volatility_multiplier,
    )
    request = SimulateWeekRequest(
        source_system=args.source_system,
        season=args.season,
        week=args.week,
        slate=args.slate,
        iterations=args.iterations,
        top_n=args.top_n,
        min_history_games=args.min_history_games,
        prior_weight=args.prior_weight,
        noise_scale=args.noise_scale,
        random_seed=args.random_seed,
        scenario_as_of=args.scenario_as_of,
        point_in_time_shocks=[shock],
    )
    with SessionLocal() as session:
        result = SimulationService(session).simulate_week(request)

    rendered = json.dumps(result.model_dump(mode="json"), indent=2)
    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    if result.status != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
