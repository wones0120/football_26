from backend.app.db import engine
from sqlalchemy import text
from pathlib import Path
from datetime import datetime,UTC
import json,sys
key=sys.argv[1]; assert len(key)==36
with engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'))
 row=dict(c.execute(text('select * from operational_job where job_id=:key'),{'key':key}).mappings().one())
 dest=Path('research/sunday_refresh_20261015')/(key+'_'+datetime.now(UTC).strftime('%H%M%S')+'.json');dest.write_text(json.dumps(row,default=str,indent=2)+'\n')
 print({k:row.get(k) for k in ['job_id','status','stage','progress_message','error_message']})
