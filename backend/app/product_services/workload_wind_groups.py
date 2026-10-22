"""Observed official workload contrasts across reported historical wind groups."""
from copy import deepcopy
import math
from .evaluation_record import digest
from .workload_venue_splits import build_workload_venue_splits, CHANNELS

VERSION = 'observed_workload_wind_groups_v1'
DEFINITIONS = {'G21-M08': dict(positive='source_wind_mph_at_least_15', negative='source_wind_mph_below_15')}

def build_workload_wind_groups(weekly, schedule, *, before_period):
    # Reuse the strict native identity, period, source and official count boundary.
    base = build_workload_venue_splits(weekly, schedule, before_period=before_period)
    contexts = {}
    for game in schedule['game_rows']:
        if game['game_type'] != 'REG' or game['season'] * 100 + game['week'] >= before_period:
            continue
        for teamrow in game['team_rows']:
            metric = teamrow['metrics'].get('G20-M05', {})
            if metric.get('unit') != 'source_wind_mph':
                raise ValueError('Explicit source wind mph unit required')
            wind = metric.get('value')
            if wind is not None and (type(wind) not in {int, float} or not math.isfinite(wind) or wind < 0):
                raise ValueError('Known source wind requires finite nonnegative mph')
            contexts[(game['game_id'], teamrow['team'])] = dict(
                source_wind_mph=wind, groups={'G21-M08': wind >= 15 if wind is not None else None})
    rows = []
    for actor in base['rows']:
        logs = []
        for log in actor['logs']:
            context = contexts.get((log['native_game_id'], actor['team']))
            logs.append(deepcopy(log) | dict(context=context))
        metrics = {}
        for mid in DEFINITIONS:
            unknown_context = sum(r['context'] is None or r['context']['groups'][mid] is None for r in logs)
            channels = {}
            for channel in CHANNELS:
                sides = {}
                for group, label in ((True, 'positive'), (False, 'negative')):
                    sample = [r for r in logs if r['context'] is not None and r['context']['groups'][mid] is group]
                    unknown = sum(r['counts'][channel] is None for r in sample)
                    total = sum(r['counts'][channel] for r in sample) if sample and not unknown else None
                    sides[label] = dict(observed_logs=len(sample), unknown_exposures=unknown,
                                        exact_sum=total, per_observed_log=total / len(sample) if total is not None else None)
                positive, negative = sides['positive']['per_observed_log'], sides['negative']['per_observed_log']
                delta = positive - negative if (positive is not None and negative is not None
                                                and not unknown_context and not actor['native_team_scope_unknown']) else None
                channels[channel] = dict(**sides, positive_minus_negative=delta,
                                         unit='official_opportunities_per_observed_source_log')
            metrics[mid] = dict(channels=channels, unknown_context_logs=unknown_context)
        rows.append({k: deepcopy(actor[k]) for k in ('season', 'team', 'source_player_id', 'player_master_id', 'native_team_scope_unknown')}
                    | dict(metrics=metrics, logs=logs))
    semantic_rows = [{**r, 'logs': [{k: v for k, v in log.items() if k != 'source_ref'} for log in r['logs']]} for r in rows]
    basis = dict(version=VERSION, before_period=before_period, definitions=DEFINITIONS, rows=semantic_rows)
    return basis | dict(rows=rows, semantic_sha256=digest(basis),
                        source_semantic_hashes=deepcopy(base['source_semantic_hashes']), provenance=deepcopy(base['provenance']),
                        identity_review_requests=deepcopy(base['identity_review_requests']),
                        evidence_use=base['evidence_use'], pregame_serving_eligible=False, forecast=None,
                        models_or_optimizer_consumed=False,
                        limitations=base['limitations'] + ['Wind threshold15mph is predeclared, not fitted; no causal workload adjustment',
                                                          'Wind is revised reported historical schedule observation, not a pregame forecast; averaging interval unknown',
                                                          'Unknown context cannot be assigned to either comparison cohort'])
