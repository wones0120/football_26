"""Offline game-block scenario research. No production promotion or database writes.

Team-score and player forecast errors are resampled from the SAME completed game.
Players map by pregame team/position/mean rank, never display name. This preserves
empirical role-level dependence but is not an event-level possession simulator.
"""
from __future__ import annotations
from collections import Counter
from datetime import datetime
import hashlib
import json
import numpy as np
import pulp

MODEL_ID = 'pregame_game_block_residual_bootstrap_v1'
SCENARIOS = ('high_close', 'low_close', 'high_home_blowout', 'high_away_blowout',
             'low_home_blowout', 'low_away_blowout')

def classify(scores, *, high_total=48., blowout_margin=14.):
    scores=np.asarray(scores,dtype=float)
    if not np.isfinite(high_total) or high_total<=0 or not np.isfinite(blowout_margin) or blowout_margin<=0:
        raise ValueError('Scenario thresholds must be positive and finite')
    if scores.ndim!=2 or scores.shape[1]!=2 or not np.isfinite(scores).all():
        raise ValueError('Expected finite home/away score pairs')
    total=scores.sum(axis=1);margin=scores[:,0]-scores[:,1]
    return np.where(np.abs(margin)<blowout_margin,np.where(total>=high_total,0,1),
                    np.where(total>=high_total,np.where(margin>=blowout_margin,2,3),
                             np.where(margin>=blowout_margin,4,5))).astype(int)

def shortlist(players, limit=4):
    return [p['id'] for p in sorted(players,key=lambda p:(-p['projected_p90'],p['id']))
            if not p.get('captain_excluded',False)][:limit]

def role_keys(players, home):
    keys={}
    for side in (0,1):
        for pos in ('QB','RB','WR','TE','K','DST'):
            group=sorted([p for p in players if (0 if p['team']==home else 1)==side and p['position']==pos],
                         key=lambda p:(-p['projected_mean'],p['id']))
            for rank,p in enumerate(group):keys[p['id']]=(side,pos,rank)
    return keys

def simulate(game, blocks, *, draws, seed, high_total=48., blowout_margin=14.):
    if draws < 1 or not 0 <= seed <= 2**32-1:raise ValueError('Invalid simulation count or seed')
    def clock(value):
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
        if parsed.tzinfo is None:raise ValueError('Research clocks require an explicit timezone')
        return parsed
    cutoff=clock(game['cutoff'])
    if len(blocks)<6:raise ValueError('At least six cutoff-safe historical game blocks required')
    # A game may only use completed, already-imported evidence before its cutoff.
    for b in blocks:
        if clock(b['available_at'])>=cutoff or clock(b['kickoff'])>=cutoff or b['game']==game['game']:
            raise ValueError('Training evidence is unavailable at target cutoff')
    rng=np.random.default_rng(seed);indices=rng.integers(len(blocks),size=draws)
    error=np.asarray([b['score_errors'] for b in blocks]);scores=np.maximum(0,np.rint(np.asarray(game['implied_scores'])+error[indices]))
    keys=role_keys(game['players'],game['home']);out=np.empty((draws,len(game['players'])));missing=Counter()
    for j,p in enumerate(game['players']):
        key=keys[p['id']];res=[]
        for b in blocks:
            # No fabricated independent error for unmatched historical roles.
            # Mean-only fallback is disclosed; the historical team draw stays joint.
            v=b['role_errors'].get(key)
            if v is None:missing[p['id']]+=1;v=0.
            res.append(v)
        out[:,j]=p['projected_mean']+np.asarray(res)[indices]
    labels=classify(scores,high_total=high_total,blowout_margin=blowout_margin)
    support=np.bincount(classify(np.maximum(0,np.rint(np.asarray(game['implied_scores'])+error)),high_total=high_total,blowout_margin=blowout_margin),minlength=6).tolist()
    return out,labels,dict(scores=scores.tolist(),training_games=[b['game'] for b in blocks],
                           unmatched_role_block_counts=dict(missing),scenario_block_support=support,seed=seed,
                           negative_fantasy_outcomes_retained=int((out<0).sum()),
                           draws_sha256=hashlib.sha256(out.tobytes()+labels.tobytes()).hexdigest())

def legal(players, captain, rules):
    if len(players)!=6 or len({p['id'] for p in players})!=6:return False
    if sorted(Counter(p['team'] for p in players).values())!=[2,4]:return False
    if sum(p['captain_salary'] if p['id']==captain else p['salary'] for p in players)>50000:return False
    if rules.get('single_te') and sum(p['position']=='TE' for p in players)>1:return False
    if rules.get('no_two_qbs') and sum(p['position']=='QB' for p in players)>1:return False
    ids={p['id'] for p in players}
    if captain not in ids:return False
    if not set(rules.get('locked_ids',[])).issubset(ids):return False
    if rules.get('leader_ids') and not ids.intersection(rules['leader_ids']):return False
    if rules.get('avoid_dst_opponents'):
        for p in players:
            if p['position']=='DST' and any(q['team']!=p['team'] and q['position']!='DST' for q in players):return False
    c=next(p for p in players if p['id']==captain)
    if rules.get('qb_correlations'):
        if c['position']!='RB' and not any(p['position']=='QB' for p in players):return False
        for tm in {p['team'] for p in players}:
            pcs=sum(p['team']==tm and p['position'] in ('WR','TE') for p in players)
            qb=any(p['team']==tm and p['position']=='QB' for p in players)
            if c['position']!='RB' and pcs>=2 and not qb:return False
        if c['position'] in ('WR','TE') and not any(p['team']==c['team'] and p['position']=='QB' for p in players):return False
        if c['position']=='QB' and sum(p['team']==c['team'] and p['position'] in ('WR','TE') for p in players)<(1 if c.get('high_rushing') else 2):return False
    return True

def solve(players, captain, flex_scores, rules):
    """Fixed captain ILP; score inputs come exclusively from development draws."""
    c=next(i for i,p in enumerate(players) if p['id']==captain)
    model=pulp.LpProblem('ResearchFlex',pulp.LpMaximize)
    x=[pulp.LpVariable(f'x_{i}',cat='Binary') for i in range(len(players))]
    model+=pulp.lpSum(float(flex_scores[i])*x[i] for i in range(len(players)))
    model+=pulp.lpSum(x)==6;model+=x[c]==1
    model+=pulp.lpSum(p['salary']*x[i] for i,p in enumerate(players))+.5*players[c]['salary']<=50000
    tm=sorted({p['team'] for p in players})[0];side=pulp.LpVariable('four_on_side',cat='Binary')
    model+=pulp.lpSum(x[i] for i,p in enumerate(players) if p['team']==tm)==2+2*side
    ids={p['id']:i for i,p in enumerate(players)}
    for pid in rules.get('locked_ids',[]):
        if pid not in ids:return None
        model+=x[ids[pid]]==1
    if rules.get('leader_ids'):model+=pulp.lpSum(x[i] for i,p in enumerate(players) if p['id'] in rules['leader_ids'])>=1
    if rules.get('single_te'):model+=pulp.lpSum(x[i] for i,p in enumerate(players) if p['position']=='TE')<=1
    if rules.get('no_two_qbs'):model+=pulp.lpSum(x[i] for i,p in enumerate(players) if p['position']=='QB')<=1
    if rules.get('avoid_dst_opponents'):
        for i,p in enumerate(players):
            if p['position']=='DST':
                for j,q in enumerate(players):
                    if q['team']!=p['team'] and q['position']!='DST':model+=x[i]+x[j]<=1
    if rules.get('qb_correlations'):
        cp=players[c]
        if cp['position']!='RB':model+=pulp.lpSum(x[i] for i,p in enumerate(players) if p['position']=='QB')>=1
        for team in {p['team'] for p in players}:
            pcs=[i for i,p in enumerate(players) if p['team']==team and p['position'] in ('WR','TE')];qbs=[i for i,p in enumerate(players) if p['team']==team and p['position']=='QB']
            if cp['position']!='RB':model+=pulp.lpSum(x[i] for i in pcs)<=1+max(1,len(pcs)-1)*pulp.lpSum(x[i] for i in qbs)
        if cp['position'] in ('WR','TE'):model+=pulp.lpSum(x[i] for i,p in enumerate(players) if p['team']==cp['team'] and p['position']=='QB')>=1
        if cp['position']=='QB':model+=pulp.lpSum(x[i] for i,p in enumerate(players) if p['team']==cp['team'] and p['position'] in ('WR','TE'))>=(1 if cp.get('high_rushing') else 2)
    if model.solve(pulp.PULP_CBC_CMD(msg=False))!=pulp.LpStatusOptimal:return None
    selected=tuple(i for i,v in enumerate(x) if v.value()>.5)
    assert legal([players[i] for i in selected],captain,rules)
    return dict(captain_id=captain,indices=list(selected))

def lineup_scores(outcomes, players, lineup):
    c=next(i for i,p in enumerate(players) if p['id']==lineup['captain_id'])
    return outcomes[:,lineup['indices']].sum(axis=1)+.5*outcomes[:,c]

def reference_pool(game, baseline, *, seed, limit=1000):
    """Fixed sampled legal pool, disclosed benchmark rather than simulated field."""
    ps=game['players'];caps=shortlist(ps);rng=np.random.default_rng(seed);found={}
    def add(l):
        if l is not None:found[(l['captain_id'],tuple(l['indices']))]=l
    for l in baseline:add(l)
    for _ in range(limit*200):
        c=caps[int(rng.integers(len(caps)))];ci=next(i for i,p in enumerate(ps) if p['id']==c)
        rest=[i for i in range(len(ps)) if i!=ci];indices=tuple(sorted([ci]+rng.choice(rest,5,replace=False).tolist()))
        if legal([ps[i] for i in indices],c,game['rules']):add(dict(captain_id=c,indices=list(indices)))
        if len(found)>=limit:break
    if not found:raise ValueError('No legal benchmark lineups')
    return list(found.values())

def benchmark_threshold(outcomes, players, reference):
    values=np.column_stack([lineup_scores(outcomes,players,l) for l in reference])
    # Empirical top-5% boundary within the SAME predeclared reference pool.
    return np.quantile(values,.95,axis=1)

def metrics(scores, labels, threshold):
    hits=scores>=threshold;prob=np.bincount(labels,minlength=6)/len(labels)
    rows=[]
    for z,name in enumerate(SCENARIOS):
        mask=labels==z;n=int(mask.sum());k=int(hits[mask].sum())
        # Wilson interval is Monte Carlo precision only, not model uncertainty.
        if n:
            p=k/n;den=1+1.96**2/n;mid=(p+1.96**2/(2*n))/den;half=1.96*np.sqrt(p*(1-p)/n+1.96**2/(4*n*n))/den;interval=[max(0.,mid-half),min(1.,mid+half)]
        else:p=None;interval=None
        rows.append(dict(scenario=name,probability=float(prob[z]),samples=n,high_finish_rate=p,mc_interval95=interval,mean_actual_simulated_points=float(scores[mask].mean()) if n else None))
    weighted=sum(r['probability']*(r['high_finish_rate'] or 0.) for r in rows)
    assert abs(weighted-hits.mean())<1e-10
    return dict(mean=float(scores.mean()),p90=float(np.quantile(scores,.9)),high_finish_rate=float(hits.mean()),weighted_high_finish_rate=weighted,scenarios=rows)

def research_game(game, blocks, *, draws=2000, seed=1212, reference_limit=1000):
    # Separate development, selection and final evaluation streams.
    ps=game['players']
    if len(ps)<6 or len({p['id'] for p in ps})!=len(ps) or len({p['team'] for p in ps})!=2:
        raise ValueError('Research needs unique canonical players from exactly two teams')
    for p in ps:
        if p['position'] not in ('QB','RB','WR','TE','K','DST') or not all(np.isfinite(p[k]) for k in ('salary','captain_salary','projected_mean','projected_p90')):
            raise ValueError('Invalid player price, position or forecast')
        if p['salary']<0 or abs(p['captain_salary']-1.5*p['salary'])>1e-7:raise ValueError('Captain salary must be 1.5 times FLEX price')
    streams=[simulate(game,blocks,draws=draws,seed=seed+i) for i in range(3)]
    dev,labels,_=streams[0];ps=game['players'];baselines=[];candidates=[]
    for cap in shortlist(ps):
        l=solve(ps,cap,[p['projected_mean'] for p in ps],game['rules'])
        if l is None:continue
        l.update(source='unrestricted',generation_scenario=None);baselines.append(l);candidates.append(l)
        for z,name in enumerate(SCENARIOS):
            if sum(labels==z)<30:continue
            l=solve(ps,cap,dev[labels==z].mean(axis=0),game['rules'])
            if l is not None:l.update(source='scenario',generation_scenario=name);candidates.append(l)
    if not baselines:raise ValueError('All shortlisted captains infeasible under retained constraints')
    ref=reference_pool(game,baselines,seed=seed+3,limit=reference_limit)
    tune,tlabels,_=streams[1];ev,elabels,evidence=streams[2]
    tthreshold=benchmark_threshold(tune,ps,ref);ethreshold=benchmark_threshold(ev,ps,ref)
    # Actuals and the final evaluation sample NEVER choose a lineup.
    baseline=max(baselines,key=lambda l:1.5*next(p['projected_p90'] for p in ps if p['id']==l['captain_id'])+sum(ps[i]['projected_mean'] for i in l['indices'] if ps[i]['id']!=l['captain_id']))
    for l in candidates:
        ts=lineup_scores(tune,ps,l);l['selection_high_finish_rate']=float((ts>=tthreshold).mean())
    selection_key=lambda l:(l['selection_high_finish_rate'],float(lineup_scores(tune,ps,l).mean()))
    simulation_baseline=max(baselines,key=selection_key)
    selected=max(candidates,key=selection_key)
    for l in candidates:
        l['evaluation']=metrics(lineup_scores(ev,ps,l),elabels,ethreshold)
        for z,row in enumerate(l['evaluation']['scenarios']):row['historical_block_support']=evidence['scenario_block_support'][z]
        l['players']=[dict(ps[i],slot='CPT' if ps[i]['id']==l['captain_id'] else 'FLEX') for i in l['indices']]
        l['salary']=sum(p['captain_salary'] if p['slot']=='CPT' else p['salary'] for p in l['players'])
    captain_reports=[]
    for cap in shortlist(ps):
        family=[l for l in candidates if l['captain_id']==cap]
        if not family:captain_reports.append(dict(captain_id=cap,feasible=False));continue
        # Freeze strongest scenario on selection draws; evaluation only reports it.
        best=None
        for l in family:
            scores=lineup_scores(tune,ps,l)
            for z,name in enumerate(SCENARIOS):
                mask=tlabels==z
                if mask.sum()<30:continue
                value=float((scores[mask]>=tthreshold[mask]).mean())
                key=(value,int(mask.sum()),float(scores[mask].mean()))
                if best is None or key>best[0]:best=(key,name,l)
        l=max(family,key=lambda l:(l['selection_high_finish_rate'],float(lineup_scores(tune,ps,l).mean())))
        strongest=next(r for r in best[2]['evaluation']['scenarios'] if r['scenario']==best[1]) if best else None
        if strongest:
            strongest=dict(strongest);mask=elabels==SCENARIOS.index(best[1]);strongest['captain_mean_points']=float(ev[mask,next(i for i,p in enumerate(ps) if p['id']==cap)].mean())
        unrestricted=next(l for l in baselines if l['captain_id']==cap)
        captain_reports.append(dict(unrestricted_lineup=unrestricted,captain_id=cap,name=next(p['name'] for p in ps if p['id']==cap),feasible=True,strongest_scenario=strongest,strongest_scenario_lineup=best[2] if best else None,best_overall_lineup=l,captain_simulated_mean=float(ev[:,next(i for i,p in enumerate(ps) if p['id']==cap)].mean())))
    return dict(game=game['game'],pricing=game['pricing'],cutoff=game['cutoff'],kickoff=game['kickoff'],home=game['home'],shortlist=shortlist(ps),rules=game['rules'],training_games=evidence['training_games'],training_available_at=[b['available_at'] for b in blocks],simulation_model=MODEL_ID,simulation_seeds=[seed+i for i in range(3)],draws_per_stream=draws,draws_sha256=[s[2]['draws_sha256'] for s in streams],unmatched_role_block_counts=evidence['unmatched_role_block_counts'],negative_fantasy_outcomes_retained=evidence['negative_fantasy_outcomes_retained'],simulation_mean_vs_projection={p['id']:float(ev[:,i].mean()-p['projected_mean']) for i,p in enumerate(ps)},benchmark_pool_count=len(ref),benchmark_pool_sha256=hashlib.sha256(json.dumps(ref,sort_keys=True).encode()).hexdigest(),scenario_probabilities=metrics(np.zeros(draws),elabels,np.ones(draws))['scenarios'],baseline=baseline,simulation_baseline=simulation_baseline,selected=selected,captains=captain_reports,candidates=candidates)
