"""Authored optimization intents: primary assessment and conditional alternative."""
from copy import deepcopy

CONTRACT = 'analyst_optimization_intents_v1'
INTENTS = ('EXPECTED_GAME', 'CONTRARIAN')


def validate_intents(packet):
    block = packet.get('optimization_intents')
    if block is None:
        return []
    if not isinstance(block, dict) or block.get('contract_id') != CONTRACT:
        return ['Unknown Analyst optimization-intent contract']
    scenarios = {s['scenario_id']: s for s in (packet.get('scenario_assumptions') or {}).get('scenarios', [])}
    sources = {s['source_id']: s for s in packet['sources']}
    used = set(); errors = []
    user_what_ifs = {f['scenario_id'] for f in (packet.get('contrarian_analysis') or {}).get('findings', []) if f.get('status') == 'user_what_if'}
    for intent in INTENTS:
        item = block.get(intent, {}); ids = item.get('scenario_ids', [])
        if not ids or not isinstance(ids, list) or len(set(ids)) != len(ids) or any(sid not in scenarios for sid in ids):
            errors.append(f'{intent} requires known, distinct authored scenario IDs')
        if used & set(ids): errors.append('Expected and contrarian scenario sets must be disjoint')
        used.update(ids)
        if not all(item.get(key) for key in ('assessment', 'supporting_evidence', 'counterevidence', 'unknowns', 'source_ids')):
            errors.append(f'{intent} requires a sourced assessment, counterevidence and unknowns')
        if any(ref not in sources or sources[ref].get('coverage') != 'verified' for ref in item.get('source_ids', [])):
            errors.append(f'{intent} requires verified source context')
        if intent == 'EXPECTED_GAME' and (set(ids) & user_what_ifs or any(scenarios.get(sid, {}).get('explicit_user_what_if') for sid in ids)):
            errors.append('Expected Game cannot include an explicit user what-if')
        story = item.get('story_requirements')
        if story and (intent != 'CONTRARIAN' or story.get('script') != 'passing_breakout'
                or story.get('require_qb') is not True or type(story.get('minimum_receivers')) is not int
                or not 1 <= story['minimum_receivers'] <= 2
                or not any(story.get('team') in game['teams'] for game in packet['games'])):
            errors.append('Unsupported contrarian story requirements')
    return errors


def scope_packet(packet, intent):
    from .analyst_packets import packet_digest
    if intent not in INTENTS: raise ValueError('Unknown Analyst optimization intent')
    errors = validate_intents(packet)
    if errors: raise ValueError('; '.join(errors))
    block = packet.get('optimization_intents') or {}
    if intent not in block: raise ValueError(f'Published research has no authored {intent} assessment; refresh research')
    item = block[intent]; ids = set(item['scenario_ids']); out = deepcopy(packet)
    out['scenario_assumptions']['scenarios'] = [s for s in out['scenario_assumptions']['scenarios'] if s['scenario_id'] in ids]
    hypothesis_ids = {hid for s in out['scenario_assumptions']['scenarios'] for hid in s['hypothesis_ids']}
    out['hypotheses'] = [h for h in out['hypotheses'] if h['hypothesis_id'] in hypothesis_ids]
    # Unscoped action modules may contain other stories. Their original authored
    # evidence remains in the immutable parent; do not apply it to this intent.
    for key in ('optimization_intents', 'analyst_assessments', 'slate_synthesis', 'captain_analysis',
                'team_game_outlook', 'discovery', 'weekly_role_review', 'defense_kicker_analysis', 'contrarian_analysis'):
        out.pop(key, None)
    out['intent_scope'] = dict(contract_id=CONTRACT, intent=intent,
        authoring_packet_sha256=packet_digest(packet), **deepcopy(item))
    out['packet_id'] += '-' + intent.lower()
    return out


def validate_scoped_packet(packet, intent):
    scoped = packet.get('intent_scope') or {}
    actual = {s['scenario_id'] for s in (packet.get('scenario_assumptions') or {}).get('scenarios', [])}
    if scoped.get('contract_id') != CONTRACT or scoped.get('intent') != intent or actual != set(scoped.get('scenario_ids', [])):
        raise ValueError('Analyst packet does not match the requested optimization intent and scenario set')
    if intent == 'EXPECTED_GAME' and any(s.get('explicit_user_what_if') for s in packet['scenario_assumptions']['scenarios']):
        raise ValueError('Expected Game cannot include an explicit user what-if')
    return deepcopy(scoped)


def require_story(model, variables, mapping, rows, intent_scope):
    import pulp
    story = intent_scope.get('story_requirements')
    if not story: return
    own = {str(r['player_id']) for r in rows if r.get('player_team', r.get('team')) == story['team']}
    by_id = {str(r['player_id']): r for r in rows}
    def terms(positions):
        return [variables[name] for name, ref in mapping.items()
                if ref['player_master_id'] in own and by_id[ref['player_master_id']]['position'] in positions]
    model += pulp.lpSum(terms({'QB'})) >= 1, 'intent_breakout_qb'
    model += pulp.lpSum(terms({'WR', 'TE'})) >= story['minimum_receivers'], 'intent_breakout_receivers'


def audit_story(roster, rows, intent_scope):
    story = intent_scope.get('story_requirements')
    if not story: return True
    by_id = {str(r['player_id']): r for r in rows}
    own = [by_id[p['player_master_id']] for p in roster if by_id[p['player_master_id']].get('player_team', by_id[p['player_master_id']].get('team')) == story['team']]
    return any(r['position'] == 'QB' for r in own) and sum(r['position'] in {'WR', 'TE'} for r in own) >= story['minimum_receivers']
