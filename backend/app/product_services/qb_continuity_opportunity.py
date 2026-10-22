"""Observed target opportunity conditioned on reported game-starter continuity.

Current means the measured game. This is neither a future role forecast nor a
claim that each target was thrown by the reported starting quarterback.
"""
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, UTC
from uuid import UUID
import math
from .evaluation_record import digest
from .factual_designation import clock
from .market_snapshots import canonical_team
from .workload_venue_splits import build_workload_venue_splits
from .workload_starting_qb_context import SOURCE_VERSION, _native, _kickoff
from .weekly_effectiveness_catalog_features import _values, SOURCE_FIELDS
from .defense_context_evidence import _hash

VERSION = 'observed_qb_continuity_target_opportunity_v1'
ROLES = {'X03-M03': {'WR', 'TE'}, 'X03-M04': {'RB', 'FB'}}


def _starter_states(schedule, starters, before_period, cutoff):
    if starters.get('version') != SOURCE_VERSION or starters.get('pregame_serving_eligible') is not False:
        raise ValueError('Authenticated nonserving native starter source required')
    if starters.get('semantic_sha256') != digest({k: starters[k] for k in ('version', 'rows', 'role_scope')}):
        raise ValueError('Starter semantic checksum differs')
    if any(starters['provenance'].get(k) != schedule['provenance'].get(k) for k in ('snapshot_id', 'sha256')):
        raise ValueError('Starter and schedule source pairing differs')
    for field in ('observed_at', 'captured_at'):
        t = clock(starters['provenance'].get(field))
        if t is None or t > cutoff: raise ValueError('Starter source clock missing or future')
    if clock(starters['provenance']['observed_at']) > clock(starters['provenance']['captured_at']):
        raise ValueError('Starter source chronology differs')
    games = {g['game_id']: g for g in schedule['game_rows']}
    lookup = {}
    for r in starters['rows']:
        g = games.get(r['game_id']); key = (r['game_id'], r['team'])
        if (g is None or key in lookup or r['team'] not in {g['home_team'], g['away_team']}
                or (r['season'], r['week']) != (g['season'], g['week'])
                or r['source_starter_native_id'] != _native(r['original_source_qb_id'])
                or r['native_kickoff_at'] != _kickoff(r['source_game_date'], r['source_gametime_Eastern'])):
            raise ValueError('Starter native scope, role identity or kickoff contradicts source')
        lookup[key] = r
    expected = {(g['game_id'], t) for g in games.values() if g['game_type'] == 'REG'
                for t in (g['home_team'], g['away_team'])}
    if set(lookup) != expected: raise ValueError('Complete scheduled starter-side universe required')
    teams = defaultdict(list)
    for g in games.values():
        if g['game_type'] == 'REG' and g['season'] * 100 + g['week'] < before_period:
            for t in (g['home_team'], g['away_team']): teams[(g['season'], t)].append(g)
    states = {}
    for (season, team), gs in teams.items():
        gs.sort(key=lambda g: g['week'])
        if len({g['week'] for g in gs}) != len(gs): raise ValueError('Ambiguous scheduled team week')
        for i, g in enumerate(gs):
            current = lookup[(g['game_id'], team)]['source_starter_native_id']
            prior = lookup[(gs[i-1]['game_id'], team)]['source_starter_native_id'] if i else None
            state = 'first_scheduled_game' if not i else 'unknown' if current is None or prior is None else 'same' if current == prior else 'changed'
            states[(season, g['week'], team)] = dict(native_game_id=g['game_id'], current_reported_QB=current,
                prior_scheduled_game_id=gs[i-1]['game_id'] if i else None, prior_reported_QB=prior, continuity=state)
    return states


def build_qb_continuity_opportunity(weekly, schedule, starters, raw_source, *, before_period, cutoff,
                                    positive_participants_missing_weekly=()):
    """Use every raw native team's target row for budgets, including bad actor IDs.

    Source-observed player logs are the opportunity cohort. Missing scheduled
    player rows are not zeros. Known positive participants lacking a weekly row
    are additional unknown response slots, never omitted complete cases.
    """
    decision = clock(cutoff)
    if decision is None or decision > datetime.now(UTC): raise ValueError('Actual nonfuture cutoff required')
    base = build_workload_venue_splits(weekly, schedule, before_period=before_period)
    if clock(weekly['provenance'].get('actual_derived_at')) is None or clock(weekly['provenance']['actual_derived_at']) > decision:
        raise ValueError('Weekly source unavailable at cutoff')
    states = _starter_states(schedule, starters, before_period, decision)
    raw_by_source = {}; budgets = defaultdict(list); unknown_team_periods = set()
    for r in raw_source['rows']:
        key = r['source_id']
        if key in raw_by_source: raise ValueError('Duplicate frozen raw source identity')
        raw_by_source[key] = r
        season, week = r['season'], r['week']; raw = r['raw_row_json']
        if (type(season) is not int or type(week) is not int or season*100+week >= before_period
                or raw.get('season_type') != 'REG' or clock(r.get('imported_at')) is None
                or clock(r['imported_at']) > decision): raise ValueError('Raw weekly phase/period/clock differs')
        teams = set()
        for value in (r.get('team'), raw.get('team'), raw.get('recent_team')):
            if value not in (None, ''):
                try: teams.add(canonical_team(value))
                except ValueError: teams.add(None)
        team = next(iter(teams)) if len(teams) == 1 and None not in teams else None
        if team is None: unknown_team_periods.add((season, week)); continue
        if (season, week, team) not in states: raise ValueError('Raw native team has no scheduled game')
        target = _values(raw)[0]['targets']
        budgets[(season, week, team)].append(target)
    exact_budget = {key: sum(v) if v and all(x is not None for x in v) and key[:2] not in unknown_team_periods else None
                    for key, v in budgets.items()}
    groups = defaultdict(list); identities = defaultdict(set); unknown_role_logs = []; unknown_actor_scope = set()
    for r in weekly['rows']:
        source = raw_by_source.get(r['source_ref']['source_id'])
        if source is None: raise ValueError('Reviewed weekly row missing from frozen raw universe')
        raw = source['raw_row_json']
        if _hash({k:v for k,v in raw.items() if k in SOURCE_FIELDS}) != r['source_ref']['projected_source_row_sha256']:
            raise ValueError('Frozen projected raw row checksum differs')
        roles = {x for x in (source.get('position'), raw.get('position'), raw.get('pos')) if x not in (None, '')}
        role = next(iter(roles)) if len(roles) == 1 else None
        if r['source_position'] not in roles or role != r['source_position']: role = None
        key = (r['season'], r['week'], r['team']); state = states.get(key)
        if state is None:
            unknown_actor_scope.add((r['season'], r['source_player_id']))
            unknown_role_logs.append(dict(source_player_id=r['source_player_id'], season=r['season'], week=r['week'], reason='Unknown native team scope')); continue
        if r['native_game_id'] not in (None, '', state['native_game_id']): raise ValueError('Weekly native game differs')
        if (source['source_player_id'], source['season'], source['week'], source.get('ingest_run_id'), source.get('imported_at')) != (r['source_player_id'], r['season'], r['week'], r['source_ref']['ingest_run_id'], r['source_ref']['imported_at']):
            raise ValueError('Frozen raw and reviewed weekly revisions differ')
        count = r['metrics']['G09-M01']['denominator']
        if count != _values(raw)[0]['targets']: raise ValueError('Raw target and reviewed count differ')
        for mid, eligible in ROLES.items():
            if role not in eligible:
                if role is None:
                    unknown_actor_scope.add((r['season'], r['source_player_id']))
                    unknown_role_logs.append(dict(source_player_id=r['source_player_id'], season=r['season'], week=r['week'], reason='Unknown/conflicting per-game role'))
                continue
            gkey = (mid, r['season'], r['team'], r['source_player_id'])
            identities[gkey].add(r['player_master_id'])
            total = exact_budget.get(key)
            if count is not None and total is not None and count > total: raise ValueError('Actor target count exceeds full native budget')
            groups[gkey].append(dict(week=r['week'], **state, source_role=role, target_count=count,
                full_native_team_targets=total, source_ref=deepcopy(r['source_ref']), positive_missing_weekly=False))
    missing_positive_identities = set()
    retained_missing_positive = []
    for p in positive_participants_missing_weekly:
        retained_missing_positive.append(deepcopy(p))
        missing_positive_identities.add((p['season'], p['team'], p.get('player_master_id')))
        key = (p['season'], p['week'], p['team']); state = states.get(key)
        if (state is None or p.get('native_game_id') != state['native_game_id']
                or type(p.get('offense_snaps')) not in {int, float} or not math.isfinite(p['offense_snaps']) or not p['offense_snaps'] > 0
                or p['offense_snaps'] != int(p['offense_snaps'])
                or p.get('player_master_id') is None
                or str(UUID(str(p['player_master_id']))) != p['player_master_id']):
            raise ValueError('Positive missing participant requires native game, positive snaps and canonical proof')
        exact_budget[key] = None
        for group_key, logs in groups.items():
            if group_key[2] != p['team']: continue
            for log in logs:
                if log['native_game_id'] == state['native_game_id'] and log['week'] == p['week']:
                    log['full_native_team_targets'] = None
        for mid, eligible in ROLES.items():
            if p.get('source_position') not in eligible: continue
            gkey = (mid, p['season'], p['team'], p['source_player_id'])
            identities[gkey].add(p.get('player_master_id'))
            if any(l['week'] == p['week'] for l in groups[gkey]): raise ValueError('Positive missing participant duplicates observed weekly row')
            groups[gkey].append(dict(week=p['week'], **state, source_role=p['source_position'], target_count=None,
                full_native_team_targets=exact_budget.get(key), source_ref=deepcopy(p), positive_missing_weekly=True))
    rows = []
    for key, logs in sorted(groups.items(), key=lambda pair: str(pair[0])):
        mid, season, team, native = key
        if len(identities[key]) != 1: raise ValueError('Per-actor canonical attachment changes')
        logs.sort(key=lambda r: r['week']); unknown = sum(l['continuity'] == 'unknown' for l in logs)
        metrics = {}
        for state in ('same', 'changed'):
            sample = [l for l in logs if l['continuity'] == state]
            known = [l for l in sample if l['target_count'] is not None]
            numerator = sum(l['target_count'] for l in known)
            count_exact = (bool(sample) and len(known) == len(sample) and not unknown and (season, native) not in unknown_actor_scope
                           and (season, team, next(iter(identities[key]))) not in missing_positive_identities)
            share_exact = count_exact and all(l['full_native_team_targets'] is not None for l in sample)
            denom = sum(l['full_native_team_targets'] for l in sample) if share_exact else None
            metrics[state] = dict(observed_logs=len(sample), known_target_logs=len(known), known_target_sum=numerator,
                exact_target_sum=numerator if count_exact else None,
                exact_targets_per_observed_log=numerator/len(sample) if count_exact else None,
                matched_full_native_team_target_sum=denom,
                exact_pooled_target_share=numerator/denom if denom is not None and denom > 0 else None)
        def contrast(field):
            a, b = metrics['changed'][field], metrics['same'][field]
            return a-b if a is not None and b is not None else None
        rows.append(dict(candidate_id=mid, season=season, team=team, source_player_id=native,
            player_master_id=next(iter(identities[key])), logs=logs, metrics=metrics,
            unknown_continuity_logs=unknown, changed_minus_same_target_mean=contrast('exact_targets_per_observed_log'),
            changed_minus_same_pooled_target_share=contrast('exact_pooled_target_share')))
    semantic_rows = [{**r, 'logs': [{k:v for k,v in l.items() if k != 'source_ref'} for l in r['logs']]} for r in rows]
    basis = dict(version=VERSION, before_period=before_period, rows=semantic_rows, unknown_role_logs=unknown_role_logs, missing_positive_participants=retained_missing_positive,
        definition='Historical measured-game reported starting QB same vs changed from immediate scheduled prior same-team game; source-proven WR/TE and RB/FB target response')
    return basis | dict(rows=rows, semantic_sha256=digest(basis), provenance=deepcopy(base['provenance']),
        pregame_serving_eligible=False, evidence_use='postlock_descriptive_not_pregame_or_serving', forecast=None,
        models_or_optimizer_consumed=False, identity_review_requests=deepcopy(weekly['identity_review_requests']),
        limitations=['Source-observed weekly opportunity logs, not all active games or absent-player zeros',
            'Reported starter is whole-game context, not every pass attribution or healthy/full-role proof',
            'Missing positive participants retained unknown where authenticated participation exists; unavailable historical participation is not imputed',
            'Full native weekly-source target budget is not independently certified complete NFL game charting',
            'Original historical publication chronology unknown; no causal response, future probability or serving'])


def require_feature_use(value, *, purpose):
    if value.get('version') != VERSION or value.get('pregame_serving_eligible') is not False or purpose != 'offline_descriptive':
        raise ValueError('Observed QB continuity cannot serve forecasts/models/optimizer')
    return value
