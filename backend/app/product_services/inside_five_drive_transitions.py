"""Observed native-drive inside20→inside5 and inside5→TD transitions."""
from collections import defaultdict
from copy import deepcopy
from .game_clock_pace_catalog import _native_timeline,build_native_redzone_drives
from .environment_context_evidence import _snap,_and
from .defense_context_evidence import _number
from .evaluation_record import digest

VERSION='observed_inside_five_drive_transitions_v1'


def build_inside_five_drive_transitions(parent,*,before_period,cutoff):
    evidence,timeline,unknown_order=_native_timeline(parent,before_period=before_period,cutoff=cutoff)
    rz=build_native_redzone_drives(parent,before_period=before_period,cutoff=cutoff)
    proofs={(r['game_id'],r['offense_team'],p['drive_id']):p for r in rz['game_rows'] for p in r['drive_quality']['drive_outcomes']}
    games={};drives={}
    for entry in timeline:
        if 'event' not in entry:continue
        e=entry['event'];gid=e['game_id'];team=e['team'];raw=e['raw_flags'];key=(gid,team)
        g=games.setdefault(key,dict(game_id=gid,team=team,season=e['season'],week=e['week'],unknown_drive_entry_events=0,drives=[]))
        yard=_number(raw.get('yardline_100'));yard=yard if yard is not None and 0<=yard<=100 else None
        snap=_snap(e);inside20=_and(snap,None if yard is None else yard<=20);inside5=_and(snap,None if yard is None else yard<=5)
        did=_number(raw.get('fixed_drive'));did=str(int(did)) if did is not None and did>=0 and int(did)==did else None
        if did is None:
            if inside20 is not False:g['unknown_drive_entry_events']+=1
            continue
        d=drives.setdefault((gid,team,did),dict(drive_id=did,entries20=[],entries5=[],unknown20=False,unknown5=False))
        if inside20 is True:d['entries20'].append(dict(play_id=entry['play_id'],order=entry['order']))
        elif inside20 is None:d['unknown20']=True
        if inside5 is True:d['entries5'].append(dict(play_id=entry['play_id'],order=entry['order']))
        elif inside5 is None:d['unknown5']=True
    for (gid,team,did),d in sorted(drives.items()):
        if not d['entries20'] and not d['unknown20']:continue
        proof=proofs.get((gid,team,did));ordered=gid not in unknown_order
        terminal_known=bool(ordered and proof and proof['outcome_known'])
        reached5=True if ordered and d['entries5'] else False if terminal_known and not d['unknown5'] else None
        first5=min((p['order'] for p in d['entries5']),default=None) if ordered else None
        terminals=proof['terminal_native_orders'] if proof else []
        terminal_after5=bool(first5 is not None and terminals and all(p['order'] is not None and p['order']>=first5 for p in terminals))
        td=(proof['completion_basis'] in {'observed_passing_touchdown','observed_rushing_touchdown'}) if terminal_known and terminal_after5 else None
        games[(gid,team)]['drives'].append(dict(**d,inside20_entry_proven=bool(d['entries20']),inside5_entry_proven=bool(d['entries5']),
            inside20_to5=reached5 if d['entries20'] else None,inside5_to_td=td,terminal_proof=deepcopy(proof),native_order_known=ordered))
    rows=[]
    for _,g in sorted(games.items()):
        metrics={}
        for mid,entry,outcome,unknown in [('X05-M03','inside20_entry_proven','inside20_to5','unknown20'),('G12-M07','inside5_entry_proven','inside5_to_td','unknown5')]:
            eligible=[d for d in g['drives'] if d[entry]];known=[d[outcome] for d in eligible if d[outcome] is not None]
            unproven=sum(not d[entry] and d[unknown] for d in g['drives'])+g['unknown_drive_entry_events']
            n=len(known);success=sum(known);complete=len(known)==len(eligible) and not unproven
            metrics[mid]=dict(observed_entered_drives=len(eligible),known_terminal_or_reach_outcomes=n,unknown_outcomes=len(eligible)-n,unknown_entry_exposures=unproven,
                known_successes=success,value=success/len(eligible) if eligible and complete else None,known_sample_value=success/n if n else None)
        rows.append(dict(g,metrics=metrics))
    basis=dict(version=VERSION,before_period=before_period,game_rows=rows,definitions={'X05-M03':'Observed inside20 drive reaches preplay inside5 at or after entry; terminal-certified nonreach only', 'G12-M07':'Physical passing-or-rushing TD after observed preplay inside5 entry, once per native drive'},source_event_sha256=evidence['sha256'])
    return basis|dict(semantic_sha256=digest(basis),source=deepcopy(evidence['source']),evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None,model_consumed=False,optimizer_consumed=False)


def derive_retrospective_inside_five(parent_ref,snapshot,*,actual_read_at,directory=None):
    from datetime import datetime,UTC
    from pathlib import Path
    import hashlib
    from .factual_designation import clock
    from .opportunity_source_capture import load_event_artifact
    original,actual,lock=(clock(v) for v in (parent_ref['decision_cutoff_at'],actual_read_at,snapshot.slate_lock_at))
    if None in (original,actual,lock) or not original<lock<=actual<=datetime.now(UTC):raise ValueError('Explicit retrospective boundary required')
    parent=load_event_artifact(parent_ref,snapshot,before_period=parent_ref['before_period'],cutoff=original,directory=directory)
    result=build_inside_five_drive_transitions(parent,before_period=parent_ref['before_period'],cutoff=actual)
    result['provenance']=dict(parent_ref=deepcopy(parent_ref),original_evidence_boundary_at=original.isoformat(),source_lock_at=lock.isoformat(),actual_read_at=actual.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return result


def require_feature_use(value,*,purpose):
    if value.get('version')!=VERSION or purpose!='offline_descriptive' or value.get('pregame_serving_eligible') is not False:raise ValueError('Observed drive transitions cannot serve forecasts/models/optimizer')
    return value
