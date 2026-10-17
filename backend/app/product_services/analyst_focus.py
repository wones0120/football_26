"""Explicit scenario-only construction; facts and declared football what-ifs stay separate."""
from copy import deepcopy
from .analyst_packets import clock

CONTRACT='contrarian_analysis_v1'


def validate_contrarian(packet):
    block=packet.get('contrarian_analysis')
    if block is None:return []
    errors=[];scenarios={s['scenario_id']:s for s in (packet.get('scenario_assumptions') or {}).get('scenarios',[])};games={g['game_id']:g for g in packet['games']};sources={s['source_id']:s for s in packet['sources']}
    if block.get('contract_id')!=CONTRACT:return ['unknown contrarian contract']
    seen=set()
    for f in block.get('findings',[]):
        sid=f.get('scenario_id');gid=f.get('game_id');team=f.get('team')
        if sid not in scenarios or sid in seen:errors.append('contrarian scenario identity missing/duplicate')
        seen.add(sid)
        if gid not in games or team not in games.get(gid,{}).get('teams',[]):errors.append('contrarian game/team outside canonical scope')
        if f.get('script') not in {'passing','run_control'}:errors.append('unsupported contrarian construction')
        if f.get('status') not in {'supported_hypothesis','user_what_if','watchlist'}:errors.append('contrarian status required')
        if any(k in f for k in ['probability','fantasy_point_bonus','confidence_score']):errors.append('contrarian fake probability/point bonus prohibited')
        if not all(f.get(k) for k in ['mechanism','conditions','counterevidence','unknowns']):errors.append('contrarian mechanism/conditions/counterevidence/unknowns required')
        refs=f.get('source_ids',[])
        if not refs or any(s not in sources for s in refs):errors.append('contrarian source lineage missing')
        if f.get('status')=='supported_hypothesis' and not any(sources.get(ref,{}).get('coverage')=='verified' for ref in refs):errors.append('supported contrarian hypothesis requires verified source context')
        if sid in scenarios and not any(a['game_id']==gid and a['team']==team and a['kind']==('passing_volume' if f.get('script')=='passing' else 'rushing_volume') and a['factor']>1 for a in scenarios[sid]['assumptions']):errors.append('contrarian finding is not bound to its positive game/team opportunity channel')
        try:
            asof=clock(f['as_of'])
            if asof>clock(packet['decision_at']) or any(clock(sources[s]['available_at'])>asof for s in refs if s in sources):errors.append('contrarian evidence after decision')
        except (KeyError,ValueError,TypeError):errors.append('contrarian chronology invalid')
        shift=f.get('opportunity_shift',.12)
        if type(shift) not in (int,float) or not .05<=shift<=.25:errors.append('contrarian opportunity shift outside bounded .05–.25')
        target=f.get('team_points_target')
        if target is not None and (type(target) not in (int,float) or not 0<target<=60 or f.get('status')!='user_what_if'):errors.append('team points target must be bounded explicit user what-if')
    return errors


def prepare_focus(packet,params,fmt):
    mode=params.get('analyst_scenario_focus_mode','MIXED');ids=params.get('analyst_scenario_focus_ids') or []
    if mode!='SELECTED_ONLY':
        optional={f['scenario_id'] for f in (packet.get('contrarian_analysis') or {}).get('findings',[]) if f['status']=='user_what_if'}
        out=deepcopy(packet) if optional else packet
        if optional:
            out['scenario_assumptions']['scenarios']=[s for s in out['scenario_assumptions']['scenarios'] if s['scenario_id'] not in optional]
            out['contrarian_analysis']['findings']=[f for f in out['contrarian_analysis']['findings'] if f['scenario_id'] not in optional]
        return out,dict(contract_id='analyst_focus_v1',mode='MIXED',selected_scenario_ids=[],inactive_explicit_user_what_if_ids=sorted(optional))
    scenarios={s['scenario_id']:s for s in packet['scenario_assumptions']['scenarios']}
    if not ids or any(s not in scenarios for s in ids):raise ValueError('Selected-only focus requires existing canonical packet scenario IDs')
    out=deepcopy(packet);out['scenario_assumptions']['scenarios']=[scenarios[s] for s in ids];requirements=[]
    if out.get('contrarian_analysis'):out['contrarian_analysis']['findings']=[f for f in out['contrarian_analysis']['findings'] if f['scenario_id'] in ids]
    findings={f['scenario_id']:f for f in (packet.get('contrarian_analysis') or {}).get('findings',[])}
    for sid in ids:
        s=scenarios[sid];gids={a['game_id'] for a in s['assumptions']}
        if len(gids)!=1:raise ValueError('Focused construction requires a single game story; composite stress scenarios are not selectable constructions')
        f=findings.get(sid)
        if f and f['status']=='watchlist':raise ValueError('Watchlist contrarian finding cannot authorize selected-only construction')
        positive=[a for a in s['assumptions'] if a['kind'] in {'passing_volume','rushing_volume'} and a['factor']>1]
        if not positive:raise ValueError('Focused story has no supported positive opportunity channel')
        a=max(positive,key=lambda a:a['factor']);requirement=dict(opportunity_shift=(f or {}).get('opportunity_shift',.12),scenario_id=sid,game_id=next(iter(gids)),team=f['team'] if f else a['team'],script=f['script'] if f else 'passing' if a['kind']=='passing_volume' else 'run_control',authority=f['status'] if f else 'existing_typed_packet_hypothesis',finding=deepcopy(f),probability_status='uncalibrated hypothesis; ownership leverage not inferred')
        s=deepcopy(s);s['focus_requirement']=requirement;out['scenario_assumptions']['scenarios'][ids.index(sid)]=s;requirements.append(requirement)
    return out,dict(contract_id='analyst_focus_v1',mode=mode,selected_scenario_ids=ids,requirements=requirements,generic_fallback=False)


def require_story(model,variables,mapping,rows,requirement):
    """Same hard legal model; every selected roster expresses this football story."""
    import pulp
    by_id={str(r['player_id']):r for r in rows};team=requirement['team']
    own={pid:r for pid,r in by_id.items() if r.get('player_team',r.get('team'))==team}
    def terms(positions):return [variables[n] for n,ref in mapping.items() if ref['player_master_id'] in own and own[ref['player_master_id']]['position'] in positions]
    captain_terms=[variables[n] for n,ref in mapping.items() if ref['role']=='CPT' and ref['player_master_id'] in own and own[ref['player_master_id']]['position'] in ({'QB','WR','TE'} if requirement['script']=='passing' else {'RB'})]
    if any(ref['role']=='CPT' for ref in mapping.values()):
        if not captain_terms:raise ValueError('Focused story lacks a legal relevant Captain')
        model+=pulp.lpSum(captain_terms)==1
    if requirement['script']=='passing':
        qb=terms({'QB'});receiver=terms({'WR','TE'})
        if not qb or not receiver:raise ValueError('Focused passing story lacks legal QB/receiver')
        model+=pulp.lpSum(qb)>=1;model+=pulp.lpSum(receiver)>=1
    else:
        backs=terms({'RB'})
        if not backs:raise ValueError('Focused running story lacks legal RB')
        model+=pulp.lpSum(backs)>=1
    return dict(team=team,script=requirement['script'],hard_requirements='own QB plus receiver' if requirement['script']=='passing' else 'own running back',forced_opponent_bringback=False)


def audit_story(roster,rows,requirement):
    by_id={str(r['player_id']):r for r in rows};own=[by_id[p['player_master_id']] for p in roster if by_id[p['player_master_id']].get('player_team',by_id[p['player_master_id']].get('team'))==requirement['team']];positions={r['position'] for r in own}
    captains=[by_id[p['player_master_id']] for p in roster if p['role']=='CPT']
    if captains and (captains[0].get('player_team',captains[0].get('team'))!=requirement['team'] or captains[0]['position'] not in ({'QB','WR','TE'} if requirement['script']=='passing' else {'RB'})):return False
    return requirement['script']=='passing' and 'QB' in positions and bool(positions&{'WR','TE'}) or requirement['script']=='run_control' and 'RB' in positions


def focused_world(scenario,rows,packet):
    """Fixed conserved game hypothesis shared across Captain labels."""
    from .scenario_allocation import conditional_world,AllocationControls
    requirement=scenario.get('focus_requirement')
    if not requirement:return scenario
    gid=requirement['game_id'];game=next(g for g in packet['games'] if g['game_id']==gid)
    idea=dict(idea_id=scenario['scenario_id'],game_id=gid,team=requirement['team'],opponent=next(t for t in game['teams'] if t!=requirement['team']),script=requirement['script'],label=scenario['label'],hypothesis_ids=scenario['hypothesis_ids'])
    world=conditional_world(idea,rows,packet,AllocationControls(opportunity_shift=requirement['opportunity_shift']))
    scenario=deepcopy(scenario);scenario.update(moments=world['moments'],opportunity_budget=world['opportunity_budget'],focused_math='Selected shared conserved opportunity mix, component-weighted0.7 response; Captain identity changes roster multiplier, not the football world',team_points_target_status='Condition to investigate, not a forecast or probability')
    return scenario


def scan_contrarian(packet,rows,*,fmt,decision_at):
    """Deterministic all-game investigation handoff, never an invented edge bonus."""
    authored=(packet.get('contrarian_analysis') or {}).get('findings',[]);games=[];candidates=[]
    for game in packet['games']:
        if game.get('format_membership',{}).get(fmt)!='confirmed_in_scope':continue
        members=[r for r in rows if r.get('player_team',r.get('team')) in game['teams'] and r.get('opponent_team',r.get('opponent')) in game['teams']]
        ids={str(r['player_id']) for r in members};local=[f for f in authored if f['game_id']==game['game_id']]
        games.append(dict(game_id=game['game_id'],scanned_canonical_players=len(ids),authored_findings=len(local)))
        for team in game['teams']:
            qbs=[r for r in members if r.get('player_team',r.get('team'))==team and r['position']=='QB' and r.get('canonical_role')=='expected_starter']
            pass_catchers=[r for r in members if r.get('player_team',r.get('team'))==team and r['position'] in {'WR','TE'} and float(r.get('projected_targets') or 0)>0]
            matches=[f for f in local if f['team']==team]
            candidates.append(dict(game_id=game['game_id'],team=team,status='authored_hypothesis' if matches else 'watchlist_research_required',findings=deepcopy(matches),canonical_qb_ids=[str(r['player_id']) for r in qbs],canonical_receiver_ids=[str(r['player_id']) for r in pass_catchers],mechanism='Investigate a shared passing breakout versus current central forecast; starter/targets alone do not establish protection, QB improvement or opponent competitiveness',counterevidence=['Source-backed current protection/coverage/drive changes may be missing; do not invent them.','A strong central projection is not evidence of a model blind spot.'],ownership_status='not asserted low-owned; football alternative and ownership leverage are distinct'))
    return dict(contract_id=CONTRACT,decision_at=decision_at,scanned_games=games,candidates=candidates,automatic_projection_mutation=False,automatic_action='Only separately typed supported hypotheses or explicit user what-ifs can authorize selected-only construction; screening alone is watchlist')
