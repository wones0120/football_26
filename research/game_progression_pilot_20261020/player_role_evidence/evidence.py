"""Descriptive full-provider role evidence; no forecast or availability policy."""
from copy import deepcopy
from collections import Counter
from uuid import UUID

from backend.app.product_services.factual_designation import resolve_designation
from research.game_progression_pilot_20261020.player_opportunity_accounting.allocation import clock, CHANNELS

VERSION = 'retained_full_team_role_evidence_v1'


def build_evidence(extracted, official, *, cutoff, alias_recorded_at):
    """Use only source-extracted facts, never saved optimizer availability states.

    Dated observations and source-native canonical links are separate evidence.
    Retrospective aliases do not become predecision identity proof.
    """
    season, week = extracted['season'], extracted['week']
    if (official['season'], official['week']) != (season, week):
        raise ValueError('Official/roster period differs')
    decision = clock(cutoff)
    seen = set(); native_seen = set(); rows = []
    facts = extracted['facts'] + official['facts']
    actors = extracted['actors']
    teams = {a['team'] for a in actors}
    for actor in actors:
        pid = str(UUID(actor['player_master_id']))
        native = actor['source_player_id']
        if pid in seen or not native or native in native_seen:
            raise ValueError('Unique canonical and native roster identities required')
        seen.add(pid); native_seen.add(native)
    for fact in facts:
        pid = str(UUID(fact['player_id']))
        actor = next((a for a in actors if a['player_master_id'] == pid), None)
        if actor is None or (fact['team'], fact['position']) != (actor['team'], actor['position']):
            raise ValueError('Fact outside canonical roster/team/position')
        if (fact['season'], fact['week']) != (season, week):
            raise ValueError('Fact period differs')
        if not fact.get('source_ids') or not fact.get('source_uri'):
            raise ValueError('Source identity and URI required')
        if not clock(fact['observed_at']) <= clock(fact['received_at']) <= decision:
            raise ValueError('Missing/future/reversed source clocks')
        for key in ('effective_at', 'modified_at', 'published_at'):
            if fact.get(key) and clock(fact[key]) > clock(fact['observed_at']):
                raise ValueError('Event clock later than source observation')
        if fact.get('practice_date') and fact['practice_date'] > decision.date().isoformat():
            raise ValueError('Future practice date')
    for actor in actors:
        pid = actor['player_master_id']
        retained = [deepcopy(f) for f in facts if f['player_id'] == pid]
        resolution = resolve_designation(retained, cutoff=cutoff, player_id=pid,
            team=actor['team'], position=actor['position'], season=season, week=week)
        # No-game-designation and a depth rank do not establish dressing,
        # snaps or a healthy/full workload. Q is not cleared by user policy.
        designation = resolution['effective_designation']
        participation = 'UNAVAILABLE_REPORTED' if designation in {'OUT', 'INACTIVE', 'IR', 'SUSPENDED'} else 'UNKNOWN'
        depth = [f for f in retained if f['kind'] == 'depth_role'
                 and (decision-clock(f['observed_at'])).total_seconds() <= 86400]
        if depth:
            latest = max(clock(f.get('effective_at') or f['observed_at']) for f in depth)
            depth = [f for f in depth if clock(f.get('effective_at') or f['observed_at']) == latest]
        ranks = {f['depth_position'] for f in depth}
        rows.append(dict(**deepcopy(actor),
            roster_facts=[f for f in retained if f['kind'] == 'roster_status'],
            depth_rank=next(iter(ranks)) if len(ranks) == 1 else None,
            depth_facts=depth, depth_status='CONFLICT' if len(ranks)>1 else 'REPORTED' if ranks else 'UNKNOWN',
            dated_practice_facts=[f for f in retained if f['kind'] == 'practice'],
            designation_resolution=resolution, participation=participation,
            opportunity_shares=dict.fromkeys(CHANNELS), replacement_work=None,
            identity_available_before_cutoff_proven=False))
    coverage = {}
    for team in sorted(teams):
        members = [r for r in rows if r['team'] == team]
        proof = extracted['roster_coverage'][team]
        if set(proof['player_master_ids']) != {r['player_master_id'] for r in members}:
            raise ValueError('Retained provider roster universe differs')
        coverage[team] = dict(provider_actor_count=len(members),
            provider_rows_exhaustively_processed=proof['provider_rows_exhaustively_processed'],
            official_full_team_complete=False,
            depth_rank_known=sum(r['depth_rank'] is not None for r in members),
            game_designations=dict(Counter(r['designation_resolution']['effective_designation'] or 'UNKNOWN' for r in members)),
            participation=dict(Counter(r['participation'] for r in members)),
            dated_practice_actors=sum(bool(r['dated_practice_facts']) for r in members))
    return dict(version=VERSION, season=season, week=week, original_source_cutoff=cutoff,
        evidence_use='RETROSPECTIVE_DESCRIPTIVE_ONLY', alias_recorded_at=alias_recorded_at,
        alias_recorded_after_cutoff=clock(alias_recorded_at)>decision,
        actors=rows, team_coverage=coverage,
        identity_review_requests=deepcopy(extracted['identity_review_requests']+official['identity_review_requests']),
        source_report_row_links=deepcopy(official['identity_resolution_actions']),
        role_scope_exclusions=deepcopy(extracted['role_scope_exclusions']),
        historical_pregame_identity_proven=False, forecast=False, activation=False,
        allocation_consumer_connected=False, full_team_completeness_proven=False)
