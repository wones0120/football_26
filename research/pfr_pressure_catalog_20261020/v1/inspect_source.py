"""Bounded indexed existing-source metadata only: no ingest, fit or name joins."""
from datetime import datetime,UTC
from pathlib import Path
import csv,hashlib,json,math,time,re
import polars as pl
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.services.source_capture import verify_snapshot_artifact
from backend.app.product_services.schedule_context_features import load_schedule_context
from backend.app.product_services.pfr_source_components import validate_pfr_frame
now=datetime.now(UTC);start=time.monotonic();out=Path('research/pfr_pressure_catalog_20261020/v1')
source_path=Path('research/pfr_source_components_20261020/v1/actual_validated_capture_receipt.json');manifest=json.loads(source_path.read_text());reports=[]
with Session(engine) as s:
 snapshot=s.get(SourceSnapshot,'6a346947-eca2-5c0d-abf0-95e52ac72e5b');schedule=load_schedule_context(snapshot,cutoff=now);future=[]
 with Path(snapshot.artifact_path).open(newline='') as f:
  for r in csv.DictReader(f):
   if r['game_type']=='REG' and int(r['season'])==2026 and int(r['week'])>=7 and (r.get('home_qb_id') or r.get('away_qb_id')):
    future.append({k:r.get(k) for k in ('game_id','season','week','game_type','gameday','gametime','weekday','home_team','away_team','home_qb_id','away_qb_id')})
 future_receipt=dict(actual_read_at=now.isoformat(),source=schedule['provenance'],rows=future,source_dictionary='https://raw.githubusercontent.com/nflverse/nflreadr/main/data-raw/dictionary_schedules.csv',status='provider_native_reported_future_starting_QB_fields_unconfirmed_not_pregame_actual_or_active_proof')
 Path('research/workload_kickoff_groups_20261020/v1/native_future_QB_rows.json').write_text(json.dumps(future_receipt,indent=2)+'\n')
 for r in manifest['reports']:
  scope=r['scope']
  if scope['summary_level']!='week' or scope['stat_type']!='pass':continue
  snap=s.get(SourceSnapshot,r['source_snapshot_id']);verify_snapshot_artifact(snap)
  assert snap.content_sha256==r['source_sha256'] and snap.byte_count==r['bytes'] and str(snap.source_uri)==r['source_uri']
  frame=pl.read_parquet(snap.artifact_path);validation=validate_pfr_frame(frame,**scope,max_season=now.year);assert validation['native_grain_valid']
  prior=[row for row in frame.to_dicts() if row['game_type']=='REG' and int(row['season'])*100+int(row['week'])<202607]
  def count(v):return None if v is None or isinstance(v,bool) or not math.isfinite(float(v)) or float(v)<0 or not float(v).is_integer() else int(v)
  pairs=[(count(row.get('times_pressured')),count(row.get('times_sacked'))) for row in prior]
  reports.append(dict(source_snapshot_id=str(snap.snapshot_id),source_sha256=snap.content_sha256,source_uri=snap.source_uri,bytes=snap.byte_count,captured_at=str(snap.captured_at),scope=scope,prior_REG_rows=len(prior),columns=frame.columns,known_pressures=sum(p is not None for p,k in pairs),known_sacks=sum(k is not None for p,k in pairs),known_pairs=sum(p is not None and k is not None for p,k in pairs),sacks_exceed_pressure=sum(p is not None and k is not None and k>p for p,k in pairs),known_pressure_sum=sum(p or 0 for p,k in pairs),known_sack_sum=sum(k or 0 for p,k in pairs),weekly_dropback_components_available={field:field in frame.columns for field in ('pass_attempts','scrambles','times_sacked','times_pressured','times_pressured_pct')}))
receipt=dict(actual_read_at=now.isoformat(),elapsed_seconds=time.monotonic()-start,before_period=202607,source_manifest_path=str(source_path),source_manifest_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),reports=reports,native_future_QB_rows=len(future),source_fetches=0,database_writes=0,models=0,status='source_field_and_native_QB_metadata_only_no_catalog_promotion')
(out/'source_inspection_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(dict(elapsed_seconds=receipt['elapsed_seconds'],PFR_assets=len(reports),prior_REG_rows=sum(r['prior_REG_rows'] for r in reports),sacks_exceed_pressure=sum(r['sacks_exceed_pressure'] for r in reports),future_QB_rows=len(future))))
