"""One indexed CSV + authenticated compact original-drive/order/fumble parents."""
from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from collections import Counter
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.turnover_drive_start_context import derive_retrospective_drive_starts
from backend.app.product_services.evaluation_record import digest
root=Path('research/turnover_drive_starts_20261020/v1');start=time.monotonic();read=datetime.now(UTC)
receipts={k:json.loads(Path(p).read_text())for k,p in dict(
 original='research/drive_start_context_20261020/v1/actual_receipt.json',
 order='research/game_clock_pace_catalog_20261020/v1/actual_receipt.json',
 fumble='research/fumble_event_components_20261020/v1/actual_receipt.json').items()}
with Session(engine)as session:
 snapshot=session.get(SourceSnapshot,'79230705-26c3-5cbd-af43-b26c9bb4e1bb')
 result=derive_retrospective_drive_starts(snapshot,receipts['original']['full_ref'],receipts['order']['native_order_map_ref'],receipts['fumble']['full_ref'],order_published_at=receipts['order']['actual_completed_at'],actual_read_at=read)
result['provenance']['actual_publication_at']=datetime.now(UTC).isoformat()
def save(value):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=16*1024*1024
 sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/turnover_drive_start_context')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb')as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
full=save(result);selected={k:v for k,v in result.items()if k not in{'game_rows','profiles','censored_giveaway_anchors','semantic_sha256','provenance'}}
selected['game_rows']=[g for g in result['game_rows']if g['opponent_defense']in{'SF','WAS'}];selected['profiles']=[p for p in result['profiles']if p['defense']in{'SF','WAS'}]
gids={g['game_id']for g in selected['game_rows']};selected['censored_giveaway_anchors']=[r for r in result['censored_giveaway_anchors']if r['game_id']in gids]
selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};sel=save(selected)
drives=[d for g in result['game_rows']for d in g['drives']]
r=dict(actual_started_at=read.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=full,selected_ref=sel,
 global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],team_games=len(result['game_rows']),profiles=len(result['profiles']),physical_original_drives=len(drives),
 selected_team_games=len(selected['game_rows']),class_counts=dict(Counter(str(d['classification'])for d in drives)),unknown_class_reasons=dict(Counter(d['acquisition']['reason']for d in drives if d['classification']is None)),
 normal_subclasses=dict(Counter(d['acquisition']['kind']for d in drives if d['classification']=='non_giveaway')),
 exact_game_contrasts=sum(g['metrics']['giveaway_minus_non_giveaway_start_yardline100']is not None for g in result['game_rows']),
 exact_team_contrasts=sum(p['metrics']['giveaway_minus_non_giveaway_start_yardline100']is not None for p in result['profiles']),
 known_sample_game_contrasts=sum(g['metrics']['known_sample_difference']is not None for g in result['game_rows']),known_sample_team_contrasts=sum(p['metrics']['known_sample_difference']is not None for p in result['profiles']),
 censored_giveaway_anchors=len(result['censored_giveaway_anchors']),source_fetches=0,parent_inflates=0,database_writes=0,alias_reads=0,models=0,evidence_use=result['evidence_use'],pregame_serving_eligible=False)
(root/'actual_receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2),flush=True)
