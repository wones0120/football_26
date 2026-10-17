"""Append-only evaluation evidence. No projection, solver or selection writes."""
from __future__ import annotations

from datetime import datetime

import hashlib
import json

from sqlalchemy import text

from .optimizer_effectiveness import candidate_signature, chronological_validation, extract_saved_pool


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


def append_record(connection, kind, payload, *, run_id=None, source=None):
    envelope = {'contract': 'evaluation_record_v1', 'kind': kind, 'optimizer_run_id': run_id,
                'source': source, 'payload': payload}
    sha = digest(envelope)
    connection.execute(text('''INSERT INTO target.evaluation_record
        (record_id,kind,optimizer_run_id,evidence_sha256,record_json)
        VALUES (:id,:kind,:run,:sha,CAST(:record AS JSONB)) ON CONFLICT DO NOTHING'''),
        {'id': 'evaluation-' + sha, 'kind': kind, 'run': run_id, 'sha': sha,
         'record': json.dumps(envelope, sort_keys=True, default=str, allow_nan=False)})
    return 'evaluation-' + sha


def snapshot_payload(run, lineups, projections):
    config = run['constraint_config_json']
    pool = extract_saved_pool(config, run['contest_format'])
    candidates = pool.pop('candidates', [])
    mappings = []
    for ordinal, candidate in enumerate(candidates, 1):
        signature = candidate_signature(candidate, run['contest_format'])
        mappings.append({'candidate_id': f"{run['optimizer_run_id']}:candidate:{ordinal}",
            'source_candidate_id': candidate.get('candidate_id'), 'candidate_ordinal': ordinal,
            'canonical_roster': list(signature or ()),
            'ai_review_candidate_id': f"{run['optimizer_run_id']}:{digest(signature)[:16]}" if run['contest_format']=='showdown' else None,
            'selector_rank': candidate.get('selector_rank', candidate.get('rank')),
            'saved_lineups': [{'lineup_id': row['lineup_id'], 'saved_lineup_number': row['lineup_number']}
                for row in lineups if candidate_signature({'players': row['players']}, run['contest_format']) == signature]})
    frozen_inputs = config.get('showdown_evidence_snapshot') or config.get('strategy_runtime', {}).get('classic_run_input_snapshot')
    return {'frozen_input_status': 'original_snapshot' if frozen_inputs else 'legacy_saved_configuration_only',
            'run': run, 'pool': pool, 'original_candidates': candidates, 'candidate_lineup_mapping': mappings,
            'frozen_projections': projections, 'saved_lineups': lineups,
            'timing': chronological_validation({**run, 'optimizer_created_at': run['created_at'],
                 'saved_lineup_games': sorted({p.get('player_json', {}).get('game_id')
                     for lineup in lineups for p in lineup['players'] if p.get('player_json', {}).get('game_id')})},
                                                {**pool, 'candidates': candidates}),
            'identifier_contract': {'candidate_id': 'run-scoped candidate identity; never a saved lineup ID',
                'lineup_id': 'persisted lineup identity', 'saved_lineup_number': 'display order within saved run',
                'selector_rank': 'recorded selector rank only; null when only generation order was saved'},
            'missing': ([pool.get('reason')] if pool['status'] != 'original_candidate_pool' else [])
                + ([] if projections else ['frozen_projection_rows'])
                + ([] if frozen_inputs else ['authenticated_original_input_snapshot'])}


def capture_run(connection, run_id, *, recovery=False):
    run = dict(connection.execute(text('SELECT * FROM target.optimizer_run WHERE optimizer_run_id=:id'),
                                  {'id': run_id}).mappings().one())
    if run['status'] != 'completed':
        return None
    lineups = [dict(row) for row in connection.execute(text('''
        SELECT l.lineup_id,l.lineup_number,jsonb_agg(jsonb_build_object(
            'player_id',p.player_id,'roster_position',p.roster_position,'player_json',p.player_json)
            ORDER BY p.slot_index) AS players
        FROM target.lineup l JOIN target.lineup_player p USING(lineup_id)
        WHERE l.optimizer_run_id=:id GROUP BY l.lineup_id ORDER BY l.lineup_number'''), {'id': run_id}).mappings()]
    projections = [dict(row) for row in connection.execute(text('''
        SELECT * FROM target.player_projection WHERE projection_run_id=:id ORDER BY player_id,game_id'''),
        {'id': run['projection_run_id']}).mappings()] if run['projection_run_id'] else []
    payload = snapshot_payload(run, lineups, projections)
    payload['capture_basis'] = 'recovered_saved_evidence' if recovery else 'optimizer_completion'
    record_id = append_record(connection, 'run_snapshot', payload, run_id=run_id,
                             source={'table': 'target.optimizer_run', 'configuration_sha256': digest(run['constraint_config_json'])})
    # Record app output as an output set, not as an invented contest assignment.
    config = run['constraint_config_json']
    append_record(connection, 'app_recommendation', {
        'snapshot_record_id': record_id, 'saved_lineup_ids': [row['lineup_id'] for row in lineups],
        'candidate_lineup_mapping': payload['candidate_lineup_mapping'],
        'recorded_recommendation': config.get('gpp_recommendation') or (config.get('decision_snapshot') or {}).get('single_lineup_selection'),
        'contest_assignments': None, 'submitted_entries': None,
        'basis': 'saved_app_output_not_submission_intent'}, run_id=run_id, source={'table': 'target.optimizer_run'})
    return record_id


def record_export(connection, run_id, filename, content, lineups, *, upload_clearance_record_id=None):
    saved = [dict(row) for row in connection.execute(text('''
        SELECT l.lineup_id,l.lineup_number,jsonb_agg(jsonb_build_object(
            'player_id',p.player_id,'roster_position',p.roster_position)) AS players
        FROM target.lineup l JOIN target.lineup_player p USING(lineup_id)
        WHERE l.optimizer_run_id=:id GROUP BY l.lineup_id'''), {'id': run_id}).mappings()]
    fmt = connection.execute(text('SELECT contest_format FROM target.optimizer_run WHERE optimizer_run_id=:id'), {'id': run_id}).scalar_one()
    rows = []
    for n, lineup in enumerate(lineups, 1):
        signature = candidate_signature({'players': lineup}, fmt)
        matches = sorted(r['lineup_id'] for r in saved if candidate_signature(r, fmt) == signature)
        rows.append({'export_row_number': n, 'saved_lineup_ids': matches, 'canonical_roster': list(signature or ())})
    return append_record(connection, 'export', {'filename': filename,
        'content_sha256': hashlib.sha256(content).hexdigest(), 'content_hex': content.hex(),
        'rows': rows, 'submission_confirmed': False,
        **({'upload_clearance_record_id': upload_clearance_record_id} if upload_clearance_record_id else {})}, run_id=run_id, source={'operation': 'lineup_download'})


def record_recommendation(connection, run_id, payload):
    """Explicit app/AI decisions; no inferred approval, assignment or submission."""
    if payload.get('actor') not in {'app', 'ai', 'user'}:
        raise ValueError('actor must be app, ai or user')
    if (not isinstance(payload.get('source_reference'), str) or not payload['source_reference'].strip()
            or not isinstance(payload.get('candidate_ids'), list) or not payload['candidate_ids']
            or not all(isinstance(cid, str) for cid in payload['candidate_ids'])):
        raise ValueError('Recorded recommendations require a source reference and candidate IDs')
    snapshot = connection.execute(text('''SELECT record_json->'payload' FROM target.evaluation_record
        WHERE optimizer_run_id=:id AND kind='run_snapshot' ORDER BY recorded_at DESC LIMIT 1'''), {'id': run_id}).scalar_one_or_none()
    if not snapshot:
        raise ValueError('A frozen evaluation snapshot is required')
    candidates = {r['candidate_id']: r for r in snapshot['candidate_lineup_mapping']}
    if set(payload['candidate_ids']) - candidates.keys():
        raise ValueError('Candidate IDs must belong to this frozen run; lineup numbers and ranks are not IDs')
    mappings = [candidates[cid] for cid in payload['candidate_ids']]
    if not isinstance(payload.get('assignments', []), list) or not all(
            isinstance(a, dict) for a in payload.get('assignments', [])):
        raise ValueError('assignments must be a list of objects')
    for assignment in payload.get('assignments') or []:
        if assignment.get('candidate_id') not in payload['candidate_ids'] or not assignment.get('contest_id') or not assignment.get('entry_id'):
            raise ValueError('Assignments require a recommended candidate and native contest/entry IDs')
        if assignment.get('lineup_id') and assignment['lineup_id'] not in {
                r['lineup_id'] for r in candidates[assignment['candidate_id']]['saved_lineups']}:
            raise ValueError('Assignment lineup does not match the candidate')
    # The server records when intent was received; client timestamps cannot turn
    # retrospective explanations into prelock intent.
    return append_record(connection, 'recommendation', {
        **{key:value for key,value in payload.items() if key != 'recorded_at'},
        'candidate_lineup_mapping': mappings,
        'verified_lock_at': snapshot.get('timing', {}).get('first_saved_kickoff_at')}, run_id=run_id,
        source={'reference': payload['source_reference']})


def recover_entry_candidates(connection, *, season, week, slate, entries):
    """Exact canonical roster matches, with all matching variants retained.

    A candidate-only match never creates a saved lineup or proves entry intent.
    """
    targets = {str(e['entry_id']): candidate_signature({'players': e.get('players', [])},
                e.get('contest_format') or 'showdown') for e in entries if e.get('identity_complete')}
    matches = {key: [] for key in targets}
    rows = connection.execute(text('''SELECT optimizer_run_id,projection_run_id,created_at,
        data_cutoff_at,contest_format,constraint_config_json FROM target.optimizer_run
        WHERE season=:season AND week=:week AND upper(slate_id)=upper(:slate) AND status='completed'
        ORDER BY created_at,optimizer_run_id'''), {'season':season,'week':week,'slate':slate}).mappings()
    for run in rows:
        pool=extract_saved_pool(run['constraint_config_json'],run['contest_format'])
        for n,candidate in enumerate(pool.get('candidates',[]),1):
            signature=candidate_signature(candidate,run['contest_format'])
            for entry_id, expected in targets.items():
                if signature == expected:
                    matches[entry_id].append({'optimizer_run_id':run['optimizer_run_id'],
                        'projection_run_id':run['projection_run_id'],
                        'candidate_id':f"{run['optimizer_run_id']}:candidate:{n}",
                        'selector_rank':candidate.get('rank'), 'candidate_ordinal':n,
                        'pool_sha256':pool['sha256']})
    for entry in entries:
        append_record(connection,'entry_candidate_lineage',{'season':season,'week':week,'slate':slate,
            'contest_id':entry['contest_id'],'entry_id':entry['entry_id'],
            'matches':matches.get(str(entry['entry_id']),[]),'basis':'exact_canonical_roster_and_captain',
            'intent_proven':False}, source={'operation':'original_saved_candidate_search'})
    return matches


def prelock_recommendation_assignments(records):
    """Only server-recorded intent before the authenticated saved lock is usable."""
    assignments = []
    for record in records:
        payload = record['payload']
        try:
            lock = datetime.fromisoformat(payload['verified_lock_at'])
            recorded = record['recorded_at']
            if isinstance(recorded, str):
                recorded = datetime.fromisoformat(recorded)
            if not lock.tzinfo or not recorded.tzinfo or recorded >= lock:
                continue
        except (KeyError, TypeError, ValueError):
            continue
        mappings = {m['candidate_id']:m for m in payload['candidate_lineup_mapping']}
        for assignment in payload.get('assignments', []):
            mapping = mappings[assignment['candidate_id']]
            assignments.append({**assignment, 'optimizer_run_id':record['optimizer_run_id'],
                'intended_players':[{'player_id':pid,'roster_position':'CPT' if cpt else 'FLEX'}
                                    for pid,cpt in mapping.get('canonical_roster', [])]})
    return assignments
