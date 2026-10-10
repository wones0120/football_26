"""Offline, descriptive DraftKings Classic contest construction study.

Reads only hashed research exports. No optimizer, API, write-to-DB, or live-source calls.
Success means top 10% by contest rank, including boundary ties. No cashing inference.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime
from itertools import combinations
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/classic_historical_study'
POPS = ('winner', 'top_01', 'top_1', 'top_10', 'field')
CONDITIONAL_METRICS = ('qb_traditional_stack','qb_same_team_rb','qb_rb_instead_of_pc','qb_rb_added_to_pc',
    'qb_2pc_1bring','qb_1pc_1bring','qb_pc_without_bring','secondary_opposing_mini',
    'four_plus_team_all','four_plus_team_offense','four_plus_qb_team_offense',
    'four_jax_all','four_jax_offense','two_rb_same_game','two_rb_same_team',
    'two_correlated_environments','rb_dst_same_team','wr_opposing_wr','rb_opposing_pc',
    'qb_pass_catchers','bring_back_bucket','unrelated_oneoffs','flex_position')
SLOTS = re.compile(r'\b(CPT|DST|FLEX|QB|RB|WR|TE)\s+(.+?)(?=\s+(?:CPT|DST|FLEX|QB|RB|WR|TE)\s+|$)')


def norm(value):
    value = re.sub(r'\s+(jr\.?|sr\.?|ii|iii|iv)$', '', str(value).strip().lower())
    return re.sub(r'[^a-z0-9]', '', value)


def team(value):
    return {'LA': 'LAR', 'JAC': 'JAX', 'WSH': 'WAS', 'SD': 'LAC', 'OAK': 'LV'}.get(value, value)


def numeric(value):
    try:
        result = float(str(value).rstrip('%'))
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def game_key(a, b):
    return '|'.join(sorted((team(a), team(b))))


def salary_lock(rows):
    dates = [re.search(r'(\d{2}/\d{2}/\d{4} \d{2}:\d{2}[AP]M)', r.get('game_info') or '') for r in rows]
    return min((datetime.strptime(m[1], '%m/%d/%Y %I:%M%p').replace(tzinfo=ZoneInfo('America/New_York')) for m in dates if m), default=None)


def build_players(salaries, observations, projections):
    """Source/slate/slot constrained salary identity, never a global name-only join.

    A missing canonical ID may retain a uniquely identified native DK salary ID;
    it is audited separately. Multiple possible IDs/teams/positions are quarantined.
    """
    index = defaultdict(list)
    for r in salaries:
        if r['position'] in {'QB', 'RB', 'WR', 'TE', 'DST'} and r.get('team') and r.get('opponent') and r.get('source_player_key'):
            index[norm(r['player_name'])].append(r)
    observed = defaultdict(list)
    for r in observations:
        observed[(norm(r['player_display_name']), r['roster_position'])].append(r)
    cache = {}

    def resolve(slot, name):
        key = slot, norm(name)
        if key in cache:
            return cache[key]
        allowed = {'RB', 'WR', 'TE'} if slot == 'FLEX' else {slot}
        rows = [r for r in index[key[1]] if r['position'] in allowed]
        identities = {(r.get('player_master_id') or 'dk:'+r['source_player_key'], team(r['team']), team(r['opponent']), r['position']) for r in rows}
        if len(identities) != 1:
            cache[key] = None
            return None
        identity, tm, opponent, position = next(iter(identities))
        salary_values = {r['salary'] for r in rows}
        obs = observed.get((key[1], position), []) or observed.get((key[1], slot), [])
        # Append-only reviewed decisions may repeat; conflicting numeric values stay unavailable.
        owns = {numeric(r.get('pct_drafted', r.get('actual_ownership'))) for r in obs} - {None}
        points = {numeric(r.get('fpts', r.get('actual_points'))) for r in obs} - {None}
        result = {'id': identity, 'team': tm, 'opponent': opponent, 'position': position,
                  'game': game_key(tm, opponent), 'salary': next(iter(salary_values)) if len(salary_values)==1 else None,
                  'ownership': next(iter(owns)) if len(owns)==1 else None,
                  'points': next(iter(points)) if len(points)==1 else None,
                  'projection': projections.get(identity), 'canonical': not identity.startswith('dk:'),
                  'source_keys': sorted({r['source_player_key'] for r in rows})}
        cache[key] = result
        return result
    return resolve, cache


def lagged_usage(rows, season, week):
    """Earlier completed weeks only, keyed by canonical identity. No current-week outcomes."""
    history=defaultdict(dict)
    conflicts=set()
    for r in rows:
        if (r['season'],r['week']) >= (season,week):
            continue
        key=(r['player_master_id'],r['season'],r['week'])
        values=(numeric(r['carries']),numeric(r['rushing_yards']),numeric(r['targets']))
        if key in history[r['player_master_id']] and history[r['player_master_id']][key]!=values:
            conflicts.add(key)
        history[r['player_master_id']][key]=values
    result={}
    for identity, games in history.items():
        ordered=[v for k,v in sorted(games.items(),key=lambda x:x[0][1:],reverse=True) if k not in conflicts][:8]
        if len(ordered)<4 or any(v[0] is None or v[1] is None or v[2] is None for v in ordered):
            continue
        result[identity]={'games':len(ordered),'carries':sum(v[0] for v in ordered)/len(ordered),
            'rush_yards':sum(v[1] for v in ordered)/len(ordered),'targets':sum(v[2] for v in ordered)/len(ordered)}
    return result


def market_frame(salaries, season, week, support):
    lock = salary_lock(salaries)
    games = {game_key(r['team'], r['opponent']) for r in salaries if r.get('team') and r.get('opponent')}
    candidates = defaultdict(list)
    provenance = []
    if not lock:
        return {}, {'slate_games': len(games), 'market_games': 0, 'relative_ranks_available': False}
    for source in support['market_sources']:
        meta = source['metadata']
        observed = datetime.fromisoformat(meta['observed_at'])
        captured = datetime.fromisoformat(meta['captured_at'])
        if not source['hash_matches'] or max(observed, captured) >= lock:
            continue
        for row in source['rows']:
            if numeric(row.get('season')) != season or numeric(row.get('week')) != week:
                continue
            a, h = team(row.get('away_team')), team(row.get('home_team'))
            if not a or not h or game_key(a, h) not in games:
                continue
            total = numeric(row.get('total_line', row.get('game_total')))
            # nflverse spread_line is home expected margin; normalized home_spread is its negative.
            spread = numeric(row.get('home_spread'))
            if spread is None:
                margin = numeric(row.get('spread_line'))
                spread = -margin if margin is not None else None
            if total is None or total <= 0 or spread is None:
                continue
            candidates[game_key(a,h)].append((max(observed,captured), {'total': total, 'home_spread': spread,
                'home': h, 'away': a, 'source_snapshot': meta['snapshot_id'], 'observed_at': str(observed), 'captured_at':str(captured)}))
    markets = {g: max(values, key=lambda x:x[0])[1] for g,values in candidates.items()}
    complete = len(markets)==len(games) and bool(games)
    for m in markets.values():
        m['team_totals'] = {m['home']: (m['total']-m['home_spread'])/2, m['away']: (m['total']+m['home_spread'])/2}
    for g, m in markets.items():
        if complete:
            totals = [r['total'] for r in markets.values()]
            rank = 1 + sum(v > m['total'] for v in totals)
            # Midrank percentile: lowest -> near 0, highest -> near 1; tie-aware.
            pct = (sum(v < m['total'] for v in totals) + .5*sum(v == m['total'] for v in totals))/len(totals)
            m.update(rank=rank, percentile=pct)
            all_team_totals = [v for r in markets.values() for v in r['team_totals'].values()]
            m['team_ranks'] = {t:1+sum(v>tt for v in all_team_totals) for t,tt in m['team_totals'].items()}
            m['team_percentiles'] = {t:(sum(v<tt for v in all_team_totals)+.5*sum(v==tt for v in all_team_totals))/len(all_team_totals) for t,tt in m['team_totals'].items()}
        provenance.append({'game':g, **m})
    return markets, {'lock':str(lock), 'slate_games':len(games), 'market_games':len(markets),
                     'relative_ranks_available':complete,'games':provenance}


def classify(players, markets, projection_top, usage=None):
    qb = next(p for p in players if p['position']=='QB')
    offense = [p for p in players if p['position']!='DST']
    same = [p for p in offense if p['team']==qb['team'] and p['position']!='QB']
    pcs = [p for p in same if p['position'] in {'WR','TE'}]
    backs = [p for p in same if p['position']=='RB']
    bring = [p for p in offense if p['team']==qb['opponent']]
    rbs = [p for p in players if p['position']=='RB']
    team_counts = Counter(p['team'] for p in players)
    offensive_teams = Counter(p['team'] for p in offense)
    game_counts = Counter(p['game'] for p in players)
    outside = [p for p in offense if p['game']!=qb['game']]
    outside_counts = Counter(p['game'] for p in outside)
    oneoffs = [p for p in outside if outside_counts[p['game']]==1]
    dst=next(p for p in players if p['position']=='DST')
    other_pairs = [pair for pair in combinations(outside,2) if pair[0]['game']==pair[1]['game'] and pair[0]['team']!=pair[1]['team']]
    correlated_secondary_games = {a['game'] for a,b in other_pairs}
    pc_combo = '+'.join(sorted(p['position'] for p in pcs)) or 'none'
    usage=usage or {}
    qu=usage.get(qb['id'])
    f = {'qb_pass_catchers':len(pcs),'qb_pc_positions':pc_combo,'qb_same_team_rb':bool(backs),
         'qb_traditional_stack':bool(pcs),'qb_alone_offense':not same,
         'qb_rb_instead_of_pc':bool(backs) and not pcs,'qb_rb_added_to_pc':bool(backs) and bool(pcs),
         'qb_has_wr':any(p['position']=='WR' for p in pcs),'qb_has_te':any(p['position']=='TE' for p in pcs),
         'qb_offensive_teammates':len(same),'qb_team_offense_including_qb':len(same)+1,
         'qb_team_all_including_dst':team_counts[qb['team']],
         'qb_2_teammates_including_rb':len(same)==2 and bool(backs),
         'qb_3_teammates_including_rb':len(same)==3 and bool(backs),
         'qb_family':f"QB+{len(pcs)}PC+{len(backs)}RB",
         'bring_backs':len(bring),'bring_back_bucket':str(len(bring)) if len(bring)<2 else '2+',
         'bring_back_position':'none' if not bring else bring[0]['position'] if len(bring)==1 else 'multiple',
         'bring_back_rb':any(p['position']=='RB' for p in bring),
         'qb_2pc_1bring':len(pcs)==2 and len(bring)==1,
         'qb_1pc_1bring':len(pcs)==1 and len(bring)==1,
         'qb_pc_without_bring':bool(pcs) and not bring,
         'qb_game_all_players':game_counts[qb['game']],
         'qb_game_offensive_players':sum(p['game']==qb['game'] for p in offense),
         'rb_count':len(rbs), 'flex_position':'RB' if len(rbs)==3 else 'TE' if sum(p['position']=='TE' for p in players)==2 else 'WR',
         'two_rb_same_game':any(a['game']==b['game'] for a,b in combinations(rbs,2)),
         'two_rb_same_team':any(a['team']==b['team'] for a,b in combinations(rbs,2)),
         'rb_opposing_pc':any(a['position']=='RB' and b['position'] in {'WR','TE'} and a['team']==b['opponent'] for a in offense for b in offense),
         'wr_opposing_wr':any(a['position']==b['position']=='WR' and a['team']==b['opponent'] for a,b in combinations(offense,2)),
         'max_team_all':max(team_counts.values()), 'max_team_offense':max(offensive_teams.values()),
         'max_team_bucket':'2 or fewer' if max(team_counts.values())<=2 else '3' if max(team_counts.values())==3 else '4+',
         'four_plus_team_all':max(team_counts.values())>=4,'four_plus_team_offense':max(offensive_teams.values())>=4,
         'four_plus_qb_team_offense':len(same)+1>=4,
         'four_jax_all':team_counts['JAX']>=4,'four_jax_offense':offensive_teams['JAX']>=4,
         'max_game_all':max(game_counts.values()),'distinct_teams':len(team_counts),'distinct_games':len(game_counts),
         'games_with_1':sum(v==1 for v in game_counts.values()),'games_with_2':sum(v==2 for v in game_counts.values()),
         'games_with_3plus':sum(v>=3 for v in game_counts.values()),
         'outside_primary_offense':len(outside),'unrelated_oneoffs':len(oneoffs),
         'true_unrelated_oneoffs':sum(p['game']!=dst['game'] for p in oneoffs),
         'oneoff_dst_same_team_count':sum(p['team']==dst['team'] for p in oneoffs),
         'oneoff_against_dst_count':sum(p['team']==dst['opponent'] for p in oneoffs),
         'outside_distinct_games':len(outside_counts),'secondary_two_player_games':sum(v==2 for v in outside_counts.values()),
         'secondary_opposing_mini':bool(other_pairs),'secondary_opposing_game_count':len(correlated_secondary_games),
         'two_correlated_environments':bool(pcs) and bool(correlated_secondary_games),
         'secondary_rb_opposing_pc':any((a['position']=='RB' and b['position'] in {'WR','TE'}) or (b['position']=='RB' and a['position'] in {'WR','TE'}) for a,b in other_pairs),
         'secondary_wr_opposing_pc':any((a['position']=='WR' and b['position'] in {'WR','TE'}) or (b['position']=='WR' and a['position'] in {'WR','TE'}) for a,b in other_pairs),
         'secondary_te_opposing_pc':any((a['position']=='TE' and b['position'] in {'WR','TE'}) or (b['position']=='TE' and a['position'] in {'WR','TE'}) for a,b in other_pairs),
         'rb_dst_same_team':any(p['team']==next(d['team'] for d in players if d['position']=='DST') for p in rbs),
         'offense_against_dst':sum(p['team']==next(d['opponent'] for d in players if d['position']=='DST') for p in offense),
         'all_canonical_ids':all(p['canonical'] for p in players),
         'qb_rushing_oriented':qu['carries']>=5 or qu['rush_yards']>=30 if qu else None,
         'qb_prior_carry_bucket':None if not qu else '<2' if qu['carries']<2 else '2-4.9' if qu['carries']<5 else '5+',
    }
    if all(p['salary'] is not None for p in players):
        salary = sum(p['salary'] for p in players)
        f.update(salary_used=salary, salary_left_bucket='0' if salary==50000 else '1-500' if salary>=49500 else '501-1000' if salary>=49000 else '>1000',
                 low_salary_rb=any(p['salary']<=4500 for p in rbs), two_high_salary_rb=sum(p['salary']>=7000 for p in rbs)>=2,
                 oneoff_low_salary_count=sum(p['salary']<=4500 for p in oneoffs))
    else:
        f.update(salary_used=None,salary_left_bucket=None,low_salary_rb=None,two_high_salary_rb=None,oneoff_low_salary_count=None)
    if all(p['ownership'] is not None for p in players):
        own = sum(p['ownership'] for p in players)
        f.update(ownership_sum_bucket='<100' if own<100 else '100-149.9' if own<150 else '150-199.9' if own<200 else '200+',
                 high_owned_players=sum(p['ownership']>=20 for p in players),low_owned_players=sum(p['ownership']<=5 for p in players))
    else:
        f.update(ownership_sum_bucket=None,high_owned_players=None,low_owned_players=None)
    f['two_high_salary_high_owned_rb'] = (sum(p['salary']>=7000 and p['ownership']>=20 for p in rbs)>=2
        if all(p['salary'] is not None and p['ownership'] is not None for p in rbs) else None)
    for label, test in [('oneoff_chalk_count',lambda p:p['ownership']>=20),('oneoff_low_owned_count',lambda p:p['ownership']<=5)]:
        f[label] = sum(test(p) for p in oneoffs) if all(p['ownership'] is not None for p in oneoffs) else None
    f['oneoff_top10_position_projection_count'] = sum(p['id'] in projection_top for p in oneoffs) if projection_top and all(p['projection'] is not None for p in oneoffs) else None
    qm = markets.get(qb['game'])
    if qm:
        total = qm['total']; spread = qm['home_spread'] if qb['team']==qm['home'] else -qm['home_spread']
        f.update(qb_game_total_bucket='<40' if total<40 else '40-44.5' if total<45 else '45-49.5' if total<50 else '50+',
                 qb_team_total_bucket='<22' if qm['team_totals'][qb['team']]<22 else '22-25.9' if qm['team_totals'][qb['team']]<26 else '26+',
                 qb_favorite=spread<0)
    else:
        f.update(qb_game_total_bucket=None,qb_team_total_bucket=None,qb_favorite=None)
    if qm and 'rank' in qm:
        f.update(qb_highest_total=qm['rank']==1,qb_top3_total=qm['rank']<=3,qb_total_rank=qm['rank'],
                 qb_total_relative='top25%' if qm['percentile']>=.75 else 'bottom25%' if qm['percentile']<=.25 else 'middle50%',
                 qb_top25_total=qm['percentile']>=.75,qb_top3_team_total=qm['team_ranks'][qb['team']]<=3)
    else:
        f.update(qb_highest_total=None,qb_top3_total=None,qb_total_rank=None,qb_total_relative=None,qb_top25_total=None,qb_top3_team_total=None)
    def is_favorite(p):
        m=markets[p['game']]
        return (m['home_spread'] if p['team']==m['home'] else -m['home_spread'])<0
    for label, group in [('rb',rbs),('oneoff',oneoffs)]:
        available=all(p['game'] in markets for p in group)
        f[label+'_favorite_count']=sum(is_favorite(p) for p in group) if available else None
        f[label+'_underdog_count']=sum(not is_favorite(p) and markets[p['game']]['home_spread']!=0 for p in group) if available else None
        f[label+'_high_implied_count']=sum(markets[p['game']]['team_totals'][p['team']]>=26 for p in group) if available else None
        f[label+'_top25_game_count']=sum(markets[p['game']]['percentile']>=.75 for p in group) if available and all('rank' in markets[p['game']] for p in group) else None
    ranked=all(p['game'] in markets and 'rank' in markets[p['game']] for p in oneoffs)
    f['oneoff_middle50_game_count']=sum(.25<markets[p['game']]['percentile']<.75 for p in oneoffs) if ranked else None
    f['oneoff_bottom25_game_count']=sum(markets[p['game']]['percentile']<=.25 for p in oneoffs) if ranked else None
    f['oneoff_top25_team_total_count']=sum(markets[p['game']]['team_percentiles'][p['team']]>=.75 for p in oneoffs) if ranked else None
    f['oneoff_underdog_prior_volume_count']=(sum(not is_favorite(p) and markets[p['game']]['home_spread']!=0 and
        (usage[p['id']]['carries']>=15 if p['position']=='RB' else usage[p['id']]['targets']>=7) for p in oneoffs)
        if all(p['id'] in usage and p['game'] in markets for p in oneoffs) else None)
    return f


def add(counters, features, weight):
    for metric, value in features.items():
        key = 'unavailable' if value is None else 'yes' if value is True else 'no' if value is False else str(value)
        counters[metric][key]+=weight


def analyze_contest(payload, inventory, support):
    contest=payload['contest']; season,week=contest['season'],contest['week']
    if not payload['entries']:
        return {'contest':contest,'status':'empty'}
    slots = Counter()
    for row in payload['entries']:
        parsed=SLOTS.findall(row['lineup_text'] or '')
        slots['showdown' if any(s=='CPT' for s,n in parsed) else 'classic' if len(parsed)==9 and Counter(s for s,n in parsed)==Counter({'QB':1,'RB':2,'WR':3,'TE':1,'FLEX':1,'DST':1}) else 'invalid']+=row['n']
    if not slots['classic']:
        return {'contest':contest,'status':'not_classic','roster_formats':dict(slots)}
    # These three fields' raw side tables, nine-slot rosters, and salary membership
    # establish Main membership; retain original metadata and explicit correction.
    scope='SUNDAY_MAIN' if season==2026 and week==2 else contest['slate_id'].upper()
    salaries=[r for r in inventory['salaries'] if r['season']==season and r['week']==week and r['slate'].upper()==scope]
    observation_rows=payload['observations'][:]
    latest={}
    for r in payload['reviewed']:
        latest[(norm(r['player_display_name']),r['roster_position'])]=r
    observation_rows.extend(latest.values())
    proj=support['projections'].get(str(week),{}) if season==2026 and scope=='SUNDAY_MAIN' else {}
    projections={r['player_id']:r['mean'] for r in proj.get('players',[])}
    resolve,cache=build_players(salaries,observation_rows,projections)
    usage=lagged_usage(support.get('prior_usage',[]),season,week)
    markets,market_inventory=market_frame(salaries,season,week,support)
    projection_positions=defaultdict(dict)
    for r in salaries:
        if r['player_master_id'] in projections:
            projection_positions[r['position']][r['player_master_id']]=projections[r['player_master_id']]
    top=set()
    for values in projection_positions.values():
        vals=sorted(values.values(),reverse=True)
        threshold=vals[min(9,len(vals)-1)]
        top.update(k for k,v in values.items() if v>=threshold)
    counters={p:{w:defaultdict(Counter) for w in ('entry','unique')} for p in POPS}
    seen={p:set() for p in POPS}; audit=Counter(); unavailable=Counter(); raw_pop=Counter(); valid_pop=Counter()
    winners=[]; score_validation=Counter(); by_qb=defaultdict(lambda:defaultdict(lambda:defaultdict(Counter)))
    for row in payload['entries']:
        weights={p:row['n'] if p=='field' else row[p] for p in POPS}
        raw_pop.update(weights)
        parsed=SLOTS.findall(row['lineup_text'] or '')
        if len(parsed)!=9 or Counter(s for s,n in parsed)!=Counter({'QB':1,'RB':2,'WR':3,'TE':1,'FLEX':1,'DST':1}):
            audit['invalid_roster_entries']+=row['n'];continue
        players=[resolve(s,n) for s,n in parsed]
        if any(p is None for p in players):
            audit['unresolved_entries']+=row['n']
            for (s,n),p in zip(parsed,players):
                if p is None:unavailable[f'{s}|{n}']+=row['n']
            continue
        if len({p['id'] for p in players})!=9:
            audit['duplicate_player_entries']+=row['n'];continue
        features=classify(players,markets,top,usage)
        if features['salary_used'] is not None and features['salary_used']>50000:
            audit['over_salary_cap_entries']+=row['n'];continue
        sig=hashlib.sha256('|'.join(sorted(p['id'] for p in players)).encode()).digest()
        if all(p['points'] is not None for p in players) and row['min_points'] is not None and row['max_points'] is not None:
            pts=sum(p['points'] for p in players)
            match=abs(pts-row['min_points'])<=.05 and abs(pts-row['max_points'])<=.05
            score_validation['matched' if match else 'mismatched']+=row['n']
        else:
            score_validation['unavailable']+=row['n']
        valid_pop.update(weights)
        qb_id=next(p['id'] for p in players if p['position']=='QB')
        for pop,weight in [('field',row['n']),('top_10',row['top_10'])]:
            if weight:
                add(by_qb[qb_id][pop],{m:features[m] for m in CONDITIONAL_METRICS},weight)
        for pop,weight in weights.items():
            if not weight:continue
            add(counters[pop]['entry'],features,weight)
            if sig not in seen[pop]:
                seen[pop].add(sig);add(counters[pop]['unique'],features,1)
        if row['winner']:
            winners.append({'lineup_text':row['lineup_text'],'entry_count':row['winner'],'points':row['max_points'],
                'signature':sig.hex(),'features':features,'players':players})
    return {'contest':contest,'status':'analyzed','analysis_scope':scope,'scope_corrected':scope!=contest['slate_id'].upper(),
        'slate_key':f'{season}-W{week:02d}-{scope}', 'roster_formats':dict(slots),'market_inventory':market_inventory,
        'projection_run':proj.get('run'),'salary_rows':len(salaries),'raw_population_entries':dict(raw_pop),
        'valid_population_entries':dict(valid_pop),'unique_population_rosters':{p:len(v) for p,v in seen.items()},
        'audit':dict(audit),'unresolved_player_tokens':dict(unavailable),'score_validation':dict(score_validation),
        'winners':winners,'distributions':{p:{w:{m:dict(v) for m,v in metrics.items()} for w,metrics in weights.items()} for p,weights in counters.items()},
        'qb_conditioned':{q:{p:{m:dict(v) for m,v in metrics.items()} for p,metrics in pops.items()} for q,pops in by_qb.items()},
        'success_definition':'top 10% contest rank inclusive of cutoff ties; cashing analysis omitted per user',
        'identity_policy':'season/week/slate salary + compatible slot + unique native/canonical identity/team/opponent/position'}


def field_bucket(n):
    return '<1000' if n<1000 else '1000-4999' if n<5000 else '5000-19999' if n<20000 else '20000+'


def aggregate(contests, pop, weighting, metric, value):
    hit=known=missing=0;rates=[];field_rates=[];by_slate=defaultdict(list)
    for c in contests:
        d=c['distributions'][pop][weighting].get(metric,{})
        total=sum(d.values());unk=d.get('unavailable',0);denom=total-unk
        fd=c['distributions']['field'][weighting].get(metric,{})
        fden=sum(fd.values())-fd.get('unavailable',0)
        missing+=unk
        if not denom:continue
        hit+=d.get(value,0);known+=denom;rates.append(d.get(value,0)/denom)
        if fden:
            fr=fd.get(value,0)/fden; field_rates.append(fr)
            by_slate[c['slate_key']].append((d.get(value,0)/denom,fr))
    cf=float(np.mean(rates)) if rates else None
    ff=float(np.mean(field_rates)) if field_rates else None
    slate_pairs=[np.mean(v,axis=0) for v in by_slate.values()]
    ratio=lo=hi=None
    if slate_pairs:
        arr=np.array(slate_pairs); means=arr.mean(axis=0)
        ratio=float(means[0]/means[1]) if means[1]>0 else None
        if len(arr)>=5 and ratio is not None:
            rng=np.random.default_rng(20261004)
            samples=arr[rng.integers(0,len(arr),size=(3000,len(arr)))].mean(axis=1)
            ratios=samples[:,0]/samples[:,1] if np.all(samples[:,1]>0) else samples[samples[:,1]>0,0]/samples[samples[:,1]>0,1]
            if len(ratios):lo,hi=map(float,np.quantile(ratios,[.025,.975]))
    return {'hits':hit,'known':known,'unavailable':missing,'rate':hit/known if known else None,
        'contest_mean_rate':cf,'contest_mean_field_rate':ff,'contest_mean_lift':cf/ff if cf is not None and ff else None,
        'slate_mean_lift':ratio,'slate_bootstrap_lift_low':lo,'slate_bootstrap_lift_high':hi,
        'contests':len(rates),'independent_slates':len(slate_pairs)}


def main():
    inventory=json.loads((OUT/'inventory_snapshot.json').read_text())
    support=json.loads((OUT/'support_snapshot.json').read_text())
    support['prior_usage']=json.loads((OUT/'native_prior_usage_snapshot.json').read_text())
    results=[]
    analysis_hash=hashlib.sha256(Path(__file__).read_bytes()+json.dumps(support,sort_keys=True).encode()+
        (OUT/'inventory_snapshot.json').read_bytes()+(OUT/'input_hashes.json').read_bytes()).hexdigest()
    expected=json.loads((OUT/'input_hashes.json').read_text())
    for path in sorted((OUT/'inputs').glob('*.gz')):
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected[str(path.relative_to(ROOT))]:
            raise ValueError('Input checksum mismatch: '+str(path))
        # Reuse already analyzed contests; raw exports are immutable and hashed.
        dest=OUT/'contests'/path.name.replace('.json.gz','.json')
        dest.parent.mkdir(exist_ok=True)
        if dest.exists():
            result=json.loads(dest.read_text())
        if not dest.exists() or result.get('analysis_sha256')!=analysis_hash:
            result=analyze_contest(json.load(gzip.open(path,'rt')),inventory,support)
            result['analysis_sha256']=analysis_hash
            dest.write_text(json.dumps(result,sort_keys=True,indent=2,allow_nan=False)+'\n')
        results.append(result)
        print(result['contest']['season'],result['contest']['week'],result['contest']['contest_id'],result['status'],result.get('audit'),flush=True)
    analyzed=[r for r in results if r['status']=='analyzed']
    strata={'all':analyzed}
    for r in analyzed:
        for label in ['season_'+str(r['contest']['season']), 'field_'+field_bucket(r['contest']['field_size']),
                      'slate_'+str(r['market_inventory']['slate_games']), 'scope_'+r['analysis_scope']]:
            strata.setdefault(label,[]).append(r)
    summary=[]
    for stratum,contests in strata.items():
        values=defaultdict(set)
        for c in contests:
            for m,d in c['distributions']['field']['entry'].items():values[m].update(set(d)-{'unavailable'})
        for metric,categories in values.items():
            for value in sorted(categories):
                for pop in POPS:
                    for weighting in ('entry','unique'):
                        stats=aggregate(contests,pop,weighting,metric,value)
                        field=aggregate(contests,'field',weighting,metric,value)
                        summary.append({'stratum':stratum,'population':pop,'weighting':weighting,'metric':metric,'value':value,
                            **stats,'field_rate':field['rate'],'pooled_lift':stats['rate']/field['rate'] if stats['rate'] is not None and field['rate'] else None})
    with (OUT/'summary.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(summary[0]));w.writeheader();w.writerows(summary)
    conditional=[]
    for stratum,contests in strata.items():
        for metric in CONDITIONAL_METRICS:
            values=set(v for c in contests for q,pops in c['qb_conditioned'].items() for v in pops['field'].get(metric,{}) if v!='unavailable')
            for value in sorted(values):
                by_slate=defaultdict(lambda:np.zeros(2));groups=0
                for c in contests:
                    for q,pops in c['qb_conditioned'].items():
                        fd=pops['field'].get(metric,{});td=pops.get('top_10',{}).get(metric,{})
                        a=td.get(value,0);b=fd.get(value,0)-a
                        cs=sum(v for k,v in td.items() if k not in {value,'unavailable'})
                        d=sum(v for k,v in fd.items() if k not in {value,'unavailable'})-cs
                        n=a+b+cs+d
                        if n and a+b and cs+d:
                            by_slate[c['slate_key']]+=np.array([a*d/n,b*cs/n]);groups+=1
                vals=np.array(list(by_slate.values()));total=vals.sum(axis=0) if len(vals) else [0,0]
                odds=float(total[0]/total[1]) if total[1]>0 else None
                low=high=None
                if len(vals)>=5 and odds is not None:
                    rng=np.random.default_rng(20261004)
                    samples=vals[rng.integers(0,len(vals),size=(3000,len(vals)))].sum(axis=1)
                    ratios=samples[samples[:,1]>0,0]/samples[samples[:,1]>0,1]
                    low,high=map(float,np.quantile(ratios,[.025,.975]))
                conditional.append({'stratum':stratum,'metric':metric,'value':value,'qb_contest_groups':groups,
                    'slates':len(vals),'mh_top10_odds_ratio':odds,'slate_bootstrap_low':low,'slate_bootstrap_high':high})
    with (OUT/'qb_conditioned.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(conditional[0]));w.writeheader();w.writerows(conditional)
    (OUT/'study_summary.json').write_text(json.dumps({'contests':len(analyzed),'slates':len({c['slate_key'] for c in analyzed}),
        'entries':sum(c['raw_population_entries']['field'] for c in analyzed),
        'analyzed_entries':sum(c['valid_population_entries'].get('field',0) for c in analyzed),
        'primary_success_population':'top_10','cashing_analysis':'omitted per user','comparison_populations':list(POPS),
        'strata':{k:len(v) for k,v in strata.items()},'excluded_contests':[{'contest':c['contest'],'status':c['status'],'roster_formats':c.get('roster_formats')} for c in results if c['status']!='analyzed'],
        'seed':20261004,'bootstrap_resamples':3000},sort_keys=True,indent=2)+'\n')
    print('Saved summary:',len(summary),'rows',flush=True)


if __name__=='__main__':
    main()
