"""Offline, constraint-only Analyst discovery against a frozen production ILP.

No database, live optimizer integration, projection edits, or portfolio selection.
The snapshot producer must capture the complete prepared model and eligibility.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
import math
from uuid import UUID

import pulp

CONTRACT = 'analyst_shadow_model_v1'
SUPPORTED = {'player_emphasis', 'qb_receiver_bringback', 'rb_dst_scenario',
             'diversify_away_from_game', 'explicit_roles'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def clock(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timezone required')
    return parsed


def freeze_model(model, *, variable_players, players, scope, available_at, decision_at,
                 policy, quality_screens=(), provenance=None):
    """Serialize a previously prepared production model without solving/mutating it.

    variable_players maps binary roster variable names to canonical ID and role.
    Auxiliary objective variables are deliberately retained in the model.
    """
    payload = dict(contract_id=CONTRACT, model=deepcopy(model.toDict()),
                   variable_players=deepcopy(variable_players), players=deepcopy(players),
                   scope=deepcopy(scope), available_at=available_at, decision_at=decision_at,
                   policy=deepcopy(policy), quality_screens=deepcopy(list(quality_screens)),
                   provenance=deepcopy(provenance or {}))
    # Solution values/status are not inputs to a frozen generation model.
    payload['model']['parameters'].update(status=0, sol_status=0)
    for row in payload['model']['variables']:
        row.update(varValue=None, dj=None)
    for row in payload['model']['constraints']:
        row['pi'] = None
    return {**payload, 'sha256': digest(payload)}


def validate_snapshot(snapshot, *, mean_only=False):
    if snapshot.get('contract_id') != CONTRACT or digest({k:v for k,v in snapshot.items() if k != 'sha256'}) != snapshot.get('sha256'):
        raise ValueError('snapshot_contract_or_hash_mismatch')
    if snapshot['scope']['format'] not in {'CLASSIC', 'SHOWDOWN'}:
        raise ValueError('unsupported_format')
    decision = clock(snapshot['decision_at'])
    if clock(snapshot['available_at']) > decision:
        raise ValueError('baseline_future_sourced')
    if not snapshot['policy'].get('complete_prepared_model'):
        raise ValueError('incomplete_baseline_policy')
    players = {p['player_master_id']:p for p in snapshot['players']}
    if len(players) != len(snapshot['players']):
        raise ValueError('duplicate_canonical_identity')
    for pid, player in players.items():
        UUID(pid)
        if player['game_id'] not in snapshot['scope']['game_ids']:
            raise ValueError('player_outside_snapshot_scope')
        for field in ('salary', 'projection', 'p90'):
            if (field=='p90' and player.get(field) is None and mean_only
                and snapshot['policy'].get('mean_only') is True
                and snapshot['policy'].get('selection_policy')=='expected_anchor_incremental_world_gain_v1'):
                continue  # Explicit mean-only contract retains an unknown tail.
            if not math.isfinite(float(player[field])) or float(player[field]) < 0:
                raise ValueError('invalid_numeric_player_input')
    variables, model = pulp.LpProblem.fromDict(deepcopy(snapshot['model']))
    pairs = set()
    for name, reference in snapshot['variable_players'].items():
        pair = (reference['player_master_id'], reference['role'])
        if name not in variables or pair[0] not in players or pair in pairs:
            raise ValueError('invalid_roster_variable_identity')
        if reference['role'] not in ({'CPT', 'FLEX'} if snapshot['scope']['format'] == 'SHOWDOWN' else {'SELECTED'}):
            raise ValueError('wrong_format_role')
        var = variables[name]
        if var.cat != 'Integer' or var.lowBound != 0 or var.upBound != 1:
            raise ValueError('roster_variable_must_be_binary')
        pairs.add(pair)
    for rule in snapshot['quality_screens']:
        if rule.get('sense') not in {'>=','<='} or not math.isfinite(float(rule['threshold'])):
            raise ValueError('invalid_quality_screen')
        if any(name not in variables or not math.isfinite(float(coef)) for name,coef in rule['terms'].items()):
            raise ValueError('invalid_quality_screen_terms')
    if not pairs:
        raise ValueError('missing_roster_mapping')
    return players, variables, model


def packet_errors(packet, snapshot):
    errors = []
    try:
        if packet.get('contract_id') != 'wones_football_analyst_v1': errors.append('unsupported_packet_version')
        if packet.get('baseline_mutation') is not False or packet.get('user_preferences') != []: errors.append('packet_policy_mismatch')
        decision = clock(snapshot['decision_at'])
        if clock(packet['decision_at']) > decision or clock(packet['frozen_at']) > decision: errors.append('packet_future_sourced')
        if clock(packet['frozen_at']) < clock(packet['decision_at']): errors.append('packet_freeze_precedes_analysis')
        if packet.get('baseline_input_sha256') != snapshot['sha256'] and snapshot.get('provenance', {}).get('analyst_packet_sha256') != digest(packet): errors.append('baseline_input_hash_mismatch')
        if not packet.get('packet_id'): errors.append('missing_packet_id')
        for key in ('games', 'sources', 'players', 'analyst_assessments'):
            rows = packet.get(key)
            if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows): errors.append('invalid_' + key)
    except (KeyError, ValueError, TypeError, AttributeError):
        errors.append('invalid_packet_clock_or_structure')
    return errors


def directive_errors(assessment, construction, packet, snapshot, players):
    errors = []
    fmt = snapshot['scope']['format']
    try:
        if construction.get('type') not in SUPPORTED: errors.append('unsupported_thesis_type')
        if assessment.get('kind') != 'subjective_analyst_judgment' or assessment.get('production_action') != 'none': errors.append('invalid_judgment_kind')
        if assessment.get('numeric_effect_proposal') is not None or assessment.get('selection_weight') is not None: errors.append('numeric_effect_prohibited')
        if construction.get('action') != 'shadow_comparison_only': errors.append('invalid_action')
        if construction.get('format') != fmt or fmt not in assessment.get('formats', []): errors.append('wrong_format')
        games = {g['game_id']:g for g in packet['games']}
        game = games.get(assessment['game_id'], {})
        if assessment['game_id'] not in snapshot['scope']['game_ids'] or game.get('format_membership', {}).get(fmt) != 'confirmed_in_scope': errors.append('wrong_slate_game')
        decision = clock(snapshot['decision_at'])
        if clock(assessment['expires_at']) <= decision: errors.append('stale_thesis')
        if clock(game['kickoff_at']) <= decision: errors.append('not_pregame')
        if clock(assessment['expires_at']) > clock(game['kickoff_at']): errors.append('expiry_beyond_kickoff')
        if clock(assessment.get('analysis_at', packet['decision_at'])) > decision: errors.append('future_analysis')
        sources = {s['source_id']:s for s in packet['sources']}
        declared = {p['player_master_id']:p for p in packet['players']}
        refs = assessment.get('source_ids', [])
        if not refs: errors.append('missing_source_references')
        for sid in refs:
            source = sources.get(sid)
            if not source or source.get('coverage') != 'verified': errors.append('missing_source_evidence'); continue
            if clock(source['available_at']) > decision or clock(source['observed_at']) > clock(source['available_at']): errors.append('future_source')
            if source.get('published_at') and clock(source['published_at']) > clock(source['available_at']): errors.append('future_source')
            if not source.get('capture_sha256'): errors.append('missing_source_hash')
        if construction.get('roles', {}).get('CPT') and snapshot['policy'].get('shortlist_ids') is not None:
            if any(pid not in snapshot['policy']['shortlist_ids'] for pid in construction['roles']['CPT']):
                errors.append('captain_shortlist_exclusion')
        roles = construction.get('roles', {})
        if not isinstance(roles, dict) or not roles: errors.append('missing_typed_roles'); return sorted(set(errors))
        for ids in roles.values():
            if not isinstance(ids, list) or not ids: errors.append('invalid_role_ids'); continue
            for pid in ids:
                UUID(pid)
                if pid not in assessment.get('player_master_ids', []) or pid not in declared or pid not in players: errors.append('unknown_or_ineligible_identity'); continue
                row = players[pid]
                if declared[pid].get('game_id') != row['game_id'] or declared[pid].get('team') != row['team']: errors.append('canonical_scope_mismatch')
                if row['game_id'] != assessment['game_id'] and construction['type'] != 'diversify_away_from_game': errors.append('identity_outside_thesis_game')
    except (KeyError, ValueError, TypeError, AttributeError):
        errors.append('malformed_thesis')
    return sorted(set(errors))


def add_directive(model, variables, snapshot, players, construction):
    roles = construction['roles']; kind = construction['type']
    by_pair = {(r['player_master_id'], r['role']):variables[n] for n,r in snapshot['variable_players'].items()}
    def selected(pid):
        return pulp.lpSum(v for (p,_),v in by_pair.items() if p == pid)
    def require(ids):
        for pid in ids: model.addConstraint(selected(pid) == 1)
    expected = {'player_emphasis': {'PLAYER'}, 'qb_receiver_bringback': {'QB','RECEIVER','BRINGBACK'},
                'rb_dst_scenario': {'RB','DST'}, 'diversify_away_from_game': {'AVOID'},
                'explicit_roles': {'CPT','FLEX'} if snapshot['scope']['format'] == 'SHOWDOWN' else {'SELECTED'}}
    if not set(roles) <= expected[kind] or (kind != 'explicit_roles' and set(roles) != expected[kind]):
        raise ValueError('unsupported_role_shape')
    if kind == 'explicit_roles':
        for role, ids in roles.items():
            for pid in ids:
                if (pid, role) not in by_pair: raise ValueError('missing_canonical_role')
                model.addConstraint(by_pair[pid,role] == 1)
    elif kind == 'diversify_away_from_game':
        # Avoid the entire explicitly scoped game; no arbitrary exposure percentage.
        games = {players[p]['game_id'] for p in roles['AVOID']}
        if len(games) != 1: raise ValueError('ambiguous_avoid_game')
        for pid,row in players.items():
            if row['game_id'] in games: model.addConstraint(selected(pid) == 0)
    elif kind == 'qb_receiver_bringback':
        if len(roles['QB']) != 1: raise ValueError('requires_one_qb')
        qb = players[roles['QB'][0]]
        if qb['position'] != 'QB' or any(players[p]['position'] not in {'WR','TE'} or players[p]['team'] != qb['team'] for p in roles['RECEIVER']) or any(players[p]['position'] not in {'RB','WR','TE'} or players[p]['team'] != qb['opponent_team'] for p in roles['BRINGBACK']): raise ValueError('incompatible_qb_stack')
        require([p for ids in roles.values() for p in ids])
    elif kind == 'rb_dst_scenario':
        if any(players[p]['position'] != 'RB' for p in roles['RB']) or any(players[p]['position'] != 'DST' for p in roles['DST']) or len({players[p]['team'] for ids in roles.values() for p in ids}) != 1: raise ValueError('incompatible_rb_dst')
        require([p for ids in roles.values() for p in ids])
    else:
        require(roles['PLAYER'])


def generate_shadow(packet, snapshot, *, requested_per_thesis=2, baseline_count=2, seed=7, enabled=True):
    """Generate separate candidate arms. Never select a combined final portfolio.

    Exposure/locks encoded in the frozen feasible region remain immutable. These
    are alternative discovery candidates, not additional portfolio appearances.
    """
    if not 0 <= requested_per_thesis <= 100 or not 0 <= baseline_count <= 100 or not isinstance(seed, int) or not 1 <= seed < 2**31:
        raise ValueError('invalid_generation_budget_or_seed')
    players, _, _ = validate_snapshot(snapshot)
    errors = packet_errors(packet, snapshot) if enabled else []
    result = dict(mode='RESEARCH_SHADOW', snapshot_sha256=snapshot['sha256'], packet_sha256=digest(packet),
                  packet_id=packet.get('packet_id'), packet_version=packet.get('contract_id'), seed=seed,
                  production_defaults_changed=False, projection_mutation=False, final_portfolio_selected=False,
                  baseline=[], shadow=[], theses=[], packet_errors=errors,
                  policy=snapshot['policy'], solver=dict(name='bundled_CBC', threads=1, randomSeed=seed, tie_handling='frozen variable order; unchanged primary objective'),
                  selection_status='NOT_PERFORMED_candidates_are_alternatives_not_portfolio', relaxations=[])
    candidates = {}
    def arm(construction, requested, thesis_id=None):
        variables, model = pulp.LpProblem.fromDict(deepcopy(snapshot['model']))
        if construction: add_directive(model, variables, snapshot, players, construction)
        records = []; status = 'not_requested'
        for _ in range(requested):
            solver = pulp.PULP_CBC_CMD(msg=False, threads=1, options=['randomSeed ' + str(seed)])
            code = model.solve(solver); status = pulp.LpStatus[code]
            if code != pulp.LpStatusOptimal: break
            chosen = sorted((r['player_master_id'],r['role']) for n,r in snapshot['variable_players'].items() if variables[n].value() > .5)
            if len(chosen) != (6 if snapshot['scope']['format'] == 'SHOWDOWN' else 9) or len({p for p,_ in chosen}) != len(chosen): raise ValueError('invalid_generated_roster_mapping')
            key = digest(chosen)
            screen = []
            for rule in snapshot['quality_screens']:
                value = sum(float(coef) * float(variables[name].value()) for name,coef in rule['terms'].items())
                passed = value >= rule['threshold'] if rule['sense'] == '>=' else value <= rule['threshold']
                screen.append(dict(id=rule['id'], passed=passed, value=value, threshold=rule['threshold']))
            record = dict(candidate_id=key, roster=[dict(player_master_id=p, role=r) for p,r in chosen],
                          baseline_objective=float(pulp.value(model.objective)), quality_screens=screen,
                          eligibility_outcome='DIAGNOSTIC_ONLY' if any(not s['passed'] for s in screen) else 'SHADOW_CANDIDATE',
                          constraint_outcomes=dict(legality='passed_frozen_model',captain_policy='passed_frozen_model' if snapshot['scope']['format']=='SHOWDOWN' else 'not_applicable',user_constraints='passed_frozen_model',quality_screens='evaluated' if screen else 'not_separately_evaluated'),
                          thesis_ids=[], salary=sum(float(players[p]['salary']) * (1.5 if r == 'CPT' else 1) for p,r in chosen),
                          projected_mean=sum(float(players[p]['projection']) * (1.5 if r == 'CPT' else 1) for p,r in chosen))
            if thesis_id:
                existing = candidates.setdefault(key, record)
                if thesis_id not in existing['thesis_ids']: existing['thesis_ids'].append(thesis_id)
            records.append(record)
            # Role-aware Showdown no-good; Classic canonical set equality.
            selected_vars = [variables[n] for n,r in snapshot['variable_players'].items() if (r['player_master_id'],r['role']) in chosen]
            model.addConstraint(pulp.lpSum(selected_vars) <= len(chosen)-1)
        return records, status
    result['baseline'], result['baseline_solver_status'] = arm(None, baseline_count)
    if enabled and not errors:
        seen = set()
        for assessment in packet['analyst_assessments']:
            aid = assessment.get('assessment_id')
            for index, construction in enumerate(assessment.get('construction_implications', [])):
                tid = str(aid) + ':' + str(index)
                reasons = directive_errors(assessment, construction, packet, snapshot, players)
                if not aid or tid in seen: reasons.append('duplicate_or_missing_thesis_id')
                seen.add(tid)
                report = dict(thesis_id=tid, analyst_thought=assessment.get('lean'), construction=deepcopy(construction), requested=requested_per_thesis, achieved=0, reasons=reasons)
                if not reasons:
                    try:
                        rows,status = arm(construction, requested_per_thesis, tid)
                        report.update(achieved=len(rows), solver_status=status, candidate_ids=[r['candidate_id'] for r in rows])
                        if len(rows) < requested_per_thesis: report['reasons'].append('baseline_feasible_region_conflict' if status == 'Infeasible' and not rows else 'no_more_feasible_distinct_candidates')
                    except ValueError as exc: report['reasons'].append(str(exc))
                report['status'] = 'generated' if report['achieved'] else 'abstained_or_infeasible'
                result['theses'].append(report)
    result['shadow'] = list(candidates.values())
    baseline_ids = {r['candidate_id'] for r in result['baseline']}
    result['comparison'] = dict(baseline_requested=baseline_count, baseline_distinct=len(baseline_ids),
                                shadow_distinct=len(candidates), shadow_new_distinct=len(set(candidates)-baseline_ids),
                                covered_theses=sum(bool(t['achieved']) for t in result['theses']),
                                diagnostic_only=sum(r['eligibility_outcome']=='DIAGNOSTIC_ONLY' for r in candidates.values()))
    return result
