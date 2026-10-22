"""Research-only chronological FG and conditional TD calibration primitives.

No serving import or optimizer activation. Marginals are not joint case weights.
Canonical/native source identities and evidence clocks remain explicit.
"""
from collections import defaultdict
from datetime import datetime, timezone
import math
import numpy as np

FEATURES=('own_implied','opponent_implied','prior_fg_attempts','prior_fg_makes','prior_offensive_tds')


def clock(value):
    d=value if isinstance(value,datetime) else datetime.fromisoformat(str(value).replace('Z','+00:00'))
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)


def feature_rows(games, schedules, markets, history, *, before_period):
    """Earlier-period rolling stats; genuine prelock quotes for 2026W5–6.

    Revised archived lines are diagnostic only outside the timestamp-checked
    evaluation. Source stats/market imports must precede decision on clean rows.
    """
    if any(g['period']>=before_period for g in games) or any(r['period']>=before_period for r in history):raise ValueError('Future calibration period')
    from .market_snapshots import canonical_team
    schedule={}
    for s in schedules:
        for team in (s['home_team'],s['away_team']):
            key=(s['season']*100+s['week'],canonical_team(team))
            if key in schedule:raise ValueError('Duplicate native schedule team/period')
            schedule[key]=s
    imported={a['source_id']:clock(a['imported_at']) for a in history}
    quotes=defaultdict(list)
    for q in markets:quotes[q['game_id']].append(q)
    past=defaultdict(list);rows=[];excluded=[]
    for period in sorted({g['period'] for g in games}):
        current=[g for g in games if g['period']==period]
        for g in current:
            s=schedule.get((period,g['team']));prior=past[g['team']][-8:]
            if s is None or len(prior)<3:
                excluded.append(dict(period=period,team=g['team'],reason='Missing native schedule or three prior team games'));continue
            home=canonical_team(s['home_team']);away=canonical_team(s['away_team'])
            if g['opponent']!= (away if g['team']==home else home):raise ValueError('Schedule/opponent mismatch')
            raw=s['raw_row_json'];total=raw.get('total_line');margin=raw.get('spread_line');clean=period in (202605,202606)
            cutoff=None;market_id=s['raw_nfl_schedule_id'];market_import=clock(s['created_at'])
            if clean:
                from datetime import timedelta
                safe=[]
                for q in quotes[s['game_id']]:
                    decision=clock(q['kickoff_at'])-timedelta(hours=1)
                    if clock(q['observed_at'])<=decision and clock(q['ingested_at'])<=decision:safe.append(q)
                if not safe:
                    excluded.append(dict(period=period,team=g['team'],reason='No original quote at one-hour prelock cutoff'));continue
                q=max(safe,key=lambda q:(clock(q['observed_at']),clock(q['ingested_at']),str(q['market_snapshot_id'])))
                if canonical_team(q['home_team'])!=home or canonical_team(q['away_team'])!=away:raise ValueError('Quote identity mismatch')
                total=float(q['game_total']);margin=-float(q['home_spread']);market_id=str(q['market_snapshot_id']);market_import=clock(q['ingested_at']);cutoff=clock(q['kickoff_at'])-timedelta(hours=1)
            try:total=float(total);margin=float(margin)
            except (ValueError,TypeError):total=None
            if total is None or not math.isfinite(total) or not math.isfinite(margin) or not 20<=total<=80 or abs(margin)>30:
                excluded.append(dict(period=period,team=g['team'],reason='Unknown/invalid intended market'));continue
            ids=[sid for p in prior for sid in p['source_ids']]
            if any(p.get('fg_att') is None for p in prior):
                excluded.append(dict(period=period,team=g['team'],reason='Missing prior FG attempts'));continue
            available=max([market_import,*[imported[sid] for sid in ids]])
            if clean and available>cutoff:
                excluded.append(dict(period=period,team=g['team'],reason='Prior stats unavailable at decision',available_at=available.isoformat(),cutoff=cutoff.isoformat()));continue
            own=(total+(margin if g['team']==home else -margin))/2
            rows.append(dict(period=period,game_id=s['game_id'],team=g['team'],features=[own,total-own,
                sum(p['fg_att'] for p in prior)/len(prior),sum(p['fg_made'] for p in prior)/len(prior),sum(p['pass_tds']+p['rush_tds'] for p in prior)/len(prior)],
                label=min(4,int(g['fg_made'])),prior_classes=[min(4,int(p['fg_made'])) for p in prior],
                feature_source_ids=ids,label_source_ids=g['source_ids'],market_id=market_id,
                available_at=available.isoformat(),label_imported_at=max(imported[sid] for sid in g['source_ids']).isoformat(),
                market_imported_at=market_import.isoformat(),cutoff_at=cutoff.isoformat() if cutoff else None,
                original_input_chronology_verified=clean))
        for g in current:past[g['team']].append(g)
    return rows,excluded


def two_td_probability(weights, capacities, *, deplete=False):
    """Exact probability that two sequential TD events use one actor."""
    if set(weights)!=set(capacities) or any(not math.isfinite(w) or w<0 for w in weights.values()) or any(n<0 or int(n)!=n for n in capacities.values()):
        raise ValueError('Invalid TD weights/capacities')
    active={pid:w for pid,w in weights.items() if capacities[pid]>0 and w>0};total=sum(active.values())
    if total<=0 or sum(capacities[p] for p in active)<2:raise ValueError('Unsupported two-TD opportunity capacity')
    result=0.
    for pid,w in active.items():
        n=capacities[pid]
        if n<2:continue
        remaining=w*(n-1)/n if deplete else w
        denominator=total-w/n if deplete else total
        result+=(w/total)*(remaining/denominator)
    return min(1.,max(0.,result))


def td_rows(history, *, before_period):
    """Conditional diagnostics using realized exposures, prior-only role rates."""
    if any(r['period']>=before_period for r in history):raise ValueError('Future calibration period')
    actors=defaultdict(list);peer=defaultdict(lambda:[0.,0.]);league=defaultdict(lambda:[0.,0.]);out=[];excluded=[]
    channels={'receiving':('receiving_tds','targets','receptions'),'rushing':('rushing_tds','rush_attempts','rush_attempts')}
    def valid(r,num,den):return r.get(num) is not None and r.get(den) is not None and 0<=r[num]<=r[den]
    def rate(r,num,den,period):
        pos=r['position'];key=(pos,num,den);p=peer[key];fallback=p[1]<=0
        if fallback:p=league[(num,den)]
        if p[1]<=0:return None,fallback
        prior=[a for a in actors[(period//100,r['team'],r['player_master_id'] or r['source_player_id'])][-8:] if valid(a,num,den) and a[den]>0]
        return (sum(a[num] for a in prior)+20*p[0]/p[1])/(sum(a[den] for a in prior)+20),fallback
    for period in sorted({r['period'] for r in history}):
        rows=[r for r in history if r['period']==period and r['position']!='K'];teams=defaultdict(list)
        for r in rows:teams[r['team']].append(r)
        for team,group in teams.items():
            for channel,(num,den,capacity) in channels.items():
                if period<202401:continue
                if any(not valid(r,num,den) or not valid(r,num,capacity) for r in group):
                    excluded.append(dict(period=period,team=team,channel=channel,reason='Missing/inconsistent realized TD opportunities'));continue
                if sum(r[num] for r in group)!=2:continue
                if channel=='receiving' and (any(r.get('passing_tds') is None for r in group) or sum(r['passing_tds'] for r in group)!=2):
                    excluded.append(dict(period=period,team=team,channel=channel,reason='Passing/receiving TD mismatch'));continue
                baseline={};candidate={};caps={};fallbacks=0
                for r in group:
                    pid=r['player_master_id'] or r['source_player_id'];a,f1=rate(r,num,den,period);b,f2=rate(r,num,capacity,period);fallbacks+=int(f1 or f2)
                    if a is None or b is None:break
                    baseline[pid]=r[den]*a;candidate[pid]=r[capacity]*b;caps[pid]=r[capacity]
                else:
                    try:p0=two_td_probability(baseline,caps);p1=two_td_probability(candidate,caps,deplete=True)
                    except ValueError:pass
                    else:
                        opponents={r['opponent'] for r in group}
                        if len(opponents)!=1:raise ValueError('Ambiguous TD opponent')
                        out.append(dict(period=period,team=team,game_id=str(period)+':'+':'.join(sorted([team,next(iter(opponents))])),channel=channel,
                            label=int(max(r[num] for r in group)==2),baseline=p0,candidate=p1,position_fallbacks=fallbacks,
                            label_source_ids=[r['source_id'] for r in group],rates_max_period=max((a['period'] for values in actors.values() for a in values),default=0)))
                        continue
                excluded.append(dict(period=period,team=team,channel=channel,reason='No supported prior role rate/capacity'))
        # Update after every team's evaluation: no same-period outcome leakage.
        for r in rows:
            actors[(period//100,r['team'],r['player_master_id'] or r['source_player_id'])].append(r)
            for num,den in {('receiving_tds','targets'),('receiving_tds','receptions'),('rushing_tds','rush_attempts')}:
                if valid(r,num,den) and r[den]>0:
                    for values in [peer[(r['position'],num,den)],league[(num,den)]]:values[0]+=r[num];values[1]+=r[den]
    return out,excluded


def scores(labels, probabilities):
    p=np.asarray(probabilities,float);y=np.asarray(labels,int)
    if p.ndim==1:p=np.column_stack([1-p,p])
    if len(y)==0 or np.any(~np.isfinite(p)) or np.any(p<0) or not np.allclose(p.sum(axis=1),1):raise ValueError('Invalid calibration probabilities')
    loss=-np.log(np.maximum(p[np.arange(len(y)),y],1e-12));brier=np.sum((p-np.eye(p.shape[1])[y])**2,axis=1)
    return dict(rows=len(y),log_loss=float(loss.mean()),brier=float(brier.mean())),loss,brier


def paired_interval(differences, game_ids, seed=17):
    groups=defaultdict(list)
    for gid,value in zip(game_ids,differences):groups[gid].append(value)
    a=np.array([[sum(v),len(v)] for v in groups.values()],float)
    if not len(a):raise ValueError('Empty calibration cohort')
    draws=np.random.default_rng(seed).integers(len(a),size=(1000,len(a)));means=a[draws,0].sum(axis=1)/a[draws,1].sum(axis=1)
    return dict(games=len(a),mean=float(np.mean(differences)),lower=float(np.quantile(means,.025)),upper=float(np.quantile(means,.975)),draws=1000,seed=seed)


def wilson(successes,total):
    if total<=0:return None
    z=1.959963984540054;p=successes/total;d=1+z*z/total;c=(p+z*z/(2*total))/d;h=z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/d
    return [c-h,c+h]
