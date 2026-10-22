"""Exact catalog efficiency definitions; preserve the earlier measured variants."""
from copy import deepcopy
from datetime import datetime, UTC
from pathlib import Path
import hashlib
from .official_efficiency_features import build_official_efficiency, DEFINITIONS as VARIANT_DEFINITIONS, _counter
from .opportunity_events import validate_event_evidence
from .player_opportunity_components import _condition
from .player_effectiveness_components import _record
from .defense_context_evidence import _finish, _hash
from .environment_context_evidence import _and
from .official_workload_components import _or
from .opportunity_events import _flag

VERSION = 'official_inclusive_efficiency_catalog_v1'
DEFINITIONS = deepcopy(VARIANT_DEFINITIONS)
DEFINITIONS.update({
    'G04-M09': ('dropback', 'source_sacks_per_official_dropback_including_spikes', 'fraction'),
    'G05-M06': ('rush', 'source_epa_positive_per_official_QB_carry_including_kneels', 'fraction'),
    'G07-M02': ('rush', 'sum_source_epa_over_official_carries_including_kneels', 'provider_expected_points_total'),
    'G07-M06': ('rush', 'source_first_down_or_rush_TD_per_official_third_or_fourth_down_carry', 'fraction')})


def build_official_efficiency_catalog(parent, *, before_period, cutoff, position_evidence=()):
    result = build_official_efficiency(parent, before_period=before_period, cutoff=cutoff, position_evidence=position_evidence)
    result['underlying_variant_semantic_sha256'] = result.pop('semantic_measurements_sha256')
    rows = {(r['game_id'], r['team'], r['source_player_id']): r for r in result['actor_game_rows']}
    teams, actors, missing = {}, {}, []
    evidence = validate_event_evidence(parent['event_evidence'], before_period=before_period, cutoff=cutoff)
    for event in evidence['events']:
        raw = event['raw_flags']; key = (event['game_id'], event['team'])
        channel = True if any(o['channel'] == 'rush_attempts' for o in event['opportunities']) else None if 'rush_attempts' in event['unknown_channels'] else False
        # Conversion opportunities are explicitly third/fourth-down official carries.
        eligible = _and(channel, _condition(raw.get('down'), lambda n: n in {3, 4}, lambda n: n in {1, 2, 3, 4}))
        if event['status'] in {'excluded', 'not_applicable'}: eligible = False
        elif event['status'] == 'unknown': eligible = _and(None, _condition(raw.get('down'), lambda n: n in {3, 4}, lambda n: n in {1, 2, 3, 4}))
        converted = _or(_flag(raw.get('first_down_rush')), _flag(raw.get('rush_touchdown')))
        value = None if converted is None else float(converted)
        native = raw.get('rusher_player_id')
        counter = teams.setdefault(key, _counter()); _record(counter, eligible, value)
        if eligible is True and not native: counter['unattributed_eligible_events'] += 1
        if eligible is None and not native: counter['unattributed_unknown_eligibility_events'] += 1
        if eligible is False: continue
        if not native:
            missing.append(dict(game_id=key[0], team=key[1], play_id=event['play_id'], eligibility=eligible))
            continue
        actor_key = (*key, str(native))
        if actor_key not in rows: raise ValueError('Conversion actor absent from validated source universe')
        _record(actors.setdefault(actor_key, _counter()), eligible, value)
    for key, row in rows.items():
        metrics = row['metrics']; variants = {}
        if 'G04-M09' in metrics:
            old = deepcopy(metrics['G04-M09']); variants['sack_avoidance_per_official_dropback'] = old
            m = metrics['G04-M09']
            m['observed_outcome_sum'] = old['known_outcome_events'] - old['observed_outcome_sum'] if old['observed_outcome_sum'] is not None else None
            rate = m['observed_outcome_sum'] / old['known_outcome_events'] if old['known_outcome_events'] else None
            m['known_attributed_sample_mean'] = rate
            m['exact_within_log_mean'] = rate if old['exact_within_log_mean'] is not None else None
        if 'G05-M06' in metrics:
            variants['QB_epa_per_official_carry'] = deepcopy(metrics['G05-M06'])
            metrics['G05-M06'] = deepcopy(metrics['G07-M03'])
        old = deepcopy(metrics['G07-M02']); variants['epa_per_official_carry'] = old
        exact = not (old['unknown_eligibility_events'] or old['unknown_outcome_events']
                     or old['inherited_unattributed_eligible_events'] or old['inherited_unattributed_unknown_eligibility_events'])
        total = old['observed_outcome_sum'] if exact and old['eligible_events'] else 0.0 if exact and not old['eligible_events'] else None
        metrics['G07-M02'].pop('exact_within_log_mean')
        metrics['G07-M02']['exact_within_log_total'] = total
        variants['first_down_or_TD_fraction_all_official_carries'] = deepcopy(metrics['G07-M06'])
        team = teams[key[:2]]; counter = actors.get(key, _counter()); conversion = _finish(counter)
        conversion['known_attributed_sample_mean'] = conversion.pop('observed_known_mean')
        all_eligible = conversion.pop('all_eligible_mean')
        conversion['exact_within_log_mean'] = all_eligible if not (team['unattributed_eligible_events'] or team['unattributed_unknown_eligibility_events']) else None
        conversion['inherited_unattributed_eligible_events'] = team['unattributed_eligible_events']
        conversion['inherited_unattributed_unknown_eligibility_events'] = team['unattributed_unknown_eligibility_events']
        metrics['G07-M06'] = conversion
        for mid, m in metrics.items():
            m.update(definition=DEFINITIONS[mid][1], unit=DEFINITIONS[mid][2])
            m['value'] = m.get('exact_within_log_total') if mid == 'G07-M02' else m['exact_within_log_mean']
        row['preserved_measured_variants'] = variants
    result['version'] = VERSION; result['definitions'] = deepcopy(DEFINITIONS)
    result['full_team_source_measurements'] = result.pop('full_team_measurements')
    result['full_team_source_measurement_definitions'] = deepcopy(VARIANT_DEFINITIONS)
    result['full_team_source_measurement_scope'] = 'Preserved v1 all-source channel measurements; keys follow the variant definition map, not corrected actor catalog definitions'
    result['full_team_conversion_measurements'] = [dict(game_id=g, team=t, metrics=_finish(v)) for (g, t), v in sorted(teams.items())]
    result['unattributed_conversion_events'] = missing
    result['limitations'] += ['Exact catalog includes sack RATE, QB EPA-positive SUCCESS and rushing EPA TOTAL; earlier contrary variants are separate',
                              'First-down conversion denominator is explicitly third/fourth-down official carries, not all carries',
                              'Zero official carry exposure has zero within-log EPA sum only when eligibility/attribution are fully known; rates remain undefined']
    basis = {k: result[k] for k in ('version', 'before_period', 'definitions', 'actor_game_rows', 'full_team_source_measurements', 'full_team_source_measurement_definitions', 'full_team_source_measurement_scope', 'full_team_conversion_measurements')}
    result['semantic_measurements_sha256'] = _hash(basis)
    return result


def derive_retrospective_efficiency_catalog(parent_ref, snapshot, *, actual_read_at, position_evidence=(), directory=None):
    from .factual_designation import clock
    from .opportunity_source_capture import load_event_artifact
    original, actual, lock = clock(parent_ref['decision_cutoff_at']), clock(actual_read_at), clock(snapshot.slate_lock_at)
    if original is None or actual is None or lock is None or not original < lock <= actual <= datetime.now(UTC):
        raise ValueError('Explicit original prelock boundary and actual nonfuture postlock read required')
    parent = load_event_artifact(parent_ref, snapshot, before_period=parent_ref['before_period'], cutoff=original, directory=directory)
    proofs = deepcopy(list(position_evidence))
    result = build_official_efficiency_catalog(parent, before_period=parent_ref['before_period'], cutoff=actual, position_evidence=proofs)
    result.update(evidence_use='postlock_descriptive_not_pregame_or_serving', pregame_serving_eligible=False)
    result['provenance'] = dict(parent_artifact_ref=deepcopy(parent_ref), source=deepcopy(parent['event_evidence']['source']),
                               event_receipt_sha256=parent['event_evidence']['sha256'], original_position_evidence=proofs,
                               original_evidence_boundary_at=original.isoformat(), source_lock_at=lock.isoformat(),
                               actual_read_at=actual.isoformat(), actual_derived_at=datetime.now(UTC).isoformat(),
                               producer_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                               variant_producer_code_sha256=hashlib.sha256(Path(__file__).with_name('official_efficiency_features.py').read_bytes()).hexdigest())
    return result
