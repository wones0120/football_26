from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.offensive_environment_catalog import load_reviewed_environment_context
from backend.app.product_services.offensive_redzone_stalls import build_offensive_redzone_stalls
from backend.app.product_services import game_clock_pace_catalog as producer
from backend.app.product_services.evaluation_record import digest
root=Path('research/offensive_redzone_stalls_20261020/v1');now=datetime.now(UTC);start=time.monotonic()
env=json.loads(Path('research/environment_context_evidence_20261019/v1/actual_combined_receipt.json').read_text())
with Session(engine) as session:
 snapshot=session.get(SourceSnapshot,env['parent_artifact_ref']['source_snapshot_id']);verified=load_reviewed_environment_context(env['full_context'],snapshot,actual_read_at=now)
ref=json.loads(Path('research/game_clock_pace_catalog_20261020/v1/actual_receipt.json').read_text())['native_redzone_source_ref'];p=Path(ref['path']).resolve();raw=p.read_bytes();assert p.parent==Path('artifacts/game_clock_pace_catalog').resolve() and p.name==ref['sha256']+'.json' and len(raw)==ref['bytes'] and hashlib.sha256(raw).hexdigest()==ref['sha256'];source=json.loads(raw)
assert source['provenance']['producer_code_sha256']==hashlib.sha256(Path(producer.__file__).read_bytes()).hexdigest() and source['provenance']['source']['snapshot_id']==str(snapshot.snapshot_id) and source['provenance']['source']['content_sha256']==snapshot.content_sha256 and source['provenance']['event_receipt_sha256']==env['parent_artifact_ref']['event_receipt_sha256']
result=build_offensive_redzone_stalls(source,before_period=source['before_period']);result['provenance'].update(immutable_input_ref=ref,authenticated_intake=verified['provenance'],actual_read_at=now.isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),catalog_producer_sha256=hashlib.sha256(Path('backend/app/product_services/offensive_redzone_stalls.py').read_bytes()).hexdigest())
def save(v):
 raw=json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/offensive_redzone_stalls')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb') as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
full=save(result);selected={k:v for k,v in result.items() if k not in {'game_rows','team_windows','semantic_sha256','provenance'}};selected['game_rows']=[r for r in result['game_rows'] if r['team'] in {'SF','WAS'}];selected['team_windows']=[r for r in result['team_windows'] if r['team'] in {'SF','WAS'}];selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};sel=save(selected)
receipt=dict(actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=full,selected_ref=sel,input_ref=ref,game_rows=len(result['game_rows']),selected_rows=len(selected['game_rows']),team_windows=len(result['team_windows']),known_exact=sum(r['metrics']['G23-M06']['value'] is not None for r in result['game_rows']),totals={k:sum(r['metrics']['G23-M06'][k] for r in result['game_rows']) for k in ('observed_entered_drives','known_stall_drives','known_touchdown_drives','unknown_terminal_outcomes','unknown_entry_eligibility','entry_events_missing_native_drive')},global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],source_fetches=0,models=0,parent_inflates=0,evidence_use=result['evidence_use'])
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
