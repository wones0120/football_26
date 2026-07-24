"""DraftKings contest ownership and past-slate analysis helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import logging
import math
from pathlib import Path
import re
from typing import Any
import uuid
from zipfile import ZipFile

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sklearn.ensemble import GradientBoostingRegressor

from Database.config import get_connection_string
from Database.operations import ensure_table_columns
from .contest_evidence import classify_contest_type
from .player_master import PlayerMasterResolver
from .target_schema import validate_target_schema


logger = logging.getLogger(__name__)

OWNERSHIP_MODEL_ID = "slate_aware_ownership_v1"
OWNERSHIP_TARGET = "actual_ownership"
OWNERSHIP_NUMERIC_FEATURES = [
    "salary",
    "salary_percentile",
    "projection_mean",
    "projection_p90",
    "projection_percentile",
    "value_per_thousand",
    "prior_player_ownership",
    "prior_slot_ownership",
    "prior_format_ownership",
    "slate_size",
    "is_showdown",
    "is_captain",
]
OWNERSHIP_CATEGORICAL_FEATURES = ["position", "contest_format", "roster_slot"]
MIN_OWNERSHIP_TRAIN_ROWS = 100


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _normalized_slate(value: object) -> str:
    return str(value or "").strip().upper()


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, np.generic):
        value = value.item()
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def infer_ownership_format(slate: object, roster_position: object) -> str:
    slate_key = _normalized_slate(slate)
    position_key = str(roster_position or "").upper()
    return "showdown" if any(token in slate_key for token in ("SHOWDOWN", "CAPTAIN")) or "CPT" in position_key else "classic"


def normalize_ownership_slot(position: object, contest_format: str) -> str:
    value = str(position or "").strip().upper()
    if contest_format == "showdown":
        return "CPT" if "CPT" in value or "CAPTAIN" in value else "FLEX"
    for candidate in ("QB", "RB", "WR", "TE", "DST", "DEF", "K"):
        if candidate in value:
            return "DST" if candidate == "DEF" else candidate
    return value or "FLEX"


def build_slate_aware_ownership_frame(rows: pd.DataFrame) -> pd.DataFrame:
    """Create leakage-safe slate/player features from observed and target ownership rows."""
    required = {"season", "week", "slate", "player_id", "roster_position", OWNERSHIP_TARGET}
    missing = sorted(required.difference(rows.columns))
    if missing:
        raise ValueError(f"Ownership modeling rows are missing required columns: {', '.join(missing)}")

    frame = rows.copy()
    frame["season"] = pd.to_numeric(frame["season"], errors="coerce")
    frame["week"] = pd.to_numeric(frame["week"], errors="coerce")
    frame[OWNERSHIP_TARGET] = pd.to_numeric(frame[OWNERSHIP_TARGET], errors="coerce")
    frame = frame.dropna(subset=["season", "week"])
    frame["season"] = frame["season"].astype(int)
    frame["week"] = frame["week"].astype(int)
    frame["slate"] = frame["slate"].map(_normalized_slate)
    frame["player_id"] = frame["player_id"].astype(str)
    frame["player_display_name"] = frame.get("player_display_name", frame["player_id"]).fillna(frame["player_id"]).astype(str)
    frame["roster_position"] = frame["roster_position"].fillna("").astype(str).str.upper()
    frame["contest_format"] = [
        infer_ownership_format(slate, position)
        for slate, position in zip(frame["slate"], frame["roster_position"], strict=True)
    ]
    slate_has_captain = frame.groupby(["season", "week", "slate"])["roster_position"].transform(
        lambda values: values.str.contains("CPT|CAPTAIN", regex=True).any()
    )
    frame.loc[slate_has_captain, "contest_format"] = "showdown"
    frame["roster_slot"] = [
        normalize_ownership_slot(position, contest_format)
        for position, contest_format in zip(frame["roster_position"], frame["contest_format"], strict=True)
    ]
    frame["position"] = frame.get("position", frame["roster_slot"]).fillna(frame["roster_slot"]).astype(str).str.upper()
    frame["position"] = frame["position"].where(frame["position"].ne("FLEX"), frame["roster_slot"])
    for column in ("salary", "projection_mean", "projection_p90"):
        frame[column] = pd.to_numeric(frame.get(column, 0.0), errors="coerce").fillna(0.0)

    group_columns = [
        "season",
        "week",
        "slate",
        "contest_format",
        "roster_slot",
        "position",
        "player_id",
        "player_display_name",
    ]
    frame = (
        frame.groupby(group_columns, dropna=False)
        .agg(
            actual_ownership=(OWNERSHIP_TARGET, "mean"),
            salary=("salary", "max"),
            projection_mean=("projection_mean", "max"),
            projection_p90=("projection_p90", "max"),
        )
        .reset_index()
        .sort_values(["season", "week", "slate", "player_id", "roster_slot"])
        .reset_index(drop=True)
    )

    slate_group = frame.groupby(["season", "week", "slate", "contest_format"], dropna=False)
    frame["salary_percentile"] = slate_group["salary"].rank(method="average", pct=True)
    frame["projection_percentile"] = slate_group["projection_mean"].rank(method="average", pct=True)
    frame["slate_size"] = slate_group["player_id"].transform("nunique").astype(float)
    salary_thousands = frame["salary"].replace(0, np.nan) / 1000.0
    frame["value_per_thousand"] = (frame["projection_mean"] / salary_thousands).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    frame["is_showdown"] = (frame["contest_format"] == "showdown").astype(float)
    frame["is_captain"] = (frame["roster_slot"] == "CPT").astype(float)

    player_period_columns = ["season", "week", "player_id", "contest_format", "roster_slot"]
    player_period = (
        frame.groupby(player_period_columns, dropna=False)[OWNERSHIP_TARGET]
        .mean()
        .reset_index(name="period_player_ownership")
        .sort_values(player_period_columns)
    )
    player_period["prior_player_ownership"] = player_period.groupby(
        ["player_id", "contest_format", "roster_slot"], dropna=False
    )["period_player_ownership"].transform(
        lambda values: values.shift(1).expanding(min_periods=1).mean()
    )
    frame = frame.merge(
        player_period[[*player_period_columns, "prior_player_ownership"]],
        on=player_period_columns,
        how="left",
    )

    period_columns = ["season", "week", "contest_format", "roster_slot"]
    period_slot = (
        frame.groupby(period_columns, dropna=False)[OWNERSHIP_TARGET]
        .mean()
        .reset_index(name="period_slot_ownership")
        .sort_values(period_columns)
    )
    period_slot["prior_slot_ownership"] = period_slot.groupby(
        ["contest_format", "roster_slot"], dropna=False
    )["period_slot_ownership"].transform(lambda values: values.shift(1).expanding(min_periods=1).mean())
    frame = frame.merge(
        period_slot[[*period_columns, "prior_slot_ownership"]],
        on=period_columns,
        how="left",
    )

    format_period_columns = ["season", "week", "contest_format"]
    period_format = (
        frame.groupby(format_period_columns, dropna=False)[OWNERSHIP_TARGET]
        .mean()
        .reset_index(name="period_format_ownership")
        .sort_values(format_period_columns)
    )
    period_format["prior_format_ownership"] = period_format.groupby("contest_format", dropna=False)[
        "period_format_ownership"
    ].transform(lambda values: values.shift(1).expanding(min_periods=1).mean())
    frame = frame.merge(
        period_format[[*format_period_columns, "prior_format_ownership"]],
        on=format_period_columns,
        how="left",
    )
    frame["prior_format_ownership"] = frame["prior_format_ownership"].fillna(5.0)
    frame["prior_slot_ownership"] = frame["prior_slot_ownership"].fillna(frame["prior_format_ownership"])
    frame["prior_player_ownership"] = frame["prior_player_ownership"].fillna(frame["prior_slot_ownership"])
    return frame.sort_values(["season", "week", "slate", "player_id", "roster_slot"]).reset_index(drop=True)


def _ownership_design_matrices(
    train_rows: pd.DataFrame,
    prediction_rows: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    combined = pd.concat(
        [
            train_rows[[*OWNERSHIP_NUMERIC_FEATURES, *OWNERSHIP_CATEGORICAL_FEATURES]],
            prediction_rows[[*OWNERSHIP_NUMERIC_FEATURES, *OWNERSHIP_CATEGORICAL_FEATURES]],
        ],
        ignore_index=True,
    )
    design = pd.get_dummies(
        combined,
        columns=OWNERSHIP_CATEGORICAL_FEATURES,
        dtype=float,
    ).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return design.iloc[: len(train_rows)].copy(), design.iloc[len(train_rows) :].copy()


def generate_walk_forward_ownership_predictions(
    feature_frame: pd.DataFrame,
    *,
    min_train_rows: int = MIN_OWNERSHIP_TRAIN_ROWS,
) -> pd.DataFrame:
    """Generate ownership predictions using only slates before each validation slate."""
    observed = feature_frame.loc[feature_frame[OWNERSHIP_TARGET].notna()].copy()
    periods = sorted({(int(row.season), int(row.week)) for row in observed[["season", "week"]].itertuples(index=False)})
    outputs: list[pd.DataFrame] = []
    for validation_season, validation_week in periods:
        prior_mask = (observed["season"] < validation_season) | (
            (observed["season"] == validation_season) & (observed["week"] < validation_week)
        )
        validation_mask = (observed["season"] == validation_season) & (observed["week"] == validation_week)
        train_rows = observed.loc[prior_mask]
        validation_rows = observed.loc[validation_mask]
        if len(train_rows) < min_train_rows or validation_rows.empty:
            continue

        X_train, X_validation = _ownership_design_matrices(train_rows, validation_rows)
        model = GradientBoostingRegressor(random_state=42, loss="huber")
        model.fit(X_train, train_rows[OWNERSHIP_TARGET].astype(float))
        predictions = np.clip(model.predict(X_validation), 0.0, 100.0)
        output = validation_rows[
            ["season", "week", "slate", "player_id", "position", "contest_format", "roster_slot", OWNERSHIP_TARGET]
        ].copy()
        output["predicted_ownership"] = predictions
        output["baseline_ownership"] = validation_rows["prior_player_ownership"].to_numpy(dtype=float)
        latest_prior = train_rows.sort_values(["season", "week"]).iloc[-1]
        output["training_through_season"] = int(latest_prior["season"])
        output["training_through_week"] = int(latest_prior["week"])
        outputs.append(output)
    return pd.concat(outputs, ignore_index=True) if outputs else pd.DataFrame()


def ownership_model_metrics(walk_forward: pd.DataFrame) -> dict[str, Any]:
    """Return declared ownership accuracy, rank, and calibration diagnostics."""
    if walk_forward.empty:
        return {
            "method": "slate_aware_gradient_boosting",
            "walk_forward_rows": 0,
            "mae": None,
            "baseline_mae": None,
            "rank_correlation": None,
            "calibration_by_format_slot": {},
            "promotion_gate": {"status": "blocked", "checks": {"walk_forward_rows_at_least_500": False}},
        }

    actual = walk_forward[OWNERSHIP_TARGET].astype(float)
    predicted = walk_forward["predicted_ownership"].astype(float)
    baseline = walk_forward["baseline_ownership"].astype(float)

    def rank_correlation(frame: pd.DataFrame) -> float:
        if len(frame) < 2:
            return 0.0
        correlation = frame["predicted_ownership"].rank().corr(frame[OWNERSHIP_TARGET].rank())
        return float(correlation) if pd.notna(correlation) else 0.0

    calibration: dict[str, dict[str, float | int]] = {}
    for (contest_format, roster_slot), group in walk_forward.groupby(["contest_format", "roster_slot"]):
        calibration[f"{contest_format}|{roster_slot}"] = {
            "samples": len(group),
            "mae": float(np.mean(np.abs(group["predicted_ownership"] - group[OWNERSHIP_TARGET]))),
            "mean_predicted": float(group["predicted_ownership"].mean()),
            "mean_actual": float(group[OWNERSHIP_TARGET].mean()),
            "bias": float((group["predicted_ownership"] - group[OWNERSHIP_TARGET]).mean()),
            "rank_correlation": rank_correlation(group),
        }

    mae = float(np.mean(np.abs(predicted - actual)))
    baseline_mae = float(np.mean(np.abs(baseline - actual)))
    overall_rank = rank_correlation(walk_forward)
    checks = {
        "walk_forward_rows_at_least_500": len(walk_forward) >= 500,
        "mae_beats_prior_player_average": mae <= baseline_mae,
        "rank_correlation_at_least_0_50": overall_rank >= 0.50,
        "format_slot_groups_have_30_rows": bool(calibration)
        and min(int(value["samples"]) for value in calibration.values()) >= 30,
    }
    return {
        "method": "slate_aware_gradient_boosting",
        "walk_forward_rows": len(walk_forward),
        "mae": mae,
        "baseline_mae": baseline_mae,
        "rank_correlation": overall_rank,
        "calibration_by_format_slot": calibration,
        "promotion_gate": {
            "status": "passed" if all(checks.values()) else "blocked",
            "checks": checks,
            "policy": "diagnostic only; model promotion remains explicit",
        },
    }


@dataclass
class OwnershipLoadResult:
    season: int
    week: int
    slate: str
    rows_written: int
    message: str
    contest_id: str | None = None
    source_file_id: str | None = None
    target_persisted: bool = False
    ownership_run_id: str | None = None
    data_cutoff_at: datetime | None = None
    model_metrics: dict[str, Any] | None = None


class OwnershipService:
    """Load DK contest standings and expose derived ownership data."""

    RAW_TABLE = "dk_contest_standings_rows"
    ENTRY_TABLE = "dk_contest_entries"
    OWNERSHIP_TABLE = "dk_ownership"

    def __init__(self, connection_string: str | None = None, engine: Engine | None = None) -> None:
        self.connection_string = connection_string or get_connection_string()
        self.engine = engine or create_engine(self.connection_string)

    def load_contest_standings(
        self,
        season: int,
        week: int,
        slate: str,
        path: str,
        *,
        contest_id: str | None = None,
        contest_name: str | None = None,
        contest_format: str | None = None,
        contest_type: str | None = None,
        entry_fee: float | None = None,
        field_size: int | None = None,
        max_entries_per_user: int | None = None,
        prize_pool: float | None = None,
        payout_tiers: list[dict[str, Any]] | None = None,
    ) -> OwnershipLoadResult:
        source_path, df = self._read_standings(path)
        standings = self._normalize_standings(df, season=season, week=week, slate=slate, source_path=source_path)
        if standings.empty:
            return OwnershipLoadResult(season, week, slate, 0, f"No contest standings rows found in {source_path.name}")

        source_info = self._source_file_info(source_path)
        observed_field_size = int(standings["entry_id"].nunique())
        resolved_field_size = int(field_size or observed_field_size)
        if resolved_field_size < observed_field_size:
            raise ValueError(
                f"field_size {resolved_field_size} is smaller than {observed_field_size} observed entries"
            )
        for label, value in (
            ("entry_fee", entry_fee),
            ("prize_pool", prize_pool),
        ):
            if value is not None and float(value) < 0:
                raise ValueError(f"{label} cannot be negative")
        if max_entries_per_user is not None and int(max_entries_per_user) < 1:
            raise ValueError("max_entries_per_user must be at least 1")
        resolved_format = self._resolve_contest_format(
            contest_format,
            slate=slate,
            roster_positions=standings.get("roster_position"),
        )
        resolved_contest_name = contest_name or source_path.stem
        contest_classification = classify_contest_type(
            resolved_contest_name,
            contest_type,
        )
        resolved_contest_id = self._resolve_contest_id(
            contest_id,
            season=season,
            week=week,
            slate=slate,
            content_sha256=source_info["content_sha256"],
        )
        normalized_tiers = self._normalize_payout_tiers(
            payout_tiers or [],
            field_size=resolved_field_size,
        )
        standings["contest_id"] = resolved_contest_id
        standings["source_file_id"] = source_info["source_file_id"]

        ownership_source = self._ownership_source_rows(standings)
        ownership_source = self._attach_player_ids(ownership_source) if not ownership_source.empty else ownership_source
        entries = self._build_entries(standings)
        ownership = self._build_ownership(ownership_source) if not ownership_source.empty else pd.DataFrame()

        ensure_table_columns(self.engine, self.RAW_TABLE, standings.head(0))
        ensure_table_columns(self.engine, self.ENTRY_TABLE, entries.head(0))
        if not ownership.empty:
            ensure_table_columns(self.engine, self.OWNERSHIP_TABLE, ownership.head(0))
        with self.engine.begin() as conn:
            self._delete_contest(conn, self.RAW_TABLE, resolved_contest_id)
            self._delete_contest(conn, self.ENTRY_TABLE, resolved_contest_id)
            if not ownership.empty and inspect(self.engine).has_table(self.OWNERSHIP_TABLE):
                self._delete_contest(conn, self.OWNERSHIP_TABLE, resolved_contest_id)

        self._append_table(self.RAW_TABLE, standings)
        self._append_table(self.ENTRY_TABLE, entries)
        self._append_table(self.OWNERSHIP_TABLE, ownership)
        target_persisted = self._persist_target_contest(
            contest_id=resolved_contest_id,
            source_info=source_info,
            season=season,
            week=week,
            slate=slate,
            contest_name=resolved_contest_name,
            contest_format=resolved_format,
            contest_type=str(contest_classification["contest_type"]),
            contest_type_source=str(contest_classification["contest_type_source"]),
            cash_game_type=contest_classification["cash_game_type"],
            entry_fee=entry_fee,
            field_size=resolved_field_size,
            max_entries_per_user=max_entries_per_user,
            prize_pool=prize_pool,
            payout_tiers=normalized_tiers,
            entries=entries,
        )

        return OwnershipLoadResult(
            season=season,
            week=week,
            slate=slate,
            rows_written=len(ownership),
            message=(
                f"Loaded {len(standings)} contest standings rows, {len(entries)} entries, "
                f"and {len(ownership)} ownership rows from {source_path.name}"
            ),
            contest_id=resolved_contest_id,
            source_file_id=source_info["source_file_id"],
            target_persisted=target_persisted,
        )

    def _load_ownership_model_rows(
        self,
        *,
        season: int,
        week: int,
        slate: str,
        data_cutoff_at: datetime | None = None,
    ) -> pd.DataFrame:
        """Load observed ownership plus point-in-time salary/projection context."""
        if not inspect(self.engine).has_table(self.OWNERSHIP_TABLE):
            return pd.DataFrame()
        inspector = inspect(self.engine)
        if not inspector.has_table("snapshot_salary", schema="target"):
            return pd.DataFrame()

        params: dict[str, Any] = {"season": season, "week": week}
        salary_cutoff_clause = ""
        projection_cutoff_clause = ""
        if data_cutoff_at is not None:
            params["data_cutoff_at"] = data_cutoff_at
            salary_cutoff_clause = " AND as_of <= :data_cutoff_at"
            projection_cutoff_clause = " AND created_at <= :data_cutoff_at"

        with self.engine.begin() as conn:
            ownership = pd.read_sql(
                text(
                    "SELECT season, week, slate, player_id, player_master_id, "
                    "player_display_name, roster_position, actual_ownership "
                    f"FROM {self.OWNERSHIP_TABLE} "
                    "WHERE actual_ownership IS NOT NULL "
                    "AND (season < :season OR (season = :season AND week < :week))"
                ),
                conn,
                params=params,
            )
            salary = pd.read_sql(
                text(
                    "SELECT season, week, COALESCE(slate, slate_id) AS slate, player_id, "
                    "site_player_id, salary, roster_position, team_id, opponent_team_id "
                    "FROM target.snapshot_salary "
                    "WHERE (season < :season OR (season = :season AND week <= :week))"
                    + salary_cutoff_clause
                ),
                conn,
                params=params,
            )
            projections = (
                pd.read_sql(
                    text(
                        "SELECT season, week, slate_id AS slate, player_id, mean AS projection_mean, "
                        "p90 AS projection_p90, created_at "
                        "FROM target.player_projection projection "
                        "WHERE (season < :season OR (season = :season AND week <= :week)) "
                        "AND projection.projection_run_id = COALESCE(("
                        "SELECT active.projection_run_id "
                        "FROM target.active_projection_run active "
                        "WHERE active.season = projection.season "
                        "AND active.week = projection.week "
                        "AND UPPER(active.slate_id) = UPPER(COALESCE(projection.slate_id, 'DEFAULT'))"
                        "), ("
                        "SELECT fallback.projection_run_id "
                        "FROM target.player_projection fallback "
                        "WHERE fallback.season = projection.season "
                        "AND fallback.week = projection.week "
                        "AND COALESCE(UPPER(fallback.slate_id), 'DEFAULT') = "
                        "COALESCE(UPPER(projection.slate_id), 'DEFAULT') "
                        "ORDER BY fallback.created_at DESC, fallback.projection_run_id "
                        "LIMIT 1"
                        "))"
                        + projection_cutoff_clause
                    ),
                    conn,
                    params=params,
                )
                if inspector.has_table("player_projection", schema="target")
                else pd.DataFrame()
            )
            players = (
                pd.read_sql(
                    text(
                        "SELECT player_id, full_name AS player_display_name, "
                        "primary_position AS dimension_position FROM target.dim_player"
                    ),
                    conn,
                )
                if inspector.has_table("dim_player", schema="target")
                else pd.DataFrame()
            )

        if ownership.empty or salary.empty:
            return pd.DataFrame()

        for frame in (ownership, salary):
            frame["slate"] = frame["slate"].map(_normalized_slate)
            frame["player_id"] = frame["player_id"].astype(str)
        if not projections.empty:
            projections["slate"] = projections["slate"].map(_normalized_slate)
            projections["player_id"] = projections["player_id"].astype(str)
        ownership["player_id"] = ownership.get("player_master_id", ownership["player_id"]).fillna(
            ownership["player_id"]
        ).astype(str)
        ownership["actual_ownership"] = pd.to_numeric(
            ownership["actual_ownership"], errors="coerce"
        )
        ownership = ownership.dropna(subset=["actual_ownership"])
        ownership["roster_position"] = ownership["roster_position"].fillna("").astype(str).str.upper()

        salary["salary"] = pd.to_numeric(salary["salary"], errors="coerce").fillna(0.0)
        salary["roster_position"] = salary["roster_position"].fillna("").astype(str).str.upper()
        salary["position"] = salary["roster_position"].fillna("").astype(str).str.split("/").str[0].str.upper()
        salary_context = (
            salary.groupby(["season", "week", "slate", "player_id", "roster_position"], dropna=False)
            .agg(
                salary=("salary", "max"),
                salary_roster_position=("roster_position", "first"),
                position=("position", "first"),
            )
            .reset_index()
        )
        if not players.empty:
            players["player_id"] = players["player_id"].astype(str)
            salary_context = salary_context.merge(players, on="player_id", how="left")
            salary_context["position"] = salary_context["dimension_position"].fillna(
                salary_context["position"]
            )
        else:
            salary_context["player_display_name"] = salary_context["player_id"]
        salary_player_context = salary_context.copy()
        salary_player_context["slot_priority"] = (
            salary_player_context["salary_roster_position"].str.contains("CPT|CAPTAIN", regex=True)
        ).astype(int)
        salary_player_context = (
            salary_player_context.sort_values(["slot_priority", "salary"])
            .drop_duplicates(["season", "week", "slate", "player_id"], keep="first")
            .drop(columns="slot_priority")
        )
        if projections.empty:
            projection_context = pd.DataFrame(
                columns=["season", "week", "player_id", "projection_mean", "projection_p90"]
            )
        else:
            projections["created_at"] = pd.to_datetime(projections["created_at"], errors="coerce", utc=True)
            projection_context = (
                projections.sort_values("created_at")
                .drop_duplicates(["season", "week", "player_id"], keep="last")
                [["season", "week", "player_id", "projection_mean", "projection_p90"]]
            )

        history = ownership.merge(
            salary_context,
            on=["season", "week", "slate", "player_id", "roster_position"],
            how="left",
            suffixes=("", "_salary"),
        ).merge(
            salary_player_context,
            on=["season", "week", "slate", "player_id"],
            how="left",
            suffixes=("", "_fallback"),
        ).merge(
            projection_context,
            on=["season", "week", "player_id"],
            how="left",
        )
        for column in ("salary", "salary_roster_position", "position", "dimension_position"):
            fallback_column = f"{column}_fallback"
            if fallback_column in history.columns:
                history[column] = history[column].fillna(history[fallback_column])
        history["roster_position"] = history["roster_position"].fillna(
            history["salary_roster_position"]
        )
        history["position"] = history.get("dimension_position", history["position"]).fillna(
            history["position"]
        ).fillna(history["roster_position"])
        history["player_display_name"] = history.get(
            "player_display_name", history["player_id"]
        ).fillna(history.get("player_display_name_fallback", history["player_id"])).fillna(history["player_id"])

        target_slate = _normalized_slate(slate)
        target = salary_context.loc[
            (salary_context["season"] == season)
            & (salary_context["week"] == week)
            & (salary_context["slate"] == target_slate)
        ].copy()
        if target.empty:
            return pd.DataFrame()
        target = target.merge(
            projection_context.loc[
                (projection_context["season"] == season)
                & (projection_context["week"] == week)
            ],
            on=["season", "week", "player_id"],
            how="left",
        )
        target["roster_position"] = target["salary_roster_position"]
        target["player_master_id"] = target["player_id"]
        target["player_display_name"] = target.get(
            "player_display_name", target["player_id"]
        ).fillna(target["player_id"])
        target["actual_ownership"] = np.nan
        target["slate"] = target_slate
        return pd.concat([history, target], ignore_index=True, sort=False)

    def _persist_target_ownership_run(
        self,
        *,
        ownership_run_id: str,
        season: int,
        week: int,
        slate: str,
        data_cutoff_at: datetime,
        training_rows: int,
        metrics: dict[str, Any],
        projections: pd.DataFrame,
    ) -> bool:
        validate_target_schema(
            self.engine,
            consumer=type(self).__name__,
            required_tables=("ownership_model_run", "ownership_projection"),
        )
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO target.ownership_model_run
                            (ownership_run_id, model_id, season, week, slate_id,
                             data_cutoff_at, training_rows, params_json, metrics_json, status)
                        VALUES
                            (:ownership_run_id, :model_id, :season, :week, :slate_id,
                             :data_cutoff_at, :training_rows, CAST(:params_json AS JSONB),
                             CAST(:metrics_json AS JSONB), 'completed')
                        """
                    ),
                    {
                        "ownership_run_id": ownership_run_id,
                        "model_id": OWNERSHIP_MODEL_ID,
                        "season": season,
                        "week": week,
                        "slate_id": slate,
                        "data_cutoff_at": data_cutoff_at,
                        "training_rows": training_rows,
                        "params_json": json.dumps(
                            {
                                "algorithm": "GradientBoostingRegressor",
                                "loss": "huber",
                                "random_state": 42,
                                "numeric_features": OWNERSHIP_NUMERIC_FEATURES,
                                "categorical_features": OWNERSHIP_CATEGORICAL_FEATURES,
                                "leakage_policy": "training slates strictly before target season/week",
                            },
                            sort_keys=True,
                        ),
                        "metrics_json": json.dumps(metrics, sort_keys=True, allow_nan=False),
                    },
                )
                payload = []
                for row in projections.to_dict(orient="records"):
                    feature_payload = {
                        column: _json_safe_value(row.get(column))
                        for column in [*OWNERSHIP_NUMERIC_FEATURES, *OWNERSHIP_CATEGORICAL_FEATURES]
                    }
                    payload.append(
                        {
                            "ownership_run_id": ownership_run_id,
                            "season": season,
                            "week": week,
                            "slate_id": slate,
                            "player_id": str(row["player_id"]),
                            "roster_position": str(row["roster_position"]),
                            "projected_ownership": float(row["projected_ownership"]),
                            "data_cutoff_at": data_cutoff_at,
                            "feature_json": json.dumps(feature_payload, sort_keys=True, allow_nan=False),
                        }
                    )
                if payload:
                    conn.execute(
                        text(
                            """
                            INSERT INTO target.ownership_projection
                                (ownership_run_id, season, week, slate_id, player_id,
                                 roster_position, projected_ownership, data_cutoff_at, feature_json)
                            VALUES
                                (:ownership_run_id, :season, :week, :slate_id, :player_id,
                                 :roster_position, :projected_ownership, :data_cutoff_at,
                                 CAST(:feature_json AS JSONB))
                            """
                        ),
                        payload,
                    )
            return True
        except Exception as exc:  # noqa: BLE001 - preserve legacy output if target persistence fails
            logger.warning("Failed to persist target ownership run: %s", exc)
            return False

    def run_projection_model(
        self,
        season: int,
        week: int,
        slate: str | None = None,
        positions: list[str] | None = None,
        data_cutoff_at: datetime | None = None,
    ) -> OwnershipLoadResult:
        """Fit and persist a leakage-safe slate-aware ownership model."""
        if not slate:
            return OwnershipLoadResult(
                season,
                week,
                "",
                0,
                "Slate is required for slate-aware ownership modeling",
            )
        cutoff = data_cutoff_at or _utcnow()
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=UTC)
        model_rows = self._load_ownership_model_rows(
            season=season,
            week=week,
            slate=slate,
            data_cutoff_at=cutoff,
        )
        if model_rows.empty:
            return OwnershipLoadResult(
                season,
                week,
                slate,
                0,
                "Ownership modeling requires prior contest ownership and a target salary snapshot",
            )

        feature_frame = build_slate_aware_ownership_frame(model_rows)
        target_slate = _normalized_slate(slate)
        target_mask = (
            (feature_frame["season"] == season)
            & (feature_frame["week"] == week)
            & (feature_frame["slate"] == target_slate)
            & feature_frame[OWNERSHIP_TARGET].isna()
        )
        training_mask = (
            ((feature_frame["season"] < season) | ((feature_frame["season"] == season) & (feature_frame["week"] < week)))
            & feature_frame[OWNERSHIP_TARGET].notna()
        )
        training_rows = feature_frame.loc[training_mask].copy()
        target_rows = feature_frame.loc[target_mask].copy()
        if positions:
            normalized_positions = {str(position).upper() for position in positions}
            target_rows = target_rows.loc[target_rows["position"].isin(normalized_positions)]
        if len(training_rows) < MIN_OWNERSHIP_TRAIN_ROWS or target_rows.empty:
            return OwnershipLoadResult(
                season,
                week,
                slate,
                0,
                f"Ownership model needs at least {MIN_OWNERSHIP_TRAIN_ROWS} prior rows and a non-empty target slate",
            )

        walk_forward = generate_walk_forward_ownership_predictions(training_rows)
        metrics = ownership_model_metrics(walk_forward)
        X_train, X_target = _ownership_design_matrices(training_rows, target_rows)
        model = GradientBoostingRegressor(random_state=42, loss="huber")
        model.fit(X_train, training_rows[OWNERSHIP_TARGET].astype(float))
        target_rows["projected_ownership"] = np.clip(model.predict(X_target), 0.0, 100.0)

        ownership_run_id = str(uuid.uuid4())
        target_rows["player_master_id"] = target_rows["player_id"]
        target_rows["roster_position"] = target_rows["roster_slot"]
        target_rows["actual_ownership"] = pd.NA
        target_rows["source"] = OWNERSHIP_MODEL_ID
        target_rows["updated_at"] = _utcnow()
        target_rows["ownership_run_id"] = ownership_run_id
        target_rows["data_cutoff_at"] = cutoff
        target_rows["model_metrics_json"] = json.dumps(metrics, sort_keys=True, allow_nan=False)
        output_columns = [
            "season",
            "week",
            "slate",
            "player_id",
            "player_master_id",
            "player_display_name",
            "roster_position",
            "projected_ownership",
            "actual_ownership",
            "source",
            "updated_at",
            "ownership_run_id",
            "data_cutoff_at",
            "model_metrics_json",
            *OWNERSHIP_NUMERIC_FEATURES,
            "position",
            "contest_format",
            "roster_slot",
        ]
        projection = target_rows[output_columns].copy()
        ensure_table_columns(self.engine, self.OWNERSHIP_TABLE, projection.head(0))
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    f"DELETE FROM {self.OWNERSHIP_TABLE} "
                    "WHERE season = :season AND week = :week AND slate = :slate "
                    "AND source <> 'contest_standings'"
                ),
                {"season": season, "week": week, "slate": target_slate},
            )
        self._append_table(self.OWNERSHIP_TABLE, projection)
        target_persisted = self._persist_target_ownership_run(
            ownership_run_id=ownership_run_id,
            season=season,
            week=week,
            slate=target_slate,
            data_cutoff_at=cutoff,
            training_rows=len(training_rows),
            metrics=metrics,
            projections=target_rows,
        )
        return OwnershipLoadResult(
            season=season,
            week=week,
            slate=target_slate,
            rows_written=len(projection),
            message=f"Wrote {len(projection)} slate-aware ownership projection rows",
            target_persisted=target_persisted,
            ownership_run_id=ownership_run_id,
            data_cutoff_at=cutoff,
            model_metrics=metrics,
        )

    def analyze_past_slate(self, season: int, week: int, slate: str, path: str, top_n: int = 100) -> dict:
        source_path, df = self._read_standings(path)
        standings = self._normalize_standings(df, season=season, week=week, slate=slate, source_path=source_path)
        if standings.empty:
            return {
                "season": season,
                "week": week,
                "slate": slate,
                "lineups": 0,
                "top_n": top_n,
                "exposures": [],
                "bucket_stats": [],
                "top_lineups": [],
                "message": f"No contest standings rows found in {source_path.name}",
            }

        top_entries = self._top_entries(standings, top_n)
        top_rows = standings[standings["entry_id"].isin(top_entries["entry_id"])]
        lineup_players = self._lineup_player_rows(top_rows, standings)
        lineups = max(len(top_entries), 1)
        if lineup_players.empty:
            exposures = pd.DataFrame(columns=["player_display_name", "roster_position", "count", "pct"])
        else:
            exposures = (
                lineup_players.groupby(["player_display_name", "roster_position"], dropna=False)
                .size()
                .reset_index(name="count")
                .sort_values(["count", "player_display_name"], ascending=[False, True])
            )
            exposures["pct"] = (exposures["count"] / lineups * 100).round(2)

        lineup_stats = self._lineup_stats(lineup_players, season=season, week=week, slate=slate)
        bucket_stats = self._bucket_stats(lineup_stats)
        top_lineups = self._top_lineups_payload(lineup_stats)

        return {
            "season": season,
            "week": week,
            "slate": slate,
            "lineups": int(standings["entry_id"].nunique()),
            "top_n": int(min(top_n, len(top_entries))),
            "exposures": exposures.head(100).to_dict(orient="records"),
            "bucket_stats": bucket_stats,
            "top_lineups": top_lineups,
            "message": f"Analyzed top {min(top_n, len(top_entries))} lineups from {source_path.name}",
        }

    def fetch_projected_ownership(
        self,
        season: int,
        week: int,
        slate: str | None = None,
        limit: int = 500,
    ) -> list[dict]:
        if not inspect(self.engine).has_table(self.OWNERSHIP_TABLE):
            return []

        existing_columns = {
            column["name"] for column in inspect(self.engine).get_columns(self.OWNERSHIP_TABLE)
        }
        selected_columns = [
            column
            for column in [
                "player_id",
                "player_master_id",
                "player_display_name",
                "roster_position",
                "projected_ownership",
                "actual_ownership",
                "source",
                "ownership_run_id",
                "data_cutoff_at",
                "salary",
                "projection_mean",
                "projection_p90",
                "salary_percentile",
                "projection_percentile",
                "prior_player_ownership",
                "contest_format",
                "roster_slot",
                "model_metrics_json",
            ]
            if column in existing_columns
        ]
        query = (
            f"SELECT {', '.join(selected_columns)} "
            f"FROM {self.OWNERSHIP_TABLE} "
            f"WHERE season = :season AND week = :week "
        )
        params: dict[str, object] = {"season": season, "week": week, "limit": limit}
        if slate:
            query += "AND slate = :slate "
            params["slate"] = slate
        query += "ORDER BY projected_ownership DESC NULLS LAST, player_display_name ASC LIMIT :limit"

        with self.engine.begin() as conn:
            rows = pd.read_sql(text(query), conn, params=params)
        if rows.empty:
            return []
        return rows.where(pd.notna(rows), None).to_dict(orient="records")

    @staticmethod
    def _source_file_info(source_path: Path) -> dict[str, Any]:
        if source_path.suffix.lower() == ".zip":
            with ZipFile(source_path) as archive:
                csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
                if not csv_names:
                    raise ValueError(f"No CSV file found inside {source_path}")
                content = archive.read(csv_names[0])
        else:
            content = source_path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        return {
            "source_file_id": f"dk_file_{digest}",
            "content_sha256": digest,
            "original_path": str(source_path),
            "file_name": source_path.name,
            "file_size_bytes": int(source_path.stat().st_size),
        }

    @staticmethod
    def _resolve_contest_id(
        contest_id: str | None,
        *,
        season: int,
        week: int,
        slate: str,
        content_sha256: str,
    ) -> str:
        explicit = str(contest_id or "").strip()
        if explicit:
            return explicit
        identity = f"draftkings|{season}|{week}|{slate.strip().upper()}|{content_sha256}"
        return f"dk_{hashlib.sha256(identity.encode('utf-8')).hexdigest()}"

    @staticmethod
    def _resolve_contest_format(
        contest_format: str | None,
        *,
        slate: str,
        roster_positions: pd.Series | None,
    ) -> str:
        if contest_format:
            normalized = str(contest_format).strip().lower()
            if normalized not in {"classic", "showdown"}:
                raise ValueError("contest_format must be 'classic' or 'showdown'")
            return normalized
        slate_key = str(slate).upper()
        positions = (
            set(roster_positions.dropna().astype(str).str.upper())
            if roster_positions is not None
            else set()
        )
        return "showdown" if "CPT" in positions or "CAPTAIN" in slate_key or "SHOWDOWN" in slate_key else "classic"

    @staticmethod
    def _normalize_payout_tiers(
        payout_tiers: list[dict[str, Any]],
        *,
        field_size: int,
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for tier in payout_tiers:
            min_rank = int(tier["min_rank"])
            max_rank = int(tier.get("max_rank", min_rank))
            payout_raw = tier.get("payout")
            payout = float(payout_raw) if payout_raw is not None else None
            prize_description = str(tier.get("prize_description") or "").strip() or None
            if min_rank < 1 or max_rank < min_rank:
                raise ValueError("Payout tiers require 1 <= min_rank <= max_rank")
            if field_size > 0 and max_rank > field_size:
                raise ValueError("Payout tier rank exceeds contest field_size")
            if payout is not None and payout < 0:
                raise ValueError("Payout tier payout cannot be negative")
            if payout is None and prize_description is None:
                raise ValueError("Payout tiers require payout or prize_description")
            normalized.append(
                {
                    "min_rank": min_rank,
                    "max_rank": max_rank,
                    "payout": payout,
                    "prize_description": prize_description,
                }
            )
        normalized.sort(key=lambda row: (row["min_rank"], row["max_rank"]))
        for previous, current in zip(normalized, normalized[1:], strict=False):
            if current["min_rank"] <= previous["max_rank"]:
                raise ValueError("Payout tiers cannot overlap")
        return normalized

    def _persist_target_contest(
        self,
        *,
        contest_id: str,
        source_info: dict[str, Any],
        season: int,
        week: int,
        slate: str,
        contest_name: str,
        contest_format: str,
        contest_type: str,
        contest_type_source: str,
        cash_game_type: str | None,
        entry_fee: float | None,
        field_size: int,
        max_entries_per_user: int | None,
        prize_pool: float | None,
        payout_tiers: list[dict[str, Any]],
        entries: pd.DataFrame | None,
    ) -> bool:
        validate_target_schema(
            self.engine,
            consumer=type(self).__name__,
            required_tables=(
                "source_file_import",
                "dfs_contest",
                "dfs_contest_payout_tier",
                "dfs_contest_entry_result",
            ),
        )
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO target.source_file_import
                            (source_file_id, source_type, content_sha256, original_path,
                             file_name, file_size_bytes, metadata_json)
                        VALUES
                            (:source_file_id, 'draftkings_contest_standings', :content_sha256,
                             :original_path, :file_name, :file_size_bytes,
                             CAST(:metadata_json AS JSONB))
                        ON CONFLICT (source_file_id) DO UPDATE SET
                            original_path = EXCLUDED.original_path,
                            file_name = EXCLUDED.file_name,
                            file_size_bytes = EXCLUDED.file_size_bytes,
                            last_ingested_at = now()
                        """
                    ),
                    {**source_info, "metadata_json": json.dumps({"site": "draftkings"})},
                )
                conn.execute(
                    text(
                        """
                        INSERT INTO target.dfs_contest
                            (contest_id, source_file_id, site, slate_id, season, week,
                             contest_name, contest_format, contest_type, entry_fee, field_size,
                             max_entries_per_user, prize_pool, metadata_json)
                        VALUES
                            (:contest_id, :source_file_id, 'draftkings', :slate_id,
                             :season, :week, :contest_name, :contest_format, :contest_type,
                             :entry_fee,
                             :field_size, :max_entries_per_user, :prize_pool,
                             CAST(:metadata_json AS JSONB))
                        ON CONFLICT (contest_id) DO UPDATE SET
                            source_file_id = EXCLUDED.source_file_id,
                            slate_id = EXCLUDED.slate_id,
                            season = EXCLUDED.season,
                            week = EXCLUDED.week,
                            contest_name = EXCLUDED.contest_name,
                            contest_format = EXCLUDED.contest_format,
                            contest_type = EXCLUDED.contest_type,
                            entry_fee = EXCLUDED.entry_fee,
                            field_size = EXCLUDED.field_size,
                            max_entries_per_user = EXCLUDED.max_entries_per_user,
                            prize_pool = EXCLUDED.prize_pool,
                            metadata_json = EXCLUDED.metadata_json,
                            updated_at = now()
                        """
                    ),
                    {
                        "contest_id": contest_id,
                        "source_file_id": source_info["source_file_id"],
                        "slate_id": slate,
                        "season": season,
                        "week": week,
                        "contest_name": contest_name,
                        "contest_format": contest_format,
                        "contest_type": contest_type,
                        "entry_fee": entry_fee,
                        "field_size": field_size,
                        "max_entries_per_user": max_entries_per_user,
                        "prize_pool": prize_pool,
                        "metadata_json": json.dumps(
                            {
                                "payout_tiers_supplied": len(payout_tiers),
                                "contest_type_source": contest_type_source,
                                "cash_game_type": cash_game_type,
                            },
                            sort_keys=True,
                        ),
                    },
                )
                conn.execute(
                    text(
                        "DELETE FROM target.dfs_contest_payout_tier "
                        "WHERE contest_id = :contest_id"
                    ),
                    {"contest_id": contest_id},
                )
                if payout_tiers:
                    conn.execute(
                        text(
                            """
                            INSERT INTO target.dfs_contest_payout_tier
                                (contest_id, min_rank, max_rank, payout, prize_description)
                            VALUES
                                (:contest_id, :min_rank, :max_rank, :payout, :prize_description)
                            """
                        ),
                        [{"contest_id": contest_id, **tier} for tier in payout_tiers],
                    )
                entry_payload = []
                for row in entries.to_dict(orient="records") if entries is not None else []:
                    entry_id = str(row.get("entry_id") or "").strip()
                    if not entry_id:
                        continue
                    rank_value = _json_safe_value(row.get("rank"))
                    points_value = _json_safe_value(row.get("entry_points"))
                    entry_payload.append(
                        {
                            "contest_id": contest_id,
                            "entry_id": entry_id,
                            "source_file_id": source_info["source_file_id"],
                            "entry_name": _json_safe_value(row.get("entry_name")),
                            "rank": int(rank_value) if rank_value is not None else None,
                            "entry_points": float(points_value) if points_value is not None else None,
                            "lineup_text": _json_safe_value(row.get("lineup_text")),
                            "ingested_at": _json_safe_value(row.get("ingested_at")),
                        }
                    )
                if entries is not None:
                    conn.execute(
                        text(
                            "DELETE FROM target.dfs_contest_entry_result "
                            "WHERE contest_id = :contest_id"
                        ),
                        {"contest_id": contest_id},
                    )
                if entry_payload:
                    conn.execute(
                        text(
                            """
                            INSERT INTO target.dfs_contest_entry_result
                                (contest_id, entry_id, source_file_id, entry_name, rank,
                                 entry_points, lineup_text, ingested_at)
                            VALUES
                                (:contest_id, :entry_id, :source_file_id, :entry_name, :rank,
                                 :entry_points, :lineup_text, :ingested_at)
                            """
                        ),
                        entry_payload,
                    )
            return True
        except Exception as exc:  # noqa: BLE001 - keep the legacy ownership import available during migration
            logger.warning("Failed to persist target contest metadata: %s", exc)
            return False

    def _read_standings(self, path: str) -> tuple[Path, pd.DataFrame]:
        expanded = Path(path).expanduser()
        if not expanded.exists():
            raise FileNotFoundError(f"Contest standings file not found: {expanded}")
        if expanded.suffix.lower() == ".zip":
            with ZipFile(expanded) as archive:
                csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
                if not csv_names:
                    raise ValueError(f"No CSV file found inside {expanded}")
                with archive.open(csv_names[0]) as handle:
                    return expanded, pd.read_csv(handle, encoding="utf-8-sig", low_memory=False)
        sep = "\t" if expanded.suffix.lower() in {".tsv", ".tab"} else ","
        return expanded, pd.read_csv(expanded, encoding="utf-8-sig", sep=sep, low_memory=False)

    def _normalize_standings(self, df: pd.DataFrame, season: int, week: int, slate: str, source_path: Path) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame()
        normalized = df.copy()
        normalized.columns = [str(col).replace("\ufeff", "").strip() for col in normalized.columns]
        rename = {
            "Rank": "rank",
            "EntryId": "entry_id",
            "EntryName": "entry_name",
            "TimeRemaining": "time_remaining",
            "Points": "entry_points",
            "Lineup": "lineup_text",
            "Player": "player_display_name",
            "Roster Position": "roster_position",
            "%Drafted": "pct_drafted",
            "FPTS": "fpts",
        }
        normalized = normalized.rename(columns=rename)
        required = {"entry_id", "player_display_name", "roster_position", "pct_drafted"}
        missing = required - set(normalized.columns)
        if missing:
            raise ValueError(f"Contest standings file missing required columns: {', '.join(sorted(missing))}")

        keep = [col for col in rename.values() if col in normalized.columns]
        normalized = normalized[keep].copy()
        normalized["season"] = int(season)
        normalized["week"] = int(week)
        normalized["slate"] = slate
        normalized["source_file"] = str(source_path)
        normalized["ingested_at"] = _utcnow()
        normalized["rank"] = pd.to_numeric(normalized.get("rank"), errors="coerce").astype("Int64")
        normalized["entry_points"] = pd.to_numeric(normalized.get("entry_points"), errors="coerce")
        normalized["fpts"] = pd.to_numeric(normalized.get("fpts"), errors="coerce")
        normalized["pct_drafted"] = normalized["pct_drafted"].map(self._parse_percent)
        normalized["entry_id"] = normalized["entry_id"].astype(str)
        normalized["player_display_name"] = normalized["player_display_name"].where(
            normalized["player_display_name"].notna(), None
        )
        normalized["roster_position"] = normalized["roster_position"].where(normalized["roster_position"].notna(), None)
        normalized["lineup_text"] = normalized.get("lineup_text", pd.Series("", index=normalized.index)).fillna("")
        return normalized

    @staticmethod
    def _parse_percent(value: object) -> float | None:
        if pd.isna(value):
            return None
        text_value = str(value).strip().replace("%", "")
        if not text_value:
            return None
        return float(pd.to_numeric(text_value, errors="coerce"))

    def _attach_player_ids(self, rows: pd.DataFrame) -> pd.DataFrame:
        resolver = PlayerMasterResolver(connection_string=self.connection_string)
        attached = resolver.attach_to_dataframe(rows, name_col="player_display_name", pos_col="roster_position")
        attached["player_id"] = attached["player_master_id"].astype(str)
        return attached

    @staticmethod
    def _ownership_source_rows(standings: pd.DataFrame) -> pd.DataFrame:
        if standings.empty or "player_display_name" not in standings.columns:
            return pd.DataFrame()
        rows = standings[
            standings["player_display_name"].notna()
            & standings["pct_drafted"].notna()
            & standings["player_display_name"].astype(str).str.strip().ne("")
        ].copy()
        rows["player_display_name"] = rows["player_display_name"].astype(str).str.strip()
        rows["roster_position"] = rows["roster_position"].fillna("").astype(str).str.strip()
        return rows

    @staticmethod
    def _build_entries(rows: pd.DataFrame) -> pd.DataFrame:
        entry_cols = [
            "season",
            "week",
            "slate",
            "contest_id",
            "source_file_id",
            "entry_id",
            "entry_name",
            "rank",
            "entry_points",
            "lineup_text",
            "source_file",
            "ingested_at",
        ]
        available = [col for col in entry_cols if col in rows.columns]
        return rows[available].drop_duplicates(subset=["season", "week", "slate", "entry_id"])

    @staticmethod
    def _mode_text(series: pd.Series) -> str | None:
        clean = series.dropna().astype(str)
        if clean.empty:
            return None
        return str(clean.mode().iloc[0])

    def _build_ownership(self, rows: pd.DataFrame) -> pd.DataFrame:
        if rows.empty:
            return pd.DataFrame()
        rows = rows.copy()
        for column in ("contest_id", "source_file_id"):
            if column not in rows.columns:
                rows[column] = None
        grouped = (
            rows.groupby(
                [
                    "season",
                    "week",
                    "slate",
                    "contest_id",
                    "source_file_id",
                    "player_id",
                    "player_master_id",
                    "player_display_name",
                ],
                dropna=False,
            )
            .agg(
                roster_position=("roster_position", self._mode_text),
                projected_ownership=("pct_drafted", "max"),
                actual_ownership=("pct_drafted", "max"),
                rows_seen=("entry_id", "size"),
                entries_seen=("entry_id", "nunique"),
            )
            .reset_index()
        )
        grouped["source"] = "contest_standings"
        grouped["updated_at"] = _utcnow()
        return grouped

    @classmethod
    def _lineup_player_rows(cls, top_rows: pd.DataFrame, all_standings: pd.DataFrame) -> pd.DataFrame:
        ownership_lookup = cls._ownership_lookup(all_standings)
        parsed_rows: list[dict] = []
        for row in top_rows.to_dict(orient="records"):
            parsed_players = cls._parse_lineup(row.get("lineup_text"))
            if not parsed_players and row.get("player_display_name"):
                parsed_players = [
                    {
                        "roster_position": row.get("roster_position") or "",
                        "player_display_name": row.get("player_display_name"),
                    }
                ]
            for player in parsed_players:
                player_name = str(player["player_display_name"]).strip()
                own = ownership_lookup.get(cls._norm_player_name(player_name))
                parsed_rows.append(
                    {
                        "entry_id": row.get("entry_id"),
                        "rank": row.get("rank"),
                        "entry_points": row.get("entry_points"),
                        "player_display_name": player_name,
                        "roster_position": player.get("roster_position") or "",
                        "pct_drafted": own,
                        "player_name_norm": cls._norm_player_name(player_name),
                    }
                )
        return pd.DataFrame(parsed_rows)

    @staticmethod
    def _ownership_lookup(standings: pd.DataFrame) -> dict[str, float]:
        source = OwnershipService._ownership_source_rows(standings)
        if source.empty:
            return {}
        source["name_norm"] = source["player_display_name"].map(OwnershipService._norm_player_name)
        return source.groupby("name_norm")["pct_drafted"].max().dropna().to_dict()

    @staticmethod
    def _norm_player_name(name: object) -> str:
        return " ".join(str(name or "").lower().replace("'", " ").split())

    @staticmethod
    def _parse_lineup(lineup_text: object) -> list[dict]:
        text_value = str(lineup_text or "").strip()
        if not text_value or text_value.lower() == "nan":
            return []
        slots = "CPT|DST|FLEX|QB|RB|WR|TE"
        pattern = re.compile(rf"\b({slots})\s+(.+?)(?=\s+(?:{slots})\s+|$)")
        players = []
        for match in pattern.finditer(text_value):
            players.append(
                {
                    "roster_position": match.group(1),
                    "player_display_name": match.group(2).strip(),
                }
            )
        return players

    def _append_table(self, table_name: str, df: pd.DataFrame) -> None:
        if df.empty:
            return
        ensure_table_columns(self.engine, table_name, df)
        df.to_sql(table_name, self.engine, if_exists="append", index=False)

    @staticmethod
    def _delete_scope(conn, table_name: str, season: int, week: int, slate: str) -> None:
        conn.execute(
            text(f"DELETE FROM {table_name} WHERE season = :season AND week = :week AND slate = :slate"),
            {"season": season, "week": week, "slate": slate},
        )

    @staticmethod
    def _delete_contest(conn, table_name: str, contest_id: str) -> None:
        conn.execute(
            text(f"DELETE FROM {table_name} WHERE contest_id = :contest_id"),
            {"contest_id": contest_id},
        )

    @staticmethod
    def _top_entries(rows: pd.DataFrame, top_n: int) -> pd.DataFrame:
        entries = rows[["entry_id", "rank", "entry_points"]].drop_duplicates("entry_id")
        return entries.sort_values(["rank", "entry_points"], ascending=[True, False]).head(top_n)

    def _load_salary_lookup(self, season: int, week: int, slate: str) -> pd.DataFrame:
        if not inspect(self.engine).has_table("dk_salaries"):
            return pd.DataFrame(columns=["player_id", "salary"])
        with self.engine.begin() as conn:
            salaries = pd.read_sql(
                text(
                    "SELECT player_id, player_master_id, name, player_name, salary "
                    "FROM dk_salaries WHERE season = :season AND week = :week AND slate = :slate"
                ),
                conn,
                params={"season": season, "week": week, "slate": slate},
            )
        if salaries.empty:
            return pd.DataFrame(columns=["player_id", "player_name_norm", "salary"])
        salaries["player_id"] = salaries.get("player_master_id", salaries["player_id"]).fillna(salaries["player_id"]).astype(str)
        salaries["salary"] = pd.to_numeric(salaries["salary"], errors="coerce").fillna(0)
        name_series = salaries.get("name", salaries.get("player_name", pd.Series("", index=salaries.index)))
        salaries["player_name_norm"] = name_series.map(self._norm_player_name)
        return salaries[["player_id", "player_name_norm", "salary"]].drop_duplicates("player_name_norm")

    def _lineup_stats(self, rows: pd.DataFrame, season: int, week: int, slate: str) -> pd.DataFrame:
        if rows.empty:
            return pd.DataFrame(
                columns=[
                    "entry_id",
                    "rank",
                    "final_points",
                    "players",
                    "total_own_sum",
                    "avg_own",
                    "num_chalk",
                    "num_low_owned",
                    "salary_used",
                    "num_sub_4k",
                    "salary_left",
                    "qb_stack_type",
                    "bring_back_count",
                    "notes",
                ]
            )
        salary_lookup = self._load_salary_lookup(season, week, slate)
        rows_for_stats = (
            rows.merge(salary_lookup[["player_name_norm", "salary"]], on="player_name_norm", how="left")
            if not salary_lookup.empty and "player_name_norm" in rows.columns
            else rows.copy()
        )
        if "salary" not in rows_for_stats.columns:
            rows_for_stats["salary"] = 0
        grouped = (
            rows_for_stats.groupby("entry_id")
            .agg(
                rank=("rank", "min"),
                final_points=("entry_points", "max"),
                players=("player_display_name", lambda s: ", ".join(s.astype(str).tolist())),
                total_own_sum=("pct_drafted", "sum"),
                avg_own=("pct_drafted", "mean"),
                num_chalk=("pct_drafted", lambda s: int((s >= 20).sum())),
                num_low_owned=("pct_drafted", lambda s: int((s <= 5).sum())),
                salary_used=("salary", "sum"),
                num_sub_4k=("salary", lambda s: int(((s > 0) & (s < 4000)).sum())),
            )
            .reset_index()
            .sort_values("rank")
        )
        grouped["salary_left"] = (50000 - grouped["salary_used"]).clip(lower=0)
        grouped["qb_stack_type"] = "not_scored"
        grouped["bring_back_count"] = 0
        grouped["notes"] = "ownership/salary summary; stack scoring pending team correlation data"
        return grouped

    @staticmethod
    def _bucket_stats(lineup_stats: pd.DataFrame) -> list[dict]:
        if lineup_stats.empty:
            return []
        buckets = [("top_1_percent", 0.01), ("top_5_percent", 0.05), ("top_20_percent", 0.20), ("all_analyzed", 1.0)]
        payload = []
        total = len(lineup_stats)
        for bucket, pct in buckets:
            size = max(1, int(round(total * pct))) if pct < 1 else total
            subset = lineup_stats.head(size)
            payload.append(
                {
                    "bucket": bucket,
                    "lineups": int(len(subset)),
                    "avg_actual_own_sum": round(float(subset["total_own_sum"].mean()), 2),
                    "median_actual_own_sum": round(float(subset["total_own_sum"].median()), 2),
                    "avg_num_chalk": round(float(subset["num_chalk"].mean()), 2),
                    "avg_num_low_owned": round(float(subset["num_low_owned"].mean()), 2),
                    "avg_total_salary": round(float(subset["salary_used"].mean()), 2),
                    "avg_num_sub_4k": round(float(subset["num_sub_4k"].mean()), 2),
                }
            )
        return payload

    @staticmethod
    def _top_lineups_payload(lineup_stats: pd.DataFrame) -> list[dict]:
        fields = [
            "rank",
            "final_points",
            "entry_id",
            "salary_used",
            "salary_left",
            "players",
            "total_own_sum",
            "avg_own",
            "num_chalk",
            "num_low_owned",
            "num_sub_4k",
            "qb_stack_type",
            "bring_back_count",
            "notes",
        ]
        return lineup_stats[fields].head(25).to_dict(orient="records")
