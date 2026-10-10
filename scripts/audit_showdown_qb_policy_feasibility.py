"""Exact saved-model feasibility and reporting diagnostics; no live optimizer changes."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from itertools import combinations
import math
from pathlib import Path
from statistics import mean
from time import monotonic

import pandas as pd
import pulp

from backend.app.product_services.rule_library import resolve_strategy_profile
from backend.app.product_services.showdown_portfolio_selection import candidate_metrics, signature
from scripts.research_showdown_prelock import render_solution, thesis
from scripts.run_showdown_qb_policy_experiment import POLICIES, TEAM_LIMITS, read, write, solver


def policy_model(snapshot, label):
    variables, model = pulp.LpProblem.from_dict(deepcopy(snapshot["solver_model"]))
    players = snapshot["player_pool"]
    cap = {i: variables[f"captain_{i}"] for i in range(len(players))}
    flex = {i: variables[f"flex_{i}"] for i in range(len(players))}
    qbs = [i for i, row in enumerate(players) if row["position"] == "QB"]
    allow, maximum = POLICIES[label]
    if not allow:
        for i in qbs:
            model += cap[i] == 0
    model += pulp.lpSum(cap[i] + flex[i] for i in qbs) <= maximum
    if label in TEAM_LIMITS:
        for team in {row["player_team"] for row in players}:
            model += pulp.lpSum(cap[i] + flex[i] for i, row in enumerate(players)
                                if row["player_team"] == team) <= TEAM_LIMITS[label]
    return model, cap, flex


def quality_expressions(snapshot, cap, flex):
    return {field: pulp.lpSum(float(row[field]) * (1.5 * cap[i] + flex[i])
                             for i, row in enumerate(snapshot["player_pool"])) for field in ("projection", "p90")}


def solve(model):
    started = monotonic()
    status = model.solve(solver())
    return {"status": pulp.LpStatus[status], "seconds": monotonic() - started,
            "objective": pulp.value(model.objective) if status == pulp.LpStatusOptimal else None}


def joint(snapshot, label, thresholds, limits, captain_limit, *, count=5, maximize_quality=False):
    """Five independent copies of the *complete* lineup model, with joint capacities."""
    model = pulp.LpProblem("FullUniverseQBPortfolio", pulp.LpMaximize)
    caps, flexes, objectives = [], [], []
    quality = pulp.LpVariable("joint_quality_fraction", lowBound=0, upBound=.95) if maximize_quality else .95
    for entry in range(count):
        local, cap, flex = policy_model(snapshot, label)
        for variable in local.variables():
            variable.name = f"entry_{entry}_{variable.name}"
        for number, constraint in enumerate(local.constraints.values()):
            model += constraint, f"entry_{entry}_constraint_{number}"
        expressions = quality_expressions(snapshot, cap, flex)
        model += expressions["projection"] >= quality * thresholds["mean"] - 1e-7
        model += expressions["p90"] >= quality * thresholds["p90"] - 1e-7
        caps.append(cap); flexes.append(flex); objectives.append(local.objective)
    for i, row in enumerate(snapshot["player_pool"]):
        pid = str(row["player_id"])
        model += pulp.lpSum(caps[e][i] + flexes[e][i] for e in range(count)) <= limits.get(pid, count)
        model += pulp.lpSum(caps[e][i] for e in range(count)) <= captain_limit
    # Signature is Captain identity plus six canonical IDs, matching production.
    for left, right in combinations(range(count), 2):
        same = []
        for role, family in (("captain", caps), ("flex", flexes)):
            for i in range(len(snapshot["player_pool"])):
                both = pulp.LpVariable(f"same_{left}_{right}_{role}_{i}", cat="Binary")
                model += both <= family[left][i]
                model += both <= family[right][i]
                model += both >= family[left][i] + family[right][i] - 1
                same.append(both)
        model += pulp.lpSum(same) <= 5
    # Identical entries can be permuted by Captain without changing feasibility.
    for entry in range(count - 1):
        model += pulp.lpSum(i * caps[entry][i] for i in caps[entry]) <= pulp.lpSum(i * caps[entry+1][i] for i in caps[entry+1])
    # Feasibility needs a certificate, not an unnecessary best-selector portfolio.
    model += quality if maximize_quality else 0
    outcome = solve(model)
    outcome["count"] = count
    if outcome["status"] == "Optimal":
        outcome["quality_fraction"] = quality.value() if maximize_quality else quality
        outcome["witness"] = [{"captain_player_id": next(str(row["player_id"]) for i, row in enumerate(snapshot["player_pool"]) if caps[e][i].value() > .5),
                                "player_ids": sorted(str(row["player_id"]) for i, row in enumerate(snapshot["player_pool"])
                                                     if caps[e][i].value() + flexes[e][i].value() > .5)} for e in range(count)]
    return outcome, model


def exposure_report(lineups, snapshot, limits, captain_limit):
    requested, generated = 5, len(lineups)
    counts = Counter(pid for lineup in lineups for pid in signature(lineup)[1])
    captains = Counter(signature(lineup)[0] for lineup in lineups)
    params = snapshot["fixed_parameters"]
    rows = []
    for player in snapshot["player_pool"]:
        pid = str(player["player_id"])
        rate = params["starting_qb_max_exposure"] if player["position"] == "QB" else params["cheap_punt_max_exposure"] if player["salary"] <= 1000 else params["core_player_max_exposure"]
        for kind, appearances, fraction, cap in (("player", counts[pid], rate, limits[pid]),
                                                 ("captain", captains[pid], params["captain_max_exposure"], captain_limit)):
            realized = appearances / generated if generated else None
            warning = bool(generated < requested and realized is not None and realized > fraction + 1e-8)
            rows.append({"player_id": pid, "name": player["name"], "kind": kind, "configured_fraction": fraction,
                         "requested_denominator": requested, "appearance_cap": cap, "appearances": appearances,
                         "requested_count_compliant": appearances <= cap, "final_denominator": generated,
                         "realized_fraction": realized, "underfill_realized_exceeds_configured": warning,
                         "warning": "UNDERFILLED PORTFOLIO — requested-count cap passed, but realized final exposure exceeds configured percentage." if warning else None})
    return rows


def finite_joint(universe, snapshot, label, thresholds, limits, captain_limit, *,
                 count=5, maximize_quality=False, additional_captain_ids=(), only_relaxed_ids=()):
    """Exact joint solve over exhaustively certified quality-relevant signatures."""
    allow, maximum = POLICIES[label]
    control = snapshot["control_raw_maxima"]
    omitted_quality_upper_bound = .88 * max(control["mean"]/thresholds["mean"], control["p90"]/thresholds["p90"])
    assert omitted_quality_upper_bound < .95 - 1e-8
    rows = [row for row in universe["rows"]
            if (allow or row["captain_position"] != "QB" or row["captain_player_id"] in additional_captain_ids)
            and row["qb_count"] <= maximum
            and max(row["team_counts"].values()) <= TEAM_LIMITS.get(label, 5)]
    for row in rows:
        row["policy_quality"] = min(row["mean"]/thresholds["mean"], row["p90"]/thresholds["p90"])
    if not maximize_quality:
        rows = [row for row in rows if row["policy_quality"] >= .95 - 1e-8]
    model = pulp.LpProblem("ExhaustiveQualityUniversePortfolio", pulp.LpMaximize)
    selected = [pulp.LpVariable(f"roster_{i}", cat="Binary") for i in range(len(rows))]
    model += pulp.lpSum(selected) == count
    for player in snapshot["player_pool"]:
        pid = str(player["player_id"])
        model += pulp.lpSum(v for v,row in zip(selected,rows) if pid in row["player_ids"]) <= limits[pid]
        model += pulp.lpSum(v for v,row in zip(selected,rows) if pid == row["captain_player_id"]) <= captain_limit
    if maximize_quality:
        quality = pulp.LpVariable("quality_fraction", lowBound=.88, upBound=.95)
        for v,row in zip(selected,rows):
            model += quality <= row["policy_quality"] + (1-v)
        model += quality
    else:
        model += 0
    result = solve(model)
    result.update(count=count, exhaustive_eligible_rosters=len(rows), method="Exhaustive certified signature universe; one binary per physical signature")
    if result["status"] == "Optimal":
        result["witness"] = [row for v,row in zip(selected,rows) if v.value() > .5]
        result["quality_fraction"] = quality.value() if maximize_quality else .95
        if maximize_quality:
            result["omitted_quality_upper_bound"] = omitted_quality_upper_bound
            result["omitted_rosters_cannot_improve_optimum"] = result["quality_fraction"] > omitted_quality_upper_bound
            assert result["omitted_rosters_cannot_improve_optimum"]
    return result, model


def diversity(lineups, snapshot):
    players = {str(row["player_id"]): row for row in snapshot["player_pool"]}
    ids = [set(signature(lineup)[1]) for lineup in lineups]
    overlaps = [len(left & right) for left, right in combinations(ids, 2)]
    jaccards = [len(left & right) / len(left | right) for left, right in combinations(ids, 2)]
    counts = Counter(pid for roster in ids for pid in roster)
    cpts = Counter(signature(lineup)[0] for lineup in lineups)
    n = len(lineups)
    metrics = [candidate_metrics(lineup) for lineup in lineups]
    return {"generated": n, "requested": 5, "avg_mean": mean(row["baseline_mean"] for row in metrics) if n else None,
            "avg_p90": mean(row["baseline_p90"] for row in metrics) if n else None,
            "portfolio_selector": sum(row["selector"] for row in metrics), "unique_captains": len(cpts), "unique_players": len(counts),
            "avg_shared_players": mean(overlaps) if overlaps else None, "max_shared_players": max(overlaps, default=None),
            "min_shared_players": min(overlaps, default=None), "avg_jaccard": mean(jaccards) if jaccards else None,
            "player_exposure_hhi": sum((count/(6*n))**2 for count in counts.values()) if n else None,
            "core_players": [{"player_id": pid, "name": players[pid]["name"]} for pid,count in counts.items() if count == n],
            "pct_unique_players_in_all_entries": sum(count == n for count in counts.values()) / len(counts) if counts else None,
            "max_player_exposure": max(counts.values(), default=0) / n if n else None,
            "qb_captain_exposure": sum(count for pid,count in cpts.items() if players[pid]["position"] == "QB") / n if n else None,
            "two_qb_exposure": sum(sum(players[pid]["position"] == "QB" for pid in roster) == 2 for roster in ids) / n if n else None,
            "captain_position_distribution": dict(Counter(players[signature(l)[0]]["position"] for l in lineups)),
            "captain_distribution": {players[pid]["name"]: count for pid,count in cpts.items()},
            "qb_count_distribution": dict(Counter(sum(players[pid]["position"] == "QB" for pid in roster) for roster in ids)),
            "team_split_distribution": dict(Counter(row["team_split"] for row in metrics)),
            "game_script_distribution": dict(Counter(thesis(lineup) for lineup in lineups)),
            "scenario_discovery_distribution": dict(Counter(row["scenario_id"] for row in metrics)),
            "pairwise_score_correlation": None, "correlation_limitation": "No frozen joint score-draw matrix; roster overlap is not score correlation",
            "player_appearances": {players[pid]["name"]: count for pid,count in counts.items()}}


def feasibility(directory, label):
    path = directory / f"feasibility-{label}.json"
    if path.exists():
        return read(path)
    snapshot = read(directory / "prepared_input.json")
    control_report = read(directory / "controlled-A.json")["selection_report"]
    snapshot["control_raw_maxima"] = {"mean": control_report["best_mean"], "p90": control_report["best_p90"]}
    run = read(directory / f"controlled-{label}.json")
    thresholds = {"mean": run["selection_report"]["best_mean"], "p90": run["selection_report"]["best_p90"]}
    limits = run["selection_kwargs"]["player_limits"]
    captain_limit = run["selection_kwargs"]["captain_limit"]
    raw_maxima = {}
    for field in ("projection", "p90"):
        local, cap, flex = policy_model(snapshot, label)
        local.setObjective(quality_expressions(snapshot, cap, flex)[field])
        result = solve(local)
        assert result["status"] == "Optimal"
        raw_maxima[field] = result["objective"]
    required = []
    for i, player in enumerate(snapshot["player_pool"]):
        if limits[str(player["player_id"])] >= 5:
            continue
        local, cap, flex = policy_model(snapshot, label)
        quality = pulp.LpVariable("fraction_without_player", lowBound=0, upBound=2)
        expressions = quality_expressions(snapshot, cap, flex)
        local += cap[i] + flex[i] == 0
        local += expressions["projection"] >= quality * thresholds["mean"]
        local += expressions["p90"] >= quality * thresholds["p90"]
        local.setObjective(quality)
        result = solve(local)
        if result["status"] == "Infeasible" or result["objective"] < .95 - 1e-7:
            required.append({"player_id": str(player["player_id"]), "name": player["name"], "appearance_cap": limits[str(player["player_id"])],
                             "best_joint_quality_without_player": result["objective"], "solve_status": result["status"]})
    universe = read(directory / "ranked-universe.json")
    result, model = finite_joint(universe, snapshot, label, thresholds, limits, captain_limit)
    model.writeLP(str(directory / f"full-universe-{label}.lp"))
    output = {"policy": label, "thresholds": thresholds, "full_legal_raw_maxima": raw_maxima,
              "raw_maxima_match_candidate_benchmark": abs(raw_maxima["projection"]-thresholds["mean"]) < 1e-5 and abs(raw_maxima["p90"]-thresholds["p90"]) < 1e-5,
              "mandatory_quality_players": required, "five_entry_feasibility": result, "diagnostic_relaxations": {}}
    if result["status"] == "Infeasible":
        assert len(run["selected"]) == 4
        output["maximum_portfolio_size_proven"] = 4  # Saved four-entry witness + exact five-entry infeasibility.
        relaxed, _ = finite_joint(universe, snapshot, label, thresholds, limits, captain_limit, maximize_quality=True)
        output["diagnostic_relaxations"]["quality_floor_only"] = relaxed
        # Single-factor diagnostics, never used by the reported production portfolio.
        core_limits = {pid: 5 if limit == 4 else limit for pid,limit in limits.items()}
        relaxed, _ = finite_joint(universe, snapshot, label, thresholds, core_limits, captain_limit)
        output["diagnostic_relaxations"]["core_player_cap_appearance_4_to_5"] = relaxed
        relaxed, _ = finite_joint(universe, snapshot, label, thresholds, limits, captain_limit+1)
        output["diagnostic_relaxations"]["captain_cap_appearance_3_to_4"] = relaxed
        mandatory_ids = [row["player_id"] for row in required]
        mandatory_limits = {pid: 5 if pid in mandatory_ids else limit for pid,limit in limits.items()}
        relaxed, _ = finite_joint(universe, snapshot, label, thresholds, mandatory_limits, captain_limit)
        output["diagnostic_relaxations"]["only_mandatory_player_caps_4_to_5"] = relaxed
        for player in snapshot["player_pool"]:
            if player["position"] == "QB":
                relaxed, _ = finite_joint(universe, snapshot, label, thresholds, limits, captain_limit,
                                         additional_captain_ids=[player["player_id"]])
                output["diagnostic_relaxations"][f"allow_only_additional_qb_captain_{player['name']}"] = relaxed
    else:
        assert result["status"] == "Optimal"
        output["maximum_portfolio_size_proven"] = 5
    write(path, output)
    print(label, {"full_universe": result["status"], "mandatory_players": [row["name"] for row in required],
                  "raw_maxima_match": output["raw_maxima_match_candidate_benchmark"]}, flush=True)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--policy", choices=list(POLICIES))
    args = parser.parse_args()
    for label in ([args.policy] if args.policy else POLICIES):
        feasibility(args.directory, label)


if __name__ == "__main__":
    main()
