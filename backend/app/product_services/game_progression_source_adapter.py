"""Lossless native-source to research runtime envelope; no source I/O."""
from collections import defaultdict
from copy import deepcopy
import math
from .game_progression_runtime import STATS,POINTS

VERSION='native_drive_runtime_adapter_v2'
POINT_NAMES={'pass_touchdown':'pass_td','rush_touchdown':'rush_td','return_touchdown':'return_td','field_goal':'field_goal','extra_point':'extra_point','two_point':'two_point','defensive_try':'two_point','safety':'safety'}


def prior_contexts(team_contexts):
    """Exact source-observed prior3 official P/(P+R); unknown stays missing."""
    out=[];seen=set()
    for row in team_contexts:
        if row['period']//100!=2023:continue
        key=row['game_id'],row['team']
        if key in seen:raise ValueError('Unique TRAIN pregame context required')
        seen.add(key);c=dict(game_id=key[0],team=key[1],season=2023)
        for axis in('own','opponent'):
            window=row['windows'][axis]
            if any(p//100!=2023 or p>=row['period']for p in window['periods']):raise ValueError('Prior context leaks target/year')
            P=row['features']['weekly3_'+axis+'_pass_attempts_mean'];R=row['features']['weekly3_'+axis+'_rush_attempts_mean']
            known=len(window['game_ids'])==3 and len(window['periods'])==3 and all(type(x)in(int,float)and math.isfinite(x)and x>=0 for x in(P,R))
            c[axis+'_pass_share']=P/(P+R)if known and P+R>0 else None
        out.append(c)
    return out


def _start(raw):
    out=dict(possession_side=raw['possession_side'],field100=raw['yardline100'],phase=raw['phase'])
    if 'coordinate_system'in raw:out['coordinate_system']=raw['coordinate_system']
    return out


def _points(raw):
    out={}
    for name,value in raw.items():
        if name not in POINT_NAMES:raise ValueError('Unsupported source scoring type retained as unknown')
        normalized=POINT_NAMES[name];unit=POINTS[normalized]
        if type(value)not in(int,float)or value not in(0,unit)or normalized in out:raise ValueError('Unproven source scoring units/duplicate type')
        out[normalized]=int(value/unit)
    return out


def adapt_library(block_receipt,opening_evidence,contexts,*,train_quarantine_rows=()):
    if block_receipt['version']!='original_drive_trajectory_blocks_v1':raise ValueError('Exact source block contract required')
    normalized=[];threats=[dict(source_ordinal=q['source_ordinal'],reason='POSSIBLE_TRAIN_REG_QUARANTINE',source_threat=q['threat'])for q in train_quarantine_rows if q['threat']!='EXPLICIT_OUT_OF_SCOPE'];coverage=[];ctx={(r['game_id'],r['team']):r for r in contexts};excluded=[];marker_ids=set()
    transferred_markers=set()
    for block in block_receipt['blocks']:
        for row in block['steps']:
            bridge=row.get('deterministic_clock_bridge')
            if bridge and bridge.get('observed_runoff_preserved')is True and bridge.get('zero_football_events')is True:
                transferred_markers.update((block['game_id'],str(p))for p in bridge.get('marker_play_ids',[]))
    for marker in block_receipt.get('deterministic_admin_markers',[]):
        if not marker['game_id'].startswith('2023_'):continue
        p=marker['proof'];key=marker['game_id'],str(marker['play_id'])
        required=('certified','zero_official_counts','zero_physical_plays','zero_event_points','raw_state_not_filled','deterministic_admin_marker_exclusion')
        if key in marker_ids or p.get('kind')not in('GAME_START','TIMEOUT','END_QUARTER','END_GAME')or any(p.get(k)is not True for k in required):raise ValueError('Explicit unique source-certified deterministic marker proof required')
        if p.get('zero_event_seconds')is True:
            if p.get('observed_runoff_seconds',0)!=0:raise ValueError('Zero-duration marker contradicts observed runoff')
        else:
            runoff=p.get('observed_runoff_seconds')
            if p.get('zero_event_seconds')is not False or p.get('elapsed_transfer_certified')is not True or type(runoff)not in(int,float)or not math.isfinite(runoff)or runoff<=0:raise ValueError('Nonzero marker runoff needs explicit source transfer proof')
            if key not in transferred_markers:raise ValueError('Excluded nonzero marker runoff must be in a retained trajectory bridge')
        marker_ids.add(key);excluded.append(deepcopy(marker))
    for raw in block_receipt['blocks']:
        gid=raw['game_id']
        if not gid.startswith('2023_'):continue
        bid=gid+'|'+str(raw['block_ordinal']);s=raw['start_state'];off=s['possession_side'];support=raw['physical_start_support']
        if any(s[k]!=support[v]for k,v in [('possession_side','possession_side'),('yardline100','yardline100'),('phase','phase'),('half','half')]):raise ValueError('Source physical support disagrees with native start')
        if type(off)is not int or off not in(0,1):
            threats.append(dict(block_id=bid,reason='UNSCOPED_START_POSSESSION'));coverage.append(dict(block_id=bid,status='UNSCOPABLE_THREAT'));continue
        key=gid,raw['source_sides'][off]
        if key not in ctx:raise ValueError('Every TRAIN source block must retain a prior-only context')
        scores=s['scores'];sign=None
        if len(scores)==2 and all(type(v)in(int,float)and math.isfinite(v)and v>=0 for v in scores):sign=int(scores[off]>scores[1-off])-int(scores[off]<scores[1-off])
        b=dict(block_id=bid,source_season=2023,context_key=list(key),certified=raw['certified'],start_possession_side=off,start=dict(field100=s['yardline100'],phase=s['phase']if s['phase']!='unknown'else None,half=s['half'],half_seconds=s['half_seconds_remaining'],score_sign=sign),duration_seconds=raw['elapsed_seconds'],terminal=_start(raw['terminal_state'])if raw['terminal_state']is not None else{},steps=[],boundary_prefixes=[],source_barriers=deepcopy(raw['barriers']))
        b['start']['coordinate_system']=s.get('coordinate_system')
        b['source_state_transition_certified']=raw.get('state_transition_certified')
        b['source_per_channel_totals']=deepcopy(raw.get('per_channel_totals'))
        b['source_drive_endpoint_proofs']=deepcopy(raw.get('source_drive_endpoint_proofs'))
        problems=[]
        for row in raw['steps']:
            if (gid,str(row['play_id']))in marker_ids:raise ValueError('Deterministic marker cannot also be a stochastic event')
            e=row['event'];stats=e.get('production_by_side')
            try:
                if not isinstance(stats,list)or len(stats)!=2 or any(set(v)!=set(STATS)or any(x is None for x in v.values())for v in stats):raise ValueError('Unknown explicit production credits')
                points=[_points(p)for p in e['points_by_type']]
            except (KeyError,ValueError,TypeError)as error:
                problems.append(str(error));stats=deepcopy(stats);points=None
            b['steps'].append(dict(row_id=gid+':'+str(row['play_id']),elapsed_seconds=row['cumulative_elapsed_endpoint'],score_delta=deepcopy(e['score_delta']),team_stats=deepcopy(stats),points_by_type=points,source_transition_endpoint=deepcopy(row.get('certified_endpoint')),source_clock_bridge=deepcopy(row.get('deterministic_clock_bridge')),source_channel_credit_masks=deepcopy(row.get('channel_credit_masks'))))
        ids=[r['play_id']for r in raw['steps']]
        for prefix in raw['certified_prefixes']:
            endpoint=prefix['terminal_state'];through=prefix['through_play_id']
            if endpoint is None or ids.count(through)!=1:continue
            count=ids.index(through)+1
            if b['steps'][count-1]['elapsed_seconds']!=prefix['elapsed_seconds']:raise ValueError('Source prefix does not match certified row endpoint')
            b['boundary_prefixes'].append(dict(elapsed_seconds=prefix['elapsed_seconds'],steps_count=count,certified=True,half_end=endpoint['phase']in('halftime','regulation_end'),terminal_phase=endpoint['phase']))
        if problems:b['certified']=False;b['source_barriers']+=problems
        normalized.append(b);coverage.append(dict(block_id=bid,status='CERTIFIED'if b['certified']else'UNCERTIFIED_RETAINED',adapter_barriers=problems))
    pairs=defaultdict(dict)
    for o in opening_evidence:
        if o['source_season']!=2023:continue
        if o['source_half']in pairs[o['game_id']]:raise ValueError('Duplicate native game-half opening')
        pairs[o['game_id']][o['source_half']]=o
    openings=[]
    for gid,pair in sorted(pairs.items()):
        o=dict(opening_id=gid,source_season=2023,certified=set(pair)=={1,2}and all(p['certified']for p in pair.values()))
        for half,key in((1,'first_half'),(2,'second_half')):
            p=pair.get(half);o[key]=_start(p['start_state'])if p is not None and p['start_state']is not None else None
        openings.append(o)
    return dict(version=VERSION,blocks=normalized,openings=openings,unscopable_threats=threats,normalization_coverage=coverage,deterministic_exclusion_ledger=excluded,explicit_overtime_exclusion_ledger=deepcopy(block_receipt.get('explicit_overtime_rows',[])),contexts=deepcopy(contexts),unknown_mass='PRESERVED_NOT_RENORMALIZED;ONLY_SOURCE_CERTIFIED_ADMIN_MARKERS_AND_EXPLICIT_OT_EXCLUDED_FROM_REGULATION',optimizer_calls=0,activation=False)
