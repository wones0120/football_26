"""One indexed native CSV read, official-inclusive inside-five rushing outcomes."""
from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.inside_five_rushing_allowed import derive_retrospective_inside_five_rushing_allowed
from backend.app.product_services.evaluation_record import digest
root=Path('research/inside_five_rushing_allowed_20261020/v1');start=time.monotonic();read=datetime.now(UTC)
with Session(engine)as session:
 snapshot=session.get(SourceSnapshot,'79230705-26c3-5cbd-af43-b26c9bb4e1bb')
 result=derive_retrospective_inside_five_rushing_allowed(snapshot,before_period=202606,actual_read_at=read)
result['provenance']['actual_publication_at']=datetime.now(UTC).isoformat()
def save(value):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=16*1024*1024
 sha=hashlib.sha256(raw).hexdigest();path=Path('artifacts/inside_five_rushing_allowed')/(sha+'.json');path.parent.mkdir(exist_ok=True)
 if path.exists():assert path.read_bytes()==raw
 else:
  with path.open('xb')as stream:stream.write(raw)
  path.chmod(0o444)
 return dict(path=str(path.resolve()),sha256=sha,bytes=len(raw))
full=save(result);selected={k:v for k,v in result.items()if k not in{'team_game_rows','profiles','event_basis','semantic_sha256','provenance'}}
selected['team_game_rows']=[r for r in result['team_game_rows']if r['defense']in{'SF','WAS'}];selected['profiles']=[r for r in result['profiles']if r['defense']in{'SF','WAS'}]
games={r['game_id']for r in selected['team_game_rows']};selected['event_basis']=[e for e in result['event_basis']if e['game_id']in games]
selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};slice_ref=save(selected);rows=result['team_game_rows']
receipt=dict(actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=full,selected_ref=slice_ref,
 global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],team_games=len(rows),selected_rows=len(selected['team_game_rows']),
 known_inside5_rush_lower_bound=sum(r['known_eligible_rush_lower_bound']for r in rows),known_inside5_TD_lower_bound=sum(r['known_td_lower_bound']for r in rows),
 unknown_eligibility_or_side=sum(r['unknown_eligibility_or_side']for r in rows),unknown_td_outcomes=sum(r['unknown_td_outcomes']for r in rows),
 exact_team_counts=sum(r['exact_official_inside5_rushes']is not None for r in rows),exact_team_TDs=sum(r['exact_inside5_rush_tds']is not None for r in rows),defined_team_rates=sum(r['value']is not None for r in rows),
 known_kneel_events=sum(e['eligible']is True and e['official_kneel']is True for e in result['event_basis']),official_flag_conflicts=sum(e['official_flag_conflict']for e in result['event_basis']),outcome_conflicts=sum(e['outcome_conflict']for e in result['event_basis']),
 evidence_use=result['evidence_use'],pregame_serving_eligible=False,source_fetches=0,parent_inflates=0,models=0,database_writes=0)
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
