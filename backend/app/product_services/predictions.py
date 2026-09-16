"""Simple training/prediction service using predictive_features."""

from __future__ import annotations

import logging
import hashlib
import json
import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Any

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import ProgrammingError

from sklearn.ensemble import GradientBoostingRegressor
from sklearn.isotonic import IsotonicRegression

from Database.config import get_connection_string
from .optimizer import _normalize_alias
from .target_schema import validate_target_schema


TARGET_COL = "label_dk_total_points"
ACTIVE_MODEL_ID = "gradient_boosting_challenger_v4_1_team_opportunity_context"
POINT_MODEL_RAW_WEIGHT = 0.80
POINT_MODEL_HISTORY_WEIGHT = 0.20
HISTORY_ROLL3_WEIGHT = 0.60
HISTORY_ROLL8_WEIGHT = 0.40
RB_TARGET_OPPORTUNITY_WEIGHT = 1.75
VETERAN_OPPORTUNITY_ANCHOR_WEIGHT = 0.55
LOW_HISTORY_OPPORTUNITY_ANCHOR_WEIGHT = 0.70
CALIBRATION_QUANTILES = {
    "p10": 0.10,
    "p25": 0.25,
    "p50": 0.50,
    "p75": 0.75,
    "p90": 0.90,
}
MIN_WALK_FORWARD_TRAIN_ROWS = 100
MIN_POSITION_CALIBRATION_ROWS = 30
MIN_ROLE_CALIBRATION_ROWS = 50
ID_COLS = [
    "player_id",
    "player_master_id",
    "player_display_name",
    "position",
    "recent_team",
    "opponent_team",
    "season",
    "week",
    "team_implied_total",
    "team_spread",
    "game_total",
    "opp_pts_allowed_pos_3",
    "opp_pts_allowed_pos_5",
    "run_funnel",
    "pass_funnel",
]


def select_training_rows_before_cutoff(
    df: pd.DataFrame,
    *,
    target_season: int,
    target_week: int,
) -> pd.DataFrame:
    """Return labeled rows that were completed before the requested prediction week."""
    required = {"season", "week", TARGET_COL}
    missing = sorted(required.difference(df.columns))
    if missing:
        raise ValueError(f"Training data is missing required columns: {', '.join(missing)}")

    rows = df.copy()
    rows["season"] = pd.to_numeric(rows["season"], errors="coerce")
    rows["week"] = pd.to_numeric(rows["week"], errors="coerce")
    rows[TARGET_COL] = pd.to_numeric(rows[TARGET_COL], errors="coerce")

    before_cutoff = (rows["season"] < target_season) | (
        (rows["season"] == target_season) & (rows["week"] < target_week)
    )
    return rows.loc[before_cutoff & rows[TARGET_COL].notna()].copy()


def derive_calibration_roles(frame: pd.DataFrame) -> pd.Series:
    """Derive stable workload roles from lagged usage features available before lock."""
    positions = frame.get("position", pd.Series("UNKNOWN", index=frame.index)).fillna("UNKNOWN").astype(str).str.upper()

    def numeric_feature(*candidates: str) -> pd.Series:
        for candidate in candidates:
            if candidate in frame.columns:
                return pd.to_numeric(frame[candidate], errors="coerce").fillna(0.0)
        return pd.Series(0.0, index=frame.index)

    snap_share = numeric_feature("snap_share_mean_3", "snap_share_roll_mean_w3")
    target_share = numeric_feature("target_share_mean_3")
    carry_share = numeric_feature("carry_share_mean_3")
    carries = numeric_feature("carries_mean_3")
    targets = numeric_feature("targets_mean_3")

    roles = pd.Series("ROTATION", index=frame.index, dtype="object")
    roles.loc[positions == "QB"] = "POCKET"
    roles.loc[(positions == "QB") & (carries >= 4.0)] = "MOBILE"
    roles.loc[positions == "RB"] = "COMMITTEE"
    roles.loc[(positions == "RB") & ((carry_share >= 0.55) | (carries >= 14.0) | (snap_share >= 0.65))] = "LEAD"
    roles.loc[(positions == "RB") & (target_share >= 0.12) & (carry_share < 0.55)] = "RECEIVING"
    receiver_mask = positions.isin(["WR", "TE"])
    roles.loc[receiver_mask] = "SECONDARY"
    roles.loc[receiver_mask & ((target_share >= 0.22) | (targets >= 7.0) | (snap_share >= 0.78))] = "PRIMARY"
    roles.loc[receiver_mask & (snap_share > 0) & (snap_share < 0.45)] = "ROTATION"
    roles.loc[positions.isin(["DST", "DEF"])] = "DEFENSE"
    roles.loc[positions == "K"] = "KICKER"
    return roles


def blend_point_predictions(
    raw_predictions: np.ndarray,
    train_df: pd.DataFrame,
    target_df: pd.DataFrame,
) -> np.ndarray:
    """Blend model output with prior-only player history or a position baseline."""
    raw = np.asarray(raw_predictions, dtype=float)
    if len(raw) != len(target_df):
        raise ValueError("Point prediction count does not match the scoring rows.")

    labels = pd.to_numeric(train_df[TARGET_COL], errors="coerce")
    global_mean = float(labels.mean()) if labels.notna().any() else 0.0
    train_positions = train_df.get(
        "position", pd.Series("UNKNOWN", index=train_df.index)
    ).fillna("UNKNOWN").astype(str).str.upper()
    position_means = (
        pd.DataFrame({"position": train_positions, "label": labels})
        .dropna(subset=["label"])
        .groupby("position")["label"]
        .mean()
        .to_dict()
    )
    target_positions = target_df.get(
        "position", pd.Series("UNKNOWN", index=target_df.index)
    ).fillna("UNKNOWN").astype(str).str.upper()
    baselines = np.asarray(
        [float(position_means.get(position, global_mean)) for position in target_positions],
        dtype=float,
    )

    def numeric_column(name: str) -> np.ndarray:
        values = (
            target_df[name]
            if name in target_df.columns
            else pd.Series(0.0, index=target_df.index)
        )
        return pd.to_numeric(values, errors="coerce").fillna(0.0).to_numpy(dtype=float)

    games_history = numeric_column("player_games_history")
    roll3 = numeric_column("player_roll3_mean")
    roll8 = numeric_column("player_roll8_mean")
    history_anchor = (HISTORY_ROLL3_WEIGHT * roll3) + (
        HISTORY_ROLL8_WEIGHT * roll8
    )
    history_anchor = np.where(games_history >= 3.0, history_anchor, baselines)
    blended = (POINT_MODEL_RAW_WEIGHT * raw) + (
        POINT_MODEL_HISTORY_WEIGHT * history_anchor
    )
    return np.maximum(0.0, blended)


def kicker_point_estimates(
    target_df: pd.DataFrame,
) -> tuple[pd.Series, dict[str, Any]]:
    """Use prior-only kicker history, with a current-slate peer fallback."""
    positions = target_df.get(
        "position", pd.Series("UNKNOWN", index=target_df.index)
    ).fillna("UNKNOWN").astype(str).str.upper()
    kicker_rows = positions.eq("K")
    history = pd.to_numeric(
        target_df.get(
            "player_games_history", pd.Series(0.0, index=target_df.index)
        ),
        errors="coerce",
    ).fillna(0.0)
    roll3 = pd.to_numeric(
        target_df.get(
            "player_roll3_mean", pd.Series(np.nan, index=target_df.index)
        ),
        errors="coerce",
    )
    roll8 = pd.to_numeric(
        target_df.get(
            "player_roll8_mean", pd.Series(np.nan, index=target_df.index)
        ),
        errors="coerce",
    )
    estimates = (HISTORY_ROLL3_WEIGHT * roll3) + (HISTORY_ROLL8_WEIGHT * roll8)
    veteran_rows = kicker_rows & history.ge(1.0) & estimates.notna()
    fallback_rows = kicker_rows & ~veteran_rows
    if fallback_rows.any():
        peer_estimates = estimates.loc[veteran_rows]
        if peer_estimates.empty:
            names = target_df.loc[
                fallback_rows,
                "player_display_name",
            ].astype(str).tolist()
            raise ValueError(
                "Kicker projections require prior canonical game history or a "
                "current-slate peer history baseline; missing: " + ", ".join(names)
            )
        estimates.loc[fallback_rows] = float(peer_estimates.median())

    fallback_names = (
        target_df.loc[fallback_rows, "player_display_name"].astype(str).tolist()
        if fallback_rows.any()
        else []
    )
    return estimates, {
        "model": "prior_game_history_with_slate_peer_fallback",
        "roll3_weight": HISTORY_ROLL3_WEIGHT,
        "roll8_weight": HISTORY_ROLL8_WEIGHT,
        "peer_baseline": (
            float(estimates.loc[veteran_rows].median())
            if veteran_rows.any()
            else None
        ),
        "peer_history_count": int(veteran_rows.sum()),
        "fallback_player_count": int(fallback_rows.sum()),
        "fallback_players": fallback_names,
        "reason": (
            "Historical kickers are absent from the shared training matrix. "
            "Veterans use their prior-only rolling history; kickers without NFL "
            "history use the median prior-only anchor of current-slate peers."
        ),
    }


def _opportunity_units(frame: pd.DataFrame) -> pd.Series:
    """Return role-volume units without using current-game outcomes."""
    positions = frame.get(
        "position", pd.Series("UNKNOWN", index=frame.index)
    ).fillna("UNKNOWN").astype(str).str.upper()
    carries = pd.to_numeric(
        frame.get("carries_mean_3", pd.Series(0.0, index=frame.index)),
        errors="coerce",
    ).fillna(0.0).clip(lower=0.0)
    targets = pd.to_numeric(
        frame.get("targets_mean_3", pd.Series(0.0, index=frame.index)),
        errors="coerce",
    ).fillna(0.0).clip(lower=0.0)
    units = pd.Series(0.0, index=frame.index, dtype=float)
    running_backs = positions.eq("RB")
    receivers = positions.isin({"WR", "TE"})
    units.loc[running_backs] = (
        carries.loc[running_backs]
        + (RB_TARGET_OPPORTUNITY_WEIGHT * targets.loc[running_backs])
    )
    units.loc[receivers] = targets.loc[receivers]
    return units


def _fit_opportunity_anchor_models(
    train_df: pd.DataFrame,
) -> tuple[dict[str, IsotonicRegression], dict[str, Any]]:
    """Fit monotonic role-volume response curves from prior training rows."""
    labels = pd.to_numeric(train_df[TARGET_COL], errors="coerce")
    positions = train_df.get(
        "position", pd.Series("UNKNOWN", index=train_df.index)
    ).fillna("UNKNOWN").astype(str).str.upper()
    units = _opportunity_units(train_df)
    evidence = pd.DataFrame(
        {"position": positions, "label": labels, "units": units}
    ).dropna(subset=["label"])
    evidence = evidence.loc[
        evidence["position"].isin({"RB", "WR", "TE"})
        & evidence["units"].gt(0.0)
    ].copy()
    models: dict[str, IsotonicRegression] = {}
    training_rows: dict[str, int] = {}
    reference_points: dict[str, dict[str, float]] = {}
    for position, position_rows in evidence.groupby("position"):
        if len(position_rows) < 2 or position_rows["units"].nunique() < 2:
            continue
        model = IsotonicRegression(y_min=0.0, out_of_bounds="clip")
        model.fit(
            position_rows["units"].to_numpy(dtype=float),
            position_rows["label"].to_numpy(dtype=float),
        )
        models[str(position)] = model
        training_rows[str(position)] = int(len(position_rows))
        examples = [1.0, 3.0, 5.0, 7.0, 10.0, 15.0]
        reference_points[str(position)] = {
            f"{units:g}": float(model.predict([units])[0])
            for units in examples
        }
    return models, {
        "method": "prior_training_position_isotonic_opportunity_curve",
        "rb_target_opportunity_weight": RB_TARGET_OPPORTUNITY_WEIGHT,
        "veteran_anchor_weight": VETERAN_OPPORTUNITY_ANCHOR_WEIGHT,
        "low_history_anchor_weight": LOW_HISTORY_OPPORTUNITY_ANCHOR_WEIGHT,
        "activation": (
            "current carry/target share or availability evidence changes a team allocation"
        ),
        "position_training_rows": training_rows,
        "position_reference_points": reference_points,
    }


def opportunity_point_contract(train_df: pd.DataFrame) -> dict[str, Any]:
    """Describe prior-only position anchors used for current role evidence."""
    _, contract = _fit_opportunity_anchor_models(train_df)
    return contract


def apply_opportunity_point_adjustment(
    base_predictions: np.ndarray,
    train_df: pd.DataFrame,
    target_df: pd.DataFrame,
) -> tuple[np.ndarray, pd.DataFrame]:
    """Blend explicit current role evidence into otherwise historical means."""
    base = np.asarray(base_predictions, dtype=float)
    if len(base) != len(target_df):
        raise ValueError("Point prediction count does not match the scoring rows.")
    models, _ = _fit_opportunity_anchor_models(train_df)
    positions = target_df.get(
        "position", pd.Series("UNKNOWN", index=target_df.index)
    ).fillna("UNKNOWN").astype(str).str.upper().reset_index(drop=True)
    units = _opportunity_units(target_df).reset_index(drop=True)
    history = pd.to_numeric(
        target_df.get(
            "player_games_history", pd.Series(0.0, index=target_df.index)
        ),
        errors="coerce",
    ).fillna(0.0).reset_index(drop=True)
    context_applied = target_df.get(
        "pregame_opportunity_context_applied",
        pd.Series(False, index=target_df.index),
    ).fillna(False).astype(bool).reset_index(drop=True)

    adjusted = base.copy()
    anchors = np.full(len(base), np.nan, dtype=float)
    weights = np.zeros(len(base), dtype=float)
    for index in range(len(base)):
        position = str(positions.iloc[index])
        if not bool(context_applied.iloc[index]) or position not in models:
            continue
        anchor = max(
            0.0,
            float(models[position].predict([float(units.iloc[index])])[0]),
        )
        weight = (
            LOW_HISTORY_OPPORTUNITY_ANCHOR_WEIGHT
            if float(history.iloc[index]) < 3.0
            else VETERAN_OPPORTUNITY_ANCHOR_WEIGHT
        )
        anchors[index] = anchor
        weights[index] = weight
        adjusted[index] = ((1.0 - weight) * base[index]) + (weight * anchor)

    details = pd.DataFrame(
        {
            "pregame_point_mean_before_opportunity": base,
            "pregame_opportunity_point_anchor": anchors,
            "pregame_opportunity_point_weight": weights,
            "pregame_point_mean_after_opportunity": adjusted,
        }
    )
    return np.maximum(0.0, adjusted), details


def point_estimate_contract(train_df: pd.DataFrame) -> dict[str, Any]:
    """Return the persisted point-model contract and its training baselines."""
    labels = pd.to_numeric(train_df[TARGET_COL], errors="coerce")
    positions = train_df.get(
        "position", pd.Series("UNKNOWN", index=train_df.index)
    ).fillna("UNKNOWN").astype(str).str.upper()
    summary = pd.DataFrame({"position": positions, "label": labels}).dropna(
        subset=["label"]
    )
    return {
        "model": "gradient_boosting_with_position_indicators",
        "raw_model_weight": POINT_MODEL_RAW_WEIGHT,
        "history_anchor_weight": POINT_MODEL_HISTORY_WEIGHT,
        "history_anchor": (
            f"{HISTORY_ROLL3_WEIGHT:.2f} * player_roll3_mean + "
            f"{HISTORY_ROLL8_WEIGHT:.2f} * player_roll8_mean"
        ),
        "history_minimum_games": 3,
        "history_fallback": "position_training_mean",
        "position_training_rows": {
            str(position): int(len(rows))
            for position, rows in summary.groupby("position")
        },
        "position_training_means": {
            str(position): float(rows["label"].mean())
            for position, rows in summary.groupby("position")
        },
        "training_zero_rate": float((summary["label"] == 0).mean())
        if not summary.empty
        else 0.0,
        "pregame_opportunity_adjustment": opportunity_point_contract(train_df),
    }


@dataclass(frozen=True)
class ResidualCalibrationProfile:
    position: str
    sample_size: int
    source: str
    residual_quantiles: dict[str, float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "position": self.position,
            "sample_size": self.sample_size,
            "source": self.source,
            "residual_quantiles": self.residual_quantiles,
        }


def generate_walk_forward_residuals(
    train_df: pd.DataFrame,
    feature_cols: list[str],
    *,
    min_train_rows: int = MIN_WALK_FORWARD_TRAIN_ROWS,
) -> pd.DataFrame:
    """Generate strictly chronological out-of-fold residuals for calibration."""
    required = {"season", "week", TARGET_COL, *feature_cols}
    missing = sorted(required.difference(train_df.columns))
    if missing:
        raise ValueError(f"Calibration data is missing required columns: {', '.join(missing)}")

    rows = train_df.copy()
    rows["season"] = pd.to_numeric(rows["season"], errors="coerce")
    rows["week"] = pd.to_numeric(rows["week"], errors="coerce")
    rows[TARGET_COL] = pd.to_numeric(rows[TARGET_COL], errors="coerce")
    rows = rows.dropna(subset=["season", "week", TARGET_COL])
    if rows.empty:
        return pd.DataFrame()

    if "position" not in rows.columns:
        rows["position"] = "UNKNOWN"
    rows["position"] = rows["position"].fillna("UNKNOWN").astype(str).str.upper()
    rows["calibration_role"] = derive_calibration_roles(rows)
    periods = sorted({(int(row.season), int(row.week)) for row in rows[["season", "week"]].itertuples(index=False)})
    residual_frames: list[pd.DataFrame] = []

    for validation_season, validation_week in periods:
        prior_mask = (rows["season"] < validation_season) | (
            (rows["season"] == validation_season) & (rows["week"] < validation_week)
        )
        validation_mask = (rows["season"] == validation_season) & (rows["week"] == validation_week)
        prior = rows.loc[prior_mask]
        validation = rows.loc[validation_mask]
        if len(prior) < min_train_rows or validation.empty:
            continue

        X_train = prior[feature_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
        y_train = prior[TARGET_COL].astype(float)
        X_validation = validation[feature_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
        model = GradientBoostingRegressor(random_state=42)
        model.fit(X_train, y_train)
        raw_predictions = model.predict(X_validation)
        point_predictions = blend_point_predictions(
            raw_predictions,
            prior,
            validation,
        )

        residual_frame = validation[["season", "week", "position", "calibration_role"]].copy()
        if "player_id" in validation.columns:
            residual_frame["player_id"] = validation["player_id"].astype(str)
        residual_frame["actual"] = validation[TARGET_COL].astype(float).to_numpy()
        residual_frame["point_prediction"] = point_predictions
        residual_frame["residual"] = residual_frame["actual"] - residual_frame["point_prediction"]
        latest_prior = prior.sort_values(["season", "week"]).iloc[-1]
        residual_frame["training_through_season"] = int(latest_prior["season"])
        residual_frame["training_through_week"] = int(latest_prior["week"])
        residual_frames.append(residual_frame)

    if not residual_frames:
        return pd.DataFrame()
    return pd.concat(residual_frames, ignore_index=True)


def build_position_calibration(
    residuals: pd.DataFrame,
    train_df: pd.DataFrame,
    *,
    min_position_rows: int = MIN_POSITION_CALIBRATION_ROWS,
    min_role_rows: int = MIN_ROLE_CALIBRATION_ROWS,
) -> tuple[dict[str, ResidualCalibrationProfile], dict[str, Any]]:
    """Fit position-aware residual quantiles with shrinkage to a global fallback."""
    calibration_rows = residuals.copy()
    method = "walk_forward_residual_quantiles"
    if calibration_rows.empty:
        fallback = train_df.copy()
        fallback[TARGET_COL] = pd.to_numeric(fallback[TARGET_COL], errors="coerce")
        fallback = fallback.dropna(subset=[TARGET_COL])
        if "position" not in fallback.columns:
            fallback["position"] = "UNKNOWN"
        fallback["position"] = fallback["position"].fillna("UNKNOWN").astype(str).str.upper()
        fallback["calibration_role"] = derive_calibration_roles(fallback)
        position_medians = fallback.groupby("position")[TARGET_COL].transform("median")
        fallback["residual"] = fallback[TARGET_COL] - position_medians
        calibration_rows = fallback[["position", "calibration_role", "residual"]].copy()
        method = "historical_position_dispersion_fallback"

    if "position" not in calibration_rows.columns:
        calibration_rows["position"] = "UNKNOWN"
    calibration_rows["position"] = calibration_rows["position"].fillna("UNKNOWN").astype(str).str.upper()
    if "calibration_role" not in calibration_rows.columns:
        calibration_rows["calibration_role"] = "ROTATION"
    calibration_rows["calibration_role"] = calibration_rows["calibration_role"].fillna("ROTATION").astype(str).str.upper()
    calibration_rows["residual"] = pd.to_numeric(calibration_rows["residual"], errors="coerce")
    calibration_rows = calibration_rows.replace([np.inf, -np.inf], np.nan).dropna(subset=["residual"])
    if calibration_rows.empty:
        calibration_rows = pd.DataFrame({"position": ["UNKNOWN"], "residual": [0.0]})
        method = "zero_residual_fallback"

    quantile_names = list(CALIBRATION_QUANTILES)
    quantile_levels = list(CALIBRATION_QUANTILES.values())

    def quantiles_for(frame: pd.DataFrame) -> dict[str, float]:
        values = np.quantile(frame["residual"].to_numpy(dtype=float), quantile_levels)
        return {name: float(value) for name, value in zip(quantile_names, values, strict=True)}

    global_quantiles = quantiles_for(calibration_rows)
    profiles: dict[str, ResidualCalibrationProfile] = {
        "__ALL__": ResidualCalibrationProfile(
            position="__ALL__",
            sample_size=len(calibration_rows),
            source=method,
            residual_quantiles=global_quantiles,
        )
    }

    known_positions = sorted(
        set(calibration_rows["position"].tolist())
        | set(train_df.get("position", pd.Series(dtype=str)).dropna().astype(str).str.upper().tolist())
    )
    for position in known_positions:
        position_rows = calibration_rows.loc[calibration_rows["position"] == position]
        if position_rows.empty:
            profiles[position] = ResidualCalibrationProfile(
                position=position,
                sample_size=0,
                source=f"{method}_global_fallback",
                residual_quantiles=global_quantiles.copy(),
            )
            continue
        position_quantiles = quantiles_for(position_rows)
        position_weight = min(1.0, len(position_rows) / max(1, min_position_rows))
        blended_values = [
            position_weight * position_quantiles[name] + (1.0 - position_weight) * global_quantiles[name]
            for name in quantile_names
        ]
        blended_values = np.maximum.accumulate(blended_values)
        profiles[position] = ResidualCalibrationProfile(
            position=position,
            sample_size=len(position_rows),
            source=method if position_weight == 1.0 else f"{method}_shrunk_to_global",
            residual_quantiles={
                name: float(value) for name, value in zip(quantile_names, blended_values, strict=True)
            },
        )

    for (position, role), role_rows in calibration_rows.groupby(["position", "calibration_role"]):
        parent_profile = profiles.get(position, profiles["__ALL__"])
        role_quantiles = quantiles_for(role_rows)
        role_weight = min(1.0, len(role_rows) / max(1, min_role_rows))
        blended_values = [
            role_weight * role_quantiles[name]
            + (1.0 - role_weight) * parent_profile.residual_quantiles[name]
            for name in quantile_names
        ]
        blended_values = np.maximum.accumulate(blended_values)
        profile_key = f"{position}|{role}"
        profiles[profile_key] = ResidualCalibrationProfile(
            position=profile_key,
            sample_size=len(role_rows),
            source=(
                f"{method}_position_role"
                if role_weight == 1.0
                else f"{method}_role_shrunk_to_position"
            ),
            residual_quantiles={
                name: float(value)
                for name, value in zip(quantile_names, blended_values, strict=True)
            },
        )

    coverage_by_position: dict[str, dict[str, float | int]] = {}
    for position, position_rows in calibration_rows.groupby("position"):
        profile = profiles.get(position, profiles["__ALL__"])
        values = position_rows["residual"].to_numpy(dtype=float)
        quantiles = profile.residual_quantiles
        coverage_by_position[position] = {
            "samples": len(values),
            "p10_observed": float(np.mean(values <= quantiles["p10"])),
            "p25_observed": float(np.mean(values <= quantiles["p25"])),
            "p50_observed": float(np.mean(values <= quantiles["p50"])),
            "p75_observed": float(np.mean(values <= quantiles["p75"])),
            "p90_observed": float(np.mean(values <= quantiles["p90"])),
            "p10_p90_coverage": float(
                np.mean((values >= quantiles["p10"]) & (values <= quantiles["p90"]))
            ),
            "mae": float(np.mean(np.abs(values))),
        }

    coverage_by_role: dict[str, dict[str, float | int]] = {}
    for (position, role), role_rows in calibration_rows.groupby(["position", "calibration_role"]):
        profile_key = f"{position}|{role}"
        profile = profiles.get(profile_key, profiles.get(position, profiles["__ALL__"]))
        values = role_rows["residual"].to_numpy(dtype=float)
        quantiles = profile.residual_quantiles
        coverage_by_role[profile_key] = {
            "samples": len(values),
            "p10_observed": float(np.mean(values <= quantiles["p10"])),
            "p25_observed": float(np.mean(values <= quantiles["p25"])),
            "p50_observed": float(np.mean(values <= quantiles["p50"])),
            "p75_observed": float(np.mean(values <= quantiles["p75"])),
            "p90_observed": float(np.mean(values <= quantiles["p90"])),
            "p10_p90_coverage": float(
                np.mean((values >= quantiles["p10"]) & (values <= quantiles["p90"]))
            ),
            "mae": float(np.mean(np.abs(values))),
        }

    position_samples = [int(value["samples"]) for value in coverage_by_position.values()]
    position_coverages = [float(value["p10_p90_coverage"]) for value in coverage_by_position.values()]
    promotion_checks = {
        "walk_forward_rows_at_least_500": len(residuals) >= 500,
        "each_position_has_at_least_30_rows": bool(position_samples) and min(position_samples) >= 30,
        "weighted_p10_p90_coverage_within_8_points": bool(position_coverages)
        and abs(
            sum(
                float(value["p10_p90_coverage"]) * int(value["samples"])
                for value in coverage_by_position.values()
            )
            / max(1, sum(position_samples))
            - 0.80
        ) <= 0.08,
    }

    metrics = {
        "method": method,
        "walk_forward_rows": len(residuals),
        "calibration_rows": len(calibration_rows),
        "min_position_rows": min_position_rows,
        "min_role_rows": min_role_rows,
        "profiles": {key: profile.as_dict() for key, profile in profiles.items()},
        "coverage_by_position": coverage_by_position,
        "coverage_by_role": coverage_by_role,
        "promotion_gate": {
            "status": "passed" if all(promotion_checks.values()) else "blocked",
            "checks": promotion_checks,
            "policy": "diagnostic only; model promotion remains explicit",
        },
    }
    return profiles, metrics


def apply_residual_calibration(
    point_prediction: float,
    profile: ResidualCalibrationProfile,
) -> dict[str, float]:
    """Apply a residual profile and return monotonic, non-negative quantiles."""
    values = [
        max(0.0, float(point_prediction) + profile.residual_quantiles[name])
        for name in CALIBRATION_QUANTILES
    ]
    values = np.maximum.accumulate(values)
    return {
        name: float(value)
        for name, value in zip(CALIBRATION_QUANTILES, values, strict=True)
    }


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


def _safe_float(value) -> float:
    try:
        if value is None or pd.isna(value):
            return 0.0
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _optional_text(value) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    normalized = str(value).strip()
    return normalized or None


def prediction_game_id(row: dict, *, season: int, week: int) -> str:
    """Build a stable game key when the legacy feature row has no canonical game ID."""
    existing = _optional_text(row.get("game_id"))
    if existing:
        return existing
    team = (_optional_text(row.get("recent_team")) or "").upper()
    opponent = (_optional_text(row.get("opponent_team")) or "").upper()
    if team and opponent:
        left, right = sorted((team, opponent))
        return f"{season}_{week:02d}_{left}_{right}"
    player_id = _optional_text(row.get("player_id")) or "unknown"
    return f"{season}_{week:02d}_unknown_{player_id}"


@dataclass(frozen=True)
class PredictionRunContext:
    feature_run_id: str
    model_run_id: str
    projection_run_id: str
    data_cutoff_at: datetime
    feature_set_hash: str
    code_hash: str


def prediction_code_hash() -> str:
    """Hash the prediction implementation recorded by newly persisted model runs."""
    return hashlib.sha256(
        Path(__file__).read_bytes()
        + Path(__file__).with_name("canonical_projection_inputs.py").read_bytes()
    ).hexdigest()


def create_prediction_run_context(
    feature_cols: Iterable[str],
    *,
    data_cutoff_at: datetime | None = None,
    feature_run_id: str | None = None,
    model_run_id: str | None = None,
    projection_run_id: str | None = None,
) -> PredictionRunContext:
    cutoff = data_cutoff_at or datetime.now(timezone.utc)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=timezone.utc)
    feature_set_hash = hashlib.sha256(
        "\n".join(sorted(str(col) for col in feature_cols)).encode("utf-8")
    ).hexdigest()
    return PredictionRunContext(
        feature_run_id=feature_run_id or str(uuid.uuid4()),
        model_run_id=model_run_id or str(uuid.uuid4()),
        projection_run_id=projection_run_id or str(uuid.uuid4()),
        data_cutoff_at=cutoff,
        feature_set_hash=feature_set_hash,
        code_hash=prediction_code_hash(),
    )


@dataclass
class PredictionRecord:
    player_id: str
    player_master_id: str
    player_display_name: str
    position: str
    recent_team: str
    opponent_team: str
    season: int
    week: int
    predicted_mean: float
    predicted_p10: float
    predicted_p25: float
    predicted_p50: float
    predicted_p75: float
    predicted_p90: float
    model: str
    feature_run_id: str
    model_run_id: str
    projection_run_id: str
    data_cutoff_at: datetime
    game_id: str
    team_implied_total: float = 0.0
    team_spread: float = 0.0
    game_total: float = 0.0
    opp_pts_allowed_pos_3: float = 0.0
    opp_pts_allowed_pos_5: float = 0.0
    run_funnel: float = 0.0
    pass_funnel: float = 0.0
    adj_mean: float = 0.0
    calibration_method: str = ""
    calibration_position: str = ""
    calibration_role: str = ""
    calibration_sample_size: int = 0


@dataclass
class PredictionRunResult:
    records: List[PredictionRecord]
    feature_run_id: str | None = None
    model_run_id: str | None = None
    projection_run_id: str | None = None
    data_cutoff_at: datetime | None = None
    target_persisted: bool = False
    calibration_metrics: dict[str, Any] | None = None

    def __len__(self) -> int:
        return len(self.records)


class PredictionsService:
    """Train position-aware models and persist append-only target projection runs."""

    def __init__(self, connection_string: str | None = None) -> None:
        self.connection_string = connection_string or get_connection_string()
        self.engine = create_engine(self.connection_string)

    def fetch_completed_run_summary(
        self,
        projection_run_id: str,
    ) -> dict[str, Any] | None:
        """Reload the immutable run contract after a worker/result-write crash."""
        inspector = inspect(self.engine)
        if not inspector.has_table("projection_run", schema="target"):
            return None
        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT pr.projection_run_id, pr.model_run_id,
                           mr.feature_run_id, pr.season, pr.week, pr.row_count,
                           pr.data_cutoff_at, mr.params_json
                    FROM target.projection_run pr
                    JOIN target.model_run mr
                      ON mr.model_run_id = pr.model_run_id
                    WHERE pr.projection_run_id = :projection_run_id
                      AND pr.status = 'completed'
                    """
                ),
                {"projection_run_id": projection_run_id},
            ).mappings().first()
        if row is None:
            return None
        params = row.get("params_json") or {}
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
                params = {}
        calibration = (
            params.get("calibration", {})
            if isinstance(params, dict)
            else {}
        )
        return {
            "season": int(row["season"]),
            "week": int(row["week"]),
            "rows_written": int(row["row_count"]),
            "message": "Predictions generated",
            "feature_run_id": str(row["feature_run_id"]),
            "model_run_id": str(row["model_run_id"]),
            "projection_run_id": str(row["projection_run_id"]),
            "data_cutoff_at": row.get("data_cutoff_at"),
            "target_persisted": True,
            "calibration_metrics": calibration,
        }

    @staticmethod
    def _normalize_team(team: str | None) -> str:
        if not team:
            return ""
        team = team.upper()
        aliases = {
            "LA": "LAR",
            "STL": "LAR",
            "SD": "LAC",
            "JAC": "JAX",
            "WSH": "WAS",
            "OAK": "LV",
        }
        return aliases.get(team, team)

    def _load_features(self, season: int) -> pd.DataFrame:
        try:
            with self.engine.begin() as connection:
                df = pd.read_sql(
                    text("SELECT * FROM predictive_features WHERE season <= :season"),
                    connection,
                    params={"season": season},
                )
            # Normalize dtypes for downstream filters
            if "player_master_id" in df.columns:
                df["player_id"] = df["player_master_id"].fillna(df.get("player_id")).astype(str)
            for col in ("season", "week"):
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            if TARGET_COL in df.columns:
                df[TARGET_COL] = pd.to_numeric(df[TARGET_COL], errors="coerce")
            return df
        except ProgrammingError as exc:
            logging.error("predictive_features table missing expected columns: %s", exc)
            return pd.DataFrame()

    def _prepare_xy(self, df: pd.DataFrame):
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if TARGET_COL not in numeric_cols:
            raise ValueError(f"{TARGET_COL} not found in predictive_features")
        feature_cols = [col for col in numeric_cols if col not in {TARGET_COL, "week", "season"}]
        return feature_cols

    def _train_model(self, X: pd.DataFrame, y: pd.Series) -> GradientBoostingRegressor:
        model = GradientBoostingRegressor(random_state=42)
        model.fit(X, y)
        return model

    def _predict_point_estimates(
        self,
        model: GradientBoostingRegressor,
        train_df: pd.DataFrame,
        target_df: pd.DataFrame,
        feature_cols: list[str],
    ) -> np.ndarray:
        """Predict position-aware means with a prior-only player-history anchor."""
        raw_predictions = model.predict(target_df[feature_cols])
        preds = blend_point_predictions(raw_predictions, train_df, target_df)
        y_train = pd.to_numeric(train_df[TARGET_COL], errors="coerce")
        print(
            f"[predictions] train target stats min/med/mean/max="
            f"{y_train.min():.2f}/{y_train.median():.2f}/{y_train.mean():.2f}/{y_train.max():.2f}"
        )
        print(
            f"[predictions] raw model preds min/med/mean/max="
            f"{raw_predictions.min():.2f}/{np.median(raw_predictions):.2f}/"
            f"{raw_predictions.mean():.2f}/{raw_predictions.max():.2f}"
        )
        print(
            f"[predictions] history-anchored preds min/med/mean/max="
            f"{preds.min():.2f}/{np.median(preds):.2f}/{preds.mean():.2f}/{preds.max():.2f}"
        )
        return preds

    def _persist_target_prediction_run(
        self,
        *,
        context: PredictionRunContext,
        season: int,
        week: int,
        slate: str,
        feature_cols: list[str],
        feature_lineage_cols: list[str] | None = None,
        train_df: pd.DataFrame,
        source_features: pd.DataFrame,
        projections: pd.DataFrame,
        calibration_metrics: dict[str, Any] | None = None,
        source_versions: dict[str, Any] | None = None,
    ) -> bool:
        """Persist append-only active prediction lineage in the target schema."""
        validate_target_schema(
            self.engine,
            consumer=type(self).__name__,
            required_tables=(
                "dim_player",
                "feature_generation_run",
                "feature_player_game",
                "model_registry",
                "model_run",
                "projection_run",
                "active_projection_run",
                "player_projection",
            ),
        )
        try:
            with self.engine.begin() as connection:
                training_start = None
                training_end = None
                if not train_df.empty:
                    ordered = train_df.sort_values(["season", "week"])
                    first = ordered.iloc[0]
                    last = ordered.iloc[-1]
                    training_start = f"{int(first['season'])}-W{int(first['week']):02d}"
                    training_end = f"{int(last['season'])}-W{int(last['week']):02d}"

                connection.execute(
                    text(
                        """
                        INSERT INTO target.feature_generation_run
                            (feature_run_id, training_cutoff, source_versions_json,
                             feature_set_hash, status)
                        VALUES
                            (:feature_run_id, :training_cutoff,
                             CAST(:source_versions_json AS JSONB), :feature_set_hash, 'completed')
                        """
                    ),
                    {
                        "feature_run_id": context.feature_run_id,
                        "training_cutoff": context.data_cutoff_at,
                        "source_versions_json": json.dumps(
                            source_versions or {
                                "source": "public.predictive_features",
                                "target_season": season,
                                "target_week": week,
                                "leakage_policy": "labeled rows strictly before target season/week",
                            },
                            sort_keys=True,
                        ),
                        "feature_set_hash": context.feature_set_hash,
                    },
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO target.model_registry
                            (model_id, model_name, model_version, trained_on_start,
                             trained_on_end, feature_set_hash, metrics_json, artifact_uri)
                        VALUES
                            (:model_id, 'Position-aware full-team opportunity-context gradient boosting', 'v4.1-team-opportunity-context', :trained_on_start,
                             :trained_on_end, :feature_set_hash, CAST(:metrics_json AS JSONB), NULL)
                        ON CONFLICT (model_id) DO UPDATE SET
                            trained_on_start = EXCLUDED.trained_on_start,
                            trained_on_end = EXCLUDED.trained_on_end,
                            feature_set_hash = EXCLUDED.feature_set_hash,
                            metrics_json = EXCLUDED.metrics_json
                        """
                    ),
                    {
                        "model_id": ACTIVE_MODEL_ID,
                        "trained_on_start": training_start,
                        "trained_on_end": training_end,
                        "feature_set_hash": context.feature_set_hash,
                        "metrics_json": json.dumps(
                            _json_safe(calibration_metrics or {}),
                            sort_keys=True,
                            allow_nan=False,
                        ),
                    },
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO target.model_run
                            (model_run_id, model_id, feature_run_id, data_cutoff_at,
                             params_json, status)
                        VALUES
                            (:model_run_id, :model_id, :feature_run_id, :data_cutoff_at,
                             CAST(:params_json AS JSONB), 'completed')
                        """
                    ),
                    {
                        "model_run_id": context.model_run_id,
                        "model_id": ACTIVE_MODEL_ID,
                        "feature_run_id": context.feature_run_id,
                        "data_cutoff_at": context.data_cutoff_at,
                        "params_json": json.dumps(
                            {
                                "algorithm": "GradientBoostingRegressor",
                                "random_state": 42,
                                "training_rows": len(train_df),
                                "feature_columns": feature_cols,
                                "feature_lineage_columns": feature_lineage_cols or [],
                                "code_hash": context.code_hash,
                                "point_estimate": point_estimate_contract(train_df),
                                "training_filter": _json_safe(
                                    (source_versions or {}).get("participation_filter", {})
                                ),
                                "opportunity_features": _json_safe(
                                    (source_versions or {}).get("opportunity_features", {})
                                ),
                                "pregame_context": _json_safe(
                                    (source_versions or {}).get("pregame_context", {})
                                ),
                                "uncertainty_model": "position-and-role-aware walk-forward residual quantiles",
                                "calibration": _json_safe(calibration_metrics or {}),
                            },
                            sort_keys=True,
                        ),
                    },
                )

                feature_rows = []
                projection_rows = []
                source_features = source_features.reset_index(drop=True)
                projections = projections.reset_index(drop=True)
                for index, projection in projections.iterrows():
                    source = source_features.iloc[index] if index < len(source_features) else pd.Series()
                    row_dict = projection.to_dict()
                    game_id = str(row_dict["game_id"])
                    player_id = str(row_dict["player_id"])
                    persisted_feature_columns = list(
                        dict.fromkeys([*feature_cols, *(feature_lineage_cols or [])])
                    )
                    feature_payload = {
                        col: _json_safe(source.get(col))
                        for col in persisted_feature_columns
                        if col in source.index
                    }
                    feature_rows.append(
                        {
                            "feature_run_id": context.feature_run_id,
                            "season": season,
                            "week": week,
                            "game_id": game_id,
                            "player_id": player_id,
                            "feature_json": json.dumps(feature_payload, sort_keys=True, allow_nan=False),
                        }
                    )
                    p10 = _safe_float(row_dict.get("predicted_p10"))
                    mean = _safe_float(row_dict.get("adj_mean_final", row_dict.get("predicted_mean")))
                    median = _safe_float(row_dict.get("predicted_p50", mean))
                    p90 = _safe_float(row_dict.get("predicted_p90"))
                    stddev = max(0.0, (p90 - p10) / 2.56)
                    projection_rows.append(
                        {
                            "projection_run_id": context.projection_run_id,
                            "model_run_id": context.model_run_id,
                            "season": season,
                            "week": week,
                            "game_id": game_id,
                            "slate_id": slate,
                            "player_id": player_id,
                            "mean": mean,
                            "median": median,
                            "p10": p10,
                            "p25": _safe_float(
                                row_dict.get("predicted_p25", max(0.0, median - 0.674 * stddev))
                            ),
                            "p75": _safe_float(
                                row_dict.get("predicted_p75", median + 0.674 * stddev)
                            ),
                            "p90": p90,
                            "stddev": stddev,
                            "calibration_method": row_dict.get("calibration_method"),
                            "calibration_position": row_dict.get("calibration_position"),
                            "calibration_role": row_dict.get("calibration_role"),
                            "calibration_sample_size": int(
                                row_dict.get("calibration_sample_size", 0) or 0
                            ),
                            "data_cutoff_at": context.data_cutoff_at,
                        }
                    )

                if feature_rows:
                    connection.execute(
                        text(
                            """
                            INSERT INTO target.dim_player
                                (player_id, full_name, primary_position,
                                 normalized_name, created_at, updated_at)
                            SELECT player_master_id, full_name, position,
                                   normalized_name, created_at, updated_at
                            FROM public.player_master
                            WHERE player_master_id = ANY(:player_ids)
                            ON CONFLICT (player_id) DO UPDATE SET
                                full_name = COALESCE(
                                    NULLIF(EXCLUDED.full_name, ''),
                                    target.dim_player.full_name
                                ),
                                primary_position = COALESCE(
                                    NULLIF(EXCLUDED.primary_position, ''),
                                    target.dim_player.primary_position
                                ),
                                normalized_name = COALESCE(
                                    NULLIF(EXCLUDED.normalized_name, ''),
                                    target.dim_player.normalized_name
                                ),
                                updated_at = GREATEST(
                                    target.dim_player.updated_at,
                                    EXCLUDED.updated_at
                                )
                            """
                        ),
                        {"player_ids": [row["player_id"] for row in feature_rows]},
                    )
                    connection.execute(
                        text(
                            """
                            INSERT INTO target.feature_player_game
                                (feature_run_id, season, week, game_id, player_id, feature_json)
                            VALUES
                                (:feature_run_id, :season, :week, :game_id, :player_id,
                                 CAST(:feature_json AS JSONB))
                            """
                        ),
                        feature_rows,
                    )
                if projection_rows:
                    connection.execute(
                        text(
                            """
                            INSERT INTO target.player_projection
                                (projection_run_id, model_run_id, season, week, game_id,
                                 slate_id, player_id, mean, median, p10, p25, p75, p90,
                                 stddev, ceiling_prob, calibration_method, calibration_position,
                                 calibration_role, calibration_sample_size, data_cutoff_at)
                            VALUES
                                (:projection_run_id, :model_run_id, :season, :week, :game_id,
                                 :slate_id, :player_id, :mean, :median, :p10, :p25, :p75,
                                 :p90, :stddev, NULL, :calibration_method, :calibration_position,
                                 :calibration_role, :calibration_sample_size, :data_cutoff_at)
                            """
                        ),
                        projection_rows,
                    )
                    connection.execute(
                        text(
                            """
                            INSERT INTO target.projection_run
                                (projection_run_id, model_run_id, season, week, slate_id,
                                 row_count, data_cutoff_at, status)
                            VALUES
                                (:projection_run_id, :model_run_id, :season, :week, :slate_id,
                                 :row_count, :data_cutoff_at, 'completed')
                            """
                        ),
                        {
                            "projection_run_id": context.projection_run_id,
                            "model_run_id": context.model_run_id,
                            "season": season,
                            "week": week,
                            "slate_id": slate,
                            "row_count": len(projection_rows),
                            "data_cutoff_at": context.data_cutoff_at,
                        },
                    )
                    connection.execute(
                        text(
                            """
                            INSERT INTO target.active_projection_run
                                (season, week, slate_id, projection_run_id,
                                 selection_reason, selected_at)
                            VALUES
                                (:season, :week, :slate_id, :projection_run_id,
                                 'prediction_run_completed', now())
                            ON CONFLICT (season, week, slate_id) DO NOTHING
                            """
                        ),
                        {
                            "season": season,
                            "week": week,
                            "slate_id": slate,
                            "projection_run_id": context.projection_run_id,
                        },
                    )
            return True
        except Exception as exc:  # noqa: BLE001 - surface persistence state in the run response
            logging.warning("Failed to persist target prediction lineage: %s", exc)
            return False

    def _train_canonical(
        self, *, season, week, positions, slate, data_cutoff_at,
        feature_run_id, model_run_id, projection_run_id,
    ) -> PredictionRunResult:
        from .canonical_projection_inputs import (
            FEATURE_COLUMNS,
            PREGAME_LINEAGE_COLUMNS,
            load_inputs,
        )

        context = create_prediction_run_context(
            FEATURE_COLUMNS, data_cutoff_at=data_cutoff_at,
            feature_run_id=feature_run_id, model_run_id=model_run_id,
            projection_run_id=projection_run_id,
        )
        train, target, sources = load_inputs(
            self.engine, season=season, week=week, slate=slate,
            cutoff=context.data_cutoff_at, positions=list(positions) if positions else None,
        )
        residuals = generate_walk_forward_residuals(train, FEATURE_COLUMNS)
        profiles, metrics = build_position_calibration(residuals, train)
        metrics["input_coverage"] = {
            "projected_players": len(target),
            "unresolved_salary_source_keys": sources["unresolved_salary_source_keys"],
            "excluded_positions": sources["excluded_positions"],
        }
        metrics["point_estimate"] = point_estimate_contract(train)
        metrics["training_filter"] = sources.get("participation_filter", {})
        metrics["salary_status_policy"] = sources.get("salary_status_policy", {})
        metrics["opportunity_features"] = sources.get("opportunity_features", {})
        metrics["pregame_context"] = sources.get("pregame_context", {})
        kicker_rows = target["position"].astype(str).str.upper().eq("K")
        kicker_estimates = pd.Series(np.nan, index=target.index, dtype=float)
        if kicker_rows.any():
            kicker_estimates, metrics["kicker_point_estimate"] = (
                kicker_point_estimates(target)
            )
        model = self._train_model(train[FEATURE_COLUMNS], train[TARGET_COL])
        means = self._predict_point_estimates(model, train, target, FEATURE_COLUMNS)
        means, opportunity_details = apply_opportunity_point_adjustment(
            means,
            train,
            target,
        )
        for column in opportunity_details.columns:
            target[column] = opportunity_details[column].to_numpy()
        roles = derive_calibration_roles(target)
        records = []
        for index, row in target.iterrows():
            position = str(row["position"])
            derived_role = str(roles.iloc[index])
            explicit_role = str(row.get("pregame_role_label") or "").upper()
            role = (
                explicit_role
                if explicit_role
                in {"LEAD", "COMMITTEE", "PRIMARY", "SECONDARY", "ROTATION"}
                else derived_role
            )
            profile = profiles.get(f"{position}|{role}", profiles.get(position, profiles["__ALL__"]))
            availability_probability = float(
                row.get("pregame_availability_probability", 1.0) or 0.0
            )
            start_probability = (
                float(row.get("pregame_start_probability", 1.0) or 0.0)
                if position == "QB"
                else 1.0
            )
            participation_probability = (
                availability_probability * start_probability
                if position == "QB"
                else availability_probability
            )
            conditional_mean = max(0.0, float(means[index]))
            if position == "K":
                conditional_mean = max(0.0, float(kicker_estimates.loc[index]))
            conditional_quantiles = apply_residual_calibration(
                conditional_mean, profile
            )
            mean = conditional_mean * participation_probability
            quantiles = {
                key: value * participation_probability
                for key, value in conditional_quantiles.items()
            }
            records.append(PredictionRecord(
                player_id=str(row["player_id"]), player_master_id=str(row["player_id"]),
                player_display_name=str(row["player_display_name"]), position=position,
                recent_team=str(row["recent_team"] or ""),
                opponent_team=str(row["opponent_team"] or ""), season=season, week=week,
                predicted_mean=mean, adj_mean=mean,
                predicted_p10=quantiles["p10"], predicted_p25=quantiles["p25"],
                predicted_p50=quantiles["p50"], predicted_p75=quantiles["p75"],
                predicted_p90=quantiles["p90"], model="GradientBoosting",
                feature_run_id=context.feature_run_id, model_run_id=context.model_run_id,
                projection_run_id=context.projection_run_id, data_cutoff_at=context.data_cutoff_at,
                game_id=prediction_game_id(row.to_dict(), season=season, week=week),
                team_implied_total=float(row["team_implied_total"]),
                team_spread=float(row["team_spread_line"]), game_total=float(row["game_total_line"]),
                calibration_method=profile.source, calibration_position=position,
                calibration_role=role, calibration_sample_size=profile.sample_size,
            ))
        projections = pd.DataFrame([record.__dict__ for record in records])
        if not self._persist_target_prediction_run(
            context=context, season=season, week=week, slate=slate,
            feature_cols=FEATURE_COLUMNS,
            feature_lineage_cols=PREGAME_LINEAGE_COLUMNS,
            train_df=train, source_features=target,
            projections=projections, calibration_metrics=metrics, source_versions=sources,
        ):
            raise RuntimeError("Canonical projections could not be persisted; the run is not complete.")
        return PredictionRunResult(
            records=records, feature_run_id=context.feature_run_id,
            model_run_id=context.model_run_id, projection_run_id=context.projection_run_id,
            data_cutoff_at=context.data_cutoff_at, target_persisted=True,
            calibration_metrics=metrics,
        )

    def train_and_predict(
        self,
        season: int,
        week: int,
        positions: Iterable[str] | None = None,
        slate: str | None = None,
        data_cutoff_at: datetime | None = None,
        feature_run_id: str | None = None,
        model_run_id: str | None = None,
        projection_run_id: str | None = None,
    ) -> PredictionRunResult:
        if inspect(self.engine).has_table("curated_salary"):
            return self._train_canonical(
                season=season, week=week, positions=positions, slate=slate,
                data_cutoff_at=data_cutoff_at, feature_run_id=feature_run_id,
                model_run_id=model_run_id, projection_run_id=projection_run_id,
            )
        df = self._load_features(season)
        if df.empty:
            logging.warning("No predictive_features available for season %s", season)
            return PredictionRunResult(records=[])

        positions_filter = set(positions) if positions else None
        results: List[PredictionRecord] = []

        feature_cols = self._prepare_xy(df)
        train_df = select_training_rows_before_cutoff(
            df,
            target_season=season,
            target_week=week,
        )
        if train_df.empty:
            raise ValueError(
                f"No labeled training rows are available before season {season} week {week}."
            )
        context = create_prediction_run_context(
            feature_cols,
            data_cutoff_at=data_cutoff_at,
            feature_run_id=feature_run_id,
            model_run_id=model_run_id,
            projection_run_id=projection_run_id,
        )

        # Pull target-week rows from DB and treat non-numeric labels as unlabeled
        with self.engine.begin() as conn:
            pred_df = pd.read_sql(
                text(
                    "SELECT * FROM predictive_features "
                    "WHERE season = :season AND week = :week"
                ),
                conn,
                params={"season": season, "week": week},
            )
        if pred_df.empty:
            # Attempt to build future-week features on the fly
            logging.warning(
                "No feature rows found for season %s week %s; attempting future-week build.",
                season,
                week,
            )
            from Database.features import build_player_features  # local import to avoid cycles
            build_player_features(season=season, weeks=None, future_week=week, connection_string=self.connection_string)
            with self.engine.begin() as conn:
                pred_df = pd.read_sql(
                    text(
                        "SELECT * FROM predictive_features "
                        "WHERE season = :season AND week = :week"
                    ),
                    conn,
                    params={"season": season, "week": week},
                )
            if "player_master_id" in pred_df.columns:
                pred_df["player_id"] = pred_df["player_master_id"].fillna(pred_df.get("player_id")).astype(str)
            if pred_df.empty:
                raise ValueError(f"No feature rows found for season {season} week {week}. Build features for that week first.")
        if TARGET_COL in pred_df.columns:
            pred_df[TARGET_COL] = pd.to_numeric(pred_df[TARGET_COL], errors="coerce")
            pred_df = pred_df[pred_df[TARGET_COL].isna()]
        else:
            pred_df = pd.DataFrame()
        if pred_df.empty:
            raise ValueError(f"No unlabeled feature rows found for season {season} week {week}. Build features for that week first.")

        # Debug: prediction target stats
        y_train = train_df[TARGET_COL].fillna(0)
        print(
            f"[predictions] y_train stats min/med/mean/max="
            f"{y_train.min():.2f}/{y_train.median():.2f}/{y_train.mean():.2f}/{y_train.max():.2f}"
        )

        allowed_player_ids: set[str] | None = None
        salary_feature_team: dict[str, str] = {}
        salary_feature_opp: dict[str, str] = {}
        opponent_map: dict[str, str] = {}
        salary_df = pd.DataFrame()
        slate_value = slate or "DEFAULT"
        if slate:
            salary_map = self._resolve_slate_player_map(season, week, slate)
            if salary_map:
                allowed_player_ids = set(salary_map.values())
            else:
                # Fall back to raw curated_salaries ids for this slate
                with self.engine.begin() as conn:
                    ids_df = pd.read_sql(
                        text("SELECT player_id, \"ID\", player_master_id FROM curated_salaries WHERE season = :season AND week = :week AND slate = :slate"),
                        conn,
                        params={"season": season, "week": week, "slate": slate},
                    )
                if not ids_df.empty:
                    allowed_player_ids = set(ids_df.get("player_master_id", []))
                    allowed_player_ids |= set(ids_df.get("player_id", []))
                    if "ID" in ids_df.columns:
                        allowed_player_ids |= set(ids_df["ID"])
                    allowed_player_ids = {str(pid) for pid in allowed_player_ids if pd.notna(pid)}
                else:
                    logging.warning(
                        "No salaries found for season=%s week=%s slate=%s; projections will be empty for this slate.",
                        season,
                        week,
                        slate,
                    )
                    allowed_player_ids = set()
            if salary_map:
                with self.engine.begin() as conn:
                    salary_df = pd.read_sql(
                        text(
                            "SELECT * FROM curated_salaries WHERE season = :season AND week = :week AND slate = :slate"
                        ),
                        conn,
                        params={"season": season, "week": week, "slate": slate},
                    )
                    # Normalize ids
                    if "player_id" not in salary_df.columns and "ID" in salary_df.columns:
                        salary_df["player_id"] = salary_df["ID"]
                    salary_df["player_id"] = salary_df["player_id"].astype(str)
                    if "player_team" not in salary_df.columns and "TeamAbbrev" in salary_df.columns:
                        salary_df["player_team"] = salary_df["TeamAbbrev"]
                    if "name" not in salary_df.columns and "Name" in salary_df.columns:
                        salary_df["name"] = salary_df["Name"]
                    if "position" not in salary_df.columns and "Position" in salary_df.columns:
                        salary_df["position"] = salary_df["Position"]
                    # Normalize game info casing
                    if "game_info" not in salary_df.columns and "Game Info" in salary_df.columns:
                        salary_df["game_info"] = salary_df["Game Info"]
                    if "internal_player_id" in salary_df.columns:
                        salary_df["internal_player_id"] = salary_df["internal_player_id"].astype(str, errors="ignore")
                    else:
                        salary_df["internal_player_id"] = ""
                for _, row in salary_df.iterrows():
                    salary_id = str(row.player_id)
                    feature_id = salary_map.get(salary_id)
                    if feature_id:
                        salary_feature_team[feature_id] = self._normalize_team(row.player_team)
                        game_info = str(row.get("game_info", "") or "")
                        if "@" in game_info:
                            left, right = game_info.split("@", 1)
                            left = self._normalize_team(left.strip().split(" ")[0])
                            right = self._normalize_team(right.strip().split(" ")[0])
                            team = self._normalize_team(row.player_team)
                            opp = right if team == left else left if team == right else ""
                            if opp:
                                salary_feature_opp[feature_id] = opp
            # Build opponent map from schedule for the target week
            with self.engine.begin() as conn:
                schedule_df = pd.read_sql(
                    text(
                        "SELECT home_team, away_team "
                        "FROM nfl_schedules WHERE season = :season AND week = :week"
                    ),
                    conn,
                    params={"season": season, "week": week},
                )
            for _, row in schedule_df.iterrows():
                home = self._normalize_team(row.home_team)
                away = self._normalize_team(row.away_team)
                opponent_map[home] = away
                opponent_map[away] = home

        if allowed_player_ids is not None:
            filtered = pred_df[pred_df["player_id"].astype(str).isin(allowed_player_ids)]
            pred_df = filtered.copy()
            if pred_df.empty:
                logging.warning(
                    "Salary map for slate %s filtered out all feature rows (%s). Ensure salaries exist for this slate.",
                    slate,
                    len(filtered),
                )
            if salary_feature_team:
                pred_df.loc[:, "recent_team"] = pred_df["player_id"].astype(str).map(salary_feature_team).fillna(pred_df["recent_team"])
            if opponent_map:
                pred_df.loc[:, "opponent_team"] = pred_df["recent_team"].map(opponent_map).fillna(pred_df["opponent_team"])
            if salary_feature_opp:
                pred_df.loc[:, "opponent_team"] = pred_df["player_id"].astype(str).map(salary_feature_opp).fillna(pred_df["opponent_team"])

        if positions_filter:
            pred_df = pred_df[pred_df["position"].isin(positions_filter)]
            if pred_df.empty:
                return PredictionRunResult(
                    records=[],
                    feature_run_id=context.feature_run_id,
                    model_run_id=context.model_run_id,
                    projection_run_id=context.projection_run_id,
                    data_cutoff_at=context.data_cutoff_at,
                )

        X_train = train_df[feature_cols].fillna(0)
        y_train = train_df[TARGET_COL].fillna(0)
        X_pred = pred_df[feature_cols].fillna(0).infer_objects(copy=False)
        print(
            f"[predictions] y_train stats min/med/mean/max="
            f"{y_train.min():.2f}/{y_train.median():.2f}/{y_train.mean():.2f}/{y_train.max():.2f}"
        )
        walk_forward_residuals = generate_walk_forward_residuals(train_df, feature_cols)
        calibration_profiles, calibration_metrics = build_position_calibration(
            walk_forward_residuals,
            train_df,
        )
        model = self._train_model(X_train, y_train)
        preds = self._predict_point_estimates(model, train_df, pred_df, feature_cols)
        pred_df = pred_df.reset_index(drop=True)
        pred_df["calibration_role"] = derive_calibration_roles(pred_df)

        # If predictions are flat and salary averages exist, blend in avg_points_per_game
        if not salary_df.empty and preds.size > 0:
            preds_series = pd.Series(preds)
            if preds_series.std() < 0.5 and "average_points_per_game" in salary_df.columns:
                apg_map = dict(zip(salary_df["player_id"].astype(str), pd.to_numeric(salary_df["average_points_per_game"], errors="coerce")))
                avg_values = pred_df["player_id"].astype(str).map(apg_map).fillna(preds_series)
                preds = avg_values.to_numpy()
        print(
            f"[predictions] raw preds (post-blend) stats min/med/mean/max="
            f"{preds.min():.2f}/{np.median(preds):.2f}/{preds.mean():.2f}/{preds.max():.2f}"
        )

        # Last-3 actuals map for recent median
        hist_df = train_df[["player_id", "week", TARGET_COL]].copy()
        pos_last3_map: dict[str, list[float]] = {}
        if not hist_df.empty:
            hist_df = hist_df.sort_values("week", ascending=False)
            for pid, group in hist_df.groupby("player_id"):
                vals = group[TARGET_COL].dropna().tolist()[:3]
                pos_last3_map[pid] = vals

        for row, pred in zip(
            pred_df[[*ID_COLS, "calibration_role"]].to_dict(orient="records"),
            preds,
            strict=False,
        ):
            # Fill missing display name/position from salaries if available
            if not salary_df.empty:
                row["player_display_name"] = row.get("player_display_name") or str(row.get("player_id", ""))
                row["position"] = row.get("position") or ""
                name_col = "name" if "name" in salary_df.columns else None
                pos_col = "position" if "position" in salary_df.columns else None
                name_map = dict(zip(salary_df["player_id"].astype(str), salary_df[name_col])) if name_col else {}
                pos_map = dict(zip(salary_df["player_id"].astype(str), salary_df[pos_col])) if pos_col else {}
                row["player_display_name"] = name_map.get(str(row.get("player_id", "")), row["player_display_name"])
                row["position"] = pos_map.get(str(row.get("player_id", "")), row["position"])

            calibration_position = (_optional_text(row.get("position")) or "UNKNOWN").upper()
            calibration_role = (_optional_text(row.pop("calibration_role", None)) or "ROTATION").upper()
            calibration_key = f"{calibration_position}|{calibration_role}"
            calibration_profile = calibration_profiles.get(
                calibration_key,
                calibration_profiles.get(calibration_position, calibration_profiles["__ALL__"]),
            )
            quantiles = apply_residual_calibration(float(pred), calibration_profile)
            adj_mean = pred
            game_id = prediction_game_id(row, season=season, week=week)
            results.append(
                PredictionRecord(
                    predicted_mean=float(pred),
                    predicted_p10=quantiles["p10"],
                    predicted_p25=quantiles["p25"],
                    predicted_p50=quantiles["p50"],
                    predicted_p75=quantiles["p75"],
                    predicted_p90=quantiles["p90"],
                    model="GradientBoosting",
                    feature_run_id=context.feature_run_id,
                    model_run_id=context.model_run_id,
                    projection_run_id=context.projection_run_id,
                    data_cutoff_at=context.data_cutoff_at,
                    game_id=game_id,
                    adj_mean=float(adj_mean),
                    calibration_method=calibration_profile.source,
                    calibration_position=calibration_position,
                    calibration_role=calibration_role,
                    calibration_sample_size=calibration_profile.sample_size,
                    **row,
                )
            )

        if not results:
            return PredictionRunResult(
                records=[],
                feature_run_id=context.feature_run_id,
                model_run_id=context.model_run_id,
                projection_run_id=context.projection_run_id,
                data_cutoff_at=context.data_cutoff_at,
                calibration_metrics=calibration_metrics,
            )

        # Compute recent median from last 3 DK scores to temper spikes, then blend with model mean
        df_pred = pd.DataFrame([r.__dict__ for r in results])
        print(
            f"[predictions] postprocessed preds stats min/med/mean/max="
            f"{df_pred['predicted_mean'].min():.2f}/{df_pred['predicted_mean'].median():.2f}/{df_pred['predicted_mean'].mean():.2f}/{df_pred['predicted_mean'].max():.2f}"
        )
        missing_pct = 0.0
        if TARGET_COL in pred_df.columns:
            missing_pct = 100.0 * float(pred_df[TARGET_COL].isna().sum()) / float(len(pred_df)) if len(pred_df) else 0.0
        print(f"[predictions] percent missing label (filled) in pred_df: {missing_pct:.1f}%")
        # Sample known players (highest salary QB/RB/WR from salaries) for merge debugging
        if "salary" in salary_df.columns and "position" in salary_df.columns:
            salary_df["salary"] = pd.to_numeric(salary_df["salary"], errors="coerce")
            for pos in ["QB", "RB", "WR"]:
                pos_df = salary_df[salary_df["position"].str.upper() == pos]
                if pos_df.empty:
                    continue
                row = pos_df.sort_values("salary", ascending=False).iloc[0]
                pid = str(row.get("player_id", ""))
                feat_row = pred_df[pred_df["player_id"].astype(str) == pid].head(1).to_dict(orient="records")
                pred_row = df_pred[df_pred["player_id"].astype(str) == pid].head(1).to_dict(orient="records")
                print(f"[predictions] sample player {row.get('name', row.get('player_display_name', pid))} ({pos})")
                print("  feature row keys:", list(feat_row[0].keys()) if feat_row else "missing")
                print("  prediction row keys:", list(pred_row[0].keys()) if pred_row else "missing")
                print("  merged prediction:", pred_row[0] if pred_row else "missing")
        player_ids = df_pred["player_id"].unique().tolist()
        recent_median_map: dict[str, float] = {}
        if player_ids:
            with self.engine.begin() as connection:
                actuals_df = pd.read_sql(
                    text(
                        "SELECT player_id, week, dk_total_points "
                        "FROM nfl_weekly_data_with_scores "
                        "WHERE season = :season AND week < :week AND player_id = ANY(:player_ids)"
                    ),
                    connection,
                    params={"season": season, "week": week, "player_ids": player_ids},
                )
            if not actuals_df.empty:
                actuals_df = actuals_df.sort_values("week", ascending=False)
                for pid, group in actuals_df.groupby("player_id"):
                    scores = group["dk_total_points"].dropna().tolist()[:3]
                    if scores:
                        recent_median_map[pid] = float(np.median(scores))

        df_pred["recent_median"] = df_pred["player_id"].map(lambda pid: recent_median_map.get(pid, 0.0))
        df_pred["adj_mean"] = (df_pred["predicted_mean"] + df_pred["recent_median"]) / 2.0
        df_pred["adj_mean_base"] = df_pred["adj_mean"]
        df_pred["slate"] = slate_value

        # Capped environment/matchup factor (±15%) using game totals + opponent allowance
        league_team_total = df_pred["team_implied_total"].replace(0, pd.NA).mean()
        league_game_total = df_pred["game_total"].replace(0, pd.NA).mean()
        league_opp_allow = df_pred["opp_pts_allowed_pos_5"].replace(0, pd.NA).mean()
        def _factor(row: pd.Series) -> float:
            tt = float(row.get("team_implied_total", 0.0) or 0.0)
            gt = float(row.get("game_total", 0.0) or 0.0)
            oa = float(row.get("opp_pts_allowed_pos_5", 0.0) or 0.0)
            run_funnel = float(row.get("run_funnel", 0.0) or 0.0)
            pass_funnel = float(row.get("pass_funnel", 0.0) or 0.0)
            comp = 1.0
            if league_team_total and league_team_total > 0:
                comp += 0.25 * ((tt / league_team_total) - 1.0)
            if league_game_total and league_game_total > 0:
                comp += 0.15 * ((gt / league_game_total) - 1.0)
            if league_opp_allow and league_opp_allow > 0:
                comp += 0.25 * ((oa / league_opp_allow) - 1.0)
            comp += 0.05 * run_funnel
            comp -= 0.05 * pass_funnel
            return float(min(1.15, max(0.85, comp)))

        df_pred["matchup_factor"] = df_pred.apply(_factor, axis=1)
        df_pred["adj_mean_final"] = df_pred["adj_mean"] * df_pred["matchup_factor"]
        distribution_shift = df_pred["adj_mean_final"] - df_pred["predicted_mean"]
        quantile_columns = [f"predicted_{name}" for name in CALIBRATION_QUANTILES]
        shifted_quantiles = np.maximum(
            0.0,
            df_pred[quantile_columns].to_numpy(dtype=float) + distribution_shift.to_numpy()[:, None],
        )
        shifted_quantiles = np.maximum.accumulate(shifted_quantiles, axis=1)
        df_pred.loc[:, quantile_columns] = shifted_quantiles
        result_by_player = {record.player_id: record for record in results}
        for row in df_pred[["player_id", *quantile_columns]].to_dict(orient="records"):
            record = result_by_player.get(row["player_id"])
            if record is None:
                continue
            record.predicted_p10 = float(row["predicted_p10"])
            record.predicted_p25 = float(row["predicted_p25"])
            record.predicted_p50 = float(row["predicted_p50"])
            record.predicted_p75 = float(row["predicted_p75"])
            record.predicted_p90 = float(row["predicted_p90"])

        target_persisted = self._persist_target_prediction_run(
            context=context,
            season=season,
            week=week,
            slate=slate_value,
            feature_cols=feature_cols,
            train_df=train_df,
            source_features=pred_df,
            projections=df_pred,
            calibration_metrics=calibration_metrics,
        )
        if not target_persisted:
            raise RuntimeError(
                "Prediction rows were generated but the immutable target run could not be persisted."
            )
        logging.info(
            "Persisted %s player predictions for season=%s week=%s (features week max=%s)",
            len(df_pred),
            season,
            week,
            df["week"].max(),
        )
        return PredictionRunResult(
            records=results,
            feature_run_id=context.feature_run_id,
            model_run_id=context.model_run_id,
            projection_run_id=context.projection_run_id,
            data_cutoff_at=context.data_cutoff_at,
            target_persisted=target_persisted,
            calibration_metrics=calibration_metrics,
        )

    def select_active_prediction_run(
        self,
        *,
        season: int,
        week: int,
        slate: str,
        projection_run_id: str,
        approval_decision_id: str,
    ) -> dict[str, Any]:
        """Reload an active pointer only when it matches an applied approval decision."""
        normalized_slate = slate.strip() or "DEFAULT"
        normalized_decision_id = approval_decision_id.strip()
        if not normalized_decision_id:
            raise ValueError("approval_decision_id is required")
        validate_target_schema(
            self.engine,
            consumer=type(self).__name__,
            required_tables=(
                "projection_run",
                "active_projection_run",
                "model_promotion_decision",
            ),
        )
        with self.engine.connect() as connection:
            run = connection.execute(
                text(
                    """
                    SELECT pr.projection_run_id, pr.model_run_id, pr.season, pr.week,
                           pr.slate_id, pr.row_count, pr.data_cutoff_at, pr.status,
                           pr.created_at, active.selection_reason
                    FROM target.model_promotion_decision decision
                    JOIN target.projection_run pr
                      ON pr.projection_run_id = decision.selected_projection_run_id
                    JOIN target.active_projection_run active
                      ON active.season = pr.season
                     AND active.week = pr.week
                     AND UPPER(active.slate_id) = UPPER(pr.slate_id)
                     AND active.projection_run_id = pr.projection_run_id
                     AND active.selection_reason =
                         'model_' || decision.action || ':' || decision.decision_id
                    WHERE decision.decision_id = :approval_decision_id
                      AND pr.projection_run_id = :projection_run_id
                      AND pr.season = :season AND pr.week = :week
                      AND UPPER(pr.slate_id) = UPPER(:slate_id)
                      AND pr.status = 'completed'
                    """
                ),
                {
                    "approval_decision_id": normalized_decision_id,
                    "projection_run_id": projection_run_id,
                    "season": season,
                    "week": week,
                    "slate_id": normalized_slate,
                },
            ).mappings().first()
            if not run:
                raise ValueError(
                    f"Projection run {projection_run_id} is not the active selection for "
                    f"approved decision {normalized_decision_id} in season {season} "
                    f"week {week} slate {normalized_slate}."
                )
        return {
            **dict(run),
            "active": True,
        }

    @staticmethod
    def _resolve_projection_run_id(
        connection: Any,
        *,
        season: int,
        week: int,
        slate: str | None,
        projection_run_id: str | None,
    ) -> str | None:
        """Resolve an exact requested run or the explicit active run for the scope."""
        params: dict[str, Any] = {"season": season, "week": week}
        slate_filter = ""
        if slate:
            params["slate"] = slate
            slate_filter = "AND (slate_id IS NULL OR UPPER(slate_id) = UPPER(:slate))"

        if projection_run_id:
            row = connection.execute(
                text(
                    f"""
                    SELECT projection_run_id
                    FROM target.player_projection
                    WHERE season = :season AND week = :week
                      AND projection_run_id = :projection_run_id
                      {slate_filter}
                    LIMIT 1
                    """
                ),
                {**params, "projection_run_id": projection_run_id},
            ).mappings().first()
            return str(row["projection_run_id"]) if row else None

        db_inspector = inspect(connection)
        if db_inspector.has_table("active_projection_run", schema="target"):
            active_filter = ""
            active_order = "selected_at DESC, slate_id"
            if slate:
                active_filter = (
                    "AND (UPPER(slate_id) = UPPER(:slate) OR slate_id = 'DEFAULT')"
                )
                active_order = (
                    "CASE WHEN UPPER(slate_id) = UPPER(:slate) THEN 0 ELSE 1 END, "
                    "selected_at DESC"
                )
            row = connection.execute(
                text(
                    f"""
                    SELECT projection_run_id
                    FROM target.active_projection_run
                    WHERE season = :season AND week = :week
                      {active_filter}
                    ORDER BY {active_order}
                    LIMIT 1
                    """
                ),
                params,
            ).mappings().first()
            if row:
                return str(row["projection_run_id"])

        row = connection.execute(
            text(
                f"""
                SELECT projection_run_id, MAX(created_at) AS latest_created_at
                FROM target.player_projection
                WHERE season = :season AND week = :week
                  {slate_filter}
                GROUP BY projection_run_id
                ORDER BY latest_created_at DESC, projection_run_id
                LIMIT 1
                """
            ),
            params,
        ).mappings().first()
        return str(row["projection_run_id"]) if row else None

    def _load_target_prediction_frame(
        self,
        connection: Any,
        *,
        season: int,
        week: int,
        limit: int,
        slate: str | None,
        projection_run_id: str | None,
    ) -> pd.DataFrame:
        """Load one exact canonical target projection run."""
        db_inspector = inspect(connection)
        if not db_inspector.has_table("player_projection", schema="target"):
            return pd.DataFrame()

        selected_projection_run_id = self._resolve_projection_run_id(
            connection,
            season=season,
            week=week,
            slate=slate,
            projection_run_id=projection_run_id,
        )
        if selected_projection_run_id is None:
            return pd.DataFrame()

        projection_columns = {
            column["name"]
            for column in db_inspector.get_columns("player_projection", schema="target")
        }
        has_public_salary = db_inspector.has_table("curated_salary", schema="public")
        has_target_salary = db_inspector.has_table("snapshot_salary", schema="target")
        has_salary = has_public_salary or has_target_salary
        has_player = db_inspector.has_table("dim_player", schema="target")
        has_model_run = db_inspector.has_table("model_run", schema="target")
        has_feature_inputs = db_inspector.has_table(
            "feature_player_game", schema="target"
        ) and has_model_run

        params: dict[str, Any] = {
            "season": season,
            "week": week,
            "limit": limit,
            "selected_projection_run_id": selected_projection_run_id,
        }
        projection_filter = ""
        projection_order = "player_id, created_at DESC"
        if slate:
            params["slate"] = slate
            projection_filter = "AND (slate_id IS NULL OR UPPER(slate_id) = UPPER(:slate))"
            projection_order = (
                "player_id, "
                "CASE WHEN UPPER(COALESCE(slate_id, '')) = UPPER(:slate) THEN 0 ELSE 1 END, "
                "created_at DESC"
            )

        salary_cte = ""
        salary_join = ""
        salary_has_player_name = False
        salary_has_position = False
        if has_public_salary:
            salary_has_player_name = True
            salary_has_position = True
            salary_filter = ""
            if slate:
                salary_filter = "AND UPPER(slate) = UPPER(:slate)"
            salary_cte = f""",
            latest_salary AS (
                SELECT DISTINCT ON (player_master_id)
                    player_master_id AS player_id,
                    player_name,
                    position,
                    salary,
                    roster_position,
                    team AS team_id,
                    opponent AS opponent_team_id,
                    NULL::TEXT AS game_id
                FROM public.curated_salary
                WHERE season = :season AND week = :week
                  AND source_system = 'draftkings'
                  AND player_master_id IS NOT NULL
                  {salary_filter}
                ORDER BY player_master_id,
                    CASE WHEN UPPER(COALESCE(roster_position, '')) = 'FLEX' THEN 0 ELSE 1 END,
                    created_at DESC,
                    curated_salary_id DESC
            )
            """
            salary_join = "LEFT JOIN latest_salary s ON s.player_id = p.player_id"
        elif has_target_salary:
            salary_filter = ""
            if slate:
                salary_filter = "AND UPPER(COALESCE(slate, slate_id, '')) = UPPER(:slate)"
            salary_cte = f""",
            latest_salary AS (
                SELECT DISTINCT ON (player_id)
                    player_id, salary, roster_position, team_id,
                    opponent_team_id, game_id
                FROM target.snapshot_salary
                WHERE season = :season AND week = :week
                  {salary_filter}
                ORDER BY player_id,
                    CASE WHEN UPPER(COALESCE(roster_position, '')) = 'FLEX' THEN 0 ELSE 1 END,
                    as_of DESC
            )
            """
            salary_join = "LEFT JOIN latest_salary s ON s.player_id = p.player_id"

        player_join = "LEFT JOIN target.dim_player d ON d.player_id = p.player_id" if has_player else ""
        model_run_join = (
            "LEFT JOIN target.model_run mr ON mr.model_run_id = p.model_run_id"
            if has_model_run
            else ""
        )
        feature_join = (
            "LEFT JOIN target.feature_player_game f "
            "ON f.feature_run_id = mr.feature_run_id "
            "AND f.season = p.season AND f.week = p.week "
            "AND f.player_id = p.player_id AND f.game_id = p.game_id"
            if has_feature_inputs
            else ""
        )
        feature_inputs = (
            "COALESCE(f.feature_json, '{}'::jsonb)"
            if has_feature_inputs
            else "'{}'::jsonb"
        )
        player_name_candidates = []
        if has_player:
            player_name_candidates.append("NULLIF(d.full_name, '')")
        if salary_has_player_name:
            player_name_candidates.append("NULLIF(s.player_name, '')")
        player_name_candidates.append("p.player_id")
        player_name = f"COALESCE({', '.join(player_name_candidates)})"
        position_candidates = []
        if salary_has_position:
            position_candidates.append("NULLIF(s.position, '')")
        if has_salary:
            position_candidates.append(
                "NULLIF(CASE WHEN UPPER(COALESCE(s.roster_position, '')) IN ('FLEX', 'CPT') "
                "THEN '' ELSE s.roster_position END, '')"
            )
        if has_player:
            position_candidates.append("NULLIF(d.primary_position, '')")
        if "calibration_position" in projection_columns:
            position_candidates.append("NULLIF(p.calibration_position, '')")
        position_source = f"COALESCE({', '.join(position_candidates)}, '')" if position_candidates else "''"
        position = (
            f"CASE WHEN UPPER({position_source}) IN ('D', 'DEF') THEN 'DST' "
            f"ELSE UPPER({position_source}) END"
        )

        salary = "s.salary" if has_salary else "NULL::integer"
        recent_team = "COALESCE(s.team_id, '')" if has_salary else "''"
        opponent_team = "COALESCE(s.opponent_team_id, '')" if has_salary else "''"
        game_id = "COALESCE(s.game_id, p.game_id)" if has_salary else "p.game_id"
        feature_run_id = "mr.feature_run_id" if has_model_run else "NULL::text"
        calibration_method = (
            "COALESCE(NULLIF(p.calibration_method, ''), 'target_projection_fallback')"
            if "calibration_method" in projection_columns
            else "'target_projection_fallback'"
        )
        calibration_position = (
            f"COALESCE(NULLIF(p.calibration_position, ''), {position_source})"
            if "calibration_position" in projection_columns
            else position_source
        )
        calibration_role = (
            "COALESCE(NULLIF(p.calibration_role, ''), 'unknown')"
            if "calibration_role" in projection_columns
            else "'unknown'"
        )
        calibration_sample_size = (
            "COALESCE(p.calibration_sample_size, 0)"
            if "calibration_sample_size" in projection_columns
            else "0"
        )

        query = text(
            f"""
            WITH latest_projection AS (
                SELECT DISTINCT ON (player_id) *
                FROM target.player_projection
                WHERE season = :season AND week = :week
                  AND projection_run_id = :selected_projection_run_id
                  {projection_filter}
                ORDER BY {projection_order}
            )
            {salary_cte}
            SELECT
                p.player_id,
                {player_name} AS player_display_name,
                {position} AS position,
                {recent_team} AS recent_team,
                {opponent_team} AS opponent_team,
                {salary} AS salary,
                p.season,
                p.week,
                COALESCE(p.mean, 0.0) AS predicted_mean,
                COALESCE(p.p10, p.mean, 0.0) AS predicted_p10,
                COALESCE(p.p25, p.median, p.mean, 0.0) AS predicted_p25,
                COALESCE(p.median, p.mean, 0.0) AS predicted_p50,
                COALESCE(p.p75, p.median, p.mean, 0.0) AS predicted_p75,
                COALESCE(p.p90, p.mean, 0.0) AS predicted_p90,
                'target.player_projection' AS model,
                {feature_run_id} AS feature_run_id,
                p.model_run_id,
                p.projection_run_id,
                p.data_cutoff_at,
                {game_id} AS game_id,
                {calibration_method} AS calibration_method,
                {calibration_position} AS calibration_position,
                {calibration_role} AS calibration_role,
                {calibration_sample_size} AS calibration_sample_size,
                {feature_inputs} AS feature_inputs,
                COALESCE(p.mean, 0.0) AS adj_mean,
                COALESCE(p.mean, 0.0) AS adj_mean_base,
                1.0 AS matchup_factor,
                COALESCE(p.mean, 0.0) AS adj_mean_final
            FROM latest_projection p
            {salary_join}
            {player_join}
            {model_run_join}
            {feature_join}
            ORDER BY COALESCE(p.mean, 0.0) DESC
            LIMIT :limit
            """
        )
        return pd.read_sql(query, connection, params=params)

    def fetch_predictions(
        self,
        season: int,
        week: int,
        limit: int = 20,
        slate: str | None = None,
        projection_run_id: str | None = None,
    ) -> List[dict[str, Any]]:
        db_inspector = inspect(self.engine)
        use_target_schema = db_inspector.has_table("player_projection", schema="target")
        use_legacy_schema = not use_target_schema and db_inspector.has_table("player_expected_points")
        with self.engine.begin() as connection:
            if use_target_schema:
                df = self._load_target_prediction_frame(
                    connection,
                    season=season,
                    week=week,
                    limit=limit,
                    slate=slate,
                    projection_run_id=projection_run_id,
                )
            elif use_legacy_schema:
                query = (
                    "SELECT * FROM player_expected_points "
                    "WHERE season = :season AND week = :week "
                )
                params: dict[str, Any] = {"season": season, "week": week, "limit": limit}
                if slate:
                    query += "AND slate = :slate "
                    params["slate"] = slate
                query += "ORDER BY COALESCE(adj_mean, predicted_mean) DESC LIMIT :limit"
                df = pd.read_sql(text(query), connection, params=params)
            else:
                df = pd.DataFrame()

            if use_legacy_schema and not df.empty:
                adjusted_query = (
                    "SELECT DISTINCT ON (player_id) player_id, rule_run_id, adjusted_mean, adjusted_p90, reason "
                    "FROM player_expected_points_adjusted "
                    "WHERE season = :season AND week = :week "
                )
                adjusted_params: dict[str, Any] = {"season": season, "week": week}
                if slate:
                    adjusted_query += "AND (slate = :slate OR slate IS NULL) "
                    adjusted_params["slate"] = slate
                adjusted_query += "ORDER BY player_id, created_at DESC"
                try:
                    adjusted_df = pd.read_sql(
                        text(adjusted_query),
                        connection,
                        params=adjusted_params,
                    )
                except Exception:
                    adjusted_df = pd.DataFrame()
                if not adjusted_df.empty:
                    df = df.merge(
                        adjusted_df,
                        on="player_id",
                        how="left",
                        suffixes=("", "_symbolic"),
                    )
                    df["adj_mean_final"] = df["adjusted_mean"].fillna(
                        df.get("adj_mean_final", df.get("adj_mean"))
                    )
                    df["symbolic_p90"] = df["adjusted_p90"]
            actuals_df = pd.DataFrame()
            team_pos_df = pd.DataFrame()
            if not df.empty:
                player_ids = df["player_id"].unique().tolist()
                if use_legacy_schema and db_inspector.has_table("nfl_weekly_data_with_scores"):
                    actuals_df = pd.read_sql(
                        text(
                            "SELECT player_id, season, week, dk_total_points "
                            "FROM nfl_weekly_data_with_scores "
                            "WHERE (season < :season OR (season = :season AND week < :week)) "
                            "AND player_id = ANY(:player_ids)"
                        ),
                        connection,
                        params={"season": season, "week": week, "player_ids": player_ids},
                    )
                    team_pos_df = pd.read_sql(
                        text(
                            "SELECT "
                            "COALESCE(recent_team, team) AS team, "
                            "position, "
                            "SUM(dk_total_points) AS total_points, "
                            "COUNT(DISTINCT week) AS games_played "
                            "FROM nfl_weekly_data_with_scores "
                            "WHERE (season < :season OR (season = :season AND week < :week)) "
                            "GROUP BY COALESCE(recent_team, team), position"
                        ),
                        connection,
                        params={"season": season, "week": week},
                    )
                elif db_inspector.has_table("fact_player_game_actual", schema="target"):
                    actuals_df = pd.read_sql(
                        text(
                            "SELECT player_id, season, week, dk_points AS dk_total_points "
                            "FROM target.fact_player_game_actual "
                            "WHERE (season < :season OR (season = :season AND week < :week)) "
                            "AND player_id = ANY(:player_ids)"
                        ),
                        connection,
                        params={"season": season, "week": week, "player_ids": player_ids},
                    )
                    team_pos_df = pd.read_sql(
                        text(
                            "SELECT team_id AS team, position, "
                            "SUM(dk_points) AS total_points, "
                            "COUNT(DISTINCT week) AS games_played "
                            "FROM target.fact_player_game_actual "
                            "WHERE (season < :season OR (season = :season AND week < :week)) "
                            "GROUP BY team_id, position"
                        ),
                        connection,
                        params={"season": season, "week": week},
                    )
        if df.empty:
            return []

        team_pos_map: dict[tuple[str, str], float] = {}
        if not team_pos_df.empty:
            for _, row in team_pos_df.iterrows():
                key = (self._normalize_team(row.team), row.position)
                games = float(row.games_played or 1.0)
                team_pos_map[key] = float(row.total_points or 0.0) / games if games else 0.0

        salary_id_map: dict[str, str] | None = None
        salary_team_map: dict[str, str] = {}
        salary_value_map: dict[str, int] = {}
        if slate and use_legacy_schema:
            salary_id_map = self._resolve_slate_player_map(season, week, slate)
            if salary_id_map:
                # Future-week builds store DK salary ids as player_id; historical rows may use internal ids.
                # Allow both the map values (feature/internal ids) and the salary ids (map keys) when filtering.
                feature_ids = set(salary_id_map.values()) | set(salary_id_map.keys())
                df_filtered = df[df["player_id"].astype(str).isin(feature_ids)]
                actuals_filtered = actuals_df[actuals_df["player_id"].astype(str).isin(feature_ids)]
                if df_filtered.empty:
                    logging.warning(
                        "Slate %s week %s filtering removed all projections; using unfiltered results instead",
                        slate,
                        week,
                    )
                else:
                    df = df_filtered
                    actuals_df = actuals_filtered
                # Build salary team map (internal_id -> player_team and salary_id -> player_team)
                with self.engine.begin() as conn:
                    inspector = inspect(conn)
                    existing_cols = {col["name"] for col in inspector.get_columns("curated_salaries")}
                    select_cols = [
                        c
                        for c in [
                            "internal_player_id",
                            "player_master_id",
                            "player_id",
                            "ID",
                            "player_team",
                            "TeamAbbrev",
                            "salary",
                            "Salary",
                        ]
                        if c in existing_cols
                    ]
                    if select_cols:
                        clause = ", ".join(f"\"{c}\"" for c in select_cols)
                        team_df = pd.read_sql(
                            text(
                                f"SELECT {clause} FROM curated_salaries WHERE season = :season AND week = :week AND slate = :slate"
                            ),
                            conn,
                            params={"season": season, "week": week, "slate": slate},
                        )
                    else:
                        team_df = pd.DataFrame()
                if not team_df.empty:
                    salary_team_map = {}
                    for _, row in team_df.iterrows():
                        player_team_val = row.get("player_team", row.get("TeamAbbrev"))
                        salary_raw = row.get("salary", row.get("Salary"))
                        salary_value = None
                        if pd.notna(salary_raw):
                            try:
                                salary_value = int(float(salary_raw))
                            except (TypeError, ValueError):
                                salary_value = None
                        if "internal_player_id" in row and pd.notna(row["internal_player_id"]):
                            salary_team_map[str(row["internal_player_id"])] = player_team_val
                            if salary_value is not None:
                                salary_value_map[str(row["internal_player_id"])] = salary_value
                        if "player_master_id" in row and pd.notna(row["player_master_id"]):
                            salary_team_map[str(row["player_master_id"])] = player_team_val
                            if salary_value is not None:
                                salary_value_map[str(row["player_master_id"])] = salary_value
                        if "player_id" in row and pd.notna(row["player_id"]):
                            salary_team_map[str(row["player_id"])] = player_team_val
                            if salary_value is not None:
                                salary_value_map[str(row["player_id"])] = salary_value
                        if "ID" in row and pd.notna(row["ID"]):
                            salary_team_map[str(row["ID"])] = player_team_val
                            if salary_value is not None:
                                salary_value_map[str(row["ID"])] = salary_value
        # Deduplicate rows: prefer player_master_id, else player_id, else name+team
        if not df.empty:
            df = df.sort_values(["adj_mean", "predicted_mean"], ascending=False)
            dedup_key = df["player_master_id"] if "player_master_id" in df.columns else pd.Series(pd.NA, index=df.index)
            if dedup_key.isna().all():
                dedup_key = df["player_id"]
            # If still empty, fall back to name + team
            if dedup_key.isna().all() and "player_display_name" in df.columns:
                team_key = df.get("recent_team", df.get("team", pd.Series("", index=df.index)))
                norm_name = df["player_display_name"].astype(str).str.strip().str.lower()
                norm_team = team_key.astype(str).str.strip().str.lower()
                dedup_key = norm_name + "|" + norm_team
            dedup_key = dedup_key.fillna("")
            df = df.assign(_dedup_key=dedup_key)
            df = df.drop_duplicates(subset=["_dedup_key"], keep="first").drop(columns=["_dedup_key"])

        last3_map: dict[str, list[float]] = {}
        if not actuals_df.empty:
            actual_sort_columns = [
                column for column in ("season", "week") if column in actuals_df
            ]
            actuals_df = actuals_df.sort_values(
                actual_sort_columns,
                ascending=[False] * len(actual_sort_columns),
            )
            for pid, group in actuals_df.groupby("player_id"):
                vals = group["dk_total_points"].dropna().tolist()[:3]
                last3_map[pid] = vals

        rows: List[dict[str, Any]] = []
        for _, row in df.iterrows():
            row_dict = row.to_dict()

            def _str(val: Any) -> str:
                return "" if val is None else str(val)

            pid = row_dict.get("player_id", "")
            l3 = last3_map.get(pid, [])
            feature_inputs = row_dict.get("feature_inputs") or {}
            if isinstance(feature_inputs, str):
                try:
                    feature_inputs = json.loads(feature_inputs)
                except json.JSONDecodeError:
                    feature_inputs = {}
            if not isinstance(feature_inputs, dict):
                feature_inputs = {}
            # Display the average of the displayed history. The saved model's
            # player_roll3_mean may use a fuller source and remains in feature_inputs.
            l3_avg = float(sum(l3) / len(l3) if l3 else 0.0)
            recent_median = float(row_dict.get("recent_median", np.median(l3) if l3 else 0.0))
            model_mean = float(row_dict.get("predicted_mean", 0.0))
            recent_team_val = row_dict.get("recent_team", "")
            if (not recent_team_val) and salary_team_map:
                recent_team_val = salary_team_map.get(str(pid), recent_team_val)

            display_player_id = _str(row_dict.get("player_id", ""))
            if salary_id_map:
                reverse = {v: k for k, v in salary_id_map.items()}
                # If predictions are already using the salary id, keep it; otherwise translate internal->salary.
                reverse.update({k: k for k in salary_id_map.keys()})
                display_player_id = reverse.get(display_player_id, display_player_id)
            salary_value = salary_value_map.get(display_player_id)
            if salary_value is None:
                salary_value = salary_value_map.get(_str(pid))
            if salary_value is None and pd.notna(row_dict.get("salary")):
                try:
                    salary_value = int(float(row_dict["salary"]))
                except (TypeError, ValueError):
                    salary_value = None

            team_key = (self._normalize_team(recent_team_val), row_dict.get("position"))
            team_pos_avg = team_pos_map.get(team_key, 0.0)

            adj_mean = float(row_dict.get("adj_mean_final", row_dict.get("adj_mean", (model_mean + recent_median) / 2.0)))
            matchup_factor = float(row_dict.get("matchup_factor", 1.0))

            rows.append(
                {
                    "player_id": display_player_id,
                    "player_display_name": _str(row_dict.get("player_display_name", "")),
                    "position": _str(row_dict.get("position", "")),
                    "recent_team": _str(recent_team_val),
                    "opponent_team": _str(row_dict.get("opponent_team", "")),
                    "salary": salary_value,
                    "season": int(row_dict.get("season", season)),
                    "week": int(row_dict.get("week", week)),
                    "predicted_mean": model_mean,
                    "predicted_p10": float(row_dict.get("predicted_p10", model_mean)),
                    "predicted_p25": float(row_dict.get("predicted_p25", model_mean)),
                    "predicted_p50": float(row_dict.get("predicted_p50", model_mean)),
                    "predicted_p75": float(row_dict.get("predicted_p75", model_mean)),
                    "predicted_p90": float(row_dict.get("predicted_p90", model_mean)),
                    "model": _str(row_dict.get("model", "")),
                    "feature_run_id": _optional_text(row_dict.get("feature_run_id")),
                    "model_run_id": _optional_text(row_dict.get("model_run_id")),
                    "projection_run_id": _optional_text(row_dict.get("projection_run_id")),
                    "data_cutoff_at": row_dict.get("data_cutoff_at"),
                    "game_id": _optional_text(row_dict.get("game_id")),
                    "calibration_method": _str(row_dict.get("calibration_method", "")),
                    "calibration_position": _str(row_dict.get("calibration_position", "")),
                    "calibration_role": _str(row_dict.get("calibration_role", "")),
                    "calibration_sample_size": int(row_dict.get("calibration_sample_size", 0) or 0),
                    "feature_inputs": feature_inputs,
                    "last3_points": l3,
                    "last3_avg": l3_avg,
                    "recent_median": recent_median,
                    "recent_robust": recent_median,
                    "delta_vs_last3": model_mean - l3_avg,
                    "team_pos_avg": team_pos_avg,
                    "adj_mean": adj_mean,
                    "adj_mean_base": float(row_dict.get("adj_mean_base", adj_mean)),
                    "matchup_factor": matchup_factor,
                    "adj_mean_final": adj_mean,
                }
            )
        return rows

    # _compute_adj_mean unused after dataframe-based adj calculation

    def _resolve_slate_player_map(self, season: int, week: int, slate: str) -> dict[str, str] | None:
        """
        Return mapping of salary player_id -> feature player_id using id match or name/team match.
        Uses predictive_features latest snapshot and weekly stats (all weeks) to allow future-week slates.
        """
        with self.engine.begin() as conn:
            salaries = pd.read_sql(
                text(
                    "SELECT * FROM curated_salaries "
                    "WHERE season = :season AND week = :week AND slate = :slate"
                ),
                conn,
                params={"season": season, "week": week, "slate": slate},
            )
            if salaries.empty:
                return None

            # Normalize salary fields
            salary_id_col = None
            for cand in ["player_id", "ID", "id"]:
                if cand in salaries.columns:
                    salary_id_col = cand
                    break
            if salary_id_col is None:
                return None
            salaries["salary_id"] = salaries[salary_id_col].astype(str)
            if "internal_player_id" in salaries.columns:
                salaries["internal_player_id"] = salaries["internal_player_id"].astype(str, errors="ignore")
            else:
                salaries["internal_player_id"] = ""
            if "player_master_id" in salaries.columns:
                salaries["player_master_id"] = salaries["player_master_id"].astype(str, errors="ignore")
            name_col = "Name" if "Name" in salaries.columns else "name" if "name" in salaries.columns else None
            team_col = "player_team" if "player_team" in salaries.columns else "TeamAbbrev" if "TeamAbbrev" in salaries.columns else "team"
            salaries["name_norm"] = salaries[name_col].astype(str).str.lower().str.strip().map(_normalize_alias) if name_col else ""
            salaries["player_team"] = salaries[team_col] if team_col in salaries.columns else ""

            features = pd.read_sql(
                text(
                    "SELECT player_id, player_master_id, player_display_name, recent_team, week "
                    "FROM predictive_features WHERE season = :season"
                ),
                conn,
                params={"season": season},
            )
            if features.empty:
                return None
            features = features.sort_values("week").drop_duplicates("player_id", keep="last")
            features["name_norm"] = features["player_display_name"].str.lower().str.strip().map(_normalize_alias)

            # Start with mapping every salary id to itself so we don't drop players
            mapping: dict[str, str] = {}
            # Prefer player_master_id; fallback to internal or salary ids
            if "player_master_id" in salaries.columns:
                pm_map = salaries.set_index("salary_id")["player_master_id"].to_dict()
                for sid, pmid in pm_map.items():
                    if pmid and pmid != "nan":
                        mapping[sid] = pmid
            if not mapping and "internal_player_id" in salaries.columns:
                internal_map = salaries.set_index("salary_id")["internal_player_id"].to_dict()
                for sid, internal_id in internal_map.items():
                    if internal_id and internal_id != "nan":
                        mapping[sid] = internal_id
            if not mapping:
                salary_ids = set(salaries["salary_id"])
                feature_ids = set(
                    features["player_master_id"].astype(str).dropna().tolist()
                    + features["player_id"].astype(str).dropna().tolist()
                )
                for sid in salary_ids & feature_ids:
                    mapping[sid] = sid

            # Name/team match for remaining
            remaining = salaries[~salaries["salary_id"].isin(mapping.keys())]
            if not remaining.empty:
                merged_feat = remaining.merge(
                    features,
                    left_on=["name_norm", "player_team"],
                    right_on=["name_norm", "recent_team"],
                    how="inner",
                    suffixes=("", "_feat"),
                )
                for _, row in merged_feat.iterrows():
                    mapping[row["salary_id"]] = str(row["player_id"])

                still_remaining = remaining[~remaining["salary_id"].isin(mapping.keys())]
                if not still_remaining.empty and not weekly.empty:
                    merged_weekly = still_remaining.merge(
                        weekly,
                        left_on=["name_norm", "player_team"],
                        right_on=["name_norm", "recent_team"],
                        how="inner",
                        suffixes=("", "_wk"),
                    )
                    for _, row in merged_weekly.iterrows():
                        mapping[row["salary_id"]] = str(row["player_id"])

                # Last resort: name-only match (may produce duplicates; keep first)
                still_remaining = remaining[~remaining["salary_id"].isin(mapping.keys())]
                if not still_remaining.empty:
                    merged_name = still_remaining.merge(
                        features,
                        on="name_norm",
                        how="inner",
                        suffixes=("", "_feat2"),
                    )
                    for _, row in merged_name.iterrows():
                        mapping[row["salary_id"]] = str(row["player_id"])

            return mapping if mapping else None
