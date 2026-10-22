"""Prior observed weekly efficiency changes, with matched exposure cohorts."""
from copy import deepcopy
import math
from uuid import UUID
from .evaluation_record import digest
from .weekly_effectiveness_catalog_features import VERSION as SOURCE_VERSION, DEFINITIONS

VERSION = 'recent_observed_efficiency_trends_v1'
DEFINITION = ('Latest observed same-team REG log efficiency minus pooled efficiency of exactly '
              'three preceding observed team logs; separate official statistical ratio channels')


def _ratio(metric, numerator_field):
    n, d = metric['numerator'], metric['denominator']
    for value in (n, d):
        if value is not None and (type(value) not in {int, float} or not math.isfinite(value)):
            raise ValueError('Finite source ratio components required')
    if d is not None and (d < 0 or d != int(d)):
        raise ValueError('Nonnegative integer exposure required')
    if n is not None and 'yards' not in numerator_field and (n < 0 or n != int(n)):
        raise ValueError('Nonnegative count numerator required')
    value = n / d if n is not None and d is not None and d > 0 else None
    if metric['value'] != value:
        raise ValueError('Source ratio differs from matched numerator/denominator')
    return n, d, value


def build_recent_efficiency(source, *, before_period):
    if (source.get('version') != SOURCE_VERSION or source.get('before_period') != before_period
            or source.get('evidence_use') != 'postlock_descriptive_not_pregame_or_serving'
            or source.get('pregame_serving_eligible') is not False):
        raise ValueError('Matched nonserving weekly feature source required')
    if type(before_period) is not int or not 1 <= before_period % 100 <= 18:
        raise ValueError('Explicit REG period required')
    by_key, windows, actors = {}, {}, {}
    canonical = {}
    unbound_actor_seasons = set()
    for row in source['rows']:
        season, week, team, native = (row[k] for k in ('season', 'week', 'team', 'source_player_id'))
        if (type(season) is not int or type(week) is not int or not 1 <= week <= 18
                or season * 100 + week >= before_period or row['season_type'] != 'REG'):
            raise ValueError('Strict prior REG source required')
        pid = row['player_master_id']
        if pid is not None and str(UUID(str(pid))) != pid:
            raise ValueError('Canonical UUID spelling required')
        if team is None:
            unbound_actor_seasons.add((season, native))
            continue  # Unbound team cannot establish a same-team window; original queue retained.
        key = (season, team, native, week)
        if key in by_key:
            raise ValueError('Duplicate native actor/team/week')
        by_key[key] = row
        windows.setdefault((season, team), set()).add(week)
        actors.setdefault((season, team, native), set()).add(pid)
        if pid is not None:
            canonical.setdefault((season, pid), set()).add(native)
        for mid, definition in DEFINITIONS.items():
            if mid in row['metrics']:
                _ratio(row['metrics'][mid], definition[0])
    if any(len(ids) > 1 for ids in actors.values()) or any(len(ids) > 1 for ids in canonical.values()):
        raise ValueError('Contradictory actor attachment across source history')
    output = []
    for (season, team, native), ids in sorted(actors.items()):
        weeks = sorted(windows[(season, team)])[-4:]
        latest_week, prior_weeks = weeks[-1], weeks[:-1]
        latest = by_key.get((season, team, native, latest_week))
        prior = [by_key.get((season, team, native, w)) for w in prior_weeks]
        metrics = {}
        for mid, definition in DEFINITIONS.items():
            recent = latest['metrics'].get(mid) if latest else None
            reference = [r['metrics'].get(mid) if r else None for r in prior]
            complete = (season, native) not in unbound_actor_seasons and len(reference) == 3 and all(m is not None and m['numerator'] is not None
                                                       and m['denominator'] is not None for m in reference)
            n = sum(m['numerator'] for m in reference) if complete else None
            d = sum(m['denominator'] for m in reference) if complete else None
            rate = n / d if n is not None and d > 0 else None
            recent_value = recent['value'] if recent and (season, native) not in unbound_actor_seasons else None
            delta = recent_value - rate if recent_value is not None and rate is not None else None
            metrics[mid] = dict(unit=definition[2], latest_value=recent_value,
                                reference_numerator=n, reference_denominator=d, reference_value=rate,
                                change=delta, status='measured_change' if delta is not None else 'unknown_or_undefined',
                                known_reference_rows=sum(m is not None and m['numerator'] is not None
                                                         and m['denominator'] is not None for m in reference))
        output.append(dict(season=season, team=team, source_player_id=native, player_master_id=next(iter(ids)),
                           latest_week=latest_week, reference_weeks=prior_weeks, metrics=metrics,
                           native_team_scope_unknown=(season, native) in unbound_actor_seasons,
                           source_refs=[deepcopy(r['source_ref']) for r in [*prior, latest] if r]))
    semantic_rows = [{k: v for k, v in row.items() if k != 'source_refs'} for row in output]
    basis = dict(version=VERSION, candidate_id='G22-M03', before_period=before_period,
                 definition=DEFINITION, rows=semantic_rows)
    return basis | dict(rows=output, semantic_sha256=digest(basis),
                        source_semantic_sha256=source['semantic_sha256'], provenance=deepcopy(source['provenance']),
                        identity_review_requests=deepcopy(source['identity_review_requests']),
                        evidence_use=source['evidence_use'], pregame_serving_eligible=False,
                        forecast=None, models_or_optimizer_consumed=False,
                        limitations=['Observed team-log universe is not an independently complete NFL schedule',
                                     'Missing actor participation is unknown, never zero/DNP or last-positive fallback',
                                     'Pooled matched numerator/exposure, not unweighted mean of weekly rates',
                                     'No cross-team/season histories, forecasts or scalar composite of different units'])
