#!/usr/bin/env python3
"""Read-only CBC and QB-family parallelism benchmark for a saved Classic run."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from multiprocessing import get_context
from pathlib import Path
from time import perf_counter

import pandas as pd
import pulp
from sqlalchemy import text

from backend.app.product_services.gpp_optimizer import (
    LineupTagCaps, ObjectiveWeights, PortfolioTargets, SlateConfig, StackRules,
    TagThresholds, _build_lineup, tag_players,
)
from backend.app.product_services.lineup_correlation_scoring import (
    build_format_specific_terms, build_lineup_correlation_terms,
)
from backend.app.product_services.optimizer import OptimizerService
from backend.app.product_services.rule_library import resolve_strategy_profile


_CONTEXT: dict = {}
_OBJECTIVE: float | None = None
_ORIGINAL_BUNDLED = pulp.PULP_CBC_CMD


def _solver_version(path: str) -> str:
    output = subprocess.run([path, "-stop"], capture_output=True, text=True,
                            check=True).stdout
    return next((line.strip() for line in output.splitlines()
                 if line.startswith("Version:")), "unknown")


class _BundledRecorder(_ORIGINAL_BUNDLED):
    def actualSolve(self, lp, **kwargs):  # noqa: ANN001, N802
        global _OBJECTIVE
        status = super().actualSolve(lp, **kwargs)
        _OBJECTIVE = pulp.value(lp.objective)
        return status


class _NativeRecorder(pulp.COIN_CMD):
    def actualSolve(self, lp, **kwargs):  # noqa: ANN001, N802
        global _OBJECTIVE
        status = super().actualSolve(lp, **kwargs)
        _OBJECTIVE = pulp.value(lp.objective)
        return status


def _initialize(players, config, correlation_terms, format_terms, native_path,
                enforce_single_te, avoid_dst_opponents):  # noqa: ANN001
    _CONTEXT.update(players=players, config=config, correlation_terms=correlation_terms,
                    format_terms=format_terms, native_path=native_path,
                    enforce_single_te=enforce_single_te,
                    avoid_dst_opponents=avoid_dst_opponents)


def _solve(task: tuple[str, str, int, int]) -> dict:
    global _OBJECTIVE
    solver_kind, qb_id, catchers, bring_back = task
    players = _CONTEXT["players"]
    config = _CONTEXT["config"]
    rules = replace(config.stack_rules, min_pass_catchers=catchers,
                    min_bring_backs=bring_back)
    original = pulp.PULP_CBC_CMD
    if solver_kind == "native":
        pulp.PULP_CBC_CMD = lambda msg=False: _NativeRecorder(  # type: ignore[assignment]
            path=_CONTEXT["native_path"], msg=msg,
        )
    else:
        pulp.PULP_CBC_CMD = lambda msg=False: _BundledRecorder(msg=msg)  # type: ignore[assignment]
    _OBJECTIVE = None
    start = perf_counter()
    try:
        indexes = _build_lineup(
            players, config, None, [],
            enforce_single_te=bool(_CONTEXT["enforce_single_te"]),
            avoid_dst_opponents=bool(_CONTEXT["avoid_dst_opponents"]),
            stack_rules=rules, required_player_ids={qb_id},
            exact_pass_catchers=catchers, exact_bring_backs=bring_back,
            precomputed_correlation_terms=_CONTEXT["correlation_terms"],
            precomputed_format_terms=_CONTEXT["format_terms"],
        )
    finally:
        pulp.PULP_CBC_CMD = original
    duration = perf_counter() - start
    chosen = [players[i] for i in indexes] if indexes is not None else []
    return {
        "task": f"{qb_id}:QB+{catchers}:bringback{bring_back}",
        "solver": solver_kind, "seconds": duration,
        "status": "optimal" if indexes is not None else "infeasible",
        "objective": _OBJECTIVE,
        "player_ids": sorted(player.player_id for player in chosen),
        "salary": sum(player.salary for player in chosen),
        "mean": sum(player.projection for player in chosen),
        "summed_p90": sum(player.ceiling for player in chosen),
    }


def _load_frozen(run_id: str):
    service = OptimizerService()
    with service.engine.connect() as connection:
        row = connection.execute(text("""
            SELECT projection_run_id, season, week, slate_id, constraint_config_json
            FROM target.optimizer_run WHERE optimizer_run_id = :run_id
        """), {"run_id": run_id}).mappings().one()
    saved = row["constraint_config_json"]
    saved_rows = {str(value["player_id"]): value for value in
                  saved["strategy_runtime"]["player_pool"]["rows"] if value.get("included")}
    raw = service._load_player_pool(  # noqa: SLF001 - saved-run diagnostic
        row["season"], row["week"], row["slate_id"],
        projection_run_id=row["projection_run_id"],
    )
    pool = raw[raw["player_id"].astype(str).isin(saved_rows)].copy()
    if len(pool) != len(saved_rows):
        raise RuntimeError("Saved eligible IDs are missing from the pinned projection run")
    for column in ("salary", "projection", "p90"):
        for live in pool.to_dict("records"):
            recorded = saved_rows[str(live["player_id"])][column]
            if abs(float(live[column]) - float(recorded)) > 1e-8:
                raise RuntimeError(f"Frozen {column} differs for {live['player_id']}")
    pool["optimizer_context_adjustment"] = pool["player_id"].astype(str).map(
        {player_id: float(value.get("optimizer_context_adjustment") or 0.0)
         for player_id, value in saved_rows.items()}
    )
    ownership_rows = saved["decision_snapshot"].get("ownership_snapshot") or []
    ownership = {str(value["player_id"]): value.get("projected_ownership")
                 for value in ownership_rows}
    if ownership:
        pool["ownership"] = pd.to_numeric(
            pool["player_id"].astype(str).map(ownership), errors="coerce",
        )
    players = service._gpp_players_from_pool(pool)  # noqa: SLF001
    config_data = saved["strategy_runtime"]["config"]
    config = SlateConfig(
        stack_rules=StackRules(**config_data["stack_rules"]),
        tag_thresholds=TagThresholds(**config_data["tag_thresholds"]),
        objective_weights=ObjectiveWeights(**config_data["objective_weights"]),
        tag_caps=LineupTagCaps(**config_data["tag_caps"]),
        salary_cap=config_data["salary_cap"], roster_size=config_data["roster_size"],
        portfolio_targets=PortfolioTargets(**config_data["portfolio_targets"]),
        correlation_bonus=config_data["correlation_bonus"],
        uniqueness_overlap=config_data["uniqueness_overlap"],
        normalize_objective=config_data["normalize_objective"],
        stack_templates=[tuple(value) for value in config_data["stack_templates"]],
    )
    tag_players(players, config.tag_thresholds)
    profile = resolve_strategy_profile(contest_format="classic", objective="gpp")
    return players, config, (
        build_lineup_correlation_terms(players, profile=profile),
        build_format_specific_terms(players, profile=profile),
    ), saved, pool


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    parser.add_argument("--qb-count", type=int, default=2)
    parser.add_argument("--qb-id")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--native-path", default="/opt/homebrew/bin/cbc")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    players, config, (correlation_terms, format_terms), saved, pool = _load_frozen(args.run_id)
    starting = {str(value["player_id"]) for value in pool.to_dict("records")
                if value.get("position") == "QB" and value.get("is_starting_qb") in (True, 1)}
    qbs = sorted((player for player in players if player.position == "QB"
                  and player.player_id in starting
                  and (args.qb_id is None or player.player_id == args.qb_id)),
                 key=lambda player: (-player.projection, player.player_id))[:args.qb_count]
    if not qbs:
        raise ValueError("No viable starting QB matched the requested benchmark scope")
    families = ((1, 0), (1, 1), (2, 0), (2, 1))
    cases = [(qb.player_id, catchers, bring_back) for qb in qbs
             for catchers, bring_back in families]
    common = (players, config, correlation_terms, format_terms, args.native_path,
              bool(saved.get("enforce_single_te", False)),
              bool(saved.get("avoid_dst_opponents", False)))
    _initialize(*common)
    results = {}
    durations = {}
    for name, solver_kind, parallel in (("bundled_serial", "bundled", False),
                                        ("native_serial", "native", False),
                                        ("bundled_parallel", "bundled", True),
                                        ("native_parallel", "native", True)):
        tasks = [(solver_kind, *case) for case in cases]
        start = perf_counter()
        if parallel:
            with ProcessPoolExecutor(max_workers=args.workers, mp_context=get_context("spawn"),
                                     initializer=_initialize,
                                     initargs=(*common,)) as executor:
                rows = list(executor.map(_solve, tasks))
        else:
            rows = [_solve(task) for task in tasks]
        results[name] = rows
        durations[name] = perf_counter() - start
        print(f"{name}: {durations[name]:.2f}s for {len(rows)} exact solves", flush=True)
    baseline = results["bundled_serial"]
    discrepancies = []
    for name in ("native_serial", "bundled_parallel", "native_parallel"):
        for old, new in zip(baseline, results[name]):
            if (old["status"] != new["status"]
                    or (old["objective"] is not None and new["objective"] is not None
                        and abs(old["objective"] - new["objective"]) > 1e-5)):
                discrepancies.append({"variant": name, "task": old["task"],
                                      "bundled": old, "comparison": new})
    saved_players = {str(value["player_id"]): value for value in
                     saved["strategy_runtime"]["player_pool"]["rows"]
                     if value.get("included")}
    legality_failures = []
    checked = 0
    for variant, rows in results.items():
        for row in rows:
            if row["status"] != "optimal":
                continue
            checked += 1
            legal, reason = OptimizerService._validate_classic_lineups(
                [[saved_players[player_id] for player_id in row["player_ids"]]],
                requested_lineups=1, max_exposure=1.0,
                enforce_single_te=bool(saved.get("enforce_single_te", False)),
                avoid_dst_opponents=bool(saved.get("avoid_dst_opponents", False)),
                excluded_opponent_teams=set(saved.get("exclude_opponent_teams") or []),
            )
            if not legal:
                legality_failures.append({"variant": variant, "task": row["task"],
                                          "reason": reason})
    saved_injections = {value["source"]: value for value in
                        saved["strategy_runtime"]["classic_small_field"]
                        ["candidate_discovery"]["injections"]}
    saved_match_counts = {}
    for variant, rows in results.items():
        matches = 0
        for row in rows:
            qb_id, family = row["task"].split(":QB+")
            catchers, bring_back = family.split(":bringback")
            source = f"qb_construction:{qb_id}:{catchers}:{bring_back}"
            prior = saved_injections.get(source)
            matches += bool(prior and prior.get("player_ids") == row["player_ids"])
        saved_match_counts[variant] = matches
    report = {"source_optimizer_run_id": args.run_id,
              "projection_run_id": saved["strategy_runtime"]["player_pool"]["projection_run_id"],
              "source_config_sha256": hashlib.sha256(
                  json.dumps(saved, sort_keys=True, default=str).encode()
              ).hexdigest(),
              "eligible_player_count": len(players),
              "qb_count": len(qbs), "case_count": len(cases),
              "worker_count": args.workers,
              "python_hash_seed": os.environ.get("PYTHONHASHSEED"),
              "machine": platform.machine(),
              "bundled_solver": str(_ORIGINAL_BUNDLED().path),
              "bundled_solver_version": _solver_version(str(_ORIGINAL_BUNDLED().path)),
              "native_solver": args.native_path,
              "native_solver_version": _solver_version(args.native_path),
              "durations_seconds": durations, "results": results,
              "objective_discrepancies": discrepancies,
              "saved_injection_match_counts": saved_match_counts,
              "independent_legality_check": {"checked": checked,
                                             "failures": legality_failures}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(f"objective discrepancies: {len(discrepancies)}", flush=True)
    print(f"independent legality failures: {len(legality_failures)}", flush=True)
    print(f"report: {args.output}", flush=True)


if __name__ == "__main__":
    main()
