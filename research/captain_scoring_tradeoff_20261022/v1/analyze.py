"""Retrospective imported-winner analysis and research-only actual-score solves."""
from collections import defaultdict, Counter
import csv
import gzip
import hashlib
import html
import json
from pathlib import Path
import numpy as np
import pulp
from scripts.analyze_showdown_qb_construction import salary_pools, select_pool, build_resolver, parse_lineup, raw_to_salary, team

OUT = Path(__file__).parent
manifest = json.loads((OUT/'manifest.json').read_text())
assert hashlib.sha256((OUT/'inputs.json.gz').read_bytes()).hexdigest() == manifest['sha256']
d = json.load(gzip.open(OUT/'inputs.json.gz','rt'))
aliases = defaultdict(list)
for a in d['aliases']:
    aliases[str(a['source_key'])].append(a)
pools = salary_pools(d['salaries']+[raw_to_salary(r,aliases) for r in d['raw_salaries']])
entries = defaultdict(list)
for r in d['entries']:
    entries[r['contest_id']].append(r)
groups = defaultdict(list)
for c in d['contests']:
    groups[(c['week'],c['slate_id'])].append(c)

def solve(players, forced=None):
    """Native salary, six unique players, one Captain, both teams; no strategy rules."""
    m=pulp.LpProblem('postgame_research',pulp.LpMaximize)
    x={p['id']:pulp.LpVariable('f'+str(i),cat='Binary') for i,p in enumerate(players)}
    y={p['id']:pulp.LpVariable('c'+str(i),cat='Binary') for i,p in enumerate(players)}
    m += pulp.lpSum(p['points']*(x[p['id']]+1.5*y[p['id']]) for p in players)
    m += pulp.lpSum(x.values())==5
    m += pulp.lpSum(y.values())==1
    for p in players: m += x[p['id']]+y[p['id']]<=1
    m += pulp.lpSum(p['flex_salary']*x[p['id']]+p['captain_salary']*y[p['id']] for p in players)<=50000
    for tm in {p['team'] for p in players}:
        m += pulp.lpSum(x[p['id']]+y[p['id']] for p in players if p['team']==tm)>=1
    if forced is not None:
        m += pulp.lpSum(y[p['id']] for p in players if p['id'] in forced)==1
    status=m.solve(pulp.PULP_CBC_CMD(msg=False,timeLimit=15))
    if status!=pulp.LpStatusOptimal:
        return {'status':pulp.LpStatus[status]}
    roster=[dict(p,slot='CPT' if y[p['id']].value()>.5 else 'FLEX') for p in players if x[p['id']].value()+y[p['id']].value()>.5]
    cap=next(p for p in roster if p['slot']=='CPT')
    score=sum(p['points']*(1.5 if p['slot']=='CPT' else 1) for p in roster)
    salary=sum(p['captain_salary'] if p['slot']=='CPT' else p['flex_salary'] for p in roster)
    assert len(roster)==6 and len({p['id'] for p in roster})==6 and salary<=50000 and len({p['team'] for p in roster})==2
    return dict(status='Optimal',points=round(score,3),salary=salary,captain=cap['name'],captain_id=cap['id'],captain_points=cap['points'],roster=roster)

games=[];winners=[];excluded=[]
for (week,slate),cts in sorted(groups.items()):
    rows=[r for c in cts for r in entries[c['contest_id']]]
    key,salary_rows,coverage=select_pool(cts[0],rows,pools)
    if key is None or key[1]!=week or not any(r['roster_position']=='CPT' for r in salary_rows):
        excluded.append(dict(week=week,slate=slate,reason='missing_or_ambiguous_native_salary',selected_key=key));continue
    resolve=build_resolver(key,salary_rows,[])
    players={}
    for r in salary_rows:
        p=resolve('FLEX',r['player_name']);cp=resolve('CPT',r['player_name'])
        if p and cp and p['id']==cp['id'] and p['flex_salary'] is not None and cp['salary'] is not None:
            players[p['id']]={**p,'captain_salary':cp['salary']}
    cidset={c['contest_id'] for c in cts}
    values=defaultdict(set)
    for o in d['observations']:
        if o['contest_id'] in cidset and o['resolution_status']=='resolved' and o['player_id'] and o['actual_points'] is not None:
            values[str(o['player_id'])].add(round(float(o['actual_points'])/(1.5 if o['roster_position']=='CPT' else 1),2))
    conflicts={pid:sorted(v) for pid,v in values.items() if len(v)>1}
    actual={pid:next(iter(v)) for pid,v in values.items() if len(v)==1}
    equations=[]
    parsed={}
    for r in rows:
        parts=parse_lineup(r['lineup_text'])
        rr=[resolve(slot,name) for slot,name in parts] if parts else []
        if len(rr)==6 and all(rr) and len({p['id'] for p in rr})==6 and all(p['id'] in players for p in rr):
            parsed[r['lineup_text']]=rr
            if r['entry_points'] is not None: equations.append((rr,float(r['entry_points'])))
    observed_ids=sorted({p['id'] for rr,_ in equations for p in rr})
    score_basis='canonical imported player observations'
    if equations and any(pid not in actual for pid in observed_ids):
        ix={pid:i for i,pid in enumerate(observed_ids)}
        a=np.zeros((len(equations),len(ix)));b=np.array([v for _,v in equations])
        for j,(rr,_) in enumerate(equations):
            for i,p in enumerate(rr):a[j,ix[p['id']]]=1.5 if i==0 else 1
        sol,_,rank,_=np.linalg.lstsq(a,b,rcond=None);sol=np.round(sol,2)
        residual=float(np.max(np.abs(a@sol-b)))
        if rank==len(ix) and residual<=.06 and not conflicts and all(abs(sol[ix[pid]]-v)<=.02 for pid,v in actual.items() if pid in ix):
            actual.update({pid:float(sol[i]) for pid,i in ix.items()})
            score_basis=f'Imported observations plus unique full-rank reconstruction from {len(equations)} lineup totals; max residual {residual:.6f}'
    known=[dict(p,points=actual[pid]) for pid,p in players.items() if pid in actual and pid not in conflicts]
    if not known:
        excluded.append(dict(week=week,slate=slate,reason='no_scores'));continue
    top=max(p['points'] for p in known);leaders=[p for p in known if abs(p['points']-top)<.001]
    schedule=[r for r in d['schedule'] if r['week']==week and tuple(sorted((team(r['home_team']),team(r['away_team']))))==key[3]]
    schedule.sort(key=lambda r:r['raw_nfl_schedule_id'],reverse=True)
    context=schedule[0]['raw_row_json'] if schedule else None
    optimal=solve(known)
    top_forced=solve(known,{p['id'] for p in leaders})
    g=dict(game='W'+str(week)+' '+ '/'.join(key[3]),week=week,slate=slate,teams=key[3],salary_key=key,contests=len(cts),
           top_scorers=[{'name':p['name'],'id':p['id'],'points':p['points'],'flex_salary':p['flex_salary']} for p in leaders],
           players=known,missing_scores=[p['name'] for pid,p in players.items() if pid not in actual],conflicts=conflicts,
           score_basis=score_basis,optimal_known_pool=optimal,top_scorer_captain_known_pool=top_forced,context=context)
    games.append(g)
    for c in cts:
        cr=entries[c['contest_id']]
        complete=sum(r['n'] for r in cr)==c['field_size']
        for r in cr:
            if r['rank']!=1:continue
            rr=parsed.get(r['lineup_text'])
            reason=None
            if not complete:reason='incomplete_field'
            elif not rr:reason='unresolved_roster'
            elif any(p['id'] not in actual or p['id'] in conflicts for p in rr):reason='missing_or_conflicting_scores'
            if reason:
                excluded.append(dict(contest_id=c['contest_id'],reason=reason,rank=1,n=r['n']));continue
            score=sum(actual[p['id']]*(1.5 if i==0 else 1) for i,p in enumerate(rr))
            total_salary=sum(p['salary'] for p in rr)
            if abs(score-float(r['entry_points']))>.06 or total_salary>50000:
                excluded.append(dict(contest_id=c['contest_id'],reason='score_or_salary_mismatch'));continue
            cap=rr[0];points=actual[cap['id']]
            swaps=[dict(name=p['name'],gain=round(.5*(actual[p['id']]-points),3),new_salary=total_salary+.5*(p['flex_salary']-cap['flex_salary'])) for p in rr[1:] if total_salary+.5*(p['flex_salary']-cap['flex_salary'])<=50000+.01 and actual[p['id']]>points+.001]
            winners.append(dict(contest_id=c['contest_id'],source_file_id=c['source_file_id'],contest_name=c['contest_name'],game=g['game'],week=week,slate=slate,
                n=r['n'],field_size=c['field_size'],captain=cap['name'],captain_id=cap['id'],position=cap['position'],captain_flex_salary=cap['flex_salary'],captain_points=points,
                scoring_rank=1+sum(p['points']>points+.001 for p in known),top_scorer=abs(points-top)<.001,top_score=top,
                salary=total_salary,points=round(score,3),top_player_in_roster=any(p['id'] in {a['id'] for a in leaders} for p in rr),
                legal_improving_swaps=swaps,roster=[dict(p,points=actual[p['id']],slot='CPT' if i==0 else 'FLEX') for i,p in enumerate(rr)],
                signature=sorted((p['id'],i==0) for i,p in enumerate(rr))))
    print(g['game'], 'known',len(known),'missing',len(g['missing_scores']),'top',[p['name'] for p in leaders], 'optimal',optimal.get('captain'), 'topforce gap',round(optimal.get('points',0)-top_forced.get('points',0),3),flush=True)

contest_flags=defaultdict(set);game_flags=defaultdict(set)
for w in winners:
    contest_flags[w['contest_id']].add(w['top_scorer']);game_flags[w['game']].add(w['top_scorer'])
summary=dict(contests_imported=len(d['contests']),games_with_native_salaries=len(games),rank1_roster_variants=len(winners),rank1_entries=sum(w['n'] for w in winners),
    contests_evaluated=len(contest_flags),contests_all_winners_top=sum(v=={True} for v in contest_flags.values()),contests_no_winner_top=sum(v=={False} for v in contest_flags.values()),contests_mixed=sum(len(v)>1 for v in contest_flags.values()),
    games_evaluated=len(game_flags),games_all_winners_top=sum(v=={True} for v in game_flags.values()),games_no_winner_top=sum(v=={False} for v in game_flags.values()),games_mixed=sum(len(v)>1 for v in game_flags.values()))
report=dict(summary=summary,games=games,winners=winners,excluded=excluded,limitations=[
    'Retrospective analysis of previously inspected outcomes; no held-out predictive claims.',
    'Game scoring ranks and actual-score optima use scored players in the stored native salary pool; missing scores never become zero.',
    'Reconstructed points are identified separately from original imported player observations.',
    'Research solves do not generate operational saved lineups; no model or live setting changed.',
    'Schedule game context is retrospective; archived market lines lack verified prelock availability here.',
    'Multiple contests and tied entries from one game are dependent evidence; report distinct-game counts separately.'
])
(OUT/'report.json').write_text(json.dumps(report,indent=2,default=str)+'\n')
fields=['game','contest_id','field_size','n','captain','captain_flex_salary','captain_points','scoring_rank','top_score','top_player_in_roster','salary','points']
with (OUT/'winners.csv').open('w') as f:
    writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(winners)
print(json.dumps(summary,indent=2))
