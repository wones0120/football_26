from copy import deepcopy
from unittest.mock import MagicMock

from backend.app.product_services.slate_learning import SlateLearningService, build_slate_learning_report
from backend.app.tests.product.test_slate_learning import NOW, complete_evidence


def report(evidence):
    return build_slate_learning_report(season=2026, week=1, slate='SUNDAY_NIGHT',
                                      entry_user='wones0120', evidence=evidence, generated_at=NOW)


def direct_record(roster=None):
    return dict(record_id='artifact-direct', kind='export', optimizer_run_id='optimizer-1',
                recorded_at=NOW, payload=dict(filename='direct.csv', content_sha256='direct-sha',
                    rows=[dict(export_row_number=2, saved_lineup_ids=['lineup-1'],
                               canonical_roster=roster if roster is not None else [['alpha', True], ['beta', False]])]))


def test_direct_download_without_assignment_is_visible_without_proving_intent():
    evidence = complete_evidence()
    evidence['assignments'] = []
    evidence['export_records'] = [direct_record()]
    result = report(evidence)
    entry = result['entries'][0]
    detail = entry['submission_evidence']
    assert entry['exports'] == []  # Existing portfolio interface stays intact.
    assert detail['intended']['status'] == 'unavailable'
    export = detail['exported'][0]
    assert export['artifact_id'] == 'artifact-direct'
    assert export['created_at'] == NOW and export['export_row_number'] == 2
    assert export['saved_lineup_ids'] == ['lineup-1']
    assert export['roster_equal'] is True and export['exact_slot_equal'] is None
    assert export['entry_specific'] is False and export['linkage'] == 'canonical_roster'
    assert 'entry:contest-1:entry-1:contest_entry_assignment' in result['missing_evidence']
    assert detail['observed']['source_file_id'] == 'source-1'
    assert detail['observed']['lineup_text'] == evidence['entries'][0]['lineup_text']
    changed = deepcopy(evidence)
    changed['export_records'][0]['record_id'] = 'other-artifact'
    assert report(changed)['evidence_hash'] != result['evidence_hash']


def test_portfolio_export_keeps_existing_interface_and_only_claims_available_linkage():
    evidence = complete_evidence()
    entry = report(evidence)['entries'][0]
    assert entry['exports'] == evidence['exports']
    detail = entry['submission_evidence']
    assert detail['intended']['status'] == 'explicit_assignment'
    assert detail['intended']['roster_comparison'] == 'equal'
    assert detail['intended']['original_submission_timing'] == 'unknown'
    assert detail['exported'][0]['linkage'] == 'portfolio_only'
    assert detail['exported'][0]['export_row_number'] is None
    evidence['export_records'] = [dict(kind='portfolio_export', record_id='portfolio-artifact',
        optimizer_run_id='optimizer-1', recorded_at=NOW,
        payload=dict(export_id='export-1', assignments=[dict(template_row_number=7,
            lineup_id='lineup-1', row_json={'Contest ID': 'contest-1', 'Entry ID': 'entry-1'})]))]
    export = report(evidence)['entries'][0]['submission_evidence']['exported'][0]
    assert export['record_id'] == 'portfolio-artifact'
    assert export['file_name'] == 'lineups.csv'
    assert export['export_row_number'] == 1 and export['template_row_number'] == 7
    assert export['entry_specific'] is True
    assert export['linkage'] == 'native_contest_entry_ids'


def test_identical_rosters_across_runs_are_ambiguous_even_with_newer_run_or_candidate_link():
    evidence = complete_evidence()
    evidence['assignments'] = []
    newer = deepcopy(evidence['lineup_players'])
    for player in newer:
        player.update(lineup_id='lineup-2', optimizer_run_id='optimizer-2', optimizer_created_at='2026-10-13')
    evidence['lineup_players'] += newer
    evidence['entry_candidate_lineage'] = [dict(contest_id='contest-1', entry_id='entry-1',
        matches=[dict(optimizer_run_id='optimizer-2')])]
    result = report(evidence)
    entry = result['entries'][0]
    assert entry['lineup_id'] is None and entry['optimizer_run_id'] is None
    assert entry['lineup_match_basis'] == 'ambiguous_canonical_lineup_signature'
    assert entry['submission_evidence']['matching_status'] == 'ambiguous_runs'
    assert {m['optimizer_run_id'] for m in entry['submission_evidence']['saved_lineup_matches']} == {'optimizer-1', 'optimizer-2'}
    assert 'entry:contest-1:entry-1:saved_lineup_lineage' in result['missing_evidence']
    evidence['assignments'] = complete_evidence()['assignments']
    assigned_entry = report(evidence)['entries'][0]
    assert assigned_entry['lineup_id'] == 'lineup-1'
    assert assigned_entry['submission_evidence']['intended']['status'] == 'explicit_assignment'
    assert assigned_entry['submission_evidence']['matching_status'] == 'ambiguous_runs'


def test_captain_difference_is_not_roster_equality_and_run_link_remains_limited():
    evidence = complete_evidence()
    evidence['export_records'] = [direct_record([['alpha', False], ['beta', True]])]
    detail = report(evidence)['entries'][0]['submission_evidence']
    export = next(e for e in detail['exported'] if e['kind'] == 'export')
    assert export['linkage'] == 'optimizer_run_only'
    assert export['export_row_number'] is None and export['roster_equal'] is None
    assert export['entry_specific'] is False
    evidence['assignments'] = []
    for player in evidence['lineup_players']:
        player['roster_position'] = 'FLEX' if player['player_id'] == 'alpha' else 'CPT'
    assert report(evidence)['entries'][0]['submission_evidence']['saved_lineup_matches'] == []


def test_flex_reordering_matches_roster_but_not_exact_slots():
    evidence = complete_evidence()
    evidence['assignments'] = []
    evidence['entries'][0]['lineup_text'] += ' FLEX Gamma Three'
    evidence['observations'].append(dict(evidence['observations'][1], player_id='gamma', player_display_name='Gamma Three'))
    extra = dict(evidence['lineup_players'][1], player_id='gamma', slot_index=1)
    evidence['lineup_players'][1]['slot_index'] = 2
    evidence['lineup_players'].append(extra)
    entry = report(evidence)['entries'][0]
    assert entry['lineup_match_basis'] == 'canonical_lineup_signature'
    assert entry['submission_evidence']['saved_lineup_matches'][0]['exact_slot_equal'] is False


def test_repeated_rosters_remain_distinct_contest_entry_observations():
    evidence = complete_evidence()
    evidence['assignments'] = []
    evidence['export_records'] = [direct_record()]
    evidence['entries'].append(dict(evidence['entries'][0], entry_id='entry-2'))
    evidence['contests'].append(dict(evidence['contests'][0], contest_id='contest-2'))
    evidence['entries'].append(dict(evidence['entries'][0], contest_id='contest-2'))
    evidence['observations'] += [dict(row, contest_id='contest-2') for row in evidence['observations']]
    entries = report(evidence)['entries']
    assert len(entries) == 3
    assert {(e['submission_evidence']['observed']['contest_id'], e['entry_id']) for e in entries} == {
        ('contest-1', 'entry-1'), ('contest-1', 'entry-2'), ('contest-2', 'entry-1')}
    assert all(not e['submission_evidence']['exported'][0]['entry_specific'] for e in entries)


def test_export_without_saved_lineup_keeps_missing_lineage_and_unknown_identity():
    evidence = complete_evidence()
    evidence['assignments'] = []
    evidence['lineup_players'] = []
    evidence['export_records'] = [direct_record()]
    result = report(evidence)
    assert result['entries'][0]['submission_evidence']['exported'][0]['linkage'] == 'canonical_roster'
    assert 'entry:contest-1:entry-1:saved_lineup_lineage' in result['missing_evidence']
    evidence['observations'] = []
    detail = report(evidence)['entries'][0]['submission_evidence']
    assert detail['observed']['canonical_roster'] is None and detail['exported'] == []


def test_sunday_early_score_difference_without_intent_is_not_execution_error():
    evidence = complete_evidence()
    evidence['assignments'] = []
    evidence['entries'][0]['entry_points'] = 165.48
    evidence['lineup_players'][0]['projection'] = 204.28
    evidence['lineup_players'][1]['projection'] = 0
    evidence['export_records'] = [direct_record()]
    result = report(evidence)
    assert result['entries'][0]['projected_points'] == 204.28
    assert result['optimizer_effectiveness']['execution_diagnostics'][0]['status'] == 'intended_entry_unavailable'
    assert not any(d.get('stage') == 'EXECUTION' for r in result['optimizer_effectiveness']['runs'] for d in r['diagnostic'])


def test_loader_projects_export_metadata_without_loading_csv_bytes():
    service = SlateLearningService(engine=MagicMock())
    service._rows = MagicMock(side_effect=lambda connection, sql, params: (
        [{'contest_id': 'contest-1'}] if 'FROM target.dfs_contest c' in sql else []))
    service._load_evidence(MagicMock(), season=2026, week=1, slate='SUNDAY_NIGHT', entry_user='wones0120')
    sql = next(call.args[1] for call in service._rows.call_args_list if "record.kind IN ('export', 'portfolio_export')" in call.args[1])
    assert 'record.recorded_at' in sql and "'{payload,rows}'" in sql
    assert 'content_hex' not in sql and 'csv_content' not in sql
    assert 'run.season=:season' in sql and 'upper(run.slate_id)=:slate' in sql
