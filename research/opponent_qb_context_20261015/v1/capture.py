from pathlib import Path
from datetime import datetime,UTC
import json
from sqlalchemy import text
from backend.app.product_services.optimizer import OptimizerService,_json_safe
P=Path(__file__).resolve().parent;s=OptimizerService()
queries={
'coverage':"SELECT 'matrix' AS domain,season,count(*) AS n FROM public.player_game_feature_matrix GROUP BY season UNION ALL SELECT 'qb_stats',season,count(*) FROM public.raw_nfl_weekly_stat WHERE position='QB' GROUP BY season ORDER BY domain,season",
'qb_logs':"WITH latest AS (SELECT DISTINCT ON (season,week,player_id) * FROM public.raw_nfl_weekly_stat WHERE position='QB' ORDER BY season,week,player_id,created_at DESC,raw_nfl_weekly_stat_id DESC) SELECT r.raw_nfl_weekly_stat_id,r.ingest_run_id,r.season,r.week,r.player_id AS source_player_id,a.player_master_id,r.team,r.raw_row_json,r.created_at FROM latest r LEFT JOIN public.player_alias a ON a.source_system='nflreadpy' AND a.source_key=r.player_id ORDER BY r.season,r.week,r.player_id",
'dst_matrix':"SELECT DISTINCT ON (season,week,team) * FROM public.player_game_feature_matrix WHERE position IN ('DST','D','DEF') AND season<=2026 AND (season<2026 OR week<=5) ORDER BY season,week,team,created_at DESC,player_game_feature_matrix_id DESC",
'schedule':"SELECT DISTINCT ON (season,week,game_id) * FROM public.raw_nfl_schedule WHERE season<=2026 ORDER BY season,week,game_id,created_at DESC,raw_nfl_schedule_id DESC",
'starter_history':"SELECT season,week,slate,team,player_master_id,evidence_tier,source,evidence_json,created_at FROM public.starting_qb_evidence ORDER BY season,week,team"}
with s.engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'))
 for name,q in queries.items():
  rows=[dict(r) for r in c.execute(text(q)).mappings()];(P/(name+'.json')).write_text(json.dumps(_json_safe(dict(captured_at=datetime.now(UTC).isoformat(),query=q,rows=rows)),indent=2,allow_nan=False)+'\n');print(name,len(rows),flush=True)
