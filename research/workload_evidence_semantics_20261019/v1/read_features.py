from pathlib import Path
import json,datetime,hashlib
from sqlalchemy import create_engine,text
from Database.config import get_connection_string
from backend.app.product_services.workload_evidence import FEATURE_FIELDS
P=Path(__file__).parent;config=next(r for r in json.load(open('/private/tmp/sunday_actual_review_20261018/stored_run_configs.json'))if r['optimizer_run_id'].startswith('398efe88'))['constraint_config_json'];snap=config['strategy_runtime']['football_analyst']['input_snapshot'];meta=config['strategy_runtime']['classic_run_input_snapshot']['payload']['metadata'];proj=meta['projection_run_id']
keys=list(dict.fromkeys([*FEATURE_FIELDS,'pregame_opportunity_context_applied','position']))
cols=', '.join("f.feature_json->'%s' AS %s"%(k,k)for k in keys)
engine=create_engine(get_connection_string(),connect_args={'options':'-c default_transaction_read_only=on -c statement_timeout=15000'})
with engine.connect()as c:
 rows=c.execute(text('SELECT f.player_id,f.game_id,f.created_at AS feature_created, mr.feature_run_id, '+cols+''' FROM target.projection_run pr JOIN target.model_run mr USING(model_run_id) JOIN target.feature_player_game f USING(feature_run_id)
 WHERE pr.projection_run_id=:projection AND f.game_id=ANY(:games) ORDER BY f.game_id,f.player_id'''),{'projection':proj,'games':snap['scope']['game_ids']}).mappings().all()
 out=dict(projection_run_id=proj,source_run_id=meta['optimizer_run_id'],decision_at=snap['decision_at'],captured_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),source_config_sha256=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest(),rows=[dict(r)for r in rows]);(P/'recovered_original_feature_fields.json').write_text(json.dumps(out,default=str,indent=2));print('recovered feature rows',len(rows))
