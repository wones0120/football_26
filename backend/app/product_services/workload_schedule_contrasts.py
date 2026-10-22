"""Observed official workload associations with native rest and roof context."""
from copy import deepcopy
import math
from .evaluation_record import digest
from .workload_venue_splits import build_workload_venue_splits, CHANNELS

VERSION = 'observed_workload_schedule_contrasts_v1'
DEFINITIONS = {
    'G21-M05': dict(positive='short_rest_fewer_than_7_reported_days', negative='standard_rest_at_least_7_reported_days'),
    'G21-M07': dict(positive='sheltered_source_dome_or_closed', negative='exposed_source_outdoors_or_open')}


def build_workload_schedule_contrasts(weekly, schedule, *, before_period):
    # Reuse the strict native identity, period, source and official count boundary.
    base = build_workload_venue_splits(weekly, schedule, before_period=before_period)
    contexts = {}
    for game in schedule['game_rows']:
        if game['game_type'] != 'REG' or game['season'] * 100 + game['week'] >= before_period:
            continue
        roof = game.get('source_roof')
        sheltered = True if roof in {'dome', 'closed'} else False if roof in {'outdoors', 'open'} else None
        for teamrow in game['team_rows']:
            rest = teamrow['metrics']['G20-M09']['value']
            if rest is not None and (type(rest) not in {int, float} or not math.isfinite(rest)
                                     or rest < 0 or rest != int(rest)):
                raise ValueError('Known native rest requires nonnegative integer days')
            contexts[(game['game_id'], teamrow['team'])] = dict(
                rest_days=rest, source_roof=roof,
                groups={'G21-M05': rest < 7 if rest is not None else None, 'G21-M07': sheltered})
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
                        limitations=base['limitations'] + ['Rest threshold is declared, not fitted; no causal workload adjustment',
                                                          'Roof is revised native schedule state, not a pregame forecast',
                                                          'Unknown context cannot be assigned to either comparison cohort'])
