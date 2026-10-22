"""Provider ORIGINAL-drive reported starting field position and reached20 view."""
from collections import defaultdict
from copy import deepcopy
import re
from .game_clock_pace_catalog import _native_timeline
from .environment_context_evidence import _snap
from .defense_context_evidence import _number
from .opportunity_events import _flag
from .market_snapshots import canonical_team
from .evaluation_record import digest

VERSION='source_original_drive_field_context_v1'


def _integer(raw):
    n=_number(raw)
    return int(n) if n is not None and n>=0 and n==int(n) else None


def _field(raw,team,pair):
    value=str(raw or '').strip()
    if value in {'50','MIDFIELD'}:return 50.
    m=re.fullmatch(r'([A-Z]{2,3})\s+(\d{1,2})',value)
    if not m or not 0<=int(m[2])<=50:return None
    try:side=canonical_team(m[1])
    except ValueError:return None
    if side not in pair:return None
    return float(100-int(m[2]) if side==team else int(m[2]))


def _one(rows,field):
    values={str(r.get(field)) for r in rows if r.get(field) not in (None,'')}
    return next(iter(values)) if len(values)==1 else None,sorted(values)


def _terminal(entry,transition):
    if not entry or 'event' not in entry or entry['event']['status']=='excluded':return False
    e=entry['event'];raw=e['raw_flags'];channels={o['channel'] for o in e['opportunities']}
    if transition=='TOUCHDOWN':return ('pass_attempts' in channels and _flag(raw.get('pass_touchdown')) is True) or ('rush_attempts' in channels and _flag(raw.get('rush_touchdown')) is True)
    if transition=='PUNT':return raw.get('play_type')=='punt' and _flag(raw.get('punt_attempt')) is True and _flag(raw.get('punt_blocked')) is False
    if transition in {'FIELD_GOAL','MISSED_FG'}:return raw.get('play_type')=='field_goal' and _flag(raw.get('field_goal_attempt')) is True and raw.get('field_goal_result')==('made' if transition=='FIELD_GOAL' else 'missed')
    if transition=='INTERCEPTION':return 'pass_attempts' in channels and _flag(raw.get('interception')) is True
    if transition=='FUMBLE':return _flag(raw.get('fumble_lost')) is True
    if transition=='DOWNS':return _flag(raw.get('fourth_down_failed')) is True
    return False


def build_original_drive_field_context(parent,*,before_period,cutoff):
    evidence,timeline,uncertain=_native_timeline(parent,before_period=before_period,cutoff=cutoff)
    index={(r['game_id'],r['play_id']):r for r in timeline};groups={};games={}
    for entry in timeline:
        if 'event' not in entry:continue
        e=entry['event'];raw=e['raw_flags'];snap=_snap(e);gid=e['game_id'];team=e['team'];did=_integer(raw.get('drive'))
        g=games.setdefault((gid,team),dict(game_id=gid,team=team,season=e['season'],week=e['week'],unknown_original_drive_events=0,drives=[]))
        if did is None:
            if snap is not False:g['unknown_original_drive_events']+=1
            continue
        d=groups.setdefault((gid,team,did),dict(original_drive_id=did,rows=[],physical=[] ,unknown_snap_events=0))
        d['rows'].append(raw)
        if snap is True:d['physical'].append(entry)
        elif snap is None:d['unknown_snap_events']+=1
    for (gid,team,did),d in sorted(groups.items()):
        if not d['physical']:
            if d['unknown_snap_events']:games[(gid,team)]['unknown_original_drive_events']+=1
            continue
        pair={canonical_team(t) for t in gid.split('_')[2:]}
        start,starts=_one(d['rows'],'drive_start_yard_line');first,firsts=_one(d['rows'],'drive_play_id_started');last,lasts=_one(d['rows'],'drive_play_id_ended');flag,flags=_one(d['rows'],'drive_inside20');transition,transitions=_one(d['rows'],'drive_end_transition')
        first,last=_integer(first),_integer(last);a=index.get((gid,first));b=index.get((gid,last))
        def matches(entry):return bool(entry and 'event' in entry and entry['event']['team']==team and _integer(entry['event']['raw_flags'].get('drive'))==did)
        physical_orders=[r['order'] for r in d['physical']]
        first_link=bool(matches(a) and gid not in uncertain and a['order']<=min(physical_orders));last_link=bool(matches(b) and gid not in uncertain and b['order']>=max(physical_orders));ordered=first_link and last_link and a['order']<=b['order']
        reported=_field(start,team,pair);start_value=reported if first_link and len(starts)==1 and len(firsts)==1 else None
        native_physical=sorted(d['physical'],key=lambda r:r['order'] if r['order'] is not None else -1)
        first_los=_number(native_physical[0]['event']['raw_flags'].get('yardline_100')) if gid not in uncertain else None
        observed=any((_number(r['event']['raw_flags'].get('yardline_100')) is not None and 0<=_number(r['event']['raw_flags'].get('yardline_100'))<=20) for r in d['physical']) or (start_value is not None and start_value<=20)
        provider=_flag(_number(flag));contradiction=len(flags)>1 or (provider is False and observed)
        terminal=bool(ordered and len(lasts)==len(transitions)==1 and _terminal(b,transition))
        reach=None if contradiction else True if provider is True or observed else False if provider is False and terminal else None
        games[(gid,team)]['drives'].append(dict(original_drive_id=did,raw_reported_start_fields=starts,reported_start_yardline100=reported,start_yardline100=start_value,
            first_observed_physical_snap_yardline100=first_los,source_first_play_id=first,source_last_play_id=last,first_play_link_verified=first_link,last_play_link_verified=last_link,
            native_boundary_order_verified=ordered,provider_inside20_flag=provider,observed_source_reach20=observed,reach20=reach,source_contradiction=contradiction,
            terminal_verified=terminal,raw_end_transitions=transitions,source_fixed_drive_ids=sorted({str(r.get('fixed_drive')) for r in d['rows'] if r.get('fixed_drive') is not None}),unknown_snap_events=d['unknown_snap_events']))
    output=[]
    for _,g in sorted(games.items()):
        drives=g['drives'];start=[r['start_yardline100'] for r in drives if r['start_yardline100'] is not None];reach=[r['reach20'] for r in drives if r['reach20'] is not None];unknown=g['unknown_original_drive_events']
        bins={str(int(v)):start.count(v) for v in sorted(set(start))};complete_start=len(start)==len(drives) and not unknown;complete_reach=len(reach)==len(drives) and not unknown
        output.append(dict(g,metrics={'X05-M01':dict(observed_original_drives=len(drives),known_start_drives=len(start),unknown_cohort_events=unknown,known_sample_histogram=bins,
            exact_histogram=bins if complete_start and drives else None,known_sample_mean=sum(start)/len(start) if start else None,value=sum(start)/len(start) if complete_start and drives else None),
            'X05-M02':dict(observed_original_drives=len(drives),known_reach_outcomes=len(reach),known_reaches=sum(reach),unknown_cohort_events=unknown,
                known_sample_rate=sum(reach)/len(reach) if reach else None,value=sum(reach)/len(drives) if complete_reach and drives else None)}))
    basis=dict(version=VERSION,before_period=before_period,game_rows=output,source_event_sha256=evidence['sha256'],definitions={'X05-M01':'Source-provider ORIGINAL physical-offense drive starting-field-position distribution, source first-play linkage verified','X05-M02':'Source-original drive reported/observed reached20 fraction, terminal-certified nonreach only'})
    return basis|dict(semantic_sha256=digest(basis),source=deepcopy(evidence['source']),evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None,model_consumed=False,optimizer_consumed=False)


def derive_retrospective_original_drives(parent_ref,snapshot,*,actual_read_at,directory=None):
    from datetime import datetime,UTC
    from pathlib import Path
    import hashlib
    from .factual_designation import clock
    from .opportunity_source_capture import load_event_artifact
    original,actual,lock=(clock(v) for v in (parent_ref['decision_cutoff_at'],actual_read_at,snapshot.slate_lock_at))
    if None in (original,actual,lock) or not original<lock<=actual<=datetime.now(UTC):raise ValueError('Explicit retrospective source boundary required')
    parent=load_event_artifact(parent_ref,snapshot,before_period=parent_ref['before_period'],cutoff=original,directory=directory)
    result=build_original_drive_field_context(parent,before_period=parent_ref['before_period'],cutoff=actual)
    result['provenance']=dict(parent_ref=deepcopy(parent_ref),original_evidence_boundary_at=original.isoformat(),source_lock_at=lock.isoformat(),actual_read_at=actual.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return result


def require_feature_use(value,*,purpose):
    if value.get('version')!=VERSION or purpose!='offline_descriptive' or value.get('pregame_serving_eligible') is not False:raise ValueError('Original-drive descriptions cannot serve forecasts/models/optimizer')
    return value
