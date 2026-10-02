"""Offline broad Showdown discovery from a hashed pre-lock freeze.

Production preparation, objective and selector are imported unchanged. The
research-only joint portfolio adds the user's captain/thesis/core constraints.
No database writes, exports, submissions or actual outcomes are supported.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import UTC, datetime
from itertools import combinations
import json
from pathlib import Path
import time
from unittest.mock import patch

import pandas as pd
import pulp
from sqlalchemy import create_engine

from backend.app.product_services.cbc_solver import make_cbc_solver
from backend.app.product_services.classic_prospective import digest_payload
from backend.app.product_services.lineup_correlation_scoring import score_lineup_correlations
from backend.app.product_services.optimizer import (
    OptimizerService, _json_safe, _safe_float, _is_high_rushing_qb,
    _saturated_showdown_correlation_summary, _showdown_qb_correlation_multipliers,
)
from backend.app.product_services.rule_library import resolve_strategy_profile
from backend.app.product_services.showdown_game_scenarios import define_game_scenarios, condition_player_pool
from backend.app.product_services.showdown_single_entry import select_single_entry_lineups, DEFAULT_WEIGHTS


TOLERANCES = (.05, .10, .15, .20, .30)


def signature(lineup):
    return tuple(sorted((str(row['player_id']), row['roster_position']) for row in lineup))


def validate_lineup(lineup):
    if len(lineup) != 6 or len({str(row['player_id']) for row in lineup}) != 6:
        raise ValueError('A lineup must have six distinct canonical identities')
    if Counter(row['roster_position'] for row in lineup) != {'CPT': 1, 'FLEX': 5}:
        raise ValueError('Invalid Showdown slots')
    if sum(float(row['salary']) for row in lineup) > 50000 + 1e-7:
        raise ValueError('Salary cap exceeded')
    teams = Counter(row['player_team'] for row in lineup)
    if len(teams) != 2 or max(teams.values()) > 5:
        raise ValueError('Both teams must be represented')
    if any(_safe_float(row.get('pregame_availability_probability')) <= 0 for row in lineup):
        raise ValueError('Unavailable player selected')


class PreparationComplete(BaseException):
    pass


class FrozenService(OptimizerService):
    def __init__(self, frozen):
        super().__init__()
        self.engine = create_engine('sqlite://')
        self.frozen = frozen

    def _load_player_pool(self, *args, **kwargs):
        frame = pd.DataFrame(deepcopy(self.frozen['player_pool']))
        frame.attrs.update(deepcopy(self.frozen.get('pool_attrs', {})))
        return frame

    def _resolve_run_lineage(self, **kwargs):
        cutoff = datetime.fromisoformat(self.frozen['projection_header'][0]['data_cutoff_at'])
        return self.frozen['projection_run_id'], None, cutoff

    def _persist_optimizer_run(self, job):
        raise AssertionError('Offline research must never persist optimizer runs')

    def _solve_lineup(self, pool, **kwargs):
        self.prepared = pool.copy().reset_index(drop=True)
        self.solve_kwargs = kwargs
        raise PreparationComplete()


class CaptureModel(pulp.LpSolver):
    def actualSolve(self, problem, **kwargs):
        self.problem = problem
        return pulp.LpStatusNotSolved


def capture_model(service, frame, kwargs):
    capture = CaptureModel()
    with patch('backend.app.product_services.optimizer.pulp.PULP_CBC_CMD', return_value=capture):
        OptimizerService._solve_lineup(service, frame, **{**kwargs, 'include_control_comparison': False})
    return capture.problem


def render_solution(frame, model, baseline_objective, stack, profile):
    variables = {variable.name: variable for variable in model.variables()}
    multipliers = _showdown_qb_correlation_multipliers(frame)
    lineup = []
    for index, source in frame.iterrows():
        captain = variables[f'captain_{index}'].value() > .5
        flex = variables[f'flex_{index}'].value() > .5
        if not (captain or flex):
            continue
        row = deepcopy(source.to_dict())
        factor = 1.5 if captain else 1.0
        row.update({'base_salary': float(row['salary']), 'base_projection': float(row['projection']),
                    'base_p90': float(row['p90']), 'is_captain': captain,
                    'roster_position': 'CPT' if captain else 'FLEX',
                    'qb_correlation_multiplier': multipliers.get(str(row['player_id']), 1.0)})
        for field in ('salary', 'projection', 'p90'):
            row[field] = float(row[field]) * factor
        if captain:
            row['dk_player_id'] = row.get('dk_captain_id')
        own = row.get('captain_ownership' if captain else 'flex_ownership')
        row['ownership'] = float(own) if pd.notna(own) else None
        row['ownership_input_status'] = 'available' if row['ownership'] is not None else 'unavailable'
        row['objective_score'] = factor * float(row['optimizer_context_ceiling_score']) * (
            (_safe_float(row.get('captain_objective_multiplier')) or 1) if captain else 1)
        lineup.append(row)
    lineup[0]['solver_objective_value'] = float(pulp.value(baseline_objective))
    lineup[0]['solver_ownership_weight'] = stack['ownership_weight'] if stack['use_role_ownership'] else 0.0
    lineup[0]['lineup_correlation_summary'] = _saturated_showdown_correlation_summary(
        lineup, score_lineup_correlations(lineup, profile=profile))
    validate_lineup(lineup)
    return lineup


def thesis(lineup):
    captain = next(row for row in lineup if row['roster_position'] == 'CPT')
    team = captain['player_team']
    same = [row for row in lineup if row['player_team'] == team]
    if captain['position'] == 'RB' and len(same) >= 4:
        return f'{team} rushing-led concentration'
    if captain['position'] == 'RB' and any(row['position'] == 'DST' for row in same):
        return f'{team} rushing/control'
    if captain['position'] in {'K', 'DST'} and sum(row['position'] in {'K', 'DST'} for row in lineup) >= 2:
        return 'defensive/kicking'
    counts = Counter(row['player_team'] for row in lineup)
    for dominant in sorted(counts, key=lambda value: (-counts[value], value)):
        rows = [row for row in lineup if row['player_team'] == dominant]
        if (counts[dominant] >= 4 and any(row['position'] == 'QB' for row in rows)
                and sum(row['position'] in {'WR','TE'} for row in rows) >= 2):
            return f'{dominant} passing concentration'
    return 'balanced competitive'


def joint_portfolio(records, lineups, requested, *, different_captains=False, different_theses=False,
                    max_shared=None, captain_limit=None, exposure_limits=None, required_theses=None):
    model = pulp.LpProblem('ProspectiveJointShowdown', pulp.LpMaximize)
    choices = [pulp.LpVariable(f'entry_{index}', cat='Binary') for index in range(len(records))]
    # Entry count dominates total selector. No lineup/player score is changed.
    span = sum(abs(row['single_entry_score']) for row in records) + 1
    model += span * pulp.lpSum(choices) + pulp.lpSum(
        choices[index] * row['single_entry_score'] for index, row in enumerate(records))
    model += pulp.lpSum(choices) <= requested
    if different_captains or captain_limit is not None:
        for captain in {row['captain_id'] for row in records}:
            model += pulp.lpSum(choices[i] for i, row in enumerate(records) if row['captain_id'] == captain) <= (
                1 if different_captains else captain_limit)
    if different_theses:
        for story in {row['research_thesis'] for row in records}:
            model += pulp.lpSum(choices[i] for i, row in enumerate(records) if row['research_thesis'] == story) <= 1
    for story in required_theses or []:
        model += pulp.lpSum(choices[i] for i,row in enumerate(records) if row['research_thesis']==story) >= 1
    ids = [set(str(row['player_id']) for row in lineup) for lineup in lineups]
    if max_shared is not None:
        for left, right in combinations(range(len(records)), 2):
            if len(ids[left] & ids[right]) > max_shared:
                model += choices[left] + choices[right] <= 1
    for player, limit in (exposure_limits or {}).items():
        model += pulp.lpSum(choices[i] for i in range(len(records)) if player in ids[i]) <= limit
    status = model.solve(make_cbc_solver('native'))
    if status != pulp.LpStatusOptimal:
        raise RuntimeError(f'Joint portfolio failed: {pulp.LpStatus[status]}')
    return [index for index, choice in enumerate(choices) if choice.value() > .5]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('freeze', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--captain-depth', type=int, default=20)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Research output is immutable; choose a new path')
    envelope = json.loads(args.freeze.read_text())
    if digest_payload(envelope['payload']) != envelope['sha256']:
        raise ValueError('Input freeze hash mismatch')
    frozen = envelope['payload']
    started = time.monotonic()
    service = FrozenService(frozen)
    with (args.output.parent / 'solver_detail.log').open('w') as log, redirect_stdout(log):
        try:
            service.run_job(frozen['season'], frozen['week'], frozen['slate'],
                            'showdown_single_entry_portfolio', {'num_single_entry_contests': 3},
                            contest_format='showdown', objective='gpp',
                            projection_run_id=frozen['projection_run_id'])
        except PreparationComplete:
            pass
        frame = service.prepared
        kwargs = service.solve_kwargs
        profile = kwargs['rule_profile']
        stack = kwargs['stack_params']
        base = capture_model(service, frame, kwargs)
    (args.output.parent / 'prepared_pool.json').write_text(json.dumps(_json_safe({
        'player_pool': frame.to_dict('records'), 'stack': stack,
        'score_column': kwargs['score_col'], 'weights': DEFAULT_WEIGHTS,
        'input_sha256': envelope['sha256']}), indent=2, sort_keys=True)+'\n')
    base.writeLP(str(args.output.parent / 'baseline_model.lp'))
    candidates = {}
    attempts = []
    sources = Counter()
    pool_ids = list(frame['player_id'].astype(str))
    index_by_id = {player: index for index, player in enumerate(pool_ids)}
    scenarios = define_game_scenarios(frame)
    def discover(source, count, *, objective='ceiling', captain=None, player=None,
                 team=None, team_count=None, qb_mode=None, required=None, scenario=None):
        model = deepcopy(base)
        variables = {variable.name: variable for variable in model.variables()}
        cap = {i: variables[f'captain_{i}'] for i in frame.index}
        flex = {i: variables[f'flex_{i}'] for i in frame.index}
        selected = {i: cap[i] + flex[i] for i in frame.index}
        baseline_objective = model.objective.copy()
        if objective == 'mean':
            model.setObjective(pulp.lpSum(float(frame.loc[i, 'projection']) * (1.5*cap[i]+flex[i]) for i in frame.index))
        if scenario is not None:
            conditioned = condition_player_pool(frame, scenario)
            # Only the existing conditioning changes discovery objective; all
            # retained lineups are scored again on the frozen baseline below.
            model.setObjective(baseline_objective + pulp.lpSum(
                (float(conditioned.loc[i, 'optimizer_context_ceiling_score']) - float(frame.loc[i, 'optimizer_context_ceiling_score']))
                * (1.5*float(frame.loc[i,'captain_objective_multiplier'])*cap[i]+flex[i]) for i in frame.index))
        if captain is not None:
            model += cap[index_by_id[captain]] == 1
        if player is not None:
            model += flex[index_by_id[player]] == 1
        if team is not None:
            team_indexes = [i for i in frame.index if frame.loc[i,'player_team'] == team]
            if team_count is not None:
                model += pulp.lpSum(selected[i] for i in team_indexes) == team_count
            for position in required or []:
                model += pulp.lpSum(selected[i] for i in team_indexes if frame.loc[i,'position'] == position) >= 1
        if qb_mode is not None:
            for i in frame.index:
                if frame.loc[i,'position'] == 'QB':
                    model += selected[i] == int(frame.loc[i,'player_team'] in qb_mode)
        begin = time.monotonic()
        found = 0
        for _ in range(count):
            status = model.solve(make_cbc_solver('native'))
            if status != pulp.LpStatusOptimal:
                break
            lineup = render_solution(frame, model, baseline_objective, stack, profile)
            key = signature(lineup)
            if key not in candidates:
                candidates[key] = {'lineup': lineup, 'sources': [], 'first_source': source}
                sources[source] += 1
            candidates[key]['sources'].append(source)
            selected_vars = [cap[index_by_id[pid]] if slot == 'CPT' else flex[index_by_id[pid]] for pid, slot in key]
            model += pulp.lpSum(selected_vars) <= 5
            found += 1
        attempts.append({'source': source, 'requested': count, 'found': found,
                         'incremental_unique': sources[source], 'seconds': time.monotonic()-begin})
        print({'source': source, 'found': found, 'universe': len(candidates), 'seconds': round(time.monotonic()-begin,2)}, flush=True)
    discover('global_ceiling', 40)
    discover('global_mean', 25, objective='mean')
    for player in pool_ids:
        discover('captain_ceiling:'+player, args.captain_depth, captain=player)
        discover('captain_mean:'+player, 5, captain=player, objective='mean')
        discover('forced_flex:'+player, 3, player=player)
    for team in sorted(frame['player_team'].unique()):
        for count in (3,4,5):
            discover(f'construction:{team}:{count}', 10, team=team, team_count=count)
        for required in (['RB','DST'], ['QB','WR'], ['K','DST']):
            discover(f'structure:{team}:{required}', 10, team=team, required=required)
    teams = sorted(frame['player_team'].unique())
    for mode in ({teams[0]}, {teams[1]}, set(teams)):
        discover('qb_construction:'+','.join(sorted(mode)), 15, qb_mode=mode)
    for scenario in scenarios[1:]:
        winner = scenario.winner
        for count in (3,4,5):
            for required in (['RB','DST'], ['QB','WR']):
                for player in frame.loc[frame.player_team == winner, 'player_id'].astype(str):
                    discover(f'scenario:{winner}:{count}:{required}:{player}', 2,
                             captain=player, team=winner, team_count=count,
                             required=required, scenario=scenario)
    lineups = [entry['lineup'] for entry in candidates.values()]
    # Ranking once over the identical broad baseline universe preserves the
    # production selector's universe-dependent normalizers.
    _, selection = select_single_entry_lineups(deepcopy(lineups), num_contests=1, report_candidate_limit=None)
    by_signature = {signature(lineup): lineup for lineup in lineups}
    records = selection['all_candidates']
    ranked_lineups = [by_signature[tuple(tuple(pair) for pair in row['signature'])] for row in records]
    for record, lineup in zip(records, ranked_lineups):
        record['research_thesis'] = thesis(lineup)
        record['discovery_sources'] = candidates[signature(lineup)]['sources']
        record['salary'] = sum(row['salary'] for row in lineup)
        record['team_counts'] = dict(Counter(row['player_team'] for row in lineup))
    best = records[0]['single_entry_score']
    eligible = [i for i,row in enumerate(records) if best-row['single_entry_score'] <= .10+1e-8]
    er = [records[i] for i in eligible]
    el = [ranked_lineups[i] for i in eligible]
    primary_limits = {str(row['player_id']): 1 for _, row in frame.iterrows()
                      if row['salary'] <= 1000 or (row.get('pregame_role_uncertain')
                          and _safe_float(row.get('snap_share_mean_3')) < .10)}
    three = joint_portfolio(er, el, 3, different_captains=True, different_theses=True,
                            max_shared=4, exposure_limits=primary_limits)
    three_captain_only = joint_portfolio(er, el, 3, different_captains=True)
    limits = {str(row['player_id']): (10 if row['position']=='QB' else 4 if row['salary']<=1000 else 8)
              for _,row in frame.iterrows()}
    ten = joint_portfolio(er, el, 10, captain_limit=6, exposure_limits=limits)
    # Current unchanged heuristic can repeat its strongest roster across SEs.
    current, current_selection = select_single_entry_lineups(deepcopy(lineups), num_contests=3)
    result = {'frozen_at': datetime.now(UTC).isoformat(), 'input_sha256': envelope['sha256'],
              'projection_run_id': frozen['projection_run_id'], 'prepared_pool': frame.to_dict('records'),
              'stack': stack, 'weights': DEFAULT_WEIGHTS, 'scenarios': [scenario.audit() for scenario in scenarios],
              'attempts': attempts, 'all_candidates': records, 'raw_lineups': ranked_lineups,
              'primary_three_ranks': [er[i]['rank'] for i in three],
              'captain_only_three_ranks': [er[i]['rank'] for i in three_captain_only],
              'ten_ranks': [er[i]['rank'] for i in ten],
              'current_heuristic_three': current, 'current_heuristic_report': current_selection,
              'research_policy': {'selector_tolerance': .10, 'primary_distinct_captains': True,
                 'primary_distinct_theses': True, 'primary_max_shared_players': 4,
                 'ten_captain_limit': 6, 'ten_player_limits': limits, 'primary_fragile_limits': primary_limits,
                 'no_projection_or_selector_parameter_changes': True},
              'runtime_seconds': time.monotonic()-started}
    body = _json_safe(result)
    args.output.write_text(json.dumps({'payload': body, 'sha256': digest_payload(body)}, indent=2, sort_keys=True)+'\n')
    print({'output': str(args.output), 'candidates': len(records), 'primary_three': result['primary_three_ranks'], 'ten': result['ten_ranks'], 'runtime': result['runtime_seconds']})


if __name__ == '__main__':
    main()
