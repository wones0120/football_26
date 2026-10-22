"""One authenticated CSV stream; no expanded event parent or provider request."""
from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.return_touchdown_components import derive_retrospective_return_components,CHANNELS
from backend.app.product_services.evaluation_record import digest
root=Path('research/return_touchdown_components_20261020/v1');start=time.monotonic();read=datetime.now(UTC)
with Session(engine)as session:
 snapshot=session.get(SourceSnapshot,'79230705-26c3-5cbd-af43-b26c9bb4e1bb')
 result=derive_retrospective_return_components(snapshot,before_period=202606,actual_read_at=read)
result['provenance']['actual_publication_at']=datetime.now(UTC).isoformat()
def save(v):
 raw=json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=16*1024*1024
 sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/return_touchdown_components')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb')as stream:stream.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
full=save(result)
selected={k:v for k,v in result.items()if k not in {'team_game_rows','team_distributions','event_ledger','semantic_sha256','provenance'}}
selected['team_game_rows']=[r for r in result['team_game_rows']if r['team']in {'SF','WAS'}]
selected['team_distributions']=[r for r in result['team_distributions']if r['team']in {'SF','WAS'}]
games={r['game_id']for r in selected['team_game_rows']};selected['event_ledger']=[r for r in result['event_ledger']if r['game_id']in games]
selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};sel=save(selected)
rows=result['team_game_rows'];receipt=dict(actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=full,selected_ref=sel,
 global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],team_games=len(rows),selected_rows=len(selected['team_game_rows']),
 known_physical_return_TDs=sum(r['known_physical_return_TDs']for r in rows),exact_team_TD_counts=sum(r['exact_physical_return_TDs']is not None for r in rows),
 channel_counts={c:dict(known_exposures=sum(r['channels'][c]['known_exposures']for r in rows),unknown_membership=sum(r['channels'][c]['unknown_exposure_membership']for r in rows),
  exact_team_counts=sum(r['channels'][c]['exact_exposures']is not None for r in rows),known_matched_TDs=sum(r['channels'][c]['known_matched_return_TDs']for r in rows))for c in CHANNELS},
 mechanism_scope_gaps=result['mechanism_scope_gaps'],evidence_use=result['evidence_use'],pregame_serving_eligible=False,source_fetches=0,parent_inflates=0,models=0,database_writes=0)
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
