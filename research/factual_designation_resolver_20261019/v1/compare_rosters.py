"""Unsaved exhaustive standalone research, exact saved LP, original base means."""
import itertools,json,hashlib,time
from pathlib import Path
root=Path(__file__).parent;source=root/'monday_optimizer.json';x=json.loads(source.read_text());s=x['football_analyst']['input_snapshot'];ps=s['players'];cs=s['model']['constraints'];began=time.monotonic()
caps=[i for i in range(len(ps)) if not any(c['sense']==0 and c['constant']==0 and c['coefficients']==[{'name':f'captain_{i}','value':1}] for c in cs)]
rows=[]
for cap in caps:
 for flex in itertools.combinations([i for i in range(len(ps)) if i!=cap],5):
  chosen={f'captain_{cap}',*(f'flex_{i}' for i in flex)}
  legal=True
  for c in cs:
   value=c['constant']+sum(a['value'] for a in c['coefficients'] if a['name'] in chosen)
   if (c['sense']==-1 and value>1e-7) or (c['sense']==1 and value < -1e-7) or (c['sense']==0 and abs(value)>1e-7):legal=False;break
  if not legal:continue
  roster=[dict(name=ps[i]['name'],player_id=ps[i]['player_id'],role='CPT' if i==cap else 'FLEX',native_id=ps[i].get('dk_captain_id') if i==cap else ps[i].get('dk_player_id'),base_salary=ps[i]['salary'],salary=ps[i]['salary']*(1.5 if i==cap else 1),base_mean=ps[i]['projection']) for i in [cap,*flex]]
  rows.append(dict(roster=roster,salary=sum(p['salary'] for p in roster),mean=sum(p['base_mean']*(1.5 if p['role']=='CPT' else 1) for p in roster)))
rows.sort(key=lambda r:(-r['mean'],r['salary'],str(r['roster'])))
def best(pred):return next((r for r in rows if pred(r)),None)
def names(r):return {p['name'] for p in r['roster']}
results={'highest_mean_control':rows[0],
 'no_watkins':best(lambda r:'Jordan Watkins' not in names(r)),
 'mclaurin_no_watkins':best(lambda r:'Terry McLaurin' in names(r) and 'Jordan Watkins' not in names(r)),
 'mclaurin_no_watkins_max_one_kicker':best(lambda r:'Terry McLaurin' in names(r) and 'Jordan Watkins' not in names(r) and len(names(r)&{'Drew Stevens','Eddy Pineiro'})<=1),
 'mclaurin_kittle_no_watkins':best(lambda r:{'Terry McLaurin','George Kittle'}<=names(r) and 'Jordan Watkins' not in names(r)),
 'mclaurin_captain_no_watkins':best(lambda r:r['roster'][0]['name']=='Terry McLaurin' and 'Jordan Watkins' not in names(r))}
assert abs(results['highest_mean_control']['mean']-x['gpp_recommendation']['recommended']['projected_points'])<1e-9
out=dict(status='UNSAVED_STANDALONE_RESEARCH',source_run=x['job_id'],source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),legal_count=len(rows),captains=[ps[i]['name'] for i in caps],elapsed_seconds=time.monotonic()-began,scope='All current saved LP constraints, original FP means, no preferences or projections changed. One-kicker branch is a comparison condition only, not a user setting. Standalone comparisons do not assert four-entry exposure compliance.',comparisons=results)
(root/'roster_comparisons.json').write_text(json.dumps(out,indent=2))
for k,r in results.items():print(k,None if not r else (r['salary'],round(r['mean'],6),[(p['role'],p['name'],p['native_id']) for p in r['roster']]))
print('count',len(rows),'seconds',out['elapsed_seconds'])
