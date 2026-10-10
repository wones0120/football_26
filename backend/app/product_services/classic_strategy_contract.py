"""Serialized production Large-GPP execution, offline parity, and labelled shadows.

This module never loads current slate data. App eligibility supplies the immutable
ordered Player frame; replay consumes that exact frame and the same pipeline.
"""
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
from itertools import combinations
import json
from pathlib import Path
import inspect

import pulp
from math import ceil, floor

from sqlalchemy import create_engine

from .classic_candidate_policy import LARGE_GPP_CANDIDATE_POLICY
from .classic_portfolio_controls import LARGE_GPP_CONTROL_KEYS, apply_large_gpp_controls, validate_large_gpp_controls, explicit_appearance_limit
from .classic_primary_game import primary_game_exposure, resolve_primary_game_cap
from .gpp_optimizer import (Player, SlateConfig, StackRules, TagThresholds,
    ObjectiveWeights, LineupTagCaps, PortfolioTargets, FULL_CONTROL_COMPARISON_MAX_LINEUPS, analyze_slate,
    build_large_gpp_config, run_gpp_pipeline, resolve_portfolio_config)

CONTRACT_ID = "classic_large_gpp_effective_strategy_v1"
STRATEGY_ID = "classic_large_gpp_v1"
EXECUTION_MODES = {"PRODUCTION", "PARITY", "RESEARCH_SHADOW"}


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def config_from_dict(value):
    value = dict(value)
    for key, cls in (("stack_rules", StackRules), ("tag_thresholds", TagThresholds),
                     ("objective_weights", ObjectiveWeights), ("tag_caps", LineupTagCaps),
                     ("portfolio_targets", PortfolioTargets)):
        value[key] = cls(**value[key])
    return SlateConfig(**value)


def model_fingerprints(model):
    """Ignore solve values, JSON int/float spelling, and additive term ordering."""
    def terms(expression):
        return sorted((variable.name, float(coefficient)) for variable, coefficient in expression.items())
    region = {"variables": sorted((v.name, v.cat,
        float(v.lowBound) if v.lowBound is not None else None,
        float(v.upBound) if v.upBound is not None else None) for v in model.variables()),
        "constraints": sorted((name, constraint.sense, float(constraint.constant), terms(constraint))
                              for name, constraint in model.constraints.items())}
    return {"feasible_region_sha256": digest(region),
            "objective_sha256": digest({"constant": float(model.objective.constant), "terms": terms(model.objective)})}


def implementation_fingerprints(solver_backend="bundled"):
    from .cbc_solver import make_cbc_solver
    from .optimizer import OptimizerService
    files = ("gpp_optimizer.py", "classic_candidate_policy.py", "classic_primary_game.py",
             "rule_library.py", "lineup_correlation_scoring.py", "classic_portfolio_controls.py", "classic_construction.py",
             "classic_prospective.py", "classic_strategy_contract.py")
    root = Path(__file__).parent
    solver = make_cbc_solver(solver_backend)
    return {"source_sha256": {name: sha256((root / name).read_bytes()).hexdigest() for name in files},
        "player_adapter_sha256": sha256(inspect.getsource(OptimizerService._gpp_players_from_pool).encode()).hexdigest(),
        "pulp_version": pulp.__version__, "cbc_sha256": sha256(Path(solver.path).read_bytes()).hexdigest()}


def build_strategy_contract(*, players, pipeline_options, requested, metadata,
                            mode="PRODUCTION", deviations=(), risk_classifications=None):
    if mode not in EXECUTION_MODES:
        raise ValueError("Choose PRODUCTION, PARITY, or RESEARCH_SHADOW explicitly")
    if (mode != "RESEARCH_SHADOW" and deviations) or (mode == "RESEARCH_SHADOW" and not deviations):
        raise ValueError("Research deviations require an explicitly labelled RESEARCH_SHADOW")
    options = {key: value for key, value in pipeline_options.items() if key not in {"players", "engine"}}
    # The app supplies existing cutoff-safe assessments. No risk is inferred from
    # missing evidence and no conservative Small-field policy is imported.
    classifications = dict(risk_classifications or {})
    if classifications:
        options["elevated_player_ids"] = sorted(pid for pid, row in classifications.items()
            if row["bucket"] == "questionable_elevated")
    validate_large_gpp_controls(options)
    cap = resolve_primary_game_cap(options.get("max_lineups_per_primary_game"))
    options["max_lineups_per_primary_game"] = cap
    config = build_large_gpp_config(analyze_slate(players),
        ownership_available=options["ownership_available"],
        minimum_uniqueness=options.get("minimum_uniqueness") or 2,
        max_from_team=options.get("max_from_team"), max_from_game=options.get("max_from_game"),
        stack_templates=options.get("stack_templates"),
        maximum_exposure_by_player=options.get("maximum_exposure_by_player"),
        minimum_exposure_by_player=options.get("minimum_exposure_by_player"),
        candidate_aware_ownership=options.get("candidate_aware_ownership", False))
    config = resolve_portfolio_config([Player(**{**asdict(p), "tags": set(p.tags)}) for p in players], config,
        ownership_available=options["ownership_available"], long_shot_mode=options.get("long_shot_mode", False),
        num_lineups=options["num_lineups"])
    config = apply_large_gpp_controls(config, options)
    # Store ordered canonical inputs, including context evidence, not just names.
    rows = [{**asdict(player), "tags": sorted(player.tags)} for player in players]
    if len({row["player_id"] for row in rows}) != len(rows):
        raise ValueError("Strategy contract requires unique canonical player IDs")
    if set(options.get("elevated_player_ids") or []) - {row["player_id"] for row in rows}:
        raise ValueError("Elevated-risk assessment references players outside the candidate pool")
    effective = {"players": rows, "pipeline_options": options,
        "resolved_config": asdict(config), "eligible_player_ids": sorted(row["player_id"] for row in rows),
        "eligibility_policy": LARGE_GPP_CANDIDATE_POLICY,
        "upstream_eligibility": "saved salary identity/status, point-in-time injury and player-pool safety, user exclusions, then strategy ranking",
        "generation": "sequential exposure-aware ILP; accepted candidates are the selected portfolio",
        "control_comparison_scope": ("all_lineups" if options["num_lineups"] <= FULL_CONTROL_COMPARISON_MAX_LINEUPS
            else "first_lineup") if options.get("include_control_comparisons", True) else "none",
        "selection": "template cycle; best feasible next lineup; no claim of a joint portfolio optimum",
        "primary_game_identity": "sorted uppercase QB team/opponent pair; opposite QB directions share one game",
        "max_lineups_per_primary_game": cap,
        "entry_count": options["num_lineups"], "max_exposure": options["max_exposure"],
        "global_player_appearance_limit": max(1, ceil(options["num_lineups"] * options["max_exposure"])),
        "exposure_rule": "ceil(entries * global rate), intersect floor(entries * player cap); explicit minimum/lock requirements retain existing semantics",
        "injury_risk_policy": "existing upstream classifications and explicit requested caps only; no small-field automatic risk policy added",
        "risk_classifications": classifications,
        "user_preference_reasons": {
            key: "explicit_user_portfolio_constraint" for key in LARGE_GPP_CONTROL_KEYS
            if options.get(key) is not None},
        "max_lineup_overlap": config.uniqueness_overlap,
        "elevated_player_max_exposure": options.get("elevated_player_max_exposure"),
        "max_elevated_players_per_lineup": options.get("max_elevated_players_per_lineup"),
        "elevated_exposure_rounding": "floor(requested entries * explicit rate), intersect existing player/global limits; never expand for locks",
        "tie_break": "preserved ordered frozen frame and bundled CBC; exact ties audited by primary objective, never by changing scoring weights"}
    effective = json.loads(json.dumps(effective, allow_nan=False))
    contract = {"implementation": implementation_fingerprints(options.get("solver_backend", "bundled")), "contract_id": CONTRACT_ID, "strategy_id": STRATEGY_ID,
        "execution_mode": mode, "strategy_label": STRATEGY_ID if mode != "RESEARCH_SHADOW" else STRATEGY_ID + " + research_shadow",
        "deviations": list(deviations), "metadata": dict(metadata),
        "requested": {"enforce_single_te": requested.get("enforce_single_te", options.get("enforce_single_te", False)), "entry_count": requested.get("num_lineups", options["num_lineups"]), "max_exposure": requested.get("max_exposure", options["max_exposure"]),
                      "max_lineups_per_primary_game": requested.get("max_lineups_per_primary_game")},
        "sources": {"enforce_single_te": "request" if "enforce_single_te" in requested else "strategy_default", "max_lineups_per_primary_game": "request" if "max_lineups_per_primary_game" in requested else "strategy_default_no_limit"},
        "effective": effective, "effective_sha256": digest(effective)}
    for key in LARGE_GPP_CONTROL_KEYS:
        contract["requested"][key] = requested.get(key)
        contract["sources"][key] = "request" if requested.get(key) is not None else "strategy_default"
    if options.get("max_lineup_overlap") is None and requested.get("minimum_uniqueness", 2) != 2:
        contract["sources"]["max_lineup_overlap"] = "legacy_minimum_uniqueness_request"
    for key in ("max_exposure", "entry_count"):
        contract["sources"][key] = "request" if ("num_lineups" if key == "entry_count" else key) in requested else "strategy_default"
    return {**contract, "sha256": digest(contract)}


def validate_strategy_contract(contract):
    if contract.get("contract_id") != CONTRACT_ID or contract.get("strategy_id") != STRATEGY_ID:
        raise ValueError("Unsupported Large-GPP strategy contract")
    if digest({key: value for key, value in contract.items() if key != "sha256"}) != contract.get("sha256"):
        raise ValueError("Strategy contract checksum mismatch")
    if digest(contract["effective"]) != contract.get("effective_sha256"):
        raise ValueError("Effective strategy checksum mismatch")
    if contract.get("implementation") != implementation_fingerprints(contract["effective"]["pipeline_options"].get("solver_backend", "bundled")):
        raise ValueError("Replay implementation or solver differs from the frozen contract; establish parity explicitly before replay")
    mode = contract.get("execution_mode")
    if mode not in EXECUTION_MODES or (mode != "RESEARCH_SHADOW" and contract.get("deviations")) or (mode == "RESEARCH_SHADOW" and not contract.get("deviations")):
        raise ValueError("Invalid execution mode or silent research deviation")


def execute_strategy_contract(contract, *, engine=None):
    validate_strategy_contract(contract)
    effective = contract["effective"]
    if effective["generation"] != "sequential exposure-aware ILP; accepted candidates are the selected portfolio":
        raise ValueError("Expanded discovery contracts must use the explicitly labelled research replay command")
    players = [Player(**{**row, "tags": set(row["tags"])}) for row in effective["players"]]
    return run_gpp_pipeline(players=players, engine=engine or create_engine("sqlite:///:memory:"),
        effective_config=config_from_dict(effective["resolved_config"]), **effective["pipeline_options"])


def portfolio_audit(contract, lineups, *, trace=()):
    effective = contract["effective"]; options = effective["pipeline_options"]
    peers = [Player(**{**row, "tags": set(row["tags"])}) for row in effective["players"]]
    config = config_from_dict(effective["resolved_config"])
    config = resolve_portfolio_config(peers, config, ownership_available=options["ownership_available"],
        long_shot_mode=options.get("long_shot_mode", False), num_lineups=options["num_lineups"])
    lookup = {player.player_id: player for player in peers}
    from .classic_small_field import describe_candidate
    rows = [describe_candidate([lookup[player.player_id] for player in lineup], all_players=peers,
        config=config, pool_by_id={}, ownership_available=options["ownership_available"],
        game_totals=sorted({player.game_total for player in peers if player.game_total is not None})) for lineup in lineups]
    ids = [set(row["player_ids"]) for row in rows]
    exposure = Counter(pid for roster in ids for pid in roster)
    games = primary_game_exposure(lineups)
    cap = effective["max_lineups_per_primary_game"]
    overlap = [[len(a & b) for b in ids] for a in ids]
    maximums = config.portfolio_targets.player_exposure_caps
    minimums = options.get("minimum_exposure_by_player") or {}
    elevated_ids = set(options.get("elevated_player_ids") or [])
    elevated_rate = options.get("elevated_player_max_exposure")
    def appearance_limit(pid):
        rate = maximums.get(pid, 1.0)
        ceiling = (explicit_appearance_limit(options["num_lineups"], rate)
                   if elevated_rate is not None and pid in elevated_ids
                   else floor(options["num_lineups"] * rate))
        return min(ceiling,
            max(effective["global_player_appearance_limit"],
                ceil(options["num_lineups"] * minimums.get(pid, 0))))
    limits = {pid: appearance_limit(pid) for pid in exposure}
    violations = (["primary_game_cap"] if cap is not None and max(games.values(), default=0) > cap else [])
    if len(rows) != options["num_lineups"]:
        violations.append("entry_count")
    if any(len(a & b) > config.uniqueness_overlap for a, b in combinations(ids, 2)):
        violations.append("overlap")
    violations += ["player_cap:" + pid for pid, count in exposure.items() if count > limits[pid]]
    elevated_limit = explicit_appearance_limit(options["num_lineups"], elevated_rate) if elevated_rate is not None else None
    per_lineup_cap = options.get("max_elevated_players_per_lineup")
    elevated_counts = [len(roster & elevated_ids) for roster in ids]
    if elevated_limit is not None and any(exposure[pid] > elevated_limit for pid in elevated_ids):
        violations.append("elevated_player_exposure")
    if per_lineup_cap is not None and max(elevated_counts, default=0) > per_lineup_cap:
        violations.append("elevated_players_per_lineup")
    max_overlap = max((len(a & b) for a, b in combinations(ids, 2)), default=0)
    max_appearances = max(exposure.values(), default=0)
    max_elevated_appearances = max((exposure[pid] for pid in elevated_ids), default=0)
    def setting(key, label, value, achieved):
        return dict(key=key, setting=label, requested=contract["requested"].get(key),
                    effective=value, source=contract["sources"].get(key, "strategy_default"), achieved=achieved)
    settings = [
        setting("enforce_single_te", "Enforce single TE (TE excluded from FLEX)", bool(options.get("enforce_single_te", False)),
                max((sum(p.position == "TE" for p in row) for row in lineups), default=0)),
        setting("entry_count", "Entry count", options["num_lineups"], len(rows)),
        setting("max_exposure", "Max player exposure", options["max_exposure"],
                f"{max_appearances}/{options['num_lineups']} requested entries; global limit {effective['global_player_appearance_limit']}"),
        setting("max_lineups_per_primary_game", "Max primary-game appearances", cap, games),
        setting("max_lineup_overlap", "Max lineup overlap", config.uniqueness_overlap, max_overlap),
        setting("elevated_player_max_exposure", "Elevated-player max exposure", elevated_rate,
                f"{max_elevated_appearances}/{options['num_lineups']} requested entries; category limit {elevated_limit if elevated_limit is not None else 'none'}; stricter player/global limits also apply"),
        setting("max_elevated_players_per_lineup", "Per-lineup elevated max", per_lineup_cap,
                max(elevated_counts, default=0)),
    ]
    failed_steps = [step for step in trace if not step.get("player_ids")]
    feasibility = {"status": "underfilled" if len(rows) != options["num_lineups"] else "complete",
        "no_constraints_relaxed": True,
        "active_constraints": {"max_lineups_per_primary_game": cap, "max_lineup_overlap": config.uniqueness_overlap,
            "max_exposure": options["max_exposure"], "elevated_player_max_exposure": elevated_rate,
            "max_elevated_players_per_lineup": per_lineup_cap},
        "saturated_primary_games": [game for game, count in games.items() if cap is not None and count >= cap],
        "saturated_player_ids": [pid for pid in lookup if exposure[pid] >= appearance_limit(pid)],
        "saturated_overlap_pairs": [{"lineups": [i+1, j+1], "shared_players": len(a & b)}
            for i, a in enumerate(ids) for j, b in enumerate(ids) if i < j and len(a & b) == config.uniqueness_overlap],
        "failed_solver_steps": failed_steps,
        "explanation": "Sequential next-lineup solve could not satisfy the combined active constraints. Saturated budgets are shown; a minimal infeasible constraint set is not proven." if failed_steps else None}
    return {"contract_sha256": contract["sha256"], "execution_mode": contract["execution_mode"],
        "strategy_label": contract["strategy_label"], "deviations": contract["deviations"],
        "requested": contract["requested"], "effective_max_lineups_per_primary_game": cap,
        "sources": contract["sources"], "settings": settings, "feasibility": feasibility,
        "elevated_player_exposures": {pid: {"appearances": exposure[pid], "limit": appearance_limit(pid), "classification": effective.get("risk_classifications", {}).get(pid),
            "user_preference_reason": "explicit_user_elevated_exposure_cap" if elevated_rate is not None else "existing_player_global_caps"} for pid in sorted(elevated_ids)},
        "elevated_players_per_lineup": elevated_counts, "canonical_primary_games": games, "candidate_rosters": rows,
        "selector_objective_total": sum(row["objective_score"] for row in rows),
        "projected_point_sum": sum(row["mean"] for row in rows), "summed_marginal_p90": sum(row["p90"] for row in rows),
        "qb_allocation": dict(Counter(next(p.name for p in lineup if p.position == "QB") for lineup in lineups)),
        "player_exposures": {pid: {"name": lookup[pid].name, "appearances": count, "limit": limits[pid]} for pid, count in sorted(exposure.items())},
        "pairwise_overlap": overlap, "maximum_overlap": max((len(a & b) for a, b in combinations(ids, 2)), default=0),
        "validation": {"status": "verified" if not violations else "failed", "violations": violations},
        "solver_steps": list(trace), "portfolio_optimality": "sequential; joint optimum not proven"}
