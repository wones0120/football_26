"""Read-only Sunday Main actual-scoring percentile research; no selection or model changes."""
from collections import Counter, defaultdict
import json
from pathlib import Path
from sqlalchemy import text
from backend.app.db import engine
from backend.app.product_services.entry_history import load_history, enrich_contests
from backend.app.product_services.contest_evidence import classify_contest_type
from scripts.analyze_classic_historical_study import SLOTS, build_players
from scripts.audit_qb_captain_paid_rushing import paid_status
from backend.app.product_services.optimizer_effectiveness import actual_points_by_player
import math

SLOT_COUNTS=Counter({'QB':1,'RB':2,'WR':3,'TE':1,'FLEX':1,'DST':1})


def run(c):
    c.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
    c.execute(text('SET TRANSACTION READ ONLY'))
    contests=[dict(r) for r in c.execute(text("SELECT * FROM target.dfs_contest WHERE season=2026 AND week BETWEEN 1 AND 4 AND contest_format='classic' ORDER BY week,slate_id,contest_id")).mappings()]
    history,_,_=load_history(c);contests=enrich_contests(contests,history)
    salaries=[dict(r) for r in c.execute(text("SELECT season,week,slate,team,opponent,position,player_name,source_player_key,player_master_id,roster_position,salary FROM curated_salary WHERE season=2026 AND week BETWEEN 1 AND 4 AND UPPER(slate)='SUNDAY_MAIN'")).mappings()]
    observations=[dict(r) for r in c.execute(text("SELECT ct.week,o.player_id,o.roster_position,o.actual_points,o.resolution_status FROM target.contest_ownership_observation o JOIN target.dfs_contest ct ON ct.contest_id=o.contest_id WHERE ct.season=2026 AND ct.week BETWEEN 1 AND 4 AND ct.contest_format='classic' AND ct.slate_id='SUNDAY_MAIN'")).mappings()]
    score_ranks={}; universes=[]
    for week in sorted({r['week'] for r in salaries}):
        ss=[r for r in salaries if r['week']==week]
        resolve,_=build_players(ss,[],{})
        players={p['id']:p for r in ss if (p:=resolve(r['position'],r['player_name']))}
        actual=actual_points_by_player([r for r in observations if r['week']==week],'classic')
        for pos in ['QB','RB','WR','TE','DST']:
            eligible={pid:p for pid,p in players.items() if p['position']==pos}
            known={pid:actual[pid] for pid in eligible if pid in actual}
            for basis in ['all_observed','nonzero_observed']:
                pool={pid:score for pid,score in known.items() if basis=='all_observed' or score!=0}
                cutoffs={str(pct):sorted(pool.values(),reverse=True)[math.ceil(len(pool)*pct/100)-1] for pct in [25,50,75]} if pool else {}
                universes.append(dict(week=week,position=pos,basis=basis,salary_players=len(eligible),known_scores=len(known),ranked_players=len(pool),missing_scores=len(eligible)-len(known),cutoffs=cutoffs))
                for pid,score in known.items():
                    score_ranks[(week,basis,pid)]={pct:score>=threshold and pid in pool for pct,threshold in cutoffs.items()}
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
        appearances=defaultdict(Counter)
        for row in rows:
            status=paid_status(row['rank'],ties[row['rank']],paid);n=row['n'];out['coverage']['raw_'+status]+=n
            parts=SLOTS.findall(row['lineup_text'] or '')
            players=[resolve(s,name) for s,name in parts] if Counter(s for s,_ in parts)==SLOT_COUNTS else []
            if len(players)!=9 or not all(players) or len({p['id'] for p in players})!=9 or any(p['salary'] is None for p in players) or sum(float(p['salary']) for p in players)>50000:
                out['coverage']['unresolved_'+status]+=n;continue
            out['coverage']['resolved_'+status]+=n
            if status=='paid':
                for player in players:
                    for basis in ['all_observed','nonzero_observed']:
                        counts=appearances[(basis,player['position'])]
                        counts['appearances']+=n
                        ranks=score_ranks.get((ct['week'],basis,player['id']))
                        if ranks is None:
                            counts['missing_actual']+=n
                        else:
                            counts['known_actual']+=n
                            for pct,qualifies in ranks.items():
                                if qualifies:counts['top_'+pct]+=n
        out['scoring_bands']=[dict(basis=basis,position=pos,**counts) for (basis,pos),counts in sorted(appearances.items())]
        results.append(out)
    return dict(season=2026,scope='verified Sunday Main GPP paid entries',ranking='Actual DK points among salary-listed players with resolved nonconflicting actual scores; cumulative ceil(N*percentile) cutoffs include score ties. Nonzero sensitivity excludes exact-zero players from ranking only. Duplicate entries count separately.',universes=universes,contests=results,excluded=excluded)

if __name__=='__main__':
    with engine.connect() as c:r=run(c)
    p=Path('artifacts/classic_paid_scoring_percentiles');p.mkdir(exist_ok=True)
    (p/'report.json').write_text(json.dumps(r,indent=2,default=str)+'\n')
    for ct in r['contests']:print(ct['week'],ct['contest_id'],dict(ct['coverage']))
