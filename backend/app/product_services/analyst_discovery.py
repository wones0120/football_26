"""Reproducible all-game edge screening and bounded investigated finding actions.

Screened statistical anomalies are research candidates, never automatic truth or
projection bonuses. Semantic investigation is supplied through a sourced packet.
"""
from copy import deepcopy
import math
from pydantic import BaseModel,ConfigDict,Field
from .analyst_shadow import digest

CONTRACT='analyst_discovery_v1'

class DiscoveryControls(BaseModel):
    model_config=ConfigDict(extra='forbid')
    max_reserved_slots: int=Field(default=1,ge=0,le=3,strict=True)
    max_reserved_fraction: float=Field(default=.2,ge=0,le=.5,allow_inf_nan=False)
    minimum_strength: float=Field(default=.6,ge=.4,le=1,allow_inf_nan=False)
    maximum_opportunity_transfer: float=Field(default=.08,ge=0,le=.1,allow_inf_nan=False)


def number(row,key):
    value=row.get(key)
    return float(value) if type(value) in (int,float) and math.isfinite(value) else None


def scan(packet,rows):
    declared={p['player_master_id']:p for p in packet['players']};candidates=[];coverage=[]
    for game in packet['games']:
        if game.get('format_membership',{}).get('CLASSIC')!='confirmed_in_scope':continue
        members=[r for r in rows if r.get('canonical_game_id',r.get('game_id'))==game['game_id'] or (r.get('player_team',r.get('team')) in game['teams'] and r.get('opponent_team',r.get('opponent')) in game['teams'])]
        game_candidates=[]
        for row in members:
            pid=str(row['player_id']);player=declared.get(pid,{})
            source_ids=sorted(set(player.get('identity_source_ids',[]))|set((player.get('workload_evidence') or {}).get('lineage',{}).get('raw_usage_source_ids',[])))
            signals=[];included=[]
            for field,threshold in [('target_share_trend',.08),('rush_share_trend',.08),('snap_share_trend',.12)]:
                value=number(row,field)
                if value is not None and abs(value)>=threshold:signals.append(dict(kind='participation_shift',field=field,value=value,threshold=threshold));included.append(field)
            if row.get('pregame_newly_assigned_role') or row.get('role_change'):signals.append(dict(kind='role_change',field='pregame_newly_assigned_role',value=row.get('pregame_newly_assigned_role')));included.append('pregame_newly_assigned_role')
            targets=number(row,'projected_targets');salary=number(row,'salary');projection=number(row,'projection')
            if row.get('position') in {'WR','TE'} and targets is not None and targets>=5 and salary is not None and salary<=4500:
                signals.append(dict(kind='opportunity_salary_outlier',projected_targets=targets,salary=salary,base_mean=projection));included.extend(['projected_targets','salary'])
            if signals:
                item=dict(candidate_edge_id=game['game_id']+':'+pid,game_id=game['game_id'],player_master_ids=[pid],source_ids=source_ids,signals=signals,classification='statistical_outlier',automatic_status='watchlist',model_accounted_fields=sorted(set(included)),reason='These fields are present in canonical projection/context inputs; unusual values alone do not justify a second boost.',investigation_questions=['Is there a sourced role/alignment/protection or joint game mechanism beyond included fields?','What evidence contradicts it; can the opponent sustain the hypothesized game flow?','Is the action supported by complete opportunity lineage and current eligibility?'])
                game_candidates.append(item);candidates.append(item)
        teams={}
        for t in game['teams']:
            side=[r for r in members if r.get('player_team',r.get('team'))==t]
            teams[t]=dict(projected_qb_means=[number(r,'projection') for r in side if r['position']=='QB' and r.get('is_starting_qb') is not False],implied_totals=sorted({number(r,'team_implied_total') for r in side if number(r,'team_implied_total') is not None}))
        coverage.append(dict(game_id=game['game_id'],scanned_player_count=len(members),candidate_edge_ids=[c['candidate_edge_id'] for c in game_candidates],game_capability=teams,unknowns=['Defender alignment/coverage and protection evidence are not established by these projection rows.','Injury absence is not assumed healthy.']))
    return dict(contract_id='analyst_discovery_scan_v1',input_rows_sha256=digest(rows),decision_at=packet['decision_at'],scanned_games=coverage,candidate_edges=candidates,scan_sha256=digest(dict(coverage=coverage,candidates=candidates)),automatic_action='none; requires sourced investigation and model-delta review')


def validate_discovery(packet):
    block=packet.get('discovery');errors=[]
    if not isinstance(block,dict) or block.get('contract_id')!=CONTRACT:return ['unknown discovery contract']
    sources={s['source_id']:s for s in packet['sources']};players={p['player_master_id']:p for p in packet['players']};games={g['game_id'] for g in packet['games'] if g.get('format_membership',{}).get('CLASSIC')=='confirmed_in_scope'}
    from .analyst_packets import clock
    if set(block.get('scanned_game_ids',[]))!=games:errors.append('discovery must cover every Classic game')
    if not isinstance(block.get('scan_snapshot_sha256'),str) or len(block['scan_snapshot_sha256'])!=64:errors.append('discovery requires immutable scan snapshot hash')
    seen=set()
    for f in block.get('findings',[]):
        label=str(f.get('finding_id'))
        if not f.get('finding_id') or label in seen:errors.append('duplicate/missing discovery finding');seen.add(label)
        else:seen.add(label)
        if f.get('game_id') not in games:errors.append(label+': unknown game')
        pids=f.get('player_master_ids',[])
        if not pids or any(pid not in players or players[pid]['game_id']!=f.get('game_id') for pid in pids):errors.append(label+': unknown/out-of-game canonical player')
        refs=f.get('source_ids',[])
        if not refs or any(sid not in sources for sid in refs):errors.append(label+': missing/unknown source')
        try:
            asof=clock(f['as_of']);decision=clock(packet['decision_at'])
            if asof>decision:errors.append(label+': finding after decision')
            if any(sources.get(sid,{}).get('coverage')=='verified' and clock(sources[sid]['available_at'])>asof for sid in refs):errors.append(label+': source unavailable at finding clock')
        except (KeyError,TypeError,ValueError):errors.append(label+': invalid finding clock')
        if f.get('classification') not in {'statistical_outlier','hypothesized_model_blindspot'}:errors.append(label+': unknown classification')
        if f.get('status') not in {'supported_provisional','watchlist','rejected'}:errors.append(label+': unknown status')
        strength=f.get('evidence_strength')
        if type(strength) not in (int,float) or not math.isfinite(strength) or not 0<=strength<=1:errors.append(label+': invalid strength')
        accounting=f.get('model_accounting') or {}
        if accounting.get('status') not in {'already_accounted','partial','unmodeled','unknown'} or not accounting.get('rationale'):errors.append(label+': incomplete model accounting')
        if not f.get('mechanism') or not f.get('counterevidence') or not isinstance(f.get('unknowns'),list):errors.append(label+': missing mechanism/counterevidence/unknowns')
        action=f.get('action')
        if action:
            if set(action)-{'idea_id','required_player_ids','opportunity_share_transfer'}:errors.append(label+': unsupported action fields')
            required=action.get('required_player_ids',[])
            if not action.get('idea_id') or not 1<=len(required)<=2 or any(pid not in pids for pid in required):errors.append(label+': invalid bounded construction action')
            transfer=action.get('opportunity_share_transfer')
            if transfer and (transfer.get('channel') not in {'targets','carries'} or transfer.get('recipient_id') not in required or type(transfer.get('share')) not in (int,float) or not math.isfinite(transfer['share']) or not 0<transfer['share']<=.1):errors.append(label+': invalid bounded target transfer')
        if f.get('status')=='supported_provisional':
            if f.get('classification')!='hypothesized_model_blindspot' or accounting.get('status') not in {'partial','unmodeled'} or not accounting.get('delta_fields') or not action:errors.append(label+': supported finding requires distinct model delta and action')
            if any(sources.get(sid,{}).get('coverage')!='verified' for sid in refs):errors.append(label+': supported finding has unavailable source')
    return errors


def prepare_actions(packet,rows,ideas,requested,params):
    controls=DiscoveryControls.model_validate(params.get('analyst_discovery_controls') or {});report=scan(packet,rows);report.update(controls=controls.model_dump(),findings=[],reserved_idea_ids=[])
    from .weekly_role_review import discovery_findings
    weekly=discovery_findings(packet)
    from .analyst_packets import clock
    expires={f['finding_id']:f['expires_at'] for f in (packet.get('weekly_role_review') or {}).get('findings',[])}
    weekly=[f for f in weekly if clock(expires[f['finding_id'].removeprefix('weekly:')])>clock(params.get('data_cutoff_at') or packet['decision_at'])]
    original_block=packet.get('discovery')
    block={'findings':weekly+list((original_block or {}).get('findings',[]))} if weekly or original_block else None
    if not block or params.get('analyst_discovery_enabled',True) is False:
        report['status']='screen_only' if not block else 'explicitly_disabled_comparison';return report
    by_id={str(r['player_id']):r for r in rows};by_idea={i['idea_id']:i for i in ideas};limit=min(controls.max_reserved_slots,math.floor(requested*controls.max_reserved_fraction))
    for f in sorted(block['findings'],key=lambda f:(-f['evidence_strength'],f['finding_id'])):
        entry=deepcopy(f);action=f.get('action') or {};idea=by_idea.get(action.get('idea_id'));reason=None
        if f['status']!='supported_provisional':reason='watchlist/rejected investigation; no action'
        elif f.get('classification')!='hypothesized_model_blindspot' or f.get('model_accounting',{}).get('status') not in {'partial','unmodeled'} or not f.get('model_accounting',{}).get('delta_fields'):reason='already accounted or no distinct investigated model delta'
        elif f['evidence_strength']<controls.minimum_strength:reason='below configured evidence threshold'
        elif not idea:reason='requested construction idea lacks credible source/role capability'
        elif any(pid not in by_id for pid in action['required_player_ids']):reason='required player ineligible/excluded/unprojected; hard preferences retained'
        elif any(by_id[pid].get('player_team',by_id[pid].get('team'))!=idea['team'] for pid in action['required_player_ids']):reason='required player conflicts with primary idea team'
        elif len(report['reserved_idea_ids'])>=limit:reason='bounded reserved-slot budget exhausted'
        elif idea['idea_id'] in report['reserved_idea_ids']:reason='duplicate idea already reserved'
        transfer=action.get('opportunity_share_transfer')
        if transfer and transfer['share']>controls.maximum_opportunity_transfer:reason='transfer exceeds configured bound'
        if reason:entry.update(action_status='no_action',decision_reason=reason)
        else:
            idea['discovery_max_lineups']=1;idea['discovery_finding_ids']=[f['finding_id']];idea['discovery_required_player_ids']=action['required_player_ids'];idea['discovery_opportunity_transfer']=transfer
            report['reserved_idea_ids'].append(idea['idea_id']);entry.update(action_status='reserved_before_generation',decision_reason='Sourced provisional model-delta finding reserves a bounded football idea slot; hard legality and actual feasibility remain enforced')
        report['findings'].append(entry)
    report['status']='investigated';return report


def apply_opportunity_transfer(world,idea,rows):
    transfer=idea.get('discovery_opportunity_transfer')
    if not transfer:return
    pid=transfer['recipient_id'];channel=transfer['channel'];members=[r for r in rows if r.get('player_team',r.get('team'))==idea['team'] and r['position'] in ({'RB'} if channel=='carries' else {'RB','WR','TE'})]
    values={str(r['player_id']):number(r,'projected_'+channel) for r in members}
    if any(v is None or v<0 for v in values.values()) or pid not in values or sum(values.values())<=0:raise ValueError('Discovery opportunity transfer requires complete attributed projected opportunity budget')
    total=sum(values.values());base={p:v/total for p,v in values.items()};share=transfer['share'];donor_mass=1-base[pid]
    if base[pid]<=0 or donor_mass<share:raise ValueError('Discovery opportunity transfer lacks positive recipient or donor mass')
    conditional={p:(v+share if p==pid else v*(1-share/donor_mass)) for p,v in base.items()}
    if any(v>0 and not .5<=conditional[p]/v<=2 for p,v in base.items()):raise ValueError('Discovery opportunity transfer exceeds coherent ratio bounds')
    for p,v in base.items():
        ratio=conditional[p]/v if v else 1;moment=world['moments'][p];row=next(r for r in members if str(r['player_id'])==p);targets=number(row,'projected_targets') or 0;carries=number(row,'projected_carries') or 0;receiving_weight=targets/(targets+carries) if targets+carries else 1;component_weight=receiving_weight if channel=='targets' else 1-receiving_weight;response=1+.7*component_weight*(ratio-1);spread=moment['p90']-moment['mean'];moment['mean']*=response;moment['p90']=moment['mean']+spread*math.sqrt(response);moment['changes'].append(dict(discovery_finding_ids=idea['discovery_finding_ids'],channel=channel,projected_share_before=v,conditional_share=conditional[p],ratio=ratio,elasticity=.7,lineage='Frozen canonical projected opportunity;  conditional conserved reallocation, not new measured truth'))
    world['discovery_opportunity_budget']=dict(channel=channel,budget_scope='eligible RB carries' if channel=='carries' else 'eligible skill targets',base_shares=base,conditional_shares=conditional,sum_before=sum(base.values()),sum_after=sum(conditional.values()),recipient_id=pid,transfer_share=share)
