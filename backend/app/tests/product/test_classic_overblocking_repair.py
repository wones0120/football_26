from backend.app.tests.product.prepared_optimizer_fixture import prepared_optimizer
from copy import deepcopy
from datetime import timedelta
import hashlib
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pandas as pd
import pytest

from backend.app.product_services import classic_data_readiness as gate
from backend.app.product_services.classic_official_context import parse_club_tables
from backend.app.product_services.classic_salary_provenance import verify_existing_import
from backend.app.product_services.showdown_player_context import CONTEXT_CONTRACT, PlayerContextUnresolved
from backend.app.tests.product.test_classic_data_readiness import (fixture, assess, service_fixture, refresh_result,
    NOW, CUT, OBS, PROJECTION)


def quarantine_fixture():
    rows, evidence = fixture()
    for i in range(6):
        r = deepcopy(rows[0])
        pid = str(uuid4())
        sid = 1000 + i
        r.update(player_id=pid, name=f'Unresolved backup {i}', position='QB', salary_source_row_id=str(sid),
            dk_player_id=str(sid), canonical_role='expected_backup', role_source_position='QB',
            availability_state='UNKNOWN', availability_status=None, availability_source=None,
            availability_source_ids=[], availability_observed_at=None, canonical_context_reason_codes=['player_status_missing'],
            is_starting_qb=False, projection=None, p90=None, ownership=None, ownership_run_id=None,
            projection_inputs_complete=False, feature_inputs_complete=False)
        s = deepcopy(evidence['source_manifest']['salaries'][0])
        s.update(curated_salary_id=sid, player_master_id=pid, player_name=r['name'], position='QB', source_player_key=str(sid))
        rows.append(r)
        evidence['source_manifest']['salaries'].append(s)
    return rows, evidence


def test_six_objectively_nonmaterial_unknowns_do_not_block_certified_pool():
    rows, evidence = quarantine_fixture()
    ready = assess(rows, evidence)
    assert ready['status'] == 'READY', ready['reason_codes']
    assert ready['projection_coverage'] == dict(population='certified_generation_pool', required_players=72, complete_players=72)
    assert ready['ownership_coverage'] == dict(population='certified_generation_pool', required_players=72, complete_players=72)
    assert ready['pool_populations']['native_salary_rows'] == 78
    assert ready['pool_populations']['certified_generation_eligible'] == 72
    assert ready['pool_populations']['quarantined_unresolved_evidence'] == 6
    assert all(p['disposition'] == 'quarantined_unresolved_evidence' and p['availability'] == 'unknown'
        and p['unresolved_evidence'] and p['materiality_evidence']['role_source_ids'] for p in ready['players'][-6:])
    frozen = gate.freeze_evidence(rows, ready, optimizer_run_id='new-run', evidence=evidence)
    assert len(frozen['audited_salary_pool']) == 78 and len(frozen['player_pool']) == 72
    assert not {r['player_id'] for r in rows[-6:]} & {r['player_id'] for r in frozen['player_pool']}


@pytest.mark.parametrize('changes', [
    dict(position='WR', canonical_role='expected_backup'),
    dict(canonical_role='expected_starter'),
    dict(canonical_role=None, role_source=None),
    dict(role_source_ids=[]),
    dict(role_observed_at=(CUT-timedelta(days=2)).isoformat()),
    dict(role_observed_at=(CUT+timedelta(seconds=1)).isoformat()),
    dict(role_uncertain=True),
    dict(canonical_context_reason_codes=['player_role_conflict']),
    dict(expected_qb_package=True),
    dict(is_starting_qb=True),
    dict(identity_resolved=False),
])
def test_material_or_unknown_materiality_still_blocks(changes):
    rows, evidence = quarantine_fixture()
    rows[-1].update(changes)
    evidence['source_manifest']['salaries'][-1]['position'] = rows[-1]['position']
    blocked = assess(rows, evidence)
    assert blocked['status'] == 'NOT_READY'
    assert blocked['players'][-1]['disposition'] in {'unresolved','invalid_canonical_identity'}
    assert rows[-1]['player_id'] not in blocked['generation_eligible_player_ids']


def test_quarantine_is_recomputed_and_new_evidence_restores_eligibility():
    rows, evidence = quarantine_fixture()
    pid = rows[-1]['player_id']
    assert assess(rows, evidence)['players'][-1]['disposition'] == 'quarantined_unresolved_evidence'
    rows[-1].update(canonical_role='expected_starter', is_starting_qb=True, availability_state='AVAILABLE',
        availability_status='ACT', availability_source='official_roster', availability_source_ids=['new-source'],
        availability_observed_at=OBS.isoformat(), canonical_context_reason_codes=[], projection=20., p90=30.,
        ownership=10., ownership_run_id='new-ownership', projection_inputs_complete=True, feature_inputs_complete=True)
    result = assess(rows, evidence)
    assert result['status'] == 'READY', result['reason_codes']
    assert result['players'][-1]['disposition'] == 'generation_eligible'
    assert pid in result['generation_eligible_player_ids']


def test_unverified_starting_qb_is_not_in_the_certified_denominator():
    rows, evidence = fixture()
    qb = next(r for r in rows if r['position'] == 'QB')
    qb['is_starting_qb'] = False
    result = assess(rows, evidence)
    assert result['status'] == 'NOT_READY'
    assert qb['player_id'] not in result['generation_eligible_player_ids']
    assert result['projection_coverage']['required_players'] == len(rows) - 1
    assert 'starting_qb_unverified' in result['reason_codes']


def test_five_entry_solve_excludes_quarantines_and_preserves_strategy_and_preferences():
    rows, evidence = quarantine_fixture()
    service = service_fixture(rows)
    options = dict(num_lineups=5,max_exposure=.8,enforce_single_te=False,max_lineup_overlap=5,
        max_players_per_team=4,max_players_per_game=5,max_lineups_per_primary_game=3,exclude_opponent_teams=['DEN'],
        exclude_questionable=False,availability_overrides=[],long_shot_mode=False,avoid_dst_opponents=True)
    with prepared_optimizer(service, return_value=refresh_result()), patch.object(gate,'read_evidence',return_value=evidence):
        job = service.run_job(season=NOW.year,week=5,slate='SUNDAY_MAIN',strategy='classic_large_gpp_v1',
            contest_format='classic',objective='gpp',params=deepcopy(options))
    assert len(job.results) == 5
    excluded = {r['player_id'] for r in rows[-6:]}
    assert not excluded & {p['player_id'] for lineup in job.results for p in lineup}
    assert {k:job.params[k] for k in options} == options
    effective = job.params['effective_strategy_contract']['effective']
    assert effective['resolved_config']['objective_weights'] == dict(projection=.35,ceiling=.45,leverage=.05,correlation=.15)
    assert job.params['data_readiness']['solver_called'] is True


@pytest.mark.parametrize('name', ['Ashton Jeanty','Tee Higgins','Justin Jefferson'])
def test_questionable_players_require_usage_evidence_and_are_not_auto_excluded(name):
    rows, evidence = fixture()
    rows[1].update(name=name,availability_status='Q')
    assert assess(rows,evidence)['players'][1]['disposition'] == 'unresolved'
    rows[1].update(practice_participation='LIMITED', practice_observed_at=OBS.isoformat(),
        expected_workload_status='LIMITED', expected_workload_observed_at=OBS.isoformat())
    result = assess(rows,evidence)
    assert result['status'] == 'READY',result['reason_codes']
    assert result['players'][1]['availability'] == 'questionable_elevated'
    assert rows[1]['player_id'] in result['generation_eligible_player_ids']


def salary_proof(tmp_path):
    csv = 'Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame,Status\nWR,Receiver (1),Receiver,1,WR/FLEX,5000,A@B 10/11/2026 01:00PM ET,A,10,\n'
    path = tmp_path/'original.csv'
    path.write_text(csv)
    raw = dict(Position='WR', **{'Name + ID':'Receiver (1)','Name':'Receiver','ID':1,'Roster Position':'WR/FLEX',
        'Salary':5000,'Game Info':'A@B 10/11/2026 01:00PM ET','TeamAbbrev':'A','AvgPointsPerGame':10.,'Status':None})
    ingest = dict(ingest_run_id='existing',source_path=str(path),source_checksum=hashlib.sha256(path.read_bytes()).hexdigest(),
        status='completed',started_at=OBS.isoformat(),completed_at=CUT.isoformat(),rows_raw=1,rows_curated=1)
    salaries = [dict(ingest_run_id='existing',player_name='Receiver',source_player_key='1',position='WR',
        roster_position='WR',salary=5000,game_info=raw['Game Info'],team='A',player_status=None)]
    return ingest,[dict(raw_row_json=raw)],salaries


def test_original_salary_lineage_validated_without_reimport_or_renewing_clocks(tmp_path):
    ingest,raw,salaries = salary_proof(tmp_path)
    proof = verify_existing_import(ingest,raw,salaries,cutoff=CUT)
    assert proof['verified'] and proof['reimported'] is False
    assert proof['imported_at'] == OBS.isoformat() and proof['completed_at'] == CUT.isoformat()
    assert proof['provider_observation_at'] is None


@pytest.mark.parametrize('change', ['checksum','raw','curated','clock','count'])
def test_unverifiable_original_salary_lineage_remains_blocking(tmp_path,change):
    ingest,raw,salaries = salary_proof(tmp_path)
    if change == 'checksum': ingest['source_checksum'] = 'bad'
    if change == 'raw': raw[0]['raw_row_json']['Salary'] = 6000
    if change == 'curated': salaries[0]['team'] = 'C'
    if change == 'clock': ingest['completed_at'] = (CUT+timedelta(seconds=1)).isoformat()
    if change == 'count': ingest['rows_raw'] = 2
    proof = verify_existing_import(ingest,raw,salaries,cutoff=CUT)
    assert not proof['verified'] and proof['reason_codes']
    rows,evidence = fixture()
    evidence['salary_provenance'] = {'existing':proof}
    assert assess(rows,evidence)['required_sources']['salary_pool']['status'] == 'NOT_READY'


def test_valid_legacy_import_does_not_need_a_new_snapshot_but_missing_draft_group_blocks():
    rows,evidence = fixture()
    for s in evidence['source_manifest']['salaries']:
        s.update(snapshot_id=None,source_observed_at=None,captured_at=None)
    evidence['salary_provenance'] = {'salary-ingest':dict(verified=True,source_checksum='salary-checksum',
        imported_at=OBS.isoformat(),completed_at=CUT.isoformat(),reason_codes=[])}
    assert assess(rows,evidence)['status'] == 'READY'
    for s in evidence['source_manifest']['salaries']: s['metadata_json'] = {}
    reasons = assess(rows,evidence)['reason_codes']
    assert 'salary_native_draft_group_missing' in reasons
    assert 'salary_native_source_unverified' not in reasons and 'salary_pool_timestamp_missing' not in reasons


def test_official_roster_parser_requires_explicit_section_and_native_profile():
    html = '<h4>Practice Squad</h4><table><tr><th>Player</th><th>Pos</th></tr><tr><td><a href="/team/players-roster/player/">Player</a><a href="/team/players-roster/player/"></a></td><td>WR</td></tr></table>'
    rows = parse_club_tables(html,team='ARI',uri='https://www.azcardinals.com/team/players-roster/',kind='roster')
    assert rows[0]['status'] == 'PS' and rows[0]['position'] == 'WR'
    with pytest.raises(ValueError):
        parse_club_tables(html.replace('Practice Squad','Unknown list'),team='ARI',uri='https://www.azcardinals.com',kind='roster')


def test_failed_live_refresh_cannot_select_an_old_active_projection():
    from backend.app.product_services.optimizer import OptimizerService
    rows,evidence=fixture()
    service=service_fixture(rows)
    refreshed=dict(projection_run_id=None,data_cutoff_at=CUT,ownership_run_id=None,
        report={'projection':dict(status='blocked'),'ownership':dict(status='blocked')})
    evidence['projection_lineage']=None
    with prepared_optimizer(service, return_value=refreshed), patch.object(gate,'read_evidence',return_value=evidence):
        with pytest.raises(gate.ClassicDataNotReady):
            service.run_job(season=NOW.year,week=5,slate='SUNDAY_MAIN',strategy='classic_large_gpp_v1',contest_format='classic',objective='gpp',params={})
    service._resolve_run_lineage.assert_not_called()
    assert service._load_player_pool.call_args.kwargs['require_explicit_runs'] is True
    failed=service._persist_optimizer_run.call_args.args[0]
    assert failed.projection_run_id is None
    assert failed.params['data_readiness']['projection_coverage']['complete_players'] == 0
    assert failed.params['data_readiness']['ownership_coverage']['complete_players'] == 0
    service._solve_lineup.assert_not_called()


def test_live_loader_preserves_missing_predictions_and_uses_canonical_identity():
    from backend.app.product_services.optimizer import OptimizerService
    service = OptimizerService.__new__(OptimizerService)
    service.engine = MagicMock()
    inspector = MagicMock()
    inspector.has_table.return_value = True
    inspector.get_columns.return_value = []
    native = pd.DataFrame([dict(player_id='canonical-id', name='Known practice-squad player',
        salary=3000, projection=None, predicted_p50=None, predicted_p10=None, predicted_p90=None,
        p90=None, position='WR', player_team='SEA', opponent_team='SF', data_cutoff_at=None)])
    with patch('backend.app.product_services.optimizer.inspect',return_value=inspector), patch(
            'backend.app.product_services.optimizer.pd.read_sql',return_value=native) as read:
        result = service._load_target_player_pool(2026,5,'SUNDAY_MAIN',evidence_cutoff_at=CUT,require_explicit_runs=True)
    assert pd.isna(result.iloc[0]['projection']) and pd.isna(result.iloc[0]['p90'])
    sql = str(read.call_args.args[0])
    assert 'canonical_player.player_master_id IS NOT NULL' in sql
    assert 'CAST(:projection_run_id AS TEXT) IS NOT NULL' in sql
    assert 'CAST(:ownership_run_id AS TEXT) IS NOT NULL' in sql
    assert read.call_args.kwargs['params']['allow_saved_input_fallback'] is False


def test_projection_builder_quarantines_before_feature_lookup_without_inventing_status():
    from backend.app.tests.product.test_canonical_projection_inputs import inputs,prepare,CUTOFF
    matrix,salaries = inputs()
    salaries = salaries[salaries.roster_position != 'CPT'].copy()
    backup = salaries.copy()
    backup['player_master_id'] = 'backup'; backup['position'] = 'QB'; backup['curated_salary_id'] += 10
    backup['source_player_key'] = 'backup-native'
    e = dict(canonical_context_contract=CONTEXT_CONTRACT,availability_state='AVAILABLE',availability_status='ACT',
        availability_source='official',availability_source_ids=['roster'],availability_observed_at=CUTOFF.isoformat(),
        canonical_role='expected_starter',role_source='depth',role_source_ids=['depth'],role_observed_at=CUTOFF.isoformat())
    contexts = pd.DataFrame([
        dict(player_master_id='canonical-1',source='canonical',observed_at=CUTOFF,received_at=CUTOFF,injury_status='ACT',evidence_json=e),
        dict(player_master_id='backup',position='QB',source='canonical',observed_at=CUTOFF,received_at=CUTOFF,injury_status='UNKNOWN',
            evidence_json=dict(canonical_context_contract=CONTEXT_CONTRACT,availability_state='UNKNOWN',canonical_role='expected_backup',
                role_source='official_depth',role_source_ids=['depth'],role_observed_at=CUTOFF.isoformat(),role_source_position='QB'))])
    _,target,metadata = prepare(matrix,pd.concat([salaries,backup]),pregame_context=contexts)
    assert target.player_id.tolist() == ['canonical-1']
    assert metadata['canonical_player_pool']['quarantined_unresolved_player_ids'] == ['backup']
    assert metadata['canonical_player_pool']['explicitly_unavailable_player_ids'] == []
    contexts.loc[1,'evidence_json']['canonical_role'] = None
    with pytest.raises(PlayerContextUnresolved):
        prepare(matrix,pd.concat([salaries,backup]),pregame_context=contexts)


@pytest.mark.parametrize('age_hours,expected_ready', [(1, True), (72, False)])
def test_club_supplement_preserves_practice_evidence_without_renewing_it(age_hours, expected_ready):
    from backend.app.product_services.classic_official_context import _retain_risk_evidence
    from backend.app.product_services.pregame_context import risk_evidence_fields
    rows, evidence = fixture()
    practice_at = (CUT - timedelta(hours=age_hours)).isoformat()
    original = {'practice_report': {'practice_status': 'Full Participation in Practice',
                                  'observed_at': practice_at},
                'role_uncertain': True}
    supplemented = {'evidence_json': {'canonical_role': 'expected_backup'}}
    _retain_risk_evidence(supplemented, original)
    fields = risk_evidence_fields(supplemented['evidence_json'], CUT.isoformat())
    rows[1].update(availability_status='Q', **fields)
    result = assess(rows, evidence)
    assert (result['status'] == 'READY') is expected_ready
    assert fields['practice_observed_at'] == practice_at
    assert fields['expected_workload_status'] is None
    assert supplemented['evidence_json']['role_uncertain'] is True
    assert rows[1]['availability_status'] == 'Q'
    supplemented['evidence_json']['practice_report']['practice_status'] = 'DNP'
    assert original['practice_report']['practice_status'] == 'Full Participation in Practice'


def test_club_supplement_does_not_invent_missing_practice_or_accept_future_facts():
    from backend.app.product_services.classic_official_context import _retain_risk_evidence
    from backend.app.product_services.pregame_context import risk_evidence_fields
    context = {'evidence_json': {}}
    _retain_risk_evidence(context, {})
    assert risk_evidence_fields(context['evidence_json'], CUT.isoformat())['practice_participation'] is None
    _retain_risk_evidence(context, {'practice_report': {'practice_status': 'Full Participation in Practice',
        'observed_at': (CUT + timedelta(seconds=1)).isoformat()}})
    with pytest.raises(ValueError, match='later than its context observation'):
        risk_evidence_fields(context['evidence_json'], CUT.isoformat())
