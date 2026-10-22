"""One exact raw-stat field revision + observed pair covariance source job."""
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime,UTC
from copy import deepcopy
from collections import Counter
import csv,gc,hashlib,json,os,time
from sqlalchemy import select,text
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.services.source_capture import SourceCaptureService,verify_snapshot_artifact,DEFAULT_NFLREADPY_LICENSE
from backend.app.product_services.weekly_passing_air_efficiency import load_reviewed_weekly_input
from backend.app.product_services.shared_pair_source import read_exact_td_revision,prepare_pair_actor_rows,persist_pair_identity_requests
from backend.app.product_services.shared_scoring_pair_covariance import build_shared_scoring_pair_covariance
from backend.app.product_services.offensive_environment_catalog import load_reviewed_environment_context
from backend.app.product_services.schedule_context_features import load_schedule_context
from backend.app.product_services.participation_source_components import _int
from backend.app.product_services.factual_designation import clock
from backend.app.product_services.market_snapshots import canonical_team
from backend.app.product_services.evaluation_record import digest
root=Path('research/shared_scoring_pair_covariance_20261020/v1');started=datetime.now(UTC);timer=time.monotonic()
def timing(stage,evidence):
 event=dict(package='shared_scoring_pair_covariance_v1',agent='/root/feature_inventory_defense_lineups',stage=stage,timestamp=datetime.now(UTC).isoformat(),evidence=evidence)
 fd=os.open('research/feature_platform_implementation_20261019/v1/PACKAGE_TIMINGS.jsonl',os.O_WRONLY|os.O_APPEND|os.O_CREAT,0o644)
 try:os.write(fd,(json.dumps(event,separators=(',',':'))+'\n').encode())
 finally:os.close(fd)
timing('source_start','Exact retained raw weekly IDs; new TD-field immutable revision plus approved-source pair transformation. Initial code start was unrecorded.')
def managed(ref,folder,cap,parse=True):
 p=Path(ref['path']);raw=p.read_bytes();assert p.resolve().parent==Path('artifacts',folder).resolve()and p.stem==ref['sha256']and len(raw)==ref['bytes']<=cap and hashlib.sha256(raw).hexdigest()==ref['sha256'];return json.loads(raw)if parse else None
sreceipt=json.loads(Path('research/scoring_share_components_20261020/v1/actual_derivation_receipt.json').read_text());scoring=managed(sreceipt['full_ref'],'scoring_share_components',16*1024*1024);before=scoring['before_period'];assert before==202606 and scoring['pregame_serving_eligible']is False
assert scoring['provenance']['producer_code_sha256']==hashlib.sha256(Path('backend/app/product_services/scoring_share_components.py').read_bytes()).hexdigest()
arec=json.loads(Path('research/active_workload_distributions_20261020/v1/actual_receipt.json').read_text());active=managed(arec['full_ref'],'active_workload_distributions',16*1024*1024)
assert clock(active['provenance']['actual_publication_at'])<=started and active['provenance']['producer_code_sha256']==hashlib.sha256(Path('backend/app/product_services/active_workload_distributions.py').read_bytes()).hexdigest()
weekly=load_reviewed_weekly_input(arec['weekly_input_ref'],cutoff=started)
weekly['rows']=[r for r in weekly['rows']if r['season']==before//100 and r['season']*100+r['week']<before];wanted={str(r['source_ref']['source_id'])for r in weekly['rows']};gc.collect()
extract=managed(arec['source_extract_ref'],'weekly_effectiveness_sources',64*1024*1024);assert clock(extract['actual_extracted_at'])<=started
extract['rows']=[r for r in extract['rows']if str(r['source_id'])in wanted];assert len(extract['rows'])==len(wanted);gc.collect()
env=json.loads(Path('research/environment_context_evidence_20261019/v1/actual_combined_receipt.json').read_text());source_id=scoring['provenance']['source']['snapshot_id'];assert source_id==env['parent_artifact_ref']['source_snapshot_id']
with Session(engine)as session:
 pbp=session.get(SourceSnapshot,source_id);verified=load_reviewed_environment_context(env['full_context'],pbp,actual_read_at=started)
 assert scoring['provenance']['source']['content_sha256']==pbp.content_sha256 and scoring['provenance']['event_receipt_sha256']==env['parent_artifact_ref']['event_receipt_sha256']
 schedule=load_schedule_context(session.get(SourceSnapshot,'6a346947-eca2-5c0d-abf0-95e52ac72e5b'),cutoff=started)
 source_PBP=dict(snapshot_id=str(pbp.snapshot_id),sha256=pbp.content_sha256,bytes=pbp.byte_count,source_uri=pbp.source_uri,observed_at=clock(pbp.observed_at).isoformat(),captured_at=clock(pbp.captured_at).isoformat());lock=pbp.slate_lock_at;csv_path=Path(pbp.artifact_path)
 ids_digest=digest(sorted(wanted));uri='retained-db://public.raw_nfl_weekly_stat/source_ids_sha256='+ids_digest+'/original_extract='+arec['source_extract_ref']['sha256']+'/pair_TD_fields_v1'
 existing=list(session.scalars(select(SourceSnapshot).where(SourceSnapshot.source_uri==uri)).all());assert len(existing)<=1,'Ambiguous retained field revisions require explicit reference'
 if existing:
  snapshot=existing[0];verify_snapshot_artifact(snapshot);revision=json.loads(Path(snapshot.artifact_path).read_text());source_appends=0
 else:
  revision=read_exact_td_revision(engine,extract['rows'],cutoff=datetime.now(UTC));revision['original_extract_ref']=arec['source_extract_ref'];revision['native_source_ids_sha256']=ids_digest
  with TemporaryDirectory()as temporary:
   p=Path(temporary)/'weekly_pair_TD_field_revision.json';raw=json.dumps(revision,sort_keys=True,separators=(',',':'),default=str,allow_nan=False).encode();assert len(raw)<=8*1024*1024;p.write_bytes(raw)
   cap=SourceCaptureService(session).capture_file(p,source_system='retained_db',dataset='weekly_pair_td_field_revision',season=2026,week=6,slate='offline_pair_features',source_uri=uri,source_license=DEFAULT_NFLREADPY_LICENSE,slate_lock_at=lock,media_type='application/json',row_count=len(revision['rows']),metadata=dict(contract=revision['version'],native_source_ids_sha256=ids_digest,original_extract_ref=arec['source_extract_ref'],original_http_snapshot_claim=False,original_TD_field_publication='unknown; captured only now'))
   snapshot=cap.snapshot;source_appends=1
 verify_snapshot_artifact(snapshot);assert snapshot.source_system=='retained_db'and snapshot.dataset=='weekly_pair_td_field_revision'and snapshot.source_uri==uri and snapshot.row_count==len(wanted)and clock(revision['actual_fields_read_at'])<=clock(snapshot.observed_at)<=clock(snapshot.captured_at)
 td_ref=dict(snapshot_id=str(snapshot.snapshot_id),path=snapshot.artifact_path,sha256=snapshot.content_sha256,bytes=snapshot.byte_count,source_uri=snapshot.source_uri,observed_at=clock(snapshot.observed_at).isoformat(),captured_at=clock(snapshot.captured_at).isoformat())
(root/'TD_SOURCE_RECEIPT.json').write_text(json.dumps(dict(source_ref=td_ref,new_snapshot_appends=source_appends),indent=2)+'\n')
# Reused capture must still match the exact original source row projection/IDs.
from backend.app.product_services.shared_pair_source import validate_td_revision
validate_td_revision(revision['rows'],extract['rows'],cutoff=datetime.now(UTC))
prepared=prepare_pair_actor_rows(active,weekly,extract,revision,before_period=before,cutoff=datetime.now(UTC));del weekly,extract;gc.collect()
lookup={};seen=set()
with csv_path.open(newline='')as handle:
 reader=csv.DictReader(handle);assert {'game_id','play_id','season_type','season','week','posteam','passer_player_id'}<=set(reader.fieldnames)
 needed={(e['game_id'],str(e['play_id']))for e in scoring['event_basis']if e['passing_and_receiving_same_TD']is not False}
 for raw in reader:
  if raw['season_type']!='REG'or _int(raw['season'])*100+_int(raw['week'])>=before:continue
  key=(raw['game_id'],str(_int(raw['play_id'])))
  if key in seen:raise ValueError('Duplicate original PBP key')
  seen.add(key)
  if key in needed:lookup[key]=dict(passer=raw['passer_player_id']or None,team=canonical_team(raw['posteam'])if raw['posteam']else None)
assert set(lookup)==needed
physical=[]
for e in scoring['event_basis']:
 key=(e['game_id'],str(e['play_id']));p=lookup.get(key)
 if p and p['team']is not None and p['team']!=e['team']:raise ValueError('Native passer/offense differs from reviewed scoring event')
 physical.append(dict(game_id=e['game_id'],play_id=str(e['play_id']),team=e['team'],physical_passing_TD=e['passing_and_receiving_same_TD'],source_passer_id=p['passer']if p else None,source_TD_scorer_id=e.get('receiver'),source_initial_receiver_id=e.get('original_receiver')))
games=[dict(game_id=g['game_id'],season=g['season'],week=g['week'],team=team)for g in schedule['game_rows']if g['game_type']=='REG'and g['season']==2026 and g['season']*100+g['week']<before for team in(g['home_team'],g['away_team'])]
result=build_shared_scoring_pair_covariance(prepared['actor_rows'],games,physical,before_period=before)
result['provenance']=dict(actual_read_started_at=started.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),active_workload_ref=arec['full_ref'],weekly_ref=arec['weekly_input_ref'],source_extract_ref=arec['source_extract_ref'],TD_field_revision_ref=td_ref,scoring_ref=sreceipt['full_ref'],source_PBP=source_PBP,authenticated_environment=verified['provenance'],schedule=schedule['provenance'],source_actor_rows=prepared['actor_rows'],unbound_source_rows=prepared['unbound_source_rows'],unbound_native_scope_keys=prepared['unbound_native_scope_keys'],positive_participants_missing_weekly_rows=prepared['positive_participants_missing_weekly_rows'],unresolved_participation_rows=prepared['unresolved_participation_rows'],inherited_identity_scope='Reviewed full weekly global collision withholding retained; positive-snap unmapped/residual actors remain explicit, no new aliases',producer_code_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in [Path('backend/app/product_services')/(n+'.py')for n in ('shared_pair_source','shared_scoring_pair_covariance','active_workload_distributions','weekly_effectiveness_catalog_features','scoring_share_components')]})
def save(value):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False,default=str).encode();assert len(raw)<=64*1024*1024;sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/shared_scoring_pair_covariance')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb')as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
full=save(result);selected={k:deepcopy(v)for k,v in result.items()if k not in {'pair_game_rows','profiles','provenance','semantic_sha256','physical_passing_TD_event_evidence','source_game_physical_passing_TDs'}}
for field in('pair_game_rows','profiles','physical_passing_TD_event_evidence','source_game_physical_passing_TDs'):selected[field]=[r for r in result[field]if r.get('team')in {'SF','WAS'}]
selected['identity_scope']='All batch-global attachment incidents retained';selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};sel=save(selected)
with engine.begin()as connection:queue=persist_pair_identity_requests(connection,result,source_refs=[full,td_ref])
if queue['records']:
 with engine.connect()as connection:records=[dict(r)for r in connection.execute(text("SELECT identity_quarantine_id,source_table,source_record_key,source_player_key,status,first_seen_at,updated_at FROM target.identity_quarantine WHERE identity_quarantine_id=ANY(CAST(:ids AS text[]))"),dict(ids=[q['identity_quarantine_id']for q in queue['records']])).mappings()]
 assert len(records)==queue['requests'];queue['durable_readback_records']=records
receipt=dict(actual_started_at=started.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-timer,before_period=before,full_ref=full,selected_ref=sel,TD_field_revision_ref=td_ref,new_source_snapshot_appends=source_appends,physical_source_events=len(physical),native_expected_game_sides=len(games),source_actor_logs=len(prepared['actor_rows']),pair_games=len(result['pair_game_rows']),pair_profiles=len(result['profiles']),exact_pair_profiles=sum(p['exact']is not None for p in result['profiles']),nondegenerate_TD_correlations=sum(p['exact']is not None and p['exact']['TD_score_components']['correlation']is not None for p in result['profiles']),nondegenerate_count_correlations=sum(p['exact']is not None and p['exact']['pass_attempt_target']['correlation']is not None for p in result['profiles']),global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],queue=queue,source_fetches=0,parent_inflates=0,aliases_mutated=0,models=0,pregame_serving_eligible=False)
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2,default=str)+'\n');timing('source_end',dict(status='success',actual_receipt=str((root/'actual_receipt.json').resolve())));print(json.dumps({k:v for k,v in receipt.items()if k!='queue'},indent=2,default=str));print(json.dumps({k:queue[k]for k in ('requests','created_new','existing_unchanged')}))
