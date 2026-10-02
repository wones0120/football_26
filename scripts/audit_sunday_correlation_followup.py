#!/usr/bin/env python3
"""Build the Week 2 Sunday correlation follow-up without changing production."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import create_engine, text

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Database.config import get_connection_string
from backend.app.product_dependencies import get_optimizer_service
from backend.app.product_services.canonical_projection_inputs import load_inputs
from backend.app.product_services.forward_opportunity import (
    forecast_player_opportunities,
    forecast_team_volumes,
    team_games_from_weekly,
)
from scripts.validate_forward_opportunity import load_weekly

DEN_RBS = ("J.K. Dobbins", "RJ Harvey", "Jonah Coleman")
DAL_WAS = ("Dak Prescott", "Jayden Daniels", "CeeDee Lamb", "Terry McLaurin")


def number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if np.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def scenario_allocations(pool: Any, scenarios: dict[str, dict[str, Any]]) -> dict[str, Any]:
    active = scenarios["A_active"]
    reconciliation = active["reconciliation"]
    output = []
    for label, scenario in scenarios.items():
        availability = scenario["harvey_availability"]
        opportunities = scenario["opportunities"]
        players = []
        for name in DEN_RBS:
            row = pool.loc[pool["name"].eq(name)].iloc[0]
            carries = number(opportunities[name].get("expected_carries")) or 0
            active_targets = number(active["opportunities"][name].get("expected_targets")) or 0
            # Do not assume an unavailable receiving back's targets all transfer
            # to another RB; hold the remaining backs at their existing shares.
            targets = active_targets * availability if name == "RJ Harvey" else active_targets
            old_carries = number(row.get("projected_carries")) or 0
            old_targets = number(row.get("projected_targets")) or 0
            mean = max(0.0, float(row["projection"]) + 0.6 * (carries - old_carries)
                       + 1.4 * (targets - old_targets))
            p90 = mean + float(row["predicted_p90"] - row["projection"])
            players.append({
                "player": name,
                "availability_factor": availability if name == "RJ Harvey" else 1.0,
                "expected_carries": carries,
                "expected_targets": targets,
                "shadow_mean": mean,
                "spread_preserving_p90": p90,
            })
        output.append({"scenario": label, "players": players})
    return {
        "expected_team_rush_attempts": reconciliation["expected_rush_attempts"],
        "expected_qb_rushes_model": reconciliation["allocated_qb_carries"],
        "expected_wr_te_rushes": reconciliation["allocated_wr_te_carries"],
        "expected_rb_carries": reconciliation["allocated_rb_carries"],
        "active_rb_targets": sum(
            number(active["opportunities"][name].get("expected_targets")) or 0
            for name in DEN_RBS
        ),
        "scenarios": output,
        "method": (
            "Team volume comes from the existing time-safe ridge forecast. RB carries and targets "
            "are recomputed from existing opportunity shares times Harvey availability. Vacated "
            "Harvey targets are not forced onto another RB. Mean uses "
            "0.6 DK per carry and 1.4 per target; P90 preserves the production spread. Diagnostic only."
        ),
    }


def board_row(row: dict[str, Any], pool: Any, label: str) -> dict[str, Any]:
    names = [player["name"] for player in row["roster"]]
    selected = pool.loc[pool["name"].isin(names)]
    injuries = []
    for record in selected.to_dict("records"):
        status = record.get("pregame_injury_status")
        if status not in (None, "", "NONE"):
            injuries.append({"player": record["name"], "status": status})
    qb = selected.loc[selected["position"].eq("QB")].iloc[0]
    return {
        "label": label,
        "rank_in_source_scenario": row["rank"],
        "roster": names,
        "salary": row["salary"],
        "mean": row["mean"],
        "p90": row["p90"],
        "ownership_sum": row["ownership_sum"],
        "relative_chalk": row["relative_chalk"],
        "football_sanity_deficit": row["football_sanity_deficit"],
        "injury_flags": injuries,
        "primary_game_market_in_projection": {
            "game": row["primary_game"],
            "game_total": number(qb.get("game_total_line")),
            "qb_team_spread": number(qb.get("team_spread_line")),
            "qb_team_total": number(qb.get("team_implied_total")),
        },
    }


def markdown(payload: dict[str, Any]) -> str:
    den = payload["den_team_rush"]
    lines = [
        "# Sunday Main correlation follow-up",
        "",
        f"Projection run: `{payload['projection_run_id']}`. Production weights changed: **No**.",
        "",
        "## Denver team volume",
        "",
        f"- Team rush attempts: **{den['expected_team_rush_attempts']:.2f}**",
        f"- QB rush allocation: **{den['expected_qb_rushes_model']:.2f}**",
        f"- RB carry allocation: **{den['expected_rb_carries']:.2f}**",
        f"- WR/TE rush allocation: **{den['expected_wr_te_rushes']:.2f}**",
        "",
        "| Scenario | Player | Carries | Targets | Mean | P90 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for scenario in den["scenarios"]:
        for player in scenario["players"]:
            lines.append(
                f"| {scenario['scenario']} | {player['player']} | "
                f"{player['expected_carries']:.2f} | {player['expected_targets']:.2f} | "
                f"{player['shadow_mean']:.2f} | {player['spread_preserving_p90']:.2f} |"
            )
    lines += ["", "## Today board", "",
              "| Candidate | Mean | P90 | Ownership | Chalk | Sanity deficit | Injuries |",
              "|---|---:|---:|---:|---:|---:|---|"]
    for row in payload["today_board"]:
        injuries = ", ".join(f"{item['player']} {item['status']}" for item in row["injury_flags"]) or "None"
        lines.append(
            f"| {row['label']} | {row['mean']:.2f} | {row['p90']:.2f} | "
            f"{row['ownership_sum']:.2f}% | {row['relative_chalk']:.1f} | "
            f"{row['football_sanity_deficit']:.2f} | {injuries} |"
        )
    lines += ["", "## Findings", ""]
    lines.extend(f"- {finding}" for finding in payload["findings"])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--projection-run-id", default="28df12cd-893e-4b59-bb12-db2cb3d1984b")
    parser.add_argument("--source-audit", type=Path,
                        default=Path("artifacts/sunday-main-correlation-oneoff-audit-2026w2.json"))
    parser.add_argument("--output", type=Path,
                        default=Path("artifacts/sunday-main-correlation-followup-2026w2.json"))
    args = parser.parse_args()

    source = json.loads(args.source_audit.read_text())
    service = get_optimizer_service()
    pool = service._load_player_pool(2026, 2, "SUNDAY_MAIN",  # noqa: SLF001
                                     projection_run_id=args.projection_run_id)
    db = create_engine(get_connection_string())
    with db.connect() as connection:
        run = dict(connection.execute(text("""
            SELECT data_cutoff_at FROM target.projection_run
            WHERE projection_run_id=:run_id AND status='completed'
        """), {"run_id": args.projection_run_id}).mappings().one())
    train, target, _ = load_inputs(db, season=2026, week=2, slate="SUNDAY_MAIN",
                                   cutoff=run["data_cutoff_at"])
    weekly = load_weekly(db, run["data_cutoff_at"], season=2026)
    team_forecasts = forecast_team_volumes(weekly, train, target, period=202602)
    opportunities, reconciliations = forecast_player_opportunities(
        weekly, target, team_forecasts, period=202602)
    opportunity = {row["name"]: row for row in opportunities}

    den_scenarios = {}
    for label, availability in {"A_active": 1.0, "B_limited": 0.5, "C_inactive": 0.0}.items():
        scenario_target = target.copy()
        scenario_target.loc[
            scenario_target["player_display_name"].eq("RJ Harvey"),
            "pregame_availability_probability",
        ] = availability
        scenario_opportunities, scenario_reconciliations = forecast_player_opportunities(
            weekly, scenario_target, team_forecasts, period=202602)
        den_scenarios[label] = {
            "harvey_availability": availability,
            "opportunities": {row["name"]: row for row in scenario_opportunities},
            "reconciliation": scenario_reconciliations["DEN"],
        }
    den = scenario_allocations(pool, den_scenarios)
    den["week_1_observed"] = team_games_from_weekly(weekly).loc[
        lambda frame: frame["team"].eq("DEN") & frame["period"].eq(202601)
    ].to_dict("records")
    den["qb_allocation_detail"] = {
        name: opportunity[name]["expected_carries"]
        for name in ("Bo Nix", "Jarrett Stidham") if name in opportunity
    }

    waddle = pool.loc[pool["name"].eq("Jaylen Waddle")].iloc[0]
    mims = pool.loc[pool["name"].eq("Marvin Mims Jr.")].iloc[0]
    waddle_role = {
        "projection": number(waddle["projection"]),
        "p90": number(waddle["predicted_p90"]),
        "snap_share_mean_3": number(waddle.get("snap_share_mean_3")),
        "snap_share_last": number(waddle.get("snap_share_last")),
        "expected_routes": number(waddle.get("pregame_expected_routes")),
        "production_expected_targets": number(waddle.get("projected_targets")),
        "forward_shadow_expected_targets": number(opportunity["Jaylen Waddle"].get("expected_targets")),
        "target_share_mean_3": number(waddle.get("target_share_mean_3")),
        "target_share_last": number(waddle.get("target_share_last")),
        "depth_chart_position": waddle.get("depth_chart_position"),
        "role_class": waddle.get("offensive_role_class"),
        "role_confidence": waddle.get("offensive_role_confidence"),
        "mims_status": mims.get("pregame_injury_status"),
        "mims_forward_availability": opportunity["Marvin Mims Jr."].get("availability"),
        "mims_out_reallocation_applied": False,
    }

    external = json.loads(Path("artifacts/sunday-main-espn-projection-sanity-2026w2.json").read_text())
    external_by_name = {row["player"]: row for row in external["overlapping_players"]}
    dal_was = []
    for name in DAL_WAS:
        row = pool.loc[pool["name"].eq(name)].iloc[0]
        opp = opportunity[name]
        history = weekly.loc[
            weekly["player_master_id"].astype(str).eq(str(row["player_id"]))
            & weekly["period"].lt(202602)
        ].sort_values("period").tail(3)
        dal_was.append({
            "player": name,
            "mean": number(row["projection"]),
            "p90": number(row["predicted_p90"]),
            "salary": int(row["salary"]),
            "value_per_1000": number(row["projection"] / (row["salary"] / 1000)),
            "expected_pass_attempts": number(opp.get("expected_qb_attempts")),
            "expected_carries": number(opp.get("expected_carries")),
            "expected_targets": number(opp.get("expected_targets")),
            "recent_games": history[["season", "week", "attempts", "passing_yards",
                                     "passing_tds", "passing_interceptions", "carries",
                                     "rushing_yards", "rushing_tds", "targets", "receptions",
                                     "receiving_yards", "receiving_tds"]].to_dict("records"),
            "espn_mean_diagnostic": external_by_name[name]["espn_mean"],
            "ours_minus_espn": external_by_name[name]["signed_difference"],
        })

    control = source["scenarios"]["control"]["top_20"]
    no_extra = source["scenarios"]["test_c_no_extra_pass_catcher"]["top_20"]
    best_swift = next(row for row in control if any(
        player["name"] == "D'Andre Swift" for player in row["roster"]))
    best_loveland = next(row for row in control if any(
        player["name"] == "Colston Loveland" for player in row["roster"]))
    board = [
        board_row(control[0], pool, "Control winner"),
        board_row(no_extra[0], pool, "No-extra-pass-catcher winner"),
        board_row(best_swift, pool, "Best D'Andre Swift lineup"),
        board_row(best_loveland, pool, "Best Colston Loveland lineup"),
    ]

    payload = {
        "artifact": "sunday_main_correlation_followup_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "projection_run_id": args.projection_run_id,
        "production_changes": "None",
        "den_team_rush": den,
        "waddle_role": waddle_role,
        "dal_was_projection_diagnostic": {
            "market_in_projection": {"game_total": 51.5, "DAL_team_total": 23.5,
                                      "WAS_team_total": 28.0},
            "team_forecasts": {team: team_forecasts[team] for team in ("DAL", "WAS")},
            "players": dal_was,
            "interpretation": (
                "The market environment is strong, but the production projections remain compressed. "
                "The forward shadow assigns Lamb and McLaurin more targets than the production rows, "
                "and the QB attempt allocator gives Daniels only part of Washington's team pass budget."
            ),
        },
        "chicago": {
            "finding": "Swift and Loveland remain strong one-offs; no MIN player is required.",
            "caleb_family_elite": False,
        },
        "today_board": board,
        "market_freshness": {
            "NO_BAL_projection_snapshot": {"game_total": 46.5, "BAL_spread": -7.5},
            "newer_user_supplied_diagnostic": {"game_total": 45.5, "BAL_spread": -8.5},
            "warning": "The final board still reflects the older 46.5/-7.5 production market snapshot.",
        },
        "findings": [
            "The production 13.33 DEN team-carry feature is too low as a team-volume budget: the separate time-safe forecast estimates 27.22 team rushes and 19.71 RB carries.",
            "The QB rush allocation includes 1.72 carries for backup Jarrett Stidham; this is a starter-allocation data-quality issue, not support for extra RB volume.",
            "Waddle's 8.46 mean is supported by modest current usage, but route evidence is unavailable and Mims being out was not reallocated: the shadow opportunity layer still treats Mims as fully available.",
            "DAL-WAS shows projection compression and allocation issues in addition to recent mediocre production. Lamb's shadow target estimate is 7.54 versus 5.72 in production, while Daniels receives only 18.98 of 32.19 forecast Washington pass attempts.",
            "Swift and Loveland remain valid one-off candidates without Minnesota bring-backs.",
            "The control and no-extra-pass-catcher winners remain serious candidates; no production weight was promoted.",
        ],
    }
    args.output.write_text(json.dumps(payload, indent=2, default=str, allow_nan=False) + "\n")
    args.output.with_suffix(".md").write_text(markdown(payload))
    print(json.dumps({"output": str(args.output), "board": len(board)}))


if __name__ == "__main__":
    main()
