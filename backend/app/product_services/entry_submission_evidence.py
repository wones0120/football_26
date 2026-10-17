"""Read-only distinctions between recorded assignments, exports and observations."""


def canonical_roster(players):
    return sorted((str(p['player_id']), str(p.get('roster_position') or '').upper() == 'CPT')
                  for p in players)


def _ledger_roster(value):
    if not isinstance(value, list) or not value:
        return None
    if any(not isinstance(p, (list, tuple)) or len(p) != 2
           or not p[0] or not isinstance(p[1], bool) for p in value):
        return None
    return sorted((str(pid), captain) for pid, captain in value)


def submission_evidence(entry, players, identity_complete, assignment, saved,
                        matches, related_exports, records, candidate_matches):
    """Roster/run links are retrospective associations, never submission proof."""
    roster = canonical_roster(players) if identity_complete else None
    run_ids = {str(m['optimizer_run_id']) for m in matches if m.get('optimizer_run_id')}
    run_ids.update(str(m['optimizer_run_id']) for m in candidate_matches if m.get('optimizer_run_id'))
    if assignment and assignment.get('optimizer_run_id'):
        run_ids.add(str(assignment['optimizer_run_id']))
    intended_players = saved.get(str(assignment.get('lineup_id')), []) if assignment else []
    comparison = ('equal' if canonical_roster(intended_players) == roster else 'different') \
        if roster is not None and intended_players else 'unknown'
    exported = []
    for export in related_exports:
        exported.append({**export, 'kind': 'portfolio_export', 'artifact_id': export['export_id'],
                         'linkage': 'portfolio_only', 'entry_specific': False,
                         'export_row_number': None, 'roster_equal': None,
                         'exact_slot_equal': None})
    for record in records:
        payload = record.get('payload') or {}
        run_id = str(record.get('optimizer_run_id') or '')
        base = {'kind': record['kind'], 'artifact_id': payload.get('export_id') or record['record_id'],
                'record_id': record['record_id'], 'optimizer_run_id': record.get('optimizer_run_id'),
                'created_at': record.get('recorded_at'), 'file_name': payload.get('filename'),
                'content_sha256': payload.get('content_sha256'), 'exact_slot_equal': None}
        previous = next((e for e in exported if e['artifact_id'] == base['artifact_id']), {})
        base = {**previous, **base, 'file_name': base['file_name'] or previous.get('file_name')}
        linked = []
        if record['kind'] == 'export':
            for row in payload.get('rows') or []:
                exported_roster = _ledger_roster(row.get('canonical_roster'))
                if roster is not None and exported_roster == roster:
                    linked.append({**base, **row, 'linkage': 'canonical_roster',
                                   'entry_specific': False, 'roster_equal': True})
        elif record['kind'] == 'portfolio_export':
            for number, row in enumerate(payload.get('assignments') or [], 1):
                native = row.get('row_json') or {}
                if (str(native.get('Contest ID', native.get('ContestId'))) == str(entry['contest_id'])
                        and str(native.get('Entry ID', native.get('EntryId'))) == str(entry['entry_id'])):
                    lineage = saved.get(str(row.get('lineup_id')), [])
                    linked.append({**base, 'linkage': 'native_contest_entry_ids',
                                   'entry_specific': True, 'export_row_number': number,
                                   'template_row_number': row.get('template_row_number'),
                                   'saved_lineup_ids': [row['lineup_id']] if row.get('lineup_id') else [],
                                   'roster_equal': canonical_roster(lineage) == roster
                                   if lineage and roster is not None else None})
        if linked:
            exported = [e for e in exported if e['artifact_id'] != base['artifact_id']]
            exported.extend(linked)
        elif run_id in run_ids and record['kind'] == 'export':
            exported.append({**base, 'linkage': 'optimizer_run_only', 'entry_specific': False,
                             'export_row_number': None, 'roster_equal': None})
    return {
        'intended': {'status': 'explicit_assignment' if assignment else 'unavailable',
                     'assignment': dict(assignment) if assignment else None,
                     'roster_comparison': comparison, 'original_submission_timing': 'unknown'},
        'exported': exported,
        'observed': {**{k: entry.get(k) for k in ('contest_id', 'entry_id', 'source_file_id',
                                                'ingested_at', 'entry_points', 'lineup_text')},
                     'identity_complete': identity_complete, 'canonical_roster': roster,
                     'basis': 'imported_standings', 'original_submission_timing': 'unknown'},
        'saved_lineup_matches': matches,
        'matching_status': ('ambiguous_runs' if len({m.get('optimizer_run_id') for m in matches}) > 1 else
                            'ambiguous_lineups' if len(matches) > 1 else
                            'explicit_assignment' if assignment else
                            'unique_roster_match' if matches else 'unavailable'),
        'limitation': 'Exports and roster equality do not establish original submission intent or timing.',
    }
