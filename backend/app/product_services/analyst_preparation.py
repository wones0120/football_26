"""Deterministic research selection, fresh compatibility audit and frozen handoff.

Machine checks assess scope/identity/clocks/typed contradictions, never matchup
truth. Original research text/clocks stay immutable; fresh checks are a separate
derived artifact with lineage. No source or projection is changed.
"""
from copy import deepcopy
from pathlib import Path
import json

from .analyst_packets import clock, validate, load_packet, import_packet, packet_digest
from .analyst_shadow import digest
from .market_snapshots import canonical_team

CONTRACT='analyst_preparation_v1'
HARD_OUT={'OUT','O','IR','PUP','INACTIVE','SUSPENDED','RESERVE/INJURED'}


def game_key(game):
    teams=game.get('teams') or [game.get('home_team'),game.get('away_team')]
    return frozenset(canonical_team(t) for t in teams),clock(game['kickoff_at'])


def eligible_scope(packet,*,season,week,fmt,games,checked_at,strategy):
    reasons=[]
    if clock(packet['decision_at'])>clock(checked_at) or clock(packet['frozen_at'])>clock(checked_at):reasons.append('future_research_clock')
    scoped=[g for g in packet['games'] if g.get('format_membership',{}).get(fmt)=='confirmed_in_scope']
    if not scoped or any(g.get('season')!=season or g.get('week')!=week for g in scoped):reasons.append('different_season_week_format')
    if {game_key(g) for g in scoped}!={game_key(g) for g in games}:reasons.append('different_game_scope_or_kickoff')
    if strategy=='MERGED_SCENARIOS' and not (packet.get('scenario_assumptions') or {}).get('scenarios'):reasons.append('missing_merged_scenarios')
    return reasons


def published_packets(*,directory=None,catalog=None):
    """Only the immutable ledger and explicitly catalogued packet evidence."""
    from .analyst_packets import LEDGER
    from .analyst_reports import CATALOG, RESEARCH_ROOT, _path
    root=Path(directory) if directory is not None else LEDGER
    packets={}
    if root.exists():
        paths=sorted(root.glob('*.json'))
        if len(paths)>1000:raise ValueError('Analyst ledger exceeds bounded selection limit')
        for path in paths:
            if len(path.stem)!=64:continue
            packet=load_packet(path.stem,directory=root);packets[path.stem]=packet
    catalog_path=Path(catalog) if catalog is not None else CATALOG
    if catalog_path.exists():
        # Catalogued JSON must be an explicit packet, never arbitrary filenames.
        for report in json.loads(catalog_path.read_text()).get('reports',[]):
            for evidence in report.get('evidence',[]):
                relative=evidence.get('path','')
                if Path(relative).name not in {'packet.json','classic_packet.json','showdown_packet.json'}:continue
                path=_path(relative)
                if not path.is_file():continue
                packet=json.loads(path.read_text())
                if packet.get('contract_id')!='wones_football_analyst_v1':continue
                errors=validate(packet)
                if errors:raise ValueError('Published Analyst packet invalid: '+'; '.join(errors))
                packets[packet_digest(packet)]=packet
    return packets


def revalidate(packet,rows,*,games,fmt,checked_at,source_sha256,projection_run_id,preliminary_snapshot_sha256=None):
    """Suppress only explicit contradictions/expired typed actions, audit unknowns."""
    out=deepcopy(packet);changes=[];blocked=set();workload_changed=set()
    scoped_ids={g['game_id'] for g in packet['games'] if g.get('format_membership',{}).get(fmt)=='confirmed_in_scope'}
    fresh={str(r.get('player_id',r.get('player_master_id'))):r for r in rows}
    for p in packet['players']:
        if p['game_id'] not in scoped_ids:continue
        pid=p['player_master_id'];row=fresh.get(pid)
        if not row:
            changes.append(dict(kind='unknown',player_master_id=pid,reason='No fresh prepared player row; absence does not prove out/inactive.'));continue
        team=canonical_team(row.get('player_team',row.get('team')))
        if team!=canonical_team(p['team']) or row.get('position')!=p['position']:raise ValueError('Analyst canonical team/position mismatch for '+pid)
        # DraftKings salary/native ID changes are checked against the same
        # canonical player, not joined by names or interpreted as a role change.
        old_salary=(p.get('baseline_model_assessment') or {}).get('salary')
        if old_salary is not None and old_salary!=row.get('salary'):changes.append(dict(kind='salary_changed',player_master_id=pid,reason='Prepared salary differs; legal objective uses the fresh salary.'))
        availability=str(row.get('official_availability_status') or row.get('availability_status') or row.get('injury_status') or '').upper()
        role_blocked=row.get('role_active') is False or row.get('role_rostered') is False or (p['position']=='K' and row.get('kicker_role_eligible') is False)
        if availability in HARD_OUT or role_blocked:
            blocked.add(pid);changes.append(dict(kind='contradicted',player_master_id=pid,reason='Fresh official availability/role evidence contradicts active-role conditions: '+availability))
        elif not availability or availability in {'UNKNOWN','UNRESOLVED'}:
            changes.append(dict(kind='unknown',player_master_id=pid,reason='Current official availability/role clearance unavailable.'))
        if p['position']=='QB' and row.get('is_starting_qb') is False:
            blocked.add(pid);changes.append(dict(kind='contradicted',player_master_id=pid,reason='Fresh canonical starting-QB evidence does not support the packet QB role.'))
        # Snapshot differences are not themselves semantic role discoveries.
        old=p.get('baseline_model_assessment') or {}
        for field in ('projection','salary','game_total_line','team_spread_line','team_implied_total'):
            if old.get(field) is not None and row.get(field) is not None and old[field]!=row[field]:
                changes.append(dict(kind='prepared_value_changed',player_master_id=pid,field=field,research_value=old[field],prepared_value=row[field],reason='Fresh prepared value differs from declared research baseline; no semantic effect or numerical bonus inferred.'))
        for field in ('projected_targets','projected_carries'):
            if old.get(field) is not None and row.get(field) is not None and old[field]!=row[field]:
                workload_changed.add(pid);changes.append(dict(kind='workload_changed',player_master_id=pid,field=field,research_value=old[field],prepared_value=row[field],reason='Fresh workload proxy differs; identity-specific transfer/concentration requires new review.'))
    expired={h['hypothesis_id'] for h in packet['hypotheses'] if clock(h['expires_at'])<=clock(checked_at)}
    # Hypothesis linkage may describe an absence or counterevidence rather than
    # require the player to be active. Never infer that requirement from prose.
    contradicted={h['hypothesis_id'] for h in packet['hypotheses'] if set(h.get('required_active_player_ids',[])) & blocked}
    removed_hypotheses=expired|contradicted
    for h in out['hypotheses']:
        if h['hypothesis_id'] in removed_hypotheses:
            h.update(status='abstain',action='none');changes.append(dict(kind='suppressed_hypothesis',finding_id=h['hypothesis_id'],reason='Research expiry passed' if h['hypothesis_id'] in expired else 'Fresh role/availability contradicts a referenced player condition'))
    surviving=[]
    for assessment in out.get('analyst_assessments',[]):
        required={pid for construction in assessment.get('construction_implications',[]) for role,ids in construction.get('roles',{}).items() if role!='AVOID' for pid in ids}
        if required&blocked or clock(assessment['expires_at'])<=clock(checked_at):
            changes.append(dict(kind='suppressed_construction',finding_id=assessment.get('assessment_id'),reason='Expired research or contradicted explicit player role'))
        else:surviving.append(assessment)
    out['analyst_assessments']=surviving
    if out.get('slate_synthesis'):
        kept_ids={a.get('assessment_id') for a in surviving}
        out['slate_synthesis']['ranked_upside_leans']=[r for r in out['slate_synthesis'].get('ranked_upside_leans',[]) if r.get('assessment_id') in kept_ids]
    removed_scenarios=[]
    if out.get('scenario_assumptions'):
        kept=[]
        for s in out['scenario_assumptions']['scenarios']:
            required={pid for a in s['assumptions'] for pid in a.get('player_master_ids',[])}|{a[k] for a in s['assumptions'] for k in ('from_player_master_id','to_player_master_id') if a.get(k)}
            sensitive=required & workload_changed
            if set(s['hypothesis_ids'])&removed_hypotheses or required&blocked or sensitive:
                removed_scenarios.append(s['scenario_id']);changes.append(dict(kind='suppressed_scenario',finding_id=s['scenario_id'],reason='Expired/contradicted hypothesis or explicit workload allocation requires new semantic review'))
            else:kept.append(s)
        out['scenario_assumptions']['scenarios']=kept
    for field in ('discovery','weekly_role_review','defense_kicker_analysis'):
        for f in (out.get(field) or {}).get('findings',[]):
            ids=set(f.get('player_master_ids',[]))|{f.get('player_master_id')}
            expired_f=bool(f.get('expires_at') and clock(f['expires_at'])<=clock(checked_at))
            if ids&blocked or expired_f:
                if field=='discovery':f.update(status='rejected',action=None)
                elif field=='weekly_role_review':f.update(status='rejected',discovery_action=None)
                else:f.update(status='rejected',action='none')
                changes.append(dict(kind='suppressed_finding',finding_id=f['finding_id'],reason='Fresh role/availability contradiction or research expiry'))
    if out.get('contrarian_analysis'):
        out['contrarian_analysis']['findings']=[f for f in out['contrarian_analysis']['findings'] if f['scenario_id'] not in removed_scenarios]
    if out.get('captain_analysis'):
        for group in ('captains','opponents'):
            for item in out['captain_analysis'].get(group,[]):
                evidence_ids={pid for e in item.get('evidence',{}).values() for pid in e.get('player_master_ids',[])}
                if item.get('player_master_id') in blocked or evidence_ids&blocked:
                    if group=='captains':item['mechanism_status']='unsupported'
                    else:item['capability']='unknown'
                    changes.append(dict(kind='weakened_captain_context',player_master_id=item.get('player_master_id'),reason='Fresh canonical role contradiction; prior context retained as unknown/unsupported.'))
    if preliminary_snapshot_sha256 and out.get('discovery'):
        old_binding=out['discovery']['scan_snapshot_sha256']
        if old_binding!=preliminary_snapshot_sha256:
            out['discovery']['scan_snapshot_sha256']=preliminary_snapshot_sha256
            for f in out['discovery']['findings']:
                if f['status']=='supported_provisional':f.update(status='watchlist',action=None)
            changes.append(dict(kind='discovery_recheck_required',reason='Deterministic scan bound to new preliminary snapshot; prior investigated actions downgraded to watchlist pending fresh semantic review.',original_snapshot_sha256=old_binding))
    missing=['Matchup truth, coaching intent and psychological effects require fresh semantic review; these checks do not supply it.',
             'Stored team-game outlook/model and research workload snapshots retain their original clocks; no re-fit or source refresh is claimed.',
             'Market quote age and final injury/role clearance remain governed by normal preparation and entry checks.']
    audit=dict(contract_id=CONTRACT,checked_at=checked_at,research_decision_at=packet['decision_at'],original_packet_sha256=packet_digest(packet),
        prepared_source_sha256=source_sha256,projection_run_id=projection_run_id,input_rows_sha256=digest(rows),
        game_binding={g['game_id']:next(b['game_id'] for b in games if game_key(b)==game_key(g)) for g in packet['games'] if g['game_id'] in scoped_ids},
        changes=changes,missing_checks=missing,semantic_research_refreshed=False,baseline_mutation=False)
    audit['machine_checks']=dict(canonical_rows=len(rows),salary_rows=sum(r.get('salary') is not None for r in rows),
        market_context_rows=sum(r.get('game_total_line') is not None or r.get('team_implied_total') is not None for r in rows),
        availability_rows=sum(bool(r.get('official_availability_status') or r.get('availability_status')) for r in rows),
        workload_proxy_rows=sum(r.get('projected_targets') is not None or r.get('projected_carries') is not None for r in rows),
        source_clocks='Original source row clocks remain in frozen preparation and research; current check is a separate clock.')
    audit['change_summary']=dict(roster_or_value_audit_count=sum(c['kind'] in {'contradicted','unknown','salary_changed','workload_changed','prepared_value_changed'} for c in changes),
        active_finding_change_count=sum(c['kind'] in {'suppressed_hypothesis','suppressed_construction','suppressed_scenario','suppressed_finding','weakened_captain_context','discovery_recheck_required'} for c in changes))
    if preliminary_snapshot_sha256:audit['preliminary_snapshot_sha256']=preliminary_snapshot_sha256
    out['preparation_compatibility']=audit
    if out.get('intent_scope'):
        out['intent_scope']['authored_scenario_ids']=out['intent_scope']['scenario_ids']
        out['intent_scope']['scenario_ids']=[s['scenario_id'] for s in out['scenario_assumptions']['scenarios']]
    out['packet_id']=packet['packet_id']+'-checked-'+digest(audit)[:12]
    # Decision/freeze belong to original research, never retimestamp its prose.
    errors=validate(out)
    usable=not errors and (not out.get('scenario_assumptions') or bool(out['scenario_assumptions']['scenarios']))
    return out,audit,usable,errors


def prepare_handoff(*,request,result,rows=None,row_loader=None,checked_at,packets=None,directory=None,preliminary_snapshot_sha256=None,optimization_intent='MIXED',personal_context_inputs=None):
    if optimization_intent not in {'MIXED','EXPECTED_GAME','CONTRARIAN'}:raise ValueError('Unknown Analyst optimization intent')
    mode=getattr(request,'analyst_mode','AUTO');strategy=getattr(request,'analyst_strategy','MERGED_SCENARIOS')
    fmt='SHOWDOWN' if request.contest_format=='showdown' else 'CLASSIC';games=result['source_manifest']['games']
    base=dict(contract_id=CONTRACT,mode=mode,scope=dict(season=request.season,week=request.week,slate=request.slate,format=fmt),checked_at=checked_at,
        source_packet_sha256=None,checked_packet_sha256=None,packet_id=None,research_decision_at=None,preferred_strategy=strategy,
        active_features=[],preferred_params={'analyst_discovery_enabled':True,'analyst_challenger_enabled':fmt=='CLASSIC','analyst_teammate_enabled':fmt=='CLASSIC'},changes=[],missing_checks=[],selection_candidates=[],prepared_source_sha256=result['source_sha256'],projection_run_id=result['projection_run_id'])
    if mode=='BASELINE':base.update(status='baseline_only',missing_checks=['Explicit baseline-only preparation; Analyst research is not applied.'])
    else:
        available=packets if packets is not None else published_packets(directory=directory)
        preferred=getattr(request,'analyst_packet_sha256',None)
        if mode=='MANUAL' and preferred in available and available[preferred].get('preparation_compatibility'):
            preferred=available[preferred]['preparation_compatibility']['original_packet_sha256']
        if mode=='MANUAL' and preferred not in available:raise ValueError('Manual Analyst packet is unavailable; import or select a published packet')
        eligible=[]
        for key,p in sorted(available.items()):
            if packet_digest(p)!=key:raise ValueError('Immutable Analyst packet hash mismatch')
            reasons=eligible_scope(p,season=request.season,week=request.week,fmt=fmt,games=games,checked_at=checked_at,strategy=strategy)
            if p.get('preparation_compatibility') or p.get('intent_scope'):reasons.append('checked_artifact_is_not_new_authored_research')
            base['selection_candidates'].append(dict(sha256=key,packet_id=p['packet_id'],status='rejected_scope' if reasons else 'candidate',reasons=reasons))
            if not reasons and (mode!='MANUAL' or key==preferred):eligible.append((key,p))
        if mode=='MANUAL' and not eligible:raise ValueError('Manual Analyst packet scope/clock/strategy is incompatible with preparation')
        if eligible and rows is None:rows=row_loader() if row_loader is not None else []
        for key,p in sorted(eligible,key=lambda item:(clock(item[1]['decision_at']),item[0]),reverse=True):
            if optimization_intent!='MIXED':
                from .analyst_intents import scope_packet
                try:
                    p=scope_packet(p,optimization_intent)
                except ValueError as exc:
                    candidate=next(c for c in base['selection_candidates'] if c['sha256']==key)
                    candidate.update(status='rejected_intent',reasons=[str(exc)])
                    continue
                scoped_receipt=import_packet(p,directory=directory)
                base['scoped_packet_sha256']=scoped_receipt['analyst_packet_sha256']
            checked,audit,usable,errors=revalidate(p,rows or [],games=games,fmt=fmt,checked_at=checked_at,source_sha256=result['source_sha256'],projection_run_id=result['projection_run_id'],preliminary_snapshot_sha256=preliminary_snapshot_sha256)
            candidate=next(c for c in base['selection_candidates'] if c['sha256']==key)
            candidate.update(status='checked_compatible' if usable else 'needs_review',reasons=errors or ([] if usable else ['no_active_research_scenarios']))
            if not usable:
                if not base['changes']:
                    base.update(source_packet_sha256=key,packet_id=p['packet_id'],research_decision_at=p['decision_at'],changes=audit['changes'],missing_checks=audit['missing_checks']+candidate['reasons'])
                if mode=='MANUAL':base.update(status='needs_review',source_packet_sha256=key,changes=audit['changes'],missing_checks=audit['missing_checks']+candidate['reasons']);break
                continue
            receipt=import_packet(checked,directory=directory)
            features=[name for name in ('scenario_assumptions','captain_analysis','team_game_outlook','discovery','weekly_role_review','defense_kicker_analysis','contrarian_analysis') if checked.get(name)]
            base.update(status='needs_review' if audit['changes'] else 'compatible',source_packet_sha256=key,checked_packet_sha256=receipt['analyst_packet_sha256'],packet_id=p['packet_id'],research_decision_at=p['decision_at'],
                active_features=features,changes=audit['changes'],missing_checks=audit['missing_checks']);break
        else:base.update(status='needs_review' if eligible else 'unavailable',missing_checks=base['missing_checks']+['No currently usable published Analyst packet matches this exact scope and requested strategy. Choose baseline explicitly or refresh research.'])
    if preliminary_snapshot_sha256:base['preliminary_snapshot_sha256']=preliminary_snapshot_sha256
    if optimization_intent!='MIXED':
        base['optimization_intent']=optimization_intent
        base['scenario_ids']=[s['scenario_id'] for s in checked['scenario_assumptions']['scenarios']] if base['checked_packet_sha256'] else []
    if personal_context_inputs is not None:
        from .analyst_personal_context import evaluate
        context_packet=load_packet(base['checked_packet_sha256'],directory=directory) if base['checked_packet_sha256'] else None
        base['personal_context']=evaluate(personal_context_inputs,scope=dict(season=request.season,week=request.week,slate=request.slate,contest_format=request.contest_format,objective=None),games=games,checked_at=checked_at,packet=context_packet)
    base['compatibility_sha256']=digest(base)
    return base


def handoff_for_intent(result,intent='MIXED'):
    return (result.get('analyst_intent_handoffs') or {}).get(intent) if intent!='MIXED' else result.get('analyst_handoff')


def bind_handoff(payload,result):
    """Server-owned exact prepared artifact; caller cannot forge its audit."""
    params=payload.setdefault('params',{});params.pop('analyst_handoff_applied',None)
    intent=params.get('analyst_optimization_intent','MIXED')
    if not isinstance(intent,str) or intent not in {'MIXED','EXPECTED_GAME','CONTRARIAN'}:raise ValueError('Unknown Analyst optimization intent')
    handoff=handoff_for_intent(result,intent)
    if intent!='MIXED' and (not handoff or handoff.get('optimization_intent')!=intent):
        raise ValueError('Prepare Slate again for the selected optimization intent; no mixed or baseline fallback is used')
    if intent!='MIXED' and params.get('analyst_handoff_mode','AUTO')!='AUTO':
        raise ValueError('Expected Game and Contrarian require automatic checked research')
    if not handoff:return  # Legacy preparations retain their previous API behavior.
    if digest({k:v for k,v in handoff.items() if k!='compatibility_sha256'})!=handoff['compatibility_sha256']:raise ValueError('Prepared Analyst compatibility hash mismatch')
    expected=params.get('analyst_handoff_compatibility_sha256')
    if expected and expected!=handoff['compatibility_sha256']:raise ValueError('Analyst preparation receipt changed; prepare/select again')
    scoped=handoff['scope']
    if any(payload.get(k) is not None and str(payload[k]).upper()!=str(scoped[k]).upper() for k in ('season','week','slate')) or (payload.get('contest_format') and payload['contest_format'].upper()!=scoped['format']):raise ValueError('Prepared Analyst handoff belongs to another scope/format')
    mode=params.get('analyst_handoff_mode',handoff.get('mode','AUTO'))
    if mode not in {'AUTO','MANUAL','BASELINE'}:raise ValueError('Unknown Analyst handoff mode')
    if mode=='BASELINE':
        if params.get('analyst_scenario_focus_mode')=='SELECTED_ONLY':raise ValueError('Baseline-only cannot retain a focused Analyst scenario')
        for key in ('analyst_packet_sha256','analyst_strategy','analyst_candidates_per_thesis','analyst_challenger_enabled','analyst_teammate_enabled','analyst_teammate_choice','analyst_discovery_enabled'):params.pop(key,None)
        params['analyst_handoff_applied']=dict(mode='BASELINE',compatibility_sha256=handoff['compatibility_sha256'],reason='explicit_baseline_only');return
    if not handoff.get('checked_packet_sha256'):raise ValueError('Prepared Analyst research unavailable; refresh research or choose baseline-only explicitly')
    chosen=params.get('analyst_packet_sha256')
    if chosen and chosen not in {handoff['source_packet_sha256'],handoff['checked_packet_sha256']}:raise ValueError('Selected Analyst packet differs from prepared research; Prepare Slate with the manual override')
    if payload.get('objective')=='cash' and params.get('analyst_strategy',handoff['preferred_strategy'])=='MERGED_SCENARIOS':raise ValueError('Merged Analyst research requires GPP; choose baseline-only explicitly for cash')
    params['analyst_packet_sha256']=handoff['checked_packet_sha256'];params.setdefault('analyst_strategy',handoff['preferred_strategy']);params.setdefault('analyst_candidates_per_thesis',2)
    if params.get('analyst_strategy')=='MERGED_SCENARIOS' and params.get('analyst_scenario_focus_mode','MIXED')=='MIXED':
        for key,value in handoff.get('preferred_params',{}).items():params.setdefault(key,value)
    if intent!='MIXED':
        params['analyst_intent_scenario_ids']=handoff['scenario_ids']
    params['analyst_handoff_applied']=dict(mode=mode,compatibility_sha256=handoff['compatibility_sha256'],source_packet_sha256=handoff['source_packet_sha256'],checked_packet_sha256=handoff['checked_packet_sha256'],checked_at=handoff['checked_at'],research_decision_at=handoff['research_decision_at'],status=handoff['status'],active_features=handoff['active_features'])

    if intent!='MIXED':params['analyst_handoff_applied'].update(optimization_intent=intent,scenario_ids=handoff['scenario_ids'],scoped_packet_sha256=handoff['scoped_packet_sha256'])
    if handoff.get('personal_context'):
        context=deepcopy(handoff['personal_context'])
        if any(item['resolved_scope'].get('objective') not in {None,payload.get('objective')} for item in context['considered']):raise ValueError('Personal thought approval belongs to another objective; Prepare Slate again')
        params['analyst_handoff_applied']['personal_context']=context



def bind_saved_preparation(session,payload):
    from ..models import OperationalJob
    job_id=(payload.get('params') or {}).get('prepared_input_job_id')
    if not job_id:return
    job=session.get(OperationalJob,job_id)
    if job and job.status=='completed':
        bind_handoff(payload,job.result_json or {})
        context=(payload.get('params',{}).get('analyst_handoff_applied') or {}).get('personal_context')
        if context and context.get('considered'):
            from .analyst_personal_context import load_inputs,validate_current
            from datetime import datetime,timezone
            validate_current(context,load_inputs(session.get_bind()),checked_at=datetime.now(timezone.utc).isoformat())


HANDOFF_LEDGER=Path('artifacts/analyst_preparation_handoffs')

def save_snapshot_handoff(snapshot,request,prepared,*,directory=None,personal_context_inputs=None):
    from datetime import datetime,timezone
    root=Path(directory) if directory is not None else HANDOFF_LEDGER;root.mkdir(parents=True,exist_ok=True)
    path=root/(snapshot['sha256']+'.json')
    if path.exists():return load_snapshot_handoff(snapshot['sha256'],directory=root)
    personal_inputs=personal_context_inputs if personal_context_inputs is not None else []
    handoff=prepare_handoff(request=request,result=prepared,rows=snapshot['pool'],checked_at=datetime.now(timezone.utc).isoformat(),preliminary_snapshot_sha256=snapshot['sha256'],personal_context_inputs=personal_inputs)
    if request.analyst_mode == 'AUTO':
        handoff['analyst_intent_handoffs'] = {intent: prepare_handoff(request=request, result=prepared,
            rows=snapshot['pool'], checked_at=datetime.now(timezone.utc).isoformat(),
            preliminary_snapshot_sha256=snapshot['sha256'], optimization_intent=intent,personal_context_inputs=personal_inputs)
            for intent in ('EXPECTED_GAME', 'CONTRARIAN')}
        handoff['compatibility_sha256'] = digest({k:v for k,v in handoff.items() if k!='compatibility_sha256'})
    with path.open('x') as handle:handle.write(json.dumps(handoff,indent=2)+'\n')
    return handoff


def load_snapshot_handoff(key,*,directory=None):
    import re
    if not re.fullmatch(r'[0-9a-f]{64}',key):raise ValueError('Invalid preliminary Analyst handoff identity')
    path=(Path(directory) if directory is not None else HANDOFF_LEDGER)/(key+'.json')
    if not path.exists():return None
    handoff=json.loads(path.read_text())
    if handoff.get('preliminary_snapshot_sha256')!=key or digest({k:v for k,v in handoff.items() if k!='compatibility_sha256'})!=handoff.get('compatibility_sha256'):raise ValueError('Preliminary Analyst handoff hash mismatch')
    return handoff
