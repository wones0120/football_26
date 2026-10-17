"""Capture and append the official SEA WR practice-squad fact; preserve all history."""
from datetime import UTC,datetime
import json
from pathlib import Path
import httpx
from sqlalchemy import text
from backend.app.db import engine,SessionLocal
from backend.app.product_services.official_injuries import _Document,observation_clock
from backend.app.product_services.pregame_context import PregameContextService,load_current_pregame_context
from backend.app.product_services.showdown_player_context import compose_player_contexts,CONTEXT_CONTRACT
from backend.app.services.source_capture import SourceCaptureService
from Database.player_identity import normalize_player_name
root=Path(__file__).resolve().parent
pid='48979952-e6d0-4b39-a5eb-44208f883058'
assert not (root/'charles_context_receipt.json').exists()
roster_envelope=json.loads((root/'sea_roster_capture.json').read_text())
roster_body=roster_envelope['body']
url='https://www.seahawks.com/news/seahawks-sign-velus-jones-jr-to-53-man-roster-move-irv-charles-to-practice-squad'
r=httpx.get(url,timeout=30,follow_redirects=True,headers={'Cache-Control':'no-cache'});r.raise_for_status();received=datetime.now(UTC);observed=observation_clock(r.headers,received)
path=root/'charles_transaction_capture.json';assert not path.exists();path.write_text(json.dumps(dict(source_uri=url,received_at=received.isoformat(),observed_at=observed.isoformat(),headers=dict(r.headers),body=r.text)))
plain=_Document(r.text).root.content()
assert 'Oct 14, 2026' in plain and 'releasing receiver Irv Charles and subsequently signing him to the practice squad' in plain
def walk(n):
 for c in n.children:
  if hasattr(c,'tag'):yield c;yield from walk(c)
group=None;matches=[]
for n in walk(_Document(roster_body).root):
 if n.tag=='h4':group=n.content()
 if n.tag!='table':continue
 for tr in n.find('tr'):
  c=list(tr.find('td'))
  if len(c)>=3 and normalize_player_name(c[0].content())==normalize_player_name('Irvin Charles'):
   matches.append(dict(name=c[0].content(),position=c[2].content(),group=group,source_keys=sorted({a.attrs['href'] for a in c[0].find('a') if '/team/players-roster/' in a.attrs.get('href','')})))
assert len(matches)==1,matches
m=matches[0];assert m['position']=='WR' and m['group']=='Active' and len(m['source_keys'])==1,m
with engine.connect() as c:
 s=dict(c.execute(text("SELECT player_master_id AS player_id,player_name,team,position,curated_salary_id AS salary_source_row_id FROM curated_salary WHERE player_master_id=:pid AND season=2026 AND week=6 AND slate='THURSDAY_NIGHT' ORDER BY created_at DESC LIMIT 1"),dict(pid=pid)).mappings().one())
 assert s['team']=='SEA' and s['position']=='WR' and normalize_player_name(s['player_name'])==normalize_player_name(m['name'])
 contexts=load_current_pregame_context(c,season=2026,week=6,slate='THURSDAY_NIGHT',cutoff=received,include_source_history=True)
facts=[];prior=None
for c in contexts:
 if str(c['player_master_id'])!=pid:continue
 e=c.get('evidence_json') or {}
 if e.get('canonical_context_contract')==CONTEXT_CONTRACT:
  facts+=e.get('source_facts',[])
  if prior is None:prior=e
with SessionLocal() as session:
 capture=SourceCaptureService(session).capture_file(path,source_system='official_nfl_club',dataset='verified_roster_observation',season=2026,week=6,slate='THURSDAY_NIGHT',source_license='Official public club roster; upstream terms apply',source_uri=url,slate_lock_at=datetime(2026,10,16,0,15,tzinfo=UTC),observation_basis='http_response_clock',media_type='application/json',metadata={'actual_received_at':received.isoformat(),'game_dressing_verified':False})
 sid=str(capture.snapshot.snapshot_id);session.commit()
facts.append(dict(player_id=pid,team='SEA',position='WR',source_position='WR',kind='roster_status',source='official_nfl_club_transaction',status='PS',observed_at=observed.isoformat(),received_at=received.isoformat(),source_uri=url,source_ids=[sid,m['source_keys'][0]],identity_method='canonical_salary_id_and_team_position_normalized_name_exact',game_dressing_verified=False,published_at='2026-10-14T14:03:00-07:00',conflicting_roster_capture='sea_roster_capture.json',resolution='Explicit Oct14 official transaction supersedes roster listing; later elevation remains unknown.'))
c=compose_player_contexts([s],facts,cutoff=received,max_age_hours=24)[0];e=c['evidence_json'];assert e['availability_state']=='UNAVAILABLE',e
if prior:e['workload_context']=prior.get('workload_context',{})
payload=dict(season=2026,week=6,slate='THURSDAY_NIGHT',source=CONTEXT_CONTRACT,source_uri=c['source_uri'],observed_at=c['observed_at'],notes='Explicit official Oct14 transaction establishes practice-squad membership despite retained roster-table Active listing. Canonical identity corroborated by SEA/WR roster link. No elevation or game dressing claim.',players=[dict(player_id=pid,injury_status=c['injury_status'],role_label=c['role_label'],availability_probability=c['availability_probability'],evidence=e)])
receipt=PregameContextService(engine=engine).create_run(payload)
(root/'charles_context_receipt.json').write_text(json.dumps(dict(official_match=m,snapshot_id=sid,observed_at=observed.isoformat(),received_at=received.isoformat(),payload=payload,result=receipt),indent=2,default=str))
print('Captured',sid,'canonical',pid,'status',c['injury_status'],'state',e['availability_state'])
