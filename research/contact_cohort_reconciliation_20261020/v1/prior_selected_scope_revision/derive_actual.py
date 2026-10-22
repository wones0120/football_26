"""Exact native actor/carry/yard-partition contact reconciliation, three seasons."""
from pathlib import Path
from datetime import datetime,UTC
from copy import deepcopy
import gc,hashlib,json,time
from collections import Counter
import polars as pl
from sqlalchemy import text
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.services.source_capture import verify_snapshot_artifact
from backend.app.product_services.contact_cohort_reconciliation import build_official_rushing_cohort,resolve_contact_identity,reconcile_contact_cohorts,persist_contact_identity_requests,_number,VERSION
from backend.app.product_services.offensive_line_participation import load_line_alias_evidence
from backend.app.product_services.pfr_source_components import BASE,asset_scope,validate_pfr_frame
from backend.app.product_services.factual_designation import clock
from backend.app.product_services.market_snapshots import canonical_team
from backend.app.product_services.evaluation_record import digest
root=Path('research/contact_cohort_reconciliation_20261020/v1');start=time.monotonic();read=datetime.now(UTC)
r=json.loads(Path('research/pfr_advanced_features_20261020/v1/actual_receipt.json').read_text());ref=r['artifact_ref'];assert ref['bytes']<=32*1024*1024
p=Path(ref['path']);raw=p.read_bytes();assert p.resolve().parent==Path('artifacts/pfr_advanced_features').resolve()and len(raw)==ref['bytes']and hashlib.sha256(raw).hexdigest()==ref['sha256'];frozen=json.loads(raw);del raw
assert clock(frozen['actual_derived_at'])<=read and frozen['producer_code_sha256']==hashlib.sha256(Path('backend/app/product_services/pfr_advanced_features.py').read_bytes()).hexdigest()
prior=frozen['features'];pfr=[];source_refs=[];original=[];cohorts=[]
with Session(engine)as session:
 for source in prior['provenance']['source_refs']:
  scope=source['scope']
  if scope['stat_type']!='rush'or scope['season']not in {2023,2024,2025}:continue
  snapshot=session.get(SourceSnapshot,source['snapshot_id']);verify_snapshot_artifact(snapshot);name=Path(snapshot.artifact_path).name
  assert snapshot.source_system=='nflverse_pfr'and snapshot.dataset=='pfr_advstats_week_rush'and snapshot.source_uri==BASE+name
  assert snapshot.byte_count<=4*1024*1024 and snapshot.content_sha256==source['source_sha256']and clock(snapshot.observed_at)<=clock(snapshot.captured_at)<=read
  assert asset_scope(name)==scope
  frame=pl.read_parquet(snapshot.artifact_path);validation=validate_pfr_frame(frame,**scope,max_season=read.year);assert validation['native_grain_valid']and frame.height<=100000
  for index,row in enumerate(frame.iter_rows(named=True)):
   if row['game_type']!='REG':continue
   pfr.append(dict(game_id=row['game_id'],team=canonical_team(row['team']),pfr_player_id=row['pfr_player_id'],carries=_number(row.get('carries')),
    before=_number(row.get('rushing_yards_before_contact')),after=_number(row.get('rushing_yards_after_contact')),
    original_source_ref=dict(snapshot_id=str(snapshot.snapshot_id),sha256=snapshot.content_sha256,native_row=index)))
  source_refs.append(dict(snapshot_id=str(snapshot.snapshot_id),sha256=snapshot.content_sha256,bytes=snapshot.byte_count,source_uri=snapshot.source_uri,captured_at=clock(snapshot.captured_at).isoformat(),scope=scope));del frame;gc.collect()
assert len(source_refs)==3
old={(a['game_id'],a['team'],a['pfr_player_id']):a for a in prior['actor_game_rows']if'G07-M07'in a['metrics']and int(a['game_id'][:4])in {2023,2024,2025}}
assert len(old)==len(pfr)
for a in pfr:
 b=old[(a['game_id'],a['team'],a['pfr_player_id'])]
 assert a['carries']==b['metrics']['G07-M07']['carry_exposure']
 assert a['before']==b['metrics']['G07-M07']['source_reported_value']and a['after']==b['metrics']['G07-M08']['source_reported_value']
descriptors=json.loads(Path('research/player_opportunity_history_20261020/v1/source_coverage.json').read_text());assert {d['season']for d in descriptors}=={2023,2024,2025}
for item in descriptors:
 d=item['descriptor'];assert d['manifest']['bytes']<=64*1024*1024 and clock(d['manifest']['received_at'])<=read;p=Path(d['path']);raw=p.read_bytes();assert len(raw)==d['manifest']['bytes']and hashlib.sha256(raw).hexdigest()==d['manifest']['sha256'];del raw
 required={'game_id','play_id','season','week','season_type','posteam','defteam','play_type','play_type_nfl','rush_attempt','pass_attempt','sack','qb_scramble','qb_spike','qb_kneel','two_point_attempt','fumble','rusher_player_id','rushing_yards'}
 names=pl.read_parquet_schema(p);assert required<=set(names)
 optional={'no_play','quarter_end','desc','lateral_rush','lateral_rusher_player_id','lateral_rushing_yards'}
 frame=pl.read_parquet(p,columns=sorted(required|(optional&set(names))));assert frame.height<=100000
 c=build_official_rushing_cohort(frame.iter_rows(named=True),before_period=202607);cohorts.append(c);original.append(dict(season=item['season'],descriptor=d,optional_field_availability={k:k in names for k in optional}));del frame;gc.collect()
cohort=dict(version=VERSION,before_period=202607,game_rows=[g for c in cohorts for g in c['game_rows']],event_basis=[e for c in cohorts for e in c['event_basis']]);del cohorts
cohort['provenance']=dict(original_PBP_sources=original,actual_read_at=read.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),producer_sha256=hashlib.sha256(Path('backend/app/product_services/contact_cohort_reconciliation.py').read_bytes()).hexdigest())
GSISkeys={n for g in cohort['game_rows']for n in g['actors']};PFRkeys={a['pfr_player_id']for a in pfr}
original_aliases=[deepcopy(a)for a in prior['provenance']['alias_receipts']if a['source_key']in PFRkeys]
assert all(clock(a['created_at'])<=clock(prior['provenance']['decision_cutoff_at'])<=read for a in original_aliases)
with engine.connect()as connection:
 aliases=load_line_alias_evidence(connection,GSISkeys,cutoff=read)
 masters={str(r['player_master_id']):clock(r['created_at']).isoformat()for r in connection.execute(text("SELECT player_master_id::text AS player_master_id,created_at AT TIME ZONE 'UTC' AS created_at FROM public.player_master WHERE player_master_id::text=ANY(CAST(:ids AS text[]))"),dict(ids=sorted({str(a['player_master_id'])for a in original_aliases}))).mappings()}
for a in aliases:a['player_master_id']=str(a['player_master_id'])
pfraliases=[{**a,'player_master_created_at':masters.get(str(a['player_master_id']))}for a in original_aliases]
gsis_proofs,GSISexcluded=resolve_contact_identity(GSISkeys,aliases,source_system='nflreadpy',cutoff=read)
pfr_proofs,PFRexcluded=resolve_contact_identity(PFRkeys,pfraliases,source_system='pfr',cutoff=read)
result=reconcile_contact_cohorts(cohort,pfr,gsis_proofs,pfr_proofs)
def save(value):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False,default=str).encode();assert len(raw)<=64*1024*1024
 sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/contact_cohort_reconciliation')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb')as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
cohort_ref=save(cohort)
result['provenance']=dict(PFR_original_source_refs=source_refs,PFR_prior_feature_ref=ref,PFR_original_alias_cutoff_at=prior['provenance']['decision_cutoff_at'],PFR_raw_actor_rows=pfr,
 official_rush_cohort_ref=cohort_ref,original_PBP_sources=original,actual_read_at=read.isoformat(),actual_alias_cutoff_at=read.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),
 producer_code_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in [Path('backend/app/product_services')/(n+'.py')for n in ('contact_cohort_reconciliation','pfr_advanced_features','pfr_source_components','offensive_line_participation','fumble_event_components')]},
 excluded_future_or_missing_master_alias_evidence=dict(nflreadpy=GSISexcluded,pfr=PFRexcluded),canonical_master_creation_evidence=masters,source_availability='Revised later captures/current identity receipts, not original historical pregame inputs')
full=save(result);selected={k:v for k,v in result.items()if k not in('game_rows','profiles','identity_review_requests','semantic_sha256','provenance')}
selected['game_rows']=[g for g in result['game_rows']if g['defense']in{'SF','WAS'}];selected['profiles']=[p for p in result['profiles']if p['defense']in{'SF','WAS'}]
selected['identity_review_requests']=[q for q in result['identity_review_requests']if q['team']in{'SF','WAS'}];selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};sel=save(selected)
with engine.begin()as connection:queue=persist_contact_identity_requests(connection,result,source_refs=[full,cohort_ref])
if queue['records']:
 with engine.connect()as connection:
  after=[dict(r)for r in connection.execute(text("SELECT identity_quarantine_id,source_table,source_record_key,source_player_key,status,first_seen_at,updated_at FROM target.identity_quarantine WHERE identity_quarantine_id=ANY(CAST(:ids AS text[]))"),dict(ids=[q['identity_quarantine_id']for q in queue['records']])).mappings()]
 assert len(after)==queue['requests'];queue['durable_readback_records']=after
coverage=[]
for year in (2023,2024,2025):
 rows=[g for g in result['game_rows']if g['season']==year]
 coverage.append(dict(season=year,defense_games=len(rows),exact_before_totals=sum(g['metrics']['G15-M05']['value']is not None for g in rows),exact_after_totals=sum(g['metrics']['G15-M06']['value']is not None for g in rows),
  source_unknown_reasons=dict(Counter(s for g in rows for s in g['unknown_or_incompatible_reasons']))))
receipt=dict(actual_started_at=read.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=full,selected_ref=sel,cohort_ref=cohort_ref,global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],
 coverage=coverage,native_GSIS_keys=len(GSISkeys),native_PFR_keys=len(PFRkeys),GSIS_identity_status_counts=dict(Counter(p['status']for p in gsis_proofs.values())),PFR_identity_status_counts=dict(Counter(p['status']for p in pfr_proofs.values())),queue=queue,
 source_fetches=0,parent_inflates=0,alias_mutations=0,models=0,evidence_use=result['evidence_use'],pregame_serving_eligible=False)
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2,default=str)+'\n');print(json.dumps({k:v for k,v in receipt.items()if k!='queue'},default=str),flush=True);print(json.dumps(dict(queue_requests=queue['requests'],queue_new=queue['created_new'],queue_existing=queue['existing_unchanged'])),flush=True)
