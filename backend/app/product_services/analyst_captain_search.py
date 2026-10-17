"""Bounded Captain/FLEX alternatives on an unchanged scenario legal model."""
from collections import Counter

import pulp

POLICY_ID = 'analyst_eligible_captain_support_v1'
MAX_SOLVES = 128
SOLVE_SECONDS = 5


def broaden_captains(*, scenarios, rows, mapping, candidates, scenario_model, solver, per_captain):
    """Search every legal Captain without requiring its eventual selection.

    Each story/Captain gets multiple best remaining supporting rosters. Existing
    candidates count toward that target. Canonical identities and roles define
    uniqueness; no-good cuts alter only discovery, never the captured legal model.
    """
    target = max(2, per_captain)
    eligible = {str(r['player_id']) for r in rows if r.get('showdown_captain_shortlisted') is not False}
    captain_names = {ref['player_master_id']: name for name, ref in mapping.items()
                     if ref['role'] == 'CPT' and ref['player_master_id'] in eligible}
    pairs = [(scenario, pid) for scenario in scenarios for pid in sorted(captain_names)
             if not scenario.get('captain_player_master_id') or scenario['captain_player_master_id'] == pid]
    attempts = []
    states = {}
    for scenario, pid in pairs:
        sid = scenario['scenario_id']
        retained = [signature for signature, candidate in candidates.items()
                    if sid in candidate['scenario_ids'] and (pid, 'CPT') in signature]
        states[(sid, pid)] = dict(retained=retained, terminal=None)
    # Round-robin passes give every Captain/story a first look before extras.
    for _ in range(target):
        for scenario, pid in pairs:
            sid = scenario['scenario_id']
            state = states[(sid, pid)]
            if state['terminal'] or len(state['retained']) >= target:
                continue
            if len(attempts) >= MAX_SOLVES:
                break
            variables, model = scenario_model(scenario)
            model += variables[captain_names[pid]] == 1, 'analyst_search_fixed_captain'
            names_by_ref = {(ref['player_master_id'], ref['role']): name for name, ref in mapping.items()}
            for index, signature in enumerate(state['retained']):
                chosen = [names_by_ref[ref] for ref in signature]
                model += pulp.lpSum(variables[name] for name in chosen) <= len(chosen) - 1, f'analyst_search_unique_{index}'
            backend = solver()
            backend.timeLimit = SOLVE_SECONDS
            model.solve(backend)
            attempt = dict(scenario_id=sid, phase='captain_support_search',
                           captain_player_master_id=pid, attempt=len(state['retained']) + 1,
                           solver_status=(pulp.LpStatus[model.status] if model.sol_status == pulp.LpSolutionOptimal
                                          else 'FeasibleNotProvenOptimal' if model.sol_status == pulp.LpSolutionIntegerFeasible
                                          else pulp.LpStatus[model.status]))
            attempts.append(attempt)
            if model.status != pulp.LpStatusOptimal or model.sol_status != pulp.LpSolutionOptimal:
                state['terminal'] = attempt['solver_status']
                continue
            chosen = [name for name in mapping if pulp.value(variables[name]) > .5]
            signature = tuple(sorted((mapping[name]['player_master_id'], mapping[name]['role']) for name in chosen))
            candidate = candidates.setdefault(signature, dict(roster=[mapping[name] for name in chosen], scenario_ids=[]))
            if sid not in candidate['scenario_ids']:
                candidate['scenario_ids'].append(sid)
            state['retained'].append(signature)
            attempt['conditional_objective'] = float(pulp.value(model.objective))
        if len(attempts) >= MAX_SOLVES:
            break
    coverage = [dict(scenario_id=sid, captain_player_master_id=pid,
                     distinct_supporting_rosters=len(state['retained']),
                     status=state['terminal'] or ('target_reached' if len(state['retained']) >= target else 'budget_exhausted'))
                for (sid, pid), state in states.items()]
    return attempts, dict(policy_id=POLICY_ID, supporting_rosters_per_captain=target, planned_supporting_slots=len(pairs) * target,
                          maximum_solves=MAX_SOLVES, maximum_seconds_per_solve=SOLVE_SECONDS, solves_used=len(attempts),
                          budget_exhausted=any(row['status'] == 'budget_exhausted' for row in coverage),
                          eligible_captain_ids=sorted(captain_names),
                          solver_status_counts=dict(Counter(row['solver_status'] for row in attempts)),
                          coverage=coverage, candidate_count=len(candidates),
                          eligibility_policy='Existing opportunity, user preference, identity and story constraints remain binding; no Captain diversity requirement or quality filler.')
