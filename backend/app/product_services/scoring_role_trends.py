"""Observed scoring-zone opportunity-share changes, never a TD-rate proxy."""
from copy import deepcopy
from uuid import UUID
import math
from .evaluation_record import digest
from .market_snapshots import canonical_team
from .player_scoring_zone_components import VERSION as SOURCE_VERSION, DEFINITIONS

VERSION = 'observed_scoring_zone_role_trends_v1'
# Disjoint source line-of-scrimmage zones and separate physical channels.
METRICS = {mid: d for mid, d in DEFINITIONS.items() if d.get('zone') in {'six_to_twenty', 'inside5'}}


def _count(value):
    if value is not None and (type(value) not in {int, float} or not math.isfinite(value)
                              or value < 0 or value != int(value)):
        raise ValueError('Nonnegative finite official zone count required')
    return value


def _period(game_id):
    parts = str(game_id).split('_')
    if len(parts) != 4:
        raise ValueError('Native game identity required')
    try:
        season, week = int(parts[0]), int(parts[1])
    except ValueError as e:
        raise ValueError('Native game period required') from e
    if not 2000 <= season or not 1 <= week <= 18:
        raise ValueError('Native REG game period required')
    return season, week


def build_scoring_role_trends(source, *, before_period):
    if (source.get('version') != SOURCE_VERSION or source.get('before_period') != before_period
            or source.get('evidence_use') != 'postlock_descriptive_not_pregame_or_serving'
            or source.get('pregame_serving_eligible') is not False):
        raise ValueError('Matched nonserving scoring-zone feature source required')
    if type(before_period) is not int or not 1 <= before_period % 100 <= 18:
        raise ValueError('Explicit REG period required')
    teams, windows = {}, {}
    for row in source['full_team_denominators']:
        season, week = _period(row['game_id']); team = canonical_team(row['team'])
        if season * 100 + week >= before_period:
            raise ValueError('Strict prior game required')
        if team not in {canonical_team(t) for t in row['game_id'].split('_')[2:]}:
            raise ValueError('Native game/team contradiction')
        key = (season, team, week)
        if key in teams:
            raise ValueError('Duplicate native team/week game')
        teams[key] = row
        windows.setdefault((season, team), []).append(week)
        for d in METRICS.values():
            _count(row['channels'][d['channel']][d['zone']]['exact_within_log_count'])
    actors, by_key = {}, {}
    canonical = {}
    for row in source['actor_game_rows']:
        season, week = _period(row['game_id']); team = canonical_team(row['team']); native = row['source_player_id']; pid = row['player_master_id']
        if (season, team, week) not in teams or teams[(season, team, week)]['game_id'] != row['game_id']:
            raise ValueError('Actor lacks matching native full-team denominator')
        if pid is not None and str(UUID(str(pid))) != pid:
            raise ValueError('Canonical UUID spelling required')
        key = (season, team, native, week)
        if key in by_key:
            raise ValueError('Duplicate native actor/game')
        by_key[key] = row
        actors.setdefault((season, team, native), set()).add(pid)
        if pid is not None:
            canonical.setdefault((season, pid), set()).add(native)
        for mid, d in METRICS.items():
            n = _count(row['metrics'].get(mid, {}).get('exact_within_log_count'))
            den = teams[(season, team, week)]['channels'][d['channel']][d['zone']]['exact_within_log_count']
            if n is not None and den is not None and n > den:
                raise ValueError('Actor zone count exceeds full team budget')
    if any(len(ids) > 1 for ids in actors.values()) or any(len(ids) > 1 for ids in canonical.values()):
        raise ValueError('Contradictory native/canonical identity history')
    output = []
    for (season, team, native), ids in sorted(actors.items()):
        weeks = sorted(windows[(season, team)])[-4:]
        latest, prior = weeks[-1], weeks[:-1]
        metrics = {}
        for mid, d in METRICS.items():
            def pair(week):
                row = by_key.get((season, team, native, week))
                n = row['metrics'].get(mid, {}).get('exact_within_log_count') if row else None
                den = teams[(season, team, week)]['channels'][d['channel']][d['zone']]['exact_within_log_count']
                return n, den
            n, den = pair(latest)
            latest_share = n / den if n is not None and den is not None and den > 0 else None
            reference = [pair(w) for w in prior]
            complete = len(reference) == 3 and all(a is not None and b is not None for a, b in reference)
            pn = sum(a for a, b in reference) if complete else None
            pd = sum(b for a, b in reference) if complete else None
            share = pn / pd if pn is not None and pd > 0 else None
            metrics[mid] = dict(channel=d['channel'], zone=d['zone'], unit='fraction_of_full_team_official_channel_zone_opportunities',
                                latest_actor_count=n, latest_full_team_count=den, latest_share=latest_share,
                                prior_actor_count=pn, prior_full_team_count=pd, prior_share=share,
                                share_change=latest_share - share if latest_share is not None and share is not None else None)
        output.append(dict(season=season, team=team, source_player_id=native, player_master_id=next(iter(ids)),
                           latest_week=latest, reference_weeks=prior, metrics=metrics))
    basis = dict(version=VERSION, candidate_id='G22-M06', before_period=before_period,
                 definition='Latest observed same-team log share minus pooled exactly3 preceding team logs; disjoint six-to-twenty/inside5 pass/rush/target shares separately',
                 actor_trends=output)
    return basis | dict(semantic_sha256=digest(basis), provenance=deepcopy(source.get('provenance', {})),
                        identity_review_requests=deepcopy(source['identity_review_requests']),
                        evidence_use=source['evidence_use'], pregame_serving_eligible=False, forecast=None,
                        models_or_optimizer_consumed=False,
                        limitations=['Missing actor/channel participation is unknown, not zero/DNP or a last-positive fallback',
                                     'Observed logs are not independently certified complete games',
                                     'Line-of-scrimmage opportunity zones, not end-zone targets or scoring likelihood',
                                     'Pass and target can describe one physical play; channels and zones are never added into a composite',
                                     'No TD-rate proxy, role forecast, replacement transfer or user-preference filtering'])
