"""Common-frame prospective Classic discovery and immutable offline replay.

Capture the existing football model without solving or globally patching a solver.
Production use is explicit opt-in; enumeration may be bounded or unproven.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from itertools import combinations
from math import floor
from pathlib import Path
from statistics import mean, median
from time import perf_counter
from typing import Any, Callable, Sequence

import pulp

from . import gpp_optimizer
from .cbc_solver import make_cbc_solver
from .classic_prospective import digest_payload, validate_solver_snapshot
from .classic_small_field import _admit_candidate_caps, describe_candidate
from .classic_thesis_shadow import canonical_game
from .gpp_optimizer import (LineupTagCaps, ObjectiveWeights, Player, PortfolioTargets,
                            SlateConfig, StackRules, TagThresholds)

TOLERANCES = (0.05, 0.10, 0.15, 0.20, 0.30)
STAGES = ('eligible_player_pool', 'solver_request_created', 'legal_lineup_solved',
          'duplicate_rejected', 'injury_risk_rejected', 'player_cap_conflict',
          'family_constraint', 'admission_target_competition', 'quality_threshold',
          'accepted_into_candidate_pool')


def roster_key(row: dict) -> tuple[str, ...]:
    return tuple(sorted(row['player_ids']))


def rank_candidates(rows: Sequence[dict]) -> list[dict]:
    return [{**r, 'rank': i} for i, r in enumerate(sorted(rows, key=lambda r:
        (-r['objective_score'], -r['mean'], roster_key(r))), 1)]


def validate_prospective(inputs: dict, *, now: datetime | None = None) -> None:
    report = inputs['report']
    snapshot = report['frozen_solver_snapshot']
    validate_solver_snapshot(snapshot)
    kickoff = datetime.fromisoformat(report['prelock_timing']['first_saved_kickoff_at'])
    cutoff = datetime.fromisoformat(snapshot['payload']['metadata']['decision_cutoff_at'])
    if cutoff >= kickoff or (now or datetime.now(UTC)) >= kickoff:
        raise ValueError('Prospective discovery must run before the frozen first kickoff')
    for name, expected in snapshot['payload']['metadata']['code_sha256'].items():
        if sha256((Path(__file__).parent / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Frozen production code changed: {name}')
    # Reject new outcome fields rather than silently letting them influence ranking.
    def check(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key.startswith(('actual_', 'postgame', 'realized_')):
                    raise ValueError(f'Outcome input forbidden: {key}')
                check(item)
        elif isinstance(value, list):
            for item in value:
                check(item)
    check(snapshot['payload'])
    # Rule evaluations use final_score for a pregame rule score. Only reject
    # that ambiguous field on source/player records, not within rule evidence.
    if any('final_score' in r for r in snapshot['payload']['players'] + snapshot['payload']['pool_rows']):
        raise ValueError('Outcome input forbidden: final_score')
    for row in snapshot['payload']['pool_rows']:
        for key, value in row.items():
            if key.endswith('_observed_at') and value and value != 'NaT':
                if datetime.fromisoformat(str(value).replace('Z', '+00:00')) > cutoff:
                    raise ValueError(f'Observation after decision cutoff: {key}')


def load_context(inputs: dict) -> dict:
    validate_prospective(inputs)
    report = inputs['report']
    p = report['frozen_solver_snapshot']['payload']
    c = p['resolved_config']
    config = SlateConfig(**{**c, 'stack_rules': StackRules(**c['stack_rules']),
        'tag_thresholds': TagThresholds(**c['tag_thresholds']),
        'objective_weights': ObjectiveWeights(**c['objective_weights']),
        'tag_caps': LineupTagCaps(**c['tag_caps']),
        'portfolio_targets': PortfolioTargets(**c['portfolio_targets'])})
    players = [Player(**{**r, 'tags': set(r['tags'])}) for r in p['players']]
    risk = {r['player_id']: r for r in report['prospective_experiment']['availability_risk']['players']}
    # Frozen eligible pool preserves the scoring denominator; forbid ineligible
    # players in the model instead of shrinking/re-normalizing the player frame.
    excluded = {r.player_id for r in players if risk.get(r.player_id, {}).get('bucket') in {'out', 'doubtful'}}
    excluded |= set(p['options'].get('exclude_player_ids') or [])
    starters = set(p['options']['starting_qb_ids'])
    excluded |= {r.player_id for r in players if r.position == 'QB' and r.player_id not in starters}
    return dict(players=players, config=config, options=p['options'], risk=risk,
                excluded=excluded, elevated={pid for pid, r in risk.items() if r['bucket'] == 'questionable_elevated'},
                source={r['player_id']: r for r in p['pool_rows']},
                policy=report['production_controls']['policy'])


def capture_model(context: dict) -> pulp.LpProblem:
    captured = []
    options = context['options']
    gpp_optimizer._build_lineup(context['players'], context['config'], None, [],
        enforce_single_te=options['enforce_single_te'],
        avoid_dst_opponents=options['avoid_dst_opponents'],
        required_player_ids=set(options.get('locked_player_ids') or []),
        model_capture=captured.append)
    if not captured:
        raise ValueError('Cannot capture an empty Classic model')
    model = captured[0]
    variables = model.variablesDict()
    for i, player in enumerate(context['players']):
        if player.player_id in context['excluded']:
            model += variables[f'p_{i}'] == 0
    return model


@dataclass(frozen=True)
class DiscoveryRequest:
    source: str
    required_ids: tuple[str, ...] = ()
    qb_id: str | None = None
    template: tuple[int, int] | None = None
    minimum_groups: tuple[tuple[tuple[str, ...], int], ...] = ()
    maximum_groups: tuple[tuple[tuple[str, ...], int], ...] = ()
    safety_max: int = 1
    tolerance: float | None = None
    enforce_risk: bool = True


def constrained_model(base: pulp.LpProblem, context: dict, request: DiscoveryRequest) -> pulp.LpProblem:
    model = deepcopy(base)
    variables = model.variablesDict()
    players = context['players']
    by_id = {p.player_id: variables[f'p_{i}'] for i, p in enumerate(players)}
    required = set(request.required_ids) | ({request.qb_id} if request.qb_id else set())
    if not required <= set(by_id) or required & context['excluded']:
        raise ValueError('Request contains an ineligible canonical player ID')
    for pid in sorted(required):
        model += by_id[pid] == 1
    if request.enforce_risk:
        model += pulp.lpSum(by_id[pid] for pid in context['elevated'] if pid in by_id) <= context['policy']['max_elevated_per_lineup']
    if request.template is not None:
        if request.qb_id is None:
            raise ValueError('Exact stack template requires a QB direction')
        qb = next(p for p in players if p.player_id == request.qb_id)
        rules = context['config'].stack_rules
        catchers, backs = request.template
        if catchers < rules.min_pass_catchers or backs < rules.min_bring_backs:
            raise ValueError('Template would relax frozen football policy')
        for positions, team, count in [(rules.pass_catcher_positions, qb.team, catchers),
                                       (rules.bring_back_positions, qb.opponent, backs)]:
            model += pulp.lpSum(by_id[p.player_id] for p in players if p.team == team and p.position in positions) == count
    for ids, count in request.minimum_groups:
        model += pulp.lpSum(by_id[pid] for pid in ids) >= count
    for ids, count in request.maximum_groups:
        model += pulp.lpSum(by_id[pid] for pid in ids) <= count
    return model


def enumerate_frontier(solve: Callable[[list[tuple[str, ...]]], dict], *, safety_max: int,
                       tolerance: float | None, frontier: float | None = None) -> dict:
    """Exact no-good cuts; censored counts never masquerade as exhaustive counts.

    solve returns {status: optimal/infeasible/unproven, player_ids, objective_score}.
    A tolerance boundary requires a proven optimum outside the inclusive window.
    """
    if safety_max < 1 or (tolerance is not None and tolerance < 0):
        raise ValueError('Invalid frontier stopping parameters')
    rows, cuts, seen = [], [], set()
    boundary = None
    numerical_warning = None
    stop = 'safety_max'
    for _ in range(safety_max):
        row = solve(cuts)
        if row['status'] != 'optimal':
            stop = 'exhausted' if row['status'] == 'infeasible' else 'unproven'
            break
        score = float(row['objective_score'])
        if frontier is None:
            frontier = score
        if rows and score > rows[-1]['objective_score'] + 1e-7:
            numerical_warning = {'previous_score': rows[-1]['objective_score'], 'next_score': score}
            stop = 'numerical_nonmonotonic'
            break
        if tolerance is not None and frontier - score > tolerance + 1e-9:
            boundary, stop = score, 'tolerance'
            break
        key = roster_key(row)
        if key in seen:
            raise ValueError('No-good cut failed to exclude an exact roster')
        seen.add(key)
        rows.append(row)
        cuts.append(key)
    return {'rows': rows, 'stop': stop, 'boundary_score': boundary,
            'frontier': frontier, 'complete': stop in {'exhausted', 'tolerance'},
            'numerical_warning': numerical_warning}


def solve_request(base: pulp.LpProblem, context: dict, request: DiscoveryRequest,
                  backend: str, frontier: float | None = None) -> dict:
    started = perf_counter()
    model = constrained_model(base, context, request)
    variables = model.variablesDict()
    by_id = {p.player_id: variables[f'p_{i}'] for i, p in enumerate(context['players'])}
    solver = make_cbc_solver(backend)
    solver.threads = 1
    solver.options.extend(['randomSeed 1', 'randomCbcSeed 1', 'increment 1e-10',
                           'primalTolerance 1e-9', 'dualTolerance 1e-9', 'integerTolerance 1e-9'])
    solver.optionsDict.update(gapRel=0, gapAbs=0)
    # A stalled solve is recorded as unproven; never claim a frontier boundary.
    solver.timeLimit = 30
    events = []
    cut_count = 0
    def solve(cuts: list[tuple[str, ...]]) -> dict:
        nonlocal cut_count
        for key in cuts[cut_count:]:
            model.addConstraint(pulp.lpSum(by_id[pid] for pid in key) <= len(key) - 1,
                                name=f'shadow_exact_roster_cut_{cut_count}')
            cut_count += 1
        begin = perf_counter()
        status = model.solve(solver)
        # CBC may report LpStatusOptimal for a time-limited incumbent; insist on
        # an optimal solution status as well, not merely an integer-feasible one.
        optimal = status == pulp.LpStatusOptimal and model.sol_status == pulp.LpSolutionOptimal
        result = {'status': 'optimal' if optimal else 'infeasible' if status == pulp.LpStatusInfeasible else 'unproven'}
        if optimal:
            ids = sorted(pid for pid, v in by_id.items() if v.value() > .9)
            if len(ids) != context['config'].roster_size:
                raise ValueError('Incomplete solved roster')
            result.update(player_ids=ids, objective_score=float(pulp.value(model.objective)))
        events.append({**result, 'seconds': perf_counter() - begin})
        return result
    result = enumerate_frontier(solve, safety_max=request.safety_max,
                                tolerance=request.tolerance, frontier=frontier)
    return {**result, 'request': request.__dict__, 'events': events, 'seconds': perf_counter() - started}


def meaningful_players(context: dict, current: Sequence[dict]) -> list[Player]:
    """Union of pregame position leaders and coverage gaps; no names/results."""
    counts = Counter(pid for r in current for pid in r['player_ids'])
    groups = defaultdict(list)
    for p in context['players']:
        if p.player_id not in context['excluded'] and p.projection > 0:
            groups[p.position].append(p)
    selected = set()
    for position, players in sorted(groups.items()):
        if position == 'QB':
            selected.update(p.player_id for p in players)
            continue
        metrics = [lambda p: p.projection, lambda p: p.ceiling,
                   lambda p: max(p.optimizer_receiving_role_strength, p.optimizer_rushing_role_strength),
                   lambda p: p.projection / max(1, p.salary) * 1000,
                   lambda p: p.ownership or 0,
                   lambda p: (p.team_total or 0) * p.projection]
        for metric in metrics:
            leaders = sorted(players, key=lambda p: (-metric(p), p.player_id))
            selected.update(p.player_id for p in leaders[:12] if metric(p) > 0)
        # Wider ceiling screen for omissions, independent of a manually named list.
        selected.update(p.player_id for p in sorted(players, key=lambda p: (-p.ceiling, p.player_id))[:24]
                        if counts[p.player_id] <= 1)
    return sorted((p for p in context['players'] if p.player_id in selected), key=lambda p: p.player_id)


def discovery_requests(context: dict, current: Sequence[dict]) -> list[DiscoveryRequest]:
    players = [p for p in context['players'] if p.player_id not in context['excluded']]
    qbs = sorted((p for p in players if p.position == 'QB'), key=lambda p: p.player_id)
    requests = []
    for qb in qbs:
        for template in ((n, b) for n in (1, 2, 3) for b in (0, 1)):
            if template[0] >= context['config'].stack_rules.min_pass_catchers and template[1] >= context['config'].stack_rules.min_bring_backs:
                requests.append(DiscoveryRequest('qb_direction', qb_id=qb.player_id, template=template))
        catchers = sorted((p for p in players if p.team == qb.team and p.position in {'WR', 'TE'}),
                          key=lambda p: (-max(p.optimizer_receiving_role_strength, p.projection / 25), -p.ceiling, p.player_id))
        partners = catchers[:3]
        te = next((p for p in catchers if p.position == 'TE'), None)
        if te and te not in partners:
            partners.append(te)
        for size in (1, 2, 3):
            for combo in combinations(partners, size):
                for bb in (0, 1):
                    if size < context['config'].stack_rules.min_pass_catchers or bb < context['config'].stack_rules.min_bring_backs:
                        continue
                    requests.append(DiscoveryRequest('stack_partner', required_ids=tuple(sorted(p.player_id for p in combo)),
                                                      qb_id=qb.player_id, template=(size, bb)))
    for p in meaningful_players(context, current):
        requests.append(DiscoveryRequest('player_forced', required_ids=(p.player_id,)))
    # Force FLEX positional alternatives, salary distributions, and each DST tier.
    for pos, count in [('RB', 3), ('WR', 4), ('TE', 2)]:
        if pos == 'TE' and context['options']['enforce_single_te']:
            continue
        ids = tuple(p.player_id for p in players if p.position == pos)
        requests.append(DiscoveryRequest(f'structure:flex:{pos}', minimum_groups=((ids, count),), maximum_groups=((ids, count),)))
    for lower, upper in ((0, 2500), (2500, 3500), (3500, 6000)):
        ids = tuple(p.player_id for p in players if p.position == 'DST' and lower <= p.salary < upper)
        requests.append(DiscoveryRequest(f'structure:dst:{lower}:{upper}', minimum_groups=((ids, 1),)))
    skill = [p for p in players if p.position in {'RB', 'WR', 'TE'}]
    stars = tuple(p.player_id for p in skill if p.salary >= 7500)
    cheap = tuple(p.player_id for p in skill if p.salary <= 4000)
    middle = tuple(p.player_id for p in skill if 4500 <= p.salary <= 7000)
    requests.append(DiscoveryRequest('structure:stars_scrubs', minimum_groups=((stars, 2), (cheap, 2))))
    requests.append(DiscoveryRequest('structure:balanced', minimum_groups=((middle, 6),)))
    # Each meaningful TE is already explicitly covered by player-forced requests.
    return requests


def compact_candidate(ids: Sequence[str], context: dict) -> dict:
    by_id = {p.player_id: p for p in context['players']}
    row = describe_candidate([by_id[pid] for pid in ids], all_players=context['players'],
        config=context['config'], pool_by_id=context['source'], ownership_available=False,
        game_totals=sorted({p.game_total for p in context['players'] if p.game_total is not None}),
        candidate_aware_ownership=True)
    # Keep the existing thesis contract, without repeating verbose rule evidence.
    fields = ('player_ids', 'objective_score', 'mean', 'p90', 'salary', 'qb', 'stack',
              'game_environment', 'roster', 'components', 'component_statuses', 'ownership_sum')
    result = {key: row[key] for key in fields}
    result['roster_sha256'] = digest_payload({'player_ids': sorted(ids)})
    result['game_key'] = canonical_game(by_id[row['qb']['player_id']].game_id,
                                        row['qb']['team'], by_id[row['qb']['player_id']].opponent)['key']
    result['family_key'] = f"{row['qb']['player_id']}|QB+{row['stack']['partner_count']}|BB{int(row['stack']['bring_back_count'] > 0)}"
    result['role_classes'] = sorted({context['source'].get(pid, {}).get('pregame_role_label') or 'unclassified' for pid in ids})
    return result


def recall(raw: Sequence[dict], discovered: Sequence[dict], frontier: float) -> dict:
    keys = {roster_key(r) for r in discovered}
    raw = list({roster_key(r): r for r in raw}.values())
    return {f'{t:.2f}': {'known_legal': len(rows := [r for r in raw if frontier - r['objective_score'] <= t + 1e-9]),
                       'discovered': (found := sum(roster_key(r) in keys for r in rows)),
                       'recall': found / len(rows) if rows else None}
            for t in TOLERANCES}


def grouped_recall(raw: Sequence[dict], discovered: Sequence[dict], frontier: float,
                   context: dict) -> dict:
    dimensions: dict[str, dict[str, list[dict]]] = {k: defaultdict(list) for k in
        ('qb', 'game', 'stack_family', 'player', 'position', 'salary_tier', 'role_class')}
    players = {p.player_id: p for p in context['players']}
    for r in raw:
        values = {'qb': [r['qb']['player_id']], 'game': [r['game_key']], 'stack_family': [r['family_key']],
                  'player': r['player_ids'], 'position': sorted({players[p].position for p in r['player_ids']}),
                  'salary_tier': sorted({'star' if players[p].salary >= 7500 else 'cheap' if players[p].salary <= 4000 else 'middle' for p in r['player_ids']}),
                  'role_class': r['role_classes']}
        for dimension, members in values.items():
            for member in members:
                dimensions[dimension][member].append(r)
    return {d: {k: recall(rows, discovered, frontier) for k, rows in sorted(groups.items())}
            for d, groups in dimensions.items()}


def diversity(rows: Sequence[dict]) -> dict:
    counts = Counter(pid for r in rows for pid in r['player_ids'])
    n = len(rows)
    scores = sorted(r['objective_score'] for r in rows)
    qbs = Counter(r['qb']['player_id'] for r in rows)
    return {'count': n, 'unique_rosters': len({roster_key(r) for r in rows}),
        'duplication': n - len({roster_key(r) for r in rows}), 'players': len(counts),
        'qb_directions': len(qbs), 'games': len({r['game_key'] for r in rows}),
        'stack_families': len({r['family_key'] for r in rows}),
        'average_overlap': sum(c * (c - 1) / 2 for c in counts.values()) / (n * (n - 1) / 2) if n > 1 else 0,
        'max_player_exposure': max(counts.values(), default=0) / max(1, n),
        'qb_hhi': sum((c / n) ** 2 for c in qbs.values()) if n else 0,
        'selector': {'max': max(scores) if scores else None, 'min': min(scores) if scores else None,
                     'median': median(scores) if scores else None, 'mean': mean(scores) if scores else None}}


def _forced_feasible(rows: Sequence[dict], required_index: int, caps: dict[str, float], count: int,
                     backend: str) -> bool:
    model = pulp.LpProblem('shadow_admission_counterfactual', pulp.LpMaximize)
    x = pulp.LpVariable.dicts('c', range(len(rows)), cat='Binary')
    model += pulp.lpSum(x.values()) == count
    model += x[required_index] == 1
    for pid, cap in sorted(caps.items()):
        if cap < 1:
            model += pulp.lpSum(x[i] for i, r in enumerate(rows) if pid in r['player_ids']) <= floor(cap * count + 1e-9)
    model += 0
    solver = make_cbc_solver(backend)
    status = model.solve(solver)
    if status not in (pulp.LpStatusOptimal, pulp.LpStatusInfeasible):
        raise ValueError('Admission counterfactual unproven')
    return status == pulp.LpStatusOptimal


def admission_lineage(raw: Sequence[dict], accepted: Sequence[dict], caps: dict[str, float],
                      elevated: set[str], max_elevated: int, backend: str,
                      *, family_allowed: Callable[[dict], bool] | None = None,
                      quality_floor: float | None = None) -> list[dict]:
    """Primary reasons from proven counterfactuals, not an overloaded counter.

    Admission is joint, so exposure_before_admission is the final chosen pool
    before proposing insertion, not an invented chronological acceptance trace.
    """
    accepted_keys = {roster_key(r) for r in accepted}
    counts = Counter(pid for r in accepted for pid in r['player_ids'])
    n = len(accepted)
    eligible, seen = [], set()
    preliminary = []
    for r in raw:
        key = roster_key(r)
        reason = ('duplicate_rejected' if key in seen else
                  'injury_risk_rejected' if len(set(key) & elevated) > max_elevated else
                  'family_constraint' if family_allowed and not family_allowed(r) else
                  'quality_threshold' if quality_floor is not None and r['objective_score'] < quality_floor else None)
        seen.add(key)
        if reason is None:
            eligible.append(r)
        preliminary.append(reason)
    eligible_index = {roster_key(r): i for i, r in enumerate(eligible)}
    result = []
    for r, reason in zip(raw, preliminary):
        key = roster_key(r)
        conflicts, single_swap, joint_feasible = [], None, None
        displaced = None
        if reason is None and key in accepted_keys:
            reason = 'accepted_into_candidate_pool'
        elif reason is None:
            for pid in key:
                cap = caps.get(pid, 1.0)
                if cap < 1 and counts[pid] + 1 > floor(cap * n + 1e-9):
                    conflicts.append({'player_id': pid, 'exposure_before_admission': counts[pid],
                        'exposure_fraction': counts[pid] / n if n else 0,
                        'cap': cap, 'cap_count': floor(cap * n + 1e-9),
                        'baseline': 'joint_chosen_pool_before_counterfactual_insertion'})
            # Check all capped players after swapping, including players absent
            # from the incoming roster whose count stays fixed.
            for old in accepted:
                incoming, outgoing = set(key), set(old['player_ids'])
                if all(counts[pid] + int(pid in incoming) - int(pid in outgoing) <= floor(cap * n + 1e-9)
                       for pid, cap in caps.items() if cap < 1):
                    displaced = old.get('roster_sha256') or digest_payload({'player_ids': sorted(outgoing)})
                    break
            single_swap = displaced is not None
            joint_feasible = single_swap or _forced_feasible(eligible, eligible_index[key], caps, n, backend)
            reason = 'admission_target_competition' if joint_feasible else 'player_cap_conflict'
        result.append({'roster_sha256': r.get('roster_sha256') or digest_payload({'player_ids': list(key)}),
            'player_ids': list(key), 'selector': r['objective_score'], 'primary_reason': reason,
            'stages': ['eligible_player_pool', 'solver_request_created', 'legal_lineup_solved', reason],
            'stage_trace': [{'stage': stage, 'status':
                'rejected' if stage == reason and reason != 'accepted_into_candidate_pool' else
                'accepted' if stage == reason else
                'passed' if stage in STAGES[:3] else
                'not_applied' if (stage == 'family_constraint' and family_allowed is None) or
                                 (stage == 'quality_threshold' and quality_floor is None) else
                'not_reached' if STAGES.index(stage) > STAGES.index(reason) else 'passed'}
                for stage in STAGES],
            'aggregate_cap_conflicts': conflicts, 'single_swap_feasible': single_swap,
            'joint_displacement_feasible': joint_feasible, 'displaceable_roster_sha256': displaced})
    return result


def compare_targets(raw: Sequence[dict], context: dict, targets: Sequence[int], backend: str,
                    frontier: float) -> dict:
    by_id = {p.player_id: p for p in context['players']}
    caps = context['caps']
    lineups = [[by_id[pid] for pid in r['player_ids']] for r in raw]
    risk_legal = [r for r in raw if len(set(r['player_ids']) & context['elevated']) <= context['policy']['max_elevated_per_lineup']]
    result = {}
    for target in targets:
        started = perf_counter()
        admitted, _, funnel = _admit_candidate_caps(list(raw), lineups, caps, context['elevated'],
            target, context['policy']['max_elevated_per_lineup'], backend)
        result[str(target)] = {'target': target, 'admitted': rank_candidates(admitted),
            'admission_seconds': perf_counter() - started, 'funnel': funnel,
            'frontier_recall': recall(risk_legal, admitted, frontier),
            'roster_legal_frontier_recall': recall(raw, admitted, frontier), 'diversity': diversity(admitted)}
    return result


def saturation(events: Sequence[dict], frontier: float, *, block_size: int = 50,
               patience: int = 2, meaningful_tolerance: float = .20) -> dict:
    seen, players, qbs, families, games = set(), set(), set(), set(), set()
    curve, quiet, stop = [], 0, None
    for start in range(0, len(events), block_size):
        block = events[start:start + block_size]
        fresh = []
        for r in block:
            if 'candidate' not in r:
                continue
            c = r['candidate']
            key = roster_key(c)
            if key not in seen:
                seen.add(key)
                fresh.append(c)
        new_players = {p for r in fresh for p in r['player_ids']} - players
        new_qbs = {r['qb']['player_id'] for r in fresh} - qbs
        new_families = {r['family_key'] for r in fresh} - families
        new_games = {r['game_key'] for r in fresh} - games
        competitive = [r for r in fresh if frontier - r['objective_score'] <= meaningful_tolerance + 1e-9]
        competitive_players = {p for r in competitive for p in r['player_ids']}
        # Track competitive coverage separately from discoveries far below the
        # frontier, so low-score bench solves cannot masquerade as useful progress.
        prior_competitive = {p for e in events[:start] if 'candidate' in e and frontier - e['candidate']['objective_score'] <= meaningful_tolerance + 1e-9 for p in e['candidate']['player_ids']}
        quiet = quiet + 1 if not competitive and not (competitive_players - prior_competitive) else 0
        full_block = len(block) == block_size
        if full_block and quiet >= patience and stop is None:
            stop = start + len(block)
        curve.append({'solves': start + len(block), 'block_solves': len(block), 'new_unique': len(fresh),
            'new_players': len(new_players), 'new_qbs': len(new_qbs), 'new_stack_families': len(new_families),
            'new_games': len(new_games), 'new_within_tolerance': {f'{t:.2f}': sum(frontier - r['objective_score'] <= t + 1e-9 for r in fresh) for t in TOLERANCES},
            'best_new_selector': max((r['objective_score'] for r in fresh), default=None),
            'new_competitive_players': len(competitive_players - prior_competitive),
            'quiet_blocks': quiet})
        players.update(new_players); qbs.update(new_qbs); families.update(new_families); games.update(new_games)
    return {'curve': curve, 'proposed_stop_solve': stop, 'block_size': block_size,
            'patience': patience, 'meaningful_tolerance': meaningful_tolerance,
            'warning': 'A quiet ordered batch is not a global recall certificate; complete all mandatory source sweeps before stopping.'}


def coverage_audits(raw: Sequence[dict], admitted: Sequence[dict], context: dict, frontier: float,
                    lineage: Sequence[dict], reference: Sequence[dict]) -> tuple[list[dict], list[dict]]:
    reasons = defaultdict(Counter)
    for event in lineage:
        if event['primary_reason'] != 'accepted_into_candidate_pool':
            for pid in event['player_ids']:
                reasons[pid][event['primary_reason']] += 1
    players = []
    qbs = []
    for p in context['players']:
        rows = [r for r in raw if p.player_id in r['player_ids']]
        saved = [r for r in admitted if p.player_id in r['player_ids']]
        best = max(rows, key=lambda r: r['objective_score'], default=None)
        policy_legal = [r for r in rows if len(set(r['player_ids']) & context['elevated']) <= context['policy']['max_elevated_per_lineup']]
        best_policy_legal = max(policy_legal, key=lambda r: r['objective_score'], default=None)
        record = {'player_id': p.player_id, 'player': p.name, 'position': p.position,
            'eligible': p.player_id not in context['excluded'], 'raw_candidate_count': len(rows),
            'raw_frontier_candidate_count': sum(frontier - r['objective_score'] <= .30 + 1e-9 for r in rows),
            'admitted_candidate_count': len(saved), 'best_raw_selector': best['objective_score'] if best else None,
            'best_admitted_selector': max((r['objective_score'] for r in saved), default=None),
            'best_policy_legal_selector': best_policy_legal['objective_score'] if best_policy_legal else None,
            'best_equivalent_rank': 1 + sum(r['objective_score'] > best['objective_score'] + 1e-9 for r in reference) if best else None,
            'known_frontier_rank': 1 + sum(r['objective_score'] > best['objective_score'] + 1e-9 for r in raw) if best else None,
            'mean': p.projection, 'p90': p.ceiling, 'salary': p.salary,
            'role': context['source'].get(p.player_id, {}).get('pregame_role_label'),
            'role_score': max(p.optimizer_receiving_role_strength, p.optimizer_rushing_role_strength),
            'raw_to_admitted_reasons': dict(reasons[p.player_id]),
            'coverage_warning': bool(best_policy_legal and frontier - best_policy_legal['objective_score'] <= .20 + 1e-9 and not saved)}
        players.append(record)
        if p.position == 'QB':
            qbs.append({**record, 'canonical_game': canonical_game(p.game_id, p.team, p.opponent)['key'],
                'frontier_counts': {f'{t:.2f}': sum(frontier - r['objective_score'] <= t + 1e-9 for r in rows) for t in TOLERANCES},
                'stack_families': sorted({r['family_key'] for r in rows}),
                'best_legal_selector': record['best_policy_legal_selector']})
    return players, qbs
