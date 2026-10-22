"""Read-only exploratory evidence counts; no continuation sampling or imputation."""
from collections import Counter
import json
import math
from backend.app.product_services.event_boundary_progression import physical_key

ACTION_FLAGS=('qb_kneel','qb_spike','qb_scramble','sack','pass_attempt','rush_attempt',
              'punt_attempt','kickoff_attempt','field_goal_attempt','extra_point_attempt','two_point_attempt')

def finite(value):return type(value)in(int,float)and math.isfinite(value)

def action_kind(raw):
    for name in ('qb_kneel','qb_spike','qb_scramble','sack'):
        if raw.get(name)in(1,'1','1.0',True):return name
    return raw.get('play_type')or'UNKNOWN'

def joint_key(cycle,raw):
    """Preserve both sides' observed marks without matching actor identities."""
    off=cycle['source_side'];order=(off,1-off)
    marks=dict(production=[cycle['production'][s]for s in order],
               score_delta=[cycle['score_delta'][s]for s in order]if cycle['score_delta']is not None else None,
               points=[cycle['points_by_type'][s]for s in order],touchdown=cycle['touchdown'],
               native_class=raw.get('play_type_nfl'),flags={f:raw.get(f)for f in ACTION_FLAGS})
    return physical_key(cycle['start']),json.dumps(marks,sort_keys=True,separators=(',',':'),allow_nan=False)

def observation_counts(cycles,censor,deadline):
    counts=Counter();games=set()
    for c in cycles:
        counts['all_observations']+=1
        counts['certified'if c['state_certified']else'unknown_source']+=1
        kind=c['wait']['kind'];w=c['wait']['seconds']
        counts[kind]+=1
        if not finite(w)or w<0:counts['invalid_wait']+=1;continue
        if kind=='EXACT_NEXT_ACTION'and w>censor:
            counts['exact_wait_beyond_censor']+=1;games.add(c['context_key'][0])
            if not c['state_certified']:counts['unknown_source_exact_beyond_censor']+=1
        if kind=='EXACT_NEXT_ACTION'and w>=deadline:counts['exact_wait_at_least_deadline']+=1
    return dict(counts=dict(counts),distinct_games_beyond_censor=len(games))

def diagnose(cycle,pool,deadline):
    censor=cycle['wait']['seconds'];source_remaining=cycle['start']['remaining']
    if (cycle['wait']['kind']!='RIGHT_CENSORED'or not finite(censor)or censor<0
            or not finite(deadline)or deadline<=censor):raise ValueError('Strictly longer generated horizon required')
    # Same-game observations are not independent evidence for a stopped source.
    external=[c for c in pool if c['context_key'][0]!=cycle['context_key'][0]]
    contextual=[c for c in external if c['start']['half']==cycle['start']['half']
                and c['start']['score_sign']==cycle['start']['score_sign']]
    horizon=[c for c in contextual if finite(c['start']['remaining'])and c['start']['remaining']>=deadline]
    return dict(source_followup_seconds=censor,generated_deadline_seconds=deadline,unobserved_seconds=deadline-censor,
        source_remaining_seconds=source_remaining,
        crosses_120_second_stratum=(source_remaining<=120)!=(deadline<=120)if finite(source_remaining)else None,
        same_joint_marks_other_games=observation_counts(external,censor,deadline),
        same_half_score_sign=observation_counts(contextual,censor,deadline),
        source_start_covers_generated_horizon=observation_counts(horizon,censor,deadline),
        continuation_supported=False,reason='JOINT_TERMINAL_CLOCK_TIMEOUT_AND_POLICY_EVIDENCE_NOT_ESTABLISHED')
