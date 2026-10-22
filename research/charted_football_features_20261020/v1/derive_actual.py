"""Single coordinated frozen-parent and actual FTN retrospective feature derive."""
from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.charted_football_features import derive_retrospective_charted_features,DEFINITIONS
from backend.app.product_services.defense_context_evidence import _hash
ROOT=Path('research/charted_football_features_20261020/v1')
def save(v):
 raw=json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<32*1024*1024;sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/charted_football_features')/f'{sha}.json';p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb') as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
started=time.monotonic();actual=datetime.now(UTC).isoformat()
parent=json.loads(Path('research/player_opportunity_components_20261019/v1/actual_derivation_current_receipt.json').read_text())['parent_artifact_ref']
proof_ref=json.loads(Path('research/player_effectiveness_components_20261020/v1/actual_derivation_receipt.json').read_text())['full_ref'];raw=Path(proof_ref['path']).read_bytes();assert len(raw)==proof_ref['bytes'] and hashlib.sha256(raw).hexdigest()==proof_ref['sha256'];proofs=json.loads(raw)['provenance']['original_position_evidence']
with Session(engine) as session:
 pbp=session.get(SourceSnapshot,parent['source_snapshot_id']);chart=session.get(SourceSnapshot,'5eafb584-bff0-5dd9-8ffb-9ef921ab1814')
 value=derive_retrospective_charted_features(parent,pbp,chart,actual_read_at=actual,position_evidence=proofs)
value['provenance']['actual_publication_at']=datetime.now(UTC).isoformat();full=save(value)
selected={k:v for k,v in value.items() if k not in {'actor_game_rows','team_game_denominators','defense_game_rows','event_basis','position_facts','coverage','provenance','semantic_sha256'}}
selected['selected_scope']=dict(teams=['SF','WAS'],parent_semantic_sha256=value['semantic_sha256'])
for key in ('actor_game_rows','team_game_denominators','defense_game_rows'):selected[key]=[x for x in value[key] if x['team'] in {'SF','WAS'}]
selected['selected_semantic_sha256']=_hash(selected);selected['provenance']={**value['provenance'],'full_ref':full};selected_ref=save(selected)
coverage={}
for mid in DEFINITIONS:
 rows=value['defense_game_rows'] if mid=='G14-M02' else value['actor_game_rows'];measurements=[r['metrics'][mid] for r in rows if mid in r['metrics']]
 coverage[mid]=dict(rows=len(measurements),exact=sum(m.get('exact_within_log_value',m.get('exact_within_log_mean',m.get('exact_within_log_sum'))) is not None for m in measurements))
r=dict(actual_started_at=actual,actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-started,full_ref=full,selected_ref=selected_ref,global_semantic_sha256=value['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],actor_games=len(value['actor_game_rows']),team_games=len(value['team_game_denominators']),defense_games=len(value['defense_game_rows']),selected_actor_games=len(selected['actor_game_rows']),coverage=coverage,native_join_coverage=value['coverage'],parent_artifact_ref=parent,position_proof_artifact_ref=proof_ref,FTN_snapshot_id='5eafb584-bff0-5dd9-8ffb-9ef921ab1814',producer_code_sha256=value['provenance']['producer_code_sha256'],evidence_use=value['evidence_use'],pregame_serving_eligible=False,models=0,source_fetches=0,consumer_status='Feature-only; all forecast/model/optimizer/serving consumers pending',catalog_status='Pending High review of exact definitions and known-exposure coverage')
(ROOT/'actual_derivation_receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
