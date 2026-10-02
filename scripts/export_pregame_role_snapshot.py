"""Export a point-in-time, canonical-ID role snapshot without running optimization."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from sqlalchemy import create_engine

from Database.config import get_connection_string
from backend.app.product_services.optimizer import OptimizerService


FIELDS = (
    "player_id", "name", "player_team", "position", "projection_run_id", "data_cutoff_at",
    "player_status", "roster_status", "depth_chart_position", "is_starting_qb",
    "pregame_availability_probability", "pregame_start_probability",
    "snap_share_mean_3", "pregame_expected_routes", "carries_mean_3", "targets_mean_3",
    "carry_share_mean_3", "target_share_mean_3", "pregame_red_zone_share",
    "pregame_goal_line_share", "pregame_injury_status", "pregame_newly_assigned_role",
    "pregame_context_source", "pregame_context_observed_at", "projected_targets",
    "projected_carries", "team_targets_mean_3", "team_carries_mean_3",
    "offensive_role_importance", "offensive_role_class", "offensive_role_confidence",
    "offensive_role_completeness", "offensive_role_reason", "offensive_role_source",
    "projection", "p90", "salary",
    "game_total_line", "team_spread_line", "team_implied_total",
)


def _value(value: object) -> object:
    if value is None:
        return None
    try:
        if math.isnan(float(value)):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--slate", required=True)
    parser.add_argument("--projection-run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    service = object.__new__(OptimizerService)
    service.engine = create_engine(get_connection_string())
    pool = service._load_target_player_pool(
        args.season, args.week, args.slate, args.projection_run_id
    )
    skill = pool.loc[pool["position"].isin(("RB", "WR", "TE"))]
    if skill.empty:
        raise ValueError("No RB/WR/TE salary players found for the requested slate/run")
    rows = [
        {field: _value(row.get(field)) for field in FIELDS}
        for row in skill.to_dict("records")
    ]
    for row in rows:
        row["unavailable_fields"] = [field for field in FIELDS if row[field] is None]
        row["recent_route_participation"] = None
        row["skill_position_starter_status"] = None
        row["red_zone_carries"] = None
        row["red_zone_targets"] = None
        row["two_minute_role"] = None
        row["recent_role_trend"] = None
        row["injury_created_role_change"] = (
            row["pregame_newly_assigned_role"] if row["pregame_context_source"] else None
        )
    output = {
        "season": args.season, "week": args.week, "slate": args.slate,
        "projection_run_id": args.projection_run_id,
        "source": "selected projection feature lineage + canonical weekly roster GSIS alias",
        "player_count": len(rows),
        "measured_role_count": sum(row["offensive_role_importance"] is not None for row in rows),
        "depth_chart_count": sum(row["depth_chart_position"] is not None for row in rows),
        "limitations": [
            "No Sunday pregame player-context rows are available at this projection cutoff",
            "Route participation, red-zone counts, two-minute roles, and role trends require sourced feeds",
            "The weekly-roster depth_chart_position contains a broad position (for example WR), not an ordinal starter rank",
            "Projected targets/carries are reconciled lagged allocations, not observed usage",
        ],
        "players": sorted(rows, key=lambda row: (row["player_team"] or "", row["name"] or "")),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(output, indent=2, allow_nan=False) + "\n"
    if args.output.exists() and args.output.read_text() != serialized:
        raise FileExistsError(
            f"{args.output} already contains a different snapshot; choose a new versioned output path"
        )
    if not args.output.exists():
        args.output.write_text(serialized)
    print(json.dumps({key: output[key] for key in ("player_count", "measured_role_count", "depth_chart_count")}))


if __name__ == "__main__":
    main()
