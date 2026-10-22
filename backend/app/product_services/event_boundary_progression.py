"""Research renewal-cycle model, not transport of a source game's ending.

An action mark belongs to its observed snap/pre-state. The clock observation is
the wait until the NEXT action, including runoff; it is not action duration.
Native half endings right-censor that wait. A censored wait can prove survival
to a SHORTER generated deadline, never continuation beyond its source followup.
"""
from copy import deepcopy
import math
from .game_progression_runtime import STATS
from .game_progression_policy import fit_prior_bins,prior_bin

VERSION='event_boundary_renewal_v3'

def physical_key(s):
    scrimmage=s.get('phase')=='scrimmage'
    return (s.get('field100'),s.get('phase'),s.get('down')if scrimmage else None,s.get('distance')if scrimmage else None)

class IndexedCycleLibrary(dict):
    """In-memory lookup for a fixed library; rebuild after any source edits.

    Buckets retain every occurrence, source order and unknown certification.
    The JSON library and its recipe version remain unchanged. Source cycles
    are shared, so callers must treat the library as immutable during use.
    """
    def __init__(self,library):
        super().__init__(library)
        buckets={}
        for c in library['cycles']:
            buckets.setdefault(physical_key(c['start']),[]).append(c)
        self.physical_index={key:tuple(pool)for key,pool in buckets.items()}

def index_library(library):
    return library if isinstance(library,IndexedCycleLibrary)else IndexedCycleLibrary(library)

def state(raw):
    return dict(field100=raw['yardline100'],phase=raw['phase'],down=raw['down'],distance=raw['distance'],possession_side=raw['possession_side'],coordinate_system=raw.get('coordinate_system'))

def compile_cycles(reconstruction,blocks,contexts):
    ctx={(c['game_id'],c['team']):c for c in contexts};cycles=[];threats=[]
    patched={r['source_ordinal']:r['event']['production_by_side']for b in blocks['blocks']for r in b['steps']}
    for g in reconstruction['games']:
        if not g['game_id'].startswith('2023_'):raise ValueError('Only TRAIN2023 supplies event cycles')
        for row in g['rows']:
            if row.get('regulation_scope')=='EXPLICIT_OT' or row.get('typed_admin_marker',{}).get('certified'):continue
            before=row['state_before'];off=before['possession_side'];cid=g['game_id']+':'+row['play_id']
            if off not in (0,1) or before['yardline100'] is None:
                threats.append(dict(cycle_id=cid,reason='UNSCOPABLE_NATIVE_ACTION_START'));continue
            key=(g['game_id'],g['sides'][off])
            if key not in ctx:raise ValueError('Every TRAIN action retains its prior-only context')
            endpoint=row.get('transition_endpoint');wait=row.get('transition_elapsed_seconds');boundary=endpoint and endpoint['phase']in('halftime','regulation_end')
            production=deepcopy(patched.get(row['source_ordinal'],row['event']['production_by_side']))
            cycles.append(dict(cycle_id=cid,source_season=2023,context_key=list(key),start=dict(state(before),half=before['half'],remaining=before['half_seconds_remaining'],score_sign=(int(before['scores'][off]>before['scores'][1-off])-int(before['scores'][off]<before['scores'][1-off]))if None not in before['scores']else None),
                source_side=off,state_certified=row['state_transition_certified'],barriers=deepcopy(row['state_transition_barriers']),source_transition_proofs=deepcopy(row.get('source_transition_proofs',[])),production=production,score_delta=deepcopy(row['event']['score_delta']),points_by_type=deepcopy(row['event']['points_by_type']),
                touchdown=_true(row['raw'].get('touchdown')),wait=dict(kind='RIGHT_CENSORED'if boundary else'EXACT_NEXT_ACTION',seconds=wait),endpoint=state(endpoint)if endpoint else None))
    for q in reconstruction['quarantine']:
        if q['threat']!='EXPLICIT_OUT_OF_SCOPE':threats.append(dict(source_ordinal=q['source_ordinal'],reason=q['threat']))
    boundaries=fit_prior_bins(contexts)
    for c in cycles:
        c['prior_bins']=[prior_bin(ctx[tuple(c['context_key'])][a+'_pass_share'],boundaries[a]) for a in ('own','opponent')]
    return dict(version=VERSION,cycles=cycles,threats=threats,boundaries=boundaries,source_marker_exclusions=deepcopy(blocks['deterministic_admin_markers']),explicit_OT_exclusions=deepcopy(blocks['explicit_overtime_rows']))

def _true(v):return v is True or v in (1,'1','1.0','true')

def choose(library,s,context,arm,u):
    if library['version']!=VERSION or arm not in('contextual','control')or not 0<=u<1:raise ValueError('Fixed event recipe/arm/uniform required')
    pool=library.physical_index.get(physical_key(s),())if isinstance(library,IndexedCycleLibrary)else[c for c in library['cycles']if physical_key(c['start'])==physical_key(s)]
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

def transfer(c,s):
    """No source absolute score, source end-half type, or clock clamp copied."""
    if not c['state_certified']:return dict(status='UNKNOWN_SOURCE_STATE',state=s,unknown_detail=dict(cycle_id=c.get('cycle_id'),source_barriers=list(c.get('barriers',[])),resolution='SOURCE_EVIDENCE_REQUIRED'))
    if physical_key(c['start'])!=physical_key(s):raise ValueError('Exact event physical support required')
    wait=c.get('wait');r=s['remaining']
    if not isinstance(wait,dict) or wait.get('kind') not in ('EXACT_NEXT_ACTION','RIGHT_CENSORED'):
        return dict(status='UNKNOWN_WAIT_OBSERVATION_KIND',state=s)
    w=wait.get('seconds')
    if type(w)not in(int,float) or not math.isfinite(w)or w<0:return dict(status='UNKNOWN_NEXT_ACTION_WAIT',state=s)
    mapping={c['source_side']:s['possession_side'],1-c['source_side']:1-s['possession_side']}
    new=deepcopy(s);credits=[dict.fromkeys(STATS)for _ in (0,1)]
    if c['score_delta']is None:return dict(status='UNKNOWN_EVENT_SCORE',state=s)
    for side in (0,1):
        values=c['production'][side]
        if set(values)!=set(STATS):raise ValueError('Exact per-channel source contract required')
        for field,value in values.items():
            if value is not None and (type(value)not in(int,float)or not math.isfinite(value)or field not in('passing_yards','receiving_yards','rushing_yards')and(value<0 or value!=int(value))):raise ValueError('Malformed source production')
        if all(values[f]is not None for f in ('official_targets','official_pass_attempts'))and values['official_targets']>values['official_pass_attempts']:raise ValueError('Targets exceed attempts')
        if sum(c['points_by_type'][side].values())!=c['score_delta'][side]:raise ValueError('Typed points disagree with score change')
    for side,target in mapping.items():
        new['scores'][target]+=c['score_delta'][side];credits[target]=deepcopy(c['production'][side])
    endpoint=c['endpoint']
    if r==0 and s['phase']!='try':return dict(status='UNKNOWN_UNTIMED_ACTION',state=s)
    # RIGHT_CENSORED means no successor was observed before its source deadline.
    # It cannot invent a successor during a longer generated followup window.
    if wait['kind']=='RIGHT_CENSORED' and r>w:
        return dict(status='UNKNOWN_CENSORED_SUCCESSOR',state=new,credits=credits,
            unknown_detail=dict(cycle_id=c.get('cycle_id'),source_followup_seconds=w,generated_deadline_seconds=r,
                unobserved_followup_seconds=r-w,wait_lower_bound_seconds=w,successor_observed=False,
                action_marks_credited_once=True,resolution='CONDITIONAL_WAIT_AND_SUCCESSOR_MODEL_OR_ADDITIONAL_OBSERVATIONS_REQUIRED'))
    if w>=r or r==0:
        if c['touchdown'] and s['phase']!='try':
            if not endpoint or endpoint['phase']!='try':return dict(status='UNKNOWN_REQUIRED_UNTIMED_TRY',state=new,credits=credits)
            new.update(endpoint,possession_side=mapping[endpoint['possession_side']],remaining=0)
        else:
            new.update(remaining=0,phase='halftime'if s['half']==1 else'regulation_end',field100=None,down=None,distance=None,possession_side=None)
        return dict(status='TRANSFERRED',state=new,credits=credits,clock_basis='NO_SUCCESSOR_BEFORE_GENERATED_DEADLINE;ACTION_MARK_AT_OBSERVED_SNAP')
    if not endpoint or endpoint['possession_side']not in(0,1)or endpoint['field100']is None:return dict(status='UNKNOWN_SUCCESSOR_STATE',state=new,credits=credits)
    new.update(endpoint,possession_side=mapping[endpoint['possession_side']],remaining=r-w)
    return dict(status='TRANSFERRED',state=new,credits=credits,clock_basis='EXACT_NEXT_ACTION_GAME_CLOCK_WAIT')

def rollout(library,openings,contexts,uniforms,arm,deadline,clock):
    library=index_library(library)
    stream=iter(uniforms);trace=[];totals=[dict.fromkeys(STATS,0)for _ in (0,1)];known_sums=deepcopy(totals);s=None
    full=not library['threats'] and all(o['certified']for o in openings)
    def result(status):return dict(status=status,state=s,team_stats=totals,known_sums=known_sums,trace=trace,full_law_known=full and status=='COMPLETE_REGULATION',scope='RESEARCH_RECONSTRUCTED_EVENT_RENEWAL;NOT_PLAYER_FORECAST',activation=False)
    try:
        if not openings:return result('UNSUPPORTED_SOURCE_OPENING')
        opening=sorted(openings,key=lambda o:o['opening_id'])[min(int(next(stream)*len(openings)),len(openings)-1)]
        if not opening['certified']:return result('UNKNOWN_SOURCE_OPENING')
        for half,k in ((1,'first_half'),(2,'second_half')):
            s=dict(opening[k],down=None,distance=None,half=half,remaining=1800,scores=[0,0]if s is None else s['scores'])
            while s['remaining']>0 or s['phase']=='try':
                if clock()>=deadline:return result('INCOMPLETE_TIME_CAP')
                if len(trace)>=400:return result('INCOMPLETE_EVENT_CAP')
                c,tier,n,unknown=choose(library,s,contexts[s['possession_side']],arm,next(stream))
                trace.append(dict(cycle_id=c['cycle_id']if c else None,tier=tier,pool_size=n,unknown_state_pool=unknown,pre_remaining=s['remaining']))
                full=full and unknown==0
                if c is None:return result('UNSUPPORTED_EVENT_STATE')
                out=transfer(c,s);s=out['state'];trace[-1].update(status=out['status'],clock_basis=out.get('clock_basis'))
                if 'unknown_detail'in out:trace[-1]['unknown_detail']=out['unknown_detail']
                if 'credits'in out:
                    for side in (0,1):
                        for field,value in out['credits'][side].items():
                            if value is None:totals[side][field]=None;full=False
                            else:
                                known_sums[side][field]+=value
                                if totals[side][field]is not None:totals[side][field]+=value
                if out['status']!='TRANSFERRED':return result(out['status'])
        return result('COMPLETE_REGULATION')
    except StopIteration:return result('INCOMPLETE_UNIFORM_STREAM')
