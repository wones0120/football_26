"""Frozen Week 4 contest decision; offline, no defaults or entry writes.

Solve writes only to a new directory. Verify reads saved reviewed outputs.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, replace
from datetime import UTC, datetime
from hashlib import sha256
from itertools import combinations
import json
from pathlib import Path
from backend.app.product_services.classic_candidate_completeness import (
    DiscoveryRequest, capture_model, compact_candidate, load_context, solve_request,
)
from backend.app.product_services.classic_prospective import digest_payload
from backend.app.product_services.classic_small_field import _position_ranks, describe_candidate
from backend.app.product_services.draftkings_export import DraftKingsExportService
from backend.app.product_services.optimizer import OptimizerService
from scripts.reconcile_classic_discovery_selection import selected_caps, solve, summary, violations


TARGETS = ('Parker Washington', 'Javonte Williams', 'Michael Wilson', 'Jakobi Meyers',
           'Brenton Strange', 'Mike Gesicki', 'Ryan Flournoy')


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)


def slots(row, ctx, salaries):
    players = {p.player_id: p for p in ctx['players']}
    lineup = []
    for pid in row['player_ids']:
        p = players[pid]
        lineup.append(dict(player_id=pid, name=p.name, position=p.position,
                           roster_position=p.position, salary=p.salary,
                           dk_player_id=str(salaries[pid]['source_player_key']),
                           player_team=p.team, opponent_team=p.opponent,
                           projection=p.projection, p90=p.ceiling))
    ordered = DraftKingsExportService._assign_players('classic',
        [{**p, 'player_json': p} for p in lineup])
    by_native = {p['dk_player_id']: p for p in lineup}
    return [dict(by_native[pid], slot=slot) for slot, pid in
            zip(('QB', 'RB', 'RB', 'WR', 'WR', 'WR', 'TE', 'FLEX', 'DST'), ordered)]


def enrich(result, ctx, salaries, frontier):
    for i, row in enumerate(result['lineups'], 1):
        row.setdefault('rank', i)
    result = summary(result, ctx['source'], ctx['risk'])
    rows = result['lineups']
    names = {p.player_id: p.name for p in ctx['players']}
    game_by_id = {p.player_id: '|'.join(sorted((p.team, p.opponent))) for p in ctx['players']}
    overlaps = [len(set(a['player_ids']) & set(b['player_ids'])) for a, b in combinations(rows, 2)]
    result['average_overlap'] = sum(overlaps) / len(overlaps) if overlaps else 0
    result['any_player_game_entries'] = dict(Counter(g for r in rows for g in
        {game_by_id[pid] for pid in r['player_ids']}))
    result['game_player_appearances'] = dict(Counter(game_by_id[pid] for r in rows for pid in r['player_ids']))
    result['component_sums'] = dict(Counter({k: sum(r['components'][k] for r in rows)
        for k in rows[0]['components']})) if rows else {}
    for r in rows:
        r['selector_gap_vs_frozen_frontier'] = frontier - r['objective_score']
        r['slots'] = slots(r, ctx, salaries)
    triples = Counter(tuple(sorted(ids)) for r in rows for ids in combinations(r['player_ids'], 3))
    result['shared_triples_at_least_three'] = [dict(ids=list(ids), names=[names[p] for p in ids], entries=n)
        for ids, n in sorted(triples.items(), key=lambda v: (-v[1], v[0])) if n >= 3]
    skill_ids = {p.player_id for p in ctx['players'] if p.position in {'RB', 'WR', 'TE'}}
    uncertain = {pid for pid, s in ctx['source'].items() if pid in skill_ids and (
        s.get('pregame_role_uncertain') is True
        or s.get('pregame_role_label') in (None, '', 'BACKUP'))}
    result['elevated_risk_entries'] = sum(bool(set(r['player_ids']) & ctx['elevated']) for r in rows)
    result['uncertain_role_definition'] = 'Skill players: explicit uncertain OR BACKUP OR missing current role label; missing is not a bad-play verdict'
    result['uncertain_role_entries'] = sum(bool(set(r['player_ids']) & uncertain) for r in rows)
    result['uncertain_role_exposures'] = {pid: result['player_exposures'][pid] for pid in uncertain if pid in result['player_exposures']}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frozen', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    old, out = args.frozen, args.output
    inputs = read(old / 'preview_inputs.json'); bundle = read(old / 'comparison.json')
    assert digest_payload({k: v for k, v in bundle.items() if k != 'sha256'}) == bundle['sha256']
    ctx = load_context(inputs)
    salaries = {r['player_master_id']: r for r in read(old / 'fresh_salary_identities.json') if r['player_master_id']}
    if args.verify:
        saved = read(out / 'decision.json')
        assert saved['sha256'] == digest_payload({k: v for k, v in saved.items() if k != 'sha256'})
        for filename, expected in saved['preserved_files'].items():
            assert sha256(Path(filename).read_bytes()).hexdigest() == expected, filename
        checks = 0
        for label, result in saved['results'].items():
            from scripts.reconcile_classic_discovery_selection import Policy
            policy = Policy(**saved['policies'][label])
            caps = saved['caps'][label]
            assert not violations(result['lineups'], policy, caps, ctx['elevated'])
            for row in result['lineups']:
                fresh = compact_candidate(row['player_ids'], ctx)
                assert all(abs(fresh[k] - row[k]) < 1e-8 for k in ('objective_score', 'mean', 'p90', 'salary'))
                assert fresh['roster_sha256'] == row['roster_sha256']
                assert slots(row, ctx, salaries) == row['slots']
                legal, why = OptimizerService._validate_classic_lineups(
                    [[OptimizerService._gpp_player_to_dict(p) for p in ctx['players'] if p.player_id in row['player_ids']]],
                    requested_lineups=1, max_exposure=1, enforce_single_te=True,
                    avoid_dst_opponents=True, locked_player_ids=set(), excluded_player_ids=ctx['excluded'],
                    excluded_opponent_teams=set())
                assert legal, why
                checks += 1
        print(json.dumps(dict(status='verified', checked_rosters=checks, preserved_files=len(saved['preserved_files']), sha256=saved['sha256'])))
        return
    out.mkdir(parents=True, exist_ok=args.resume)
    if (out / 'decision.json').exists():
        raise ValueError('Completed decision exists; use --verify or a new directory')
    preserved = {str(p.resolve()): sha256(p.read_bytes()).hexdigest() for p in old.rglob('*') if p.is_file()}
    full, admitted = bundle['union'], bundle['targets']['400']['admitted']
    for row in full:
        fresh = compact_candidate(row['player_ids'], ctx)
        assert abs(fresh['objective_score'] - row['objective_score']) < 1e-8
    from scripts.reconcile_classic_discovery_selection import Policy
    policy = Policy(**bundle['frozen_eligibility_policy']); base_caps = selected_caps(inputs)
    capped = {**base_caps}
    for p in ctx['players']:
        if p.position in {'RB', 'WR', 'TE'}:
            capped[p.player_id] = min(base_caps.get(p.player_id, 1), .8)
    policies = dict(A=policy, B=replace(policy, name='B_game_max3', canonical_game_cap=3),
                    C=replace(policy, name='C_skill_max4'),
                    D=replace(policy, name='D_joint', canonical_game_cap=3),
                    E=replace(policy, name='E_joint_overlap4', canonical_game_cap=3, overlap=4))
    results, caps_by_label = {}, {}
    for label, pol in policies.items():
        caps = capped if label in {'C', 'D', 'E'} else base_caps
        for pool_name, pool in [('full757', full), ('admitted400', admitted)]:
            key = label + '_' + pool_name
            checkpoint = out / (key + '.json')
            if args.resume and checkpoint.exists():
                results[key] = read(checkpoint)
            else:
                result = solve(pool, pol, caps, ctx['elevated'], log_path=out / (key + '.cbc.log'))
                results[key] = enrich(result, ctx, salaries, bundle['global_known_frontier'])
                write(checkpoint, results[key])
            caps_by_label[key] = caps
            print(key, results[key]['status'], results[key]['selector_sum'], flush=True)
    serialized_policies = {k: asdict(policies[k.split('_')[0]]) for k in results}
    meyers = next(p.player_id for p in ctx['players'] if p.name == 'Jakobi Meyers')
    for label, pol, caps in [('A_no_Meyers', policy, {**base_caps, meyers: 0}),
                              ('D_no_Meyers', policies['D'], {**capped, meyers: 0})]:
        result = solve(full, pol, caps, ctx['elevated'], log_path=out / (label + '.cbc.log'))
        results[label] = enrich(result, ctx, salaries, bundle['global_known_frontier'])
        serialized_policies[label] = asdict(pol); caps_by_label[label] = caps
        print(label, result['status'], results[label]['selector_sum'], flush=True)
    # Independent single-lineup Classic objective. Multi-entry QB/core caps have
    # no coherent one-entry interpretation; the existing conservative risk
    # portfolio budget floor(.6*1)=0 is retained by excluding elevated players.
    single_caps = {pid: (0 if cap < 1 and pid in ctx['elevated'] else 1) for pid, cap in base_caps.items()}
    single_policy = replace(policy, name='existing_classic_lineup_objective_single', count=1,
                            minimum_qbs=1, minimum_stack_types=1, canonical_game_cap=None)
    legal_single = [r for r in full if not set(r['player_ids']) & ctx['elevated']]
    for label, rows in [('friends_single', legal_single),
                        ('friends_alternative', [r for r in legal_single if r['roster_sha256'] != legal_single[0]['roster_sha256']])]:
        result = solve(rows, single_policy, single_caps, ctx['elevated'], log_path=out / (label + '.cbc.log'))
        results[label] = enrich(result, ctx, salaries, bundle['global_known_frontier'])
        serialized_policies[label] = asdict(single_policy); caps_by_label[label] = single_caps
    # Verify global single-lineup objective separately from saved-pool selection.
    model = capture_model(ctx)
    single_request = DiscoveryRequest('independent_single_lineup', maximum_groups=((tuple(sorted(ctx['elevated'] & {p.player_id for p in ctx['players']})), 0),), safety_max=2)
    single_path = out / 'single_lineup_solver.json'
    single = read(single_path) if args.resume and single_path.exists() else solve_request(model, ctx, single_request, ctx['options']['solver_backend'])
    if not single_path.exists():
        write(single_path, single)
    assert single['events'][0]['status'] == 'optimal'
    assert abs(single['rows'][0]['objective_score'] - results['friends_single']['selector_sum']) < 1e-8
    ranks = _position_ranks([p for p in ctx['players'] if p.player_id not in ctx['excluded']])
    evidence = {r['player_id']: r for r in read(old / 'source_to_risk_audit_final.json')}
    features = {r['player_id']: r['feature_json'] for r in read(old / 'projection_features.json')}
    targets = []
    for name in TARGETS:
        p = next(p for p in ctx['players'] if p.name == name)
        alternatives = {}
        for contains in (True, False):
            request = DiscoveryRequest('audit_contains' if contains else 'audit_avoids',
                required_ids=(p.player_id,) if contains else (),
                maximum_groups=() if contains else (((p.player_id,), 0),))
            value = solve_request(model, ctx, request, ctx['options']['solver_backend'])
            alternatives['containing' if contains else 'avoiding'] = {**value,
                'lineup': enrich(dict(status=value['events'][0]['status'], lineups=[compact_candidate(value['rows'][0]['player_ids'], ctx)]),
                                  ctx, salaries, bundle['global_known_frontier']) if value['rows'] else None}
        selected = [r for r in results['A_full757']['lineups'] if p.player_id in r['player_ids']]
        diag = []
        for r in selected:
            others = [o for o in ctx['players'] if o.position == p.position and o.player_id not in r['player_ids']
                      and o.player_id not in ctx['excluded'] and o.salary <= p.salary + 50000 - r['salary']
                      and o.projection >= p.projection and o.ceiling >= p.ceiling]
            detail = describe_candidate([q for q in ctx['players'] if q.player_id in r['player_ids']],
                all_players=ctx['players'], config=ctx['config'], pool_by_id=ctx['source'],
                ownership_available=False, game_totals=[], candidate_aware_ownership=True)
            rules = [rule for rule in detail['correlation_rules'] if p.player_id in {m.get('player_id') for m in rule.get('players', [])}]
            diag.append(dict(roster_sha256=r['roster_sha256'], salary_slack=50000-r['salary'],
                affordable_nonworse_same_position=[o.name for o in others],
                player_involving_correlation_contribution=sum(float(r.get('objective_contribution') or 0) for r in rules),
                correlation_rules=rules))
        targets.append(dict(player_id=p.player_id, name=name, salary=p.salary, mean=p.projection,
            marginal_p90=p.ceiling, ranks=ranks[p.player_id],
            mean_value_rank=1+sum(q.projection/(q.salary/1000)>p.projection/(p.salary/1000) for q in ctx['players']
                                if q.position==p.position and q.player_id not in ctx['excluded']),
            evidence=evidence.get(p.player_id), features=features.get(p.player_id),
            candidate_exposure={pool: sum(p.player_id in r['player_ids'] for r in rows) for pool,rows in [('full757',full),('admitted400',admitted)]},
            selected_exposure={label: result['player_exposures'].get(p.player_id,{}).get('entries',0) for label,result in results.items()},
            salary_and_stack_diagnostics=diag, best_legal_alternatives=alternatives))
        print('player audited', name, flush=True)
    write(out / 'player_audits.json', targets)
    body = dict(contract='week4_sunday_contest_portfolio_decision_v1', created_at=datetime.now(UTC).isoformat(),
        frozen_path=str(old.resolve()), frozen_comparison_sha256=bundle['sha256'], input_sha256=digest_payload(inputs),
        projection_run_id=bundle['projection_run_id'], control_run_id=bundle['control_run_id'],
        prior_preview_run_id=bundle['preview_run_id'], draft_group_id=154078, entry_status='UNASSIGNED_PLANNING_ONLY',
        policies=serialized_policies, caps=caps_by_label, results=results, preserved_files=preserved,
        solver_scope='757 known legal rosters; single-lineup and player-specific global solves use frozen eligible model; no exhaustive portfolio-generation claim',
        ownership_evidence=inputs['report']['ownership_evidence'])
    write(out / 'decision.json', {**body, 'sha256':digest_payload(body)})


if __name__ == '__main__':
    main()
