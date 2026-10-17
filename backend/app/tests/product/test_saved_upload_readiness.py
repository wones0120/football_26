from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest

from backend.app.product_services.saved_upload_readiness import validate_inputs, require_clearance, CONTRACT
from backend.app.product_services.evaluation_record import digest

NOW = datetime(2026, 10, 15, 15, tzinfo=UTC)
PID = '1838dd60-35e8-4018-b307-39cde90e1f03'


def fixture():
    rows = [dict(player_id=PID, name='Canonical player', roster_position='CPT', dk_captain_id='123',
        salary=15000, position='WR', player_team='SEA', game_id='SEA@DEN 10/15/2026 08:15PM ET',
        canonical_game_id='2026_06_SEA_DEN', projection_run_id='projection', canonical_role='expected_starter',
        salary_source_checksum='sha', salary_source_path='immutable.csv')]
    scope=dict(season=2026,week=6,slate='THURSDAY_NIGHT',contest_format='showdown')
    job=SimpleNamespace(job_id='saved', status='completed', **scope, projection_run_id='projection',results=[rows],
        params=dict(prepared_input_evidence={'prepared_input_job_id':'prep'}, questionable_eligible_player_ids=[PID],
        strategy_runtime={'football_analyst':{'input_snapshot':{'scope':dict(season=2026,week=6,slate_id='THURSDAY_NIGHT',format='SHOWDOWN',game_ids=['2026_06_SEA_DEN']), 'players':[{'player_master_id':PID}]}}}))
    evidence=dict(scope=scope,official=dict(observed_at=NOW.isoformat(),received_at=NOW.isoformat(),teams=['SEA','DEN'],source_sha256='official-sha'),
        salary_sources={'immutable.csv':'sha'},players={PID:dict(availability_state='AVAILABLE',availability_status='ACT',
        availability_observed_at=NOW.isoformat(),role_observed_at=NOW.isoformat(),canonical_role='expected_starter',
        official_status=None,official_listed=True,official_practice='Full Participation in Practice',
        salaries={'CPT':dict(native_id='123',salary=15000,team='SEA',position='WR',game_info=rows[0]['game_id'],status='Q')})})
    return job,evidence


def evaluate(job, evidence, now=NOW):
    # Structural export/model checks have their own real tests. These fixtures
    # isolate availability, scoped lineage and clearance invalidation.
    with patch('backend.app.product_services.analyst_shadow.validate_snapshot'), patch('backend.app.product_services.saved_upload_readiness.DraftKingsExportService.build_lineup_download'):
        return validate_inputs(job,evidence,now)


def test_provisional_csv_clearance_never_claims_final_active_or_relabels_source():
    job,evidence=fixture(); before=deepcopy(job.params)
    result=evaluate(job,evidence)
    assert result['upload_ready'] is True and result['status']=='UPLOAD_READY_PENDING_INACTIVES'
    assert result['entry_ready'] is False and result['final_active_confirmed'] is False
    assert result['valid_until']=='2026-10-15T15:30:00+00:00'
    assert job.params==before and result['source_evidence']==evidence


@pytest.mark.parametrize('change', ['wrong_scope','out','questionable','unknown','stale','future','missing_id','wrong_id','salary','game','role','file','exception','no_official_proof','incomplete_report','expired_report','no_snapshot','wrong_projection','partial','explicit_preliminary'])
def test_blocks_invalid_or_changed_inputs(change):
    job,e=fixture();p=e['players'][PID];native=p['salaries']['CPT']
    if change=='wrong_scope': e['scope']={**e['scope'],'week':5}
    elif change=='out': p['official_status']='OUT'
    elif change=='questionable':p['official_status']='QUESTIONABLE'
    elif change=='unknown':p['availability_state']='UNKNOWN'
    elif change=='stale':p['availability_observed_at']=(NOW-timedelta(hours=25)).isoformat()
    elif change=='future':p['role_observed_at']=(NOW+timedelta(minutes=1)).isoformat()
    elif change=='missing_id':native['native_id']=None
    elif change=='wrong_id':native['native_id']='456'
    elif change=='salary':native['salary']=14000
    elif change=='game':native['game_info']='other'
    elif change=='role':p['canonical_role']='expected_backup'
    elif change=='file':e['salary_sources']['immutable.csv']='changed'
    elif change=='exception':job.params['questionable_eligible_player_ids']=[]
    elif change=='no_official_proof':p['official_listed']=False
    elif change=='incomplete_report':e['official']['teams']=['DEN']
    elif change=='expired_report':e['official']['observed_at']=(NOW-timedelta(hours=7)).isoformat()
    elif change=='no_snapshot':job.params['strategy_runtime']={}
    elif change=='wrong_projection':job.results[0][0]['projection_run_id']='different'
    elif change=='partial':job.status='failed'
    elif change=='explicit_preliminary':job.params['preliminary_report']={'research':True}
    result=evaluate(job,e)
    assert not result['upload_ready'] and result['reasons']


def test_lock_blocks_and_semantic_or_source_change_changes_binding():
    job,e=fixture()
    assert not evaluate(job,e,NOW+timedelta(hours=10))['upload_ready']
    original=evaluate(job,e)['input_basis_sha256']
    e['official']['source_sha256']='new-equivalent-capture'
    assert evaluate(job,e)['input_basis_sha256'] == original
    e['players'][PID]['salaries']['CPT']['native_id']='456'
    assert evaluate(job,e)['input_basis_sha256'] != original


@pytest.mark.parametrize('change', ['missing','tampered','false','expired','wrong_run','input_changed','current_out'])
def test_download_rejects_false_stale_wrong_or_changed_clearance(change):
    job,e=fixture(); stored=evaluate(job,e)
    stored['valid_until']=(datetime.now(UTC)+timedelta(minutes=20)).isoformat()
    if change=='false':stored['upload_ready']=False
    elif change=='expired':stored['valid_until']=(datetime.now(UTC)-timedelta(seconds=1)).isoformat()
    elif change=='wrong_run':stored['optimizer_run_id']='different'
    envelope={'payload':stored}; record_id='evaluation-'+digest(envelope)
    if change=='tampered':record_id='evaluation-forged'
    row=None if change=='missing' else {'record_id':record_id,'record_json':envelope}
    current=deepcopy(stored)
    if change=='input_changed':current['input_basis_sha256']='changed'
    if change=='current_out':current['upload_ready']=False;current['reasons']=['OUT']
    engine=MagicMock();engine.connect.return_value.__enter__.return_value.execute.return_value.mappings.return_value.first.return_value=row
    with patch('backend.app.product_services.saved_upload_readiness.assess',return_value=current):
        with pytest.raises(ValueError):require_clearance(engine,job)


def test_valid_clearance_returns_exact_persisted_reference():
    job,e=fixture();stored=evaluate(job,e);stored['valid_until']=(datetime.now(UTC)+timedelta(minutes=20)).isoformat()
    envelope={'payload':stored};rid='evaluation-'+digest(envelope)
    engine=MagicMock();engine.connect.return_value.__enter__.return_value.execute.return_value.mappings.return_value.first.return_value={'record_id':rid,'record_json':envelope}
    with patch('backend.app.product_services.saved_upload_readiness.assess',return_value=stored):
        assert require_clearance(engine,job)==rid


def test_live_refresh_composes_official_supplement_before_reading_current_roles():
    from backend.app.product_services.saved_upload_readiness import assess
    job,e=fixture(); job.results[0].append({**job.results[0][0], 'player_team':'DEN'}); order=[];engine=MagicMock()
    with patch('backend.app.product_services.official_injuries.refresh_official_injuries',side_effect=lambda *a,**kw:order.append('official')), \
         patch('backend.app.product_services.showdown_player_context.refresh_canonical_context',side_effect=lambda *a,**kw:order.append('canonical')), \
         patch('backend.app.product_services.saved_upload_readiness.current_evidence',side_effect=lambda *a:order.append('read') or e), \
         patch('backend.app.product_services.saved_upload_readiness.validate_inputs',return_value={'upload_ready':True}):
        assert assess(engine,job,refresh=True,now=NOW)['upload_ready']
    assert order==['official','canonical','read']


def test_saved_raw_questionable_flag_requires_named_proof_when_native_status_is_blank():
    job,e=fixture();e['players'][PID]['salaries']['CPT']['status']=None
    job.results[0][0]['player_status']='Q'
    assert evaluate(job,e)['upload_ready']
    job.params['questionable_eligible_player_ids']=[]
    assert not evaluate(job,e)['upload_ready']
    job.params['questionable_eligible_player_ids']=[PID]
    e['players'][PID]['official_listed']=False
    assert not evaluate(job,e)['upload_ready']
    e['players'][PID]['official_listed']=True
    e['players'][PID]['salaries']['CPT']['status']='OUT'
    assert not evaluate(job,e)['upload_ready']
