from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,joblib
import numpy as np
from sqlalchemy import text
from backend.app.product_services.optimizer import OptimizerService,_json_safe
P=Path(__file__).resolve().parent;s=OptimizerService();baseline=json.load(open(P/'active_baseline.json'));expected=next(r for r in baseline if r['slate_id']=='SUNDAY_MAIN');a=joblib.load(P/'prepared_incumbent.joblib')
with s.engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'))
 active=dict(c.execute(text("SELECT * FROM target.active_projection_run WHERE season=2026 AND week=6 AND slate_id='SUNDAY_MAIN'")).mappings().one());assert str(active['projection_run_id'])==expected['projection_run_id']
 projections=[dict(r) for r in c.execute(text("SELECT player_id,mean FROM target.player_projection WHERE projection_run_id='b2ae485d-f436-470b-a52c-fa53095bbd4d' ORDER BY player_id")).mappings()];target=a['target'].set_index('player_id');assert len(projections)==len(target)==288
 assert all(abs(float(r['mean'])-float(target.loc[str(r['player_id']),'projection_after_scenario']))<1e-12 for r in projections)
 receipt=dict(verified_at=datetime.now(UTC).isoformat(),main_pointer_unchanged=True,main_pointer=_json_safe(active),prepared_projection_unchanged=True,prepared_projection_run_id='b2ae485d-f436-470b-a52c-fa53095bbd4d',rows=len(projections),prepared_mean_sha256=hashlib.sha256(json.dumps(_json_safe(projections),sort_keys=True).encode()).hexdigest(),no_write_commands_executed=True)
(P/'live_unchanged.json').write_text(json.dumps(receipt,indent=2)+'\n');print('Main pointer and all288 prepared means unchanged')
