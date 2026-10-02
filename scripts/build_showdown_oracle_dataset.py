from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal
from backend.app.services.lineup_learning import (
    LineupLearningService,
    ShowdownLineup,
    ShowdownPlayerPoolRow,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a time-safe Showdown oracle dataset with unrestricted, "
            "forced-Captain, and near-optimal hindsight lineups."
        )
    )
    parser.add_argument("--source-system", default="draftkings", choices=["draftkings", "fanduel"])
    parser.add_argument("--season-start", type=int, default=2024)
    parser.add_argument("--season-end", type=int, default=2026)
    parser.add_argument("--top-lineups", type=int, default=50)
    parser.add_argument("--limit-slates", type=int, default=0)
    parser.add_argument("--output-json", default="artifacts/showdown-oracle-dataset.json")
    parser.add_argument("--output-csv", default="artifacts/showdown-forced-captain-oracles.csv")
    parser.add_argument("--output-md", default="artifacts/showdown-oracle-report.md")
    return parser.parse_args()


def _lineup_players(lineup: ShowdownLineup) -> list[dict[str, Any]]:
    return [
        {
            "slot": "CPT",
            "player_id": lineup.captain.uid,
            "name": lineup.captain.name,
            "team": lineup.captain.team,
            "position": lineup.captain.position,
        },
        *[
            {
                "slot": "FLEX",
                "player_id": player.uid,
                "name": player.name,
                "team": player.team,
                "position": player.position,
            }
            for player in lineup.flex_players
        ],
    ]


def _captain_row(
    *,
    season: int,
    week: int,
    slate: str,
    player: ShowdownPlayerPoolRow,
    forced: tuple[ShowdownLineup, float, int] | None,
    optimal_points: float,
) -> dict[str, Any]:
    forced_lineup, forced_points, forced_salary = forced if forced is not None else (None, None, None)
    regret = optimal_points - forced_points if forced_points is not None else None
    return {
        "season": season,
        "week": week,
        "slate": slate,
        "player_id": player.uid,
        "player_master_id": player.player_master_id,
        "player_name": player.name,
        "team": player.team,
        "opponent": player.opponent,
        "position": player.position,
        "flex_salary": player.flex_salary,
        "captain_salary": player.captain_salary,
        "projected_mean": player.projected_mean_points,
        "projected_p90": player.projected_p90_points,
        "expected_pass_attempts": player.pregame_expected_pass_attempts,
        "expected_carries": player.pregame_expected_carries,
        "expected_targets": player.pregame_expected_targets,
        "expected_routes": player.pregame_expected_routes,
        "expected_snaps": player.pregame_expected_snaps,
        "carry_share": player.pregame_carry_share,
        "target_share": player.pregame_target_share,
        "red_zone_share": player.pregame_red_zone_share,
        "goal_line_share": player.pregame_goal_line_share,
        "opportunity_source": player.pregame_opportunity_source,
        "offensive_role_importance": player.offensive_role_importance,
        "offensive_role_completeness": player.offensive_role_completeness,
        "offensive_role_class": player.offensive_role_class,
        "offensive_role_confidence": player.offensive_role_confidence,
        "injury_status": player.player_injury_status,
        "game_total": player.game_total_line,
        "team_spread": player.team_spread_line,
        "team_implied_total": player.team_implied_total,
        "actual_pass_attempts": player.actual_pass_attempts,
        "actual_carries": player.actual_carries,
        "actual_targets": player.actual_targets,
        "actual_points": player.actual_points,
        "actual_source": player.actual_source,
        "actual_zero": player.actual_points <= 0.0,
        "actual_below_3": player.actual_points < 3.0,
        "actual_below_5": player.actual_points < 5.0,
        "actual_below_8": player.actual_points < 8.0,
        "forced_captain_feasible": forced_lineup is not None,
        "forced_captain_score": forced_points,
        "forced_captain_salary": forced_salary,
        "captain_regret": regret,
        "within_1_of_optimal": regret is not None and regret <= 1.0,
        "within_3_of_optimal": regret is not None and regret <= 3.0,
        "within_5_of_optimal": regret is not None and regret <= 5.0,
        "within_10_of_optimal": regret is not None and regret <= 10.0,
        "forced_lineup": _lineup_players(forced_lineup) if forced_lineup is not None else None,
    }


def _completion_evidence(players: list[ShowdownPlayerPoolRow]) -> dict[str, Any]:
    team_plays: dict[str, float] = {}
    for player in players:
        if not player.team:
            continue
        team_plays.setdefault(player.team, 0.0)
        team_plays[player.team] += player.actual_pass_attempts + player.actual_carries
    complete_teams = sorted(
        team for team, plays in team_plays.items() if plays >= 20.0
    )
    return {
        "team_offensive_plays": team_plays,
        "complete_teams": complete_teams,
        "is_complete": len(complete_teams) >= 2,
        "rule": "at least two teams with 20 actual pass attempts plus carries",
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    scalar_rows = [
        {key: value for key, value in row.items() if key != "forced_lineup"}
        for row in rows
    ]
    if not scalar_rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(scalar_rows[0]))
        writer.writeheader()
        writer.writerows(scalar_rows)


def _markdown(payload: dict[str, Any]) -> str:
    rows = payload["slates"]
    captain_rows = payload["forced_captains"]
    feasible = [row for row in captain_rows if row["forced_captain_feasible"]]
    zero_count = sum(bool(row["actual_zero"]) for row in feasible)
    lines = [
        "# Showdown Oracle Dataset",
        "",
        f"- Generated: `{payload['generated_at']}`",
        f"- Slates: **{len(rows)}**",
        f"- Skipped incomplete slates: **{len(payload['skipped_slates'])}**",
        f"- Forced-Captain observations: **{len(captain_rows)}**",
        f"- Feasible forced-Captain observations: **{len(feasible)}**",
        f"- Zero-point Captain candidates: **{zero_count}**",
        "",
        "## Slate Oracles",
        "",
        "| Season | Week | Slate | Pool | Oracle score | Captain | Near-optimal lineups |",
        "|---:|---:|---|---:|---:|---|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['season']} | {row['week']} | {row['slate']} | {row['pool_size']} | "
            f"{row['optimal_score']:.2f} | {row['optimal_captain']} | {len(row['near_optimal_lineups'])} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "`captain_regret` is the actual-score difference between the unrestricted legal oracle and the best legal lineup with that player forced at Captain. Opportunity fields are pregame inputs; actual attempts, carries, targets, and points are labels only.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    start = min(args.season_start, args.season_end)
    end = max(args.season_start, args.season_end)
    forced_rows: list[dict[str, Any]] = []
    slate_rows: list[dict[str, Any]] = []
    skipped_slates: list[dict[str, Any]] = []

    with SessionLocal() as session:
        service = LineupLearningService(session)
        slices = service._fetch_available_slate_slices(
            source_system=args.source_system,
            season_start=start,
            season_end=end,
            slate_filter=None,
        )
        slices = service._filter_slices_by_slate_type(
            source_system=args.source_system,
            slices=slices,
            slate_type="showdown",
        )
        if args.limit_slates > 0:
            slices = slices[: args.limit_slates]

        for season, week, slate in slices:
            projection_lookup, dst_projection_lookup = service._compute_player_projection_lookup(
                source_system=args.source_system,
                season=season,
                week=week,
                slate=slate,
            )
            pool = service._fetch_showdown_player_pool(
                source_system=args.source_system,
                season=season,
                week=week,
                slate=slate,
                projection_lookup=projection_lookup,
                dst_projection_lookup=dst_projection_lookup,
                curated_actual_fallback=True,
            )
            completion = _completion_evidence(pool)
            if not completion["is_complete"]:
                skipped_slates.append(
                    {
                        "season": season,
                        "week": week,
                        "slate": slate,
                        "reason": "final_actual_usage_incomplete",
                        "completion_evidence": completion,
                    }
                )
                continue
            optimal = service.optimize_actual_showdown_lineup(players=pool)
            if optimal is None:
                skipped_slates.append(
                    {"season": season, "week": week, "slate": slate,
                     "reason": "no_legal_actual_score_lineup",
                     "completion_evidence": completion}
                )
                continue
            optimal_lineup, optimal_points, optimal_salary = optimal
            near_optimal = service.optimize_top_actual_showdown_lineups(
                players=pool,
                limit=max(1, args.top_lineups),
            )
            for player in pool:
                forced = service.optimize_actual_showdown_lineup(
                    players=pool,
                    forced_captain_uid=player.uid,
                )
                forced_rows.append(
                    _captain_row(
                        season=season,
                        week=week,
                        slate=slate,
                        player=player,
                        forced=forced,
                        optimal_points=optimal_points,
                    )
                )
            slate_rows.append(
                {
                    "season": season,
                    "week": week,
                    "slate": slate,
                    "pool_size": len(pool),
                    "optimal_score": optimal_points,
                    "optimal_salary": optimal_salary,
                    "optimal_captain": optimal_lineup.captain.name,
                    "optimal_lineup": _lineup_players(optimal_lineup),
                    "near_optimal_lineups": [
                        {
                            "rank": rank,
                            "score": points,
                            "regret": optimal_points - points,
                            "salary": salary,
                            "projected_mean": service._showdown_projected_mean(lineup),
                            "projected_p90": service._showdown_projected_p90(lineup),
                            "lineup": _lineup_players(lineup),
                        }
                        for rank, (lineup, points, salary) in enumerate(near_optimal, start=1)
                    ],
                }
            )

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source_system": args.source_system,
        "season_start": start,
        "season_end": end,
        "top_lineups_per_slate": max(1, args.top_lineups),
        "methodology": {
            "oracle": "actual DK points under historical Showdown salary and roster constraints",
            "actual_score_source_precedence": ["raw_nfl_weekly_stat", "curated_weekly_stats by player_master_id when raw is absent", "raw_nfl_schedule for DST"],
            "captain_label": "best legal score with each player forced at CPT",
            "captain_regret": "unrestricted oracle score minus forced-CPT oracle score",
            "pregame_inputs_only": True,
            "actual_usage_is_label_only": True,
        },
        "slates": slate_rows,
        "skipped_slates": skipped_slates,
        "forced_captains": forced_rows,
    }
    json_path = Path(args.output_json)
    csv_path = Path(args.output_csv)
    md_path = Path(args.output_md)
    for path in (json_path, csv_path, md_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    _write_csv(csv_path, forced_rows)
    md_path.write_text(_markdown(payload), encoding="utf-8")
    print(
        json.dumps(
            {
                "slates": len(slate_rows),
                "skipped_slates": len(skipped_slates),
                "forced_captain_rows": len(forced_rows),
                "json": str(json_path),
                "csv": str(csv_path),
                "report": str(md_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
