"""Versioned Wones Football Analyst packet validation and immutable local import ledger."""
from datetime import datetime
from uuid import UUID
import json
import sys

CONTRACT = 'wones_football_analyst_v1'
FORMATS = {'CLASSIC', 'SHOWDOWN'}
STATUSES = {'actionable_monitor', 'research_only', 'abstain'}

def clock(value):
    if not isinstance(value, str):
        raise ValueError('missing clock')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('clock requires timezone')
    return parsed

def _validate(packet):
    errors = []
    def need(condition, message):
        if not condition:
            errors.append(message)
    def time(value, label):
        try:
            return clock(value)
        except (ValueError, TypeError):
            errors.append(label + ': invalid/missing timezone clock')
            return None
    if not isinstance(packet, dict):
        return ['packet must be an object']
    need(packet.get('contract_id') == CONTRACT, 'unknown contract')
    need(packet.get('analyst_name') == 'Wones Football Analyst', 'analyst name mismatch')
    need(isinstance(packet.get('packet_id'), str) and bool(packet.get('packet_id').strip()), 'missing/invalid packet_id')
    decision = time(packet.get('decision_at'), 'decision_at')
    freeze = time(packet.get('frozen_at'), 'frozen_at')
    if freeze and decision:
        need(freeze >= decision, 'freeze precedes decision')
    need(packet.get('baseline_mutation') is False, 'baseline mutation prohibited')
    need(packet.get('user_preferences') == [], 'user preferences must remain separate')
    for field in ('games', 'sources', 'players', 'baseline_facts', 'hypotheses'):
        if not isinstance(packet.get(field), list) or not all(isinstance(item, dict) for item in packet[field]):
            return errors + [field + ': expected array of objects']
    scopes = {}
    kickoff_clocks = {}
    for game in packet.get('games', []):
        gid = game.get('game_id')
        need(bool(gid) and gid not in scopes, 'duplicate/missing game identity')
        scopes[gid] = game
        kickoff = time(game.get('kickoff_at'), str(gid) + '.kickoff_at')
        kickoff_clocks[gid] = kickoff
        if kickoff and decision:
            need(decision < kickoff, 'decision is not pregame')
        if kickoff and freeze:
            need(freeze < kickoff, 'freeze is not pregame')
        need(len(game.get('teams', [])) == 2, 'game requires two teams')
    need(bool(scopes), 'missing games')
    sources = {}
    for source in packet.get('sources', []):
        sid = source.get('source_id')
        need(bool(sid) and sid not in sources, 'duplicate/missing source identity')
        sources[sid] = source
        need(bool(source.get('uri')), str(sid) + ': missing uri')
        need(source.get('coverage') in {'verified', 'unavailable'}, str(sid) + ': invalid coverage')
        if source.get('coverage') == 'verified':
            observed = time(source.get('observed_at'), str(sid) + '.observed_at')
            available = time(source.get('available_at'), str(sid) + '.available_at')
            published = time(source['published_at'], str(sid) + '.published_at') if source.get('published_at') else None
            if observed and available:
                need(observed <= available, str(sid) + ': observed after availability')
            if available and decision:
                need(available <= decision, str(sid) + ': available after decision')
            if published and available:
                need(published <= available, str(sid) + ': future publication')
            need(bool(source.get('capture_sha256')), str(sid) + ': missing capture hash')
    def refs(values, label, actionable=False):
        need(isinstance(values, list) and bool(values), label + ': missing source references')
        for sid in values if isinstance(values, list) else []:
            need(sid in sources, label + ': unknown source ' + str(sid))
            if actionable and sid in sources:
                need(sources[sid]['coverage'] == 'verified', label + ': source coverage unavailable')
    players = {}
    for player in packet.get('players', []):
        pid = player.get('player_master_id')
        try:
            UUID(pid)
        except (ValueError, TypeError, AttributeError):
            errors.append('invalid canonical player identity')
        need(pid not in players, 'duplicate canonical player identity')
        players[pid] = player
        gid = player.get('game_id')
        need(gid in scopes and player.get('team') in scopes.get(gid, {}).get('teams', []), 'player outside game scope')
        need(bool(player.get('source_native_key')), 'player requires source native identity key')
        refs(player.get('identity_source_ids'), 'player identity')
        evidence = player.get('workload_evidence')
        need(isinstance(evidence, dict), 'missing shared workload evidence')
        if isinstance(evidence, dict):
            need(evidence.get('contract_id') == 'workload_evidence_v1', 'workload contract mismatch')
            need(evidence.get('player_id') == pid, 'workload canonical identity mismatch')
            for group in ('historical', 'derived_proxies', 'explicit_pregame'):
                need(isinstance(evidence.get(group), dict), 'missing workload group ' + group)
            for item in evidence.get('historical', {}).values():
                if item.get('status') == 'observed':
                    need(item.get('available') is True, 'observed workload requires measurement flag')
                if item.get('available') is False:
                    need(item.get('value') is None, 'unavailable workload cannot be measured zero')
    for fact in packet.get('baseline_facts', []):
        need(fact.get('kind') == 'observed_fact', 'conditional assumption in baseline')
        refs(fact.get('source_ids'), 'baseline fact')
    seen = set()
    for h in packet.get('hypotheses', []):
        hid = h.get('hypothesis_id')
        need(bool(hid) and hid not in seen, 'duplicate/missing hypothesis id')
        seen.add(hid)
        need(h.get('status') in STATUSES, 'invalid hypothesis status')
        actionable = h.get('status') == 'actionable_monitor'
        gid = h.get('game_id')
        need(gid in scopes, 'unknown hypothesis game scope')
        formats = h.get('formats')
        need(isinstance(formats, list) and bool(formats) and set(formats) <= FORMATS, 'invalid hypothesis formats')
        for fmt in formats if isinstance(formats, list) else []:
            need(scopes.get(gid, {}).get('format_membership', {}).get(fmt) == 'confirmed_in_scope', 'hypothesis format not in game scope')
        need(bool(h.get('player_master_ids')), 'missing hypothesis canonical linkage')
        for pid in h.get('player_master_ids', []):
            need(pid in players and players.get(pid, {}).get('game_id') == gid, 'unknown/out-of-scope hypothesis player')
        for field in ('hypothesis', 'supporting_evidence', 'contrary_evidence', 'conditional_assumptions', 'unknowns', 'testable_implication', 'uncertainty', 'recheck_triggers'):
            need(bool(h.get(field)), str(hid) + ': missing ' + field)
        refs(h.get('source_ids'), str(hid), actionable)
        expiry = time(h.get('expires_at'), str(hid) + '.expires_at')
        if expiry and decision:
            need(expiry > decision, str(hid) + ': expired')
        kickoff = kickoff_clocks.get(gid)
        if expiry and kickoff:
            need(expiry <= kickoff, str(hid) + ': expiry beyond kickoff')
        need(isinstance(h.get('uncertainty'), str), 'uncertainty must be unquantified text')
        need(h.get('numeric_effect_proposal') is None, 'v1 prohibits numeric workload/fantasy adjustment proposals')
        if actionable:
            need(h.get('action') == 'refresh_evidence_only', 'actionable status only permits evidence refresh')
        else:
            need(h.get('action') == 'none', 'unsupported hypothesis must abstain from action')
        need(not any(k in h for k in ('probability', 'confidence_score', 'fantasy_point_bonus', 'expected_targets', 'expected_carries', 'expected_snaps', 'projected_targets', 'projected_carries', 'scenario_weight')), 'invented numeric hypothesis field')
    assessments = packet.get('analyst_assessments', [])
    if not isinstance(assessments, list) or not all(isinstance(a, dict) for a in assessments):
        return errors + ['analyst_assessments: expected array of objects']
    for a in assessments:
        need(a.get('kind') == 'subjective_analyst_judgment', 'analyst judgment cannot become baseline fact')
        need(a.get('status') == 'research_only' and a.get('production_action') == 'none', 'analyst judgment cannot drive production action')
        gid = a.get('game_id')
        need(gid in scopes, 'analyst judgment unknown game scope')
        for fmt in a.get('formats', []):
            need(fmt in FORMATS and scopes.get(gid, {}).get('format_membership', {}).get(fmt) == 'confirmed_in_scope', 'analyst judgment format out of scope')
        for pid in a.get('player_master_ids', []):
            need(pid in players and players.get(pid, {}).get('game_id') == gid, 'analyst judgment invalid canonical linkage')
        refs(a.get('source_ids'), 'analyst judgment')
        for premise in a.get('factual_premises', []):
            source = sources.get(premise.get('source_id'), {})
            need(source.get('coverage') == 'verified', 'factual premise requires verified source')
            asserted = source.get('fact_assertions', {}).get(premise.get('fact_key'))
            need(bool(asserted) and asserted == premise.get('text'), 'unsupported or fabricated factual premise')
        for hid in a.get('source_hypothesis_ids', []):
            need(hid in seen, 'analyst judgment unknown hypothesis reference')
        for field in ('lean', 'supporting_reasoning', 'contrary_evidence', 'conditions', 'strongest_alternative', 'construction_implications', 'what_changes_view'):
            need(bool(a.get(field)), 'analyst judgment missing ' + field)
        need(isinstance(a.get('confidence_label'), str), 'analyst conviction must remain unquantified')
        need(a.get('numeric_effect_proposal') is None and a.get('selection_weight') is None, 'analyst judgment numeric effect/weight prohibited')
        need(not any(k in a for k in ('probability', 'confidence_score', 'expected_targets', 'expected_carries')), 'invented numeric analyst judgment')
        expiry = time(a.get('expires_at'), 'analyst judgment expiry')
        if expiry and decision:
            need(expiry > decision, 'analyst judgment expired')
        if expiry and kickoff_clocks.get(gid):
            need(expiry <= kickoff_clocks[gid], 'analyst judgment expiry beyond kickoff')
        for construction in a.get('construction_implications', []):
            need(construction.get('action') == 'shadow_comparison_only', 'construction requires shadow-only action')
            need(construction.get('format') in a.get('formats', []), 'construction format outside assessment')
            for ids in construction.get('roles', {}).values():
                for pid in ids:
                    need(pid in a.get('player_master_ids', []), 'construction canonical identity outside assessment')
    synthesis = packet.get('slate_synthesis')
    if synthesis is not None:
        need(isinstance(synthesis, dict), 'slate synthesis must be an object')
        if isinstance(synthesis, dict):
            refs(synthesis.get('scope_source_ids'), 'slate synthesis scope')
            checklist = synthesis.get('game_checklist', [])
            complete = bool(checklist) and all(g.get('review_complete') is True for g in checklist)
            need(synthesis.get('all_games_reviewed') is complete, 'all-games review claim inconsistent with checklist')
            for ranked in synthesis.get('ranked_upside_leans', []):
                need(any(a.get('assessment_id') == ranked.get('assessment_id') for a in assessments), 'slate ranking unknown assessment')
            if not complete and synthesis.get('ranked_upside_leans'):
                need(synthesis.get('status') == 'preliminary_partial' and bool(synthesis.get('coverage_gap')), 'partial slate ranking requires coverage label')
            for g in checklist:
                if g.get('review_complete'):
                    need(all(g.get(k) == 'reviewed' for k in ('usage_review', 'injury_review', 'market_review', 'opponent_review')), 'game review lacks required evidence categories')
    if packet.get('scenario_assumptions') is not None:
        from .analyst_scenarios import validate_scenarios
        errors.extend(validate_scenarios(packet))
    if packet.get('discovery') is not None:
        from .analyst_discovery import validate_discovery
        errors.extend(validate_discovery(packet))
    if packet.get('captain_analysis') is not None:
        from .captain_analyst import validate_captain_analysis
        errors.extend(validate_captain_analysis(packet))
    if packet.get('defense_kicker_analysis') is not None:
        from .defense_kicker_analyst import validate_specialists
        errors.extend(validate_specialists(packet))
    if packet.get('contrarian_analysis') is not None:
        from .analyst_focus import validate_contrarian
        errors.extend(validate_contrarian(packet))
    if packet.get('weekly_role_review') is not None:
        from .weekly_role_review import validate_weekly_review
        errors.extend(validate_weekly_review(packet))
    if packet.get('team_game_outlook') is not None:
        from .team_game_outlook import validate_outlook
        errors.extend(validate_outlook(packet['team_game_outlook'],games=packet['games'],decision_at=packet['decision_at']))
    need(bool(packet.get('hypotheses')), 'missing hypotheses')
    return errors



def validate(packet):
    try:
        from .analyst_intents import validate_intents
        errors = _validate(packet)
        return errors + (validate_intents(packet) if not errors else [])
    except (KeyError, TypeError, ValueError, AttributeError, IndexError) as exc:
        return ['malformed packet: ' + str(exc)]


from hashlib import sha256
from pathlib import Path

LEDGER = Path('artifacts/football_analyst_packets')

def packet_digest(packet):
    return sha256(json.dumps(packet, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def import_packet(packet, *, directory=None):
    """Validate then save an immutable, idempotent packet; no live model changes."""
    errors = validate(packet)
    if errors:
        raise ValueError('Invalid Analyst packet: ' + '; '.join(errors))
    key = packet_digest(packet)
    root = Path(directory) if directory is not None else LEDGER
    root.mkdir(parents=True, exist_ok=True)
    path = root / (key + '.json')
    payload = json.dumps(packet, indent=2, allow_nan=False) + '\n'
    try:
        with path.open('x') as handle:
            handle.write(payload)
    except FileExistsError:
        if packet_digest(json.loads(path.read_text())) != key:
            raise ValueError('Existing packet ledger hash mismatch')
    return dict(contract_id=packet['contract_id'], packet_id=packet['packet_id'],
                analyst_packet_sha256=key, path=str(path), decision_at=packet['decision_at'],
                frozen_at=packet['frozen_at'], assessment_count=len(packet.get('analyst_assessments', [])))

def load_packet(key, *, directory=None):
    if not isinstance(key, str) or len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
        raise ValueError('Invalid Analyst packet hash')
    root = Path(directory) if directory is not None else LEDGER
    try:
        packet = json.loads((root / (key + '.json')).read_text())
    except (OSError, ValueError) as exc:
        raise ValueError('Analyst packet is unavailable or malformed; import it again') from exc
    if packet_digest(packet) != key:
        raise ValueError('Analyst packet ledger hash mismatch')
    errors = validate(packet)
    if errors:
        raise ValueError('Invalid Analyst packet: ' + '; '.join(errors))
    return packet
