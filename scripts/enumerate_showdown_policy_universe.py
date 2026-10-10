"""Exhaustive roster enumeration checked against the immutable production MILP."""
from collections import Counter
from copy import deepcopy
from itertools import combinations
from pathlib import Path
import argparse
import numpy as np
import pulp
from scripts.run_showdown_qb_policy_experiment import read, write, solver
from backend.app.product_services.showdown_portfolio_selection import candidate_metrics, signature


def certify(template, captain, indices):
    """Binary interval propagation is exact when all variables resolve; CBC otherwise."""
    variables = template['variables']
    names = [v['name'] for v in variables]
    values = {v['name']: (int(v['lowBound']), int(v['upBound'])) for v in variables}
    for name in names:
        if name.startswith(('captain_', 'flex_')):
            i = int(name.split('_')[1])
            value = int(i == captain) if name.startswith('captain_') else int(i in indices and i != captain)
            if not values[name][0] <= value <= values[name][1]: return None
            values[name] = (value, value)
    constraints = template['constraints']
    def possible(c, override=None):
        low = high = float(c['constant'])
        for term in c['coefficients']:
            a = term['value']; lo, hi = override[1:] if override and term['name'] == override[0] else values[term['name']]
            low += a * (lo if a >= 0 else hi); high += a * (hi if a >= 0 else lo)
        return not (c['sense'] <= 0 and low > 1e-6 or c['sense'] >= 0 and high < -1e-6)
    for _ in range(len(names)):
        changed = False
        for c in constraints:
            if not possible(c): return None
            for term in c['coefficients']:
                name = term['name']
                if values[name][0] == values[name][1]: continue
                zero, one = possible(c, (name, 0, 0)), possible(c, (name, 1, 1))
                if not zero and not one: return None
                if zero != one:
                    value = int(one); values[name] = (value, value); changed = True
        if not changed: break
    if all(lo == hi for lo, hi in values.values()):
        return sum(term['value'] * values[term['name']][0] for term in template['objective']['coefficients'])
    vs, model = pulp.LpProblem.from_dict(deepcopy(template))
    for name, (lo, hi) in values.items():
        vs[name].lowBound = lo; vs[name].upBound = hi
    if model.solve(solver()) != pulp.LpStatusOptimal: return None
    return pulp.value(model.objective)


def enumerate_universe(directory):
    destination = directory/'ranked-universe.json'
    if destination.exists(): return read(destination)
    snapshot = read(directory/'prepared_input.json'); players = snapshot['player_pool']; model = snapshot['solver_model']
    runs = {label: read(directory/f'controlled-{label}.json') for label in 'ABCDEF' if (directory/f'controlled-{label}.json').exists()}
    cutoff = min(candidate_metrics(l)['selector'] for run in runs.values() for l in run['selected']) - 1e-6
    # Every auxiliary variable is bounded binary. This is a valid global score upper bound.
    obj = {term['name']: term['value'] for term in model['objective']['coefficients']}
    aux_bound = sum(max(0, obj.get(v['name'], 0)) for v in model['variables'] if not v['name'].startswith(('captain_', 'flex_')))
    maximum_mean = runs['A']['selection_report']['best_mean']; maximum_p90 = runs['A']['selection_report']['best_p90']
    retained, examined, candidates = [], 0, []
    for indices in combinations(range(len(players)), 6):
        base_salary = sum(players[i]['salary'] for i in indices)
        teams = Counter(players[i]['player_team'] for i in indices)
        if len(teams) != 2 or max(teams.values()) > 5: continue
        base_mean = sum(players[i]['projection'] for i in indices); base_p90 = sum(players[i]['p90'] for i in indices)
        base_obj = sum(obj[f'flex_{i}'] for i in indices)
        for captain in indices:
            if base_salary + .5*players[captain]['salary'] > 50000 + 1e-8: continue
            examined += 1
            mean = base_mean + .5*players[captain]['projection']; p90 = base_p90 + .5*players[captain]['p90']
            quality = min(mean/maximum_mean, p90/maximum_p90)
            upper = base_obj - obj[f'flex_{captain}'] + obj[f'captain_{captain}'] + aux_bound
            if upper < cutoff and quality < .88: continue
            candidates.append((captain, indices, mean, p90, upper))
    print({'salary_legal_rosters':examined,'certification_candidates':len(candidates),'global_rank_cutoff':cutoff},flush=True)
    for n, (captain, indices, mean, p90, upper) in enumerate(candidates):
        objective = certify(model, captain, indices)
        if objective is not None:
            retained.append({'captain_player_id':players[captain]['player_id'], 'player_ids':sorted(players[i]['player_id'] for i in indices),
                'indices':list(indices), 'captain_index':captain, 'selector':objective, 'mean':mean, 'p90':p90,
                'salary':sum(players[i]['salary'] for i in indices)+.5*players[captain]['salary'],
                'team_counts':dict(Counter(players[i]['player_team'] for i in indices)),
                'qb_count':sum(players[i]['position']=='QB' for i in indices), 'captain_position':players[captain]['position']})
        if (n+1)%100 == 0: print({'certified':n+1,'legal_retained':len(retained)},flush=True)
    retained.sort(key=lambda r:(-r['selector'],r['captain_player_id'],r['player_ids']))
    for row in retained:
        row['global_rank'] = 1 + sum(other['selector'] > row['selector'] + 1e-6 for other in retained)
    by_signature={(r['captain_player_id'],tuple(r['player_ids'])):r for r in retained}
    for label, run in runs.items():
        for lineup in run['selected']:
            row=by_signature[signature(lineup)]
            assert abs(row['selector']-candidate_metrics(lineup)['selector']) < 1e-5, (label,row['selector'],candidate_metrics(lineup)['selector'])
    output={'rows':retained,'examined_salary_legal_rosters':examined,'certification_candidates':len(candidates),
        'exact_global_rank_at_or_above':cutoff,'complete_quality_universe_at_or_above_fixed_A':.88,
        'method':'All six-player/Captain signatures; salary/team prefilter; valid objective upper bound; every retained signature satisfies every saved production MILP constraint. Binary propagation with CBC fallback. No portfolio exposure or QB preference in global rank.'}
    write(destination,output);return output

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path)
    enumerate_universe(parser.parse_args().directory)
