"""Describe saved pre-lock Sunday Main stack outcomes without changing policy."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from sqlalchemy import create_engine, text

from Database.config import get_connection_string


OUTPUT = Path("artifacts/classic-stack-outcomes-historical.json")


def construction(players: list[dict]) -> tuple[str, dict]:
    qb = next((row for row in players if row["position"] == "QB"), None)
    if qb is None:
        return "unclassified", {}
    catches = sum(row["position"] in {"WR", "TE"} and row["team"] == qb["team"]
                  for row in players)
    bring_back = sum(row["position"] in {"RB", "WR", "TE"}
                     and row["team"] == qb["opponent"] for row in players)
    family = f"QB+{catches}" if catches else "QB naked"
    if bring_back:
        family += "+bring-back"
    return family, qb


def main() -> None:
    engine = create_engine(get_connection_string())
    with engine.connect() as conn:
        rows = conn.execute(text("""
            WITH locks AS (
                SELECT season, week,
                       MIN(((raw_row_json ->> 'gameday') || ' ' || kickoff)::timestamp
                           AT TIME ZONE 'America/New_York') AS lock_at
                FROM public.raw_nfl_schedule
                WHERE raw_row_json ->> 'weekday' = 'Sunday'
                  AND raw_row_json ->> 'gameday' IS NOT NULL
                GROUP BY season, week
            ), fact_actual AS (
                SELECT season, week, player_master_id AS player_id,
                       MAX(dk_points) AS dk_points
                FROM public.player_game_feature_matrix
                WHERE player_master_id IS NOT NULL
                GROUP BY season, week, player_master_id
            ), contest_actual AS (
                SELECT season, week, player_id, MAX(actual_points) AS dk_points
                FROM target.contest_ownership_observation
                WHERE slate = 'SUNDAY_MAIN' AND resolution_status = 'resolved'
                  AND player_id IS NOT NULL AND actual_points IS NOT NULL
                GROUP BY season, week, player_id
            ), contest_period AS (
                SELECT DISTINCT season, week FROM contest_actual
            ), actual AS (
                SELECT c.season, c.week, c.player_id, c.dk_points,
                       'contest_results' AS actual_source
                FROM contest_actual c
                UNION ALL
                SELECT f.season, f.week, f.player_id, f.dk_points,
                       'player_game_feature_matrix' AS actual_source
                FROM fact_actual f LEFT JOIN contest_period p
                  ON p.season = f.season AND p.week = f.week
                WHERE p.season IS NULL
            )
            SELECT r.season, r.week, r.optimizer_run_id, r.strategy,
                   r.created_at, l.lineup_id, l.projected_mean,
                   r.constraint_config_json #>> '{strategy_runtime,classic_small_field,contest,capacity}'
                       AS contest_size,
                   lp.player_id, lp.player_json ->> 'position' AS position,
                   COALESCE(lp.player_json ->> 'player_team', lp.player_json ->> 'team') AS team,
                   lp.player_json ->> 'opponent_team' AS opponent,
                   lp.player_json ->> 'game_total_line' AS game_total,
                   lp.player_json ->> 'team_implied_total' AS team_total,
                   lp.player_json ->> 'team_spread_line' AS spread,
                   lp.player_json ->> 'market_context_point_in_time_safe' AS market_safe,
                   a.dk_points, a.actual_source
            FROM target.optimizer_run r
            JOIN locks k ON k.season = r.season AND k.week = r.week
            JOIN target.lineup l ON l.optimizer_run_id = r.optimizer_run_id
            JOIN target.lineup_player lp ON lp.lineup_id = l.lineup_id
            LEFT JOIN actual a ON a.season = r.season AND a.week = r.week
                              AND a.player_id = lp.player_id
            WHERE UPPER(r.slate_id) = 'SUNDAY_MAIN' AND r.contest_format = 'classic'
              AND r.objective = 'gpp' AND r.status = 'completed'
              AND r.created_at < k.lock_at
              AND (r.data_cutoff_at IS NULL OR r.data_cutoff_at < k.lock_at)
            ORDER BY r.season, r.week, r.created_at, l.lineup_id, lp.slot_index
        """)).mappings().all()
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[str(row["lineup_id"])].append(dict(row))
    unique: dict[tuple, dict] = {}
    incomplete = 0
    for lineup in grouped.values():
        if len(lineup) != 9 or any(row["dk_points"] is None for row in lineup):
            incomplete += 1
            continue
        first = lineup[0]
        key = (first["season"], first["week"], tuple(sorted(row["player_id"] for row in lineup)))
        if key in unique:
            continue
        family, qb = construction(lineup)
        def safe_float(value):
            try:
                return float(value) if value is not None else None
            except (TypeError, ValueError):
                return None
        market_safe = qb.get("market_safe") == "true" if qb else False
        unique[key] = {
            "season": first["season"], "week": first["week"],
            "optimizer_run_id": first["optimizer_run_id"],
            "strategy": first["strategy"], "lineup_id": first["lineup_id"],
            "actual_source": first["actual_source"],
            "construction": family, "projected_mean": safe_float(first["projected_mean"]),
            "actual_score": sum(float(row["dk_points"]) for row in lineup),
            "game_total": safe_float(qb.get("game_total")) if market_safe else None,
            "team_total": safe_float(qb.get("team_total")) if market_safe else None,
            "spread": safe_float(qb.get("spread")) if market_safe else None,
            "contest_size": safe_float(first["contest_size"]),
            "market_point_in_time_safe": market_safe,
        }
    lineups = list(unique.values())
    def summary(items: list[dict]) -> dict:
        if not items:
            return {"lineups": 0}
        return {"lineups": len(items), "mean_actual_score": sum(x["actual_score"] for x in items)/len(items),
                "mean_projected_score": sum(x["projected_mean"] for x in items
                                            if x["projected_mean"] is not None)
                                            / max(1, sum(x["projected_mean"] is not None for x in items)),
                "slates": sorted({f"{x['season']}-W{x['week']:02d}" for x in items})}
    by_family: dict[str, list[dict]] = defaultdict(list)
    by_total: dict[str, list[dict]] = defaultdict(list)
    by_team_total: dict[str, list[dict]] = defaultdict(list)
    by_spread: dict[str, list[dict]] = defaultdict(list)
    by_contest_size: dict[str, list[dict]] = defaultdict(list)
    by_family_slate: dict[str, list[dict]] = defaultdict(list)
    for row in lineups:
        by_family[row["construction"]].append(row)
        by_family_slate[f"{row['season']}-W{row['week']:02d}|{row['construction']}"].append(row)
        by_total["unavailable" if row["game_total"] is None else
                 "<45" if row["game_total"] < 45 else "45-49.9" if row["game_total"] < 50 else ">=50"].append(row)
        by_team_total["unavailable" if row["team_total"] is None else
                      "<22" if row["team_total"] < 22 else "22-25.9" if row["team_total"] < 26 else ">=26"].append(row)
        by_spread["unavailable" if row["spread"] is None else
                  "competitive <=4" if abs(row["spread"]) <= 4 else "spread >4"].append(row)
        by_contest_size["unavailable" if row["contest_size"] is None else
                        "<=1000" if row["contest_size"] <= 1000 else
                        "1001-10000" if row["contest_size"] <= 10000 else ">10000"].append(row)
    report = {
        "scope": "Saved Classic Sunday Main GPP lineups created before first Sunday kickoff; unique rosters per slate",
        "limitations": ["Selected lineup observations are not randomized construction tests.",
                        "Candidate archives and contest field sizes are not consistently stored for these runs.",
                        "Naked QB lineups are unavailable when strategy construction requires a pass catcher."],
        "saved_lineups": len(grouped), "incomplete_actual_lineups": incomplete,
        "unique_complete_lineups": len(lineups),
        "by_construction": {key: summary(value) for key, value in sorted(by_family.items())},
        "by_construction_and_slate": {key: summary(value) for key, value in sorted(by_family_slate.items())},
        "by_game_total": {key: summary(value) for key, value in sorted(by_total.items())},
        "by_implied_team_total": {key: summary(value) for key, value in sorted(by_team_total.items())},
        "by_spread": {key: summary(value) for key, value in sorted(by_spread.items())},
        "by_contest_size": {key: summary(value) for key, value in sorted(by_contest_size.items())},
        "lineups": lineups,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(f"{OUTPUT}: {len(lineups)} unique complete lineups; {report['by_construction']}")


if __name__ == "__main__":
    main()
