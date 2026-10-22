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


def classic_fixture():
    job, evidence = fixture()
    job.contest_format = 'classic'
    job.slate = 'SUNDAY_MAIN'
    evidence['scope'] = dict(season=job.season, week=job.week, slate=job.slate, contest_format='classic')
    row = job.results[0][0]
    row.update(roster_position='FLEX', dk_player_id='123', salary=5000)
    player = evidence['players'][PID]
    player['salaries'] = {'WR': {**player['salaries']['CPT'], 'salary':5000, 'status':''}}
    job.params['preliminary_report'] = {'snapshot_sha256':'frozen'}
    job.params.pop('prepared_input_evidence')
    frozen = dict(sha256='frozen', scope=evidence['scope'], projection_run_id='projection',
                  pool=[deepcopy(row)], assumption_manifest={'exclude_player_ids':[]})
    return job, evidence, frozen


def test_classic_preliminary_can_pass_separate_current_roster_check_without_relabeling():
    job, evidence, frozen = classic_fixture()
    before = deepcopy(job.params)
    with patch('backend.app.product_services.preliminary_optimizer.load_snapshot', return_value=frozen):
        result = evaluate(job, evidence)
    assert result['upload_ready'] is True
    assert result['entry_ready'] is False and job.params == before


@pytest.mark.parametrize('change', ['excluded','wrong_scope','wrong_projection','changed_salary','unknown','out','missing_clock'])
def test_classic_clearance_preserves_identity_exclusions_and_current_availability(change):
    job, evidence, frozen = classic_fixture()
    if change == 'excluded': frozen['assumption_manifest']['exclude_player_ids']=[PID]
    elif change == 'wrong_scope': frozen['scope']={**frozen['scope'],'week':5}
    elif change == 'wrong_projection': frozen['projection_run_id']='other'
    elif change == 'changed_salary': frozen['pool'][0]['salary']=6000
    elif change == 'unknown': evidence['players'][PID]['availability_state']='UNKNOWN'
    elif change == 'out': evidence['players'][PID]['official_status']='OUT'
    elif change == 'missing_clock': evidence['players'][PID]['role_observed_at']=None
    with patch('backend.app.product_services.preliminary_optimizer.load_snapshot', return_value=frozen):
        assert not evaluate(job, evidence)['upload_ready']


def test_classic_dst_uses_team_identity_not_individual_injury_status():
    job, evidence, frozen = classic_fixture()
    row = job.results[0][0]
    row.update(position='DST', roster_position='DST', canonical_role='team_defense')
    player = evidence['players'][PID]
    player.update(canonical_role='team_defense', availability_status=None,
                  availability_observed_at=None, role_observed_at=None)
    player['salaries']={'DST':{**player['salaries']['WR'],'position':'DST'}}
    frozen['pool']=[deepcopy(row)]
    with patch('backend.app.product_services.preliminary_optimizer.load_snapshot', return_value=frozen):
        assert evaluate(job, evidence)['upload_ready']
        player['salaries']['DST']['native_id']='wrong'
        assert not evaluate(job, evidence)['upload_ready']


def count_fixture():
    from backend.app.product_services.showdown_data_readiness import freeze_evidence
    from backend.app.product_services.workload_count_forecast import VERSION
    job,evidence=fixture()
    row=job.results[0][0]
    source={**row,'salary':10000,'projection':8.,'dk_captain_id':'123','dk_player_id':'124'}
    forecast={'player_master_id':PID,'utility':1.,'counts':{'targets':5.}}
    counts={'version':VERSION,'projection_run_id':'projection','players':[forecast]}
    counts['sha256']=digest(counts)
    row.update(base_projection=8.,workload_forecast=forecast,workload_forecast_sha256=counts['sha256'],dk_player_id='123')
    job.params.update(workload_comparison='normalized_counts',strategy_runtime={},
        prepared_input_evidence={'prepared_input_job_id':'prep','projection_run_id':'projection',
            'workload_forecast':counts,'games':[{'game_id':'2026_06_SEA_DEN'}]},
        showdown_evidence_snapshot=freeze_evidence([source],{'status':'READY','evaluated_at':NOW.isoformat(),
            'evidence_cutoff':NOW.isoformat()},optimizer_run_id='saved'))
    return job,evidence


def test_count_upload_authenticates_frozen_inputs_without_semantic_analyst():
    job,evidence=count_fixture()
    assert evaluate(job,evidence)['upload_ready']


@pytest.mark.parametrize('change',['frozen_hash','count_hash','wrong_run','wrong_projection','wrong_native',
    'wrong_salary','wrong_mean','wrong_forecast','unknown','override','game','no_preparation'])
def test_count_upload_rejects_changed_frozen_inputs(change):
    job,evidence=count_fixture(); row=job.results[0][0]
    if change=='frozen_hash':job.params['showdown_evidence_snapshot']['sha256']='bad'
    elif change=='count_hash':job.params['prepared_input_evidence']['workload_forecast']['sha256']='bad'
    elif change=='wrong_run':job.job_id='other'
    elif change=='wrong_projection':row['projection_run_id']='other'
    elif change=='wrong_native':row['dk_player_id']='other'
    elif change=='wrong_salary':row['salary']=14000
    elif change=='wrong_mean':row['base_projection']=9.
    elif change=='wrong_forecast':row['workload_forecast']={'utility':2.}
    elif change=='unknown':
        counts=job.params['prepared_input_evidence']['workload_forecast'];counts['players'][0]['utility']=None
        counts['sha256']=digest({k:v for k,v in counts.items() if k!='sha256'})
    elif change=='override':
        frozen=job.params['showdown_evidence_snapshot'];frozen['non_production_override']=True
        frozen['sha256']=digest({k:v for k,v in frozen.items() if k!='sha256'})
    elif change=='game':job.params['prepared_input_evidence']['games']=[{'game_id':'other'}]
    elif change=='no_preparation':job.params['prepared_input_evidence']={}
    assert not evaluate(job,evidence)['upload_ready']


def test_resolver_evaluation_clock_does_not_invalidate_identical_clearance_facts():
    job,evidence=fixture()
    resolution={'contract':'legacy-audit','status':'resolved','effective_designation':'ACTIVE',
        'evaluated_at':NOW.isoformat(),'chosen_fact':{'status':'ACTIVE','source_ids':['original']},'conflicts':[]}
    evidence['players'][PID]['designation_resolution']=resolution
    original=evaluate(job,evidence)['input_basis_sha256']
    resolution['evaluated_at']=(NOW+timedelta(minutes=1)).isoformat()
    assert evaluate(job,evidence)['input_basis_sha256']==original
    resolution['chosen_fact']['source_ids']=['new-factual-source']
    assert evaluate(job,evidence)['input_basis_sha256']!=original
    resolution['chosen_fact']['source_ids']=['original']
    resolution['effective_designation']='QUESTIONABLE'
    assert evaluate(job,evidence)['input_basis_sha256']!=original


def scenario_fixture():
    job,evidence=count_fixture()
    job.params.pop('workload_comparison')
    mode=dict(team='SEA',passing_factor=1.,rushing_factor=1.,rationale='Primary fixture',scoring_mode='new_model_primary')
    actor=dict(player_master_id=PID,baseline_mean=8.,conditional_mean=10.)
    primary=dict(players=[actor],scoring_head={'incumbent_projection_consumed':False})
    primary['sha256']=digest(primary)
    report=dict(config=mode,projection_run_id='projection',players=[actor],new_model_primary=True,primary_model_forecast=primary)
    report['sha256']=digest(report)
    job.params.update(scenario_mode=mode,strategy_runtime={'scenario_mode':{'prepared':deepcopy(report)}})
    job.params['prepared_input_evidence']['scenario_mode']=report
    job.results[0][0].update(projection=12.,scenario_mean=15.,scenario_mode_player=deepcopy(actor))
    return job,evidence


def test_primary_upload_authenticates_scores_without_analyst_snapshot():
    job,evidence=scenario_fixture()
    assert evaluate(job,evidence)['upload_ready']


@pytest.mark.parametrize('change',['receipt','primary','runtime','score','native','salary','baseline','player','run','override','game','no_preparation'])
def test_scenario_upload_rejects_changed_frozen_inputs(change):
    job,evidence=scenario_fixture();row=job.results[0][0];report=job.params['prepared_input_evidence']['scenario_mode']
    if change=='receipt':report['sha256']='bad'
    elif change=='primary':
        report['primary_model_forecast']['sha256']='bad';report['sha256']=digest({k:v for k,v in report.items() if k!='sha256'})
        job.params['strategy_runtime']['scenario_mode']['prepared']=deepcopy(report)
    elif change=='runtime':job.params['strategy_runtime']['scenario_mode']['prepared']={}
    elif change=='score':row['scenario_mean']=16.
    elif change=='native':row['dk_player_id']='bad'
    elif change=='salary':row['salary']=14000
    elif change=='baseline':row['projection']=13.
    elif change=='player':row['scenario_mode_player']={}
    elif change=='run':job.job_id='wrong'
    elif change=='override':
        f=job.params['showdown_evidence_snapshot'];f['non_production_override']=True;f['sha256']=digest({k:v for k,v in f.items() if k!='sha256'})
    elif change=='game':job.params['prepared_input_evidence']['games']=[{'game_id':'wrong'}]
    elif change=='no_preparation':job.params['prepared_input_evidence']={}
    assert not evaluate(job,evidence)['upload_ready']
