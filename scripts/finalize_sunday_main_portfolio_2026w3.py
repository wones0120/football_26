#!/usr/bin/env python3
"""Persist a guarded prelock Classic portfolio from a saved optimizer lineage."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pulp
from sqlalchemy import text

from backend.app.db import engine
from backend.app.product_dependencies import get_optimizer_service
from backend.app.product_services.classic_frontier_diagnostic import (
    add_relative_chalk, candidate_ownership, lineup_key,
)
from backend.app.product_services.classic_small_field import (
    describe_candidate, expand_candidate_discovery,
)
from backend.app.product_services.football_sanity_deficit import lineup_sanity_deficit
from backend.app.product_services.gpp_optimizer import (
    GPPOptimizerResult, _build_lineup, build_format_specific_terms,
    build_lineup_correlation_terms,
)
from backend.app.product_services.optimizer import OptimizerJob
from backend.app.product_services.rule_library import resolve_strategy_profile
from scripts.audit_sunday_main_portfolio_frontier import load_frozen


SOURCE_RUN = "8d01319a-c852-4304-ae82-9c94beaf70c3"
GUARD = 5.05
COKER = "2fa43876-8b80-4de0-a467-82bfa150f042"
FLOWERS = "ecadd109-bcd3-46c5-b77e-60a6d3214d7f"
BONUS_KEYS = ("context", "qb_stack", "bring_back", "game_environment", "correlation")
OUTPUT = Path("artifacts/sunday-main-final-five-2026w3.json")


def _source_lineups(run_id: str) -> tuple[list[list[str]], list[list[str]]]:
    selected, controls = [], []
    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT l.lineup_number, array_agg(lp.player_id ORDER BY lp.slot_index) AS ids,
                   (array_agg(lp.player_json ORDER BY lp.slot_index))[1] AS first_player
            FROM target.lineup l JOIN target.lineup_player lp ON lp.lineup_id=l.lineup_id
            WHERE l.optimizer_run_id=:run_id GROUP BY l.lineup_number ORDER BY l.lineup_number
        """), {"run_id": run_id}).mappings().all()
    for row in rows:
        selected.append(list(row["ids"]))
        control = (row["first_player"].get("lineup_control_comparison") or {}).get("control_lineup") or []
        if len(control) == 9:
            controls.append([str(player["player_id"]) for player in control])
    return selected, controls


def _prior_sequential(current_ids: set[str]) -> list[list[str]]:
    """Reuse the saved 120 ordinary candidates from the same projection run."""
    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT constraint_config_json->'strategy_runtime'->'classic_small_field'->'all_candidates'
            FROM target.optimizer_run
            WHERE optimizer_run_id='a6d7f5e7-db0f-44ae-87c4-60a826973408'
              AND projection_run_id=(SELECT projection_run_id FROM target.optimizer_run
                                     WHERE optimizer_run_id=:source_run)
        """), {"source_run": SOURCE_RUN}).scalar()
    return [list(row["player_ids"]) for row in rows or []
            if set(row["player_ids"]) <= current_ids]


def _kickoff(value: str | None) -> datetime:
    match = re.search(r"(\d\d/\d\d/\d{4})\s+(\d\d:\d\d[AP]M)\s+ET", value or "")
    if not match:
        return datetime.min
    return datetime.strptime(" ".join(match.groups()), "%m/%d/%Y %I:%M%p")


def _slots(ids: list[str], by_id: dict, source: dict) -> list[dict]:
    players = [by_id[player_id] for player_id in ids]
    groups = {position: [p for p in players if p.position == position]
              for position in ("QB", "RB", "WR", "TE", "DST")}
    for group in groups.values():
        group.sort(key=lambda p: (_kickoff(source[p.player_id].get("game_id")), p.name))
    fixed = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "DST": 1}
    extras = [p for pos, group in groups.items() for p in group[fixed[pos]:]]
    if len(extras) != 1:
        raise ValueError("Lineup has no unique FLEX player")
    flex = extras[0]
    ordered = [("QB", groups["QB"][0]), *( ("RB", p) for p in groups["RB"][:2]),
               *(("WR", p) for p in groups["WR"][:3]), ("TE", groups["TE"][0]),
               ("FLEX", flex), ("DST", groups["DST"][0])]
    service = get_optimizer_service()
    result = []
    for slot, player in ordered:
        row = service._gpp_player_to_dict(player)
        saved = source[player.player_id]
        row.update({"roster_position": slot, "dk_player_id": saved.get("dk_player_id"),
                    "game_id": saved.get("game_id"),
                    "injury_status": saved.get("pregame_injury_status") or saved.get("injury_status"),
                    "ownership_run_id": saved.get("ownership_run_id")})
        result.append(row)
    return result


def _select(candidates: list[dict], *, exclude: set[str], exposure_limit: int,
            distinct_qbs: int) -> dict:
    eligible = [row for row in candidates if not (exclude & set(row["player_ids"]))]
    model = pulp.LpProblem("guarded_final_five", pulp.LpMaximize)
    variables = pulp.LpVariable.dicts("lineup", range(len(eligible)), cat="Binary")
    model += pulp.lpSum(float(row["objective_score"]) * variables[i]
                        for i, row in enumerate(eligible))
    model += pulp.lpSum(variables.values()) == 5
    by_qb: dict[str, list[int]] = defaultdict(list)
    by_non_qb: dict[str, list[int]] = defaultdict(list)
    sets = []
    for i, row in enumerate(eligible):
        ids = set(row["player_ids"])
        sets.append(ids)
        qb = str(row["qb"]["player_id"])
        by_qb[qb].append(i)
        for player_id in ids - {qb}:
            by_non_qb[player_id].append(i)
    qb_active = pulp.LpVariable.dicts("qb", list(by_qb), cat="Binary")
    for qb, indexes in by_qb.items():
        appearances = pulp.lpSum(variables[i] for i in indexes)
        model += appearances <= (1 if distinct_qbs == 5 else 2)
        model += appearances >= qb_active[qb]
        model += appearances <= 5 * qb_active[qb]
    model += pulp.lpSum(qb_active.values()) >= distinct_qbs
    for indexes in by_non_qb.values():
        model += pulp.lpSum(variables[i] for i in indexes) <= exposure_limit
    for i in range(len(eligible)):
        for j in range(i+1, len(eligible)):
            if len(sets[i] & sets[j]) > 6:
                model += variables[i] + variables[j] <= 1
    status = model.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=120))
    if status != pulp.LpStatusOptimal:
        return {"status": pulp.LpStatus[status], "rows": [], "candidate_count": len(eligible)}
    rows = sorted((eligible[i] for i in variables if pulp.value(variables[i]) > .9),
                  key=lambda row: -row["objective_score"])
    return {"status": "optimal", "rows": rows, "candidate_count": len(eligible),
            "score_sum": sum(row["objective_score"] for row in rows),
            "mean_sum": sum(row["mean"] for row in rows),
            "p90_sum": sum(row["p90"] for row in rows),
            "distinct_qbs": len({row["qb"]["player_id"] for row in rows}),
            "exposure_limit": exposure_limit}


def _best_portfolio(candidates: list[dict], *, exclude: set[str]) -> dict:
    attempts = []
    for qbs, exposure in ((5, 4), (5, 5), (4, 4), (4, 5)):
        found = _select(candidates, exclude=exclude, exposure_limit=exposure,
                        distinct_qbs=qbs)
        attempts.append({k: v for k, v in found.items() if k != "rows"} | {"qb_target": qbs})
        if found["status"] == "optimal":
            found["attempts"] = attempts
            return found
    return {"status": "infeasible", "rows": [], "attempts": attempts}


def _persist(name: str, selected: dict, frozen: dict, by_id: dict, source: dict,
             report: dict, excluded: set[str], *, guard: float = GUARD) -> str:
    if selected["status"] != "optimal":
        raise ValueError(f"Cannot persist {name}: {selected['status']}")
    now = datetime.now(timezone.utc)
    run_id = str(uuid4())
    lineups = []
    for row in selected["rows"]:
        lineup = _slots(row["player_ids"], by_id, source)
        for player in lineup:
            player["lineup_selector_score"] = row["objective_score"]
            player["lineup_mean_loss_vs_global"] = row["mean_loss"]
            player["lineup_p90_loss_vs_global"] = row["p90_loss"]
        lineups.append(lineup)
    params = {"num_lineups": 5, "max_exposure": selected["exposure_limit"] / 5,
              "enforce_single_te": True, "avoid_dst_opponents": True,
              "exclude_opponent_teams": ["DEN"],
              "portfolio_constraints": {"joint_mean_p90_guard": guard,
                                        "max_pairwise_overlap": 6,
                                        "non_qb_max_appearances": selected["exposure_limit"],
                                        "distinct_qbs": selected["distinct_qbs"],
                                        "excluded_player_ids": sorted(excluded)},
              "ownership_run_id": frozen["params"]["ownership_run_id"],
              "decision_context": {"reason_selected": name,
                                   "injury_scenarios": [{"name": name,
                                                         "excluded_player_ids": sorted(excluded)}]},
              "strategy_runtime": {"final_five_report": {"source_run_id": SOURCE_RUN,
                                                           "report_path": str(OUTPUT),
                                                           "scenario": name,
                                                           "candidate_count": report["candidate_count"]}}}
    job = OptimizerJob(job_id=run_id, status="completed", created_at=now, updated_at=now,
                       season=2026, week=3, slate="SUNDAY_MAIN",
                       strategy="classic_small_field_gpp", contest_format="classic",
                       objective="gpp", params=params,
                       projection_run_id=frozen["run"]["projection_run_id"],
                       data_cutoff_at=frozen["run"]["data_cutoff_at"],
                       results=lineups,
                       message=(f"Final five: {name}; {len(report['candidates'])} expanded candidates; "
                                f"joint mean/P90 guard {guard}; five-entry global selection; "
                                f"overlap <=6; distinct QBs {selected['distinct_qbs']}"))
    service = get_optimizer_service()
    if not service._persist_optimizer_run(job):
        raise RuntimeError(f"Application failed to persist {name}")
    if not service.get_job(run_id) or len(service.get_job(run_id).results or []) != 5:
        raise RuntimeError(f"Persisted {name} failed reload")
    return run_id


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-run", default=SOURCE_RUN)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    frozen = load_frozen(args.source_run)
    with engine.connect() as connection:
        injury_rows = connection.execute(text("""
            SELECT DISTINCT ON (player_id) player_id, injury_status, injury_details,
                   as_of, source
            FROM target.snapshot_injury_status
            WHERE season=2026 AND week=3 AND UPPER(slate)='SUNDAY_MAIN'
              AND as_of <= :source_created_at
            ORDER BY player_id, as_of DESC
        """), {"source_created_at": frozen["run"]["created_at"]}).mappings().all()
    injuries = {str(row["player_id"]): dict(row) for row in injury_rows}
    out_ids = {pid for pid, row in injuries.items()
               if str(row["injury_status"]).upper() in {"O", "OUT", "IR", "INACTIVE"}}
    players = [player for player in frozen["players"] if player.player_id not in out_ids]
    config = frozen["config"]
    by_id = {player.player_id: player for player in players}
    source = {str(row["player_id"]): row for row in frozen["pool"].to_dict("records")}
    source_selected, controls = _source_lineups(args.source_run)
    source_selected = [ids for ids in source_selected if set(ids) <= set(by_id)]
    controls = [ids for ids in controls if set(ids) <= set(by_id)]
    for pid, row in injuries.items():
        if pid in source:
            source[pid]["pregame_injury_status"] = row["injury_status"]
    print(f"Loaded {len(players)} frozen eligible players, {len(source_selected)} production and {len(controls)} control lineups", flush=True)
    source_eligible_ids = {player.player_id for player in frozen["players"]}
    print(f"Excluded {len(out_ids & source_eligible_ids)} snapshot-confirmed OUT players from discovery", flush=True)
    prior_sequential = _prior_sequential(set(by_id))
    ordinary = {tuple(sorted(ids)): [by_id[pid] for pid in ids]
                for ids in [*source_selected, *prior_sequential]}
    sequential = GPPOptimizerResult(
        job_id=args.source_run, status="completed", message="saved ordinary candidates",
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        lineups=list(ordinary.values()), config=config, analysis=None, portfolio=None,
        iterations=1,
    )
    print(f"Loaded {len(source_selected)} current production and {len(prior_sequential)} prior saved sequential candidates", flush=True)
    expanded, discovery = expand_candidate_discovery(
        sequential, players, enforce_single_te=True, avoid_dst_opponents=True,
        starting_qb_ids={p.player_id for p in players if p.position == "QB"},
    )
    universe: dict[tuple[str, ...], set[str]] = defaultdict(set)
    for lineup in sequential.lineups:
        universe[tuple(sorted(p.player_id for p in lineup))].add("ordinary_sequential")
    for index, ids in enumerate(source_selected, 1):
        universe[tuple(sorted(ids))].add(f"source_production_{index}")
    for index, ids in enumerate(controls, 1):
        universe[tuple(sorted(ids))].add(f"rules_disabled_control_{index}")
    for lineup in expanded:
        universe[tuple(sorted(p.player_id for p in lineup))].add("expanded_discovery")
    for injection in discovery["injections"]:
        if injection["status"] == "legal":
            universe[tuple(injection["player_ids"])].add(injection["source"])
    global_mean = max(sum(by_id[pid].projection for pid in row["player_ids"])
                      for row in discovery["injections"] if row["source"] == "global_highest_mean"
                      and row["status"] == "legal")
    global_p90 = max(sum(by_id[pid].ceiling for pid in row["player_ids"])
                     for row in discovery["injections"] if row["source"] == "global_highest_p90"
                     and row["status"] == "legal")
    print(f"Expanded to {len(universe)} unique candidates; maxima {global_mean:.4f}/{global_p90:.4f}", flush=True)
    profile = resolve_strategy_profile(contest_format="classic", objective="gpp")
    terms = build_lineup_correlation_terms(players, profile=profile)
    formats = build_format_specific_terms(players, profile=profile)
    scenario_exclusions = {"active": set(), "coker_out": {COKER},
                           "flowers_out": {FLOWERS}, "both_out": {COKER, FLOWERS}}
    requests = [(qb.player_id, name, excluded)
                for name, excluded in scenario_exclusions.items()
                for qb in players if qb.position == "QB"]

    def solve(request):
        qb_id, name, excluded = request
        active_players = [player for player in players if player.player_id not in excluded]
        active_terms = terms if not excluded else build_lineup_correlation_terms(active_players, profile=profile)
        active_formats = formats if not excluded else build_format_specific_terms(active_players, profile=profile)
        indexes = _build_lineup(
            active_players, config, None, [], required_player_ids={qb_id},
            enforce_single_te=True, avoid_dst_opponents=True,
            minimum_mean=global_mean-GUARD, minimum_p90=global_p90-GUARD,
            precomputed_correlation_terms=active_terms, precomputed_format_terms=active_formats,
        )
        return name, qb_id, ([active_players[i].player_id for i in indexes]
                             if indexes is not None else None)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(solve, request) for request in requests]
        for index, future in enumerate(as_completed(futures), 1):
            name, qb_id, ids = future.result()
            if ids:
                universe[tuple(sorted(ids))].add(f"guarded_qb:{name}:{qb_id}")
            if index % 25 == 0:
                print(f"Solved {index}/{len(requests)} guarded QB/scenario families", flush=True)
    game_totals = sorted({float(p.game_total) for p in players if p.game_total is not None})
    candidates = []
    for ids, origins in universe.items():
        if not set(ids) <= set(by_id):
            continue
        row = describe_candidate([by_id[pid] for pid in ids], all_players=players,
                                 config=config, pool_by_id=source,
                                 ownership_available=False, candidate_aware_ownership=True,
                                 game_totals=game_totals)
        row["sources"] = sorted(origins)
        row["mean_loss"] = global_mean-row["mean"]
        row["p90_loss"] = global_p90-row["p90"]
        row["ownership"] = candidate_ownership(row, frozen["ownership"])
        row["correlation_context_gain"] = sum(row["components"].get(key, 0.0)
                                              for key in BONUS_KEYS)
        candidates.append(row)
    candidates.sort(key=lambda row: -row["objective_score"])
    add_relative_chalk(candidates)
    for rank, row in enumerate(candidates, 1):
        row["rank"] = rank
    eligible = [row for row in candidates if row["mean_loss"] <= GUARD+1e-8
                and row["p90_loss"] <= GUARD+1e-8]
    print(f"Quality screen: {len(eligible)}/{len(candidates)} candidates", flush=True)
    scenarios = {name: _best_portfolio(eligible, exclude=excluded)
                 for name, excluded in scenario_exclusions.items()}
    if scenarios["active"]["status"] != "optimal":
        raise RuntimeError("No five-entry portfolio fits the specified joint guard")
    report = {"source_optimizer_run_id": args.source_run,
              "projection_run_id": frozen["run"]["projection_run_id"],
              "ownership_run_id": frozen["params"]["ownership_run_id"],
              "projection_cutoff_at": str(frozen["run"]["data_cutoff_at"]),
              "injury_snapshot_cutoff_at": str(max((row["as_of"] for row in injury_rows), default=None)),
              "injury_source": sorted({str(row["source"]) for row in injury_rows}),
              "snapshot_out_ids": sorted(out_ids),
              "snapshot_out_players": [
                  {"player_id": pid, "name": frozen["saved"][pid].get("player_name"),
                   "status": injuries[pid]["injury_status"],
                   "details": injuries[pid]["injury_details"]}
                  for pid in sorted(out_ids & source_eligible_ids)],
              "guard": GUARD, "global_mean": global_mean, "global_p90": global_p90,
              "candidate_count": len(candidates), "guarded_candidate_count": len(eligible),
              "discovery": discovery, "candidates": candidates,
              "scenarios": {}, "no_game_outcomes_used": True}
    for name, selected in scenarios.items():
        summary = {key: value for key, value in selected.items() if key != "rows"}
        summary["lineups"] = []
        for row in selected["rows"]:
            roster = _slots(row["player_ids"], by_id, source)
            same_qb = [other for other in eligible
                       if other["qb"]["player_id"] == row["qb"]["player_id"]]
            control = max(same_qb, key=lambda other: other["mean"]+other["p90"])
            summary["lineups"].append({
                "rank": row["rank"], "roster": roster,
                "salary": row["salary"], "mean": row["mean"], "p90": row["p90"],
                "selector": row["objective_score"], "ownership": row["ownership"],
                "qb": row["qb"], "primary_game": row.get("primary_game"),
                "stack": row["stack"], "mean_loss": row["mean_loss"],
                "p90_loss": row["p90_loss"], "sources": row["sources"],
                "strongest_same_qb_raw_control": {
                    "rank": control["rank"], "mean": control["mean"],
                    "p90": control["p90"], "selector": control["objective_score"],
                    "mean_sacrifice": control["mean"]-row["mean"],
                    "p90_sacrifice": control["p90"]-row["p90"],
                    "correlation_context_gain": row["correlation_context_gain"]-
                                                control["correlation_context_gain"],
                },
                "football_sanity": lineup_sanity_deficit(
                    roster, core_by_id={}, player_pool=[{"player_id": p.player_id,
                    "name": p.name, "team": p.team, "position": p.position,
                    "salary": p.salary, "projection": p.projection} for p in players]),
            })
        if selected["status"] == "optimal":
            summary["optimizer_run_id"] = _persist(name, selected, frozen, by_id, source,
                                                    report, scenario_exclusions[name])
        report["scenarios"][name] = summary
        print(name, summary["status"], summary.get("optimizer_run_id"), flush=True)
    args.output.write_text(json.dumps(report, indent=2, default=str, allow_nan=False)+"\n")
    print(json.dumps({"output": str(args.output),
                      "runs": {name: value.get("optimizer_run_id")
                               for name, value in report["scenarios"].items()}}, indent=2))


if __name__ == "__main__":
    main()
