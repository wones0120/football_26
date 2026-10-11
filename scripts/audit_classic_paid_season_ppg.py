"""Read-only prior-week season-average research; no selection or model changes."""
from collections import Counter, defaultdict
import json
from pathlib import Path
from sqlalchemy import text
from backend.app.db import engine
from backend.app.product_services.entry_history import load_history, enrich_contests
from backend.app.product_services.contest_evidence import classify_contest_type
from scripts.analyze_classic_historical_study import SLOTS, build_players, team
from scripts.audit_qb_captain_paid_rushing import paid_status
from backend.app.product_services.optimizer_effectiveness import actual_points_by_player
import math
from backend.app.services.simulation import calculate_dk_points

SLOT_COUNTS=Counter({'QB':1,'RB':2,'WR':3,'TE':1,'FLEX':1,'DST':1})


def run(c):
    c.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
    c.execute(text('SET TRANSACTION READ ONLY'))
    contests=[dict(r) for r in c.execute(text("SELECT * FROM target.dfs_contest WHERE season=2026 AND week BETWEEN 1 AND 4 AND contest_format='classic' ORDER BY week,slate_id,contest_id")).mappings()]
    history,_,_=load_history(c);contests=enrich_contests(contests,history)
    salaries=[dict(r) for r in c.execute(text("SELECT season,week,slate,team,opponent,position,player_name,source_player_key,player_master_id,roster_position,salary FROM curated_salary WHERE season=2026 AND week BETWEEN 1 AND 4 AND UPPER(slate)='SUNDAY_MAIN'")).mappings()]
    aliases=defaultdict(set)
    for a in c.execute(text("SELECT source_system,source_key,player_master_id FROM player_alias WHERE source_system IN ('nflreadpy','pfr')")).mappings():
        aliases[(a['source_system'],a['source_key'])].add(a['player_master_id'])
    games=defaultdict(set); positions=defaultdict(set); names={}; participation=set(); gaps=Counter()
    for r in c.execute(text("SELECT * FROM raw_nfl_weekly_stat WHERE season=2026 AND week BETWEEN 1 AND 3")).mappings():
        if r['position'] not in {'QB','RB','WR','TE'}:continue
        ids=aliases.get((r['source_system'],r['player_id']),set())
        if len(ids)!=1:gaps['unresolved_stat_rows']+=1;continue
        pid=next(iter(ids));raw=r['raw_row_json'];key=(pid,r['week'])
        # Preserve negative points; source uses aggregated special-team TDs.
        stats=dict(raw)
        if 'kickoff_return_tds' not in stats and 'punt_return_tds' not in stats:
            stats['kickoff_return_tds']=stats.get('special_teams_tds',0)
        points=round(calculate_dk_points(stats,floor_at_zero=False)+6*float(stats.get('fumble_recovery_tds') or 0),2)
        games[key].add(points);positions[pid].add(r['position']);names[pid]=raw.get('player_display_name') or r['player_name']
        if points!=0 or any(float(raw.get(k) or 0)>0 for k in ['attempts','carries','targets','sacks_suffered','kickoff_returns','punt_returns']):participation.add(key)
    for r in c.execute(text("SELECT * FROM raw_nfl_snap_count WHERE season=2026 AND week BETWEEN 1 AND 3 AND position IN ('QB','RB','WR','TE') AND offense_snaps>0")).mappings():
        ids=aliases.get(('pfr',r['pfr_player_id']),set())
        if len(ids)!=1:gaps['unresolved_snap_rows']+=1;continue
        pid=next(iter(ids));key=(pid,r['week']);participation.add(key);positions[pid].add(r['position']);names.setdefault(pid,r['player_name'])
        if not games[key]:games[key].add(0.0)
    # DST observed scores use canonical IDs; require complete prior-week coverage.
    dst_ids={r['player_master_id']:team(r['team']) for r in c.execute(text("SELECT DISTINCT player_master_id,team FROM curated_salary WHERE season=2026 AND week BETWEEN 1 AND 4 AND position='DST' AND player_master_id IS NOT NULL")).mappings()}
    observations=[dict(r) for r in c.execute(text("SELECT ct.week,ct.contest_format,o.player_id,o.roster_position,o.actual_points,o.resolution_status FROM target.contest_ownership_observation o JOIN target.dfs_contest ct ON ct.contest_id=o.contest_id WHERE ct.season=2026 AND ct.week BETWEEN 1 AND 3")).mappings()]
    dst_values=defaultdict(set)
    for o in observations:
        if o['player_id'] in dst_ids:
            for pid,score in actual_points_by_player([o],o['contest_format']).items():dst_values[(pid,o['week'])].add(score)
    for key,values in dst_values.items():
        games[key]=values;participation.add(key);positions[key[0]].add('DST');names[key[0]]=dst_ids[key[0]]
    score_ranks={};universes=[];rankings=[]
    for week in [3,4]:
        for pos in ['QB','RB','WR','TE','DST']:
            averages={};counts={}
            for pid,ps in positions.items():
                if ps!={pos}:continue
                prior=[key for key in participation if key[0]==pid and key[1]<week]
                if pos=='DST' and len(prior)!=week-1:continue
                if not prior or any(len(games[key])!=1 for key in prior):continue
                scores=[next(iter(games[key])) for key in prior]
                averages[pid]=sum(scores)/len(scores);counts[pid]=len(scores)
            cutoffs={str(pct):sorted(averages.values(),reverse=True)[math.ceil(len(averages)*pct/100)-1] for pct in [25,50,75]} if averages else {}
            universes.append(dict(week=week,position=pos,ranked_players=len(averages),cutoffs=cutoffs))
            # Incomplete DST league history cannot establish league-wide percentiles.
            if pos=='DST' and len(averages)!=32:
                gaps['week_'+str(week)+'_incomplete_dst_history']=32-len(averages);continue
            for pid,average in averages.items():
                score_ranks[(week,'prior_season_ppg',pid)]={pct:average>=threshold for pct,threshold in cutoffs.items()}
                rankings.append(dict(week=week,player_id=pid,name=names.get(pid),position=pos,prior_games=counts[pid],ppg=average))
    results=[];excluded=[]
    for ct in contests:
        paid=ct.get('places_paid');cid=str(ct['contest_id']);field=int(ct['field_size'] or 0)
        if ct['week']==1 or ct['slate_id']!='SUNDAY_MAIN' or ct.get('paid_places_source')!='draftkings_entry_history' or type(paid) is not int or classify_contest_type(ct.get('contest_name'),ct.get('contest_type'))['contest_type']!='gpp':
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
                    for basis in ['prior_season_ppg']:
                        counts=appearances[(basis,player['position'])]
                        counts['appearances']+=n
                        ranks=score_ranks.get((ct['week'],basis,player['id']))
                        if ranks is None:
                            counts['unranked_history']+=n
                        else:
                            counts['ranked_history']+=n
                            for pct,qualifies in ranks.items():
                                if qualifies:counts['top_'+pct]+=n
        out['scoring_bands']=[dict(basis=basis,position=pos,**counts) for (basis,pos),counts in sorted(appearances.items())]
        results.append(out)
    return dict(season=2026,scope='verified Sunday Main paid GPP entries, Weeks 3–4',ranking='League-wide season DK points per participating game through the prior week, at least one game; offense participation from snaps or recorded offensive/return activity. Includes negative and zero-point participating games. Ties included at ceil(N*fraction) cutoff. Week 1 has no prior history. Retrospective source corrections possible; not a frozen pregame snapshot.',universes=universes,rankings=rankings,gaps=dict(gaps),contests=results,excluded=excluded)

if __name__=='__main__':
    with engine.connect() as c:r=run(c)
    p=Path('artifacts/classic_paid_season_ppg');p.mkdir(exist_ok=True)
    (p/'report.json').write_text(json.dumps(r,indent=2,default=str)+'\n')
    for ct in r['contests']:print(ct['week'],ct['contest_id'],dict(ct['coverage']))
