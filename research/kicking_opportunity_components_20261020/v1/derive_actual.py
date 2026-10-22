from datetime import datetime,UTC
from pathlib import Path
from collections import defaultdict
import json,hashlib,time
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import PlayerAlias,SourceSnapshot
from backend.app.product_services.kicking_opportunity_components import derive_retrospective_kicking_components
from backend.app.product_services.defense_context_evidence import _hash
ROOT=Path('research/kicking_opportunity_components_20261020/v1')
def save(v):
 raw=json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<16*1024*1024;sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/kicking_opportunity_components')/f'{sha}.json';p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb') as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
start=time.monotonic();actual=datetime.now(UTC).isoformat();parent=json.loads(Path('research/player_opportunity_components_20261019/v1/actual_derivation_current_receipt.json').read_text())['parent_artifact_ref']
with Session(engine) as session:
 aliases=defaultdict(set)
 for native,pid in session.execute(select(PlayerAlias.source_key,PlayerAlias.player_master_id).where(PlayerAlias.source_system=='nflreadpy')):
  if native.startswith('00-'):aliases[native].add(str(pid))
 ids={k:next(iter(v)) for k,v in aliases.items() if len(v)==1};snapshot=session.get(SourceSnapshot,parent['source_snapshot_id'])
 value=derive_retrospective_kicking_components(parent,snapshot,actual_read_at=actual,canonical_ids=ids)
value['provenance']['actual_publication_at']=datetime.now(UTC).isoformat();full=save(value)
selected={k:v for k,v in value.items() if k not in {'actor_game_rows','team_game_rows','event_basis','identity_review_requests','semantic_sha256','provenance'}};selected['selected_scope']=dict(teams=['SF','WAS'],parent_semantic_sha256=value['semantic_sha256'])
for key in ('actor_game_rows','team_game_rows','event_basis','identity_review_requests'):selected[key]=[r for r in value[key] if r['team'] in {'SF','WAS'}]
selected['selected_semantic_sha256']=_hash(selected);selected['provenance']={**value['provenance'],'full_ref':full};selection=save(selected)
coverage={m:dict(actor_games=len(value['actor_game_rows']),exact=sum((r['metrics'][m]['exact_attempts'] is not None) if m in {'G23-M01','G23-M04'} else all(b['exact_attempts'] is not None for b in r['metrics'][m]['distance_buckets'].values()) for r in value['actor_game_rows'])) for m in value['definitions']}
r=dict(actual_started_at=actual,actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=full,selected_ref=selection,global_semantic_sha256=value['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],actor_games=len(value['actor_game_rows']),selected_actor_games=len(selected['actor_game_rows']),team_games=len(value['team_game_rows']),canonical_attached=sum(r['player_master_id'] is not None for r in value['actor_game_rows']),identity_requests=len(value['identity_review_requests']),ambiguous_alias_keys=sum(len(v)>1 for v in aliases.values()),coverage=coverage,no_play_relevant_unknown=sum(r['derived_no_play'] is None for r in value['event_basis']),raw_no_play_key_absent=sum(not r['no_play_key_present'] for r in value['event_basis']),native_classification_certified_events=sum(r['nullification_basis']=='verified_source_exclusive_native_kick_classes' for r in value['event_basis']),unknown_no_play_known_attempts=sum(r['derived_no_play'] is None and (r['FG'] is True or r['XP'] is True) for r in value['event_basis']),parent_artifact_ref=parent,producer_code_sha256=value['provenance']['producer_code_sha256'],evidence_use=value['evidence_use'],pregame_serving_eligible=False,source_fetches=0,models=0,consumer_status='Feature-only; all model/optimizer/serving consumers pending')
(ROOT/'actual_derivation_receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
