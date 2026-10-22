"""Partial historical observation contract; never a generated-state transition."""
from collections import Counter
from copy import deepcopy
import math
import re

VERSION='clock_timeout_action_observation_v1'
CLOCK_FIELDS=('qtr','game_half','quarter_seconds_remaining','half_seconds_remaining','game_seconds_remaining')
ACTION_FIELDS=('play_type','play_type_nfl','play_deleted','no_play','penalty','replay_or_challenge',
    'replay_or_challenge_result','aborted_play','qb_kneel','qb_spike','qb_scramble','sack','pass_attempt',
    'rush_attempt','punt_attempt','kickoff_attempt','field_goal_attempt','extra_point_attempt','two_point_attempt',
    'passer_player_id','rusher_player_id','receiver_player_id','punter_player_id','kicker_player_id')
PRE_FIELDS=(*CLOCK_FIELDS,'season','week','season_type','home_team','away_team','posteam','defteam',
    'order_sequence','down','ydstogo','yardline_100','posteam_score','defteam_score',
    'home_timeouts_remaining','away_timeouts_remaining')
MISSING_OBSERVATIONS={
    'play_end':'Native play-end clock, terminal possession/field and enforcement bound independently of the next snap.',
    'clock_control':'Running/stopped cause, restart, runoff and correction events bound to native actions.',
    'timeout_use':'Native timeout event/team, pre/post budget and enforcement; pre-event counts alone are insufficient.',
    'untimed_action':'Explicit adjudication of required untimed action after enforcement.',
    'successor_native_identity':'General unique next-action native linkage; compiled endpoints have no general native successor ID.',
    'generated_policy':'Supported generated timeout evolution and clock-conditioned action policy, separately validated.'}

def integer(value):
    # Preserve source bytes separately; accept finite integral JSON numbers only.
    return int(value)if type(value)in(int,float)and math.isfinite(value)and value==int(value)else None

def bounded(value,low,high):
    n=integer(value)
    return n if n is not None and low<=n<=high else None

def native_key(raw):
    game=raw.get('game_id');play=integer(raw.get('play_id'))
    if not isinstance(game,str)or not game.strip()or play is None or play<0:return None
    return game+':'+str(play)

def clock_snapshot(raw):
    q=integer(raw.get('qtr'));quarter=bounded(raw.get('quarter_seconds_remaining'),0,900)
    half=bounded(raw.get('half_seconds_remaining'),0,1800);game=bounded(raw.get('game_seconds_remaining'),0,3600)
    if q is not None and q>4:return dict(status='EXPLICIT_OVERTIME',quarter=q,regulation_half=None,quarter_seconds=None,half_seconds=None,game_seconds=None)
    h=1 if q in(1,2)else 2 if q in(3,4)else None
    known=(h is not None and quarter is not None and half is not None and game is not None
        and raw.get('game_half')==f'Half{h}'and half==quarter+(900 if q in(1,3)else 0)
        and game==half+(1800 if h==1 else 0))
    return dict(status='SOURCE_PRE_EVENT_VALIDATED'if known else'UNKNOWN_OR_CONFLICTING_CLOCK',
        quarter=q,regulation_half=h,quarter_seconds=quarter if known else None,
        half_seconds=half if known else None,game_seconds=game if known else None)

def timeout_snapshot(raw):
    home=bounded(raw.get('home_timeouts_remaining'),0,3);away=bounded(raw.get('away_timeouts_remaining'),0,3)
    h,a=raw.get('home_team'),raw.get('away_team');off,defense=raw.get('posteam'),raw.get('defteam')
    teams_ok=all(isinstance(t,str)and t.strip()for t in (h,a))and h!=a
    oriented=teams_ok and off in(h,a)and defense in(h,a)and off!=defense
    values={h:home,a:away}if teams_ok else{}
    return dict(status='SOURCE_PRE_EVENT_VALIDATED'if teams_ok and home is not None and away is not None else'UNKNOWN_OR_INVALID_TIMEOUT_SNAPSHOT',
        home=home,away=away,team_orientation_known=bool(oriented),
        offense=values[off]if oriented else None,defense=values[defense]if oriented else None,
        timeout_use_proven=False,generated_budget_transition_supported=False)

def record(raw,ordinal,projection_sha256,identity_counts,cycle_by_id):
    key=native_key(raw);matches=identity_counts.get(key,0)if key else 0
    cycle=cycle_by_id.get(key)if key and matches==1 else None
    link='MISSING_NATIVE_IDENTITY'if key is None else'AMBIGUOUS_NATIVE_IDENTITY'if matches!=1 else'UNIQUE_CYCLE_MATCH'if cycle else'NO_COMPILED_CYCLE'
    kind='CONTROL'if raw.get('play_type_nfl')in('TIMEOUT','GAME_START','END_QUARTER','END_GAME')or raw.get('play_type')in('time_out','quarter_end')else'ACTION'if cycle else'UNCLASSIFIED_SOURCE_ROW'
    timeouts=timeout_snapshot(raw);off_score=integer(raw.get('posteam_score'));def_score=integer(raw.get('defteam_score'))
    if off_score is not None and off_score<0:off_score=None
    if def_score is not None and def_score<0:def_score=None
    score_known=timeouts['team_orientation_known']and off_score is not None and def_score is not None
    action='UNKNOWN'
    for flag in ('qb_kneel','qb_spike','qb_scramble','sack'):
        if raw.get(flag)is True or integer(raw.get(flag))==1:action=flag;break
    else:action=raw.get('play_type')or'UNKNOWN'
    followup=dict(status='NO_UNIQUE_COMPILED_CYCLE',wait=None,next_action_or_boundary_state=None,
        next_action_native_id=None,next_action_identity_status='UNKNOWN',joint_marks=None,
        source_state_certified=None,source_barriers=None)
    if cycle:
        followup.update(status='FROZEN_SOURCE_INTERVAL',cycle_id=key,wait=deepcopy(cycle['wait']),
            source_context_key=deepcopy(cycle['context_key']),
            next_action_or_boundary_state=deepcopy(cycle['endpoint']),
            joint_marks=deepcopy({k:cycle[k]for k in ('production','score_delta','points_by_type','source_side','touchdown')}),
            source_state_certified=cycle['state_certified'],source_barriers=deepcopy(cycle['barriers']))
    return dict(version=VERSION,record_id=f'{VERSION}|{projection_sha256}|{ordinal}',
        provenance=dict(projection_sha256=projection_sha256,source_ordinal_zero_based=ordinal,native_cycle_id=key,
            identity_status=link,original_pregame_availability_proven=False),
        row_kind=kind,raw_pre_event={f:raw.get(f)for f in PRE_FIELDS if f in raw},
        observed_action=dict(kind=action,raw={f:raw[f]for f in ACTION_FIELDS if f in raw},
            policy_probability=None,policy_support='OBSERVED_SOURCE_ACTION_ONLY'),
        pre_event=dict(clock=clock_snapshot(raw),timeouts=timeouts,
            score=dict(status='SOURCE_PRE_EVENT_VALIDATED'if score_known else'UNKNOWN_OR_UNORIENTED_SCORE',
                offense=off_score if score_known else None,defense=def_score if score_known else None,
                differential=off_score-def_score if score_known else None)),
        play_end=dict(status='UNKNOWN_NOT_BOUND',clock=None,possession=None,field100=None,enforcement=None),
        clock_control=dict(status='UNKNOWN_NOT_BOUND',running=None,stopped_reason=None,restart=None,runoff=None,
            timeout_team=None,timeout_use=None,correction=None,untimed_action_required=None),
        followup=followup,continuation_support='UNKNOWN',generated_policy_supported=False)

def identity_census(rows):return Counter(native_key(r)for r in rows if native_key(r)is not None)

def validate_record(row,ordinal,projection_sha256):
    if row['version']!=VERSION or row['record_id']!=f'{VERSION}|{projection_sha256}|{ordinal}':raise ValueError('Bound ordered record identity required')
    if not re.fullmatch('[0-9a-f]{64}',projection_sha256):raise ValueError('Projection SHA256 required')
    if row['play_end']['status']!='UNKNOWN_NOT_BOUND'or row['clock_control']['status']!='UNKNOWN_NOT_BOUND':raise ValueError('No terminal/enforcement evidence supplied by this adapter')
    if any(v is not None for k,v in row['play_end'].items()if k!='status')or any(v is not None for k,v in row['clock_control'].items()if k!='status'):raise ValueError('Unbound terminal/control fields must stay unknown')
    if row['generated_policy_supported']or row['continuation_support']!='UNKNOWN':raise ValueError('Observations cannot establish generated policy')
