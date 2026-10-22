"""One coordinated retrospective source-result derivation, no fit/fetch/DBwrites."""
from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time,csv
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.offensive_line_context_components import derive_retrospective_offensive_line_context


def main():
 start=time.monotonic();actual=datetime.now(UTC).isoformat();directory=Path('research/offensive_line_context_components_20261020/v1')
 ref=json.loads(Path('research/player_opportunity_components_20261019/v1/actual_derivation_current_receipt.json').read_text())['parent_artifact_ref']
 with Session(engine) as session:
  snapshot=session.get(SourceSnapshot,ref['source_snapshot_id']);assert snapshot is not None
  full=derive_retrospective_offensive_line_context(ref,snapshot,actual_read_at=actual)
 full['provenance']['actual_publication_at']=datetime.now(UTC).isoformat();destination=Path('artifacts/offensive_line_context_components');destination.mkdir(parents=True,exist_ok=True)
 def save(value):
  raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=2*1024*1024;sha=hashlib.sha256(raw).hexdigest();path=(destination/(sha+'.json')).resolve()
  if path.exists():assert path.read_bytes()==raw
  else:
   with path.open('xb') as stream:stream.write(raw)
  return dict(path=str(path),sha256=sha,bytes=len(raw),semantic_measurements_sha256=value.get('selected_semantic_measurements_sha256') or value['semantic_measurements_sha256'],evidence_use=value['evidence_use'],pregame_serving_eligible=False)
 full_ref=save(full);selected={k:v for k,v in full.items() if k not in {'team_game_rows','team_windows','provenance','semantic_measurements_sha256'}};selected['teams']=['SF','WAS']
 for field in ('team_game_rows','team_windows'):selected[field]=[r for r in full[field] if r['offense_team'] in selected['teams']]
 selected['selected_semantic_measurements_sha256']=hashlib.sha256(json.dumps(selected,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest();selected['provenance']={**full['provenance'],'full_ref':full_ref,'global_semantic_measurements_sha256':full['semantic_measurements_sha256']};selected_ref=save(selected)
 coverage={m:dict(team_game_rows=len(full['team_game_rows']),known_sample_rows=sum(r['metrics'][m]['observed_known_mean'] is not None for r in full['team_game_rows']),exact_rows=sum(r['metrics'][m]['all_eligible_mean'] is not None for r in full['team_game_rows'])) for m in full['definitions'] if m!='G13-M10'}
 directions={d:dict(known_eligible=sum(r['direction_success'][d]['eligible_events'] for r in full['team_game_rows']),unknown_eligibility=sum(r['direction_success'][d]['unknown_eligibility_events'] for r in full['team_game_rows']),unknown_outcome=sum(r['direction_success'][d]['unknown_outcome_events'] for r in full['team_game_rows'])) for d in ('left','middle','right','unknown')}
 receipt=dict(status='Actual retrospective G13 source-result variants; review pending',full_ref=full_ref,selected_ref=selected_ref,full_team_games=len(full['team_game_rows']),full_team_windows=len(full['team_windows']),selected_team_games=len(selected['team_game_rows']),coverage=coverage,directional_coverage=directions,parent_artifact_ref=ref,actual_read_at=actual,actual_publication_at=full['provenance']['actual_publication_at'],elapsed_seconds=time.monotonic()-start,fits=0,source_fetches=0,database_writes=0,model_optimizer_consumers='Deferred under features-only priority')
 (directory/'actual_derivation_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))

if __name__=='__main__':main()
