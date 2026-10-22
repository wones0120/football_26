from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime,UTC
import json,hashlib,time
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.services.source_capture import SourceCaptureService,verify_snapshot_artifact,DEFAULT_NFLREADPY_LICENSE
from backend.app.product_services.weekly_passing_air_efficiency import load_reviewed_weekly_input
from backend.app.product_services.schedule_context_features import load_schedule_context
from backend.app.product_services.official_absence_source import absence_layout,parse_absence_layout,read_absence_roster_revision,resolve_absence_roster,persist_absence_identity_incidents
ROOT=Path('research/official_absence_path_20261020/v1');start=time.monotonic();now=datetime.now(UTC)
wr=json.loads(Path('research/weekly_effectiveness_catalog_features_20261020/v1/actual_derivation_receipt.json').read_text());weekly_ref=wr['full_ref'];weekly=load_reviewed_weekly_input(weekly_ref,cutoff=now)
with Session(engine) as session:
 schedule=load_schedule_context(session.get(SourceSnapshot,'6a346947-eca2-5c0d-abf0-95e52ac72e5b'),cutoff=now)
 gs=[g for g in schedule['game_rows'] if g['game_id']=='2025_03_DEN_LAC'];assert len(gs)==1;game=gs[0]
 pdf=session.get(SourceSnapshot,'103f7525-dbd3-508f-b80d-4d7ff6053cad');verify_snapshot_artifact(pdf)
 assert (pdf.season,pdf.week,pdf.media_type)==(2025,3,'application/pdf')
 pdf_ref=dict(snapshot_id=str(pdf.snapshot_id),path=pdf.artifact_path,sha256=pdf.content_sha256,bytes=pdf.byte_count,observed_at=pdf.observed_at.isoformat(),captured_at=pdf.captured_at.isoformat(),source_uri=pdf.source_uri)
 layout=absence_layout(Path(pdf.artifact_path).read_bytes());parsed=parse_absence_layout(layout,game,source_sha256=pdf.content_sha256)
if (ROOT/'ROSTER_SOURCE_RECEIPT.json').exists():
 prior=json.loads((ROOT/'ROSTER_SOURCE_RECEIPT.json').read_text());roster_ref=prior['roster_source_ref']
 with Session(engine) as session:
  snapshot=session.get(SourceSnapshot,roster_ref['snapshot_id']);verify_snapshot_artifact(snapshot)
  assert snapshot.content_sha256==roster_ref['sha256'];roster=json.loads(Path(snapshot.artifact_path).read_text())
 source_appends=0
else:
 roster=read_absence_roster_revision(engine,game,cutoff=now)
 with TemporaryDirectory() as directory,Session(engine) as session:
  p=Path(directory)/'roster_attachment_revision_2025_w03.json';p.write_text(json.dumps(roster,sort_keys=True,separators=(',',':'),allow_nan=False))
  cap=SourceCaptureService(session).capture_file(p,source_system='retained_db',dataset='weekly_roster_attachment_revision',season=2025,week=3,slate='offline_feature_inventory',
   source_uri='retained-db://public.raw_nfl_weekly_roster/season=2025/week=3/teams=DEN,LAC',source_license=DEFAULT_NFLREADPY_LICENSE,
   slate_lock_at=datetime(2025,9,21,20,5,tzinfo=UTC),media_type='application/json',row_count=len(roster['rows']),
   metadata=dict(contract=roster['contract'],native_game_id=game['game_id'],team_scope=['DEN','LAC'],original_http_snapshot_claim=False))
  snapshot=cap.snapshot;roster_ref=dict(snapshot_id=str(snapshot.snapshot_id),path=snapshot.artifact_path,sha256=snapshot.content_sha256,bytes=snapshot.byte_count,observed_at=snapshot.observed_at.isoformat(),captured_at=snapshot.captured_at.isoformat(),source_uri=snapshot.source_uri)
 source_appends=1
 (ROOT/'ROSTER_SOURCE_RECEIPT.json').write_text(json.dumps(dict(roster_source_ref=roster_ref,source_snapshot_appends=1,original_provider_snapshot_claim=False),indent=2)+'\n')
derivation_cutoff=datetime.now(UTC)
result=resolve_absence_roster(parsed,roster['rows'],weekly,cutoff=derivation_cutoff)
result['provenance']=dict(original_pdf_ref=pdf_ref,roster_source_ref=roster_ref,weekly_input_ref=weekly_ref,schedule=schedule['provenance'],
 actual_read_at=now.isoformat(),identity_derivation_cutoff=derivation_cutoff.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),
 producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/official_absence_source.py').read_bytes()).hexdigest(),
 original_gamebook_observation_at=None,original_pregame_availability_unknown=True)
raw=json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/official_absence_source')/(sha+'.json');p.parent.mkdir(exist_ok=True)
if p.exists():assert p.read_bytes()==raw
else:
 with p.open('xb') as f:f.write(raw)
 p.chmod(0o444)
ref=dict(path=str(p.resolve()),sha256=sha,bytes=len(raw));source_refs=dict(pdf_sha256=pdf_ref['sha256'],roster_sha256=roster_ref['sha256'],weekly_sha256=weekly_ref['sha256'])
with engine.begin() as connection:queue=persist_absence_identity_incidents(connection,result,source_refs=source_refs)
ids=[r['identity_quarantine_id'] for r in queue['records']]
with engine.connect() as connection:
 readback=[dict(r) for r in connection.execute(text('SELECT identity_quarantine_id,source_record_key,status,first_seen_at,updated_at FROM target.identity_quarantine WHERE identity_quarantine_id=ANY(CAST(:ids AS text[])) ORDER BY identity_quarantine_id'),dict(ids=ids)).mappings()] if ids else []
assert len(readback)==len(ids)
(ROOT/'layout_first_page.txt').write_text(layout)
out=dict(completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,pdf_source_ref=pdf_ref,roster_source_ref=roster_ref,weekly_input_ref=weekly_ref,artifact_ref=ref,
 roster_rows=len(roster['rows']),source_fact_rows=len(result['rows']),ordinary_not_active=sum(r['ordinary_absence_anchor'] for r in result['rows']),
 canonical_rows=sum(r['player_master_id'] is not None for r in result['rows']),offensive_absence_anchors=[r for r in result['rows'] if r['ordinary_absence_anchor'] and r['source_position'] in {'QB','RB','FB','WR','TE'}],
 identity_persistence=queue,identity_readback=[{k:v.isoformat() if isinstance(v,datetime) else v for k,v in r.items()} for r in readback],
 source_snapshot_appends=source_appends,raw_ingest_writes=0,aliases_mutated=0,source_fetches=0,parent_inflations=0,models=0,catalog_ids_completed=[])
(ROOT/'actual_receipt.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in {'offensive_absence_anchors','identity_persistence','identity_readback'}}))
