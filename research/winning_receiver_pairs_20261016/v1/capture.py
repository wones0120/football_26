from pathlib import Path
import json,gzip,hashlib,csv,zipfile,io
from sqlalchemy import text
from backend.app.product_services.optimizer import OptimizerService,_json_safe
P=Path(__file__).resolve().parent;old=Path('artifacts/classic_historical_study');inv=json.loads((P/'inventory.json').read_text());(P/'inputs').mkdir(exist_ok=True)
with OptimizerService().engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'))
 salaries=_json_safe([dict(r) for r in c.execute(text("SELECT season,week,slate,player_master_id,source_player_key,player_name,team,opponent,position,salary,game_info FROM public.curated_salary WHERE source_system='draftkings' AND UPPER(slate)='SUNDAY_MAIN' AND season IN(2025,2026)")).mappings()]);(P/'salaries.json').write_text(json.dumps(salaries,sort_keys=True))
 sched=_json_safe([dict(r) for r in c.execute(text("SELECT DISTINCT ON(game_id) game_id,season,week,home_team,away_team,raw_row_json,ingest_run_id FROM public.raw_nfl_schedule WHERE season IN(2025,2026) ORDER BY game_id,created_at DESC,raw_nfl_schedule_id DESC")).mappings()]);(P/'schedule.json').write_text(json.dumps(sched,sort_keys=True))
 aliases=_json_safe([dict(r) for r in c.execute(text("SELECT DISTINCT player_master_id,source_key FROM public.player_alias WHERE source_system='nflreadpy'")).mappings()]);(P/'aliases.json').write_text(json.dumps(aliases,sort_keys=True))
 for contest in inv['contests']:
  cid=contest['contest_id'];dest=P/'inputs'/(cid+'.json.gz');cache=old/'inputs'/(cid+'.json.gz')
  if dest.exists():continue
  if cache.exists():
   # Preserve existing immutable grouped raw evidence; all required cohorts were captured originally.
   payload=json.load(gzip.open(cache,'rt'));payload['contest']=contest;payload['capture_origin']=str(cache)
  else:
   q="""SELECT lineup_text,count(*)::int n,min(rank) best_rank,max(rank) worst_rank,min(entry_points) min_points,max(entry_points) max_points,count(*) FILTER(WHERE rank=1)::int winner,count(*) FILTER(WHERE rank<=ceil(:n*.01))::int top_1 FROM target.dfs_contest_entry_result WHERE contest_id=:cid GROUP BY lineup_text"""
   rows=_json_safe([dict(r) for r in c.execute(text(q),{'cid':cid,'n':contest['field_size']}).mappings()]);payload=dict(contest=contest,entries=rows,capture_origin='read_only_current_normalized_actual_standings')
  with gzip.open(dest,'wt') as f:json.dump(payload,f,sort_keys=True)
  print(cid,sum(r['n'] for r in payload['entries']),flush=True)
audit=[]
for source in inv['sources']:
 candidates=[Path(source['original_path']),Path('/Users/wones/NFL')/source['file_name'],Path('/Users/wones/NFL/Processed')/source['file_name'],Path('/Users/wones/Downloads')/source['file_name']];path=next((x for x in candidates if x.exists()),None)
 item=dict(source_file_id=source['source_file_id'],original_path=source['original_path'],located_path=str(path) if path else None,expected_sha256=source['content_sha256'])
 if path:
  h=hashlib.sha256()
  with path.open('rb') as f:
   while chunk:=f.read(1024*1024):h.update(chunk)
  item['sha256']=h.hexdigest();item['hash_matches']=h.hexdigest()==source['content_sha256']
  if path.suffix.lower()=='.zip':
   with zipfile.ZipFile(path) as z:
    names=[n for n in z.namelist() if n.lower().endswith('.csv')];item['zip_members']=names
    with z.open(names[0]) as f:item['headers']=next(csv.reader(io.TextIOWrapper(f,encoding='utf-8-sig')))
    with z.open(names[0]) as f:
     memberhash=hashlib.sha256()
     while chunk:=f.read(1024*1024):memberhash.update(chunk)
    item['csv_member_sha256']=memberhash.hexdigest();item['hash_matches']=memberhash.hexdigest()==source['content_sha256'];item['hash_semantics']='imported uncompressed CSV bytes'
  else:
   with path.open(encoding='utf-8-sig') as f:item['headers']=next(csv.reader(f))
 audit.append(item)
(P/'source_audit.json').write_text(json.dumps(audit,indent=2));print('sources',len(audit),'located',sum(bool(x['located_path']) for x in audit),'hashmatch',sum(x.get('hash_matches',False) for x in audit),flush=True)
