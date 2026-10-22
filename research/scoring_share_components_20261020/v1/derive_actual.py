from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.scoring_share_components import derive_retrospective_scoring_shares
from backend.app.product_services.defense_context_evidence import _hash
ROOT=Path('research/scoring_share_components_20261020/v1')
def save(v):
 raw=json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<32*1024*1024;sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/scoring_share_components')/f'{sha}.json';p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb') as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
start=time.monotonic();actual=datetime.now(UTC).isoformat();parent=json.loads(Path('research/player_opportunity_components_20261019/v1/actual_derivation_current_receipt.json').read_text())['parent_artifact_ref']
with Session(engine) as session:value=derive_retrospective_scoring_shares(parent,session.get(SourceSnapshot,parent['source_snapshot_id']),actual_read_at=actual)
value['provenance']['actual_publication_at']=datetime.now(UTC).isoformat();full=save(value)
selected={k:v for k,v in value.items() if k not in {'actor_game_rows','team_game_rows','actor_windows','event_basis','identity_review_requests','semantic_sha256','provenance'}};selected['selected_scope']=dict(teams=['SF','WAS'],parent_semantic_sha256=value['semantic_sha256'])
for key in ('actor_game_rows','team_game_rows','actor_windows','event_basis','identity_review_requests'):selected[key]=[r for r in value[key] if r['team'] in {'SF','WAS'}]
selected['selected_semantic_sha256']=_hash(selected);selected['provenance']={**value['provenance'],'full_ref':full};selected_ref=save(selected)
coverage={}
for mid in value['definitions']:
 rows=value['team_game_rows'] if mid in {'G12-M02','G12-M03'} else value['actor_game_rows'];metrics=[r['metrics'][mid] for r in rows]
 coverage[mid]=dict(rows=len(metrics),exact_ratio=sum(m['exact_within_log_value'] is not None for m in metrics),known_numerator=sum(m['numerator']['exact_within_log_count'] is not None for m in metrics),known_denominator=sum(m['full_team_denominator']['exact_within_log_count'] is not None for m in metrics))
r=dict(actual_started_at=actual,actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=full,selected_ref=selected_ref,global_semantic_sha256=value['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],actor_games=len(value['actor_game_rows']),team_games=len(value['team_game_rows']),actor_windows=len(value['actor_windows']),identity_requests=len(value['identity_review_requests']),selected_actor_games=len(selected['actor_game_rows']),coverage=coverage,parent_artifact_ref=parent,producer_code_sha256=value['provenance']['producer_code_sha256'],evidence_use=value['evidence_use'],pregame_serving_eligible=False,source_fetches=0,models=0,consumer_status='Feature-only; models/optimizer/app consumers pending')
(ROOT/'actual_derivation_receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
