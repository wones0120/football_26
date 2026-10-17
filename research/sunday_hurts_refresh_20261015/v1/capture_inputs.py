from pathlib import Path
from datetime import datetime,UTC
import json
from sqlalchemy import text
from backend.app.product_services.optimizer import OptimizerService,_json_safe
P=Path(__file__).resolve().parent;s=OptimizerService()
queries={
'old_request':"SELECT request_json FROM public.operational_job WHERE run_id='fa65082d-ca23-45e0-9edf-b45b79de86e5' ORDER BY created_at DESC LIMIT 1",
'current_context':"SELECT c.player_master_id,c.player_name,c.team,c.position,c.injury_status,c.role_label,c.evidence_json,r.* FROM public.pregame_player_context c JOIN public.pregame_context_run r USING(context_run_id) WHERE r.season=2026 AND r.week=6 AND r.slate='SUNDAY_MAIN' AND (c.player_name IN ('Jalen Hurts','Tanner McKee','Caleb Williams','Chuba Hubbard','Derrick Henry','Rome Odunze') OR c.team='CAR') ORDER BY r.received_at DESC LIMIT 150",
'starter':"SELECT * FROM public.starting_qb_evidence WHERE season=2026 AND week=6 AND slate='SUNDAY_MAIN' AND team IN ('PHI','CHI','BAL') ORDER BY created_at DESC LIMIT 50",
'stats':"SELECT DISTINCT ON (player_id,week) * FROM public.raw_nfl_weekly_stat WHERE season=2026 AND week BETWEEN 1 AND 5 ORDER BY player_id,week,created_at DESC,raw_nfl_weekly_stat_id DESC",
'aliases':"SELECT * FROM public.player_alias WHERE player_master_id IN (SELECT player_master_id FROM public.curated_salary WHERE season=2026 AND week=6 AND slate='SUNDAY_MAIN')",
'snaps':"SELECT DISTINCT ON (pfr_player_id,week) * FROM public.raw_nfl_snap_count WHERE season=2026 AND week BETWEEN 1 AND 5 ORDER BY pfr_player_id,week,created_at DESC,raw_nfl_snap_count_id DESC",
'salary':"SELECT * FROM public.curated_salary WHERE season=2026 AND week=6 AND slate='SUNDAY_MAIN'"}
with s.engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'))
 for name,q in queries.items():
  values=[dict(r) for r in c.execute(text(q)).mappings()];(P/(name+'_capture.json')).write_text(json.dumps(_json_safe(dict(captured_at=datetime.now(UTC).isoformat(),query=q,rows=values)),indent=2,allow_nan=False)+'\n');print(name,len(values))
