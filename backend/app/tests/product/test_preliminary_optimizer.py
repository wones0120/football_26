from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from backend.app.main import app
from backend.app.product_schemas import OptimizerRunRequest
from backend.app.product_services.optimizer import OptimizerService
from backend.app.product_services.preliminary_optimizer import PreliminaryOptimizerRequest, save_snapshot,load_snapshot,validate_request,run_preliminary,CONTRACT
from scripts.run_merged_analyst_fixture import scenario_fixture


def snapshot_fixture():
    packet,fixture=scenario_fixture('CLASSIC')
    snapshot=dict(contract_id=CONTRACT,classification='PRELIMINARY_RESEARCH',entry_ready=False,
        preparation_job_id='failed-prep',scope=dict(season=2099,week=1,slate='SYNTHETIC_CLASSIC',contest_format='classic'),
        projection_run_id='synthetic-projection',ownership_run_id='synthetic-ownership',data_cutoff_at='2099-09-01T10:00:00+00:00',
        source_sha256='a'*64,pool_sha256='b'*64,assumption_manifest_sha256='c'*64,
        assumption_manifest={'exclude_player_ids':[fixture['players'][2]['player_id']]},
        normal_readiness={'status':'ERROR','reason_codes':['official_player_status_refresh_failed']},source_refresh={'official_player_status':{'status':'ERROR'}},
        source_manifest={'games':packet['games']},pool=fixture['players'],pool_attrs={})
    return snapshot,packet


def request_fixture(snapshot,strategy='MERGED_SCENARIOS'):
    return PreliminaryOptimizerRequest(snapshot_sha256=snapshot['sha256'],optimizer=OptimizerRunRequest(season=2099,week=1,slate='SYNTHETIC_CLASSIC',strategy='classic_large_gpp_v1',contest_format='classic',objective='gpp',projection_run_id='synthetic-projection',params={'num_lineups':2,'max_exposure':1,'exclude_questionable':True,'analyst_packet_sha256':'d'*64,'analyst_strategy':strategy,'analyst_portfolio_mode':'CONDITIONAL_COVERAGE','analyst_candidates_per_thesis':2}))


def test_immutable_snapshot_and_no_ready_claim(tmp_path):
    source,_=snapshot_fixture();snapshot=save_snapshot(source,directory=tmp_path)
    assert save_snapshot(source,directory=tmp_path)==snapshot
    assert load_snapshot(snapshot['sha256'],directory=tmp_path)['entry_ready'] is False
    path=tmp_path/(snapshot['sha256']+'.json');path.write_text('{}')
    with pytest.raises(ValueError,match='mismatch'):load_snapshot(snapshot['sha256'],directory=tmp_path)


@pytest.mark.parametrize('changed',[{'exclude_questionable':False},{'availability_overrides':[{'player_id':'00000000-0000-0000-0000-000000000001','assumption':'available'}]},{'prepared_input_job_id':'failed-prep'},{'ownership_run_id':'other'}])
def test_explicit_research_policy_cannot_be_silently_relaxed(tmp_path,changed):
    source,_=snapshot_fixture();snapshot=save_snapshot(source,directory=tmp_path);request=request_fixture(snapshot)
    request.optimizer.params.update(changed)
    with pytest.raises(ValueError):validate_request(request,snapshot)


@pytest.mark.parametrize('strategy',['CONSTRUCTION','MERGED_SCENARIOS'])
def test_preliminary_old_new_runs_save_blocked_readiness_and_base_truth(tmp_path,strategy):
    source,packet=snapshot_fixture();snapshot=save_snapshot(source,directory=tmp_path);request=request_fixture(snapshot,strategy)
    service=OptimizerService();service.engine=create_engine('sqlite://')
    saved=[]
    with patch.object(OptimizerService,'_persist_optimizer_run',side_effect=lambda job: saved.append(deepcopy(job)) or True),patch('backend.app.product_services.analyst_packets.load_packet',return_value=packet),patch('backend.app.product_services.analyst_generation.load_packet',return_value=packet),patch('backend.app.product_services.analyst_scenarios.datetime') as clock:
        clock.now.return_value=datetime(2099,9,1,12,tzinfo=UTC)
        job=run_preliminary(request,run_id='preliminary-'+strategy,service=service,directory=tmp_path)
    assert job.status=='completed' and len(job.results)==2
    assert job.params['entry_readiness']['entry_ready'] is False
    assert job.params['data_readiness']['status']=='ERROR'
    assert job.params['preliminary_report']['snapshot_sha256']==snapshot['sha256']
    assert job.message.startswith('PRELIMINARY RESEARCH') and saved
    excluded=snapshot['assumption_manifest']['exclude_player_ids'][0]
    assert all(excluded not in {p['player_id'] for p in lineup} for lineup in job.results)
    assert all(p['entry_ready'] is False and p['preliminary_research'] is True for lineup in job.results for p in lineup)


def test_preliminary_result_cannot_clear_or_export_through_normal_routes(monkeypatch):
    from backend.app.api import product_routes
    job=SimpleNamespace(params={'preliminary_report':{'entry_ready':False},'entry_readiness':{'entry_ready':False,'status':'PRELIMINARY_NOT_ENTRY_CLEARED'}},status='completed')
    app.dependency_overrides[product_routes.get_optimizer_service]=lambda: SimpleNamespace(get_job=lambda _:job)
    try:
        client=TestClient(app)
        assert client.post('/api/optimizer/results/research/readiness').json()['entry_ready'] is False
        assert client.get('/api/optimizer/results/research/draftkings/download').status_code==409
    finally:app.dependency_overrides.pop(product_routes.get_optimizer_service,None)


def test_unknown_exclusion_snapshot_retains_normal_errors_and_requires_other_sources(tmp_path):
    from unittest.mock import MagicMock
    from backend.app.product_services import preliminary_optimizer as preliminary
    from backend.app.product_services.analyst_shadow import digest
    source,packet=snapshot_fixture()
    manifest=source['source_manifest']; scoring_unknown=source['pool'][1]['player_id']
    manifest['availability']=[{'player_master_id':scoring_unknown,'player_name':'Stale OUT evidence','evidence_json':{'availability_state':'UNKNOWN'}}]
    proof={'immutable':'projection-proof','run':{'source_versions_json':{'preliminary_research':{'exclude_player_ids':[scoring_unknown]}}}}
    player={'player_id':source['pool'][0]['player_id'],'player':'Unknown player','availability':'unknown','reason_codes':['player_availability_unknown','player_status_stale']}
    readiness={'status':'NOT_READY','reason_codes':player['reason_codes'], 'players':[player],
               'required_sources':{name:{'status':'READY','reason_codes':[]} for name in ('salary_pool','market','projection','ownership')}}
    readiness['required_sources']['player_status']={'status':'NOT_READY','reason_codes':player['reason_codes']}
    prepared={'data_readiness':deepcopy(readiness),'projection_run_id':'research-projection','ownership_run_id':'research-ownership',
              'data_cutoff_at':'2099-09-01T12:00:00Z','source_sha256':digest(manifest),'projection_lineage_sha256':digest(proof),'source_manifest':manifest,'source_refresh':{}}
    payload={'season':2099,'week':1,'slate':'SYNTHETIC_CLASSIC','contest_format':'classic','action':'prepare','preliminary_research':True}
    job=SimpleNamespace(job_id='research-preparation',job_type='slate_preparation',status='completed',request_json=payload,result_json=prepared)
    session=MagicMock();session.scalar.return_value=job
    service=SimpleNamespace(_load_player_pool=lambda *a,**kw:__import__('pandas').DataFrame(source['pool']))
    with patch.object(preliminary,'assess_prepared_inputs',return_value=readiness),patch.object(preliminary,'source_manifest',return_value=manifest),patch.object(preliminary,'projection_proof',return_value=proof),patch.object(preliminary,'verify_artifacts'),patch.object(preliminary,'require_prelock'),patch('backend.app.product_services.player_roles.resolve_player_roles',side_effect=lambda frame:(frame,{})),patch('backend.app.product_services.kicker_roles.assign_kicker_roles',side_effect=lambda frame:(frame,{})),patch('backend.app.product_services.analyst_preparation.save_snapshot_handoff'):
        snapshot=preliminary.create_snapshot(session,preliminary.PreliminarySnapshotRequest(preparation_job_id=job.job_id),service,directory=tmp_path)
        assert snapshot['entry_ready'] is False
        assert snapshot['normal_readiness']==readiness
        assert snapshot['assumption_manifest']['exclude_player_ids']==sorted([player['player_id'],scoring_unknown])
        recorded=next(p for p in snapshot['assumption_manifest']['players'] if p['player_id']==scoring_unknown)
        assert recorded['availability']=='unknown' and recorded['source_context']['evidence_json']['availability_state']=='UNKNOWN'
        assert recorded['research_assumption']=='EXCLUDE_FROM_RESEARCH'
        assert snapshot['assumption_manifest']['players'][0]['research_assumption']=='EXCLUDE_FROM_RESEARCH'
        assert snapshot['assumption_manifest']['assumed_available_player_ids']==[]
        assert snapshot['assumption_manifest_sha256']==digest(snapshot['assumption_manifest'])
        readiness['required_sources']['market']['status']='NOT_READY'
        with pytest.raises(ValueError,match='verified market'):preliminary.create_snapshot(session,preliminary.PreliminarySnapshotRequest(preparation_job_id=job.job_id),service,directory=tmp_path)
        readiness['required_sources']['market']['status']='READY'
        job.request_json={**payload,'preliminary_research':False}
        with pytest.raises(ValueError,match='Unsupported preliminary readiness blocker'):preliminary.create_snapshot(session,preliminary.PreliminarySnapshotRequest(preparation_job_id=job.job_id),service,directory=tmp_path)


def test_preliminary_classic_solve_does_not_copy_full_context_attrs(tmp_path):
    source, packet = snapshot_fixture()
    original_context = [{'player_master_id':'outside-fixture','evidence_json':{'source_facts':[{'native':'immutable'}]}}]
    source['pool_attrs']['role_context'] = deepcopy(original_context)
    snapshot = save_snapshot(source,directory=tmp_path)
    request = request_fixture(snapshot,'MERGED_SCENARIOS')
    service=OptimizerService();service.engine=create_engine('sqlite://')
    original_solve=OptimizerService._solve_lineup;seen=[]
    def inspect_working_attrs(self, frame, *args, **kwargs):
        assert 'role_context' not in frame.attrs
        seen.append(True)
        return original_solve(self, frame, *args, **kwargs)
    with patch.object(OptimizerService,'_persist_optimizer_run',return_value=True),patch.object(OptimizerService,'_solve_lineup',new=inspect_working_attrs),patch('backend.app.product_services.analyst_packets.load_packet',return_value=packet),patch('backend.app.product_services.analyst_generation.load_packet',return_value=packet),patch('backend.app.product_services.analyst_scenarios.datetime') as clock:
        clock.now.return_value=datetime(2099,9,1,12,tzinfo=UTC)
        job=run_preliminary(request,run_id='no-repeated-metadata',service=service,directory=tmp_path)
    assert seen and job.status=='completed' and len(job.results)==2
    assert load_snapshot(snapshot['sha256'],directory=tmp_path)['pool_attrs']['role_context']==original_context
    assert job.params['preliminary_report']['snapshot_sha256']==snapshot['sha256']
