"""Exact Classic baseline-mean selection; optional correlation and no player locks."""
import math

import pandas as pd
import pulp

OBJECTIVE = "baseline_mean"
POLICY_ID = "classic_highest_baseline_mean_optional_stacks_v1"


def normalize_request(params, *, contest_format, strategy):
    selected = params.get("classic_selection_objective")
    if selected is None:
        return False
    if selected != OBJECTIVE:
        raise ValueError("Unknown Classic selection objective")
    if contest_format != "classic" or strategy != "classic_large_gpp_v1":
        raise ValueError("Highest projection requires Classic Large GPP")
    if any(params.get(key) for key in ("locked_player_ids", "lock_player_ids", "locked_players", "locked_captain_player_id")):
        raise ValueError("Highest projection requires no player locks; clear locks first")
    if any(float(value) > 0 for value in (params.get("minimum_exposure_by_player") or {}).values()):
        raise ValueError("Highest projection cannot retain minimum-exposure player locks")
    if params.get("long_shot_mode"):
        raise ValueError("Highest projection cannot use long-shot scoring")
    # Selection objective is explicit and independent of Analyst annotation/intent.
    for key in tuple(params):
        if key.startswith("analyst_"):
            params.pop(key)
    params.update(analyst_handoff_mode="BASELINE", analyst_optimization_intent="MIXED", num_lineups=1)
    return True


def stack_policy():
    return dict(policy_id=POLICY_ID, contest_format="classic", objective="gpp", enabled=False,
                stack_min=0, stack_max=None, bringback=False, include_rb_in_stack=False,
                bringback_positions=[], source="explicit_selection_objective",
                description="Highest baseline projection; stacks and opponent bringbacks optional.")


def solve(service, pool, *, params, cutoff=None, locked_ids=(), excluded_qb_ids=()):
    """One exact solve. Internal research locks are explicit in the returned audit.

    The public mode rejects locks. Internal matched controls can use this helper
    directly; they cannot be mistaken for the unlocked public optimum.
    """
    from .analyst_shadow import digest
    from .optimizer import _json_safe
    from .single_lineup import elevated_player
    from .classic_portfolio_controls import explicit_appearance_limit

    frame = pool.copy(deep=True)
    values = pd.to_numeric(frame["projection"], errors="coerce")
    valid = values.map(lambda value: pd.notna(value) and math.isfinite(float(value)))
    missing = frame.loc[~valid, "player_id"].astype(str).tolist()
    frame = frame.loc[valid].copy().reset_index(drop=True)
    if frame.empty:
        return [], dict(policy_id=POLICY_ID, solver_status="Not Solved", reason="No finite baseline projections")
    if not set(locked_ids) <= set(frame["player_id"].astype(str)):
        raise ValueError("Research lock is outside the exact eligible baseline-mean pool")
    captured = {}
    def exact_objective(model, rows, variables):
        model.setObjective(pulp.lpSum(float(rows.loc[i, "projection"]) * variables[i] for i in rows.index))
        for i in rows.index:
            pid = str(rows.loc[i, "player_id"])
            if pid in set(excluded_qb_ids):
                model += variables[i] == 0, f"research_excluded_qb_{i}"
            rate = (params.get("maximum_exposure_by_player") or {}).get(pid)
            if rate is not None and explicit_appearance_limit(1, float(rate)) == 0:
                model += variables[i] == 0, f"user_player_maximum_{i}"
            elevated_rate = params.get("elevated_player_max_exposure")
            if elevated_rate is not None and explicit_appearance_limit(1, float(elevated_rate)) == 0 and elevated_player(rows.loc[i], cutoff):
                model += variables[i] == 0, f"user_elevated_maximum_{i}"
        captured.update(model=model, rows=rows.copy(deep=True), variables=variables)
    settings = {**stack_policy(), "correlation_bonus": 0,
                "single_lineup_user_controls": {key: params[key] for key in
                    ("max_players_per_team", "max_players_per_game", "max_elevated_players_per_lineup") if params.get(key) is not None},
                "single_lineup_cutoff": cutoff}
    lineup = service._solve_lineup(frame, score_col="projection", contest_type="tournament", stack_params=settings,
        locked_player_ids=set(locked_ids), enforce_single_te=bool(params.get("enforce_single_te", False)),
        avoid_dst_opponents=bool(params.get("avoid_dst_opponents", False)), rule_profile=None,
        include_control_comparison=False, quality_floor=None, additional_constraints=exact_objective)
    model = captured.get("model")
    status = pulp.LpStatus[model.status] if model is not None else "Not Solved"
    rows = _json_safe(captured["rows"].to_dict("records")) if model is not None else []
    frozen = dict(players=rows, model=_json_safe(model.toDict()) if model is not None else None,
                  variable_players={var.name: str(captured["rows"].loc[i, "player_id"]) for i, var in captured.get("variables", {}).items()})
    audit = dict(policy_id=POLICY_ID, objective_id=OBJECTIVE, objective_label="Highest baseline projection",
        objective_definition="sum unchanged baseline player means", solver_status=status,
        solution_status=pulp.LpSolution.get(model.sol_status) if model is not None else None,
        optimal=status == "Optimal", eligible_player_count=len(frame), missing_projection_player_ids=missing,
        locked_player_ids=sorted(locked_ids), excluded_qb_ids=sorted(excluded_qb_ids),
        hard_qb_stack=False, mandatory_opponent_bringback=False, generated_scenario_constraints=False,
        ownership_weight=0, ceiling_weight=0, correlation_bonus=0, conditional_adjustments=False,
        constraints_relaxed=False, input_snapshot=frozen, input_snapshot_sha256=digest(frozen))
    if lineup:
        assert model is not None and model.valid(1e-5)
        total = sum(float(player["projection"]) for player in lineup)
        assert abs(total - pulp.value(model.objective)) < 1e-6
        audit.update(base_mean=total, salary=sum(float(player["salary"]) for player in lineup))
        for player in lineup:
            player.update(selection_objective=OBJECTIVE, selection_policy_id=POLICY_ID,
                          roster_position=player.get("position"), solver_scoring_policy=POLICY_ID)
        lineup[0]["highest_projection_report"] = {key: value for key, value in audit.items() if key != "input_snapshot"}
    return ([lineup] if lineup else []), audit
