from datetime import datetime,UTC
from pathlib import Path
import hashlib,json,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.redzone_disruption_features import derive_redzone_disruptions
from backend.app.product_services.evaluation_record import digest
R=Path('research/redzone_disruption_features_20261020/v1');now=datetime.now(UTC);start=time.monotonic()
refs={key:json.loads(Path(f'research/{folder}_20261020/v1/actual_receipt.json').read_text())['full_ref'] for key,folder in [('defense','defensive_event_distributions'),('offense','explosive_touchdown_features'),('fumbles','fumble_event_components')]}
with Session(engine) as s:result=derive_redzone_disruptions(refs,s.get(SourceSnapshot,'79230705-26c3-5cbd-af43-b26c9bb4e1bb'),actual_read_at=now)
result['provenance']['actual_publication_at']=datetime.now(UTC).isoformat()
def save(v):
 raw=json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=8*1024*1024;sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/redzone_disruption_features')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb') as f:f.write(raw)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
full=save(result);selected={k:v for k,v in result.items() if k not in {'game_rows','event_basis','provenance','semantic_sha256'}}
for field in ('game_rows','event_basis'):selected[field]=[r for r in result[field] if r['team'] in {'SF','WAS'}]
selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};sl=save(selected)
coverage={name:dict(exact_game_rates=sum(r['metrics'][name]['value'] is not None for r in result['game_rows']),known_events=sum(r['metrics'][name]['known_events'] for r in result['game_rows']),known_exposures=sum(r['metrics'][name]['known_exposures'] for r in result['game_rows']),unknown_exposures=sum(r['metrics'][name]['unknown_exposures'] for r in result['game_rows']),unknown_outcomes=sum(r['metrics'][name]['unknown_outcomes'] for r in result['game_rows'])) for name in ['sack_per_dropback','interception_per_pass','offense_fumble_loss_per_snap','turnover_event_per_snap']}
r=dict(full_ref=full,selected_ref=sl,input_refs=refs,coverage=coverage,team_games=len(result['game_rows']),selected_team_games=len(selected['game_rows']),source_events=len(result['event_basis']),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,parent_inflates=0,source_fetches=0,model_fits=0,database_writes=0,evidence_use=result['evidence_use'])
(R/'actual_receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
