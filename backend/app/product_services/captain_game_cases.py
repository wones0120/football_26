"""Reusable, market-first shared scoring cases. Conditional stress cases, not win odds.

No incumbent point forecast, ownership, display name join, player-specific rule or
live default is consumed. Full possession/clock simulation remains out of scope.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import math

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sqlalchemy import text

from .evaluation_record import digest
from .market_snapshots import canonical_team

VERSION = 'captain_shared_scoring_cases_v6'
SEED = 17
# Named stress coordinates, not frequencies or calibrated probabilities.
COORDINATES = [('central', 0, 0), ('lower_total', -3, -3),
               ('higher_total', 3, 3), ('home_ahead', 3, -3), ('away_ahead', -3, 3)]
DRAWS_PER_COORDINATE = 4
UNKNOWN = '__unallocated__'
FIELDS = {'pass_attempts': ('attempts','passing_attempts'), 'rush_attempts': ('carries','rushing_attempts'),
          'rushing_yards': ('rushing_yards',), 'passing_yards': ('passing_yards',), 'completions': ('completions','passing_completions'), 'targets': ('targets',), 'receptions': ('receptions',), 'passing_tds': ('passing_tds',),
          'rushing_tds': ('rushing_tds',), 'receiving_tds': ('receiving_tds',),
          'fg_made': ('fg_made',), 'fg_att': ('fg_att',), 'pat_made': ('pat_made',), 'pat_att': ('pat_att',),
          **{k:(k,) for k in ['fg_made_0_19','fg_made_20_29','fg_made_30_39','fg_made_40_49','fg_made_50_59','fg_made_60_']}}


def known(raw, aliases, *, signed=False):
    value=next((raw[k] for k in aliases if raw.get(k) is not None),None)
    if isinstance(value,bool):return None
    try:
        return float(value) if math.isfinite(float(value)) and (signed or float(value)>=0) else None
    except (TypeError,ValueError):return None


def load_history(engine, *, season, week, cutoff):
    with engine.connect() as connection:
        rows=connection.execute(text('''WITH aliases AS (
          SELECT source_key,MIN(player_master_id::text) AS pid FROM public.player_alias
          WHERE source_system='nflreadpy' GROUP BY source_key HAVING COUNT(DISTINCT player_master_id)=1)
          SELECT DISTINCT ON (r.player_id,r.season,r.week) a.pid,r.player_id,r.season,r.week,r.team,r.position,
            r.raw_row_json,r.raw_nfl_weekly_stat_id AS source_id,r.created_at
          FROM public.raw_nfl_weekly_stat r LEFT JOIN aliases a ON a.source_key=r.player_id
          WHERE r.season BETWEEN :start AND :season AND (r.season<:season OR r.week<:week)
            AND r.week<=18 AND r.created_at<=:cutoff AND r.raw_row_json->>'season_type'='REG'
            AND r.position IN ('QB','RB','FB','WR','TE','K')
          ORDER BY r.player_id,r.season,r.week,r.created_at DESC,r.raw_nfl_weekly_stat_id DESC'''),
          dict(start=season-3,season=season,week=week,cutoff=cutoff)).mappings().all()
    return [dict(player_master_id=r['pid'],source_player_id=r['player_id'],team=canonical_team(r['team']),
        opponent=canonical_team((r['raw_row_json'] or {}).get('opponent_team')),
        position='RB' if r['position']=='FB' else r['position'],period=r['season']*100+r['week'],
        source_id=int(r['source_id']),imported_at=r['created_at'].isoformat(),
        **{key:known(r['raw_row_json'] or {},aliases,signed=key.endswith('_yards')) for key,aliases in FIELDS.items()}) for r in rows]


def checked_history(records, *, before_period, cutoff):
    records=deepcopy(records)
    decision=pd.to_datetime(cutoff,utc=True)
    for row in records:
        clock=pd.to_datetime(row['imported_at'],utc=True,errors='coerce')
        if pd.isna(clock) or row['period']>=before_period or clock>decision:
            raise ValueError('Scenario roles contain future period/import evidence')
    keys=[(r['source_player_id'],r['period']) for r in records]
    canonical=[(r['player_master_id'],r['period']) for r in records if r['player_master_id']]
    if len(set(keys))!=len(keys) or len(set(canonical))!=len(canonical):
        raise ValueError('Duplicate native/canonical scenario history')
    return sorted(records,key=lambda r:(r['period'],r['source_player_id']))


def team_history(records):
    groups={}
    for row in records:groups.setdefault((row['period'],row['team']),[]).append(row)
    result=[];excluded=[]
    for (period,team),rows in sorted(groups.items()):
        offense=[r for r in rows if r['position']!='K'];kickers=[r for r in rows if r['position']=='K']
        needed=['pass_attempts','rush_attempts','passing_tds','rushing_tds','receiving_tds']
        if not offense or not kickers or any(r[k] is None for r in offense for k in needed) or any(r[k] is None for r in kickers for k in ['fg_made','pat_made']):
            excluded.append(dict(period=period,team=team,reason='missing full-source offensive/kicking components'));continue
        passing=sum(r['passing_tds'] for r in offense);receiving=sum(r['receiving_tds'] for r in offense)
        if passing!=receiving:
            excluded.append(dict(period=period,team=team,reason='historical passing/receiving TD mismatch'));continue
        opponents={r['opponent'] for r in rows if r.get('opponent')}
        if len(opponents)!=1:
            excluded.append(dict(period=period,team=team,reason='unknown/ambiguous historical opponent'));continue
        rushing=sum(r['rushing_tds'] for r in offense);fg=sum(r['fg_made'] for r in kickers)
        pats=sum(r['pat_made'] for r in kickers)
        result.append(dict(period=period,team=team,opponent=next(iter(opponents)),pass_tds=passing,rush_tds=rushing,
            fg_made=fg,pat_made=pats,points=6*(passing+rushing)+3*fg+pats,
            pass_attempts=sum(r['pass_attempts'] for r in offense),rush_attempts=sum(r['rush_attempts'] for r in offense),
            source_ids=[r['source_id'] for r in rows],
            **{k:sum(r[k] for r in offense) if all(r.get(k) is not None for r in offense) else None for k in ('completions','passing_yards')}))
    return result,excluded


def volume_response(games):
    by={(r['period'],r['team']):r for r in games};pairs=[(r,by.get((r['period'],r['opponent']))) for r in games]
    pairs=[(r,o) for r,o in pairs if o]
    if len(pairs)<100:raise ValueError('Scenario volume response requires 100 complete prior paired team games')
    x=np.array([[r['points'],o['points']] for r,o in pairs]);y=np.array([[r['pass_attempts'],r['rush_attempts']] for r,o in pairs])
    scaler=StandardScaler().fit(x);model=Ridge(alpha=30.).fit(scaler.transform(x),y)
    # Conditional association is a declared sensitivity, not a causal game law.
    slopes=model.coef_/scaler.scale_
    return dict(method='prior_paired_offensive_score_association_standardized_ridge_alpha30',
        rows=len(pairs),training_max_period=max(r['period'] for r,o in pairs),slopes=slopes.tolist(),
        source_sha256=digest(pairs),interpretation='Conditional score sensitivity around published learned count anchor; no causal or calibrated joint law.')


class Roles:
    def __init__(self, records, before_period):
        self.records=records;self.before=before_period;self.cache={}

    def rate(self, actor, numerator, denominator, prior_size=20.):
        key=(actor['player_master_id'],actor['team'],actor['position'],numerator,denominator)
        if key in self.cache:return self.cache[key]
        same=[r for r in self.records if r['player_master_id']==actor['player_master_id'] and r['team']==actor['team']
              and r['position']==actor['position'] and r['period']//100==self.before//100][-8:]
        peers=[r for r in self.records if r['position']==actor['position'] and r.get(numerator) is not None
               and r.get(denominator) is not None and r[denominator]>0]
        observed=[r for r in same if r.get(numerator) is not None and r.get(denominator) is not None and r[denominator]>0]
        if len(peers)<10 or sum(r[denominator] for r in peers)<=0:
            self.cache[key]=None;return None
        reference=sum(r[numerator] for r in peers)/sum(r[denominator] for r in peers)
        value=(sum(r[numerator] for r in observed)+prior_size*reference)/(sum(r[denominator] for r in observed)+prior_size)
        result=dict(value=value,player_rows=len(observed),player_opportunities=sum(r[denominator] for r in observed),
            numerator=sum(r[numerator] for r in observed),prior_opportunities=prior_size,reference_rate=reference,
            source_ids=[r['source_id'] for r in observed],peer_rows=len(peers),
            peer_sha256=digest([(r['source_id'],r[numerator],r[denominator]) for r in peers]))
        self.cache[key]=result;return result


def partition(total, weights):
    """Deterministic integer budget with explicit residual, never donation to salary actors."""
    if total<0 or any(not math.isfinite(v) or v<0 for v in weights.values()):raise ValueError('Invalid scenario allocation')
    if sum(weights.values())<=0:return {**dict.fromkeys(weights,0),UNKNOWN:total}
    raw={k:total*v/sum(weights.values()) for k,v in weights.items()};result={k:int(math.floor(v)) for k,v in raw.items()}
    for k in sorted(raw,key=lambda k:(-(raw[k]-result[k]),k))[:total-sum(result.values())]:result[k]+=1
    return result


def draw_one(rng, weights, capacities):
    ids=sorted(k for k,v in weights.items() if v>0 and capacities.get(k,0)>0)
    if not ids:raise ValueError('Scoring event exceeds supported opportunity capacity')
    values=np.array([weights[k] for k in ids],dtype=float);return str(rng.choice(ids,p=values/values.sum()))


def composition(target, recent, draw_index):
    # Match the scoring environment before drawing TD/FG composition. Scaling
    # a low-scoring all-FG game creates unsupported7–10 FG extrapolations.
    # Use actual same-team prior compositions inside the declared score band;
    # no component count is scaled, clipped or fabricated to hit the market.
    distance=min(abs(7*(r['pass_tds']+r['rush_tds'])+3*r['fg_made']-target) for r in recent)
    if distance>3:raise ValueError('No source-supported same-team scoring profile within one field goal of target')
    local=[r for r in recent if abs(7*(r['pass_tds']+r['rush_tds'])+3*r['fg_made']-target)<=3]
    profiles=sorted(local,key=lambda r:(7*(r['pass_tds']+r['rush_tds'])/max(1.,7*(r['pass_tds']+r['rush_tds'])+3*r['fg_made']),r['period']))
    profile=profiles[round((draw_index%DRAWS_PER_COORDINATE)*(len(profiles)-1)/(DRAWS_PER_COORDINATE-1))]
    return int(profile['pass_tds']+profile['rush_tds']),int(profile['fg_made']),profile['source_ids']



FG_DISTANCE_POINTS = {'fg_made_0_19':3,'fg_made_20_29':3,'fg_made_30_39':3,
                      'fg_made_40_49':4,'fg_made_50_59':5,'fg_made_60_':5}


def kicking_profile(records, source_ids):
    """Keep made counts, distances and misses in one complete source game.

    A conditional team scoring profile does not license independent long-kick
    draws from unrelated games. This replays an observed outcome mix; it is not
    a current kicker make-probability or a forecast of historical repeatability.
    """
    source_ids=set(source_ids)
    rows=[r for r in records if r['source_id'] in source_ids and r['position']=='K']
    if (not rows or len({(r['team'],r['period']) for r in rows})!=1 or
        any(r.get(k) is None or not math.isfinite(r[k]) or r[k]<0 or r[k]!=int(r[k])
            for r in rows for k in [*FG_DISTANCE_POINTS,'fg_made','fg_att']) or
        any(sum(r[k] for k in FG_DISTANCE_POINTS)!=r['fg_made'] or r['fg_att']<r['fg_made'] for r in rows)):
        raise ValueError('Missing/inconsistent sourced field-goal attempts or distance bins; no marginal-distance fallback')
    distances={k:int(sum(r[k] for r in rows)) for k in FG_DISTANCE_POINTS}
    made=int(sum(r['fg_made'] for r in rows));attempts=int(sum(r['fg_att'] for r in rows))
    return dict(version='joint_source_kicking_v1',team=rows[0]['team'],donor_period=rows[0]['period'],
        source_ids=sorted(r['source_id'] for r in rows),
        donor_kickers=[dict(player_master_id=r['player_master_id'],source_player_id=r['source_player_id'],source_id=r['source_id']) for r in rows],
        attempts=attempts,made=made,missed=attempts-made,distance_counts=distances,
        fg_points=sum(distances[k]*points for k,points in FG_DISTANCE_POINTS.items()),
        interpretation='Conditional same-team donor FG outcome, not calibrated current-kicker make/distance probabilities; PATs use the declared all-success case assumption')


def build(receipt, records, pool_rows, *, before_period, cutoff, games, markets):
    if not receipt.get('learned_opportunities') or not receipt.get('yardage_model'):
        raise ValueError('Scenario-first requires authenticated learned counts and efficiency')
    if len(games)!=1:raise ValueError('Scenario-first v1 supports one Captain game')
    game=games[0];home=game.get('home_team') or game['game_id'].split('_')[-1];away=game.get('away_team') or game['game_id'].split('_')[-2]
    quotes=[r for r in markets if r['game_id']==game['game_id']]
    if len(quotes)!=1:raise ValueError('One exact game market quote is required')
    quote=quotes[0];total=known(quote,('game_total',));spread=quote.get('home_spread')
    if total is None or total<=0 or spread is None or not math.isfinite(float(spread)):
        raise ValueError('Known total and home spread required; no neutral fallback')
    implied={home:(total-float(spread))/2,away:(total+float(spread))/2}
    if min(implied.values())<=0:raise ValueError('Unsupported implied team score')
    history=checked_history(records,before_period=before_period,cutoff=cutoff)
    past,excluded=team_history(history);response=volume_response(past);roles=Roles(history,before_period)
    def population_rate(numerator,denominator):
        pairs=[r for r in history if r.get(numerator) is not None and r.get(denominator) is not None and r[denominator]>0]
        if len(pairs)<10:raise ValueError('Missing residual role population evidence')
        return sum(r[numerator] for r in pairs)/sum(r[denominator] for r in pairs)
    residual_rates=dict(catch=population_rate('receptions','targets'),receiving_td=population_rate('receiving_tds','targets'),
        rushing_td=population_rate('rushing_tds','rush_attempts'),rushing_yards=population_rate('rushing_yards','rush_attempts'))
    result=deepcopy(receipt);by={a['player_master_id']:a for a in result['players']};native={str(r['player_id']):r for r in pool_rows}
    evidence={};kickers={};team_recent={}
    for team in (home,away):
        team_recent[team]=[r for r in past if r['team']==team][-8:]
        if len(team_recent[team])<3:raise ValueError('Three supported prior full-team scoring games required')
    for pid,a in by.items():
        a['prior_comparison_utility']=a.get('utility');a['utility']=None;a['scenario_scores']={}
        if a['position'] in {'QB','RB','WR','TE'} and a['prior_comparison_utility'] is not None:
            evidence[pid]={key:roles.rate(a,*pair) for key,pair in {
                'catch':('receptions','targets'),'receiving_td':('receiving_tds','targets'),
                'rushing_td':('rushing_tds','rush_attempts')}.items()}
            if (a['counts'].get('rush_attempts',0)>0 and evidence[pid]['rushing_td'] is None) or (a['position']!='QB' and (evidence[pid]['catch'] is None or evidence[pid]['receiving_td'] is None)):
                evidence.pop(pid);a['reasons'].append('Missing sourced scenario role rates');continue
        elif a['position']=='K' and pid in native:
            source=native[pid]
            if source.get('canonical_role')!='expected_starter' or source.get('role_optimizer_eligible') is False:continue
            same=[r for r in history if r['player_master_id']==pid and r['team']==a['team'] and r['period']//100==before_period//100][-8:]
            bins=['fg_made_0_19','fg_made_20_29','fg_made_30_39','fg_made_40_49','fg_made_50_59','fg_made_60_']
            if len(same)<3 or any(r[k] is None for r in same for k in [*bins,'fg_made','fg_att','pat_made','pat_att']):
                a['reasons'].append('Missing current-team FG/PAT opportunity evidence');continue
            try:
                for row in same:kicking_profile(same,[row['source_id']])
            except ValueError:
                a['reasons'].append('Inconsistent current-team FG attempts/distance evidence');continue
            if sum(r['fg_made'] for r in same)<=0:
                a['reasons'].append('Unknown prior made-FG distance mix');continue
            if a['team'] in kickers:raise ValueError('Ambiguous canonical starting kicker')
            kickers[a['team']]=pid;evidence[pid]=dict(kicking=dict(source_ids=[r['source_id'] for r in same],games=len(same),
                fg_attempts=sum(r['fg_att'] for r in same),fg_made=sum(r['fg_made'] for r in same),
                pat_attempts=sum(r['pat_att'] for r in same),pat_made=sum(r['pat_made'] for r in same),
                distance_weights={'3':sum(r[k] for r in same for k in bins[:3]),'4':sum(r[bins[3]] for r in same),'5':sum(r[k] for r in same for k in bins[4:])}))
    from .captain_case_variation import profiles as joint_profiles, allocate as variable_allocate, allocate_passers, allocation_plan
    for team in (home,away):
        starter=by.get(receipt['starter_ids'].get(team),{})
        proof=starter.get('current_role_evidence') or {}
        if (starter.get('position')!='QB' or starter.get('canonical_role')!='expected_starter' or
            starter.get('world_activity') is False or starter.get('player_master_id') not in evidence or
            proof.get('player_id')!=starter.get('player_master_id') or proof.get('team')!=team or
            proof.get('role')!='expected_starter' or not proof.get('source_ids')):
            raise ValueError('Sourced current starter required for conditional passing reconciliation')
    variation={team:joint_profiles(history,past,team=team,starter_id=receipt['starter_ids'][team],
        members={pid:a for pid,a in by.items() if a['team']==team and pid in evidence and a['position']!='K'},before_period=before_period) for team in (home,away)}
    worlds=[]
    for coordinate,home_delta,away_delta in COORDINATES:
        for draw in range(DRAWS_PER_COORDINATE):
            wid=f'{coordinate}:{draw}';rng=np.random.default_rng(SEED+len(worlds));world=dict(world_id=wid,likelihood='unknown',coordinate=coordinate,teams={},player_stats={},player_scores={},events=[])
            scoring={team:composition(max(0.,implied[team]+delta),[r for r in past if r['team']==team],draw+offset)
                for team,delta,offset in [(home,home_delta,0),(away,away_delta,1)]}
            for team,opponent,delta,other_delta in [(home,away,home_delta,away_delta),(away,home,away_delta,home_delta)]:
                budget=receipt['teams'][team];target=max(0.,implied[team]+delta);opp_target=max(0.,implied[opponent]+other_delta)
                td,fg,profile_ids=scoring[team];kick_profile=kicking_profile(history,profile_ids)
                if kick_profile['made']!=fg or kick_profile['team']!=team:raise ValueError('Scoring/kicking source profile mismatch')
                members={pid:a for pid,a in by.items() if a['team']==team and pid in evidence and a['position']!='K'}
                profile=variation[team]['profiles'][draw]
                change=np.asarray(response['slopes'])@np.array([7*td+3*fg-implied[team],7*scoring[opponent][0]+3*scoring[opponent][1]-implied[opponent]])
                pass_n=max(0,int(round((budget['pass_attempts']+change[0])*profile['volume_factors']['pass_attempts'])));rush_n=max(0,int(round((budget['rush_attempts']+change[1])*profile['volume_factors']['rush_attempts'])))
                target_n=min(pass_n,int(round(pass_n*budget['targets']/budget['pass_attempts'])))
                passing,passing_audit=allocate_passers(pass_n,profile['passing_roles'],set(members))
                allocations={'pass_attempts':passing};opportunity_audit={}
                for channel,n in [('rush_attempts',rush_n),('targets',target_n)]:
                    weights={pid:float(a['counts'][channel]) for pid,a in members.items() if a['counts'].get(channel) is not None}
                    residual=budget[channel]-sum(weights.values())
                    if residual<-1e-6:raise ValueError('Scenario counts exceed full-source team budget')
                    factors={pid:profile['multipliers'][pid].get(channel,1.) for pid in weights}
                    opportunity_audit[channel]=allocation_plan(n,weights,residual,factors)
                    allocations[channel]=variable_allocate(n,weights,residual,factors,rng)
                qbs={pid:n for pid,n in allocations['pass_attempts'].items() if n>0}
                receivers={pid:n for pid,n in allocations['targets'].items() if n>0}
                # All completions are shared QB/receiver events, including explicit unknown actors.
                passing_td_rate=sum(r['pass_tds'] for r in team_recent[team]);rushing_td_rate=sum(r['rush_tds'] for r in team_recent[team])
                if passing_td_rate+rushing_td_rate<=0:raise ValueError('Unsupported historical team TD mix')
                p=passing_td_rate/(passing_td_rate+rushing_td_rate)
                weights={pid:receivers[pid]*(evidence[pid]['receiving_td']['value'] if pid!=UNKNOWN else residual_rates['receiving_td']) for pid in receivers}
                supported_td_targets=sum(n for pid,n in receivers.items() if weights[pid]>0)
                possible=list(range(max(0,td-rush_n),min(td,supported_td_targets,pass_n)+1))
                masses=np.array([math.comb(td,n)*p**n*(1-p)**(td-n) for n in possible],dtype=float)
                if not possible or masses.sum()<=0:raise ValueError('Scoring case exceeds physical pass/rush opportunity capacity')
                pass_td=int(rng.choice(possible,p=masses/masses.sum()))
                # Conditional on this case's passing TDs, at least those catches
                # must occur. Bounded rejection preserves the catch model rather
                # than inventing targets, forcing a receiver or clipping TDs.
                for completion_draw in range(64):
                    recs={pid:int(rng.binomial(n,min(1.,max(0.,(evidence[pid]['catch']['value'] if pid!=UNKNOWN else residual_rates['catch'])*profile['completion_factor'])))) for pid,n in receivers.items()}
                    if sum(n for pid,n in recs.items() if weights[pid]>0)>=pass_td:break
                else:raise ValueError('Conditional completion draw bound exhausted')
                stats={pid:dict(pass_attempts=allocations['pass_attempts'].get(pid,0),rush_attempts=allocations['rush_attempts'].get(pid,0),
                    targets=allocations['targets'].get(pid,0),receptions=recs.get(pid,0),passing_yards=0.,rushing_yards=0.,receiving_yards=0.,
                    passing_tds=0,receiving_tds=0,rushing_tds=0,fg_points=0,pat_made=0) for pid in sorted(set(members)|{UNKNOWN})}
                rec_td={pid:0 for pid in receivers};completion_events=[];available_passes=dict(qbs)
                for _ in range(pass_td):
                    receiver=draw_one(rng,weights,{pid:recs[pid]-rec_td[pid] for pid in receivers});rec_td[receiver]+=1
                for receiver in sorted(recs):
                    for index in range(recs[receiver]):
                        passer=draw_one(rng,qbs,available_passes);available_passes[passer]-=1
                        touchdown=index<rec_td[receiver];stats[receiver]['receiving_tds']+=int(touchdown);stats[passer]['passing_tds']+=int(touchdown)
                        completion_events.append((passer,receiver))
                        if touchdown:world['events'].append(dict(team=team,kind='passing_td',passer=passer,receiver=receiver))
                carries=allocations['rush_attempts'];rush_weights={pid:(n*(evidence[pid]['rushing_td']['value'] if pid!=UNKNOWN else residual_rates['rushing_td']) if n else 0.) for pid,n in carries.items()}
                used_rush=dict.fromkeys(carries,0)
                for _ in range(td-pass_td):
                    rusher=draw_one(rng,rush_weights,{pid:n-used_rush[pid] for pid,n in carries.items()});used_rush[rusher]+=1;stats[rusher]['rushing_tds']+=1
                    world['events'].append(dict(team=team,kind='rushing_td',rusher=rusher))
                # Shared passing yards arise from actual sampled catches. Never
                # normalize receivers back up to an attempts×YPA yard floor.
                old_account=receipt['yardage_model']['accounting'][team]
                for pid in receivers:
                    ypc=(members[pid]['efficiency']['receiving_yards']['value']/max(evidence[pid]['catch']['value'],1e-9)
                        if pid!=UNKNOWN else old_account['residual_rate']/residual_rates['catch'])
                    stats[pid]['receiving_yards']=recs[pid]*ypc*profile['yards_per_completion_factor']
                for passer,receiver in completion_events:stats[passer]['passing_yards']+=stats[receiver]['receiving_yards']/recs[receiver]
                for pid,n in carries.items():
                    if pid==UNKNOWN:stats[pid]['rushing_yards']=n*residual_rates['rushing_yards']
                    elif n:
                        rate=members[pid]['efficiency'].get('rushing_yards')
                        if rate is None:raise ValueError('Missing conditional rushing efficiency')
                        stats[pid]['rushing_yards']=n*rate['value']
                kicker=kickers.get(team,UNKNOWN);kick_stats=dict(fg_points=kick_profile['fg_points'],pat_made=td)
                if kicker!=UNKNOWN:
                    stats[kicker]=dict(pass_attempts=0,rush_attempts=0,targets=0,receptions=0,passing_yards=0.,rushing_yards=0.,receiving_yards=0.,passing_tds=0,receiving_tds=0,rushing_tds=0,**kick_stats)
                else:
                    # Missing current-kicker proof retains the event/points in
                    # the explicit unknown bucket, without losing offense work.
                    stats[UNKNOWN].update(kick_stats)
                world['events'].extend([dict(team=team,kind='made_fg',kicker=kicker) for _ in range(fg)])
                world['events'].extend([dict(team=team,kind='missed_fg',kicker=kicker) for _ in range(kick_profile['missed'])])
                world['events'].extend([dict(team=team,kind='made_pat',kicker=kicker) for _ in range(td)])
                ledger=dict(target_points=target,historical_scoring_profile_ids=profile_ids,points=7*td+3*fg,touchdowns=td,passing_tds=pass_td,rushing_tds=td-pass_td,
                    made_field_goals=fg,field_goal_attempts=kick_profile['attempts'],missed_field_goals=kick_profile['missed'],kicking_profile=kick_profile,made_pats=td,joint_role_profile=profile,opportunity_allocation=opportunity_audit,passing_allocation=passing_audit,completion_draw_attempts=completion_draw+1,pass_attempts=pass_n,rush_attempts=rush_n,targets=target_n,
                    passing_yards=sum(v['passing_yards'] for v in stats.values()),receiving_yards=sum(v['receiving_yards'] for v in stats.values()),
                    unknown=stats[UNKNOWN],quarterback_pass_residual=allocations['pass_attempts'].get(UNKNOWN,0),
                    unknown_target_residual=allocations['targets'].get(UNKNOWN,0),kicker=kicker)
                if abs(ledger['passing_yards']-ledger['receiving_yards'])>1e-6 or sum(v['passing_tds'] for v in stats.values())!=sum(v['receiving_tds'] for v in stats.values()):
                    raise ValueError('Shared event conservation failure')
                world['teams'][team]=ledger
                for pid,s in stats.items():
                    if pid==UNKNOWN:continue
                    world['player_stats'][pid]=s
                    world['player_scores'][pid]=float(.04*s['passing_yards']+.1*(s['rushing_yards']+s['receiving_yards'])+s['receptions']+
                        4*s['passing_tds']+6*(s['receiving_tds']+s['rushing_tds'])+s['fg_points']+s['pat_made']+
                        3*sum(s[k]>=threshold for k,threshold in [('passing_yards',300),('rushing_yards',100),('receiving_yards',100)]))
            worlds.append(world)
    primary_worlds=[w for w in worlds if w['coordinate']=='central']
    primary_scenario=dict(version='market_implied_primary_v1',basis='market_total_and_home_spread',
        game_id=game['game_id'],market_snapshot_id=quote.get('market_snapshot_id'),
        game_total=total,home_spread=float(spread),home_team=home,away_team=away,implied_points=implied,
        team_score_support_band=3.,case_ids=[w['world_id'] for w in primary_worlds],
        diagnostic_case_ids=[w['world_id'] for w in worlds if w['coordinate']!='central'],
        selection='Only market-centered cases enter eligibility utility, legal benchmarks, coverage and tie-breaks.',
        interpretation='Market-implied expected scoring environment, not a proven modal exact score or calibrated case probability.')
    for pid,a in by.items():
        a['scenario_role_evidence']=evidence.get(pid)
        if pid in evidence and all(pid in w['player_scores'] for w in worlds):
            a['scenario_scores']={w['world_id']:w['player_scores'][pid] for w in worlds}
            a['utility']=float(np.mean([w['player_scores'][pid] for w in primary_worlds]))
            a['reasons']=[v for v in a['reasons'] if v!='not modeled: offensive workload domain only']
        elif a['position']=='K':a['reasons'].append('Unknown scenario kicking support; no incumbent fallback')
    result['scenario_first']=dict(version=VERSION,seed=SEED,market=deepcopy(quote),implied_points=implied,
        passing_reconciliation=dict(version='source_passer_shares_v1',
            basis='conditional historical full-team passer shares, with current sourced starting QB',
            learned_counts_unchanged=True,model_gap_is_not_backup_evidence=True,
            teams={team:dict(starter_id=receipt['starter_ids'][team],team_learned_attempts=receipt['teams'][team]['pass_attempts'],
                starter_learned_attempts=by[receipt['starter_ids'][team]]['counts']['pass_attempts'],
                forecast_difference=receipt['teams'][team]['pass_attempts']-sum(a['counts'].get('pass_attempts') or 0 for a in by.values() if a['team']==team),
                current_starter_evidence=by[receipt['starter_ids'][team]]['current_role_evidence']) for team in (home,away)}),
        primary_scenario=primary_scenario,
        construction_policy=dict(team_split='3-3',category='explicit_user_construction_policy',basis='Competitive-game starting construction, not an inferred universal optimum'),
        selection_policy='market_primary_whole_roster_case_coverage_then_mean_capture',worlds=worlds,world_count=len(worlds),
        joint_role_variation={team:{k:v for k,v in model.items() if k!='profiles'} for team,model in variation.items()},
        joint_role_code_sha256=hashlib.sha256(Path(__file__).with_name('captain_case_variation.py').read_bytes()).hexdigest(),
        source_ids=[r['source_id'] for r in history],source_sha256=digest(history),code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        training_max_period=max(r['period'] for r in history),residual_rates=residual_rates,volume_response=response,excluded_historical_team_games=excluded,
        historical_complete_team_games=len(past),likelihood='unknown',
        assumptions=['Conditional offensive/kicking scoring cases, not full possession/clock simulation.',
            'TD/FG compositions span actual same-team prior profiles within one field goal of the stress target, including TD-heavy/zero-FG profiles when sourced; counts are never scaled from low-scoring games.',
            'Made FG counts, distance bins and missed FG attempts remain linked to one same-team donor outcome. Current starter proof is separate; this is not a calibrated kicking distribution.',
            'All PATs succeed in this first slice; missed PATs, turnovers, defensive/return scores and two-point plays are outside these conditional cases, not observed zeros.',
            'Historical whole-field TD/opportunity rates approximate scoring roles; red-zone-specific and current role persistence uncertainty remain.',
            'Targets and carries use balanced whole-count rounding around conditional joint-profile shares. No additional multinomial count draw is supported; source-role expansion remains possible without player-specific caps. Conditional expected counts and role factors are audited per team/channel.',
            'Published learned counts remain anchors. Current-starter-compatible prior games vary team volumes, role shares, completions and shared yards. Observed zero work is retained; missing rows are not zeros. These cases have unknown likelihood.',
            'Passing attempts use actual full-source donor passer shares; independent learned player/team forecast disagreement is not evidence of another passer. Single-passer donors give that passer all case attempts; observed relief/trick-play passers retain their sourced shares, with unsupported identities explicit. Learned anchors stay unchanged.',
            'Receiving/rushing residual actors retain their production; salary exclusions never redistribute it. Historical relief/trick-play shares are conditional examples, not calibrated current-game substitution probabilities.',
            'Four market-centered cases alone drive primary selection. Sixteen alternative-script cases are diagnostic only and never enter selection or tie-breaks. Case likelihood is unknown; no win probability, independent player P90 or incumbent fantasy projection is used.',
            '3-3 is the explicit initial construction policy; not automatically inferred as optimal from a close spread.'])
    result['objective']='whole_lineup_case_coverage';result['normalization_policy']='scenario_first_no_position_count_or_yard_utility_selection'
    result['domain']='Supported offense and current starting kickers; DST and missing scenario evidence excluded explicitly'
    result['sha256']=digest({k:v for k,v in result.items() if k!='sha256'})
    return result
