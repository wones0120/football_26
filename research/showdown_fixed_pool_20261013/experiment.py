"""Offline fixed-pool research: verify, freeze, then evaluate. No candidate generation."""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import subprocess
from zoneinfo import ZoneInfo

import pandas as pd
import pulp

from .capture import OUT, ROOT, RUNS, CODE, REPORT, read_report, save, sha

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def signature(candidate):
    players=candidate['players']
    pairs=tuple(sorted((str(p['player_id']),str(p.get('slot',p.get('roster_position'))).upper()=='CPT') for p in players))
    if len(pairs)!=6 or len({p for p,_ in pairs})!=6 or sum(c for _,c in pairs)!=1:
        raise ValueError('Six unique canonical players and one Captain required')
    return pairs

def roster_id(candidate):
    return digest(signature(candidate))

def deduplicate(rows):
    grouped=defaultdict(list)
    for row in rows:
        grouped[signature(row)].append(row)
    result=[]
    for sig, variants in sorted(grouped.items()):
        # Pregame only: maximum recorded common-baseline selector; baseline
        # preferred on equal scores, then scenario ID and recorded rank.
        representative=min(variants,key=lambda v:(-float(v['selector']),v.get('scenario_id')!='baseline',v.get('scenario_id','baseline'),v['rank']))
        row=deepcopy(representative)
        row['roster_id']=roster_id(row)
        row['variant_ranks']=sorted(v['rank'] for v in variants)
        row['signature']=sig
        for field in ['mean','p90','baseline_mean','baseline_p90','salary']:
            values=[float(v.get(field,v.get(field.replace('baseline_','')))) for v in variants]
            if max(values)-min(values)>1e-7:
                raise ValueError(f'Variant baseline inconsistency: {field}, {row["roster_id"]}')
        result.append(row)
    return result

def quantized(value):
    return int((Decimal(str(value))*Decimal(1000000)).quantize(Decimal(1),rounding=ROUND_HALF_EVEN))

def solve(rows, limits, captain_limit, requested, score=None, size=None, stable=False):
    model=pulp.LpProblem('fixed_pool_only',pulp.LpMaximize)
    variables={i:pulp.LpVariable(f'candidate_{i}',cat='Binary') for i in range(len(rows))}
    count=pulp.lpSum(variables.values())
    model += count <= requested if size is None else count == size
    for pid,limit in limits.items():
        model += pulp.lpSum(variables[i] for i,r in enumerate(rows) if pid in {p for p,_ in signature(r)}) <= limit
    for captain in sorted({next(p for p,c in signature(r) if c) for r in rows}):
        model += pulp.lpSum(variables[i] for i,r in enumerate(rows) if (captain,True) in signature(r)) <= captain_limit
    groups=defaultdict(list)
    for i,r in enumerate(rows):
        groups[signature(r)].append(i)
    for indexes in groups.values():
        model += pulp.lpSum(variables[i] for i in indexes)<=1
    if score is None:
        objective=count
    else:
        weights=[quantized(r[score]) if stable else float(r[score]) for r in rows]
        objective=pulp.lpSum(weights[i]*variables[i] for i in variables)
    model += objective
    solver=pulp.PULP_CBC_CMD(msg=False,threads=1,options=['randomSeed 0'])
    status=model.solve(solver)
    if status==pulp.LpStatusInfeasible:
        return None
    if status!=pulp.LpStatusOptimal:
        raise ValueError('Solver failed: '+pulp.LpStatus[status])
    optimum=pulp.value(objective) or 0
    if stable and score is not None:
        # Exact integer optimum followed by canonical-roster lexicographic tie
        # break. This cannot introduce postgame information or alter constraints.
        model += objective == round(optimum)
        for i in variables:
            model.setObjective(variables[i])
            assert model.solve(solver)==pulp.LpStatusOptimal
            model += variables[i] == int(variables[i].value()>.5)
    selected=[r for i,r in enumerate(rows) if variables[i].value()>.5]
    return dict(rows=selected,count=len(selected),objective=optimum)

def budgets(config, runtime):
    policy=runtime['showdown_portfolio_policy']
    requested=int(config['num_lineups'])
    rates=policy['exposure_rates']
    starters={str(v['player_id']) for v in runtime['starter_qb_filter']['selected']}
    starters.update(runtime['starter_qb_filter'].get('specialty_qb_ids',[]))
    limits={}
    for row in runtime['player_pool']['rows']:
        if not row['included']:
            continue
        pid=str(row['player_id'])
        rate=rates['starting_qb'] if row['position']=='QB' and pid in starters else rates['cheap_punt'] if float(row['salary'])<=1000 else rates['core']
        limits[pid]=max(1,math.ceil(requested*rate))
    captain_limit=max(1,math.ceil(requested*rates['captain']))
    exposure=policy.get('exposure_report',{})
    if exposure:
        assert exposure['cap_denominator']==requested
        assert exposure['captain_maximum_appearances']==captain_limit
        for r in exposure['rows']:
            assert r['maximum_allowed_appearances']==(captain_limit if r['scope']=='captain' else limits[r['player_id']])
    return limits,captain_limit,requested

def validate_portfolio(rows,limits,captain_limit,size):
    assert len(rows)==size
    assert len({signature(r) for r in rows})==size
    counts=Counter(pid for r in rows for pid,_ in signature(r))
    captains=Counter(pid for r in rows for pid,cpt in signature(r) if cpt)
    assert all(count<=limits[pid] for pid,count in counts.items())
    assert all(count<=captain_limit for count in captains.values())
    return dict(player_counts=dict(counts),captain_counts=dict(captains),passed=True)

def candidate_checks(row, player_by_id, config):
    sig=signature(row)
    assert all(pid in player_by_id and player_by_id[pid]['included'] for pid,_ in sig)
    assert float(row['salary'])<=50000+1e-7
    captain=player_by_id[next(pid for pid,cpt in sig if cpt)]
    allowed=config.get('captain_positions',[])
    assert not allowed or captain['position'] in allowed
    assert not (captain.get('flex_only') or captain['player_id'] in config.get('flex_only_player_ids',[]))
    ids={pid for pid,_ in sig}
    assert set(config.get('locked_player_ids',[]))<=ids
    assert not ids.intersection(config.get('exclude_player_ids',[]))
    qb_count=sum(player_by_id[pid]['position']=='QB' for pid in ids)
    assert not config.get('no_qbs') or qb_count==0
    assert not config.get('no_two_qbs') or qb_count<=1
    assert not config.get('no_qb_captain') or captain['position']!='QB'
    team_counts=Counter(player_by_id[pid]['team'] for pid in ids)
    assert max(team_counts.values())<=int(config.get('max_players_per_team') or 5)

def reconstruct(row, players, spreads=None):
    sig=signature(row)
    mean=sum(float(players[pid]['projection'])*(1.5 if cpt else 1) for pid,cpt in sig)
    p90=sum(float(players[pid]['p90'])*(1.5 if cpt else 1) for pid,cpt in sig)
    current=sum(float(players[pid]['p90'])*1.5 if cpt else float(players[pid]['projection']) for pid,cpt in sig)
    assert abs(mean-float(row.get('baseline_mean',row['mean'])))<1e-7
    assert abs(p90-float(row.get('baseline_p90',row['p90'])))<1e-7
    cap=next(pid for pid,cpt in sig if cpt)
    alternative=mean+1.5*(float(players[cap]['p90'])-float(players[cap]['projection']))
    assert abs(current-alternative)<1e-7
    old_base=sum((float(players[pid]['p90'])+float(players[pid]['optimizer_context_adjustment']))*(1.5*float(row['captain_objective_multiplier']) if cpt else 1) for pid,cpt in sig)
    residual=float(row['selector'])-old_base-float(row.get('correlation') or 0)
    correction=0.0
    if spreads is not None:
        # Historical solver scales positive terms by required/captain indexes;
        # reporting scales by evidence players, which also includes QBs in
        # count-only construction terms. Undo precisely that reporting mismatch.
        counts=Counter(players[pid]['team'] for pid,_ in sig)
        qb_reference=max(float(p['projection']) for p in players.values() if p['included'] and p['position']=='QB')
        split=sorted(counts.values())
        for team,count in counts.items():
            target_teams=set(counts) if split==[3,3] else {team}
            factors=[max(.4,min(1,float(players[pid]['projection'])/qb_reference))
                     for pid,_ in sig if players[pid]['position']=='QB' and players[pid]['team'] in target_teams]
            factor=min(factors,default=1)
            competitive=max(0,min(1,1-abs(spreads[team])/7))
            contribution=(.35*competitive if split==[3,3] and team==sorted(counts)[0] else
                          .20*competitive if count==4 else
                          .60*max(0,min(1,(-spreads[team]-3)/10)) if count==5 else 0)
            correction+=contribution*(1-factor)
    return dict(current_score=current,mean_score=mean,p90_score=p90,
                historical_additive_residual=residual, historical_reporting_correction=correction,
                historical_corrected_residual=residual-correction)

def load_shortlist():
    path=OUT/'inputs/code/backend/app/product_services/showdown_captain_shortlist.py'
    spec=importlib.util.spec_from_file_location('backend.app.product_services.frozen_research_shortlist',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_captain_shortlist

def verify_inputs():
    manifest=json.loads((OUT/'input_manifest.json').read_text())
    for p,expected in manifest['code_sha256'].items():
        assert sha(OUT/'inputs/code'/p)==expected
        assert sha(ROOT/p)==expected,'Live code changed after capture: '+p
    assert sha(REPORT)==manifest['report']['sha256']
    for run_id,expected in manifest['source_sha256'].items():
        assert sha(OUT/'inputs'/f'{run_id}.json')==expected
    return manifest

def verify():
    verify_inputs()
    report=read_report()
    reported={r['optimizer_run_id']:r for s in report['slate_reports'] for r in s['optimizer_effectiveness']['runs']}
    results=[]
    for run_id in RUNS:
        source=json.loads((OUT/'inputs'/f'{run_id}.json').read_text())
        run=source['run'];config=run['constraint_config_json'];runtime=config['strategy_runtime'];selection=runtime['showdown_portfolio_policy']['candidate_selection'];variants=selection['ranked_metrics']
        assert not selection.get('require_scenario_diversity') and not selection.get('soft_scenario_diversity')
        assert [r['rank'] for r in variants]==list(range(1,len(variants)+1))
        if run_id in reported:
            assert digest(variants)==reported[run_id]['candidate_pool']['sha256']
        manifest=runtime.get('candidate_pool_manifest',{})
        if manifest.get('sha256'):
            assert digest(variants)==manifest['sha256']
        best_mean=max(r.get('baseline_mean',r['mean']) for r in variants)
        best_p90=max(r.get('baseline_p90',r['p90']) for r in variants)
        assert abs(best_mean-selection['best_mean'])<1e-7 and abs(best_p90-selection['best_p90'])<1e-7
        assert selection['quality_fraction']==.95
        for r in variants:
            eligible=r.get('baseline_mean',r['mean'])+1e-8>=.95*best_mean and r.get('baseline_p90',r['p90'])+1e-8>=.95*best_p90
            assert eligible==r['quality_eligible']
        limits,cap,requested=budgets(config,runtime)
        eligible=[r for r in variants if r['quality_eligible']]
        cardinality=solve(eligible,limits,cap,requested)
        replay=solve(eligible,limits,cap,requested,score='selector',size=cardinality['count'])
        saved=[r for r in variants if r['rank'] in selection['selected_ranks']]
        validate_portfolio(saved,limits,cap,len(saved))
        assert cardinality['count']==len(saved),'Historical cardinality mismatch'
        saved_score=sum(float(r['selector']) for r in saved)
        replay_score=sum(float(r['selector']) for r in replay['rows'])
        assert abs(saved_score-replay_score)<1e-6,'Historical objective mismatch'
        physical_match={signature(r) for r in saved}=={signature(r) for r in replay['rows']}
        players={str(r['player_id']):r for r in runtime['player_pool']['rows']}
        raw_players=config.get('showdown_evidence_snapshot',{}).get('player_pool',[]) or [r['player_json'] for r in source['selected_players']]
        spreads={p.get('player_team',p.get('team')):float(p['team_spread_line']) for p in raw_players if p.get('team_spread_line') is not None}
        rosters=deduplicate(variants)
        for row in rosters:
            candidate_checks(row,players,config)
            row.update(reconstruct(row,players,spreads))
            assert abs(row['historical_corrected_residual'])<1e-7, 'Unexplained historical objective residual'
        # Verify original selected-player persistence agrees with saved candidates.
        persisted=defaultdict(list)
        for row in source['selected_players']:
            persisted[row['lineup_id']].append({'player_id':row['player_id'],'slot':row['roster_position']})
        assert {signature({'players':v}) for v in persisted.values()}=={signature(r) for r in saved}
        frozen=config.get('showdown_evidence_snapshot',{})
        chronology=dict(status='unverified',reason='No original explicitly zoned frozen input timestamp',database_created_at=run['created_at'])
        if frozen:
            assert digest({k:v for k,v in frozen.items() if k!='sha256'})==frozen['sha256']
            kicks=[]
            for row in frozen['player_pool']:
                match=re.search(r'(\d{2}/\d{2}/\d{4} \d{2}:\d{2}[AP]M) ET',row['game_id'])
                if match:
                    kicks.append(datetime.strptime(match.group(1),'%m/%d/%Y %I:%M%p').replace(tzinfo=ZoneInfo('America/New_York')))
            kickoff=min(kicks);decision=datetime.fromisoformat(frozen['frozen_at']);cutoff=datetime.fromisoformat(frozen['evidence_cutoff'])
            assert cutoff<=decision<kickoff
            assert datetime.fromisoformat(source['projection_run']['created_at'])<kickoff
            assert datetime.fromisoformat(source['projection_run']['data_cutoff_at'])<kickoff
            native={str(r['player_id']):r for r in frozen['player_pool']}
            for pid,p in players.items():
                if p['included']:
                    assert pid in native
                    assert abs(float(p['p90'])-float(native[pid]['p90']))<1e-7
                    assert abs(float(p['projection'])-float(native[pid]['projection']))<1e-7
            chronology=dict(status='pregame_frozen_inputs',frozen_at=frozen['frozen_at'],cutoff=frozen['evidence_cutoff'],kickoff_at=kickoff.isoformat(),projection_created_at=source['projection_run']['created_at'],snapshot_sha256=frozen['sha256'],preferences_basis='Saved exact optimizer parameters; no separately timestamped preference revision or optimizer executable hash')
        shortlist={}
        if chronology['status']=='pregame_frozen_inputs':
            frame=pd.DataFrame([dict(r,name=r['player_name'],player_team=r['team']) for r in players.values() if r['included']])
            _,shortlist=load_shortlist()(frame,params=config,flex_only_ids={p for p,r in players.items() if r.get('flex_only')} | set(config.get('flex_only_player_ids',[])))
        shortlisted={r['player_id'] for r in shortlist.get('shortlist',[])}
        for r in rosters:
            r['current_captain_eligible']=next(p for p,c in signature(r) if c) in shortlisted
        common=[r for r in rosters if r['quality_eligible'] and r['current_captain_eligible']]
        common_size=solve(common,limits,cap,requested)['count'] if shortlist else None
        residuals=[r['historical_additive_residual'] for r in rosters]
        result=dict(run_id=run_id,week=run['week'],slate=run['slate_id'],variant_count=len(variants),roster_count=len(rosters),
            pool_sha256=digest(variants),historical_selected_ranks=selection['selected_ranks'],replay_variant_ranks=[r['rank'] for r in replay['rows']],
            historical_physical_match=physical_match,historical_optimum_match=True,historical_size=len(saved),requested=requested,
            historical_objective=saved_score,replay_objective=replay_score,quality_thresholds=dict(mean=.95*best_mean,p90=.95*best_p90),
            quality_eligible_variants=len(eligible),quality_eligible_rosters=sum(r['quality_eligible'] for r in rosters),
            quality_excluded_rosters=sum(not r['quality_eligible'] for r in rosters),current_captain_excluded_rosters=sum(not r['current_captain_eligible'] for r in rosters) if shortlist else None,
            current_captain_excluded_quality_rosters=sum(r['quality_eligible'] and not r['current_captain_eligible'] for r in rosters) if shortlist else None,
            common_eligible_count=len(common),common_size=common_size,player_limits=limits,captain_limit=cap,
            exposure_rates=runtime['showdown_portfolio_policy']['exposure_rates'],cap_denominator=requested,
            ownership_policy=runtime.get('showdown_ownership_selector_policy'),captain_prior=runtime.get('captain_position_model'),
            chronology=chronology,current_shortlist=shortlist,projection_identity=dict(projection_run_id=run['projection_run_id'],model_artifact=config.get('decision_snapshot',{}).get('projection_model_artifact')),
            historical_additive_reconstruction=dict(max_abs_residual=max(abs(v) for v in residuals),nonzero_rosters=sum(abs(v)>1e-7 for v in residuals),
                max_abs_corrected_residual=max(abs(r['historical_corrected_residual']) for r in rosters),
                conclusion='Aggregate historical objective reproduced after undoing summary-only QB scaling of positive count-construction terms; raw per-candidate trigger decomposition is not retained'),
            preference_inputs={k:config.get(k) for k in ['captain_positions','no_qbs','no_two_qbs','no_qb_captain','exclude_questionable','max_players_per_team','exclude_opponent_teams','locked_player_ids','exclude_player_ids','flex_only_player_ids']},
            omission_reasons=selection['omission_reasons'],rosters=rosters,
            saved_roster_ids=sorted(roster_id(r) for r in saved),replay_roster_ids=sorted(roster_id(r) for r in replay['rows']))
        if not physical_match:
            # A different equally optimal physical portfolio is a material finding,
            # not permission to treat the recorded choice as reproduced exactly.
            result['reproduction_caveat']='Equal count and objective; physical portfolio differs under solver ties. Original selection retained as reference.'
        results.append(result)
    # Verification is an iterative pre-freeze work product. A frozen run may not
    # be revised; all source inputs remain immutable throughout.
    if (OUT/'freeze.json').exists():
        raise ValueError('Verification cannot be rewritten after freeze')
    (OUT/'verification.json').write_text(json.dumps(dict(runs=results,alternative_outcomes_computed=False),indent=2,sort_keys=True)+'\n')
    for r in results:
        print(r['week'],r['slate'],r['historical_physical_match'],r['historical_size'],r['common_eligible_count'],r['common_size'],r['historical_additive_reconstruction'])

SPEC = '''# Frozen retrospective fixed-candidate-pool experiment

This specification is saved and hashed before alternative selections are evaluated
against outcomes. All six named slates were inspected previously. No held-out claim.

1. First verify saved candidate hashes, dual 95% eligibility, exposure budgets,
   maximum cardinality, historical objective optimum and persisted physical rosters.
   Tied historical variants may differ; physical roster/objective discrepancies must
   be disclosed and investigated before outcomes. Historical reference is the saved
   portfolio, not a reselected portfolio under new Captain eligibility.
2. Deduplicate using (canonical Captain ID, sorted six canonical player IDs).
   Select the variant with largest recorded baseline selector; equal scores prefer
   baseline, then scenario ID and recorded rank. Require identical baseline mean,
   marginal P90 sum and salary across variants. Never use actuals to choose a variant.
3. Reconstruct current scoring exactly as 1.5 * Captain base P90 + sum(FLEX base
   means). No Captain prior, ownership, leverage, context or correlation contributions.
   Current top-four Captain eligibility uses every historically included player,
   historical pregame P90, saved Captain preferences/FLEX-only exclusions, and
   canonical-ID tiebreak. Missing reconstructable evidence blocks that slate.
4. Every comparison arm uses the same distinct canonical rosters, current Captain
   eligibility, historical user/model eligibility and historical player/Captain caps.
   Retain the ORIGINAL dual thresholds: 95% of separate full original-pool maxima.
   Do not recompute thresholds after Captain filtering. No quality-screen ablation.
   Retain historical generation legality; verify explicit saved player/role/team
   preferences. No candidate regeneration, new projections, simulations or latest data.
5. Establish maximum common feasible size with a count-only ILP BEFORE outcomes.
   All arms must choose exactly that size. Caps use original requested count (five),
   including Thursday underfill; do not retighten to realized size. Empty feasible
   portfolios are reported, not relaxed. No extra overlap/diversity constraints.
6. Arms: current role-specific score, total projected mean with CPT multiplied 1.5,
   summed marginal player P90 with CPT multiplied 1.5. Maximize portfolio sum.
   Quantize scores to nearest 1e-6 (Decimal half-even), maximize integer total, then
   prefer lexicographically earliest canonical rosters among tied optimal portfolios.
   Single-thread CBC with randomSeed 0. Save chosen IDs and verify constraint parity.
7. Freeze specification, prepared inputs and research/code hashes before separately
   capturing/evaluating outcomes. Canonical actuals require resolved IDs and agreement
   across contests; undo CPT multiplication before applying it once to each roster.
   Never impute missing/conflicting scores. Use report's frozen field thresholds.
8. Per slate: average actual, best actual, and number reaching each contest threshold.
   Show contest-specific thresholds separately; no repeated-contest weighting or pooled
   lineup correlations. Use one slate observation for comparisons. Pool-best actual is
   a hindsight coverage diagnostic, not an achievable benchmark. Entry choice remains
   separate. Report deduplicated within-slate historical metric correlations.
9. Exclude W4 Sunday night from chronological validation unless explicitly zoned
   original pregame generation evidence is established. Reproduce its historical saved
   portfolio descriptively but do not evaluate alternatives without that evidence.
   No uninspected slate has been designated; no held-out or future-improvement claims.
10. Exact contemporaneous historical optimizer executable/version attestation is
    absent. Stored scoring inputs, coefficients, library labels and full selectors
    support selection replay. Aggregate historical reconstruction explicitly undoes
    the summary-only QB scaling of positive count-construction terms, verified
    against every saved selector. Raw per-candidate trigger breakdown is absent.
    This experiment does not validate today's generator or production defaults.
'''

def freeze():
    manifest=verify_inputs()
    verification=json.loads((OUT/'verification.json').read_text())
    assert all(r['historical_optimum_match'] and r['historical_physical_match'] for r in verification['runs']), 'Investigate physical replay discrepancies before freezing'
    save(OUT/'prepared.json',verification)
    path=OUT/'SPECIFICATION.md'
    if path.exists():
        assert path.read_text()==SPEC,'Specification already frozen; do not overwrite'
    else:
        path.write_text(SPEC)
    code={f.name:sha(f) for f in OUT.glob('*.py')}
    save(OUT/'freeze.json',dict(specification_sha256=sha(path),prepared_sha256=sha(OUT/'prepared.json'),
        research_code_sha256=code,input_manifest_sha256=sha(OUT/'input_manifest.json'),
        created_at=datetime.now(timezone.utc).isoformat(),alternative_outcome_results_present=False,
        pulp_version=pulp.__version__,solver_path=pulp.PULP_CBC_CMD().path,
        solver_sha256=sha(pulp.PULP_CBC_CMD().path),git_head=manifest['git_head']))
    print('FROZEN',sha(path),'prepared',sha(OUT/'prepared.json'))

def actuals(rows):
    values=defaultdict(set)
    for r in rows:
        if r['resolution_status']=='resolved' and r['player_id'] and r['actual_points'] is not None:
            base=float(r['actual_points'])/(1.5 if r['roster_position']=='CPT' else 1)
            values[r['player_id']].add(round(base,2))
    return {pid:next(iter(v)) for pid,v in values.items() if len(v)==1}, sorted(pid for pid,v in values.items() if len(v)>1)

def evaluate():
    verify_inputs()
    frozen=json.loads((OUT/'freeze.json').read_text())
    assert frozen['specification_sha256']==sha(OUT/'SPECIFICATION.md')
    assert frozen['prepared_sha256']==sha(OUT/'prepared.json')
    assert frozen['input_manifest_sha256']==sha(OUT/'input_manifest.json')
    for p,h in frozen['research_code_sha256'].items():
        assert sha(OUT/p)==h,'Research code changed after freeze'
    assert frozen['solver_sha256']==sha(pulp.PULP_CBC_CMD().path)
    prepared=json.loads((OUT/'prepared.json').read_text())
    report=json.loads((OUT/'outcomes/report_evidence.json').read_text())
    from backend.app.product_services.optimizer_effectiveness import metric_correlations
    results=[]
    for run in prepared['runs']:
        run=deepcopy(run)
        base,conflicts=actuals(json.loads((OUT/'outcomes'/f'{run["run_id"]}.json').read_text()))
        scores={}
        for row in run['rosters']:
            sig=signature(row)
            scores[row['roster_id']]=round(sum(base[pid]*(1.5 if cpt else 1) for pid,cpt in sig),2) if all(pid in base for pid,_ in sig) else None
        run['outcome_conflicting_player_ids']=conflicts
        run['unscored_roster_ids']=[k for k,v in scores.items() if v is None]
        run['pool_best_hindsight_actual']=max((v for v in scores.values() if v is not None),default=None)
        run['deduplicated_historical_correlations']=metric_correlations([dict(pregame=dict(mean=r['mean_score'],p90=r['p90_score'],objective_score=r['selector']),postgame=dict(actual_points=scores[r['roster_id']])) for r in run['rosters']])
        rep=next((s for s in report['slates'] if any(r['optimizer_run_id']==run['run_id'] for r in s['runs'])),None)
        fields=rep['field_benchmarks'] if rep else {}
        def summarize(chosen):
            points=[scores[r['roster_id']] for r in chosen]
            complete=all(p is not None for p in points)
            attainment={}
            for contest_id,field in fields.items():
                if field['status']!='available':
                    continue
                thresholds={**field['thresholds'],'cash':field['cash_line'],'winner':field['winner']}
                attainment[contest_id]={k:dict(threshold=v,count=sum(p>=v-.005 for p in points) if complete and v is not None else None) for k,v in thresholds.items()}
            return dict(roster_ids=[r['roster_id'] for r in chosen],representative_ranks=[r['rank'] for r in chosen],
                actual_points=points,average_actual=sum(points)/len(points) if complete and points else None,
                best_actual=max(points) if complete and points else None,complete=complete,contest_attainment=attainment)
        historic=[r for r in run['rosters'] if r['roster_id'] in run['saved_roster_ids']]
        run['historical_reference']=summarize(historic)
        if rep:
            original=next(r for r in rep['runs'] if r['optimizer_run_id']==run['run_id'])
            assert abs(original['best_selected_actual']-run['historical_reference']['best_actual'])<.005
            assert abs(original['best_generated_actual']-run['pool_best_hindsight_actual'])<.005
            run['entry_choice_reference']=dict(best_matched_entered_actual=original['best_entered_actual'],assignment_evidence='Report signature matches; not certified contemporaneous user intent')
        run['arms']={}
        if run['chronology']['status']=='pregame_frozen_inputs':
            eligible=sorted((r for r in run['rosters'] if r['quality_eligible'] and r['current_captain_eligible']),key=lambda r:signature(r))
            size=run['common_size']
            assert solve(eligible,run['player_limits'],run['captain_limit'],run['requested'])['count']==size
            for label,key in [('current','current_score'),('mean','mean_score'),('p90','p90_score')]:
                solution=solve(eligible,run['player_limits'],run['captain_limit'],run['requested'],score=key,size=size,stable=True)
                assert solution is not None
                check=validate_portfolio(solution['rows'],run['player_limits'],run['captain_limit'],size)
                assert all(r['quality_eligible'] and r['current_captain_eligible'] for r in solution['rows'])
                run['arms'][label]={**summarize(solution['rows']), 'score_key':key,'integer_objective':solution['objective'],
                    'constraints_sha256':digest(dict(eligible_roster_ids=sorted(r['roster_id'] for r in eligible),limits=run['player_limits'],captain_limit=run['captain_limit'],size=size,thresholds=run['quality_thresholds'])),
                    'constraint_check':check}
            assert len({a['constraints_sha256'] for a in run['arms'].values()})==1
            run['evaluation_status']='retrospective_comparison'
        else:
            run['evaluation_status']='blocked_unverified_pregame_generation'
        results.append(run)
    save(OUT/'results.json',dict(runs=results,retrospective=True,held_out_slates=[],freeze_sha256=sha(OUT/'freeze.json'),
        outcome_sha256={p.name:sha(p) for p in sorted((OUT/'outcomes').glob('*.json'))}))
    for r in results:
        print(r['week'],r['slate'],'size',r['common_size'],'historical',round(r['historical_reference']['average_actual'],2),r['historical_reference']['best_actual'],
              {k:(round(v['average_actual'],2) if v['average_actual'] is not None else None,v['best_actual'],v['representative_ranks']) for k,v in r['arms'].items()})

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('phase',choices=['verify','freeze','evaluate'])
    globals()[parser.parse_args().phase]()
