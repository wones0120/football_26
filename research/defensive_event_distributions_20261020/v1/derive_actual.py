"""One explicit retrospective source load, no training/current-serving path."""
from pathlib import Path
from datetime import datetime,UTC
import hashlib,json,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.defensive_event_distributions import derive_retrospective_defensive_events,DEFINITIONS
from backend.app.product_services.evaluation_record import digest
root=Path('research/defensive_event_distributions_20261020/v1');start=time.monotonic();now=datetime.now(UTC)
parent_ref=json.loads(Path('research/environment_context_evidence_20261019/v1/actual_combined_receipt.json').read_text())['parent_artifact_ref']
with Session(engine) as session:
 snapshot=session.get(SourceSnapshot,parent_ref['source_snapshot_id'])
 result=derive_retrospective_defensive_events(parent_ref,snapshot,actual_read_at=now)
result['provenance']['actual_publication_at']=datetime.now(UTC).isoformat()
def save(value):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=16*1024*1024
 sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/defensive_event_distributions')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb') as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
full=save(result)
selected={k:v for k,v in result.items() if k not in {'game_rows','team_distributions','event_basis','semantic_sha256','provenance'}}
selected['game_rows']=[r for r in result['game_rows'] if r['defense_team']in {'SF','WAS'}]
selected['team_distributions']=[r for r in result['team_distributions'] if r['defense_team']in {'SF','WAS'}]
keys={(r['game_id'],r['offense_team']) for r in selected['game_rows']}
selected['event_basis']=[r for r in result['event_basis'] if (r['game_id'],r['offense'])in keys]
selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};sel=save(selected)
receipt=dict(actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=full,selected_ref=sel,
 source_parent_ref=parent_ref,game_rows=len(result['game_rows']),selected_rows=len(selected['game_rows']),team_profiles=len(result['team_distributions']),
 source_event_rows=len(result['event_basis']),coverage={mid:dict(exact_pairs=sum(r['metrics'][mid]['exact_observed_event_count']is not None for r in result['game_rows']),
 unknown_pairs=sum(r['metrics'][mid]['exact_observed_event_count']is None for r in result['game_rows']),
 known_event_lower_bound=sum(r['metrics'][mid]['known_event_count'] for r in result['game_rows']),
 known_exposure_lower_bound=sum(r['metrics'][mid]['known_exposure'] for r in result['game_rows'])) for mid in DEFINITIONS},
 global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],
 evidence_use=result['evidence_use'],pregame_serving_eligible=False,source_fetches=0,database_writes=0,parent_inflates=1,models=0)
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
