"""Prior observed defensive context; measured samples, never forward forecasts.

The caller must load the immutable event parent through opportunity_source_capture.
An event checksum alone does not establish original historical availability or a
complete game. Each metric preserves its own eligibility and outcome missingness.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from .opportunity_events import validate_event_evidence, _flag
from .market_snapshots import canonical_team

VERSION = 'defense_context_evidence_v1'
DEFINITIONS = {
    'G14-M07': dict(variant='nonspike_official_pass_attempt_net20_v1', outcome='yards_gained >= 20', unit='observed_rate'),
    'dropback_epa_support': dict(variant='reported_nonspike_dropback_epa_support_v1', catalog_supports='G14-M09', outcome='source EPA; sacks and scrambles included', unit='expected_points_per_play'),
    'G14-M09': dict(variant='reported_nonspike_dropback_success_v1', outcome='epa > 0; sacks and scrambles included', unit='observed_rate'),
    'G15-M01': dict(variant='all_nonkneel_official_rush_success_v1', outcome='epa > 0; scrambles included', unit='observed_rate'),
    'G15-M02': dict(variant='all_nonkneel_official_rush_epa_v1', outcome='source epa; scrambles included', unit='expected_points_per_play'),
    'G15-M03': dict(variant='all_nonkneel_official_rush_net10_v1', outcome='yards_gained >= 10', unit='observed_rate'),
    'G15-M04': dict(variant='all_nonkneel_official_rush_stuff_v1', outcome='yards_gained <= 0', unit='observed_rate'),
    'G15-M09': dict(variant='inside5_all_nonkneel_official_rush_td_v1', outcome='rush_touchdown on preplay yardline_100 in [0,5]', unit='observed_rate'),
}


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _metric():
    return dict(eligible_events=0, unknown_eligibility_events=0, known_outcome_events=0,
                unknown_outcome_events=0, observed_outcome_sum=0.0)


def _finish(value):
    result = dict(value)
    n = result['known_outcome_events']
    result['observed_known_mean'] = result['observed_outcome_sum'] / n if n else None
    result['all_eligible_mean'] = result['observed_known_mean'] if not (
        result['unknown_outcome_events'] or result['unknown_eligibility_events']) else None
    result['observed_outcome_sum'] = result['observed_outcome_sum'] if n else None
    return result


def _eligibility(event):
    raw = event['raw_flags']
    if event['status'] in {'excluded', 'not_applicable'}:
        return False, False, False
    if event['status'] == 'unknown':
        return None, None, None
    channels = {o['channel'] for o in event['opportunities']}
    def without(channel, flag):
        if channel not in channels:
            return None if channel in event['unknown_channels'] else False
        excluded = _flag(raw.get(flag))
        return None if excluded is None else not excluded
    passing = without('pass_attempts', 'qb_spike')
    rushing = without('rush_attempts', 'qb_kneel')
    dropback = _flag(raw.get('qb_dropback'))
    if dropback is True:
        spike = _flag(raw.get('qb_spike'))
        dropback = None if spike is None else not spike
    return passing, dropback, rushing


def build_defense_context_evidence(event_receipt, *, before_period, cutoff, last_n_games=8):
    """Build per-game and trailing observed-game context from a verified intake.

    ``event_receipt`` is the outer receipt returned by load_event_artifact, not
    an arbitrary CSV or an FP-allowance table. Window games are observed logs;
    complete-game and historical publication proofs remain separately unknown.
    """
    if isinstance(last_n_games, bool) or not isinstance(last_n_games, int) or not 1 <= last_n_games <= 32:
        raise ValueError('Observed-game window must be an integer in [1,32]')
    evidence = validate_event_evidence(event_receipt['event_evidence'], before_period=before_period, cutoff=cutoff)
    games = {}; semantic_rows = []
    for event in sorted(evidence['events'], key=lambda e: (e['game_id'], e['play_id'])):
        raw = event['raw_flags']; gid = event['game_id']; parts = gid.split('_')
        if len(parts) != 4:
            raise ValueError('Defense context requires canonical native game team pair')
        # Source intake already canonicalizes aliases; use its canonical map.
        pair = {canonical_team(t) for t in parts[2:]}
        offense = event['team']
        if offense not in pair or len(pair) != 2:
            raise ValueError('Defense event offense conflicts with native game')
        defense = next(iter(pair - {offense}))
        if raw.get('defteam') is not None and raw['defteam'] != defense:
            raise ValueError('Defense event team conflicts with native game')
        key = (gid, defense)
        game = games.setdefault(key, dict(game_id=gid, defense_team=defense, offense_team=offense,
            season=event['season'], week=event['week'], defense_identity=dict(explicit_defteam_events=0, missing_defteam_inferred_from_native_pair_events=0), metrics={m: _metric() for m in DEFINITIONS}))
        identity_key = 'explicit_defteam_events' if raw.get('defteam') is not None else 'missing_defteam_inferred_from_native_pair_events'
        game['defense_identity'][identity_key] += 1
        passing, dropback, rushing = _eligibility(event)
        yards = _number(raw.get('yards_gained')); epa = _number(raw.get('epa'))
        yardline = _number(raw.get('yardline_100'))
        zone_known = yardline is not None and 0 <= yardline <= 100
        inside5 = False if rushing is False or (zone_known and yardline > 5) else None if rushing is None or not zone_known else True
        td = _flag(raw.get('rush_touchdown'))
        outcomes = {
            'G14-M07': (passing, None if yards is None else float(yards >= 20)),
            'dropback_epa_support': (dropback, epa),
            'G14-M09': (dropback, None if epa is None else float(epa > 0)),
            'G15-M01': (rushing, None if epa is None else float(epa > 0)),
            'G15-M02': (rushing, epa),
            'G15-M03': (rushing, None if yards is None else float(yards >= 10)),
            'G15-M04': (rushing, None if yards is None else float(yards <= 0)),
            'G15-M09': (inside5, None if td is None else float(td)),
        }
        for metric, (eligible, outcome) in outcomes.items():
            value = game['metrics'][metric]
            if eligible is None:
                value['unknown_eligibility_events'] += 1
            elif eligible:
                value['eligible_events'] += 1
                if outcome is None:
                    value['unknown_outcome_events'] += 1
                else:
                    value['known_outcome_events'] += 1
                    value['observed_outcome_sum'] += outcome
        semantic_rows.append(dict(game_id=gid, play_id=event['play_id'], defense=defense, outcomes=outcomes))
    grouped = defaultdict(list)
    for game in games.values():
        grouped[game['defense_team']].append(game)
    windows = []
    for team, rows in sorted(grouped.items()):
        rows.sort(key=lambda r: (r['season'], r['week'], r['game_id']))
        periods = [(r['season'], r['week']) for r in rows]
        if len(periods) != len(set(periods)):
            raise ValueError('Multiple defense games in one period; chronology ambiguous')
        selected = rows[-last_n_games:]
        totals = {m: _metric() for m in DEFINITIONS}
        for game in selected:
            for metric, value in game['metrics'].items():
                for k, v in value.items():
                    totals[metric][k] += v
        windows.append(dict(defense_team=team, observed_game_ids=[r['game_id'] for r in selected],
            observed_games=len(selected), metrics={m: _finish(v) for m, v in totals.items()}))
    game_rows = []
    for _, game in sorted(games.items()):
        game_rows.append({**game, 'metrics': {m: _finish(v) for m, v in game['metrics'].items()}})
    result = dict(version=VERSION, status='observed_descriptive_context', before_period=before_period,
        last_n_observed_games=last_n_games, definitions=deepcopy(DEFINITIONS), game_rows=game_rows, team_windows=windows,
        unavailable=['pressure', 'blitz', 'man_zone', 'route_charting', 'forecast_probabilities'],
        operational_verification='Pure boundary requires caller verified immutable parent and indexed raw Snapshot; checksum alone is not source verification',
        source_measurement='EPA is provider-derived expected-points measurement; not raw physical fact or fantasy points',
        full_game_coverage='unverified; observed logs are not verified complete games',
        historical_availability='later revised capture; original pregame publication unknown', forecast=None)
    semantic_rows.sort(key=lambda r: (r['game_id'], r['play_id'], r['defense']))
    result['semantic_measurements_sha256'] = _hash(dict(result=result, source_outcomes=semantic_rows, source_quality=dict(full_game_coverage=evidence['source'].get('full_game_coverage'), game_completion=evidence['source'].get('game_completion'), official_reconciliation=sorted([{k:v for k,v in r.items() if k not in {'official_source_id','official_imported_at'}} for r in evidence.get('official_reconciliation', [])], key=lambda r: json.dumps(r, sort_keys=True)))))
    result['provenance'] = dict(source=deepcopy(evidence['source']), event_receipt_sha256=evidence['sha256'],
        decision_cutoff_at=str(cutoff), source_epa='provider-derived expected-points measurement, not raw physical fact or fantasy points',
        metric_lineage={m: dict(source_snapshot_id=evidence['source']['snapshot_id'], event_receipt_sha256=evidence['sha256'], before_period=before_period, unit=d['unit'], definition=d['variant']) for m,d in DEFINITIONS.items()},
        producer_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return result
