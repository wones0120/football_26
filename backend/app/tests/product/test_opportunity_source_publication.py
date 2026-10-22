from copy import deepcopy
from datetime import timedelta
import json
from types import SimpleNamespace
from uuid import UUID

import pytest

from backend.app.product_services import opportunity_source_publication as publication
from backend.app.product_services.evaluation_record import digest
from backend.app.product_services.opportunity_source_capture import freeze_event_artifact, freeze_scalar_artifact
from backend.app.tests.product.test_opportunity_source_capture import service, capture, derive, NOW, CANONICAL


class Ledger:
    """Isolated append-only ledger; real source/derived artifact checks below."""
    def __init__(self, session):
        self.session=session;self.records=[]
    def get(self,*args):return self.session.get(*args)
    def execute(self,sql,params):
        rows=self.records
        if 'key' in params:
            rows=[r for r in rows if r['record_json']['payload']['idempotency_key']==params['key']]
        return SimpleNamespace(mappings=lambda:SimpleNamespace(all=lambda:list(reversed(rows))))


@pytest.fixture
def prepared_source(service,tmp_path,monkeypatch):
    snapshot=capture(service).snapshot
    event=derive(snapshot)
    parent_root=tmp_path/'events';scalar_root=tmp_path/'scalar'
    parent=freeze_event_artifact(event,snapshot,directory=parent_root)
    scalar=freeze_scalar_artifact(parent,snapshot,before_period=202603,cutoff=NOW+timedelta(minutes=2),
        teams=['BUF','MIA'],actor_ids=[CANONICAL],directory=scalar_root,parent_directory=parent_root,
        producer_clock=lambda:NOW+timedelta(minutes=3))
    ledger=Ledger(service.session)
    def append(session,kind,payload,*,source=None,run_id=None):
        envelope=dict(contract='evaluation_record_v1',kind=kind,optimizer_run_id=run_id,source=source,payload=deepcopy(payload))
        record=dict(record_id='evaluation-'+digest(envelope),record_json=envelope);session.records.append(record)
        return record['record_id']
    monkeypatch.setattr(publication,'append_record',append)
    request=publication.SourcePublicationRequest(source_snapshot_id=snapshot.snapshot_id,scalar_sha256=scalar['sha256'],idempotency_key='synthetic-source')
    dirs=dict(scalar_directory=scalar_root,parent_directory=parent_root)
    return ledger,request,dirs,snapshot,scalar


def test_real_source_publication_idempotent_and_prepared_read_is_not_forecast(prepared_source):
    ledger,request,dirs,snapshot,scalar=prepared_source
    now=NOW+timedelta(minutes=4)
    first=publication.publish(ledger,request,now=now,**dirs)
    retry=publication.publish(ledger,request,now=now+timedelta(minutes=1),**dirs)
    assert retry['reused'] and retry['record_id']==first['record_id'] and retry['published_at']==first['published_at']
    assert len(ledger.records)==1
    result=publication.prepared_context(ledger,season=2026,week=3,teams=['BUF','MIA'],actor_ids=[CANONICAL],cutoff=now+timedelta(minutes=1),**dirs)
    assert result['status']=='available_descriptive' and result['forecast'] is None
    assert result['publication_record_id']==first['record_id']
    assert result['facts']['opportunity']['team_rows'][0]['counted_lower_bound']['rush_attempts']==1
    assert result['facts']['opportunity']['quality']['game_completion'].startswith('unverified')
    assert result['numeric_forecast_consumption'].startswith('unconsumed_until')


def test_unknown_actor_does_not_change_team_budget_or_donate_opportunities(prepared_source):
    ledger,request,dirs,_,_=prepared_source;now=NOW+timedelta(minutes=4)
    publication.publish(ledger,request,now=now,**dirs)
    args=dict(season=2026,week=3,teams=['BUF','MIA'],cutoff=now,**dirs)
    known=publication.prepared_context(ledger,actor_ids=[CANONICAL],**args)
    missing=str(UUID(int=999))
    unknown=publication.prepared_context(ledger,actor_ids=[CANONICAL,missing],**args)
    assert known['facts']==unknown['facts']
    assert unknown['missing_canonical_attachment_ids']==[missing]
    assert unknown['attachment_status']=='refresh_required_for_missing_actors'
    assert 'not zero opportunity' in unknown['missing_actor_meaning']


def test_future_publication_wrong_period_and_source_tamper_are_explicit(prepared_source):
    ledger,request,dirs,snapshot,_=prepared_source;now=NOW+timedelta(minutes=4)
    publication.publish(ledger,request,now=now,**dirs)
    args=dict(teams=['BUF','MIA'],actor_ids=[CANONICAL],**dirs)
    assert publication.prepared_context(ledger,season=2026,week=3,cutoff=NOW+timedelta(minutes=3),**args)['status']=='unavailable'
    assert publication.prepared_context(ledger,season=2026,week=4,cutoff=now,**args)['status']=='stale_period'
    snapshot.content_sha256='b'*64  # Isolated fixture metadata corruption; immutable bytes stay untouched.
    result=publication.prepared_context(ledger,season=2026,week=3,cutoff=now,**args)
    assert result['status']=='integrity_failed' and result['forecast'] is None


def test_changed_content_under_key_rejected_and_no_client_facts_or_paths(prepared_source):
    ledger,request,dirs,_,_=prepared_source;now=NOW+timedelta(minutes=4)
    publication.publish(ledger,request,now=now,**dirs)
    old=ledger.records[0]['record_json'];old['payload']['material']['semantic_measurements_sha256']='b'*64
    ledger.records[0]['record_id']='evaluation-'+digest(old)
    with pytest.raises(ValueError,match='different content'):
        publication.publish(ledger,request,now=now,**dirs)
    with pytest.raises(ValueError):
        publication.SourcePublicationRequest(**request.model_dump(),path='/tmp/fake.json')
