"""Immutable offline Classic selection audit. Does not write production or tune inputs.

Run with PYTHONHASHSEED=0; --help documents the frozen file inputs.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, replace, asdict
from datetime import UTC, datetime
from hashlib import sha256
from itertools import combinations
import json
from math import ceil, floor
from pathlib import Path

import pulp

from backend.app.product_services.cbc_solver import make_cbc_solver, resolve_cbc_backend
from backend.app.product_services.classic_candidate_completeness import (
    compact_candidate, load_context, rank_candidates, recall, roster_key,
)
from backend.app.product_services.classic_prospective import digest_payload
from backend.app.product_services.classic_thesis_shadow import (
    _candidate_view, _dominance, _family_metrics,
)


@dataclass(frozen=True)
class Policy:
    name: str
    count: int = 5
    overlap: int = 6
    distinct_qb: bool = False
    minimum_qbs: int = 3
    minimum_stack_types: int = 2
    elevated_share: float = .6
    canonical_game_cap: int | None = None
    tolerance: float | None = None
    frontier: float | None = None
    objective: str = 'selector_sum'


def resolve_effective_policy(inputs: dict) -> Policy:
    """Mirror the current production branch, including its explicit-overlap override.

    This is an audit of current behavior, not a proposed preference resolution.
    The final path/family stage is recorded in the saved production tradeoffs.
    """
    report = inputs['report']
    options = report['frozen_solver_snapshot']['payload']['options']
    constraints = options.get('portfolio_constraints') or {}
    trades = report['production_controls']['selection_tradeoffs']
    paths = 3 if trades['path_frontier'].get('3', {}).get('feasible') and (
        trades['path_frontier']['2']['selector_sum'] - trades['path_frontier']['3']['selector_sum']
        <= options['requested_lineups'] * trades['quality_loss_tolerance_per_lineup'] + 1e-9) else 2
    families = 2 if trades.get('alternative_stack_family_selector_cost') is not None and (
        trades['alternative_stack_family_selector_cost'] <= options['requested_lineups'] *
        trades['quality_loss_tolerance_per_lineup'] + 1e-9) else 1
    return Policy('current_control_final_effective_policy_v1', count=options['requested_lineups'],
                  overlap=6, distinct_qb=constraints.get('distinct_qb_paths', False),
                  minimum_qbs=paths, minimum_stack_types=families,
                  elevated_share=report['production_controls']['policy']['selected_lineups_with_elevated_cap'],
                  tolerance=constraints.get('max_objective_loss'))


def selected_caps(inputs: dict) -> dict[str, float]:
    r = inputs['report']; p = r['frozen_solver_snapshot']['payload']
    options = p['options']; locked = set(options.get('locked_player_ids') or [])
    risk = {r['player_id']: r for r in r['prospective_experiment']['availability_risk']['players']}
    caps = {}
    for player in p['players']:
        pid = player['player_id']
        if pid in locked:
            cap = 1.0
        else:
            cap = min(options['selection_max_exposure'], options['maximum_exposure_by_player'].get(pid, 1.0))
            if player['position'] == 'QB':
                cap = min(cap, .6)
            elif player['position'] in {'RB', 'WR', 'TE'} and r['production_controls']['core_classes'][pid] != 'elite_high_confidence':
                cap = min(cap, .8)
        bucket = risk.get(pid, {}).get('bucket', '')
        if bucket == 'questionable_elevated':
            cap = min(cap, r['production_controls']['policy']['elevated_selected_cap'])
        elif bucket == 'questionable_full_role':
            cap = min(cap, r['production_controls']['policy']['full_role_selected_cap'])
        caps[pid] = cap
    return caps


def eligibility(rows: list[dict], policy: Policy) -> list[dict]:
    frontier = policy.frontier if policy.frontier is not None else max((r['objective_score'] for r in rows), default=0)
    return [r for r in rows if policy.tolerance is None or frontier-r['objective_score'] <= policy.tolerance+1e-9]


def evidence_value(features: dict, field: str):
    """An unavailable model sentinel is not measured usage; a measured zero is.

    This only renders evidence in the audit. It never mutates model features.
    """
    if features.get(field+'_available') is False:
        return None
    return features.get(field)


def violations(rows: list[dict], policy: Policy, caps: dict, elevated: set,
               minimum_caps: dict | None = None) -> list[str]:
    reasons = []
    if len(rows) != policy.count: reasons.append('entry_count')
    if len({roster_key(r) for r in rows}) != len(rows): reasons.append('duplicate_roster')
    exposures = Counter(pid for r in rows for pid in r['player_ids'])
    for pid, n in exposures.items():
        if n > floor(policy.count*caps.get(pid, 1.0)+1e-9): reasons.append('cap:'+pid)
    for pid, cap in (minimum_caps or {}).items():
        if exposures[pid] < ceil(policy.count*cap): reasons.append('minimum_cap:'+pid)
    qbs = Counter(r['qb']['player_id'] for r in rows)
    if len(qbs) < policy.minimum_qbs: reasons.append('minimum_qbs')
    if policy.distinct_qb and max(qbs.values(), default=0)>1: reasons.append('distinct_qb')
    if len({r['stack']['type'] for r in rows}) < policy.minimum_stack_types: reasons.append('minimum_stack_types')
    if sum(bool(elevated & set(r['player_ids'])) for r in rows)>floor(policy.count*policy.elevated_share): reasons.append('elevated_budget')
    if any(len(set(a['player_ids']) & set(b['player_ids']))>policy.overlap for a,b in combinations(rows,2)): reasons.append('overlap')
    if policy.canonical_game_cap is not None and max(Counter(r['game_key'] for r in rows).values(),default=0)>policy.canonical_game_cap: reasons.append('canonical_game_cap')
    if len(eligibility(rows,policy)) != len(rows): reasons.append('quality_floor')
    return reasons


def solve(rows: list[dict], policy: Policy, caps: dict, elevated: set, *,
          families: dict | None = None, incumbent: list[dict] | None = None,
          minimum_caps: dict | None = None, log_path: Path | None = None) -> dict:
    """Proof-aware exact portfolio selection; feasible status never means optimal.

    The original portfolio is an explicit warm start and objective floor for the
    nested scalar comparison. All output rosters are mechanically validated.
    """
    rows = eligibility(rows, policy)
    if incumbent:
        missing = {roster_key(r) for r in incumbent}-{roster_key(r) for r in rows}
        if missing or violations(incumbent,policy,caps,elevated,minimum_caps):
            raise ValueError('Incumbent is not in the unchanged feasible set')
    if len(rows)<policy.count: return {'status':'infeasible', 'lineups':[], 'eligible_count':len(rows)}
    model=pulp.LpProblem('classic_reconciliation',pulp.LpMaximize)
    x=pulp.LpVariable.dicts('candidate', range(len(rows)),cat='Binary')
    model += pulp.lpSum(x.values()) == policy.count
    for pid in sorted({pid for r in rows for pid in r['player_ids']}):
        n=pulp.lpSum(x[i] for i,r in enumerate(rows) if pid in r['player_ids'])
        model += n <= floor(policy.count*caps.get(pid,1.0)+1e-9)
        if minimum_caps and minimum_caps.get(pid): model += n >= ceil(policy.count*minimum_caps[pid])
    model += pulp.lpSum(x[i] for i,r in enumerate(rows) if elevated & set(r['player_ids'])) <= floor(policy.count*policy.elevated_share)
    def active_groups(key, label, minimum=0, maximum=None):
        groups=sorted({key(r) for r in rows});active=pulp.LpVariable.dicts(label,range(len(groups)),cat='Binary')
        for j,g in enumerate(groups):
            n=pulp.lpSum(x[i] for i,r in enumerate(rows) if key(r)==g)
            model.addConstraint(n>=active[j]);model.addConstraint(n<=policy.count*active[j])
            if maximum is not None:model.addConstraint(n<=maximum)
        if minimum:model.addConstraint(pulp.lpSum(active.values())>=minimum)
        return active
    active_groups(lambda r:r['qb']['player_id'],'qb',policy.minimum_qbs,1 if policy.distinct_qb else None)
    active_groups(lambda r:r['stack']['type'],'stack',policy.minimum_stack_types)
    if policy.canonical_game_cap is not None:active_groups(lambda r:r['game_key'],'canonical_game',maximum=policy.canonical_game_cap)
    sets=[set(r['player_ids']) for r in rows]
    for i,left in enumerate(sets):
        for j in range(i+1,len(rows)):
            if len(left & sets[j])>policy.overlap:model += x[i]+x[j]<=1
    score=pulp.lpSum(r['objective_score']*x[i] for i,r in enumerate(rows))
    if incumbent:
        model += score >= sum(r['objective_score'] for r in incumbent)-1e-8
        keys={roster_key(r) for r in incumbent}
        for i,r in enumerate(rows):x[i].setInitialValue(int(roster_key(r) in keys))
    objectives=[]
    if policy.objective=='frontier_theses_then_games_then_selector':
        frontier_ids={k for k,v in families.items() if v['pareto_status']=='frontier' and v['global_selector_gap']<=.20+1e-9}
        ids=sorted(frontier_ids & {r['thesis_id'] for r in rows})
        active=pulp.LpVariable.dicts('reward_thesis',range(len(ids)),cat='Binary')
        for j,f in enumerate(ids):
            n=pulp.lpSum(x[i] for i,r in enumerate(rows) if r['thesis_id']==f)
            model += n>=active[j];model += n<=policy.count*active[j]
        games=sorted({r['game_key'] for r in rows if r['thesis_id'] in frontier_ids})
        ga=pulp.LpVariable.dicts('reward_game',range(len(games)),cat='Binary')
        for j,g in enumerate(games):
            n=pulp.lpSum(x[i] for i,r in enumerate(rows) if r['game_key']==g and r['thesis_id'] in frontier_ids)
            model += n>=ga[j];model += n<=policy.count*ga[j]
        objectives=[pulp.lpSum(active.values()),pulp.lpSum(ga.values())]
    solver=make_cbc_solver(resolve_cbc_backend('auto'));solver.timeLimit=60
    solver.threads=1;solver.options += ['randomSeed 1','randomCbcSeed 1','increment 1e-10','primalTolerance 1e-9','dualTolerance 1e-9','integerTolerance 1e-9']
    solver.optionsDict.update(gapRel=0,gapAbs=0,warmStart=bool(incumbent))
    if log_path:solver.optionsDict['logPath']=str(log_path)
    stages=[]
    for j,objective in enumerate([*objectives,score]):
        model.setObjective(objective);status=model.solve(solver)
        proven=status==pulp.LpStatusOptimal and model.sol_status==pulp.LpSolutionOptimal
        stages.append({'lp_status':pulp.LpStatus[status],'solution_status':pulp.LpSolution[model.sol_status],
                       'proven_optimal':proven,'objective':pulp.value(objective)})
        if not proven:
            chosen=[r for i,r in enumerate(rows) if (x[i].value() or 0)>.9]
            valid=not violations(chosen,policy,caps,elevated,minimum_caps)
            return {'status':'infeasible' if status==pulp.LpStatusInfeasible else 'unproven',
                    'lineups':chosen if valid else [],'eligible_count':len(rows),'stages':stages}
        if j<len(objectives):model += objective == round(pulp.value(objective) or 0)
    chosen=[r for i,r in enumerate(rows) if (x[i].value() or 0)>.9]
    if violations(chosen,policy,caps,elevated,minimum_caps):raise ValueError('Solver output violates policy')
    return {'status':'optimal','lineups':chosen,'eligible_count':len(rows),'stages':stages}


def summary(result: dict, source: dict, risk: dict) -> dict:
    rows=result['lineups'];views=[_candidate_view(r,source,risk) for r in rows]
    players=Counter(pid for r in rows for pid in r['player_ids'])
    pairs=Counter(tuple(sorted((a,b))) for r in rows for a,b in combinations(r['player_ids'],2))
    names={pid:row['name'] for pid,row in source.items()}
    matrix=[[len(set(a['player_ids']) & set(b['player_ids'])) for b in rows] for a in rows]
    return {**result,'selector_sum':sum(r['objective_score'] for r in rows),
        'mean_sum':sum(r['mean'] for r in rows),'p90_sum':sum(r['p90'] for r in rows),
        'qb_directions':dict(Counter(r['qb'] for r in views)),
        'canonical_primary_games':dict(Counter(r['game_key'] for r in views)),
        'broad_directional_families':dict(Counter(f"{r['game_key']}|{r['qb_id']}" for r in views)),
        'construction_families':dict(Counter(r['thesis_id'] for r in views)),
        'player_exposures':{pid:{'name':names.get(pid,pid),'entries':n} for pid,n in sorted(players.items(),key=lambda v:(-v[1],v[0]))},
        'cores_in_at_least_three':[{'ids':list(k),'names':[names.get(pid,pid) for pid in k],'entries':n} for k,n in pairs.items() if n>=3],
        'all_entry_core':[names.get(pid,pid) for pid,n in players.items() if n==len(rows)],
        'overlap_matrix':matrix,'max_overlap':max((matrix[i][j] for i in range(len(rows)) for j in range(i+1,len(rows))),default=0),
        'roster_hashes':[r['roster_sha256'] for r in rows]}


def families_for(rows: list[dict], source: dict, risk: dict) -> tuple[list[dict],dict]:
    views=[_candidate_view(r,source,risk) for r in rows];groups=defaultdict(list)
    for r,v in zip(rows,views):r['thesis_id']=v['thesis_id'];groups[v['thesis_id']].append(v)
    best=max(r['objective_score'] for r in rows)
    families=[_family_metrics(g,views,best) for g in groups.values()]
    _dominance(families)
    return views,{f['thesis_id']:f for f in families}


def stage_attribution(reference: list[dict], discovered: list[dict], admitted: list[dict],
                      selected: list[dict], policy: Policy, elevated: set) -> dict:
    d,a,s=({roster_key(r) for r in pool} for pool in (discovered,admitted,selected))
    eligible={roster_key(r) for r in eligibility(admitted,policy)}
    out=[]
    for r in reference:
        key=roster_key(r)
        reason=('never_discovered' if key not in d else 'discovered_not_admitted' if key not in a else
                'admitted_rejected_by_lineup_quality' if key not in eligible else
                'selected' if key in s else 'eligible_not_selected')
        out.append({'roster_sha256':r['roster_sha256'],'stage':reason,
                    'risk_legal':len(elevated & set(r['player_ids']))<=1})
    return {'counts':dict(Counter(r['stage'] for r in out)),'rosters':out}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--control',type=Path,required=True)
    parser.add_argument('--expanded',type=Path,required=True)
    parser.add_argument('--old-inputs',type=Path,required=True)
    parser.add_argument('--thesis',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Choose a new immutable output')
    inputs=json.loads(args.control.read_text());old=json.loads(args.old_inputs.read_text())
    expanded=json.loads(args.expanded.read_text());thesis=json.loads(args.thesis.read_text())
    for payload in [expanded,thesis]:
        assert payload['sha256']==digest_payload({k:v for k,v in payload.items() if k!='sha256'})
    ctx=load_context(inputs);caps=selected_caps(inputs);r=inputs['report'];p=r['frozen_solver_snapshot']['payload']
    assert p['players']==old['report']['frozen_solver_snapshot']['payload']['players']
    assert p['resolved_config']==old['report']['frozen_solver_snapshot']['payload']['resolved_config']
    assert r['production_controls']['candidate_caps']==old['report']['production_controls']['candidate_caps']
    all_saved=expanded['raw_candidates']+r['all_candidates']
    scored={}
    for row in all_saved:
        fresh=compact_candidate(row['player_ids'],ctx)
        for field in ['objective_score','mean','p90']:
            if abs(fresh[field]-row[field])>1e-9:raise ValueError('Scoring changed: '+field)
        if len(set(row['player_ids']) & ctx['elevated'])<=ctx['policy']['max_elevated_per_lineup']:
            scored[roster_key(row)]=fresh
    union=rank_candidates(list(scored.values()))
    original=[{**scored[roster_key(row)],'rank':row['rank']} for row in r['all_candidates']]
    _,families=families_for(union,ctx['source'],ctx['risk']);families_for(original,ctx['source'],ctx['risk'])
    fixed=replace(resolve_effective_policy(inputs),frontier=max(row['objective_score'] for row in union))
    selected=[row for row in original if row['rank'] in r['selected_ranks']]
    assert not violations(selected,fixed,caps,ctx['elevated'])
    out={'contract':'classic_discovery_selection_reconciliation_v1','frozen_at':datetime.now(UTC).isoformat(),
         'files':{str(path):sha256(path.read_bytes()).hexdigest() for path in [args.control,args.expanded,args.old_inputs,args.thesis]},
         'input_sha256':digest_payload(inputs),'universe_sha256':digest_payload(union),
         'normalization':{'mean':max(pl.projection+pl.optimizer_context_adjustment for pl in ctx['players']),
                          'p90':max(pl.ceiling+pl.optimizer_context_adjustment for pl in ctx['players'])},
         'scoring_replay':{'checked':len(all_saved),'mismatches':0},'policies':{},'results':{},
         'original':original,'union':union,'families':families,'player_caps':caps,
         'saved_control':summary({'status':'saved','lineups':selected},ctx['source'],ctx['risk'])}
    logs=args.output.parent/'solver_logs';logs.mkdir(exist_ok=True)
    def execute(name,rows,policy,pcaps,inc=None,fam=None):
        result=solve(rows,policy,pcaps,ctx['elevated'],families=fam,incumbent=inc,
                     minimum_caps=p['options'].get('minimum_exposure_by_player'),log_path=logs/(name+'.log'))
        out['policies'][name]={**asdict(policy),'player_caps_sha256':digest_payload(pcaps)}
        out['results'][name]=summary(result,ctx['source'],ctx['risk'])
        print(name,result['status'],out['results'][name]['selector_sum'],flush=True)
        return result
    a=execute('original_fixed',original,fixed,caps,selected)
    b=execute('union_fixed',union,fixed,caps,a['lineups'] or selected)
    if a['status']==b['status']=='optimal':assert out['results']['union_fixed']['selector_sum']>=out['results']['original_fixed']['selector_sum']-1e-8
    previous=replace(fixed,name='previous_user_overlap4_distinctQB_shadow',overlap=4,distinct_qb=True,minimum_qbs=5)
    prior_caps={pid:min(cap,.8) for pid,cap in caps.items()}
    execute('previous_user_shadow',union,previous,prior_caps)
    execute('canonical_game_max3_shadow',union,replace(fixed,name='current_policy_game_max3_shadow',canonical_game_cap=3),caps)
    # Existing research thesis exposure policy is the immutable v3 policy (.8 global).
    dynamic=replace(fixed,name='existing_v3_dynamic_thesis_shadow',minimum_qbs=2,minimum_stack_types=1,
                    objective='frontier_theses_then_games_then_selector')
    dcaps=thesis['selection_caps']['player_caps']
    fixed_thesis=replace(dynamic,name='existing_v3_thesis_fixed020_shadow',tolerance=.20)
    execute('thesis_union_fixed020',union,fixed_thesis,dcaps,fam=families)
    for tolerance in [.05,.10,.15,.20,None]:
        test=execute('thesis_union_tolerance_'+str(tolerance),union,replace(dynamic,tolerance=tolerance),dcaps,fam=families)
        if test['lineups']:
            out['dynamic_chosen']='thesis_union_tolerance_'+str(tolerance);break
    # Reproduce the original fixture independently of current candidate refresh.
    old_pool=[{**scored[roster_key(row)],'rank':row['rank']} for row in old['report']['all_candidates']]
    _,old_families=families_for(old_pool,ctx['source'],ctx['risk'])
    for tolerance in [.05,.10,.15,.20,None]:
        test=execute('thesis_original_tolerance_'+str(tolerance),old_pool,replace(dynamic,tolerance=tolerance),dcaps,fam=old_families)
        if test['lineups']:
            out['old_dynamic_chosen']='thesis_original_tolerance_'+str(tolerance);break
    # Exact original expanded artifact, excluding newly saved current rosters.
    old_union=rank_candidates([scored[roster_key(row)] for row in expanded['raw_candidates'] if roster_key(row) in scored])
    _,ef=families_for(old_union,ctx['source'],ctx['risk'])
    execute('thesis_original_expanded015',old_union,replace(dynamic,tolerance=.15),dcaps,fam=ef)
    excluded=[row for row in union if fixed.frontier-row['objective_score']>.15+1e-9 and fixed.frontier-row['objective_score']<=.20+1e-9]
    out['dynamic_exclusions']={'count':len(excluded),'qb_counts':dict(Counter(row['qb']['name'] for row in excluded)),
          'canonical_games':dict(Counter(row['game_key'] for row in excluded)),
          'families':dict(Counter(row['thesis_id'] for row in excluded)),
          'roster_hashes':[row['roster_sha256'] for row in excluded]}
    # Density intervention: only add existing CIN|JAX discoveries to old admitted pool.
    near_game=rank_candidates(list({roster_key(row):row for row in old_pool+[row for row in old_union
                if row['game_key']=='CIN|JAX' and fixed.frontier-row['objective_score']<=.15+1e-9]}.values()))
    _,nf=families_for(near_game,ctx['source'],ctx['risk'])
    execute('density_only_same_game015',near_game,replace(dynamic,tolerance=.15),dcaps,fam=nf)
    for target,t in expanded['targets'].items():
        admitted=[{**scored[roster_key(row)],'rank':row['rank']} for row in t['admitted']]
        families_for(admitted,ctx['source'],ctx['risk'])
        solved=execute('admitted_'+target,admitted,fixed,caps)
        out.setdefault('admission',{})[target]={'recall':recall(union,admitted,fixed.frontier),
            'attribution':stage_attribution(union,old_union,admitted,solved['lineups'],fixed,ctx['elevated'])}
    out['original_attribution']=stage_attribution(union,expanded['historical_raw_candidates'],original,a['lineups'],fixed,ctx['elevated'])
    for label,pid in [('chase_brown','0be06444-4cd6-41a4-98a5-877a9a5c42b2'),('dolphins_dst','1f3ab2b3-189f-420b-a120-d0acec6b43d1')]:
        for n in [5,4,3]:
            execute(label+'_max'+str(n),union,replace(fixed,name=fixed.name+'_'+label+'_max'+str(n)),{**caps,pid:min(caps[pid],n/5)})
    out['coverage']={'original':recall(union,original,fixed.frontier),'union':recall(union,union,fixed.frontier)}
    out['sha256']=digest_payload(out)
    with args.output.open('x') as handle:json.dump(out,handle,indent=2,sort_keys=True,allow_nan=False)
    print('frozen',args.output,out['sha256'],flush=True)


if __name__=='__main__':main()
