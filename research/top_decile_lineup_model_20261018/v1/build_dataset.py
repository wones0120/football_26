"""Read-only full-field audit; bounded deterministic label-independent model cohort."""
from collections import Counter,defaultdict
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import csv,gzip,hashlib,io,json,math,pathlib,re,zipfile
from backend.app.product_services.slate_learning import _parse_lineup,_normalized_name
from backend.app.product_services.lineup_top_decile_research import canonical_roster,lineup_features,top_decile_boundary
ROOT=pathlib.Path(__file__).resolve().parent
DATA=pathlib.Path('/private/tmp/season_accuracy_20261018')
clock=lambda x:(datetime.fromisoformat(str(x)).replace(tzinfo=timezone.utc)if datetime.fromisoformat(str(x)).tzinfo is None else datetime.fromisoformat(str(x)))
load=lambda n:json.loads((DATA/(n+'.json')).read_text())
obs=load('actuals');pred=load('projections');runs=load('runs');files=json.loads((pathlib.Path('research/season_projection_accuracy_20261018/v1/source_completion.json')).read_text())
salary={str(r['curated_salary_id']):r for r in json.loads((ROOT/'salary_scope.json').read_text())}
features={(r['projection_run_id'],r['player_id'],r['game_id']):r for r in json.loads((ROOT/'historical_features_v2.json').read_text())}
by_file=defaultdict(list);by_run=defaultdict(dict)
for r in obs:by_file[r['source_file_id']].append(r)
for r in pred:by_run[r['projection_run_id']][r['player_id']]=r
native=defaultdict(list)
for r in salary.values():native[r['season'],r['week'],r['player_master_id'],r['roster_position']].append(r)
def kickoff(row):
 m=re.search(r'(\d\d/\d\d/\d{4} \d\d:\d\d[AP]M)',str(row.get('game_info','')))
 return datetime.strptime(m[1],'%m/%d/%Y %I:%M%p').replace(tzinfo=ZoneInfo('America/New_York'))if m else None
all_reports=[]
for number,source in enumerate(files,1):
 rows=by_file[source['source_file_id']]
 if not rows:continue
 week=rows[0]['week'];slate=rows[0]['slate'];contest=rows[0]['contest_id'];fmt='showdown'if any(r['roster_position']=='CPT'for r in rows)else'classic'
 native_by_key=defaultdict(list);starts=[]
 for o in rows:
  for cand in o['evidence_json'].get('salary_candidates',[]):
   s=salary.get(str(cand.get('curated_salary_id')))
   if s and s['player_master_id']==o['player_id'] and s['source_player_key']==cand.get('source_player_key'):
    native_by_key[o['player_id'],o['roster_position']].append(s)
    k=kickoff(s)
    if k:starts.append(k)
 lock=min(starts)if starts else None
 eligible=[r for r in runs if r['week']==week and r['slate_id']==slate and r['status']=='completed' and lock and max(clock(r['created_at']),clock(r['model_created_at']))<lock and clock(r['data_cutoff_at'])<=clock(r['created_at'])]
 run=max(eligible,key=lambda r:(clock(r['created_at']),r['projection_run_id']))if eligible else None
 lookup=defaultdict(set);records={};identity_reasons=Counter()
 for o in rows:
  key=o['player_id'],o['roster_position'];choices=[s for s in native_by_key[key]if lock and clock(s['created_at'])<lock]
  semantics={(s['team'],s['opponent'],s['position'],s['salary'])for s in choices}
  if len(semantics)!=1:identity_reasons['native_salary_missing_or_not_pregame_or_ambiguous']+=1;continue
  s=choices[0];p=by_run.get(run['projection_run_id']if run else'',{}).get(o['player_id']);f=features.get((p['projection_run_id'],p['player_id'],p['game_id']))if p else None
  lookup[_normalized_name(o['player_display_name']),o['roster_position']].add(o['player_id'])
  if not p or not f or max(clock(p['created_at']),clock(f['feature_created']),clock(f['feature_run_created']))>=lock:
   continue
  # Optional context clocks cannot be silently used if after decision/lock.
  context=dict(f)
  if f.get('pregame_context_observed_at') and clock(f['pregame_context_observed_at'])>=lock:
   for k in ['targets_mean_3','carries_mean_3','team_implied_total','game_total_line','team_spread_line']:context[k]=None
  records[key]=dict(player_id=o['player_id'],role=o['roster_position']if fmt=='showdown'else'SELECTED',position=s['position'],team=s['team'],game_id=p['game_id'],salary=float(s['salary']),mean=float(p['mean']),p90=float(p['p90']),features=context)
 path=pathlib.Path(source['path']);raw=zipfile.ZipFile(path).read(zipfile.ZipFile(path).namelist()[0])if path.suffix=='.zip'else path.read_bytes()
 reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')));points=[];lineups={};entry_ids=set();duplicate_entry=0
 for row in reader:
  eid=(row.get('EntryId')or'').strip()
  if not eid:continue
  if eid in entry_ids:duplicate_entry+=1;continue
  entry_ids.add(eid)
  try:score=float(row.get('Points'));remaining=float(row.get('TimeRemaining'))
  except(TypeError,ValueError):continue
  if not math.isfinite(score)or remaining!=0:continue
  points.append(score);text=(row.get('Lineup')or'').strip()
  if text:
   if text not in lineups:lineups[text]=dict(points=score,multiplicity=0,entry_examples=[])
   d=lineups[text];d['multiplicity']+=1
   if len(d['entry_examples'])<2:d['entry_examples'].append(eid)
   if abs(score-d['points'])>.025:d['conflicting_points']=True
 boundary=top_decile_boundary(points);cohort={};reasons=Counter();valid_entries=0
 for text,meta in lineups.items():
  if meta.get('conflicting_points'):reasons['same_roster_conflicting_points']+=1;continue
  parsed=_parse_lineup(text);players=[];failed=None
  for token in parsed:
   role=token['roster_position'];slots=[role]if fmt=='showdown'or role!='FLEX'else['RB','WR','TE'];matches={(pid,slot)for slot in slots for pid in lookup.get((_normalized_name(token['player_display_name']),slot),set())}
   if len({pid for pid,slot in matches})!=1:failed='canonical_identity_not_unique_in_native_contest_slot';break
   pid,slot=next(iter(matches));record=records.get((pid,slot))
   if not record:failed='original_pregame_projection_feature_or_native_salary_unavailable';break
   players.append(record)
  if failed:reasons[failed]+=1;continue
  try:sig=canonical_roster(players,fmt);x=lineup_features(players,fmt)
  except ValueError:reasons['invalid_roster_or_original_feature_values']+=1;continue
  valid_entries+=meta['multiplicity'];key=hashlib.sha256(json.dumps(sig).encode()).hexdigest()
  if key not in cohort:
   try:rich=lineup_features(players,fmt,rich=True)
   except ValueError:rich=None
   cohort[key]=dict(roster_key=key,signature=sig,features=x,rich_features=rich,points=meta['points'],label=int(meta['points']>=boundary['points_cutoff']),multiplicity=0,entry_examples=meta['entry_examples'])
  cohort[key]['multiplicity']+=meta['multiplicity']
 sampled=sorted(cohort.values(),key=lambda r:r['roster_key'])[:5000]
 report=dict(contest_id=contest,source_file_id=source['source_file_id'],season=2026,week=week,slate=slate,contest_format=fmt,lock_at=lock.isoformat()if lock else None,projection_run_id=run['projection_run_id']if run else None,model_id=run['model_id']if run else None,projection_stored_at=run['created_at']if run else None,**boundary,unique_raw_rosters=len(lineups),duplicate_entry_rows=duplicate_entry,scoreable_distinct_rosters=len(cohort),scoreable_entries=valid_entries,unscoreable_distinct_roster_reasons=dict(reasons),identity_observation_reasons=dict(identity_reasons),sampled_rosters=len(sampled),rich_sampled_rosters=sum(r['rich_features']is not None for r in sampled),coverage_upper_bound_top10_candidates=sum(r['label']for r in sampled),chronology='physical storage prelock verified; independent original source/code capture not certified')
 out=dict(context=report,rosters=sampled)
 (ROOT/'contests').mkdir(exist_ok=True)
 with gzip.open(ROOT/'contests'/f'{contest}_{source["source_file_id"][-8:]}.json.gz','wt')as f:json.dump(out,f,allow_nan=False)
 all_reports.append(report)
 print(number,week,slate,fmt,'field',len(points),'unique',len(lineups),'scoreable',len(cohort),'sample',len(sampled),'run',str(report['projection_run_id'])[:8],flush=True)
(ROOT/'dataset_inventory.json').write_text(json.dumps(all_reports,indent=2))
