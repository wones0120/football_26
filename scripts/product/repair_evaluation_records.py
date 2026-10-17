#!/usr/bin/env python3
"""Recover evaluation evidence without replaying or modifying optimizer outputs.

Repairs derived contest scope using native contest-ID history + saved schedule.
Original sources, reports and observations are retained. --apply is explicit.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import pandas as pd
from sqlalchemy import text
from backend.app.db import engine
from backend.app.product_services.evaluation_record import append_record, capture_run, recover_entry_candidates
from backend.app.product_services.contest_scope import saved_history_scope
from backend.app.product_services.contest_ownership_identity import attach_salary_identities, persist_observations
from backend.app.product_services.entry_history import load_history, enrich_contests
from backend.app.product_services.ownership import OwnershipService
from backend.app.product_services.slate_learning import SlateLearningService, build_weekly_learning_report


def recover_reviews(connection, manifest_path):
    """Import operator-reviewed links to retained conversations, never infer intent."""
    for link in json.loads(manifest_path.read_text()):
        source_path = Path(link['source_file'])
        source_bytes = source_path.read_bytes()
        source = json.loads(source_bytes)
        run_ids = connection.execute(text("""SELECT optimizer_run_id FROM target.optimizer_run
            WHERE optimizer_run_id LIKE :prefix"""), {'prefix': link['run_prefix'] + '%'}).scalars().all()
        if len(run_ids) != 1:
            raise ValueError('Review run prefix must uniquely identify a saved run')
        run_id = run_ids[0]
        snapshot_id = capture_run(connection, run_id, recovery=True)
        snapshot = connection.execute(text("""SELECT record_json->'payload' FROM target.evaluation_record
            WHERE record_id=:id"""), {'id':snapshot_id}).scalar_one()
        mappings = [row for row in snapshot['candidate_lineup_mapping'] if any(
            saved['saved_lineup_number'] == link['saved_lineup_number'] for saved in row['saved_lineups'])]
        saved = [row for row in snapshot['saved_lineups'] if row['lineup_number'] == link['saved_lineup_number']]
        if not saved:
            raise ValueError('Review saved lineup number is unavailable')
        append_record(connection, 'recovered_ai_review', {
            'review':link, 'source_document':source, 'candidate_lineup_mapping':mappings,
            'saved_lineup_ids':[row['lineup_id'] for row in saved],
            'candidate_mapping_status':'matched' if mappings else 'original_candidate_unavailable',
            'contest_assignments':None, 'submission_confirmed':False,
            'snapshot_record_id':snapshot_id}, run_id=run_id,
            source={'path':str(source_path), 'sha256':hashlib.sha256(source_bytes).hexdigest(),
                    'thread_id':source['thread']['id']})


def repair(season, week, user, output, apply=False, reviews=None):
    output.mkdir(parents=True, exist_ok=True)
    manifest = {'season': season, 'week': week, 'entry_user': user, 'contests': [], 'captured_runs': []}
    with engine.connect() as c:
        contests = [dict(r) for r in c.execute(text('''SELECT DISTINCT c.* FROM target.dfs_contest c
            JOIN target.dfs_contest_entry_result e USING(contest_id)
            WHERE c.season=:season AND (c.week=:week OR c.contest_id IN (
                SELECT record_json#>>'{payload,contest_id}' FROM target.evaluation_record
                WHERE kind='scope_correction' AND record_json#>>'{payload,before,week}'=CAST(:week AS TEXT)
                AND record_json#>>'{payload,before,season}'=CAST(:season AS TEXT))) AND lower(regexp_replace(coalesce(e.entry_name,''),
                '\\s+\\([0-9]+/[0-9]+\\)$',''))=:user ORDER BY c.contest_id'''),
            {'season': season, 'week': week, 'user': user.lower()}).mappings()]
    corrected_scopes = set()
    for contest in contests:
        cid = contest['contest_id']
        with engine.begin() as c:
            verification = saved_history_scope(c, cid, season, week)
            source = dict(c.execute(text('SELECT * FROM target.source_file_import WHERE source_file_id=:id'),
                            {'id': contest['source_file_id']}).mappings().one())
            path = Path(source['original_path'])
            if not path.exists():
                path = path.parent / 'Processed' / path.name
            if path.exists():
                raw = path.read_bytes()
                assert OwnershipService._source_file_info(path)['content_sha256'] == source['content_sha256'], 'Source content changed'
                source['archive_sha256'] = hashlib.sha256(raw).hexdigest()
                retained = output / (source['content_sha256'] + path.suffix)
                if not retained.exists():
                    retained.write_bytes(raw)
                source['retained_copy'] = str(retained.resolve())
            target_week = verification.get('week', week)
            if verification['status'] == 'conflict' and 'week' not in verification:
                raise ValueError(f'Conflicting contest date evidence: {cid}')
            details = {'contest_id': cid, 'before': contest, 'verified_scope': verification, 'source': source}
            if apply:
                append_record(c, 'contest_evidence', details, source={'source_file_id': contest['source_file_id']})
                if target_week != contest['week']:
                    append_record(c, 'scope_correction', {'contest_id': cid, 'before': {'season': season, 'week': week, 'slate': contest['slate_id']},
                        'after': {'season': season, 'week': target_week, 'slate': contest['slate_id']}, 'verification': verification},
                        source={'source_file_id': contest['source_file_id']})
                    c.execute(text('UPDATE target.dfs_contest SET week=:week,updated_at=now() WHERE contest_id=:id'),
                              {'week': target_week, 'id': cid})
                history, _, _ = load_history(c)
                enriched = enrich_contests([contest], history)[0]
                if enriched.get('entry_fee') is not None:
                    c.execute(text('''UPDATE target.dfs_contest SET entry_fee=coalesce(entry_fee,:fee),
                        contest_name=:name,prize_pool=coalesce(prize_pool,:prize),updated_at=now() WHERE contest_id=:id
                        AND (entry_fee IS DISTINCT FROM coalesce(entry_fee,:fee)
                          OR contest_name IS DISTINCT FROM :name
                          OR prize_pool IS DISTINCT FROM coalesce(prize_pool,:prize))'''),
                        {'fee': enriched['entry_fee'], 'name': enriched['contest_name'], 'prize': enriched.get('prize_pool'), 'id': cid})
                # Append derived identities; never replace original observations.
                rows = [dict(r) for r in c.execute(text('''SELECT DISTINCT ON (player_display_name,roster_position)
                    contest_id,source_file_id,player_display_name,roster_position,actual_ownership AS pct_drafted,
                    actual_points AS fpts FROM target.contest_ownership_observation WHERE contest_id=:id
                    ORDER BY player_display_name,roster_position,recorded_at DESC'''), {'id': cid}).mappings()]
        if apply and rows:
            frame = pd.DataFrame(rows).assign(season=season,week=target_week,slate=contest['slate_id'])
            resolved = attach_salary_identities(engine, frame)
            details['identity_counts'] = persist_observations(engine, resolved)
        manifest['contests'].append(details)
        corrected_scopes.add((season, target_week, contest['slate_id']))
    if not apply:
        return manifest
    if reviews:
        with engine.begin() as c:
            recover_reviews(c, reviews)
    service = SlateLearningService(engine=engine)
    reports = []
    for sy, wk, slate in sorted(corrected_scopes):
        report = service.generate(season=sy, week=wk, slate=slate, entry_user=user)
        if any(e['identity_complete'] and not e['lineup_id'] for e in report['entries']):
            with engine.begin() as c:
                recover_entry_candidates(c,season=sy,week=wk,slate=slate,
                    entries=[{**e,'contest_format':next((r['contest_format'] for r in contests if r['contest_id']==e['contest_id']), 'showdown')}
                             for e in report['entries']])
            report = service.generate(season=sy, week=wk, slate=slate, entry_user=user)
        with engine.begin() as c:
            run_ids = sorted(set(report['run_ids'].get('optimizer_run_ids', [])) | {
                match['optimizer_run_id'] for entry in report['entries'] for match in entry.get('candidate_lineage', [])})
            for run_id in run_ids:
                record_id = capture_run(c, run_id, recovery=True)
                manifest['captured_runs'].append({'optimizer_run_id': run_id, 'record_id': record_id})
            append_record(c, 'submitted_entries', {'report_id': report['report_id'], 'scope': [sy,wk,slate],
                'entries': report['entries'], 'missing_evidence': report['missing_evidence']},
                source={'source_file_ids': report['source_file_ids']})
        report = service.generate(season=sy, week=wk, slate=slate, entry_user=user)
        (output / f'{sy}-w{wk}-{slate}.json').write_text(json.dumps(report,default=str,indent=2))
        reports.append(report)
    (output/'repair_manifest.json').write_text(json.dumps(manifest,default=str,indent=2))
    current = [r for r in reports if r['week'] == week]
    # Reuse the standard report builder and persisted actuals. Never fetch today's
    # projections, rerun optimization, or infer missing prelock recommendations.
    weekly = build_weekly_learning_report(season=season,week=week,entry_user=user,slate_reports=current,
        correlation_loader=service._correlation_samples,
        weekly_stats=None)
    weekly['evaluation_repair'] = {'manifest': str((output/'repair_manifest.json').resolve()),
        'corrected_contests': [r['contest_id'] for r in manifest['contests'] if r['verified_scope'].get('week',week) != week]}
    (output/'week5_report.json').write_text(json.dumps(weekly,default=str,indent=2))
    with engine.begin() as c:
        append_record(c, 'weekly_report', weekly, source={'operation': 'saved_evidence_recovery'})
    (output/'repair_manifest.json').write_text(json.dumps(manifest,default=str,indent=2))
    return manifest


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season',type=int,required=True);parser.add_argument('--week',type=int,required=True)
    parser.add_argument('--entry-user',required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--reviews',type=Path)
    args=parser.parse_args()
    result=repair(args.season,args.week,args.entry_user,args.output,args.apply,args.reviews)
    print(json.dumps({'contests':len(result['contests']),'captured_runs':result['captured_runs'],
        'identity_counts':{r['contest_id']:r.get('identity_counts') for r in result['contests']}},default=str))
