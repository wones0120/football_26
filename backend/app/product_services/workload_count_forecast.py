"""Explicit next-game offensive count forecasts.

No fantasy-point inputs. Team budgets are learned from prior team games; player
shares are a declared same-team lagged-role baseline. Missing actors retain an
unallocated residual. Preferences never enter this producer.
"""
from __future__ import annotations

import hashlib
import json
import math

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from Database.player_identity import normalize_position
from .opportunity_history_evidence import (
    build_history_evidence, select_role_window, source_history, team_history,
)

VERSION = "offensive_count_forecast_v1"
POSITIONS = {"QB", "RB", "WR", "TE"}
CHANNELS = ("pass_attempts", "rush_attempts", "targets")
FEATURES = ("pass_mean3", "pass_mean8", "rush_mean3", "rush_mean8")


def finite(value):
    if isinstance(value,(bool,np.bool_)):return None
    try:
        value = float(value)
        return value if math.isfinite(value) and value >= 0 else None
    except (TypeError, ValueError):
        return None


def signed_finite(value):
    """Observed yard numerators may be negative; missing is never zero."""
    if isinstance(value,(bool,np.bool_)):return None
    try:
        number=float(value)
        return number if math.isfinite(number) else None
    except (TypeError,ValueError):return None


def verified_current_role(source, *, cutoff):
    """Current canonical resolved role, independent of salary/user eligibility."""
    from .factual_designation import clock
    from .player_pool_safety import DEFAULT_CONTEXT_MAX_AGE
    evidence=source.get("role_starter_evidence") or {}
    try:
        observed=clock(evidence["observed_at"]);received=clock(evidence["received_at"])
        decision=clock(cutoff)
    except (KeyError,TypeError,ValueError):return None
    if (evidence.get("player_id")!=str(source.get("player_id"))
            or evidence.get("team")!=(source.get("player_team") or source.get("team"))
            or normalize_position(evidence.get("position"))!=normalize_position(source.get("position"))
            or source.get("canonical_role") not in {"expected_starter","expected_backup","rotational"}
            or evidence.get("role")!=source.get("canonical_role")
            or source.get("role_optimizer_eligible") is False or source.get("pregame_role_uncertain")
            or source.get("role_availability") not in {"rostered","active"}
            or not evidence.get("source_ids") or not evidence.get("source_uri")
            or observed>received or received>decision or decision-observed>DEFAULT_CONTEXT_MAX_AGE):return None
    return evidence


def team_games(weekly):
    """Full source universe, never the salary/optimizer-selected subset."""
    normalized = weekly.copy()
    normalized["position"] = normalized.position.map(normalize_position)
    return team_history(normalized)


def _features(history):
    if len(history) < 3:
        return None
    recent = history.tail(8)
    if recent[["pass_attempts", "rush_attempts"]].isna().any().any():
        return None
    return [float(history.tail(n)[field].mean())
            for field, n in (("pass_attempts", 3), ("pass_attempts", 8),
                             ("rush_attempts", 3), ("rush_attempts", 8))]


def fit_team_model(games, *, before_period):
    """Two tiny fixed Ridge fits; metadata is sufficient for exact inference."""
    training = []
    prior = games.loc[games.period < before_period]
    for _, rows in prior.groupby("team", sort=True):
        rows = rows.sort_values("period")
        for offset in range(3, len(rows)):
            x = _features(rows.iloc[:offset])
            y = rows.iloc[offset]
            if x is not None and pd.notna(y.pass_attempts) and pd.notna(y.rush_attempts):
                training.append((x, [float(y.pass_attempts), float(y.rush_attempts)], int(y.period)))
    if len(training) < 100:
        raise ValueError("Workload forecasts require 100 complete prior team-game examples")
    x = np.asarray([row[0] for row in training]); y = np.asarray([row[1] for row in training])
    center = x.mean(axis=0); scale = x.std(axis=0); scale[scale == 0] = 1
    model = Ridge(alpha=30.0).fit((x-center)/scale, y)
    receipt = {"version": VERSION, "method": "standardized_ridge_alpha30_prior_team_games",
               "feature_columns": list(FEATURES), "center": center.tolist(), "scale": scale.tolist(),
               "coefficients": model.coef_.tolist(), "intercept": model.intercept_.tolist(),
               "training_rows": len(training), "training_max_period": max(row[2] for row in training),
               "before_period": before_period,
               "training_sha256": hashlib.sha256(json.dumps(training).encode()).hexdigest(),
               "quality": "count baseline; no calibrated count probabilities"}
    return receipt


def predict_team(model, history):
    x = _features(history)
    if x is None:
        return None
    z = (np.asarray(x)-model["center"])/model["scale"]
    values = np.maximum(0, np.asarray(model["coefficients"]) @ z + model["intercept"])
    recent = history.tail(8)
    ratios = recent.targets / recent.pass_attempts.replace(0, np.nan)
    rate = float(ratios.mean()) if ratios.notna().all() else None
    # Targets are a subset of physical passes; throwaways remain unallocated.
    return {"pass_attempts": float(values[0]), "rush_attempts": float(values[1]),
            "targets": float(values[0])*min(1.0, max(0.0, rate)) if rate is not None else None,
            "observed_target_rate": rate,
            "accounting_flags": ["observed_target_rate_above_one_clamped_to_pass_budget"] if rate is not None and rate > 1 else [],
            "features": dict(zip(FEATURES, x)),
            "history_periods": recent.period.astype(int).tolist()}


def forecast(weekly, actors, *, before_period, starters=None, model=None, verified_gaps=None, cutoff=None,
             event_evidence=None,team_budgets=None):
    """All native actors enter BEFORE eligibility preferences; unknown stays null.

    Counts are conditional on active participation and persistence of observed
    same-team role. This baseline does not invent injury-replacement expansion.
    """
    weekly = source_history(weekly, before_period=before_period, cutoff=cutoff)
    actors = [{**a, "position": normalize_position(a["position"])} for a in actors]
    if weekly.loc[weekly.player_master_id.notna()].duplicated(["player_master_id", "period"]).any():
        raise ValueError("Duplicate canonical player-game workload rows")
    if len({str(a["player_master_id"]) for a in actors}) != len(actors):
        raise ValueError("Duplicate canonical forecast actors")
    games = team_games(weekly); model = model or fit_team_model(games, before_period=before_period)
    if model["training_max_period"] >= before_period:
        raise ValueError("Workload model contains future target-period evidence")
    teams = {}; predictions = []; starters = starters or {};verified_gaps=verified_gaps or []
    for team in sorted({a["team"] for a in actors}):
        team_history = games.loc[games.team.eq(team)].sort_values("period")
        if team_budgets is None:
            teams[team] = predict_team(model, team_history)
        else:
            supplied=team_budgets.get(team)
            if supplied is None:raise ValueError('Declared team count budget missing; no reference fallback')
            for channel in CHANNELS:
                if supplied.get(channel) is not None and finite(supplied[channel]) is None:
                    raise ValueError('Invalid declared team count budget')
            if supplied.get('targets') is not None and (supplied.get('pass_attempts') is None or supplied['targets']>supplied['pass_attempts']):
                raise ValueError('Declared target budget exceeds physical passes')
            teams[team] = __import__('copy').deepcopy(supplied)
    for actor in actors:
        pid = str(actor["player_master_id"]); team = actor["team"]; pos = actor["position"]
        row = {**actor, "evidence_kind": "producer_forecast", "version": VERSION,
               "conditional_on": "active participation and stable observed same-team role",
               "counts": dict.fromkeys(CHANNELS), "raw_history": {}, "reasons": []}
        if pos not in POSITIONS:
            row["reasons"].append("not modeled: offensive workload domain only")
            predictions.append(row); continue
        same, window = select_role_window(weekly, actor, games,
            before_period=before_period, verified_gaps=verified_gaps)
        row["history_window_status"] = window["status"]
        if window["reason"] or teams[team] is None:
            row["reasons"].append(window["reason"] or "insufficient supported same-team role or team volume")
            predictions.append(row); continue
        if window["verified_inactive_gaps"]:
            row["verified_inactive_gaps"] = window["verified_inactive_gaps"]
            row["role_window"] = f"last{len(same)} observed current-team active games across verified inactive gaps; conditional return to observed role"
            if len(same) == 2:
                row["reasons"].append("Sparse two-game current-team return window; role persistence and workload uncertainty remain uncalibrated")
        evidence = same.merge(games, on=["team", "period"], suffixes=("", "_team"))
        applicable = ("pass_attempts", "rush_attempts") if pos == "QB" else ("targets", "rush_attempts")
        for channel in applicable:
            raw = same[channel]
            row["raw_history"][channel] = {"values": [finite(v) for v in raw],
                "periods": same.period.astype(int).tolist(), "mean": finite(raw.mean()) if raw.notna().all() else None}
            budget = teams[team].get(channel)
            denominator = evidence[channel+"_team"]
            shares = evidence[channel] / denominator.replace(0, np.nan)
            if budget is None or shares.isna().any() or (shares < 0).any() or (shares > 1).any():
                row["reasons"].append(channel+": incomplete count/share coverage"); continue
            if channel == "pass_attempts" and (starters.get(team) != pid or shares.iloc[-1] < .8):
                row["reasons"].append("passing: current sourced stable starter not established"); continue
            # Fixed forecast rule, declared before evaluation; no FP or injury boost.
            share = .5*float(shares.mean()) + .5*float(shares.iloc[-1])
            row["counts"][channel] = budget*share
        row["source_ids"] = same.source_id.tolist() if "source_id" in same else []
        predictions.append(row)
    # Downward reconciliation only. Missing/excluded actors never donate work.
    for team, budget in teams.items():
        if budget is None:
            continue
        budget["reconciliation"] = {}
        for channel in CHANNELS:
            members = [r for r in predictions if r["team"] == team and r["counts"][channel] is not None]
            total = sum(r["counts"][channel] for r in members); available = budget[channel]
            factor = min(1., available/total) if available is not None and total > 0 else 1.
            for row in members:
                row.setdefault("unreconciled_counts", {})[channel] = row["counts"][channel]
                row["counts"][channel] *= factor
            budget["reconciliation"][channel] = {"raw_sum": total, "downward_factor": factor,
                "unallocated": available-total*factor if available is not None else None,
                "unknown_actors": sum(r["counts"][channel] is None for r in predictions if r["team"] == team)}
    from .opportunity_events import event_capture_state, validate_event_evidence
    event_capture = (validate_event_evidence(event_evidence, before_period=before_period, cutoff=cutoff)
                     if event_evidence is not None else event_capture_state())
    return {"version": VERSION, "before_period": before_period, "model": model,
            "event_evidence": event_capture,
            "history_evidence": build_history_evidence(weekly, actors, before_period=before_period,
                verified_gaps=verified_gaps, cutoff=cutoff),
            "teams": teams, "players": predictions,
            "uncertainty": {"status": "unavailable", "reason": "No calibrated current count intervals or participation probabilities; point forecast conditional on stated role"},
            "limitations": ["count baseline, conditional participation; no injury role transfers",
                "targets and QB passes describe shared physical events, not independent opportunities"]}


def utility(row, scales):
    """Equal normalized-component utility; salary is only a constraint/cost."""
    pos = row["position"]
    applicable = ("pass_attempts", "rush_attempts") if pos == "QB" else ("targets", "rush_attempts")
    if pos not in POSITIONS or any(row["counts"][c] is None for c in applicable):
        return None
    # Each applicable component gets equal weight; fixed training scales only.
    return sum(row["counts"][c] / max(1., scales[pos][c]) for c in applicable) / len(applicable)


def training_scales(weekly, *, before_period):
    """Fixed prior-period per-position means; no slate exclusions or FP inputs."""
    return {pos: {channel: max(1., float(rows[channel].dropna().mean()))
                  for channel in CHANNELS}
            for pos, rows in weekly.loc[weekly.period < before_period].groupby("position")
            if pos in POSITIONS}


def load_history(engine, *, season, week, cutoff):
    """Immutable native stat IDs plus persisted canonical aliases; no name join.

    Source import clocks constrain present inference. Historical evaluations of
    these revised source rows must not claim originally captured pregame inputs.
    """
    from sqlalchemy import text
    from .market_snapshots import canonical_team
    with engine.connect() as connection:
        rows = connection.execute(text("""
            WITH aliases AS (
              SELECT source_key, MIN(player_master_id::text) AS player_master_id
              FROM public.player_alias WHERE source_system='nflreadpy'
              GROUP BY source_key HAVING COUNT(DISTINCT player_master_id)=1
            ), latest AS (
              SELECT DISTINCT ON (r.player_id,r.season,r.week) r.*, a.player_master_id
              FROM public.raw_nfl_weekly_stat r LEFT JOIN aliases a ON a.source_key=r.player_id
              WHERE r.season BETWEEN :start_season AND :season
                AND (r.season<:season OR r.week<:week) AND r.week<=18
                AND r.created_at<=:cutoff AND r.position IN ('QB','RB','FB','WR','TE')
                AND r.raw_row_json->>'season_type'='REG'
              ORDER BY r.player_id,r.season,r.week,r.created_at DESC,r.raw_nfl_weekly_stat_id DESC
            ) SELECT player_master_id,player_id AS source_player_id,season,week,team,position,raw_row_json,
                     raw_nfl_weekly_stat_id,created_at FROM latest
        """), dict(start_season=season-3, season=season, week=week, cutoff=cutoff)).mappings().all()
    records = []
    for row in rows:
        raw = row["raw_row_json"] or {}
        records.append(dict(player_master_id=str(row["player_master_id"]) if row["player_master_id"] else None,
            source_player_id=row["source_player_id"],
            period=int(row["season"])*100+int(row["week"]), team=canonical_team(row["team"]),
            position=normalize_position(row["position"]), pass_attempts=finite(raw.get("attempts", raw.get("passing_attempts"))),
            rush_attempts=finite(raw.get("carries", raw.get("rushing_attempts"))),
            targets=finite(raw.get("targets")),
            passing_yards=signed_finite(raw.get("passing_yards")),
            passing_interceptions=finite(raw.get("interceptions",raw.get("passing_interceptions"))),
            completions=finite(raw.get("completions")),
            rushing_yards=signed_finite(raw.get("rushing_yards")),
            receptions=finite(raw.get("receptions")),receiving_yards=signed_finite(raw.get("receiving_yards")),
            source_id=int(row["raw_nfl_weekly_stat_id"]),
            imported_at=row["created_at"].isoformat()))
    return pd.DataFrame(records)


def prepare_receipt(engine, pool_rows, *, season, week, cutoff, projection_run_id, opportunity_source_context=None, games=None, markets=None):
    """Called once by public Prepare; Optimize consumes these frozen bytes."""
    from .market_snapshots import canonical_team
    weekly = load_history(engine, season=season, week=week, cutoff=cutoff)
    native = {}
    starters = {}
    for source in pool_rows:
        pid = str(source.get("player_id") or "")
        if not pid:
            raise ValueError("Native workload actor lacks canonical identity")
        team = canonical_team(source.get("player_team") or source.get("team"))
        native[pid] = dict(player_master_id=pid, team=team, position=source["position"],
            name=source.get("name") or source.get("player_name"), native_id=source.get("dk_player_id"),
            current_role_evidence=verified_current_role(source,cutoff=cutoff),canonical_role=source.get("canonical_role"))
        if source["position"] == "QB" and source.get("is_starting_qb") is True and source.get("starting_qb_source"):
            if team in starters and starters[team] != pid:
                raise ValueError("Conflicting current starting QB evidence")
            starters[team] = pid
    for actor in native.values():
        if actor.get("current_role_evidence"):
            actor["current_role_evidence"]={**actor["current_role_evidence"],"season":season,"week":week,
                "scope_basis":"validated current canonical role within frozen native slate"}
    teams = {r["team"] for r in native.values()}
    historical = weekly.loc[weekly.player_master_id.notna()].sort_values("period").drop_duplicates("player_master_id", keep="last")
    actors = {str(r.player_master_id): dict(player_master_id=str(r.player_master_id), team=r.team, position=r.position)
              for r in historical.itertuples() if r.team in teams}
    actors.update(native)  # current native team/identity wins; history is not transplanted
    from .workload_gamebook_participation import load_verified_gaps
    gaps=load_verified_gaps(engine,season=season,cutoff=cutoff)
    result = forecast(weekly, [actors[k] for k in sorted(actors)],
                      before_period=season*100+week, starters=starters,verified_gaps=gaps,cutoff=cutoff)
    # Versioned model inference consumes authenticated current measurements and
    # markets. Reference producer remains frozen as the component anchor.
    if games and opportunity_source_context is not None and opportunity_source_context.get('status')=='available_descriptive':
        from sqlalchemy.orm import Session
        from .team_opportunity_serving import predict_registered_teams
        with Session(engine) as session:
            issued=predict_registered_teams(session,weekly,opportunity_source_context,games,markets or [],
                before_period=season*100+week,cutoff=cutoff)
        result['team_opportunity_model_inference']=issued
        if issued['status']=='forecast_complete':
            reference=result
            budgets={}
            for issued_team in issued['predictions']:
                team=issued_team['team'];budget=__import__('copy').deepcopy(reference['teams'][team])
                if budget is None:raise ValueError('New team producer lacks supported reference target subset rate')
                budget.update(issued_team['counts'])
                rate=budget.get('observed_target_rate')
                budget['targets']=budget['pass_attempts']*min(1.,max(0.,rate)) if rate is not None else None
                budgets[team]=budget
            result=forecast(weekly,[actors[k] for k in sorted(actors)],before_period=season*100+week,
                starters=starters,model=reference['model'],verified_gaps=gaps,cutoff=cutoff,team_budgets=budgets)
            result['reference_count_forecast']=reference
            result['team_opportunity_model_inference']=issued
            result['team_budget_model_contract']={k:issued.get(k) for k in ('version','inference_matrix_sha256','source_measurements_sha256')}
            from .opportunity_role_allocation import allocate_factual_vacancies
            from .opportunity_role_allocation import unavailable_from_canonical_rows
            unavailable,unresolved=unavailable_from_canonical_rows(pool_rows,before_period=season*100+week,cutoff=cutoff)
            result=allocate_factual_vacancies(result,unavailable=unavailable,cutoff=cutoff)
            result['unresolved_vacancy_proofs']=unresolved
            from .count_component_response import component_response
            base={str(r.get('player_id')):finite(r.get('projection')) for r in pool_rows}
            result['component_response']=component_response(weekly,reference,result,base,before_period=season*100+week,cutoff=cutoff)
    # Gamebooks have a separately captured JSON derivation. IR intervals are
    # rederived from authenticated transaction bytes; retain their actual raw
    # snapshot ID rather than inventing a derived snapshot.
    result["verified_gap_source_ids"]=sorted({g.get("derived_snapshot_id") or g["source_snapshot_id"] for g in gaps})
    result["scales"] = training_scales(weekly, before_period=season*100+week)
    for row in result["players"]:
        row["native_salary_actor"] = row["player_master_id"] in native
        row["utility"] = utility(row, result["scales"])
    result.update(projection_run_id=projection_run_id, source_cutoff_at=cutoff.isoformat(),
        source_history_sha256=hashlib.sha256(weekly.sort_values(["period", "player_master_id"]).to_json(orient="records").encode()).hexdigest(),
        source_ids=sorted(weekly.source_id.astype(int).tolist()),
        unresolved_source_actor_ids=sorted(set(weekly.loc[weekly.player_master_id.isna(), "source_player_id"].astype(str))),
        starter_ids=starters, starter_evidence={str(r.get("player_id")): r.get("role_starter_evidence")
            for r in pool_rows if str(r.get("player_id")) in set(starters.values())},
        producer_code_sha256=hashlib.sha256(__import__("pathlib").Path(__file__).read_bytes()).hexdigest(),
        objective="mean of equally weighted count/training-position-scale components; Captain1.5 utility only",
        domain="offensive workload only; K/DST unsupported, unknown forecasts ineligible; preferences never redistribute volume")
    if opportunity_source_context is not None:
        # Measurements are available numeric inputs, not automatically expected
        # counts. The versioned forecast producer must explicitly consume its
        # trained feature contract before any count/FP result changes.
        result["opportunity_source_context"] = opportunity_source_context
        result["opportunity_measurement_consumption"] = {
            "status": "measured_numeric_inputs_available" if opportunity_source_context.get("status")=="available_descriptive" else opportunity_source_context.get("status"),
            "forecast_effect": "none_until_versioned_numeric_producer_consumes_contract",
            "semantic_measurements_sha256": opportunity_source_context.get("semantic_measurements_sha256")}
    result["sha256"] = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return result
