"""Read-only Sunday Main salary-floor research; no selection or model changes."""
from collections import Counter, defaultdict
import json
from pathlib import Path
from sqlalchemy import text
from backend.app.db import engine
from backend.app.product_services.entry_history import load_history, enrich_contests
from backend.app.product_services.contest_evidence import classify_contest_type
from scripts.analyze_classic_historical_study import SLOTS, build_players, team
from scripts.audit_qb_captain_paid_rushing import paid_status

FLOORS=(3000,3500,4000,4500,5000)
SLOT_COUNTS=Counter({'QB':1,'RB':2,'WR':3,'TE':1,'FLEX':1,'DST':1})


def run(c, *, floors_by_group=None):
    floors_by_group = {g:FLOORS for g in ["all","offense","QB","RB","WR","TE","DST"]} if floors_by_group is None else floors_by_group
    c.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
    c.execute(text('SET TRANSACTION READ ONLY'))
    contests=[dict(r) for r in c.execute(text("SELECT * FROM target.dfs_contest WHERE season=2026 AND week BETWEEN 1 AND 4 AND contest_format='classic' ORDER BY week,slate_id,contest_id")).mappings()]
    history,_,_=load_history(c);contests=enrich_contests(contests,history)
    salaries=[dict(r) for r in c.execute(text("SELECT season,week,slate,team,opponent,position,player_name,source_player_key,player_master_id,roster_position,salary FROM curated_salary WHERE season=2026 AND week BETWEEN 1 AND 4 AND UPPER(slate)='SUNDAY_MAIN'")).mappings()]
    home_evidence=defaultdict(set)
    for row in c.execute(text("SELECT week,raw_row_json FROM raw_nfl_schedule WHERE season=2026 AND week BETWEEN 1 AND 4")).mappings():
        raw=row['raw_row_json'];home=team(raw.get('home_team'));away=team(raw.get('away_team'))
        if home and away:home_evidence[(row['week'],tuple(sorted((home,away))))].add(home)
    results=[];excluded=[]
    for ct in contests:
        paid=ct.get('places_paid');cid=str(ct['contest_id']);field=int(ct['field_size'] or 0)
        if ct['slate_id']!='SUNDAY_MAIN' or ct.get('paid_places_source')!='draftkings_entry_history' or type(paid) is not int or classify_contest_type(ct.get('contest_name'),ct.get('contest_type'))['contest_type']!='gpp':
            excluded.append(dict(contest_id=cid,week=ct['week'],slate=ct['slate_id'],reason='not_verified_Main_GPP_paid_evidence'));continue
        rows=[dict(r) for r in c.execute(text('SELECT rank,lineup_text,count(*) AS n FROM target.dfs_contest_entry_result WHERE contest_id=:id GROUP BY rank,lineup_text'),{'id':cid}).mappings()]
        assert sum(r['n'] for r in rows)==field and 0<=paid<=field
        resolve,_=build_players([r for r in salaries if r['week']==ct['week']],[],{})
        ties=Counter()
        for row in rows: ties[row['rank']]+=row['n']
        out=dict(contest_id=cid,name=ct['contest_name'],week=ct['week'],field=field,places_paid=paid,coverage=Counter(),rows=[])
        buckets=defaultdict(Counter); minimums=defaultdict(Counter); home_away=defaultdict(Counter); lineup_sides=defaultdict(Counter)
        for row in rows:
            status=paid_status(row['rank'],ties[row['rank']],paid);n=row['n'];out['coverage']['raw_'+status]+=n
            parts=SLOTS.findall(row['lineup_text'] or '')
            players=[resolve(s,name) for s,name in parts] if Counter(s for s,_ in parts)==SLOT_COUNTS else []
            if len(players)!=9 or not all(players) or len({p['id'] for p in players})!=9 or any(p['salary'] is None for p in players) or sum(float(p['salary']) for p in players)>50000:
                out['coverage']['unresolved_'+status]+=n;continue
            out['coverage']['resolved_'+status]+=n
            if status=='paid':
                present=defaultdict(set)
                for player in players:
                    homes=home_evidence.get((ct['week'],tuple(sorted((player['team'],player['opponent'])))),set())
                    side=('home' if player['team']==next(iter(homes)) else 'away') if len(homes)==1 else 'unknown'
                    home_away[player['position']][side]+=n
                    present[player['position']].add(side)
                for pos,sides in present.items():
                    for side in sides:lineup_sides[pos][side]+=n
            for group in floors_by_group:
                ps=players if group=='all' else [p for p in players if p['position']!='DST'] if group=='offense' else [p for p in players if p['position']==group]
                minimums[(group,min(float(p['salary']) for p in ps))][status]+=n
                for floor in floors_by_group[group]:
                    count=sum(float(p['salary'])<floor for p in ps)
                    buckets[(group,floor,min(count,2))][status]+=n
        out['paid_home_away_appearances']=dict(home_away)
        out['paid_lineups_with_side']=dict(lineup_sides)
        out['minimum_salaries']=[dict(group=g,salary=sal,**v) for (g,sal),v in sorted(minimums.items())]
        out['rows']=[dict(group=g,floor=f,below=b,**v) for (g,f,b),v in sorted(buckets.items())]
        results.append(out)
    return dict(season=2026,weeks=[1,2,3,4],scope='verified Sunday Main GPPs',floors_by_group=floors_by_group,floors=FLOORS,semantics='Below floor is strictly less; floor itself qualifies. All includes DST; offense excludes DST. Entry-weighted, duplicated rosters retained. Cutoff-straddling ties unknown.',contests=results,excluded=excluded)

if __name__=='__main__':
    with engine.connect() as c:r=run(c)
    p=Path('artifacts/classic_salary_floor');p.mkdir(exist_ok=True)
    (p/'report.json').write_text(json.dumps(r,indent=2,default=str)+'\n')
    for ct in r['contests']:print(ct['week'],ct['contest_id'],dict(ct['coverage']))
