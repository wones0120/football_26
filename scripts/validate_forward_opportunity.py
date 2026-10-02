"""Read-only, point-in-time shadow comparison of forward-opportunity projections.

Historical raw stats are filtered by game week at every forecast. The source
snapshot itself was ingested later, so this is chronological validation rather
than a complete historical source-availability replay.
"""
from __future__ import annotations

import argparse
import json
from datetime import UTC
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from sklearn.ensemble import GradientBoostingRegressor

from Database.config import get_connection_string
from backend.app.product_services.canonical_projection_inputs import FEATURE_COLUMNS, load_inputs
from backend.app.product_services.forward_opportunity import (
    STAT_COLUMNS, forecast_player_opportunities, forecast_team_volumes,
    opportunity_sanity, prepare_weekly_stats, project_components,
)
from backend.app.product_services.predictions import TARGET_COL, blend_point_predictions


def load_weekly(engine, cutoff, *, season):
    # Bronze created_at is stored as UTC-naive. Normalize aware application
    # cutoffs before PostgreSQL compares the timestamp-without-time-zone field.
    if getattr(cutoff, "tzinfo", None) is not None:
        cutoff = cutoff.astimezone(UTC).replace(tzinfo=None)
    fields = ",\n".join(
        f"NULLIF(raw.raw_row_json ->> '{field}', '')::DOUBLE PRECISION AS {field}"
        for field in STAT_COLUMNS
    )
    query = f"""
        WITH latest AS (
            SELECT DISTINCT ON (season, week, player_id) *
            FROM public.raw_nfl_weekly_stat
            WHERE season BETWEEN 2024 AND :season AND created_at <= :cutoff
            ORDER BY season, week, player_id, created_at DESC, raw_nfl_weekly_stat_id DESC
        )
        SELECT raw.season, raw.week, raw.team, raw.position,
               alias.player_master_id, raw.player_id AS source_player_id,
               {fields}
        FROM latest raw
        LEFT JOIN public.player_alias alias
          ON alias.source_system = 'nflreadpy' AND alias.source_key = raw.player_id
    """
    with engine.connect() as connection:
        frame = pd.read_sql(text(query), connection, params={"cutoff": cutoff, "season": season})
    return prepare_weekly_stats(frame)


def metrics(frame, prediction):
    if frame.empty:
        return {"n": 0}
    error = frame[prediction] - frame["actual"]
    return {"n": len(frame), "mae": float(error.abs().mean()),
            "rmse": float(np.sqrt(np.square(error).mean())), "bias": float(error.mean())}


def prior_week_p90_proxy(frame: pd.DataFrame) -> dict:
    """Evaluate mean-plus-residual P90 using only earlier held-out weeks."""
    output = {}
    for name in ("direct", "hybrid"):
        rows = []
        for week in sorted(frame["week"].unique()):
            prior = frame.loc[frame["week"].lt(week)]
            current = frame.loc[frame["week"].eq(week)]
            if len(prior) < 100:
                continue
            global_quantile = float((prior["actual"] - prior[name]).quantile(0.9))
            for position, group in current.groupby("position"):
                prior_position = prior.loc[prior["position"].eq(position)]
                quantile = (float((prior_position["actual"] - prior_position[name]).quantile(0.9))
                            if len(prior_position) >= 30 else global_quantile)
                proxy = group[name] + quantile
                rows.append({"week": int(week), "position": position,
                             "prior_residual_p90": quantile,
                             "n": len(group), "exceeded": int(group["actual"].gt(proxy).sum()),
                             "absolute_error": float((group["actual"] - proxy).abs().sum())})
        n = sum(row["n"] for row in rows)
        output[name] = {"n": n, "weeks": sorted({row["week"] for row in rows}),
                        "exceedance_rate": sum(row["exceeded"] for row in rows) / n if n else None,
                        "target_exceedance_rate": 0.10,
                        "mean_absolute_error": sum(row["absolute_error"] for row in rows) / n if n else None,
                        "calibration_rows": rows}
    output["method"] = "position residual 90th percentile from earlier held-out weeks; global fallback below 30 position rows"
    output["limitation"] = "Diagnostic proxy, not the production P90 calibration or full outcome distribution"
    return output


def compare(train, weekly, weeks):
    residuals = []
    for week in weeks:
        prior = train.loc[(train["season"] < 2025) | (train["season"].eq(2025) & train["week"].lt(week))]
        holdout = train.loc[train["season"].eq(2025) & train["week"].eq(week)].copy()
        if len(prior) < 100 or holdout.empty:
            continue
        model = GradientBoostingRegressor(random_state=42)
        model.fit(prior[FEATURE_COLUMNS].apply(pd.to_numeric, errors="coerce").fillna(0.0),
                  prior[TARGET_COL])
        raw = model.predict(holdout[FEATURE_COLUMNS].apply(pd.to_numeric, errors="coerce").fillna(0.0))
        holdout["point_prediction"] = blend_point_predictions(raw, prior, holdout)
        holdout["actual"] = holdout[TARGET_COL]
        residuals.append(holdout)
    if not residuals:
        return {"status": "unavailable", "reason": "no direct-model walk-forward rows"}
    validation = pd.concat(residuals, ignore_index=True)
    validation["player_id"] = validation["player_id"].astype(str)
    validation["period"] = validation["season"].astype(int) * 100 + validation["week"].astype(int)
    records = []
    week_status = []
    for week in weeks:
        period = 202500 + week
        direct = validation.loc[validation["period"].eq(period)]
        targets = train.loc[train["season"].eq(2025) & train["week"].eq(week)].copy()
        if direct.empty or targets.empty:
            week_status.append({"week": week, "status": "no direct model or target rows"})
            continue
        targets["player_id"] = targets["player_id"].astype(str)
        targets = targets.merge(direct[["player_id", "point_prediction", "actual"]],
                                on="player_id", how="inner")
        targets["predicted_mean"] = targets["point_prediction"]
        teams = forecast_team_volumes(weekly, train, targets, period=period)
        opportunities, reconciliation = forecast_player_opportunities(weekly, targets, teams, period=period)
        components = project_components(weekly, opportunities, teams, period=period)
        component_by_id = {row["player_id"]: row for row in components}
        for row in targets.to_dict("records"):
            projection = component_by_id.get(str(row["player_id"]))
            if not projection or projection["component_status"] != "available":
                continue
            records.append({"season": 2025, "week": week, "player_id": str(row["player_id"]),
                            "position": row["position"], "role_class": row.get("offensive_role_class"),
                            "actual": float(row["actual"]), "direct": float(row["point_prediction"]),
                            "component": projection["component_mean"],
                            "hybrid": projection["hybrid_mean"]})
        week_status.append({"week": week, "direct_rows": len(direct), "covered_rows": len(records) - sum(
            item.get("covered_rows", 0) for item in week_status), "team_forecasts": sum(
                item.get("status") == "available" for item in teams.values()),
                            "team_reconciliations": len(reconciliation)})
    frame = pd.DataFrame(records)
    if frame.empty:
        return {"status": "unavailable", "reason": "no component projections on validation weeks",
                "weeks": week_status}
    result = {"status": "available", "weeks": week_status,
              "direct_all_rows": len(validation), "shadow_covered_rows": len(frame),
              "shadow_coverage": float(len(frame) / len(validation)),
              "same_row_metrics": {name: metrics(frame, name) for name in ("direct", "component", "hybrid")},
              "direct_full_metrics": metrics(validation.rename(columns={"point_prediction": "direct"}), "direct"),
              "by_position": {}, "by_role_class": {},
              "top_decile": {}, "p90": prior_week_p90_proxy(frame)}
    for field, output in (("position", "by_position"), ("role_class", "by_role_class")):
        for key, group in frame.groupby(field, dropna=False):
            result[output][str(key)] = {name: metrics(group, name) for name in ("direct", "hybrid")}
    threshold = frame["actual"].quantile(0.9)
    high = frame.loc[frame["actual"].ge(threshold)]
    result["top_decile"] = {"actual_threshold": float(threshold),
                             "direct": metrics(high, "direct"), "hybrid": metrics(high, "hybrid")}
    selected_count = max(1, int(np.ceil(len(frame) * 0.1)))
    actual_top = set(frame.nlargest(selected_count, "actual").index)
    result["top_decile"]["selection_precision"] = {
        name: len(actual_top & set(frame.nlargest(selected_count, name).index)) / selected_count
        for name in ("direct", "hybrid")}
    result["promotion"] = "shadow only; no automatic promotion"
    result["limitation"] = "Historical source snapshots were ingested retrospectively; game-order leakage is prevented, but source-availability replay is not proven."
    return result


def current_shadow(train, target, weekly, *, saved_optimizer_json: Path, period: int):
    """Explain saved high-role exposure using current shadow workloads."""
    saved = json.loads(saved_optimizer_json.read_text())
    report = saved["results"][0][0]["classic_small_field_report"]
    exposure = {str(row["player_id"]): row for row in report["role_exposure"]}
    targets = target.copy()
    targets["player_id"] = targets["player_id"].astype(str)
    targets["predicted_mean"] = targets["player_id"].map(
        {key: row["mean"] for key, row in exposure.items()})
    teams = forecast_team_volumes(weekly, train, targets, period=period)
    opportunities, reconciliation = forecast_player_opportunities(
        weekly, targets, teams, period=period)
    components = project_components(weekly, opportunities, teams, period=period)
    by_id = {row["player_id"]: row for row in components}
    players = []
    for record in report["role_exposure"]:
        if record["role_class"] != "offensive centerpiece" and (record["importance"] or 0) < 0.6:
            continue
        row = by_id.get(str(record["player_id"]))
        peers = [peer for peer in report["role_exposure"] if peer["position"] == record["position"]]
        value_rank = 1 + sum((peer.get("mean_per_1000_salary") or 0) > (record.get("mean_per_1000_salary") or 0)
                             for peer in peers)
        mean_rank = 1 + sum((peer.get("mean") or 0) > (record.get("mean") or 0) for peer in peers)
        p90_rank = 1 + sum((peer.get("p90") or 0) > (record.get("p90") or 0) for peer in peers)
        players.append({"player_id": record["player_id"], "name": record["name"],
                        "team": record["team"], "position": record["position"],
                        "role_class": record["role_class"], "role_importance": record["importance"],
                        "candidate_exposure": record["candidate_rate"],
                        "salary": record["salary"], "salary_adjusted_value": record["mean_per_1000_salary"],
                        "position_mean_rank": mean_rank, "position_p90_rank": p90_rank,
                        "position_value_rank": value_rank, "position_peer_count": len(peers),
                        "direct_mean": record["mean"], "direct_p90": record["p90"],
                        "expected_carries": row.get("expected_carries") if row else None,
                        "expected_targets": row.get("expected_targets") if row else None,
                        "target_share_blend": row.get("target_share_blend") if row else None,
                        "carry_share_blend": row.get("carry_share_blend") if row else None,
                        "role_factor": row.get("role_factor") if row else None,
                        "availability_evidence": row.get("availability_evidence") if row else None,
                        "context_adjustment": row.get("context_adjustment") if row else None,
                        "team_implied_total": row.get("team_implied_total") if row else None,
                        "component_mean": row.get("component_mean") if row else None,
                        "hybrid_mean": row.get("hybrid_mean") if row else None,
                        "shadow_status": row.get("component_status") if row else "unavailable",
                        "unavailable_reason": (row.get("reason") if row else
                                               "team volume unavailable or player outside target slate"),
                        "opportunity_confidence": row.get("opportunity_confidence") if row else "unavailable",
                        "last_opportunity_period": row.get("last_opportunity_period") if row else None,
                        "explanation": (f"Historical-only workload is plausible, but the unchanged direct-model salary-adjusted value ranks {value_rank}/{len(peers)} at {record['position']} and candidate exposure is {record['candidate_rate']:.1%}. Stack and lineup construction may also contribute; no causal attribution or projection substitution is claimed."
                                        if row else "Forward opportunity unavailable; source role/efficiency evidence incomplete.")})
    return {"status": "shadow only", "players": players,
            "teams": reconciliation, "sanity_flags": opportunity_sanity(opportunities, reconciliation),
            "current_season_weekly_rows": int(weekly["season"].eq(period // 100).sum()),
            "current_week_usage": ("unavailable: no current-season raw weekly stats at saved cutoff"
                                   if not weekly["season"].eq(period // 100).any()
                                   else "available where native-ID history and team coverage permit"),
            "optimizer_unchanged": True,
            "direct_projection_unchanged": True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--weeks", nargs="+", type=int, default=[10, 11, 12, 13, 17, 18])
    parser.add_argument("--output", type=Path, default=Path("artifacts/forward-opportunity-shadow-2025.json"))
    parser.add_argument("--projection-run-id", default="bba2fa75-3af1-4f8f-8331-b22107c7da79")
    parser.add_argument("--saved-optimizer-json", type=Path,
                        default=Path("artifacts/sunday-role-diagnostic-2026w2.json"))
    args = parser.parse_args()
    engine = create_engine(get_connection_string())
    with engine.connect() as connection:
        run = connection.execute(text("""
            SELECT season, week, slate_id, data_cutoff_at FROM target.projection_run
            WHERE projection_run_id = :projection_run_id AND status = 'completed'
        """), {"projection_run_id": args.projection_run_id}).mappings().one()
    train, target, metadata = load_inputs(engine, season=run["season"], week=run["week"],
                                     slate=run["slate_id"], cutoff=run["data_cutoff_at"])
    weekly = load_weekly(engine, run["data_cutoff_at"], season=run["season"])
    result = compare(train, weekly, args.weeks)
    result["current_sunday_shadow"] = current_shadow(
        train, target, weekly, saved_optimizer_json=args.saved_optimizer_json,
        period=int(run["season"]) * 100 + int(run["week"]))
    result["source"] = {"projection_run_id": args.projection_run_id,
                        "cutoff": str(run["data_cutoff_at"]), "weekly_rows": len(weekly),
                        "missing_canonical_player_ids": int(weekly["player_master_id"].isna().sum()),
                        "metadata": {"slate": run["slate_id"], "season": run["season"], "week": run["week"]}}
    args.output.write_text(json.dumps(result, indent=2, default=str, allow_nan=False) + "\n")
    print(json.dumps({"status": result["status"], "covered": result.get("shadow_covered_rows"),
                      "direct": result.get("same_row_metrics", {}).get("direct"),
                      "hybrid": result.get("same_row_metrics", {}).get("hybrid"),
                      "output": str(args.output)}))


if __name__ == "__main__":
    main()
