"""Observed workload in games reported started by a future target's listed QB.

No pass-volume starter inference or claim of confirmed future participation.
"""
from copy import deepcopy
from datetime import datetime, UTC
from pathlib import Path
from zoneinfo import ZoneInfo
import csv
import re
from .evaluation_record import digest
from .factual_designation import clock
from .schedule_context_features import load_schedule_context
from .workload_venue_splits import build_workload_venue_splits, CHANNELS
from .market_snapshots import canonical_team

VERSION = 'observed_workload_starting_qb_context_v1'
SOURCE_VERSION = 'native_reported_starting_qb_context_v1'


def _native(value):
    return value if isinstance(value, str) and re.fullmatch(r'00-\d{7}', value) and int(value[3:]) > 0 else None


def _kickoff(day, time):
    try:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(day)) or not re.fullmatch(r'\d{2}:\d{2}', str(time)):
            return None
        local = datetime.strptime(f'{day} {time}', '%Y-%m-%d %H:%M')
        ny = ZoneInfo('America/New_York'); aware = local.replace(tzinfo=ny)
        # Do not guess ambiguous/nonexistent local times.
        if local.replace(tzinfo=ny, fold=0).utcoffset() != local.replace(tzinfo=ny, fold=1).utcoffset(): return None
        if aware.astimezone(UTC).astimezone(ny).replace(tzinfo=None) != local: return None
        return aware.astimezone(UTC).isoformat()
    except (ValueError, TypeError):
        return None


def normalize_starting_qb_context(records, schedule):
    games = {r['game_id']: r for r in schedule['game_rows']}; rows = []; seen = set()
    for raw in records:
        gid = raw['game_id']; game = games.get(gid)
        if game is None or gid in seen: raise ValueError('Unique authenticated native game required')
        seen.add(gid)
        if (str(raw['season']) != str(game['season']) or str(raw['week']) != str(game['week'])
                or raw['game_type'] != game['game_type']
                or canonical_team(raw['home_team']) != game['home_team']
                or canonical_team(raw['away_team']) != game['away_team']):
            raise ValueError('Native starter source scope/orientation differs')
        if game['game_type'] != 'REG': continue
        kickoff = _kickoff(raw.get('gameday'), raw.get('gametime'))
        for side in ('home', 'away'):
            original = raw.get(side + '_qb_id')
            rows.append(dict(game_id=gid, season=game['season'], week=game['week'], team=game[side + '_team'],
                             source_starter_native_id=_native(original), original_source_qb_id=original,
                             identity_status='native_GSIS_reported' if _native(original) else 'unknown_or_invalid_native_id',
                             source_game_date=raw.get('gameday'), source_gametime_Eastern=raw.get('gametime'),
                             native_kickoff_at=kickoff))
    if seen != set(games): raise ValueError('Starter source does not cover authenticated schedule rows')
    rows.sort(key=lambda r: (r['game_id'], r['team']))
    basis = dict(version=SOURCE_VERSION, rows=rows,
                 role_scope='Provider-reported starting QB identity; future identities are unconfirmed, not active/healthy/full-role proof')
    return basis | dict(semantic_sha256=digest(basis), provenance=deepcopy(schedule['provenance']),
                        evidence_use='postlock_descriptive_not_pregame_or_serving', pregame_serving_eligible=False)


def load_starting_qb_context(snapshot, *, cutoff):
    schedule = load_schedule_context(snapshot, cutoff=cutoff)
    with Path(snapshot.artifact_path).open(newline='') as stream:
        reader = csv.DictReader(stream)
        required = {'game_id', 'season', 'week', 'game_type', 'home_team', 'away_team', 'gameday', 'gametime', 'home_qb_id', 'away_qb_id'}
        if not required.issubset(reader.fieldnames or []): raise ValueError('Native starting QB/clock fields unavailable')
        result = normalize_starting_qb_context(reader, schedule)
    return schedule, result


def build_workload_starting_qb_context(weekly, schedule, starters, *, before_period, target_game_ids, cutoff):
    base = build_workload_venue_splits(weekly, schedule, before_period=before_period)
    if starters.get('version') != SOURCE_VERSION or starters.get('pregame_serving_eligible') is not False:
        raise ValueError('Explicit nonserving native starter context required')
    decision = clock(cutoff)
    if decision is None or decision > datetime.now(UTC): raise ValueError('Actual nonfuture feature cutoff required')
    if starters.get('semantic_sha256') != digest({k: starters[k] for k in ('version', 'rows', 'role_scope')}):
        raise ValueError('Native starter context semantic checksum differs')
    if any(starters['provenance'].get(k) != schedule['provenance'].get(k) for k in ('snapshot_id', 'sha256')):
        raise ValueError('Starter/schedule immutable source pairing differs')
    derived = clock(weekly['provenance'].get('actual_derived_at'))
    if derived is None or derived > decision: raise ValueError('Weekly feature source unavailable at cutoff')
    for field in ('observed_at', 'captured_at'):
        if clock(starters['provenance'].get(field)) is None or clock(starters['provenance'][field]) > decision:
            raise ValueError('Starter source unavailable at feature cutoff')
    if clock(starters['provenance']['observed_at']) > clock(starters['provenance']['captured_at']):
        raise ValueError('Starter source observation/capture chronology differs')
    lookup = {}; by_native = {}; games = {g['game_id']: g for g in schedule['game_rows']}
    for row in weekly['rows']: by_native.setdefault(row['source_player_id'], set()).add(row['player_master_id'])
    for row in starters['rows']:
        game = games.get(row['game_id'])
        if game is None or (row['season'], row['week']) != (game['season'], game['week']) or row['team'] not in {game['home_team'], game['away_team']}:
            raise ValueError('Starter row differs from authenticated native schedule')
        if row['native_kickoff_at'] != _kickoff(row['source_game_date'], row['source_gametime_Eastern']):
            raise ValueError('Native kickoff clock differs from source fields')
        if row['source_starter_native_id'] != _native(row['original_source_qb_id']):
            raise ValueError('Native QB identity differs from original source')
        key = (row['game_id'], row['team'])
        if key in lookup: raise ValueError('Duplicate native starter game/team')
        if row['source_starter_native_id'] is not None and _native(row['source_starter_native_id']) != row['source_starter_native_id']:
            raise ValueError('Native starter identity malformed')
        lookup[key] = row
    expected = {(g['game_id'], team) for g in games.values() if g['game_type'] == 'REG' for team in (g['home_team'], g['away_team'])}
    if set(lookup) != expected: raise ValueError('Native starter game/team universe is incomplete')
    requested = list(target_game_ids)
    if not requested or len(requested) != len(set(requested)): raise ValueError('Explicit unique target games required')
    target_rows = [r for r in starters['rows'] if r['game_id'] in requested]
    if {r['game_id'] for r in target_rows} != set(requested): raise ValueError('Target absent from authenticated native source')
    rows = []; requests = []
    for target in target_rows:
        if target['season'] * 100 + target['week'] != before_period:
            raise ValueError('Target game period differs from feature boundary')
        kickoff = clock(target['native_kickoff_at']) if target['native_kickoff_at'] else None
        if kickoff is None or kickoff <= decision:
            raise ValueError('Postgame/unknown-time target QB cannot be reconstructed as current pregame identity')
        native_qb = target['source_starter_native_id']; qb_ids = by_native.get(native_qb, set())
        canonical_qb = next(iter(qb_ids)) if len(qb_ids) == 1 else None
        if native_qb and canonical_qb is None:
            requests.append(dict(source_player_id=native_qb, team=target['team'], game_id=target['game_id'],
                                 reason='Target native QB has no unique canonical attachment in frozen weekly source'))
        for actor in base['rows']:
            if actor['season'] != target['season'] or actor['team'] != target['team']: continue
            logs = []
            for log in actor['logs']:
                historical = lookup.get((log['native_game_id'], actor['team']))
                historical_qb = historical['source_starter_native_id'] if historical else None
                group = historical_qb == native_qb if historical_qb is not None and native_qb is not None else None
                logs.append(deepcopy(log) | dict(historical_reported_starter_native_id=historical_qb, matches_target_starter=group))
            unknown = sum(r['matches_target_starter'] is None for r in logs)
            metrics = {}
            for channel in CHANNELS:
                groups = {}
                for match, label in ((True, 'with_reported_target_starter'), (False, 'other_reported_starter')):
                    sample = [r for r in logs if r['matches_target_starter'] is match]
                    missing = sum(r['counts'][channel] is None for r in sample)
                    total = sum(r['counts'][channel] for r in sample) if sample and not missing else None
                    mean = total / len(sample) if total is not None and not unknown and not actor['native_team_scope_unknown'] else None
                    groups[label] = dict(observed_source_logs=len(sample), unknown_exposures=missing,
                                         matched_known_sum=total, exact_per_observed_log=mean)
                a, b = (groups[k]['exact_per_observed_log'] for k in ('with_reported_target_starter', 'other_reported_starter'))
                metrics[channel] = groups | dict(with_minus_other=a-b if a is not None and b is not None else None,
                                                  unit='official_opportunities_per_observed_source_log')
            rows.append({k: deepcopy(actor[k]) for k in ('season', 'team', 'source_player_id', 'player_master_id')}
                        | dict(target_game_id=target['game_id'], target_qb_source_player_id=native_qb,
                               target_qb_player_master_id=canonical_qb, target_role_status='source_reported_unconfirmed_not_healthy_or_full_role_proof',
                               target_native_kickoff_at=target['native_kickoff_at'], unknown_historical_starter_logs=unknown,
                               metrics=metrics, logs=logs))
    semantic_rows = [{**r, 'logs': [{k:v for k,v in log.items() if k != 'source_ref'} for log in r['logs']]} for r in rows]
    basis = dict(version=VERSION, candidate_id='G21-M10', before_period=before_period,
                 definition='Observed same-season/team workload in games reported started by future target source-listed QB; no pass-play attribution or future-role guarantee', rows=semantic_rows)
    return basis | dict(rows=rows, semantic_sha256=digest(basis), provenance=dict(weekly=deepcopy(weekly['provenance']), starter_context=deepcopy(starters['provenance'])),
                        identity_review_requests=deepcopy(weekly['identity_review_requests']) + requests,
                        evidence_use='postlock_descriptive_not_pregame_or_serving', pregame_serving_eligible=False, forecast=None,
                        models_or_optimizer_consumed=False,
                        limitations=base['limitations'] + ['Reported historical starter is a whole-game context; backups may also play, not every opportunity came from that QB',
                                                          'Future listed QB is a conditional source identity, not confirmed dressing/health or a full-game role probability',
                                                          'No pregame target identity reconstructed from postgame source; native future kickoff must exceed actual cutoff',
                                                          'Revised historical starter publication chronology is unknown; no training/serving promotion'])


def require_feature_use(block, *, purpose):
    if block.get('version') != VERSION or purpose != 'offline_descriptive' or block.get('pregame_serving_eligible') is not False:
        raise ValueError('Descriptive starter workload contexts cannot serve forecasts/models/optimizer')
    return block
