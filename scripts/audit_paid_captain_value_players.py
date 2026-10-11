"""Read-only salary-band counts in verified Week 3/4 Thursday paid fields."""
from collections import Counter, defaultdict
import json
from pathlib import Path
from sqlalchemy import text
from backend.app.db import engine
from backend.app.product_services.entry_history import load_history, enrich_contests
from backend.app.product_services.contest_evidence import classify_contest_type
from scripts.analyze_showdown_qb_construction import salary_pools, build_resolver, parse_lineup, raw_to_salary
from scripts.audit_qb_captain_paid_rushing import paid_status


def run(c):
    c.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
    c.execute(text('SET TRANSACTION READ ONLY'))
    contests=[dict(r) for r in c.execute(text("SELECT * FROM target.dfs_contest WHERE season=2026 AND week IN (3,4) AND slate_id='THURSDAY_NIGHT' AND contest_format='showdown' ORDER BY week,contest_id")).mappings()]
    history,_,_=load_history(c);contests=enrich_contests(contests,history)
    salary=[dict(r) for r in c.execute(text("SELECT season,week,slate,team,opponent,position,player_name,source_player_key,player_master_id,roster_position,salary,game_info FROM curated_salary WHERE season=2026 AND week IN (3,4) AND slate='THURSDAY_NIGHT'")).mappings()]
    aliases=defaultdict(list)
    for a in c.execute(text("SELECT source_key,player_master_id,team,position FROM player_alias WHERE source_system='draftkings'")).mappings():
        aliases[str(a['source_key'])].append(dict(a))
    recovered=[dict(r) for r in c.execute(text("SELECT season,week,slate,source_player_key,raw_row_json,ingest_run_id FROM raw_salary_row WHERE season=2026 AND week=3 AND slate='THURSDAY_NIGHT'")).mappings()]
    salary.extend(raw_to_salary(r,aliases) for r in recovered)
    pools=salary_pools(salary);blocks=[]
    for ct in contests:
        cid=str(ct['contest_id']);field=int(ct['field_size'] or 0);paid=ct.get('places_paid')
        if classify_contest_type(ct.get('contest_name'),ct.get('contest_type'))['contest_type']!='gpp' or ct.get('paid_places_source')!='draftkings_entry_history' or type(paid) is not int: continue
        rows=[dict(r) for r in c.execute(text('SELECT rank,lineup_text,count(*) AS n FROM target.dfs_contest_entry_result WHERE contest_id=:id GROUP BY rank,lineup_text'),{'id':cid}).mappings()]
        assert sum(r['n'] for r in rows)==field and 0<=paid<=field
        ties=Counter()
        for r in rows: ties[r['rank']]+=r['n']
        keys=[k for k in pools if k[:3]==(2026,ct['week'],'thursday_night')]
        if len(keys)>1: keys=[k for k in keys if any(r['roster_position']=='CPT' for r in pools[k])]
        assert len(keys)==1,'Ambiguous salary matchup'
        key=keys[0];resolve=build_resolver(key,pools[key],[])
        out=dict(contest_id=cid,contest_name=ct['contest_name'],week=ct['week'],places_paid=paid,field_size=field,confirmed_paid=0,unresolved_paid=0,paid_buckets={'0':0,'1':0,'2+':0},boundary_entries=0,boundary_buckets={'0':0,'1':0,'2+':0},unresolved_boundary=0)
        for row in rows:
            status=paid_status(row['rank'],ties[row['rank']],paid)
            if status=='unpaid': continue
            if status=='unknown' and (row['rank'] is None or row['rank']<1): continue
            boundary=status=='unknown';n=row['n']
            out['boundary_entries' if boundary else 'confirmed_paid']+=n
            parts=parse_lineup(row['lineup_text']);roster=[resolve(slot,name) for slot,name in parts] if parts else []
            if len(roster)!=6 or not all(roster) or len({p['id'] for p in roster})!=6 or {p['team'] for p in roster}!=set(key[3]) or any(p['salary'] is None or p['salary']<0 for p in roster):
                out['unresolved_boundary' if boundary else 'unresolved_paid']+=n;continue
            count=sum(p['salary']<=1600 for p in roster)
            out['boundary_buckets' if boundary else 'paid_buckets'][str(min(count,2)) if count<2 else '2+']+=n
        assert sum(out['paid_buckets'].values())+out['unresolved_paid']==out['confirmed_paid']
        assert sum(out['boundary_buckets'].values())+out['unresolved_boundary']==out['boundary_entries']
        blocks.append(out)
    return dict(threshold=1600,salary_basis='native lineup-slot salary; Captain salary includes multiplier',unit='entries; identical lineups count separately',paid_basis='verified Places_Paid and whole tie group inside cutoff; cutoff ties separate',contests=blocks)

if __name__=='__main__':
    with engine.connect() as c: report=run(c)
    p=Path('artifacts/paid_captain_value_players');p.mkdir(exist_ok=True)
    (p/'report.json').write_text(json.dumps(report,indent=2,default=str)+'\n')
    print(json.dumps(report,indent=2,default=str))
