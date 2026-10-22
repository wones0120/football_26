"""Deterministic whole-roster coverage of a common conditional world set.

Expected-game anchor first; further entries add conditional upside coverage.
World likelihoods remain unknown; this is not probability or payout utility.
The caller supplies a completion oracle backed by the unchanged hard model.
No solver, source collection, player forecast or live default is created here.
"""
from copy import deepcopy
from dataclasses import dataclass
import math
import time
from uuid import UUID

from .analyst_shadow import digest

POLICY = 'expected_anchor_incremental_world_gain_v1'
MEAN_CONTRACT = 'single_conditional_fp_mean_before_roster_multiplier_v1'
ORACLE_SIZE = 'exact_requested_portfolio'


@dataclass(frozen=True)
class Limits:
    max_candidates: int = 1000
    max_worlds: int = 64
    max_oracle_calls: int = 128
    wall_seconds: float = 10.0
    point_decimals: int = 9


def _number(value, label):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(label + ' requires a known finite number')
    return float(value)


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _roster(candidate, fmt):
    roster = candidate.get('roster')
    if not isinstance(roster, list) or len(roster) != (6 if fmt == 'showdown' else 9):
        raise ValueError('Candidate must contain a complete format-specific roster')
    members = []
    for player in roster:
        pid = player.get('player_master_id')
        try:
            if str(UUID(pid)) != pid:
                raise ValueError('Canonical UUID spelling required')
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError('Candidate requires canonical player UUID') from exc
        role = player.get('role')
        if fmt == 'showdown' and role not in {'CPT', 'FLEX'}:
            raise ValueError('Showdown requires explicit CPT/FLEX roles')
        if fmt == 'classic' and role not in {'SELECTED', 'QB', 'RB', 'WR', 'TE', 'FLEX', 'DST'}:
            raise ValueError('Unknown Classic roster role')
        salary = _number(player.get('salary'), 'Role-specific salary')
        if salary < 0:
            raise ValueError('Negative salary')
        members.append(dict(player_master_id=pid, role=role, salary=salary))
    if len({p['player_master_id'] for p in members}) != len(members):
        raise ValueError('Candidate repeats a physical player')
    if fmt == 'showdown' and sum(p['role'] == 'CPT' for p in members) != 1:
        raise ValueError('Showdown requires exactly one Captain')
    # Classic slot permutations are one roster; CPT identity remains material.
    signature = tuple(sorted((p['player_master_id'], 'CPT' if p['role'] == 'CPT' else 'FLEX' if fmt == 'showdown' else 'SELECTED') for p in members))
    return signature, sorted(members, key=lambda p: (p['player_master_id'], p['role']))


def _score(roster, means):
    return sum(_number(means.get(p['player_master_id']), 'Player/world conditional mean')
               * (1.5 if p['role'] == 'CPT' else 1.0) for p in roster)


class _BoundedStop(Exception):
    pass


def select_shared_world_portfolio(candidates, worlds, *, base_player_means, requested,
                                  completion_feasible, anchor_world_id, limits=None, clock=time.monotonic):
    """Select deterministic admissible prefixes, with exact completion proof.

    A candidate contains candidate_id, input_sha256, frozen_scope and a full
    roster of canonical players with role-specific salary. A world contains the
    same input/scope, world_id, kind baseline/conditional/contrary, source_refs,
    mechanism, MEAN_CONTRACT, likelihood='unknown', and physical-player means.

    The oracle receives prefix_ids, remaining_ids, requested and deadline. It
    must return status feasible/infeasible/timeout, constraint_sha256,
    target_size=requested, achieved_size_semantics=ORACLE_SIZE, and proof. A
    feasible response also declares feasible_completion_size=requested. Boolean
    responses are rejected. Every admitted prefix must still permit the entire
    requested portfolio; no cap/minimum/overlap relaxation is hidden here.
    """
    if not callable(completion_feasible):
        raise ValueError('An unchanged-hard-model completion oracle is required')
    limits = limits or Limits()
    if type(requested) is not int or requested < 1:
        raise ValueError('Requested portfolio size must be positive')
    if (not 1 <= len(candidates) <= limits.max_candidates
            or not 2 <= len(worlds) <= limits.max_worlds
            or limits.max_oracle_calls < 1 or limits.wall_seconds <= 0
            or not 0 <= limits.point_decimals <= 12):
        raise ValueError('Shared-world input exceeds declared bounds')
    start = clock(); deadline = start + limits.wall_seconds
    scope = worlds[0].get('frozen_scope'); input_sha = worlds[0].get('input_sha256')
    if not isinstance(scope, dict) or not scope or not _sha(input_sha):
        raise ValueError('Worlds require frozen scope and input lineage')
    fmt = scope.get('contest_format')
    if fmt not in {'classic', 'showdown'}:
        raise ValueError('Unknown frozen contest format')
    kinds = set(); world_ids = set(); original_worlds = []
    for world in worlds:
        if world.get('frozen_scope') != scope or world.get('input_sha256') != input_sha:
            raise ValueError('Every world must share one frozen scope/input lineage')
        wid = world.get('world_id')
        if not isinstance(wid, str) or not wid or wid in world_ids:
            raise ValueError('World identity missing or duplicate')
        world_ids.add(wid); kinds.add(world.get('kind'))
        if world.get('kind') not in {'baseline', 'conditional', 'contrary'}:
            raise ValueError('World kind must be explicit')
        if world.get('mean_contract') != MEAN_CONTRACT or not isinstance(world.get('player_means'), dict):
            raise ValueError('World requires a single physical-player conditional FP mean ancestry')
        if world.get('likelihood') != 'unknown' or any(k in world for k in ('weight', 'probability', 'scenario_weight', 'fp_bonus', 'count_bonus')):
            raise ValueError('World weights/probabilities/additive bonuses are unsupported')
        if not world.get('source_refs') or not world.get('mechanism'):
            raise ValueError('World requires source ancestry and an authored mechanism')
        original_worlds.append(deepcopy(world))
    if not {'baseline', 'contrary'} <= kinds:
        raise ValueError('Common world set requires identified baseline and contrary coverage')
    anchor = next((w for w in original_worlds if w['world_id'] == anchor_world_id), None)
    if anchor is None or anchor.get('anchor_basis') not in {'authored_EXPECTED_GAME', 'explicit_base_model_expected'}:
        raise ValueError('Explicit expected-game anchor with declared lineage is required')
    canonical = {}; variant_ids = {}
    for candidate in candidates:
        if candidate.get('frozen_scope') != scope or candidate.get('input_sha256') != input_sha:
            raise ValueError('Candidate belongs to another frozen scope/input lineage')
        signature, roster = _roster(candidate, fmt)
        cid = candidate.get('candidate_id')
        if not isinstance(cid, str) or not cid:
            raise ValueError('Candidate variant identity required')
        if cid in variant_ids and variant_ids[cid] != signature:
            raise ValueError('One candidate ID describes conflicting rosters')
        variant_ids[cid] = signature
        salary = sum(p['salary'] for p in roster)
        if signature in canonical:
            if canonical[signature]['roster'] != roster:
                raise ValueError('Same canonical roster has conflicting role salary mapping')
            canonical[signature]['variant_ids'].add(cid)
            continue
        canonical[signature] = dict(signature=signature, roster=roster, salary=salary,
            base_mean=_score(roster, base_player_means), variant_ids={cid})
    pool = [canonical[k] for k in sorted(canonical)]
    for row in pool:
        row['canonical_id'] = digest(row['signature'])
        row['variant_ids'] = sorted(row['variant_ids'])
    pool_ids = tuple(row['canonical_id'] for row in pool)
    lookup = {row['canonical_id']: row for row in pool}
    original_worlds.sort(key=lambda w: w['world_id'])
    columns = {}; world_records = []
    for world in original_worlds:
        scores = tuple(_score(row['roster'], world['player_means']) for row in pool)
        # One numeric column per distinct complete-roster score vector. Keep
        # aliases and different semantic/source descriptions in the receipt.
        column = columns.setdefault(scores, dict(scores=scores, aliases=[]))
        column['aliases'].append({k: deepcopy(v) for k, v in world.items() if k != 'player_means'})
    for scores, column in sorted(columns.items(), key=lambda item: item[0]):
        column['column_id'] = digest(scores)
        column['best_candidate_score'] = max(scores)
        world_records.append(column)
    by_id = {row['canonical_id']: index for index, row in enumerate(pool)}
    all_scores = {row['canonical_id']: [w['scores'][i] for w in world_records] for i, row in enumerate(pool)}
    report = dict(policy_id=POLICY, status='incomplete', requested=requested, achieved=0,
        input_sha256=input_sha, frozen_scope=deepcopy(scope),
        canonical_pool_sha256=digest([{k: r[k] for k in ('canonical_id', 'roster', 'base_mean', 'salary')} for r in pool]),
        world_inputs_sha256=digest(original_worlds), world_score_columns_sha256=digest(world_records),
        candidate_variants=len(candidates), distinct_canonical_rosters=len(pool),
        original_worlds=len(worlds), distinct_world_score_columns=len(world_records),
        frozen_world_inputs=deepcopy(original_worlds),
        gap_diagnostic_basis='Frozen candidate-pool best score per world; not a proven feasible final portfolio benchmark',
        score_equivalent_worlds=deepcopy(world_records),
        candidate_evaluations=[dict(canonical_id=r['canonical_id'], variant_ids=r['variant_ids'],
            roster=deepcopy(r['roster']), salary=r['salary'], original_base_expected_points=r['base_mean'],
            world_scores=[dict(column_id=w['column_id'], conditional_mean_points=all_scores[r['canonical_id']][i])
                          for i,w in enumerate(world_records)]) for r in pool],
        selection_steps=[], oracle_calls=[],
        numerical_precision=dict(point_decimals=limits.point_decimals, purpose='Numerical comparison precision in fantasy points, not a football preference'),
        anchor_world_id=anchor_world_id, anchor_basis=anchor['anchor_basis'],
        objective='First maximize anchor conditional mean; later maximize positive incremental gain in any common world; tie anchor mean, original base mean, canonical signature',
        probability_status='Unknown world likelihood; no weights, win probability, payout EV or superiority claim',
        tail_status='Unavailable without calibrated joint draws; marginal player P90 is not scored',
        accounting_limit='Upstream world physical accounting/role/chronology is supplied evidence; this score evaluator cannot certify football mechanics from means',
        limits=deepcopy(limits.__dict__), constraint_fingerprint=None,
        completion_status='No accepted portfolio before exact requested-size completion proof', tentative_prefix=[])
    selected = []; cache = {}; fingerprints = set()
    def check_time():
        if clock() >= deadline:
            raise _BoundedStop('wall_time_limit')
    def oracle(prefix):
        check_time()
        key = tuple(sorted(prefix))
        if key in cache:
            return cache[key]
        if len(report['oracle_calls']) >= limits.max_oracle_calls:
            raise _BoundedStop('oracle_call_limit')
        remaining = tuple(pid for pid in pool_ids if pid not in key)
        try:
            proof = completion_feasible(prefix_ids=key, remaining_ids=remaining,
                requested=requested, deadline=deadline)
        except TimeoutError as exc:
            raise _BoundedStop('completion_oracle_timeout') from exc
        if not isinstance(proof, dict) or proof.get('status') not in {'feasible', 'infeasible', 'timeout'}:
            raise ValueError('Completion oracle must return explicit evidence, not a boolean')
        if (not _sha(proof.get('constraint_sha256')) or proof.get('target_size') != requested
                or proof.get('achieved_size_semantics') != ORACLE_SIZE or not proof.get('proof')):
            raise ValueError('Completion oracle constraint/size proof is incomplete')
        fingerprints.add(proof['constraint_sha256'])
        if len(fingerprints) != 1:
            raise ValueError('Hard-constraint fingerprint changed during selection')
        report['constraint_fingerprint'] = proof['constraint_sha256']
        report['oracle_calls'].append(dict(prefix_ids=list(key), evidence=deepcopy(proof)))
        if proof['status'] == 'timeout':
            raise _BoundedStop('completion_oracle_timeout')
        if proof['status'] == 'feasible' and proof.get('feasible_completion_size') != requested:
            raise ValueError('Oracle proved a different achieved portfolio size')
        check_time()
        cache[key] = proof['status'] == 'feasible'
        return cache[key]
    def gaps(prefix):
        return [w['best_candidate_score'] - max(all_scores[cid][i] for cid in prefix)
                for i, w in enumerate(world_records)]
    anchor_scores = {row['canonical_id']: _score(row['roster'], anchor['player_means']) for row in pool}
    def gains(cid):
        if not selected:
            return [0.0 for _ in world_records]
        return [max(0.0, all_scores[cid][i] - max(all_scores[x][i] for x in selected))
                for i in range(len(world_records))]
    def rank(cid):
        gain = max(gains(cid)) if selected else 0.0
        return (-round(gain, limits.point_decimals),
                -round(anchor_scores[cid], limits.point_decimals),
                -round(lookup[cid]['base_mean'], limits.point_decimals), lookup[cid]['signature'])
    try:
        check_time()
        if not oracle([]):
            report.update(status='infeasible_requested_portfolio', completion_status='Unchanged hard constraints cannot complete requested size')
            return [], report
        for index in range(requested):
            check_time()
            ordered = sorted((cid for cid in pool_ids if cid not in selected), key=rank)
            admissible = []
            for cid in ordered:
                if oracle(selected+[cid]):
                    admissible.append(cid)
                    if len(admissible) == 2:
                        break
            if not admissible:
                report.update(status='infeasible_requested_portfolio', tentative_prefix=selected,
                    completion_status='No exact requested-size completion; no underfilled prefix is accepted')
                return [], report
            chosen = admissible[0]; alternative = admissible[1] if len(admissible) > 1 else None
            before = gaps(selected) if selected else None
            after = gaps(selected+[chosen])
            incremental = gains(chosen)
            best_gain = max(incremental)
            target_columns = [w['column_id'] for i,w in enumerate(world_records) if incremental[i] > 0 and round(incremental[i],limits.point_decimals) == round(best_gain,limits.point_decimals)]
            step = dict(rank=index+1, canonical_id=chosen, variant_ids=lookup[chosen]['variant_ids'],
                roster=deepcopy(lookup[chosen]['roster']), salary=lookup[chosen]['salary'],
                original_base_expected_points=lookup[chosen]['base_mean'],
                anchor_conditional_mean_points=anchor_scores[chosen],
                incremental_gain_by_world=incremental, maximum_incremental_gain_points=best_gain,
                target_world_columns=target_columns,
                target_world_ids=[a['world_id'] for w in world_records if w['column_id'] in target_columns for a in w['aliases']],
                coverage_status='anchor_selection' if not selected else 'incremental_scenario_coverage' if best_gain > 0 else 'no_incremental_scenario_coverage',
                descending_remaining_gap_points=sorted(after, reverse=True),
                marginal_gap_reduction_by_world=None if before is None else [a-b for a, b in zip(before, after)],
                strongest_admissible_alternative=None if alternative is None else dict(
                    canonical_id=alternative, roster=deepcopy(lookup[alternative]['roster']),
                    salary=lookup[alternative]['salary'], original_base_expected_points=lookup[alternative]['base_mean'],
                    anchor_conditional_mean_points=anchor_scores[alternative], incremental_gain_by_world=gains(alternative),
                    selected_minus_alternative_base_mean=lookup[chosen]['base_mean']-lookup[alternative]['base_mean'],
                    selected_minus_alternative_anchor_mean=anchor_scores[chosen]-anchor_scores[alternative],
                    selected_minus_alternative_maximum_incremental_gain=best_gain-max(gains(alternative)),
                    descending_remaining_gap_points=sorted(gaps(selected+[alternative]), reverse=True)),
                world_assessments=[dict(column_id=w['column_id'], world_aliases=deepcopy(w['aliases']),
                    full_roster_points=all_scores[chosen][i], remaining_portfolio_gap_points=after[i],
                    player_contributions_representative_world_id=w['aliases'][0]['world_id'],
                    contribution_scope='Representative alias only; each original player allocation is retained in frozen_world_inputs',
                    player_contributions=[dict(player_master_id=p['player_master_id'], role=p['role'],
                        conditional_points=(next(original['player_means'][p['player_master_id']] for original in original_worlds if original['world_id']==w['aliases'][0]['world_id']))*(1.5 if p['role']=='CPT' else 1)) for p in lookup[chosen]['roster']]) for i, w in enumerate(world_records)],
                reason='Highest expected-game anchor conditional mean with exact completion proof' if not selected else 'Largest positive incremental points in any authored common world; likelihood unknown' if best_gain > 0 else 'No incremental scenario coverage; strongest remaining anchor under unchanged controls',
                shared_risk='Entries use the same worlds; failure within one common world can affect several entries together; likelihood is unknown')
            report['selection_steps'].append(step)
            selected.append(chosen)
        report.update(status='completed', achieved=len(selected), tentative_prefix=[],
            completion_status='Every selected prefix proved an exact requested-size completion; final portfolio reaches it',
            final_remaining_gap_points=gaps(selected), elapsed_seconds=clock()-start)
        return [deepcopy(lookup[cid]) for cid in selected], report
    except _BoundedStop as exc:
        report.update(status='bounded_incomplete', stop_reason=str(exc), tentative_prefix=list(selected),
            achieved=0, elapsed_seconds=clock()-start,
            completion_status='No playable portfolio returned from incomplete bounded search; timeout is not infeasibility')
        return [], report
