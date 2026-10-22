"""Conditional opportunity scenarios and portfolio coverage; never base-model edits.

Volume responses use declared elasticity. Concentration conserves team target
volume; transfers conserve specified workload. Missing measurements remain explicit.
Equal scenario weights and the uncertainty response are research design assumptions,
not calibrated probabilities or a fitted fantasy scoring model.
"""
from copy import deepcopy
from datetime import datetime, timezone
import math

import pulp

from .analyst_packets import validate, clock, packet_digest
from .analyst_shadow import digest
from .cbc_solver import make_cbc_solver

STRATEGY = 'MERGED_SCENARIOS'
KINDS = {'passing_volume', 'rushing_volume', 'target_concentration', 'workload_transfer'}


def _solver():
    solver=make_cbc_solver()
    solver.options.extend(['randomSeed 7','randomCbcSeed 7'])
    return solver


def validate_scenarios(packet):
    errors = []
    block = packet.get('scenario_assumptions')
    if not isinstance(block, dict) or block.get('contract_id') != 'analyst_scenarios_v1':
        return ['Merged strategy requires analyst_scenarios_v1 scenario_assumptions']
    scenarios = block.get('scenarios')
    if not isinstance(scenarios, list) or not 1 <= len(scenarios) <= 24:
        return ['scenario count must be 1 through 24']
    players = {p['player_master_id']: p for p in packet.get('players', [])}
    hypotheses = {h['hypothesis_id']: h for h in packet.get('hypotheses', [])}
    games = {g['game_id']: g for g in packet.get('games', [])}
    ids = set()
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            errors.append('scenario must be an object'); continue
        sid = scenario.get('scenario_id')
        if not isinstance(sid, str) or not sid or sid in ids: errors.append('missing/duplicate scenario_id')
        ids.add(sid)
        if not scenario.get('label'): errors.append('scenario requires a label')
        if scenario.get('team_game_branch') is not None and (scenario['team_game_branch'] not in {'competitive_scoring','trailing_productive_passing','drive_stall_runout','other'} or packet.get('team_game_outlook') is None):errors.append('team branch requires supported saved outlook')
        if any(key in scenario for key in ('captain_player_master_id','opponent_capability_branch','design_contract')):
            errors.append('Captain conditioning requires the versioned captain_analysis contract')
        if any(key in scenario for key in ('probability','scenario_weight','confidence_score','fantasy_point_bonus')): errors.append('scenario probabilities/bonuses are not supported')
        refs = scenario.get('hypothesis_ids')
        if not isinstance(refs, list) or not refs or any(h not in hypotheses for h in refs):
            errors.append('scenario requires known hypothesis_ids')
        assumptions = scenario.get('assumptions')
        if not isinstance(assumptions, list) or not 1 <= len(assumptions) <= 24:
            errors.append('scenario requires 1 through 24 assumptions'); continue
        touched = set()
        for a in assumptions:
            if not isinstance(a, dict): errors.append('assumption must be an object'); continue
            kind = a.get('kind'); gid = a.get('game_id'); team = a.get('team')
            common={'kind','game_id','team','elasticity'}
            allowed=common|({'factor'} if kind in {'passing_volume','rushing_volume'} else {'player_master_ids','share_delta'} if kind=='target_concentration' else {'workload','fraction','from_player_master_id','to_player_master_id'})
            if set(a)-allowed: errors.append('unsupported assumption field')
            if kind not in KINDS: errors.append('unsupported opportunity assumption')
            if gid not in games or team not in games.get(gid, {}).get('teams', []): errors.append('assumption outside game/team scope')
            if refs and not any(hypotheses.get(h, {}).get('game_id') == gid for h in refs): errors.append('assumption lacks game hypothesis lineage')
            def number(key, low, high):
                value = a.get(key)
                ok = type(value) in (int, float) and math.isfinite(value) and low <= value <= high
                if not ok: errors.append(key + ': finite bounded value required')
            number('elasticity', 0, 1)
            if kind in {'passing_volume', 'rushing_volume'}: number('factor', .5, 1.5)
            elif kind == 'target_concentration': number('share_delta', -.15, .15)
            elif kind == 'workload_transfer':
                number('fraction', 0, .5)
                if a.get('workload') not in {'targets', 'carries'}: errors.append('transfer workload must be targets or carries')
                if a.get('from_player_master_id') == a.get('to_player_master_id'): errors.append('transfer identities must differ')
            pids = a.get('player_master_ids', []) if kind == 'target_concentration' else ([a.get('from_player_master_id'), a.get('to_player_master_id')] if kind == 'workload_transfer' else [])
            if kind == 'target_concentration' and (not isinstance(pids, list) or not pids): errors.append('concentration requires canonical player_master_ids'); pids=[]
            for pid in pids:
                if pid not in players or players[pid].get('team') != team or players[pid].get('game_id') != gid: errors.append('assumption canonical identity outside game/team')
            # Avoid contradictory/double-counted changes to the same opportunity.
            channel = 'targets' if kind in {'passing_volume', 'target_concentration'} else a.get('workload', 'carries')
            key = (gid, team, channel, kind)
            if key in touched: errors.append('duplicate opportunity assumption in scenario')
            touched.add(key)
    return errors


def _measurement(player, channel, decision):
    evidence = player.get('workload_evidence') or {}
    lineage={**(evidence.get('lineage') or {}),**(evidence.get('explicit_pregame_lineage') or {})}
    for key,value in lineage.items():
        if value and key.endswith(('_at','_cutoff')):
            try: observed=clock(value)
            except (TypeError,ValueError): return None, 'unverified_workload_chronology'
            if observed>decision: raise ValueError('future workload evidence')
    from .workload_evidence import select_measurement
    return select_measurement(player, channel)


def build_scenarios(packet, rows, *, fmt, decision_at, mean_only=False, measurement_rows=None, count_receipt=None):
    errors = validate(packet) + validate_scenarios(packet)
    if errors: raise ValueError('; '.join(errors))
    decision = clock(decision_at)
    if clock(packet['frozen_at']) > decision: raise ValueError('scenario packet is future-sourced')
    declared = {p['player_master_id']: p for p in packet['players']}
    by_id = {str(r.get('player_id',r.get('player_master_id'))): r for r in rows}
    if len(by_id) != len(rows): raise ValueError('duplicate canonical pool identity')
    full_rows=rows if measurement_rows is None else measurement_rows
    source_by_id={str(r.get('player_id',r.get('player_master_id'))):r for r in full_rows}
    if len(source_by_id)!=len(full_rows) or not set(by_id)<=set(source_by_id):
        raise ValueError('Scenario measurement universe has duplicate or missing canonical actors')
    games = {g['game_id']:g for g in packet['games']}
    result=[]
    for scenario in packet['scenario_assumptions']['scenarios']:
        gids={a['game_id'] for a in scenario['assumptions']}
        if any(games[g].get('format_membership',{}).get(fmt) != 'confirmed_in_scope' for g in gids): continue
        if any(clock(games[g]['kickoff_at']) <= decision for g in gids): raise ValueError('scenario is not pregame')
        if any(clock(h['expires_at']) <= decision for h in packet['hypotheses'] if h['hypothesis_id'] in scenario['hypothesis_ids']): raise ValueError('scenario hypothesis expired')
        moments={}
        for pid,r in by_id.items():
            try:
                mean=float(r['projection'])
                try:p90=float(r.get('p90',r.get('ceiling')))
                except (TypeError,ValueError):p90=None
            except (TypeError,ValueError) as exc: raise ValueError('missing base scenario moments') from exc
            if not math.isfinite(mean) or mean<0:raise ValueError('invalid base scenario moments')
            if p90 is None or not math.isfinite(p90) or p90<0:
                if not mean_only:raise ValueError('invalid base scenario moments')
                p90=None
            moments[pid]=dict(mean=mean,p90=max(mean,p90) if p90 is not None else None,
                opportunity_ratio=1.0,changes=[],workload={},**({'tail_status':'unavailable_not_imputed'} if p90 is None else {}))
        if count_receipt is not None and count_receipt.get('component_response'):
            from .count_scenario_response import count_world
            response=count_world(count_receipt,scenario,{pid:r.get('projection') for pid,r in source_by_id.items()},cutoff=decision_at)
            by_actor={a['player_master_id']:a for a in response['response']['players']}
            for pid,moment in moments.items():
                actor=by_actor.get(pid)
                if actor is None:continue  # K/DST/absent actors preserve base, explicitly unmodeled.
                if actor['conditional_mean'] is not None:moment['mean']=actor['conditional_mean']
                moment.update(p90=None,tail_status='conditional_tail_unmodeled',
                    component_response=actor,response_ancestry=response['version'],
                    changes=response['changes'],conditional_delta_points=actor['conditional_delta_points'])
            result.append(dict(**deepcopy(scenario),moments=moments,count_component_response=response,
                measurement_universe_sha256=digest(full_rows),design_weight=1,probability_status='conditional_likelihood_unknown'))
            continue
        budgets=[]
        for a in scenario['assumptions']:
            members=[pid for pid,r in source_by_id.items() if r.get('player_team',r.get('team'))==a['team'] and r.get('opponent_team',r.get('opponent')) in games[a['game_id']]['teams']]
            channel='targets' if a['kind'] in {'passing_volume','target_concentration'} else a.get('workload','carries')
            if not members: raise ValueError('scenario game/team is absent from source measurement universe')
            measured={pid:_measurement(declared.get(pid,source_by_id[pid]),channel,decision) for pid in members}
            ratios={}
            if a['kind'] in {'passing_volume','rushing_volume'}:
                positions={'QB','WR','TE','RB'} if channel=='targets' else {'RB','QB'}
                ratios={pid:a['factor'] for pid in members if source_by_id[pid]['position'] in positions}
            else:
                if any(measured[pid][0] is None for pid in members if source_by_id[pid]['position'] in {'RB','WR','TE'}):
                    raise ValueError('concentration/transfer requires complete measured or explicitly attributed proxy workload for team skill players')
                amounts={pid:value for pid,(value,_) in measured.items() if value is not None}
                total=sum(amounts.values()); updated=dict(amounts)
                if a['kind']=='target_concentration':
                    targets=set(a['player_master_ids'])
                    if not targets <= set(amounts): raise ValueError('scenario concentration identity missing from eligible measured pool')
                    target_total=sum(amounts[p] for p in targets); rest=total-target_total
                    delta=a['share_delta']*total
                    if target_total<=0 or rest<=0 or target_total+delta<0 or rest-delta<0: raise ValueError('concentration exceeds available workload')
                    updated={pid:value*((target_total+delta)/target_total if pid in targets else (rest-delta)/rest) for pid,value in amounts.items()}
                else:
                    donor=a['from_player_master_id']; receiver=a['to_player_master_id']
                    if donor not in amounts or receiver not in amounts or amounts[receiver]<=0: raise ValueError('transfer identity lacks positive measured baseline workload')
                    moved=amounts[donor]*a['fraction']; updated[donor]-=moved; updated[receiver]+=moved
                ratios={pid:updated[pid]/value for pid,value in amounts.items() if value>0}
                budgets.append(dict(assumption=deepcopy(a),full_source_actor_ids=sorted(members),
                    excluded_from_selection_actor_ids=sorted(set(members)-set(by_id)),
                    workload_before=amounts,workload_after=updated,total_before=total,total_after=sum(updated.values()),
                    meaning='Source-universe conditional sensitivity; user exclusions never create or redistribute football workload'))
                if any(ratio>2 or ratio<0 for ratio in ratios.values()): raise ValueError('workload ratio exceeds bounded 0 through 2 response')
            for pid,ratio in ratios.items():
                if pid not in moments:continue
                moment=moments[pid]; response=1+a['elasticity']*(ratio-1)
                moment['opportunity_ratio']*=response
                moment['changes'].append(dict(assumption=deepcopy(a),workload_before=measured.get(pid,(None,''))[0],workload_lineage=measured.get(pid,(None,'unavailable'))[1],ratio=ratio,response=response))
        for pid,m in moments.items():
            ratio=m['opportunity_ratio']; base=by_id[pid]
            if not math.isfinite(ratio) or not 0<=ratio<=2: raise ValueError('combined opportunity response exceeds bounded 0 through 2 range')
            m['mean']=float(base['projection'])*ratio
            m['p90']=(m['mean']+max(0,m['p90']-float(base['projection']))*math.sqrt(ratio)) if m['p90'] is not None else None
        result.append(dict(**deepcopy(scenario),moments=moments,source_workload_budgets=budgets,
            measurement_universe_sha256=digest(full_rows),design_weight=1,probability_status='uncalibrated_equal_design_weights'))
    if not result: raise ValueError('No applicable scenarios in selected format')
    from .team_game_outlook import attach_context
    return attach_context(packet,result,decision_at=decision_at,rows=rows)


def projection_distribution_pool(pool, *, mean_only=False):
    """Missing forecasts are unscored model eligibility, never a zero estimate."""
    def valid(value):
        try: return math.isfinite(float(value)) and float(value)>=0
        except (ValueError,TypeError): return False
    keep=[];excluded=[]
    for index,row in pool.iterrows():
        mean=row.get('projection');p90=row.get('p90',row.get('ceiling'))
        if valid(mean) and (mean_only or valid(p90)): keep.append(index)
        else: excluded.append(dict(player_master_id=str(row.get('player_id',row.get('player_master_id'))),
            reason='missing_or_invalid_base_projection_distribution',base_projection=mean,base_p90=p90))
    return pool.loc[keep].copy(deep=True).reset_index(drop=True),excluded


def _research_explanations(report, lineups, params):
    """Saved full-roster consumer proof, separate from the scenario objective."""
    handoff = params.get('analyst_handoff_applied') or {}
    coverage = handoff.get('research_coverage')
    if not coverage:
        return
    worlds = {s['scenario_id']: s for s in report.get('scenario_definitions', [])}
    material = {sid for sid, world in worlds.items()
                if any(m.get('changes') and (m.get('opportunity_ratio', 1) != 1 or m.get('conditional_delta_points',0) != 0)
                       for m in world.get('moments', {}).values())}
    games = []
    for game in coverage.get('games', []):
        assessment = game.get('authored_assessment') or {}
        games.append({**deepcopy(game),
            'material_scenario_ids_consumed': sorted(set(assessment.get('scenario_ids', [])) & material),
            'interpretation': 'Conditional sensitivity; occurrence likelihood unknown. An explicit no-change assessment does not claim a numerical effect.'})
    receipt = dict(coverage=deepcopy(coverage), games=games,
        source_packet_sha256=handoff.get('source_packet_sha256'),
        checked_packet_sha256=handoff.get('checked_packet_sha256'),
        compatibility_sha256=handoff.get('compatibility_sha256'),
        pending_requests=deepcopy(handoff.get('research_requests', [])),
        baseline_comparison_roster=deepcopy(report.get('baseline_comparison_roster')),
        alternative_status='same_legal_model_reference' if report.get('baseline_comparison_roster') else 'not_captured_by_this_generation_path',
        portfolio_dependency='All entries share these conditional game worlds; this is not a calibrated joint success probability.')
    report['research_consumption'] = receipt
    for lineup in lineups:
        if not lineup:
            continue
        lineup[0]['analyst_research_explanation'] = dict(
            research_consumption=receipt,
            selected_scenario_ids=lineup[0].get('analyst_thesis_ids', []),
            canonical_roster=[dict(player_master_id=str(p['player_id']),
                role=p.get('roster_position', 'SELECTED'), salary=p.get('salary')) for p in lineup],
            salary=sum(float(p.get('salary') or 0) for p in lineup),
            base_mean_sum=sum(float(p.get('projection') or 0) for p in lineup),
            meaning='Complete saved legal roster; base fantasy means and user controls remain unchanged. Scenario mechanisms, shared risks and the reference alternative are retained separately.')


def run_merged(service, pool, *, params, packet, fmt, season, week, slate, requested, solve_kwargs, progress=None, source_pool_rows=None, research_only_joint_opportunity=False):
    """Capture legal prepared constraints; replace objective before generation.

    Exact roster replay restores base projection fields for persisted output. The
    baseline candidate is a comparison only and cannot approve/veto a scenario.
    """
    if params.get('analyst_joint_opportunity_enabled') and not research_only_joint_opportunity:
        raise ValueError('Joint opportunity prototype is inactive pending empirical and scenario audit review; isolated research only')
    from .analyst_generation import ModelCaptured, runtime_snapshot
    from .optimizer import _json_safe
    now=datetime.now(timezone.utc).isoformat()
    from .shared_world_selection import POLICY as SHARED_WORLD_POLICY
    shared_world=params.get('analyst_selection_policy')==SHARED_WORLD_POLICY
    if shared_world and (params.get('analyst_scenario_focus_mode','MIXED')!='MIXED' or params.get('analyst_teammate_choice')):
        raise ValueError('Shared-world coverage cannot silently combine a manual story or teammate construction')
    intent=params.get('analyst_optimization_intent','MIXED')
    intent_scope=None
    if intent!='MIXED' and not shared_world:
        from .analyst_intents import validate_scoped_packet
        if fmt not in {'SHOWDOWN','CLASSIC'}:raise ValueError('Unsupported optimization intent format')
        if params.get('analyst_scenario_focus_mode','MIXED')!='MIXED':raise ValueError('An optimization intent cannot be blended with a manual scenario focus')
        intent_scope=validate_scoped_packet(packet,intent)
        if set(params.get('analyst_intent_scenario_ids',intent_scope['scenario_ids']))!=set(intent_scope['scenario_ids']):raise ValueError('Prepared intent scenario lineage changed')
    original_packet=packet
    original_packet_sha256=packet_digest(packet)
    from .analyst_focus import prepare_focus
    packet,focus=prepare_focus(packet,params,fmt)
    if shared_world:
        from .shared_world_runtime import common_packet
        packet=common_packet(packet)
    original_rows=_json_safe(pool.to_dict('records'))
    pool,distribution_exclusions=projection_distribution_pool(pool,mean_only=shared_world)
    if set(solve_kwargs.get('locked_player_ids') or []) & {r['player_master_id'] for r in distribution_exclusions}:
        raise ValueError('Locked player has no finite base projection distribution for merged scenarios')
    from .joint_opportunity import PARAM,enable_world,attach_objective,candidate_metric,summary
    captured={}
    def capture(model,frame,selected):
        captured.update(model=model,frame=frame.copy(deep=True)); raise ModelCaptured()
    kwargs={**solve_kwargs,'quality_floor':None,'include_control_comparison':False}
    if shared_world:
        from .shared_world_runtime import user_legal_kwargs
        kwargs=user_legal_kwargs(kwargs)
    try: service._solve_lineup(pool,**{**kwargs,'additional_constraints':capture})
    except ModelCaptured: pass
    if not captured: return [],dict(mode=STRATEGY,status='blocked',reasons=['legal_model_unavailable'])
    rows=_json_safe(captured['frame'].to_dict('records'))
    if any(g.get('season',season)!=season or g.get('week',week)!=week for g in packet['games'] if g.get('format_membership',{}).get(fmt)=='confirmed_in_scope'):
        raise ValueError('scenario game is outside selected season/week')
    scenarios=build_scenarios(packet,rows,fmt=fmt,decision_at=now,mean_only=shared_world,
        measurement_rows=source_pool_rows if source_pool_rows is not None else original_rows,
        count_receipt=(params.get("prepared_input_evidence") or {}).get("workload_forecast") if shared_world else None)
    captain_analysis=None
    if not shared_world and fmt=='SHOWDOWN' and packet.get('captain_analysis') is not None:
        from .captain_analyst import condition_captains
        scenarios,captain_analysis=condition_captains(packet,rows,scenarios,
            decision_at=now,locked_captain=kwargs.get('locked_captain_player_id'))
    if focus['mode']=='SELECTED_ONLY':
        from .analyst_focus import focused_world
        scenarios=[focused_world(sc,rows,packet) for sc in scenarios]
    if params.get(PARAM):
        for scenario in scenarios:enable_world(scenario,source_pool_rows or original_rows,packet)
    mapping={prefix+'_'+str(i):dict(player_master_id=str(r['player_id']),role=role) for i,r in enumerate(rows)
             for prefix,role in ([('captain','CPT'),('flex','FLEX')] if fmt=='SHOWDOWN' else [('player','SELECTED')])}
    # Classic solver uses x_N; inspect actual captured names to keep mapping exact.
    if fmt=='CLASSIC':
        mapping={('player_'+str(i)):dict(player_master_id=str(r['player_id']),role='SELECTED') for i,r in enumerate(rows)}
    names={v.name for v in captured['model'].variables()}
    if not set(mapping)<=names: raise ValueError('merged roster variable mapping mismatch')
    snapshot=runtime_snapshot(captured['model'],mapping,rows,packet=original_packet,season=season,week=week,slate=slate,fmt=fmt,decision_at=now,policy={'quality_screen':'none','strategy':STRATEGY,
        **({'mean_only':True,'selection_policy':SHARED_WORLD_POLICY} if shared_world else {})})
    if shared_world:
        from .shared_world_runtime import run_prepared
        return run_prepared(service,pool,kwargs=kwargs,snapshot=snapshot,rows=rows,packet=original_packet,
            scenarios=scenarios,params={**params,'locked_player_ids':sorted(kwargs.get('locked_player_ids') or []),
            'data_cutoff_at':params.get('data_cutoff_at',now)},fmt=fmt,requested=requested,focus=focus,
            distribution_exclusions=distribution_exclusions,original_rows=original_rows)
    if params.get('analyst_teammate_choice'):
        from .teammate_opportunity import validate_choice
        validate_choice(service,params,packet,source_pool_rows or rows,pool.iloc[0].get('projection_run_id'))
    from .defense_kicker_analyst import scan_specialists
    specialists=scan_specialists(packet,source_pool_rows or rows,fmt=fmt)
    from .weekly_role_review import scan_weekly_review
    weekly=scan_weekly_review(original_packet,source_pool_rows or rows,fmt=fmt,decision_at=now)
    from .analyst_focus import scan_contrarian
    contrarian=scan_contrarian(original_packet,source_pool_rows or rows,fmt=fmt,decision_at=now)
    if fmt=='CLASSIC' and params.get('analyst_portfolio_mode','SCENARIO_FIRST')=='SCENARIO_FIRST':
        from .scenario_allocation import generate_allocated
        selected,worlds,selection,plan=generate_allocated(snapshot,packet,rows,
            {**params,'locked_player_ids':sorted(kwargs.get('locked_player_ids') or []),'data_cutoff_at':now},requested,source_rows=source_pool_rows,on_plan=(lambda plan: progress('scenario_allocation',0,requested,'Football idea allocation frozen before roster generation',checkpoint={'scenario_allocation_plan':plan})) if progress else None)
        lineups=[]
        for candidate in selected:
            lineup=service._solve_lineup(pool,**{**kwargs,'locked_player_ids':{p['player_master_id'] for p in candidate['roster']}})
            if not lineup:raise ValueError('Allocated scenario roster failed exact legal replay')
            lineup[0].update(analyst_thesis_ids=candidate['scenario_ids'],analyst_packet_sha256=original_packet_sha256,analyst_strategy=STRATEGY,
                analyst_focus_mode=focus['mode'],analyst_selected_scenario_ids=focus['selected_scenario_ids'],analyst_focus_story_compliance=candidate['construction_audit']['passed'],analyst_portfolio_mode='SCENARIO_FIRST',analyst_allocation_slot=candidate['allocation_slot'],analyst_scenario_scores=candidate['scores'],
                analyst_teammate_pair_id=candidate.get('teammate_pair_id'),analyst_teammate_source_optimizer_run_id=candidate.get('teammate_source_optimizer_run_id'),analyst_challenger_vulnerability_id=candidate.get('challenger_vulnerability_id'),analyst_challenger_conditions=candidate.get('challenger_conditions'),analyst_discovery_finding_ids=candidate.get('discovery_finding_ids',[]),analyst_allocated_idea_id=candidate['allocated_idea_id'],analyst_opportunity_budget=candidate['opportunity_budget'],analyst_joint_opportunity_summary=candidate.get('joint_opportunity_summary'))
            lineups.append(lineup)
        report=dict(mode=STRATEGY,portfolio_mode='SCENARIO_FIRST',packet_sha256=original_packet_sha256,
            focus=focus,contrarian_analysis=contrarian,defense_kicker_analysis=specialists,weekly_role_review=weekly,teammate_opportunity=plan.get('teammate_opportunity'),challenger=plan.get('challenger'),discovery=plan['discovery'],scenario_allocation_plan=plan,scenario_definitions=worlds,candidates=selected,selection=selection,generation=plan['generation_attempts'],
            input_snapshot=snapshot,input_snapshot_sha256=snapshot['sha256'],seed=7,quality_screen='none',baseline_veto=False,
            projection_distribution_eligibility={'original_input_sha256':digest(original_rows),'original_input_rows':original_rows,'excluded':_json_safe(distribution_exclusions)},
            generated_candidate_count=(plan.get('challenger') or {}).get('candidate_pool_count',len(selected)),initial_generated_candidate_count=len(plan['slots']),distinct_candidate_pool_count=(plan.get('challenger') or {}).get('candidate_pool_count',len(selected)),selected_lineup_count=len(lineups),requested_portfolio_size=requested,achieved_portfolio_size=len(lineups),
            status='completed' if len(lineups)==requested else 'underfilled',mathematical_assumptions={
                'allocation':'Evidence/role/usage capability and ordinal editorial preference before solves, overlap penalties, new-script credit; no calibrated probabilities.',
                'opportunity':'Conserved 100 normalized skill-opportunity units shifted between targets and carries; partial coverage uses disclosed allocation prior.',
                'response':'Declared component weights and 0.7 elasticity translate pass/rush ratios into conditional moments, sqrt response for spread; not fitted scoring efficiency.',
                'construction':'Passing primary QB plus receiver, evidence-qualified opponent response only; run control RB, no own QB, at most one own receiver; secondary offense limits.',
                'dependence':'Actual same-team receiving pairs and canonical triples bounded across assigned slots; explicit locks retained and disclosed.'})
        if intent_scope:
            report['optimization_intent']={**intent_scope,'scope':dict(season=season,week=week,slate=slate,format=fmt),
                'generation_comparison':'Separate intent candidate pools; not a frozen-pool selector comparison'}
            for lineup in lineups:
                lineup[0].update(analyst_optimization_intent=intent,analyst_intent_scenario_ids=intent_scope['scenario_ids'])
        if params.get(PARAM):
            from .joint_opportunity import annotate_report
            annotate_report(report)
        _research_explanations(report, lineups, params)
        return lineups,report
    candidates={}; generation=[]
    budget=int(params.get('analyst_candidates_per_thesis',2))
    if not 1<=budget<=10: raise ValueError('scenario candidate budget must be 1 through 10')
    # Baseline solve against the identical legal model is comparison evidence only.
    base_vars,base_model=pulp.LpProblem.fromDict(deepcopy(snapshot['model']))
    base_model.solve(_solver()); baseline=[]
    if base_model.status==pulp.LpStatusOptimal:
        baseline=sorted((ref['player_master_id'],ref['role']) for name,ref in mapping.items() if pulp.value(base_vars[name])>.5)
    if captain_analysis:
        for assessment in captain_analysis['assessments']:
            variables,model=pulp.LpProblem.fromDict(deepcopy(snapshot['model']))
            name=next(n for n,r in mapping.items() if r['role']=='CPT' and r['player_master_id']==assessment['player_master_id'])
            model+=variables[name]==1
            model.solve(_solver())
            assessment['baseline_solver_status']=pulp.LpStatus[model.status]
            assessment['baseline_flex_player_master_ids']=sorted(r['player_master_id'] for n,r in mapping.items() if r['role']=='FLEX' and model.status==pulp.LpStatusOptimal and pulp.value(variables[n])>.5)
    def scenario_model(scenario):
        variables,model=pulp.LpProblem.fromDict(deepcopy(snapshot['model']))
        captain_id=scenario.get('captain_player_master_id')
        if captain_id:
            captain_name=next(name for name,ref in mapping.items() if ref['role']=='CPT' and ref['player_master_id']==captain_id)
            model+=variables[captain_name]==1,'analyst_conditioned_captain'
        requirement=scenario.get('focus_requirement')
        if requirement:
            from .analyst_focus import require_story
            require_story(model,variables,mapping,rows,requirement)
        model.setObjective(pulp.lpSum((1.5 if ref['role']=='CPT' else 1)*(scenario['moments'][ref['player_master_id']]['mean']+.35*(scenario['moments'][ref['player_master_id']]['p90']-scenario['moments'][ref['player_master_id']]['mean']))*variables[name] for name,ref in mapping.items()))
        if params.get(PARAM):attach_objective(model,variables,mapping,scenario,scenario['joint_opportunity'])
        if intent_scope:
            from .analyst_intents import require_story
            require_story(model,variables,mapping,rows,intent_scope)
        return variables,model
    for scenario in scenarios:
        variables,model=scenario_model(scenario)
        captain_id=scenario.get('captain_player_master_id')
        for index in range(budget):
            model.solve(_solver()); generation.append(dict(scenario_id=scenario['scenario_id'],attempt=index+1,solver_status=pulp.LpStatus[model.status],**({'captain_player_master_id':captain_id} if captain_id else {})))
            if model.status!=pulp.LpStatusOptimal: break
            chosen=[name for name in mapping if pulp.value(variables[name])>.5]
            signature=tuple(sorted((mapping[n]['player_master_id'],mapping[n]['role']) for n in chosen))
            candidates.setdefault(signature,dict(roster=[mapping[n] for n in chosen],scenario_ids=[]))['scenario_ids'].append(scenario['scenario_id'])
            model+=pulp.lpSum(variables[n] for n in chosen)<=len(chosen)-1
    initial_candidate_count=len(candidates)
    captain_search=dict(enabled=False,reason='scoped_showdown_intents_only')
    if fmt=='SHOWDOWN' and intent_scope:
        from .analyst_captain_search import broaden_captains
        attempts,captain_search=broaden_captains(scenarios=scenarios,rows=rows,mapping=mapping,
            candidates=candidates,scenario_model=scenario_model,solver=_solver,per_captain=budget)
        generation.extend(attempts)
        captain_search.update(enabled=True,initial_global_candidate_budget=len(scenarios)*budget,
                              added_candidates=len(candidates)-initial_candidate_count)
    selected,selection=select_portfolio(list(candidates.values()),scenarios,rows,requested=requested,params={**params, 'locked_player_ids': sorted(kwargs.get('locked_player_ids') or []), 'data_cutoff_at': params.get('data_cutoff_at', now)},fmt=fmt)
    coverage_initial_count=len(candidates)
    captain_augmentation=dict(enabled=False,reason=None,added_candidates=0)
    if fmt=='SHOWDOWN' and len(selected)<requested:
        caprate=float(params.get('captain_max_exposure',1))
        limit=math.ceil(requested*caprate)
        needed=math.ceil(requested/limit) if limit else 0
        seen={p['player_master_id'] for c in candidates.values() for p in c['roster'] if p['role']=='CPT'}
        if needed and len(seen)<needed:
            captain_augmentation.update(enabled=True,reason='initial_pool_missing_captains_for_requested_exposure',
                required_distinct_captains=needed,initial_distinct_captains=len(seen))
            # Search the same legal model and authored worlds for unseen Captains.
            # This expands candidate evidence, never eligibility or exposure limits.
            for scenario in scenarios:
                while len(selected)<requested and len(seen)<needed:
                    variables,model=scenario_model(scenario)
                    unseen=[name for name,ref in mapping.items() if ref['role']=='CPT' and ref['player_master_id'] not in seen]
                    if not unseen:break
                    model+=pulp.lpSum(variables[name] for name in unseen)==1,'analyst_unseen_captain'
                    model.solve(_solver())
                    generation.append(dict(scenario_id=scenario['scenario_id'],phase='captain_exposure_coverage',
                        solver_status=pulp.LpStatus[model.status]))
                    if model.status!=pulp.LpStatusOptimal:break
                    chosen=[name for name in mapping if pulp.value(variables[name])>.5]
                    signature=tuple(sorted((mapping[n]['player_master_id'],mapping[n]['role']) for n in chosen))
                    candidates.setdefault(signature,dict(roster=[mapping[n] for n in chosen],scenario_ids=[]))['scenario_ids'].append(scenario['scenario_id'])
                    seen.update(mapping[n]['player_master_id'] for n in chosen if mapping[n]['role']=='CPT')
                    selected,selection=select_portfolio(list(candidates.values()),scenarios,rows,requested=requested,
                        params={**params,'locked_player_ids':sorted(kwargs.get('locked_player_ids') or []),
                                'data_cutoff_at':params.get('data_cutoff_at',now)},fmt=fmt)
                if len(selected)==requested:break
            captain_augmentation['added_candidates']=len(candidates)-coverage_initial_count
            captain_augmentation['achieved_distinct_captains']=len(seen)
    if captain_analysis:
        for candidate in candidates.values():
            captain=next(p['player_master_id'] for p in candidate['roster'] if p['role']=='CPT')
            assessment=next(a for a in captain_analysis['assessments'] if a['player_master_id']==captain)
            baseline_flex=set(assessment['baseline_flex_player_master_ids'])
            flex={p['player_master_id'] for p in candidate['roster'] if p['role']=='FLEX'}
            candidate['captain_conditioned_flex_comparison']=dict(captain_player_master_id=captain,
                added=sorted(flex-baseline_flex),removed=sorted(baseline_flex-flex),
                baseline_solver_status=assessment['baseline_solver_status'],baseline_veto=False)
    lineups=[]
    for candidate in selected:
        if intent_scope:
            from .analyst_intents import audit_story
            if not audit_story(candidate['roster'],rows,intent_scope):raise ValueError('Selected roster failed optimization intent story')
        if focus['mode']=='SELECTED_ONLY':
            from .analyst_focus import audit_story
            matching=[sc for sc in scenarios if sc['scenario_id'] in candidate['scenario_ids']]
            if not matching or not any(audit_story(candidate['roster'],rows,sc['focus_requirement']) for sc in matching):raise ValueError('Selected roster failed focused story compliance')
            candidate['focused_story_compliance']=True
        ids={r['player_master_id'] for r in candidate['roster']}
        replay={**kwargs,'locked_player_ids':ids}
        if fmt=='SHOWDOWN': replay['locked_captain_player_id']=next(r['player_master_id'] for r in candidate['roster'] if r['role']=='CPT')
        lineup=service._solve_lineup(pool,**replay)
        if not lineup: raise ValueError('Merged candidate failed exact legal model replay')
        if fmt=='SHOWDOWN':
            lineup.sort(key=lambda row:(row.get('roster_position')!='CPT',str(row['player_id'])))
        lineup[0]['analyst_joint_opportunity_summary']=summary(candidate,next((s for s in scenarios if s['scenario_id'] in candidate['scenario_ids']),scenarios[0]))
        lineup[0].update(analyst_focus_mode=focus['mode'],analyst_selected_scenario_ids=focus['selected_scenario_ids'],analyst_focus_story_compliance=candidate.get('focused_story_compliance'),analyst_thesis_ids=candidate['scenario_ids'],analyst_packet_sha256=original_packet_sha256,analyst_strategy=STRATEGY,analyst_scenario_scores=candidate['scores'])
        if intent_scope:
            lineup[0].update(analyst_optimization_intent=intent,analyst_intent_scenario_ids=intent_scope['scenario_ids'],analyst_intent_story_compliance=True)
        if captain_analysis:
            captain_id=next(p['player_master_id'] for p in candidate['roster'] if p['role']=='CPT')
            lineup[0]['analyst_captain_assessment']=next(a for a in captain_analysis['assessments'] if a['player_master_id']==captain_id)
            lineup[0]['analyst_captain_flex_comparison']=candidate['captain_conditioned_flex_comparison']
        lineups.append(lineup)
    report=dict(mode=STRATEGY,projection_distribution_eligibility={'original_input_sha256':digest(original_rows),'original_input_rows':original_rows,'excluded':_json_safe(distribution_exclusions),'quality_screen':'none','meaning':'Missing/nonfinite model moments cannot be scenario distributions; no healthy or zero-projection assumption is invented.'},packet_sha256=original_packet_sha256,input_snapshot=snapshot,input_snapshot_sha256=snapshot['sha256'],seed=7,
                quality_screen='none',baseline_veto=False,baseline_comparison_roster=baseline,
                scenario_definitions=scenarios,candidates=list(candidates.values()),generation=generation,selection=selection,
                generated_candidate_count=len(candidates),initial_generated_candidate_count=initial_candidate_count,
                captain_exposure_coverage=captain_augmentation,captain_candidate_search=captain_search,selected_lineup_count=len(lineups),requested_candidate_count=len(scenarios)*budget,
                requested_portfolio_size=requested,achieved_portfolio_size=len(lineups),status='completed' if len(lineups)==requested else 'underfilled',
                mathematical_assumptions={'opportunity_response':'base_mean * product(1 + declared_elasticity * (opportunity_ratio - 1))','uncertainty':'P90-mean spread scales by sqrt(response); Poisson-style sensitivity proxy','candidate_objective':'conditional_mean + 0.35 * conditional_P90_spread','portfolio_objective':'equal-weight normalized conditional upside coverage plus average score; no calibrated probability claim','relationships':'shared team volume moves QB and receiving roles together; concentration and transfers conserve specified opportunity','workload_chronology':'Existing workload lineage retained. Missing source observation clocks remain unverified; a cutoff alone is not proof of availability.', 'limitations':'No fitted scoring efficiency, joint simulation, calibrated probabilities, or causal injury estimate. All elasticities are declared sensitivity assumptions.'})
    if intent_scope:
        report['optimization_intent']={**intent_scope,'scope':dict(season=season,week=week,slate=slate,format=fmt),
            'generation_comparison':'Separate intent candidate pools; not a frozen-pool selector comparison'}
    report['defense_kicker_analysis']=specialists
    report['weekly_role_review']=weekly
    report['focus']=focus
    report['contrarian_analysis']=contrarian
    if packet.get('team_game_outlook') is not None:
        report['team_game_outlook']=deepcopy(packet['team_game_outlook'])
    if captain_analysis:
        for assessment in captain_analysis['assessments']:
            pid=assessment['player_master_id']
            assessment['generated_candidate_count']=sum(any(p['player_master_id']==pid and p['role']=='CPT' for p in c['roster']) for c in candidates.values())
            assessment['selected_lineup_count']=sum(any(p['player_master_id']==pid and p['role']=='CPT' for p in c['roster']) for c in selected)
            assessment['generation_status']='generated' if assessment['generated_candidate_count'] else assessment.get('generation_status','infeasible_under_prepared_constraints')
        report['captain_analysis']=captain_analysis
    if params.get(PARAM):
        from .joint_opportunity import annotate_report
        annotate_report(report)
    _research_explanations(report, lineups, params)
    return lineups,report


def _solve_joint_research(model):
    """Bounded research only; a CBC incumbent is not an optimality proof."""
    solver=_solver();solver.timeLimit=30
    model.solve(solver)
    return model.status==pulp.LpStatusOptimal and model.sol_status==pulp.LpSolutionOptimal


def candidate_portfolio_model(candidates,rows,*,requested,params,fmt,allocation_plan=None,allocation_controls=None):
    """One unchanged hard-constraint model for selection and exact completion.

    Individual roster legality is already captured by candidate generation.
    This model retains all existing cross-roster controls without objectives.
    """
    by_id={str(r["player_id"]):r for r in rows}
    model=pulp.LpProblem('AnalystScenarioPortfolio',pulp.LpMaximize)
    chosen=pulp.LpVariable.dicts('candidate',range(len(candidates)),cat='Binary')
    model+=pulp.lpSum(chosen.values())<=requested
    maximums=params.get('maximum_exposure_by_player') or {}; minimums=params.get('minimum_exposure_by_player') or {}
    if any(pid not in by_id and float(rate)>0 for pid,rate in minimums.items()):
        raise ValueError('Minimum exposure references an ineligible canonical player')
    for pid in by_id:
        appearances=pulp.lpSum(chosen[i] for i,c in enumerate(candidates) if any(p['player_master_id']==pid for p in c['roster']))
        locks=set(params.get('locked_player_ids') or [])
        rate=1.0 if pid in locks else float(params.get('max_exposure',1))
        if fmt=='SHOWDOWN' and pid not in locks:
            row=by_id[pid]
            role_key=('starting_qb_max_exposure' if row['position']=='QB' and row.get('showdown_qb_eligible')
                      else 'cheap_punt_max_exposure' if float(row.get('base_salary',row.get('salary',0)))<=1000
                      else 'core_player_max_exposure')
            rate=min(rate,float(params.get(role_key,1)))
        if not math.isfinite(rate) or not 0<=rate<=1: raise ValueError('invalid maximum exposure')
        limit=math.ceil(requested*rate)
        from .classic_portfolio_controls import explicit_appearance_limit
        if pid in maximums:
            explicit=float(maximums[pid])
            if not math.isfinite(explicit) or not 0<=explicit<=1: raise ValueError('invalid explicit maximum exposure')
            limit=min(limit,explicit_appearance_limit(requested,explicit))
        if params.get('elevated_player_max_exposure') is not None:
            from .single_lineup import elevated_player
            if elevated_player(by_id[pid],params.get('data_cutoff_at')):
                limit=min(limit,explicit_appearance_limit(requested,float(params['elevated_player_max_exposure'])))
        model+=appearances<=limit
        if pid in minimums:
            minimum=float(minimums[pid])
            if not math.isfinite(minimum) or not 0<=minimum<=1: raise ValueError('invalid minimum exposure')
            model+=appearances>=math.ceil(requested*minimum)
    if fmt=='SHOWDOWN':
        caprate=float(params.get('captain_max_exposure',1))
        if not math.isfinite(caprate) or not 0<=caprate<=1: raise ValueError('invalid captain exposure')
        # An underfilled set must not silently spend the full requested
        # portfolio's Captain allowance (e.g. 2/2 of a 4-entry 50% request).
        sizes=pulp.LpVariable.dicts('achieved_portfolio_size',range(requested+1),cat='Binary')
        model+=pulp.lpSum(sizes.values())==1
        model+=pulp.lpSum(chosen.values())==pulp.lpSum(size*sizes[size] for size in sizes)
        achieved_limit=pulp.lpSum((math.ceil(requested*caprate) if size==requested else math.floor(size*caprate))*sizes[size] for size in sizes)
        for pid in by_id:
            model+=pulp.lpSum(chosen[i] for i,c in enumerate(candidates) if any(p['player_master_id']==pid and p['role']=='CPT' for p in c['roster']))<=math.ceil(requested*caprate)
            model+=pulp.lpSum(chosen[i] for i,c in enumerate(candidates) if any(p['player_master_id']==pid and p['role']=='CPT' for p in c['roster']))<=achieved_limit
    if fmt=='CLASSIC' and params.get('max_lineups_per_primary_game') is not None:
        from .classic_primary_game import canonical_primary_game
        game_candidates={}
        for i,c in enumerate(candidates):
            qb=next(by_id[p['player_master_id']] for p in c['roster'] if by_id[p['player_master_id']]['position']=='QB')
            game=canonical_primary_game(qb.get('player_team',qb.get('team')),qb.get('opponent_team',qb.get('opponent')))
            game_candidates.setdefault(game,[]).append(chosen[i])
        for variables in game_candidates.values(): model+=pulp.lpSum(variables)<=int(params['max_lineups_per_primary_game'])
    overlap=params.get('max_lineup_overlap')
    if params.get('minimum_uniqueness') is not None:
        derived=(6 if fmt=='SHOWDOWN' else 9)-int(params['minimum_uniqueness'])
        overlap=min(int(overlap),derived) if overlap is not None else derived
    if overlap is not None:
        for i,c in enumerate(candidates):
            ids={p['player_master_id'] for p in c['roster']}
            for j in range(i):
                if len(ids & {p['player_master_id'] for p in candidates[j]['roster']})>int(overlap): model+=chosen[i]+chosen[j]<=1
    if allocation_plan is not None:
        from .scenario_breadth import add_selection_constraints
        add_selection_constraints(model,chosen,candidates,rows,requested,params,allocation_plan,allocation_controls)
    return model,chosen


def select_portfolio(candidates,scenarios,rows,*,requested,params,fmt,allocation_plan=None,allocation_controls=None,selection_objective=None,candidate_utilities=None,joint_state_scores=None,research_solver_seconds=None):
    by_id={str(r['player_id']):r for r in rows}
    for candidate in candidates:
        from .joint_opportunity import candidate_metric
        candidate['scores']={s['scenario_id']:candidate_metric(candidate,s) for s in scenarios}
        # A Captain-conditioned opportunity world is shared football context.
        # Other Captain rosters retain their actual scores in that world.
    if not candidates: return [],dict(solver_status='no_candidates',quality_rejected=0)
    model,chosen=candidate_portfolio_model(candidates,rows,requested=requested,params=params,fmt=fmt,allocation_plan=allocation_plan,allocation_controls=allocation_controls)
    coverage=[]; utility=[]; joint_stages=[]; joint_floor=None
    # Identical shared outcomes must not gain votes from Captain labels.
    from .analyst_shadow import digest
    unique_worlds={}
    for scenario in scenarios:
        unique_worlds.setdefault(digest(dict(moments={pid:{key:moment[key] for key in ('mean','p90')} for pid,moment in scenario['moments'].items()},**({'joint_costs':scenario['joint_opportunity']['costs']} if scenario.get('joint_opportunity') else {}))),scenario)
    weighted_scenarios=[] if selection_objective=="JOINT_WORST_REGRET" else list(unique_worlds.values())
    for scenario in weighted_scenarios:
        sid=scenario['scenario_id']; best=max(c['scores'][sid] for c in candidates) or 1
        # Coverage measures the best selected roster for each possible outcome.
        assignments=pulp.LpVariable.dicts('coverage_'+str(len(coverage)),range(len(candidates)),cat='Binary')
        model+=pulp.lpSum(assignments.values())<=1
        for i in assignments: model+=assignments[i]<=chosen[i]
        priority=next((i['credibility_score'] for i in allocation_plan['ideas'] if i['idea_id']==sid),0) if allocation_plan is not None else 1
        coverage.append(priority*pulp.lpSum(assignments[i]*candidates[i]['scores'][sid]/best for i in assignments))
        utility.extend(chosen[i]*candidates[i]['scores'][sid]/best/(requested*len(weighted_scenarios)) for i in chosen)
    # Lexicographic size dominates every bounded secondary term: never relax caps.
    if selection_objective=='JOINT_WORST_REGRET':
        if not joint_state_scores or any(len(values)!=len(candidates) or any(type(v) not in (int,float) or not math.isfinite(v) for v in values) or max(values)<=0 for values in joint_state_scores.values()):
            raise ValueError('Complete finite joint-state scores and positive state normalizers required')
        # Genuine lexicographic stages: no invented scenario probabilities or
        # scalar weight trading a lineup against shared-outcome coverage.
        model.setObjective(pulp.lpSum(chosen.values())); proven=_solve_joint_research(model)
        if not proven:
            return [],dict(solver_status='unproven_count_research_limit',requested=requested,achieved=0,constraints_relaxed=False)
        feasible_count=round(pulp.value(pulp.lpSum(chosen.values())))
        joint_stages.append(dict(stage='maximum_feasible_count',solver_status='Optimal',value=feasible_count))
        if not feasible_count:
            return [],dict(solver_status='no_feasible_rosters',requested=requested,achieved=0,constraints_relaxed=False)
        model+=pulp.lpSum(chosen.values())==feasible_count
        from .joint_coverage_solver import optimize_coverage
        optimum,coverage_attempts=optimize_coverage(model,chosen,joint_state_scores)
        if optimum is None:
            return [],dict(solver_status='unproven_joint_research_limit',requested=requested,achieved=0,constraints_relaxed=False,joint_selection_stages=joint_stages,coverage_attempts=coverage_attempts)
        joint_floor=optimum
        joint_stages.append(dict(stage='worst_relative_best_roster_coverage',solver_status='Optimal',value=optimum,feasibility_attempts=coverage_attempts))
        model.setObjective(pulp.lpSum(chosen[i]*sum(float(by_id[p['player_master_id']]['projection']) for p in c['roster']) for i,c in enumerate(candidates)))
    elif selection_objective=='EXTERNAL_LINEUP_SCORE':
        if candidate_utilities is None or len(candidate_utilities)!=len(candidates) or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in candidate_utilities):
            raise ValueError('External complete-lineup utilities must be finite values in [0,1] for every candidate')
        model.setObjective((requested+1)*pulp.lpSum(chosen.values())+pulp.lpSum(chosen[i]*candidate_utilities[i] for i in chosen))
    elif selection_objective=='BASELINE_MEAN':
        means=[sum(float(by_id[p['player_master_id']]['projection']) for p in c['roster']) for c in candidates]
        bound=max(means) or 1
        model.setObjective((requested+1)*pulp.lpSum(chosen.values())+pulp.lpSum(chosen[i]*means[i]/bound for i in chosen))
    else:
        model.setObjective((len(scenarios)+2)*pulp.lpSum(chosen.values())+pulp.lpSum(coverage)+pulp.lpSum(utility))
    proven=_solve_joint_research(model) if selection_objective=='JOINT_WORST_REGRET' else None
    if selection_objective!='JOINT_WORST_REGRET':
        solver=_solver()
        if research_solver_seconds is not None:
            if selection_objective not in {'BASELINE_MEAN','EXTERNAL_LINEUP_SCORE'} or not 0<research_solver_seconds<=30:raise ValueError('Invalid bounded research solver contract')
            solver.timeLimit=research_solver_seconds
            solver.threads=1
        model.solve(solver)
        if research_solver_seconds is not None:proven=model.status==pulp.LpStatusOptimal and model.sol_status==pulp.LpSolutionOptimal
    valid=model.status==pulp.LpStatusOptimal and (model.valid(1e-6) if selection_objective=='JOINT_WORST_REGRET' or research_solver_seconds is not None else True)
    if selection_objective=='JOINT_WORST_REGRET':joint_stages.append(dict(stage='original_mean_tiebreak',solver_status='Optimal' if proven else 'feasible_unproven' if valid else 'no_verified_incumbent'))
    selected=[c for i,c in enumerate(candidates) if valid and pulp.value(chosen[i])>.5]
    return selected,dict(solver_status=('Optimal' if proven else 'feasible_unproven_mean_tiebreak' if valid else pulp.LpStatus[model.status]) if selection_objective=='JOINT_WORST_REGRET' or research_solver_seconds is not None else pulp.LpStatus[model.status],requested=requested,achieved=len(selected),quality_rejected=0,quality_screen='none',constraints_relaxed=False,
        captain_exposure_basis='requested-size rounding for complete portfolio; actual achieved-size bound without rounding up for underfill' if fmt=='SHOWDOWN' else None,
        joint_selection_stages=joint_stages,joint_worst_relative_coverage=float(pulp.value(joint_floor)) if joint_floor is not None and model.status==pulp.LpStatusOptimal else None,
        unique_shared_outcome_count=len(weighted_scenarios),comparison_policy='All rosters evaluated under every shared opportunity world; equivalent moment worlds counted once',
        scenario_coverage={s['scenario_id']:max((c['scores'][s['scenario_id']] for c in selected),default=0) for s in scenarios},selection_reason=('Maximum feasible count, then worst-state best-roster relative coverage, then original mean tie-break; stress set has no probabilities' if selection_objective=='JOINT_WORST_REGRET' else 'Maximum feasible count, then declared external complete-lineup research utility under unchanged hard controls' if selection_objective=='EXTERNAL_LINEUP_SCORE' else 'Maximum feasible count, then highest summed baseline mean under unchanged constraints' if selection_objective=='BASELINE_MEAN' else 'Maximum feasible count, then ordinal evidence-priority conditional coverage; weights are not probabilities' if allocation_plan is not None else 'Maximum feasible count, then best-roster coverage across equal-weight plausible outcomes and average conditional upside'))
