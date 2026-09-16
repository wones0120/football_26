"""Lineup optimizer using PuLP ILP."""

from __future__ import annotations

import uuid
import math
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
import logging

import pandas as pd
import numpy as np
import pulp
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import ProgrammingError, ResourceClosedError

from Database.config import get_connection_string
from Database.operations import ensure_table_columns
from ..config import get_settings
from .gpp_optimizer import run_gpp_pipeline, Player as GPPPlayer, GPPOptimizerResult
from .optimizer_control import solve_control, build_comparison
from .point_in_time import injury_snapshot_cutoff_sql
from .player_pool_safety import (
    ExclusionCategory,
    categorize_exclusion_reason,
    evaluate_player_pool_safety,
    has_explicit_specialty_role,
    normalize_canonical_player_ids,
)
from .player_context_scoring import score_player_context
from .lineup_correlation_scoring import (
    LINEUP_CORRELATION_LIBRARY_ID,
    LINEUP_CORRELATION_LIBRARY_VERSION,
    add_format_specific_objective,
    add_lineup_correlation_objective,
    build_format_specific_terms,
    build_lineup_correlation_terms,
    score_lineup_correlations,
)
from .rule_library import StrategyProfile, resolve_strategy_profile
from .salary_eligibility import INELIGIBLE_SALARY_STATUSES_SQL
from .simulations import SimulationService
from .target_schema import validate_target_schema


VALID_CONTEST_FORMATS = {"classic", "showdown"}
VALID_OPTIMIZER_OBJECTIVES = {"cash", "gpp"}
CASH_OBJECTIVE_ID = "classic_cash_v1"
CLASSIC_CASH_STACK_UNCONSTRAINED_ID = "classic_cash_unconstrained_v1"
CLASSIC_CASH_STACK_QB_PAIR_ID = "classic_cash_qb_pair_v1"
CLASSIC_CASH_STACK_QB_PAIR_BRINGBACK_ID = "classic_cash_qb_pair_bringback_v1"
CLASSIC_GPP_STACK_LEGACY_ID = "classic_gpp_double_bringback_v1"
CLASSIC_GPP_BASELINE_STRATEGY_ID = "classic_gpp_baseline_v1"
CLASSIC_GPP_ADVANCED_STRATEGY_ID = "classic_gpp_slate_aware_v1"
CLASSIC_HEAD_TO_HEAD_STRATEGY_ID = "classic_head_to_head_v1"
CLASSIC_LARGE_GPP_STRATEGY_ID = "classic_large_gpp_v1"
SHOWDOWN_CASH_BASELINE_STRATEGY_ID = "showdown_cash_baseline_v1"
SHOWDOWN_CASH_QB_CAPTAIN_STACK_STRATEGY_ID = (
    "showdown_cash_qb_captain_stack_v1"
)
SHOWDOWN_GPP_BASELINE_STRATEGY_ID = "showdown_gpp_baseline_v1"
SHOWDOWN_GPP_CAPTAIN_INFORMED_V1_STRATEGY_ID = (
    "showdown_gpp_captain_informed_v1"
)
SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID = (
    "showdown_gpp_portfolio_v3"
)
SHOWDOWN_GPP_CAPTAIN_INFORMED_V2_STRATEGY_ID = "showdown_gpp_captain_informed_v2"
SHOWDOWN_SINGLE_ENTRY_GPP_STRATEGY_ID = "showdown_single_entry_gpp"
SHOWDOWN_SINGLE_ENTRY_PORTFOLIO_STRATEGY_ID = "showdown_single_entry_portfolio"
SHOWDOWN_SINGLE_ENTRY_STRATEGY_IDS = frozenset({
    SHOWDOWN_SINGLE_ENTRY_GPP_STRATEGY_ID,
    SHOWDOWN_SINGLE_ENTRY_PORTFOLIO_STRATEGY_ID,
})
SHOWDOWN_QB_CAPTAIN_RECEIVER_RULE_ID = (
    "showdown_qb_captain_same_team_wr_te_v1"
)
SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_IDS = frozenset(
    {
        SHOWDOWN_GPP_CAPTAIN_INFORMED_V1_STRATEGY_ID,
        SHOWDOWN_GPP_CAPTAIN_INFORMED_V2_STRATEGY_ID,
        SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID,
        *SHOWDOWN_SINGLE_ENTRY_STRATEGY_IDS,
    }
)


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
class HeadToHeadObjectiveConfig:
    objective_id: str = CLASSIC_HEAD_TO_HEAD_STRATEGY_ID
    mean_weight: float = 0.75
    ceiling_weight: float = 0.20
    floor_weight: float = 0.05
    fragile_punt_salary: int = 3500
    fragile_punt_mean: float = 5.0
    fragile_punt_penalty: float = 0.5
    correlation_bonus: float = 0.05


DEFAULT_HEAD_TO_HEAD_OBJECTIVE = HeadToHeadObjectiveConfig()


@dataclass(frozen=True)
class OptimizerStrategyConfig:
    strategy_id: str
    version: str
    contest_format: str
    objective: str
    engine: str
    evidence_status: str
    description: str


OPTIMIZER_STRATEGIES = {
    CLASSIC_HEAD_TO_HEAD_STRATEGY_ID: OptimizerStrategyConfig(
        strategy_id=CLASSIC_HEAD_TO_HEAD_STRATEGY_ID,
        version="v1",
        contest_format="classic",
        objective="cash",
        engine="head_to_head_ilp",
        evidence_status="explicit_contest_strategy",
        description=(
            "Head-to-Head: broad eligible pool with a mean-dominant objective, "
            "secondary ceiling/floor value, and no required game stack."
        ),
    ),
    CLASSIC_LARGE_GPP_STRATEGY_ID: OptimizerStrategyConfig(
        strategy_id=CLASSIC_LARGE_GPP_STRATEGY_ID,
        version="v1",
        contest_format="classic",
        objective="gpp",
        engine="large_gpp_portfolio",
        evidence_status="explicit_contest_strategy",
        description=(
            "Large GPP: ceiling-weighted portfolio optimization with flexible "
            "QB stacks, optional bring-backs, uniqueness, and exposure controls."
        ),
    ),
    CLASSIC_GPP_BASELINE_STRATEGY_ID: OptimizerStrategyConfig(
        strategy_id=CLASSIC_GPP_BASELINE_STRATEGY_ID,
        version="v1",
        contest_format="classic",
        objective="gpp",
        engine="legacy_ilp",
        evidence_status="production_baseline",
        description="Current classic GPP P90/leverage ILP with the legacy double-stack policy.",
    ),
    CLASSIC_GPP_ADVANCED_STRATEGY_ID: OptimizerStrategyConfig(
        strategy_id=CLASSIC_GPP_ADVANCED_STRATEGY_ID,
        version="v1",
        contest_format="classic",
        objective="gpp",
        engine="slate_aware_gpp",
        evidence_status="explicit_candidate",
        description=(
            "Slate-aware classic GPP portfolio optimizer with ownership templates, "
            "correlation bonuses, leverage, uniqueness, and exposure controls."
        ),
    ),
    SHOWDOWN_CASH_BASELINE_STRATEGY_ID: OptimizerStrategyConfig(
        strategy_id=SHOWDOWN_CASH_BASELINE_STRATEGY_ID,
        version="v1",
        contest_format="showdown",
        objective="cash",
        engine="captain_ilp",
        evidence_status="initial_policy_unvalidated",
        description=(
            "Persistent Showdown cash contract using the basic one-captain, "
            "five-flex mean/stability solver using the Showdown cash profile."
        ),
    ),
    SHOWDOWN_CASH_QB_CAPTAIN_STACK_STRATEGY_ID: OptimizerStrategyConfig(
        strategy_id=SHOWDOWN_CASH_QB_CAPTAIN_STACK_STRATEGY_ID,
        version="v1",
        contest_format="showdown",
        objective="cash",
        engine="captain_ilp",
        evidence_status="user_required",
        description=(
            "Showdown cash mean/stability solver requiring a same-team WR or TE in FLEX "
            "whenever the captain is a quarterback."
        ),
    ),
    SHOWDOWN_GPP_BASELINE_STRATEGY_ID: OptimizerStrategyConfig(
        strategy_id=SHOWDOWN_GPP_BASELINE_STRATEGY_ID,
        version="v1",
        contest_format="showdown",
        objective="gpp",
        engine="captain_ilp",
        evidence_status="basic_p90_baseline",
        description=(
            "Persistent Showdown GPP contract using the basic one-captain, "
            "five-flex P90 solver pending DT-605 objective research."
        ),
    ),
    SHOWDOWN_GPP_CAPTAIN_INFORMED_V1_STRATEGY_ID: OptimizerStrategyConfig(
        strategy_id=SHOWDOWN_GPP_CAPTAIN_INFORMED_V1_STRATEGY_ID,
        version="v1",
        contest_format="showdown",
        objective="gpp",
        engine="captain_informed_ilp",
        evidence_status="production_validated",
        description=(
            "Showdown GPP P90 solver with starter-QB eligibility and the validated "
            "captain-position prior (0.35 strength; 39-slate paired evaluation)."
        ),
    ),
    SHOWDOWN_GPP_CAPTAIN_INFORMED_V2_STRATEGY_ID: OptimizerStrategyConfig(
        strategy_id=SHOWDOWN_GPP_CAPTAIN_INFORMED_V2_STRATEGY_ID,
        version="v2",
        contest_format="showdown",
        objective="gpp",
        engine="captain_informed_ilp",
        evidence_status="production_validated_plus_user_rule",
        description=(
            "Showdown GPP P90 solver with starter-QB eligibility, the validated "
            "captain-position prior, and a same-team WR/TE requirement for QB captains."
        ),
    ),
    SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID: OptimizerStrategyConfig(
        strategy_id=SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID,
        version="v3",
        contest_format="showdown",
        objective="gpp",
        engine="captain_informed_ilp",
        evidence_status="user_required_portfolio_policy",
        description=(
            "Five-entry Showdown GPP portfolio solver with role-specific exposure, "
            "hard quarterback correlations, opportunity eligibility, quality floors, "
            "role-specific ownership, and intentional game-script diversity."
        ),
    ),
    **{
        strategy_id: OptimizerStrategyConfig(
            strategy_id=strategy_id,
            version="v1",
            contest_format="showdown",
            objective="gpp",
            engine="single_entry_candidate_selector",
            evidence_status="heuristic_unvalidated",
            description="Showdown single-entry GPP candidate selection without cross-contest exposure limits.",
        )
        for strategy_id in SHOWDOWN_SINGLE_ENTRY_STRATEGY_IDS
    },
}


def showdown_optimizer_rules(strategy: str) -> list[dict]:
    """Return hard Showdown construction rules owned by one strategy version."""
    if strategy not in {
        SHOWDOWN_CASH_QB_CAPTAIN_STACK_STRATEGY_ID,
        SHOWDOWN_GPP_CAPTAIN_INFORMED_V2_STRATEGY_ID,
        SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID,
        *SHOWDOWN_SINGLE_ENTRY_STRATEGY_IDS,
    }:
        return []
    rules = [] if strategy in ({SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID} | SHOWDOWN_SINGLE_ENTRY_STRATEGY_IDS) else [
        {
            "rule_id": SHOWDOWN_QB_CAPTAIN_RECEIVER_RULE_ID,
            "rule_type": "hard_constraint",
            "trigger": {"captain_position": "QB"},
            "requirement": {
                "minimum": 1,
                "roster_position": "FLEX",
                "same_team": True,
                "positions": ["WR", "TE"],
            },
            "source": "user_required",
        }
    ]
    if strategy == SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID or strategy in SHOWDOWN_SINGLE_ENTRY_STRATEGY_IDS:
        rules.extend(
            [
                {"rule_id": "showdown_require_starting_qb_v1", "rule_type": "hard_constraint", "trigger": {"portfolio_size_max": 5}, "requirement": {"minimum_starting_qbs": 1}, "source": "user_required"},
                {"rule_id": "showdown_pass_catcher_captain_qb_v1", "rule_type": "hard_constraint", "trigger": {"captain_positions": ["WR", "TE"]}, "requirement": {"same_team_starting_qb": True}, "source": "user_required"},
                {"rule_id": "showdown_multi_pass_catcher_qb_v1", "rule_type": "hard_constraint", "trigger": {"same_team_wr_te_minimum": 2}, "requirement": {"same_team_starting_qb": True}, "source": "user_required"},
                {"rule_id": "showdown_qb_captain_role_stack_v1", "rule_type": "hard_constraint", "trigger": {"captain_position": "QB"}, "requirement": {"pocket_qb_wr_te": 2, "high_rushing_qb_wr_te": 1}, "source": "user_required"},
                {"rule_id": "showdown_low_opportunity_skill_gate_v2", "rule_type": "hard_exclusion", "trigger": {"positions": ["RB", "WR", "TE"], "legacy_salary_max": 1000, "legacy_projection_below": 3, "legacy_p90_below": 10, "fallback_salary_max": 2000, "fallback_projection_below": 2, "fallback_p90_below": 8, "opportunity_path": False}, "source": "user_required"},
            ]
        )
    return rules


def resolve_optimizer_strategy(
    *,
    contest_format: str,
    objective: str,
    strategy: str,
) -> dict:
    """Resolve an explicit, versioned engine selection for the requested mode."""
    requested = str(strategy or "").strip().lower()
    if not requested:
        raise ValueError("strategy must be a non-empty optimizer strategy ID")

    rule_profile = resolve_strategy_profile(
        contest_format=contest_format,
        objective=objective,
    )

    def with_rule_profile(payload: dict) -> dict:
        payload["rule_profile_id"] = rule_profile.profile_id
        payload["rule_profile"] = rule_profile.to_dict()
        return payload

    if contest_format == "classic" and objective in {"cash", "gpp"}:
        source = "explicit"
        if objective == "cash" and requested in {"baseline", "gpp"}:
            return with_rule_profile(
                {
                    "strategy_id": requested,
                    "version": "legacy",
                    "contest_format": contest_format,
                    "objective": objective,
                    "engine": "legacy_ilp",
                    "evidence_status": "legacy_mode_contract",
                    "description": "Historical classic cash optimizer contract.",
                    "source": "legacy_alias",
                }
            )
        if objective == "cash" and requested in {"cash", "h2h", "head_to_head"}:
            requested = CLASSIC_HEAD_TO_HEAD_STRATEGY_ID
            source = "legacy_alias"
        elif objective == "gpp" and requested in {"gpp", "baseline"}:
            requested = CLASSIC_GPP_BASELINE_STRATEGY_ID
            source = "legacy_alias"
        config = OPTIMIZER_STRATEGIES.get(requested)
        if (
            config is None
            or config.contest_format != contest_format
            or config.objective != objective
        ):
            raise ValueError(
                "strategy must be one of: "
                + ", ".join(
                    sorted(
                        strategy_id
                        for strategy_id, strategy_config in OPTIMIZER_STRATEGIES.items()
                        if strategy_config.contest_format == contest_format
                        and strategy_config.objective == objective
                    )
                )
                + f" for classic {objective}"
            )
        resolved = asdict(config)
        resolved["source"] = source
        return with_rule_profile(resolved)

    if contest_format == "showdown":
        source = "explicit"
        if requested == "baseline":
            requested = (
                SHOWDOWN_CASH_BASELINE_STRATEGY_ID
                if objective == "cash"
                else SHOWDOWN_GPP_BASELINE_STRATEGY_ID
            )
            source = "legacy_alias"
        elif requested in {"gpp", "captain"}:
            requested = (
                SHOWDOWN_CASH_QB_CAPTAIN_STACK_STRATEGY_ID
                if objective == "cash"
                else SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID
            )
            source = "legacy_alias"
        config = OPTIMIZER_STRATEGIES.get(requested)
        if (
            config is None
            or config.contest_format != contest_format
            or config.objective != objective
        ):
            valid_strategies = sorted(
                strategy_id
                for strategy_id, candidate in OPTIMIZER_STRATEGIES.items()
                if candidate.contest_format == contest_format
                and candidate.objective == objective
            )
            raise ValueError(
                "strategy must be one of: "
                + ", ".join(valid_strategies)
                + f" for showdown {objective}"
            )
        resolved = asdict(config)
        resolved["source"] = source
        return with_rule_profile(resolved)

    if requested in OPTIMIZER_STRATEGIES:
        raise ValueError(
            f"strategy {requested} is not valid for {contest_format} {objective}"
        )
    return with_rule_profile(
        {
            "strategy_id": requested,
            "version": "legacy",
            "contest_format": contest_format,
            "objective": objective,
            "engine": "legacy_ilp",
            "evidence_status": "legacy_mode_contract",
            "description": "Existing optimizer engine for this format/objective mode.",
            "source": "request",
        }
    )


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


def build_showdown_cash_objective(pool: pd.DataFrame) -> pd.DataFrame:
    """Apply the declared cash profile to player distributions before CPT scaling."""
    frame = pool.copy()
    weights = resolve_strategy_profile(contest_format="showdown", objective="cash").objective_weights
    mean = pd.to_numeric(frame["projection"], errors="coerce").fillna(0.0)
    score = mean * 0.0
    components = {}
    for component, column in (("mean", "projection"), ("median", "predicted_p50"),
                              ("floor", "predicted_p10"), ("ceiling", "p90")):
        values = pd.to_numeric(frame[column], errors="coerce").fillna(mean) if column in frame else mean
        components[component] = values * weights.get(component, 0.0)
        score += components[component]
    context = pd.to_numeric(frame.get("optimizer_context_adjustment", mean * 0.0), errors="coerce").fillna(0.0)
    frame["showdown_cash_score"] = score + context
    frame["showdown_cash_objective_explanation"] = [
        {"objective_id": "showdown_cash_distribution_v1", "weights": dict(weights),
         "components": {key: float(value.loc[index]) for key, value in components.items()},
         "context_adjustment": float(context.loc[index]), "score": float(frame.loc[index, "showdown_cash_score"])}
        for index in frame.index
    ]
    return frame


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


def head_to_head_objective_config(
    config: HeadToHeadObjectiveConfig = DEFAULT_HEAD_TO_HEAD_OBJECTIVE,
) -> dict:
    """Return the persisted, versioned Head-to-Head objective contract."""
    return asdict(config)


def build_head_to_head_objective(
    pool: pd.DataFrame,
    config: HeadToHeadObjectiveConfig = DEFAULT_HEAD_TO_HEAD_OBJECTIVE,
) -> pd.DataFrame:
    """Add a mean-dominant H2H score without hard-pruning legitimate starters."""
    if pool.empty:
        return pool.copy()
    frame = pool.copy()
    mean = pd.to_numeric(frame.get("projection", 0.0), errors="coerce").fillna(0.0)
    ceiling = pd.to_numeric(
        frame.get("p90", frame.get("predicted_p90", mean)), errors="coerce"
    ).fillna(mean)
    floor = pd.to_numeric(
        frame.get("predicted_p10", mean), errors="coerce"
    ).fillna(mean)
    salary = pd.to_numeric(frame.get("salary", 0), errors="coerce").fillna(0.0)
    role = frame.get(
        "calibration_role", pd.Series("", index=frame.index)
    ).fillna("").astype(str).str.upper()
    fragile_punt = (
        (salary <= config.fragile_punt_salary)
        & (mean < config.fragile_punt_mean)
        & role.isin({"", "UNKNOWN", "GLOBAL", "FALLBACK", "ROTATION", "BACKUP"})
    )
    frame["h2h_objective_id"] = config.objective_id
    frame["h2h_mean"] = mean
    frame["h2h_ceiling"] = ceiling
    frame["h2h_floor"] = floor
    frame["h2h_risk"] = (mean - floor).clip(lower=0.0)
    frame["h2h_fragile_punt"] = fragile_punt.astype(bool)
    frame["h2h_fragile_punt_penalty"] = (
        fragile_punt.astype(float) * config.fragile_punt_penalty
    )
    frame["h2h_score"] = (
        config.mean_weight * mean
        + config.ceiling_weight * ceiling
        + config.floor_weight * floor
        - frame["h2h_fragile_punt_penalty"]
    )
    frame["h2h_objective_explanation"] = frame.apply(
        lambda row: {
            "objective_id": config.objective_id,
            "mean": float(row["h2h_mean"]),
            "ceiling_p90": float(row["h2h_ceiling"]),
            "floor_p10": float(row["h2h_floor"]),
            "risk": float(row["h2h_risk"]),
            "fragile_punt": bool(row["h2h_fragile_punt"]),
            "fragile_punt_penalty": float(row["h2h_fragile_punt_penalty"]),
            "h2h_score": float(row["h2h_score"]),
        },
        axis=1,
    )
    return frame


def summarize_head_to_head_lineup(lineup: list[dict]) -> dict:
    """Aggregate H2H mean, ceiling, floor, and risk for UI/persistence."""
    if not lineup:
        return {}
    projected_mean = sum(
        _safe_float(row.get("h2h_mean", row.get("projection"))) for row in lineup
    )
    projected_floor = sum(
        _safe_float(row.get("h2h_floor", row.get("predicted_p10", row.get("projection"))))
        for row in lineup
    )
    individual_ceiling_sum = sum(
        _safe_float(row.get("h2h_ceiling", row.get("p90", row.get("projection"))))
        for row in lineup
    )
    return {
        "objective_id": CLASSIC_HEAD_TO_HEAD_STRATEGY_ID,
        "player_count": len(lineup),
        "projected_mean": projected_mean,
        # Compatibility alias: this is a sum of marginal player P90 values, not a
        # jointly simulated lineup quantile.
        "projected_p90": individual_ceiling_sum,
        "projected_p90_is_joint_quantile": False,
        "individual_ceiling_sum": individual_ceiling_sum,
        "projected_floor_p10": projected_floor,
        "downside_risk": max(0.0, projected_mean - projected_floor),
        "objective_score": sum(
            _safe_float(row.get("h2h_score", row.get("projection"))) for row in lineup
        ),
        "fragile_punt_count": sum(bool(row.get("h2h_fragile_punt")) for row in lineup),
    }


def summarize_individual_ceiling_sum(lineup: list[dict]) -> dict:
    """Describe a summed player ceiling without calling it a lineup quantile."""

    return {
        "metric_id": "individual_ceiling_sum_v1",
        "label": "Individual Ceiling Sum",
        "value": sum(
            _safe_float(row.get("p90", row.get("predicted_p90", row.get("projection"))))
            for row in lineup
        ),
        "source_metric": "player_p90",
        "is_joint_quantile": False,
        "note": "Sum of player-level P90 values; not a simulated lineup P90.",
    }


def classify_showdown_game_script(lineup: list[dict]) -> dict:
    """Classify a completed Showdown lineup from its actual construction."""
    team_rows: dict[str, list[dict]] = {}
    for row in lineup:
        team = str(row.get("player_team") or row.get("team") or "").upper()
        if team:
            team_rows.setdefault(team, []).append(row)

    def _team_summary(team: str, rows: list[dict]) -> dict:
        positions = [str(row.get("position") or "").upper() for row in rows]
        pass_catchers = sum(position in {"WR", "TE"} for position in positions)
        meaningful_rbs = sum(
            position == "RB"
            and (
                _safe_float(row.get("base_projection", row.get("projection"))) >= 3
                or _safe_float(row.get("base_p90", row.get("p90"))) >= 10
                or _safe_float(row.get("base_salary", row.get("salary"))) > 1000
            )
            for row, position in zip(rows, positions)
        )
        return {
            "team": team,
            "players": len(rows),
            "quarterbacks": positions.count("QB"),
            "pass_catchers": pass_catchers,
            "meaningful_rbs": meaningful_rbs,
            "kickers": positions.count("K"),
            "defenses": sum(position in {"DST", "D", "DEF"} for position in positions),
        }

    summaries = {
        team: _team_summary(team, rows) for team, rows in sorted(team_rows.items())
    }
    material_pass_teams = [
        summary for summary in summaries.values()
        if summary["quarterbacks"] >= 1 and summary["pass_catchers"] >= 1
    ]
    if len(material_pass_teams) >= 2:
        return {
            "script_id": "shootout",
            "kind": "shootout",
            "label": "Shootout",
            "reason_codes": ["both_teams_qb_pass_catcher"],
            "team_summaries": summaries,
            "explanation": "Both offenses include a quarterback with at least one pass catcher.",
        }

    pass_led = [
        summary for summary in summaries.values()
        if summary["quarterbacks"] >= 1
        and summary["pass_catchers"] >= 2
        and summary["pass_catchers"] > summary["meaningful_rbs"]
    ]
    if pass_led:
        leader = max(
            pass_led,
            key=lambda row: (row["pass_catchers"], row["players"], row["team"]),
        )
        team = str(leader["team"])
        return {
            "script_id": f"{team}_pass_led",
            "kind": "pass_led",
            "team": team,
            "label": f"{team} pass-led",
            "reason_codes": ["starting_qb", "multiple_pass_catchers", "pass_over_run_concentration"],
            "team_summaries": summaries,
            "explanation": (
                f"{team} includes its quarterback and {leader['pass_catchers']} WR/TE, "
                f"exceeding its {leader['meaningful_rbs']} meaningful RB selections."
            ),
        }

    run_control = [
        summary for summary in summaries.values()
        if summary["players"] >= 4
        and summary["meaningful_rbs"] >= 1
        and (
            summary["meaningful_rbs"] >= 2
            or summary["kickers"] >= 1
            or summary["defenses"] >= 1
        )
    ]
    if run_control:
        leader = max(
            run_control,
            key=lambda row: (
                row["meaningful_rbs"], row["kickers"] + row["defenses"],
                row["players"], row["team"],
            ),
        )
        team = str(leader["team"])
        return {
            "script_id": f"{team}_run_control",
            "kind": "run_control",
            "team": team,
            "label": f"{team} run-control",
            "reason_codes": ["meaningful_running_back", "control_support"],
            "team_summaries": summaries,
            "explanation": (
                f"{team} has {leader['meaningful_rbs']} meaningful RB selection(s) "
                "with kicker, defense, or additional rushing support."
            ),
        }

    leader = max(
        summaries.values(), key=lambda row: (row["players"], row["team"]),
        default={"team": "UNKNOWN"},
    )
    team = str(leader["team"])
    return {
        "script_id": f"{team}_contrarian",
        "kind": "contrarian",
        "team": team,
        "label": f"Contrarian {team} script",
        "reason_codes": ["no_primary_script_match"],
        "team_summaries": summaries,
        "explanation": "The lineup does not meet the deterministic shootout, pass-led, or run-control definitions.",
    }


def summarize_showdown_portfolio_exposure(
    lineups: list[list[dict]],
    *,
    requested_lineups: int,
    exposure_rates: dict[str, float],
) -> dict:
    """Report requested-count caps alongside realized under-filled exposure."""
    generated_lineups = len(lineups)
    player_rows: dict[str, dict] = {}
    player_counts: dict[str, int] = {}
    captain_counts: dict[str, int] = {}
    for lineup in lineups:
        for row in lineup:
            player_id = str(row.get("player_id") or row.get("dk_player_id") or "")
            if not player_id:
                continue
            player_rows[player_id] = row
            player_counts[player_id] = player_counts.get(player_id, 0) + 1
            if str(row.get("roster_position") or "").upper() == "CPT":
                captain_counts[player_id] = captain_counts.get(player_id, 0) + 1

    def _report_row(player_id: str, count: int, exposure_class: str, rate: float, scope: str) -> dict:
        row = player_rows[player_id]
        maximum = max(1, int(math.ceil(max(1, requested_lineups) * rate)))
        return {
            "player_id": player_id,
            "player_name": str(row.get("player_name") or row.get("name") or player_id),
            "scope": scope,
            "exposure_class": exposure_class,
            "configured_cap": rate,
            "requested_lineups": requested_lineups,
            "maximum_allowed_appearances": maximum,
            "generated_lineups": generated_lineups,
            "actual_appearances": count,
            "final_generated_portfolio_exposure": (
                count / generated_lineups if generated_lineups else 0.0
            ),
            "cap_respected": count <= maximum,
            "cap_status": "PASS" if count <= maximum else "FAIL",
        }

    rows: list[dict] = []
    for player_id, count in sorted(
        player_counts.items(), key=lambda item: (-item[1], str(player_rows[item[0]].get("player_name") or ""))
    ):
        row = player_rows[player_id]
        exposure_class = "core"
        rate = float(exposure_rates.get("core", 0.80))
        if str(row.get("position") or "").upper() == "QB" and bool(row.get("showdown_qb_eligible")):
            exposure_class = "starting_qb"
            rate = float(exposure_rates.get("starting_qb", 1.00))
        elif _safe_float(row.get("base_salary", row.get("salary"))) <= 1000:
            exposure_class = "cheap_punt"
            rate = float(exposure_rates.get("cheap_punt", 0.40))
        rows.append(_report_row(player_id, count, exposure_class, rate, "player"))
    for player_id, count in sorted(captain_counts.items()):
        rows.append(
            _report_row(
                player_id, count, "captain",
                float(exposure_rates.get("captain", 0.60)), "captain",
            )
        )
    return {
        "policy_id": "requested_lineup_denominator_exposure_report_v1",
        "requested_lineups": requested_lineups,
        "generated_lineups": generated_lineups,
        "underfilled": generated_lineups < requested_lineups,
        "configured_captain_cap": float(exposure_rates.get("captain", 0.60)),
        "captain_maximum_appearances": max(
            1,
            int(math.ceil(
                max(1, requested_lineups) * float(exposure_rates.get("captain", 0.60))
            )),
        ),
        "rows": rows,
    }


def add_showdown_lineup_chalk_metrics(lineups: list[list[dict]]) -> list[dict]:
    """Attach slot-aware ownership products for relative lineup comparison."""
    summaries: list[dict] = []
    available_logs: list[float] = []
    for lineup in lineups:
        ownership = [row.get("ownership") for row in lineup]
        available = len(ownership) == len(lineup) and all(
            value is not None and _safe_float(value) > 0 for value in ownership
        )
        log_probability = (
            sum(math.log(min(1.0, _safe_float(value) / 100.0)) for value in ownership)
            if available else None
        )
        if log_probability is not None:
            available_logs.append(log_probability)
        summaries.append({
            "metric_id": "slot_ownership_log_product_v1",
            "ownership_available": available,
            "log_probability": log_probability,
            "probability_product": math.exp(log_probability) if log_probability is not None else None,
            "relative_chalk_score": None,
            "optimization_weight": 0.0,
            "interpretation": "Relative duplication-risk indicator; not a predicted duplicate count.",
        })
    chalkiest_log = max(available_logs, default=None)
    for lineup, summary in zip(lineups, summaries):
        if chalkiest_log is not None and summary["log_probability"] is not None:
            summary["relative_chalk_score"] = 100.0 * math.exp(
                float(summary["log_probability"]) - chalkiest_log
            )
        if lineup:
            lineup[0]["lineup_duplication_risk"] = summary
    return summaries


def plan_showdown_captain_diversification(
    qualifying_candidates: list[dict],
    *,
    minimum_distinct: int = 3,
) -> list[str]:
    """Choose strong qualifying Captains while ensuring both teams when possible."""
    ordered = sorted(
        qualifying_candidates,
        key=lambda row: (-_safe_float(row.get("objective_score")), str(row.get("player_id"))),
    )
    target_count = min(minimum_distinct, len(ordered))
    planned = [str(row["player_id"]) for row in ordered[:target_count]]
    qualifying_teams = {str(row.get("team") or "") for row in ordered if row.get("team")}
    planned_teams = {
        str(row.get("team") or "") for row in ordered
        if str(row.get("player_id")) in planned
    }
    if len(qualifying_teams) >= 2 and len(planned_teams) < 2 and planned:
        first_team = str(ordered[0].get("team") or "")
        other_team_candidate = next(
            (row for row in ordered if str(row.get("team") or "") != first_team),
            None,
        )
        if other_team_candidate is not None:
            planned[-1] = str(other_team_candidate["player_id"])
    return planned


def summarize_classic_stack(lineup: list[dict]) -> dict:
    """Describe the realized QB stack instead of only the configured policy."""
    quarterbacks = [
        row for row in lineup if str(row.get("position") or "").upper() == "QB"
    ]
    if not quarterbacks:
        return {"label": "No QB", "pass_catchers": 0, "bring_backs": 0}
    qb = quarterbacks[0]
    qb_team = str(qb.get("player_team") or qb.get("team") or "").upper()
    opponent = str(qb.get("opponent_team") or "").upper()
    pass_catchers = sum(
        str(row.get("player_team") or row.get("team") or "").upper() == qb_team
        and str(row.get("position") or "").upper() in {"WR", "TE"}
        and row is not qb
        for row in lineup
    )
    bring_backs = sum(
        bool(opponent)
        and str(row.get("player_team") or row.get("team") or "").upper() == opponent
        and str(row.get("position") or "").upper() in {"RB", "WR", "TE"}
        for row in lineup
    )
    return {
        "quarterback": str(qb.get("name") or qb.get("player_name") or qb.get("player_id")),
        "quarterback_team": qb_team,
        "pass_catchers": int(pass_catchers),
        "bring_backs": int(bring_backs),
        "label": f"QB + {pass_catchers}; {bring_backs} bring-back",
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


def normalize_exposure_rate(value, *, default: float) -> float:
    """Accept either a 0-1 rate or UI-style percentage and persist a rate."""
    try:
        rate = float(value)
    except (TypeError, ValueError):
        rate = default
    if not math.isfinite(rate):
        rate = default
    if rate > 1.0:
        rate /= 100.0
    return max(0.01, min(1.0, rate))


def _has_current_opportunity(row: pd.Series | dict) -> bool:
    fields = (
        "pregame_expected_snaps", "pregame_expected_routes",
        "pregame_expected_carries", "pregame_expected_targets",
        "pregame_target_share", "pregame_carry_share",
        "pregame_red_zone_share", "pregame_goal_line_share",
    )
    if any(_safe_float(row.get(field)) > 0 for field in fields):
        return True
    newly_assigned = row.get("pregame_newly_assigned_role")
    if newly_assigned is True or str(newly_assigned).strip().lower() in {"1", "true", "yes"}:
        return True
    role = str(row.get("pregame_role_label") or "").strip().upper()
    return role not in {"", "UNKNOWN", "BACKUP", "ROTATION", "GENERIC"}


def apply_showdown_opportunity_gate(pool: pd.DataFrame) -> tuple[pd.DataFrame, set[str]]:
    """Exclude low-opportunity RB/WR/TE values using role evidence first."""
    if pool.empty:
        return pool.copy(), set()
    frame = pool.copy()
    salary = pd.to_numeric(frame.get("salary", 0), errors="coerce").fillna(0)
    mean = pd.to_numeric(frame.get("projection", 0), errors="coerce").fillna(0)
    p90 = pd.to_numeric(frame.get("p90", mean), errors="coerce").fillna(mean)
    positions = frame.get("position", pd.Series("", index=frame.index)).astype(str).str.upper()
    no_opportunity = ~frame.apply(_has_current_opportunity, axis=1)
    skill_player = positions.isin({"RB", "WR", "TE"})
    legacy_punt = (salary <= 1000) & (mean < 3) & (p90 < 10)
    low_salary_fallback = (salary <= 2000) & (mean < 2) & (p90 < 8)
    excluded_mask = skill_player & no_opportunity & (legacy_punt | low_salary_fallback)
    excluded = set(frame.loc[excluded_mask, "player_id"].astype(str))
    return frame.loc[~excluded_mask].reset_index(drop=True), excluded


def _is_high_rushing_qb(row: pd.Series | dict) -> bool:
    role = str(row.get("pregame_role_label") or "").upper()
    return (
        any(token in role for token in ("RUSH", "MOBILE", "DUAL"))
        or _safe_float(row.get("pregame_expected_carries")) >= 5
        or _safe_float(row.get("pregame_carry_share")) >= 0.20
        or _safe_float(row.get("carries_mean_3")) >= 5
    )


_SATURATED_SHOWDOWN_RULE_IDS = {
    "correlation.qb_pass_catcher_v2",
    "correlation.shootout_bring_back_v1",
    "correlation.opposing_pass_catchers_v1",
    "captain.qb_pass_catcher_v2",
    "captain.pass_catcher_qb_v2",
}


def _add_saturated_showdown_correlation_objective(
    model: pulp.LpProblem,
    pool: pd.DataFrame,
    selected_vars: dict[int, object],
) -> pulp.LpAffineExpression:
    """Reward stack depth with diminishing returns and one bring-back per QB team."""
    terms: list = []
    teams = pool["player_team"].astype(str).str.upper()
    positions = pool["position"].astype(str).str.upper()
    for qb_index in [i for i in pool.index if positions.iloc[i] == "QB"]:
        team = teams.iloc[qb_index]
        opponent = str(pool.loc[qb_index].get("opponent_team") or "").upper()
        pass_catchers = [
            i for i in pool.index
            if teams.iloc[i] == team and positions.iloc[i] in {"WR", "TE"}
        ]
        count = pulp.lpSum(selected_vars[i] for i in pass_catchers)
        for threshold, bonus in ((1, 0.60), (2, 0.30), (3, 0.10)):
            if len(pass_catchers) < threshold:
                continue
            active = pulp.LpVariable(
                f"saturated_qb_stack_{qb_index}_{threshold}", 0, 1, cat="Binary"
            )
            model += active <= selected_vars[qb_index]
            model += count >= threshold * active
            model += count <= (threshold - 1) + len(pass_catchers) * active + len(pass_catchers) * (1 - selected_vars[qb_index])
            terms.append(bonus * active)
        opponent_catchers = [
            i for i in pool.index
            if teams.iloc[i] == opponent and positions.iloc[i] in {"WR", "TE"}
        ]
        if opponent_catchers:
            opponent_count = pulp.lpSum(selected_vars[i] for i in opponent_catchers)
            bring_back = pulp.LpVariable(
                f"saturated_bring_back_{qb_index}", 0, 1, cat="Binary"
            )
            model += bring_back <= selected_vars[qb_index]
            model += bring_back <= opponent_count
            model += opponent_count <= len(opponent_catchers) * bring_back + len(opponent_catchers) * (1 - selected_vars[qb_index])
            terms.append(0.45 * bring_back)
    return pulp.lpSum(terms)


def _saturated_showdown_correlation_summary(
    lineup: list[dict], summary: dict
) -> dict:
    kept = [
        row for row in summary.get("triggered_rules", [])
        if row.get("rule_id") not in _SATURATED_SHOWDOWN_RULE_IDS
        and row.get("construction_kind") != "showdown_fragile_punt"
    ]
    custom: list[dict] = []
    for qb in [row for row in lineup if str(row.get("position") or "").upper() == "QB"]:
        team = str(qb.get("player_team") or qb.get("team") or "").upper()
        opponent = str(qb.get("opponent_team") or "").upper()
        catchers = [
            row for row in lineup
            if str(row.get("player_team") or row.get("team") or "").upper() == team
            and str(row.get("position") or "").upper() in {"WR", "TE"}
        ]
        for threshold, contribution in ((1, 0.60), (2, 0.30), (3, 0.10)):
            if len(catchers) >= threshold:
                custom.append({
                    "rule_id": f"correlation.qb_pass_catcher_saturated_{threshold}_v1",
                    "reason_code": f"qb_pass_catcher_{threshold}",
                    "score_contribution": contribution,
                    "objective_contribution": contribution,
                    "term_kind": "saturated_team_threshold",
                    "players": [{"player_id": str(qb.get("player_id")), "player_name": qb.get("name"), "team": team, "position": "QB"}],
                    "evidence": {"pass_catcher_count": len(catchers), "threshold": threshold},
                })
        if any(
            str(row.get("player_team") or row.get("team") or "").upper() == opponent
            and str(row.get("position") or "").upper() in {"WR", "TE"}
            for row in lineup
        ):
            custom.append({
                "rule_id": "correlation.shootout_bring_back_team_once_v1",
                "reason_code": "shootout_bring_back_once",
                "score_contribution": 0.45,
                "objective_contribution": 0.45,
                "term_kind": "saturated_team_threshold",
                "players": [{"player_id": str(qb.get("player_id")), "player_name": qb.get("name"), "team": team, "position": "QB"}],
                "evidence": {"opponent": opponent},
            })
    triggers = kept + custom
    total = sum(_safe_float(row.get("objective_contribution")) for row in triggers)
    return {
        **summary,
        "total_rule_adjustment": total,
        "total_adjustment": total,
        "triggered_rules": triggers,
        "correlation_saturation_policy": "qb_stack_diminishing_60_30_10_bringback_once_v1",
    }


def _safe_text(*values: object) -> str:
    """Return the first non-missing scalar without evaluating pandas NA as bool."""
    for value in values:
        normalized = _json_safe(value)
        if normalized is not None and str(normalized).strip():
            return str(normalized).strip()
    return ""


def restrict_pool_to_pregame_available(
    pool: pd.DataFrame,
) -> tuple[pd.DataFrame, set[str]]:
    """Exclude players whose selected projection has zero availability."""
    if pool.empty or "pregame_availability_probability" not in pool.columns:
        return pool.copy(), set()
    availability = pd.to_numeric(
        pool["pregame_availability_probability"], errors="coerce"
    )
    unavailable = availability.notna() & availability.le(0.0)
    excluded_ids = set(pool.loc[unavailable, "player_id"].astype(str))
    return pool.loc[~unavailable].copy(), excluded_ids


def restrict_showdown_pool_to_starting_qbs(
    pool: pd.DataFrame,
    *,
    require_exactly_two_teams: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """Keep one evidence-backed QB per slate team and describe the decision.

    Explicit QB1 evidence wins. When the roster source only says ``QB``, a unique
    highest DraftKings FLEX salary is retained as an inference. Ties and incomplete
    team coverage fail closed rather than allowing a backup into the solver. Showdown
    callers retain the default two-team requirement; the starter-loading workflow can
    validate a multi-game Classic slate by disabling that format-specific guard.
    """
    if pool.empty:
        raise ValueError("Starter-QB validation has no player pool.")

    frame = pool.copy()
    frame["position"] = frame.get("position", "").fillna("").astype(str).str.upper()
    frame["player_team"] = (
        frame.get("player_team", "").fillna("").astype(str).str.upper()
    )
    teams = sorted(team for team in frame["player_team"].unique() if team)
    if require_exactly_two_teams and len(teams) != 2:
        raise ValueError(
            "Showdown starter-QB validation requires exactly two slate teams; "
            f"found {len(teams)} ({', '.join(teams) or 'none'})."
        )
    if not require_exactly_two_teams and len(teams) < 2:
        raise ValueError(
            "Starter-QB validation requires at least two slate teams; "
            f"found {len(teams)} ({', '.join(teams) or 'none'})."
        )

    qb_pool = frame[frame["position"] == "QB"].copy()
    frame["showdown_qb_eligible"] = frame["position"] != "QB"
    frame["starter_qb_source"] = None
    frame["starter_qb_evidence_tier"] = None
    selected_ids: set[str] = set()
    selections: list[dict] = []
    for team in teams:
        team_qbs = qb_pool[qb_pool["player_team"] == team].copy()
        if team_qbs.empty:
            raise ValueError(
                f"Showdown starter-QB evidence is missing for {team}: no QB is in the slate pool."
            )

        explicit_mask = pd.Series(False, index=team_qbs.index)
        if "is_starting_qb" in team_qbs.columns:
            stored_starter_mask = team_qbs["is_starting_qb"].map(
                lambda value: (
                    bool(value)
                    if isinstance(value, (bool, np.bool_))
                    else str(value).strip().lower() in {"1", "true", "yes"}
                )
            )
            if "starting_qb_evidence_tier" in team_qbs.columns:
                stored_starter_mask &= (
                    team_qbs["starting_qb_evidence_tier"]
                    .fillna("confirmed")
                    .astype(str)
                    .str.lower()
                    != "inferred"
                )
            explicit_mask |= stored_starter_mask
        if "depth_chart_position" in team_qbs.columns:
            explicit_mask |= (
                team_qbs["depth_chart_position"]
                .fillna("")
                .astype(str)
                .str.upper()
                .isin({"QB1", "STARTER", "STARTING"})
            )
        explicit = team_qbs[explicit_mask]
        if len(explicit) > 1:
            raise ValueError(
                f"Showdown starter-QB evidence is ambiguous for {team}: "
                f"{len(explicit)} quarterbacks are marked as starters."
            )

        if len(explicit) == 1:
            selected = explicit.iloc[0]
            source = str(
                selected.get("starting_qb_source") or "explicit_depth_chart_qb1"
            )
            evidence_tier = str(
                selected.get("starting_qb_evidence_tier") or "confirmed"
            ).lower()
            if evidence_tier not in {"confirmed", "inferred"}:
                evidence_tier = "confirmed"
        else:
            team_qbs["_starter_salary"] = pd.to_numeric(
                team_qbs.get("salary", 0), errors="coerce"
            ).fillna(0.0)
            top_salary = float(team_qbs["_starter_salary"].max())
            top_qbs = team_qbs[team_qbs["_starter_salary"] == top_salary]
            if top_salary <= 0 or len(top_qbs) != 1:
                raise ValueError(
                    f"Showdown starter-QB evidence is ambiguous for {team}: "
                    "no explicit QB1 and no unique highest DraftKings salary."
                )
            selected = top_qbs.iloc[0]
            source = "draftkings_unique_top_salary"
            evidence_tier = "inferred"

        player_id = str(selected.get("player_id") or "").strip()
        if not player_id:
            raise ValueError(
                f"Showdown starter-QB evidence for {team} has no canonical player ID."
            )
        selected_ids.add(player_id)
        selected_mask = frame["player_id"].astype(str) == player_id
        frame.loc[selected_mask, "showdown_qb_eligible"] = True
        frame.loc[selected_mask, "starter_qb_source"] = source
        frame.loc[selected_mask, "starter_qb_evidence_tier"] = evidence_tier
        selections.append(
            {
                "team": team,
                "player_id": player_id,
                "player_name": str(
                    selected.get("name") or selected.get("player_name") or player_id
                ),
                "salary": _safe_float(selected.get("salary")),
                "source": source,
                "evidence_tier": evidence_tier,
                **(
                    {"source_uri": str(selected.get("starting_qb_source_uri"))}
                    if str(selected.get("starting_qb_source_uri") or "").strip()
                    else {}
                ),
                **(
                    {"observed_at": str(selected.get("starting_qb_observed_at"))}
                    if str(selected.get("starting_qb_observed_at") or "").strip()
                    else {}
                ),
            }
        )

    specialty_ids = {
        str(row.get("player_id"))
        for row in qb_pool.to_dict(orient="records")
        if str(row.get("player_id") or "").strip()
        and has_explicit_specialty_role(row)
    }
    specialty_ids -= selected_ids
    if specialty_ids:
        specialty_mask = frame["player_id"].astype(str).isin(specialty_ids)
        frame.loc[specialty_mask, "showdown_qb_eligible"] = True
        frame.loc[specialty_mask, "starter_qb_source"] = "explicit_specialty_role"
        frame.loc[specialty_mask, "starter_qb_evidence_tier"] = "confirmed"

    qb_ids = set(qb_pool["player_id"].astype(str))
    eligible_qb_ids = selected_ids | specialty_ids
    filtered = frame[
        (frame["position"] != "QB")
        | frame["player_id"].astype(str).isin(eligible_qb_ids)
    ].copy()
    metadata = {
        "status": "passed",
        "required_starters": len(teams),
        "candidate_qb_count": len(qb_pool),
        "selected_qb_count": len(selected_ids),
        "specialty_qb_count": len(specialty_ids),
        "specialty_qb_ids": sorted(specialty_ids),
        "excluded_qb_count": len(qb_ids - eligible_qb_ids),
        "selected": selections,
        "evidence_status": (
            "confirmed" if all(row["evidence_tier"] == "confirmed" for row in selections)
            else "salary_inferred"
        ),
    }
    return filtered.reset_index(drop=True), metadata


def build_showdown_captain_prior(
    pool: pd.DataFrame,
    *,
    model_path: str,
    strength: float,
) -> tuple[pd.DataFrame, dict]:
    """Apply the validated captain-position model to CPT objective weights."""
    configured_path = Path(model_path).expanduser()
    resolved_path = (
        configured_path
        if configured_path.is_absolute()
        else Path(__file__).resolve().parents[3] / configured_path
    ).resolve()
    if not resolved_path.exists():
        raise ValueError(f"Showdown captain model not found: {resolved_path}")
    payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    model = payload.get("model") or {}
    classes = [str(value).upper() for value in model.get("classes", [])]
    feature_names = [str(value) for value in model.get("feature_names", [])]
    weights = np.asarray(model.get("weights"), dtype=float)
    bias = np.asarray(model.get("bias"), dtype=float)
    x_mean = np.asarray(model.get("x_mean"), dtype=float)
    x_std = np.asarray(model.get("x_std"), dtype=float)
    if (
        not classes
        or not feature_names
        or weights.shape != (len(feature_names), len(classes))
        or bias.shape != (len(classes),)
        or x_mean.shape != (len(feature_names),)
        or x_std.shape != (len(feature_names),)
    ):
        raise ValueError("Invalid showdown captain model artifact.")

    frame = pool.copy()
    frame["position"] = frame.get("position", "").fillna("").astype(str).str.upper()
    frame["player_team"] = (
        frame.get("player_team", "").fillna("").astype(str).str.upper()
    )

    def numeric_values(column: str, *, absolute: bool = False) -> list[float]:
        if column not in frame.columns:
            return []
        values = pd.to_numeric(frame[column], errors="coerce").dropna().astype(float)
        if absolute:
            values = values.abs()
        return [float(value) for value in values if math.isfinite(float(value))]

    def median_or_zero(values: list[float]) -> float:
        return float(np.median(values)) if values else 0.0

    team_counts = sorted(
        [
            int(count)
            for count in frame[frame["player_team"] != ""]
            .groupby("player_team")
            .size()
            .tolist()
        ],
        reverse=True,
    )
    team_implied_values: list[float] = []
    if "team_implied_total" in frame.columns:
        for _, rows in frame.groupby("player_team"):
            values = pd.to_numeric(
                rows["team_implied_total"], errors="coerce"
            ).dropna()
            if not values.empty:
                team_implied_values.append(float(values.median()))
    features = {
        "game_total_line": median_or_zero(numeric_values("game_total_line")),
        "game_spread_abs": median_or_zero(
            numeric_values("team_spread_line", absolute=True)
        ),
        "max_team_implied_total": max(team_implied_values, default=0.0),
        "min_team_implied_total": min(team_implied_values, default=0.0),
        "implied_total_diff": (
            max(team_implied_values) - min(team_implied_values)
            if team_implied_values
            else 0.0
        ),
        "has_vegas_line": float(
            bool(numeric_values("game_total_line"))
            and bool(numeric_values("team_spread_line"))
        ),
        "pool_size": float(len(frame)),
        "team_count": float(frame["player_team"].replace("", np.nan).nunique()),
        "team1_player_count": float(team_counts[0]) if team_counts else 0.0,
        "team2_player_count": float(team_counts[1]) if len(team_counts) > 1 else 0.0,
    }
    for position in ("QB", "RB", "WR", "TE", "K", "DST"):
        rows = frame[frame["position"] == position]
        projection_values = (
            pd.to_numeric(rows.get("projection", pd.Series(dtype=float)), errors="coerce")
            .dropna()
            .tolist()
        )
        salary_values = (
            pd.to_numeric(rows.get("salary", pd.Series(dtype=float)), errors="coerce")
            .dropna()
            .tolist()
        )
        features[f"{position.lower()}_count"] = float(len(rows))
        features[f"top_{position.lower()}_proj_mean"] = float(
            max(projection_values, default=0.0)
        )
        features[f"top_{position.lower()}_salary"] = float(
            max(salary_values, default=0.0)
        )

    feature_vector = np.asarray(
        [float(features.get(name, 0.0)) for name in feature_names], dtype=float
    )
    safe_std = np.where(x_std < 1e-6, 1.0, x_std)
    standardized = (feature_vector - x_mean) / safe_std
    logits = standardized @ weights + bias
    shifted = logits - np.max(logits)
    probabilities = np.exp(shifted)
    probabilities = probabilities / np.sum(probabilities)
    model_position_probs = {
        classes[index]: float(probabilities[index]) for index in range(len(classes))
    }
    out_of_distribution_features = [
        {
            "feature": feature_names[index],
            "standard_deviations": float(standardized[index]),
        }
        for index in range(len(feature_names))
        if abs(float(standardized[index])) > 5.0
    ]
    historical_probs = {
        str(position).upper(): float(probability)
        for position, probability in (
            payload.get("summary", {}).get(
                "historical_captain_position_probabilities", {}
            )
            or {}
        ).items()
    }
    if out_of_distribution_features and historical_probs:
        probability_source = "historical_position_mix_fallback"
        position_probs = {
            position: historical_probs.get(position, 0.0) for position in classes
        }
    else:
        probability_source = "matchup_model"
        position_probs = model_position_probs
    probability_total = float(sum(position_probs.values()))
    if probability_total <= 0:
        raise ValueError("Showdown captain model produced no usable probabilities.")
    position_probs = {
        position: probability / probability_total
        for position, probability in position_probs.items()
    }

    prior_strength = float(min(max(strength, 0.0), 1.0))
    class_scale = float(max(len(position_probs), 1))
    frame["captain_position_probability"] = frame["position"].map(
        lambda position: float(position_probs.get(str(position).upper(), 0.0))
    )
    frame["captain_objective_multiplier"] = frame[
        "captain_position_probability"
    ].map(
        lambda probability: (1.0 - prior_strength)
        + (prior_strength * max(0.05, float(probability) * class_scale))
    )
    metadata = {
        "model_path": str(model_path),
        "prior_strength": prior_strength,
        "probability_source": probability_source,
        "position_probabilities": position_probs,
        "raw_model_position_probabilities": model_position_probs,
        "out_of_distribution_features": out_of_distribution_features,
        "context_features": {
            name: float(features.get(name, 0.0)) for name in feature_names
        },
        "evaluation": payload.get("summary", {}),
    }
    return frame, metadata


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


def _resolve_player_control_names(
    pool: pd.DataFrame,
    values: object,
    *,
    field_name: str,
) -> tuple[set[str], set[str]]:
    """Resolve user-facing names to unambiguous canonical IDs in this slate."""

    if values is None:
        return set(), set()
    if isinstance(values, str):
        raw_values = [values]
    else:
        try:
            raw_values = list(values)  # type: ignore[arg-type]
        except TypeError as exc:
            raise ValueError(f"{field_name} must be a list of player names") from exc
    requested_names = {
        str(name).strip()
        for value in raw_values
        for name in str(value).split(",")
        if str(name).strip()
    }
    if not requested_names:
        return set(), set()

    ids_by_name: dict[str, set[str]] = {}
    for row in pool.to_dict(orient="records"):
        player_id = str(row.get("player_id") or "").strip()
        if not player_id:
            continue
        player_name = next(
            (
                str(row.get(column) or "").strip()
                for column in ("player_display_name", "player_name", "name")
                if str(row.get(column) or "").strip()
            ),
            "",
        )
        if player_name:
            ids_by_name.setdefault(_normalize_alias(player_name), set()).add(
                player_id
            )

    resolved_ids: set[str] = set()
    for requested_name in sorted(requested_names):
        matches = ids_by_name.get(_normalize_alias(requested_name), set())
        if not matches:
            raise ValueError(
                f"{field_name} player was not found in the selected slate: "
                f"{requested_name}"
            )
        if len(matches) > 1:
            raise ValueError(
                f"{field_name} player name is ambiguous; use a canonical player ID: "
                f"{requested_name}"
            )
        resolved_ids.update(matches)
    return resolved_ids, requested_names


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
                    cash_summary = {}
                    if job.strategy == CLASSIC_HEAD_TO_HEAD_STRATEGY_ID:
                        cash_summary = summarize_head_to_head_lineup(lineup)
                    elif job.contest_format == "classic" and job.objective == "cash":
                        cash_summary = summarize_classic_cash_lineup(lineup)
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
                    objective_score = cash_summary.get("objective_score")
                    if job.contest_format == "showdown":
                        objective_score = sum(
                            _safe_float(row.get("objective_score")) for row in lineup
                        )
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
                            "objective_score": objective_score,
                            "average_role_certainty": cash_summary.get("average_role_certainty"),
                            "fragility_penalty": cash_summary.get("total_fragility_penalty"),
                            "ownership_sum": ownership_sum,
                            "leverage_score": leverage_score,
                            "created_at": job.created_at,
                        },
                    )
                    player_rows = []
                    for slot_index, row in enumerate(lineup):
                        roster_position = str(
                            row.get("roster_position") or row.get("position") or ""
                        ).upper()
                        player_payload = dict(row)
                        player_payload["lineup_slot_index"] = slot_index
                        player_payload["roster_position"] = roster_position
                        player_rows.append(
                            {
                                "lineup_id": lineup_id,
                                "slot_index": slot_index,
                                "player_id": str(row.get("player_id") or row.get("dk_player_id") or ""),
                                "roster_position": roster_position,
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
                                    _json_safe(player_payload),
                                    sort_keys=True,
                                    allow_nan=False,
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
                    strategy_config = job.params.get("strategy_config")
                    if isinstance(strategy_config, dict):
                        connection.execute(
                            text(
                                """
                                INSERT INTO target.lineup_constraint_explanation
                                    (lineup_id, constraint_name, constraint_status, explanation_json)
                                VALUES
                                    (:lineup_id, 'optimizer_strategy', 'applied',
                                     CAST(:explanation_json AS JSONB))
                                """
                            ),
                            {
                                "lineup_id": lineup_id,
                                "explanation_json": json.dumps(
                                    _json_safe(
                                        {
                                            "config": strategy_config,
                                            "runtime": job.params.get(
                                                "strategy_runtime", {}
                                            ),
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
                            "SELECT slot_index, roster_position, player_json "
                            "FROM target.lineup_player "
                            "WHERE lineup_id = :lineup_id ORDER BY slot_index"
                        ),
                        {"lineup_id": lineup_row["lineup_id"]},
                    ).mappings().all()
                    lineup = []
                    for player_row in player_rows:
                        payload = player_row.get("player_json") or {}
                        if isinstance(payload, str):
                            payload = json.loads(payload)
                        player = dict(payload)
                        player["lineup_slot_index"] = int(
                            player_row.get("slot_index") or 0
                        )
                        if player_row.get("roster_position"):
                            player["roster_position"] = str(
                                player_row["roster_position"]
                            ).upper()
                        lineup.append(player)
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
            "p90": player.ceiling,
            "ownership": player.ownership,
            "optimal_lineup_probability": player.optimal_lineup_probability,
            "leverage": player.leverage,
            "optimizer_context_adjustment": player.optimizer_context_adjustment,
            "optimizer_context_rule_evaluation": (
                player.optimizer_context_rule_evaluation
            ),
            "game_id": player.game_id,
            "game_total_line": player.game_total,
            "team_spread_line": player.spread,
            "team_implied_total": player.team_total,
            "market_context_point_in_time_safe": (
                player.market_context_point_in_time_safe
            ),
            "optimizer_receiving_role_strength": (
                player.optimizer_receiving_role_strength
            ),
            "optimizer_rushing_role_strength": (
                player.optimizer_rushing_role_strength
            ),
            "tags": list(player.tags),
        }

    @staticmethod
    def _gpp_players_from_pool(pool: pd.DataFrame) -> list[GPPPlayer]:
        """Adapt the exact live optimizer pool without reloading or rematching players."""
        players: list[GPPPlayer] = []
        for row in pool.to_dict(orient="records"):
            projection = _safe_float(row.get("projection", row.get("predicted_mean")))
            ceiling = _safe_float(
                row.get("p90", row.get("predicted_p90", projection))
            )
            optimal_raw = row.get("optimal_lineup_probability")
            optimal_probability = (
                None
                if optimal_raw is None or pd.isna(optimal_raw)
                else _safe_float(optimal_raw)
            )
            market_context_raw = row.get("market_context_point_in_time_safe")
            market_context_safe = (
                None
                if market_context_raw is None or pd.isna(market_context_raw)
                else (
                    market_context_raw
                    if isinstance(market_context_raw, bool)
                    else str(market_context_raw).strip().lower()
                    in {"1", "true", "t", "yes", "y"}
                )
            )
            players.append(
                GPPPlayer(
                    player_id=str(row.get("player_id") or ""),
                    name=str(
                        row.get("name")
                        or row.get("player_name")
                        or row.get("player_display_name")
                        or row.get("player_id")
                        or ""
                    ),
                    team=str(
                        row.get("player_team") or row.get("team") or ""
                    ).upper(),
                    opponent=str(
                        row.get("opponent_team") or row.get("opponent") or ""
                    ).upper(),
                    position=str(
                        row.get("position") or row.get("roster_position") or ""
                    ).upper(),
                    salary=int(_safe_float(row.get("salary"))),
                    projection=projection,
                    ceiling=ceiling,
                    ownership=_safe_float(
                        row.get("ownership", row.get("projected_ownership"))
                    ),
                    optimal_lineup_probability=optimal_probability,
                    game_id=(
                        str(row.get("game_id") or row.get("game_info"))
                        if row.get("game_id") or row.get("game_info")
                        else None
                    ),
                    spread=(
                        _safe_float(
                            row.get("team_spread_line", row.get("spread"))
                        )
                        if row.get("team_spread_line", row.get("spread")) is not None
                        else None
                    ),
                    game_total=(
                        _safe_float(
                            row.get("game_total_line", row.get("game_total"))
                        )
                        if row.get("game_total_line", row.get("game_total")) is not None
                        else None
                    ),
                    team_total=(
                        _safe_float(
                            row.get("team_implied_total", row.get("team_total"))
                        )
                        if row.get("team_implied_total", row.get("team_total")) is not None
                        else None
                    ),
                    market_context_point_in_time_safe=market_context_safe,
                    optimizer_context_adjustment=_safe_float(
                        row.get("optimizer_context_adjustment")
                    ),
                    optimizer_context_rule_evaluation=(
                        row.get("optimizer_context_rule_evaluation")
                        if isinstance(
                            row.get("optimizer_context_rule_evaluation"), dict
                        )
                        else None
                    ),
                    optimizer_receiving_role_strength=_safe_float(
                        row.get("optimizer_receiving_role_strength")
                    ),
                    optimizer_rushing_role_strength=_safe_float(
                        row.get("optimizer_rushing_role_strength")
                    ),
                )
            )
        return players

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
            salary_cte = f"""
                latest_salary AS (
                    SELECT DISTINCT ON (salary.player_master_id)
                        salary.player_master_id AS player_id,
                        salary.source_player_key AS site_player_id,
                        captain.source_player_key AS captain_site_player_id,
                        salary.player_name AS salary_name,
                        salary.salary,
                        COALESCE(
                            NULLIF(salary.position, ''),
                            salary.roster_position
                        ) AS salary_position,
                        salary.player_status,
                        salary.team AS team_id,
                        salary.opponent AS opponent_team_id,
                        salary.game_info AS game_id
                    FROM public.curated_salary salary
                    LEFT JOIN LATERAL (
                        SELECT role.source_player_key
                        FROM public.curated_salary role
                        WHERE role.season = salary.season
                          AND role.week = salary.week
                          AND UPPER(role.slate) = UPPER(salary.slate)
                          AND role.player_master_id = salary.player_master_id
                          AND UPPER(role.roster_position) = 'CPT'
                        ORDER BY role.created_at DESC, role.curated_salary_id DESC
                        LIMIT 1
                    ) captain ON TRUE
                    WHERE salary.season = :season AND salary.week = :week
                      AND UPPER(salary.slate) = UPPER(:slate)
                      AND salary.player_master_id IS NOT NULL
                    ORDER BY salary.player_master_id,
                        CASE WHEN UPPER(salary.roster_position) = 'FLEX' THEN 0 ELSE 1 END,
                        salary.created_at DESC,
                        salary.curated_salary_id DESC
                )
            """
        else:
            salary_cte = f"""
                latest_salary AS (
                    SELECT DISTINCT ON (salary.player_id)
                        salary.player_id,
                        salary.site_player_id,
                        captain.site_player_id AS captain_site_player_id,
                        NULL::TEXT AS salary_name,
                        salary.salary,
                        salary.roster_position AS salary_position,
                        salary.player_status,
                        salary.team_id,
                        salary.opponent_team_id,
                        salary.game_id
                    FROM target.snapshot_salary salary
                    LEFT JOIN LATERAL (
                        SELECT role.site_player_id
                        FROM target.snapshot_salary role
                        WHERE role.season = salary.season
                          AND role.week = salary.week
                          AND UPPER(COALESCE(role.slate, role.slate_id)) =
                              UPPER(COALESCE(salary.slate, salary.slate_id))
                          AND role.player_id = salary.player_id
                          AND UPPER(role.roster_position) = 'CPT'
                        ORDER BY role.as_of DESC, role.snapshot_salary_id DESC
                        LIMIT 1
                    ) captain ON TRUE
                    WHERE salary.season = :season AND salary.week = :week
                      AND UPPER(COALESCE(salary.slate, salary.slate_id)) = UPPER(:slate)
                    ORDER BY salary.player_id,
                        CASE WHEN UPPER(salary.roster_position) = 'FLEX' THEN 0 ELSE 1 END,
                        salary.as_of DESC,
                        salary.snapshot_salary_id DESC
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
        has_roster_participation = inspector.has_table(
            "curated_player_game_participation",
            schema="public",
        )
        has_feature_matrix = inspector.has_table(
            "player_game_feature_matrix",
            schema="public",
        )
        has_starting_qbs = inspector.has_table(
            "starting_qb_evidence", schema="public"
        )
        has_projection_features = inspector.has_table(
            "feature_player_game", schema="target"
        ) and inspector.has_table("model_run", schema="target")
        has_ownership = inspector.has_table("ownership_projection", schema="target")
        position_source = (
            "COALESCE("
            "NULLIF(CASE WHEN UPPER(COALESCE(s.salary_position, '')) "
            "IN ('FLEX', 'CPT') THEN '' ELSE s.salary_position END, ''), "
            "d.primary_position)"
        )
        injury_join = ""
        injury_status_select = "NULL::TEXT AS injury_status"
        filters: list[str] = []
        if has_injuries:
            cutoff_predicate = injury_snapshot_cutoff_sql(
                injury_alias="injury",
                projection_alias="p",
            )
            injury_join = f"""
                LEFT JOIN LATERAL (
                    SELECT injury.injury_status
                    FROM target.snapshot_injury_status injury
                    WHERE injury.season = :season AND injury.week = :week
                      AND injury.player_id = s.player_id
                      AND (injury.slate IS NULL OR UPPER(injury.slate) = UPPER(:slate))
                      AND {cutoff_predicate}
                    ORDER BY injury.as_of DESC
                    LIMIT 1
                ) i ON TRUE
            """
            injury_status_select = "i.injury_status"
        roster_join = ""
        roster_status_select = "NULL::TEXT AS roster_status"
        roster_evidence_select = "FALSE AS roster_evidence_available"
        if has_roster_participation:
            roster_status_select = "participation.roster_status"
            roster_evidence_select = """
                EXISTS (
                    SELECT 1
                    FROM public.curated_player_game_participation roster_evidence
                    WHERE roster_evidence.season = :season
                      AND roster_evidence.week = :week
                      AND (
                          p.data_cutoff_at IS NULL
                          OR roster_evidence.created_at <= p.data_cutoff_at
                      )
                ) AS roster_evidence_available
            """
            roster_join = """
                LEFT JOIN LATERAL (
                    SELECT roster_row.roster_status
                    FROM public.curated_player_game_participation roster_row
                    WHERE roster_row.season = :season
                      AND roster_row.week = :week
                      AND roster_row.player_master_id = s.player_id
                      AND UPPER(roster_row.team) = UPPER(s.team_id)
                      AND (
                          p.data_cutoff_at IS NULL
                          OR roster_row.created_at <= p.data_cutoff_at
                      )
                    ORDER BY roster_row.created_at DESC,
                        roster_row.curated_player_game_participation_id DESC
                    LIMIT 1
                ) participation ON TRUE
            """
        feature_join = ""
        feature_select = """
                NULL::DOUBLE PRECISION AS game_total_line,
                NULL::DOUBLE PRECISION AS team_spread_line,
                NULL::DOUBLE PRECISION AS team_implied_total,
                FALSE AS market_context_point_in_time_safe,
        """
        if has_feature_matrix:
            feature_select = """
                feature.game_total_line,
                feature.team_spread_line,
                feature.team_implied_total,
                FALSE AS market_context_point_in_time_safe,
            """
            feature_join = """
                LEFT JOIN LATERAL (
                    SELECT
                        matrix.game_total_line,
                        matrix.team_spread_line,
                        matrix.team_implied_total
                    FROM public.player_game_feature_matrix matrix
                    WHERE matrix.season = :season
                      AND matrix.week = :week
                      AND matrix.player_master_id = s.player_id
                      AND (
                          matrix.slate IS NULL
                          OR UPPER(matrix.slate) = UPPER(:slate)
                      )
                    ORDER BY matrix.created_at DESC,
                        matrix.player_game_feature_matrix_id DESC
                    LIMIT 1
                ) feature ON TRUE
            """
        starter_join = ""
        starter_select = """
                FALSE AS is_starting_qb,
                NULL::TEXT AS starting_qb_source,
                NULL::TEXT AS starting_qb_evidence_tier,
        """
        if has_starting_qbs:
            starter_select = """
                (starter.player_master_id IS NOT NULL) AS is_starting_qb,
                starter.source AS starting_qb_source,
                starter.evidence_tier AS starting_qb_evidence_tier,
            """
            starter_join = """
                LEFT JOIN public.starting_qb_evidence starter
                  ON starter.season = :season
                 AND starter.week = :week
                 AND UPPER(starter.slate) = UPPER(:slate)
                 AND starter.player_master_id = s.player_id
                 AND UPPER(starter.team) = UPPER(s.team_id)
                 AND UPPER(starter.status) = 'ACTIVE'
            """
        pregame_select = """
                NULL::DOUBLE PRECISION AS pregame_availability_probability,
                NULL::DOUBLE PRECISION AS pregame_start_probability,
                NULL::DOUBLE PRECISION AS pregame_carry_share,
                NULL::DOUBLE PRECISION AS pregame_target_share,
                NULL::TEXT AS pregame_role_label,
                NULL::TEXT AS pregame_injury_status,
                NULL::TEXT AS pregame_context_run_id,
                NULL::TEXT AS pregame_context_source,
                NULL::TIMESTAMPTZ AS pregame_context_observed_at,
                NULL::DOUBLE PRECISION AS pregame_expected_snaps,
                NULL::DOUBLE PRECISION AS pregame_expected_routes,
                NULL::DOUBLE PRECISION AS pregame_expected_carries,
                NULL::DOUBLE PRECISION AS pregame_expected_targets,
                NULL::DOUBLE PRECISION AS pregame_red_zone_share,
                NULL::DOUBLE PRECISION AS pregame_goal_line_share,
                NULL::DOUBLE PRECISION AS carries_mean_3,
                FALSE AS pregame_role_uncertain,
                FALSE AS pregame_newly_assigned_role,
                FALSE AS pregame_depth_chart_conflict,
        """
        pregame_join = ""
        if has_projection_features:
            feature_select = """
                NULLIF(projection_feature.feature_json ->> 'game_total_line', '')::DOUBLE PRECISION
                    AS game_total_line,
                NULLIF(projection_feature.feature_json ->> 'team_spread_line', '')::DOUBLE PRECISION
                    AS team_spread_line,
                NULLIF(projection_feature.feature_json ->> 'team_implied_total', '')::DOUBLE PRECISION
                    AS team_implied_total,
                TRUE AS market_context_point_in_time_safe,
            """
            feature_join = ""
            pregame_select = """
                NULLIF(
                    projection_feature.feature_json
                        ->> 'pregame_availability_probability',
                    ''
                )::DOUBLE PRECISION AS pregame_availability_probability,
                NULLIF(projection_feature.feature_json ->> 'pregame_start_probability', '')::DOUBLE PRECISION
                    AS pregame_start_probability,
                NULLIF(projection_feature.feature_json ->> 'pregame_carry_share', '')::DOUBLE PRECISION
                    AS pregame_carry_share,
                NULLIF(projection_feature.feature_json ->> 'pregame_target_share', '')::DOUBLE PRECISION
                    AS pregame_target_share,
                projection_feature.feature_json ->> 'pregame_role_label'
                    AS pregame_role_label,
                projection_feature.feature_json ->> 'pregame_injury_status'
                    AS pregame_injury_status,
                projection_feature.feature_json
                    ->> 'pregame_context_run_id' AS pregame_context_run_id,
                projection_feature.feature_json
                    ->> 'pregame_context_source' AS pregame_context_source,
                NULLIF(projection_feature.feature_json ->> 'pregame_context_observed_at', '')::TIMESTAMPTZ
                    AS pregame_context_observed_at,
                NULLIF(projection_feature.feature_json ->> 'pregame_expected_snaps', '')::DOUBLE PRECISION
                    AS pregame_expected_snaps,
                NULLIF(projection_feature.feature_json ->> 'pregame_expected_routes', '')::DOUBLE PRECISION
                    AS pregame_expected_routes,
                NULLIF(projection_feature.feature_json ->> 'pregame_expected_carries', '')::DOUBLE PRECISION
                    AS pregame_expected_carries,
                NULLIF(projection_feature.feature_json ->> 'pregame_expected_targets', '')::DOUBLE PRECISION
                    AS pregame_expected_targets,
                NULLIF(projection_feature.feature_json ->> 'pregame_red_zone_share', '')::DOUBLE PRECISION
                    AS pregame_red_zone_share,
                NULLIF(projection_feature.feature_json ->> 'pregame_goal_line_share', '')::DOUBLE PRECISION
                    AS pregame_goal_line_share,
                NULLIF(projection_feature.feature_json ->> 'carries_mean_3', '')::DOUBLE PRECISION
                    AS carries_mean_3,
                COALESCE(NULLIF(projection_feature.feature_json ->> 'pregame_role_uncertain', '')::BOOLEAN, FALSE)
                    AS pregame_role_uncertain,
                COALESCE(NULLIF(projection_feature.feature_json ->> 'pregame_newly_assigned_role', '')::BOOLEAN, FALSE)
                    AS pregame_newly_assigned_role,
                COALESCE(NULLIF(projection_feature.feature_json ->> 'pregame_depth_chart_conflict', '')::BOOLEAN, FALSE)
                    AS pregame_depth_chart_conflict,
            """
            pregame_join = """
                LEFT JOIN target.model_run projection_model_run
                  ON projection_model_run.model_run_id = p.model_run_id
                LEFT JOIN target.feature_player_game projection_feature
                  ON projection_feature.feature_run_id =
                        projection_model_run.feature_run_id
                 AND projection_feature.season = p.season
                 AND projection_feature.week = p.week
                 AND projection_feature.game_id = p.game_id
                 AND projection_feature.player_id = p.player_id
            """
            if not has_starting_qbs:
                starter_select = """
                    COALESCE(
                        NULLIF(
                            projection_feature.feature_json
                                ->> 'pregame_start_probability',
                            ''
                        )::DOUBLE PRECISION >= 0.5,
                        FALSE
                    ) AS is_starting_qb,
                    projection_feature.feature_json
                        ->> 'starting_qb_source' AS starting_qb_source,
                    projection_feature.feature_json
                        ->> 'starting_qb_evidence_tier'
                        AS starting_qb_evidence_tier,
                """
        ownership_select = """
                NULL::DOUBLE PRECISION AS captain_ownership,
                NULL::DOUBLE PRECISION AS flex_ownership,
        """
        ownership_join = ""
        if has_ownership:
            ownership_select = """
                ownership.captain_ownership,
                ownership.flex_ownership,
            """
            ownership_join = """
                LEFT JOIN LATERAL (
                    SELECT
                        MAX(projected_ownership) FILTER (
                            WHERE UPPER(roster_position) = 'CPT'
                        ) AS captain_ownership,
                        MAX(projected_ownership) FILTER (
                            WHERE UPPER(roster_position) = 'FLEX'
                        ) AS flex_ownership
                    FROM target.ownership_projection ownership_row
                    WHERE ownership_row.season = :season
                      AND ownership_row.week = :week
                      AND UPPER(ownership_row.slate_id) = UPPER(:slate)
                      AND ownership_row.player_id = s.player_id
                      AND ownership_row.ownership_run_id = (
                          SELECT latest.ownership_run_id
                          FROM target.ownership_model_run latest
                          WHERE latest.season = :season
                            AND latest.week = :week
                            AND UPPER(latest.slate_id) = UPPER(:slate)
                          ORDER BY latest.data_cutoff_at DESC NULLS LAST,
                                   latest.created_at DESC,
                                   latest.ownership_run_id DESC
                          LIMIT 1
                      )
                ) ownership ON TRUE
            """
        row_filter = "WHERE " + " AND ".join(filters) if filters else ""

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
            SELECT
                s.player_id,
                (d.player_id IS NOT NULL) AS identity_resolved,
                s.site_player_id AS dk_player_id,
                s.captain_site_player_id AS dk_captain_id,
                COALESCE(NULLIF(s.salary_name, ''), NULLIF(d.full_name, ''), s.player_id) AS name,
                COALESCE(NULLIF(s.salary_name, ''), NULLIF(d.full_name, ''), s.player_id) AS player_name,
                CASE
                    WHEN UPPER({position_source}) IN ('D', 'DEF') THEN 'DST'
                    ELSE UPPER({position_source})
                END AS position,
                s.salary,
                s.player_status,
                UPPER(TRIM(COALESCE(s.player_status, ''))) NOT IN (
                    {INELIGIBLE_SALARY_STATUSES_SQL}
                ) AS salary_status_eligible,
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
                {ownership_select}
                {pregame_select}
                {feature_select}
                {starter_select}
                {roster_status_select},
                {roster_evidence_select},
                {injury_status_select},
                {calibration_select['calibration_method']} AS calibration_method,
                {calibration_select['calibration_position']} AS calibration_position,
                {calibration_select['calibration_role']} AS calibration_role,
                {calibration_select['calibration_sample_size']} AS calibration_sample_size
            FROM latest_salary s
            LEFT JOIN latest_projection p ON p.player_id = s.player_id
            LEFT JOIN target.dim_player d ON d.player_id = s.player_id
            {injury_join}
            {roster_join}
            {feature_join}
            {starter_join}
            {pregame_join}
            {ownership_join}
            {row_filter}
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
    def _validate_classic_lineups(
        lineups: List[List[dict]],
        *,
        requested_lineups: int,
        max_exposure: float,
        enforce_single_te: bool,
        avoid_dst_opponents: bool,
        uniqueness_overlap: int | None = None,
        locked_player_ids: set[str] | None = None,
    ) -> tuple[bool, str]:
        """Validate finalized classic lineups independently of either solver."""
        exposure_counts: dict[str, int] = {}
        signatures: list[set[str]] = []
        exposure_limit = max(
            1, int(math.ceil(max(1, requested_lineups) * max_exposure))
        )

        for lineup_number, lineup in enumerate(lineups, start=1):
            if len(lineup) != 9:
                return False, f"Lineup {lineup_number} has {len(lineup)} players; expected 9"

            player_ids = [
                str(row.get("player_id") or row.get("dk_player_id") or "").strip()
                for row in lineup
            ]
            if any(not player_id for player_id in player_ids):
                return False, f"Lineup {lineup_number} has a missing canonical player ID"
            if len(set(player_ids)) != len(player_ids):
                return False, f"Lineup {lineup_number} contains a duplicate player ID"
            missing_locks = (locked_player_ids or set()) - set(player_ids)
            if missing_locks:
                return False, (
                    f"Lineup {lineup_number} is missing locked player(s): "
                    + ", ".join(sorted(missing_locks))
                )

            positions = [
                str(row.get("position") or row.get("roster_position") or "").upper()
                for row in lineup
            ]
            if positions.count("QB") != 1:
                return False, f"Lineup {lineup_number} must contain exactly one QB"
            if sum(position in {"DST", "D", "DEF"} for position in positions) != 1:
                return False, f"Lineup {lineup_number} must contain exactly one DST"
            if positions.count("RB") < 2:
                return False, f"Lineup {lineup_number} must contain at least two RBs"
            if positions.count("WR") < 3:
                return False, f"Lineup {lineup_number} must contain at least three WRs"
            if positions.count("TE") < 1:
                return False, f"Lineup {lineup_number} must contain at least one TE"
            if enforce_single_te and positions.count("TE") > 1:
                return False, f"Lineup {lineup_number} violates the single-TE control"

            salary = sum(_safe_float(row.get("salary")) for row in lineup)
            if salary > SALARY_CAP:
                return False, (
                    f"Lineup {lineup_number} salary {salary:.0f} exceeds "
                    f"the {SALARY_CAP} cap"
                )

            team_counts: dict[str, int] = {}
            for row, player_id in zip(lineup, player_ids):
                team = str(
                    row.get("player_team") or row.get("team") or ""
                ).upper()
                if not team:
                    return False, f"Lineup {lineup_number} player {player_id} is missing team"
                team_counts[team] = team_counts.get(team, 0) + 1
                exposure_counts[player_id] = exposure_counts.get(player_id, 0) + 1
            if max(team_counts.values(), default=0) > TEAM_LIMIT:
                return False, (
                    f"Lineup {lineup_number} exceeds the {TEAM_LIMIT}-player "
                    "classic team limit"
                )

            if avoid_dst_opponents:
                dst = next(
                    row
                    for row, position in zip(lineup, positions)
                    if position in {"DST", "D", "DEF"}
                )
                dst_opponent = str(
                    dst.get("opponent_team") or dst.get("opponent") or ""
                ).upper()
                if dst_opponent:
                    conflicting = [
                        row
                        for row, position in zip(lineup, positions)
                        if position not in {"DST", "D", "DEF"}
                        and str(
                            row.get("player_team") or row.get("team") or ""
                        ).upper()
                        == dst_opponent
                    ]
                    if conflicting:
                        return False, (
                            f"Lineup {lineup_number} contains offense against "
                            f"its selected DST ({dst_opponent})"
                        )
            signatures.append(set(player_ids))

        over_exposed = sorted(
            player_id
            for player_id, count in exposure_counts.items()
            if count > exposure_limit
            and player_id not in (locked_player_ids or set())
        )
        if over_exposed:
            return False, (
                f"Player exposure exceeds {exposure_limit}/{requested_lineups}: "
                + ", ".join(over_exposed[:5])
            )

        if uniqueness_overlap is not None:
            for left_index, left in enumerate(signatures):
                for right_index, right in enumerate(
                    signatures[left_index + 1 :],
                    start=left_index + 1,
                ):
                    shared = len(left & right)
                    if shared > uniqueness_overlap:
                        return False, (
                            f"Lineups {left_index + 1} and {right_index + 1} "
                            f"share {shared} players; maximum is {uniqueness_overlap}"
                        )
        return True, ""

    @staticmethod
    def _validate_showdown_lineups(
        lineups: List[List[dict]],
        *,
        requested_lineups: int,
        max_exposure: float,
        require_qb_captain_receiver: bool = False,
        portfolio_policy: bool = False,
        allow_duplicate_lineups: bool = False,
        portfolio_exposure_rates: dict[str, float] | None = None,
        locked_player_ids: set[str] | None = None,
        flex_only_player_ids: set[str] | None = None,
    ) -> tuple[bool, str]:
        """Validate the persisted one-CPT/five-FLEX contract independently."""
        exposure_counts: dict[str, int] = {}
        captain_counts: dict[str, int] = {}
        player_rows: dict[str, dict] = {}
        signatures: set[tuple[tuple[str, str], ...]] = set()
        exposure_limit = max(
            1, int(math.ceil(max(1, requested_lineups) * max_exposure))
        )

        for lineup_number, lineup in enumerate(lineups, start=1):
            if len(lineup) != 6:
                return (
                    False,
                    f"Lineup {lineup_number} has {len(lineup)} players; expected 6",
                )

            player_ids = [
                str(row.get("player_id") or row.get("dk_player_id") or "").strip()
                for row in lineup
            ]
            if any(not player_id for player_id in player_ids):
                return False, f"Lineup {lineup_number} has a missing canonical player ID"
            if len(set(player_ids)) != len(player_ids):
                return False, f"Lineup {lineup_number} contains a duplicate player ID"
            missing_locks = (locked_player_ids or set()) - set(player_ids)
            if missing_locks:
                return False, (
                    f"Lineup {lineup_number} is missing locked player(s): "
                    + ", ".join(sorted(missing_locks))
                )

            roster_positions = [
                str(row.get("roster_position") or "").strip().upper()
                for row in lineup
            ]
            if roster_positions.count("CPT") != 1:
                return False, f"Lineup {lineup_number} must contain exactly one CPT"
            if roster_positions.count("FLEX") != 5:
                return False, f"Lineup {lineup_number} must contain exactly five FLEX slots"
            if any(position not in {"CPT", "FLEX"} for position in roster_positions):
                return False, f"Lineup {lineup_number} contains an invalid showdown slot"
            captain_index = roster_positions.index("CPT")
            if player_ids[captain_index] in (flex_only_player_ids or set()):
                return False, (
                    f"Lineup {lineup_number} uses FLEX-only player "
                    f"{player_ids[captain_index]} at CPT"
                )

            natural_positions = [
                str(row.get("position") or "").strip().upper() for row in lineup
            ]
            quarterback_rows = [
                row
                for row, position in zip(lineup, natural_positions)
                if position == "QB"
            ]
            regular_quarterbacks = [
                row
                for row in quarterback_rows
                if not has_explicit_specialty_role(row)
            ]
            if len(regular_quarterbacks) > 2:
                return False, (
                    f"Lineup {lineup_number} contains more than two non-specialty "
                    "quarterbacks"
                )
            ineligible_qbs = [
                player_id
                for row, player_id, position in zip(
                    lineup, player_ids, natural_positions
                )
                if position == "QB"
                and row.get("showdown_qb_eligible") is not True
            ]
            if ineligible_qbs:
                return False, (
                    f"Lineup {lineup_number} contains QB(s) without starter evidence: "
                    + ", ".join(ineligible_qbs)
                )

            if require_qb_captain_receiver:
                if natural_positions[captain_index] == "QB":
                    captain_team = str(
                        lineup[captain_index].get("player_team")
                        or lineup[captain_index].get("team")
                        or ""
                    ).strip().upper()
                    has_same_team_receiver = any(
                        roster_position == "FLEX"
                        and natural_position in {"WR", "TE"}
                        and str(
                            row.get("player_team") or row.get("team") or ""
                        ).strip().upper()
                        == captain_team
                        for row, roster_position, natural_position in zip(
                            lineup, roster_positions, natural_positions
                        )
                    )
                    if not has_same_team_receiver:
                        return False, (
                            f"Lineup {lineup_number} has QB CPT "
                            f"{player_ids[captain_index]} without a same-team "
                            "WR or TE in FLEX"
                        )

            if portfolio_policy:
                starter_qbs = [
                    row for row, position in zip(lineup, natural_positions)
                    if position == "QB" and bool(row.get("showdown_qb_eligible"))
                ]
                if not starter_qbs:
                    return False, f"Lineup {lineup_number} has no starting quarterback"
                for team in {
                    str(row.get("player_team") or row.get("team") or "").upper()
                    for row in lineup
                }:
                    team_qbs = [
                        row for row in starter_qbs
                        if str(row.get("player_team") or row.get("team") or "").upper() == team
                    ]
                    team_catchers = [
                        row for row in lineup
                        if str(row.get("player_team") or row.get("team") or "").upper() == team
                        and str(row.get("position") or "").upper() in {"WR", "TE"}
                    ]
                    if len(team_catchers) >= 2 and not team_qbs:
                        return False, f"Lineup {lineup_number} has two {team} pass catchers without their QB"
                captain = lineup[captain_index]
                captain_team = str(captain.get("player_team") or captain.get("team") or "").upper()
                captain_position = natural_positions[captain_index]
                own_qbs = [
                    row for row in starter_qbs
                    if str(row.get("player_team") or row.get("team") or "").upper() == captain_team
                ]
                own_catchers = [
                    row for row in lineup
                    if str(row.get("player_team") or row.get("team") or "").upper() == captain_team
                    and str(row.get("position") or "").upper() in {"WR", "TE"}
                ]
                if captain_position in {"WR", "TE"} and not own_qbs:
                    return False, f"Lineup {lineup_number} has pass-catcher CPT without same-team QB"
                if captain_position == "QB":
                    minimum = 1 if _is_high_rushing_qb(captain) else 2
                    if len(own_catchers) < minimum:
                        return False, f"Lineup {lineup_number} QB CPT requires {minimum} same-team WR/TE"

            salary = sum(_safe_float(row.get("salary")) for row in lineup)
            if salary > SALARY_CAP:
                return False, (
                    f"Lineup {lineup_number} salary {salary:.0f} exceeds "
                    f"the {SALARY_CAP} cap"
                )

            team_counts: dict[str, int] = {}
            for row, player_id in zip(lineup, player_ids):
                team = str(
                    row.get("player_team") or row.get("team") or ""
                ).strip().upper()
                if not team:
                    return (
                        False,
                        f"Lineup {lineup_number} player {player_id} is missing team",
                    )
                team_counts[team] = team_counts.get(team, 0) + 1
                exposure_counts[player_id] = exposure_counts.get(player_id, 0) + 1
                player_rows[player_id] = row
                if str(row.get("roster_position") or "").upper() == "CPT":
                    captain_counts[player_id] = captain_counts.get(player_id, 0) + 1
            if max(team_counts.values(), default=0) > 5:
                return (
                    False,
                    f"Lineup {lineup_number} exceeds the 5-player showdown team limit",
                )

            signature = tuple(sorted(zip(player_ids, roster_positions)))
            if signature in signatures and not allow_duplicate_lineups:
                return False, f"Lineup {lineup_number} duplicates an earlier showdown lineup"
            signatures.add(signature)

        over_exposed = sorted(
            player_id
            for player_id, count in exposure_counts.items()
            if count > exposure_limit
            and player_id not in (locked_player_ids or set())
        )
        if over_exposed:
            return False, (
                f"Player exposure exceeds {exposure_limit}/{requested_lineups}: "
                + ", ".join(over_exposed[:5])
            )
        if portfolio_policy and not allow_duplicate_lineups:
            rates = portfolio_exposure_rates or {}
            captain_rate = float(rates.get("captain", 0.60))
            captain_limit = max(1, int(math.ceil(requested_lineups * captain_rate)))
            over_captain = [pid for pid, count in captain_counts.items() if count > captain_limit]
            if over_captain:
                return False, f"Captain exposure exceeds {captain_rate:.0%}: " + ", ".join(over_captain)
            for player_id, count in exposure_counts.items():
                row = player_rows[player_id]
                rate = float(rates.get("core", 0.80))
                if str(row.get("position") or "").upper() == "QB" and bool(row.get("showdown_qb_eligible")):
                    rate = float(rates.get("starting_qb", 1.00))
                elif _safe_float(row.get("base_salary", row.get("salary"))) <= 1000:
                    rate = float(rates.get("cheap_punt", 0.40))
                if count > max(1, int(math.ceil(requested_lineups * rate))):
                    return False, f"Player {player_id} exceeds {rate:.0%} portfolio exposure"
        return True, ""

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
        df["strategy_projection_score"] = pd.to_numeric(
            df.get("optimizer_context_mean_score", df["projection"]),
            errors="coerce",
        ).fillna(df["projection"])
        df["strategy_p90_score"] = pd.to_numeric(
            df.get("optimizer_context_ceiling_score", df["p90"]),
            errors="coerce",
        ).fillna(df["p90"])
        salary_k = (df["salary"] / 1000).replace(0, pd.NA)
        df["ceil_per_k"] = (df["strategy_p90_score"] / salary_k).fillna(0)

        # Drop only the worst DSTs; always keep the top few to preserve feasibility
        dst_mask = df["position"].isin(["DST", "D", "DEF"])
        if dst_mask.any():
            dst_sorted = df[dst_mask].sort_values(
                "strategy_projection_score", ascending=False
            )
            keep_dst = dst_sorted.head(max(6, len(dst_sorted)))
            df = pd.concat([df[~dst_mask], keep_dst])

        team_field = "player_team" if "player_team" in df.columns else "team"
        df[team_field] = df[team_field].astype(str).str.upper()
        df["opponent_team"] = df.get("opponent_team", "").astype(str).str.upper()
        df["player_id"] = df["player_id"].astype(str)

        cash_cfg = {
            "score_field": "strategy_projection_score",
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
            "score_field": "strategy_p90_score",
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
            return (
                group.sort_values("strategy_p90_score", ascending=False)
                .groupby(team_field)
                .head(cap)
            )

        for pos, cap in cfg["team_caps"].items():
            mask = filtered["position"] == pos
            filtered = pd.concat([_cap_team(filtered[mask], cap), filtered[~mask]])

        # Stack safety: ensure QBs, pass-catchers, bring-backs, and one cheap relief piece survive filters
        rows_to_add: list[pd.DataFrame] = []
        for team, team_df in df.groupby(team_field):
            team_qb = team_df[team_df["position"] == "QB"].sort_values(
                "strategy_p90_score", ascending=False
            )
            if not team_qb.empty and filtered[(filtered["position"] == "QB") & (filtered[team_field] == team)].empty:
                rows_to_add.append(team_qb.head(1))

            pass_catchers = (
                team_df[team_df["position"].isin(["WR", "TE"])]
                .sort_values("strategy_p90_score", ascending=False)
                .head(2)
            )
            if not pass_catchers.empty:
                rows_to_add.append(pass_catchers)

            opp_team = str(team_df["opponent_team"].dropna().iloc[0]) if not team_df["opponent_team"].dropna().empty else ""
            if opp_team:
                opp_pool = df[
                    (df[team_field] == opp_team)
                    & (df["position"].isin(["WR", "TE", "RB"]))
                ].sort_values("strategy_p90_score", ascending=False)
                if not opp_pool.empty:
                    rows_to_add.append(opp_pool.head(1))

            cheap_pc = (
                team_df[
                    team_df["position"].isin(["WR", "TE"]) & (team_df["salary"] <= 4000)
                ]
                .sort_values("strategy_p90_score", ascending=False)
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

    def _select_strategy_candidates(
        self,
        pool: pd.DataFrame,
        *,
        strategy: str,
        contest_type: str,
    ) -> tuple[pd.DataFrame, dict[str, list[str]]]:
        """Apply post-eligibility candidate policy with player-level audit reasons."""
        if pool.empty:
            return pool.copy(), {}
        frame = pool.copy()
        frame["player_id"] = frame["player_id"].astype(str)
        frame["position"] = frame["position"].fillna("").astype(str).str.upper()
        frame["projection"] = pd.to_numeric(
            frame.get("projection", 0.0), errors="coerce"
        ).fillna(0.0)
        frame["p90"] = pd.to_numeric(
            frame.get("p90", frame["projection"]), errors="coerce"
        ).fillna(frame["projection"])
        frame["salary"] = pd.to_numeric(
            frame.get("salary", 0), errors="coerce"
        ).fillna(0.0)
        reasons: dict[str, list[str]] = {}

        def exclude(mask: pd.Series, reason: str) -> None:
            for player_id in frame.loc[mask, "player_id"]:
                reasons.setdefault(str(player_id), []).append(reason)

        if strategy == CLASSIC_HEAD_TO_HEAD_STRATEGY_ID:
            positive_projection = (frame["projection"] > 0) & (frame["p90"] > 0)
            exclude(~positive_projection, "no positive projection")
            keep = positive_projection.copy()
            if "is_starting_qb" in frame.columns:
                is_starting = frame["is_starting_qb"].map(
                    lambda value: value is True
                    or str(value).strip().lower() in {"1", "true", "t", "yes"}
                )
                specialty_role = frame.apply(
                    lambda row: has_explicit_specialty_role(row.to_dict()),
                    axis=1,
                )
                backup_qb = (
                    (frame["position"] == "QB")
                    & ~is_starting
                    & ~specialty_role
                )
                exclude(backup_qb, "backup QB / zero expected snaps")
                keep &= ~backup_qb
            return frame.loc[keep].reset_index(drop=True), reasons

        if strategy == CLASSIC_LARGE_GPP_STRATEGY_ID:
            working = frame.copy()
            if "is_starting_qb" in working.columns:
                is_starting = working["is_starting_qb"].map(
                    lambda value: value is True
                    or str(value).strip().lower() in {"1", "true", "t", "yes"}
                )
                specialty_role = working.apply(
                    lambda row: has_explicit_specialty_role(row.to_dict()),
                    axis=1,
                )
                backup_qb = (
                    (working["position"] == "QB")
                    & ~is_starting
                    & ~specialty_role
                )
                exclude(backup_qb, "backup QB / zero expected snaps")
                working = working.loc[~backup_qb].copy()
            no_projection = (working["projection"] <= 0) | (working["p90"] <= 0)
            for player_id in working.loc[no_projection, "player_id"]:
                reasons.setdefault(str(player_id), []).append("no positive projection")
            working = working.loc[~no_projection].copy()
            filtered = self._apply_pool_filters(working, contest_type="tournament")
            included_ids = set(filtered["player_id"].astype(str))
            salary_k = (working["salary"] / 1000.0).replace(0, pd.NA)
            working["strategy_p90_score"] = pd.to_numeric(
                working.get("optimizer_context_ceiling_score", working["p90"]),
                errors="coerce",
            ).fillna(working["p90"])
            working["ceil_per_k"] = (
                working["strategy_p90_score"] / salary_k
            ).fillna(0.0)
            config = {
                "QB": {"top": 14, "min_score": 17.0, "min_value": 3.0, "value": 3.0},
                "RB": {"top": 20, "min_score": 11.0, "min_value": 3.0, "value": 3.0},
                "WR": {"top": 34, "min_score": 10.0, "min_value": 3.4, "value": 3.4},
                "TE": {"top": 16, "min_score": 8.0, "min_value": 3.4, "value": 3.4},
                "DST": {"top": 12, "min_score": 0.0, "min_value": 0.0, "value": 0.0},
            }
            team_caps = {"RB": 2, "WR": 4, "TE": 3}
            team_field = "player_team" if "player_team" in working.columns else "team"
            working[team_field] = working[team_field].fillna("").astype(str).str.upper()
            for position, group in working.groupby("position"):
                position_config = config.get(position)
                if position_config is None:
                    continue
                ordered = group.sort_values("strategy_p90_score", ascending=False)
                position_rank = {
                    str(player_id): rank
                    for rank, player_id in enumerate(ordered["player_id"], start=1)
                }
                team_rank: dict[str, int] = {}
                for _team, team_group in group.groupby(team_field):
                    for rank, player_id in enumerate(
                        team_group.sort_values(
                            "strategy_p90_score", ascending=False
                        )["player_id"],
                        start=1,
                    ):
                        team_rank[str(player_id)] = rank
                for row in group.to_dict(orient="records"):
                    player_id = str(row["player_id"])
                    if player_id in included_ids:
                        continue
                    player_reasons = reasons.setdefault(player_id, [])
                    if float(row["ceil_per_k"]) < position_config["value"]:
                        player_reasons.append(
                            f"below GPP {position} value threshold"
                        )
                    if (
                        float(row["strategy_p90_score"])
                        < position_config["min_score"]
                        and float(row["ceil_per_k"]) < position_config["min_value"]
                    ):
                        player_reasons.append(
                            f"below GPP {position} ceiling threshold"
                        )
                    if position_rank[player_id] > position_config["top"]:
                        player_reasons.append("outside positional candidate cap")
                    if (
                        position in team_caps
                        and team_rank.get(player_id, 0) > team_caps[position]
                    ):
                        player_reasons.append("team candidate cap")
                    if not player_reasons:
                        player_reasons.append("not selected by Large GPP candidate ranking")
            return filtered.reset_index(drop=True), reasons

        filtered = self._apply_pool_filters(frame, contest_type=contest_type)
        included_ids = set(filtered["player_id"].astype(str))
        for player_id in set(frame["player_id"]) - included_ids:
            reasons[str(player_id)] = ["legacy strategy candidate filter"]
        return filtered.reset_index(drop=True), reasons

    def _solve_lineup(
        self,
        pool: pd.DataFrame,
        score_col: str = "p90",
        exposure_remaining: dict | None = None,
        captain_exposure_remaining: dict | None = None,
        exclude_lineups: List[set] | None = None,
        exclude_signatures: List[list[tuple[str, str | None]]] | None = None,
        enforce_single_te: bool = False,
        avoid_dst_opponents: bool = False,
        contest_type: str = "classic",
        stack_params: dict | None = None,
        locked_player_ids: set[str] | None = None,
        flex_only_player_ids: set[str] | None = None,
        rule_profile: StrategyProfile | None = None,
        quality_floor: dict[str, float] | None = None,
        portfolio_script: dict | None = None,
        locked_captain_player_id: str | None = None,
        include_control_comparison: bool = True,
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

        context_score_columns = {
            "cash_score", "h2h_score", "showdown_cash_score",
            "optimizer_context_ceiling_score", "gpp_score",
        }
        context_multiplier = 1.0 if score_col in context_score_columns else 0.0

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

        locked_ids = {str(player_id) for player_id in (locked_player_ids or set())}
        flex_only_ids = {
            str(player_id) for player_id in (flex_only_player_ids or set())
        }
        candidate_ids = set(pool["player_id"].astype(str))
        if locked_ids - candidate_ids:
            return None
        locked_captain_id = str(locked_captain_player_id or "").strip()
        if locked_captain_id and (
            locked_captain_id not in candidate_ids or locked_captain_id in flex_only_ids
        ):
            return None
        index_range = range(len(pool))
        contest_type = (contest_type or "classic").lower()
        params = stack_params or {}

        # Captain mode (Showdown): 1 CPT (1.5x points + salary) + 5 Flex
        if contest_type == "captain":
            if "captain_objective_multiplier" not in pool.columns:
                pool["captain_objective_multiplier"] = 1.0
            pool["captain_objective_multiplier"] = pd.to_numeric(
                pool["captain_objective_multiplier"], errors="coerce"
            ).fillna(1.0)
            cap_vars = pulp.LpVariable.dicts("captain", index_range, lowBound=0, upBound=1, cat="Binary")
            flex_vars = pulp.LpVariable.dicts("flex", index_range, lowBound=0, upBound=1, cat="Binary")

            model = pulp.LpProblem("DK_Captain", pulp.LpMaximize)
            objective_expression = pulp.lpSum(
                1.5
                * pool.loc[i, score_col]
                * pool.loc[i, "captain_objective_multiplier"]
                * cap_vars[i]
                + pool.loc[i, score_col] * flex_vars[i]
                for i in index_range
            )
            if bool(params.get("use_role_ownership", False)):
                ownership_weight = float(params.get("ownership_weight", 0.08))
                captain_ownership = pd.to_numeric(
                    pool.get("captain_ownership", np.nan), errors="coerce"
                )
                flex_ownership = pd.to_numeric(
                    pool.get("flex_ownership", np.nan), errors="coerce"
                )
                objective_expression -= ownership_weight * pulp.lpSum(
                    _safe_float(captain_ownership.iloc[i]) * cap_vars[i]
                    + _safe_float(flex_ownership.iloc[i]) * flex_vars[i]
                    for i in index_range
                )
            control_objective = pulp.lpSum(
                (pool.loc[i, score_col] - context_multiplier * _safe_float(pool.loc[i].get("optimizer_context_adjustment")))
                * (1.5 * pool.loc[i, "captain_objective_multiplier"] * cap_vars[i] + flex_vars[i])
                for i in index_range
            )
            if rule_profile is not None:
                rule_players = pool.to_dict(orient="records")
                correlation_terms = build_lineup_correlation_terms(
                    rule_players, profile=rule_profile
                )
                if bool(params.get("saturate_correlations", False)):
                    correlation_terms = [
                        term for term in correlation_terms
                        if not any(
                            trigger.rule_id in _SATURATED_SHOWDOWN_RULE_IDS
                            for trigger in term.evaluation.triggered_rules
                        )
                    ]
                objective_expression += add_lineup_correlation_objective(
                    model,
                    correlation_terms,
                    selected_vars={
                        i: cap_vars[i] + flex_vars[i] for i in index_range
                    },
                    captain_vars=cap_vars,
                    prefix="showdown_rule_correlation",
                )
                format_terms = build_format_specific_terms(
                    rule_players, profile=rule_profile
                )
                if bool(params.get("opportunity_gate", False)):
                    format_terms = [
                        term for term in format_terms
                        if term.kind != "showdown_fragile_punt"
                    ]
                objective_expression += add_format_specific_objective(
                    model,
                    format_terms,
                    selected_vars={
                        i: cap_vars[i] + flex_vars[i] for i in index_range
                    },
                    captain_vars=cap_vars,
                    prefix="showdown_format_rule",
                )
                if bool(params.get("saturate_correlations", False)):
                    objective_expression += _add_saturated_showdown_correlation_objective(
                        model,
                        pool,
                        {i: cap_vars[i] + flex_vars[i] for i in index_range},
                    )
            model += objective_expression

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
                if str(pool.loc[i, "player_id"]) in flex_only_ids:
                    model += cap_vars[i] == 0, f"flex_only_{i}"
                if str(pool.loc[i, "player_id"]) in locked_ids:
                    model += cap_vars[i] + flex_vars[i] == 1
            if locked_captain_id:
                model += pulp.lpSum(
                    cap_vars[i]
                    for i in index_range
                    if str(pool.loc[i, "player_id"]) == locked_captain_id
                ) == 1

            team_field = "player_team" if "player_team" in pool.columns else "team"
            normalized_teams = pool[team_field].astype(str).str.strip().str.upper()
            normalized_positions = pool["position"].astype(str).str.strip().str.upper()
            selected = {i: cap_vars[i] + flex_vars[i] for i in index_range}

            if bool(params.get("require_starting_qb", False)):
                starter_qbs = [
                    i for i in index_range
                    if normalized_positions.iloc[i] == "QB"
                    and bool(pool.loc[i].get("showdown_qb_eligible"))
                ]
                if not starter_qbs:
                    return None
                model += pulp.lpSum(selected[i] for i in starter_qbs) >= 1

            if bool(params.get("hard_qb_correlations", False)):
                for team in sorted(set(normalized_teams)):
                    qbs = [
                        i for i in index_range
                        if normalized_teams.iloc[i] == team
                        and normalized_positions.iloc[i] == "QB"
                        and bool(pool.loc[i].get("showdown_qb_eligible"))
                    ]
                    pass_catchers = [
                        i for i in index_range
                        if normalized_teams.iloc[i] == team
                        and normalized_positions.iloc[i] in {"WR", "TE"}
                    ]
                    qb_selected = pulp.lpSum(selected[i] for i in qbs)
                    if pass_catchers:
                        # Two same-team pass catchers require their starting QB.
                        model += pulp.lpSum(selected[i] for i in pass_catchers) <= (
                            1 + max(1, len(pass_catchers) - 1) * qb_selected
                        )
                    for receiver_index in pass_catchers:
                        if qbs:
                            model += cap_vars[receiver_index] <= qb_selected
                        else:
                            model += cap_vars[receiver_index] == 0
                    for qb_index in qbs:
                        minimum = 1 if _is_high_rushing_qb(pool.loc[qb_index]) else 2
                        if len(pass_catchers) >= minimum:
                            model += pulp.lpSum(selected[i] for i in pass_catchers) >= (
                                minimum * cap_vars[qb_index]
                            )
                        else:
                            model += cap_vars[qb_index] == 0

            script = dict(portfolio_script or {})
            script_kind = str(script.get("kind") or "")
            script_team = str(script.get("team") or "").upper()
            teams = sorted(team for team in set(normalized_teams) if team)
            if script_kind == "shootout" and len(teams) == 2:
                for team in teams:
                    team_indexes = [i for i in index_range if normalized_teams.iloc[i] == team]
                    team_qbs = [i for i in team_indexes if normalized_positions.iloc[i] == "QB"]
                    model += pulp.lpSum(selected[i] for i in team_indexes) >= 2
                    if team_qbs:
                        model += pulp.lpSum(selected[i] for i in team_qbs) >= 1
            elif script_kind in {"pass_led", "run_control"} and script_team:
                team_indexes = [i for i in index_range if normalized_teams.iloc[i] == script_team]
                model += pulp.lpSum(selected[i] for i in team_indexes) >= 4
                model += pulp.lpSum(cap_vars[i] for i in team_indexes) == 1
            elif script_kind == "contrarian" and script_team:
                team_indexes = [i for i in index_range if normalized_teams.iloc[i] == script_team]
                model += pulp.lpSum(selected[i] for i in team_indexes) >= 4
                model += pulp.lpSum(cap_vars[i] for i in team_indexes) == 1
                if "captain_ownership" in pool.columns:
                    team_ownership = pd.to_numeric(
                        pool.loc[team_indexes, "captain_ownership"], errors="coerce"
                    ).dropna()
                    if not team_ownership.empty:
                        median_ownership = float(team_ownership.median())
                        for i in team_indexes:
                            ownership = pd.to_numeric(
                                pd.Series([pool.loc[i, "captain_ownership"]]), errors="coerce"
                            ).iloc[0]
                            if pd.notna(ownership) and float(ownership) > median_ownership:
                                model += cap_vars[i] == 0

            if quality_floor:
                mean_expression = pulp.lpSum(
                    pool.loc[i, "projection"] * (1.5 * cap_vars[i] + flex_vars[i])
                    for i in index_range
                )
                p90_expression = pulp.lpSum(
                    pool.loc[i, "p90"] * (1.5 * cap_vars[i] + flex_vars[i])
                    for i in index_range
                )
                model += mean_expression >= float(quality_floor["mean"])
                model += p90_expression >= float(quality_floor["p90"])

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

            if bool(params.get("require_qb_captain_receiver", False)):
                team_field = (
                    "player_team" if "player_team" in pool.columns else "team"
                )
                normalized_teams = pool[team_field].astype(str).str.strip().str.upper()
                normalized_positions = pool["position"].astype(str).str.strip().str.upper()
                for quarterback_index in [
                    i for i in index_range if normalized_positions.iloc[i] == "QB"
                ]:
                    quarterback_team = normalized_teams.iloc[quarterback_index]
                    receiver_indexes = [
                        i
                        for i in index_range
                        if i != quarterback_index
                        and normalized_teams.iloc[i] == quarterback_team
                        and normalized_positions.iloc[i] in {"WR", "TE"}
                    ]
                    if receiver_indexes:
                        model += (
                            pulp.lpSum(flex_vars[i] for i in receiver_indexes)
                            >= cap_vars[quarterback_index]
                        )
                    else:
                        model += cap_vars[quarterback_index] == 0

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
                    if (
                        pid not in locked_ids
                        and remaining is not None
                        and remaining <= 0
                    ):
                        model += cap_vars[i] == 0
                        model += flex_vars[i] == 0
            if captain_exposure_remaining:
                for i in index_range:
                    pid = str(pool.loc[i, "player_id"])
                    if captain_exposure_remaining.get(pid, 1) <= 0:
                        model += cap_vars[i] == 0

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

            scored_objective_value = float(pulp.value(model.objective) or 0.0)
            scored_values = {v.name: v.value() for v in model.variables()}
            replay = solve_control(model, control_objective) if include_control_comparison else None
            if replay is not None:
                replay["variable_players"] = {
                    variable.name: {"player_id": str(pool.loc[i, "player_id"]), "roster_position": slot}
                    for slot, variables in (("CPT", cap_vars), ("FLEX", flex_vars))
                    for i, variable in variables.items()
                }
            paired_rows = []
            value_sets = [scored_values]
            if replay is not None:
                value_sets.append(replay["values"])
            for values in value_sets:
                lineup_rows = []
                for i in index_range:
                    selected_cap = values.get(cap_vars[i].name, 0) >= 0.9
                    selected_flex = values.get(flex_vars[i].name, 0) >= 0.9
                    if selected_cap or selected_flex:
                        row = pool.loc[i].to_dict()
                        base_salary = _safe_float(row.get("salary"))
                        base_projection = _safe_float(row.get("projection"))
                        base_p90 = _safe_float(row.get("p90", base_projection))
                        base_objective = _safe_float(
                            row.get(score_col, row.get("projection"))
                        )
                        captain_objective_multiplier = _safe_float(
                            row.get("captain_objective_multiplier")
                        ) or 1.0
                        row["base_salary"] = base_salary
                        row["base_projection"] = base_projection
                        row["base_p90"] = base_p90
                        row["is_captain"] = bool(selected_cap)
                        if selected_cap:
                            captain_site_id = row.get("dk_captain_id")
                            if captain_site_id is not None and not pd.isna(captain_site_id):
                                captain_site_id = str(captain_site_id).strip()
                                if captain_site_id:
                                    row["dk_player_id"] = captain_site_id
                            row["salary"] = base_salary * 1.5
                            row["projection"] = base_projection * 1.5
                            row["p90"] = base_p90 * 1.5
                            row["objective_score"] = (
                                base_objective * 1.5 * captain_objective_multiplier
                            )
                            row["roster_position"] = "CPT"
                            row["ownership"] = (
                                _safe_float(row.get("captain_ownership"))
                                if pd.notna(row.get("captain_ownership")) else None
                            )
                        else:
                            row["salary"] = base_salary
                            row["projection"] = base_projection
                            row["p90"] = base_p90
                            row["objective_score"] = base_objective
                            row["roster_position"] = "FLEX"
                            row["ownership"] = (
                                _safe_float(row.get("flex_ownership"))
                                if pd.notna(row.get("flex_ownership")) else None
                            )
                        row["ownership_roster_position"] = row["roster_position"]
                        row["ownership_input_status"] = (
                            "available" if row.get("ownership") is not None else "unavailable"
                        )
                        lineup_rows.append(row)
                paired_rows.append(lineup_rows)
            lineup_rows = paired_rows[0]
            lineup_rows[0]["solver_objective_value"] = scored_objective_value
            if replay is not None:
                lineup_rows[0]["lineup_control_comparison"] = build_comparison(
                    lineup_rows, paired_rows[1], replay, profile=rule_profile,
                    context_multiplier=context_multiplier,
                )
            return lineup_rows

        # Decision variables
        x = pulp.LpVariable.dicts("player", index_range, lowBound=0, upBound=1, cat="Binary")

        model = pulp.LpProblem("DK_Lineup", pulp.LpMaximize)
        objective_expression = pulp.lpSum(
            pool.loc[i, score_col] * x[i] for i in index_range
        )
        control_objective = pulp.lpSum(
            (pool.loc[i, score_col] - context_multiplier * _safe_float(pool.loc[i].get("optimizer_context_adjustment"))) * x[i]
            for i in index_range
        )
        if rule_profile is not None:
            rule_players = pool.to_dict(orient="records")
            correlation_terms = build_lineup_correlation_terms(
                rule_players, profile=rule_profile
            )
            objective_expression += add_lineup_correlation_objective(
                model,
                correlation_terms,
                selected_vars=x,
                prefix="classic_rule_correlation",
            )
            objective_expression += add_format_specific_objective(
                model,
                build_format_specific_terms(
                    rule_players, profile=rule_profile
                ),
                selected_vars=x,
                prefix="classic_format_rule",
            )
        else:
            correlation_bonus = float(
                params.get("correlation_bonus", 0.0) or 0.0
            )
        if rule_profile is None and correlation_bonus > 0:
            team_field = "player_team" if "player_team" in pool.columns else "team"
            for qb_index in [
                i for i in index_range if str(pool.loc[i, "position"]).upper() == "QB"
            ]:
                quarterback_team = str(pool.loc[qb_index, team_field]).upper()
                for receiver_index in [
                    i
                    for i in index_range
                    if i != qb_index
                    and str(pool.loc[i, team_field]).upper() == quarterback_team
                    and str(pool.loc[i, "position"]).upper() in {"WR", "TE"}
                ]:
                    pair = pulp.LpVariable(
                        f"soft_stack_{qb_index}_{receiver_index}",
                        lowBound=0,
                        upBound=1,
                        cat="Binary",
                    )
                    model += pair <= x[qb_index]
                    model += pair <= x[receiver_index]
                    model += pair >= x[qb_index] + x[receiver_index] - 1
                    objective_expression += correlation_bonus * pair
        model += objective_expression

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

        for i in index_range:
            if str(pool.loc[i, "player_id"]) in locked_ids:
                model += x[i] == 1

        # Exposure caps (remaining count for each player across multi-lineup generation)
        if exposure_remaining:
            for i in index_range:
                pid = str(pool.loc[i, "player_id"])
                remaining = exposure_remaining.get(pid)
                if (
                    pid not in locked_ids
                    and remaining is not None
                    and remaining <= 0
                ):
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
        replay = solve_control(model, control_objective)
        replay["variable_players"] = {
            variable.name: {"player_id": str(pool.loc[i, "player_id"]), "roster_position": str(pool.loc[i, "position"])}
            for i, variable in x.items()
        }
        control_rows = [pool.loc[i].to_dict() for i in index_range if replay["values"].get(x[i].name, 0) >= 0.9]
        lineup_rows[0]["lineup_control_comparison"] = build_comparison(
            lineup_rows, control_rows, replay, profile=rule_profile,
            context_multiplier=context_multiplier,
        )
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
        optimizer_run_id: str | None = None,
    ) -> OptimizerJob:
        job_id = optimizer_run_id or str(uuid.uuid4())
        if optimizer_run_id:
            existing = self.get_job(optimizer_run_id)
            if existing is not None and existing.status == "completed":
                return existing
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        params = dict(params or {})

        contest_format, objective, contest_type = resolve_optimizer_mode(
            contest_format=contest_format,
            objective=objective,
            params=params,
        )
        strategy_config = resolve_optimizer_strategy(
            contest_format=contest_format,
            objective=objective,
            strategy=strategy,
        )
        strategy = str(strategy_config["strategy_id"])
        params["strategy_config"] = strategy_config
        optimizer_rules = (
            showdown_optimizer_rules(strategy)
            if contest_format == "showdown"
            else []
        )
        params["optimizer_rules"] = optimizer_rules
        require_qb_captain_receiver = any(
            rule.get("rule_id") == SHOWDOWN_QB_CAPTAIN_RECEIVER_RULE_ID
            for rule in optimizer_rules
        )
        if strategy == CLASSIC_GPP_ADVANCED_STRATEGY_ID:
            unsupported_stack_fields = {
                field
                for field in (
                    "stack_policy_id",
                    "stack_min",
                    "stack_max",
                    "bringback",
                    "include_rb_in_stack",
                    "bringback_positions",
                )
                if field in params
            }
            if unsupported_stack_fields:
                raise ValueError(
                    f"{CLASSIC_GPP_ADVANCED_STRATEGY_ID} owns its slate-aware "
                    "stack policy and cannot be combined with: "
                    + ", ".join(sorted(unsupported_stack_fields))
                )
        if strategy == CLASSIC_HEAD_TO_HEAD_STRATEGY_ID:
            params["objective_config"] = head_to_head_objective_config()
        elif contest_format == "classic" and objective == "cash":
            params["objective_config"] = cash_objective_config()
        if contest_format == "showdown":
            informed_showdown = (
                strategy in SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_IDS
            )
            settings = get_settings()
            params["objective_config"] = {
                "objective_id": strategy,
                "score_column": "showdown_cash_score" if objective == "cash" else "optimizer_context_ceiling_score",
                "scoring_version": "showdown_cash_distribution_v1" if objective == "cash" else "context_ceiling_v1",
                "captain_multiplier": 1.5,
                "captain_slots": 1,
                "flex_slots": 5,
                "salary_cap": SALARY_CAP,
                "max_players_per_team": 5,
                "starter_qb_policy": "one_per_team_evidence_hierarchy_v1",
                "optimizer_rules": optimizer_rules,
                "evidence_status": strategy_config["evidence_status"],
            }
            if informed_showdown:
                params["objective_config"].update(
                    {
                        "captain_model_path": settings.showdown_captain_model_path,
                        "captain_prior_strength": settings.showdown_captain_prior_strength,
                        "captain_evaluation_slates": 39,
                    }
                )
        if strategy == CLASSIC_GPP_ADVANCED_STRATEGY_ID:
            stack_policy = {
                "policy_id": "classic_gpp_slate_aware_stack_v1",
                "contest_format": "classic",
                "objective": "gpp",
                "enabled": True,
                "stack_min": 1,
                "stack_max": None,
                "bringback": True,
                "include_rb_in_stack": True,
                "bringback_positions": ["RB", "WR", "TE"],
                "evidence_status": "resolved_at_runtime",
                "description": (
                    "The selected strategy resolves the exact stack minimum "
                    "from slate size at runtime."
                ),
                "source": "optimizer_strategy",
            }
        elif strategy == CLASSIC_HEAD_TO_HEAD_STRATEGY_ID:
            stack_policy = {
                "policy_id": "classic_head_to_head_optional_stack_unconstrained_v1",
                "contest_format": "classic",
                "objective": "cash",
                "enabled": False,
                "stack_min": 0,
                "stack_max": None,
                "bringback": False,
                "include_rb_in_stack": False,
                "bringback_positions": [],
                "correlation_bonus": DEFAULT_HEAD_TO_HEAD_OBJECTIVE.correlation_bonus,
                "evidence_status": "explicit_contest_strategy",
                "description": "Correlation is rewarded softly; no stack or bring-back is required.",
                "source": "optimizer_strategy",
            }
        elif strategy == CLASSIC_LARGE_GPP_STRATEGY_ID:
            stack_policy = {
                "policy_id": "classic_large_gpp_flexible_stacks_v1",
                "contest_format": "classic",
                "objective": "gpp",
                "enabled": True,
                "stack_min": 1,
                "stack_max": None,
                "bringback": False,
                "include_rb_in_stack": True,
                "bringback_positions": ["RB", "WR", "TE"],
                "stack_templates": params.get(
                    "stack_templates", [[1, 0], [1, 1], [2, 0], [2, 1]]
                ),
                "evidence_status": "explicit_contest_strategy",
                "description": "Portfolio cycles QB+1/QB+2 with optional bring-backs.",
                "source": "optimizer_strategy",
            }
        else:
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
        initial_pool = pool.copy()
        eligible_pool_ids: set[str] = set()
        exclusion_reasons: dict[str, list[str]] = {}
        exclusion_details: dict[str, list[dict]] = {}
        player_warnings: dict[str, list[dict]] = {}
        safety_audit_by_player: dict[str, dict] = {}
        context_audit_by_player: dict[str, dict] = {}
        flex_only_ids = normalize_canonical_player_ids(
            params.get("flex_only_player_ids"),
            field_name="flex_only_player_ids",
        )
        resolved_flex_ids, flex_only_names = _resolve_player_control_names(
            initial_pool,
            params.get("flex_only_players"),
            field_name="FLEX-only",
        )
        flex_only_ids.update(resolved_flex_ids)
        if flex_only_ids and contest_format != "showdown":
            raise ValueError("FLEX-only player controls require Showdown format")
        initial_player_ids = (
            set(initial_pool["player_id"].astype(str))
            if not initial_pool.empty and "player_id" in initial_pool
            else set()
        )
        missing_flex_only_ids = flex_only_ids - initial_player_ids
        if missing_flex_only_ids:
            raise ValueError(
                "FLEX-only canonical player IDs were not found in the selected slate: "
                + ", ".join(sorted(missing_flex_only_ids))
            )
        params["flex_only_player_ids"] = sorted(flex_only_ids)
        params["flex_only_players"] = sorted(flex_only_names)
        exclude_ids = normalize_canonical_player_ids(
            params.get("exclude_player_ids"),
            field_name="exclude_player_ids",
        )
        lock_values: list = []
        for lock_field in ("lock_player_ids", "locked_player_ids"):
            field_values = params.get(lock_field)
            if field_values is None:
                continue
            if isinstance(field_values, str):
                lock_values.append(field_values)
            else:
                lock_values.extend(field_values)
        locked_ids = normalize_canonical_player_ids(
            lock_values,
            field_name="locked_player_ids",
        )
        conflicting_controls = exclude_ids & locked_ids
        if conflicting_controls:
            raise ValueError(
                "Players cannot be both locked and excluded: "
                + ", ".join(sorted(conflicting_controls))
            )
        conflicting_flex_exclusions = exclude_ids & flex_only_ids
        if conflicting_flex_exclusions:
            raise ValueError(
                "Players cannot be both FLEX-only and excluded: "
                + ", ".join(sorted(conflicting_flex_exclusions))
            )
        roster_size = 6 if contest_format == "showdown" else 9
        if len(locked_ids) > roster_size:
            raise ValueError(
                f"At most {roster_size} canonical players can be locked for "
                f"{contest_format}"
            )
        params["locked_player_ids"] = sorted(locked_ids)

        rule_profile = resolve_strategy_profile(
            contest_format=contest_format,
            objective=objective,
        )
        if contest_format == "showdown" and objective == "cash":
            params["objective_config"]["objective_weights"] = dict(rule_profile.objective_weights)
        params.setdefault("strategy_runtime", {})["lineup_correlation"] = {
            "library_id": LINEUP_CORRELATION_LIBRARY_ID,
            "library_version": LINEUP_CORRELATION_LIBRARY_VERSION,
            "profile_id": rule_profile.profile_id,
            "profile_version": rule_profile.version,
            "objective_multiplier": 1.0,
            "evidence_status": "initial_policy_unvalidated",
        }
        safety_result = evaluate_player_pool_safety(
            pool,
            profile=rule_profile,
            expected_slate_teams=params.get("slate_teams"),
            as_of=datetime.now(timezone.utc),
            projection_cutoff=data_cutoff_at,
            user_excluded_player_ids=exclude_ids,
        )
        pool = safety_result.eligible_pool
        params.setdefault("strategy_runtime", {})["player_pool_safety"] = (
            safety_result.summary
        )
        for audit_row in safety_result.audit_rows:
            player_id = str(audit_row.get("player_id") or "")
            if not player_id:
                continue
            safety_audit_by_player[player_id] = audit_row
            exclusion_reasons[player_id] = list(
                audit_row.get("exclusion_reasons") or []
            )
            exclusion_details[player_id] = list(
                audit_row.get("exclusion_details") or []
            )
            player_warnings[player_id] = list(audit_row.get("warnings") or [])

        context_result = score_player_context(pool, profile=rule_profile)
        pool = context_result.scored_pool
        raw_pool_ids = (
            set(pool["player_id"].astype(str))
            if not pool.empty and "player_id" in pool else set()
        )
        opportunity_eligible_ids = set(raw_pool_ids)
        params.setdefault("strategy_runtime", {})["context_scoring"] = (
            context_result.summary
        )
        for audit_row in context_result.audit_rows:
            player_id = str(audit_row.get("player_id") or "")
            if not player_id:
                continue
            context_audit_by_player[player_id] = audit_row
            warnings = player_warnings.setdefault(player_id, [])
            for warning in audit_row.get("warnings") or []:
                if not any(
                    existing.get("reason_code") == warning.get("reason_code")
                    for existing in warnings
                ):
                    warnings.append(warning)

        if strategy == SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID or strategy in SHOWDOWN_SINGLE_ENTRY_STRATEGY_IDS:
            pool, opportunity_excluded = apply_showdown_opportunity_gate(pool)
            opportunity_eligible_ids = set(pool["player_id"].astype(str))
            for player_id in opportunity_excluded:
                reason = "showdown_low_opportunity_skill_player"
                exclusion_reasons.setdefault(player_id, []).append(reason)
                exclusion_details.setdefault(player_id, []).append(
                    {
                        "rule_id": "showdown_low_opportunity_skill_gate_v2",
                        "reason_code": reason,
                        "description": (
                            "RB/WR/TE has no identified current opportunity path and "
                            "falls below the applicable low-salary mean and P90 thresholds."
                        ),
                        "category": ExclusionCategory.STRATEGY.value,
                    }
                )
            params.setdefault("strategy_runtime", {})["opportunity_gate"] = {
                "rule_id": "showdown_low_opportunity_skill_gate_v2",
                "excluded_player_ids": sorted(opportunity_excluded),
                "positions": ["RB", "WR", "TE"],
                "thresholds": {
                    "legacy_punt": {"salary_max": 1000, "mean_max": 3, "p90_max": 10},
                    "low_salary_fallback": {"salary_max": 2000, "mean_max": 2, "p90_max": 8},
                },
            }

        def record_pool_exclusions(
            before: pd.DataFrame,
            after: pd.DataFrame,
            reason: str,
            category: ExclusionCategory | None = None,
        ) -> None:
            if before.empty or "player_id" not in before:
                return
            after_ids = (
                set(after["player_id"].astype(str))
                if not after.empty and "player_id" in after
                else set()
            )
            for player_id in set(before["player_id"].astype(str)) - after_ids:
                reasons = exclusion_reasons.setdefault(player_id, [])
                if reason not in reasons:
                    reasons.append(reason)
                detail = {
                    "rule_id": None,
                    "reason_code": reason,
                    "description": reason.replace("_", " "),
                    "category": (
                        category or categorize_exclusion_reason(reason)
                    ).value,
                }
                details = exclusion_details.setdefault(player_id, [])
                if not any(
                    row.get("reason_code") == reason for row in details
                ):
                    details.append(detail)

        before_availability_filter = pool.copy()
        pool, _ = restrict_pool_to_pregame_available(pool)
        record_pool_exclusions(
            before_availability_filter,
            pool,
            "pregame_unavailable",
        )

        pool_failure_message: str | None = None
        if contest_format == "showdown" and not pool.empty:
            try:
                if strategy in SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_IDS:
                    settings = get_settings()
                    pool, captain_runtime = build_showdown_captain_prior(
                        pool,
                        model_path=settings.showdown_captain_model_path,
                        strength=settings.showdown_captain_prior_strength,
                    )
                    params.setdefault("strategy_runtime", {})[
                        "captain_position_model"
                    ] = captain_runtime
                before_starter_filter = pool.copy()
                pool, starter_runtime = restrict_showdown_pool_to_starting_qbs(pool)
                record_pool_exclusions(
                    before_starter_filter,
                    pool,
                    "not_selected_starting_qb",
                )
                params.setdefault("strategy_runtime", {})[
                    "starter_qb_filter"
                ] = starter_runtime
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                pool_failure_message = f"Showdown optimizer blocked: {exc}"
                record_pool_exclusions(pool, pd.DataFrame(), "starter_validation_failed")
                pool = pd.DataFrame()
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
        # Classic removes deep punt rows; Showdown permits every positive salary.
        if not pool.empty:
            before_salary_filter = pool.copy()
            pool = pool.copy()
            pool["salary"] = pd.to_numeric(pool.get("salary", 0), errors="coerce")
            minimum_salary = MIN_SALARY if contest_format == "classic" else 1
            pool = pool[pool["salary"] >= minimum_salary]
            pool = pool.reset_index(drop=True)
            record_pool_exclusions(
                before_salary_filter,
                pool,
                "below_minimum_salary",
            )
        eligible_pool_ids = (
            set(pool["player_id"].astype(str))
            if not pool.empty and "player_id" in pool
            else set()
        )
        # Optional hard exclusions by player name/id passed in params
        exclude_names = {
            str(name).lower().strip(): str(name).lower().strip()
            for name in params.get("exclude_players", [])
            if str(name).strip()
        }
        conflicting_flex_names = {
            _normalize_alias(name) for name in flex_only_names
        } & {_normalize_alias(name) for name in exclude_names}
        if conflicting_flex_names:
            raise ValueError(
                "Players cannot be both FLEX-only and excluded: "
                + ", ".join(sorted(conflicting_flex_names))
            )
        exclusions_present = bool(exclude_names or exclude_ids)
        if not pool.empty and exclusions_present:
            before_user_exclusions = pool.copy()
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
            record_pool_exclusions(
                before_user_exclusions,
                pool,
                "user_excluded",
                ExclusionCategory.USER,
            )

        candidate_ids_before_strategy = (
            set(pool["player_id"].astype(str))
            if not pool.empty and "player_id" in pool
            else set()
        )
        unavailable_locks = locked_ids - candidate_ids_before_strategy
        if unavailable_locks:
            details = []
            for player_id in sorted(unavailable_locks):
                reasons = exclusion_reasons.get(player_id) or [
                    "not_found_in_selected_slate"
                ]
                details.append(f"{player_id} ({', '.join(reasons)})")
            raise ValueError(
                "Locked players must pass identity and eligibility checks: "
                + "; ".join(details)
            )

        if not pool.empty and contest_type != "captain":
            pre_strategy_pool = pool.copy()
            pool, strategy_exclusions = self._select_strategy_candidates(
                pool,
                strategy=strategy,
                contest_type=contest_type,
            )
            for player_id, player_reasons in strategy_exclusions.items():
                if player_id in locked_ids:
                    continue
                for reason in player_reasons:
                    reasons = exclusion_reasons.setdefault(player_id, [])
                    if reason not in reasons:
                        reasons.append(reason)
                    details = exclusion_details.setdefault(player_id, [])
                    if not any(
                        row.get("reason_code") == reason for row in details
                    ):
                        details.append(
                            {
                                "rule_id": None,
                                "reason_code": reason,
                                "description": reason,
                                "category": categorize_exclusion_reason(
                                    reason
                                ).value,
                            }
                        )
            selected_ids = set(pool["player_id"].astype(str))
            restore_ids = locked_ids - selected_ids
            if restore_ids:
                locked_rows = pre_strategy_pool.loc[
                    pre_strategy_pool["player_id"].astype(str).isin(restore_ids)
                ]
                pool = pd.concat([pool, locked_rows], ignore_index=True)
        if not pool.empty and contest_format == "showdown" and objective == "cash":
            pool = build_showdown_cash_objective(pool)
        if not pool.empty and strategy == CLASSIC_HEAD_TO_HEAD_STRATEGY_ID:
            pool = build_head_to_head_objective(pool)
            pool["h2h_score_before_context"] = pool["h2h_score"]
            pool["h2h_score"] += pd.to_numeric(
                pool.get("optimizer_context_adjustment", 0.0), errors="coerce"
            ).fillna(0.0)
            pool["h2h_objective_explanation"] = pool.apply(
                lambda row: {
                    **dict(row["h2h_objective_explanation"]),
                    "context_adjustment": float(
                        row["optimizer_context_adjustment"]
                    ),
                    "h2h_score_before_context": float(
                        row["h2h_score_before_context"]
                    ),
                    "h2h_score": float(row["h2h_score"]),
                },
                axis=1,
            )
        elif not pool.empty and contest_format == "classic" and objective == "cash":
            pool = build_classic_cash_objective(pool)
            pool["cash_score_before_context"] = pool["cash_score"]
            pool["cash_score"] += pd.to_numeric(
                pool.get("optimizer_context_adjustment", 0.0), errors="coerce"
            ).fillna(0.0)
            pool["cash_objective_explanation"] = pool.apply(
                lambda row: {
                    **dict(row["cash_objective_explanation"]),
                    "context_adjustment": float(
                        row["optimizer_context_adjustment"]
                    ),
                    "cash_score_before_context": float(
                        row["cash_score_before_context"]
                    ),
                    "cash_score": float(row["cash_score"]),
                },
                axis=1,
            )
        params.setdefault("strategy_runtime", {})["player_controls"] = {
            "locked_player_ids": sorted(locked_ids),
            "excluded_player_ids": sorted(exclude_ids),
            "excluded_player_names": sorted(exclude_names),
            "flex_only_player_ids": sorted(flex_only_ids),
            "flex_only_player_names": sorted(flex_only_names),
        }

        if pool.empty:
            lineup_results: List[List[dict]] = []
            status = "failed"
            message = pool_failure_message or "Optimizer failed: no salaries found for this slate."
        else:
            pool = pool.reset_index(drop=True)
            id_to_index = {str(pool.loc[i, "player_id"]): i for i in pool.index}
            num_lineups = max(1, int(params.get("num_lineups", 1)))
            params["num_lineups"] = num_lineups
            max_exposure_raw = params.get("max_exposure", 1.0)
            try:
                max_exposure = float(max_exposure_raw)
            except Exception:  # noqa: BLE001
                max_exposure = 1.0
            if max_exposure > 1.0:
                max_exposure = max_exposure / 100.0
            max_exposure = max(0.01, min(1.0, max_exposure))
            score_col = {
                "cash": "cash_score",
                "tournament": "optimizer_context_ceiling_score",
                "captain": "optimizer_context_ceiling_score",
            }.get(contest_type, "optimizer_context_ceiling_score")
            if strategy == CLASSIC_HEAD_TO_HEAD_STRATEGY_ID:
                score_col = "h2h_score"
            if contest_format == "showdown" and objective == "cash":
                score_col = "showdown_cash_score"
            if contest_format == "classic" and objective == "gpp":
                pool["gpp_score"] = pd.to_numeric(
                    pool["optimizer_context_ceiling_score"], errors="coerce"
                ).fillna(0.0)
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
            stack_cfg["require_qb_captain_receiver"] = (
                require_qb_captain_receiver
            )
            portfolio_v3 = strategy == SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID
            single_entry = strategy in SHOWDOWN_SINGLE_ENTRY_STRATEGY_IDS
            if portfolio_v3 or single_entry:
                stack_cfg.update(
                    {
                        "require_starting_qb": single_entry or num_lineups <= 5,
                        "hard_qb_correlations": True,
                        "opportunity_gate": True,
                        "saturate_correlations": True,
                        "use_role_ownership": bool(
                            {"captain_ownership", "flex_ownership"} <= set(pool.columns)
                            and pd.to_numeric(pool["captain_ownership"], errors="coerce").notna().any()
                            and pd.to_numeric(pool["flex_ownership"], errors="coerce").notna().any()
                        ),
                        "ownership_weight": float(params.get("ownership_weight", 0.08)),
                    }
                )

            def _run_baseline() -> tuple[list[list[dict]], str, str]:
                exposure_limit = max(1, int(math.ceil(num_lineups * max_exposure)))
                used_counts: dict[str, int] = {}
                captain_counts: dict[str, int] = {}
                exclude_lineups: List[set] = []
                exclude_signatures: List[list[tuple[str, str | None]]] = []
                lineup_results_local: List[List[dict]] = []

                captain_rate = normalize_exposure_rate(
                    params.get("captain_max_exposure"), default=0.60
                )
                core_rate = normalize_exposure_rate(
                    params.get("core_player_max_exposure"), default=0.80
                )
                qb_rate = normalize_exposure_rate(
                    params.get("starting_qb_max_exposure"), default=1.00
                )
                punt_rate = normalize_exposure_rate(
                    params.get("cheap_punt_max_exposure"), default=0.40
                )
                params.update({
                    "captain_max_exposure": captain_rate,
                    "core_player_max_exposure": core_rate,
                    "starting_qb_max_exposure": qb_rate,
                    "cheap_punt_max_exposure": punt_rate,
                })
                captain_limit = max(1, int(math.ceil(num_lineups * captain_rate)))
                player_limits: dict[str, int] = {}
                for _, row in pool.iterrows():
                    pid = str(row["player_id"])
                    rate = core_rate
                    if str(row.get("position") or "").upper() == "QB" and bool(
                        row.get("showdown_qb_eligible")
                    ):
                        rate = qb_rate
                    elif _safe_float(row.get("salary")) <= 1000:
                        rate = punt_rate
                    player_limits[pid] = max(1, int(math.ceil(num_lineups * rate)))

                team_implied: dict[str, float] = {}
                if portfolio_v3:
                    for team, team_rows in pool.groupby("player_team"):
                        raw_values = (
                            team_rows["team_implied_total"]
                            if "team_implied_total" in team_rows.columns
                            else pd.Series(np.nan, index=team_rows.index)
                        )
                        values = pd.to_numeric(raw_values, errors="coerce").dropna()
                        team_implied[str(team).upper()] = float(values.max()) if not values.empty else 0.0
                ordered_teams = sorted(team_implied, key=lambda team: (-team_implied[team], team))
                scripts: list[dict] = []
                if portfolio_v3 and num_lineups == 5 and len(ordered_teams) >= 2:
                    scripts = [
                        {"script_id": "shootout_1", "kind": "shootout", "label": "Shootout"},
                        {"script_id": "shootout_2", "kind": "shootout", "label": "Shootout"},
                        {"script_id": f"{ordered_teams[0]}_run_control", "kind": "run_control", "team": ordered_teams[0], "label": f"{ordered_teams[0]} run-control"},
                        {"script_id": f"{ordered_teams[1]}_pass_led", "kind": "pass_led", "team": ordered_teams[1], "label": f"{ordered_teams[1]} pass-led"},
                        {"script_id": f"{ordered_teams[1]}_contrarian", "kind": "contrarian", "team": ordered_teams[1], "label": f"Contrarian {ordered_teams[1]} script"},
                    ]
                quality_floor: dict[str, float] | None = None
                captain_diversification: dict = {
                    "enabled": portfolio_v3 and num_lineups >= 10,
                    "minimum_distinct_target": 0,
                    "both_teams_target": False,
                    "qualifying_captain_candidates": [],
                    "quality_rejected_captain_candidates": [],
                    "other_rejected_captain_candidates": [],
                    "planned_captain_player_ids": [],
                    "final_captain_exposures": [],
                    "targets_achieved": True,
                    "limitations": [],
                }
                forced_captain_ids: list[str] = []
                if portfolio_v3:
                    reference_lineup = self._solve_lineup(
                        pool,
                        score_col=score_col,
                        enforce_single_te=enforce_single_te,
                        avoid_dst_opponents=avoid_dst_opponents,
                        contest_type=contest_type,
                        stack_params=stack_cfg,
                        locked_player_ids=locked_ids,
                        flex_only_player_ids=flex_only_ids,
                        rule_profile=rule_profile,
                    )
                    if reference_lineup:
                        quality_floor = {
                            "mean": 0.85 * sum(_safe_float(row.get("projection")) for row in reference_lineup),
                            "p90": 0.90 * sum(_safe_float(row.get("p90")) for row in reference_lineup),
                        }
                    params.setdefault("strategy_runtime", {})["showdown_portfolio_policy"] = {
                        "policy_id": "showdown_five_entry_portfolio_v3",
                        "exposure_rates": {
                            "captain": captain_rate,
                            "core": core_rate,
                            "starting_qb": qb_rate,
                            "cheap_punt": punt_rate,
                        },
                        "quality_floor": dict(quality_floor or {}),
                        "game_scripts": [dict(script) for script in scripts],
                        "ownership_status": (
                            "cpt_flex_available" if stack_cfg["use_role_ownership"] else "unavailable"
                        ),
                        "correlation_policy": "qb_stack_diminishing_60_30_10_bringback_once_v1",
                    }
                    if num_lineups >= 10 and quality_floor:
                        qualifying: list[dict] = []
                        quality_rejected: list[dict] = []
                        other_rejected: list[dict] = []
                        for _, candidate in pool.iterrows():
                            player_id = str(candidate.get("player_id") or "")
                            if not player_id or player_id in flex_only_ids:
                                continue
                            base_kwargs = {
                                "score_col": score_col,
                                "enforce_single_te": enforce_single_te,
                                "avoid_dst_opponents": avoid_dst_opponents,
                                "contest_type": contest_type,
                                "stack_params": stack_cfg,
                                "locked_player_ids": locked_ids,
                                "flex_only_player_ids": flex_only_ids,
                                "rule_profile": rule_profile,
                                "portfolio_script": None,
                                "locked_captain_player_id": player_id,
                                "include_control_comparison": False,
                            }
                            candidate_lineup = self._solve_lineup(
                                pool, quality_floor=quality_floor, **base_kwargs
                            )
                            candidate_summary = {
                                "player_id": player_id,
                                "player_name": str(candidate.get("name") or candidate.get("player_name") or player_id),
                                "team": str(candidate.get("player_team") or candidate.get("team") or "").upper(),
                                "position": str(candidate.get("position") or "").upper(),
                            }
                            if candidate_lineup:
                                candidate_summary.update({
                                    "lineup_mean": sum(_safe_float(row.get("projection")) for row in candidate_lineup),
                                    "lineup_p90": sum(_safe_float(row.get("p90")) for row in candidate_lineup),
                                    "objective_score": sum(_safe_float(row.get("objective_score")) for row in candidate_lineup),
                                    "solver_objective_value": _safe_float(
                                        candidate_lineup[0].get("solver_objective_value")
                                    ),
                                    "best_lineup_players": [
                                        {
                                            "player_id": str(row.get("player_id") or ""),
                                            "player_name": str(row.get("player_name") or row.get("name") or row.get("player_id") or ""),
                                            "roster_position": str(row.get("roster_position") or ""),
                                        }
                                        for row in candidate_lineup
                                    ],
                                })
                                qualifying.append(candidate_summary)
                                continue
                            relaxed_lineup = self._solve_lineup(
                                pool, quality_floor=None, **base_kwargs
                            )
                            if relaxed_lineup:
                                lineup_mean = sum(_safe_float(row.get("projection")) for row in relaxed_lineup)
                                lineup_p90 = sum(_safe_float(row.get("p90")) for row in relaxed_lineup)
                                candidate_summary.update({
                                    "lineup_mean": lineup_mean,
                                    "lineup_p90": lineup_p90,
                                    "failed_mean_floor": lineup_mean < quality_floor["mean"],
                                    "failed_p90_floor": lineup_p90 < quality_floor["p90"],
                                })
                                quality_rejected.append(candidate_summary)
                            else:
                                candidate_summary["reason"] = "no_valid_construction_before_quality_floors"
                                other_rejected.append(candidate_summary)

                        qualifying.sort(
                            key=lambda row: (-_safe_float(row.get("objective_score")), str(row.get("player_id")))
                        )
                        minimum_distinct = min(3, len(qualifying))
                        forced_captain_ids = plan_showdown_captain_diversification(
                            qualifying, minimum_distinct=3
                        )
                        qualifying_teams = sorted({
                            str(row.get("team") or "") for row in qualifying if row.get("team")
                        })
                        both_teams_target = len(qualifying_teams) >= 2
                        captain_diversification.update({
                            "minimum_distinct_target": minimum_distinct,
                            "both_teams_target": both_teams_target,
                            "qualifying_captain_candidates": qualifying,
                            "quality_rejected_captain_candidates": quality_rejected,
                            "other_rejected_captain_candidates": other_rejected,
                            "planned_captain_player_ids": forced_captain_ids,
                        })
                        if len(qualifying) < 3:
                            captain_diversification["limitations"].append(
                                f"Only {len(qualifying)} Captain candidates passed all quality and construction constraints."
                            )
                        params.setdefault("strategy_runtime", {}).setdefault(
                            "showdown_portfolio_policy", {}
                        )["captain_diversification"] = captain_diversification

                underfill_diagnostics: dict = {
                    "attempted_lineup_number": None,
                    "reason_counts": {},
                    "counts_may_overlap": True,
                    "quality_floors_relaxed": False,
                }
                captain_choice_snapshots: list[dict] = []

                def _record_underfill_diagnostics(
                    lineup_number: int,
                    *,
                    exposure_remaining: dict,
                    captain_remaining: dict | None,
                    script: dict | None,
                    locked_captain_id: str | None,
                ) -> None:
                    if not portfolio_v3:
                        return
                    checks: list[tuple[str, dict]] = []
                    if quality_floor:
                        checks.extend([
                            ("failed_mean_floor", {"quality_floor": {"mean": 0.0, "p90": quality_floor["p90"]}}),
                            ("failed_p90_floor", {"quality_floor": {"mean": quality_floor["mean"], "p90": 0.0}}),
                        ])
                    checks.extend([
                        ("exposure_constraint", {"exposure_remaining": None, "captain_exposure_remaining": None}),
                        ("duplicate_lineup", {"exclude_lineups": None, "exclude_signatures": None}),
                        ("portfolio_script_diversification", {"portfolio_script": None}),
                        ("captain_diversification_constraint", {"locked_captain_player_id": None}),
                        (
                            "hard_correlation_constraint",
                            {"stack_params": {**stack_cfg, "require_starting_qb": False, "hard_qb_correlations": False}},
                        ),
                    ])
                    base = {
                        "score_col": score_col,
                        "exposure_remaining": exposure_remaining,
                        "captain_exposure_remaining": captain_remaining,
                        "exclude_lineups": exclude_lineups,
                        "exclude_signatures": exclude_signatures,
                        "enforce_single_te": enforce_single_te,
                        "avoid_dst_opponents": avoid_dst_opponents,
                        "contest_type": contest_type,
                        "stack_params": stack_cfg,
                        "locked_player_ids": locked_ids,
                        "flex_only_player_ids": flex_only_ids,
                        "rule_profile": rule_profile,
                        "quality_floor": quality_floor,
                        "portfolio_script": script,
                        "locked_captain_player_id": locked_captain_id,
                        "include_control_comparison": False,
                    }
                    reasons: list[str] = []
                    for reason, overrides in checks:
                        if self._solve_lineup(pool, **{**base, **overrides}):
                            reasons.append(reason)
                    if not reasons:
                        reasons = ["other_constraint"]
                    underfill_diagnostics["attempted_lineup_number"] = lineup_number
                    underfill_diagnostics["reason_counts"] = {
                        reason: reasons.count(reason) for reason in sorted(set(reasons))
                    }

                for lineup_index in range(num_lineups):
                    remaining = {
                        pid: (player_limits.get(pid, exposure_limit) if portfolio_v3 else exposure_limit)
                        - used_counts.get(pid, 0)
                        for pid in pool["player_id"].astype(str)
                    }
                    captain_remaining = {
                        pid: captain_limit - captain_counts.get(pid, 0)
                        for pid in pool["player_id"].astype(str)
                    } if portfolio_v3 else None
                    if captain_diversification["enabled"]:
                        captain_choice_snapshots.append({
                            "lineup_number": lineup_index + 1,
                            "exposure_remaining": dict(remaining),
                            "captain_exposure_remaining": dict(captain_remaining or {}),
                            "exclude_lineups": [set(values) for values in exclude_lineups],
                            "exclude_signatures": [list(values) for values in exclude_signatures],
                            "portfolio_script": (
                                dict(scripts[lineup_index])
                                if lineup_index < len(scripts) else None
                            ),
                            "forced_captain_player_id": (
                                forced_captain_ids[lineup_index]
                                if lineup_index < len(forced_captain_ids) else None
                            ),
                        })
                    lineup = self._solve_lineup(
                        pool,
                        score_col=score_col,
                        exposure_remaining=remaining,
                        captain_exposure_remaining=captain_remaining,
                        exclude_lineups=exclude_lineups,
                        exclude_signatures=exclude_signatures,
                        enforce_single_te=enforce_single_te,
                        avoid_dst_opponents=avoid_dst_opponents,
                        contest_type=contest_type,
                        stack_params=stack_cfg,
                        locked_player_ids=locked_ids,
                        flex_only_player_ids=flex_only_ids,
                        rule_profile=rule_profile,
                        quality_floor=quality_floor,
                        portfolio_script=(scripts[lineup_index] if lineup_index < len(scripts) else None),
                        locked_captain_player_id=(
                            forced_captain_ids[lineup_index]
                            if lineup_index < len(forced_captain_ids) else None
                        ),
                    )
                    if not lineup:
                        _record_underfill_diagnostics(
                            lineup_index + 1,
                            exposure_remaining=remaining,
                            captain_remaining=captain_remaining,
                            script=(scripts[lineup_index] if lineup_index < len(scripts) else None),
                            locked_captain_id=(
                                forced_captain_ids[lineup_index]
                                if lineup_index < len(forced_captain_ids) else None
                            ),
                        )
                        break
                    lineup_indices = {id_to_index[str(row.get("player_id"))] for row in lineup if str(row.get("player_id")) in id_to_index}
                    # Update counts and exclusion set
                    for row in lineup:
                        pid = str(row.get("player_id"))
                        used_counts[pid] = used_counts.get(pid, 0) + 1
                        if str(row.get("roster_position") or "").upper() == "CPT":
                            captain_counts[pid] = captain_counts.get(pid, 0) + 1
                    signature = []
                    for row in lineup:
                        pid = str(row.get("player_id"))
                        role = str(row.get("roster_position") or "").upper() if contest_type == "captain" else None
                        signature.append((pid, role))
                    lineup_results_local.append(lineup)
                    if portfolio_v3:
                        script = scripts[lineup_index] if lineup_index < len(scripts) else {"script_id": "best_available", "label": "Best available"}
                        for row in lineup:
                            row["portfolio_script_target"] = dict(script)
                        if quality_floor is None:
                            best_mean = sum(_safe_float(row.get("projection")) for row in lineup)
                            best_p90 = sum(_safe_float(row.get("p90")) for row in lineup)
                            quality_floor = {"mean": 0.85 * best_mean, "p90": 0.90 * best_p90}
                    if lineup_indices:
                        exclude_lineups.append(lineup_indices)
                    if signature:
                        exclude_signatures.append(signature)

                if captain_diversification["enabled"]:
                    captain_rows: dict[str, dict] = {}
                    selected_captain_quality: dict[str, list[dict]] = {}
                    for lineup_number, lineup in enumerate(lineup_results_local, start=1):
                        captain = next(
                            (row for row in lineup if str(row.get("roster_position") or "").upper() == "CPT"),
                            None,
                        )
                        if captain is None:
                            continue
                        player_id = str(captain.get("player_id") or "")
                        current = captain_rows.setdefault(player_id, {
                            "player_id": player_id,
                            "player_name": str(captain.get("player_name") or captain.get("name") or player_id),
                            "team": str(captain.get("player_team") or captain.get("team") or "").upper(),
                            "appearances": 0,
                        })
                        current["appearances"] += 1
                        selected_captain_quality.setdefault(player_id, []).append({
                            "lineup_number": lineup_number,
                            "lineup_mean": sum(
                                _safe_float(row.get("projection")) for row in lineup
                            ),
                            "lineup_p90": sum(
                                _safe_float(row.get("p90")) for row in lineup
                            ),
                            "solver_objective_value": _safe_float(
                                lineup[0].get("solver_objective_value")
                            ),
                        })
                    final_exposures = sorted(
                        captain_rows.values(), key=lambda row: (-int(row["appearances"]), str(row["player_name"]))
                    )
                    for row in final_exposures:
                        row["exposure"] = row["appearances"] / len(lineup_results_local) if lineup_results_local else 0.0
                    final_teams = {str(row.get("team") or "") for row in final_exposures}
                    distinct_achieved = len(final_exposures) >= int(captain_diversification["minimum_distinct_target"])
                    both_teams_achieved = (
                        not captain_diversification["both_teams_target"] or len(final_teams) >= 2
                    )
                    captain_diversification.update({
                        "final_captain_exposures": final_exposures,
                        "distinct_target_achieved": distinct_achieved,
                        "both_teams_target_achieved": both_teams_achieved,
                        "targets_achieved": distinct_achieved and both_teams_achieved,
                    })

                    qualifying_by_id = {
                        str(row.get("player_id") or ""): row
                        for row in captain_diversification["qualifying_captain_candidates"]
                    }
                    selected_quality_report: list[dict] = []
                    for player_id, selections in selected_captain_quality.items():
                        standalone = qualifying_by_id.get(player_id, {})
                        first = selections[0]
                        enriched_selections = []
                        for selection_number, selection in enumerate(selections, start=1):
                            snapshot = captain_choice_snapshots[
                                int(selection["lineup_number"]) - 1
                            ]
                            standalone_exposure_blockers = []
                            for standalone_player in standalone.get(
                                "best_lineup_players", []
                            ):
                                standalone_player_id = str(
                                    standalone_player.get("player_id") or ""
                                )
                                if _safe_float(
                                    snapshot["exposure_remaining"].get(
                                        standalone_player_id
                                    )
                                ) <= 0:
                                    standalone_exposure_blockers.append({
                                        "player_id": standalone_player_id,
                                        "player_name": str(
                                            standalone_player.get("player_name")
                                            or standalone_player_id
                                        ),
                                    })
                            enriched_selections.append({
                                **selection,
                                "selection_number": selection_number,
                                "mean_delta_from_first_selected": (
                                    selection["lineup_mean"] - first["lineup_mean"]
                                ),
                                "p90_delta_from_first_selected": (
                                    selection["lineup_p90"] - first["lineup_p90"]
                                ),
                                "mean_delta_from_standalone_best": (
                                    selection["lineup_mean"]
                                    - _safe_float(standalone.get("lineup_mean"))
                                ),
                                "p90_delta_from_standalone_best": (
                                    selection["lineup_p90"]
                                    - _safe_float(standalone.get("lineup_p90"))
                                ),
                                "standalone_best_exposure_blockers": (
                                    standalone_exposure_blockers
                                ),
                            })
                        selected_quality_report.append({
                            "player_id": player_id,
                            "player_name": str(
                                standalone.get("player_name")
                                or captain_rows[player_id]["player_name"]
                            ),
                            "team": str(
                                standalone.get("team") or captain_rows[player_id]["team"]
                            ),
                            "standalone_best": {
                                "lineup_mean": _safe_float(standalone.get("lineup_mean")),
                                "lineup_p90": _safe_float(standalone.get("lineup_p90")),
                                "solver_objective_value": _safe_float(
                                    standalone.get("solver_objective_value")
                                ),
                            },
                            "selected_lineups": enriched_selections,
                        })

                    unselected_reports: list[dict] = []
                    for player_id, candidate in qualifying_by_id.items():
                        if player_id in captain_rows:
                            continue
                        step_results: list[dict] = []
                        for snapshot in captain_choice_snapshots[:len(lineup_results_local)]:
                            lineup_number = int(snapshot["lineup_number"])
                            forced_id = str(
                                snapshot.get("forced_captain_player_id") or ""
                            )
                            if forced_id and forced_id != player_id:
                                step_results.append({
                                    "lineup_number": lineup_number,
                                    "status": "captain_diversity_reserved_slot",
                                    "reserved_for_player_id": forced_id,
                                    "reserved_for_player_name": str(
                                        qualifying_by_id.get(forced_id, {}).get(
                                            "player_name", forced_id
                                        )
                                    ),
                                })
                                continue

                            base = {
                                "score_col": score_col,
                                "exposure_remaining": snapshot["exposure_remaining"],
                                "captain_exposure_remaining": snapshot["captain_exposure_remaining"],
                                "exclude_lineups": snapshot["exclude_lineups"],
                                "exclude_signatures": snapshot["exclude_signatures"],
                                "enforce_single_te": enforce_single_te,
                                "avoid_dst_opponents": avoid_dst_opponents,
                                "contest_type": contest_type,
                                "stack_params": stack_cfg,
                                "locked_player_ids": locked_ids,
                                "flex_only_player_ids": flex_only_ids,
                                "rule_profile": rule_profile,
                                "quality_floor": quality_floor,
                                "portfolio_script": snapshot["portfolio_script"],
                                "locked_captain_player_id": player_id,
                                "include_control_comparison": False,
                            }
                            candidate_lineup = self._solve_lineup(pool, **base)
                            actual_lineup = lineup_results_local[lineup_number - 1]
                            actual_captain = next(
                                row for row in actual_lineup
                                if str(row.get("roster_position") or "").upper() == "CPT"
                            )
                            if candidate_lineup:
                                candidate_objective = _safe_float(
                                    candidate_lineup[0].get("solver_objective_value")
                                )
                                selected_objective = _safe_float(
                                    actual_lineup[0].get("solver_objective_value")
                                )
                                step_results.append({
                                    "lineup_number": lineup_number,
                                    "status": "available_lower_sequential_objective",
                                    "lineup_mean": sum(
                                        _safe_float(row.get("projection"))
                                        for row in candidate_lineup
                                    ),
                                    "lineup_p90": sum(
                                        _safe_float(row.get("p90"))
                                        for row in candidate_lineup
                                    ),
                                    "solver_objective_value": candidate_objective,
                                    "selected_captain_player_id": str(
                                        actual_captain.get("player_id") or ""
                                    ),
                                    "selected_captain_player_name": str(
                                        actual_captain.get("player_name")
                                        or actual_captain.get("name")
                                        or actual_captain.get("player_id")
                                        or ""
                                    ),
                                    "selected_solver_objective_value": selected_objective,
                                    "solver_objective_deficit": (
                                        candidate_objective - selected_objective
                                    ),
                                })
                                continue

                            reasons: list[str] = []
                            blocking_players: list[dict] = []
                            if _safe_float(
                                snapshot["captain_exposure_remaining"].get(player_id)
                            ) <= 0:
                                reasons.append("captain_exposure")
                            exposure_relaxed = self._solve_lineup(
                                pool,
                                **{
                                    **base,
                                    "exposure_remaining": None,
                                    "captain_exposure_remaining": None,
                                },
                            )
                            if exposure_relaxed:
                                reasons.append("player_exposure")
                                for row in exposure_relaxed:
                                    blocker_id = str(row.get("player_id") or "")
                                    if _safe_float(
                                        snapshot["exposure_remaining"].get(blocker_id)
                                    ) > 0:
                                        continue
                                    blocker_class = "core_player_exposure"
                                    if (
                                        str(row.get("position") or "").upper() == "QB"
                                        and bool(row.get("showdown_qb_eligible"))
                                    ):
                                        blocker_class = "starting_qb_exposure"
                                    elif _safe_float(
                                        row.get("base_salary", row.get("salary"))
                                    ) <= 1000:
                                        blocker_class = "cheap_punt_exposure"
                                    blocking_players.append({
                                        "player_id": blocker_id,
                                        "player_name": str(
                                            row.get("player_name")
                                            or row.get("name")
                                            or blocker_id
                                        ),
                                        "exposure_class": blocker_class,
                                    })
                            duplicate_relaxed = self._solve_lineup(
                                pool,
                                **{
                                    **base,
                                    "exclude_lineups": None,
                                    "exclude_signatures": None,
                                },
                            )
                            if duplicate_relaxed:
                                reasons.append("exact_duplicate_or_overlap")
                            if quality_floor and self._solve_lineup(
                                pool, **{**base, "quality_floor": None}
                            ):
                                reasons.append("quality_floor_after_prior_constraints")
                            if not reasons and self._solve_lineup(
                                pool,
                                **{
                                    **base,
                                    "exposure_remaining": None,
                                    "captain_exposure_remaining": None,
                                    "exclude_lineups": None,
                                    "exclude_signatures": None,
                                },
                            ):
                                reasons.append("exposure_duplicate_interaction")
                            step_results.append({
                                "lineup_number": lineup_number,
                                "status": "blocked",
                                "reasons": reasons or ["other_specific_constraint"],
                                "blocking_players": blocking_players,
                            })

                        available_steps = [
                            row for row in step_results
                            if row.get("status") == "available_lower_sequential_objective"
                        ]
                        blocked_steps = [
                            row for row in step_results if row.get("status") == "blocked"
                        ]
                        if available_steps:
                            primary_reason = "lower_solver_objective_at_available_sequential_step"
                            best_available = max(
                                available_steps,
                                key=lambda row: _safe_float(
                                    row.get("solver_objective_value")
                                ),
                            )
                        else:
                            reason_counts: dict[str, int] = {}
                            for row in blocked_steps:
                                for reason in row.get("reasons", []):
                                    reason_counts[str(reason)] = (
                                        reason_counts.get(str(reason), 0) + 1
                                    )
                            primary_reason = (
                                max(
                                    reason_counts,
                                    key=lambda reason: (reason_counts[reason], reason),
                                )
                                if reason_counts
                                else "captain_diversity_reserved_slots"
                            )
                            best_available = None
                        unselected_reports.append({
                            "player_id": player_id,
                            "player_name": str(candidate.get("player_name") or player_id),
                            "team": str(candidate.get("team") or ""),
                            "position": str(candidate.get("position") or ""),
                            "standalone_best": {
                                "lineup_mean": _safe_float(candidate.get("lineup_mean")),
                                "lineup_p90": _safe_float(candidate.get("lineup_p90")),
                                "solver_objective_value": _safe_float(
                                    candidate.get("solver_objective_value")
                                ),
                            },
                            "primary_reason": primary_reason,
                            "best_available_sequential_step": best_available,
                            "step_results": step_results,
                        })

                    captain_diversification["selection_diagnostics"] = {
                        "construction_mode": "sequential_greedy",
                        "is_joint_portfolio_optimization": False,
                        "explanation": (
                            "The optimizer solves one lineup at a time. Earlier lineups "
                            "consume player and Captain exposure and become duplicate exclusions, "
                            "so lineup order changes the feasible choices available later."
                        ),
                        "selected_captain_quality": sorted(
                            selected_quality_report,
                            key=lambda row: str(row.get("player_name") or ""),
                        ),
                        "unselected_qualifying_captains": unselected_reports,
                    }
                    if not distinct_achieved:
                        captain_diversification["limitations"].append("Distinct-Captain target was not achieved.")
                    if not both_teams_achieved:
                        captain_diversification["limitations"].append("Both-team Captain representation was not achieved.")
                    params.setdefault("strategy_runtime", {}).setdefault(
                        "showdown_portfolio_policy", {}
                    )["captain_diversification"] = captain_diversification

                status_local = "completed" if lineup_results_local else "failed"
                if status_local == "completed":
                    message_local = (
                        f"Optimizer completed: {len(lineup_results_local)} lineup(s) "
                        f"generated (mode={contest_type})"
                    )
                    if not portfolio_v3:
                        message_local += f"; max exposure={max_exposure:.2f}"
                    if portfolio_v3:
                        message_local += (
                            f"; CPT/core/QB/punt exposure={captain_rate:.2f}/"
                            f"{core_rate:.2f}/{qb_rate:.2f}/{punt_rate:.2f}"
                            "; hard QB correlations=enabled; quality floors=85% mean and 90% P90"
                        )
                        if stack_cfg["use_role_ownership"]:
                            message_local += "; CPT/FLEX ownership=enabled"
                        else:
                            message_local += "; GPP ownership unavailable — optimizing ceiling/correlation only"
                        if len(lineup_results_local) < num_lineups:
                            reason_counts = underfill_diagnostics.get("reason_counts") or {}
                            reason_text = ", ".join(
                                f"{reason.replace('_', ' ')} ({count})"
                                for reason, count in sorted(reason_counts.items())
                            ) or "other constraint (1)"
                            message_local += (
                                f"; generated {len(lineup_results_local)} of {num_lineups} requested "
                                "because the remaining candidates did not satisfy all portfolio "
                                f"constraints; rejection diagnostics (counts may overlap): {reason_text}; "
                                "quality floors were not relaxed"
                            )
                            params.setdefault("strategy_runtime", {}).setdefault(
                                "showdown_portfolio_policy", {}
                            )["underfill_diagnostics"] = dict(underfill_diagnostics)
                        if captain_diversification["enabled"]:
                            message_local += (
                                "; Captain diversity="
                                f"{len(captain_diversification['final_captain_exposures'])} distinct, "
                                f"both teams={'yes' if captain_diversification.get('both_teams_target_achieved') else 'no'}, "
                                f"target status={'PASS' if captain_diversification['targets_achieved'] else 'LIMITED'}"
                            )
                    if strategy == CLASSIC_HEAD_TO_HEAD_STRATEGY_ID:
                        message_local += f" using {CLASSIC_HEAD_TO_HEAD_STRATEGY_ID}"
                    elif contest_format == "classic" and objective == "cash":
                        message_local += f" using {CASH_OBJECTIVE_ID}"
                    message_local += f"; stack policy={stack_policy['policy_id']}"
                    if contest_format == "showdown":
                        starter_runtime = params.get("strategy_runtime", {}).get(
                            "starter_qb_filter", {}
                        )
                        message_local += (
                            "; starter QB filter="
                            f"{starter_runtime.get('evidence_status', 'unavailable')}"
                        )
                        if strategy in SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_IDS:
                            message_local += (
                                "; captain position prior="
                                f"{params['objective_config']['captain_prior_strength']:.2f}"
                            )
                        if require_qb_captain_receiver:
                            message_local += (
                                f"; rule={SHOWDOWN_QB_CAPTAIN_RECEIVER_RULE_ID}"
                            )
                else:
                    if portfolio_v3:
                        params.setdefault("strategy_runtime", {}).setdefault(
                            "showdown_portfolio_policy", {}
                        )["underfill_diagnostics"] = dict(underfill_diagnostics)
                        message_local = (
                            f"Optimizer generated 0 of {num_lineups} requested lineups because "
                            "no candidate satisfied all portfolio constraints; quality floors "
                            "were not relaxed."
                        )
                    else:
                        message_local = "Optimizer failed to find lineup (check salaries/projections)."
                    if require_qb_captain_receiver:
                        message_local += (
                            f" Enforced rule: {SHOWDOWN_QB_CAPTAIN_RECEIVER_RULE_ID}."
                        )
                return lineup_results_local, status_local, message_local

            lineup_results: List[List[dict]] = []
            status: str
            message: str
            uniqueness_overlap: int | None = None
            correlation_objective_multiplier = 1.0

            use_gpp = (
                strategy_config["engine"] in {"slate_aware_gpp", "large_gpp_portfolio"}
                and contest_format == "classic"
                and objective == "gpp"
            )
            if use_gpp:
                try:
                    maximum_exposure_by_player = dict(
                        params.get("maximum_exposure_by_player") or {}
                    )
                    minimum_exposure_by_player = dict(
                        params.get("minimum_exposure_by_player") or {}
                    )
                    conflicting_lock_caps = {
                        player_id
                        for player_id in locked_ids
                        if player_id in maximum_exposure_by_player
                        and float(maximum_exposure_by_player[player_id]) < 1.0
                    }
                    if conflicting_lock_caps:
                        raise ValueError(
                            "Locked players require 100% maximum exposure: "
                            + ", ".join(sorted(conflicting_lock_caps))
                        )
                    for player_id in locked_ids:
                        maximum_exposure_by_player[player_id] = 1.0
                        minimum_exposure_by_player[player_id] = 1.0
                    ownership_available = (
                        "ownership" in pool.columns
                        and pd.to_numeric(pool["ownership"], errors="coerce")
                        .notna()
                        .any()
                    )
                    gpp_result = run_gpp_pipeline(
                        season=season,
                        week=week,
                        slate=slate,
                        num_lineups=num_lineups,
                        engine=self.engine,
                        players=self._gpp_players_from_pool(pool),
                        ownership_available=ownership_available,
                        max_exposure=max_exposure,
                        enforce_single_te=enforce_single_te,
                        avoid_dst_opponents=avoid_dst_opponents,
                        large_gpp=(strategy == CLASSIC_LARGE_GPP_STRATEGY_ID),
                        minimum_uniqueness=int(params.get("minimum_uniqueness", 2)),
                        max_from_team=params.get("max_players_per_team"),
                        max_from_game=params.get("max_players_per_game"),
                        stack_templates=params.get("stack_templates"),
                        maximum_exposure_by_player=maximum_exposure_by_player,
                        minimum_exposure_by_player=minimum_exposure_by_player,
                    )
                    lineup_results = [
                        [self._gpp_player_to_dict(p) for p in lineup] for lineup in gpp_result.lineups
                    ]
                    for lineup, comparison in zip(lineup_results, gpp_result.control_comparisons):
                        lineup[0]["lineup_control_comparison"] = comparison
                    site_ids = {str(row["player_id"]): row.get("dk_player_id")
                                for row in pool.to_dict("records")}
                    for lineup in lineup_results:
                        for player in lineup:
                            player["dk_player_id"] = site_ids.get(str(player["player_id"]))
                    status = gpp_result.status
                    uniqueness_overlap = gpp_result.config.uniqueness_overlap
                    correlation_objective_multiplier = (
                        gpp_result.config.objective_weights.correlation
                        * gpp_result.config.correlation_bonus
                    )
                    params["strategy_runtime"]["lineup_correlation"][
                        "objective_multiplier"
                    ] = correlation_objective_multiplier
                    message = (
                        f"{gpp_result.message}; strategy={strategy}; "
                        f"validation=slate-aware-config"
                    )
                    stack_policy = {
                        "policy_id": (
                            "classic_large_gpp_flexible_stacks_v1"
                            if strategy == CLASSIC_LARGE_GPP_STRATEGY_ID
                            else "classic_gpp_slate_aware_stack_v1"
                        ),
                        "contest_format": "classic",
                        "objective": "gpp",
                        "enabled": True,
                        "stack_min": gpp_result.config.stack_rules.min_pass_catchers,
                        "stack_max": None,
                        "bringback": (
                            gpp_result.config.stack_rules.min_bring_backs > 0
                        ),
                        "include_rb_in_stack": True,
                        "bringback_positions": ["RB", "WR", "TE"],
                        "max_from_team": gpp_result.config.stack_rules.max_from_team,
                        "evidence_status": "strategy_runtime",
                        "description": (
                            "Flexible portfolio stack policy resolved by the selected "
                            "GPP strategy."
                        ),
                        "source": "optimizer_strategy",
                    }
                    stack_cfg = dict(stack_policy)
                    params["stack_policy_id"] = stack_policy["policy_id"]
                    params["stack_policy"] = stack_policy
                    params.setdefault("strategy_runtime", {}).update({
                        "iterations": gpp_result.iterations,
                        "analysis": asdict(gpp_result.analysis),
                        "config": asdict(gpp_result.config),
                        "portfolio": asdict(gpp_result.portfolio),
                    })
                except Exception as exc:  # noqa: BLE001
                    lineup_results = []
                    status = "failed"
                    message = f"{strategy} failed: {exc}"
            elif single_entry:
                from .showdown_single_entry import select_single_entry_lineups
                from .showdown_contests import fetch_contests, select_contests

                contest_metadata = params.get("contest_metadata")
                contest_selection_report = None
                if strategy == SHOWDOWN_SINGLE_ENTRY_PORTFOLIO_STRATEGY_ID and params.get("contest_urls"):
                    available = fetch_contests(
                        params["contest_urls"], manual=params.get("manual_contest_metadata"),
                    )
                    draft_groups = {row.get("draft_group_id") for row in available if row.get("draft_group_id") is not None}
                    if len(draft_groups) > 1:
                        raise ValueError("All pasted contests must belong to the same DraftKings draft group")
                    contest_metadata, contest_selection_report = select_contests(
                        available, mode=params.get("contest_selection", "auto"),
                        budget=params.get("maximum_total_entry_budget"),
                        maximum=params.get("maximum_contests_to_enter"),
                    )
                num_contests = (
                    1 if strategy == SHOWDOWN_SINGLE_ENTRY_GPP_STRATEGY_ID
                    else len(contest_metadata) if contest_metadata is not None
                    else int(params.get("num_single_entry_contests", 3))
                )
                if num_contests < 1 or num_contests > 50:
                    raise ValueError("Single-entry portfolio must contain 1 to 50 contests")
                params["num_single_entry_contests"] = num_contests
                params["num_lineups"] = num_contests
                num_lineups = num_contests
                candidates = []
                excluded = []
                candidate_limit = max(10, min(50, int(params.get("single_entry_candidate_pool_size", 30))))
                broad_count = max(10, int(candidate_limit * 0.6))
                forced_count = (candidate_limit - broad_count) // 2
                forced_captains = [
                    str(player_id) for player_id in pool.sort_values(score_col, ascending=False)["player_id"]
                    if str(player_id) not in flex_only_ids
                ]
                teams = sorted(str(team) for team in pool["player_team"].dropna().unique())
                script_targets = [
                    {"script_id": f"single_entry_{kind}_{team}", "kind": kind, "team": team}
                    for kind in ("run_control", "pass_led", "contrarian")
                    for team in teams
                ]
                for candidate_index in range(candidate_limit):
                    forced_captain = (
                        forced_captains[candidate_index - broad_count]
                        if broad_count <= candidate_index < broad_count + forced_count
                        and candidate_index - broad_count < len(forced_captains)
                        else None
                    )
                    script_index = candidate_index - broad_count - forced_count
                    script_target = (
                        script_targets[script_index]
                        if script_index >= 0 and script_index < len(script_targets)
                        else None
                    )
                    lineup = self._solve_lineup(
                        pool, score_col=score_col, exclude_signatures=excluded,
                        contest_type=contest_type, stack_params=stack_cfg,
                        locked_player_ids=locked_ids, flex_only_player_ids=flex_only_ids,
                        rule_profile=rule_profile, include_control_comparison=False,
                        locked_captain_player_id=forced_captain,
                        portfolio_script=script_target,
                    )
                    if not lineup:
                        if forced_captain or script_target:
                            continue
                        break
                    excluded.append([(str(row["player_id"]), str(row["roster_position"])) for row in lineup])
                    correlation = score_lineup_correlations(lineup, profile=rule_profile)
                    lineup[0]["lineup_correlation_summary"] = _saturated_showdown_correlation_summary(lineup, correlation)
                    candidates.append(lineup)
                lineup_results, single_entry_report = select_single_entry_lineups(
                    candidates, num_contests=num_contests,
                    weights=params.get("single_entry_objective_weights"),
                    contest_metadata=contest_metadata,
                )
                if contest_selection_report:
                    single_entry_report["contest_selection"] = contest_selection_report
                params.setdefault("strategy_runtime", {})["single_entry"] = single_entry_report
                status = "completed" if lineup_results else "failed"
                message = f"Selected {len(lineup_results)} single-entry contest lineup(s) from {len(candidates)} candidates"
            else:
                lineup_results, status, message = _run_baseline()
                message += f"; strategy={strategy}"

            if (
                lineup_results
                and contest_format == "classic"
                and (
                    objective == "gpp"
                    or strategy == CLASSIC_HEAD_TO_HEAD_STRATEGY_ID
                )
            ):
                ok, reason = self._validate_classic_lineups(
                    lineup_results,
                    requested_lineups=num_lineups,
                    max_exposure=max_exposure,
                    enforce_single_te=enforce_single_te,
                    avoid_dst_opponents=avoid_dst_opponents,
                    uniqueness_overlap=uniqueness_overlap,
                    locked_player_ids=locked_ids,
                )
                if not ok:
                    status = "failed"
                    message = f"{strategy} lineup validation failed: {reason}"
                    lineup_results = []

            if lineup_results and contest_format == "showdown":
                for lineup in lineup_results:
                    control_comparison = lineup[0].pop("lineup_control_comparison", None)
                    if portfolio_v3 and isinstance(control_comparison, dict):
                        control_comparison["rule_contributions"] = [
                            row for row in control_comparison.get("rule_contributions", [])
                            if not any(rule_id in str(row.get("rule_id") or "") for rule_id in _SATURATED_SHOWDOWN_RULE_IDS)
                            and "showdown_fragile_punt" not in str(row.get("rule_id") or "")
                        ]
                        control_comparison["correlation_policy"] = (
                            "qb_stack_diminishing_60_30_10_bringback_once_v1"
                        )
                    lineup.sort(
                        key=lambda row: (
                            0
                            if str(row.get("roster_position") or "").upper()
                            == "CPT"
                            else 1,
                            str(row.get("player_id") or row.get("dk_player_id") or ""),
                        )
                    )
                    if control_comparison is not None:
                        lineup[0]["lineup_control_comparison"] = control_comparison
                    if portfolio_v3 or single_entry:
                        actual_script = classify_showdown_game_script(lineup)
                        for row in lineup:
                            row["portfolio_game_script"] = dict(actual_script)
                    for slot_index, row in enumerate(lineup):
                        row["lineup_slot_index"] = slot_index
                        row["roster_position"] = str(
                            row.get("roster_position") or ""
                        ).upper()
                if portfolio_v3:
                    exposure_rates = {
                        "captain": float(params.get("captain_max_exposure", 0.60)),
                        "core": float(params.get("core_player_max_exposure", 0.80)),
                        "starting_qb": float(params.get("starting_qb_max_exposure", 1.00)),
                        "cheap_punt": float(params.get("cheap_punt_max_exposure", 0.40)),
                    }
                    exposure_report = summarize_showdown_portfolio_exposure(
                        lineup_results,
                        requested_lineups=num_lineups,
                        exposure_rates=exposure_rates,
                    )
                    chalk_metrics = add_showdown_lineup_chalk_metrics(lineup_results)
                    strategy_runtime = params.setdefault("strategy_runtime", {})
                    portfolio_runtime = strategy_runtime.setdefault(
                        "showdown_portfolio_policy", {}
                    )
                    portfolio_runtime["exposure_report"] = exposure_report
                    portfolio_runtime["lineup_duplication_risk"] = chalk_metrics
                    if lineup_results and lineup_results[0]:
                        lineup_results[0][0]["portfolio_exposure_report"] = exposure_report
                        underfill = portfolio_runtime.get("underfill_diagnostics")
                        if isinstance(underfill, dict) and underfill.get("reason_counts"):
                            lineup_results[0][0]["portfolio_underfill_diagnostics"] = dict(
                                underfill
                            )
                        captain_diversity = portfolio_runtime.get("captain_diversification")
                        if isinstance(captain_diversity, dict) and captain_diversity.get("enabled"):
                            lineup_results[0][0]["captain_diversification_report"] = dict(
                                captain_diversity
                            )
                ok, reason = self._validate_showdown_lineups(
                    lineup_results,
                    requested_lineups=num_lineups,
                    max_exposure=(1.0 if portfolio_v3 or single_entry else max_exposure),
                    require_qb_captain_receiver=require_qb_captain_receiver,
                    portfolio_policy=portfolio_v3 or single_entry,
                    allow_duplicate_lineups=single_entry,
                    portfolio_exposure_rates=(exposure_rates if portfolio_v3 else None),
                    locked_player_ids=locked_ids,
                    flex_only_player_ids=flex_only_ids,
                )
                if not ok:
                    params.setdefault("strategy_runtime", {})["validation"] = {
                        "status": "failed",
                        "rejection_reason": reason,
                        "optimizer_rule_ids": [
                            str(rule["rule_id"]) for rule in optimizer_rules
                        ],
                        "qb_captain_same_team_wr_te": (
                            require_qb_captain_receiver
                        ),
                        "flex_only_player_ids": sorted(flex_only_ids),
                    }
                    status = "failed"
                    message = f"{strategy} lineup validation failed: {reason}"
                    lineup_results = []
                else:
                    strategy_runtime = params.setdefault("strategy_runtime", {})
                    strategy_runtime["validation"] = {
                        "status": "passed",
                        "lineup_count": len(lineup_results),
                        "salary_cap": SALARY_CAP,
                        "requested_lineups": num_lineups,
                        "max_exposure": max_exposure,
                        "captain_slots": 1,
                        "flex_slots": 5,
                        "max_players_per_team": 5,
                        "optimizer_rule_ids": [
                            str(rule["rule_id"]) for rule in optimizer_rules
                        ],
                        "qb_captain_same_team_wr_te": (
                            require_qb_captain_receiver
                        ),
                        "flex_only_player_ids": sorted(flex_only_ids),
                    }
                    message += "; showdown lineup validation=passed"

            # Validate stacks/bring-backs for any lineups produced
            if lineup_results:
                ok, reason = self._lineups_satisfy_stack(lineup_results, stack_cfg, contest_type)
                if not ok:
                    status = "failed"
                    message = (
                        f"{strategy} stack/bring-back validation failed: {reason}"
                    )
                    lineup_results = []

            if status == "completed" and lineup_results:
                if contest_format == "classic":
                    strategy_runtime = params.setdefault("strategy_runtime", {})
                    strategy_runtime["validation"] = {
                        "status": "passed",
                        "lineup_count": len(lineup_results),
                        "salary_cap": SALARY_CAP,
                        "team_limit": TEAM_LIMIT,
                        "requested_lineups": num_lineups,
                        "max_exposure": max_exposure,
                        "enforce_single_te": enforce_single_te,
                        "avoid_dst_opponents": avoid_dst_opponents,
                        "uniqueness_overlap": uniqueness_overlap,
                    }
                    message += "; lineup validation=passed"
                for lineup in lineup_results:
                    stack_summary = (
                        summarize_classic_stack(lineup)
                        if contest_format == "classic"
                        else {}
                    )
                    ceiling_summary = summarize_individual_ceiling_sum(lineup)
                    correlation_summary = score_lineup_correlations(
                        lineup,
                        profile=rule_profile,
                        objective_multiplier=correlation_objective_multiplier,
                    )
                    if (portfolio_v3 or single_entry) and contest_format == "showdown":
                        correlation_summary = _saturated_showdown_correlation_summary(
                            lineup, correlation_summary
                        )
                        script = lineup[0].get("portfolio_game_script")
                        if isinstance(script, dict):
                            correlation_summary["implied_game_script"] = {
                                "script_id": script.get("script_id"),
                                "label": script.get("label"),
                                "evidence": {
                                    "classification": "actual_lineup_construction_v1",
                                    **script,
                                    "portfolio_target": lineup[0].get("portfolio_script_target"),
                                },
                            }
                    context_rule_counts: dict[str, int] = {}
                    for lineup_row in lineup:
                        evaluation = lineup_row.get(
                            "optimizer_context_rule_evaluation"
                        )
                        if not isinstance(evaluation, dict):
                            continue
                        for trigger in evaluation.get("triggered_rules") or []:
                            reason_code = str(trigger.get("reason_code") or "")
                            if reason_code:
                                context_rule_counts[reason_code] = (
                                    context_rule_counts.get(reason_code, 0) + 1
                                )
                    context_summary = {
                        "library_id": context_result.summary["library_id"],
                        "library_version": context_result.summary[
                            "library_version"
                        ],
                        "total_adjustment": sum(
                            _safe_float(
                                lineup_row.get("optimizer_context_adjustment")
                            )
                            * (
                                1.5
                                if str(
                                    lineup_row.get("roster_position") or ""
                                ).upper()
                                == "CPT"
                                else 1.0
                            )
                            for lineup_row in lineup
                        ),
                        "trigger_counts": dict(sorted(context_rule_counts.items())),
                    }
                    for row in lineup:
                        row["lineup_stack_policy"] = dict(stack_policy)
                        if stack_summary:
                            row["lineup_stack_summary"] = stack_summary
                        row["lineup_optimizer_strategy"] = dict(strategy_config)
                        row["lineup_optimizer_rules"] = [
                            dict(rule) for rule in optimizer_rules
                        ]
                        row["lineup_context_summary"] = context_summary
                        row["lineup_correlation_summary"] = correlation_summary
                        row["lineup_ceiling_summary"] = ceiling_summary
                if strategy == CLASSIC_HEAD_TO_HEAD_STRATEGY_ID:
                    for lineup in lineup_results:
                        lineup_summary = summarize_head_to_head_lineup(lineup)
                        for row in lineup:
                            row["lineup_h2h_summary"] = lineup_summary
                elif contest_format == "classic" and objective == "cash":
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

        final_pool_ids = (
            set(pool["player_id"].astype(str))
            if not pool.empty and "player_id" in pool
            else set()
        )
        player_pool_rows: list[dict] = []
        unresolved_safety_audits = [
            row
            for row in safety_result.audit_rows
            if not str(row.get("player_id") or "").strip()
        ]
        if not initial_pool.empty and "player_id" in initial_pool:
            for row in initial_pool.drop_duplicates("player_id").to_dict(
                orient="records"
            ):
                player_id = _safe_text(row.get("player_id"))
                safety_audit = safety_audit_by_player.get(player_id, {})
                context_audit = context_audit_by_player.get(player_id, {})
                if not player_id and unresolved_safety_audits:
                    safety_audit = unresolved_safety_audits.pop(0)
                safety_context = safety_audit.get("context") or {}
                context_observed_at = _json_safe(
                    row.get("pregame_context_observed_at")
                )
                role_label = _json_safe(row.get("pregame_role_label"))
                injury_status = _json_safe(row.get("pregame_injury_status"))
                player_pool_rows.append(
                    {
                        "player_id": player_id,
                        "player_name": _safe_text(
                            row.get("player_display_name"),
                            row.get("player_name"),
                            row.get("name"),
                            player_id,
                        ),
                        "position": _safe_text(row.get("position")),
                        "team": _safe_text(
                            row.get("player_team"), row.get("team")
                        ),
                        "opponent_team": _safe_text(row.get("opponent_team")),
                        "salary": int(_safe_float(row.get("salary"))),
                        "projection": _safe_float(
                            row.get("projection", row.get("predicted_mean"))
                        ),
                        "p90": _safe_float(
                            row.get("p90", row.get("predicted_p90"))
                        ),
                        "optimizer_context_adjustment": (
                            _safe_float(context_audit.get("adjustment"))
                            if context_audit
                            else None
                        ),
                        "optimizer_context_reason_codes": list(
                            context_audit.get("reason_codes") or []
                        ),
                        "player_status": _json_safe(row.get("player_status")),
                        "pregame_availability_probability": _json_safe(
                            row.get("pregame_availability_probability")
                        ),
                        "pregame_start_probability": _json_safe(
                            row.get("pregame_start_probability")
                        ),
                        "pregame_carry_share": _json_safe(
                            row.get("pregame_carry_share")
                        ),
                        "pregame_target_share": _json_safe(
                            row.get("pregame_target_share")
                        ),
                        "pregame_expected_snaps": _json_safe(
                            row.get("pregame_expected_snaps")
                        ),
                        "pregame_expected_routes": _json_safe(
                            row.get("pregame_expected_routes")
                        ),
                        "pregame_expected_carries": _json_safe(
                            row.get("pregame_expected_carries")
                        ),
                        "pregame_expected_targets": _json_safe(
                            row.get("pregame_expected_targets")
                        ),
                        "pregame_red_zone_share": _json_safe(
                            row.get("pregame_red_zone_share")
                        ),
                        "pregame_goal_line_share": _json_safe(
                            row.get("pregame_goal_line_share")
                        ),
                        "pregame_context_run_id": _json_safe(
                            row.get("pregame_context_run_id")
                        ),
                        "pregame_context_source": _json_safe(
                            row.get("pregame_context_source")
                        ),
                        "pregame_context_observed_at": _json_safe(
                            context_observed_at
                            if context_observed_at is not None
                            else safety_context.get("observed_at")
                        ),
                        "pregame_role_label": _json_safe(
                            role_label
                            if role_label is not None
                            else safety_context.get("role_label")
                        ),
                        "pregame_injury_status": _json_safe(
                            injury_status
                            if injury_status is not None
                            else safety_context.get("injury_status")
                        ),
                        "identity_resolved": safety_audit.get(
                            "identity_resolved", bool(player_id)
                        ),
                        "flex_only": player_id in flex_only_ids,
                        "included": player_id in final_pool_ids,
                        "removal_stage": (
                            "pre_opportunity_eligibility"
                            if player_id not in raw_pool_ids
                            else "opportunity_gate"
                            if player_id not in opportunity_eligible_ids
                            else "optimizer_filter"
                            if player_id not in final_pool_ids
                            else None
                        ),
                        "exclusion_reasons": exclusion_reasons.get(player_id, []),
                        "exclusion_details": exclusion_details.get(player_id, []),
                        "warnings": player_warnings.get(player_id, []),
                        "rule_evaluation": safety_audit.get("rule_evaluation"),
                        "context_rule_evaluation": context_audit.get(
                            "rule_evaluation"
                        ),
                    }
                )
        removal_reason_counts: dict[str, int] = {}
        prior_eligibility_reason_counts: dict[str, int] = {}
        for row in player_pool_rows:
            if row["included"]:
                continue
            target = (
                removal_reason_counts
                if row.get("removal_stage") == "opportunity_gate"
                else prior_eligibility_reason_counts
            )
            for reason in row.get("exclusion_reasons") or ["unspecified"]:
                target[reason] = target.get(reason, 0) + 1
        params.setdefault("strategy_runtime", {})["player_pool"] = {
            "projection_run_id": projection_run_id,
            "initial_count": len(player_pool_rows),
            "source_pool_count": len(player_pool_rows),
            "raw_pool_count": len(raw_pool_ids),
            "opportunity_eligible_count": len(opportunity_eligible_ids),
            "optimizer_eligible_count": len(final_pool_ids),
            "eligible_count": len(eligible_pool_ids),
            "included_count": sum(row["included"] for row in player_pool_rows),
            "excluded_count": sum(not row["included"] for row in player_pool_rows),
            "candidate_excluded_count": len(eligible_pool_ids - final_pool_ids),
            "ineligible_count": len(
                set(row["player_id"] for row in player_pool_rows)
                - eligible_pool_ids
            ),
            "warning_player_count": sum(
                bool(row.get("warnings")) for row in player_pool_rows
            ),
            "removal_reason_counts": dict(sorted(removal_reason_counts.items())),
            "prior_eligibility_removal_reason_counts": dict(
                sorted(prior_eligibility_reason_counts.items())
            ),
            "safety": safety_result.summary,
            "context_scoring": context_result.summary,
            "rows": player_pool_rows,
        }

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
