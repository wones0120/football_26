"""Research-only regulation trajectory decoder; no default probabilities.

The source adapter supplies certified row boundaries and typed credits. Unknown
support terminates the path; partial paths never become full-game forecasts.
"""
from copy import deepcopy
import math
import time
import hashlib
import numpy as np
from .game_progression_policy import select_block
from backend.app.services.simulation import calculate_dk_points

VERSION='regulation_drive_progression_smoke_v1'
STATS=('official_pass_attempts','official_carries','official_targets','physical_plays','passing_yards','receiving_yards','rushing_yards','passing_TD','receiving_TD','rushing_TD','possessions')
COUNTS=set(STATS)-{'passing_yards','receiving_yards','rushing_yards'}
POINTS={'pass_td':6,'rush_td':6,'return_td':6,'field_goal':3,'extra_point':1,'two_point':2,'safety':2}
DK_FIELDS=('passing_yards','passing_tds','passing_interceptions','rushing_yards','rushing_tds','receptions','receiving_yards','receiving_tds','fumbles_lost','passing_2pt_conversions','rushing_2pt_conversions','receiving_2pt_conversions','kickoff_return_tds','punt_return_tds')


def _number(x):return type(x)in(int,float)and math.isfinite(x)


def _start(value):
    if value.get('possession_side')not in(0,1)or not _number(value.get('field100'))or not 0<=value['field100']<=100 or not isinstance(value.get('phase'),str)or not value['phase']:
        raise ValueError('Certified source side/field/phase required')
    return {k:value[k]for k in('possession_side','field100','phase')}


def _credits(step):
    if len(step['team_stats'])!=2 or len(step['score_delta'])!=2 or len(step['points_by_type'])!=2:raise ValueError('Both fixed source sides required')
    for stats,points,delta in zip(step['team_stats'],step['points_by_type'],step['score_delta']):
        if set(stats)!=set(STATS)or any(not _number(v)for v in stats.values()):raise ValueError('Unknown team credit cannot become zero')
        if any(v<0 or v!=int(v)for k,v in stats.items()if k in COUNTS):raise ValueError('Known nonnegative count credits required')
        if stats['official_targets']>stats['official_pass_attempts']or stats['official_pass_attempts']+stats['official_carries']>stats['physical_plays']:raise ValueError('Official opportunity conservation failure')
        if stats['passing_TD']>stats['official_targets']or stats['rushing_TD']>stats['official_carries']:raise ValueError('Touchdown without compatible official opportunity')
        if(stats['passing_yards']!=0 or stats['receiving_yards']!=0)and stats['official_pass_attempts']==0 or stats['rushing_yards']!=0 and stats['official_carries']==0:raise ValueError('Yards without compatible official opportunity')
        if stats['passing_yards']!=stats['receiving_yards']or stats['passing_TD']!=stats['receiving_TD']:raise ValueError('Linked pass/receiving credits disagree')
        if set(points)-set(POINTS)or any(not _number(v)or v not in(0,1)for v in points.values()):raise ValueError('Typed single-event real scoring components required')
        if not _number(delta)or sum(POINTS[k]*v for k,v in points.items())!=delta:raise ValueError('Typed points must equal source score delta')
        if points.get('pass_td',0)!=stats['passing_TD']or points.get('rush_td',0)!=stats['rushing_TD']:raise ValueError('Physical TD counted once, distinct fantasy credits')
    if sum(s['physical_plays']for s in step['team_stats'])>1 or sum(s['official_pass_attempts']+s['official_carries']for s in step['team_stats'])>1:raise ValueError('One native row cannot create multiple physical opportunities')
    primary=sum(v for p in step['points_by_type']for k,v in p.items()if k in{'pass_td','rush_td','return_td','field_goal','safety'})
    tries=sum(v for p in step['points_by_type']for k,v in p.items()if k in{'extra_point','two_point'})
    if primary>1 or tries>1 or primary and tries:raise ValueError('Incompatible scoring outcomes on one native row')


def decode_block(block,state):
    """Transfer verified elapsed source intervals, never source absolute scores."""
    if not block['certified']:return dict(status='UNKNOWN_SOURCE_BLOCK')
    if block['start']['field100']!=state['field100']or block['start']['phase']!=state['phase']:raise ValueError('No physical support transport/rescaling')
    remaining=state['half_seconds'];duration=block['duration_seconds'];steps=block['steps'];prefix=None
    if not _number(duration)or duration<0:raise ValueError('Known nonnegative duration required')
    if not steps or steps[-1]['elapsed_seconds']!=duration:raise ValueError('Full duration must equal the last certified source-row endpoint')
    if duration>remaining:
        matches=[p for p in block.get('boundary_prefixes',[])if p.get('certified')is True and p.get('half_end')is True and p.get('terminal_phase')in('halftime','regulation_end')and p['elapsed_seconds']==remaining]
        if len(matches)!=1:return dict(status='UNKNOWN_HALF_BOUNDARY_PREFIX')
        prefix=matches[0];count=prefix['steps_count']
        if type(count)is not int or not 1<=count<=len(steps):raise ValueError('Certified nonempty source row-prefix required')
        if steps[count-1]['elapsed_seconds']!=prefix['elapsed_seconds']:raise ValueError('Prefix must end at the exact last included source-row endpoint')
        steps=steps[:count];duration=remaining
    terminal_phase=prefix['terminal_phase']if prefix is not None else block['terminal']['phase']
    if duration<remaining and terminal_phase in('halftime','regulation_end'):return dict(status='UNKNOWN_SOURCE_BOUNDARY_ALIGNMENT')
    if duration==remaining and terminal_phase not in('halftime','regulation_end'):return dict(status='UNKNOWN_PENDING_UNTIMED_OR_BOUNDARY_PHASE')
    source_side=block['start_possession_side']
    if source_side not in(0,1):raise ValueError('Source possession orientation unknown')
    target_side=state['possession_side'];mapping={source_side:target_side,1-source_side:1-target_side}
    scores=list(state['scores']);totals=[dict.fromkeys(STATS,0)for _ in range(2)];previous=0;events=[]
    for step in steps:
        elapsed=step['elapsed_seconds']
        if not _number(elapsed)or not previous<=elapsed<=duration:raise ValueError('Unknown/reversed/cross-boundary elapsed clock')
        _credits(step);previous=elapsed
        for s in(0,1):
            target=mapping[s];scores[target]+=step['score_delta'][s]
            for k,v in step['team_stats'][s].items():totals[target][k]+=v
        events.append(dict(source_row_id=step['row_id'],elapsed_seconds=elapsed,generated_half_seconds=state['half_seconds']-elapsed,score_delta=[step['score_delta'][s]for s in(sorted(mapping,key=mapping.get))]))
    new=dict(state,scores=scores,half_seconds=remaining-duration)
    if new['half_seconds']>0:
        terminal=_start(block['terminal']);new.update(terminal,possession_side=mapping[terminal['possession_side']])
    else:new.update(phase='halftime'if state['half']==1 else'regulation_end',possession_side=None,field100=None)
    return dict(status='DECODED',state=new,team_stats=totals,events=events,source_rows=len(steps),prefix_used=prefix is not None)


def rollout(policy,openings,context_by_side,uniforms,*,arm,max_events=400,deadline=None,clock=time.monotonic):
    """A supplied common-uniform stream; no target outcome or script argument."""
    stream=iter(uniforms);trace=[];totals=[dict.fromkeys(STATS,0)for _ in range(2)];state=None;full_law=True;source_rows=0
    def uniform():
        u=next(stream)
        if not _number(u)or not 0<=u<1:raise ValueError('Uniform in [0,1) required')
        return u
    def result(status,reason=None):return dict(version=VERSION,status=status,reason=reason,state=deepcopy(state),team_stats=totals,trace=trace,source_rows=source_rows,full_law_known=full_law and status=='COMPLETE_REGULATION',player_forecasts='UNKNOWN_UNASSIGNED',nonlinear_fantasy_bonuses='UNKNOWN',scope='MECHANICS_SMOKE_ONLY_NOT_FORECAST_QUALITY',activation=False)
    if not openings:return result('UNSUPPORTED_TRAJECTORY','NO_TRAIN_OPENING_SUPPORT')
    if len(context_by_side)!=2:raise ValueError('Both target pregame contexts required')
    if type(max_events)is not int or not 1<=max_events<=400:raise ValueError('Fixed event limit cannot increase')
    if len({o['opening_id']for o in openings})!=len(openings)or any(o['source_season']!=2023 or type(o['certified'])is not bool for o in openings):raise ValueError('Unique TRAIN source opening pool required')
    full_law=all(o['certified']for o in openings)
    try:
        ordered=sorted(openings,key=lambda o:o['opening_id']);opening=ordered[min(int(uniform()*len(ordered)),len(ordered)-1)]
        if opening['source_season']!=2023 or not opening['certified']:return result('UNKNOWN_SOURCE_OPENING')
        for half,key in((1,'first_half'),(2,'second_half')):
            start=_start(opening[key]);state=dict(start,half=half,half_seconds=1800,scores=[0,0]if state is None else state['scores'])
            while state['half_seconds']>0:
                if deadline is not None and clock()>=deadline:return result('INCOMPLETE_TIME_CAP')
                if source_rows>=max_events:return result('INCOMPLETE_EVENT_CAP')
                selection=select_block(policy,state,context_by_side[state['possession_side']],arm=arm,uniform=uniform());full_law &= selection['full_law_known']
                trace.append({k:v for k,v in selection.items()if k!='selected'})
                if selection['status']!='SELECTED':return result(selection['status'],selection.get('reason'))
                block=selection['selected']
                if not block['steps']:return result('UNKNOWN_EMPTY_SOURCE_BLOCK')
                if source_rows+len(block['steps'])>max_events:return result('INCOMPLETE_EVENT_CAP')
                decoded=decode_block(block,state)
                if decoded['status']!='DECODED':return result(decoded['status'])
                source_rows+=decoded['source_rows'];state=decoded['state'];trace[-1].update(block_id=block['block_id'],events=decoded['events'],prefix_used=decoded['prefix_used'])
                for side in(0,1):
                    for k,v in decoded['team_stats'][side].items():totals[side][k]+=v
        return result('COMPLETE_REGULATION')
    except StopIteration:return result('INCOMPLETE_UNIFORM_STREAM')


def source_bound_dk_replay(statistics,*,full_individual_credits_known):
    """Original source-only scoring check, never a target player forecast."""
    if not full_individual_credits_known or any(not _number(statistics.get(k))for k in DK_FIELDS):return dict(status='UNKNOWN_INDIVIDUAL_CREDITS',points=None)
    return dict(status='SOURCE_BOUND_REPLAY_ONLY',points=calculate_dk_points(statistics,floor_at_zero=False),future_player_forecast=False)


def mechanics_smoke(policy,openings,games,*,clock=time.monotonic,publish_path=None):
    """Fixed32x2/seed17/120s smoke only; no outcome metrics or probability claim."""
    started=clock();deadline=started+120;rows=[];capped=False;seen=set()
    for game in sorted(games,key=lambda g:g['game_id']):
        gid=game['game_id']
        if gid in seen:raise ValueError('Unique native target game required')
        seen.add(gid)
        for path in range(32):
            seed_bytes=hashlib.sha256(f'progression_smoke_v1|17|{gid}|{path}'.encode()).digest()
            uniforms=np.random.default_rng(int.from_bytes(seed_bytes[:8],'big')).random(401).tolist()
            for arm in('contextual','control'):
                if capped or clock()>=deadline:
                    capped=True;result=dict(status='NOT_RUN_TIME_CAP',full_law_known=False)
                else:
                    result=rollout(policy,openings,game['context_by_side'],uniforms,arm=arm,deadline=deadline,clock=clock)
                    capped=result['status']=='INCOMPLETE_TIME_CAP'
                rows.append(dict(game_id=gid,path=path,arm=arm,seed=17,uniform_stream_sha256=hashlib.sha256(np.asarray(uniforms,dtype='<f8').tobytes()).hexdigest(),result=result))
                if publish_path is not None:publish_path(rows[-1])
    statuses={}
    for row in rows:
        key=row['result']['status'];statuses[key]=statuses.get(key,0)+1
    return dict(version=VERSION,status='INCOMPLETE_TIME_CAP'if capped else'MECHANICS_SMOKE_EXECUTED',elapsed_seconds=clock()-started,hard_seconds=120,paths_per_arm_per_game=32,arms=2,seed=17,planned_paths=len(games)*64,status_counts=statuses,paths=rows,forecast_quality_assessed=False,tail_calibration_assessed=False,conditional_successful_subset_is_not_full_forecast=True,optimizer_calls=0,activation=False)
