#!/usr/bin/env python3
"""Offline supplement to the immutable Week 4 v3 shadow; never writes production."""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path

from backend.app.product_services.cbc_solver import resolve_cbc_backend
from backend.app.product_services.classic_prospective import digest_payload, validate_solver_snapshot
from backend.app.product_services.classic_small_field import describe_candidate
from backend.app.product_services.classic_thesis_shadow import forced_candidate_swap_feasible
from backend.app.product_services.gpp_optimizer import (
    LineupTagCaps, ObjectiveWeights, Player, PortfolioTargets, SlateConfig,
    StackRules, TagThresholds, _build_lineup,
)
from backend.app.product_services.lineup_correlation_scoring import (
    build_format_specific_terms, build_lineup_correlation_terms,
)
from backend.app.product_services.rule_library import resolve_strategy_profile


def allocation_delta(base: dict, alternative: dict, players: dict[str, Player]) -> dict:
    """Positive gains mean the Brissett roster gains over the alternative."""
    base_qb = players[base['qb']['player_id']]
    alt_qb = players[alternative['qb']['player_id']]
    result = {
        'qb_salary_saved': alt_qb.salary - base_qb.salary,
        'qb_mean_sacrificed': alt_qb.projection - base_qb.projection,
        'qb_p90_sacrificed': alt_qb.ceiling - base_qb.ceiling,
        'qb_ownership_difference_alt_minus_base': (
            alt_qb.ownership - base_qb.ownership
            if alt_qb.ownership is not None and base_qb.ownership is not None else None),
        'non_qb_salary_gain': (base['salary'] - base_qb.salary)
                              - (alternative['salary'] - alt_qb.salary),
        'non_qb_mean_gain': (base['mean'] - base_qb.projection)
                            - (alternative['mean'] - alt_qb.projection),
        'non_qb_p90_gain': (base['p90'] - base_qb.ceiling)
                           - (alternative['p90'] - alt_qb.ceiling),
        'net_mean_gain': base['mean'] - alternative['mean'],
        'net_p90_gain': base['p90'] - alternative['p90'],
        'net_selector_gain': base['objective_score'] - alternative['objective_score'],
        'positions': {},
    }
    for position in ('RB', 'WR', 'TE', 'DST'):
        b = [players[pid] for pid in base['player_ids'] if players[pid].position == position]
        a = [players[pid] for pid in alternative['player_ids'] if players[pid].position == position]
        result['positions'][position] = {
            'base_players': [p.player_id for p in b], 'alternative_players': [p.player_id for p in a],
            'base_only': [p.player_id for p in b if p.player_id not in alternative['player_ids']],
            'alternative_only': [p.player_id for p in a if p.player_id not in base['player_ids']],
            'salary_gain': sum(p.salary for p in b) - sum(p.salary for p in a),
            'mean_gain': sum(p.projection for p in b) - sum(p.projection for p in a),
            'p90_gain': sum(p.ceiling for p in b) - sum(p.ceiling for p in a),
        }
    return result


def complete(inputs: dict, shadow: dict) -> dict:
    report = inputs['report']
    snapshot = report['frozen_solver_snapshot']
    validate_solver_snapshot(snapshot)
    assert digest_payload({k: v for k, v in shadow.items() if k != 'sha256'}) == shadow['sha256']
    assert digest_payload({'candidates': report['all_candidates']}) == shadow['source']['candidate_universe_sha256']
    payload = snapshot['payload']
    code_hashes = payload['metadata']['code_sha256']
    for name, expected in code_hashes.items():
        if sha256((Path('backend/app/product_services') / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Frozen scoring/solver code changed: {name}')
    freeze_time = datetime.now(UTC)
    if freeze_time >= datetime.fromisoformat(shadow['source']['first_kickoff_at']):
        raise ValueError('Refusing prospective supplement at or after kickoff')
    config_data = payload['resolved_config']
    config = SlateConfig(**{**config_data,
        'stack_rules': StackRules(**config_data['stack_rules']),
        'tag_thresholds': TagThresholds(**config_data['tag_thresholds']),
        'objective_weights': ObjectiveWeights(**config_data['objective_weights']),
        'tag_caps': LineupTagCaps(**config_data['tag_caps']),
        'portfolio_targets': PortfolioTargets(**config_data['portfolio_targets']),
        'stack_templates': [tuple(t) for t in config_data['stack_templates']],
    })
    players = [Player(**{**p, 'tags': set(p['tags'])}) for p in payload['players']]
    by_id = {p.player_id: p for p in players}
    source = {p['player_id']: p for p in payload['pool_rows']}
    risk = {r['player_id']: r for r in report['prospective_experiment']['availability_risk']['players']}
    eligible = [p for p in players if risk.get(p.player_id, {}).get('bucket') not in {'out', 'doubtful'}]
    elevated = {pid for pid, r in risk.items() if r['bucket'] == 'questionable_elevated'}
    profile = resolve_strategy_profile(contest_format='classic', objective='gpp')
    correlation = build_lineup_correlation_terms(eligible, profile=profile)
    format_terms = build_format_specific_terms(eligible, profile=profile)
    game_totals = sorted({p.game_total for p in players if p.game_total is not None})
    candidates = report['all_candidates']
    frontier = max(r['objective_score'] for r in candidates)
    options = payload['options']
    locked = set(options.get('locked_player_ids') or [])

    def describe(ids: list[str]) -> dict:
        row = describe_candidate([by_id[pid] for pid in ids], all_players=players,
            config=config, pool_by_id=source, ownership_available=False,
            game_totals=game_totals, candidate_aware_ownership=True)
        row['equivalent_global_rank'] = 1 + sum(c['objective_score'] > row['objective_score'] + 1e-9 for c in candidates)
        row['frontier_loss'] = frontier - row['objective_score']
        row['roster_sha256'] = digest_payload({'player_ids': sorted(ids)})
        return row

    # Check every saved candidate against the exact frozen scoring implementation.
    for c in candidates:
        replay = describe(c['player_ids'])
        if abs(replay['objective_score'] - c['objective_score']) > 1e-9:
            raise ValueError(f"Candidate {c['rank']} scoring replay mismatch")

    base = max((c for c in candidates if by_id[c['qb']['player_id']].name == 'Jacoby Brissett'),
               key=lambda c: c['objective_score'])
    base_ids = set(base['player_ids']) - {base['qb']['player_id']}
    rb_ids = {p.player_id for p in eligible if p.position == 'RB'}
    qbs = [p for p in eligible if p.position == 'QB' and p.player_id in set(options['starting_qb_ids'])]
    highest = max(qbs, key=lambda p: p.projection)
    names = {'Jacoby Brissett', 'Trevor Lawrence', 'Joe Burrow', 'Patrick Mahomes', 'Josh Allen', highest.name}

    def solve(required: set[str], *, comparable: bool, template: tuple[int, int] | None = None) -> dict | None:
        minimum_groups = []
        maximum_groups = [(elevated, int(report['production_controls']['policy']['max_elevated_per_lineup']))]
        kwargs = {}
        if comparable:
            # Preserve the original RB flex, WR+TE double stack, no bring-back,
            # and at least half of its eight non-QB players, while reoptimizing.
            qb = by_id[next(pid for pid in required if by_id[pid].position == 'QB')]
            own_te = {p.player_id for p in eligible if p.team == qb.team and p.position == 'TE'}
            minimum_groups = [(base_ids, 4), (rb_ids, 3), (own_te, 1)]
            maximum_groups += [(rb_ids, 3)]
            template = (2, 0)
        if template is not None:
            partners, bb = template
            kwargs = {'stack_rules': replace(config.stack_rules, min_pass_catchers=partners,
                        min_bring_backs=bb), 'exact_pass_catchers': partners, 'exact_bring_backs': bb}
        indexes = _build_lineup(eligible, config, None, [],
            enforce_single_te=bool(options['enforce_single_te']),
            avoid_dst_opponents=bool(options['avoid_dst_opponents']),
            required_player_ids=required | locked, minimum_player_groups=minimum_groups,
            maximum_player_groups=maximum_groups, precomputed_correlation_terms=correlation,
            precomputed_format_terms=format_terms, solver_backend=resolve_cbc_backend('auto'), **kwargs)
        if indexes is None:
            return None
        ids = [eligible[i].player_id for i in indexes]
        if not required <= set(ids):
            raise ValueError('Required canonical player missing')
        return describe(ids)

    controls = []
    for qb in sorted((p for p in qbs if p.name in names), key=lambda p: -p.projection):
        saved = max((c for c in candidates if c['qb']['player_id'] == qb.player_id),
                    key=lambda c: c['objective_score'], default=None)
        comparable = solve({qb.player_id}, comparable=True)
        # Sensitivity: let stack and flex follow the saved hard minimum rules.
        relaxed = solve({qb.player_id}, comparable=False)
        controls.append({'qb_id': qb.player_id, 'qb': qb.name,
            'is_highest_projected_viable_qb': qb.player_id == highest.player_id,
            'saved_best': saved, 'comparable': comparable, 'relaxed': relaxed,
            'saved_allocation_delta': allocation_delta(base, saved, by_id) if saved else None,
            'comparable_allocation_delta': allocation_delta(base, comparable, by_id) if comparable else None,
            'relaxed_allocation_delta': allocation_delta(base, relaxed, by_id) if relaxed else None})
        print(f"QB control {qb.name}: comparable={comparable['objective_score'] if comparable else None}, "
              f"relaxed={relaxed['objective_score'] if relaxed else None}", flush=True)

    diagnostics = []
    forced_names = {'Jaxon Smith-Njigba', 'Justin Jefferson', 'Lamar Jackson', 'Bucky Irving', 'Brock Bowers'}
    caps = report['production_controls']['candidate_caps']
    for player in sorted((p for p in eligible if p.name in forced_names), key=lambda p: p.name):
        # Optimize each saved stack template, including ones the initial
        # unrestricted solve would not choose; never claim best from one probe.
        probes = [solve({player.player_id}, comparable=False)]
        probes += [solve({player.player_id}, comparable=False, template=t) for t in config.stack_templates]
        valid = [r for r in probes if r]
        best = max(valid, key=lambda r: r['objective_score'], default=None)
        feasible = bool(best and forced_candidate_swap_feasible(set(best['player_ids']), candidates, caps))
        cause = ('no viable legal lineup' if best is None else 'quality floor' if best['frontier_loss'] > .20 + 1e-9
                 else 'exposure/risk rule' if not feasible else 'candidate search omission')
        diagnostics.append({'player_id': player.player_id, 'player': player.name,
            'candidate_count': sum(player.player_id in c['player_ids'] for c in candidates),
            'cause': cause, 'single_swap_cap_feasible': feasible, 'best': best,
            'template_probes': probes, 'allocation_delta_vs_frontier': allocation_delta(candidates[0], best, by_id) if best else None})
        print(f"Forced {player.name}: {cause}, selector={best['objective_score'] if best else None}", flush=True)
    assert {r['player'] for r in diagnostics} == forced_names
    body = {'contract': 'week4_thesis_completion_v1', 'frozen_at': datetime.now(UTC).isoformat(),
        'source_shadow_sha256': shadow['sha256'], 'source': shadow['source'],
        'input_sha256': digest_payload(inputs), 'code_sha256': code_hashes,
        'analysis_script_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
        'method': {'comparable': 'QB+WR+TE; no bring-back; RB flex; >=4 original non-QBs; saved salary/team/game/DST/risk rules',
                   'relaxed': 'saved hard stack minimums, free flex/stack size; single required QB',
                   'diagnostics': 'maximum frozen selector over saved hard stack rules and all saved exact stack templates'},
        'players': payload['players'], 'base_rank': base['rank'], 'base': base,
        'qb_controls': controls, 'forced_diagnostics': diagnostics}
    if datetime.fromisoformat(body['frozen_at']) >= datetime.fromisoformat(shadow['source']['first_kickoff_at']):
        raise ValueError('Analysis finished at or after kickoff')
    return {**body, 'sha256': digest_payload(body)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--shadow', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Refusing to overwrite a frozen analysis supplement; choose a new output')
    result = complete(json.loads(args.inputs.read_text()), json.loads(args.shadow.read_text()))
    with args.output.open('x') as handle:
        handle.write(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + '\n')
    print(f"Frozen supplement {result['sha256']}")


if __name__ == '__main__':
    main()
