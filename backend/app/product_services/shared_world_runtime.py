"""Prepared common-world generation and exact user-constraint completion.

Conditional point means are sensitivity estimates, not independent events or
calibrated scenario probabilities. No count/P90/ownership bonus is scored.
"""
from copy import deepcopy
import math
import time

import pulp

from .analyst_shadow import digest
from .cbc_solver import make_cbc_solver
from .shared_world_selection import POLICY, MEAN_CONTRACT, ORACLE_SIZE, Limits, _roster, select_shared_world_portfolio

RECOMMENDATION_POLICY = "shared_world_anchor_recommendation_v1"
LEGACY_STACK_RULES = {"showdown_require_starting_qb_v2", "showdown_pass_catcher_captain_qb_v1",
    "showdown_multi_pass_catcher_qb_v2", "showdown_qb_captain_role_stack_v1", "showdown_qb_captain_same_team_wr_te_v1"}


def user_legal_kwargs(kwargs):
    """Omit static strategy constructions, never actual persisted user knobs."""
    result = {**kwargs, "stack_params": dict(kwargs.get("stack_params") or {})}
    for key in ("require_starting_qb", "hard_qb_correlations", "require_qb_captain_receiver"):
        result["stack_params"][key] = False
    return result


def common_packet(packet):
    """Retain supported authored worlds; explicit personal what-ifs stay out."""
    from .analyst_intents import validate_intents
    errors = validate_intents(packet)
    intents = packet.get("optimization_intents") or {}
    if errors or not intents.get("EXPECTED_GAME") or not intents.get("CONTRARIAN"):
        raise ValueError("Shared-world coverage requires valid authored expected and contrary research: " + "; ".join(errors))
    personal = {f["scenario_id"] for f in (packet.get("contrarian_analysis") or {}).get("findings", [])
                if f.get("status") == "user_what_if"}
    authored = set(intents["EXPECTED_GAME"]["scenario_ids"]) | set(intents["CONTRARIAN"]["scenario_ids"])
    result = deepcopy(packet)
    result["scenario_assumptions"]["scenarios"] = [s for s in result["scenario_assumptions"]["scenarios"]
        if s["scenario_id"] in authored and s["scenario_id"] not in personal and not s.get("explicit_user_what_if")]
    retained = {s["scenario_id"] for s in result["scenario_assumptions"]["scenarios"]}
    if not retained & set(intents["CONTRARIAN"]["scenario_ids"]):
        raise ValueError("No supported non-personal contrary world is available")
    # These optional action modules may reference excluded personal stories.
    # Their original evidence stays in the checked parent; they add no hard
    # constructions, quotas or bonuses to this policy.
    for key in ("optimization_intents", "intent_scope", "captain_analysis", "contrarian_analysis",
                "analyst_assessments", "slate_synthesis", "discovery", "weekly_role_review", "defense_kicker_analysis", "team_game_outlook"):
        result.pop(key, None)
    for scenario in result["scenario_assumptions"]["scenarios"]:
        # A descriptive branch tag is not a source-story construction rule.
        # The original tag/outlook remains in parent provenance/world details.
        scenario.pop("team_game_branch", None)
    return result


def common_worlds(packet, scenarios, rows, *, scope, input_sha256):
    """Explicit authored anchor, or a disclosed base-model fallback."""
    intents = packet.get("optimization_intents") or {}
    expected = set((intents.get("EXPECTED_GAME") or {}).get("scenario_ids", []))
    contrary = set((intents.get("CONTRARIAN") or {}).get("scenario_ids", []))
    source = digest(packet)
    original_scenarios = {s["scenario_id"]: s for s in packet["scenario_assumptions"]["scenarios"]} if packet.get("scenario_assumptions") else {}
    hypotheses = {h["hypothesis_id"]: h for h in packet.get("hypotheses", [])}
    means = {str(r["player_id"]): float(r["projection"]) for r in rows}
    worlds = [dict(world_id="base_model_expected", kind="baseline", frozen_scope=scope,
        input_sha256=input_sha256, source_refs=[source, input_sha256],
        mechanism="Unchanged prepared point-forecast means; no scenario adjustment.",
        mean_contract=MEAN_CONTRACT, likelihood="unknown", player_means=means,
        anchor_basis="explicit_base_model_expected")]
    for s in scenarios:
        assessment = intents.get("CONTRARIAN" if s["scenario_id"] in contrary else "EXPECTED_GAME", {})
        worlds.append(dict(world_id=s["scenario_id"], kind="contrary" if s["scenario_id"] in contrary else "conditional",
            frozen_scope=scope, input_sha256=input_sha256, source_refs=[source, *assessment.get("source_ids", []), *s["hypothesis_ids"]],
            mechanism=assessment.get("assessment") or s["label"], label=s["label"],
            supporting_evidence=deepcopy(assessment.get("supporting_evidence", [])),
            counterevidence=deepcopy(assessment.get("counterevidence", [])), unknowns=deepcopy(assessment.get("unknowns", [])),
            declared_assumptions=deepcopy(original_scenarios.get(s["scenario_id"], {}).get("assumptions", [])),
            original_team_game_branch=original_scenarios.get(s["scenario_id"], {}).get("team_game_branch"),
            hypothesis_evidence=[deepcopy(hypotheses[h]) for h in s["hypothesis_ids"] if h in hypotheses],
            conditional_response_lineage={pid: deepcopy(m.get("changes", [])) for pid, m in s["moments"].items()},
            count_component_response=deepcopy(s.get("count_component_response")),
            mean_contract=MEAN_CONTRACT, conditional_response_contract="frozen_base_plus_matched_linear_component_delta_v1" if s.get("count_component_response") else None, likelihood="unknown",
            player_means={pid: float(m["mean"]) for pid, m in s["moments"].items()},
            **({"anchor_basis": "authored_EXPECTED_GAME"} if s["scenario_id"] in expected else {})))
    supported_expected = [w["world_id"] for w in worlds if w["world_id"] in expected]
    anchor = supported_expected[0] if len(supported_expected) == 1 else "base_model_expected"
    reason = ("Unique supported authored Expected Game world" if len(supported_expected) == 1 else
              "No unique supported authored expected anchor; explicitly use unchanged base-model mean, not a first-world guess or average")
    if not any(w["kind"] == "contrary" for w in worlds):
        raise ValueError("Shared-world coverage has no supported contrary world")
    return worlds, anchor, reason


def _bounded_solver(seconds):
    solver = make_cbc_solver()
    solver.timeLimit = max(.01, seconds)
    solver.threads = 1
    solver.options.extend(["randomSeed 7", "randomCbcSeed 7"])
    return solver


def completion_oracle(candidates, rows, *, requested, params, fmt):
    """Reuse the exact existing portfolio model, with exact requested size."""
    from .analyst_scenarios import candidate_portfolio_model
    ids = [digest(_roster(c, fmt.lower())[0]) for c in candidates]
    if len(set(ids)) != len(ids):
        raise ValueError("Completion oracle requires canonical roster deduplication")
    model, variables = candidate_portfolio_model(candidates, rows, requested=requested, params=params, fmt=fmt)
    model += pulp.lpSum(variables.values()) == requested, "exact_requested_portfolio"
    fingerprint = digest(dict(model=model.toDict(), candidate_ids=ids, requested=requested))
    target = requested
    def feasible(*, prefix_ids, remaining_ids, requested, deadline):
        if requested != target:
            raise ValueError("Completion oracle requested portfolio size changed")
        known = set(ids)
        if set(prefix_ids) | set(remaining_ids) != known or set(prefix_ids) & set(remaining_ids):
            raise ValueError("Completion oracle candidate universe changed")
        seconds = deadline - time.monotonic()
        common = dict(constraint_sha256=fingerprint, target_size=requested,
                      achieved_size_semantics=ORACLE_SIZE)
        if seconds <= 0:
            return dict(common, status="timeout", proof="Completion deadline exhausted")
        solver_vars, copy = pulp.LpProblem.fromDict(deepcopy(model.toDict()))
        for i, cid in enumerate(ids):
            if cid in prefix_ids:
                copy += solver_vars[variables[i].name] == 1
        copy.setObjective(pulp.lpSum(solver_vars[variables[i].name] for i in variables))
        copy.solve(_bounded_solver(seconds))
        proven = copy.status == pulp.LpStatusOptimal and copy.sol_status == pulp.LpSolutionOptimal and copy.valid(1e-6)
        selected = [ids[i] for i in variables if (pulp.value(solver_vars[variables[i].name]) or 0) > .5]
        if proven and len(selected) == requested:
            return dict(common, status="feasible", feasible_completion_size=requested,
                proof=dict(solver_status="Optimal", selected_canonical_ids=selected, exact_size=True, constraints_relaxed=False))
        return dict(common, status="infeasible" if copy.status == pulp.LpStatusInfeasible else "timeout",
                    proof=dict(solver_status=pulp.LpStatus[copy.status], exact_size=True, constraints_relaxed=False))
    return feasible, fingerprint


def generate_and_select(snapshot, rows, worlds, *, anchor_world_id, requested, params, fmt,
                        generation_seconds=60., max_candidates=96):
    """Mean-only world/Captain searches in copies of the captured legal model."""
    if not 0 < generation_seconds <= 60 or not 1 <= max_candidates <= 96:
        raise ValueError("Shared-world generation bounds exceed the supported contract")
    start = time.monotonic(); deadline = start + generation_seconds
    mapping = snapshot["variable_players"]
    by_id = {str(r["player_id"]): r for r in rows}
    scope = worlds[0]["frozen_scope"]; input_sha = worlds[0]["input_sha256"]
    anchor = next(w for w in worlds if w["world_id"] == anchor_world_id)
    ordered = [anchor, *[w for w in worlds if w is not anchor]]
    candidates = {}; attempts = []; anchor_proven = False
    captains = sorted({ref["player_master_id"] for ref in mapping.values() if ref["role"] == "CPT"
        and by_id[ref["player_master_id"]].get("showdown_captain_shortlisted")}) if fmt == "SHOWDOWN" else []
    # Reserve a first unconstrained search for every world before spending
    # work on Captain families or additional variants. All calls share bounds.
    families = [(world, None) for world in ordered] + [(world, captain) for captain in captains for world in ordered]
    family_seen = {}; exhausted = set(); max_calls = 96
    for variant in range(min(3, requested)):
        for world, captain in families:
            if len(candidates) >= max_candidates or len(attempts) >= max_calls or time.monotonic() >= deadline:
                break
            key = (world["world_id"], captain)
            if key in exhausted:
                continue
            variables, model = pulp.LpProblem.fromDict(deepcopy(snapshot["model"]))
            if captain:
                variable = next(n for n, ref in mapping.items() if ref["role"] == "CPT" and ref["player_master_id"] == captain)
                model += variables[variable] == 1
            for prior in family_seen.get(key, []):
                model += pulp.lpSum(variables[n] for n in prior) <= len(prior) - 1
            model.setObjective(pulp.lpSum(variables[name] * world["player_means"][ref["player_master_id"]]
                * (1.5 if ref["role"] == "CPT" else 1) for name, ref in mapping.items()))
            model.solve(_bounded_solver(min(2., deadline - time.monotonic())))
            proven = model.status == pulp.LpStatusOptimal and model.sol_status == pulp.LpSolutionOptimal and model.valid(1e-6)
            attempts.append(dict(world_id=world["world_id"], captain_player_master_id=captain,
                variant=variant, solver_status=pulp.LpStatus[model.status], optimality_proven=proven))
            if not proven:
                exhausted.add(key)
                continue
            if world is anchor and captain is None and variant == 0:
                anchor_proven = True
            chosen = [n for n in mapping if (pulp.value(variables[n]) or 0) > .5]
            family_seen.setdefault(key, []).append(chosen)
            roster = [{**mapping[n], "salary": float(by_id[mapping[n]["player_master_id"]].get("base_salary", by_id[mapping[n]["player_master_id"]]["salary"]))
                * (1.5 if mapping[n]["role"] == "CPT" else 1)} for n in chosen]
            signature = _roster(dict(roster=roster), fmt.lower())[0]
            cid = digest(signature)
            record = candidates.setdefault(cid, dict(candidate_id=cid, roster=roster, scenario_ids=[], input_sha256=input_sha, frozen_scope=scope))
            if world["world_id"] not in record["scenario_ids"]:
                record["scenario_ids"].append(world["world_id"])
    if not anchor_proven:
        return [], dict(policy_id=POLICY, status="unproven_anchor", requested=requested, achieved=0,
                        generation=attempts, constraints_relaxed=False)
    pool = list(candidates.values())
    generation_elapsed = time.monotonic() - start
    oracle, fingerprint = completion_oracle(pool, rows, requested=requested, params=params, fmt=fmt)
    selected, report = select_shared_world_portfolio(pool, worlds,
        base_player_means={pid: float(r["projection"]) for pid, r in by_id.items()}, requested=requested,
        completion_feasible=oracle, anchor_world_id=anchor_world_id,
        limits=Limits(max_candidates=max_candidates, wall_seconds=10.))
    # Preserve the selector's anchor-first order, never insertion/FP rank.
    ordered_selected = []
    for item in selected:
        record = deepcopy(candidates[item["canonical_id"]])
        record["shared_world_evaluation"] = item
        ordered_selected.append(record)
    report.update(generation=attempts, generation_limits=dict(seconds=generation_seconds, max_candidates=max_candidates, max_solver_calls=max_calls),
                  generation_elapsed_seconds=generation_elapsed, selection_elapsed_seconds=time.monotonic() - start - generation_elapsed,
                  anchor_mean_optimality_proven=anchor_proven,
                  candidate_pool=pool, constraint_sha256=fingerprint, constraints_relaxed=False)
    report["generation_world_coverage"] = [dict(world_id=w["world_id"],
        attempted=sum(a["world_id"]==w["world_id"] for a in attempts),
        optimal_searches=sum(a["world_id"]==w["world_id"] and a["optimality_proven"] for a in attempts),
        status="searched" if any(a["world_id"]==w["world_id"] for a in attempts) else "unattempted_within_bounds") for w in ordered]
    report.update(feasibility_scope="bounded_generated_candidate_pool_only",
        full_legal_model_completion="feasible" if selected else "unknown; pool failure does not prove original full-model infeasibility")
    if report["status"] == "infeasible_requested_portfolio":
        report.update(status="candidate_pool_infeasible",
            completion_status="This bounded candidate pool cannot complete the requested portfolio; original full legal-model completion is unknown. No constraints relaxed.")
    return ordered_selected, report


def explain_rosters(selection, worlds, rows):
    """Describe frozen football dependencies without adding scores or probabilities."""
    lookup = {str(r.get("player_id") or r.get("player_master_id")): r for r in rows}
    steps = selection.get("selection_steps", [])
    def actor(p):
        row = lookup.get(p["player_master_id"], {})
        proof = row.get("current_role_evidence") or row.get("pregame_context_role_evidence") or row.get("role_starter_evidence")
        role_sources = {key: deepcopy(row[key]) for key in ("role_source", "role_source_ids", "role_observed_at", "starter_qb_evidence_tier", "role_confidence") if row.get(key) is not None}
        return dict(player_master_id=p["player_master_id"], role=p["role"],
            name=row.get("name") or row.get("player_name") or p["player_master_id"],
            team=row.get("player_team") or row.get("team"), position=row.get("position"),
            current_role=row.get("canonical_role") or row.get("pregame_role") or row.get("role"),
            role_evidence=deepcopy(proof), role_source_lineage=role_sources,
            role_evidence_status="available_as_captured_not_upgraded" if proof or role_sources else "not_present_in_frozen_row")
    for step in steps:
        ids = {p["player_master_id"] for p in step["roster"]}
        target_ids = ([selection["anchor_world_id"]] if step["rank"] == 1 or not step["target_world_ids"] else step["target_world_ids"])
        step["football_paths"] = [dict(world_id=w["world_id"], mechanism=w["mechanism"],
            supporting_evidence=w.get("supporting_evidence", []), counterevidence=w.get("counterevidence", []),
            unknowns=w.get("unknowns", []), source_refs=w.get("source_refs", [])) for w in worlds if w["world_id"] in target_ids]
        step["roster_roles"] = [actor(p) for p in step["roster"]]
        shared = [p for p in step["roster"] if any(p["player_master_id"] in {r["player_master_id"] for r in other["roster"]} for other in steps if other is not step)]
        step["shared_actor_dependencies"] = [actor(p) for p in shared]
        teams = {}
        for p in step["roster_roles"]:
            teams.setdefault(p["team"] or "unknown", []).append(p)
        step["team_role_couplings"] = [dict(team=team, actors=actors,
            interpretation="These roster slots share team scoring and possession opportunities; passers and receivers may credit the same passing event. No independent-event or probability claim.") for team, actors in teams.items() if len(actors)>1]
        step["shared_risk"] = ("Shared actors across saved entries: " + ", ".join(str(p["name"]) for p in step["shared_actor_dependencies"]) + ". Their role or team-production shortfalls affect multiple entries; conditional likelihood is unknown.") if shared else "No shared actors across saved entries; common game and team outcome dependencies still remain. Likelihood unknown."
        alternative = step.get("strongest_admissible_alternative")
        if alternative:
            alt_ids = {p["player_master_id"] for p in alternative["roster"]}
            alternative["entering_actors"] = [actor(p) for p in step["roster"] if p["player_master_id"] not in alt_ids]
            alternative["leaving_actors"] = [actor(p) for p in alternative["roster"] if p["player_master_id"] not in ids]
            alternative["selected_minus_alternative_salary"] = step["salary"] - alternative["salary"]


def run_prepared(service, pool, *, kwargs, snapshot, rows, packet, scenarios, params, fmt,
                 requested, focus, distribution_exclusions, original_rows):
    """Actual prepared solver consumer; exact replay restores original FP rows."""
    from .analyst_scenarios import _research_explanations
    scope = {"contest_format": fmt.lower(), **{k: snapshot["scope"][k] for k in ("season", "week")},
             "slate": snapshot["scope"]["slate_id"]}
    worlds, anchor, reason = common_worlds(packet, scenarios, rows, scope=scope, input_sha256=snapshot["sha256"])
    selected, selection = generate_and_select(snapshot, rows, worlds, anchor_world_id=anchor,
        requested=requested, params=params, fmt=fmt)
    explain_rosters(selection, worlds, original_rows)
    lineups = []
    for index, candidate in enumerate(selected):
        replay = {**kwargs, "locked_player_ids": {p["player_master_id"] for p in candidate["roster"]}}
        if fmt == "SHOWDOWN":
            replay["locked_captain_player_id"] = next(p["player_master_id"] for p in candidate["roster"] if p["role"] == "CPT")
        lineup = service._solve_lineup(pool, **replay)
        if not lineup:
            raise ValueError("Shared-world candidate failed exact unchanged legal replay")
        original = {str(r["player_id"]): r for r in rows}
        for player in lineup:
            tail = original[str(player["player_id"])].get("p90")
            if type(tail) not in (int, float) or not math.isfinite(tail) or tail < 0:
                # The legacy renderer uses safe_float for optional tails. That
                # must not turn this mean-only policy's missing tail into0.
                player.update(base_p90=None, p90=None, showdown_captain_p90=None,
                              tail_status="unavailable_not_imputed")
        lineup.sort(key=lambda r: (r.get("roster_position") != "CPT", str(r["player_id"])))
        step = deepcopy(selection["selection_steps"][index])
        lineup[0].update(analyst_strategy="MERGED_SCENARIOS", analyst_thesis_ids=candidate["scenario_ids"],
            analyst_packet_sha256=digest(packet), analyst_selection_policy=POLICY,
            shared_world_lineup=step, shared_world_selection_rank=index + 1,
            analyst_scenario_scores={w["world_id"]: sum(w["player_means"][p["player_master_id"]] * (1.5 if p["role"] == "CPT" else 1)
                                    for p in candidate["roster"]) for w in worlds})
        lineups.append(lineup)
    selection.update(anchor_selection_reason=reason,
        user_controls={key:deepcopy(params.get(key)) for key in ('num_lineups','max_exposure','captain_max_exposure',
            'captain_positions','captain_position_exception_ids','minimum_player_salary','max_players_per_team','max_players_per_game',
            'exclude_questionable','questionable_eligible_player_ids','no_qbs','no_qb_captain','no_two_qbs','avoid_dst_opponents',
            'require_team_leader','require_home_team_leader','locked_player_ids','exclude_player_ids','flex_only_player_ids',
            'maximum_exposure_by_player','minimum_exposure_by_player','max_lineup_overlap','minimum_uniqueness')},
        retained_user_construction_rules=deepcopy(params.get("optimizer_rules", [])),
        omitted_strategy_construction_rules=deepcopy(params.get("shared_world_omitted_strategy_rules", [])),
        count_forecast_consumption="No additive workload score; count evidence can support authored mechanisms but is not a second FP contribution",
        absent_count_receipt="unconsumed" if not params.get("workload_forecast") else "referenced_only_not_additive")
    report = dict(mode="MERGED_SCENARIOS", selection_policy=POLICY, shared_world_selection=selection,
        status="completed" if len(lineups) == requested else "blocked", focus=focus, seed=7,
        packet_sha256=digest(packet), input_snapshot=snapshot, input_snapshot_sha256=snapshot["sha256"],
        candidates=selection.get("candidate_pool", []), generation=selection.get("generation", []),
        generated_candidate_count=len(selection.get("candidate_pool", [])), selected_lineup_count=len(lineups),
        requested_portfolio_size=requested, achieved_portfolio_size=len(lineups),
        quality_screen="none", baseline_veto=False, scenario_definitions=scenarios,
        selection=dict(requested=requested, achieved=len(lineups),
            solver_status="Optimal" if len(lineups) == requested else selection["status"],
            constraints_relaxed=False, selection_reason=selection.get("objective")),
        projection_distribution_eligibility=dict(original_input_sha256=digest(original_rows),
            original_input_rows=original_rows, excluded=deepcopy(distribution_exclusions)),
        mathematical_assumptions=dict(objective=selection.get("objective"),
            probability="Conditional likelihood unknown; no equal-probability weights, payout estimate or summed marginal P90",
            opportunity="Existing declared common-world response lineage; full-roster means scored once, Captain1.5 changes FP only",
            legacy_construction="No source-story stacks, hero/top-four restoration, allocation quotas or teammate penalty added; explicit existing user rules retained"))
    _research_explanations(report, lineups, params)
    return lineups, report


def recommendation(report, lineups, selection):
    """Keep the actual anchor-first policy order through saved/exported picks."""
    if selection.get("policy_id") != POLICY or selection.get("status") != "completed" or len(lineups) != selection.get("requested"):
        raise ValueError("Shared-world recommendation requires its complete frozen portfolio receipt")
    out = deepcopy(report)
    by_number = {c["lineup_number"]: c for c in out["candidates"]}
    if set(by_number) != set(range(1, len(lineups) + 1)):
        raise ValueError("Shared-world recommendation has unvalidated or duplicated saved rosters")
    for index, lineup in enumerate(lineups, 1):
        if lineup[0].get("shared_world_selection_rank") != index:
            raise ValueError("Shared-world saved order differs from frozen selection")
        by_number[index]["rank"] = index
        step = selection["selection_steps"][index - 1]
        by_number[index]["anchor_conditional_mean_points"] = step["anchor_conditional_mean_points"]
        by_number[index]["incremental_world_gain_points"] = step["maximum_incremental_gain_points"]
    out.update(policy_id=RECOMMENDATION_POLICY, selection_basis=POLICY,
        goal="expected_anchor_and_supported_conditional_coverage", candidates=[by_number[i] for i in sorted(by_number)],
        recommended=deepcopy(by_number[1]), shared_world_selection_sha256=digest(selection),
        reason="First completion-proven expected-anchor lineup; subsequent saved entries add common conditional-world coverage where supported. Original FP/P90 does not rerank this policy.",
        limitations=["World likelihoods, paid-finish probability and payout EV are unknown.",
            "Conditional means are sourced sensitivity estimates; no marginal P90 sum is optimized or claimed to be a lineup percentile.",
            "Candidate generation and exact-size completion are bounded; no tournament superiority or final game dressing is asserted."])
    return out
