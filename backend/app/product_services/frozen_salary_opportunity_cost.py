"""Arithmetic validation of stored Showdown alternatives; never runs a solver."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import math
from uuid import UUID

VERSION = 'frozen_salary_opportunity_cost_v1'
TOLERANCE = 1e-7


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _number(value):
    _require(not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value), 'finite numeric value required')
    return float(value)


def _uuid(value):
    _require(isinstance(value, str) and str(UUID(value)) == value, 'canonical UUID required')
    return value


def _equal(actual, expected, label):
    _require(math.isclose(_number(actual), _number(expected), rel_tol=TOLERANCE, abs_tol=TOLERANCE), label + ' mismatch')


def _time(value):
    t = datetime.fromisoformat(value.replace('Z', '+00:00'))
    _require(t.tzinfo is not None, 'timezone required')
    return t


def _signed(payload):
    unsigned = {k: v for k, v in payload.items() if k != 'sha256'}
    _require(payload.get('sha256') == digest(unsigned), 'semantic hash mismatch')


def validate_frozen_snapshot(snapshot):
    """Validate the supported linear binary model format without constructing it."""
    _signed(snapshot)
    _require(snapshot['contract_id'] == 'analyst_shadow_model_v1', 'snapshot contract')
    _require(snapshot['scope']['format'] == 'SHOWDOWN', 'Showdown required')
    _require(_time(snapshot['available_at']) <= _time(snapshot['decision_at']), 'snapshot chronology')
    _require(snapshot['policy']['complete_prepared_model'] is True, 'complete model required')
    players = {}
    for row in snapshot['players']:
        pid = _uuid(row['player_master_id'])
        _require(pid not in players, 'duplicate canonical pool actor')
        _require(row['game_id'] in snapshot['scope']['game_ids'], 'player scope')
        _require(_number(row['salary']) >= 0 and _number(row['projection']) >= 0, 'negative salary/projection')
        players[pid] = row
    model = snapshot['model']
    _require(not model.get('sos1') and not model.get('sos2'), 'unsupported special ordered sets')
    _require(model['parameters']['sense'] in (-1, 1), 'objective sense')
    mapping, variables, links = snapshot['variable_players'], {}, set()
    for var in model['variables']:
        name = var['name']
        _require(name not in variables, 'duplicate variable')
        _require(var['cat'] == 'Integer' and var['lowBound'] == 0 and var['upBound'] == 1, 'binary model required')
        _require(name in mapping, 'unmapped model variable')
        link = mapping[name]
        key = (_uuid(link['player_master_id']), link['role'])
        _require(key[0] in players and key[1] in ('CPT', 'FLEX') and key not in links, 'ambiguous player-role mapping')
        links.add(key)
        variables[name] = key
    _require(set(mapping) == set(variables), 'extra variable mapping')
    for row in [model['objective'], *model['constraints']]:
        names = set()
        for term in row['coefficients']:
            _require(term['name'] in variables and term['name'] not in names, 'invalid or duplicate coefficient')
            names.add(term['name'])
            _number(term['value'])
    for row in model['constraints']:
        _require(row['sense'] in (-1, 0, 1), 'constraint sense')
        _number(row['constant'])
    # Unsupported quality screens cannot silently disappear from the comparison.
    _require(not snapshot.get('quality_screens'), 'nonempty quality screens require an explicit evaluator')
    return players, variables


def validate_comparison(snapshot, comparison):
    """Recheck recorded rosters, constraints, utility and opportunity-cost deltas.

    Solver optimality is retained as a historical report, not independently proved.
    """
    players, variables = validate_frozen_snapshot(snapshot)
    _signed(comparison)
    _require(comparison['contract_id'] == 'defense_kicker_paired_flex_v1', 'comparison contract')
    _require(comparison['snapshot_sha256'] == snapshot['sha256'], 'different frozen model')
    _require(comparison['baseline_mutation'] is False and comparison['selection_action'] == 'comparison_only', 'comparison-only required')
    _require(comparison['relaxations'] == [], 'relaxed comparison')
    _require(comparison['requested_lineup_count'] == comparison['achieved_lineup_count'] == 2, 'two complete alternatives required')
    _require(isinstance(comparison['seed'], int) and not isinstance(comparison['seed'], bool), 'recorded seed required')
    captain, specialist = _uuid(comparison['captain_id']), _uuid(comparison['specialist_id'])
    _require(captain != specialist and captain in players and specialist in players, 'comparison identities')
    _require(players[specialist]['position'] in ('DST', 'K'), 'specialist role')
    branches = comparison['branches']
    _require(len(branches) == 2 and branches[0]['included'] is False and branches[1]['included'] is True, 'include/omit treatment order')
    results = []
    for branch in branches:
        _require(branch['solver_status'] == 'Optimal' and branch['achieved_lineup_count'] == 1, 'stored complete Optimal branch required')
        selected = []
        for item in branch['roster']:
            selected.append((_uuid(item['player_master_id']), item['role']))
        _require(len(selected) == 6 and len({p for p, _ in selected}) == 6, 'six distinct roster actors required')
        _require(sum(role == 'CPT' for _, role in selected) == 1 and sum(role == 'FLEX' for _, role in selected) == 5, 'Captain/FLEX shape')
        _require((captain, 'CPT') in selected and (specialist, 'CPT') not in selected, 'fixed Captain treatment')
        _require(((specialist, 'FLEX') in selected) is branch['included'], 'specialist include/omit treatment')
        _require(set(selected) <= set(variables.values()), 'roster outside frozen pool')
        x = {name: int(key in selected) for name, key in variables.items()}
        for row in snapshot['model']['constraints']:
            residual = row['constant'] + sum(term['value'] * x[term['name']] for term in row['coefficients'])
            sense = row['sense']
            _require((sense == -1 and residual <= TOLERANCE) or (sense == 1 and residual >= -TOLERANCE) or (sense == 0 and abs(residual) <= TOLERANCE), 'frozen constraint violation: ' + str(row.get('name')))
        salary = sum(players[p]['salary'] * (1.5 if role == 'CPT' else 1) for p, role in selected)
        mean = sum(players[p]['projection'] * (1.5 if role == 'CPT' else 1) for p, role in selected)
        objective = sum(term['value'] * x[term['name']] for term in snapshot['model']['objective']['coefficients'])
        _equal(branch['salary'], salary, 'salary')
        _equal(branch['baseline_mean'], mean, 'baseline mean')
        _equal(branch['objective_value'], objective, 'captured objective')
        results.append(dict(included=branch['included'], roster=[dict(player_master_id=p, role=r) for p, r in sorted(selected)], salary=salary, baseline_mean=mean, captured_objective_value=objective, constraints_checked=len(snapshot['model']['constraints']), recorded_solver_status=branch['solver_status'], independently_proved_optimality=False))
    a, b = results
    omitted = {p['player_master_id'] for p in a['roster']}
    included = {p['player_master_id'] for p in b['roster']}
    cost = dict(displaced_player_ids=sorted(omitted - included), added_player_ids=sorted(included - omitted), salary_delta=b['salary'] - a['salary'], baseline_mean_delta=b['baseline_mean'] - a['baseline_mean'])
    reported = comparison['opportunity_cost']
    for key in ('displaced_player_ids', 'added_player_ids'):
        _require(reported[key] == cost[key], 'displacement mismatch')
    for key in ('salary_delta', 'baseline_mean_delta'):
        _equal(reported[key], cost[key], key)
    cost['captured_objective_delta'] = b['captured_objective_value'] - a['captured_objective_value']
    return dict(version=VERSION, snapshot_sha256=snapshot['sha256'], comparison_sha256=comparison['sha256'], captain_id=captain, specialist_id=specialist, branches=results, opportunity_cost=cost, scoring_definition='frozen_projection_sum_cpt_1p5_v1', source_scoring_status=comparison['scoring_status'], recorded_execution=dict(seed=comparison['seed'], requested_lineup_count=comparison['requested_lineup_count'], achieved_lineup_count=comparison['achieved_lineup_count'], selection_action=comparison['selection_action'], relaxations=deepcopy(comparison['relaxations'])), frozen_model_sha256=digest(snapshot['model']), scope=deepcopy(snapshot['scope']), source_available_at=snapshot['available_at'], source_decision_at=snapshot['decision_at'], frozen_policy=deepcopy(snapshot['policy']), frozen_provenance=deepcopy(snapshot['provenance']), forecast_activation=False, new_solver_execution=False)
