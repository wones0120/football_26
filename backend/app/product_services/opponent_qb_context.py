"""Shadow-only, auditable opponent-QB inputs; never modifies live projections.

Historical proxies select a QB from *prior* completed games, not the eventual
starter in the target game. Strict source clocks are the default. Explicit
retrospective reconstruction is useful for feature ablation, but cannot restore
unrecorded historical information availability or validate starter-change news.
"""
from datetime import UTC, datetime
import math
from uuid import UUID

from Database.dst import normalize_team

CONTRACT = 'opponent_qb_context_shadow_v1'
RATE_FIELDS = {
    'sack_rate': ('sacks', 'dropbacks'),
    'interception_rate': ('interceptions', 'attempts'),
    'sack_fumble_lost_rate': ('sack_fumbles_lost', 'dropbacks'),
    'yards_per_attempt': ('passing_yards', 'attempts'),
    'passing_epa_per_dropback': ('passing_epa', 'dropbacks'),
    'rushing_yards_per_carry': ('rushing_yards', 'carries'),
}
FEATURE_COLUMNS = [
    'opponent_qb_prior_games', 'opponent_qb_prior_dropbacks',
    'opponent_qb_context_missing', 'opponent_qb_small_sample',
    'opponent_qb_starter_uncertain', 'opponent_qb_changed_from_last_primary',
    *['opponent_qb_' + key for key in RATE_FIELDS],
    *['opponent_qb_' + key + '_missing' for key in RATE_FIELDS],
]


def _clock(value):
    if value is None:
        return None
    value = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


class QBContextIndex:
    """Index caller-normalized canonical QB/game logs without name matching.

    Required log keys: player_master_id, team, season, week, completed_at,
    available_at, source_row_id; numeric keys are RATE_FIELDS plus attempts/sacks.
    Missing numeric values stay missing. Multiple versions of a QB/period must
    be resolved upstream at the appropriate source cutoff, never silently picked.
    """
    def __init__(self, logs):
        self.by_team, self.by_player = {}, {}
        seen = set()
        for item in logs:
            row = dict(item)
            pid = str(row['player_master_id']); UUID(pid)
            row.update(player_master_id=pid, team=normalize_team(row['team']),
                       period=(int(row['season']), int(row['week'])),
                       completed_at=_clock(row.get('completed_at')), available_at=_clock(row.get('available_at')))
            key = (pid, row['period'])
            if key in seen:
                raise ValueError('Duplicate canonical QB/period; resolve source versions before indexing')
            seen.add(key)
            for field in {'attempts','sacks','interceptions','sack_fumbles_lost','passing_yards','passing_epa','carries','rushing_yards'}:
                row[field] = _number(row.get(field))
            row['dropbacks'] = row['attempts'] + row['sacks'] if row['attempts'] is not None and row['sacks'] is not None else None
            self.by_team.setdefault(row['team'], []).append(row)
            self.by_player.setdefault(pid, []).append(row)
        for group in [*self.by_team.values(), *self.by_player.values()]:
            group.sort(key=lambda row: row['period'])

    def context(self, *, opponent_team, season, week, decision_at,
                starter_evidence=None, strict_source_clocks=True, window=8):
        if window < 1:
            raise ValueError('Positive prior-game window required')
        cutoff = _clock(decision_at)
        if cutoff is None:
            raise ValueError('A decision cutoff is required')
        period = (int(season), int(week)); team = normalize_team(opponent_team)
        def visible(row):
            return (row['period'] < period and row['completed_at'] is not None and row['completed_at'] < cutoff
                    and (not strict_source_clocks or row['available_at'] is not None and row['available_at'] <= cutoff))
        prior_team = [r for r in self.by_team.get(team, []) if visible(r) and (r['dropbacks'] or 0) > 0]
        latest_period = max((r['period'] for r in prior_team), default=None)
        last = sorted([r for r in prior_team if r['period'] == latest_period],
                      key=lambda r: (-(r['dropbacks'] or 0), r['player_master_id']))
        tied = len(last) > 1 and last[0]['dropbacks'] == last[1]['dropbacks']
        last_id = last[0]['player_master_id'] if last and not tied else None
        evidence = dict(starter_evidence or {})
        clocks = [_clock(evidence.get(k)) for k in ('observed_at','received_at')]
        valid_evidence = (evidence.get('team') is not None and normalize_team(evidence['team']) == team
                          and evidence.get('player_master_id') is not None and bool(evidence.get('source_uri'))
                          and all(t is not None and t <= cutoff for t in clocks)
                          and evidence.get('evidence_tier') in {'confirmed','inferred'})
        selected = str(evidence['player_master_id']) if valid_evidence else last_id
        if selected:
            UUID(selected)
        history = [r for r in self.by_player.get(selected, []) if visible(r) and (r['dropbacks'] or 0) > 0][-window:]
        dropbacks = sum(r['dropbacks'] for r in history)
        features = dict(opponent_qb_prior_games=len(history), opponent_qb_prior_dropbacks=dropbacks,
            opponent_qb_context_missing=int(not history), opponent_qb_small_sample=int(dropbacks < 100),
            opponent_qb_starter_uncertain=int(not valid_evidence or evidence['evidence_tier'] != 'confirmed' or bool(evidence.get('conditional_scenario'))),
            opponent_qb_changed_from_last_primary=int(bool(selected and last_id and selected != last_id)))
        for label, (numerator, denominator) in RATE_FIELDS.items():
            present = bool(history) and all(r[numerator] is not None and r[denominator] is not None for r in history)
            total = sum(r[denominator] for r in history) if present else 0
            value = sum(r[numerator] for r in history) / total if present and total > 0 else None
            features['opponent_qb_' + label] = value
            features['opponent_qb_' + label + '_missing'] = int(value is None)
        return dict(contract_id=CONTRACT, features=features, player_master_id=selected,
            selection='conditional_starter_scenario' if valid_evidence and evidence.get('conditional_scenario') else 'sourced_expected_starter' if valid_evidence else 'previous_completed_team_game_primary_qb_proxy' if last_id else 'unknown',
            source_clock_mode='strict' if strict_source_clocks else 'retrospective_event_time_reconstruction',
            decision_at=cutoff.isoformat(), opponent_team=team,
            starter_evidence=evidence if valid_evidence else None,
            rejected_starter_evidence=bool(starter_evidence and not valid_evidence),
            history_source_row_ids=[r['source_row_id'] for r in history],
            history_periods=[list(r['period']) for r in history],
            latest_history_completed_at=max((r['completed_at'] for r in history), default=None),
            latest_history_available_at=max((r['available_at'] for r in history if r['available_at']), default=None),
            limitations=['Dropbacks are pass attempts + sacks; no charted pressure or scramble denominator.',
                'QB rushing includes designed runs and kneels; it is not a pure pressure-escape rate.',
                'Missing/small samples require train-only imputation; no hand-assigned quality score.',
                'Prior-primary historical proxy cannot validate announced starter-change effects.'])


def dst_label_lower_bound_violation(points, qb_sacks, qb_interceptions):
    """Reject impossible DK DST labels without reconstructing missing scores.

    Each sack is +1, interception +2 and the points-allowed floor is -4.
    Other DST scoring components cannot reduce the score. QB-only totals are
    conservative when non-QBs also throw or suffer sacks. Passing this check
    is not proof a label is complete or that its chronology is established.
    """
    score, sacks, interceptions = map(_number, (points, qb_sacks, qb_interceptions))
    if any(value is None for value in (score, sacks, interceptions)):
        return None
    if sacks < 0 or interceptions < 0:
        raise ValueError('Sack and interception counts must be nonnegative')
    return score < sacks + 2 * interceptions - 4 - 1e-8
