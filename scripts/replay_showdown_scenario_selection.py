"""Selection-only replay of saved candidates. No DB, imports, or lineup solve.

Run with: .venv/bin/python -m scripts.replay_showdown_scenario_selection
Old reports did not retain conditional selector totals, so alternative B uses
an explicitly labeled 20% marginal-ceiling uplift proxy, not a made-up score.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

import pulp

from backend.app.product_services.showdown_portfolio_selection import select_showdown_portfolio, signature
from backend.app.product_services.showdown_scenario_value import scenario_credits

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts/showdown_scenario_selection"


def restore(saved: dict, requested: int | None = None):
    report = next(p["captain_family_coverage_report"] for l in saved["results"] for p in l
                  if p.get("captain_family_coverage_report"))
    if report.get("quality_basis") != "common_baseline":
        raise ValueError("Pre-restoration report: conditional selectors were not retained on a common baseline")
    exposure = next(p["portfolio_exposure_report"] for l in saved["results"] for p in l
                    if p.get("portfolio_exposure_report"))
    requested = requested or exposure["requested_lineups"]
    pool = {p["player_id"]: p for p in saved["player_pool"]["rows"]}
    rates = {p["exposure_class"]: p["configured_cap"] for p in exposure["rows"]}
    limits = {pid: max(1, math.ceil(requested * rates.get(
        "starting_qb" if p["position"] == "QB" else "cheap_punt" if p["salary"] <= 1000 else "core",
        1.0 if p["position"] == "QB" else 0.4 if p["salary"] <= 1000 else 0.8)))
        for pid, p in pool.items()}
    candidates = []
    for m in report["ranked_metrics"]:
        if not m.get("players"):
            raise ValueError("Saved report has no retained roster: cannot replay honestly")
        rows = []
        for p in m["players"]:
            a = p.get("adjustment") or {}
            rows.append({"player_id": p["player_id"], "name": p["name"],
                         "player_team": p["team"], "roster_position": p["slot"],
                         "projection": a["baseline_mean"], "p90": a["baseline_p90"],
                         "conditioned_projection": a["scenario_mean"], "conditioned_p90": a["scenario_p90"],
                         "showdown_scenario_adjustment": a})
        # Salary is retained only at lineup level. This replay never solves
        # lineup legality, scores players, or exports a DraftKings entry.
        rows[0].update(salary=m["salary"], solver_objective_value=m["selector"],
                       showdown_scenario_id=m["scenario_id"], showdown_scenario=m.get("scenario"),
                       showdown_candidate_source=m["candidate_source"],
                       lineup_correlation_summary={"total_adjustment": m.get("correlation")},
                       conditioned_selector=m.get("conditioned_selector"))
        captain = next(p for p in rows if p["roster_position"] == "CPT")
        captain.update(objective_score=m.get("captain_objective_score"),
                       captain_objective_multiplier=m.get("captain_objective_multiplier"))
        assert abs(sum(p["projection"] for p in rows) - m["mean"]) < 1e-6
        assert abs(sum(p["p90"] for p in rows) - m["p90"]) < 1e-6
        for field, key in [("conditioned_mean", "conditioned_projection"), ("conditioned_p90", "conditioned_p90")]:
            if m.get(field) is None:
                m[field] = sum(p[key] for p in rows)
        candidates.append(rows)
    return report, candidates, limits, max(1, math.ceil(requested * exposure["configured_captain_cap"]))


def prototype(metrics, candidates, limits, captain_limit, requested, *, policy="A", floor=0.95):
    eligible = [i for i, m in enumerate(metrics) if
                m["baseline_mean"] >= floor * max(r["baseline_mean"] for r in metrics) - 1e-8 and
                m["baseline_p90"] >= floor * max(r["baseline_p90"] for r in metrics) - 1e-8]
    def solve(credits=None, blend=False):
        model = pulp.LpProblem("FrozenScenarioAB", pulp.LpMaximize)
        x = {i: pulp.LpVariable(f"x_{i}", cat="Binary") for i in eligible}
        scores = {i: metrics[i]["selector"] + (0.2 * (metrics[i]["conditioned_p90"] -
                   metrics[i]["baseline_p90"]) if blend else 0) for i in eligible}
        reward_vars = {i: pulp.LpVariable(f"reward_{i}", cat="Binary") for i in eligible
                       if credits and credits[i]["credit"] > 0}
        for i, y in reward_vars.items(): model += y <= x[i]
        for family in {metrics[i]["scenario_id"] for i in reward_vars}:
            model += pulp.lpSum(y for i, y in reward_vars.items() if metrics[i]["scenario_id"] == family) <= 1
        # Count dominates even if every reward changes.
        span = sum(abs(s) for s in scores.values()) + sum(c["credit"] for c in (credits or [])) + 1
        model += 2 * span * pulp.lpSum(x.values()) + pulp.lpSum(scores[i] * x[i] for i in eligible) + pulp.lpSum(
            credits[i]["credit"] * y for i, y in reward_vars.items())
        model += pulp.lpSum(x.values()) <= requested
        for pid, cap in limits.items():
            model += pulp.lpSum(x[i] for i in eligible if pid in signature(candidates[i])[1]) <= cap
        for cpt in {m["captain_player_id"] for m in metrics}:
            model += pulp.lpSum(x[i] for i in eligible if metrics[i]["captain_player_id"] == cpt) <= captain_limit
        for sig in {signature(l) for l in candidates}:
            model += pulp.lpSum(x[i] for i in eligible if signature(candidates[i]) == sig) <= 1
        assert model.solve(pulp.PULP_CBC_CMD(msg=False)) == pulp.LpStatusOptimal
        return [i for i in eligible if x[i].value() > 0.5]
    ordinary = solve()
    credits = scenario_credits(metrics, candidates, ordinary, eligible, requested)
    return (ordinary if policy == "A" else solve(blend=True) if policy == "B" else solve(credits)), credits


def summary(indices, metrics, candidates):
    counts = Counter(p["name"] for i in indices for p in candidates[i])
    pairs = [len(set(signature(candidates[i])[1]) & set(signature(candidates[j])[1]))
             for offset, i in enumerate(indices) for j in indices[offset + 1:]]
    return {"ranks": [i + 1 for i in indices], "count": len(indices),
            "mean": sum(metrics[i]["baseline_mean"] for i in indices),
            "summed_marginal_p90_proxy": sum(metrics[i]["baseline_p90"] for i in indices),
            "selector": sum(metrics[i]["selector"] for i in indices),
            "captains": dict(Counter(metrics[i]["captain_name"] for i in indices)),
            "team_constructions": dict(Counter(metrics[i]["team_split"] for i in indices)),
            "player_appearances": dict(counts), "maximum_player_concentration": max(counts.values(), default=0),
            "scenario_labels": dict(Counter(metrics[i]["scenario_id"] for i in indices)),
            "average_pairwise_shared_players": sum(pairs) / len(pairs) if pairs else None,
            "worst_mean_fraction": min((metrics[i]["baseline_mean"] / max(m["baseline_mean"] for m in metrics)
                                        for i in indices), default=None),
            "worst_p90_fraction": min((metrics[i]["baseline_p90"] / max(m["baseline_p90"] for m in metrics)
                                       for i in indices), default=None),
            "lineups": [{"rank": i + 1, "captain": metrics[i]["captain_name"],
                         "players": [p["name"] for p in candidates[i]], "scenario": metrics[i]["scenario_id"]}
                        for i in indices]}


def main():
    output = {"method": "frozen selection only; no candidate regeneration or live imports",
              "B": "80% baseline + 20% conditional marginal-P90 uplift proxy; conditional selectors absent in saved reports",
              "oracle": "Unavailable for these retained candidate sets; no tournament EV or top-percentile claim",
              "excluded": [], "slates": []}
    for path in sorted((ARTIFACT / "reference").glob("*.json")):
        saved = json.loads(path.read_text())
        try:
            report, candidates, limits, captain_limit = restore(saved)
        except ValueError as error:
            output["excluded"].append({"slate": path.stem, "reason": str(error)})
            continue
        metrics = report["ranked_metrics"]
        result = {"slate": path.stem, "job_id": saved["job_id"], "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                  "source_observed_at": report["scenario_definitions"][0]["market_observed_at"],
                  "reference_selected_ranks": report["selected_ranks"], "variants": {}}
        for policy in ["A", "B", "C"]:
            indices, credits = prototype(metrics, candidates, limits, captain_limit, report["requested"], policy=policy)
            result["variants"][policy] = summary(indices, metrics, candidates)
        # Check the implemented selector against the frozen prototype before
        # interpreting its output. No live generation path is invoked.
        for enabled, policy in [(False, "A"), (True, "C")]:
            selected, live_report = select_showdown_portfolio(deepcopy(candidates), requested=report["requested"],
                player_limits=limits, captain_limit=captain_limit, soft_scenario_diversity=enabled)
            expected = {signature(candidates[i - 1]) for i in result["variants"][policy]["ranks"]}
            assert {signature(l) for l in selected} == expected
            live_report["scenario_definitions"] = report["scenario_definitions"]
            (ARTIFACT / f"{path.stem}-{policy}-accounting.json").write_text(json.dumps(live_report, indent=2) + "\n")
        # A must reproduce physical rosters, since baseline/scenario label ties
        # in old CBC versions can select different IDs for the same entry.
        original = {signature(candidates[i - 1]) for i in report["selected_ranks"]}
        a = {signature(candidates[i - 1]) for i in result["variants"]["A"]["ranks"]}
        assert a == original, f"Baseline replay mismatch: {path}"
        result["credits"] = [{"rank": i + 1, **c} for i, c in enumerate(credits) if metrics[i]["scenario_id"] != "baseline"]
        result["size_sensitivity"] = {}
        for n in [1, 3, 5, 10]:
            _, _, cap_limits, cpt_limit = restore(saved, n)
            result["size_sensitivity"][n] = {p: summary(prototype(metrics, candidates, cap_limits, cpt_limit, n, policy=p)[0], metrics, candidates)
                                             for p in ["A", "C"]}
        result["quality_floor_research_only"] = {}
        for floor in [0.95, 0.90, 0.85]:
            result["quality_floor_research_only"][floor] = {p: summary(prototype(metrics, candidates, limits, captain_limit,
                report["requested"], policy=p, floor=floor)[0], metrics, candidates) for p in ["A", "C"]}
        output["slates"].append(result)
    (ARTIFACT / "ab.json").write_text(json.dumps(output, indent=2) + "\n")
    for s in output["slates"]:
        print(s["slate"], {p: {k: v for k, v in r.items() if k in ["ranks", "mean", "summed_marginal_p90_proxy", "selector", "scenario_labels"]}
                           for p, r in s["variants"].items()})


if __name__ == "__main__": main()
