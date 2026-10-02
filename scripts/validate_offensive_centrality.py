"""Read-only calibration and current-slate football core diagnostics."""
from __future__ import annotations

import argparse
import json
from datetime import UTC
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from sklearn.linear_model import LinearRegression

from Database.config import get_connection_string
from backend.app.product_services.canonical_projection_inputs import load_inputs
from backend.app.product_services.offensive_centrality import (
    FORMULATIONS,
    apply_core_membership,
    attach_walk_forward_fitted,
    calibrate_core_thresholds,
    formulation_metrics,
    historical_prediction_rows,
    score_current_players,
)
from scripts.validate_forward_opportunity import load_weekly

SKILL_POSITIONS = {"RB", "WR", "TE"}
INSPECTION = {
    "DET": ["Jahmyr Gibbs", "Amon-Ra St. Brown"],
    "BUF": ["James Cook", "Khalil Shakir"],
    "DEN": ["Courtland Sutton"],
}


def fit_final(rows: pd.DataFrame) -> LinearRegression:
    training = rows.dropna(
        subset=["receiving_centrality", "rushing_centrality", "actual_overall"]
    )
    features = training[["receiving_centrality", "rushing_centrality"]].copy()
    features["dual"] = features.min(axis=1)
    return LinearRegression(positive=True).fit(features, training["actual_overall"])


def choose(metrics: dict[str, dict]) -> tuple[str, dict[str, float]]:
    def value(formulation: str) -> float:
        row = metrics[formulation]
        values = [
            row.get("overall_spearman", {}).get("mean"), row.get("top_1_recall"),
            row.get("top_2_recall"), row.get("top_3_recall"),
            row.get("dual_threat_top_3_recall"),
        ]
        observed = [item for item in values if item is not None]
        penalty = row.get("false_core_rate") or 0
        return float(np.mean(observed) - 0.25 * penalty) if observed else -1
    ranking = sorted(FORMULATIONS, key=value, reverse=True)
    return ranking[0], {name: value(name) for name in ranking}


def latest_run(engine, projection_run_id: str | None) -> dict:
    where = "AND projection_run_id = :projection_run_id" if projection_run_id else ""
    params = {"projection_run_id": projection_run_id} if projection_run_id else {}
    with engine.connect() as connection:
        row = connection.execute(text(f"""
            SELECT projection_run_id, season, week, slate_id, data_cutoff_at, created_at
            FROM target.projection_run
            WHERE season = 2026 AND week = 2
              AND UPPER(slate_id) = 'SUNDAY_MAIN' AND status = 'completed' {where}
            ORDER BY created_at DESC LIMIT 1
        """), params).mappings().first()
    if not row:
        raise ValueError("No completed Sunday Main projection run was found")
    return dict(row)


def _naive_utc(value):
    return (value.astimezone(UTC).replace(tzinfo=None)
            if getattr(value, "tzinfo", None) is not None else value)


def participation_rows(engine, *, season: int, weeks: list[int], cutoff) -> pd.DataFrame:
    with engine.connect() as connection:
        return pd.read_sql(text("""
            SELECT DISTINCT ON (week, player_master_id, team)
                   week, player_master_id, player_name, team, position,
                   roster_status, participation_status,
                   offense_snap_share, offense_snaps, created_at
            FROM public.curated_player_game_participation
            WHERE season = :season AND week = ANY(:weeks) AND created_at <= :cutoff
            ORDER BY week, player_master_id, team, created_at DESC,
                     curated_player_game_participation_id DESC
        """), connection, params={"season": season, "weeks": weeks,
                                   "cutoff": _naive_utc(cutoff)})


def current_usage_maps(engine, weekly: pd.DataFrame, *, season: int, week: int,
                       cutoff) -> tuple[dict[str, dict], pd.DataFrame]:
    prior_week = week - 1
    usage = weekly.loc[
        weekly["season"].eq(season) & weekly["week"].eq(prior_week)
        & weekly["position"].isin(SKILL_POSITIONS)
        & weekly["player_master_id"].notna()
    ].copy()
    usage["player_master_id"] = usage["player_master_id"].astype(str)
    usage = usage.groupby(["team", "player_master_id", "position"], as_index=False).agg(
        targets=("targets", "sum"), carries=("carries", "sum"))
    target_totals = usage.groupby("team")["targets"].transform("sum")
    carry_totals = usage.groupby("team")["carries"].transform("sum")
    usage["target_share"] = np.where(target_totals > 0, usage["targets"] / target_totals, 0.0)
    usage["carry_share"] = np.where(carry_totals > 0, usage["carries"] / carry_totals, 0.0)
    participation = participation_rows(engine, season=season, weeks=[prior_week, week], cutoff=cutoff)
    prior = participation.loc[participation["week"].eq(prior_week)]
    current = participation.loc[participation["week"].eq(week)]
    prior_by_id = {str(row["player_master_id"]): row for row in prior.to_dict("records")}
    current_by_id = {str(row["player_master_id"]): row for row in current.to_dict("records")}
    usage_by_id = {str(row["player_master_id"]): row for row in usage.to_dict("records")}
    evidence = {}
    for player_id in set(usage_by_id) | set(prior_by_id) | set(current_by_id):
        usage_row, snap_row, active_row = (usage_by_id.get(player_id, {}),
                                           prior_by_id.get(player_id, {}),
                                           current_by_id.get(player_id, {}))
        evidence[player_id] = {
            "player_name": active_row.get("player_name") or snap_row.get("player_name"),
            "week_1_targets": usage_row.get("targets"),
            "week_1_target_share": usage_row.get("target_share"),
            "week_1_carries": usage_row.get("carries"),
            "week_1_carry_share": usage_row.get("carry_share"),
            "week_1_snap_share": snap_row.get("offense_snap_share"),
            "week_2_roster_status": active_row.get("roster_status"),
            "week_2_participation_status": active_row.get("participation_status"),
        }
    return evidence, usage


def attach_current_evidence(rows: list[dict], evidence: dict[str, dict]) -> list[dict]:
    output = []
    for source in rows:
        row, current = dict(source), dict(evidence.get(str(source["player_id"]), {}))
        usage = current.get("week_1_targets") is not None
        snap = current.get("week_1_snap_share") is not None
        active = current.get("week_2_roster_status") is not None
        confidence = ("high_current" if usage and snap and active else
                      "medium_current_missing_snap" if usage and active else
                      "low_current_missing_status" if usage else "stale_2025_primary")
        row.update(current_usage=current, current_evidence_confidence=confidence,
                   relies_mainly_on_2025=not usage)
        output.append(row)
    return output


def coverage_by_team(rows: list[dict]) -> dict[str, dict]:
    output = {}
    fields = {"targets": "week_1_targets", "target_share": "week_1_target_share",
              "carries": "week_1_carries", "carry_share": "week_1_carry_share",
              "snap_share": "week_1_snap_share", "active_status": "week_2_roster_status"}
    for team in sorted({row["team"] for row in rows}):
        members = [row for row in rows if row["team"] == team]
        counts = {name: sum(row["current_usage"].get(field) is not None for row in members)
                  for name, field in fields.items()}
        stale = [row["player"] for row in members if row["relies_mainly_on_2025"]]
        output[team] = {"skill_players": len(members), "coverage_counts": counts,
                        "stale_2025_primary_players": stale,
                        "current_usage_complete": not stale and all(
                            count == len(members) for count in counts.values())}
    return output


def current_week_snapshot_rows(usage: pd.DataFrame, evidence: dict[str, dict],
                               fitted, calibration: dict) -> list[dict]:
    frame = usage.rename(columns={"player_master_id": "player_id",
                                  "target_share": "target_share_mean_3",
                                  "carry_share": "carry_share_mean_3"}).copy()
    frame["player_display_name"] = frame["player_id"].map(
        {player_id: row.get("player_name") for player_id, row in evidence.items()})
    frame["player_display_name"] = frame["player_display_name"].fillna(frame["player_id"])
    frame["recent_team"] = frame["team"]
    frame["snap_share_mean_3"] = frame["player_id"].map(
        {player_id: row.get("week_1_snap_share") for player_id, row in evidence.items()})
    frame["snap_share_mean_3_available"] = frame["snap_share_mean_3"].notna()
    frame["player_games_history"] = 1
    return apply_core_membership(
        score_current_players(frame, "monotonic_fitted", fitted), calibration)


def inspection_examples(rows: list[dict]) -> dict[str, list[dict]]:
    result = {}
    for team, names in INSPECTION.items():
        team_rows = [row for row in rows if row["team"] == team]
        by_name = {str(row["player"]): row for row in team_rows}
        result[team] = []
        for name in names:
            row = by_name.get(name)
            if row is None:
                matches = [item for item in team_rows
                           if str(item["player"]).lower().startswith(name.lower())]
                row = matches[0] if len(matches) == 1 else None
            result[team].append(dict(row) if row else
                                {"player": name, "status": "not resolved in Week 1 usage"})
    return result


def team_tables(rows: list[dict]) -> dict[str, list[dict]]:
    output: dict[str, list[dict]] = {}
    for row in rows:
        output.setdefault(row["team"], []).append(row)
    return output


def _fmt(value: Any) -> str:
    return ("Unavailable" if value is None or
            (isinstance(value, float) and not np.isfinite(value)) else f"{float(value):.3f}")


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def render_markdown(payload: dict) -> str:
    calibration = payload["core_calibration"]
    lines = ["# Sunday Main football core validation", "",
        "This report changes neither fantasy projections nor optimizer behavior. Core membership is football-opportunity evidence prepared for shadow testing.", "",
        "## Historically calibrated core rules", "",
        "| Dimension | Selected rule | Top-1 recall | Top-2 recall | Precision | False-core rate |",
        "|---|---|---:|---:|---:|---:|"]
    for dimension in ("receiving", "rushing", "overall"):
        row = calibration[dimension]["selected"]
        lines.append(f"| {dimension} | score ≥ {row['threshold']:.2f}, team rank ≤ {row['rank_limit']} | {row['top_1_recall']:.1%} | {row['top_2_recall']:.1%} | {row['precision_vs_top_2']:.1%} | {row['false_core_rate']:.1%} |")
    dual = calibration["dual_threat"]["selected"]
    lines += ["", f"Dual threat: receiving ≥ {dual['receiving_threshold']:.2f} and rushing ≥ {dual['rushing_threshold']:.2f}; precision {dual['precision']:.1%}, recall {dual['recall']:.1%}, false-core rate {dual['false_core_rate']:.1%}.", "",
        "`overall_core` is the union of receiving core, rushing core, dual threat core, and the separately calibrated combined-score core.", "", "### Precision/recall alternatives", ""]
    for dimension in ("receiving", "rushing"):
        lines += [f"#### {dimension.title()}", "",
            "| Score | Rank cap | Top-1 | Top-2 | Precision | False core | Cores/team |",
            "|---:|---:|---:|---:|---:|---:|---:|"]
        for row in calibration[dimension]["candidates"][:8]:
            lines.append(f"| {row['threshold']:.2f} | {row['rank_limit']} | {row['top_1_recall']:.1%} | {row['top_2_recall']:.1%} | {row['precision_vs_top_2']:.1%} | {row['false_core_rate']:.1%} | {row['cores_per_team']:.2f} |")
        lines.append("")
    lines += ["## 2026 Week 1 evidence coverage", "",
        "| Team | Skill players | Targets | Target share | Carries | Carry share | Snap share | Active status | Mainly 2025 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|"]
    for team, row in payload["current_usage_coverage"].items():
        counts, total = row["coverage_counts"], row["skill_players"]
        stale = ", ".join(row["stale_2025_primary_players"]) or "None"
        lines.append(f"| {team} | {total} | {counts['targets']}/{total} | {counts['target_share']}/{total} | {counts['carries']}/{total} | {counts['carry_share']}/{total} | {counts['snap_share']}/{total} | {counts['active_status']}/{total} | {stale} |")
    lines += ["", "## Sunday Main core set", "",
        "| Team | Player | Pos | Receiving | Rushing | Overall | Rec core | Rush core | Dual | Overall core | Classification | Confidence |",
        "|---|---|---|---:|---:|---:|---|---|---|---|---|---|"]
    for team, rows in payload["sunday_core_by_team"].items():
        for row in rows:
            yn = lambda value: "Y" if value else "N"
            lines.append(f"| {team} | {row['player']} | {row['position']} | {_fmt(row['receiving_centrality'])} | {_fmt(row['rushing_centrality'])} | {_fmt(row['overall_centrality'])} | {yn(row['receiving_core'])} | {yn(row['rushing_core'])} | {yn(row['dual_threat_core'])} | {yn(row['overall_core'])} | {row['football_classification']} | {row['current_evidence_confidence']} |")
    lines += ["", "## Explicit sanity checks", ""]
    for team, rows in payload["sanity_checks"].items():
        lines += [f"### {team}", ""]
        for row in rows:
            if row.get("status"):
                lines.append(f"- **{row['player']}**: {row['status']}.")
            else:
                lines.append(f"- **{row['player']}**: receiving/rushing/overall {_fmt(row['receiving_centrality'])}/{_fmt(row['rushing_centrality'])}/{_fmt(row['overall_centrality'])}; receiving core {'Y' if row['receiving_core'] else 'N'}, rushing core {'Y' if row['rushing_core'] else 'N'}, dual {'Y' if row['dual_threat_core'] else 'N'}; **{row['football_classification']}**.")
        lines.append("")
    lines += ["## Shadow handoff", "", f"Optimizer input: `{payload['optimizer_shadow_artifact']}`", "",
        "The artifact contains canonical player IDs, the three centrality dimensions, independent core flags, the union flag, classification, confidence, and Week 1 evidence. It contains no optimizer weight and does not alter lineup generation.", ""]
    return "\n".join(lines)


def shadow_rows(rows: list[dict]) -> list[dict]:
    fields = ("player_id", "player", "team", "position", "receiving_centrality",
        "rushing_centrality", "overall_centrality", "receiving_rank", "rushing_rank",
        "overall_rank", "receiving_core", "rushing_core", "dual_threat_core",
        "overall_score_core", "overall_core", "football_classification",
        "current_evidence_confidence", "relies_mainly_on_2025", "current_usage")
    return [{field: row.get(field) for field in fields} for row in rows]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--projection-run-id", default="")
    parser.add_argument("--output", type=Path,
                        default=Path("artifacts/sunday-football-core-2026w2.json"))
    args = parser.parse_args()
    engine = create_engine(get_connection_string())
    run = latest_run(engine, args.projection_run_id or None)
    train, target, metadata = load_inputs(engine, season=run["season"], week=run["week"],
                                          slate=run["slate_id"], cutoff=run["data_cutoff_at"])
    weekly = load_weekly(engine, run["data_cutoff_at"], season=run["season"])
    historical = attach_walk_forward_fitted(historical_prediction_rows(weekly))
    common = historical.dropna(subset=["monotonic_fitted"]).copy()
    metrics = {name: formulation_metrics(common, name) for name in FORMULATIONS}
    best, selection_scores = choose(metrics)
    fitted = fit_final(historical)
    calibration = calibrate_core_thresholds(common)
    scored = apply_core_membership(
        score_current_players(target, best, fitted if best == "monotonic_fitted" else None),
        calibration)
    evidence, usage = current_usage_maps(engine, weekly, season=int(run["season"]),
                                         week=int(run["week"]), cutoff=run["data_cutoff_at"])
    scored = attach_current_evidence(scored, evidence)
    sunday_teams = set(target["recent_team"].dropna().astype(str))
    sunday_rows = [row for row in scored if row["team"] in sunday_teams]
    coverage = coverage_by_team(sunday_rows)
    week_snapshot = attach_current_evidence(
        current_week_snapshot_rows(usage, evidence, fitted, calibration), evidence
    )
    # Sunday rows and the optimizer handoff share the saved pregame centrality snapshot.
    # Use the Week 1-only view solely for teams absent from Sunday Main (DET/BUF).
    sanity_source = [row for row in week_snapshot if row["team"] not in sunday_teams]
    sanity_source.extend(sunday_rows)
    sanity = inspection_examples(sanity_source)
    shadow_path = args.output.with_name(args.output.stem + "-optimizer-shadow.json")
    det_buf_shadow_path = args.output.with_name(
        args.output.stem.replace("sunday", "det-buf") + "-optimizer-shadow.json"
    )
    shadow_payload = {"contract": "football_core_shadow_v1",
        "projection_run_id": run["projection_run_id"], "data_cutoff_at": run["data_cutoff_at"],
        "centrality_formulation": best, "calibration": calibration,
        "players": shadow_rows(sunday_rows), "projection_changed": False,
        "optimizer_changed": False}
    shadow_path.write_text(json.dumps(_json_safe(shadow_payload), indent=2,
                                      default=str, allow_nan=False) + "\n")
    det_buf_rows = [row for row in week_snapshot if row["team"] in {"DET", "BUF"}]
    det_buf_shadow_payload = {**shadow_payload,
        "projection_run_id": None,
        "source_projection_run_id": run["projection_run_id"],
        "slate": "THURSDAY_NIGHT", "players": shadow_rows(det_buf_rows)}
    det_buf_shadow_path.write_text(json.dumps(_json_safe(det_buf_shadow_payload), indent=2,
                                              default=str, allow_nan=False) + "\n")
    payload = {"historical_validation": {"rows": len(common),
            "period_range": [int(common["period"].min()), int(common["period"].max())],
            "formulations": metrics, "best_formulation": best,
            "selection_scores": selection_scores,
            "fitted_model": {"coefficients": dict(zip(["receiving", "rushing", "dual"], fitted.coef_.tolist())),
                             "intercept": float(fitted.intercept_), "positive_coefficients": True}},
        "core_calibration": calibration, "current_usage_coverage": coverage,
        "sunday_core_by_team": team_tables(sunday_rows), "sanity_checks": sanity,
        "optimizer_shadow_artifact": str(shadow_path),
        "det_buf_optimizer_shadow_artifact": str(det_buf_shadow_path),
        "provenance": {"projection_run_id": run["projection_run_id"],
            "data_cutoff": str(run["data_cutoff_at"]),
            "current_2026_weekly_rows": int(weekly["season"].eq(2026).sum()),
            "current_week_1_rows": int((weekly["season"].eq(2026) & weekly["week"].eq(1)).sum()),
            "production_projection_changed": False, "optimizer_changed": False}}
    args.output.write_text(json.dumps(_json_safe(payload), indent=2,
                                      default=str, allow_nan=False) + "\n")
    args.output.with_suffix(".md").write_text(render_markdown(payload) + "\n")
    print(json.dumps({"best": best, "historical_rows": len(common),
        "week_1_rows": payload["provenance"]["current_week_1_rows"],
        "sunday_players": len(sunday_rows), "teams": len(coverage),
        "stale_players": sum(len(row["stale_2025_primary_players"]) for row in coverage.values()),
        "output": str(args.output), "shadow": str(shadow_path)}))


if __name__ == "__main__":
    main()
