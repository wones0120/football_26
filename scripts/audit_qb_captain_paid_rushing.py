"""Read-only QB Captain top-decile/paid-finish and actual rushing-TD audit."""
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
from sqlalchemy import text
from backend.app.db import engine
from backend.app.product_services.entry_history import load_history, enrich_contests
from backend.app.product_services.contest_evidence import classify_contest_type
from scripts.analyze_showdown_qb_construction import salary_pools, build_resolver, parse_lineup, team, raw_to_salary


def paid_status(rank, tie_count, paid):
    if paid is None or rank is None or rank < 1:
        return 'unknown'
    if rank + tie_count - 1 <= paid:
        return 'paid'
    if rank > paid:
        return 'unpaid'
    return 'unknown'


def position_summary(contests):
    totals=defaultdict(Counter)
    for contest in contests:
        if not contest['paid_ready'] or contest.get('exclusion'):
            continue
        for position, counts in contest['position_counts'].items():
            totals[position].update(counts)
            if position!='QB': totals['NON_QB'].update(counts)
    result={}
    for position, counts in sorted(totals.items()):
        n=counts['entries'];known=counts['paid']+counts['unpaid']
        result[position]=dict(counts,known_paid_rate=counts['paid']/known if known else None,
            paid_rate_lower=counts['paid']/n if n else None,
            paid_rate_upper=(counts['paid']+counts['unknown'])/n if n else None)
    return result


def run(c):
    c.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
    c.execute(text('SET TRANSACTION READ ONLY'))
    contests=[dict(r) for r in c.execute(text("SELECT contest_id,season,week,slate_id,contest_format,contest_name,contest_type,field_size,entry_fee,prize_pool FROM target.dfs_contest WHERE season=2026 AND week BETWEEN 1 AND 4 AND contest_format='showdown' ORDER BY week,slate_id,contest_id")).mappings()]
    history,_,_=load_history(c);contests=enrich_contests(contests,history)
    salary=[dict(r) for r in c.execute(text('SELECT season,week,slate,team,opponent,position,player_name,source_player_key,player_master_id,roster_position,salary,game_info FROM curated_salary WHERE season=2026 AND week BETWEEN 1 AND 4')).mappings()]
    aliases=defaultdict(list)
    for a in c.execute(text("SELECT source_key,player_master_id,team,position FROM player_alias WHERE source_system='draftkings'")).mappings():
        aliases[str(a['source_key'])].append(dict(a))
    recovered=[dict(r) for r in c.execute(text("SELECT season,week,slate,source_player_key,raw_row_json,ingest_run_id FROM raw_salary_row WHERE season=2026 AND week=3 AND slate='THURSDAY_NIGHT'")).mappings()]
    salary.extend(raw_to_salary(r,aliases) for r in recovered)
    pools=salary_pools(salary)
    stats={}
    stat_rows=c.execute(text("""SELECT DISTINCT r.raw_nfl_weekly_stat_id,r.week,r.team,r.opponent,r.player_id AS source_id,
        r.raw_row_json->>'rushing_tds' AS rushing_tds,a.player_master_id
        FROM raw_nfl_weekly_stat r JOIN player_alias a ON a.source_system=r.source_system AND a.source_key=r.player_id
        WHERE r.season=2026 AND r.week BETWEEN 1 AND 4 AND r.position='QB'
        ORDER BY r.raw_nfl_weekly_stat_id DESC""")).mappings().all()
    source_ids=defaultdict(set)
    for r in stat_rows: source_ids[r['source_id']].add(r['player_master_id'])
    for r in stat_rows:
        if len(source_ids[r['source_id']])!=1: continue
        key=(r['week'],r['player_master_id'],team(r['team']),team(r['opponent']))
        if key not in stats:
            v=r['rushing_tds']
            stats[key]=dict(rushing_tds=int(v) if v is not None and str(v).isdigit() else None,source_id=r['source_id'],stat_row_id=r['raw_nfl_weekly_stat_id'])
    blocks=[];players=defaultdict(lambda:dict(top10_entries=0,paid_entries=0,unpaid_entries=0,unknown_paid_entries=0,top10_boundary_entries=0,contests=set()))
    for ct in contests:
        cid=str(ct['contest_id']);field=int(ct['field_size'] or 0)
        rows=[dict(r) for r in c.execute(text('SELECT rank,lineup_text,count(*) AS n FROM target.dfs_contest_entry_result WHERE contest_id=:id GROUP BY rank,lineup_text'),{'id':cid}).mappings()]
        ties=Counter()
        for r in rows: ties[r['rank']]+=r['n']
        keys=[k for k in pools if k[:3]==(2026,ct['week'],ct['slate_id'].lower())]
        if len(keys)>1:
            keys=[k for k in keys if any(r['roster_position']=='CPT' for r in pools[k])]
        complete=bool(field and sum(r['n'] for r in rows)==field)
        classification=classify_contest_type(ct.get('contest_name'),ct.get('contest_type'))['contest_type']
        paid=ct.get('places_paid')
        paid_ready=bool(complete and classification=='gpp' and ct.get('paid_places_source')=='draftkings_entry_history' and type(paid) is int and 0<=paid<=field)
        audit=dict(contest_id=cid,week=ct['week'],slate=ct['slate_id'],contest_name=ct['contest_name'],field_size=field,places_paid=paid if paid_ready else None,
            paid_ready=paid_ready,field_complete=complete,position_counts={},unresolved_field_entries=0,unresolved_entries=0,qb_top10=0,qb_paid=0,qb_unknown_paid=0,qb_unpaid=0,qb_boundary=0)
        if not complete or len(keys)!=1:
            audit['exclusion']='incomplete_field_or_ambiguous_salary_matchup';blocks.append(audit);continue
        key=keys[0];resolve=build_resolver(key,pools[key],[]);threshold=math.ceil(field*.1)
        for row in rows:
            rank=row['rank']
            if rank is None or rank<1:
                audit['unresolved_field_entries']+=row['n'];continue
            parts=parse_lineup(row['lineup_text'])
            roster=[resolve(slot,name) for slot,name in parts] if parts else []
            if len(roster)!=6 or not all(roster) or len({r['id'] for r in roster})!=6 or {r['team'] for r in roster}!=set(key[3]):
                audit['unresolved_field_entries']+=row['n']
                if rank<=threshold: audit['unresolved_entries']+=row['n']
                continue
            qb=roster[0]
            counts=audit['position_counts'].setdefault(qb['position'],dict(entries=0,paid=0,unpaid=0,unknown=0))
            counts['entries']+=row['n']
            counts[paid_status(rank,ties[rank],paid if paid_ready else None)]+=row['n']
            if rank>threshold: continue
            if qb['position']!='QB':continue
            pk=(ct['week'],ct['slate_id'],qb['id']);out=players[pk]
            opponent=next(t for t in key[3] if t!=qb['team'])
            stat=stats.get((ct['week'],qb['id'],qb['team'],opponent),{})
            out.update(week=ct['week'],slate=ct['slate_id'],player_id=qb['id'],name=qb['name'],team=qb['team'],opponent=opponent,**stat)
            out['contests'].add(cid)
            worst=rank+ties[rank]-1
            if worst>threshold:
                out['top10_boundary_entries']+=row['n'];audit['qb_boundary']+=row['n'];continue
            out['top10_entries']+=row['n'];audit['qb_top10']+=row['n']
            status=True if paid_ready and worst<=paid else False if paid_ready and rank>paid else None
            if status is True:out['paid_entries']+=row['n'];audit['qb_paid']+=row['n']
            elif status is False:out['unpaid_entries']+=row['n'];audit['qb_unpaid']+=row['n']
            else:out['unknown_paid_entries']+=row['n'];audit['qb_unknown_paid']+=row['n']
        blocks.append(audit)
    players=[dict(v,contests=sorted(v['contests'])) for _,v in sorted(players.items())]
    return dict(scope='2026 Weeks 1–4 imported Captain contests',top10='entire tied rank group within ceil(field_size * .10); straddling groups reported separately',
        paid='verified GPP classification + complete standings + account-history Places_Paid; entire tied group within paid ranks',
        stats='latest imported native-ID-matched QB weekly record; season/week/team/opponent scoped; missing is unknown',
        contests=blocks,players=players,position_summary=position_summary(blocks))

if __name__=='__main__':
    with engine.connect() as c:r=run(c)
    p=Path('artifacts/qb_captain_paid_rushing');p.mkdir(exist_ok=True)
    (p/'report.json').write_text(json.dumps(r,indent=2,default=str)+'\n')
    print(json.dumps(r['players'],indent=2))
    print('contest coverage',len(r['contests']),sum(c['paid_ready'] for c in r['contests']),'unresolved',sum(c['unresolved_entries'] for c in r['contests']))
