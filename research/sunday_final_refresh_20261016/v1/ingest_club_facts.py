from pathlib import Path
from datetime import datetime,UTC
import json,httpx,hashlib
from sqlalchemy import text
from sqlalchemy.orm import Session
from backend.app.product_services.optimizer import OptimizerService,_json_safe
from backend.app.product_services.pregame_context import PregameContextService
from backend.app.product_services.official_injuries import resolve_official_player,observation_clock
from backend.app.services.source_capture import SourceCaptureService
from backend.app.product_services.starters import StartingQBService
P=Path(__file__).resolve().parent;assert not (P/'club_ingest_receipt.json').exists(),'Preserve append-only receipt; use a new version'
engine=OptimizerService().engine
with engine.connect() as c:
 salary=[dict(r) for r in c.execute(text("SELECT DISTINCT s.player_master_id AS player_id,s.player_name,s.team,s.position,m.full_name FROM public.curated_salary s JOIN public.player_master m USING(player_master_id) WHERE s.season=2026 AND s.week=6 AND upper(s.slate)='SUNDAY_MAIN' AND s.source_system='draftkings'")).mappings()]
 aliases=[dict(r) for r in c.execute(text("SELECT player_master_id,source_system,source_key,alias_name FROM public.player_alias WHERE player_master_id=ANY(:ids) OR source_system='nfl_official'"),dict(ids=[r['player_id'] for r in salary])).mappings()]
def identity(team,pos,name):
 row=dict(team=team,position=pos,player_name=name,source_key='club_fact:'+team+':'+pos+':'+name);pid,method=resolve_official_player(row,salary,aliases);assert pid,(row,method);return pid,method
def capture(sid,uri):
 r=httpx.get(uri,follow_redirects=True,headers={'Cache-Control':'no-cache'},timeout=45);r.raise_for_status();received=datetime.now(UTC);observed=observation_clock(dict(r.headers),received);envelope=dict(uri=str(r.url),received_at=received.isoformat(),observed_at=observed.isoformat(),headers=dict(r.headers),body=r.text);f=P/(sid+'_ingest_response.json');f.write_text(json.dumps(envelope,indent=2)+'\n')
 with Session(engine) as session:
  cap=SourceCaptureService(session).capture_file(f,source_system='nfl_official',dataset='official_club_facts',season=2026,week=6,slate='SUNDAY_MAIN',source_uri=str(r.url),effective_at=observed,slate_lock_at=datetime(2026,10,18,17,tzinfo=UTC),observation_basis='http_response_clock',source_license='Official public NFL/club pregame reporting retained for source audit',media_type='application/json',metadata=dict(body_sha256=hashlib.sha256(r.content).hexdigest(),publication_clock_available=False))
 return dict(snapshot_id=str(cap.snapshot.snapshot_id),uri=str(r.url),observed_at=observed,received_at=received,body=r.text)
receipts={};groups=[('no_friday','https://www.neworleanssaints.com/news/injury-report-new-york-giants-vs-new-orleans-saints-2026-nfl-week-6-friday',[('NO','WR','Chris Olave','QUESTIONABLE'),('NO','RB','Alvin Kamara','QUESTIONABLE')]),('pit_tb_friday','https://www.buccaneers.com/news/buccaneers-steelers-injury-report-oct-16-week-6-2026',[('PIT','WR','DK Metcalf','QUESTIONABLE'),('PIT','RB','Rico Dowdle','QUESTIONABLE'),('TB','QB','Baker Mayfield','OUT'),('TB','RB','Sean Tucker','QUESTIONABLE')]),('phi_friday','https://www.philadelphiaeagles.com/news/panthers-vs-eagles-injury-report-2026-nfl-week-6-saquon-barkley-devonta-smith',[('PHI','WR','DeVonta Smith','ACTIVE'),('PHI','WR','Dontayvion Wicks','ACTIVE'),('PHI','WR','Hollywood Brown','ACTIVE'),('PHI','RB','Saquon Barkley','OUT'),('PHI','RB','Will Shipley','OUT'),('PHI','QB','Jalen Hurts','OUT')])]
for sid,uri,facts in groups:
 source=capture(sid,uri);players=[]
 assert '2026' in source['body'] and ('Week 6' in source['body'] or 'Week Six' in source['body'] or 'week-6' in source['body'])
 for team,pos,name,status in facts:
  pid,method=identity(team,pos,name)
  players.append(dict(player_id=pid,team=team,position=pos,injury_status=status,evidence=dict(source_snapshot_id=source['snapshot_id'],identity_match=method,source_fact='Explicit Friday official club game designation/return statement; no numeric workload assumption or final inactive claim.',official_game_designation=status,observation_basis='http_response_clock')))
 if sid=='phi_friday':
  pid,method=identity('PHI','RB','Dameon Pierce');players.append(dict(player_id=pid,team='PHI',position='RB',role_label='STARTER',evidence=dict(source_snapshot_id=source['snapshot_id'],identity_match=method,role_source='Official club says in line to start with Barkley/Shipley out',expected_workload_status=None,numeric_workload_unavailable=True)))
 result=PregameContextService(engine=engine).create_run(dict(season=2026,week=6,slate='SUNDAY_MAIN',source='nfl_official',source_uri=source['uri'],observed_at=source['observed_at'],notes='Explicit official Friday facts; source rows append-only; no probabilities, shares or fantasy point changes authored.',players=players));receipts[sid]=dict(snapshot_id=source['snapshot_id'],context_run_id=result['context_run_id'],source_uri=source['uri'],observed_at=source['observed_at'],canonical_players=players)
starters=[]
for sid,uri,team,name in [('phi_starter','https://www.philadelphiaeagles.com/news/tanner-mckee-will-be-ready-for-his-moment-2026-nfl-week-6-carolina-panthers','PHI','Tanner McKee'),('bal_starter','https://amp.nfl.com/news/ravens-qb-lamar-jackson-ankle-out-sunday-vs-browns-tyler-huntley-to-start-again','BAL','Tyler Huntley')]:
 source=capture(sid,uri);pid,method=identity(team,'QB',name);starters.append(dict(player_master_id=pid,team=team,source='nfl_official',source_uri=source['uri'],observed_at=source['observed_at'],evidence_tier='confirmed',note='Explicit primary-source starting quarterback report; does not assert a numerical workload or fantasy adjustment.'));receipts[sid]=dict(snapshot_id=source['snapshot_id'],source_uri=source['uri'],observed_at=source['observed_at'],player_id=pid,identity_match=method)
result=StartingQBService().derive_starters(2026,6,'SUNDAY_MAIN',confirmed_starters=starters);receipts['starting_qbs']=vars(result)
(P/'club_ingest_receipt.json').write_text(json.dumps(_json_safe(receipts),indent=2)+'\n');print(json.dumps(_json_safe({k:{x:y for x,y in v.items() if x not in ['canonical_players','candidates']} for k,v in receipts.items()}),indent=2))
