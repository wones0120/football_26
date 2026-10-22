"""Unsaved frozen comparisons; no solver, API mutation, or model fitting."""
import itertools,json,hashlib
from pathlib import Path
ROOT=Path(__file__).parent
source=Path('research/sunday_night_results_monday_refresh_20261019/v1/monday_optimizer.json')
x=json.loads(source.read_text()); s=x['football_analyst']['input_snapshot']
players=s['players']; constraints=s['model']['constraints']
def enumerate_rows(conditional=False):
    ps=list(players)
    cs=json.loads(json.dumps(constraints))
    if conditional:
        mc=next(p for p in x['player_pool']['rows'] if p['player_id']=='6031d562-62b5-4ac6-a6a7-ea36ce773116')
        ps.append(dict(mc,name=mc['player_name']))
        # Add FLEX-only McLaurin as a WAS WR to each generic constraint that
        # contains Antonio FLEX. Salary is his own; original CMC leader retained.
        for c in cs:
            if c['name']=='unique_player_13': continue
            old=next((v['value'] for v in c['coefficients'] if v['name']=='flex_13'),None)
            if old is not None:
                c['coefficients'].append({'name':'flex_15','value':8000 if c['name']=='salary_cap' else old})
    rows=[]
    captains=[i for i in range(15) if not any(c['sense']==0 and c['constant']==0 and c['coefficients']==[{'name':f'captain_{i}','value':1}] for c in cs)]
    for cap in captains:
        for flex in itertools.combinations([i for i in range(len(ps)) if i!=cap],5):
            if conditional and 15 not in flex:continue
            chosen={f'captain_{cap}',*(f'flex_{i}' for i in flex)}
            valid=True
            for c in cs:
                v=c['constant']+sum(a['value'] for a in c['coefficients'] if a['name'] in chosen)
                if (c['sense']==-1 and v>1e-7) or (c['sense']==1 and v < -1e-7) or (c['sense']==0 and abs(v)>1e-7):valid=False;break
            if not valid:continue
            roster=[dict(name=ps[i]['name'],player_master_id=ps[i].get('player_master_id',ps[i].get('player_id')),role='CPT' if i==cap else 'FLEX',salary=ps[i]['salary']*(1.5 if i==cap else 1),base_mean=ps[i]['projection']) for i in [cap,*flex]]
            rows.append(dict(roster=roster,salary=sum(p['salary'] for p in roster),mean=sum(p['base_mean']*(1.5 if p['role']=='CPT' else 1) for p in roster)))
    return sorted(rows,key=lambda r:(-r['mean'],r['salary'],str(r['roster'])))
normal=enumerate_rows(); conditional=enumerate_rows(True)
def best(rows,predicate):return next((r for r in rows if predicate(r)),None)
names=lambda r:{p['name'] for p in r['roster']}
out=dict(status='UNSAVED_RESEARCH_COMPARISONS',source_run='8a4a1d21-4b13-4ed0-baf4-b48d95da967e',source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),normal_legal_count=len(normal),conditional_mclaurin_flex_count=len(conditional),conditional_scope='McLaurin FLEX-only; waive only his native-Q exclusion, preserve all original constraints including CMC required; no Captain eligibility conclusion; no live preference change',comparisons={
 'highest_mean_control':normal[0],
 'no_watkins':best(normal,lambda r:'Jordan Watkins' not in names(r)),
 'kittle_flex_no_watkins':best(normal,lambda r:'George Kittle' in names(r) and r['roster'][0]['name']!='George Kittle' and 'Jordan Watkins' not in names(r)),
 'kittle_captain_no_watkins':best(normal,lambda r:r['roster'][0]['name']=='George Kittle' and 'Jordan Watkins' not in names(r)),
 'cmc_captain_no_fringe_sf_receivers':best(normal,lambda r:r['roster'][0]['name']=='Christian McCaffrey' and not names(r)&{'Jordan Watkins','Jacob Cowing','Brandin Cooks'}),
 'cmc_captain_no_watkins':best(normal,lambda r:r['roster'][0]['name']=='Christian McCaffrey' and 'Jordan Watkins' not in names(r)),
 'conditional_mclaurin_no_watkins':best(conditional,lambda r:'Jordan Watkins' not in names(r))})
(ROOT/'comparison.json').write_text(json.dumps(out,indent=2))
for k,r in out['comparisons'].items():print(k, None if not r else (r['salary'],r['mean'],[(p['role'],p['name']) for p in r['roster']]))
print('counts',len(normal),len(conditional))
