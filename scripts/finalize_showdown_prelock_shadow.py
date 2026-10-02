"""Finalize a reliability-gated shadow without changing production policy."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from contextlib import redirect_stdout
from datetime import UTC, datetime
import json
from pathlib import Path
import time

import pandas as pd
import pulp

from backend.app.product_services.classic_prospective import digest_payload
from backend.app.product_services.cbc_solver import make_cbc_solver
from backend.app.product_services.optimizer import _json_safe, _safe_float
from backend.app.product_services.rule_library import resolve_strategy_profile
from backend.app.product_services.showdown_game_scenarios import define_game_scenarios, condition_player_pool
from backend.app.product_services.showdown_single_entry import select_single_entry_lineups
from scripts.research_showdown_prelock import (
    FrozenService, capture_model, render_solution, signature, thesis, joint_portfolio,
)


def read_frozen(path):
    value = json.loads(path.read_text())
    if digest_payload(value['payload']) != value['sha256']:
        raise ValueError(f'Hash mismatch: {path}')
    return value


def mask_diagnostic_ownership(lineup):
    for row in lineup:
        for field in ('ownership', 'captain_ownership', 'flex_ownership'):
            row['diagnostic_'+field] = row.get(field)
            row[field] = None
        row.pop('lineup_duplication_risk', None)
        row['ownership_input_status'] = 'unavailable_for_selection_weak_showdown_calibration'
        row['solver_ownership_weight'] = 0.0
    return lineup


def compact_lineup(lineup):
    omit = {'historical_role_calibration', 'role_counterfactual_grid'}
    return [{key: value for key,value in row.items() if key not in omit} for row in lineup]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    sensitivity_path = args.output.parent/'ten_thesis_sensitivity.json'
    if args.output.exists() or sensitivity_path.exists():
        raise ValueError('Shadow output is immutable; choose a new path')
    started = time.monotonic()
    raw_envelope = read_frozen(args.directory/'discovery_v1.json')
    raw = raw_envelope['payload']
    freeze_envelope = read_frozen(args.directory/'refreshed_database_freeze.json')
    frame = pd.DataFrame(raw['prepared_pool']).reset_index(drop=True)
    service = FrozenService(freeze_envelope['payload'])
    profile = resolve_strategy_profile(contest_format='showdown', objective='gpp')
    kwargs = {'contest_type': 'captain', 'score_col': 'optimizer_context_ceiling_score',
              'rule_profile': profile, 'stack_params': raw['stack'], 'include_control_comparison': False}
    with (args.directory/'conditional_model_details.log').open('w') as log, redirect_stdout(log):
        baseline = capture_model(service, frame, kwargs)
        scenarios = define_game_scenarios(frame)
        models = {scenario.winner: capture_model(service, condition_player_pool(frame,scenario), kwargs)
                  for scenario in scenarios[1:]}
    candidates = {signature(lineup): {'lineup': deepcopy(lineup),
                  'sources': list(record['discovery_sources'])}
                  for record,lineup in zip(raw['all_candidates'],raw['raw_lineups'])}
    conditional = {scenario.winner: [] for scenario in scenarios[1:]}
    attempts = []
    for scenario in scenarios[1:]:
        winner = scenario.winner
        conditioned = condition_player_pool(frame,scenario)
        for captain_index in frame.index[frame.player_team == winner]:
            for count in (3,4,5):
                for required in (['RB','DST'],['QB','WR']):
                    model = deepcopy(models[winner])
                    variables = {variable.name:variable for variable in model.variables()}
                    cap = {i:variables[f'captain_{i}'] for i in frame.index}
                    flex = {i:variables[f'flex_{i}'] for i in frame.index}
                    model += cap[captain_index] == 1
                    own = list(frame.index[frame.player_team == winner])
                    model += pulp.lpSum(cap[i]+flex[i] for i in own) == count
                    for position in required:
                        model += pulp.lpSum(cap[i]+flex[i] for i in own if frame.loc[i,'position']==position) >= 1
                    source = f'conditional_exact:{winner}:{count}:{required}:{frame.loc[captain_index,"player_id"]}'
                    begin = time.monotonic()
                    found = 0
                    for _ in range(3):
                        status = model.solve(make_cbc_solver('native'))
                        if status != pulp.LpStatusOptimal:
                            break
                        conditioned_lineup = render_solution(conditioned,model,model.objective,raw['stack'],profile)
                        key = signature(conditioned_lineup)
                        # Exact baseline re-evaluation, including every auxiliary
                        # correlation variable, so conditions never inflate baseline quality.
                        evaluation = deepcopy(baseline)
                        ev = {variable.name:variable for variable in evaluation.variables()}
                        by_id = {str(frame.loc[i,'player_id']):i for i in frame.index}
                        for player,slot in key:
                            evaluation += ev[('captain_' if slot=='CPT' else 'flex_')+str(by_id[player])] == 1
                        if evaluation.solve(make_cbc_solver('native')) != pulp.LpStatusOptimal:
                            raise AssertionError('Conditional roster violates baseline legality')
                        lineup = render_solution(frame,evaluation,evaluation.objective,raw['stack'],profile)
                        if key not in candidates:
                            candidates[key] = {'lineup':lineup,'sources':[]}
                        candidates[key]['sources'].append(source)
                        conditional[winner].append({'signature':key,'conditioned_solver':float(pulp.value(model.objective)),
                            'conditioned_mean':sum(row['projection'] for row in conditioned_lineup),
                            'conditioned_p90':sum(row['p90'] for row in conditioned_lineup),
                            'team_count':count,'required_positions':required,'captain':frame.loc[captain_index,'name'],
                            'source':source})
                        model += pulp.lpSum(cap[by_id[player]] if slot=='CPT' else flex[by_id[player]] for player,slot in key) <= 5
                        found += 1
                    attempts.append({'source':source,'found':found,'seconds':time.monotonic()-begin})
        print({'conditional_winner':winner,'attempts':len(conditional[winner]),'universe':len(candidates)},flush=True)
    lineups = [mask_diagnostic_ownership(deepcopy(value['lineup'])) for value in candidates.values()]
    _, report = select_single_entry_lineups(lineups,num_contests=1,report_candidate_limit=None)
    records = report['all_candidates']
    by_signature = {signature(lineup):lineup for lineup in lineups}
    ranked = [by_signature[tuple(tuple(pair) for pair in row['signature'])] for row in records]
    by_key = {}
    for record,lineup in zip(records,ranked):
        key = signature(lineup)
        record.update({'research_thesis':thesis(lineup),'discovery_sources':candidates[key]['sources'],
                       'salary':sum(row['salary'] for row in lineup),
                       'team_counts':dict(Counter(row['player_team'] for row in lineup))})
        by_key[key] = record
    for winner,rows in conditional.items():
        for row in rows:
            record = by_key[row['signature']]
            row.update({'baseline_rank':record['rank'],'baseline_selector':record['single_entry_score'],
                        'baseline_mean':record['mean'],'baseline_p90':record['p90']})
    best = records[0]['single_entry_score']
    primary_limits = {str(row['player_id']):1 for _,row in frame.iterrows()
                      if row['salary']<=1000 or (row.get('pregame_role_uncertain') and _safe_float(row.get('snap_share_mean_3'))<.1)}
    eligible = [i for i,row in enumerate(records) if best-row['single_entry_score']<=.10+1e-8]
    er,el = [records[i] for i in eligible],[ranked[i] for i in eligible]
    primary = joint_portfolio(er,el,3,different_captains=True,different_theses=True,max_shared=4,exposure_limits=primary_limits)
    captain_only = joint_portfolio(er,el,3,different_captains=True)
    limits = {str(row['player_id']):(10 if row['position']=='QB' else 4 if row['salary']<=1000 else 8) for _,row in frame.iterrows()}
    ten = joint_portfolio(er,el,10,captain_limit=6,exposure_limits=limits)
    supported = sorted({er[index]['research_thesis'] for index in primary})
    thesis_ten = joint_portfolio(er,el,10,captain_limit=6,exposure_limits=limits,
                                required_theses=supported)
    control = read_frozen(args.directory/'production_single_entry_control.json')['payload']
    gated_control, gated_control_report = select_single_entry_lineups(
        [mask_diagnostic_ownership(deepcopy(lineup)) for lineup in control['raw_candidates']],num_contests=3)
    result = {'frozen_at':datetime.now(UTC).isoformat(),'input_sha256':freeze_envelope['sha256'],
              'raw_discovery_sha256':raw_envelope['sha256'],'projection_run_id':raw['projection_run_id'],
              'prepared_pool':raw['prepared_pool'],'stack':raw['stack'],'weights':raw['weights'],
              'all_candidates':records,'raw_lineups':[compact_lineup(lineup) for lineup in ranked],
              'conditional_candidates':conditional,'conditional_attempts':attempts,'original_attempts':raw['attempts'],
              'scenarios':[scenario.audit() for scenario in scenarios],
              'primary_three_ranks':[er[i]['rank'] for i in primary],
              'captain_only_three_ranks':[er[i]['rank'] for i in captain_only],
              'ten_ranks':[er[i]['rank'] for i in ten],
              'thesis_ten_ranks':[er[i]['rank'] for i in thesis_ten],
              'reliability_gated_control_selected':[compact_lineup(lineup) for lineup in gated_control],
              'reliability_gated_control_report':gated_control_report,
              'research_policy':{**raw['research_policy'],'primary_fragile_limits':primary_limits,
                  'ownership_evidence':'diagnostic only; poor Showdown slot calibration and incomplete KC identity coverage',
                  'ownership_selection_eligibility':'uniformly unavailable in shadow; all selector weights unchanged',
                  'primary_thesis_definition':'allocation and actual stacks, not captain identity'},
              'runtime_seconds':raw['runtime_seconds']+time.monotonic()-started,
              'conditional_extension_seconds':time.monotonic()-started}
    body = _json_safe(result)
    args.output.write_text(json.dumps({'payload':body,'sha256':digest_payload(body)},indent=2,sort_keys=True)+'\n')
    sensitivity = {'required_supported_theses':supported,'ranks':[er[i]['rank'] for i in thesis_ten],
                   'total_selector':sum(er[i]['single_entry_score'] for i in thesis_ten),
                   'original_ten_total_selector':sum(er[i]['single_entry_score'] for i in ten),
                   'captain_allocation':dict(Counter(er[i]['captain'] for i in thesis_ten)),
                   'quality_shadow_hash':digest_payload(body)}
    sensitivity_path.write_text(json.dumps({'payload':sensitivity,'sha256':digest_payload(sensitivity)},indent=2,sort_keys=True)+'\n')
    print({'output':str(args.output),'candidates':len(records),'primary':result['primary_three_ranks'],'ten':result['ten_ranks']},flush=True)


if __name__ == '__main__':
    main()
