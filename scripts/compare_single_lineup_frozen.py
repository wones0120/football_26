#!/usr/bin/env python3
"""Offline proxy reconstruction on frozen Week 3 inputs; no outcomes or live I/O.

Canonical IDs join saved rosters to the exact source audit. Missing P10 remains
missing for every candidate. This is not a readiness replay or calibration test.
"""
from contextlib import redirect_stdout
from copy import deepcopy
from hashlib import sha256
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd
from backend.app.product_services.optimizer import OptimizerService
from backend.app.product_services.single_lineup import (
    CLASSIC_SINGLE_LINEUP_STRATEGY_ID, CAPTAIN_SINGLE_LINEUP_STRATEGY_ID,
    WEIGHTS, POLICY_ID, generate_candidates, lineup_diagnostics, select_single_lineup, signature,
)

CLASSIC = 'artifacts/classic_discovery_multi_slate/week3_archived_control_check/inputs.json'
CAPTAIN = 'artifacts/showdown-monday-2026w3-ui-recovery-f1aec338.json'


def read(path):
    raw = (ROOT / path).read_bytes()
    return json.loads(raw), {'path': path, 'sha256': sha256(raw).hexdigest()}


def row(audit):
    return {key: audit.get(key) for key in ('player_id', 'position', 'salary', 'projection', 'p90',
        'opponent_team', 'pregame_availability_probability')} | {
        'name': audit['player_name'], 'player_team': audit['team'],
        'predicted_p10': None, 'ownership': None}


def summary(lineup):
    d = lineup_diagnostics(lineup)
    return {**{k: d[k] for k in ('expected_points', 'downside_diagnostic', 'upside_diagnostic', 'selection_score',
        'availability_risk_points', 'missing_quantiles', 'cash_probability')},
        'salary': sum(r['salary'] for r in lineup),
        'roster': [{k: r.get(k) for k in ('player_id', 'name', 'position', 'roster_position', 'salary', 'projection')} for r in lineup]}


def compare(fmt):
    data, source = read(CLASSIC if fmt == 'classic' else CAPTAIN)
    audit = data['eligible_rows'] if fmt == 'classic' else data['player_pool']['rows']
    lookup = {p['player_id']: row(p) for p in audit}
    pool = [lookup[p['player_id']] for p in audit if p.get('included')]
    if fmt == 'classic':
        archived = [[{**lookup[p['player_id']], 'roster_position': p['position']} for p in c['roster']]
                    for c in data['old_candidates']]
        assert all(abs(sum(p['projection'] for p in lineup) - c['mean']) < 1e-8
                   for lineup, c in zip(archived, data['old_candidates']))
        old_strategy = data['params']['strategy_config']['strategy_id']
        cutoff = data['cutoff_at']; params = data['params']
        strategy = CLASSIC_SINGLE_LINEUP_STRATEGY_ID
        kwargs = {'contest_type': 'cash', 'stack_params': {'enabled': False},
                  'enforce_single_te': params.get('enforce_single_te', False),
                  'avoid_dst_opponents': params.get('avoid_dst_opponents', False),
                  'locked_player_ids': set(params.get('locked_player_ids') or []),
                  'flex_only_player_ids': set(params.get('flex_only_player_ids') or [])}
        for p in pool:
            p['game_id'] = ':'.join(sorted([p['player_team'], p['opponent_team']]))
    else:
        # Preserve slot-adjusted means exactly, while uniformly using audit P10
        # fallback rather than borrowing quantiles only for old selected players.
        archived = []
        known = {p['player_id']: p for lineup in data['results'] for p in lineup}
        for p in pool:
            p['showdown_qb_eligible'] = bool(known.get(p['player_id'], {}).get('showdown_qb_eligible'))
            p['is_starting_qb'] = bool(known.get(p['player_id'], {}).get('is_starting_qb'))
        for lineup in data['results']:
            rows = []
            for p in lineup:
                r = deepcopy(lookup[p['player_id']]); r['roster_position'] = p['roster_position']
                if r['roster_position'] == 'CPT':
                    for k in ('salary', 'projection', 'p90'): r[k] *= 1.5
                assert abs(r['projection'] - p['projection']) < 1e-8
                r['showdown_qb_eligible'] = p.get('showdown_qb_eligible', False)
                r['is_starting_qb'] = p.get('is_starting_qb', False)
                rows.append(r)
            archived.append(rows)
        old_strategy = data['strategy']; cutoff = data['data_cutoff_at']; strategy = CAPTAIN_SINGLE_LINEUP_STRATEGY_ID
        kwargs = {'contest_type': 'captain', 'stack_params': {'enabled': False,
            'require_starting_qb': True, 'hard_qb_correlations': True, 'saturate_correlations': True}}
    service = OptimizerService.__new__(OptimizerService)
    with redirect_stdout(io.StringIO()):
        generated = generate_candidates(pd.DataFrame(pool), service._solve_lineup, contest_format=fmt,
                                        target=120 if fmt == 'classic' else 60, base_kwargs=kwargs)
    chosen, report = select_single_lineup(generated, strategy=strategy)
    same_pool, _ = select_single_lineup(archived, strategy=strategy)
    validate = service._validate_classic_lineups if fmt == 'classic' else service._validate_showdown_lineups
    valid, reason = validate(chosen, requested_lineups=1, max_exposure=1,
        enforce_single_te=kwargs.get('enforce_single_te', False),
        **({'avoid_dst_opponents': kwargs.get('avoid_dst_opponents', False)} if fmt == 'classic' else {'portfolio_policy': True}))
    assert len(chosen) == 1 and valid, reason
    return {'format': fmt, 'source': source, 'projection_run_id': data['projection_run_id'],
        'frozen_cutoff': cutoff, 'old_strategy': old_strategy, 'old_requested_recommendations': 5,
        'archived_candidates_reconstructable': len(archived), 'new_candidates': report['candidate_count'],
        'old_first_recommendation_or_rank': summary(archived[0]),
        'new_on_archived_pool': summary(same_pool[0]), 'new_with_discovery': summary(chosen[0]),
        'new_matches_old_first': signature(chosen[0]) == signature(archived[0]), 'one_legal_lineup': valid,
        'all_new_candidates': [{k: c[k] for k in ('rank', 'expected_points', 'downside_diagnostic', 'upside_diagnostic',
            'selection_score', 'salary', 'objective_contributions')} | {'roster_ids': list(signature(c['players']))} for c in report['all_candidates']],
        'limitations': ['Frozen audit reconstruction only; historical live readiness is not certified.',
            'Every marginal P10 is absent from the saved audit and uses the documented spread fallback.',
            'Ownership support is not established at the frozen cutoff, so competition term is disabled.',
            'Captain original complete discovery universe is unavailable; its five saved recommendations are the same-pool control.',
            'No realized outcomes, payouts, cash rates, Week 4–5 outcomes, or weight tuning are used.']}


def main():
    out = ROOT / 'artifacts/single_lineup_redesign/frozen_comparison.json'
    result = {'contract_id': 'single_lineup_frozen_proxy_comparison_v1', 'policy_id': POLICY_ID,
        'objective_weights': WEIGHTS, 'policy_code_sha256': sha256((ROOT / 'backend/app/product_services/single_lineup.py').read_bytes()).hexdigest(),
        'outcomes_used': False, 'comparisons': [compare('classic'), compare('showdown')]}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + '\n')
    for c in result['comparisons']:
        print(c['format'], 'candidates', c['new_candidates'], 'legal', c['one_legal_lineup'])
        for label in ('old_first_recommendation_or_rank', 'new_on_archived_pool', 'new_with_discovery'):
            d = c[label]; print(label, {k: round(d[k], 3) for k in ('expected_points', 'downside_diagnostic', 'upside_diagnostic', 'selection_score')})
    print(out)

if __name__ == '__main__': main()
