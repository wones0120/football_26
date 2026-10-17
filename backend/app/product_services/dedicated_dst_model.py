"""Research-only DST learner and canonical preweek feature contract.

Live Prepare does not call this module. Corrections and event sources must be
verified explicitly by the caller; unknown history is never a zero observation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from Database.dst import normalize_team
from .dst_training_labels import SCORING_CONTRACT

MARKETS = ['salary', 'game_total_line', 'team_spread_line', 'team_implied_total', 'opponent_implied_total']
HISTORY = ['dst_history_count', 'dst_points_last3', 'dst_points_last8', 'dst_points_std8',
           'dst_sacks_last8', 'dst_takeaways_last8', 'dst_allowed_last8',
           'opponent_conceded_last3', 'opponent_conceded_last8', 'opponent_sacks_last8',
           'opponent_takeaways_last8']
FEATURES = [*MARKETS, 'dst_home_from_game', *HISTORY]
LEARNERS = ('median', 'ridge', 'regularized_tree')


def checked_outcomes(events: list[dict], identities: list[dict]) -> pd.DataFrame:
    """Require complete, finite event outcomes and independently supplied UUIDs."""
    identity = {normalize_team(r['primary_team']): str(r['player_master_id']) for r in identities}
    rows = []
    seen = set()
    for event in events:
        team, opponent = normalize_team(event['team']), normalize_team(event['opponent'])
        parts = event['game_id'].split('_')
        if (event.get('contract_id') != SCORING_CONTRACT
                or event.get('coverage') != 'complete_final_event_scoring'
                or len(parts) != 4 or {normalize_team(x) for x in parts[2:]} != {team, opponent}
                or identity.get(team) != str(event['player_master_id'])):
            raise ValueError('Unverified DST event identity/coverage/scoring contract')
        key = (event['game_id'], str(event['player_master_id']))
        if key in seen:
            raise ValueError('Duplicate canonical DST game outcome')
        seen.add(key)
        c = event['components']
        values = [event['dk_points'], c['sacks'], c['interceptions'], c['fumble_recoveries'], c['points_allowed']]
        if not all(v is not None and np.isfinite(float(v)) for v in values):
            raise ValueError('Missing finite observed DST outcome/component')
        rows.append(dict(season=int(parts[0]), week=int(parts[1]), team=team, opponent=opponent,
                         game_id=event['game_id'], player_master_id=str(event['player_master_id']),
                         points=float(event['dk_points']), sacks=float(c['sacks']),
                         takeaways=float(c['interceptions']) + float(c['fumble_recoveries']),
                         allowed=float(c['points_allowed'])))
    if not rows:
        raise ValueError('No verified DST outcomes')
    return pd.DataFrame(rows).sort_values(['season', 'week', 'game_id', 'team']).reset_index(drop=True)


def build_features(frame: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    """Each row sees only complete outcomes from strictly earlier NFL weeks.

    Use canonical UUID for own history and canonical opponent team for conceded
    history. Game IDs establish home only after exact week and teams validation.
    """
    if not frame.position.astype(str).str.upper().eq('DST').all():
        raise ValueError('Dedicated DST model cannot score offensive players')
    features = frame.reindex(columns=MARKETS).apply(pd.to_numeric, errors='coerce').copy()
    features.replace([np.inf, -np.inf], np.nan, inplace=True)
    for column in ['dst_home_from_game', *HISTORY]:
        features[column] = np.nan
    periods = outcomes.season * 100 + outcomes.week
    for index, row in frame.iterrows():
        season, week = int(row.season), int(row.week)
        team, opponent = normalize_team(row.team), normalize_team(row.opponent)
        prior = outcomes[periods < season * 100 + week]
        identity = str(row.player_master_id)
        known = outcomes[outcomes.player_master_id.eq(identity)]
        if known.empty or not known.team.eq(team).all():
            raise ValueError('Unknown or inconsistent canonical DST identity')
        own = prior[prior.player_master_id.eq(identity)]
        if not own.empty and not own.team.eq(team).all():
            raise ValueError('Canonical DST identity has inconsistent team history')
        current = outcomes[(outcomes.season == season) & (outcomes.week == week) & outcomes.team.eq(team)]
        game_id = row.get('game_id')
        if pd.isna(game_id) or not str(game_id).strip():
            if len(current) != 1 or str(current.iloc[0].player_master_id) != identity:
                raise ValueError('Missing canonical DST game identity')
            game_id = current.iloc[0].game_id
        parts = str(game_id).split('_')
        if (len(parts) != 4 or parts[:2] != [str(season), f'{week:02d}']
                or {normalize_team(x) for x in parts[2:]} != {team, opponent}):
            raise ValueError('DST target canonical game identity mismatch')
        if not current.empty and (len(current) != 1 or str(current.iloc[0].player_master_id) != identity
                                  or current.iloc[0].game_id != game_id):
            raise ValueError('DST outcome and matrix identity mismatch')
        conceded = prior[prior.opponent.eq(opponent)]
        features.at[index, 'dst_home_from_game'] = float(normalize_team(parts[3]) == team)
        features.at[index, 'dst_history_count'] = len(own)
        for name, values in [
            ('dst_points_last3', own.tail(3).points), ('dst_points_last8', own.tail(8).points),
            ('dst_sacks_last8', own.tail(8).sacks), ('dst_takeaways_last8', own.tail(8).takeaways),
            ('dst_allowed_last8', own.tail(8).allowed),
            ('opponent_conceded_last3', conceded.tail(3).points),
            ('opponent_conceded_last8', conceded.tail(8).points),
            ('opponent_sacks_last8', conceded.tail(8).sacks),
            ('opponent_takeaways_last8', conceded.tail(8).takeaways),
        ]:
            features.at[index, name] = values.mean() if len(values) else np.nan
        features.at[index, 'dst_points_std8'] = own.tail(8).points.std(ddof=0) if len(own) else np.nan
    return features[FEATURES]


def learner(name: str) -> Pipeline:
    """Small frozen candidate set; imputer/scaler always fit on training rows."""
    models = {
        'median': DummyRegressor(strategy='median'),
        'ridge': Ridge(alpha=100),
        'regularized_tree': HistGradientBoostingRegressor(
            loss='squared_error', max_iter=100, max_leaf_nodes=7, max_depth=2,
            min_samples_leaf=30, l2_regularization=10, learning_rate=.05,
            random_state=42, early_stopping=False),
    }
    if name not in models:
        raise ValueError('Unknown frozen DST learner')
    steps = [('missing', SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True))]
    if name == 'ridge':
        steps.append(('scale', StandardScaler()))
    return Pipeline([*steps, ('model', models[name])])


def choose_on_prior_weeks(frame: pd.DataFrame, features: pd.DataFrame, target: str):
    """Select on the last three training weeks; outer test labels never enter."""
    period = frame.season * 100 + frame.week
    weeks = sorted(period.unique())
    if len(weeks) < 6:
        raise ValueError('At least six observed training weeks required')
    inner = period >= weeks[-3]
    scores = []
    for name in LEARNERS:
        model = learner(name)
        model.fit(features.loc[~inner], frame.loc[~inner, target])
        prediction = model.predict(features.loc[inner])
        scores.append(dict(name=name, mae=float(np.abs(prediction-frame.loc[inner, target]).mean()),
                           train_n=int((~inner).sum()), validation_n=int(inner.sum()),
                           train_last_week=int(period.loc[~inner].max()), validation_first_week=int(period.loc[inner].min())))
    selected = min(scores, key=lambda r: (r['mae'], LEARNERS.index(r['name'])))['name']
    result = learner(selected)
    result.fit(features, frame[target])
    return result, dict(selected=selected, scores=scores, training_last_week=int(period.max()))
