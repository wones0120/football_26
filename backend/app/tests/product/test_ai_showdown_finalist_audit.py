"""Synthetic post-slate labels test the diagnostic without historical tuning."""
from copy import deepcopy

import pytest

from backend.app.product_services.ai_showdown_finalist_audit import audit_finalist_set, render_audit_markdown
from backend.app.product_services.ai_showdown_packet import digest
from backend.app.product_services.optimizer_effectiveness import candidate_signature, actual_points_by_player


def fixture():
    candidates = []
    for i in range(20):
        players = [{'player_id': 'cap', 'slot': 'CPT'}] + [
            {'player_id': f'p{j}', 'slot': 'FLEX'} for j in range(4)] + [{'player_id': f'u{i}', 'slot': 'FLEX'}]
        candidates.append({'rank': i+1, 'players': players})
    source = {'job_id': 'synthetic-run', 'results': [[{'captain_family_coverage_report': {'ranked_metrics': candidates}}]]}
    ids = [f"synthetic-run:{digest(candidate_signature(c, 'showdown'))[:16]}" for c in candidates]
    packet = {'contract_id': 'ai_showdown_selection_packet_v1', 'finalist_policy_version': 'ai_showdown_finalists_v2',
              'run': {'optimizer_run_id': 'synthetic-run', 'candidate_pool_hash': digest(candidates)},
              'pool_summary': {'requested_entries': 2}, 'finalists': [{'candidate_id': ids[i]} for i in (0, 1, 15)]}
    packet['evidence_hash'] = digest(packet)
    packet['generated_at'] = '2026-10-06T00:00:00+00:00'
    actuals = {'cap': 10, **{f'p{j}': 5 for j in range(4)}, **{f'u{i}': i for i in range(20)}}
    return packet, source, actuals


def test_retrospective_regret_tails_and_decomposition():
    packet, source, actuals = fixture()
    audit = audit_finalist_set(packet, source, actuals, universe_best_actual_score=60,
                              selected_candidate_ids=[r['candidate_id'] for r in packet['finalists'][:2]])
    assert audit['status'] == 'complete'
    assert audit['best_generated_actual_score'] == 54
    assert audit['best_finalist_actual_score'] == 50
    assert audit['finalist_selection_regret'] == 4
    assert audit['eventual_best_generated_candidate_included'] is False
    assert audit['selector_rank_of_best_finalist'] == 16
    assert audit['regret_decomposition'] == {'candidate_generation_regret': 6, 'candidate_generation_reason': None,
                                           'finalist_filtering_regret': 4, 'ai_manual_selection_regret': 14,
                                           'ai_manual_selection_reason': None}
    assert audit['top_tails']['top_1_percent']['generated_count'] == 1
    assert audit['top_tails']['top_10_percent']['generated_count'] == 2
    assert audit['actual_rank_distribution']['values'] == [5, 19, 20]
    assert 'not field percentiles' in render_audit_markdown(audit)


def test_top_tail_cutoff_ties_and_best_included():
    packet, source, actuals = fixture()
    actuals['u15'] = 19
    audit = audit_finalist_set(packet, source, actuals)
    assert audit['top_tails']['top_1_percent']['generated_count'] == 2
    assert audit['top_tails']['top_1_percent']['finalist_count'] == 1
    assert audit['top_tails']['top_1_percent']['retention_rate'] == .5
    assert audit['eventual_best_generated_candidate_included'] is True
    assert audit['all_tied_best_generated_candidates_included'] is False
    assert audit['finalist_selection_regret'] == 0
    assert audit['regret_decomposition']['candidate_generation_regret'] is None
    assert audit['regret_decomposition']['ai_manual_selection_regret'] is None


def test_missing_actuals_are_never_imputed_and_packet_not_mutated():
    packet, source, actuals = fixture()
    before = deepcopy(packet)
    del actuals['u15']
    audit = audit_finalist_set(packet, source, actuals)
    assert packet == before
    assert audit['status'] == 'partial_actual_coverage'
    assert audit['scoreable_generated_count'] == 19
    assert audit['scoreable_finalist_count'] == 2
    assert audit['unscored_candidates'][0]['missing_player_ids'] == ['u15']
    assert audit['unscored_candidates'][0]['actual_score'] is None


@pytest.mark.parametrize('change', ['packet', 'source', 'run', 'actual', 'selection', 'universe'])
def test_audit_rejects_bad_lineage_and_labels(change):
    packet, source, actuals = fixture()
    kwargs = {}
    if change == 'packet': packet['finalists'].pop()
    if change == 'source': source['results'][0][0]['captain_family_coverage_report']['ranked_metrics'][0]['rank'] = 200
    if change == 'run': source['job_id'] = 'wrong-run'
    if change == 'actual': actuals['cap'] = float('nan')
    if change == 'selection': kwargs['selected_candidate_ids'] = ['unknown']
    if change == 'universe': kwargs['universe_best_actual_score'] = 1
    with pytest.raises(ValueError): audit_finalist_set(packet, source, actuals, **kwargs)


def test_conflicting_actual_observations_remain_unresolved():
    observations = [{'player_id': 'a', 'resolution_status': 'resolved', 'actual_points': 15, 'roster_position': 'CPT'},
                    {'player_id': 'a', 'resolution_status': 'resolved', 'actual_points': 10, 'roster_position': 'FLEX'},
                    {'player_id': 'b', 'resolution_status': 'resolved', 'actual_points': 4, 'roster_position': 'FLEX'},
                    {'player_id': 'b', 'resolution_status': 'resolved', 'actual_points': 5, 'roster_position': 'FLEX'}]
    assert actual_points_by_player(observations, 'showdown') == {'a': 10}


def test_contest_field_tails_are_separate_and_require_complete_standings():
    packet, source, actuals = fixture()
    fields = {'complete': {'reported_field_size': 100, 'entry_points': list(range(100))},
              'partial': {'reported_field_size': 100, 'entry_points': [0, 1]}}
    audit = audit_finalist_set(packet, source, actuals, contest_fields=fields)
    assert audit['top_tails']['top_1_percent']['generated_count'] == 1
    assert audit['contest_field_top_tails']['complete']['top_tails']['top_1_percent']['generated_count'] == 0
    assert audit['contest_field_top_tails']['complete']['field_winner_score'] == 99
    assert audit['contest_field_top_tails']['partial']['status'] == 'unavailable'
