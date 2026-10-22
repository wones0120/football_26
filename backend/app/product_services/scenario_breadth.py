"""Bounded evidence-first alternative search over a frozen Classic legal model.

Experimental policy, not a calibrated game model. No outcome data is accepted.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from itertools import combinations
import math

import pulp

from .analyst_shadow import digest
from .cbc_solver import make_cbc_solver
from .scenario_allocation import AllocationControls, apply_idea, audit_construction, dependence_audit

CONTRACT = 'evidence_scenario_breadth_v1'


def signature(candidate):
    return tuple(sorted((p['player_master_id'], p['role']) for p in candidate['roster']))


def compose_world(primary, supporting, rows):
    """Combine disjoint game responses, never stack two budgets for one game."""
    result = deepcopy(primary)
    if supporting is None:
        return result
    primary_games = {r['game_id'] for r in rows if primary['moments'][str(r['player_id'])].get('changes')}
    support_games = {r['game_id'] for r in rows if supporting['moments'][str(r['player_id'])].get('changes')}
    if primary_games & support_games:
        raise ValueError('Cannot compose opportunity budgets for the same game')
    for row in rows:
        if row['game_id'] in support_games:
            result['moments'][str(row['player_id'])] = deepcopy(supporting['moments'][str(row['player_id'])])
    result['scenario_id'] = primary['scenario_id'] + '__support__' + supporting['scenario_id']
    result['supporting_scenario_id'] = supporting['scenario_id']
    result['supporting_opportunity_budget'] = deepcopy(supporting['opportunity_budget'])
    result['probability_status'] = 'Two disjoint sourced conditional sensitivities; joint likelihood unknown'
    return result


def generate_pool(snapshot, rows, ideas, worlds, params, requested, controls=None):
    controls = controls or AllocationControls()
    if len(ideas) > 48 or not 1 <= requested <= 20:
        raise ValueError('Bounded breadth research supports 1–20 entries and at most 48 ideas')
    by_id = {str(r['player_id']): r for r in rows}
    world_map = {w['scenario_id']: w for w in worlds}
    candidates, attempts = [], []
    # Freeze support choice before any solve, using only existing ordinal evidence.
    support = {idea['idea_id']: next((i for i in sorted(ideas, key=lambda x: (-x['credibility_score'], x['idea_id']))
               if i['game_id'] != idea['game_id']), None) for idea in ideas}
    for idea in ideas:
        previous = []
        for variant in range(2):
            other = support[idea['idea_id']] if variant else None
            world = compose_world(world_map[idea['idea_id']], world_map[other['idea_id']] if other else None, rows)
            variables, model = pulp.LpProblem.fromDict(deepcopy(snapshot['model']))
            player_vars = {ref['player_master_id']: variables[name] for name, ref in snapshot['variable_players'].items()}
            apply_idea(model, variables, snapshot['variable_players'], rows, idea, controls)
            for pid in idea.get('discovery_required_player_ids', []):
                model += player_vars[pid] == 1
            # Zero maximums are individual eligibility; portfolio exposures otherwise belong to selection.
            for pid, var in player_vars.items():
                if float((params.get('maximum_exposure_by_player') or {}).get(pid, params.get('max_exposure', 1))) == 0:
                    model += var == 0
            for ids in previous:
                model += pulp.lpSum(player_vars[pid] for pid in ids) <= len(ids) - 1
            model.setObjective(pulp.lpSum((world['moments'][pid]['mean'] + .35 *
                (world['moments'][pid]['p90'] - world['moments'][pid]['mean'])) * var for pid, var in player_vars.items()))
            solver = make_cbc_solver()
            solver.options.extend(['randomSeed 7', 'randomCbcSeed 7'])
            model.solve(solver)
            attempts.append(dict(idea_id=idea['idea_id'], variant=variant + 1, supporting_idea_id=other['idea_id'] if other else None,
                                 solver_status=pulp.LpStatus[model.status]))
            if model.status != pulp.LpStatusOptimal:
                continue
            ids = sorted(pid for pid, var in player_vars.items() if pulp.value(var) > .5)
            audit = audit_construction(ids, rows, idea, controls)
            if len(ids) != 9 or not audit['passed']:
                raise ValueError('Breadth candidate failed canonical construction audit')
            previous.append(ids)
            candidate = dict(roster=[dict(player_master_id=pid, role='SELECTED') for pid in ids],
                candidate_id=CONTRACT + ':' + idea['idea_id'] + ':' + str(variant + 1),
                allocated_idea_id=idea['idea_id'], scenario_ids=[idea['idea_id']], allocation_slot=0,
                supporting_idea_id=other['idea_id'] if other else None, generation_world_id=world['scenario_id'],
                opportunity_budget=world['opportunity_budget'], supporting_opportunity_budget=world.get('supporting_opportunity_budget'),
                construction_compliance=True, construction_audit=audit, discovery_finding_ids=idea.get('discovery_finding_ids', []),
                baseline_mean=sum(float(by_id[pid]['projection']) for pid in ids), salary=sum(float(by_id[pid]['salary']) for pid in ids),
                candidate_objective='conditional mean +0.35 summed marginal P90 spread; not joint upside')
            candidates.append(candidate)
    return candidates, dict(contract_id=CONTRACT, attempts=attempts, variants=len(candidates),
        distinct_canonical_rosters=len({signature(c) for c in candidates}),
        support_plan={key: value['idea_id'] if value else None for key, value in support.items()},
        generation_experiment=True, outcomes_used=False, base_projections_changed=False)


def select_pool(candidates, worlds, rows, params, requested, plan, *, objective='ORDINAL_CONDITIONAL_COVERAGE', candidate_utilities=None, joint_state_scores=None, research_solver_seconds=None):
    """Reuse normal hard controls; add the existing allocation dependence policy."""
    from .analyst_scenarios import select_portfolio
    controls = AllocationControls.model_validate(plan['controls'])
    selected, selection = select_portfolio(candidates, worlds, rows, requested=requested, params=params,
        fmt='CLASSIC', allocation_plan=plan, allocation_controls=controls, selection_objective=objective, candidate_utilities=candidate_utilities, joint_state_scores=joint_state_scores, research_solver_seconds=research_solver_seconds)
    for index, candidate in enumerate(selected, 1):
        candidate['allocation_slot'] = index
    return selected, {**selection, 'actual_roster_audit': dependence_audit(selected, rows, requested),
                      'objective': objective, 'probability_status': 'ordinal design priorities only; no calibrated probabilities'}


def add_selection_constraints(model, chosen, candidates, rows, requested, params, plan, controls):
    by_id = {str(r['player_id']): r for r in rows}
    locks = set(params.get('locked_player_ids') or [])
    rosters, pairs, triples, ideas = defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
    for index, candidate in enumerate(candidates):
        ids = sorted(p['player_master_id'] for p in candidate['roster'])
        rosters[signature(candidate)].append(chosen[index])
        ideas[candidate['allocated_idea_id']].append(chosen[index])
        for group in combinations(ids, 3):
            triples[group].append(chosen[index])
        for group in combinations(ids, 2):
            a, b = (by_id[pid] for pid in group)
            if a.get('player_team', a.get('team')) == b.get('player_team', b.get('team')) and a['position'] in {'WR', 'TE'} and b['position'] in {'WR', 'TE'}:
                pairs[group].append(chosen[index])
    for values in rosters.values():
        model += pulp.lpSum(values) <= 1
    for groups, fraction in [(pairs, controls.receiving_core_max_fraction), (triples, controls.shared_triple_max_fraction)]:
        limit = math.ceil(requested * fraction)
        for ids, values in groups.items():
            if len(values) > limit and not set(ids) <= locks:
                model += pulp.lpSum(values) <= limit
    for idea in plan['ideas']:
        if 'discovery_max_lineups' in idea:
            model += pulp.lpSum(ideas[idea['idea_id']]) <= idea['discovery_max_lineups']
    for idea_id, minimum in Counter((plan.get('discovery') or {}).get('reserved_idea_ids', [])).items():
        model += pulp.lpSum(ideas[idea_id]) >= minimum
