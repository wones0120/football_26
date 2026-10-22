"""Full-team availability/depth/practice features, without forecast or preferences.

Canonical factual resolution is reused; no roster ACT/blank becomes healthy,
no native Q policy changes the facts, and no absent teammate donates workload.
"""
from copy import deepcopy
from datetime import UTC,datetime
from uuid import UUID
from urllib.parse import urlparse
from .classic_official_context import CLUBS
from .factual_designation import clock
from .evaluation_record import digest
from .showdown_player_context import compose_player_contexts,assess_availability

VERSION='full_team_role_features_v1'
PLAYER_METRICS={'G17-M01':'Official game designation','G17-M02':'practice participation trend',
    'G17-M05':'current depth position','G17-M10':'documented workload restriction'}
KNOWN_POSITIONS={'QB','RB','HB','FB','WR','TE','K','P','LS','C','G','OG','OC','OT','T','OL','DE','DT','DL','NT','CB','S','FS','SS','LB','ILB','OLB','MLB'}
TEAM_GROUPS={'G18-M03':{'C','G','OG','OC','OT','T','OL'},'G18-M04':{'DE','DT','DL','NT'},
    'G18-M05':{'CB'},'G18-M06':{'S','FS','SS'},'G18-M07':{'LB','ILB','OLB','MLB'}}


def _metric(mid,value,*,unit,refs=(),reason=None,sample=None,variant='exact_definition_v1'):
    return dict(metric_id=mid,definition_version=VERSION,variant_id=variant,kind='derived_feature',value=value,
        unit=unit,coverage_state='derived' if value is not None else 'unknown',missing_reason=reason if value is None else None,
        source_refs=sorted(set(str(x) for x in refs)),sample=sample or {},forecast=False)


def _scoped(f,actor,*,season,week,cutoff,max_age_hours):
    try:
        observed=clock(f['observed_at']);received=clock(f['received_at']);published=clock(f['published_at']) if f.get('published_at') else None
        if f.get('kind') in {'depth_role','workload_restriction'} and any(clock(f[k])>cutoff for k in ('effective_at','modified_at') if f.get(k) is not None):return False
        return (str(f.get('player_id'))==actor['player_master_id'] and f.get('team')==actor['team']
            and f.get('position')==actor['position'] and f.get('season')==season and f.get('week')==week
            and f.get('source') and f.get('source_ids') and f.get('source_uri') and observed<=received<=cutoff
            and (published is None or published<=observed) and (cutoff-observed).total_seconds()<=max_age_hours*3600)
    except (KeyError,TypeError,ValueError):return False


def _latest_consistent(facts,key):
    if not facts:return None,'missing_source'
    newest=max(clock(f.get('effective_at') or f['observed_at']) for f in facts)
    latest=[f for f in facts if clock(f.get('effective_at') or f['observed_at'])==newest]
    if len({str(f.get(key)) for f in latest})!=1:return None,'conflicting_source'
    return latest[-1],None


def build_player_role_features(actors,facts,*,season,week,cutoff,roster_coverage=None,max_age_hours=24):
    """Caller supplies the full source roster, never an optimizer-filtered pool.

    A complete roster claim must identify the exact canonical actor universe,
    source refs and actual scope/clocks. At this pure boundary source bytes are
    caller-owned evidence; this function does not pretend to capture/verify them.
    """
    if type(season) is not int or type(week) is not int or not 2000<=season<=2200 or not 1<=week<=18:raise ValueError('REG availability scope required')
    cutoff=clock(cutoff);seen=set();normalized=[];queue=[];roster_coverage=roster_coverage or {}
    for source in actors:
        actor=deepcopy(source);pid=actor.get('player_master_id') or actor.get('player_id')
        if not pid:
            queue.append(dict(source_player_id=actor.get('source_player_id'),team=actor.get('team'),reason='canonical_player_unresolved'));continue
        pid=str(UUID(str(pid)))
        if str(pid) in seen:raise ValueError('Duplicate canonical full-team actor')
        seen.add(str(pid));actor.update(player_master_id=str(pid),player_id=str(pid),season=season,week=week)
        if not actor.get('team') or not actor.get('position'):raise ValueError('Historical/current team and position required')
        normalized.append(actor)
    original_facts=deepcopy(facts);canonical_facts=[]
    for f in facts:
        row=deepcopy(f)
        if row.get('player_id') is not None:
            try:row['player_id']=str(UUID(str(row['player_id'])))
            except (ValueError,TypeError,AttributeError):
                queue.append(dict(source_player_id=row.get('source_player_id'),team=row.get('team'),reason='invalid_canonical_fact_identity'));continue
        canonical_facts.append(row)
    facts=canonical_facts
    scoped_facts=[f for f in facts if any(_scoped(f,a,season=season,week=week,cutoff=cutoff,max_age_hours=max_age_hours) for a in normalized)]
    for f in facts:
        if not f.get('player_id') and f.get('source_player_id'):
            queue.append(dict(source_player_id=f['source_player_id'],team=f.get('team'),reason='canonical_fact_player_unresolved'))
    canonical=compose_player_contexts(normalized,scoped_facts,cutoff=cutoff,max_age_hours=max_age_hours)
    contexts={str(r['player_id']):{**r,**r['evidence_json']} for r in canonical};players=[]
    for actor in normalized:
        pid=actor['player_master_id'];context=contexts[pid];resolved=context['designation_resolution'];valid=[f for f in facts if _scoped(f,actor,season=season,week=week,cutoff=cutoff,max_age_hours=max_age_hours)]
        refs=[x for f in valid for x in f['source_ids']]
        official_hosts={'nfl.com','www.nfl.com',*(d+'.com' for d in CLUBS.values()),*('www.'+d+'.com' for d in CLUBS.values())}
        chosen=resolved.get('chosen_fact') or {}
        official=urlparse(str(chosen.get('source_uri') or '')).hostname in official_hosts
        designation=resolved.get('effective_designation') if resolved['status']=='resolved' and official else None
        # Restriction absence is unknown, not an unrestricted/full workload fact.
        restriction,restriction_reason=_latest_consistent([f for f in valid if f.get('kind')=='workload_restriction'],'restriction')
        depth,depth_reason=_latest_consistent([f for f in valid if f.get('kind')=='depth_role' and type(f.get('depth_position')) is int and f['depth_position']>=1],'depth_position')
        # A dated practice event, not HTTP observation time, orders the trend.
        practices=[]
        for f in valid:
            if f.get('kind')!='practice' or f.get('practice_status') not in {'DNP','LP','FP'} or not f.get('practice_date'):continue
            try:day=datetime.fromisoformat(f['practice_date']).date()
            except (ValueError,TypeError):continue
            if day>cutoff.date():continue
            practices.append((day,f))
        by_day={};conflict=False
        for day,f in practices:
            if day in by_day and by_day[day]['practice_status']!=f['practice_status']:conflict=True
            by_day[day]=f
        ordered=[by_day[k] for k in sorted(by_day)];trend=None
        if len(ordered)>=2 and not conflict:
            levels={'DNP':0,'LP':1,'FP':2};trend=dict(previous=ordered[-2]['practice_status'],latest=ordered[-1]['practice_status'],ordinal_change=levels[ordered[-1]['practice_status']]-levels[ordered[-2]['practice_status']],dates=[f['practice_date'] for f in ordered])
        state,reasons=assess_availability(context,cutoff=cutoff,evaluated_at=cutoff,max_age_hours=max_age_hours)
        if state=='AVAILABLE' and resolved['status']=='unknown':
            state='UNKNOWN';reasons=[*reasons,'roster_membership_not_game_designation']
        metrics={
            'G17-M01':_metric('G17-M01',designation,unit='categorical_game_designation',refs=refs,reason=resolved['status']),
            'G17-M02':_metric('G17-M02',trend,unit='dated_categorical_practice_sequence',refs=[x for f in ordered for x in f['source_ids']],reason='conflicting_practice_day' if conflict else 'two_dated_practice_reports_required',sample={'practice_days':len(ordered)}),
            'G17-M05':_metric('G17-M05',depth['depth_position'] if depth else None,unit='source_depth_order_1_based',refs=(depth or {}).get('source_ids',[]),reason=depth_reason),
            'G17-M10':_metric('G17-M10',deepcopy(restriction['restriction']) if restriction else None,unit='source_authored_restriction_not_forecast',refs=(restriction or {}).get('source_ids',[]),reason=restriction_reason)}
        players.append(dict(player_master_id=pid,team=actor['team'],position=actor['position'],metrics=metrics,availability_state=state,availability_reasons=reasons,
            canonical_role=context.get('canonical_role'),designation_resolution=deepcopy(resolved),binding_roster_unavailability=deepcopy(context.get('binding_roster_unavailability'))))
    teams=[]
    for team in sorted({a['team'] for a in normalized}):
        members=[p for p in players if p['team']==team];coverage=roster_coverage.get(team) or {};complete=False
        try:
            complete=(coverage.get('complete') is True and coverage.get('season')==season and coverage.get('week')==week
                and set(coverage['player_master_ids'])=={p['player_master_id'] for p in members} and coverage.get('source_refs')
                and clock(coverage['observed_at'])<=clock(coverage['received_at'])<=cutoff
                and (cutoff-clock(coverage['observed_at'])).total_seconds()<=max_age_hours*3600
                and not any(q['team']==team for q in queue))
        except (KeyError,TypeError,ValueError):complete=False
        metrics={}
        for mid,positions in TEAM_GROUPS.items():
            selected=[p for p in members if p['position'] in positions]
            unknown_positions=sum(p['position'] not in KNOWN_POSITIONS for p in members)
            starter_only=mid in {'G18-M03','G18-M04'}
            role_unknown=sum(p['canonical_role'] not in {'expected_starter','expected_backup','rotation','rotational','specialist'} for p in selected) if starter_only else 0
            counted=[p for p in selected if not starter_only or p['canonical_role']=='expected_starter']
            known=sum(p['availability_state']=='UNAVAILABLE' for p in counted);unknown=sum(p['availability_state']=='UNKNOWN' for p in counted)
            metrics[mid]=_metric(mid,known if complete and not unknown and not role_unknown and not unknown_positions else None,unit='players',refs=coverage.get('source_refs',[]),reason='full_team_roster_status_or_unit_role_incomplete',sample=dict(known_unavailable_lower_bound=known,unknown_status_actors=unknown,unknown_position_actors=unknown_positions,unknown_unit_role_actors=role_unknown,source_actors=len(selected),starter_only=starter_only,roster_complete=bool(complete)))
        starters=[p for p in members if p['position']=='QB' and p['canonical_role']=='expected_starter']
        value=starters[0]['availability_state'] if len(starters)==1 and starters[0]['availability_state']!='UNKNOWN' else None
        metrics['G18-M01']=_metric('G18-M01',value,unit='categorical_participation_availability',refs=coverage.get('source_refs',[]),reason='unique_current_sourced_starting_qb_and_availability_required',sample=dict(starter_ids=[p['player_master_id'] for p in starters]))
        teams.append(dict(team=team,metrics=metrics,full_source_actor_ids=sorted(p['player_master_id'] for p in members),roster_complete=bool(complete)))
    result=dict(version=VERSION,season=season,week=week,players=players,teams=teams,identity_review_requests=queue,
        consumed_by_models=False,consumed_by_optimizer=False,definition_notes={'practice_trend':'Ordinal DNP/LP/FP sequence only, not health or participation probability','unavailable_counts':'Exact count only with full roster and known status; lower bound retained otherwise','restrictions':'Authored restriction retained, never converted to an invented workload fraction'},
        source_boundary='Supplied canonical facts/roster refs validated for scope and clocks; immutable byte verification belongs to upstream intake')
    semantic=deepcopy(result)
    for row in semantic['players']:
        row.pop('designation_resolution',None);row.pop('binding_roster_unavailability',None)
        for m in row['metrics'].values():m.pop('source_refs',None)
    for row in semantic['teams']:
        for m in row['metrics'].values():m.pop('source_refs',None)
    result['semantic_measurements_sha256']=digest(semantic)
    result['provenance']=dict(actual_derived_at=datetime.now(UTC).isoformat(),decision_cutoff_at=cutoff.isoformat(),actors=deepcopy(actors),facts=original_facts,roster_coverage=deepcopy(roster_coverage))
    return result
