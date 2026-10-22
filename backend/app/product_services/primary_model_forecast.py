"""New-model primary forecast: tree/NN opportunities → complete DK score heads.

Incumbent projections are absent from offense/K inference. DST has its own
explicitly selected, verified serving component. Full clock simulation is absent.
"""
from copy import deepcopy
from sqlalchemy.orm import Session
from .evaluation_record import digest
from .primary_model_source import source_inputs
from .workload_count_forecast import load_history,forecast
from .team_opportunity_serving import predict_registered_teams
from .player_opportunity_serving import predict_registered_players
from .team_opportunity_matrix import build_team_matrix
from .offensive_volume_features import build_player_matrix
from .defense_context_evidence import build_defense_context_evidence
from .environment_context_evidence import build_environment_context_evidence
from .player_opportunity_components import build_player_opportunity_components
from .primary_points_model import load_rows,fit_and_predict

VERSION='new_model_primary_v1'


def prepare(engine,reference,pool_rows,*,season,week,slate,cutoff,games,markets,scenario,counts_only=False):
    if not reference:raise ValueError('New-model primary requires complete workload reference; no incumbent fallback')
    before=season*100+week
    events,source=source_inputs(engine,season=season,week=week,slate=slate,cutoff=cutoff)
    weekly=load_history(engine,season=season,week=week,cutoff=cutoff)
    defense=build_defense_context_evidence(events,before_period=before,cutoff=cutoff)
    environment=build_environment_context_evidence(events,before_period=before,cutoff=cutoff)
    contexts=dict(defense=defense,environment=environment,source=events['event_evidence']['source'])
    source_context=dict(status='available_descriptive',facts=dict(contexts=dict(defense=defense,environment=environment)),
        semantic_measurements_sha256=digest(dict(defense=defense['semantic_measurements_sha256'],environment=environment['semantic_measurements_sha256'])),
        provenance=dict(source=source))
    with Session(engine) as session:
        team=predict_registered_teams(session,weekly,source_context,games,markets,before_period=before,cutoff=cutoff)
    if team['status']!='forecast_complete':raise ValueError('Published team tree/neural forecasts unavailable; no reference-model fallback')
    budgets={}
    for issued in team['predictions']:
        budget=deepcopy(reference['teams'][issued['team']])
        budget.update(issued['counts'])
        if budget.get('observed_target_rate') is None:raise ValueError('New team forecast lacks supported target-subset rate')
        budget['targets']=budget['pass_attempts']*min(1.,max(0.,budget['observed_target_rate']))
        if issued['team']==scenario['team']:
            budget['pass_attempts']*=scenario['passing_factor'];budget['targets']*=scenario['passing_factor']
            budget['rush_attempts']*=scenario['rushing_factor']
        budgets[issued['team']]=budget
    actors=[{k:deepcopy(v) for k,v in a.items() if k not in {'counts','raw_history','component_response','player_model_components'}} for a in reference['players']]
    from .workload_gamebook_participation import load_verified_gaps
    gaps=load_verified_gaps(engine,season=season,cutoff=cutoff)
    counts=forecast(weekly,actors,before_period=before,starters=reference['starter_ids'],model=reference['model'],
        cutoff=cutoff,team_budgets=budgets,verified_gaps=gaps)
    from .opportunity_role_allocation import unavailable_from_canonical_rows,allocate_factual_vacancies
    unavailable,unresolved=unavailable_from_canonical_rows(pool_rows,before_period=before,cutoff=cutoff)
    counts=allocate_factual_vacancies(counts,unavailable=unavailable,cutoff=cutoff)
    targets=[]
    for game in games:
        away,home=game['game_id'].split('_')[2:]
        for t,o in ((away,home),(home,away)):targets.append(dict(game_id=game['game_id'],season=season,week=week,team=t,opponent=o))
    matrix=build_team_matrix(weekly,targets,[contexts],before_period=before,cutoff=cutoff,market_rows=markets)
    components=build_player_opportunity_components(events,before_period=before,cutoff=cutoff)
    # Only this named server consumer can authorize fresh, prelock measurements.
    # The immutable reader above verifies actual source bytes, scope and clocks.
    components.update(pregame_serving_eligible=True,current_consumer_contract=VERSION)
    from .player_opportunity_serving import registered_history_refs
    from .player_opportunity_sources import current_history_components
    from sqlalchemy import text
    with Session(engine) as session:
        refs=registered_history_refs(session,cutoff=cutoff,before_period=before)
        aliases=session.execute(text("SELECT source_key,player_master_id FROM player_alias WHERE source_system='nflreadpy'")).all()
    ids={}
    for native,pid in aliases:
        if native in ids and ids[native]!=str(pid):raise ValueError('Conflicting historical native alias')
        ids[native]=str(pid)
    components=current_history_components(refs,components,cutoff=cutoff,before_period=before,canonical_ids=ids)
    player_matrix=build_player_matrix(weekly.loc[weekly.team.isin(budgets)],components,before_period=before,cutoff=cutoff,
        actors=[a for a in actors if a['position'] in {'QB','RB','WR','TE'}],team_matrix=matrix,
        usage='current_inference',consumer_contract=VERSION,include_historical=False,event_window='observed_player_games')
    with Session(engine) as session:player=predict_registered_players(session,player_matrix,counts,cutoff=cutoff)
    if player['status']!='forecast_complete':raise ValueError('Published player tree/neural forecasts unavailable; no lagged-share fallback')
    counts=player['counts']
    if counts_only:
        # Same authenticated learned heads/reconciliation; stop before FP fitting
        # or DST scoring. Preserve the reference's fixed prior count scales.
        from .workload_count_forecast import utility
        native={str(r['player_id']):r for r in pool_rows}
        counts.update(scales=deepcopy(reference['scales']), projection_run_id=reference['projection_run_id'],
            source_cutoff_at=cutoff.isoformat(), source_history_sha256=reference['source_history_sha256'],
            source_ids=reference['source_ids'], verified_gap_source_ids=reference.get('verified_gap_source_ids',[]),
            starter_ids=reference['starter_ids'], starter_evidence=reference.get('starter_evidence',{}),
            learned_opportunities=True, objective=reference['objective'], domain=reference['domain'],
            learned_model_consumption=dict(source=source,team=team,
                player={k:v for k,v in player.items() if k not in {'counts','predictions'}},
                points_heads_consumed=False,unresolved_vacancy_proofs=unresolved),
            normalization_policy='equal_applicable_components_divided_by_prior_position_count_means_floor1')
        for actor in counts['players']:
            pid=actor['player_master_id'];row=native.get(pid,{})
            actor.update(native_salary_actor=pid in native,name=row.get('name') or actor.get('name'),
                native_id=row.get('dk_player_id'))
            actor['utility']=utility(actor,counts['scales'])
        counts['sha256']=digest({k:v for k,v in counts.items() if k!='sha256'})
        return counts
    # K is a separate complete-score head conditioned on the new team budgets.
    point_actors=deepcopy(counts['players'])
    records,unknown=load_rows(engine,season=season,week=week,cutoff=cutoff)
    scoring=fit_and_predict(records,point_actors,counts['teams'],before_period=before)
    from .dst_deployment import runtime_status
    dst=runtime_status()
    if dst.get('status')!='selected' or dst.get('target_period')!=before:raise ValueError('Primary forecast requires a verified current-period DST component')
    players=pool_scores(pool_rows,scoring['players'],counts['players'],dst)
    from .forecast_player_audit import audit_primary
    audit=audit_primary(players,counts,player_matrix,player['predictions'],before_period=before)
    if audit['errors']:raise ValueError('All-player forecast audit failed: '+str(audit['errors'][:5]))
    audit_rows={r['player_master_id']:r for r in audit['players']}
    for p in players:
        findings=audit_rows.get(p['player_master_id'],{}).get('findings',[])
        p['audit_findings']=findings
        if p['conditional_mean'] is not None and p['new_model_evidence'].get('source')!='factual_unavailable_zero':
            p['missing_evidence'] += [f"Incomplete event measurement/attribution: {f['channel']}; forecast uses explicit missingness, not zero workload" for f in findings if f['code']=='incomplete_event_window']
    result=dict(version=VERSION,scoring_basis='new_models_complete_score_heads',new_model_primary=True,full_game_simulator_consumed=False,
        players=players,source=source,team_model_consumption=team,player_model_consumption={k:v for k,v in player.items() if k not in {'counts','predictions'}},
        scoring_head=scoring,unknown_training_scoring_rows=unknown,physical_count_budgets=counts['teams'],unresolved_vacancy_proofs=unresolved,
        dst_expert=dst,all_player_audit=audit,limitations=scoring['limitations']+[f"All-player audit: {audit['native_player_count']} native players; {audit['unknown_native_scores']} unknown scores; {audit['counts']['review_players']} full-source players have review flags. Unknown attribution and diagnostic ratios are not zero workloads or automatic eligibility penalties.",'Player event features use prior observed same-team player games in both training and inference; missing metrics remain unknown','Prior-season player-event history is verified retained revised data available now; original historical pregame availability remains unproven','Inactive-gap count windows are conditional on active participation and stable current observed role; they do not establish recovered health or guaranteed workload','Full game clock/continuation simulator is not consumed','Player count-head estimands are declared in consumed model evidence; arithmetic-mean calibration remains unproven',
            'Unsupported actors stay visible and are ineligible in the new-model arm; the old comparison preserves its full eligible pool','Existing user-required eligibility rules, including legacy low-opportunity fallback thresholds, remain binding; incumbent FP/P90 do not enter the primary objective','Authored volume changes have unknown likelihood'])
    result['sha256']=digest(result)
    return result


def pool_scores(pool_rows,by_id,actors,dst):
    players=[]
    for row in pool_rows:
        pid=str(row['player_id']);point=dict(by_id.get(pid,{}))
        baseline=None if row.get('projection') is None else float(row['projection'])
        if row['position']=='DST':point=dict(mean=baseline,source='explicit_selected_dst_expert',selection_sha256=dst['selection_sha256'],reason='Selected DST expert score unavailable' if baseline is None else None)
        actor=next((a for a in actors if a['player_master_id']==pid),{})
        if actor.get('world_activity') is False:point=dict(mean=0.,source='factual_unavailable_zero')
        point.setdefault('position',row['position'])
        if point.get('mean') is not None:point.setdefault('source','complete_dk_score_head')
        support=point.get('source') if point.get('source') in {'factual_unavailable_zero','explicit_selected_dst_expert'} else 'complete_dk_score_head'
        players.append(dict(player_master_id=pid,name=row.get('name'),team=row.get('player_team') or row.get('team'),
            baseline_mean=baseline,conditional_mean=point.get('mean'),delta=None if point.get('mean') is None or baseline is None else point['mean']-baseline,
            new_model_evidence={**point,'count_evidence':{k:actor.get(k) for k in ('counts','reasons','history_window_status','current_role_evidence','verified_inactive_gaps','raw_history','conditional_on','source_ids','player_model_components','unreconciled_player_model_counts')}},supported_components=[support] if point.get('mean') is not None else [],
            missing_evidence=[point.get('reason','New-model score unavailable; actor outside modeled coverage'),*actor.get('reasons',[])] if point.get('mean') is None else []))
    return players
