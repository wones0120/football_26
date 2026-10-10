"""Certify corrected frozen portfolios without changing production controls."""
from pathlib import Path
import argparse
from copy import deepcopy
import pulp
from scripts.run_showdown_qb_policy_experiment import read, write, POLICIES, TEAM_LIMITS, solver
from scripts.audit_showdown_qb_policy_feasibility import finite_joint, policy_model, quality_expressions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    d = parser.parse_args().directory
    snapshot = read(d / "prepared_input.json")
    universe = read(d / "ranked-universe.json")
    result = {}
    for label in POLICIES:
        run = read(d / f"controlled-{label}.json")
        report = run["selection_report"]
        thresholds = {"mean": report["best_mean"], "p90": report["best_p90"]}
        snapshot["control_raw_maxima"] = {"mean": read(d / "controlled-A.json")["selection_report"]["best_mean"],
                                         "p90": read(d / "controlled-A.json")["selection_report"]["best_p90"]}
        maxima = {}
        for field in ("projection", "p90"):
            model, cap, flex = policy_model(snapshot, label)
            model.setObjective(quality_expressions(snapshot, cap, flex)[field])
            assert model.solve(solver()) == pulp.LpStatusOptimal
            maxima[field] = pulp.value(model.objective)
        assert abs(maxima["projection"] - thresholds["mean"]) < 1e-5
        assert abs(maxima["p90"] - thresholds["p90"]) < 1e-5
        allow, maximum = POLICIES[label]
        eligible = [r for r in universe["rows"] if (allow or r["captain_position"] != "QB")
            and r["qb_count"] <= maximum and max(r["team_counts"].values()) <= TEAM_LIMITS.get(label, 5)
            and min(r["mean"] / thresholds["mean"], r["p90"] / thresholds["p90"]) >= .95 - 1e-8]
        support = {}
        for count in range(5, 0, -1):
            outcome, model = finite_joint(deepcopy(universe), snapshot, label, thresholds,
                run["selection_kwargs"]["player_limits"], run["selection_kwargs"]["captain_limit"], count=count)
            support[count] = outcome
            if outcome["status"] == "Optimal":
                # Rebuild after the feasibility solve: PuLP's constant objective
                # introduces a dummy column which CBC cannot reuse here.
                selector_model = pulp.LpProblem("CorrectedPortfolioSelector", pulp.LpMaximize)
                for name, constraint in model.constraints.items():
                    selector_model.addConstraint(constraint, name)
                selector_model.setObjective(pulp.lpSum(model.variablesDict()[f"roster_{i}"] * row["selector"]
                                                       for i, row in enumerate(eligible)))
                assert selector_model.solve(solver()) == pulp.LpStatusOptimal
                optimum = pulp.value(selector_model.objective)
                selected_rows = [row for i, row in enumerate(eligible)
                                 if selector_model.variablesDict()[f"roster_{i}"].value() > .5]
                break
        required = set.intersection(*(set(r["player_ids"]) for r in eligible)) if eligible else set()
        names = {r["player_id"]: r["name"] for r in snapshot["player_pool"]}
        result[label] = dict(raw_maxima=maxima, exact_maximum_count=count,
            discovered_selected_count=len(run["selected"]), complete_quality_signatures=len(eligible),
            global_optimal_selector=optimum,
            globally_selected_witness=selected_rows,
            selector_gap_at_same_count=optimum - report["selected_portfolio_selector"] if count == len(run["selected"]) else None,
            mandatory_players=[dict(player_id=pid, name=names[pid], cap=run["selection_kwargs"]["player_limits"][pid]) for pid in sorted(required)],
            count_feasibility=support)
        print(label, result[label]["exact_maximum_count"], result[label]["mandatory_players"], flush=True)
    write(d / "corrected_feasibility.json", result)


if __name__ == "__main__": main()
