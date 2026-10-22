import json,pathlib,datetime as dt,zoneinfo,collections,csv,zipfile,io,math,statistics,hashlib
p=pathlib.Path('/private/tmp/season_accuracy_20261018');load=lambda n:json.loads((p/(n+'.json')).read_text());schedules=load('schedule');runs={r['projection_run_id']:r for r in load('runs')};pred=load('projections');actual=load('actuals');salary=load('salary');files=load('allfiles');paths=(p/'paths.txt').read_text().splitlines();tz=zoneinfo.ZoneInfo('America/New_York');parse=lambda x:dt.datetime.fromisoformat(x)
games={r['game_id']:r for r in schedules};kick={k:dt.datetime.fromisoformat(r['raw_row_json']['gameday']+'T'+r['raw_row_json']['gametime']).replace(tzinfo=tz)for k,r in games.items() if r['raw_row_json'].get('gametime')}
# Check immutable source hash, all nonblank remaining-time rows, never treat missing clock as final.
checks={}
for f in files:
 candidates=[f['original_path']]+[x for x in paths if pathlib.Path(x).name==f['file_name']];status={'source_file_id':f['source_file_id'],'file_name':f['file_name'],'status':'source_missing'}
 for loc in dict.fromkeys(candidates):
  path=pathlib.Path(loc)
  if not path.exists():continue
  data=path.read_bytes()
  raw=zipfile.ZipFile(io.BytesIO(data)).read(zipfile.ZipFile(io.BytesIO(data)).namelist()[0])if path.suffix=='.zip' else data
  if hashlib.sha256(data).hexdigest()!=f['content_sha256'] and hashlib.sha256(raw).hexdigest()!=f['content_sha256']:continue
  reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')));remaining=[]
  for row in reader:
   x=row.get('TimeRemaining')
   if x is not None and x.strip():
    try:remaining.append(float(x))
    except ValueError:pass
  status.update(path=str(path),sha256_verified=True,rows_with_time=len(remaining),max_time_remaining=max(remaining)if remaining else None,status='final'if remaining and max(remaining)==0 else 'completion_unverified');break
 checks[f['source_file_id']]=status
(p/'completion.json').write_text(json.dumps(list(checks.values()),indent=2))
# canonical salary mapping, exact opposing team pair + season/week (not names).
pg=collections.defaultdict(set);sal=collections.defaultdict(list)
for r in salary:
 if not r['player_master_id']:continue
 for gid,g in games.items():
  if g['week']==r['week'] and {g['home_team'],g['away_team']}=={r['team'],r['opponent']}:pg[r['week'],r['player_master_id']].add(gid)
 sal[r['week'],r['player_master_id']].append(r)
obs=collections.defaultdict(list);unmatched=0
for r in actual:
 if checks.get(r['source_file_id'],{}).get('status')!='final':continue
 gs=pg[r['week'],r['player_id']]
 if len(gs)!=1:unmatched+=1;continue
 gid=next(iter(gs));obs[gid,r['player_id']].append((r['actual_points']/(1.5 if r['roster_position']=='CPT'else 1),r))
truth={};conflicts=[]
for key,v in obs.items():
 vals=[x[0]for x in v]
 if max(vals)-min(vals)>.025:conflicts.append({'key':key,'values':sorted(set(vals))});continue
 truth[key]=statistics.median(vals)
# Predeclared descriptive forecast rule latest physically stored projection AND model run before game kickoff, cutoff <= creation and kickoff. Original source availability/code replay not verified -> strict aggregate unavailable.
choices=collections.defaultdict(list);excluded=collections.Counter()
for r in pred:
 key=r['game_id'],r['player_id'];run=runs[r['projection_run_id']];lock=kick.get(r['game_id'])
 if key not in truth:continue
 if not lock:excluded['no_kickoff']+=1;continue
 clocks=[parse(r['created_at']),parse(run['created_at']),parse(run['model_created_at'])]
 if any(t>=lock for t in clocks) or parse(r['data_cutoff_at'])>min(clocks):excluded['not_stored_pregame_or_inconsistent_cutoff']+=1;continue
 choices[key].append(r)
rows=[]
for key,opts in choices.items():
 opts.sort(key=lambda r:(parse(runs[r['projection_run_id']]['created_at']),parse(r['created_at']),r['projection_run_id']),reverse=True);r=opts[0];run=runs[r['projection_run_id']];a=truth[key];salaryrows=[s for s in sal[r['week'],r['player_id']]if parse(s['created_at']).replace(tzinfo=tz) <kick[r['game_id']]]
 rows.append(dict(game_id=key[0],player_id=key[1],name=r['full_name'],position=r['position'],week=r['week'],mean=r['mean'],actual=a,p10=r['p10'],p90=r['p90'],model_id=run['model_id'],projection_run_id=r['projection_run_id'],stored_at=run['created_at'],cutoff=r['data_cutoff_at'],kickoff=kick[r['game_id']].isoformat(),pregame_salary=max([s['salary']for s in salaryrows if s['salary']is not None],default=None),provenance='stored_before_kickoff_sources_and_original_code_not_independently_verified'))
def metrics(rs):
 n=len(rs);err=[r['mean']-r['actual']for r in rs];q=[r for r in rs if r['p90']is not None];iv=[r for r in q if r['p10']is not None and r['p10']<=r['p90']]
 return dict(n=n,games=len(set(r['game_id']for r in rs)),mae=sum(abs(x)for x in err)/n if n else None,rmse=math.sqrt(sum(x*x for x in err)/n)if n else None,bias=sum(err)/n if n else None,p90_n=len(q),p90_exceed=sum(r['actual']>r['p90']for r in q)/len(q)if q else None,p10_p90_coverage=sum(r['p10']<=r['actual']<=r['p90']for r in iv)/len(iv)if iv else None,interval_n=len(iv))
regular=[r for r in rows if r['mean']>=5] # forecast-defined, fixed before reporting outcomes; includes legitimate zeros
out={'selection_rule':'latest physically stored pre-kickoff forecast per canonical player-game across slates; model creation pre-kickoff; cutoff<=creation; independent source and original code chronology unverified','regular_cohort':'predicted mean >=5 DK points (pre-outcome, no actual threshold)','strict_verified_n':0,'source_completion':dict(collections.Counter(x['status']for x in checks.values())),'unmapped_observations':unmatched,'conflicting_actuals':conflicts,'canonical_actual_playergames':len(truth),'forecast_matched_playergames':len(rows),'excluded_forecast_variants':dict(excluded),'all':metrics(rows),'regular':metrics(regular)}
for label,key in [('by_week','week'),('by_position','position'),('by_model','model_id')]:
 out[label]={str(v):{'all':metrics([r for r in rows if r[key]==v]),'regular':metrics([r for r in regular if r[key]==v])}for v in sorted(set(r[key]for r in rows),key=str)}
out['largest_errors']=sorted(rows,key=lambda r:abs(r['mean']-r['actual']),reverse=True)[:20]
(p/'rows.json').write_text(json.dumps(rows,indent=2));(p/'summary.json').write_text(json.dumps(out,indent=2));print(json.dumps({k:v for k,v in out.items()if k not in['largest_errors','conflicting_actuals','by_model']},indent=2))
