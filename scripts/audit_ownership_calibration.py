"""Read-only, pre-lock ownership calibration audit for saved model runs.

Usage: PYTHONPATH=. .venv/bin/python scripts/audit_ownership_calibration.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

from Database.config import get_connection_string


OUTPUT = Path("artifacts/ownership-calibration-historical.json")


def error_summary(rows: pd.DataFrame) -> dict:
    if rows.empty:
        return {"rows": 0, "mae": None, "rmse": None, "bias": None,
                "correlation": None, "mean_projected": None, "mean_actual": None}
    error = rows["projected_ownership"] - rows["actual_ownership"]
    correlation = (rows["projected_ownership"].corr(rows["actual_ownership"])
                   if len(rows) > 1 else None)
    return {"rows": len(rows), "mae": float(error.abs().mean()),
            "rmse": float(np.sqrt((error * error).mean())),
            "bias": float(error.mean()),
            "correlation": float(correlation) if pd.notna(correlation) else None,
            "mean_projected": float(rows["projected_ownership"].mean()),
            "mean_actual": float(rows["actual_ownership"].mean())}


def calibration_report(rows: pd.DataFrame) -> dict:
    """Compare canonical players within each contest; preserve contest differences."""
    if rows.empty:
        return {"overall": error_summary(rows), "coverage": {"matched_rows": 0}}
    frame = rows.copy()
    frame["projected_bucket"] = pd.cut(
        frame["projected_ownership"], [-0.001, 1, 5, 10, 20, 30, 50, 100],
        labels=["0-1", "1-5", "5-10", "10-20", "20-30", "30-50", "50-100"],
        include_lowest=True,
    ).astype(str)
    frame["salary_tier"] = pd.cut(
        frame["salary"], [-1, 3500, 5000, 7000, float("inf")],
        labels=["<=3500", "3501-5000", "5001-7000", ">7000"],
    ).astype(str)
    frame["actual_bucket"] = pd.cut(
        frame["actual_ownership"], [-0.001, 1, 5, 10, 20, 30, 50, 100],
        labels=["0-1", "1-5", "5-10", "10-20", "20-30", "30-50", "50-100"],
        include_lowest=True,
    ).astype(str)

    def grouped(keys: list[str]) -> dict:
        return {"|".join(map(str, key if isinstance(key, tuple) else (key,))):
                error_summary(group) for key, group in frame.groupby(keys, dropna=False)}

    top = frame.sort_values(
        ["season", "week", "slate", "contest_id", "projected_ownership"],
        ascending=[True, True, True, True, False],
    ).groupby(["season", "week", "slate", "contest_id"]).head(10)
    low = frame.loc[frame["projected_ownership"] < 5]
    tail = {str(threshold): {"count": int((low["actual_ownership"] > threshold).sum()),
                             "rate": float((low["actual_ownership"] > threshold).mean())
                             if len(low) else None}
            for threshold in (10, 20, 30)}
    return {
        "overall": error_summary(frame),
        "by_slate": grouped(["season", "week", "slate"]),
        "by_projected_bucket": grouped(["projected_bucket"]),
        "by_actual_bucket": grouped(["actual_bucket"]),
        "by_position": grouped(["position"]),
        "by_salary_tier": grouped(["salary_tier"]),
        "by_slate_type": grouped(["slate"]),
        "by_contest_format": grouped(["contest_format"]),
        "by_contest_type": grouped(["contest_type"]),
        "by_field_size": grouped(["field_size_tier"]),
        "top_10_projected_per_contest": error_summary(top),
        "top_10_projected_per_contest_by_slate": {
            "|".join(map(str, key)): error_summary(group)
            for key, group in top.groupby(["season", "week", "slate"])
        },
        "projected_under_5_actual_over": {"eligible_rows": len(low), **tail},
        "actual_vs_projected": frame[["season", "week", "slate", "contest_id",
                                       "player_id", "position", "salary",
                                       "projected_ownership", "actual_ownership"]].to_dict("records"),
    }


def load_matched_rows(engine) -> tuple[pd.DataFrame, list[dict]]:
    with engine.connect() as conn:
        runs = pd.read_sql(text("""
            SELECT r.ownership_run_id, r.season, r.week, r.slate_id AS slate,
                   r.data_cutoff_at, r.created_at,
                   MIN(((g.raw_row_json ->> 'gameday') || ' ' || g.kickoff)::timestamp
                       AT TIME ZONE 'America/New_York') AS slate_lock_at
            FROM target.ownership_model_run r
            JOIN public.raw_nfl_schedule g ON g.season = r.season AND g.week = r.week
                 AND g.raw_row_json ->> 'weekday' = CASE
                     WHEN r.slate_id LIKE 'THURSDAY%' THEN 'Thursday'
                     WHEN r.slate_id LIKE 'MONDAY%' THEN 'Monday'
                     WHEN r.slate_id LIKE 'SUNDAY%' THEN 'Sunday'
                     WHEN r.slate_id LIKE 'WEDNESDAY%' THEN 'Wednesday'
                     ELSE '' END
            WHERE r.status = 'completed' AND r.data_cutoff_at IS NOT NULL
                  AND g.raw_row_json ->> 'gameday' IS NOT NULL
            GROUP BY r.ownership_run_id, r.season, r.week, r.slate_id,
                     r.data_cutoff_at, r.created_at
        """), conn)
        if runs.empty:
            return pd.DataFrame(), []
        runs = runs.sort_values(
            ["season", "week", "slate", "data_cutoff_at", "created_at", "ownership_run_id"]
        ).reset_index(drop=True)
        runs["prelock"] = runs["data_cutoff_at"] < runs["slate_lock_at"]
        eligible = runs.loc[runs["prelock"]].sort_values(
            ["season", "week", "slate", "data_cutoff_at", "created_at"]
        ).drop_duplicates(["season", "week", "slate"], keep="last")
        selected_ids = eligible["ownership_run_id"].tolist()
        runs["selected_for_slate"] = runs["ownership_run_id"].isin(selected_ids)
        if not selected_ids:
            return pd.DataFrame(), runs.to_dict("records")
        forecasts = pd.read_sql(text("""
            SELECT ownership_run_id, season, week, slate_id AS slate, player_id,
                   roster_position, projected_ownership,
                   NULLIF(feature_json ->> 'salary', '')::DOUBLE PRECISION AS salary,
                   feature_json ->> 'position' AS position,
                   feature_json ->> 'contest_format' AS forecast_format
            FROM target.ownership_projection
            WHERE ownership_run_id = ANY(:run_ids)
        """), conn, params={"run_ids": selected_ids})
        actual = pd.read_sql(text("""
            SELECT o.season, o.week, o.slate, o.contest_id, o.player_id,
                   o.roster_position, o.actual_ownership,
                   COALESCE(c.contest_format, 'unknown') AS contest_format,
                   COALESCE(c.contest_type, 'unknown') AS contest_type,
                   c.field_size
            FROM target.contest_ownership_observation o
            LEFT JOIN target.dfs_contest c ON c.contest_id = o.contest_id
            WHERE o.resolution_status = 'resolved' AND o.player_id IS NOT NULL
                  AND o.actual_ownership IS NOT NULL
        """), conn)
    if forecasts.empty or actual.empty:
        return pd.DataFrame(), runs.to_dict("records")
    # Classic ownership is the probability a player appears in any roster slot.
    # Contest files give position and FLEX percentages separately; sum those.
    forecasts["slot"] = np.where(forecasts["forecast_format"].eq("showdown"),
                                  forecasts["roster_position"].str.upper(), "ALL")
    actual["slot"] = np.where(actual["contest_format"].eq("showdown"),
                               actual["roster_position"].str.upper(), "ALL")
    projected = forecasts.groupby(
        ["season", "week", "slate", "player_id", "slot"], as_index=False
    ).agg(projected_ownership=("projected_ownership", "sum"), salary=("salary", "max"),
          position=("position", "first"), ownership_run_id=("ownership_run_id", "first"))
    observed = actual.groupby(
        ["season", "week", "slate", "contest_id", "player_id", "slot",
         "contest_format", "contest_type", "field_size"], dropna=False, as_index=False
    )["actual_ownership"].sum()
    matched = observed.merge(projected, on=["season", "week", "slate", "player_id", "slot"],
                             how="inner", validate="many_to_one")
    matched["field_size_tier"] = pd.cut(
        matched["field_size"], [-1, 1000, 10000, 50000, float("inf")],
        labels=["<=1000", "1001-10000", "10001-50000", ">50000"],
    ).astype(str)
    matched = matched.sort_values(
        ["season", "week", "slate", "contest_id", "player_id", "slot"]
    ).reset_index(drop=True)
    return matched, runs.to_dict("records")


def main() -> None:
    rows, runs = load_matched_rows(create_engine(get_connection_string()))
    report = calibration_report(rows)
    report["coverage"] = {
        "saved_runs": len(runs), "prelock_runs": sum(bool(run["prelock"]) for run in runs),
        "matched_slates": sorted({f"{r.season}-W{int(r.week):02d}-{r.slate}"
                                  for r in rows.itertuples()}),
        "contest_count": int(rows["contest_id"].nunique()) if not rows.empty else 0,
        "selected_runs": [
            {"season": int(run["season"]), "week": int(run["week"]),
             "slate": run["slate"], "ownership_run_id": run["ownership_run_id"],
             "data_cutoff_at": run["data_cutoff_at"].isoformat(),
             "slate_lock_at": run["slate_lock_at"].isoformat()}
            for run in runs if run["selected_for_slate"]
        ],
        "selection": "latest saved ownership run strictly before first slate kickoff",
        "limitation": "Only slates with saved prelock forecasts and resolved contest observations are scored",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(f"{OUTPUT}: {report['overall']}; {report['coverage']}")


if __name__ == "__main__":
    main()
