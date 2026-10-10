from copy import deepcopy

import pulp
import pytest

from scripts.enumerate_showdown_policy_universe import certify
from scripts.run_showdown_qb_policy_experiment import solver
from scripts.audit_showdown_qb_policy_feasibility import finite_joint


def test_binary_certificate_agrees_with_independent_fixed_roster_solve():
    model = pulp.LpProblem("certificate", pulp.LpMaximize)
    captain = pulp.LpVariable("captain_0", cat="Binary")
    flex = pulp.LpVariable("flex_1", cat="Binary")
    interaction = pulp.LpVariable("interaction", cat="Binary")
    model += interaction <= captain
    model += interaction <= flex
    model += interaction >= captain + flex - 1
    model += captain + flex == 2
    model += 12 * captain + 10 * flex - 3 * interaction
    serialized = model.to_dict()
    score = certify(serialized, 0, [0, 1])
    variables, independent = pulp.LpProblem.from_dict(deepcopy(serialized))
    independent += variables["captain_0"] == 1
    independent += variables["flex_1"] == 1
    assert independent.solve(solver()) == pulp.LpStatusOptimal
    assert score == pytest.approx(pulp.value(independent.objective))
    assert certify(serialized, 0, [0]) is None


def test_exhaustive_joint_audit_distinguishes_underfill_and_diagnostic_relaxation():
    rows = [{"captain_player_id": "c1" if i < 3 else "c2",
             "captain_position": "WR", "qb_count": 1,
             "player_ids": ["mandatory", "c1" if i < 3 else "c2", f"other{i}"],
             "team_counts": {"SEA": 3, "SF": 3}, "mean": 100, "p90": 150}
            for i in range(5)]
    ids = {pid for row in rows for pid in row["player_ids"]}
    snapshot = {"player_pool": [{"player_id": pid} for pid in ids],
                "control_raw_maxima": {"mean": 100, "p90": 150}}
    limits = {pid: 4 if pid == "mandatory" else 5 for pid in ids}
    thresholds = {"mean": 100, "p90": 150}
    result, _ = finite_joint({"rows": rows}, snapshot, "C", thresholds, limits, 3)
    assert result["status"] == "Infeasible"
    result, _ = finite_joint({"rows": rows}, snapshot, "C", thresholds, limits, 3, count=4)
    assert result["status"] == "Optimal"
    result, _ = finite_joint({"rows": rows}, snapshot, "C", thresholds,
                             {**limits, "mandatory": 5}, 3)
    assert result["status"] == "Optimal"
    assert len(result["witness"]) == 5
