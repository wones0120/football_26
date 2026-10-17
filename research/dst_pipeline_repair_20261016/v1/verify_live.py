"""Read-only comparison to the preserved Main projection; writes local evidence only."""
from pathlib import Path
from datetime import datetime, UTC
import hashlib
import json
import sys
import joblib
from sqlalchemy import text
from backend.app.product_services.optimizer import OptimizerService, _json_safe
P=Path(__file__).resolve().parent
baseline=joblib.load('research/dst_retrain_20261016/v1/prepared_incumbent.joblib')['target'].set_index('player_id')
service=OptimizerService()
with service.engine.connect() as connection:
    connection.execute(text('SET TRANSACTION READ ONLY'))
    pointer=dict(connection.execute(text("SELECT * FROM target.active_projection_run WHERE season=2026 AND week=6 AND slate_id='SUNDAY_MAIN'")).mappings().one())
    active_rows=[dict(row) for row in connection.execute(text('SELECT player_id,mean FROM target.player_projection WHERE projection_run_id=:run ORDER BY player_id'),dict(run=pointer['projection_run_id'])).mappings()]
    rows=[dict(row) for row in connection.execute(text("SELECT player_id,mean FROM target.player_projection WHERE projection_run_id='b2ae485d-f436-470b-a52c-fa53095bbd4d' ORDER BY player_id")).mappings()]
assert len(rows)==len(baseline)==288
assert all(abs(float(row['mean'])-float(baseline.loc[str(row['player_id']),'projection_after_scenario']))<1e-12 for row in rows)
payload=dict(active_projection_sha256=hashlib.sha256(json.dumps(_json_safe(active_rows),sort_keys=True).encode()).hexdigest(),active_rows=len(active_rows),verified_at=datetime.now(UTC).isoformat(),pointer=_json_safe(pointer),rows=288,projection_sha256=hashlib.sha256(json.dumps(_json_safe(rows),sort_keys=True).encode()).hexdigest(),all_prepared_means_unchanged=True,read_only=True)
name=sys.argv[1] if len(sys.argv)>1 else 'after'
if name == 'after':
    before=json.loads((P/'live_before.json').read_text())
    assert payload['pointer']==before['pointer']
    assert payload['active_projection_sha256']==before['active_projection_sha256']
    assert payload['projection_sha256']==before['projection_sha256']
(P/f'live_{name}.json').write_text(json.dumps(payload,indent=2)+'\n')
print('Main pointer and all 288 means unchanged',name)
