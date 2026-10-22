import json,statistics,collections
from pathlib import Path
p=Path('/private/tmp/wones_analyst_20261021_v1')
read=lambda n:json.loads((p/(n+'_capture.json')).read_text())['rows']
a=read('aliases'); st=read('stats'); sn=read('snaps');sal=read('salary')
keys=collections.defaultdict(set)
for r in a:keys[(r['source_system'],r['source_key'])].add(r['player_master_id'])
stat_by=collections.defaultdict(list);snap_by=collections.defaultdict(list)
for r in st:
 ids=keys[('nflreadpy',r['player_id'])]
 if len(ids)==1:stat_by[next(iter(ids))].append(r)
for r in sn:
 ids=keys[('pfr',r['pfr_player_id'])]
 if len(ids)==1:snap_by[next(iter(ids))].append(r)
summary=[]
for s in sal:
 pid=s['player_master_id'];rows=[r for r in stat_by[pid] if r['team']==s['team']];snaps=[r for r in snap_by[pid] if r['team']==s['team']]
 hist=[{'week':r['week'],'raw_row_id':r['raw_nfl_weekly_stat_id'],'ingest_run_id':r['ingest_run_id'],**{k:r['raw_row_json'].get(k) for k in ['carries','targets','attempts','target_share','receiving_yards','rushing_yards','passing_yards','passing_tds','rushing_tds','receiving_tds']}} for r in rows]
 item={'player_master_id':pid,'name':s['player_name'],'team':s['team'],'position':s['position'],'salary':s['salary'],'salary_row_id':s['curated_salary_id'],'source_native_key':s['source_player_key'],'game_info':s['game_info'],'observed_usage':hist,'observed_snaps':[{'week':r['week'],'offense_snaps':r['offense_snaps'],'offense_pct':r['offense_pct'],'raw_row_id':r['raw_nfl_snap_count_id'],'ingest_run_id':r['ingest_run_id']} for r in snaps],'coverage':'No record means unknown; observed boxes only, no absent games filled; historical means use observed last3records.'}
 for k in ['carries','targets','attempts']:
  vals=[r[k] for r in hist[-3:] if isinstance(r[k],(int,float))];item[k+'_last3_observed_mean']=round(statistics.mean(vals),2) if vals else None
 summary.append(item)
(p/'usage_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
for g in sorted({x['game_info'] for x in summary}):
 print('\n'+g)
 for t in sorted({x['team'] for x in summary if x['game_info']==g}):
  sel=[x for x in summary if x['team']==t and x['position'] in ['QB','RB','WR','TE']];sel.sort(key=lambda x:(x['targets_last3_observed_mean'] or 0)+(x['carries_last3_observed_mean'] or 0)+(x['attempts_last3_observed_mean'] or 0),reverse=True)
  for x in sel[:7]:print(x['team'],x['name'],x['salary'],'C/T/A',x['carries_last3_observed_mean'],x['targets_last3_observed_mean'],x['attempts_last3_observed_mean'],'snaps',[(r['week'],r['offense_pct']) for r in x['observed_snaps'][-2:]])
