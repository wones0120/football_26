from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from backend.app.product_services import slate_preparation as prep

PARENT = '11111111-1111-4111-8111-111111111111'
CURRENT = '22222222-2222-4222-8222-222222222222'


def fixture():
    original = prep.SlatePreparationRequest(season=2026, week=6, slate='MONDAY_NIGHT',
        action='prepare', contest_format='showdown', include_workload_forecast=True,
        minimum_player_salary=1700)
    manifest = {'games': [{'game_id':'2026_06_WAS_SF','kickoff_at':(datetime.now(UTC)+timedelta(hours=1)).isoformat()}]}
    counts = {'version':'fixture', 'players':[{'counts':{'targets':None, 'rush_attempts':0}}]}
    counts['sha256'] = prep.digest(counts)
    proof = {'projection':'original-proof'}
    result = dict(source_manifest=manifest, source_sha256=prep.digest(manifest),
        projection_lineage_sha256=prep.digest(proof), projection_run_id='original-projection',
        data_cutoff_at='2026-10-19T23:00:00+00:00', workload_forecast=counts,
        analyst_handoff={'status':'old'}, analyst_intent_handoffs={'old':'old'})
    parent = SimpleNamespace(job_id=PARENT,status='completed',request_json=original.model_dump(),
        result_json=result,created_at=datetime.now(UTC))
    request=original.model_copy(update={'reuse_prepared_input_job_id':PARENT})
    return parent,request,manifest,proof


def call(parent,request,manifest,proof,jobs=()):
    session=SimpleNamespace(get=lambda *args:parent)
    with patch.object(prep,'source_manifest',return_value=manifest), patch.object(prep,'verify_artifacts') as verify, \
         patch.object(prep,'projection_proof',return_value=proof),patch.object(prep,'preparation_jobs',return_value=jobs):
        result=prep.recheck_saved_preparation(session,request,current_job_id=CURRENT)
        verify.assert_called_once()
        return result


def test_exact_inputs_reused_without_changing_original_or_unknowns():
    parent,request,manifest,proof=fixture(); original=deepcopy(parent.result_json)
    result=call(parent,request,manifest,proof)
    assert parent.result_json==original
    assert result['workload_forecast']==original['workload_forecast']
    assert result['data_cutoff_at']==original['data_cutoff_at']
    assert 'analyst_handoff' not in result
    assert result['research_recheck']['source_capture_or_model_fit_performed'] is False


@pytest.mark.parametrize('kind',['scope','floor','count','source','projection','newer','failed','locked'])
def test_changed_or_unverified_evidence_cannot_reuse(kind):
    parent,request,manifest,proof=fixture(); jobs=[]
    if kind=='scope': request=request.model_copy(update={'week':7})
    if kind=='floor': request=request.model_copy(update={'minimum_player_salary':1600})
    if kind=='count': parent.result_json['workload_forecast']['players'][0]['counts']['targets']=0
    if kind=='source': manifest={**manifest,'revision':'new'}
    if kind=='projection': proof={'projection':'changed'}
    if kind=='newer': jobs=[SimpleNamespace(job_id='other',created_at=parent.created_at+timedelta(seconds=1))]
    if kind=='failed':parent.status='failed'
    if kind=='locked':manifest['games'][0]['kickoff_at']=(datetime.now(UTC)-timedelta(minutes=1)).isoformat()
    with pytest.raises(ValueError):call(parent,request,manifest,proof,jobs)


def test_recheck_actual_prepare_consumer_does_not_capture_fit_or_recompute_counts():
    import pandas as pd
    from contextlib import nullcontext
    parent,request,manifest,proof=fixture()
    frozen=deepcopy(parent.result_json)
    frozen['source_manifest']['opportunity_source']={'status':'available_descriptive'}
    frozen.update(ownership_run_id='ownership',source_refresh={},feature_run_id='features')
    service=SimpleNamespace(engine=object(),_load_player_pool=lambda *a,**k:pd.DataFrame([{'player_id':'canonical'}]))
    context=SimpleNamespace(job_id=CURRENT,progress=lambda *a,**k:None)
    with patch('backend.app.product_services.optimizer.OptimizerService',return_value=service), \
         patch('backend.app.db.SessionLocal',return_value=nullcontext(object())), \
         patch.object(prep,'recheck_saved_preparation',return_value=frozen), \
         patch.object(prep,'assess_prepared_inputs',return_value={'status':'READY'}), \
         patch('backend.app.product_services.showdown_data_readiness.refresh_live_sources',side_effect=AssertionError('must not refresh')), \
         patch('backend.app.product_services.workload_count_forecast.prepare_receipt',side_effect=AssertionError('must not recompute')), \
         patch('backend.app.product_services.kicker_roles.assign_kicker_roles',side_effect=lambda p:(p,{})), \
         patch('backend.app.product_services.player_roles.resolve_player_roles',side_effect=lambda p:(p,{})), \
         patch('backend.app.product_services.analyst_personal_context.load_inputs',return_value=[]), \
         patch('backend.app.product_services.analyst_preparation.prepare_handoff',side_effect=lambda **k:{'status':'new_checked','rows':k['row_loader']()}) as bind:
        result=prep.prepare_optimizer_inputs(context,request)
    assert bind.call_count==3
    assert result['analyst_handoff']['status']=='new_checked'
    assert result['workload_forecast']==parent.result_json['workload_forecast']
    assert result['projection_run_id']=='original-projection'
