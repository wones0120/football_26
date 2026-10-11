"""Read-only prior-week season-average team leaders in verified paid entries."""
from collections import Counter, defaultdict
import json
from pathlib import Path
from sqlalchemy import text
from backend.app.db import engine
from backend.app.product_services.entry_history import load_history,enrich_contests
from backend.app.product_services.contest_evidence import classify_contest_type
from backend.app.product_services.optimizer_effectiveness import actual_points_by_player
from scripts.analyze_showdown_qb_construction import salary_pools,build_resolver,parse_lineup,raw_to_salary
from scripts.audit_qb_captain_paid_rushing import paid_status
from backend.app.product_services.classic_season_rank_preferences import build_rankings
from backend.app.services.simulation import calculate_dk_points


def run(c, *, exclude_qbs=True, compare_field=False):
    c.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
    c.execute(text('SET TRANSACTION READ ONLY'))
    contests=[dict(r) for r in c.execute(text("SELECT * FROM target.dfs_contest WHERE season=2026 AND week BETWEEN 1 AND 4 AND contest_format='showdown' ORDER BY week,slate_id,contest_id")).mappings()]
    history,_,_=load_history(c);contests=enrich_contests(contests,history)
    salary=[dict(r) for r in c.execute(text('SELECT season,week,slate,team,opponent,position,player_name,source_player_key,player_master_id,roster_position,salary,game_info FROM curated_salary WHERE season=2026 AND week BETWEEN 1 AND 4')).mappings()]
    aliases=defaultdict(list)
    for a in c.execute(text("SELECT source_key,player_master_id,team,position FROM player_alias WHERE source_system='draftkings'")).mappings(): aliases[str(a['source_key'])].append(dict(a))
    recovered=[dict(r) for r in c.execute(text("SELECT season,week,slate,source_player_key,raw_row_json,ingest_run_id FROM raw_salary_row WHERE season=2026 AND week=3 AND slate='THURSDAY_NIGHT'")).mappings()]
    salary.extend(raw_to_salary(r,aliases) for r in recovered)
    pools=salary_pools(salary);groups=defaultdict(list)
    for ct in contests:groups[(ct['week'],ct['slate_id'])].append(ct)
    stats=[dict(r) for r in c.execute(text("SELECT * FROM raw_nfl_weekly_stat WHERE season=2026 AND week BETWEEN 1 AND 3")).mappings()]
    snaps=[dict(r) for r in c.execute(text("SELECT * FROM raw_nfl_snap_count WHERE season=2026 AND week BETWEEN 1 AND 3")).mappings()]
    source_aliases=[dict(r) for r in c.execute(text("SELECT source_system,source_key,player_master_id FROM player_alias WHERE source_system IN ('nflreadpy','pfr')")).mappings()]
    aliases_by_key=defaultdict(set)
    for a in source_aliases:aliases_by_key[(a['source_system'],a['source_key'])].add(str(a['player_master_id']))
    averages={};history_warnings={}
    for w in [2,3,4]:
        rank_rows,warnings=build_rankings(stats,snaps,source_aliases,season=2026,week=w)
        ranked={r['player_id']:r for r in rank_rows}
        kicker_scores=defaultdict(set)
        for r in stats:
            if r['week']>=w or r['position']!='K':continue
            ids=aliases_by_key[(r['source_system'],r['player_id'])]
            if len(ids)!=1:continue
            raw=r['raw_row_json'];num=lambda k:float(raw.get(k) or 0)
            # DK kicking points: no missed-FG penalty; retain other football scoring.
            score=calculate_dk_points(raw,floor_at_zero=False)+3*sum(num(k) for k in ['fg_made_0_19','fg_made_20_29','fg_made_30_39'])+4*num('fg_made_40_49')+5*(num('fg_made_50_59')+num('fg_made_60_'))+num('pat_made')
            kicker_scores[(next(iter(ids)),r['week'])].add(round(score,2))
        for pid in {k[0] for k in kicker_scores}:
            games=[dict(week=ww,points=next(iter(v))) for (pp,ww),v in kicker_scores.items() if pp==pid and len(v)==1]
            if any(len(v)!=1 for (pp,ww),v in kicker_scores.items() if pp==pid):continue
            if games:ranked[pid]=dict(player_id=pid,position='K',games=games,games_played=len(games),ppg=sum(g['points'] for g in games)/len(games))
        averages[w]=ranked;history_warnings[w]=warnings
    results=[]
    for (week,slate),cts in sorted(groups.items()):
        if week==1:
            results.append(dict(week=week,slate=slate,error='no_prior_season_history'));continue
        keys=[k for k in pools if k[:3]==(2026,week,slate.lower())]
        if len(keys)>1:keys=[k for k in keys if any(r['roster_position']=='CPT' for r in pools[k])]
        if len(keys)!=1:
            results.append(dict(week=week,slate=slate,error='ambiguous_salary_matchup'));continue
        key=keys[0];resolve=build_resolver(key,pools[key],[]);players={}
        for r in pools[key]:
            p=resolve('FLEX',r['player_name'])
            if p:players[p['id']]=p
        history=averages[week]
        actuals={pid:r['ppg'] for pid,r in history.items()};leaders=[]
        for team in key[3]:
            candidates=[p for pid,p in players.items() if p['team']==team and pid in actuals and p['position'] not in ({'DST','QB'} if exclude_qbs else {'DST'})]
            missing=[dict(id=pid,name=p['name'],position=p['position']) for pid,p in players.items() if p['team']==team and pid not in actuals and p['position'] not in ({'DST','QB'} if exclude_qbs else {'DST'})]
            if not candidates:continue
            best=max(actuals[p['id']] for p in candidates)
            for p in candidates:
                if actuals[p['id']]==best:leaders.append(dict(player_id=p['id'],name=p['name'],position=p['position'],team=team,season_ppg=best,prior_games=history[p['id']]['games_played'],prior_game_scores=history[p['id']]['games'],tied_leader=sum(actuals[q['id']]==best for q in candidates)>1,missing_prior_history_players=missing,any_slot=0,captain=0,flex=0,unpaid_with_player=0))
        block=dict(week=week,slate=slate,teams=key[3],leaders=leaders,verified_contests=[],paid_entries=0,resolved_paid_entries=0,unresolved_paid_entries=0,boundary_entries=0,both_team_leaders=0,at_least_one_team_leader=0)
        for ct in cts:
            paid=ct.get('places_paid');field=int(ct['field_size'] or 0)
            if ct.get('paid_places_source')!='draftkings_entry_history' or type(paid) is not int or classify_contest_type(ct.get('contest_name'),ct.get('contest_type'))['contest_type']!='gpp':continue
            rows=[dict(r) for r in c.execute(text('SELECT rank,lineup_text,count(*) AS n FROM target.dfs_contest_entry_result WHERE contest_id=:id GROUP BY rank,lineup_text'),{'id':str(ct['contest_id'])}).mappings()]
            if sum(r['n'] for r in rows)!=field:continue
            assert 0<=paid<=field
            block['verified_contests'].append(str(ct['contest_id']));ties=Counter()
            for r in rows:ties[r['rank']]+=r['n']
            for r in rows:
                status=paid_status(r['rank'],ties[r['rank']],paid)
                if status=='unknown':block['boundary_entries']+=r['n'];continue
                if status!='paid' and not compare_field:continue
                if status=='paid': block['paid_entries']+=r['n']
                parts=parse_lineup(r['lineup_text']);roster=[resolve(slot,name) for slot,name in parts] if parts else []
                if len(roster)!=6 or not all(roster) or len({p['id'] for p in roster})!=6 or {p['team'] for p in roster}!=set(key[3]):
                    if status=='paid': block['unresolved_paid_entries']+=r['n']
                    continue
                ids={p['id'] for p in roster}
                if status=='unpaid':
                    for leader in leaders:
                        if leader['player_id'] in ids: leader['unpaid_with_player']+=r['n']
                    continue
                block['resolved_paid_entries']+=r['n']
                # If a team has tied leaders, any tied leader represents that team.
                leader_ids_by_team={team:{p['player_id'] for p in leaders if p['team']==team} for team in key[3]}
                if any(ids & team_ids for team_ids in leader_ids_by_team.values()):
                    block['at_least_one_team_leader']+=r['n']
                if all(ids & team_ids for team_ids in leader_ids_by_team.values()):
                    block['both_team_leaders']+=r['n']
                for leader in leaders:
                    if leader['player_id'] in ids:
                        leader['any_slot']+=r['n']
                        leader['captain' if roster[0]['id']==leader['player_id'] else 'flex']+=r['n']
        for leader in leaders:
            assert leader['any_slot']==leader['captain']+leader['flex']
            for metric in ['any_slot','captain','flex']:
                leader[metric+'_percent']=100*leader[metric]/block['resolved_paid_entries'] if block['resolved_paid_entries'] else None
        results.append(block)
    return dict(scope='2026 Weeks 1–4 imported Showdown games',leader_basis='Each team highest season-average DK points per participating game through prior week, among salary-listed RB/WR/TE/K; no QBs or DST. Current/future weeks excluded. Tied leaders qualify. Missing history is not zero.',percentage_basis='Resolved paid entries, whole tie group within verified paid places; duplicated entries retained',history_warnings=history_warnings,results=results)

if __name__=='__main__':
    with engine.connect() as c:r=run(c)
    p=Path('artifacts/captain_season_average_leaders');p.mkdir(exist_ok=True)
    (p/'report.json').write_text(json.dumps(r,indent=2,default=str)+'\n')
    for b in r['results']:
        print(b['week'],b['slate'],'paid',b.get('resolved_paid_entries'),'unresolved',b.get('unresolved_paid_entries'))
        for a in b.get('leaders',[]):print(a['team'],a['name'],a['season_ppg'],'any',a['any_slot_percent'],'CPT',a['captain_percent'],'missing_actuals',len(a['missing_prior_history_players']))
