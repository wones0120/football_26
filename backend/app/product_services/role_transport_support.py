"""Pregame opportunity composition for paired-game analog research only."""
import math
import statistics
from .scenario_allocation import measurement,team

ROLE_CHANNELS=[('WR','targets',3),('TE','targets',2),('RB','targets',2),('RB','carries',2)]


def denominator(row,channel):
    item=(row.get('workload_evidence')or{}).get('team_volume_proxies',{}).get('team_'+channel+'_mean_3',{})
    value=item.get('value')
    if item.get('status')in{'unavailable','after_cutoff','coverage_unknown'}or type(value)not in(int,float)or not math.isfinite(value)or value<=0:return None
    return float(value)


def current_vectors(full_rows,universe):
    result={}
    for t in sorted({team(r)for r in full_rows}):
        volumes={}
        for channel in ['targets','carries']:
            values=[v for r in full_rows if team(r)==t and (v:=denominator(r,channel))is not None]
            if not values or max(values)-min(values)>1e-6:raise ValueError('Missing or conflicting team workload denominator')
            volumes[channel]=values[0]
        vector=[]
        for pos,channel,n in ROLE_CHANNELS:
            roles=universe.get((t,pos),[])[:n]
            if len(roles)<n:raise ValueError('Insufficient supported current role ranks; cannot zero unknown roles')
            for row,_,_ in roles:
                value,_=measurement(row,channel)
                if value is None:raise ValueError('Unknown role-channel share')
                vector.append(value/volumes[channel])
        result[t]=vector
    return result


def historical_vector(side):
    vector=[]
    for pos,channel,n in ROLE_CHANNELS:
        roles=sorted((p for p in side['players']if p['position']==pos),key=lambda p:(-(p['prior']['targets']+p['prior']['carries']if pos=='RB'else p['prior']['targets']),p['source_player_id']))
        volume=side['prior_team_volume'][channel]
        if not math.isfinite(volume)or volume<=0:raise ValueError('Unknown historical team denominator')
        # The prior three complete team-game sources establish zero credited
        # production for absent role ranks; this is not missing current workload.
        vector += [roles[i]['prior'][channel]/volume if i<len(roles)else 0. for i in range(n)]
    return vector


def scale_vectors(vectors):
    return [statistics.pstdev(v[j]for v in vectors)or 1. for j in range(len(vectors[0]))]


def role_distance(source,target,scales):
    if not(len(source)==len(target)==len(scales))or not source:raise ValueError('Role feature contract mismatch')
    return sum(((s-t)/scale)**2 for s,t,scale in zip(source,target,scales))/len(source)
