#!/usr/bin/env python3
"""Create a pre-lock Sunday Main readiness audit from a complete Classic pool."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from math import exp, log
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd
from sqlalchemy import text

from backend.app.db import engine
from backend.app.product_dependencies import get_optimizer_service
from backend.app.product_services.football_sanity_deficit import prepare_deficit_candidates
from backend.app.product_services.optimizer import _json_safe

SKILL = {"RB", "WR", "TE"}
INACTIVE = {"OUT", "O", "IR", "INA", "INACTIVE", "PUP", "SUS", "RES", "PS", "PRACTICE_SQUAD"}


def _report(payload: Any) -> dict:
    if isinstance(payload, dict):
        if isinstance(payload.get("report"), dict) and "all_candidates" in payload["report"]:
            return payload["report"]
        if isinstance(payload.get("classic_small_field_report"), dict):
            return payload["classic_small_field_report"]
        for value in payload.values():
            try:
                return _report(value)
            except LookupError:
                pass
    elif isinstance(payload, list):
        for value in payload:
            try:
                return _report(value)
            except LookupError:
                pass
    raise LookupError("classic_small_field_report not found")


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _distribution(values: Iterable[float]) -> dict[str, float | int | None]:
    rows = np.asarray([float(value) for value in values if _number(value) is not None])
    if not len(rows):
        return {"count": 0, "minimum": None, "p25": None, "median": None,
                "mean": None, "p75": None, "maximum": None}
    return {"count": len(rows), "minimum": float(rows.min()),
            "p25": float(np.quantile(rows, .25)), "median": float(np.median(rows)),
            "mean": float(rows.mean()), "p75": float(np.quantile(rows, .75)),
            "maximum": float(rows.max())}


def _lineup_ownership(candidate: Mapping[str, Any], pool_by_id: Mapping[str, Mapping[str, Any]]) -> dict:
    players = []
    for roster in candidate["roster"]:
        source = pool_by_id.get(str(roster["player_id"]), {})
        ownership = _number(source.get("ownership"))
        players.append({"player_id": str(roster["player_id"]), "name": roster["name"],
                        "team": roster["team"], "position": roster["position"],
                        "ownership": ownership})
    known = [row["ownership"] for row in players if row["ownership"] is not None]
    complete = len(known) == len(players)
    log_proxy = sum(log(max(.01, value) / 100.0) for value in known) if complete else None
    qb = next((row for row in candidate["roster"] if row["position"] == "QB"), None)
    stack_ids = ({str(qb["player_id"])} | {
        str(row["player_id"]) for row in candidate["roster"]
        if qb and row["team"] == qb["team"] and row["position"] in SKILL
    }) if qb else set()
    return {"coverage": len(known), "roster_size": len(players), "complete": complete,
            "sum": sum(known) if complete else None, "log_proxy": log_proxy,
            "product_proxy": exp(log_proxy) if log_proxy is not None else None,
            "stack_sum": sum(row["ownership"] for row in players
                             if row["player_id"] in stack_ids and row["ownership"] is not None)
                         if complete else None,
            "highest_owned": sorted(players, key=lambda row: -(row["ownership"] or -1))[:3],
            "low_owned": sorted((row for row in players if row["ownership"] is not None and row["ownership"] < 5),
                                key=lambda row: row["ownership"]),
            "players": players}


def _ownership_metadata(run_ids: list[str]) -> list[dict]:
    if not run_ids:
        return []
    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT ownership_run_id, model_id, season, week, slate_id, created_at,
                   data_cutoff_at, training_rows, params_json, metrics_json, status
            FROM target.ownership_model_run
            WHERE ownership_run_id = ANY(:run_ids)
            ORDER BY created_at DESC
        """), {"run_ids": run_ids}).mappings().all()
    return [dict(row) for row in rows]


def _latest_ownership_diagnostic() -> tuple[dict[str, float], dict[str, Any]]:
    with engine.connect() as connection:
        run = connection.execute(text("""
            SELECT ownership_run_id, model_id, data_cutoff_at, metrics_json
            FROM target.ownership_model_run
            WHERE season = 2026 AND week = 2
              AND UPPER(slate_id) = 'SUNDAY_MAIN' AND status = 'completed'
            ORDER BY created_at DESC
            LIMIT 1
        """)).mappings().first()
        if run is None:
            return {}, {}
        rows = connection.execute(text("""
            SELECT player_id, projected_ownership
            FROM target.ownership_projection
            WHERE ownership_run_id = :run_id
        """), {"run_id": run["ownership_run_id"]}).mappings().all()
    return (
        {str(row["player_id"]): float(row["projected_ownership"]) for row in rows},
        dict(run),
    )


def _status_flags(pool: Mapping[str, Any], core: Mapping[str, Any]) -> list[str]:
    flags = []
    statuses = [str(pool.get(key) or "").strip().upper()
                for key in ("roster_status", "player_status", "pregame_injury_status", "injury_status")]
    if any(status in INACTIVE or "PRACTICE" in status for status in statuses):
        flags.append("inactive_or_roster_uncertain")
    usage = core.get("current_usage") or {}
    if _number(usage.get("week_1_snap_share")) == 0:
        flags.append("zero_week_1_snap_share")
    if core.get("current_evidence_confidence") != "high_current":
        flags.append("stale_or_unknown_role")
    for field in ("snap_share_trend", "target_share_trend", "rush_share_trend"):
        value = _number(pool.get(field))
        if value is not None and abs(value) >= .15:
            flags.append(f"material_{field}")
    if pool.get("pregame_newly_assigned_role") is True:
        flags.append("newly_assigned_role")
    if pool.get("pregame_injury_created_opportunity") is True:
        flags.append("injury_created_opportunity")
    return flags


def _role_counts(candidate: Mapping[str, Any], core_by_id: Mapping[str, Mapping[str, Any]]) -> dict:
    counts = Counter()
    for player in candidate["roster"]:
        if player["position"] not in SKILL:
            continue
        core = core_by_id.get(str(player["player_id"]), {})
        classification = core.get("football_classification") or "stale/unknown"
        if core.get("current_evidence_confidence") != "high_current":
            counts["stale_unknown"] += 1
        elif classification == "offensive centerpiece":
            counts["offensive_centerpiece"] += 1
            counts["core"] += 1
        elif classification.startswith("core "):
            counts["core"] += 1
        elif classification == "meaningful secondary":
            counts["meaningful_secondary"] += 1
        elif classification == "complementary":
            counts["complementary"] += 1
        else:
            counts["peripheral"] += 1
    return dict(counts)


def _candidate_summary(report: Mapping[str, Any], core_by_id: Mapping[str, Mapping[str, Any]],
                       pool_by_id: Mapping[str, Mapping[str, Any]]) -> dict:
    candidates = report["all_candidates"]
    prepared, deficit_distribution = prepare_deficit_candidates(
        [{**row, "roster": row["roster"]} for row in candidates],
        core_by_id=core_by_id,
        player_pool=[{"player_id": player_id, "name": row.get("name"),
                      "team": row.get("player_team"), "position": row.get("position"),
                      "salary": row.get("salary"), "projection": row.get("projection"),
                      "p90": row.get("p90")} for player_id, row in pool_by_id.items()],
    )
    player = Counter(item["name"] for row in candidates for item in row["roster"])
    team = Counter(item["team"] for row in candidates for item in row["roster"])
    games = Counter(game for row in candidates for game in row.get("games_represented", []))
    ownership = [_lineup_ownership(row, pool_by_id) for row in candidates]
    complete_logs = sorted(row["log_proxy"] for row in ownership if row["log_proxy"] is not None)
    for row in ownership:
        row["relative_chalk"] = (
            100 * complete_logs.index(row["log_proxy"]) / max(1, len(complete_logs) - 1)
            if row["log_proxy"] is not None else None
        )
    return {
        "candidate_count": len(candidates),
        "qb_distribution": dict(Counter(row["qb"]["name"] for row in candidates)),
        "stack_distribution": dict(Counter(row["stack"]["type"] for row in candidates)),
        "primary_game_distribution": dict(Counter(row["primary_game"] for row in candidates)),
        "player_exposure": dict(player.most_common()), "team_exposure": dict(team.most_common()),
        "game_exposure": dict(games.most_common()),
        "salary_distribution": _distribution(row["salary"] for row in candidates),
        "mean_distribution": _distribution(row["mean"] for row in candidates),
        "p90_distribution": _distribution(row["p90"] for row in candidates),
        "football_sanity_deficit_distribution": deficit_distribution,
        "stale_evidence_distribution": _distribution(
            row["sanity"]["stale_count"] for row in prepared
        ),
        "deficient_candidate_count": sum(
            row["sanity"]["total_football_sanity_deficit"] > 0 for row in prepared
        ),
        "ownership_complete_candidates": sum(row["complete"] for row in ownership),
        "ownership": ownership,
        "top_20_role_mix": [
            {"rank": row["rank"], **_role_counts(row, core_by_id)}
            for row in candidates[:20]
        ],
    }


def _selected_explanation(report: Mapping[str, Any], core_by_id: Mapping[str, Mapping[str, Any]],
                          pool_by_id: Mapping[str, Mapping[str, Any]],
                          pool_summary: Mapping[str, Any]) -> dict:
    candidates = report["all_candidates"]
    winner = candidates[0]
    ownership = pool_summary["ownership"][0]
    roster = []
    qb = winner["qb"]
    same_team_dst = {row["team"] for row in winner["roster"] if row["position"] == "DST"}
    for player, owner in zip(winner["roster"], ownership["players"]):
        player_id = str(player["player_id"])
        source = pool_by_id.get(player_id, {})
        core = core_by_id.get(player_id, {})
        usage = core.get("current_usage") or {}
        if player["position"] == "QB":
            purpose = f"Quarterback anchor for {winner['stack']['type']}"
        elif player["team"] == qb["team"] and player["position"] in SKILL:
            purpose = "Same-team quarterback stack partner"
        elif player["position"] == "RB" and player["team"] in same_team_dst:
            purpose = "Running back paired with same-team defense"
        elif core.get("overall_core"):
            purpose = "Core offensive role plus projection/salary fit"
        else:
            purpose = "Projection, salary, and whole-lineup construction fit"
        roster.append({**player, "mean": _number(source.get("projection")),
                       "p90": _number(source.get("p90")), "ownership": owner["ownership"],
                       "role_classification": core.get("football_classification"),
                       "role_confidence": core.get("current_evidence_confidence"),
                       "week_1_target_share": usage.get("week_1_target_share"),
                       "week_1_carry_share": usage.get("week_1_carry_share"),
                       "purpose": purpose})
    competitors = []
    for index, candidate in enumerate(candidates[1:6], 1):
        component_delta = {
            key: float(winner["components"].get(key, 0)) - float(candidate["components"].get(key, 0))
            for key in set(winner["components"]) | set(candidate["components"])
        }
        positive = sorted(((key, value) for key, value in component_delta.items() if value > 1e-9),
                          key=lambda item: -item[1])
        negative = sorted(((key, value) for key, value in component_delta.items() if value < -1e-9),
                          key=lambda item: item[1])
        competitors.append({"rank": candidate["rank"],
            "objective_gap": winner["objective_score"] - candidate["objective_score"],
            "mean_delta_winner_minus_candidate": winner["mean"] - candidate["mean"],
            "p90_delta_winner_minus_candidate": winner["p90"] - candidate["p90"],
            "salary_delta_winner_minus_candidate": winner["salary"] - candidate["salary"],
            "component_delta": component_delta,
            "winner_advantages": positive[:3], "competitor_advantages": negative[:3],
            "winner_relative_chalk": ownership["relative_chalk"],
            "competitor_relative_chalk": pool_summary["ownership"][index]["relative_chalk"],
            "lineup": [row["name"] for row in candidate["roster"]]})
    return {"rank": 1, "objective": winner["objective_score"], "mean": winner["mean"],
            "p90": winner["p90"], "salary": winner["salary"], "components": winner["components"],
            "ownership": ownership, "role_mix": _role_counts(winner, core_by_id),
            "players": roster, "closest_competitors": competitors}


def _refresh_delta(current_report: Mapping[str, Any], previous_report: Mapping[str, Any] | None,
                   core_by_id: Mapping[str, Mapping[str, Any]],
                   previous_core_by_id: Mapping[str, Mapping[str, Any]]) -> dict:
    if previous_report is None:
        return {"status": "unavailable", "reason": "no previous optimizer artifact supplied"}
    current_roles = {str(row["player_id"]): row for row in current_report["role_exposure"]}
    previous_roles = {str(row["player_id"]): row for row in previous_report["role_exposure"]}
    common = set(current_roles) & set(previous_roles)
    projection_changes = sorted(({
        "player_id": player_id, "player": current_roles[player_id]["name"],
        "mean_delta": current_roles[player_id]["mean"] - previous_roles[player_id]["mean"],
        "p90_delta": current_roles[player_id]["p90"] - previous_roles[player_id]["p90"],
    } for player_id in common), key=lambda row: -abs(row["mean_delta"]))
    exposure_changes = sorted(({
        "player_id": player_id, "player": current_roles[player_id]["name"],
        "candidate_count_delta": current_roles[player_id]["candidate_count"]
                                 - previous_roles[player_id]["candidate_count"],
    } for player_id in common), key=lambda row: -abs(row["candidate_count_delta"]))
    role_changes = []
    for player_id in set(core_by_id) & set(previous_core_by_id):
        current = core_by_id[player_id]
        previous = previous_core_by_id[player_id]
        if (current.get("football_classification"), current.get("current_evidence_confidence")) != (
                previous.get("football_classification"), previous.get("current_evidence_confidence")):
            role_changes.append({"player": current.get("player"),
                "previous_classification": previous.get("football_classification"),
                "current_classification": current.get("football_classification"),
                "previous_confidence": previous.get("current_evidence_confidence"),
                "current_confidence": current.get("current_evidence_confidence")})
    current_selected = set(current_report["all_candidates"][0]["player_ids"])
    previous_selected = set(previous_report["all_candidates"][0]["player_ids"])
    current_names = {str(player["player_id"]): player["name"]
                     for candidate in current_report["all_candidates"]
                     for player in candidate["roster"]}
    previous_names = {str(player["player_id"]): player["name"]
                      for candidate in previous_report["all_candidates"]
                      for player in candidate["roster"]}
    return {"status": "available",
        "eligible_added": [current_roles[player_id]["name"] for player_id in sorted(set(current_roles) - set(previous_roles))],
        "eligible_removed": [previous_roles[player_id]["name"] for player_id in sorted(set(previous_roles) - set(current_roles))],
        "largest_projection_changes": projection_changes[:20],
        "role_classification_changes": role_changes,
        "largest_candidate_exposure_changes": exposure_changes[:20],
        "selected_lineup_added": [current_names.get(player_id, player_id) for player_id in sorted(current_selected - previous_selected)],
        "selected_lineup_removed": [previous_names.get(player_id, player_id) for player_id in sorted(previous_selected - current_selected)]}


def _fmt(value: Any, digits: int = 2) -> str:
    return "—" if value is None else f"{float(value):.{digits}f}"


def _markdown(payload: Mapping[str, Any]) -> str:
    data, ownership, full, selected, refresh = (payload[key] for key in
        ("data_quality", "ownership", "complete_candidate_pool", "selected_lineup", "refresh_delta"))
    lines = ["# Sunday Main priority readiness audit", "",
        f"Projection: `{payload['projection_run_id']}`; cutoff {payload['projection_cutoff']}.", "",
        "## Current Sunday data quality", "",
        f"- DK-eligible RB/WR/TE: **{data['eligible_skill_players']}**",
        f"- High-current role evidence: **{data['high_current_role_players']}**",
        f"- Stale/unknown role evidence: **{data['stale_unknown_role_players']}**",
        f"- Stale/unknown appearing in 120 candidates: **{len(data['stale_in_candidates'])}**",
        f"- Stale/unknown appearing in top 20: **{len(data['stale_in_top_20'])}**",
        f"- Players facing Denver in candidates: **{len(data['players_facing_denver'])}**", "",
        "### Candidate-impacting eligibility and role flags", "",
        "| player | team | exposure | flags | roster | injury | Week 1 snaps |",
        "|---|---|---:|---|---|---|---:|"]
    for row in data["candidate_role_flags"][:40]:
        lines.append(f"| {row['name']} | {row['team']} | {row['candidate_count']}/120 | "
                     f"{', '.join(row['flags'])} | {row.get('roster_status') or '—'} | "
                     f"{row.get('injury_status') or '—'} | {_fmt(row.get('week_1_snap_share'),3)} |")
    if not data["candidate_role_flags"]:
        lines.append("| none | | | | | | |")
    lines += ["", "## Ownership", "",
        f"Status: **{ownership['status']}**. Source `{ownership.get('model_id')}` run "
        f"`{ownership.get('ownership_run_id')}` at {ownership.get('data_cutoff_at')}. ",
        f"Eligible coverage {ownership['covered_players']}/{ownership['eligible_players']}; "
        f"positive estimates {ownership['positive_players']}. {ownership['assessment']}", "",
        f"Complete candidate ownership diagnostics: {full['ownership_complete_candidates']}/{full['candidate_count']}.", "",
        "## Complete 120-candidate pool", "",
        f"Generated = serialized = analyzed: **{full['candidate_count']}**.",
        f"Deficient candidates: {full['deficient_candidate_count']}; deficit mean "
        f"{_fmt(full['football_sanity_deficit_distribution']['mean'],3)}.",
        f"Salary median/range: ${_fmt(full['salary_distribution']['median'],0)} "
        f"(${_fmt(full['salary_distribution']['minimum'],0)}–${_fmt(full['salary_distribution']['maximum'],0)}).",
        f"Mean median/range: {_fmt(full['mean_distribution']['median'])} "
        f"({_fmt(full['mean_distribution']['minimum'])}–{_fmt(full['mean_distribution']['maximum'])}).",
        f"P90 median/range: {_fmt(full['p90_distribution']['median'])} "
        f"({_fmt(full['p90_distribution']['minimum'])}–{_fmt(full['p90_distribution']['maximum'])}).", "",
        f"QB distribution: {full['qb_distribution']}", "",
        f"Stack distribution: {full['stack_distribution']}", "",
        f"Primary game distribution: {full['primary_game_distribution']}", "",
        "Highest player exposures: " + ", ".join(
            f"{name} {count}/120" for name, count in list(full["player_exposure"].items())[:15]
        ) + ".", "",
        "Highest team player-slot appearances: " + ", ".join(
            f"{name} {count}" for name, count in list(full["team_exposure"].items())[:12]
        ) + ".", "",
        "Highest game appearances: " + ", ".join(
            f"{name} {count}/120" for name, count in list(full["game_exposure"].items())[:10]
        ) + ".", "",
        "## Top-20 opportunity representation", "",
        "| rank | core | centerpiece | meaningful | complementary | peripheral | stale |",
        "|---:|---:|---:|---:|---:|---:|---:|"]
    for row in full["top_20_role_mix"]:
        lines.append(f"| {row['rank']} | {row.get('core',0)} | {row.get('offensive_centerpiece',0)} | "
                     f"{row.get('meaningful_secondary',0)} | {row.get('complementary',0)} | "
                     f"{row.get('peripheral',0)} | {row.get('stale_unknown',0)} |")
    lines += ["", "### High-confidence core players with low candidate representation", ""]
    for row in payload["underrepresented_core"][:20]:
        lines.append(f"- {row['name']} ({row['team']} {row['position']}): {row['candidate_count']}/120; "
                     f"mean {_fmt(row['mean'])}, P90 {_fmt(row['p90'])}, salary ${row['salary']:,}, "
                     f"value rank {row['value_rank']}/{row['position_count']}. {row['diagnosis']}")
    lines += ["", "## Selected lineup #1", "",
        f"Mean {_fmt(selected['mean'])}; P90 {_fmt(selected['p90'])}; salary ${selected['salary']:,}; "
        f"objective {_fmt(selected['objective'],4)}; role mix {selected['role_mix']}.",
        f"Diagnostic ownership sum {_fmt(selected['ownership']['sum'])}; stack ownership "
        f"{_fmt(selected['ownership']['stack_sum'])}; log proxy "
        f"{_fmt(selected['ownership']['log_proxy'],4)}; relative chalk "
        f"{_fmt(selected['ownership']['relative_chalk'],1)} percentile. Ownership contribution "
        "to this completed selector run: 0.000 (diagnostic only).", "",
        "| player | pos | salary | mean | P90 | own | football role | target share | carry share | purpose |",
        "|---|---|---:|---:|---:|---:|---|---:|---:|---|"]
    for row in selected["players"]:
        lines.append(f"| {row['name']} | {row['position']} | ${row['salary']:,} | {_fmt(row['mean'])} | "
                     f"{_fmt(row['p90'])} | {_fmt(row['ownership'])} | {row.get('role_classification') or 'n/a'} "
                     f"({row.get('role_confidence') or 'n/a'}) | {_fmt(row.get('week_1_target_share'),3)} | "
                     f"{_fmt(row.get('week_1_carry_share'),3)} | {row['purpose']} |")
    lines += ["", "### Five closest competing lineups", ""]
    for row in selected["closest_competitors"]:
        advantages = ", ".join(f"{key} +{value:.4f}" for key, value in row["winner_advantages"]) or "tie-break only"
        lines.append(f"- **#{row['rank']}** trails by {row['objective_gap']:.4f}. Winner minus competitor: "
                     f"mean {row['mean_delta_winner_minus_candidate']:+.2f}, P90 "
                     f"{row['p90_delta_winner_minus_candidate']:+.2f}, salary "
                     f"${row['salary_delta_winner_minus_candidate']:+,.0f}; relative chalk "
                     f"{_fmt(row['winner_relative_chalk'],1)} vs "
                     f"{_fmt(row['competitor_relative_chalk'],1)}. "
                     f"Main winner contributions: {advantages}.")
    lines += ["", "## Refresh delta from prior run", ""]
    if refresh["status"] != "available":
        lines.append(refresh["reason"])
    else:
        lines += [f"- Eligible added: {', '.join(refresh['eligible_added']) or 'none'}",
                  f"- Eligible removed: {', '.join(refresh['eligible_removed']) or 'none'}",
                  f"- Selected added: {', '.join(refresh['selected_lineup_added']) or 'none'}",
                  f"- Selected removed: {', '.join(refresh['selected_lineup_removed']) or 'none'}",
                  f"- Role classification changes: {len(refresh['role_classification_changes'])}",
                  f"- Ownership: {refresh['ownership_change']}",
                  "- Projection and candidate-exposure deltas are preserved in the JSON artifact."]
    lines += ["", "## Pre-lock decision", "", payload["decision"], ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--optimizer", type=Path, required=True)
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--previous-optimizer", type=Path)
    parser.add_argument("--previous-core", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts/sunday-main-priority-readiness-2026w2.json"))
    args = parser.parse_args()
    optimizer_payload = json.loads(args.optimizer.read_text())
    report = _report(optimizer_payload)
    projection_run_id = str(optimizer_payload["projection_run_id"])
    core_payload = json.loads(args.core.read_text())
    core_by_id = {str(row["player_id"]): row for row in core_payload["players"]}
    pool = get_optimizer_service()._load_player_pool(  # noqa: SLF001 - audit only
        2026, 2, "SUNDAY_MAIN", projection_run_id=projection_run_id,
    )
    pool_by_id = {str(row["player_id"]): row for row in pool.to_dict("records")}
    diagnostic_ownership, latest_ownership_run = _latest_ownership_diagnostic()
    for player_id, projected_ownership in diagnostic_ownership.items():
        if player_id in pool_by_id:
            pool_by_id[player_id]["ownership"] = projected_ownership
            pool_by_id[player_id]["ownership_run_id"] = str(
                latest_ownership_run["ownership_run_id"]
            )
    eligible_ids = {str(row["player_id"]) for row in report["role_exposure"]}
    candidate_ranks: dict[str, list[int]] = {}
    players_facing_denver: list[dict[str, Any]] = []
    for candidate in report["all_candidates"]:
        for player in candidate["roster"]:
            if str(player.get("opponent") or "").upper() == "DEN":
                players_facing_denver.append(
                    {"rank": candidate["rank"], "player": player["name"]}
                )
            if player["position"] in SKILL:
                candidate_ranks.setdefault(str(player["player_id"]), []).append(candidate["rank"])
    high_current = {player_id for player_id in eligible_ids
                    if core_by_id.get(player_id, {}).get("current_evidence_confidence") == "high_current"}
    stale = eligible_ids - high_current
    skill_rows = []
    candidate_role_flags = []
    for row in report["role_exposure"]:
        player_id = str(row["player_id"])
        source = pool_by_id.get(player_id, {})
        core = core_by_id.get(player_id, {})
        usage = core.get("current_usage") or {}
        flags = _status_flags(source, core)
        detail = {**row, "week_1_targets": usage.get("week_1_targets"),
            "week_1_carries": usage.get("week_1_carries"),
            "week_1_target_share": usage.get("week_1_target_share"),
            "week_1_carry_share": usage.get("week_1_carry_share"),
            "week_1_snap_share": usage.get("week_1_snap_share"),
            "roster_status": source.get("roster_status"),
            "injury_status": source.get("pregame_injury_status") or source.get("injury_status"),
            "football_classification": core.get("football_classification"),
            "current_evidence_confidence": core.get("current_evidence_confidence"),
            "relies_mainly_on_2025": core.get("relies_mainly_on_2025"), "flags": flags}
        skill_rows.append(detail)
        if player_id in candidate_ranks and flags:
            candidate_role_flags.append({**detail, "candidate_ranks": candidate_ranks[player_id]})
    candidate_role_flags.sort(key=lambda row: (-row["candidate_count"], row["name"]))
    full = _candidate_summary(report, core_by_id, pool_by_id)
    ownership_run_ids = sorted({str(pool_by_id[player_id].get("ownership_run_id"))
                                for player_id in eligible_ids
                                if pool_by_id.get(player_id, {}).get("ownership_run_id")})
    ownership_runs = _ownership_metadata(ownership_run_ids)
    ownership_values = [_number(pool_by_id.get(player_id, {}).get("ownership")) for player_id in eligible_ids]
    covered = sum(value is not None for value in ownership_values)
    positive = sum((value or 0) > 0 for value in ownership_values)
    ownership_run = ownership_runs[0] if ownership_runs else latest_ownership_run
    ownership_status = "diagnostic_current" if ownership_run else "unavailable"
    ownership = {"status": ownership_status,
        "ownership_run_id": str(ownership_run.get("ownership_run_id") or "") or None,
        "model_id": ownership_run.get("model_id"),
        "data_cutoff_at": ownership_run.get("data_cutoff_at"),
        "eligible_players": len(eligible_ids), "covered_players": covered,
        "positive_players": positive, "coverage_rate": covered / max(1, len(eligible_ids)),
        "model_metrics": ownership_run.get("metrics_json"),
        "assessment": ("Fresh slate-specific diagnostic generated after the selected projection; "
                       "it is reported here without changing selector weights or the completed lineup ranking." if ownership_run else
                       "No slate-specific estimate run is available."),
        "selector_changed": False}
    position_groups: dict[str, list[dict]] = {}
    for row in skill_rows:
        position_groups.setdefault(row["position"], []).append(row)
    underrepresented = []
    for row in skill_rows:
        core = core_by_id.get(str(row["player_id"]), {})
        if core.get("current_evidence_confidence") != "high_current" or not core.get("overall_core"):
            continue
        if row["candidate_count"] > 2:
            continue
        peers = position_groups[row["position"]]
        value = row["mean"] / max(1.0, row["salary"] / 1000)
        value_rank = 1 + sum(peer["mean"] / max(1.0, peer["salary"] / 1000) > value for peer in peers)
        if value_rank > max(12, len(peers) // 3):
            continue
        underrepresented.append({**row, "value_rank": value_rank, "position_count": len(peers),
            "diagnosis": ("No generated candidate contains this competitive-value core player; "
                          "candidate exploration requires review." if row["candidate_count"] == 0 else
                          "The generator found a containing lineup, but it ranked below alternatives; "
                          "this points to whole-lineup construction rather than total exploration failure.")})
    underrepresented.sort(key=lambda row: (row["candidate_count"], row["value_rank"]))
    previous_report = _report(json.loads(args.previous_optimizer.read_text())) if args.previous_optimizer else None
    previous_core_by_id = ({str(row["player_id"]): row for row in
                            json.loads(args.previous_core.read_text())["players"]}
                           if args.previous_core else {})
    refresh = _refresh_delta(report, previous_report, core_by_id, previous_core_by_id)
    if refresh.get("status") == "available":
        refresh["ownership_change"] = (
            "fresh diagnostic coverage is 263/263; the prior selector artifact did not "
            "carry a comparable complete ownership snapshot, so no numeric old/new delta is asserted"
        )
    payload = _json_safe({"artifact": "sunday_main_priority_readiness_v1",
        "projection_run_id": projection_run_id,
        "projection_cutoff": optimizer_payload.get("data_cutoff_at") or core_payload.get("data_cutoff_at"),
        "optimizer_job_id": optimizer_payload.get("job_id"),
        "data_quality": {"eligible_skill_players": len(eligible_ids),
            "high_current_role_players": len(high_current),
            "stale_unknown_role_players": len(stale),
            "players_facing_denver": players_facing_denver,
            "stale_in_candidates": [{"player_id": player_id,
                "player": pool_by_id.get(player_id, {}).get("name"),
                "ranks": candidate_ranks[player_id]} for player_id in sorted(stale & set(candidate_ranks))],
            "stale_in_top_20": [{"player_id": player_id,
                "player": pool_by_id.get(player_id, {}).get("name"),
                "ranks": [rank for rank in candidate_ranks[player_id] if rank <= 20]}
                for player_id in sorted(stale & set(candidate_ranks))
                if any(rank <= 20 for rank in candidate_ranks[player_id])],
            "candidate_role_flags": candidate_role_flags,
            "eligible_skill_audit": skill_rows},
        "ownership": ownership, "complete_candidate_pool": full,
        "underrepresented_core": underrepresented,
        "selected_lineup": _selected_explanation(report, core_by_id, pool_by_id, full),
        "refresh_delta": refresh,
        "decision": ("The current winner is football-sound and should remain the control. Resolve any "
                     "candidate-impacting inactive/stale flags and refresh ownership after injury news "
                     "before considering contest-layer weight changes. No projection or selector weight "
                     "was changed by this audit.")})
    args.output.write_text(json.dumps(payload, indent=2, default=str, allow_nan=False) + "\n")
    args.output.with_suffix(".md").write_text(_markdown(payload) + "\n")
    print(json.dumps({"eligible_skill": len(eligible_ids), "high_current": len(high_current),
        "stale_unknown": len(stale), "stale_in_candidates": len(stale & set(candidate_ranks)),
        "candidate_role_flags": len(candidate_role_flags),
        "ownership_coverage": f"{covered}/{len(eligible_ids)}",
        "output": str(args.output.with_suffix('.md'))}, indent=2))


if __name__ == "__main__":
    main()
