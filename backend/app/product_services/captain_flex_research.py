"""Offline conditional Captain/FLEX research. Never imported by live selection.

Gaussian upper-tail moments and declared factor priors are ranking proxies, not
calibrated football distributions, optimal-Captain probabilities or payout EV.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
from statistics import NormalDist

from .showdown_portfolio_selection import select_showdown_portfolio, signature

POLICY_ID = "captain_flex_conditional_proxy_v1"
Z90 = NormalDist().inv_cdf(.90)
TAIL_MOMENT = NormalDist().pdf(Z90) / .10
FACTOR_PRIORS = {
    "environment": .20, "qb_passing": .60, "receiver_passing": .35,
    "receiving_back_passing": .35, "trailing_passing": .15,
    "leading_rush_defense": .30, "defense_opposing_passing": -.40,
    "receiving_competition": .60, "rushing_competition": .35,
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def workload(player, kind):
    """Only frozen current/lagged opportunity fields; never actuals or names."""
    diagnostic = player.get("opportunity_diagnostic") or {}
    for field, value in (
        (f"pregame_expected_{kind}", player.get(f"pregame_expected_{kind}")),
        (f"projected_{kind}", player.get(f"projected_{kind}")),
        (f"{kind}_mean_3", player.get(f"{kind}_mean_3")),
        (f"diagnostic.recent_{kind}_mean_3", diagnostic.get(f"recent_{kind}_mean_3")),
    ):
        if number(value) is not None and float(value) >= 0:
            return float(value), field
    return None, "missing"


def role(player, unknown=.5):
    carries, carry_source = workload(player, "carries")
    targets, target_source = workload(player, "targets")
    position = player["position"]
    if position == "QB":
        rushing = min(1., carries / 6.) if carries is not None else unknown
        receiving = 0.
        missing = carries is None
    elif position == "RB":
        # A target carries more receiving-role evidence than a carry does.
        missing = targets is None or carries is None or targets + carries == 0
        receiving = unknown if missing else targets / (targets + .25 * carries)
        rushing = 1. - receiving
    else:
        receiving, rushing, missing = (1. if position in {"WR", "TE"} else 0.), 0., False
    return {"rushing": rushing, "receiving": receiving, "unknown": missing,
            "carries": carries, "targets": targets,
            "carry_source": carry_source, "target_source": target_source}


def factor_model(players, *, unknown_role=.5, competition=True):
    """PSD covariance via shared factors plus independent residual variance.

    Pairwise opposite-sign factors represent finite opportunity competition.
    Competition is normalized by the number of teammates, not lineup membership.
    """
    if not 0 <= unknown_role <= 1:
        raise ValueError("Unknown-role prior must be between zero and one")
    ids = [p["player_id"] for p in players]
    if len(ids) != len(set(ids)) or any(not pid for pid in ids):
        raise ValueError("Unique canonical player IDs required")
    teams = sorted({p["team"] for p in players})
    if len(teams) != 2 or any(not t for t in teams):
        raise ValueError("Exactly two explicit teams required")
    f, roles = {}, {}
    w = FACTOR_PRIORS
    for p in sorted(players, key=lambda p: p["player_id"]):
        pid, team, pos = p["player_id"], p["team"], p["position"]
        if pos not in {"QB", "RB", "WR", "TE", "K", "DST"}:
            raise ValueError("Natural player position required")
        r = roles[pid] = role(p, unknown_role)
        side = 1. if team == teams[0] else -1.
        factors = {"environment": w["environment"] * (-1 if pos == "DST" else 1)}
        if pos in {"QB", "WR", "TE", "RB"}:
            passing = (w["qb_passing"] * (1 - r["rushing"]) if pos == "QB" else
                       w["receiving_back_passing"] * r["receiving"] if pos == "RB" else
                       w["receiver_passing"])
            factors[f"passing:{team}"] = passing
            factors["script"] = side * (w["leading_rush_defense"] * r["rushing"]
                if pos == "RB" else -w["trailing_passing"] * (1-r["rushing"]))
        if pos == "DST":
            factors["script"] = side * w["leading_rush_defense"]
            factors[f"passing:{next(t for t in teams if t != team)}"] = w["defense_opposing_passing"]
        f[pid] = factors
    if competition:
        for team in teams:
            for label, eligible, strength_key, scale in (
                ("receiving_competition", {"RB", "WR", "TE"}, "receiving", w["receiving_competition"]),
                ("rushing_competition", {"QB", "RB"}, "rushing", w["rushing_competition"]),
            ):
                group = sorted(p["player_id"] for p in players if p["team"] == team
                               and p["position"] in eligible and roles[p["player_id"]][strength_key] > 0)
                for i, left in enumerate(group):
                    for right in group[i+1:]:
                        key = f"{label}:{left}:{right}"
                        scale_pair = scale / math.sqrt(len(group)-1)
                        f[left][key] = scale_pair * roles[left][strength_key]
                        f[right][key] = -scale_pair * roles[right][strength_key]
    for factors in f.values():
        if sum(v*v for v in factors.values()) >= 1:
            raise ValueError("Invalid factor variance")
    return f, roles


def score_candidates(players, candidates, *, unknown_role=.5, competition=True):
    pool = {p["player_id"]: p for p in players}
    factors, roles = factor_model(players, unknown_role=unknown_role, competition=competition)
    for p in players:
        if number(p.get("mean")) is None or number(p.get("p90")) is None or p["p90"] < p["mean"]:
            raise ValueError("Finite mean <= P90 required; do not silently repair a forecast")
    output = []
    seen = set()
    for lineup in candidates:
        ids = [p["player_id"] for p in lineup]
        slots = Counter(p["roster_position"] for p in lineup)
        if len(set(ids)) != 6 or slots != {"CPT": 1, "FLEX": 5} or set(ids)-pool.keys():
            raise ValueError("Six distinct known IDs, one CPT and five FLEX required")
        sig = signature(lineup)
        if sig in seen:
            raise ValueError("Physical candidate duplicates must be removed before scoring")
        seen.add(sig)
        captain = pool[sig[0]]
        # Sigma=0 is a degenerate forecast: no tail event or conditional lift.
        sigma = (captain["p90"]-captain["mean"])/Z90
        tail = captain["mean"] + sigma * TAIL_MOMENT
        flex = []
        for pid in sorted(set(ids)-{sig[0]}):
            p = pool[pid]
            terms = {key: value*factors[pid].get(key, 0.) for key, value in factors[sig[0]].items()
                     if value*factors[pid].get(key, 0.) != 0}
            rho = sum(terms.values())
            flex_sigma = (p["p90"]-p["mean"])/Z90
            lift_scale = flex_sigma*TAIL_MOMENT if sigma > 0 else 0.
            flex.append({"player_id": pid, "name": p["name"], "position": p["position"],
                         "team": p["team"], "mean": p["mean"], "correlation_proxy": rho,
                         "conditional_lift": rho*lift_scale,
                         "conditional_mean_proxy": p["mean"]+rho*lift_scale,
                         "factor_contributions": {k: v*lift_scale for k,v in terms.items()},
                         "role_evidence": roles[pid]})
        independent = 1.5*tail + sum(p["mean"] for p in flex)
        lift = sum(p["conditional_lift"] for p in flex)
        output.append({"candidate_id": digest(sig), "captain_id": sig[0],
                       "captain": captain["name"], "captain_position": captain["position"],
                       "captain_p90_points": 1.5*captain["p90"],
                       "captain_tail_mean_points_proxy": 1.5*tail,
                       "captain_role_evidence": roles[sig[0]],
                       "tail_event_degenerate": sigma == 0,
                       "flex": flex, "flex_conditional_lift": lift,
                       "ceiling_only": independent, "captain_flex": independent+lift,
                       "saved_selector": float(lineup[0]["solver_objective_value"]),
                       "mean": sum(float(p["projection"]) for p in lineup),
                       "marginal_p90_sum": sum(float(p["p90"]) for p in lineup)})
    return output


def compare(players, candidates, *, requested, player_limits, captain_limit, quality_fraction=.95):
    """No outcomes accepted here. Identical gates/caps across all ranking arms."""
    if not candidates:
        raise ValueError("No frozen candidates")
    rows = score_candidates(players, candidates)
    best_mean = max(r["mean"] for r in rows)
    best_p90 = max(r["marginal_p90_sum"] for r in rows)
    for row in rows:
        row["quality_eligible"] = (row["mean"]+1e-8 >= quality_fraction*best_mean
            and row["marginal_p90_sum"]+1e-8 >= quality_fraction*best_p90)
    by_id = {r["candidate_id"]: r for r in rows}
    variants = {}
    for label, scores in (
        ("saved_selector", [r["saved_selector"] for r in rows]),
        ("ceiling_only", [r["ceiling_only"] for r in rows]),
        ("captain_flex", [r["captain_flex"] for r in rows]),
        ("half_dependence", [r["ceiling_only"]+.5*r["flex_conditional_lift"] for r in rows]),
        ("unknown_roles_low", [r["captain_flex"] for r in score_candidates(players, candidates, unknown_role=0.)]),
        ("unknown_roles_high", [r["captain_flex"] for r in score_candidates(players, candidates, unknown_role=1.)]),
        ("no_competition", [r["captain_flex"] for r in score_candidates(players, candidates, competition=False)]),
    ):
        copies = deepcopy(candidates)
        for lineup, score in zip(copies, scores):
            lineup[0]["solver_objective_value"] = score
        selected, report = select_showdown_portfolio(copies, requested=requested,
            player_limits=player_limits, captain_limit=captain_limit, quality_fraction=quality_fraction)
        selected_ids = [digest(signature(l)) for l in selected]
        variants[label] = {"selected_ids": selected_ids, "selected_count": len(selected_ids),
            "captains": [by_id[i]["captain"] for i in selected_ids],
            "mean_sum": sum(by_id[i]["mean"] for i in selected_ids),
            "quality_eligible_count": report["quality_eligible_count"],
            "best_unscreened_candidate_id": rows[max(range(len(rows)), key=lambda i: scores[i])]["candidate_id"]}
    return {"policy_id": POLICY_ID, "production_promotion_eligible": False,
            "factor_priors": FACTOR_PRIORS, "rows": rows, "variants": variants,
            "unknown_role_player_ids": [p["player_id"] for p in players if role(p)["unknown"]],
            "controls": {"requested": requested, "player_limits": player_limits,
                         "captain_limit": captain_limit, "quality_fraction": quality_fraction}}
