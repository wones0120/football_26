"""Opt-in typed Analyst constructions using the normal prepared solver and selector.

Packet prose is provenance only. Each independent thesis adds hard construction
constraints to a copy of the unchanged baseline model. No score bonuses exist.
"""
from copy import deepcopy
from datetime import datetime, timezone

import pandas as pd

from .analyst_packets import load_packet
from .analyst_shadow import add_directive, digest, freeze_model, generate_shadow


class ModelCaptured(BaseException):
    pass


def runtime_snapshot(model, variable_players, rows, *, packet, season, week, slate,
                     fmt, decision_at, policy):
    games = {g['game_id']:g for g in packet['games']}
    players = []
    for row in rows:
        pid = str(row.get('player_id', row.get('player_master_id')))
        team = row.get('player_team', row.get('team'))
        opp = row.get('opponent_team', row.get('opponent'))
        matching = [gid for gid,g in games.items() if set(g['teams']) == {team,opp} and g.get('season',season)==season and g.get('week',week)==week]
        gid = matching[0] if len(matching)==1 else str(season)+'_W'+str(week).zfill(2)+'_'+ '_'.join(sorted([str(team),str(opp)]))
        players.append({**deepcopy(row), 'player_master_id':pid, 'game_id':gid, 'team':team,
                        'opponent_team':opp, 'p90':row.get('p90',row.get('ceiling'))})
    return freeze_model(model, variable_players=variable_players, players=players,
        scope=dict(format=fmt,season=season,week=week,slate_id=slate,game_ids=sorted({p['game_id'] for p in players})),
        available_at=decision_at,decision_at=decision_at, policy={**policy,'complete_prepared_model':True},
        provenance=dict(analyst_packet_sha256=digest(packet),analysis_at=packet['decision_at'],
                        baseline_binding='runtime prepared model; original source/projection clocks retained in normal optimizer evidence'))


def generate_showdown(service, pool, *, params, season, week, slate, solve_kwargs):
    """Return ordinary solver-rendered candidates plus a machine-readable report."""
    key = params.get('analyst_packet_sha256')
    if not key: return [], None
    packet = load_packet(key)
    budget = int(params.get('analyst_candidates_per_thesis',2))
    if not 1 <= budget <= 10: raise ValueError('Analyst candidate budget must be 1 through 10')
    captured = {}
    def capture(model, frame, selected):
        captured.update(model=model, frame=frame.copy(deep=True))
        raise ModelCaptured()
    try:
        service._solve_lineup(pool, **{**solve_kwargs,'include_control_comparison':False,'additional_constraints':capture})
    except ModelCaptured: pass
    if not captured: return [], dict(status='blocked',reasons=['baseline_model_unavailable'],packet_sha256=key)
    frame = captured['frame']; rows = frame.to_dict('records')
    mapping = {prefix+'_'+str(i):dict(player_master_id=str(row['player_id']),role=role)
               for i,row in enumerate(rows) for prefix,role in [('captain','CPT'),('flex','FLEX')]}
    from .optimizer import _json_safe
    snapshot = runtime_snapshot(captured['model'],mapping,_json_safe(rows),packet=packet,
        season=season,week=week,slate=slate,fmt='SHOWDOWN',decision_at=datetime.now(timezone.utc).isoformat(),
        policy=dict(shortlist_ids=[str(r['player_id']) for r in rows if r.get('showdown_captain_shortlisted')],
                    quality_floor=solve_kwargs.get('quality_floor'),
                    selected_exposure_policy='unchanged downstream selector; candidates are alternatives'))
    report = generate_shadow(packet,snapshot,requested_per_thesis=budget,baseline_count=0,seed=7)
    report.update(mode='ANALYST_CONSTRUCTION',production_defaults_changed=True,
                  final_portfolio_selected=False,status='generated' if report['shadow'] else 'abstained')
    candidates = []
    for record in report['shadow']:
        if record['eligibility_outcome']=='DIAGNOSTIC_ONLY': continue
        ids = {r['player_master_id'] for r in record['roster']}
        captain = next(r['player_master_id'] for r in record['roster'] if r['role']=='CPT')
        kwargs = {**solve_kwargs,'locked_player_ids':ids,'locked_captain_player_id':captain,'include_control_comparison':False}
        lineup = service._solve_lineup(pool, **kwargs)
        if not lineup:
            record['eligibility_outcome']='FAILED_EXACT_BASELINE_REPLAY'; continue
        lineup[0]['analyst_thesis_ids']=record['thesis_ids']
        lineup[0]['analyst_packet_sha256']=key
        lineup[0]['analyst_construction_only']=True
        candidates.append(lineup)
    report['eligible_generated_count']=len(candidates)
    return candidates,report


def merge_showdown(baseline, analyst, *, preserve_variants=False):
    """Canonical Captain dedup with attribution, preserving existing scenario evidence.

    The portfolio selector owns variant dedup by scenario + canonical roster.
    Its original baseline variants/order must survive an Analyst import intact.
    """
    def signature(lineup): return tuple(sorted((str(p['player_id']),p['roster_position']) for p in lineup))
    if preserve_variants:
        merged = list(baseline)
        by_roster = {}
        for lineup in merged:
            by_roster.setdefault(signature(lineup), []).append(lineup)
        for lineup in analyst:
            key = signature(lineup)
            existing = by_roster.get(key, [])
            baseline_variants = [variant for variant in existing
                if str(variant[0].get('showdown_scenario_id') or 'baseline') ==
                   str(lineup[0].get('showdown_scenario_id') or 'baseline')]
            if not baseline_variants:
                merged.append(lineup)
                by_roster.setdefault(key, []).append(lineup)
                existing = by_roster[key]
            # The same physical roster can satisfy an opinion in several existing
            # scenarios; this is overlap attribution, never a unique origin claim.
            for variant in existing:
                variant[0]['analyst_thesis_ids'] = sorted(set(variant[0].get('analyst_thesis_ids', [])) |
                                                        set(lineup[0]['analyst_thesis_ids']))
                variant[0]['analyst_packet_sha256'] = lineup[0]['analyst_packet_sha256']
                variant[0]['analyst_construction_only'] = True
        return merged
    merged = {signature(lineup):lineup for lineup in baseline}
    for lineup in analyst:
        key = signature(lineup)
        if key not in merged: merged[key]=lineup; continue
        existing=merged[key]
        existing[0]['analyst_thesis_ids']=sorted(set(existing[0].get('analyst_thesis_ids',[])) | set(lineup[0]['analyst_thesis_ids']))
        existing[0]['analyst_packet_sha256']=lineup[0]['analyst_packet_sha256']
        existing[0]['analyst_construction_only']=True
    return list(merged.values())


def classic_step_candidates(model, players, *, packet, season, week, slate, budget, decision_at):
    """Generate alternatives in the exact current sequential feasible region."""
    from dataclasses import asdict
    rows=[]
    for player in players:
        row=asdict(player); row['tags']=sorted(row['tags']); rows.append(row)
    mapping={'p_'+str(i):dict(player_master_id=p.player_id,role='SELECTED') for i,p in enumerate(players)}
    snapshot=runtime_snapshot(model,mapping,rows,packet=packet,season=season,week=week,slate=slate,
                              fmt='CLASSIC',decision_at=decision_at,
                              policy=dict(selection='unchanged sequential maximum baseline objective',
                                          constraints='exact current remaining exposures, overlap, stack, game and user constraints'))
    report=generate_shadow(packet,snapshot,requested_per_thesis=budget,baseline_count=0,seed=7)
    report.update(mode='ANALYST_CONSTRUCTION', production_defaults_changed=True,
                  selection_status='exact current baseline objective comparison',final_portfolio_selected=False)
    return report


def annotate_showdown_selection(report, selected, selection_report):
    selected_keys={tuple(sorted((str(p['player_id']),p['roster_position']) for p in lineup)) for lineup in selected}
    variants={}
    for row in selection_report.get('ranked_metrics',[]):
        key=tuple(sorted((str(p['player_id']),p['slot']) for p in row.get('players',[])))
        variants.setdefault(key,[]).append(row)
    for candidate in report.get('shadow',[]):
        key=tuple(sorted((p['player_master_id'],p['role']) for p in candidate['roster']))
        rows=variants.get(key,[])
        row=next((r for r in rows if r.get('scenario_id')=='baseline'), rows[0] if rows else None)
        candidate['selector_variant_outcomes']=[dict(scenario_id=r.get('scenario_id'),
            rank=r.get('rank'),quality_eligible=r['quality_eligible'],
            baseline_constraint_survives=r.get('baseline_constraint_survives')) for r in rows]
        candidate['selected']=key in selected_keys
        candidate['quality_screen_status']='evaluated_unchanged_existing_selector' if row else 'not_separately_evaluated'
        if row:
            candidate['quality_eligible']=row['quality_eligible']
            candidate['constraint_survives']=row.get('baseline_constraint_survives')
            if not row['quality_eligible']:
                candidate['eligibility_outcome']='DIAGNOSTIC_ONLY_existing_quality_screen'
    report['comparison']['diagnostic_only']=sum(str(c['eligibility_outcome']).startswith('DIAGNOSTIC_ONLY') for c in report.get('shadow',[]))
    report['selection_policy']=dict(quality_fraction=selection_report.get('quality_fraction'),
                                    quality_basis=selection_report.get('quality_basis'),constraints='unchanged existing portfolio selector')


def summarize_report(report, lineups):
    steps=report.get('steps') or [report]
    theses=[t for step in steps for t in step.get('theses',[])]
    attributed={}
    for step in steps:
        for candidate in step.get('shadow',[]):
            key=tuple(sorted((p['player_master_id'],p['role']) for p in candidate['roster']))
            attributed.setdefault(key,set()).update(candidate['thesis_ids'])
    for lineup in lineups:
        key=tuple(sorted((str(p['player_id']),p.get('roster_position') if p.get('roster_position') in {'CPT','FLEX'} else 'SELECTED') for p in lineup))
        if key in attributed:
            lineup[0]['analyst_thesis_ids']=sorted(attributed[key])
            lineup[0]['analyst_packet_sha256']=report.get('packet_sha256')
            lineup[0]['analyst_construction_only']=True
    report.update(generated_candidate_count=sum(len(step.get('shadow',[])) for step in steps),
                  requested_candidate_count=sum(t['requested'] for t in theses),
                  selected_lineup_count=sum(bool(lineup and lineup[0].get('analyst_thesis_ids')) for lineup in lineups),
                  abstention_count=sum(not t['achieved'] for t in theses),
                  status=report.get('status') or ('generated' if any(step.get('shadow') for step in steps) else 'abstained'))


def annotate_original_construction_comparison(report, *, params, lineups, coverage):
    """Label the deliberately selected original policy without claiming Analyst application."""
    if (params.get('analyst_optimization_intent') != 'EXPECTED_GAME'
            or params.get('analyst_strategy') != 'CONSTRUCTION' or not coverage):
        return
    report.update(mode='ORIGINAL_CONSTRUCTION_BASELINE', status='explicit_baseline_comparison', reasons=[],
        analyst_directives_applied=False, baseline_selected_lineup_count=len(lineups),
        baseline_candidate_attempt_count=len(coverage.get('captains', [])),
        baseline_generation_evidence=deepcopy(coverage),
        comparison_limitation='Same checked Expected Game evidence is retained for provenance only. Original Captain-coverage generation, shortlist and quality screens apply; Analyst scenario directives and scoring do not. A complete frozen candidate pool is not available for selector comparison.')
