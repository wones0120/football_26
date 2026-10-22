"""Preserve exact unattached subject evidence and one append-only review case; zero feature approval."""
from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from sqlalchemy import text
from backend.app.db import engine
from backend.app.product_services.documented_restriction_source import inspect_unattached_restriction,identity_case_request
from backend.app.product_services.nws_hourly_precipitation_context import _time
ROOT=Path('research/documented_workload_restriction_20261020/v1');started=datetime.now(UTC);timer=time.monotonic()
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p.resolve()),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))
r=json.loads((ROOT/'source_receipt.json').read_text());assert len(r['sources'])==1 and _time(r['actual_completed_at'])<=started;s=r['sources'][0];raw=Path(s['path']).read_bytes();m=json.loads(Path(s['manifest_path']).read_text());assert m['snapshot_id']==s['snapshot_id']and m['source_uri']==s['source_uri']and m['content_sha256']==s['sha256']and m['byte_count']==s['bytes'];assert m['metadata']['contract']=='official_team_workload_restriction_document_source_v1'and m['metadata']['team_id']=='NYJ';assert _time(m['captured_at'])==_time(s['captured_at'])and _time(m['observed_at'])==_time(s['observed_at'])and s['restriction_effective_at']is None
f=inspect_unattached_restriction(raw,dict(s,team_id='NYJ'),actual_cutoff=started)
# Reuse the first immutable derived source fact and its request. New read clocks must
# not fabricate a new evidence case for an equivalent source/producer payload.
if (ROOT/'actual_receipt.json').exists():
 prior=json.loads((ROOT/'actual_receipt.json').read_text());old_ref=prior['full_ref'];old_bytes=Path(old_ref['path']).read_bytes();assert hashlib.sha256(old_bytes).hexdigest()==old_ref['sha256']and len(old_bytes)==old_ref['bytes'];old_fact=json.loads(old_bytes)
 assert {k:v for k,v in old_fact.items()if k!='provenance'}==f,'Changed semantic source requires separately reviewed version'
 if old_fact['provenance']['producer_ref']!=ref('backend/app/product_services/documented_restriction_source.py'):
  binding=json.loads((ROOT/'CURRENT_GUARD_BINDING.json').read_text());assert binding['original_measurement_ref']==old_ref and binding['current_guard_ref']==ref('backend/app/product_services/documented_restriction_source.py')
  core={k:v for k,v in old_fact.items()if k!='provenance'};assert binding['original_measurement_core_sha256']==hashlib.sha256(json.dumps(core,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 expected=identity_case_request(old_fact,old_ref);assert expected==prior['queue_request']
 with engine.connect()as conn:
  row=conn.execute(text('SELECT identity_quarantine_id,source_record_key,source_player_key,status,first_seen_at,updated_at FROM target.identity_quarantine WHERE source_schema=\'public\' AND source_table=\'source_snapshot\' AND source_record_key=:key'),{'key':expected['source_record_key']}).mappings().one();assert row['identity_quarantine_id']==expected['identity_quarantine_id']and row['source_player_key']==expected['source_player_key']
 reused=dict(actual_checked_at=datetime.now(UTC).isoformat(),reused_full_ref=old_ref,queue_readback=dict(row),new_review_cases=0,database_writes=0,prior_receipt_unchanged=True)
 (ROOT/'idempotence_readback.json').write_text(json.dumps(reused,indent=2,default=str)+'\n');print(json.dumps(reused,default=str));raise SystemExit(0)
assert f['source_profile_href_candidates']==[],'Unexpected native-profile candidate: stop for supported chain review, do not guess'
f['provenance']=dict(source_ref=s,manifest_ref=ref(s['manifest_path']),source_index_week=s.get('week',1),index_scope_note='Original intake classified Week1 reference; article explicitly contains Week1 history and intended Week2 restriction. No retagging or player value.',actual_read_at=started.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),producer_ref=ref('backend/app/product_services/documented_restriction_source.py'),model_consumed=False)
b=json.dumps(f,sort_keys=True,separators=(',',':'),allow_nan=False).encode();p=Path('artifacts/documented_restriction_source')/(hashlib.sha256(b).hexdigest()+'.json');p.parent.mkdir(exist_ok=True)
if p.exists():assert p.read_bytes()==b
else:
 with p.open('xb')as out:out.write(b)
 p.chmod(0o444)
full=ref(p);q=identity_case_request(f,full)
with engine.begin()as conn:
 old=conn.execute(text('SELECT identity_quarantine_id,status,first_seen_at,updated_at FROM target.identity_quarantine WHERE source_schema=\'public\' AND source_table=\'source_snapshot\' AND source_record_key=:key'),{'key':q['source_record_key']}).mappings().first()
 conn.execute(text('''INSERT INTO target.identity_quarantine
 (identity_quarantine_id,entity_type,source_schema,source_table,source_record_key,source_system,season,week,slate,source_player_key,display_name,team_id,position,reason_code,candidate_player_ids,status,first_seen_at,updated_at)
 VALUES (:qid,'player','public','source_snapshot',:key,'official_team',2023,2,'FEATURE_INVENTORY',:subject,:name,'NYJ','RB',:reason,CAST('[]' AS jsonb),'open',now(),now())
 ON CONFLICT(source_schema,source_table,source_record_key) DO NOTHING'''),dict(qid=q['identity_quarantine_id'],key=q['source_record_key'],subject=q['source_player_key'],name=q['display_name'],reason=q['reason_code']))
 row=conn.execute(text('SELECT identity_quarantine_id,source_record_key,source_player_key,status,first_seen_at,updated_at FROM target.identity_quarantine WHERE source_schema=\'public\' AND source_table=\'source_snapshot\' AND source_record_key=:key'),{'key':q['source_record_key']}).mappings().one();assert row['identity_quarantine_id']==q['identity_quarantine_id']and row['source_player_key']==q['source_player_key'];record=dict(row)
 if old:assert all(record[k]==old[k]for k in old)
out=dict(actual_started_at=started.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-timer,full_ref=full,source_article_id=f['source_article_id'],catalog_ids_promoted=0,restriction_catalog_value=None,identity_blocker=f['identity_blocker'],source_requests=0,queue_request=q,queue_readback=record,new_review_cases=int(old is None),existing_case_updated=False,aliases_mutated=False,models=0)
(ROOT/'actual_receipt.json').write_text(json.dumps(out,indent=2,default=str)+'\n');print(json.dumps(out,default=str))
