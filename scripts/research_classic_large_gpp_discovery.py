"""Labelled expanded discovery on the parity fixture; never invoked by production."""
from collections import Counter
from dataclasses import replace
import json
from pathlib import Path
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import pulp
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.product_services.classic_strategy_contract import validate_strategy_contract, config_from_dict, portfolio_audit, digest
from backend.app.product_services.gpp_optimizer import Player, resolve_portfolio_config, _build_lineup
from backend.app.product_services.lineup_correlation_scoring import build_lineup_correlation_terms, build_format_specific_terms
from backend.app.product_services.rule_library import resolve_strategy_profile
from backend.app.product_services.classic_primary_game import canonical_primary_game
from backend.app.product_services.classic_prospective import classify_pool, risk_exposure
from backend.app.product_services.cbc_solver import make_cbc_solver
from datetime import datetime

D = Path('artifacts/classic_large_gpp_parity/d0e2ff8f')
def save(name, data): (D / name).write_text(json.dumps(data, indent=2, allow_nan=False)+'\n')


def run():
    assert json.loads((D/'parity.json').read_text())['status']=='PASS', 'Establish parity first'
    contract = json.loads((D/'A_no_cap_contract.json').read_text()); validate_strategy_contract(contract)
    options = contract['effective']['pipeline_options']
    players = [Player(**{**row,'tags':set(row['tags'])}) for row in contract['effective']['players']]
    config = resolve_portfolio_config(players, config_from_dict(contract['effective']['resolved_config']),
        ownership_available=options['ownership_available'], long_shot_mode=False, num_lineups=5)
    profile=resolve_strategy_profile(contest_format='classic', objective='gpp')
    terms=build_lineup_correlation_terms(players, profile=profile); format_terms=build_format_specific_terms(players, profile=profile)
    lookup={p.player_id:p for p in players}; index={p.player_id:i for i,p in enumerate(players)}
    candidates={tuple(sorted(row['player_ids'])): [lookup[pid] for pid in row['player_ids']]
        for name in ['A_no_cap','B_cap4','C_cap3','D_cap2']
        for row in json.loads((D/f'{name}_audit.json').read_text())['candidate_rosters']}
    requests=[(qb.player_id, tuple(template)) for qb in players if qb.position=='QB' for template in config.stack_templates]
    def discover(request):
        qb_id, template=request; found=[]; excluded=[]; traces=[]
        for variant in range(2):
            audit={}
            chosen=_build_lineup(players, config, None, excluded,
                enforce_single_te=options['enforce_single_te'], avoid_dst_opponents=options['avoid_dst_opponents'],
                stack_rules=replace(config.stack_rules, min_pass_catchers=template[0], min_bring_backs=template[1]),
                required_player_ids={qb_id}, solver_backend='bundled',
                precomputed_correlation_terms=terms, precomputed_format_terms=format_terms, solve_audit=audit)
            traces.append(dict(qb_id=qb_id, template=list(template), variant=variant+1, **audit))
            if not chosen: break
            found.append(chosen); excluded.append(set(chosen))
        return found,traces
    started=time.monotonic(); traces=[]
    with ThreadPoolExecutor(max_workers=2) as executor:
        for n,(found,trace) in enumerate(executor.map(discover,requests),1):
            traces.extend(trace)
            for indices in found:
                roster=[players[i] for i in indices]; candidates.setdefault(tuple(sorted(p.player_id for p in roster)),roster)
            print(f'discovery {n}/{len(requests)}; {len(candidates)} unique',flush=True)
    lineups=[candidates[key] for key in sorted(candidates)]
    descriptions=portfolio_audit(contract,lineups)['candidate_rosters']
    save('expanded_candidate_pool.json',dict(label='classic_large_gpp_v1 + expanded_discovery',
        execution_mode='RESEARCH_SHADOW',
        deviations=['Broader eligible QB/minimum-template discovery with two distinct solves each',
                    'Generation defers 80% exposure to joint finite-candidate selection; same scoring and five template slots'],
        frozen_effective_sha256=contract['effective_sha256'], candidates=descriptions, traces=traces,
        elapsed_seconds=time.monotonic()-started))
    fixture=json.loads((D/'app_fixture.json').read_text()); payload=fixture['params']['strategy_runtime']['classic_run_input_snapshot']['payload']
    risks=classify_pool(payload['final_solver_rows'],datetime.fromisoformat(fixture['data_cutoff_at']))
    for name,cap in [('expanded_no_cap',None),('expanded_cap3',3)]:
        shadow=json.loads(json.dumps(contract)); shadow.pop('sha256')
        shadow.update(execution_mode='RESEARCH_SHADOW', strategy_label='classic_large_gpp_v1 + expanded_discovery',
            deviations=['Broader discovery: each eligible QB and production minimum-stack template, two unique score-optimal constructions; production sensitivity rosters included',
                'Candidate generation defers 80% player and game caps to final finite-pool selection',
                'Joint finite-candidate assignment replaces sequential selection; same five production template slots and scoring',
                *([f'max_lineups_per_primary_game={cap}'] if cap else [])])
        shadow['requested']['max_lineups_per_primary_game']=cap
        shadow['effective']['max_lineups_per_primary_game']=cap
        shadow['effective']['pipeline_options']['max_lineups_per_primary_game']=cap
        shadow['effective']['generation']='expanded frozen-eligible QB/template discovery; exact existing lineup score'
        shadow['effective']['selection']='joint finite-pool template-slot assignment'
        shadow['sources']['max_lineups_per_primary_game']='research_request' if cap else 'strategy_default_no_limit'
        shadow['effective_sha256']=digest(shadow['effective']);shadow['sha256']=digest(shadow)
        validate_strategy_contract(shadow);save(f'{name}_contract.json',shadow)
        model=pulp.LpProblem(name,pulp.LpMaximize)
        # Stable canonical candidate order and production slot order retain CBC tie behavior.
        assignments={(i,slot):pulp.LpVariable(f'candidate_{i}_slot_{slot}',cat='Binary')
            for i,row in enumerate(descriptions) for slot in range(5)
            if row['stack']['partner_count']>=config.stack_templates[slot%len(config.stack_templates)][0]
            and row['stack']['bring_back_count']>=config.stack_templates[slot%len(config.stack_templates)][1]}
        selected={i:pulp.lpSum(v for (candidate,slot),v in assignments.items() if candidate==i) for i in range(len(lineups))}
        model+=pulp.lpSum(descriptions[i]['objective_score']*v for (i,slot),v in assignments.items())
        for slot in range(5):model+=pulp.lpSum(v for (i,s),v in assignments.items() if s==slot)==1
        for expr in selected.values():model+=expr<=1
        roster_ids=[set(row['player_ids']) for row in descriptions]
        for pid in lookup:model+=pulp.lpSum(selected[i] for i,ids in enumerate(roster_ids) if pid in ids)<=4
        if cap:
            games=[canonical_primary_game(row['qb']['team'],row['qb']['opponent']) for row in descriptions]
            for game in sorted(set(games)):model+=pulp.lpSum(selected[i] for i,key in enumerate(games) if key==game)<=cap
        for i,left in enumerate(roster_ids):
            for j in range(i+1,len(roster_ids)):
                if len(left&roster_ids[j])>config.uniqueness_overlap:model+=selected[i]+selected[j]<=1
        started=time.monotonic(); model.solve(make_cbc_solver('bundled'))
        status=pulp.LpStatus[model.status]
        chosen=[next(i for (i,s),v in assignments.items() if s==slot and (v.value() or 0)>.5) for slot in range(5)] if status=='Optimal' else []
        audit=portfolio_audit(shadow,[lineups[i] for i in chosen])
        audit.update(status=status, solver_solution_status=pulp.LpSolution[model.sol_status], solver_objective=pulp.value(model.objective),
            solver_elapsed_seconds=time.monotonic()-started, candidate_count=len(lineups),
            portfolio_optimality='CBC optimum over this explicit finite candidate pool; no all-feasible-portfolio optimum claim',
            risk_exposure=risk_exposure(audit['candidate_rosters'],risks))
        source=json.loads((D/('A_no_cap_audit.json' if cap is None else 'C_cap3_audit.json')).read_text())
        source_keys={tuple(sorted(row['player_ids'])) for row in source['candidate_rosters']};keys={tuple(sorted(row['player_ids'])) for row in audit['candidate_rosters']}
        audit.update(displaced_rosters=[list(k) for k in sorted(source_keys-keys)],additional_rosters=[list(k) for k in sorted(keys-source_keys)])
        save(f'{name}_audit.json',audit)
        print(json.dumps({k:audit[k] for k in ['status','candidate_count','canonical_primary_games','selector_objective_total','projected_point_sum','summed_marginal_p90']}),flush=True)

if __name__=='__main__':run()
