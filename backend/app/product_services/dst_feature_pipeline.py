"""Inactive candidate path for verified DST matrix, training and inference inputs.

The context must be supplied explicitly. No live route or default model policy
constructs it. Candidate matrix generation cannot persist over historical rows.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from Database.dst import normalize_team
from .dedicated_dst_model import build_features, checked_outcomes
from .dst_training_labels import SCORING_CONTRACT

POLICY = 'verified_dst_features_candidate_v1'
REPAIRED_COLUMNS = ['game_id', 'is_home', 'player_games_history', 'player_roll3_mean',
                    'player_roll8_mean', 'player_roll8_std', 'player_vs_opp_roll4',
                    'defense_pos_allowed_roll3', 'defense_pos_allowed_roll8',
                    'defense_pos_allowed_p90_roll8']


@dataclass(frozen=True)
class DstFeatureContext:
    outcomes: pd.DataFrame
    source_sha256: str
    identities_sha256: str
    chronology: str
    schedule: pd.DataFrame | None = None

    @classmethod
    def read(cls, events_path, identities_path, *, expected_events_sha256,
             expected_identities_sha256, schedule=None):
        def read_verified(path, expected):
            raw = Path(path).read_bytes()
            if hashlib.sha256(raw).hexdigest() != expected:
                raise ValueError('DST feature source checksum mismatch')
            return json.loads(raw)
        events = read_verified(events_path, expected_events_sha256)
        identities = read_verified(identities_path, expected_identities_sha256)
        return cls(checked_outcomes(events, identities), expected_events_sha256,
                   expected_identities_sha256,
                   'Retrospective verified outcomes; original pregame capture clocks incomplete', schedule)


def repair_dst_frame(frame: pd.DataFrame, context: DstFeatureContext, *, matrix_generation=False):
    """One canonical adapter shared by matrix generation, training and prediction.

    Unknown history remains NaN, never a synthetic zero observation. Labels are
    replaced only during explicitly nonpersistent candidate matrix generation;
    canonical training label selection remains a separate verified operation.
    """
    if not isinstance(context, DstFeatureContext):
        raise ValueError('Explicit verified DST candidate context required')
    result = frame.copy(deep=True)
    mask = result.position.astype(str).str.upper().eq('DST')
    if not mask.any():
        return result, dict(policy=POLICY, rows=0)
    dst = result.loc[mask].copy()
    # The legacy generator deliberately left game_id unset. Resolve from an
    # independently captured canonical game/team record, never display names.
    for index, row in dst.iterrows():
        if pd.notna(row.get('game_id')) and str(row.get('game_id')).strip():
            continue
        matches = context.outcomes[(context.outcomes.season == int(row.season))
                                   & (context.outcomes.week == int(row.week))
                                   & context.outcomes.player_master_id.eq(str(row.player_master_id))]
        if matches.empty and context.schedule is not None:
            matches = context.schedule[(context.schedule.season == int(row.season))
                                       & (context.schedule.week == int(row.week))
                                       & context.schedule.player_master_id.astype(str).eq(str(row.player_master_id))]
        if len(matches) != 1:
            raise ValueError('Missing or ambiguous canonical DST schedule identity')
        dst.at[index, 'game_id'] = matches.iloc[0].game_id
    features = build_features(dst, context.outcomes)
    mappings = dict(is_home='dst_home_from_game', player_games_history='dst_history_count',
                    player_roll3_mean='dst_points_last3', player_roll8_mean='dst_points_last8',
                    player_roll8_std='dst_points_std8', defense_pos_allowed_roll3='opponent_conceded_last3',
                    defense_pos_allowed_roll8='opponent_conceded_last8')
    result.loc[mask, 'game_id'] = dst.game_id
    for column, source in mappings.items():
        result.loc[mask, column] = features[source]
    for index, row in dst.iterrows():
        prior = context.outcomes[(context.outcomes.season*100+context.outcomes.week) < int(row.season)*100+int(row.week)]
        own = prior[prior.player_master_id.eq(str(row.player_master_id))]
        opponent = prior[prior.opponent.eq(normalize_team(row.opponent))]
        versus = own[own.opponent.eq(normalize_team(row.opponent))]
        result.at[index, 'player_vs_opp_roll4'] = versus.tail(4).points.mean() if len(versus) else np.nan
        result.at[index, 'defense_pos_allowed_p90_roll8'] = opponent.tail(8).points.quantile(.9) if len(opponent) else np.nan
        if matrix_generation:
            current = context.outcomes[(context.outcomes.season==int(row.season)) & (context.outcomes.week==int(row.week))
                                       & context.outcomes.player_master_id.eq(str(row.player_master_id))]
            # Future target rows have no observed label, even if legacy pool uses 0.
            result.at[index, 'dk_points'] = float(current.iloc[0].points) if len(current)==1 else np.nan
    result.attrs["dst_feature_policy"] = POLICY
    audit = dict(policy=POLICY, rows=int(mask.sum()), source_sha256=context.source_sha256,
                 identities_sha256=context.identities_sha256, scoring_contract=SCORING_CONTRACT,
                 columns=REPAIRED_COLUMNS, chronology=context.chronology,
                 missing_history_rows=int(result.loc[mask, 'player_roll3_mean'].isna().sum()),
                 prior_only='season/week strictly before decision week', live_enabled=False)
    return result, audit


def prepare_candidate_frames(train, target, context):
    """Apply the exact same matrix contract after canonical selection to both arms."""
    repaired_train, training_audit = repair_dst_frame(train, context)
    repaired_target, prediction_audit = repair_dst_frame(target, context)
    return repaired_train, repaired_target, dict(training=training_audit, prediction=prediction_audit,
                                               policy=POLICY, live_enabled=False)


def shrunk_history_prediction(frame, context):
    """Fixed eight-game prior strength; recent history shrinks to prior league mean."""
    features = build_features(frame, context.outcomes)
    predictions = []
    for index, row in frame.iterrows():
        prior = context.outcomes[(context.outcomes.season*100+context.outcomes.week) < int(row.season)*100+int(row.week)]
        if prior.empty:
            predictions.append(np.nan)
            continue
        league = float(prior.points.mean())
        n = min(float(features.at[index, 'dst_history_count']), 8.)
        short = features.at[index, 'dst_points_last3']
        long = features.at[index, 'dst_points_last8']
        anchor = .65*short+.35*long if n else league
        predictions.append((n*anchor+8.*league)/(n+8.))
    return np.asarray(predictions, dtype=float)


def score_dst_candidate_bundle(bundle, target, *, arm='repaired_dedicated'):
    """Concrete read-only artifact scorer; returns a DST overlay, never persists.

    All targets must follow the artifact's training window. Offense projections
    are absent from this overlay so the caller cannot accidentally replace them.
    """
    if arm not in {'repaired_shared', 'repaired_dedicated', 'history_baseline'}:
        raise ValueError('Unknown candidate scoring arm')
    selected = target[target.position.astype(str).str.upper().eq('DST')].copy()
    if selected.empty:
        raise ValueError('No canonical DST targets')
    train = bundle['training']
    training_end = int((train.season*100+train.week).max())
    if (selected.season*100+selected.week <= training_end).any():
        raise ValueError('Candidate scoring targets overlap training history')
    selected, audit = repair_dst_frame(selected, bundle['context'])
    if arm == 'history_baseline':
        means = shrunk_history_prediction(selected, bundle['context'])
    else:
        columns = bundle['metadata']['dedicated_columns' if arm == 'repaired_dedicated' else 'feature_columns']
        means = bundle['models'][arm].predict(selected[columns])
        if arm == 'repaired_shared':
            from .predictions import blend_point_predictions
            means = blend_point_predictions(means, train, selected)
    if not np.isfinite(means).all():
        raise ValueError('Candidate DST means are not finite')
    overlay = selected[['player_master_id', 'season', 'week', 'game_id']].copy()
    overlay['mean'] = means
    return overlay, dict(**audit, arm=arm, training_end=training_end, persisted=False)
