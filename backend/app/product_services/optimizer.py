"""Lineup optimizer using PuLP ILP."""

from __future__ import annotations

import uuid
import math
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional
import logging

import pandas as pd
import numpy as np
import pulp
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import ProgrammingError, ResourceClosedError

from Database.config import get_connection_string
from Database.operations import ensure_table_columns
from .gpp_optimizer import run_gpp_pipeline, Player as GPPPlayer, GPPOptimizerResult
from .simulations import SimulationService
from .target_schema import validate_target_schema


VALID_CONTEST_FORMATS = {"classic", "showdown"}
VALID_OPTIMIZER_OBJECTIVES = {"cash", "gpp"}
CASH_OBJECTIVE_ID = "classic_cash_v1"
CLASSIC_CASH_STACK_UNCONSTRAINED_ID = "classic_cash_unconstrained_v1"
CLASSIC_CASH_STACK_QB_PAIR_ID = "classic_cash_qb_pair_v1"
CLASSIC_CASH_STACK_QB_PAIR_BRINGBACK_ID = "classic_cash_qb_pair_bringback_v1"
CLASSIC_GPP_STACK_LEGACY_ID = "classic_gpp_double_bringback_v1"


@dataclass(frozen=True)
class CashObjectiveConfig:
    objective_id: str = CASH_OBJECTIVE_ID
    mean_weight: float = 0.25
    median_weight: float = 0.35
    floor_weight: float = 0.40
    role_certainty_bonus: float = 1.25
    fragility_penalty: float = 3.0
    full_role_sample_size: int = 250


DEFAULT_CASH_OBJECTIVE = CashObjectiveConfig()


@dataclass(frozen=True)
class StackPolicyConfig:
    policy_id: str
    contest_format: str
    objective: str
    enabled: bool
    stack_min: int
    stack_max: int | None
    bringback: bool
    include_rb_in_stack: bool = False
    bringback_positions: tuple[str, ...] = ("WR", "TE")
    evidence_status: str = "candidate_unvalidated"
    description: str = ""


STACKING_POLICIES = {
    CLASSIC_CASH_STACK_UNCONSTRAINED_ID: StackPolicyConfig(
        policy_id=CLASSIC_CASH_STACK_UNCONSTRAINED_ID,
        contest_format="classic",
        objective="cash",
        enabled=False,
        stack_min=0,
        stack_max=None,
        bringback=False,
        evidence_status="replay_baseline",
        description="No QB pairing or opponent bring-back constraint.",
    ),
    CLASSIC_CASH_STACK_QB_PAIR_ID: StackPolicyConfig(
        policy_id=CLASSIC_CASH_STACK_QB_PAIR_ID,
        contest_format="classic",
        objective="cash",
        enabled=True,
        stack_min=1,
        stack_max=None,
        bringback=False,
        description="Require at least one same-team QB pass catcher.",
    ),
    CLASSIC_CASH_STACK_QB_PAIR_BRINGBACK_ID: StackPolicyConfig(
        policy_id=CLASSIC_CASH_STACK_QB_PAIR_BRINGBACK_ID,
        contest_format="classic",
        objective="cash",
        enabled=True,
        stack_min=1,
        stack_max=None,
        bringback=True,
        description="Require a QB pass catcher and one opposing WR/TE bring-back.",
    ),
    CLASSIC_GPP_STACK_LEGACY_ID: StackPolicyConfig(
        policy_id=CLASSIC_GPP_STACK_LEGACY_ID,
        contest_format="classic",
        objective="gpp",
        enabled=True,
        stack_min=2,
        stack_max=None,
        bringback=True,
        evidence_status="legacy_default",
        description="Preserve the current classic GPP double-stack and bring-back contract.",
    ),
}


def stacking_policy_config(config: StackPolicyConfig) -> dict:
    """Return a JSON-safe, versioned stacking policy configuration."""
    return {
        "policy_id": config.policy_id,
        "contest_format": config.contest_format,
        "objective": config.objective,
        "enabled": config.enabled,
        "stack_min": config.stack_min,
        "stack_max": config.stack_max,
        "bringback": config.bringback,
        "include_rb_in_stack": config.include_rb_in_stack,
        "bringback_positions": list(config.bringback_positions),
        "evidence_status": config.evidence_status,
        "description": config.description,
        "source": "registry",
    }


def resolve_stacking_policy(
    *,
    contest_format: str,
    objective: str,
    params: dict | None = None,
) -> dict:
    """Resolve a versioned policy while retaining explicit legacy overrides."""
    values = params or {}
    if contest_format != "classic":
        return {
            "policy_id": "showdown_classic_stack_not_applicable_v1",
            "contest_format": contest_format,
            "objective": objective,
            "enabled": False,
            "stack_min": 0,
            "stack_max": None,
            "bringback": False,
            "include_rb_in_stack": False,
            "bringback_positions": [],
            "evidence_status": "not_applicable",
            "description": "Classic QB stacking policies do not apply to showdown.",
            "source": "format_contract",
        }

    requested_policy_id = str(values.get("stack_policy_id") or "").strip()
    legacy_fields = {
        field
        for field in (
            "stack_min",
            "stack_max",
            "bringback",
            "include_rb_in_stack",
            "bringback_positions",
        )
        if field in values
    }
    if requested_policy_id and legacy_fields:
        raise ValueError(
            "stack_policy_id cannot be combined with legacy stack overrides: "
            + ", ".join(sorted(legacy_fields))
        )

    if requested_policy_id:
        policy = STACKING_POLICIES.get(requested_policy_id)
        if policy is None:
            raise ValueError(
                "stack_policy_id must be one of: "
                + ", ".join(sorted(STACKING_POLICIES))
            )
        if policy.contest_format != contest_format or policy.objective != objective:
            raise ValueError(
                f"stack_policy_id {requested_policy_id} is not valid for "
                f"{contest_format} {objective}"
            )
        resolved = stacking_policy_config(policy)
        resolved["source"] = "explicit"
        return resolved

    if not legacy_fields:
        default_policy_id = (
            CLASSIC_CASH_STACK_UNCONSTRAINED_ID
            if objective == "cash"
            else CLASSIC_GPP_STACK_LEGACY_ID
        )
        resolved = stacking_policy_config(STACKING_POLICIES[default_policy_id])
        resolved["source"] = "default"
        return resolved

    legacy_base_id = (
        CLASSIC_CASH_STACK_QB_PAIR_BRINGBACK_ID
        if objective == "cash"
        else CLASSIC_GPP_STACK_LEGACY_ID
    )
    resolved = stacking_policy_config(STACKING_POLICIES[legacy_base_id])
    resolved.update(
        {
            "policy_id": f"classic_{objective}_custom_v1",
            "base_policy_id": legacy_base_id,
            "evidence_status": "legacy_override_unvalidated",
            "source": "legacy_params",
        }
    )
    if "stack_min" in values:
        resolved["stack_min"] = int(values["stack_min"])
    if resolved["stack_min"] < 0:
        raise ValueError("stack_min must be at least 0")
    if "stack_max" in values:
        raw_stack_max = values["stack_max"]
        resolved["stack_max"] = (
            None if raw_stack_max in (None, "", False) else int(raw_stack_max)
        )
    if resolved["stack_max"] is not None and resolved["stack_max"] < resolved["stack_min"]:
        raise ValueError("stack_max must be greater than or equal to stack_min")
    if "bringback" in values:
        resolved["bringback"] = bool(values["bringback"])
    if "include_rb_in_stack" in values:
        resolved["include_rb_in_stack"] = bool(values["include_rb_in_stack"])
    if "bringback_positions" in values:
        raw_positions = values["bringback_positions"]
        if raw_positions is None:
            raw_positions = []
        if isinstance(raw_positions, str):
            raw_positions = [raw_positions]
        resolved["bringback_positions"] = sorted(
            {str(position).strip().upper() for position in raw_positions if str(position).strip()}
        )
    resolved["enabled"] = bool(
        resolved["stack_min"] > 0
        or resolved["stack_max"] is not None
        or resolved["bringback"]
    )
    return resolved


def cash_objective_config(config: CashObjectiveConfig = DEFAULT_CASH_OBJECTIVE) -> dict:
    """Return the exact versioned configuration persisted with classic cash runs."""
    return {
        "objective_id": config.objective_id,
        "mean_weight": config.mean_weight,
        "median_weight": config.median_weight,
        "floor_weight": config.floor_weight,
        "role_certainty_bonus": config.role_certainty_bonus,
        "fragility_penalty": config.fragility_penalty,
        "full_role_sample_size": config.full_role_sample_size,
    }


def build_classic_cash_objective(
    pool: pd.DataFrame,
    config: CashObjectiveConfig = DEFAULT_CASH_OBJECTIVE,
) -> pd.DataFrame:
    """Add explainable cash-stability terms while preserving projection-only fallback."""
    if pool.empty:
        return pool.copy()
    frame = pool.copy()
    mean_source = frame["projection"] if "projection" in frame.columns else pd.Series(0.0, index=frame.index)
    mean = pd.to_numeric(mean_source, errors="coerce").fillna(0.0)
    median_source = frame["predicted_p50"] if "predicted_p50" in frame.columns else mean
    floor_source = frame["predicted_p10"] if "predicted_p10" in frame.columns else mean
    median_observed = (
        pd.to_numeric(frame["predicted_p50"], errors="coerce").notna()
        if "predicted_p50" in frame.columns
        else pd.Series(False, index=frame.index)
    )
    floor_observed = (
        pd.to_numeric(frame["predicted_p10"], errors="coerce").notna()
        if "predicted_p10" in frame.columns
        else pd.Series(False, index=frame.index)
    )
    median = pd.to_numeric(median_source, errors="coerce").fillna(mean)
    floor = pd.to_numeric(floor_source, errors="coerce").fillna(median)
    sample_source = frame["calibration_sample_size"] if "calibration_sample_size" in frame.columns else pd.Series(0.0, index=frame.index)
    sample_size = pd.to_numeric(sample_source, errors="coerce").fillna(0.0).clip(lower=0.0)
    role_source = frame["calibration_role"] if "calibration_role" in frame.columns else pd.Series("", index=frame.index)
    known_role = ~role_source.fillna("").astype(str).str.lower().isin({"", "unknown", "global", "fallback"})
    role_certainty = (sample_size / float(config.full_role_sample_size)).clip(upper=1.0)
    role_certainty = role_certainty * np.where(known_role, 1.0, 0.5)
    downside_gap = (median - floor).clip(lower=0.0)
    fragility = (downside_gap / median.abs().clip(lower=1.0)).clip(upper=2.0)

    frame["cash_objective_id"] = config.objective_id
    frame["cash_evidence_status"] = np.select(
        [mean <= 0.0, median_observed & floor_observed],
        ["missing_projection", "calibrated_distribution"],
        default="projection_only",
    )
    frame["cash_mean"] = mean
    frame["cash_median"] = median
    frame["cash_floor"] = floor
    frame["cash_role_certainty"] = role_certainty.astype(float)
    frame["cash_fragility"] = fragility.astype(float)
    frame["cash_mean_component"] = mean * config.mean_weight
    frame["cash_median_component"] = median * config.median_weight
    frame["cash_floor_component"] = floor * config.floor_weight
    frame["cash_role_bonus"] = frame["cash_role_certainty"] * config.role_certainty_bonus
    frame["cash_fragility_penalty"] = frame["cash_fragility"] * config.fragility_penalty
    frame["cash_score"] = (
        frame["cash_mean_component"]
        + frame["cash_median_component"]
        + frame["cash_floor_component"]
        + frame["cash_role_bonus"]
        - frame["cash_fragility_penalty"]
    )
    frame["cash_objective_explanation"] = frame.apply(
        lambda row: {
            "objective_id": config.objective_id,
            "evidence_status": str(row["cash_evidence_status"]),
            "mean": float(row["cash_mean"]),
            "median": float(row["cash_median"]),
            "floor_p10": float(row["cash_floor"]),
            "role_certainty": float(row["cash_role_certainty"]),
            "fragility": float(row["cash_fragility"]),
            "mean_component": float(row["cash_mean_component"]),
            "median_component": float(row["cash_median_component"]),
            "floor_component": float(row["cash_floor_component"]),
            "role_bonus": float(row["cash_role_bonus"]),
            "fragility_penalty": float(row["cash_fragility_penalty"]),
            "cash_score": float(row["cash_score"]),
        },
        axis=1,
    )
    return frame


def summarize_classic_cash_lineup(lineup: list[dict]) -> dict:
    """Aggregate player-level cash terms into an inspectable lineup explanation."""
    if not lineup:
        return {}
    missing_projection_players = [
        {
            "player_id": str(row.get("player_id") or ""),
            "name": str(row.get("name") or row.get("player_name") or ""),
            "position": str(row.get("position") or row.get("roster_position") or ""),
        }
        for row in lineup
        if row.get("cash_evidence_status") == "missing_projection"
        or _safe_float(row.get("cash_mean", row.get("projection"))) <= 0.0
    ]
    return {
        "objective_id": CASH_OBJECTIVE_ID,
        "player_count": len(lineup),
        "projected_mean": sum(_safe_float(row.get("cash_mean", row.get("projection"))) for row in lineup),
        "projected_median": sum(_safe_float(row.get("cash_median", row.get("predicted_p50", row.get("projection")))) for row in lineup),
        "projected_floor_p10": sum(_safe_float(row.get("cash_floor", row.get("predicted_p10", row.get("projection")))) for row in lineup),
        "objective_score": sum(_safe_float(row.get("cash_score", row.get("projection"))) for row in lineup),
        "average_role_certainty": sum(_safe_float(row.get("cash_role_certainty")) for row in lineup) / len(lineup),
        "total_fragility_penalty": sum(_safe_float(row.get("cash_fragility_penalty")) for row in lineup),
        "evidence_complete": not missing_projection_players,
        "missing_projection_players": missing_projection_players,
    }


def resolve_optimizer_mode(
    *,
    contest_format: str | None,
    objective: str | None,
    params: dict | None = None,
) -> tuple[str, str, str]:
    """Resolve the explicit format/objective contract and legacy solver mode."""
    legacy_type = str((params or {}).get("contest_type", "")).strip().lower()

    if contest_format is None:
        contest_format = "showdown" if legacy_type == "captain" else "classic"
    if objective is None:
        objective = "cash" if legacy_type == "cash" else "gpp"

    normalized_format = str(contest_format).strip().lower()
    normalized_objective = str(objective).strip().lower()
    if normalized_format not in VALID_CONTEST_FORMATS:
        raise ValueError(
            f"contest_format must be one of: {', '.join(sorted(VALID_CONTEST_FORMATS))}"
        )
    if normalized_objective not in VALID_OPTIMIZER_OBJECTIVES:
        raise ValueError(
            f"objective must be one of: {', '.join(sorted(VALID_OPTIMIZER_OBJECTIVES))}"
        )

    if normalized_format == "showdown":
        solver_mode = "captain"
    elif normalized_objective == "cash":
        solver_mode = "cash"
    else:
        solver_mode = "tournament"
    return normalized_format, normalized_objective, solver_mode


@dataclass
class OptimizerJob:
    job_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    season: int
    week: int
    slate: str
    strategy: str
    contest_format: str
    objective: str
    params: dict
    projection_run_id: str | None = None
    rule_run_id: str | None = None
    data_cutoff_at: datetime | None = None
    lineage_persisted: bool = False
    results: Optional[list] = None
    message: Optional[str] = None


SALARY_CAP = 50000
TEAM_LIMIT = 4
MIN_SALARY = 2000
logger = logging.getLogger(__name__)


def _json_safe(value):
    """Convert dataframe/numpy values into strict JSON-compatible values."""
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
    """Normalize optional dataframe scalars for persisted lineup summaries."""
    try:
        if value is None or pd.isna(value):
            return 0.0
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _merge_simulation_evidence(
    pool: pd.DataFrame,
    simulation_rows: List[dict],
) -> pd.DataFrame:
    """Merge DT-502 evidence without discarding existing ownership coverage."""
    simulation_frame = pd.DataFrame(simulation_rows).rename(
        columns={"field_ownership": "simulation_field_ownership"}
    )
    evidence_columns = (
        "optimal_lineup_probability",
        "simulation_field_ownership",
        "leverage_score",
    )
    for column in evidence_columns:
        if column not in simulation_frame.columns:
            simulation_frame[column] = np.nan
    merged = pool.copy()
    merged["player_id"] = merged["player_id"].astype(str)
    if simulation_frame.empty:
        for column in evidence_columns:
            merged[column] = np.nan
    else:
        simulation_frame["player_id"] = simulation_frame["player_id"].astype(str)
        merged = merged.merge(
            simulation_frame[["player_id", *evidence_columns]],
            on="player_id",
            how="left",
        )
    existing_ownership = (
        pd.to_numeric(merged["ownership"], errors="coerce")
        if "ownership" in merged.columns
        else pd.Series(np.nan, index=merged.index, dtype=float)
    )
    simulation_ownership = pd.to_numeric(
        merged["simulation_field_ownership"], errors="coerce"
    )
    merged["ownership"] = simulation_ownership.combine_first(existing_ownership)
    merged["leverage"] = pd.to_numeric(merged["leverage_score"], errors="coerce")
    return merged


def _normalize_alias(name: str) -> str:
    """Map common aliases to canonical forms (e.g., Hollywood Brown -> Marquise Brown)."""
    key = " ".join(name.lower().replace("'", " ").split())
    if "hollywood brown" in key or ("hollywood" in key and "brown" in key):
        return "marquise brown"
    if key == "marquise brown":
        return "marquise brown"
    return key


def _log_pool_stats(df: pd.DataFrame, label: str) -> None:
    """Debug helper: print projection/ceiling diagnostics."""
    if df.empty:
        print(f"[pool:{label}] empty")
        return
    if "position" not in df.columns:
        print(f"[pool:{label}] missing position column; cols={list(df.columns)}")
        return

    def _stats(series: pd.Series) -> tuple[float, float, float]:
        series = pd.to_numeric(series, errors="coerce")
        return (float(series.min()), float(series.median()), float(series.max()))

    proj_min, proj_med, proj_max = _stats(df.get("projection", pd.Series()))
    p90_min, p90_med, p90_max = _stats(df.get("p90", pd.Series()))
    print(f"[pool:{label}] rows={len(df)} proj min/med/max={proj_min:.2f}/{proj_med:.2f}/{proj_max:.2f} "
          f"p90 min/med/max={p90_min:.2f}/{p90_med:.2f}/{p90_max:.2f}")
    for pos, group in df.groupby("position"):
        g_proj_min, g_proj_med, g_proj_max = _stats(group.get("projection", pd.Series()))
        g_p90_min, g_p90_med, g_p90_max = _stats(group.get("p90", pd.Series()))
        print(f"[pool:{label}] {pos} count={len(group)} proj {g_proj_min:.2f}/{g_proj_med:.2f}/{g_proj_max:.2f} "
              f"p90 {g_p90_min:.2f}/{g_p90_med:.2f}/{g_p90_max:.2f}")
    proj_nan = df["projection"].isna().sum() if "projection" in df else 0
    p90_nan = df["p90"].isna().sum() if "p90" in df else 0
    proj_zero = (df["projection"] == 0).sum() if "projection" in df else 0
    p90_zero = (df["p90"] == 0).sum() if "p90" in df else 0
    print(f"[pool:{label}] NaNs proj={proj_nan} p90={p90_nan} zeros proj={proj_zero} p90={p90_zero}")
    cols = ["name", "position", "player_team", "salary", "projection", "p90"]
    top_proj = df.sort_values("projection", ascending=False).head(10)[cols] if "projection" in df else pd.DataFrame()
    top_p90 = df.sort_values("p90", ascending=False).head(10)[cols] if "p90" in df else pd.DataFrame()
    print(f"[pool:{label}] top proj:\n{top_proj.to_string(index=False)}")
    print(f"[pool:{label}] top p90:\n{top_p90.to_string(index=False)}")


class OptimizerService:
    """ILP-based optimizer that maximizes projected points under DK constraints."""

    def __init__(self, connection_string: str | None = None) -> None:
        self._jobs: Dict[str, OptimizerJob] = {}
        self.connection_string = connection_string or get_connection_string()
        self.engine = create_engine(self.connection_string)

    def _resolve_run_lineage(
        self,
        *,
        season: int,
        week: int,
        slate: str,
        projection_run_id: str | None,
        rule_run_id: str | None,
        data_cutoff_at: datetime | None,
    ) -> tuple[str | None, str | None, datetime | None]:
        """Best-effort lookup of the active projection and symbolic run IDs."""
        try:
            with self.engine.begin() as connection:
                if projection_run_id is None or data_cutoff_at is None:
                    projection_query = (
                        "SELECT p.projection_run_id, p.data_cutoff_at "
                        "FROM target.player_projection p "
                        "WHERE p.season = :season AND p.week = :week "
                        "AND (p.slate_id = :slate OR p.slate_id IS NULL) "
                    )
                    projection_params = {
                        "season": season,
                        "week": week,
                        "slate": slate,
                    }
                    if projection_run_id is not None:
                        projection_query += "AND p.projection_run_id = :projection_run_id "
                        projection_params["projection_run_id"] = projection_run_id
                    else:
                        projection_query += (
                            "AND p.projection_run_id = COALESCE(("
                            "SELECT active.projection_run_id "
                            "FROM target.active_projection_run active "
                            "WHERE active.season = :season AND active.week = :week "
                            "AND (UPPER(active.slate_id) = UPPER(:slate) "
                            "OR active.slate_id = 'DEFAULT') "
                            "ORDER BY CASE WHEN UPPER(active.slate_id) = UPPER(:slate) "
                            "THEN 0 ELSE 1 END, active.selected_at DESC LIMIT 1"
                            "), p.projection_run_id) "
                        )
                    projection_query += "ORDER BY created_at DESC LIMIT 1"
                    projection_row = connection.execute(
                        text(projection_query),
                        projection_params,
                    ).mappings().first()
                    if projection_row:
                        projection_run_id = str(projection_row["projection_run_id"])
                        data_cutoff_at = data_cutoff_at or projection_row.get("data_cutoff_at")

                if rule_run_id is None:
                    rule_query = (
                        "SELECT rule_run_id FROM target.symbolic_adjusted_projection "
                        "WHERE season = :season AND week = :week "
                        "AND (slate_id = :slate OR slate_id IS NULL) "
                    )
                    rule_params = {"season": season, "week": week, "slate": slate}
                    if projection_run_id is not None:
                        rule_query += "AND projection_run_id = :projection_run_id "
                        rule_params["projection_run_id"] = projection_run_id
                    rule_query += "ORDER BY created_at DESC LIMIT 1"
                    rule_row = connection.execute(
                        text(rule_query),
                        rule_params,
                    ).mappings().first()
                    if rule_row:
                        rule_run_id = str(rule_row["rule_run_id"])
        except Exception as exc:  # noqa: BLE001 - legacy databases may not have target lineage tables yet
            logger.info("Optimizer lineage lookup unavailable: %s", exc)
        return projection_run_id, rule_run_id, data_cutoff_at

    def _persist_optimizer_run(self, job: OptimizerJob) -> bool:
        """Persist one optimizer execution even when it produced no lineups."""
        validate_target_schema(
            self.engine,
            consumer=type(self).__name__,
            required_tables=(
                "optimizer_run",
                "lineup",
                "lineup_player",
                "lineup_constraint_explanation",
            ),
        )
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO target.optimizer_run
                            (optimizer_run_id, projection_run_id, rule_run_id, slate_id,
                             season, week, contest_format, objective, strategy,
                             objective_config_json, constraint_config_json, data_cutoff_at,
                             created_at, updated_at, status, message)
                        VALUES
                            (:optimizer_run_id, :projection_run_id, :rule_run_id, :slate_id,
                             :season, :week, :contest_format, :objective, :strategy,
                             CAST(:objective_config_json AS JSONB), CAST(:constraint_config_json AS JSONB),
                             :data_cutoff_at, :created_at, :updated_at, :status, :message)
                        ON CONFLICT (optimizer_run_id) DO UPDATE SET
                            updated_at = EXCLUDED.updated_at,
                            status = EXCLUDED.status,
                            message = EXCLUDED.message,
                            objective_config_json = EXCLUDED.objective_config_json,
                            constraint_config_json = EXCLUDED.constraint_config_json
                        """
                    ),
                    {
                        "optimizer_run_id": job.job_id,
                        "projection_run_id": job.projection_run_id,
                        "rule_run_id": job.rule_run_id,
                        "slate_id": job.slate,
                        "season": job.season,
                        "week": job.week,
                        "contest_format": job.contest_format,
                        "objective": job.objective,
                        "strategy": job.strategy,
                        "objective_config_json": json.dumps(
                            {
                                "objective": job.objective,
                                "strategy": job.strategy,
                                **(
                                    job.params.get("objective_config", {})
                                    if isinstance(job.params.get("objective_config"), dict)
                                    else {}
                                ),
                            },
                            sort_keys=True,
                        ),
                        "constraint_config_json": json.dumps(job.params, sort_keys=True, default=str),
                        "data_cutoff_at": job.data_cutoff_at,
                        "created_at": job.created_at,
                        "updated_at": job.updated_at,
                        "status": job.status,
                        "message": job.message,
                    },
                )
                connection.execute(
                    text(
                        "DELETE FROM target.lineup WHERE optimizer_run_id = :optimizer_run_id"
                    ),
                    {"optimizer_run_id": job.job_id},
                )
                for lineup_number, lineup in enumerate(job.results or [], start=1):
                    lineup_id = f"{job.job_id}:{lineup_number}"
                    cash_summary = (
                        summarize_classic_cash_lineup(lineup)
                        if job.contest_format == "classic" and job.objective == "cash"
                        else {}
                    )
                    salary_used = sum(_safe_float(row.get("salary")) for row in lineup)
                    projected_mean = sum(
                        _safe_float(row.get("projection", row.get("predicted_mean")))
                        for row in lineup
                    )
                    projected_p90 = sum(
                        _safe_float(row.get("p90", row.get("predicted_p90")))
                        for row in lineup
                    )
                    ownership_sum = sum(
                        _safe_float(row.get("ownership", row.get("projected_ownership")))
                        for row in lineup
                    )
                    leverage_score = sum(_safe_float(row.get("leverage")) for row in lineup)
                    connection.execute(
                        text(
                            """
                            INSERT INTO target.lineup
                                (lineup_id, optimizer_run_id, lineup_number, salary_used,
                                 projected_mean, projected_median, projected_floor, projected_p90,
                                 objective_score, average_role_certainty, fragility_penalty,
                                 ownership_sum, leverage_score, created_at)
                            VALUES
                                (:lineup_id, :optimizer_run_id, :lineup_number, :salary_used,
                                 :projected_mean, :projected_median, :projected_floor, :projected_p90,
                                 :objective_score, :average_role_certainty, :fragility_penalty,
                                 :ownership_sum, :leverage_score, :created_at)
                            """
                        ),
                        {
                            "lineup_id": lineup_id,
                            "optimizer_run_id": job.job_id,
                            "lineup_number": lineup_number,
                            "salary_used": salary_used,
                            "projected_mean": projected_mean,
                            "projected_median": cash_summary.get("projected_median"),
                            "projected_floor": cash_summary.get("projected_floor_p10"),
                            "projected_p90": projected_p90,
                            "objective_score": cash_summary.get("objective_score"),
                            "average_role_certainty": cash_summary.get("average_role_certainty"),
                            "fragility_penalty": cash_summary.get("total_fragility_penalty"),
                            "ownership_sum": ownership_sum,
                            "leverage_score": leverage_score,
                            "created_at": job.created_at,
                        },
                    )
                    player_rows = []
                    for slot_index, row in enumerate(lineup):
                        player_rows.append(
                            {
                                "lineup_id": lineup_id,
                                "slot_index": slot_index,
                                "player_id": str(row.get("player_id") or row.get("dk_player_id") or ""),
                                "roster_position": str(
                                    row.get("roster_position") or row.get("position") or ""
                                ),
                                "salary": _safe_float(row.get("salary")),
                                "projection": _safe_float(
                                    row.get("projection", row.get("predicted_mean"))
                                ),
                                "projected_p90": _safe_float(
                                    row.get("p90", row.get("predicted_p90"))
                                ),
                                "ownership_projection": _safe_float(
                                    row.get("ownership", row.get("projected_ownership"))
                                ),
                                "player_json": json.dumps(
                                    _json_safe(row), sort_keys=True, allow_nan=False
                                ),
                            }
                        )
                    if player_rows:
                        connection.execute(
                            text(
                                """
                                INSERT INTO target.lineup_player
                                    (lineup_id, slot_index, player_id, roster_position, salary,
                                     projection, projected_p90, ownership_projection, player_json)
                                VALUES
                                    (:lineup_id, :slot_index, :player_id, :roster_position, :salary,
                                     :projection, :projected_p90, :ownership_projection,
                                     CAST(:player_json AS JSONB))
                                """
                            ),
                            player_rows,
                        )
                    connection.execute(
                        text(
                            """
                            INSERT INTO target.lineup_constraint_explanation
                                (lineup_id, constraint_name, constraint_status, explanation_json)
                            VALUES
                                (:lineup_id, 'optimizer_configuration', 'applied',
                                 CAST(:explanation_json AS JSONB))
                            """
                        ),
                        {
                            "lineup_id": lineup_id,
                            "explanation_json": json.dumps(
                                _json_safe(
                                    {
                                        "contest_format": job.contest_format,
                                        "objective": job.objective,
                                        "strategy": job.strategy,
                                        "params": job.params,
                                    }
                                ),
                                sort_keys=True,
                                allow_nan=False,
                            ),
                        },
                    )
                    stack_policy = job.params.get("stack_policy")
                    if isinstance(stack_policy, dict):
                        connection.execute(
                            text(
                                """
                                INSERT INTO target.lineup_constraint_explanation
                                    (lineup_id, constraint_name, constraint_status, explanation_json)
                                VALUES
                                    (:lineup_id, 'stack_policy', :constraint_status,
                                     CAST(:explanation_json AS JSONB))
                                """
                            ),
                            {
                                "lineup_id": lineup_id,
                                "constraint_status": (
                                    "applied" if stack_policy.get("enabled") else "baseline"
                                ),
                                "explanation_json": json.dumps(
                                    _json_safe(stack_policy),
                                    sort_keys=True,
                                    allow_nan=False,
                                ),
                            },
                        )
                    if cash_summary:
                        connection.execute(
                            text(
                                """
                                INSERT INTO target.lineup_constraint_explanation
                                    (lineup_id, constraint_name, constraint_status, explanation_json)
                                VALUES
                                    (:lineup_id, 'cash_objective', 'applied',
                                     CAST(:explanation_json AS JSONB))
                                """
                            ),
                            {
                                "lineup_id": lineup_id,
                                "explanation_json": json.dumps(
                                    _json_safe(
                                        {
                                            "config": job.params.get("objective_config", {}),
                                            "summary": cash_summary,
                                        }
                                    ),
                                    sort_keys=True,
                                    allow_nan=False,
                                ),
                            },
                        )
            return True
        except Exception as exc:  # noqa: BLE001 - report optimization even if lineage persistence is unavailable
            logger.warning("Failed to persist target optimizer run %s: %s", job.job_id, exc)
            return False

    def _load_persisted_job(self, job_id: str) -> OptimizerJob | None:
        """Reload a completed or failed optimizer execution after process restart."""
        try:
            with self.engine.begin() as connection:
                run_row = connection.execute(
                    text(
                        "SELECT * FROM target.optimizer_run "
                        "WHERE optimizer_run_id = :optimizer_run_id"
                    ),
                    {"optimizer_run_id": job_id},
                ).mappings().first()
                if not run_row:
                    return None
                lineup_rows = connection.execute(
                    text(
                        "SELECT lineup_id, lineup_number FROM target.lineup "
                        "WHERE optimizer_run_id = :optimizer_run_id ORDER BY lineup_number"
                    ),
                    {"optimizer_run_id": job_id},
                ).mappings().all()
                results: list[list[dict]] = []
                for lineup_row in lineup_rows:
                    player_rows = connection.execute(
                        text(
                            "SELECT player_json FROM target.lineup_player "
                            "WHERE lineup_id = :lineup_id ORDER BY slot_index"
                        ),
                        {"lineup_id": lineup_row["lineup_id"]},
                    ).mappings().all()
                    lineup = []
                    for player_row in player_rows:
                        payload = player_row.get("player_json") or {}
                        if isinstance(payload, str):
                            payload = json.loads(payload)
                        lineup.append(dict(payload))
                    results.append(lineup)

            params = run_row.get("constraint_config_json") or {}
            if isinstance(params, str):
                params = json.loads(params)
            job = OptimizerJob(
                job_id=str(run_row["optimizer_run_id"]),
                status=str(run_row["status"]),
                created_at=run_row["created_at"],
                updated_at=run_row["updated_at"],
                season=int(run_row["season"]),
                week=int(run_row["week"]),
                slate=str(run_row.get("slate_id") or ""),
                strategy=str(run_row["strategy"]),
                contest_format=str(run_row["contest_format"]),
                objective=str(run_row["objective"]),
                params=dict(params),
                projection_run_id=run_row.get("projection_run_id"),
                rule_run_id=run_row.get("rule_run_id"),
                data_cutoff_at=run_row.get("data_cutoff_at"),
                lineage_persisted=True,
                results=results if str(run_row["status"]) == "completed" else None,
                message=run_row.get("message"),
            )
            self._jobs[job_id] = job
            return job
        except Exception as exc:  # noqa: BLE001 - older databases may not have target optimizer tables
            logger.info("Persisted optimizer run %s is unavailable: %s", job_id, exc)
            return None

    @staticmethod
    def _gpp_player_to_dict(player: GPPPlayer) -> dict:
        return {
            "player_id": player.player_id,
            "name": player.name,
            "player_name": player.name,
            "player_display_name": player.name,
            "team": player.team,
            "player_team": player.team,
            "opponent_team": player.opponent,
            "roster_position": player.position,
            "position": player.position,
            "salary": player.salary,
            "projection": player.projection,
            "predicted_mean": player.projection,
            "predicted_p90": player.ceiling,
            "ownership": player.ownership,
            "optimal_lineup_probability": player.optimal_lineup_probability,
            "leverage": player.leverage,
            "tags": list(player.tags),
        }

    def _load_symbolic_explanations(self, season: int, week: int, slate: str) -> dict[str, list[dict]]:
        """Return recent symbolic adjustment traces keyed by player_id."""
        try:
            with self.engine.begin() as connection:
                rows = pd.read_sql(
                    text(
                        """
                        SELECT DISTINCT ON (sa.player_id, sa.rule_id)
                            sa.player_id,
                            sa.rule_run_id,
                            sa.rule_id,
                            sa.rule_name,
                            sa.reason,
                            sa.mean_before,
                            sa.mean_after,
                            sa.p90_before,
                            sa.p90_after,
                            sa.delta_mean,
                            sa.delta_p90,
                            rr.created_at
                        FROM symbolic_adjustments sa
                        LEFT JOIN symbolic_rule_runs rr
                            ON rr.rule_run_id = sa.rule_run_id
                        WHERE sa.season = :season
                          AND sa.week = :week
                          AND (sa.slate = :slate OR sa.slate IS NULL)
                        ORDER BY sa.player_id, sa.rule_id, rr.created_at DESC NULLS LAST
                        """
                    ),
                    connection,
                    params={"season": season, "week": week, "slate": slate},
                )
        except Exception:
            return {}

        explanations: dict[str, list[dict]] = {}
        for row in rows.to_dict(orient="records"):
            player_id = str(row.get("player_id"))
            explanations.setdefault(player_id, []).append(
                {
                    "rule_run_id": row.get("rule_run_id"),
                    "rule_id": row.get("rule_id"),
                    "rule_name": row.get("rule_name"),
                    "reason": row.get("reason"),
                    "mean_before": row.get("mean_before"),
                    "mean_after": row.get("mean_after"),
                    "p90_before": row.get("p90_before"),
                    "p90_after": row.get("p90_after"),
                    "delta_mean": row.get("delta_mean"),
                    "delta_p90": row.get("delta_p90"),
                }
            )
        return explanations

    def _attach_symbolic_explanations(
        self,
        lineups: list[list[dict]],
        season: int,
        week: int,
        slate: str,
    ) -> None:
        explanation_map = self._load_symbolic_explanations(season=season, week=week, slate=slate)
        if not explanation_map:
            return
        for lineup in lineups:
            for row in lineup:
                player_id = str(row.get("player_id"))
                notes = explanation_map.get(player_id, [])
                row["symbolic_explanations"] = notes
                row["symbolic_adjusted"] = bool(notes)
                if notes:
                    row["symbolic_rule_summary"] = ", ".join(
                        str(note.get("rule_id")) for note in notes if note.get("rule_id")
                    )

    @staticmethod
    def _parse_game_info_opponent(game_info: str, player_team: str | None) -> str | None:
        """
        Extract opponent from DK game_info (e.g., 'GB@DET' or 'GB @ DET').
        """
        if not game_info:
            return None
        cleaned = game_info.replace(" ", "").upper()
        if "@" not in cleaned:
            return None
        left, right = cleaned.split("@", 1)
        player_team = (player_team or "").upper()
        if player_team == left:
            return right
        if player_team == right:
            return left
        # Fallback: return right side
        return right

    def _load_target_player_pool(
        self,
        season: int,
        week: int,
        slate: str,
        projection_run_id: str | None = None,
    ) -> pd.DataFrame:
        """Load one exact target-schema salary/projection contract."""
        inspector = inspect(self.engine)
        has_curated_salary = inspector.has_table("curated_salary")
        has_target_salary = inspector.has_table("snapshot_salary", schema="target")
        if not (
            (has_curated_salary or has_target_salary)
            and inspector.has_table("player_projection", schema="target")
            and inspector.has_table("dim_player", schema="target")
        ):
            return pd.DataFrame()
        if has_curated_salary:
            salary_cte = """
                latest_salary AS (
                    SELECT DISTINCT ON (player_master_id)
                        player_master_id AS player_id,
                        source_player_key AS site_player_id,
                        player_name AS salary_name,
                        salary,
                        COALESCE(NULLIF(position, ''), roster_position) AS salary_position,
                        team AS team_id,
                        opponent AS opponent_team_id,
                        game_info AS game_id
                    FROM public.curated_salary
                    WHERE season = :season AND week = :week
                      AND UPPER(slate) = UPPER(:slate)
                      AND player_master_id IS NOT NULL
                    ORDER BY player_master_id, created_at DESC
                )
            """
        else:
            salary_cte = """
                latest_salary AS (
                    SELECT DISTINCT ON (player_id)
                        player_id, site_player_id, NULL::TEXT AS salary_name, salary,
                        roster_position AS salary_position,
                        team_id, opponent_team_id, game_id
                    FROM target.snapshot_salary
                    WHERE season = :season AND week = :week
                      AND UPPER(COALESCE(slate, slate_id)) = UPPER(:slate)
                    ORDER BY player_id,
                        CASE WHEN UPPER(roster_position) = 'FLEX' THEN 0 ELSE 1 END,
                        as_of DESC
                )
            """
        projection_columns = {
            column["name"]
            for column in inspector.get_columns("player_projection", schema="target")
        }
        calibration_select = {
            "calibration_method": "p.calibration_method" if "calibration_method" in projection_columns else "'target_projection_fallback'",
            "calibration_position": "p.calibration_position" if "calibration_position" in projection_columns else "d.primary_position",
            "calibration_role": "p.calibration_role" if "calibration_role" in projection_columns else "'unknown'",
            "calibration_sample_size": "p.calibration_sample_size" if "calibration_sample_size" in projection_columns else "0",
        }
        has_injuries = inspector.has_table("snapshot_injury_status", schema="target")
        injury_cte = ""
        injury_join = ""
        injury_filter = ""
        if has_injuries:
            injury_cte = """,
                latest_injury AS (
                    SELECT DISTINCT ON (player_id)
                        player_id, injury_status
                    FROM target.snapshot_injury_status
                    WHERE season = :season AND week = :week
                      AND (slate IS NULL OR UPPER(slate) = UPPER(:slate))
                    ORDER BY player_id, as_of DESC
                )
            """
            injury_join = "LEFT JOIN latest_injury i ON i.player_id = s.player_id"
            injury_filter = "WHERE COALESCE(i.injury_status, '') !~* '(OUT|IR|PUP|NFI|RESERVE)'"

        query = text(
            f"""
            WITH {salary_cte},
            latest_projection AS (
                SELECT DISTINCT ON (player_id) *
                FROM target.player_projection
                WHERE season = :season AND week = :week
                  AND (slate_id IS NULL OR UPPER(slate_id) = UPPER(:slate))
                  AND projection_run_id = COALESCE(
                      :projection_run_id,
                      (
                          SELECT projection_run_id
                          FROM target.active_projection_run
                          WHERE season = :season AND week = :week
                            AND (UPPER(slate_id) = UPPER(:slate) OR slate_id = 'DEFAULT')
                          ORDER BY CASE WHEN UPPER(slate_id) = UPPER(:slate)
                              THEN 0 ELSE 1 END, selected_at DESC
                          LIMIT 1
                      ),
                      (
                          SELECT projection_run_id
                          FROM target.player_projection
                          WHERE season = :season AND week = :week
                            AND (slate_id IS NULL OR UPPER(slate_id) = UPPER(:slate))
                          ORDER BY created_at DESC, projection_run_id
                          LIMIT 1
                      )
                  )
                ORDER BY player_id, created_at DESC
            )
            {injury_cte}
            SELECT
                s.player_id,
                s.site_player_id AS dk_player_id,
                COALESCE(NULLIF(s.salary_name, ''), NULLIF(d.full_name, ''), s.player_id) AS name,
                COALESCE(NULLIF(s.salary_name, ''), NULLIF(d.full_name, ''), s.player_id) AS player_name,
                CASE
                    WHEN UPPER(COALESCE(NULLIF(s.salary_position, ''), d.primary_position)) IN ('D', 'DEF') THEN 'DST'
                    ELSE UPPER(COALESCE(NULLIF(s.salary_position, ''), d.primary_position))
                END AS position,
                s.salary,
                s.team_id AS player_team,
                s.opponent_team_id AS opponent_team,
                s.game_id,
                p.mean AS projection,
                p.median AS predicted_p50,
                p.p10 AS predicted_p10,
                p.p90 AS predicted_p90,
                p.p90,
                p.projection_run_id,
                p.data_cutoff_at,
                {calibration_select['calibration_method']} AS calibration_method,
                {calibration_select['calibration_position']} AS calibration_position,
                {calibration_select['calibration_role']} AS calibration_role,
                {calibration_select['calibration_sample_size']} AS calibration_sample_size
            FROM latest_salary s
            LEFT JOIN latest_projection p ON p.player_id = s.player_id
            LEFT JOIN target.dim_player d ON d.player_id = s.player_id
            {injury_join}
            {injury_filter}
            """
        )
        with self.engine.begin() as connection:
            pool = pd.read_sql(
                query,
                connection,
                params={
                    "season": season,
                    "week": week,
                    "slate": slate,
                    "projection_run_id": projection_run_id,
                },
            )
        if pool.empty:
            return pool
        pool["player_id"] = pool["player_id"].astype(str)
        pool["salary"] = pd.to_numeric(pool["salary"], errors="coerce").fillna(0)
        pool["projection"] = pd.to_numeric(pool["projection"], errors="coerce").fillna(0.0)
        for column, fallback in (
            ("predicted_p50", pool["projection"]),
            ("predicted_p10", pool["projection"]),
            ("predicted_p90", pool["projection"]),
            ("p90", pool["projection"]),
        ):
            pool[column] = pd.to_numeric(pool[column], errors="coerce").fillna(fallback)
        pool["position"] = pool["position"].fillna("").astype(str).str.upper()
        pool["player_team"] = pool["player_team"].fillna("").astype(str).str.upper()
        pool["opponent_team"] = pool["opponent_team"].fillna("").astype(str).str.upper()
        pool["name_norm"] = pool["name"].astype(str).str.lower().str.strip().map(_normalize_alias)
        pool["team_norm"] = pool["player_team"]
        return pool

    def _load_player_pool(
        self,
        season: int,
        week: int,
        slate: str,
        projection_run_id: str | None = None,
    ) -> pd.DataFrame:
        """Join salaries with projections for the slate."""
        inspector = inspect(self.engine)
        if (
            inspector.has_table("player_projection", schema="target")
            and (
                inspector.has_table("curated_salary")
                or inspector.has_table("snapshot_salary", schema="target")
            )
        ):
            return self._load_target_player_pool(
                season,
                week,
                slate,
                projection_run_id=projection_run_id,
            )
        if not (
            inspector.has_table("curated_salaries")
            and inspector.has_table("player_expected_points")
        ):
            return self._load_target_player_pool(
                season,
                week,
                slate,
                projection_run_id=projection_run_id,
            )
        try:
            with self.engine.begin() as connection:
                salaries = pd.read_sql(
                    text(
                        "SELECT * FROM curated_salaries WHERE season = :season AND week = :week AND slate = :slate"
                    ),
                    connection,
                    params={"season": season, "week": week, "slate": slate},
                )
                if "player_id" not in salaries.columns and "ID" in salaries.columns:
                    salaries["player_id"] = salaries["ID"]
                projections = pd.read_sql(
                    text(
                        "SELECT * FROM player_expected_points "
                        "WHERE season = :season AND week = :week AND (slate = :slate OR slate IS NULL)"
                    ),
                    connection,
                    params={"season": season, "week": week, "slate": slate},
                )
                try:
                    adjusted = pd.read_sql(
                        text(
                            "SELECT DISTINCT ON (player_id) player_id, rule_run_id, adjusted_mean, adjusted_p90, reason "
                            "FROM player_expected_points_adjusted "
                            "WHERE season = :season AND week = :week AND (slate = :slate OR slate IS NULL) "
                            "ORDER BY player_id, created_at DESC"
                        ),
                        connection,
                        params={"season": season, "week": week, "slate": slate},
                    )
                except Exception:
                    adjusted = pd.DataFrame()
                if not projections.empty and not adjusted.empty:
                    projections = projections.merge(adjusted, on="player_id", how="left")
                    projections["adj_mean_final"] = projections["adjusted_mean"].fillna(
                        projections.get("adj_mean_final", projections.get("predicted_mean"))
                    )
                    projections["predicted_p90"] = projections["adjusted_p90"].fillna(
                        projections.get("predicted_p90")
                    )
                injuries = pd.read_sql(
                    text(
                        "SELECT player_id, injury_indicator, first_name, last_name, nickname, team "
                        "FROM weekly_injuries "
                        "WHERE season = :season AND week = :week "
                        "AND (slate = :slate OR slate IS NULL)"
                    ),
                    connection,
                    params={"season": season, "week": week, "slate": slate},
                )
                try:
                    starters_df = pd.read_sql(
                        text(
                            "SELECT player_id, player_master_id FROM starting_qbs "
                            "WHERE season = :season AND week = :week AND (slate = :slate OR slate IS NULL)"
                        ),
                        connection,
                        params={"season": season, "week": week, "slate": slate},
                    )
                except Exception:
                    starters_df = pd.DataFrame()
        except ResourceClosedError:
            # Recreate engine if previous connection was closed
            self.engine = create_engine(self.connection_string)
            return self._load_player_pool(
                season,
                week,
                slate,
                projection_run_id=projection_run_id,
            )
        if salaries.empty:
            return pd.DataFrame()
        # Slate sanity counts before projections
        pos_counts = salaries.get("Position", salaries.get("position", pd.Series([], dtype=object))).astype(str).str.upper().value_counts()
        print(f"[slate-check] counts by position: {pos_counts.to_dict()}")
        expected_ranges = {
            "DST": (12, 16),
            "QB": (10, 18),
            "RB": (30, 60),
            "WR": (60, 120),
            "TE": (20, 50),
        }
        for pos, (lo, hi) in expected_ranges.items():
            cnt = pos_counts.get(pos, 0)
            if cnt < lo or cnt > hi:
                print(f"[slate-check] WARNING: {pos} count {cnt} outside expected range {lo}-{hi}")
        # First filter: restrict QBs to starters if available
        if not starters_df.empty:
            starter_ids = {str(pid) for pid in starters_df.get("player_id", []) if pd.notna(pid)}
            starter_pm_ids = {str(pid) for pid in starters_df.get("player_master_id", []) if pd.notna(pid)}
            qb_mask = salaries.get("Position", salaries.get("position", pd.Series([], dtype=object))).astype(str).str.upper() == "QB"
            before_qb = qb_mask.sum()
            if before_qb:
                id_series = salaries["player_id"].astype(str) if "player_id" in salaries.columns else pd.Series([], dtype=str)
                pm_series = salaries.get("player_master_id", pd.Series([], dtype=str)).astype(str)
                keep_qb = qb_mask & (
                    id_series.isin(starter_ids) | pm_series.isin(starter_pm_ids)
                )
                salaries = pd.concat([salaries[~qb_mask], salaries[keep_qb]], ignore_index=True)
                after_qb = keep_qb.sum()
                print(f"[slate-check] QB starters filter (pre-merge): before={before_qb} after={after_qb} starters={len(starter_ids)}")
        if projections.empty:
            salaries["projection"] = salaries.get("average_points_per_game", 0)
            salaries["p90"] = salaries["projection"]
            return salaries

        # Preserve DK id and align merge key to player_master_id when present
        if "dk_player_id" not in salaries.columns:
            if "ID" in salaries.columns:
                salaries["dk_player_id"] = salaries["ID"]
            else:
                salaries["dk_player_id"] = salaries.get("player_id", "")
        if "player_master_id" in salaries.columns:
            salaries["player_id"] = salaries["player_master_id"].fillna(salaries["player_id"])
        # Normalize salary numeric column
        if "salary" not in salaries.columns:
            if "Salary" in salaries.columns:
                salaries["salary"] = pd.to_numeric(salaries["Salary"], errors="coerce")
            else:
                salaries["salary"] = 0
        else:
            salaries["salary"] = pd.to_numeric(salaries["salary"], errors="coerce")

        # Normalize key types before merging
            salaries["player_id"] = salaries["player_id"].astype(str)
            projections["player_id"] = projections["player_id"].astype(str)
            injuries["player_id"] = injuries.get("player_id", pd.Series([], dtype=str)).astype(str)
            if not projections.empty:
                projections = projections.sort_values(by=["adj_mean_final", "predicted_mean"], ascending=False)
                projections = projections.drop_duplicates(subset=["player_id"], keep="first")
            if "name" in salaries.columns:
                salaries["name_norm"] = salaries["name"].astype(str).str.lower().str.strip().map(_normalize_alias)
            if "player_name" in salaries.columns and "name_norm" not in salaries.columns:
                salaries["name_norm"] = salaries["player_name"].astype(str).str.lower().str.strip().map(_normalize_alias)
        if not injuries.empty:
            injuries = injuries.copy()
            for col in ["first_name", "last_name", "nickname", "player_name", "name"]:
                if col in injuries.columns:
                    injuries[col] = injuries[col].astype(str)
            injuries["name_norm"] = injuries.apply(
                lambda row: " ".join(
                    [
                        str(row.get("first_name", "")).strip(),
                        str(row.get("last_name", "")).strip(),
                    ]
                ).lower().strip(),
                axis=1,
            )
            # fallback to nickname/player_name if name missing
            if "nickname" in injuries.columns:
                injuries.loc[injuries["name_norm"] == "", "name_norm"] = (
                    injuries["nickname"].astype(str).str.lower().str.strip()
                )
            if "player_name" in injuries.columns:
                injuries.loc[injuries["name_norm"] == "", "name_norm"] = (
                    injuries["player_name"].astype(str).str.lower().str.strip()
                )
            injuries["name_norm"] = injuries["name_norm"].map(_normalize_alias)

        # Use adjusted mean when available; fall back to model mean
        if "adj_mean_final" in projections.columns:
            projections = projections.rename(columns={"adj_mean_final": "projection"})
        elif "adj_mean" in projections.columns:
            projections = projections.rename(columns={"adj_mean": "projection"})
        else:
            projections = projections.rename(columns={"predicted_mean": "projection"})
        projection_defaults = {
            "predicted_p50": projections.get("projection", 0.0),
            "predicted_p10": projections.get("predicted_p50", projections.get("projection", 0.0)),
            "calibration_role": "unknown",
            "calibration_sample_size": 0,
            "calibration_method": "projection_fallback",
        }
        for column, default in projection_defaults.items():
            if column not in projections.columns:
                projections[column] = default
        merged = salaries.merge(
            projections[
                [
                    "player_id",
                    "projection",
                    "predicted_p90",
                    "predicted_p50",
                    "predicted_p10",
                    "calibration_role",
                    "calibration_sample_size",
                    "calibration_method",
                    "opponent_team",
                    "recent_team",
                    "position",
                ]
            ],
            on="player_id",
            how="left",
        )
        # Fill projection from averages if model outputs are missing
        avg_col = "average_points_per_game" if "average_points_per_game" in merged.columns else None
        if not avg_col and "AvgPointsPerGame" in merged.columns:
            avg_col = "AvgPointsPerGame"
        if avg_col:
            merged["projection"] = merged["projection"].fillna(merged[avg_col])
        merged["p90"] = merged["predicted_p90"].fillna(merged["projection"])

        # Fallback: try name-based match to projections when ids don't align
        projections = projections.copy()
        projections["name_norm"] = projections.get("player_display_name", "").astype(str).str.lower().str.strip().map(_normalize_alias)
        merged_name_norm = merged.get("name_norm")
        if "projection" in merged.columns and merged["projection"].isna().any() and merged_name_norm is not None:
            proj_map = dict(zip(projections["name_norm"], projections["projection"]))
            p90_map = dict(zip(projections["name_norm"], projections.get("predicted_p90", projections["projection"])))
            missing_mask = merged["projection"].isna()
            merged.loc[missing_mask, "projection"] = merged.loc[missing_mask, "name_norm"].map(proj_map)
            merged.loc[missing_mask, "p90"] = merged.loc[missing_mask, "name_norm"].map(p90_map)

        # Ensure a ceiling uplift exists; if p90 ~= projection, scale up modestly to avoid degenerate ceilings.
        def _ceiling_with_uplift(row: pd.Series) -> float:
            proj_val = float(row.get("projection", 0) or 0)
            p90_val = float(row.get("p90", 0) or 0)
            if proj_val <= 0:
                return p90_val
            pos = str(row.get("position", "")).upper()
            floor_mult = 1.05 if pos in {"DST", "D", "DEF"} else 1.10
            if p90_val <= proj_val * floor_mult:
                # Modest uplift to avoid degenerate ceilings; DST smaller bump.
                bump = 1.08 if pos in {"DST", "D", "DEF"} else 1.18
                return proj_val * bump
            return p90_val

        merged["p90"] = merged.apply(_ceiling_with_uplift, axis=1)

        # Prefer readable names for downstream display
        if "player_display_name" in merged.columns:
            merged["name"] = merged["player_display_name"]
            merged["player_name"] = merged["player_display_name"]
        elif "name" not in merged.columns and "player_name" in merged.columns:
            merged["name"] = merged["player_name"]
        # Normalize positions (prefer projection/salary position over showdown CPT/FLEX tags)
        if "position_y" in merged.columns:
            merged["position"] = merged["position_y"]
        elif "position_x" in merged.columns:
            merged["position"] = merged["position_x"]
        elif "position" not in merged.columns:
            merged["position"] = merged.get("roster_position", "")
        merged["position"] = (
            merged["position"]
            .fillna(merged.get("position_x", merged.get("roster_position", "")))
            .astype(str)
            .str.upper()
            .str.split("/")
            .str[0]
        )
        # Filter QBs to starters if starting_qbs table is available
        if 'position' in merged.columns and not locals().get("starters_df", pd.DataFrame()).empty:
            starter_ids = {str(pid) for pid in starters_df.get("player_id", []) if pd.notna(pid)}
            starter_pm_ids = {str(pid) for pid in starters_df.get("player_master_id", []) if pd.notna(pid)}
            before_qb = len(merged[merged["position"] == "QB"])
            merged = merged[
                (merged["position"] != "QB")
                | merged["player_id"].astype(str).isin(starter_ids)
                | merged.get("player_master_id", pd.Series([], dtype=str)).astype(str).isin(starter_pm_ids)
            ]
            after_qb = len(merged[merged["position"] == "QB"])
            print(f"[slate-check] QB starters filter: before={before_qb} after={after_qb} starters={len(starter_ids)}")
        # Normalize team/opponent for correlation rules
        team_series = (
            merged["player_team"]
            if "player_team" in merged.columns
            else merged["recent_team"]
            if "recent_team" in merged.columns
            else pd.Series("", index=merged.index)
        )
        merged["player_team"] = team_series.astype(str).str.upper()
        if "opponent_team" in merged.columns:
            merged["opponent_team"] = merged["opponent_team"].astype(str).str.upper()
        # Fill missing opponent from game_info for DST and any rows missing it
        if "game_info" in merged.columns:
            merged["game_info"] = merged["game_info"].astype(str)
            missing_mask = merged["opponent_team"].isna() if "opponent_team" in merged.columns else pd.Series([True] * len(merged))
            merged.loc[missing_mask, "opponent_team"] = merged.loc[missing_mask].apply(
                lambda row: self._parse_game_info_opponent(row.get("game_info"), row.get("player_team")),
                axis=1,
            )

        # Normalize salary names/teams for later matching
        base_name = (
            merged["name_norm"]
            if "name_norm" in merged.columns
            else merged["name"]
            if "name" in merged.columns
            else merged["player_name"]
            if "player_name" in merged.columns
            else pd.Series("", index=merged.index)
        )
        merged["name_norm"] = base_name.astype(str).str.lower().str.strip().map(_normalize_alias)
        merged_team_series = (
            merged["player_team"]
            if "player_team" in merged.columns
            else (merged["team"] if "team" in merged.columns else pd.Series("", index=merged.index))
        )
        merged["team_norm"] = merged_team_series.astype(str).str.upper().str.strip()

        # Drop injured/IR/Out players using salary-like matching rules
        if not injuries.empty:
            inj = injuries.copy()
            inj["injury_indicator"] = inj["injury_indicator"].fillna("").astype(str).str.upper()
            block_tokens = ("OUT", "IR", "PUP", "NFI", "RESERVE")
            inj = inj[inj["injury_indicator"].str.contains("|".join(block_tokens))]
            inj["team_norm"] = (
                inj["team"] if "team" in inj.columns else (inj["player_team"] if "player_team" in inj.columns else "")
            )
            inj["team_norm"] = inj["team_norm"].astype(str).str.upper().str.strip()

            def _norm_injury_name(row):
                nick = str(row.get("nickname", "")).lower().strip()
                full = f"{str(row.get('first_name', '')).strip()} {str(row.get('last_name', '')).strip()}".strip().lower()
                if nick:
                    return nick
                return full

            inj["name_norm"] = [_norm_injury_name(r) for r in inj.to_dict(orient="records")]
            inj["last_norm"] = inj.get("last_name", "").astype(str).str.lower().str.strip() if "last_name" in inj.columns else ""
            bad_ids = set(inj["player_id"].astype(str))
            bad_name_team = {(r.name_norm, r.team_norm) for r in inj.itertuples() if r.name_norm}
            bad_names = {r.name_norm for r in inj.itertuples() if r.name_norm}
            bad_last_team = {(str(r.last_norm).lower().strip(), r.team_norm) for r in inj.itertuples() if getattr(r, "last_norm", "")}
            bad_last = {str(r.last_norm).lower().strip() for r in inj.itertuples() if getattr(r, "last_norm", "")}

            def _salary_last(row) -> str:
                name = str(row.get("name_norm", "")).strip()
                if " " in name:
                    return name.split(" ")[-1]
                return name

            def _is_injured(row) -> bool:
                pid = str(row.get("player_id"))
                n = str(row.get("name_norm", "")).lower().strip()
                t = str(row.get("team_norm", "")).upper().strip()
                ln = _salary_last(row).lower().strip()
                if pid in bad_ids:
                    return True
                if (n, t) in bad_name_team:
                    return True
                if n in bad_names:
                    return True
                if (ln, t) in bad_last_team:
                    return True
                if ln in bad_last:
                    return True
                return False

            merged = merged[~merged.apply(_is_injured, axis=1)]

        proj_series = pd.to_numeric(merged.get("projection"), errors="coerce")
        valid_mask = proj_series.notna() & (proj_series > 0)
        fallback_mask = proj_series.notna() & (proj_series <= 0)
        nan_count = proj_series.isna().sum()
        print(
            f"[pool:pre-filter] projection counts: valid>0={valid_mask.sum()} fallback<=0={fallback_mask.sum()} nan={nan_count}"
        )
        _log_pool_stats(merged, "pre-filter")
        proj_med = float(pd.to_numeric(merged.get("projection", pd.Series()), errors="coerce").median())
        p90_med = float(pd.to_numeric(merged.get("p90", pd.Series()), errors="coerce").median())
        qb_med = float(pd.to_numeric(merged.loc[merged["position"] == "QB", "projection"], errors="coerce").median()) if not merged.empty else 0
        dst_med = float(pd.to_numeric(merged.loc[merged["position"].isin(["DST", "D", "DEF"]), "projection"], errors="coerce").median()) if not merged.empty else 0
        if (qb_med and qb_med < 12) or (dst_med and dst_med < 3) or (proj_med and proj_med < 6):
            # Attempt auto-fix by switching to predicted_p50/p90 if available
            if "predicted_p50" in merged.columns:
                merged["projection"] = pd.to_numeric(merged["predicted_p50"], errors="coerce")
            if "predicted_p90" in merged.columns:
                merged["p90"] = pd.to_numeric(merged["predicted_p90"], errors="coerce")
            _log_pool_stats(merged, "pre-filter-refit")
            proj_med = float(pd.to_numeric(merged.get("projection", pd.Series()), errors="coerce").median())
            p90_med = float(pd.to_numeric(merged.get("p90", pd.Series()), errors="coerce").median())
            qb_med = float(pd.to_numeric(merged.loc[merged["position"] == "QB", "projection"], errors="coerce").median()) if not merged.empty else 0
            dst_med = float(pd.to_numeric(merged.loc[merged["position"].isin(["DST", "D", "DEF"]), "projection"], errors="coerce").median()) if not merged.empty else 0
            if (qb_med and qb_med < 12) or (dst_med and dst_med < 3) or (proj_med and proj_med < 6):
                logger.warning(
                    "Projection scale still low after refit: qb_med=%.2f dst_med=%.2f proj_med=%.2f; continuing",
                    qb_med,
                    dst_med,
                    proj_med,
                )
        if proj_med and p90_med and p90_med / max(proj_med, 1e-6) > 3:
            logger.warning("Ceiling scale mismatch: p90/mean median ratio=%.2f", p90_med / max(proj_med, 1e-6))
        return merged

    @staticmethod
    def _position_mask(df: pd.DataFrame, positions: List[str]) -> List[str]:
        return df.index[df["position"].isin(positions)].tolist()

    def add_qb_stacking_constraints(
        self,
        model: pulp.LpProblem,
        x: dict,
        pool: pd.DataFrame,
        stack_cfg: dict,
    ) -> dict:
        """
        Add QB stacking constraints with optional bring-backs.
        Returns metadata per QB for post-solve validation.
        """
        if pool.empty:
            return {}

        include_rb = bool(stack_cfg.get("include_rb_in_stack", False))
        pass_positions = {"WR", "TE"}
        if include_rb:
            pass_positions.add("RB")

        bringback_enabled = bool(stack_cfg.get("bringback", False))
        bringback_positions = {p.upper() for p in stack_cfg.get("bringback_positions", {"WR", "TE"})}
        stack_min_default = int(stack_cfg.get("stack_min", 1))
        stack_max = stack_cfg.get("stack_max")
        stack_max_val = None
        if stack_max not in (None, "", False):
            try:
                stack_max_val = int(stack_max)
            except Exception:
                stack_max_val = None

        team_field = "player_team" if "player_team" in pool.columns else "team"
        pool[team_field] = pool[team_field].astype(str).str.upper()
        pool["opponent_team"] = pool.get("opponent_team", "").astype(str).str.upper()

        team_pos_to_idx: dict[tuple[str, str], list[int]] = {}
        for i in pool.index:
            team = str(pool.loc[i, team_field]).upper()
            pos = str(pool.loc[i, "position"]).upper()
            team_pos_to_idx.setdefault((team, pos), []).append(i)

        qb_idx = pool.index[pool["position"] == "QB"].tolist()
        metadata: dict[str, dict] = {}

        for q_idx in qb_idx:
            team = str(pool.loc[q_idx, team_field]).upper()
            opp = str(pool.loc[q_idx, "opponent_team"]).upper()
            qb_id = str(pool.loc[q_idx, "player_id"])

            team_stack_idxs: list[int] = []
            for pos in pass_positions:
                team_stack_idxs.extend(team_pos_to_idx.get((team, pos), []))
            team_stack_idxs = [i for i in team_stack_idxs if i != q_idx]

            if len(team_stack_idxs) < stack_min_default:
                # Exclude this QB (insufficient stack partners after filtering)
                model += x[q_idx] == 0
                metadata[qb_id] = {
                    "qb_idx": q_idx,
                    "team": team,
                    "opp": opp,
                    "stack_min": stack_min_default,
                    "stack_max": stack_max_val,
                    "team_stack_ids": set(),
                    "bringback_ids": set(),
                    "bringback_required": False,
                    "include_rb": include_rb,
                    "bringback_positions": bringback_positions,
                }
                continue

            model += pulp.lpSum(x[i] for i in team_stack_idxs) >= stack_min_default * x[q_idx]
            if stack_max_val is not None:
                big_m = len(team_stack_idxs)
                model += pulp.lpSum(x[i] for i in team_stack_idxs) <= stack_max_val * x[q_idx] + big_m * (1 - x[q_idx])

            bringback_idxs: list[int] = []
            bringback_required = False
            if bringback_enabled and not opp:
                # Exclude this QB due to missing opponent
                model += x[q_idx] == 0
                metadata[qb_id] = {
                    "qb_idx": q_idx,
                    "team": team,
                    "opp": opp,
                    "stack_min": stack_min_default,
                    "stack_max": stack_max_val,
                    "team_stack_ids": set(),
                    "bringback_ids": set(),
                    "bringback_required": False,
                    "include_rb": include_rb,
                    "bringback_positions": bringback_positions,
                }
                continue
            if bringback_enabled and opp:
                for pos in bringback_positions:
                    bringback_idxs.extend(team_pos_to_idx.get((opp, pos), []))
                bringback_idxs = [i for i in bringback_idxs if i != q_idx]
                if bringback_idxs:
                    model += pulp.lpSum(x[i] for i in bringback_idxs) >= 1 * x[q_idx]
                    bringback_required = True
                else:
                    # Exclude this QB if no bring-back available
                    model += x[q_idx] == 0
                    metadata[qb_id] = {
                        "qb_idx": q_idx,
                        "team": team,
                        "opp": opp,
                        "stack_min": stack_min_default,
                        "stack_max": stack_max_val,
                        "team_stack_ids": set(),
                        "bringback_ids": set(),
                        "bringback_required": False,
                        "include_rb": include_rb,
                        "bringback_positions": bringback_positions,
                    }
                    continue

            metadata[qb_id] = {
                "qb_idx": q_idx,
                "team": team,
                "opp": opp,
                "stack_min": stack_min_default,
                "stack_max": stack_max_val,
                "team_stack_ids": {str(pool.loc[i, "player_id"]) for i in team_stack_idxs},
                "bringback_ids": {str(pool.loc[i, "player_id"]) for i in bringback_idxs},
                "bringback_required": bringback_required,
                "include_rb": include_rb,
                "bringback_positions": bringback_positions,
            }

        return metadata

    @staticmethod
    def _validate_stack_solution(
        lineup_rows: List[dict],
        stack_meta: dict,
    ) -> None:
        if not lineup_rows:
            return
        qb_rows = [r for r in lineup_rows if str(r.get("position", "")).upper() == "QB"]
        if len(qb_rows) != 1:
            raise ValueError(f"Expected exactly 1 QB in lineup for validation, found {len(qb_rows)}")
        qb_row = qb_rows[0]
        qb_id = str(qb_row.get("player_id"))
        meta = stack_meta.get(qb_id)
        if not meta:
            raise ValueError(f"No stack metadata found for QB {qb_id}")

        selected_ids = {str(r.get("player_id")) for r in lineup_rows}
        team_stack_selected = len(meta["team_stack_ids"].intersection(selected_ids))
        if team_stack_selected < meta["stack_min"]:
            raise ValueError(
                f"Stack validation failed for QB {qb_id}: selected {team_stack_selected} stack pieces, "
                f"required min {meta['stack_min']}"
            )
        if meta["stack_max"] is not None and team_stack_selected > meta["stack_max"]:
            raise ValueError(
                f"Stack validation failed for QB {qb_id}: selected {team_stack_selected} stack pieces, "
                f"exceeds max {meta['stack_max']}"
            )
        if meta["bringback_required"] and not meta["bringback_ids"].intersection(selected_ids):
            raise ValueError(f"Bring-back validation failed for QB {qb_id}: none selected")

    @staticmethod
    def _lineups_satisfy_stack(lineups: List[List[dict]], stack_cfg: dict, contest_type: str) -> tuple[bool, str]:
        """Lightweight validation for finalized lineups (baseline or GPP pipeline)."""
        if contest_type == "captain" or not bool(stack_cfg.get("enabled", True)):
            return True, ""
        include_rb = bool(stack_cfg.get("include_rb_in_stack", False))
        pass_positions = {"WR", "TE"}
        if include_rb:
            pass_positions.add("RB")
        bringback_positions = {p.upper() for p in stack_cfg.get("bringback_positions", {"WR", "TE"})}
        stack_min = int(stack_cfg.get("stack_min", 1))
        stack_max = stack_cfg.get("stack_max")
        stack_max_val = None
        if stack_max not in (None, "", False):
            try:
                stack_max_val = int(stack_max)
            except Exception:
                stack_max_val = None
        bringback_required = bool(stack_cfg.get("bringback", False))

        def _team(row: dict) -> str:
            return str(
                row.get("player_team")
                or row.get("team")
                or row.get("team_norm")
                or ""
            ).upper()

        def _opp(row: dict) -> str:
            return str(
                row.get("opponent_team")
                or row.get("opp")
                or row.get("opponent")
                or ""
            ).upper()

        for idx, lineup in enumerate(lineups, start=1):
            qb_rows = [r for r in lineup if str(r.get("position", "")).upper() == "QB"]
            if len(qb_rows) != 1:
                return False, f"Lineup {idx} has {len(qb_rows)} QBs"
            qb = qb_rows[0]
            qb_team = _team(qb)
            qb_opp = _opp(qb)
            if not qb_team:
                return False, f"Lineup {idx} QB missing team"
            same_team = [r for r in lineup if _team(r) == qb_team and str(r.get("position", "")).upper() in pass_positions and r is not qb]
            if len(same_team) < stack_min:
                return False, f"Lineup {idx} stack failed: {len(same_team)} < {stack_min}"
            if stack_max_val is not None and len(same_team) > stack_max_val:
                return False, f"Lineup {idx} stack exceeded max {stack_max_val}"
            if bringback_required:
                if not qb_opp:
                    return False, f"Lineup {idx} QB missing opponent for bring-back"
                bringbacks = [r for r in lineup if _team(r) == qb_opp and str(r.get("position", "")).upper() in bringback_positions]
                if not bringbacks:
                    return False, f"Lineup {idx} missing bring-back vs {qb_opp}"
        return True, ""

    def _apply_pool_filters(self, pool: pd.DataFrame, contest_type: str) -> pd.DataFrame:
        """Prune the candidate pool with projection/ceiling rules while keeping stack pieces."""
        if pool.empty:
            return pool
        if "position" not in pool.columns:
            raise ValueError(f"Player pool missing 'position' column; columns={list(pool.columns)}")

        mode = "cash" if (contest_type or "tournament").lower() == "cash" else "gpp"
        df = pool.copy()
        df["salary"] = pd.to_numeric(df.get("salary", 0), errors="coerce").fillna(0)
        df["projection"] = pd.to_numeric(df.get("projection", 0), errors="coerce").fillna(0)
        df["p90"] = pd.to_numeric(df.get("p90", df["projection"]), errors="coerce").fillna(df["projection"])
        salary_k = (df["salary"] / 1000).replace(0, pd.NA)
        df["ceil_per_k"] = (df["p90"] / salary_k).fillna(0)

        # Drop only the worst DSTs; always keep the top few to preserve feasibility
        dst_mask = df["position"].isin(["DST", "D", "DEF"])
        if dst_mask.any():
            dst_sorted = df[dst_mask].sort_values("projection", ascending=False)
            keep_dst = dst_sorted.head(max(6, len(dst_sorted)))
            df = pd.concat([df[~dst_mask], keep_dst])

        team_field = "player_team" if "player_team" in df.columns else "team"
        df[team_field] = df[team_field].astype(str).str.upper()
        df["opponent_team"] = df.get("opponent_team", "").astype(str).str.upper()
        df["player_id"] = df["player_id"].astype(str)

        cash_cfg = {
            "score_field": "projection",
            "value_floor": {"default": 2.6, "WR": 2.8, "TE": 2.8, "DST": 0.0},
            "team_caps": {"WR": 3, "TE": 3, "RB": 3},
            "positions": {
                "QB": {"top": 10, "min_score": 14.0, "min_value": 2.6},
                "RB": {"top": 18, "min_score": 8.5, "min_value": 3.0},
                "WR": {"top": 28, "min_score": 7.0, "min_value": 3.3},
                "TE": {"top": 14, "min_score": 6.0, "min_value": 3.1},
                "DST": {"top": 10, "min_score": 5.0, "min_value": 0.0},
            },
        }
        gpp_cfg = {
            "score_field": "p90",
            "value_floor": {"default": 3.0, "WR": 3.4, "TE": 3.4, "DST": 0.0},
            "team_caps": {"WR": 4, "TE": 3, "RB": 2},
            "positions": {
                "QB": {"top": 14, "min_score": 17.0, "min_value": 3.0},
                "RB": {"top": 20, "min_score": 11.0, "min_value": 3.0},
                "WR": {"top": 34, "min_score": 10.0, "min_value": 3.4},
                "TE": {"top": 16, "min_score": 8.0, "min_value": 3.4},
                "DST": {"top": 12, "min_score": 0.0, "min_value": 0.0},
            },
        }
        cfg = cash_cfg if mode == "cash" else gpp_cfg
        sort_field = cfg["score_field"]

        filtered_parts = []
        for pos, group in df.groupby("position"):
            pos_cfg = cfg["positions"].get(pos)
            if not pos_cfg:
                filtered_parts.append(group)
                continue
            base = group.sort_values(sort_field, ascending=False).head(pos_cfg["top"])
            threshold = pos_cfg["min_score"]
            value_floor = cfg["value_floor"].get(pos, cfg["value_floor"]["default"])
            if mode == "cash":
                base = base[(base[sort_field] >= threshold) | (base["ceil_per_k"] >= pos_cfg["min_value"])]
            else:
                base = base[(base[sort_field] >= threshold) | (base["ceil_per_k"] >= pos_cfg["min_value"])]
                if pos in {"WR", "TE"}:
                    darts = group[
                        (group["salary"] <= 4500)
                        & (group["ceil_per_k"] >= 3.4)
                    ]
                    if not darts.empty:
                        base = pd.concat([base, darts])
            base = base[base["ceil_per_k"] >= value_floor]
            filtered_parts.append(base)

        filtered = pd.concat(filtered_parts).drop_duplicates(subset=["player_id"])

        # Team caps per position
        def _cap_team(group: pd.DataFrame, cap: int) -> pd.DataFrame:
            return group.sort_values("p90", ascending=False).groupby(team_field).head(cap)

        for pos, cap in cfg["team_caps"].items():
            mask = filtered["position"] == pos
            filtered = pd.concat([_cap_team(filtered[mask], cap), filtered[~mask]])

        # Stack safety: ensure QBs, pass-catchers, bring-backs, and one cheap relief piece survive filters
        rows_to_add: list[pd.DataFrame] = []
        for team, team_df in df.groupby(team_field):
            team_qb = team_df[team_df["position"] == "QB"].sort_values("p90", ascending=False)
            if not team_qb.empty and filtered[(filtered["position"] == "QB") & (filtered[team_field] == team)].empty:
                rows_to_add.append(team_qb.head(1))

            pass_catchers = (
                team_df[team_df["position"].isin(["WR", "TE"])].sort_values("p90", ascending=False).head(2)
            )
            if not pass_catchers.empty:
                rows_to_add.append(pass_catchers)

            opp_team = str(team_df["opponent_team"].dropna().iloc[0]) if not team_df["opponent_team"].dropna().empty else ""
            if opp_team:
                opp_pool = df[
                    (df[team_field] == opp_team)
                    & (df["position"].isin(["WR", "TE", "RB"]))
                ].sort_values("p90", ascending=False)
                if not opp_pool.empty:
                    rows_to_add.append(opp_pool.head(1))

            cheap_pc = (
                team_df[
                    team_df["position"].isin(["WR", "TE"]) & (team_df["salary"] <= 4000)
                ]
                .sort_values("p90", ascending=False)
                .head(1)
            )
            if not cheap_pc.empty:
                rows_to_add.append(cheap_pc)

        if rows_to_add:
            filtered = pd.concat([filtered] + rows_to_add)

        filtered = filtered.drop_duplicates(subset=["player_id"]).reset_index(drop=True)
        _log_pool_stats(filtered, "post-filter")
        dst_list = filtered[filtered["position"].isin(["DST", "D", "DEF"])]
        if not dst_list.empty:
            print("[pool:post-filter] DST candidates:\n", dst_list[["name", "player_team", "salary", "projection", "p90"]].to_string(index=False))
        return filtered

    def _solve_lineup(
        self,
        pool: pd.DataFrame,
        score_col: str = "p90",
        exposure_remaining: dict | None = None,
        exclude_lineups: List[set] | None = None,
        exclude_signatures: List[list[tuple[str, str | None]]] | None = None,
        enforce_single_te: bool = False,
        avoid_dst_opponents: bool = False,
        contest_type: str = "classic",
        stack_params: dict | None = None,
    ) -> Optional[List[dict]]:
        if pool.empty:
            return None

        # Pool is pre-filtered for min salary and exclusions upstream
        if score_col not in pool.columns:
            score_col = "projection"
        print(f"[solve] objective column={score_col}")
        pool = pool.copy()
        pool[score_col] = pd.to_numeric(pool[score_col], errors="coerce").fillna(0)
        pool["salary"] = pd.to_numeric(pool.get("salary", 0), errors="coerce").fillna(0)
        pool = pool.reset_index(drop=True)
        print(f"[solve] sample objective values:\n{pool[[score_col,'name','position','salary']].head(5).to_string(index=False)}")

        # Drop QBs that cannot meet stack/bring-back requirements to keep model feasible
        if contest_type != "captain" and bool((stack_params or {}).get("enabled", True)):
            stack_min = int(stack_params.get("stack_min", 1))
            bringback_flag = bool(stack_params.get("bringback", False))
            include_rb = bool(stack_params.get("include_rb_in_stack", False))
            pass_positions = {"WR", "TE"}
            if include_rb:
                pass_positions.add("RB")
            bringback_positions = {p.upper() for p in stack_params.get("bringback_positions", {"WR", "TE"})}
            team_field = "player_team" if "player_team" in pool.columns else "team"
            pool[team_field] = pool[team_field].astype(str).str.upper()
            pool["opponent_team"] = pool.get("opponent_team", "").astype(str).str.upper()
            keep_idxs = []
            for i in pool.index:
                if pool.loc[i, "position"] != "QB":
                    keep_idxs.append(i)
                    continue
                team = str(pool.loc[i, team_field]).upper()
                opp = str(pool.loc[i, "opponent_team"]).upper()
                team_stack = pool[(pool[team_field] == team) & (pool["position"].isin(pass_positions)) & (pool.index != i)]
                if len(team_stack) < stack_min:
                    continue
                if bringback_flag:
                    if not opp:
                        continue
                    bb = pool[(pool[team_field] == opp) & (pool["position"].isin(bringback_positions))]
                    if bb.empty:
                        continue
                keep_idxs.append(i)
            pool = pool.loc[keep_idxs].reset_index(drop=True)

        index_range = range(len(pool))
        contest_type = (contest_type or "classic").lower()
        params = stack_params or {}

        # Captain mode (Showdown): 1 CPT (1.5x points + salary) + 5 Flex
        if contest_type == "captain":
            cap_vars = pulp.LpVariable.dicts("captain", index_range, lowBound=0, upBound=1, cat="Binary")
            flex_vars = pulp.LpVariable.dicts("flex", index_range, lowBound=0, upBound=1, cat="Binary")

            model = pulp.LpProblem("DK_Captain", pulp.LpMaximize)
            model += pulp.lpSum(
                1.5 * pool.loc[i, score_col] * cap_vars[i] + pool.loc[i, score_col] * flex_vars[i]
                for i in index_range
            )

            # Salary cap (captain costs 1.5x)
            model += pulp.lpSum(
                1.5 * pool.loc[i, "salary"] * cap_vars[i] + pool.loc[i, "salary"] * flex_vars[i] for i in index_range
            ) <= SALARY_CAP

            # Roster size: 1 CPT + 5 Flex = 6
            model += pulp.lpSum(cap_vars[i] for i in index_range) == 1
            model += pulp.lpSum(flex_vars[i] for i in index_range) == 5

            # A player can only appear once (either CPT or Flex)
            for i in index_range:
                model += cap_vars[i] + flex_vars[i] <= 1

            # Team exposure limit (DK rule allows up to 5 from one team in Showdown)
            for team, team_df in pool.groupby("player_team"):
                idx = team_df.index.tolist()
                model += pulp.lpSum(cap_vars[i] + flex_vars[i] for i in idx) <= max(TEAM_LIMIT, 5)

            # Prevent duplicate player selections if multiple rows exist for same player_id or name+team
            by_pid = {}
            for i, pid in enumerate(pool["player_id"].astype(str)):
                by_pid.setdefault(pid, []).append(i)
            for pid, idxs in by_pid.items():
                if len(idxs) > 1:
                    model += pulp.lpSum(cap_vars[i] + flex_vars[i] for i in idxs) <= 1
            by_name_team = {}
            for i in index_range:
                key = (
                    str(pool.loc[i].get("name_norm") or pool.loc[i].get("name") or pool.loc[i].get("player_name", ""))
                    .lower()
                    .strip(),
                    str(pool.loc[i].get("player_team") or pool.loc[i].get("team", "")).upper().strip(),
                )
                by_name_team.setdefault(key, []).append(i)
            for key, idxs in by_name_team.items():
                if len(idxs) > 1:
                    model += pulp.lpSum(cap_vars[i] + flex_vars[i] for i in idxs) <= 1

            # Avoid offensive players vs selected DST
            if avoid_dst_opponents:
                dst_idx = self._position_mask(pool, ["DST", "D", "DEF"])
                for d_idx in dst_idx:
                    dst_team = str(pool.loc[d_idx, "player_team"]).upper()
                    dst_opp = str(pool.loc[d_idx].get("opponent_team", "")).upper()
                    if not dst_opp:
                        continue
                    for i in index_range:
                        if i == d_idx:
                            continue
                        pos = str(pool.loc[i, "position"] if "position" in pool.columns else "").upper()
                        if pos in ("DST", "D", "DEF"):
                            continue
                        player_team = str(pool.loc[i, "player_team"]).upper()
                        if player_team == dst_opp:
                            model += cap_vars[i] + flex_vars[i] + cap_vars[d_idx] + flex_vars[d_idx] <= 1

            # Exposure caps (remaining count across multi-lineup generation)
            if exposure_remaining:
                for i in index_range:
                    pid = str(pool.loc[i, "player_id"])
                    remaining = exposure_remaining.get(pid)
                    if remaining is not None and remaining <= 0:
                        model += cap_vars[i] == 0
                        model += flex_vars[i] == 0

            # Avoid duplicate lineups
            if exclude_lineups:
                valid_idx = set(index_range)
                for lineup_indices in exclude_lineups:
                    idxs = [i for i in lineup_indices if i in valid_idx]
                    if not idxs:
                        continue
                    model += pulp.lpSum(cap_vars[i] + flex_vars[i] for i in idxs) <= len(idxs) - 1
            if exclude_signatures:
                pid_to_idx = {}
                for i, pid in enumerate(pool["player_id"].astype(str)):
                    pid_to_idx.setdefault(pid, []).append(i)
                for signature in exclude_signatures:
                    vars_in_sig = []
                    target_len = len(signature)
                    for pid, role in signature:
                        idxs = pid_to_idx.get(str(pid), [])
                        if not idxs:
                            continue
                        if role == "CPT":
                            vars_in_sig.extend([cap_vars[i] for i in idxs])
                        else:
                            vars_in_sig.extend([flex_vars[i] for i in idxs])
                    if vars_in_sig:
                        model += pulp.lpSum(vars_in_sig) <= max(0, target_len - 1)

            solver = pulp.PULP_CBC_CMD(msg=False)
            status = model.solve(solver)
            if status != pulp.LpStatusOptimal:
                return None

            lineup_rows = []
            for i in index_range:
                selected_cap = pulp.value(cap_vars[i]) >= 0.9
                selected_flex = pulp.value(flex_vars[i]) >= 0.9
                if selected_cap or selected_flex:
                    row = pool.loc[i].to_dict()
                    row["is_captain"] = bool(selected_cap)
                    if selected_cap:
                        row["salary"] = row.get("salary", 0) * 1.5
                        row["projection"] = row.get(score_col, row.get("projection", 0)) * 1.5
                        row["p90"] = row.get(score_col, row.get("p90", 0)) * 1.5
                        row["roster_position"] = "CPT"
                    else:
                        row["projection"] = row.get(score_col, row.get("projection", 0))
                        row["p90"] = row.get(score_col, row.get("p90", 0))
                        row["roster_position"] = "FLEX"
                    lineup_rows.append(row)
            return lineup_rows

        # Decision variables
        x = pulp.LpVariable.dicts("player", index_range, lowBound=0, upBound=1, cat="Binary")

        model = pulp.LpProblem("DK_Lineup", pulp.LpMaximize)
        model += pulp.lpSum(pool.loc[i, score_col] * x[i] for i in index_range)

        # Salary cap
        model += pulp.lpSum(pool.loc[i, "salary"] * x[i] for i in index_range) <= SALARY_CAP

        # Roster size
        model += pulp.lpSum(x[i] for i in index_range) == 9

        # Position constraints
        qb_idx = self._position_mask(pool, ["QB"])
        rb_idx = self._position_mask(pool, ["RB"])
        wr_idx = self._position_mask(pool, ["WR"])
        te_idx = self._position_mask(pool, ["TE"])
        dst_idx = self._position_mask(pool, ["DST", "D", "DEF"])

        model += pulp.lpSum(x[i] for i in qb_idx) == 1
        model += pulp.lpSum(x[i] for i in dst_idx) == 1
        model += pulp.lpSum(x[i] for i in rb_idx) >= 2
        model += pulp.lpSum(x[i] for i in wr_idx) >= 3
        model += pulp.lpSum(x[i] for i in te_idx) >= 1
        if enforce_single_te:
            model += pulp.lpSum(x[i] for i in te_idx) <= 1

        # Team exposure limit
        for team, team_df in pool.groupby("player_team"):
            idx = team_df.index.tolist()
            model += pulp.lpSum(x[i] for i in idx) <= TEAM_LIMIT

        # Avoid offensive players vs selected DST
        if avoid_dst_opponents and dst_idx:
            for d_idx in dst_idx:
                dst_team = str(pool.loc[d_idx, "player_team"]).upper()
                dst_opp = str(pool.loc[d_idx].get("opponent_team", "")).upper()
                if not dst_opp:
                    continue
                for i in index_range:
                    if i == d_idx:
                        continue
                    pos = str(pool.loc[i, "position"] if "position" in pool.columns else "").upper()
                    if pos in ("DST", "D", "DEF"):
                        continue
                    player_team = str(pool.loc[i, "player_team"]).upper()
                    if player_team == dst_opp:
                        model += x[i] + x[d_idx] <= 1

        # Prevent duplicate player selections if multiple rows with same id
        for pid, pid_df in pool.groupby("player_id"):
            idx = pid_df.index.tolist()
            model += pulp.lpSum(x[i] for i in idx) <= 1

        # Exposure caps (remaining count for each player across multi-lineup generation)
        if exposure_remaining:
            for i in index_range:
                pid = str(pool.loc[i, "player_id"])
                remaining = exposure_remaining.get(pid)
                if remaining is not None and remaining <= 0:
                    model += x[i] == 0

        # Avoid duplicate lineups
        if exclude_lineups:
            valid_idx = set(index_range)
            for lineup_indices in exclude_lineups:
                idxs = [i for i in lineup_indices if i in valid_idx]
                if not idxs:
                    continue
                model += pulp.lpSum(x[i] for i in idxs) <= len(idxs) - 1
        if exclude_signatures:
            pid_to_idx = {}
            for i, pid in enumerate(pool["player_id"].astype(str)):
                pid_to_idx.setdefault(pid, []).append(i)
            for signature in exclude_signatures:
                idxs = []
                target_len = len(signature)
                for pid, _role in signature:
                    idxs.extend(pid_to_idx.get(str(pid), []))
                if idxs:
                    model += pulp.lpSum(x[i] for i in idxs) <= max(0, target_len - 1)

        stack_mode = "cash" if contest_type == "cash" else "gpp"
        stack_cfg = {
            "mode": stack_mode,
            "stack_min": 1 if stack_mode == "cash" else 2,
            "stack_max": None,
            "bringback": True,
            "include_rb_in_stack": False,
            "bringback_positions": ["WR", "TE"],
            **params,
        }
        stack_meta = (
            self.add_qb_stacking_constraints(model, x, pool, stack_cfg)
            if bool(stack_cfg.get("enabled", True))
            else {}
        )

        solver = pulp.PULP_CBC_CMD(msg=False)
        status = model.solve(solver)
        if status != pulp.LpStatusOptimal:
            return None

        lineup_rows = []
        for i in index_range:
            if pulp.value(x[i]) >= 0.9:
                row = pool.loc[i].to_dict()
                lineup_rows.append(row)
        if stack_meta:
            self._validate_stack_solution(lineup_rows, stack_meta)
        if lineup_rows:
            total_salary = sum(float(r.get("salary", 0) or 0) for r in lineup_rows)
            total_obj = sum(float(r.get(score_col, 0) or 0) for r in lineup_rows)
            print(f"[solve] total salary used={total_salary}, total {score_col}={total_obj}")
            print("[solve] selected players:")
            for r in lineup_rows:
                print(f"  {r.get('name')} {r.get('position')} team={r.get('player_team')} opp={r.get('opponent_team')} "
                      f"salary={r.get('salary')} proj={r.get('projection')} p90={r.get('p90')}")
            qb_rows = [r for r in lineup_rows if str(r.get("position", "")).upper() == "QB"]
            if qb_rows:
                qb = qb_rows[0]
                qb_team = str(qb.get("player_team", "")).upper()
                qb_opp = str(qb.get("opponent_team", "")).upper()
                include_rb = bool(params.get("include_rb_in_stack", False))
                pass_positions = {"WR", "TE"}
                if include_rb:
                    pass_positions.add("RB")
                same_team = [r for r in lineup_rows if str(r.get("player_team", "")).upper() == qb_team and str(r.get("position", "")).upper() in pass_positions and r is not qb]
                bringback_positions = {p.upper() for p in params.get("bringback_positions", {"WR", "TE"})}
                bringbacks = [r for r in lineup_rows if str(r.get("player_team", "")).upper() == qb_opp and str(r.get("position", "")).upper() in bringback_positions]
                print(f"[solve] QB={qb.get('name')} team={qb_team} opp={qb_opp} stack_count={len(same_team)} bringbacks={len(bringbacks)}")
        return lineup_rows

    def run_job(
        self,
        season: int,
        week: int,
        slate: str,
        strategy: str,
        params: dict,
        contest_format: str | None = None,
        objective: str | None = None,
        projection_run_id: str | None = None,
        rule_run_id: str | None = None,
        data_cutoff_at: datetime | None = None,
    ) -> OptimizerJob:
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        params = dict(params or {})

        contest_format, objective, contest_type = resolve_optimizer_mode(
            contest_format=contest_format,
            objective=objective,
            params=params,
        )
        if contest_format == "classic" and objective == "cash":
            params["objective_config"] = cash_objective_config()
        stack_policy = resolve_stacking_policy(
            contest_format=contest_format,
            objective=objective,
            params=params,
        )
        params["stack_policy_id"] = stack_policy["policy_id"]
        params["stack_policy"] = stack_policy
        projection_run_id, rule_run_id, data_cutoff_at = self._resolve_run_lineage(
            season=season,
            week=week,
            slate=slate,
            projection_run_id=projection_run_id,
            rule_run_id=rule_run_id,
            data_cutoff_at=data_cutoff_at,
        )

        pool = self._load_player_pool(
            season,
            week,
            slate,
            projection_run_id=projection_run_id,
        )
        simulation_result = None
        if contest_format == "classic" and objective == "gpp" and not pool.empty:
            try:
                simulation_result = SimulationService(engine=self.engine).fetch_latest(
                    season=season,
                    week=week,
                    slate=slate,
                    contest_format="classic",
                    projection_run_id=projection_run_id,
                )
            except Exception as exc:  # noqa: BLE001 - simulation is optional optimizer evidence
                logger.info("DT-502 simulation lookup unavailable: %s", exc)
            if simulation_result is not None:
                pool = _merge_simulation_evidence(pool, simulation_result.rows)
                params["simulation_run_id"] = simulation_result.simulation_run_id
                params["simulation_model_id"] = simulation_result.simulation_model_id
                params["simulation_seed"] = simulation_result.seed
        # Enforce minimum salary floor
        if not pool.empty:
            pool = pool.copy()
            pool["salary"] = pd.to_numeric(pool.get("salary", 0), errors="coerce")
            pool = pool[pool["salary"] >= MIN_SALARY]
            pool = pool.reset_index(drop=True)
        # Optional hard exclusions by player name/id passed in params
        exclude_names = {
            str(name).lower().strip(): str(name).lower().strip()
            for name in params.get("exclude_players", [])
            if str(name).strip()
        }
        exclude_ids = {str(pid) for pid in params.get("exclude_player_ids", []) if str(pid).strip()}
        exclusions_present = bool(exclude_names or exclude_ids)
        if not pool.empty and exclusions_present:
            pool = pool.copy()
            if "name_norm" not in pool.columns:
                if "name" in pool.columns:
                    pool["name_norm"] = pool["name"].astype(str).str.lower().str.strip().map(_normalize_alias)
                elif "player_name" in pool.columns:
                    pool["name_norm"] = pool["player_name"].astype(str).str.lower().str.strip().map(_normalize_alias)
            pool["player_id"] = pool["player_id"].astype(str)
            name_block = {_normalize_alias(n) for n in exclude_names}
            if name_block:
                pool = pool[~pool["name_norm"].isin(name_block)]
            if exclude_ids:
                pool = pool[~pool["player_id"].isin(exclude_ids)]

        if not pool.empty and contest_type != "captain":
            pool = self._apply_pool_filters(pool, contest_type=contest_type)
        if not pool.empty and contest_format == "classic" and objective == "cash":
            pool = build_classic_cash_objective(pool)

        if pool.empty:
            lineup_results: List[List[dict]] = []
            status = "failed"
            message = "Optimizer failed: no salaries found for this slate."
        else:
            pool = pool.reset_index(drop=True)
            id_to_index = {str(pool.loc[i, "player_id"]): i for i in pool.index}
            num_lineups = max(1, int(params.get("num_lineups", 1)))
            max_exposure_raw = params.get("max_exposure", 1.0)
            try:
                max_exposure = float(max_exposure_raw)
            except Exception:  # noqa: BLE001
                max_exposure = 1.0
            if max_exposure > 1.0:
                max_exposure = max_exposure / 100.0
            max_exposure = max(0.01, min(1.0, max_exposure))
            score_col = {"cash": "cash_score", "tournament": "p90", "captain": "p90"}.get(contest_type, "p90")
            if contest_format == "classic" and objective == "gpp":
                pool["gpp_score"] = pd.to_numeric(pool["p90"], errors="coerce").fillna(0.0)
                if simulation_result is not None:
                    leverage_weight = float(params.get("leverage_weight", 0.25))
                    pool["gpp_score"] += leverage_weight * pd.to_numeric(
                        pool["leverage_score"], errors="coerce"
                    ).fillna(0.0)
                    params["leverage_weight"] = leverage_weight
                score_col = "gpp_score"
            enforce_single_te = bool(params.get("enforce_single_te", False))
            avoid_dst_opponents = bool(params.get("avoid_dst_opponents", False))
            stack_cfg = dict(stack_policy)

            def _run_baseline() -> tuple[list[list[dict]], str, str]:
                exposure_limit = max(1, int(math.ceil(num_lineups * max_exposure)))
                used_counts: dict[str, int] = {}
                exclude_lineups: List[set] = []
                exclude_signatures: List[list[tuple[str, str | None]]] = []
                lineup_results_local: List[List[dict]] = []

                for _ in range(num_lineups):
                    remaining = {pid: exposure_limit - used_counts.get(pid, 0) for pid in pool["player_id"].astype(str)}
                    lineup = self._solve_lineup(
                        pool,
                        score_col=score_col,
                        exposure_remaining=remaining,
                        exclude_lineups=exclude_lineups,
                        exclude_signatures=exclude_signatures,
                        enforce_single_te=enforce_single_te,
                        avoid_dst_opponents=avoid_dst_opponents,
                        contest_type=contest_type,
                        stack_params=stack_cfg,
                    )
                    if not lineup:
                        break
                    lineup_indices = {id_to_index[str(row.get("player_id"))] for row in lineup if str(row.get("player_id")) in id_to_index}
                    # Update counts and exclusion set
                    for row in lineup:
                        pid = str(row.get("player_id"))
                        used_counts[pid] = used_counts.get(pid, 0) + 1
                    signature = []
                    for row in lineup:
                        pid = str(row.get("player_id"))
                        role = str(row.get("roster_position") or "").upper() if contest_type == "captain" else None
                        signature.append((pid, role))
                    lineup_results_local.append(lineup)
                    if lineup_indices:
                        exclude_lineups.append(lineup_indices)
                    if signature:
                        exclude_signatures.append(signature)

                status_local = "completed" if lineup_results_local else "failed"
                if status_local == "completed":
                    message_local = (
                        f"Optimizer completed: {len(lineup_results_local)} lineup(s) "
                        f"generated (mode={contest_type}, max exposure={max_exposure:.2f})"
                    )
                    if contest_format == "classic" and objective == "cash":
                        message_local += f" using {CASH_OBJECTIVE_ID}"
                    message_local += f"; stack policy={stack_policy['policy_id']}"
                else:
                    message_local = "Optimizer failed to find lineup (check salaries/projections)."
                return lineup_results_local, status_local, message_local

            lineup_results: List[List[dict]] = []
            status: str
            message: str

            # Alternate strategy: slate-aware GPP optimizer
            # Disable GPP pipeline when stack/bring-back enforcement is required; baseline path enforces constraints.
            use_gpp = False
            if use_gpp:
                try:
                    gpp_result = run_gpp_pipeline(
                        season=season,
                        week=week,
                        slate=slate,
                        num_lineups=num_lineups,
                        engine=self.engine,
                    )
                    lineup_results = [
                        [self._gpp_player_to_dict(p) for p in lineup] for lineup in gpp_result.lineups
                    ]
                    status = gpp_result.status
                    message = gpp_result.message
                except Exception as exc:  # noqa: BLE001
                    lineup_results = []
                    status = "failed"
                    message = f"GPP optimizer failed: {exc}"
            else:
                lineup_results, status, message = _run_baseline()

            # Validate stacks/bring-backs for any lineups produced
            if lineup_results:
                ok, reason = self._lineups_satisfy_stack(lineup_results, stack_cfg, contest_type)
                if not ok:
                    if use_gpp:
                        # Try baseline as fallback
                        lineup_results, status, message = _run_baseline()
                        if lineup_results:
                            ok, reason = self._lineups_satisfy_stack(lineup_results, stack_cfg, contest_type)
                    if not ok:
                        status = "failed"
                        message = f"Stack/bring-back validation failed: {reason}"
                        lineup_results = []

            if status == "completed" and lineup_results:
                for lineup in lineup_results:
                    for row in lineup:
                        row["lineup_stack_policy"] = dict(stack_policy)
                if contest_format == "classic" and objective == "cash":
                    missing_projection_count = 0
                    for lineup in lineup_results:
                        lineup_summary = summarize_classic_cash_lineup(lineup)
                        missing_projection_count += len(
                            lineup_summary.get("missing_projection_players", [])
                        )
                        for row in lineup:
                            row["lineup_cash_summary"] = lineup_summary
                    if missing_projection_count:
                        message += (
                            f"; {missing_projection_count} selected player input(s) "
                            "have no projection evidence"
                        )
                self._attach_symbolic_explanations(
                    lineups=lineup_results,
                    season=season,
                    week=week,
                    slate=slate,
                )

        job = OptimizerJob(
            job_id=job_id,
            status=status,
            created_at=now,
            updated_at=now,
            season=season,
            week=week,
            slate=slate,
            strategy=strategy,
            contest_format=contest_format,
            objective=objective,
            params=params,
            projection_run_id=projection_run_id,
            rule_run_id=rule_run_id,
            data_cutoff_at=data_cutoff_at,
            results=lineup_results if status == "completed" else None,
            message=message,
        )
        self._jobs[job_id] = job
        job.lineage_persisted = self._persist_optimizer_run(job)

        # Persist results if found (skip captain showdown to avoid schema churn). Disabled by default to avoid
        # schema mismatches; set params.persist_results=True to enable.
        persist_results = bool(params.get("persist_results", False))
        if persist_results and lineup_results and contest_type != "captain":
            try:
                all_rows = []
                for idx, lineup in enumerate(lineup_results, start=1):
                    for row in lineup:
                        row["lineup_number"] = idx
                        all_rows.append(row)
                df = pd.DataFrame(all_rows)
                df["job_id"] = job_id
                with self.engine.begin() as connection:
                    ensure_table_columns(self.engine, "dk_optimizer", df)
                    try:
                        connection.execute(
                            text("DELETE FROM dk_optimizer WHERE job_id = :job_id"),
                            {"job_id": job_id},
                        )
                    except ProgrammingError:
                        # Column may not exist yet; proceed after schema ensured
                        pass
                    df.to_sql("dk_optimizer", connection, if_exists="append", index=False)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to persist optimizer results: %s", exc)
        return job

    def get_job(self, job_id: str) -> OptimizerJob | None:
        return self._jobs.get(job_id) or self._load_persisted_job(job_id)


def toy_slate_test() -> dict:
    """
    Tiny slate harness to exercise stacking constraints for cash vs. gpp.
    Returns a dict with solved lineups for inspection.
    """
    players = [
        # Team AAA (vs BBB)
        {"player_id": "QB_AAA", "name": "QB AAA", "position": "QB", "player_team": "AAA", "opponent_team": "BBB", "salary": 7000, "projection": 20, "p90": 22},
        {"player_id": "RB_AAA", "name": "RB AAA", "position": "RB", "player_team": "AAA", "opponent_team": "BBB", "salary": 6000, "projection": 15, "p90": 17},
        {"player_id": "WR_AAA1", "name": "WR AAA1", "position": "WR", "player_team": "AAA", "opponent_team": "BBB", "salary": 5500, "projection": 14, "p90": 17},
        {"player_id": "WR_AAA2", "name": "WR AAA2", "position": "WR", "player_team": "AAA", "opponent_team": "BBB", "salary": 5000, "projection": 13, "p90": 15},
        {"player_id": "TE_AAA", "name": "TE AAA", "position": "TE", "player_team": "AAA", "opponent_team": "BBB", "salary": 4000, "projection": 9, "p90": 11},
        # Team BBB (vs AAA) - bring-backs
        {"player_id": "RB_BBB", "name": "RB BBB", "position": "RB", "player_team": "BBB", "opponent_team": "AAA", "salary": 5200, "projection": 12, "p90": 14},
        {"player_id": "WR_BBB1", "name": "WR BBB1", "position": "WR", "player_team": "BBB", "opponent_team": "AAA", "salary": 5200, "projection": 13, "p90": 15},
        {"player_id": "WR_BBB2", "name": "WR BBB2", "position": "WR", "player_team": "BBB", "opponent_team": "AAA", "salary": 4200, "projection": 10, "p90": 12},
        {"player_id": "TE_BBB", "name": "TE BBB", "position": "TE", "player_team": "BBB", "opponent_team": "AAA", "salary": 3800, "projection": 8, "p90": 10},
        # DST options
        {"player_id": "DST_AAA", "name": "DST AAA", "position": "DST", "player_team": "AAA", "opponent_team": "BBB", "salary": 3000, "projection": 7, "p90": 7},
        {"player_id": "DST_BBB", "name": "DST BBB", "position": "DST", "player_team": "BBB", "opponent_team": "AAA", "salary": 3000, "projection": 7, "p90": 7},
    ]
    pool = pd.DataFrame(players)
    svc = OptimizerService(connection_string="sqlite:///:memory:")

    cash_lineup = svc._solve_lineup(
        pool,
        score_col="projection",
        contest_type="cash",
        stack_params={"stack_min": 1, "stack_max": None, "bringback": False, "include_rb_in_stack": False, "bringback_positions": ["WR", "TE"]},
    )
    gpp_lineup = svc._solve_lineup(
        pool,
        score_col="p90",
        contest_type="tournament",
        stack_params={"stack_min": 2, "stack_max": None, "bringback": True, "include_rb_in_stack": False, "bringback_positions": ["WR", "TE"]},
    )
    return {"cash": cash_lineup, "gpp": gpp_lineup}
