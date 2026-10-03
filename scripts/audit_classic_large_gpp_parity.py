"""Offline frozen Large-GPP parity and explicitly labelled cap sensitivities.

No database reads, projection refresh, entry submission, or strategy promotion.
"""
import argparse
from collections import Counter
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import sys
import time

import pandas as pd
import pulp

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.product_services.optimizer import OptimizerService
from backend.app.product_services.classic_prospective import validate_classic_run_input, classify_pool, risk_exposure
from backend.app.product_services.classic_strategy_contract import build_strategy_contract, execute_strategy_contract, portfolio_audit, model_fingerprints, digest


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def run(directory):
    fixture = directory / 'app_fixture.json'
    manifest = json.loads((directory / 'fixture_manifest.json').read_text())
    assert sha256(fixture.read_bytes()).hexdigest() == manifest['fixture_sha256'], 'Frozen fixture changed'
    job = json.loads(fixture.read_text())
    snapshot = job['params']['strategy_runtime']['classic_run_input_snapshot']
    validate_classic_run_input(snapshot)
    payload = snapshot['payload']; parameters = payload['parameters']
    assert parameters['num_lineups'] == 5 and parameters['max_exposure'] == .8
    players = OptimizerService._gpp_players_from_pool(pd.DataFrame(payload['final_solver_rows']))
    projection_p90_match = all(player.projection == float(row["projection"]) and player.ceiling == float(row["p90"])
        for player, row in zip(players, payload["final_solver_rows"]))
    assert projection_p90_match, "Frozen projections/P90 changed during adaptation"
    options = dict(season=job['season'], week=job['week'], slate=job['slate'], num_lineups=5,
        ownership_available=all(p.ownership is not None for p in players), max_exposure=.8,
        enforce_single_te=parameters['enforce_single_te'], avoid_dst_opponents=parameters['avoid_dst_opponents'],
        large_gpp=True, minimum_uniqueness=parameters['minimum_uniqueness'],
        max_from_team=parameters['max_players_per_team'], max_from_game=parameters['max_players_per_game'],
        stack_templates=parameters.get('stack_templates'), maximum_exposure_by_player={}, minimum_exposure_by_player={},
        include_control_comparisons=True, long_shot_mode=False, candidate_aware_ownership=False,
        solver_backend='bundled', precompute_correlation_terms=False, maximum_player_groups=None)
    metadata = dict(optimizer_run_id=job['job_id'], projection_run_id=job['projection_run_id'],
        input_snapshot_sha256=snapshot['sha256'], fixture_sha256=manifest['fixture_sha256'])
    classifications = classify_pool(payload['final_solver_rows'], datetime.fromisoformat(job['data_cutoff_at']))
    audits = {}
    baseline = json.loads((directory / 'baseline_replay.json').read_text())
    for name, cap in [('A_no_cap', None), ('B_cap4', 4), ('C_cap3', 3), ('D_cap2', 2)]:
        request = {**parameters, **({'max_lineups_per_primary_game': cap} if cap is not None else {})}
        contract = build_strategy_contract(players=players, pipeline_options={**options, 'max_lineups_per_primary_game': cap},
            requested=request, metadata=metadata, mode='PARITY' if cap is None else 'RESEARCH_SHADOW',
            deviations=[] if cap is None else [f'max_lineups_per_primary_game={cap}; all other frozen inputs and constraints unchanged'])
        save(directory / f'{name}_contract.json', contract)
        print(f'{name}: starting frozen shared production pipeline', flush=True)
        started = time.monotonic(); result = execute_strategy_contract(contract)
        audit = portfolio_audit(contract, result.lineups, trace=result.selection_trace)
        audit.update(status=result.status, message=result.message, elapsed_seconds=time.monotonic()-started,
                     risk_exposure=risk_exposure(audit['candidate_rosters'], classifications))
        save(directory / f'{name}_audit.json', audit)
        audits[name] = audit
        print(json.dumps({k: audit[k] for k in ('status', 'elapsed_seconds', 'canonical_primary_games', 'selector_objective_total', 'projected_point_sum', 'summed_marginal_p90')}), flush=True)
        if cap is None:
            expected = [sorted(p['player_id'] for p in lineup) for lineup in job['results']]
            actual = [sorted(row['player_ids']) for row in audit['candidate_rosters']]
            comparisons = []
            for i, (step, saved) in enumerate(zip(result.selection_trace, job['results'])):
                replay = saved[0]['lineup_control_comparison']['replay']
                old_model = pulp.LpProblem.fromDict(replay['model'])[1]
                region = model_fingerprints(old_model)['feasible_region_sha256']
                old_model.setObjective(pulp.lpSum(c['value'] * old_model.variablesDict()[c['name']] for c in baseline['steps'][i]['objective_coefficients']))
                score = replay['scored_objective']
                comparisons.append(dict(step=i+1, roster_match=expected[i]==actual[i],
                    feasible_region_match=step['feasible_region_sha256']==region,
                    objective_coefficients_match=step['objective_sha256']==model_fingerprints(old_model)['objective_sha256'],
                    primary_objective_match=abs(step['objective_score']-score)<1e-9,
                    reported_objective_match=abs(audit['candidate_rosters'][i]['objective_score']-score)<1e-9,
                    saved_primary_score=score, replay_primary_score=step['objective_score']))
            config_match = digest(contract['effective']['resolved_config']) == digest(job['params']['strategy_runtime']['config'])
            final_ids = sorted(row['player_id'] for row in payload['final_solver_rows'])
            input_match = final_ids == contract['effective']['eligible_player_ids']
            # The legacy immutable ledger is the eligibility boundary, not a fresh database reconstruction.
            pool_rows = job['params']['strategy_runtime']['player_pool']['rows']
            included_ids = sorted(str(row['player_id']) for row in pool_rows if row.get('included') is True)
            ledger_match = included_ids == final_ids if included_ids else None
            passed = actual == expected and input_match and projection_p90_match and ledger_match and config_match and all(all(row[k] for k in ('roster_match','feasible_region_match','objective_coefficients_match','primary_objective_match','reported_objective_match')) for row in comparisons)
            mismatches = []
            if not input_match or not projection_p90_match: mismatches.append("INPUT_MISMATCH")
            if ledger_match is not True: mismatches.append("ELIGIBILITY_MISMATCH")
            if not config_match or any(not row["feasible_region_match"] for row in comparisons): mismatches.append("CONSTRAINT_MISMATCH")
            if any(not row["objective_coefficients_match"] or not row["reported_objective_match"] for row in comparisons): mismatches.append("SCORING_MISMATCH")
            if actual != expected:
                mismatches.append("SOLVER/TIE_BREAK_MISMATCH" if all(row["primary_objective_match"] for row in comparisons) else "GENERATION_MISMATCH")
            parity = dict(status='PASS' if passed else 'FAIL', input_match=input_match, projection_p90_match=projection_p90_match, eligibility_ledger_match=ledger_match,
                config_match=config_match, exact_five_rosters=actual==expected, comparisons=comparisons,
                saved_candidate_manifest=job['params']['strategy_runtime']['candidate_pool_manifest'],
                boundary='Frozen ordered final solver frame and immutable upstream eligibility ledger; no current data loaded',
                mismatch_classifications=mismatches,
                reconciled_report_only_differences=['Legacy rule-profile metadata weights differ from actual resolved GPP solver config; effective contract renders executed config',
                    'Legacy stack-policy description says include RB; actual production catcher constraint is WR/TE',
                    'Raw model JSON int/float spelling and term order differ; numerical coefficients/bounds and objective fingerprints match'])
            save(directory / 'parity.json', parity)
            print(json.dumps(parity, indent=2), flush=True)
            if not passed:
                raise RuntimeError('Parity failed; do not proceed with sensitivity or expanded research')
    baseline_keys = {tuple(sorted(row['player_ids'])) for row in audits['A_no_cap']['candidate_rosters']}
    for name, audit in audits.items():
        keys = {tuple(sorted(row['player_ids'])) for row in audit['candidate_rosters']}
        audit['displaced_rosters'] = [list(key) for key in sorted(baseline_keys-keys)]
        audit['additional_rosters'] = [list(key) for key in sorted(keys-baseline_keys)]
        save(directory / f'{name}_audit.json', audit)
    save(directory / 'sensitivity_summary.json', audits)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, default=Path('artifacts/classic_large_gpp_parity/d0e2ff8f'))
    args = parser.parse_args()
    run(args.directory)
