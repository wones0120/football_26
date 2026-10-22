from datetime import UTC,datetime
import json,csv,hashlib
from pathlib import Path
from sqlalchemy import select,text
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.official_role_report_features import extract_official_role_report
from backend.app.product_services.player_role_features import build_player_role_features
R=Path('research/player_role_features_20261020/v1');cutoff='2026-10-19T23:00:39.837202+00:00'
receipt=json.loads((R/'actual_retained_feature_receipt.json').read_text());ref=receipt['artifact_ref'];raw=Path(ref['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==ref['sha256'];base=json.loads(raw);roster=base['extracted']['actors']
with Session(engine) as session:
 source=session.get(SourceSnapshot,'8fed5cc6-a041-50cc-a150-a1d2787d7f9a')
 from backend.app.services.source_capture import verify_snapshot_artifact
 verify_snapshot_artifact(source)
 names={r['gsis_id']:r['full_name'] for r in csv.DictReader(open(source.artifact_path))}
 roster=[dict(r,player_name=names.get(r['source_player_id'])) for r in roster]
 aliases=[dict(r) for r in session.execute(text("SELECT source_system,source_key,player_master_id,alias_name FROM public.player_alias WHERE source_system='nfl_official'")).mappings()]
 found=session.execute(select(SourceSnapshot).where(SourceSnapshot.dataset=='official_final_game_report',SourceSnapshot.season==2026,SourceSnapshot.week==6,SourceSnapshot.captured_at<=datetime.fromisoformat(cutoff)).order_by(SourceSnapshot.captured_at.desc())).scalars().all()
 chosen={}
 for s in found:
  if s.metadata_json.get('team') in {'SF','WAS'}:chosen.setdefault(s.metadata_json['team'],s)
 outputs=[extract_official_role_report(s,roster,aliases,cutoff=cutoff) for s in chosen.values()]
 facts=base['extracted']['facts']+[f for b in outputs for f in b['facts']]
 # Final report feature facts now cover non-salary players, without relabeling
 # source roster ACT or allocating a single missing player's opportunity.
 features=build_player_role_features(roster,facts,season=2026,week=6,cutoff=cutoff,roster_coverage=base['extracted']['roster_coverage'])
out=dict(evidence_use='postlock_descriptive_not_pregame_or_serving',actual_derived_at=datetime.now(UTC).isoformat(),original_cutoff=cutoff,source_outputs=outputs,features=features)
D=Path('artifacts/player_role_features');data=json.dumps(out,sort_keys=True,separators=(',',':'),allow_nan=False,default=str).encode();sha=hashlib.sha256(data).hexdigest();p=D/(sha+'.json')
if p.exists():assert p.read_bytes()==data
else:p.write_bytes(data)
summary=dict(actual_derived_at=out['actual_derived_at'],status='official_practice_source_features_not_models',official_report_teams=sorted(chosen),source_snapshot_ids=[s.snapshot_id for s in chosen.values()],actors=len(roster),official_resolved_players=sum(len(b['identity_resolution_actions']) for b in outputs),identity_review_requests=sum(len(b['identity_review_requests']) for b in outputs),known_player_features={m:sum(p['metrics'][m]['value'] is not None for p in features['players']) for m in ('G17-M01','G17-M02','G17-M05','G17-M10')},known_team_features={m:sum(p['metrics'][m]['value'] is not None for p in features['teams']) for m in ('G18-M01','G18-M03','G18-M04','G18-M05','G18-M06','G18-M07')},artifact_ref=dict(path=str(p.resolve()),sha256=sha,bytes=len(data)),queue_persisted=False,model_consumed=False,optimizer_consumed=False)
(R/'actual_official_practice_receipt.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary))
