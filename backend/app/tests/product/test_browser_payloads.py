from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
import json

from backend.app.product_services.browser_payloads import readiness_summary
from backend.app.product_services.slate_preparation import preparation_summary
from backend.app.api.product_routes import get_optimizer_results


def test_compact_saved_results_preserve_roster_and_decisions_without_mutating_evidence():
    now=datetime.now(timezone.utc)
    params=dict(entry_readiness=dict(status='blocked',entry_ready=False,reasons=['final checks'],checks=[{'status':'fail'}],
        preparation_evidence={'large':'x'*1_000_000}),
        data_readiness=dict(status='READY',reason_codes=[],refresh={'large':'x'*1_000_000},required_sources={'market':{'status':'pass'}}))
    job=SimpleNamespace(job_id='saved',status='completed',strategy='baseline',params=params,contest_format='showdown',objective='gpp',
        results=[[{'player_id':'canonical','roster_position':'CPT','salary':6600}]],projection_run_id='projection',rule_run_id=None,
        data_cutoff_at=now,lineage_persisted=True,message='saved',created_at=now,updated_at=now)
    service=SimpleNamespace(get_job=lambda _:job)
    before=deepcopy(params)
    full=get_optimizer_results('saved',service=service)
    compact=get_optimizer_results('saved',service=service,compact=True)
    assert params==before and full.results==compact.results
    assert full.projection_run_id==compact.projection_run_id
    assert compact.entry_readiness['entry_ready'] is False and compact.entry_readiness['checks']==full.entry_readiness['checks']
    assert compact.data_readiness['required_sources']==full.data_readiness['required_sources']
    assert 'preparation_evidence' not in compact.entry_readiness and 'refresh' not in compact.data_readiness
    assert len(compact.model_dump_json())<len(full.model_dump_json())/100
    assert full.entry_readiness['preparation_evidence']==before['entry_readiness']['preparation_evidence']


def test_preparation_handoff_summaries_keep_binding_checks_and_never_change_original():
    handoff=dict(status='compatible',compatibility_sha256='retained',checked_packet_sha256='checked',scope={'season':2026},
        missing_checks=['unknown'],changes=[{'reason':'finding'}],research_dependency_snapshot={'payload':'x'*1_000_000},selection_candidates=[{'payload':'x'*10000}])
    raw=dict(projection_run_id='projection',source_sha256='source',analyst_handoff=handoff,analyst_intent_handoffs={'EXPECTED_GAME':handoff})
    before=deepcopy(raw);summary=preparation_summary(raw)
    assert raw==before
    for item in [summary['analyst_handoff'],summary['analyst_intent_handoffs']['EXPECTED_GAME']]:
        assert item['compatibility_sha256']=='retained' and item['missing_checks']==['unknown'] and item['changes']==handoff['changes']
        assert 'research_dependency_snapshot' not in item and 'selection_candidates' not in item
    assert len(json.dumps(summary))<len(json.dumps(raw))/100
    assert readiness_summary(None,omit=('refresh',)) is None
