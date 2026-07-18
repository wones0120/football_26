from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal
from backend.app.models import CuratedSalary
from backend.app.schemas import RoleShockRequest, SimulateWeekRequest
from backend.app.services.simulation import SimulationService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a reproducible manual role-shock projection simulation."
    )
    parser.add_argument("--source-system", default="draftkings", choices=["draftkings", "fanduel"])
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--slate", type=str, default="sunday_main")
    identity = parser.add_mutually_exclusive_group(required=True)
    identity.add_argument("--player-master-id", type=str)
    identity.add_argument("--source-player-key", type=str)
    identity.add_argument("--player-name", type=str)
    parser.add_argument("--retained-opportunity-share", type=float, default=0.0)
    parser.add_argument(
        "--reallocation-scope",
        choices=["same_position", "skill_players"],
        default="same_position",
    )
    parser.add_argument("--max-recipient-multiplier", type=float, default=2.0)
    parser.add_argument("--iterations", type=int, default=5000)
    parser.add_argument("--top-n", type=int, default=40)
    parser.add_argument("--min-history-games", type=int, default=4)
    parser.add_argument("--prior-weight", type=float, default=12.0)
    parser.add_argument("--noise-scale", type=float, default=0.12)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--output-json", type=str, default=None)
    return parser.parse_args()


def _resolve_identity(
    *,
    session: Session,
    source_system: str,
    season: int,
    week: int,
    slate: str,
    player_name: str,
) -> tuple[str | None, str | None]:
    salary_rows = session.execute(
        select(CuratedSalary).where(
            and_(
                CuratedSalary.source_system == source_system,
                CuratedSalary.season == season,
                CuratedSalary.week == week,
                CuratedSalary.slate == slate,
            )
        )
    ).scalars().all()
    normalized_target = player_name.strip().casefold()
    matches = [
        row
        for row in salary_rows
        if row.player_name.strip().casefold() == normalized_target
    ]
    identities = {
        (row.player_master_id, row.source_player_key)
        for row in matches
    }
    if not identities:
        raise ValueError(f"Player name not found in selected salary slice: {player_name}")
    if len(identities) > 1:
        raise ValueError(
            f"Player name is ambiguous in selected salary slice: {player_name}"
        )
    return next(iter(identities))


def main() -> None:
    args = parse_args()
    with SessionLocal() as session:
        player_master_id = args.player_master_id
        source_player_key = args.source_player_key
        if args.player_name:
            player_master_id, source_player_key = _resolve_identity(
                session=session,
                source_system=args.source_system,
                season=args.season,
                week=args.week,
                slate=args.slate,
                player_name=args.player_name,
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
            role_shocks=[
                RoleShockRequest(
                    player_master_id=player_master_id,
                    source_player_key=source_player_key,
                    retained_opportunity_share=args.retained_opportunity_share,
                    reallocation_scope=args.reallocation_scope,
                    max_recipient_multiplier=args.max_recipient_multiplier,
                )
            ],
        )
        result = SimulationService(session).simulate_week(request)

    payload = result.model_dump(mode="json")
    rendered = json.dumps(payload, indent=2)
    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    if result.status != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
