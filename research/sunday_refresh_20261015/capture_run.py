from backend.app.db import engine
from sqlalchemy import text
from pathlib import Path
from datetime import datetime,UTC
import json,sys
key=sys.argv[1];label=sys.argv[2];assert label in ['normal','contrarian'];assert len(key)==36
with engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'))
 run=dict(c.execute(text('select * from target.optimizer_run where optimizer_run_id=:key'),dict(key=key)).mappings().one())
 rows=[dict(r) for r in c.execute(text('select l.lineup_id,l.lineup_number,p.slot_index,p.roster_position,p.player_json from target.lineup l join target.lineup_player p using(lineup_id) where l.optimizer_run_id=:key order by l.lineup_number,p.slot_index'),dict(key=key)).mappings()]
 lineups=[]
 for n in sorted({r['lineup_number'] for r in rows}):lineups.append([r['player_json'] for r in rows if r['lineup_number']==n])
 output=dict(observed_at=datetime.now(UTC).isoformat(),access='read-only persisted saved result verification',run=run,lineups=lineups,rows=rows)
 path=Path('research/sunday_refresh_20261015')/(label+'_saved_result.json');assert not path.exists();path.write_text(json.dumps(output,indent=2,default=str)+'\n')
 print('saved',label,key,run['status'],len(lineups));print('configkeys',list(run.get('constraint_config_json',{})))
