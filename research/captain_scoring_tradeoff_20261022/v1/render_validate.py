"""Verify reported joins/scoring and render the retrospective comparison."""
from collections import Counter
import gzip
import hashlib
import html
import json
from pathlib import Path
from scripts.analyze_showdown_qb_construction import salary_pools,build_resolver,parse_lineup,raw_to_salary

out=Path(__file__).parent
r=json.loads((out/'report.json').read_text())
d=json.load(gzip.open(out/'inputs.json.gz','rt'))
aliases={}
for a in d['aliases']: aliases.setdefault(str(a['source_key']),[]).append(a)
pools=salary_pools(d['salaries']+[raw_to_salary(a,aliases) for a in d['raw_salaries']])
checks=Counter();bad=[]
for g in r['games']:
    key=tuple(g['salary_key'][:3])+(tuple(g['salary_key'][3]),)
    resolve=build_resolver(key,pools[key],[])
    actual={p['id']:p['points'] for p in g['players']}
    cids={c['contest_id'] for c in d['contests'] if c['week']==g['week'] and c['slate_id']==g['slate']}
    for e in d['entries']:
        if e['contest_id'] not in cids:continue
        parts=parse_lineup(e['lineup_text']);rr=[resolve(s,n) for s,n in parts] if parts else []
        if len(rr)!=6 or not all(rr) or len({p['id'] for p in rr})!=6:
            checks['unresolved_roster_variants']+=1;continue
        if any(p['id'] not in actual for p in rr) or e['entry_points'] is None:
            checks['missing_score_roster_variants']+=1;continue
        total=sum(actual[p['id']]*(1.5 if i==0 else 1) for i,p in enumerate(rr))
        checks['scored_roster_variants']+=1
        if abs(total-float(e['entry_points']))>.06:bad.append({'contest_id':e['contest_id'],'rank':e['rank'],'difference':total-float(e['entry_points'])})
    o=g['optimal_known_pool'];t=g['top_scorer_captain_known_pool']
    assert o['status']==t['status']=='Optimal' and o['points']+.001>=t['points']
    for w in r['winners']:
        if w['game']==g['game']: assert o['points']+.061>=w['points']
checks['score_mismatch_roster_variants']=len(bad)
validation={'checks':dict(checks),'mismatches':bad,'source_sha256':hashlib.sha256((out/'inputs.json.gz').read_bytes()).hexdigest(),
            'code_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.glob('*.py')}}
(out/'validation.json').write_text(json.dumps(validation,indent=2)+'\n')
assert not bad, 'Investigate score mismatches before delivery'

esc=lambda x:html.escape(str(x))
def table(headers,rows):
    return '<table><thead><tr>'+''.join('<th>'+esc(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table>'
body='<h1>2026 Captain: highest scorer versus salary savings</h1><p>Local imported evidence captured '+esc(json.loads((out/'manifest.json').read_text())['captured_at'])+'. Retrospective research only; no DraftKings browsing or live lineup generation.</p>'
body+='<p>41 contests across 18 games. All first-place rosters used the highest recorded scorer in 27 contests; lower scorers in 14. Across distinct games: 11 had only highest-scorer winners, four only lower-scorer winners, and three had different Captain strategies win different contests.</p>'
body+='<p>Actual-score optimization over the scored native salary pools favored a highest scorer in 13 of 18 games, and a lower scorer in five. These are hindsight optima within available data, not observed contest winners or predictive success rates.</p>'
body+='<h2>Observed first-place Captains</h2>'
rows=[]
for g in r['games']:
    ws=[w for w in r['winners'] if w['game']==g['game']]
    caps=sorted({(w['captain'],w['scoring_rank']) for w in ws})
    rows.append([g['game'],len({w['contest_id'] for w in ws}),', '.join(f'{n} (#{rank})' for n,rank in caps),', '.join(p['name'] for p in g['top_scorers']),len(g['missing_scores'])])
body+=table(['Game','Contests','Winning Captains (base-score rank)','Highest recorded scorer','Missing player scores'],rows)
body+='<h2>Salary-tradeoff exceptions</h2><p>For each game below, compare the best legal lineup over scored players with the best one requiring a highest scorer at Captain. Rules: six unique players, one Captain, both teams, native slot salaries, $50,000 limit. No exact team split or strategy constraints.</p>'
for g in r['games']:
    o=g['optimal_known_pool'];t=g['top_scorer_captain_known_pool']
    if o['points']-t['points']<.001:continue
    body+='<h3>'+esc(g['game'])+'</h3>'
    body+=table(['Construction','Captain','Total points','Salary'],[['Best scored-pool lineup',o['captain'],o['points'],o['salary']],['Highest scorer at Captain',t['captain'],t['points'],t['salary']]])
    for label,a in [('Best scored-pool roster',o),('Highest-scorer Captain roster',t)]:
        body+='<h4>'+esc(label)+'</h4>'+table(['Slot','Player','Team','Base points','Slot salary'],[[p['slot'],p['name'],p['team'],p['points'],p['captain_salary'] if p['slot']=='CPT' else p['flex_salary']] for p in sorted(a['roster'],key=lambda p:p['slot']!='CPT')])
body+='<h2>How to evaluate the tradeoff</h2><p>If the same six players fit either way, the highest scorer should be Captain to maximize actual points. Moving a player from FLEX to Captain adds half their base salary and half their base points. When both candidate Captains remain rostered, compare the additional FLEX points enabled by salary savings with half the difference in their base points. Different six-player sets require comparing complete lineups.</p>'
body+='<h2>Limits and verification</h2><ul>'+''.join('<li>'+esc(x)+'</li>' for x in r['limitations'])+'</ul>'
body+='<p>97 salary-pool player scores are missing across the 18 games. Highest scorer means highest among recorded/reconstructed scores; this is not proof of complete official scoring coverage. Full-rank reconstructed scores are labeled per game in report.json. Missing scores are never replaced by zero.</p>'
body+='<p>Validation: '+esc(dict(checks))+'. All evaluated winners reconcile to imported lineup totals; all research solves returned Optimal.</p>'
(out/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>2026 Captain scoring tradeoffs</title><style>body{font:16px system-ui;max-width:1200px;margin:40px auto;padding:0 20px;color:#172332;line-height:1.5}table{border-collapse:collapse;width:100%;margin:18px 0 30px}th,td{padding:9px 12px;border:1px solid #ccd5df;text-align:left}th{background:#edf2f7}h2{margin-top:40px}</style>'+body)
print(json.dumps(validation['checks'],indent=2))
