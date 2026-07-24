#!/usr/bin/env python3
"""Compare DT-502 leverage with the retired points-minus-ownership proxy."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Database.config import get_connection_string


CONTRACT_ID = "dt_502_top_lineup_replay_v1"


def evaluate_frame(frame: pd.DataFrame, *, top_k: int = 20) -> dict[str, Any]:
    required = {
        "season",
        "week",
        "player_id",
        "projection_mean",
        "field_ownership",
        "leverage_score",
        "actual_top_lineup_exposure",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError("Replay frame is missing: " + ", ".join(missing))
    scored = frame.dropna(subset=["field_ownership", "leverage_score"]).copy()
    if scored.empty:
        return {
            "status": "insufficient_data",
            "weeks": 0,
            "player_rows": 0,
            "matched_top_lineup_players": 0,
            "performance_claim_eligible": False,
        }
    scored["legacy_proxy"] = scored["projection_mean"] - scored["field_ownership"]
    groups = scored.groupby(["season", "week"], dropna=False)
    scored["dt_502_rank"] = groups["leverage_score"].rank(method="min", ascending=False)
    scored["legacy_rank"] = groups["legacy_proxy"].rank(method="min", ascending=False)
    scored["actual_rank"] = groups["actual_top_lineup_exposure"].rank(
        method="min", ascending=False
    )
    dt_502_top = scored.loc[
        scored["dt_502_rank"] <= top_k, "actual_top_lineup_exposure"
    ]
    legacy_top = scored.loc[
        scored["legacy_rank"] <= top_k, "actual_top_lineup_exposure"
    ]
    weeks = int(scored[["season", "week"]].drop_duplicates().shape[0])
    matched = int((scored["actual_top_lineup_exposure"] > 0).sum())
    dt_502_exposure = float(dt_502_top.mean()) if not dt_502_top.empty else 0.0
    legacy_exposure = float(legacy_top.mean()) if not legacy_top.empty else 0.0
    eligible = weeks >= 3 and matched >= 20 and dt_502_exposure > legacy_exposure
    def rank_correlation(left: str, right: str) -> float | None:
        if len(scored) < 2 or scored[left].nunique() < 2 or scored[right].nunique() < 2:
            return None
        return round(float(scored[left].corr(scored[right])), 6)

    return {
        "status": "passed" if eligible else "failed",
        "weeks": weeks,
        "player_rows": int(len(scored)),
        "matched_top_lineup_players": matched,
        "top_k": int(top_k),
        "dt_502_top_k_average_exposure": round(dt_502_exposure, 6),
        "legacy_top_k_average_exposure": round(legacy_exposure, 6),
        "top_k_exposure_lift": round(dt_502_exposure - legacy_exposure, 6),
        "dt_502_rank_correlation": rank_correlation("dt_502_rank", "actual_rank"),
        "legacy_rank_correlation": rank_correlation("legacy_rank", "actual_rank"),
        "performance_claim_eligible": eligible,
    }


def load_replay_frame(
    *,
    database_url: Any,
    season: int,
    slate: str,
    weeks: list[int] | None,
) -> pd.DataFrame:
    engine = create_engine(database_url)
    week_filter = "AND run.week = ANY(:weeks)" if weeks else ""
    params: dict[str, Any] = {"season": season, "slate": slate}
    if weeks:
        params["weeks"] = weeks
    query = text(
        f"""
        WITH latest_run AS (
            SELECT DISTINCT ON (run.season, run.week, UPPER(run.slate_id))
                run.simulation_run_id,
                run.season,
                run.week,
                UPPER(run.slate_id) AS slate
            FROM target.simulation_run run
            WHERE run.season = :season
              AND UPPER(run.slate_id) = UPPER(:slate)
              AND run.status = 'completed'
              {week_filter}
            ORDER BY run.season, run.week, UPPER(run.slate_id), run.created_at DESC
        ),
        top_lineup_exposure AS (
            SELECT
                lineup.season,
                lineup.week,
                UPPER(lineup.slate) AS slate,
                player.player_master_id AS player_id,
                COUNT(DISTINCT player.actual_top_lineup_id)::DOUBLE PRECISION
                    AS actual_top_lineup_exposure
            FROM actual_top_lineup_player player
            JOIN actual_top_lineup lineup USING (actual_top_lineup_id)
            WHERE lineup.season = :season
              AND UPPER(lineup.slate) = UPPER(:slate)
            GROUP BY lineup.season, lineup.week, UPPER(lineup.slate), player.player_master_id
        )
        SELECT
            run.season,
            run.week,
            player.player_id,
            player.projection_mean,
            player.field_ownership,
            player.leverage_score,
            COALESCE(actual.actual_top_lineup_exposure, 0.0)
                AS actual_top_lineup_exposure
        FROM latest_run run
        JOIN target.player_simulation player USING (simulation_run_id)
        LEFT JOIN top_lineup_exposure actual
          ON actual.season = run.season
         AND actual.week = run.week
         AND actual.slate = run.slate
         AND actual.player_id = player.player_id
        """
    )
    with engine.begin() as connection:
        return pd.read_sql(query, connection, params=params)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="football_26_dev")
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--slate", default="SUNDAY_MAIN")
    parser.add_argument("--weeks", type=int, nargs="*")
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    database_url = make_url(get_connection_string()).set(database=args.database)
    frame = load_replay_frame(
        database_url=database_url,
        season=args.season,
        slate=args.slate,
        weeks=args.weeks,
    )
    report = {
        "contract_id": CONTRACT_ID,
        "season": args.season,
        "slate": args.slate,
        "requested_weeks": args.weeks or [],
        **evaluate_frame(frame, top_k=args.top_k),
    }
    print(json.dumps(report, indent=2 if args.pretty else None, sort_keys=True))
    return 0 if report["performance_claim_eligible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
