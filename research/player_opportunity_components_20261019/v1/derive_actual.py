"""One coordinated verified parent load; no fetch, fit, DB write or runtime hook."""
from datetime import datetime,UTC
import hashlib,json,time
from pathlib import Path
from copy import deepcopy
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.player_opportunity_components import derive_retrospective_player_components
start=time.monotonic();cutoff=datetime.now(UTC).isoformat()
handoff=json.loads(Path('research/opportunity_source_capture_20261019/actual/scalar_serving_handoff_receipt.json').read_text());ref=handoff['parent_artifact_ref']
with Session(engine) as session:
 snapshot=session.get(SourceSnapshot,ref['source_snapshot_id']);assert snapshot is not None
 full=derive_retrospective_player_components(ref,snapshot,actual_read_at=cutoff,position_evidence=())
root=Path('artifacts/player_opportunity_components');root.mkdir(parents=True,exist_ok=True)
def freeze(value,bound):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=bound
 sha=hashlib.sha256(raw).hexdigest();path=(root/(sha+'.json')).resolve()
 if path.exists():assert path.read_bytes()==raw
 else:
  with path.open('xb') as handle:handle.write(raw)
 return dict(sha256=sha,path=str(path),bytes=len(raw),version=value['version'],evidence_use=value.get('evidence_use'),pregame_serving_eligible=value.get('pregame_serving_eligible'),semantic_measurements_sha256=value.get('selected_semantic_measurements_sha256') or value['semantic_measurements_sha256'])
publication=dict(actual_publication_at=datetime.now(UTC).isoformat(),actual_started_at=cutoff,parent_artifact_ref=ref,meaning='Postlock offline historical derivation; NOT pregame/current serving or a Monday prediction')
full['provenance']['artifact_publication']=publication;full_ref=freeze(full,16*1024*1024)
selected=deepcopy(full);teams={'SF','WAS'}
for field in ('actor_game_rows','team_denominators','unattributed_events','identity_review_requests'):
 selected[field]=[r for r in full[field] if r['team'] in teams]
selected['teams']=sorted(teams);selected['global_semantic_measurements_sha256']=full['semantic_measurements_sha256']
selected.pop('semantic_measurements_sha256')
semantic={k:v for k,v in selected.items() if k not in {'provenance','global_semantic_measurements_sha256'}}
selected['selected_semantic_measurements_sha256']=hashlib.sha256(json.dumps(semantic,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
selected['provenance']['full_component_ref']=full_ref;selected_ref=freeze(selected,2*1024*1024)
r=dict(status='postlock_descriptive_not_pregame_or_serving',source_snapshot_id=ref['source_snapshot_id'],parent_artifact_ref=ref,
 full_ref=full_ref,selected_ref=selected_ref,full_actor_games=len(full['actor_game_rows']),selected_actor_games=len(selected['actor_game_rows']),
 full_team_games=len(full['team_denominators']),selected_team_games=len(selected['team_denominators']),identity_requests=len(full['identity_review_requests']),
 unattributed_events=len(full['unattributed_events']),position_scope='No prior-game position proof supplied; generic passer/rusher/receiver measurements only, no QB/RB-specific catalog completion',
 elapsed_seconds=time.monotonic()-start,source_fetched_again=False,fits=0,database_writes=0,actual_current_consumers=[],
 next_consumer='Offline research/model-contract validation only; require_component_use rejects pregame/current source registration and forecast/scenario serving. Future operational source must have a separately valid decision/source contract.',
 limitations=full['limitations'])
Path('research/player_opportunity_components_20261019/v1/actual_derivation_current_receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
