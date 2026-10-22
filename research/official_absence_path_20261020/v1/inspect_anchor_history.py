from pathlib import Path
from datetime import datetime,UTC
import json
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.weekly_passing_air_efficiency import load_reviewed_weekly_input
from backend.app.product_services.schedule_context_features import load_schedule_context
p=Path('research/official_absence_path_20261020/v1')
r=json.loads((p/'actual_receipt.json').read_text());now=datetime.now(UTC)
w=load_reviewed_weekly_input(r['weekly_input_ref'],cutoff=now)
with Session(engine) as session:s=load_schedule_context(session.get(SourceSnapshot,'6a346947-eca2-5c0d-abf0-95e52ac72e5b'),cutoff=now)
rows=[]
for a in r['offensive_absence_anchors']:
 records=[x for x in w['rows'] if x['season']==a['season'] and x['team']==a['team'] and x['source_player_id']==a['source_native_gsis_id'] and x['week']<=9]
 games=sorted([x for x in s['game_rows'] if x['season']==a['season'] and x['game_type']=='REG' and a['team'] in (x['home_team'],x['away_team']) and x['week']<=9],key=lambda x:x['week'])
 logs=[]
 for g in games:
  match=[x for x in records if x['week']==g['week']];assert len(match)<=1
  x=match[0] if match else None
  logs.append(dict(week=g['week'],game_id=g['game_id'],source_position=x['source_position'] if x else None,canonical=x['player_master_id'] if x else None,counts={c:x['metrics'].get(mid,{}).get('denominator') if x else None for c,mid in [('pass','G04-M01'),('rush','G07-M01'),('target','G09-M01')]},weekly_present=x is not None))
 rows.append(dict(anchor=a,scheduled_slots=logs))
(p/'anchor_history_inspection.json').write_text(json.dumps(dict(inspected_at=now.isoformat(),source_ref=r['weekly_input_ref'],schedule=s['provenance'],rows=rows,missing_weekly_is_absence=False),indent=2)+'\n')
print(json.dumps(rows))
