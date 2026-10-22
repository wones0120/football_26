"""Opt-in offensive-count comparison; standard optimizer remains unchanged."""
from __future__ import annotations

import hashlib
import json

from .workload_count_forecast import VERSION

RECOMMENDATION_POLICY = "offensive_workload_recommendation_v1"


def learned_recommendation(lineups, *, run_id, season, week, slate, contest_format,
                           projection_run_id, data_cutoff_at, mode="learned_counts"):
    """Native export legality and count ranking, without a scoreability gate."""
    from .gpp_recommendation import candidate_id
    from .draftkings_export import DraftKingsExportService
    report=dict(status='provisional',optimizer_run_id=run_id,
        scope=dict(season=season,week=week,slate=slate,contest_format=contest_format),
        projection_run_id=projection_run_id,data_cutoff_at=str(data_cutoff_at),
        candidates=[],exceptions=[],limitations=['Declared workload utility is not calibrated tournament value.'],
        paid_finish_probability=None,expected_return=None)
    seen=set()
    for index,lineup in enumerate(lineups,1):
        cid=candidate_id(lineup)
        try:
            DraftKingsExportService.build_lineup_download(contest_format=contest_format,lineups=[lineup],run_id=run_id)
            if cid in seen:continue
            seen.add(cid)
            report['candidates'].append(dict(candidate_id=cid,lineup_number=index,
                projected_points=None,marginal_upside_sum=None,salary=sum(float(p['salary']) for p in lineup),
                availability_exceptions=[],paid_finish_probability=None,expected_return=None))
        except ValueError as exc:
            report['exceptions'].append(dict(lineup_number=index,reason=str(exc)))
    if not report['candidates']:report['status']='unavailable'
    return recommendation(report,lineups,mode)


def recommendation(report, lineups, mode):
    """Reuse export legality audit, replace FP-based ranking explicitly."""
    report.update(policy_id=RECOMMENDATION_POLICY, goal="offensive_workload_comparison",
        selection_basis=mode, reason="Highest declared workload objective; full fantasy projections are report-only. Yard weights use partial DK yard scoring when selected. Canonical identity breaks utility ties.")
    for candidate in report["candidates"]:
        lineup = lineups[candidate["lineup_number"]-1]
        candidate["workload_utility"] = sum((float(r["base_projection"]) if mode == "offensive_mean_control"
            else float(r["workload_forecast"]["utility"])) * (1.5 if r.get("roster_position") == "CPT" else 1.) for r in lineup)
    report["candidates"].sort(key=lambda r:(-r["workload_utility"], r["candidate_id"]))
    for rank, candidate in enumerate(report["candidates"], 1):
        candidate["rank"] = rank
    report["recommended"] = dict(report["candidates"][0]) if report["candidates"] else None
    if mode=='scenario_first':
        report.update(goal='scenario_first_captain',reason='Market spread and total define the primary scenario. Only market-centered complete-roster case coverage selects the lineup; primary mean relative capture breaks ties. Alternative scripts are diagnostic only. Worst-case capture is diagnostic only. Case likelihood and tournament performance are unknown.')
        report['limitations'].insert(0,'Supported offense and sourced starting kickers; conditional scoring cases, not calibrated full-game forecasts. Individual case means are display only; whole-roster coverage is primary and mean relative capture is the explicit tie-break.')
        return report
    report["limitations"].insert(0, "Offensive-only supported forecast domain; not a validated tournament recommendation. K/DST and unknown workloads are outside this comparison; no standard projections changed.")
    return report


def solve(service, pool, *, params, contest_type, stack_params, locked_ids,
          flex_only_ids, avoid_dst_opponents, enforce_single_te, requested_captain_id):
    receipt = (params.get("prepared_input_evidence") or {}).get("workload_forecast")
    if contest_type != "captain":
        raise ValueError("Initial operational workload comparison supports Captain only; shared count producer also supports Classic inputs")
    if not receipt or receipt.get("version") != VERSION:
        raise ValueError("Explicit workload comparison requires a supported frozen Prepare forecast receipt")
    expected_hash = hashlib.sha256(json.dumps({k:v for k,v in receipt.items() if k != "sha256"},
        sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    if receipt.get("sha256") != expected_hash:
        raise ValueError("Prepared workload forecast checksum mismatch")
    mode = params.get("workload_comparison")
    if mode not in {"normalized_counts", "offensive_mean_control", "learned_counts", "learned_yards", "scenario_first"}:
        raise ValueError("Unknown workload comparison objective")
    if bool(receipt.get('yardage_model')) != (mode in {'learned_yards','scenario_first'}):
        raise ValueError('Prepare again for the selected learned count/yard objective; no receipt substitution')
    if bool(receipt.get('scenario_first')) != (mode=='scenario_first'):
        raise ValueError('Prepare again for selected scenario-first objective; no receipt substitution')
    if mode in {'learned_counts','learned_yards','scenario_first'}:
        if not receipt.get('learned_opportunities') or not receipt.get('learned_model_consumption'):
            raise ValueError('Prepare the latest learned opportunity forecasts first; no reference-count fallback')
        if mode=='learned_yards':
            from .opportunity_yards import VERSION as YARD_VERSION, WEIGHTS
            if receipt['yardage_model'].get('version')!=YARD_VERSION or receipt['yardage_model'].get('selection_weights')!=WEIGHTS:
                raise ValueError('Unsupported yardage model or selection weights; Prepare again')
        if params.get('require_team_leader') or params.get('require_home_team_leader'):
            raise ValueError('Learned opportunities cannot use points-based team leader requirements')
    unsupported = ("max_lineup_overlap", "minimum_uniqueness", "max_elevated_players_per_lineup",
                   "elevated_player_max_exposure", "portfolio_constraints", "minimum_player_exposure",
                   "minimum_exposure_by_player")
    if any(params.get(key) is not None for key in unsupported) or params.get("min_exposure"):
        raise ValueError("Workload comparison does not yet support explicit overlap/minimum/elevated portfolio controls; no setting was relaxed")
    if mode=='scenario_first':
        from .captain_case_selection import solve as solve_cases
        return solve_cases(service,pool,receipt=receipt,params=params,contest_type=contest_type,stack_params=stack_params,
            locked_ids=locked_ids,flex_only_ids=flex_only_ids,avoid_dst_opponents=avoid_dst_opponents,
            enforce_single_te=enforce_single_te,requested_captain_id=requested_captain_id)
    by_id = {r["player_master_id"]: r for r in receipt["players"]}
    frame = pool.copy()
    excluded = []
    for index, row in frame.iterrows():
        forecast = by_id.get(str(row["player_id"]))
        if forecast is None or forecast.get("utility") is None:
            excluded.append({"player_id": str(row["player_id"]), "name": row.get("name"),
                "reasons": (forecast or {}).get("reasons") or ["unknown forecasts"],
                "original_projection": row.get("projection")})
            frame.loc[index, "workload_utility"] = float("nan")
            continue
        frame.loc[index, "workload_utility"] = forecast["utility"]
    frame = frame.loc[frame.workload_utility.notna()].sort_values("player_id").reset_index(drop=True)
    if set(locked_ids) - set(frame.player_id.astype(str)):
        raise ValueError("Locked actor lacks a supported offensive count forecast; constraints were not relaxed")
    for index, row in frame.iterrows():
        frame.at[index, "workload_utility"] = (float(row["projection"]) if mode == "offensive_mean_control"
                                                  else float(row["workload_utility"]))
    requested = int(params.get("num_lineups", 1))
    from .classic_portfolio_controls import explicit_appearance_limit
    def rate(value):
        value = float(value)
        value = value/100 if value > 1 else value
        if not 0 <= value <= 1:
            raise ValueError("Workload exposure rates must be between0 and1")
        return value
    exposure = rate(params.get("max_exposure", 1))
    cap_rate = rate(params.get("captain_max_exposure", 1))
    player_limits = {}
    for row in frame.to_dict("records"):
        key = "core_player_max_exposure"
        if row["position"] == "QB" and row.get("showdown_qb_eligible"):
            key = "starting_qb_max_exposure"
        elif float(row["salary"]) <= 1000:
            key = "cheap_punt_max_exposure"
        effective_rate = min(exposure, rate(params.get(key, 1)),
            rate((params.get("maximum_exposure_by_player") or {}).get(str(row["player_id"]), 1)))
        player_limits[str(row["player_id"])] = explicit_appearance_limit(requested, effective_rate)
    used = {}; caps = {}; signatures = []; results = []; solve_audits = []
    for _ in range(requested):
        solve_audit = {}
        lineup = service._solve_lineup(frame, score_col="workload_utility",
            exposure_remaining={str(p): player_limits[str(p)]-used.get(str(p), 0) for p in frame.player_id},
            captain_exposure_remaining={str(p): explicit_appearance_limit(requested,cap_rate)-caps.get(str(p), 0) for p in frame.player_id},
            exclude_signatures=signatures, contest_type=contest_type,
            stack_params={**stack_params, "offensive_workload": True,
                **({'learned_opportunity_audit':solve_audit} if mode in {'learned_counts','learned_yards'} else {})},
            locked_player_ids=locked_ids, flex_only_player_ids=flex_only_ids,
            locked_captain_player_id=requested_captain_id,
            avoid_dst_opponents=avoid_dst_opponents, enforce_single_te=enforce_single_te,
            rule_profile=None, include_control_comparison=False)
        if mode in {'learned_counts','learned_yards'}:
            solve_audit.update(full_fantasy_projection_in_objective=False,
                partial_dk_yard_scoring_in_objective=mode=='learned_yards',
                selection_weights=receipt.get('yardage_model',{}).get('selection_weights'))
            solve_audits.append(solve_audit)
        if not lineup:
            break
        for row in lineup:
            pid = str(row["player_id"]); used[pid] = used.get(pid, 0)+1
            if row.get("roster_position") == "CPT":
                caps[pid] = caps.get(pid, 0)+1
            row["workload_forecast"] = by_id[pid]
            row["workload_forecast_sha256"] = receipt["sha256"]
        signatures.append([(str(r["player_id"]), r.get("roster_position")) for r in lineup])
        results.append(lineup)
    report = {"version": "offensive_workload_optimizer_v1", "mode": mode,
        "forecast_sha256": receipt["sha256"], "source_cutoff_at": receipt["source_cutoff_at"],
        "requested": requested, "achieved": len(results), "supported_pool": len(frame),
        "excluded_domain_or_unknown": excluded, "captain_counts": caps,
        "selection": "sequential declared-workload-objective lineups under remaining user exposure; no calibrated tournament value",
        "domain": receipt["domain"], "objective": receipt["objective"] if mode != "offensive_mean_control" else "highest FP mean on identical offensive supported domain",
        "learned_model_consumption": receipt.get('learned_model_consumption') if mode in {'learned_counts','learned_yards'} else None,
        "normalization_scales":receipt.get('scales'),
        "yardage_model":receipt.get('yardage_model'),
        "solver_audits":solve_audits,
        "inactive_point_preferences":params.get('inactive_point_preferences',{}),
        "points_selection_gates_consumed":False if mode in {'learned_counts','learned_yards'} else 'legacy qualification only',
        "status": "completed" if len(results) == requested else "failed_underfilled_no_relaxation"}
    invalid_exposure = (any(count > player_limits[pid] for pid,count in used.items())
        or any(count > explicit_appearance_limit(len(results),cap_rate) for count in caps.values()))
    if len(results) != requested or invalid_exposure:
        report["status"] = "failed_underfilled_or_exposure_no_relaxation"
        report["attempted_portfolio"] = [[{"player_id":r["player_id"], "role":r.get("roster_position"),
            "salary":r["salary"]} for r in lineup] for lineup in results]
        report["reason"] = "Requested size not achieved; partial results cannot certify requested or achieved exposure caps and are not downloadable"
        return [], report
    return results, report
