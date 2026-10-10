"""Offline Showdown standings study. Never optimizes, ingests, or updates the DB.

PYTHONPATH=. .venv/bin/python scripts/analyze_showdown_qb_construction.py
Fractions in JSON/CSV are 0..1; finish percentiles are 0..100 (lower is better).
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import itertools
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/showdown_qb_construction'
ET = ZoneInfo('America/New_York')
CUTS = {'top20': .20, 'top10': .10, 'top5': .05, 'top1': .01, 'top01': .001, 'winner': None}
GROUPS = {
    'QB Captain': 'captain', 'Non-QB Captain': 'captain',
    'Both QBs': 'starter', 'Exactly one QB': 'starter', 'Zero QB': 'starter',
    'QB Captain + both QBs': 'combination', 'QB Captain + one QB': 'combination',
    'Non-QB Captain + both QBs': 'combination', 'Non-QB Captain + one QB': 'combination',
    'Non-QB Captain + zero QB': 'combination',
    **{f'CPT {p}': 'position' for p in ('QB', 'RB', 'WR', 'TE', 'DST', 'K')},
}
SLOTS = re.compile(r'\b(CPT|FLEX)\s+(.+?)(?=\s+(?:CPT|FLEX)\s+|$)')


def norm(value):
    value = re.sub(r'\s+(jr\.?|sr\.?|ii|iii|iv)$', '', str(value).strip().lower())
    return re.sub(r'[^a-z0-9]', '', value)


def team(value):
    return {'LA': 'LAR', 'JAC': 'JAX', 'WSH': 'WAS', 'SD': 'LAC', 'OAK': 'LV'}.get(str(value).upper(), str(value).upper())


def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def divide(a, b):
    return a / b if b and a is not None else None


def timestamp(value):
    if not value:
        return None
    d = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return d if d.tzinfo else d.replace(tzinfo=ET)


def parse_lineup(value):
    value = (value or '').strip()
    parts = [(m[1], m[2].strip()) for m in SLOTS.finditer(value)]
    if len(parts) != 6 or [s for s, _ in parts] != ['CPT'] + ['FLEX'] * 5:
        return None
    # Require the whole string to parse; don't accept a Classic prefix.
    if not value.startswith('CPT '):
        return None
    return parts


def weighted_median(values):
    values = sorted(values)
    n = sum(w for _, w in values)
    if not n:
        return None
    targets = ((n - 1) // 2, n // 2)
    result, cumulative = [], 0
    for value, weight in values:
        for target in targets[len(result):]:
            if cumulative <= target < cumulative + weight:
                result.append(value)
            else:
                break
        cumulative += weight
        if len(result) == 2:
            break
    return sum(result) / 2


def raw_to_salary(row, aliases):
    r = row['raw_row_json']
    tm = team(r.get('TeamAbbrev'))
    pos = str(r.get('Position') or '').upper()
    ids = {a['player_master_id'] for a in aliases.get(str(row['source_player_key']), [])
           if team(a['team']) == tm and a['position'] == pos}
    match = re.match(r'(\w+)@(\w+)', r.get('Game Info') or '')
    opponent = next((team(t) for t in match.groups() if team(t) != tm), None) if match else None
    return {'season': row['season'], 'week': row['week'], 'slate': row['slate'],
            'team': tm, 'opponent': opponent, 'position': pos,
            'player_name': r.get('Name'), 'source_player_key': str(row['source_player_key']),
            'player_master_id': next(iter(ids)) if len(ids) == 1 else None,
            'roster_position': r.get('Roster Position'), 'salary': r.get('Salary'),
            'game_info': r.get('Game Info'), 'ingest_run_id': row['ingest_run_id'],
            'recovered_raw': True}


def salary_pools(salaries):
    pools = defaultdict(list)
    for row in salaries:
        if not row.get('source_player_key') or not row.get('team') or not row.get('opponent'):
            continue
        key = (row['season'], row['week'], str(row['slate']).lower(),
               tuple(sorted((team(row['team']), team(row['opponent'])))))
        pools[key].append(row)
    return pools


def select_pool(contest, entries, pools):
    names = Counter()
    for row in entries:
        for _, name in parse_lineup(row['lineup_text']) or []:
            names[norm(name)] += row['n']
    candidates = []
    for key, rows in pools.items():
        if key[0] != contest['season'] or abs(key[1] - contest['week']) > 1:
            continue
        known = {norm(r['player_name']) for r in rows}
        score = sum(n for name, n in names.items() if name in known)
        exact = key[2] == contest['slate_id'].lower().removesuffix('_captain')
        sd = any(r['roster_position'] == 'CPT' for r in rows)
        candidates.append((score, key[1] == contest['week'], exact, sd, key, rows))
    candidates.sort(key=lambda r: r[:5], reverse=True)
    if not candidates or not names:
        return None, [], 0
    best = candidates[0]
    # A second source for the same matchup is fine; a tied different matchup is not.
    if any(r[0] == best[0] and r[4][3] != best[4][3] for r in candidates[1:]):
        return None, [], divide(best[0], sum(names.values()))
    coverage = divide(best[0], sum(names.values()))
    if coverage < .80:
        return None, [], coverage
    return best[4], best[5], coverage


def build_resolver(pool_key, rows, aliases):
    """Unique source/game/team/position identity. Conflicts remain unresolved.

    Standings text has no native IDs. A salary match must be unique within the
    selected source slate/game and carry team, position and native/canonical ID.
    Alias fallback is constrained to the two game teams and observed season;
    it supplies identity only, never missing Showdown salary or starter status.
    """
    salary_index = defaultdict(list)
    for row in rows:
        salary_index[norm(row['player_name'])].append(row)
    alias_index = defaultdict(list)
    if pool_key:
        for row in aliases:
            if team(row.get('team')) in pool_key[3] and (row.get('first_seen_season') or 9999) <= pool_key[0]:
                alias_index[norm(row['alias_name'])].append(row)
    cache = {}
    def resolve(slot, name):
        key = slot, norm(name)
        if key in cache:
            return cache[key]
        possible = salary_index[key[1]]
        identities = {(r.get('player_master_id') or 'dk:'+str(r['source_player_key']),
                       team(r['team']), r['position']) for r in possible}
        # Slot-native DK IDs differ between Captain and FLEX. Prefer canonical
        # identity; if absent, require one native FLEX ID for the player.
        if len(identities) != 1:
            canonical = {(r['player_master_id'], team(r['team']), r['position'])
                         for r in possible if r.get('player_master_id')}
            known_native = {(str(r['source_player_key']),team(r['team']),r['position'])
                            for r in possible if r.get('player_master_id')}
            if len(canonical) == 1 and all(r.get('player_master_id') or
                    (str(r['source_player_key']),team(r['team']),r['position']) in known_native for r in possible):
                identities = canonical
            elif not canonical:
                native_flex = {(str(r['source_player_key']),team(r['team']),r['position'])
                               for r in possible if r['roster_position']=='FLEX'}
                if len(native_flex)==1 and len({(team(r['team']),r['position']) for r in possible})==1:
                    native,tm,pos=next(iter(native_flex));identities={('dk:'+native,tm,pos)}
        basis = 'source_slate_salary'
        if len(identities) != 1:
            if possible:  # Never override conflicting salary identities with aliases.
                cache[key] = None
                return None
            identities = {(r['player_master_id'], team(r['team']), r['position'])
                          for r in alias_index[key[1]] if r.get('position') in {'QB','RB','WR','TE','DST','K'}}
            basis = 'source_game_team_position_alias'
        if len(identities) != 1:
            cache[key] = None
            return None
        identity, tm, pos = next(iter(identities))
        native_slot = [r for r in possible if r['roster_position'] == slot]
        salaries = {number(r['salary']) for r in native_slot} - {None}
        flex = {number(r['salary']) for r in possible if r['roster_position']=='FLEX'} - {None}
        result = {'id':identity, 'team':tm, 'position':pos, 'name':name,
                  'salary':next(iter(salaries)) if len(salaries)==1 else None,
                  'flex_salary':next(iter(flex)) if len(flex)==1 else None, 'identity_basis':basis}
        cache[key] = result
        return result
    return resolve


def game_context(key, rows, support):
    if not key:
        return {'key':None, 'lock':None, 'schedule':None}
    dates = [re.search(r'(\d{2}/\d{2}/\d{4} \d{2}:\d{2}[AP]M)', r.get('game_info') or '') for r in rows]
    dates = {datetime.strptime(m[1], '%m/%d/%Y %I:%M%p').replace(tzinfo=ET) for m in dates if m}
    lock = next(iter(dates)) if len(dates)==1 else None
    candidates = [r for r in support['schedule'] if r['season']==key[0] and r['week']==key[1]
                  and tuple(sorted((team(r['home_team']),team(r['away_team']))))==key[3]]
    candidates.sort(key=lambda r:r['raw_nfl_schedule_id'], reverse=True)
    schedule = candidates[0]['raw_row_json'] if candidates else None
    if schedule and lock and str(schedule.get('gameday')) != lock.date().isoformat():
        schedule = None
    return {'key':f'{key[0]}_{key[1]}_'+ '_'.join(key[3]), 'lock':lock, 'schedule':schedule}


def prior_qb_stats(stats, identity, season, week):
    games = {}
    for row in stats:  # newest native source row first, repeated imports deduplicated
        period = row['season'],row['week']
        if row['player_master_id'] != identity or period >= (season,week):
            continue
        raw = row['raw_row_json']
        if raw.get('season_type') not in (None,'REG'):
            continue
        games.setdefault(period,raw)
    periods = sorted(games,reverse=True)[:3]
    if not periods:
        return None
    values = [games[k] for k in periods]
    attempts = [number(r.get('attempts',r.get('passing_attempts'))) for r in values]
    carries = [number(r.get('carries')) for r in values]
    return {'games':len(periods), 'last_prior_game':list(periods[0]),
            'attempts':sum(attempts)/len(attempts) if all(v is not None for v in attempts) else None,
            'carries':sum(carries)/len(carries) if all(v is not None for v in carries) else None}


def identify_starters(key, rows, resolver, context, support, stats):
    result, rejected = [], []
    if not key or not context['lock']:
        return result, [{'reason':'no independently dated salary game'}]
    for tm in key[3]:
        qbs = {r['id']:r for r in (resolver('FLEX',row['player_name']) for row in rows if row['position']=='QB') if r}
        qbs = [r for r in qbs.values() if r['team']==tm]
        explicit = [r for r in support['starters'] if r['season']==key[0] and r['week']==key[1]
                    and str(r['slate']).lower()==key[2] and team(r['team'])==tm]
        picked = None
        for row in explicit:
            clocks = [timestamp(row.get('created_at')),timestamp(row.get('updated_at')),
                      timestamp((row.get('evidence_json') or {}).get('observed_at'))]
            if any(d and d >= context['lock'] for d in clocks):
                rejected.append({'team':tm,'name':row['player_name'],'reason':'starter row recorded/updated or observed after lock'})
                continue
            if str(row.get('status') or '').lower() in {'out','inactive','ruled_out'}:
                continue
            picked = next((r for r in qbs if r['id']==row['player_master_id']),None)
            if picked:
                picked = {**picked,'method':'archived_pregame_'+row['evidence_tier'],
                          'source':row['source'],'recorded_at':row['created_at']}
                break
        if not picked and qbs:
            # A reconstructed pregame-safe proxy, separately marked as inferred.
            # Never consult current-game attempts, scores or hindsight starter IDs.
            ranked = sorted(qbs,key=lambda r:-(r['flex_salary'] or 0))
            top = ranked[0]
            prior = prior_qb_stats(stats,top['id'],key[0],key[1])
            other_volume = [prior_qb_stats(stats,r['id'],key[0],key[1]) for r in ranked[1:]]
            if (top['flex_salary'] is not None and top['flex_salary']-(ranked[1]['flex_salary'] or 0 if len(ranked)>1 else 0)>=1200
                    and prior and prior['attempts'] is not None and prior['attempts']>=20
                    and not any(p and (p['attempts'] or 0)>prior['attempts']+8 for p in other_volume)):
                picked = {**top,'method':'reconstructed_salary_prior_volume','prior':prior}
        if picked:
            result.append(picked)
        else:
            rejected.append({'team':tm,'reason':'expected starter uncertain; no qualifying pregame evidence'})
    return result,rejected


def top_counts(row, field, ties):
    rank = row['rank']
    counts, fractional = {}, {}
    for metric,q in CUTS.items():
        if metric=='winner':
            counts[metric] = row['n'] if rank==1 else 0
            continue
        k = math.floor(field*q + 1e-9)
        counts[metric] = (row['n'] if rank<=k else 0) if k else None
        fractional[metric] = row['n']*min(1,max(0,(k-rank+1)/ties[rank])) if k else None
    return counts,fractional


def economics(contest, support):
    matches=[r for r in support['saved_observations'] if r['contest_id']==contest['contest_id']]
    for observation in reversed(matches):
        row=observation.get('contest_json') or {};ladder=row.get('payout_ladder') or []
        fee=number(row.get('entry_fee'));paid=row.get('paid_places');pool=number(row.get('prize_pool'))
        if not fee or not paid or not pool or row.get('capacity')!=contest['field_size']:
            continue
        ranks={}
        for tier in ladder:
            cash=number(tier.get('cash'))
            if cash is None:break
            for rank in range(int(tier['from']),int(tier['to'])+1):ranks[rank]=cash
        if set(ranks)==set(range(1,int(paid)+1)) and abs(sum(ranks.values())-pool)<.01:
            return {'fee':fee,'payout_by_rank':ranks,'observation_id':observation.get('observation_id'),
                    'method':'tie-split reconstruction from exact-native contest cash economics'}
    return None


def tie_payout(rank, tie_size, ranks):
    return sum(ranks.get(i,0) for i in range(rank,rank+tie_size))/tie_size


def entry_groups(captain, players, starters):
    qb = captain['position']=='QB'
    groups = ['QB Captain' if qb else 'Non-QB Captain',f"CPT {captain['position']}"]
    qb_players = [r for r in players if r['position']=='QB']
    starter_ids = {r['id'] for r in starters}
    backup = any(r['id'] not in starter_ids for r in qb_players)
    if len(starter_ids)==2 and not backup:
        count = len(qb_players)
        groups.append({2:'Both QBs',1:'Exactly one QB',0:'Zero QB'}[count])
        groups.append(('QB Captain' if qb else 'Non-QB Captain')+' + '+{2:'both QBs',1:'one QB',0:'zero QB'}[count])
    return groups,backup


def analyze_contest(payload, support, pools, aliases, stats):
    c,entries = payload['contest'],payload['entries']
    field = sum(r['n'] for r in entries)
    key,pool,match_fraction = select_pool(c,entries,pools)
    resolve = build_resolver(key,pool,aliases)
    context = game_context(key,pool,support)
    starters,rejected = identify_starters(key,pool,resolve,context,support,stats)
    ties = Counter()
    econ=economics(c,support)
    for r in entries:
        if r['rank'] is not None:
            ties[r['rank']] += r['n']
    records,unknown,failures = [],[],Counter()
    for r in entries:
        parts = parse_lineup(r['lineup_text'])
        counts,fractional = top_counts(r,field,ties) if r['rank'] and 1<=r['rank']<=field else ({},{})
        if not parts or not counts:
            reason = 'missing_or_malformed_roster' if not parts else 'invalid_rank'
            failures[reason] += r['n'];unknown.append({**r,'reason':reason,'counts':counts});continue
        players = [resolve(slot,name) for slot,name in parts]
        if not all(players):
            reason = 'unresolved_identity'
            failures[reason] += r['n'];unknown.append({**r,'reason':reason,'counts':counts,
                'unresolved':[name for (_,name),p in zip(parts,players) if not p]});continue
        ids = [p['id'] for p in players]
        teams = Counter(p['team'] for p in players)
        if len(set(ids))!=6 or len(teams)!=2 or not key or set(teams)!=set(key[3]):
            failures['invalid_or_off_game_roster']+=r['n'];unknown.append({**r,'reason':'invalid_or_off_game_roster','counts':counts});continue
        salary = sum(p['salary'] for p in players) if all(p['salary'] is not None for p in players) else None
        if salary is not None and salary>50000:
            failures['over_salary_cap']+=r['n'];unknown.append({**r,'reason':'over_salary_cap','counts':counts});continue
        groups,backup = entry_groups(players[0],players,starters)
        signature = (ids[0],tuple(sorted(ids[1:])))
        captain_prior = prior_qb_stats(stats,ids[0],key[0],key[1]) if players[0]['position']=='QB' else None
        archetype = 'unknown'
        if captain_prior and captain_prior['carries'] is not None:
            carries=captain_prior['carries'];archetype='pocket' if carries<=1.67 else 'mobile' if carries<=3.33 else 'high_rush'
        records.append({**r,'counts':counts,'fractional':fractional,'groups':groups,'signature':signature,
            'players':players,'captain_position':players[0]['position'],'captain_team':players[0]['team'],
            'starter_eligible':len(starters)==2 and not backup,'other_qb_present':backup,
            'percentile':100*(r['rank']+(ties[r['rank']]-1)/2)/field,
            'team_split':'-'.join(map(str,sorted(teams.values(),reverse=True))),
            'captain_archetype':archetype,'salary':salary,
            'entry_fee':econ['fee'] if econ else None,
            'reconstructed_payout':tie_payout(r['rank'],ties[r['rank']],econ['payout_by_rank']) if econ else None,
            'tie_payout_reduction':econ['payout_by_rank'].get(r['rank'],0)-tie_payout(r['rank'],ties[r['rank']],econ['payout_by_rank']) if econ else None})
    duplicates = Counter()
    for r in records:
        duplicates[r['signature']]+=r['n']
    for r in records:
        r['duplicates']=duplicates[r['signature']]
    audit = {**c,'game_key':context['key'],'salary_pool_key':key,'salary_name_match_fraction':match_fraction,
        'kickoff':context['lock'].isoformat() if context['lock'] else None,
        'raw_salary_recovered':any(r.get('recovered_raw') for r in pool),
        'corrected_week':key[1] if key else None,'loaded_entries':field,
        'resolved_entries':sum(r['n'] for r in records),'unknown_entries':sum(r['n'] for r in unknown),
        'exclusions':dict(failures),'starters':starters,'starter_rejections':rejected,
        'starter_eligible_entries':sum(r['n'] for r in records if r['starter_eligible']),
        'nonstarter_qb_entries':sum(r['n'] for r in records if r['other_qb_present']) if len(starters)==2 else None,
        'first_place_tie_size':ties[1], 'unique_winning_rosters':len({r['signature'] for r in records if r['rank']==1}),
        'schedule':context['schedule']}
    audit['economic_reconstruction']={k:v for k,v in econ.items() if k!='payout_by_rank'} if econ else None
    return audit,records,unknown


def summarize(contest, records, group):
    family=GROUPS[group]
    population = [r for r in records if family in {'captain','position'} or r['starter_eligible']]
    rows = [r for r in population if group in r['groups']]
    n = sum(r['n'] for r in rows); base=sum(r['n'] for r in population)
    result={'contest_id':contest['contest_id'],'season':contest['season'],'game_key':contest['game_key'],
        'group':group,'cohort':family,'entries':n,'population_entries':base,'field_share':divide(n,base),
        'average_percentile':divide(sum(r['percentile']*r['n'] for r in rows),n),
        'median_percentile':weighted_median([(r['percentile'],r['n']) for r in rows]),
        'average_duplicates':divide(sum(r['duplicates']*r['n'] for r in rows),n),
        'median_duplicates':weighted_median([(r['duplicates'],r['n']) for r in rows]),
        'unique_entry_share':divide(sum(r['n'] for r in rows if r['duplicates']==1),n),
        'roi':None,'payout_impact':None,
        'economic_entries':sum(r['n'] for r in rows if r['entry_fee'] is not None),
        'reconstructed_fees':sum((r['entry_fee'] or 0)*r['n'] for r in rows),
        'reconstructed_payouts':sum((r['reconstructed_payout'] or 0)*r['n'] for r in rows),
        'tie_payout_reduction_total':sum((r['tie_payout_reduction'] or 0)*r['n'] for r in rows),
        'percentile_histogram':[(r['percentile'],r['n']) for r in rows],
        'duplicate_histogram':[(r['duplicates'],r['n']) for r in rows]}
    for metric in CUTS:
        supported=any(r['counts'][metric] is not None for r in population)
        y=sum(r['counts'][metric] or 0 for r in rows) if supported else None
        by=sum(r['counts'][metric] or 0 for r in population) if supported else None
        result.update({metric+'_count':y,metric+'_field_count':by,
            metric+'_rate':divide(y,n) if y is not None else None,
            metric+'_share':divide(y,by) if y is not None else None,
            metric+'_field_rate':divide(by,base) if by is not None else None,
            metric+'_lift':divide(divide(y,n),divide(by,base)) if y is not None and n and by else None})
        if metric in {'top10','top1'}:
            fy=sum(r['fractional'][metric] or 0 for r in rows) if supported else None
            fby=sum(r['fractional'][metric] or 0 for r in population) if supported else None
            result[metric+'_fractional_count']=fy;result[metric+'_fractional_field_count']=fby
            result[metric+'_fractional_lift']=divide(divide(fy,n),divide(fby,base)) if fy is not None and n and fby else None
    top=[r for r in rows if r['counts']['top10']]
    result['top10_duplicate_entry_rate']=divide(sum(r['n'] for r in top if r['duplicates']>1),sum(r['n'] for r in top))
    result['first_place_chop_size']=contest['first_place_tie_size'] if result['winner_count'] else None
    result['roi']=divide(result['reconstructed_payouts'],result['reconstructed_fees'])-1 if result['reconstructed_fees'] else None
    result['payout_impact']=divide(result['tie_payout_reduction_total'],result['economic_entries'])
    return result


def pooled(rows, group, season='pooled'):
    rows=[r for r in rows if r['group']==group and (season=='pooled' or r['season']==season)]
    n=sum(r['entries'] for r in rows);base=sum(r['population_entries'] for r in rows)
    result={'group':group,'season':season,'cohort':GROUPS[group], 'contests':len([r for r in rows if r['population_entries']]),
        'games':len({r['game_key'] for r in rows if r['population_entries']}),
        'entries':n,'population_entries':base,'field_share':divide(n,base),
        'average_percentile':divide(sum((r['average_percentile'] or 0)*r['entries'] for r in rows),n),
        'median_percentile':weighted_median([v for r in rows for v in r['percentile_histogram']]),
        'average_duplicates':divide(sum((r['average_duplicates'] or 0)*r['entries'] for r in rows),n),
        'median_duplicates':weighted_median([v for r in rows for v in r['duplicate_histogram']]),
        'unique_entry_share':divide(sum((r['unique_entry_share'] or 0)*r['entries'] for r in rows),n),
        'roi':None,'payout_impact':None,
        'economic_entries':sum(r['economic_entries'] for r in rows),
        'reconstructed_fees':sum(r['reconstructed_fees'] for r in rows),
        'reconstructed_payouts':sum(r['reconstructed_payouts'] for r in rows),
        'tie_payout_reduction_total':sum(r['tie_payout_reduction_total'] for r in rows)}
    for metric in CUTS:
        usable=[r for r in rows if r[metric+'_count'] is not None]
        gn=sum(r['entries'] for r in usable);bn=sum(r['population_entries'] for r in usable)
        y=sum(r[metric+'_count'] for r in usable);by=sum(r[metric+'_field_count'] for r in usable)
        result.update({metric+'_count':y if usable else None,metric+'_field_count':by if usable else None,
            metric+'_eligible_entries':gn, metric+'_eligible_contests':len(usable),
            metric+'_eligible_population_entries':bn,metric+'_eligible_field_share':divide(gn,bn),
            metric+'_rate':divide(y,gn),metric+'_share':divide(y,by),
            metric+'_field_rate':divide(by,bn),metric+'_lift':divide(divide(y,gn),divide(by,bn)) if gn and by else None})
        result[metric+'_share_index_vs_all_field']=divide(result[metric+'_share'],result['field_share']) if result['field_share'] else None
        if metric in {'top10','top1'}:
            fy=sum(r[metric+'_fractional_count'] for r in usable);fby=sum(r[metric+'_fractional_field_count'] for r in usable)
            result[metric+'_fractional_lift']=divide(divide(fy,gn),divide(fby,bn)) if gn and fby else None
    result['top10_duplicate_entry_rate']=divide(sum((r['top10_duplicate_entry_rate'] or 0)*(r['top10_count'] or 0) for r in rows),result['top10_count'])
    result['first_place_chop_median']=weighted_median([(r['first_place_chop_size'],r['winner_count']) for r in rows if r['winner_count']])
    result['roi']=divide(result['reconstructed_payouts'],result['reconstructed_fees'])-1 if result['reconstructed_fees'] else None
    result['payout_impact']=divide(result['tie_payout_reduction_total'],result['economic_entries'])
    return result


def interval(values):
    finite=np.asarray([v for v in values if v is not None and math.isfinite(v)])
    return [float(v) for v in np.quantile(finite,[.025,.975])] if len(finite) else None


def contest_weighted(rows, group, rng, draws):
    usable=[r for r in rows if r['group']==group and r['entries']>0 and r['top10_lift'] is not None]
    lifts=[r['top10_lift'] for r in usable]
    games=sorted({r['game_key'] for r in usable});boot=[]
    draws=rng.choice(games,size=(len(draws),len(games))) if games else []
    for draw in draws:
        sampled=[r for g in draw for r in usable if r['game_key']==g]
        if sampled:boot.append(float(np.mean([r['top10_lift'] for r in sampled])))
    return {'group':group,'contests':len(usable),'games':len(games),'entries':sum(r['entries'] for r in usable),
        'mean_field_share':float(np.mean([r['field_share'] for r in usable])) if usable else None,
        'mean_top10_rate':float(np.mean([r['top10_rate'] for r in usable])) if usable else None,
        'mean_top10_lift':float(np.mean(lifts)) if lifts else None,
        'median_top10_lift':float(np.median(lifts)) if lifts else None,
        'top10_lift_iqr':[float(v) for v in np.quantile(lifts,[.25,.75])] if lifts else None,
        'contests_outperforming':sum(v>1+1e-12 for v in lifts),
        'contests_outperforming_share':divide(sum(v>1+1e-12 for v in lifts),len(lifts)),
        'mean_top10_lift_game_bootstrap_95':interval(boot),
        'mean_top1_lift':float(np.mean([r['top1_lift'] for r in usable if r['top1_lift'] is not None])) if any(r['top1_lift'] is not None for r in usable) else None}


def odds(y,n,z,m):
    a,b,c,d=y,n-y,z,m-z
    return divide(a*d,b*c) if n and m else None


def comparison(rows,a,b,metric,draws):
    ar={r['contest_id']:r for r in rows if r['group']==a and r['entries'] and r[metric+'_rate'] is not None}
    br={r['contest_id']:r for r in rows if r['group']==b and r['entries'] and r[metric+'_rate'] is not None}
    pairs=[(ar[k],br[k]) for k in sorted(ar.keys() & br.keys())]
    def calculate(sample):
        an=sum(x['entries'] for x,y in sample);bn=sum(y['entries'] for x,y in sample)
        ay=sum(x[metric+'_count'] for x,y in sample);by=sum(y[metric+'_count'] for x,y in sample)
        if not an or not bn:return None
        return ay/an-by/bn,divide(ay/an,by/bn),odds(ay,an,by,bn)
    result=calculate(pairs)
    if result is None:return {'a':a,'b':b,'metric':metric,'status':'unavailable'}
    grouped=defaultdict(list)
    for pair in pairs:grouped[pair[0]['game_key']].append(pair)
    rng=np.random.default_rng(20261005)
    draws=rng.choice(sorted(grouped),size=(len(draws),len(grouped)))
    boot=[];cwboot=[]
    for draw in draws:
        sample=[p for g in draw for p in grouped.get(g,[])]
        value=calculate(sample)
        if value:boot.append(value)
        if sample:cwboot.append(float(np.mean([x[metric+'_rate']-y[metric+'_rate'] for x,y in sample])))
    game_diffs=[float(np.mean([x[metric+'_rate']-y[metric+'_rate'] for x,y in grouped[g]])) for g in sorted(grouped)]
    # Exact paired sign-flip diagnostic, at the game level, not millions of entries.
    pvalue=None
    if 2<=len(game_diffs)<=18:
        observed=abs(sum(game_diffs))
        signs=np.array(list(itertools.product((-1,1),repeat=len(game_diffs))))
        pvalue=float(np.mean(np.abs(signs@np.asarray(game_diffs))>=observed-1e-12))
    return {'a':a,'b':b,'metric':metric,'status':'exploratory_few_independent_games',
        'paired_contests':len(pairs),'paired_games':len(grouped),
        'a_entries':sum(x['entries'] for x,y in pairs),'b_entries':sum(y['entries'] for x,y in pairs),
        'a_success_rate':divide(sum(x[metric+'_count'] for x,y in pairs),sum(x['entries'] for x,y in pairs)),
        'b_success_rate':divide(sum(y[metric+'_count'] for x,y in pairs),sum(y['entries'] for x,y in pairs)),
        'absolute_difference':result[0],'relative_rate':result[1],'odds_ratio':result[2],
        'absolute_difference_game_bootstrap_95':interval([v[0] for v in boot]),
        'relative_rate_game_bootstrap_95':interval([v[1] for v in boot]),
        'odds_ratio_game_bootstrap_95':interval([v[2] for v in boot]),
        'contest_weighted_difference':float(np.mean([x[metric+'_rate']-y[metric+'_rate'] for x,y in pairs])),
        'contest_weighted_difference_game_bootstrap_95':interval(cwboot),
        'game_mean_paired_difference':float(np.mean(game_diffs)),
        'game_sign_flip_p':pvalue,'bootstrap_valid_draws':len(boot)}


def write_csv(path,rows):
    if not rows:
        path.write_text('status\nunavailable\n');return
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for row in rows:
            writer.writerow({k:json.dumps(v,sort_keys=True) if isinstance(v,(list,dict,tuple)) else v for k,v in row.items()})


def missing_bounds(contest,records,unknown,group):
    family=GROUPS[group]
    if family in {'starter','combination'} and len(contest['starters'])!=2:
        return None
    selected=[r for r in records if group in r['groups']]
    n=sum(r['n'] for r in selected);u=sum(r['n'] for r in unknown)
    N=contest['loaded_entries']
    result={'contest_id':contest['contest_id'],'game_key':contest['game_key'],'season':contest['season'],
            'group':group,'known_group_entries':n,'unknown_rosters':u,'full_entries':N,
            'all_entry_usage_lower':divide(n,N),'all_entry_usage_upper':divide(n+u,N)}
    for metric in ('top10','top1','winner'):
        y=sum(r['counts'][metric] or 0 for r in selected)
        uy=sum(r.get('counts',{}).get(metric) or 0 for r in unknown)
        full_y=sum(r['counts'][metric] or 0 for r in records)+uy
        result.update({metric+'_known_success':y,metric+'_unknown_success':uy,metric+'_full_success':full_y,
            metric+'_rate_lower':divide(y,n+u-uy),metric+'_rate_upper':divide(y+uy,n+uy),
            metric+'_success_share_lower':divide(y,full_y),metric+'_success_share_upper':divide(y+uy,full_y)})
    return result


def rate_intervals(rows,group,rng,draws):
    usable=[r for r in rows if r['group']==group and r['population_entries']]
    games=sorted({r['game_key'] for r in usable});result={'group':group,'games':len(games)}
    choices=rng.choice(games,size=(draws,len(games))) if games else []
    for metric in ('top10','top1','winner'):
        rates=[];lifts=[]
        for choice in choices:
            sample=[r for g in choice for r in usable if r['game_key']==g and r[metric+'_count'] is not None]
            n=sum(r['entries'] for r in sample);N=sum(r['population_entries'] for r in sample)
            y=sum(r[metric+'_count'] for r in sample);Y=sum(r[metric+'_field_count'] for r in sample)
            rates.append(divide(y,n));lifts.append(divide(divide(y,n),divide(Y,N)) if n and Y else None)
        result[metric+'_rate_game_bootstrap_95']=interval(rates)
        result[metric+'_lift_game_bootstrap_95']=interval(lifts)
    return result


def market_archive(support,path):
    if path.exists():return json.loads(path.read_text())
    result=[]
    for s in support['snapshots']:
        if s['dataset'] not in {'schedule_market_line','schedule_market_snapshot'}:continue
        source=Path(s['artifact_path'])
        if not source.exists():continue
        actual=hashlib.sha256(source.read_bytes()).hexdigest()
        if actual!=s['content_sha256']:continue
        rows=list(csv.DictReader(source.open()))
        result.append({'metadata':s,'rows':rows,'verified_sha256':actual})
    path.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    return result


def pregame_market(contest,archives):
    if not contest['kickoff'] or not contest['salary_pool_key']:return None
    key=contest['salary_pool_key'];matches=[]
    for source in archives:
        s=source['metadata'];clocks=[timestamp(s['observed_at']),timestamp(s['captured_at'])]
        if any(d is None or d>=timestamp(contest['kickoff']) for d in clocks):continue
        for r in source['rows']:
            if number(r.get('season'))!=key[0] or number(r.get('week'))!=key[1]:continue
            home=team(r.get('home_team'));away=team(r.get('away_team'))
            if tuple(sorted((home,away)))!=tuple(key[3]):continue
            total=number(r.get('total_line',r.get('game_total')))
            margin=number(r.get('spread_line'));hspread=number(r.get('home_spread'))
            if margin is None and hspread is not None:margin=-hspread
            if total is not None and margin is not None:
                matches.append((max(clocks),{'total_line':total,'spread_line':margin,
                    'home_team':home,'away_team':away,'source_snapshot_id':s['snapshot_id'],
                    'observed_at':s['observed_at'],'captured_at':s['captured_at']}))
    return max(matches,key=lambda x:x[0])[1] if matches else None


def exploratory_tables(contest,audit_rows):
    market=contest.get('schedule') or {}
    # Schedule market values are retrospective audit-only unless immutable prelock
    # market sources prove historical availability. Never use these to select starters.
    total=number(market.get('total_line'));spread=number(market.get('spread_line'))
    tables=[]
    for dimension in ('team_split','captain_archetype','game_total_audit','spread_audit','favorite_captain_audit',
                      'winning_team_captain_audit','captain_qb_salary','combined_starting_qb_salary'):
        buckets=defaultdict(list)
        for r in audit_rows:
            if dimension=='team_split':value=r['team_split']
            elif dimension=='captain_archetype':
                if r['captain_position']!='QB':continue
                value=r['captain_archetype']
            elif dimension=='game_total_audit':value='unknown' if total is None else '<43' if total<43 else '43-49' if total<=49 else '>49'
            elif dimension=='spread_audit':value='unknown' if spread is None else 'close <=3' if abs(spread)<=3 else 'moderate 3-7' if abs(spread)<=7 else 'large >7'
            elif dimension=='favorite_captain_audit':
                if r['captain_position']!='QB':continue
                value='unknown' if spread is None else 'pickem' if spread==0 else 'favorite' if r['captain_team']==team(market.get('home_team') if spread>0 else market.get('away_team')) else 'underdog'
            elif dimension=='winning_team_captain_audit':
                if r['captain_position']!='QB':continue
                hs,aws=number(market.get('home_score')),number(market.get('away_score'))
                value='unknown' if hs is None or aws is None else 'tied_game' if hs==aws else 'winning_team' if r['captain_team']==team(market.get('home_team') if hs>aws else market.get('away_team')) else 'losing_team'
            elif dimension=='captain_qb_salary':
                if r['captain_position']!='QB':continue
                s=r['players'][0]['flex_salary'];value='unknown' if s is None else '<9000' if s<9000 else '9000-10400' if s<10500 else '>=10500'
            else:
                starters=contest['starters']
                s=sum(p['flex_salary'] for p in starters) if len(starters)==2 and all(p['flex_salary'] is not None for p in starters) else None
                value='unknown' if s is None else '<38%' if s/50000<.38 else '38-42%' if s/50000<=.42 else '>42%'
            buckets[value].append(r)
        for bucket,rows in buckets.items():
            for group in ('QB Captain','Non-QB Captain','Both QBs','Exactly one QB','Zero QB','QB Captain + both QBs'):
                s=summarize(contest,rows,group)
                if not s['entries']:continue
                tables.append(s | {
                    'dimension':dimension,'bucket':bucket,'evidence':'exploratory',
                    'covariate_time_safety':'retrospective_audit_only' if dimension.endswith('_audit') else 'prior_game_or_salary_identity',
                    'baseline':'same stratum eligible field'})
    return tables


def optimizer_audit(support):
    result=[];runs=defaultdict(list);candidates=[];seen_reports=set()
    canonical_positions=defaultdict(set)
    for r in support['salaries']:
        if r.get('player_master_id'):canonical_positions[r['player_master_id']].add(r['position'])
    position={k:next(iter(v)) for k,v in canonical_positions.items() if len(v)==1}
    for l in support['optimizer_lineups']:
        players=l['players'];captain=next((p for p in players if p['roster_position']=='CPT'),None)
        if not captain or len(players)!=6:continue
        raw=captain['player_json'];qbs=[p for p in players if p['player_json'].get('position')=='QB']
        qc=raw.get('position')=='QB';group=('QB Captain' if qc else 'Non-QB Captain')+' + '+{0:'zero QB',1:'one QB',2:'both QBs'}.get(len(qbs),'other QBs')
        first=players[0]['player_json'];corr=first.get('lineup_correlation_summary') or {}
        prior=float(raw.get('captain_objective_multiplier') or 1);cscore=float(raw.get('objective_score') or 0)
        ledger={}
        for r in corr.get('triggered_rules',[]):
            ledger[r['rule_id']]=ledger.get(r['rule_id'],0)+float(r.get('objective_contribution') or 0)
        row={'optimizer_run_id':l['optimizer_run_id'],'lineup_id':l['lineup_id'],'season':l['season'],
            'week':l['week'],'slate':l['slate_id'],'strategy':l['strategy'],'group':group,
            'qb_count_position_audit':len(qbs),'qb_captain':qc,'captain_name':raw.get('name'),
            'captain_multiplier':prior,'captain_prior_score_contribution':cscore*(1-1/prior),
            'correlation_contribution':corr.get('total_adjustment'),
            'rule_contributions':ledger,'objective_score':l['objective_score'],
            'roster_signature':str((captain['player_id'],tuple(sorted(p['player_id'] for p in players)))),
            'created_at':l['created_at']}
        result.append(row);runs[l['optimizer_run_id']].append(row)
        report=first.get('captain_family_coverage_report') or raw.get('captain_family_coverage_report')
        if not report or l['optimizer_run_id'] in seen_reports:continue
        seen_reports.add(l['optimizer_run_id'])
        # Re-rank only the saved quality-eligible candidate set. No re-solve, no
        # exposure-feasibility claim. Positions keyed by native/canonical roster IDs.
        position.update({p['player_id']:p['player_json'].get('position') for ll in support['optimizer_lineups']
                  if (ll['season'],ll['week'],ll['slate_id'])==(l['season'],l['week'],l['slate_id']) for p in ll['players']}
        )
        metrics=report.get('ranked_metrics') or []
        legal=[r for r in metrics if r.get('quality_eligible')]
        if not legal:continue
        def classify(r):
            ids=[p.get('player_id') for p in r.get('players',[])]
            if len(ids)!=6 or any(not position.get(i) for i in ids):return 'unknown'
            cq=position.get(r['captain_player_id'])=='QB';n=sum(position[i]=='QB' for i in ids)
            return ('QB CPT' if cq else 'non-QB CPT')+f' / {n} QB'
        baseline=max(legal,key=lambda r:r.get('selector') or -math.inf)
        for adjustment in ('correlation','captain_position_prior_contribution','both'):
            def score(r):
                return float(r.get('selector') or 0)-sum(float(r.get(k) or 0) for k in
                    (('correlation','captain_position_prior_contribution') if adjustment=='both' else (adjustment,)))
            alternative=max(legal,key=score)
            candidates.append({'optimizer_run_id':l['optimizer_run_id'],'season':l['season'],'week':l['week'],
                'slate':l['slate_id'],'adjustment_removed':adjustment,'quality_eligible_candidates':len(legal),
                'original_rank':baseline.get('rank'),'alternative_original_rank':alternative.get('rank'),
                'original_construction':classify(baseline),'alternative_construction':classify(alternative),
                'rank_changed':baseline.get('rank')!=alternative.get('rank'),
                'comparison_scope':'fixed saved candidates; individual rank only; no portfolio reoptimization'})
    run_summary=[{'optimizer_run_id':key,'season':rows[0]['season'],'week':rows[0]['week'],'slate':rows[0]['slate'],
        'strategy':rows[0]['strategy'],'saved_lineups':len(rows),'qb_captain_share':sum(r['qb_captain'] for r in rows)/len(rows),
        'two_qb_position_share':sum(r['qb_count_position_audit']==2 for r in rows)/len(rows),
        'qb_captain_two_qb_share':sum(r['qb_captain'] and r['qb_count_position_audit']==2 for r in rows)/len(rows)} for key,rows in runs.items()]
    return result,run_summary,candidates


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',type=Path,default=OUT/'inputs');p.add_argument('--output',type=Path,default=OUT);p.add_argument('--bootstrap',type=int,default=4000)
    args=p.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((args.inputs/'manifest.json').read_text())
    for name,expected in manifest['hashes'].items():
        if hashlib.sha256((args.inputs/name).read_bytes()).hexdigest()!=expected:raise ValueError('Input hash mismatch: '+name)
    support=json.loads((args.inputs/'support.json').read_text());recovered=json.loads((args.inputs/'recovered_salary.json').read_text())
    aliases=defaultdict(list)
    for r in recovered['aliases']:aliases[str(r['source_key'])].append(r)
    raw=recovered['raw_salaries']+json.loads((args.inputs/'raw_historical_salaries.json').read_text())
    salaries=support['salaries']+[raw_to_salary(r,aliases) for r in raw]
    pools=salary_pools(salaries);stats=recovered['qb_stats'];audits=[];summaries=[];unknown_rows=[];strata=[];bounds=[]
    archives=market_archive(support,args.inputs/'market_archive_snapshot.json')
    supplements={name:hashlib.sha256((args.inputs/name).read_bytes()).hexdigest()
                 for name in ('recovered_salary.json','raw_historical_salaries.json','market_archive_snapshot.json')}
    supplement_path=args.inputs/'supplement_hashes.json'
    if supplement_path.exists():
        if json.loads(supplement_path.read_text())!=supplements:raise ValueError('Supplemental research input hash mismatch')
    else:supplement_path.write_text(json.dumps(supplements,indent=2,sort_keys=True)+'\n')
    for path in sorted(args.inputs.glob('*.json.gz')):
        audit,records,unknown=analyze_contest(json.load(gzip.open(path,'rt')),support,pools,recovered['aliases'],stats)
        audits.append(audit)
        for group in GROUPS:summaries.append(summarize(audit,records,group))
        for group in GROUPS:
            bound=missing_bounds(audit,records,unknown,group)
            if bound:bounds.append(bound)
        unknown_rows += [{'contest_id':audit['contest_id'],**r} for r in unknown]
        strata+=exploratory_tables(audit,records)
        audit['pregame_market']=pregame_market(audit,archives)
        if audit['pregame_market']:
            pre=exploratory_tables({**audit,'schedule':audit['pregame_market']},records)
            for row in pre:
                if row['dimension'] not in {'game_total_audit','spread_audit','favorite_captain_audit'}:continue
                row['dimension']=row['dimension'].replace('_audit','_pregame')
                row['covariate_time_safety']='hash_verified_observed_and_captured_before_lock'
                strata.append(row)
        print(audit['season'],audit['week'],audit['slate_id'],audit['resolved_entries'],audit['exclusions'],len(audit['starters']),flush=True)
    rng=np.random.default_rng(20261005);games=sorted({r['game_key'] for r in summaries if r['population_entries'] and r['game_key']})
    draws=rng.choice(games,size=(args.bootstrap,len(games)))
    pooled_rows=[pooled(summaries,g,s) for s in ('pooled',2024,2025,2026) for g in GROUPS]
    cw=[contest_weighted(summaries,g,rng,draws) for g in GROUPS]
    rate_cis=[rate_intervals(summaries,g,rng,args.bootstrap) for g in GROUPS]
    sensitivity=[]
    strict_ids={r['contest_id'] for r in audits if len(r['starters'])==2 and all(p['method'].startswith('archived_pregame') for p in r['starters'])}
    for name,rows in [('archived_starters_only',[r for r in summaries if r['contest_id'] in strict_ids]),
                      ('fields_at_least_1000',[r for r in summaries if next(a['field_size'] for a in audits if a['contest_id']==r['contest_id'])>=1000])]:
        for group in GROUPS:sensitivity.append(pooled(rows,group)|{'sensitivity':name})
    for game in games:
        for group in ('QB Captain','Both QBs','QB Captain + both QBs'):
            sensitivity.append(pooled([r for r in summaries if r['game_key']!=game],group)|{'sensitivity':'leave_one_game_out','omitted_game':game})
    stratum_summary=[]
    for dimension,bucket in sorted({(r['dimension'],r['bucket']) for r in strata}):
        selected=[r for r in strata if (r['dimension'],r['bucket'])==(dimension,bucket)]
        for group in GROUPS:
            if any(r['group']==group for r in selected):
                stratum_summary.append(pooled(selected,group)|{'dimension':dimension,'bucket':bucket,'evidence':'exploratory'})
    contrasts=[('QB Captain','Non-QB Captain'),('Both QBs','Exactly one QB'),('Both QBs','Zero QB'),
        ('QB Captain + both QBs','QB Captain + one QB'),('QB Captain + both QBs','Non-QB Captain + both QBs'),
        ('QB Captain + both QBs','Non-QB Captain + one QB'),('QB Captain + both QBs','Non-QB Captain + zero QB')]
    comparisons=[comparison(summaries,a,b,m,draws) for m in ('top10','top1') for a,b in contrasts]
    valid=sorted((r for r in comparisons if r.get('game_sign_flip_p') is not None),key=lambda r:r['game_sign_flip_p']);prior=0
    for i,r in enumerate(valid):
        prior=max(prior,min(1,r['game_sign_flip_p']*(len(valid)-i)));r['holm_adjusted_p']=prior
    opt,run_summaries,re_rank=optimizer_audit(support)
    clean_summaries=[{k:v for k,v in r.items() if not k.endswith('_histogram')} for r in summaries]
    result={'method':{'seed':20261005,'bootstrap_draws':args.bootstrap,'cluster':'salary-dated NFL game; all contests in a game sampled together',
        'top_cutoff':'floor(full field * q); competition-rank ties included; unavailable if cutoff < 1',
        'finish_percentile':'full-field tie midrank / full-field entries * 100; lower is better',
        'cohorts':'captain/position: complete resolved legal rosters; starter/combination: additionally two expected starters identified and no other QB',
        'primary_starter_policy':'archived before lock or reconstructed salary/prior-volume, explicitly distinguished',
        'pvalues':'exact game-level paired sign-flip diagnostic; Holm across all available major top10/top1 contrasts; associations, not causal'},
        'inventory':{'all_contests':len(support['contests']),'showdown_files':len(audits),'loaded_entries':sum(r['loaded_entries'] for r in audits),
            'resolved_entries':sum(r['resolved_entries'] for r in audits),'games':len(games),
            'starter_eligible_entries':sum(r['starter_eligible_entries'] for r in audits),'starter_eligible_contests':sum(r['starter_eligible_entries']>0 for r in audits)},
        'entry_weighted':pooled_rows,'contest_weighted':cw,'comparisons':comparisons,'contest_audits':audits,
        'rate_confidence_intervals':rate_cis,'sensitivities':sensitivity,
        'optimizer_summary':{'saved_runs':len(run_summaries),'saved_lineups':len(opt),'candidate_rerank_runs':len({r['optimizer_run_id'] for r in re_rank}),
            'qb_captain_share':divide(sum(r['qb_captain'] for r in opt),len(opt)),
            'two_qb_position_share':divide(sum(r['qb_count_position_audit']==2 for r in opt),len(opt)),
            'qb_captain_two_qb_share':divide(sum(r['qb_captain'] and r['qb_count_position_audit']==2 for r in opt),len(opt))},
        'source_manifest':manifest,'analysis_input_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(args.inputs.iterdir()) if p.is_file()},
        'unavailable':{'roi':'No normalized historical payout tiers; reconstruction only on exact-native contests with verified cash ladder/fees',
            'expected_duplication_payout_impact':'Observed duplication and chops are not an ex ante payout model',
            '2024_standings':'No stored historical contest standings in 2024',
            'market_time_safety':'Schedule closing lines treated as retrospective audit-only; not verified pregame market archives'}}
    (out/'analysis.json').write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
    for name,rows in [('summary',pooled_rows),('contest_weighted',cw),('comparisons',comparisons),('rate_confidence_intervals',rate_cis),('sensitivities',sensitivity),('missing_roster_bounds',bounds),('contest_metrics',clean_summaries),
                      ('contest_inventory',audits),('unresolved_rosters',unknown_rows),('exploratory',[{k:v for k,v in r.items() if not k.endswith('_histogram')} for r in strata]),('exploratory_summary',stratum_summary),
                      ('optimizer_lineups',opt),('optimizer_runs',run_summaries),('optimizer_candidate_rerank',re_rank)]:write_csv(out/(name+'.csv'),rows)
    print(json.dumps(result['inventory']));print(json.dumps(result['optimizer_summary']))


if __name__=='__main__':main()
