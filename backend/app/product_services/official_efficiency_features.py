"""Official-inclusive observed efficiency, preserving missing native attribution."""
from copy import deepcopy
from datetime import datetime, UTC
from .opportunity_events import validate_event_evidence, _flag
from .player_opportunity_components import build_player_opportunity_components
from .player_effectiveness_components import _record
from .defense_context_evidence import _metric, _finish, _number, _hash
from .environment_context_evidence import _and
from .official_workload_components import _or

VERSION = 'official_inclusive_efficiency_features_v1'
DEFINITIONS = {
    'G04-M06': ('dropback', 'source_epa_per_official_dropback_including_spikes', 'provider_expected_points_per_dropback'),
    'G04-M07': ('dropback', 'source_epa_positive_per_official_dropback_including_spikes', 'fraction'),
    'G04-M09': ('dropback', 'one_minus_source_sack_per_official_dropback_including_spikes', 'fraction'),
    'G05-M06': ('rush', 'source_epa_per_official_QB_carry_including_kneels', 'provider_expected_points_per_carry'),
    'G07-M02': ('rush', 'source_epa_per_official_carry_including_kneels', 'provider_expected_points_per_carry'),
    'G07-M03': ('rush', 'source_epa_positive_per_official_carry_including_kneels', 'fraction'),
    'G07-M04': ('rush', 'source_credited_rushing_yards_ge10_per_official_carry', 'fraction'),
    'G07-M05': ('rush', 'source_credited_rushing_yards_le0_per_official_carry', 'fraction'),
    'G07-M06': ('rush', 'source_rush_first_down_or_rush_TD_per_official_carry', 'fraction')}


def _counter():
    return _metric() | dict(unattributed_eligible_events=0, unattributed_unknown_eligibility_events=0)


def _outcome(value, predicate):
    return float(predicate(value)) if value is not None else None


def build_official_efficiency(event_receipt, *, before_period, cutoff, position_evidence=()):
    evidence = validate_event_evidence(event_receipt['event_evidence'], before_period=before_period, cutoff=cutoff)
    base = build_player_opportunity_components(event_receipt, before_period=before_period, cutoff=cutoff,
                                               position_evidence=position_evidence)
    actors = {(r['game_id'], r['team'], r['source_player_id']):
              {k: deepcopy(r[k]) for k in ('game_id', 'team', 'source_player_id', 'player_master_id', 'position', 'position_status')}
              | dict(counters={}) for r in base['actor_game_rows']}
    teams, missing = {}, []
    for event in evidence['events']:
        raw = event['raw_flags']; teamkey = (event['game_id'], event['team'])
        tm = teams.setdefault(teamkey, {})
        channels = {o['channel'] for o in event['opportunities']}
        passed = True if 'pass_attempts' in channels else None if 'pass_attempts' in event['unknown_channels'] else False
        rushed = True if 'rush_attempts' in channels else None if 'rush_attempts' in event['unknown_channels'] else False
        scramble = _and(rushed, _flag(raw.get('qb_scramble')))
        sack = _flag(raw.get('sack'))
        if event['status'] in {'excluded', 'not_applicable'}:
            dropback, rushed = False, False
        elif event['status'] == 'unknown':
            dropback, rushed = None, None
        else:
            dropback = _or(passed, sack, scramble)
        if (event['status'] not in {'excluded', 'not_applicable'} and _flag(raw.get('qb_scramble')) is True
                and raw.get('passer_player_id') and raw.get('rusher_player_id')
                and str(raw['passer_player_id']) != str(raw['rusher_player_id'])):
            raise ValueError('Scramble has contradictory native passer/rusher identity')
        passer = raw.get('passer_player_id') or (raw.get('rusher_player_id') if _flag(raw.get('qb_scramble')) is True else None)
        rusher = raw.get('rusher_player_id')
        epa, yards = _number(raw.get('epa')), _number(raw.get('rushing_yards'))
        converted = _or(_flag(raw.get('first_down_rush')), _flag(raw.get('rush_touchdown')))
        outcomes = {'G04-M06': epa, 'G04-M07': _outcome(epa, lambda n: n > 0),
                    'G04-M09': None if sack is None else float(not sack), 'G05-M06': epa,
                    'G07-M02': epa, 'G07-M03': _outcome(epa, lambda n: n > 0),
                    'G07-M04': _outcome(yards, lambda n: n >= 10),
                    'G07-M05': _outcome(yards, lambda n: n <= 0),
                    'G07-M06': None if converted is None else float(converted)}
        for mid, (family, _, _) in DEFINITIONS.items():
            eligible, native = (dropback, passer) if family == 'dropback' else (rushed, rusher)
            value = outcomes[mid]; counter = tm.setdefault(mid, _counter())
            _record(counter, eligible, value)
            if eligible is True and not native: counter['unattributed_eligible_events'] += 1
            if eligible is None and not native: counter['unattributed_unknown_eligibility_events'] += 1
            if eligible is False: continue
            if not native:
                missing.append(dict(game_id=event['game_id'], team=event['team'], play_id=event['play_id'], metric=mid, eligibility=eligible))
                continue
            key = (*teamkey, str(native))
            if key not in actors: raise ValueError('Native actor absent from validated source identity universe')
            actor = actors[key]
            if mid.startswith(('G04-', 'G05-')) and actor['position'] != 'QB': continue
            _record(actor['counters'].setdefault(mid, _counter()), eligible, value)
    rows = []
    for key, actor in sorted(actors.items()):
        metrics = {}
        for mid, (_, definition, unit) in DEFINITIONS.items():
            if mid.startswith(('G04-', 'G05-')) and actor['position'] != 'QB': continue
            counter = actor['counters'].get(mid, _counter()); team = teams[key[:2]][mid]
            inherited = team['unattributed_eligible_events'] + team['unattributed_unknown_eligibility_events']
            finished = _finish(counter)
            finished['known_attributed_sample_mean'] = finished.pop('observed_known_mean')
            all_eligible = finished.pop('all_eligible_mean')
            finished['exact_within_log_mean'] = all_eligible if not inherited else None
            finished.update(inherited_unattributed_eligible_events=team['unattributed_eligible_events'],
                            inherited_unattributed_unknown_eligibility_events=team['unattributed_unknown_eligibility_events'],
                            definition=definition, unit=unit)
            metrics[mid] = finished
        rows.append({k: deepcopy(v) for k, v in actor.items() if k != 'counters'} | dict(metrics=metrics))
    semantic_basis = dict(version=VERSION, before_period=before_period, definitions=DEFINITIONS,
                          actor_game_rows=rows, full_team_measurements=[dict(game_id=g, team=t, scope='all_source_channel_actors_not_QB_filtered', metrics={m: _finish(c) for m, c in values.items()}) for (g, t), values in sorted(teams.items())])
    return semantic_basis | dict(semantic_measurements_sha256=_hash(semantic_basis), identity_review_requests=deepcopy(base['identity_review_requests']),
                                  unattributed_events=missing, source_quality=deepcopy(base['source_quality']), forecast=None,
                                  limitations=['Official physical dropback is pass OR sack OR scramble once; spikes/kneels retained',
                                               'G04/G05 requires scoped source-proven QB position; generic passing is not role proof',
                                               'Credited native rusher yards, not team net/lateral yards, define explosive/stuffed outcomes',
                                               'Missing native actors mask exact per-actor means; known sample means stay separate',
                                               'Observed source logs are not independently certified complete games',
                                               'No causality, FP bonus, forecast or current-role inference'])


def derive_retrospective_official_efficiency(parent_ref, snapshot, *, actual_read_at, position_evidence=(), directory=None):
    """Explicit offline read; never a fresh pregame/current-serving intake."""
    from pathlib import Path
    import hashlib
    from .factual_designation import clock
    from .opportunity_source_capture import load_event_artifact
    original, actual, lock = clock(parent_ref['decision_cutoff_at']), clock(actual_read_at), clock(snapshot.slate_lock_at)
    if original is None or lock is None or actual is None or not original < lock <= actual <= datetime.now(UTC):
        raise ValueError('Retrospective reader requires original prelock boundary and actual nonfuture postlock read')
    parent = load_event_artifact(parent_ref, snapshot, before_period=parent_ref['before_period'], cutoff=original, directory=directory)
    proofs = deepcopy(list(position_evidence))
    result = build_official_efficiency(parent, before_period=parent_ref['before_period'], cutoff=actual, position_evidence=proofs)
    result['underlying_measurements_sha256'] = result.pop('semantic_measurements_sha256')
    result.update(evidence_use='postlock_descriptive_not_pregame_or_serving', pregame_serving_eligible=False)
    result['provenance'] = dict(parent_artifact_ref=deepcopy(parent_ref), source=deepcopy(parent['event_evidence']['source']),
                               event_receipt_sha256=parent['event_evidence']['sha256'],
                               original_position_evidence=proofs, producer_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                               actual_read_at=actual.isoformat(), actual_derived_at=datetime.now(UTC).isoformat(),
                               original_evidence_boundary_at=original.isoformat(), source_lock_at=lock.isoformat(),
                               original_historical_availability='Unknown revised historical source; current read is explicitly postlock nonserving')
    result['semantic_measurements_sha256'] = _hash(dict(version=VERSION, before_period=parent_ref['before_period'],
                                                       definitions=DEFINITIONS, measurements=result['underlying_measurements_sha256']))
    return result


def require_official_efficiency_use(value, *, purpose):
    if (purpose != 'offline_descriptive' or value.get('evidence_use') != 'postlock_descriptive_not_pregame_or_serving'
            or value.get('pregame_serving_eligible') is not False):
        raise ValueError('Retrospective official efficiency cannot serve forecasts/scenarios/optimizer')
    return value
