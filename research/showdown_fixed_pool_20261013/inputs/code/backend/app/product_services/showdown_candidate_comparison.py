"""Retain conditional discovery evidence while comparing baseline forecasts."""
from copy import deepcopy
from typing import Callable


def baseline_rescore_discovery(discovered: list[dict], solve_baseline: Callable) -> list[dict]:
    captain = next(row for row in discovered if row["roster_position"] == "CPT")
    by_id = {str(row["player_id"]): row for row in discovered}
    if len(by_id) != 6:
        raise ValueError("Conditional discovery requires six distinct canonical players")
    baseline = solve_baseline(set(by_id), str(captain["player_id"]))
    if not baseline or {(str(r["player_id"]), r["roster_position"]) for r in baseline} != {
        (str(r["player_id"]), r["roster_position"]) for r in discovered
    }:
        raise ValueError("Conditional discovery roster violates baseline legality")
    for player in baseline:
        conditional = by_id[str(player["player_id"])]
        player["conditioned_projection"] = conditional["projection"]
        player["conditioned_p90"] = conditional["p90"]
        player["conditioned_selector"] = discovered[0].get("solver_objective_value")
        player["showdown_scenario_adjustment"] = deepcopy(conditional.get("showdown_scenario_adjustment"))
        player["conditioned_correlation_summary"] = deepcopy(discovered[0].get("lineup_correlation_summary"))
        player["showdown_comparison_basis"] = "common_baseline"
    return baseline
