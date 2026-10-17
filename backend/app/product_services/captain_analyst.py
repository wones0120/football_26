"""Captain-conditioned FLEX sensitivities, separate from model truth.

The packet supplies sourced qualitative capability judgments. Numeric responses
below are versioned design sensitivities, never forecasts or winning probabilities.
Unknown opponents retain competing paths; no path requires a bringback.
"""
from copy import deepcopy
import math

from .analyst_packets import clock

CONTRACT = 'captain_analysis_v1'
STATES = ('competitive_scoring', 'trailing_productive_passing', 'drive_stall_runout')
DIMENSIONS = ('quarterback', 'offense', 'opposing_defense', 'availability_role', 'pace_drives')
# Declared sensitivity parameters: (opponent pass, opponent rush, Captain-team pass, rush).
RESPONSES = {
    'competitive_scoring': (1.15, 1.05, 1.15, .95),
    'trailing_productive_passing': (1.25, .75, 1.05, 1.15),
    'drive_stall_runout': (.65, .75, .85, 1.25),
}


def validate_captain_analysis(packet):
    block = packet.get('captain_analysis')
    if block is None:
        return []
    errors = []
    def need(ok, message):
        if not ok: errors.append('Captain analysis: ' + message)
    need(isinstance(block, dict) and block.get('contract_id') == CONTRACT, 'unknown contract')
    if not isinstance(block, dict): return errors
    need(isinstance(packet.get('scenario_assumptions'), dict), 'requires typed scenario_assumptions')
    players = {p['player_master_id']: p for p in packet.get('players', [])}
    games = {g['game_id']: g for g in packet.get('games', [])}
    sources = {s['source_id']: s for s in packet.get('sources', [])}
    hypotheses = {h['hypothesis_id']: h for h in packet.get('hypotheses', [])}
    need(not any(k in block for k in ('probability', 'scenario_weight', 'confidence_score')), 'probabilities are unsupported')
    def evidence(item, gid, supported, team):
        need(isinstance(item.get('evidence'), dict), 'evidence dimensions required')
        for dimension in DIMENSIONS:
            entry = (item.get('evidence') or {}).get(dimension, {})
            need(entry.get('status') in {'reviewed', 'unavailable'}, dimension + ' review status required')
            need(bool(entry.get('summary')), dimension + ' summary required')
            refs = entry.get('source_ids', [])
            need(isinstance(refs, list), dimension + ' source references must be an array')
            need(all(s in sources for s in refs), dimension + ' unknown source')
            if entry.get('status') == 'reviewed':
                need(bool(refs) and all(sources.get(s, {}).get('coverage') == 'verified' for s in refs), dimension + ' reviewed evidence requires verified sources')
            if supported:
                need(entry.get('status') == 'reviewed', 'supported capability requires all evidence dimensions reviewed')
            for pid in entry.get('player_master_ids', []):
                need(pid in players and players[pid].get('game_id') == gid, 'evidence canonical identity outside game')
            if dimension == 'quarterback' and entry.get('status') == 'reviewed':
                need(any(players.get(pid, {}).get('position') == 'QB' and players.get(pid, {}).get('team') == team for pid in entry.get('player_master_ids', [])), 'quarterback evidence requires assessed-team canonical QB')
            if dimension == 'availability_role' and entry.get('status') == 'reviewed':
                need(bool(entry.get('player_master_ids')), 'availability evidence requires canonical player linkage')
        need(bool(item.get('supporting_evidence')) and bool(item.get('contrary_evidence')) and bool(item.get('unknowns')), 'support, disconfirmation and unknowns required')
        refs = item.get('hypothesis_ids', [])
        need(isinstance(refs, list) and bool(refs) and all(h in hypotheses and hypotheses[h].get('game_id') == gid and 'SHOWDOWN' in hypotheses[h].get('formats', []) for h in refs), 'known Showdown hypotheses required')
        try:
            expiry = clock(item.get('expires_at'))
            need(clock(packet['decision_at']) < expiry <= clock(games[gid]['kickoff_at']), 'invalid expiry')
        except (KeyError, TypeError, ValueError): need(False, 'invalid expiry clock')
    opponents = block.get('opponents', [])
    need(isinstance(opponents, list), 'opponents must be an array')
    seen = set()
    for item in opponents if isinstance(opponents, list) else []:
        if not isinstance(item, dict): need(False, 'opponent must be an object'); continue
        gid, team = item.get('game_id'), item.get('team')
        key = (gid, team)
        need(key not in seen, 'duplicate opponent assessment'); seen.add(key)
        need(gid in games and team in games.get(gid, {}).get('teams', []) and games.get(gid, {}).get('format_membership', {}).get('SHOWDOWN') == 'confirmed_in_scope', 'opponent outside Showdown scope')
        state = item.get('capability')
        need(state in (*STATES, 'unknown'), 'invalid opponent capability')
        alternatives = item.get('alternative_capabilities')
        need(isinstance(alternatives, list) and bool(alternatives) and len(set(alternatives)) == len(alternatives) and all(s in STATES for s in alternatives), 'distinct alternative capabilities required')
        need(state not in (alternatives or []), 'primary capability repeated as alternative')
        need(not any(k in item for k in ('probability', 'confidence_score', 'fantasy_point_bonus')), 'capability probabilities/bonuses prohibited')
        evidence(item, gid, state != 'unknown', team)
    assessments = block.get('captains', [])
    need(isinstance(assessments, list), 'captains must be an array')
    seen = set()
    for item in assessments if isinstance(assessments, list) else []:
        if not isinstance(item, dict): need(False, 'Captain assessment must be an object'); continue
        pid = item.get('player_master_id'); gid = players.get(pid, {}).get('game_id')
        need(pid in players and pid not in seen, 'unknown/duplicate canonical Captain'); seen.add(pid)
        need(item.get('mechanism_status') in {'supported', 'unknown', 'unsupported'}, 'mechanism status required')
        need(bool(item.get('high_end_path')), 'high-end path required')
        need(not any(k in item for k in ('probability', 'fantasy_point_bonus', 'confidence_score')), 'Captain probability/bonus prohibited')
        evidence(item, gid, item.get('mechanism_status') == 'supported', players.get(pid, {}).get('team'))
    return errors


def condition_captains(packet, rows, base_scenarios, *, decision_at, locked_captain=None):
    """Expand only the current prepared shortlist; legal model remains authoritative."""
    from .analyst_scenarios import build_scenarios, _measurement
    decision = clock(decision_at)
    block = packet['captain_analysis']
    declared = {p['player_master_id']: p for p in packet['players']}
    games = {g['game_id']: g for g in packet['games']}
    opponents = {(a['game_id'], a['team']): a for a in block.get('opponents', [])}
    opinions = {a['player_master_id']: a for a in block.get('captains', [])}
    definitions, assessments = [], []
    for row in rows:
        pid = str(row['player_id'])
        if locked_captain and pid != locked_captain: continue
        if not row.get('showdown_captain_shortlisted', False): continue
        player = declared.get(pid)
        if not player: raise ValueError('Captain analysis requires packet identity for every eligible Captain')
        gid, team = player['game_id'], player['team']
        opponent = next(t for t in games[gid]['teams'] if t != team)
        assessment = opponents.get((gid, opponent))
        opinion = opinions.get(pid)
        for item in (assessment, opinion):
            if item and clock(item['expires_at']) <= decision: raise ValueError('Captain analysis expired')
        states = list(STATES) if not assessment or assessment['capability'] == 'unknown' else [assessment['capability'], *assessment['alternative_capabilities']]
        status = opinion['mechanism_status'] if opinion else 'unknown'
        position = row['position']
        mechanism = {'QB': 'shared_passing', 'WR': 'receiving_concentration', 'TE': 'receiving_concentration', 'RB': 'rushing_completion'}.get(position, 'unmodeled_scoring_path')
        if status == 'unsupported': mechanism = 'unmodeled_scoring_path'
        summary = dict(player_master_id=pid, player_name=row.get('name', row.get('player_name', pid)), game_id=gid, team=team, position=position,
            mechanism=mechanism, mechanism_status=status,
            high_end_path=opinion['high_end_path'] if opinion else 'Conditional opportunity sensitivity only; evidence does not establish this Captain reaches the high end.',
            opponent_team=opponent, opponent_capability=assessment['capability'] if assessment else 'unknown',
            opponent_assessment=deepcopy(assessment), captain_assessment=deepcopy(opinion),
            unknowns=deepcopy(opinion.get('unknowns', [])) if opinion else ['No sourced Captain-specific mechanism assessment'],
            scenario_ids=[], limitations=['Sensitivity hypotheses, not calibrated simulation; salary and role opportunity cost remain in legal FLEX solves.'])
        summary['unknowns'].extend(deepcopy(assessment.get('unknowns', [])) if assessment else ['No sourced opponent capability assessment'])
        # Eligibility is not evidence for an automatically authored ceiling story.
        # A sourced starter role with positive channel opportunity can support a
        # provisional sensitivity. Explicit user Captain locks remain what-ifs.
        channel = 'carries' if position == 'RB' else 'targets'
        measured_role = _measurement(player, channel, decision)[0] if position != 'QB' else None
        role_opportunity_source='packet_attributed_workload'
        if measured_role is None and position in {'RB','WR','TE'}:
            proxy=row.get('projected_'+channel)
            if type(proxy) in (float,int) and math.isfinite(proxy) and proxy>=0:
                measured_role=float(proxy);role_opportunity_source='fresh_prepared_projection_proxy:'+channel
        primary_role = row.get('canonical_role') == 'expected_starter'
        credible_role = primary_role and bool(row.get('role_source')) and (
            position == 'QB' and row.get('is_starting_qb', row.get('showdown_qb_eligible', False))
            or position in {'RB','WR','TE'} and measured_role is not None and measured_role > 0)
        explicit_what_if = bool(locked_captain and pid == locked_captain)
        if not explicit_what_if and (status == 'unsupported' or (status != 'supported' and not credible_role)):
            summary.update(generation_status='suppressed_unsupported_automatic_story',
                suppression_reason='No sourced positive primary-role opportunity or supported Captain-specific high-end mechanism; legal eligibility alone is insufficient')
            assessments.append(summary)
            continue
        summary['story_authority'] = 'supported_captain_opinion' if status == 'supported' else 'explicit_locked_captain_what_if' if explicit_what_if else 'provisional_positive_sourced_primary_role'
        summary['measured_channel_opportunity'] = measured_role
        summary['opportunity_evidence_source'] = role_opportunity_source
        members = [p for p in packet['players'] if p['game_id'] == gid and p['team'] == team and p['position'] in {'RB', 'WR', 'TE'} and p['player_master_id'] in {str(r['player_id']) for r in rows}]
        measured = [_measurement(p, 'targets', decision)[0] for p in members]
        concentration = mechanism == 'receiving_concentration' and measured and all(v is not None for v in measured) and sum(measured) > 0 and any(p['player_master_id'] == pid and v > 0 for p, v in zip(members, measured)) and sum(v for p, v in zip(members, measured) if p['player_master_id'] != pid) > .08 * sum(measured)
        if mechanism == 'receiving_concentration' and not concentration:
            summary['limitations'].append('Complete positive target measurements unavailable: no invented target concentration; shared passing sensitivity only.')
        seen_definitions={}
        for base in base_scenarios:
            if not any(a['game_id'] == gid for a in base['assumptions']): continue
            for state in states:
                opass, orush, ownpass, ownrush = RESPONSES[state]
                from .team_game_outlook import conditional_factors
                fitted_opponent=conditional_factors(packet,gid,opponent,state,conditioned_on_team=opponent)
                fitted_own=conditional_factors(packet,gid,team,state,conditioned_on_team=opponent)
                fitted_response=bool(fitted_opponent and fitted_own)
                if fitted_response:
                    opass,orush=fitted_opponent;ownpass,ownrush=fitted_own
                if not fitted_response and mechanism in {'shared_passing', 'receiving_concentration'}: ownpass = max(ownpass, 1.2)
                elif not fitted_response and mechanism == 'rushing_completion': ownrush = max(ownrush, 1.2)
                # Replace volume channels for this game; retain explicitly declared transfers/concentration.
                assumptions = [deepcopy(a) for a in base['assumptions'] if a['game_id'] != gid or a['kind'] not in {'passing_volume', 'rushing_volume'}]
                for side, passing, rushing in ((team, ownpass, ownrush), (opponent, opass, orush)):
                    assumptions.extend([dict(kind='passing_volume', game_id=gid, team=side, factor=passing, elasticity=.6), dict(kind='rushing_volume', game_id=gid, team=side, factor=rushing, elasticity=.6)])
                if concentration and not any(a['kind'] == 'target_concentration' and a['team'] == team and a['game_id'] == gid for a in assumptions):
                    assumptions.append(dict(kind='target_concentration', game_id=gid, team=team, player_master_ids=[pid], share_delta=.08, elasticity=.6))
                sid = base['scenario_id'] + ':CPT:' + pid + ':' + state
                definition = dict(scenario_id=sid, label=base['label'] + ' / ' + mechanism + ' / ' + state,
                    hypothesis_ids=list(dict.fromkeys(base['hypothesis_ids'] + (assessment or {}).get('hypothesis_ids', []) + (opinion or {}).get('hypothesis_ids', []))), assumptions=assumptions)
                from .analyst_shadow import digest
                key=digest(dict(state=state,assumptions=assumptions))
                if key in seen_definitions:
                    prior=seen_definitions[key]
                    prior['source_scenario_ids'].append(base['scenario_id'])
                    prior['hypothesis_ids']=list(dict.fromkeys(prior['hypothesis_ids']+definition['hypothesis_ids']))
                    continue
                temporary = deepcopy(packet)
                temporary.pop('captain_analysis', None)
                temporary.pop('contrarian_analysis', None)  # Parent finding retained in outer report; this is an internal derived ID.
                temporary['scenario_assumptions']['scenarios'] = [definition]
                scenario = build_scenarios(temporary, rows, fmt='SHOWDOWN', decision_at=decision_at)[0]
                if base.get('focus_requirement'):scenario['focus_requirement']=deepcopy(base['focus_requirement'])
                scenario.update(captain_player_master_id=pid, opponent_capability_branch=state,
                    capability_status='sourced_qualitative_assessment' if assessment and assessment['capability'] != 'unknown' else 'unknown_competing_sensitivities',
                    source_scenario_id=base['scenario_id'], captain_mechanism=mechanism,
                    source_scenario_ids=[base['scenario_id']],
                    volume_response_source='fitted_conditional_budget_ratios' if fitted_response else 'uncalibrated_fixed_design_fallback',
                    design_contract=CONTRACT, primary_capability_branch=bool(assessment and state == assessment['capability']))
                if fitted_response:
                    from .team_game_outlook import allocate_budget
                    outlook_game=next(g for g in packet['team_game_outlook']['games'] if g['game_id']==gid)
                    condition=outlook_game['teams'][opponent]['capability_branches'][state]
                    scenario['fitted_game_condition']=dict(conditioned_on_team=opponent,branch=state,empirical_event_probability=condition['probability'],probability_status=outlook_game['probability_status'],portfolio_weight_status='uncalibrated_design; no Captain-tail probability claim')
                    scenario['team_budget_allocation_audit']=[allocate_budget(packet,rows,gid,side,budget,decision_at=decision_at) for side,budget in [(opponent,condition['budget']),(team,condition['opponent_budget'])]]
                    for audit in scenario['team_budget_allocation_audit']:audit['audit_basis']='same joint conditional game budget; distinct from player fantasy elasticity'
                seen_definitions[key]=scenario
                definitions.append(scenario); summary['scenario_ids'].append(sid)
        assessments.append(summary)
    if locked_captain and not assessments: raise ValueError('Locked Captain is outside the current prepared Captain shortlist')
    if not definitions: raise ValueError('No applicable Captain-conditioned scenarios')
    return definitions, dict(contract_id=CONTRACT, assessments=assessments,
        eligible_captain_count=len(assessments), opponent_responses=RESPONSES,
        elasticity=.6, receiving_share_delta=.08, probabilities='uncalibrated_design_sensitivities',
        shortlist_expanded=False, forced_bringback=False,
        limitations=['Reviewed sources support qualitative judgments, not the numeric response magnitudes.', 'Unknown capability retains competing branches. No assumption that an opponent must score proves it can score.'])
