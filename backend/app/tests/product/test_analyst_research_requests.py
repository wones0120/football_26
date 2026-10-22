from copy import deepcopy

import pytest

from backend.app.product_services.analyst_packets import load_packet, packet_digest, validate
from backend.app.product_services.analyst_preparation import prepare_handoff, bind_handoff
from backend.app.product_services.analyst_research_requests import (
    semantic_dependencies, ensure_requests, publish_research, finish_preparation, load_request,
)
from backend.app.tests.product.test_analyst_preparation import inputs


def dependency(rows, result, at='2099-09-01T12:30:00Z'):
    return semantic_dependencies(games=result['source_manifest']['games'], rows=rows,
        checked_at=at, source_manifest=result['source_manifest'])


def assessment(packet, disposition='material'):
    return dict(game_id=packet['games'][0]['game_id'], disposition=disposition,
        mechanism='SYNTHETIC sourced shared passing-volume sensitivity, not a factual forecast upgrade.',
        counterevidence=['Opponent response and protection remain uncertain.'],
        unknowns=['Scenario occurrence probability is unknown.'],
        source_ids=[packet['sources'][0]['source_id']],
        scenario_ids=['passing'] if disposition == 'material' else [])


def authored(tmp_path, disposition='material'):
    packet, rows, request, result = inputs('SHOWDOWN')
    dependencies = dependency(rows, result)
    requests = ensure_requests(dependencies, prior_packet_sha256=packet_digest(packet),
        requested_at='2099-09-01T12:30:00Z', directory=tmp_path)
    packet['decision_at'] = packet['frozen_at'] = '2099-09-01T13:00:00Z'
    publication = publish_research(requests, packet, assessments=[assessment(packet, disposition)],
        producer='synthetic-authored-fixture', completed_at=packet['decision_at'],
        directory=tmp_path, packet_directory=tmp_path/'packets')
    packet = load_packet(publication['packet']['analyst_packet_sha256'], directory=tmp_path/'packets')
    return packet, rows, request, result, dependencies, publication


def test_equivalent_recapture_is_idempotent_but_publication_role_and_fact_changes_are_not(tmp_path):
    packet, rows, _, result = inputs('CLASSIC')
    pid = rows[0]['player_id']
    result['source_manifest']['injuries'] = [dict(player_master_id=pid, status='Q',
        published_at='2099-09-01T10:00:00Z', observed_at='2099-09-01T11:00:00Z',
        captured_at='2099-09-01T11:05:00Z', ingest_run_id='old', source_checksum='whole-slate-file-one')]
    before = dependency(rows, result)
    first = ensure_requests(before, prior_packet_sha256=packet_digest(packet),
        requested_at='2099-09-01T12:30:00Z', directory=tmp_path)
    result['source_manifest']['injuries'][0].update(captured_at='2099-09-01T12:10:00Z',
        observed_at='2099-09-01T12:00:00Z', ingest_run_id='new', source_checksum='whole-slate-file-two')
    after = dependency(rows, result)
    assert before['dependency_sha256'] == after['dependency_sha256']
    assert before['source_provenance_sha256'] != after['source_provenance_sha256']
    repeated = ensure_requests(after, prior_packet_sha256=packet_digest(packet),
        requested_at='2099-09-01T12:45:00Z', directory=tmp_path)
    assert first == repeated  # Including original request clock, never renewed.
    rows[0]['role_active'] = False
    changed = dependency(rows, result)
    assert sum(a['dependency_sha256'] != b['dependency_sha256']
               for a, b in zip(after['games'], changed['games'])) == 1
    rows[0]['role_active'] = None
    result['source_manifest']['injuries'][0]['published_at'] = '2099-09-01T12:00:00Z'
    assert dependency(rows, result)['dependency_sha256'] != after['dependency_sha256']


def test_future_sources_and_role_clocks_rejected_unknown_stays_unknown():
    _, rows, _, result = inputs('SHOWDOWN')
    rows[0]['role_observed_at'] = '2099-09-01T14:00:00Z'
    with pytest.raises(ValueError, match='Future research'):
        dependency(rows, result)
    rows[0]['role_observed_at'] = None
    rows[0]['projected_targets'] = None
    snapshot = dependency(rows, result)
    assert snapshot['games'][0]['semantics']['actors'][0]['facts']['projected_targets'] is None
    result['source_manifest']['injuries'] = [dict(player_master_id=rows[0]['player_id'],
        evidence_json=dict(published_at='2099-09-01T14:00:00Z'))]
    with pytest.raises(ValueError, match='Future research'):
        dependency(rows, result)


def test_no_raw_name_join_duplicate_or_wrong_game_identity():
    _, rows, _, result = inputs('SHOWDOWN')
    bad = deepcopy(rows); bad[0]['player_id'] = bad[0].get('name', 'display-name')
    with pytest.raises(ValueError, match='canonical player UUID'):
        dependency(bad, result)
    with pytest.raises(ValueError, match='Duplicate canonical'):
        dependency(rows + [rows[0]], result)
    rows[0]['game_id'] = 'wrong-game'
    with pytest.raises(ValueError, match='game identity'):
        dependency(rows, result)


def test_neutral_packet_stays_reference_only_and_requests_are_visible(tmp_path):
    packet, rows, request, result = inputs('SHOWDOWN')
    for scenario in packet['scenario_assumptions']['scenarios']:
        for assumption in scenario['assumptions']:
            assumption['factor'] = 1
    report = prepare_handoff(request=request, result=result, rows=rows,
        checked_at='2099-09-01T14:00:00Z', packets={packet_digest(packet): packet}, directory=tmp_path)
    assert report['research_coverage']['status'] == 'reference_only'
    assert report['research_coverage']['producer_executed'] is False
    assert report['research_requests'][0]['status'] == 'refresh_pending'


def test_authored_publication_closes_only_after_fresh_exact_prepare_and_propagates_saved_binding(tmp_path):
    packet, rows, request, result, dependencies, publication = authored(tmp_path)
    assert publication['status'] == 'published_prepare_pending'
    report = prepare_handoff(request=request, result=result, rows=rows,
        checked_at='2099-09-01T14:00:00Z', packets={packet_digest(packet): packet},
        directory=tmp_path/'packets', research_directory=tmp_path)
    assert report['research_coverage']['status'] == 'mechanisms_current'
    assert report['research_requests'] == []
    closure = finish_preparation(publication, report, dependencies, directory=tmp_path)
    assert closure['status'] == 'producer_closed'
    reopened = prepare_handoff(request=request, result=result, rows=rows,
        checked_at='2099-09-01T14:05:00Z', packets={packet_digest(packet): packet},
        directory=tmp_path/'packets', research_directory=tmp_path)
    assert reopened['research_coverage']['producer_loop_closed'] is True
    assert reopened['research_coverage']['closure_receipt'] == closure
    payload = dict(objective='gpp', params={})
    bind_handoff(payload, dict(analyst_handoff=report))
    assert payload['params']['analyst_handoff_applied']['research_coverage'] == report['research_coverage']
    wrong = deepcopy(dependencies); wrong['dependency_sha256'] = '0'*64
    with pytest.raises(ValueError, match='different research dependency'):
        finish_preparation(publication, report, wrong, directory=tmp_path)
    wrong_report = deepcopy(report); wrong_report['source_packet_sha256'] = '0'*64
    with pytest.raises(ValueError, match='did not bind'):
        finish_preparation(publication, wrong_report, dependencies, directory=tmp_path)


def test_current_fact_change_requests_only_affected_game_and_preserves_original_packet(tmp_path):
    packet, rows, request, result, _, _ = authored(tmp_path)
    before = deepcopy(packet)
    rows[0]['official_availability_status'] = 'OUT'
    report = prepare_handoff(request=request, result=result, rows=rows,
        checked_at='2099-09-01T14:00:00Z', packets={packet_digest(packet): packet}, directory=tmp_path/'packets')
    assert report['research_coverage']['status'] == 'refresh_pending'
    assert len(report['research_requests']) == 1
    assert packet == before
    assert not any(c.get('kind') == 'invented_replacement' for c in report['changes'])


def test_explicit_no_change_requires_author_sources_and_is_not_a_material_forecast(tmp_path):
    packet, rows, request, result, _, _ = authored(tmp_path, disposition='no_change')
    report = prepare_handoff(request=request, result=result, rows=rows,
        checked_at='2099-09-01T14:00:00Z', packets={packet_digest(packet): packet}, directory=tmp_path/'packets')
    assert report['research_coverage']['status'] == 'mechanisms_current'
    assert report['research_coverage']['games'][0]['authored_assessment']['disposition'] == 'no_change'
    broken = deepcopy(packet); broken['research_producer']['games'][0]['source_ids'] = []
    assert any('verified sources' in e for e in validate(broken))


def test_forged_material_neutral_zero_elasticity_and_future_completion_rejected(tmp_path):
    packet, _, _, _, _, _ = authored(tmp_path)
    for scenario in packet['scenario_assumptions']['scenarios']:
        for assumption in scenario['assumptions']:
            assumption['elasticity'] = 0
    assert any('nonneutral typed scenario' in e for e in validate(packet))
    packet['research_producer']['completed_at'] = '2099-09-01T14:00:00Z'
    assert any('completion after packet decision' in e for e in validate(packet))


def test_research_completion_cannot_precede_cited_source_availability(tmp_path):
    packet, _, _, _, _, _ = authored(tmp_path)
    packet['decision_at'] = packet['frozen_at'] = '2099-09-01T14:00:00Z'
    packet['sources'][0]['available_at'] = '2099-09-01T13:30:00Z'
    assert any('before cited source evidence' in e for e in validate(packet))


def test_real_designation_and_starter_evidence_recapture_preserves_original_provenance():
    from backend.app.product_services.factual_designation import resolve_designation, FINAL_REPORT, NO_DESIGNATION
    _, rows, _, result = inputs('SHOWDOWN')
    row = rows[0]; gid = result['source_manifest']['games'][0]
    fact = dict(player_id=row['player_id'], team=row['player_team'], position=row['position'],
        kind='game_status', status=NO_DESIGNATION, source='nfl_official_final_report',
        source_ids=['capture-one'], source_uri='https://www.nfl.com/final-report',
        report_contract=FINAL_REPORT, report_phase='final', scope_verified=True,
        published_at='2099-09-01T10:00:00Z', observed_at='2099-09-01T11:00:00Z',
        received_at='2099-09-01T11:01:00Z', kickoff_at=gid['kickoff_at'])
    def resolve(at):
        return resolve_designation([fact], cutoff=at, player_id=row['player_id'],
            team=row['player_team'], position=row['position'])
    row['designation_resolution'] = resolve('2099-09-01T12:00:00Z')
    row['canonical_role'] = 'expected_starter'; row['role_availability'] = 'rostered'
    row['role_starter_evidence'] = dict(player_id=row['player_id'], team=row['player_team'],
        position=row['position'], role='expected_starter', observed_at='2099-09-01T11:00:00Z',
        received_at='2099-09-01T11:01:00Z', source_ids=['role-capture-one'], source_uri='synthetic:depth')
    first = dependency(rows, result)
    fact.update(observed_at='2099-09-01T12:00:00Z', received_at='2099-09-01T12:01:00Z', source_ids=['capture-two'])
    row['designation_resolution'] = resolve('2099-09-01T12:30:00Z')
    row['role_starter_evidence'].update(observed_at='2099-09-01T12:00:00Z',
        received_at='2099-09-01T12:01:00Z', source_ids=['role-capture-two'])
    second = dependency(rows, result)
    assert first['dependency_sha256'] == second['dependency_sha256']
    assert first['games'][0]['original_actor_provenance'] != second['games'][0]['original_actor_provenance']
    fact['published_at'] = '2099-09-01T11:30:00Z'
    row['designation_resolution'] = resolve('2099-09-01T12:30:00Z')
    assert dependency(rows, result)['dependency_sha256'] != second['dependency_sha256']


def test_frozen_count_receipt_recapture_is_stable_but_count_and_gap_facts_are_material():
    _, rows, _, result = inputs('SHOWDOWN'); row = rows[0]
    counts = dict(version='offensive_count_forecast_v1', players=[dict(
        player_master_id=row['player_id'], team=row['player_team'], position=row['position'],
        version='offensive_count_forecast_v1', conditional_on='active and stable same-team role',
        counts=dict(pass_attempts=30, rush_attempts=4, targets=None), reasons=[],
        raw_history=dict(pass_attempts=dict(values=[30, 28, 32], periods=[209801, 209802, 209803])),
        current_role_evidence=dict(role='expected_starter', source_uri='synthetic:depth',
            observed_at='2099-09-01T11:00:00Z', received_at='2099-09-01T11:01:00Z', source_ids=['role-one']),
        verified_inactive_gaps=[dict(kind='official_gamebook_not_active_v1', period=209804,
            player_master_id=row['player_id'], team=row['player_team'], source_uri='synthetic:gamebook',
            source_sha256='same-gamebook-bytes', source_ids=['old'], derived_snapshot_id='derived-one',
            observed_at='2099-09-01T11:00:00Z', received_at='2099-09-01T11:01:00Z')], source_ids=['weekly-one'])])
    def snapshot():
        return semantic_dependencies(games=result['source_manifest']['games'], rows=rows,
            checked_at='2099-09-01T12:30:00Z', source_manifest=result['source_manifest'], workload_receipt=counts)
    before = snapshot(); actor = counts['players'][0]
    actor['current_role_evidence'].update(observed_at='2099-09-01T12:00:00Z',
        received_at='2099-09-01T12:01:00Z', source_ids=['role-two'])
    actor['verified_inactive_gaps'][0].update(observed_at='2099-09-01T12:00:00Z',
        received_at='2099-09-01T12:01:00Z', source_ids=['new'], derived_snapshot_id='derived-two')
    actor['source_ids'] = ['weekly-two']
    after = snapshot()
    assert before['dependency_sha256'] == after['dependency_sha256']
    assert before['games'][0]['original_count_provenance'] != after['games'][0]['original_count_provenance']
    actor['counts']['pass_attempts'] = 31
    assert snapshot()['dependency_sha256'] != after['dependency_sha256']
    actor['counts']['pass_attempts'] = 30; actor['verified_inactive_gaps'][0]['period'] = 209805
    assert snapshot()['dependency_sha256'] != after['dependency_sha256']


def test_canonical_composed_availability_recapture_and_duplicate_fact_lineage_are_stable():
    from backend.app.product_services.showdown_player_context import compose_player_contexts
    from datetime import datetime, timezone
    _, rows, _, result = inputs('SHOWDOWN'); row = rows[0]
    salary = dict(player_id=row['player_id'], team=row['player_team'], position=row['position'])
    facts = [dict(player_id=row['player_id'], team=row['player_team'], position=row['position'],
        kind=kind, source='synthetic_primary', status='ACT', role='expected_starter',
        source_uri='synthetic:primary', source_ids=['capture-one'],
        observed_at='2099-09-01T11:00:00Z', received_at='2099-09-01T11:01:00Z')
        for kind in ('roster_status', 'role')]
    at = datetime(2099, 9, 1, 12, tzinfo=timezone.utc)
    result['source_manifest']['availability'] = compose_player_contexts([salary], facts, cutoff=at, max_age_hours=24)
    first = dependency(rows, result)
    captured = deepcopy(facts)
    for fact in captured:
        fact.update(observed_at='2099-09-01T12:00:00Z', received_at='2099-09-01T12:01:00Z', source_ids=['capture-two'])
    result['source_manifest']['availability'] = compose_player_contexts([salary], facts+captured,
        cutoff=datetime(2099, 9, 1, 12, 15, tzinfo=timezone.utc), max_age_hours=24)
    second = dependency(rows, result)
    assert first['dependency_sha256'] == second['dependency_sha256']
    assert first['source_provenance_sha256'] != second['source_provenance_sha256']
    captured[1]['role'] = 'expected_backup'
    result['source_manifest']['availability'] = compose_player_contexts([salary], facts+captured,
        cutoff=datetime(2099, 9, 1, 12, 15, tzinfo=timezone.utc), max_age_hours=24)
    assert dependency(rows, result)['dependency_sha256'] != second['dependency_sha256']
    evidence = result['source_manifest']['availability'][0]['evidence_json']
    evidence['practice_report'] = dict(practice_status='LIMITED', observed_at='2099-09-01T11:00:00Z')
    practice = dependency(rows, result)
    evidence['practice_report']['observed_at'] = '2099-09-01T12:00:00Z'
    assert dependency(rows, result)['dependency_sha256'] != practice['dependency_sha256']


def test_actual_native_slate_designation_recapture_is_stable_but_status_and_identity_are_not():
    _, rows, _, result = inputs('SHOWDOWN'); row = rows[0]
    fact = dict(player_id=row['player_id'], team=row['player_team'], position=row['position'],
        kind='game_status', status='OUT', source='draftkings_current_slate_status',
        observation_basis='current_native_slate_designation', identity_match='native_draftable_id',
        native_draft_group=154960, native_id='44533083',
        source_uri='https://api.draftkings.com/draftgroups/v1/draftgroups/154960/draftables',
        observed_at='2099-09-01T11:00:00Z', received_at='2099-09-01T11:01:00Z',
        source_ids=['native-capture-one', 'lobby-one', '44533083'])
    resolution = dict(status='resolved', effective_designation='OUT',
        chosen_fact=fact, source_facts=[fact], evaluated_at='2099-09-01T12:00:00Z')
    row['designation_resolution'] = resolution
    result['source_manifest']['availability'] = [dict(player_master_id=row['player_id'],
        evidence_json=dict(canonical_context_contract='canonical_showdown_player_context_v1',
            designation_resolution=resolution, source_facts=[fact]))]
    before = dependency(rows, result)
    fact.update(observed_at='2099-09-01T12:00:00Z', received_at='2099-09-01T12:01:00Z',
        source_ids=['native-capture-two', 'lobby-two', '44533083'])
    resolution['evaluated_at'] = '2099-09-01T12:15:00Z'
    after = dependency(rows, result)
    assert before['dependency_sha256'] == after['dependency_sha256']
    assert before['games'][0]['original_actor_provenance'] != after['games'][0]['original_actor_provenance']
    fact['status'] = 'QUESTIONABLE'
    assert dependency(rows, result)['dependency_sha256'] != after['dependency_sha256']
    fact['status'] = 'OUT'; fact['native_id'] = 'different-native-id'
    assert dependency(rows, result)['dependency_sha256'] != after['dependency_sha256']
    fact['native_id'] = '44533083'; fact['native_draft_group'] = 154961
    assert dependency(rows, result)['dependency_sha256'] != after['dependency_sha256']


def test_public_native_game_info_binds_canonical_schedule_and_conflicts_fail():
    _, rows, _, result = inputs('SHOWDOWN')
    for row in rows:
        row['game_id'] = 'BUF@NYJ 09/02/2099 08:00AM ET'
    result['source_manifest']['games'][0]['game_id'] = 'canonical-schedule-game'
    report = dependency(rows, result)
    assert report['games'][0]['game_id'] == 'canonical-schedule-game'
    assert report['games'][0]['original_actor_provenance'][0]['native_game_id'].startswith('BUF@NYJ')
    rows[0]['canonical_game_id'] = 'conflicting-canonical-id'
    with pytest.raises(ValueError, match='game identity'):
        dependency(rows, result)
    del rows[0]['canonical_game_id']
    rows[0]['game_id'] = 'BUF@NYJ 09/03/2099 08:00AM ET'
    with pytest.raises(ValueError, match='Native game date'):
        dependency(rows, result)


def test_explicit_wrong_source_scope_or_future_modification_rejected():
    _, rows, _, result = inputs('SHOWDOWN')
    result['source_manifest']['injuries'] = [dict(player_master_id=rows[0]['player_id'], game_id='wrong-game')]
    with pytest.raises(ValueError, match='source explicitly conflicts'):
        dependency(rows, result)
    result['source_manifest']['injuries'] = [dict(player_master_id=rows[0]['player_id'],
        evidence_json=dict(modified_at='2099-09-01T14:00:00Z'))]
    with pytest.raises(ValueError, match='Future research'):
        dependency(rows, result)


@pytest.mark.parametrize('key,value', [
    ('captured_at', '2099-09-01T14:00:00Z'),
    ('imported_at', '2099-09-01 14:00:00'),
])
def test_future_source_capture_and_internal_utc_naive_receipt_are_rejected(key, value):
    _, rows, _, result = inputs('SHOWDOWN')
    result['source_manifest']['injuries'] = [dict(player_master_id=rows[0]['player_id'], **{key: value})]
    with pytest.raises(ValueError, match='Future research'):
        dependency(rows, result)
    result['source_manifest']['injuries'][0][key] = '2099-09-01 11:00:00' if key == 'imported_at' else '2099-09-01T11:00:00Z'
    assert dependency(rows, result)['games']
    rows[0]['role_starter_evidence'] = dict(observed_at='2099-09-01T14:00:00Z')
    result['source_manifest']['injuries'] = []
    with pytest.raises(ValueError, match='Future research'):
        dependency(rows, result)


@pytest.mark.parametrize('forged', ['intent_scope', 'preparation_compatibility'])
def test_original_publication_cannot_use_derivative_flag_to_claim_neutral_is_material(tmp_path, forged):
    packet, _, _, _, _, publication = authored(tmp_path)
    requests = [load_request(key, directory=tmp_path) for key in publication['identity']['request_ids']]
    for scenario in packet['scenario_assumptions']['scenarios']:
        for assumption in scenario['assumptions']:
            assumption['factor'] = 1
    packet[forged] = dict(forged=True)
    with pytest.raises(ValueError, match='nonneutral typed scenario'):
        publish_research(requests, packet, assessments=[assessment(packet)], producer='forged',
            completed_at=packet['decision_at'], directory=tmp_path, packet_directory=tmp_path/'packets')


def test_partial_authored_prepare_cannot_close_producer_loop(tmp_path):
    packet, rows, request, result, dependencies, publication = authored(tmp_path, disposition='partial')
    report = prepare_handoff(request=request, result=result, rows=rows,
        checked_at='2099-09-01T14:00:00Z', packets={packet_digest(packet): packet},
        directory=tmp_path/'packets', research_directory=tmp_path)
    assert report['research_coverage']['status'] == 'mechanisms_partial'
    with pytest.raises(ValueError, match='complete current authored'):
        finish_preparation(publication, report, dependencies, directory=tmp_path)


def test_material_authored_world_reaches_saved_full_roster_report_without_changing_base_means(tmp_path):
    import json
    from datetime import datetime, timezone
    from unittest.mock import patch
    import pandas as pd
    from backend.app.product_services.analyst_scenarios import run_merged
    from backend.app.product_services.optimizer import OptimizerService, _json_safe
    packet, rows, request, result, _, _ = authored(tmp_path)
    report = prepare_handoff(request=request, result=result, rows=rows,
        checked_at='2099-09-01T14:00:00Z', packets={packet_digest(packet): packet},
        directory=tmp_path/'packets', research_directory=tmp_path)
    payload = dict(objective='gpp', params=dict(analyst_portfolio_mode='CONDITIONAL_COVERAGE',
        max_exposure=1, minimum_uniqueness=1))
    bind_handoff(payload, dict(analyst_handoff=report))
    checked = load_packet(report['checked_packet_sha256'], directory=tmp_path/'packets')
    original = deepcopy(rows)
    with patch('backend.app.product_services.analyst_scenarios.datetime') as now:
        now.now.return_value = datetime(2099, 9, 1, 14, tzinfo=timezone.utc)
        lineups, generated = run_merged(OptimizerService.__new__(OptimizerService), pd.DataFrame(rows),
            params=payload['params'], packet=checked, fmt='SHOWDOWN', season=2099, week=1,
            slate='SYNTHETIC', requested=1, solve_kwargs=dict(contest_type='captain', score_col='p90',
                stack_params={'enabled': False}, locked_player_ids=set(), exposure_remaining={},
                include_control_comparison=False))
    assert rows == original
    assert lineups and generated['research_consumption']['games'][0]['material_scenario_ids_consumed'] == ['passing']
    assert generated['baseline_comparison_roster']
    assert any(m['opportunity_ratio'] != 1 for s in generated['scenario_definitions'] for m in s['moments'].values())
    saved = tmp_path/'saved_result.json'
    saved.write_text(json.dumps(_json_safe(dict(results=lineups, report=generated))))
    reopened = json.loads(saved.read_text())
    explanation = reopened['results'][0][0]['analyst_research_explanation']
    assert len(explanation['canonical_roster']) == 6 and explanation['salary'] <= 50000
    assert explanation['research_consumption']['source_packet_sha256'] == packet_digest(packet)
    for player in lineups[0]:
        base = next(r for r in rows if r['player_id'] == player['player_id'])
        assert player['projection'] == pytest.approx(base['projection'] * (1.5 if player.get('roster_position') == 'CPT' else 1))


def test_writer_and_legacy_reader_use_same_compact_logical_bound_without_rewriting(tmp_path, monkeypatch):
    import json
    from backend.app.product_services import analyst_research_requests as service
    value = dict(identity={'request': 'synthetic'}, facts=[dict(status='unknown', count=None)]*80)
    complete = {**value, 'record_sha256': service.digest(value)}
    compact = json.dumps(complete, sort_keys=True, separators=(',', ':')).encode()
    pretty = json.dumps(complete, sort_keys=True, indent=2).encode()
    assert len(pretty) > len(compact)
    monkeypatch.setattr(service, 'MAX_RECORD_BYTES', len(compact))
    monkeypatch.setattr(service, 'MAX_LEGACY_ENVELOPE_BYTES', len(pretty)+1)
    saved = service._write('requests', 'synthetic', value, tmp_path)
    path = tmp_path/'requests/synthetic.json'
    assert path.read_bytes() == compact and service._read(path) == saved
    legacy = tmp_path/'legacy.json'; legacy.write_bytes(pretty)
    assert service._read(legacy) == saved and legacy.read_bytes() == pretty


def test_new_and_legacy_logical_oversize_fail_explicitly_before_fact_loss(tmp_path, monkeypatch):
    import json
    from backend.app.product_services import analyst_research_requests as service
    value = dict(identity={'request': 'synthetic'}, fact='x'*2048)
    complete = {**value, 'record_sha256': service.digest(value)}
    monkeypatch.setattr(service, 'MAX_RECORD_BYTES', 1024)
    monkeypatch.setattr(service, 'MAX_LEGACY_ENVELOPE_BYTES', 8192)
    with pytest.raises(ValueError, match='logical receipt exceeds'):
        service._write('requests', 'oversized', value, tmp_path)
    assert not (tmp_path/'requests/oversized.json').exists()
    legacy = tmp_path/'legacy.json'; legacy.write_text(json.dumps(complete, indent=2))
    original = legacy.read_bytes()
    with pytest.raises(ValueError, match='logical receipt exceeds'):
        service._read(legacy)
    assert legacy.read_bytes() == original


def test_legacy_whitespace_envelope_itself_remains_bounded(tmp_path, monkeypatch):
    from backend.app.product_services import analyst_research_requests as service
    monkeypatch.setattr(service, 'MAX_LEGACY_ENVELOPE_BYTES', 1024)
    path = tmp_path/'oversized_envelope.json'; path.write_text(' '*1025)
    with pytest.raises(ValueError, match='legacy receipt envelope exceeds'):
        service._read(path)


def test_shared_provenance_roundtrip_preserves_every_fact_and_receipt_identity(tmp_path, monkeypatch):
    import json
    from backend.app.product_services import analyst_research_requests as service
    fact = dict(source_id='immutable-source', observations=list(range(600)), status='unknown')
    value = dict(identity={'request': 'shared'}, sources=[fact]*6,
                 literal={'$research_object': 'this is an original fact, not a pointer'})
    monkeypatch.setattr(service, 'MAX_RECORD_BYTES', 6000)
    monkeypatch.setattr(service, 'MAX_LEGACY_ENVELOPE_BYTES', 20000)
    assert len(json.dumps(value).encode()) > service.MAX_RECORD_BYTES
    saved = service._write('requests', 'shared', value, tmp_path)
    path = tmp_path/'requests/shared.json'; original = path.read_bytes()
    assert len(original) <= service.MAX_RECORD_BYTES
    assert json.loads(original)['storage_contract'] == 'research_receipt_shared_objects_v1'
    assert service._read(path) == saved
    restored = service._read(path)
    restored['sources'][0]['status'] = 'changed locally'
    assert restored['sources'][1]['status'] == 'unknown'
    assert saved == {**value, 'record_sha256': service.digest(value)}
    assert service._write('requests', 'shared', value, tmp_path) == saved
    assert path.read_bytes() == original
    broken = json.loads(original)
    first = next(k for k, v in broken['objects'].items() if isinstance(v, dict) and 'status' in v)
    broken['objects'][first]['status'] = 'incorrect'
    path.write_text(json.dumps(broken, separators=(',', ':')))
    with pytest.raises(ValueError, match='checksum mismatch'):
        service._read(path)


def test_shared_receipt_rejects_missing_cycles_and_expansion_bombs():
    from backend.app.product_services.research_receipt_storage import CONTRACT, unpack
    missing = dict(storage_contract=CONTRACT, record={'$research_object': 'missing'}, objects={})
    with pytest.raises(ValueError, match='reference'):
        unpack(missing, expanded_limit=10000)
    cycle = dict(storage_contract=CONTRACT, record={'$research_object': 'cycle'},
                 objects={'cycle': {'$research_object': 'cycle'}})
    with pytest.raises(ValueError, match='reference'):
        unpack(cycle, expanded_limit=10000)
    from backend.app.product_services.analyst_shadow import digest
    fact = {'observations': 'x'*2000}; key = digest(fact)
    bomb = dict(storage_contract=CONTRACT, record=[{'$research_object': key}]*100,
                objects={key: fact})
    with pytest.raises(ValueError, match='expanded receipt exceeds'):
        unpack(bomb, expanded_limit=10000)


def league_capture_fixture():
    """Real producer/composition field shapes; no live ledger or DB required."""
    _,rows,_,result=inputs('SHOWDOWN');pid=rows[0]['player_id']
    fact=dict(kind='game_status',source='nfl_official',source_uri='https://www.nfl.com/injuries/league/2099/reg1',
        player_id=pid,team=rows[0]['team'],position=rows[0]['position'],status='OUT',
        observed_at='2099-09-01T11:00:00Z',source_ids=['old-context','old-row'])
    practice=dict(practice_status='Limited Participation in Practice',observed_at=fact['observed_at'],practice_date='2099-08-31')
    workload=dict(source=fact['source'],source_uri=fact['source_uri'],player_master_id=pid,
        pregame_player_context_id=12,observed_at=fact['observed_at'],injury_status='OUT',
        evidence_json=dict(observation_basis='http_response_clock',official_player_key='/players/native-key',practice_report=deepcopy(practice)))
    rows[0]['designation_resolution']=dict(contract='factual_game_designation_v1',chosen_fact=deepcopy(fact),
        effective_designation='OUT',source_facts=[deepcopy(fact)],superseded_facts=[deepcopy(fact)],conflicts=[])
    result['source_manifest']['availability']=[dict(player_master_id=pid,team=rows[0]['team'],source='canonical',
        evidence_json=dict(canonical_context_contract='canonical_showdown_player_context_v1',
            designation_resolution=deepcopy(rows[0]['designation_resolution']),source_facts=[deepcopy(fact)],
            workload_context=workload,practice_report=deepcopy(practice)))]
    return rows,result


def test_league_http_recapture_whole_composed_dependency_stable_and_provenance_retained():
    rows,result=league_capture_fixture();before=dependency(rows,result)
    fact=deepcopy(rows[0]['designation_resolution']['chosen_fact']);fact.update(observed_at='2099-09-01T12:00:00Z',source_ids=['new-context','new-row'])
    rows[0]['designation_resolution']['source_facts'].append(fact)
    rows[0]['designation_resolution']['superseded_facts'].append(deepcopy(fact))
    rows[0]['designation_resolution']['chosen_fact']=deepcopy(fact)
    e=result['source_manifest']['availability'][0]['evidence_json']
    e['source_facts'].append(deepcopy(fact));e['designation_resolution']=deepcopy(rows[0]['designation_resolution'])
    e['workload_context'].update(pregame_player_context_id=24,observed_at=fact['observed_at'])
    e['workload_context']['evidence_json']['practice_report']['observed_at']=fact['observed_at']
    e['practice_report']['observed_at']=fact['observed_at']
    after=dependency(rows,result)
    assert before['games'][0]['semantics']==after['games'][0]['semantics']
    assert before['dependency_sha256']==after['dependency_sha256']
    assert before['source_provenance_sha256']!=after['source_provenance_sha256']


@pytest.mark.parametrize('change',['status','practice_status','practice_date','published_at','modified_at','native_key'])
def test_league_material_report_changes_still_invalidate(change):
    rows,result=league_capture_fixture();before=dependency(rows,result)
    e=result['source_manifest']['availability'][0]['evidence_json']
    if change=='status':rows[0]['designation_resolution']['chosen_fact']['status']='QUESTIONABLE'
    elif change in {'practice_status','practice_date'}:e['practice_report'][change]='Full Participation in Practice' if change=='practice_status' else '2099-09-01'
    elif change=='native_key':e['workload_context']['evidence_json']['official_player_key']='/players/different-native-key'
    else:rows[0]['designation_resolution']['chosen_fact'][change]='2099-09-01T12:00:00Z'
    assert before['dependency_sha256']!=dependency(rows,result)['dependency_sha256']


def test_unknown_practice_source_clock_and_future_league_capture_are_not_swallowed():
    rows,result=league_capture_fixture();e=result['source_manifest']['availability'][0]['evidence_json']
    e['workload_context']['source']='other_source';before=dependency(rows,result)
    e['practice_report']['observed_at']='2099-09-01T12:00:00Z'
    assert before['dependency_sha256']!=dependency(rows,result)['dependency_sha256']
    rows[0]['designation_resolution']['source_facts'][0]['observed_at']='2099-09-01T14:00:00Z'
    with pytest.raises(ValueError,match='Future research'):dependency(rows,result)
