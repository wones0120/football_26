"""Cash-oriented single-lineup selection. No estimated cash probabilities.

The current simulation model has independent marginals and no supported field
model. These fixed, ex-ante risk preferences and factor assumptions are a proxy,
not fitted parameters or calibrated lineup quantiles. Slot projections returned
by the Captain solver already include 1.5x; its marginal P10 does not.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from decimal import Decimal, ROUND_CEILING
import math

CAPTAIN_SINGLE_LINEUP_STRATEGY_ID = "captain_single_lineup_v1"
CLASSIC_SINGLE_LINEUP_STRATEGY_ID = "classic_single_lineup_v1"
SINGLE_LINEUP_STRATEGIES = {
    CAPTAIN_SINGLE_LINEUP_STRATEGY_ID: "showdown",
    CLASSIC_SINGLE_LINEUP_STRATEGY_ID: "classic",
}
POLICY_ID = "cash_oriented_selection_proxy_v1"
WEIGHTS = {"mean": 1.0, "downside": 0.45, "bounded_upside": 0.10,
           "availability": 1.0, "competition": 0.05}
Z90 = 1.2815515655446004
PORTFOLIO_FIELDS = (
    "min_exposure", "portfolio_constraints", "stack_templates",
    "require_scenario_diversity", "soft_scenario_diversity",
    "entries_to_use", "num_single_entry_contests", "single_entry_objective_weights",
    "classic_portfolio_objective_weights", "max_objective_loss",
    "min_distinct_primary_games", "minimum_player_exposure",
)
LINEUP_CONTROL_FIELDS = (
    "num_lineups", "max_exposure", "max_lineup_overlap", "minimum_uniqueness",
    "max_lineups_per_primary_game", "captain_max_exposure", "core_player_max_exposure",
    "starting_qb_max_exposure", "cheap_punt_max_exposure", "elevated_player_max_exposure",
    "max_elevated_players_per_lineup", "maximum_exposure_by_player", "max_players_per_team",
    "max_players_per_game", "locked_player_ids",
)


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def normalize_single_lineup_params(params: dict, *, contest_format="classic") -> None:
    if params.get("long_shot_mode"):
        raise ValueError("Single-lineup strategies use the cash-oriented objective; long-shot mode is historical research only")
    present = {key for key in PORTFOLIO_FIELDS if key in params}
    ignored = sorted(set(params.get("ignored_portfolio_controls") or []) | present)
    for key in present:
        params.pop(key)
    params.setdefault("num_lineups", 1)
    params.setdefault("max_exposure", 1.0)
    roster_size = 6 if contest_format == "showdown" else 9
    bounds = {"num_lineups": (1, 50), "max_lineup_overlap": (0, roster_size),
              "minimum_uniqueness": (1, roster_size), "max_elevated_players_per_lineup": (0, roster_size),
              "max_lineups_per_primary_game": (1, 50),
              "max_players_per_team": (3, 5) if contest_format == "showdown" else (1, 4),
              "max_players_per_game": (1, roster_size)}
    for key, (low, high) in bounds.items():
        value = params.get(key)
        if value is not None and (type(value) is not int or not low <= value <= high):
            raise ValueError(f"{key} must be a whole number from {low} through {high}")
    for key in ("max_exposure", "captain_max_exposure", "core_player_max_exposure",
                "starting_qb_max_exposure", "cheap_punt_max_exposure", "elevated_player_max_exposure"):
        value = params.get(key)
        if value is not None and (type(value) not in (int, float) or number(value) is None or not 0 <= value <= 1):
            raise ValueError(f"{key} must be a finite rate from 0 through 1")
    caps = params.get("maximum_exposure_by_player") or {}
    if not isinstance(caps, dict) or any(not isinstance(pid, str) or not pid or
            type(rate) not in (int, float) or number(rate) is None or not 0 <= rate <= 1 for pid, rate in caps.items()):
        raise ValueError("maximum_exposure_by_player requires canonical player IDs and finite rates from 0 through 1")
    if contest_format != "classic" and params.get("max_lineups_per_primary_game") is not None:
        raise ValueError("Max lineups per primary game requires Classic")
    params.update(long_shot_mode=False, ignored_portfolio_controls=ignored, exclusions_assumed_out=False)


def contest_context(params, pool_rows, *, contest_format):
    """Read contest facts from the native parser, never a client verification flag."""
    from .showdown_contests import fetch_contests, _ladder_is_complete

    urls = params.get("contest_urls") or []
    if not urls:
        return {"status": "generic_no_contest", "selection_effect": "generic_cash_oriented_proxy"}
    if not isinstance(urls, list) or len(urls) != 1:
        raise ValueError("A single-lineup run accepts exactly one DraftKings contest URL")
    row = fetch_contests(urls)[0]
    verified = (row.get("source") == "draftkings_embedded_contest_detail"
                and bool(row.get("source_sha256")) and not row.get("unavailable_fields")
                and _ladder_is_complete(row))
    groups = {str(r["draft_group_id"]) for r in pool_rows if r.get("draft_group_id") is not None}
    if verified and groups and str(row.get("draft_group_id")) not in groups:
        raise ValueError("Contest draft group does not match the frozen salary slate")
    # Without native salary draft-group identity, facts are visible but cannot
    # be asserted to describe this slate's field.
    matched = verified and len(groups) == 1 and str(row.get("draft_group_id")) in groups
    return {"status": "verified_payout_facts" if matched else "unverified_or_slate_match_unavailable",
            "contest_format": contest_format,
            "facts": {key: row.get(key) for key in ("contest_id", "name", "draft_group_id", "capacity",
                "current_entries", "paid_places", "payout_ladder", "lock_time", "source", "source_sha256", "observed_at", "error", "unavailable_fields")},
            "selection_effect": "generic_cash_oriented_proxy_no_supported_field_model",
            "note": "Paid places are rank facts, not a fantasy-point cutoff. No uniform-rank payout proxy is used."}


def signature(lineup):
    return tuple(sorted((str(row["player_id"]), row.get("roster_position") == "CPT") for row in lineup))


def marginal(row):
    mean = number(row.get("projection"))
    if mean is None:
        raise ValueError("Single-lineup ranking requires finite expected points for every player")
    multiplier = 1.5 if row.get("roster_position") == "CPT" else 1.0
    p10 = number(row.get("predicted_p10"))
    p90 = number(row.get("p90"))
    # Solver rows retain unmultiplied predicted_p10 but multiply projection/P90.
    p10 = p10 * multiplier if p10 is not None else None
    supported = p10 is not None and p90 is not None and p10 <= mean <= p90 and p90 > p10
    sigma = (p90 - p10) / (2 * Z90) if supported else max(3 * multiplier, abs(mean) * 0.6)
    return mean, sigma, supported


def _loadings(row):
    """PSD factor covariance: game, team offense, passing offense, residual.

    DST loads negatively on opposing offense. All coefficients are unvalidated
    structural assumptions; this does not add fantasy points for correlations.
    """
    team = str(row.get("player_team") or row.get("team") or "")
    opponent = str(row.get("opponent_team") or "")
    if not team:
        return {}
    position = str(row.get("position") or "").upper()
    factors = {}
    if opponent:
        factors["game:" + ":".join(sorted((team, opponent)))] = 0.25
    if position == "DST":
        if opponent:
            factors["offense:" + opponent] = -0.35
    else:
        factors["offense:" + team] = 0.35
        if position in {"QB", "WR", "TE"}:
            factors["passing:" + team] = 0.35
    return factors


def lineup_diagnostics(lineup, *, competition_supported=False):
    mean = variance = availability_risk = competition_risk = 0.0
    factors = defaultdict(float)
    missing_quantiles, unknown_availability, risks = [], [], []
    for row in lineup:
        player_mean, sigma, supported = marginal(row)
        mean += player_mean
        loadings = _loadings(row)
        variance += sigma * sigma * (1 - sum(v * v for v in loadings.values()))
        for key, value in loadings.items():
            factors[key] += sigma * value
        label = str(row.get("name") or row.get("player_name") or row["player_id"])
        if not supported:
            missing_quantiles.append(label)
        availability = number(row.get("pregame_availability_probability"))
        if availability is None or not 0 <= availability <= 1:
            unknown_availability.append(label)
            availability_risk += max(0.0, player_mean) * 0.10
        else:
            availability_risk += max(0.0, player_mean) * (1 - availability)
            if availability < 0.95:
                risks.append(f"{label}: availability uncertainty ({availability:.0%} sourced model availability; not cash probability).")
        if competition_supported:
            own = number(row.get("ownership"))
            if own is None or not 0 <= own <= 100:
                raise ValueError("Supported competition proxy requires complete slot ownership")
            competition_risk += max(0.0, player_mean) * (1 - own / 100)
    variance += sum(v * v for v in factors.values())
    downside = Z90 * math.sqrt(max(0.0, variance))
    if missing_quantiles:
        risks.append("Marginal quantiles missing/invalid; conservative spread fallback: " + ", ".join(missing_quantiles))
    if unknown_availability:
        risks.append("Availability probability unavailable; explicit uncertainty penalty: " + ", ".join(unknown_availability))
    team_counts = defaultdict(int)
    for row in lineup:
        team_counts[str(row.get("player_team") or row.get("team") or "unknown")] += 1
    if max(team_counts.values()) >= 3:
        risks.append("Concentrated team exposure: shared offensive/game failure increases downside.")
    if not competition_supported:
        risks.append("Supported projected competition unavailable; ownership term disabled.")
    terms = {"mean": mean, "downside": -WEIGHTS["downside"] * downside,
             "bounded_upside": WEIGHTS["bounded_upside"] * min(downside, max(0.0, mean) * 0.25),
             "availability": -availability_risk,
             "competition": -WEIGHTS["competition"] * competition_risk}
    return {"expected_points": mean, "downside_diagnostic": mean - downside,
            "upside_diagnostic": mean + downside, "downside_spread": downside,
            "availability_risk_points": availability_risk,
            "competition_risk_points": competition_risk if competition_supported else None,
            "objective_contributions": terms, "selection_score": sum(terms.values()),
            "risk_factors": risks, "missing_quantiles": missing_quantiles,
            "correlation_assumptions": "game=.25; offense=.35; passing=.35; opposing DST=-.35; PSD factors",
            "distribution_status": "unvalidated_correlated_normal_spread_diagnostic",
            "cash_probability": None}


def elevated_player(row, cutoff=None):
    from .classic_prospective import classify_availability
    return classify_availability(row, cutoff)["bucket"] in {"questionable_elevated", "doubtful", "out"}


def appearance_limit(count, rate):
    return int((Decimal(count) * Decimal(str(rate))).to_integral_value(rounding=ROUND_CEILING))


def apply_lineup_constraints(model, pool, variables, controls, *, cutoff=None):
    """Hard user preferences shared by discovery and final selection."""
    import pulp
    from .classic_primary_game import canonical_primary_game

    for field, key in (("max_players_per_team", "team"), ("max_players_per_game", "game")):
        cap = controls.get(field)
        if cap is None:
            continue
        groups = defaultdict(list)
        for index, row in pool.iterrows():
            team = row.get("player_team") or row.get("team")
            group = str(team) if key == "team" else canonical_primary_game(team, row.get("opponent_team"))
            groups[group].append(variables[index])
        for values in groups.values():
            model += pulp.lpSum(values) <= cap
    cap = controls.get("max_elevated_players_per_lineup")
    if cap is not None:
        model += pulp.lpSum(variables[index] for index, row in pool.iterrows()
                            if elevated_player(row, cutoff)) <= cap


def _constrained_indices(evaluated, controls, *, contest_format, cutoff=None):
    """Maximize feasible count, then preserve individual cash ranking lexically.

    There is no aggregate lineup score, diversity bonus or portfolio EV. A
    higher-ranked candidate wins whenever it can coexist with the requested
    number of outputs under the user's hard limits. Limits are never relaxed.
    """
    import pulp
    import time
    from .classic_portfolio_controls import explicit_appearance_limit
    from .classic_primary_game import canonical_primary_game

    count = controls.get("num_lineups", 1)
    if not evaluated:
        return [], {"status": "underfilled", "requested": count, "achieved": 0, "limits_relaxed": False}
    model = pulp.LpProblem("cash_rank_user_constraints", pulp.LpMaximize)
    choices = [pulp.LpVariable(f"candidate_{i}", cat="Binary") for i in range(len(evaluated))]
    total = pulp.lpSum(choices)
    model += total <= count
    players, captains, games = defaultdict(list), defaultdict(list), defaultdict(list)
    player_rows, sets = {}, []
    locks = set(controls.get("locked_player_ids") or [])
    blocked = {}
    for i, (_, _, lineup) in enumerate(evaluated):
        sets.append({str(row["player_id"]) for row in lineup})
        if locks - sets[i]:
            model += choices[i] == 0
            blocked[i] = "Missing required locked player(s)."
        for row in lineup:
            pid = str(row["player_id"])
            players[pid].append(choices[i]); player_rows[pid] = row
            if row.get("roster_position") == "CPT":
                captains[pid].append(choices[i])
        cap = controls.get("max_elevated_players_per_lineup")
        if cap is not None and sum(elevated_player(row, cutoff) for row in lineup) > cap:
            model += choices[i] == 0
            blocked[i] = "Exceeds requested elevated-risk players per lineup."
        for field, group_key in (("max_players_per_team", "team"), ("max_players_per_game", "game")):
            if controls.get(field) is None:
                continue
            groups = defaultdict(int)
            for row in lineup:
                team = row.get("player_team") or row.get("team")
                key = str(team) if group_key == "team" else canonical_primary_game(team, row.get("opponent_team"))
                groups[key] += 1
            if max(groups.values()) > controls[field]:
                model += choices[i] == 0
                blocked[i] = f"Exceeds requested {field}."
        if controls.get("max_lineups_per_primary_game") is not None:
            qb = next(row for row in lineup if row.get("position") == "QB")
            game = canonical_primary_game(qb.get("player_team") or qb.get("team"), qb.get("opponent_team"))
            games[game].append(choices[i])
    for pid, variables in players.items():
        row = player_rows[pid]
        # A lock means inclusion in every output, as in the existing optimizer.
        # Explicit per-player/elevated caps still apply and can conflict with it.
        rate = 1.0 if pid in locks else controls.get("max_exposure", 1.0)
        if contest_format == "showdown" and pid not in locks:
            key = "core_player_max_exposure"
            if row.get("position") == "QB" and row.get("showdown_qb_eligible") is True:
                key = "starting_qb_max_exposure"
            elif (number(row.get("base_salary")) or number(row.get("salary")) or 0) <= 1000:
                key = "cheap_punt_max_exposure"
            rate = min(rate, controls.get(key, 1.0))
        rate = min(rate, (controls.get("maximum_exposure_by_player") or {}).get(pid, 1.0))
        limit = appearance_limit(count, rate)
        if controls.get("elevated_player_max_exposure") is not None and elevated_player(row, cutoff):
            limit = min(limit, explicit_appearance_limit(count, controls["elevated_player_max_exposure"]))
        model += pulp.lpSum(variables) <= limit
    for variables in captains.values():
        model += pulp.lpSum(variables) <= appearance_limit(count, controls.get("captain_max_exposure", 1.0))
    for variables in games.values():
        model += pulp.lpSum(variables) <= controls["max_lineups_per_primary_game"]
    overlap = controls.get("max_lineup_overlap")
    if controls.get("minimum_uniqueness") is not None:
        derived = (6 if contest_format == "showdown" else 9) - controls["minimum_uniqueness"]
        overlap = min(overlap, derived) if overlap is not None else derived
    if overlap is not None:
        for i, left in enumerate(sets):
            for j in range(i):
                if len(left & sets[j]) > overlap:
                    model += choices[i] + choices[j] <= 1
    # Bound solving across the cardinality and all feasibility checks together.
    deadline = time.monotonic() + 30
    def solve():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError("Lineup constraint selection timed out; no user limits were relaxed")
        status = model.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=remaining))
        if status not in {pulp.LpStatusOptimal, pulp.LpStatusInfeasible} or (
                status == pulp.LpStatusOptimal and model.sol_status != pulp.LpSolutionOptimal):
            raise ValueError("Lineup constraint selection could not certify feasibility; no user limits were relaxed")
        return status
    model.setObjective(total)
    solve()
    achieved = round(pulp.value(total) or 0)
    model += total == achieved
    model.setObjective(pulp.lpSum([]))
    selected = []
    for i, choice in enumerate(choices):
        if len(selected) == achieved:
            break
        name = f"prefer_rank_{i}"
        model += choice == 1, name
        if solve() == pulp.LpStatusOptimal:
            selected.append(i)
        else:
            del model.constraints[name]
            model += choice == 0
            blocked.setdefault(i, "Cannot coexist with the higher-ranked selections and requested count under user limits.")
    return selected, {"status": "fulfilled" if achieved == count else "underfilled",
        "requested": count, "achieved": achieved, "effective_overlap": overlap,
        "limits_relaxed": False, "blocked_candidates": {f"cash-{i + 1}": reason for i, reason in blocked.items()},
        "note": "Exposure appearance limits use requested count; ordinary caps round up, explicit elevated-risk caps round down. Locked players bypass ordinary player caps."}


def select_single_lineup(candidates, *, strategy, competition_supported=False, contest=None, controls=None, cutoff=None):
    if strategy not in SINGLE_LINEUP_STRATEGIES:
        raise ValueError("Unknown single-lineup strategy")
    unique = {signature(lineup): lineup for lineup in candidates if lineup}
    evaluated = [(lineup_diagnostics(lineup, competition_supported=competition_supported), key, lineup)
                 for key, lineup in unique.items()]
    from .showdown_captain_shortlist import POLICY_ID as captain_policy
    p90_captain_policy = bool(evaluated) and all(
        lineup[0].get("solver_scoring_policy") == captain_policy for _, _, lineup in evaluated
    )
    if p90_captain_policy:
        for diagnostic, _, lineup in evaluated:
            diagnostic["objective_contributions"] = {
                "captain_p90": sum(float(row["objective_score"]) for row in lineup if row["roster_position"] == "CPT"),
                "flex_mean": sum(float(row["objective_score"]) for row in lineup if row["roster_position"] == "FLEX"),
            }
            diagnostic["selection_score"] = sum(diagnostic["objective_contributions"].values())
    evaluated.sort(key=lambda item: (-item[0]["selection_score"], -item[0]["expected_points"], item[1]))
    controls = {k: v for k, v in (controls or {}).items() if k in LINEUP_CONTROL_FIELDS and v is not None}
    normalize_single_lineup_params(controls, contest_format=SINGLE_LINEUP_STRATEGIES[strategy])
    selected_indices, constraint_report = _constrained_indices(evaluated, controls,
        contest_format=SINGLE_LINEUP_STRATEGIES[strategy], cutoff=cutoff)
    rows = []
    primary = selected_indices[0] if selected_indices else None
    best = evaluated[primary if primary is not None else 0][0] if evaluated else None
    for rank, (diagnostic, key, lineup) in enumerate(evaluated, 1):
        rows.append({**diagnostic, "rank": rank, "candidate_id": f"cash-{rank}",
                     "mean": diagnostic["expected_points"],
                     "p90": sum(number(p.get("p90")) or 0 for p in lineup),
                     "salary": sum(number(p.get("salary")) or 0 for p in lineup),
                     "games_represented": sorted({str(p.get("game_id")) for p in lineup if p.get("game_id")}),
                     "players": deepcopy(lineup), "selected": rank - 1 in selected_indices,
                     "primary_recommendation": rank - 1 == primary,
                     "rejection_reason": None if rank - 1 in selected_indices else constraint_report.get("blocked_candidates", {}).get(f"cash-{rank}") or
                         f"Lower cash-oriented proxy by {best['selection_score'] - diagnostic['selection_score']:.3f} points; "
                         f"mean delta {diagnostic['expected_points'] - best['expected_points']:+.2f}, "
                         f"downside delta {diagnostic['downside_diagnostic'] - best['downside_diagnostic']:+.2f}.",
                     "term_deltas_vs_selected": {k: v - best["objective_contributions"][k]
                                                for k, v in diagnostic["objective_contributions"].items()}})
    notable = sorted({row["rank"] for metric in ("expected_points", "upside_diagnostic", "downside_diagnostic")
                      for row in sorted(rows, key=lambda r: -r[metric])[:1]} - {i + 1 for i in selected_indices})
    report = {"contract_id": POLICY_ID, "strategy_id": strategy, "recommended_count": 1 if selected_indices else 0,
              "requested_count": controls["num_lineups"], "selected_count": len(selected_indices),
              "selected_candidate_ids": [f"cash-{i + 1}" for i in selected_indices],
              "user_constraints": {k: v for k, v in controls.items() if k in LINEUP_CONTROL_FIELDS},
              "constraint_selection": constraint_report,
              "method": "transparent_cash_oriented_proxy", "calibration_status": "unvalidated",
              "cash_probability": None,
              "cash_probability_unavailable_reason": "No supported joint contest-field outcome model or calibrated paid-cutoff estimator exists.",
              "contest": contest, "objective_weights": dict(WEIGHTS),
              "competition_status": "supported_slot_popularity_proxy" if competition_supported else "unavailable_term_disabled",
              "candidate_count": len(rows), "all_candidates": rows,
              "recommended": {k: v for k, v in rows[primary].items() if k != "players"} if primary is not None else None,
              "notable_alternatives": [row for row in rows if not row["selected"] and (row["rank"] in notable or row["rank"] <= 4)],
              "why_preferred": "Highest cash-oriented rank compatible with the feasible requested count and hard user limits; correlated downside, capped upside, availability uncertainty and supported popularity-risk penalties determine individual rank. No portfolio EV or diversity bonus.",
              "limitations": ["Proxy score is in preference points, never a cash probability or expected payout.",
                  "Downside/upside are normal-spread diagnostics with assumed correlations, not calibrated lineup P10/P90.",
                  "Upside credit stops at 25% of expected points; summed player P90 is research only.",
                  "Availability penalty expresses risk aversion; projections remain unchanged.",
                  "Ownership describes marginal popularity, not opponent lineups or a paid-score cutoff.",
                  "Generic objective: no contest-specific cash cutoff is inferred, even when payout facts are verified.",
                  "Requested exposure limits use whole appearances; underfilled outputs can have higher realized percentages. No user limits are relaxed.",
                  "Best among generated candidates; candidate generation does not certify the global proxy optimum."]}
    if p90_captain_policy:
        report.update({
            "contract_id": captain_policy, "method": "captain_p90_flex_mean",
            "objective_weights": {"captain_p90": 1.5, "flex_mean": 1.0},
            "why_preferred": "Highest 1.5× pregame captain P90 plus FLEX means compatible with requested count and hard user limits.",
            "limitations": ["Sum of role-specific projections, not a calibrated lineup percentile or payout estimate.",
                            "Best among generated candidates under existing roster and user constraints."],
        })
        for row in rows:
            if not row["selected"] and row["candidate_id"] not in constraint_report.get("blocked_candidates", {}):
                row["rejection_reason"] = f"Lower captain P90 plus FLEX mean objective by {best['selection_score'] - row['selection_score']:.3f} points."
    selected = [deepcopy(evaluated[i][2]) for i in selected_indices]
    for output_index, (lineup, candidate_index) in enumerate(zip(selected, selected_indices), 1):
        lineup[0]["cash_lineup_selection"] = {"output_index": output_index,
            "candidate_id": f"cash-{candidate_index + 1}", "primary": output_index == 1,
            "diagnostics": deepcopy(evaluated[candidate_index][0])}
    if selected:
        selected[0][0]["single_lineup_report"] = report
    return selected, report


def generate_candidates(pool, solve, *, contest_format, target, base_kwargs, requested_captain_id=None):
    """Reuse the legal ILP across risk views and Captain/QB families.

    Candidate uniqueness is discovery deduplication, never a final overlap cap.
    No exposure constraints, portfolio quality floors or diversification scores.
    """
    import pandas as pd

    frame = pool.copy()
    means = pd.to_numeric(frame["projection"], errors="coerce").fillna(0)
    floors = pd.to_numeric(frame.get("predicted_p10", means), errors="coerce").fillna(means)
    ceilings = pd.to_numeric(frame.get("p90", means), errors="coerce").fillna(means)
    availability = pd.to_numeric(frame.get("pregame_availability_probability", pd.Series(0.9, index=frame.index)), errors="coerce").fillna(0.9).clip(0, 1)
    frame["single_mean"] = means
    frame["single_floor"] = floors
    frame["single_balanced"] = means - .45 * (means - floors).clip(lower=0) + .1 * (ceilings - means).clip(lower=0, upper=means.clip(lower=0) * .25) - means.clip(lower=0) * (1 - availability)
    frame["single_upside"] = means + .2 * (ceilings - means).clip(lower=0, upper=means.clip(lower=0) * .25)
    modes = ("single_balanced", "single_mean", "single_floor", "single_upside")
    seen, candidates, excluded = set(), [], []
    kwargs = {**base_kwargs, "include_control_comparison": False}

    def add(mode, **extra):
        lineup = solve(frame, score_col=mode, exclude_signatures=excluded, **{**kwargs, **extra})
        if lineup and signature(lineup) not in seen:
            seen.add(signature(lineup)); candidates.append(lineup)
            excluded.append([(str(r["player_id"]), r.get("roster_position") if contest_format == "showdown" else None) for r in lineup])
        return bool(lineup)

    if contest_format == "showdown":
        families = [requested_captain_id] if requested_captain_id else frame.sort_values("single_balanced", ascending=False)["player_id"].astype(str).tolist()
        for captain in families:
            if len(candidates) >= target:
                break
            if captain in kwargs.get("flex_only_player_ids", set()):
                continue
            add(modes[0], locked_captain_player_id=captain)
        kwargs["locked_captain_player_id"] = requested_captain_id
    else:
        for player_id in frame.loc[frame["position"].eq("QB")].sort_values("single_balanced", ascending=False)["player_id"].astype(str):
            if len(candidates) >= target:
                break
            add(modes[0], locked_player_ids=set(kwargs.get("locked_player_ids", set())) | {player_id})
    exhausted = set()
    for index in range(target * len(modes)):
        if len(candidates) >= target or len(exhausted) == len(modes):
            break
        mode = modes[index % len(modes)]
        if mode not in exhausted and not add(mode):
            exhausted.add(mode)
    return candidates
