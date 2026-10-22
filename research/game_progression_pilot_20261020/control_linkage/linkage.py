"""Add source timeout/control evidence without changing the v1 ledger or runtime."""
from collections import Counter,defaultdict
from copy import deepcopy
import math,re
from research.game_progression_pilot_20261020.observation_contract.contract import (
    native_key,integer,clock_snapshot,bounded)

VERSION='timeout_control_linkage_v1'
FIELDS=('game_id','play_id','order_sequence','home_team','away_team','qtr','game_half',
    'quarter_seconds_remaining','half_seconds_remaining','game_seconds_remaining','play_type_nfl',
    'play_deleted','replay_or_challenge','replay_or_challenge_result','timeout','timeout_team',
    'home_timeouts_remaining','away_timeouts_remaining','end_clock_time','play_clock','out_of_bounds')

def number(v):return v if type(v)in(int,float)and math.isfinite(v)else None

def flag(v):
    if v is True or number(v)==1:return True
    if v is False or number(v)==0:return False
    return None

def final_row(raw):
    replay=flag(raw.get('replay_or_challenge'));result=raw.get('replay_or_challenge_result')
    return flag(raw.get('play_deleted'))is False and ((replay is False and result in(None,''))or(replay is True and result=='upheld'))

def indexes(rows):
    census=Counter(native_key(r)for r in rows if native_key(r)is not None)
    unique={native_key(r):r for r in rows if native_key(r)is not None and census[native_key(r)]==1}
    grouped=defaultdict(list)
    for raw in rows:
        if isinstance(raw.get('game_id'),str):grouped[raw['game_id']].append(raw)
    previous={};order_ok={}
    for game,group in grouped.items():
        orders=[number(r.get('order_sequence'))for r in group]
        good=None not in orders and len(set(orders))==len(orders)and all(native_key(r)in unique for r in group)
        order_ok[game]=good
        if good:
            ordered=sorted(group,key=lambda r:r['order_sequence'])
            for a,b in zip(ordered,ordered[1:]):previous[native_key(b)]=a
    return census,unique,previous,order_ok

def clock_format(value):
    if value in(None,''):return 'MISSING'
    if isinstance(value,str)and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)',value):return 'WALL_TIMESTAMP'
    if isinstance(value,str)and re.fullmatch(r'(?:0?\d|1[0-5]):[0-5]\d',value):return 'QUARTER_CLOCK_LIKE_UNVALIDATED'
    return 'OTHER_UNVALIDATED'

def timeout_evidence(raw,previous,unique_identity):
    team=raw.get('timeout_team');h,a=raw.get('home_team'),raw.get('away_team')
    teams_ok=all(isinstance(t,str)and t for t in(h,a))and h!=a
    reported=flag(raw.get('timeout'))
    qualified=unique_identity and teams_ok and team in(h,a)and reported is True and final_row(raw)
    status='REPORTED_TEAM_TIMEOUT'if qualified else'NO_TEAM_TIMEOUT_REPORTED'if reported is False and team in(None,'')else'UNKNOWN_OR_CONFLICTING_TIMEOUT'
    after=[bounded(raw.get(f),0,3)for f in ('home_timeouts_remaining','away_timeouts_remaining')]
    before=None;debit=False
    if qualified and previous and final_row(previous):
        p=clock_snapshot(previous);c=clock_snapshot(raw)
        same=(p['status']==c['status']=='SOURCE_PRE_EVENT_VALIDATED'and p['regulation_half']==c['regulation_half']
            and p['half_seconds']>=c['half_seconds']and previous.get('home_team')==h and previous.get('away_team')==a)
        if same:
            before=[bounded(previous.get(f),0,3)for f in ('home_timeouts_remaining','away_timeouts_remaining')]
            if None not in before+after:
                expected=[int(team==h),int(team==a)]
                debit=[b-e for b,e in zip(before,expected)]==after
    return dict(status=status,reported_flag=reported,team=team if qualified else None,
        attachment='DEDICATED_TIMEOUT_EVENT'if raw.get('play_type_nfl')=='TIMEOUT'else'ATTACHED_TO_NATIVE_PLAY',
        observed_budget_snapshot=after,snapshot_timing='AFTER_CURRENT_REPORTED_DEBIT'if reported is True else'NO_CURRENT_REPORTED_DEBIT'if reported is False else'UNKNOWN',
        debit_status='CORROBORATED_SOURCE_BUDGET_DEBIT'if debit else'UNKNOWN_OR_UNCORROBORATED_DEBIT',
        prior_native_id=native_key(previous)if previous else None,prior_budget_snapshot=before,
        generated_timeout_transition_supported=False)

def marker_link(raw,marker,unique):
    out=dict(status='NO_VALIDATED_FROZEN_ADMIN_LINK',kind=raw.get('play_type_nfl'),
        preceding_native_id=None,following_native_id=None,source_event_clock=None,boundary_state=None,
        timeout_stop_event_observed=False,play_end_game_clock=None,restart=None,runoff_enforcement=None)
    if not marker or not final_row(raw)or native_key(raw)not in unique:return out
    proof=marker['proof'];clock=clock_snapshot(raw);boundary=proof.get('boundary_state',{})
    if (not proof.get('certified')or proof.get('kind')!=raw.get('play_type_nfl')
            or clock['status']!='SOURCE_PRE_EVENT_VALIDATED'or boundary.get('half')!=clock['regulation_half']
            or boundary.get('half_seconds_remaining')!=clock['half_seconds']):return out
    game=raw['game_id'];before=proof.get('preceding_score_play_id');after=proof.get('corroborating_next_play_id')
    ids=[game+':'+str(v)for v in(before,after)if v is not None]
    if any(k not in unique for k in ids):return out
    out.update(status='FROZEN_CERTIFIED_ADMIN_LINK',preceding_native_id=game+':'+str(before)if before is not None else None,
        following_native_id=game+':'+str(after)if after is not None else None,
        source_event_clock=clock,boundary_state=deepcopy(boundary))
    # An explicitly typed source timeout clock is not the preceding play's end.
    out['timeout_stop_event_observed']=proof['kind']=='TIMEOUT'
    return out

def enrichment(raw,ordinal,projection_sha,census,unique,previous,order_ok,markers):
    key=native_key(raw);one=key is not None and census.get(key)==1
    timeout=timeout_evidence(raw,previous.get(key)if one else None,one)
    control=marker_link(raw,markers.get(key)if one and order_ok.get(raw.get('game_id'))else None,unique)
    return dict(version=VERSION,source_ordinal_zero_based=ordinal,native_id=key,
        base_record_id=f'clock_timeout_action_observation_v1|{projection_sha}|{ordinal}',
        native_order_verified=bool(order_ok.get(raw.get('game_id'))),unique_native_identity=one,
        raw=deepcopy(raw),timeout_use=timeout,clock_control_link=control,
        end_clock_time_format=clock_format(raw.get('end_clock_time')),
        play_end_game_clock=None,clock_running_state=None,restart_policy=None,
        continuation_supported=False,generated_policy_supported=False)
