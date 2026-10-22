"""One primary NFL original PDF capture, immutable source record and native measurement."""
from pathlib import Path
from datetime import datetime,UTC
from zoneinfo import ZoneInfo
import csv,json,hashlib,time
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.services.source_capture import SourceCaptureService
from backend.app.product_services.schedule_context_features import load_schedule_context
from backend.app.product_services.gamebook_weather import capture_gamebook_weather,load_gamebook_temperature,first_page_text

def main():
    root=Path('research/gamebook_weather_20261020/v1');cfg=json.loads((root/'source_config.json').read_text());start=time.monotonic();requested=datetime.now(UTC).isoformat()
    with Session(engine) as session:
        source=session.get(SourceSnapshot,cfg['schedule_snapshot_id']);assert source is not None
        schedule=load_schedule_context(source,cutoff=requested)
        with Path(source.artifact_path).open(newline='') as stream:rawrows=[r for r in csv.DictReader(stream) if r['game_id']==cfg['native_game_id']]
        assert len(rawrows)==1;native=rawrows[0];lock=datetime.fromisoformat(native['gameday']+'T'+native['gametime']).replace(tzinfo=ZoneInfo('America/New_York')).astimezone(UTC)
        prior=list(session.scalars(select(SourceSnapshot).where(SourceSnapshot.source_system=='nfl_official_gamebook',SourceSnapshot.dataset=='game_summary',SourceSnapshot.source_uri==cfg['uri'],SourceSnapshot.season==int(native['season']),SourceSnapshot.week==int(native['week']))))
        (root/'existing_source_inventory.json').write_text(json.dumps(dict(actual_checked_at=requested,source_uri=cfg['uri'],snapshots=[dict(snapshot_id=str(r.snapshot_id),content_sha256=r.content_sha256,captured_at=str(r.captured_at)) for r in prior]),indent=2)+'\n')
        if len(prior)==1:snapshot=prior[0];created=False
        else:
            captured=capture_gamebook_weather(SourceCaptureService(session),uri=cfg['uri'],season=int(native['season']),week=int(native['week']),slate_lock_at=lock);snapshot=captured.snapshot;created=captured.created
        actual=datetime.now(UTC).isoformat();result=load_gamebook_temperature(snapshot,schedule,before_period=cfg['before_period'],actual_read_at=actual)
        assert result['game_id']==cfg['native_game_id']
        reported=result['reported_weather']['reported_venue'];scheduled=native.get('stadium') or None
        if reported and scheduled:assert reported.casefold().strip()==scheduled.casefold().strip()
        result['provenance']['venue_corroboration']=dict(source_reported=reported,schedule_reported=scheduled,status='exact_casefold_match' if reported and scheduled else 'unknown',schedule_raw_row_sha256=hashlib.sha256(json.dumps(native,sort_keys=True).encode()).hexdigest())
        result['provenance']['actual_publication_at']=datetime.now(UTC).isoformat()
        text,pages=first_page_text(Path(snapshot.artifact_path).read_bytes());(root/'original_first_page.txt').write_text(text)
        source_ref=dict(snapshot_id=str(snapshot.snapshot_id),path=snapshot.artifact_path,sha256=snapshot.content_sha256,bytes=snapshot.byte_count,manifest_path=snapshot.manifest_path,source_uri=snapshot.source_uri,source_captured_at=str(snapshot.captured_at),source_observed_at=str(snapshot.observed_at),pdf_pages=pages)
    raw=json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(raw).hexdigest();folder=Path('artifacts/gamebook_weather');folder.mkdir(parents=True,exist_ok=True);path=(folder/(sha+'.json')).resolve()
    if path.exists():assert path.read_bytes()==raw
    else:
        with path.open('xb') as f:f.write(raw)
    receipt=dict(full_ref=dict(path=str(path),sha256=sha,bytes=len(raw)),source_ref=source_ref,schedule_snapshot_id=cfg['schedule_snapshot_id'],source_created=created,native_game_id=result['game_id'],reported_weather=result['reported_weather'],venue_corroboration=result['provenance']['venue_corroboration'],actual_request_started_at=requested,actual_read_at=actual,actual_publication_at=result['provenance']['actual_publication_at'],elapsed_seconds=time.monotonic()-start,source_fetches=0 if len(prior)==1 else 1,source_snapshot_append=int(created),alias_or_player_writes=0,models=0,review_status='pending actual visual QA and High')
    (root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
