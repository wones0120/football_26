"""Fixed empirical drive-kernel selection for a research mechanics smoke.

This module does not estimate player roles, optimize parameters, or declare a
complete forecast law when source support is uncertain.
"""
from copy import deepcopy
import math
import numpy as np

VERSION='regulation_drive_empirical_policy_v1'
MIN_CONTEXT_BLOCKS=8


def prior_bin(value,boundaries):
    if value is None:return 'MISSING'
    if type(value)not in(int,float)or not math.isfinite(value)or not 0<=value<=1:raise ValueError('Known prior share must be in [0,1]')
    return int(np.searchsorted(boundaries,value,side='right'))


def fit_prior_bins(contexts):
    """Only unique 2023 native team-game contexts, never block-weighted."""
    seen=set();values={'own':[],'opponent':[]}
    for c in contexts:
        key=c['game_id'],c['team']
        if key in seen:raise ValueError('Unique native team-game contexts required')
        seen.add(key)
        if c['season']!=2023 or not c['game_id'].startswith('2023_'):raise ValueError('Only 2023 TRAIN can define terciles')
        for axis in values:
            value=c[axis+'_pass_share'];prior_bin(value,[0.,1.])
            if value is not None:values[axis].append(value)
    return {axis:np.quantile(v,[1/3,2/3],method='linear').tolist()if v else None for axis,v in values.items()}


def _bins(context,boundaries):
    out=[]
    for axis in('own','opponent'):
        v=context[axis+'_pass_share'];b=boundaries[axis]
        if b is None and v is not None:raise ValueError('No TRAIN boundary support for a known prior share')
        out.append(prior_bin(v,b)if b is not None else'MISSING')
    return tuple(out)


def compile_policy(blocks,contexts,*,unscopable_threats=()):
    """Normalize only the kernel envelope; source decoder owns certification.

    Each block supplies start(field100,phase,half,half_seconds,score_sign),
    context_key=(native game,team), source_season and certified. Unknown starts
    remain explicit threats; known-start uncertified blocks stay in the pool.
    """
    boundaries=fit_prior_bins(contexts);ctx={(c['game_id'],c['team']):c for c in contexts};normalized=[];threats=list(deepcopy(unscopable_threats));ids=set()
    for raw in blocks:
        b=deepcopy(raw)
        if b['block_id']in ids or b['source_season']!=2023 or type(b['certified'])is not bool:raise ValueError('Unique TRAIN source block and explicit certification required')
        ids.add(b['block_id']);s=b['start'];key=tuple(b['context_key'])
        if key not in ctx:raise ValueError('Every block retains a native pregame context')
        b['prior_bins']=_bins(ctx[key],boundaries)
        field=s.get('field100');phase=s.get('phase')
        if type(field)not in(int,float)or not math.isfinite(field)or not 0<=field<=100 or not isinstance(phase,str)or not phase:
            threats.append(dict(block_id=b['block_id'],reason='UNKNOWN_START_PHYSICAL_SUPPORT'));continue
        known=s.get('half')in(1,2)and type(s.get('half_seconds'))in(int,float)and math.isfinite(s['half_seconds'])and 0<=s['half_seconds']<=1800 and s.get('score_sign')in(-1,0,1)
        b['context_known']=known
        if known:b['late']=s['half_seconds']<=120
        normalized.append(b)
    return dict(version=VERSION,blocks=normalized,prior_boundaries=boundaries,unscopable_threats=threats,minimum_context_blocks=MIN_CONTEXT_BLOCKS,interpretation='Empirical sampled trajectories; uncertain support is not a complete calibrated law')


def select_block(policy,state,context,*,arm,uniform):
    """Use generated state only; no observed target state/label parameter."""
    if policy['version']!=VERSION or arm not in('contextual','control')or not 0<=uniform<1:raise ValueError('Fixed kernel/version/arm/uniform required')
    if state['half']not in(1,2)or not 0<state['half_seconds']<=1800 or state['possession_side']not in(0,1):raise ValueError('Valid generated regulation state required')
    if not _valid_generated_scores(state.get('scores')):raise ValueError('Known generated score vector required')
    physical=[b for b in policy['blocks']if b['start']['field100']==state['field100']and b['start']['phase']==state['phase']]
    threats=deepcopy(policy['unscopable_threats'])+[dict(block_id=b['block_id'],reason='UNKNOWN_CONTEXT_MEMBERSHIP_AT_PHYSICAL_SUPPORT')for b in physical if not b['context_known']]
    if not physical:return dict(status='UNSUPPORTED_TRAJECTORY',reason='NO_EXACT_FIELD_PHASE_SUPPORT',selected=None,full_law_known=False,potential_support_threats=threats)
    side=state['possession_side'];delta=state['scores'][side]-state['scores'][1-side];sign=int(delta>0)-int(delta<0);late=state['half_seconds']<=120
    priors=_bins(context,policy['prior_boundaries']);known=[b for b in physical if b['context_known']]
    timed=[b for b in known if b['start']['half']==state['half']and b['late']==late]
    scored=[b for b in timed if b['start']['score_sign']==sign]
    tiers=[('ALL_CONTEXT',[b for b in scored if tuple(b['prior_bins'])==priors]),('DROP_PRIORS',scored),('DROP_SCORE',timed)]
    tier,pool='EXACT_PHYSICAL_ONLY',physical
    if arm=='contextual':
        for name,candidates in tiers:
            if len(candidates)>=MIN_CONTEXT_BLOCKS:tier,pool=name,candidates;break
    else:tier='CONTROL_EXACT_PHYSICAL'
    # Stable source order makes common random uniforms reproducible across arms.
    pool=sorted(pool,key=lambda b:b['block_id']);chosen=pool[min(int(uniform*len(pool)),len(pool)-1)]
    uncertified=sum(not b['certified']for b in pool)
    return dict(status='SELECTED'if chosen['certified']else'UNKNOWN_UNCERTIFIED_SOURCE_BLOCK',selected=deepcopy(chosen),fallback=tier,pool_size=len(pool),uncertified_pool_blocks=uncertified,full_law_known=not threats and uncertified==0,potential_support_threats=threats,generated_score_sign=sign,generated_late=late,prior_bins=list(priors))


def _valid_generated_scores(scores):
    return isinstance(scores,(list,tuple))and len(scores)==2 and all(type(v)in(int,float)and math.isfinite(v)and v>=0 and v==int(v)for v in scores)
