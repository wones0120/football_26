from pathlib import Path
from datetime import datetime,timezone
import json
from sqlalchemy import text
from backend.app.db import engine
with engine.connect()as c:
 with c.begin():
  c.execute(text('SET TRANSACTION READ ONLY'));c.execute(text("SET LOCAL statement_timeout='30000ms'"))
  q="""SELECT snapshot_id,source_system,dataset,week,observed_at,effective_at,captured_at,slate_lock_at,observation_basis,content_sha256,byte_count,row_count,artifact_path,source_uri FROM public.source_snapshot WHERE season=2026 ORDER BY captured_at,snapshot_id LIMIT 1500"""
  rows=[dict(r)for r in c.execute(text(q)).mappings()]
assert len(rows)<1500
Path('research/readiness_2026_20261020/v1/DB_SOURCE_INVENTORY_COMPLETE.json').write_text(json.dumps(dict(read_at=datetime.now(timezone.utc).isoformat(),query=q,snapshots=rows,complete_under_row_cap=True,mutation_statements=0),indent=2,sort_keys=True,default=str)+'\n');print(len(rows))
