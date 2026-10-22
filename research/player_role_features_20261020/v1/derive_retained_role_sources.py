from datetime import UTC,datetime
import csv,json,hashlib
from pathlib import Path
from sqlalchemy import select,text
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.player_role_source_features import extract_retained_role_sources
from backend.app.product_services.player_role_features import build_player_role_features
R=Path('research/player_role_features_20261020/v1');cutoff='2026-10-19T23:00:39.837202+00:00';ids=['8fed5cc6-a041-50cc-a150-a1d2787d7f9a','a7f5f27b-9bfa-5a60-8809-32dc0b4dad80']
with Session(engine) as s:
 snapshots=[s.get(SourceSnapshot,k) for k in ids]
 natives=set()
 for snap in snapshots:
  with open(snap.artifact_path) as f:natives.update(r['gsis_id'] for r in csv.DictReader(f) if r.get('team') in {'SF','WAS'} and r.get('gsis_id'))
 aliases={}
 for row in s.execute(text("SELECT source_key,player_master_id FROM public.player_alias WHERE source_system='nflreadpy' AND source_key=ANY(:keys)"),dict(keys=sorted(natives))).mappings():aliases.setdefault(row['source_key'],set()).add(str(row['player_master_id']))
 extracted=extract_retained_role_sources(*snapshots,aliases,season=2026,week=6,teams=['SF','WAS'],cutoff=cutoff)
 old=json.loads(Path('research/opportunity_component_response_20261019/v1/fullshape_retry_prepare_job.json').read_text())['result'];facts=[f for r in old['source_manifest']['availability'] for f in r['evidence_json'].get('source_facts',[])]
 # Original scoped official facts are retained; raw-roster/depth clocks are not
 # renewed. This is a new postlock derivation, never original pregame output.
 features=build_player_role_features(extracted['actors'],extracted['facts']+facts,season=2026,week=6,cutoff=cutoff,roster_coverage=extracted['roster_coverage'])
 known={mid:sum(p['metrics'][mid]['value'] is not None for p in features['players']) for mid in ('G17-M01','G17-M02','G17-M05','G17-M10')}
 team_known={mid:sum(t['metrics'][mid]['value'] is not None for t in features['teams']) for mid in ('G18-M01','G18-M03','G18-M04','G18-M05','G18-M06','G18-M07')}
D=Path('artifacts/player_role_features');D.mkdir(exist_ok=True)
result=dict(evidence_use='postlock_descriptive_not_pregame_or_serving',actual_derived_at=datetime.now(UTC).isoformat(),original_source_cutoff=cutoff,extracted=extracted,features=features)
raw=json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(raw).hexdigest();path=D/(sha+'.json')
if path.exists():assert path.read_bytes()==raw
else:path.write_bytes(raw)
summary=dict(status='actual_retained_source_feature_derivation_not_models_or_serving',actual_derived_at=result['actual_derived_at'],source_snapshot_ids=ids,actors=len(extracted['actors']),source_facts=len(extracted['facts']),identity_review_requests=len(extracted['identity_review_requests']),known_player_features=known,known_team_features=team_known,roster_complete=False,artifact_ref=dict(path=str(path.resolve()),sha256=sha,bytes=len(raw)),model_consumed=False,optimizer_consumed=False)
(R/'actual_retained_feature_receipt.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary))
