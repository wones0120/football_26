"""Observed official workload splits with native schedule home/away binding."""
from collections import defaultdict
from copy import deepcopy
import math
from uuid import UUID
from .evaluation_record import digest
from .market_snapshots import canonical_team
from .schedule_context_features import VERSION as SCHEDULE_VERSION
from .weekly_effectiveness_catalog_features import VERSION as WEEKLY_VERSION

VERSION = 'observed_workload_venue_splits_v1'
CHANNELS = {'pass_attempts': 'G04-M01', 'rush_attempts': 'G07-M01', 'targets': 'G09-M01'}


def build_workload_venue_splits(weekly, schedule, *, before_period):
    if (weekly.get('version') != WEEKLY_VERSION or schedule.get('version') != SCHEDULE_VERSION
            or weekly.get('before_period') != before_period
            or any(s.get('pregame_serving_eligible') is not False for s in (weekly, schedule))):
        raise ValueError('Matched nonserving weekly/schedule sources required')
    if type(before_period) is not int or not 1 <= before_period % 100 <= 18:
        raise ValueError('Explicit REG period required')
    games = {}
    for game in schedule['game_rows']:
        if game['game_type'] != 'REG' or game['season'] * 100 + game['week'] >= before_period:
            continue
        home, away = canonical_team(game['home_team']), canonical_team(game['away_team'])
        if home == away:
            raise ValueError('Distinct native home/away teams required')
        for team, venue in ((home, 'home'), (away, 'away')):
            key = (game['season'], game['week'], team)
            if key in games:
                raise ValueError('Ambiguous native team/week schedule')
            games[key] = dict(native_game_id=game['game_id'], venue=venue)
    groups = defaultdict(list)
    unbound = []
    seen = set()
    native_ids = defaultdict(set)
    canonical_natives = defaultdict(set)
    unbound_natives = set()
    for row in weekly['rows']:
        season, week, native, team = (row[k] for k in ('season', 'week', 'source_player_id', 'team'))
        if (type(season) is not int or type(week) is not int or not 1 <= week <= 18
                or season * 100 + week >= before_period or row['season_type'] != 'REG'):
            raise ValueError('Strict prior REG weekly source required')
        pid = row['player_master_id']
        if pid is not None and str(UUID(str(pid))) != pid:
            raise ValueError('Canonical UUID spelling required')
        team = canonical_team(team) if team else None
        key = (season, week, native, team)
        if key in seen:
            raise ValueError('Duplicate native weekly scope')
        seen.add(key)
        native_ids[(season, native)].add(pid)
        if pid is not None:
            canonical_natives[(season, pid)].add(native)
        if team is None:
            unbound_natives.add((season, native))
        game = games.get((season, week, team))
        if not game:
            unbound.append(dict(season=season, week=week, source_player_id=native, team=team,
                                reason='Missing unique native schedule/team; venue unknown'))
        elif row['native_game_id'] not in (None, '', game['native_game_id']):
            raise ValueError('Weekly native game contradicts schedule')
        counts = {}
        for channel, mid in CHANNELS.items():
            count = row['metrics'].get(mid, {}).get('denominator')
            if count is not None and (type(count) not in {int, float} or not math.isfinite(count)
                                      or count < 0 or count != int(count)):
                raise ValueError('Nonnegative finite official exposure required')
            counts[channel] = count
        groups[(season, team, native)].append(dict(week=week, venue=game['venue'] if game else None,
                                                   native_game_id=game['native_game_id'] if game else None,
                                                   counts=counts, source_ref=deepcopy(row['source_ref'])))
    if any(len(ids) > 1 for ids in native_ids.values()) or any(len(ids) > 1 for ids in canonical_natives.values()):
        raise ValueError('Contradictory native canonical attachment')
    rows = []
    for (season, team, native), logs in sorted(groups.items(), key=lambda item: str(item[0])):
        logs.sort(key=lambda row: row['week'])
        metrics = {}
        for channel in CHANNELS:
            sides = {}
            for venue in ('home', 'away'):
                samples = [r for r in logs if r['venue'] == venue]
                missing = sum(r['counts'][channel] is None for r in samples)
                total = sum(r['counts'][channel] for r in samples) if samples and not missing else None
                sides[venue] = dict(observed_logs=len(samples), unknown_exposures=missing,
                                    exact_sum=total, per_observed_log=total / len(samples) if total is not None else None)
            h, a = sides['home']['per_observed_log'], sides['away']['per_observed_log']
            unbound_count = sum(r['venue'] is None for r in logs)
            difference = h - a if h is not None and a is not None and not unbound_count and (season, native) not in unbound_natives else None
            metrics[channel] = dict(unit='official_opportunities_per_observed_source_log',
                                    **sides, home_minus_away=difference, unknown_venue_logs=unbound_count)
        rows.append(dict(season=season, team=team, source_player_id=native,
                         player_master_id=next(iter(native_ids[(season, native)])), metrics=metrics, logs=logs,
                         native_team_scope_unknown=(season, native) in unbound_natives))
    semantic_rows = [{**r, 'logs': [{k: v for k, v in log.items() if k != 'source_ref'} for log in r['logs']]} for r in rows]
    basis = dict(version=VERSION, candidate_id='G21-M01', before_period=before_period,
                 definition='Same-season/team observed official workload per source log, home minus away; separate pass/rush/target units',
                 rows=semantic_rows, unbound_rows=unbound)
    return basis | dict(rows=rows, semantic_sha256=digest(basis),
                        source_semantic_hashes=dict(weekly=weekly['semantic_sha256'], schedule=schedule['semantic_sha256']),
                        provenance=dict(weekly=deepcopy(weekly['provenance']), schedule=deepcopy(schedule['provenance'])),
                        evidence_use='postlock_descriptive_not_pregame_or_serving', pregame_serving_eligible=False,
                        forecast=None, models_or_optimizer_consumed=False,
                        identity_review_requests=deepcopy(weekly['identity_review_requests']),
                        limitations=['Observed source logs only; missing scheduled player rows are not zero/DNP',
                                     'QB-only pass channel follows upstream explicit source position proof',
                                     'Official kneel/spike/scramble statistics retained; no causal venue effect',
                                     'Missing exposure or venue masks exact comparisons; no cross-team/season pooling'])
