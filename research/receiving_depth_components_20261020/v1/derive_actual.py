"""One coordinated frozen-parent retrospective derivation; no fetch/fit/DBwrites."""
from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.receiving_depth_components import derive_retrospective_receiving_depth


def main():
 start=time.monotonic();actual=datetime.now(UTC).isoformat();directory=Path('research/receiving_depth_components_20261020/v1')
 ref=json.loads(Path('research/player_opportunity_components_20261019/v1/actual_derivation_current_receipt.json').read_text())['parent_artifact_ref']
 with Session(engine) as session:
  snapshot=session.get(SourceSnapshot,ref['source_snapshot_id']);assert snapshot is not None
  full=derive_retrospective_receiving_depth(ref,snapshot,actual_read_at=actual)
 full['provenance']['actual_publication_at']=datetime.now(UTC).isoformat()
 destination=Path('artifacts/receiving_depth_components');destination.mkdir(parents=True,exist_ok=True)
 def save(value,bound):
  raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=bound;sha=hashlib.sha256(raw).hexdigest();path=(destination/(sha+'.json')).resolve()
  if path.exists():assert path.read_bytes()==raw
  else:
   with path.open('xb') as stream:stream.write(raw)
  return dict(path=str(path),sha256=sha,bytes=len(raw),semantic_measurements_sha256=value.get('selected_semantic_measurements_sha256') or value['semantic_measurements_sha256'],evidence_use=value['evidence_use'],pregame_serving_eligible=False)
 full_ref=save(full,16*1024*1024)
 selected={k:v for k,v in full.items() if k not in {'actor_game_rows','full_team_denominators','identity_review_requests','unattributed_events','provenance','semantic_measurements_sha256'}};selected['teams']=['SF','WAS']
 for field in ('actor_game_rows','full_team_denominators','identity_review_requests','unattributed_events'):selected[field]=[r for r in full[field] if r['team'] in selected['teams']]
 selected['selected_semantic_measurements_sha256']=hashlib.sha256(json.dumps(selected,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
 selected['provenance']={**full['provenance'],'full_ref':full_ref,'global_semantic_measurements_sha256':full['semantic_measurements_sha256']};selected_ref=save(selected,2*1024*1024)
 for team in full['full_team_denominators']:
  assert sum(team['buckets'].values())==team['known_targets']
 coverage={metric:dict(actor_rows=len(full['actor_game_rows']),exact_share_rows=sum(r['metrics'][metric]['exact_within_log_share'] is not None for r in full['actor_game_rows'])) for metric in full['definitions']}
 receipt=dict(status='Actual retrospective source-measured G10M07–09 air-depth feature variants; High review pending',full_ref=full_ref,selected_ref=selected_ref,full_actor_games=len(full['actor_game_rows']),selected_actor_games=len(selected['actor_game_rows']),full_team_games=len(full['full_team_denominators']),selected_team_games=len(selected['full_team_denominators']),coverage=coverage,identity_requests=len(full['identity_review_requests']),unattributed_events=len(full['unattributed_events']),team_partition_conservation=True,parent_artifact_ref=ref,actual_started_at=actual,actual_publication_at=full['provenance']['actual_publication_at'],elapsed_seconds=time.monotonic()-start,fits=0,source_fetches=0,database_writes=0,catalog_completion_claim=False,model_optimizer_consumers='Deferred/pending under features-only priority')
 (directory/'actual_derivation_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))

if __name__=='__main__':main()
