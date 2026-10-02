"""Offline chronological discovery validation contracts; no production callers.

This does not rebuild absent historical inputs from today's mutable tables.
Retrospective computations have their real replay time; only original inputs
must precede lock. Pregame outputs must be persisted before attaching outcomes.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import fields
from datetime import datetime
from math import isfinite
from pathlib import Path
from statistics import mean, median
from typing import Any, Callable

from .classic_candidate_completeness import roster_key
from .classic_prospective import digest_payload, validate_solver_snapshot
from .gpp_optimizer import (LineupTagCaps, ObjectiveWeights, Player,
                            PortfolioTargets, SlateConfig, StackRules, TagThresholds)

TARGETS = (205, 300, 400, 500)
OPTION_FIELDS = frozenset({
    'candidate_target', 'production_candidate_target', 'seed_generation_method',
    'seed_generation_workers', 'deterministic_seed', 'solver_backend',
    'starting_qb_ids', 'maximum_exposure_by_player', 'minimum_exposure_by_player',
    'portfolio_constraints', 'selection_max_exposure', 'generation_max_exposure',
    'ownership_available', 'enforce_single_te', 'avoid_dst_opponents',
    'locked_player_ids', 'exclude_player_ids', 'stack_templates',
    'minimum_uniqueness', 'max_players_per_team', 'max_players_per_game',
    'long_shot_mode', 'large_gpp', 'candidate_aware_ownership',
})


def timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timezone required for chronology evidence')
    return result


def forbid_outcomes(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and (key.startswith(('actual_', 'postgame', 'realized_')) or key in {
                'entry_points', 'winning_lineup', 'dk_points', 'fd_points'}):
                raise ValueError(f'Outcome input forbidden: {key}')
            forbid_outcomes(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            forbid_outcomes(item)


def reconstruction_gate(snapshot: dict | None, *, kickoff_at: str,
                        run_created_at: str, as_of: str,
                        code_hashes: dict[str, str]) -> dict:
    """Validate an original frozen solver frame, not merely saved pool scores.

Source-only safe reconstruction is not implemented by this gate. Such evidence
needs an independently verified complete snapshot and original code archive.
Missing observations can be explicitly frozen as unavailable; they cannot be
filled in from future records.
"""
    try:
        kickoff, created, audit_time = map(timestamp, (kickoff_at, run_created_at, as_of))
        if kickoff >= audit_time:
            return {'qualified': False, 'reason': 'future_slate_diagnostic_only'}
        if created >= kickoff:
            return {'qualified': False, 'reason': 'original_run_at_or_after_lock'}
        if not snapshot:
            return {'qualified': False, 'reason': 'complete_frozen_generation_inputs_absent'}
        validate_solver_snapshot(snapshot)
        payload = snapshot['payload']
        forbid_outcomes(payload)
        meta, options = payload['metadata'], payload['options']
        cutoff = timestamp(meta['decision_cutoff_at'])
        if cutoff >= kickoff or timestamp(meta['created_at']) >= kickoff:
            raise ValueError('Snapshot frozen at or after lock')
        if timestamp(meta['data_cutoff_at']) > cutoff:
            raise ValueError('Data cutoff after decision')
        expected = meta['code_sha256']
        required_code = {'gpp_optimizer.py', 'classic_small_field.py',
                         'lineup_correlation_scoring.py', 'rule_library.py', 'classic_prospective.py'}
        if not required_code <= expected.keys() or any(code_hashes.get(k) != v for k, v in expected.items()):
            raise ValueError('Original generation code unavailable or changed')
        if not OPTION_FIELDS <= options.keys():
            raise ValueError('Incomplete generation/portfolio options')
        if not {f.name for f in fields(SlateConfig)} <= payload['resolved_config'].keys():
            raise ValueError('Incomplete resolved scoring configuration')
        for key, schema in (('stack_rules', StackRules), ('tag_thresholds', TagThresholds),
                            ('objective_weights', ObjectiveWeights), ('tag_caps', LineupTagCaps),
                            ('portfolio_targets', PortfolioTargets)):
            if not {f.name for f in fields(schema)} <= payload['resolved_config'][key].keys():
                raise ValueError(f'Incomplete resolved scoring configuration: {key}')
        ids = [str(p['player_id']) for p in payload['players']]
        if not ids or len(ids) != len(set(ids)) or sorted(ids) != sorted(payload['eligible_player_ids']):
            raise ValueError('Canonical player identities incomplete or duplicated')
        required = {f.name for f in fields(Player)}
        if any(not required <= p.keys() or 'final_score' in p for p in payload['players']):
            raise ValueError('Incomplete frozen player solver frame')
        if not payload.get('pool_rows') or not payload.get('source_pool_rows'):
            raise ValueError('Frozen eligibility/availability source frame absent')
        def check_times(value: Any) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    if (key == 'observed_at' or key.endswith('_observed_at')) and item not in (None, '', 'NaT') and timestamp(item) > cutoff:
                        raise ValueError(f'Observation after decision: {key}')
                    check_times(item)
            elif isinstance(value, list):
                for item in value:
                    check_times(item)
        check_times(payload)
        return {'qualified': True, 'reason': 'original_frozen_inputs_verified',
                'input_sha256': snapshot['sha256'], 'replayed_as_of': as_of}
    except (KeyError, TypeError, ValueError) as exc:
        return {'qualified': False, 'reason': str(exc)}


def freeze_pregame(path: Path, payload: dict, *, frozen_at: str) -> dict:
    """Exclusive creation: later actuals are a separate artifact referencing this."""
    import json
    timestamp(frozen_at)
    # Solver diagnostics can use integer keys. Hash the JSON representation that
    # will actually be persisted, so reloading those keys as strings stays stable.
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'Duplicate serialized JSON key: {key}')
            result[key] = value
        return result
    payload = json.loads(json.dumps(payload, allow_nan=False), object_pairs_hook=unique_object)
    forbid_outcomes(payload)
    if set(payload['expanded_targets']) != {str(t) for t in TARGETS}:
        raise ValueError('All four admitted targets required')
    if not payload.get('input_sha256') or 'old' not in payload or 'full_expanded' not in payload:
        raise ValueError('Both frozen comparison arms and input hash required')
    envelope = {'contract': 'classic_discovery_pregame_comparison_v1',
                'frozen_at': frozen_at, 'payload': payload}
    envelope['sha256'] = digest_payload(envelope)
    with path.open('x') as stream:
        json.dump(envelope, stream, sort_keys=True, indent=2)
        stream.write('\n')
    return envelope


def attach_postgame(path: Path, load_actuals: Callable[[], dict], *, attached_at: str) -> dict:
    """Read and verify the persisted pregame artifact before accepting outcomes."""
    import json
    envelope = json.loads(path.read_text())
    unsigned = {k: v for k, v in envelope.items() if k != 'sha256'}
    if envelope['sha256'] != digest_payload(unsigned):
        raise ValueError('Persisted pregame artifact changed')
    if envelope.get('contract') != 'classic_discovery_pregame_comparison_v1':
        raise ValueError('Pregame comparison contract missing')
    if timestamp(attached_at) <= timestamp(envelope['frozen_at']):
        raise ValueError('Actuals must be attached after pregame output freeze')
    if timestamp(attached_at) < timestamp(envelope['payload']['kickoff_at']):
        raise ValueError('Actuals cannot be attached before lock')
    actuals = load_actuals()
    return {'pregame_sha256': envelope['sha256'], 'attached_at': attached_at,
            'actuals_sha256': digest_payload(actuals), 'actuals': actuals}


def chronological_split(rows: list[dict], *, minimum: int = 6) -> dict:
    qualified = [r for r in rows if r['qualified']]
    keys = [r['slate_key'] for r in qualified]
    if len(keys) != len(set(keys)):
        raise ValueError('Refreshes of a slate are not independent observations')
    ordered = sorted(qualified, key=lambda r: (timestamp(r['kickoff_at']), r['slate_key']))
    if len(ordered) < minimum:
        return {'status': 'insufficient_independent_slates', 'development': [], 'holdout': [],
                'qualified_count': len(ordered), 'minimum': minimum}
    split = len(ordered) - max(1, len(ordered) // 3)
    return {'status': 'chronological', 'development': ordered[:split], 'holdout': ordered[split:]}


def verify_old_replay(saved: list[dict], replayed: list[dict]) -> dict:
    """Canonical roster order and exact saved selector, including admission ties."""
    if not saved or any(not isfinite(r['objective_score']) for r in saved + replayed):
        raise ValueError('Old replay requires nonempty finite-scored control')
    if list(map(roster_key, saved)) != list(map(roster_key, replayed)):
        raise ValueError('Old pipeline replay changed roster membership or order')
    if any(abs(a['objective_score'] - b['objective_score']) > 1e-9 for a, b in zip(saved, replayed)):
        raise ValueError('Old pipeline replay changed selector scores')
    return {'status': 'identical', 'count': len(saved), 'roster_score_sha256': digest_payload([
        {'roster': roster_key(r), 'selector': r['objective_score']} for r in saved])}


def portfolio_match(selected: list[dict] | None, full: list[dict] | None) -> dict:
    if not selected or not full or len(selected) != len(full):
        return {'status': 'infeasible_or_unavailable', 'exact': None, 'structural': None,
                'quality_equivalent': {str(t): None for t in (.01, .05, .10)}}
    def structure(rows: list[dict]) -> tuple:
        return tuple(tuple(sorted(Counter(str(r[key]) if key != 'qb' else
                       str(r['qb']['player_id']) for r in rows).items()))
                     for key in ('qb', 'game_key', 'family_key'))
    gap = sum(r['objective_score'] for r in full) - sum(r['objective_score'] for r in selected)
    return {'status': 'available', 'exact': sorted(map(roster_key, selected)) == sorted(map(roster_key, full)),
            'structural': structure(selected) == structure(full), 'selector_gap': gap,
            'quality_equivalent': {str(t): abs(gap) <= t + 1e-9 for t in (.01, .05, .10)}}


def runtime_summary(values: list[float | None]) -> dict:
    observed = [v for v in values if v is not None]
    if any(v < 0 for v in observed):
        raise ValueError('Negative runtime')
    return {'measured_count': len(observed), 'missing_count': len(values) - len(observed),
            'mean': mean(observed) if observed else None,
            'median': median(observed) if observed else None,
            'max': max(observed) if observed else None}


def source_contribution(events: list[dict], *, frontier: float,
                        five: list[dict], twenty: list[dict],
                        baseline: tuple[dict, ...] = ()) -> dict:
    """Marginal first-discovery credit in persisted event order, never double count.

    A duplicated roster contributes a solve to later sources but no new roster.
    Alternative overlap-credit ablations are needed before pruning any source.
    """
    result = {}
    seen = set(map(roster_key, baseline))
    players = {pid for r in baseline for pid in r['player_ids']}
    qbs = {r['qb']['player_id'] for r in baseline}
    families = {r['family_key'] for r in baseline}
    selected5, selected20 = set(map(roster_key, five)), set(map(roster_key, twenty))
    for event in events:
        row = result.setdefault(event['source'], dict(solves=0, unique_candidates=0,
            within_020=0, new_players=0, new_qbs=0, new_families=0, selected5=0, selected20=0))
        row['solves'] += 1
        if event['status'] != 'optimal' or not event.get('player_ids'):
            continue
        key = roster_key(event)
        if key in seen:
            continue
        seen.add(key)
        row['unique_candidates'] += 1
        row['within_020'] += event['objective_score'] >= frontier - .20 - 1e-9
        row['new_players'] += len(set(key) - players)
        qb, family = event['qb']['player_id'], event['family_key']
        row['new_qbs'] += qb not in qbs
        row['new_families'] += family not in families
        row['selected5'] += key in selected5
        row['selected20'] += key in selected20
        players.update(key)
        qbs.add(qb)
        families.add(family)
    return result
