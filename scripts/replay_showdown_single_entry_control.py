"""Reproduce the unchanged 30-candidate single-entry control offline."""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

from backend.app.product_services.cbc_solver import make_cbc_solver
from backend.app.product_services.classic_prospective import digest_payload
from backend.app.product_services.optimizer import OptimizerService, _json_safe
from backend.app.product_services.lineup_correlation_scoring import score_lineup_correlations
from backend.app.product_services.optimizer import _saturated_showdown_correlation_summary
from backend.app.product_services.showdown_single_entry import select_single_entry_lineups
from scripts.research_showdown_prelock import FrozenService, PreparationComplete, validate_lineup


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('freeze', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Control output is immutable; choose another path')
    envelope = json.loads(args.freeze.read_text())
    if digest_payload(envelope['payload']) != envelope['sha256']:
        raise ValueError('Input hash mismatch')
    frozen = envelope['payload']
    service = FrozenService(frozen)
    with args.output.with_suffix('.log').open('w') as log, redirect_stdout(log):
        try:
            service.run_job(frozen['season'], frozen['week'], frozen['slate'],
                            'showdown_single_entry_portfolio', {'num_single_entry_contests': 3},
                            contest_format='showdown', objective='gpp',
                            projection_run_id=frozen['projection_run_id'])
        except PreparationComplete:
            pass
        pool = service.prepared
        kwargs = service.solve_kwargs
        score_col = kwargs['score_col']
        forced = list(pool.sort_values(score_col, ascending=False)['player_id'].astype(str))
        teams = sorted(pool.player_team.unique())
        scripts = [{'script_id': f'single_entry_{kind}_{team}', 'kind': kind, 'team': team}
                   for kind in ('run_control', 'pass_led', 'contrarian') for team in teams]
        candidates, excluded = [], []
        for index in range(30):
            captain = forced[index-18] if 18 <= index < 24 else None
            script = scripts[index-24] if index >= 24 else None
            with patch('backend.app.product_services.optimizer.pulp.PULP_CBC_CMD',
                       side_effect=lambda **unused: make_cbc_solver('native')):
                lineup = OptimizerService._solve_lineup(service, pool, **{
                    **kwargs, 'include_control_comparison': False, 'exclude_signatures': excluded,
                    'locked_captain_player_id': captain, 'portfolio_script': script})
            if not lineup:
                if captain or script:
                    continue
                break
            validate_lineup(lineup)
            excluded.append([(str(row['player_id']), row['roster_position']) for row in lineup])
            lineup[0]['lineup_correlation_summary'] = _saturated_showdown_correlation_summary(
                lineup, score_lineup_correlations(lineup, profile=kwargs['rule_profile']))
            candidates.append(lineup)
        selected, report = select_single_entry_lineups(deepcopy(candidates), num_contests=3,
                                                     report_candidate_limit=None)
    payload = _json_safe({'input_sha256': envelope['sha256'], 'candidate_limit': 30,
                         'raw_candidates': candidates, 'selected': selected, 'report': report,
                         'solver_backend': 'native CBC; unchanged mathematical model and policy'})
    args.output.write_text(json.dumps({'payload': payload, 'sha256': digest_payload(payload)}, indent=2, sort_keys=True)+'\n')
    print({'candidates': len(candidates), 'assignment': report['selected_comparison'] if 'selected_comparison' in report else report.get('recommended_structure')})


if __name__ == '__main__':
    main()
