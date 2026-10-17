from pathlib import Path
from datetime import datetime,UTC
import json
from sqlalchemy import text
from sqlalchemy.orm import Session
from backend.app.product_services.optimizer import OptimizerService,_json_safe
from backend.app.product_services.official_injuries import _Document,resolve_official_player,observation_clock
from backend.app.product_services.pregame_context import PregameContextService,load_current_pregame_context
from backend.app.product_services.starters import StartingQBService
from backend.app.product_services.slate_preparation import SlatePreparationRequest,slate_games,require_prelock
from backend.app.services.source_capture import SourceCaptureService
P=Path(__file__).resolve().parent;svc=OptimizerService();scope=dict(season=2026,week=6,slate='SUNDAY_MAIN')
with Session(svc.engine) as s:
 games=slate_games(s,SlatePreparationRequest(**scope,action='rebuild'));lock=require_prelock(games)
 rows=[dict(r) for r in s.execute(text('SELECT DISTINCT s.player_master_id AS player_id,s.player_name,s.team,s.position,m.full_name FROM public.curated_salary s JOIN public.player_master m USING(player_master_id) WHERE season=2026 AND week=6 AND slate=\'SUNDAY_MAIN\' AND source_system=\'draftkings\'')).mappings()]
 aliases=[dict(r) for r in s.execute(text('SELECT player_master_id,source_system,source_key,alias_name FROM public.player_alias')).mappings()]
 captures={}
 for name in ['hurts_statement','phi_depth','chi_qb','phi_injury','car_injury','bal_injury','chi_injury','no_injury']:
  v=json.loads((P/(name+'.json')).read_text());received=datetime.fromisoformat(v['received_at']);at=observation_clock(v['headers'],received)
  cap=SourceCaptureService(s).capture_file(P/(name+'.json'),source_system='nfl_official',dataset='official_club_news' if name in ['hurts_statement','chi_qb'] else 'official_club_depth' if name=='phi_depth' else 'official_club_injury_article',**scope,source_uri=v['uri'],slate_lock_at=lock,source_license='Official club public evidence retained for source audit',effective_at=at,observation_basis='http_response_clock',media_type='application/json',row_count=1,metadata={'body_sha256':v['body_sha256'],'publication_clock_available':name in ['hurts_statement','chi_qb']})
  captures[name]=dict(snapshot_id=str(cap.snapshot.snapshot_id),observed_at=at.isoformat(),received_at=received.isoformat(),uri=v['uri'])
# Explicit assertions bind manual article interpretation to retained source text.
h=json.loads((P/'hurts_statement.json').read_text());plain=_Document(h['body']).root.content();assert "Jalen will be out for Sunday's game vs. the Panthers" in plain
ids={}
for name,team,slug in [('Jalen Hurts','PHI','jalen-hurts'),('Tanner McKee','PHI','tanner-mckee'),('Caleb Williams','CHI','caleb-williams')]:
 row=dict(team=team,position='QB',player_name=name,source_key=f'https://www.{"philadelphiaeagles" if team=="PHI" else "chicagobears"}.com/team/players-roster/{slug}')
 pid,reason=resolve_official_player(row,rows,aliases);assert pid,(row,reason);ids[name]=dict(player_id=pid,identity_match=reason,team=team,position='QB',source_key=row['source_key'])
news=captures['hurts_statement'];ctx=PregameContextService(engine=svc.engine).create_run(dict(**scope,source='official_club_news',source_uri=h['uri'],observed_at=datetime.fromisoformat(news['observed_at']),players=[dict(player_id=ids['Jalen Hurts']['player_id'],team='PHI',position='QB',injury_status='OUT',evidence={'source_snapshot_id':news['snapshot_id'],'official_player_key':ids['Jalen Hurts']['source_key'],'identity_match':ids['Jalen Hurts']['identity_match'],'article_published_at':'2026-10-15T13:00:00-04:00','extraction':'explicit_game_specific_OUT_statement','evidence_excerpt':"Jalen will be out for Sunday's game vs. the Panthers"})]))
# Club still lists Hurts first, McKee second. Absence + next depth rank is
# sourced provisional inference, deliberately not official starter confirmation.
d=json.loads((P/'phi_depth.json').read_text());assert 'Tanner McKee' in _Document(d['body']).root.content()
starter=StartingQBService(svc.connection_string).derive_starters(**scope,confirmed_starters=[dict(team='PHI',player_master_id=ids['Tanner McKee']['player_id'],source='provisional_official_club_depth_after_hurts_out',evidence_tier='inferred',source_uri=h['uri'],observed_at=news['observed_at'],note='Hurts explicitly OUT; current official club depth lists McKee next. Expected replacement, not a club starter announcement. Source snapshots '+news['snapshot_id']+' '+captures['phi_depth']['snapshot_id'])])
result=dict(captured_at=datetime.now(UTC).isoformat(),captures=captures,canonical_ids=ids,hurts_context=ctx,starting_qb=_json_safe(vars(starter)),chi_status='Oct14 estimated FULL; team explicitly says starter remains unknown among Williams/Bagent/Keenum; no confirmed starter asserted')
(P/'news_ingest.json').write_text(json.dumps(_json_safe(result),indent=2)+'\n');print(json.dumps(_json_safe(result),indent=2),flush=True)
