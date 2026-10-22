"""Frozen v3 scan selector for SCENARIO-01 parity; never used by production."""
from backend.app.product_services.event_boundary_progression import VERSION,physical_key
from backend.app.product_services.game_progression_policy import prior_bin

def choose(library,s,context,arm,u):
    if library['version']!=VERSION or arm not in('contextual','control')or not 0<=u<1:raise ValueError('Fixed event recipe/arm/uniform required')
    pool=[c for c in library['cycles']if physical_key(c['start'])==physical_key(s)]
    if not pool:return None,'NO_EXACT_EVENT_STATE_SUPPORT',0,0
    timed=[c for c in pool if c['start']['half']==s['half'] and c['start']['remaining'] is not None and (c['start']['remaining']<=120)==(s['remaining']<=120)]
    delta=s['scores'][s['possession_side']]-s['scores'][1-s['possession_side']];sign=int(delta>0)-int(delta<0)
    scored=[c for c in timed if c['start']['score_sign']==sign]
    bins=[prior_bin(context[a+'_pass_share'],library['boundaries'][a])for a in ('own','opponent')]
    tier='EXACT_PHYSICAL_CONTROL'if arm=='control'else'EXACT_PHYSICAL_FALLBACK'
    if arm=='contextual':
        for name,p in [('ALL_CONTEXT',[c for c in scored if c['prior_bins']==bins]),('DROP_PRIORS',scored),('DROP_SCORE',timed)]:
            if len(p)>=8:pool=p;tier=name;break
    pool=sorted(pool,key=lambda c:c['cycle_id']);unknown=sum(not c['state_certified']for c in pool)
    return pool[min(int(u*len(pool)),len(pool)-1)],tier,len(pool),unknown
