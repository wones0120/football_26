"""Last-game events, actual reactions and competing next-week role hypotheses.

Box-score anomalies trigger research, never trust/benching forecasts. Only sourced
distinct role mechanisms can reuse the existing bounded discovery allocator.
"""
from copy import deepcopy
import math
from uuid import UUID

from .analyst_shadow import digest

CONTRACT='weekly_role_review_v1'
EVENT_KINDS={'ball_security','receiving_opportunity','participation_change','post_event_usage',
             'assignment_error','drop','qb_change','protection_change','availability_change','critical_down_usage'}


def value(row,key):
    n=row.get(key)
    return float(n) if type(n) in (int,float) and math.isfinite(n) else None


def fumble_counts(row):
    """Prefer explicitly measured total; missing components cannot become zero."""
    total=value(row,'fumbles_total'); lost=value(row,'fumbles_lost_total')
    if total is None:
        parts=[value(row,k) for k in ('rushing_fumbles','receiving_fumbles','sack_fumbles')]
        if all(v is not None for v in parts):total=sum(parts)
    if lost is None:
        parts=[value(row,k) for k in ('rushing_fumbles_lost','receiving_fumbles_lost','sack_fumbles_lost')]
        if all(v is not None for v in parts):lost=sum(parts)
    if any(v is not None and (v<0 or not v.is_integer()) for v in (total,lost)) or (total is not None and lost is not None and lost>total):
        raise ValueError('invalid fumble/lost counts')
    return dict(fumbles=total,fumbles_lost=lost)


def validate_weekly_review(packet):
    from .analyst_packets import clock
    block=packet.get('weekly_role_review')
    if block is None:return []
    if not isinstance(block,dict) or block.get('contract_id')!=CONTRACT:return ['unknown weekly role review contract']
    errors=[]; players={p['player_master_id']:p for p in packet.get('players',[])}; sources={s['source_id']:s for s in packet.get('sources',[])}; games={g['game_id']:g for g in packet.get('games',[])}
    observations=block.get('observations'); findings=block.get('findings')
    if not isinstance(observations,list) or not isinstance(findings,list):return ['weekly observations/findings must be arrays']
    seen=set()
    for o in observations:
        if not isinstance(o,dict):errors.append('weekly observation must be object');continue
        label=str(o.get('observation_id'))
        def need(ok,reason):
            if not ok:errors.append(label+': '+reason)
        pid=o.get('player_master_id'); player=players.get(pid,{})
        try:UUID(pid)
        except (ValueError,TypeError,AttributeError):need(False,'invalid canonical UUID')
        need(bool(o.get('observation_id')) and label not in seen,'missing/duplicate observation');seen.add(label)
        need(pid in players and bool(o.get('source_native_player_id')),'canonical/native identity required')
        need(bool(o.get('previous_game_id')) and bool(o.get('source_native_row_id')),'prior-game/source-row lineage required')
        need(o.get('team')==player.get('team'),'team mismatch')
        game=games.get(player.get('game_id'),{})
        need(type(o.get('season')) is int and o.get('season')==game.get('season'),'season mismatch')
        need(type(o.get('week')) is int and o.get('week')==game.get('week',0)-1,'not immediately previous week')
        need(o.get('source_id') in sources,'unknown observation source')
        try:
            asof=clock(o['available_at']); decision=clock(packet['decision_at'])
            need(asof<=decision,'future observation')
            source=sources.get(o.get('source_id'),{})
            need(source.get('coverage')=='verified' and clock(source['available_at'])<=asof,'observation source unavailable')
            if o.get('completed_at'):need(clock(o['completed_at'])<=asof,'future game completion')
        except (KeyError,ValueError,TypeError):need(False,'invalid observation clock')
        try:fumble_counts(o.get('stats',{}))
        except ValueError:need(False,'invalid fumble/lost counts')
        events=o.get('events',[])
        need(isinstance(events,list),'event sequence must be array')
        event_ids=set(); previous=-1
        for e in events if isinstance(events,list) else []:
            need(isinstance(e,dict),'event must be object')
            if not isinstance(e,dict):continue
            need(e.get('event_id') and e['event_id'] not in event_ids,'duplicate/missing native event');event_ids.add(e.get('event_id'))
            need(e.get('kind') in EVENT_KINDS and e.get('player_master_id')==pid,'invalid canonical event mapping')
            need(e.get('identity_evidence') in {'native_id','reviewed_native_roster_crosswalk'},'raw name event match prohibited')
            sequence=e.get('sequence')
            need(type(sequence) is int and sequence>previous,'event sequence must be strictly increasing')
            if type(sequence) is int:previous=sequence
            need(e.get('source_id') in sources and e.get('summary'),'event source/summary required')
    seen_findings=set()
    for f in findings:
        if not isinstance(f,dict):errors.append('weekly finding must be object');continue
        label=str(f.get('finding_id'))
        def need(ok,reason):
            if not ok:errors.append(label+': '+reason)
        need(bool(f.get('finding_id')) and label not in seen_findings,'missing/duplicate finding');seen_findings.add(label)
        pid=f.get('player_master_id'); player=players.get(pid,{})
        need(pid in players and f.get('game_id')==player.get('game_id'),'finding canonical game mismatch')
        formats=f.get('formats',[]); game=games.get(f.get('game_id'),{})
        need(isinstance(formats,list) and bool(formats) and all(game.get('format_membership',{}).get(fmt)=='confirmed_in_scope' for fmt in formats),'finding format out of scope')
        need(isinstance(f.get('observation_ids'),list) and bool(f.get('observation_ids')) and all(i in seen for i in f['observation_ids']),'unknown prior observation')
        need(all(o.get('player_master_id')==pid for o in observations if o.get('observation_id') in f.get('observation_ids',[])),'cross-player observation reference')
        for k in ('what_happened','actual_reaction','alternative_interpretations','contrary_evidence','role_mechanism','conditions','model_accounting','next_checks','roster_implication'):
            need(bool(f.get(k)),'missing '+k)
        need(f.get('status') in {'watchlist','supported_model_delta','rejected'},'unknown finding status')
        need(f.get('forecast_basis') in {'coach_conditional','measured_role','analyst_hypothesis','unresolved'},'forecast basis required')
        need(not any(k in f for k in ('fantasy_point_bonus','motivation_bonus','probability','confidence_score','numeric_penalty')),'unsupported causal/numeric boost')
        try:
            asof=clock(f['as_of']);need(asof<=clock(packet['decision_at'])<clock(f['expires_at'])<=clock(game['kickoff_at']),'invalid finding expiry')
        except (KeyError,TypeError,ValueError):need(False,'invalid finding clock');asof=None
        for premise in f.get('factual_premises',[]):
            source=sources.get(premise.get('source_id'),{})
            need(source.get('fact_assertions',{}).get(premise.get('fact_key'))==premise.get('text') and bool(premise.get('text')),'unsupported factual premise')
            try:need(source.get('coverage')=='verified' and asof is not None and clock(source['available_at'])<=asof,'premise unavailable at finding')
            except (KeyError,TypeError,ValueError):need(False,'invalid premise source clock')
        action=f.get('discovery_action')
        if f.get('status')=='supported_model_delta':
            need(f.get('forecast_basis')=='measured_role' and f.get('model_accounting',{}).get('status') in {'partial','unmodeled'} and f.get('model_accounting',{}).get('delta_fields'),'distinct measured model delta required')
            need(bool(f.get('factual_premises')) and bool(action),'supported action needs sourced role and bounded construction')
            need(not any(o.get('completion_status')!='verified_complete' for o in observations if o['observation_id'] in f.get('observation_ids',[])),'unsupported completion chronology')
            for o in observations:
                if o['observation_id'] not in f.get('observation_ids',[]):continue
                completion=sources.get(o.get('completion_evidence_source_id'),{})
                need(completion.get('coverage')=='verified' and o['previous_game_id'] in completion.get('completed_game_ids',[]),'verified native final-game evidence required')
                try:need(asof is not None and clock(completion['available_at'])<=asof,'completion evidence unavailable at finding')
                except (KeyError,TypeError,ValueError):need(False,'invalid completion evidence clock')
            need(isinstance(action,dict) and set(action)=={'idea_id','required_player_ids'} and bool(action.get('idea_id')) and action.get('required_player_ids')==[pid],'bounded canonical construction required; numeric transfer prohibited')
        elif action:need(False,'watchlist/rejected cannot allocate construction')
        branches=f.get('branches',[])
        need(isinstance(branches,list) and len(branches)>=2 and len({b.get('branch_id') for b in branches})==len(branches),'distinct competing branches required')
        for branch in branches:
            need(branch.get('conditions') and branch.get('role_implication'),'branch conditions/role implication required')
            need(not any(k in branch for k in ('probability','fantasy_point_bonus','factor','share_delta')),'weekly prose cannot invent numerical role response')
    return errors


def scan_weekly_review(packet,rows,*,fmt,decision_at=None):
    """Deterministic full-game event screen plus separately sourced interpretations."""
    errors=validate_weekly_review(packet)
    if errors:raise ValueError('; '.join(errors))
    from .analyst_packets import clock
    now=decision_at or packet['decision_at'];block=packet.get('weekly_role_review') or {};history=block.get('observations',[])
    if clock(now)<clock(packet['decision_at']):raise ValueError('newer weekly research cannot replay an earlier decision clock')
    opinions={f['player_master_id']:f for f in block.get('findings',[]) if fmt in f['formats']}; candidates=[];coverage=[]
    for game in packet['games']:
        if game.get('format_membership',{}).get(fmt)!='confirmed_in_scope':continue
        members=[r for r in rows if r.get('canonical_game_id',r.get('game_id'))==game['game_id'] or {r.get('player_team',r.get('team')),r.get('opponent_team',r.get('opponent'))}==set(game['teams'])]
        pids={str(r.get('player_id',r.get('player_master_id'))) for r in members};observed={o['player_master_id'] for o in history if o['player_master_id'] in pids and clock(o['available_at'])<=clock(now)}
        game_findings=[]
        for o in sorted(history,key=lambda x:x['observation_id']):
            pid=o['player_master_id']
            if pid not in pids or clock(o['available_at'])>clock(now):continue
            stats=o.get('stats',{}); counts=fumble_counts(stats);signals=[]
            if counts['fumbles'] is not None and counts['fumbles']>0:signals.append(dict(kind='ball_security',**counts))
            targets=value(stats,'targets'); catches=value(stats,'receptions'); yards=value(stats,'receiving_yards');old=o.get('prior_stats',{});prior_targets=value(old,'targets')
            if targets is not None and ((prior_targets is not None and targets-prior_targets>=3) or (yards is not None and yards>=70)):
                signals.append(dict(kind='receiving_opportunity',targets=targets,prior_targets=prior_targets,receptions=catches,receiving_yards=yards,interpretation='Volume/efficiency candidate; a touchdown or big yardage does not prove promotion.'))
            if o.get('events'):signals.extend(dict(kind=e['kind'],event_id=e['event_id']) for e in o['events'])
            finding=opinions.get(pid)
            if not signals and not finding:continue
            row=next(r for r in members if str(r.get('player_id',r.get('player_master_id')))==pid)
            entry=dict(player_master_id=pid,game_id=game['game_id'],previous_game_id=o['previous_game_id'],observation_id=o['observation_id'],signals=signals,
                source_native_player_id=o['source_native_player_id'],source_native_row_id=o['source_native_row_id'],source_id=o['source_id'],
                finding=deepcopy(finding),baseline_mean=row.get('projection'),baseline_unchanged=True,
                model_accounted_fields=[k for k in ('player_roll3_mean','targets_mean_3','carries_mean_3','snap_share_trend','target_share_trend','rush_share_trend') if row.get(k) is not None],
                action_status='supported_discovery_comparison' if finding and finding['status']=='supported_model_delta' and clock(finding['expires_at'])>clock(now) else 'watchlist_no_numerical_adjustment',
                unknowns=['Aggregate stats do not show post-event benching, routes, assignment responsibility or next-week coach decisions.','Motivation is a hypothesis; no causal scoring boost.'],completion_status=o.get('completion_status','unknown'))
            candidates.append(entry);game_findings.append(pid)
        coverage.append(dict(game_id=game['game_id'],scanned_player_count=len(members),previous_week_observed_players=len(observed),missing_player_ids=sorted(pids-observed),reviewed_candidate_ids=sorted(set(game_findings)),
            sequence_coverage='native events only where captured and canonical mapping verified; otherwise unavailable'))
    report=dict(contract_id=CONTRACT,format=fmt,decision_at=now,games=coverage,candidates=candidates,baseline_mutation=False,
        automatic_bonus=False,automatic_benching=False,history_coverage='packet-bound prior-week observations' if history else 'unavailable; enrich packet with prior-week native evidence',
        semantic_protocol='Investigate events, actual coach/QB reaction, post-event usage, current depth/practice, opposing interpretations and model accounting before role forecasts.')
    report['sha256']=digest(report);return report


def discovery_findings(packet):
    """Bridge qualifying Classic findings into existing discovery controls/legality."""
    errors=validate_weekly_review(packet)
    if errors:raise ValueError('; '.join(errors))
    result=[]
    for f in (packet.get('weekly_role_review') or {}).get('findings',[]):
        if f['status']!='supported_model_delta' or 'CLASSIC' not in f['formats']:continue
        result.append(dict(finding_id='weekly:'+f['finding_id'],game_id=f['game_id'],player_master_ids=[f['player_master_id']],
            source_ids=sorted({p['source_id'] for p in f['factual_premises']}),as_of=f['as_of'],classification='hypothesized_model_blindspot',status='supported_provisional',
            evidence_strength=.6,mechanism=f['role_mechanism'],counterevidence=f['contrary_evidence'],unknowns=f.get('unknowns',[]),
            model_accounting=deepcopy(f['model_accounting']),action=deepcopy(f['discovery_action']),
            strength_status='ordinal boundary for existing discovery gate; never event likelihood'))
    return result
