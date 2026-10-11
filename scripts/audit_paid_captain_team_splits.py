"""Read-only team composition of verified paid Showdown entries."""
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
    contests = [dict(r) for r in c.execute(text("SELECT * FROM target.dfs_contest WHERE season=2026 AND week BETWEEN 1 AND 4 AND contest_format='showdown' ORDER BY week,slate_id,contest_id")).mappings()]
    history, _, _ = load_history(c)
    contests = enrich_contests(contests, history)
    salary = [dict(r) for r in c.execute(text('SELECT season,week,slate,team,opponent,position,player_name,source_player_key,player_master_id,roster_position,salary,game_info FROM curated_salary WHERE season=2026 AND week BETWEEN 1 AND 4')).mappings()]
    aliases = defaultdict(list)
    for a in c.execute(text("SELECT source_key,player_master_id,team,position FROM player_alias WHERE source_system='draftkings'")).mappings():
        aliases[str(a['source_key'])].append(dict(a))
    recovered = c.execute(text("SELECT season,week,slate,source_player_key,raw_row_json,ingest_run_id FROM raw_salary_row WHERE season=2026 AND week=3 AND slate='THURSDAY_NIGHT'")).mappings()
    salary.extend(raw_to_salary(dict(r), aliases) for r in recovered)
    pools = salary_pools(salary)
    results, excluded = [], []
    for ct in contests:
        cid = str(ct['contest_id'])
        paid, field = ct.get('places_paid'), int(ct['field_size'] or 0)
        if ct.get('paid_places_source') != 'draftkings_entry_history' or type(paid) is not int or classify_contest_type(ct.get('contest_name'), ct.get('contest_type'))['contest_type'] != 'gpp':
            excluded.append(dict(contest_id=cid, reason='unverified_paid_places_or_not_gpp'))
            continue
        keys = [k for k in pools if k[:3] == (2026, ct['week'], ct['slate_id'].lower())]
        if len(keys) > 1:
            keys = [k for k in keys if any(r['roster_position'] == 'CPT' for r in pools[k])]
        if len(keys) != 1:
            excluded.append(dict(contest_id=cid, reason='ambiguous_salary_matchup'))
            continue
        rows = [dict(r) for r in c.execute(text('SELECT rank,lineup_text,count(*) AS n FROM target.dfs_contest_entry_result WHERE contest_id=:id GROUP BY rank,lineup_text'), {'id': cid}).mappings()]
        if sum(r['n'] for r in rows) != field:
            excluded.append(dict(contest_id=cid, reason='incomplete_field'))
            continue
        assert 0 <= paid <= field
        key = keys[0]
        resolve = build_resolver(key, pools[key], [])
        ties = Counter()
        for r in rows:
            ties[r['rank']] += r['n']
        block = dict(contest_id=cid, week=ct['week'], slate=ct['slate_id'], teams=key[3], paid_entries=0, unresolved_paid=0, unknown_entries=0, splits={'5-1': 0, '4-2': 0, '3-3': 0})
        for r in rows:
            status = paid_status(r['rank'], ties[r['rank']], paid)
            if status == 'unknown':
                block['unknown_entries'] += r['n']
            if status != 'paid':
                continue
            block['paid_entries'] += r['n']
            parts = parse_lineup(r['lineup_text'])
            roster = [resolve(slot, name) for slot, name in parts] if parts else []
            if len(roster) != 6 or not all(roster) or len({p['id'] for p in roster}) != 6 or {p['team'] for p in roster} != set(key[3]):
                block['unresolved_paid'] += r['n']
                continue
            counts = sorted(Counter(p['team'] for p in roster).values(), reverse=True)
            split = '-'.join(map(str, counts))
            assert split in block['splits']
            block['splits'][split] += r['n']
        assert sum(block['splits'].values()) + block['unresolved_paid'] == block['paid_entries']
        results.append(block)
    return dict(basis='Verified paid places, whole tie group inside cutoff; duplicate entries retained. Captain counts as one player; larger team count first, regardless of Captain team.', contests=results, excluded=excluded)


if __name__ == '__main__':
    with engine.connect() as c:
        report = run(c)
    path = Path('artifacts/paid_captain_team_splits')
    path.mkdir(exist_ok=True)
    (path / 'report.json').write_text(json.dumps(report, indent=2, default=str) + '\n')
    print(json.dumps(report, indent=2, default=str))
