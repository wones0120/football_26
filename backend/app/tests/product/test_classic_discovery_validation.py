"""Chronological audit contracts; fixtures never certify missing historical state."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest

from backend.app.product_services.classic_discovery_validation import (
    TARGETS, attach_postgame, chronological_split, forbid_outcomes, freeze_pregame,
    portfolio_match, reconstruction_gate, runtime_summary, source_contribution, verify_old_replay,
)
from backend.app.product_services.classic_prospective import digest_payload
from scripts.audit_classic_discovery_cohort import build_cohort

ROOT = Path(__file__).resolve().parents[4]
INPUT = ROOT / 'artifacts/week4-thesis-frozen-analysis-inputs-8b5c114c.json'


@pytest.fixture
def snapshot():
    return json.loads(INPUT.read_text())['report']['frozen_solver_snapshot']


def gate(snapshot, **overrides):
    defaults = dict(kickoff_at='2026-10-04T13:00:00-04:00',
        run_created_at='2026-09-30T11:06:20-04:00', as_of='2026-10-05T12:00:00+00:00',
        code_hashes=snapshot['payload']['metadata']['code_sha256'] if snapshot else {})
    return reconstruction_gate(snapshot, **{**defaults, **overrides})


def rehash(snapshot):
    snapshot['sha256'] = digest_payload(snapshot['payload'])


def test_historical_replay_time_is_honest_and_original_inputs_prelock(snapshot):
    result = gate(snapshot)
    assert result['qualified'] and result['replayed_as_of'].startswith('2026-10-05')
    assert result['input_sha256'] == snapshot['sha256']


def test_future_week4_is_never_historical_observation(snapshot):
    assert gate(snapshot, as_of='2026-09-30T16:00:00Z')['reason'] == 'future_slate_diagnostic_only'


@pytest.mark.parametrize('created', ['2026-10-04T13:00:00-04:00', '2026-10-04T17:00:01Z'])
def test_original_control_after_lock_rejected(snapshot, created):
    assert gate(snapshot, run_created_at=created)['reason'] == 'original_run_at_or_after_lock'


def test_missing_snapshot_is_not_fixed_by_saved_score_replay():
    assert gate(None)['reason'] == 'complete_frozen_generation_inputs_absent'


@pytest.mark.parametrize('mutation', ['hash', 'ownership', 'role', 'options', 'config', 'config_nested', 'identity', 'future', 'future_source', 'nested_actual', 'code'])
def test_complete_pregame_frame_and_provenance_required(snapshot, mutation):
    p = snapshot['payload']
    if mutation == 'hash':
        snapshot['sha256'] = 'tampered'
    elif mutation == 'ownership':
        p['players'][0].pop('ownership')
    elif mutation == 'role':
        p['players'][0].pop('optimizer_receiving_role_strength')
    elif mutation == 'options':
        p['options'].pop('seed_generation_method')
    elif mutation == 'config':
        p['resolved_config'].pop('objective_weights')
    elif mutation == 'config_nested':
        p['resolved_config']['objective_weights'].pop('projection')
    elif mutation == 'identity':
        p['players'][1]['player_id'] = p['players'][0]['player_id']
    elif mutation == 'future':
        p['source_pool_rows'][0]['injury_observed_at'] = '2026-10-04T18:00:00Z'
    elif mutation == 'future_source':
        p['source_pool_rows'][0]['source'] = {'observed_at': '2026-10-04T18:00:00Z'}
    elif mutation == 'nested_actual':
        p['players'][0]['evidence'] = {'future': [{'actual_points': 55}]}
    elif mutation == 'code':
        p['metadata']['code_sha256']['gpp_optimizer.py'] = 'wrong'
    if mutation != 'hash':
        rehash(snapshot)
    hashes = json.loads(INPUT.read_text())['report']['frozen_solver_snapshot']['payload']['metadata']['code_sha256']
    assert not gate(snapshot, code_hashes=hashes)['qualified']


def _payload():
    return {'input_sha256': 'fixture', 'kickoff_at': '2026-09-20T13:00:00-04:00',
            'old': {'candidates': [], 'portfolio5': [], 'portfolio20': []},
            'full_expanded': {}, 'expanded_targets': {str(t): {} for t in TARGETS}}


def test_persist_both_arms_before_loading_actuals_and_do_not_mutate_pregame(tmp_path):
    path = tmp_path / 'pregame.json'
    payload = _payload()
    before = deepcopy(payload)
    frozen = freeze_pregame(path, payload, frozen_at='2026-09-21T09:00:00Z')
    persisted = path.read_bytes()
    calls = []
    result = attach_postgame(path, lambda: calls.append('read') or {'actual_points': 55},
                             attached_at='2026-09-21T09:01:00Z')
    assert calls == ['read'] and result['pregame_sha256'] == frozen['sha256']
    assert path.read_bytes() == persisted and payload == before
    with pytest.raises(FileExistsError):
        freeze_pregame(path, payload, frozen_at='2026-09-21T09:02:00Z')


@pytest.mark.parametrize('case', ['missing', 'tampered', 'early', 'same_time'])
def test_actuals_loader_never_called_without_verified_prior_freeze(tmp_path, case):
    path = tmp_path / 'pregame.json'
    calls = []
    if case != 'missing':
        freeze_pregame(path, _payload(), frozen_at='2026-09-20T17:01:00Z')
    if case == 'tampered':
        x = json.loads(path.read_text())
        x['payload']['old']['candidates'] = ['changed']
        path.write_text(json.dumps(x))
    time = '2026-09-20T17:02:00Z' if case in {'missing', 'tampered'} else '2026-09-20T17:01:00Z'
    if case == 'early':
        time = '2026-09-20T16:59:00Z'
    with pytest.raises((ValueError, FileNotFoundError)):
        attach_postgame(path, lambda: calls.append('read') or {}, attached_at=time)
    assert calls == []


def test_freeze_refuses_outcomes_and_missing_candidate_target(tmp_path):
    payload = _payload()
    payload['expanded_targets'].pop('500')
    with pytest.raises(ValueError, match='four'):
        freeze_pregame(tmp_path / 'a.json', payload, frozen_at='2026-09-21T00:00:00Z')
    payload = _payload()
    payload['old']['actual_points'] = 44
    with pytest.raises(ValueError, match='Outcome'):
        freeze_pregame(tmp_path / 'b.json', payload, frozen_at='2026-09-21T00:00:00Z')


def test_freeze_normalizes_numeric_solver_diagnostics_before_hashing(tmp_path):
    payload = _payload()
    payload['diagnostics'] = {10: ('ten',), 2: ('two',), 1: ('one',)}
    before = deepcopy(payload)
    path = tmp_path / 'numeric.json'
    frozen = freeze_pregame(path, payload, frozen_at='2026-09-21T09:00:00Z')
    persisted = json.loads(path.read_text())
    assert persisted['sha256'] == digest_payload({k: v for k, v in persisted.items() if k != 'sha256'})
    assert persisted['payload']['diagnostics']['10'] == ['ten']
    assert payload == before
    assert attach_postgame(path, lambda: {}, attached_at='2026-09-21T09:01:00Z')['pregame_sha256'] == frozen['sha256']


def test_numeric_diagnostics_do_not_hide_outcomes(tmp_path):
    payload = _payload()
    payload['diagnostics'] = {1: {'actual_points': 12}}
    with pytest.raises(ValueError, match='Outcome'):
        freeze_pregame(tmp_path / 'leak.json', payload, frozen_at='2026-09-21T09:00:00Z')
    assert not (tmp_path / 'leak.json').exists()


def test_freeze_rejects_key_collisions_in_persisted_json(tmp_path):
    payload = _payload()
    payload['diagnostics'] = {1: 'a', '1': 'b'}
    with pytest.raises(ValueError, match='Duplicate serialized JSON key'):
        freeze_pregame(tmp_path / 'collision.json', payload, frozen_at='2026-09-21T09:00:00Z')


def test_holdout_is_independent_chronological_and_small_n_stays_unavailable():
    assert chronological_split([])['status'] == 'insufficient_independent_slates'
    rows = [{'slate_key': str(i), 'qualified': True, 'kickoff_at': f'2026-09-{i+1:02d}T13:00:00-04:00'} for i in range(6)]
    result = chronological_split(list(reversed(rows)))
    assert [r['slate_key'] for r in result['development']] == ['0', '1', '2', '3']
    assert [r['slate_key'] for r in result['holdout']] == ['4', '5']
    with pytest.raises(ValueError, match='Refreshes'):
        chronological_split(rows + [rows[0]])
    assert chronological_split([{**r, 'qualified': False} for r in rows])['qualified_count'] == 0


def row(i, score=10):
    return {'player_ids': ['q', str(i)], 'objective_score': score,
            'qb': {'player_id': 'q'}, 'game_key': 'A|B', 'family_key': 'q|QB+1|BB0'}


@pytest.mark.parametrize('size', [5, 20])
def test_exact_structural_and_quality_match_do_not_confuse_tied_rosters(size):
    full = [row(i) for i in range(size)]
    exact = [{**r, 'player_ids': list(reversed(r['player_ids']))} for r in reversed(full)]
    assert portfolio_match(exact, full)['exact']
    alternative = [row(i + 100, 10 - .04 / size) for i in range(size)]
    result = portfolio_match(alternative, full)
    assert not result['exact'] and result['structural']
    assert result['quality_equivalent'] == {'0.01': False, '0.05': True, '0.1': True}
    alternative[0]['game_key'] = 'C|D'
    assert not portfolio_match(alternative, full)['structural']
    assert portfolio_match(None, full)['exact'] is None


def test_runtime_reports_missing_measurements_without_zero_fabrication():
    assert runtime_summary([1, 2, 3, None]) == {'measured_count': 3, 'missing_count': 1, 'mean': 2, 'median': 2, 'max': 3}
    assert runtime_summary([None])['median'] is None
    with pytest.raises(ValueError):
        runtime_summary([-1])


def test_old_replay_preserves_membership_order_and_scores():
    saved = [row('a'), row('b')]
    canonical = [{**r, 'player_ids': list(reversed(r['player_ids']))} for r in saved]
    assert verify_old_replay(saved, canonical)['status'] == 'identical'
    with pytest.raises(ValueError, match='order'):
        verify_old_replay(saved, list(reversed(saved)))
    with pytest.raises(ValueError, match='selector'):
        verify_old_replay(saved, [saved[0], row('b', 9.9)])
    with pytest.raises(ValueError, match='nonempty'):
        verify_old_replay([], [])
    with pytest.raises(ValueError, match='finite'):
        verify_old_replay(saved, [saved[0], row('b', float('nan'))])


def test_source_credit_deduplicates_and_retains_failed_solves():
    a, b = row('a'), row('b', 9.79)
    events = [{'status': 'optimal', 'source': 'qb_frontier', **a},
              {'status': 'optimal', 'source': 'player_forced', **a},
              {'status': 'optimal', 'source': 'player_forced', **b},
              {'status': 'infeasible', 'source': 'qb_frontier'}]
    result = source_contribution(events, frontier=10, five=[a], twenty=[a, b])
    assert result['qb_frontier']['solves'] == 2
    assert result['qb_frontier']['unique_candidates'] == result['qb_frontier']['within_020'] == 1
    assert result['player_forced']['solves'] == 2
    assert result['player_forced']['within_020'] == 0
    assert result['player_forced']['selected5'] == 0 and result['player_forced']['selected20'] == 1
    assert sum(r['unique_candidates'] for r in result.values()) == 2
    with_baseline = source_contribution(events, frontier=10, five=[a], twenty=[a, b], baseline=(a,))
    assert with_baseline['qb_frontier']['unique_candidates'] == 0
    assert with_baseline['player_forced']['new_players'] == 1


def test_catalog_excludes_missing_control_future_and_ambiguous_membership():
    catalog = {key: [] for key in ('salaries', 'salary_snapshots', 'projections', 'ownership',
        'schedules', 'actual_availability', 'contest_actual_availability', 'contest_availability', 'runs')}
    catalog['projections'] = [{'season': 2025, 'week': 1, 'slate': 'DEFAULT'},
                              {'season': 2026, 'week': 4, 'slate': 'SUNDAY_MAIN'}]
    catalog['schedules'] = [{'season': 2026, 'week': 4, 'game_id': 'x', 'gameday': '2026-10-04',
        'weekday': 'Sunday', 'gametime': '13:00', 'market_values_present': False}]
    result = build_cohort(catalog, as_of='2026-09-30T12:00:00Z')
    assert result['historical_qualified_count'] == 0
    assert 'Sunday_Main_membership_not_certified' in result['slates'][0]['exclusion_reasons']
    assert 'future_slate_diagnostic_only' in result['slates'][1]['exclusion_reasons']
    catalog['runs'] = [{'season': 2025, 'week': 1, 'slate': 'SUNDAY_MAIN',
        'strategy': 'classic_small_field_gpp', 'status': 'completed', 'snapshot_sha256': 'new'}]
    with pytest.raises(ValueError, match='full replay audit'):
        build_cohort(catalog, as_of='2026-09-30T12:00:00Z')


def test_production_code_still_matches_frozen_week4_hashes(snapshot):
    for name, expected in snapshot['payload']['metadata']['code_sha256'].items():
        assert sha256((ROOT / 'backend/app/product_services' / name).read_bytes()).hexdigest() == expected


def test_current_cohort_exclusion_artifact_is_hash_verified():
    audit = json.loads((ROOT / 'artifacts/classic_discovery_multi_slate/cohort_audit_final.json').read_text())
    assert audit['sha256'] == digest_payload(audit['payload'])
    assert audit['payload']['historical_qualified_count'] == 0
    assert not audit['payload']['actual_score_values_read']
    assert all(not r['qualified'] for r in audit['payload']['slates'])


def test_source_recheck_preserves_recoverable_inputs_without_certifying_generator():
    audit = json.loads((ROOT / 'artifacts/classic_discovery_multi_slate/continuation_reconstruction_audit.json').read_text())
    assert audit['sha256'] == digest_payload(audit['payload'])
    payload = audit['payload']
    assert payload['prelock_run_count'] == 28 and payload['postlock_run_count'] == 2
    assert sum(r['prelock'] for r in payload['completed_week2_week3_runs']) == 28
    assert all(r['solver_snapshot_sha256'] is None and r['generation_sha256'] is None
               for r in payload['completed_week2_week3_runs'])
    for row in payload['pinned_feature_representatives'].values():
        assert row['projection_rows'] == row['feature_rows'] == row['eligible']
        assert row['feature_rows_present_before_decision'] == row['eligible']
    assert not payload['supplementary_source_evidence']['week2_role_snapshot']['matches_representative_control_projection']
    assert not payload['historical_candidate_solves_executed']


def test_recovered_week3_archive_preserves_input_integrity_and_model_equivalence():
    directory = ROOT / 'artifacts/classic_discovery_multi_slate/week3_archived_control_check'
    manifest = json.loads((directory / 'reconstruction_manifest.json').read_text())
    assert manifest['sha256'] == digest_payload({k: v for k, v in manifest.items() if k != 'sha256'})
    for name, expected in manifest['file_sha256'].items():
        assert sha256((directory / name).read_bytes()).hexdigest() == expected
    for name in ('inputs.json', 'candidate_solver_frame.json'):
        forbid_outcomes(json.loads((directory / name).read_text()))
    score = json.loads((directory / 'score_check.json').read_text())
    assert score['matching_scores_1e9'] == 120 and score['max_absolute_selector_difference'] == 0
    assert json.loads((directory / 'config_check.json').read_text())['canonical_config_match']
    archived = json.loads((directory / 'archived_model_check.json').read_text())
    expanded = json.loads((directory / 'current_model_check.json').read_text())
    assert archived['mathematical_model_sha256'] == expanded['mathematical_model_sha256']
    assert archived['variables'] == expanded['variables'] == 2204
    assert archived['constraints'] == expanded['constraints'] == 5507
    # Input/scoring/model evidence alone must not certify original generation.
    assert manifest['generation_check'].startswith('running; qualification pending')


def test_report_ends_with_requested_answers_and_labels_provisional_execution():
    report = (ROOT / 'CLASSIC_EXPANDED_DISCOVERY_MULTI_SLATE_VALIDATION.md').read_text()
    ending = report.split('## 27. Remaining uncertainty', 1)[1]
    questions = (
        'Does expanded discovery generalize?', 'Is incomplete generation a recurring problem?',
        'Is generation or admission the dominant source of competitive misses?',
        'Which discovery sources add the most useful coverage?', 'Which sources are low-value relative to compute?',
        'What admitted candidate target should production use?', 'Does 400 generalize as the best default?',
        'Does expanded discovery materially change thesis conclusions?',
        "Does it materially improve the user's five-entry feasible set?",
        'Does it materially improve the 20-entry thesis portfolio?', 'What do realized results show?',
        'Is expanded discovery ready for production?', 'What exact code/config change should be promoted next?',
    )
    assert [line[4:] for line in ending.splitlines() if line.startswith('### ')] == list(questions)
    assert 'N=0' in report and '**SHADOW LONGER.**' in ending and '**None yet.**' in ending
    assert 'completed provisional historical experiments N=1' in report
    assert 'exact-certified multi-slate validation cannot be completed' in report


def test_completed_provisional_experiment_preserves_failure_and_fixed_portfolios():
    directory = ROOT / 'artifacts/classic_discovery_multi_slate/week3_archived_control_check'
    assessment = json.loads((directory / 'original_replay_assessment.json').read_text())
    assert assessment['identical_rosters'] == 117
    assert assessment['exact_certified'] is False
    frozen = json.loads((directory / 'pregame_comparison.json').read_text())
    assert digest_payload({key: value for key, value in frozen.items() if key != 'sha256'}) == frozen['sha256']
    forbid_outcomes(frozen['payload'])
    payload = frozen['payload']
    raw = {tuple(sorted(row['player_ids'])) for row in payload['full_expanded']['candidates']}
    assert len(raw) == 1589
    for target in TARGETS:
        admitted = payload['expanded_targets'][str(target)]['admitted']
        assert len(admitted) == target
        assert all(tuple(sorted(row['player_ids'])) in raw for row in admitted)
        selected = payload['user_five'][f'target_{target}']['selected']
        assert len(selected) == 5 and len({row['qb']['player_id'] for row in selected}) == 5
        assert all(len(set(left['player_ids']) & set(right['player_ids'])) <= 4
                   for i, left in enumerate(selected) for right in selected[i + 1:])
        assert {tuple(sorted(row['player_ids'])) for row in selected} == {
            tuple(sorted(row['player_ids'])) for row in payload['user_five']['full_expanded']['selected']}


def test_completed_postgame_attachment_follows_immutable_freeze_without_zero_imputation():
    from datetime import datetime
    directory = ROOT / 'artifacts/classic_discovery_multi_slate/week3_archived_control_check'
    frozen = json.loads((directory / 'pregame_comparison.json').read_text())
    attached = json.loads((directory / 'postgame_attachment.json').read_text())
    metrics = json.loads((directory / 'postgame_metrics.json').read_text())
    assert attached['pregame_sha256'] == metrics['pregame_sha256'] == frozen['sha256']
    assert digest_payload(attached['actuals']) == attached['actuals_sha256']
    assert datetime.fromisoformat(attached['attached_at']) > datetime.fromisoformat(frozen['frozen_at'])
    assert metrics['resolved_consistent_actual_players'] == 371
    assert metrics['universes']['full_expanded']['scoreable'] == 1461
    assert metrics['universes']['full_expanded']['missing'] == 128
    assert metrics['portfolios']['full_expanded']['thesis_twenty']['scoreable'] == 18
    assert metrics['portfolios']['full_expanded']['thesis_twenty']['complete'] is False
