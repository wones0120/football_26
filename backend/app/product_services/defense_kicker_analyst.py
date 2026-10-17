"""Separate DST/K research passes and matched legal FLEX comparisons.

No projection edits, inferred availability, name joins, or automatic exposure.
The captured legal model is authoritative, including user exclusions/correlations.
"""
from copy import deepcopy
from uuid import UUID

from .analyst_shadow import digest

CONTRACT = 'defense_kicker_analysis_v1'
DIMENSIONS = {
    'DST': ('opponent_qb_protection', 'pressure', 'dropbacks_pace',
            'turnover_uncertainty', 'points_allowed_scoring', 'availability', 'special_teams'),
    'K': ('confirmed_role', 'drives_scoring_chances', 'red_zone_stalls',
          'distance_scoring', 'weather_venue', 'fourth_down_tendencies', 'accuracy_uncertainty'),
}


def validate_specialists(packet):
    """Evidence must be traceable and predecision; unavailable is never zero."""
    from .analyst_packets import clock
    block = packet.get('defense_kicker_analysis')
    if block is None:
        return []
    if not isinstance(block, dict) or block.get('contract_id') != CONTRACT:
        return ['Defense/kicker: unknown contract']
    errors = []
    sources = {s['source_id']: s for s in packet.get('sources', [])}
    players = {p['player_master_id']: p for p in packet.get('players', [])}
    games = {g['game_id']: g for g in packet.get('games', [])}
    findings = block.get('findings')
    if not isinstance(findings, list):
        return ['Defense/kicker: findings must be an array']
    seen = set()
    for f in findings:
        if not isinstance(f, dict):
            errors.append('Defense/kicker: finding must be an object'); continue
        label = str(f.get('finding_id'))
        def need(ok, reason):
            if not ok: errors.append(label + ': ' + reason)
        need(bool(f.get('finding_id')) and label not in seen, 'missing/duplicate finding identity'); seen.add(label)
        pid = f.get('player_master_id'); player = players.get(pid, {})
        need(player.get('position') in DIMENSIONS, 'requires canonical DST/K identity')
        need(player.get('source_native_key'), 'requires native identity')
        need(f.get('game_id') == player.get('game_id') and f.get('team') == player.get('team'), 'identity/game/team mismatch')
        fmt = f.get('format'); game = games.get(f.get('game_id'), {})
        need(fmt in {'CLASSIC', 'SHOWDOWN'} and game.get('format_membership', {}).get(fmt) == 'confirmed_in_scope', 'format outside scope')
        need(not (player.get('position') == 'K' and fmt != 'SHOWDOWN'), 'kicker illegal in Classic')
        need(f.get('status') in {'watchlist', 'supported_comparison', 'rejected'}, 'unknown status')
        need(f.get('action') == ('paired_flex_comparison' if f.get('status') == 'supported_comparison' and fmt == 'SHOWDOWN' else 'none'), 'unsupported action')
        need(not any(k in f for k in ('fantasy_point_bonus', 'probability', 'selection_weight', 'confidence_score')), 'numeric bonuses/probabilities prohibited')
        refs = f.get('supporting_source_ids', [])
        need(isinstance(refs, list) and all(s in sources for s in refs), 'unknown supporting source')
        for name in ('mechanism', 'contrary_evidence', 'uncertainty', 'what_changes_view', 'model_accounting', 'opportunity_cost'):
            need(bool(f.get(name)), 'missing ' + name)
        try:
            asof = clock(f['as_of']); decision = clock(packet['decision_at'])
            need(asof <= decision < clock(f['expires_at']) <= clock(game['kickoff_at']), 'invalid finding/expiry clocks')
        except (KeyError, TypeError, ValueError):
            errors.append(label + ': invalid clocks'); asof = None
        for sid in refs if isinstance(refs, list) else []:
            source = sources.get(sid, {})
            try:
                need(source.get('coverage') == 'verified' and asof is not None and clock(source['available_at']) <= asof, 'supporting source unavailable at finding')
            except (KeyError, TypeError, ValueError): need(False, 'invalid supporting source clock')
        evidence = f.get('evidence', {})
        for dimension in DIMENSIONS.get(player.get('position'), ()):
            e = evidence.get(dimension, {})
            need(e.get('status') in {'reviewed', 'unavailable'} and bool(e.get('summary')), 'missing dimension ' + dimension)
            refs = e.get('source_ids', [])
            need(isinstance(refs, list) and all(s in sources for s in refs), 'unknown dimension source')
            if e.get('status') == 'unavailable':
                need(e.get('value') is None, 'unavailable evidence cannot be measured zero')
            else:
                need(bool(refs), 'reviewed evidence needs sources')
                for sid in refs:
                    source = sources.get(sid, {})
                    try:
                        need(source.get('coverage') == 'verified' and asof is not None and clock(source['available_at']) <= asof, 'source unavailable at finding')
                    except (KeyError, ValueError, TypeError): need(False, 'invalid source clock')
                    assertion = source.get('fact_assertions', {}).get(e.get('fact_key'))
                    need(bool(assertion) and assertion == e.get('summary'), 'reviewed dimension needs exact sourced assertion')
        if f.get('status') == 'supported_comparison':
            required = ('confirmed_role', 'drives_scoring_chances', 'red_zone_stalls') if player.get('position') == 'K' else ('opponent_qb_protection', 'pressure', 'dropbacks_pace', 'availability')
            need(all(evidence.get(d, {}).get('status') == 'reviewed' for d in required), 'core opportunity/role evidence incomplete')
            need(f.get('model_accounting', {}).get('status') in {'partial', 'unmodeled'}, 'no distinct model delta')
    return errors


def scan_specialists(packet, rows, *, fmt):
    """Automatic complete scope screen; semantic findings remain distinct."""
    errors = validate_specialists(packet)
    if errors: raise ValueError('; '.join(errors))
    declared = {p['player_master_id']: p for p in packet.get('players', [])}
    findings = {(f['player_master_id'], f['format']): f for f in (packet.get('defense_kicker_analysis') or {}).get('findings', [])}
    assessments = []; coverage = []
    for game in packet['games']:
        if game.get('format_membership', {}).get(fmt) != 'confirmed_in_scope': continue
        members = [r for r in rows if r.get('canonical_game_id', r.get('game_id')) == game['game_id'] or {r.get('player_team', r.get('team')), r.get('opponent_team', r.get('opponent'))} == set(game['teams'])]
        game_ids = []
        for row in members:
            position = row.get('position')
            if position not in DIMENSIONS or (position == 'K' and fmt != 'SHOWDOWN'): continue
            pid = str(row.get('player_id', row.get('player_master_id')))
            try: UUID(pid)
            except (ValueError, TypeError): raise ValueError('specialist requires canonical UUID')
            opinion = findings.get((pid, fmt)); player = declared.get(pid, {})
            missing = [d for d in DIMENSIONS[position] if (opinion or {}).get('evidence', {}).get(d, {}).get('status') != 'reviewed']
            item = dict(player_master_id=pid, game_id=game['game_id'], team=row.get('player_team', row.get('team')), position=position,
                source_native_key=player.get('source_native_key') or row.get('dk_player_id'),
                salary=row.get('salary'), baseline_mean=row.get('projection'), baseline_p90=row.get('p90'),
                finding=deepcopy(opinion), status=opinion['status'] if opinion else 'watchlist', missing_evidence=missing,
                roster_decision='mandatory position: compare DST opportunity cost across games' if fmt == 'CLASSIC' else 'optional FLEX candidate; compare against skill-player construction',
                action='paired_flex_comparison' if opinion and opinion['status'] == 'supported_comparison' and fmt == 'SHOWDOWN' else 'none',
                correlation_conditions=['Own RB/DST can share a game-control branch; neither forces the other.', 'Opposing QB/receiver coexistence depends on sacks, yards, scoring and game flow; retain configured avoid-DST-opponents constraints.'] if position == 'DST' else ['Sustained drives plus red-zone stalls can create FG volume; touchdowns instead favor XP volume.'],
                uncertainty='Pressure differs from realized sacks; turnovers and defensive TDs have high variance.' if position == 'DST' else 'Drive/stall volume differs from accuracy; a strong offense alone does not establish FG ceiling.',
                calibration_status='qualitative research; no calibrated scoring response or new projection')
            assessments.append(item); game_ids.append(pid)
        coverage.append(dict(game_id=game['game_id'],teams=game['teams'],screened_specialist_ids=game_ids,
                             unknowns=['Missing specialist rows/role evidence remain missing; never create an inferred player.']))
    result = dict(contract_id=CONTRACT, format=fmt, decision_at=packet['decision_at'], input_rows_sha256=digest(rows),
                  baseline_mutation=False, automatic_exposure=False, games=coverage, assessments=assessments)
    result['sha256'] = digest(result)
    return result


def paired_flex_comparison(snapshot, *, specialist_id, captain_id):
    """Exact captured legal model, same objective/Captain, include versus omit FLEX.

    This generates research alternatives; it never approves a projection change or
    relaxes a user constraint. Even an infeasible branch is retained as evidence.
    """
    import pulp
    from .analyst_scenarios import _solver
    from .analyst_shadow import validate_snapshot
    validate_snapshot(snapshot)
    if snapshot['scope']['format'] != 'SHOWDOWN': raise ValueError('paired FLEX comparison requires Showdown')
    rows = {str(r.get('player_master_id', r.get('player_id'))): r for r in snapshot['players']}
    if rows.get(specialist_id, {}).get('position') not in DIMENSIONS: raise ValueError('canonical DST/K required')
    if captain_id == specialist_id: raise ValueError('FLEX comparison needs a separate fixed Captain')
    mapping = snapshot['variable_players']; branches = []
    def variables_for(variables, pid, role):
        return [variables[name] for name, link in mapping.items() if link['player_master_id'] == pid and link['role'] == role]
    for included in (False, True):
        variables, model = pulp.LpProblem.fromDict(deepcopy(snapshot['model']))
        captain = variables_for(variables, captain_id, 'CPT'); flex = variables_for(variables, specialist_id, 'FLEX'); special_cpt = variables_for(variables, specialist_id, 'CPT')
        if len(captain) != 1 or len(flex) != 1: raise ValueError('comparison identity absent from captured legal model')
        model += captain[0] == 1; model += flex[0] == int(included)
        for var in special_cpt: model += var == 0
        model.solve(_solver()); status = pulp.LpStatus[model.status]; roster = []
        if status == 'Optimal':
            for name, link in mapping.items():
                if variables[name].value() and variables[name].value() > .5:
                    roster.append({**deepcopy(link), 'name': rows[link['player_master_id']].get('name'), 'position': rows[link['player_master_id']]['position']})
        salary = sum(float(rows[p['player_master_id']]['salary']) * (1.5 if p['role'] == 'CPT' else 1) for p in roster)
        mean = sum(float(rows[p['player_master_id']]['projection']) * (1.5 if p['role'] == 'CPT' else 1) for p in roster)
        branches.append(dict(included=included, solver_status=status, achieved_lineup_count=int(bool(roster)), roster=roster,
                             salary=salary if roster else None, baseline_mean=mean if roster else None,
                             objective_value=pulp.value(model.objective) if roster else None))
    omitted, included = branches
    result = dict(contract_id='defense_kicker_paired_flex_v1', snapshot_sha256=snapshot['sha256'], specialist_id=specialist_id,
                  captain_id=captain_id, seed=7, requested_lineup_count=2, achieved_lineup_count=sum(b['achieved_lineup_count'] for b in branches),
                  branches=branches, relaxations=[], baseline_mutation=False, selection_action='comparison_only',
                  scoring_status='unchanged baseline objective; no new specialist numerical response')
    if all(b['roster'] for b in branches):
        a = {p['player_master_id'] for p in omitted['roster']}; b = {p['player_master_id'] for p in included['roster']}
        result['opportunity_cost'] = dict(displaced_player_ids=sorted(a-b), added_player_ids=sorted(b-a),
            salary_delta=included['salary']-omitted['salary'], baseline_mean_delta=included['baseline_mean']-omitted['baseline_mean'])
    result['sha256'] = digest(result)
    return result
