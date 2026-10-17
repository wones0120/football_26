"""One optimal legal construction per frozen pregame captain, in P90 order."""

import math

import pulp


def solve_captain_coverage(pool, *, solve, solve_kwargs, shortlist, exposure_rates,
                          max_exposure, requested_captain_id=None,
                          single_lineup_controls=None, cutoff=None):
    def user_constraints(model, frame, selected):
        if single_lineup_controls is None:
            return
        from .single_lineup import apply_lineup_constraints
        apply_lineup_constraints(model, frame, selected, single_lineup_controls, cutoff=cutoff)

    reference = solve(pool, **solve_kwargs, additional_constraints=user_constraints)

    def totals(lineup):
        return {key: sum(float(row.get(key) or 0) for row in lineup)
                for key in ("projection", "p90")}

    reference_totals = totals(reference or [])
    floors = {"projection": reference_totals["projection"] * .85,
              "p90": reference_totals["p90"] * .90}
    report = {"mode": "four_captains_25_percent", "requested_lineups": 4,
              "quality_floor_policy": "diagnostic_only", "reference_totals": reference_totals,
              "quality_floors": floors, "captains": [], "underfill": 0}
    results, counts = [], {}
    for captain in shortlist:
        pid = captain["player_id"]
        entry = {"player_id": pid, "name": captain.get("name"), "status": "infeasible"}
        report["captains"].append(entry)
        if requested_captain_id and requested_captain_id != pid:
            entry["reason"] = f"Locked captain {requested_captain_id} conflicts with shortlisted captain {pid}"
            continue
        remaining = {}
        for row in pool.to_dict("records"):
            rate = max_exposure
            if exposure_rates is not None:
                role = "core"
                if row.get("position") == "QB" and row.get("showdown_qb_eligible"):
                    role = "starting_qb"
                elif float(row["salary"]) <= 1000:
                    role = "cheap_punt"
                rate = exposure_rates[role]
            remaining[str(row["player_id"])] = max(1, math.ceil(4 * rate)) - counts.get(str(row["player_id"]), 0)

        def coverage_constraints(model, frame, selected):
            user_constraints(model, frame, selected)
            if single_lineup_controls is None:
                return
            from .single_lineup import appearance_limit, elevated_player
            from .classic_portfolio_controls import explicit_appearance_limit
            controls = single_lineup_controls
            locks = set(controls.get("locked_player_ids") or [])
            for i, row in frame.iterrows():
                player_id = str(row["player_id"])
                rate = 1.0 if player_id in locks else controls.get("max_exposure", 1.0)
                if player_id not in locks:
                    role = "core_player_max_exposure"
                    if row.get("position") == "QB" and row.get("showdown_qb_eligible"):
                        role = "starting_qb_max_exposure"
                    elif float(row["salary"]) <= 1000:
                        role = "cheap_punt_max_exposure"
                    rate = min(rate, controls.get(role, 1.0))
                rate = min(rate, (controls.get("maximum_exposure_by_player") or {}).get(player_id, 1.0))
                limit = appearance_limit(4, rate)
                if controls.get("elevated_player_max_exposure") is not None and elevated_player(row, cutoff):
                    limit = min(limit, explicit_appearance_limit(4, controls["elevated_player_max_exposure"]))
                if counts.get(player_id, 0) >= limit:
                    model += selected[i] == 0, f"user_exposure_{i}"
            overlap = controls.get("max_lineup_overlap")
            if controls.get("minimum_uniqueness") is not None:
                derived = 6 - controls["minimum_uniqueness"]
                overlap = derived if overlap is None else min(overlap, derived)
            if overlap is not None:
                for number, prior in enumerate(results):
                    ids = {str(row["player_id"]) for row in prior}
                    model += pulp.lpSum(selected[i] for i in frame.index
                                        if str(frame.loc[i, "player_id"]) in ids) <= overlap, f"user_overlap_{number}"

        diagnostics = {}
        lineup = solve(pool, **solve_kwargs, locked_captain_player_id=pid,
                       exposure_remaining=remaining if single_lineup_controls is None else None,
                       infeasibility_diagnostics=diagnostics, additional_constraints=coverage_constraints)
        if not lineup:
            entry.update(diagnostics)
            if diagnostics.get("solver_status") not in (None, "Infeasible"):
                entry["status"] = "solver_failed"
            entry.setdefault("reason", "No legal construction under the active hard constraints")
            continue
        values = totals(lineup)
        entry.update({"status": "selected", "lineup_number": len(results) + 1,
                      "totals": values,
                      "projection_gap": {key: reference_totals[key] - values[key] for key in values},
                      "quality_floor_warnings": [
                          {"metric": key, "value": values[key], "floor": floors[key],
                           "gap": floors[key] - values[key]}
                          for key in values if values[key] < floors[key] - 1e-6]})
        for row in lineup:
            player_id = str(row["player_id"])
            counts[player_id] = counts.get(player_id, 0) + 1
        results.append(lineup)
    report["underfill"] = 4 - len(results)
    report["missing_eligible_captains"] = max(0, 4 - len(shortlist))
    for lineup in results:
        # Attach to every row because final validation sorts CPT/FLEX rows.
        for row in lineup:
            row["showdown_captain_coverage"] = report
    return results, report
