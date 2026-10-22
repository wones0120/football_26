"""Observed workload distributions conditioned on proven offensive participation.

Descriptive revised-source summaries, never forward uncertainty distributions.
"""
from collections import defaultdict
from datetime import datetime,UTC
from copy import deepcopy
import math
from uuid import UUID
from .evaluation_record import digest
from .factual_designation import clock
from .workload_venue_splits import build_workload_venue_splits,CHANNELS

VERSION='observed_active_workload_distributions_v1'
ROLES={'QB','RB','FB','WR','TE'}
DEFINITIONS={
 'X02-M01':'Sample variance of official targets in observed source logs with strictly positive offensive snaps, within same source role/team/season',
 'X02-M02':'Sample variance of official rush attempts in observed source logs with strictly positive offensive snaps, within same source role/team/season',
 'X02-M03':'Sample variance of official pass attempts among source-proven QB logs with strictly positive offensive snaps, within same team/season',
 'X02-M04':'Observed zero-target fraction among same-role/team/season source logs with proven positive offensive snaps',
 'X02-M05':'Observed zero-carry fraction among source-proven QB/RB/FB logs with positive offensive snaps; no WR/TE rusher inference',
}


def build_active_workload_distributions(weekly,schedule,participation,*,before_period,cutoff):
    base=build_workload_venue_splits(weekly,schedule,before_period=before_period)
    decision=clock(cutoff)
    if decision is None or decision>datetime.now(UTC):raise ValueError('Actual nonfuture decision clock required')
    if participation.get('version')!='canonical_offensive_participation_v1' or participation.get('pregame_serving_eligible') is not False:
        raise ValueError('Verified descriptive participation contract required')
    if clock(participation.get('actual_derived_at')) is None or clock(participation['actual_derived_at'])>decision:
        raise ValueError('Participation unavailable at cutoff')
    if clock(weekly['provenance'].get('actual_derived_at')) is None or clock(weekly['provenance']['actual_derived_at'])>decision:
        raise ValueError('Weekly input unavailable at cutoff')
    active={};unresolved=[]
    for r in participation['rows']:
        season,week,pid,team,gid=(r[k] for k in ('season','week','player_master_id','team','native_game_id'))
        if type(season) is not int or type(week) is not int or not 1<=week<=18 or season*100+week>=before_period:
            raise ValueError('Strict prior REG participation required')
        if pid is None:unresolved.append(deepcopy(r));continue
        if str(UUID(pid))!=pid:raise ValueError('Canonical participation identity required')
        n=r['offense_snaps']
        if n is not None and (type(n) not in (int,float) or not math.isfinite(n) or n<0 or int(n)!=n):raise ValueError('Known nonnegative snap count required')
        key=(season,week,pid,team)
        if key in active:raise ValueError('Duplicate canonical participation game')
        active[key]=deepcopy(r)
    weekly_rows={(r['season'],r['week'],r['source_player_id'],r['team']):r for r in weekly['rows']}
    output=[];covered=set()
    weekly_keys={(r['season'],r['week'],r['player_master_id'],r['team']) for r in weekly['rows'] if r['player_master_id'] is not None}
    missing_weekly_scopes={(r['season'],r['player_master_id'],r['team']) for k,r in active.items() if r['offense_snaps'] is not None and r['offense_snaps']>0 and k not in weekly_keys}
    for actor in base['rows']:
        if actor['season']!=before_period//100:continue
        groups=defaultdict(list)
        for log in actor['logs']:
            raw=weekly_rows[(actor['season'],log['week'],actor['source_player_id'],actor['team'])]
            role=raw.get('source_position');role=role if role in ROLES else None
            key=(actor['season'],log['week'],actor['player_master_id'],actor['team'])
            proof=active.get(key) if actor['player_master_id'] is not None else None
            if proof is not None:
                if proof['native_game_id']!=log['native_game_id']:raise ValueError('Native participation game differs from official weekly source')
                covered.add(key)
            positive=proof is not None and proof['offense_snaps'] is not None and proof['offense_snaps']>0
            # Zero snaps are not an inactive/DNP proof; the active-conditional cohort is unresolved.
            groups[role].append(dict(week=log['week'],native_game_id=log['native_game_id'],counts=deepcopy(log['counts']),
                positive_offensive_participation_proven=positive,participation_ref=deepcopy(proof),source_ref=deepcopy(log['source_ref'])))
        for role,logs in sorted(groups.items(),key=lambda x:str(x[0])):
            unknown=sum(not r['positive_offensive_participation_proven'] for r in logs)
            metrics={}
            for mid,ch,stat in [('X02-M01','targets','variance'),('X02-M02','rush_attempts','variance'),('X02-M03','pass_attempts','variance'),('X02-M04','targets','zero_rate'),('X02-M05','rush_attempts','zero_rate')]:
                applicable=role is not None and (mid!='X02-M03' or role=='QB') and (mid!='X02-M05' or role in {'QB','RB','FB'})
                samples=[r['counts'][ch] for r in logs if r['positive_offensive_participation_proven']]
                known=[x for x in samples if x is not None];missing=len(samples)-len(known)
                mean=sum(known)/len(known) if known else None
                value=(sum((x-mean)**2 for x in known)/(len(known)-1) if len(known)>=2 else None) if stat=='variance' else (sum(x==0 for x in known)/len(known) if known else None)
                exact=value if applicable and not unknown and not missing and not actor['native_team_scope_unknown'] and (actor['season'],actor['player_master_id'],actor['team']) not in missing_weekly_scopes else None
                metrics[mid]=dict(value=exact,known_sample_value=value if applicable else None,unit='official_opportunities_squared' if stat=='variance' else 'fraction_of_observed_positive_snap_logs',
                    source_role_applicable=applicable,observed_logs=len(logs),proven_active_logs=len(samples),unknown_participation_logs=unknown,unknown_count_logs=missing,
                    observed_zero_logs=sum(x==0 for x in known) if applicable else None,known_count_logs=len(known))
            output.append({k:actor[k] for k in ('season','team','source_player_id','player_master_id')}|dict(source_position=role,metrics=metrics,logs=logs))
    unmatched=[deepcopy(r) for k,r in active.items() if r['offense_snaps'] is not None and r['offense_snaps']>0 and k not in covered]
    normalized=[{**r,'logs':[{k:v for k,v in log.items() if k not in {'source_ref','participation_ref'}} for log in r['logs']]} for r in output]
    basis=dict(version=VERSION,before_period=before_period,definitions=DEFINITIONS,rows=normalized)
    return basis|dict(rows=output,semantic_sha256=digest(basis),unresolved_participation_rows=unresolved,positive_participants_missing_weekly_rows=unmatched,
        provenance=dict(weekly=deepcopy(weekly['provenance']),participation=deepcopy(participation.get('provenance',{}))),
        identity_review_requests=deepcopy(weekly['identity_review_requests']),participation_identity_review_requests=deepcopy(participation.get('identity_review_requests',[])),
        evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None,model_consumed=False,optimizer_consumed=False,
        limitations=['Observed weekly source cohort only; missing source rows or zero snaps are not inactive/DNP or zero workload',
            'Positive offensive snaps prove observed participation, not a stable role/full game or future participation likelihood',
            'Historical sample variance/zero rate is not a next-game uncertainty distribution or calibrated probability',
            'Source role QB/RB/FB/WR/TE is explicit; unknown or unsupported role stays inapplicable, no source-position inference',
            'Unmatched positive snap participants retain unknown weekly opportunity counts; no zero fill'])


def require_feature_use(block,*,purpose):
    if block.get('version')!=VERSION or purpose!='offline_descriptive' or block.get('pregame_serving_eligible') is not False:
        raise ValueError('Observed active workload summaries cannot serve models/forecasts/optimizer')
    return block


def load_positive_snap_participation(snapshot,*,cutoff):
    """Reuse authenticated retained revision + reviewed alias/collision decisions."""
    from pathlib import Path
    import json
    from .recent_snap_features import load_frozen_snap_revision,_number
    validated=load_frozen_snap_revision(snapshot,cutoff=cutoff)
    frozen=json.loads(Path(snapshot.artifact_path).read_text())
    actors={(r['pfr_player_id'],r['team']):r['player_master_id'] for r in validated['actor_trends']}
    rows={};skipped=[]
    for source in frozen['rows']:
        raw=source['raw'];native=raw.get('pfr_player_id');team=raw.get('team')
        from .market_snapshots import canonical_team
        team=canonical_team(team)
        period=raw.get('season',0)*100+raw.get('week',0)
        if raw.get('season')!=snapshot.season or period>=snapshot.season*100+snapshot.week or raw.get('game_type')!='REG':
            skipped.append(dict(source_row_id=source['source_row_id'],reason='Outside validated prior season/REG scope'))
            continue
        if (native,team) not in actors:
            skipped.append(dict(source_row_id=source['source_row_id'],reason='No validated native participation scope'))
            continue
        gid=raw['game_id'];season,week=int(raw['season']),int(raw['week'])
        parts=str(gid).split('_')
        if len(parts)!=4 or parts[0]!=str(season) or parts[1]!=f'{week:02}' or team not in {canonical_team(p) for p in parts[2:]}:
            skipped.append(dict(source_row_id=source['source_row_id'],reason='Native game/team scope unknown'))
            continue
        n=_number(raw.get('offense_snaps'),count=True);share=_number(raw.get('offense_pct'))
        if n==0 and share is not None and share>0:n=None
        value=dict(season=season,week=week,team=team,native_game_id=gid,player_master_id=actors[(native,team)],
                   pfr_player_id=native,offense_snaps=n,source_records=[])
        key=(gid,native,team)
        proof={k:source[k] for k in ('source_row_id','ingest_run_id','created_at')}
        if key in rows:
            if {k:v for k,v in rows[key].items() if k!='source_records'}!={k:v for k,v in value.items() if k!='source_records'}:
                raise ValueError('Equivalent native participation revision differs')
        else:rows[key]=value
        rows[key]['source_records'].append(proof)
    ordered=[r for _,r in sorted(rows.items())]
    basis=dict(version='canonical_offensive_participation_v1',rows=[{k:v for k,v in r.items() if k!='source_records'} for r in ordered])
    return basis|dict(rows=ordered,semantic_sha256=digest(basis),actual_derived_at=clock(cutoff).isoformat(),
        provenance=deepcopy(validated['provenance']),skipped_source_rows=skipped,
        identity_review_requests=deepcopy(validated['identity_review_requests']),pregame_serving_eligible=False,
        evidence_use='postlock_descriptive_not_pregame_or_serving')
