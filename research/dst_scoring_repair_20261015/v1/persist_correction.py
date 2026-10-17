"""Append source/correction snapshots only; never update matrix or projections."""
from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,httpx
from sqlalchemy import text
from sqlalchemy.orm import Session
from backend.app.product_services.optimizer import OptimizerService,_json_safe
from backend.app.services.source_capture import SourceCaptureService
P=Path(__file__).resolve().parent;s=OptimizerService();correction=json.load(open(P/'corrected_dst_matrix.json'));books=json.load(open(P/'official_gamebook_checks.json'));assert len(books)==81 and all(r['status']=='verified' for r in books)
# Read primary current DFS guide; actual coefficients also have contract tests.
file=P/'draftkings_classic_scoring_guide.html'
if not file.exists():
 u='https://dknetwork.draftkings.com/2025/08/27/nfl-dfs-beginners-guide-draftkings/';r=httpx.get(u,follow_redirects=True,timeout=45);r.raise_for_status();file.write_bytes(r.content);(P/'draftkings_classic_scoring_guide.capture.json').write_text(json.dumps(dict(uri=u,captured_at=datetime.now(UTC).isoformat(),sha256=hashlib.sha256(r.content).hexdigest(),headers=dict(r.headers)),indent=2)+'\n')
with s.engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'))
 ids=sorted({r['player_master_id'] for r in correction['rows']});masters=[dict(r) for r in c.execute(text('SELECT * FROM public.player_master WHERE player_master_id=ANY(:ids)'),{'ids':ids}).mappings()];assert len(masters)==32;(P/'canonical_dst_identity.json').write_text(json.dumps(_json_safe(masters),indent=2)+'\n')
records=[]
with Session(s.engine) as session:
 for year in [2024,2025,2026]:
  source=P/f'play_by_play_{year}.parquet';meta=json.load(open(P/('pbp_capture.json' if year==2026 else f'play_by_play_{year}.parquet.capture.json')))
  cap=SourceCaptureService(session).capture_file(source,source_system='nflverse',dataset='dst_scoring_pbp_audit',season=year,week=5 if year==2026 else 18,slate='DST_SCORING_RESEARCH',source_uri=meta['uri'],source_license='nflverse public play-by-play release; retained for research scoring audit',effective_at=datetime.fromisoformat(meta['captured_at']),observation_basis='capture_clock',media_type='application/vnd.apache.parquet',metadata={'research_only':True,'no_historical_availability_claim':True,'scoring_contract':correction['contract_id']})
  records.append(dict(kind='raw_pbp',season=year,snapshot_id=str(cap.snapshot.snapshot_id),sha256=cap.snapshot.content_sha256,artifact_path=cap.snapshot.artifact_path))
 source=P/'corrected_dst_matrix.json';cap=SourceCaptureService(session).capture_file(source,source_system='football26_research',dataset='dst_label_correction_version',season=2026,week=5,slate='DST_SCORING_RESEARCH',source_uri='football26://research/dst_scoring_repair_20261015/v1/corrected_dst_matrix.json',source_license='Derived research correction with linked NFL/nflverse source evidence; not live activated',effective_at=datetime.now(UTC),observation_basis='versioned_research_correction',media_type='application/json',row_count=len(correction['rows']),metadata={'research_only':True,'logical_dataset_sha256':correction['sha256'],'original_dataset_sha256':correction['original_dataset_sha256'],'raw_source_snapshot_ids':[r['snapshot_id'] for r in records],'gamebook_checks_sha256':hashlib.sha256((P/'official_gamebook_checks.json').read_bytes()).hexdigest(),'live_projection_activation':False,'matrix_overwrite':False})
 records.append(dict(kind='corrected_dataset',snapshot_id=str(cap.snapshot.snapshot_id),sha256=cap.snapshot.content_sha256,artifact_path=cap.snapshot.artifact_path,logical_dataset_sha256=correction['sha256']))
 # Preserve the official independent verification index as a distinct record.
 cap=SourceCaptureService(session).capture_file(P/'gamebook_manifest.json',source_system='nfl_official',dataset='dst_correction_gamebook_index',season=2026,week=5,slate='DST_SCORING_RESEARCH',source_uri='football26://official-gamebook-capture-index',source_license='Official NFL gamebooks retained for source audit; no redistribution',effective_at=datetime.now(UTC),observation_basis='capture_clock',media_type='application/json',row_count=81,metadata={'research_only':True,'scoring_verification_file':'official_gamebook_checks.json'})
 records.append(dict(kind='official_gamebook_index',snapshot_id=str(cap.snapshot.snapshot_id),sha256=cap.snapshot.content_sha256,artifact_path=cap.snapshot.artifact_path))
(P/'persistence_receipt.json').write_text(json.dumps(dict(recorded_at=datetime.now(UTC).isoformat(),records=records,live_projection_changes=False,original_matrix_overwrite=False),indent=2)+'\n');print(json.dumps(records,indent=2),flush=True)
# Fresh read of exact original Main active pointer/values; Morning is separate.
with s.engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'));checks={}
 for name in ['live_main_run','live_main_values']:
  old=json.load(open(P/(name+'.json')));rows=_json_safe([dict(r) for r in c.execute(text(old['query'])).mappings()]);assert rows==old['rows'],name;checks[name]=dict(unchanged=True,rows=len(rows),sha256=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest())
(P/'live_unchanged.json').write_text(json.dumps(dict(verified_at=datetime.now(UTC).isoformat(),checks=checks),indent=2)+'\n');print('Main active pointer and 288 persisted projection rows exactly unchanged',flush=True)
