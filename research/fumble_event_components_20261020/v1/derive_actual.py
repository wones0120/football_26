"""One bounded immutable-source CSV read, no parent inflation or source fetch."""
from pathlib import Path
from datetime import datetime,UTC
import hashlib,json,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.fumble_event_components import derive_retrospective_fumble_components
from backend.app.product_services.evaluation_record import digest
root=Path('research/fumble_event_components_20261020/v1');start=time.monotonic();now=datetime.now(UTC)
with Session(engine)as session:
 snapshot=session.get(SourceSnapshot,'79230705-26c3-5cbd-af43-b26c9bb4e1bb')
 result=derive_retrospective_fumble_components(snapshot,before_period=202606,actual_read_at=now)
result['provenance']['actual_publication_at']=datetime.now(UTC).isoformat()
def save(value):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=16*1024*1024
 sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/fumble_event_components')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb')as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
full=save(result);selected={k:v for k,v in result.items()if k not in {'game_rows','team_recovery_rows','fumble_ledger','event_basis','semantic_sha256','provenance'}}
selected['game_rows']=[r for r in result['game_rows']if set(r['game_id'].split('_')[2:])&{'SF','WAS'}]
keys={r['game_id']for r in selected['game_rows']}
selected['team_recovery_rows']=[r for r in result['team_recovery_rows']if r['game_id']in keys]
for field in ('fumble_ledger','event_basis'):selected[field]=[r for r in result[field]if r['game_id']in keys]
selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};sel=save(selected)
receipt=dict(actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=full,selected_ref=sel,
 global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],
 game_rows=len(result['game_rows']),selected_rows=len(selected['game_rows']),scoped_native_rows=len(result['event_basis']),
 positive_known_fumble_plays=sum(r['known_fumble_plays']for r in result['game_rows']),known_single_recoveries=sum(r['known_single_fumble_recoveries']for r in result['game_rows']),
 known_lost=sum(r['known_lost']for r in result['game_rows']),known_retained=sum(r['known_retained']for r in result['game_rows']),
 unknown_recovery_fumble_plays=sum(r['unknown_recovery_fumble_plays']for r in result['game_rows']),
 team_recovery_rows=len(result['team_recovery_rows']),exact_team_recovery_fractions=sum(r['all_reported_fumble_loss_fraction']is not None for r in result['team_recovery_rows']),
 exact_fumble_play_counts=sum(r['exact_fumble_play_count']is not None for r in result['game_rows']),
 exact_incidence_rates=sum(r['fumble_play_incidence']is not None for r in result['game_rows']),
 exact_all_fumble_loss_fractions=sum(r['all_fumble_loss_fraction']is not None for r in result['game_rows']),
 unknown_live_rows=sum(r['unknown_live_eligibility']for r in result['game_rows']),
 evidence_use=result['evidence_use'],pregame_serving_eligible=False,source_fetches=0,database_writes=0,parent_inflates=0,models=0)
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
